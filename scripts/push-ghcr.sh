#!/usr/bin/env bash
# Build the app image and push it to GitHub Container Registry (ghcr.io).
#
# Usage:
#   export GITHUB_TOKEN=ghp_...   # PAT with write:packages (or GHCR_TOKEN)
#   ./scripts/push-ghcr.sh
#
# Or read the token from KeePassXC (tries, in order):
#   1. Entry titled GITHUB_TOKEN_PUSH_REGISTRY
#   2. Entry titled like this git repo (e.g. who-brings-what)
#   3. Entry tagged/labelled with that repo name
#   export KEEPASSXC_VAULT=/path/to/vault.kdbx
#   export KEEPASSXC_PASSWORD=...   # optional; prompts if unset
#   ./scripts/push-ghcr.sh
#
# Optional:
#   GITHUB_ACTOR=your-github-username
#   IMAGE_TAG=latest
#   GHCR_IMAGE=ghcr.io/owner/repo   # override auto-detected image name
#   KEEPASSXC_KEY_FILE=/path/to/key  # if the vault uses a key file

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

KEEPASS_DEFAULT_ENTRY="GITHUB_TOKEN_PUSH_REGISTRY"

keepassxc_cli() {
  if ! command -v keepassxc-cli >/dev/null 2>&1; then
    echo "Error: keepassxc-cli is not installed (required when using KEEPASSXC_VAULT)." >&2
    exit 1
  fi
  if [[ -n "${KEEPASSXC_PASSWORD:-}" ]]; then
    printf '%s\n' "$KEEPASSXC_PASSWORD" | keepassxc-cli "$@"
  else
    keepassxc-cli "$@"
  fi
}

keepassxc_db_args() {
  KEEPASSXC_DB_ARGS=(-q)
  if [[ -n "${KEEPASSXC_KEY_FILE:-}" ]]; then
    KEEPASSXC_DB_ARGS+=(-k "$KEEPASSXC_KEY_FILE")
  fi
}

escape_regex() {
  printf '%s' "$1" | sed 's/[][(){}.^$|*+?\\]/\\&/g'
}

detect_repo_name() {
  local origin="${1:-}"
  local repo=""

  if [[ "$origin" =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
    repo="${BASH_REMATCH[2]}"
  elif [[ -n "${GHCR_IMAGE:-}" && "${GHCR_IMAGE}" =~ /([^/]+)$ ]]; then
    repo="${BASH_REMATCH[1]}"
  fi
  printf '%s' "$repo"
}

find_keepass_entry_by_title() {
  local vault="$1"
  local entry_name="$2"
  local escaped matches count

  [[ -n "$entry_name" ]] || return 1

  escaped="$(escape_regex "$entry_name")"
  keepassxc_db_args
  matches="$(
    keepassxc_cli ls -R -f "${KEEPASSXC_DB_ARGS[@]}" "$vault" 2>/dev/null \
      | grep -E "(^|/)${escaped}$" \
      || true
  )"
  count="$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')"

  [[ "$count" -eq 1 ]] || return 1
  printf '%s\n' "$matches" | sed '/^$/d' | head -n 1
}

entry_has_tag() {
  local vault="$1"
  local entry_path="$2"
  local tag="$3"
  local tags

  tags="$(
    keepassxc_cli show -a Tags "${KEEPASSXC_DB_ARGS[@]}" "$vault" "$entry_path" 2>/dev/null \
      || true
  )"
  [[ -n "$tags" ]] || return 1

  local IFS=$',\n'
  local part
  for part in $tags; do
    part="${part#"${part%%[![:space:]]*}"}"
    part="${part%"${part##*[![:space:]]}"}"
    [[ "$part" == "$tag" ]] && return 0
  done
  return 1
}

find_keepass_entry_by_tag() {
  local vault="$1"
  local tag="$2"
  local entry matches=() count

  [[ -n "$tag" ]] || return 1

  keepassxc_db_args
  while IFS= read -r entry; do
    [[ -n "$entry" ]] || continue
    if entry_has_tag "$vault" "$entry" "$tag"; then
      matches+=("$entry")
    fi
  done < <(keepassxc_cli ls -R -f "${KEEPASSXC_DB_ARGS[@]}" "$vault" 2>/dev/null || true)

  count="${#matches[@]}"
  [[ "$count" -eq 1 ]] || return 1
  printf '%s\n' "${matches[0]}"
}

resolve_keepass_entry() {
  local vault="$1"
  local repo_name="$2"
  local entry_path=""
  local tried=()

  if entry_path="$(find_keepass_entry_by_title "$vault" "$KEEPASS_DEFAULT_ENTRY")"; then
    tried+=("title:${KEEPASS_DEFAULT_ENTRY}")
  elif [[ -n "$repo_name" ]] && entry_path="$(find_keepass_entry_by_title "$vault" "$repo_name")"; then
    tried+=("title:${repo_name}")
  elif [[ -n "$repo_name" ]] && entry_path="$(find_keepass_entry_by_tag "$vault" "$repo_name")"; then
    tried+=("tag:${repo_name}")
  fi

  if [[ -z "$entry_path" ]]; then
    echo "Error: no KeePassXC entry found in ${vault}." >&2
    echo "  Tried title '${KEEPASS_DEFAULT_ENTRY}'." >&2
    if [[ -n "$repo_name" ]]; then
      echo "  Tried title and tag/label '${repo_name}'." >&2
    else
      echo "  Could not detect repo name for alternate title/tag lookup; set GHCR_IMAGE or use a git remote." >&2
    fi
    exit 1
  fi

  echo "Using KeePassXC entry (${tried[*]}): ${entry_path}" >&2
  printf '%s' "$entry_path"
}

read_github_token_from_keepass() {
  local vault="$1"
  local repo_name="$2"
  local entry_path
  local token
  local err

  if [[ ! -f "$vault" ]]; then
    echo "Error: KEEPASSXC_VAULT is not a file: ${vault}" >&2
    exit 1
  fi

  entry_path="$(resolve_keepass_entry "$vault" "$repo_name")"
  keepassxc_db_args

  err="$(mktemp)"
  token="$(
    keepassxc_cli show -a Password "${KEEPASSXC_DB_ARGS[@]}" "$vault" "$entry_path" 2>"$err" \
      | head -n 1 \
      || true
  )"
  if [[ -z "$token" ]]; then
    echo "Error: could not read password from KeePassXC entry '${entry_path}'." >&2
    if [[ -s "$err" ]]; then
      sed 's/^/  /' "$err" >&2
    fi
    rm -f "$err"
    exit 1
  fi
  rm -f "$err"
  printf '%s' "$token"
}

read_github_token() {
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    printf '%s' "$GITHUB_TOKEN"
    return
  fi
  if [[ -n "${GHCR_TOKEN:-}" ]]; then
    printf '%s' "$GHCR_TOKEN"
    return
  fi
  if [[ -n "${KEEPASSXC_VAULT:-}" ]]; then
    read_github_token_from_keepass "$KEEPASSXC_VAULT" "$(detect_repo_name "${origin:-}")"
    return
  fi
  echo "Error: set GITHUB_TOKEN (or GHCR_TOKEN), or KEEPASSXC_VAULT." >&2
  exit 1
}

origin="$(git remote get-url origin 2>/dev/null || true)"

if [[ -z "${GHCR_IMAGE:-}" ]]; then
  if [[ "$origin" =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
    owner="${BASH_REMATCH[1]}"
    repo="${BASH_REMATCH[2]}"
    GHCR_IMAGE="ghcr.io/$(echo "$owner" | tr '[:upper:]' '[:lower:]')/$(echo "$repo" | tr '[:upper:]' '[:lower:]')"
  fi
fi

token="$(read_github_token)"

if [[ -z "${GHCR_IMAGE:-}" ]]; then
  echo "Error: could not detect repo from git remote; set GHCR_IMAGE." >&2
  exit 1
fi

TAG="${IMAGE_TAG:-latest}"
actor="${GITHUB_ACTOR:-$(git config user.github 2>/dev/null || true)}"
if [[ -z "$actor" && "${origin:-}" =~ github\.com[:/]([^/]+)/ ]]; then
  actor="${BASH_REMATCH[1]}"
fi
if [[ -z "$actor" ]]; then
  echo "Error: set GITHUB_ACTOR to your GitHub username." >&2
  exit 1
fi

full_image="${GHCR_IMAGE}:${TAG}"

echo "Logging in to ghcr.io as ${actor}..."
echo "$token" | docker login ghcr.io -u "$actor" --password-stdin

echo "Building ${full_image}..."
docker build -t "$full_image" .

echo "Pushing ${full_image}..."
docker push "$full_image"

echo "Done: ${full_image}"

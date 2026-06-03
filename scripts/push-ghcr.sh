#!/usr/bin/env bash
# Build the app image and push it to GitHub Container Registry (ghcr.io).
#
# Usage:
#   export GITHUB_TOKEN=ghp_...   # PAT with write:packages (or GHCR_TOKEN)
#   ./scripts/push-ghcr.sh
#
# Or read the token from KeePassXC:
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

KEEPASS_ENTRY_NAME="GITHUB_TOKEN_PUSH_REGISTRY"

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

resolve_keepass_entry() {
  local vault="$1"
  local matches
  local count

  keepassxc_db_args
  matches="$(
    keepassxc_cli ls -R -f "${KEEPASSXC_DB_ARGS[@]}" "$vault" 2>/dev/null \
      | grep -E "(^|/)${KEEPASS_ENTRY_NAME}$" \
      || true
  )"
  count="$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')"

  if [[ "$count" -eq 0 ]]; then
    echo "Error: KeePassXC entry '${KEEPASS_ENTRY_NAME}' not found in ${vault}." >&2
    exit 1
  fi
  if [[ "$count" -gt 1 ]]; then
    echo "Error: multiple KeePassXC entries named '${KEEPASS_ENTRY_NAME}'; use a unique title." >&2
    printf '%s\n' "$matches" >&2
    exit 1
  fi
  printf '%s\n' "$matches" | sed '/^$/d' | head -n 1
}

read_github_token_from_keepass() {
  local vault="$1"
  local entry_path
  local token
  local err

  if [[ ! -f "$vault" ]]; then
    echo "Error: KEEPASSXC_VAULT is not a file: ${vault}" >&2
    exit 1
  fi

  entry_path="$(resolve_keepass_entry "$vault")"
  keepassxc_db_args

  err="$(mktemp)"
  token="$(
    keepassxc_cli show -a Password "${KEEPASSXC_DB_ARGS[@]}" "$vault" "$entry_path" 2>"$err" \
      | head -n 1 \
      || true
  )"
  if [[ -z "$token" ]]; then
    echo "Error: could not read '${KEEPASS_ENTRY_NAME}' from KeePassXC vault." >&2
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
    read_github_token_from_keepass "$KEEPASSXC_VAULT"
    return
  fi
  echo "Error: set GITHUB_TOKEN (or GHCR_TOKEN), or KEEPASSXC_VAULT with entry ${KEEPASS_ENTRY_NAME}." >&2
  exit 1
}

token="$(read_github_token)"

if [[ -z "${GHCR_IMAGE:-}" ]]; then
  origin="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$origin" =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
    owner="${BASH_REMATCH[1]}"
    repo="${BASH_REMATCH[2]}"
    GHCR_IMAGE="ghcr.io/$(echo "$owner" | tr '[:upper:]' '[:lower:]')/$(echo "$repo" | tr '[:upper:]' '[:lower:]')"
  else
    echo "Error: could not detect repo from git remote; set GHCR_IMAGE." >&2
    exit 1
  fi
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

#!/usr/bin/env bash
# Build the app image and push it to GitHub Container Registry (ghcr.io).
#
# Usage:
#   export GITHUB_TOKEN=ghp_...   # PAT with write:packages (or GHCR_TOKEN)
#   ./scripts/push-ghcr.sh
#
# Optional:
#   GITHUB_ACTOR=your-github-username
#   IMAGE_TAG=latest
#   GHCR_IMAGE=ghcr.io/owner/repo   # override auto-detected image name

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

token="${GITHUB_TOKEN:-${GHCR_TOKEN:-}}"
if [[ -z "$token" ]]; then
  echo "Error: set GITHUB_TOKEN or GHCR_TOKEN (needs write:packages)." >&2
  exit 1
fi

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

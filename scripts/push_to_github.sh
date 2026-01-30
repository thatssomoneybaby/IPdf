#!/usr/bin/env bash
set -euo pipefail

REMOTE_URL=${1:-}
if [[ -z "${REMOTE_URL}" ]]; then
  echo "Usage: scripts/push_to_github.sh <git_remote_url>" >&2
  echo "Example: scripts/push_to_github.sh git@github.com:your-org/ipdf.git" >&2
  exit 1
fi

# Initialize repo if needed
if [[ ! -d .git ]]; then
  git init
fi

# Create main branch if not present
current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [[ "${current_branch}" == "HEAD" || -z "${current_branch}" ]]; then
  git checkout -b main
fi

# Basic hygiene
git add .
git commit -m "Initial commit: IPdf M1 stack (API+UI+Compose)" || true

# Set remote and push
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "${REMOTE_URL}"
else
  git remote add origin "${REMOTE_URL}"
fi

git push -u origin main

echo "Pushed to ${REMOTE_URL}" 

#!/usr/bin/env bash
# 新知 news site: test+build -> commit source on main -> sync public/ to gh-pages -> push -> verify live. Non-interactive.
# Usage: bash publish.sh [--build-only]
# Exit codes: 1 build/test failed | 0 success (or nothing changed and live is healthy) | 3 no GitHub auth / push failed | 4 live verification failed
set -uo pipefail
cd "$(dirname "$0")"
export GIT_TERMINAL_PROMPT=0 GH_PROMPT_DISABLED=1
OWNER=nofeetbird0321; REPO=news; DOMAIN=news.nofeetbird.tech; BRANCH=gh-pages
PAGES_DIR="$(cd .. && pwd)/mynews_pages"
GIT_ID=(-c user.name=$OWNER -c user.email=$OWNER@users.noreply.github.com)
CRED=(-c credential.helper= -c "credential.helper=!gh auth git-credential")

# 1. Environment (idempotent)
[[ -x .venv/bin/python ]] || { python3 -m venv .venv && .venv/bin/pip -q install -r requirements.txt; } || { echo "venv setup failed" >&2; exit 1; }
[[ -d node_modules/jsdom ]] || npm ci --no-audit --no-fund --loglevel=error || { echo "npm ci failed" >&2; exit 1; }
export PATH="$PWD/.venv/bin:$PATH"

# 2. Build + all tests (python unittest + jsdom reader tests). Never publish on failure.
npm test --silent >/tmp/mynews-test.log 2>&1 || { tail -40 /tmp/mynews-test.log >&2; echo "TESTS FAILED (full log /tmp/mynews-test.log)" >&2; exit 1; }
echo "tests ok: $(grep -E '^Ran [0-9]+ tests' /tmp/mynews-test.log) / reader $(grep -E '^ℹ pass' /tmp/mynews-test.log)"
[[ "${1:-}" == "--build-only" ]] && exit 0

# 3. Commit + push source (content/, scripts/, public/ ...) to main
gh auth status >/dev/null 2>&1 || { echo "SKIP DEPLOY: gh not logged in; built only" >&2; exit 3; }
git add -A
if ! git diff --cached --quiet; then
  git "${GIT_ID[@]}" commit -qm "publish $(TZ=Asia/Shanghai date '+%F %R')" || exit 3
fi
git "${CRED[@]}" push -q origin main </dev/null || { echo "PUSH main FAILED" >&2; exit 3; }

# 4. Sync public/ to the gh-pages branch (served by GitHub Pages, custom domain via public/CNAME)
if [[ ! -d "$PAGES_DIR/.git" ]]; then
  git "${CRED[@]}" clone -q --branch "$BRANCH" "https://github.com/$OWNER/$REPO.git" "$PAGES_DIR" 2>/dev/null || {
    rm -rf "$PAGES_DIR"; mkdir -p "$PAGES_DIR" && git -C "$PAGES_DIR" init -q -b "$BRANCH" && git -C "$PAGES_DIR" remote add origin "https://github.com/$OWNER/$REPO.git"; }
fi
( cd "$PAGES_DIR" && git "${CRED[@]}" pull -q --ff-only origin "$BRANCH" </dev/null 2>/dev/null || true
  find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  cp -a "$OLDPWD/public/." .
  git add -A
  if git diff --cached --quiet; then echo "gh-pages: no changes"; else
    git "${GIT_ID[@]}" commit -qm "site $(TZ=Asia/Shanghai date '+%F %R')" &&
    git "${CRED[@]}" push -q origin "$BRANCH" </dev/null || { echo "PUSH $BRANCH FAILED" >&2; exit 3; }
    echo "gh-pages: pushed"
  fi ) || exit 3

# 5. Verify live: homepage lists the newest article and feed.xml has its GUID (up to ~4 min for Pages build)
want=$(python3 -c "import json;print(json.load(open('public/articles.json',encoding='utf-8'))[0]['id'])")
GH_IP=185.199.108.153   # box DNS may return proxy fake IPs; also check directly against GitHub Pages
fetch(){ curl -sfL --max-time 20 -H 'Cache-Control: no-cache' "$@"; }
for i in $(seq 1 24); do
  for extra in "" "--resolve $DOMAIN:443:$GH_IP"; do
    page=$(fetch $extra "https://$DOMAIN/?t=$(date +%s)") || continue
    feed=$(fetch $extra "https://$DOMAIN/feed.xml?t=$(date +%s)") || continue
    if grep -q "/a/$want" <<<"$page" && grep -qF "https://$DOMAIN/a/$want</guid>" <<<"$feed"; then
      echo "OK https://$DOMAIN/ ${extra:+(via $GH_IP)} newest=$want"; exit 0; fi
  done
  sleep 10
done
echo "VERIFY FAILED: https://$DOMAIN/ does not show $want yet" >&2; exit 4

#!/usr/bin/env bash
# Run the tracker, save data/ to the repo, and (if LOOP=true) repeat every INTERVAL
# seconds until BUDGET seconds have passed. GitHub only starts scheduled runs every
# few hours, so one run keeps the leaderboard fresh until the next one takes over.
#
# Env: LOOP (true/false), INTERVAL (s, default 900), BUDGET (s, default 20700 = 5h45m),
#      FULL ("--full" for a full zKill re-scan on the first round), TRACKER (command).
set -u
INTERVAL=${INTERVAL:-900}
BUDGET=${BUDGET:-20700}
TRACKER=${TRACKER:-python tracker.py}
FULL=${FULL:-}
start=$(date +%s)
round=1

while true; do
  # Start every round from the latest repo state: picks up config.json edits and
  # data pushed by any other run. Uncommitted data from a failed push is dropped;
  # the tracker regenerates it.
  git fetch -q origin main && git reset -q --hard origin/main

  echo "--- round $round ($(date -u +%H:%M) UTC)"
  $TRACKER $FULL || echo "update failed; retrying next round"
  FULL=""

  if [ -n "$(git status --porcelain data)" ]; then
    git add data
    git commit -q -m "Update killmark data"
    git push -q origin HEAD:main || echo "push failed (another run pushed first); retrying next round"
  fi

  [ "${LOOP:-false}" = "true" ] || break
  [ $(( $(date +%s) - start + INTERVAL + 300 )) -lt "$BUDGET" ] || break
  sleep "$INTERVAL"
  round=$((round + 1))
done

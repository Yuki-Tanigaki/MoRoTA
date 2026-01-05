#!/usr/bin/env bash
set -euo pipefail

SCENARIO_DIR="configs/20251229-1"
SEED="0000"

scenarios=("${SCENARIO_DIR}"/*.yml)
TOTAL=${#scenarios[@]}
COUNT=0

START_TIME=$(date +%s)

for scenario in "${scenarios[@]}"; do
  COUNT=$((COUNT + 1))
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TIME))

  AVG_SEC=$((ELAPSED / COUNT))
  REMAIN_SEC=$(((TOTAL - COUNT) * AVG_SEC))

  AVG_MIN=$(awk "BEGIN { printf \"%.2f\", ${AVG_SEC}/60 }")
  ETA_MIN=$(awk "BEGIN { printf \"%.1f\", ${REMAIN_SEC}/60 }")

  PCT=$((COUNT * 100 / TOTAL))

  echo "================================================"
  echo "[${COUNT}/${TOTAL}] (${PCT}%) Running scenario:"
  echo "  ${scenario}"
  echo "  Avg / exp : ${AVG_MIN} min"
  echo "  ETA       : ${ETA_MIN} min remaining"
  echo "================================================"

  uv run python scripts/run.py \
    --scenario "${scenario}" \
    --seed "${SEED}" \
    --log-file
done

echo "All scenarios finished."

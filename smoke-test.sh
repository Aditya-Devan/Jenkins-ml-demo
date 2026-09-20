#!/usr/bin/env bash
# Smoke test: run the serving container, wait for /health, then assert
# two real predictions: (2,2) -> 1 and (-2,-2) -> 0.
#
# Requests are made from INSIDE the container (docker exec + python's
# urllib) so this works identically on a laptop and inside Jenkins,
# where the docker socket points at the host engine and published
# ports would not be reachable via localhost.
set -euo pipefail

IMAGE="${1:?usage: smoke-test.sh <image>}"
NAME="inference-smoke-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" "$IMAGE" >/dev/null

req() {
  docker exec "$NAME" python -c \
    "import urllib.request; print(urllib.request.urlopen('http://localhost:8000$1', timeout=5).read().decode())"
}

echo "waiting for service to become healthy..."
healthy=0
for i in $(seq 1 30); do
  if req /health >/dev/null 2>&1; then healthy=1; break; fi
  sleep 1
done
if [ "$healthy" -ne 1 ]; then
  echo "ERROR: service never became healthy"
  docker logs "$NAME"
  exit 1
fi

check() {
  local x1=$1 x2=$2 expected=$3
  local body
  body=$(req "/predict?x1=${x1}&x2=${x2}")
  echo "predict(${x1},${x2}) -> ${body}"
  if ! echo "$body" | grep -q "\"prediction\":${expected}"; then
    echo "ERROR: expected prediction ${expected} for (${x1},${x2})"
    exit 1
  fi
}

check 2 2 1
check -2 -2 0

echo "SMOKE TEST PASSED"
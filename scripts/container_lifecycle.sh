#!/usr/bin/env bash
# Container lifecycle: find containers whose health check is failing, restart them, and wait until
# they're healthy again. Then clear out stopped containers and dangling images.
set -euo pipefail
cd "$(dirname "$0")/.."

# Give a failing health check time to register
sleep 8

healed=0
for c in $(docker compose ps -q); do
  name=$(docker inspect -f '{{.Name}}' "$c" | sed 's#^/##')
  health=$(docker inspect -f '{{.State.Health.Status}}' "$c")
  if [ "$health" = "unhealthy" ]; then
    echo "UNHEALTHY  $name: restarting"
    docker restart "$c" >/dev/null
    for _ in $(seq 1 30); do
      [ "$(docker inspect -f '{{.State.Health.Status}}' "$c")" = "healthy" ] && break
      sleep 1
    done
    health=$(docker inspect -f '{{.State.Health.Status}}' "$c")
    [ "$health" = "healthy" ] || { echo "FAILED     $name is still $health"; exit 1; }
    echo "HEALED     $name is healthy again"
    healed=$((healed + 1))
  else
    echo "OK         $name is $health"
  fi
done

docker container prune -f >/dev/null
docker image prune -f >/dev/null
echo "Restarted and healed $healed container(s); stopped containers and dangling images pruned"
mkdir -p report && echo "{\"healed\": $healed}" > report/lifecycle.json

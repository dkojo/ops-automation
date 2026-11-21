#!/usr/bin/env bash
# Builds the test fleet with the kind of problems that pile up on real servers:
#   web2: its app gets stuck (health check starts failing)
#   web3: its TLS certificate expires in 3 days, and someone hand-edited its config (old TLS, version banner, no HSTS)
# Then sends some traffic so there are logs to parse.
set -euo pipefail
cd "$(dirname "$0")/.."

RUN=fleet/run
rm -rf "$RUN" && mkdir -p "$RUN/ca"

# A private certificate authority for the fleet
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=Fleet CA" \
  -keyout "$RUN/ca/ca.key" -out "$RUN/ca/ca.crt" 2>/dev/null

issue() { # issue <server> <days>
  local dir="$RUN/$1/tls"
  mkdir -p "$dir"
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$1" -keyout "$dir/server.key" -out "$dir/server.csr" 2>/dev/null
  openssl x509 -req -in "$dir/server.csr" -CA "$RUN/ca/ca.crt" -CAkey "$RUN/ca/ca.key" -CAcreateserial \
    -days "$2" -extfile <(printf "subjectAltName=DNS:%s,DNS:localhost" "$1") -out "$dir/server.crt" 2>/dev/null
  rm -f "$dir/server.csr"
  chmod 644 "$dir/server.key"   # nginx workers read it inside the container
}

for s in web1 web2 web3; do
  mkdir -p "$RUN/$s/conf.d"
  sed "s/SERVER_NAME/$s/g" fleet/baseline.conf.template > "$RUN/$s/conf.d/default.conf"
done
issue web1 90
issue web2 90
issue web3 3     # about to expire

# Drift on web3: someone "fixed" an old client by hand
sed -i -e 's/ssl_protocols       TLSv1.2 TLSv1.3;/ssl_protocols       TLSv1 TLSv1.1 TLSv1.2 TLSv1.3;/' \
       -e 's/server_tokens       off;/server_tokens       on;/' \
       -e '/Strict-Transport-Security/d' "$RUN/web3/conf.d/default.conf"

docker compose up -d --wait

# web2's app gets stuck
docker compose exec -T web2 touch /usr/share/nginx/html/down

# Some traffic: mostly fine, a few missing pages and server errors
for port in 8441 8442 8443; do
  for _ in $(seq 1 40); do curl -sk -o /dev/null "https://localhost:$port/"; done
  for _ in $(seq 1 4); do curl -sk -o /dev/null "https://localhost:$port/missing-page"; done
  curl -sk -o /dev/null "https://localhost:$port/error"
done
echo "Fleet up: web1 healthy, web2 stuck, web3 with an expiring certificate and a drifted config"

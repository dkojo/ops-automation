#!/usr/bin/env bash
# SSL certificate rotation: read the certificate each server is actually serving, and if it expires within
# RENEW_DAYS, issue a new one from the fleet CA, install it, reload nginx (no downtime), and check the new one is live.
set -euo pipefail
cd "$(dirname "$0")/.."

RENEW_DAYS=${RENEW_DAYS:-30}
RUN=fleet/run

served_end() { # served_end <port>: the expiry date of the certificate served on that port
  echo | openssl s_client -connect "localhost:$1" -servername localhost 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2
}
days_left() { echo $(( ($(date -d "$1" +%s) - $(date +%s)) / 86400 )); }

rotated=0
for entry in web1:8441 web2:8442 web3:8443; do
  name=${entry%%:*}; port=${entry##*:}
  end=$(served_end "$port"); left=$(days_left "$end")
  if [ "$left" -ge "$RENEW_DAYS" ]; then
    echo "OK       $name expires in $left days"
    continue
  fi
  echo "RENEW    $name expires in $left days (under $RENEW_DAYS): issuing a new 90-day certificate"
  dir="$RUN/$name/tls"
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$name" -keyout "$dir/server.key.new" -out "$dir/server.csr" 2>/dev/null
  openssl x509 -req -in "$dir/server.csr" -CA "$RUN/ca/ca.crt" -CAkey "$RUN/ca/ca.key" -CAcreateserial -days 90 \
    -extfile <(printf "subjectAltName=DNS:%s,DNS:localhost" "$name") -out "$dir/server.crt.new" 2>/dev/null
  mv "$dir/server.key.new" "$dir/server.key" && mv "$dir/server.crt.new" "$dir/server.crt" && rm -f "$dir/server.csr"
  chmod 644 "$dir/server.key"
  docker compose exec -T "$name" nginx -s reload
  sleep 1
  new_left=$(days_left "$(served_end "$port")")
  [ "$new_left" -ge 89 ] || { echo "FAILED   $name is still serving a certificate with $new_left days left"; exit 1; }
  echo "ROTATED  $name now serves a certificate valid for $new_left days"
  rotated=$((rotated + 1))
done
echo "$rotated certificate(s) rotated"
mkdir -p report && echo "{\"rotated\": $rotated}" > report/certs.json

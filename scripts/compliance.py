"""Compliance validation: check every server against the security baseline, fix any drift by re-applying
the approved config, then check again. Fails if anything is still non-compliant after the fix.

  python3 scripts/compliance.py
Writes report/compliance.json.
"""
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

FLEET = {"web1": 8441, "web2": 8442, "web3": 8443}
RUN = "fleet/run"
ALLOWED_PROTOCOLS = {"TLSv1.2", "TLSv1.3"}
MIN_CERT_DAYS = 30


def evaluate(conf, headers, cert_days):
    """The policy. Pure function of what was observed, so it's easy to test. Returns [(check, ok, detail)]."""
    m = re.search(r"ssl_protocols\s+([^;]+);", conf)
    protocols = set(m.group(1).split()) if m else set()
    server = headers.get("Server", "")
    return [
        ("Only TLS 1.2 and 1.3", protocols == ALLOWED_PROTOCOLS, " ".join(sorted(protocols)) or "not set"),
        ("No version in Server header", server == "nginx", server or "missing"),
        ("HSTS header present", "Strict-Transport-Security" in headers, headers.get("Strict-Transport-Security", "missing")),
        (f"Certificate valid {MIN_CERT_DAYS}+ days", cert_days >= MIN_CERT_DAYS, f"{cert_days} days left"),
    ]


def observe(name, port):
    with open(f"{RUN}/{name}/conf.d/default.conf", encoding="utf-8") as f:
        conf = f.read()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(f"https://localhost:{port}/", context=ctx, timeout=5) as r:
        headers = dict(r.headers)
    pem = ssl.get_server_certificate(("localhost", port))
    end = subprocess.run(["openssl", "x509", "-noout", "-enddate"], input=pem, capture_output=True, text=True, check=True).stdout
    expiry = datetime.strptime(end.strip().split("=", 1)[1], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    return conf, headers, (expiry - datetime.now(timezone.utc)).days


def remediate(name):
    """Re-apply the approved baseline to one server and reload nginx without downtime."""
    with open("fleet/baseline.conf.template", encoding="utf-8") as f:
        conf = f.read().replace("SERVER_NAME", name)
    with open(f"{RUN}/{name}/conf.d/default.conf", "w", encoding="utf-8") as f:
        f.write(conf)
    subprocess.run(["docker", "compose", "exec", "-T", name, "nginx", "-t", "-q"], check=True)
    subprocess.run(["docker", "compose", "exec", "-T", name, "nginx", "-s", "reload"], check=True)


def check_fleet():
    return {name: evaluate(*observe(name, port)) for name, port in FLEET.items()}


def show(results):
    for name, checks in results.items():
        for check, ok, detail in checks:
            print(f"{'PASS' if ok else 'FAIL'}  {name:5} {check:30} {detail}")


def main():
    print("== Before")
    before = check_fleet()
    show(before)
    drifted = [n for n, checks in before.items() if not all(ok for _, ok, _ in checks)]
    for name in drifted:
        print(f"REMEDIATE  {name}: re-applying the baseline config")
        remediate(name)
    if drifted:
        time.sleep(1)
    print("== After")
    after = check_fleet()
    show(after)

    violations = sum(1 for checks in after.values() for _, ok, _ in checks if not ok)
    found = sum(1 for checks in before.values() for _, ok, _ in checks if not ok)
    print(f"{found} violation(s) found on {len(drifted)} server(s), {found - violations} fixed, {violations} remaining")
    os.makedirs("report", exist_ok=True)
    with open("report/compliance.json", "w", encoding="utf-8") as f:
        json.dump({"found": found, "drifted": drifted, "remaining": violations,
                   "checks": {n: [[c, ok, d] for c, ok, d in checks] for n, checks in after.items()}}, f, indent=2)
    return 0 if violations == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

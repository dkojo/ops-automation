"""Log parsing: read the fleet's JSON access logs and summarise them per server.

  python3 scripts/parse_logs.py            (reads `docker compose logs`)
  python3 scripts/parse_logs.py file.log   (reads a saved log)
Writes report/logs.json. Fails if nothing could be parsed, because that means logging itself is broken.
"""
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict


def summarise(lines):
    """Turn raw log lines into a per-server summary. Lines that aren't JSON (nginx start-up notices) are skipped."""
    servers = defaultdict(lambda: {"requests": 0, "2xx": 0, "4xx": 0, "5xx": 0, "paths": Counter()})
    for line in lines:
        start = line.find("{")
        if start < 0:
            continue
        try:
            entry = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        s = servers[entry["server"]]
        s["requests"] += 1
        s[f"{str(entry['status'])[0]}xx"] = s.get(f"{str(entry['status'])[0]}xx", 0) + 1
        if entry["status"] >= 400:
            s["paths"][f"{entry['status']} {entry['path']}"] += 1
    summary = {}
    for name, s in sorted(servers.items()):
        summary[name] = {
            "requests": s["requests"],
            "2xx": s["2xx"], "4xx": s["4xx"], "5xx": s["5xx"],
            "error_rate_pct": round((s["4xx"] + s["5xx"]) / s["requests"] * 100, 1),
            "top_errors": [f"{path} x{n}" for path, n in s["paths"].most_common(3)],
        }
    return summary


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            lines = f.read().splitlines()
    else:
        out = subprocess.run(["docker", "compose", "logs", "--no-color", "--no-log-prefix"], capture_output=True, text=True, check=True)
        lines = out.stdout.splitlines()

    summary = summarise(lines)
    if not summary:
        print("FAIL  no access log lines could be parsed")
        return 1
    for name, s in summary.items():
        print(f"{name}: {s['requests']} requests · 2xx {s['2xx']} · 4xx {s['4xx']} · 5xx {s['5xx']} · "
              f"errors {s['error_rate_pct']}% · top: {', '.join(s['top_errors']) or 'none'}")
    os.makedirs("report", exist_ok=True)
    with open("report/logs.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())

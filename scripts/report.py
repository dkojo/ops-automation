"""Ops report: one summary of what today's run found and fixed, printed and added to the GitHub job summary."""
import json
import os


def load(name):
    with open(f"report/{name}.json", encoding="utf-8") as f:
        return json.load(f)


life, certs, logs, comp = load("lifecycle"), load("certs"), load("logs"), load("compliance")
requests = sum(s["requests"] for s in logs.values())
errors = sum(s["4xx"] + s["5xx"] for s in logs.values())
rows = [
    ("Containers healed", life["healed"]),
    ("Certificates rotated", certs["rotated"]),
    ("Requests parsed", f"{requests} ({errors} errors)"),
    ("Compliance violations fixed", f"{comp['found'] - comp['remaining']} of {comp['found']}"),
    ("Remaining drift", comp["remaining"]),
]
text = "\n".join(f"{k:30} {v}" for k, v in rows)
print(text)
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a", encoding="utf-8") as f:
        f.write("### Ops report\n\n| | |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in rows))

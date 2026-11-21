import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import compliance  # noqa: E402
import parse_logs  # noqa: E402

BASELINE = (Path(__file__).resolve().parent.parent / "fleet" / "baseline.conf.template").read_text()
GOOD_HEADERS = {"Server": "nginx", "Strict-Transport-Security": "max-age=31536000"}


class ParseLogsTests(unittest.TestCase):
    def test_counts_requests_and_errors_per_server(self):
        lines = [
            '2026/11/21 [notice] start worker process',
            '{"time":"t","server":"web1","status":200,"path":"/","bytes":1,"rt":0.001}',
            '{"time":"t","server":"web1","status":404,"path":"/missing","bytes":1,"rt":0.001}',
            '{"time":"t","server":"web1","status":500,"path":"/error","bytes":1,"rt":0.001}',
        ]
        s = parse_logs.summarise(lines)["web1"]
        self.assertEqual((s["requests"], s["2xx"], s["4xx"], s["5xx"]), (3, 1, 1, 1))
        self.assertEqual(s["error_rate_pct"], 66.7)

    def test_nothing_to_parse_gives_empty_summary(self):
        self.assertEqual(parse_logs.summarise(["not json"]), {})


class ComplianceTests(unittest.TestCase):
    def test_the_baseline_itself_is_compliant(self):
        self.assertTrue(all(ok for _, ok, _ in compliance.evaluate(BASELINE, GOOD_HEADERS, 90)))

    def test_old_tls_versions_fail(self):
        conf = BASELINE.replace("TLSv1.2 TLSv1.3", "TLSv1 TLSv1.1 TLSv1.2 TLSv1.3")
        self.assertFalse(compliance.evaluate(conf, GOOD_HEADERS, 90)[0][1])

    def test_version_banner_missing_hsts_and_expiring_cert_fail(self):
        results = compliance.evaluate(BASELINE, {"Server": "nginx/1.30.7"}, 3)
        self.assertEqual([ok for _, ok, _ in results], [True, False, False, False])


if __name__ == "__main__":
    unittest.main()

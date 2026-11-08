"""Portfolio standard checks: the lock holds, required files exist, no public score."""
import glob
import hashlib
import os
import pathlib
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# PREREG.md as committed in 0e0c035 (tag proposal-v1), before any code or data:
# 12,618 bytes with this SHA-256. Its own text says deviations are appended at
# the bottom, so the locked bytes must stay an unchanged prefix of the file.
LOCKED_BYTES = 12618
LOCKED_SHA256 = "eb429981e28c4ad3b9358c848f6c7561b3154512ec62392a0727b5256ccbe023"
REQUIRED = ["README.md", "PREREG.md", "REPORT.md", "METHODS.md", "RESULTS.md", "DECISIONS.md",
            "CHANGELOG.md", "CITATION.cff", "SECURITY.md", "LICENSE", "results/verdicts.json"]
SCORE = re.compile(r"of 10,000|/ ?10,?000|Grade:|Final grade|rubric score", re.I)


class Layout(unittest.TestCase):
    def test_locked_preregistration_bytes_unchanged(self):
        with open(os.path.join(ROOT, "PREREG.md"), "rb") as f:
            head = f.read()[:LOCKED_BYTES]
        self.assertEqual(hashlib.sha256(head).hexdigest(), LOCKED_SHA256,
                         "PREREG.md changed inside its locked text; append a deviation instead")

    def test_required_files_exist(self):
        missing = [p for p in REQUIRED if not os.path.exists(os.path.join(ROOT, p))]
        self.assertEqual(missing, [])

    def test_no_public_score(self):
        public = glob.glob(os.path.join(ROOT, "*.md")) + glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True) \
            + glob.glob(os.path.join(ROOT, "site", "src", "*"))
        hits = [os.path.relpath(p, ROOT) for p in public if SCORE.search(pathlib.Path(p).read_text(encoding="utf-8"))]
        self.assertEqual(hits, [], "grades are internal")


if __name__ == "__main__":
    unittest.main()

"""Every file the Dockerfile COPYs from the build context must survive .dockerignore.

Regression: house.py was added to the Dockerfile but the allow-list .dockerignore
still excluded it, so the image build failed on a clean worker.
"""
import fnmatch
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


def included(path, rules):
    keep = True
    for rule in rules:
        neg = rule.startswith("!")
        pat = rule[1:] if neg else rule
        pat = pat.rstrip("/")
        hit = fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, pat + "/**") or path.split("/")[0] == pat
        if pat == "*":
            hit = True
        if hit:
            keep = neg
    return keep


class DockerContextTest(unittest.TestCase):
    def test_every_copied_file_is_in_build_context(self):
        rules = [l.strip() for l in (ROOT / ".dockerignore").read_text().splitlines() if l.strip() and not l.startswith("#")]
        missing = []
        for line in (ROOT / "Dockerfile").read_text().splitlines():
            parts = line.split()
            if not parts or parts[0] != "COPY" or any(p.startswith("--from") for p in parts):
                continue
            for src in [p for p in parts[1:-1] if not p.startswith("--")]:
                src = src.rstrip("/")
                if not (ROOT / src).exists():
                    missing.append(src + " (absent)")
                elif not included(src, rules):
                    missing.append(src + " (excluded by .dockerignore)")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()

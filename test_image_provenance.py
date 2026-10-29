"""Exercise the image builder with a fake Docker CLI; never starts containers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

class ImageProvenanceTests(unittest.TestCase):
    def exercise(self, skip=False):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            log = folder / 'calls.jsonl'
            docker = folder / 'docker'
            docker.write_text('#!' + sys.executable + '\nimport os,sys,json\nwith open(os.environ["PROVENANCE_TEST_LOG"], "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
            docker.chmod(0o755)
            env = {**os.environ, 'PATH': str(folder) + os.pathsep + os.environ['PATH'], 'PROVENANCE_TEST_LOG': str(log)}
            if skip:
                env['VIDEO_SKIP_BUILD'] = '1'
                git = folder / 'git'
                git.write_text('#!/bin/sh\nexit 99\n')
                git.chmod(0o755)
            else:
                env.pop('VIDEO_SKIP_BUILD', None)
            subprocess.run(['sh', str(ROOT / 'test-container.sh')], env=env, check=True)
            return [json.loads(line) for line in log.read_text().splitlines()]

    def test_build_records_exact_checkout_commit(self):
        calls = self.exercise()
        build = next(c for c in calls if c[0] == 'build')
        rev = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        self.assertIn('org.opencontainers.image.source=https://github.com/humanitylabs-org/defleur-video', build)
        self.assertIn('org.opencontainers.image.revision=' + rev, build)
        self.assertEqual([c[0] for c in calls], ['build', 'run'])

    def test_skip_build_needs_neither_git_nor_a_rebuild(self):
        self.assertEqual([c[0] for c in self.exercise(skip=True)], ['run'])

if __name__ == '__main__':
    unittest.main()

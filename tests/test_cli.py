import os
import subprocess
import sys
import unittest


class CLITests(unittest.TestCase):
    def test_bilingual_help_survives_an_ascii_default_console(self):
        environment = dict(os.environ, PYTHONIOENCODING="ascii", PYTHONUTF8="0")
        result = subprocess.run([sys.executable, "-m", "packet_tracer_mcp", "--help"],
                                capture_output=True, env=environment, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        output = result.stdout.decode("utf-8")
        self.assertIn("Packet Tracer", output)
        self.assertIn("原生接口", output)


if __name__ == "__main__":
    unittest.main()

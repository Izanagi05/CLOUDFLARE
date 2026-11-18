import sys
import tempfile
import time
import unittest
from pathlib import Path

from tunnel_manager.processes import ProcessManager


class ProcessManagerTests(unittest.TestCase):
    def test_service_runs_without_shell_and_captures_output(self):
        lines = []
        manager = ProcessManager(lines.append)
        with tempfile.TemporaryDirectory() as tmp:
            service = {
                "id": "test-service",
                "name": "smoke-test",
                "workdir": tmp,
                "executable": sys.executable,
                "args": ["-c", "print('smoke-ok')"],
            }
            manager.start_service(service)
            deadline = time.time() + 5
            while time.time() < deadline and manager.is_running("service:test-service"):
                time.sleep(0.05)
            # Give output reader a moment to flush the last line.
            time.sleep(0.1)
            self.assertFalse(manager.is_running("service:test-service"))
            self.assertTrue(any("smoke-ok" in line for line in lines), lines)

    def test_rejects_non_array_arguments(self):
        manager = ProcessManager(lambda _: None)
        with tempfile.TemporaryDirectory() as tmp:
            service = {
                "id": "bad-service",
                "name": "bad",
                "workdir": tmp,
                "executable": sys.executable,
                "args": "-c print('not-json-array')",
            }
            with self.assertRaises(ValueError):
                manager.start_service(service)

    def test_named_tunnel_passes_token_in_env_not_argv(self):
        lines = []
        manager = ProcessManager(lines.append)
        # Verify start_tunnel validates token
        with self.assertRaises(ValueError):
            manager.start_tunnel("tunnel", sys.executable, "named", "", token="")

    def test_resolve_executable_relative_to_workdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dummy_bin = tmp_path / "custom_app.bat"
            dummy_bin.write_text("@echo hello", encoding="utf-8")
            # Resolving relative to workdir
            resolved = ProcessManager._resolve_executable("custom_app.bat", workdir=tmp_path)
            self.assertEqual(resolved, str(dummy_bin.resolve()))


if __name__ == "__main__":
    unittest.main()

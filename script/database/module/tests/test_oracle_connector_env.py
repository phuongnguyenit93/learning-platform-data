"""Regression tests for the shared Oracle env path; no live DB connection."""

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


CONNECT_FILE = Path(__file__).resolve().parents[2] / "connect-oracle-db.py"
spec = importlib.util.spec_from_file_location("oracle_connector_env_test", CONNECT_FILE)
assert spec and spec.loader
connector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connector)


class OracleConnectorEnvTests(unittest.TestCase):
    def test_default_env_uses_data_repository_not_parent_java_repository(self):
        data_root = Path(__file__).resolve().parents[4]
        self.assertEqual(connector.DEFAULT_ENV_FILE, data_root / ".env.oracle-overview")
        self.assertEqual(connector.REPO_ROOT, data_root)

    def test_load_env_preserves_process_environment_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env.oracle-overview"
            env_file.write_text(
                "ORACLE_USER=file-user\nORACLE_PASSWORD=file-password\n"
                "ORACLE_DSN=file-dsn\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {"ORACLE_USER": "process-user"}, clear=True):
                connector.load_env_file(env_file, required=True)
                config = connector.config_from_env()
                self.assertEqual(config["user"], "process-user")
                self.assertEqual(config["password"], "file-password")
                self.assertEqual(config["dsn"], "file-dsn")

    def test_missing_explicit_env_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(connector.OracleConnectionError):
                connector.load_env_file(Path(directory) / "not-found.env", required=True)


if __name__ == "__main__":
    unittest.main()

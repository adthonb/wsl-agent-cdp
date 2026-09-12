import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.profile_hardening import harden, pending


class ProfileHardeningTest(unittest.TestCase):
    def test_absent_profile_has_no_pending_scrub(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual([], pending(Path(temporary) / "brave"))

    def test_scrubs_password_stores_and_preserves_sessions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            default = root / "Default"
            network = default / "Network"
            network.mkdir(parents=True)
            cookies = network / "Cookies"
            cookies.write_bytes(b"session database")
            (default / "Preferences").write_text(json.dumps({
                "profile": {"name": "Agent"},
                "signin": {"other": True},
            }), encoding="utf-8")
            for name in ("Login Data", "Login Data-wal", "Login Data For Account"):
                (default / name).write_bytes(b"saved password")

            self.assertTrue(pending(root))
            harden(root)
            self.assertEqual([], pending(root))
            self.assertEqual(b"session database", cookies.read_bytes())
            self.assertEqual("Agent", json.loads((default / "Preferences").read_text())["profile"]["name"])
            self.assertFalse((default / "Login Data").exists())
            self.assertFalse((default / "Login Data-wal").exists())
            self.assertFalse((default / "Login Data For Account").exists())

    def test_hardens_additional_browser_profiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            other = root / "Profile 1"
            other.mkdir()
            (other / "Preferences").write_text("{}", encoding="utf-8")
            (other / "Login Data").write_bytes(b"saved password")
            harden(root)
            self.assertEqual([], pending(root))
            self.assertFalse((other / "Login Data").exists())

    def test_empty_recreated_password_store_is_not_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            harden(root)
            database = root / "Default" / "Login Data"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE logins (password_value BLOB)")
            self.assertEqual([], pending(root))
            with sqlite3.connect(database) as connection:
                connection.execute("INSERT INTO logins VALUES (?)", (b"encrypted",))
            self.assertTrue(pending(root))
            harden(root)
            self.assertEqual([], pending(root))


if __name__ == "__main__":
    unittest.main()

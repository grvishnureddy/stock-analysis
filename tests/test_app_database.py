import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("app_database", ROOT / "scripts" / "app_database.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AppDatabaseTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self):
        first = MODULE.hash_password("correct horse battery staple")
        second = MODULE.hash_password("correct horse battery staple")
        self.assertNotEqual(first, second)
        self.assertTrue(MODULE.verify_password("correct horse battery staple", first))
        self.assertFalse(MODULE.verify_password("wrong", first))

    def test_database_path_is_inside_data(self):
        self.assertEqual(MODULE.DATABASE.parent, ROOT / "data")

    def test_initial_user_can_authenticate_and_change_password(self):
        original_database, original_password_file = MODULE.DATABASE, MODULE.INITIAL_PASSWORD_FILE
        with tempfile.TemporaryDirectory() as directory:
            MODULE.DATABASE = Path(directory) / "test.db"
            MODULE.INITIAL_PASSWORD_FILE = Path(directory) / "initial.txt"
            try:
                MODULE.initialize_database("admin", "initial-password-123")
                user = MODULE.authenticate("admin", "initial-password-123")
                self.assertIsNotNone(user)
                changed, _ = MODULE.change_password(user["id"], "initial-password-123", "replacement-password-456")
                self.assertTrue(changed)
                self.assertIsNotNone(MODULE.authenticate("admin", "replacement-password-456"))
            finally:
                MODULE.DATABASE, MODULE.INITIAL_PASSWORD_FILE = original_database, original_password_file


if __name__ == "__main__":
    unittest.main()

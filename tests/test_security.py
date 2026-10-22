import unittest
from types import SimpleNamespace

from bson import ObjectId

from app.security import create_token, decode_token


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(jwt_secret='x' * 32, token_seconds=60)

    def test_signed_token_round_trip(self):
        user_id = ObjectId()
        self.assertEqual(decode_token(create_token(user_id, self.settings),
                                      self.settings)['sub'], str(user_id))

    def test_rejects_changed_token(self):
        token = create_token(ObjectId(), self.settings)
        changed = ('A' if token[0] != 'A' else 'B') + token[1:]
        with self.assertRaises(ValueError):
            decode_token(changed, self.settings)

    def test_rejects_malformed_token(self):
        with self.assertRaises(ValueError):
            decode_token('not-a-token', self.settings)


if __name__ == '__main__':
    unittest.main()

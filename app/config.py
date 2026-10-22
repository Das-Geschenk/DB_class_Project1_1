import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mongo_uri: str
    database_name: str
    app_origin: str
    jwt_secret: str
    cookie_secure: bool
    token_seconds: int = 86400

    @classmethod
    def from_env(cls):
        secret = os.getenv('JWT_SECRET', '')
        if len(secret) < 32 or secret.startswith('replace-with-'):
            raise RuntimeError('请设置至少 32 个字符的随机 JWT_SECRET，详见 README.md。')
        return cls(
            mongo_uri=os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017'),
            database_name=os.getenv('MONGO_DATABASE', 'survey_project1_1'),
            app_origin=os.getenv('APP_ORIGIN', 'http://127.0.0.1:8001').rstrip('/'),
            jwt_secret=secret,
            cookie_secure=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
        )

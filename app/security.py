import base64
import binascii
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from bson import ObjectId
from fastapi import HTTPException, Request

COOKIE_NAME = 'survey_session'
password_hasher = PasswordHasher()
# Use a valid hash for unknown accounts too, so both cases perform password work.
dummy_hash = password_hasher.hash('unused-account-password')


def utcnow():
    return datetime.now(timezone.utc)


def verify_password(encoded, password):
    try:
        return password_hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id, settings):
    payload = json.dumps({'sub': str(user_id),
                          'exp': int(time.time()) + settings.token_seconds},
                         separators=(',', ':')).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b'=')
    signature = hmac.new(settings.jwt_secret.encode(), encoded,
                         hashlib.sha256).digest()
    return (encoded + b'.' + base64.urlsafe_b64encode(signature).rstrip(b'=')).decode()


def decode_token(token, settings):
    try:
        encoded, encoded_signature = token.encode().split(b'.', 1)
        signature = base64.urlsafe_b64decode(encoded_signature + b'=' * (-len(encoded_signature) % 4))
        expected = hmac.new(settings.jwt_secret.encode(), encoded, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError('Invalid signature')
        raw = base64.urlsafe_b64decode(encoded + b'=' * (-len(encoded) % 4))
        payload = json.loads(raw)
        if type(payload.get('exp')) is not int or payload['exp'] < int(time.time()):
            raise ValueError('Expired token')
        return payload
    except (ValueError, TypeError, KeyError, UnicodeDecodeError,
            binascii.Error, json.JSONDecodeError):
        raise ValueError('Invalid token') from None


def require_origin(request: Request):
    if request.headers.get('origin') != request.app.state.settings.app_origin:
        raise HTTPException(403, '请求来源不被允许')


def current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, '请先登录')
    try:
        claims = decode_token(token, request.app.state.settings)
        subject = claims['sub']
        if not isinstance(subject, str) or not ObjectId.is_valid(subject):
            raise ValueError('Invalid subject')
        user_id = ObjectId(subject)
    except (ValueError, TypeError):
        raise HTTPException(401, '登录已失效，请重新登录') from None
    user = request.app.state.db.users.find_one({'_id': user_id})
    if not user:
        raise HTTPException(401, '账号不存在，请重新登录')
    return user

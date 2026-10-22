from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError

from .security import (COOKIE_NAME, create_token, current_user, dummy_hash,
                       password_hasher, require_origin, utcnow, verify_password)

router = APIRouter(prefix='/api/auth', tags=['账号'])


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator('username')
    @classmethod
    def normalize_username(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('用户名不能为空')
        return value


def public_user(user):
    return {'id': str(user['_id']), 'username': user['username'],
            'createdAt': user['createdAt']}


@router.post('/register', status_code=201, dependencies=[Depends(require_origin)])
def register(body: Credentials, request: Request):
    user = {'username': body.username,
            'passwordHash': password_hasher.hash(body.password),
            'createdAt': utcnow()}
    try:
        result = request.app.state.db.users.insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(409, '用户名已存在') from None
    user['_id'] = result.inserted_id
    return public_user(user)


@router.post('/login', dependencies=[Depends(require_origin)])
def login(body: Credentials, request: Request, response: Response):
    user = request.app.state.db.users.find_one({'username': body.username})
    valid = verify_password(user['passwordHash'] if user else dummy_hash, body.password)
    if not user or not valid:
        raise HTTPException(401, '用户名或密码错误')
    settings = request.app.state.settings
    response.set_cookie(COOKIE_NAME, create_token(user['_id'], settings),
                        max_age=settings.token_seconds, httponly=True,
                        secure=settings.cookie_secure, samesite='lax', path='/')
    return public_user(user)


@router.post('/logout', dependencies=[Depends(require_origin)])
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path='/')
    return {'message': '已退出登录'}


@router.get('/me')
def me(user=Depends(current_user)):
    return public_user(user)

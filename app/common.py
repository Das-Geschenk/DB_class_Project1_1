from bson import ObjectId
from fastapi import HTTPException


def object_id(value, label='资源'):
    if not ObjectId.is_valid(value):
        raise HTTPException(404, f'{label}不存在')
    return ObjectId(value)


def serialize(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value

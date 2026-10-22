import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SurveyCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ''

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('标题不能为空')
        return value


class SurveyUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    anonymous: bool | None = None
    startsAt: datetime | None = None
    endsAt: datetime | None = None
    maxSubmissionsPerUser: int | None = Field(default=None, ge=1)

    @field_validator('title')
    @classmethod
    def normalize_title(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError('标题不能为空')
        return value


class Option(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=500)

    @field_validator('id', 'label')
    @classmethod
    def strip_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('选项不能为空')
        return value


class QuestionInput(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    type: Literal['single', 'multiple', 'text', 'number']
    required: bool = False
    options: list[Option] | None = None
    validation: dict[str, Any] = Field(default_factory=dict)

    @field_validator('title')
    @classmethod
    def normalize_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('题目内容不能为空')
        return value

    @model_validator(mode='after')
    def validate_configuration(self):
        allowed = {
            'single': set(), 'multiple': {'minSelections', 'maxSelections'},
            'text': {'minLength', 'maxLength'},
            'number': {'min', 'max', 'integerOnly'},
        }[self.type]
        unknown = set(self.validation) - allowed
        if unknown:
            raise ValueError('当前题型包含不支持的校验字段')
        if self.type in ('single', 'multiple'):
            if not self.options:
                raise ValueError('选择题至少需要一个选项')
            ids = [item.id for item in self.options]
            if len(ids) != len(set(ids)):
                raise ValueError('同一题的选项 ID 不能重复')
        elif self.options is not None:
            raise ValueError('填空题和数字题不能设置选项')
        v = self.validation
        if self.type == 'multiple':
            for key in allowed:
                if key in v and (type(v[key]) is not int or v[key] < 0):
                    raise ValueError('多选数量必须是非负整数')
            low, high = v.get('minSelections'), v.get('maxSelections')
            if low is not None and high is not None and low > high:
                raise ValueError('最少选择数不能大于最多选择数')
            if high is not None and high > len(self.options or []):
                raise ValueError('最多选择数不能超过选项数')
        if self.type == 'text':
            for key in allowed:
                if key in v and (type(v[key]) is not int or v[key] < 0):
                    raise ValueError('文本长度必须是非负整数')
            if v.get('minLength', 0) > v.get('maxLength', float('inf')):
                raise ValueError('最短长度不能大于最长长度')
        if self.type == 'number':
            if 'integerOnly' in v and type(v['integerOnly']) is not bool:
                raise ValueError('integerOnly 必须是布尔值')
            for key in ('min', 'max'):
                if key in v and (type(v[key]) not in (int, float) or not math.isfinite(v[key])):
                    raise ValueError('数值上下限必须是有限数值')
            if v.get('min', -math.inf) > v.get('max', math.inf):
                raise ValueError('最小值不能大于最大值')
        return self


class JumpCondition(BaseModel):
    operator: Literal['equals', 'containsAny', 'containsAll', 'eq', 'gt', 'gte', 'lt', 'lte']
    value: Any


class JumpRuleInput(BaseModel):
    sourceQuestionId: str
    condition: JumpCondition
    targetQuestionId: str | None


class RulesInput(BaseModel):
    rules: list[JumpRuleInput]


class OrderInput(BaseModel):
    questionIds: list[str]


class AnswerInput(BaseModel):
    questionId: str
    value: Any


class ResponseInput(BaseModel):
    requestId: str = Field(min_length=1, max_length=100)
    answers: list[AnswerInput]

    @model_validator(mode='after')
    def distinct_questions(self):
        ids = [item.questionId for item in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError('一份答卷不能重复提交同一道题')
        return self

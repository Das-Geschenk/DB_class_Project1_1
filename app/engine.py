import math

from fastapi import HTTPException


def validate_answer(question, value):
    kind = question['type']
    validation = question.get('validation', {})
    if kind == 'single':
        valid = {item['id'] for item in question['options']}
        if not isinstance(value, str) or value not in valid:
            raise HTTPException(422, f"题目“{question['title']}”的选项无效")
    elif kind == 'multiple':
        valid = {item['id'] for item in question['options']}
        if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
            raise HTTPException(422, f"题目“{question['title']}”应提交选项数组")
        if len(value) != len(set(value)) or not set(value).issubset(valid):
            raise HTTPException(422, f"题目“{question['title']}”包含无效或重复选项")
        if len(value) < validation.get('minSelections', 0) or len(value) > validation.get('maxSelections', math.inf):
            raise HTTPException(422, f"题目“{question['title']}”选择数量不符合要求")
    elif kind == 'text':
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(422, f"题目“{question['title']}”应填写文本")
        length = len(value)
        if length < validation.get('minLength', 0) or length > validation.get('maxLength', math.inf):
            raise HTTPException(422, f"题目“{question['title']}”文本长度不符合要求")
    elif kind == 'number':
        if type(value) not in (int, float) or not math.isfinite(value):
            raise HTTPException(422, f"题目“{question['title']}”应填写有限数值")
        if validation.get('integerOnly') and not float(value).is_integer():
            raise HTTPException(422, f"题目“{question['title']}”必须是整数")
        if value < validation.get('min', -math.inf) or value > validation.get('max', math.inf):
            raise HTTPException(422, f"题目“{question['title']}”超出允许范围")


def matches(condition, value):
    operator, expected = condition['operator'], condition['value']
    if operator == 'equals':
        return value == expected
    if operator == 'containsAny':
        return bool(set(value) & set(expected))
    if operator == 'containsAll':
        return set(expected).issubset(value)
    return {'eq': value == expected, 'gt': value > expected,
            'gte': value >= expected, 'lt': value < expected,
            'lte': value <= expected}[operator]


def validate_submission(questions, rules, submitted):
    by_id = {str(item['_id']): item for item in questions}
    answers = {item['questionId']: item['value'] for item in submitted}
    ordered = [str(item['_id']) for item in questions]
    path, index = [], 0
    while index < len(ordered):
        question_id = ordered[index]
        question = by_id[question_id]
        path.append(question_id)
        present = question_id in answers
        if question['required'] and not present:
            raise HTTPException(422, f"题目“{question['title']}”必须回答")
        if present:
            validate_answer(question, answers[question_id])
        target = None
        if present:
            for rule in rules:
                if str(rule['sourceQuestionId']) == question_id and matches(rule['condition'], answers[question_id]):
                    target = None if rule['targetQuestionId'] is None else str(rule['targetQuestionId'])
                    break
        if target is None:
            matched_end = present and any(
                str(r['sourceQuestionId']) == question_id and r['targetQuestionId'] is None and
                matches(r['condition'], answers[question_id]) for r in rules)
            if matched_end:
                break
            index += 1
        else:
            index = ordered.index(target)
    extras = set(answers) - set(path)
    if extras:
        raise HTTPException(422, '答卷包含当前跳转路径之外的题目')
    return [{'questionId': by_id[qid]['_id'], 'value': answers[qid]}
            for qid in path if qid in answers]

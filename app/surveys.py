from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo import ReturnDocument

from .common import object_id, serialize
from .models import (JumpRuleInput, OrderInput, QuestionInput, RulesInput,
                     SurveyCreate, SurveyUpdate)
from .security import current_user, require_origin, utcnow

router = APIRouter(prefix='/api/surveys', tags=['问卷管理'])


def owned_survey(request, survey_id, user):
    survey = request.app.state.db.surveys.find_one({'_id': object_id(survey_id, '问卷')})
    if not survey:
        raise HTTPException(404, '问卷不存在')
    if survey['ownerId'] != user['_id']:
        raise HTTPException(403, '无权管理该问卷')
    return survey


def draft_only(survey):
    if survey['status'] != 'draft':
        raise HTTPException(409, '发布后的问卷结构不能修改')


def full_survey(request, survey):
    questions = list(request.app.state.db.questions.find(
        {'_id': {'$in': survey['questionIds']}}))
    mapping = {q['_id']: q for q in questions}
    result = serialize(survey)
    result['questions'] = [serialize(mapping[qid]) for qid in survey['questionIds'] if qid in mapping]
    result['shareUrl'] = f"/survey/{survey['_id']}"
    return result


@router.post('', status_code=201, dependencies=[Depends(require_origin)])
def create_survey(body: SurveyCreate, request: Request, user=Depends(current_user)):
    now = utcnow()
    document = {'ownerId': user['_id'], 'title': body.title,
                'description': body.description, 'status': 'draft',
                'questionIds': [], 'anonymous': False, 'startsAt': None,
                'endsAt': None, 'maxSubmissionsPerUser': 1,
                'jumpRules': [], 'createdAt': now, 'updatedAt': now}
    document['_id'] = request.app.state.db.surveys.insert_one(document).inserted_id
    return full_survey(request, document)


@router.get('')
def list_surveys(request: Request, user=Depends(current_user)):
    return [serialize(item) for item in request.app.state.db.surveys.find(
        {'ownerId': user['_id']}).sort('createdAt', -1)]


@router.get('/{survey_id}')
def get_survey(survey_id: str, request: Request, user=Depends(current_user)):
    return full_survey(request, owned_survey(request, survey_id, user))


@router.patch('/{survey_id}', dependencies=[Depends(require_origin)])
def update_survey(survey_id: str, body: SurveyUpdate, request: Request,
                  user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    changes = body.model_dump(exclude_unset=True)
    structural = {'title', 'description', 'anonymous', 'startsAt', 'maxSubmissionsPerUser'}
    if survey['status'] != 'draft' and structural & changes.keys():
        raise HTTPException(409, '发布后只能修改截止时间')
    starts = changes.get('startsAt', survey.get('startsAt'))
    ends = changes.get('endsAt', survey.get('endsAt'))
    if starts and ends and ends <= starts:
        raise HTTPException(422, '截止时间必须晚于开始时间')
    changes['updatedAt'] = utcnow()
    updated = request.app.state.db.surveys.find_one_and_update(
        {'_id': survey['_id']}, {'$set': changes}, return_document=ReturnDocument.AFTER)
    return full_survey(request, updated)


@router.post('/{survey_id}/questions', status_code=201,
             dependencies=[Depends(require_origin)])
def add_question(survey_id: str, body: QuestionInput, request: Request,
                 user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    draft_only(survey)
    question = {'surveyId': survey['_id'], **body.model_dump(exclude_none=True)}
    result = request.app.state.db.questions.insert_one(question)
    try:
        request.app.state.db.surveys.update_one({'_id': survey['_id']}, {
            '$push': {'questionIds': result.inserted_id}, '$set': {'updatedAt': utcnow()}})
    except Exception:
        request.app.state.db.questions.delete_one({'_id': result.inserted_id})
        raise
    question['_id'] = result.inserted_id
    return serialize(question)


@router.patch('/{survey_id}/questions/{question_id}', dependencies=[Depends(require_origin)])
def edit_question(survey_id: str, question_id: str, body: QuestionInput,
                  request: Request, user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    draft_only(survey)
    qid = object_id(question_id, '题目')
    update = {'$set': body.model_dump(exclude_none=True)}
    if body.options is None:
        update['$unset'] = {'options': ''}
    result = request.app.state.db.questions.find_one_and_update(
        {'_id': qid, 'surveyId': survey['_id']}, update,
        return_document=ReturnDocument.AFTER)
    if not result:
        raise HTTPException(404, '题目不存在')
    return serialize(result)


@router.delete('/{survey_id}/questions/{question_id}', dependencies=[Depends(require_origin)])
def delete_question(survey_id: str, question_id: str, request: Request,
                    user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    draft_only(survey)
    qid = object_id(question_id, '题目')
    if not request.app.state.db.questions.find_one({'_id': qid, 'surveyId': survey['_id']}):
        raise HTTPException(404, '题目不存在')
    request.app.state.db.surveys.update_one({'_id': survey['_id']}, {
        '$pull': {'questionIds': qid},
        '$set': {'jumpRules': [rule for rule in survey['jumpRules']
                               if rule['sourceQuestionId'] != qid and rule['targetQuestionId'] != qid],
                 'updatedAt': utcnow()}})
    request.app.state.db.questions.delete_one({'_id': qid, 'surveyId': survey['_id']})
    return {'message': '题目已删除'}


@router.put('/{survey_id}/question-order', dependencies=[Depends(require_origin)])
def reorder(survey_id: str, body: OrderInput, request: Request,
            user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    draft_only(survey)
    ids = [object_id(value, '题目') for value in body.questionIds]
    if len(ids) != len(set(ids)) or set(ids) != set(survey['questionIds']):
        raise HTTPException(422, '题目顺序必须恰好包含问卷的全部题目且不能重复')
    request.app.state.db.surveys.update_one({'_id': survey['_id']},
        {'$set': {'questionIds': ids, 'jumpRules': [], 'updatedAt': utcnow()}})
    return {'questionIds': [str(item) for item in ids],
            'message': '顺序已更新；为防止错误，原跳转规则已清空'}


def validate_rule(rule, questions, positions):
    source = object_id(rule.sourceQuestionId, '源题目')
    target = None if rule.targetQuestionId is None else object_id(rule.targetQuestionId, '目标题目')
    if source not in questions or (target is not None and target not in questions):
        raise HTTPException(422, '跳转规则引用了不属于该问卷的题目')
    if target is not None and positions[target] <= positions[source]:
        raise HTTPException(422, '只允许跳转到后续题目')
    question, condition = questions[source], rule.condition
    allowed = {'single': {'equals'}, 'multiple': {'containsAny', 'containsAll'},
               'number': {'eq', 'gt', 'gte', 'lt', 'lte'}, 'text': set()}[question['type']]
    if condition.operator not in allowed:
        raise HTTPException(422, '判断条件与源题目类型不匹配')
    if question['type'] == 'single':
        if condition.value not in {o['id'] for o in question['options']}:
            raise HTTPException(422, '单选跳转条件引用了无效选项')
    elif question['type'] == 'multiple':
        if (not isinstance(condition.value, list) or not condition.value or
                not set(condition.value).issubset({o['id'] for o in question['options']})):
            raise HTTPException(422, '多选跳转条件必须使用有效选项数组')
    elif type(condition.value) not in (int, float):
        raise HTTPException(422, '数字跳转条件值必须是数值')
    return {'sourceQuestionId': source, 'condition': condition.model_dump(),
            'targetQuestionId': target}


@router.put('/{survey_id}/jump-rules', dependencies=[Depends(require_origin)])
def set_rules(survey_id: str, body: RulesInput, request: Request,
              user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    draft_only(survey)
    questions = {q['_id']: q for q in request.app.state.db.questions.find(
        {'_id': {'$in': survey['questionIds']}})}
    positions = {qid: index for index, qid in enumerate(survey['questionIds'])}
    rules = [validate_rule(item, questions, positions) for item in body.rules]
    request.app.state.db.surveys.update_one({'_id': survey['_id']},
        {'$set': {'jumpRules': rules, 'updatedAt': utcnow()}})
    return {'rules': serialize(rules)}


@router.post('/{survey_id}/publish', dependencies=[Depends(require_origin)])
def publish(survey_id: str, request: Request, user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    draft_only(survey)
    if not survey['questionIds']:
        raise HTTPException(422, '问卷至少需要一道题才能发布')
    found = {q['_id'] for q in request.app.state.db.questions.find(
        {'surveyId': survey['_id']}, {'_id': 1})}
    if found != set(survey['questionIds']):
        raise HTTPException(409, '问卷题目引用不一致，请检查数据')
    questions = {q['_id']: q for q in request.app.state.db.questions.find(
        {'_id': {'$in': survey['questionIds']}})}
    positions = {qid: index for index, qid in enumerate(survey['questionIds'])}
    for rule in survey['jumpRules']:
        validate_rule(JumpRuleInput(
            sourceQuestionId=str(rule['sourceQuestionId']),
            condition=rule['condition'],
            targetQuestionId=(None if rule['targetQuestionId'] is None
                              else str(rule['targetQuestionId']))),
            questions, positions)
    updated = request.app.state.db.surveys.find_one_and_update(
        {'_id': survey['_id'], 'status': 'draft'},
        {'$set': {'status': 'published', 'updatedAt': utcnow()}},
        return_document=ReturnDocument.AFTER)
    return full_survey(request, updated)


@router.post('/{survey_id}/close', dependencies=[Depends(require_origin)])
def close(survey_id: str, request: Request, user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    if survey['status'] != 'published':
        raise HTTPException(409, '只有已发布问卷可以关闭')
    request.app.state.db.surveys.update_one({'_id': survey['_id']},
        {'$set': {'status': 'closed', 'updatedAt': utcnow()}})
    return {'message': '问卷已关闭'}

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from .common import object_id, serialize
from .engine import validate_submission
from .models import ResponseInput
from .security import current_user, require_origin, utcnow

router = APIRouter(prefix='/api/fill', tags=['填写问卷'])


def available_survey(request, survey_id):
    survey = request.app.state.db.surveys.find_one({'_id': object_id(survey_id, '问卷')})
    if not survey:
        raise HTTPException(404, '问卷不存在')
    if survey['status'] != 'published':
        raise HTTPException(409, '问卷当前不可填写')
    now = utcnow()
    if survey.get('startsAt') and now < survey['startsAt']:
        raise HTTPException(409, '问卷尚未开始')
    if survey.get('endsAt') and now >= survey['endsAt']:
        raise HTTPException(409, '问卷已截止')
    return survey


def ordered_questions(database, survey):
    found = {q['_id']: q for q in database.questions.find(
        {'_id': {'$in': survey['questionIds']}})}
    if set(found) != set(survey['questionIds']):
        raise HTTPException(409, '问卷题目数据不完整')
    return [found[qid] for qid in survey['questionIds']]


@router.get('/{survey_id}')
def get_for_filling(survey_id: str, request: Request, user=Depends(current_user)):
    survey = available_survey(request, survey_id)
    count = request.app.state.db.responses.count_documents(
        {'surveyId': survey['_id'], 'respondentId': user['_id']})
    maximum = survey.get('maxSubmissionsPerUser')
    return {
        'id': str(survey['_id']), 'title': survey['title'],
        'description': survey['description'], 'anonymous': survey['anonymous'],
        'startsAt': survey.get('startsAt'), 'endsAt': survey.get('endsAt'),
        'maxSubmissionsPerUser': maximum, 'submissionsUsed': count,
        'canSubmit': maximum is None or count < maximum,
        'questions': serialize(ordered_questions(request.app.state.db, survey)),
        'jumpRules': serialize(survey['jumpRules']),
    }


@router.post('/{survey_id}/responses', status_code=201,
             dependencies=[Depends(require_origin)])
def submit(survey_id: str, body: ResponseInput, request: Request,
           user=Depends(current_user)):
    database = request.app.state.db
    survey = available_survey(request, survey_id)
    existing = database.responses.find_one({
        'surveyId': survey['_id'], 'respondentId': user['_id'],
        'requestId': body.requestId})
    if existing:
        return {'id': str(existing['_id']), 'attempt': existing['attempt'],
                'submittedAt': existing['submittedAt'], 'duplicate': True}
    questions = ordered_questions(database, survey)
    answers = validate_submission(questions, survey['jumpRules'],
                                  [item.model_dump() for item in body.answers])
    for _ in range(4):
        latest = database.responses.find_one(
            {'surveyId': survey['_id'], 'respondentId': user['_id']},
            sort=[('attempt', -1)], projection={'attempt': 1})
        attempt = (latest['attempt'] if latest else 0) + 1
        maximum = survey.get('maxSubmissionsPerUser')
        if maximum is not None and attempt > maximum:
            raise HTTPException(409, '已达到允许填写次数')
        document = {'surveyId': survey['_id'], 'respondentId': user['_id'],
                    'attempt': attempt, 'requestId': body.requestId,
                    'submittedAt': utcnow(), 'answers': answers}
        try:
            result = database.responses.insert_one(document)
            return {'id': str(result.inserted_id), 'attempt': attempt,
                    'submittedAt': document['submittedAt'], 'duplicate': False}
        except DuplicateKeyError:
            existing = database.responses.find_one({
                'surveyId': survey['_id'], 'respondentId': user['_id'],
                'requestId': body.requestId})
            if existing:
                return {'id': str(existing['_id']), 'attempt': existing['attempt'],
                        'submittedAt': existing['submittedAt'], 'duplicate': True}
    raise HTTPException(409, '同时提交冲突，请重试')

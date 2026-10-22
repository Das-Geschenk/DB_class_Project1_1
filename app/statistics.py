from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .common import object_id, serialize
from .security import current_user
from .surveys import owned_survey

router = APIRouter(prefix='/api/surveys', tags=['统计'])


def question_statistics(question, values):
    kind = question['type']
    result = {'questionId': str(question['_id']), 'title': question['title'],
              'type': kind, 'answeredCount': len(values)}
    if kind in ('single', 'multiple'):
        counts = {item['id']: 0 for item in question['options']}
        for value in values:
            selected = [value] if kind == 'single' else value
            for option_id in selected:
                if option_id in counts:
                    counts[option_id] += 1
        result['options'] = [{'id': item['id'], 'label': item['label'],
                              'count': counts[item['id']]}
                             for item in question['options']]
    else:
        result['values'] = values
        if kind == 'number':
            result['average'] = sum(values) / len(values) if values else None
    return result


def all_statistics(database, survey):
    questions = {q['_id']: q for q in database.questions.find(
        {'_id': {'$in': survey['questionIds']}})}
    values = {qid: [] for qid in survey['questionIds']}
    total = 0
    for response in database.responses.find({'surveyId': survey['_id']}, {'answers': 1}):
        total += 1
        for answer in response['answers']:
            if answer['questionId'] in values:
                values[answer['questionId']].append(answer['value'])
    return total, [question_statistics(questions[qid], values[qid])
                   for qid in survey['questionIds'] if qid in questions]


@router.get('/{survey_id}/statistics')
def survey_statistics(survey_id: str, request: Request, user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    total, questions = all_statistics(request.app.state.db, survey)
    return {'surveyId': str(survey['_id']), 'title': survey['title'],
            'responseCount': total, 'questions': questions}


@router.get('/{survey_id}/questions/{question_id}/statistics')
def single_statistics(survey_id: str, question_id: str, request: Request,
                      user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    qid = object_id(question_id, '题目')
    if qid not in survey['questionIds']:
        raise HTTPException(404, '题目不存在')
    total, questions = all_statistics(request.app.state.db, survey)
    result = next(item for item in questions if item['questionId'] == str(qid))
    result['surveyResponseCount'] = total
    return result


@router.get('/{survey_id}/responses')
def list_responses(survey_id: str, request: Request,
                   skip: int = Query(default=0, ge=0),
                   limit: int = Query(default=50, ge=1, le=100),
                   user=Depends(current_user)):
    survey = owned_survey(request, survey_id, user)
    database = request.app.state.db
    cursor = database.responses.find({'surveyId': survey['_id']}).sort(
        'submittedAt', -1).skip(skip).limit(limit)
    documents = list(cursor)
    if survey['anonymous']:
        for document in documents:
            document.pop('respondentId', None)
    else:
        ids = {item['respondentId'] for item in documents}
        users = {item['_id']: item['username'] for item in database.users.find(
            {'_id': {'$in': list(ids)}}, {'username': 1})}
        for document in documents:
            document['respondentUsername'] = users.get(document['respondentId'], '已删除用户')
            document['respondentId'] = str(document['respondentId'])
    return {'total': database.responses.count_documents({'surveyId': survey['_id']}),
            'items': serialize(documents)}

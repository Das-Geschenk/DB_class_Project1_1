import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import utcnow


TEST_DATABASE = os.getenv('TEST_MONGO_DATABASE', '')


@unittest.skipUnless(TEST_DATABASE.startswith('survey_project1_1_test_'),
                     '需要设置安全的 TEST_MONGO_DATABASE')
class PhaseOneIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = Settings(
            mongo_uri=os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017'),
            database_name=TEST_DATABASE,
            app_origin='http://127.0.0.1:8001',
            jwt_secret='integration-test-secret-at-least-32-characters',
            cookie_secure=False,
        )
        cls.app = create_app(settings)
        cls.owner = TestClient(cls.app, base_url=settings.app_origin)
        cls.respondent = TestClient(cls.app, base_url=settings.app_origin)
        cls.other = TestClient(cls.app, base_url=settings.app_origin)
        cls.owner.__enter__()
        cls.respondent.__enter__()
        cls.other.__enter__()
        cls.headers = {'Origin': settings.app_origin}

    @classmethod
    def tearDownClass(cls):
        for client in (cls.other, cls.respondent, cls.owner):
            client.__exit__(None, None, None)

    def post(self, client, path, body=None):
        return client.post(path, json={} if body is None else body,
                           headers=self.headers)

    def put(self, client, path, body):
        return client.put(path, json=body, headers=self.headers)

    def patch(self, client, path, body):
        return client.patch(path, json=body, headers=self.headers)

    def register_login(self, client, prefix):
        credentials = {'username': prefix + '_' + uuid4().hex,
                       'password': 'example-password'}
        self.assertEqual(self.post(client, '/api/auth/register', credentials).status_code, 201)
        self.assertEqual(self.post(client, '/api/auth/register', credentials).status_code, 409)
        bad = {**credentials, 'password': 'wrong-password'}
        self.assertEqual(self.post(client, '/api/auth/login', bad).status_code, 401)
        response = self.post(client, '/api/auth/login', credentials)
        self.assertEqual(response.status_code, 200)
        return credentials['username']

    def add_question(self, survey_id, body):
        response = self.post(self.owner, f'/api/surveys/{survey_id}/questions', body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_complete_phase_one_flow(self):
        owner_name = self.register_login(self.owner, 'owner')
        respondent_name = self.register_login(self.respondent, 'respondent')
        self.register_login(self.other, 'other')

        response = self.post(self.owner, '/api/surveys',
                             {'title': '校园生活调查', 'description': '集成测试'})
        self.assertEqual(response.status_code, 201, response.text)
        survey_id = response.json()['_id']
        response = self.patch(self.owner, f'/api/surveys/{survey_id}', {
            'anonymous': True, 'maxSubmissionsPerUser': 1})
        self.assertEqual(response.status_code, 200, response.text)

        q1 = self.add_question(survey_id, {
            'title': '你是在校学生吗', 'type': 'single', 'required': True,
            'options': [{'id': 'yes', 'label': '是'}, {'id': 'no', 'label': '否'}],
            'validation': {}})
        q2 = self.add_question(survey_id, {
            'title': '喜欢的活动', 'type': 'multiple', 'required': True,
            'options': [{'id': 'reading', 'label': '阅读'},
                        {'id': 'sports', 'label': '运动'},
                        {'id': 'music', 'label': '音乐'}],
            'validation': {'minSelections': 2, 'maxSelections': 2}})
        q3 = self.add_question(survey_id, {
            'title': '校园建议', 'type': 'text', 'required': True,
            'validation': {'minLength': 2, 'maxLength': 20}})
        q4 = self.add_question(survey_id, {
            'title': '年龄', 'type': 'number', 'required': True,
            'validation': {'min': 0, 'max': 120, 'integerOnly': True}})

        rules = {'rules': [{
            'sourceQuestionId': q1['_id'],
            'condition': {'operator': 'equals', 'value': 'no'},
            'targetQuestionId': q4['_id']} ]}
        response = self.put(self.owner, f'/api/surveys/{survey_id}/jump-rules', rules)
        self.assertEqual(response.status_code, 200, response.text)

        response = self.post(self.owner, f'/api/surveys/{survey_id}/publish')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.patch(self.owner, f'/api/surveys/{survey_id}',
                                    {'anonymous': False}).status_code, 409)
        self.assertEqual(self.post(self.owner,
            f'/api/surveys/{survey_id}/questions', {
                'title': '发布后新增', 'type': 'text', 'required': False,
                'validation': {}}).status_code, 409)

        self.assertEqual(self.other.get(f'/api/surveys/{survey_id}').status_code, 403)
        fill = self.respondent.get(f'/api/fill/{survey_id}')
        self.assertEqual(fill.status_code, 200, fill.text)
        self.assertTrue(fill.json()['canSubmit'])

        invalid_multi = {'requestId': uuid4().hex, 'answers': [
            {'questionId': q1['_id'], 'value': 'yes'},
            {'questionId': q2['_id'], 'value': ['reading']},
            {'questionId': q3['_id'], 'value': '很好'},
            {'questionId': q4['_id'], 'value': 20}]}
        self.assertEqual(self.post(self.respondent,
            f'/api/fill/{survey_id}/responses', invalid_multi).status_code, 422)

        invalid_number = {'requestId': uuid4().hex, 'answers': [
            {'questionId': q1['_id'], 'value': 'no'},
            {'questionId': q4['_id'], 'value': 20.5}]}
        self.assertEqual(self.post(self.respondent,
            f'/api/fill/{survey_id}/responses', invalid_number).status_code, 422)

        outside_path = {'requestId': uuid4().hex, 'answers': [
            {'questionId': q1['_id'], 'value': 'no'},
            {'questionId': q2['_id'], 'value': ['reading', 'sports']},
            {'questionId': q4['_id'], 'value': 20}]}
        self.assertEqual(self.post(self.respondent,
            f'/api/fill/{survey_id}/responses', outside_path).status_code, 422)

        request_id = uuid4().hex
        valid = {'requestId': request_id, 'answers': [
            {'questionId': q1['_id'], 'value': 'no'},
            {'questionId': q4['_id'], 'value': 20}]}
        submitted = self.post(self.respondent,
            f'/api/fill/{survey_id}/responses', valid)
        self.assertEqual(submitted.status_code, 201, submitted.text)
        self.assertEqual(submitted.json()['attempt'], 1)
        duplicate = self.post(self.respondent,
            f'/api/fill/{survey_id}/responses', valid)
        self.assertEqual(duplicate.status_code, 201, duplicate.text)
        self.assertTrue(duplicate.json()['duplicate'])
        valid['requestId'] = uuid4().hex
        self.assertEqual(self.post(self.respondent,
            f'/api/fill/{survey_id}/responses', valid).status_code, 409)

        statistics = self.owner.get(f'/api/surveys/{survey_id}/statistics')
        self.assertEqual(statistics.status_code, 200, statistics.text)
        data = statistics.json()
        self.assertEqual(data['responseCount'], 1)
        age = next(item for item in data['questions'] if item['questionId'] == q4['_id'])
        self.assertEqual(age['average'], 20)
        self.assertEqual(self.owner.get(
            f'/api/surveys/{survey_id}/questions/{q4["_id"]}/statistics').status_code, 200)

        answers = self.owner.get(f'/api/surveys/{survey_id}/responses').json()['items']
        self.assertEqual(len(answers), 1)
        self.assertNotIn('respondentId', answers[0])
        self.assertNotIn('respondentUsername', answers[0])
        self.assertNotIn(owner_name, str(answers))
        self.assertNotIn(respondent_name, str(answers))

        self.assertEqual(self.post(self.owner,
            f'/api/surveys/{survey_id}/close').status_code, 200)
        self.assertEqual(self.respondent.get(f'/api/fill/{survey_id}').status_code, 409)

    def test_nonanonymous_identity_and_time_windows(self):
        self.register_login(self.owner, 'time_owner')
        respondent_name = self.register_login(self.respondent, 'visible_respondent')

        future = self.post(self.owner, '/api/surveys',
                           {'title': '未来问卷', 'description': ''}).json()
        fq = self.add_question(future['_id'], {
            'title': '问题', 'type': 'text', 'required': True,
            'validation': {'minLength': 1}})
        response = self.patch(self.owner, f"/api/surveys/{future['_id']}", {
            'startsAt': (utcnow() + timedelta(days=1)).isoformat()})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.post(self.owner,
            f"/api/surveys/{future['_id']}/publish").status_code, 200)
        self.assertEqual(self.respondent.get(
            f"/api/fill/{future['_id']}").status_code, 409)

        expired = self.post(self.owner, '/api/surveys',
                            {'title': '截止问卷', 'description': ''}).json()
        self.add_question(expired['_id'], {
            'title': '问题', 'type': 'text', 'required': True,
            'validation': {}})
        response = self.patch(self.owner, f"/api/surveys/{expired['_id']}", {
            'endsAt': (utcnow() - timedelta(minutes=1)).isoformat()})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.post(self.owner,
            f"/api/surveys/{expired['_id']}/publish").status_code, 200)
        self.assertEqual(self.respondent.get(
            f"/api/fill/{expired['_id']}").status_code, 409)

        visible = self.post(self.owner, '/api/surveys',
                            {'title': '非匿名问卷', 'description': ''}).json()
        vq = self.add_question(visible['_id'], {
            'title': '留言', 'type': 'text', 'required': True,
            'validation': {'minLength': 2, 'maxLength': 10}})
        self.assertEqual(self.post(self.owner,
            f"/api/surveys/{visible['_id']}/publish").status_code, 200)
        submitted = self.post(self.respondent,
            f"/api/fill/{visible['_id']}/responses", {
                'requestId': uuid4().hex,
                'answers': [{'questionId': vq['_id'], 'value': '很好'}]})
        self.assertEqual(submitted.status_code, 201, submitted.text)
        item = self.owner.get(f"/api/surveys/{visible['_id']}/responses").json()['items'][0]
        self.assertEqual(item['respondentUsername'], respondent_name)
        self.assertIn('respondentId', item)

    def test_concurrent_last_attempt(self):
        self.register_login(self.owner, 'concurrent_owner')
        credentials = {'username': 'concurrent_' + uuid4().hex,
                       'password': 'example-password'}
        self.assertEqual(self.post(self.respondent,
            '/api/auth/register', credentials).status_code, 201)
        self.assertEqual(self.post(self.respondent,
            '/api/auth/login', credentials).status_code, 200)
        survey = self.post(self.owner, '/api/surveys',
                           {'title': '并发测试', 'description': ''}).json()
        question = self.add_question(survey['_id'], {
            'title': '答案', 'type': 'text', 'required': True,
            'validation': {}})
        self.assertEqual(self.post(self.owner,
            f"/api/surveys/{survey['_id']}/publish").status_code, 200)

        def send(_):
            return self.post(self.respondent,
                f"/api/fill/{survey['_id']}/responses", {
                    'requestId': uuid4().hex,
                    'answers': [{'questionId': question['_id'], 'value': '回答'}]
                }).status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(send, range(8)))
        self.assertEqual(statuses.count(201), 1, statuses)
        self.assertEqual(statuses.count(409), 7, statuses)


if __name__ == '__main__':
    unittest.main()

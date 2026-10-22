import unittest
from bson import ObjectId
from fastapi import HTTPException

from app.engine import validate_submission


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.q1, self.q2, self.q3 = ObjectId(), ObjectId(), ObjectId()
        self.questions = [
            {'_id': self.q1, 'title': '是否继续', 'type': 'single', 'required': True,
             'options': [{'id': 'yes', 'label': '是'}, {'id': 'no', 'label': '否'}],
             'validation': {}},
            {'_id': self.q2, 'title': '水果', 'type': 'multiple', 'required': True,
             'options': [{'id': 'a', 'label': '苹果'}, {'id': 'b', 'label': '香蕉'}],
             'validation': {'minSelections': 1, 'maxSelections': 2}},
            {'_id': self.q3, 'title': '年龄', 'type': 'number', 'required': True,
             'validation': {'min': 0, 'max': 120, 'integerOnly': True}},
        ]

    def test_sequential_path(self):
        result = validate_submission(self.questions, [], [
            {'questionId': str(self.q1), 'value': 'yes'},
            {'questionId': str(self.q2), 'value': ['a']},
            {'questionId': str(self.q3), 'value': 20},
        ])
        self.assertEqual([item['questionId'] for item in result], [self.q1, self.q2, self.q3])

    def test_jump_skips_required_question(self):
        rules = [{'sourceQuestionId': self.q1,
                  'condition': {'operator': 'equals', 'value': 'no'},
                  'targetQuestionId': self.q3}]
        result = validate_submission(self.questions, rules, [
            {'questionId': str(self.q1), 'value': 'no'},
            {'questionId': str(self.q3), 'value': 30},
        ])
        self.assertEqual([item['questionId'] for item in result], [self.q1, self.q3])

    def test_rejects_answer_outside_path(self):
        rules = [{'sourceQuestionId': self.q1,
                  'condition': {'operator': 'equals', 'value': 'no'},
                  'targetQuestionId': self.q3}]
        with self.assertRaises(HTTPException):
            validate_submission(self.questions, rules, [
                {'questionId': str(self.q1), 'value': 'no'},
                {'questionId': str(self.q2), 'value': ['a']},
                {'questionId': str(self.q3), 'value': 30},
            ])

    def test_number_integer_and_range(self):
        with self.assertRaises(HTTPException):
            validate_submission(self.questions, [], [
                {'questionId': str(self.q1), 'value': 'yes'},
                {'questionId': str(self.q2), 'value': ['a']},
                {'questionId': str(self.q3), 'value': 20.5},
            ])

    def test_multiple_contains_all_jump(self):
        rules = [{'sourceQuestionId': self.q2,
                  'condition': {'operator': 'containsAll', 'value': ['a', 'b']},
                  'targetQuestionId': None}]
        result = validate_submission(self.questions, rules, [
            {'questionId': str(self.q1), 'value': 'yes'},
            {'questionId': str(self.q2), 'value': ['a', 'b']},
        ])
        self.assertEqual([item['questionId'] for item in result], [self.q1, self.q2])

    def test_number_comparison_jump(self):
        questions = [self.questions[2], {
            '_id': ObjectId(), 'title': '后续', 'type': 'text',
            'required': True, 'validation': {}}]
        rules = [{'sourceQuestionId': self.q3,
                  'condition': {'operator': 'gte', 'value': 18},
                  'targetQuestionId': None}]
        result = validate_submission(questions, rules, [
            {'questionId': str(self.q3), 'value': 20}])
        self.assertEqual(len(result), 1)

    def test_text_length_validation(self):
        question = {'_id': ObjectId(), 'title': '留言', 'type': 'text',
                    'required': True, 'validation': {'minLength': 2, 'maxLength': 4}}
        with self.assertRaises(HTTPException):
            validate_submission([question], [], [
                {'questionId': str(question['_id']), 'value': '一'}])


if __name__ == '__main__':
    unittest.main()

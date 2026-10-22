import unittest
from pydantic import ValidationError

from app.models import QuestionInput


class QuestionModelTests(unittest.TestCase):
    def test_valid_multiple_choice(self):
        item = QuestionInput(title='水果', type='multiple', required=True,
            options=[{'id': 'a', 'label': '苹果'}, {'id': 'b', 'label': '香蕉'}],
            validation={'minSelections': 1, 'maxSelections': 2})
        self.assertEqual(item.type, 'multiple')

    def test_rejects_duplicate_option_ids(self):
        with self.assertRaises(ValidationError):
            QuestionInput(title='水果', type='single', options=[
                {'id': 'a', 'label': '苹果'}, {'id': 'a', 'label': '香蕉'}])

    def test_rejects_options_on_text(self):
        with self.assertRaises(ValidationError):
            QuestionInput(title='留言', type='text', options=[{'id': 'x', 'label': 'x'}])


if __name__ == '__main__':
    unittest.main()

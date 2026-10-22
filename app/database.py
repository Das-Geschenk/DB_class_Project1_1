from pymongo import MongoClient


def connect(settings):
    client = MongoClient(settings.mongo_uri, tz_aware=True,
                         serverSelectionTimeoutMS=5000)
    try:
        client.admin.command('ping')
        database = client[settings.database_name]
        expected = {'users', 'surveys', 'questions', 'responses'}
        infos = {item['name']: item for item in database.list_collections()}
        if not expected.issubset(infos):
            raise RuntimeError('数据库缺少必要集合，请先执行 init_database.js。')
        for name in expected:
            options = infos[name].get('options', {})
            if not options.get('validator', {}).get('$jsonSchema'):
                raise RuntimeError(f'{name} 缺少字段校验器，请检查数据库初始化结果。')
            if options.get('validationLevel', 'strict') != 'strict' or options.get('validationAction', 'error') != 'error':
                raise RuntimeError(f'{name} 的校验模式应为 strict/error。')
        required_indexes = {
            'users': [([('username', 1)], True)],
            'surveys': [([('ownerId', 1), ('createdAt', -1)], False)],
            'questions': [([('surveyId', 1)], False)],
            'responses': [
                ([('surveyId', 1), ('respondentId', 1), ('attempt', 1)], True),
                ([('surveyId', 1), ('respondentId', 1), ('requestId', 1)], True),
                ([('surveyId', 1), ('submittedAt', -1)], False),
            ],
        }
        for name, requirements in required_indexes.items():
            indexes = list(database[name].list_indexes())
            for keys, unique in requirements:
                if not any(list(i['key'].items()) == keys and
                           bool(i.get('unique', False)) == unique for i in indexes):
                    raise RuntimeError(f'{name} 缺少必要索引，请检查初始化结果。')
        return client, database
    except Exception:
        client.close()
        raise

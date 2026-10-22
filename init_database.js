// Run with mongosh. This script does not delete databases, collections or documents.
// Tests may set TEST_DATABASE_NAME before loading this file. Only the guarded
// course-test prefix is accepted; normal use always initializes the formal DB.
const databaseName = (typeof TEST_DATABASE_NAME !== 'undefined')
  ? TEST_DATABASE_NAME : 'survey_project1_1';
if (databaseName !== 'survey_project1_1' &&
    !databaseName.startsWith('survey_project1_1_test_')) {
  throw new Error('Refusing to initialize an unexpected database name: ' + databaseName);
}
const projectDb = db.getSiblingDB(databaseName);
const oid = { bsonType: 'objectId' };
const date = { bsonType: 'date' };
const str = { bsonType: 'string' };
const nullableDate = { bsonType: ['date', 'null'] };
const numeric = { bsonType: ['int', 'long', 'double', 'decimal'] };
const schemas = {
  users: {
    bsonType: 'object',
    required: ['username', 'passwordHash', 'createdAt'],
    properties: {
      _id: oid,
      username: { bsonType: 'string', minLength: 1, maxLength: 100 },
      passwordHash: { bsonType: 'string', minLength: 1 },
      createdAt: date
    }
  },
  surveys: {
    bsonType: 'object',
    required: ['ownerId', 'title', 'description', 'status', 'questionIds',
      'anonymous', 'startsAt', 'endsAt', 'maxSubmissionsPerUser', 'jumpRules',
      'createdAt', 'updatedAt'],
    properties: {
      _id: oid,
      ownerId: oid,
      title: { bsonType: 'string', minLength: 1, maxLength: 200 },
      description: str,
      status: { enum: ['draft', 'published', 'closed'] },
      questionIds: { bsonType: 'array', uniqueItems: true, items: oid },
      anonymous: { bsonType: 'bool' },
      startsAt: nullableDate,
      endsAt: nullableDate,
      maxSubmissionsPerUser: {
        anyOf: [{ bsonType: 'null' }, { bsonType: ['int', 'long'], minimum: 1 }]
      },
      jumpRules: {
        bsonType: 'array',
        items: {
          bsonType: 'object',
          required: ['sourceQuestionId', 'condition', 'targetQuestionId'],
          properties: {
            sourceQuestionId: oid,
            targetQuestionId: { bsonType: ['objectId', 'null'] },
            condition: {
              bsonType: 'object',
              required: ['operator', 'value'],
              properties: {
                operator: { enum: ['equals', 'containsAny', 'containsAll',
                  'eq', 'gt', 'gte', 'lt', 'lte'] },
                value: {
                  anyOf: [str, numeric, {
                    bsonType: 'array', minItems: 1, uniqueItems: true, items: str
                  }]
                }
              }
            }
          }
        }
      },
      createdAt: date,
      updatedAt: date
    }
  },
  questions: {
    bsonType: 'object',
    required: ['surveyId', 'title', 'type', 'required', 'validation'],
    properties: {
      _id: oid,
      surveyId: oid,
      title: { bsonType: 'string', minLength: 1 },
      type: { enum: ['single', 'multiple', 'text', 'number'] },
      required: { bsonType: 'bool' },
      options: {
        bsonType: 'array',
        items: {
          bsonType: 'object', required: ['id', 'label'],
          properties: {
            id: { bsonType: 'string', minLength: 1 },
            label: { bsonType: 'string', minLength: 1 }
          }
        }
      },
      validation: {
        bsonType: 'object',
        properties: {
          minSelections: { bsonType: ['int', 'long'], minimum: 0 },
          maxSelections: { bsonType: ['int', 'long'], minimum: 0 },
          minLength: { bsonType: ['int', 'long'], minimum: 0 },
          maxLength: { bsonType: ['int', 'long'], minimum: 0 },
          min: numeric,
          max: numeric,
          integerOnly: { bsonType: 'bool' }
        }
      }
    },
    oneOf: [
      {
        properties: {
          type: { enum: ['single', 'multiple'] },
          options: { minItems: 1 }
        },
        required: ['options']
      },
      {
        properties: { type: { enum: ['text', 'number'] } },
        not: { required: ['options'] }
      }
    ]
  },
  responses: {
    bsonType: 'object',
    required: ['surveyId', 'respondentId', 'attempt', 'requestId',
      'submittedAt', 'answers'],
    properties: {
      _id: oid,
      surveyId: oid,
      respondentId: oid,
      attempt: { bsonType: ['int', 'long'], minimum: 1 },
      requestId: { bsonType: 'string', minLength: 1 },
      submittedAt: date,
      answers: {
        bsonType: 'array',
        items: {
          bsonType: 'object', required: ['questionId', 'value'],
          properties: {
            questionId: oid,
            value: {
              anyOf: [str, numeric, {
                bsonType: 'array', uniqueItems: true, items: str
              }]
            }
          }
        }
      }
    }
  }
};

function checkResult(result, operation) {
  if (result.ok !== 1) throw new Error(operation + ': ' + JSON.stringify(result));
}

for (const [name, schema] of Object.entries(schemas)) {
  const validator = { $jsonSchema: schema };
  if (projectDb.getCollectionNames().includes(name)) {
    // Avoid silently replacing an existing collection's rules.
    const info = projectDb.getCollectionInfos({ name })[0];
    const options = info.options || {};
    const hasValidator = options.validator && Object.keys(options.validator).length > 0;
    const hasDocuments = projectDb.getCollection(name).findOne({}) !== null;
    if (hasValidator || hasDocuments) {
      throw new Error('Collection ' + name + ' already has rules or data. Stop and review it before initialization.');
    }
    checkResult(projectDb.runCommand({
      collMod: name, validator, validationLevel: 'strict', validationAction: 'error'
    }), 'Configure ' + name);
  } else {
    checkResult(projectDb.createCollection(name, {
      validator, validationLevel: 'strict', validationAction: 'error'
    }), 'Create ' + name);
  }
  print('Configured collection: ' + name);
}

projectDb.users.createIndex({ username: 1 }, { unique: true, name: 'uq_username' });
projectDb.surveys.createIndex({ ownerId: 1, createdAt: -1 }, { name: 'owner_created' });
projectDb.questions.createIndex({ surveyId: 1 }, { name: 'question_survey' });
projectDb.responses.createIndex({ surveyId: 1, respondentId: 1, attempt: 1 },
  { unique: true, name: 'uq_response_attempt' });
projectDb.responses.createIndex({ surveyId: 1, respondentId: 1, requestId: 1 },
  { unique: true, name: 'uq_response_request' });
projectDb.responses.createIndex({ surveyId: 1, submittedAt: -1 },
  { name: 'response_survey_time' });
print('Initialization complete: ' + projectDb.getName());
printjson(projectDb.getCollectionNames());

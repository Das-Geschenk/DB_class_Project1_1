# API 说明

所有路径以当前站点为根。除注册、登录和健康检查外均需登录。修改请求还必须携带与 `APP_ORIGIN` 一致的 `Origin`；网页会自动携带。错误统一以 HTTP 状态码和 `{"detail":"说明"}` 返回。

## 账号

| 方法 | 路径 | 请求或结果 |
| --- | --- | --- |
| POST | /api/auth/register | `{"username":"u","password":"至少八字符"}` |
| POST | /api/auth/login | 同上，成功设置 HttpOnly Cookie |
| POST | /api/auth/logout | 清除 Cookie |
| GET | /api/auth/me | 当前用户公开信息 |

## 问卷管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST、GET | /api/surveys | 创建草稿；列出自己的问卷 |
| GET、PATCH | /api/surveys/{id} | 查看完整问卷；修改草稿设置 |
| POST | /api/surveys/{id}/questions | 添加题目 |
| PATCH、DELETE | /api/surveys/{id}/questions/{qid} | 编辑、删除题目 |
| PUT | /api/surveys/{id}/question-order | `{"questionIds":[...]}`，排序后清空规则 |
| PUT | /api/surveys/{id}/jump-rules | `{"rules":[...]}` |
| POST | /api/surveys/{id}/publish | 完整检查后发布 |
| POST | /api/surveys/{id}/close | 关闭已发布问卷 |

题目示例：

```json
{
  "title": "喜欢的水果",
  "type": "multiple",
  "required": true,
  "options": [{"id": "apple", "label": "苹果"}, {"id": "banana", "label": "香蕉"}],
  "validation": {"minSelections": 1, "maxSelections": 2}
}
```

跳转规则示例：

```json
{
  "rules": [{
    "sourceQuestionId": "源题目 ObjectId 字符串",
    "condition": {"operator": "equals", "value": "no"},
    "targetQuestionId": "后续题目 ObjectId 字符串"
  }]
}
```

目标为 `null` 表示结束。运算符：单选 `equals`；多选 `containsAny`、`containsAll`；数字 `eq`、`gt`、`gte`、`lt`、`lte`。

## 填写与统计

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/fill/{id} | 取得发布问卷、规则及已用次数 |
| POST | /api/fill/{id}/responses | 提交答卷 |
| GET | /api/surveys/{id}/statistics | 创建者查看整卷统计 |
| GET | /api/surveys/{id}/questions/{qid}/statistics | 单题统计 |
| GET | /api/surveys/{id}/responses?skip=0&limit=50 | 分页答卷；匿名问卷移除填写者身份 |

提交示例：

```json
{
  "requestId": "客户端本次提交的唯一 UUID",
  "answers": [
    {"questionId": "题目 ObjectId 字符串", "value": "apple"}
  ]
}
```

相同用户、问卷和 `requestId` 的重试返回原结果，不重复计次。后端只接受实际跳转路径上的答案。

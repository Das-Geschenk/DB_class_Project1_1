# MongoDB 数据库配置

本项目默认使用本机 MongoDB 数据库 `survey_project1_1`。初始化脚本会创建 `users`、`surveys`、`questions` 和 `responses` 四个集合，并配置文档校验器与必要索引。

## 1. 前置条件

- 已安装并启动 MongoDB；
- 已安装 `mongosh`；
- MongoDB 默认监听 `127.0.0.1:27017`。

可先检查连接：

```powershell
mongosh "mongodb://127.0.0.1:27017" --eval "db.runCommand({ ping: 1 })"
```

返回 `ok: 1` 表示连接正常。

## 2. 初始化正式数据库

在项目根目录执行：

```powershell
mongosh "mongodb://127.0.0.1:27017" --file ".\init_database.js"
```

脚本默认操作 `survey_project1_1`。为避免覆盖已有数据，如果目标集合已有文档或校验规则，脚本会停止并要求先检查数据库。

初始化完成后可查看集合：

```powershell
mongosh "mongodb://127.0.0.1:27017/survey_project1_1" --quiet --eval "printjson(db.getCollectionNames())"
```

正常结果应包含 `users`、`surveys`、`questions` 和 `responses`。

## 3. 应用连接配置

`.env.example` 用于说明需要的配置项，程序不会自动加载 `.env` 文件。可在 PowerShell 中设置：

```powershell
$env:MONGO_URI = 'mongodb://127.0.0.1:27017'
$env:MONGO_DATABASE = 'survey_project1_1'
$env:APP_ORIGIN = 'http://127.0.0.1:8001'
$env:JWT_SECRET = (& python -c 'import secrets; print(secrets.token_urlsafe(48))')
$env:COOKIE_SECURE = 'false'
```

应用启动时会检查四个集合及其关键唯一索引是否存在。集合未初始化或索引不完整时，启动会失败并给出错误信息；应用不会在启动时自动重建数据库结构。

## 4. 数据库结构

| 集合 | 用途 | 关键索引 |
| --- | --- | --- |
| `users` | 用户账号和密码哈希 | `username` 唯一 |
| `surveys` | 问卷元数据、状态和设置 | `ownerId + createdAt` |
| `questions` | 题目、选项和校验规则 | 按 `surveyId` 查询 |
| `responses` | 答卷、答案、实际路径和提交时间 | 填写次数与请求幂等唯一索引 |

MongoDB 自动为每份文档生成 `_id`。问卷通过 `questionIds` 数组保存题目顺序，答案和跳转规则使用题目的 `_id` 建立引用。

## 5. 集成测试数据库

集成测试必须使用以 `survey_project1_1_test` 开头的临时数据库，避免修改正式数据。例如：

```powershell
mongosh "mongodb://127.0.0.1:27017" --quiet --eval "const TEST_DATABASE_NAME='survey_project1_1_test_local'; load('init_database.js');"
$env:TEST_MONGO_DATABASE = "survey_project1_1_test_local"
python -m unittest discover -s tests -v
```

测试结束后可删除临时数据库：

```powershell
mongosh "mongodb://127.0.0.1:27017/survey_project1_1_test_local" --quiet --eval "db.dropDatabase()"
```

## 6. 常见问题

- **`mongosh` 无法连接**：确认 MongoDB 服务已经启动，并检查端口是否为 `27017`。
- **提示集合已有规则或数据**：说明目标数据库已经初始化或包含数据。先确认数据库名称，不要直接覆盖仍需保留的数据。
- **应用提示缺少索引**：重新核对连接的数据库名称，并使用 `getIndexes()` 检查初始化结果。
- **认证失败**：将带用户名、密码和认证库的连接串写入本机 `.env`；不要把真实凭据提交到仓库。

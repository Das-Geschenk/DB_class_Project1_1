# MongoDB 问卷系统

一个使用 FastAPI 和 MongoDB 实现的简化在线问卷系统。用户可以创建和发布问卷，通过链接邀请其他登录用户填写，并查看自动生成的统计结果。

系统支持可配置的条件跳转、输入校验、匿名答卷和每人填写次数限制。前端使用原生 HTML、CSS 和 JavaScript，无需额外的前端构建工具。

## 功能

- 用户注册、登录和退出
- 用户只能管理自己创建的问卷
- 问卷草稿、发布、截止时间和关闭状态
- 问卷链接分享
- 单选题、多选题、文本填空题和数字填空题
- 必答、选择数量、文本长度、数值范围和整数校验
- 根据单选、多选或数字答案跳转到后续题目
- 登录后填写、匿名答卷和重复填写次数限制
- 单选及多选计数、文本回答列表、数字平均值
- 整份问卷统计、单题统计和分页答卷查询
- MongoDB BSON 校验器和必要索引

## 技术栈

- Python 3.11+
- FastAPI
- PyMongo
- MongoDB
- Argon2 密码哈希
- 原生 HTML、CSS 和 JavaScript

## 项目结构

```text
app/
├─ main.py          # FastAPI 应用入口
├─ auth.py          # 注册、登录和退出
├─ security.py      # 密码哈希、签名令牌和鉴权
├─ database.py      # MongoDB 连接及结构检查
├─ models.py        # 请求模型和题目配置校验
├─ surveys.py       # 问卷、题目、规则、发布和关闭
├─ filling.py       # 问卷读取、答卷提交和次数控制
├─ engine.py        # 答案校验和跳转路径计算
├─ statistics.py    # 整卷、单题和答卷统计
└─ static/
   └─ index.html    # 中文操作页面

tests/              # 单元测试和 MongoDB 集成测试
init_database.js    # 集合、校验器和索引初始化脚本
requirements.txt    # Python 依赖
API.md              # API 说明
DATABASE_SETUP.md   # 数据库初始化说明
DESIGN.md           # 数据库和业务设计
TEST_CASES.md       # 测试用例
TEST_RESULTS.md     # 已执行的测试结果
```

## 安装

准备以下环境：

- Python 3.11 或更高版本
- MongoDB 服务
- MongoDB Shell，即 `mongosh`

克隆项目后进入项目目录，在已有虚拟环境中安装依赖：

```powershell
python -m pip install -r requirements.txt
```

如果尚未创建虚拟环境，可以自行使用 `venv`、Conda 或其他 Python 环境管理工具。

## 初始化数据库

默认连接本机 MongoDB，数据库名为 `survey_project1_1`：

```powershell
mongosh "mongodb://127.0.0.1:27017" --file ".\init_database.js"
```

脚本会创建以下集合：

```text
users
surveys
questions
responses
```

同时会配置字段校验器和索引，但不会插入示例用户或问卷。脚本不会删除已有数据；如果目标集合已经包含数据或校验规则，会停止并要求人工检查。

更详细的说明见 [DATABASE_SETUP.md](DATABASE_SETUP.md)。

## 配置

程序通过环境变量读取配置。`.env.example` 只用于说明，程序不会自动加载该文件。

PowerShell 示例：

```powershell
$env:MONGO_URI = 'mongodb://127.0.0.1:27017'
$env:MONGO_DATABASE = 'survey_project1_1'
$env:APP_ORIGIN = 'http://127.0.0.1:8001'
$env:JWT_SECRET = (& python -c 'import secrets; print(secrets.token_urlsafe(48))')
$env:COOKIE_SECURE = 'false'
```

`JWT_SECRET` 至少需要 32 个字符。生产环境应安全保存一个固定值；更换该值会使现有登录状态失效。使用 HTTPS 时应设置：

```powershell
$env:COOKIE_SECURE = 'true'
```

不要把包含真实密码或密钥的 `.env` 文件提交到 Git。

## 启动

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

打开以下地址：

- 操作页面：<http://127.0.0.1:8001/>
- OpenAPI 文档：<http://127.0.0.1:8001/docs>
- 健康检查：<http://127.0.0.1:8001/health>

浏览器地址必须与 `APP_ORIGIN` 保持一致。例如配置为 `127.0.0.1` 时，不要改用 `localhost` 打开页面。

## 基本使用流程

1. 注册账号并登录。
2. 创建问卷草稿，填写标题和说明。
3. 设置匿名方式、开始和截止时间以及每人填写次数。
4. 添加单选、多选、文本或数字题，并设置对应校验条件。
5. 根据需要添加条件跳转规则。
6. 发布问卷，将生成的链接发送给填写者。
7. 填写者登录后完成并提交问卷。
8. 创建者查看整份问卷及各题统计，或关闭问卷。

问卷发布后会冻结题目、顺序、跳转规则、匿名方式和填写次数限制，以保证已有答卷可以继续解释。发布后仍可调整截止时间或关闭问卷。

## 条件跳转

支持以下条件：

| 题型 | 条件 |
| --- | --- |
| 单选 | 等于某个选项 |
| 多选 | 包含任意指定选项、包含全部指定选项 |
| 数字 | 等于、大于、大于等于、小于、小于等于 |

第一阶段只允许跳转到后续题目或结束问卷，以避免循环。规则按列表顺序判断，第一条命中的规则生效；没有命中时进入下一题。

前端会根据答案动态显示答题路径，后端提交时会重新计算并验证路径。被跳过的必答题不需要回答，路径外答案会被拒绝。

## 匿名和填写次数

匿名表示问卷创建者看不到填写者身份。系统内部仍保存用户 ID，用于登录鉴权和填写次数控制；匿名答卷接口不会返回填写者 ID 或用户名。

系统允许不同用户并发提交。同一用户的并发请求不能突破每人填写次数限制。客户端为每次提交生成 `requestId`，相同请求的网络重试不会重复保存或重复计次。

## 测试

运行不需要 MongoDB 写入的单元测试：

```powershell
python -m unittest discover -s tests -v
```

未设置测试数据库时，MongoDB 集成测试会自动跳过。

运行完整集成测试时，应使用名称以 `survey_project1_1_test_` 开头的独立测试数据库。例如：

```powershell
mongosh "mongodb://127.0.0.1:27017" --quiet --eval "const TEST_DATABASE_NAME='survey_project1_1_test_local'; load('init_database.js');"

$env:MONGO_URI = 'mongodb://127.0.0.1:27017'
$env:TEST_MONGO_DATABASE = 'survey_project1_1_test_local'
python -m unittest discover -s tests -v
```

测试结束后确认名称无误，再删除测试数据库：

```powershell
mongosh "mongodb://127.0.0.1:27017/survey_project1_1_test_local" --quiet --eval "if (db.getName() !== 'survey_project1_1_test_local') throw new Error('Unexpected database'); db.dropDatabase();"
```

当前自动测试覆盖注册登录、权限、四种题型、条件跳转、匿名、时间窗口、幂等提交、统计和并发次数限制。详细结果见 [TEST_RESULTS.md](TEST_RESULTS.md)。

## API 和设计文档

- [API.md](API.md)：接口路径、请求结构和返回约定
- [DESIGN.md](DESIGN.md)：集合划分、索引、跳转和一致性设计
- [DATABASE_SETUP.md](DATABASE_SETUP.md)：数据库初始化和检查方法
- [TEST_CASES.md](TEST_CASES.md)：功能及边界测试用例

## 当前限制

- 仅允许向后跳转，不支持循环跳转。
- 不保存尚未提交的填写草稿。
- 已发布问卷不支持修改题目结构。
- 本项目面向本地运行和教学示例，生产部署还需要 HTTPS、登录限速、日志、备份及监控等配置。

# AI 简历优化器（Web MVP）

[![CI](https://github.com/td910856-rgb/lyp-s-creations/actions/workflows/ci.yml/badge.svg)](https://github.com/td910856-rgb/lyp-s-creations/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **在线体验**：<https://ai-resume-optimizer-ocde.onrender.com>
> （免费实例，第一次打开要等十几秒唤醒；站点不提供模型密钥，使用前需在页面里填自己的 API Key）

上传一份 PDF / Word 简历，输入目标岗位，得到：

- 总体匹配度、技能匹配度、项目匹配度（三个分数）
- 岗位关键词缺失情况
- 逐条简历修改建议
- 一份优化后的简历文本
- 联网采集这个岗位的真实招聘要求，作为打分依据（而不是只靠你填的岗位名称）
- 直接粘贴完整岗位 JD，用它来打分（最准，不需要联网）
- 把优化后的简历导出成 Word，或按 A4 排版打印成 PDF
- 预测面试官可能追问的 6~8 个问题，附答题思路
- 同一份简历、同一个岗位的多次分析会显示「比上次 +N 分」
- 已上传的简历可以切换复用，历史记录可以删除

技术栈：React（前端） + FastAPI（后端） + SQLite（数据库） + 大模型 API（可换服务商）。

## 用 Docker 一条命令跑起来

```bash
git clone https://github.com/td910856-rgb/lyp-s-creations.git
cd lyp-s-creations
cp backend/.env.example backend/.env   # 然后按需修改
docker compose up --build
```

打开 <http://localhost:8000> 就是完整产品（前端打包后由后端托管）。
想部署成公开网站，看 [DEPLOY.md](DEPLOY.md)。

---

## 一、快速开始

需要先装好 **Python 3.10+** 和 **Node.js 18+**。在命令行里执行
`python --version` 和 `node --version`，能打印出版本号即可。

### 第 1 步：启动后端（开一个命令行窗口）

```bash
cd ai-resume-optimizer/backend
python -m venv .venv
.venv\Scripts\activate          # Mac / Linux 用: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # Mac / Linux 用: cp .env.example .env
python -m uvicorn app.main:app --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000` 就成功了。
这个窗口**不要关**，关掉后端就停了。

### 第 2 步：启动前端（再开一个命令行窗口）

```bash
cd ai-resume-optimizer/frontend
npm install
npm run dev
```

浏览器会自动打开 <http://localhost:5173>。

### 第 3 步：先用演示模式跑一遍

仓库里的 `.env` 默认是 **`LLM_MOCK=1`（演示模式）**：
不调用真实模型、不花钱，返回的是示例数据，但完整流程能跑通。

先上传 `examples/sample_resume.txt`，岗位填「字节跳动 AI 算法实习生」，
点「开始分析」，看看结果长什么样。

---

## 二、接入真实模型

打开 `backend/.env`，填三行，然后**重启后端**：

```ini
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_MOCK=0
```

常见服务商的填写方式：

| 服务商 | LLM_BASE_URL | LLM_MODEL 示例 |
|---|---|---|
| OpenRouter（有免费模型） | `https://openrouter.ai/api/v1` | `qwen/qwen3.8-27b:free` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 本地 Ollama（不联网） | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` |

免费的怎么选：

- **OpenRouter**：注册一个账号就能用多家模型，带 `:free` 后缀的模型不花钱
  （去 <https://openrouter.ai/models?max_price=0> 挑，中文建议用 Qwen 系）。
  免费模型有频率限制，具体以官网为准。
- **本地 Ollama**：完全免费、不用联网、不限次数，但要占几个 GB 硬盘，
  而且小模型的改简历质量明显不如云端模型。只适合先把流程跑通。

注意：

- 密钥只写在 `.env` 里。`.env` 已经被 `.gitignore` 排除，不会被提交到 Git。
- 前端「运行状态」面板会显示当前是「演示数据」还是「真实模型」，
  以及用的哪个模型，方便确认配置有没有生效。
- 分析一次大概消耗几千个 token，用便宜的小模型就够。

---

## 三、联网采集最新岗位信息

只填一个岗位名称，模型其实不知道这个岗位到底要什么，打分只能靠印象。
所以分析前会先去网上抓这个岗位的真实要求，一起交给模型。

工作方式（全过程只用 Python 标准库，没有额外依赖）：

1. 用「岗位名称 + 岗位职责 + 任职要求」去搜索；
2. 优先采用招聘网站的结果（Boss直聘、猎聘、实习僧、牛客、公司招聘官网等）；
3. 并发抓取前 2 个页面，正文里必须出现「岗位职责 / 任职要求」这类词才算有效，
   失效页面和纯公司介绍页会被丢掉；
4. 抓到的内容拼成「岗位要求参考」塞进提示词，提示词里也明确告诉模型这部分可能有噪音。

在 `.env` 里可以调整：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `WEB_SEARCH_ENABLED` | `1` | 关掉就只用岗位名称分析 |
| `WEB_SEARCH_PROVIDER` | `auto` | `auto` = 先 DuckDuckGo 再 Bing；也可写死 `bing` |
| `WEB_SEARCH_MAX_RESULTS` | `5` | 取几条搜索结果 |
| `WEB_FETCH_PAGES` | `2` | 最多抓几个页面，越多越慢 |
| `WEB_TIMEOUT` | `12` | 单个网页的超时秒数 |
| `WEB_MAX_CHARS` | `3000` | 送给模型的参考材料最长多少字 |

几个实用细节：

- **同一个岗位 30 分钟内复用上次的采集结果**，不会重复打搜索接口、也不会被限流。
- 页面上那个「联网采集最新岗位信息」勾选框可以临时关闭它，关掉后分析快很多。
- 采集失败（网络不通、被网站拦截）不会让分析失败，只会退回「仅按岗位名称分析」，
  结果里会写清楚原因，并列出它找到的页面链接。

## 四、项目结构

```
ai-resume-optimizer/
├─ backend/                     后端（FastAPI）
│  ├─ app/
│  │  ├─ main.py                应用入口、健康检查、托管前端打包结果
│  │  ├─ config.py              集中读取 .env，密钥只从这里进程序
│  │  ├─ database.py            SQLite 连接
│  │  ├─ models.py              两张表：resumes、analyses
│  │  ├─ schemas.py             接口的请求 / 响应结构
│  │  ├─ routers/               接口层（只负责收参数、返回结果）
│  │  ├─ services/              业务层
│  │  │  ├─ file_parser.py      PDF / Word / TXT 转纯文本
│  │  │  ├─ prompts.py          提示词模板
│  │  │  ├─ llm_client.py       全项目唯一调用大模型的地方
│  │  │  └─ analyzer.py         结果归一化 + 落库
│  │  └─ .env                   你的密钥（不提交）
│  ├─ uploads/                  上传的原始文件
│  └─ resume.db                 SQLite 数据库文件
├─ frontend/                    前端（React + Vite）
│  └─ src/
│     ├─ App.jsx                页面主流程
│     ├─ api.js                 所有后端请求集中在这里
│     ├─ styles.css             手写样式
│     └─ components/            上传框、分数卡、结果面板、简历预览
└─ examples/sample_resume.txt   测试用简历
```

---

## 五、接口一览

后端启动后，打开 <http://127.0.0.1:8000/docs> 可以直接在网页上点着测接口。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务状态、模型是否配置好 |
| POST | `/api/resumes/upload` | 上传简历，返回提取出的文字 |
| GET | `/api/resumes` | 已上传的简历列表（用于切换） |
| POST | `/api/analyses` | 传 `resume_id` + `job_title`，执行分析 |
| GET | `/api/analyses` | 最近的分析记录 |
| GET | `/api/analyses/{id}` | 读取某一条分析结果 |
| DELETE | `/api/analyses/{id}` | 删除一条分析记录 |
| GET | `/api/analyses/{id}/export.docx` | 把优化后的简历导出成 Word |

发起分析时还可以带上两个可选参数：

- `job_description`：直接粘贴的岗位 JD。填了就以它为准，不再联网采集。
- 页面上勾掉「联网采集」等于传 `use_web: false`，只用岗位名称分析。

网页地址后面可以加参数直接打开某次结果：`?analysis=11`（结果 ID），
再加 `&theme=dark` 就是深色模式。

---

## 六、怎么测试

按顺序试这几件事，能覆盖绝大多数问题：

1. **正常流程**：上传 `examples/sample_resume.txt`，岗位填「字节跳动 AI 算法实习生」，点分析。
2. **Word 简历**：把自己的 `.docx` 简历传上去，看「已提取文字 N 字」的预览对不对。
3. **PDF 简历**：同上。如果是扫描件（图片版），会提示读不出文字，这是正常的。
4. **错误格式**：随便传一个 `.doc` 或图片，应该提示「不支持的格式」。
5. **断言后端**：直接访问 <http://127.0.0.1:8000/api/health>，应返回 `"status": "ok"`。
6. **换岗位**：同一个简历换「前端开发实习生」，分数和缺失关键词应该跟着变。
7. **历史记录**：左侧「最近的分析」可以点开之前的结果（刷新页面也还在）。

---

## 七、出错了怎么办

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面提示「连不上后端服务」 | 后端没启动或已关闭 | 看后端窗口是否还在运行；重新执行启动命令 |
| 页面一片空白 | 前端报错了 | 按 F12 打开控制台看红色报错；确认 `npm install` 跑完了 |
| 「还没有配置模型密钥」 | `.env` 没填 key，且不是演示模式 | 填 `LLM_API_KEY`，或把 `LLM_MOCK` 临时改成 1 |
| 「模型接口返回错误（HTTP 401）」 | 密钥不对 | 检查 `LLM_API_KEY` 有没有多余空格 |
| 「模型接口返回错误（HTTP 404）」 | 接口地址不对 | 检查 `LLM_BASE_URL`，注意结尾要有 `/v1` |
| 「连接模型接口失败或超时」 | 网络问题或地址写错 | 检查网络和 `LLM_BASE_URL`；慢的话把 `LLM_TIMEOUT` 调大 |
| 「这份文件里几乎读不出文字」 | 扫描件 PDF、或者简历是图片 | 换文字版 PDF，或把内容存成 `.txt` 上传 |
| 「模型返回的内容不是合法 JSON」 | 小模型不太听话 | 再点一次；或换一个更强的 `LLM_MODEL` |
| 端口被占用（Address already in use） | 上一次没关干净 | 换端口：`--port 8001`；前端代理地址也要跟着改 |
| 想清空所有数据 | — | 删掉 `backend/resume.db` 和 `backend/uploads/` 里的文件，重启后端会自动重建 |

---

## 八、几个设计上的取舍（写给想搞懂原理的你）

1. **一次调用拿全部结果。**
   不是让模型回答 6 个问题，而是让它一次返回一个固定结构的 JSON。
   省时间、省费用，6 个分数之间也不会自相矛盾。

2. **模型输出要当作不可信输入。**
   `analyzer.py` 会把分数夹到 0–100、把 `"71分"`、`0.74` 这类值统一成整数、
   给缺字段补默认值。模型偶尔抽风时，前端也不会白屏。

3. **模型可能返回不合法 JSON。**
   `llm_client.py` 会先尝试从 ``` 代码块里抠出 JSON，
   失败就把模型自己的回答塞回去，让它重写一次。

4. **只有一个文件接触大模型。**
   想换服务商、加缓存、换成本地模型，只需要改 `llm_client.py`。

5. **分数单独成列，其余塞进 JSON 字段。**
   `analyses` 表里三个分数是独立字段（方便以后排序对比），
   缺失关键词、建议、优化后的简历都放在 `details` 这个 JSON 字段里，
   避免为了加一个小字段就去改表结构。

6. **没装第三方 HTTP 库。**
   调用大模型只用 Python 标准库 `urllib`，
   因为需求就是「发一个 JSON、收一个 JSON」，没必要为此多装一个包。

---

## 九、接着可以做什么

按性价比排序，都适合拿来练手：

1. 给「优化后的简历」加导出 Word / PDF。
2. 支持扫描件 PDF（接一个 OCR）。
3. 把岗位 JD 变成一个大输入框，直接粘贴完整招聘描述，分析会更准。
4. 加一个「历史结果对比」，看改完简历后分数涨了多少。
5. 加上用户登录，让简历在账号之间同步。

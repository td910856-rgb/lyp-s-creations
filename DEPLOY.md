# 部署成公开网站

这份文档把项目从"我电脑上能跑"变成"所有人都能访问"。

## 一、先想清楚：模型的钱谁来出

项目支持两种模式，上线前必须先选：

| 模式 | 谁付钱 | 适合 |
|---|---|---|
| 服务端配置密钥 | 你，按量付费 | 小范围分享、内部使用 |
| **访客自带密钥（BYOK）** | 访客自己 | **公开开源部署，推荐** |

BYOK 模式下，访客在页面「设置与隐私 → 模型设置」里填自己的 API Key。
密钥只存在访客浏览器的 localStorage，每次请求临时带上，服务端不保存、不写日志。

想强制 BYOK，把 `.env` 里改成：

```ini
REQUIRE_OWN_KEY=1
LLM_MOCK=0
LLM_API_KEY=
```

这样服务器不再垫付任何模型费用，你只承担服务器的钱（免费额度足够）。

## 二、用 Docker 跑（本地验证部署形态）

```bash
cp backend/.env.example backend/.env
# 按需修改 backend/.env
docker compose up --build
```

打开 <http://localhost:8000> 即可。数据（SQLite 和上传文件）落在 `./data`，容器重建不会丢。

## 三、部署到 Render（免费，推荐先这样上线）

### 最省事的走法：用 Blueprint

仓库根目录里有 `render.yaml`，Render 能直接读它建服务：

1. 打开 <https://dashboard.render.com/blueprints>
2. 点 **New Blueprint Instance**
3. 选 `lyp-s-creations` 这个仓库，点 **Apply**
4. 等两三分钟构建完成，就能拿到 `https://xxx.onrender.com`

环境变量、健康检查路径、Docker 配置都写在 `render.yaml` 里了，不用手填。

### 手动建服务（想自己控制每个选项时用）

1. 把代码推到 GitHub（见 README 的「开源到 GitHub」一节）
2. 打开 <https://render.com>，用 GitHub 账号登录
3. New → **Web Service** → 选择你的仓库
4. 关键设置：
   - Language / Runtime：**Docker**
   - Instance Type：**Free**
   - Health Check Path：`/api/health`
5. 在 **Environment** 里加变量：

   ```ini
   LLM_MOCK=0
   REQUIRE_OWN_KEY=1
   DATA_RETENTION_HOURS=72
   RATE_LIMIT_PER_DAY=10
   RATE_LIMIT_GLOBAL_PER_DAY=500
   DATABASE_URL=sqlite:////data/resume.db
   UPLOAD_DIR=/data/uploads
   ```

6. 部署完成后会给你一个 `https://xxx.onrender.com` 的地址，直接就能分享

注意：免费实例一段时间没人访问会休眠，第一次打开要等十几秒唤醒，这是正常的。

**数据持久化**：免费实例的本地磁盘在重建时会清空。如果在意历史数据，
在 Render 上挂一个 Disk（挂载到 `/data`），或者接受"数据会丢"（反正有自动清理）。

## 四、其他平台

- **Railway**：同样支持 Dockerfile，流程和 Render 类似，免费额度按月计
- **Fly.io**：`fly launch` 会自动识别 Dockerfile，需要绑定信用卡
- **国内轻量服务器**：访问最快，但**域名指向国内服务器必须 ICP 备案**，
  流程几天到两周，且对个人网站内容有要求。不备案只能 IP + 端口访问。
- **Hugging Face Spaces**：可以跑，但资源小、会休眠，国内访问一般

## 五、上线前的检查清单

- [ ] `.env` 没有提交到 Git（`.gitignore` 已经排除，确认一下）
- [ ] `REQUIRE_OWN_KEY=1`，或者给 `RATE_LIMIT_*` 设了合理的小数字
- [ ] `DATA_RETENTION_HOURS` 不为 0（简历是别人的个人信息，别无限期保存）
- [ ] 页面上有隐私说明（已有：「设置与隐私」里写了保留时长和额度）
- [ ] 访问 `/api/health` 返回 `status: ok`
- [ ] 自己完整跑一遍：上传 → 分析 → 下载 Word

## 六、域名（可选）

不买域名也能用平台给的地址。要买的话：

1. 买域名（阿里云/腾讯云/Cloudflare 都行，几十块一年）
2. 在平台里绑定自定义域名，按提示把 DNS 记录指过去
3. 平台会自动签发 HTTPS 证书

## 七、出问题怎么查

| 现象 | 看哪里 |
|---|---|
| 部署失败 | 平台上的构建日志，通常是依赖装不上 |
| 打开很慢 | 免费实例休眠唤醒，等十几秒 |
| 分析报错 | 平台的运行日志；BYOK 模式下多半是访客密钥填错 |
| 数据没了 | 容器重建且没挂持久卷，属预期行为 |
| 被人刷 | 调小 `RATE_LIMIT_PER_DAY` / `RATE_LIMIT_GLOBAL_PER_DAY` |

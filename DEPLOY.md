# 部署指南（让别人可访问）

## 你现在具备的部署能力

项目已支持：
- 生产启动（Gunicorn）
- Docker 部署
- 密钥通过环境变量注入（不再写死在代码里）

## 方案一：Render（推荐，最省事）

1. 把 `models/ChildrenConflictProject` 上传到 GitHub 仓库。
2. 打开 [Render](https://render.com/) 并登录。
3. 选择 **New +** -> **Blueprint**，连接你的仓库。
4. Render 会读取项目中的 `render.yaml` 并创建 Web Service。
5. 在环境变量里填写：
   - `OPENAI_API_KEY` = 你的智谱/兼容 OpenAI 的 key
   - `OPENAI_BASE_URL`（可选，默认已配置）
   - `OPENAI_MODEL`（可选，默认 `glm-4-flash`）
6. 点击 Deploy，等待构建完成。
7. 构建成功后，你会得到一个 `https://xxx.onrender.com` 地址，别人直接访问即可。

## 方案二：任意支持 Docker 的平台

例如 Railway、Fly.io、阿里云容器服务、腾讯云轻量应用服务器等。

关键点：
- 使用项目内 `Dockerfile`
- 暴露端口：`5000`
- 必填环境变量：`OPENAI_API_KEY`

## 本地先验证 Docker

```bash
docker build -t children-conflict .
docker run -p 5000:5000 -e OPENAI_API_KEY=你的key children-conflict
```

浏览器打开 `http://localhost:5000`，确认功能正常后再推到云平台。

## 安全建议

- 你之前的 API Key 曾出现在代码中，建议立即去平台后台轮换（重置）这个 key。
- 以后统一使用环境变量，不要把密钥提交到仓库。

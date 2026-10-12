# EchoMind

面向客服与运营场景的多 Agent 系统，包含 Python 后端和 Vue 前端。

## 目录

- `EchoMind/`：FastAPI、Agent 编排、RAG、记忆、Skills、监控和评测。
- `EchoMindFrontend/`：Vue 控制台、知识库管理及运行状态展示。
- [后端说明](EchoMind/README.md)、[前端说明](EchoMindFrontend/README.md)。

## 启动完整项目

需要 Docker 和 Docker Compose。在仓库根目录执行：

```bash
cp .env.example .env
```

在本地 `.env` 中填写 `ANTHROPIC_API_KEY` 和 `REDIS_PASSWORD`。可用 `openssl rand -hex 24` 生成 Redis 密码。按模型供应商配置 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_MODEL`。

```bash
docker compose --env-file .env -f EchoMindFrontend/docker-compose.yml up -d --build
```

访问控制台：<http://localhost>；API 文档：<http://localhost:8000/docs>。也可以通过 <http://localhost:5174> 访问前端。

停止服务：

```bash
docker compose --env-file .env -f EchoMindFrontend/docker-compose.yml down
```

后端单独部署可按 [后端说明](EchoMind/README.md) 在 `EchoMind/` 内配置 `.env` 后启动；两套部署请择一运行。

## 配置与数据

密钥仅通过本地环境变量提供；提交的 `.env.example` 不含有效凭据。不要把模型密钥放入前端 `VITE_` 变量，前端变量会进入浏览器代码。

首次部署时数据库为空，需要自行导入知识库。

默认部署供本地开发与演示使用；访问控制需按实际部署环境另行配置。

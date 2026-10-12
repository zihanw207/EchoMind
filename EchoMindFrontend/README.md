# EchoMind Frontend

Vue 控制台，连接同一仓库中的 EchoMind Python 后端。支持聊天调试、健康检查、监控摘要、知识库检索、文档导入与上传。

## 本地开发

先启动 Python 后端，再在本目录执行：

```bash
npm ci
npm run dev
```

访问 <http://localhost:5173>。Vite 将 `/api/python` 请求代理到 `http://localhost:8000`。

若后端地址不同，可通过 `VITE_PYTHON_API_URL` 配置开发代理目标：

```bash
VITE_PYTHON_API_URL=http://localhost:8000 npm run dev
```

前端只访问后端，不应配置模型 API 密钥；所有 `VITE_` 变量都可能暴露在浏览器代码中。

## Docker 部署

从仓库根目录按 [启动说明](../README.md) 配置 `.env`，再执行：

```bash
docker compose --env-file .env -f EchoMindFrontend/docker-compose.yml up -d --build
```

包含 Python、Redis、ChromaDB、前端和 Nginx；不依赖 Java 项目。访问 <http://localhost> 或 <http://localhost:5174>。

## 构建

```bash
npm run build
```

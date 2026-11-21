# EchoMind

EchoMind 是一个面向客服/运营场景的多 Agent 智能系统。它不是单纯的聊天机器人，而是把以下能力串成闭环：

- 细粒度意图识别
- 路由驱动的多 Agent 编排
- 意图驱动 RAG 检索
- Redis + ChromaDB 分层记忆
- 动态 Skills 注入
- 在线监控与路由降权
- LLM-as-Judge 端到端评测

## 快速开始

### 1. 准备环境

- Docker
- Docker Compose
- `ANTHROPIC_API_KEY`

如果使用兼容 Anthropic 协议的第三方模型服务，也可以配置：

```env
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_MODEL=deepseek-v4-pro
ANTHROPIC_API_KEY=your_key
```

### 2. 配置环境变量

复制示例配置：

```bash
cp .env.example .env
```

最少确认这些变量可用：

```env
ANTHROPIC_API_KEY=your_api_key
REDIS_PASSWORD=your-redis-password
```

### 3. 启动服务

推荐直接启动全栈：

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

看日志：

```bash
docker compose logs -f echomind
```

### 4. 访问入口

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Nginx: `http://localhost`
- Health: `http://localhost:8000/health`

## 核心功能

### 对话主链路

`POST /chat`

流程是：

```text
读取记忆 -> 意图识别 -> 知识检索 -> Agent 路由 -> 回复生成 -> 写回记忆
```

### Jev 路由实验

在用于启动服务的 `.env` 中填写 `TYPESAFE_API_KEY`。这个配置会把本轮消息和最多五条最近对话发送给 TypeSafe，在一次请求中判断技术、账单和转人工三项。`ANTHROPIC_API_KEY` 仍用于生成 Agent 回复和汇总结果。 [Jev API 文档](https://docs.typesafe.ai/primitives/noul)

| Jev 判定 | 派发 |
| --- | --- |
| 转人工达到阈值 | 直接进入 `EscalationAgent`，生成交接信息并标记升级。实际人工队列或工单系统需要另行接入。 |
| 技术和账单均达到阈值 | 两个 Agent 平级并行，汇总器按用户优先级和问题顺序组织回复。 |
| 只有技术或账单达到阈值 | 派给对应的专业 Agent。 |
| 三项均未达到阈值 | 调用 `GeneralAgent` 直接回答或追问。 |

三个阈值默认是 `0.5`，可分别用 `ECHOMIND_JEV_TECHNICAL_THRESHOLD`、`ECHOMIND_JEV_BILLING_THRESHOLD`、`ECHOMIND_JEV_HANDOFF_THRESHOLD` 调整。可用 `ECHOMIND_JEV_MODEL` 指定模型版本。`/chat` 的 `intent_source_scores` 会列出三个 Jev 概率。未配置密钥或 Jev 请求失败时，服务使用原有意图路由。

### 知识库

- `POST /search`
- `POST /knowledge/add`
- `POST /knowledge/upload`
- `GET /knowledge/stats`

### Skills

- `GET /skills`
- `POST /skills/reload`

### 监控与评测

- `GET /monitor`
- `POST /eval/run`

## 项目结构

```text
api/main.py                  FastAPI 入口
agents/agent_orchestrator.py 多 Agent 编排
core/intent_recognizer.py    三路融合意图识别
core/skill_loader.py         动态 Skills 加载
memory/conversation_memory.py  Redis + ChromaDB 记忆
mcp/tool_manager.py          工具层、缓存、熔断、重排
mcp/knowledge_base.py        ChromaDB 知识库
monitor/performance_monitor.py 在线监控
evaluation/evaluator.py      端到端评测
skills/                     动态业务规则
data/                       持久化数据
```

## 运行时架构

```text
用户请求
  -> /chat
  -> MemoryManager 读取工作记忆、情景记忆、用户画像
  -> IntentRecognizer 输出 intent / intent_group / urgency / entities
  -> 按意图决定是否检索知识库
  -> AgentOrchestrator 路由到 General / Technical / Billing / Escalation
  -> Skills 注入、工具调用、回复生成
  -> 写回 Redis 和 ChromaDB
  -> Monitor 采集在线指标
  -> Evaluator 做意图识别和回复质量评测
```

## 主要端口

| 服务 | 端口 |
|---|---:|
| EchoMind API | 8000 |
| ChromaDB | 8001 |
| Redis | 6379 |
| Prometheus | 9090 |
| Nginx | 80 |

## 开发和调试

常用顺序：

```text
1. /health
2. /chat
3. /skills
4. /monitor
5. /eval/run
```

## 一句话概括

EchoMind 是一个可观测、可评测、可降级的多 Agent 客服运行时。

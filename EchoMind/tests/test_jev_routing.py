import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from agents import agent_orchestrator
from agents.agent_orchestrator import AgentOrchestrator, AgentResponse, AgentStats, AgentType, Request


TECHNICAL = AgentType.TECHNICAL
BILLING = AgentType.BILLING
ESCALATION = AgentType.ESCALATION
GENERAL = AgentType.GENERAL


@pytest.fixture
def orchestrator(monkeypatch):
    monkeypatch.setenv("no_proxy", "*")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    for name in ("TECHNICAL", "BILLING", "HANDOFF"):
        monkeypatch.setenv(f"ECHOMIND_JEV_{name}_THRESHOLD", "0.5")
    return AgentOrchestrator(api_key="test-key")


def set_noul_answers(orchestrator, technical, billing, handoff):
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.typesafe.ai/v1/systemone"),
        json={"answers": {
            "technical": {"type": "noul", "noul": technical},
            "billing": {"type": "noul", "noul": billing},
            "handoff": {"type": "noul", "noul": handoff},
        }},
    )
    orchestrator._jev_router._client.post = AsyncMock(return_value=response)
    return orchestrator._jev_router._client.post


@pytest.mark.parametrize("technical,billing,handoff,expected", [
    (0.1, 0.1, 0.1, [GENERAL]),
    (0.5, 0.1, 0.1, [TECHNICAL]),
    (0.1, 0.5, 0.1, [BILLING]),
    (0.9, 0.5, 0.1, [TECHNICAL, BILLING]),
    (0.1, 0.1, 0.5, [ESCALATION]),
    (0.9, 0.1, 0.5, [ESCALATION]),
    (0.1, 0.9, 0.5, [ESCALATION]),
    (0.9, 0.9, 0.5, [ESCALATION]),
])
def test_jev_routes_all_noul_combinations(orchestrator, technical, billing, handoff, expected):
    post = set_noul_answers(orchestrator, technical, billing, handoff)
    compose = AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text="已合并")]))
    orchestrator._composer._client = SimpleNamespace(messages=SimpleNamespace(create=compose))

    handlers = {}
    for agent_type in (GENERAL, TECHNICAL, BILLING):
        handler = AsyncMock(return_value=AgentResponse(agent_type, f"{agent_type.value} 答复", True))
        orchestrator._pool[agent_type] = [SimpleNamespace(handle=handler, stats=AgentStats())]
        handlers[agent_type] = handler

    req = Request("登录报 401，扣款 99 元", "u1", "c1", history=[{"role": "user", "content": "先看账单"}])

    async def run():
        try:
            return await orchestrator.run(req)
        finally:
            await orchestrator.close()

    result = asyncio.run(run())
    post.assert_awaited_once()
    payload = post.call_args.kwargs["json"]
    assert payload["state"] == {"message": req.message, "recent_history": req.history}
    assert set(payload["questions"]) == {"technical", "billing", "handoff"}
    assert all(question["type"] == "noul" for question in payload["questions"].values())
    assert result.agent_types == expected
    assert result.routing_source == "jev"
    assert result.escalated is (expected == [ESCALATION])
    assert req.entities["error_code"] == ["401"]
    for agent_type, handler in handlers.items():
        assert handler.await_count == int(agent_type in expected)

    if len(expected) == 2:
        assert result.primary_agent is None and result.supporting_agents == []
        compose.assert_awaited_once()
        prompt = compose.call_args.kwargs["messages"][0]["content"]
        assert "逐项覆盖" in prompt and "主 Agent" not in prompt
    else:
        compose.assert_not_awaited()


@pytest.mark.parametrize("failure", ["invalid_response", "http_error", "timeout"])
def test_jev_failures_call_general_directly(orchestrator, monkeypatch, failure):
    if failure == "invalid_response":
        post = set_noul_answers(orchestrator, 0.9, 0.9, "not a probability")
    elif failure == "http_error":
        request = httpx.Request("POST", "https://api.typesafe.ai/v1/systemone")
        post = AsyncMock(return_value=httpx.Response(503, request=request))
    else:
        async def slow_request(*args, **kwargs):
            await asyncio.sleep(10)

        monkeypatch.setattr(agent_orchestrator, "JEV_ROUTING_TIMEOUT_SECONDS", 0.01)
        post = AsyncMock(side_effect=slow_request)
    orchestrator._jev_router._client.post = post

    general = AsyncMock(return_value=AgentResponse(GENERAL, "请问是登录还是账单问题？", True))
    orchestrator._pool[GENERAL] = [SimpleNamespace(handle=general, stats=AgentStats())]
    req = Request(
        "登录报错 401，还被重复扣款", "u1", "c1",
        history=[{"role": "user", "content": "我刚才在 App 操作"}],
    )

    async def run():
        try:
            return await orchestrator.run(req)
        finally:
            await orchestrator.close()

    result = asyncio.run(run())
    post.assert_awaited_once()
    general.assert_awaited_once_with(req)
    assert result.agent_types == [GENERAL]
    assert result.response == "请问是登录还是账单问题？"
    assert result.routing_source == "general_fallback"
    assert ("超时" if failure == "timeout" else "失败") in result.routing_reason
    assert req.intent_source_scores == {}
    assert orchestrator.get_tool_trace(req.request_id)["routing_source"] == "general_fallback"


def test_without_jev_key_calls_general_directly(monkeypatch):
    monkeypatch.setenv("no_proxy", "*")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    orchestrator = AgentOrchestrator(api_key="test-key")
    general = AsyncMock(return_value=AgentResponse(GENERAL, "请告诉我你想问什么。", True))
    orchestrator._pool[GENERAL] = [SimpleNamespace(handle=general, stats=AgentStats())]

    result = asyncio.run(orchestrator.run(Request("你好", "u1", "c1")))
    general.assert_awaited_once()
    assert result.agent_types == [GENERAL]
    assert result.routing_source == "general_fallback"
    assert "未配置 Jev 密钥" in result.routing_reason


def test_chat_all_negative_calls_general_and_exposes_jev_scores(orchestrator, monkeypatch):
    from api import main

    post = set_noul_answers(orchestrator, 0.1, 0.2, 0.3)
    general = AsyncMock(return_value=AgentResponse(GENERAL, "你想咨询哪件事？", True))
    orchestrator._pool[GENERAL] = [SimpleNamespace(handle=general, stats=AgentStats())]
    memory = SimpleNamespace(
        get_context=AsyncMock(return_value=SimpleNamespace(recent_messages=[], to_prompt_text=lambda: "")),
        add_message=AsyncMock(),
        update_profile=AsyncMock(),
    )
    monkeypatch.setattr(main, "_orchestrator", orchestrator)
    monkeypatch.setattr(main, "_memory", memory)

    async def run():
        try:
            return await main.chat(main.ChatRequest(message="这个怎么弄", conv_id="c1"))
        finally:
            await orchestrator.close()

    response = asyncio.run(run())
    post.assert_awaited_once()
    general.assert_awaited_once()
    assert response.response == "你想咨询哪件事？"
    assert response.agent_types == ["general"]
    assert response.routing_source == "jev"
    assert response.intent_source_scores == {"jev_technical": 0.1, "jev_billing": 0.2, "jev_handoff": 0.3}
    assert memory.add_message.await_count == 2

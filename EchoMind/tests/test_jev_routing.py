import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from agents.agent_orchestrator import AgentOrchestrator, AgentResponse, AgentStats, AgentType, Request
from core.intent_recognizer import IntentCategory, IntentResult, UrgencyLevel


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
    orchestrator.recognize_intent = AsyncMock(side_effect=AssertionError("Unexpected legacy routing"))
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


def test_malformed_jev_response_uses_legacy_routing(orchestrator):
    set_noul_answers(orchestrator, 0.1, 0.1, "not a probability")
    orchestrator.recognize_intent = AsyncMock(return_value=IntentResult(
        intent=IntentCategory.HUMAN_HANDOFF,
        confidence=0.95,
        urgency=UrgencyLevel.HIGH,
        intent_group="escalation",
        entities={},
        reasoning="",
        latency_ms=0.0,
    ))

    async def run():
        try:
            return await orchestrator.run(Request("请转人工", "u1", "c1"))
        finally:
            await orchestrator.close()

    result = asyncio.run(run())
    orchestrator.recognize_intent.assert_awaited_once()
    assert result.agent_types == [ESCALATION]
    assert result.escalated is True


def test_chat_all_negative_calls_general_and_exposes_jev_scores(orchestrator, monkeypatch):
    from api import main

    post = set_noul_answers(orchestrator, 0.1, 0.2, 0.3)
    orchestrator.recognize_intent = AsyncMock(side_effect=AssertionError("Unexpected legacy routing"))
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
    assert response.intent_source_scores == {"jev_technical": 0.1, "jev_billing": 0.2, "jev_handoff": 0.3}
    assert memory.add_message.await_count == 2

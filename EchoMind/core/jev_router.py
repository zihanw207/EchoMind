"""Evaluate the three EchoMind routing questions in one TypeSafe request."""

import httpx


ROUTING_QUESTIONS = {
    "technical": {
        "type": "noul",
        "instructions": "根据当前消息和对话历史，用户这轮是否希望解决一个尚未处理的技术问题？",
        "criteria": {
            "true": "用户需要排查登录失败、报错、崩溃或功能故障。",
            "false": "用户只是在提及已解决的问题，或数字只是金额或订单号。",
        },
    },
    "billing": {
        "type": "noul",
        "instructions": "根据当前消息和对话历史，用户这轮是否希望解决一个尚未处理的账单或账户管理问题？",
        "criteria": {
            "true": "用户需要处理扣款、支付、退款、发票、订阅或账户资料与安全。",
            "false": "相关话题只是背景、已解决，或用户明确暂不处理。",
        },
    },
    "handoff": {
        "type": "noul",
        "instructions": "根据当前消息和对话历史，用户这轮是否希望由真人客服接手？",
        "criteria": {
            "true": "用户希望现在由真人客服或主管接手，包括用不同说法提出同一要求。",
            "false": "用户只是催促、表达不满、询问是否有人，或明确表示无需转人工。",
        },
    },
}


class JevRouter:
    def __init__(self, api_key: str, model: str, thresholds: dict[str, float]):
        for question, threshold in thresholds.items():
            if not 0.0 < threshold <= 1.0:
                raise ValueError(f"Jev threshold for {question} must be in (0, 1]")
        self._model = model
        self._thresholds = dict(thresholds)
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0,
        )

    async def assess(
        self, message: str, history: list[dict[str, str]] | None = None
    ) -> tuple[dict[str, float], set[str]]:
        response = await self._client.post(
            "https://api.typesafe.ai/v1/systemone",
            json={
                "model": self._model,
                "state": {"message": message, "recent_history": (history or [])[-5:]},
                "questions": ROUTING_QUESTIONS,
            },
        )
        response.raise_for_status()
        data = response.json()
        answers = data.get("answers") if isinstance(data, dict) else None
        if not isinstance(answers, dict):
            raise ValueError("Jev response did not include answers")

        scores: dict[str, float] = {}
        for question in ROUTING_QUESTIONS:
            answer = answers.get(question)
            if not isinstance(answer, dict) or answer.get("type") != "noul":
                raise ValueError(f"Jev did not return a Noul for {question}")
            score = answer.get("noul")
            if type(score) not in (int, float) or not 0.0 <= score <= 1.0:
                raise ValueError(f"Invalid Jev probability for {question}")
            scores[question] = float(score)

        accepted = {question for question, score in scores.items() if score >= self._thresholds[question]}
        return scores, accepted

    async def close(self) -> None:
        await self._client.aclose()

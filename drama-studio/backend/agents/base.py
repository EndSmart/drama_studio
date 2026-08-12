"""
Agent 基类。

所有智能体继承 BaseAgent，持有：
- project_id：当前项目
- llm_provider / llm：LLM 调用能力
- 统一的 run(state, config) 接口
"""

import json
import logging
from typing import Any, Dict, Optional

from ..providers.llm import LLMProvider, LLMFactory
from ..services.storage import store

logger = logging.getLogger("drama-studio.agents.base")


class BaseAgent:
    """智能体基类。"""

    name = "base"
    description = "基础智能体"

    def __init__(self, project_id: str, llm_provider: str = None, api_key: str = None):
        self.project_id = project_id
        self.llm_provider_name = llm_provider
        self._llm = None
        self._llm_api_key = api_key

    @property
    def llm(self) -> LLMProvider:
        """惰性创建 LLM provider（通过工厂按 api_style 路由）。"""
        if self._llm is None:
            self._llm = LLMFactory.create(
                provider=self.llm_provider_name, api_key=self._llm_api_key
            )
        return self._llm

    async def run(self, state: Dict, config: Dict) -> Any:
        """执行 agent 主逻辑。子类必须实现。"""
        raise NotImplementedError

    def log(self, message: str):
        store.log(self.project_id, self.name, message)
        logger.info("[%s] %s", self.name, message)

    def _safe_json(self, text: str) -> dict:
        """从 LLM 输出中提取 JSON。"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试去掉 Markdown 代码块
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                # 尝试提取花括号块
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(text[start:end + 1])
                    except json.JSONDecodeError:
                        pass
                raise ValueError(f"无法解析 JSON 输出: {text[:200]}...")

    async def chat_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """调用 LLM 并解析 JSON。"""
        text = await self.llm.chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], **kwargs)
        return self._safe_json(text)

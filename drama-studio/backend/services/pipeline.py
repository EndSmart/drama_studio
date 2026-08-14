"""
流水线编排层。

负责把用户的短剧创作请求拆解为多智能体工作流：
    director（总导演）协调 screenwriter → storyboarder → character_designer
    → video_producer → editor

每个阶段写入 project state，支持进度追踪。
"""

import asyncio
import datetime
import json
import logging
from typing import Dict, Optional, Any

from .. import config
from .storage import store

logger = logging.getLogger("drama-studio.services.pipeline")


class ProgressEmitter:
    """进度回调接口，供 WebSocket 推送到前端。"""

    def __init__(self):
        self._listeners = []

    def add_listener(self, coro):
        self._listeners.append(coro)

    async def emit(self, project_id: str, event: Dict):
        for coro in self._listeners:
            try:
                await coro(project_id, event)
            except Exception:
                pass


progress_emitter = ProgressEmitter()


class PipelineService:
    """多智能体流水线编排。"""

    def __init__(self):
        from ..agents.director import DirectorAgent
        from ..agents.screenwriter import ScreenwriterAgent
        from ..agents.storyboarder import StoryboarderAgent
        from ..agents.character_designer import CharacterDesignerAgent
        from ..agents.video_producer import VideoProducerAgent
        from ..agents.editor import EditorAgent

        self.agents = {
            "director": DirectorAgent,
            "screenwriter": ScreenwriterAgent,
            "storyboarder": StoryboarderAgent,
            "character_designer": CharacterDesignerAgent,
            "video_producer": VideoProducerAgent,
            "editor": EditorAgent,
        }
        self._running = {}  # project_id -> asyncio.Task

    async def _emit(self, project_id: str, stage: str, status: str, message: str, data: Dict = None):
        event = {"stage": stage, "status": status, "message": message, "data": data or {}}
        await progress_emitter.emit(project_id, event)

    async def run_agent(self, project_id: str, agent_name: str, llm_provider: str, api_key: str = None,
                        config_override: Dict = None) -> Any:
        """运行单个 agent。"""
        state = store.load_state(project_id)
        if not state:
            raise ValueError(f"项目不存在: {project_id}")

        agent_cls = self.agents.get(agent_name)
        if not agent_cls:
            raise ValueError(f"未知 agent: {agent_name}")

        # 注入主题（存在 meta.theme，config 本身不含）
        state = store.load_state(project_id)
        cfg = dict(config_override or {})
        if "theme" not in cfg and state:
            cfg["theme"] = (state.get("meta") or {}).get("theme", "")

        agent = agent_cls(project_id, llm_provider, api_key=api_key)
        await self._emit(project_id, agent_name, "running", f"{agent_name} 开始执行")

        # 更新状态
        state["current_stage"] = agent_name
        state["stages"][agent_name] = {"status": "running", "started_at": datetime.datetime.utcnow().isoformat()}
        store.save_state(project_id, state)

        try:
            result = await agent.run(state, config_override or {})
            state = store.load_state(project_id)
            state["stages"][agent_name] = {
                "status": "completed",
                "completed_at": datetime.datetime.utcnow().isoformat(),
                "result": result,
            }
            store.save_state(project_id, state)
            await self._emit(project_id, agent_name, "completed", f"{agent_name} 完成")
            return result
        except Exception as e:
            logger.exception("Agent %s 执行失败", agent_name)
            state = store.load_state(project_id)
            state["stages"][agent_name] = {"status": "failed", "error": str(e)}
            store.save_state(project_id, state)
            await self._emit(project_id, agent_name, "failed", str(e))
            raise

    async def run_pipeline(self, project_id: str, llm_provider: str, api_key: str = None,
                           config_override: Dict = None) -> str:
        """运行完整流水线（从编剧到成片）。"""
        if project_id in self._running and not self._running[project_id].done():
            raise ValueError("该项目已在运行中")

        task = asyncio.create_task(
            self._run_pipeline_inner(project_id, llm_provider, api_key, config_override or {})
        )
        self._running[project_id] = task
        return "started"

    async def _run_pipeline_inner(self, project_id: str, llm_provider: str, api_key: str, cfg: Dict):
        state = store.load_state(project_id)
        state["status"] = "running"
        store.save_state(project_id, state)

        # 合并全局配置
        merged_cfg = {**config.DEFAULT_CONFIG, **cfg}

        try:
            # Stage 0: 总导演（产出导演工作单，供下游使用）
            state = store.load_state(project_id)
            merged_cfg = {**merged_cfg, "theme": (state.get("meta") or {}).get("theme", "")}
            director = self.agents["director"](project_id, llm_provider, api_key=api_key)
            await director.run(state, merged_cfg)
            await self._emit(project_id, "director", "completed", "总导演工作单已生成")

            # Stage 1-2: 编剧（故事+剧本）
            state = store.load_state(project_id)
            screenwriter = self.agents["screenwriter"](project_id, llm_provider, api_key=api_key)
            script = await screenwriter.run(state, merged_cfg)

            # Stage 3: 分镜
            state = store.load_state(project_id)
            storyboarder = self.agents["storyboarder"](project_id, llm_provider, api_key=api_key)
            storyboard = await storyboarder.run(state, merged_cfg)

            # Stage 4: 角色设计
            state = store.load_state(project_id)
            character_designer = self.agents["character_designer"](project_id, llm_provider, api_key=api_key)
            characters = await character_designer.run(state, merged_cfg)

            # Stage 5: 视频生成
            state = store.load_state(project_id)
            video_producer = self.agents["video_producer"](project_id, llm_provider, api_key=api_key)
            clips = await video_producer.run(state, merged_cfg)

            # Stage 6-8: 剪辑成片
            state = store.load_state(project_id)
            editor = self.agents["editor"](project_id, llm_provider, api_key=api_key)
            final = await editor.run(state, merged_cfg)

            state = store.load_state(project_id)
            state["status"] = "completed"
            state["result"] = final
            store.save_state(project_id, state)
            await self._emit(project_id, "pipeline", "completed", "全部完成", final)
            return final

        except Exception as e:
            logger.exception("流水线失败")
            state = store.load_state(project_id)
            state["status"] = "failed"
            state["error"] = str(e)
            store.save_state(project_id, state)
            await self._emit(project_id, "pipeline", "failed", str(e))
            raise


# 全局单例
pipeline_service = PipelineService()

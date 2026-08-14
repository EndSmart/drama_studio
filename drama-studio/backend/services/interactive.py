"""
交互式（分步精修）流水线引擎。

在原有「一键生成」全流程之外，提供按阶段逐步执行的能力：
每个文本阶段（编剧/分镜/角色）运行后，把产物返回前端供用户查看、修改、润色，
多轮交互直至满意；视频生成与剪辑阶段则支持「运行 → 查看 → 重生成」。

设计要点：
- 各阶段产物落盘到 artifacts/，下游阶段直接读取磁盘，因此用户对上游的
  编辑会被自然继承（保存即覆盖文件）。
- 对 screenwriter / storyboarder / character_designer 的 run() 增加了可选的
  instruction 参数，用于「润色重生成」。
- 一键生成（run_pipeline）完全不受影响。
"""

import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional

from .. import config
from .storage import store

logger = logging.getLogger("drama-studio.services.interactive")


# ============ 阶段定义（有序） ============
# editable: 是否允许用户在前端编辑该产物
# format:   前端编辑/展示格式（md / json）
# artifact: 可编辑产物的相对路径（相对于项目目录）
# context:  展示时一并加载的只读上下文产物
STAGE_DEFS = [
    {
        "key": "director",
        "label": "总导演",
        "editable": True,
        "format": "json",
        "artifact": "artifacts/director/creative_brief.json",
        "context": [],
        "hint": "总导演分析主题、产出导演工作单（角色/类型/基调/情节脉络）。可查看并修改后再继续。",
    },
    {
        "key": "screenwriter",
        "label": "编剧创作",
        "editable": True,
        "format": "md",
        "artifact": "artifacts/screenwriter/script.md",
        "context": ["artifacts/screenwriter/story.md"],
        "hint": "可修改对白、节奏、场景，或填写「润色指令」让 AI 重新生成剧本。",
    },
    {
        "key": "storyboarder",
        "label": "分镜设计",
        "editable": True,
        "format": "json",
        "artifact": "artifacts/storyboarder/storyboard.json",
        "context": [],
        "hint": "可调整镜头数量、景别、运镜、时长、image_prompt 等，或填写指令重生成。",
    },
    {
        "key": "character_designer",
        "label": "角色设计",
        "editable": True,
        "format": "json",
        "artifact": "artifacts/characters/characters.json",
        "context": [],
        "hint": "可修改角色外貌、性格、seed_prompt（影响后续一致性）。保存会以角色卡写回。",
    },
    {
        "key": "video_producer",
        "label": "视频生成",
        "editable": False,
        "format": "json",
        "artifact": "artifacts/video_producer/clips_manifest.json",
        "context": [],
        "hint": "逐镜头生成视频片段（耗时较长）。生成后可查看结果并选择「重新生成」。",
    },
    {
        "key": "editor",
        "label": "剪辑成片",
        "editable": False,
        "format": "json",
        "artifact": "artifacts/editor/final_summary.json",
        "context": [],
        "hint": "下载片段、拼接、生成字幕并合成成片。完成后即可下载最终短片。",
    },
]


class InteractiveService:
    """交互式分阶段执行引擎。"""

    def __init__(self):
        from ..agents.director import DirectorAgent
        from ..agents.screenwriter import ScreenwriterAgent
        from ..agents.storyboarder import StoryboarderAgent
        from ..agents.character_designer import CharacterDesignerAgent
        from ..agents.video_producer import VideoProducerAgent
        from ..agents.editor import EditorAgent

        self.agent_map = {
            "director": DirectorAgent,
            "screenwriter": ScreenwriterAgent,
            "storyboarder": StoryboarderAgent,
            "character_designer": CharacterDesignerAgent,
            "video_producer": VideoProducerAgent,
            "editor": EditorAgent,
        }
        # 这些阶段支持 instruction 润色
        self._refinable = {"director", "screenwriter", "storyboarder", "character_designer"}

    # ---------- 阶段元数据 ----------
    @staticmethod
    def stage_order() -> List[str]:
        return [s["key"] for s in STAGE_DEFS]

    @staticmethod
    def stage_defs() -> List[Dict]:
        return STAGE_DEFS

    @staticmethod
    def get_stage(key: str) -> Optional[Dict]:
        for s in STAGE_DEFS:
            if s["key"] == key:
                return s
        return None

    @classmethod
    def next_stage(cls, key: str) -> Optional[str]:
        order = cls.stage_order()
        if key in order:
            i = order.index(key)
            if i + 1 < len(order):
                return order[i + 1]
        return None

    # ---------- Agent 构造 ----------
    def _build_agent(self, stage: str, project_id: str, providers: Dict):
        lp = providers.get("llm_provider")
        lk = providers.get("api_key")
        cls = self.agent_map.get(stage)
        if not cls:
            raise ValueError(f"未知阶段: {stage}")

        if stage in ("director", "screenwriter", "storyboarder", "editor"):
            return cls(project_id, lp, api_key=lk)
        if stage == "character_designer":
            return cls(
                project_id, lp, api_key=lk,
                image_provider=providers.get("image_provider"),
                image_api_key=providers.get("image_api_key"),
            )
        if stage == "video_producer":
            return cls(
                project_id, lp, api_key=lk,
                video_provider=providers.get("video_provider"),
                video_api_key=providers.get("video_api_key"),
                image_provider=providers.get("image_provider"),
                image_api_key=providers.get("image_api_key"),
            )
        raise ValueError(f"未支持的阶段: {stage}")

    # ---------- 产物读取 ----------
    @staticmethod
    def _read_artifact_text(project_id: str, rel_path: str, fmt: str) -> str:
        full = store.file_path(project_id, rel_path)
        if not full.exists():
            return ""
        if fmt == "json":
            try:
                data = json.loads(full.read_text(encoding="utf-8"))
                return json.dumps(data, ensure_ascii=False, indent=2)
            except Exception:
                return full.read_text(encoding="utf-8")
        return full.read_text(encoding="utf-8")

    def _artifact_envelope(self, project_id: str, stage: str, result: Any = None) -> Dict:
        """构造返回给前端的产物信封（含可编辑内容 + 只读上下文）。"""
        sd = self.get_stage(stage)
        if sd is None:
            raise ValueError(f"未知阶段: {stage}")

        # 角色阶段：把各角色卡聚合为统一的 characters.json 供编辑
        if stage == "character_designer":
            chars = (result or {}).get("characters", []) if isinstance(result, dict) else []
            if not chars:
                existing = store.load_artifact(project_id, "artifacts/characters/characters.json")
                chars = existing if isinstance(existing, list) else []
            store.save_artifact(project_id, "characters", "characters.json", chars)
            content = json.dumps(chars, ensure_ascii=False, indent=2)
        elif stage == "editor":
            # 剪辑结果存一份 summary 供前端审阅
            summary = result or {}
            store.save_artifact(project_id, "editor", "final_summary.json", summary)
            content = json.dumps(summary, ensure_ascii=False, indent=2)
        else:
            content = self._read_artifact_text(project_id, sd["artifact"], sd["format"])

        # 只读上下文
        context = []
        for ctx_path in sd.get("context", []):
            ctx_text = self._read_artifact_text(project_id, ctx_path, "md")
            if ctx_text:
                context.append({"path": ctx_path, "content": ctx_text})

        return {
            "stage": stage,
            "label": sd["label"],
            "editable": sd["editable"],
            "format": sd["format"],
            "artifact_path": sd["artifact"],
            "content": content,
            "context": context,
            "hint": sd.get("hint", ""),
            "next_stage": self.next_stage(stage),
        }

    # ---------- 执行 / 润色 / 保存 ----------
    async def execute(self, project_id: str, stage: str, providers: Dict,
                      config_override: Dict = None, instruction: str = None) -> Dict:
        """运行某阶段（run / refine 共用）。instruction 非空即为润色重生成。"""
        if stage not in self.agent_map:
            raise ValueError(f"未知阶段: {stage}")

        agent = self._build_agent(stage, project_id, providers)
        now = datetime.datetime.utcnow().isoformat() + "Z"

        state = store.load_state(project_id)
        if not state:
            raise ValueError(f"项目不存在: {project_id}")
        # 合并优先级：默认 < 项目创建时的配置 < 本次覆盖
        project_cfg = (state.get("meta") or {}).get("config", {})
        # 主题存在 meta.theme，需注入到 config 供导演等阶段使用
        theme = (state.get("meta") or {}).get("theme", "")
        merged_cfg = {**config.DEFAULT_CONFIG, **project_cfg, **(config_override or {}), "theme": theme}
        state["current_stage"] = stage
        state["mode"] = "interactive"
        state.setdefault("stages", {})[stage] = {"status": "running", "started_at": now}
        store.save_state(project_id, state)

        try:
            if stage in self._refinable:
                result = await agent.run(state, merged_cfg, instruction=instruction)
            else:
                result = await agent.run(state, merged_cfg)

            state = store.load_state(project_id)
            state.setdefault("stages", {})[stage] = {
                "status": "completed",
                "completed_at": datetime.datetime.utcnow().isoformat() + "Z",
                "result": result,
            }
            store.save_state(project_id, state)
        except Exception as e:
            logger.exception("交互式阶段 %s 执行失败", stage)
            state = store.load_state(project_id)
            state.setdefault("stages", {})[stage] = {"status": "failed", "error": str(e)}
            store.save_state(project_id, state)
            raise

        return self._artifact_envelope(project_id, stage, result)

    async def save(self, project_id: str, stage: str, content: str) -> Dict:
        """保存用户对某阶段产物的编辑（覆盖落盘文件）。"""
        sd = self.get_stage(stage)
        if sd is None:
            raise ValueError(f"未知阶段: {stage}")
        if not sd["editable"]:
            raise ValueError(f"阶段 {stage} 的产物不可编辑")

        fmt = sd["format"]
        rel = sd["artifact"]
        full = store.file_path(project_id, rel)
        full.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "json":
            try:
                data = json.loads(content)
            except Exception as e:
                raise ValueError(f"JSON 格式错误: {e}")
            if stage == "character_designer":
                self._write_character_cards(project_id, data)
                store.save_artifact(project_id, "characters", "characters.json", data)
            else:
                full.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            full.write_text(content, encoding="utf-8")

        # 标记用户已编辑
        state = store.load_state(project_id)
        if state:
            state.setdefault("stages", {}).setdefault(stage, {})["user_edited"] = True
            store.save_state(project_id, state)

        return self._artifact_envelope(project_id, stage, None)

    @staticmethod
    def _write_character_cards(project_id: str, cards: List[Dict]):
        """把编辑后的角色卡列表写回各角色目录（供视频生成读取）。"""
        if not isinstance(cards, list):
            return
        for card in cards:
            name = str(card.get("name", "角色")).strip() or "角色"
            safe = re.sub(r'[^\w一-龥-]', "_", name)[:40] or "角色"
            card["style"] = card.get("style") or "cinematic"
            store.save_artifact(project_id, f"characters/{safe}", "character_card.json", card)


# 全局单例
interactive_service = InteractiveService()

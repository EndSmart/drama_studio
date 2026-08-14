"""
系统提示词（System Prompt）集中管理。

问题背景：
    原先每个 Agent 的提示词都硬编码在各自的类属性里（如 DirectorAgent.SYSTEM_PROMPT），
    既无法查看也无法修改。本模块把"种子提示词"统一收口，并提供两级覆盖：

    1. 全局默认（global）：存于 data/prompts/global.json，管理员可改，影响所有新项目。
    2. 项目覆盖（project）：存于各项目 state["prompts"]，仅作用于当前项目。

解析优先级：项目覆盖 > 全局覆盖 > 代码种子（DEFAULT_PROMPTS）。

为避免循环导入，本模块只依赖 config / storage，Agent 改为从本模块 import prompt_store。
"""

import json
import logging
from typing import Dict, List, Optional

from .. import config
from .storage import store

logger = logging.getLogger("drama-studio.services.prompts")


# ============ 阶段 / 提示词元数据（供前端展示） ============
STAGE_META: Dict[str, Dict] = {
    "director": {
        "label": "总导演",
        "keys": {
            "system": "导演工作单系统提示词",
        },
        "desc": "分析主题，产出后续所有环节统一遵循的导演工作单。",
    },
    "screenwriter": {
        "label": "编剧",
        "keys": {
            "story": "故事文本生成提示词",
            "script": "剧本生成提示词（含 {duration} 占位符）",
        },
        "desc": "基于导演工作单生成故事文本与标准短剧剧本。",
    },
    "storyboarder": {
        "label": "分镜",
        "keys": {
            "system": "分镜系统提示词",
            "user_template": "分镜用户模板（含 {duration} 占位符）",
        },
        "desc": "将剧本拆分为逐镜头分镜脚本并规划配乐基调。",
    },
    "character_designer": {
        "label": "角色设计",
        "keys": {
            "system": "角色设计系统提示词",
        },
        "desc": "为每个角色生成标准化角色卡，建立一致性基准。",
    },
}

# ============ 种子提示词（代码默认值，可被全局/项目覆盖） ============
DEFAULT_PROMPTS: Dict[str, Dict[str, str]] = {
    "director": {
        "system": """你是资深的短剧总导演。你的职责是分析用户给出的创作主题，产出一份结构化的"导演工作单"（creative brief），作为后续编剧、分镜、角色设计、视频生成等所有环节的统一指导纲领。

工作单必须包含：
1. theme：短剧主题
2. genre：类型（言情/悬疑/喜剧/都市/奇幻/科幻/古装等）
3. tone：整体基调（如：暗恋虐心/轻甜欢喜/悬疑紧张等）
4. story_highlights：核心看点与卖点（2-4 条）
5. characters：主要角色清单，每个含 name / role（主角/配角/反派）/ personality（性格）/ appearance（外貌，尽量具体到发型/脸型/服饰，供角色设计使用）
6. plot_arc：情节脉络（起/承/转/合四个阶段的简述）
7. target_audience：目标受众
8. visual_style：视觉风格建议（如：电影质感/日系清新/都市写实等）

严格要求：
- 角色外貌描述必须具体、可被图像生成模型理解（描述发型、脸型、眼睛、体型、标志性服饰），这是后续角色一致性的基础
- 用 JSON 格式输出
- 不要写完整剧本，那是编剧的事

如果用户已经预定义了角色（在 user_characters 中给出），请直接沿用这些角色的 name 与 role，不要另起炉灶重新发明角色；可在其基础上补充性格与外貌细节。""",
    },
    "screenwriter": {
        "story": """你是资深短剧编剧。根据导演工作单，生成一个适合竖屏短剧的完整故事文本。

要求：
1. 故事要有完整的起承转合，节奏紧凑（短剧需要高频冲突和钩子）
2. 明确所有主要角色的性格和外形
3. 包含故事梗概（300-500字）和分场大纲
4. 结尾要有一个钩子或反转，吸引观众看下一集

输出 Markdown 格式：
# 故事标题
## 故事梗概
（正文）
## 角色设定
（每个角色一段）
## 分场大纲
（每场一段，标注地点/时间/核心事件）""",
        "script": """你是专业短剧编剧。根据故事文本，将故事转化为标准的短剧分场剧本。

要求：
1. 用标准剧本格式：场景标题（场景编号、地点、时间）、人物、对白、动作指示
2. 对白要口语化、符合角色性格、每句简洁有力（短剧对白要短促、有张力）
3. 动作指示放在括号中
4. 目标总时长约 {duration} 秒，平均每场景 15-20 秒
5. 每场包含 1-2 个核心情节点

输出 Markdown 格式：
## 场景 {N}：{地点}（{时间}）
人物：{角色1}、{角色2}
{动作/环境描述}
**{角色1}**：（{动作指示}）{对白}
**{角色2}**：{对白}
...""",
    },
    "storyboarder": {
        "system": "你是专业分镜师。严格按照 JSON 格式输出分镜脚本和配乐计划。",
        "user_template": """你是专业的短剧分镜师。根据剧本，将其拆分为逐镜头分镜脚本，并规划配乐基调。

要求：
1. 每个镜头包含：shot_id、scene_id、shot_type（closeup/medium/wide）、camera_movement（static/pan/tilt/zoom_in/zoom_out/tracking）、visual_description、characters_in_shot、dialogue、duration_seconds、transition_to_next（cut/fade/dissolve）、music_mood、image_prompt、video_prompt、negative_prompt
2. image_prompt：完整的画面描述（含角色外貌特征 + 场景环境 + 光线氛围 + 视觉风格），供图像生成首帧。角色外貌必须保持与角色设定一致
3. video_prompt：仅描述运动/动作/镜头运动，不要重复角色外貌（因为首帧已锁定角色）
4. duration_seconds：默认 5 秒，总时长约 {duration} 秒
5. 竖屏短剧以中近景和特写为主
6. music_mood 用以下标签：tense/romantic/sad/happy/suspense/neutral/action

另外输出 music_plan.json：
{{
  "overall_tone": "整体基调",
  "segments": [
    {{
      "shot_range": [起始镜头, 结束镜头],
      "mood": "情绪标签",
      "tempo": "slow/medium/fast",
      "instruments": ["钢琴","弦乐"],
      "duration_seconds": 时长,
      "source": "auto",
      "description": "音乐描述"
    }}
  ]
}}

严格输出 JSON，格式：
{{"storyboard": {{"shots": [...]}}, "music_plan": {{...}} }}
不要输出任何多余文字。""",
    },
    "character_designer": {
        "system": """你是角色设计总监。根据剧本和分镜中的角色，为每个角色生成标准化的角色卡。

对每个角色输出：
{{
  "name": "角色名",
  "role": "主角/配角/反派",
  "personality": "性格",
  "appearance": {{
    "age": "年龄",
    "hair": "发型",
    "face": "脸型",
    "eyes": "眼睛",
    "complexion": "肤色",
    "body": "体型",
    "clothing": "标志性服装"
  }},
  "seed_prompt": "一段固定的外貌描述前缀，用于所有后续图像/视频生成保持一致性（整合外貌特征为一句话，如：20岁长发瓜子脸大眼睛皮肤白皙的少女，穿着白色连衣裙）",
  "style": "视觉风格"
}}

说明：
- appearance 字段结构不固定，可自由增减键（例如增加"配饰""纹身"等），只要能描述清楚外貌即可。
- 如果用户已经预定义了角色（user_characters），请直接沿用其 name / role / appearance / seed_prompt，仅做必要的补全与规范化，不要替换或重命名角色。
- 严格输出 JSON 数组格式：[角色卡1, 角色卡2, ...]""",
    },
}


class PromptStore:
    """系统提示词存储（全局 + 项目两级覆盖）。"""

    def __init__(self):
        self.global_dir = config.DATA_DIR / "prompts"
        self.global_dir.mkdir(parents=True, exist_ok=True)
        self.global_path = self.global_dir / "global.json"

    # ---------- 持久化 ----------
    def _load_global(self) -> Dict[str, Dict[str, str]]:
        if not self.global_path.exists():
            return {}
        try:
            return json.loads(self.global_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("全局提示词读取失败，回退为空")
            return {}

    def _save_global(self, data: Dict[str, Dict[str, str]]) -> None:
        self.global_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- 读取 ----------
    def get_default(self, stage: str, key: str) -> str:
        """代码种子提示词。"""
        return DEFAULT_PROMPTS.get(stage, {}).get(key, "")

    def get_global(self, stage: str, key: str) -> Optional[str]:
        return self._load_global().get(stage, {}).get(key)

    def get_project(self, project_id: str, stage: str, key: str) -> Optional[str]:
        state = store.load_state(project_id)
        if not state:
            return None
        return (state.get("prompts") or {}).get(stage, {}).get(key)

    def get_effective(self, project_id: str, stage: str, key: str) -> str:
        """解析优先级：项目覆盖 > 全局覆盖 > 代码种子。"""
        if project_id:
            p = self.get_project(project_id, stage, key)
            if p is not None:
                return p
        g = self.get_global(stage, key)
        if g is not None:
            return g
        return self.get_default(stage, key)

    # ---------- 写入 ----------
    def set_global(self, stage: str, key: str, text: str) -> None:
        data = self._load_global()
        data.setdefault(stage, {})[key] = text
        self._save_global(data)

    def set_project(self, project_id: str, stage: str, key: str, text: str) -> None:
        state = store.load_state(project_id)
        if not state:
            raise ValueError(f"项目不存在: {project_id}")
        state.setdefault("prompts", {}).setdefault(stage, {})[key] = text
        store.save_state(project_id, state)

    def reset(self, scope: str, project_id: str = None,
              stage: str = None, key: str = None) -> None:
        """重置覆盖：删除覆盖项使其回退到更低优先级（或代码种子）。"""
        if scope == "global":
            data = self._load_global()
            if stage:
                data.get(stage, {}).pop(key, None) if key else data.pop(stage, None)
            else:
                data = {}
            self._save_global(data)
        elif scope == "project":
            if not project_id:
                raise ValueError("project 作用域需要 project_id")
            state = store.load_state(project_id)
            if not state:
                raise ValueError(f"项目不存在: {project_id}")
            prompts = state.get("prompts") or {}
            if stage:
                if key:
                    prompts.get(stage, {}).pop(key, None)
                else:
                    prompts.pop(stage, None)
            else:
                prompts = {}
            state["prompts"] = prompts
            store.save_state(project_id, state)
        else:
            raise ValueError(f"未知 scope: {scope}")

    # ---------- 罗列（供前端） ----------
    def list_all(self, project_id: str = None) -> List[Dict]:
        """返回所有阶段提示词的元数据 + 各级内容。"""
        result = []
        for stage, meta in STAGE_META.items():
            for key, key_label in meta["keys"].items():
                default = self.get_default(stage, key)
                global_val = self.get_global(stage, key)
                project_val = self.get_project(project_id, stage, key) if project_id else None
                effective = self.get_effective(project_id, stage, key)
                result.append({
                    "stage": stage,
                    "stage_label": meta["label"],
                    "key": key,
                    "key_label": key_label,
                    "default": default,
                    "global": global_val,
                    "project": project_val,
                    "effective": effective,
                    # 用户当前编辑的"覆盖值"：项目优先，否则全局
                    "override": project_val if project_val is not None else global_val,
                    "scope_in_use": "project" if project_val is not None
                    else ("global" if global_val is not None else "default"),
                })
        return result


# 全局单例
prompt_store = PromptStore()

"""
dryrun_pipeline.py — 全流程 Mock 桩回归测试（无需任何 API Key / 真实 ffmpeg）。

目的
----
在没有大模型 / 图像 / 视频 API Key 的沙箱里，用桩替换外部依赖，但跑通**真实的编排代码**
（director → screenwriter → storyboarder → character_designer → video_producer → editor），
验证：
  1. 全流程编排不报错、各阶段产物正确落盘；
  2. 项目级系统提示词覆盖生效（director 实际收到的 system 含标记）；
  3. 用户预定义角色被导演 + 角色设计采用（角色不写死、可手动添加）；
  4. 角色卡 appearance 字段自由（可含自定义字段，不被固定 schema 限制）；
  5. 交互式逐步流程（含新增的 director 阶段）正常工作。

外部依赖如何处理
--------------
  - LLM / Image / Video provider：用 Fake 桩替换工厂方法，返回结构化桩数据。
  - 视频 clip：生成本地虚拟文件（无需真实视频/ffmpeg），video 桩直接返回其路径。
  - editor 的 ffmpeg 调用：本环境 ffmpeg 二进制会 SIGSEGV，故整体桩化为「拷贝首个输入作为输出」。
    这不影响对被测编排代码的验证（editor 的 ffmpeg 步骤不属于本次改动范围）。

运行方式
------
    python tests/dryrun_pipeline.py
退出码非 0 表示失败。脚本结束会清理自己在 data/ 下创建的测试项目。

注意：脚本依赖 backend 包，须从仓库根（drama-studio/drama-studio/）或任意位置运行，
路径根据 __file__ 自动推算，无需手动设置 cwd。
"""

import asyncio
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

# ---------- 路径推算 ----------
HERE = Path(__file__).resolve().parent          # .../drama-studio/drama-studio/tests
ROOT = HERE.parent                               # .../drama-studio/drama-studio
sys.path.insert(0, str(ROOT))

from backend import config
from backend.services import storage as storage_mod
store = storage_mod.store
from backend.services.prompts import prompt_store
from backend.providers.llm import LLMFactory
from backend.providers.image import ImageProviderFactory
from backend.providers.video import VideoProviderFactory
from backend.services.pipeline import pipeline_service
from backend.services.interactive import interactive_service
from backend.agents.editor import EditorAgent
from backend.services import ffmpeg as ffmpeg_mod

# ---------- 准备虚拟片段（无需 ffmpeg） ----------
CLIP_DIR = "/tmp/dryrun_clips"
os.makedirs(CLIP_DIR, exist_ok=True)
CLIPS = []
for i in range(3):
    p = os.path.join(CLIP_DIR, f"clip_{i}.mp4")
    Path(p).write_bytes(b"FAKE_MP4_CLIP_BYTES_" + bytes([i]) * 1000)
    CLIPS.append(p)

# ---------- 桩：LLM ----------
seen_systems = []  # 记录每次 LLM 收到的 system 内容

STORYBOARD = {
    "storyboard": {"shots": [
        {"shot_id": 1, "scene_id": 1, "shot_type": "closeup", "camera_movement": "static",
         "visual_description": "墨子特写", "characters_in_shot": ["墨子"], "dialogue": "我反对。",
         "duration_seconds": 5, "transition_to_next": "cut", "music_mood": "tense",
         "image_prompt": "墨子 灰袍 长须 特写", "video_prompt": "墨子缓缓摇头", "negative_prompt": ""},
        {"shot_id": 2, "scene_id": 1, "shot_type": "medium", "camera_movement": "pan",
         "visual_description": "公输班中景", "characters_in_shot": ["公输班"], "dialogue": "那就来比一比。",
         "duration_seconds": 5, "transition_to_next": "cut", "music_mood": "tense",
         "image_prompt": "公输班 匠装 中景", "video_prompt": "公输班转身", "negative_prompt": ""},
    ]},
    "music_plan": {"overall_tone": "紧张", "segments": [
        {"shot_range": [1, 2], "mood": "tense", "tempo": "fast", "instruments": ["鼓"],
         "duration_seconds": 10, "source": "auto", "description": "紧张配乐"}]},
}

DEFAULT_BRIEF_CHARS = [
    {"name": "墨子", "role": "主角", "personality": "睿智",
     "appearance": {"age": "50", "hair": "长须", "face": "方脸", "eyes": "深邃", "complexion": "偏黑", "body": "清瘦", "clothing": "灰袍"}},
    {"name": "公输班", "role": "配角", "personality": "倔强",
     "appearance": {"age": "45", "hair": "短发", "face": "圆脸", "eyes": "锐利", "complexion": "白净", "body": "壮实", "clothing": "匠装"}},
]

USER_CHARS = [
    {"name": "自定义角色A", "role": "主角", "personality": "冷静",
     "appearance": {"age": "30", "hair": "短发", "custom_field": "红眸"}, "seed_prompt": "", "style": "cinematic"},
    {"name": "自定义角色B", "role": "反派", "personality": "阴险",
     "appearance": {"weapon": "黑剑", "clothing": "黑袍"}, "seed_prompt": "30岁红眸短发青年", "style": "cinematic"},
]


def _extract_json_array(text):
    try:
        s = text.index("[")
        e = text.rindex("]") + 1
        return json.loads(text[s:e])
    except Exception:
        return None


class FakeLLM:
    def __init__(self, *a, **k):
        pass

    async def chat(self, messages, temperature=0.7, max_tokens=None, **kwargs):
        sys_text = "\n".join(m["content"] for m in messages if m["role"] == "system")
        user_text = "\n".join(m["content"] for m in messages if m["role"] == "user")
        seen_systems.append(sys_text)

        if "总导演" in sys_text or "导演工作单" in sys_text:
            chars = _extract_json_array(user_text)
            brief_chars = chars if chars else DEFAULT_BRIEF_CHARS
            return json.dumps({
                "theme": "测试主题", "genre": "科幻", "tone": "紧张",
                "story_highlights": ["亮点1", "亮点2"], "characters": brief_chars,
                "plot_arc": "起承转合", "target_audience": "成人", "visual_style": "电影质感",
            }, ensure_ascii=False)

        if "完整故事" in sys_text or "故事文本" in sys_text:
            return "# 故事标题\n## 故事梗概\n测试故事梗概内容。\n## 角色设定\n墨子、公输班。\n## 分场大纲\n场景1：工坊。"

        if "分场剧本" in sys_text or "标准剧本" in sys_text:
            return ("## 场景 1：工坊（日）\n人物：墨子、公输班\n"
                    "**墨子**：（平静）我反对。\n**公输班**：（倔强）那就来比一比。")

        if "分镜师" in sys_text:
            return json.dumps(STORYBOARD, ensure_ascii=False)

        if "角色设计总监" in sys_text:
            chars = _extract_json_array(user_text)
            if chars:  # 用户预定义 → 仅补全 seed_prompt
                out = []
                for c in chars:
                    c = dict(c)
                    if not c.get("seed_prompt"):
                        ap = c.get("appearance", {})
                        c["seed_prompt"] = "，".join(str(v) for v in ap.values() if v) or c.get("name", "角色")
                    out.append(c)
                return json.dumps(out, ensure_ascii=False)
            return json.dumps([
                {**c, "seed_prompt": "，".join(str(v) for v in c["appearance"].values()), "style": "cinematic"}
                for c in DEFAULT_BRIEF_CHARS
            ], ensure_ascii=False)

        return "OK"

    async def chat_json(self, messages, temperature=0.4, **kwargs):
        return await self.chat(messages, temperature=temperature, **kwargs)


class FakeImage:
    def __init__(self, *a, **k):
        pass

    async def generate(self, prompt, **kwargs):
        p = os.path.join(CLIP_DIR, f"img_{uuid.uuid4().hex[:6]}.png")
        Path(p).write_bytes(b"FAKE_PNG")
        return p


class FakeVideo:
    def __init__(self, *a, **k):
        self._n = 0
        self._map = {}

    async def submit_task(self, prompt, image_url=None, duration=5, resolution="720p", aspect_ratio="9:16"):
        tid = f"fake-task-{uuid.uuid4().hex[:8]}"
        self._map[tid] = CLIPS[self._n % len(CLIPS)]
        self._n += 1
        return tid

    async def wait_for_result(self, task_id, timeout=600, interval=5):
        return self._map.get(task_id, CLIPS[0])


# 编辑器下载：桩改为本地复制（避免 httpx 拉取本地路径）
async def fake_download(self, clips, project_dir):
    d = project_dir / "artifacts" / "editor" / "clips"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for clip in clips:
        url = clip.get("clip_url")
        if url and os.path.exists(url):
            dst = d / f"shot_{clip.get('shot_id', 0)}.mp4"
            shutil.copy2(url, dst)
            out.append(dst)
    return out


# 编辑器 ffmpeg 步骤：本环境 ffmpeg 二进制会 SIGSEGV，做无害桩（拷贝首个输入作为输出）
def fake_concat_cut(clip_paths, output_path):
    if clip_paths:
        shutil.copy2(clip_paths[0], output_path)

def fake_xfade_concat(clip_paths, transitions, output_path, transition_duration=0.5):
    if clip_paths:
        shutil.copy2(clip_paths[0], output_path)

def fake_burn_subtitles(input_path, srt_path, output_path, style="default"):
    if os.path.exists(input_path):
        shutil.copy2(input_path, output_path)

def fake_probe_duration(video_path):
    return 2.0

def fake_probe_size(video_path):
    return {"width": 720, "height": 1280}


def patch():
    LLMFactory.create = staticmethod(lambda *a, **k: FakeLLM())
    ImageProviderFactory.create = staticmethod(lambda *a, **k: FakeImage())
    VideoProviderFactory.create = staticmethod(lambda *a, **k: FakeVideo())
    EditorAgent._download_clips = fake_download
    ffmpeg_mod.FFmpegService.concat_cut = staticmethod(fake_concat_cut)
    ffmpeg_mod.FFmpegService.xfade_concat = staticmethod(fake_xfade_concat)
    ffmpeg_mod.FFmpegService.burn_subtitles = staticmethod(fake_burn_subtitles)
    ffmpeg_mod.FFmpegService.probe_duration = staticmethod(fake_probe_duration)
    ffmpeg_mod.FFmpegService.probe_size = staticmethod(fake_probe_size)


_CREATED = []  # 记录创建的测试项目，便于清理


async def run_case(use_user_chars: bool, use_prompt_override: bool):
    project_id = uuid.uuid4().hex[:12]
    _CREATED.append(project_id)
    store.create_project(project_id, {"theme": "测试主题：机关术之争", "config": {**config.DEFAULT_CONFIG}})

    if use_prompt_override:
        prompt_store.set_project(project_id, "director", "system",
                                 "<<<OVERRIDE_MARKER>>> 你是总导演，请严格按 JSON 输出。")
    if use_user_chars:
        store.save_artifact(project_id, "characters", "characters.json", USER_CHARS)

    seen_systems.clear()
    await pipeline_service._run_pipeline_inner(project_id, "openai", api_key="fake", cfg={})

    def assert_path(rel):
        p = store.file_path(project_id, rel)
        assert p.exists(), f"缺失产物: {rel}"
        return p

    story = assert_path("artifacts/screenwriter/story.md").read_text(encoding="utf-8")
    script = assert_path("artifacts/screenwriter/script.md").read_text(encoding="utf-8")
    sb = assert_path("artifacts/storyboarder/storyboard.json")
    brief = json.loads(assert_path("artifacts/director/creative_brief.json").read_text(encoding="utf-8"))
    chars_obj = json.loads(assert_path("artifacts/characters/characters.json").read_text(encoding="utf-8"))
    manifest_obj = json.loads(assert_path("artifacts/video_producer/clips_manifest.json").read_text(encoding="utf-8"))
    final = assert_path("artifacts/editor/final_drama.mp4")

    print(f"\n===== 用例(use_user_chars={use_user_chars}, use_prompt_override={use_prompt_override}) =====")
    print("story.md 字节:", len(story), "| script.md 字节:", len(script))
    print("分镜 shots 数:", len(json.loads(sb.read_text())["shots"]))
    print("导演工作单 characters:", [c["name"] for c in brief["characters"]])
    print("角色卡数:", len(chars_obj), "| 名字:", [c["name"] for c in chars_obj])
    print("角色卡字段示例(角色A appearance):", chars_obj[0]["appearance"] if chars_obj else None)
    print("视频 clips 成功数:", len([c for c in manifest_obj["clips"] if c["status"] == "succeeded"]))
    print("最终成片存在:", final.exists(), "| 大小:", final.stat().st_size, "字节")

    if use_prompt_override:
        assert any("<<<OVERRIDE_MARKER>>>" in s for s in seen_systems), "项目提示词覆盖未生效!"
        print("✔ 项目级提示词覆盖已生效（director 收到标记）")
    if use_user_chars:
        names = [c["name"] for c in brief["characters"]]
        assert "自定义角色A" in names and "自定义角色B" in names, "用户预定义角色未被导演采用!"
        assert "自定义角色A" in [c["name"] for c in chars_obj], "用户预定义角色未被角色设计采用!"
        print("✔ 用户预定义角色被导演 + 角色设计采用（可添加、不写死）")
    print("✔ 全流程产物落盘完成")


async def run_interactive_case():
    project_id = uuid.uuid4().hex[:12]
    _CREATED.append(project_id)
    store.create_project(project_id, {"theme": "交互式测试", "config": {**config.DEFAULT_CONFIG}})
    store.save_artifact(project_id, "characters", "characters.json", USER_CHARS)

    providers = {"llm_provider": "openai", "api_key": "fake",
                 "image_provider": "wanx", "image_api_key": "fake"}
    env_dir = await interactive_service.execute(project_id, "director", providers, config_override={})
    brief = json.loads(env_dir["content"])
    assert [c["name"] for c in brief["characters"]] == ["自定义角色A", "自定义角色B"], "交互式导演未采用用户角色"
    print("\n===== 交互式用例 =====")
    print("✔ 交互式导演阶段生成工作单，并采用用户预定义角色:", [c["name"] for c in brief["characters"]])

    env_char = await interactive_service.execute(project_id, "character_designer", providers, config_override={})
    chars = json.loads(env_char["content"])
    assert [c["name"] for c in chars] == ["自定义角色A", "自定义角色B"], "交互式角色设计未采用用户角色"
    print("✔ 交互式角色设计阶段采用用户角色:", [c["name"] for c in chars])
    print("✔ 交互式逐步流程（含新增 director 阶段）正常工作")


def cleanup():
    for pid in _CREATED:
        d = store.project_dir(pid)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


async def main():
    patch()
    await run_case(use_user_chars=False, use_prompt_override=False)
    await run_case(use_user_chars=True, use_prompt_override=True)
    await run_interactive_case()
    print("\n=== ALL DRY-RUN CHECKS PASSED ===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        cleanup()

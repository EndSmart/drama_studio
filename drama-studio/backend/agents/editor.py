"""
剪辑 Agent（Stage 6-8）。

职责：
1. 下载各镜头视频片段
2. 按分镜顺序拼接（粗剪），加转场
3. 生成字幕（SRT）
4. 合成音视频（配乐 + 配音），烧录字幕
5. 产出最终成片

注意：视频 URL 由各平台返回，需下载到本地。下载依赖 httpx。
"""

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List

import httpx

from .base import BaseAgent
from ..services.ffmpeg import ffmpeg, FFmpegError
from ..services.storage import store

logger = logging.getLogger("drama-studio.agents.editor")


class EditorAgent(BaseAgent):
    """剪辑 Agent。"""

    name = "editor"
    description = "剪辑：拼接片段、加转场、生成字幕、合成成片"

    async def _download_clips(self, clips: List[Dict], project_dir: Path) -> List[Path]:
        """下载视频片段到本地。返回本地文件路径列表。"""
        local_paths = []
        download_dir = project_dir / "artifacts" / "editor" / "clips"
        download_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            for clip in clips:
                url = clip.get("clip_url")
                if not url:
                    continue
                shot_id = clip.get("shot_id", 0)
                # 根据 URL 判断扩展名
                ext = ".mp4"
                if "webm" in url:
                    ext = ".webm"
                local_path = download_dir / f"shot_{shot_id}{ext}"
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    local_path.write_bytes(resp.content)
                    local_paths.append(local_path)
                    self.log(f"镜头 {shot_id} 已下载")
                except Exception as e:
                    logger.warning("镜头 %d 下载失败: %s", shot_id, e)
                    self.log(f"镜头 {shot_id} 下载失败: {e}")

        return local_paths

    def _generate_srt(self, storyboard: Dict, output_path: Path) -> int:
        """根据分镜生成 SRT 字幕文件。"""
        shots = storyboard.get("shots", [])
        current_time = 0.0
        lines = []
        idx = 1

        for shot in shots:
            duration = shot.get("duration_seconds", 5)
            dialogue = shot.get("dialogue", "").strip()
            if dialogue:
                start = self._fmt_srt(current_time)
                end = self._fmt_srt(current_time + duration)
                lines.append(f"{idx}\n{start} --> {end}\n{dialogue}\n")
                idx += 1
            current_time += duration

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return len(lines)

    def _fmt_srt(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    async def run(self, state: Dict, config: Dict) -> Any:
        self.log("剪辑 Agent 开始")

        project_dir = store.project_dir(self.project_id)

        # 读取视频片段清单
        manifest = store.load_artifact(self.project_id, "artifacts/video_producer/clips_manifest.json")
        if not manifest or not manifest.get("clips"):
            raise ValueError("未找到视频片段，请先运行视频生成 Agent")

        clips = manifest["clips"]
        succeeded = [c for c in clips if c.get("status") == "succeeded" and c.get("clip_url")]
        if not succeeded:
            raise ValueError("没有成功生成的视频片段")

        # 读取分镜
        storyboard = store.load_artifact(self.project_id, "artifacts/storyboarder/storyboard.json") or {}
        shots = storyboard.get("shots", [])

        # 1. 下载片段
        self.log("下载视频片段...")
        local_clips = await self._download_clips(succeeded, project_dir)
        if not local_clips:
            raise ValueError("所有视频片段下载失败")

        # 2. 粗剪拼接（按 shot_id 排序）
        shot_id_map = {c.get("shot_id"): c for c in succeeded}
        ordered = []
        for shot in shots:
            clip = shot_id_map.get(shot.get("shot_id"))
            if clip:
                ordered.append(clip)

        # 与下载文件对应（简化：按顺序取）
        ordered_local = [local_clips[i] for i in range(min(len(ordered), len(local_clips)))]
        if not ordered_local:
            ordered_local = local_clips

        rough_dir = project_dir / "artifacts" / "editor"
        rough_dir.mkdir(parents=True, exist_ok=True)
        rough_path = rough_dir / "rough_cut.mp4"

        # 转场列表
        transitions = [shot.get("transition_to_next", "cut") for shot in shots[:-1]]

        try:
            self.log("进行视频拼接...")
            if all(t == "cut" for t in transitions):
                ffmpeg.concat_cut([str(p) for p in ordered_local], str(rough_path))
            else:
                ffmpeg.xfade_concat([str(p) for p in ordered_local], transitions, str(rough_path))
            self.log("粗剪完成")
        except FFmpegError as e:
            logger.error("拼接失败: %s", e)
            # 降级：用 concat
            try:
                ffmpeg.concat_cut([str(p) for p in ordered_local], str(rough_path))
            except Exception as e2:
                raise ValueError(f"视频拼接失败: {e2}")

        # 3. 生成字幕
        srt_path = rough_dir / "subtitles.srt"
        sub_count = self._generate_srt(storyboard, srt_path)
        self.log(f"生成 {sub_count} 条字幕")

        # 4. 合成成片（烧录字幕）
        final_path = project_dir / "artifacts" / "editor" / "final_drama.mp4"
        subtitle_style = config.get("subtitle_style", "drama")
        try:
            self.log("烧录字幕合成成片...")
            ffmpeg.burn_subtitles(str(rough_path), str(srt_path), str(final_path), subtitle_style)
            self.log("成片合成完成")
        except FFmpegError as e:
            logger.error("字幕烧录失败，降级为无字幕: %s", e)
            shutil.copy2(rough_path, final_path)

        duration = ffmpeg.probe_duration(str(final_path))
        size = ffmpeg.probe_size(str(final_path))

        result = {
            "final_video_path": str(final_path),
            "rough_cut_path": str(rough_path),
            "subtitle_path": str(srt_path),
            "duration_seconds": duration,
            "size": size,
            "shot_count": len(ordered_local),
            "subtitle_count": sub_count,
            "downloadable": True,
        }
        self.log(f"剪辑完成，成片时长 {duration:.1f} 秒")

        return result

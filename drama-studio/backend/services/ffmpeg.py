"""
ffmpeg 封装层。

负责视频后期处理：拼接、裁剪、转场、字幕烧录、音视频合成、帧提取。
全部通过 subprocess 调用系统 ffmpeg。
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("drama-studio.services.ffmpeg")


class FFmpegError(Exception):
    """ffmpeg 错误。"""


class FFmpegService:
    """ffmpeg 操作封装。"""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg = ffmpeg_path
        self.ffprobe = ffprobe_path

    def run(self, args: List[str]) -> str:
        """执行 ffmpeg 命令。"""
        cmd = [self.ffmpeg, "-y"] + args
        logger.info("ffmpeg: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise FFmpegError(f"ffmpeg 失败: {result.stderr[-500:]}")
        return result.stdout

    def probe_duration(self, video_path: str) -> float:
        """获取视频时长（秒）。"""
        cmd = [self.ffprobe, "-v", "error", "-show_entries", "format=duration",
               "-of", "json", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception:
            return 0.0

    def probe_size(self, video_path: str):
        """获取视频宽高。"""
        cmd = [self.ffprobe, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height", "-of", "json", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(result.stdout)
            s = data["streams"][0]
            return {"width": s.get("width"), "height": s.get("height")}
        except Exception:
            return None

    def concat_cut(self, clip_paths: List[str], output_path: str):
        """全硬切拼接（concat demuxer），适合无转场的快速拼接。"""
        # 统一编码后拼接，避免编码不兼容
        list_file = Path(output_path).parent / "concat_list.txt"
        list_file.write_text("\n".join(f"file '{p}'" for p in clip_paths), encoding="utf-8")
        self.run([
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy",
            output_path,
        ])

    def xfade_concat(self, clip_paths: List[str], transitions: List[str], output_path: str,
                     transition_duration: float = 0.5):
        """带转场的拼接（xfade filter）。transitions 长度 = clip数-1。"""
        if not clip_paths:
            raise FFmpegError("无视频片段可拼接")
        if len(clip_paths) == 1:
            self.run(["-i", clip_paths[0], "-c", "copy", output_path])
            return

        inputs = []
        for p in clip_paths:
            inputs += ["-i", p]

        durations = [self.probe_duration(p) for p in clip_paths]
        filter_parts = []
        # 构建 xfade 链
        prev = "[0:v]"
        offset = durations[0] - transition_duration
        for i in range(1, len(clip_paths)):
            trans = transitions[i - 1] if i - 1 < len(transitions) else "fade"
            out_label = f"[v{i}]"
            filter_parts.append(
                f"{prev}[{i}:v]xfade=transition={trans}:duration={transition_duration}:offset={offset:.2f}{out_label}"
            )
            prev = out_label
            offset += durations[i] - transition_duration

        filter_complex = ";".join(filter_parts)
        self.run([
            *inputs,
            "-filter_complex", filter_complex,
            "-map", prev,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            output_path,
        ])

    def trim_clip(self, input_path: str, output_path: str, start: float = None, end: float = None):
        """裁剪片段。"""
        args = ["-i", input_path]
        if start is not None:
            args += ["-ss", str(start)]
        if end is not None:
            args += ["-to", str(end)]
        args += ["-c", "copy", output_path]
        self.run(args)

    def speed_up(self, input_path: str, output_path: str, factor: float):
        """调整播放速度。factor>1 加速，<1 减速。"""
        self.run([
            "-i", input_path,
            "-filter_complex",
            f"[0:v]setpts={1/factor:.3f}*PTS[v];[0:a]atempo={factor:.2f}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            output_path,
        ])

    def extract_frame(self, input_path: str, output_path: str, time_sec: float = 0):
        """提取指定时间的帧为图片。"""
        self.run([
            "-i", input_path,
            "-ss", str(time_sec),
            "-frames:v", "1",
            output_path,
        ])

    def burn_subtitles(self, input_path: str, srt_path: str, output_path: str, style: str = "default"):
        """烧录字幕。"""
        style_map = {
            "default": "FontName=Noto Sans CJK SC,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=30",
            "drama": "FontName=Noto Sans CJK SC,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV=25",
        }
        force = style_map.get(style, style_map["default"])
        srt_escaped = str(srt_path).replace("'", "\\'")
        self.run([
            "-i", input_path,
            "-vf", f"subtitles='{srt_escaped}':force_style='{force}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "copy",
            output_path,
        ])

    def mix_audio(self, video_path: str, audio_inputs: List[Dict], output_path: str,
                  voice_volume: float = 1.0, music_volume: float = 0.3):
        """
        音视频合成。audio_inputs 每项：
        {"path": str, "start": float(延迟秒), "volume": float}
        """
        inputs = ["-i", video_path]
        for a in audio_inputs:
            inputs += ["-i", a["path"]]

        filter_parts = []
        for i, a in enumerate(audio_inputs, 1):
            delay_ms = int(a.get("start", 0) * 1000)
            vol = a.get("volume", 1.0)
            filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},volume={vol}[a{i}]")

        if filter_parts:
            mix_inputs = "".join(f"[a{i}]" for i in range(1, len(audio_inputs) + 1))
            filter_complex = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={len(audio_inputs)}:duration=first:dropout_transition=0[aout]"
        else:
            # 无音频输入，保留原音轨
            self.run([*inputs[:2], "-c", "copy", output_path])
            return

        self.run([
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ])


# 全局单例
ffmpeg = FFmpegService()

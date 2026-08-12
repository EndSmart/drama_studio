#!/usr/bin/env python3
"""
generate_srt.py — 从剧本和分镜脚本生成 SRT 字幕文件

用法：
    python3 generate_srt.py <script_md> <storyboard_json> <output_srt>

功能：
    从剧本的 scene 对白和分镜脚本的时间信息，
    生成精确对齐的 SRT 字幕文件。
"""

import json
import re
import sys
import os
from pathlib import Path


def parse_script_dialogues(script_path):
    """从剧本 Markdown 中解析场景和对白"""
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    dialogues = []
    current_scene = None
    current_time = None
    current_location = None
    
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        
        # 匹配场景标题
        scene_match = re.match(r'^##\s*场景\s*(\d+)', line)
        if scene_match:
            current_scene = int(scene_match.group(1))
            continue
        
        # 匹配地点
        loc_match = re.match(r'^\*\*地点\*\*[：:]\s*(.+)', line)
        if loc_match:
            current_location = loc_match.group(1).strip()
            continue
        
        # 匹配时间
        time_match = re.match(r'^\*\*时间\*\*[：:]\s*(.+)', line)
        if time_match:
            current_time = time_match.group(1).strip()
            continue
        
        # 匹配对白：**角色名**：对白内容
        dialogue_match = re.match(r'^\*\*(.+?)\*\*[：:]\s*(.+)', line)
        if dialogue_match:
            character = dialogue_match.group(1).strip()
            text = dialogue_match.group(2).strip()
            dialogues.append({
                'scene': current_scene,
                'character': character,
                'text': text,
                'location': current_location,
                'time': current_time
            })
    
    return dialogues


def build_subtitle_entries(dialogues, storyboard):
    """将对白按镜头时间段分配，生成字幕条目"""
    shots = storyboard.get('shots', [])
    
    # 按场景分组对白
    scene_dialogues = {}
    for d in dialogues:
        scene_id = d['scene']
        if scene_id not in scene_dialogues:
            scene_dialogues[scene_id] = []
        scene_dialogues[scene_id].append(d)
    
    # 按镜头分配对白
    entries = []
    current_time = 0.0
    
    for shot in shots:
        shot_id = shot['shot_id']
        scene_id = shot.get('scene_id', shot_id)
        duration = shot.get('duration_seconds', 5)
        
        # 该镜头的对白（从该场景的对白中取）
        scene_dlg = scene_dialogues.get(scene_id, [])
        shot_dialogue = shot.get('dialogue', '')
        
        # 如果镜头有明确对白
        if shot_dialogue:
            entries.append({
                'start': current_time,
                'end': current_time + duration,
                'text': shot_dialogue
            })
        elif scene_dlg:
            # 从场景对白中取（按顺序消费）
            d = scene_dlg.pop(0)
            entries.append({
                'start': current_time,
                'end': current_time + duration,
                'text': f"{d['character']}：{d['text']}"
            })
        
        current_time += duration
    
    return entries


def format_timestamp(seconds):
    """将秒数格式化为 SRT 时间戳 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(entries, output_path):
    """写入 SRT 文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, entry in enumerate(entries, 1):
            start = format_timestamp(entry['start'])
            end = format_timestamp(entry['end'])
            text = entry['text']
            
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n")
            f.write("\n")
    
    print(f"[generate_srt] 字幕生成完成：{output_path}")
    print(f"[generate_srt] 共 {len(entries)} 条字幕")


def main():
    if len(sys.argv) < 4:
        print("用法: python3 generate_srt.py <script_md> <storyboard_json> <output_srt>")
        sys.exit(1)
    
    script_path = sys.argv[1]
    storyboard_path = sys.argv[2]
    output_path = sys.argv[3]
    
    # 解析剧本对白
    dialogues = parse_script_dialogues(script_path)
    print(f"[generate_srt] 解析到 {len(dialogues)} 条对白")
    
    # 加载分镜脚本
    with open(storyboard_path, 'r', encoding='utf-8') as f:
        storyboard = json.load(f)
    
    # 构建字幕条目
    entries = build_subtitle_entries(dialogues, storyboard)
    print(f"[generate_srt] 生成 {len(entries)} 条字幕")
    
    if not entries:
        # 如果没有对白，生成占位字幕
        total_duration = sum(s.get('duration_seconds', 5) for s in storyboard.get('shots', []))
        entries.append({
            'start': 0,
            'end': total_duration,
            'text': '（无对白）'
        })
    
    # 写入 SRT
    write_srt(entries, output_path)


if __name__ == '__main__':
    main()

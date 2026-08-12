# ffmpeg 常用命令速查

短剧制作中所需的所有 ffmpeg 操作，包含完整命令行示例。

---

## 1. 视频拼接

### 方式一：concat demuxer（推荐，同编码格式）

适用场景：拼接编码格式、分辨率、帧率完全相同的视频片段。速度快，无重新编码。

```bash
# 创建文件列表 filelist.txt
# file 'shot_01.mp4'
# file 'shot_02.mp4'
# file 'shot_03.mp4'

ffmpeg -f concat -safe 0 -i filelist.txt -c copy output.mp4
```

### 方式二：concat filter（不同编码格式）

适用场景：拼接不同编码格式、分辨率或帧率的视频片段。需要重新编码，速度较慢。

```bash
ffmpeg -i shot_01.mp4 -i shot_02.mp4 -i shot_03.mp4 \
  -filter_complex "[0:v][1:v][2:v]concat=n=3:v=1:a=0[outv]" \
  -map "[outv]" output.mp4
```

带音频拼接：

```bash
ffmpeg -i shot_01.mp4 -i shot_02.mp4 \
  -filter_complex "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[outv][outa]" \
  -map "[outv]" -map "[outa]" output.mp4
```

---

## 2. 视频裁剪/截取

### 方式一：-ss / -to 参数（快速定位）

适用场景：截取指定时间段的视频。

```bash
# 从第 5 秒截取到第 15 秒
ffmpeg -i input.mp4 -ss 00:00:05 -to 00:00:15 -c copy output.mp4

# 从第 5 秒截取 10 秒时长
ffmpeg -i input.mp4 -ss 00:00:05 -t 00:00:10 -c copy output.mp4
```

**注意**：`-ss` 放在 `-i` 之前为快速定位（可能不精确），放在 `-i` 之后为精确定位（较慢）。需要精确裁剪时将 `-ss` 放在 `-i` 之后：

```bash
ffmpeg -i input.mp4 -ss 00:00:05 -t 00:00:10 -c:v libx264 -c:a aac output.mp4
```

### 方式二：trim filter（精确裁剪）

适用场景：在 filter_complex 链中精确裁剪，可与其他滤镜组合。

```bash
ffmpeg -i input.mp4 -filter_complex \
  "[0:v]trim=start=5:end=15,setpts=PTS-STARTPTS[v]; \
   [0:a]atrim=start=5:end=15,asetpts=PTS-STARTPTS[a]" \
  -map "[v]" -map "[a]" output.mp4
```

---

## 3. 转场效果

使用 `xfade` filter 在两段视频之间添加转场。

### 基本语法

```bash
ffmpeg -i video1.mp4 -i video2.mp4 \
  -filter_complex \
  "[0:v][1:v]xfade=transition=fade:duration=1:offset=4[outv]" \
  -map "[outv]" output.mp4
```

- `offset`：转场开始时间点（相对于第一段视频的时长，通常为第一段视频时长 - 转场时长）。
- `duration`：转场持续时间（秒）。

### 常用转场模式

```bash
# 淡入淡出
xfade=transition=fade:duration=1:offset=4

# 溶解
xfade=transition=dissolve:duration=1:offset=4

# 擦除
xfade=transition=wipeleft:duration=0.5:offset=4
xfade=transition=wiperight:duration=0.5:offset=4
xfade=transition=wipeup:duration=0.5:offset=4
xfade=transition=wipedown:duration=0.5:offset=4

# 滑动
xfade=transition=slideleft:duration=0.5:offset=4
xfade=transition=slideright:duration=0.5:offset=4

# 缩放
xfade=transition=zoomin:duration=0.5:offset=4
```

### 带音频的转场

```bash
ffmpeg -i video1.mp4 -i video2.mp4 \
  -filter_complex \
  "[0:v][1:v]xfade=transition=fade:duration=1:offset=4[outv]; \
   [0:a][1:a]acrossfade=d=1[outa]" \
  -map "[outv]" -map "[outa]" output.mp4
```

---

## 4. 播放速度调整

### 视频加速

```bash
# 2 倍速（setpts 除以倍数）
ffmpeg -i input.mp4 -filter_complex "[0:v]setpts=0.5*PTS[v]" -map "[v]" output.mp4

# 4 倍速
ffmpeg -i input.mp4 -filter_complex "[0:v]setpts=0.25*PTS[v]" -map "[v]" output.mp4
```

### 视频减速

```bash
# 0.5 倍速（慢动作）
ffmpeg -i input.mp4 -filter_complex "[0:v]setpts=2.0*PTS[v]" -map "[v]" output.mp4
```

### 音频同步变速

```bash
# 2 倍速（视频 + 音频同步）
ffmpeg -i input.mp4 -filter_complex \
  "[0:v]setpts=0.5*PTS[v]; \
   [0:a]atempo=2.0[a]" \
  -map "[v]" -map "[a]" output.mp4
```

`atempo` 取值范围 0.5-2.0。超出范围需串联：

```bash
# 4 倍速音频（atempo=2.0 * atempo=2.0）
ffmpeg -i input.mp4 -filter_complex \
  "[0:v]setpts=0.25*PTS[v]; \
   [0:a]atempo=2.0,atempo=2.0[a]" \
  -map "[v]" -map "[a]" output.mp4
```

---

## 5. 音视频合成

### 多流合并（视频 + 音频）

```bash
# 将视频和音频合并，保留原始编码
ffmpeg -i video.mp4 -i audio.mp3 -c:v copy -c:a aac -map 0:v -map 1:a output.mp4
```

### 多音频混合（amix）

```bash
# 混合两路音频（配音 + 配乐）
ffmpeg -i voiceover.wav -i bgm.mp3 \
  -filter_complex "[0:a]volume=1.0[a1];[1:a]volume=0.3[a2];[a1][a2]amix=inputs=2:duration=first[outa]" \
  -map "[outa]" output.wav
```

### 视频替换音频

```bash
ffmpeg -i video.mp4 -i new_audio.wav -c:v copy -c:a aac -map 0:v -map 1:a -shortest output.mp4
```

---

## 6. 音频延迟对齐

使用 `adelay` filter 将音频延迟到指定时间开始，用于配乐分段对齐。

### 单路音频延迟

```bash
# 音频延迟 5 秒开始
ffmpeg -i bgm.mp3 -filter_complex "[0:a]adelay=5000|5000[a]" -map "[a]" output.mp3
```

**注意**：`adelay` 的单位是毫秒。`5000|5000` 表示左右声道各延迟 5000ms。

### 多段配乐对齐

```bash
# 第一段配乐从 0 秒开始，第二段配乐从 30 秒开始，混合输出
ffmpeg -i bgm_seg1.mp3 -i bgm_seg2.mp3 \
  -filter_complex \
  "[0:a]adelay=0|0[a1]; \
   [1:a]adelay=30000|30000[a2]; \
   [a1][a2]amix=inputs=2:duration=longest[outa]" \
  -map "[outa]" output.wav
```

### 配音 + 多段配乐混合

```bash
ffmpeg -i voiceover.wav -i bgm_seg1.mp3 -i bgm_seg2.mp3 \
  -filter_complex \
  "[0:a]volume=1.0[a0]; \
   [1:a]volume=0.3,adelay=0|0[a1]; \
   [2:a]volume=0.3,adelay=30000|30000[a2]; \
   [a0][a1][a2]amix=inputs=3:duration=longest[outa]" \
  -map "[outa]" output.wav
```

---

## 7. 字幕烧录

### 使用 subtitles filter（.ass 字幕）

```bash
ffmpeg -i video.mp4 -vf "subtitles=subtitle.ass" -c:a copy output.mp4
```

### 使用 subtitles filter（.srt 字幕）

```bash
ffmpeg -i video.mp4 -vf "subtitles=subtitle.srt:force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2'" -c:a copy output.mp4
```

### .ass 样式文件示例

```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans CJK SC,72,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,1,2,80,80,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:03.00,Default,,0,0,0,,这是一段字幕
```

### 字幕烧录到竖屏视频

```bash
ffmpeg -i video.mp4 -vf "scale=1080:1920,subtitles=subtitle.ass" -c:a copy output.mp4
```

---

## 8. 分辨率/画幅转换

### 转为 9:16 竖屏（1080x1920）

```bash
# 方式一：缩放后裁剪（可能裁掉画面边缘）
ffmpeg -i input.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" -c:a copy output.mp4

# 方式二：缩放并保持比例，加黑边填充
ffmpeg -i input.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" -c:a copy output.mp4
```

### 转为 16:9 横屏（1920x1080）

```bash
ffmpeg -i input.mp4 -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080" -c:a copy output.mp4
```

### 自定义分辨率

```bash
ffmpeg -i input.mp4 -vf "scale=720x1280" -c:a copy output.mp4
```

---

## 9. 帧提取

从视频中提取单帧图片，用于跨镜头末帧参考。

### 提取指定时间的单帧

```bash
# 提取第 5 秒的画面
ffmpeg -i input.mp4 -ss 00:00:05 -frames:v 1 output_frame.png
```

### 提取最后一帧

```bash
# 先获取视频时长
DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 input.mp4)

# 提取最后 0.5 秒处的帧
ffmpeg -i input.mp4 -ss $(echo "$DURATION - 0.5" | bc) -frames:v 1 last_frame.png
```

### 按固定间隔提取多帧

```bash
# 每秒提取一帧
ffmpeg -i input.mp4 -vf "fps=1" frames/frame_%04d.png

# 每 10 帧提取一帧
ffmpeg -i input.mp4 -vf "select=not(mod(n\,10))" -vsync vfr frames/frame_%04d.png
```

---

## 10. 视频信息查询

### 获取视频时长

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 input.mp4
```

### 获取视频分辨率

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 input.mp4
```

### 获取视频编码格式

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 input.mp4
```

### 获取帧率

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 input.mp4
```

### 获取完整视频信息

```bash
ffprobe -v error -show_format -show_streams input.mp4
```

### 获取音频信息

```bash
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate,channels -of default=noprint_wrappers=1 input.mp4
```

### 获取视频码率

```bash
ffprobe -v error -show_entries format=bit_rate -of default=noprint_wrappers=1:nokey=1 input.mp4
```

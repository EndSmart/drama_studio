# 转场预设

本目录用于存放 ffmpeg 转场预设配置。

## 支持的转场类型

| 转场 | ffmpeg filter | 适用场景 |
|------|--------------|---------|
| cut | 直接拼接（concat demuxer） | 快节奏切换，默认选项 |
| fade | xfade=transition=fade:duration=0.5 | 情绪转换、时间流逝 |
| dissolve | xfade=transition=dissolve:duration=0.5 | 柔和过渡、回忆切入 |
| wipe | xfade=transition=wipeleft:duration=0.5 | 场景切换、空间转换 |
| fadeblack | xfade=transition=fadeblack:duration=0.5 | 段落分隔、章节结束 |
| fadewhite | xfade=transition=fadewhite:duration=0.5 | 闪回、梦境切入 |
| slideup | xfade=transition=slideup:duration=0.5 | 动感切换、快节奏 |

## xfade 使用示例

```bash
# 两段视频之间添加 fade 转场
ffmpeg -i clip1.mp4 -i clip2.mp4 \
  -filter_complex "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=4.5[v]" \
  -map "[v]" -c:v libx264 -preset fast -crf 23 \
  output.mp4
```

> `offset` = 第一段视频时长 - 转场时长（转场在第一段末尾开始重叠）

## 多段转场链

对于多段视频的连续转场，需要链式 xfade：

```bash
ffmpeg -i c1.mp4 -i c2.mp4 -i c3.mp4 \
  -filter_complex "
    [0:v][1:v]xfade=transition=fade:duration=0.5:offset=4.5[v01];
    [v01][2:v]xfave=transition=fade:duration=0.5:offset=9.0[vout]
  " \
  -map "[vout]" -c:v libx264 -preset fast -crf 23 \
  output.mp4
```

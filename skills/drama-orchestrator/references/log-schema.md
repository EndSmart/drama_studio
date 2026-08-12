# Log Schema — 结构化日志字段定义

> `trace/pipeline.log` 是 JSON Lines 格式的结构化日志，记录每个 Stage 的路由决策、工具调用和异常。

---

## 日志格式

每行一个 JSON 对象：

```json
{"timestamp": "<ISO-8601>", "request_id": "<uuid>", "stage": <int>, "event": "<event_type>", ...fields}
```

---

## 事件类型

### `stage_start`

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "request_id": "abc-123",
  "stage": 1,
  "event": "stage_start",
  "agent": "story-agent",
  "entry_type": "full_pipeline",
  "input_summary": {"theme_length": 25}
}
```

### `stage_complete`

```json
{
  "timestamp": "2026-01-01T00:01:00Z",
  "request_id": "abc-123",
  "stage": 1,
  "event": "stage_complete",
  "agent": "story-agent",
  "output_path": "stage1/story.md",
  "duration_seconds": 60,
  "metadata": {"genre": "romance", "expert_used": "romance-expert", "character_count": 3}
}
```

### `tool_call`

```json
{
  "timestamp": "2026-01-01T00:02:00Z",
  "request_id": "abc-123",
  "stage": 4,
  "event": "tool_call",
  "tool": "ImageGen",
  "purpose": "character_keyframe",
  "params_summary": {"prompt_length": 120, "size": "1024x1536"},
  "credits_estimate": 7.5,
  "result": "success",
  "output_path": "stage4/characters/林晓/front.png"
}
```

### `tool_call` (VideoGen)

```json
{
  "timestamp": "2026-01-01T00:03:00Z",
  "request_id": "abc-123",
  "stage": 5,
  "event": "tool_call",
  "tool": "VideoGen",
  "purpose": "video_segment",
  "params_summary": {"prompt_length": 80, "seconds": 5, "resolution": "1080P", "image_to_video": true},
  "credits_estimate": 75,
  "result": "success",
  "output_path": "stage5/clips/shot_1.mp4"
}
```

### `feedback_received`

```json
{
  "timestamp": "2026-01-01T00:04:00Z",
  "request_id": "abc-123",
  "stage": 7,
  "event": "feedback_received",
  "feedback_round": 1,
  "feedback_summary": {"type": "replace", "shot_id": 5, "reason": "角色表情不对"},
  "regenerate_triggered": true
}
```

### `regeneration`

```json
{
  "timestamp": "2026-01-01T00:05:00Z",
  "request_id": "abc-123",
  "stage": 5,
  "event": "regeneration",
  "shot_id": 5,
  "reason": "S7 feedback: 角色表情不对",
  "new_clip_path": "stage5/clips/shot_5_v2.mp4",
  "credits_used": 82.5
}
```

### `error`

```json
{
  "timestamp": "2026-01-01T00:06:00Z",
  "request_id": "abc-123",
  "stage": 5,
  "event": "error",
  "error_type": "video_gen_failed",
  "shot_id": 3,
  "error_message": "VideoGen timeout",
  "fallback_action": "retry_once"
}
```

### `pipeline_complete`

```json
{
  "timestamp": "2026-01-01T00:07:00Z",
  "request_id": "abc-123",
  "stage": 8,
  "event": "pipeline_complete",
  "final_output": "stage8/final_drama.mp4",
  "total_duration_seconds": 3600,
  "credit_tracking": {
    "estimated_total": 1200,
    "actual_total": 1185,
    "image_gen": {"calls": 24, "credits": 180},
    "video_gen": {"calls": 12, "credits": 900},
    "tts": {"calls": 12, "credits": 105}
  }
}
```

---

## 日志不记录

- 用户原文（仅记长度）
- 完整的 ImageGen/VideoGen prompt（仅记长度）
- 视频文件内容
- 角色卡完整内容（仅记路径）

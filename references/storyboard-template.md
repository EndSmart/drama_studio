# 分镜脚本模板和示例

本文档定义 storyboard.json 和 music_plan.json 的完整模板、编写规范及速查表。

---

## 1. storyboard.json 完整模板

```json
{
  "$schema": "storyboard/v1",
  "project_name": "短剧项目名称",
  "total_shots": 6,
  "target_resolution": "1080x1920",
  "target_fps": 30,

  "characters": [
    {
      "character_id": "char_001",
      "name": "角色名称",
      "character_card": "assets/characters/char_001/character_card.json",
      "reference_image": "assets/characters/char_001/ref.png"
    }
  ],

  "shots": [
    {
      "shot_id": "shot_001",
      "scene_id": "scene_01",
      "scene_description": "场景描述：地点、时间、环境",

      "shot_type": "medium",
      "camera_movement": "static",
      "duration_sec": 5,
      "transition_in": "cut",
      "transition_out": "cut",

      "characters_in_shot": ["char_001"],
      "primary_character": "char_001",

      "image_prompt": "完整的图像生成 prompt，以角色 seed_prompt 开头",
      "image_fidelity": 0.7,

      "video_prompt": "仅运动描述，不包含角色外貌",

      "dialogue": "角色台词（如有）",
      "voiceover": "旁白（如有）",

      "music_segment_id": "seg_01",
      "notes": "拍摄备注"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `shot_id` | string | 镜头唯一标识，格式 shot_XXX |
| `scene_id` | string | 所属场景标识 |
| `scene_description` | string | 场景地点、时间、环境描述 |
| `shot_type` | string | 镜头类型，见速查表 |
| `camera_movement` | string | 运镜方式，见速查表 |
| `duration_sec` | number | 镜头时长（秒） |
| `transition_in` | string | 入场转场，见速查表 |
| `transition_out` | string | 出场转场，见速查表 |
| `characters_in_shot` | array | 出场角色 ID 列表 |
| `primary_character` | string | 主要角色 ID（用于 reference_image 选择） |
| `image_prompt` | string | ImageGen 图生图 prompt |
| `image_fidelity` | number | input_fidelity 值 (0.0-1.0) |
| `video_prompt` | string | VideoGen 运动描述 prompt |
| `dialogue` | string | 角色台词 |
| `voiceover` | string | 旁白 |
| `music_segment_id` | string | 关联的 music_plan segment ID |

---

## 2. 完整分镜示例

以下是一个 6 镜头短剧片段，展示不同 shot_type/camera_movement/music_mood 的用法。

```json
{
  "$schema": "storyboard/v1",
  "project_name": "重逢",
  "total_shots": 6,
  "target_resolution": "1080x1920",
  "target_fps": 30,

  "characters": [
    {
      "character_id": "char_001",
      "name": "林晓",
      "character_card": "assets/characters/char_001/character_card.json",
      "reference_image": "assets/characters/char_001/ref.png"
    },
    {
      "character_id": "char_002",
      "name": "陈默",
      "character_card": "assets/characters/char_002/character_card.json",
      "reference_image": "assets/characters/char_002/ref.png"
    }
  ],

  "shots": [
    {
      "shot_id": "shot_001",
      "scene_id": "scene_01",
      "scene_description": "傍晚，城市公园小径，金色夕阳透过树叶洒下斑驳光影",
      "shot_type": "wide",
      "camera_movement": "static",
      "duration_sec": 4,
      "transition_in": "fade",
      "transition_out": "cut",
      "characters_in_shot": ["char_001"],
      "primary_character": "char_001",
      "image_prompt": "25-year-old Asian woman, long straight black hair, oval face, almond-shaped brown eyes, fair skin, slim build, wearing a white cotton blouse with collar and dark navy slim trousers, walking alone on a tree-lined park path during golden hour, warm sunset light filtering through leaves creating dappled shadows, wide establishing shot, cinematic photorealistic style",
      "image_fidelity": 0.7,
      "video_prompt": "The woman walks slowly along the path, leaves rustle gently in the breeze, warm sunlight shifts through the canopy",
      "dialogue": "",
      "voiceover": "三年了，我又回到了这座城市。",
      "music_segment_id": "seg_01",
      "notes": "开场镜头，建立场景氛围，慢节奏"
    },
    {
      "shot_id": "shot_002",
      "scene_id": "scene_01",
      "scene_description": "傍晚，城市公园小径，金色夕阳",
      "shot_type": "medium",
      "camera_movement": "tracking",
      "duration_sec": 5,
      "transition_in": "cut",
      "transition_out": "cut",
      "characters_in_shot": ["char_001"],
      "primary_character": "char_001",
      "image_prompt": "25-year-old Asian woman, long straight black hair, oval face, almond-shaped brown eyes, fair skin, slim build, wearing a white cotton blouse with collar and dark navy slim trousers, walking on a park path, golden hour lighting, side profile medium shot, cinematic photorealistic style",
      "image_fidelity": 0.8,
      "video_prompt": "Camera tracks alongside the woman as she walks, her hair sways gently with each step, she looks ahead thoughtfully",
      "dialogue": "",
      "voiceover": "",
      "music_segment_id": "seg_01",
      "notes": "跟拍镜头，展示角色行进状态"
    },
    {
      "shot_id": "shot_003",
      "scene_id": "scene_01",
      "scene_description": "傍晚，城市公园长椅旁",
      "shot_type": "closeup",
      "camera_movement": "zoom_in",
      "duration_sec": 4,
      "transition_in": "cut",
      "transition_out": "dissolve",
      "characters_in_shot": ["char_001"],
      "primary_character": "char_001",
      "image_prompt": "25-year-old Asian woman, long straight black hair, oval face, almond-shaped brown eyes, fair skin, slim build, wearing a white cotton blouse with collar and dark navy slim trousers, standing still near a park bench, expression of surprise and recognition, golden hour warm light on face, close-up shot, shallow depth of field, cinematic photorealistic style",
      "image_fidelity": 0.85,
      "video_prompt": "The woman stops abruptly, her eyes widen in surprise, camera slowly pushes in on her face",
      "dialogue": "陈默？",
      "voiceover": "",
      "music_segment_id": "seg_02",
      "notes": "关键情绪转折点，切到紧张配乐"
    },
    {
      "shot_id": "shot_004",
      "scene_id": "scene_01",
      "scene_description": "傍晚，城市公园，林晓视角看向前方",
      "shot_type": "medium",
      "camera_movement": "static",
      "duration_sec": 4,
      "transition_in": "dissolve",
      "transition_out": "cut",
      "characters_in_shot": ["char_002"],
      "primary_character": "char_002",
      "image_prompt": "32-year-old Asian man, short undercut black hair, square jawline, narrow monolid eyes, light olive skin, athletic build, wearing a charcoal grey overcoat over a black turtleneck, standing on a park path, warm golden hour backlight creating a rim light effect, medium shot, cinematic photorealistic style",
      "image_fidelity": 0.8,
      "video_prompt": "The man turns his head toward camera, a faint smile appears on his face, he takes one step forward",
      "dialogue": "好久不见。",
      "voiceover": "",
      "music_segment_id": "seg_02",
      "notes": "反打镜头，切换到男主角"
    },
    {
      "shot_id": "shot_005",
      "scene_id": "scene_01",
      "scene_description": "傍晚，城市公园，两人面对面",
      "shot_type": "wide",
      "camera_movement": "static",
      "duration_sec": 5,
      "transition_in": "cut",
      "transition_out": "cut",
      "characters_in_shot": ["char_001", "char_002"],
      "primary_character": "char_001",
      "image_prompt": "25-year-old Asian woman, long straight black hair, oval face, almond-shaped brown eyes, fair skin, slim build, wearing a white cotton blouse with collar and dark navy slim trousers, standing face to face with a 32-year-old Asian man with short undercut black hair, square jawline, narrow monolid eyes, wearing a charcoal grey overcoat over a black turtleneck, park path at golden hour, two-shot wide framing, cinematic photorealistic style",
      "image_fidelity": 0.7,
      "video_prompt": "Both characters stand still facing each other, a gentle breeze moves the leaves behind them, neither speaks",
      "dialogue": "",
      "voiceover": "",
      "music_segment_id": "seg_02",
      "notes": "双人镜头，使用主角 reference_image，配角文字描述"
    },
    {
      "shot_id": "shot_006",
      "scene_id": "scene_01",
      "scene_description": "傍晚，城市公园，两人面对面近景",
      "shot_type": "extreme_closeup",
      "camera_movement": "static",
      "duration_sec": 3,
      "transition_in": "cut",
      "transition_out": "fade",
      "characters_in_shot": ["char_001"],
      "primary_character": "char_001",
      "image_prompt": "25-year-old Asian woman, long straight black hair, oval face, almond-shaped brown eyes, fair skin, slim build, wearing a white cotton blouse with collar and dark navy slim trousers, extreme close-up on eyes, a single tear forming, golden hour light reflecting in her eyes, cinematic photorealistic style",
      "image_fidelity": 0.9,
      "video_prompt": "A single tear rolls down slowly, eyes blink once, slight tremor in the lips",
      "dialogue": "",
      "voiceover": "有些话，迟了三年。",
      "music_segment_id": "seg_03",
      "notes": "结尾情绪高潮，极致特写，切到抒情配乐"
    }
  ]
}
```

---

## 3. image_prompt 编写模板和示例

### 模板

```
{seed_prompt}, {scene_description}, {lighting}, {shot_type_composition}, {emotional_note}, cinematic photorealistic style
```

### 要素分解

| 要素 | 说明 | 示例 |
|------|------|------|
| seed_prompt | 角色卡中的不可变前缀 | `25-year-old Asian woman, long straight black hair, ...` |
| scene_description | 当前镜头的场景描述 | `standing in a sunlit hospital corridor` |
| lighting | 光线描述 | `soft warm natural light from left window` |
| shot_type_composition | 构图和镜头类型 | `medium shot, shallow depth of field` |
| emotional_note | 情绪/表情提示 | `with a determined expression` |
| style | 统一风格后缀 | `cinematic photorealistic style` |

### 示例 1：单人特写

```
25-year-old Asian woman, long straight black hair, oval face, almond-shaped brown eyes, fair skin, slim build, wearing a white cotton blouse with collar and dark navy slim trousers, sitting alone in a dimly lit cafe, warm amber light from a small table lamp, close-up shot, expression of quiet contemplation, cinematic photorealistic style
```

### 示例 2：多角色中景

```
25-year-old Asian woman, long straight black hair, oval face, almond-shaped brown eyes, fair skin, slim build, wearing a white cotton blouse with collar and dark navy slim trousers, standing face to face with a 32-year-old Asian man with short undercut black hair, square jawline, narrow monolid eyes, wearing a charcoal grey overcoat, modern office interior with large windows, cool fluorescent overhead lighting, medium two-shot, cinematic photorealistic style
```

### 示例 3：换装镜头

```
25-year-old Asian woman, long straight black hair, oval face, almond-shaped brown eyes, fair skin, slim build, wearing a red evening gown with thin straps, standing in a grand hotel lobby, warm chandelier light, full body wide shot, confident posture, cinematic photorealistic style
```

### 编写原则

- 始终以 `seed_prompt` 开头，原样拼接，不修改任何字符。
- 场景描述包含：地点、时间、环境细节。
- 光线描述具体到光源方向和色温。
- 不使用模糊的情绪词（如 "happy"），使用具体表情描述（如 "a subtle smile"）。
- 所有镜头以统一风格后缀结尾。

---

## 4. video_prompt 编写模板和示例

### 模板

```
{character_action}, {camera_movement_description}, {environment_dynamics}
```

### 要素分解

| 要素 | 说明 | 示例 |
|------|------|------|
| character_action | 角色动作/表情变化 | `The woman walks forward slowly` |
| camera_movement_description | 镜头运动 | `camera tracks forward following her` |
| environment_dynamics | 环境动态 | `sunlight shifts through the windows` |

### 示例 1：行走 + 跟拍

```
The woman walks forward slowly along the corridor, camera tracks alongside her, her hair sways gently with each step, sunlight shifts through the windows
```

### 示例 2：静止 + 推进

```
The woman stands still, her eyes widen in surprise, camera slowly pushes in on her face, subtle dust particles float in the light beam
```

### 示例 3：对话 + 静止

```
Both characters stand still facing each other, the man slightly nods his head, a gentle breeze moves the leaves behind them
```

### 编写原则

- **仅描述运动和变化**，不重复角色外貌特征。
- 使用现在时态。
- 角色动作和镜头运动分开描述。
- 如果镜头完全静止且角色无动作，描述环境的微小动态（如光线变化、风吹）。
- 不包含任何角色年龄、发型、服装等外貌信息。

---

## 5. music_plan.json 完整模板和示例

### 模板

```json
{
  "$schema": "music_plan/v1",
  "project_name": "短剧项目名称",
  "total_duration_sec": 120,
  "voiceover_volume": 1.0,
  "bgm_volume": 0.3,

  "segments": [
    {
      "id": "seg_001",
      "start_time": 0,
      "duration": 30,
      "mood": "calm",
      "tempo": "slow",
      "genre": "cinematic",
      "instruments": ["piano", "strings"],
      "music_source": "suno",
      "music_file": "assets/music/segments/seg_001.mp3",
      "suno_prompt": "cinematic, calm, slow tempo, featuring piano and strings, no vocals, background music"
    }
  ]
}
```

### 完整示例

对应上方分镜示例的 music_plan.json：

```json
{
  "$schema": "music_plan/v1",
  "project_name": "重逢",
  "total_duration_sec": 25,
  "voiceover_volume": 1.0,
  "bgm_volume": 0.3,

  "segments": [
    {
      "id": "seg_01",
      "start_time": 0,
      "duration": 9,
      "mood": "melancholic",
      "tempo": "slow",
      "genre": "cinematic ambient",
      "instruments": ["piano", "cello"],
      "music_source": "suno",
      "music_file": "assets/music/segments/seg_01.mp3",
      "suno_prompt": "cinematic ambient, melancholic, slow tempo, featuring piano and cello, no vocals, background music for drama scene"
    },
    {
      "id": "seg_02",
      "start_time": 9,
      "duration": 13,
      "mood": "tense",
      "tempo": "moderate",
      "genre": "cinematic thriller",
      "instruments": ["strings", "percussion"],
      "music_source": "suno",
      "music_file": "assets/music/segments/seg_02.mp3",
      "suno_prompt": "cinematic thriller, tense, moderate tempo, featuring strings and subtle percussion, no vocals, suspenseful background music"
    },
    {
      "id": "seg_03",
      "start_time": 22,
      "duration": 3,
      "mood": "emotional",
      "tempo": "slow",
      "genre": "cinematic",
      "instruments": ["piano", "violin"],
      "music_source": "royalty_free",
      "music_file": "assets/music/segments/seg_03.mp3",
      "suno_prompt": "cinematic, emotional, slow tempo, featuring solo piano and violin, no vocals, touching background music"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_duration_sec` | number | 视频总时长（秒），用于验证分段覆盖完整 |
| `voiceover_volume` | number | 配音音量（默认 1.0） |
| `bgm_volume` | number | 配乐音量（默认 0.3） |
| `id` | string | 分段唯一标识，对应 storyboard 中的 music_segment_id |
| `start_time` | number | 分段起始时间（秒），用于 adelay 对齐 |
| `duration` | number | 分段时长（秒） |
| `mood` | string | 情绪描述 |
| `tempo` | string | 速度：slow / moderate / fast |
| `genre` | string | 音乐风格 |
| `instruments` | array | 乐器列表 |
| `music_source` | string | 来源：suno / royalty_free / user_upload |
| `music_file` | string | 音频文件路径 |
| `suno_prompt` | string | Suno 生成用的 prompt（仅 suno 来源时使用） |

---

## 6. 镜头类型速查表

| shot_type | 画面范围 | 适用场景 | 注意事项 |
|-----------|---------|---------|---------|
| `extreme_closeup` | 面部局部（眼睛、嘴唇） | 极致情绪表达、关键细节强调 | input_fidelity 设为 0.85-0.9，面部特征必须精确 |
| `closeup` | 面部及肩部 | 情绪表达、对话反应、角色识别 | input_fidelity 设为 0.8-0.9 |
| `medium` | 腰部以上 | 对话场景、日常互动、角色动作 | input_fidelity 设为 0.6-0.8 |
| `wide` | 全身及环境 | 场景建立、环境交代、人物关系 | input_fidelity 设为 0.5-0.7，侧重场景一致性 |
| `extreme_wide` | 远景，人物为画面中小点 | 开场全景、大场面、结尾收束 | input_fidelity 设为 0.4-0.6，侧重环境 |

### 选择原则

- 开场第一个镜头通常用 `wide` 或 `extreme_wide` 建立场景。
- 情绪高潮用 `closeup` 或 `extreme_closeup`。
- 对话场景在 `medium` 和 `closeup` 之间切换（正反打）。
- 同一场景内避免连续使用相同 shot_type，通过类型切换创造节奏感。

---

## 7. 运镜速查表

| camera_movement | 运动方式 | 适用场景 | 注意事项 |
|----------------|---------|---------|---------|
| `static` | 镜头静止 | 对话反应、情绪凝视、静态环境 | video_prompt 中描述环境动态代替镜头运动 |
| `pan` | 水平摇摄 | 展示全景、跟随移动角色、揭示新信息 | 在 video_prompt 中说明方向：pan left / pan right |
| `tilt` | 垂直摇摄 | 从上到下或从下到上展示、揭示角色全貌 | 在 video_prompt 中说明方向：tilt up / tilt down |
| `zoom_in` | 推进放大 | 强调情绪、聚焦细节、制造紧张感 | 缓慢推进配合情绪升级 |
| `zoom_out` | 拉远缩小 | 揭示全貌、疏离感、结尾收束 | 配合情绪淡化或场景交代 |
| `tracking` | 跟随移动 | 角色行走/奔跑、沉浸式跟随 | 在 video_prompt 中说明方向：track left / track right / track forward |

### 选择原则

- `static` 是默认选择，适用于大多数对话和情绪镜头。
- 角色移动时使用 `tracking` 或 `pan`。
- 情绪转折点使用 `zoom_in` 制造压迫感。
- 场景结尾使用 `zoom_out` 制造疏离或收束感。
- 避免无意义的运镜，每次运镜都应有叙事目的。

---

## 8. 转场速查表

| transition | 效果 | 适用场景 | ffmpeg 实现 |
|-----------|------|---------|------------|
| `cut` | 直接切换 | 正反打对话、快节奏叙事、同场景连续镜头 | concat demuxer 直接拼接 |
| `fade` | 淡入/淡出（黑场） | 场景切换、时间跳跃、开场/结尾 | `xfade=transition=fade:duration=1:offset=N` |
| `dissolve` | 溶解叠加 | 回忆闪回、梦境、情绪过渡 | `xfade=transition=dissolve:duration=1:offset=N` |
| `wipe` | 擦除过渡 | 场景跳转、时间快速流逝、风格化切换 | `xfade=transition=wipeleft:duration=0.5:offset=N` |

### 选择原则

- `cut` 是默认转场，适用于 80% 的镜头切换。
- 同场景内的镜头切换一律使用 `cut`。
- 不同场景之间使用 `fade` 或 `dissolve`。
- 回忆/闪回使用 `dissolve`。
- 开场第一个镜头用 `fade`（从黑场淡入）。
- 结尾最后一个镜头用 `fade`（淡出到黑场）。
- `wipe` 谨慎使用，仅用于特殊风格化需求。
- 转场持续时间：`fade` 和 `dissolve` 通常 0.5-1.5 秒，`wipe` 通常 0.3-0.5 秒。

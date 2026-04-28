# 2D Pixel Art Sprite 生成流程文档

> 适用仓库：[BuildAndRelease/agent-sprite-forge](https://github.com/BuildAndRelease/agent-sprite-forge)  
> 核心 skill：`skills/generate2dsprite`  
> 作者：铃铛（OpenClaw）  
> 最后更新：2026-04-28

---

## 背景与整体思路

原版 `generate2dsprite` skill 依赖 Codex 内置的 `image_gen` 工具生成图片，无法在其他 AI 运行环境（如 OpenClaw、Claude Code 等）中复用。

本次改造将图片生成步骤替换为调用 **Nano Banana Pro API**（`aiapi.uu.cc`，模型 `gemini-3-pro-image-preview`），并通过一个轻量 Python 脚本 `nanobananagen.py` 封装，从而让任何能执行 Python 脚本的 Agent 都可以独立完成完整的 sprite 生成+后处理流程。

```
用户描述 → Agent 推断参数 → 构造 Prompt → nanobananagen.py 调 API → 得到原始 PNG
         ↓
generate2dsprite.py 后处理（去品红背景 + 分帧 + 对齐 + QC + GIF 导出）
         ↓
输出完整资源包（透明 sheet / 分帧 PNG / 动画 GIF / meta）
```

---

## 目录结构

```
skills/generate2dsprite/
├── SKILL.md                        # Agent 读取的 skill 配置（含规则和流程）
├── references/
│   ├── modes.md                    # 资源类型、动作、bundle 选择参考
│   └── prompt-rules.md             # 手写 prompt 规范
└── scripts/
    ├── nanobananagen.py            # ← 新增：调用 Nano Banana Pro API 生图
    └── generate2dsprite.py         # 本地后处理：去背景 / 分帧 / QC / GIF
```

---

## 第一步：让 Agent 推断资源计划

**不要要求用户手动指定格子数、帧数或 bundle 结构**，让 Agent 自行从自然语言请求中推断。

### 参数集

| 参数 | 可选值 | 说明 |
|------|--------|------|
| `asset_type` | `player` / `npc` / `creature` / `character` / `spell` / `projectile` / `impact` / `prop` / `summon` / `fx` | 资源类型 |
| `action` | `idle` / `cast` / `attack` / `hurt` / `combat` / `walk` / `run` / `hover` / `projectile` / `impact` / `explode` / `death` / `single` | 动作类型 |
| `view` | `topdown` / `side` / `3/4` | 视角 |
| `sheet` | `auto` / `1x4` / `2x2` / `2x3` / `3x3` / `4x4` | 表格形状 |
| `bundle` | `single_asset` / `unit_bundle` / `spell_bundle` / `combat_bundle` / `line_bundle` | 资源包组合 |
| `effect_policy` | `all` / `largest` | 处理独立 FX 的策略 |
| `anchor` | `center` / `bottom` / `feet` | 对齐基准 |
| `reference` | `none` / `attached_image` / `generated_image` / `local_file` | 参考图来源 |

### 推断示例

| 用户说 | Agent 推断 |
|--------|-----------|
| "给我一个可控英雄的四方向行走" | `player` + `4x4` + `walk` |
| "治愈师 NPC 的待机动画" | `npc` + `unit_bundle` 或 `single_asset` + `idle` |
| "大型 BOSS 的待机循环" | `creature` + `idle` + `3x3` |
| "法师扔魔法球" | `spell_bundle`（法师施法表 + 抛射物循环 + 命中爆炸） |
| "一组怪物进化线" | `line_bundle`（1-3 形态，每形态按需输出） |

---

## 第二步：手写 Prompt

**规则**：Agent 自己写 prompt，不要交给脚本。参考 `references/prompt-rules.md`。

### 全局硬性约束（每次必须写进去）

```
- 背景必须是 100% 纯平品红 #FF00FF，无渐变
- 无文字、无标签、无 UI、无对话框
- 格子数量完全精确（如"恰好 2x2 四格"）
- 格子间无边框或分割线
- 所有帧的主体 identity 一致
- 所有帧相同边界框、相同像素比例
- 任何部位（尾巴、翅膀、弹道、火花）不得超出格子边缘
```

### 含参考图时的额外规则

```
1. 先让模型"看到"参考图（API 支持图片输入则直接传；本地路径需先读取/描述）
2. 说明参考图的用途：保持 identity / 创建同角色动画 / 进化变体 / 派生道具 FX
3. 声明哪些元素不变：轮廓族、调色盘、脸/眼特征、服装、材质语言
4. 声明哪些元素可以变：姿势、动画相位、进化特征、FX 强度
5. 仍然要求品红背景和格子封闭
```

### 快速 Prompt 模板

```
一张 <行>x<列> 的像素艺术 <资源类型> 动画表。
<主体描述>。
[可选：以刚才展示的图片作为视觉参考，保持 <固定特征> 不变，只改变 <可变部分>。]
帧描述：[帧1内容] / [帧2内容] / [帧N内容]。
背景必须是 100% 纯品红 #FF00FF，无渐变。
所有帧相同尺寸和像素比例，完全封闭在格子内，四边留品红边距。
无任何文字和标签。
```

### 常用 Sheet 默认值

| 动作 | 推荐 Sheet |
|------|-----------|
| `idle`（普通角色） | `2x2` |
| `idle`（大型怪物/BOSS） | `3x3` |
| `cast` | `2x3` |
| `projectile` | `1x4` |
| `impact` / `explode` | `2x2` |
| `walk`（俯视 4 方向） | `4x4` |
| `walk`（侧视） | `2x2` |

---

## 第三步：调用 Nano Banana Pro API 生图

### nanobananagen.py 的作用

这是一个无外部依赖（只用标准库）的 Python 脚本，封装了对 `aiapi.uu.cc` 的调用，解析响应中的 base64 图片，保存为 PNG 文件。

### 安装依赖

无 pip 依赖，纯标准库。确保 Python 3.8+ 可用即可。

### 获取 API Key

前往 [aiapi.uu.cc](https://aiapi.uu.cc) 注册，获取 API Key，支持 OpenAI 兼容接口，模型选 `gemini-3-pro-image-preview`。

### 调用方式

```bash
# 设置 API Key（不要硬编码在脚本或文件里）
export AIAPI_UU_CC_KEY="sk-你的key"

# 方式一：直接传 prompt
python3 skills/generate2dsprite/scripts/nanobananagen.py \
  --prompt "A 2x2 pixel art idle animation sheet of a small fire sprite ..." \
  --output output/raw-sheet.png

# 方式二：从文件读 prompt（适合 prompt 很长的情况）
python3 skills/generate2dsprite/scripts/nanobananagen.py \
  --prompt "$(cat prompt-used.txt)" \
  --output output/raw-sheet.png

# 也可以显式指定 key
python3 skills/generate2dsprite/scripts/nanobananagen.py \
  --prompt "..." \
  --output output/raw-sheet.png \
  --api-key sk-你的key
```

### 脚本工作原理（简述）

1. 用 `urllib.request`（标准库）向 `https://aiapi.uu.cc/v1/chat/completions` 发 POST
2. 模型返回 Markdown 格式中内嵌 `data:image/png;base64,...` 的图片数据
3. 脚本 regex 提取 base64，解码后写入指定 PNG 文件
4. 将文件路径打印到 stdout（方便 pipeline 使用）

### 安全提醒

- **绝对不要把 API Key 写进 prompt 文本、脚本文件、或提交到 git**
- 使用环境变量 `AIAPI_UU_CC_KEY` 或通过 `--api-key` 在命令行传入
- 生产环境中考虑通过 secret manager（如 1Password CLI）注入

---

## 第四步：本地后处理

使用 `generate2dsprite.py process` 对原始 PNG 做以下处理：

- **去品红背景**（chroma-key）
- **分帧提取**（按 rows/cols 切格）
- **等比缩放 / 共享比例对齐**（`--shared-scale` 保证所有帧大小一致）
- **component 过滤**（`--component-mode largest` 去掉游离的 FX 噪点）
- **边缘接触检测 QC**
- **导出透明 sheet、分帧 PNG、动画 GIF**

### 最小调用示例

```bash
python3 skills/generate2dsprite/scripts/generate2dsprite.py process \
  --input output/raw-sheet.png \
  --target asset \
  --mode idle \
  --rows 2 --cols 2 \
  --output-dir output/
```

### 关键参数说明

| 参数 | 说明 |
|------|------|
| `--target` | `asset` / `creature` / `npc` / `player` |
| `--mode` | 与 action 对应，如 `idle` / `walk` / `cast` |
| `--rows` / `--cols` | 手动指定 sheet 格子行列数 |
| `--fit-scale` | 缩放系数（让角色在格子里恰好合适） |
| `--align` | 对齐方式：`center` / `bottom` / `feet` |
| `--shared-scale` | 所有帧共享同一比例（推荐多帧动画默认开启） |
| `--component-mode` | `all`（保留全部）/ `largest`（只保留最大连通体，去游离噪点） |
| `--component-padding` | 最大连通体外扩 padding（px） |
| `--reject-edge-touch` | 若帧内容碰到格子边缘就报错并拒绝 |
| `--edge-touch-margin` | 边缘接触判定的容忍范围（px） |
| `--duration` | GIF 帧间隔（毫秒） |

---

## 第五步：QC 检查

后处理完成后，检查以下几点：

| 问题 | 处置方式 |
|------|---------|
| 帧内容碰到格子边缘 | 加 `--fit-scale`（缩小主体），或重新生图（prompt 里再强调封闭约束） |
| 各帧大小不一致 | 开启 `--shared-scale` |
| 游离 FX 噪点干扰主体对齐 | 改用 `--component-mode largest` |
| 帧间主体 identity 漂移 | 重新生图，prompt 里强调所有帧相同边界框 |
| GIF 播放卡顿 | 调整 `--duration`（默认约 150ms/帧） |

---

## 第六步：输出物清单

### 单张 sheet（`single_asset`）

```
output/
├── raw-sheet.png           # API 直出原始图
├── raw-sheet-clean.png     # 去品红后
├── sheet-transparent.png   # 透明背景合并 sheet
├── frame-00.png            # 分帧
├── frame-01.png
├── ...
├── animation.gif           # 动画预览
├── prompt-used.txt         # 使用的 prompt（留存）
└── pipeline-meta.json      # QC 元数据
```

### 玩家 sheet（`player_sheet`，`4x4`）

```
output/
├── sheet-transparent.png   # 透明 4x4 总表
├── frame-00.png ~ frame-15.png
├── strip-down.png          # 方向分条
├── strip-left.png
├── strip-right.png
├── strip-up.png
├── walk-down.gif
├── walk-left.gif
├── walk-right.gif
└── walk-up.gif
```

### Bundle（`spell_bundle` / `unit_bundle`）

每个子资源单独一个文件夹，结构同上。

---

## 迁移到其他 OpenClaw 实例

### 准备工作

1. **克隆仓库**（或直接 fork [BuildAndRelease/agent-sprite-forge](https://github.com/BuildAndRelease/agent-sprite-forge)）

```bash
git clone git@github.com:BuildAndRelease/agent-sprite-forge.git
```

2. **安装 Python 依赖**（后处理脚本需要）

```bash
pip install Pillow numpy
```

3. **设置 API Key**

```bash
export AIAPI_UU_CC_KEY="sk-你的key"
```

或者在 OpenClaw 的 workspace 里配置到 `.env` / secrets 管理。

4. **注册 skill**（如果你的 OpenClaw 支持 skill 加载）

把 `skills/generate2dsprite/` 目录整个放到 OpenClaw 识别的 skills 路径下，并确保 `SKILL.md` 的 `description` 字段准确描述 skill 用途（Agent 通过这个 description 决定什么时候用这个 skill）。

### 验证安装

```bash
# 确认脚本可运行
python3 skills/generate2dsprite/scripts/nanobananagen.py --help
python3 skills/generate2dsprite/scripts/generate2dsprite.py --help

# 快速冒烟测试（会消耗一次 API 调用）
export AIAPI_UU_CC_KEY="sk-..."
python3 skills/generate2dsprite/scripts/nanobananagen.py \
  --prompt "A 2x2 pixel art idle animation sheet of a glowing blue orb, solid magenta #FF00FF background, 2 rows 2 columns, no text, no labels." \
  --output /tmp/test-sprite.png && echo "OK: $(du -h /tmp/test-sprite.png)"
```

---

## 常见问题

**Q: API 返回结果里没有图片怎么办？**  
A: 检查 prompt 是否过于复杂或违反模型内容策略。也可以先用 `curl` 直接测一下 API 是否正常。脚本会打印 `Content preview` 帮助排查。

**Q: 后处理后透明 sheet 大量空帧？**  
A: 说明原始图里主体没有在正确格子位置，或品红比例不准。先检查 `raw-sheet-clean.png` 是否干净。

**Q: 想支持参考图怎么办？**  
A: `nanobananagen.py` 目前是纯文本 prompt 接口。如果 `aiapi.uu.cc` 的 `gemini-3-pro-image-preview` 支持图片输入（OpenAI vision 格式），可扩展脚本的 `messages` 字段，在 `content` 中加入 `{"type": "image_url", ...}` 条目。

**Q: 想换其他模型（如 GPT-4o image）？**  
A: 修改 `nanobananagen.py` 的 `BASE_URL` 和 `DEFAULT_MODEL`，以及响应解析逻辑（不同模型的输出格式可能不同）。

---

## 参考链接

- 仓库：https://github.com/BuildAndRelease/agent-sprite-forge
- 原始仓库：https://github.com/0x0funky/agent-sprite-forge
- Nano Banana Pro API：https://aiapi.uu.cc

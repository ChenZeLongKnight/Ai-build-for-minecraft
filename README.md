# Ai-build-for-minecraft

对 AI 说"帮我设计一座日式拱门"，它在三维体素设计器中自己建模；说"建"，蓝图落进你的世界；说"屋顶换个材质"，它只动需要动的方块。你负责提需求和看效果，其余全部交给 agent。

具体来说，它能做三件事：

- **根据你的描述设计蓝图。** 一句话需求，AI 在网页体素设计器中自主完成三维建模并截图自查；也可以把现成的建模文件转换成蓝图，或者把一张照片直接还原成像素建筑。
- **根据你的蓝图完成建筑。** 蓝图一次性写入世界，想看过程还可以切换表演模式，由工人机器人现场回放；建造结果逐方块回读验收，一块不差。
- **根据你的需求完成建筑微调。** 只计算新旧蓝图的最小差异并写入变化的部分，材质替换一键完成，不做整体重建。

**首次使用请先运行 mc-env 技能完成环境配置。** 全部操作通过 minecraft-mcp-server 提供的 MCP 工具连接游戏，蓝图文件是贯穿设计、建造、修改的唯一数据源。

## 整体架构

```
mc-env（环境配置与体检，首次使用先执行）
        ↓ 环境就绪后
mc-design                     mc-build                      mc-modify
┌──────────────────┐   蓝图   ┌───────────────────┐  差量补丁 ┌──────────────────┐
│ 网页设计器、      │ ──────→ │ 秒落（默认）或      │ ───────→ │ 差量计算后仅写入   │
│ 既有文件转换或    │         │ 表演模式回放，      │          │ 差异格，再同步     │
│ 图片还原产出      │         │ 逐格回读验收        │          │ 蓝图并验收         │
│ JSON 与 litematic│         │                   │          │                  │
└──────────────────┘         └───────────────────┘          └──────────────────┘
```

你在游戏里按 F2 截图查看实际观感，满意即交付，不满意回到 mc-modify 继续调。

## 技能构成

| 技能 | 职责 |
|------|------|
| mc-env | 环境配置与体检，第一次使用时先执行 |
| mc-design | 体素设计与蓝图产出，含自主设计与图片还原两条路线 |
| mc-build | 落地建造与验收 |
| mc-modify | 差量微调 |

每个技能目录内的 SKILL.md 是完整说明书，设计器的 AI 接口、转换脚本的用法、建造与验收的细则、差量计算的规则等全部细节都在里面。

## 快速开始

环境怎么准备、两种上手方式（让 Agent 带着配置，或自己照清单手动配置），见 [`环境配置.md`](环境配置.md)。安装技能，以 WorkBuddy 为例：

```bash
git clone https://github.com/ChenZeLongKnight/Ai-build-for-minecraft.git
cp -r Ai-build-for-minecraft/mc-env \
      Ai-build-for-minecraft/mc-design \
      Ai-build-for-minecraft/mc-build \
      Ai-build-for-minecraft/mc-modify \
      ~/.workbuddy/skills/
```

前置依赖：Minecraft Java 版（已在 1.21.1 完整验证），单人世界对局域网开放并开启作弊；[minecraft-mcp-server-blueprint](https://github.com/ChenZeLongKnight/minecraft-mcp-server-blueprint) 作为连接游戏的 MCP 引擎，注意必须使用本仓库，不要安装官方原版，原版没有蓝图工具；[browser-use](https://github.com/browser-use/browser-use) 浏览器自动化 MCP；图片还原路线另需 Python 3.10 以上与若干依赖包，模型权重见 [`models/README.md`](models/README.md)，仓库内附轻量版开箱可用。

## 演示

**日式拱门：设计器蓝图与实际建造对比。**

<p align="center">
  <img src="docs/images/japanese_gate_blueprint.png" width="45%" alt="日式拱门蓝图" />
  <img src="docs/images/japanese_gate_in_game.jpg" width="45%" alt="日式拱门游戏内效果" />
</p>

**小型宫殿：AI 自主设计与落地微调。**

<p align="center">
  <img src="docs/images/palace_designer.jpg" width="45%" alt="设计器中的小型宫殿" />
  <img src="docs/images/palace_in_game.jpg" width="45%" alt="小型宫殿游戏内效果" />
</p>

**建筑群。** 图中全部建筑均由智能体自主设计并建造完成。

![智能体自主设计建造的建筑群](docs/images/agent_built_village.jpg)

**建造者 XiaoBuddy。** 由 WorkBuddy 驱动的建筑师机器人，正在游戏中接收指令。

![建筑师机器人 XiaoBuddy](docs/images/xiaobuddy.png)

**图片还原：照片自动转建筑。** 一张猫的照片经脚本自动还原后写入世界：脚本自己识别主体、剔除背景、逐格配色、生成蓝图并建造，游戏内与原图一一对应。

<p align="center">
  <img src="docs/images/cat_image_restore_in_game.jpg" width="45%" alt="照片还原的猫在游戏内的效果" />
  <img src="docs/images/cat_image_restore_source.jpg" width="45%" alt="原始猫照片" />
</p>

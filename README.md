# Ai-build-for-minecraft

Minecraft AI 建筑流水线：一组面向 AI Agent 的技能（Skill），使智能体能够在 Minecraft Java 版中自主完成建筑的体素设计、落地建造与后续微调。全部操作通过 minecraft-mcp-server 提供的 MCP 工具连接游戏，蓝图文件（JSON 与 litematic）作为唯一数据源，贯穿设计、建造、修改三个阶段。

## 设计输入的三种方式

本流水线支持三种产生蓝图的方式，覆盖"AI 从零设计""复用既有建模文件""把现成图片还原成建筑"三类需求。

### 方式一：由既有建模文件生成

当用户已持有其他工具产出的建模文件时，可以直接复用，无需重新设计。目前支持 Litematica 的 `.litematic`、WorldEdit 的 `.schem` 以及 Sponge 结构方块 `.nbt` 三种格式。

处理流程为：将建模文件复制入引擎蓝图库，调用 `convert_litematic` 工具将其解析为标准蓝图 JSON；随后核对方块总数与元数据是否在转换中保持一致，并在落地前扫描调色板，确认文件中不包含当前游戏版本无法识别的方块（若包含，需先生成替换补丁）。转换完成后的 JSON 与手工设计的蓝图具有同等地位，可直接进入建造阶段。

这一方式适用于复刻社区分享的建筑、迁移其他存档的作品，或将外部设计工具的产出纳入统一流程。

### 方式二：AI 通过网页设计器建模（推荐方式）

这是本流水线的主要设计方式。技能内置一个网页体素设计器（`voxel_designer.html`，基于 Three.js，双击即可在本地打开，无任何网络依赖），AI 通过浏览器自动化工具操控该页面，在真正的三维仿真环境中完成设计与自查，而不是在文字中凭空推算坐标。

设计器的核心是一套面向 AI 的程序化接口 `window.vd`，提供十五个方法，覆盖体素摆放（`build`）、画布清空（`clear`）、撤销（`undo`）、状态核对（`state`）、相机预设与环绕（`view`、`orbit`）、纵剖面切片（`slice`）、蓝图导出（`download`）等操作。AI 以 JS 求值的方式调用这些接口，全部方法同步返回 JSON 结果。

这种方式的关键价值在于闭环自查。AI 每完成一部分摆放，即可切换相机视角并对页面截图，以多模态方式直接查看建筑的实际渲染效果：整体形态用适配视角检查，内部结构用切片功能检查。若发现比例失调、结构错位或方块用错，立即回到接口修改后重新截图确认，直至形态与设计意图相符。设计器内置两百余种常用方块，并固化了树叶持久化等原版物理规则，避免建造后出现树叶凋零、附着物脱落一类的问题。

设计完成后，AI 调用 `download` 接口，由浏览器将蓝图直接落成磁盘文件，再移动至引擎蓝图库，全程不经手模型上下文，节省 token 开销的同时避免大体积 JSON 被截断或抄写走样。导出的蓝图包含标准 JSON 与 `.litematic` 存档两种形式，后者可被 Litematica 模组直接打开。

### 方式三：图片还原

当输入是一张现成的图片，而非建模文件或设计意图时，走图片还原路线。这一路线不打开设计器，直接由转换脚本产出蓝图；难点在于读懂图片，而不在于设计造型。

按源图类型分四条入口：**照片**（背景杂乱、画面里有无关物体）用 `photo2blueprint.py`，它先用显著性分割模型自动识别并抠出画面主体，不需要人工裁剪或调整背景参数，画面里有多个可辨认的主体时可先列出候选再指定；**平涂像素图**（拼豆、十字绣图纸）用 `img2blueprint_flat.py`；**光照均匀的干净位图**用 `img2blueprint.py`；**建筑照片**则先按 `mc-design/references/photo-to-building.md` 判别照片类型，再走该文档的四条路线之一。

几个使用要点：画面里同时存在多个可辨认主体时，先用候选模式生成一张带编号的框选图，确认后再指定要还原的那一个；照片在室内暗光下拍摄时颜色往往偏灰，成品会落到棕褐系，可开启彩度增强提高饱和度；还原产物是宽乘高乘一的平面像素壁画，只含正面信息，不含厚度与内部结构，若需要立体还原应改走建筑照片路线。

这条路线需要额外的 Python 依赖与一个模型权重，获取方式见[模型权重](#模型权重)。

三种方式的产物完全一致，可以交叉使用：外部文件转换出的蓝图，同样可以导入设计器继续修改。

## 技能构成

| 技能 | 职责 | 核心工具 |
|------|------|----------|
| mc-design | 体素设计与蓝图产出，含自主设计与图片还原两条路线 | 网页设计器、图片转换脚本、write_litematic 脚本 |
| mc-build | 落地建造与验收 | build-blueprint 工具、perf_build 表演回放、json_to_fills 转换器 |
| mc-modify | 差量微调 | blueprint_diff 差量计算、replace_material 材质替换 |
| mc-screenshot | 视觉通道，读取游戏内截图供验收与迭代 | 游戏截图目录读取 |

## 工作流程

建造环节的三个技能按顺序衔接，形成单向数据流：

```
mc-design                     mc-build                      mc-modify
┌──────────────────┐   蓝图   ┌───────────────────┐  差量补丁 ┌──────────────────┐
│ 网页设计器、      │ ──────→ │ 秒落（默认）或      │ ───────→ │ 差量计算后仅写入   │
│ 既有文件转换或    │         │ 表演模式回放，      │          │ 差异格，再同步     │
│ 图片还原产出      │         │ 逐格回读验收        │          │ 蓝图并验收         │
│ JSON 与 litematic│         │                   │          │                  │
└──────────────────┘         └───────────────────┘          └──────────────────┘
```

1. **设计阶段**（mc-design）：通过网页设计器建模、转换既有建模文件，或从照片与像素图还原，产出蓝图 JSON 与 `.litematic` 存档，写入引擎蓝图库。
2. **建造阶段**（mc-build）：默认以秒落模式将蓝图一次性写入世界；用户希望观看过程时，切换为表演模式，由工人机器人按预生成的指令清单走位回放。建造完成后执行 verify-region 逐格回读验收，世界与蓝图完全一致方可通过。
3. **修改阶段**（mc-modify）：在既有蓝图上执行差量修改，先计算新旧版本的最小变更集，再仅将差异方块写入世界，最后同步蓝图并再次验收。纯材质替换提供一键通道。

建造与修改全程可用 mc-screenshot 读取游戏内 F2 截图，以多模态方式确认实际观感。

## 核心原则

- **严格遵守蓝图。** 引擎蓝图库中的 JSON 是设计结果的唯一定义，世界中的任何修改都必须回写同步，保证蓝图与实际建筑始终一致。
- **节省 token。** 设计产物由浏览器直接落盘，不注入模型上下文；大体量数据在上下文中的往返既浪费资源，也可能引入抄写误差。
- **可微调。** 修改一律通过最小变更集完成，只改动需要改的部分，除用户明确要求外不进行整体重建。
- **一块不差。** 每次建造与修改后执行逐方块回读比对，世界与蓝图完全一致才作为通过标准；观感终审由用户游戏内截图完成。

## 安装

将本仓库的技能目录复制到 Agent 的技能目录即可，以 WorkBuddy 为例：

```bash
git clone https://github.com/ChenZeLongKnight/Ai-build-for-minecraft.git
cp -r Ai-build-for-minecraft/mc-design \
      Ai-build-for-minecraft/mc-build \
      Ai-build-for-minecraft/mc-modify \
      Ai-build-for-minecraft/mc-screenshot \
      ~/.workbuddy/skills/
```

前置依赖（均为开源项目）：

- Minecraft Java 版（已在 1.21.1 完整验证；其余版本理论上可行但未测试），单人世界对局域网开放，并开启作弊；
- [minecraft-mcp-server-blueprint](https://github.com/ChenZeLongKnight/minecraft-mcp-server-blueprint)：连接游戏的 MCP 服务，基于 [yuniko-software/minecraft-mcp-server](https://github.com/yuniko-software/minecraft-mcp-server)（Apache License 2.0）扩展而来，新增 build-blueprint、verify-region、list-schematics 等蓝图建造工具；
- [browser-use](https://github.com/browser-use/browser-use)：浏览器自动化 MCP，网页设计器的打开、操控与截图依赖此项；
- Python 3.10 以上，仅在图片还原路线下需要，依赖 `numpy`、`Pillow`、`scipy`、`onnxruntime` 四个包。

## 模型权重

图片还原路线的显著性分割模型不随仓库分发完整版，说明与获取方式见 [`models/README.md`](models/README.md)；仓库内附轻量版权重，开箱可用。

## 目录结构

```
Ai-build-for-minecraft/
├── mc-design/
│   ├── SKILL.md              # 使用说明书（自主设计、图片还原两条路线）
│   ├── assets/voxel_designer.html   # 网页体素设计器
│   ├── scripts/              # 图片转换脚本、write_litematic、design_template、convert_litematic
│   └── references/           # 设计器路线、图片还原、建筑照片还原的深度参考
├── mc-build/
│   ├── SKILL.md              # 建造流程（秒落、表演、验收）
│   ├── scripts/              # perf_build、json_to_fills、convert_litematic
│   └── references/pipeline.md
├── mc-modify/
│   ├── SKILL.md              # 微调流程（微改捷径、三步差量、材质替换）
│   ├── scripts/              # blueprint_diff、replace_material
│   └── references/modify.md
├── mc-screenshot/
│   └── SKILL.md              # 游戏内 F2 截图通道
└── models/
    ├── u2netp.onnx           # 图片还原的轻量分割模型
    └── README.md             # 权重说明与完整版下载地址
```

## 演示

**日式拱门：设计器蓝图与实际建造对比。** 左图为网页设计器中由 AI 摆放的蓝图模型，右图为蓝图写入世界后的实际效果，两者逐方块一致。

<p align="center">
  <img src="docs/images/japanese_gate_blueprint.png" width="45%" alt="日式拱门蓝图" />
  <img src="docs/images/japanese_gate_in_game.jpg" width="45%" alt="日式拱门游戏内效果" />
</p>

**小型宫殿：AI 自主设计与落地微调。** 左图为 AI 通过网页设计器自主建模的过程，右图为建造完成后经差量微调方块材质的游戏内效果。

<p align="center">
  <img src="docs/images/palace_designer.jpg" width="45%" alt="设计器中的小型宫殿" />
  <img src="docs/images/palace_in_game.jpg" width="45%" alt="小型宫殿游戏内效果" />
</p>

**建筑群。** 图中全部建筑均由智能体自主设计并建造完成。

![智能体自主设计建造的建筑群](docs/images/agent_built_village.jpg)

**建造者 XiaoBuddy。** 由 WorkBuddy 驱动的建筑师机器人，正在游戏中接收指令。

![建筑师机器人 XiaoBuddy](docs/images/xiaobuddy.png)

**图片还原：照片自动转建筑。** 左图为一张照片经脚本自动还原后写入世界的实际效果，右图为原始照片。全过程没有人工裁剪，也没有调整任何背景参数：脚本自动识别出猫头为主体，将背景与毛毯一并剔除，再逐格配色、生成蓝图并落地建造，游戏内与原图的毛色分布、耳朵轮廓和胡须位置一一对应。

<p align="center">
  <img src="docs/images/cat_image_restore_in_game.jpg" width="45%" alt="照片还原的猫在游戏内的效果" />
  <img src="docs/images/cat_image_restore_source.jpg" width="45%" alt="原始猫照片" />
</p>

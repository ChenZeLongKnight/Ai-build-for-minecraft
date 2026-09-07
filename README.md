# AIcraft

Minecraft AI 建筑流水线：一套让 AI Agent（WorkBuddy / Claude Code / zcode 等 CLI）在 Minecraft Java 版中**设计 → 建造 → 微调**建筑的 Agent Skill 三部曲。

所有建筑操作通过 [minecraft-mcp-server](https://github.com/yuniko-software/minecraft-mcp-server)（本地构建版）连接游戏，蓝图以 JSON / litematic 为唯一真相源。

## 三个技能

| 技能 | 职责 | 核心工具 |
|------|------|----------|
| **mc-design** | 体素设计：网页体素设计器 + 脚本生成 | `voxel_designer.html`（42 种方块、AI 程序化接口 `window.vd`）、`write_litematic.mjs` |
| **mc-build** | 落地建造：秒落 / 表演模式两种 | MCP `build-blueprint`、`perf_build.js`（工人 bot 走位回放）、`json_to_fills.mjs` |
| **mc-modify** | 差量微调：在既有建筑上改，不重建 | `blueprint_diff.mjs`（最小变更集）、`replace_material.mjs`（一键换材质） |

## 工作流

```
mc-design                    mc-build                     mc-modify
┌─────────────────┐   蓝图   ┌──────────────────┐  差量补丁 ┌─────────────────┐
│ 网页设计器/脚本   │ ──────→ │ 秒落(默认)/表演回放 │ ───────→ │ diff→build→verify│
│ 产出 JSON+litematic│        │ verify-region 验收 │          │ 真相源同步        │
└─────────────────┘         └──────────────────┘          └─────────────────┘
```

**核心原则**

- **蓝图即真相源**：`<ENGINE>/schematics/<名字>.json` 是唯一权威，世界改动后必须回写同步
- **数据不过模型**：设计产物经 `vd.download()` 直接落盘，不注入上下文
- **差量优先**：修改一律走 diff 补丁，除非明确要求重新设计
- **全量验收**：`verify-region` 逐格回读 diff，四项计数全零才通过

## 安装

将本仓库三个目录复制到 Agent 的 skills 目录即可（如 WorkBuddy 的 `~/.workbuddy/skills/`）：

```bash
git clone https://github.com/<你的用户名>/AIcraft.git
cp -r AIcraft/mc-design AIcraft/mc-build AIcraft/mc-modify ~/.workbuddy/skills/
```

前置依赖：

- Minecraft Java 版 1.21.1，单人世界对局域网开放（作弊开启）
- minecraft-mcp-server 本地构建版（提供 `build-blueprint` / `verify-region` / `list-schematics` 等工具）
- 浏览器自动化 MCP（mc-design 的网页设计器依赖）

## 目录结构

```
AIcraft/
├── mc-design/
│   ├── SKILL.md              # 使用说明书（内置设计器手册）
│   ├── assets/voxel_designer.html   # 网页体素设计器（file:// 直接打开）
│   ├── scripts/              # write_litematic / design_template / convert
│   └── references/design.md  # 脚本路线与 NBT 格式深度参考
├── mc-build/
│   ├── SKILL.md              # 建造流程（秒落/表演/验收）
│   ├── scripts/              # perf_build / json_to_fills / convert
│   └── references/pipeline.md
└── mc-modify/
    ├── SKILL.md              # 微调流程（微改捷径/三步差量/换材质）
    ├── scripts/              # blueprint_diff / replace_material
    └── references/modify.md
```

---
name: mc-modify
agent_created: true
description: Minecraft 建筑微调阶段：在已建建筑上做小修改（换材质、加减方块、拆装部件），蓝图差量 diff 只发变化部分，绝不整体重建。触发词：改一下、微调、换个材质、拆掉、加上、挪一下、修改建筑、调整建筑。设计新建筑用 mc-design，整体落地用 mc-build。
---

# Minecraft 建筑微调（修改阶段）

本技能负责 Minecraft 建筑流水线中的修改阶段，其职责是在已建成的建筑上执行增量修改，包括更换材质、增删方块与拆装部件。除非用户明确说「重新设计」或「重建」，否则一律执行差量微调，禁止整体重放。新建筑的设计工作由 mc-design 技能承担，从零落地的整体建造由 mc-build 技能承担。

## 通用约定

以下约定是本技能执行时必须遵守的基础规则（设计阶段的对应约定见 mc-design 技能，彼此独立）。

1. 引擎目录在下文中以 `<ENGINE>` 表示，其取值来自环境变量 `MC_BUILD_HOME`，默认值为 `D:/mcserver`。执行 Node 脚本时统一使用 `C:/Users/ASUS/.workbuddy/binaries/node/versions/22.22.2-2/node.exe`。
2. 蓝图的唯一真相源是 `<ENGINE>/schematics/<名字>.json` 文件；`.litematic` 文件作为存档使用；`<名字>_fills.txt` 文件作为表演模式的输入使用。
3. 执行任何建造操作之前，单人世界必须已经对局域网开放并记录端口号，且世界已开启作弊。
4. 五十格阈值：当操作涉及的方块数量少于 50 格时，优先采用内联方式而不创建文件；当数量达到或超过 50 格时，改用蓝图文件通道。
5. 验收标准：verify-region 检查结果中的缺失、不符、多余、未加载四项计数必须全部为零；观感层面的最终审定通过用户 F2 截图完成，读图方法见 mc-screenshot 技能。
6. 三条物理规则必须遵守：树叶必须携带 `[persistent=true]` 状态，否则会自然凋零；灯笼不能放置在半砖之上，否则没有完整支撑面；藤蔓不能依附于玻璃板，即使强制放置也会被方块更新弹掉。
7. 深度参考资料位于本技能的 references 目录，本文件正文不重复其内容；全部可执行命令集中列于本文件末尾的「命令速查」一节，正文只描述流程与决策逻辑。

## 核心原则

蓝图是修改工作的唯一真相源。「修改建筑」的实质是「修改蓝图，再将差异同步到世界」，以下三步永远完整执行，禁止跳过第三步：第一步修改蓝图，第二步计算最小变更集，第三步将补丁应用到世界、同步真相源与存档并验收。

## 工作流程

**第 0 步：定位建筑并判断规模。** 本步骤的目的是确认修改对象并选择执行路径。首先与用户确认要修改哪座建筑、引擎库中对应蓝图的名称（可借助 MCP 工具 list-schematics 查询），并确认该建筑当初建造时的原点坐标；若记忆不清，应询问用户或查阅工作日志。随后按修改性质选择执行路径，共三条：

- **快捷通道 A（微改，不超过 5 格）**：直接使用 /setblock 修改世界，再用一行脚本同步真相源 JSON，最后以 verify-region 兜底确认——省去工作副本与差量工具，但真相源同步不可省略。
- **快捷通道 B（纯材质替换，任何规模）**：当修改内容仅是「把某种方块换成另一种」（可带区域限定）时，使用 replace_material.mjs 专用脚本一次完成：脚本就地更新真相源并自动生成补丁文件，随后只需 build-blueprint 应用补丁、验收、删除补丁文件，全程不需要 diff 工具。
- **标准三步**：其余一切修改（增删、挪动、结构调整、混合变更）走以下三步流程。注意这三步本身是秒级操作——几格到几十格的补丁一次内联调用即可写完——因此五至五十格之间的常规修改走标准三步即可，不存在需要回避的额外开销，不要为此重新设计或整体重建。

标准三步之前还应确认站位：修改应用前确认目标区域内没有玩家或 bot 站立，否则会导致放置失败或方块被站位者撸掉。

**第 ① 步：修改蓝图。** 本步骤的目的是产出修改后的蓝图版本。将 `<名字>.json` 复制为工作副本，用 Node 一行脚本对其 blocks 数组执行修改；具体改法样例见 references/modify.md，包括按方块名筛选替换材质、push 新增方块、filter 删除方块以及按坐标范围执行区域操作。方块名称可以携带完整状态，例如 `spruce_stairs[facing=south]`。

**第 ② 步：计算差量。** 本步骤的目的是从新旧两版蓝图中提取最小变更集。使用 blueprint_diff.mjs 脚本比对旧 JSON 与新 JSON，输出包含 add、change、remove 三类计数的 blocks 数组，其中删除项以 `minecraft:air` 表示。比对标准是坐标加完整方块字符串（含状态），与 verify-region 的判定标准一致，因此 `spruce_stairs` 与 `spruce_stairs[facing=south]` 会被视为不同方块。

**第 ③ 步：应用补丁并收尾。** 本步骤的目的是将差异写入世界并使全部数据源恢复一致，五个子步骤按固定顺序执行。第一，通过 MCP 工具 build-blueprint 将补丁写入世界并指定原建筑的原点坐标；补丁的传入方式按 Fifty 格硬规则执行：不超过 50 格时将补丁的 blocks 数组内联传入；**超过 50 格时必须先把补丁包装为带 width/height/length 元数据的完整蓝图文件、放入 `<ENGINE>/schematics/`（build-blueprint 的 file= 参数只认引擎库），再以 file= 参数传入，用完即删**——replace_material.mjs 生成的补丁已自动满足包装与入库两个条件。第二，用修改后的新 JSON 覆盖真相源 `<ENGINE>/schematics/<名字>.json`（replace_material.mjs 已就地完成）。第三，用 write_litematic.mjs 脚本从新 JSON 重新生成存档。第四，执行 verify-region：缺失、不符、未加载必须全为零，「多余」按 mc-build 的分类规则判断（天然地形误报忽略，装饰残留处理）。第五，请用户按 F2 截图进行观感终审。

**路径参数注意**：向 MCP 工具传文件时只传引擎库内的文件名（如 `file=<名字>.json`），不要传绝对路径——Git Bash 会把 `/d/...` 形态的路径改写为 `d:\d\...` 导致引擎找不到文件；确需绝对路径时加 `MSYS_NO_PATHCONV=1` 前缀。

**特殊情况：反向同步。** 当用户在游戏中手工修改过建筑时，本技能的执行方向反转：先通过 verify-region 获取世界与蓝图的差异清单，再将世界现状写回蓝图，最后重新执行差量比对并要求结果全部为零，使真相源恢复一致。具体样例见 references/modify.md。

## 判断准则

- 当预期的变更集规模超过蓝图总块数的一半时，差量方式已失去意义，应与用户确认是否改为整体重建（转入 mc-build 技能）。
- 删除依附类方块（灯笼、盆栽、藤蔓、门）时，差量结果中的 air 项没有问题，但应注意先删除依附物、或接受其随后自动掉落；若反向安装（先装依附物后装支撑），操作会无效。
- 补丁应用失败时可直接重试，因为 /setblock 与 air 补丁均具有幂等性。

## 命令速查

以下命令按照工作流程的出现顺序排列，供执行时直接查阅。

```
# 快捷通道 A（微改，不超过 5 格）
# 1) 在游戏内直接放置：/setblock x y z minecraft:<方块>[状态]
# 2) 用 Node 一行脚本按坐标修改 <ENGINE>/schematics/<名字>.json 的 blocks 数组，同步真相源
# 3) 执行 verify-region（file=<名字>.json）兜底确认

# 快捷通道 B（纯材质替换，任何规模，免 diff）
# 就地更新真相源 + 自动生成 <名字>_patch.json（已包装元数据、已在引擎库内，可直接 file= 使用）
# 支持可选区域：末尾追加 6 个数字 x1 x2 y1 y2 z1 z2（蓝图相对坐标）
node <skill>/scripts/replace_material.mjs <ENGINE>/schematics/<名字>.json <旧材质> <新材质>
# 随后: build-blueprint file=<名字>_patch.json + 原建筑 originX/Y/Z → verify-region → 删除补丁文件

# 第 ① 步至第 ② 步：标准三步
# 工作副本上用 Node 一行脚本改蓝图（样例见 references/modify.md），然后算差量：
node <skill>/scripts/blueprint_diff.mjs <旧.json> <新.json> <patch.json>
# 补丁超过 50 格时：包装为完整蓝图（带 width/height/length）并 cp 进 <ENGINE>/schematics/ 才能用 file= 通道
# 向 MCP 传文件只传库内文件名，不传绝对路径（Git Bash 的 /d/... 会被改写；确需绝对路径加 MSYS_NO_PATHCONV=1）

# 第 ③ 步：重新生成存档
node <mc-design>/scripts/write_litematic.mjs <ENGINE>/schematics/<名字>.json <ENGINE>/schematics/<名字>.litematic <名字>

# 验收（MCP 工具 verify-region）
# 参数：file=<新.json>、originX/Y/Z；执行反向同步时可将 maxReport 调大以获取完整差异清单。
# 「多余」分类：天然地形（草/泥土等）=误报忽略；装饰类或蓝图相关方块=残留，需处理。
```

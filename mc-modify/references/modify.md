# 建筑微调深度手册

本文件是 mc-modify 技能的深度参考资料，记载蓝图修改的脚本样例、差量工具的细节说明与实战记录。

## 常用蓝图修改样例（Node 一行脚本）

以下样例假设已通过 `d = JSON.parse(fs.readFileSync(p,'utf8'))` 读入蓝图 JSON（其中 p 为蓝图文件路径），修改完成后以 `fs.writeFileSync(p2, JSON.stringify(d,null,1))` 写出。

### 替换材质（全局或限定区域）

```js
let n=0;
for(const b of d.blocks)
  if(b.block==='minecraft:oak_planks'){ b.block='minecraft:spruce_planks'; n++; }
// 若需限定区域，追加坐标条件，例如：&& b.x>=4 && b.x<=8 && b.y>=1
// 携带状态的方块应使用前缀匹配，例如：b.block.startsWith('minecraft:spruce_stairs')
```

### 新增方块

```js
d.blocks.push({x:5,y:1,z:4,block:'minecraft:lantern[hanging=true]'});
// 扩建超出原 width/height/length 时无需修改元数据：write_litematic 会按体素实际范围自动扩展尺寸。
```

### 删除方块

```js
d.blocks = d.blocks.filter(b => !(b.x===5 && b.y===1 && b.z===4));
```

### 区域拆除与区域替换

```js
// 拆除一个长方体区域（对应的 air 补丁由差量工具自动生成）：
d.blocks = d.blocks.filter(b => !(b.x>=2&&b.x<=6&&b.y>=1&&b.y<=3&&b.z>=2&&b.z<=6));
// 在指定区域内替换材质：
for(const b of d.blocks) if(b.x>=2&&b.x<=6&&b.block.startsWith('minecraft:cobblestone')) b.block='minecraft:stone_bricks';
```

### 反向同步（用户在游戏中手工修改后，将世界现状写回蓝图）

1. 执行 MCP 工具 verify-region（file=当前蓝图，maxReport 调大至 200），获取「不符」「缺失」「多余」三项的完整清单。
2. 按清单修改蓝图：「不符」项改为世界的实际方块；「多余」项从 blocks 中删除该坐标；「缺失」项需要判断本意后二选一——补上蓝图条目，或接受世界现状并从蓝图删除，拿不准时询问用户。
3. 重新执行差量比对并要求结果全部为零，此时真相源恢复一致。

## 差量工具细节（blueprint_diff.mjs）

- 比对标准为坐标加完整方块字符串（含状态），与 verify-region 的判定标准一致：`oak_planks` 与 `oak_planks` 一致，而 `spruce_stairs` 与 `spruce_stairs[facing=south]` 视为不同方块。
- 输入容错：既接受 `{blocks:[...]}` 形式，也接受裸数组；忽略 width、height、length 元数据。
- 输出的 blocks 数组可直接内联传给 build-blueprint；不要将 patch.json 作为 file= 参数传入，因为它缺少 width、height、length 元数据。
- 当补丁超过约五十格时，应改走文件通道：将 patch.blocks 包装上原蓝图的 width、height、length 元数据，存为临时蓝图文件（例如 `<名字>_patch.json`）后以 file= 参数传入，使用完毕即删除。原因是内联数百格的参数既冗长又容易出错。
- 删除项以 `minecraft:air` 表示，通过 /fill air 实现，具有幂等性。

## 实战记录（2026 年 9 月 7 日验证）

集市亭包边材质更换（苔石替换为磨制安山岩）的完整流程如下：第一步，Node 脚本替换三十二处方块；第二步，差量比对得出 change 为 32；第三步，build-blueprint 内联三十二块，实际产生十六条指令，而整楼重建需要八十六条；第四步，用新 JSON 覆盖真相源，并以 write_litematic 重新生成存档（530 字节，242 方块）；第五步，verify-region 结果为 242/242 全部为零，验收通过。

增、改、删混合样例已在本地验证：新增一项、修改一项、删除一项（air）的结果全部正确。

## 与其他技能的关系

- mc-design 技能负责产出初始蓝图三件套并写入引擎库，这是微调工作的前提。
- mc-build 技能负责整体落地或重建（仅当用户明确要求时使用）；其中 verify-region 的物理坑知识与本技能通用。
- mc-screenshot 技能负责观感终审：修改完成后请用户按 F2 截图。

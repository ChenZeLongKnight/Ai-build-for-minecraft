// 自由创造设计模板：体素设计 → .litematic 存档 → 回读校验 → JSON + /fill 指令清单
// 用法: 复制本文件为 design_<名字>.mjs，改 buildDesign() 里的体素，然后:
//   node design_<名字>.mjs <世界原点x> <世界原点y> <世界原点z> [名字]
//   输出: 直接入引擎库 <ENGINE>/schematics/<名字>.{litematic,json} + <名字>_fills.txt
// 引擎路径：MC_BUILD_HOME 环境变量可覆盖，默认 D:/mcserver
//
// 【约定·避免返工】
// 1. import 其他 skill 脚本一律用 pathToFileURL(...).href 动态 import，
//    不要手写 'file:///' 前缀（Windows 盘符路径 C:/ 开头不是合法 ESM URL）
// 2. 产物直接写引擎库，build-blueprint/verify-region/perf_build 无需再手动 cp
import path from 'path';
import { pathToFileURL } from 'url';
import fs from 'fs';

const ENGINE = process.env.MC_BUILD_HOME || 'D:/mcserver';
const SKILL_SCRIPTS = 'C:/Users/ASUS/.workbuddy/skills/mc-design/scripts'; // 模板被复制到任何目录都能找到兄弟脚本
const { writeLitematicFile } = await import(
  pathToFileURL(path.join(SKILL_SCRIPTS, 'write_litematic.mjs')).href
);
const { loadBlueprintFileAsync, blueprintToFills } = await import(
  pathToFileURL(path.join(ENGINE, 'dist', 'tools', 'schematic-tools.js')).href
);

const [ oxArg, oyArg, ozArg, nameArg ] = process.argv.slice(2);
const NAME = nameArg || 'template';
const OX = parseInt(oxArg || '0'), OY = parseInt(oyArg || '0'), OZ = parseInt(ozArg || '0');
const OUT = path.join(ENGINE, 'schematics');

// ============ 在这里改设计 ============
const W = 5, H = 6, L = 5;
function buildDesign(put) {
  // 中世纪水井示例（参考物理规则：围水用全方块、依附方块留支撑）
  for (let x = 0; x < W; x++) for (let z = 0; z < L; z++) {
    const corner = (x === 0 || x === W - 1) && (z === 0 || z === L - 1);
    put(x, 0, z, corner ? 'minecraft:mossy_cobblestone'
      : (x === 2 && z === 2 ? 'minecraft:cobblestone' : 'minecraft:stone_bricks'));
  }
  for (let x = 1; x <= 3; x++) for (let z = 1; z <= 3; z++)
    put(x, 1, z, (x === 2 && z === 2) ? 'minecraft:water[level=0]' : 'minecraft:cobblestone');
  for (const [x, z] of [[1,1],[3,1],[1,3],[3,3]]) put(x, 2, z, 'minecraft:spruce_log[axis=y]');
  for (const [x, z] of [[2,1],[1,2],[3,2],[2,3]]) put(x, 2, z, 'minecraft:cobblestone_wall[up=true]');
  for (const [x, z] of [[1,1],[3,1],[1,3],[3,3]]) put(x, 3, z, 'minecraft:spruce_log[axis=y]');
  for (let x = 1; x <= 3; x++) for (let z = 1; z <= 3; z++) put(x, 4, z, 'minecraft:spruce_planks');
  put(2, 5, 2, 'minecraft:lantern[hanging=true]');
}
// =====================================

const blocks = [];
const put = (x, y, z, block) => blocks.push({ x, y, z, block });
buildDesign(put);
// 同格覆盖收敛：后放覆盖先放（与 /setblock 一致），按坐标保留最后条目即为最终态。
// 若不收敛，覆盖掉的旧格会让 ② 回读校验误报「丢失」。需要叠盖设计时 put 顺序 = 覆盖顺序。
const finalMap = new Map();
for (const b of blocks) finalMap.set(`${b.x},${b.y},${b.z}`, b);
const finalBlocks = [...finalMap.values()];
const bp = { width: W, height: H, length: L, source: 'design', blocks: finalBlocks };

// ① 生成 .litematic 存档（Litematica 模组可开、可分享）—— 直接入引擎库
fs.mkdirSync(OUT, { recursive: true });
const size = writeLitematicFile(bp, path.join(OUT, `${NAME}.litematic`), NAME);
console.log(`① ${NAME}.litematic 已入引擎库 (${size} bytes)`);

// ② 回读校验：体素集逐一对比，必须 100% 一致
const back = await loadBlueprintFileAsync(path.join(OUT, `${NAME}.litematic`));
const key = b => `${b.x},${b.y},${b.z},${b.block}`;
const origin = new Set(finalBlocks.map(key)), rt = new Set(back.blocks.map(key));
const lost = [...origin].filter(k => !rt.has(k)), extra = [...rt].filter(k => !origin.has(k));
if (lost.length || extra.length) { console.error('❌ 往返不一致 丢失:', lost, '多余:', extra); process.exit(1); }
console.log(`② 回读校验 ✅ ${back.blocks.length}/${finalBlocks.length} 方块（含方块状态）`);

// ③ 输出建造用 JSON（build-blueprint 用）与 /fill 指令清单（表演模式用）
fs.writeFileSync(path.join(OUT, `${NAME}.json`), JSON.stringify({ width: W, height: H, length: L, source: 'litematic', blocks: back.blocks }, null, 1));
const fills = blueprintToFills(back, OX, OY, OZ);
fs.writeFileSync(path.join(OUT, `${NAME}_fills.txt`), fills.join('\n') + '\n');
console.log(`③ ${NAME}.json + ${NAME}_fills.txt 已入引擎库（${fills.length} 条指令）`);
console.log(`   秒落: MCP build-blueprint file=${NAME}.json origin=(${OX},${OY},${OZ})`);
console.log(`   表演: node perf_build.js 25565 XiaoGold ${path.join(OUT, `${NAME}_fills.txt`)} 400`);

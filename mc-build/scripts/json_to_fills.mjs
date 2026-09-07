// 蓝图 JSON → /fill 指令清单（表演模式 perf_build.js 的官方前置转换器）
// 用法: node json_to_fills.mjs <blueprint.json> [输出路径] [originX originY originZ]
// 行为: 按纵坐标自低向高排序（物理依赖安全），同一高度层内沿 x 方向合并连续同方块区段
//       不传输出路径时默认写到蓝图同目录 <名字>_fills.txt；origin 为世界绝对坐标偏移，默认 0 0 0
import fs from 'fs';
import path from 'path';

const [, , inPath, outArg, ox = '0', oy = '0', oz = '0'] = process.argv;
if (!inPath) { console.error('用法: node json_to_fills.mjs <blueprint.json> [输出路径] [originX originY originZ]'); process.exit(1); }

const bp = JSON.parse(fs.readFileSync(inPath, 'utf8'));
const blocks = Array.isArray(bp) ? bp : bp.blocks;
if (!blocks || !blocks.length) { console.error('蓝图没有体素'); process.exit(1); }

const OX = +ox, OY = +oy, OZ = +oz;

// 按 (y, z, x) 排序保证支撑先行；再对同一 (y,z) 内 x 连续且方块相同的区段合并为 /fill
const sorted = [...blocks].sort((a, b) => a.y - b.y || a.z - b.z || a.x - b.x);
const lines = [];
let i = 0;
while (i < sorted.length) {
  const start = sorted[i];
  let end = start, j = i + 1;
  while (j < sorted.length
    && sorted[j].y === start.y && sorted[j].z === start.z
    && sorted[j].x === end.x + 1 && sorted[j].block === start.block) {
    end = sorted[j]; j++;
  }
  const b = start.block.replace(/^minecraft:/, '') === 'air' ? 'minecraft:air' : start.block;
  const x1 = start.x + OX, y = start.y + OY, z = start.z + OZ;
  if (end.x === start.x) {
    lines.push(`/setblock ${x1} ${y} ${z} ${b}`);
  } else {
    lines.push(`/fill ${x1} ${y} ${z} ${end.x + OX} ${y} ${z} ${b}`);
  }
  i = j;
}

const outPath = outArg || path.join(path.dirname(inPath), path.basename(inPath).replace(/\.json$/i, '') + '_fills.txt');
fs.writeFileSync(outPath, lines.join('\n') + '\n');
console.log(`已写入 ${outPath}: ${lines.length} 条指令（${blocks.length} 方块，origin ${OX} ${OY} ${OZ}）`);

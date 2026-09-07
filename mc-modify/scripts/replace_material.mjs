// 按材质名全局/限区域替换（mc-modify 纯换材质快捷命令，免 diff 三步）
// 用法: node replace_material.mjs <blueprint.json> <旧材质> <新材质> [x1 x2 y1 y2 z1 z2]
// 行为: 直接改写蓝图文件（真相源就地更新），并把变更格写为 <名字>_patch.json（与蓝图同目录，
//       已带 width/height/length 包装，可直接作为 build-blueprint 的 file= 参数）
// 匹配规则: 旧材质不带 minecraft: 前缀自动补全；带状态时按前缀匹配（spruce_stairs 命中 spruce_stairs[facing=south]）
import fs from 'fs';
import path from 'path';

const [, , inPath, oldM, newM, ...regionArgs] = process.argv;
if (!inPath || !oldM || !newM) {
  console.error('用法: node replace_material.mjs <blueprint.json> <旧材质> <新材质> [x1 x2 y1 y2 z1 z2]');
  console.error('  材质名可带或不带 minecraft: 前缀；区域 6 参数可选（两个对角坐标，蓝图相对坐标）');
  process.exit(1);
}

const norm = s => s.startsWith('minecraft:') ? s : 'minecraft:' + s;
const oldBase = norm(oldM);
const newBase = norm(newM);
const oldPrefix = oldBase + '[';

const region = regionArgs.length === 6 ? regionArgs.map(Number) : null;
if (region && region.some(v => !Number.isFinite(v))) { console.error('区域参数必须是 6 个数字'); process.exit(1); }
const inRegion = b => !region || (b.x >= Math.min(region[0], region[1]) && b.x <= Math.max(region[0], region[1])
  && b.y >= Math.min(region[2], region[3]) && b.y <= Math.max(region[2], region[3])
  && b.z >= Math.min(region[4], region[5]) && b.z <= Math.max(region[4], region[5]));

const bp = JSON.parse(fs.readFileSync(inPath, 'utf8'));
if (!bp.blocks || !bp.blocks.length) { console.error('蓝图没有体素'); process.exit(1); }

// 替换：完整状态跟随——旧块的状态部分原样保留到新块（oak_stairs[facing=south] → spruce_stairs[facing=south]）
let replaced = 0;
const patchBlocks = [];
for (const b of bp.blocks) {
  if (!inRegion(b)) continue;
  let hit = false, props = '';
  if (b.block === oldBase) hit = true;
  else if (b.block.startsWith(oldPrefix)) { hit = true; props = b.block.slice(oldPrefix.length).replace(/\]$/, ''); }
  if (!hit) continue;
  b.block = props ? `${newBase}[${props}]` : newBase;
  replaced++;
  patchBlocks.push({ x: b.x, y: b.y, z: b.z, block: b.block });
}

if (!replaced) { console.log(JSON.stringify({ replaced: 0, note: '没有命中任何方块，未写任何文件' })); process.exit(0); }

// 真相源就地更新
fs.writeFileSync(inPath, JSON.stringify(bp, null, 1));

// 补丁文件与蓝图同目录（build-blueprint 的 file= 只认引擎库，蓝图本就在库里）
const patchPath = path.join(path.dirname(inPath), path.basename(inPath).replace(/\.json$/i, '') + '_patch.json');
fs.writeFileSync(patchPath, JSON.stringify({ width: bp.width, height: bp.height, length: bp.length, blocks: patchBlocks }, null, 1));

console.log(JSON.stringify({
  replaced,
  blueprintUpdated: inPath,
  patchFile: patchPath,
  next: 'build-blueprint file=<patchFile> + 原建筑 originX/Y/Z → 验收 → 删除 patch 文件'
}, null, 1));

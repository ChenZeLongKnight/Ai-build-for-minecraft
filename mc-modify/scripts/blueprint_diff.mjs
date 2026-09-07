// 蓝图差量：旧蓝图 vs 新蓝图 → 最小变更集（不重建，只发变化部分）
// 用法: node blueprint_diff.mjs <旧.json> <新.json> [patch输出.json]
// patch 格式: { add, change, remove, total, blocks:[{x,y,z,block}] }
//   新增/修改 → 直接放目标方块；删除 → block 为 minecraft:air
//   blocks 数组可直接内联喂 MCP build-blueprint（origin 传原建筑的 originX/Y/Z）
import fs from 'fs';

const [oldPath, newPath, outPath] = process.argv.slice(2);
if (!oldPath || !newPath) {
  console.error('用法: node blueprint_diff.mjs <旧.json> <新.json> [patch输出.json]');
  process.exit(1);
}
const load = p => {
  const d = JSON.parse(fs.readFileSync(p, 'utf8'));
  const arr = Array.isArray(d) ? d : d.blocks;
  if (!Array.isArray(arr)) throw new Error(`${p} 里找不到 blocks 数组`);
  return arr;
};
const parseK = k => { const [x, y, z] = k.split(',').map(Number); return { x, y, z }; };
const oldMap = new Map(load(oldPath).map(b => [`${b.x},${b.y},${b.z}`, b.block]));
const newMap = new Map(load(newPath).map(b => [`${b.x},${b.y},${b.z}`, b.block]));

const blocks = [];
let add = 0, change = 0, remove = 0;
for (const [k, block] of newMap) {
  const o = oldMap.get(k);
  if (o === undefined) { add++; blocks.push({ ...parseK(k), block }); }
  else if (o !== block) { change++; blocks.push({ ...parseK(k), block }); }
}
for (const k of oldMap.keys()) {
  if (!newMap.has(k)) { remove++; blocks.push({ ...parseK(k), block: 'minecraft:air' }); }
}

const patch = { add, change, remove, total: blocks.length, blocks };
const text = JSON.stringify(patch, null, 1);
if (outPath) { fs.writeFileSync(outPath, text); console.log(`patch 已写入 ${outPath}`); }
else console.log(text);
console.log(`差量汇总: 新增 ${add} | 修改 ${change} | 删除 ${remove} | 共 ${blocks.length} 格`);
console.log(`应用: MCP build-blueprint 传 blocks=<patch.blocks>、origin=原建筑的 originX/Y/Z，随后 verify-region 验收`);

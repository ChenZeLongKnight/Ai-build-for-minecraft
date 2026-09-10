// 蓝图 JSON → .litematic 写入器（Litematica Version 6 / BlockStatePalette 列表格式）
// 可移植版：依赖解析自 mcserver 引擎（MC_BUILD_HOME 环境变量可覆盖，默认 D:/mcserver）
// 用法: node write_litematic.mjs <input.json> <output.litematic> [名称]
import { createRequire } from 'module';
import path from 'path';
import { pathToFileURL } from 'url';
import zlib from 'zlib';
import fs from 'fs';

const ENGINE = process.env.MC_BUILD_HOME || 'D:/mcserver';
const require = createRequire(pathToFileURL(path.join(ENGINE, 'noop.js')));
const { writeUncompressed } = require('prismarine-nbt');

// "minecraft:oak_log[axis=y]" → { Name, Properties }
function parseBlockName(str) {
  const m = str.match(/^([\w:]+)(?:\[(.*)\])?$/);
  if (!m) return { Name: 'minecraft:air' };
  const entry = { Name: m[1].includes(':') ? m[1] : 'minecraft:' + m[1] };
  if (m[2]) {
    const props = {};
    for (const kv of m[2].split(',')) {
      const [k, v] = kv.split('=');
      if (k && v !== undefined) props[k] = v;
    }
    if (Object.keys(props).length) entry.Properties = props;
  }
  return entry;
}

// 跨 long 连续位打包（litematica 规范，无对齐），返回 signed BigInt 数组
function packSpanning(entries, bits) {
  const longCount = Math.ceil((entries.length * bits) / 64);
  const longs = new Array(longCount).fill(0n);
  entries.forEach((v, i) => {
    for (let b = 0; b < bits; b++) {
      if ((v >> b) & 1) {
        const absBit = i * bits + b;
        longs[Math.floor(absBit / 64)] |= 1n << BigInt(absBit % 64);
      }
    }
  });
  return longs.map(l => BigInt.asIntN(64, l));
}

export function blueprintToLitematicNbt(bp, name = 'Unnamed', source = '') {
  let { width: W, height: H, length: L } = bp;
  if (!bp.blocks || !bp.blocks.length) throw new Error('蓝图没有体素');

  // 兼容两种体素写法：紧凑数组 [x, y, z, block] 与对象 { x, y, z, block }
  // （引擎的 build-blueprint 两种都吃，生成器习惯输出数组格式）
  bp.blocks = bp.blocks.map(b => Array.isArray(b)
    ? { x: b[0], y: b[1], z: b[2], block: b[3] }
    : b);

  // 自动按体素实际范围扩展尺寸（修改扩建后元数据未同步也不报错）
  for (const b of bp.blocks) {
    if (b.x < 0 || b.y < 0 || b.z < 0) throw new Error(`负坐标体素: ${JSON.stringify(b)}`);
    if (b.x + 1 > W) W = b.x + 1;
    if (b.y + 1 > H) H = b.y + 1;
    if (b.z + 1 > L) L = b.z + 1;
  }

  // 体素 → 全量索引（空气补 0），索引顺序 y 外层 → z → x 内层
  const map = new Map();
  for (const b of bp.blocks) {
    map.set((b.y * L + b.z) * W + b.x, b.block);
  }

  // 调色板：air 必须 0 号
  const paletteList = [{ Name: 'minecraft:air' }];
  const paletteIdx = new Map([['minecraft:air', 0]]);
  const setIdx = (block) => {
    const entry = parseBlockName(block);
    const key = entry.Name + (JSON.stringify(entry.Properties) || '');
    if (!paletteIdx.has(key)) {
      paletteIdx.set(key, paletteList.length);
      paletteList.push(entry);
    }
    return paletteIdx.get(key);
  };
  const entries = new Array(W * H * L).fill(0);
  for (const [idx, block] of map) entries[idx] = setIdx(block);

  const bitsPerEntry = Math.max(1, Math.ceil(Math.log2(paletteList.length)));

  const int = v => ({ type: 'int', value: v });
  const str = v => ({ type: 'string', value: v });

  const now = BigInt(Date.now()) * 1000n;
  const description = `modified=${new Date().toISOString()}` + (source ? `; source=${source}` : '');

  const nbt = {
    type: 'compound', name: '',
    value: {
      MinecraftDataVersion: int(3953), // 1.21
      Version: int(6),
      Metadata: {
        type: 'compound', value: {
          Name: str(name),
          Author: str('XiaoBuddy'),
          Description: str(description),
          RegionCount: int(1),
          TotalBlocks: int(map.size),
          TotalVolume: int(W * H * L),
          EnclosingSize: { type: 'compound', value: { x: int(W), y: int(H), z: int(L) } },
          TimeCreated: { type: 'long', value: now },
          TimeModified: { type: 'long', value: now }
        }
      },
      Regions: {
        type: 'compound', value: {
          main: {
            type: 'compound', value: {
              Position: { type: 'compound', value: { x: int(0), y: int(0), z: int(0) } },
              Size: { type: 'compound', value: { x: int(W), y: int(H), z: int(L) } },
              BlockStatePalette: { type: 'list', value: { type: 'compound', value: paletteList.map(e => {
                const c = { Name: str(e.Name) };
                if (e.Properties) c.Properties = { type: 'compound', value: Object.fromEntries(Object.entries(e.Properties).map(([k, v]) => [k, str(v)])) };
                return c;
              }) } },
              BlockStates: { type: 'longArray', value: packSpanning(entries, bitsPerEntry) },
              Entities: { type: 'list', value: { type: 'end', value: [] } },
              TileEntities: { type: 'list', value: { type: 'end', value: [] } },
              PendingBlockTicks: { type: 'list', value: { type: 'end', value: [] } },
              PendingFluidTicks: { type: 'list', value: { type: 'end', value: [] } }
            }
          }
        }
      }
    }
  };
  return { nbt, width: W, height: H, length: L };
}

export function writeLitematicFile(bp, outPath, name) {
  const { nbt } = blueprintToLitematicNbt(bp, name);
  const buf = zlib.gzipSync(writeUncompressed(nbt));
  fs.writeFileSync(outPath, buf);
  return buf.length;
}

// CLI 入口守卫（Windows 健壮版）：兼容盘符大小写、正反斜杠、URL 百分号编码差异；
// 未命中时不做任何事（作为模块被导入属正常情况）。唯一支持的命令行方式是 node 本脚本 + 参数，
// 经 stdin / --input-type=module -e 等方式调用时 argv[1] 为空，请改用模块导入 writeLitematicFile。
const invokedDirectly = (() => {
  if (!process.argv[1]) return false;
  try {
    const entry = pathToFileURL(path.resolve(process.argv[1])).href;
    const self = decodeURIComponent(import.meta.url);
    return process.platform === 'win32'
      ? entry.toLowerCase() === self.toLowerCase()
      : entry === self;
  } catch { return false; }
})();

if (invokedDirectly) {
  const [, , inPath, outPath, name] = process.argv;
  if (!inPath || !outPath) { console.error('用法: node write_litematic.mjs <input.json> <output.litematic> [名称]'); process.exit(1); }
  const bp = JSON.parse(fs.readFileSync(inPath, 'utf8'));
  const { nbt, width, height, length } = blueprintToLitematicNbt(bp, name || 'Unnamed', inPath);
  const buf = zlib.gzipSync(writeUncompressed(nbt));
  fs.writeFileSync(outPath, buf);
  console.log(`已写入 ${outPath} (${buf.length} bytes): ${width}x${height}x${length}, ${bp.blocks.length} 方块`);
}

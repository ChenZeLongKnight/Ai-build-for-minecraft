// .litematic/.schem/.nbt → 蓝图 JSON 转换桥（可移植版）
// 用途：MCP 服务进程还跑着旧解析器时，用命令行走新代码转换，产出给 build-blueprint 的 JSON
// 用法: node convert_litematic.mjs <input.litematic> <output.json>
// 引擎路径：MC_BUILD_HOME 环境变量可覆盖，默认 D:/mcserver
import path from 'path';
import { pathToFileURL } from 'url';
import fs from 'fs';

const ENGINE = process.env.MC_BUILD_HOME || 'D:/mcserver';
const { loadBlueprintFileAsync } = await import(
  pathToFileURL(path.join(ENGINE, 'dist', 'tools', 'schematic-tools.js')).href
);

const [, , src, out] = process.argv;
if (!src || !out) { console.error('用法: node convert_litematic.mjs <input> <output.json>'); process.exit(1); }

const bp = await loadBlueprintFileAsync(src);
console.log(`尺寸 ${bp.width}x${bp.height}x${bp.length}, 非空方块 ${bp.blocks.length}`);
fs.writeFileSync(out, JSON.stringify({ width: bp.width, height: bp.height, length: bp.length, source: bp.source, blocks: bp.blocks }, null, 1));
console.log('written:', out);

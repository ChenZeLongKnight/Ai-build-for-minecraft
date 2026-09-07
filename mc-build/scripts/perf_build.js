// 表演回放建造器：指令全部预生成，bot 作为"工人"逐条走位→看落点→挥手→执行
// 可移植版：依赖解析自 mcserver 引擎（MC_BUILD_HOME 环境变量可覆盖，默认 D:/mcserver）
// 用法: node perf_build.js <port> <username> <commands.txt> [每条间隔ms=400]
// ⚠️ 工人 bot 必须用第二用户名（如 XiaoGold），用 XiaoBuddy 会顶掉 MCP 会话的 bot
const path = require("path");
const ENGINE = process.env.MC_BUILD_HOME || path.join("D:", "work", "minecraft", "mcserver");
const mineflayer = require(path.join(ENGINE, "node_modules", "mineflayer"));
const Vec3 = require(path.join(ENGINE, "node_modules", "vec3"));
const fs = require("fs");

const [, , portArg, username, file, delayArg] = process.argv;
const port = parseInt(portArg || "25565", 10);
const DELAY = parseInt(delayArg || "400", 10);

// 解析指令的影响区域（用于走位和看向）
function regionOf(cmd) {
  const m = cmd.match(/^\/(fill|setblock) (-?\d+) (-?\d+) (-?\d+)(?: (-?\d+) (-?\d+) (-?\d+))?/);
  if (!m) return null;
  const a = [ +m[2], +m[3], +m[4] ];
  const b = m[5] ? [ +m[5], +m[6], +m[7] ] : a;
  return {
    min: [ Math.min(a[0],b[0]), Math.min(a[1],b[1]), Math.min(a[2],b[2]) ],
    max: [ Math.max(a[0],b[0]), Math.max(a[1],b[1]), Math.max(a[2],b[2]) ]
  };
}

const cmds = fs.readFileSync(file, "utf8").split("\n").map(s => s.trim()).filter(s => s.startsWith("/"));
if (cmds.length === 0) { console.error("指令文件为空: " + file); process.exit(1); }
const jobs = cmds.map(c => ({ cmd: c, region: regionOf(c) })).filter(j => j.region);

const bot = mineflayer.createBot({
  host: "localhost", port,
  username: username || "WorkerBot",
  auth: "offline",
  version: "1.21.1",
});

const sleep = ms => new Promise(r => setTimeout(r, ms));
let lastPos = null;

async function perform(j, i) {
  const [x0,y0,z0] = j.region.min, [x1,y1,z1] = j.region.max;
  const cx = (x0+x1)/2, cy = (y0+y1)/2, cz = (z0+z1)/2;
  // 工位：区域外沿东南方向站
  const sx = x1 + 1.5 + (x1-x0)/2, sy = y0, sz = z1 + 1.5 + (z1-z0)/2;
  const moved = !lastPos || Math.hypot(lastPos.x-sx, lastPos.z-sz) > 3.5;
  if (moved) {
    bot.chat(`/tp ${username} ${sx.toFixed(1)} ${sy} ${sz.toFixed(1)}`);
    await sleep(250); // 等传送落地
    lastPos = { x: sx, z: sz };
  }
  // 转头看向落点，挥手，执行
  try { bot.lookAt(new Vec3(cx, cy + 0.5, cz), true); } catch {}
  bot.swingArm();
  await sleep(120);
  bot.chat(j.cmd);
  console.log(`[${i+1}/${jobs.length}] ${j.cmd}`);
  await sleep(DELAY);
}

let done = false;
bot.on("login", () => console.log(`[perf_build] ${username} 已登录`));
bot.on("spawn", async () => {
  console.log(`[perf_build] 进入世界，表演回放 ${jobs.length} 条指令，节拍 ${DELAY}ms`);
  await sleep(800);
  const t0 = Date.now();
  for (let i = 0; i < jobs.length; i++) await perform(jobs[i], i);
  console.log(`[perf_build] 表演完成！耗时 ${((Date.now()-t0)/1000).toFixed(1)} 秒`);
  done = true;
  setTimeout(() => { bot.quit(); process.exit(0); }, 1200);
});
bot.on("message", (msg) => {
  const s = msg.toString();
  if (/无法|不能|错误|Invalid|Expected|Unknown|error/i.test(s)) console.log("[世界反馈] " + s);
});
bot.on("kicked", (r) => console.log("[perf_build] 被踢出: " + JSON.stringify(r)));
bot.on("error", (e) => console.error("[perf_build] 连接错误: " + e.message));

setTimeout(() => { if (!done) { console.error("[perf_build] 超时退出"); process.exit(2); } }, 120000);

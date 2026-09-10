---
name: mc-screenshot
description: 获取 Minecraft Java 版游戏内画面。用户在游戏中按 F2 截图后，从本地截图文件夹读取最新 PNG 并用多模态直接查看。适用于：验收 AI 建造效果、让 agent "亲眼"看到游戏画面、视觉迭代调整建筑。触发词：游戏截图、F2、看看游戏里什么样、截图验收。
---

# Minecraft 游戏内截图获取

## 核心原理

Minecraft Java 版按 **F2** 会把当前画面存为 PNG 到游戏目录的 `screenshots/` 文件夹，agent 可直接读取（Read 工具支持多模态看图）。这是最可靠的"游戏之眼"——真实光影、真实材质，零渲染误差。

## 关键路径（本机实测）

- **游戏目录**：`E:/Minecraft/.minecraft`（PCL/HMCL 启动器，1.21.1 实例）
- **截图文件夹**：`E:/Minecraft/.minecraft/screenshots`
- ⚠️ 不是官方启动器默认的 `C:/Users/ASUS/AppData/Roaming/.minecraft`（那里只有 runtime）。若未来换了启动器/实例，先用 `find ... -name "options.txt"` 或 `find ... -type d -name "1.21*"` 重新定位

## 操作流程

1. 请用户在游戏中按 **F2**（聊天栏会闪"已保存截图"）
2. 读取最新截图（bash）：
   ```bash
   ls -t "E:/Minecraft/.minecraft/screenshots" | head -3
   ```
3. 用 Read 工具直接看图（绝对路径）：
   ```
   Read("E:/Minecraft/.minecraft/screenshots/<最新文件名>.png")
   ```
4. 基于画面给出验收/调整意见

## 批量查看 / 拷贝

- 看最近 3 张：`ls -t` 后逐个 Read
- 需要在对话中展示给用户时，先 `cp` 到工作区（如 `D:/work/minecraft/shots/`）再 present_files

## 坑点

- F2 在聊天框打开时无效，先按 T 关聊天/按 F1 隐藏 HUD（可选）
- 截图文件名格式 `YYYY-MM-DD_HH.mm.ss.png`，按修改时间排序取最新最稳
- 若 `screenshots` 文件夹不存在说明从未按过 F2，游戏首次截图会自动创建（也可手动 mkdir 预创建）
- 系统截屏（Win+Shift+S 等）不落到此文件夹，必须游戏内 F2

## 典型场景

- **建造验收**：AI 用 /fill 建完 → 用户 F2 → agent 看图 → 提出或直接执行调整
- **视觉迭代**：蓝图渲染图只能校对布局，F2 截图才是最终观感裁决
- 配合本项目现有流水线：villa_gen.js 生成 → fast_build.js 落地 → F2 截图验收

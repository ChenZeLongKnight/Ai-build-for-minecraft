# 脚本路线与蓝图格式深度参考

本文件是 mc-design 技能的深度参考资料。设计器网页的使用说明书已并入 SKILL.md 正文（使用前必读），本文件只保留脚本路线的细节与蓝图格式的技术规范。全部内容来自 2026 年 9 月 7 日的实战验证。

## 设计产物规范

设计完成后产出三个文件，文件名统一以 `<名字>` 为前缀，全部写入引擎库 `<ENGINE>/schematics/`。

1. `<ENGINE>/schematics/<名字>.json` 为必需文件，即蓝图主文件，格式为 `{width,height,length,blocks:[{x,y,z,block:"minecraft:…"}]}`，坐标相对蓝图原点。路线 A 通过 `vd.download()` 下载 blueprint.json 后移动改名至此（蓝图数据不经过模型上下文），路线 B 自动产出。
2. `<ENGINE>/schematics/<名字>.litematic` 为存档文件，推荐生成，Litematica 模组可直接打开。脚本路线使用 `scripts/write_litematic.mjs` 生成。
3. `<名字>_fills.txt` 为 /fill 指令清单，仅在收到指令清单需求时生成，每行一条 /fill 或 /setblock 指令。

design_template.mjs 的复刻版产物直接写入引擎库 `<ENGINE>/schematics/`，无需手动复制。

## write_litematic.mjs 用法与注意事项

- 命令行用法（推荐）：`node write_litematic.mjs <input.json> <output.litematic> [名称]`。
- 不要以 `node -e "import(...)"` 方式动态调用该脚本：脚本尾部的命令行守卫依赖 `process.argv[1]`，在 -e 模式下该值为 undefined，会抛出 `ERR_INVALID_ARG_TYPE` 错误。
- 体积自动扩展：当体素实际范围超出 JSON 元数据中记录的 width、height、length 时，脚本会自动扩展尺寸，因此扩建后即使忘记同步元数据也不会报错；命令行打印的是扩展后的真实尺寸。此项为 2026 年 9 月 7 日的修复，起因是扩建灯柱时触发了越界报错。

## 一次性脚本约定（避免返工）

- 导入技能脚本时一律采用 `pathToFileURL(path.join(...)).href` 形式的动态导入，不要手工书写 `file:///` 前缀。原因在于 Windows 下以 `C:/` 开头的裸路径不是合法的 ESM URL，会抛出 `ERR_UNSUPPORTED_ESM_URL_SCHEME` 错误；而基于 `import.meta.url` 的相对引用（`new URL('./x.mjs', import.meta.url)`）只在脚本留在技能目录时有效，复制到工作区后即失效。
- 产物直接写入引擎库 `<ENGINE>/schematics/`，不要使用相对当前工作目录的路径。引擎目录的取值为 `ENGINE = process.env.MC_BUILD_HOME || 'D:/mcserver'`。
- 模板的第四个命令行参数是名称（`node design_x.mjs ox oy oz 名字`），其目的是避免覆盖与模板同名的产物文件。
- 回读校验打印 `N/M` 时，M 大于 N 属于正常现象：同一格被多次 put 时会去重，只要没有「丢失」或「多余」报错即为通过。
- 一次性设计脚本使用完毕后应归档（例如存放到 `D:/work/minecraft/`），不要堆积在技能目录中。

## 蓝图格式规范（读写 litematic 时查阅）

三种蓝图格式均为 NBT 结构（gzip 压缩），使用 prismarine-nbt 库解析。

- .litematic（Litematica 格式）：Region 内的 BlockStatePalette 为列表形式 `[{Name, Properties}]`（新版）；旧版使用 Palette 名字到序号的映射，解析器对两种形式均需兼容。方块数据按条目位打包：位宽等于 max(1, ceil(log2(paletteSize)))，跨 long 连续排列且无对齐，需用 BigInt.asUintN/IntN(64) 处理符号。索引顺序为 y 在最外层、z 次之、x 在最内层，即 `(y*L+z)*W+x`。Size 字段为负表示该轴翻转。写出文件时，空气必须占据调色板的 0 号位置。
- .schem（Sponge 格式）：Palette 为名字到序号的复合标签，BlockData 为 varint 字节流，索引公式为 `x + z*W + y*W*L`。
- .nbt（原版结构格式）：palette 列表加 blocks 列表，每项包含 pos 与 state。
- 写出文件时先调用 `writeUncompressed`，再用 `zlib.gzipSync` 压缩（prismarine-nbt 未提供同步写方法）。

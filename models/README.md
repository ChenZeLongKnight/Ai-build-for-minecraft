# 模型权重

`mc-design` 技能的图片还原路线（`scripts/photo2blueprint.py`）需要一个显著性分割模型，用来从照片中自动抠出画面主体。脚本按质量优先自动挑选，权重文件默认放在 `~/.workbuddy/models/`（可用环境变量 `SUBJECT_MODEL_DIR` 覆盖）。

## 目录内容

| 文件 | 大小 | 说明 |
|---|---|---|
| `u2netp.onnx` | 4.4 MB | 轻量版，**已随仓库提供**。边缘略粗，网速受限时够用 |
| `u2net.onnx` | 167.8 MB | 完整版，**未随仓库提供**——超出 GitHub 单文件 100 MB 上限。边缘能出绒毛级细节，会把背景杂物整块判为背景，脚本默认优先使用 |

两者都不需要时也可不下载：权重缺失时脚本会打印下载地址并退出，不影响其他功能。

## 获取完整版

下载后放进权重目录，文件名保持 `u2net.onnx`，脚本会自动优先选它：

```bash
curl -L -o ~/.workbuddy/models/u2net.onnx \
  https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx
```

国内网络可在地址前加镜像前缀 `https://ghfast.top/` 或 `https://gh-proxy.com/`。

## 说明

- 权重来自 [rembg](https://github.com/danielgatis/rembg) 发布的 U²-Net 模型，原项目以 Apache License 2.0 发行。
- 脚本对权重文件做双重校验：体积需达到期望值的九成以上，且能被推理引擎成功加载。下载中断产生的半截文件会被自动跳过并打印原因，不会导致脚本崩溃。
- 运行不依赖 PyTorch。`.onnx` 是模型交换格式，由 onnxruntime 直接推理；图片还原路线共需 `onnxruntime`、`numpy`、`Pillow`、`scipy` 四个 Python 包。

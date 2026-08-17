# ComfyUI H3 Atoms

[English](README.md)

用于 ComfyUI 的 MiniMax H3 组合节点，覆盖 Prompt 规则、生成设置、参考媒体、OpenAI-compatible API 和官方 H3 conditioning 接线。

本扩展基于 ComfyUI 新节点 API（`comfy_api.latest`），并调用 ComfyUI 自带的官方 `comfy_extras.nodes_minimax_h3`。

## 节点

| 节点 | 作用 |
|---|---|
| `H3 Prompt Rules Loader` | 组合执行契约、Core H3 规则、Base/Ref guide 和一个可选 Style，输出 `rules: STRING`。 |
| `H3 Generation Settings Pack` | 规范化模式，并把时长对齐到 H3 24fps `17k+5` 帧网格，输出 `H3_GENERATION_SETTINGS`。 |
| `H3 Reference Pack` | 规范化参考图片、视频帧批次、视频配套音频、独立音频和首尾帧，输出 `H3_REFERENCE_PACK`。 |
| `H3 API Profile` | 生成不包含 API key 的 OpenAI-compatible 配置，输出 `H3_API_PROFILE`。 |
| `H3 LLM Prompt Process` | 发起一次多模态 completion 请求，返回 `final_prompt` 和 `output_msg`。 |
| `H3 Unified Encode` | T2VA/I2VA/FL2VA/L2VA 委托 `MiniMaxH3ImageToVideo`，Ref2VA 委托 `MiniMaxH3ReferenceToVideo`。 |

## 工作流

```text
Reference Pack ─────┬──────────────────────────────────────────────┐
Settings Pack ──────┤                                              │
Rules Loader ───────┤                                              │
User Prompt ────────┼──> H3 LLM Prompt Process ──> final_prompt ───┤
API Profile ────────┘                                              │
clip ──────────────────────────────────────────────────────────────┤
vae ───────────────────────────────────────────────────────────────┤
audio_vae (Ref2VA) ────────────────────────────────────────────────┘
                                                                   │
                                                                   v
                                                     H3 Unified Encode
                                                                   │
                                                                   v
                                                         positive + latent
```

推荐连接方式：

1. 让 `H3 Prompt Rules Loader` 和 `H3 Generation Settings Pack` 使用相同的 `workflow_mode`。
2. 按模式把参考媒体或首尾帧连到 `H3 Reference Pack`。
3. 在 `H3 API Profile` 配置 endpoint、模型和 API key 环境变量名。
4. 把规则、设置、用户输入和媒体包接入 `H3 LLM Prompt Process`。
5. 把 `final_prompt`、两个 pack、`clip`、`vae`、`audio_vae` 接入 `H3 Unified Encode`。
6. 后续继续连接 MiniMax H3 sampler/save 节点。

## API Profile

API key 不会写入 workflow JSON。设置 `api_key_env` 指定的环境变量，例如：

```powershell
$env:H3_API_KEY = "your-key"
```

支持：

- `base_url`、`model`
- `max_completion_tokens` 或 `max_tokens`
- 可选 `reasoning_effort`
- 超时、JPEG 质量和视频抽帧数量
- 按媒体类型开关发送
- `direct_video` 标记；当前 OpenAI-compatible 路径遇到参考视频时会明确报错

## 当前限制

- 图片和视频抽样帧以 JPEG data URL 发送。
- 通用 OpenAI-compatible endpoint 暂不支持原始视频/音频上传。
- `send_ref_audio=true` 和 `direct_video=true` 会明确报错，不会静默丢素材。
- 暂不包含 Gemini Native 和 Google Files API。

## Requirements

- 包含官方 MiniMax H3 extras（`comfy_extras.nodes_minimax_h3`）的 ComfyUI。
- ComfyUI 自带 Python 环境提供 `torch`、`Pillow`、`av`。
- 正常使用不需要额外安装 pip 包，详见 `requirements.txt`。

## 安装

把本目录放入 `ComfyUI/custom_nodes/` 并重启 ComfyUI：

```powershell
git clone https://github.com/TommyShing/ComfyUI-H3-Atoms.git
Copy-Item -Recurse ComfyUI-H3-Atoms E:\Stable Diffusion\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\ComfyUI-H3-Atoms
```

## 开发

纯核心测试：

```powershell
python -m unittest discover -s tests -v
```

节点 schema 测试需要 ComfyUI 自带 Python：

```powershell
E:\Stable Diffusion\ComfyUI-aki-v3.2\python\python.exe -m unittest discover -s tests -v
```

## License

本项目使用 GNU Affero General Public License v3.0 or later。详见 `LICENSE` 和 `NOTICE`。

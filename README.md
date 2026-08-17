# ComfyUI H3 Atoms

Composable MiniMax H3 prompt, media, API, and conditioning nodes for ComfyUI.

This package targets the ComfyUI new node API (`comfy_api.latest`) and the installed official `comfy_extras.nodes_minimax_h3` module.

## Nodes

| Node | Purpose |
|---|---|
| `H3 Prompt Rules Loader` | Composes execution contract, core H3 rules, Base/Ref guide, and one optional Style rule into a `rules: STRING`. |
| `H3 Generation Settings Pack` | Normalizes mode and snaps duration to the H3 24 fps `17k+5` frame grid. Outputs `H3_GENERATION_SETTINGS`. |
| `H3 Reference Pack` | Normalizes reference images, video-frame batches, paired video audio, standalone audio, and first/last keyframes into `H3_REFERENCE_PACK`. |
| `H3 API Profile` | Builds a non-secret OpenAI-compatible API profile. Outputs `H3_API_PROFILE`. |
| `H3 LLM Prompt Process` | Sends one multimodal completion request and returns `final_prompt` plus `output_msg`. |
| `H3 Unified Encode` | Routes to `MiniMaxH3ImageToVideo` for T2VA/I2VA/FL2VA/L2VA and `MiniMaxH3ReferenceToVideo` for Ref2VA. |

## Workflow

```text
Reference Pack ──┐
Settings Pack ───┤
Rules Loader ────┤--> H3 LLM Prompt Process --> H3 Unified Encode --> positive + latent
User Prompt ─────┤              |
API Profile ─────┘              +--> final_prompt / output_msg
```

Typical chain:

1. Set the same `workflow_mode` on `H3 Prompt Rules Loader` and `H3 Generation Settings Pack`.
2. Connect reference media and keyframes into `H3 Reference Pack` as required by the mode.
3. Configure `H3 API Profile`. API keys are read from an environment variable at request time and are never stored in the workflow JSON.
4. Connect all inputs into `H3 LLM Prompt Process`.
5. Connect `final_prompt`, both packs, `clip`, `vae`, and `audio_vae` into `H3 Unified Encode`.
6. Continue with the normal MiniMax H3 sampler/save nodes.

## API Profile

The API key is not a widget value. Set the environment variable named by `api_key_env`, for example:

```powershell
$env:H3_API_KEY = "your-key"
```

Supported fields:

- `base_url`, `model`
- `max_completion_tokens` or `max_tokens`
- optional `reasoning_effort`
- timeout, JPEG quality, and sampled video frame count
- per-category media sending flags
- `direct_video` flag, which is intentionally rejected by the OpenAI-compatible adapter when reference videos are present

## Current limitations

- Images and sampled video frames are sent as JPEG data URLs.
- Raw video and audio upload are not implemented for generic OpenAI-compatible endpoints.
- `send_ref_audio=true` and `direct_video=true` produce clear errors rather than silently dropping media.
- Gemini Native and Google Files API are not implemented here.

## Installation

Copy this directory into `ComfyUI/custom_nodes/` and restart ComfyUI:

```powershell
git clone https://github.com/TommyShing/ComfyUI-H3-Atoms.git
Copy-Item -Recurse ComfyUI-H3-Atoms E:\Stable Diffusion\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\ComfyUI-H3-Atoms
```

## License

This project is licensed under the GNU Affero General Public License v3.0 or later. See `LICENSE` and `NOTICE` for attribution details.

## Development

Pure core tests run with any Python 3.10+:

```powershell
python -m unittest discover -s tests -v
```

The node schema tests need ComfyUI's bundled Python because they import `comfy_api.latest`:

```powershell
E:\Stable Diffusion\ComfyUI-aki-v3.2\python\python.exe -m unittest discover -s tests -v
```


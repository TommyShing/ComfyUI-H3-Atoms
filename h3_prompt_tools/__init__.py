"""Pure-Python core for ComfyUI H3 Prompt Tools."""

from .settings import build_generation_settings
from .rules import RuleBundle

__all__ = ["RuleBundle", "build_generation_settings"]


async def comfy_entrypoint():
    """ComfyUI extension entrypoint. Imported lazily so pure core stays ComfyUI-free."""
    from .nodes import H3PromptToolsExtension

    return H3PromptToolsExtension()


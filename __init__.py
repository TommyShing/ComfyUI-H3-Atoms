"""ComfyUI entrypoint for the H3 Prompt Tools custom node package."""


async def comfy_entrypoint():
    from .h3_prompt_tools.nodes import H3PromptToolsExtension

    return H3PromptToolsExtension()

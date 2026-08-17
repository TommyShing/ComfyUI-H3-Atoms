# MiniMax H3 Prompt Rules

This directory is the version-controlled source for the rule bundle consumed by the planned custom ComfyUI node `H3 Prompt Rules Loader`.

## One loader, modular files

The ComfyUI workflow exposes one loader node and one `rules: STRING` output. The files remain modular internally so that official mode guides can be updated independently from our prompt-only style adaptations.

The loader composes, in this order:

1. `execution-contract.md`
2. `core.md`
3. `modes/base-en.txt` for T2VA/I2VA/FL2VA/L2VA, or `modes/ref-en.txt` for Ref2VA
4. `style-contract.md` plus one selected file from `styles/`, unless style is `None`

Only the combined result is exposed to the workflow. Core rules are always active; style is optional.

## Source policy

- `core.md` is a prompt-only adaptation of the official `h3-prompt-writing` skill.
- `modes/base-en.txt` and `modes/ref-en.txt` are verbatim official mode guides.
- `styles/*.md` are concise prompt-only adaptations generated from the official eight style skills, using Easy only as an integration reference.
- Hub tools, canvas delivery, approval gates, asset generation, editing agents, and multi-turn instructions are deliberately removed.

## Snapshot

- Official repository: `MiniMax-AI/MiniMax-H3`
- Official commit: `d21241f0a4b3acbb34c97dae47fa417b7065e438`
- Easy reference: `nkxx188/ComfyUI-MiniMaxH3-Easy`
- Easy commit: `404e6e8c3af4d013c275f773da09e181765cdc14`
- Adapted: 2026-08-16


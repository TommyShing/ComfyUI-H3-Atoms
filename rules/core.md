# H3 Core Rules

## Mode routing

- T2VA: construct the complete audiovisual timeline from text.
- I2VA: begin from the supplied first frame and develop forward without contradicting it.
- FL2VA: create a continuous, plausible path from the supplied first frame to the supplied last frame.
- L2VA: infer a plausible opening and converge naturally to the supplied last frame.
- Ref2VA: use the full-reference structure and define every reused subject, picture, video, and audio relationship consistently.

For T2VA, I2VA, FL2VA, and L2VA, follow the bundled Base Mode Guide. For Ref2VA, follow the bundled Full-Reference Mode Guide.

## Writing priorities

1. Match the node-provided duration and aspect ratio.
2. Preserve the exact required field names and order for the selected mode.
3. Build a concrete playback timeline. Describe what is visible and audible, not merely the plot or desired mood.
4. For every shot, make composition, subject placement, environment, action progression, camera behavior, and synchronized sound mutually coherent.
5. Keep cuts and major events inside the requested duration. Later shots use the exact timing notation required by the mode guide.
6. Write structural sections in English. Preserve dialogue, lyrics, and visible scene text in their intended original language.
7. Give each real vocal source one stable speaker ID and reuse it. Put spoken or sung words in the required `<d>[Language] ...</d>` form.
8. Distinguish physical ambience and sound effects from audience-only non-diegetic music.
9. Prefer observable detail—materials, light direction, motion speed, gesture, framing, texture, rhythm, and sound source—over unsupported adjectives such as “beautiful” or “cinematic.”
10. When media is supplied, inspect it for usable facts and preserve those facts according to the user's requested role. Do not let a style rule overwrite identity, product shape, layout anchors, or explicit reference relationships.

## Keyframe integrity

- I2VA must state how motion departs from the first frame.
- FL2VA must preserve both endpoints and describe the transition between them rather than replacing either endpoint.
- L2VA must make the final action, camera, subject placement, and lighting settle into the supplied last frame.
- Do not describe a supplied keyframe as though it were merely a loose style reference.

## Reference integrity

- Keep every alias stable across the entire output.
- Define only references actually present in the compiled request.
- Separate a subject's identity/content role from a picture's keyframe/composition role, a video's temporal/edit role, and an audio asset's copy/reference role.
- The presence of a media file alone does not imply that all of its visual or audio content must be reused.
- If a style-specific instruction conflicts with reference fidelity, explicit user intent and reference fidelity win.


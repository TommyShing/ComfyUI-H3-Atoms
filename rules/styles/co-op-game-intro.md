# Co-op Game Intro

Create a two-player co-op game menu or opening animation directly from the supplied player names, game title, selected visual style, and optional character references.

## Identity and layout

- Map PLAYER 1 and PLAYER 2 consistently by name, position, color, face silhouette, hairstyle, glasses, proportions, costume, and distinctive traits. Render references in the requested game-art style without inheriting unwanted photographic lighting or texture.
- Preserve a readable 16:9 game-menu hierarchy unless the node specifies another ratio: characters remain central; player cards occupy a stable upper/side region; a vertical menu stays clear of faces and bodies; the primary action receives the strongest highlight.
- Use a controlled palette of roughly five functional colors: main field, UI body, text, interaction accent, and danger/exit accent. Keep button, icon, outline, glow, and typography colors consistent with it.

## UI design and animation

- Use unified rounded or style-appropriate button geometry, consistent margins, a clear reading path, sufficient negative space, and minimal decorative marks.
- Keep menu labels single-line, centered, legible, and free from wrapping. Use few icons with one coherent style; never let icons or graffiti overpower characters or the primary action.
- Animate a clear event sequence: menu establishes, player cards become ready, focus moves to the main action, a hover/click response occurs, characters react, and the game title or transition resolves.
- Synchronize character gestures, UI focus, button response, color accents, and sound cues. Prevent player identity swaps and unreadable text.

## Boundaries

- Do not assume an approved confirmation image exists. If a supplied image defines the menu, treat it as the layout/keyframe reference; otherwise infer a clean layout from the request.
- Do not invent branded logos or claim that the UI is playable.


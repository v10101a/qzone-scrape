# QQ Music Player — JS reimplementation (Webamp-style) · PROOF OF CONCEPT

Goal: replace the Ruffle/Flash music-player skins in the museum with a **pure
JS/HTML player** that still renders the *original* QQ skins — like
[Webamp](https://webamp.org) does for Winamp `.wsz` skins. No Flash black box,
full control over the ticker / buttons / state.

## Why this is feasible (the key finding)

All **249** skins in `../library/player/*.swf` are built from **one shared Flash
template**. Parsing a sample from across the collection, every skin has the
*same internal control names*:

| piece        | SWF element                          | role                    |
|--------------|--------------------------------------|-------------------------|
| `playButton` | `DefineButton2`                      | play                    |
| `stopButton` | `DefineButton2`                      | stop                    |
| `nextButton` | `DefineButton2`                      | next                    |
| `rewind`     | `DefineButton2`                      | prev                    |
| `JSTxt`      | `DefineEditText`                     | the scrolling ticker    |
| (background) | `DefineBitsJPEG3` / `DefineBitsLossless2` | the skin artwork   |

Marquee logic lives in one `DoAction` (`onEnterFrame` moving `JSTxt` between
`minX`/`maxX` — i.e. the scroll we already reimplement in the museum overlay).

This is exactly the property that made Webamp possible: **a shared convention,
so we write the player logic ONCE and every skin slots in.** The difference from
Webamp is the skin is a *program* (`.swf`) not a documented bitmap pack — but
because they share a template, we only extract known, named pieces.

## Pipeline

1. **Extract** (`extract/`) — per skin, pull from the `.swf`:
   - the background image (`DefineBitsJPEG3`/`Lossless2`) → `skins/<id>.png`
     *(or reuse the already-rendered `../site/assets/player_gallery/<id>.png`)*
   - the placement rect (x,y,w,h, in px = twips/20) of each named button + `JSTxt`
   - emit `skins/<id>.json`: `{ bg, w, h, buttons:{play,stop,next,prev:[x,y,w,h]}, ticker:[x,y,w,h] }`
   - A minimal stdlib SWF tag parser already works (see chat history /
     `../pipeline/analyze.py`); for robustness, [JPEXS/ffdec](https://github.com/jindrapetrik/jpexs-decompiler)
     CLI can batch-export shapes/images/coords (`.gitignore` already reserves `tools/ffdec*/`).

2. **Player component** (`web/`) — one JS module that takes `(bg, region-json)` and:
   - draws the background PNG
   - overlays transparent real `<button>`s at the button rects → wired to the
     museum's existing `setMusic` / `toggleMusic` audio
   - renders a real HTML ticker in the `JSTxt` rect (our own marquee — full control)

3. Drop-in replace `addPlayer()` in `../site/qzone-library.js`.

## Sample assets to develop against

`extract/10268.{swf,png}` and `extract/10269.{swf,png}` — one skin's source +
its rendered preview, for building/validating the extractor and coordinate mapping.

## Hard parts (known, deferred)

- **Animated skins** (spinning disc / EQ bars from the 11 `DefineSprite`s) freeze
  under a static-bg approach. Capturing them = extracting sprite frames per skin.
- **Coordinate mapping**: SWF twips → the preview PNG's pixel scale must line up
  or buttons land off; verify per skin (or automate a check).
- **Button press art**: needs the button "down" frame; CSS active-state is a fine v1 stand-in.

## Next step

Build the end-to-end POC on `10268` only: extract → `skins/10268.json` → render in
`web/` next to the Ruffle version. If coordinates land cleanly, batch the other 248.

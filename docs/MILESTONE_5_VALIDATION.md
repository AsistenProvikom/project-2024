# Milestone 5 - Project 2024 Gallery Validation

Date: 2026-11-23
Evidence: `docs/verification/3a-integration.json`
Automated external suite: **54/54 checks passed**
Scope: local Chromium run against the CheerpJ CDN

## Status Matrix

| Game | Player | Automated evidence | Status | Remaining limitation |
|---|---|---|---|---|
| Car Traffic | generated | Canvas mount, menu render, menu interaction, restart, Stop, Back | Runtime-verified locally | Manual gameplay acceptance still recommended |
| Flappy Bird | generated | Canvas mount, menu render, PLAY transition, Stop, Back | Runtime-verified locally | Manual gameplay acceptance still recommended |
| Paddle Game | generated | Canvas mount, level select, Easy mode, `AbsoluteLayout.jar` Range request, Stop, Back | Runtime-verified locally | Manual gameplay acceptance still recommended |
| Froggie Cross the Road | legacy | Catalog mode only | Not visually accepted | Launcher/gameplay not exercised in this run |
| Minesweeper | legacy | Catalog mode only | Not visually accepted | Launcher/gameplay not exercised in this run |
| Pong | legacy | Catalog mode and explicit audio limitation | Blocked by known limitation | Not launched; browser audio limitation remains |
| Snake | legacy | Launcher surface, first-input repaint, Stop, Back | Launcher state verified; gameplay unverified | Gameplay not exercised |

## Snake Rendering Finding

The previous snapshot was taken before Snake's canvas painted. A longer probe
showed the applet starts successfully but the initial canvas can remain visually
blank:

- before input: 71 unique colors, luminance stddev 15.91;
- after a center click: 208 unique colors, luminance stddev 20.64.

The updated check clicks the center of the canvas and requires a non-blank
repaint. It does **not** claim that the game is playable. The durable screenshot
`docs/screenshots/3a-legacy-snake.png` now shows the post-input state.

This is a rendering-trigger issue in the legacy path, not evidence of a Java
exception. No fatal console/page errors were recorded.

## Generated Game Notes

- Car Traffic, Flappy Bird, and Paddle Game remain on the generated CheerpJ
  players introduced in Milestone 3A.
- Paddle Game's dependency is served under `/str/` and supports HTTP Range.
- Generated artifacts load only after Play; Stop and Back remove the iframe.
- No generated SwingJS artifact is added to the portal because licensing and
  redistribution approval remain unresolved.

## Remaining Work

- Manual visual/gameplay acceptance for Froggie, Minesweeper, Pong, and Snake.
- Pong's audio limitation remains and is disclosed rather than hidden.
- Manual review of generated gameplay beyond automated canvas/interaction
  checks.
- Publication remains blocked by B-002, B-003, B-004, and B-005.

# Brand icons — design

**Date:** 2026-07-28
**Status:** implemented

## Problem

The integration ships no brand imagery, so Home Assistant renders a generic
placeholder wherever `samsung_tv_frame` appears.

The historical fix — opening a PR against `home-assistant/brands` under
`custom_integrations/` — is no longer available. That folder is legacy and the
repository auto-closes new custom-integration PRs. Since **HA 2026.3.0** a custom
component ships its own brand images and the core `brands` integration proxies
them through `/api/brands/integration/{domain}/{image}`, preferring local files
over the CDN.

`hacs.json` declared a 2026.1.0 minimum, below the 2026.3 floor, so on 2026.1–2026.2
the `brand/` folder would be silently ignored and those installations would keep
the placeholder. Rather than ship an asset that does nothing for part of the
supported range, the minimum is raised to **2026.3.0** — the version that
introduced the brands proxy. This is a breaking change for installations still on
2026.1 or 2026.2 and is recorded as such in the changelog.

## Constraints

The integration is unofficial and not endorsed by Samsung.

An icon is a *source identifier* — the slot where a brand asserts origin. Placing
the Samsung wordmark or logo there would fail the nominative-fair-use conditions
that the integration's naming currently satisfies, and would read as a claim of
endorsement.

Samsung blue as a colour carries no meaningful exposure: single colours are hard
to protect, and the hue on a non-Samsung glyph identifies no source.

## Decision

Device-first artwork in Samsung's blue, carrying no Samsung marks of any kind.

**Palette**

| Role | Light | Dark |
|---|---|---|
| Primary | `#1428A0` | `#6B8AFF` |
| Accent | `#5C7CFA` | `#A9BEFF` |

The dark variants lift the same hues so they hold contrast against the HA dark
theme, where `#1428A0` reads as near-black.

**Composition**

A thick rectangular bezel in primary with slightly rounded corners, landscape at
roughly 16:9, wrapping an accent canvas that holds a minimal abstract artwork:
one circle in the upper area, one diagonal horizon crossing the lower area, both
in primary.

The heavy bezel is the single trait that distinguishes a Frame from any other TV,
and the artwork inside says *art mode* — which is what this integration is
actually about — while the aspect ratio keeps it reading as a television. No
stand, legs, buttons or cables.

Shares its corner radius, stroke weight, palette and margin with the
`samsung_ac_windfree` icon so the two read as a matched pair in the integrations
list.

## Assets

`custom_components/samsung_tv_frame/brand/`

| File | Size |
|---|---|
| `icon.png` | 256×256 |
| `icon@2x.png` | 512×512 |
| `dark_icon.png` | 256×256 |
| `dark_icon@2x.png` | 512×512 |

Flat colour, transparent background, trimmed to content with a uniform 4% margin,
PNG optimised. `logo.png` is deliberately omitted — the core fallback chain
resolves `logo*` requests to `icon.png`.

The folder name must be exactly `brand`: `homeassistant/loader.py` derives
`has_branding` from `"brand" in self._top_level_files`. No manifest change is
required.

## Production

Generated with `openai/gpt-5.4-image-2` via OpenRouter. Codex CLI cannot do this —
it has no image generation and authenticates with a ChatGPT OAuth token that
cannot reach the images endpoint.

The OpenAI provider rejects `background: "transparent"` and returns RGB with no
alpha; asked for transparency it paints a checkerboard. So each icon renders at
1024×1024 on a flat pure-magenta field, and post-processing snaps every pixel to
the nearest of {magenta, primary, accent}. That both keys out the background and
corrects the model's colour drift to exact brand hexes. Alpha comes from a
separately resized coverage mask, so the downscale anti-aliases without leaving a
magenta fringe.

Verified: zero residual magenta pixels, alpha present, exact palette hexes
dominant, legible at 32×32.

# Changelog

## Unreleased

- Tooling only; no runtime behavior change. Ruff has been failing on `main`
  since 0.8.0 through no code fault: `astral-sh/ruff-action` installs the newest
  ruff on every run, so the rule set changed underneath the repo. Pin ruff to
  0.16.3 in CI and clear all 80 findings. Bump the pin deliberately, with the
  resulting fixes in the same commit.
- Replace the pure `try/except/pass` teardown blocks with
  `contextlib.suppress(...)`. This is behavior-preserving:
  `asyncio.CancelledError` derives from `BaseException`, so `suppress(Exception)`
  still lets cancellation propagate exactly as the explicit re-raise did.
  Deliberate broad excepts that run recovery code keep their handler and carry a
  justified `# noqa: BLE001`.
- Pin `pytest-homeassistant-custom-component==0.13.355` (Home Assistant
  2026.8.1) so the test environment matches the core running in production. The
  harness previously floated to an older core than we ship against, which is
  what allowed the 0.9.1 requirement conflict to reach production with a green
  suite. With the pin in place, `tests/test_manifest.py` reads the real
  production constraints and does catch that manifest.

## 0.9.1

- **FIX:** the integration failed to load on Home Assistant 2026.8 and later,
  leaving the config entry in `not_loaded` with no entities and no error in the
  log. `async-upnp-client` was pinned to `==0.46.2`, but Home Assistant core
  constrains it to `==0.47.1` in `package_constraints.txt` and installs custom
  integration requirements under that constraint. Pip resolution failed
  (`ResolutionImpossible`), so setup aborted before the module was ever
  imported.
- Drop `async-upnp-client` from `requirements` and declare `ssdp` in
  `dependencies` instead. The core `ssdp` integration already provides
  `async_upnp_client` at whatever version core ships, so the library is
  guaranteed present and the version coupling is gone for good. A custom
  integration cannot pin a core-managed package: core bumps it on its own
  schedule and any fixed pin eventually becomes unsatisfiable.
- Declaring `ssdp` as a dependency also matches the `ssdp` discovery matchers
  this manifest already declares, mirroring core's own `samsungtv` integration.
- Add `tests/test_manifest.py`, which fails if any manifest requirement pins a
  version that Home Assistant's `package_constraints.txt` disallows. The
  original pin was correct when written and only became unsatisfiable when core
  bumped the library, so nothing in the suite could have caught it; this check
  turns that silent production failure into a red build instead.
- Unpin `async-upnp-client` in `requirements_test.txt` (`>=0.46.2`) so the test
  environment stops reproducing the same conflict as Home Assistant advances.

## 0.9.0

- **BREAKING:** raise the minimum Home Assistant version from 2026.1.0 to
  2026.3.0. Installations on 2026.1 or 2026.2 must update Home Assistant before
  taking this release.
- Ship brand images inside the integration (`custom_components/samsung_tv_frame/brand/`)
  so the integration shows its own icon instead of a placeholder. Home Assistant
  2026.3.0 serves local brand images through the brands proxy and prefers them
  over the CDN; the previous route, a pull request against
  `home-assistant/brands` under `custom_integrations/`, is no longer accepted.
- Icons carry no Samsung wordmark or logo. See
  `docs/superpowers/specs/2026-07-28-brand-icons-design.md`.

## 0.8.0

- **BREAKING:** rename integration domain `samsungtv_frame` → `samsung_tv_frame`
  and repository `ha-samsungtv-frame` → `ha-samsung-tv-frame`. There is no
  migration: remove the old integration entry and `custom_components/samsungtv_frame`
  directory, install this version, and re-add the TV via the config flow.
  All services move to the new domain (e.g. `samsung_tv_frame.set_slideshow`);
  automations, scripts, and dashboards referencing `samsungtv_frame.*` services
  or device triggers must be updated. Entity IDs are re-created by the fresh
  config entry. Older changelog entries below retain the historical names.

## 0.7.1

- Treat silently unsupported optional Art capability reads as bounded probes,
  allowing modern-to-legacy fallback without closing a healthy websocket.
- Require same-generation correlated liveness before caching Art settings or
  slideshow dialects, while retaining supervised recovery for ambiguous
  all-silent transports.
- Route slideshow writes through the read-proven generation dialect so older
  Frame firmware does not time out on an unsupported modern command.

## 0.7.0

- Read all advertised local Art settings as one aggregate, generation-scoped snapshot
  and expose the live-verified Sleep After, neutral motion-sensitivity, and automatic
  brightness-sensor controls without SmartThings.
- Add read-only slideshow state, including duration and category, while keeping
  `samsungtv_frame.set_slideshow` as the single atomic write surface for duration,
  shuffle order, and category.
- Reconcile optional Art state directly after successful local mutations so entity
  state reflects authoritative readback rather than an optimistic value.
- Add strictly allowlisted, zero-I/O Home Assistant diagnostics for integration and Art
  session health without exposing device addresses, credentials, artwork, apps, or raw
  protocol data.
- Intentionally make the existing art brightness and color-temperature entities
  unavailable when the TV is off or their optional Art state is not authoritative for
  the current ready session, instead of exposing an unknown or stale value.

## 0.6.9

- Use a curated built-in app catalog for the media-player source dropdown instead of
  attempting runtime installed-app discovery, whose unanswered websocket requests could
  stall foreground commands. Raw Tizen app ids remain launchable with
  `media_player.play_media`.
- Pair the remote-control channel first during setup, reconfiguration, and
  reauthorization, then validate Art with the same canonical token.
- Reconfigure now requires the TV to show normal TV or app content and the user to
  accept the new Allow prompt.
- Persist a changed remote token synchronously before a successful foreground command
  returns, including before power-off can make the TV unreachable.
- On an ordinary stale remote connection, close the exact captured failed client before
  retrying once with the same credential.
- Route `ms.channel.timeOut` from foreground remote commands through Home Assistant
  reauthorization while preserving the stored token, instead of silently retrying
  without one or treating the event as proof that the credential is invalid. Background
  polling never starts pairing or opens an authorization prompt.

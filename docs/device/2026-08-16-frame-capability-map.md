# Frame TV capability map — QE65LS03B (2022, `22_PONTUSM_FTV`)

**Date:** 2026-08-16 · **Integration:** v0.9.1 · **Core:** HA 2026.8.1, Python 3.14
· **Library:** `samsungtvws` 3.0.5

A lay of the land of what this TV model actually supports — documented and
undocumented — set against what the integration currently controls, reports and
promises. The point is to find where those three disagree.

Sanitized per `AGENTS.md`: no host, MAC, token, or artwork identifier appears
here. The device is referred to generically throughout.

## How to read the confidence labels

The repo's live-protocol-first doctrine says upstream documentation and other
models are hypotheses, not evidence. This document keeps that distinction
strictly, because most of the risk lives in the gap between them:

| Label | Meaning |
|---|---|
| **CONFIRMED** | Observed on *this* TV, with a probe note, changelog entry or test fixture behind it |
| *ASSUMED* | The code depends on it, but nothing here proves it on this model |
| *UNKNOWN* | Never examined |
| **MISMATCH** | The integration's promise and the device's established reality actually disagree |

Tally across 42 capabilities: **11 CONFIRMED · 12 ASSUMED · 5 UNKNOWN · 14 MISMATCH.**

A caveat that colours everything below: the D2D upload/thumbnail evidence and
all art-push evidence predate the v0.6.7 async transport rewrite, and **no
release since v0.7.1 has been exercised against the device.** A CONFIRMED label
means "confirmed against the old transport" more often than is comfortable.

## Method

Five independent read-only audits ran in parallel — entity surface, state
machine, library API, repo evidence, external research — then a synthesis pass
adjudicated their disagreements against the source, and a completeness critic
attacked the result. Every high-severity claim below was then re-verified by
hand against the code.

Live measurement ran alongside, deliberately **without** opening an art
websocket: project memory records a connect livelock (v0.5.7) in which two of
our own clients poison each other's handshake. Raw network signals were sampled
directly; art state was read from the integration's own entities instead.

## Newly measured this session

These are fresh observations on the live device, all reproducible:

- **Device identity.** `FrameTVSupport: true`, `TokenAuthSupport: true`,
  `OS: Tizen`, `networkType: wireless`. Open TCP services: **8001** (REST),
  **8002** (secure websocket), **9197** (UPnP/DMR), **8080**. Port **7676** is
  actively refused, not filtered.
- **Slideshow reading is correct — independently verified.** The integration
  reported `sequential, duration_minutes: 5`; sampling the artwork identifier
  every 30 s for 26 minutes showed rotation at **exactly 5-minute intervals**
  across 6 artworks. This is the strongest positive confirmation in the whole
  document: a device reading cross-checked against an independent measurement.
- **This corrects project memory,** which recorded the TV rotating store art
  "~hourly on its own". The observed cadence is the configured 5-minute
  slideshow interval.
- **`category_id` is populated** (`ARTSTREAM`), which contradicts the audit
  finding that this firmware omits it and the integration therefore publishes
  `None` indefinitely. The synthesized-`duration_minutes` concern applies only
  to the `off` payload.
- **Current settings:** art brightness 5, colour temperature 0, motion
  sensitivity 2, brightness sensor on, and **sleep-after = 60 minutes** — the
  timer directly implicated in the open question below.
- **The integration agrees with the device in this state.** With the TV in art
  mode, every signal lined up: `tv_mode=art_mode`, `art_mode=on`,
  `media_player=on`, all optional entities live.

## The open question: the dark-panel state

The motivating question — *"the TV was not really off, only art mode was not
displaying, because the motion sensor blanks the screen after a while"* — is
**not yet resolved**, and this document does not claim otherwise.

What is established: with `sleep-after = 60 minutes`, the panel is expected to
blank after an hour without motion. What is *not* established is what happens to
the TV's network services at that moment, and that is the whole question,
because of how the integration decides the TV is off.

An earlier reading in this session that suggested a novel "ICMP up, all TCP
ports closed" state was a **measurement artifact** — busybox `sh` does not
implement `/dev/tcp`, so every port test returned a false negative. It is
withdrawn. No such state has been observed with a reliable tool.

But the question it raised stands on its own, because of a genuine structural
finding:

> **`reachable` is not reachability.** It means "an HTTP GET to TCP 8001
> `/api/v2/` returned a `device` object within 8 s". ICMP, port 8002, port 9197
> and ARP are never consulted anywhere in the integration — verified by grep.

So *any* condition that stops port 8001 answering — a blanked panel, a Tizen
hiccup, an AP outage, a DHCP change — is reported as a confident `off`. Whether
the motion-sensor blank is such a condition is exactly what the P0 probes below
must settle. Two OFF fingerprints are already on record for this model and they
differ from each other: a ~3-minute standby window with the NIC up and 8001
answering `PowerState: standby`, and a later phase where the TV drops off Wi-Fi
entirely.

A sampler is running for 6 hours to catch the transition. It can only see it if
the room actually empties for the full hour.

## Capability matrix

### power/state

#### Reachability oracle (`reachable`) — **MISMATCH**

- **Integration claims:** "The TV is on the network and talking to us."
- **Device reality:** Actually: one HTTP GET to TCP 8001 `/api/v2/` returned a truthy `device` object within 8 s. coordinator.py:143-144 -> device.py:222-228 -> rest.py:19-41. `except Exception` collapses RST, filtered-port timeout, HTTP error, and non-JSON into one indistinguishable None. ICMP, ARP, 8002 and 9197 are never consulted (grep for icmp|ping in custom_components/ returns nothing).

#### OFF derivation (unreachable => OFF, 2-poll debounce) — **MISMATCH**

- **Integration claims:** Two consecutive unreachable heartbeats mean the TV is powered off. const.py:62 OFF_DEBOUNCE_COUNT=2; coordinator.py:201-215.
- **Device reality:** Live record for this model is TWO-PHASE, not one: a 3 s KEY_POWER hold puts it into a ~3 MIN standby window with the NIC UP and REST answering PowerState="standby" (memory frame-state-detection, live 2026-07-07; commit 469fcef), and only later does it drop off WiFi (spec 2026-07-01:41). The observed ICMP-up/all-TCP-closed state matches NEITHER phase — in the standby phase 8001 answers. Unreachable is therefore not a proven OFF fingerprint.

#### PowerState "standby" on this model — **CONFIRMED**

- **Integration claims:** `standby_wins` learned trait: once art has been seen with PowerState "on", standby unconditionally means shutdown. models.py:60-61; coordinator.py:311-313, 472-473.
- **Device reality:** CONFIRMED observed on this model, contrary to the older 2026-07-01 spec note that PowerState is "always on when reachable" (superseded). Commit 469fcef timed it live 2026-07-07. The trait is learned per-process, never persisted, never unlearned — after every HA restart the ~50 s dying-art-socket ART blip returns until art is seen with PowerState "on" again.

#### Entity availability when the TV cannot be reached — **MISMATCH**

- **Integration claims:** Entities go unavailable when the integration cannot talk to the TV.
- **Device reality:** Inverted. entity.py:52-67 has no `available` override; an unreachable TV yields a SUCCESSFUL poll (coordinator.py:142-276) that asserts OFF. media_player, remote, tv_mode, current_art and binary_sensor art_mode all stay available and positively assert "off". Only optional-art entities and the art switch gate. No entity, attribute or trigger anywhere exposes "lost contact" as distinct from "off".

#### Art app UI state "nav" — **MISMATCH**

- **Integration claims:** Art mode is a boolean: device.py:396-401 maps any value != "on" to False, so the TV reports WATCHING.
- **Device reality:** CONFIRMED live on THIS model (operator memory, 2026-07-02): "get_artmode() can transiently return 'nav' (menu) besides on/off". Independently corroborated by a 2025 LS03F firmware decompile (ArtScreenAPI.GetUIStatus -> off|nav|on). The string "nav" appears NOWHERE in custom_components/, docs/ or tests/ (verified by grep). While the art menu is on screen the integration publishes WATCHING with full confidence.

#### tv_mode ENUM sensor options — **CONFIRMED**

- **Integration claims:** off / watching / art_mode. sensor.py:30-45.
- **Device reality:** TvMode.UNKNOWN is deliberately not an option, so a transitional or art-dead TV publishes HA state "unknown" while the entity stays available. No device trigger exists for it (device_trigger.py:24-28), so automations cannot react to "the integration lost track of the TV".

#### PowerState missing or unrecognized — **MISMATCH**

- **Integration claims:** Not modelled.
- **Device reality:** If REST answers with a device dict lacking PowerState (or any third value), four guards disengage at once: reconcile_due is False forever (coordinator.py:169-180), the art socket is never reconnected (art_session.py:132), the art-failure streak resets every poll (coordinator.py:185-186) so the 6-strike bound never engages, and derive_tv_mode falls to UNKNOWN which is replaced by last-stable. tv_mode freezes indefinitely with entities available and no warning.

#### Wake-on-LAN turn_on — *ASSUMED*

- **Integration claims:** Powers the TV on and detects the wake quickly. device.py:632-635; wake probe coordinator.py:404-443.
- **Device reality:** CONFIRMED live (~4 s warm / 12-15 s cold). Two unproven edges: the magic packet goes to a HARDCODED 255.255.255.255 (operator notes record needing a subnet broadcast in at least one environment), and a WoL wake with no active source lands the TV in a no-signal zombie that powers itself off minutes later. Failure after 30 attempts is only a log warning; the service never fails. The wake probe tests only port 8001, so it is blind in exactly the observed ICMP-up state.

#### Motion-sensor / Sleep-After blank as a state — *UNKNOWN*

- **Integration claims:** Not modelled anywhere. The design explicitly excludes motion events, Night Mode and ambient-light readings from scope.
- **Device reality:** The integration WRITES the exact setting that causes the blank (motion_timer) and cannot observe its effect. No TvMode value, entity or push event represents "art mode, panel asleep". No motion/screen-off broadcast is documented to exist on the art channel in any source. This is the leading hypothesis for the observed ICMP-up/TCP-closed state and is entirely unprobed.


### art mode

#### Art-mode read (`get_artmode_status`) — **CONFIRMED**

- **Integration claims:** Authoritative ART/WATCHING discriminator. frame_art.py:380.
- **Device reality:** CONFIRMED correlated success on this model (hotfix design 2026-07-22:27). Excluded from probe treatment by design, so a timeout here retires the whole art generation.

#### Art push events (art_mode_changed / image_selected / go_to_standby) — **CONFIRMED**

- **Integration claims:** Sub-second art and artwork changes via d2d_service_message. coordinator.py:463-527.
- **Device reality:** CONFIRMED live on this model incl. the JSON-string-inside-envelope decode and the TV's own store-art rotation (memory 2026-07-02/07-08; commits ac72d16, 577bcef, 6eec4a8). Caveats: the pushed snapshot reuses the LAST POLLED PowerState (coordinator.py:506-508); the alias spellings artmode_status / image_changed are defensive, not observed; power-off from art emits art_mode_changed(off) first, giving a measured ~7 s false WATCHING blip.

#### Art-mode WRITE (`set_artmode_status`) — switch + set_art_mode service — *ASSUMED*

- **Integration claims:** Clickable art<->watching toggle. switch.py:33-69; frame_art.py:382-386.
- **Device reality:** The READ is in the live matrix; the WRITE is not — no probe note, changelog entry or fixture records this model acknowledging it. A 2025 decompile indicates it is an app-control launch (mode=fullscreen/exit), not a state flag, and is disclaimer-gated. If silently ignored it burns the 20 s deadline and retires the art generation.

#### binary_sensor art_mode when the TV is off — **MISMATCH**

- **Integration claims:** "on when the TV is displaying art mode."
- **Device reality:** No availability gate (binary_sensor.py:23-35). When tv_mode is OFF the coordinator FORCES art_mode=False (coordinator.py:263) — a positive assertion about a TV it cannot see. Consumers cannot distinguish "art is off" from "we cannot know".


### art settings

#### Aggregate settings read (`get_artmode_settings`) — **CONFIRMED**

- **Integration claims:** Capability oracle; drives availability of all six optional entities. frame_art.py:394 (probe=True); art_settings.py:65.
- **Device reality:** CONFIRMED correlated aggregate success on this model (hotfix design:29). But the parser reads only `item`/`value` (art_settings.py:66-101) and silently DROPS unrecognized items (art_settings.py:83-86) — any additional setting this firmware advertises is invisible, never logged.

#### Per-item min / max / valid_values from the device — *UNKNOWN*

- **Integration claims:** Not read at all. Ranges are hardcoded: brightness 0-10, colour temp -5..5 (art_settings.py:50-57), motion timer 7 values, sensitivity {1,2,3} (art_settings.py:14-15).
- **Device reality:** Other firmwares are documented to return min/max/valid_values per item, and report different ranges (2025: brightness 0-50, colour temp 0-4; a 2019 capture shows a motion-timer valid_values list with no "5"). Whether THIS firmware advertises ranges is unprobed. Any device value outside the hardcoded bounds is normalised to None, so the entity goes unavailable rather than showing the truth.

#### Art brightness (number 0-10) — *ASSUMED*

- **Integration claims:** Slider with authoritative readback. number.py:30-64.
- **Device reality:** Scale 0-10 confirmed live (commit 577bcef, pre-rewrite). Read path CONFIRMED only via the aggregate — the legacy `get_brightness` getter is a CONFIRMED silent timeout on this firmware (hotfix design:30). The WRITE `set_brightness` has NO recorded live ack on current firmware and is sent as a non-probe (frame_art.py:416): if it is also silently ignored, every slider move costs 20 s and closes the art socket.

#### Art colour temperature (number -5..5) — *ASSUMED*

- **Integration claims:** Slider with authoritative readback. number.py:67-101.
- **Device reality:** Identical asymmetry to brightness: scale confirmed pre-rewrite, `get_color_temperature` is a CONFIRMED silent timeout (hotfix design:31), `set_color_temperature` has no live ack and is a non-probe write (frame_art.py:420).

#### Sleep After / motion timer (select, 7 options) — *ASSUMED*

- **Integration claims:** Seven writable choices: off/5/15/30/60/120/240 min, labelled "Art sleep after". select.py:32-66; art_settings.py:14.
- **Device reality:** Setter ack shape CONFIRMED live with exactly ONE value ("5"), readback confirmed, original restored (phase1 design:194-200). The other six are an assumed client-side frozenset. The wire key is `motion_timer`; the mapping to the user-facing concept "Sleep After" is an interpretation — nothing records observing the TV's own menu change. Other firmwares document additional values ("always", "180").

#### Motion sensitivity (select, 1/2/3) — *ASSUMED*

- **Integration claims:** Three neutral protocol states, deliberately unlabelled. select.py:69-105.
- **Device reality:** Setter ack CONFIRMED live with value "1" only. The domain {1,2,3} is a client-side guess; the ordering and human meaning are explicitly undetermined by design (phase1 design:103-110). Correctly refuses to guess labels.

#### Automatic brightness sensor (switch) — **CONFIRMED**

- **Integration claims:** Enable/disable the TV's auto art-brightness. switch.py:72-110.
- **Device reality:** CONFIRMED live for the "off" write with ack shape and restore (phase1 design:194-200; fixture tests/test_frame_art.py:359-405). The "on" write is inferred symmetry, not recorded. Readback is via the aggregate only.

#### Optional-art freshness gate (`art_setting_available`) — **CONFIRMED**

- **Integration claims:** The six optional entities are unavailable unless the value is authoritative for the current READY art generation. entity.py:14-49.
- **Device reality:** Verified correct and the strongest part of the surface. Note the asymmetry: current_art, art_mode and volume carry NO equivalent gate.


### artwork

#### Artwork enumeration / gallery (`get_content_list`) — *UNKNOWN*

- **Integration claims:** Nothing — not implemented. The integration tracks only the single current content id.
- **Device reality:** The request exists in the pinned library (art/art.py:345) and is never sent. There is no way to browse, and no way to validate a content_id before select/delete/matte/filter. Unprobed on this model.

#### current_art sensor freshness — **MISMATCH**

- **Integration claims:** Content id of the artwork currently selected. sensor.py:48-61.
- **Device reality:** Unlike every other art-derived entity, current_art has NO generation-freshness gate (coordinator.py:265): while the TV is on but the art session is dead it keeps publishing the last-known content id indefinitely; it is cleared only at OFF. This model rotates store art on its own (~hourly, confirmed live), so the held value goes stale silently.

#### Thumbnail image entity — **MISMATCH**

- **Integration claims:** Thumbnail of the currently displayed artwork. image.py:30-78.
- **Device reality:** Transport CONFIRMED: singular `get_thumbnail` is ignored by this firmware, `get_thumbnail_list` is answered, store artworks are DRM-refused, user uploads return real JPEGs (memory 2026-07-08). But three silent-wrong paths in image.py:56-69: on any fetch failure it serves the PREVIOUS artwork's bytes; when current_art is None it still serves the last fetched image; DRM refusal serves a bundled placeholder — which on this TV is the COMMON case since nearly all displayed art is store content. image_last_updated is bumped on content change even if the fetch then fails.

#### select_art / upload_art — *ASSUMED*

- **Integration claims:** Show an artwork by content id; upload a local file (allowlist-gated). media_player.py:254-281.
- **Device reality:** Upload/select/delete round-trip CONFIRMED live (commit 577bcef) — but on the PRE-REWRITE synchronous transport. The v0.6.7 native-async D2D re-implementation has NO post-rewrite live record. D2D framing on both read and write sides is derived from the library and an external fork, explicitly labelled "a protocol reference, not a source dependency". Which upload branch this TV takes (api_version 0.97 websocket-binary vs D2D) has never been observed.

#### delete_art result reporting — **MISMATCH**

- **Integration claims:** Irreversibly delete an artwork; the service reports success.
- **Device reality:** `FrameArt.delete` DOES validate the echoed content-id list (and handles a JSON-string response via json.loads, frame_art.py:461-477) and returns a bool — but `device.async_delete_art` (device.py:553-556) DISCARDS the return value and the service ignores it. A TV response that does not confirm the deletion is reported to the user as success.

#### set_favourite service — **MISMATCH**

- **Integration claims:** Mark/unmark an artwork as favourite. frame_art.py:502-511, waiting on sub-event `favorite_changed`.
- **Device reality:** CODE-VERIFIED CORRELATION HAZARD. The live-derived ack shape for THIS firmware (three probed setters) is event == the request name with a matching request_id. The dispatcher (frame_art.py:913-920) resolves an id-matched waiter ONLY if sub_event equals the expected one or is "error"; the uuidless rescue path is skipped whenever a request_id is present. So if the TV acks with event `change_favorite`, the waiter never resolves: 20 s timeout, websocket closed, art generation retired — on EVERY invocation. No favourite state is exposed, so nothing else would reveal it. Never probed.


### slideshow

#### Slideshow read (sensor, off/sequential/shuffle) — *ASSUMED*

- **Integration claims:** Read-only slideshow mode with duration and category attributes. sensor.py:64-98.
- **Device reality:** Only the LEGACY getter answers on this firmware and the only observed value is "off" (hotfix design:33). "sequential"/"shuffle" have never been seen here. `duration_minutes` is SYNTHESIZED as 0 when parsing the observed off payload (art_settings.py:112), not read from the device. `category_id` is absent from the observed payload and publishes as None indefinitely.

#### set_slideshow service — **MISMATCH**

- **Integration claims:** Atomically set duration, shuffle order and category. media_player.py:290-299.
- **Device reality:** Split reality: `set_auto_rotation_status` (modern) is a CONFIRMED SILENT TIMEOUT here; `set_slideshow_status` (legacy) is a CONFIRMED correlated success — but only for the identity write (off -> off). A real duration/shuffle/category write has never been live-verified. Worse, device.py:591-612 falls through to the modern-first path whenever the dialect is UNKNOWN (fresh generation before first reconcile) or UNSUPPORTED — reachable whenever a user calls the service after a new art generation, and that first command is the confirmed silent timeout that closes the socket.

#### Slideshow category ids — *ASSUMED*

- **Integration claims:** Three named category constants documented to the user as fact in services.yaml:95-100 and strings.json:133, one hardcoded as the service default.
- **Device reality:** Not enumerated from the TV and in no live-probe note; upstream/library-derived. A wrong id is a free-text write with the same silent-timeout / session-kill exposure as any other unvalidated art command.


### matte

#### change_matte service — *UNKNOWN*

- **Integration claims:** Change an artwork's matte by free-text matte id, with example ids shown to the user. media_player.py:301-311.
- **Device reality:** ZERO live evidence anywhere in docs, changelog, git log or session notes. No matte catalogue is fetched (`get_matte_list` exists in the library at art/art.py:815 and is never called), so ids cannot be validated. No matte state is exposed anywhere, so a wrong value can never be noticed. Defaults to the ungated current_art, which can be stale.


### photo filter

#### set_photo_filter service — *UNKNOWN*

- **Integration claims:** Apply a photo filter by free-text filter id. media_player.py:313-324.
- **Device reality:** Same asymmetry: `get_photo_filter_list` exists in the library (art/art.py:800) and is never called. No live evidence. Additionally it requests NO refresh at all and there is no state anywhere reflecting a filter — a pure write-only promise.


### remote keys

#### All remote-channel writes (send_key, transport keys, volume step, turn_off, app launch) — **MISMATCH**

- **Integration claims:** The service returns success.
- **Device reality:** Systemically unacknowledged by library construction: samsungtvws 3.0.5 `async_connection.send_commands` writes each frame and awaits nothing. Success means "frames were written to a socket". A typo'd key, an unsupported key and a working key are indistinguishable. No readback exists for any of them.

#### turn_off (3 s KEY_POWER hold) — **CONFIRMED**

- **Integration claims:** Truly powers the TV off, not just art mode. device.py:637-646.
- **Device reality:** CONFIRMED on this model (a single press only toggles art mode). Requires a valid REMOTE-channel grant, which is granted separately from the art channel and whose prompt renders only while WATCHING. Library inserts a ~1 s key_press_delay per element, so the "3 s" hold is ~5-6 s of held lock; no test measures this (tests zero the delay).

#### Transport controls (play/pause/stop/next/previous) — *ASSUMED*

- **Integration claims:** Advertised unconditionally in supported_features, including in art mode and while off. media_player.py:215-228.
- **Device reality:** No live evidence for any of these five key codes on this model, and the library does not even list KEY_PLAY/KEY_PAUSE/KEY_STOP among its named helpers. Whether the foreground app honours them is app-dependent and unobservable.


### apps/sources

#### source_list — **MISMATCH**

- **Integration claims:** A dropdown of app names. media_player.py:162-166; const.py:94-102.
- **Device reality:** CONFIRMED only negatively: this model ACCEPTS but NEVER ANSWERS `ed.installedApp.get` (commit 3b7fe17; memory), so runtime discovery is disabled (device.py:661-663) and the list is a curated static 7-app catalog. It is not a statement about what is installed; selecting an absent app still "succeeds".

#### source / app_name (foreground detection) — *ASSUMED*

- **Integration claims:** Name of the foreground app while watching, via REST GET /api/v2/applications/<id> and a `visible` flag. coordinator.py:354-371.
- **Device reality:** The single shipped READ path with NO probe evidence at all on this model — the `visible` field name and semantics appear in no live matrix, only synthetic fixtures. The only recorded REST-application observation here is that LAUNCH over REST is capricious (sometimes 401). On failure `source` degrades silently to "TV", which is indistinguishable from real live-TV/HDMI. Costs 7 REST calls per WATCHING poll.


### volume/mute

#### volume_level (UPnP RenderingControl) — **CONFIRMED**

- **Integration claims:** Absolute volume 0-1 from the TV's UPnP RenderingControl at port 9197. device.py:230-253.
- **Device reality:** CONFIRMED live (set + track, commits b99ccf9/577bcef). The `/dmr` URL is the device description; the control URL is discovered from it, so the survey-claimed mismatch with the memory's control path is not real. Read only while reachable AND PowerState=="on", else None -> "unknown" not unavailable. CurrentVolume/100 with no clamping. No repo-level deadline on the UPnP path.

#### is_volume_muted (GetMute/SetMute) — *ASSUMED*

- **Integration claims:** Real mute state, not a blind toggle.
- **Device reality:** The live notes record volume get/set on this model; GetMute/SetMute are not separately recorded. Shares the volume read's failure path — (None, None) on any UPnP error, so mute reads "unknown" rather than unavailable.


### discovery/pairing

#### SSDP / DHCP discovery — **MISMATCH**

- **Integration claims:** manifest.json declares an ssdp matcher and a dhcp hostname matcher (`samsung*`) and depends on ssdp.
- **Device reality:** config_flow.py implements NO async_step_ssdp and NO async_step_dhcp (verified: only reauth, reauth_confirm, reconfigure, user, init). HA will start a discovery flow for any matching Samsung device and find no handler, so discovery cannot complete; the dhcp matcher also fires for non-Frame Samsung devices. Discovery was in the original design and never implemented. Consequence: a DHCP address change makes the TV permanently "OFF" with no repair flow.

#### Pairing model (one Allow grants both channels) — **CONFIRMED**

- **Integration claims:** One Allow tap grants remote + art; the returned token is stored. config_flow.py:128-162.
- **Device reality:** CONFIRMED by a controlled live test (remote-pairing design:19-30). But live notes also record: grants are PER CHANNEL and per client NAME; the Allow prompt renders only while WATCHING; an art-origin token presented to the remote channel gets an INSTANT ms.channel.timeOut with no prompt; a hard power cycle can wipe the grant; and tokens are flaky across boots (accepted at one boot, rejected the next). Silent reauth prompts are expected behaviour here, not a defect.

#### Frame detection gate (FrameTVSupport == "true") — **CONFIRMED**

- **Integration claims:** Rejects non-Frame Samsung TVs. config_flow.py:120-126.
- **Device reality:** CONFIRMED on this model. Fragile typing: exact string comparison against "true" while the library does str(...).lower()=="true"; a firmware returning a real boolean or "True" aborts setup as not_a_frame.


## Where promise and device disagree

Ranked by user-visible harm: a wrong state that breaks automations outranks
a cosmetic attribute. Every HIGH below was re-verified by hand against the source.

### H1. Any condition that stops port 8001 answering is reported as a confident OFF

**Symptom.** tv_mode flips to 'off', the 'turned_off' device trigger fires, and on recovery 'started_watching'/'entered_art_mode' fire again — spurious off/on cycles in automations and history for a TV that may be perfectly alive. Any automation keyed on off/on runs at the wrong time, and there is no way to write an automation on 'lost contact' instead.

Full traced path: REST connect to 8001 fails -> async_device_info returns None (device.py:225-228) -> reachable=False, power_state=None (coordinator.py:143-145) -> art work skipped entirely (art_session.py:132) -> art-failure streak RESET each poll (coordinator.py:185-186) so tv_mode can never reach 'unknown' -> poll 2 derives TvMode.OFF (models.py:58-59). The model is CONFIDENT: there is no path by which an unreachable TV becomes `unknown` instead of `off`.

**Scope correction.** An earlier reading in this session appeared to show a novel "ICMP up, all TCP ports closed" state. That was a measurement artifact — busybox `sh` does not implement `/dev/tcp`, so every port test returned a false negative — and it is withdrawn. No third network state has been observed with a reliable tool.

What survives the correction is the structural defect, which does not depend on that observation at all: `reachable` is a single-signal oracle over port 8001, so **whatever** silences that port — a blanked panel, a Tizen crash, an AP outage, a DHCP reassignment — becomes a confident `off` with entities still available asserting it. Two OFF fingerprints are already recorded for this model and they differ from each other: the ~3 min post-power-hold standby window keeps the NIC up *and* 8001 answering `PowerState='standby'` (memory, live 2026-07-07; commit 469fcef), while the later phase drops off Wi-Fi entirely including ICMP (spec 2026-07-01:41). A blank-panel state, if it silences 8001, would be indistinguishable from either.

Note two surveys asserted 'standby has never been observed on this model' — that is wrong, and traceable to the superseded 2026-07-01 spec table; the whole `standby_wins` mechanism exists precisely because standby IS observed here.

### H2. Nothing anywhere distinguishes 'cannot reach the TV' from 'the TV is off'

**Symptom.** Operators cannot build 'TV unreachable' alerting, and cannot tell a network fault from a power-off. A DHCP address change makes the TV permanently 'off' with no repair path.

`reachable` exists only inside FrameData and the zero-I/O diagnostics snapshot (coordinator.py:96-124). No entity, attribute or device trigger exposes it. Entity availability tracks only last_update_success, which an unreachable TV does NOT clear because the poll succeeds and reports OFF (entity.py:52-67 has no `available` override). A Wi-Fi/AP outage, a DHCP reassignment, a Tizen crash, a filtered port, or a move to Ethernet all publish a positively-asserted 'off'. The dhcp/ssdp matchers that could repair an address change have no config-flow handler, so recovery is manual.

### H3. `set_favourite` will very likely time out and retire the art session on every call

**Symptom.** Calling set_favourite hangs 20 s, then errors; the art websocket drops and art_mode/current_art/all six optional entities go stale or unavailable until the session is rebuilt. No favourite state is exposed anywhere, so nothing else would ever reveal the problem.

Code-verified, not inferred. frame_art.py:502-511 waits for sub-event `favorite_changed`. The dispatcher at frame_art.py:913-920 resolves an id-matched waiter only when sub_event equals the expected one or is 'error', and the uuidless rescue path is explicitly skipped when a request_id is present (`uuidless = self._uuidless_pending if message_id is None else None`). The live-derived ack shape for THIS firmware — established from the three probed setters — is event == the request name with a matching request_id. If the TV acks with event `change_favorite`, the future never resolves: 20 s non-probe deadline, websocket closed, art generation retired (frame_art.py:822-831). Never probed.

### H4. `set_slideshow` falls through to a confirmed-dead command whenever the dialect is not yet learned

**Symptom.** A slideshow automation fired shortly after HA restart or an art reconnect kills the art session instead of setting the slideshow, cascading into stale art state for every art entity.

device.py:591-612 routes to the legacy setter only when `_slideshow_dialect is LEGACY`; for UNKNOWN (fresh art generation, before the first reconcile) or UNSUPPORTED it falls through to the modern-first `FrameArt.set_slideshow`. On this firmware `set_auto_rotation_status` is a CONFIRMED silent timeout (hotfix design:34) — and it is a non-probe write, so it burns 20 s, closes the websocket and retires the generation. This is reachable any time a user calls the service after a reconnect but before the first reconcile. Additionally, the only slideshow write ever live-verified is the identity restore (off -> off); a real duration/shuffle/category write is unproven.

### H5. `nav` — a live-confirmed third art-app state on THIS model — is silently reported as WATCHING

**Symptom.** Opening the art menu on the TV publishes tv_mode 'watching' and fires the started_watching device trigger. Lights/scenes bound to art->watching transitions run because someone pressed a menu button. Same defect class as the ~7 s shutdown blip the project already fought.

The operator's own live probe (2026-07-02) recorded that get_artmode can transiently return 'nav' (menu) on this TV, and the design-era guidance was 'treat non-on as not-art'. device.py:396-401 does exactly that. The string 'nav' appears NOWHERE in custom_components/, docs/ or tests/ (verified by grep) — it was never encoded as a distinct state. With PowerState 'on', a nav sample derives WATCHING with full confidence. Corroborated independently by a 2025 firmware decompile documenting off|nav|on from ArtScreenAPI.GetUIStatus().

### Medium

- **delete_art reports success even when the TV did not confirm the deletion** — A delete that the TV declined, partially applied, or answered ambiguously is reported to the user as success. The artwork is still on the TV; the user believes it is gone.

- **current_art (and the image entity) publish stale artwork indefinitely while the art session is dead** — A dashboard shows an artwork the TV stopped displaying hours ago, with a fresh-looking timestamp. `_resolve_content_id` (media_player.py:363-369) then defaults change_matte / set_photo_filter / set_favourite to that stale id, so the mutation lands on the WRONG artwork and reports success.

- **Every remote-channel write reports success on socket write alone** — Scripts appear to work while the TV does nothing. A typo'd key code, an uninstalled app, and a correct command are all indistinguishable to the caller.

- **Unvalidated free-text domains are session-killers on this firmware, not error messages** — Picking an unsupported option from a dropdown, or passing an upstream-derived matte/filter/category id, drops the art websocket for 20 s rather than returning a clean error.

- **The learned `standby_wins` trait is lost on every restart and can never be unlearned** — Right after an HA restart, powering the TV off from art leaves tv_mode stuck on 'art_mode' for the better part of a minute, so 'turned_off' automations fire late.

- **PowerState missing or unrecognized freezes tv_mode forever with no warning** — tv_mode is frozen at whatever it last was, indefinitely, with every entity available and asserting it, and nothing in the logs. The worst unrepresentable state in the model.

- **The manifest advertises SSDP and DHCP discovery that cannot complete** — Discovery notifications that dead-end, plus the absence of the one mechanism that could repair a changed IP address — which is exactly the failure the reachability model cannot otherwise survive.

### Low

- **Poll deadline can be exceeded by a serialized worst-case poll, flipping every entity to unavailable** — All entities briefly go unavailable together with no state explanation, and the art-health counters do not reflect that anything went wrong.

- **Sleep-After is a labelled interpretation of the wire key `motion_timer`** — A user sets what they believe is a screensaver timer and gets different behaviour; also directly relevant to gap #1, since this is the one control that can cause the panel to blank.

- **Attributes published as real but permanently synthetic or blank** — A dashboard binding to slideshow category gets a permanent blank presented as a real attribute; a diagnostics reader concludes the TV lacks settings it actually supports.


## Probe plan

Ordered by priority. **[MUTATES]** marks a probe that changes a device setting
or power state; per `AGENTS.md` each must capture the original value, make the
smallest reversible change, read it back authoritatively, and restore and verify
the original even if the probe fails.

- **P0** What IS the state in which the TV answers ICMP while 8001/8002/9197/7676 are all closed — is it still the paired TV at that address at all, and which of the two recorded OFF phases (if either) is it?
  - *Method:* Before touching anything, resolve identity: read the ARP/neighbour entry for the address from the HA host and compare the MAC against the config entry's paired MAC (compare a hash or the last octets only; do not record either value). A mismatch means DHCP reassigned the address to a foreign host and the whole question dissolves. If it matches, run a 1 Hz logger for >=6 min capturing, per tick: ICMP reachability, TCP connect result for 8001, 8002, 9197 (connect-only, 2 s timeout, no handshake, no client name -> no Allow prompt), and on any 8001 success the REST /api/v2/ PowerState. Compare the resulting trace against the two recorded fingerprints: phase 1 = NIC up + 8001 ANSWERING + PowerState 'standby' (~3 min after a power hold), phase 2 = full WiFi drop incl. ICMP loss. The observed state matches neither, so the deliverable is a third named fingerprint plus the answer to whether 8001 ever reopens on its own.
  - *Requires:* The TV must already be in, or be allowed to drift into, the observed state. Human confirms by eye and records: is the panel fully dark, showing art, or showing a no-signal message; and what was the last thing done to the TV (power hold, left alone in art, woken by WoL). That observation is the ground truth the trace is matched against, and nothing else can supply it.

- **P0** **[MUTATES]** Does the motion-sensor / Sleep-After blank produce exactly the observed ICMP-up, all-TCP-closed fingerprint?
  - *Method:* Capture the current motion_timer value from the aggregate settings read first. Set it to the shortest live-acknowledged value ('5', the only one with a recorded ack on this firmware). Start the same 1 Hz multi-port logger as P0-1 plus an art-websocket listener on the existing session, then leave the room. Record: the exact time the panel goes dark (human), whether any push event arrives (specifically go_to_standby, or nothing at all), and the per-port/ICMP trace across the transition and for 10 min after. Then restore the original motion_timer and verify the readback matches the captured original. If the fingerprint matches P0-1's, the observed state is the motion blank and the integration is reporting a lit-or-blanked art TV as powered off.
  - *Requires:* TV in ART MODE, displaying art, art session healthy. A human must physically leave the sensor's field of view for the whole timer period and must not walk past it — this probe cannot be run remotely, and a single motion event invalidates the run. The human also reports the moment the panel visibly blanks.

- **P0** **[MUTATES]** How does the TV leave the observed state, and can the integration trigger or detect that exit without a WoL packet?
  - *Method:* From the state established by P0-1/P0-2, with the multi-port logger still running: (a) have the human trigger motion in front of the sensor and record whether ICMP/8001/8002 change and how fast; (b) if motion does nothing, press a remote key by hand and record the same; (c) only if both fail, send a WoL magic packet and record. Log which stimulus reopens 8001 and after how long. This decides whether the integration can recover by polling alone, needs a wake, or is simply blind. Also settles whether the wake probe's port-8001-only design (coordinator.py:436-443) can ever see this transition.
  - *Requires:* TV in the observed ICMP-up/TCP-closed state. Human must physically stand in front of the motion sensor for step (a) and press a physical remote key for step (b).

- **P1** Does the paired MAC still own this address, and does REST expose networkType so the integration could detect a move to Ethernet at runtime?
  - *Method:* When the TV is reachable, read REST /api/v2/ and record which keys the `device` object actually contains — specifically whether networkType, firmwareVersion and the isSupport blob are present and what networkType reports on WiFi. Record key names and the networkType value only; never record wifiMac, udn, duid, ssid or the serial. This is the cheapest possible mitigation for gap #1 and #2: the entire unreachable-as-OFF rule is documented as WiFi-only, and networkType would let the integration detect at runtime that the assumption no longer holds.
  - *Requires:* TV reachable, any mode. No human action.

- **P1** Does this TV emit get_artmode_status == 'nav', and under exactly which on-screen conditions?
  - *Method:* With the art session healthy, poll get_artmode_status at 1 Hz while a human steps the TV through: fullscreen art -> art menu open -> browsing art categories -> back to fullscreen art -> art->watching toggle -> watching->art toggle. Record the value at each step alongside the human's description of what is on screen, plus every art push event and its sub-event name. Deliverable: the set of distinct values this firmware returns and the screen state each corresponds to, which determines whether 'nav' needs its own TvMode or merely a hold-last-stable rule.
  - *Requires:* TV in ART MODE with the art session connected. A human must operate the physical remote to open and navigate the art menu and to toggle modes, narrating each step so values can be aligned to screen states.

- **P1** **[MUTATES]** Does `change_favorite` acknowledge with sub-event `favorite_changed` or with event == the request name, i.e. does set_favourite time out and kill the art session on every call?
  - *Method:* On a USER-UPLOADED artwork only (never store content), invoke set_favourite once with the art session healthy and capture the raw d2d_service_message frames for 30 s: record the sub-event name, whether request_id is echoed, and whether the call resolves or hits the 20 s deadline and closes the socket. Then invoke it again with the opposite status to restore the original favourite state, and confirm via the same frame capture. If the ack carries event 'change_favorite' with a matching request_id, the dispatcher gap at frame_art.py:913-920 is confirmed and the fix is a one-line expected_sub_event change.
  - *Requires:* TV in ART MODE, art session READY, with at least one user-uploaded artwork present whose favourite state the human is willing to have toggled and restored. Human confirms the original favourite state on screen beforehand.

- **P1** **[MUTATES]** Do `set_brightness` and `set_color_temperature` actually acknowledge on current firmware, given that both of their paired legacy getters are confirmed silent timeouts?
  - *Method:* Read the aggregate settings and capture the original brightness and colour-temperature values. Change brightness by exactly one step, capture the raw response frames (ack shape, request_id echo, latency, or silence to the 20 s deadline), read back via the aggregate to confirm the change landed, then restore the original and confirm the readback matches. Repeat independently for colour temperature. Run each as a separate art generation if the first kills the socket. This is the highest-value gap in the SHIPPED write surface: both are non-probe writes wired to user-facing sliders with no live ack on record.
  - *Requires:* TV in ART MODE, art session READY, human watching the panel to report any visible brightness/tone change (which also cross-checks that the wire value maps to the on-screen effect).

- **P1** Does get_artmode_settings on this firmware return min / max / valid_values per item, and does it advertise items the parser silently drops?
  - *Method:* Send get_artmode_settings as a bounded probe (5 s) and dump the FULL decoded item list verbatim — every key on every item, not just item/value. Compare the advertised item names against ArtSettingKey (models.py:17-24) to find silently-dropped settings (art_settings.py:83-86 discards them today), and compare any advertised ranges against the hardcoded bounds (brightness 0-10, colour temp -5..5, the 7 motion timers, sensitivity 1/2/3). Read-only, one request, no mutation.
  - *Requires:* TV in ART MODE, art session READY. No human action.

- **P1** **[MUTATES]** Does a real (non-identity) slideshow write succeed via the legacy dialect, and what does an ACTIVE slideshow payload look like?
  - *Method:* Read and capture the current slideshow state via the legacy getter (the only dialect that answers here). With the dialect already learned as LEGACY for the current generation — verify this first, since an UNKNOWN dialect routes to the confirmed-dead modern setter — write a short non-zero duration with sequential order, read back, and record the full payload of an ACTIVE slideshow: the exact `value`/`type` types and whether category and sub_category keys appear. Then repeat once for shuffle to learn the shuffle `type` string. Restore the original state (observed live as 'off') and confirm the readback. This settles both the enum mapping and the synthesized duration_minutes=0 defect.
  - *Requires:* TV in ART MODE, art session READY, dialect already reconciled to LEGACY. Human should be present to confirm the TV visibly starts and stops rotating artwork.

- **P1** Does REST GET /api/v2/applications/<id> return a `visible` flag on this model, and what does it return for an app that is not installed?
  - *Method:* While the TV is WATCHING with a known catalog app in the foreground, call the per-app status endpoint for each of the 7 curated app ids and dump the full response body shape (key names only, plus the boolean values of running/visible). Then repeat with a deliberately bogus app id to learn the not-installed response shape and whether it raises or returns a body. This is the only shipped READ path with zero probe evidence, and it fires 7 times on every WATCHING heartbeat.
  - *Requires:* TV WATCHING with one known catalog app in the foreground (human launches it and states which), then repeated on live TV or an HDMI input to confirm the 'no app visible' case that currently degrades silently to source='TV'.

- **P1** What does `api_version` return on this firmware, and does it answer at all — i.e. which upload branch is live code and which is dead?
  - *Method:* Send `api_version` as a BOUNDED PROBE (5 s), not the 20 s non-probe deadline the upload path currently uses at frame_art.py:654. Record the returned version string or the silence. If it is silent, that alone is a shipped defect: every upload would burn 20 s and close the art socket before sending a byte. If it answers, the value decides whether the 0.97 websocket-binary branch (frame_art.py:745-792) is dead code or the live path. Follow up with the legacy alias `get_api_version` if the modern name is silent.
  - *Requires:* TV in ART MODE, art session READY. No human action.

- **P1** **[MUTATES]** Does the post-rewrite native-async D2D path still upload, thumbnail, select and delete correctly on this TV?
  - *Method:* All existing upload/select/delete evidence predates the v0.6.7 transport rewrite. Upload one small test image via the current async path, capture the D2D handshake (ready_to_use conn_info shape, secured flag) and the completion ack (image_added and whether it carries a request id), fetch its thumbnail via get_thumbnail_list, select it, confirm on screen, then delete it and capture the delete response to verify the echo-equality check in frame_art.py:461-477 actually matches this firmware's reply. Restore the previously displayed artwork. Record no content identifiers.
  - *Requires:* TV in ART MODE, art session READY. Human confirms on screen that the uploaded image appears when selected and is gone after deletion, and that the original artwork is restored.

- **P2** Does a 'silent' command ever answer late, past the 5 s probe deadline?
  - *Method:* Send one of the confirmed-silent getters (get_brightness) as a probe, then hold the socket open and keep capturing frames for at least 120 s, logging any late correlated response and its request_id. The hotfix design's safety property — that a late response cannot resolve a newer request — is designed-for, never measured. A late correlated answer would also mean these commands are slow rather than unsupported.
  - *Requires:* TV in ART MODE, art session READY and otherwise idle. No human action.

- **P2** **[MUTATES]** Which numeric error_code does this firmware return for an unsupported vs a bad-parameter vs a busy request?
  - *Method:* Send one request with a deliberately invalid parameter value on a command known to be supported here (e.g. set_slideshow_status with an out-of-range duration) and record the error_code. The dialect logic currently switches on the mere EXISTENCE of a correlated ResponseError and caches the result for the whole art generation, so a transient busy code or a bad-parameter code would pin the wrong dialect. Only a NOT_SUPPORTED_API code should mean unsupported. Restore any value touched.
  - *Requires:* TV in ART MODE, art session READY.

- **P2** Does the art websocket get dropped by the TV when idle, invalidating the 300 s reconcile cadence?
  - *Method:* With the art session READY and no user activity, send nothing for 10 minutes while logging every received frame and the socket state, then send get_artmode_status and record whether it answers or the socket is found dead. A third-party client claims Frame firmware drops sockets idle for roughly a minute; the integration's only periodic traffic is at 300 s. A half-closed socket would stop push events with no error while art_ready still reports READY.
  - *Requires:* TV in ART MODE, art session READY, completely idle — no remote presses, no phone app connecting.

- **P2** Does this TV expose matte and photo-filter catalogues, so the two free-text services can be validated?
  - *Method:* Send get_matte_list and get_photo_filter_list as bounded probes (5 s each) and record whether they answer, plus the response key names (this firmware may use matte_type_list or matte_list). Both are read-only, both are natural probe=True candidates, and both fix a real defect: services that today accept unvalidatable free-text ids with upstream-derived examples shown to the user. If they answer, follow with a single change_matte round-trip on a user-uploaded artwork using a discovered id, capturing and restoring the original matte.
  - *Requires:* TV in ART MODE, art session READY. Human present only for the optional change_matte round-trip, to confirm the visible matte change and its restoration.

- **P2** Does get_device_info answer on this firmware, and does it advertise the support flags the integration currently infers indirectly?
  - *Method:* Send get_device_info as a bounded probe (5 s) and record the key names and the support_* flag values (note they are documented as strings 'TRUE'/'FALSE', not booleans). Explicitly exclude any device identifier from the capture. This is a free read already present in the pinned library and never sent; it would replace the current 'infer capability from which keys appeared in get_artmode_settings' heuristic.
  - *Requires:* TV in ART MODE, art session READY. No human action.

- **P2** Is there a second local control plane on this 2022 set — does TCP 1516 (or 1515) accept a connection?
  - *Method:* A single connect-only TCP probe to 1516 and 1515, no handshake, no token, no createAccessToken call (that would raise a pairing UI on the TV). Record open/closed only. This is documented on 2025 firmware as a JSON-RPC service exposing an art-mode getter/setter and a real installed-app list — both independent of the art websocket and the flaky remote grant. If the port is closed on this set, the whole avenue closes for one packet's cost.
  - *Requires:* TV reachable and on, any mode. No human action.

- **P2** Does this TV advertise the SSDP device type the manifest matches on?
  - *Method:* Passive SSDP listen (or a single M-SEARCH) recording whether the TV advertises the manufacturer and deviceType the manifest matcher expects. This decides whether implementing async_step_ssdp would actually repair a changed IP address, or whether the matchers are simply wrong in addition to being unhandled.
  - *Requires:* TV reachable and on. No human action.


## What this survey did not cover

From the completeness critic. These are acknowledged holes, not findings —
listing them is what keeps the matrix from reading as complete when it is not.

- **External inputs / HDMI / CEC — entire area absent from matrix, gaps and probes** — media_player advertises SELECT_SOURCE unconditionally (media_player.py:141-155) but source_list is only the 7-app catalog (media_player.py:162-166, const.py:94-102). There is no HDMI1-4, no live-TV input, no KEY_SOURCE/KEY_HDMI path anywhere in custom_components/ (grep confirms), and `source` collapses every non-app foreground into the literal string "TV" (media_player.py:170-175). A user watching HDMI2 sees "TV"; a user wanting to switch to HDMI2 cannot. Not one row, gap or probe mentions inputs. This is the largest advertised HA feature with zero coverage.

- **Firmware version is never read, stored, or surfaced — yet the whole dialect model is per-firmware** — The hotfix design states the finding explicitly (docs/superpowers/specs/2026-07-22-optional-art-probe-timeout-hotfix-design.md, 'dialect support is per command and firmware, not per model year'). But validate_and_pair captures only wifiMac and modelName (config_flow.py:159-163); DeviceInfo sets manufacturer/model/name with no sw_version, hw_version or configuration_url (entity.py:60-67); diagnostics_snapshot reports no version at all (coordinator.py:96-124). Consequence: every 'CONFIRMED on this model' claim is silently a claim about an unknown firmware build, a firmware update that changes dialects is undetectable and unreportable, and no bug report can be version-anchored. Probe P1-4 asks only whether firmwareVersion is PRESENT in the REST payload — it never proposes recording it, surfacing it as sw_version, or versioning the evidence base against it.

- **The MAC identity is wifiMac — the Ethernet case is a hole in both the code and the plan** — config_flow.py:160 sets CONF_MAC = format_mac(device.get("wifiMac", "")), and that one value is simultaneously the config-entry unique id, the DeviceInfo identifier and connection, every entity's unique_id prefix, and the Wake-on-LAN magic-packet target (device.py:632-635). If the set is ever wired, WoL targets the wrong NIC and P0-1's ARP identity comparison is against a MAC that is not on the wire. format_mac("") on a payload missing the key yields an empty unique id and setup still succeeds. The operator's own memory carries the caveat ('if TV is ever wired via Ethernet, re-test') and it was never turned into a matrix row, a gap, or a probe.

- **set_artmode_status — the headline user-facing write — has no probe anywhere in the plan** — The matrix correctly marks the WRITE ASSUMED (switch.py:33-69; frame_art.py:381-386; device.py async_set_artmode). Grep confirms no live record in docs/, tests/ or CHANGELOG.md. It is the art-mode switch entity, the set_art_mode service, and the art button on the shipped examples/remote-card.yaml dashboard. Probe P1-5 has a HUMAN toggle art with the physical remote, so it never exercises the integration's write. No probe in the plan sends set_artmode_status. If it is silently ignored it is a non-probe write on the 20 s deadline that retires the art generation on every click. This is the single largest promise/probe gap.

- **The pairing CONFIRMED is over-claimed, and the shipped pairing path has never been run live** — The cited controlled test (docs/superpowers/specs/2026-07-13-remote-control-pairing-design.md:19-30) establishes that a remote-issued token was subsequently accepted by the art channel — on a TV that already had the art channel whitelisted under the same fixed client name (const.py CLIENT_NAME) from months of art-only pairings. It does not establish that ONE Allow tap grants both channels on a set holding no art grant, which is the claim, and which the same evidence base contradicts ('the TV authorizes the ART channel and the REMOTE channel SEPARATELY, per device'). Worse: the v0.8.0 deploy memory records that both config entries were deleted at the rename and the final re-pair is still pending — so the v0.9.1 config flow has zero live executions. Downgrade to ASSUMED and add a probe that clears the client-name grants on the TV first.

- **App launch (ed.apps.launch) and play_media deep-linking have no probe and no matrix row** — select_source and play_media both route to async_launch_app (device.py:650-656). The matrix itself notes no live record of ed.apps.launch succeeding here and that REST launch is capricious (sometimes 401) — yet probe P1-10 only READS per-app status. Nothing tests whether a launch actually reaches the TV. media_player.play_media with extra.meta_tag deep-link content (media_player.py:336-361) is a documented README feature with no matrix row at all, and it accepts a raw Tizen app id that bypasses the catalog entirely.

- **Wake-on-LAN broadcast address: an identified risk on the integration's most visible promise, with no probe** — device.py:632-635 hardcodes send_magic_packet(mac, ip_address="255.255.255.255"). The operator's own notes record needing the subnet broadcast in at least one environment. turn_on is the most user-visible service in the integration and its failure is silent (only a log warning after 30 attempts). A two-packet probe from the actual HA host — 255.255.255.255, then the subnet broadcast — settles it, and no probe in the plan does it. The wake probe's port-8001-only design (coordinator.py:436-443) is separately blind in exactly the new ICMP-up/ports-closed state, which the plan notes but does not turn into a fix-validating probe.

- **GetMute/SetMute: sold to users as CONFIRMED, and it can suppress the proven volume read** — README.md:29 promises 'absolute volume + real mute state (via the TV's UPnP service)'; the live notes record only GetVolume/SetVolume. The coupling is worse than the matrix states: async_get_volume issues GetVolume AND GetMute inside one try block (device.py:239-253), so if GetMute is the unsupported action the whole call returns (None, None) — volume disappears too — and self._upnp_device = None forces a full device-description re-fetch next poll. An unproven action can suppress a proven one. No probe covers GetMute/SetMute at all.

- **Channel/broadcast semantics: transport controls are silently bound to channel keys** — async_media_next_track sends KEY_CHUP and async_media_previous_track sends KEY_CHDOWN (media_player.py:206-211). The matrix's 'Transport controls' row treats next/previous as track keys with no live evidence and never notes the substitution — so inside Netflix/YouTube the HA 'next track' button sends a channel key. No media_title, media_content_type, media_duration or media_position is exposed anywhere, so media_player publishes PLAYING with no media metadata. No probe asks whether KEY_CHUP/KEY_CHDOWN do anything at all on this set.

- **The UPnP surface at :9197 was never enumerated — one free read would list every service the TV offers** — device.py:50-51 hardcodes _DMR_URL = 'http://{host}:9197/dmr' and _RENDERING_CONTROL, and the code fetches that device description on every UPnP recovery (device.py:232-238). Nothing in the plan asks what that description actually advertises: which RenderingControl actions exist beyond GetVolume/GetMute/SetVolume/SetMute, whether AVTransport or ConnectionManager are present, whether any of it answers while in art mode. This is a zero-risk, zero-mutation read the integration already performs, and it is the only route to picture/sound-mode-adjacent capability on the local network. No probe covers it.

- **Screen rotation / portrait mode — a library capability the integration never touches** — get_current_rotation exists in the pinned library (art/art.py:794) and change_matte accepts portrait_matte_id (art/art.py:829-843). The integration's async_change_matte passes only the landscape matte_id (device.py:571-574) and nothing anywhere reads rotation. The Frame's auto-rotating mount is a real product for this model year. No matrix row, no gap, no probe — and it silently affects the matte service, the upload matte default, and the image entity's aspect.

- **P0-1's identity check cannot answer the question it exists to answer** — Reading the ARP/neighbour entry once proves nothing: the Linux neighbour table retains a STALE entry for a departed host for minutes, and an absent/FAILED entry is equally uninformative once the address has moved. The probe must record the neighbour STATE field (only REACHABLE is evidence) and — the part that actually matters for gap #2 — scan the WHOLE neighbour table for the paired MAC, because 'did DHCP move the TV to a different address' is unanswerable by only ever inspecting one address. It also never distinguishes ICMP answered by the TV from ICMP answered on its behalf by the AP/router.

- **P0-2 can produce no interpretable negative, and the cheapest decisive experiment is missing entirely** — It writes motion_timer='5' to induce the blank. If the panel never blanks, the result is uninterpretable: the plan cannot separate 'motion_timer is not the sleep-after timer' (its own gap #14) from 'the human moved' from 'the timer is longer than the observation window'. Absent from the plan is the zero-risk, zero-mutation experiment that settles gap #14 outright: have the human open the TV's own Art settings menu and report WHICH on-screen control now shows the value the integration wrote, what the other controls are called, and what values each offers. That one observation settles motion_timer-vs-Sleep-After, reveals whether a separate Night Mode control exists, and reveals whether the TV offers timer values outside the hardcoded seven (art_settings.py:14) — none of which any wire probe can answer.

- **P1-6 (set_favourite) has no authoritative readback — it violates the repo's own mutation-probe doctrine** — AGENTS.md requires capturing the original, making the smallest reversible change, reading it back AUTHORITATIVELY, and restoring and verifying the exact original even if the probe fails. Favourite state is exposed nowhere in the integration and get_content_list is never called (art/art.py:345 exists, unused), so the probe as written can only observe the ack frame — it can never confirm the flag changed or that the restore landed. The fix is already in the plan's own inventory: read the artwork's favourite field via get_content_list before, after, and after restore. Compounding it: the hypothesis under test is that the first call kills the socket, so the 'invoke again to restore' step runs on a fresh generation with unknown dialect state — the restore is itself an untested half of the experiment.

- **P1-7 (brightness / colour temperature) cannot isolate the failure it is hunting** — set_brightness and set_color_temperature are non-probe writes (frame_art.py:412-419, no probe=True), so a silent TV burns the 20 s deadline and closes the socket — after which the probe's own 'read back via the aggregate to confirm the change landed' step cannot run on that generation and the 'restore the original' step runs blind. Since the entire question is whether the setter is silent, the outcome must be decided from a raw frame capture on the socket, not from the integration's success/failure. As written, the most likely outcome leaves the panel at a changed brightness with no verified restore.

- **P1-9 (slideshow) restores the wrong thing and skips the measurement that settles gap #4** — It restores slideshow state to 'off' but says nothing about restoring the DISPLAYED artwork, which a real rotation will have changed — and current_art is precisely the value that change_matte / set_photo_filter / set_favourite silently default to (media_player.py:363-369). It also never sends set_auto_rotation_status under a bounded probe deadline to learn whether the modern setter answers with a ResponseError rather than silence. That distinction is what the dialect cache actually switches on (device.py:591-612), so without it gap #4 stays open even if the probe succeeds.

- **The image entity's COMMON case (store-art DRM refusal) is not probed on the post-rewrite transport** — P1-12 round-trips a user upload only. README.md:41-43 promises store artworks show a placeholder, and the matrix says store content is the common case on this TV. But image.py:56-69 serves the PREVIOUS artwork's bytes on any failure that is not a clean None, so the behavioural difference between 'clean DRM refusal' and 'error' is exactly what decides whether users see a placeholder or a stale artwork. Add a store-content thumbnail fetch to P1-12 and record whether the D2D socket closes empty or raises.

- **upload_art's matte parameter is written on every upload and never validated or read back** — services.yaml:41-46 defaults matte to 'none' with an example value shown to the user, and async_upload_art passes it straight through (device.py:545-551). P1-12 uploads but never varies or verifies the matte, and P2-16 defers matte entirely to an optional separate round-trip. So the one matte value the integration writes by default on every single upload is never checked against the TV's own matte list, on a firmware where an unsupported art command is answered with silence.

- **The brightness-sensor CONFIRMED is an ack SHAPE, not either written value** — docs/superpowers/specs/2026-07-22-local-art-settings-phase1-design.md:195-199 establishes one deterministic acknowledgement shape common to three setters (matching request_id, event equal to the request command, requested value echoed) and asserts generically that 'every original setting was restored'. It records no per-command value. Nothing in the repo pins which brightness-sensor value was written. Treat the shape as CONFIRMED and every individual value — for the sensor switch, the motion timer, and the sensitivity select alike — as ASSUMED.

- **All art-push evidence predates the v0.6.7 transport rewrite, exactly like the upload/thumbnail evidence the matrix does caveat** — The push confirmation rests on samsungtvws 3.0.5 SamsungTVArt.start_listening, including the operator's finding that polling and listening CANNOT share one instance so two sockets were needed. The v0.6.7 rewrite replaced that with a single native-async FrameArt doing both on one socket (frame_art.py). No live record exists for the shipped arrangement. The matrix applies the 'predates the rewrite' caveat to upload/select/delete and to thumbnails but not to push events, where it applies identically.

- **A cheap remote-channel readback oracle exists and neither the matrix nor any probe uses it** — The matrix asserts flatly that 'no readback exists for any' remote write. That is wrong in one useful case: UPnP GetVolume (device.py:239-253) is a genuine independent readback for KEY_VOLUP/KEY_VOLDOWN. That makes a cheap, fully reversible end-to-end remote-channel liveness probe available — send KEY_VOLUP, read GetVolume, restore the original level via SetVolume — and it is the only proposed way to prove that remote-channel frames reach the TV at all, given send_commands awaits nothing. No probe in the plan does it. remote.send_command with hold_secs on any key other than KEY_POWER (device.py:648-649, a documented README feature) is unprobed for the same reason.

- **Long-run / duty-cycle behaviour: every probe is a short capture, but every unexplained failure is a long-run phenomenon** — Steady-state load is up to 9 network round-trips per heartbeat forever: 1 REST device-info, plus 2 UPnP SOAP calls whenever PowerState=='on' (including throughout art mode, coordinator.py:222-224), plus 7 concurrent REST app-status calls whenever WATCHING (coordinator.py:354-371), at a 10 s default heartbeat (const.py:29). The one failure the operator recorded as unfixable client-side is the TV's art app wedging after heavy testing, and the new ICMP-up/ports-closed observation is likewise a long-run state. No probe runs the shipped integration at its shipped cadence for hours, and none varies heartbeat_seconds to test whether poll rate is causal. P2-15 is the only long probe and deliberately sends nothing — the opposite condition.

- **Reauth and reconfigure are user-visible recovery promises with no probe, in a system whose own evidence says grants are fragile** — config_flow.py implements reauth, reauth_confirm and reconfigure; the recorded evidence base says tokens are flaky across boots (accepted at one boot, rejected the next), that a hard power cycle can wipe the grant, and that an invalid token gets an instant ms.channel.timeOut with no prompt. None of those recovery paths has been exercised on the shipped release. There is no probe of the form 'invalidate the grant, then confirm HA's reauth flow actually re-pairs and the prompt renders' — despite silent reauth prompts being documented as expected behaviour here.

- **SmartThings is neither used nor explicitly rejected, so the matrix cannot claim completeness** — The README sells 'no SmartThings or other cloud service is required' as a feature and the local-first choice is defensible. But SmartThings is the only documented route to input source and picture/sound mode on Samsung TVs, and the operator's own model-year matrix names it as the OFF oracle for 2020-21 sets. Nothing in the plan records it as an examined-and-rejected alternative with a reason, so a reader cannot distinguish 'considered and out of scope' from 'never considered' — which matters most for gap #1, where the local reachability oracle is the thing under suspicion.


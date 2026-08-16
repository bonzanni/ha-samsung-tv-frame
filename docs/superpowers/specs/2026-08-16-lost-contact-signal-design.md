# Lost-contact signal design

**Date:** 2026-08-16 · **Status:** reviewed (Sol + Terra, round 1: both SHIP WITH
FIXES; both findings folded in below) · **Target release:** v0.10.0
· **Core:** HA 2026.8.1, Python 3.14 · **Device:** QE65LS03B, `api_version` 4.3.4.0

## Objective

Make *"Home Assistant cannot reach the TV"* observable and automatable, as a
signal distinct from *"the TV is off"* — without redefining what any existing
entity means.

## Evidence

**The oracle.** `reachable` means one HTTP GET to TCP 8001 `/api/v2/` returned a
truthy `device` object within 8 s (`coordinator.py:143-145` → `device.py:224-230`
→ `rest.py`). `except Exception` collapses RST, timeout, HTTP error and non-JSON
into one indistinguishable `None`. ICMP, 8002, 9197 and ARP are consulted
nowhere in the integration (verified by grep).

**Measured live during this session (2026-08-16).** While probing, the TV left
the network on its own:

| signal | during the outage |
|---|---|
| ICMP | 100% loss (3/3) |
| 8001 / 8002 / 9197 | all connect-timeout |
| `sensor.<tv>_tv_mode` | `off` — **entity still available**, positively asserting it |
| `binary_sensor.<tv>_art_mode` | `off` — coordinator forces `False` when off |
| art-derived entities | `unavailable` (generation freshness gate), ~2 min earlier |

Wake-on-LAN recovered it: REST answered `PowerState: on` 29.5 s after the magic
packet, all three ports were open by 39 s, and Home Assistant republished
`art_mode` ~85 s after the TV started answering again. Nothing anywhere in that
sequence distinguished "gone" from "off".

**Why probing harder cannot fix it.** Art-sleep and a real power-off traverse an
identical network sequence (capability map, 2026-08-16): a brief standby phase
with the NIC up and 8001 still answering `PowerState: standby`, then a full
network exit where nothing answers at all. In that second phase there is
nothing left to probe.

## What the gap actually is

Two independent questions collapse into one published answer:

1. **Contact** — did the last poll reach the TV at all?
2. **Mode** — what is the TV doing?

`derive_tv_mode` maps `reachable=False → OFF` (`models.py:58-59`), and question 1
is published nowhere: `reachable` lives only inside `FrameData` and the zero-I/O
diagnostics snapshot (`coordinator.py:97-125`). Entity availability tracks only
`last_update_success`, which an unreachable TV does **not** clear, because the
poll succeeds and reports OFF (`entity.py` has no `available` override).

Consequences: no "TV unreachable" alerting is expressible; an AP outage, a DHCP
move, a Tizen crash and art-sleep all present as a confident `off`; and no
automation can be written on *lost contact* at all.

## Chosen design — add the missing signal, do not redefine the existing ones

### 1. `binary_sensor.<tv>_connection`

- `device_class: CONNECTIVITY` (on = connected), `entity_category: DIAGNOSTIC`,
  enabled by default. Both verified present in the installed HA 2026.8.1.
- `is_on` returns `coordinator.data.reachable` — "the last poll got a `device`
  object from port 8001", and nothing more.

#### `reachable` must become a poll-owned fact (review finding, Terra S1)

As shipped, `reachable` is **not** poll-owned: the art push path overwrites it
with a hardcoded `True` (`coordinator.py:526`), so an unsolicited art event
would flip the sensor to "connected" without any REST heartbeat having answered.
Fix: drop `reachable=True` from that `replace(...)` call and let the field carry
the last polled value. `derive_tv_mode(True, ...)` on that path keeps its literal
`True` argument — it is a separate statement ("the TV just talked to us"), and
the mode derivation is unchanged. `FrameData.reachable` has exactly one consumer
today (the diagnostics snapshot, `coordinator.py:105`), so nothing else moves.

The alternative — defining the sensor as *"in contact by any channel"*, which an
art push would legitimately satisfy — is **rejected**, for two reasons:

1. **It would flap.** The art session is not torn down when a poll reports
   unreachable (`art_session.py:126-133` records and returns), so a TV whose
   REST port has wedged while its art socket lives would push an event every
   slideshow rotation — 5 minutes apart on this device — flipping the sensor on,
   then off again at the next failing poll, and firing the very triggers this
   design adds, indefinitely.
2. **It would hide the thing worth seeing.** The sensor exists to expose the
   state of the oracle that drives `unreachable → OFF`. Smoothing that oracle
   with evidence from a different channel defeats the purpose.
- **No debounce.** `OFF_DEBOUNCE_COUNT` exists to stabilise *mode*; applying it
  here would hide exactly the short outages this entity exists to reveal.
  Automations that want persistence use `for:`, which every trigger already
  supports. A one-poll disagreement with `tv_mode` (contact lost, mode not yet
  OFF) is accurate, not inconsistent.
- **Availability.** It stays available while the coordinator is succeeding —
  and an unreachable TV still produces a *successful* poll, which is the whole
  point. If the poll itself fails (`POLL_DEADLINE`), `CoordinatorEntity` makes
  it unavailable, which is the correct statement: the integration, not the TV,
  is what failed.
- **No attributes.** A `last_contact` timestamp would rewrite entity state into
  the recorder ~8 640×/day at the default 10 s heartbeat, and buys no automation
  capability that `for:` does not already provide. `reachable` is already in the
  diagnostics snapshot for support dumps.

### 2. Device triggers `lost_contact` / `regained_contact`

`device_trigger.py` today maps trigger type → `to` state against the single
`tv_mode` entity, found by a `_tv_mode` unique-id suffix. Generalise the table to
(entity suffix, from-state, to-state) triples so triggers can attach to the
connection sensor as well. `for:` support is already generic
(`async_get_trigger_capabilities`).

#### The two new triggers are deliberately asymmetric (review finding, Sol S2)

A `to`-only state trigger also fires on `unavailable → <state>`. Sol's scenario:
a poll that blows `POLL_DEADLINE` makes every entity unavailable, the next
successful poll restores `on`, and a `to: "on"` trigger announces
`regained_contact` although contact was never lost. Sol's fix was to give *both*
new triggers explicit opposite `from` states. Only half of that is right:

| sequence | meaning | `to`-only | with `from` |
|---|---|---|---|
| `on → off` | contact lost | fires ✓ | fires ✓ |
| `on → unavailable → on` | coordinator hiccup, TV fine | **false `regained`** | silent ✓ |
| `on → unavailable → off` | coordinator failed, then TV really gone | fires ✓ | **misses a real loss** |
| `off → on` | contact restored | fires ✓ | fires ✓ |

So `regained_contact` takes `from: "off"`, and `lost_contact` stays `to: "off"`
with no `from` — which also matches the existing `turned_off` trigger's
convention, so the three shipped triggers keep behaving exactly as they do
today. A missed "recovered" notification is a smaller harm than a fabricated
one; a missed "lost" notification is the larger harm, so that direction stays
permissive.

### 3. Nothing else changes

This is the deliberate half of the design.

| Not changed | Why |
|---|---|
| `derive_tv_mode`'s `unreachable → OFF` | Every automation keyed on `off` depends on it, and for the common case the inference is *right*: the TV really is off or asleep. Publishing `unknown` instead would trade a rare wrong answer for a permanently useless one. |
| `media_player` / `remote` availability | Making them unavailable removes `turn_on` exactly when it is needed — WoL is the documented recovery from art-sleep *and* from power-off. HA core's own `samsungtv` media_player does the same thing: `MediaPlayerState.OFF` with no `available` override (`media_player.py:141,157`). |
| `binary_sensor.<tv>_art_mode` forced `False` when off | See deferred work below. |
| The 2-poll OFF debounce | Untouched; the new sensor is the undebounced view. |

### Rejected alternatives

- **A fourth `tv_mode` option (`unreachable`)** — breaking for every existing
  automation and device trigger, for information a separate entity carries
  without breaking anything.
- **`reachable` as an attribute on `tv_mode`** — not reachable from UI device
  triggers, and attribute-only signals are second-class in automations.
- **Marking every entity unavailable on lost contact** — rejected above for
  `media_player`/`remote`; the art-derived entities already gate on generation
  freshness, which is a strictly better signal than reachability.
- **Adding ICMP / 8002 / 9197 to the reachability oracle** — rejected *on
  measurement*: in the phase-2 outage nothing answers, and in the standby phase
  8001 answers already, so extra probes cost round-trips and change no verdict.
  Worth reconsidering only for the unmeasured Tizen-crash case.
- **A `repairs` issue after N minutes of no contact** — repairs are for
  user-actionable misconfiguration; a TV that is off is not a repair.

### What the entity is documented to mean

> **Connected** — the TV answered the integration's REST heartbeat on port 8001.
> It does not mean the panel is lit. **Disconnected** does not distinguish a
> powered-off TV from a sleeping one or from a network fault.

That sentence goes in `strings.json` and the README, because an entity that
overclaims is how this integration got into this position in the first place.

## Deferred: telling art-sleep from a real power-off

Not designed here, because the measurement that would decide it has not been
made. Two candidate discriminators, both **unproven**:

1. **Standby-window duration.** Project memory records ~3 min of NIC-up standby
   after a 3 s power hold; the art-sleep standby phase measured under 30 s.
   Confirming needs a ~2 s sampler across *both* transitions — 30 s sampling
   already produced one wrong conclusion this month.
2. **Push-event pattern.** A power-off from art emits `art_mode_changed(off)`
   and a measured ~7 s false `watching` blip; the one observed art-sleep went
   `art_mode → off` directly. One sample each side.

Until one of them is measured, the connection sensor deliberately says only
"no contact", and `binary_sensor.art_mode` keeps its current behaviour: changing
it would be a breaking change made to resolve an ambiguity the connection sensor
already exposes.

## Test plan (TDD, failing first)

1. `is_on` follows `FrameData.reachable` on the poll where it changes, with no
   debounce (contact lost on poll 1, while `tv_mode` still holds last-stable).
2. It stays `available` while the TV is unreachable and the poll succeeds.
3. It goes `unavailable` when the coordinator poll itself fails.
4. **An art push event does not flip it to connected** — the regression for
   Terra's S1, and the one test that fails against today's code for a reason
   nothing else covers.
5. Device triggers `lost_contact` / `regained_contact` fire on the transitions
   and honour `for:`; `regained_contact` does **not** fire on
   `unavailable → on`, while `lost_contact` does fire on `unavailable → off`.
6. Pinning: `tv_mode`, `media_player` and `binary_sensor.art_mode` behave
   exactly as before across an unreachable poll — this change is additive.

## Rollout

New entity, enabled by default, diagnostic category (off the main card). No
config-entry migration and no unique-id changes. Updates: `binary_sensor.py`,
`device_trigger.py`, `strings.json` + `translations/en.json`, README, and the
`quality_scale.yaml` entity rows.

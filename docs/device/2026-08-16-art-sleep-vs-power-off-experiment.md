# Can art-sleep be told apart from a real power-off? — Experiment report

**Date:** 2026-08-16/17 · **Device:** QE65LS03B (2022, `22_PONTUSM_FTV`), `api_version` 4.3.4.0
· **Integration:** v0.9.1 installed · **Core:** HA 2026.8.1, Python 3.14 · Issue #8

Sanitized per `AGENTS.md`: no host, MAC, token or artwork identifier appears here.

## Answer

**No — not by duration, and not by any push event the integration receives.**

Both candidate discriminators were measured live at 2 s resolution, and both
fail. Art-sleep and a real power-off produce the same push event, the same port
signature, and standby windows that agreed **to the decisecond** in the run where
both were captured on one clock. The `binary_sensor.<tv>_connection` sensor
shipped in v0.10.0 stays as documented: it says *no contact*, and it deliberately
does not say why, because on this device there is nothing that says why.

## Method

One instrument, two runs, both from inside the Home Assistant container with the
`samsung_tv_frame` config entry disabled so the experiment owned the art channel:

- a **2 s sampler** recording, per tick: ICMP; connect-only TCP to 8002 and 9197
  (no bytes sent, so no Allow prompt); and an HTTP GET to 8001 `/api/v2/` —
  the integration's own reachability oracle — parsed for `device.PowerState`;
- an **art-channel listener** built on the integration's own `FrameArt`, so the
  transport under measurement is the shipped one, logging every push event onto
  the same clock;
- one JSONL trace per run, durations taken from `time.monotonic()` so a wall-clock
  step cannot move them.

Every probe is bounded end-to-end below the 2 s tick, and a lost slot is recorded
explicitly rather than silently skipped. **Across 3,554 ticks in the two runs
(2,700 + 854, 90 min + 28 min), zero slots were lost** and the slowest sample
cycle was 1,205 ms against a 2,000 ms budget. Sampling at 30 s is what produced
the earlier wrong conclusion this experiment replaces; the instrument was written
so that failure could not recur silently.

The instrument was reviewed adversarially before use (Sol + Terra, four rounds:
DO NOT SHIP ×3, then SHIP / one S1). Seven findings were applied, each verified by
reproduction — including two that would have corrupted this measurement: probe
overruns silently skipping sample slots, and lag recovery losing one more slot
than it reported.

## Result 1 — standby-window duration: **falsified**

The premise was that a real power-off holds a ~3 minute NIC-up standby window
(project memory, 2026-07-07) while art-sleep's is under 30 s. Measured:

| | run 1 power-off | run 1 art-sleep | run 2 power-off | run 2 art-sleep |
|---|---|---|---|---|
| `standby` → last 8001 answer | 16.0 s | 14.0 s | **14.0 s** | **14.0 s** |
| `standby` → full network exit | 19.2 s | 17.2 s | **17.2 s** | **17.2 s** |
| 9197 refused while 8001 open | all 9 ticks | all 8 ticks | all 8 ticks | all 8 ticks |

In run 2 — both halves in one continuous trace, one process, one clock — the two
transitions are **identical to the decisecond**. In run 1 they differ by 2.0 s,
which is exactly one sample.

**The ~3 minute figure is wrong by an order of magnitude.** It was recorded in a
2026-07-07 session with coarser tooling and has been carried forward in project
memory, the capability map and the lost-contact design ever since. The real
standby window on this device is ~17 s.

That kills the discriminator twice over. Even if a 2 s difference were real, the
integration polls at 10 s: it can only see this window at ±10 s, and the window
itself is under two poll intervals wide.

### Run 1's art-sleep half identifies itself

Run 1's second transition began **3602.0 s — 60 min 2 s — after the Wake-on-LAN
wake**, against a `motion_timer` that was read back as `60` at the start of run 2.
A 60-minute timer firing 60:02 after the art session started is not a coincidence,
and it is what identifies that transition as art-sleep rather than anything else.

Note what that also says: the countdown ran from the wake, **not** from the last
motion — the operator was in front of the TV roughly 36 minutes before the panel
blanked, and the timer did not reset.

## Result 2 — push-event pattern: **both emit `go_to_standby`**

With the art socket live across both transitions in run 2:

| transition | push events, in order |
|---|---|
| **art-sleep** (motion timer, 5 min) | `go_to_standby` — **alone** |
| **power-off** (3 s hold, from watching) | `art_mode_changed status=off`, then `go_to_standby` 5.4 s later |

`go_to_standby` arrived **1.1 s before** `PowerState` flipped to `standby` in the
art-sleep case and **1.6 s before** it in the power-off case. The coordinator
already consumes this event (`coordinator.py:485`) and already treats it as
*"never a state by itself (the destination is ambiguous)"*. **That comment is now
measured, not assumed: the destination genuinely is ambiguous.**

Two further observations, both negative results that matter:

- **The TV never reports leaving art mode when the panel sleeps.** No
  `art_mode_changed` accompanies art-sleep at all. From the art channel's point of
  view the TV is still in art mode while the panel is dark — so the art socket
  cannot be used to detect the blank either.
- The `art_mode_changed status=off` in the power-off row is **attributable to the
  operator**, who short-pressed out of art mode before holding power. It is not
  evidence that a shutdown emits it.

### The one sub-case, and the indirect evidence against it

The surviving candidate was: if a 3 s hold issued **from art mode** emits
`art_mode_changed(off)` immediately before `go_to_standby` — as project memory's
2026-07-07 note claims, via the ~7 s false `watching` blip recorded there — then
*`art_mode_changed(off)` shortly before `go_to_standby` means power-off, and
`go_to_standby` alone means art-sleep.*

**Indirect evidence says no.** A power-off was performed at 23:08 UTC after the
sampler had stopped and the config entry had been re-enabled, so the integration
itself was the observer. Its published states, from the recorder:

| time (UTC) | `tv_mode` | |
|---|---|---|
| 23:08:11.1 | `watching` | operator short-pressed out of art |
| 23:08:14.5 | `art_mode` | back into art mode — pushes were being reflected promptly |
| 23:08:18.4 | `off` | the 3 s hold |

The TV was in **art mode** at the moment of the hold, and the integration went
`art_mode → off` **in one transition, with no `watching` in between** — no trace
of the ~7 s false blip. Had `art_mode_changed(off)` arrived meaningfully before
the standby, the derivation (`art off` + `power on` ⇒ WATCHING) would have
published it, exactly as it did at 23:08:11.

This is **derived-state evidence, not a raw push capture**, so it is corroborating
rather than conclusive: a very short gap between an `art_mode_changed(off)` and
the standby could be masked by `standby_wins`. Capturing it raw needs one more
5-minute cycle — entry disabled, listener up, and a hold from art mode with
nothing pressed first. Until then the candidate is **not claimed**, but it now has
evidence against it rather than merely lacking evidence for it.

Even if it did hold, it would be fragile: silent for a TV powered off from
watching (indistinguishable from art-sleep by construction), dependent on a
correlation window, and requiring the art socket to be alive at shutdown — which,
as below, this device does not guarantee.

## Incidental findings

- **UPnP 9197 flipping to `refused` leads `PowerState: standby`** by up to 2 s
  (run 2 power-off: 9197 refused at t=98.0, standby at t=100.0), or is
  simultaneous (art-sleep). It is the earliest network-visible signal of either
  transition — and it is identical for both, so it discriminates nothing.
- **The art websocket's death is a lagging indicator.** Our listener kept
  reporting itself alive for **32–35 s** after the TV left the network, because
  the `websockets` keepalive ping is what eventually notices. Socket liveness must
  never be used as a promptness signal.
- **Wake-on-LAN is fast and reliable here:** REST answered 2.6 s, 2.7 s and 2.7 s
  after the magic packet across three wakes, with all ports open by the next tick.
  One wake is unattributed: `media_player.turn_on` was called and the TV had still
  not answered 30 s later; a subnet-broadcast packet was then sent by hand and REST
  answered within 2 s, but the two are too close together to separate. Worth a
  dedicated probe, since the integration's packet goes to a hardcoded
  255.255.255.255 while every wake measured here used the subnet broadcast.
- **A single-tick REST failure with port 8001 still open** was captured (run 1,
  t=2218): one `rest=error` sample between two clean ones. The reachability oracle
  can blip for one poll with the TV perfectly healthy — which is what the
  undebounced connection sensor will publish.
- **A WoL wake returns the TV to whatever it was doing when it went down**, not to
  art mode: after a power-off from watching, the TV woke into watching
  (`get_artmode` = `off`), and had to be put back into art mode explicitly.

## The art-host wedge — a separate finding

For the whole of run 1 the art channel was **hostless**: our client connected,
`ms.channel.connect` listed it as the only client with `isHost: false`, no
internal host appeared, and `ms.channel.ready` never arrived — while the panel
visibly displayed artwork. This is the state the v0.6.8 supervised-recovery design
was written for. Home Assistant's art entities had already been `unavailable` for
40 minutes before this session began, so the wedge pre-dated any probing.

Remedies tried, in order, all against the live device:

| attempted | result |
|---|---|
| repeated handshakes (8 over 2 min) | no change — and this is the pattern v0.6.8 exists to stop |
| tokenless plain-HTTP port 8001 (July's successful probe path) | **identical hostless client list** — so it is the TV, not our transport or token |
| 3 s power hold, ~7 min fully off the network, WoL wake | no change |
| leaving art mode to watching for 30 s and returning | no change |
| **mains disconnect, 30+ s** | **cleared it** — two internal `isHost: true` clients and `ms.channel.ready` immediately, on both transports |

This extends the July record: it was already known that unloading Home Assistant
and re-entering art mode does not recover a wedged art host. It is now also known
that **a soft power-off, a complete network exit and a Wake-on-LAN wake do not
recover it either**, and that the failure is visible identically on the unsecured
port-8001 path, which rules out the token and the TLS transport.

## What this means for the integration

Nothing changes. Concretely:

- `derive_tv_mode`'s `unreachable → OFF` stays. The inference is not merely
  convenient, it is **correct**: at 10 s polling, an art-sleeping TV and a
  powered-off TV present the same signals in the same order at the same times.
- `binary_sensor.<tv>_connection` keeps its documented meaning — *no contact*,
  cause unstated — and the deferred section of the lost-contact design closes as
  **measured and rejected** rather than pending.
- `binary_sensor.<tv>_art_mode` keeps being forced `False` when off. Since the TV
  never announces leaving art mode on sleep, there is no better signal available.
- The `go_to_standby` handler's "destination is ambiguous" comment is confirmed.

The honest summary for the README and for anyone reading the entity docs: **a
Frame that has gone to sleep on its motion timer is, to everything the network can
see, a Frame that has been switched off.** Wake-on-LAN recovers it from either
state in under 3 seconds, which is why `turn_on` remains available on an entity
that reports `off`.

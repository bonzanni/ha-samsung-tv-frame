# What makes the Frame's art host disappear

Investigation of issue #10, run on 2026-08-17 against the production recorder and
container log on `n150-ha`, plus a documentation and bug-corpus sweep. No device
experiment was performed; everything measured here is mined from records that
already existed.

Two findings, one measured here and one found in the wild:

**1. Every observed failure followed a viewing session.** In the twelve days the
recorder retains, all three viewing sessions longer than a few minutes ended with
the art channel failing, 24 to 42 minutes after the TV left art mode — and no
art-mode session failed, including one of 100 minutes. That is an association in
one household over twelve days, not an intervention: it makes watching the
leading candidate trigger and it is worth one deliberate reproduction, but it is
not yet a demonstrated cause. What it does establish is that the fault is **not
rare and not unobservable**, and that it is not correlated with the slideshow or
with any art command.

**2. It is not unique to this integration.** An owner of the same 2022 Frame
platform (`22_PONTUSM_FTV`) reports the identical hostless signature while running
nothing but the upstream library's plain example script, and reports the same
remedy asymmetry: a soft power-off does not clear it, a mains cycle does. The
maintainer of the library this integration builds on attributes it to a memory
leak in Samsung's own art websocket code.

Nothing in the public record connects the fault to watching. Finding 1 appears to
be new.

**Provenance note.** External sources below are marked *verified* where they were
fetched and read first-hand during this investigation (`gh api`, `curl`), and
*reported* where they came from a research sweep and were not independently
retrieved. The distinction is load-bearing: the sweep was right often enough to be
useful and wrong often enough to check.

## The trail already existed

Issue #10 proposed building a forensic trail and then waiting for the next
occurrence. Most of that trail was already being recorded: Home Assistant's
recorder keeps ten-plus days of every entity this integration publishes, and the
entities are fine-grained enough to time the fault to the second.

Three signals carry the forensics:

| signal | what it means |
|---|---|
| `number.living_room_tv_art_brightness` → `unavailable` | the optional-art gate closed: the art session lost its generation, went not-ready, **or** its settings probe stopped answering (`entity.py:14-49`, `coordinator.py:251-275`) |
| `sensor.living_room_tv_tv_mode` → `unknown` | six consecutive coordinator heartbeats with a failed or unavailable art session (`ART_FAIL_UNKNOWN_COUNT`); note the streak also advances on heartbeats that issue no art request at all, when the session is already down (`coordinator.py:193-194`) |
| `sensor.living_room_tv_current_art` changing | the art channel was observed alive — either a push arrived or the 5-minute reconciliation read answered (`coordinator.py:287-318`) |

The third is close to what the issue asked for and did not know it had: with the
slideshow on a 5-minute rotation, `current_art` is an art-channel liveness trace
at 5-minute resolution, already persisted for ten days. It is not a pure push log
— a reconciliation read updates it too — so it proves the channel answered, not
which direction the traffic went.

The first is a *leading indicator*, not proof of death: it can also close when a
single optional-settings probe times out while the socket is alive. It is used
below only to timestamp the onset to within about a minute; the failure itself is
established by the second signal.

## Three failures, three viewing sessions

Every `tv_mode == watching` run longer than two minutes in the retained window
(all times UTC):

| date | art mode → watching | optional-art gate closed | delay | art queries persistently failing |
|---|---|---|---|---|
| 08-07 | 20:53:44 | 21:31:21 | **37.6 min** | 21:32:31 |
| 08-09 | 18:21:51 | 18:45:42 | **23.9 min** | 18:46:52 |
| 08-16 | 19:18:06 | 19:59:55 | **41.8 min** | 20:01:06 |

Three for three. In all three the `media_player` source is `TV`, which means only
that *no curated streaming app was detected* — `source` falls back to `"TV"`
whenever `running_app` is absent (`media_player.py:170-176`), and detection also
comes back empty if all seven REST status requests fail (`coordinator.py:355-372`).
Live TV, an HDMI input and an uncurated app are indistinguishable here. The other
thirteen `watching` runs in the window are 0.1–0.3 min mode transitions, or the
~1.0 min artifact that appears at the start of a wake episode while the cached
art-mode value is still being published.

And the control: art-mode sessions in the same window, art session healthy
throughout — 65.4, 35.9, 74.7, 56.6, **100.5**, 62.6 and 21.1 minutes. About seven
hours of art mode, zero failures. That 100.5-minute session also excludes a
threshold measured from the panel waking: two of the three failures happened at
less time-since-art-mode-entry than that session survived. It does not exclude a
threshold on the TV's *uptime*, which the recorder cannot see at all — art-sleep
is not a reboot, so this TV's uptime is measured in days.

Note what the timing rules out about the mechanism. `tv_mode` is published from a
*cached* art answer, so `watching` is not proof of a live answer on every
heartbeat — but the cache cannot carry it far. A dead art session forces `unknown`
within roughly six minutes: the reconciliation runs every 300 s
(`ART_RECONCILE_SECONDS`), a hung request gives up after 20 s and closes the
socket (`frame_art.py:816-824`), and six further heartbeats at 10 s then flip the
mode. So the art channel was answering until at most ~6 minutes before each
recorded onset — that is, for at least 18 to 36 minutes *after* the TV left art
mode. Whatever happens, the art host is not lost when the app stops being on
screen; it survives well into the viewing session and then goes.

Only the 08-16 episode was probed live and is therefore the only one *proven* to
be the hostless wedge (client list with no `isHost: true`, `ms.channel.ready`
never arriving). The other two are art-channel failures with the same shape and,
for 08-07, the same persistence; calling them the same fault is an inference.

## It persists — and that was visible without unplugging anything

After the 08-07 failure the art channel stayed dead across all of 08-08 and into
08-09 — through six separate ~60-minute episodes in which the TV was reachable
with `PowerState: on`, i.e. **the panel was displaying art the whole time**. (Those
episodes are art-mode wake cycles ending at the art-sleep timer:
`select.living_room_tv_art_sleep_after` is `60`.) The art channel answered again
at 08-09 17:07:12, about 44 hours later, by a route this data cannot identify — no
household power event is visible in the recorder for that afternoon, and an
unrecorded reboot, a power interruption, or spontaneous recovery all remain
possible — the last of these is reported upstream (see below), which makes it more
than a formality.

So the **persistence** measured on 2026-08-16 has an independent precedent a week
earlier, running to tens of hours rather than 2.5. The *remedy* finding does not
follow from this episode: what ended it is unknown.

## Other people's Frames do this, with none of our code

Issue #10 records the only public hint as xchwarze/samsung-tv-ws-api#115 — an
empty-bodied issue title. That lead is worse than thin and should be dropped:
*verified* via `gh api`, #115 has `body: null`, **zero comments**, and was closed
by the maintainer on 2025-12-27 with `state_reason: completed` and no resolution
text. Its only cross-reference in the entire timeline is this repository's own
issue #10.

The fault is, however, reported in full and with logs on this exact platform:

**NickWaterton/samsung-tv-ws-api#18** (opened 2025-05-26 by `ferdiflash`, verified
verbatim via `gh api`). Their TV reports
`"model":"22_PONTUSM_FTV","modelName":"GQ55LS03BGUXZG"` — the same 2022 LS03B
platform as this one. Running the library's own `async_art_simple.py` example:

```
{"data":{"clients":[{"attributes":{...},"connectTime":...,"deviceName":"U2Fxx",
 "id":"...","isHost":false}],"id":"..."},"event":"ms.channel.connect"}
< PING  > PONG   … just keeps on playing 🏓
```

One client, `isHost: false`, no `ms.channel.ready`, socket healthy forever. That is
our wedge, reproduced by a stranger's plain script. A second owner on the same
platform (`QN65LS03BAFXZA`, `jmjesperson`, 2025-10-22, *verified*) quotes that log
back with "My TV is not even a 2025 TV … and I get this also". Neither report says
what else was on their network, so this does not prove the absence of a polling
client — only that no such client is needed to produce the signature.

The thread also contains both halves of what this repository measured on
2026-08-16, from strangers:

> Sometimes you have to power cycle the TV as there is also a **memory leak in
> Samsung's latest art websocket code that stops it working after a while**. Power
> cycle usually fixes it
> — NickWaterton, library maintainer, 2025-12-07

> I think the power cycle did its trick, as with no code changes I was able to
> connect to the frame via the script … **I tried turning it off before but no
> real power off.**
> — ferdiflash, 2026-01-02

Both comments were fetched and read first-hand (*verified*). That is the
standby-versus-mains asymmetry, independently reproduced by someone else's TV. It
also demotes the most uncomfortable candidate in this repository: the fault does
not require this integration, and nothing suggests those households ran anything
like our watching-mode REST fan-out.

Three more *verified* fragments from the same fork's issues change what to do next:

- The maintainer's memory-leak comment ends: **"This is why the Smarthings app
  doesn't work most of the time as well."** If that is right, Samsung's own app is
  a free oracle — during a wedge, art control in SmartThings should be dead too.
- **A wedge can clear itself.** `piiotre`, 2025-02-13: after too many uploads the
  TV "freezes or lags … I then not even get an error and it timeouts on TCP
  level. Also in that case either waiting or power cycle restores functionality."
  Waiting "a really long time like several hours" is reported to work. That is a
  candidate explanation for this household's unexplained 08-09 recovery, and it
  means a mains cycle may be the fast remedy rather than the only one.
- **A client action can wedge it.** The maintainer, 2025-07-19: "if an upload goes
  wrong, then the TV sometimes will not upload anymore, until you power cycle the
  TV. Not totally common, but it does happen." That is the upload path rather than
  the whole channel losing its host, so it is adjacent, not identical — but it is
  the only maintainer-level statement that client behaviour can put this TV into a
  power-cycle-only state.

## Three things issues #9 and #10 state that are not true

1. **"19:59:55 — the art query returns `off`, so the TV announced itself out of
   art mode."** No: art mode reported `off` at **19:18:06**, 41.8 minutes earlier,
   when the TV switched to watching. What happened at 19:59:55 is that the
   optional-art gate closed.
2. **The 70-second escalation at 20:01:06** is not a device-side delay. It is this
   integration's own debounce: `tv_mode` may not go `unknown` until six
   consecutive art polls have failed (`ART_FAIL_UNKNOWN_COUNT = 6`), which at a
   10-second heartbeat accounts for the gap.
3. **"`docker logs homeassistant` contains zero lines"** for the window. The line
   is there:
   ```
   2026-08-16 22:01:06.153 WARNING (MainThread) [custom_components.samsung_tv_frame]
   Art websocket has failed 6 consecutive polls; tv_mode will report unknown until it recovers
   ```
   The container stamps its log in **local time (UTC+2)**; 22:01:06 local *is*
   20:01:06 UTC, the onset in the table above. The window was searched in UTC
   against a local-time log. (Cross-checked: a second warning at 00:17:49 local
   matches a recorder transition at 22:17:49 UTC.)

## What owns the channel: `msf-server` is not the art app

`isHost` is a first-class field of Samsung's MultiScreen framework, which is what
this websocket API is: the SDK's `Client` class carries exactly
`id / attributes / isHost / connectTime`, with `isHost` documented as the "flag
for determining if the client is the host"
([multiscreen-js `docs/api.md`](https://raw.githubusercontent.com/MultiScreenSDK/multiscreen-js/master/docs/api.md),
*verified*). The stronger claim that only the host client may *open* a channel
comes from the Smart View SDK's API guide, which renders via JavaScript and could
not be retrieved here — *reported*, and not relied on below.

What the empirical record does show (*verified*, `gh api`): a healthy Frame's art
channel lists **two** internal clients named `Smart Device` with
`attributes: {"name": null}` and `isHost: true`, connecting about five seconds
apart, alongside the external client — captured by another owner entirely
(NickWaterton/samsung-tv-ws-api#3, `Adesfire`, 2024-12-19). The wedged list has
none of them. So the flag is not an artifact of this TV or this integration.

A third-party firmware decompile supplies the process boundary that makes a
hostless-but-answering channel possible —
`TheFab21/ha-samsungtv-smart`, `notes/QN55LS03FAFXZA/WEBSOCKET_DECOMPILED.md`
(a **2025 LS03F on Tizen 9**, not this 2022 set, so suggestive rather than
authoritative; the copy read here was fetched fresh and is byte-identical to
upstream, sha256 `bb24610b…`):

> `8001` and `8002` are served by `/usr/bin/msf-server`. … `com.samsung.art-app`
> is registered by the Art app through the SmartView/MSF local service API, **not
> hard-coded in `msf-server`**.

Different processes: the daemon that accepts our socket, and the app
(`/opt/usr/apps/org.tizen.art-app`) that registers the channel and hosts it. Kill
or break the second and the first keeps answering handshakes on a channel with no
host — exactly what is measured, and exactly what strangers capture.

For completeness, Samsung documents that its TVs will kill processes to reclaim
memory — "Since 2017 model groups, Samsung TVs have a stability-monitoring feature
that automatically terminates processes to free up system memory"
([developer FAQ](https://developer.samsung.com/smarttv/develop/faq/other-features.html),
*verified*). The neighbouring "applications are automatically paused when they are
hidden" rule from the same FAQ is *not* a fit twice over: it answers a question
about a web app's `background-support` attribute in `config.xml`, and this art
host kept answering for tens of minutes after being hidden.

Samsung's published remedy for a wedged Frame art app is *reported* to be a mains
disconnect at the wall, twice, rather than a standby toggle
([TSG10002347](https://www.samsung.com/us/support/troubleshoot/TSG10002347/)) —
consistent with what was measured on 2026-08-16, but not retrieved first-hand
here, so treat it as corroboration rather than evidence.

## Where that leaves the mechanism

- **A — the art app or its MSF bridge dies during a viewing session.** Best
  supported: the process boundary is described in a decompile of a neighbouring
  model, the upstream maintainer names a leak in Samsung's art websocket code, and
  a cold boot is what restores it. What is unexplained is why leaving art mode
  should be what starts the clock — nothing in this mechanism predicts that, and
  it is the one thing the data here actually shows.
- **B — our own REST polling** (`_async_detect_running_app()` runs *only* in
  watching mode, `coordinator.py:221-223`, fanning out 7 `GET /api/v2/applications/<id>`
  per 10 s heartbeat — 42 requests/minute, zero in art mode). **Demoted**: someone
  else's TV produced the same signature under a plain script, so this traffic is
  not needed to reach the fault. It is not excluded as an accelerant, it remains
  the only client-side behaviour that differs between the two modes, and it is the
  one candidate we could stop tomorrow — which is why the experiment below is
  still worth an evening.
- **C — a co-resident service dies and takes the art host with it** (the owner's
  SmartThings "TV disconnected" notices; this 2022 Frame does ship a radio-less
  built-in SmartThings Hub sharing Tizen with the art app). **Weakened**: the
  two-`isHost` healthy signature is not special to this TV — public captures of
  other people's Frames show the same two anonymous `Smart Device` hosts
  connecting seconds apart (NickWaterton/samsung-tv-ws-api#3), and a 2019 Frame
  shows one. Nothing ties either host to SmartThings. Worth noting separately that
  this TV leaves the LAN completely when it sleeps (probed 2026-08-17 ~14:20
  local: no ICMP, and 8001/8002/9197/39500/8080 all refused, while ARP still held
  its MAC), so a TV that is genuinely still acting as a hub would be a broken one,
  and the "TV disconnected" notices may be nothing but art-sleep.

## Four tests that cost nothing at the next occurrence

1. **Does the artwork still rotate?** The slideshow runs *inside* the art app. If
   the panel keeps changing picture on its 5-minute interval while the channel has
   no host, the app is alive and only its channel bridge is broken; if the picture
   is frozen, the app is gone. Two photos six minutes apart is the whole
   experiment.
2. **Ask the TV whether the art app is running.** `GET /api/v2/applications/<id>`
   on port 8001 keeps answering throughout the wedge (it is `msf-server`, not the
   art app) and returns `{running, visible}`. The decompile names the package
   `org.tizen.art-app`; whether that string is accepted as an id on this firmware
   is untested, and one request settles it.
3. **Does the remote channel still list clients normally?** `samsung.remote.control`
   carries no `isHost: true` client even on a healthy TV, so a normal remote
   handshake during a hostless art handshake shows `msf-server` is entirely well
   and only the art host is missing. The integration already holds both sockets.
4. **Open the SmartThings app.** Per the upstream maintainer, this same fault is
   why Samsung's own app "doesn't work most of the time". If art control is dead
   in SmartThings while the wedge is on, that is first-party confirmation the
   fault is the TV's, from a client this repository does not write.

## And one long shot that would be worth a great deal

If the art channel's host is an ordinary Tizen application, it may be restartable
over the LAN, without touching the mains: on `samsung.remote.control` — which
keeps working throughout the wedge — stop and then start the art application, and
reopen the art channel to see whether an `isHost: true` client returns.

Everything about that sentence is unverified and it is **not** a recommendation
yet. The package name `org.tizen.art-app` comes from a decompile of a *different
model generation*; no evidence says that string is a valid application id on this
2022 firmware, or that `ms.application.stop` / `start` accept it, or that a
stopped art app restarts cleanly. It is also a mutation, not a read: it could
leave the TV worse than the wedge it is trying to clear, and the only known way
back is the power cycle it is trying to avoid.

So the order is: confirm the command contract against a *healthy* TV first
(does `ms.application.get` acknowledge the id at all?), capture the state, and
only then try the stop/start during a wedge that is already in progress. If it
works, the remedy for this fault stops being "unplug a 65-inch television", which
would change #9 and #11 substantially. Nothing in the public record shows anyone
trying it.

## The experiment that would still settle B

One viewing session: **disable the config entry, watch TV for ≥45 minutes, then
make one direct art-host probe** (from inside the HA container, per the
established recipe). Zero Home Assistant traffic of any kind. Host gone anyway ⇒ B
is dead as an accelerant too, and the trigger is entirely device-side. Host
healthy ⇒ not proof of B from one trial, but it earns the paired run with the
entry enabled. A cheaper secondary: raise the heartbeat option to 60 s, dividing
the REST rate by six, and see whether the onset moves in wall-clock or in request
count.

## What the recorder still cannot say

- It cannot distinguish `ArtHostUnavailable` from an ordinary art connection
  failure. Two of the three episodes are identified by shape, not by a client
  list. **This is the gap the issue's instrumentation must close** — and the
  client list should be recorded on *every* handshake, healthy ones included,
  because the identity of the two healthy hosts is unknown to the entire public
  record and is what would settle C.
- It cannot see what the TV was doing at the instant of failure, only what we
  asked it. A rolling buffer of art pushes plus the last handshake's client list,
  dumped in diagnostics, turns the next occurrence into a two-line diagnosis.
- It cannot tell live TV from an HDMI input, and all three failures were in that
  undifferentiated state. If the trigger is the tuner specifically, this data
  cannot see it.
- No public report anywhere ties this fault to watching TV. The 3-of-3 correlation
  above is, as far as this search could establish, the only evidence of it in
  existence — a reason to hold it loosely, and a reason it is worth publishing
  upstream if it survives one deliberate reproduction.

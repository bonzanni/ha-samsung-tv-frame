# Does the hardcoded 255.255.255.255 Wake-on-LAN broadcast reach this TV?

Investigation of issue #12, run live against the production host on 2026-08-17.

**Answer: yes. The global broadcast reaches the TV and wakes it, and the address
was never the problem.** The premise the issue rested on turned out to be a
misattributed memory record. A real fragility does exist on the wake path, but
it is that a *broadcast-only* wake is a single unacknowledged shot at a TV that
is on Wi-Fi — not that the broadcast is the wrong kind.

## The premise was laundered across three documents

Issue #12 states that "project memory already records that a global broadcast
does not route reliably in at least one environment on this network." The record
it refers to is real. It says something else. Verbatim, from
`memory/frame-state-detection.md`:

> WoL from WSL needs the SUBNET broadcast (192.168.33.255) — 255.255.255.255
> doesn't route out of WSL NAT reliably.

That is about **WSL2's NAT'd stack on the development box**, which is where this
repository is edited from. It is not about `n150-ha`, and it has no bearing on
the Home Assistant container. The qualifier "WSL" was dropped when the claim was
paraphrased into `2026-08-16-frame-capability-map.md` ("the operator's own notes
record needing the subnet broadcast in at least one environment"), and issue #12
then cited the capability map. Three documents, and the environment that
actually failed disappeared between the first and the second.

## What the packet actually does — measured on the wire

The Home Assistant Core container runs with `NetworkMode=host`, so integration
code uses the host's routing table unmodified.

| destination | `ip route get` on n150-ha |
|---|---|
| `255.255.255.255` | `broadcast 255.255.255.255 dev enp1s0  src 192.168.33.2` |
| `192.168.33.255`  | `broadcast 192.168.33.255 dev enp1s0  src 192.168.33.2` |

Both resolve to the LAN NIC. There is no NAT interface for the limited
broadcast to escape down, which is precisely why the WSL failure mode cannot
occur here.

Confirmed by capture rather than by inference. Three packets were sent from
inside the container with fabricated, locally-administered MACs (so nothing on
the LAN could wake), while `tcpdump` watched `enp1s0`:

```
09:50:13.023270 00:ce:39:d7:85:04 > ff:ff:ff:ff:ff:ff, ethertype IPv4 (0x0800),
    length 144: 192.168.33.2.60731 > 255.255.255.255.9: UDP, length 102
09:50:14.023945 00:ce:39:d7:85:04 > ff:ff:ff:ff:ff:ff, ethertype IPv4 (0x0800),
    length 144: 192.168.33.2.45478 > 192.168.33.255.9: UDP, length 102
09:50:15.024648 00:ce:39:d7:85:04 > ff:ff:ff:ff:ff:ff, ethertype IPv4 (0x0800),
    length 144: 192.168.33.2.47976 > 255.255.255.255.7: UDP, length 102
```

Same interface, same source, **same layer-2 destination `ff:ff:ff:ff:ff:ff`**,
same 102-byte magic packet (6 × `0xFF` + 16 × MAC). The global and the subnet
broadcast differ on the wire in four bytes of IP destination address and the
checksum. Nothing between the host and the access point can tell them apart
without inspecting layer 3, and a NIC's magic-packet filter matches the payload
pattern, not the IP header.

The configured MAC is also correct: `a0:d0:5b:86:ce:b7` (a Samsung OUI) matches
the live ARP entry for the configured host `192.168.33.53`.

## The library sends one datagram, to port 9 only

`wakeonlan` 3.3.0, verified byte-identical to the upstream release inside the
container:

```python
with socket.socket(address_family, socket.SOCK_DGRAM) as sock:
    if interface is not None:
        sock.bind((interface, 0))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.connect((ip_address, port))
    for packet in packets:
        sock.send(packet)
```

Two consequences worth recording:

- `BROADCAST_IP = '255.255.255.255'` and `DEFAULT_PORT = 9` are the library's
  own defaults, so the integration's explicit `ip_address="255.255.255.255"`
  **restated the default**. It was never a deliberate override, which is part of
  why it read as suspicious.
- **The issue's founding observation changed two variables, not one.** The
  integration sent `255.255.255.255:9`. The hand-sent packet that worked went to
  `192.168.33.255` on ports **9 and 7**. Address and port were confounded.

## The TV is on Wi-Fi

From the TV's own REST endpoint while awake:

```
networkType = wireless
wifiMac     = A0:D0:5B:86:CE:B7
model       = 22_PONTUSM_FTV   (QE65LS03BAUXXH)
```

This is the finding that reframes the whole issue. **802.11 broadcast frames are
sent at a basic rate, unacknowledged, and never retransmitted**, and an access
point may buffer or drop them for a station in power save — which is exactly
what a sleeping TV is. A unicast frame, by contrast, is acknowledged,
retransmitted on failure, and buffered per station.

So a broadcast-only wake is a single unreliable shot, and it is *equally*
unreliable whichever broadcast address it carries. That explains an occasional
miss without needing the address hypothesis at all.

Separately measured, and load-bearing for the fix: **the TV answers ARP while it
is powered off.** With ICMP at 100% loss and port 8001 closed throughout, the
neighbour entry was watched across a full revalidation cycle:

```
t=10s  192.168.33.53 lladdr a0:d0:5b:86:ce:b7 ... REACHABLE
t=15s  192.168.33.53 lladdr a0:d0:5b:86:ce:b7 ... DELAY
t=20s  192.168.33.53 lladdr a0:d0:5b:86:ce:b7 ... REACHABLE
```

A `DELAY → REACHABLE` transition happens only when the kernel's ARP probe gets a
reply. The panel was off; the NIC answered anyway. A unicast magic packet is
therefore deliverable to a sleeping Frame — which is what makes the unicast arm
of the fix meaningful rather than decorative.

## Live trials

12 counterbalanced trials from inside the HA container, three arms, TV returned
to a verified-off state (`8001` closed) with a 45 s settle before each send, and
a 0.5 s sampler on TCP 8001 with a 90 s ceiling.

| # | arm | woke | time to REST |
|---|---|---|---|
| 1 | GLOBAL `255.255.255.255:9` | yes | 2.17 s |
| 2 | SUBNET `192.168.33.255:9` | yes | 2.11 s |
| 3 | UNICAST `192.168.33.53:9` | yes | 3.01 s |
| 4 | UNICAST | yes | 2.28 s |
| 5 | GLOBAL | yes | 2.20 s |
| 6 | SUBNET | yes | 2.06 s |
| 7 | SUBNET | yes | 2.14 s |
| 8 | UNICAST | yes | 2.22 s |
| 9 | GLOBAL | yes | 3.01 s |
| 10 | UNICAST | yes | 2.43 s |
| 11 | SUBNET | yes | 4.79 s |
| 12 | GLOBAL | yes | 2.08 s |

**12/12 woke. No arm is distinguishable** — every latency falls in 2.06–4.79 s,
and an ARP entry for the TV was present before every send. Per-arm means:
GLOBAL 2.37 s, SUBNET 2.78 s, UNICAST 2.49 s. The single slowest wake in the
whole matrix (4.79 s) was a **subnet** broadcast — the arm issue #12 proposed as
the fix.

An earlier, separately-run global-only trial also woke the TV in 2.71 s.

### What the trials do not establish

They did not reproduce the failure, and were never going to. The production log
holds **exactly one** wake failure across a ~6-day buffer, so the base rate is
far below anything 12 trials can sample. With 0 failures in 12, the 95% upper
bound on a per-attempt failure rate is ~22%; for the 4 GLOBAL trials alone it is
~53%. The trials rule out a *frequent* failure and confirm the global broadcast
works; they cannot measure the rare one.

The weight in this investigation therefore rests on the on-the-wire capture and
the routing table, not on the trial count.

## The one recorded failure

`2026-08-17 00:17:38.845 CEST` — the only Wake-on-LAN warning in the whole log
buffer, and the event issue #12 was filed on:

> TV did not respond within 30 s of the Wake-on-LAN packet; check that WoL is
> enabled on the TV and the stored MAC matches its active network interface

The log shows the wake probe ran for **48.8 continuous seconds** against TCP
8001 without a connection — stronger than the issue's own framing, which allowed
that the integration's packet might merely have landed late. Every wake ever
measured on this device completes in 2.1–29.5 s.

Two confounds were checked and cleared:

- **Mains disconnect.** The art-host wedge session that night was resolved by a
  30 s+ mains disconnect, and Frames commonly lose WoL until powered on once
  after mains is restored. But the wedge memory was written at 01:11 CEST and
  the mains cut was the *last* remedy tried, after the failed wake at 00:17.
  The cut followed the failure; it does not explain it.
- **A wrong MAC.** Ruled out: the stored MAC matches the live ARP entry, and the
  same MAC woke the TV 12 times.

Counter-evidence the issue did not cite: the global broadcast has repeatedly
worked from this host, including on the same day, with recorded wakes of 8 s and
29.5 s via `media_player.turn_on` — which sends only the global packet.

So the failure was real and remains a single unexplained miss. A single
unacknowledged broadcast frame to a sleeping Wi-Fi station is a sufficient
explanation, and it is the only one still standing.

## Prior art: what Home Assistant core does

`homeassistant/components/samsungtv/entity.py`, HA core 2026.8.1:

```python
def _wake_on_lan(self) -> None:
    """Wake the device via wake on lan."""
    send_magic_packet(self._mac, ip_address=self._host)
    # If the ip address changed since we last saw the device
    # broadcast a packet as well
    send_magic_packet(self._mac)
```

**Core sends two packets — unicast to the configured host first, then the global
broadcast.** It never computes a subnet broadcast. This integration was sending
only the second of the two.

`wake_on_lan`'s own documentation states the position on the address directly:
`broadcast_address` "defaults to `255.255.255.255` and is normally not changed."

## The change

`device.py` now sends the same pair core does, with one addition core lacks: a
guard so that a unicast failure cannot cost us the broadcast.

```python
try:
    send_magic_packet(self._mac, ip_address=self._host)
except OSError as err:
    LOGGER.debug("Unicast wake packet to %s failed: %s", self._host, err)
send_magic_packet(self._mac, ip_address="255.255.255.255")
```

Without the guard, a host that will not resolve or route raises out of
`async_turn_on` and the broadcast — the arm that covers a changed address — never
goes out, which would be a regression against today's behaviour.

Deliberately not changed:

- **The subnet broadcast is not used.** It is indistinguishable from the global
  one on this network, and deriving it would need a prefix length the config
  entry does not store.
- **Port 7 is not added.** Port 9 alone woke the TV in every trial; there is no
  evidence for the second port, and it was only ever a confound in the founding
  observation.

## Residual unknowns

- The rare failure is explained by mechanism, not reproduced. If it recurs after
  this change, the next measurement is a capture on the TV's own segment, or the
  AP's client-power-save and multicast-enhancement settings — not the address.
- Whether this Frame's firmware would honour a unicast magic packet when its ARP
  entry has aged out entirely was not tested; the broadcast covers that case.
- The wake-probe warning understates its own bound. It reports "within 30 s"
  (`WAKE_PROBE_ATTEMPTS * WAKE_PROBE_DELAY`) but each iteration also spends up to
  `WAKE_PROBE_TIMEOUT`, so the real ceiling is ~90 s; the observed run took
  48.8 s. Cosmetic, untouched here, worth a separate issue.

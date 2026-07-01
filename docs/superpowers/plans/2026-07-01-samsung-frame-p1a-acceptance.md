# P1a Live Acceptance (run against the real TV at 192.0.2.53)

- [ ] Add integration via UI; accept Allow prompt ONCE (TV in watching mode).
- [ ] Restart HA. Confirm entities reconnect with NO second Allow prompt (token persisted).
- [ ] TV watching Netflix → `sensor...tv_mode` == `watching`, media_player == `playing`.
- [ ] Switch to art mode → within ~1 s `sensor...tv_mode` == `art_mode`, binary_sensor == `on`.
- [ ] Power off (3 s hold) → within ~20 s `sensor...tv_mode` == `off`, media_player == `off`.
- [ ] Call `media_player.turn_on` → TV wakes via WoL.
- [ ] Create the art→watching automation; verify it fires on the transition.

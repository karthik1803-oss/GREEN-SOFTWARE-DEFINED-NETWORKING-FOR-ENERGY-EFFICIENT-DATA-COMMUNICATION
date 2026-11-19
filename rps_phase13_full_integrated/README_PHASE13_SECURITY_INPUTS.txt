PHASE 13 - SECURITY INPUT CONSTRUCTION

Goal
----
Preserve the validated Phase 12 Ryu/OpenFlow RPS behavior and add the inputs that
will be authenticated in Phase 14.

For each LAN1 -> LAN6 experiment route installation, the controller records:
  timestamp, nonce, source MAC, destination MAC, source IP, destination IP, path

No secret key is transmitted or logged. No HMAC/token is generated in Phase 13.
That is intentionally deferred to Phase 14.

Run
---
Terminal 1:
  cd rps_phase13_security_inputs
  ryu-manager --ofp-tcp-listen-port 6653 phase13_ryu_controller.py

Terminal 2:
  cd rps_phase13_security_inputs
  sudo mn -c
  sudo python2 phase12_sdn_topology.py

Mininet validation:
  sdnstatus
  h1 ping -c 3 192.168.6.10
  flows r1
  traffic 120

Ryu should print SECURITY-INPUT records such as:
  SECURITY-INPUT | src=192.168.1.10/00:00:00:00:01:10 dst=192.168.6.10/00:00:00:00:06:10 ts=... nonce=... path=R1 -> ... -> R6

A CSV is created in the controller working directory:
  phase13_security_inputs.csv

Inspect it from a normal shell after/during the run:
  tail -n 10 phase13_security_inputs.csv

Important
---------
This phase constructs security metadata at route-installation time. It does NOT
claim per-packet authentication yet. Phase 14 will add HMAC-SHA256 token creation,
and later phases will add verification/freshness/replay enforcement.

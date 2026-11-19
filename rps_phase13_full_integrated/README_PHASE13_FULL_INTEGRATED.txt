PHASE 13 FULL INTEGRATED RYU/OPENFLOW BUILD
===========================================
This build keeps the validated Phase 12/13 OpenFlow RPS and integrates all features implemented so far:
- Dynamic packet/flow classification: HIGH/MEDIUM/LOW
- DSCP marking: HIGH=46, MEDIUM=18, LOW=8
- OpenFlow port-stat link utilization
- Four-path priority-aware RPS
- Hysteresis and hold-down
- OpenFlow FlowMod path switching
- Phase 13 security inputs: MAC, IP, timestamp, nonce, current path
- Green underutilized-link sleep state
- >=2 viable R1-R6 paths safety rule
- Selective minimum-link wake when current-path bottleneck >=70%
- Baseline/proposed power and cumulative modeled energy
- Energy saving %, sleep/wake event counters

IMPORTANT: Green mode here is SIMULATE, matching the earlier safe experimental mode. A sleeping link is logically excluded from RPS and energy accounting; the OVS interface is not physically shut down. Therefore power/energy values are MODEL ESTIMATES, not physical wattmeter measurements.

Defaults:
underutilized <=10% for 3 Green cycles
wake threshold >=70%
minimum viable R1-R6 paths = 2
active link power model = 10W
sleeping link power model = 2W

RUN
Terminal 1:
  ryu-manager --ofp-tcp-listen-port 6653 phase13_ryu_controller.py
Terminal 2:
  sudo mn -c
  sudo python2 phase12_sdn_topology.py
Mininet:
  sdnstatus
  h1 ping -c 3 192.168.6.10
  traffic 180

Ryu prints CLASSIFICATION, RPS and GREEN output automatically.

CSV files:
  phase13_integrated_rps.csv
  phase13_security_inputs.csv
  phase13_energy_statistics.csv

Graphs after experiment:
  python3 generate_phase13_full_graphs.py
Output folder:
  phase13_full_graphs/

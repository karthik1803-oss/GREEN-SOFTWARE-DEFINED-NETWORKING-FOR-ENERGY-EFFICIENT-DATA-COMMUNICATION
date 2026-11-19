PHASE 13 INTEGRATED — Dynamic Classification + OpenFlow DSCP + RPS + Security Inputs

Purpose
- Preserve validated Phase 12 OpenFlow RPS.
- Dynamically classify sampled R1->LAN6 traffic from observed packet properties.
- Map HIGH/MEDIUM/LOW to DSCP 46/18/8 in OpenFlow.
- Use the classified network priority in RPS path-cost calculation.
- Preserve Phase 13 security inputs: MACs, IPs, timestamp, nonce, selected path.

Important: DSCP marking is implemented in OpenFlow. This package does NOT claim that the old Linux-router HTB queues were migrated to OVS; queue enforcement is a later integration item.

Run Terminal 1:
  ryu-manager --ofp-tcp-listen-port 6653 phase13_ryu_controller.py

Run Terminal 2:
  sudo mn -c
  sudo python2 phase12_sdn_topology.py

Mininet:
  sdnstatus
  h1 ping -c 3 192.168.6.10
  traffic 120
  flows r1

Expected Ryu output includes:
  DYNAMIC CLASSIFICATION
  FLOW ... score=... => HIGH/MEDIUM/LOW
  NETWORK PRIORITY ... DSCP=...
  RPS | priority=... DSCP=... | current ... | best ... | KEEP/SWITCH
  SECURITY-INPUT ...

CSVs:
  phase13_security_inputs.csv
  phase13_integrated_rps.csv

Graphs after experiment:
  python3 generate_phase13_integrated_graphs.py
Outputs are written to phase13_integrated_graphs/.

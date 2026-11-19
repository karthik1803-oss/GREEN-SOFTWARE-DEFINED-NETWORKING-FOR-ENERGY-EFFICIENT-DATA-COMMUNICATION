PHASE 10 - GREEN THRESHOLD EVALUATION

Purpose
-------
Compare multiple underutilization thresholds under the same workload instead
of assuming 10% is optimal.

Run
---
sudo mn -c
sudo python2 topology_dynamic_step5.py

At the Mininet prompt:
  thresholdtest 5,10,15,20 120

The command automatically performs four sequential trials. Each trial:
- restores all links
- resets Green energy counters and RPS counters
- starts the same traffic workload for duration+30 seconds
- uses required low-load cycles = 3
- uses wake threshold = 70%
- uses SIMULATE mode
- runs Auto-RPS at 10 s interval, hysteresis 3, hold-down 20 s
- preserves at least two viable R1-R6 paths
- runs for the requested bounded duration

Output
------
threshold_comparison.csv
Columns:
threshold_percent,duration_sec,cycles,switch_count,sleep_events,wake_events,
active_links,sleeping_links,viable_paths,baseline_energy_j,
proposed_energy_j,energy_saving_percent

Graphs
------
python3 generate_threshold_graphs.py

Produces:
threshold_vs_energy_saving.png
threshold_vs_sleeping_links.png
threshold_vs_route_switches.png
threshold_vs_viable_paths.png

Important
---------
The 10 W ACTIVE / 2 W SLEEPING values are an experimental energy model,
not physical power measurements from Mininet.
Do not select a final threshold only from energy saving. Phase 11 should also
compare network performance (throughput, latency, jitter, loss and retransmissions).

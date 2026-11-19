PHASE 10 FIX + PHASE 11
=======================

Phase 10 fix:
- threshold trials run synchronously; no Auto-RPS background worker is started.
- exactly duration/10 control slots are attempted.
- EINTR (errno 4) and empty transient Mininet command interruptions are retried up to 3 times.
- stale tcpdump processes are cleaned between trials.
- failed individual cycles are recorded/skipped rather than poisoning the rest of the trial.
- summary includes successful_cycles.

Phase 11:
Run:
  phase11test 5,10,15,20 120

It performs the corrected Phase 10 experiment and also records:
- average backbone throughput
- average backbone utilization
- H1->H11 latency
- packet loss
- RTT mdev as jitter proxy
- TCP retransmission delta
- energy saving
- active/sleeping links and viable paths

Outputs:
  phase11_green_performance_comparison.csv
  phase11_cycle_metrics.csv

Graphs:
  python3 generate_phase11_graphs.py

Note: SIMULATE mode models sleeping links logically; it does not physically power hardware.

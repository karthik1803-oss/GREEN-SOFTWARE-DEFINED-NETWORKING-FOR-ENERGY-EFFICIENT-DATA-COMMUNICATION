PHASE 4 COMPLETE - NETWORK MONITORING + STATISTICS

RUN:
  sudo mn -c
  sudo python2 topology_dynamic_step5.py

RECOMMENDED:
  mininet> traffic
  mininet> experiment

The experiment automatically samples at:
  30 sec
  60 sec
  90 sec
  120 sec

OUTPUT:
  network_statistics.csv
  link_statistics.csv

NETWORK CSV:
  time_sec
  avg_throughput_mbps
  packet_loss_percent
  configured_bandwidth_mbps
  avg_utilization_percent
  latency_ms
  jitter_ms
  tcp_retransmissions_actual
  expected_transmissions
  packets_sent
  packets_received
  packets_dropped

Expected transmissions:
  1 / (1 - p)
where:
  p = packet_loss_percent / 100

Graphs generated in:
  graphs_timeseries/

Graphs:
  throughput_vs_time.png
  packet_loss_vs_time.png
  bandwidth_vs_time.png
  latency_vs_time.png
  jitter_vs_time.png
  retransmission_vs_time.png
  utilization_vs_time.png
  expected_transmissions_vs_time.png
  per_link_utilization_vs_time.png
  per_link_throughput_vs_time.png

NOTE:
  Jitter is still ping RTT mdev, so it is a jitter proxy.
  TCP retransmissions are actual measured retransmission counters.


SIMPLIFIED CLI
==============

The separate commands:

  classify
  monitor

have been removed from the CLI.

Reason:
- Dynamic packet classification is already executed internally by `rps`.
- Full Phase 4 monitoring/statistics are handled by `experiment`.

Recommended commands now:

  traffic
  experiment
  rps
  graph
  routecheck
  stoptraffic
  rpshelp

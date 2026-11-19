PHASE 5 - DYNAMIC QoS + RPS
=============================

WHAT WAS ADDED
--------------

The existing dynamic classifier is now connected to a real Linux QoS
enforcement layer.

There are still NO static HIGH/MEDIUM/LOW flow labels.

Pipeline:

  traffic
      |
      v
  live tcpdump capture
      |
      v
  dynamic classifier
      |
      +---- HIGH
      +---- MEDIUM
      +---- LOW
      |
      v
  DSCP marking with iptables
      |
      v
  HTB HIGH/MEDIUM/LOW queues on backbone router interfaces
      |
      v
  priority-aware RPS path selection
      |
      v
  route switching

QoS MAPPING
-----------

HIGH
  DSCP EF = 46
  guaranteed rate = 50 Mbps
  ceil = 100 Mbps
  HTB priority = 0

MEDIUM
  DSCP AF21 = 18
  guaranteed rate = 30 Mbps
  ceil = 100 Mbps
  HTB priority = 1

LOW
  DSCP CS1 = 8
  guaranteed rate = 20 Mbps
  ceil = 100 Mbps
  HTB priority = 2

Unused capacity can be borrowed up to the full 100 Mbps link capacity.

Each QoS class also preserves:
  2 ms link delay
  1000 packet queue limit

MAIN WORKFLOW
-------------

Start:

  sudo mn -c
  sudo python2 topology_dynamic_step5.py

Inside Mininet:

  mininet> traffic
  mininet> rps
  mininet> qosstatus
  mininet> experiment

IMPORTANT:
  Run rps AFTER traffic starts.
  rps performs the live classification and installs QoS rules dynamically.

COMMANDS
--------

traffic
  Start the experiment traffic.

rps
  Capture packets, classify them dynamically, install QoS,
  calculate utilization-aware priority path costs, and switch route.

qosstatus
  Show HTB classes, tc filters, and iptables DSCP rules.

qosoff
  Remove dynamic priority marking and restore a neutral one-class
  100 Mbps baseline while preserving 2 ms delay and queue limit.

experiment
  Collect the 30/60/90/120 second Phase 4 metrics.

routecheck
  Show routing tables.

stoptraffic
  Stop iperf traffic.

QoS TESTING
-----------

WITH QoS:

  mininet> traffic
  mininet> rps
  mininet> experiment

WITHOUT QoS baseline:

  mininet> qosoff
  mininet> traffic
  mininet> experiment

For a clean scientific comparison, run each case from a fresh topology
and save/rename the CSV files after each run.

NEW EXPERIMENT SUMMARY
----------------------

experiment also creates:

  experiment_summary.csv

This stores exactly the main values printed at every 30-second sample:

  time_sec
  average_throughput_mbps
  average_utilization_percent
  packet_loss_percent
  latency_ms
  jitter_proxy_ms
  tcp_retransmissions_interval
  tcp_retransmissions_cumulative
  expected_transmissions
  packets_sent
  packets_received
  packets_dropped

TCP retransmissions are now stored in TWO forms:

1. interval retransmissions
   retransmissions observed during that 30-second interval

2. cumulative retransmissions
   retransmissions since the beginning of the 120-second experiment

GRAPH GENERATION
----------------

  python3 generate_qos_graphs.py experiment_summary.csv

Output:
  qos_graphs/

NOTE
----

The current jitter value remains ping RTT mdev, so it is a jitter proxy.
For strict UDP application-level jitter, parse iperf UDP jitter later.

The current architecture is still centralized Linux routing with OVS
standalone mode. It is QoS-enabled and dynamically routed, but it should
not yet be described as OpenFlow-controlled SDN.

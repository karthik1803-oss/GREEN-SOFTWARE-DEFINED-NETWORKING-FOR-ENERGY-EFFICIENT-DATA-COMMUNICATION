RPS PROJECT - STEP 5 UPDATE
===========================

This version adds:

1. 100 Mbps controlled backbone links using Mininet TCLink.
2. 2 ms delay on every router-to-router backbone link.
3. Dynamic packet classification from the previous version.
4. Complete Step 5 monitoring framework.
5. RPS now uses utilization percentage instead of unbounded raw Mbps.

FILES
-----
topology_dynamic_step5.py
rps_controller6.py
traffic_classifier.py

RUN
---
sudo mn -c
sudo python2 topology_dynamic_step5.py

START TRAFFIC
-------------
mininet> traffic

DYNAMIC PRIORITY
----------------
mininet> classify

STEP 5 MONITORING
-----------------
mininet> monitor

Default sampling interval: 5 seconds.

Or:

mininet> monitor 10

The monitor reports:

- Backbone throughput
- Configured bandwidth
- Link utilization %
- Packet loss/drop information
- End-to-end latency
- Jitter proxy using ping RTT mdev
- TCP retransmissions
- Packets sent
- Packets received
- Packets dropped
- Interface errors

RPS
---
mininet> rps

RPS now performs:

1. packet capture
2. dynamic priority classification
3. real link throughput measurement
4. utilization calculation
5. priority-aware path-cost calculation
6. best path selection
7. route update

BACKBONE CAPACITY
-----------------
All eight router-to-router links:

R1-R2
R1-R3
R2-R4
R2-R5
R3-R4
R3-R5
R4-R6
R5-R6

are configured as:

100 Mbps
2 ms delay
queue size 1000 packets

UTILIZATION
-----------
Utilization = measured directional throughput / 100 Mbps * 100

The busier direction is used for a full-duplex link.

RPS LINK COST
-------------
0-10%    -> 1
10-30%   -> 2
30-50%   -> 4
50-70%   -> 6
70-90%   -> 8
>90%     -> 10

HIGH priority:
  path cost = sum(link costs) + 2 * worst-link cost

MEDIUM:
  path cost = sum(link costs) + worst-link cost

LOW:
  path cost = sum(link costs)

IMPORTANT RESEARCH NOTE
-----------------------
The displayed "jitter" is currently ping RTT mdev, which is an RTT
variation proxy. It is NOT the same as RTP/UDP one-way jitter.

For the next phase (30-second CSV collection), UDP iperf server results
can be parsed separately to report iperf's actual UDP jitter and packet
loss as an experimental application-level metric.

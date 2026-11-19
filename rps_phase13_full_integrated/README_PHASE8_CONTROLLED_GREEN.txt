PHASE 8 - CONTROLLED GREEN RPS EXPERIMENT
=========================================

This update makes the Auto-RPS/Green experiment bounded and preserves routing redundancy.

1. BOUNDED AUTO-RPS
   autorps [interval] [hysteresis] [hold-down] [duration]
   Example: autorps 10 3 20 120
   Default duration is 120 seconds. The loop schedules cycles from the experiment start time
   to reduce timing drift and stops automatically at the deadline.

2. TRAFFIC GUARD WINDOW
   traffic [duration]
   Default traffic duration is now 150 seconds so a 120-second controller experiment remains
   under workload through its final control cycle. Example: traffic 150

3. BACKUP-PATH PROTECTION
   Green sleep decisions now require at least TWO viable R1-R6 paths after a candidate link
   is logically/physically slept. This preserves one primary and at least one backup path.
   The four protected RPS paths are:
     R1-R2-R4-R6
     R1-R2-R5-R6
     R1-R3-R4-R6
     R1-R3-R5-R6

4. GREEN STATUS
   greenstatus now reports viable R1-R6 paths and the minimum preserved path count.

RECOMMENDED TEST
----------------
sudo mn -c
sudo python2 topology_dynamic_step5.py

mininet> traffic 150
mininet> greenon 10 3 70 simulate
mininet> autorps 10 3 20 120

Auto-RPS should stop automatically after 120 seconds. Then run:
mininet> autorpsstatus
mininet> greenstatus

Expected behavior:
- no indefinite cycle growth;
- approximately 12 cycles at a 10-second interval (processing timing may affect exact count);
- Green control will not reduce the topology below two viable R1-R6 paths;
- traffic remains active throughout the 120-second measurement window.

PHASE 9 - GREEN WAKE / CAPACITY RESTORATION TEST

New behavior
------------
1. Congestion no longer wakes every sleeping backbone link.
2. The Green manager finds an unavailable alternate R1-R6 path that needs
   the fewest sleeping links restored and wakes only those links.
3. New Mininet command: wakeburst [mbps] [duration]
   Default: wakeburst 95 35
   It starts a temporary H1->H11 UDP burst on port 5099. Because H11 is in
   192.168.6.0/24, the burst follows the currently selected RPS path.
4. If the measured bottleneck reaches the configured wake threshold (70%
   in greenon 10 3 70 simulate), the next Green evaluation restores the
   minimum links needed to make an additional R1-R6 path available.

Recommended controlled test
---------------------------
sudo mn -c
sudo python2 topology_dynamic_step5.py

mininet> traffic 180
mininet> greenon 10 3 70 simulate
mininet> autorps 10 3 20 150

Wait until greenstatus shows at least one sleeping link, then:
mininet> wakeburst 95 35

Observe subsequent cycles for:
  Current-path bottleneck >= 70%
  Wake decision : CONGESTION - restore capacity
  Woken link(s) : ...

Then:
mininet> greenstatus
mininet> autorpsstatus

Expected result
---------------
- Green first sleeps persistently underutilized redundant links.
- A high-rate burst loads the current path.
- The Green manager wakes the minimum sleeping link set needed to restore
  an alternate R1-R6 path.
- RPS can then evaluate the restored path in the following cycle.
- wake_events increases.

Notes
-----
SIMULATE mode changes logical Green/RPS availability and the energy model;
it does not physically bring Mininet interfaces down. LIVE mode performs
interface down/up operations and retains the connectivity rollback checks.

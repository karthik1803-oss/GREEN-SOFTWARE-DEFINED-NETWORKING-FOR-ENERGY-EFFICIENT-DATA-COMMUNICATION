PHASE 7 - GREEN / ENERGY-AWARE ROUTING
======================================

WHAT THIS PHASE ADDS
--------------------

1. Underutilized-link detection.
2. Consecutive low-utilization thresholding.
3. Traffic/path consolidation around the current R1-R6 route.
4. Sleeping-link state.
5. Automatic wake-up when the active path becomes congested.
6. Optional LIVE interface DOWN/UP mode.
7. Safety rollback for LIVE mode using the five experiment flows.
8. Energy/power model and energy_statistics.csv.
9. Energy graphs.

IMPORTANT
---------

The energy values are SIMULATION PARAMETERS, not measurements from
physical switches/routers.

Default model:
  ACTIVE backbone link   = 10 W
  SLEEPING backbone link = 2 W

Baseline power with all 8 links active:
  8 * 10 W = 80 W

Energy saving:
  (baseline_energy - proposed_energy) / baseline_energy * 100

RECOMMENDED FIRST TEST - SIMULATION MODE
----------------------------------------

sudo mn -c
sudo python2 topology_dynamic_step5.py

mininet> traffic
mininet> greenon 10 3 70 simulate
mininet> autorps 10 3 20

Meaning:
  10 = link is underutilized at <= 10%
   3 = it must remain low for 3 controller cycles
  70 = wake sleeping capacity if current path bottleneck >= 70%

SIMULATE mode does not physically bring links down. It marks them as
SLEEPING for routing/energy-model purposes, so it is the safest mode for
validating the logic first.

Check:
  mininet> greenstatus
  mininet> autorpsstatus

Stop:
  mininet> stopautorps
  mininet> greenoff

LIVE MODE
---------

After simulation works:

mininet> greenon 10 3 70 live
mininet> autorps 10 3 20

LIVE mode can run `ip link set ... down` on both router endpoints of an
eligible backbone link.

Before keeping a link asleep, the code tests the five experiment traffic
relationships. If connectivity fails, the link is immediately restored.

The controller sleeps at most ONE new link per cycle.

WAKE LOGIC
----------

If the bottleneck utilization of the current selected R1-R6 path reaches
70% or more, all sleeping links are restored so RPS can consider the
additional paths on the next cycle.

AUTO RPS INTEGRATION
--------------------

When Green control is enabled, any RPS path containing a SLEEPING link is
shown as:

  SLEEPING / UNAVAILABLE

and is not selected.

The selected current path itself is protected from sleeping.

COMMANDS
--------

greenon [threshold] [cycles] [wake_threshold] [simulate|live]

greenstatus

greenoff

wakeall

autorps 10 3 20

autorpsstatus

stopautorps

OUTPUT FILE
-----------

energy_statistics.csv

Columns:
  cycle
  timestamp
  mode
  current_path
  active_links
  sleeping_links
  baseline_power_w
  proposed_power_w
  baseline_energy_j
  proposed_energy_j
  energy_saving_percent
  sleep_events
  wake_events

GRAPHS
------

After the experiment:

python3 generate_energy_graphs.py energy_statistics.csv

Graphs are generated under:
  energy_graphs/

NEXT STEP
---------

After this works reliably:
  1. evaluate thresholds (5%, 10%, 15%, etc.)
  2. compare baseline vs Green routing
  3. then integrate the token/security phases

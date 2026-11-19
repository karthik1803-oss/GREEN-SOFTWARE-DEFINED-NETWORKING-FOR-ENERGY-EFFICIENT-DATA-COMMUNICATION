PHASE 6 - CONTINUOUS AUTO RPS
================================

NEW FEATURES
------------

1. Continuous automatic RPS
2. Hysteresis / anti-flapping
3. Hold-down timer
4. Bidirectional R1 <-> R6 route switching
5. Dynamic DSCP marking refresh
6. Route-switch logging in auto_rps_log.csv

RUN
---

sudo mn -c
sudo python2 topology_dynamic_step5.py

Inside Mininet:

  mininet> traffic
  mininet> autorps 10 3 20

Meaning:

  10 = auto-RPS interval in seconds
   3 = minimum path-cost improvement needed to switch
  20 = minimum hold-down time between switches

The controller repeatedly performs:

  link measurement
      ->
  packet classification
      ->
  HIGH / MEDIUM / LOW
      ->
  dynamic DSCP refresh
      ->
  calculate all 4 path costs
      ->
  compare current path vs best path
      ->
  hysteresis check
      ->
  hold-down check
      ->
  bidirectional route switch when justified

STATUS
------

  mininet> autorpsstatus

STOP
----

  mininet> stopautorps

MANUAL ONE-SHOT RPS
-------------------

  mininet> rps

The manual RPS command is also updated to install the selected path in
both directions.

BIDIRECTIONAL EXAMPLE
---------------------

Selected forward path:

  R1 -> R3 -> R5 -> R6

Forward destination:

  192.168.6.0/24

Reverse path:

  R6 -> R5 -> R3 -> R1

Reverse destination:

  192.168.1.0/24

ANTI-FLAPPING EXAMPLE
---------------------

Current cost = 12
Best cost    = 11
Hysteresis   = 3

Improvement = 1, so KEEP current path.

Current cost = 12
Best cost    = 7

Improvement = 5. If the 20-second hold-down has expired, SWITCH.

LOG FILE
--------

auto_rps_log.csv contains:

  cycle
  timestamp
  priority
  current_path
  current_cost
  best_path
  best_cost
  decision
  switch_count

RECOMMENDED TEST
----------------

  mininet> traffic
  mininet> autorps 10 3 20

Let it run for at least 60 seconds. During the run:

  mininet> autorpsstatus
  mininet> routecheck
  mininet> qosstatus

Then:

  mininet> stopautorps

NEXT PHASE
----------

Green routing:

  underutilized-link detection
      ->
  traffic consolidation
      ->
  safe link sleep
      ->
  automatic wake-up
      ->
  energy model and energy-saving CSV

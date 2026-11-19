PHASE 13 - INTEGRATED GREEN + NETWORK EFFECT + WAKE VALIDATION

What changed
1. Green threshold runs remain 5, 10, 15, 20 percent.
2. Separate network-effect measurements are now saved:
   - average backbone throughput (derived from OpenFlow active-link utilization x 100 Mbps)
   - average backbone utilization
   - end-to-end RTT latency (h1 -> h11 ping)
   - jitter proxy (ping RTT mdev)
   - packet loss
   - TCP RetransSegs delta sampled from TCP traffic hosts
3. Wake mechanism is congestion-triggered and configurable.
   Default GREEN_WAKE_THRESHOLD=40 percent so the existing workload can exercise wake behavior.
   A woken link is protected from re-sleep for 30 seconds (GREEN_WAKE_HOLD) to prevent immediate sleep/wake oscillation.
   Wake restores the minimum number of sleeping links needed to make an alternate path available.
4. Graphs are separated into:
   threshold_green_graphs/
   threshold_network_effect_graphs/

RUN EACH THRESHOLD (same duration/workload)
Terminal 1:
  python3 clear_run_csvs.py
  GREEN_THRESHOLD=5 GREEN_WAKE_THRESHOLD=40 ryu-manager --ofp-tcp-listen-port 6653 phase13_ryu_controller.py
Terminal 2:
  sudo mn -c
  sudo python2 phase12_sdn_topology.py
  mininet> traffic 180
After the run, stop/exit and save:
  python3 save_threshold_run.py 5
Repeat for 10,15,20.

Generate all threshold graphs:
  python3 generate_threshold_comparison_graphs.py

WAKE VALIDATION
Watch the Ryu terminal. A wake is valid only when:
- at least one link is sleeping, and
- current-path bottleneck >= GREEN_WAKE_THRESHOLD.
Expected event example:
  EVENTS : sleep=3 | wake=1 | last=WAKE R1-R3 | wake-trigger=40%
Then threshold_vs_wake_events.png will contain a non-zero bar for that run.

If normal workload never reaches 40%, use 35% for a dedicated wake validation run:
  GREEN_THRESHOLD=10 GREEN_WAKE_THRESHOLD=35 ryu-manager --ofp-tcp-listen-port 6653 phase13_ryu_controller.py
Do not describe this as the same threshold-comparison experiment unless all compared runs use the same wake threshold.

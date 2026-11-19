PHASE 13 SDN THRESHOLD COMPARISON (5%, 10%, 15%, 20%)

For a fair comparison, use the SAME traffic duration for every run (recommended 180 s).
Before each run: stop Ryu/Mininet, save the previous run, then clear current CSVs.

For threshold 5%:
  python3 clear_run_csvs.py
  GREEN_THRESHOLD=5 ryu-manager --ofp-tcp-listen-port 6653 phase13_ryu_controller.py
  # second terminal: sudo mn -c ; sudo python2 phase12_sdn_topology.py ; mininet> traffic 180
  # after run and after stopping controller:
  python3 save_threshold_run.py 5

Repeat with GREEN_THRESHOLD=10, 15, 20 and save with matching number.

After all four runs:
  python3 generate_threshold_comparison_graphs.py

Outputs:
  phase13_threshold_comparison.csv
  threshold_comparison_graphs/

The Ryu console is now grouped into one readable SDN CYCLE block showing:
  traffic priority + DSCP
  current/best RPS path + decision + switches
  all P1-P4 utilization/cost/state
  active/sleeping/viable links
  bottleneck utilization
  baseline -> proposed power
  baseline -> proposed energy
  cumulative energy saved
  sleep/wake event counts and last event

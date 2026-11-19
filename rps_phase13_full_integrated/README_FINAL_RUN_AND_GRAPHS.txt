FINAL PROJECT RUN (RPS + GREEN + SECURITY)
==========================================
1) Clear only run CSVs:
   python3 clear_run_csvs.py

2) Start controller:
   export RPS_SECURITY_KEY='my-demo-secret-key'
   GREEN_THRESHOLD=20 GREEN_WAKE_THRESHOLD=40 ryu-manager --ofp-tcp-listen-port 6653 phase13_ryu_controller.py

3) In another terminal:
   sudo mn -c
   sudo python2 phase12_sdn_topology.py
   mininet> traffic 180

4) After the run, security evidence:
   python3 security_summary.py
   python3 generate_security_graphs.py

New security graphs:
- security_allow_vs_deny.png
- security_authentication_reasons.png
- security_event_summary.png

Existing Green/RPS/network graphs remain unchanged. The new security graphs are additional evidence and do not replace the old threshold/performance graphs.

IMPORTANT PRESENTATION WORDING
------------------------------
The current HMAC mechanism protects the selective-wake control action. It does not modify every TCP/UDP application payload. A wake is allowed only when the controller has a valid, fresh HMAC security record; otherwise the wake request is denied.

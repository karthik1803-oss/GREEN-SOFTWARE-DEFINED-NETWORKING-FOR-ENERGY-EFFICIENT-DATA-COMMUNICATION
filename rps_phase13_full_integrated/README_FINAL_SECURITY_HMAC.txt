FINAL SECURITY MECHANISM (ADDED WITHOUT REMOVING EXISTING PHASE-13 FEATURES)
=========================================================================== 

What was added
--------------
1. HMAC-SHA256 token generation. The digest is 32 bytes (64 hex characters).
2. Secret key remains local to the controller/router security logic and is never written to packet/security CSV logs.
3. Existing Phase-13 security input CSV is preserved unchanged:
   timestamp,nonce,src_mac,dst_mac,src_ip,dst_ip,path
4. New file: phase14_security_authentication.csv
   It logs TOKEN_CREATE and WAKE ALLOW/DENY decisions.
5. Every Green sleep event stores that link's last sleep timestamp.
6. When Green selective-wake wants to restore a sleeping link, wake is allowed only if the latest security record passes:
   - timestamp parsing
   - freshness window
   - future-timestamp rejection
   - HMAC-SHA256 recomputation
   - constant-time token comparison
7. Invalid/missing/expired/tampered tokens deny the wake operation.
8. Existing RPS, classification, DSCP, hysteresis, hold-down, Green threshold logic,
   minimum 2 viable paths, power/energy accounting and network-effect CSVs are retained.

Token formula
-------------
M = srcMAC || dstMAC || srcIP || dstIP || timestamp || nonce || currentPath
TOKEN = HMAC-SHA256(SECRET_KEY, M)

The requested MAC + timestamp + secret-key idea is implemented using HMAC rather than
plain HASH(MAC + timestamp + secret). HMAC is the correct keyed construction and the
existing Phase-13 fields are included too, so changing destination/path/nonce also breaks validation.

IMPORTANT IMPLEMENTATION DETAIL
-------------------------------
OpenFlow 1.3 / OVS cannot natively compute HMAC-SHA256 on arbitrary packets. Therefore the
cryptographic token is handled by the Ryu control-plane security mechanism and gates the
Green wake decision. The normal IP/TCP/UDP packet payload is NOT modified, so existing
traffic generation, checksums and performance measurements continue to work unchanged.

Run
---
Terminal 1:
  cd <project-folder>
  export RPS_SECURITY_KEY='my-demo-secret-key'
  GREEN_THRESHOLD=20 GREEN_WAKE_THRESHOLD=40 ryu-manager --ofp-tcp-listen-port 6653 phase13_ryu_controller.py

Terminal 2:
  sudo mn -c
  sudo python2 phase12_sdn_topology.py

Mininet:
  traffic 180

Watch for:
  SECURITY-AUTH | event=TOKEN_CREATE result=CREATED ...
  SECURITY-TOKEN | ... token=<first bytes>...
  SECURITY-AUTH | event=WAKE result=ALLOW reason=HMAC_VALID ...

Existing cycle output remains and wake counters continue to appear there.

Files to inspect after run
--------------------------
  phase13_security_inputs.csv            (unchanged old security inputs)
  phase14_security_authentication.csv    (new token/authentication audit)
  phase13_integrated_rps.csv
  phase13_energy_statistics.csv
  phase13_network_effect.csv

Security test knobs
-------------------
  RPS_SECURITY_KEY       secret key; set it before starting Ryu
  RPS_TOKEN_MAX_AGE      freshness window in seconds; default 300

For the report/viva
-------------------
"The controller creates a 32-byte HMAC-SHA256 token from the security fields using a secret
key that is never transmitted. Green links retain their last sleep timestamp. Before a
selective wake operation, the controller recomputes the HMAC and compares it in constant
time. Only a valid, fresh token authorizes the wake; otherwise the link remains sleeping."

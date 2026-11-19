PHASE 12 - TRUE SDN / RYU / OPENFLOW 1.3
=========================================

IMPORTANT
---------
Phases 1-11 remain unchanged in topology_dynamic_step5.py.
Phase 12 is intentionally a separate topology because the old R1-R6 objects are
Linux routers. Ryu cannot install OpenFlow forwarding rules into Linux router
namespaces. In Phase 12, R1-R6 are OVS/OpenFlow datapaths (DPID 1..6), which
makes the backbone forwarding plane genuinely controller-programmable.

What is preserved
-----------------
- 12 hosts and original 192.168.1.0/24 ... 192.168.6.0/24 addressing
- gateway addresses 192.168.X.1 (implemented as proxy-ARP virtual gateways)
- 8 backbone relationships
- four R1->R6 paths:
  P1 R1-R2-R4-R6
  P2 R1-R2-R5-R6
  P3 R1-R3-R4-R6
  P4 R1-R3-R5-R6
- 100 Mbps, 2 ms, queue 1000 backbone links
- utilization -> cost thresholds
- HIGH-priority path cost = sum + 2*max
- hysteresis 3 and hold-down 20 sec
- same five traffic flows available with `traffic 120`

New in Phase 12
---------------
- Ryu controller
- OpenFlow 1.3
- secure-mode OVS datapaths
- table-miss PacketIn
- proxy ARP for virtual gateways
- OFPPortStatsRequest/OFPPortStatsReply monitoring
- link utilization calculated in controller
- RPS path calculation in Ryu
- OFPFlowMod installation when selected R1<->R6 path changes
- deterministic switch/port mapping

INSTALL
-------
Use Python 3 for Ryu. Typical Ubuntu setup:
  sudo apt update
  sudo apt install -y mininet openvswitch-switch python3-pip iperf
  python3 -m pip install ryu

If your distro blocks system pip packages, use a virtual environment for Ryu.

RUN - TERMINAL 1
----------------
cd <this folder>
ryu-manager --ofp-tcp-listen-port 6653 phase12_ryu_controller.py

RUN - TERMINAL 2
----------------
sudo mn -c
sudo python3 phase12_sdn_topology.py

VERIFY
------
mininet> sdnstatus
mininet> h1 ping -c 3 192.168.6.10
mininet> flows r1
mininet> flows r3
mininet> traffic 120

In Terminal 1, Ryu should print:
- Datapath connected: R1 ... R6
- OpenFlow IPv4 routes installed
- RPS current path, best path, costs, decision, switch count
- per-path utilization/cost

OpenFlow proof
--------------
Run:
  mininet> flows r1
You should see OpenFlow13 rules with ipv4_dst matches and output actions.
This is the evidence that forwarding is now programmed with FlowMod rather
than Linux `ip route` updates.

Architecture note
-----------------
The Phase 12 file is a migration/proof stage. It does not yet move the complete
Phase 11 Green sleep/wake and threshold-evaluation experiment into Ryu. First
validate OpenFlow connectivity, port statistics, and dynamic RPS FlowMods.
After that, the Green state can be mapped onto OpenFlow port/link eligibility
without confusing a controller connection with actual SDN forwarding.

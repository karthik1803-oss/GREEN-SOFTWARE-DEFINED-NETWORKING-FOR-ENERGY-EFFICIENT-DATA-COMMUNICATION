#!/usr/bin/env python3
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet, arp, ether_types
import time
from collections import deque

VIRTUAL_GW_MAC='02:00:00:00:00:01'
CAPACITY_MBPS=100.0
POLL=2.0
RPS_INTERVAL=6.0
HYSTERESIS=3.0
HOLD_DOWN=20.0

HOSTS={
 '192.168.1.10':(1,1,'00:00:00:00:01:10'),'192.168.1.11':(1,2,'00:00:00:00:01:11'),
 '192.168.2.10':(2,1,'00:00:00:00:02:10'),'192.168.2.11':(2,2,'00:00:00:00:02:11'),
 '192.168.3.10':(3,1,'00:00:00:00:03:10'),'192.168.3.11':(3,2,'00:00:00:00:03:11'),
 '192.168.4.10':(4,1,'00:00:00:00:04:10'),'192.168.4.11':(4,2,'00:00:00:00:04:11'),
 '192.168.5.10':(5,1,'00:00:00:00:05:10'),'192.168.5.11':(5,2,'00:00:00:00:05:11'),
 '192.168.6.10':(6,1,'00:00:00:00:06:10'),'192.168.6.11':(6,2,'00:00:00:00:06:11')}
GATEWAYS={'192.168.%d.1'%i for i in range(1,7)}

# (switch A, switch B) -> (port on A, port on B)
LINK_PORTS={(1,2):(10,10),(1,3):(11,10),(2,4):(11,10),(2,5):(12,10),
            (3,4):(11,11),(3,5):(12,11),(4,6):(12,10),(5,6):(12,11)}
PATHS=[[1,2,4,6],[1,2,5,6],[1,3,4,6],[1,3,5,6]]

class Phase12RPS(app_manager.RyuApp):
    OFP_VERSIONS=[ofproto_v1_3.OFP_VERSION]

    def __init__(self,*args,**kwargs):
        super(Phase12RPS,self).__init__(*args,**kwargs)
        self.dp={}; self.last={}; self.util={k:0.0 for k in LINK_PORTS}
        self.current_path=None; self.current_cost=None; self.last_switch=0; self.switch_count=0
        self.monitor=hub.spawn(self._monitor)

    @set_ev_cls(ofp_event.EventOFPStateChange,[MAIN_DISPATCHER,DEAD_DISPATCHER])
    def state_change(self,ev):
        dp=ev.datapath
        if ev.state==MAIN_DISPATCHER:
            self.dp[dp.id]=dp; self.logger.info('Datapath connected: R%d',dp.id)
        elif ev.state==DEAD_DISPATCHER:
            self.dp.pop(dp.id,None)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures,CONFIG_DISPATCHER)
    def features(self,ev):
        dp=ev.msg.datapath; p=dp.ofproto_parser; ofp=dp.ofproto
        self._add_flow(dp,0,p.OFPMatch(),[p.OFPActionOutput(ofp.OFPP_CONTROLLER,ofp.OFPCML_NO_BUFFER)])

    def _add_flow(self,dp,priority,match,actions,cookie=0x1200):
        p=dp.ofproto_parser
        inst=[p.OFPInstructionActions(dp.ofproto.OFPIT_APPLY_ACTIONS,actions)]
        dp.send_msg(p.OFPFlowMod(datapath=dp,cookie=cookie,priority=priority,match=match,instructions=inst))

    def _delete_ipv4(self):
        for dp in self.dp.values():
            p=dp.ofproto_parser; ofp=dp.ofproto
            dp.send_msg(p.OFPFlowMod(datapath=dp,cookie=0x1200,cookie_mask=0xffff,
                table_id=ofp.OFPTT_ALL,command=ofp.OFPFC_DELETE,
                out_port=ofp.OFPP_ANY,out_group=ofp.OFPG_ANY,
                match=p.OFPMatch(eth_type=ether_types.ETH_TYPE_IP)))

    def _port_to(self,a,b):
        if (a,b) in LINK_PORTS:return LINK_PORTS[(a,b)][0]
        return LINK_PORTS[(b,a)][1]

    def _shortest(self,src,dst):
        graph={i:set() for i in range(1,7)}
        for a,b in LINK_PORTS: graph[a].add(b);graph[b].add(a)
        q=deque([[src]]); seen={src}
        while q:
            path=q.popleft(); u=path[-1]
            if u==dst:return path
            for v in sorted(graph[u]):
                if v not in seen: seen.add(v);q.append(path+[v])
        return None

    def _install_one(self,src_ip,dst_ip,path):
        dst_sw,dst_port,dst_mac=HOSTS[dst_ip]
        for i,swid in enumerate(path):
            dp=self.dp.get(swid)
            if not dp:return
            p=dp.ofproto_parser
            if i==len(path)-1:
                actions=[p.OFPActionSetField(eth_dst=dst_mac),p.OFPActionOutput(dst_port)]
            else:
                actions=[p.OFPActionOutput(self._port_to(swid,path[i+1]))]
            self._add_flow(dp,100,p.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,ipv4_dst=dst_ip),actions)

    def _install_all_routes(self):
        if len(self.dp)<6:return
        self._delete_ipv4(); hub.sleep(0.05)
        for src_ip,(ss,_,_) in HOSTS.items():
            for dst_ip,(ds,_,_) in HOSTS.items():
                if src_ip==dst_ip:continue
                if ss==ds: path=[ss]
                elif ss==1 and ds==6: path=self.current_path or PATHS[0]
                elif ss==6 and ds==1: path=list(reversed(self.current_path or PATHS[0]))
                else:path=self._shortest(ss,ds)
                self._install_one(src_ip,dst_ip,path)
        self.logger.info('OpenFlow IPv4 routes installed. R1-R6 path=%s',self._pname(self.current_path or PATHS[0]))

    @set_ev_cls(ofp_event.EventOFPPacketIn,MAIN_DISPATCHER)
    def packet_in(self,ev):
        msg=ev.msg; dp=msg.datapath; in_port=msg.match['in_port']; p=packet.Packet(msg.data)
        a=p.get_protocol(arp.arp)
        if not a:return
        if a.opcode!=arp.ARP_REQUEST:return
        if a.dst_ip in GATEWAYS: reply_mac=VIRTUAL_GW_MAC
        elif a.dst_ip in HOSTS: reply_mac=HOSTS[a.dst_ip][2]
        else:return
        e=p.get_protocol(ethernet.ethernet)
        rp=packet.Packet(); rp.add_protocol(ethernet.ethernet(dst=e.src,src=reply_mac,ethertype=ether_types.ETH_TYPE_ARP))
        rp.add_protocol(arp.arp(opcode=arp.ARP_REPLY,src_mac=reply_mac,src_ip=a.dst_ip,dst_mac=a.src_mac,dst_ip=a.src_ip));rp.serialize()
        parser=dp.ofproto_parser
        dp.send_msg(parser.OFPPacketOut(datapath=dp,buffer_id=dp.ofproto.OFP_NO_BUFFER,in_port=dp.ofproto.OFPP_CONTROLLER,
                    actions=[parser.OFPActionOutput(in_port)],data=rp.data))

    def _monitor(self):
        while True:
            if len(self.dp)==6:
                for dp in list(self.dp.values()):
                    p=dp.ofproto_parser
                    dp.send_msg(p.OFPPortStatsRequest(dp,0,dp.ofproto.OFPP_ANY))
                if self.current_path is None:
                    self.current_path=PATHS[0];self.current_cost=self._path_cost(self.current_path);self.switch_count=1;self.last_switch=time.time();self._install_all_routes()
                self._rps()
            hub.sleep(POLL)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply,MAIN_DISPATCHER)
    def stats(self,ev):
        now=time.time(); dpid=ev.msg.datapath.id
        for st in ev.msg.body:
            key=(dpid,st.port_no); total=st.tx_bytes+st.rx_bytes
            if key in self.last:
                old,t0=self.last[key]; dt=max(now-t0,0.001)
                mbps=max(0,total-old)*8.0/dt/1e6
                for link,(pa,pb) in LINK_PORTS.items():
                    a,b=link
                    if (dpid==a and st.port_no==pa) or (dpid==b and st.port_no==pb):
                        self.util[link]=min(100.0,mbps/CAPACITY_MBPS*100.0)
            self.last[key]=(total,now)

    def _link_util(self,a,b): return self.util.get((a,b),self.util.get((b,a),0.0))
    def _link_cost(self,u):
        if u<=10:return 1
        if u<=30:return 2
        if u<=50:return 4
        if u<=70:return 6
        if u<=90:return 8
        return 10
    def _path_cost(self,path):
        costs=[self._link_cost(self._link_util(path[i],path[i+1])) for i in range(len(path)-1)]
        # Phase 12 starts with HIGH-priority R1-R6 RPS semantics from Phases 5-7.
        return sum(costs)+2*max(costs)
    def _pname(self,p): return ' -> '.join('R%d'%x for x in p)

    def _rps(self):
        # Run only roughly every RPS_INTERVAL, while stats are polled faster.
        now=time.time()
        if not hasattr(self,'last_rps'):self.last_rps=0
        if now-self.last_rps<RPS_INTERVAL:return
        self.last_rps=now
        vals=[(self._path_cost(p),p) for p in PATHS]; vals.sort(key=lambda x:PATHS.index(x[1]))
        best_cost,best=min(vals,key=lambda x:x[0]); cur=self._path_cost(self.current_path)
        decision='KEEP'
        if best!=self.current_path and cur-best_cost>=HYSTERESIS:
            if now-self.last_switch>=HOLD_DOWN:
                self.current_path=list(best);self.current_cost=best_cost;self.last_switch=now;self.switch_count+=1;decision='SWITCH';self._install_all_routes()
            else:decision='KEEP-HOLD-DOWN'
        elif best!=self.current_path:decision='KEEP-HYSTERESIS'
        self.logger.info('RPS | %s cost=%.1f | best=%s cost=%.1f | %s | switches=%d',
                         self._pname(self.current_path),cur,self._pname(best),best_cost,decision,self.switch_count)
        for pth in PATHS:
            us=[self._link_util(pth[i],pth[i+1]) for i in range(3)]
            self.logger.info('  %s util=%s cost=%.1f',self._pname(pth),'/'.join('%.1f%%'%u for u in us),self._path_cost(pth))

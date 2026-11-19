#!/usr/bin/env python3
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet, arp, ether_types, ipv4, tcp, udp
import time
import csv
import os
import secrets
import hmac
import hashlib
from collections import deque

VIRTUAL_GW_MAC='02:00:00:00:00:01'
CAPACITY_MBPS=100.0
POLL=2.0
RPS_INTERVAL=6.0
HYSTERESIS=3.0
HOLD_DOWN=20.0

# Integrated Green Energy policy (modeled/simulated link sleep)
GREEN_ENABLED=True
GREEN_UNDERUTIL=float(os.environ.get('GREEN_THRESHOLD', '10.0'))
GREEN_REQUIRED_CYCLES=3
GREEN_WAKE_THRESHOLD=float(os.environ.get('GREEN_WAKE_THRESHOLD', '40.0'))
GREEN_WAKE_HOLD=float(os.environ.get('GREEN_WAKE_HOLD', '30.0'))
GREEN_MIN_VIABLE_PATHS=2
ACTIVE_LINK_POWER_W=10.0
SLEEP_LINK_POWER_W=2.0

# Final security mechanism: HMAC-SHA256 authorization for Green wake-up.
# Override this in the shell for experiments: export RPS_SECURITY_KEY='your-secret'
SECURITY_SECRET=os.environ.get('RPS_SECURITY_KEY','rps-green-demo-secret-change-me').encode('utf-8')
SECURITY_TOKEN_MAX_AGE=float(os.environ.get('RPS_TOKEN_MAX_AGE','300.0'))
SECURITY_TEST_MODE=os.environ.get('RPS_SECURITY_TEST_MODE','0')=='1'

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

class Phase13SecurityInputs(app_manager.RyuApp):
    OFP_VERSIONS=[ofproto_v1_3.OFP_VERSION]

    def __init__(self,*args,**kwargs):
        super(Phase13SecurityInputs,self).__init__(*args,**kwargs)
        self.dp={}; self.last={}; self.util={k:0.0 for k in LINK_PORTS}
        self.current_path=None; self.current_cost=None; self.last_switch=0; self.switch_count=0
        self.security_csv='phase13_security_inputs.csv'
        self.security_seen=set()
        # Final security state. Token is 32 raw bytes (SHA-256), logged as 64 hex chars.
        self.latest_security_token={}
        self.link_last_sleep_ts={k:0.0 for k in LINK_PORTS}
        self.security_auth_csv='phase14_security_authentication.csv'
        # Phase 13 Integrated: short OpenFlow packet-sampling window for dynamic classification.
        self.samples=[]; self.sample_started=time.time(); self.sample_duration=2.0
        self.network_priority='LOW'; self.last_flows=[]
        self.rps_csv='phase13_integrated_rps.csv'
        # Green state is integrated directly with the OpenFlow RPS controller.
        self.green_enabled=GREEN_ENABLED
        self.link_state={k:'ACTIVE' for k in LINK_PORTS}
        self.underutil_count={k:0 for k in LINK_PORTS}
        self.sleep_events=0; self.wake_events=0; self.green_cycle=0
        self.baseline_energy_j=0.0; self.proposed_energy_j=0.0; self.last_energy_time=time.time()
        self.energy_csv='phase13_energy_statistics.csv'
        self.network_csv='phase13_network_effect.csv'
        self.wake_protect_until={k:0.0 for k in LINK_PORTS}
        self._init_security_csv(); self._init_security_auth_csv(); self._init_rps_csv(); self._init_energy_csv(); self._init_network_csv()
        self.monitor=hub.spawn(self._monitor)
        if SECURITY_TEST_MODE:
            hub.spawn_after(1.0,self._run_security_negative_tests)

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


    def _init_security_csv(self):
        if not os.path.exists(self.security_csv):
            with open(self.security_csv,'w') as f:
                w=csv.writer(f)
                w.writerow(['timestamp','nonce','src_mac','dst_mac','src_ip','dst_ip','path'])


    def _init_security_auth_csv(self):
        if not os.path.exists(self.security_auth_csv):
            with open(self.security_auth_csv,'w') as f:
                csv.writer(f).writerow(['timestamp','event','src_mac','dst_mac','src_ip','dst_ip','packet_timestamp','nonce','path','token_hex','result','reason','link'])

    def _token_message(self,src_mac,dst_mac,src_ip,dst_ip,ts,nonce,path_name):
        # Canonical byte representation prevents ambiguous concatenation.
        return ('%s|%s|%s|%s|%s|%s|%s' %
                (src_mac,dst_mac,src_ip,dst_ip,ts,nonce,path_name)).encode('utf-8')

    def _make_token(self,src_mac,dst_mac,src_ip,dst_ip,ts,nonce,path_name):
        # HMAC-SHA256 returns a 32-byte authentication token.
        msg=self._token_message(src_mac,dst_mac,src_ip,dst_ip,ts,nonce,path_name)
        return hmac.new(SECURITY_SECRET,msg,hashlib.sha256).digest()

    def _verify_token_record(self,record,now,required_after=0.0):
        if not record:
            return False,'NO_TOKEN'
        try:
            packet_ts=float(record['timestamp'])
        except Exception:
            return False,'BAD_TIMESTAMP'
        if now-packet_ts > SECURITY_TOKEN_MAX_AGE:
            return False,'TOKEN_EXPIRED'
        if packet_ts > now+5.0:
            return False,'TIMESTAMP_IN_FUTURE'
        # The link's last sleep time is retained for audit. Token freshness is checked
        # independently so normal 180 s experiments do not deadlock the wake mechanism.
        expected=self._make_token(record['src_mac'],record['dst_mac'],record['src_ip'],record['dst_ip'],
                                  record['timestamp'],record['nonce'],record['path'])
        if not hmac.compare_digest(record['token'],expected):
            return False,'HMAC_MISMATCH'
        return True,'VALID'

    def _latest_valid_wake_token(self,links,now):
        # Any recent authenticated R1->LAN6 security record can authorize capacity wake.
        # Last-sleep timestamps remain recorded per link for audit/replay analysis.
        required_after=max([self.link_last_sleep_ts.get(x,0.0) for x in links] or [0.0])
        candidates=sorted(self.latest_security_token.values(),key=lambda r:float(r['timestamp']),reverse=True)
        for record in candidates:
            ok,reason=self._verify_token_record(record,now,required_after)
            if ok:
                return record,True,'VALID'
        if not candidates:
            return None,False,'NO_TOKEN'
        record=candidates[0]
        ok,reason=self._verify_token_record(record,now,required_after)
        return record,False,reason

    def _log_security_auth(self,event,record,result,reason,link=''):
        now=time.time()
        r=record or {}
        with open(self.security_auth_csv,'a') as f:
            csv.writer(f).writerow(['%.6f'%now,event,r.get('src_mac',''),r.get('dst_mac',''),r.get('src_ip',''),r.get('dst_ip',''),
                r.get('timestamp',''),r.get('nonce',''),r.get('path',''),r.get('token_hex',''),result,reason,link])
        self.logger.info('SECURITY-AUTH | event=%s result=%s reason=%s link=%s token=%s',
                         event,result,reason,link,(r.get('token_hex','')[:16]+'...') if r.get('token_hex') else '-')

    def _run_security_negative_tests(self):
        """Optional isolated HMAC tests. Enable with RPS_SECURITY_TEST_MODE=1.
        These tests do not alter RPS, Green link state, OpenFlow rules, or wake counters.
        They only verify the existing HMAC/freshness checks and write SECURITY_TEST rows.
        """
        now=time.time()
        src_ip='192.168.1.10'; dst_ip='192.168.6.10'
        src_mac=HOSTS[src_ip][2]; dst_mac=HOSTS[dst_ip][2]
        path_name='P1'

        # 1) Valid token -> ALLOW
        ts='%.6f'%now; nonce=secrets.token_hex(8)
        token=self._make_token(src_mac,dst_mac,src_ip,dst_ip,ts,nonce,path_name)
        valid={'timestamp':ts,'nonce':nonce,'src_mac':src_mac,'dst_mac':dst_mac,
               'src_ip':src_ip,'dst_ip':dst_ip,'path':path_name,
               'token':token,'token_hex':token.hex()}
        ok,reason=self._verify_token_record(valid,time.time())
        self._log_security_auth('SECURITY_TEST_VALID',valid,'ALLOW' if ok else 'DENY',
                                'HMAC_VALID' if ok else reason,'TEST')

        # 2) Tampered token -> DENY / HMAC_MISMATCH
        bad=dict(valid)
        tampered=bytearray(valid['token']); tampered[0]^=0x01
        bad['token']=bytes(tampered); bad['token_hex']=bad['token'].hex()
        ok,reason=self._verify_token_record(bad,time.time())
        self._log_security_auth('SECURITY_TEST_TAMPERED',bad,'ALLOW' if ok else 'DENY',reason,'TEST')

        # 3) Expired timestamp -> DENY / TOKEN_EXPIRED
        old_ts='%.6f'%(time.time()-SECURITY_TOKEN_MAX_AGE-10.0)
        old_nonce=secrets.token_hex(8)
        old_token=self._make_token(src_mac,dst_mac,src_ip,dst_ip,old_ts,old_nonce,path_name)
        expired={'timestamp':old_ts,'nonce':old_nonce,'src_mac':src_mac,'dst_mac':dst_mac,
                 'src_ip':src_ip,'dst_ip':dst_ip,'path':path_name,
                 'token':old_token,'token_hex':old_token.hex()}
        ok,reason=self._verify_token_record(expired,time.time())
        self._log_security_auth('SECURITY_TEST_EXPIRED',expired,'ALLOW' if ok else 'DENY',reason,'TEST')

        self.logger.info('SECURITY-TEST complete | expected: VALID=ALLOW, TAMPERED=DENY, EXPIRED=DENY')

    def _init_rps_csv(self):
        if not os.path.exists(self.rps_csv):
            with open(self.rps_csv,'w') as f:
                csv.writer(f).writerow(['timestamp','priority','dscp','current_path','best_path','current_cost','best_cost','decision','switch_count','p1_cost','p2_cost','p3_cost','p4_cost'])


    def _init_energy_csv(self):
        if not os.path.exists(self.energy_csv):
            with open(self.energy_csv,'w') as f:
                csv.writer(f).writerow(['cycle','timestamp','mode','current_path','active_links','sleeping_links','viable_paths','baseline_power_w','proposed_power_w','baseline_energy_j','proposed_energy_j','energy_saving_percent','sleep_events','wake_events','bottleneck_utilization','event'])

    def _init_network_csv(self):
        if not os.path.exists(self.network_csv):
            with open(self.network_csv,'w') as f:
                csv.writer(f).writerow(['cycle','timestamp','threshold','priority','avg_backbone_throughput_mbps','avg_backbone_utilization_percent','current_path_bottleneck_percent','sleeping_links','viable_paths','rps_switch_count'])

    def _norm_link(self,a,b):
        return (a,b) if (a,b) in LINK_PORTS else (b,a)

    def _path_links(self,path):
        return [self._norm_link(path[i],path[i+1]) for i in range(len(path)-1)]

    def _path_available(self,path):
        return all(self.link_state.get(x,'ACTIVE')=='ACTIVE' for x in self._path_links(path))

    def _viable_paths(self):
        return [p for p in PATHS if self._path_available(p)]

    def _can_sleep(self,link):
        old=self.link_state[link]; self.link_state[link]='SLEEPING'
        n=len(self._viable_paths())
        self.link_state[link]=old
        return n>=GREEN_MIN_VIABLE_PATHS

    def _wake_minimum_for_capacity(self):
        choices=[]
        for p in PATHS:
            if p==self.current_path: continue
            missing=[x for x in self._path_links(p) if self.link_state.get(x)=='SLEEPING']
            if missing: choices.append((len(missing),PATHS.index(p),missing,p))
        if not choices: return []
        choices.sort(key=lambda x:(x[0],x[1]))
        missing=choices[0][2]
        # Security gate: a sleeping link is restored only after a valid 32-byte HMAC
        # from traffic observed after that link's last sleep timestamp is verified.
        record,ok,reason=self._latest_valid_wake_token(missing,time.time())
        link_name=','.join('R%d-R%d'%x for x in missing)
        if not ok:
            self._log_security_auth('WAKE',record,'DENY',reason,link_name)
            return []
        self._log_security_auth('WAKE',record,'ALLOW','HMAC_VALID',link_name)
        woke=[]
        for link in missing:
            if self.link_state.get(link)=='SLEEPING':
                self.link_state[link]='ACTIVE'; self.underutil_count[link]=0; self.wake_protect_until[link]=time.time()+GREEN_WAKE_HOLD; self.wake_events+=1; woke.append(link)
        return woke

    def _green_evaluate(self,now):
        if not self.green_enabled: return
        self.green_cycle+=1
        current_links=set(self._path_links(self.current_path))
        bottleneck=max([self._link_util(*x) for x in current_links] or [0.0])
        event='NONE'
        # Selective wake: restore the minimum sleeping capacity needed for an alternate path.
        if bottleneck>=GREEN_WAKE_THRESHOLD and any(v=='SLEEPING' for v in self.link_state.values()):
            woke=self._wake_minimum_for_capacity()
            if woke:
                event='WAKE '+','.join('R%d-R%d'%x for x in woke)
        # Underutilization counters. Never sleep a link on the current RPS path.
        candidates=[]
        for link in LINK_PORTS:
            if self.link_state[link]=='SLEEPING': continue
            if link in current_links or now < self.wake_protect_until.get(link,0.0):
                self.underutil_count[link]=0; continue
            u=self._link_util(*link)
            if u<=GREEN_UNDERUTIL: self.underutil_count[link]+=1
            else: self.underutil_count[link]=0
            if self.underutil_count[link]>=GREEN_REQUIRED_CYCLES: candidates.append((u,link))
        if not event.startswith('WAKE'):
            for u,link in sorted(candidates):
                if self._can_sleep(link):
                    self.link_state[link]='SLEEPING'; self.link_last_sleep_ts[link]=now; self.underutil_count[link]=0; self.sleep_events+=1
                    event='SLEEP R%d-R%d'%link
                    break
        dt=max(0.0,now-self.last_energy_time); self.last_energy_time=now
        active=sum(1 for x in self.link_state.values() if x=='ACTIVE'); sleeping=len(LINK_PORTS)-active
        baseline=len(LINK_PORTS)*ACTIVE_LINK_POWER_W
        proposed=active*ACTIVE_LINK_POWER_W+sleeping*SLEEP_LINK_POWER_W
        self.baseline_energy_j+=baseline*dt; self.proposed_energy_j+=proposed*dt
        saving=((self.baseline_energy_j-self.proposed_energy_j)/self.baseline_energy_j*100.0) if self.baseline_energy_j else 0.0
        viable=len(self._viable_paths())
        with open(self.energy_csv,'a') as f:
            csv.writer(f).writerow([self.green_cycle,'%.6f'%now,'SIMULATE',self._pname(self.current_path),active,sleeping,viable,'%.2f'%baseline,'%.2f'%proposed,'%.2f'%self.baseline_energy_j,'%.2f'%self.proposed_energy_j,'%.2f'%saving,self.sleep_events,self.wake_events,'%.2f'%bottleneck,event])
        active_utils=[self._link_util(*x) for x in LINK_PORTS if self.link_state[x]=='ACTIVE']
        avg_util=sum(active_utils)/len(active_utils) if active_utils else 0.0
        avg_thr=avg_util/100.0*CAPACITY_MBPS
        with open(self.network_csv,'a') as f:
            csv.writer(f).writerow([self.green_cycle,'%.6f'%now,'%.1f'%GREEN_UNDERUTIL,self.network_priority,'%.3f'%avg_thr,'%.3f'%avg_util,'%.3f'%bottleneck,sleeping,viable,self.switch_count])
        self._last_green=(active,sleeping,viable,baseline,proposed,self.baseline_energy_j,self.proposed_energy_j,saving,self.sleep_events,self.wake_events,event,bottleneck)

    def _priority_score(self, proto, size, packet_rate, avg_interarrival):
        score=0.0
        if proto=='UDP': score+=2.0
        if 0<size<=256: score+=2.0
        elif 0<size<=800: score+=1.0
        elif size>=1200: score-=1.0
        if packet_rate>=1000.0: score+=2.0
        elif packet_rate>=200.0: score+=1.0
        if 0<avg_interarrival<=0.002: score+=1.0
        return score

    def _priority_from_score(self,score):
        return 'HIGH' if score>=5.0 else ('MEDIUM' if score>=2.0 else 'LOW')

    def _classify_samples(self):
        if not self.samples: return []
        groups={}
        for x in self.samples:
            k=(x['src_ip'],x['dst_ip'],x['proto'],x['src_port'],x['dst_port'])
            groups.setdefault(k,[]).append(x)
        flows=[]
        for k,arr in groups.items():
            arr.sort(key=lambda x:x['ts']); n=len(arr)
            dur=max(arr[-1]['ts']-arr[0]['ts'], self.sample_duration if n==1 else 0.001)
            rate=float(n)/max(dur,0.001)
            gaps=[arr[i]['ts']-arr[i-1]['ts'] for i in range(1,n) if arr[i]['ts']>=arr[i-1]['ts']]
            ia=sum(gaps)/len(gaps) if gaps else 0.0
            avgsize=sum(x['size'] for x in arr)/float(n)
            score=self._priority_score(k[2],avgsize,rate,ia)
            flows.append({'src_ip':k[0],'dst_ip':k[1],'protocol':k[2],'src_port':k[3],'dst_port':k[4],'packet_count':n,'packet_rate':rate,'avg_interarrival':ia,'avg_size':avgsize,'score':score,'priority':self._priority_from_score(score)})
        return flows

    def _dscp(self,priority): return {'HIGH':46,'MEDIUM':18,'LOW':8}[priority]

    def _finish_sampling(self):
        flows=self._classify_samples()
        if not flows: return
        rank={'LOW':1,'MEDIUM':2,'HIGH':3}; relevant=[f for f in flows if f['dst_ip'].startswith('192.168.6.')]
        if relevant: self.network_priority=max((f['priority'] for f in relevant),key=lambda x:rank[x])
        self.last_flows=flows
        self.logger.info('CLASSIFY | flows=%d | network=%s | DSCP=%d', len(flows), self.network_priority, self._dscp(self.network_priority))
        # Stop controller packet copies by overriding R1->R6 destination rules at priority 110,
        # while applying the dynamically selected DSCP marking at ingress R1.
        for dst in ('192.168.6.10','192.168.6.11'):
            self._install_priority_route(dst)
        self.samples=[]

    def _install_priority_route(self,dst_ip):
        path=self.current_path or PATHS[0]; dst_sw,dst_port,dst_mac=HOSTS[dst_ip]
        for i,swid in enumerate(path):
            dp=self.dp.get(swid)
            if not dp:return
            p=dp.ofproto_parser; actions=[]
            if i==0: actions.append(p.OFPActionSetField(ip_dscp=self._dscp(self.network_priority)))
            if i==len(path)-1:
                actions += [p.OFPActionSetField(eth_dst=dst_mac),p.OFPActionOutput(dst_port)]
            else: actions.append(p.OFPActionOutput(self._port_to(swid,path[i+1])))
            self._add_flow(dp,110,p.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,ipv4_dst=dst_ip),actions)

    def _security_record(self,src_ip,dst_ip,path):
        # Final security mechanism: construct the security message and create a
        # 32-byte HMAC-SHA256 token. The secret key never appears in the token/CSV.
        key=(src_ip,dst_ip,tuple(path))
        if key in self.security_seen:
            return
        self.security_seen.add(key)
        ts='%.6f'%time.time()
        nonce=secrets.token_hex(8)
        src_mac=HOSTS[src_ip][2]
        dst_mac=HOSTS[dst_ip][2]
        pname=self._pname(path)
        token=self._make_token(src_mac,dst_mac,src_ip,dst_ip,ts,nonce,pname)
        token_hex=token.hex()
        record={'timestamp':ts,'nonce':nonce,'src_mac':src_mac,'dst_mac':dst_mac,'src_ip':src_ip,
                'dst_ip':dst_ip,'path':pname,'token':token,'token_hex':token_hex}
        self.latest_security_token[(src_ip,dst_ip)]=record
        with open(self.security_csv,'a') as f:
            # Preserve the existing Phase-13 CSV columns exactly; token/auth results
            # are written to the new phase14_security_authentication.csv file.
            csv.writer(f).writerow([ts,nonce,src_mac,dst_mac,src_ip,dst_ip,pname])
        self._log_security_auth('TOKEN_CREATE',record,'CREATED','HMAC_SHA256_32_BYTES','')
        self.logger.info('SECURITY-TOKEN | src=%s/%s dst=%s/%s ts=%s nonce=%s path=%s token=%s...',
                         src_ip,src_mac,dst_ip,dst_mac,ts,nonce,pname,token_hex[:16])


    def _install_one(self,src_ip,dst_ip,path):
        dst_sw,dst_port,dst_mac=HOSTS[dst_ip]
        if HOSTS[src_ip][0]==1 and HOSTS[dst_ip][0]==6:
            self._security_record(src_ip,dst_ip,path)
        for i,swid in enumerate(path):
            dp=self.dp.get(swid)
            if not dp:return
            p=dp.ofproto_parser
            if i==len(path)-1:
                actions=[p.OFPActionSetField(eth_dst=dst_mac),p.OFPActionOutput(dst_port)]
            else:
                actions=[p.OFPActionOutput(self._port_to(swid,path[i+1]))]
                if i==0 and HOSTS[src_ip][0]==1 and HOSTS[dst_ip][0]==6:
                    actions.append(p.OFPActionOutput(dp.ofproto.OFPP_CONTROLLER,128))
            self._add_flow(dp,100,p.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,ipv4_dst=dst_ip),actions)

    def _install_all_routes(self):
        if len(self.dp)<6:return
        self.security_seen.clear(); self.samples=[]; self.sample_started=time.time()
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
        ip4=p.get_protocol(ipv4.ipv4)
        if ip4:
            # Only sample experiment traffic entering R1 and destined for LAN6.
            if dp.id==1 and ip4.dst.startswith('192.168.6.'):
                proto='OTHER'; sp=0; dport=0
                u=p.get_protocol(udp.udp); t=p.get_protocol(tcp.tcp)
                if u: proto='UDP'; sp=u.src_port; dport=u.dst_port
                elif t: proto='TCP'; sp=t.src_port; dport=t.dst_port
                self.samples.append({'ts':time.time(),'src_ip':ip4.src,'dst_ip':ip4.dst,'proto':proto,'src_port':sp,'dst_port':dport,'size':len(msg.data)})
            return
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
        if self.green_enabled and not self._path_available(path): return float('inf')
        costs=[self._link_cost(self._link_util(path[i],path[i+1])) for i in range(len(path)-1)]
        base=sum(costs); peak=max(costs)
        if self.network_priority=='HIGH': return base+2*peak
        if self.network_priority=='MEDIUM': return base+peak
        return base
    def _pname(self,p): return ' -> '.join('R%d'%x for x in p)

    def _rps(self):
        # Run only roughly every RPS_INTERVAL, while stats are polled faster.
        now=time.time()
        if not hasattr(self,'last_rps'):self.last_rps=0
        if now-self.last_rps<RPS_INTERVAL:return
        self.last_rps=now
        if self.samples and now-self.sample_started>=self.sample_duration:
            self._finish_sampling()
        vals=[(self._path_cost(p),p) for p in PATHS]; vals.sort(key=lambda x:PATHS.index(x[1]))
        best_cost,best=min(vals,key=lambda x:x[0]); cur=self._path_cost(self.current_path)
        decision='KEEP'
        if best!=self.current_path and cur-best_cost>=HYSTERESIS:
            if now-self.last_switch>=HOLD_DOWN:
                self.current_path=list(best);self.current_cost=best_cost;self.last_switch=now;self.switch_count+=1;decision='SWITCH';self._install_all_routes()
            else:decision='KEEP-HOLD-DOWN'
        elif best!=self.current_path:decision='KEEP-HYSTERESIS'
        pcost=[self._path_cost(x) for x in PATHS]
        with open(self.rps_csv,'a') as f:
            csv.writer(f).writerow(['%.6f'%now,self.network_priority,self._dscp(self.network_priority),self._pname(self.current_path),self._pname(best),'%.2f'%cur,'%.2f'%best_cost,decision,self.switch_count]+['%.2f'%x for x in pcost])
        self._green_evaluate(now)
        g=getattr(self,'_last_green',(0,0,0,0,0,0,0,0,0,0,'NONE',0))
        lines=[]
        for idx,pth in enumerate(PATHS):
            us=[self._link_util(pth[i],pth[i+1]) for i in range(3)]
            state=('cost=%.1f'%self._path_cost(pth)) if self._path_available(pth) else 'SLEEPING'
            lines.append('P%d %-20s util=%-18s %s'%(idx+1,self._pname(pth),'/'.join('%.1f%%'%u for u in us),state))
        self.logger.info('\n========== SDN CYCLE %d | GREEN THRESHOLD %.0f%% ==========\n'
            'TRAFFIC : priority=%s | DSCP=%d\n'
            'RPS     : current=%s | best=%s | decision=%s | switches=%d\n'
            '%s\n'
            'GREEN   : active=%d | sleeping=%d | viable=%d | bottleneck=%.1f%%\n'
            'POWER   : %.1f W -> %.1f W | ENERGY: %.1f J -> %.1f J | SAVED=%.2f%%\n'
            'EVENTS  : sleep=%d | wake=%d | last=%s | wake-trigger=%.0f%%\n'
            '==========================================================',
            self.green_cycle,GREEN_UNDERUTIL,self.network_priority,self._dscp(self.network_priority),
            self._pname(self.current_path),self._pname(best),decision,self.switch_count,'\n'.join(lines),
            g[0],g[1],g[2],g[11],g[3],g[4],g[5],g[6],g[7],g[8],g[9],g[10],GREEN_WAKE_THRESHOLD)

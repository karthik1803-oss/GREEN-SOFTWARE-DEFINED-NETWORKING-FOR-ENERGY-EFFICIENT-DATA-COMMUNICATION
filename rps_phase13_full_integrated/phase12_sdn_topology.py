#!/usr/bin/env python3
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
import os
import time
import csv
import re
import threading

BW=100
DELAY='2ms'

HOSTS = {
 'h1':('192.168.1.10/24','192.168.1.1','00:00:00:00:01:10','r1',1),
 'h2':('192.168.1.11/24','192.168.1.1','00:00:00:00:01:11','r1',2),
 'h3':('192.168.2.10/24','192.168.2.1','00:00:00:00:02:10','r2',1),
 'h4':('192.168.2.11/24','192.168.2.1','00:00:00:00:02:11','r2',2),
 'h5':('192.168.3.10/24','192.168.3.1','00:00:00:00:03:10','r3',1),
 'h6':('192.168.3.11/24','192.168.3.1','00:00:00:00:03:11','r3',2),
 'h7':('192.168.4.10/24','192.168.4.1','00:00:00:00:04:10','r4',1),
 'h8':('192.168.4.11/24','192.168.4.1','00:00:00:00:04:11','r4',2),
 'h9':('192.168.5.10/24','192.168.5.1','00:00:00:00:05:10','r5',1),
 'h10':('192.168.5.11/24','192.168.5.1','00:00:00:00:05:11','r5',2),
 'h11':('192.168.6.10/24','192.168.6.1','00:00:00:00:06:10','r6',1),
 'h12':('192.168.6.11/24','192.168.6.1','00:00:00:00:06:11','r6',2),
}

def _tcp_retrans(host):
    out=host.cmd("cat /proc/net/snmp | grep '^Tcp:' | tail -2")
    lines=[x.split() for x in out.strip().splitlines() if x.startswith('Tcp:')]
    if len(lines)<2: return 0
    try:
        hdr=lines[0][1:]; val=lines[1][1:]
        return int(val[hdr.index('RetransSegs')])
    except: return 0

def _performance_monitor(net, duration, stop_event):
    path='phase13_end_to_end_metrics.csv'
    fresh=not os.path.exists(path)
    f=open(path,'a')
    w=csv.writer(f)
    if fresh: w.writerow(['elapsed_sec','timestamp','latency_ms','jitter_proxy_ms','packet_loss_percent','tcp_retransmissions_interval','tcp_retransmissions_cumulative'])
    f.flush()
    start=time.time(); last_retrans=_tcp_retrans(net.get('h2'))+_tcp_retrans(net.get('h5'))
    # Give iperf a few seconds to establish before first sample.
    time.sleep(5)
    while not stop_event.is_set() and time.time()-start < duration:
        h1=net.get('h1')
        out=h1.cmd('ping -c 5 -W 1 192.168.6.10')
        loss=100.0; lat=0.0; jit=0.0
        m=re.search(r'(\d+(?:\.\d+)?)% packet loss',out)
        if m: loss=float(m.group(1))
        m=re.search(r'=\s*[\d.]+/([\d.]+)/[\d.]+/([\d.]+)',out)
        if m: lat=float(m.group(1)); jit=float(m.group(2))
        cur=_tcp_retrans(net.get('h2'))+_tcp_retrans(net.get('h5'))
        delta=max(0,cur-last_retrans); last_retrans=cur
        w.writerow(['%.1f'%(time.time()-start),'%.6f'%time.time(),'%.3f'%lat,'%.3f'%jit,'%.3f'%loss,delta,cur]); f.flush()
        for _ in range(10):
            if stop_event.is_set(): break
            time.sleep(1)
    f.close()

class Phase12CLI(CLI):
    def __init__(self,*args,**kwargs):
        self.perf_stop=threading.Event(); self.perf_thread=None
        CLI.__init__(self,*args,**kwargs)

    def do_sdnstatus(self, _line):
        print('\n=== PHASE 12 SDN STATUS ===')
        for s in self.mn.switches:
            out=s.cmd('ovs-vsctl get-controller %s' % s.name).strip()
            print('%s controller: %s' % (s.name, out or 'NONE'))
        print('Use: flows [r1..r6], traffic [seconds], stoptraffic')

    def do_flows(self, line):
        name=line.strip() or 'r1'
        if name not in [s.name for s in self.mn.switches]:
            print('Usage: flows r1   (r1..r6)')
            return
        print(self.mn.get(name).cmd('ovs-ofctl -O OpenFlow13 dump-flows %s' % name))

    def do_traffic(self, line):
        try: duration=int(line.strip() or '120')
        except: duration=120
        self.do_stoptraffic('')
        for h,p in [('h11',5001),('h9',5002),('h12',5003),('h8',5004),('h10',5005)]:
            self.mn.get(h).cmd('iperf -s -p %d > /tmp/%s_p%d.log 2>&1 &'%(p,h,p))
        self.mn.get('h1').cmd('iperf -c 192.168.6.10 -u -b 8M -l 160 -p 5001 -t %d >/tmp/p12_h1.log 2>&1 &'%duration)
        self.mn.get('h2').cmd('iperf -c 192.168.5.10 -p 5002 -t %d >/tmp/p12_h2.log 2>&1 &'%duration)
        self.mn.get('h3').cmd('iperf -c 192.168.6.11 -u -b 2M -l 700 -p 5003 -t %d >/tmp/p12_h3.log 2>&1 &'%duration)
        self.mn.get('h5').cmd('iperf -c 192.168.4.11 -p 5004 -t %d >/tmp/p12_h5.log 2>&1 &'%duration)
        self.mn.get('h6').cmd('iperf -c 192.168.5.11 -u -b 1M -l 1000 -p 5005 -t %d >/tmp/p12_h6.log 2>&1 &'%duration)
        self.perf_stop.clear()
        self.perf_thread=threading.Thread(target=_performance_monitor,args=(self.mn,duration,self.perf_stop))
        self.perf_thread.daemon=True; self.perf_thread.start()
        print('Integrated traffic + end-to-end performance monitoring started for %d seconds.'%duration)

    def do_stoptraffic(self, _line):
        if hasattr(self,'perf_stop'): self.perf_stop.set()
        for h in self.mn.hosts:
            h.cmd('pkill -f iperf >/dev/null 2>&1 || true')
        print('iperf traffic stopped.')


def run():
    net=Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=False)
    c0=net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    sw={}
    for i in range(1,7):
        sw['r%d'%i]=net.addSwitch('r%d'%i, dpid='%016x'%i, protocols='OpenFlow13', failMode='secure')
    hs={}
    for name,(ip,gw,mac,sname,port) in HOSTS.items():
        hs[name]=net.addHost(name, ip=ip, mac=mac, defaultRoute='via %s'%gw)
        net.addLink(hs[name], sw[sname], port2=port)

    opt=dict(bw=BW,delay=DELAY,max_queue_size=1000,use_htb=True)
    # Explicit OpenFlow ports: stable mapping shared with the Ryu app.
    net.addLink(sw['r1'],sw['r2'],port1=10,port2=10,**opt)
    net.addLink(sw['r1'],sw['r3'],port1=11,port2=10,**opt)
    net.addLink(sw['r2'],sw['r4'],port1=11,port2=10,**opt)
    net.addLink(sw['r2'],sw['r5'],port1=12,port2=10,**opt)
    net.addLink(sw['r3'],sw['r4'],port1=11,port2=11,**opt)
    net.addLink(sw['r3'],sw['r5'],port1=12,port2=11,**opt)
    net.addLink(sw['r4'],sw['r6'],port1=12,port2=10,**opt)
    net.addLink(sw['r5'],sw['r6'],port1=12,port2=11,**opt)

    net.start()
    for s in sw.values():
        s.cmd('ovs-vsctl set bridge %s protocols=OpenFlow13'%s.name)
        s.cmd('ovs-vsctl set-fail-mode %s secure'%s.name)
    print('\n*** Phase 12 topology ready')
    print('*** R1-R6 are now OpenFlow datapaths (DPID 1..6), not Linux routers.')
    print('*** Controller: tcp:127.0.0.1:6653')
    print('*** Test: h1 ping -c 3 192.168.6.10')
    print('*** Inspect: flows r1   |   sdnstatus   |   traffic 120')
    Phase12CLI(net)
    net.stop()

if __name__=='__main__':
    setLogLevel('info')
    run()

#!/usr/bin/env python3
import csv, os, math
import matplotlib.pyplot as plt
GREEN='threshold_green_graphs'; NET='threshold_network_effect_graphs'
os.makedirs(GREEN,exist_ok=True); os.makedirs(NET,exist_ok=True)
ths=[5,10,15,20]; data=[]
def rows(path):
    if not os.path.exists(path): return []
    with open(path,newline='') as f: return list(csv.DictReader(f))
def avg(rs,key):
    vals=[]
    for r in rs:
        try: vals.append(float(r[key]))
        except: pass
    return sum(vals)/len(vals) if vals else 0.0
for t in ths:
    root='threshold_results/%d'%t
    er=rows(root+'/phase13_energy_statistics.csv'); rr=rows(root+'/phase13_integrated_rps.csv')
    nr=rows(root+'/phase13_network_effect.csv'); pr=rows(root+'/phase13_end_to_end_metrics.csv')
    if not er: continue
    z=er[-1]
    data.append({'threshold':t,'saving':float(z['energy_saving_percent']),'active':int(z['active_links']),
      'sleeping':int(z['sleeping_links']),'viable':int(z['viable_paths']),'sleep_events':int(z['sleep_events']),
      'wake_events':int(z['wake_events']),'switches':int(rr[-1]['switch_count']) if rr else 0,
      'baseline_energy':float(z['baseline_energy_j']),'proposed_energy':float(z['proposed_energy_j']),
      'throughput':avg(nr,'avg_backbone_throughput_mbps'),'utilization':avg(nr,'avg_backbone_utilization_percent'),
      'latency':avg(pr,'latency_ms'),'jitter':avg(pr,'jitter_proxy_ms'),'packet_loss':avg(pr,'packet_loss_percent'),
      'retransmissions':sum(float(x.get('tcp_retransmissions_interval',0) or 0) for x in pr)})
if not data:
    print('No threshold results found. Save threshold runs first.'); raise SystemExit(1)
fields=list(data[0].keys())
with open('phase13_threshold_comparison.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(data)
def bar(folder,key,ylabel,name,title):
    plt.figure(figsize=(8,5)); plt.bar([str(x['threshold'])+'%' for x in data],[x[key] for x in data]); plt.xlabel('Green underutilization threshold'); plt.ylabel(ylabel); plt.title(title); plt.tight_layout(); plt.savefig(os.path.join(folder,name),dpi=180); plt.close()
# Green / routing effect graphs
bar(GREEN,'saving','Cumulative energy saving (%)','threshold_vs_energy_saving.png','Threshold vs energy saving')
bar(GREEN,'sleeping','Sleeping links','threshold_vs_sleeping_links.png','Threshold vs sleeping links')
bar(GREEN,'viable','Viable paths','threshold_vs_viable_paths.png','Threshold vs viable paths')
bar(GREEN,'sleep_events','Sleep events','threshold_vs_sleep_events.png','Threshold vs sleep events')
bar(GREEN,'wake_events','Wake events','threshold_vs_wake_events.png','Threshold vs wake events')
bar(GREEN,'switches','Cumulative RPS switch counter','threshold_vs_rps_switches.png','Threshold vs RPS switches')
plt.figure(figsize=(8,5)); x=[str(z['threshold'])+'%' for z in data]; plt.plot(x,[z['baseline_energy'] for z in data],marker='o',label='Baseline'); plt.plot(x,[z['proposed_energy'] for z in data],marker='o',label='Proposed'); plt.xlabel('Green underutilization threshold'); plt.ylabel('Energy (J)'); plt.title('Threshold energy comparison'); plt.legend(); plt.tight_layout(); plt.savefig(os.path.join(GREEN,'threshold_energy_comparison.png'),dpi=180); plt.close()
# Separate network-effect graphs
bar(NET,'throughput','Average backbone throughput (Mbps)','threshold_vs_throughput.png','Threshold vs average backbone throughput')
bar(NET,'utilization','Average backbone utilization (%)','threshold_vs_utilization.png','Threshold vs average backbone utilization')
bar(NET,'latency','Average RTT (ms)','threshold_vs_latency.png','Threshold vs latency')
bar(NET,'jitter','RTT mdev / jitter proxy (ms)','threshold_vs_jitter_proxy.png','Threshold vs jitter proxy')
bar(NET,'packet_loss','Packet loss (%)','threshold_vs_packet_loss.png','Threshold vs packet loss')
bar(NET,'retransmissions','TCP retransmissions during samples','threshold_vs_tcp_retransmissions.png','Threshold vs TCP retransmissions')
print('Created phase13_threshold_comparison.csv')
print('Green graphs   :',GREEN)
print('Network graphs :',NET)

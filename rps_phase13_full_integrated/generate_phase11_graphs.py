#!/usr/bin/env python3
import csv, os
import matplotlib.pyplot as plt
BASE=os.path.dirname(os.path.abspath(__file__))
CSV=os.path.join(BASE,'phase11_green_performance_comparison.csv')
if not os.path.exists(CSV):
    raise SystemExit('Missing phase11_green_performance_comparison.csv. Run phase11test first.')
with open(CSV,newline='') as f: rows=list(csv.DictReader(f))
if not rows: raise SystemExit('CSV has no results.')
x=[float(r['threshold_percent']) for r in rows]
def plot(col,ylabel,name):
    y=[float(r[col]) for r in rows]
    plt.figure(figsize=(8,5)); plt.plot(x,y,marker='o'); plt.xlabel('Underutilization Threshold (%)'); plt.ylabel(ylabel); plt.grid(True,alpha=.3); plt.tight_layout(); plt.savefig(os.path.join(BASE,name),dpi=160); plt.close()
plot('energy_saving_percent','Energy Saving (%)','phase11_energy_saving.png')
plot('avg_throughput_mbps','Average Throughput (Mbps)','phase11_throughput.png')
plot('avg_utilization_percent','Average Utilization (%)','phase11_utilization.png')
plot('avg_latency_ms','Average Latency (ms)','phase11_latency.png')
plot('avg_jitter_ms','Average Jitter Proxy (ms)','phase11_jitter.png')
plot('avg_packet_loss_percent','Average Packet Loss (%)','phase11_packet_loss.png')
plot('tcp_retransmissions_delta','TCP Retransmissions (delta)','phase11_retransmissions.png')
plot('sleeping_links','Sleeping Links','phase11_sleeping_links.png')
plot('viable_paths','Viable R1-R6 Paths','phase11_viable_paths.png')
print('Phase 11 graphs generated.')

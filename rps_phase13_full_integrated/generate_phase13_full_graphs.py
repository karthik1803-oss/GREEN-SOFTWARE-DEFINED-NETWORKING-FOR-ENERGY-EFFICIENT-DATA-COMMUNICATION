#!/usr/bin/env python3
import os, csv
import matplotlib.pyplot as plt
from collections import Counter

OUT='phase13_full_graphs'
os.makedirs(OUT,exist_ok=True)

def rows(path):
    if not os.path.exists(path): return []
    with open(path,newline='') as f: return list(csv.DictReader(f))

def save(name):
    plt.tight_layout(); plt.savefig(os.path.join(OUT,name),dpi=180,bbox_inches='tight'); plt.close()

r=rows('phase13_integrated_rps.csv')
e=rows('phase13_energy_statistics.csv')
s=rows('phase13_security_inputs.csv')
if r:
    c=Counter(x['priority'] for x in r); keys=['HIGH','MEDIUM','LOW']
    plt.figure(figsize=(8,5)); plt.bar(keys,[c.get(k,0) for k in keys]); plt.title('Dynamic priority distribution'); plt.ylabel('RPS cycles'); save('priority_distribution.png')
    x=list(range(1,len(r)+1))
    plt.figure(figsize=(10,5))
    for k,label in [('p1_cost','P1 R1-R2-R4-R6'),('p2_cost','P2 R1-R2-R5-R6'),('p3_cost','P3 R1-R3-R4-R6'),('p4_cost','P4 R1-R3-R5-R6')]:
        vals=[]
        for z in r:
            try: vals.append(float(z[k]))
            except: vals.append(float('nan'))
        plt.plot(x,vals,label=label)
    plt.title('RPS path cost over time'); plt.xlabel('RPS cycle'); plt.ylabel('Priority-aware path cost'); plt.legend(); save('rps_path_costs.png')
    pc=Counter(x['current_path'] for x in r)
    plt.figure(figsize=(10,5)); plt.bar(list(pc.keys()),list(pc.values())); plt.title('Selected RPS path distribution'); plt.ylabel('RPS cycles'); plt.xticks(rotation=15,ha='right'); save('rps_path_distribution.png')
    plt.figure(figsize=(9,5)); plt.plot(x,[int(z['switch_count']) for z in r],marker='o'); plt.title('RPS path switches'); plt.xlabel('RPS cycle'); plt.ylabel('Cumulative switches'); save('rps_switches.png')
if e:
    x=[int(z['cycle']) for z in e]
    plt.figure(figsize=(9,5)); plt.plot(x,[float(z['energy_saving_percent']) for z in e],marker='o'); plt.title('Green energy saving over time'); plt.xlabel('Green cycle'); plt.ylabel('Cumulative energy saving (%)'); save('energy_saving.png')
    plt.figure(figsize=(9,5)); plt.plot(x,[float(z['baseline_power_w']) for z in e],label='Baseline power'); plt.plot(x,[float(z['proposed_power_w']) for z in e],label='Proposed power'); plt.title('Baseline vs proposed power'); plt.xlabel('Green cycle'); plt.ylabel('Power (W)'); plt.legend(); save('power_comparison.png')
    plt.figure(figsize=(9,5)); plt.plot(x,[int(z['active_links']) for z in e],label='Active links'); plt.plot(x,[int(z['sleeping_links']) for z in e],label='Sleeping links'); plt.title('Active and sleeping backbone links'); plt.xlabel('Green cycle'); plt.ylabel('Number of links'); plt.legend(); save('active_sleeping_links.png')
    plt.figure(figsize=(9,5)); plt.plot(x,[int(z['viable_paths']) for z in e],marker='o'); plt.title('Viable R1-R6 paths'); plt.xlabel('Green cycle'); plt.ylabel('Viable paths'); plt.ylim(0,4.5); save('viable_paths.png')
    plt.figure(figsize=(9,5)); plt.plot(x,[int(z['sleep_events']) for z in e],label='Sleep events'); plt.plot(x,[int(z['wake_events']) for z in e],label='Wake events'); plt.title('Green sleep/wake events'); plt.xlabel('Green cycle'); plt.ylabel('Cumulative events'); plt.legend(); save('sleep_wake_events.png')
    plt.figure(figsize=(9,5)); plt.plot(x,[float(z['baseline_energy_j']) for z in e],label='Baseline energy'); plt.plot(x,[float(z['proposed_energy_j']) for z in e],label='Proposed energy'); plt.title('Baseline vs proposed cumulative energy'); plt.xlabel('Green cycle'); plt.ylabel('Energy (J)'); plt.legend(); save('energy_comparison.png')
if s:
    fc=Counter('%s -> %s'%(z['src_ip'],z['dst_ip']) for z in s)
    plt.figure(figsize=(10,5)); plt.bar(list(fc.keys()),list(fc.values())); plt.title('Security input records by flow'); plt.ylabel('Security records'); plt.xticks(rotation=15,ha='right'); save('security_records_by_flow.png')
print('Generated graphs in:',OUT)
print('RPS rows:',len(r),'Energy rows:',len(e),'Security rows:',len(s))
if e:
    z=e[-1]
    print('Final Green: active=%s sleeping=%s viable=%s saved=%s%% sleep_events=%s wake_events=%s'%(z['active_links'],z['sleeping_links'],z['viable_paths'],z['energy_saving_percent'],z['sleep_events'],z['wake_events']))

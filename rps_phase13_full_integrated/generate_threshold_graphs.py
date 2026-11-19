#!/usr/bin/env python3
import csv, os
import matplotlib.pyplot as plt

BASE=os.path.dirname(os.path.abspath(__file__))
CSV=os.path.join(BASE,'threshold_comparison.csv')
if not os.path.exists(CSV):
    raise SystemExit('threshold_comparison.csv not found. Run thresholdtest first.')
with open(CSV,newline='') as f:
    rows=list(csv.DictReader(f))
if not rows:
    raise SystemExit('No threshold results found.')

def vals(k): return [float(r[k]) for r in rows]
x=vals('threshold_percent')

def graph(ykey,ylabel,title,name):
    plt.figure(figsize=(8,5))
    plt.plot(x,vals(ykey),marker='o')
    plt.xlabel('Underutilization threshold (%)')
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True,alpha=.3)
    plt.tight_layout()
    plt.savefig(os.path.join(BASE,name),dpi=160)
    plt.close()

graph('energy_saving_percent','Energy saving (%)','Threshold vs Energy Saving','threshold_vs_energy_saving.png')
graph('sleeping_links','Sleeping links','Threshold vs Sleeping Links','threshold_vs_sleeping_links.png')
graph('switch_count','Route switches','Threshold vs Route Switches','threshold_vs_route_switches.png')
graph('viable_paths','Viable R1-R6 paths','Threshold vs Routing Redundancy','threshold_vs_viable_paths.png')
print('Generated 4 Phase-10 threshold comparison graphs.')

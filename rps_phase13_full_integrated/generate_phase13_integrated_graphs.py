#!/usr/bin/env python3
import csv, os
from collections import Counter
import matplotlib.pyplot as plt

RPS='phase13_integrated_rps.csv'; SEC='phase13_security_inputs.csv'; OUT='phase13_integrated_graphs'
os.makedirs(OUT,exist_ok=True)
if not os.path.exists(RPS): raise SystemExit('Missing %s. Run the Phase 13 integrated experiment first.'%RPS)
with open(RPS,newline='') as f: rows=list(csv.DictReader(f))
if not rows: raise SystemExit('No RPS rows found.')
x=list(range(1,len(rows)+1))
# 1 priority distribution
c=Counter(r['priority'] for r in rows)
plt.figure(figsize=(7,4)); plt.bar(['HIGH','MEDIUM','LOW'],[c.get('HIGH',0),c.get('MEDIUM',0),c.get('LOW',0)]); plt.ylabel('RPS cycles'); plt.title('Dynamic priority distribution'); plt.tight_layout(); plt.savefig(os.path.join(OUT,'priority_distribution.png'),dpi=180); plt.close()
# 2 path costs
plt.figure(figsize=(9,5))
for key,label in [('p1_cost','P1 R1-R2-R4-R6'),('p2_cost','P2 R1-R2-R5-R6'),('p3_cost','P3 R1-R3-R4-R6'),('p4_cost','P4 R1-R3-R5-R6')]: plt.plot(x,[float(r[key]) for r in rows],label=label)
plt.xlabel('RPS cycle'); plt.ylabel('Priority-aware path cost'); plt.title('RPS path cost over time'); plt.legend(); plt.tight_layout(); plt.savefig(os.path.join(OUT,'rps_path_costs.png'),dpi=180); plt.close()
# 3 selected path distribution
pc=Counter(r['current_path'] for r in rows); labels=list(pc); vals=[pc[k] for k in labels]
plt.figure(figsize=(9,4)); plt.bar(range(len(labels)),vals); plt.xticks(range(len(labels)),labels,rotation=15,ha='right'); plt.ylabel('RPS cycles'); plt.title('Selected RPS path distribution'); plt.tight_layout(); plt.savefig(os.path.join(OUT,'rps_path_distribution.png'),dpi=180); plt.close()
# 4 switch progression
plt.figure(figsize=(8,4)); plt.plot(x,[int(r['switch_count']) for r in rows],marker='o'); plt.xlabel('RPS cycle'); plt.ylabel('Cumulative switches'); plt.title('RPS path switches'); plt.tight_layout(); plt.savefig(os.path.join(OUT,'rps_switches.png'),dpi=180); plt.close()
# 5 security records
if os.path.exists(SEC):
    with open(SEC,newline='') as f: sr=list(csv.DictReader(f))
    fc=Counter('%s -> %s'%(r['src_ip'],r['dst_ip']) for r in sr)
    if fc:
        labels=list(fc); vals=[fc[k] for k in labels]
        plt.figure(figsize=(9,4)); plt.bar(range(len(labels)),vals); plt.xticks(range(len(labels)),labels,rotation=20,ha='right'); plt.ylabel('Security records'); plt.title('Security input records by flow'); plt.tight_layout(); plt.savefig(os.path.join(OUT,'security_records_by_flow.png'),dpi=180); plt.close()
print('Generated graphs in:',OUT)
print('RPS cycles:',len(rows)); print('Priority counts:',dict(c)); print('Path counts:',dict(pc))

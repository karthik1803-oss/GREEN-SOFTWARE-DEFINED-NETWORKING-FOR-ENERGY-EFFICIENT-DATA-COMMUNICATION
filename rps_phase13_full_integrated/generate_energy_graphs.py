#!/usr/bin/env python3

import csv
import os
import sys
import matplotlib.pyplot as plt


def read_rows(path):
    rows=[]
    with open(path,newline='') as f:
        for r in csv.DictReader(f):
            rows.append({
                'cycle': int(r['cycle']),
                'active': int(r['active_links']),
                'sleeping': int(r['sleeping_links']),
                'baseline_power': float(r['baseline_power_w']),
                'proposed_power': float(r['proposed_power_w']),
                'baseline_energy': float(r['baseline_energy_j']),
                'proposed_energy': float(r['proposed_energy_j']),
                'saving': float(r['energy_saving_percent'])
            })
    return rows


def line(x,y,ylabel,title,path):
    plt.figure(figsize=(8,5))
    plt.plot(x,y,marker='o')
    plt.xlabel('Auto-RPS cycle')
    plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path,dpi=160)
    plt.close()


def main():
    src=sys.argv[1] if len(sys.argv)>1 else 'energy_statistics.csv'
    rows=read_rows(src)
    if not rows:
        print('No rows found.')
        return 1
    out=os.path.join(os.path.dirname(os.path.abspath(src)),'energy_graphs')
    os.makedirs(out,exist_ok=True)
    x=[r['cycle'] for r in rows]
    line(x,[r['active'] for r in rows],'Active links','Active links vs controller cycle',os.path.join(out,'active_links.png'))
    line(x,[r['sleeping'] for r in rows],'Sleeping links','Sleeping links vs controller cycle',os.path.join(out,'sleeping_links.png'))
    line(x,[r['proposed_power'] for r in rows],'Power (W)','Proposed network power vs cycle',os.path.join(out,'proposed_power.png'))
    line(x,[r['saving'] for r in rows],'Energy saving (%)','Estimated energy saving vs cycle',os.path.join(out,'energy_saving_percent.png'))
    line(x,[r['baseline_energy'] for r in rows],'Energy (J)','Baseline cumulative energy',os.path.join(out,'baseline_energy.png'))
    line(x,[r['proposed_energy'] for r in rows],'Energy (J)','Proposed cumulative energy',os.path.join(out,'proposed_energy.png'))
    print('Generated:',out)
    return 0

if __name__=='__main__':
    raise SystemExit(main())

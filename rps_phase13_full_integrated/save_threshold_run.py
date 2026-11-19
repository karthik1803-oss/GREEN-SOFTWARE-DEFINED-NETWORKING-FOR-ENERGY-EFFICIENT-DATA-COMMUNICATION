#!/usr/bin/env python3
import sys, os, shutil
if len(sys.argv)!=2 or sys.argv[1] not in ('5','10','15','20'):
    print('Usage: python3 save_threshold_run.py 5|10|15|20'); raise SystemExit(1)
t=sys.argv[1]; out=os.path.join('threshold_results',t); os.makedirs(out,exist_ok=True)
for f in ('phase13_integrated_rps.csv','phase13_energy_statistics.csv','phase13_security_inputs.csv','phase13_network_effect.csv','phase13_end_to_end_metrics.csv'):
    if os.path.exists(f): shutil.copy2(f,os.path.join(out,f))
print('Saved threshold %s%% results to %s'%(t,out))

#!/usr/bin/env python3
import os, sys
import pandas as pd
import matplotlib.pyplot as plt

CSV='phase13_security_inputs.csv'
OUT='phase13_graphs'

if not os.path.exists(CSV):
    print('ERROR: %s not found. Run Phase 13 traffic first.' % CSV)
    sys.exit(1)

df=pd.read_csv(CSV)
required=['timestamp','nonce','src_mac','dst_mac','src_ip','dst_ip','path']
missing=[c for c in required if c not in df.columns]
if missing:
    print('ERROR: missing columns: %s' % ', '.join(missing)); sys.exit(1)
if df.empty:
    print('ERROR: CSV contains no security records.'); sys.exit(1)

df['timestamp']=pd.to_numeric(df['timestamp'], errors='coerce')
df=df.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
if df.empty:
    print('ERROR: no valid timestamps found.'); sys.exit(1)
os.makedirs(OUT, exist_ok=True)

def save(name):
    plt.tight_layout(); p=os.path.join(OUT,name); plt.savefig(p,dpi=200,bbox_inches='tight'); plt.close(); print('Created:',p)

# 1 cumulative security records vs elapsed time
elapsed=df['timestamp']-df['timestamp'].iloc[0]
plt.figure(figsize=(9,5))
plt.plot(elapsed, range(1,len(df)+1), marker='o', markersize=3)
plt.xlabel('Elapsed time (s)'); plt.ylabel('Cumulative security records')
plt.title('Phase 13 - Security Records Generated Over Time'); plt.grid(True,alpha=.3)
save('phase13_records_over_time.png')

# 2 nonce uniqueness: cumulative records vs cumulative unique nonces
unique=[]; seen=set()
for n in df['nonce'].astype(str):
    seen.add(n); unique.append(len(seen))
plt.figure(figsize=(9,5))
plt.plot(elapsed, range(1,len(df)+1), label='Records', marker='o', markersize=3)
plt.plot(elapsed, unique, label='Unique nonces', marker='x', markersize=3)
plt.xlabel('Elapsed time (s)'); plt.ylabel('Count')
plt.title('Phase 13 - Nonce Uniqueness Over Time'); plt.legend(); plt.grid(True,alpha=.3)
save('phase13_nonce_uniqueness.png')

# 3 records by source -> destination flow
flow=(df['src_ip'].astype(str)+' -> '+df['dst_ip'].astype(str)).value_counts().sort_values()
plt.figure(figsize=(10,max(5,0.45*len(flow))))
flow.plot(kind='barh')
plt.xlabel('Security records'); plt.ylabel('Flow')
plt.title('Phase 13 - Security Records by Source-Destination Flow'); plt.grid(axis='x',alpha=.3)
save('phase13_flow_distribution.png')

# 4 records by active RPS path
paths=df['path'].astype(str).value_counts().sort_values()
plt.figure(figsize=(10,max(5,0.55*len(paths))))
paths.plot(kind='barh')
plt.xlabel('Security records'); plt.ylabel('RPS path')
plt.title('Phase 13 - Security Records by Active RPS Path'); plt.grid(axis='x',alpha=.3)
save('phase13_path_distribution.png')

# Summary
print('\nPhase 13 graph summary')
print('Records:',len(df))
print('Unique nonces:',df['nonce'].nunique())
print('Duplicate nonces:',len(df)-df['nonce'].nunique())
print('Flows:',flow.size)
print('Paths observed:',paths.size)

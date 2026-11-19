#!/usr/bin/env python3
import csv, os
import matplotlib.pyplot as plt
from collections import Counter

FILE='phase14_security_authentication.csv'
if not os.path.exists(FILE):
    raise SystemExit('phase14_security_authentication.csv not found. Run the security experiment first.')
with open(FILE,newline='') as f:
    rows=list(csv.DictReader(f))
if not rows:
    raise SystemExit('No security authentication rows found.')

wake=[r for r in rows if r.get('event')=='WAKE']
results=Counter(r.get('result','UNKNOWN') for r in wake)
reasons=Counter(r.get('reason','UNKNOWN') for r in wake)
created=sum(1 for r in rows if r.get('event')=='TOKEN_CREATE')

# 1 Valid/invalid wake authentication
labels=['ALLOW','DENY']; vals=[results.get(x,0) for x in labels]
plt.figure(figsize=(7,4.5)); plt.bar(labels,vals)
plt.title('Security authentication results'); plt.xlabel('Wake authentication decision'); plt.ylabel('Events')
plt.tight_layout(); plt.savefig('security_allow_vs_deny.png',dpi=180); plt.close()

# 2 Authentication reason breakdown
if reasons:
    labs=list(reasons.keys()); values=[reasons[x] for x in labs]
    plt.figure(figsize=(8,4.8)); plt.bar(labs,values)
    plt.title('Security authentication reason breakdown'); plt.xlabel('Reason'); plt.ylabel('Events'); plt.xticks(rotation=20,ha='right')
    plt.tight_layout(); plt.savefig('security_authentication_reasons.png',dpi=180); plt.close()

# 3 Token generation vs wake decisions
labs=['Tokens created','Wake allowed','Wake denied']; values=[created,results.get('ALLOW',0),results.get('DENY',0)]
plt.figure(figsize=(7.5,4.5)); plt.bar(labs,values)
plt.title('Security mechanism event summary'); plt.ylabel('Events'); plt.xticks(rotation=12)
plt.tight_layout(); plt.savefig('security_event_summary.png',dpi=180); plt.close()

print('Generated: security_allow_vs_deny.png')
if reasons: print('Generated: security_authentication_reasons.png')
print('Generated: security_event_summary.png')
print('Tokens created:',created,'Wake ALLOW:',results.get('ALLOW',0),'Wake DENY:',results.get('DENY',0))

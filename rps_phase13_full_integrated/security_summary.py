#!/usr/bin/env python3
import csv, os
from collections import Counter
f='phase14_security_authentication.csv'
if not os.path.exists(f): raise SystemExit(f+' not found')
with open(f,newline='') as h: rows=list(csv.DictReader(h))
w=[r for r in rows if r.get('event')=='WAKE']
print('=== FINAL SECURITY SUMMARY ===')
print('HMAC tokens created :',sum(r.get('event')=='TOKEN_CREATE' for r in rows))
print('Wake checks         :',len(w))
print('Wake ALLOW          :',sum(r.get('result')=='ALLOW' for r in w))
print('Wake DENY           :',sum(r.get('result')=='DENY' for r in w))
print('Reasons             :',dict(Counter(r.get('reason','') for r in w)))

#!/usr/bin/env python3
import os
for f in ('phase13_integrated_rps.csv','phase13_energy_statistics.csv','phase13_security_inputs.csv','phase13_network_effect.csv','phase13_end_to_end_metrics.csv','phase14_security_authentication.csv'):
    if os.path.exists(f): os.remove(f); print('removed',f)

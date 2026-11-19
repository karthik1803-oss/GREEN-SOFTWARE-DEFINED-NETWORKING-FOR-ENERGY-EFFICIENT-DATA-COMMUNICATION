#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import os
import csv
import time


class GreenEnergyManager(object):

    def __init__(self, net, routers):
        self.net = net
        self.routers = routers

        self.enabled = False
        self.mode = 'simulate'

        self.underutil_threshold = 10.0
        self.required_cycles = 3
        self.wake_threshold = 70.0

        # Experimental energy-model parameters, not physical measurements.
        self.active_power_w = 10.0
        self.sleep_power_w = 2.0

        # Preserve routing resilience: Green control must leave at least
        # two viable R1-R6 paths (one primary plus one backup).
        self.min_viable_paths = 2
        self.rps_paths = [
            ['r1', 'r2', 'r4', 'r6'],
            ['r1', 'r2', 'r5', 'r6'],
            ['r1', 'r3', 'r4', 'r6'],
            ['r1', 'r3', 'r5', 'r6']
        ]

        self.link_interfaces = {
            ('r1', 'r2'): ('r1-eth1', 'r2-eth1'),
            ('r1', 'r3'): ('r1-eth2', 'r3-eth1'),
            ('r2', 'r4'): ('r2-eth2', 'r4-eth1'),
            ('r2', 'r5'): ('r2-eth3', 'r5-eth1'),
            ('r3', 'r4'): ('r3-eth2', 'r4-eth2'),
            ('r3', 'r5'): ('r3-eth3', 'r5-eth2'),
            ('r4', 'r6'): ('r4-eth3', 'r6-eth1'),
            ('r5', 'r6'): ('r5-eth3', 'r6-eth2')
        }

        self.link_state = {}
        self.underutil_count = {}

        for link in self.link_interfaces:
            self.link_state[link] = 'ACTIVE'
            self.underutil_count[link] = 0

        self.last_energy_time = None
        self.baseline_energy_j = 0.0
        self.proposed_energy_j = 0.0
        self.sleep_events = 0
        self.wake_events = 0

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.csv_path = os.path.join(
            self.base_dir,
            'energy_statistics.csv'
        )

    def normalize_link(self, link):
        if link in self.link_interfaces:
            return link
        rev = (link[1], link[0])
        if rev in self.link_interfaces:
            return rev
        return link

    def path_links(self, path):
        result = []
        if not path:
            return result
        for i in range(len(path) - 1):
            result.append(
                self.normalize_link((path[i], path[i + 1]))
            )
        return result

    def is_path_available(self, path):
        for link in self.path_links(path):
            if self.link_state.get(link, 'ACTIVE') == 'SLEEPING':
                return False
        return True

    def sleeping_links(self):
        return [
            link for link in self.link_state
            if self.link_state[link] == 'SLEEPING'
        ]

    def active_links(self):
        return [
            link for link in self.link_state
            if self.link_state[link] == 'ACTIVE'
        ]

    def _set_interfaces(self, link, up):
        link = self.normalize_link(link)
        if link not in self.link_interfaces:
            return

        a, b = link
        a_if, b_if = self.link_interfaces[link]
        state = 'up' if up else 'down'

        self.routers[a].cmd(
            'ip link set dev %s %s' % (a_if, state)
        )
        self.routers[b].cmd(
            'ip link set dev %s %s' % (b_if, state)
        )

    def _ping_ok(self, src_host, dst_ip):
        output = self.net.get(src_host).cmd(
            'ping -c 1 -W 1 %s 2>/dev/null' % dst_ip
        )
        return (
            '1 received' in output
            or '1 packets received' in output
        )

    def verify_experiment_connectivity(self):
        checks = [
            ('h1', '192.168.6.10'),
            ('h2', '192.168.5.10'),
            ('h3', '192.168.6.11'),
            ('h5', '192.168.4.11'),
            ('h6', '192.168.5.11')
        ]

        for src, dst in checks:
            if not self._ping_ok(src, dst):
                return False
        return True

    def _viable_path_count_if_sleep(self, candidate):
        candidate = self.normalize_link(candidate)
        count = 0
        for path in self.rps_paths:
            available = True
            for link in self.path_links(path):
                if link == candidate:
                    available = False
                    break
                if self.link_state.get(link, 'ACTIVE') == 'SLEEPING':
                    available = False
                    break
            if available:
                count += 1
        return count

    def can_sleep_with_backup(self, link):
        return (
            self._viable_path_count_if_sleep(link)
            >= self.min_viable_paths
        )

    def sleep_link(self, link):
        link = self.normalize_link(link)

        if self.link_state.get(link) == 'SLEEPING':
            return True

        if self.mode == 'live':
            self._set_interfaces(link, False)
            time.sleep(0.4)

            # Safety rollback: do not keep a link down if one of the
            # experiment's five traffic relationships loses reachability.
            if not self.verify_experiment_connectivity():
                self._set_interfaces(link, True)
                time.sleep(0.2)
                self.link_state[link] = 'ACTIVE'
                self.underutil_count[link] = 0
                print(
                    'GREEN SAFETY ROLLBACK: %s-%s kept ACTIVE'
                    % (link[0].upper(), link[1].upper())
                )
                return False

        self.link_state[link] = 'SLEEPING'
        self.sleep_events += 1
        return True

    def wake_link(self, link):
        link = self.normalize_link(link)

        if self.link_state.get(link) != 'SLEEPING':
            return False

        if self.mode == 'live':
            self._set_interfaces(link, True)
            time.sleep(0.2)

        self.link_state[link] = 'ACTIVE'
        self.underutil_count[link] = 0
        self.wake_events += 1
        return True

    def wake_all(self):
        count = 0
        for link in list(self.link_state.keys()):
            if self.wake_link(link):
                count += 1
        return count

    def wake_minimum_for_capacity(self, current_path):
        # Restore the smallest number of sleeping links needed to make
        # one additional R1-R6 path available. This avoids waking the
        # entire backbone for a single congestion event.
        choices = []
        for path in self.rps_paths:
            if current_path and path == current_path:
                continue
            missing = []
            for link in self.path_links(path):
                if self.link_state.get(link, 'ACTIVE') == 'SLEEPING':
                    missing.append(link)
            if missing:
                choices.append((len(missing), path, missing))

        if not choices:
            return []

        choices.sort(key=lambda item: item[0])
        missing = choices[0][2]
        woke = []
        for link in missing:
            if self.wake_link(link):
                woke.append(link)
        return woke

    def _util(self, metrics, link):
        link = self.normalize_link(link)
        if link in metrics:
            return float(metrics[link].get('utilization_percent', 0.0))
        rev = (link[1], link[0])
        if rev in metrics:
            return float(metrics[rev].get('utilization_percent', 0.0))
        return 0.0

    def _update_energy(self, elapsed_hint):
        now = time.time()
        if self.last_energy_time is None:
            dt = float(elapsed_hint)
        else:
            dt = max(0.0, now - self.last_energy_time)
        self.last_energy_time = now

        total_links = len(self.link_interfaces)
        active = len(self.active_links())
        sleeping = len(self.sleeping_links())

        baseline_power = total_links * self.active_power_w
        proposed_power = (
            active * self.active_power_w
            + sleeping * self.sleep_power_w
        )

        self.baseline_energy_j += baseline_power * dt
        self.proposed_energy_j += proposed_power * dt

        saving = 0.0
        if self.baseline_energy_j > 0:
            saving = (
                (self.baseline_energy_j - self.proposed_energy_j)
                / self.baseline_energy_j
                * 100.0
            )

        return {
            'active_links': active,
            'sleeping_links': sleeping,
            'baseline_power_w': baseline_power,
            'proposed_power_w': proposed_power,
            'baseline_energy_j': self.baseline_energy_j,
            'proposed_energy_j': self.proposed_energy_j,
            'energy_saving_percent': saving
        }

    def _write_csv(self, cycle, current_path, energy):
        write_header = not os.path.exists(self.csv_path)

        with open(self.csv_path, 'ab') as f:
            writer = csv.writer(f)

            if write_header:
                writer.writerow([
                    'cycle',
                    'timestamp',
                    'mode',
                    'current_path',
                    'active_links',
                    'sleeping_links',
                    'baseline_power_w',
                    'proposed_power_w',
                    'baseline_energy_j',
                    'proposed_energy_j',
                    'energy_saving_percent',
                    'sleep_events',
                    'wake_events'
                ])

            writer.writerow([
                cycle,
                int(time.time()),
                self.mode,
                '->'.join([x.upper() for x in current_path])
                    if current_path else 'NONE',
                energy['active_links'],
                energy['sleeping_links'],
                '%.3f' % energy['baseline_power_w'],
                '%.3f' % energy['proposed_power_w'],
                '%.3f' % energy['baseline_energy_j'],
                '%.3f' % energy['proposed_energy_j'],
                '%.3f' % energy['energy_saving_percent'],
                self.sleep_events,
                self.wake_events
            ])

    def evaluate(self, metrics, current_path, cycle, interval):
        if not self.enabled:
            return None

        current_links = set(self.path_links(current_path))

        # Wake sleeping capacity if the currently used R1-R6 path
        # becomes heavily utilized.
        path_utils = [
            self._util(metrics, link)
            for link in current_links
        ]
        bottleneck = max(path_utils) if path_utils else 0.0

        woke_for_congestion = False
        woken_links = []
        if bottleneck >= self.wake_threshold and self.sleeping_links():
            woken_links = self.wake_minimum_for_capacity(current_path)
            woke_for_congestion = bool(woken_links)

        sleep_candidates = []

        for link in self.link_interfaces:
            if self.link_state[link] == 'SLEEPING':
                continue

            util = self._util(metrics, link)

            # Never sleep an edge currently carrying the selected R1-R6 path.
            if link in current_links:
                self.underutil_count[link] = 0
                continue

            if util <= self.underutil_threshold:
                self.underutil_count[link] += 1
            else:
                self.underutil_count[link] = 0

            if self.underutil_count[link] >= self.required_cycles:
                sleep_candidates.append((link, util))

        slept = None

        # Conservative policy: at most one new sleep decision per cycle.
        # This makes the behavior easier to observe and safer to roll back.
        if sleep_candidates and not woke_for_congestion:
            sleep_candidates.sort(key=lambda item: item[1])
            # Choose the lowest-utilization candidate that still leaves
            # at least one backup R1-R6 path after the sleep decision.
            for candidate, util in sleep_candidates:
                if not self.can_sleep_with_backup(candidate):
                    continue
                if self.sleep_link(candidate):
                    slept = candidate
                    self.underutil_count[candidate] = 0
                    break

        energy = self._update_energy(interval)
        self._write_csv(cycle, current_path, energy)

        return {
            'bottleneck_utilization': bottleneck,
            'slept_link': slept,
            'woke_for_congestion': woke_for_congestion,
            'woken_links': woken_links,
            'energy': energy
        }

    def reset_experiment(self, restore_links=True):
        """Reset Green state and energy counters for a fair new trial."""
        if restore_links:
            self.wake_all()
        for link in self.link_interfaces:
            self.link_state[link] = 'ACTIVE'
            self.underutil_count[link] = 0
        self.last_energy_time = None
        self.baseline_energy_j = 0.0
        self.proposed_energy_j = 0.0
        self.sleep_events = 0
        self.wake_events = 0
        try:
            if os.path.exists(self.csv_path):
                os.remove(self.csv_path)
        except:
            pass

    def status_text(self):
        sleeping = [
            '%s-%s' % (a.upper(), b.upper())
            for a, b in self.sleeping_links()
        ]
        active = [
            '%s-%s' % (a.upper(), b.upper())
            for a, b in self.active_links()
        ]

        return {
            'enabled': self.enabled,
            'mode': self.mode,
            'underutil_threshold': self.underutil_threshold,
            'required_cycles': self.required_cycles,
            'wake_threshold': self.wake_threshold,
            'active': active,
            'sleeping': sleeping,
            'sleep_events': self.sleep_events,
            'wake_events': self.wake_events,
            'min_viable_paths': self.min_viable_paths,
            'viable_paths': sum(1 for p in self.rps_paths if self.is_path_available(p)),
            'baseline_energy_j': self.baseline_energy_j,
            'proposed_energy_j': self.proposed_energy_j
        }

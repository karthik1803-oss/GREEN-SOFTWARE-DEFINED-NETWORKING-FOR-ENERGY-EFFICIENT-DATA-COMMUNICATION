#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import re
from collections import defaultdict


class TrafficClassifier(object):
    """
    Dynamic packet-based traffic classifier.

    IMPORTANT:
    - No host or flow has a hard-coded HIGH/MEDIUM/LOW priority.
    - Priority is calculated from observed packet characteristics.
    - Packet features used:
        protocol
        packet size
        packet rate
        inter-arrival time
        TCP control-packet behaviour
    """

    HIGH_THRESHOLD = 5.0
    MEDIUM_THRESHOLD = 2.0

    def __init__(self):
        self.packet_regex = re.compile(
            r'^(\d+\.\d+)\s+IP\s+(\S+)\s+>\s+(\S+):\s+(.*)$'
        )

    def _split_endpoint(self, endpoint):
        """
        tcpdump normally prints IPv4 TCP/UDP endpoints as:
        192.168.1.10.34567

        Return:
            ("192.168.1.10", 34567)

        If a port is absent, return port 0.
        """
        endpoint = endpoint.rstrip(':')

        parts = endpoint.rsplit('.', 1)

        if len(parts) == 2 and parts[1].isdigit():
            return parts[0], int(parts[1])

        return endpoint, 0

    def _detect_protocol(self, details):
        upper = details.upper()

        if 'UDP' in upper:
            return 'UDP'

        if 'FLAGS [' in upper:
            return 'TCP'

        if 'ICMP' in upper:
            return 'ICMP'

        return 'OTHER'

    def _extract_size(self, details):
        match = re.search(r'length\s+(\d+)', details)

        if match:
            return int(match.group(1))

        return 0

    def _tcp_control_packet(self, protocol, size, details):
        if protocol != 'TCP':
            return False

        # Small TCP packets carrying SYN/ACK/FIN/RST information are
        # treated as control-sensitive packets.
        if size <= 100 and 'Flags [' in details:
            return True

        return False

    def parse_tcpdump(self, text):
        packets = []

        for raw_line in text.splitlines():
            line = raw_line.strip()

            match = self.packet_regex.match(line)

            if not match:
                continue

            timestamp = float(match.group(1))
            src_endpoint = match.group(2)
            dst_endpoint = match.group(3)
            details = match.group(4)

            src_ip, src_port = self._split_endpoint(src_endpoint)
            dst_ip, dst_port = self._split_endpoint(dst_endpoint)

            protocol = self._detect_protocol(details)
            size = self._extract_size(details)

            packet = {
                'timestamp': timestamp,
                'src_ip': src_ip,
                'dst_ip': dst_ip,
                'src_port': src_port,
                'dst_port': dst_port,
                'protocol': protocol,
                'size': size,
                'details': details
            }

            packets.append(packet)

        return packets

    def _flow_key(self, packet):
        return (
            packet['src_ip'],
            packet['dst_ip'],
            packet['protocol'],
            packet['src_port'],
            packet['dst_port']
        )

    def _priority_from_score(self, score):
        if score >= self.HIGH_THRESHOLD:
            return 'HIGH'

        if score >= self.MEDIUM_THRESHOLD:
            return 'MEDIUM'

        return 'LOW'

    def _packet_score(self, packet, packet_rate, avg_interarrival):
        score = 0.0

        protocol = packet['protocol']
        size = packet['size']
        details = packet['details']

        # -----------------------------------------------------
        # 1. PROTOCOL
        # -----------------------------------------------------
        # UDP is commonly used by delay-sensitive streams.
        if protocol == 'UDP':
            score += 2.0

        # -----------------------------------------------------
        # 2. PACKET SIZE
        # -----------------------------------------------------
        # Smaller packets are frequently associated with
        # interactive/control/real-time traffic.
        if size > 0 and size <= 256:
            score += 2.0
        elif size <= 800 and size > 0:
            score += 1.0
        elif size >= 1200:
            score -= 1.0

        # -----------------------------------------------------
        # 3. PACKET RATE
        # -----------------------------------------------------
        if packet_rate >= 1000.0:
            score += 2.0
        elif packet_rate >= 200.0:
            score += 1.0

        # -----------------------------------------------------
        # 4. INTER-ARRIVAL TIME
        # -----------------------------------------------------
        if avg_interarrival > 0 and avg_interarrival <= 0.002:
            score += 1.0

        # -----------------------------------------------------
        # 5. TCP CONTROL PACKETS
        # -----------------------------------------------------
        if self._tcp_control_packet(protocol, size, details):
            score += 2.0

        return score

    def classify_packets(self, packets, capture_duration):
        """
        Classify observed packets and aggregate them per 5-tuple flow.

        Returns a list of flow dictionaries.
        """
        grouped = defaultdict(list)

        for packet in packets:
            grouped[self._flow_key(packet)].append(packet)

        flows = []

        for key in grouped:
            flow_packets = grouped[key]
            flow_packets.sort(key=lambda x: x['timestamp'])

            count = len(flow_packets)

            if capture_duration <= 0:
                packet_rate = 0.0
            else:
                packet_rate = float(count) / float(capture_duration)

            inter_arrivals = []

            for i in range(1, count):
                delta = (
                    flow_packets[i]['timestamp'] -
                    flow_packets[i - 1]['timestamp']
                )

                if delta >= 0:
                    inter_arrivals.append(delta)

            if inter_arrivals:
                avg_interarrival = (
                    sum(inter_arrivals) /
                    float(len(inter_arrivals))
                )
            else:
                avg_interarrival = 0.0

            scores = []
            priorities = []

            for packet in flow_packets:
                score = self._packet_score(
                    packet,
                    packet_rate,
                    avg_interarrival
                )

                scores.append(score)
                priorities.append(
                    self._priority_from_score(score)
                )

            if scores:
                average_score = sum(scores) / float(len(scores))
            else:
                average_score = 0.0

            flow_priority = self._priority_from_score(
                average_score
            )

            first_packet = flow_packets[0]

            flows.append({
                'src_ip': first_packet['src_ip'],
                'dst_ip': first_packet['dst_ip'],
                'src_port': first_packet['src_port'],
                'dst_port': first_packet['dst_port'],
                'protocol': first_packet['protocol'],
                'packet_count': count,
                'packet_rate': packet_rate,
                'avg_interarrival': avg_interarrival,
                'average_score': average_score,
                'priority': flow_priority,
                'packet_priorities': priorities
            })

        flows.sort(
            key=lambda x: (
                x['src_ip'],
                x['dst_ip'],
                x['src_port'],
                x['dst_port']
            )
        )

        return flows

    def get_network_priority(self, flows, destination_prefix=None):
        """
        The current RPS implementation selects one path toward a
        destination network. Therefore, use the highest observed
        priority among flows going to that destination network.

        No priority is hard-coded for a host or flow.
        """
        rank = {
            'LOW': 1,
            'MEDIUM': 2,
            'HIGH': 3
        }

        best_priority = 'LOW'
        found = False

        for flow in flows:
            if destination_prefix is not None:
                if not flow['dst_ip'].startswith(destination_prefix):
                    continue

            found = True

            if rank[flow['priority']] > rank[best_priority]:
                best_priority = flow['priority']

        if not found:
            return 'LOW'

        return best_priority

    def print_report(self, flows):
        print("")
        print("============================================================")
        print("          DYNAMIC PACKET TRAFFIC CLASSIFICATION")
        print("============================================================")

        if not flows:
            print("")
            print("No IPv4 packets were captured.")
            print("")
            print("Check:")
            print("  1. traffic is running")
            print("  2. tcpdump is installed")
            print("  3. capture interfaces are correct")
            print("============================================================")
            return

        for index, flow in enumerate(flows):
            print("")
            print("FLOW %d" % (index + 1))
            print("----------------------------------------")
            print("Source          : %s:%d" % (
                flow['src_ip'],
                flow['src_port']
            ))
            print("Destination     : %s:%d" % (
                flow['dst_ip'],
                flow['dst_port']
            ))
            print("Protocol        : %s" % flow['protocol'])
            print("Packets Captured: %d" % flow['packet_count'])
            print("Packet Rate     : %.2f packets/sec" % (
                flow['packet_rate']
            ))
            print("Avg Interarrival: %.6f sec" % (
                flow['avg_interarrival']
            ))
            print("Priority Score  : %.2f" % (
                flow['average_score']
            ))
            print("Priority        : %s" % (
                flow['priority']
            ))

        print("")
        print("============================================================")

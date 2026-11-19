#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from mininet.net import Mininet
from mininet.node import Node, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

import re
import time
import csv
import os
import threading

from rps_controller6 import RPSController
from traffic_classifier import TrafficClassifier
from qos_manager import (
    apply_dynamic_qos,
    mark_flows,
    disable_qos,
    print_qos_assignments,
    show_qos_status
)
from green_energy_manager import GreenEnergyManager


BACKBONE_BW_MBPS = 100.0


# =============================================================
# LINUX ROUTER
# =============================================================

class Router(Node):

    def config(self, **params):
        Node.config(self, **params)
        self.cmd('sysctl -w net.ipv4.ip_forward=1')

    def terminate(self):
        self.cmd('sysctl -w net.ipv4.ip_forward=0')
        Node.terminate(self)


# =============================================================
# BACKBONE LINK MAP
# =============================================================

def get_monitored_links(routers):

    # Both interfaces are stored so that TX/RX packet counters and
    # drops can be measured from both ends of every backbone link.

    return {
        ('r1', 'r2'): {
            'a': routers['r1'],
            'a_if': 'r1-eth1',
            'b': routers['r2'],
            'b_if': 'r2-eth1',
            'capacity_mbps': BACKBONE_BW_MBPS
        },

        ('r1', 'r3'): {
            'a': routers['r1'],
            'a_if': 'r1-eth2',
            'b': routers['r3'],
            'b_if': 'r3-eth1',
            'capacity_mbps': BACKBONE_BW_MBPS
        },

        ('r2', 'r4'): {
            'a': routers['r2'],
            'a_if': 'r2-eth2',
            'b': routers['r4'],
            'b_if': 'r4-eth1',
            'capacity_mbps': BACKBONE_BW_MBPS
        },

        ('r2', 'r5'): {
            'a': routers['r2'],
            'a_if': 'r2-eth3',
            'b': routers['r5'],
            'b_if': 'r5-eth1',
            'capacity_mbps': BACKBONE_BW_MBPS
        },

        ('r3', 'r4'): {
            'a': routers['r3'],
            'a_if': 'r3-eth2',
            'b': routers['r4'],
            'b_if': 'r4-eth2',
            'capacity_mbps': BACKBONE_BW_MBPS
        },

        ('r3', 'r5'): {
            'a': routers['r3'],
            'a_if': 'r3-eth3',
            'b': routers['r5'],
            'b_if': 'r5-eth2',
            'capacity_mbps': BACKBONE_BW_MBPS
        },

        ('r4', 'r6'): {
            'a': routers['r4'],
            'a_if': 'r4-eth3',
            'b': routers['r6'],
            'b_if': 'r6-eth1',
            'capacity_mbps': BACKBONE_BW_MBPS
        },

        ('r5', 'r6'): {
            'a': routers['r5'],
            'a_if': 'r5-eth3',
            'b': routers['r6'],
            'b_if': 'r6-eth2',
            'capacity_mbps': BACKBONE_BW_MBPS
        }
    }


# =============================================================
# INTERFACE STATISTICS
# =============================================================

def read_counter(node, interface, counter_name):

    path = (
        '/sys/class/net/%s/statistics/%s'
        % (
            interface,
            counter_name
        )
    )

    output = node.cmd(
        'cat %s 2>/dev/null'
        % path
    ).strip()

    try:
        return int(output)

    except:
        return 0


def read_interface_stats(node, interface):

    names = [
        'tx_bytes',
        'rx_bytes',
        'tx_packets',
        'rx_packets',
        'tx_dropped',
        'rx_dropped',
        'tx_errors',
        'rx_errors'
    ]

    stats = {}

    for name in names:
        stats[name] = read_counter(
            node,
            interface,
            name
        )

    return stats


def read_all_link_stats(routers):

    result = {}

    links = get_monitored_links(routers)

    for link in links:

        info = links[link]

        result[link] = {
            'a': read_interface_stats(
                info['a'],
                info['a_if']
            ),

            'b': read_interface_stats(
                info['b'],
                info['b_if']
            )
        }

    return result


def safe_delta(current, previous):

    value = current - previous

    if value < 0:
        return 0

    return value


def calculate_link_metrics(
        routers,
        before,
        after,
        interval):

    links = get_monitored_links(routers)

    metrics = {}

    for link in links:

        info = links[link]

        a_before = before[link]['a']
        a_after = after[link]['a']

        b_before = before[link]['b']
        b_after = after[link]['b']

        a_tx_bytes = safe_delta(
            a_after['tx_bytes'],
            a_before['tx_bytes']
        )

        b_tx_bytes = safe_delta(
            b_after['tx_bytes'],
            b_before['tx_bytes']
        )

        a_rx_bytes = safe_delta(
            a_after['rx_bytes'],
            a_before['rx_bytes']
        )

        b_rx_bytes = safe_delta(
            b_after['rx_bytes'],
            b_before['rx_bytes']
        )

        a_to_b_mbps = (
            a_tx_bytes * 8.0
        ) / (
            interval * 1000000.0
        )

        b_to_a_mbps = (
            b_tx_bytes * 8.0
        ) / (
            interval * 1000000.0
        )

        # Full-duplex link utilization is represented by the busier
        # direction, not the sum of both directions.
        throughput_mbps = max(
            a_to_b_mbps,
            b_to_a_mbps
        )

        capacity = info['capacity_mbps']

        if capacity > 0:
            utilization = (
                throughput_mbps /
                capacity
            ) * 100.0
        else:
            utilization = 0.0

        # Limit display to a sensible value. Slight values above 100%
        # can appear because Linux counters and tc timing are not exact.
        if utilization < 0:
            utilization = 0.0

        a_tx_packets = safe_delta(
            a_after['tx_packets'],
            a_before['tx_packets']
        )

        b_tx_packets = safe_delta(
            b_after['tx_packets'],
            b_before['tx_packets']
        )

        a_rx_packets = safe_delta(
            a_after['rx_packets'],
            a_before['rx_packets']
        )

        b_rx_packets = safe_delta(
            b_after['rx_packets'],
            b_before['rx_packets']
        )

        tx_dropped = (
            safe_delta(
                a_after['tx_dropped'],
                a_before['tx_dropped']
            )
            +
            safe_delta(
                b_after['tx_dropped'],
                b_before['tx_dropped']
            )
        )

        rx_dropped = (
            safe_delta(
                a_after['rx_dropped'],
                a_before['rx_dropped']
            )
            +
            safe_delta(
                b_after['rx_dropped'],
                b_before['rx_dropped']
            )
        )

        packets_sent = (
            a_tx_packets +
            b_tx_packets
        )

        packets_received = (
            a_rx_packets +
            b_rx_packets
        )

        packets_dropped = (
            tx_dropped +
            rx_dropped
        )

        denominator = (
            packets_sent +
            packets_dropped
        )

        if denominator > 0:
            drop_percent = (
                packets_dropped * 100.0 /
                denominator
            )
        else:
            drop_percent = 0.0

        errors = (
            safe_delta(
                a_after['tx_errors'],
                a_before['tx_errors']
            )
            +
            safe_delta(
                a_after['rx_errors'],
                a_before['rx_errors']
            )
            +
            safe_delta(
                b_after['tx_errors'],
                b_before['tx_errors']
            )
            +
            safe_delta(
                b_after['rx_errors'],
                b_before['rx_errors']
            )
        )

        metrics[link] = {
            'capacity_mbps': capacity,

            'a_to_b_mbps': a_to_b_mbps,
            'b_to_a_mbps': b_to_a_mbps,

            'throughput_mbps': throughput_mbps,
            'utilization_percent': utilization,

            'packets_sent': packets_sent,
            'packets_received': packets_received,
            'packets_dropped': packets_dropped,

            'drop_percent': drop_percent,
            'errors': errors,

            'a_tx_bytes': a_tx_bytes,
            'b_tx_bytes': b_tx_bytes,
            'a_rx_bytes': a_rx_bytes,
            'b_rx_bytes': b_rx_bytes
        }

    return metrics


def print_link_metrics(metrics):

    print("")
    print("======================================================================")
    print("                    BACKBONE LINK STATISTICS")
    print("======================================================================")
    print(
        "%-9s %-9s %-9s %-8s %-10s %-10s %-10s"
        % (
            "LINK",
            "THR(Mb)",
            "BW(Mb)",
            "UTIL%",
            "SENT",
            "RECEIVED",
            "DROPPED"
        )
    )
    print("----------------------------------------------------------------------")

    for link in sorted(metrics.keys()):

        m = metrics[link]

        print(
            "%-9s %-9.2f %-9.0f %-8.2f %-10d %-10d %-10d"
            % (
                "%s-%s" % (
                    link[0].upper(),
                    link[1].upper()
                ),
                m['throughput_mbps'],
                m['capacity_mbps'],
                m['utilization_percent'],
                m['packets_sent'],
                m['packets_received'],
                m['packets_dropped']
            )
        )

    print("======================================================================")


# =============================================================
# TCP RETRANSMISSION COUNTER
# =============================================================

def get_tcp_retransmissions(node):

    output = node.cmd(
        'cat /proc/net/snmp 2>/dev/null'
    )

    lines = output.splitlines()

    for i in range(len(lines) - 1):

        if (
            lines[i].startswith('Tcp:') and
            lines[i + 1].startswith('Tcp:')
        ):

            headers = lines[i].split()
            values = lines[i + 1].split()

            try:
                index = headers.index(
                    'RetransSegs'
                )

                return int(
                    values[index]
                )

            except:
                return 0

    return 0


def get_total_tcp_retransmissions(nodes):

    total = 0

    for node in nodes:
        total += get_tcp_retransmissions(
            node
        )

    return total


# =============================================================
# END-TO-END LATENCY / LOSS / JITTER
# =============================================================

def measure_ping_metrics(
        source_host,
        destination_ip,
        count=10):

    command = (
        'ping -n -c %d -i 0.1 -W 1 %s'
        % (
            count,
            destination_ip
        )
    )

    output = source_host.cmd(
        command
    )

    packet_loss = 100.0
    latency_avg = 0.0
    jitter = 0.0
    received = 0

    loss_match = re.search(
        r'(\d+(?:\.\d+)?)%\s+packet loss',
        output
    )

    if loss_match:
        packet_loss = float(
            loss_match.group(1)
        )

    recv_match = re.search(
        r'(\d+)\s+packets transmitted,\s+(\d+)\s+(?:packets )?received',
        output
    )

    if recv_match:
        received = int(
            recv_match.group(2)
        )

    # Ubuntu ping:
    # rtt min/avg/max/mdev = 0.123/0.456/0.789/0.111 ms
    rtt_match = re.search(
        r'=\s*'
        r'([\d\.]+)/'
        r'([\d\.]+)/'
        r'([\d\.]+)/'
        r'([\d\.]+)\s*ms',
        output
    )

    if rtt_match:

        latency_avg = float(
            rtt_match.group(2)
        )

        # mdev is used as an RTT variation / jitter proxy.
        jitter = float(
            rtt_match.group(4)
        )

    return {
        'latency_ms': latency_avg,
        'packet_loss_percent': packet_loss,
        'jitter_ms': jitter,
        'ping_received': received,
        'raw': output
    }


# =============================================================
# PACKET CAPTURE
# =============================================================

def get_capture_points(routers):

    return [
        {
            'router': routers['r1'],
            'router_name': 'r1',
            'interface': 'r1-eth0',
            'source_net': '192.168.1.0/24'
        },

        {
            'router': routers['r2'],
            'router_name': 'r2',
            'interface': 'r2-eth0',
            'source_net': '192.168.2.0/24'
        },

        {
            'router': routers['r3'],
            'router_name': 'r3',
            'interface': 'r3-eth0',
            'source_net': '192.168.3.0/24'
        }
    ]


def start_packet_capture(
        routers,
        duration):

    capture_files = []

    for point in get_capture_points(
            routers):

        router = point['router']
        interface = point['interface']
        source_net = point['source_net']

        filename = (
            '/tmp/rps_capture_%s.log'
            % point['router_name']
        )

        router.cmd(
            'rm -f %s'
            % filename
        )

        command = (
            "timeout %.1f tcpdump "
            "-l -n -tt "
            "-i %s "
            "'src net %s and ip' "
            "> %s 2>/dev/null &"
            % (
                duration,
                interface,
                source_net,
                filename
            )
        )

        router.cmd(
            command
        )

        capture_files.append(
            (
                router,
                filename
            )
        )

    return capture_files


def read_packet_captures(
        capture_files):

    combined = ""

    for router, filename in capture_files:

        combined += router.cmd(
            'cat %s 2>/dev/null'
            % filename
        )

    return combined


# =============================================================
# APPLY RPS PATH
# =============================================================

def apply_rps_path(
        routers,
        selected_path):

    destination = '192.168.6.0/24'

    next_hops = {
        ('r1', 'r2'): '10.0.12.2',
        ('r1', 'r3'): '10.0.13.2',

        ('r2', 'r4'): '10.0.24.2',
        ('r2', 'r5'): '10.0.25.2',

        ('r3', 'r4'): '10.0.34.2',
        ('r3', 'r5'): '10.0.35.2',

        ('r4', 'r6'): '10.0.46.2',
        ('r5', 'r6'): '10.0.56.2'
    }

    print("")
    print("============================================================")
    print("                  AUTOMATIC ROUTE SWITCHING")
    print("============================================================")
    print("")
    print(
        " -> ".join(
            [
                router.upper()
                for router in selected_path
            ]
        )
    )
    print("")

    for i in range(
            len(selected_path) - 1):

        current_name = selected_path[i]
        next_name = selected_path[i + 1]

        next_hop = next_hops[
            (
                current_name,
                next_name
            )
        ]

        routers[current_name].cmd(
            'ip route replace %s via %s'
            % (
                destination,
                next_hop
            )
        )

        print(
            '%s route to %s -> %s'
            % (
                current_name.upper(),
                destination,
                next_hop
            )
        )

    print("")
    print("ROUTES UPDATED SUCCESSFULLY")
    print("============================================================")


def apply_bidirectional_rps_path(
        routers,
        selected_path):

    # Forward direction: R1-side LAN -> R6-side LAN.
    apply_rps_path(
        routers,
        selected_path
    )

    # Reverse direction: R6-side LAN -> R1-side LAN.
    reverse_destination = '192.168.1.0/24'

    reverse_next_hops = {
        ('r6', 'r4'): '10.0.46.1',
        ('r6', 'r5'): '10.0.56.1',

        ('r4', 'r2'): '10.0.24.1',
        ('r4', 'r3'): '10.0.34.1',

        ('r5', 'r2'): '10.0.25.1',
        ('r5', 'r3'): '10.0.35.1',

        ('r2', 'r1'): '10.0.12.1',
        ('r3', 'r1'): '10.0.13.1'
    }

    reverse_path = list(reversed(selected_path))

    print("")
    print("Reverse route:")
    print(
        " -> ".join(
            [router.upper() for router in reverse_path]
        )
    )
    print("")

    for i in range(len(reverse_path) - 1):

        current_name = reverse_path[i]
        next_name = reverse_path[i + 1]

        next_hop = reverse_next_hops[
            (current_name, next_name)
        ]

        routers[current_name].cmd(
            'ip route replace %s via %s'
            % (
                reverse_destination,
                next_hop
            )
        )

        print(
            '%s route to %s -> %s'
            % (
                current_name.upper(),
                reverse_destination,
                next_hop
            )
        )

    print("")
    print("BIDIRECTIONAL ROUTES UPDATED")
    print("============================================================")



# =============================================================
# SAVE MONITOR SNAPSHOT FOR GRAPHING
# =============================================================

def save_monitor_snapshot(metrics, ping_metrics, retransmissions):

    base_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

    link_file = os.path.join(
        base_dir,
        'link_statistics_latest.csv'
    )

    network_file = os.path.join(
        base_dir,
        'network_statistics_latest.csv'
    )

    with open(link_file, 'wb') as f:

        writer = csv.writer(f)

        writer.writerow([
            'link',
            'throughput_mbps',
            'bandwidth_mbps',
            'utilization_percent',
            'packets_sent',
            'packets_received',
            'packets_dropped',
            'drop_percent',
            'errors'
        ])

        for link in sorted(metrics.keys()):

            m = metrics[link]

            writer.writerow([
                '%s-%s' % (
                    link[0].upper(),
                    link[1].upper()
                ),
                '%.6f' % m['throughput_mbps'],
                '%.6f' % m['capacity_mbps'],
                '%.6f' % m['utilization_percent'],
                m['packets_sent'],
                m['packets_received'],
                m['packets_dropped'],
                '%.6f' % m['drop_percent'],
                m['errors']
            ])

    total_sent = sum(
        [
            metrics[link]['packets_sent']
            for link in metrics
        ]
    )

    total_received = sum(
        [
            metrics[link]['packets_received']
            for link in metrics
        ]
    )

    total_dropped = sum(
        [
            metrics[link]['packets_dropped']
            for link in metrics
        ]
    )

    avg_throughput = 0.0
    avg_utilization = 0.0

    if metrics:

        avg_throughput = (
            sum(
                [
                    metrics[link]['throughput_mbps']
                    for link in metrics
                ]
            )
            /
            float(len(metrics))
        )

        avg_utilization = (
            sum(
                [
                    metrics[link]['utilization_percent']
                    for link in metrics
                ]
            )
            /
            float(len(metrics))
        )

    with open(network_file, 'wb') as f:

        writer = csv.writer(f)

        writer.writerow([
            'avg_throughput_mbps',
            'avg_utilization_percent',
            'latency_ms',
            'packet_loss_percent',
            'jitter_ms',
            'tcp_retransmissions',
            'packets_sent',
            'packets_received',
            'packets_dropped'
        ])

        writer.writerow([
            '%.6f' % avg_throughput,
            '%.6f' % avg_utilization,
            '%.6f' % ping_metrics['latency_ms'],
            '%.6f' % ping_metrics['packet_loss_percent'],
            '%.6f' % ping_metrics['jitter_ms'],
            retransmissions,
            total_sent,
            total_received,
            total_dropped
        ])

    return link_file, network_file


def generate_graph_files():

    # Always locate generate_graphs.py relative to this topology file,
    # not relative to the terminal's current working directory.
    base_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

    script = os.path.join(
        base_dir,
        'generate_graphs.py'
    )

    if not os.path.exists(script):
        print("")
        print(
            "generate_graphs.py was not found in the current directory."
        )
        print("")
        return False

    base_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

    link_csv = os.path.join(
        base_dir,
        'link_statistics_latest.csv'
    )

    network_csv = os.path.join(
        base_dir,
        'network_statistics_latest.csv'
    )

    command = (
        'python3 "%s" "%s" "%s"'
        % (
            script,
            link_csv,
            network_csv
        )
    )

    result = os.system(command)

    return result == 0



# =============================================================
# PHASE 4 - 30 SECOND EXPERIMENT COLLECTION
# =============================================================

def calculate_expected_transmissions(packet_loss_percent):

    p = float(packet_loss_percent) / 100.0

    if p >= 1.0:
        return float('inf')

    return 1.0 / (1.0 - p)


def append_network_timeseries(
        csv_path,
        elapsed_time,
        metrics,
        ping_metrics,
        retransmissions):

    total_sent = sum(
        [
            metrics[link]['packets_sent']
            for link in metrics
        ]
    )

    total_received = sum(
        [
            metrics[link]['packets_received']
            for link in metrics
        ]
    )

    total_dropped = sum(
        [
            metrics[link]['packets_dropped']
            for link in metrics
        ]
    )

    avg_throughput = 0.0
    avg_utilization = 0.0

    if metrics:
        avg_throughput = (
            sum(
                [
                    metrics[link]['throughput_mbps']
                    for link in metrics
                ]
            )
            /
            float(len(metrics))
        )

        avg_utilization = (
            sum(
                [
                    metrics[link]['utilization_percent']
                    for link in metrics
                ]
            )
            /
            float(len(metrics))
        )

    expected_transmissions = (
        calculate_expected_transmissions(
            ping_metrics['packet_loss_percent']
        )
    )

    write_header = not os.path.exists(csv_path)

    with open(csv_path, 'ab') as f:

        writer = csv.writer(f)

        if write_header:
            writer.writerow([
                'time_sec',
                'avg_throughput_mbps',
                'packet_loss_percent',
                'configured_bandwidth_mbps',
                'avg_utilization_percent',
                'latency_ms',
                'jitter_ms',
                'tcp_retransmissions_actual',
                'expected_transmissions',
                'packets_sent',
                'packets_received',
                'packets_dropped'
            ])

        writer.writerow([
            elapsed_time,
            '%.6f' % avg_throughput,
            '%.6f' % ping_metrics['packet_loss_percent'],
            '%.6f' % BACKBONE_BW_MBPS,
            '%.6f' % avg_utilization,
            '%.6f' % ping_metrics['latency_ms'],
            '%.6f' % ping_metrics['jitter_ms'],
            retransmissions,
            (
                'inf'
                if expected_transmissions == float('inf')
                else '%.6f' % expected_transmissions
            ),
            total_sent,
            total_received,
            total_dropped
        ])



def append_experiment_summary(
        csv_path,
        elapsed_time,
        avg_throughput,
        avg_utilization,
        ping_metrics,
        retransmissions_cumulative,
        retransmissions_interval,
        expected_transmissions,
        total_sent,
        total_received,
        total_dropped):

    write_header = not os.path.exists(csv_path)

    with open(csv_path, 'ab') as f:

        writer = csv.writer(f)

        if write_header:
            writer.writerow([
                'time_sec',
                'average_throughput_mbps',
                'average_utilization_percent',
                'packet_loss_percent',
                'latency_ms',
                'jitter_proxy_ms',
                'tcp_retransmissions_interval',
                'tcp_retransmissions_cumulative',
                'expected_transmissions',
                'packets_sent',
                'packets_received',
                'packets_dropped'
            ])

        writer.writerow([
            elapsed_time,
            '%.6f' % avg_throughput,
            '%.6f' % avg_utilization,
            '%.6f' % ping_metrics['packet_loss_percent'],
            '%.6f' % ping_metrics['latency_ms'],
            '%.6f' % ping_metrics['jitter_ms'],
            retransmissions_interval,
            retransmissions_cumulative,
            (
                'inf'
                if expected_transmissions == float('inf')
                else '%.6f' % expected_transmissions
            ),
            total_sent,
            total_received,
            total_dropped
        ])


def append_link_timeseries(
        csv_path,
        elapsed_time,
        metrics):

    write_header = not os.path.exists(csv_path)

    with open(csv_path, 'ab') as f:

        writer = csv.writer(f)

        if write_header:
            writer.writerow([
                'time_sec',
                'link',
                'throughput_mbps',
                'bandwidth_mbps',
                'utilization_percent',
                'packets_sent',
                'packets_received',
                'packets_dropped',
                'drop_percent',
                'errors'
            ])

        for link in sorted(metrics.keys()):

            m = metrics[link]

            writer.writerow([
                elapsed_time,
                '%s-%s' % (
                    link[0].upper(),
                    link[1].upper()
                ),
                '%.6f' % m['throughput_mbps'],
                '%.6f' % m['capacity_mbps'],
                '%.6f' % m['utilization_percent'],
                m['packets_sent'],
                m['packets_received'],
                m['packets_dropped'],
                '%.6f' % m['drop_percent'],
                m['errors']
            ])


def generate_timeseries_graph_files(
        network_csv,
        link_csv):

    base_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

    script = os.path.join(
        base_dir,
        'generate_timeseries_graphs.py'
    )

    if not os.path.exists(script):
        print("")
        print("generate_timeseries_graphs.py was not found.")
        return False

    command = (
        'python3 "%s" "%s" "%s"'
        % (
            script,
            network_csv,
            link_csv
        )
    )

    return os.system(command) == 0


# =============================================================
# CUSTOM CLI
# =============================================================

class RPSCLI(CLI):

    def __init__(
            self,
            net,
            routers,
            rps,
            classifier,
            *args,
            **kwargs):

        self.net = net
        self.routers = routers
        self.rps = rps
        self.classifier = classifier

        self.last_flows = []
        self.last_link_metrics = {}
        self.qos_active = False
        self.last_qos_assignments = []

        # Phase 6: continuous RPS state
        self.auto_rps_enabled = False
        self.auto_rps_thread = None
        self.auto_rps_interval = 10
        self.auto_rps_hysteresis = 3.0
        self.auto_rps_hold_down = 20
        self.current_path = None
        self.current_path_cost = None
        self.last_switch_time = 0.0
        self.switch_count = 0
        self.auto_rps_cycle = 0
        self.auto_rps_duration = 120
        self.auto_rps_start_time = None

        # Phase 7: Green / energy-aware network manager
        self.green = GreenEnergyManager(
            self.net,
            self.routers
        )

        CLI.__init__(
            self,
            net,
            *args,
            **kwargs
        )

    # =========================================================
    # TRAFFIC
    # =========================================================

    def do_traffic(
            self,
            line):

        # Keep workload alive slightly longer than the default 120-second
        # control experiment so the last control sample is still under load.
        duration = 150
        args = line.strip().split()
        if args:
            try:
                duration = max(10, int(args[0]))
            except:
                pass

        print("")
        print("============================================================")
        print("              STARTING MULTIPLE TRAFFIC FLOWS")
        print("============================================================")

        for host in self.net.hosts:
            host.cmd(
                'killall -q iperf'
            )

        time.sleep(1)

        self.net.get('h11').cmd(
            'iperf -s -u -p 5001 '
            '> /tmp/h11_server.log 2>&1 &'
        )

        self.net.get('h9').cmd(
            'iperf -s -p 5002 '
            '> /tmp/h9_server.log 2>&1 &'
        )

        self.net.get('h12').cmd(
            'iperf -s -u -p 5003 '
            '> /tmp/h12_server.log 2>&1 &'
        )

        self.net.get('h8').cmd(
            'iperf -s -p 5004 '
            '> /tmp/h8_server.log 2>&1 &'
        )

        self.net.get('h10').cmd(
            'iperf -s -u -p 5005 '
            '> /tmp/h10_server.log 2>&1 &'
        )

        time.sleep(2)

        # Different packet characteristics are generated for testing.
        # They are NOT given static priority labels.

        self.net.get('h1').cmd(
            'iperf -c 192.168.6.10 '
            '-u -b 8M -l 160 '
            '-p 5001 -t %d '
            '> /tmp/h1_to_h11.log 2>&1 &'
            % duration
        )

        self.net.get('h2').cmd(
            'iperf -c 192.168.5.10 '
            '-p 5002 -t %d '
            '> /tmp/h2_to_h9.log 2>&1 &'
            % duration
        )

        self.net.get('h3').cmd(
            'iperf -c 192.168.6.11 '
            '-u -b 2M -l 700 '
            '-p 5003 -t %d '
            '> /tmp/h3_to_h12.log 2>&1 &'
            % duration
        )

        self.net.get('h5').cmd(
            'iperf -c 192.168.4.11 '
            '-p 5004 -t %d '
            '> /tmp/h5_to_h8.log 2>&1 &'
            % duration
        )

        self.net.get('h6').cmd(
            'iperf -c 192.168.5.11 '
            '-u -b 1M -l 1000 '
            '-p 5005 -t %d '
            '> /tmp/h6_to_h10.log 2>&1 &'
            % duration
        )

        print("")
        print("Traffic started for %d seconds." % duration)
        print("")
        print("Flow 1: H1 -> H11")
        print("Flow 2: H2 -> H9")
        print("Flow 3: H3 -> H12")
        print("Flow 4: H5 -> H8")
        print("Flow 5: H6 -> H10")
        print("")
        print("NO STATIC PRIORITY IS ASSIGNED.")
        print("============================================================")

    def do_wakeburst(self, line):
        """wakeburst [mbps] [duration]

        Add a temporary high-rate UDP flow from H1 to H11. It follows
        the current RPS route to 192.168.6.0/24 and is intended to push
        the selected path above the Green wake threshold.
        """
        mbps = 95
        duration = 35
        args = line.strip().split()
        if len(args) >= 1:
            try:
                mbps = max(1, int(args[0]))
            except:
                pass
        if len(args) >= 2:
            try:
                duration = max(5, int(args[1]))
            except:
                pass

        self.net.get('h11').cmd(
            'iperf -s -u -p 5099 > /tmp/h11_wake_server.log 2>&1 &'
        )
        time.sleep(1)
        self.net.get('h1').cmd(
            'iperf -c 192.168.6.10 -u -b %dM -l 1400 -p 5099 -t %d '
            '> /tmp/h1_wake_burst.log 2>&1 &' % (mbps, duration)
        )
        print("")
        print("============================================================")
        print("                 GREEN WAKE BURST STARTED")
        print("============================================================")
        print("Flow       : H1 -> H11")
        print("Rate       : %d Mbps UDP" % mbps)
        print("Duration   : %d sec" % duration)
        print("Purpose    : exceed Green wake threshold on current RPS path")
        print("Observe the next AUTO RPS / GREEN cycles for a WAKE decision.")
        print("============================================================")
        print("")

    def do_stoptraffic(
            self,
            line):

        for host in self.net.hosts:
            host.cmd(
                'killall -q iperf'
            )

        print("")
        print("All iperf traffic stopped.")
        print("")



    # =========================================================
    # GRAPH GENERATION
    # =========================================================

    def do_graph(
            self,
            line):

        print("")
        print("============================================================")
        print("                    GRAPH GENERATION")
        print("============================================================")

        base_dir = os.path.dirname(
            os.path.abspath(__file__)
        )

        if (
            not os.path.exists(
                os.path.join(
                    base_dir,
                    'link_statistics_latest.csv'
                )
            )
            or
            not os.path.exists(
                os.path.join(
                    base_dir,
                    'network_statistics_latest.csv'
                )
            )
        ):
            print("")
            print(
                "No monitoring snapshot exists yet."
            )
            print(
                "Run 'monitor' first."
            )
            print("")
            return

        if generate_graph_files():
            print("")
            print("Graphs generated in ./graphs/")
            print("")
            print("1. link_throughput.png")
            print("2. link_utilization.png")
            print("3. packet_counts.png")
            print("4. network_quality.png")
        else:
            print("")
            print("Graph generation failed.")

        print("============================================================")
        print("")


    # =========================================================
    # PHASE 4 COMPLETE EXPERIMENT
    # =========================================================

    def do_experiment(
            self,
            line):

        base_dir = os.path.dirname(
            os.path.abspath(__file__)
        )

        network_csv = os.path.join(
            base_dir,
            'network_statistics.csv'
        )

        link_csv = os.path.join(
            base_dir,
            'link_statistics.csv'
        )

        summary_csv = os.path.join(
            base_dir,
            'experiment_summary.csv'
        )

        # Start a fresh experiment every time.
        for path in [
            network_csv,
            link_csv,
            summary_csv
        ]:
            if os.path.exists(path):
                os.remove(path)

        print("")
        print("============================================================")
        print("             PHASE 4 - 120 SECOND EXPERIMENT")
        print("============================================================")
        print("")
        print("Samples will be collected at:")
        print("  30 sec")
        print("  60 sec")
        print("  90 sec")
        print(" 120 sec")
        print("")
        print("Make sure traffic is already running.")
        print("Recommended:")
        print("  mininet> traffic")
        print("  mininet> experiment")
        print("")
        print("Starting experiment...")
        print("")

        sample_points = [30, 60, 90, 120]
        previous_time = 0

        all_nodes = (
            self.net.hosts +
            list(self.routers.values())
        )

        retrans_start = (
            get_total_tcp_retransmissions(
                all_nodes
            )
        )

        retrans_previous = retrans_start

        for target_time in sample_points:

            interval = target_time - previous_time

            before = read_all_link_stats(
                self.routers
            )

            time.sleep(interval)

            after = read_all_link_stats(
                self.routers
            )

            metrics = calculate_link_metrics(
                self.routers,
                before,
                after,
                interval
            )

            ping_metrics = measure_ping_metrics(
                self.net.get('h1'),
                '192.168.6.10',
                count=10
            )

            retrans_now = (
                get_total_tcp_retransmissions(
                    all_nodes
                )
            )

            retransmissions = safe_delta(
                retrans_now,
                retrans_start
            )

            retransmissions_interval = safe_delta(
                retrans_now,
                retrans_previous
            )

            retrans_previous = retrans_now

            append_network_timeseries(
                network_csv,
                target_time,
                metrics,
                ping_metrics,
                retransmissions
            )

            append_link_timeseries(
                link_csv,
                target_time,
                metrics
            )

            total_sent = sum(
                [
                    metrics[link]['packets_sent']
                    for link in metrics
                ]
            )

            total_received = sum(
                [
                    metrics[link]['packets_received']
                    for link in metrics
                ]
            )

            total_dropped = sum(
                [
                    metrics[link]['packets_dropped']
                    for link in metrics
                ]
            )

            avg_throughput = 0.0
            avg_utilization = 0.0

            if metrics:
                avg_throughput = (
                    sum(
                        [
                            metrics[link]['throughput_mbps']
                            for link in metrics
                        ]
                    )
                    /
                    float(len(metrics))
                )

                avg_utilization = (
                    sum(
                        [
                            metrics[link]['utilization_percent']
                            for link in metrics
                        ]
                    )
                    /
                    float(len(metrics))
                )

            expected_tx = (
                calculate_expected_transmissions(
                    ping_metrics['packet_loss_percent']
                )
            )

            append_experiment_summary(
                summary_csv,
                target_time,
                avg_throughput,
                avg_utilization,
                ping_metrics,
                retransmissions,
                retransmissions_interval,
                expected_tx,
                total_sent,
                total_received,
                total_dropped
            )

            print("")
            print(
                "---------------- SAMPLE @ %d sec ----------------"
                % target_time
            )
            print(
                "Average Throughput      : %.3f Mbps"
                % avg_throughput
            )
            print(
                "Average Utilization     : %.2f %%"
                % avg_utilization
            )
            print(
                "Packet Loss             : %.2f %%"
                % ping_metrics['packet_loss_percent']
            )
            print(
                "Latency                 : %.3f ms"
                % ping_metrics['latency_ms']
            )
            print(
                "Jitter Proxy            : %.3f ms"
                % ping_metrics['jitter_ms']
            )
            print(
                "TCP Retransmissions/30s : %d"
                % retransmissions_interval
            )
            print(
                "TCP Retrans. Cumulative : %d"
                % retransmissions
            )

            if expected_tx == float('inf'):
                print("Expected Transmissions  : infinite")
            else:
                print(
                    "Expected Transmissions  : %.4f"
                    % expected_tx
                )

            print(
                "Packets Sent            : %d"
                % total_sent
            )
            print(
                "Packets Received        : %d"
                % total_received
            )
            print(
                "Packets Dropped         : %d"
                % total_dropped
            )

            previous_time = target_time

        print("")
        print("============================================================")
        print("                 PHASE 4 EXPERIMENT COMPLETE")
        print("============================================================")
        print("")
        print("Generated CSV files:")
        print("  %s" % network_csv)
        print("  %s" % link_csv)
        print("  %s" % summary_csv)

        print("")
        print("Generating time-series graphs...")

        if generate_timeseries_graph_files(
                network_csv,
                link_csv):

            print("")
            print("Time-series graphs generated successfully.")
            print("")
            print("See graphs_timeseries/")

        else:
            print("")
            print("Time-series graph generation failed.")
            print("Check Python 3 and matplotlib installation.")

        print("")
        print("============================================================")
        print("PHASE 4 REQUIREMENTS NOW IMPLEMENTED")
        print("============================================================")
        print("")


    # =========================================================
    # RPS USING UTILIZATION + PRIORITY
    # =========================================================

    # =========================================================
    # PHASE 6 - CONTINUOUS AUTOMATIC RPS
    # =========================================================

    def _path_text(self, path):

        if not path:
            return 'NONE'

        return ' -> '.join(
            [router.upper() for router in path]
        )


    def _write_auto_rps_log(
            self,
            priority,
            best_path,
            best_cost,
            decision):

        base_dir = os.path.dirname(
            os.path.abspath(__file__)
        )

        path = os.path.join(
            base_dir,
            'auto_rps_log.csv'
        )

        write_header = not os.path.exists(path)

        with open(path, 'ab') as f:

            writer = csv.writer(f)

            if write_header:
                writer.writerow([
                    'cycle',
                    'timestamp',
                    'priority',
                    'current_path',
                    'current_cost',
                    'best_path',
                    'best_cost',
                    'decision',
                    'switch_count'
                ])

            writer.writerow([
                self.auto_rps_cycle,
                int(time.time()),
                priority,
                self._path_text(self.current_path),
                self.current_path_cost,
                self._path_text(best_path),
                best_cost,
                decision,
                self.switch_count
            ])


    def _auto_rps_once(self):

        self.auto_rps_cycle += 1
        interval = 2.0

        print("")
        print("============================================================")
        print(
            "                 AUTO RPS CYCLE %d"
            % self.auto_rps_cycle
        )
        print("============================================================")

        before = read_all_link_stats(
            self.routers
        )

        capture_files = start_packet_capture(
            self.routers,
            interval
        )

        time.sleep(interval + 0.3)

        after = read_all_link_stats(
            self.routers
        )

        metrics = calculate_link_metrics(
            self.routers,
            before,
            after,
            interval
        )

        self.last_link_metrics = metrics

        raw_capture = read_packet_captures(
            capture_files
        )

        packets = self.classifier.parse_tcpdump(
            raw_capture
        )

        flows = self.classifier.classify_packets(
            packets,
            interval
        )

        self.last_flows = flows

        # Refresh only dynamic DSCP marking here. The HTB tree is
        # already created by the first normal RPS/QoS activation.
        if self.qos_active:
            try:
                self.last_qos_assignments = mark_flows(
                    self.routers,
                    flows
                )
            except Exception as exc:
                print(
                    "QoS mark refresh warning: %s"
                    % str(exc)
                )
        else:
            self.last_qos_assignments = apply_dynamic_qos(
                self.routers,
                flows
            )
            self.qos_active = True

        priority = self.classifier.get_network_priority(
            flows,
            destination_prefix='192.168.6.'
        )

        link_utilizations = {}

        for link in metrics:
            link_utilizations[link] = (
                metrics[link]['utilization_percent']
            )

        path_costs = []

        print("")
        print("Traffic Priority = %s" % priority)
        print("")

        for index, path in enumerate(self.rps.paths):

            if (
                    self.green.enabled
                    and not self.green.is_path_available(path)):

                print(
                    "Path %d : %-25s SLEEPING / UNAVAILABLE"
                    % (
                        index + 1,
                        self._path_text(path)
                    )
                )
                continue

            cost = self.rps.calculate_path_cost(
                path,
                link_utilizations,
                priority
            )

            path_costs.append(
                (path, cost)
            )

            print(
                "Path %d : %-25s Cost = %.2f"
                % (
                    index + 1,
                    self._path_text(path),
                    cost
                )
            )

        if not path_costs:
            print("No active RPS path is currently available.")
            if self.green.enabled:
                print("Waking all sleeping links for recovery...")
                self.green.wake_all()
            return

        best_path, best_cost = min(
            path_costs,
            key=lambda item: item[1]
        )

        now = time.time()
        decision = ''

        if self.current_path is None:

            apply_bidirectional_rps_path(
                self.routers,
                best_path
            )

            self.current_path = list(best_path)
            self.current_path_cost = best_cost
            self.last_switch_time = now
            self.switch_count += 1

            decision = 'INITIAL APPLY'

        else:

            current_cost = None

            for path, cost in path_costs:
                if path == self.current_path:
                    current_cost = cost
                    break

            if current_cost is None:
                current_cost = self.current_path_cost

            self.current_path_cost = current_cost

            improvement = (
                current_cost - best_cost
            )

            since_switch = (
                now - self.last_switch_time
            )

            if best_path == self.current_path:
                decision = 'KEEP - CURRENT PATH IS BEST'

            elif improvement < self.auto_rps_hysteresis:
                decision = (
                    'KEEP - HYSTERESIS '
                    '(improvement %.2f < %.2f)'
                    % (
                        improvement,
                        self.auto_rps_hysteresis
                    )
                )

            elif since_switch < self.auto_rps_hold_down:
                decision = (
                    'KEEP - HOLD-DOWN '
                    '(%.1fs < %ds)'
                    % (
                        since_switch,
                        self.auto_rps_hold_down
                    )
                )

            else:

                apply_bidirectional_rps_path(
                    self.routers,
                    best_path
                )

                self.current_path = list(best_path)
                self.current_path_cost = best_cost
                self.last_switch_time = now
                self.switch_count += 1

                decision = 'SWITCH'

        print("")
        print(
            "Current Path : %s"
            % self._path_text(self.current_path)
        )
        print(
            "Current Cost : %.2f"
            % float(self.current_path_cost)
        )
        print(
            "Best Path    : %s"
            % self._path_text(best_path)
        )
        print(
            "Best Cost    : %.2f"
            % best_cost
        )
        print(
            "Switch Count : %d"
            % self.switch_count
        )
        print(
            "Decision     : %s"
            % decision
        )
        print("============================================================")

        self._write_auto_rps_log(
            priority,
            best_path,
            best_cost,
            decision
        )

        # -----------------------------------------------------
        # GREEN / ENERGY-AWARE EVALUATION
        # -----------------------------------------------------
        if self.green.enabled:
            green_result = self.green.evaluate(
                metrics,
                self.current_path,
                self.auto_rps_cycle,
                self.auto_rps_interval
            )

            if green_result is not None:
                energy = green_result['energy']

                print("")
                print("---------------- GREEN ENERGY ----------------")
                print(
                    "Current-path bottleneck : %.2f %%"
                    % green_result['bottleneck_utilization']
                )

                if green_result['slept_link']:
                    link = green_result['slept_link']
                    print(
                        "Sleep decision          : %s-%s"
                        % (link[0].upper(), link[1].upper())
                    )

                if green_result['woke_for_congestion']:
                    woken = green_result.get('woken_links', [])
                    wake_text = ', '.join([
                        '%s-%s' % (x[0].upper(), x[1].upper())
                        for x in woken
                    ])
                    print("Wake decision           : CONGESTION - restore capacity")
                    print("Woken link(s)           : %s" % (wake_text or 'NONE'))

                print(
                    "Active / Sleeping links  : %d / %d"
                    % (
                        energy['active_links'],
                        energy['sleeping_links']
                    )
                )
                print(
                    "Baseline power           : %.2f W"
                    % energy['baseline_power_w']
                )
                print(
                    "Proposed power           : %.2f W"
                    % energy['proposed_power_w']
                )
                print(
                    "Estimated energy saving  : %.2f %%"
                    % energy['energy_saving_percent']
                )
                print("------------------------------------------------")


    def _auto_rps_loop(self):

        self.auto_rps_start_time = time.time()

        while self.auto_rps_enabled:

            total_elapsed = time.time() - self.auto_rps_start_time
            if total_elapsed >= self.auto_rps_duration:
                self.auto_rps_enabled = False
                print("")
                print("AUTO RPS experiment completed after %d seconds." % self.auto_rps_duration)
                print("Total completed cycles: %d" % self.auto_rps_cycle)
                print("")
                break

            cycle_start = time.time()

            try:
                self._auto_rps_once()

            except Exception as exc:
                print("")
                print(
                    "AUTO RPS ERROR: %s"
                    % str(exc)
                )

            # Schedule from experiment start, not processing-time + interval.
            # This avoids timing drift across cycles.
            next_target = self.auto_rps_start_time + (
                self.auto_rps_cycle * self.auto_rps_interval
            )
            remaining = next_target - time.time()

            while self.auto_rps_enabled and remaining > 0:
                # Do not sleep past the experiment deadline.
                deadline_remaining = (
                    self.auto_rps_start_time + self.auto_rps_duration
                    - time.time()
                )
                if deadline_remaining <= 0:
                    break
                step = min(1.0, remaining, deadline_remaining)
                time.sleep(step)
                remaining = next_target - time.time()


    def do_autorps(
            self,
            line):

        if self.auto_rps_enabled:
            print("")
            print("AUTO RPS is already running.")
            print("")
            return

        args = line.strip().split()

        if len(args) >= 1:
            try:
                self.auto_rps_interval = max(
                    5,
                    int(args[0])
                )
            except:
                pass

        if len(args) >= 2:
            try:
                self.auto_rps_hysteresis = max(
                    0.0,
                    float(args[1])
                )
            except:
                pass

        if len(args) >= 3:
            try:
                self.auto_rps_hold_down = max(
                    0,
                    int(args[2])
                )
            except:
                pass

        if len(args) >= 4:
            try:
                self.auto_rps_duration = max(
                    self.auto_rps_interval,
                    int(args[3])
                )
            except:
                pass
        else:
            self.auto_rps_duration = 120

        self.auto_rps_cycle = 0
        self.auto_rps_start_time = None
        self.auto_rps_enabled = True

        self.auto_rps_thread = threading.Thread(
            target=self._auto_rps_loop
        )

        self.auto_rps_thread.daemon = True
        self.auto_rps_thread.start()

        print("")
        print("============================================================")
        print("                   AUTO RPS STARTED")
        print("============================================================")
        print(
            "Interval   : %d sec"
            % self.auto_rps_interval
        )
        print(
            "Hysteresis : %.2f cost units"
            % self.auto_rps_hysteresis
        )
        print(
            "Hold-down  : %d sec"
            % self.auto_rps_hold_down
        )
        print(
            "Duration   : %d sec (bounded experiment)"
            % self.auto_rps_duration
        )
        print("Bidirectional switching : ENABLED")
        print("Dynamic DSCP refresh    : ENABLED")
        print("Log file                : auto_rps_log.csv")
        print("============================================================")
        print("")


    def do_stopautorps(
            self,
            line):

        self.auto_rps_enabled = False

        print("")
        print("AUTO RPS stopped.")
        print("")


    def do_autorpsstatus(
            self,
            line):

        print("")
        print("============================================================")
        print("                   AUTO RPS STATUS")
        print("============================================================")
        print(
            "Running      : %s"
            % str(self.auto_rps_enabled)
        )
        print(
            "Interval     : %d sec"
            % self.auto_rps_interval
        )
        print(
            "Hysteresis   : %.2f"
            % self.auto_rps_hysteresis
        )
        print(
            "Hold-down    : %d sec"
            % self.auto_rps_hold_down
        )
        print(
            "Duration     : %d sec"
            % self.auto_rps_duration
        )
        print(
            "Current Path : %s"
            % self._path_text(self.current_path)
        )
        print(
            "Current Cost : %s"
            % str(self.current_path_cost)
        )
        print(
            "Switch Count : %d"
            % self.switch_count
        )
        print(
            "Cycles       : %d"
            % self.auto_rps_cycle
        )
        print("============================================================")
        print("")


    # =========================================================
    # PHASE 7 - GREEN / ENERGY-AWARE NETWORK CONTROL
    # =========================================================

    def _phase10_run_cycle_safe(self, max_retries=3):
        """Run one RPS cycle and retry transient EINTR failures.

        Phase 10/11 runs synchronously from the Mininet CLI.  No Auto-RPS
        worker thread is created, which avoids concurrent Node.cmd() calls.
        """
        attempt = 0
        while attempt < max_retries:
            try:
                self._auto_rps_once()
                return True
            except (OSError, IOError) as exc:
                err = getattr(exc, 'errno', None)
                if err == 4:  # EINTR - interrupted system call
                    attempt += 1
                    print('Transient EINTR during cycle; retry %d/%d...' %
                          (attempt, max_retries))
                    for router in self.routers.values():
                        try:
                            router.cmd('killall -q tcpdump 2>/dev/null')
                        except:
                            pass
                    time.sleep(0.5)
                    continue
                raise
            except Exception as exc:
                # Empty-string exceptions from Mininet/pexpect are treated as
                # transient once the shell is still responsive.
                if not str(exc).strip():
                    attempt += 1
                    print('Transient Mininet command interruption; retry %d/%d...' %
                          (attempt, max_retries))
                    time.sleep(0.5)
                    continue
                raise
        return False

    def _phase10_threshold_experiment(self, thresholds, duration, phase11=False):
        """Sequential threshold experiment used by Phase 10 and Phase 11."""
        import csv
        import os

        base = os.path.dirname(os.path.abspath(__file__))
        summary_name = 'phase11_green_performance_comparison.csv' if phase11 else 'threshold_comparison.csv'
        summary_path = os.path.join(base, summary_name)
        detail_path = os.path.join(base, 'phase11_cycle_metrics.csv')

        for path in [summary_path, detail_path] if phase11 else [summary_path]:
            try:
                if os.path.exists(path): os.remove(path)
            except:
                pass

        summary_header = [
            'threshold_percent','duration_sec','cycles','successful_cycles',
            'switch_count','sleep_events','wake_events','active_links',
            'sleeping_links','viable_paths','baseline_energy_j',
            'proposed_energy_j','energy_saving_percent'
        ]
        if phase11:
            summary_header += [
                'avg_throughput_mbps','avg_utilization_percent','avg_latency_ms',
                'avg_jitter_ms','avg_packet_loss_percent','tcp_retransmissions_delta'
            ]
        with open(summary_path, 'wb') as f:
            csv.writer(f).writerow(summary_header)

        if phase11:
            with open(detail_path, 'wb') as f:
                csv.writer(f).writerow([
                    'threshold_percent','cycle','elapsed_sec','traffic_priority',
                    'selected_path','active_links','sleeping_links','viable_paths',
                    'avg_throughput_mbps','avg_utilization_percent','latency_ms',
                    'jitter_ms','packet_loss_percent','tcp_retransmissions_cumulative',
                    'energy_saving_percent'
                ])

        print('')
        print('============================================================')
        print('   PHASE %d - %s' % (11 if phase11 else 10,
              'GREEN ENERGY + NETWORK PERFORMANCE' if phase11 else 'THRESHOLD EVALUATION (FIXED)'))
        print('============================================================')
        print('Thresholds : %s' % ', '.join(['%.1f%%' % x for x in thresholds]))
        print('Duration   : %d sec per threshold' % duration)
        print('Traffic    : %d sec per trial' % (duration + 30))
        print('Execution  : SYNCHRONOUS / NO AUTO-RPS BACKGROUND THREAD')
        print('============================================================')

        for idx, threshold in enumerate(thresholds):
            print('')
            print('################ TRIAL %d/%d : %.1f%% ################' %
                  (idx + 1, len(thresholds), threshold))

            self.auto_rps_enabled = False
            if self.auto_rps_thread is not None and self.auto_rps_thread.is_alive():
                try: self.auto_rps_thread.join(2.0)
                except: pass
            self.do_stoptraffic('')
            for router in self.routers.values():
                try: router.cmd('killall -q tcpdump 2>/dev/null')
                except: pass
            time.sleep(1)

            self.green.reset_experiment(True)
            self.green.enabled = True
            self.green.mode = 'simulate'
            self.green.underutil_threshold = threshold
            self.green.required_cycles = 3
            self.green.wake_threshold = 70.0

            self.auto_rps_cycle = 0
            self.switch_count = 0
            self.current_path = None
            self.current_path_cost = None
            self.last_switch_time = 0
            self.auto_rps_interval = 10
            self.auto_rps_hysteresis = 3.0
            self.auto_rps_hold_down = 20
            self.auto_rps_duration = duration
            self.auto_rps_enabled = True

            self.do_traffic(str(duration + 30))
            time.sleep(2)
            start_time = time.time()
            next_deadline = start_time
            successful = 0
            perf = []
            retrans_start = get_total_tcp_retransmissions(self.net.hosts + list(self.routers.values())) if phase11 else 0

            # Exactly one synchronous control iteration per 10-second slot.
            max_cycles = max(1, int(duration / self.auto_rps_interval))
            for slot in range(max_cycles):
                if not self.auto_rps_enabled:
                    break
                next_deadline = start_time + slot * self.auto_rps_interval
                wait = next_deadline - time.time()
                if wait > 0: time.sleep(wait)

                ok = False
                try:
                    ok = self._phase10_run_cycle_safe(3)
                except Exception as exc:
                    print('TRIAL CYCLE FAILED: %s' % str(exc))
                if not ok:
                    print('Cycle skipped after retries; trial continues safely.')
                    continue
                successful += 1

                if phase11:
                    metrics = self.last_link_metrics or {}
                    throughputs = [m.get('throughput_mbps', 0.0) for m in metrics.values()]
                    utils = [m.get('utilization_percent', 0.0) for m in metrics.values()]
                    avg_thr = sum(throughputs) / len(throughputs) if throughputs else 0.0
                    avg_util = sum(utils) / len(utils) if utils else 0.0
                    ping = measure_ping_metrics(self.net.get('h1'), '192.168.6.10', count=5)
                    st_now = self.green.status_text()
                    base_e = st_now['baseline_energy_j']; prop_e = st_now['proposed_energy_j']
                    es = ((base_e-prop_e)/base_e*100.0) if base_e > 0 else 0.0
                    retrans_now = get_total_tcp_retransmissions(self.net.hosts + list(self.routers.values()))
                    priority = self.classifier.get_network_priority(self.last_flows or [], destination_prefix='192.168.6.')
                    row = [
                        '%.2f' % threshold, self.auto_rps_cycle, '%.2f' % (time.time()-start_time),
                        priority, self._path_text(self.current_path), len(st_now['active']),
                        len(st_now['sleeping']), st_now['viable_paths'], '%.6f' % avg_thr,
                        '%.6f' % avg_util, '%.6f' % ping['latency_ms'],
                        '%.6f' % ping['jitter_ms'], '%.6f' % ping['packet_loss_percent'],
                        retrans_now, '%.6f' % es
                    ]
                    with open(detail_path, 'ab') as f: csv.writer(f).writerow(row)
                    perf.append((avg_thr, avg_util, ping['latency_ms'], ping['jitter_ms'], ping['packet_loss_percent']))

            self.auto_rps_enabled = False
            st = self.green.status_text()
            baseline = st['baseline_energy_j']; proposed = st['proposed_energy_j']
            saving = ((baseline-proposed)/baseline*100.0) if baseline > 0 else 0.0
            row = [
                '%.2f' % threshold, duration, self.auto_rps_cycle, successful,
                self.switch_count, st['sleep_events'], st['wake_events'],
                len(st['active']), len(st['sleeping']), st['viable_paths'],
                '%.3f' % baseline, '%.3f' % proposed, '%.3f' % saving
            ]
            if phase11:
                def av(i): return sum(x[i] for x in perf)/len(perf) if perf else 0.0
                retrans_end = get_total_tcp_retransmissions(self.net.hosts + list(self.routers.values()))
                row += ['%.6f' % av(0),'%.6f' % av(1),'%.6f' % av(2),
                        '%.6f' % av(3),'%.6f' % av(4), max(0, retrans_end-retrans_start)]
            with open(summary_path, 'ab') as f: csv.writer(f).writerow(row)

            print('TRIAL RESULT: threshold %.1f%% | saving %.2f%% | sleeping %d | viable paths %d | successful cycles %d/%d' %
                  (threshold, saving, len(st['sleeping']), st['viable_paths'], successful, max_cycles))
            self.do_stoptraffic('')
            time.sleep(2)

        self.auto_rps_enabled = False
        self.green.enabled = False
        self.green.wake_all()
        print('')
        print('============================================================')
        print('PHASE %d COMPLETE' % (11 if phase11 else 10))
        print('CSV: %s' % summary_name)
        if phase11:
            print('Cycle CSV: phase11_cycle_metrics.csv')
            print('Run: python3 generate_phase11_graphs.py')
        else:
            print('Run: python3 generate_threshold_graphs.py')
        print('============================================================')
        print('')

    def do_thresholdtest(self, line):
        """thresholdtest [comma-separated thresholds] [duration]"""
        args = line.strip().split(); thresholds = [5.0,10.0,15.0,20.0]; duration = 120
        if len(args) >= 1:
            try: thresholds = [float(x) for x in args[0].split(',') if x.strip()]
            except: print('Invalid thresholds. Example: thresholdtest 5,10,15,20 120'); return
        if len(args) >= 2:
            try: duration = max(30, int(args[1]))
            except: pass
        self._phase10_threshold_experiment(thresholds, duration, False)

    def do_phase11test(self, line):
        """phase11test [comma-separated thresholds] [duration]

        Runs the fixed threshold experiment and additionally measures network
        performance so energy savings can be evaluated against QoS impact.
        """
        args = line.strip().split(); thresholds = [5.0,10.0,15.0,20.0]; duration = 120
        if len(args) >= 1:
            try: thresholds = [float(x) for x in args[0].split(',') if x.strip()]
            except: print('Invalid thresholds. Example: phase11test 5,10,15,20 120'); return
        if len(args) >= 2:
            try: duration = max(30, int(args[1]))
            except: pass
        self._phase10_threshold_experiment(thresholds, duration, True)

    def do_greenon(self, line):
        """
        greenon [underutil%] [cycles] [wake%] [simulate|live]

        Example:
          greenon 10 3 70 simulate
        """
        args = line.strip().split()

        if len(args) >= 1:
            try:
                self.green.underutil_threshold = float(args[0])
            except:
                pass

        if len(args) >= 2:
            try:
                self.green.required_cycles = max(1, int(args[1]))
            except:
                pass

        if len(args) >= 3:
            try:
                self.green.wake_threshold = float(args[2])
            except:
                pass

        if len(args) >= 4:
            requested = args[3].lower()
            if requested in ('simulate', 'live'):
                self.green.mode = requested

        self.green.enabled = True
        self.green.last_energy_time = None

        print("")
        print("============================================================")
        print("               GREEN ENERGY CONTROL ENABLED")
        print("============================================================")
        print(
            "Underutilized threshold : %.2f %%"
            % self.green.underutil_threshold
        )
        print(
            "Required low-load cycles: %d"
            % self.green.required_cycles
        )
        print(
            "Wake threshold          : %.2f %%"
            % self.green.wake_threshold
        )
        print("Mode                    : %s" % self.green.mode.upper())
        print("Energy CSV              : energy_statistics.csv")
        print("")
        if self.green.mode == 'simulate':
            print("SIMULATE mode models link sleep without bringing interfaces down.")
        else:
            print("LIVE mode can bring eligible backbone interfaces DOWN/UP.")
            print("A connectivity test is used; failed sleep attempts are rolled back.")
        print("============================================================")
        print("")


    def do_greenoff(self, line):
        self.green.enabled = False
        count = self.green.wake_all()

        print("")
        print("Green energy control disabled.")
        print("Sleeping links restored: %d" % count)
        print("")


    def do_greenstatus(self, line):
        status = self.green.status_text()

        print("")
        print("============================================================")
        print("                 GREEN ENERGY STATUS")
        print("============================================================")
        print("Enabled                 : %s" % str(status['enabled']))
        print("Mode                    : %s" % status['mode'].upper())
        print(
            "Underutilized threshold : %.2f %%"
            % status['underutil_threshold']
        )
        print("Low-load cycles required: %d" % status['required_cycles'])
        print("Wake threshold          : %.2f %%" % status['wake_threshold'])
        print("Active links            : %s" % ', '.join(status['active']))
        print(
            "Sleeping links          : %s"
            % (', '.join(status['sleeping']) if status['sleeping'] else 'NONE')
        )
        print("Sleep events            : %d" % status['sleep_events'])
        print("Wake events             : %d" % status['wake_events'])
        print("Viable R1-R6 paths       : %d" % status['viable_paths'])
        print("Minimum paths preserved : %d" % status['min_viable_paths'])
        print("Baseline energy         : %.2f J" % status['baseline_energy_j'])
        print("Proposed energy         : %.2f J" % status['proposed_energy_j'])
        print("============================================================")
        print("")


    def do_wakeall(self, line):
        count = self.green.wake_all()
        print("")
        print("Woke/restored %d sleeping backbone link(s)." % count)
        print("")


    def do_rps(
            self,
            line):

        interval = 2.0

        print("")
        print("============================================================")
        print("   PACKET CLASSIFICATION + UTILIZATION-AWARE RPS")
        print("============================================================")
        print("")
        print(
            "Sampling for %.1f seconds..."
            % interval
        )

        before = read_all_link_stats(
            self.routers
        )

        capture_files = start_packet_capture(
            self.routers,
            interval
        )

        time.sleep(
            interval + 0.3
        )

        after = read_all_link_stats(
            self.routers
        )

        metrics = calculate_link_metrics(
            self.routers,
            before,
            after,
            interval
        )

        self.last_link_metrics = metrics

        print_link_metrics(
            metrics
        )

        raw_capture = read_packet_captures(
            capture_files
        )

        packets = self.classifier.parse_tcpdump(
            raw_capture
        )

        flows = self.classifier.classify_packets(
            packets,
            interval
        )

        self.last_flows = flows

        self.classifier.print_report(
            flows
        )

        # -----------------------------------------------------
        # DYNAMIC QoS
        # -----------------------------------------------------
        # The same dynamically classified HIGH/MEDIUM/LOW flows
        # are now converted into DSCP marks and HTB queue classes.
        self.last_qos_assignments = apply_dynamic_qos(
            self.routers,
            flows
        )

        self.qos_active = True

        print_qos_assignments(
            self.last_qos_assignments
        )

        priority = (
            self.classifier.get_network_priority(
                flows,
                destination_prefix='192.168.6.'
            )
        )

        print("")
        print(
            "RPS TRAFFIC PRIORITY FOR "
            "192.168.6.0/24 = %s"
            % priority
        )

        link_utilizations = {}

        for link in metrics:
            link_utilizations[link] = (
                metrics[link][
                    'utilization_percent'
                ]
            )

        selected_path, best_cost = (
            self.rps.select_best_path(
                link_utilizations,
                priority
            )
        )

        apply_bidirectional_rps_path(
            self.routers,
            selected_path
        )

        self.current_path = list(selected_path)
        self.current_path_cost = best_cost
        self.last_switch_time = time.time()
        self.switch_count += 1

        print("")
        print(
            "Final Selected Path = %s"
            % " -> ".join(
                [
                    router.upper()
                    for router in selected_path
                ]
            )
        )
        print(
            "Best Cost = %.2f"
            % best_cost
        )
        print("")

    # =========================================================
    # ROUTES / HELP
    # =========================================================

    def do_routecheck(
            self,
            line):

        print("")
        print("============================================================")
        print("                  CURRENT ROUTING TABLES")
        print("============================================================")

        for router_name in [
            'r1',
            'r2',
            'r3',
            'r4',
            'r5',
            'r6'
        ]:

            print("")
            print(
                "%s:"
                % router_name.upper()
            )

            print(
                self.routers[
                    router_name
                ].cmd(
                    'ip route'
                )
            )

        print("============================================================")

    # =========================================================
    # QoS CONTROL
    # =========================================================

    def do_qosstatus(
            self,
            line):

        show_qos_status(
            self.routers
        )


    def do_qosoff(
            self,
            line):

        print("")
        print("============================================================")
        print("              SWITCHING TO WITHOUT-QoS BASELINE")
        print("============================================================")

        disable_qos(
            self.routers
        )

        self.qos_active = False
        self.last_qos_assignments = []

        print("")
        print("Dynamic DSCP marking removed.")
        print("Backbone restored to one neutral 100 Mbps class.")
        print("2 ms delay and 1000-packet queue are preserved.")
        print("============================================================")
        print("")


    def do_rpshelp(
            self,
            line):

        print("")
        print("============================================================")
        print("RPS COMMANDS")
        print("============================================================")
        print("traffic")
        print("  Start five traffic flows")
        print("")
        print("graph")
        print("  Regenerate graphs from latest monitor CSV files")
        print("")
        print("experiment")
        print("  Run Phase 4 120-sec experiment, sample at 30/60/90/120 sec")
        print("")
        print("rps")
        print("  One manual classify + QoS + bidirectional RPS cycle")
        print("")
        print("greenon [underutil%] [cycles] [wake%] [simulate|live]")
        print("thresholdtest [5,10,15,20] [duration]")
        print("phase11test [5,10,15,20] [duration]")
        print("autorps [interval] [hysteresis] [hold-down] [duration]")
        print("traffic [duration]  (default 150 sec)")
        print("  Enable energy-aware link consolidation")
        print("")
        print("greenstatus")
        print("  Show active/sleeping links and energy counters")
        print("")
        print("greenoff")
        print("  Disable Green control and restore sleeping links")
        print("")
        print("wakeall")
        print("  Restore all sleeping links")
        print("")
        print("autorps [interval] [hysteresis] [hold-down]")
        print("  Start continuous RPS, e.g. autorps 10 3 20")
        print("")
        print("autorpsstatus")
        print("  Show current path, cost, cycles and switch count")
        print("")
        print("stopautorps")
        print("  Stop continuous RPS")
        print("")
        print("qosstatus")
        print("  Show active QoS classes and DSCP rules")
        print("")
        print("qosoff")
        print("  Restore neutral without-QoS baseline")
        print("")
        print("routecheck")
        print("  Show routing tables")
        print("")
        print("wakeburst [mbps] [duration]")
        print("stoptraffic")
        print("  Stop iperf")
        print("")
        print("rpshelp")
        print("  Show this help")
        print("============================================================")


# =============================================================
# TOPOLOGY
# =============================================================

def create_topology():

    net = Mininet(
        switch=OVSSwitch,
        controller=None,
        autoSetMacs=True
    )

    print("*** Creating routers")

    r1 = net.addHost(
        'r1',
        cls=Router,
        ip=None
    )

    r2 = net.addHost(
        'r2',
        cls=Router,
        ip=None
    )

    r3 = net.addHost(
        'r3',
        cls=Router,
        ip=None
    )

    r4 = net.addHost(
        'r4',
        cls=Router,
        ip=None
    )

    r5 = net.addHost(
        'r5',
        cls=Router,
        ip=None
    )

    r6 = net.addHost(
        'r6',
        cls=Router,
        ip=None
    )

    print("*** Creating switches")

    s1 = net.addSwitch(
        's1',
        failMode='standalone'
    )

    s2 = net.addSwitch(
        's2',
        failMode='standalone'
    )

    s3 = net.addSwitch(
        's3',
        failMode='standalone'
    )

    s4 = net.addSwitch(
        's4',
        failMode='standalone'
    )

    s5 = net.addSwitch(
        's5',
        failMode='standalone'
    )

    s6 = net.addSwitch(
        's6',
        failMode='standalone'
    )

    print("*** Creating hosts")

    h1 = net.addHost(
        'h1',
        ip='192.168.1.10/24',
        defaultRoute='via 192.168.1.1'
    )

    h2 = net.addHost(
        'h2',
        ip='192.168.1.11/24',
        defaultRoute='via 192.168.1.1'
    )

    h3 = net.addHost(
        'h3',
        ip='192.168.2.10/24',
        defaultRoute='via 192.168.2.1'
    )

    h4 = net.addHost(
        'h4',
        ip='192.168.2.11/24',
        defaultRoute='via 192.168.2.1'
    )

    h5 = net.addHost(
        'h5',
        ip='192.168.3.10/24',
        defaultRoute='via 192.168.3.1'
    )

    h6 = net.addHost(
        'h6',
        ip='192.168.3.11/24',
        defaultRoute='via 192.168.3.1'
    )

    h7 = net.addHost(
        'h7',
        ip='192.168.4.10/24',
        defaultRoute='via 192.168.4.1'
    )

    h8 = net.addHost(
        'h8',
        ip='192.168.4.11/24',
        defaultRoute='via 192.168.4.1'
    )

    h9 = net.addHost(
        'h9',
        ip='192.168.5.10/24',
        defaultRoute='via 192.168.5.1'
    )

    h10 = net.addHost(
        'h10',
        ip='192.168.5.11/24',
        defaultRoute='via 192.168.5.1'
    )

    h11 = net.addHost(
        'h11',
        ip='192.168.6.10/24',
        defaultRoute='via 192.168.6.1'
    )

    h12 = net.addHost(
        'h12',
        ip='192.168.6.11/24',
        defaultRoute='via 192.168.6.1'
    )

    # ---------------------------------------------------------
    # HOST -> SWITCH
    # ---------------------------------------------------------

    net.addLink(h1, s1)
    net.addLink(h2, s1)

    net.addLink(h3, s2)
    net.addLink(h4, s2)

    net.addLink(h5, s3)
    net.addLink(h6, s3)

    net.addLink(h7, s4)
    net.addLink(h8, s4)

    net.addLink(h9, s5)
    net.addLink(h10, s5)

    net.addLink(h11, s6)
    net.addLink(h12, s6)

    # ---------------------------------------------------------
    # SWITCH -> ROUTER
    # ---------------------------------------------------------

    net.addLink(s1, r1)
    net.addLink(s2, r2)
    net.addLink(s3, r3)
    net.addLink(s4, r4)
    net.addLink(s5, r5)
    net.addLink(s6, r6)

    # ---------------------------------------------------------
    # ROUTER -> ROUTER
    #
    # Each backbone link is now a controlled 100 Mbps TCLink.
    # ---------------------------------------------------------

    link_options = {
        'bw': BACKBONE_BW_MBPS,
        'delay': '2ms',
        'max_queue_size': 1000,
        'use_htb': True
    }

    net.addLink(
        r1,
        r2,
        cls=TCLink,
        **link_options
    )

    net.addLink(
        r1,
        r3,
        cls=TCLink,
        **link_options
    )

    net.addLink(
        r2,
        r4,
        cls=TCLink,
        **link_options
    )

    net.addLink(
        r2,
        r5,
        cls=TCLink,
        **link_options
    )

    net.addLink(
        r3,
        r4,
        cls=TCLink,
        **link_options
    )

    net.addLink(
        r3,
        r5,
        cls=TCLink,
        **link_options
    )

    net.addLink(
        r4,
        r6,
        cls=TCLink,
        **link_options
    )

    net.addLink(
        r5,
        r6,
        cls=TCLink,
        **link_options
    )

    print("*** Starting network")

    net.start()

    for switch in net.switches:

        switch.cmd(
            'ovs-vsctl set-fail-mode %s standalone'
            % switch.name
        )

    for router in [
        r1,
        r2,
        r3,
        r4,
        r5,
        r6
    ]:

        router.cmd(
            'sysctl -w net.ipv4.ip_forward=1'
        )

    # =========================================================
    # ROUTER IP ADDRESSES
    # =========================================================

    r1.cmd('ip addr add 192.168.1.1/24 dev r1-eth0')
    r1.cmd('ip addr add 10.0.12.1/30 dev r1-eth1')
    r1.cmd('ip addr add 10.0.13.1/30 dev r1-eth2')

    r2.cmd('ip addr add 192.168.2.1/24 dev r2-eth0')
    r2.cmd('ip addr add 10.0.12.2/30 dev r2-eth1')
    r2.cmd('ip addr add 10.0.24.1/30 dev r2-eth2')
    r2.cmd('ip addr add 10.0.25.1/30 dev r2-eth3')

    r3.cmd('ip addr add 192.168.3.1/24 dev r3-eth0')
    r3.cmd('ip addr add 10.0.13.2/30 dev r3-eth1')
    r3.cmd('ip addr add 10.0.34.1/30 dev r3-eth2')
    r3.cmd('ip addr add 10.0.35.1/30 dev r3-eth3')

    r4.cmd('ip addr add 192.168.4.1/24 dev r4-eth0')
    r4.cmd('ip addr add 10.0.24.2/30 dev r4-eth1')
    r4.cmd('ip addr add 10.0.34.2/30 dev r4-eth2')
    r4.cmd('ip addr add 10.0.46.1/30 dev r4-eth3')

    r5.cmd('ip addr add 192.168.5.1/24 dev r5-eth0')
    r5.cmd('ip addr add 10.0.25.2/30 dev r5-eth1')
    r5.cmd('ip addr add 10.0.35.2/30 dev r5-eth2')
    r5.cmd('ip addr add 10.0.56.1/30 dev r5-eth3')

    r6.cmd('ip addr add 192.168.6.1/24 dev r6-eth0')
    r6.cmd('ip addr add 10.0.46.2/30 dev r6-eth1')
    r6.cmd('ip addr add 10.0.56.2/30 dev r6-eth2')

    # =========================================================
    # STATIC ROUTES
    # =========================================================

    r1.cmd('ip route add 192.168.2.0/24 via 10.0.12.2')
    r1.cmd('ip route add 192.168.3.0/24 via 10.0.13.2')
    r1.cmd('ip route add 192.168.4.0/24 via 10.0.12.2')
    r1.cmd('ip route add 192.168.5.0/24 via 10.0.12.2')
    r1.cmd('ip route add 192.168.6.0/24 via 10.0.12.2')

    r2.cmd('ip route add 192.168.1.0/24 via 10.0.12.1')
    r2.cmd('ip route add 192.168.3.0/24 via 10.0.12.1')
    r2.cmd('ip route add 192.168.4.0/24 via 10.0.24.2')
    r2.cmd('ip route add 192.168.5.0/24 via 10.0.25.2')
    r2.cmd('ip route add 192.168.6.0/24 via 10.0.24.2')

    r3.cmd('ip route add 192.168.1.0/24 via 10.0.13.1')
    r3.cmd('ip route add 192.168.2.0/24 via 10.0.13.1')
    r3.cmd('ip route add 192.168.4.0/24 via 10.0.34.2')
    r3.cmd('ip route add 192.168.5.0/24 via 10.0.35.2')
    r3.cmd('ip route add 192.168.6.0/24 via 10.0.34.2')

    r4.cmd('ip route add 192.168.1.0/24 via 10.0.24.1')
    r4.cmd('ip route add 192.168.2.0/24 via 10.0.24.1')
    r4.cmd('ip route add 192.168.3.0/24 via 10.0.34.1')
    r4.cmd('ip route add 192.168.5.0/24 via 10.0.24.1')
    r4.cmd('ip route add 192.168.6.0/24 via 10.0.46.2')

    r5.cmd('ip route add 192.168.1.0/24 via 10.0.25.1')
    r5.cmd('ip route add 192.168.2.0/24 via 10.0.25.1')
    r5.cmd('ip route add 192.168.3.0/24 via 10.0.35.1')
    r5.cmd('ip route add 192.168.4.0/24 via 10.0.25.1')
    r5.cmd('ip route add 192.168.6.0/24 via 10.0.56.2')

    r6.cmd('ip route add 192.168.1.0/24 via 10.0.46.1')
    r6.cmd('ip route add 192.168.2.0/24 via 10.0.46.1')
    r6.cmd('ip route add 192.168.3.0/24 via 10.0.46.1')
    r6.cmd('ip route add 192.168.4.0/24 via 10.0.46.1')
    r6.cmd('ip route add 192.168.5.0/24 via 10.0.56.1')

    routers = {
        'r1': r1,
        'r2': r2,
        'r3': r3,
        'r4': r4,
        'r5': r5,
        'r6': r6
    }

    rps = RPSController()
    classifier = TrafficClassifier()

    print("")
    print("============================================================")
    print("              RPS NETWORK TOPOLOGY READY")
    print("============================================================")
    print("")
    print(
        "Backbone link capacity: %.0f Mbps"
        % BACKBONE_BW_MBPS
    )
    print("Backbone delay: 2 ms/link")
    print("")
    print("Paths:")
    print("1. R1 -> R2 -> R4 -> R6")
    print("2. R1 -> R2 -> R5 -> R6")
    print("3. R1 -> R3 -> R4 -> R6")
    print("4. R1 -> R3 -> R5 -> R6")
    print("")
    print("Step 4 dynamic packet classification: ENABLED internally in RPS")
    print("Phase 4 monitoring/statistics: handled by experiment")
    print("")
    print("Commands:")
    print("  traffic")
    print("  graph")
    print("  experiment")
    print("  rps")
    print("  qosstatus")
    print("  qosoff")
    print("  routecheck")
    print("  wakeburst")
    print("  stoptraffic")
    print("  rpshelp")
    print("============================================================")

    RPSCLI(
        net,
        routers,
        rps,
        classifier
    )

    net.stop()


if __name__ == '__main__':

    setLogLevel('info')

    create_topology()

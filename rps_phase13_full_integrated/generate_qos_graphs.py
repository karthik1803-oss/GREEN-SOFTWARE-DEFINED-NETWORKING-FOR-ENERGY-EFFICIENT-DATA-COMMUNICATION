#!/usr/bin/env python3

"""
Generate QoS experiment graphs from experiment_summary.csv.

Usage:
    python3 generate_qos_graphs.py experiment_summary.csv

The CSV is produced by the Mininet 'experiment' command.
"""

import csv
import os
import sys
import matplotlib.pyplot as plt


def read_rows(path):
    rows = []

    with open(path, newline='') as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append({
                'time_sec': int(row['time_sec']),
                'average_throughput_mbps':
                    float(row['average_throughput_mbps']),
                'average_utilization_percent':
                    float(row['average_utilization_percent']),
                'packet_loss_percent':
                    float(row['packet_loss_percent']),
                'latency_ms':
                    float(row['latency_ms']),
                'jitter_proxy_ms':
                    float(row['jitter_proxy_ms']),
                'tcp_retransmissions_interval':
                    int(row['tcp_retransmissions_interval']),
                'tcp_retransmissions_cumulative':
                    int(row['tcp_retransmissions_cumulative']),
                'expected_transmissions':
                    float('nan')
                    if row['expected_transmissions'] == 'inf'
                    else float(row['expected_transmissions'])
            })

    return rows


def save_line(times, values, ylabel, title, filename):
    plt.figure(figsize=(8, 5))
    plt.plot(times, values, marker='o')
    plt.xlabel('Time (s)')
    plt.ylabel(ylabel)
    plt.title(title)
    plt.xticks(times)
    plt.tight_layout()
    plt.savefig(filename, dpi=160)
    plt.close()


def main():
    if len(sys.argv) < 2:
        path = 'experiment_summary.csv'
    else:
        path = sys.argv[1]

    rows = read_rows(path)

    if not rows:
        print('No experiment rows found.')
        return 1

    base_dir = os.path.dirname(os.path.abspath(path))
    outdir = os.path.join(base_dir, 'qos_graphs')

    if not os.path.exists(outdir):
        os.makedirs(outdir)

    t = [r['time_sec'] for r in rows]

    save_line(
        t,
        [r['average_throughput_mbps'] for r in rows],
        'Throughput (Mbps)',
        'Average Throughput vs Time',
        os.path.join(outdir, 'throughput_vs_time.png')
    )

    save_line(
        t,
        [r['average_utilization_percent'] for r in rows],
        'Utilization (%)',
        'Average Utilization vs Time',
        os.path.join(outdir, 'utilization_vs_time.png')
    )

    save_line(
        t,
        [r['packet_loss_percent'] for r in rows],
        'Packet Loss (%)',
        'Packet Loss vs Time',
        os.path.join(outdir, 'packet_loss_vs_time.png')
    )

    save_line(
        t,
        [r['latency_ms'] for r in rows],
        'Latency (ms)',
        'Latency vs Time',
        os.path.join(outdir, 'latency_vs_time.png')
    )

    save_line(
        t,
        [r['jitter_proxy_ms'] for r in rows],
        'Jitter Proxy (ms)',
        'Jitter vs Time',
        os.path.join(outdir, 'jitter_vs_time.png')
    )

    save_line(
        t,
        [r['tcp_retransmissions_interval'] for r in rows],
        'TCP Retransmissions / 30 s',
        'Interval TCP Retransmissions vs Time',
        os.path.join(outdir, 'tcp_retransmissions_interval_vs_time.png')
    )

    save_line(
        t,
        [r['tcp_retransmissions_cumulative'] for r in rows],
        'Cumulative TCP Retransmissions',
        'Cumulative TCP Retransmissions vs Time',
        os.path.join(outdir, 'tcp_retransmissions_cumulative_vs_time.png')
    )

    print('QoS graphs generated in:')
    print(outdir)
    return 0


if __name__ == '__main__':
    sys.exit(main())

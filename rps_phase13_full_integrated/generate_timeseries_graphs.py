#!/usr/bin/env python3

import csv
import os
import sys
import matplotlib.pyplot as plt


def read_network(path):
    rows = []

    with open(path, newline='') as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append({
                'time_sec': int(row['time_sec']),
                'avg_throughput_mbps': float(row['avg_throughput_mbps']),
                'packet_loss_percent': float(row['packet_loss_percent']),
                'configured_bandwidth_mbps': float(row['configured_bandwidth_mbps']),
                'avg_utilization_percent': float(row['avg_utilization_percent']),
                'latency_ms': float(row['latency_ms']),
                'jitter_ms': float(row['jitter_ms']),
                'tcp_retransmissions_actual': int(row['tcp_retransmissions_actual']),
                'expected_transmissions': (
                    float('nan')
                    if row['expected_transmissions'] == 'inf'
                    else float(row['expected_transmissions'])
                )
            })

    return rows


def read_links(path):
    rows = []

    with open(path, newline='') as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append({
                'time_sec': int(row['time_sec']),
                'link': row['link'],
                'throughput_mbps': float(row['throughput_mbps']),
                'bandwidth_mbps': float(row['bandwidth_mbps']),
                'utilization_percent': float(row['utilization_percent'])
            })

    return rows


def save_line(x, y, xlabel, ylabel, title, path):
    plt.figure(figsize=(8, 5))
    plt.plot(x, y, marker='o')
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.xticks(x)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def main():

    if len(sys.argv) != 3:
        print(
            'Usage: python3 generate_timeseries_graphs.py '
            'network_statistics.csv link_statistics.csv'
        )
        return 1

    network_csv = sys.argv[1]
    link_csv = sys.argv[2]

    network = read_network(network_csv)
    links = read_links(link_csv)

    if not network:
        print('No network data found.')
        return 1

    base_dir = os.path.dirname(
        os.path.abspath(network_csv)
    )

    outdir = os.path.join(
        base_dir,
        'graphs_timeseries'
    )

    if not os.path.exists(outdir):
        os.makedirs(outdir)

    t = [row['time_sec'] for row in network]

    save_line(
        t,
        [row['avg_throughput_mbps'] for row in network],
        'Time (s)',
        'Throughput (Mbps)',
        'Throughput vs Time',
        os.path.join(outdir, 'throughput_vs_time.png')
    )

    save_line(
        t,
        [row['packet_loss_percent'] for row in network],
        'Time (s)',
        'Packet loss (%)',
        'Packet Loss vs Time',
        os.path.join(outdir, 'packet_loss_vs_time.png')
    )

    save_line(
        t,
        [row['configured_bandwidth_mbps'] for row in network],
        'Time (s)',
        'Bandwidth (Mbps)',
        'Configured Bandwidth vs Time',
        os.path.join(outdir, 'bandwidth_vs_time.png')
    )

    save_line(
        t,
        [row['latency_ms'] for row in network],
        'Time (s)',
        'Latency (ms)',
        'Latency vs Time',
        os.path.join(outdir, 'latency_vs_time.png')
    )

    save_line(
        t,
        [row['jitter_ms'] for row in network],
        'Time (s)',
        'Jitter proxy (ms)',
        'Jitter vs Time',
        os.path.join(outdir, 'jitter_vs_time.png')
    )

    save_line(
        t,
        [row['tcp_retransmissions_actual'] for row in network],
        'Time (s)',
        'TCP retransmissions',
        'TCP Retransmissions vs Time',
        os.path.join(outdir, 'retransmission_vs_time.png')
    )

    save_line(
        t,
        [row['avg_utilization_percent'] for row in network],
        'Time (s)',
        'Average utilization (%)',
        'Average Link Utilization vs Time',
        os.path.join(outdir, 'utilization_vs_time.png')
    )

    save_line(
        t,
        [row['expected_transmissions'] for row in network],
        'Time (s)',
        'Expected transmissions',
        'Expected Transmissions vs Time',
        os.path.join(outdir, 'expected_transmissions_vs_time.png')
    )

    unique_links = sorted(set(row['link'] for row in links))

    plt.figure(figsize=(10, 6))
    for link in unique_links:
        subset = [row for row in links if row['link'] == link]
        subset.sort(key=lambda r: r['time_sec'])
        plt.plot(
            [r['time_sec'] for r in subset],
            [r['utilization_percent'] for r in subset],
            marker='o',
            label=link
        )

    plt.xlabel('Time (s)')
    plt.ylabel('Utilization (%)')
    plt.title('Per-Link Utilization vs Time')
    plt.xticks(t)
    plt.legend(fontsize=8, ncol=2)
    plt.tight_layout()
    plt.savefig(
        os.path.join(outdir, 'per_link_utilization_vs_time.png'),
        dpi=160
    )
    plt.close()

    plt.figure(figsize=(10, 6))
    for link in unique_links:
        subset = [row for row in links if row['link'] == link]
        subset.sort(key=lambda r: r['time_sec'])
        plt.plot(
            [r['time_sec'] for r in subset],
            [r['throughput_mbps'] for r in subset],
            marker='o',
            label=link
        )

    plt.xlabel('Time (s)')
    plt.ylabel('Throughput (Mbps)')
    plt.title('Per-Link Throughput vs Time')
    plt.xticks(t)
    plt.legend(fontsize=8, ncol=2)
    plt.tight_layout()
    plt.savefig(
        os.path.join(outdir, 'per_link_throughput_vs_time.png'),
        dpi=160
    )
    plt.close()

    print('')
    print('Time-series graphs generated in:')
    print(outdir)

    return 0


if __name__ == '__main__':
    sys.exit(main())

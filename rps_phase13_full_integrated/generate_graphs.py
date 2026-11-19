#!/usr/bin/env python3

import csv
import os
import sys

import matplotlib.pyplot as plt


def read_link_csv(path):
    rows = []

    with open(path, newline='') as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append({
                'link': row['link'],
                'throughput_mbps': float(row['throughput_mbps']),
                'bandwidth_mbps': float(row['bandwidth_mbps']),
                'utilization_percent': float(row['utilization_percent']),
                'packets_sent': int(row['packets_sent']),
                'packets_received': int(row['packets_received']),
                'packets_dropped': int(row['packets_dropped']),
                'drop_percent': float(row['drop_percent'])
            })

    return rows


def read_network_csv(path):
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        row = next(reader)

        return {
            'avg_throughput_mbps': float(row['avg_throughput_mbps']),
            'avg_utilization_percent': float(row['avg_utilization_percent']),
            'latency_ms': float(row['latency_ms']),
            'packet_loss_percent': float(row['packet_loss_percent']),
            'jitter_ms': float(row['jitter_ms']),
            'tcp_retransmissions': int(row['tcp_retransmissions']),
            'packets_sent': int(row['packets_sent']),
            'packets_received': int(row['packets_received']),
            'packets_dropped': int(row['packets_dropped'])
        }


def save_link_throughput(rows, outdir):
    links = [r['link'] for r in rows]
    throughput = [r['throughput_mbps'] for r in rows]

    plt.figure(figsize=(10, 6))
    plt.bar(links, throughput)
    plt.xlabel('Backbone link')
    plt.ylabel('Throughput (Mbps)')
    plt.title('Backbone Link Throughput')
    plt.xticks(rotation=35)
    plt.tight_layout()
    plt.savefig(
        os.path.join(outdir, 'link_throughput.png'),
        dpi=160
    )
    plt.close()


def save_link_utilization(rows, outdir):
    links = [r['link'] for r in rows]
    utilization = [r['utilization_percent'] for r in rows]

    plt.figure(figsize=(10, 6))
    plt.bar(links, utilization)
    plt.xlabel('Backbone link')
    plt.ylabel('Utilization (%)')
    plt.title('Backbone Link Utilization')
    plt.ylim(0, max(100, max(utilization) * 1.1 if utilization else 100))
    plt.xticks(rotation=35)
    plt.tight_layout()
    plt.savefig(
        os.path.join(outdir, 'link_utilization.png'),
        dpi=160
    )
    plt.close()


def save_packet_counts(rows, outdir):
    links = [r['link'] for r in rows]
    sent = [r['packets_sent'] for r in rows]
    received = [r['packets_received'] for r in rows]
    dropped = [r['packets_dropped'] for r in rows]

    x = list(range(len(links)))
    width = 0.25

    plt.figure(figsize=(11, 6))
    plt.bar([v - width for v in x], sent, width=width, label='Sent')
    plt.bar(x, received, width=width, label='Received')
    plt.bar([v + width for v in x], dropped, width=width, label='Dropped')
    plt.xlabel('Backbone link')
    plt.ylabel('Packet count')
    plt.title('Packets Sent, Received and Dropped')
    plt.xticks(x, links, rotation=35)
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        os.path.join(outdir, 'packet_counts.png'),
        dpi=160
    )
    plt.close()


def save_network_quality(network, outdir):
    names = [
        'Latency (ms)',
        'Jitter (ms)',
        'Packet loss (%)'
    ]

    values = [
        network['latency_ms'],
        network['jitter_ms'],
        network['packet_loss_percent']
    ]

    plt.figure(figsize=(8, 6))
    plt.bar(names, values)
    plt.ylabel('Measured value')
    plt.title('End-to-End Network Quality')
    plt.tight_layout()
    plt.savefig(
        os.path.join(outdir, 'network_quality.png'),
        dpi=160
    )
    plt.close()


def main():
    if len(sys.argv) != 3:
        print(
            'Usage: python3 generate_graphs.py '
            'link_statistics_latest.csv '
            'network_statistics_latest.csv'
        )
        return 1

    link_csv = sys.argv[1]
    network_csv = sys.argv[2]

    if not os.path.exists(link_csv):
        print('Missing: %s' % link_csv)
        return 1

    if not os.path.exists(network_csv):
        print('Missing: %s' % network_csv)
        return 1

    rows = read_link_csv(link_csv)
    network = read_network_csv(network_csv)

    outdir = os.path.join(
        os.path.dirname(
            os.path.abspath(link_csv)
        ),
        'graphs'
    )

    if not os.path.exists(outdir):
        os.makedirs(outdir)

    save_link_throughput(rows, outdir)
    save_link_utilization(rows, outdir)
    save_packet_counts(rows, outdir)
    save_network_quality(network, outdir)

    print('')
    print('Graphs generated:')
    print('  %s' % os.path.join(outdir, 'link_throughput.png'))
    print('  %s' % os.path.join(outdir, 'link_utilization.png'))
    print('  %s' % os.path.join(outdir, 'packet_counts.png'))
    print('  %s' % os.path.join(outdir, 'network_quality.png'))

    return 0


if __name__ == '__main__':
    sys.exit(main())

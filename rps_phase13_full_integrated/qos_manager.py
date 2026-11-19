#!/usr/bin/env python2
# -*- coding: utf-8 -*-

"""
Dynamic QoS manager for the Mininet/RPS project.

QoS model:
    HIGH   -> DSCP EF   (46) -> HTB class 1:10
    MEDIUM -> DSCP AF21 (18) -> HTB class 1:20
    LOW    -> DSCP CS1  (8)  -> HTB class 1:30

The classifier still decides HIGH/MEDIUM/LOW dynamically.
No traffic flow is permanently hard-coded to a priority class.
"""

BACKBONE_BW_MBIT = 100
LINK_DELAY = '2ms'
QUEUE_LIMIT = 1000

PRIORITY_CONFIG = {
    'HIGH': {
        'dscp': 46,
        'tos_hex': '0xb8',
        'classid': '1:10',
        'rate': '50mbit',
        'ceil': '100mbit',
        'prio': 0
    },
    'MEDIUM': {
        'dscp': 18,
        'tos_hex': '0x48',
        'classid': '1:20',
        'rate': '30mbit',
        'ceil': '100mbit',
        'prio': 1
    },
    'LOW': {
        'dscp': 8,
        'tos_hex': '0x20',
        'classid': '1:30',
        'rate': '20mbit',
        'ceil': '100mbit',
        'prio': 2
    }
}


def get_backbone_interfaces():
    """
    All router-facing backbone interfaces.
    QoS is applied in both directions by configuring every router endpoint.
    """
    return {
        'r1': ['r1-eth1', 'r1-eth2'],
        'r2': ['r2-eth1', 'r2-eth2', 'r2-eth3'],
        'r3': ['r3-eth1', 'r3-eth2', 'r3-eth3'],
        'r4': ['r4-eth1', 'r4-eth2', 'r4-eth3'],
        'r5': ['r5-eth1', 'r5-eth2', 'r5-eth3'],
        'r6': ['r6-eth1', 'r6-eth2']
    }


def source_router_for_ip(ip):
    if ip.startswith('192.168.1.'):
        return 'r1'
    if ip.startswith('192.168.2.'):
        return 'r2'
    if ip.startswith('192.168.3.'):
        return 'r3'
    if ip.startswith('192.168.4.'):
        return 'r4'
    if ip.startswith('192.168.5.'):
        return 'r5'
    if ip.startswith('192.168.6.'):
        return 'r6'
    return None


def _run(router, command):
    return router.cmd(command)


def clear_dynamic_marking(routers):
    """
    Remove the project-specific dynamic DSCP marking chain.
    """
    for router_name in routers:
        router = routers[router_name]

        _run(
            router,
            'iptables -t mangle -D PREROUTING -j RPS_QOS '
            '2>/dev/null || true'
        )

        _run(
            router,
            'iptables -t mangle -F RPS_QOS '
            '2>/dev/null || true'
        )

        _run(
            router,
            'iptables -t mangle -X RPS_QOS '
            '2>/dev/null || true'
        )


def prepare_dynamic_marking(routers):
    """
    Build one clean RPS_QOS chain in each router namespace.
    """
    clear_dynamic_marking(routers)

    for router_name in routers:
        router = routers[router_name]

        _run(
            router,
            'iptables -t mangle -N RPS_QOS'
        )

        _run(
            router,
            'iptables -t mangle -A PREROUTING -j RPS_QOS'
        )


def configure_priority_queues(routers):
    """
    Replace the router-backbone egress qdisc with a three-class HTB tree.

    Guaranteed rates:
        HIGH   50 Mbps
        MEDIUM 30 Mbps
        LOW    20 Mbps

    All classes may borrow unused capacity up to 100 Mbps.
    Each class preserves the project's 2 ms delay and 1000-packet limit.
    """
    interfaces = get_backbone_interfaces()

    for router_name in interfaces:
        router = routers[router_name]

        for interface in interfaces[router_name]:

            _run(
                router,
                'tc qdisc del dev %s root 2>/dev/null || true'
                % interface
            )

            _run(
                router,
                'tc qdisc add dev %s root handle 1: '
                'htb default 30'
                % interface
            )

            # HIGH
            _run(
                router,
                'tc class add dev %s parent 1: classid 1:10 '
                'htb rate 50mbit ceil 100mbit prio 0'
                % interface
            )

            # MEDIUM
            _run(
                router,
                'tc class add dev %s parent 1: classid 1:20 '
                'htb rate 30mbit ceil 100mbit prio 1'
                % interface
            )

            # LOW
            _run(
                router,
                'tc class add dev %s parent 1: classid 1:30 '
                'htb rate 20mbit ceil 100mbit prio 2'
                % interface
            )

            # Keep the same emulated delay/queue behavior under each class.
            _run(
                router,
                'tc qdisc add dev %s parent 1:10 handle 110: '
                'netem delay %s limit %d'
                % (
                    interface,
                    LINK_DELAY,
                    QUEUE_LIMIT
                )
            )

            _run(
                router,
                'tc qdisc add dev %s parent 1:20 handle 120: '
                'netem delay %s limit %d'
                % (
                    interface,
                    LINK_DELAY,
                    QUEUE_LIMIT
                )
            )

            _run(
                router,
                'tc qdisc add dev %s parent 1:30 handle 130: '
                'netem delay %s limit %d'
                % (
                    interface,
                    LINK_DELAY,
                    QUEUE_LIMIT
                )
            )

            # DSCP/TOS filters.
            _run(
                router,
                'tc filter add dev %s parent 1: protocol ip prio 1 '
                'u32 match ip tos 0xb8 0xfc flowid 1:10'
                % interface
            )

            _run(
                router,
                'tc filter add dev %s parent 1: protocol ip prio 2 '
                'u32 match ip tos 0x48 0xfc flowid 1:20'
                % interface
            )

            _run(
                router,
                'tc filter add dev %s parent 1: protocol ip prio 3 '
                'u32 match ip tos 0x20 0xfc flowid 1:30'
                % interface
            )


def configure_neutral_queues(routers):
    """
    Restore a neutral 100 Mbps single-class backbone while keeping
    the original 2 ms delay and 1000-packet queue.

    This is useful as the WITHOUT-QoS baseline.
    """
    interfaces = get_backbone_interfaces()

    for router_name in interfaces:
        router = routers[router_name]

        for interface in interfaces[router_name]:

            _run(
                router,
                'tc qdisc del dev %s root 2>/dev/null || true'
                % interface
            )

            _run(
                router,
                'tc qdisc add dev %s root handle 1: htb default 1'
                % interface
            )

            _run(
                router,
                'tc class add dev %s parent 1: classid 1:1 '
                'htb rate 100mbit ceil 100mbit'
                % interface
            )

            _run(
                router,
                'tc qdisc add dev %s parent 1:1 handle 10: '
                'netem delay %s limit %d'
                % (
                    interface,
                    LINK_DELAY,
                    QUEUE_LIMIT
                )
            )


def mark_flows(routers, flows):
    """
    Convert dynamically classified flows to DSCP marks.

    Only TCP/UDP flows with a visible destination port are installed.
    The source router is derived from the source IP subnet.
    """
    prepare_dynamic_marking(routers)

    installed = []

    seen = set()

    for flow in flows:

        priority = flow.get('priority', 'LOW')

        if priority not in PRIORITY_CONFIG:
            priority = 'LOW'

        protocol = flow.get('protocol', '').lower()

        if protocol not in ('tcp', 'udp'):
            continue

        src_ip = flow.get('src_ip', '')
        dst_ip = flow.get('dst_ip', '')
        dst_port = int(flow.get('dst_port', 0))

        if dst_port <= 0:
            continue

        router_name = source_router_for_ip(src_ip)

        if router_name is None:
            continue

        key = (
            router_name,
            src_ip,
            dst_ip,
            protocol,
            dst_port,
            priority
        )

        if key in seen:
            continue

        seen.add(key)

        dscp = PRIORITY_CONFIG[priority]['dscp']

        command = (
            'iptables -t mangle -A RPS_QOS '
            '-s %s -d %s -p %s --dport %d '
            '-j DSCP --set-dscp %d'
            % (
                src_ip,
                dst_ip,
                protocol,
                dst_port,
                dscp
            )
        )

        output = _run(
            routers[router_name],
            command
        )

        installed.append({
            'router': router_name,
            'src_ip': src_ip,
            'dst_ip': dst_ip,
            'protocol': protocol.upper(),
            'dst_port': dst_port,
            'priority': priority,
            'dscp': dscp,
            'output': output.strip()
        })

    return installed


def apply_dynamic_qos(routers, flows):
    """
    Full dynamic QoS operation:
      1. create HIGH/MEDIUM/LOW egress queues
      2. mark observed flows using their dynamically calculated priority
    """
    configure_priority_queues(routers)
    return mark_flows(routers, flows)


def disable_qos(routers):
    """
    Switch to neutral single-class forwarding.
    """
    clear_dynamic_marking(routers)
    configure_neutral_queues(routers)


def print_qos_assignments(assignments):
    print("")
    print("============================================================")
    print("                DYNAMIC QoS ASSIGNMENTS")
    print("============================================================")

    if not assignments:
        print("")
        print("No TCP/UDP flow rules were installed.")
        print("============================================================")
        return

    for item in assignments:
        print("")
        print(
            "%s  %s -> %s:%d  %s"
            % (
                item['router'].upper(),
                item['src_ip'],
                item['dst_ip'],
                item['dst_port'],
                item['protocol']
            )
        )
        print(
            "Priority = %-6s  DSCP = %d"
            % (
                item['priority'],
                item['dscp']
            )
        )

        if item['output']:
            print(
                "iptables output: %s"
                % item['output']
            )

    print("")
    print("Queue policy:")
    print("  HIGH   -> 50 Mbps guaranteed, ceil 100 Mbps, priority 0")
    print("  MEDIUM -> 30 Mbps guaranteed, ceil 100 Mbps, priority 1")
    print("  LOW    -> 20 Mbps guaranteed, ceil 100 Mbps, priority 2")
    print("")
    print("Unused capacity can be borrowed up to 100 Mbps.")
    print("============================================================")


def show_qos_status(routers):
    """
    Print queue/classes on the first backbone interface and dynamic marking
    rules on source routers. This keeps terminal output readable.
    """
    print("")
    print("============================================================")
    print("                     QoS STATUS")
    print("============================================================")
    print("")

    sample_router = routers['r1']

    print("R1 backbone interface r1-eth1:")
    print(
        sample_router.cmd(
            'tc class show dev r1-eth1'
        )
    )

    print("R1 QoS filters:")
    print(
        sample_router.cmd(
            'tc filter show dev r1-eth1 parent 1:'
        )
    )

    for router_name in ['r1', 'r2', 'r3']:
        print(
            "%s dynamic DSCP rules:"
            % router_name.upper()
        )
        print(
            routers[router_name].cmd(
                'iptables -t mangle -L RPS_QOS -n -v '
                '2>/dev/null || true'
            )
        )

    print("============================================================")

#!/usr/bin/env python2
# -*- coding: utf-8 -*-


class RPSController(object):

    def __init__(self):

        self.paths = [
            ['r1', 'r2', 'r4', 'r6'],
            ['r1', 'r2', 'r5', 'r6'],
            ['r1', 'r3', 'r4', 'r6'],
            ['r1', 'r3', 'r5', 'r6']
        ]

        self.current_path = None
        self.current_cost = None

    # =========================================================
    # LINK COST FROM UTILIZATION %
    # =========================================================

    def calculate_link_cost(self, utilization_percent):

        if utilization_percent <= 10:
            return 1

        elif utilization_percent <= 30:
            return 2

        elif utilization_percent <= 50:
            return 4

        elif utilization_percent <= 70:
            return 6

        elif utilization_percent <= 90:
            return 8

        else:
            return 10

    def get_link_utilization(
            self,
            link_utilizations,
            router1,
            router2):

        key1 = (router1, router2)
        key2 = (router2, router1)

        if key1 in link_utilizations:
            return link_utilizations[key1]

        if key2 in link_utilizations:
            return link_utilizations[key2]

        return 0.0

    # =========================================================
    # PRIORITY-AWARE PATH COST
    # =========================================================

    def calculate_path_cost(
            self,
            path,
            link_utilizations,
            traffic_priority):

        link_costs = []

        for i in range(len(path) - 1):

            router1 = path[i]
            router2 = path[i + 1]

            utilization = self.get_link_utilization(
                link_utilizations,
                router1,
                router2
            )

            cost = self.calculate_link_cost(
                utilization
            )

            link_costs.append(cost)

        if not link_costs:
            return 0.0

        base_cost = sum(link_costs)
        bottleneck_cost = max(link_costs)

        # HIGH priority strongly avoids a congested bottleneck.
        if traffic_priority == 'HIGH':
            return (
                float(base_cost) +
                (2.0 * float(bottleneck_cost))
            )

        # MEDIUM priority uses a balanced bottleneck penalty.
        elif traffic_priority == 'MEDIUM':
            return (
                float(base_cost) +
                float(bottleneck_cost)
            )

        # LOW priority mainly uses ordinary total path cost.
        return float(base_cost)

    # =========================================================
    # SELECT BEST PATH
    # =========================================================

    def select_best_path(
            self,
            link_utilizations,
            traffic_priority):

        print("")
        print("============================================================")
        print("             PRIORITY-AWARE RPS PATH SELECTION")
        print("============================================================")
        print("")
        print("Observed Traffic Priority = %s" % traffic_priority)
        print("")
        print("Available Paths:")
        print("------------------------------------------------------------")

        best_path = None
        best_cost = float('inf')

        for path in self.paths:

            path_cost = self.calculate_path_cost(
                path,
                link_utilizations,
                traffic_priority
            )

            util_text = []

            for i in range(len(path) - 1):
                u = self.get_link_utilization(
                    link_utilizations,
                    path[i],
                    path[i + 1]
                )

                util_text.append("%.1f%%" % u)

            print(
                "%s | Util = [%s] | Cost = %.2f"
                % (
                    " -> ".join(
                        [router.upper() for router in path]
                    ),
                    ", ".join(util_text),
                    path_cost
                )
            )

            if path_cost < best_cost:
                best_cost = path_cost
                best_path = path

        print("------------------------------------------------------------")
        print("")
        print("SELECTED BEST PATH:")
        print(
            " -> ".join(
                [router.upper() for router in best_path]
            )
        )
        print("")
        print("TOTAL PRIORITY-AWARE COST = %.2f" % best_cost)
        print("============================================================")

        self.current_path = list(best_path)
        self.current_cost = best_cost

        return best_path, best_cost

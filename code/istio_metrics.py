from prometheus_api_client import PrometheusConnect

class IstioMetrics:
    def __init__(self, prometheus_url):
        self.prom = PrometheusConnect(url=prometheus_url, disable_ssl=True)

    def get_request_durations(self, namespace):
        query = (
            f'sum(rate(istio_request_duration_milliseconds_sum{{reporter="source", destination_service_namespace="{namespace}"}}[5m])) by (source_workload, destination_workload) / '
            f'sum(rate(istio_request_duration_milliseconds_count{{reporter="source", destination_service_namespace="{namespace}"}}[5m])) by (source_workload, destination_workload)'
        )
        result = self.prom.custom_query(query)
        return self.parse_istio_metrics(result)

    @staticmethod
    def parse_istio_metrics(result):
        edges = []
        for item in result:
            metric = item['metric']
            source = metric.get('source_workload', 'unknown')
            destination = metric.get('destination_workload', 'unknown')
            duration = float(item['value'][1])
            if source != 'unknown' and destination != 'unknown' and duration > 0:
                edges.append((source, destination, duration))
        return edges

    def get_probe_icmp_durations(self):
        query = 'probe_icmp_duration_seconds{phase="rtt"}'
        result = self.prom.custom_query(query)
        return self.parse_probe_icmp_durations(result)

    @staticmethod
    def parse_probe_icmp_durations(result):
        durations = {}
        for item in result:
            instance = item['metric']['instance']
            job = item['metric']['job']
            value_seconds = float(item['value'][1])
            value_ms = round(value_seconds * 1000, 1)
            if job not in durations:
                durations[job] = {}
            durations[job][instance] = value_ms
        return durations

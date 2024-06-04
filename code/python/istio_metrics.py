from prometheus_api_client import PrometheusConnect

class IstioMetrics:
    def __init__(self, prometheus_url):
        self.prom = PrometheusConnect(url=prometheus_url, disable_ssl=True)

    def get_request_durations(self, namespace):
        query = f'istio_request_duration_milliseconds_sum{{kubernetes_namespace="paper2"}} / istio_request_duration_milliseconds_count{{kubernetes_namespace="paper2"}}'
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
            # Exclude edges with 'unknown' source or destination
            if source != 'unknown' and destination != 'unknown' and duration > 0:
                edges.append((source, destination, duration))
        return edges

from prometheus_api_client import PrometheusConnect

class IstioMetrics:
    def __init__(self, prometheus_url):
        self.prom = PrometheusConnect(url=prometheus_url, disable_ssl=True)

    def get_request_durations(self, namespace):
        #query = f'rate(istio_request_duration_milliseconds_sum{{kubernetes_namespace="{namespace}"}}[1h]) / \
        #   rate(istio_request_duration_milliseconds_count{{kubernetes_namespace="{namespace}"}}[1h])'
    
        
        query = (
            f'('
            f'istio_request_duration_milliseconds_sum{{kubernetes_namespace="{namespace}"}} - '
            f'istio_request_duration_milliseconds_sum{{kubernetes_namespace="{namespace}"}} offset 1h) '
            f'/' #1000 / '
            f'(istio_requests_total{{kubernetes_namespace="{namespace}"}} - '
            f'istio_requests_total{{kubernetes_namespace="{namespace}"}} offset 1h)'
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
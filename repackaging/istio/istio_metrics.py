from prometheus_api_client import PrometheusConnect

def connect_to_prometheus(prometheus_url):
    return PrometheusConnect(url=prometheus_url, disable_ssl=True)

def get_request_durations(prom, namespace):
    query = (
        f'rate(istio_request_duration_milliseconds_sum{{kubernetes_namespace="{namespace}"}}[120s]) '
        f'/ '
        f'rate(istio_requests_total{{kubernetes_namespace="{namespace}"}}[120s])'
    )

    result = prom.custom_query(query)
    return parse_istio_metrics(result)

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

def get_probe_icmp_durations(prom):
    query = 'probe_icmp_duration_seconds{phase="rtt"}'
    result = prom.custom_query(query)
    return parse_probe_icmp_durations(result)

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

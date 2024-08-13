import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os 

class KubernetesClient:
    def __init__(self, namespace):
        self.namespace = namespace
        config.load_kube_config()
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_objects_api = client.CustomObjectsApi()
        self.virtualservice_dir = "/home/dnc/master/paper2024/trafficyaml"
        self.trafficyaml_dir = "/home/dnc/master/paper2024/trafficyaml"

    def get_pods_for_service(self, service_name):
        pods = self.v1.list_namespaced_pod(self.namespace, label_selector=f'app={service_name}').items
        return [pod.metadata.name for pod in pods]
    
    def get_node_resources(self, node_name):
        node = self.v1.read_node(node_name)
        allocatable = node.status.allocatable
        return {
            "cpu": allocatable["cpu"],
            "memory": allocatable["memory"]
        }   

    def get_node_for_pod(self, pod_name):
        pod = self.v1.read_namespaced_pod(pod_name, self.namespace)
        return pod.spec.node_name

    def get_service_for_deployment(self, deployment_name):
        deployment = self.apps_v1.read_namespaced_deployment(name=deployment_name, namespace=self.namespace)
        deployment_labels = deployment.spec.selector.match_labels
        label_selector = ",".join([f"{key}={value}" for key, value in deployment_labels.items()])
        services = self.v1.list_namespaced_service(self.namespace, label_selector=label_selector).items
        return [service.metadata.name for service in services]
    
    def get_versions_for_service(self, service_name):
        pods = self.v1.list_namespaced_pod(self.namespace, label_selector=f'app={service_name}').items
        versions = set()
        for pod in pods:
            version = pod.metadata.labels.get('version')
            if version:
                versions.add(version)
        return versions

    def get_pods(self):
        pods = self.v1.list_namespaced_pod(self.namespace).items
        return [pod.metadata.name for pod in pods]



    def get_deployment_resources(self, deployment_name, namespace, k8s_client):
        deployment = self.apps_v1.read_namespaced_deployment(deployment_name, namespace)
        containers = deployment.spec.template.spec.containers
        total_cpu = 0
        total_memory = 0

        for container in containers:
            if container.resources.requests:
                if container.resources.requests.get("cpu"):
                    cpu_request = container.resources.requests["cpu"]
                    if cpu_request.endswith('m'):
                        total_cpu += int(cpu_request.rstrip('m'))
                    else:
                        total_cpu += int(float(cpu_request) * 1000)  # Convert cores to millicores

                if container.resources.requests.get("memory"):
                    memory_request = container.resources.requests["memory"]
                    if memory_request.endswith('Mi'):
                        total_memory += int(memory_request.rstrip('Mi'))
                    elif memory_request.endswith('Gi'):
                        total_memory += int(float(memory_request.rstrip('Gi')) * 1024)  # Convert Gi to Mi
                    elif memory_request.endswith('Ki'):
                        total_memory += int(memory_request.rstrip('Ki')) // 1024  # Convert Ki to Mi

        return {"cpu": total_cpu, "memory": total_memory}



    def get_service_versions(self):
        services = self.v1.list_namespaced_service(self.namespace).items
        versions = {}
        
        for service in services:
            service_name = service.metadata.name
            versions[service_name] = set()
            
            pods = self.v1.list_namespaced_pod(self.namespace, label_selector=f'app={service_name}').items
            for pod in pods:
                version = pod.metadata.labels.get('version')
                if version:
                    versions[service_name].add(version)
        
        return versions

    def get_labels_from_deployment(self, deployment_name):
        deployment = self.apps_v1.read_namespaced_deployment(name=deployment_name, namespace=self.namespace)
        return deployment.metadata.labels.get('app'), deployment.metadata.labels.get('version')

    def apply_yaml(self, yaml_content):
        yaml_string = yaml.dump(yaml_content, default_flow_style=False)
        yaml_object = yaml.safe_load(yaml_string)
        group, version = yaml_object["apiVersion"].split('/')
        plural = yaml_object["kind"].lower() + "s"
        name = yaml_object["metadata"]["name"]
        namespace = yaml_object.get("metadata", {}).get("namespace", "default")
        
        try:
            self.custom_objects_api.create_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                body=yaml_object
            )
        except ApiException as e:
            if e.status == 409:
                existing_object = self.custom_objects_api.get_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    name=name
                )
                yaml_object["metadata"]["resourceVersion"] = existing_object["metadata"]["resourceVersion"]
                self.custom_objects_api.replace_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    name=name,
                    body=yaml_object
                )
            else:
                raise

    def create_virtual_service_yaml(self, service_routes):
        grouped_routes = {}
        for route in service_routes:
            source, source_version, destination, destination_version, weight = route
            key = (source, source_version)
            if key not in grouped_routes:
                grouped_routes[key] = {}
            if destination not in grouped_routes[key]:
                grouped_routes[key][destination] = {}
            grouped_routes[key][destination][destination_version] = weight

        yamls = {}
        for (source, source_version), destinations in grouped_routes.items():
            for destination, version_weights in destinations.items():
                file_path = os.path.join(self.virtualservice_dir, f"{source}-to-{destination}-vs.yaml")
                
                # Create new YAML content
                routes_yaml = []
                for version, weight in version_weights.items():
                    routes_yaml.append({
                        'destination': {
                            'host': destination,
                            'subset': version
                        },
                        'weight': weight
                    })

                match_entry = {
                    'match': [
                        {
                            'sourceLabels': {
                                'app': source,
                                'version': source_version
                            }
                        }
                    ],
                    'route': routes_yaml
                }

                if os.path.exists(file_path):
                    with open(file_path, 'r') as file:
                        existing_content = yaml.safe_load(file)

                    # Check if the same source version exists
                    updated = False
                    for http_entry in existing_content['spec']['http']:
                        match = http_entry['match'][0]
                        if match['sourceLabels']['version'] == source_version:
                            http_entry['route'] = routes_yaml
                            updated = True
                            break

                    if not updated:
                        existing_content['spec']['http'].append(match_entry)

                    yaml_content = existing_content
                else:
                    yaml_content = {
                        'apiVersion': 'networking.istio.io/v1alpha3',
                        'kind': 'VirtualService',
                        'metadata': {
                            'name': f'{source}-to-{destination}-vs',
                            'namespace': 'paper2'
                        },
                        'spec': {
                            'hosts': [destination],
                            'http': [match_entry]
                        }
                    }

                yamls[(source, source_version)] = yaml_content

                # Save to file
                with open(file_path, 'w') as file:
                    yaml.dump(yaml_content, file, default_flow_style=False)
                print(f"Updated/Created VirtualService YAML at {file_path}")

        return yamls

    def create_destination_rule_yaml(self, service, versions):
        subsets = ""
        for version in versions:
            subsets += f"""
  - name: {version}
    labels:
      version: {version}"""
        
        yaml_content = f"""
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: {service}-dr
  namespace: {self.namespace}
spec:
  host: {service}
  subsets:{subsets}
  trafficPolicy:
    loadBalancer:
      simple: LEAST_CONN
"""

        return yaml.safe_load(yaml_content)

    def reset_weights(self, original_edges):
        for edge in original_edges:
            source, destination, weight = edge
            source_name, source_version = self.get_labels_from_deployment(source)
            destination_name, destination_version = self.get_labels_from_deployment(destination)
            virtual_service_yaml = self.create_virtual_service_yaml([(source_name, source_version, destination_name, destination_version, weight)])
            print(f"Resetting weight for {source} to {destination} to {weight}")
            self.apply_yaml(virtual_service_yaml[(source_name, destination_name)])

    def distribute_remaining_weights(self, source, destination_weights):
        remaining_destinations = [dest for dest, weight in destination_weights.items() if weight != 0]
        if not remaining_destinations:
            return

        equal_weight = 100 // len(remaining_destinations)
        for dest in remaining_destinations:
            destination_weights[dest] = equal_weight

    def apply_virtual_service(self, service_routes):
        # Delete existing files in the virtualservice and trafficyaml directories
        for directory in [self.virtualservice_dir, self.trafficyaml_dir]:
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        
        virtual_service_yamls = self.create_virtual_service_yaml(service_routes)
        for vs_yaml in virtual_service_yamls.values():
            self.apply_yaml(vs_yaml)
            # Save to trafficyaml directory
            file_path = os.path.join(self.trafficyaml_dir, f"{vs_yaml['metadata']['name']}.yaml")
            with open(file_path, 'w') as file:
                yaml.dump(vs_yaml, file, default_flow_style=False)

    def apply_destination_rules(self, service_versions):
        for service, versions in service_versions.items():
            destination_rule_yaml = self.create_destination_rule_yaml(service, versions)
            self.apply_yaml(destination_rule_yaml)
            # Save to trafficyaml directory
            file_path = os.path.join(self.trafficyaml_dir, f"{service}-dr.yaml")
            with open(file_path, 'w') as file:
                yaml.dump(destination_rule_yaml, file, default_flow_style=False)

    def update_node_selector(self, replacement_nodes):
        for service, (version, worker) in replacement_nodes.items():
            deployment_name = service
            try:
                deployment = self.apps_v1.read_namespaced_deployment(name=deployment_name, namespace=self.namespace)
            except client.exceptions.ApiException as e:
                print(f"Failed to get deployment {deployment_name}: {e}")
                continue

            try:
                node_affinity = deployment.spec.template.spec.affinity.node_affinity
                if not node_affinity:
                    deployment.spec.template.spec.affinity = client.V1Affinity(
                        node_affinity=client.V1NodeAffinity(
                            required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
                                node_selector_terms=[
                                    client.V1NodeSelectorTerm(
                                        match_expressions=[
                                            client.V1NodeSelectorRequirement(
                                                key="kubernetes.io/hostname",
                                                operator="In",
                                                values=[worker]
                                            )
                                        ]
                                    )
                                ]
                            )
                        )
                    )
                else:
                    node_selector_terms = node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms
                    for term in node_selector_terms:
                        for expression in term.match_expressions:
                            if (expression.key == "kubernetes.io/hostname" and worker not in expression.values):
                                expression.values.append(worker)
                            else:
                                term.match_expressions.append(
                                    client.V1NodeSelectorRequirement(
                                        key="kubernetes.io/hostname",
                                        operator="In",
                                        values=[worker]
                                    )
                                )
            except KeyError as e:
                print(f"KeyError: {e} in deployment {deployment_name}")
                continue

            try:
                self.apps_v1.patch_namespaced_deployment(
                    name=deployment_name,
                    namespace=self.namespace,
                    body=deployment
                )
                print(f"Updated nodeSelector for deployment {deployment_name} to {worker}")
            except client.exceptions.ApiException as e:
                print(f"Failed to update deployment {deployment_name}: {e}")

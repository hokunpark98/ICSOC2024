import copy
import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException

class KubernetesClient:
    def __init__(self, namespace):
        self.namespace = namespace
        config.load_kube_config()
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_objects_api = client.CustomObjectsApi()

    def get_pods(self):
        pods = self.v1.list_namespaced_pod(self.namespace).items
        return [pod.metadata.name for pod in pods]

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
        yaml_object = yaml.safe_load(yaml_content)
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
                # If the object already exists, fetch the existing object
                existing_object = self.custom_objects_api.get_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    name=name
                )
                # Set the resourceVersion from the existing object
                yaml_object["metadata"]["resourceVersion"] = existing_object["metadata"]["resourceVersion"]
                # Replace the existing object with the new one
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

    def create_virtual_service_yaml(self, service_routes, downstream_versions):
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
            routes_yaml = ""
            unique_destinations = {}
            for destination, version_weights in destinations.items():
                unique_destinations[destination] = version_weights
                print(f'source: {source_version} destination: {version_weights}')

            for destination, version_weights in unique_destinations.items():
                non_zero_versions = {v: w for v, w in version_weights.items() if w != 0}
                num_versions = len(non_zero_versions)


                if num_versions > 0:
                    equal_weight = 100 // num_versions
                    for version in version_weights:
                        if version_weights[version] != 0:
                            version_weights[version] = equal_weight
                        else:
                            version_weights[version] = 0
                else:
                    for version in downstream_versions.get(destination, []):
                        version_weights[version] = 0

                for version, weight in version_weights.items():
                    routes_yaml += f"""
    - destination:
        host: {destination}
        subset: {version}
      weight: {weight}"""

                    if destination in downstream_versions:
                        for version in downstream_versions[destination]:
                            if version not in version_weights:
                                routes_yaml += f"""
    - destination:
        host: {destination}
        subset: {version}
      weight: 0"""

            if routes_yaml:  # Only add if there are routes
                yaml_content = f"""
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
    name: {source}-to-{destination}-vs
    namespace: {self.namespace}
spec:
  hosts:
  - {destination}
  http:
  - match:
    - sourceLabels:
        app: {source}
        version: {source_version}
    route:{routes_yaml}
"""
                yamls[(source, source_version)] = yaml_content

        return yamls




    def create_destination_rule_yaml(self, service, versions):
        subsets = ""
        for version in versions:
            subsets += f"""
  - name: {version}
    labels:
      version: {version}"""
        
        return f"""
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

    def reset_weights(self, original_edges):
        for edge in original_edges:
            source, destination, weight = edge
            source_name, source_version = self.get_labels_from_deployment(source)
            destination_name, destination_version = self.get_labels_from_deployment(destination)
            virtual_service_yaml = self.create_virtual_service_yaml([(source_name, source_version, destination_name, destination_version, weight)], {})
            print(f"Resetting weight for {source} to {destination} to {weight}")
            self.apply_yaml(virtual_service_yaml[(source_name, destination_name)])

    def distribute_remaining_weights(self, source, destination_weights):
        remaining_destinations = [dest for dest, weight in destination_weights.items() if weight != 0]
        if not remaining_destinations:
            return

        equal_weight = 100 // len(remaining_destinations)
        for dest in remaining_destinations:
            destination_weights[dest] = equal_weight

    def apply_virtual_service(self, service_routes, downstream_versions):
        virtual_service_yamls = self.create_virtual_service_yaml(service_routes, downstream_versions)
        for vs_yaml in virtual_service_yamls.values():
            print(vs_yaml)
            #self.apply_yaml(vs_yaml)

    def apply_destination_rules(self, service_versions):
        for service, versions in service_versions.items():
            destination_rule_yaml = self.create_destination_rule_yaml(service, versions)
            print(destination_rule_yaml)
            #self.apply_yaml(destination_rule_yaml)








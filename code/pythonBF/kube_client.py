from kubernetes import client, config

class KubernetesClient:
    def __init__(self, namespace):
        config.load_kube_config()
        self.namespace = namespace
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    def get_pods(self):
        pods = self.v1.list_namespaced_pod(self.namespace)
        pod_names = [pod.metadata.name for pod in pods.items]
        return pod_names

    def get_deployments(self):
        deployments = self.apps_v1.list_namespaced_deployment(self.namespace)
        deployment_dict = {}
        for deployment in deployments.items:
            deployment_name = deployment.metadata.name
            for pod in self.v1.list_namespaced_pod(self.namespace, label_selector=f'app={deployment_name}').items:
                deployment_dict[pod.metadata.name] = deployment_name
        return deployment_dict

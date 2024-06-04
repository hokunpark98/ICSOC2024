#!/bin/bash

# Get all pods in the paper2 namespace
pods=$(kubectl get pods -n paper2 -o json | jq -r '.items[] | @base64')

for pod in $pods; do
  _jq() {
    echo ${pod} | base64 --decode | jq -r ${1}
  }

  pod_name=$(_jq '.metadata.name')
  node_name=$(kubectl get pod ${pod_name} -n paper2 -o jsonpath='{.spec.nodeName}')

  echo "Labeling pod ${pod_name} with node ${node_name}"

  # Label the pod with the node name
  kubectl label pod ${pod_name} version=${node_name} -n paper2 --overwrite || echo "Failed to label pod ${pod_name}, skipping..."
done


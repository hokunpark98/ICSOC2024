#!/bin/bash

# Get all pods with the label io.kompose.service=frontend
pods=$(kubectl get pods -n default -o json | jq -r '.items[] | @base64')

for pod in $pods; do
  _jq() {
    echo ${pod} | base64 --decode | jq -r ${1}
  }

  pod_name=$(_jq '.metadata.name')
  echo "Labeling pod ${pod_name}"

done

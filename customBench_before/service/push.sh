#!/bin/bash

cd /home/dnclab/hokun/paper2/bench/service/a
docker build -t hokunpark/paper2:serviceA .
docker push hokunpark/paper2:serviceA

cd /home/dnclab/hokun/paper2/bench/service/b
docker build -t hokunpark/paper2:serviceB .
docker push hokunpark/paper2:serviceB


cd /home/dnclab/hokun/paper2/bench/service/c
docker build -t hokunpark/paper2:serviceC .
docker push hokunpark/paper2:serviceC


cd /home/dnclab/hokun/paper2/bench/service/d
docker build -t hokunpark/paper2:serviceD .
docker push hokunpark/paper2:serviceD
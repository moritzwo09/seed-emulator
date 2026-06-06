#!/bin/sh

docker compose -f output/docker-compose.yml exec -T hnode_151_web \
    ping -4 -c 3 -W 5 23.192.228.80 >/dev/null

echo "A03a: hnode_151_web can ping 23.192.228.80"

#!/bin/sh

docker compose -f output/docker-compose.yml exec -T hnode_151_web \
    curl -4 -fsS --connect-timeout 5 --max-time 20 http://23.192.228.80/ >/dev/null

echo "A03a: hnode_151_web can reach http://23.192.228.80/"

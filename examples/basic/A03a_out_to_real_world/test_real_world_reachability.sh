#!/bin/sh

docker compose -f output/docker-compose.yml exec -T hnode_151_web \
    curl -4 -fsS --connect-timeout 5 --max-time 20 http://example.com/ >/dev/null

echo "A03a: hnode_151_web can reach http://example.com/"

#!/usr/bin/env zsh
# 利用可能なツール一覧を取得

cd $(dirname $0)/../

{
    echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
    sleep 1
    echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'
    sleep 1
} | ./launch-mcp-server.sh | jq

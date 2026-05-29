#!/usr/bin/env zsh
# list_sql_servers ツールを呼び出して登録済み SQL サーバー一覧を取得する

cd $(dirname $0)/../

source ./.loadenv.sh

# MCP は initialize → notifications/initialized → tools/call の順で送る。
# ツールは "tools/call" メソッドで呼び、ツール名は params.name に渡す。
{
    echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_sql_servers", "arguments": {}}}'
    sleep 1
} | ./launch-mcp-server.sh | jq

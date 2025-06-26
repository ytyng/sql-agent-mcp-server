#!/usr/bin/env zsh
#
# 簡単なテスト用スクリプト
#

cd $(dirname $0)/../

# 一回だけテストしてレスポンスを確認
{
    echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_sql_servers", "arguments": {}}}'
    sleep 1
} | .venv/bin/python3 mcp_server.py | {
    while IFS= read -r line; do
        if echo "$line" | grep -q '"id":2'; then
            echo "=== FULL RESPONSE ==="
            echo "$line"
            echo ""
            echo "=== RESULT EXTRACTION ==="
            result=$(echo "$line" | jq -r '.result.content[0].text')
            echo "Extracted result: $result"
            echo ""
            echo "=== PARSED JSON ==="
            echo "$result" | jq '.'
            break
        fi
    done
}
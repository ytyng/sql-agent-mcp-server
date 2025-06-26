#!/usr/bin/env zsh
#
# ytyng-blog PostgreSQL サーバーの動作テスト (最終版)
#

cd $(dirname $0)/../

echo "=================================================="
echo "  ytyng-blog PostgreSQL サーバー テストスクリプト"
echo "=================================================="
echo

# カラー出力用の定数
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

run_test() {
    local tool_name="$1"
    local params="$2"
    local test_name="$3"
    
    echo -e "${BLUE}[INFO]${NC} テスト実行中: $test_name"
    
    # MCP 通信を実行
    local response=$({
        echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
        sleep 0.3
        echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
        sleep 0.3
        echo "{\"jsonrpc\": \"2.0\", \"id\": 2, \"method\": \"tools/call\", \"params\": {\"name\": \"$tool_name\", \"arguments\": $params}}"
        sleep 0.8
    } | .venv/bin/python3 mcp_server.py 2>/dev/null | grep '"id":2')
    
    if [ -n "$response" ]; then
        if echo "$response" | jq -e '.result' > /dev/null 2>&1; then
            echo -e "${GREEN}[SUCCESS]${NC} $test_name が成功しました"
            local content=$(echo "$response" | jq -r '.result.content[0].text')
            if echo "$content" | jq '.' > /dev/null 2>&1; then
                echo "$content" | jq '.'
            else
                echo "$content"
            fi
        else
            echo -e "${RED}[ERROR]${NC} $test_name が失敗しました"
            echo "$response" | jq '.error'
        fi
    else
        echo -e "${RED}[ERROR]${NC} $test_name でレスポンスが取得できませんでした"
    fi
    
    echo "---"
}

# テスト実行
run_test "list_sql_servers" "{}" "SQL サーバー一覧取得"
run_test "get_table_list" '{"server_name": "ytyng-blog"}' "テーブル一覧取得"
run_test "execute_sql" '{"server_name": "ytyng-blog", "sql": "SELECT version();"}' "PostgreSQL バージョン確認"
run_test "execute_sql" '{"server_name": "ytyng-blog", "sql": "SELECT NOW() as current_time;"}' "現在の日時取得"
run_test "execute_sql" '{"server_name": "ytyng-blog", "sql": "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = '\''public'\'';"}' "テーブル数取得"

echo
echo -e "${GREEN}[SUCCESS]${NC} 全てのテストが完了しました！"
echo "=================================================="
#!/usr/bin/env zsh
#
# ytyng-blog PostgreSQL サーバーの動作テスト用スクリプト
# MCP サーバーの各機能をテストします
#

cd $(dirname $0)/../

# カラー出力用の定数
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ログ関数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# MCP リクエストを送信してレスポンスを取得
send_mcp_request() {
    local tool_name="$1"
    local params="$2"
    local request_id="$3"
    
    log_info "テスト実行中: $tool_name"
    
    # MCP 通信を実行
    {
        # 1. 初期化リクエスト
        echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
        sleep 0.5
        
        # 2. 初期化完了通知
        echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
        sleep 0.5
        
        # 3. ツール呼び出し
        echo "{\"jsonrpc\": \"2.0\", \"id\": $request_id, \"method\": \"tools/call\", \"params\": {\"name\": \"$tool_name\", \"arguments\": $params}}"
        sleep 1
    } | .venv/bin/python3 mcp_server.py | {
        while IFS= read -r line; do
            # 対象のレスポンスが見つかったら処理
            if echo "$line" | grep -q "\"id\":$request_id"; then
                echo "$line"
                break
            fi
        done
    }
}

# JSON レスポンスをパースして結果を表示
parse_and_display_result() {
    local response="$1"
    local test_name="$2"
    
    # レスポンスをチェック
    if echo "$response" | jq -e '.result' > /dev/null 2>&1; then
        log_success "$test_name が成功しました"
        
        # レスポンスの詳細を表示
        if echo "$response" | jq -e '.result.content[0].text' > /dev/null 2>&1; then
            # JSON の内容を整形して表示
            local result_text=$(echo "$response" | jq -r '.result.content[0].text')
            
            # JSON として解析してみる
            if echo "$result_text" | jq '.' > /dev/null 2>&1; then
                log_info "レスポンス内容:"
                echo "$result_text" | jq '.' >&2
            else
                log_info "レスポンス内容 (テキスト):"
                echo "$result_text" >&2
            fi
        else
            log_info "レスポンス内容:"
            echo "$response" | jq '.result' >&2
        fi
    elif echo "$response" | jq -e '.error' > /dev/null 2>&1; then
        log_error "$test_name でエラーが発生しました"
        local error_msg=$(echo "$response" | jq -r '.error.message // .error')
        log_error "エラー: $error_msg"
    else
        log_error "$test_name で予期しないレスポンスが返されました"
        echo "$response" >&2
    fi
    
    echo "---" >&2
}

# メイン関数
main() {
    echo "==================================================" >&2
    echo "  ytyng-blog PostgreSQL サーバー テストスクリプト" >&2
    echo "==================================================" >&2
    echo >&2
    
    # 依存関係チェック
    if ! command -v jq &> /dev/null; then
        log_error "jq コマンドが見つかりません。インストールしてください:"
        echo "  brew install jq" >&2
        exit 1
    fi
    
    # .venv の存在チェック
    if [ ! -d ".venv" ]; then
        log_error ".venv ディレクトリが見つかりません。uv sync を実行してください。"
        exit 1
    fi
    
    echo >&2
    
    # テスト 1: サーバー一覧取得
    log_info "=== テスト 1: SQL サーバー一覧取得 ==="
    response=$(send_mcp_request "list_sql_servers" "{}" "2")
    parse_and_display_result "$response" "サーバー一覧取得"
    
    # テスト 2: テーブル一覧取得
    log_info "=== テスト 2: テーブル一覧取得 ==="
    response=$(send_mcp_request "get_table_list" '{"server_name": "ytyng-blog"}' "3")
    parse_and_display_result "$response" "テーブル一覧取得"
    
    # テスト 3: PostgreSQL バージョン確認
    log_info "=== テスト 3: PostgreSQL バージョン確認 ==="
    response=$(send_mcp_request "execute_sql" '{"server_name": "ytyng-blog", "sql": "SELECT version();"}' "4")
    parse_and_display_result "$response" "PostgreSQL バージョン確認"
    
    # テスト 4: 現在の日時取得
    log_info "=== テスト 4: 現在の日時取得 ==="
    response=$(send_mcp_request "execute_sql" '{"server_name": "ytyng-blog", "sql": "SELECT NOW() as current_time;"}' "5")
    parse_and_display_result "$response" "現在の日時取得"
    
    # テスト 5: データベース情報取得
    log_info "=== テスト 5: データベース情報取得 ==="
    response=$(send_mcp_request "execute_sql" '{"server_name": "ytyng-blog", "sql": "SELECT current_database(), current_user, inet_server_addr(), inet_server_port();"}' "6")
    parse_and_display_result "$response" "データベース情報取得"
    
    # テスト 6: 簡単な COUNT クエリ
    log_info "=== テスト 6: 簡単な COUNT クエリ ==="
    response=$(send_mcp_request "execute_sql" '{"server_name": "ytyng-blog", "sql": "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = '\''public'\'';"}' "7")
    parse_and_display_result "$response" "テーブル数取得"
    
    echo >&2
    log_success "全てのテストが完了しました！"
    echo "==================================================" >&2
}

# スクリプト実行
main "$@"
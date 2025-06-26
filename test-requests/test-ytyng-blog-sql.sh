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
    
    # レスポンスに result が含まれているかチェック
    if echo "$response" | jq -e '.result' > /dev/null 2>&1; then
        # MCP のレスポンスから結果を取得
        local result=$(echo "$response" | jq -r '.result.content[0].text // .result.content[0] // .result')
        
        # result が JSON 文字列かチェック
        if echo "$result" | jq -e '.success' > /dev/null 2>&1; then
            local success=$(echo "$result" | jq -r '.success')
            if [ "$success" = "true" ]; then
                log_success "$test_name が成功しました"
                
                # 行数や件数を表示
                local row_count=$(echo "$result" | jq -r '.row_count // empty')
                if [ -n "$row_count" ] && [ "$row_count" != "empty" ]; then
                    log_info "結果: $row_count 行"
                fi
                
                local count=$(echo "$result" | jq -r '.count // empty')
                if [ -n "$count" ] && [ "$count" != "empty" ]; then
                    log_info "結果: $count 件"
                fi
                
                # 実行時間を表示
                local exec_time=$(echo "$result" | jq -r '.execution_time_ms // empty')
                if [ -n "$exec_time" ] && [ "$exec_time" != "empty" ]; then
                    log_info "実行時間: ${exec_time}ms"
                fi
                
                # データの一部を表示 (最初の数行)
                if echo "$result" | jq -e '.rows' > /dev/null 2>&1; then
                    local row_count_actual=$(echo "$result" | jq '.rows | length')
                    if [ "$row_count_actual" -gt 0 ]; then
                        log_info "データサンプル (最初の3行):"
                        echo "$result" | jq -c '.rows[0:3][]' >&2
                    fi
                fi
                
                # サーバー情報を表示
                if echo "$result" | jq -e '.servers' > /dev/null 2>&1; then
                    log_info "サーバー情報:"
                    echo "$result" | jq -c '.servers[] | {name: .name, engine: .engine, description: .description}' >&2
                fi
            else
                local error_msg=$(echo "$result" | jq -r '.error // "不明なエラー"')
                log_error "$test_name が失敗しました: $error_msg"
            fi
        else
            log_info "$test_name の結果:"
            echo "$result" | jq '.' >&2 2>/dev/null || echo "$result" >&2
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
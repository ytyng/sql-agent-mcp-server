#!/usr/bin/env python3
from test_mcp_lib import MCPTestClient


def test_mangazenkan_dev_sql():
    """mangazenkan-dev サーバーに対して SQL を実行するテスト"""
    
    with MCPTestClient() as client:
        # サーバーを起動
        if not client.start_server():
            return
        
        # 初期化
        init_response = client.initialize(client_name="mangazenkan-test-client")
        if not init_response:
            print("初期化に失敗しました")
            return
            
        # initialized 通知を送信
        client.send_initialized()
        
        # server_name を指定して SQL を実行
        server_name = "mangazenkan-dev"
        
        print("\n" + "=" * 50)
        print(f"サーバー {server_name} に対して SQL を実行")
        print("=" * 50)
        
        # 1. バージョン情報を取得
        print("\n1. MySQL バージョンを取得:")
        client.call_tool("execute_sql", {
            "server_name": server_name,
            "sql": "SELECT version();"
        })
        
        # 2. 現在時刻を取得
        print("\n2. 現在時刻を取得:")
        client.call_tool("execute_sql", {
            "server_name": server_name,
            "sql": "SELECT NOW();"
        })
        
        print("\n" + "=" * 50)
        print("SQL 実行テスト完了")


if __name__ == "__main__":
    test_mangazenkan_dev_sql()
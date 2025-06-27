#!/usr/bin/env python3
from test_mcp_lib import MCPTestClient


def test_list_tools():
    """利用可能なツール一覧を取得するテスト"""
    
    with MCPTestClient() as client:
        # サーバーを起動
        if not client.start_server():
            return
        
        # 初期化
        client.initialize()
        
        # initialized 通知を送信
        client.send_initialized()
        
        # ツール一覧を取得
        print("\n" + "=" * 50)
        print("利用可能なツール一覧")
        print("=" * 50)
        
        tools_response = client.list_tools()
        
        if tools_response and "result" in tools_response and "tools" in tools_response["result"]:
            tools = tools_response["result"]["tools"]
            print(f"\n合計 {len(tools)} 個のツールが利用可能:")
            
            for tool in tools:
                print(f"\n- {tool['name']}")
                if "description" in tool:
                    print(f"  説明: {tool['description']}")
                if "inputSchema" in tool:
                    print(f"  パラメータ: {tool['inputSchema']}")
        
        print("\nテスト完了")


if __name__ == "__main__":
    test_list_tools()
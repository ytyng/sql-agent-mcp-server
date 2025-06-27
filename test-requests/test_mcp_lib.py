#!/usr/bin/env python3
"""MCP サーバーテスト用の共通ライブラリ"""
import subprocess
import json
import time
import os
from typing import Dict, Any, Optional, Tuple


class MCPTestClient:
    """MCP サーバーとの通信を管理するテストクライアント"""

    def __init__(self):
        self.process = None
        self.request_id = 0

    def start_server(self, wait_time: float = 1.0) -> bool:
        """MCP サーバーを起動"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        launch_script = os.path.join(project_root, "launch-mcp-server.sh")

        print(f"起動スクリプト: {launch_script}")
        print("-" * 50)

        # launch-mcp-server.sh を起動
        self.process = subprocess.Popen(
            [launch_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
        )

        print(f"MCP サーバーを起動しました。{wait_time}秒待機中...")
        time.sleep(wait_time)

        # プロセスが生きているか確認
        if self.process.poll() is not None:
            print("\nエラー: プロセスが終了しました")
            stderr_output = self.process.stderr.read()
            if stderr_output:
                print("標準エラー出力:")
                print(stderr_output)
            return False

        return True

    def initialize(
        self, client_name: str = "test-client", client_version: str = "1.0.0"
    ) -> Optional[Dict[str, Any]]:
        """initialize リクエストを送信"""
        self.request_id += 1
        initialize_request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": client_version},
            },
        }

        print("\ninitialize リクエストを送信:")
        print(json.dumps(initialize_request, indent=2))

        response = self._send_request(initialize_request)
        if response:
            print("\nレスポンス:")
            print(json.dumps(response, indent=2, ensure_ascii=False))

        return response

    def send_initialized(self) -> None:
        """initialized 通知を送信"""
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }

        print("\n" + "-" * 50)
        print("\ninitialized 通知を送信:")
        print(json.dumps(initialized_notification, indent=2))

        # JSON を送信
        self.process.stdin.write(json.dumps(initialized_notification) + "\n")
        self.process.stdin.flush()

        # 通知のレスポンスは通常ないが、念のため確認
        time.sleep(0.5)

    def list_tools(self) -> Optional[Dict[str, Any]]:
        """利用可能なツール一覧を取得"""
        self.request_id += 1
        list_tools_request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/list",
        }

        print("\nツール一覧を取得:")
        print(json.dumps(list_tools_request, indent=2))

        response = self._send_request(list_tools_request)
        if response:
            print("\nレスポンス:")
            print(json.dumps(response, indent=2, ensure_ascii=False))

        return response

    def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """ツールを呼び出す"""
        self.request_id += 1
        tool_request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        print(f"\n{tool_name} ツールを呼び出し:")
        print(json.dumps(tool_request, indent=2, ensure_ascii=False))

        response = self._send_request(tool_request)
        if response:
            print("\nレスポンス:")
            print(json.dumps(response, indent=2, ensure_ascii=False))

        return response

    def _send_request(
        self, request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """リクエストを送信してレスポンスを取得"""
        if not self.process:
            print("エラー: サーバーが起動していません")
            return None

        # JSON を送信
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()

        # レスポンスを読み取り
        response_line = self.process.stdout.readline()
        if response_line:
            try:
                return json.loads(response_line)
            except json.JSONDecodeError as e:
                print(f"JSON パースエラー: {e}")
                print(f"受信したデータ: {response_line}")
                return None
        else:
            print("レスポンスなし")
            return None

    def close(self) -> None:
        """サーバープロセスを終了"""
        if self.process:
            self.process.terminate()
            self.process.wait()
            print("\n" + "-" * 50)
            print("MCP サーバーを終了しました")

    def __enter__(self):
        """コンテキストマネージャーの開始"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了"""
        self.close()

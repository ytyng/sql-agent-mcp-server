# SQL Agent MCP Server - Claude 用ドキュメント

MySQL と PostgreSQL に接続してクエリを実行できる MCP サーバーです。

## プロジェクト概要

このプロジェクトは Model Context Protocol (MCP) を使用して、複数のデータベース (MySQL/PostgreSQL) に対して SQL クエリを実行できるサーバーを提供します。

### 主な機能

- 複数データベースサーバーへの接続管理
- SSH トンネル経由での安全な接続
- テーブル一覧・スキーマ情報の取得
- SQL クエリの実行
- MySQL 専用管理コマンド

## 開発環境

- Python 3.11+
- uv パッケージマネージャー
- FastMCP フレームワーク

## 重要なファイル

- `mcp_server.py`: MCP サーバーのメイン実装
- `sql_agent.py`: データベース接続とクエリ実行のロジック
- `config.yaml`: データベース接続設定
- `launch-mcp-server.sh`: サーバー起動スクリプト
- `test-requests/`: テスト用スクリプト一式

## テスト方法

```bash
# 仮想環境とサーバーの起動確認
./launch-mcp-server.sh

# ツール一覧の取得テスト
python3 test-requests/test_list_tools.py

# 実際の SQL 実行テスト
python3 test-requests/test_mangazenkan_dev.py
```

## ログ設定について

MCP 通信では JSON-RPC の標準入出力を使用するため、ログが標準出力に出力されると通信が阻害されます。
このプロジェクトでは以下の対策を実装しています：

- `setup_logger_for_mcp_server()` 関数でログハンドラーをファイル出力のみに設定
- FastMCP および関連ライブラリのログレベルを調整
- アプリケーションログは `/tmp/sql-agent-mcp-server.log` に出力

## 開発時の注意点

- 新しい依存関係を追加する場合は `uv add` を使用
- データベース接続情報は `config.yaml` で管理
- SSH トンネル機能は `test_ssh_tunnel.py` でテスト可能
- ログ設定を変更する場合は MCP 通信への影響を考慮する

## セキュリティ

- パスワードや秘密鍵は適切に管理
- SSH トンネル経由での安全な接続をサポート
- SQL インジェクション対策は sql_agent 側で実装済み
# SQL Agent MCP Server

MySQL と PostgreSQL に接続してクエリを実行できる MCP サーバーです。

## 機能

- 複数のデータベースサーバーへの接続管理
- MySQL と PostgreSQL の両方をサポート
- SSH トンネル経由での接続サポート
- テーブル一覧やスキーマ情報の取得
- SQL クエリの実行
- MySQL 専用の管理コマンド

## インストール

```bash
# 依存関係のインストール
uv sync
```

## 設定

`config.yaml` ファイルを作成して、接続するデータベースサーバーの情報を設定します。

```yaml
mysql_servers:
  - name: my-postgres
    description: "PostgreSQL サーバー"
    engine: postgres
    host: localhost
    port: 5432
    schema: mydb
    user: postgres
    password: password
  
  - name: my-mysql
    description: "MySQL サーバー"
    engine: mysql
    host: localhost
    port: 3306
    schema: mydb
    user: root
    password: password
```

### SSH トンネル経由での接続

SSH トンネルを使ってリモートのデータベースに安全に接続できます。

```yaml
mysql_servers:
  - name: remote-db
    description: "SSH トンネル経由のリモートデータベース"
    engine: postgres
    host: localhost  # SSH トンネル経由の場合は localhost を指定
    port: 5432
    schema: remote_db
    user: db_user
    password: db_password
    ssh_tunnel:
      host: ssh.example.com
      port: 22
      user: ssh_user
      # パスワード認証の場合
      password: ssh_password
      # または秘密鍵認証の場合
      # private_key_path: ~/.ssh/id_rsa
      # private_key_passphrase: key_passphrase  # パスフレーズがある場合
```

## 使い方

### MCP サーバーの起動

```bash
# 起動スクリプトを使用 (推奨)
./launch-mcp-server.sh

# または直接起動
source .venv/bin/activate
python mcp_server.py
```

### 利用可能なツール

#### 1. sql_query
SQL クエリを実行します。

```
Parameters:
- server_name: サーバー名
- sql: 実行する SQL クエリ
```

#### 2. get_server_list
登録されているサーバーの一覧を取得します。

#### 3. get_table_list
指定したサーバーのテーブル一覧を取得します。

```
Parameters:
- server_name: サーバー名
```

#### 4. get_table_schema
テーブルのスキーマ情報を取得します。

```
Parameters:
- server_name: サーバー名
- table_name: テーブル名
```

### MySQL 専用ツール

MySQL サーバーに対してのみ使用できる管理ツールです。

- `get_mysql_status`: ステータス情報を取得
- `get_mysql_variables`: 変数情報を取得
- `get_mysql_processlist`: プロセス一覧を取得
- `get_mysql_databases`: データベース一覧を取得
- `get_mysql_table_status`: テーブルステータスを取得
- `get_mysql_indexes`: インデックス情報を取得
- `analyze_mysql_table`: テーブルを分析
- `optimize_mysql_table`: テーブルを最適化
- `check_mysql_table`: テーブルをチェック
- `repair_mysql_table`: テーブルを修復

## テスト

`test-requests/` ディレクトリに MCP サーバーのテスト用スクリプトが含まれています。

### テストライブラリ

- `test_mcp_lib.py`: MCP サーバーとの通信用共通ライブラリ
- `test_list_tools.py`: 利用可能なツール一覧を取得するテスト
- `test_mangazenkan_dev.py`: 実際のデータベースに対する SQL 実行テスト

```bash
# ツール一覧の取得テスト
python3 test-requests/test_list_tools.py

# SQL 実行テスト
python3 test-requests/test_mangazenkan_dev.py
```

## ログ

- アプリケーションログは `/tmp/sql-agent-mcp-server.log` に出力されます
- MCP 通信ではログが標準出力に出力されないよう設定済みです

## セキュリティに関する注意

- `config.yaml` にはデータベースのパスワードが含まれるため、適切に管理してください
- SSH 秘密鍵を使用する場合は、適切なファイルパーミッションを設定してください
- 本番環境では環境変数や秘密管理ツールの使用を検討してください
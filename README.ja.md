# SQL Agent MCP Server

MySQL と PostgreSQL に接続してクエリを実行できる MCP サーバー。スタンドアロン CLI (`sql-agent-cli`) も同梱。

## ⚠️ 破壊的変更 (Breaking Changes)

- **設定キー名の変更**: `mysql_servers` → `sql_servers`。`config.yaml` を更新する必要あり。旧キーは認識されない。
- **PostgreSQL の行形式**: cursor を `DictCursor` から `RealDictCursor` に変更。SELECT の rows が普通の dict (`[{"col": value}]`) になり、旧来の list 形 `DictRow` (`[[value]]`) ではなくなった。これはバグ修正。Postgres 結果に対して位置アクセスをしていたクライアントはキーアクセスに変更が必要。
- **`python-dotenv` 依存削除**: `.env` の自動読み込みは廃止。環境変数 (`SQL_AGENT_CONFIG_YAML`, `SQL_AGENT_LOG_FILE_PATH`) は MCP クライアントの `env` ブロックやシェルから渡す。`config.yaml` の代わりに `SQL_AGENT_CONFIG_YAML` で YAML 文字列をインライン指定もできる。

## 機能

- 複数のデータベースサーバーへの接続管理
- MySQL と PostgreSQL の両方をサポート
- SSH トンネル経由での接続サポート
- MCP サーバーまたは CLI から SQL クエリを実行
- `config.yaml` または `SQL_AGENT_CONFIG_YAML` 環境変数による設定

## インストール

```bash
# 依存関係のインストール
uv sync
```

## 設定

`config.yaml` ファイルを作成して、接続するデータベースサーバーの情報を設定します。`SQL_AGENT_CONFIG_YAML` 環境変数で YAML 文字列を直接渡すこともできます (環境変数が優先)。

```yaml
# 任意: ログファイルのパス
# 解決順: この YAML > 環境変数 SQL_AGENT_LOG_FILE_PATH > /tmp/sql-agent-mcp-server.log
log_file_path: /tmp/sql-agent-mcp-server.log

sql_servers:
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
sql_servers:
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

#### `list_sql_servers`
登録されている SQL サーバーの一覧を取得します。

#### `execute_sql`
指定したサーバーで SQL を実行し、結果を JSON で返します。

```
Parameters:
- server_name: サーバー名 (sql_servers の name と一致する必要あり)
- sql: 実行する SQL クエリ
```

スキーマ情報 (テーブル一覧、カラム情報など) は、`SHOW TABLES`、`DESCRIBE <table>` (MySQL) や `pg_tables` / `information_schema` への問い合わせ (PostgreSQL) を `execute_sql` 経由で実行してください。

### CLI

MCP ツールと同じ機能をコマンドラインから利用できる CLI を同梱しています。AI エージェントのコンテキストに MCP サーバーをロードしたくない場合に有用です。

```bash
sql-agent-cli list-sql-servers
sql-agent-cli execute-sql --server my-postgres --sql "SELECT 1"
echo "SELECT NOW()" | sql-agent-cli execute-sql -s my-postgres
```

`sql-agent-cli --help` および `sql-agent-cli <subcommand> --help` で全オプションを確認できます。

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
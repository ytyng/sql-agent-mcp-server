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
- `config.yaml`、`SQL_AGENT_CONFIG_YAML`、または秘密マネージャー向けの遅延 getter コマンド (`SQL_AGENT_CONFIG_YAML_GETTER_COMMAND`) による設定

## インストール

```bash
# 依存関係のインストール
uv sync
```

## 設定

`config.yaml` ファイルを作成して、接続するデータベースサーバーの情報を設定します。設定は次の優先順で解決されます:

1. `SQL_AGENT_CONFIG_YAML` — YAML 文字列をインライン指定 (最優先)
2. `SQL_AGENT_CONFIG_YAML_GETTER_COMMAND` — stdout が YAML 設定になるコマンド (遅延実行。後述)
3. プロジェクトディレクトリの `config.yaml` ファイル

#### 設定の遅延ロード (`SQL_AGENT_CONFIG_YAML_GETTER_COMMAND`)

設定を秘密マネージャー (例: 1Password) に置いている場合、秘密そのものではなく **取得コマンド** を渡せます:

```sh
export SQL_AGENT_CONFIG_YAML_GETTER_COMMAND='op read "op://development/sql-agent/config-yaml"'
```

このコマンドは **起動時には実行されません**。実際に設定が必要になった時 — つまり最初の `list_sql_servers` / `execute_sql` 呼び出し時 — にだけ実行されます。これにより、MCP クライアント (例: Claude Desktop) がサーバーを起動するたびに 1Password 等の認証ダイアログが出るのを防げます。

コマンドは `shlex.split` で分解し `shell=False` で実行します (シェルを介さない)。そのためシェルメタ文字によるインジェクションは起きませんが、パイプ・リダイレクト・変数展開は **使えません**。シェル機能が必要な場合はラッパースクリプトを 1 コマンドとして渡してください。

起動時に認証せずともツール説明にサーバー一覧を表示できるよう、初回ロード成功後に **機密を含まないメタデータキャッシュ** (サーバーの `name` / `description` / `engine` / `host` / `port` / `schema` と `log_file_path`) を保存します。パスワードや SSH 秘密鍵は **キャッシュしません**。キャッシュパスは既定で `~/.cache/sql-agent-mcp-server/server-metadata.json`、`SQL_AGENT_CONFIG_CACHE_PATH` で変更できます。

```yaml
# 任意: ログファイルのパス
# 解決順: この YAML > 環境変数 SQL_AGENT_LOG_FILE_PATH > /tmp/sql-agent/sql-agent-mcp-server.log
log_file_path: /tmp/sql-agent/sql-agent-mcp-server.log

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

### テンプレートで接続情報を共有する (`sql_server_templates`)

同一 DB インスタンス上の複数 schema を扱う場合など、`sql_servers` に接続情報 (engine / host / port / user / password / ssh_tunnel 等) を重複して書くのを避けられます。共通項目を `sql_server_templates` にまとめ、各サーバーで `template: <テンプレート名>` を指定して継承します。

```yaml
sql_server_templates:
  - name: my-awesome-sql-host
    engine: mysql
    host: db.example.com
    port: 3306
    user: shared_user
    password: shared_password

sql_servers:
  - template: my-awesome-sql-host
    name: my-app-db
    description: "アプリ本体の DB"
    schema: app_db

  - template: my-awesome-sql-host
    name: my-log-db
    description: "ログ用 DB"
    schema: log_db
```

- サーバー側で指定したキーは、テンプレートの同名キーを上書きします (シャローマージ)。`ssh_tunnel` のようなネストした値をサーバー側で指定すると丸ごと置き換わります。
- テンプレートの `name` はルックアップ用のキーなので継承されません。各サーバーは自分自身の `name` を持つ必要があります。
- `template` を指定しないサーバーは従来どおりそのまま使えます。`sql_server_templates` 自体を書かなくても構いません (後方互換)。

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

- アプリケーションログは `/tmp/sql-agent/sql-agent-mcp-server.log` に出力されます
- MCP 通信ではログが標準出力に出力されないよう設定済みです

## セキュリティに関する注意

- `config.yaml` にはデータベースのパスワードが含まれるため、適切に管理してください
- SSH 秘密鍵を使用する場合は、適切なファイルパーミッションを設定してください
- 本番環境では環境変数や秘密管理ツールの使用を検討してください
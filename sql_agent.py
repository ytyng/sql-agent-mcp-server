#!/usr/bin/env python3
"""
SQL Agent - Core class for managing SQL connections and query execution
"""

import decimal
import os
import re
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Callable, Dict, List

import psycopg2
import psycopg2.extras
import pymysql
import pymysql.cursors
from sshtunnel import SSHTunnelForwarder

from config_loader import save_metadata_cache
from logging_config import logger, setup_logger_for_mcp_server

# SQL の文字列リテラル '...' を ログ出力時にマスクする正規表現。
# 単一引用符の中身は次の 3 通りを許容:
#   1. ' でも \ でもない普通の文字
#   2. \. (バックスラッシュエスケープ; MySQL デフォルト)
#   3. '' (二重シングルクォートでのエスケープ; PostgreSQL / 標準 SQL)
_SQL_STRING_LITERAL_RE = re.compile(r"'(?:[^'\\]|\\.|'')*'")

# PostgreSQL のドルクォート文字列をマスクする正規表現。
# 開始/終了のタグが一致する必要があるため後方参照 (\1) を使う:
#   - タグ無し: $$...$$ (\1 は空文字にマッチ)
#   - タグ付き: $tag$...$tag$
# 本文は改行を含みうるので [\s\S] で全文字を非貪欲にマッチさせる。
_SQL_DOLLAR_QUOTE_RE = re.compile(r"\$(\w*)\$[\s\S]*?\$\1\$")


def mask_sql_for_log(sql: str) -> str:
    """ログ出力用に SQL の文字列リテラルをマスクする (PII / 機密漏れ防止)"""
    # ドルクォートを先にマスクする (本文に ' を含んでいても丸ごと潰すため)。
    masked = _SQL_DOLLAR_QUOTE_RE.sub("$$***$$", sql)
    return _SQL_STRING_LITERAL_RE.sub("'***'", masked)


class SQLAgent:
    """Class for managing SQL database connections and query execution"""

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: データベース設定
        """
        self.config = config
        self.connection = None

    def connect(self, ssh_tunnel: SSHTunnelForwarder = None) -> None:
        """
        データベースに接続する

        Args:
            ssh_tunnel: 使用する SSH トンネル (SSH トンネル経由の場合)
        """
        try:
            # SSH トンネル経由の場合はローカルホストとポートを使用
            if ssh_tunnel:
                db_host = '127.0.0.1'
                db_port = ssh_tunnel.local_bind_port
            else:
                db_host = self.config['host']
                db_port = self.config['port']

            if self.config['engine'] == 'postgres':
                self.connection = psycopg2.connect(
                    host=db_host,
                    port=db_port,
                    database=self.config['schema'],
                    user=self.config['user'],
                    password=self.config['password'],
                    cursor_factory=psycopg2.extras.RealDictCursor,
                )
            elif self.config['engine'] == 'mysql':
                self.connection = pymysql.connect(
                    host=db_host,
                    port=db_port,
                    database=self.config['schema'],
                    user=self.config['user'],
                    password=self.config['password'],
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor,
                )
            else:
                raise ValueError(
                    f"Unsupported engine: {self.config['engine']}"
                )

            logger.info(f"データベースに接続しました: {self.config['name']}")

        except Exception as e:
            logger.error(
                f"データベース接続エラー ({self.config['name']}): {e}"
            )
            raise

    def disconnect(self) -> None:
        """データベースから切断する"""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info(f"データベースから切断しました: {self.config['name']}")

    def execute_query(self, sql: str) -> Dict[str, Any]:
        """
        SQL クエリを実行する
        SSH トンネルが設定されている場合は、クエリ実行毎にトンネルを作成・クローズする

        Args:
            sql: 実行する SQL クエリ

        Returns:
            クエリ結果を含む辞書
        """
        ssh_tunnel = None

        try:
            # SSH トンネルが必要な場合は作成
            if 'ssh_tunnel' in self.config:
                ssh_tunnel = self._create_ssh_tunnel()

            # データベースに接続
            self.connect(ssh_tunnel)

            sql_for_log = mask_sql_for_log(sql)
            logger.info(
                f"クエリ実行開始 ({self.config['name']}): {sql_for_log}"
            )

            with self.connection.cursor() as cursor:
                start_time = datetime.now()
                cursor.execute(sql)

                # 結果を取得できるクエリかどうかをチェック
                try:
                    rows = cursor.fetchall()
                    # 結果を JSON シリアライズ可能な形式に変換
                    serializable_rows = self._make_serializable(rows)

                    # RETURNING を使う INSERT/UPDATE/DELETE は fetchall に成功し、
                    # この分岐に入る。autocommit=False のため明示 commit しないと
                    # disconnect 時にロールバックされて変更が消える。
                    # SELECT に対しても commit() は安全 (進行中の暗黙トランザクションを
                    # 終わらせるだけで、変更が無いので副作用は無い) なので無条件で呼ぶ。
                    self.connection.commit()

                    result = {
                        'success': True,
                        'query': sql,
                        'rows': serializable_rows,
                        'row_count': len(rows),
                        'execution_time_ms': (
                            datetime.now() - start_time
                        ).total_seconds()
                        * 1000,
                        'server_name': self.config['name'],
                    }
                    logger.info(
                        f"クエリ実行成功 ({self.config['name']}): {len(rows)} 行取得"
                    )
                except (
                    psycopg2.ProgrammingError,
                    pymysql.err.ProgrammingError,
                ) as e:
                    # 結果がないため fetchall が失敗する場合 (INSERT, UPDATE, DELETE など)
                    logger.info(
                        f"クエリ実行成功だが fetchall に失敗: {self.config['name']}, "
                        f"{e.__class__.__name__}: {e}"
                    )
                    self.connection.commit()
                    affected_rows = cursor.rowcount

                    result = {
                        'success': True,
                        'query': sql,
                        'affected_rows': affected_rows,
                        'execution_time_ms': (
                            datetime.now() - start_time
                        ).total_seconds()
                        * 1000,
                        'server_name': self.config['name'],
                    }

                sql_log_tail = (
                    sql_for_log[:100] + '...'
                    if len(sql_for_log) > 100
                    else sql_for_log
                )
                logger.info(
                    f"クエリ実行完了 ({self.config['name']}): {sql_log_tail}"
                )
                return result

        except Exception as e:
            logger.error(
                f"クエリ実行エラー ({self.config['name']}): {e.__class__.__name__}: {e}"
            )
            result = {
                'success': False,
                'query': sql,
                'error': f'{e.__class__.__name__}: {e}',
                'server_name': self.config['name'],
            }
            return result

        finally:
            # 接続を閉じる
            self.disconnect()

            # SSH トンネルを閉じる
            if ssh_tunnel:
                ssh_tunnel.stop()
                logger.info(f"SSH トンネルを閉じました: {self.config['name']}")

    def _make_serializable(self, data: Any) -> Any:
        """
        データを JSON シリアライズ可能な形式に変換する

        Args:
            data: 変換するデータ

        Returns:
            シリアライズ可能なデータ
        """
        if isinstance(data, list):
            return [self._make_serializable(item) for item in data]
        elif isinstance(data, dict):
            return {
                key: self._make_serializable(value)
                for key, value in data.items()
            }
        elif isinstance(data, (datetime, date)):
            return data.isoformat()
        elif isinstance(data, decimal.Decimal):
            return float(data)
        elif isinstance(data, bytes):
            try:
                return data.decode('utf-8')
            except UnicodeDecodeError:
                return data.hex()
        else:
            return data

    @contextmanager
    def connection_context(self):
        """
        データベース接続のコンテキストマネージャー
        SSH トンネルが設定されている場合は自動的に管理する
        """
        ssh_tunnel = None

        try:
            # SSH トンネルが必要な場合は作成
            if 'ssh_tunnel' in self.config:
                ssh_tunnel = self._create_ssh_tunnel()

            # データベースに接続
            self.connect(ssh_tunnel)
            yield self

        finally:
            # 接続を閉じる
            self.disconnect()

            # SSH トンネルを閉じる
            if ssh_tunnel:
                ssh_tunnel.stop()
                logger.info(f"SSH トンネルを閉じました: {self.config['name']}")

    def __enter__(self):
        """
        レガシー対応のコンテキストマネージャーの開始
        SSH トンネルが設定されている場合は connection_context() を使用することを推奨
        """
        if 'ssh_tunnel' in self.config:
            logger.warning(
                f"SSH トンネルが設定されているため connection_context() の使用を推奨します: {self.config['name']}"
            )
        self.connect()
        return self

    def _create_ssh_tunnel(self) -> SSHTunnelForwarder:
        """
        SSH トンネルを作成する

        Returns:
            SSH トンネルインスタンス
        """
        ssh_config = self.config['ssh_tunnel']

        # SSH 接続パラメータを設定
        ssh_params = {
            'ssh_address_or_host': (
                ssh_config['host'],
                ssh_config.get('port', 22),
            ),
            'ssh_username': ssh_config['user'],
            'remote_bind_address': (self.config['host'], self.config['port']),
        }

        # 認証方法の設定
        if 'private_key_path' in ssh_config:
            # 秘密鍵認証
            key_path = os.path.expanduser(ssh_config['private_key_path'])
            ssh_params['ssh_pkey'] = key_path

            # 秘密鍵のパスフレーズがある場合
            if 'private_key_passphrase' in ssh_config:
                ssh_params['ssh_private_key_password'] = ssh_config[
                    'private_key_passphrase'
                ]
        elif 'password' in ssh_config:
            # パスワード認証
            ssh_params['ssh_password'] = ssh_config['password']
        # 認証情報が明示的に設定されていない場合はデフォルトの SSH キー認証を使用
        # SSHTunnelForwarder はデフォルトで ~/.ssh/id_rsa を使用する

        # SSH トンネルを作成して開始
        ssh_tunnel = SSHTunnelForwarder(**ssh_params)
        ssh_tunnel.start()

        logger.info(
            f"SSH トンネルを確立しました: {ssh_config['host']}:{ssh_config.get('port', 22)} -> "
            f"{self.config['host']}:{self.config['port']}"
        )

        return ssh_tunnel

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了"""
        self.disconnect()


class SQLAgentManager:
    """複数の SQL Agent を管理するクラス"""

    def __init__(self, config_loader: Callable[[], Dict[str, Any]]):
        """
        Args:
            config_loader: config (dict) を返す callable。実際に config が
                必要になった初回アクセス時に一度だけ呼ばれる。getter command
                経由の場合、この呼び出しが 1Password 等の認証をトリガーする。
        """
        self._config_loader = config_loader
        self._loaded = False
        self.servers_config: List[Dict[str, Any]] = []
        self.server_configs: Dict[str, Dict[str, Any]] = {}
        self.agents = {}

    def _ensure_loaded(self) -> None:
        """config を初回アクセス時に一度だけロードする (memoize)。"""
        if self._loaded:
            return

        config = self._config_loader()
        self.servers_config = config.get('sql_servers', [])
        self.server_configs = {
            server['name']: server for server in self.servers_config
        }

        # ロード成功時に、機密を除いたメタデータをキャッシュ更新する。
        # 次回起動時の instructions / ログパスに使われる (best-effort)。
        save_metadata_cache(config)

        # YAML に log_file_path があればログ設定を差し替える
        # (起動時はキャッシュ or 環境変数のパス、初回ロード後に正規パスへ)。
        # ただしログ設定の失敗で config ロード全体を巻き戻すと、次回呼び出しで
        # 再び _config_loader() が走り 1Password 認証が毎回出るループになる。
        # config 自体は読めているので、ログ差し替えは best-effort とし、
        # 失敗しても起動時に設定済みの (動作中の) ロガーで続行する。
        if config.get('log_file_path'):
            try:
                setup_logger_for_mcp_server(config['log_file_path'])
            except Exception as e:
                logger.warning(
                    f"log_file_path への切り替えに失敗 (既存ロガーで続行): {e}"
                )

        self._loaded = True

    def get_agent(self, server_name: str) -> SQLAgent:
        """
        指定したサーバー名の SQL Agent を取得する
        SQLAgent が存在しない場合は遅延生成する

        Args:
            server_name: サーバー名

        Returns:
            SQL Agent インスタンス
        """
        self._ensure_loaded()
        if server_name not in self.server_configs:
            raise ValueError(f"Server not found: {server_name}")

        # SQLAgent が未作成の場合は遅延生成
        if server_name not in self.agents:
            self.agents[server_name] = SQLAgent(
                self.server_configs[server_name]
            )
            logger.info(f"SQLAgent を遅延生成しました: {server_name}")

        return self.agents[server_name]

    def get_server_list(self) -> List[Dict[str, Any]]:
        """
        登録されているサーバーの一覧を取得する

        Returns:
            サーバー情報のリスト
        """
        self._ensure_loaded()
        servers = []
        for config in self.servers_config:
            servers.append(
                {
                    'name': config['name'],
                    'description': config.get('description', ''),
                    'engine': config['engine'],
                    'host': config['host'],
                    'port': config['port'],
                    'schema': config['schema'],
                }
            )

        return servers

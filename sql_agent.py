#!/usr/bin/env python3
"""
SQL Agent - Core class for managing SQL connections and query execution
"""

import decimal
import os
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Dict, List

import psycopg2
import psycopg2.extras
import pymysql
import pymysql.cursors
from sshtunnel import SSHTunnelForwarder

from logging_config import logger


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
                    cursor_factory=psycopg2.extras.DictCursor,
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

            logger.info(f"クエリ実行開始 ({self.config['name']}): {sql}")

            with self.connection.cursor() as cursor:
                start_time = datetime.now()
                cursor.execute(sql)

                # 結果を取得できるクエリかどうかをチェック
                try:
                    rows = cursor.fetchall()
                    # 結果を JSON シリアライズ可能な形式に変換
                    serializable_rows = self._make_serializable(rows)

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

                logger.info(
                    f"クエリ実行完了 ({self.config['name']}): {sql[:100]}..."
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

    def __init__(self, servers_config: List[Dict[str, Any]]):
        """
        Args:
            servers_config: サーバー設定のリスト
        """
        self.servers_config = servers_config
        self.agents = {}
        # サーバー名からサーバー設定を取得するための辞書を作成
        self.server_configs = {
            config['name']: config for config in servers_config
        }

    def get_agent(self, server_name: str) -> SQLAgent:
        """
        指定したサーバー名の SQL Agent を取得する
        SQLAgent が存在しない場合は遅延生成する

        Args:
            server_name: サーバー名

        Returns:
            SQL Agent インスタンス
        """
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

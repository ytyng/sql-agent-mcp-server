#!/usr/bin/env python3
"""
SQL Agent - Core class for managing SQL connections and query execution
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, date
import decimal
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import pymysql
import pymysql.cursors
from sshtunnel import SSHTunnelForwarder


logger = logging.getLogger(__name__)


class SQLAgent:
    """Class for managing SQL database connections and query execution"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: データベース設定
        """
        self.config = config
        self.connection = None
        self.ssh_tunnel = None
        
    def connect(self) -> None:
        """データベースに接続する"""
        try:
            # SSH トンネルの設定がある場合は先にトンネルを作成
            if 'ssh_tunnel' in self.config:
                self._create_ssh_tunnel()
            
            # SSH トンネル経由の場合はローカルホストとポートを使用
            if self.ssh_tunnel:
                db_host = '127.0.0.1'
                db_port = self.ssh_tunnel.local_bind_port
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
                    cursor_factory=psycopg2.extras.DictCursor
                )
            elif self.config['engine'] == 'mysql':
                self.connection = pymysql.connect(
                    host=db_host,
                    port=db_port,
                    database=self.config['schema'],
                    user=self.config['user'],
                    password=self.config['password'],
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor
                )
            else:
                raise ValueError(f"Unsupported engine: {self.config['engine']}")
                
            logger.info(f"データベースに接続しました: {self.config['name']}")
            
        except Exception as e:
            logger.error(f"データベース接続エラー ({self.config['name']}): {e}")
            # エラー時は SSH トンネルも閉じる
            if self.ssh_tunnel:
                self.ssh_tunnel.stop()
                self.ssh_tunnel = None
            raise
    
    def disconnect(self) -> None:
        """データベースから切断する"""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info(f"データベースから切断しました: {self.config['name']}")
        
        # SSH トンネルがある場合は閉じる
        if self.ssh_tunnel:
            self.ssh_tunnel.stop()
            self.ssh_tunnel = None
            logger.info(f"SSH トンネルを閉じました: {self.config['name']}")
    
    def execute_query(self, sql: str) -> Dict[str, Any]:
        """
        SQL クエリを実行する
        
        Args:
            sql: 実行する SQL クエリ
            
        Returns:
            クエリ結果を含む辞書
        """
        if not self.connection:
            self.connect()
        
        try:
            with self.connection.cursor() as cursor:
                start_time = datetime.now()
                cursor.execute(sql)
                
                # SELECT 文の場合は結果を取得
                if sql.strip().upper().startswith('SELECT'):
                    rows = cursor.fetchall()
                    # 結果を JSON シリアライズ可能な形式に変換
                    serializable_rows = self._make_serializable(rows)
                    
                    result = {
                        'success': True,
                        'query': sql,
                        'rows': serializable_rows,
                        'row_count': len(rows),
                        'execution_time_ms': (datetime.now() - start_time).total_seconds() * 1000,
                        'server_name': self.config['name']
                    }
                else:
                    # INSERT, UPDATE, DELETE などの場合
                    self.connection.commit()
                    affected_rows = cursor.rowcount
                    
                    result = {
                        'success': True,
                        'query': sql,
                        'affected_rows': affected_rows,
                        'execution_time_ms': (datetime.now() - start_time).total_seconds() * 1000,
                        'server_name': self.config['name']
                    }
                
                logger.info(f"クエリ実行完了 ({self.config['name']}): {sql[:100]}...")
                return result
                
        except Exception as e:
            logger.error(f"クエリ実行エラー ({self.config['name']}): {e}")
            result = {
                'success': False,
                'query': sql,
                'error': str(e),
                'server_name': self.config['name']
            }
            return result
    
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
            return {key: self._make_serializable(value) for key, value in data.items()}
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
    
    def get_table_list(self) -> Dict[str, Any]:
        """
        データベース内のテーブル一覧を取得する
        
        Returns:
            テーブル一覧を含む辞書
        """
        if self.config['engine'] == 'postgres':
            sql = """
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """
        elif self.config['engine'] == 'mysql':
            sql = f"""
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = '{self.config['schema']}'
                ORDER BY table_name
            """
        else:
            raise ValueError(f"Unsupported engine: {self.config['engine']}")
        
        return self.execute_query(sql)
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """
        指定したテーブルのスキーマ情報を取得する
        
        Args:
            table_name: テーブル名
            
        Returns:
            スキーマ情報を含む辞書
        """
        if self.config['engine'] == 'postgres':
            sql = f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = '{table_name}'
                ORDER BY ordinal_position
            """
        elif self.config['engine'] == 'mysql':
            sql = f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = '{self.config['schema']}' AND table_name = '{table_name}'
                ORDER BY ordinal_position
            """
        else:
            raise ValueError(f"Unsupported engine: {self.config['engine']}")
        
        return self.execute_query(sql)
    
    def __enter__(self):
        """コンテキストマネージャーの開始"""
        self.connect()
        return self
    
    def _create_ssh_tunnel(self) -> None:
        """SSH トンネルを作成する"""
        ssh_config = self.config['ssh_tunnel']
        
        # SSH 接続パラメータを設定
        ssh_params = {
            'ssh_address_or_host': (ssh_config['host'], ssh_config.get('port', 22)),
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
                ssh_params['ssh_private_key_password'] = ssh_config['private_key_passphrase']
        elif 'password' in ssh_config:
            # パスワード認証
            ssh_params['ssh_password'] = ssh_config['password']
        else:
            raise ValueError("SSH authentication information is not configured")
        
        # SSH トンネルを作成
        self.ssh_tunnel = SSHTunnelForwarder(**ssh_params)
        self.ssh_tunnel.start()
        
        logger.info(f"SSH トンネルを確立しました: {ssh_config['host']}:{ssh_config.get('port', 22)} -> {self.config['host']}:{self.config['port']}")
    
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
        
        for server_config in servers_config:
            self.agents[server_config['name']] = SQLAgent(server_config)
    
    def get_agent(self, server_name: str) -> SQLAgent:
        """
        指定したサーバー名の SQL Agent を取得する
        
        Args:
            server_name: サーバー名
            
        Returns:
            SQL Agent インスタンス
        """
        if server_name not in self.agents:
            raise ValueError(f"Server not found: {server_name}")
        
        return self.agents[server_name]
    
    def get_server_list(self) -> List[Dict[str, Any]]:
        """
        登録されているサーバーの一覧を取得する
        
        Returns:
            サーバー情報のリスト
        """
        servers = []
        for config in self.servers_config:
            servers.append({
                'name': config['name'],
                'description': config.get('description', ''),
                'engine': config['engine'],
                'host': config['host'],
                'port': config['port'],
                'schema': config['schema']
            })
        
        return servers
    
    def get_mysql_status(self, server_name: str) -> Dict[str, Any]:
        """
        MySQL サーバーのステータス情報を取得する
        
        Args:
            server_name: サーバー名
            
        Returns:
            ステータス情報を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = "SHOW STATUS"
        return agent.execute_query(sql)
    
    def get_mysql_variables(self, server_name: str) -> Dict[str, Any]:
        """
        MySQL サーバーの変数情報を取得する
        
        Args:
            server_name: サーバー名
            
        Returns:
            変数情報を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = "SHOW VARIABLES"
        return agent.execute_query(sql)
    
    def get_mysql_processlist(self, server_name: str) -> Dict[str, Any]:
        """
        MySQL サーバーのプロセス一覧を取得する
        
        Args:
            server_name: サーバー名
            
        Returns:
            プロセス一覧を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = "SHOW PROCESSLIST"
        return agent.execute_query(sql)
    
    def get_mysql_databases(self, server_name: str) -> Dict[str, Any]:
        """
        MySQL サーバーのデータベース一覧を取得する
        
        Args:
            server_name: サーバー名
            
        Returns:
            データベース一覧を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = "SHOW DATABASES"
        return agent.execute_query(sql)
    
    def get_mysql_table_status(self, server_name: str, table_name: str = None) -> Dict[str, Any]:
        """
        MySQL テーブルのステータス情報を取得する
        
        Args:
            server_name: サーバー名
            table_name: テーブル名 (省略時は全テーブル)
            
        Returns:
            テーブルステータス情報を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        if table_name:
            sql = f"SHOW TABLE STATUS LIKE '{table_name}'"
        else:
            sql = "SHOW TABLE STATUS"
        
        return agent.execute_query(sql)
    
    def get_mysql_indexes(self, server_name: str, table_name: str) -> Dict[str, Any]:
        """
        MySQL テーブルのインデックス情報を取得する
        
        Args:
            server_name: サーバー名
            table_name: テーブル名
            
        Returns:
            インデックス情報を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = f"SHOW INDEX FROM {table_name}"
        return agent.execute_query(sql)
    
    def get_mysql_engine_status(self, server_name: str) -> Dict[str, Any]:
        """
        MySQL ストレージエンジンのステータス情報を取得する
        
        Args:
            server_name: サーバー名
            
        Returns:
            エンジンステータス情報を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = "SHOW ENGINES"
        return agent.execute_query(sql)
    
    def get_mysql_binary_logs(self, server_name: str) -> Dict[str, Any]:
        """
        MySQL バイナリログの情報を取得する
        
        Args:
            server_name: サーバー名
            
        Returns:
            バイナリログ情報を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = "SHOW BINARY LOGS"
        return agent.execute_query(sql)
    
    def get_mysql_master_status(self, server_name: str) -> Dict[str, Any]:
        """
        MySQL マスターのステータス情報を取得する
        
        Args:
            server_name: サーバー名
            
        Returns:
            マスターステータス情報を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = "SHOW MASTER STATUS"
        return agent.execute_query(sql)
    
    def get_mysql_slave_status(self, server_name: str) -> Dict[str, Any]:
        """
        MySQL スレーブのステータス情報を取得する
        
        Args:
            server_name: サーバー名
            
        Returns:
            スレーブステータス情報を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = "SHOW SLAVE STATUS"
        return agent.execute_query(sql)
    
    def analyze_mysql_table(self, server_name: str, table_name: str) -> Dict[str, Any]:
        """
        MySQL テーブルの分析を実行する
        
        Args:
            server_name: サーバー名
            table_name: テーブル名
            
        Returns:
            分析結果を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = f"ANALYZE TABLE {table_name}"
        return agent.execute_query(sql)
    
    def optimize_mysql_table(self, server_name: str, table_name: str) -> Dict[str, Any]:
        """
        MySQL テーブルの最適化を実行する
        
        Args:
            server_name: サーバー名
            table_name: テーブル名
            
        Returns:
            最適化結果を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = f"OPTIMIZE TABLE {table_name}"
        return agent.execute_query(sql)
    
    def check_mysql_table(self, server_name: str, table_name: str) -> Dict[str, Any]:
        """
        MySQL テーブルのチェックを実行する
        
        Args:
            server_name: サーバー名
            table_name: テーブル名
            
        Returns:
            チェック結果を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = f"CHECK TABLE {table_name}"
        return agent.execute_query(sql)
    
    def repair_mysql_table(self, server_name: str, table_name: str) -> Dict[str, Any]:
        """
        MySQL テーブルの修復を実行する
        
        Args:
            server_name: サーバー名
            table_name: テーブル名
            
        Returns:
            修復結果を含む辞書
        """
        agent = self.get_agent(server_name)
        if agent.config['engine'] != 'mysql':
            raise ValueError(f"Not a MySQL server: {server_name}")
        
        sql = f"REPAIR TABLE {table_name}"
        return agent.execute_query(sql)
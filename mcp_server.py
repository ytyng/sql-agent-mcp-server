#!/usr/bin/env python3
"""
MySQL, Postgres に接続する MCP サーバー
"""

import os
import sys
from typing import Annotated
import yaml
import json

import logging
import fastmcp
from fastmcp.utilities.types import Image
from dotenv import load_dotenv
from pydantic import Field

from sql_agent import SQLAgentManager


# .envファイルから環境変数を読み込む
load_dotenv()


def setup_logger():
    log_file = '/tmp/sql-agent-mcp-server.log'
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(
        logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    )

    # ルートロガーの設定
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers = [file_handler]
    return logger


logger = setup_logger()

# グローバルな SQL Agent Manager
sql_agent_manager = None


def get_config():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, 'config.yaml')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


def init_sql_agent_manager():
    """SQL Agent Manager を初期化する"""
    global sql_agent_manager
    if sql_agent_manager is None:
        config = get_config()
        mysql_servers = config.get('mysql_servers', [])
        sql_agent_manager = SQLAgentManager(mysql_servers)
    return sql_agent_manager


# MCPサーバーの設定
server = fastmcp.FastMCP(
    name="sql-agent-mcp-server",
    instructions="""MySQL と Postgres に接続する MCP サーバーです。""",
)


@server.tool(
    name="list_sql_servers",
    description="""登録してある SQL サーバーの一覧を取得します。
""",
)
async def list_sql_servers() -> str:
    """登録されている SQL サーバーの一覧を取得する"""
    try:
        manager = init_sql_agent_manager()
        servers = manager.get_server_list()
        
        result = {
            'success': True,
            'servers': servers,
            'count': len(servers)
        }
        
        logger.info(f"サーバー一覧を取得しました: {len(servers)} 個")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"サーバー一覧取得エラー: {e}")
        result = {
            'success': False,
            'error': str(e)
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="execute_sql",
    description="""SQL クエリを実行し、結果を JSON で返します。
""",
)
async def execute_sql(
    server_name: Annotated[
        str,
        Field(
            description=(
                "実行する SQL サーバーの名前。 config.yaml の mysql_servers の name"
            ),
            examples=["ytyng-blog"],
        ),
    ] = None,
    sql: Annotated[
        str | None,
        Field(
            description=("実行する SQL クエリ。"),
            examples=[
                "SELECT * FROM users",
                "UPDATE posts SET title = 'New Title' WHERE id = 1",
            ],
        ),
    ] = None,
) -> str:
    """
    SQL クエリを実行し、結果を JSON で返します。
    """
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    if not sql:
        result = {
            'success': False,
            'error': 'SQL クエリが指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        agent = manager.get_agent(server_name)
        
        logger.info(f"SQL 実行開始 ({server_name}): {sql[:100]}...")
        result = agent.execute_query(sql)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"SQL 実行エラー ({server_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name,
            'query': sql
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_table_list",
    description="""指定したサーバーのテーブル一覧を取得します。
""",
)
async def get_table_list(
    server_name: Annotated[
        str,
        Field(
            description=(
                "テーブル一覧を取得する SQL サーバーの名前"
            ),
            examples=["ytyng-blog"],
        ),
    ] = None,
) -> str:
    """指定したサーバーのテーブル一覧を取得する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        agent = manager.get_agent(server_name)
        
        logger.info(f"テーブル一覧取得開始 ({server_name})")
        result = agent.get_table_list()
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"テーブル一覧取得エラー ({server_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_table_schema",
    description="""指定したテーブルのスキーマ情報を取得します。
""",
)
async def get_table_schema(
    server_name: Annotated[
        str,
        Field(
            description=(
                "スキーマを取得する SQL サーバーの名前"
            ),
            examples=["ytyng-blog"],
        ),
    ] = None,
    table_name: Annotated[
        str,
        Field(
            description=("スキーマを取得するテーブル名"),
            examples=["users", "posts"],
        ),
    ] = None,
) -> str:
    """指定したテーブルのスキーマ情報を取得する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    if not table_name:
        result = {
            'success': False,
            'error': 'table_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        agent = manager.get_agent(server_name)
        
        logger.info(f"テーブルスキーマ取得開始 ({server_name}.{table_name})")
        result = agent.get_table_schema(table_name)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"テーブルスキーマ取得エラー ({server_name}.{table_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name,
            'table_name': table_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_mysql_status",
    description="""MySQL サーバーのステータス情報を取得します。
""",
)
async def get_mysql_status(
    server_name: Annotated[
        str,
        Field(
            description="MySQL サーバーの名前",
            examples=["mysql-server"],
        ),
    ] = None,
) -> str:
    """MySQL サーバーのステータス情報を取得する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        result = manager.get_mysql_status(server_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"MySQL ステータス取得エラー ({server_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_mysql_variables",
    description="""MySQL サーバーの変数情報を取得します。
""",
)
async def get_mysql_variables(
    server_name: Annotated[
        str,
        Field(
            description="MySQL サーバーの名前",
            examples=["mysql-server"],
        ),
    ] = None,
) -> str:
    """MySQL サーバーの変数情報を取得する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        result = manager.get_mysql_variables(server_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"MySQL 変数取得エラー ({server_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_mysql_processlist",
    description="""MySQL サーバーのプロセス一覧を取得します。
""",
)
async def get_mysql_processlist(
    server_name: Annotated[
        str,
        Field(
            description="MySQL サーバーの名前",
            examples=["mysql-server"],
        ),
    ] = None,
) -> str:
    """MySQL サーバーのプロセス一覧を取得する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        result = manager.get_mysql_processlist(server_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"MySQL プロセス一覧取得エラー ({server_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_mysql_databases",
    description="""MySQL サーバーのデータベース一覧を取得します。
""",
)
async def get_mysql_databases(
    server_name: Annotated[
        str,
        Field(
            description="MySQL サーバーの名前",
            examples=["mysql-server"],
        ),
    ] = None,
) -> str:
    """MySQL サーバーのデータベース一覧を取得する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        result = manager.get_mysql_databases(server_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"MySQL データベース一覧取得エラー ({server_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_mysql_table_status",
    description="""MySQL テーブルのステータス情報を取得します。
""",
)
async def get_mysql_table_status(
    server_name: Annotated[
        str,
        Field(
            description="MySQL サーバーの名前",
            examples=["mysql-server"],
        ),
    ] = None,
    table_name: Annotated[
        str,
        Field(
            description="テーブル名 (省略時は全テーブル)",
            examples=["users", "posts"],
        ),
    ] = None,
) -> str:
    """MySQL テーブルのステータス情報を取得する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        result = manager.get_mysql_table_status(server_name, table_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"MySQL テーブルステータス取得エラー ({server_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name,
            'table_name': table_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_mysql_indexes",
    description="""MySQL テーブルのインデックス情報を取得します。
""",
)
async def get_mysql_indexes(
    server_name: Annotated[
        str,
        Field(
            description="MySQL サーバーの名前",
            examples=["mysql-server"],
        ),
    ] = None,
    table_name: Annotated[
        str,
        Field(
            description="テーブル名",
            examples=["users", "posts"],
        ),
    ] = None,
) -> str:
    """MySQL テーブルのインデックス情報を取得する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    if not table_name:
        result = {
            'success': False,
            'error': 'table_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        result = manager.get_mysql_indexes(server_name, table_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"MySQL インデックス取得エラー ({server_name}.{table_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name,
            'table_name': table_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="optimize_mysql_table",
    description="""MySQL テーブルの最適化を実行します。
""",
)
async def optimize_mysql_table(
    server_name: Annotated[
        str,
        Field(
            description="MySQL サーバーの名前",
            examples=["mysql-server"],
        ),
    ] = None,
    table_name: Annotated[
        str,
        Field(
            description="最適化するテーブル名",
            examples=["users", "posts"],
        ),
    ] = None,
) -> str:
    """MySQL テーブルの最適化を実行する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    if not table_name:
        result = {
            'success': False,
            'error': 'table_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        result = manager.optimize_mysql_table(server_name, table_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"MySQL テーブル最適化エラー ({server_name}.{table_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name,
            'table_name': table_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="analyze_mysql_table",
    description="""MySQL テーブルの分析を実行します。
""",
)
async def analyze_mysql_table(
    server_name: Annotated[
        str,
        Field(
            description="MySQL サーバーの名前",
            examples=["mysql-server"],
        ),
    ] = None,
    table_name: Annotated[
        str,
        Field(
            description="分析するテーブル名",
            examples=["users", "posts"],
        ),
    ] = None,
) -> str:
    """MySQL テーブルの分析を実行する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    if not table_name:
        result = {
            'success': False,
            'error': 'table_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        result = manager.analyze_mysql_table(server_name, table_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"MySQL テーブル分析エラー ({server_name}.{table_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name,
            'table_name': table_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="check_mysql_table",
    description="""MySQL テーブルのチェックを実行します。
""",
)
async def check_mysql_table(
    server_name: Annotated[
        str,
        Field(
            description="MySQL サーバーの名前",
            examples=["mysql-server"],
        ),
    ] = None,
    table_name: Annotated[
        str,
        Field(
            description="チェックするテーブル名",
            examples=["users", "posts"],
        ),
    ] = None,
) -> str:
    """MySQL テーブルのチェックを実行する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    if not table_name:
        result = {
            'success': False,
            'error': 'table_name が指定されていません'
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    try:
        manager = init_sql_agent_manager()
        result = manager.check_mysql_table(server_name, table_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"MySQL テーブルチェックエラー ({server_name}.{table_name}): {e}")
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name,
            'table_name': table_name
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


def main() -> None:
    """
    メイン関数: MCPサーバーを起動します
    """
    logger.info("MCP サーバー起動中...")

    # SQL Agent Manager を初期化
    try:
        init_sql_agent_manager()
        logger.info("SQL Agent Manager を初期化しました")
    except Exception as e:
        error_msg = f"❌ エラー: SQL Agent Manager の初期化に失敗しました: {e}"
        logger.error(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

    try:
        # サーバーを起動 (stdio モード)
        logger.info("MCP サーバー起動完了")
        server.run()  # stdio is default
    except KeyboardInterrupt:
        logger.info("MCP サーバーを終了します (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"MCP サーバーエラー: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

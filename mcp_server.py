#!/usr/bin/env python3
"""
MCP server for connecting to MySQL and PostgreSQL databases
"""

import json
import logging
import os
import sys
from textwrap import dedent
from typing import Annotated

import yaml

# Completely suppress logs before importing fastmcp
logging.getLogger().setLevel(logging.ERROR)
for logger_name in ['fastmcp', 'mcp', 'uvicorn', 'asyncio', 'rich']:
    logging.getLogger(logger_name).setLevel(logging.ERROR)
    logging.getLogger(logger_name).disabled = True

import fastmcp
from dotenv import load_dotenv
from pydantic import Field

from sql_agent import SQLAgentManager

# Load environment variables from .env file
load_dotenv()


def setup_logger_for_mcp_server():
    """
    Configure logger for MCP server
    Prevent logs from being output to stdout
    """
    log_file = '/tmp/sql-agent-mcp-server.log'
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(
        logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers = []  # Clear existing handlers
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG)

    # Configure third-party loggers
    for logger_name, log_level in [
        ('httpx', logging.WARNING),
        ('urllib3', logging.WARNING),
        ('asyncio', logging.WARNING),
        ('fastmcp', logging.INFO),
        ('FastMCP.fastmcp.server.server', logging.INFO),
        ('mcp', logging.WARNING),
        ('uvicorn', logging.WARNING),
        ('rich', logging.WARNING),
    ]:
        _logger = logging.getLogger(logger_name)
        _logger.handlers = []
        _logger.addHandler(file_handler)
        _logger.setLevel(log_level)
        _logger.propagate = False


# Execute log configuration for MCP server
setup_logger_for_mcp_server()

# Get logger for application
logger = logging.getLogger('sql-agent-mcp-server')

# Global SQL Agent Manager
sql_agent_manager = None


def get_config():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, 'config.yaml')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


config = get_config()


def init_sql_agent_manager():
    """SQL Agent Manager を初期化する"""
    global sql_agent_manager
    if sql_agent_manager is None:
        mysql_servers = config.get('mysql_servers', [])
        sql_agent_manager = SQLAgentManager(mysql_servers)
    return sql_agent_manager


sql_server_name_and_description = '\n\n'.join(
    [
        f"## server_name: {server['name']}\n\n{server['description']}"
        for server in config.get('mysql_servers', [])
    ]
)

sql_server_names = [
    server['name'] for server in config.get('mysql_servers', [])
]


# MCPサーバーの設定
server = fastmcp.FastMCP(
    name="sql-agent-mcp-server",
    instructions=dedent(
        f"""
        MySQL と Postgres に接続する MCP サーバーです。
        テーブルの読み取り権限のみ持ちます。Update, Insert はできません。
        個人情報を含むテーブルや、秘密情報が含まれるテーブルは、
        SELECT 権限を付与していないため内容を読み取ることはできませんが、
        テーブルの構造を読むことはできます。

        # SQL サーバー の名前 (server_name) と説明

        {sql_server_name_and_description}
        """
    ),
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

        result = {'success': True, 'servers': servers, 'count': len(servers)}

        logger.info(f"サーバー一覧を取得しました: {len(servers)} 個")
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"サーバー一覧取得エラー: {e}")
        result = {'success': False, 'error': str(e)}
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="execute_sql",
    description=f"""SQL クエリを実行し、結果を JSON で返します。

利用可能な server_name: {', '.join(sql_server_names)}
""",
)
async def execute_sql(
    server_name: Annotated[
        str,
        Field(
            description=(
                "実行する SQL サーバーの名前。 config.yaml の mysql_servers の name"
            ),
            examples=sql_server_names,
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
            'error': 'server_name is not specified',
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    if not sql:
        result = {'success': False, 'error': 'SQL query is not specified'}
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
            'query': sql,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_table_list",
    description=f"""指定したサーバーのテーブル一覧を取得します。

利用可能な server_name: {', '.join(sql_server_names)}
""",
)
async def get_table_list(
    server_name: Annotated[
        str,
        Field(
            description=("テーブル一覧を取得する SQL サーバーの名前"),
            examples=sql_server_names,
        ),
    ] = None,
) -> str:
    """指定したサーバーのテーブル一覧を取得する"""
    if not server_name:
        result = {
            'success': False,
            'error': 'server_name is not specified',
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
            'server_name': server_name,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool(
    name="get_table_schema",
    description=f"""指定したテーブルのスキーマ情報を取得します。

利用可能な server_name: {', '.join(sql_server_names)}
""",
)
async def get_table_schema(
    server_name: Annotated[
        str,
        Field(
            description=("スキーマを取得する SQL サーバーの名前"),
            examples=sql_server_names,
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
            'error': 'server_name is not specified',
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    if not table_name:
        result = {'success': False, 'error': 'table_name is not specified'}
        return json.dumps(result, ensure_ascii=False, indent=2)

    try:
        manager = init_sql_agent_manager()
        agent = manager.get_agent(server_name)

        logger.info(f"テーブルスキーマ取得開始 ({server_name}.{table_name})")
        result = agent.get_table_schema(table_name)

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(
            f"テーブルスキーマ取得エラー ({server_name}.{table_name}): {e}"
        )
        result = {
            'success': False,
            'error': str(e),
            'server_name': server_name,
            'table_name': table_name,
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

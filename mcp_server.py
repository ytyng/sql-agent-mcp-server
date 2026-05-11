#!/usr/bin/env python3
"""
MCP server for connecting to MySQL and PostgreSQL databases
"""

import json
import sys
from textwrap import dedent
from typing import Annotated

import fastmcp
from pydantic import Field

from config_loader import load_config
from logging_config import logger, setup_logger_for_mcp_server
from sql_agent import SQLAgentManager

# 遅延初期化: main() で確定する。
_config: dict | None = None
_sql_agent_manager: SQLAgentManager | None = None


def _get_manager() -> SQLAgentManager:
    """SQL Agent Manager を遅延生成して取得する"""
    global _sql_agent_manager
    if _sql_agent_manager is None:
        if _config is None:
            raise RuntimeError(
                "Config not loaded. main() を呼ぶ前に _get_manager() が"
                " 呼ばれた可能性があります。"
            )
        _sql_agent_manager = SQLAgentManager(_config.get('sql_servers', []))
    return _sql_agent_manager


def build_server(config: dict) -> fastmcp.FastMCP:
    """config から FastMCP サーバーインスタンスを構築してツールを登録する"""
    sql_servers = config.get('sql_servers', [])
    sql_server_names = [server['name'] for server in sql_servers]
    sql_server_name_and_description = '\n\n'.join(
        [
            f"## server_name: {server['name']}\n\n"
            f"{server.get('description', '')}"
            for server in sql_servers
        ]
    )

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
        try:
            manager = _get_manager()
            servers = manager.get_server_list()
            result = {
                'success': True,
                'servers': servers,
                'count': len(servers),
            }
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
                    "実行する SQL サーバーの名前。"
                    " config.yaml の sql_servers の name"
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
        if not server_name:
            result = {
                'success': False,
                'error': 'server_name is not specified',
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

        if not sql:
            result = {
                'success': False,
                'error': 'SQL query is not specified',
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

        try:
            manager = _get_manager()
            agent = manager.get_agent(server_name)

            logger.info(f"SQL 実行開始 ({server_name})")
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

    return server


def main() -> None:
    """メイン関数: MCPサーバーを起動します"""
    global _config

    # 起動エラーもログに残るよう、デフォルトパス (or 環境変数) で先にロガーを
    # 初期化する。
    setup_logger_for_mcp_server()

    try:
        _config = load_config()
    except Exception as e:
        error_msg = f"❌ エラー: 設定の読み込みに失敗しました: {e}"
        logger.error(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

    # config に log_file_path があれば再設定 (パスが違えば差し替え)
    if _config.get('log_file_path'):
        setup_logger_for_mcp_server(_config['log_file_path'])

    logger.info("MCP サーバー起動中...")

    try:
        server = build_server(_config)
        _get_manager()
        logger.info("SQL Agent Manager を初期化しました")
    except Exception as e:
        error_msg = f"❌ エラー: SQL Agent Manager の初期化に失敗しました: {e}"
        logger.error(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

    try:
        logger.info("MCP サーバー起動完了")
        server.run()  # stdio is default
    except KeyboardInterrupt:
        logger.info("MCP サーバーを終了します (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"MCP サーバーエラー: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

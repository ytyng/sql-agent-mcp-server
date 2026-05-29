#!/usr/bin/env python3
"""
MCP server for connecting to MySQL and PostgreSQL databases
"""

import json
import os
import sys
from textwrap import dedent
from typing import Annotated

import fastmcp
from pydantic import Field

from config_loader import load_config, load_metadata_cache
from logging_config import logger, setup_logger_for_mcp_server
from sql_agent import SQLAgentManager


def build_server() -> fastmcp.FastMCP:
    """FastMCP サーバーインスタンスを構築してツールを登録する。

    config 本体 (パスワード等を含む) はここでは読み込まない。getter command
    経由だと起動時に 1Password 認証が走ってしまうため。代わりに、機密を含まない
    ローカルメタデータキャッシュ (前回ロード時に保存) から server_name 一覧を
    instructions / tool description に埋め込む。キャッシュが無い初回起動時は
    一覧が空になるが、LLM が list_sql_servers を呼べば実際の config が遅延ロード
    される (このタイミングで初めて認証が走る)。

    SQLAgentManager には load_config を loader として渡し、初回ツール呼び出し時に
    遅延ロードさせる。
    """
    cache = load_metadata_cache() or {}
    cached_servers = cache.get('sql_servers', [])
    # キャッシュが手動編集等で壊れて name 欠落があっても起動を止めない。
    sql_server_names = [
        server['name'] for server in cached_servers if server.get('name')
    ]
    if sql_server_names:
        sql_server_name_and_description = '\n\n'.join(
            [
                f"## server_name: {server['name']}\n\n"
                f"{server.get('description', '')}"
                for server in cached_servers
                if server.get('name')
            ]
        )
    else:
        sql_server_name_and_description = (
            "(まだサーバー一覧をロードしていません。"
            "list_sql_servers ツールを呼ぶと取得できます。)"
        )

    manager = SQLAgentManager(load_config)

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

            下記はローカルキャッシュに基づく一覧です。最新の一覧は
            list_sql_servers ツールで取得してください。

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
            str | None,
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

    # 起動時は config 本体 (パスワード等) を読み込まない。getter command 経由だと
    # 起動時に 1Password 認証が走ってしまうため、実際の config ロードは最初の
    # ツール呼び出しまで遅延させる (SQLAgentManager._ensure_loaded)。
    #
    # ログパスの解決順:
    #   1. 環境変数 SQL_AGENT_LOG_FILE_PATH
    #   2. メタデータキャッシュの log_file_path (前回ロード時に保存)
    #   3. デフォルトパス
    # config (YAML) 内の log_file_path は初回ロード後に再設定される。
    cache = load_metadata_cache() or {}
    cached_log_path = cache.get('log_file_path')
    if not os.environ.get('SQL_AGENT_LOG_FILE_PATH') and cached_log_path:
        setup_logger_for_mcp_server(cached_log_path)
    else:
        setup_logger_for_mcp_server()

    logger.info("MCP サーバー起動中...")

    try:
        server = build_server()
        logger.info("SQL Agent Manager を初期化しました (config は遅延ロード)")
    except Exception as e:
        error_msg = f"❌ エラー: MCP サーバーの構築に失敗しました: {e}"
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

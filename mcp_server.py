#!/usr/bin/env python3
"""
MySQL, Postgres に接続する MCP サーバー
"""

import os
import sys
from typing import Annotated
import yaml

import fastmcp
from fastmcp.utilities.types import Image
from dotenv import load_dotenv
from pydantic import Field


# .envファイルから環境変数を読み込む
load_dotenv()


def get_config():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, 'config.yaml')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


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
    config = get_config()
    # TODO: 書く


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
    # TODO 書く


def main() -> None:
    """
    メイン関数: MCPサーバーを起動します
    """
    logger.info("MCP サーバー起動中...")

    # 必要な環境変数のチェック
    required_env_vars = ['OPENAI_API_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        error_msg = f"❌ エラー: 必要な環境変数が設定されていません: {', '.join(missing_vars)}"
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

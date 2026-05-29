#!/usr/bin/env python3
"""
sql-agent-cli - SQL Agent MCP サーバーの CLI インターフェイス

MCP サーバーと同じ機能をコマンドラインから利用可能にする。
SQLAgentManager を直接使用し、MCP レイヤーを通さない。
"""
import argparse
import json
import sys

from config_loader import load_config
from logging_config import setup_logger_for_mcp_server
from sql_agent import SQLAgentManager


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _read_sql_from_stdin_or_arg(sql_arg: str | None) -> str:
    if sql_arg:
        return sql_arg
    if sys.stdin.isatty():
        print(
            "Error: --sql を指定するか、SQL を標準入力から渡してください",
            file=sys.stderr,
        )
        sys.exit(1)
    sql = sys.stdin.read().strip()
    if not sql:
        print("Error: SQL が空です", file=sys.stderr)
        sys.exit(1)
    return sql


def _build_manager() -> SQLAgentManager:
    # まずデフォルトパスでロガーを初期化 (load_config 失敗時にもログを残す)。
    # CLI は明示的に実行されるので、起動時に config をロードして認証が走っても
    # 問題ない。SQLAgentManager が初回アクセス時に load_config を呼び、
    # log_file_path の再設定とメタデータキャッシュ更新も行う。
    setup_logger_for_mcp_server()
    return SQLAgentManager(load_config)


# -- subcommand handlers --


def cmd_list_sql_servers(args):
    manager = _build_manager()
    servers = manager.get_server_list()
    _print_json(
        {
            'success': True,
            'count': len(servers),
            'servers': servers,
        }
    )


def cmd_execute_sql(args):
    sql = _read_sql_from_stdin_or_arg(args.sql)
    manager = _build_manager()

    try:
        agent = manager.get_agent(args.server)
    except ValueError as e:
        _print_json(
            {
                'success': False,
                'error': str(e),
                'server_name': args.server,
            }
        )
        sys.exit(1)

    result = agent.execute_query(sql)
    _print_json(result)
    if not result.get('success'):
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='sql-agent-cli',
        description=(
            'SQL Agent CLI - MySQL/PostgreSQL に SSH トンネル経由でも'
            ' 接続して SQL を実行する CLI ツール。'
            ' config.yaml の sql_servers に登録されたサーバーを利用する。'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '使用例:\n'
            '  sql-agent-cli list-sql-servers\n'
            '  sql-agent-cli execute-sql --server prod-db --sql "SELECT 1"\n'
            '  echo "SELECT NOW()" | sql-agent-cli execute-sql -s prod-db\n'
        ),
    )
    sub = parser.add_subparsers(dest='command', metavar='<subcommand>')

    # list-sql-servers
    p = sub.add_parser(
        'list-sql-servers',
        help='登録されている SQL サーバーの一覧を JSON で出力',
        description=(
            'config.yaml の sql_servers に登録された全サーバーを'
            ' name, description, engine, host, port, schema 付きで返す。'
            ' 引数なし。'
        ),
    )
    p.set_defaults(func=cmd_list_sql_servers)

    # execute-sql
    p = sub.add_parser(
        'execute-sql',
        help='指定サーバーで SQL を実行し結果を JSON で出力',
        description=(
            '指定したサーバーで SQL クエリを実行し、結果を JSON で出力する。\n'
            'SELECT は rows / row_count を、INSERT/UPDATE/DELETE は'
            ' affected_rows を返す。\n'
            'SSH トンネルが必要なサーバーは自動的に確立・切断される。\n'
            '読み取り権限のみ付与されたサーバーでは UPDATE/INSERT は失敗する。'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '使用例:\n'
            '  sql-agent-cli execute-sql -s prod-db --sql "SHOW TABLES"\n'
            '  sql-agent-cli execute-sql -s prod-db --sql "SELECT * FROM users LIMIT 10"\n'
            '  cat query.sql | sql-agent-cli execute-sql -s prod-db\n'
        ),
    )
    p.add_argument(
        '-s',
        '--server',
        required=True,
        help='接続先サーバー名 (config.yaml の sql_servers の name)',
    )
    p.add_argument(
        '--sql',
        default=None,
        help='実行する SQL クエリ。省略時は stdin から読み取る',
    )
    p.set_defaults(func=cmd_execute_sql)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == '__main__':
    main()

import logging
import os

_current_log_file_path: str | None = None

DEFAULT_LOG_FILE_PATH = '/tmp/sql-agent-mcp-server.log'


def setup_logger_for_mcp_server(log_file_path: str | None = None) -> None:
    """
    Configure logger for MCP server / CLI.
    Prevent logs from being output to stdout.

    log_file_path の解決順:
        1. 引数 log_file_path
        2. 環境変数 SQL_AGENT_LOG_FILE_PATH
        3. DEFAULT_LOG_FILE_PATH

    同じパスで2回呼ばれた場合は何もしない (冪等)。
    異なるパスで呼ばれた場合は、ハンドラを差し替える
    (起動シーケンスで先にデフォルトパスで初期化 → config 読み込み後に
    log_file_path で再設定するユースケースに対応)。
    """
    global _current_log_file_path

    if log_file_path is None:
        log_file_path = os.environ.get(
            'SQL_AGENT_LOG_FILE_PATH', DEFAULT_LOG_FILE_PATH
        )

    if _current_log_file_path == log_file_path:
        return
    _current_log_file_path = log_file_path

    file_handler = logging.FileHandler(
        log_file_path, mode='a', encoding='utf-8'
    )
    file_handler.setFormatter(
        logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    )

    # Configure root logger - これが一番重要！
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
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
        _logger.handlers.clear()
        _logger.addHandler(file_handler)
        _logger.setLevel(log_level)
        _logger.propagate = False


# メインロガー (setup 前でも import 可能。setup 後に handler が付く)
logger = logging.getLogger('sql_agent')

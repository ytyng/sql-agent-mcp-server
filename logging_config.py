import logging
import os

_logger_initialized = False


def setup_logger_for_mcp_server():
    """
    Configure logger for MCP server
    Prevent logs from being output to stdout
    """
    global _logger_initialized
    if _logger_initialized:
        return

    _logger_initialized = True
    log_file = os.environ.get(
        'SQL_AGENT_LOG_FILE_PATH', '/tmp/sql-agent-mcp-server.log'
    )
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(
        logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    )

    # Configure root logger - これが一番重要！
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # 既存の handler をクリア
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


# Execute log configuration for MCP server
setup_logger_for_mcp_server()

# メインロガー
logger = logging.getLogger('sql_agent')

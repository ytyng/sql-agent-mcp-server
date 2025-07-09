import logging

# ファイルハンドラーの設定
log_file = '/tmp/sql-agent-mcp-server.log'
file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)

# ルートロガーの設定
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

logger_set_up = False


def setup_logger_for_mcp_server():
    """
    Configure logger for MCP server
    Prevent logs from being output to stdout
    """
    global logger_set_up
    if logger_set_up:
        return

    logger_set_up = True
    log_file = '/tmp/sql-agent-mcp-server.log'
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(
        logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    )

    # # Configure root logger
    # root_logger = logging.getLogger()
    # root_logger.handlers = []  # Clear existing handlers
    # root_logger.addHandler(file_handler)
    # root_logger.setLevel(logging.DEBUG)

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

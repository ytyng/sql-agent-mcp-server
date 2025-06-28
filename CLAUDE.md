# SQL Agent MCP Server - Claude Documentation

An MCP server that connects to MySQL and PostgreSQL databases to execute queries.

## Project Overview

This project provides a server that can execute SQL queries against multiple databases (MySQL/PostgreSQL) using the Model Context Protocol (MCP).

### Key Features

- Connection management for multiple database servers
- Secure connections via SSH tunnels
- Retrieval of table lists and schema information
- SQL query execution
- MySQL-specific administrative commands

## Development Environment

- Python 3.11+
- uv package manager
- FastMCP framework

## Important Files

- `mcp_server.py`: Main implementation of the MCP server
- `sql_agent.py`: Database connection and query execution logic
- `config.yaml`: Database connection configuration
- `launch-mcp-server.sh`: Server startup script
- `test-requests/`: Test script suite

## Testing

```bash
# Verify virtual environment and server startup
./launch-mcp-server.sh

# Test tool list retrieval
python3 test-requests/test_list_tools.py

# Test actual SQL execution
python3 test-requests/test_mangazenkan_dev.py
```

## Logging Configuration

Since MCP communication uses JSON-RPC standard input/output, logs output to stdout would interfere with communication.
This project implements the following measures:

- Configure log handlers to file output only with the `setup_logger_for_mcp_server()` function
- Adjust log levels for FastMCP and related libraries
- Application logs are output to `/tmp/sql-agent-mcp-server.log`

## Development Notes

- Use `uv add` when adding new dependencies
- Manage database connection information with `config.yaml`
- SSH tunnel functionality can be tested with `test_ssh_tunnel.py`
- Consider the impact on MCP communication when changing log settings

## Security

- Properly manage passwords and private keys
- Support secure connections via SSH tunnels
- SQL injection countermeasures are implemented on the sql_agent side
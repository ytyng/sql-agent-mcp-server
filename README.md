# SQL Agent MCP Server

![](./documents/images/featured-image.png)

An MCP server that connects to MySQL and PostgreSQL databases to execute queries. A standalone CLI (`sql-agent-cli`) is also provided.

[日本語版 README はこちら](README.ja.md)

## ⚠️ Breaking Changes

- **Config key rename**: `mysql_servers` → `sql_servers`. Update your `config.yaml`. The old key is no longer recognized.
- **PostgreSQL row format**: The cursor was changed from `DictCursor` to `RealDictCursor`, so SELECT result rows are now plain dicts (`[{"col": value}]`) instead of list-shaped `DictRow` (`[[value]]`). This is a bug fix — clients that depended on positional access on Postgres results need to switch to key access.
- **`python-dotenv` dependency removed**: `.env` files are no longer auto-loaded. Pass environment variables (`SQL_AGENT_CONFIG_YAML`, `SQL_AGENT_LOG_FILE_PATH`) via your MCP client's `env` block, or via your shell. Inline YAML can also be passed via `SQL_AGENT_CONFIG_YAML` instead of using a `config.yaml` file.

## Features

- Connection management for multiple database servers
- Support for both MySQL and PostgreSQL
- SSH tunnel connection support
- Execute SQL queries via MCP server or CLI
- Configuration via `config.yaml` or `SQL_AGENT_CONFIG_YAML` environment variable

## Installation

```bash
# Install dependencies
uv sync
```

## Configuration

Create a `config.yaml` file to configure database server connection information. Alternatively, the entire YAML can be provided inline via the `SQL_AGENT_CONFIG_YAML` environment variable (takes precedence over the file).

```yaml
# Optional: log file path
# Resolution order: this YAML value > SQL_AGENT_LOG_FILE_PATH env var > /tmp/sql-agent-mcp-server.log
log_file_path: /tmp/sql-agent-mcp-server.log

sql_servers:
  - name: my-postgres
    description: "PostgreSQL server"
    engine: postgres
    host: localhost
    port: 5432
    schema: mydb
    user: postgres
    password: password

  - name: my-mysql
    description: "MySQL server"
    engine: mysql
    host: localhost
    port: 3306
    schema: mydb
    user: root
    password: password
```

### Connection via SSH Tunnel

You can securely connect to remote databases using SSH tunnels.

```yaml
sql_servers:
  - name: remote-db
    description: "Remote database via SSH tunnel"
    engine: postgres
    host: localhost  # Use localhost for SSH tunnel connections
    port: 5432
    schema: remote_db
    user: db_user
    password: db_password
    ssh_tunnel:
      host: ssh.example.com
      port: 22
      user: ssh_user
      # For password authentication
      password: ssh_password
      # Or for private key authentication
      # private_key_path: ~/.ssh/id_rsa
      # private_key_passphrase: key_passphrase  # If passphrase is required
```

## Usage

### Starting the MCP Server

```bash
# Using startup script (recommended)
./launch-mcp-server.sh

# Or start directly
source .venv/bin/activate
python mcp_server.py
```

### MCP Tools

#### `list_sql_servers`
Get the list of registered SQL servers.

#### `execute_sql`
Execute a SQL query against a registered server and return the result as JSON.

```
Parameters:
- server_name: Server name (must match a name in sql_servers)
- sql: SQL query to execute
```

For schema introspection (table list, column info, etc.), use standard SQL such as `SHOW TABLES`, `DESCRIBE <table>` (MySQL) or queries against `pg_tables` / `information_schema` (PostgreSQL) via `execute_sql`.

### CLI Usage

A CLI mirrors the MCP tools — useful when you don't want to load the MCP server into the AI context.

```bash
sql-agent-cli list-sql-servers
sql-agent-cli execute-sql --server my-postgres --sql "SELECT 1"
echo "SELECT NOW()" | sql-agent-cli execute-sql -s my-postgres
```

`sql-agent-cli --help` and `sql-agent-cli <subcommand> --help` show full options.

## Testing

The `test-requests/` directory contains test scripts for the MCP server.

### Test Library

- `test_mcp_lib.py`: Common library for communicating with MCP server
- `test_list_tools.py`: Test to get list of available tools
- `test_mangazenkan_dev.py`: Test for SQL execution against actual database

```bash
# Test to get tool list
python3 test-requests/test_list_tools.py

# SQL execution test
python3 test-requests/test_mangazenkan_dev.py
```

## Logging

- Application logs are output to `/tmp/sql-agent-mcp-server.log`
- Configured to prevent logs from being output to stdout for MCP communication

## Security Considerations

- `config.yaml` contains database passwords, so manage it appropriately
- When using SSH private keys, set appropriate file permissions
- Consider using environment variables or secret management tools in production environments

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

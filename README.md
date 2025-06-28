# SQL Agent MCP Server

An MCP server that connects to MySQL and PostgreSQL databases to execute queries.

[日本語版 README はこちら](README.ja.md)

## Features

- Connection management for multiple database servers
- Support for both MySQL and PostgreSQL
- SSH tunnel connection support
- Retrieve table lists and schema information
- Execute SQL queries
- MySQL-specific administrative commands

## Installation

```bash
# Install dependencies
uv sync
```

## Configuration

Create a `config.yaml` file to configure database server connection information.

```yaml
mysql_servers:
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
mysql_servers:
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

### Available Tools

#### 1. sql_query
Execute SQL queries.

```
Parameters:
- server_name: Server name
- sql: SQL query to execute
```

#### 2. get_server_list
Get a list of registered servers.

#### 3. get_table_list
Get a list of tables for the specified server.

```
Parameters:
- server_name: Server name
```

#### 4. get_table_schema
Get schema information for a table.

```
Parameters:
- server_name: Server name
- table_name: Table name
```

### MySQL-Specific Tools

Administrative tools that can only be used with MySQL servers.

- `get_mysql_status`: Get status information
- `get_mysql_variables`: Get variable information
- `get_mysql_processlist`: Get process list
- `get_mysql_databases`: Get database list
- `get_mysql_table_status`: Get table status
- `get_mysql_indexes`: Get index information
- `analyze_mysql_table`: Analyze table
- `optimize_mysql_table`: Optimize table
- `check_mysql_table`: Check table
- `repair_mysql_table`: Repair table

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
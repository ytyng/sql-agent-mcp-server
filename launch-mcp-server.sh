#!/usr/bin/env zsh

# MCPサーバーを起動するスクリプト

cd $(dirname $0)

# 設定は ~/.config/sql-agent-mcp-server/config.yaml から読む。
# 秘密を 1Password 等に置く場合は、その config.yaml に
# config_override_command を書く (.loadenv.sh の読み込みは廃止)。

.venv/bin/python3 mcp_server.py

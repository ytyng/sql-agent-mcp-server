#!/usr/bin/env python3
"""
SSH トンネル機能のテストスクリプト
"""

import yaml
import logging
from sql_agent import SQLAgent

# ログ設定
logging.basicConfig(level=logging.INFO)

def test_ssh_tunnel():
    """SSH トンネル機能をテストする"""
    
    # テスト用の設定
    test_config = {
        'name': 'test-ssh-server',
        'description': 'SSH トンネルテスト用サーバー',
        'engine': 'postgres',
        'host': 'localhost',  # リモートサーバー上の DB ホスト
        'port': 5432,
        'schema': 'test_db',
        'user': 'test_user',
        'password': 'test_password',
        'ssh_tunnel': {
            'host': 'ssh.example.com',
            'port': 22,
            'user': 'ssh_user',
            'password': 'ssh_password',
            # 'private_key_path': '~/.ssh/id_rsa',  # 秘密鍵を使う場合
            # 'private_key_passphrase': 'key_passphrase',  # パスフレーズがある場合
        }
    }
    
    print("SSH トンネル機能のテスト設定例:")
    print(yaml.dump(test_config, allow_unicode=True, default_flow_style=False))
    
    # 実際に接続するには以下のコメントを外してください
    # agent = SQLAgent(test_config)
    # try:
    #     agent.connect()
    #     print("SSH トンネル経由でデータベースに接続しました！")
    #     
    #     # テーブル一覧を取得
    #     result = agent.get_table_list()
    #     print(f"テーブル数: {result.get('row_count', 0)}")
    #     
    # finally:
    #     agent.disconnect()
    #     print("接続を閉じました")


if __name__ == "__main__":
    test_ssh_tunnel()
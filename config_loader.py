"""
SQL Agent の設定ローダー。

SQL_AGENT_CONFIG_YAML 環境変数があればその YAML 文字列を、
無ければ同ディレクトリの config.yaml を読み込んで dict で返す。
"""
import os
from typing import Any

import yaml


def load_config(config_filename: str = 'config.yaml') -> dict[str, Any]:
    """
    設定を読み込んで dict で返す。

    SQL_AGENT_CONFIG_YAML 環境変数が設定されていればそれを YAML として
    パースし、無ければ このモジュールと同ディレクトリの config.yaml を読む。
    """
    config_yaml_env = os.environ.get('SQL_AGENT_CONFIG_YAML')
    if config_yaml_env:
        source = 'SQL_AGENT_CONFIG_YAML 環境変数'
        try:
            data = yaml.safe_load(config_yaml_env)
        except yaml.YAMLError as e:
            raise ValueError(f"{source} の YAML パースに失敗: {e}") from e
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, config_filename)
        source = config_path
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"{source} の YAML パースに失敗: {e}") from e

    if not data:
        raise ValueError(f"Config is empty: {source}")

    if not isinstance(data, dict):
        raise ValueError(
            f"Config must be a YAML mapping, got {type(data).__name__}:"
            f" {source}"
        )

    return data

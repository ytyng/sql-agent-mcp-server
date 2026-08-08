#!/usr/bin/env python3
"""
config_loader の設定解決・上書きマージのテスト。

    python3 -m unittest test_config_loader

外部プロセスに依存する部分 (config_override_command) は、`cat <一時ファイル>`
を取得コマンドとして使うことで、1Password 等が無い環境でも実行できるようにする。
"""

import os
import tempfile
import unittest
from unittest import mock

import config_loader


class ConfigPathTest(unittest.TestCase):
    def test_uses_home_at_call_time(self):
        """HOME はモジュール読み込み時ではなく呼び出し時に解決される。"""
        with mock.patch.dict(os.environ, {'HOME': '/tmp/example-home'}):
            self.assertEqual(
                config_loader.get_config_path(),
                '/tmp/example-home/.config/sql-agent-mcp-server/config.yaml',
            )


class ConfigLoaderTestBase(unittest.TestCase):
    """
    HOME を一時ディレクトリへ差し替える共通の土台。

    テストメソッドは持たない (持たせると継承先で二重に実行されるため)。
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.config_dir = os.path.join(
            self.tmpdir.name, '.config', 'sql-agent-mcp-server'
        )
        os.makedirs(self.config_dir)
        self.config_path = os.path.join(self.config_dir, 'config.yaml')
        # HOME だけを差し替え、他の環境変数は clear=True で落としておく
        # (実行環境に SQL_AGENT_CONFIG_YAML 等が居ても影響を受けないように)。
        self.env = mock.patch.dict(
            os.environ, {'HOME': self.tmpdir.name}, clear=True
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def write_config(self, text: str) -> None:
        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write(text)

    def write_temp_yaml(self, text: str) -> str:
        """取得コマンドに読ませる YAML を一時ファイルに書き、パスを返す。"""
        path = os.path.join(self.tmpdir.name, 'override.yaml')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path


class LoadConfigTest(ConfigLoaderTestBase):
    def test_reads_config_from_user_config_dir(self):
        self.write_config('sql_servers:\n  - name: a\n    engine: mysql\n')
        config = config_loader.load_config()
        self.assertEqual(
            config['sql_servers'], [{'name': 'a', 'engine': 'mysql'}]
        )

    def test_missing_config_file_raises(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            config_loader.load_config()
        self.assertIn(self.config_path, str(ctx.exception))

    def test_project_directory_config_is_ignored(self):
        """リポジトリ内の config.yaml は読まない (決め打ちパスのみ)。"""
        project_config = os.path.join(
            os.path.dirname(os.path.abspath(config_loader.__file__)),
            'config.yaml',
        )
        if os.path.exists(project_config):
            # 開発者の実設定を壊さないよう、既にある場合は作らず消さない。
            self.skipTest('リポジトリに実在する config.yaml を触らない')
        with open(project_config, 'w', encoding='utf-8') as f:
            f.write('sql_servers:\n  - name: from-project-dir\n')
        self.addCleanup(os.remove, project_config)

        # 決め打ちパス側には config.yaml を置いていないので、
        # プロジェクト側にフォールバックしていれば読めてしまう。
        with self.assertRaises(FileNotFoundError):
            config_loader.load_config()

    def test_env_yaml_takes_precedence_over_file(self):
        self.write_config('sql_servers:\n  - name: from-file\n')
        os.environ['SQL_AGENT_CONFIG_YAML'] = (
            'sql_servers:\n  - name: from-env\n'
        )
        config = config_loader.load_config()
        self.assertEqual(config['sql_servers'], [{'name': 'from-env'}])

    def test_removed_getter_env_raises_with_migration_hint(self):
        self.write_config('sql_servers: []\n')
        os.environ['SQL_AGENT_CONFIG_YAML_GETTER_COMMAND'] = 'op read x'
        with self.assertRaises(ValueError) as ctx:
            config_loader.load_config()
        self.assertIn('config_override_command', str(ctx.exception))

    def test_removed_getter_env_is_ignored_when_env_yaml_is_used(self):
        """
        SQL_AGENT_CONFIG_YAML があれば、旧 getter 環境変数が残っていても通す。

        旧実装でも SQL_AGENT_CONFIG_YAML が優先され getter は参照されなかった。
        使っていない環境変数が残っているだけで落とすと、無用な後方互換の破壊になる。
        """
        os.environ['SQL_AGENT_CONFIG_YAML'] = (
            'sql_servers:\n  - name: from-env\n'
        )
        os.environ['SQL_AGENT_CONFIG_YAML_GETTER_COMMAND'] = 'op read x'
        config = config_loader.load_config()
        self.assertEqual(config['sql_servers'], [{'name': 'from-env'}])


class ConfigOverrideTest(ConfigLoaderTestBase):
    def test_override_replaces_lists_and_merges_mappings(self):
        override = self.write_temp_yaml(
            'sql_servers:\n'
            '  - name: from-secret\n'
            '    password: secret\n'
            'nested:\n'
            '  b: 2\n'
        )
        self.write_config(
            f'config_override_command: cat {override}\n'
            'log_file_path: /tmp/local.log\n'
            'sql_servers:\n'
            '  - name: from-local\n'
            'nested:\n'
            '  a: 1\n'
        )
        config = config_loader.load_config()

        # リストは丸ごと置き換わる
        self.assertEqual(
            config['sql_servers'],
            [{'name': 'from-secret', 'password': 'secret'}],
        )
        # 取得側に無いキーはローカルの値が残る
        self.assertEqual(config['log_file_path'], '/tmp/local.log')
        # マッピングは再帰的に混ざる
        self.assertEqual(config['nested'], {'a': 1, 'b': 2})
        # 適用済みのキーは残さない
        self.assertNotIn('config_override_command', config)

    def test_override_is_not_fetched_recursively(self):
        override = self.write_temp_yaml(
            'config_override_command: /bin/false\nsql_servers: []\n'
        )
        self.write_config(f'config_override_command: cat {override}\n')
        # 取得 YAML 側の config_override_command を実行すると /bin/false で
        # 失敗するため、例外が出なければ再帰していないことが示される。
        config = config_loader.load_config()
        self.assertNotIn('config_override_command', config)

    def test_override_applies_before_template_expansion(self):
        """取得側から sql_server_templates を丸ごと差し替えられる。"""
        override = self.write_temp_yaml(
            'sql_server_templates:\n'
            '  - name: shared\n'
            '    host: secret-host\n'
            '    password: secret\n'
        )
        self.write_config(
            f'config_override_command: cat {override}\n'
            'sql_servers:\n'
            '  - name: a\n'
            '    template: shared\n'
            '    schema: mydb\n'
        )
        config = config_loader.load_config()
        self.assertEqual(
            config['sql_servers'],
            [
                {
                    'name': 'a',
                    'host': 'secret-host',
                    'password': 'secret',
                    'schema': 'mydb',
                }
            ],
        )
        self.assertNotIn('sql_server_templates', config)

    def test_override_also_applies_to_env_yaml(self):
        """
        取得元によらず上書きは適用される (仕様として固定する)。

        SQL_AGENT_CONFIG_YAML は MCP クライアントの env ブロック由来で、
        設定ファイルと同じ信頼境界にある。環境変数側だけコマンド実行を
        禁じても防御にならないため、経路で挙動を変えない。
        """
        override = self.write_temp_yaml(
            'sql_servers:\n  - name: from-secret\n'
        )
        os.environ['SQL_AGENT_CONFIG_YAML'] = (
            f'config_override_command: cat {override}\nsql_servers: []\n'
        )
        config = config_loader.load_config()
        self.assertEqual(config['sql_servers'], [{'name': 'from-secret'}])

    def test_failing_override_command_raises(self):
        self.write_config('config_override_command: /bin/false\n')
        with self.assertRaises(ValueError) as ctx:
            config_loader.load_config()
        self.assertIn('config_override_command', str(ctx.exception))

    def test_empty_override_command_output_raises(self):
        self.write_config('config_override_command: /bin/true\n')
        with self.assertRaises(ValueError) as ctx:
            config_loader.load_config()
        self.assertIn('出力が空', str(ctx.exception))

    def test_non_string_override_command_raises(self):
        self.write_config('config_override_command: 123\n')
        with self.assertRaises(ValueError):
            config_loader.load_config()

    def test_override_command_is_not_run_through_a_shell(self):
        """シェルを介さないので `;` 等はメタ文字として解釈されない。"""
        marker = os.path.join(self.tmpdir.name, 'pwned')
        self.write_config(
            f'config_override_command: /bin/echo x; touch {marker}\n'
        )
        with self.assertRaises(ValueError):
            # `/bin/echo x; touch <marker>` は argv として渡るため、
            # YAML として不正な出力になり ValueError になる。
            config_loader.load_config()
        self.assertFalse(os.path.exists(marker))


if __name__ == '__main__':
    unittest.main()

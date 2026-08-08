"""
SQL Agent の設定ローダー。

設定 (YAML) の解決順:
    1. SQL_AGENT_CONFIG_YAML 環境変数 (YAML 文字列リテラル。開発・テスト用)
    2. ~/.config/sql-agent-mcp-server/config.yaml

設定ファイルの場所は決め打ちで、プロジェクトディレクトリは見ない。
リポジトリの中に設定を置くと、チェックアウトごとに設定が分裂し、
パスワード入りのファイルを誤ってコミットする事故も起きやすいため。

読み込んだ設定に config_override_command があれば実行し、その stdout を
YAML として設定へ再帰マージする (取得した側が優先)。これは
「秘密は 1Password 等に置き、ローカルの config.yaml には平文で持たない」
ための仕組みで、queryfolio の同名キーと同じ方式。

    config_override_command: op read "op://development/sql-agent/config-yaml"

コマンドは実際に config が必要になった時に実行されるため、MCP サーバーの
起動時ではなくツール呼び出し時まで 1Password の認証を遅延できる。
コマンドは shlex.split で argv に分解し shell=False で実行する
(シェルを介さないのでパイプ/リダイレクト/変数展開は不可。単一コマンド前提)。

機密を含まないサーバーメタデータ (name / description / engine / host / port /
schema / log_file_path) のみをローカルにキャッシュする仕組みも提供する。
これは起動時の instructions / tool description / ログパス設定に使い、
パスワードや SSH 秘密鍵はキャッシュしない。

sql_server_templates (接続情報の雛形) にも対応する。同一 DB インスタンス上の
複数 schema を扱う際、接続情報の重複を避けるために、共通項目をテンプレートに
まとめ、sql_servers 側で `template: <名前>` を指定して継承させられる。
展開はロード直後 (load_config 内) に行うため、消費側は常に展開済みの
sql_servers を受け取る。
"""

import copy
import json
import os
import shlex
import subprocess
from typing import Any

import yaml

# 設定ファイルの置き場所 (決め打ち)。
CONFIG_DIR = '~/.config/sql-agent-mcp-server'
CONFIG_FILENAME = 'config.yaml'

# 設定を上書きする YAML を取得するコマンドのキー。
CONFIG_OVERRIDE_COMMAND_KEY = 'config_override_command'

# 廃止した環境変数。設定されたまま黙って無視すると、秘密が読まれずに
# 「サーバーが 1 件も無い」等の分かりにくい失敗になるため、明示的に案内する。
_REMOVED_GETTER_COMMAND_ENV = 'SQL_AGENT_CONFIG_YAML_GETTER_COMMAND'


def get_config_path() -> str:
    """
    設定ファイルのパス (~/.config/sql-agent-mcp-server/config.yaml)。

    HOME を見て毎回組み立てる (モジュール読み込み時に固定しない)。
    """
    return os.path.join(os.path.expanduser(CONFIG_DIR), CONFIG_FILENAME)


def _parse_yaml(yaml_text: str, source: str) -> dict[str, Any]:
    """YAML 文字列をパースして dict を返す。検証付き。"""
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise ValueError(f'{source} の YAML パースに失敗: {e}') from e

    if not data:
        raise ValueError(f'Config is empty: {source}')

    if not isinstance(data, dict):
        raise ValueError(
            f'Config must be a YAML mapping, got {type(data).__name__}:'
            f' {source}'
        )

    return data


def _run_override_command(command: str) -> str:
    """
    config_override_command を実行して stdout を返す。

    `op read "op://..."` を shlex.split で argv に分解し、shell=False で実行する。
    shell を介さないため、コマンド文字列に `;` `|` `$()` 等が混入しても
    シェルメタ文字として解釈されず、コマンドインジェクションの余地が無い。
    その代わりパイプ・リダイレクト・変数展開は使えない (単一コマンド前提)。
    """
    try:
        argv = shlex.split(command)
    except ValueError as e:
        # クォートが閉じていない等で分解に失敗
        raise ValueError(
            f'{CONFIG_OVERRIDE_COMMAND_KEY} の解析に失敗'
            f' (クォート不整合等): {command!r}: {e}'
        ) from e
    if not argv:
        raise ValueError(f'{CONFIG_OVERRIDE_COMMAND_KEY} が空です')

    try:
        # S603: shell=False なのでシェルメタ文字による注入は起きない
        # (上記 docstring 参照)。argv そのものは設定ファイル
        # (~/.config/sql-agent-mcp-server/config.yaml) 由来であり、
        # これは利用者自身が管理する信頼済みの入力という前提で扱う。
        result = subprocess.run(  # noqa: S603
            argv,
            shell=False,
            capture_output=True,
            text=True,
            # 認証待ち等で無限ハングするとツール呼び出しが固まるので timeout 必須。
            timeout=60,
            # returncode は下で自前に検査するので例外送出はしない。
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise ValueError(
            f'{CONFIG_OVERRIDE_COMMAND_KEY} がタイムアウト'
            f' ({e.timeout}秒): {command!r}'
            f' (1Password 等の認証待ちでハングしている可能性)'
        ) from e
    except Exception as e:
        raise ValueError(
            f'{CONFIG_OVERRIDE_COMMAND_KEY} の実行に失敗: {command!r}: {e}'
        ) from e

    if result.returncode != 0:
        raise ValueError(
            f'{CONFIG_OVERRIDE_COMMAND_KEY} が異常終了'
            f' (code={result.returncode}): {command!r}\n'
            f'stderr: {result.stderr.strip()}'
        )

    if not result.stdout.strip():
        raise ValueError(
            f'{CONFIG_OVERRIDE_COMMAND_KEY} の出力が空: {command!r}'
        )

    return result.stdout


def _merge_mapping(base: dict[str, Any], over: dict[str, Any]) -> None:
    """
    Over を base へ再帰的にマージする (over 側が優先)。base を破壊的に更新する。

    値がどちらもマッピングの時だけ中へ入って混ぜ、それ以外 (スカラー・リスト)
    は over で丸ごと置き換える。sql_servers のようなリストを要素単位で
    マージしないのは、どの要素が「同じ項目」かを決める安定した同一性が無いため
    (name 一致で混ぜると意図しない部分適用が起きる)。
    """
    for key, over_value in over.items():
        base_value = base.get(key)
        if isinstance(base_value, dict) and isinstance(over_value, dict):
            _merge_mapping(base_value, over_value)
        else:
            base[key] = over_value


def _apply_config_override(config: dict[str, Any]) -> dict[str, Any]:
    """
    config_override_command があれば実行し、取得した YAML を再帰マージする。

    取得した YAML の中に config_override_command があっても再帰取得はしない
    (適用済みであることを示すためキー自体を落とす)。
    """
    command = config.get(CONFIG_OVERRIDE_COMMAND_KEY)
    if command is None:
        return config

    if not isinstance(command, str) or not command.strip():
        raise ValueError(
            f'{CONFIG_OVERRIDE_COMMAND_KEY} は空でない文字列である必要があります'
        )

    yaml_text = _run_override_command(command)
    overrides = _parse_yaml(
        yaml_text,
        f'{CONFIG_OVERRIDE_COMMAND_KEY} ({command})',
    )

    # 呼び出し元が渡した dict を書き換えないようコピーしてからマージする。
    merged = copy.deepcopy(config)
    _merge_mapping(merged, overrides)
    merged.pop(CONFIG_OVERRIDE_COMMAND_KEY, None)
    return merged


def _expand_server_templates(config: dict[str, Any]) -> dict[str, Any]:
    """
    sql_server_templates を展開して sql_servers に共通項目を継承させる。

    sql_server_templates は接続情報の雛形 (engine / host / port / user /
    password / ssh_tunnel 等) をまとめたもの。sql_servers の各エントリで
    `template: <テンプレート名>` を指定すると、そのテンプレートの項目を
    土台にし、サーバー側で指定した同名キーで上書きする (シャローマージ)。
    ネストした値 (例: ssh_tunnel) はサーバー側で指定すると丸ごと置き換わる。

    テンプレートの name はルックアップ用のキーなので継承させない
    (サーバーは自分自身の name を持つ)。sql_server_templates が無ければ
    config はそのまま返す (後方互換)。展開後は sql_server_templates を除去する。

    エラーメッセージには要素そのもの (repr) を載せない。テンプレート/サーバー
    dict には password 等の機密が含まれるうえ、この関数の ValueError は
    mcp_server 側で str(e) として MCP クライアントに返るため、機密が別トラスト
    境界へ漏れないよう位置 (index) と事実のみを示す。
    """
    templates_list = config.get('sql_server_templates')
    servers_list = config.get('sql_servers', [])
    if not templates_list:
        # テンプレート未定義 (キー無し or 空リスト) なのに template を参照する
        # サーバーがあると、展開されず template キーが残ったまま接続時に
        # 分かりにくい KeyError になる。ここで明示的に弾く (後方互換のため、
        # そもそも template 参照が無ければ従来どおり config を素通しする)。
        stray = [
            s.get('name')
            for s in servers_list
            if isinstance(s, dict) and s.get('template')
        ]
        if stray:
            raise ValueError(
                'sql_servers が template を参照していますが'
                f' sql_server_templates が定義されていません: {stray}'
            )
        return config

    if not isinstance(templates_list, list):
        raise ValueError('sql_server_templates はリストである必要があります')

    templates: dict[str, dict[str, Any]] = {}
    for i, template in enumerate(templates_list):
        if not isinstance(template, dict) or 'name' not in template:
            raise ValueError(
                f'sql_server_templates の {i} 番目の要素は'
                ' name を持つマッピングである必要があります'
            )
        name = template['name']
        if name in templates:
            raise ValueError(
                f'sql_server_templates に重複した name があります: {name!r}'
            )
        templates[name] = template

    expanded_servers = []
    for i, server in enumerate(servers_list):
        if not isinstance(server, dict):
            raise ValueError(
                f'sql_servers の {i} 番目の要素は'
                ' マッピングである必要があります'
            )
        template_name = server.get('template')
        if template_name is None:
            expanded_servers.append(server)
            continue
        if template_name not in templates:
            raise ValueError(
                'sql_servers が参照するテンプレートが見つかりません:'
                f' template={template_name!r}'
                f' (定義済み: {sorted(templates)})'
            )
        merged = {
            k: v for k, v in templates[template_name].items() if k != 'name'
        }
        for k, v in server.items():
            if k == 'template':
                continue
            merged[k] = v
        expanded_servers.append(merged)

    expanded = {k: v for k, v in config.items() if k != 'sql_server_templates'}
    expanded['sql_servers'] = expanded_servers
    return expanded


def _reject_removed_env() -> None:
    """
    廃止した SQL_AGENT_CONFIG_YAML_GETTER_COMMAND が残っていたら移行を促す。

    黙って無視すると、秘密が読まれないまま設定ファイル側だけが使われ、
    「サーバーが 1 件も見つからない」といった原因の分かりにくい失敗になる。
    """
    if os.environ.get(_REMOVED_GETTER_COMMAND_ENV):
        raise ValueError(
            f'{_REMOVED_GETTER_COMMAND_ENV} は廃止されました。'
            f' 同じことは {get_config_path()} に'
            f' {CONFIG_OVERRIDE_COMMAND_KEY} を書くことで行えます'
            f' (例: {CONFIG_OVERRIDE_COMMAND_KEY}:'
            ' op read "op://development/sql-agent/config-yaml")。'
            f' 移行後は {_REMOVED_GETTER_COMMAND_ENV} を環境変数から外してください'
        )


def load_config() -> dict[str, Any]:
    """
    設定を読み込んで dict で返す。

    解決順はモジュール docstring を参照。config_override_command が設定されて
    いる場合はここで実行されるため、この関数の呼び出しが 1Password 等の認証を
    トリガーしうる点に注意 (= 起動時ではなく実際に config が要る時に呼ぶ)。

    config_override_command は SQL_AGENT_CONFIG_YAML 経由で読んだ設定にも
    適用する (取得元によらず「読み込んだ設定に対する上書き」として扱う)。
    どちらの経路もプロセスの起動設定と同じ信頼境界にあるため、
    環境変数側だけコマンド実行を禁じても防御にはならない。
    """
    config_yaml_env = os.environ.get('SQL_AGENT_CONFIG_YAML')
    if config_yaml_env:
        data = _parse_yaml(config_yaml_env, 'SQL_AGENT_CONFIG_YAML 環境変数')
    else:
        # 廃止した getter 環境変数の検出は、設定ファイルを使う経路に限る。
        # SQL_AGENT_CONFIG_YAML で設定が渡っている場合、旧実装でも getter は
        # 参照されなかったので、残っていても実害が無い。ここで一律に落とすと
        # 「使っていない環境変数が残っているだけ」で動かなくなってしまう。
        _reject_removed_env()

        config_path = get_config_path()
        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f'Config file not found: {config_path}'
                ' (config.example.yaml を参考に作成してください)'
            )
        with open(config_path, encoding='utf-8') as f:
            data = _parse_yaml(f.read(), config_path)

    # テンプレート展開より先に上書きを適用する。上書き側から
    # sql_server_templates / sql_servers を丸ごと差し替えられるようにするため。
    data = _apply_config_override(data)
    return _expand_server_templates(data)


# -- 機密を含まないサーバーメタデータのローカルキャッシュ --

# キャッシュに残してよいサーバー項目 (パスワード / SSH 秘密鍵は含めない)。
_CACHEABLE_SERVER_KEYS = (
    'name',
    'description',
    'engine',
    'host',
    'port',
    'schema',
)

DEFAULT_CACHE_PATH = os.path.expanduser(
    '~/.cache/sql-agent-mcp-server/server-metadata.json'
)


def get_cache_path() -> str:
    """メタデータキャッシュのパス。環境変数で上書き可能。"""
    return os.environ.get('SQL_AGENT_CONFIG_CACHE_PATH', DEFAULT_CACHE_PATH)


def _sanitize_for_cache(config: dict[str, Any]) -> dict[str, Any]:
    """Config から機密を除いた、起動時に必要なメタデータだけを抽出する。"""
    servers = []
    for server in config.get('sql_servers', []):
        servers.append(
            {k: server[k] for k in _CACHEABLE_SERVER_KEYS if k in server}
        )
    cached: dict[str, Any] = {'sql_servers': servers}
    if config.get('log_file_path'):
        cached['log_file_path'] = config['log_file_path']
    return cached


def save_metadata_cache(config: dict[str, Any]) -> None:
    """
    機密を除いたサーバーメタデータをローカルキャッシュに保存する。
    保存失敗は致命的ではないので握りつぶす (best-effort)。
    """
    cache_path = get_cache_path()
    try:
        cache_dir = os.path.dirname(cache_path)
        os.makedirs(cache_dir, exist_ok=True)
        # ディレクトリも owner のみ (0o700) にし、path 存在の列挙を防ぐ。
        # makedirs の mode は umask の影響を受けるので chmod で確実に締める。
        os.chmod(cache_dir, 0o700)
        # host / port / schema 等が他ユーザーに読まれないよう owner のみ (0o600)。
        fd = os.open(cache_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(_sanitize_for_cache(config), f, ensure_ascii=False)
    except Exception:
        # キャッシュは best-effort。失敗してもアプリは動く。
        pass


def load_metadata_cache() -> dict[str, Any] | None:
    """
    保存済みメタデータキャッシュを読み込む。無い / 壊れている場合は None。
    """
    cache_path = get_cache_path()
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data

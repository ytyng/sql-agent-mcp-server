"""
SQL Agent の設定ローダー。

設定 (YAML) の解決順:
    1. SQL_AGENT_CONFIG_YAML 環境変数 (YAML 文字列リテラル)
    2. SQL_AGENT_CONFIG_YAML_GETTER_COMMAND 環境変数 (実行して stdout を YAML として使う)
    3. 同ディレクトリの config.yaml ファイル

2 番の getter command は「秘密の取得コマンド (例: `op read op://...`)」を
環境変数に置いておき、実際に config が必要になった時だけ実行することを想定する。
これにより MCP サーバー起動時ではなく、ツール呼び出し時まで 1Password 等の
認証を遅延できる。コマンドは shlex.split で argv に分解し shell=False で実行する
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
import json
import os
import shlex
import subprocess
from typing import Any

import yaml


def _parse_yaml(yaml_text: str, source: str) -> dict[str, Any]:
    """YAML 文字列をパースして dict を返す。検証付き。"""
    try:
        data = yaml.safe_load(yaml_text)
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


def _run_getter_command(command: str) -> str:
    """
    getter command を実行して stdout を返す。

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
            f"SQL_AGENT_CONFIG_YAML_GETTER_COMMAND の解析に失敗"
            f" (クォート不整合等): {command!r}: {e}"
        ) from e
    if not argv:
        raise ValueError(
            "SQL_AGENT_CONFIG_YAML_GETTER_COMMAND が空です"
        )

    try:
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            # 認証待ち等で無限ハングするとツール呼び出しが固まるので timeout 必須。
            timeout=60,
        )
    except subprocess.TimeoutExpired as e:
        raise ValueError(
            f"SQL_AGENT_CONFIG_YAML_GETTER_COMMAND がタイムアウト"
            f" ({e.timeout}秒): {command!r}"
            f" (1Password 等の認証待ちでハングしている可能性)"
        ) from e
    except Exception as e:
        raise ValueError(
            f"SQL_AGENT_CONFIG_YAML_GETTER_COMMAND の実行に失敗:"
            f" {command!r}: {e}"
        ) from e

    if result.returncode != 0:
        raise ValueError(
            f"SQL_AGENT_CONFIG_YAML_GETTER_COMMAND が異常終了"
            f" (code={result.returncode}): {command!r}\n"
            f"stderr: {result.stderr.strip()}"
        )

    if not result.stdout.strip():
        raise ValueError(
            f"SQL_AGENT_CONFIG_YAML_GETTER_COMMAND の出力が空: {command!r}"
        )

    return result.stdout


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
                "sql_servers が template を参照していますが"
                f" sql_server_templates が定義されていません: {stray}"
            )
        return config

    if not isinstance(templates_list, list):
        raise ValueError(
            "sql_server_templates はリストである必要があります"
        )

    templates: dict[str, dict[str, Any]] = {}
    for i, template in enumerate(templates_list):
        if not isinstance(template, dict) or 'name' not in template:
            raise ValueError(
                f"sql_server_templates の {i} 番目の要素は"
                " name を持つマッピングである必要があります"
            )
        name = template['name']
        if name in templates:
            raise ValueError(
                f"sql_server_templates に重複した name があります: {name!r}"
            )
        templates[name] = template

    expanded_servers = []
    for i, server in enumerate(servers_list):
        if not isinstance(server, dict):
            raise ValueError(
                f"sql_servers の {i} 番目の要素は"
                " マッピングである必要があります"
            )
        template_name = server.get('template')
        if template_name is None:
            expanded_servers.append(server)
            continue
        if template_name not in templates:
            raise ValueError(
                "sql_servers が参照するテンプレートが見つかりません:"
                f" template={template_name!r}"
                f" (定義済み: {sorted(templates)})"
            )
        merged = {
            k: v for k, v in templates[template_name].items() if k != 'name'
        }
        for k, v in server.items():
            if k == 'template':
                continue
            merged[k] = v
        expanded_servers.append(merged)

    expanded = {
        k: v for k, v in config.items() if k != 'sql_server_templates'
    }
    expanded['sql_servers'] = expanded_servers
    return expanded


def load_config(config_filename: str = 'config.yaml') -> dict[str, Any]:
    """
    設定を読み込んで dict で返す。

    解決順はモジュール docstring を参照。getter command が設定されている
    場合はここで実行されるため、この関数の呼び出しが 1Password 等の認証を
    トリガーしうる点に注意 (= 起動時ではなく実際に config が要る時に呼ぶ)。
    """
    config_yaml_env = os.environ.get('SQL_AGENT_CONFIG_YAML')
    if config_yaml_env:
        data = _parse_yaml(config_yaml_env, 'SQL_AGENT_CONFIG_YAML 環境変数')
    else:
        getter_command = os.environ.get(
            'SQL_AGENT_CONFIG_YAML_GETTER_COMMAND'
        )
        if getter_command:
            yaml_text = _run_getter_command(getter_command)
            data = _parse_yaml(
                yaml_text,
                f'SQL_AGENT_CONFIG_YAML_GETTER_COMMAND ({getter_command})',
            )
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, config_filename)
            if not os.path.exists(config_path):
                raise FileNotFoundError(
                    f"Config file not found: {config_path}"
                )
            with open(config_path, 'r', encoding='utf-8') as f:
                data = _parse_yaml(f.read(), config_path)

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
    """config から機密を除いた、起動時に必要なメタデータだけを抽出する。"""
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
        fd = os.open(
            cache_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
        )
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
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data

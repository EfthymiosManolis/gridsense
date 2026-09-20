"""Prepare persistent runtime credentials before the database services start."""
import json
import io
import os
from pathlib import Path
import secrets
import shlex

from dotenv import dotenv_values

KEYS = ('NEO4J_USER', 'NEO4J_PASSWORD', 'POSTGRES_USER',
        'POSTGRES_PASSWORD', 'POSTGRES_DB')


def initialize(workspace: Path, config: Path):
    config.mkdir(parents=True, exist_ok=True)
    env_path = workspace / '.env'
    saved_path = config / 'credentials.json'
    saved = json.loads(saved_path.read_text()) if saved_path.exists() else None
    if not env_path.exists():
        if saved:
            content = (config / 'saved.env').read_text()
        else:
            template = (workspace / '.env.example').read_text()
            values = dict(dotenv_values(stream=io.StringIO(template), interpolate=False))
            values['NEO4J_PASSWORD'] = secrets.token_hex(24)
            values['POSTGRES_PASSWORD'] = secrets.token_hex(24)
            content = '\n'.join(f'{key}={json.dumps(value, ensure_ascii=False)}'
                                for key, value in values.items() if value is not None) + '\n'
        # Exclusive creation protects an existing user configuration.
        fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        if os.geteuid() == 0:
            owner = workspace.stat()
            os.chown(env_path, owner.st_uid, owner.st_gid)
    values = dotenv_values(env_path, interpolate=False)
    credentials = {key: values.get(key) for key in KEYS}
    if any(not value or '\n' in value or '\r' in value for value in credentials.values()):
        raise RuntimeError('The .env file needs non-empty, single-line values for: ' + ', '.join(KEYS))
    if credentials['NEO4J_USER'] != 'neo4j':
        raise RuntimeError('The Neo4j image requires NEO4J_USER=neo4j for initialization')
    if saved and saved != credentials:
        raise RuntimeError('Credentials changed since initialization; refusing automatic password rotation. Restore the existing .env credentials or migrate database credentials explicitly.')
    backup_path = config / 'saved.env'
    backup_path.write_bytes(env_path.read_bytes())
    backup_path.chmod(0o600)
    saved_path.write_text(json.dumps(credentials))
    saved_path.chmod(0o600)
    shell_path = config / 'runtime.sh'
    shell_path.write_text('\n'.join(f'export {key}={shlex.quote(value)}'
                                    for key, value in credentials.items()) + '\n')
    shell_path.chmod(0o600)
    print('Runtime configuration ready; existing .env credentials preserved.')


if __name__ == '__main__':
    initialize(Path('/workspace'), Path('/config'))

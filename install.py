#!/usr/bin/env python3
"""Install or update a Git-managed standalone skill; Python 3.9+, Git."""
import argparse
from pathlib import Path
import subprocess
import sys

REPOSITORY = 'https://github.com/Cui-Owen/ozbargain-radar.git'
PATHS = {'codex': '.agents/skills', 'claude': '.claude/skills',
         'antigravity': '.gemini/config/skills'}


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()


def install(repo, dest, ref):
    if dest.exists():
        if not (dest / '.git').is_dir():
            raise ValueError(f'Existing unmanaged directory: {dest}. Use --dest with a new path.')
        if Path(git('rev-parse', '--show-toplevel', cwd=dest)).resolve() != dest.resolve():
            raise ValueError('Destination is not the repository root.')
        if git('remote', 'get-url', 'origin', cwd=dest) != repo:
            raise ValueError('Destination belongs to another repository.')
        if git('status', '--porcelain', '--untracked-files=all', cwd=dest):
            raise ValueError('Local changes found. Commit or move them before updating.')
        if not (dest / 'SKILL.md').is_file():
            raise ValueError('Destination has no SKILL.md.')
        git('fetch', '--tags', 'origin', cwd=dest)
        # main is the moving update channel; tags are immutable version selections.
        target = 'origin/main' if ref == 'main' else f'refs/tags/{ref}'
        git('rev-parse', '--verify', target + '^{commit}', cwd=dest)
        if ref == 'main':
            git('checkout', 'main', cwd=dest)
            git('merge', '--ff-only', target, cwd=dest)
        else:
            git('checkout', '--detach', target, cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        git('clone', '--branch', ref, '--', repo, str(dest))
    print(f'Installed: {dest}')
    print(f'Version: {(dest / "VERSION").read_text().strip()} ({git("rev-parse", "--short", "HEAD", cwd=dest)})')
    print('Use: $ozbargain-radar 帮我找今天值得看的澳洲优惠')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=PATHS, default='codex')
    parser.add_argument('--dest', type=Path, help='Custom skill directory, including ozbargain-radar')
    parser.add_argument('--ref', default='main', help='main (updates) or a release tag such as v1.0.0')
    parser.add_argument('--repo', default=REPOSITORY, help='Repository URL; defaults to the official repo')
    args = parser.parse_args()
    dest = (args.dest or Path.home() / PATHS[args.agent] / 'ozbargain-radar').expanduser().absolute()
    try:
        install(args.repo, dest, args.ref)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'Installation stopped: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

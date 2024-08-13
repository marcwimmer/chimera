import subprocess
import tempfile
import time
from datetime import datetime
import shutil
import uuid
import os
from pathlib import Path
import click
import sys
from curses import wrapper
from contextlib import contextmanager


def is_forced():
    return os.getenv("GIMERA_FORCE", "0") == "1"


def yieldlist(method):
    def wrapper(*args, **kwargs):
        result = list(method(*args, **kwargs))
        return result

    return wrapper


def X(*params, output=False, cwd=None, allow_error=False, env=None):
    """
    Catching output error and stderr
    try:
        stdout = X(output=True, .....)
    except subprocess.CalledProcessError as ex:
        stderr = ex.stderr
    """
    params = list(filter(lambda x: x is not None, list(params)))
    env2 = {k: v for k, v in os.environ.items()}
    env2.update(env or {})
    if output:
        ret = subprocess.run(
            params,
            encoding="utf-8",
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env2,
        )
        if ret.returncode:
            if allow_error:
                return ""
            raise subprocess.CalledProcessError(
                returncode=ret.returncode,
                cmd=params,
                output=ret.stdout,
                stderr=ret.stderr,
            )
        return ret.stdout.rstrip()
    try:
        return subprocess.check_call(params, cwd=cwd, env=env2)
    except subprocess.CalledProcessError:
        if allow_error:
            return None
        raise


def _raise_error(msg):
    click.secho(msg, fg="red")
    if os.getenv("GIMERA_EXCEPTION_THAN_SYSEXIT") == "1":
        raise Exception(msg)
    else:
        sys.exit(-1)


def _strip_paths(paths):
    for x in paths:
        yield str(Path(x))


def safe_relative_to(path, path2):
    try:
        res = Path(path).relative_to(path2)
    except ValueError:
        return False
    else:
        return res


def is_empty_dir(path):
    return not any(Path(path).rglob("*"))


@contextmanager
def prepare_dir(path):
    tmp_path = path.parent / f"{path.name}.{uuid.uuid4()}"
    assert path.parent.exists()
    assert len(path.parts) > 1
    tmp_path.mkdir(parents=True)
    try:
        yield tmp_path
        if path.exists():
            rmtree(path)
        shutil.move(tmp_path, path)
    except Exception as ex:
        raise
    finally:
        if tmp_path.exists():
            try:
                rmtree(tmp_path)
            except Exception:
                pass


def file_age(path):
    try:
        mtime = datetime.fromtimestamp(os.stat(path).st_mtime)
    except:
        return 0
    return (datetime.now() - mtime).total_seconds()


@contextmanager
def wait_git_lock(path):
    MAX_TIMEOUT = 3600
    from .filelock import FileLock

    gimera_lock = path / ".git" / "gimera.lock"
    if not gimera_lock.parent.exists():
        gimera_lock = None
    index_lock = path / ".git" / "index.lock"

    def lock_exists():
        if index_lock.exists():
            return True
        if gimera_lock and gimera_lock.exists():
            return True
        return False

    if not index_lock.exists():
        yield
    else:
        while lock_exists():
            if file_age(index_lock) > MAX_TIMEOUT:
                index_lock.unlink()
                continue

            if gimera_lock and file_age(gimera_lock) > MAX_TIMEOUT:
                gimera_lock.unlink()
                continue

            time.sleep(0.5)

        if gimera_lock:
            with FileLock(gimera_lock, timeout=MAX_TIMEOUT):
                yield
        else:
            yield


def rmtree(path):
    try:
        shutil.rmtree(path)
    except:
        click.secho(f"Failed to remove {path}", fg="red")
        sys.exit(-1)


@contextmanager
def remember_cwd(cwd):
    old = os.getcwd()
    if cwd is not None:
        os.chdir(cwd)
    try:
        yield Path(cwd)
    finally:
        os.chdir(old)


def confirm(msg, raise_exception=True):
    if os.getenv("GIMERA_NON_INTERACTIVE") == "1":
        return True
    click.secho(msg, fg="yellow")
    res = click.confirm("Continue?", default=True)
    if not res and raise_exception:
        _raise_error("Aborted by user")
    return res


def retry(func, attempts=3, sleep=5):
    for i in range(attempts):
        try:
            func()
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(sleep)
        else:
            break


def try_rm_tree(path):
    if not path.exists():
        return

    def _action():
        shutil.rmtree(path)

    retry(func=_action)


@contextmanager
def temppath(mkdir=True):
    path = Path(tempfile.mktemp(suffix="."))
    try:
        if mkdir:
            path.mkdir()
        yield path
    finally:
        try_rm_tree(path)


def path1inpath2(path1, path2):
    try:
        path1.relative_to(path2)
        return True
    except:
        return False


def rsync(dir1, dir2, exclude=None, delete_after=True):
    cmd = [
        "rsync",
        "-ar",
        "--info=progress2",
    ]
    if delete_after:
        cmd += ["--delete-after"]
    for X in exclude or []:
        cmd += [f"--exclude={X}"]
    cmd.append(str(dir1) + "/")
    cmd.append(str(dir2) + "/")
    subprocess.check_call(cmd)


def get_url_type(url):
    if url.startswith("http"):
        return "http"
    if url.startswith("git@"):
        return "git"
    if url.startswith("/") or url.startswith("file://"):
        return "file"
    raise NotImplementedError(url)


def reformat_url(url, ttype):
    assert ttype in ["http", "git"]

    current = get_url_type(url)
    if ttype == "http" and current == "git":
        if url.startswith("git@"):
            url = url[4:]
        if ":" in url:
            # colon in password possible
            url = "/".join(url.split(":", 1))
        url = "https://" + url
        return url
    elif ttype == "git" and current == "http":
        url = url.split("://", 1)[1]
        url = f"git@{url}"
        url = ":".join(url.split("/", 1))
        return url
    else:
        raise NotImplementedError(f"{url} + {ttype}")


def verbose(txt):
    if not os.getenv("GIMERA_VERBOSE") == "1":
        return
    click.secho(txt, fg="yellow")


def get_nearest_repo(end, start):
    start = Path(start)
    p = start
    while p != Path(end):
        git = p / ".git"
        if git.exists():
            return git.parent
        p = p.parent
    return end


def _make_sure_hidden_gimera_dir(root_dir):
    path = Path(root_dir) / ".gitignore"
    if not path.exists():
        path.write_text(".gimera\n")
    else:
        content = path.read_text().splitlines()
        if not [x for x in content if x == ".gimera"]:
            content.append(".gimera")
            path.write_text("\n".join(content))
    return root_dir / ".gimera"


@yieldlist
def _get_remotes(repo_yml):
    from .repo import Remote

    config = repo_yml.remotes
    if not config:
        return

    for name, url in dict(config).items():
        yield Remote(None, name, url)


def _get_main_repo():
    from .repo import Repo

    path = Path(os.getcwd())
    while True:
        #  TODO think about that
        # if (path / ".git").exists() and (path / ".git").is_dir():
        if (path / ".git").exists():
            break
        path = path.parent
        if len(path.parts) == 1:
            path = Path(os.getcwd())
            break

    return Repo(path)


def _get_missing_repos(config):
    for repo in config.repos:
        if not repo.enabled:
            continue
        if not repo.path.exists():
            yield repo


def get_parent_gimera(end, start):
    p = start.parent
    while p != end:
        if (p / "gimera.yml").exists():
            return p
        p = p.parent
    return end
    raise Exception(f"No parent gimera found for {start}")


def get_effective_state(root_dir, path):
    from .repo import Repo

    path = Path(path)
    root_dir = Path(root_dir)

    # closest_gimera = local_gimera
    from .config import Config

    closest_gimera = get_parent_gimera(root_dir, path / "dummy")
    config = Config(force_gimera_file=closest_gimera / 'gimera.yml')
    for repo in config.repos:
        if repo.path == safe_relative_to(path, closest_gimera):
            path_is_provided_by_gimera_but_itself_no_gimera = True
            break
    else:
        path_is_provided_by_gimera_but_itself_no_gimera = False


    parent_gimera = get_parent_gimera(root_dir, closest_gimera)
    if parent_gimera == root_dir:
        parent_repo = root_dir
    else:
        if path_is_provided_by_gimera_but_itself_no_gimera:
            parent_repo = get_nearest_repo(root_dir, closest_gimera)
        else:
            parent_repo = get_nearest_repo(root_dir, parent_gimera)

    rel_path = safe_relative_to(path, parent_repo)
    is_submodule = Repo(parent_repo).is_path_a_submodule(rel_path)
    return {
        "is_submodule": is_submodule,
        "relpath": rel_path,
        "closest_gimera": closest_gimera,
        "parent_gimera": parent_gimera,
        "parent_repo": parent_repo,
    }

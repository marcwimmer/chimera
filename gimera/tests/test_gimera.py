#!/usr/bin/env python3
import uuid
import yaml
from contextlib import contextmanager
from ..repo import Repo
import os
import subprocess
import click
import inspect
import os
from pathlib import Path
from .tools import gimera_apply
from . import temppath
from .tools import _make_remote_repo
from .tools import clone_and_commit
from .tools import gimera_commit

from ..consts import gitcmd as git

current_dir = Path(
    os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
)


def test_basicbehaviour(temppath):
    """
    * put same repo integrated and submodule into main repo
    * add file2.txt on remote
    * check after apply that file exists in both
    * make a patch in integrated version
    """
    workspace = temppath / "workspace"

    remote_main_repo = _make_remote_repo(temppath / "mainrepo")
    remote_sub_repo = _make_remote_repo(temppath / "sub1")

    subprocess.check_output(
        git + ["clone", "file://" + str(remote_main_repo), workspace.name],
        cwd=workspace.parent,
    )
    os.environ["GIMERA_NON_INTERACTIVE"] = "1"

    # region gimera config
    repos = {
        "repos": [
            {
                "url": f"file://{remote_sub_repo}",
                "branch": "branch1",
                "path": "submodules/sub1",
                "patches": [],
                "type": "submodule",
            },
            {
                "url": f"file://{remote_sub_repo}",
                "branch": "branch1",
                "path": "integrated/sub1",
                "patches": ["integrated/sub1_patches"],
                "type": "integrated",
            },
        ]
    }
    # endregion

    (workspace / "gimera.yml").write_text(yaml.dump(repos))
    (workspace / "main.txt").write_text("main repo")
    subprocess.check_call(git + ["add", "main.txt"], cwd=workspace)
    subprocess.check_call(git + ["add", "gimera.yml"], cwd=workspace)
    subprocess.check_call(git + ["commit", "-am", "on main"], cwd=workspace)
    subprocess.check_call(git + ["push"], cwd=workspace)
    (workspace / repos["repos"][1]["patches"][0]).mkdir(exist_ok=True, parents=True)
    os.chdir(workspace)
    os.environ["GIMERA_NON_THREADED"] = "1"
    gimera_apply([], None)
    subprocess.check_call(git + ["add", "gimera.yml"], cwd=workspace)
    assert not Repo(workspace).staged_files
    # subprocess.check_call(git + ["commit", "-am", "updated gimera"], cwd=workspace)

    click.secho(
        "Now we have a repo with two subrepos; now we update the subrepos and pull"
    )
    with clone_and_commit(remote_sub_repo, "branch1") as repopath:
        (repopath / "file2.txt").write_text("This is a new function")
        subprocess.check_call(git + ["add", "file2.txt"], cwd=repopath)
        subprocess.check_call(git + ["commit", "-am", "file2 added"], cwd=repopath)

    os.chdir(workspace)
    os.environ["GIMERA_NON_INTERACTIVE"] = "1"
    gimera_apply([], update=True)

    click.secho(str(workspace), fg="green")
    assert (workspace / "submodules" / "sub1" / "file2.txt").exists()
    assert (workspace / "integrated" / "sub1" / "file2.txt").exists()

    # check dirty - disabled because the command is_path_dirty is not cool
    (workspace / "integrated" / "sub1" / "file2.txt").write_text("a change!")
    (workspace / "integrated" / "sub1" / "file3.txt").write_text("a new file!")
    (workspace / "file4.txt").write_text(
        "a new file!"
    )  # should not stop the process but should not be committed

    # annotation: it would be bad if file3.txt would be gone
    # and also the change of file2.txt

    # now lets make a patch for new integrated/sub1/file3.txt and changed integrated/sub1/file2.txt
    os.chdir(workspace)
    os.environ["GIMERA_EXCEPTION_THAN_SYSEXIT"] = "1"
    (workspace / repos["repos"][1]["patches"][0]).mkdir(exist_ok=True, parents=True)
    gimera_apply([], update=True)
    assert (workspace / "integrated" / "sub1" / "file3.txt").exists()

    # now lets make an update and see if patches are applied
    with clone_and_commit(remote_sub_repo, "branch1") as repopath:
        (repopath / "file5.txt").write_text("This is a new function")
        subprocess.check_call(git + ["add", "file5.txt"], cwd=repopath)
        subprocess.check_call(git + ["commit", "-am", "file5 added"], cwd=repopath)

    # should apply patches now
    os.chdir(workspace)
    gimera_apply([], update=False)

    # check if test is applied
    assert "file4.txt" in [x.name for x in Repo(workspace).untracked_files]
    assert (workspace / "integrated" / "sub1" / "file3.txt").exists()
    assert (
        "a change"
        in (
            (workspace / "integrated" / "sub1" / "file3.txt").parent / "file2.txt"
        ).read_text()
    )

    # now lets edit that patch again
    Repo(workspace).simple_commit_all()
    patchfile = list((workspace / "integrated" / "sub1_patches").glob("*"))[
        0
    ].relative_to(workspace)
    os.chdir(workspace)
    from ..gimera import _edit_patch as edit_patch

    edit_patch([patchfile])
    dirty_files = Repo(workspace).all_dirty_files
    assert (workspace / str(patchfile)) not in dirty_files
    assert (workspace / "integrated/sub1/file3.txt") in dirty_files
    assert (workspace / "integrated/sub1/file2.txt") in dirty_files


def test_submodule_tree_dirty_files(temppath):
    """
    * put same repo integrated and submodule into main repo
    * add file2.txt on remote
    * check after apply that file exists in both
    * make a patch in integrated version
    """
    workspace = temppath / "workspace_tree_dirty_files"
    workspace.mkdir()
    workspace_main = workspace / "main_working"

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_sub = _make_remote_repo(temppath / "sub1")
    repo_subsub = _make_remote_repo(temppath / "subsub1")
    repo_2 = _make_remote_repo(temppath / "repo2")

    with clone_and_commit(repo_2, "main") as repopath:
        (repopath / "file1.txt").write_text("This is a new function")
        subprocess.check_call(git + ["add", "file1.txt"], cwd=repopath)
        subprocess.check_call(git + ["commit", "-am", "file1 added"], cwd=repopath)

    with clone_and_commit(repo_subsub, "main") as repopath:
        (repopath / "file1.txt").write_text("This is a new function")
        subprocess.check_call(git + ["add", "file1.txt"], cwd=repopath)
        subprocess.check_call(git + ["commit", "-am", "file1 added"], cwd=repopath)

    with clone_and_commit(repo_sub, "main") as repopath:
        (repopath / "file1.txt").write_text("This is a new function")
        subprocess.check_call(git + ["add", "file1.txt"], cwd=repopath)
        subprocess.check_call(
            git + ["submodule", "add", f"file://{repo_subsub}", "subsub"], cwd=repopath
        )
        subprocess.check_call(git + ["commit", "-am", "file1 added"], cwd=repopath)

    with clone_and_commit(repo_main, "main") as repopath:
        (repopath / "file1.txt").write_text("This is a new function")
        subprocess.check_call(git + ["add", "file1.txt"], cwd=repopath)
        subprocess.check_call(
            git + ["submodule", "add", f"file://{repo_sub}", "sub"], cwd=repopath
        )
        subprocess.check_call(git + ["commit", "-am", "file1 added"], cwd=repopath)

    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace_main],
        cwd=workspace,
    )
    subprocess.check_call(
        git + ["submodule", "update", "--init", "--recursive"], cwd=workspace_main
    )
    assert (workspace_main / "sub" / "subsub" / "file1.txt").exists()

    from ..gitcommands import GitCommands

    assert not GitCommands(workspace_main / "sub" / "subsub").dirty_existing_files
    assert not GitCommands(workspace_main / "sub" / "subsub").untracked_files
    assert not GitCommands(workspace_main / "sub" / "subsub").all_dirty_files
    (workspace_main / "sub" / "subsub" / "newfile.txt").write_text("new")
    assert not GitCommands(workspace_main / "sub" / "subsub").dirty_existing_files
    assert GitCommands(workspace_main / "sub" / "subsub").untracked_files
    assert GitCommands(workspace_main / "sub" / "subsub").all_dirty_files
    assert GitCommands(workspace_main / "sub").dirty_existing_files
    assert not GitCommands(workspace_main / "sub").untracked_files
    assert GitCommands(workspace_main / "sub").all_dirty_files
    assert GitCommands(workspace_main).dirty_existing_files
    assert not GitCommands(workspace_main).untracked_files
    assert GitCommands(workspace_main).all_dirty_files
    (workspace_main / "sub" / "subsub" / "newfile.txt").unlink()
    assert not GitCommands(workspace_main / "sub" / "subsub").dirty_existing_files
    assert not GitCommands(workspace_main / "sub" / "subsub").untracked_files
    assert not GitCommands(workspace_main / "sub" / "subsub").all_dirty_files
    (workspace_main / "sub" / "newfile.txt").write_text("new")
    assert not GitCommands(workspace_main / "sub" / "subsub").dirty_existing_files
    assert not GitCommands(workspace_main / "sub" / "subsub").untracked_files
    assert not GitCommands(workspace_main / "sub" / "subsub").all_dirty_files
    assert GitCommands(workspace_main).dirty_existing_files
    assert not GitCommands(workspace_main).untracked_files
    assert GitCommands(workspace_main).all_dirty_files
    (workspace_main / "sub" / "newfile.txt").unlink()
    assert not GitCommands(workspace_main / "sub" / "subsub").dirty_existing_files
    assert not GitCommands(workspace_main / "sub" / "subsub").untracked_files
    assert not GitCommands(workspace_main / "sub" / "subsub").all_dirty_files
    (workspace_main / "newfile.txt").write_text("new")
    assert not GitCommands(workspace_main / "sub" / "subsub").dirty_existing_files
    assert not GitCommands(workspace_main / "sub" / "subsub").untracked_files
    assert not GitCommands(workspace_main / "sub" / "subsub").all_dirty_files
    (workspace_main / "newfile.txt").unlink()
    assert not GitCommands(workspace_main / "sub" / "subsub").dirty_existing_files
    assert not GitCommands(workspace_main / "sub" / "subsub").untracked_files
    assert not GitCommands(workspace_main / "sub" / "subsub").all_dirty_files

    # make a submodule and check if marked as dirty
    subprocess.check_call(
        git + ["submodule", "add", f"file://{repo_2}", "repo2"],
        cwd=workspace_main / "sub" / "subsub",
    )
    assert not GitCommands(workspace_main / "sub" / "subsub").dirty_existing_files
    assert GitCommands(workspace_main / "sub" / "subsub").untracked_files
    assert GitCommands(workspace_main / "sub" / "subsub").all_dirty_files

    assert GitCommands(workspace_main / "sub").is_submodule("subsub")


def test_cleanup_dirty_submodule(temppath):
    """
    make dirty submodule then repo.full_clean
    """
    workspace = temppath / "workspace_cleanup_dirty_submodule"
    os.chdir(workspace.parent)

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_sub = _make_remote_repo(temppath / "sub1")
    repo_subsub = _make_remote_repo(temppath / "subsub1")

    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace.name],
        cwd=workspace.parent,
    )
    with clone_and_commit(repo_subsub, "main") as repopath:
        (repopath / "file1.txt").write_text("This is a new function")
        subprocess.check_call(git + ["add", "file1.txt"], cwd=repopath)
        subprocess.check_call(git + ["commit", "-am", "file1 added"], cwd=repopath)

    with clone_and_commit(repo_sub, "main") as repopath:
        (repopath / "file1.txt").write_text("This is a new function")
        subprocess.check_call(git + ["add", "file1.txt"], cwd=repopath)
        subprocess.check_call(
            git + ["submodule", "add", f"file://{repo_subsub}", "subsub"], cwd=repopath
        )
        subprocess.check_call(git + ["commit", "-am", "file1 added"], cwd=repopath)

    with clone_and_commit(repo_main, "main") as repopath:
        (repopath / "file1.txt").write_text("This is a new function")
        subprocess.check_call(git + ["add", "file1.txt"], cwd=repopath)
        subprocess.check_call(
            git + ["submodule", "add", f"file://{repo_sub}", "sub"], cwd=repopath
        )
        subprocess.check_call(git + ["commit", "-am", "file1 added"], cwd=repopath)

    workspace_main = workspace / "main_working"
    subprocess.check_call(git + ["clone", f"file://{repo_main}", workspace_main])
    subprocess.check_call(
        git + ["submodule", "update", "--init", "--recursive"], cwd=workspace_main
    )
    assert (workspace_main / "sub" / "subsub" / "file1.txt").exists()

    # make dirty
    (workspace_main / "sub" / "subsub" / "file5.txt").write_text("data")
    Repo(workspace_main).full_clean()


def test_switch_submodule_to_integrated_and_sub(temppath):
    workspace = temppath / "workspace_switch_submodule"
    workspace.mkdir()
    workspace_main = workspace / "main_working"

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_sub = _make_remote_repo(temppath / "sub1")

    repos_sub = {
        "repos": [
            {
                "url": f"file://{repo_sub}",
                "branch": "branch1",
                "path": "sub1",
                "patches": [],
                "type": "submodule",
            },
        ]
    }
    repos_int = {
        "repos": [
            {
                "url": f"file://{repo_sub}",
                "branch": "branch1",
                "path": "sub1",
                "patches": [],
                "type": "integrated",
            },
        ]
    }
    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace_main],
        cwd=workspace.parent,
    )
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_int))
    (workspace_main / "main.txt").write_text("main repo")
    repo = Repo(workspace_main)
    repo.simple_commit_all()
    repo.X(*(git + ["push"]))

    os.chdir(workspace_main)
    gimera_apply([], None)

    def test_if_change_is_pushed_back():
        file = workspace_main / "sub1" / str(uuid.uuid4())
        file.write_text("content")
        subrepo = repo.get_submodule("sub1")
        subrepo.simple_commit_all()
        subrepo.X(*(git + ["push"]))
        with clone_and_commit(repo_sub, "branch1") as repopath:
            assert (repopath / file.name).exists()

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_sub))
    os.chdir(workspace_main)
    gimera_apply([], None)
    try:
        repo.get_submodule("sub1")
    except ValueError:
        raise Exception("Should be found")
    test_if_change_is_pushed_back()

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_int))
    os.chdir(workspace_main)
    repo.X(*(git + ["add", "sub1"]))
    repo.X(*(git + ["commit", "-m", "submodule new revision"]))
    gimera_apply([], None)
    try:
        repo.get_submodule("sub1")
    except ValueError:
        pass
    else:
        raise Exception("Should not be found")

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_sub))
    os.chdir(workspace_main)
    gimera_apply([], None)
    try:
        repo.get_submodule("sub1")
    except ValueError:
        raise Exception("Should be found")
    test_if_change_is_pushed_back()


def test_switch_submodule_to_integrated_and_sub_with_gitignores(temppath):
    """Took long time to understand it:
    if there are gitignores and a submodule is moved to an integrated module
    then files of that subrepo may become gitignored files of main repo and
    removal of that directory fails.
    For that clear_empty_subpaths is called after switching to git clean
    untracked, ignored and excluded files. Excluded files not really used and tested
    yet.
    """
    workspace = temppath / "workspace_switch_submodule_gitignore"
    workspace.mkdir()
    workspace_main = workspace / "main_working"

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_sub = _make_remote_repo(temppath / "sub1")

    repos_sub = {
        "repos": [
            {
                "url": f"file://{repo_sub}",
                "branch": "branch1",
                "path": "sub1",
                "patches": [],
                "type": "submodule",
            },
        ]
    }
    repos_int = {
        "repos": [
            {
                "url": f"file://{repo_sub}",
                "branch": "branch1",
                "path": "sub1",
                "patches": [],
                "type": "integrated",
            },
        ]
    }
    with clone_and_commit(repo_sub, "main") as repopath:
        (repopath / "repo_sub.txt").write_text("This is a new function")
        (repopath / "dont_look_at_me").write_text("i am ugly")
        Repo(repopath).simple_commit_all()

    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace_main],
        cwd=workspace.parent,
    )
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_int))
    (workspace_main / "main.txt").write_text("main repo")
    (workspace_main / ".gitignore").write_text("dont_look_at_me\n")
    repo = Repo(workspace_main)
    repo.simple_commit_all()
    repo.X(*(git + ["push"]))

    os.chdir(workspace_main)
    gimera_apply([], None)

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_sub))
    repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    try:
        repo.get_submodule("sub1")
    except ValueError:
        raise Exception("Should be found")
    assert not repo.all_dirty_files

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_int))
    repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    try:
        repo.get_submodule("sub1")
    except ValueError:
        pass
    else:
        raise Exception("Should not be found")
    assert not repo.all_dirty_files

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_sub))
    repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    try:
        repo.get_submodule("sub1")
    except ValueError:
        raise Exception("Should be found")
    assert not repo.all_dirty_files


def test_switch_submodule_to_other_url(temppath):
    """
    switch url of sub repo and check if redirected
    """
    workspace = temppath / "workspace_switch_subrepo"
    os.chdir(workspace.parent)

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_1 = _make_remote_repo(temppath / "repo1")
    repo_2 = _make_remote_repo(temppath / "repo2")

    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace.name],
        cwd=workspace.parent,
    )
    with clone_and_commit(repo_1, "main") as repopath:
        (repopath / "repo1.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    with clone_and_commit(repo_2, "main") as repopath:
        (repopath / "repo2.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    with clone_and_commit(repo_main, "main") as repopath:
        (repopath / "dummy.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    workspace_main = workspace / "main_working"
    subprocess.check_call(git + ["clone", f"file://{repo_main}", workspace_main])
    subprocess.check_call(
        git + ["submodule", "update", "--init", "--recursive"], cwd=workspace_main
    )

    repos1 = {
        "repos": [
            {
                "url": f"file://{repo_1}",
                "branch": "main",
                "path": "subby",
                "patches": [],
                "type": "submodule",
            },
        ]
    }
    repos2 = {
        "repos": [
            {
                "url": f"file://{repo_2}",
                "branch": "main",
                "path": "subby",
                "patches": [],
                "type": "submodule",
            },
        ]
    }
    main_repo = Repo(workspace_main)
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos1))
    main_repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    assert (workspace_main / "subby" / "repo1.txt").exists()

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos2))
    main_repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    assert (workspace_main / "subby" / "repo2.txt").exists()


def test_switch_submodule_to_integrated_on_different_branches(temppath):
    """
    switch url of sub repo and check if redirected
    """
    workspace = temppath / "workspace_switch_subrepo"
    os.chdir(workspace.parent)

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_1 = _make_remote_repo(temppath / "repo1")

    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace.name],
        cwd=workspace.parent,
    )
    with clone_and_commit(repo_1, "main") as repopath:
        (repopath / "repo1.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    with clone_and_commit(repo_main, "main") as repopath:
        (repopath / "dummy.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    workspace_main = workspace / "main_working"
    subprocess.check_call(git + ["clone", f"file://{repo_main}", workspace_main])
    subprocess.check_call(
        git + ["submodule", "update", "--init", "--recursive"], cwd=workspace_main
    )

    repos = {
        "repos": [
            {
                "url": f"file://{repo_1}",
                "branch": "main",
                "path": "subby",
                "patches": [],
                "type": "submodule",
            },
        ]
    }

    main_repo = Repo(workspace_main)
    main_repo.X(*(git + ["checkout", "-b", "as_submodule"]))
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos))
    main_repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    assert (workspace_main / "subby" / "repo1.txt").exists()
    sha_submodule_step1 = yaml.safe_load((workspace_main / "gimera.yml").read_text())[
        "repos"
    ][0]["sha"]
    assert sha_submodule_step1

    main_repo.X(*(git + ["checkout", "-b", "as_integrated"]))
    repos["repos"][0]["type"] = "integrated"
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos))
    main_repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    assert (workspace_main / "subby" / "repo1.txt").exists()
    assert not (workspace_main / "subby" / "repo2.txt").exists()
    assert not (workspace_main / ".gitmodules").read_text()

    main_repo.X(*(git + ["checkout", "as_submodule"]))
    assert (workspace_main / ".gitmodules").read_text()

    with clone_and_commit(repo_1, "main") as repopath:
        (repopath / "repo2.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    os.chdir(workspace_main)
    assert yaml.safe_load((workspace_main / "gimera.yml").read_text())["repos"][0][
        "sha"
    ]
    gimera_apply([], False)
    assert (workspace_main / "subby" / "repo1.txt").exists()
    assert not (workspace_main / "subby" / "repo2.txt").exists()

    os.chdir(workspace_main)
    os.environ["GIMERA_NON_THREADED"] = "1"
    gimera_apply([], True)
    assert (workspace_main / "subby" / "repo1.txt").exists()
    assert (workspace_main / "subby" / "repo2.txt").exists()

    main_repo.X(*(git + ["checkout", "-f", "as_integrated"]))
    main_repo.X("git", "clean", "-xdff")
    gimera_apply([], False)
    assert (workspace_main / "subby" / "repo1.txt").exists()
    assert not (workspace_main / "subby" / "repo2.txt").exists()


def test_merges(temppath):
    workspace = temppath / "workspace_switch_subrepo"
    os.chdir(workspace.parent)

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_1 = _make_remote_repo(temppath / "repo1")
    repo_1variant = temppath / "repo1variant"

    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace.name],
        cwd=workspace.parent,
    )
    # make variant repo and change on a branch there
    with clone_and_commit(repo_1, "main") as repopath:
        (repopath / "repo1.txt").write_text("This is a new function")
        subprocess.check_call(["sync"])
        repo = Repo(repopath)
        repo.simple_commit_all()
        repo.X(*(git + ["push"]))

    subprocess.check_call(git + ["clone", "--mirror", "--bare", repo_1, repo_1variant])
    subprocess.check_call(["sync"])

    with clone_and_commit(repo_1variant, "main") as repopath_variant:
        assert Path(repopath_variant / "repo1.txt").exists()
        variant = Repo(repopath_variant)
        variant.X(*(git + ["checkout", "-b", "variant"]))
        (repopath_variant / "variant.txt").write_text("This is a new function")
        variant.simple_commit_all()
        variant.X(*(git + ["push", "--set-upstream", "origin", "variant"]))
        variant.X(*(git + ["checkout", "main"]))

        variant.X(*(git + ["checkout", "-b", "variant2"]))
        (repopath_variant / "variant2.txt").write_text("This is a new function")
        variant.simple_commit_all()
        variant.X(*(git + ["push", "--set-upstream", "origin", "variant2"]))
        variant.X(*(git + ["checkout", "main"]))

    with clone_and_commit(repo_main, "main") as repopath:
        (repopath / "dummy.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    workspace_main = workspace / "main_working"
    subprocess.check_call(git + ["clone", f"file://{repo_main}", workspace_main])
    subprocess.check_call(
        git + ["submodule", "update", "--init", "--recursive"], cwd=workspace_main
    )

    repos = {
        "repos": [
            {
                "url": f"file://{repo_1}",
                "branch": "main",
                "path": "subby",
                "remotes": {
                    "repo_variant": str(repo_1variant),
                },
                "merges": ["repo_variant variant"],
                "patches": [],
                "type": "integrated",
            },
        ]
    }

    main_repo = Repo(workspace_main)
    main_repo.X(*(git + ["checkout", "-b", "as_submodule"]))
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos))
    main_repo.simple_commit_all()
    subprocess.check_call(["sync"])
    os.chdir(workspace_main)
    gimera_apply([], None)
    assert (workspace_main / "subby" / "variant.txt").exists()
    assert (workspace_main / "subby" / "repo1.txt").exists()

    # reapply should also work
    gimera_apply([], None)
    assert (workspace_main / "subby" / "variant.txt").exists()
    assert (workspace_main / "subby" / "repo1.txt").exists()

    # change the merge - no changes from other merge should exist
    repos = {
        "repos": [
            {
                "url": f"file://{repo_1}",
                "branch": "main",
                "path": "subby",
                "remotes": {
                    "repo_variant": str(repo_1variant),
                },
                "merges": ["repo_variant variant2"],
                "patches": [],
                "type": "integrated",
            },
        ]
    }
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos))
    main_repo.simple_commit_all()
    gimera_apply([], None)
    assert not (workspace_main / "subby" / "variant.txt").exists()
    assert (workspace_main / "subby" / "variant2.txt").exists()
    assert (workspace_main / "subby" / "repo1.txt").exists()


def test_clean_a_submodule_in_submodule(temppath):
    workspace = temppath / "workspace_switch_subrepo"
    os.chdir(workspace.parent)

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_1 = _make_remote_repo(temppath / "repo1")
    repo_2 = _make_remote_repo(temppath / "repo1variant")

    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace.name],
        cwd=workspace.parent,
    )
    # make variant repo and change on a branch there
    with clone_and_commit(repo_2, "main") as repopath:
        (repopath / "repo2.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    with clone_and_commit(repo_1, "main") as repopath:
        (repopath / "repo1.txt").write_text("This is a new function")
        Repo(repopath).X(
            *(git + ["submodule", "add", f"file://{repo_2}", "folder_of_repo2/repo2"])
        )
        Repo(repopath).simple_commit_all()

    with clone_and_commit(repo_main, "main") as repopath:
        (repopath / "dummy.txt").write_text("This is a new function")
        Repo(repopath).X(
            *(git + ["submodule", "add", f"file://{repo_1}", "folder_of_repo1"])
        )
        Repo(repopath).simple_commit_all()

    workspace_main = workspace / "main_working"
    subprocess.check_call(git + ["clone", f"file://{repo_main}", workspace_main])
    subprocess.check_call(
        git + ["submodule", "update", "--init", "--recursive"], cwd=workspace_main
    )
    main_repo = Repo(workspace_main)
    assert (workspace_main / "folder_of_repo1" / "repo1.txt").exists()
    assert (
        workspace_main / "folder_of_repo1" / "folder_of_repo2" / "repo2" / "repo2.txt"
    ).exists()

    submodule_repo1 = main_repo.get_submodule("folder_of_repo1")
    submodule_repo1.force_remove_submodule("folder_of_repo2/repo2")


def test_2_submodules(temppath):
    """
    The delete submodule was too hard and deleted submodules
    """
    workspace = temppath / "workspace_2submodules"
    workspace.mkdir(exist_ok=True)
    os.chdir(workspace.parent)

    repo_main = _make_remote_repo(workspace / "mainrepo")
    repo_1 = _make_remote_repo(workspace / "repo1")
    subrepo_1 = _make_remote_repo(workspace / "subrepo1")
    repo_2 = _make_remote_repo(workspace / "repo2")
    subrepo_2 = _make_remote_repo(workspace / "subrepo2")

    with clone_and_commit(subrepo_1, "main") as repopath:
        (repopath / "subrepo1.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()
    with clone_and_commit(subrepo_2, "main") as repopath:
        (repopath / "subrepo2.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    with clone_and_commit(repo_1, "main") as repopath:
        (repopath / "repo1.txt").write_text("This is a new function")
        (repopath / "gimera.yml").write_text(
            yaml.dump(
                {
                    "repos": [
                        {
                            "url": f"file://{subrepo_1}",
                            "branch": "main",
                            "path": "subrepo1",
                            "type": "submodule",
                        },
                    ]
                }
            )
        )
        Repo(repopath).simple_commit_all()

    with clone_and_commit(repo_2, "main") as repopath:
        (repopath / "repo2.txt").write_text("This is a new function")
        (repopath / "gimera.yml").write_text(
            yaml.dump(
                {
                    "repos": [
                        {
                            "url": f"file://{subrepo_2}",
                            "branch": "main",
                            "path": "subrepo2",
                            "type": "submodule",
                        },
                    ]
                }
            )
        )
        Repo(repopath).simple_commit_all()

    repos = {
        "repos": [
            {
                "url": f"file://{repo_1}",
                "branch": "main",
                "path": "repo1",
                "type": "submodule",
            },
            {
                "url": f"file://{repo_2}",
                "branch": "main",
                "path": "repo2",
                "type": "submodule",
            },
        ]
    }

    workspace_main = workspace / "main_working"
    main_repo = Repo(workspace_main)
    subprocess.check_call(git + ["clone", f"file://{repo_main}", workspace_main])
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos))

    os.chdir(workspace_main)
    gimera_apply([], update=None, recursive=True)

    assert (workspace_main / "repo1" / "repo1.txt").exists()
    assert (workspace_main / "repo1" / "subrepo1" / "subrepo1.txt").exists()
    assert (workspace_main / "repo2" / "repo2.txt").exists()
    assert (workspace_main / "repo2" / "subrepo2" / "subrepo2.txt").exists()

    submodule_repo1 = main_repo.get_submodule("repo1")
    submodule_repo2 = main_repo.get_submodule("repo2")
    assert submodule_repo1
    assert submodule_repo2


# test change something in submodule and check if gets lost if not pushed




def test_switch_submodule_to_integrated_and_sub_with_gitignoring_main_repo(temppath):
    workspace = temppath / "workspace_switch_submodule_gitignore"
    workspace.mkdir()
    workspace_main = workspace / "main_working"

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_sub = _make_remote_repo(temppath / "sub1")

    repos_sub = {
        "repos": [
            {
                "url": f"file://{repo_sub}",
                "branch": "branch1",
                "path": "sub1",
                "patches": [],
                "type": "submodule",
            },
        ]
    }
    repos_int = {
        "repos": [
            {
                "url": f"file://{repo_sub}",
                "branch": "branch1",
                "path": "sub1",
                "patches": [],
                "type": "integrated",
            },
        ]
    }
    with clone_and_commit(repo_sub, "main") as repopath:
        (repopath / "repo_sub.txt").write_text("This is a new function")
        (repopath / "dont_look_at_me").write_text("i am ugly")
        Repo(repopath).simple_commit_all()

    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace_main],
        cwd=workspace.parent,
    )
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_int))
    (workspace_main / "main.txt").write_text("main repo")
    (workspace_main / ".gitignore").write_text("dont_look_at_me\n")
    repo = Repo(workspace_main)
    repo.simple_commit_all()
    repo.X(*(git + ["push"]))

    os.chdir(workspace_main)

    gitignore = workspace_main / ".gitignore"
    gitignore.write_text("sub1")
    gimera_apply([], None)

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_sub))
    repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    try:
        repo.get_submodule("sub1")
    except ValueError:
        raise Exception("Should be found")
    assert not repo.all_dirty_files

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_int))
    repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    try:
        repo.get_submodule("sub1")
    except ValueError:
        pass
    else:
        raise Exception("Should not be found")
    assert not repo.all_dirty_files

    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_sub))
    repo.simple_commit_all()
    os.chdir(workspace_main)
    gimera_apply([], None)
    try:
        repo.get_submodule("sub1")
    except ValueError:
        raise Exception("Should be found")
    assert not repo.all_dirty_files


def test_git_submodule_point_to_branch_if_last_commit_matches_tip_point_of_branch(
    temppath,
):
    workspace = temppath / "workspace_switch_submodule_gitignore"
    workspace.mkdir()
    workspace_main = workspace / "main_working"

    repo_main = _make_remote_repo(temppath / "mainrepo")
    repo_sub = _make_remote_repo(temppath / "sub1")

    repos_sub = {
        "repos": [
            {
                "url": f"file://{repo_sub}",
                "branch": "main",
                "path": "sub1",
                "patches": [],
                "type": "submodule",
            },
        ]
    }
    with clone_and_commit(repo_sub, "main") as repopath:
        (repopath / "repo_sub.txt").write_text("This is a new function")
        Repo(repopath).simple_commit_all()

    subprocess.check_output(
        git + ["clone", "file://" + str(repo_main), workspace_main],
        cwd=workspace.parent,
    )
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_sub))
    (workspace_main / "main.txt").write_text("main repo")
    (workspace_main / ".gitignore").write_text("dont_look_at_me\n")
    repo = Repo(workspace_main)
    repo.simple_commit_all()
    repo.X(*(git + ["push"]))
    os.chdir(workspace_main)
    gimera_apply([], None)

    # now update the submodule and remember commit sha
    with clone_and_commit(repo_sub, "main") as repopath:
        (repopath / "repo_sub.txt").write_text("This is a new function2")
        reposub = Repo(repopath)
        reposub.simple_commit_all()
        commit = reposub.get_commit()
        branch = reposub.get_branch()
        assert branch == "main"

    repos_sub["repos"][0]["sha"] = commit
    (workspace_main / "gimera.yml").write_text(yaml.dump(repos_sub))
    os.chdir(workspace_main)
    gimera_apply([], {})

    submodule = repo.get_submodule("sub1")
    assert submodule.get_commit() == commit
    assert submodule.get_branch() == branch, "Should now be on the branch, not a sha"

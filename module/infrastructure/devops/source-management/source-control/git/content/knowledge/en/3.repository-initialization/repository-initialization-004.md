# Inspecting a Repository with git status and git rev-parse

After opening a terminal, the first thing you need to know is which repository you are in, whether the repository has a working tree, and which changes are pending. Git provides two complementary commands for this: `git status` describes the working state of the repository; `git rev-parse` helps determine internal repository paths and properties.

These two commands are frequently used together in daily workflows and in scripts. `git status` answers the question "what has changed?", while `git rev-parse` answers "how is Git recognizing this repository and where are its administrative directories located?".

After this lesson, you will be able to:

- Read the state of the working tree and staging area using `git status`.
- Distinguish between staged, unstaged, untracked, and ignored changes.
- Use short and porcelain modes for stable, parseable output.
- Identify the branch, detached HEAD, and upstream status.
- Determine the repository root, Git directory, and common directory with `git rev-parse`.
- Distinguish between standard repositories, bare repositories, subdirectories, and linked worktrees.
- Combine both commands to diagnose repository location and state in scripts.

## 1. Quick inspection with git status

Run:

~~~bash
git status
~~~

This command reports the current branch, status relative to upstream if configured, changes in the staging area, unstaged changes, and untracked files. It is a command you should run before committing, merging, rebasing, checking out, or applying a patch.

Example output:

~~~text
On branch feature/search
Your branch is up to date with 'origin/feature/search'.

Changes to be committed:
  modified:   src/Search.java

Changes not staged for commit:
  modified:   README.md

Untracked files:
  docs/search-notes.md
~~~

In this example:

- `src/Search.java` is staged and will be included in the snapshot if you create a commit right now.
- `README.md` has been modified in the working tree but has not yet been staged.
- `docs/search-notes.md` is a new file not yet tracked by Git.

`git status` does not modify files, the index, or history. It is a safe read-only status command.

## 2. Working tree, staging area, and file state

To understand `git status` output, distinguish between three areas:

~~~text
        git add                 git commit
Working tree ----------> Staging area ----------> Repository
     ^                         |
     |                         |
     +------ git restore ------+
~~~

- The working tree consists of the files and directories you see, open, and edit.
- The staging area is stored by Git in the index, holding the content that will go into the next commit.
- The repository stores commits and objects already recorded in history.

A tracked file can differ from the current commit, differ from the index, or differ in both places. That is why Git distinguishes changes in the index from changes in the working tree.

Example:

~~~bash
# Stage changes to the file
git add src/Search.java

# Continue editing the file after staging
git status
~~~

At this point, the file can appear under both "Changes to be committed" and "Changes not staged for commit". That means the snapshot in the index and the current contents of the working tree differ.

To view the details:

~~~bash
# Unstaged changes: working tree vs. index
git diff

# Staged changes: index vs. HEAD
git diff --cached
~~~

`git status` summarizes state; `git diff` lets you inspect the actual differing content.

## 3. Reading short status output

When you need compact output, use:

~~~bash
git status --short
~~~

Each line begins with two status columns:

~~~text
XY path
~~~

- `X` describes changes in the index compared to the current commit.
- `Y` describes changes in the working tree compared to the index.

Some common codes:

| Code | Meaning |
| --- | --- |
| ` M` | Tracked file modified in the working tree, not staged. |
| `M ` | File has staged modifications. |
| `MM` | File has a staged modification and was modified again in the working tree. |
| `A ` | New file has been staged. |
| `D ` | Deletion of a file has been staged. |
| ` D` | File was deleted in the working tree, not yet staged. |
| `??` | File is untracked by Git. |
| `!!` | File is ignored, when showing ignored files is requested. |

Spaces in the two columns are significant. For example, ` M` and `M ` describe two different areas, so do not strip leading whitespace when reading the output.

For renames or copies, the output may display the corresponding status code along with old and new paths. For merge conflicts, codes such as `UU`, `AA`, or `DD` indicate specific unmerged states. When you need detailed conflict information, also run `git diff` and full `git status`.

## 4. Showing branch and upstream information

To view the branch alongside file status in a short output:

~~~bash
git status --short --branch
~~~

Example:

~~~text
## feature/search...origin/feature/search [ahead 2]
 M src/Search.java
?? docs/search-notes.md
~~~

The first line shows the current branch and its relationship to upstream if tracking is configured. `[ahead 2]` indicates the local branch has two commits not yet on upstream. Depending on the state, Git may also show `behind`, both `ahead` and `behind`, or an up-to-date status.

If the branch has no upstream, Git may display only the branch name without the comparison part. If HEAD is detached, the output reports the detached state instead of a regular branch name.

This command does not fetch from the remote. Ahead/behind counts are computed from local remote-tracking refs currently stored on disk, so they may be stale if the remote recently changed and you have not fetched.

To update remote information before viewing the comparison status:

~~~bash
git fetch
git status --short --branch
~~~

Fetching updates remote-tracking refs without automatically merging or rebasing your current branch.

## 5. Showing untracked and ignored files

By default, Git often groups untracked files inside the same directory into a single directory entry to keep output readable. If you need every file listed individually:

~~~bash
git status --untracked-files=all
~~~

To also view ignored files:

~~~bash
git status --short --ignored
~~~

Ignored files are typically marked `!!` in short output. This is useful when confirming why a build artifact or local config file does not appear in the untracked list.

`git status` does not imply ignored files will be staged automatically. To see which ignore rule applies, use:

~~~bash
git check-ignore -v path/to/file
~~~

Only un-ignore or force-add a file when you understand why it was ignored and are certain it belongs in the repository.

## 6. Using porcelain output for scripts

The default output of `git status` is designed for human readers. Wording and layout can change between Git versions, so scripts should not parse English phrases like "Changes not staged for commit".

Git provides a porcelain format for programmatic consumption. Example:

~~~bash
git status --porcelain=v1
~~~

Or version 2:

~~~bash
git status --porcelain=v2 --branch
~~~

Porcelain output has a more stable format than human-facing output. Version 1 uses two-character status codes and paths. Version 2 has a more explicit record structure, providing richer information about branches and file states.

When filenames contain spaces, tabs, newlines, or special characters, line-based parsing can be unsafe. Use `-z` for NUL-delimited output:

~~~bash
git status --porcelain=v1 -z
~~~

In scripts, use a parser that properly understands the porcelain format and handles NUL-terminated paths. Do not split output on whitespace, because valid filenames can contain spaces.

Example quick check for whether a repository has changes:

~~~bash
if test -z "$(git status --porcelain)"; then
    echo "Working tree and index are clean."
else
    echo "Repository has pending changes."
fi
~~~

This snippet is suitable for simple checks in shell. If you need to handle arbitrary filenames with special characters or make decisions based on change types, use porcelain with `-z` and an appropriate parser.

## 7. What is git rev-parse used for?

`git rev-parse` is a low-level command that helps Git resolve revisions and print internal repository information. In repository inspection tasks, it is commonly used to determine:

- The repository root.
- The path to the Git directory.
- The path to the common directory shared across worktrees.
- Whether you are inside a working tree, a Git directory, or a bare repository.
- The path to an internal file such as the index or object database.
- The repository's object hash format.

This command is especially useful in scripts because it does not assume the user is running from the root directory.

## 8. Determining the repository root and current location

To obtain the absolute path to the working tree root directory:

~~~bash
git rev-parse --show-toplevel
~~~

For example, even if the terminal is in `src/service/search`, the command still returns the root of the repository.

To view the relative path from the root to the current directory:

~~~bash
git rev-parse --show-prefix
~~~

To view how many directory levels you need to move up from the current location to reach the root:

~~~bash
git rev-parse --show-cdup
~~~

For example, if you are at the root, `--show-prefix` and `--show-cdup` return an empty string. If you are in `src/service`, `--show-prefix` may return `src/service/`, while `--show-cdup` may return `../../`.

These three commands help scripts locate files using repository-relative paths instead of depending on where the terminal happens to be.

## 9. Distinguishing between the Git directory and common directory

Get the Git directory of the current repository:

~~~bash
git rev-parse --git-dir
~~~

To get the absolute path:

~~~bash
git rev-parse --absolute-git-dir
~~~

In a standard repository, the Git directory is typically `.git`. However, `.git` is not always a directory. In a linked worktree, `.git` inside the working tree can be a file pointing to that worktree's separate Git directory.

To get the common directory:

~~~bash
git rev-parse --git-common-dir
~~~

In a linked worktree, the worktree's own Git directory stores per-worktree data such as HEAD and the index, while the common directory holds the shared object database and refs. In a repository without linked worktrees, these two paths normally point to the same location.

Therefore, do not write scripts assuming `.git` is always a directory directly under the repository root. Use `git rev-parse --git-dir` or `--git-common-dir` to retrieve the resolved Git paths.

## 10. Identifying the repository type and current context

Several boolean inspection commands:

~~~bash
git rev-parse --is-inside-work-tree
git rev-parse --is-inside-git-dir
git rev-parse --is-bare-repository
~~~

The output is `true` or `false`.

| State | is-inside-work-tree | is-inside-git-dir | is-bare-repository |
| --- | --- | --- | --- |
| Inside a standard working tree | true | false | false |
| Inside the .git directory of a non-bare repository | false | true | false |
| Inside a bare repository directory (Git directory) | false | true | true |

If you are in a subdirectory of a working tree, `--is-inside-work-tree` still returns `true`. If you are outside a repository, the command typically reports an error and exits with a non-zero exit code rather than returning `false`.

A bare repository contains Git data but has no working tree for editing files. It is commonly used as a central remote or shared storage repository. `git status` cannot display working tree file changes in a bare repository because there is no working tree as in a standard repository.

## 11. Resolving internal paths with --git-path

Do not manually concatenate paths like `.git/index` or `.git/objects` in scripts. Use:

~~~bash
git rev-parse --git-path index
git rev-parse --git-path objects
git rev-parse --git-path hooks
~~~

`--git-path` asks Git to resolve a path inside the Git directory. It accounts for settings such as `GIT_OBJECT_DIRECTORY`, `GIT_INDEX_FILE`, and special storage layouts.

Example retrieving the index path:

~~~bash
git rev-parse --git-path index
~~~

This is the staging index of the current repository. In a linked worktree, the worktree's own index may live inside the worktree's administrative directory rather than the common directory.

To determine the object format:

~~~bash
git rev-parse --show-object-format
~~~

The output is typically `sha1` or `sha256`. This is useful for tools that process OIDs without assuming a fixed length.

## 12. Checking HEAD and branch with rev-parse

To view the current branch name:

~~~bash
git rev-parse --abbrev-ref HEAD
~~~

If HEAD is attached to a branch, the command returns its short name such as `main` or `feature/search`. If HEAD is detached, the output may be `HEAD`, since there is no corresponding short branch name.

To check whether HEAD resolves to a commit:

~~~bash
git rev-parse --verify HEAD
~~~

In a repository without an initial commit yet, the branch may be in an unborn state and `HEAD` does not yet resolve to a commit object. The `--verify` command will fail. This is a normal situation for a new repository after `git init` and before the first commit.

If the branch has an upstream, you can query the full upstream name:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

This command fails if the current branch does not have an upstream configured. Handle the exit code rather than assuming every branch tracks a remote branch.

## 13. Combining status and rev-parse in a workflow

When taking over a project directory or running a script from a subdirectory, you can check step by step:

~~~bash
# 1. Confirm this is a working tree
git rev-parse --is-inside-work-tree

# 2. Get the repository root
git rev-parse --show-toplevel

# 3. Get the Git directory and common directory
git rev-parse --absolute-git-dir
git rev-parse --git-common-dir

# 4. View branch and change status
git status --short --branch

# 5. Inspect detailed changes
git diff
git diff --cached
~~~

If `--is-inside-work-tree` does not return `true`, determine whether you are inside a bare repository, inside the Git directory, or outside a repository. Do not run file-manipulation commands on the assumption that a working tree is always present.

An illustrative shell script:

~~~bash
#!/bin/sh
set -eu

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "Current directory is not inside a Git repository."
    exit 1
fi

if [ "$(git rev-parse --is-bare-repository)" = "true" ]; then
    echo "This is a bare repository."
    exit 0
fi

if [ "$(git rev-parse --is-inside-work-tree)" != "true" ]; then
    echo "Current directory is inside Git metadata, not a working tree."
    exit 1
fi

root=$(git rev-parse --show-toplevel)
echo "Repository root: $root"
git status --short --branch
~~~

This script distinguishes three basic cases: not a repository, a bare repository, and a working tree. If you are inside the Git directory rather than the working tree, the script reports it separately to avoid treating the metadata directory as a source code directory.

## 14. Practical scenarios

### Terminal is in a subdirectory

You open a terminal at `project/src/service` and want to determine the root before invoking a script:

~~~bash
git rev-parse --show-toplevel
git rev-parse --show-prefix
git status --short --branch
~~~

`git status` still reports repository-wide status if no pathspec is passed. `--show-prefix` tells you the current location relative to the root.

### New repository with no commits yet

After `git init`, check:

~~~bash
git status --short --branch
git rev-parse --is-inside-work-tree
git rev-parse --verify HEAD
~~~

The repository already has a working tree, but HEAD may not yet point to a valid commit. `git rev-parse --verify HEAD` fails until the first commit is created. Do not treat this as a broken repository.

### Working inside a linked worktree

Check:

~~~bash
git rev-parse --show-toplevel
git rev-parse --absolute-git-dir
git rev-parse --git-common-dir
git status --short --branch
~~~

The worktree's Git directory may differ from the common directory. Each worktree has its own HEAD and index, while the object database is shared. This explains why `.git` can be a file and why you should not hard-code `.git/index`.

### Script needs to know whether there are uncommitted changes

Use porcelain:

~~~bash
git status --porcelain
~~~

If output is empty, the index and working tree have no changes reported by status. If you need to include ignored or untracked files in detail, add the corresponding options. Do not rely on default output to conclude there are no ignored files in the directory.

## 15. Common mistakes

### Running git status outside a repository

Git reports that it is not a repository. Use `git rev-parse --git-dir` to check before a script runs repository-dependent steps.

### Thinking git status only shows unstaged changes

Incorrect. It shows staged, unstaged, and untracked changes as well as some branch/upstream information. Use `git diff` and `git diff --cached` to inspect the contents of each area.

### Not seeing a new file in git status

The file may be ignored or located outside the working tree. Use `git status --short --ignored` and `git check-ignore -v path/to/file` to diagnose.

### Confusing M in the first column vs. the second column

The first column is the index; the second column is the working tree. `M ` is a staged change, whereas ` M` is an unstaged change.

### Parsing human-readable git status output in scripts

Do not rely on human-facing phrasing. Use `--porcelain=v1` or `--porcelain=v2`; add `-z` if you need to safely handle filenames with special characters.

### Assuming .git is always a directory

In a linked worktree or submodule, `.git` can be a file pointing to the real Git directory. Use `git rev-parse --git-dir`, `--absolute-git-dir`, and `--git-common-dir`.

### git rev-parse --verify HEAD failing after git init

The repository may not have its first commit yet. Check `git status` and branch state; create the first commit once you have content to record.

## 16. Key takeaways

- `git status` reports the branch, upstream, and changes in the index/working tree.
- `git status --short` uses two columns: X is index status, Y is working tree status.
- `??` indicates an untracked file; `!!` indicates an ignored file when showing ignored files is enabled.
- Use `--porcelain=v1` or `--porcelain=v2` when scripts require stable output; add `-z` to handle special filenames.
- `git rev-parse --show-toplevel` gets the repository root; `--show-prefix` and `--show-cdup` describe the current location relative to the root.
- `--git-dir`, `--absolute-git-dir`, and `--git-common-dir` identify metadata areas, including for linked worktrees.
- `--is-inside-work-tree`, `--is-inside-git-dir`, and `--is-bare-repository` distinguish repository contexts.
- `--git-path` resolves internal paths without hard-coding `.git`.
- `git rev-parse --verify HEAD` can fail in a repository before its first commit.

Combining `git status` and `git rev-parse` helps you know where the repository is, what kind of working tree it has, and which changes are pending. This is the foundation for operating safely in the terminal, writing reliable Git scripts, and diagnosing repositories across different layouts.

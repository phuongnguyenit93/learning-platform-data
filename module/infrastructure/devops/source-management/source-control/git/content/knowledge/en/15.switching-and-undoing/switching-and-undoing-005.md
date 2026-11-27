# Path Reset vs. Branch Pointer Reset

`git reset` has two usages that are easy to confuse. When accompanied by a path, the command updates the **index (staging area)** for the selected files and does not move `HEAD` or the branch pointer. When given a commit without a path, the command can move `HEAD`/the branch and, depending on the mode, also update the index or working tree.

Distinguishing these two forms helps you unstage a file while keeping your edits, or move an entire branch back to an older commit when you genuinely want to rewrite local history.

## 1. Two Command Forms with Different Purposes

### Reset by path: changes only the index

General syntax:

```bash
git reset [<tree-ish>] -- <pathspec>
```

Common example:

```bash
git reset -- src/config.yml
```

When `<tree-ish>` is omitted, Git uses `HEAD`. The command takes the version of `src/config.yml` from `HEAD` and copies the corresponding entry into the index. `HEAD` and the current branch do not change; the file in the working tree is not overwritten either.

This is how to unstage a file that was mistakenly staged with `git add`:

```bash
git add src/config.yml
git reset -- src/config.yml
```

After the reset command, the file's staged content returns to matching `HEAD`, while the edits in the working tree remain so you can continue editing or re-stage them.

You can choose another tree as the source for the index:

```bash
git reset HEAD~1 -- src/config.yml
```

The command above takes the file version from the parent commit of `HEAD` to update the index. It does not move the branch back to the parent commit and does not change the file's content currently in the working tree.

### Resetting the branch pointer: changes HEAD's position

Without a pathspec, the syntax takes the form:

```bash
git reset [--soft | --mixed | --hard | --merge | --keep] [<commit>]
```

Example:

```bash
git reset --mixed HEAD~1
```

This command moves `HEAD` and the current branch to the parent commit, and sets the index to that commit's state. The working tree is preserved. Changes from the commit just removed from the branch tip become unstaged changes in the working tree.

When on a branch, a commit reset updates that branch. If in detached `HEAD` state, Git moves only the detached `HEAD`, without updating any named branch.

## 2. How Does Path Reset Work?

The index stores the content that will go into the next commit. When you run `git add`, Git updates the entry in the index with the file's current content. A path reset copies content from a tree into the index to replace the staged entry.

Model before and after unstaging:

```text
Before git reset -- file
HEAD:         version A
Index:        version B  (staged)
Working tree: version C  (may have further edits)

After git reset -- file
HEAD:         version A
Index:        version A
Working tree: version C  (preserved)
```

The post-reset state means change B is no longer in the staging area. If the working tree differs from A, Git still displays the file as modified but unstaged.

Inspect each area:

```bash
git status
git diff --cached -- src/config.yml
git diff -- src/config.yml
```

- `git diff --cached` views the difference between the index and `HEAD`.
- `git diff` views the difference between the working tree and the index.

After `git reset -- src/config.yml`, the staged difference typically disappears, while the unstaged difference remains.

### Unstaging partial changes

If you only want to unstage certain hunks instead of the entire file, use interactive mode:

```bash
git reset -p -- src/config.yml
```

Git displays each staged hunk one by one so you can choose which parts to remove from the index. Content in the working tree is preserved. This is a useful option when a file contains both finished changes and work still in progress.

An equivalent, often clearer phrasing in many situations is:

```bash
git restore --staged --source=HEAD -- src/config.yml
```

`restore --staged` also restores the index from `HEAD` without modifying the working tree. `git reset <tree-ish> -- <pathspec>` is the older syntax and remains widely supported.

## 3. Path Reset Does Not Move the Branch

The key detail is the placement of `--` and the pathspec:

```bash
git reset HEAD~1 -- src/config.yml
```

In this command:

- `HEAD~1` is the source tree from which to take the file version.
- `--` ends options and separates the revision from the path.
- `src/config.yml` is the file updated in the index.

The branch still points to the current commit. To verify for yourself, run:

```bash
git rev-parse HEAD
git status
git diff --cached -- src/config.yml
git diff -- src/config.yml
```

If the goal is to unstage a file to the current version in `HEAD`, use `git reset -- <file>`. If the goal is to move the entire branch to a previous commit, do not include a pathspec:

```bash
git reset --mixed HEAD~1
```

The two commands have completely different scopes of impact. Do not omit `--` when a filename could be misinterpreted by Git as a revision name or an option.

## 4. Branch Pointer Reset Modes

When resetting to a commit without a pathspec, the mode determines how Git handles the index and working tree.

| Mode | `HEAD`/branch | Index | Working tree |
|---|---|---|---|
| `--soft` | Moves to target commit | Unchanged | Unchanged |
| `--mixed` (default) | Moves to target commit | Reset to target commit | Unchanged |
| `--hard` | Moves to target commit | Reset to target commit | Reset to target commit |
| `--merge` | Moves to target commit if safe | Reset to target commit | Conditionally updated, preserving unstaged changes when possible |
| `--keep` | Moves to target commit if safe | Reset to target commit | Preserves local changes; aborts if updating would overwrite changes |

Examples with the latest commit:

```bash
git reset --soft HEAD~1
```

The last commit is removed from the branch tip, while that commit's changes remain in the index. You can revise them or create a new commit.

```bash
git reset --mixed HEAD~1
```

The last commit is removed from the branch tip; the index returns to the parent commit, while the changes remain in the working tree as unstaged. This is the default mode if you do not specify one.

```bash
git reset --hard HEAD~1
```

The branch, index, and working tree are all reset to the parent commit. Uncommitted tracked changes in the index and working tree are discarded. Untracked files or directories obstructing writing tracked files may be deleted so Git can write the target version; this command is not a way to clean up all untracked files in the repository.

`--merge` and `--keep` are conditional modes, typically used when you need to reset while still protecting certain local changes. If Git detects that updating would unsafely overwrite changes, the command may abort. Read the messages and check `git status`; do not treat these two modes as a guarantee that every edit is preserved in every state.

## 5. Choosing the Right Operation by Goal

| Goal | Common command | Primary impact |
|---|---|---|
| Unstage a file, keep edits | `git reset -- file` | Updates index only |
| Unstage specific hunks | `git reset -p -- file` | Select hunks to update index |
| Set a file's index entry to another commit's version | `git reset <commit> -- file` | Updates index only from specified tree |
| Undo last commit while keeping changes staged | `git reset --soft HEAD~1` | Moves branch, keeps index and working tree |
| Undo last commit, keep changes unstaged | `git reset --mixed HEAD~1` | Moves branch and resets index |
| Undo last commit along with local tracked changes | `git reset --hard HEAD~1` | Moves branch, index, and working tree |

### Example: accidentally staging a configuration file

You edit `src/config.yml`, run `git add`, then notice the file still contains test values that should not go into the commit. You want to unstage it to keep editing:

```bash
git status
git reset -- src/config.yml
git diff -- src/config.yml
```

Then edit the content and re-stage:

```bash
git add src/config.yml
git diff --cached -- src/config.yml
```

### Example: wanting to rewrite the last commit

You just created a commit and realize you need to add a file and adjust that commit before sharing it:

```bash
git reset --soft HEAD~1
git status
git add src/missing-file.java
git commit -c ORIG_HEAD
```

After `--soft`, the changes from the removed commit remain staged. `ORIG_HEAD` usually stores `HEAD`'s position prior to the reset so you can reuse the previous commit's information; verify this value if the repository recently ran other operations that might update it. You can also use `git commit --amend` while the old commit is still `HEAD`, whereas in this example `HEAD` was already moved back so creating a new commit with `-c ORIG_HEAD` clearly expresses the intent to reuse the old message.

## 6. Limits on Shared Branches and Safe Undoing

Resetting the branch pointer alters the history published by the branch. If commits have already been pushed and teammates have based work on them, resetting and force-pushing can cause history in other clones to diverge and lose work others have pushed.

For shared commits, it is usually better to use `git revert` to create a new commit reversing the change:

```bash
git revert <commit-to-undo>
```

`revert` preserves old commits and records an additional new commit. For merge commits, identify the mainline parent with the `-m` option according to actual history; do not guess the parent.

If you reset by mistake on a local branch, the reflog usually helps find the old position:

```bash
git reflog --date=local
```

Find the entry before the reset, then create a rescue branch at the appropriate commit hash:

```bash
git branch rescue-before-reset <commit-id>
```

Creating a rescue branch keeps that commit reachable while you inspect. Only after confirming the right commit and understanding the working tree state should you decide to move the current branch. Reflog is a local log and entries can expire according to cleanup configuration; do not treat it as a long-term backup.

## 7. Practice Exercise

Create a test repository and make a commit containing two files `README.md` and `src/config.yml`. Then edit both files and stage them.

1. Run `git status` and `git diff --cached` to inspect the staged changes.
2. Edit `src/config.yml` again after staging so the file has both staged and unstaged changes.
3. Run `git reset -- src/config.yml`, then compare `git diff --cached` and `git diff` to confirm the working tree remains intact.
4. Run `git reset -p -- README.md` in the test repository to unstage one hunk.
5. Create another local commit, then test `git reset --soft HEAD~1` and `git reset --mixed HEAD~1` on separate test branches to compare the index and working tree.
6. Observe the reflog after resetting and create a rescue branch from the previous commit.

You have completed the exercise when you can explain why a pathspec reset affects only the index, whereas a commit reset can move the branch and additionally alter the index/working tree depending on the mode.

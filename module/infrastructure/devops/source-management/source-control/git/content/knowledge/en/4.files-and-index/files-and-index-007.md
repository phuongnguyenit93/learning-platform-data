# Renaming, Moving, and Deleting Files with git mv and git rm

When renaming or relocating a file already tracked by Git, you can use `git mv`. When you want to delete a file from the repository, use `git rm`. Both commands update both the working tree and the index so the operation is recorded for the next commit.

The key point to remember is that Git stores snapshots of paths and file contents. A commit does not store a separate “rename” operation. When viewing history, Git detects renames by comparing content at the old and new paths. Therefore, renaming properly keeps staging clear, while Git's ability to display it as a rename depends on the degree of content similarity.

## 1. Renaming a File with git mv

Basic syntax:

```bash
git mv <source> <destination>
```

Example renaming a file:

```bash
git mv src/old-name.js src/new-name.js
```

After the command, the file is moved in the working tree and the index is updated to record the new path. Verify:

```bash
git status --short
git diff --cached --summary
git diff --cached --find-renames
```

If Git detects content similarity, `status` typically displays a rename status, such as `R` in short format. The staged changes can be viewed with `git diff --cached`.

### Moving a File to Another Directory

You can also change the directory containing the file:

```bash
git mv src/config.yml config/config.yml
git mv docs/old-guide.md docs/guides/guide.md
```

The destination can be a new file path or an existing directory. If the destination is a directory, Git moves the file into that directory keeping its current filename. Parent directories must exist or be creatable in a way Git and the operating system support.

### Moving an Entire Directory

Git does not track empty directories as separate objects; Git tracks files and their paths in trees. When moving a directory containing tracked files:

```bash
git mv src/legacy-module src/archive/legacy-module
```

Git moves the tracked files inside that directory and updates the index. An empty directory is not preserved in a commit if there are no files inside it.

## 2. What Does git mv Do to the Index?

`git mv` is a convenience command combining a filesystem move operation with an index update. You can think of it as roughly equivalent to moving the file, staging the new path, and removing the old path from the index:

```bash
# Illustrating equivalent meaning; no need to run after git mv
mv src/old-name.js src/new-name.js
git add src/new-name.js
git rm --cached src/old-name.js
```

In practice, use `git mv` so Git performs the related steps consistently. After the command, the index records the file at the new path and removes the entry at the old path. The new file content is staged according to its state at the time of the operation.

If the file had unstaged changes before renaming, pay attention: current content may be brought into the index along with the rename. If you need to separate content changes and renaming into different commits, stage/commit the content changes according to your plan first, or carefully inspect `git diff --cached` and `git diff` after moving.

## 3. Renaming Does Not Mean Git Stores a Rename Operation

Git stores tree snapshots. A tree contains entries with names and object OIDs; after a rename, the new tree has the new path name. In the commit, Git sees the old path disappear and the new path appear.

When displaying a diff, Git can pair the deleted file with the new file based on content similarity. This is **rename detection**, not an independent rename object or metadata stored inside the commit.

Example:

```text
Previous commit:              Next commit:
src/old-name.js               src/new-name.js
blob A                        blob A or blob B
```

If the content stays identical, Git typically detects this as a 100% rename. If the file is renamed and heavily edited, similarity may be low and the diff may display as delete + add.

Explicitly instruct Git to display rename detection:

```bash
git diff --cached --find-renames
git show --summary --find-renames HEAD
```

You can set a similarity threshold, for example:

```bash
git diff --cached --find-renames=70%
```

A higher threshold requires more identical content to pair as a rename; a lower threshold allows detecting files that were edited more heavily. This affects how Git presents diffs, without changing how commits store snapshots.

## 4. Case-Only File Renaming

On some filesystems that are case-insensitive by default, especially common Windows configurations, renaming `Readme.md` to `README.md` may not be treated as two distinct paths by the filesystem.

A safe approach is using an intermediate name:

```bash
git mv Readme.md README.tmp
git mv README.tmp README.md
```

Check the filename and status again:

```bash
git status --short
git diff --cached --summary
```

If the repository uses a case-sensitive filesystem, a single-step operation can work; using an intermediate name is more predictable when collaborating across Windows, macOS, and Linux.

## 5. Common Options of git mv

| Option | Effect |
|---|---|
| `-v`, `--verbose` | Displays details of files moved |
| `-f`, `--force` | Allows overwriting the destination in cases Git permits |
| `-n`, `--dry-run` | Shows planned operations only, without executing |
| `-k` | Skips per-path errors and continues with other paths when possible |

Preview an operation:

```bash
git mv --dry-run src/old-name.js src/new-name.js
```

`--force` can overwrite the destination file. Inspect the destination file before using it; if that file holds unsaved content, overwriting can lose data. `--dry-run` is useful when renaming many files or moving a large directory tree.

## 6. Deleting Files from the Working Tree and Index with git rm

`git rm` deletes the file from the working tree and stages the deletion in the index.

Syntax:

```bash
git rm [options] -- <pathspec>...
```

Example deleting one file:

```bash
git rm src/obsolete-helper.js
```

Deleting multiple files:

```bash
git rm docs/old-api.md tests/obsolete-test.js
```

After running, the file is deleted from the working tree and the index records that the path is no longer in the next snapshot. Verify:

```bash
git status --short
git diff --cached --summary
git diff --cached
```

When committing, the deletion will be recorded in history:

```bash
git commit -m "Remove obsolete API helper"
```

## 7. Deleting Directories with git rm -r

To delete all files tracked by Git inside a directory, use `-r`:

```bash
git rm -r -- src/legacy-module
```

The command recursively deletes matching tracked files in the directory and stages the deletions. Untracked or ignored files do not automatically become managed by Git just because they sit in the same directory; inspect carefully before cleaning an entire directory with OS tools.

Before deleting many files, you can preview:

```bash
git rm -n -r -- src/legacy-module
```

`-n`/`--dry-run` lists the planned operations without deleting files or updating the index. Use dry-run when the pathspec is broad or the directory contains substantial content.

## 8. When a File Has Uncommitted Changes

If a tracked file has been modified in the working tree or index, `git rm` may refuse to delete it to prevent losing changes. Example:

```text
error: the following file has local modifications:
    src/config.yml
```

Before deciding, inspect changes in both areas:

```bash
git status --short
git diff -- src/config.yml
git diff --cached -- src/config.yml
```

If the changes need to be kept, commit or back them up first. If you have confirmed you want to delete the file along with its local changes, you can use `-f`:

```bash
git rm -f -- src/config.yml
```

`-f` (force) bypasses safety checks regarding differences between `HEAD`, the index, and the working tree. This operation can lose content not saved elsewhere; do not use it merely to force the command through without reading the diff.

## 9. Untracking a File While Keeping It Locally with git rm --cached

If a file was committed in the past but you no longer want Git to track it going forward while still needing to keep the local copy, use `--cached`:

```bash
git rm --cached -- config/local.yml
```

This command removes the entry from the index while keeping the file in the working tree. When committed, the repository records the file as deleted; on your machine, the file remains and typically appears as untracked (unless ignored).

A common case is machine-specific configuration files. After untracking, add an appropriate rule to `.gitignore`:

```gitignore
config/local.yml
```

Then stage `.gitignore` and commit both changes:

```bash
git add .gitignore
git status --short
git commit -m "Stop tracking local configuration"
```

Note: `git rm --cached` only stops tracking in future commits. If the file ever contained passwords, tokens, or private keys, the old content remains in Git history. You must revoke/rotate secrets and clean history per security procedures; adding `.gitignore` does not delete already-committed data.

## 10. Useful Options of git rm

| Option | Effect |
|---|---|
| `-r` | Recursively deletes tracked files in a directory |
| `-f`, `--force` | Bypasses safety checks when the file has changes |
| `--cached` | Removes from index only, keeping the file in the working tree |
| `-n`, `--dry-run` | Previews paths that would be deleted |
| `-q`, `--quiet` | Suppresses output messages |
| `--ignore-unmatch` | Does not report an error if the pathspec matches no tracked files |

Example:

```bash
git rm --dry-run -r -- generated/
git rm --cached -- .env.local
```

Use `--ignore-unmatch` in scripts when having no matching files is an acceptable case. In manual operations, a mismatch error is usually a signal to double-check the path.

## 11. How Does Deleting via the Filesystem Differ from git rm?

You can delete a file with Explorer, Finder, `rm`, or `del`. In that case, the working tree changes while the index has not been updated yet. `git status` reports the tracked file as deleted but unstaged.

Example:

```bash
rm src/obsolete-helper.js
git status --short
```

To stage the deletion after deleting via the filesystem:

```bash
git add -u -- src/obsolete-helper.js
```

Or stage all tracked changes:

```bash
git add -u
```

`git rm` combines deleting on the filesystem and updating the index in one command, so intent is usually clearer. Either way, Git still stores snapshots in commits; it does not record a separate deletion log outside tree changes.

Do not use `git clean` as a substitute for `git rm` when deleting tracked files. `git clean` cleans untracked files (and potentially ignored files with appropriate flags), whereas `git rm` handles paths tracked in the index.

## 12. Viewing History After Rename or Delete

Because Git detects renames by comparing content, you can view operation summaries with:

```bash
git diff --cached --summary --find-renames
git show --summary --find-renames HEAD
```

To follow a file's history across renames, use `--follow`:

```bash
git log --follow --oneline -- src/new-name.js
```

`--follow` traces a file's history backward across renames detected by Git. This option applies to a single path and has limitations with complex merge histories. If Git cannot detect a rename because content changed too much, history may not link across as expected.

To find the commit that deleted a file:

```bash
git log --all --diff-filter=D --summary -- src/obsolete-helper.js
```

This command finds commits that contain a deletion change for that path. If the file was deleted on the current branch but still existed in an earlier commit, you can view old content with:

```bash
git show HEAD~1:src/obsolete-helper.js
```

Replace `HEAD~1` with the appropriate commit found in history.

## 13. Undoing Operations Before Committing

If you just staged a deletion with `git rm` and have not committed yet, you can restore the index from `HEAD`:

```bash
git restore --staged -- src/obsolete-helper.js
```

This command unstages the deletion; the file is still missing from the working tree. To restore the file on disk from the index:

```bash
git restore --worktree -- src/obsolete-helper.js
```

If the deletion was already committed and you want to reverse it on a shared branch, the safe approach is typically creating a new commit with `git revert`:

```bash
git revert <DELETE_COMMIT>
```

If you need to retrieve the file from a specific commit, you can restore the path from that commit and commit again:

```bash
git restore --source=<COMMIT_ID> --worktree -- src/obsolete-helper.js
git add src/obsolete-helper.js
git commit -m "Restore obsolete helper"
```

Verify the exact source commit before writing the file to avoid accidentally replacing the current version with old content.

## 14. Practical Workflow: Renaming, Moving, and Deleting Files

Suppose you need to reorganize a module in the project:

```bash
# Rename file
git mv src/old-service.js src/payment-service.js

# Move documentation
git mv docs/old-api.md docs/api/guide.md

# Delete unused file
git rm src/legacy-adapter.js

# Check status and staged diff
git status --short
git diff --cached --summary --find-renames
git diff --cached
```

If the result is right, create the commit:

```bash
git commit -m "Reorganize payment module files"
```

If a config file needs to stay local but no longer be tracked:

```bash
git rm --cached -- config/local.yml
```

Then add the file to `.gitignore` and commit the ignore change along with untracking it.

## 15. Practice Exercises

In a test repository, create an initial commit containing `src/old-name.js`, `docs/old-guide.md`, and `config/local.yml`.

1. Use `git mv` to rename `src/old-name.js` to `src/new-name.js`; verify with `git status --short` and `git diff --cached --summary`.
2. Use `git mv` to move the document into `docs/guides/guide.md`; confirm the index records the new path.
3. Edit the file content after renaming, then use `git diff --cached` and `git diff` to distinguish staged parts from unstaged parts.
4. Use `git rm` to delete a tracked file and verify the deletion is staged.
5. Try `git rm --cached config/local.yml`, confirm the file stays on disk and is no longer tracked by the index; add a rule to `.gitignore`.
6. On a suitable filesystem environment, try a case-only rename through an intermediate name.
7. Commit the changes, then use `git log --follow --oneline -- src/new-name.js` to view history across the rename.
8. Explain why Git detects renames based on content instead of storing a separate rename operation.

You have completed the exercises when you know how to use `git mv` to rename/move, `git rm` to delete, and `git rm --cached` to untrack while keeping the local file; and can verify staged content before committing.

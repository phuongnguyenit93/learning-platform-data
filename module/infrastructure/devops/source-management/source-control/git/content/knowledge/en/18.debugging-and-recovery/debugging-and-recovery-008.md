# Restoring a File or Directory from a Previous Version

When a file is edited incorrectly, deleted by mistake, or needs content brought back from an older commit, you do not necessarily have to roll back the entire branch. `git restore` lets you pick a specific file or directory and retrieve its content from `HEAD`, the index, or a specific commit. The key is identifying the exact source and target before running the command, because restoring can overwrite existing changes in the working tree or index.

## 1. Understanding the Three Places Git Can Retrieve Content From

A file in a repository can have different content in three places:

- **HEAD**: the current commit the branch points to.
- **Index (staging area)**: the staged version that will go into the next commit.
- **Working tree**: the file on disk that you open and edit.

`git restore` can take content from one of these sources to update a file or the index. If no source is specified, Git uses a default that depends on the restoration target:

| Command | Default Source | What Gets Updated |
|---|---|---|
| `git restore --worktree -- file` | Index | Working tree |
| `git restore --staged -- file` | `HEAD` | Index |
| `git restore --source=<commit> --worktree -- file` | Specified commit | Working tree |
| `git restore --source=<commit> --staged --worktree -- file` | Specified commit | Index and working tree |

If neither `--staged` nor `--worktree` is specified, Git restores only the working tree by default. Specify the flags explicitly when operating on important files to avoid confusion.

## 2. Checking Status Before Restoring

Before running the command, check the current branch and existing changes:

```bash
git status --short
git diff -- path/to/file
git diff --cached -- path/to/file
```

- `git status --short` shows which files are modified, staged, deleted, or untracked.
- `git diff -- path/to/file` shows changes in the working tree compared to the index.
- `git diff --cached -- path/to/file` shows staged changes compared to `HEAD`.

If the current content is valuable, commit, stash, or back it up to a safe location before restoring. `git restore` does not automatically save a backup of the content it overwrites. In particular, uncommitted edits cannot always be recovered via reflog.

## 3. Restoring a File to the Version in HEAD

If you edited a tracked file in the working tree without staging it and want to discard those edits, you can use:

```bash
git restore --worktree -- src/main/ReportService.java
```

Git takes the content from the index and writes it to the working tree. When the index has no staged changes, that content normally matches `HEAD`.

If you want to restore the index to `HEAD` to unstage the file:

```bash
git restore --staged -- src/main/ReportService.java
```

This command sets the version in the index back to `HEAD`, while leaving the working tree content untouched. If the file was modified earlier, those changes will now appear as unstaged.

If you want both the index and working tree to return to the content in `HEAD`:

```bash
git restore --source=HEAD --staged --worktree -- src/main/ReportService.java
```

This last command can discard both staged and unstaged changes to the file. Run it only after confirming that you truly want to discard all current changes at that path.

## 4. Restoring a File from an Older Commit

When you need the version from a specific commit, use `--source` to pick the source:

```bash
git restore --source=<commit> --worktree -- src/main/ReportService.java
```

Replace `<commit>` with a verified hash, tag, or commit expression, such as `a1b2c3d` or `HEAD~2`. The command brings the file's content at that commit into the current working tree. By default, the index is not updated; if you want to stage the older version right away, add `--staged`.

Example restoring the version of the file from two commits ago:

```bash
git restore --source=HEAD~2 --worktree -- src/main/ReportService.java
```

After this command, the file in the working tree has the content from `HEAD~2`, while the current branch still points to the latest current commit. No new commit is created automatically.

If you want to turn the old version into a staged change ready to commit:

```bash
git restore --source=HEAD~2 --staged --worktree -- src/main/ReportService.java
git diff --cached -- src/main/ReportService.java
```

After inspecting the diff and running tests, you can create a new commit to record bringing the file back to the previous version. This approach preserves existing history and records the restoration as a new change.

## 5. Finding the Commit Containing the Needed Version

If you do not yet know the commit hash, inspect the file's history:

```bash
git log --oneline -- src/main/ReportService.java
```

If the file was ever renamed and you want to follow history across renames, use:

```bash
git log --oneline --follow -- src/main/ReportService.java
```

`--follow` works for a single file path when Git detects a rename operation. If the commit you are looking for is not in the current branch's history, you can broaden the search scope:

```bash
git log --oneline --all --follow -- src/main/ReportService.java
```

After choosing a commit, inspect the file content at that commit before overwriting the current version:

```bash
git show <commit>:src/main/ReportService.java
```

This command only prints the content in the terminal; it does not modify the working tree or index. If the file did not exist at the chosen commit, Git reports that the path was not found in that commit's tree.

## 6. Restoring an Entire Directory

`git restore` also accepts a directory pathspec. For example, retrieving tracked files under `src/main/report/` from an older commit:

```bash
git restore --source=<commit> --worktree -- src/main/report/
```

Add `--staged` if you want the index to also reflect the version from the source commit:

```bash
git restore --source=<commit> --staged --worktree -- src/main/report/
```

A directory path ending with `/` clarifies the scope. You can use a more specific pathspec if you only want to restore part of a directory. For example:

```bash
git restore --source=<commit> --worktree -- 'src/main/report/*.java'
```

Pathspecs are interpreted according to Git's pathspec rules, which do not always match shell wildcards. Use quotes when needed to prevent the shell from expanding characters before Git receives the argument.

Restoring a directory can affect many files at once. Before running it, inspect the file list and diff in the source commit. Do not use an overly broad pathspec like `.` if your goal is only to fix a few files.

## 7. Restoring a Deleted File

If a tracked file was deleted from the working tree and the deletion has not been staged, you can restore it from the index:

```bash
git restore --worktree -- src/main/ReportService.java
```

If the deletion has already been staged, the index no longer has the file version either. In that case, restoring only the working tree from the index will not retrieve the content. Retrieve both the index and working tree from `HEAD`:

```bash
git restore --source=HEAD --staged --worktree -- src/main/ReportService.java
```

If you want to retrieve the file from another older commit:

```bash
git restore --source=<commit> --staged --worktree -- src/main/ReportService.java
```

If the file was already deleted in the current commit but existed in an older commit, verify the path in the source commit using `git show <commit>:<path>` before restoring.

## 8. Restoring a Renamed or Moved File

Git stores a snapshot of the directory tree at each commit; rename information is usually inferred when comparing snapshots. Therefore, a renamed file may appear under its old path in an earlier commit and under its new path in the current commit.

To trace history across a rename:

```bash
git log --follow --oneline -- path/to/new-name.java
```

Once you find the commit that still contains the old path, inspect its content using the path at that commit:

```bash
git show <commit>:path/to/old-name.java
```

If you want to bring that content into the current path, use `git restore` with the corresponding pathspec in the source commit. When the old and new paths differ, be explicit about which filename you want to restore under. You can inspect the content beforehand with `git show`, then create a new file or adjust paths intentionally.

Do not assume Git automatically infers a rename intent when you pass a path that does not exist in the source commit. Verify the filename at each point in time before restoring.

## 9. Does Restoring Create a New Commit?

`git restore` only updates the index and/or working tree; it does not create a commit automatically. After restoring an older version, inspect the changes:

```bash
git status --short
git diff
git diff --cached
```

If you need to record the restoration in history, stage the exact file and create a commit:

```bash
git add src/main/ReportService.java
git diff --cached
git commit -m "Restore report service implementation"
```

The new commit records the restored content on top of current history. This is usually the right approach when changes have already been shared and you want everyone to receive the restoration via pull or fetch.

If you are only testing locally and do not want to commit yet, you can keep the changes in the working tree or index. Keep in mind that they can still be overwritten by other operations later.

## 10. Comparing `git restore` with Legacy Checkout Syntax

Before `git restore` existed, many guides used:

```bash
git checkout <commit> -- path/to/file
```

This syntax can still be encountered in older repositories or documentation. It typically updates both the index and working tree for the path from the specified commit. `git restore` clearly separates what to update using `--staged` and `--worktree`, making it easier to read and less likely to be confused with branch switching.

| Need | Explicit Usage with `git restore` |
|---|---|
| Discard unstaged edits, take from index | `git restore --worktree -- file` |
| Unstage, keep edits in working tree | `git restore --staged -- file` |
| Retrieve old commit version into working tree | `git restore --source=<commit> --worktree -- file` |
| Retrieve old commit version into both index and working tree | `git restore --source=<commit> --staged --worktree -- file` |

Do not confuse `git restore` with `git switch` or `git checkout <branch>`. The switch/checkout branch commands change the branch or HEAD position; restore replaces the content of selected paths.

## 11. What Git Cannot Recover with Restore

`git restore` can only retrieve content that already exists in the Git source you specify. It cannot recover on its own:

- New files that were never committed or saved in a stash.
- Uncommitted edits that were overwritten and are no longer in the index, a stash, or any other copy.
- Files deleted before Git ever tracked them.
- Runtime data or data outside the repository, such as databases, uploaded files, or cloud resources.

Untracked files have no version in a commit for Git to restore. If a new file was deleted by mistake, check backups, IDE local history, or OS file recovery tools. If the file was previously stashed, locate the matching stash and recover from there.

Reflog records movements of refs such as `HEAD` and branches; it is not a log of every file edit. If uncommitted content was overwritten, reflog usually cannot restore that content.

## 12. Safe Workflow Before Restoring

Before a restore operation, follow these steps in order:

1. **Identify the exact path.** Check filename, directory, and tracked/untracked status.
2. **Choose the exact source.** Decide whether to take from index, `HEAD`, a tag, or a specific commit.
3. **Preview the source content.** Use `git show <commit>:<path>` to read it before overwriting.
4. **Preserve current changes.** Commit, stash, or back up any content you do not want to lose.
5. **Select the restore target.** Use `--worktree`, `--staged`, or both according to your goal.
6. **Limit the pathspec.** Restore only the necessary file or directory.
7. **Inspect after the operation.** Use `git status`, `git diff`, `git diff --cached`, and relevant tests.
8. **Commit if sharing is needed.** Create a new commit so everyone receives the restored change through normal history.

Complete example: retrieving an older version of a file, inspecting it, and creating a restore commit:

```bash
git status --short
git log --oneline --follow -- src/main/ReportService.java
git show <commit>:src/main/ReportService.java
git restore --source=<commit> --worktree -- src/main/ReportService.java
git diff -- src/main/ReportService.java
git add src/main/ReportService.java
git diff --cached -- src/main/ReportService.java
git commit -m "Restore report service from previous version"
```

Replace `<commit>` with a verified commit. If you also want the index updated immediately from that source, add `--staged` to the restore command and still inspect the staged diff before committing.

## 13. Takeaways

`git restore` helps retrieve a single file or directory without rolling back an entire branch. Distinguish among `HEAD`, index, and older commit sources; explicitly choose whether to update the working tree, index, or both; scope the pathspec properly; and preview source content first. The command does not create a commit automatically and cannot recover data that Git never stored. For shared changes, commit the restored result as a new change to keep collaborative history consistent.

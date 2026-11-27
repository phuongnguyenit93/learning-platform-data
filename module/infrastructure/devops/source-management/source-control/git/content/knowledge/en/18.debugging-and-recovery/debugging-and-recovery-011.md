# Recovery Limits for Data Never Added or Committed

Git can help you recover many lost changes, but Git is not a backup tool for every file on your machine. Git only manages content that has been placed into the repository through commits, staging, or storage operations like stashing. A new file that was never staged with `git add`, never stashed, and never appeared in any commit normally has no copy in Git's data.

This is a critical limitation when handling incidents. If an untracked file is deleted, `git restore`, `git reset`, `git checkout`, `git reflog`, and `git fsck` cannot reconstruct content Git never stored. You will need to look for a copy in your IDE, operating system, sync service, or another backup.

## 1. What Does Git Store and What Does It Not Store?

Git tracks content through objects in the object database and references in the repository. `git add` puts the contents of a tracked or new file into the index; when creating a commit, Git saves a snapshot of the index as a commit. Stash operations also save changes as Git objects so they can be reapplied later.

| File Status | Does Git Have Content to Recover? | Possible Recovery Sources |
|---|---|---|
| Already in a commit | Yes | Commit, branch, tag, or reflog still holding the commit |
| Already run `git add` and currently in index | Yes | Index; can be restored from the index |
| Previously run `git add`, later unstaged, blob not yet cleaned | Possibly | Dangling blob in the object database, if it still exists |
| Editing a tracked file without staging | Has original in commit/index; new edits may not be stored by Git | Can retrieve the original; unstaged edits require another source if lost |
| Untracked file never added or stashed | No | IDE, operating system, sync service, or backup |
| Ignored file never added or stashed | No | IDE, operating system, sync service, or backup |

Git stores snapshots; it does not automatically record every keystroke. Therefore, for tracked files, Git can restore committed or indexed versions, but not necessarily the latest characters that were never staged. For untracked files never saved to Git, the repository has no data to rebuild them.

## 2. Distinguishing Tracked, Untracked, and Ignored

Before recovering, check whether Git knows about the file:

```bash
git status --short --untracked-files=all
git ls-files -- src/config.yml
git check-ignore -v local.env
```

- **Tracked**: a file already added to the index or appearing in Git history. Git knows its path and may have snapshots for recovery.
- **Untracked**: a file existing in the working tree that is not yet tracked by the index. Git can list the file, but does not store its contents.
- **Ignored**: a file excluded from normal status by ignore rules. Git does not include that file in commits or default stashes.

`git status --short --untracked-files=all` lets you see individual untracked files inside directories. `git check-ignore -v` shows which rule is ignoring a path. An ignored file can still be added by specifying its path explicitly, yet if it has never been added, Git holds no snapshot of it.

Do not confuse Git displaying an untracked file's name with Git having saved the file's content. Untracked status simply means the file exists in the working tree and is not managed by the index.

## 3. Recovering a File Previously Tracked by Git

If the file is already in a commit, you can retrieve its version from the current commit. For example, file `src/config.yml` was deleted from the working tree yet still exists in `HEAD`:

```bash
git status
git restore --source=HEAD --worktree -- src/config.yml
```

This command restores content from `HEAD` into the working tree. If the file was staged with different content, check the index before picking a recovery source. To retrieve the currently staged version, you can use:

```bash
git restore --worktree -- src/config.yml
```

Do not use these commands to recover an untracked file that was never added: there is no version in `HEAD` or the index for Git to pull from.

If you need to retrieve a file from an older commit:

```bash
git log --all --oneline -- src/config.yml
git restore --source=<COMMIT_ID> --worktree -- src/config.yml
```

The first command finds commits with changes related to the path. The second restores the file according to the selected commit's snapshot. Verify the exact commit and path before overwriting current contents.

## 4. When a File Has Been `git add`ed but Not Committed

`git add` does not merely mark a file in the staging area; Git also writes the file's content as a blob object in the object database and stores the blob ID in the index. If a file was staged and then deleted from the working tree, you can restore it from the index:

```bash
git status
git restore --worktree -- src/new-report.md
```

This command takes the content currently in the index and writes the file back into the working tree. If the index still holds the version you want to keep, this is a direct recovery path.

If you already unstaged it with `git reset` or replaced the index entry with another version, the old blob may no longer be referenced by the index or any commit. However, the blob data may still exist in the object database for a period before Git cleans up garbage.

In that case, you can try looking for unreferenced objects:

```bash
git fsck --full --no-reflogs --unreachable
```

If the output includes `unreachable blob <OBJECT_ID>` or `dangling blob <OBJECT_ID>`, inspect its content with:

```bash
git cat-file -p <OBJECT_ID>
```

Or instruct Git to write dangling objects into the `lost-found` directory inside repository metadata:

```bash
git fsck --full --lost-found
```

Found blobs typically lack their original filename or path. You must read the contents to determine which blob corresponds to the file needing recovery. Results are not guaranteed either: the object may already have been deleted by garbage collection, or the blob may never have been created.

One note: `git add -N <file>` (intent-to-add) primarily records the intent to add a path so diffs can show its contents. Do not treat that operation as proof that the file's entire contents were written as a recoverable blob.

## 5. Untracked Files Never Added or Stashed

This is the case where Git cannot recover the content. For example:

```bash
git status --short
# ?? notes/draft.md
```

File `notes/draft.md` exists but has not been added. If you delete the file using a file manager, shell command, or cleanup tool, Git has no blob or commit containing its content to restore.

The following commands cannot reconstruct the contents of a file never stored in Git:

- `git restore` retrieves content from the index or a commit.
- `git reset` updates the index and/or moves commit references.
- `git checkout` retrieves a version from a commit or switches branches.
- `git reflog` records movements of references such as `HEAD` and branches, not the edit history of untracked files.
- `git fsck` inspects the object database; it does not scan the disk for content never written into Git.

If the file has already been deleted, look for copies outside Git. Depending on your setup, sources may include:

- **IDE/editor**: Local History, Timeline, JetBrains Local History, file history, or auto-saved drafts.
- **Operating system**: Recycle Bin/Trash, File History, Previous Versions, or disk snapshots.
- **Sync services**: version history in OneDrive, Dropbox, Google Drive, or enterprise storage systems.
- **Backups**: periodic backups, VM snapshots, project folder copies, or device backups.
- **Data recovery**: filesystem deleted-file recovery tools, if the data has not been overwritten; on SSDs, TRIM can significantly reduce recovery chances.

If the file was just deleted from disk and holds critical value, minimize writing additional data to the same drive before attempting recovery. Any new write can overwrite the old storage blocks. Recoverability depends on the filesystem, hardware, and sync mechanisms; there is no guarantee of success.

## 6. Ignored Files and Stash Limitations

Ignored files are not stored by Git by default either. For example, `.env.local`, build artifacts, or machine-specific configuration are commonly placed in `.gitignore` to avoid accidental commits. If such a file was never added or stashed, Git cannot recover its content once deleted.

Before an incident occurs, if you want to temporarily set aside untracked files, use:

```bash
git stash push -u -m "WIP: include new test"
```

If you need to stash ignored files as well:

```bash
git stash push -a -m "WIP: include local config"
```

`-u` includes untracked files; `-a` includes both untracked and ignored files. The stash must be created before the file is lost. If the file was already deleted beforehand, a stash command cannot recreate its contents.

For files containing secrets such as tokens, passwords, or private keys, do not use stashes or commits as a general storage vault. Use a secret manager or an organization-approved secure backup mechanism.

## 7. Being Careful with Reset and Clean

`git reset --hard` brings the index and working tree of tracked files back to the target commit. It is not a command for cleaning all untracked files, yet an untracked file standing in the way of writing a tracked file can be overwritten/deleted during the update.

`git clean` is the command specifically for cleaning untracked files. Always preview the list before deleting:

```bash
git clean -nd
```

`-n` is dry-run, `-d` includes untracked directories. To view ignored files as well:

```bash
git clean -ndx
```

`-x` includes ignored files. `-X` targets only ignored files:

```bash
git clean -ndX
```

Only after carefully inspecting the dry-run output should you consider an actual deletion command like `git clean -fd`. This deletion command does not send files to the Recycle Bin in the normal way and can lose content not stored in Git. Do not run `git clean -fdx` in a repository containing local data you need to keep.

## 8. Workflow When Discovering a Missing File

When a file disappears, check in sequence to avoid making recovery harder:

1. **Stop overwriting or cleanup operations.** Do not run further `git clean`, resets, or file-deletion scripts before understanding the cause.
2. **Determine status before the loss.** Use `git status --short --untracked-files=all`, `git ls-files -- <path>`, and `git check-ignore -v <path>` if the file still exists or to check how Git manages that path.
3. **Check Git history.** Search for the file in `git log --all -- <path>` and check the index if the file was ever staged.
4. **Search related stashes or commits.** Inspect `git stash list`, branches, tags, and reflog if you suspect the content was saved through those operations.
5. **Try searching for dangling objects if the file was ever added.** Run `git fsck` and inspect remaining blobs.
6. **If the file was never saved by Git, check external sources.** Check IDE Local History, Trash/Recycle Bin, sync service version history, and backups.
7. **After recovering, save a safe copy.** Inspect the contents, then add/commit or store in an appropriate backup for that data type.

Example checking a path:

```bash
git status --short --untracked-files=all
git ls-files -- notes/draft.md
git log --all --oneline -- notes/draft.md
git stash list
```

If both `git ls-files` and `git log` show nothing for the path, that does not strictly prove the file never existed in Git at some other point, yet it indicates there is no easily accessible version in the index or current history. If the file was never added/stashed in any state, move to recovery sources outside Git.

## 9. Preventing Loss of Data Not Managed by Git

- **Commit in small milestones.** Once a piece of work is stable, create a commit so you have an accessible snapshot.
- **Stage early when appropriate.** `git add` writes blobs into the object database and creates an index entry. This lets Git hold staged contents, though it still does not replace backups.
- **Stash untracked files before switching tasks.** Use `git stash push -u` if you need to keep new untracked files.
- **Preview before cleaning.** Run `git clean -n` or `git clean -ndx` to preview; carefully read the paths that will be affected.
- **Back up ignored files.** Local files, configuration files, and generated data may require separate backups per project policy.
- **Enable file history in your IDE or OS.** Local history and version history features help recover changes Git has never seen.
- **Do not treat Git as your only backup.** Git stores the history of source code placed into the repository; it does not automatically protect all data on disk.

## 10. Practice Exercise

In a test repository, create one tracked file, one untracked file, and one ignored file. Use dummy content, not sensitive data.

1. Commit the tracked file, edit it without staging, then delete the file from the working tree. Restore the committed version with `git restore --source=HEAD --worktree -- <file>` and note that the unstaged edits are not present in the restored version.
2. Create a new file, `git add` it, then delete it from the working tree. Restore the staged contents using `git restore --worktree -- <file>`.
3. Create another untracked file without adding it. Delete the file using the file manager in your test environment and verify whether Git can recover its contents.
4. Use `git stash push -u` on another untracked file and observe that the file is saved because a stash operation stored it.
5. Run `git clean -nd` and `git clean -ndx` to compare the lists of untracked and ignored files that would be deleted.
6. Explain why `git reflog` cannot recover a file that was never added, stashed, or committed.

You complete the exercise when you can distinguish data stored by Git from data existing only in the working tree, know when `git fsck` can help, and identify recovery sources outside Git when a file was never saved into the repository.

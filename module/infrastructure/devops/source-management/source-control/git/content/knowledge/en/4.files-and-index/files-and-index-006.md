# Restoring Uncommitted Changes with `git restore` and Scope of Data Loss

When you edit the wrong file, stage the wrong content, or delete a path, you can use `git restore` to return a file or the index to a known version. This command is very useful because it lets you explicitly choose where to restore: the working tree, the staging area, or both. However, restore can overwrite uncommitted content. Before running it, identify where the version currently lives, what source you want to pull from, and what pathspec scope will be affected.

## 1. Three States to Distinguish Before Restoring

Git works with three main states of a file:

| State | Role | Common Command to Inspect |
|---|---|---|
| `HEAD` | Snapshot of the current commit | `git show HEAD:path/to/file` |
| Index (staging area) | Version that will go into the next commit | `git diff --cached -- path/to/file` |
| Working tree | Current file content on disk | `git diff -- path/to/file` |

A single file can hold three different contents simultaneously. For example, you stage a change and then continue editing the file without re-staging. In that case:

- `HEAD` is still the version in the latest commit.
- The index holds the version staged the first time.
- The working tree holds the newest version on disk.

`git commit` takes content from the index. Therefore, when planning a restore, do not look only at the file open in your editor; check both staged and unstaged changes.

## 2. Checking Before Running `git restore`

Start with overall status:

```bash
git status --short
```

View unstaged changes:

```bash
git diff -- path/to/file
```

View staged changes:

```bash
git diff --cached -- path/to/file
```

If you need to view the committed version:

```bash
git show HEAD:path/to/file
```

For important files, save a copy outside the repository, commit the work you want to keep, or stash before restoring. One way to stash both tracked changes and untracked files is:

```bash
git stash push -u -m "Backup before restoring files"
```

`-u` includes untracked files but does not include ignored files. If you need to save ignored files as well, `git stash push -a` has a broader scope; inspect carefully because it can sweep up caches and large local data.

## 3. Default Sources of `git restore`

`git restore` reads content from a *source* and writes it to a *destination*. If `--source` is not specified, the default source depends on the destination:

| Command | Default Source | Updated Destination |
|---|---|---|
| `git restore --worktree -- file` | Index | Working tree |
| `git restore --staged -- file` | `HEAD` | Index |
| `git restore --source=<commit> --worktree -- file` | Specified commit | Working tree |
| `git restore --source=<commit> --staged -- file` | Specified commit | Index |
| `git restore --source=<commit> --staged --worktree -- file` | Specified commit | Index and working tree |

If `--staged` is omitted, Git defaults to updating the working tree. When `--staged` is present, the default source is `HEAD`. Explicitly specifying `--source` and the destinations to update makes the command easier to read, especially when an operation risks losing changes.

`--` separates Git options from the pathspec. You should use it when specifying files so filenames cannot be misinterpreted as options:

```bash
git restore --worktree -- src/main/App.java
```

## 4. Discarding Unstaged Changes in the Working Tree

Suppose you edited `src/main/App.java` without running `git add`. To discard those edits and retrieve content from the index:

```bash
git restore --worktree -- src/main/App.java
```

This command updates only the working tree. The index remains untouched. If the file has no staged changes, the content in the index normally matches `HEAD`; in that case, the file returns to the current commit version.

Check after restoring:

```bash
git diff -- src/main/App.java
git status --short
```

If no unstaged changes remain for that file, `git diff` displays no differences. Other files in the repository are unaffected because the pathspec specifies only one file.

## 5. Unstaging While Keeping Edited Content

If you ran `git add` but want to pull changes out of the staging area to continue editing, use:

```bash
git restore --staged -- src/main/App.java
```

The command takes the version from `HEAD` and updates the index. The working tree is not overwritten, so your edited file content remains on disk and becomes an unstaged change.

Check:

```bash
git diff --cached -- src/main/App.java
git diff -- src/main/App.java
```

After unstaging, the staged diff is typically empty; the working tree diff shows the preserved edits. This is the right approach when you staged the wrong file or want to split one commit into multiple parts.

## 6. Discarding Both Staged and Unstaged Changes of a File

If you want the file to return to the exact version in the current commit regardless of how the index and working tree differ, explicitly specify the source and both destinations:

```bash
git restore --source=HEAD --staged --worktree -- src/main/App.java
```

This command updates both the index and the working tree from `HEAD`. Both staged and unstaged changes for that path will be replaced. Other files outside the pathspec remain intact.

Before running it, inspect both diffs:

```bash
git diff -- src/main/App.java
git diff --cached -- src/main/App.java
```

After running, check again:

```bash
git status --short -- src/main/App.java
```

Do not use this command if you only want to unstage while keeping edits in the working tree; in that case use `git restore --staged -- file`.

## 7. Restoring a File Deleted from the Working Tree

If a tracked file was deleted from disk but the deletion has not been staged, the index still holds the file content. Restore from the index:

```bash
git restore --worktree -- src/main/App.java
```

Git recreates the file in the working tree according to the index version. This is a simple way to recover a tracked file deleted by mistake.

Check status before running to see whether the deletion has already been staged:

```bash
git status --short
```

The symbol ` D` typically indicates a file deleted in the working tree but not yet staged; `D ` indicates the deletion has been staged. Leading spaces and character positions matter greatly in short status output.

## 8. Restoring a Deleted File Whose Deletion Was Staged

If a file was deleted and you ran `git add -u` or staged the deletion, the index no longer has an entry for the file either. In that case, `git restore --worktree -- file` pulling from the index will not restore the desired content.

Reset both the index and working tree to the version in `HEAD`:

```bash
git restore --source=HEAD --staged --worktree -- src/main/App.java
```

If you only want to unstage the deletion first, use:

```bash
git restore --staged -- src/main/App.java
```

This command brings the entry back into the index from `HEAD`, while the file on disk remains deleted. Then restore the working tree from the index:

```bash
git restore --worktree -- src/main/App.java
```

Two steps make the effects clear: the first restores the index, the second recreates the file. If your end goal is discarding all changes to the file, the combined command at the start of this section is shorter.

## 9. Reverting a Newly Staged File

Suppose `notes.txt` never existed in `HEAD`, and you created the file and ran `git add notes.txt`. If you want to unstage it while keeping the file content:

```bash
git restore --staged -- notes.txt
```

Because `HEAD` does not have this path, the entry is removed from the index. The file stays in the working tree and typically reappears as untracked.

If you want to remove the newly staged file from both the index and the working tree, you can use:

```bash
git restore --source=HEAD --staged --worktree -- notes.txt
```

Because the path does not exist in the `HEAD` source, Git removes the path from both destinations. Confirm the file does not contain data you need to keep before running this.

## 10. Restoring from an Older Commit or Tag

You can pull file content from an older commit without moving the current branch. For example, bring the version from two commits ago into the working tree:

```bash
git restore --source=HEAD~2 --worktree -- src/main/App.java
```

The index is unchanged; the working tree gets the content from `HEAD~2`. Git treats this as a modification compared to the current index. You can review it and decide whether to stage or keep editing.

To pull the old version into both the index and the working tree:

```bash
git restore --source=HEAD~2 --staged --worktree -- src/main/App.java
```

Then view the content about to be committed:

```bash
git diff --cached -- src/main/App.java
```

If you want to record the restoration as a new commit, run tests, review the diff, and commit. Branch history still moves forward; Git does not move `HEAD` back to the old commit.

You can use a tag or commit hash as the source:

```bash
git restore --source=v1.4.0 --worktree -- config/default.yml
```

Verify that the commit/tag and path exist in the source snapshot before restoring. If the source lacks the specified path, the operation may remove that path from the corresponding restore destination.

## 11. Restoring an Entire Directory or Multiple Paths

`git restore` accepts files, directories, or multiple paths as pathspecs. For example, restore all tracked files under `src/generated/` from `HEAD`:

```bash
git restore --source=HEAD --worktree -- src/generated/
```

To update both the index and the working tree:

```bash
git restore --source=HEAD --staged --worktree -- src/generated/
```

You can pass multiple paths:

```bash
git restore --worktree -- README.md src/main/App.java config/default.yml
```

Pathspecs are interpreted relative to the current directory inside the repository by default. If you want to specify explicitly from the repository root, use the `:(top)` pathspec magic:

```bash
git restore --worktree -- ':(top)src/main/App.java'
```

Quote pathspecs when they contain wildcard characters so the shell does not expand them before Git receives them. Check the scope carefully before using broad pathspecs like `.` or `:(top)**`.

## 12. Restoring Partially with Interactive Mode

You do not always want to discard all changes in a file. The `-p` (or `--patch`) option lets you pick individual hunks to restore.

Discard selected unstaged hunks in the working tree, pulling corresponding content from the index:

```bash
git restore -p --worktree -- src/main/App.java
```

Unstage selected hunks, pulling corresponding content from `HEAD` into the index:

```bash
git restore -p --staged -- src/main/App.java
```

Git shows each block of changes and asks whether you want to restore that part. Read each hunk carefully before deciding. For files with complex interleaved edits, manual editing may be needed after restoring.

`git restore -p` is a useful option when a file contains both parts to keep and parts to discard. If you need to split changes into small commits, combine `git add -p` to stage hunk by hunk and `git restore -p --staged` to send mistakenly staged parts back.

## 13. Restoring One Side When a File Is Conflicted

During a merge, rebase, or cherry-pick, the index can hold multiple stages for the same path:

| Stage | Meaning |
|---|---|
| 1 | Common base version, if present |
| 2 | `ours` side version |
| 3 | `theirs` side version |

If you want to take the entire `ours` version into the working tree:

```bash
git restore --ours --worktree -- path/to/conflicted-file
```

Or take the `theirs` version:

```bash
git restore --theirs --worktree -- path/to/conflicted-file
```

These two options apply only to paths in an unmerged state and cannot be combined with `--source`. After selecting a side, the file in the working tree no longer has conflict markers for that side's content, though the index still needs to be marked resolved:

```bash
git add path/to/conflicted-file
git status
```

Note: during a rebase, how Git names `ours` and `theirs` can feel counterintuitive when thinking in terms of feature branch vs. target branch. Check `git status`, the stages, and the content of each side before choosing. If you need to view the base, read stage 1 with:

```bash
git show :1:path/to/conflicted-file
```

If you need to cancel the entire merge/rebase operation rather than picking a side, use the appropriate abort command (`git merge --abort` or `git rebase --abort`) after checking status.

## 14. Data Loss Scope of Each Command

The most important thing when using restore is understanding which destination gets overwritten:

| Command | What Can Be Lost? | What Is Preserved? |
|---|---|---|
| `git restore --worktree -- file` | Unstaged changes of the file in the working tree | Index and other files |
| `git restore --staged -- file` | Staged version of the file in the index is replaced with `HEAD` | Working tree and other files |
| `git restore --source=HEAD --staged --worktree -- file` | Both staged and unstaged changes of the file | Commit history and files outside pathspec |
| `git restore -p ...` | Only the hunks you select | Unselected hunks and other paths |
| `git restore --source=<commit> --worktree -- directory/` | Replaces working tree content of paths within the directory scope with the source snapshot | Index and paths outside the scope |

Restore commands do not create new commits, do not move branches, and do not delete old commits. They alter the index and/or working tree according to the specified destinations. However, overwritten data may have no copy left to recover.

Do not run `git restore .` without knowing what changes exist across all tracked files in the current directory. `.` may cover more files than you intend to restore. Check `git status` and specify the narrowest pathspec possible.

## 15. `git restore` Cannot Recover Every Kind of Data

Git can only retrieve content from objects or index entries it still knows about. `git restore` cannot recover on its own:

- Deleted untracked files if they were never stored in Git.
- Overwritten unstaged working tree content when no other copy remains.
- Ignored files that were never committed or stashed.
- Data in databases, volumes, cloud services, or systems outside the repository.
- Never-committed content once lost from both the working tree and the index.

The reflog records movements of refs like `HEAD` and branches; it does not log every file edit you make. Therefore, the reflog generally cannot rescue uncommitted content that has been overwritten.

If you lose an untracked file or local content not saved by Git, check the Recycle Bin/Trash, system backups, IDE Local History, filesystem snapshots, or appropriate data recovery tools. Outcomes depend on whether the old bytes still exist on the device or have been overwritten.

## 16. Distinguishing `restore`, `reset`, `revert`, and `clean`

These commands have different goals and scopes:

| Command | Primary Effect | When Appropriate |
|---|---|---|
| `git restore` | Restores path content in index and/or working tree | Discarding or retrieving changes for specific files |
| `git reset` | Moves `HEAD`/branch and, depending on mode, updates index and working tree | Adjusting branch position or staging state |
| `git revert` | Creates a new commit reversing the changes of an earlier commit | Undoing a shared commit while preserving history |
| `git clean` | Deletes untracked files from the working tree | Cleaning up files not tracked by Git after verification |

`git restore` does not replace `git revert` when undoing a shared commit. If a commit has been pushed and the team needs to preserve history, `git revert` is usually more appropriate. `git clean` is a command for deleting untracked files; it is not a recovery tool. Always use `git clean -n` to preview if cleanup is needed, and run the actual deletion only after confirming.

## 17. Practice Example: A File with Both Staged and Unstaged Changes

Suppose you edit `src/main/InvoiceService.java`, stage the first part, and continue editing:

```bash
git add src/main/InvoiceService.java
```

Then continue modifying the file without staging again. Check:

```bash
git status --short
git diff -- src/main/InvoiceService.java
git diff --cached -- src/main/InvoiceService.java
```

If the staged part is right but you do not want to keep the extra edits, restore only the working tree from the index:

```bash
git restore --worktree -- src/main/InvoiceService.java
```

If you realize you accidentally staged the whole content and want to keep the current file to split commits again:

```bash
git restore --staged -- src/main/InvoiceService.java
```

If you want to discard all changes to the file and go back to `HEAD`:

```bash
git restore --source=HEAD --staged --worktree -- src/main/InvoiceService.java
```

After each choice, run `git status` and both `git diff` commands to confirm the index and working tree match your target.

## 18. Safe Workflow Before Restoring

1. **Identify paths:** choose the exact file or directory, and check tracked/untracked status.
2. **Read status:** run `git status --short`, `git diff`, and `git diff --cached`.
3. **Choose source:** index, `HEAD`, tag, or specific commit.
4. **Choose destination:** working tree, index, or both.
5. **Preserve content to keep:** commit, stash, or back up outside the repository.
6. **Narrow pathspec:** avoid `.` or broad wildcards if you only need to fix one file.
7. **Execute restore:** explicitly specify `--worktree`, `--staged`, and `--source` when needed.
8. **Review after operation:** run status and diff to verify remaining data.
9. **Run tests and commit:** if the restored result is a change meant to be shared, stage and create a new commit.

Example restoring an old version and recording it with a new commit:

```bash
git status --short
git log --oneline -- src/main/InvoiceService.java
git show <commit>:src/main/InvoiceService.java
git restore --source=<commit> --worktree -- src/main/InvoiceService.java
git diff -- src/main/InvoiceService.java
git add src/main/InvoiceService.java
git diff --cached -- src/main/InvoiceService.java
git commit -m "Restore invoice service implementation"
```

Replace `<commit>` with a verified commit. If you want to stage the old version immediately, add `--staged` to the restore command; still review the diff before committing.

## 19. Key Takeaways

`git restore` restores content according to the selected source and destination. By default, `--worktree` pulls from the index; `--staged` pulls from `HEAD`. Use `--source` to fetch a version from another commit, and use both `--staged --worktree` when you want both areas returned to the same snapshot. The command affects only the chosen pathspec or hunks, creates no commit, and moves no branch. It cannot recover untracked files or overwritten uncommitted edits if neither Git nor a backup system holds a copy. Check status, protect data you need to keep, and review diffs before performing operations that can discard content.

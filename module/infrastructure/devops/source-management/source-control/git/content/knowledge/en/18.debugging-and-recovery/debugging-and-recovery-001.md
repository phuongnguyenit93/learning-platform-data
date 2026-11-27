# Creating a Protective Copy and Recording State Before Data Recovery

When Git encounters an incident such as lost commits, an accidentally moved branch, an incomplete rebase, an overwritten working tree, or accidentally deleted files, the first instinct is often to run a command to fix it immediately. However, recovery operations can further alter data and make it harder to locate the original state.

Before using `reset`, `clean`, `restore`, `checkout`, `rebase`, `gc`, or any command that may overwrite or remove data, **stop write operations, record the current state, and create a protective copy outside the affected repository**.

A complete protective copy needs to preserve the working tree, staging area, new files, ignored files, and Git data in `.git` (or the actual Git directory). Records such as `git status`, `git diff`, `git reflog`, and the commit graph help us understand the state before recovery. They complement the copy; they do not replace it.

## 1. Why Protect Data Before Recovery?

Git stores commit history and refs in the repository, but work in progress may not yet be in a commit. An affected repository can contain several types of data:

| Component | Examples | When Can It Be Lost? |
|---|---|---|
| Created commits | New commits, merge commits, commits on a separate branch | When a branch/ref is moved or deleted, objects can become hard to find; later they may be reclaimed by garbage collection if no longer referenced. |
| Branches and tags | `main`, `feature/payment`, `v1.2.0` | When a ref is accidentally deleted or updated. |
| Staged changes | Files with `git add` run but not yet committed | When resetting the index, checking out, or running operations that replace content. |
| Unstaged changes | Modified tracked files in the working tree | During restore, checkout, reset, or file overwrite. |
| Untracked files | New files not yet added with `git add` | When running `git clean` or directory cleanup operations. |
| Ignored files | `.env`, local config files, build artifacts, or IDE files | When running `git clean -x`, deleting directories, or running cleanup tools. |
| Reflog and Git metadata | Movement trail of HEAD, refs, index, and repository configuration | When deleting or replacing the Git directory, or when old entries expire and are collected by garbage collection. |

A single command may affect only part of the data. For example, `git reset --hard` updates HEAD, the index, and the working tree to match the target commit; `git clean` deletes untracked files; `git clean -x` can also delete ignored files. Running multiple commands in a row without inspecting first can lose multiple types of data at once.

## 2. The First Rule: Stop Writing and Avoid Making the Situation Worse

When an incident is detected:

1. Stop any commands currently rewriting history or cleaning data if it is safe to do so.
2. Do not run `reset --hard`, `clean -fd`, `clean -fdx`, `rebase --abort`, `gc`, or ref-deletion commands based on guesswork.
3. Do not create new commits, stashes, branches, or tags just to experiment before recording and backing up the current state.
4. Do not close or delete the repository directory if you do not yet know what data still needs to be kept.
5. If an IDE, build tool, or another process is still automatically writing to the repository, pause it before taking a copy if possible.

The goal is to preserve the current state for investigation. Each additional write operation can alter the index, working tree, reflog, or refs, making it harder to distinguish old data from new.

## 3. Recording Git State with Read-Only Commands

First, identify the repository and its current state. The commands below are primarily for observation and do not modify working content.

### 3.1. Identify the Repository, Branch, and Current Commit

```bash
git rev-parse --show-toplevel
git rev-parse --show-prefix
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short --branch
```

These commands show:

- The path to the root directory of the working tree.
- The current location relative to the repository root.
- The name of the checked-out branch; if in detached HEAD state, the branch command may return `HEAD`.
- The object ID of the commit that HEAD currently points to.
- A summary of staged, unstaged, and untracked status.

Also record any detached HEAD state. Do not switch branches just to make a branch name appear, because switching branches can modify the working tree and conflict with current changes.

### 3.2. Record Detailed Status

```bash
git status --porcelain=v2 --branch --untracked-files=all
```

The porcelain v2 format is suitable for saving and comparing because it has a more stable structure than the standard display format. The `--untracked-files=all` option lists each untracked file individually instead of showing only the parent directory.

If you also need to view ignored files:

```bash
git status --short --branch --ignored
```

Ignored files can contain important local data such as environment configuration or files not yet added to Git. Check this list before performing any cleanup operation.

### 3.3. Record Staged and Unstaged Changes

```bash
# Unstaged tracked changes
git diff --binary

# Staged changes
git diff --cached --binary

# Change statistics
git diff --stat
git diff --cached --stat
```

`git diff` does not show the contents of untracked files. `git diff --cached` shows the contents currently in the staging area. These two diffs help record uncommitted tracked changes.

For untracked and ignored files, record their lists separately:

```bash
git ls-files --others --exclude-standard
git ls-files --others --ignored --exclude-standard
```

These lists do not contain file contents. Therefore, to protect new or ignored files, you must copy the files themselves in the full copy.

### 3.4. Record History and Refs

```bash
# Commit graph of existing refs
git log --graph --oneline --decorate --all -n 100

# Local and remote-tracking branches
git branch -avv

# Refs and object IDs
git show-ref --head

# Movement trail of HEAD and refs
git reflog --all --date=iso
```

`git reflog` is especially useful when a branch or HEAD was just moved by mistake. The reflog can help locate the commit before the erroneous operation, but it is not a long-term backup: entries can expire and unreferenced objects can be reclaimed by garbage collection.

If the incident involves a remote, you can record:

```bash
git remote -v
git config --get-regexp '^branch\.'
```

Remote URLs sometimes contain credentials or tokens. Do not share logs verbatim when they contain sensitive URLs; redact secrets before sending them to others.

## 4. Creating a Full Protective Copy

### 4.1. Why Copy the Entire Working Copy?

A full repository directory copy typically protects:

- Current tracked files, including both staged and unstaged changes.
- Untracked files not yet managed by Git.
- Ignored files, if the copy operation includes them.
- The Git directory containing the object database, refs, reflogs, index, and other metadata.

This is important because simply cloning the repository or creating a Git bundle does not save all uncommitted state.

**Place the copy outside the original repository.** If you place the backup folder inside the working tree, Git may see the copy as a large number of untracked files, cluttering status and risking deletion by cleanup commands.

If the incident might involve a disk or storage device, place the copy on an independent drive or storage location. A folder outside the repository but still on the same disk only protects against certain accidental operations, not against disk failure. The copy may contain `.env`, keys, or internal data, so restrict access permissions accordingly.

### 4.2. Copying on Windows with PowerShell and Robocopy

On Windows, you can use Robocopy to copy hidden folders such as `.git` as well. Run from a PowerShell window inside the repository:

```powershell
$repoRoot = (git rev-parse --show-toplevel).Trim()
$parentDir = Split-Path -Parent $repoRoot
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $parentDir ("git-recovery-" + $stamp)

New-Item -ItemType Directory -Path $backupDir | Out-Null
robocopy $repoRoot $backupDir /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) {
    throw "Robocopy failed with exit code $LASTEXITCODE"
}
```

Explanation:

- `$repoRoot` retrieves the working tree root path from Git.
- `$backupDir` creates a backup directory at the same level as the original repository, outside the working tree.
- `/E` copies subdirectories, including empty ones.
- `/COPY:DAT` and `/DCOPY:DAT` preserve data, attributes, and timestamps.
- `/R:1 /W:1` limits the number of retries on error.
- `/XJ` avoids following junctions, preventing recursive loops or copying unintended directories.
- Robocopy uses exit codes from 0 to 7 for completed states or states with differences; exit codes of 8 or higher indicate copy errors.

Do not use `/MIR` in the initial protective step. `/MIR` can delete files at the destination if they do not exist in the source; a backup copy command should avoid deleting anything in the destination directory.

After copying, verify that the backup directory contains both project content and Git metadata. If `.git` is a directory, confirm it appears in the copy. If `.git` is a file pointing to another Git directory, handle the linked worktree case covered in the next section.

### 4.3. Notes on Linked Worktrees and Submodules

Not every working tree contains a `.git` directory. With a linked worktree, `.git` can be a file pointing to a Git directory located elsewhere; multiple worktrees also share a Git common directory.

Check:

```bash
git rev-parse --absolute-git-dir
git rev-parse --git-common-dir
```

If these paths lie outside the working tree directory you just copied, the working tree copy alone is not enough to protect Git metadata. Copy the actual Git directory and common directory to a safe location as well, preserving path structure or clearly documenting the pointer relationship to them. Do not delete or move these directories before verifying the copy.

A submodule is a separate repository referenced from the parent repository. Copying the parent working tree may copy the submodule content directory, but you need to inspect each submodule's Git metadata and change state inside it. If a submodule has uncommitted changes, back up the corresponding submodule repository rather than relying solely on the commit pointer recorded by the parent repository.

## 5. Git Bundle: A Supplementary Copy for Referenced Commits

After protecting the working copy, you can create an additional Git bundle to save existing commits and refs. For example, in PowerShell, using the backup directory created in the previous step:

```powershell
$bundlePath = Join-Path $backupDir 'repository-recovery.bundle'
git bundle create $bundlePath --all
if ($LASTEXITCODE -ne 0) {
    throw "git bundle create failed with exit code $LASTEXITCODE"
}
git bundle verify $bundlePath
```

A Git bundle packages the objects needed to reconstruct the refs included in the bundle. It is useful for storing or transferring commit history without needing remote access.

However, a bundle **does not replace a full working copy**:

- It does not contain uncommitted changes in the working tree.
- It does not save staging area state as an index that can be restored verbatim.
- It does not automatically contain the contents of uncommitted untracked or ignored files.
- It does not preserve the reflog like an exact copy of the Git directory.
- It does not necessarily contain commits only reachable via the reflog if those commits do not belong to the packaged refs.

Therefore, a bundle is suitable for protecting referenced commit history, whereas a full copy protects the actual state of the working copy and Git metadata.

## 6. Recording Evidence into the Backup Directory

After creating the backup directory outside the repository, save the diagnostic outputs into it. PowerShell example:

```powershell
git status --porcelain=v2 --branch --untracked-files=all |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'status.txt')

git status --short --branch --ignored |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'status-with-ignored.txt')

git rev-parse --show-toplevel |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'repository-root.txt')

git rev-parse HEAD |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'head.txt')

git branch -avv |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'branches.txt')

git show-ref --head |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'refs.txt')

git log --graph --oneline --decorate --all -n 100 |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'commit-graph.txt')

git reflog --all --date=iso |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'reflog.txt')

git diff --binary |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'unstaged.patch')

git diff --cached --binary |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'staged.patch')

git ls-files --others --exclude-standard |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'untracked-files.txt')

git ls-files --others --ignored --exclude-standard |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'ignored-files.txt')
```

The patch files are supplementary records for tracked changes; they do not include untracked/ignored contents. The full copy remains the primary source of protection.

If you record `git remote -v` or Git configuration, review the URLs and remove credentials before sharing. Do not include tokens, passwords, private keys, or `.env` contents in public reports.

## 7. Verifying the Copy Before Starting Recovery

A copy is only useful when you know it actually exists and contains the necessary components.

Verification checklist:

- The backup directory is outside the original repository.
- Important project files are present in the copy.
- Untracked and ignored files that need to be kept are present in the copy.
- The actual Git directory or Git common directory has been copied.
- If there are submodules or linked worktrees, the corresponding metadata has been protected separately.
- Status record files such as `status.txt`, `head.txt`, and `reflog.txt` have been created.
- The Git bundle, if created, has passed `git bundle verify`.
- There are no copy errors or unexpectedly skipped files.

If the incident is severe, keep the first copy untouched and test recovery on a second copy. That way, if a recovery approach alters more data, you still have the original copy to fall back on.

## 8. Choosing a Recovery Approach Only After Protecting Data

Once you have the copy and state records, start analyzing the cause. Choose the action based on the type of data that needs to be recovered.

| Situation | Data to Find | Initial Investigation Direction |
|---|---|---|
| Branch deleted or moved by mistake | Old commit the branch used to point to | `git reflog --all`, `git log --all`, `git show <commit>` |
| HEAD reset by mistake | Commit before the reset operation | `git reflog`, `git rev-parse`, `git show` |
| Commit lost from branch | Commit object still exists but has no ref | Reflog, `git fsck --full --no-reflogs --unreachable` after backing up |
| Tracked file overwritten | Content in a commit, index, or backup copy | `git show <commit>:<path>`, `git diff`, compare with backup copy |
| Untracked file deleted | Content not in the Git object database | Full copy, OS backup, or file recovery tool |
| Ignored file deleted | Local content not tracked by Git | Full copy or OS backup |
| Incomplete rebase/merge | Index, working tree, and sequencer metadata state | `git status`, Git metadata in the copy, refs and reflog |

Not all data can be recovered with Git. Untracked or ignored files that were never committed may not exist in the object database. If they are deleted and no other copy exists, look into OS backups or file recovery tools; Git cannot reconstruct content it never stored.

### 8.1. Finding Old Commits with Reflog

After backing up, you can inspect:

```bash
git reflog --all --date=iso
```

Find the entry right before the incident-causing operation, then inspect the commit:

```bash
git show --stat <commit-id>
git log --oneline --decorate -n 20 <commit-id>
```

Only after confirming the right commit should you create a rescue branch to hold the ref:

```bash
git branch rescue/recovered-state <commit-id>
```

A rescue branch prevents the commit from losing visibility when other refs move. Before creating it, make sure the branch name does not already exist and the commit is indeed the state that needs rescuing.

### 8.2. Finding Unreferenced Objects

If the reflog no longer has a matching entry, after creating a full copy you can check for unreferenced objects:

```bash
git fsck --full --no-reflogs --unreachable
```

If you see a commit-type object, inspect its contents:

```bash
git show --stat <object-id>
git show --no-patch --pretty=fuller <object-id>
```

Do not rush to run `git gc`, `git prune`, or object cleanup commands. Those commands can remove the very objects you are looking for. Once you find the right commit, create a rescue ref such as a branch or tag to keep it.

### 8.3. Recovering a Tracked File from a Commit

If a tracked file was modified or deleted, you can view its version in a known commit:

```bash
git show <commit-id>:path/to/file
```

The command above displays the file contents at that commit. Save the needed content to a recovery location or compare it with your copy before using an overwriting command like `git restore`. Do not replace a file that currently has other changes without first determining whether they need to be kept.

## 9. Why You Should Not Use a "Quick Fix" Command Before Backing Up

| Command | Impact to Watch Out For |
|---|---|
| `git reset --hard <commit>` | Moves HEAD/branch and makes the index and working tree match the target commit; uncommitted tracked changes may be lost. |
| `git clean -fd` | Deletes selected untracked files and directories. |
| `git clean -fdx` | Can also delete ignored files such as local configuration or build artifacts. |
| `git restore <path>` | Can overwrite working tree contents with the version from the index or specified source. |
| `git restore --staged <path>` | Changes staging state; staged contents may no longer remain in the index as before. |
| `git rebase --abort` | Ends the rebase session and restores the pre-rebase state according to Git metadata; you need to understand current changes first. |
| `git gc` / `git prune` | Can clean up unreferenced objects, including objects needed for post-incident investigation. |

These commands are not always dangerous; they are valid tools once you understand the state and goal. The problem is running them before knowing which data needs to be protected.

## 10. Sample Recovery Workflow

Suppose a branch was just reset by mistake and the working tree still has some uncommitted files. The workflow can be carried out as follows:

1. **Stop write operations:** do not continue running reset, clean, rebase, or checkout based on guesswork.
2. **Record the current state:** save `status --porcelain=v2`, HEAD, branch, staged/unstaged diffs, untracked/ignored lists, log, and reflog.
3. **Copy the entire working copy:** place the backup outside the repository; verify that `.git` or the actual Git directory is protected.
4. **Create a supplementary history record:** optionally create and verify a Git bundle if referenced commits need to be saved.
5. **Analyze the cause:** identify the erroneous operation, old commit/ref, and type of data to recover.
6. **Test on a copy:** if possible, create a second working copy and execute the recovery approach there.
7. **Verify the result:** compare files, branches, commits, staging, and working tree against the desired state; run appropriate tests.
8. **Only update the main repository once confirmed:** clearly note which data the operation will change and keep the original copy until everything is complete.

## 11. Takeaways

- Before recovering data, stop write operations and record the current state.
- `git status --porcelain=v2 --branch --untracked-files=all` helps save structured tracked and untracked status.
- `git diff --binary` and `git diff --cached --binary` record unstaged and staged tracked changes.
- Untracked/ignored lists do not contain contents; you must copy the files you need to keep.
- A full copy needs to include both the working tree and Git metadata; linked worktrees, Git common directories, and submodules may reside in separate locations.
- A Git bundle protects packaged commits/refs, but does not replace a copy of the working copy, index, untracked files, ignored files, or reflog.
- Reflog is useful for finding old commits, but it is not a long-term backup.
- Do not run `reset --hard`, `clean`, `gc`, or `prune` based on guesswork before protecting data.
- Test recovery on a second copy for complex incidents; only apply to the main repository after confirmation.

When handling a Git incident, treat the current state as evidence that needs to be preserved. A complete copy along with clear state records allows you to investigate with confidence, test multiple approaches, and return to the starting point if a recovery step does not produce the desired result.

# Restoring the Index State with `stash apply --index`

While working, you may stage part of your changes to prepare a commit while continuing to edit other parts in the working tree. If you need to switch to handle an urgent task or change branches, `git stash` can temporarily shelve the current state. When returning, the `--index` option helps restore both the staged state in the staging area alongside the working tree content.

The point to distinguish is **file content** versus **the state of content in the index**. A single file can contain both a staged part and newer unstaged edits. When running just `git stash apply`, Git reapplies the changes without attempting to restore the exact original staging state. With `git stash apply --index`, Git attempts to restore both parts so what was previously staged stays in the index while the unstaged part remains in the working tree.

In Git source control, understanding the index is very important because a commit only records staged content. Properly restoring the index state lets you resume work without accidentally including unfinished parts in a commit or having to manually re-stage changes one by one.

## 1. Distinguishing HEAD, index, and working tree

Before using `--index`, you need to understand the three main state areas in a repository:

| Area | Role | Command to inspect changes |
| --- | --- | --- |
| `HEAD` | Current commit of the active branch | `git show --stat HEAD` |
| Index (staging area) | Content to be included in the next commit | `git diff --cached` |
| Working tree | Current file content in the working directory | `git diff` |

For example, we edit `PaymentService.java`, stage part of the changes, and then continue editing the rest:

```bash
# Edit the first time, then put this part into the index
git add src/main/java/example/PaymentService.java

# Continue editing the file after staging
# The new edits stay in the working tree, unstaged

git status --short
git diff --cached
git diff
```

In the `git status --short` output, two status columns represent the two different areas:

```text
MM src/main/java/example/PaymentService.java
```

The first `M` indicates that the content in the index differs from `HEAD`; the second `M` indicates that the working tree differs from the index. Thus, the file currently has both staged changes and unstaged changes. This is the state that `git stash apply --index` needs to restore accurately.

If you only see:

```text
M  src/main/java/example/PaymentService.java
```

then the changes are in the index and the working tree currently matches the index. If you see:

```text
 M src/main/java/example/PaymentService.java
```

then the file has unstaged changes compared to the index.

## 2. What does stash save?

Basic command:

```bash
git stash push -m "WIP: payment validation"
```

Git temporarily saves tracked changes in the index and working tree, then returns the working tree to a clean state matching the current commit. The message after `-m` helps identify the stash's purpose in the list.

By default, files not tracked by Git (untracked) are not included in the stash. If you need to shelve untracked files too, use `-u` or `--include-untracked`; if you need to shelve ignored files too, use `-a` or `--all`:

```bash
git stash push -u -m "WIP including new test files"
git stash push -a -m "WIP including ignored build output"
```

Only use `-a` when you truly want to shelve ignored files, because they can include local config, caches, or auto-generated data. The `--index` option on apply decides whether to restore the staging state; it does not change the rules for selecting which files are saved into the stash.

### How does stash retain index information?

Structurally, a regular stash records the working tree state and holds a reference to a separate index snapshot. The diagram below only illustrates the two snapshots and does not depict commit parent ordering:

```text
                 W  working tree snapshot
                / \
HEAD (H) ------    I  index snapshot
```

In commit structure terms, `W` has two parents: the first parent is `H`, and the second parent is `I`; commit `I` also has `H` as its parent. `H` is the `HEAD` commit at the time of stash creation; `I` records the staged state; `W` records the working tree state. What matters in practice is that the stash holds enough information for Git to attempt recovering the staged part separately from the unstaged part.

Inspect saved stashes:

```bash
git stash list
git stash show --stat 'stash@{0}'
git stash show -p 'stash@{0}'
```

`stash@{0}` is the newest stash; `stash@{1}` is the next entry, and so on. Using single quotes around the reference name helps the command run reliably in PowerShell, where `@{...}` syntax has special meaning.

## 3. Restoring with `git stash apply --index`

After stashing, you can switch to another branch or handle other work. When returning to the right branch and wanting to restore both the index state and the working tree, run:

```bash
git stash apply --index 'stash@{0}'
```

If no stash name is passed, Git applies the newest stash by default:

```bash
git stash apply --index
```

`--index` asks Git to attempt restoring the staging state saved in the stash as well. After applying successfully:

- Changes that were staged before stashing return to the index.
- Changes that were unstaged before stashing return to the working tree.
- File contents reflect the working state before stashing, within the limits of changes that can apply cleanly onto the current `HEAD`.

Check the state after applying:

```bash
git status --short
git diff --cached
git diff
```

`git diff --cached` shows what was restored in the index; `git diff` shows what remains in the working tree. Do not merely look at file contents and conclude restoration succeeded: both staged and unstaged parts can live in the same file, so you need to inspect both diff commands.

### Comparing regular `apply` and `apply --index`

Suppose before stashing, a file has a staged edit and an unstaged edit:

| Operation | File content after applying | Index state |
| --- | --- | --- |
| `git stash apply` | Attempts to restore changes in stash | Does not attempt to recover the original staging state; changes are usually brought back as unstaged |
| `git stash apply --index` | Attempts to restore changes in stash | Attempts to recover both the staged part and the unstaged part as when the stash was created |

Example:

```bash
git stash apply 'stash@{0}'
```

This command applies the changes without requesting index state restoration. If you need to continue with the exact original staged/unstaged split, use `--index` from the start or manually re-stage after checking the diff.

## 4. Full workflow: partial stage, stash, then restore index

Practice on a test repository or personal branch to observe the result.

### Step 1: Create both staged and unstaged changes

Modify a tracked file, then stage the first change:

```bash
git add src/main/java/example/PaymentService.java
```

Continue editing the file or another file without staging the new part. Check:

```bash
git status --short
git diff --cached
git diff
```

Note: if you want the same file to have both staged and unstaged changes, edit the file, stage the first state, then edit the file again. Do not run `git add` a second time before creating the stash if the goal is to keep the two layers of changes separate.

### Step 2: Shelve the state

```bash
git stash push -m "WIP: separate staged and unstaged changes"
```

After the command succeeds, check:

```bash
git status -sb
git stash list
```

The tracked working tree usually returns to clean. If untracked files remain, remember that by default stash does not include them; if needed, you must create the stash with `-u` or save them separately.

### Step 3: Do other work and return to the original branch

You can switch branches and handle another task:

```bash
git switch main
# do other work and commit if needed
git switch feature/payment
```

Before applying, check the current branch and repository state:

```bash
git branch --show-current
git status -sb
```

For more accurate restoration, apply the stash on the branch and commit base corresponding to when the stash was created, with a clean working tree. If the branch has changed significantly, Git may encounter conflicts or be unable to restore the index as before.

### Step 4: Apply the stash with the index state

```bash
git stash apply --index 'stash@{0}'
```

If it succeeds, inspect both areas separately:

```bash
git status --short
git diff --cached
git diff
```

Compare the result with the state before stashing. The staged part must be in the index; the unstaged part must be in the working tree.

### Step 5: Delete the stash only after verification

`git stash apply` keeps the stash in the list even when application succeeds. This lets you inspect or re-apply if needed. After verifying the contents and index state, if you are sure the saved entry is no longer needed, you can delete the specific entry:

```bash
git stash drop 'stash@{0}'
```

Do not delete a stash right after applying without checking the result. If any doubt remains or review is pending, keep the stash as a recovery point.

## 5. Using `git stash pop --index`

`pop` combines applying a stash and removing it from the list when application succeeds:

```bash
git stash pop --index 'stash@{0}'
```

Unlike `apply`, `pop` is geared toward one-time stash use. If application succeeds, Git deletes the corresponding stash entry. If conflicts arise or the operation does not complete, Git keeps the stash so you can resolve and retry.

Choose:

- `git stash apply --index` when you want to keep the stash until you personally verify and decide to delete it.
- `git stash pop --index` when you are ready to apply and discard the stash upon success.

In workflows where index state control matters, `apply --index` is usually easier to verify because the saved entry remains intact in the list after applying.

## 6. Why might `--index` fail to restore?

`--index` asks Git to recover two layers of state, so there are situations where it cannot be applied automatically.

### The current branch changed the same content

If the file on the current branch was modified after creating the stash, the patch in the stash may conflict with the new changes. Git may fail to apply part or all of the patch.

### The current index state is incompatible

The index may contain other changes, or be in an unmerged state from a previous conflict resolution. In this situation, Git cannot easily recreate the old index snapshot. Before applying, check `git status` and finish or separately save existing work.

### One file has both staged and unstaged edits

This is a valid case and often why we need `--index`, yet it is also prone to conflicts when content on the target branch has changed. Git must restore the staged part and the unstaged part in the right order; if the patches can no longer apply, the operation may stop.

### The stash was created on a different commit base

A stash is created from a specific `HEAD`. If applied onto a branch that changed file structures, renamed files, or edited the same region, Git must reconcile the differences. You may need to return to the original branch, update to a suitable base, or resolve conflicts manually.

### The stash does not contain the file to restore

Untracked or ignored files are not included in a stash by default. `--index` cannot restore content that was never saved in the stash. Check how the stash was created and use `-u` or `-a` for the next save if needed.

## 7. Handling when `stash apply --index` encounters conflicts

When applying a stash results in conflicts, first read the status:

```bash
git status
```

Git will list unmerged files. Open each file, pick the right content, remove conflict markers if present, and stage the result:

```bash
git add src/main/java/example/PaymentService.java
```

After staging the resolved file, check again:

```bash
git status --short
git diff --cached
git diff
```

There is no `git stash apply --continue` command like a rebase session. When apply stops, you handle the file and index state directly. The original stash remains in the list, so there is no need to re-stash to preserve the backup.

If you need to cancel an interrupted apply, Git does not provide a `git stash apply --abort` command similar to rebase. How to handle it depends on the state before applying. If the working tree was clean beforehand and no extra work was created, you can restore the affected files appropriately after checking carefully. Avoid running `git reset --hard` or `git clean` out of habit because they can delete unsaved changes. When important data is involved, make a copy or stash the current state before performing a recovery action.

After resolving, verify the staged/unstaged parts. If you need to try again from the initial stash, return to a safe state and re-run `git stash apply --index` with the right stash.

## 8. Accurately checking index state after restoration

To confirm proper restoration, do not only look at general `git status`. Use both diff commands:

```bash
# What is staged compared to HEAD
git diff --cached

# What is unstaged compared to the index
git diff
```

If you want to view filenames and short status:

```bash
git status --short
```

If you need to compare accurately with the pre-stash snapshot, you can view the stash contents:

```bash
git stash show -p 'stash@{0}'
```

This command shows changes in the stash relative to its base. To inspect the index state separately, you would inspect the stash's index commit or use appropriate Git plumbing commands; in daily work, comparing `git diff --cached`, `git diff`, and the pre-stash state is usually enough to confirm.

A short checklist after applying:

1. The right branch received the stash.
2. No unresolved conflict files remain.
3. Previously staged changes appear in `git diff --cached`.
4. Previously unstaged changes appear in `git diff`.
5. Necessary untracked/ignored files were saved appropriately.
6. The original stash remains until confirmed no longer needed.

## 9. Related stash commands

| Command | Purpose |
| --- | --- |
| `git stash push -m "message"` | Save tracked changes in the index and working tree with a description |
| `git stash push -u -m "message"` | Also save untracked files |
| `git stash push -a -m "message"` | Also save ignored files |
| `git stash list` | List existing stashes |
| `git stash show -p 'stash@{0}'` | View patch of a stash |
| `git stash apply --index 'stash@{0}'` | Apply stash and attempt to restore index state |
| `git stash pop --index 'stash@{0}'` | Apply stash with index and delete entry if successful |
| `git stash drop 'stash@{0}'` | Delete a specific stash entry |
| `git stash clear` | Delete all stashes in the repository |

`git stash clear` has a wide scope and can make changes kept only in stashes hard to recover. Do not use this command for cleanup without confirming every entry is no longer needed.

## 10. Common confusions

| Confusion | Correct understanding |
| --- | --- |
| `git stash apply` always restores staged changes | To have Git attempt restoring the index, `--index` must be used |
| `--index` only restores file contents | It requests restoring the saved index state as well, in addition to the working tree |
| Successful apply deletes the stash | `apply` keeps the stash; `pop` deletes the entry on successful apply |
| Stash includes all new files by default | Untracked files require `-u`; ignored files require `-a` |
| `--index` guarantees successful restoration in all cases | It is an attempt to recover the index; conflicts or current index state can cause the operation to fail |
| Checking `git status` alone is enough | You should check both `git diff --cached` and `git diff` to distinguish the two areas |
| `git stash apply --abort` can be used | There is no such option; apply has no dedicated abort flow like rebase |

## 11. Practice

Carry out in a test repository:

1. Create or edit a tracked file, then stage part of the changes.
2. Continue editing the file to create additional unstaged changes; use `git status --short`, `git diff --cached`, and `git diff` to confirm the two parts are separate.
3. Run `git stash push -m "test staged and unstaged"`.
4. Confirm the working tree is clean and the stash appears in `git stash list`.
5. Return to the right branch and run `git stash apply --index 'stash@{0}'`.
6. Use `git status --short`, `git diff --cached`, and `git diff` to confirm the staged and unstaged parts returned to their proper areas.
7. Once the state is restored, stash again with a different message and then try `git stash apply` without `--index` to compare the staging state.
8. After verifying, delete the test stashes using `git stash drop 'stash@{0}'` in newest-first order; keep any other stashes if present.
9. Try adding an untracked file and observe the difference between `git stash push` and `git stash push -u`.

After practicing, explain why the same file can simultaneously have staged and unstaged changes, why `--index` is necessary when you want to recover that split, and why you should use `apply` before deciding to delete the stash.

## 12. Knowledge self-check

1. How does the index differ from the working tree?
2. When a file has both staged and unstaged changes, how does `git status --short` typically display its status?
3. What types of changes does `git stash push` save by default?
4. How does `git stash apply` differ from `git stash apply --index`?
5. Why can `--index` fail when the current branch has modified the same file?
6. After a successful apply, which commands are used to inspect the staged part and unstaged part separately?
7. How does `git stash pop --index` differ from `git stash apply --index` in terms of stash lifecycle?
8. If apply encounters a conflict, why can't you use `git stash apply --abort`?
9. Which options are needed to save untracked or ignored files?
10. When should an applied stash be dropped?

## Conclusion

`git stash apply --index` helps restore temporarily shelved changes and asks Git to recover the original staging state as well. After applying, check `git diff --cached` and `git diff` to confirm that staged and unstaged parts are in their proper areas. Because restoring the index can encounter conflicts when the branch or files have changed, keep the stash until verification is complete; drop it only when certain the saved entry is no longer needed.

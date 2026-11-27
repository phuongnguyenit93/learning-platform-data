# Git reset --mixed Affects HEAD and the Index

In Git, a change can reside in three different places: the commit referenced by HEAD, the staging area (index), and the working tree. When you want to undo the most recent commit while keeping the file contents to edit or create a new commit, `git reset --mixed` is a commonly used option. This command moves HEAD to the target commit and resets the index to that commit's state, while preserving the working tree's content.

Understanding these three areas accurately helps you predict the result before running the command. `--mixed` does not delete content currently in the working tree, but it replaces the current staging state with the target commit's snapshot. Consequently, changes that were previously staged become unstaged changes.

## 1. Three Components to Understand Before Using Reset

### HEAD and the current branch

`HEAD` indicates the repository's current position. In normal workflow, HEAD is a symbolic reference pointing to the checked-out branch, such as `refs/heads/main`. When you create a new commit, that branch advances to the new commit and HEAD follows the branch. If you check out a commit directly (*detached HEAD*), HEAD points directly to that commit.

With `git reset <commit>`, Git moves the current branch to the target commit (or moves HEAD if detached). Thus, a commit-level reset changes the current branch's position in history.

### Index (staging area)

The index is the area where Git stores the content and state selected to go into the next commit. When you run `git add`, the file's content at that moment is placed into the index. A file can continue changing in the working tree after being staged; in that case, the index and working tree hold two different versions.

### Working tree

The working tree consists of the files and directories you directly view, create, edit, or delete in the project folder. This is where active work resides, including both staged and unstaged changes.

You can picture the state flow as follows:

```mermaid
flowchart LR
    H[HEAD / current commit] -->|commit snapshot| I[Index / staging area]
    I -->|checked-out content| W[Working tree]
    W -->|git add| I
    I -->|git commit| H
```

The diagram describes the conceptual relationship between areas in daily work. `git reset --mixed <commit>` sets HEAD and the index to match the target commit, without checking out content back into the working tree.

## 2. Syntax and Meaning of --mixed

Commit-level reset syntax:

```bash
git reset [--mixed] [<commit>]
```

If no mode is specified, `git reset` defaults to `--mixed`. If no commit is specified, the target commit defaults to the current HEAD.

Examples:

```bash
# Reset the index to the current HEAD snapshot, keeping the working tree unchanged.
git reset --mixed HEAD

# Move the current branch and index back to the parent commit of HEAD.
git reset --mixed HEAD~1
```

With `git reset --mixed <commit>`, Git performs two main actions:

1. Moves the current branch (or HEAD in detached state) to `<commit>`.
2. Sets the index to the snapshot of `<commit>`.

The working tree is preserved. Files whose contents differ from the new index will appear as unstaged changes. Files not tracked by Git are also preserved; reset is not a cleanup command for untracked files.

## 3. Observing the Impact on HEAD, Index, and Working Tree

Suppose the initial history has three commits:

```text
A---B---C  (HEAD -> main)
```

Commit `C` was just created and contains changes to `README.md` and `src/App.java`. You decide to remove commit `C` from the branch tip to edit the content and create a different commit.

Before resetting, the committed state can be represented as follows:

| Component | State before reset |
|---|---|
| HEAD / `main` | Commit `C` |
| Index | Snapshot of `C` if no additional changes were staged after committing |
| Working tree | Content of `C` if no additional edits were made after committing |

Run:

```bash
git reset --mixed HEAD~1
```

Result:

```text
A---B  (HEAD -> main)
     \
      C  (no longer the tip of main)
```

`main` now points to `B`; the index is set to `B`'s snapshot; the working tree still holds the pre-reset content, i.e., the content that was in `C`. Because the working tree differs from the index, `C`'s changes become unstaged changes.

| Component | State after reset |
|---|---|
| HEAD / `main` | Commit `B` (`HEAD~1` before the operation) |
| Index | Snapshot of `B` |
| Working tree | Still keeps pre-reset content, including changes previously in `C` |
| Result in `git status` | Differences between the working tree and index are listed as unstaged |

Key takeaway: commit `C` is no longer at the tip of `main`, yet its modified content remains in the working tree for you to review, edit, re-stage, and commit differently.

## 4. Practical Example: Undoing the Latest Commit While Keeping Content

Suppose you created a commit and realized it bundled multiple unrelated changes. You want to split it into two smaller commits.

First, check status and history:

```bash
git status
git log --oneline -5
```

If the working tree and index have no other changes that need separate preservation, you can move the branch back to the parent commit:

```bash
git reset --mixed HEAD~1
```

Check again:

```bash
git status
git diff
git diff --staged
```

Typically, `git status` lists the modified files under *Changes not staged for commit*. `git diff` shows the unstaged content; `git diff --staged` no longer displays changes from the commit removed from the branch tip because the index was reset to the new `HEAD`.

Then, select each part to create commits by purpose:

```bash
# Interactively select chunks of changes to stage.
git add -p

# View the exact content that will be committed.
git diff --staged

# Create the first commit.
git commit -m "feat: add application configuration"

# Stage the remaining part and create the next commit.
git add src/App.java
git diff --staged
git commit -m "feat: wire application startup"
```

`git add -p` lets you choose individual hunks instead of staging an entire file. If you need to re-stage all changes, you can use `git add <path>` or `git add -A` depending on the desired scope.

## 5. Unstaging Changes Without Moving the Branch

Another usage is running `git reset` without specifying a commit:

```bash
git reset
```

This command is equivalent to `git reset --mixed HEAD`: HEAD remains on the current commit, the index is reset to HEAD's snapshot, and the working tree is left untouched. This is a common way to unstage all staged changes without deleting edits.

For example, after staging two files:

```bash
git add README.md src/App.java
git status
```

You realize you only want to commit `README.md`. Run:

```bash
git reset
```

Afterward, both files retain their edited contents in the working tree, but are no longer staged. You can re-stage just the file you need to commit:

```bash
git add README.md
git diff --staged
```

Note: this operation unstages all changes managed by the index, not just one file. If you only want to unstage specific paths, use the pathspec form shown in the next section.

## 6. Distinguishing Commit Reset from Pathspec Reset

`git reset` has a syntax form for paths:

```bash
git reset [<tree-ish>] -- <pathspec>...
```

Example:

```bash
git reset HEAD -- README.md
```

This form updates the index for the specified paths using content from `<tree-ish>` (which defaults to HEAD). It **does not move HEAD or the current branch** and does not alter the working tree. This is the way to unstage a specific file.

Comparing the cases:

| Command | HEAD / branch | Index | Working tree |
|---|---|---|---|
| `git reset --mixed HEAD~1` | Moves to parent commit | Set to `HEAD~1` | Unchanged |
| `git reset` | Keeps current HEAD | Set to HEAD | Unchanged |
| `git reset HEAD -- README.md` | Unchanged | Updates index for `README.md` only to HEAD | Unchanged |

Do not confuse `git reset HEAD -- <file>` with `git reset --mixed HEAD~1`. Both can change staging status, but only the commit-level reset moves the branch position.

## 7. Comparing --soft, --mixed, and --hard

The three reset modes differ in which areas Git updates:

| Mode | HEAD / branch | Index | Working tree |
|---|---|---|---|
| `--soft` | Moves to target commit | Unchanged | Unchanged |
| `--mixed` | Moves to target commit | Set to target commit | Unchanged |
| `--hard` | Moves to target commit | Set to target commit | Updated to target commit; may overwrite tracked changes |

Examples resetting to `HEAD~1`:

```bash
git reset --soft HEAD~1
git reset --mixed HEAD~1
git reset --hard HEAD~1
```

These are three alternative options for the same hypothetical situation; do not run all three commands consecutively as a workflow. `--soft` keeps changes staged after removing the commit; `--mixed` keeps content while turning differences into unstaged changes; `--hard` brings the working tree back to the target commit as well and can lose uncommitted tracked changes. Determine your desired state before choosing a mode.

## 8. Checking Before and After Using --mixed

Before resetting, inspect the branch, index, and working tree:

```bash
git status --short --branch
git diff --staged
git diff
git log --oneline --decorate -5
```

These commands tell you:

- Which commit the current branch points to.
- Which content is staged.
- Which content is only in the working tree.
- Which commit will become the target if using `HEAD~1`.

After resetting, inspect again:

```bash
git status
git log --oneline --decorate -5
git diff
git diff --staged
```

If the goal was to undo a commit while keeping content, verify the branch now points to the intended commit and the changes you want to keep appear in the working tree. Do not rely solely on command output messages; read the actual state.

## 9. Recovering When Resetting by Mistake

When performing a commit-level reset, Git typically records HEAD movements in the reflog. If you chose the wrong target commit, you can view the movement history:

```bash
git reflog --date=local
```

Example:

```text
5d6e7f8 HEAD@{0}: reset: moving to HEAD~1
9a0b1c2 HEAD@{1}: commit: add login validation
```

If `9a0b1c2` was the commit before resetting and you want to return the branch to that commit while keeping the current working tree content, you can run:

```bash
git reset --mixed 9a0b1c2
```

Replace the illustrative hash with the verified commit hash from the reflog. If you need to keep a reference point before further handling, you can create a rescue branch pointing to that commit:

```bash
git branch rescue/before-reset 9a0b1c2
```

Reflog helps locate the old HEAD position while entries are still retained. It does not save the exact index staging state from before the reset; `git reset --mixed` already replaced the index with the target commit's snapshot. Therefore, restoring the branch pointer does not necessarily restore the exact staged portions from before the operation.

If the commit had already been pushed and others may have relied on it, resetting and pushing rewrites shared branch history. When needing to undo a shared change, you should usually consider `git revert <commit>` to create a new commit reversing the change without moving the branch back in history. Follow your team's conventions before changing remote history.

## 10. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| `git reset --mixed` deletes modified content | The command preserves the working tree; it moves HEAD and updates the index |
| `--mixed` preserves staging | The index is set to the target commit, so staged changes usually become unstaged |
| `git reset` with no arguments deletes the latest commit | With no target commit, it defaults to resetting to current HEAD; the branch does not move, and the index is reset to HEAD |
| Every form of `git reset` moves HEAD | The pathspec form such as `git reset HEAD -- file` only updates the index for that path |
| Resetting a commit immediately deletes the commit object | The branch no longer points to that commit; the commit may still be found via reflog while entries are kept |
| You can freely reset a pushed branch without affecting anyone | Updating shared history can disrupt others; coordinate or use revert |

## 11. Takeaways

For commit-level resets, `git reset --mixed <commit>` affects two areas: HEAD/branch is moved to the target commit, and the index is reset to that commit's snapshot. The working tree is left untouched, so content differing from the index becomes unstaged changes.

Remember three common cases:

- `git reset --mixed HEAD~1`: removes the latest commit from the branch tip, keeping content in the working tree as unstaged.
- `git reset` or `git reset --mixed HEAD`: unstages changes managed by the index, leaving the branch and working tree content unchanged.
- `git reset HEAD -- <file>`: unstages a specific path without moving HEAD.

Before resetting, inspect `git status`, diffs, and history. After resetting, check the state again to confirm the target commit and preserved content. This approach lets you use `--mixed` intentionally when reorganizing commits or adjusting the staging area.

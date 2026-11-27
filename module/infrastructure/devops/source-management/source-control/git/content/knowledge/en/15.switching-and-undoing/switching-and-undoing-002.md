# Git reset --soft Affects HEAD and Preserves the Index

In Git, a commit that has been created does not mean history must remain unchanged forever. When working on a personal branch, you may need to undo the last commit to recreate it with a better message, combine several small commits into a meaningful one, or add more content before recording it again. The `git reset --soft` command supports these scenarios by moving `HEAD` to another commit while leaving the staging area (index) and working tree untouched.

The most important point about `--soft` is that Git only changes the position of `HEAD` or the current branch. Staged content and in-progress files are preserved. Because the `HEAD` comparison baseline has changed, the status shown in `git status` may look different even though the index and working tree were not modified.

## 1. Reviewing HEAD, the Index, and the Working Tree

To understand `git reset --soft`, first distinguish the three components in a repository.

| Component | Role | Question to answer |
| --- | --- | --- |
| HEAD | Identifies the current commit; usually points to the checked-out branch | Which commit are you currently on? |
| Index (staging area) | Stores content selected for the next commit | Which content has been prepared to commit? |
| Working tree | The actual files in the project directory | What changes do you currently have on files? |

You can inspect the state with:

~~~bash
git status
git log --oneline --decorate -5
git diff
git diff --cached
~~~

- `git status` shows staged changes, unstaged changes, and untracked files.
- `git log` shows recent commits and where the current branch points.
- `git diff` compares the working tree with the index, i.e., unstaged changes.
- `git diff --cached` compares the index with `HEAD`, i.e., changes staged for commit.

The two diff commands compare two different pairs of states. Therefore, a change can appear in `git diff --cached` without appearing in `git diff`.

## 2. What Does Git reset --soft Do?

Syntax:

~~~bash
git reset --soft <commit>
~~~

`<commit>` is the historical point you want `HEAD` or the current branch to point to. You can use a commit hash, branch name, tag, or an expression like `HEAD~1`.

When running this command, Git:

1. Moves `HEAD` to the target commit. If a normal branch is checked out, that branch reference is moved.
2. Keeps the index exactly as it was before the command.
3. Keeps the working tree exactly as it was before the command.

In other words, `--soft` does not check out the content of the target commit and does not revert files in the working directory to an older state. It only changes the historical baseline against which the index is compared.

### 2.1. Illustration with commit history

Suppose the branch currently has the history:

~~~text
A --- B --- C  (HEAD -> feature/payment)
~~~

You want to remove commit `C` from the branch tip while keeping all of that commit's content in the staging area:

~~~bash
git reset --soft HEAD~1
~~~

After the command, the branch points to `B`:

~~~text
A --- B  (HEAD -> feature/payment)

Index:        still keeps pre-reset content
Working tree: still keeps pre-reset files
~~~

Commit `C` is no longer the current branch tip, but the commit object is not immediately deleted from the repository. It can still be recovered via the reflog during Git's retention period or through another reference such as a backup branch.

Because the index still contains the pre-reset content, Git shows the difference between `B` and the index as staged changes. This is how `reset --soft` retains the content of the commit just removed from the branch tip.

### 2.2. The index is unchanged, yet staged status can change

Distinguish two points:

- **Index content does not change:** the blobs and modes currently staged remain the same as before running the command.
- **Comparison result against HEAD changes:** because HEAD moved back to a different commit, `git diff --cached` may display more staged changes.

For example, before reset:

- `HEAD` points to commit `C`.
- The index contains the content of `C`.
- The working tree has an additional unstaged edit.

After `git reset --soft HEAD~1`:

- `HEAD` points to `B`.
- The index still contains the content of `C`.
- The working tree still contains the unstaged edit.

Then:

- `git diff --cached` shows the difference between `B` and the index, which typically includes the content of commit `C`.
- `git diff` still shows the difference between the index and the working tree, i.e., the previous unstaged edits.

Do not interpret the appearance of additional staged changes as Git automatically re-staging files. The index stayed the same; only the baseline commit used for comparison changed.

## 3. Common Use Cases

### 3.1. Undoing the last commit while keeping changes staged

Suppose you just created a commit and realize the message is unclear or you want to add content before recreating the commit.

Check first:

~~~bash
git status
git log --oneline -5
~~~

If the last commit is the one to remove from the branch tip:

~~~bash
git reset --soft HEAD~1
~~~

Check after resetting:

~~~bash
git status
git diff --cached
git diff
~~~

The changes from the removed commit remain in the index. You can continue editing the working tree, stage the additions, and create a new commit:

~~~bash
git add src/PaymentService.java
git diff --cached
git commit -m "Validate payment reference"
~~~

The result is a branch with a new commit containing the prepared content. The new commit hash will differ from the old commit because the history changed.

### 3.2. Combining two or more recent commits into one commit

While working, you might create small commits like:

~~~text
A --- B --- C --- D  (HEAD -> feature/payment)
~~~

If you want to combine `C` and `D` into a single commit, you can move HEAD back to `B` and keep the content of both commits in the index:

~~~bash
git reset --soft HEAD~2
git status
git diff --cached
~~~

Then create the new commit:

~~~bash
git commit -m "Implement payment validation"
~~~

The history then looks like:

~~~text
A --- B --- E  (HEAD -> feature/payment)
~~~

Where `E` contains the combined content from `C` and `D`. The old commits are no longer on the current branch's path.

Before combining, check whether the commits share the same purpose. Avoid squashing independent changes if keeping them separate makes code review, bug tracking, or reverting easier.

### 3.3. Combining the last commit with currently staged changes

Suppose you committed part of your work, then discovered a small adjustment was needed. You make the edit and stage the addition:

~~~bash
git add src/PaymentService.java
git status
~~~

If you want to create a new commit containing both the previous commit and the staged addition:

~~~bash
git reset --soft HEAD~1
git diff --cached
git commit -m "Complete payment validation"
~~~

Because the index is preserved, it contains the old commit's content along with the changes staged after that commit. The working tree is also preserved, including any unstaged changes.

Before recommitting, inspect `git diff --cached` carefully to avoid including previously staged files that do not belong to the new commit's purpose.

### 3.4. Changing the content and message of the last commit

If you only want to edit the message or add a small change to the last commit, `git commit --amend` is usually more direct:

~~~bash
git add src/PaymentService.java
git commit --amend
~~~

An alternative is using `reset --soft HEAD~1`, followed by creating a new commit. Both approaches create a new commit replacing the old commit at the branch tip, though amending expresses the intent of editing the last commit more clearly.

Choose the approach that fits your team's workflow. If the commit has already been pushed and others are basing work on it, both amending and resetting then recommitting rewrite shared history.

## 4. Safe Execution Workflow

Before running `git reset --soft`, identify the exact target commit and preserve a reference to the current branch tip if needed.

### 4.1. Checking status and history

~~~bash
git status --short --branch
git branch --show-current
git log --oneline --decorate -5
git diff
git diff --cached
~~~

Confirm that:

- You are on the right branch whose history needs editing.
- The commit you intend to undo or combine is in the expected position.
- Existing staged and unstaged changes are clearly understood.
- There are no unrelated changes that you would accidentally include in the new commit.

### 4.2. Creating a backup branch for the current branch tip

If the operation affects multiple commits or you are not yet comfortable with reset, you can create a backup branch pointing to the current commit:

~~~bash
git branch backup/before-soft-reset
~~~

The backup branch name must not already exist. If it does, choose another name so you do not alter a reference currently in use.

The backup branch holds a reference to the old commit. It preserves the commit point, not separate changes sitting in the index or working tree; inspect and preserve those changes too if they are important. If you need to return HEAD to the starting point, you can use the backup reference.

### 4.3. Running reset with an explicit target

To move HEAD back one commit:

~~~bash
git reset --soft HEAD~1
~~~

To move back two commits:

~~~bash
git reset --soft HEAD~2
~~~

Or specify a commit hash directly:

~~~bash
git reset --soft a1b2c3d
~~~

Commit hashes in examples are illustrative only. Replace them with actual commits identified via `git log`.

### 4.4. Re-checking the index and working tree

After resetting:

~~~bash
git status
git diff --cached
git diff
git log --oneline --decorate -5
~~~

Check whether the staged content is truly what you want to put into the next commit. If there are unstaged changes, they still appear in `git diff`.

Once confirmed, you can:

- Continue editing and stage the needed files.
- Partially unstage using `git restore --staged <file>` if you do not want to include that file in the next commit.
- Create a new commit with `git commit`.

Example:

~~~bash
git restore --staged docs/draft.md
git diff
git diff --cached
git commit -m "Refine payment validation"
~~~

The `git restore --staged` command only returns the staged content of the path to its state in the current HEAD; it keeps the working tree content. After a soft reset, HEAD has moved back to a new point, so inspect the diff before using it.

## 5. Comparing reset --soft, reset --mixed, and reset --hard

The three reset modes differ in how much they affect the index and working tree.

| Mode | Moves HEAD/branch | Updates index | Updates working tree |
| --- | --- | --- | --- |
| `--soft` | Yes | Unchanged | Unchanged |
| `--mixed` | Yes | Resets to target commit | Unchanged |
| `--hard` | Yes | Resets to target commit | Resets to target commit |

### 5.1. --soft

~~~bash
git reset --soft HEAD~1
~~~

Use this when you want to remove a commit from the branch tip while keeping all of that commit's content in the staging area. This is the right mode when preparing to recreate or squash commits.

### 5.2. --mixed

~~~bash
git reset --mixed HEAD~1
~~~

This is the default mode if neither `--soft` nor `--hard` is specified. It moves HEAD and updates the index to match the target commit, without updating the working tree.

Therefore, changes from the removed commit typically appear in the working tree as unstaged changes. You can selectively re-stage parts using `git add`.

### 5.3. --hard

~~~bash
git reset --hard HEAD~1
~~~

This mode moves HEAD, updates the index, and overwrites the working tree to match the target commit. Uncommitted changes to tracked files can be overwritten and lost. Untracked files are usually preserved, unless they obstruct writing a tracked file from the target commit; in that case Git may delete them.

Only use `--hard` when you have confirmed you want to discard working tree changes. If your goal is only to undo a commit while keeping its content, `--soft` or `--mixed` is more appropriate.

## 6. Comparing reset --soft with revert

`reset --soft` and `git revert` solve two different needs.

| Criterion | `git reset --soft` | `git revert` |
| --- | --- | --- |
| How it works | Moves HEAD/branch to another commit | Creates a new commit reversing the changes |
| Old commit | No longer on the current branch tip | Remains in history |
| Index | Unchanged | Changes are prepared for the revert commit according to the workflow |
| Best suited for | Editing local history, squashing, or recreating commits | Undoing shared changes |
| Impact on others | May require resynchronizing if already pushed | Usually easy to coordinate on shared branches |

If the commit has already been pushed to a shared branch, `git revert` is usually the safer choice:

~~~bash
git revert <commit>
~~~

The command creates a new commit that has the opposite effect of the specified commit. It preserves a record of both the original change and the undo in history.

Do not use `reset --soft` to silently rewrite history on a shared branch. If the team actively requires rewriting history, coordinate with everyone using the branch and push the updated history according to the agreed workflow.

## 7. Recovering If You Reset to the Wrong Commit

### 7.1. Using the backup branch

If you created a backup branch before resetting:

~~~bash
git reset --soft backup/before-soft-reset
~~~

This moves HEAD or the current branch back to the commit the backup points to, while keeping the current index and working tree. Re-check `git status` and diffs after the operation.

### 7.2. Using reflog to find the old branch tip

If you did not create a backup, reflog usually records updates to HEAD and local branches:

~~~bash
git reflog
~~~

For example, you may see an entry recording the recent reset operation and the previous commit. Identify the exact old commit hash and create a rescue branch:

~~~bash
git branch rescue/before-reset <old-commit>
~~~

Or, if you are certain you want to move the current branch back to that commit while keeping the index and working tree:

~~~bash
git reset --soft <old-commit>
~~~

Reflog is a local log and has a retention period. It is useful for finding a commit recently detached from a branch, but it does not replace a long-term backup. When you realize you reset by mistake, check reflog promptly and create a rescue branch before running any further history-overwriting commands.

### 7.3. Understanding recovery limits

After `reset --soft`, the old commit usually still exists in the object database even though it is no longer referenced by the current branch. Git may clean up unreferenced objects after a period of time through garbage collection. Therefore, do not treat reflog recovery as a permanent guarantee.

If the content is important, create a backup branch or copy before editing history.

## 8. Special Considerations

### 8.1. Detached HEAD

If you are in a detached HEAD state, `HEAD` points directly to a commit rather than through a local branch. When running:

~~~bash
git reset --soft <commit>
~~~

Git moves HEAD to the target commit without moving any normal local branch. If you want to continue developing work, create or switch to an appropriate branch before modifying history.

Check detached state with:

~~~bash
git status -sb
git branch --show-current
~~~

If `git branch --show-current` prints no branch name, you may be in detached HEAD state.

### 8.2. HEAD~1 and HEAD^ in history with merge commits

`HEAD~1` is equivalent to the first parent of the current commit. `HEAD~2` follows the first parent one step further. With merge commits, there are multiple parents, so `HEAD~1` does not mean every parent branch is chosen.

Before resetting a merge commit, inspect the graph:

~~~bash
git log --oneline --graph --decorate -10
~~~

If you want to select a specific parent or another point, specify the commit hash explicitly rather than relying on relative notation.

### 8.3. Soft reset does not switch to another branch

The name `reset` sometimes makes beginners confuse it with switching branches. `git reset --soft` is not used to switch to a different branch. It moves HEAD or the current branch to the target commit.

To switch branches, use:

~~~bash
git switch main
~~~

To move the current branch tip while keeping the index and working tree, use:

~~~bash
git reset --soft <commit>
~~~

The two operations serve different purposes.

## 9. Comprehensive Example: Squashing Two Bugfix Commits

Suppose you are working on branch `bugfix/invoice-rounding` and created two commits:

~~~text
a10f2c1 Fix decimal conversion
b21a3d4 Add rounding boundary case  (HEAD -> bugfix/invoice-rounding)
~~~

You want to combine them into a single commit because both address the same rounding bug.

**Step 1 — Check history and status**

~~~bash
git status --short --branch
git log --oneline -5
git diff
git diff --cached
~~~

Confirm there are no unexpected changes.

**Step 2 — Create a backup branch**

~~~bash
git branch backup/invoice-rounding-before-squash
~~~

**Step 3 — Move HEAD back two commits while keeping the index**

~~~bash
git reset --soft HEAD~2
~~~

**Step 4 — Inspect the content that will go into the new commit**

~~~bash
git status
git diff --cached
git diff
~~~

The index now holds the content from the two previous commits. If there were prior unstaged changes, they remain in the working tree and should be reviewed separately.

**Step 5 — Create the combined commit**

~~~bash
git commit -m "Fix invoice rounding boundaries"
~~~

**Step 6 — Verify the new history**

~~~bash
git log --oneline --decorate -5
git status
~~~

The current branch now has one combined commit in place of the two old ones. The backup branch still retains the original history point for reference if needed.

If the two old commits had already been pushed and others are using the branch, coordinate before updating the rewritten history. When squashing history is unnecessary, you can keep both commits and continue development.

## 10. Common Mistakes

- **Assuming soft reset deletes commit content:** the command only moves HEAD or the branch; content remains in the index and working tree.
- **Assuming an unchanged index means git status will not change:** staged status is computed by comparing the index with HEAD, so additional staged changes can appear after reset.
- **Confusing soft with mixed:** mixed updates the index to match the target commit, whereas soft leaves the index unchanged.
- **Using hard reset when you only want to undo a commit:** this can cause loss of uncommitted changes on tracked files.
- **Resetting the wrong number of commits:** `HEAD~2` steps back twice along the first parent. Inspect the graph and commit hashes before running it.
- **Resetting shared history without coordination:** causes other clones to diverge and may require a force push. On shared branches, consider revert.
- **Not checking staged changes before the new commit:** unrelated changes might be bundled into the same commit.
- **Treating reflog as a permanent backup:** reflog has a retention limit. Create a backup branch when you need to preserve an important point.

## 11. Quick Reference Table

| Goal | Command |
| --- | --- |
| View HEAD and history | `git log --oneline --decorate -5` |
| View unstaged changes | `git diff` |
| View staged changes | `git diff --cached` |
| Undo last commit, keep staged changes | `git reset --soft HEAD~1` |
| Undo last two commits, keep staged changes | `git reset --soft HEAD~2` |
| Move HEAD to a specific commit, keep index | `git reset --soft <commit>` |
| Create backup branch before reset | `git branch backup/before-soft-reset` |
| View HEAD movement history | `git reflog` |
| Undo a commit in history with a reversing commit | `git revert <commit>` |
| Reset staged content to current HEAD | `git restore --staged <file>` |

## 12. Summary

`git reset --soft` is a tool for adjusting history at the branch tip by moving HEAD or the branch reference to another commit while leaving the index and working tree unchanged. Because the index does not change, content present before the reset is preserved; however, when HEAD moves back, the difference between the new HEAD and the index will be displayed as staged changes.

This command fits scenarios where you undo the last commit while keeping its content to recreate it, combine multiple commits, or prepare a new commit with a clearer purpose. Before using it, inspect history, staged and unstaged status, consider creating a backup branch, and verify afterward with `git status`, `git diff --cached`, and `git diff`.

For shared history, consider the impact on others. If the goal is to undo changes on a shared branch while preserving history, `git revert` is usually more suitable. Understanding the exact scope of each command helps you edit history with control and keep important work intact.

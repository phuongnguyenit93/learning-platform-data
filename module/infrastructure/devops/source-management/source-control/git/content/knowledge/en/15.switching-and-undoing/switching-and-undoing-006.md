# Git revert Creates a Reversing Commit on Shared History

When a commit has already been pushed to a shared branch and needs to be undone, deleting or rewriting the old commit can cause teammates' histories to diverge. `git revert` solves this situation by creating a new commit containing changes that reverse the selected commit. The old commit remains in history, while the undo operation is explicitly recorded so everyone can pull or fetch normally.

## 1. What Is Revert?

Git stores history using immutable commits. Once a commit has been shared, you generally should not move a remote branch back to an older commit just to remove a change. Instead, create a new commit to bring the project content to the desired state.

Suppose the `main` branch has the history:

```text
A---B---C---D  main, origin/main
```

Commit `D` introduced a buggy change. When you run:

```bash
git revert D
```

Git creates a new commit `R` whose content reverses the changes of `D`:

```text
A---B---C---D---R  main
```

`D` remains in history. `R` is a normal commit whose parent is `D`, recording the undo. The branch moves forward rather than backward.

Revert is appropriate when:

- The commit has already been pushed to a shared branch.
- The team wants to undo a change while preserving a trace in history.
- You need to create a change that can be reviewed, tested, and pushed through the normal workflow.
- You want to undo a specific commit without rewriting subsequent commits behind it.

## 2. How Does Revert Differ from Reset?

Both commands can be used in situations people call "undo," but they affect history differently.

| Criterion | `git revert` | `git reset` |
|---|---|---|
| How it works | Creates a new commit reversing the selected changes | Moves the current branch to another commit and optionally updates the index/working tree |
| Old commit | Preserved in history | May no longer be referenced by the current branch |
| Best suited for | Undoing shared changes | Adjusting unshared local history or moving a branch to a different state |
| Impact on remote branch | Can be pushed via normal fast-forward | If rewriting pushed history, usually requires a force push and team coordination |

For example, if `D` has already been fetched by multiple people, resetting the remote branch to `C` can leave others still holding `D` in their local history. When they synchronize, the two histories no longer match. Revert creates `R` on top of `D`, so everyone continues sharing the same line of history.

`git revert` is not a command to delete a commit from the repository. It creates a new change aimed at reversing the old commit's effect.

## 3. How Git Creates a Reversing Commit

For a normal commit, Git compares that commit's content with its parent commit to determine the changes the commit introduced. Revert applies the inverse changes onto the current state.

For example, commit `D` adds the line:

```java
boolean allowGuestCheckout = true;
```

Revert can create a commit that removes that line. If a later commit `E` modified the same area, Git must apply `D`'s reversed changes onto the current content after `E`. The result might not apply automatically and may require you to resolve conflicts.

The key point is that revert does not literally restore the exact directory tree from `D`'s parent commit. It applies a reversing patch onto the current `HEAD`. Other changes created after `D` are preserved if they do not conflict with the reversing patch.

## 4. Workflow for Reverting a Shared Commit

First, inspect the repository and working tree:

```bash
git status -sb
git log --oneline --decorate -10
```

Make sure you are on the right branch and have no uncommitted changes that need preserving. Identify the exact commit to undo by hash, message, and diff content:

```bash
git show --stat --oneline <commit>
git show --format=fuller <commit>
```

After confirming the target commit, run:

```bash
git revert <commit>
```

Git applies the reversed changes and usually opens an editor for you to confirm the commit message. By default, the message typically takes the form `Revert "..."` and references the original commit.

Inspect the new commit and the modified content:

```bash
git status
git show --stat --oneline HEAD
git show --format=fuller HEAD
```

Run appropriate tests or checks to confirm the bug is resolved and related features still work. If the result passes, push the revert commit:

```bash
git push origin main
```

Replace `main` with the actual branch. Because the revert commit is created on the current tip, a normal push is typically a fast-forward. If someone else pushed new commits while you were working, fetch and integrate the new changes according to your team's workflow before pushing again.

## 5. When Revert Encounters Conflicts

Conflicts can happen if commits after the one being undone modified the same content area. Git cannot automatically decide an outcome that both reverses the old change and keeps the new changes.

Example:

- Commit `D` adds an old fee calculation method.
- Commit `E` updates the formula and adds a new condition based on the code from `D`.
- You revert `D` at the current state that already includes `E`.

If you delete the entire code block according to `D`, you might accidentally delete the valid condition added by `E` as well. Inspect both the original change and the current content before editing.

When Git reports a conflict:

```bash
git status
git diff
```

Edit each file to achieve the meaningful result, then stage the resolved files and continue:

```bash
git add path/to/resolved-file
git revert --continue
```

If you want to cancel an in-progress revert that paused:

```bash
git revert --abort
```

`--abort` returns the repository to the state before the current revert operation started. Before using it, check status and ensure any uncommitted changes of yours are safely saved.

## 6. Reverting Multiple Commits

You may need to reverse multiple commits, but identify dependency relationships beforehand. If commits are sequential and a later commit builds on an earlier commit's changes, you usually need to undo from the newer commit back to the older commit to reverse dependencies in reverse order.

Example history:

```text
A---B---C---D---E  main
```

If you want to reverse both `D` and `E`, you can run each command in order:

```bash
git revert E
git revert D
```

After each command, inspect the content and run necessary tests. The actual order should be based on dependencies between the changes; for independent commits, confirm the final result is still correct.

If you want to apply multiple reversing changes into the index and working tree and then create a single combined commit, you can use `--no-commit`:

```bash
git revert --no-commit E
git revert --no-commit D
git diff
git diff --cached
```

After carefully inspecting the result and passing tests, create the commit manually:

```bash
git commit -m "Revert related changes"
```

`--no-commit` does not create a commit after each revert; changes are placed into the index and working tree for you to review before committing. Check status between steps. If one revert stops due to a conflict, resolve it and run `git revert --continue` per Git's instructions before continuing the sequence.

Avoid reverting a large range of commits just to return to an older state without understanding the changes in that range. If multiple commits have dependencies, list the commits to undo, check each commit's diff, and confirm the final outcome with the team.

## 7. Reverting a Merge Commit

A merge commit has two or more parents. Therefore, Git needs to know which parent you want to treat as the *mainline* when calculating the changes to reverse.

Inspect the parents of a merge commit:

```bash
git show --no-patch --pretty=raw <merge-commit>
```

The output lists `parent` lines in order. In a typical merge, the first parent is usually the commit of the branch that was checked out when performing the merge; the second parent is usually the tip of the branch that was merged in. This order must be verified from the commit itself rather than guessed solely from branch names.

To revert a merge commit and choose the first parent as the mainline:

```bash
git revert -m 1 <merge-commit>
```

`-m 1` means selecting parent number 1 as the mainline when determining which changes to reverse. Choosing parent number 2 calculates the reversal from the opposite direction. Choosing the wrong mainline can remove unintended changes from the codebase.

### Implications for future merges

Reverting a merge commit does not remove the merged branch's commits from the history graph. It creates a new commit reversing the changes that the merge introduced into the content tree.

This has an important consequence: if you later re-merge the same branch that was previously merged, Git knows that branch's old commits are already ancestors in history. The reverted changes may not be brought back as a normal new merge; the subsequent merge primarily brings in new commits not yet in shared history.

If the team wants to bring back the changes from a reverted merge, it may be necessary to revert the earlier revert commit itself, or create new commits re-expressing the desired changes. Review history and agree on the recovery approach before taking action.

## 8. Reverting a Revert Commit

Sometimes you undo a commit because a bug was found, then the bug is fixed and you want to bring the feature back. If the previous revert commit is `R`, you can revert `R`:

```bash
git revert <revert-commit>
```

This operation creates a new commit reversing the effect of `R`, which in terms of content typically restores the original change. History will record the original commit, the revert commit, and the revert-of-revert commit.

However, if other commits modified the same area after `R`, reverting `R` may conflict or require adjustments. Do not assume this operation always restores every byte identically; inspect the diff and run tests afterward.

## 9. Using `--no-edit` and `--no-commit`

These two options address two different needs:

| Option | Effect |
|---|---|
| `--no-edit` | Uses the default revert message without opening an editor |
| `--no-commit` (`-n`) | Applies reversed changes to the index/working tree without immediately creating a commit |

Example:

```bash
git revert --no-edit <commit>
```

The command creates a revert commit with the default message without opening an editor. Meanwhile:

```bash
git revert --no-commit <commit>
```

This command only prepares the reversing changes for you to review. You can then continue editing, run tests, and create the commit manually once you confirm the result.

## 10. Limits of Revert with Data and External Effects

Git revert only changes content managed inside the repository. It does not automatically reverse effects that have already happened outside Git, for example:

- Migrations already executed on a production database.
- Emails, notifications, or transactions already sent to customers.
- Cloud resources already created or deleted.
- Files or data already written to volumes, object storage, or other systems.

For example, reverting a commit containing an SQL migration does not automatically roll a running database back to the old schema. You need a new intentional migration reversing the schema or an appropriate data recovery procedure. For transactions already sent, compensating business actions may be needed instead of erasing transaction traces.

Before reverting a commit involving data or deployments, determine which environments executed that change and plan compensating steps for every affected system.

## 11. Common Mistakes When Using Revert

- **Selecting the wrong commit:** always check the hash, message, and diff before reverting.
- **Thinking revert deletes the old commit:** the original commit remains in history; the new commit only reverses its content effect.
- **Reverting without checking subsequent changes:** a reversing patch can affect new logic added after the original commit.
- **Choosing the wrong mainline when reverting a merge:** check parent order with `git show --pretty=raw` before using `-m`.
- **Using `--skip` or skipping changes without understanding:** if a revert stops, identify the exact commit and skipped content before continuing.
- **Assuming Git rolls back external systems:** create separate migrations or compensating operations for modified data and services.
- **Using reset/force push on shared branches instead of revert:** that rewrites history and can cause others to lose work they already pulled.

## 12. Practical Workflow: Undoing a Pushed Commit

Suppose you pushed commit `abc1234` to `main`, then discovered a buggy change. The team agrees to undo it with a new commit.

1. Check the branch, working tree, and history:

   ```bash
   git status -sb
   git log --oneline --decorate -10
   git show --stat --oneline abc1234
   ```

2. Fetch updates from the remote and confirm you are working on the latest base:

   ```bash
   git fetch origin
   git log --oneline --graph --decorate HEAD origin/main
   ```

   If local `main` is behind, integrate remote commits according to your team's workflow before reverting.

3. Create the reversing commit:

   ```bash
   git revert abc1234
   ```

4. Inspect the new commit, run tests, and verify related features:

   ```bash
   git show --stat --oneline HEAD
   git status
   ```

5. Once the result passes and the branch is still clear to update, push the revert commit:

   ```bash
   git push origin main
   ```

If the remote received additional commits while you were working, the push may be rejected as non-fast-forward. Fetch, inspect the new history, and integrate per your workflow; do not force push just to bypass the rejection.

## 13. Takeaways

`git revert` is the appropriate undo method for shared history because it creates a new reversing commit while keeping the old commit intact. Identify the right commit, inspect subsequent changes, choose the right mainline when reverting a merge commit, and run tests before pushing. For data or external effects outside the repository, separate compensating actions are required; Git cannot automatically undo things that have already happened in external systems.

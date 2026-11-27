# Fast-Forward Merge and Cases Without a Merge Commit

When you merge a branch into the current branch, Git does not always create a merge commit. If the tip of the current branch is an ancestor of the branch being merged, Git can **fast-forward**: simply moving the ref of the current branch to the newer commit. History retains all existing commits, but no new merge commit is created.

Beyond fast-forward, there are other situations that do not produce a merge commit: the current branch already contains the entire history of the branch being merged (already up to date), or you use `git merge --squash` to prepare a snapshot and manually create a regular commit. The options `--ff`, `--ff-only`, and `--no-ff` let you control the integration policy, while `--no-commit` has an important limitation during a fast-forward.

## 1. Understanding Fast-Forward Through Ancestry

A branch in Git is a ref pointing to a commit. Suppose `main` points to commit B and `feature/search` has created two additional commits C and D from B:

```text
A---B---C---D  feature/search
     ^
    main
```

The commit that `main` points to is an ancestor of the commit that `feature/search` points to. If you are on `main` and run:

```bash
git switch main
git merge feature/search
```

Git can move the `main` ref straight from B to D. There is no need to create a new commit because `main`'s history is already completely contained within `feature/search`'s history.

After the operation:

```text
A---B---C---D  main, feature/search
```

Commits C and D remain the original commits. Git merely updates the position of the `main` branch; the OIDs of C and D do not change and no new merge commit is created.

### Condition for Fast-Forward

A fast-forward can occur when the tip of the current branch is an ancestor of the tip of the branch being merged. Check with:

```bash
git merge-base --is-ancestor main feature/search
```

If the command returns exit code `0`, the tip commit of `main` is an ancestor of the tip commit of `feature/search`, so `main` can fast-forward to `feature/search` unless an option or policy prevents it. A non-zero exit code means this ancestry condition does not hold.

You can also inspect the graph:

```bash
git log --graph --oneline --decorate --all
```

Fast-forward is not "combining file contents in a simpler way." It is a ref update operation because the current branch has no separate history to reconcile. If both branches have developed independently since their common ancestor, Git needs a real merge or must abort if you require fast-forward only.

## 2. Fast-Forward Does Not Create a Merge Commit

A merge commit is a new commit with a resulting tree and typically two parents: the tip of the current branch before the merge and the tip of the branch being merged. Fast-forward does not create a new commit object; the target branch simply moves to an existing commit.

Compare the two states:

Before merge:

```text
A---B---C---D  feature
     ^
    main
```

After fast-forward:

```text
A---B---C---D  main, feature
```

If you want to record an explicit integration point in history even when fast-forward is possible, use `--no-ff` to force a merge commit (explained in the next section).

Fast-forward is still a merge in terms of branch integration, but it does not create a merge commit. The feature commits become part of the history reachable from the target branch because the target ref moved to the feature's last commit.

## 3. Using --ff, --ff-only, and --no-ff

The three options have different meanings:

| Option | When fast-forward is possible | When the two branches have diverged |
|---|---|---|
| `--ff` | Allows fast-forward | Performs merge and creates a merge commit if the merge succeeds |
| `--ff-only` | Fast-forward only | Refuses, does not create a merge commit |
| `--no-ff` | Does not fast-forward; creates a merge commit | Performs three-way merge and creates a merge commit if successful |

### --ff

```bash
git switch main
git merge --ff feature/search
```

`--ff` allows Git to fast-forward if the ancestry relationship permits. If the two branches have diverged, Git performs a normal merge and creates a merge commit after successfully combining changes. This option can be used to explicitly allow fast-forward even when the `merge.ff` configuration is disabled.

### --ff-only

```bash
git switch main
git merge --ff-only feature/search
```

`--ff-only` requires the operation to succeed only if a fast-forward is possible. If the current branch and the branch being merged have diverged, Git refuses instead of automatically creating a merge commit. This is useful when a team wants linear history and wants divergence handled explicitly by updating branches first.

Example message you might encounter:

```text
fatal: Not possible to fast-forward, aborting.
```

In that case, fetch and inspect the separate commits on both sides before deciding whether to rebase or merge according to your team's workflow.

### --no-ff

```bash
git switch main
git merge --no-ff feature/search
```

`--no-ff` prevents Git from using fast-forward even when the current branch is an ancestor of the branch being merged. Git creates a merge commit to mark the integration. The history clearly shows that the feature branch was integrated as a unit.

Example:

```text
      C---D------+
     /           \
A---B-------------M  main
```

Commit M has its first parent as B (the tip of `main` before the merge) and its second parent as D (the tip of `feature/search`).

## 4. The Already Up to Date Case

Another case that does not create a merge commit is when the current branch already contains the entire history of the branch being merged.

Example:

```text
A---B---C---D  main
         ^
        feature
```

If you are on `main` and run:

```bash
git merge feature
```

Git reports:

```text
Already up to date.
```

No ref needs to move and no new merge commit is created. The tip of `feature` is already reachable from `main`.

Check this relationship:

```bash
git merge-base --is-ancestor feature main
```

If it returns exit code `0`, the tip of `feature` is an ancestor of `main`; therefore, merging `feature` into `main` requires no new changes. This differs from fast-forward: fast-forward moves the target branch forward, whereas already up to date means the target branch already stands at a position that includes the commit to be merged.

`--no-ff` also does not create a merge commit in the already up-to-date case, because there are no new commits or changes to integrate. `--no-ff` forces a merge commit when there is new history from the merged side and Git could normally fast-forward; it does not create an empty merge commit merely to record running the command.

## 5. Comparison Table of the Three States

| Situation | Before operation | Result |
|---|---|---|
| Fast-forward | `main` is an ancestor of `feature` | `main` moves to tip of `feature`; no merge commit |
| Already up to date | `feature` is an ancestor of `main` | Ref unchanged; no merge commit |
| Two branches diverged | Each branch has separate commits | Three-way merge; typically creates a merge commit |
| `--no-ff` when feature has new commits | `main` is an ancestor of `feature` | Creates a merge commit even though fast-forward is possible |
| `--ff-only` when two branches diverged | No valid fast-forward relationship | Refuses; no merge commit created |

Distinguishing these cases helps you read Git's messages accurately. Not every `git merge` execution creates a new commit.

## 6. When Two Branches Have Diverged

If both branches have their own commits after the common ancestor, fast-forward cannot update the target branch while preserving both lines of history.

```text
      C---D  feature/search
     /
A---B---E---F  main
```

Here `main` has E and F, while feature has C and D. The tip of `main` is not an ancestor of the tip of feature, and the tip of feature is not an ancestor of main either. Check:

```bash
git merge-base --is-ancestor main feature/search
git merge-base --is-ancestor feature/search main
git merge-base main feature/search
```

Both `--is-ancestor` commands fail when the two branches have diverged as shown in the diagram. The final `git merge-base` command identifies the common ancestor for Git to perform a three-way merge.

In this situation:

- `git merge --ff-only feature/search` will refuse.
- `git merge --ff feature/search` will perform the merge and create a merge commit if there are no errors/conflicts.
- `git merge --no-ff feature/search` will also create a merge commit; `--no-ff` does not change the need to combine both sides.

## 7. Fast-Forward Policy in Configuration

You can configure how `git merge` handles fast-forward by default.

View the current value:

```bash
git config --show-origin --get merge.ff
```

Common values:

| Value | Default behavior |
|---|---|
| `true` | Allows fast-forward when possible (standard default behavior) |
| `false` | Always creates a merge commit when there is new history to merge, even if fast-forward is possible |
| `only` | Only allows fast-forward; refuses if branches have diverged |

Set in the current repository:

```bash
git config --local merge.ff only
```

Set for all repositories of the current user:

```bash
git config --global merge.ff false
```

Choose the configuration scope that fits your workflow. Local config affects only the current repository; global affects the user's repositories unless overridden by a higher-precedence configuration.

Command-line options override the default policy for a single merge:

```bash
git merge --ff feature/search
git merge --ff-only feature/search
git merge --no-ff feature/search
```

## 8. Fast-Forward in git pull

`git pull` essentially fetches and then integrates changes from upstream into the current branch using merge or rebase depending on configuration and options. The fast-forward policy for the merge step can be controlled with `pull.ff`.

Check configuration:

```bash
git config --show-origin --get pull.ff
git config --show-origin --get pull.rebase
```

Common values for `pull.ff`:

- `true`: allows fast-forward when possible.
- `false`: requires a merge commit instead of fast-forward when a merge is performed.
- `only`: accepts fast-forward only; if branches have diverged, pull stops.

Example:

```bash
git pull --ff-only
```

This command is suitable when you want to update a local branch solely by advancing the ref to the upstream commit. If local has its own commits and remote also has its own commits, Git refuses so you can decide how to integrate.

Do not confuse `pull.ff` with `pull.rebase`. `pull.rebase` determines whether pull uses rebase or merge; `pull.ff` controls the fast-forward policy when a merge operation is used. Always check effective configuration before running `git pull` in a repository with team policies.

## 9. Why Doesn't --no-commit Stop a Fast-Forward?

`--no-commit` tells Git to pause before creating a merge commit so you can inspect the result. However, fast-forward does not create a merge commit; Git simply moves the branch ref to an existing commit. Because there is no merge commit to pause before creating, `git merge --no-commit` cannot prevent a fast-forward.

If you want to inspect the result before creating a merge commit, combine:

```bash
git merge --no-ff --no-commit feature/search
```

`--no-ff` ensures Git prepares a merge commit; `--no-commit` pauses before the commit is created. You can inspect:

```bash
git status
git diff --cached
git diff --check
```

After verifying the result, complete it:

```bash
git commit
```

Or cancel the paused merge:

```bash
git merge --abort
```

If you only use `--no-commit` and Git can fast-forward, the branch can still be updated immediately. That is why you need to add `--no-ff` when the goal is to review the snapshot before the merge commit.

## 10. --squash: Integration Result Without a Merge Commit

`git merge --squash <branch>` takes the changes from the specified branch relative to the current history and prepares the content in the working tree/index, without creating a merge commit and without recording a parent relationship to the merged branch.

Example:

```bash
git switch main
git merge --squash feature/search
git status
git diff --cached
git commit -m "Add search feature"
```

The commit you create afterward is a regular commit, typically having one parent—the tip of `main` before the squash. It contains the resulting snapshot, but does not have the tip of `feature/search` as a second parent. Therefore, Git does not treat the original feature commits as ancestors of main solely because of this squash commit.

Conceptual graph:

```text
      C---D  feature/search
     /
A---B---S    main
```

S is a regular commit containing the squashed changes. The feature branch still exists and may still be rejected by `git branch -d` because commits C and D are not reachable from main.

Differences between `--squash` and `--no-ff`:

| Command | Result |
|---|---|
| `git merge --no-ff feature` | Creates a merge commit with two parents when there are changes to integrate |
| `git merge --squash feature` | Stages changes in index/working tree; user creates a regular commit with no merge parent |

Choose squash when the team wants to combine changes into a single commit and accepts not preserving the ancestry of feature commits in the target branch. Choose a merge commit when you want to explicitly record the history of two branches being combined.

## 11. Summary of Cases That Do Not Create a Merge Commit

There are several reasons why a merge command does not produce a merge commit:

1. **Fast-forward:** the target branch is an ancestor of the branch being merged; Git moves the ref to an existing commit.
2. **Already up to date:** the target branch already contains the tip of the branch being merged; nothing needs to be integrated.
3. **Squash merge:** Git prepares the combined snapshot without creating a merge commit; the user creates a regular commit if they want to save the result.
4. **Merge aborted or failed before completion:** conflicts or errors can cause Git to stop without creating a merge commit. Only after resolving conflicts does the user complete it with a commit; or use `git merge --abort` to cancel.

Distinguish "no merge commit" from "no commit created at all." Fast-forward can point the branch to an existing commit; already up to date leaves history unchanged; squash lets you create a regular commit; an incomplete conflicted merge has not yet created a commit.

## 12. Inspecting the Result After Merging

After a successful merge, inspect both the graph and the content:

```bash
git status --short
git log --graph --oneline --decorate --all -12
git show -s --format="%H%n%P%n%s" HEAD
```

If it was a fast-forward, `HEAD` points to an existing commit from the merged branch; there is no new commit with two parents. If it was a merge commit, the `%P` line typically shows two parents. If it was a squash, the commit created afterward has only one parent.

Verify the ancestry relationship:

```bash
git merge-base --is-ancestor feature/search main
```

After a fast-forward, the command typically returns `0` because the feature tip has become an ancestor of or is identical to the main tip. After a merge commit, the feature tip is also reachable from main via the second parent. After a squash merge, the command may return non-zero because the original feature commits did not become ancestors of main.

Read the diff of the integration commit:

```bash
git show --stat HEAD
git diff HEAD^1 HEAD
```

For a merge commit, `HEAD^1` is the first parent; this diff shows how the merged snapshot differs from the first parent. For a regular squash commit, the first parent is the commit before the squash. Always run the necessary tests because Git does not evaluate business logic correctness.

## 13. Choosing the Right Policy for Your Workflow

| Team need | Typically suitable policy | Reason |
|---|---|---|
| Linear history, update only when branches have not diverged | `--ff-only` | Forces users to handle divergence explicitly |
| Record every feature integration with a merge commit | `--no-ff` | Preserves the merge milestone and two parents in the DAG |
| Allow fast-forward when possible, create merge commit when diverged | `--ff` or default | Flexible and common behavior |
| Single summary commit of feature changes | `--squash` | Target history does not keep feature commits as ancestry |
| Need to inspect result before creating merge commit | `--no-ff --no-commit` | Stops in the state of preparing a merge commit |

There is no single policy that fits every team. Choose based on review conventions, traceability, release practices, and history retention requirements. What matters is that team members understand the policy and do not accidentally alter how history is recorded across integrations.

## 14. Practical Workflow for Fast-Forward and Non-Merge-Commit Cases

In a test repository, create a base commit and a feature branch:

```bash
git switch -c feature/search
```

Create one or two commits on feature, then switch back to main:

```bash
git switch main
git merge-base --is-ancestor main feature/search
```

If the ancestry condition holds, try fast-forward:

```bash
git merge --ff-only feature/search
```

Observe the graph and parents of `HEAD`:

```bash
git log --graph --oneline --decorate --all
git show -s --format="%H %P %s" HEAD
```

Next, create another test branch to observe `--no-ff`:

```bash
git switch -c feature/report
# Create commit on feature/report
git switch main
git merge --no-ff feature/report
```

Verify there is a merge commit with two parents. Create a third test branch to observe squash:

```bash
git switch -c feature/cleanup
# Create commit on feature/cleanup
git switch main
git merge --squash feature/cleanup
git status
git diff --cached
git commit -m "Apply cleanup changes"
```

Verify that the squash commit is a regular commit and that the original commits of `feature/cleanup` did not become its parents. Use a dedicated test repository to avoid altering real project history.

## 15. Practice Exercise

Create a test repository with a `main` branch and a `feature/demo` branch from the same base commit.

1. Create two commits on `feature/demo` and no new commits on `main`.
2. Run `git merge-base --is-ancestor main feature/demo` and explain the result.
3. Run `git merge --ff-only feature/demo`, then inspect the graph and verify there is no merge commit.
4. Create a new feature branch, make a commit on it, then merge with `--no-ff`; verify the merge commit has two parents.
5. Create another feature branch and try `git merge --ff-only`; beforehand, create a separate commit on main so the two branches diverge, and observe Git refusing.
6. Try `git merge --no-commit` in a fast-forwardable situation and explain why this option does not prevent the ref from moving.
7. Try `git merge --no-ff --no-commit`, inspect the index/working tree before running `git commit`, then finish or abort.
8. Perform `git merge --squash`, create a regular commit, and compare its parents with a merge commit.
9. Set up a case where a branch is already fully merged and run `git merge` again; observe the `Already up to date` message and confirm no new commit is created.
10. Try setting `merge.ff` to `only` in the test repository, then check how `git merge` reacts when branches diverge.

You have completed the exercise when you can explain the fast-forward condition, distinguish fast-forward from already up to date, choose appropriately among `--ff`, `--ff-only`, and `--no-ff`, understand the limitation of `--no-commit`, and distinguish a merge commit from a commit created after a squash.

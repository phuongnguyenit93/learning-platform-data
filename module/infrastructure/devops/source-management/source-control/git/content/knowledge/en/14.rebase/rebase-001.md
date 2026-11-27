# Rebase copies commits onto a new base and changes commit IDs

Rebase moves a branch's unique commits onto a new history base. Git takes the changes from each commit, applies them one by one onto the new base commit, and creates replacement commits. Because the new commits have different parent relationships than the old commits, their identifiers also change, even if the change content is nearly identical. Understanding this mechanism helps you read history after a rebase, compare commits before and after, and avoid rewriting history that teammates are using.

## 1. What scenario does rebase solve?

Suppose you create a `feature/report` branch from `main`. Later, while you are developing the feature, `main` continues receiving new commits. Your feature branch is still based on the old base and has some commits of its own.

Before rebasing, the history might look like this:

```text
      D---E  feature/report
     /
A---B---C    main
```

- `B` is the common commit where the feature branch diverged.
- `C` is the new commit added to `main` after the feature branch diverged.
- `D` and `E` are the feature branch's own commits.

If you want the feature branch to continue from `C`, you can rebase `feature/report` onto `main`. After a successful rebase, the history along the new branch looks like this:

```text
A---B---C---D'---E'  feature/report
        ^
        main
```

The changes from `D` and `E` are replayed onto base `C`, creating `D'` and `E'`. The prime symbol (`'`) in the diagram is only used to distinguish the new commits from the old ones; it is not a notation Git displays in commit IDs.

As a result, the feature branch history becomes a linear sequence from `main` to the new commits. Rebase does not create a merge commit to join the two branches like a regular merge.

## 2. What does rebase do internally?

Conceptually, Git performs the following steps:

1. Identify the common base commit between the current branch and the target branch.
2. Identify the commits that exist on the current branch but are not yet in the target branch's history.
3. Temporarily reset the branch being rebased to the new base commit.
4. Take the changes of each unique commit in order and apply them onto the new base.
5. Create a new commit for each successfully applied change, then update the current branch to point to the final commit.

You can think of this operation as replaying each patch in sequence. Git does not simply move the old commits to another location, because a commit is an immutable object that links to its parent commit.

In the example above, parent relationships change as follows:

| Commit | Parent commit before rebase | Parent commit after rebase |
|---|---|---|
| `D` and `D'` | `B` | `C` |
| `E` and `E'` | `D` | `D'` |

Commit `D'` is created on `C`, so the next commit `E'` must reference `D'` as its parent. Therefore, when the first commit is recreated with a new ID, subsequent commits in the chain usually get new IDs as well.

## 3. Why do commit IDs change?

A commit identifier (commit ID or hash) is computed from the contents of the commit object. This object contains multiple pieces of information, including:

- Tree ID: the directory tree and file contents recorded by the commit.
- Parent ID: the parent commit; a merge commit can have multiple parents.
- Author: the person who made the change and the author timestamp.
- Committer: the person who created the commit object and the commit timestamp.
- Commit message and other metadata; signed commits also contain signature data.

Changing even one part of the commit object changes its identifier. During a rebase, the parent ID almost certainly changes when the commit is placed onto a new base. The committer timestamp is also typically updated when the commit is recreated. Thus, even if the diffs of `D` and `D'` look identical, the two commits still have different hashes.

For example:

```text
Old commit: 7ab31c2  parent = B
New commit: d92f840  parent = C
```

The hashes above are illustrative only. Do not infer whether two commits are the same or different simply by looking at the first few characters; inspect their contents, parents, and metadata.

### 3.1. Does the change content have to be identical?

No. Git attempts to apply the old commit's changes onto the new base. If the new base contains related changes, the resulting content after applying may differ from the file in the old commit. When conflicts occur, you must manually choose the combined result; the commit created afterward records the resolved content.

If there are no conflicts and the changes apply cleanly, the tree of the new commit may match the tree of the old commit. Even so, a changed parent or metadata is enough to produce a different hash.

### 3.2. How do author and committer differ?

The author usually remains the person who originally wrote the change. The committer is the person who creates the new commit during the rebase; the committer info and commit timestamp typically reflect the recreation. Therefore, when inspecting commit details after a rebase, you may see the original author while the committer is the person who ran the rebase.

There are advanced options to adjust date/time metadata, though you do not need to change them in a standard rebase workflow. The key goal is to understand that a commit ID represents the entire commit object, not just the diff.

## 4. Performing a rebase on a feature branch

Suppose you are working on `feature/report`, and the base branch is `main` on the `origin` remote.

Before rebasing, check your branch and working tree:

```bash
git status -sb
git branch -vv
```

If there are uncommitted changes, commit or save them according to your workflow first. Rebase requires a clean working tree in most normal situations; do not start while unmanaged changes remain.

Update information from the remote and switch to the feature branch:

```bash
git fetch origin
git switch feature/report
```

Inspect the history before making changes:

```bash
git log --oneline --graph --decorate --all
```

Once you confirm `origin/main` is the desired base, run:

```bash
git rebase origin/main
```

Git replays the unique commits of `feature/report` onto `origin/main`. If successful, `feature/report` points to the last recreated commit. Neither the local `main` branch nor `origin/main` is moved by rebasing the feature branch.

If you prefer to update the local `main` branch first and then rebase, you can use an alternative approach:

```bash
git switch main
git pull --ff-only origin main
git switch feature/report
git rebase main
```

`--ff-only` requires the local `main` branch to advance only via fast-forward; if the histories have diverged, Git stops instead of automatically creating a merge commit. Choose a workflow consistent with how your team manages the base branch.

## 5. Observing old and new commits

To see which commits were recreated, record the history beforehand or inspect the reflog afterward.

Before rebasing, save the branch's old tip commit:

```bash
git rev-parse feature/report
```

Suppose the output is `OLD_TIP`. After rebasing, view the new tip:

```bash
git rev-parse feature/report
```

The two IDs may differ because the commit chain was recreated. To view the new history:

```bash
git log --oneline --graph --decorate feature/report
```

To inspect recent HEAD and branch movements:

```bash
git reflog show feature/report
git reflog
```

The reflog often helps locate the old tip after a rebase, such as an entry recording `rebase (finish)` or the branch's previous state. The reflog is a local reference log with a configurable retention period; it is not a permanent backup and is not shared with the remote.

Once you know the old and new hashes, you can compare their metadata:

```bash
git show --no-patch --format=fuller <old-commit>
git show --no-patch --format=fuller <new-commit>
```

This command displays Author, AuthorDate, Commit, CommitDate, and commit details. To view the parent ID directly in the commit object:

```bash
git cat-file -p <commit-id>
```

The `parent` lines indicate the parent commits. For a new commit after a rebase, the parent is usually the new base commit or the commit recreated immediately before it.

## 6. Rebase does not always recreate every commit

Rebase only needs to replay commits within the selected range that are not already in the target history. Keep the following cases in mind:

- If the branch is already based on the new base and there are no commits left to replay, rebase may finish without changing history.
- If an equivalent change already exists in the target branch, Git may recognize that the commit has already been applied and skip it during rebase.
- If a commit becomes empty after application, Git may stop to ask, skip it, or handle it according to the active rebase options.
- If you resolve a conflict by discarding all changes from a commit, that commit may become empty and no longer be recreated in the standard way.

Therefore, do not assume the number of commits before and after a rebase is always equal. Always inspect the log and actual results.

## 7. Resolving conflicts during replay

Rebase applies commits one at a time. If a commit cannot be applied automatically, Git pauses at that commit and asks you to resolve the conflicts.

Check the status:

```bash
git status
```

Read the contents of the conflicted files, identify the changes from the commit being replayed and the changes on the new base. Once you produce the intended result, stage the resolved files:

```bash
git add path/to/resolved-file
git rebase --continue
```

Git proceeds to replay the next commit. You may need to resolve conflicts multiple times if several commits touch areas that changed on the new base.

Options available while rebase is paused:

| Command | Effect |
|---|---|
| `git rebase --continue` | Continue after resolving and staging conflicts |
| `git rebase --skip` | Skip the current commit being replayed |
| `git rebase --abort` | Cancel the rebase and return to the state before it started |

Only use `--skip` when you have verified that the commit's changes are no longer needed or have already been integrated another way. This command discards all changes of the current commit in the rebase, not just the conflicting portion.

If the resolution result is unclear or you want to start over, `git rebase --abort` is usually the safe choice to stop the process. You can then review the history, discuss with relevant people, and try again with a new plan.

## 8. Comparing commit chains before and after rebase

When rebasing many commits, visually comparing individual hashes is error-prone. You can use:

```bash
git range-diff <old-base>..<old-tip> <new-base>..feature/report
```

`git range-diff` compares two commit ranges to help identify which commits correspond, which changed in content, and which were added or dropped. Replace the placeholders with the actual base and tip hashes recorded before the rebase alongside the new branch after the rebase.

This command is especially useful when rebasing a long chain or when conflicts had to be resolved. It helps review whether replaying accidentally dropped part of a change. However, the comparison output should still be evaluated alongside project requirements and tests.

## 9. Impact of rebase on shared history

Because rebase creates new commits, the remote branch may still point to the old commit chain. If you previously pushed the branch and then rebased locally, your next push may be rejected as non-fast-forward.

Before rebasing, determine whether the branch's commits have been fetched by others or used as a base for other branches. On an unshared personal branch, recreating commits is usually easier to manage. On a shared branch, rebasing can leave everyone else with local history based on old commits and force them to deal with divergence.

If the team has agreed to rewrite the remote branch's history, fetch and inspect carefully before updating that branch. `--force-with-lease` can reduce the risk of overwriting new commits you have not seen yet:

```bash
git fetch origin
git log --oneline --graph --decorate HEAD origin/feature/report
git push --force-with-lease origin feature/report
```

This command is still a history-overwriting operation when the lease condition is satisfied. It does not replace coordinating with teammates, does not bypass branch protection, and does not make rebasing a shared branch safe by default. Do not use `git push --force` just to bypass a non-fast-forward rejection.

## 10. Are old commits deleted immediately after rebase?

No. Rebase creates new commit objects and updates the branch reference to point to the new chain. The old commits that are no longer referenced by the current branch may still remain in Git's object store for some time. They may still be referenced by another branch, a tag, the reflog, or other objects.

If no references keep them alive, Git may prune unused objects after a retention period and garbage collection. Therefore, do not rely on old commits remaining forever as a backup strategy.

If you discover that a rebase lost a needed commit, check the reflog to find the old hash. Once you identify the right commit, you can create a rescue branch pointing to that commit:

```bash
git branch rescue/report-before-rebase <old-commit>
```

Only use a verified hash from the reflog or a trusted source. A rescue branch keeps the old commit reachable so you can inspect, cherry-pick, or recover it according to plan. Do not hastily reset your working branch.

## 11. Summary

Rebase replays the changes of unique commits onto a new base and creates a replacement commit chain. The new commits have new parents, so their identifiers change even when patches or file contents match the old commits. Review history before and after, use reflog or range-diff to verify when needed, resolve conflicts commit by commit, and consider the impact on teammates before rebasing or updating a shared branch.

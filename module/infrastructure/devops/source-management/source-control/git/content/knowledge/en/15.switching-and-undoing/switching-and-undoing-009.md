# Picking Multiple Commits, Preserving Source References with -x, and Handling Conflicts

`git cherry-pick` lets you take changes from one or more existing commits and apply them onto the current branch. This is a common way to port a bug fix from a development branch to a release branch, or select specific needed changes without merging the entire source branch.

When picking multiple commits, the application order can affect the result because later commits often depend on earlier ones. The `-x` option records the source commit hash in the commit message so readers can trace the origin of the change. If a commit causes a conflict, Git pauses the cherry-pick sequence so you can resolve it and continue.

## 1. What Does Cherry-Pick Produce?

Suppose branch `feature` has a committed bug fix, and branch `release` needs only that fix:

```bash
git switch release
git cherry-pick abc123
```

Git applies the changes introduced by commit `abc123` onto the current state of `release`, then creates a new commit if it applies cleanly.

Simple diagram:

```text
A---B---C             (feature)
     \
      D---E           (release)
```

If you cherry-pick commit `C` onto `release`, Git creates a new commit `C'` on top of `E`:

```text
A---B---C             (feature)
     \
      D---E---C'      (release)
```

`C'` has modified content corresponding to `C`, yet it is a different commit because it has a new parent and may have a different timestamp/committer. Therefore, the commit hash of `C'` differs from `C`. The source branch `feature` is not moved; the operation only adds a commit to the current branch.

Cherry-pick transfers a commit's changes, not the whole branch or the entire development history of the source branch. If a commit depends on changes in an earlier commit, you need to transfer the prerequisite commit as well or resolve any resulting differences.

## 2. Picking Multiple Commits in a Specified Order

You can pass multiple commit hashes in the same command:

```bash
git switch release
git cherry-pick abc123 def456 789abc
```

Git applies the commits sequentially in the order you list: `abc123`, then `def456`, then `789abc`. This approach fits when you already know the exact commits to transfer and the dependency order between them.

If each commit applies cleanly, Git creates a corresponding new commit for each source commit. If one commit causes a conflict or cannot be applied, Git stops at that commit. The remaining commits in the sequence have not been processed yet and are held in the sequencer state so you can continue after resolving.

Before picking multiple commits, inspect the source branch's history:

```bash
git log --oneline --decorate feature
git log --oneline --graph --decorate --all
```

Use full commit hashes or prefixes unique enough to avoid confusing commits with similar content. If unsure of the order, check parent-child relationships and each commit's contents:

```bash
git show --stat abc123
git show --stat def456
git show --stat 789abc
```

Do not pick commits based solely on chronological order or commit messages. A commit updating how an API is called may depend on the commit that added that API; picking them out of order can cause conflicts or produce a broken state.

## 3. Picking a Commit Range

Common revision range syntax is:

```bash
git cherry-pick BASE..TIP
```

The expression `BASE..TIP` selects commits reachable from `TIP` that are not reachable from `BASE`. Thus, commit `BASE` is excluded from the range; commit `TIP` is included if it falls within the selected set.

For example, linear history:

```text
A---B---C---D---E  (feature)
    ^
   BASE
```

The range `B..E` includes `C`, `D`, `E`; it excludes `B`. If you want to include `B` in this linear history as well, you can use `A..E`.

For a commit range, it is good practice to generate an explicit list in parent-before-child order and pipe that list to cherry-pick:

```bash
git rev-list --reverse --topo-order BASE..TIP | git cherry-pick -x --stdin
```

- `git rev-list BASE..TIP` determines the set of commits in the range.
- `--reverse` reverses traversal order so older commits are applied first.
- `--topo-order` prioritizes topological order, ensuring parent commits are processed before child commits in branched history.
- `git cherry-pick --stdin` reads the list of commit hashes from standard input.

Replace `BASE` and `TIP` with actual commit hashes or ref names. This is useful when a range contains many commits and you want clear control over order. For a small list of commits, passing individual commit hashes directly in the desired order is usually easier to read.

Note that a revision range over branched history may include commits from multiple branches. Inspect the list before applying:

```bash
git rev-list --reverse --topo-order BASE..TIP
```

If the commit set contains a merge commit, cherry-picking a merge commit usually requires specifying the mainline parent with `-m <parent-number>`. Selecting the parent determines which part of the merge commit's changes will be applied; do not add `-m` mechanically. Inspect `git show --no-patch --pretty=raw <merge-commit>` and determine the appropriate parent first. If you only want to transfer regular commits, you can filter merge commits out of the list, while understanding that changes appearing only in the merge resolution might not be transferred that way.

## 4. Preserving Source Commit References with -x

When porting commits between public branches or branches shared across multiple teams, readers may need to know where the new commit came from. The `-x` option tells Git to append a reference line to the commit message:

```bash
git cherry-pick -x abc123
```

The added line takes the form:

```text
(cherry picked from commit abc123...)
```

With a list of commits:

```bash
git cherry-pick -x abc123 def456 789abc
```

Git records the source reference in the message of commits that cherry-pick cleanly without conflicts. When reading history on the target branch, others can look up the source commit hash and cross-check the original change.

View the result with:

```bash
git log --format=fuller -5
git show --format=fuller HEAD
```

`-x` only adds text information to the commit message. It does not preserve the original commit hash, does not create a ref link between the two commits, does not keep the source branch alive, and does not prevent the source commit from being pruned from other refs. The new commit still has its own hash.

This option is especially useful when cherry-picking between public branches because it helps maintain history traceability. For commits from private or internal branches that carry no meaning for recipients, that reference usually adds little value.

**Important limitation:** Git only automatically adds the `(cherry picked from commit ...)` line when the cherry-pick has no conflicts. If Git has to stop for you to resolve a conflict, do not assume the `-x` line was added. If your project workflow requires preserving provenance, add the source commit hash to the commit message after resolving the conflict. When you need per-commit message control, process one commit at a time so you can inspect and edit the message before moving to the next commit.

## 5. Previewing Changes Before Cherry-Picking

Before porting commits, confirm the target branch and working tree:

```bash
git status
git branch --show-current
```

If the working tree has uncommitted changes, decide how to preserve them before cherry-picking. A clean working tree helps you distinguish changes created by the integration operation from pre-existing changes.

Inspect the source commit and affected files:

```bash
git show --stat --oneline abc123
git show --format=fuller --find-renames abc123
```

For multiple commits, check the list before executing:

```bash
git rev-list --reverse --topo-order BASE..TIP
```

If you need to compare a commit's changes against the target branch's state, inspect the commit diff and surrounding file context. Cherry-pick applies the commit's patch onto the current state; it does not guarantee identical results to the source branch if the two branches have diverged.

## 6. Handling Conflicts in a Cherry-Pick Sequence

When a commit cannot apply automatically, Git pauses the cherry-pick sequence and leaves a conflict state. Identify the commit currently being processed and the conflicted files:

```bash
git status
git diff --name-only --diff-filter=U
git show CHERRY_PICK_HEAD
```

`CHERRY_PICK_HEAD` points to the commit currently being applied. In a multi-commit sequence, this is the current commit causing the conflict; subsequent commits remain queued in the sequencer.

Open the conflicted files, and understand both the changes from the source commit and the existing content on the target branch. You can inspect the combined diff:

```bash
git diff --cc -- path/to/file
```

Edit each file to its final content, remove any conflict markers, and mark each resolved file:

```bash
git add -- path/to/file
```

If you decide to delete a file, use:

```bash
git rm -- path/to/file
```

Verify before continuing:

```bash
git status
git diff --cached
git diff --cached --check
git diff --name-only --diff-filter=U
```

Once all files are resolved, continue the sequence:

```bash
git cherry-pick --continue
```

Git creates the commit for the resolved changes and continues processing the remaining commits in the sequence. If the next commit also conflicts, repeat the process. After the sequence completes, re-check history and run appropriate tests.

If you do not want to apply the current commit, you can skip it:

```bash
git cherry-pick --skip
```

Only use `--skip` when you have decided that commit's changes are not needed on the target branch or were already brought in another way. Skipping a commit can prevent subsequent commits from applying or leave out part of a feature.

If you want to cancel the entire in-progress cherry-pick sequence and return to the state before the sequence began:

```bash
git cherry-pick --abort
```

`--abort` cancels the running cherry-pick operation; it is not a conflict resolution method. Before starting a sequence, protect uncommitted changes to avoid risking lost work.

## 7. Adding Provenance When a Commit Has Conflicts

Because `-x` does not automatically add the source line for commits with conflicts, inspect the commit message after resolving. A straightforward approach is picking one commit at a time when you know conflicts are likely:

```bash
git cherry-pick -x abc123
```

If conflicts occur, resolve the files and run:

```bash
git add -- path/to/file
git cherry-pick --continue
```

After the commit is created, open the message to append the source reference if needed:

```bash
git commit --amend
```

Add the following line at the end of the commit message, substituting the full source commit hash:

```text
(cherry picked from commit <source-commit-oid>)
```

Save and close the editor. Then inspect:

```bash
git show --format=fuller --no-patch HEAD
```

Amending recreates the target commit with the updated message, so the target commit hash changes. If you already pushed this commit to a remote, amending may require a history-updating push according to team policy.

If processing a multi-commit sequence and you want to add provenance to conflicted commits, consider cherry-picking each commit individually. That way you can finish, verify the message, and amend the current commit before starting the next one.

## 8. Already-Applied or Empty Commits

A source commit may have already been applied previously by another route, or its changes may already exist on the target branch. In that case, cherry-pick may report that the commit becomes empty after applying.

Do not create an empty commit solely to keep the sequence moving unless there is a clear historical reason. Inspect the diff, confirm whether the changes already exist on the target branch, and choose how to proceed:

- Use `git cherry-pick --skip` if the change does not need to be applied again.
- Keep an empty commit only when the project intentionally marks such an event or milestone.
- If the change only partially applies, edit the result properly, stage it, and continue.

Do not skip a commit merely because Git reports it empty without checking the content and why that commit was in the sequence.

## 9. Example Workflow: Porting a Group of Commits to Release

Suppose branch `feature/payment-fix` has three verified commits that need to be ported to `release/2.x`. You have determined the dependency order and want to keep source references:

```bash
# Check current status
git status

# Switch to the receiving branch
git switch release/2.x

# Inspect source commits before applying
git show --stat 12ab345
git show --stat 34bc567
git show --stat 56cd789

# Port in exact order while recording origin in commit messages
git cherry-pick -x 12ab345 34bc567 56cd789

# If a conflict occurs:
# 1. Edit files
# 2. Stage resolved files
git add -- path/to/file

# 3. Continue the sequence
git cherry-pick --continue

# Inspect the new commits and messages
git log --oneline --decorate -5
git show --format=fuller --no-patch HEAD

# Run tests appropriate for the changes
```

In practice, if the sequence stops at a commit with conflicts and you need to add provenance manually, process one commit at a time and amend the message as shown in section 7 before moving to the next commit.

## 10. Common Confusions

| Confusion | Accurate understanding |
|---|---|
| Cherry-pick preserves the source commit hash | Git creates a new commit on the target branch; the commit hash usually differs |
| `-x` keeps the source branch alive | `-x` only adds the source commit hash to the commit message |
| `-x` always adds the provenance line | Git only adds this line automatically for conflict-free cherry-picks |
| `BASE..TIP` includes BASE | The range excludes BASE and commits reachable from BASE; TIP is included if in the selected set |
| Commits can be applied in any order | Later commits can depend on earlier ones; specify parent-before-child order |
| Removing conflict markers is enough | You must stage the resolved files and run `git cherry-pick --continue` |
| `--skip` and `--abort` are the same | `--skip` skips the current commit; `--abort` cancels the entire in-progress operation |
| Cherry-picking a merge commit is like a regular commit | A merge commit requires selecting the mainline parent with `-m` and understanding the diff that will be applied |

## Conclusion

Use `git cherry-pick <commit>...` when you already know the exact list and order of commits to transfer. For a commit range, generate the list with `git rev-list --reverse --topo-order` to control parent-before-child ordering. Add `-x` when you need to record source commit hashes in the messages of conflict-free cherry-picks; if conflicts occur, check and add provenance manually when project policy requires it. When Git stops, resolve the files, stage the results, and run `git cherry-pick --continue`; only skip or abort after understanding the impact of that decision.

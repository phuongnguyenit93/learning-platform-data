# Porting Fixes and Safely Reverting on Shared History

During collaboration, a fix may be committed on the wrong branch, needed on a release branch, or already pushed to a shared branch before a bug is discovered. How you handle it depends on whether the change is committed yet, whether the commit has already been shared, and whether you want to **port the change** or **reverse its effects**.

This lab combines three key operations:

- **Cherry-pick** to bring a commit's changes onto another branch by creating a new commit.
- **Revert** to undo the effects of a shared commit while preserving existing history.
- **Reset/restore/stash** to manage local changes before switching branches or revising private history.

The overarching rule is to inspect repository status and history before acting, safeguard local work, and verify the result after every step.

## 1. Start by Identifying the Repository State

Before porting commits or reverting, verify your current branch, uncommitted changes, and recent commits:

```bash
git status --short --branch
git branch --show-current
git log --oneline --decorate --graph --all -15
```

These three commands answer different questions:

- `git status` shows whether the working tree or index has changes or conflicts.
- `git branch --show-current` shows the current local branch; an empty output may indicate a detached HEAD.
- `git log` shows recent commits and branch/merge relationships across fetched refs.

Refresh remote state before comparing against shared branches:

```bash
git fetch origin
```

`fetch` updates remote-tracking refs such as `origin/main` without merging or rebasing your current branch. Next, inspect commits unique to either side:

```bash
git log --oneline --left-right --graph origin/main...HEAD
```

The `<` and `>` markers distinguish commits reachable only from the left side versus the right side of the comparison. Replace `origin/main` with your team's actual remote-tracking branch.

If the working tree has changes, do not rush into cherry-picking, reverting, or switching branches. Inspect the diff first and decide whether to commit, stash, or handle those changes separately.

## 2. Choosing the Right Porting or Undo Operation

Not every situation calls for the same command:

| Situation | Usually appropriate operation | Impact on history |
|---|---|---|
| Commit exists on branch A and needs to be ported to branch B | `git cherry-pick` | Creates a new commit on branch B |
| Faulty commit was pushed to a shared branch | `git revert` | Creates a new commit reversing its effects |
| Want to drop unshared commits on a private branch | `git reset` | Moves the branch ref; may modify index/working tree |
| Want to unstage a file | `git restore --staged` | Does not alter commits |
| Want to discard unstaged changes in a file | `git restore` | Overwrites local file changes |
| Need to set aside uncommitted changes to switch branches | `git stash` | Temporarily stores changes in the local repository |

A critical question is whether the commit has already been shared. If the commit has been pushed to a branch others depend on, prefer revert to publish a new reversing commit. If the commit resides only on a private, unshared branch, reset may be appropriate when you want to revise history.

## 3. Porting a Commit to Another Branch With Cherry-Pick

Suppose you fixed a login bug on `feature/login`, creating commit `F1`, and that fix also needs to go onto the maintenance branch `release/2.x`.

Initial history:

```text
main:        A --- B
                  \
feature/login:     C --- F1

release/2.x: R1 --- R2
```

The goal is to bring `F1`'s changes onto the release branch without merging the entire `feature/login` branch.

First, identify the commit to port:

```bash
git log --oneline --decorate feature/login
git show --stat --oneline <fix-commit>
```

Replace `<fix-commit>` with the actual OID of the bug-fix commit. Read the diff before applying to verify the commit contains no out-of-scope changes.

Fetch and create a working branch from the latest release branch:

```bash
git fetch origin
git switch -c hotfix/login origin/release/2.x
```

If `hotfix/login` already exists, do not pass `-c` to recreate it. Check whether that existing branch is really the one you intend to continue.

Apply the commit:

```bash
git cherry-pick -x <fix-commit>
```

`git cherry-pick` takes the diff introduced by the source commit and applies it onto the current HEAD. Git creates a new commit whose parent is the current tip of the target branch. The new commit's OID differs from the source OID because its parent and commit metadata differ.

The `-x` option appends a line referencing the source commit's OID to the commit message, which helps trace origins when porting commits between public branches.

After applying, verify:

```bash
git status
git log --oneline --decorate -5
git show --stat --oneline HEAD
```

Run tests appropriate for the release branch before pushing the hotfix branch:

```bash
git push -u origin hotfix/login
```

If the release branch is protected, open a pull request from `hotfix/login` into `release/2.x` per team workflow. Never bypass branch protection to push directly.

## 4. Porting Multiple Commits in Order

Suppose the source branch has three consecutive commits:

```text
base --- C1 --- C2 --- C3
```

When porting all three commits, apply them from oldest to newest so later commits have the foundation from earlier ones.

Inspect the list:

```bash
git log --oneline --reverse <base>..<source-branch>
```

The `<base>..<source-branch>` range selects commits reachable from the source branch and not reachable from the base. It is not necessarily linear if history contains merges.

After reviewing the list, cherry-pick the OIDs from top to bottom:

```bash
git cherry-pick -x <oid-C1> <oid-C2> <oid-C3>
```

Do not copy the example verbatim if the actual order or OIDs differ. If the commits have merge topology you need to preserve, cherry-picking commit by commit will not recreate the branch/merge structure; consider merging or another integration method.

You can use `git cherry` to check whether equivalent changes already exist on the destination branch:

```bash
git cherry -v <destination-branch> <source-branch>
```

A `+` indicates the patch has not yet been found on the destination side; a `-` indicates an equivalent patch already exists. This compares patch equivalence and does not imply identical commit OIDs.

Do not blindly cherry-pick a commit whose equivalent change is already on the destination branch. Doing so can produce duplicate changes, conflicts, or empty commits.

## 5. Cherry-Picking Only Part of a Commit's Changes

Sometimes a source commit touches multiple files, yet the destination branch needs only part of the changes. You can run:

```bash
git cherry-pick --no-commit <fix-commit>
```

The `--no-commit` option applies changes to the index and working tree without creating a commit yet. Next, inspect:

```bash
git status --short
git diff
git diff --cached
```

You can adjust the contents, stage only what should be kept, and commit according to the destination branch's scope. Note that the index may already hold the cherry-picked changes; inspect carefully before committing.

If you want to cancel everything currently applied before committing, how to handle it depends on the sequencer state and prior edits. For an active single cherry-pick paused mid-operation, use `git cherry-pick --abort` to cancel. If `--no-commit` has already finished, inspect `git status` and selectively revert the applied changes; avoid broad reset/restore commands when the index or working tree holds other work.

## 6. Handling Conflicts During Cherry-Pick

Cherry-pick can conflict if the destination branch edited the same code region or file structure differently from the source branch.

When a conflict occurs, Git pauses and marks unmerged paths. Inspect:

```bash
git status
git diff --name-only --diff-filter=U
```

Open each file, inspect conflict markers, and combine contents to meet the destination branch's requirements. Then stage the resolved files:

```bash
git add -- src/login/Authenticator.java
git status
```

Continue the cherry-pick:

```bash
git cherry-pick --continue
```

If you determine the current commit is unnecessary because its changes already exist or were handled differently, you can skip the paused commit:

```bash
git cherry-pick --skip
```

Only skip after confirming the commit's effect is already accounted for. To cancel the entire active cherry-pick sequence and return to the state before it started:

```bash
git cherry-pick --abort
```

After continuing or aborting, check `git status` and `git log` to confirm the sequencer finished and the branch is in the right state.

## 7. Cherry-Picking a Merge Commit Requires Specifying a Mainline

A merge commit has multiple parents. When cherry-picking a merge commit, Git must know which parent acts as the baseline to compute the diff to apply.

Inspect the parents:

```bash
git show --no-patch --pretty=raw <merge-commit>
```

To extract the merge commit's changes relative to its first parent, use:

```bash
git cherry-pick -m 1 <merge-commit>
```

`-m 1` selects the first parent as the mainline. Choosing the wrong parent applies a diff from the unintended side.

Before cherry-picking a merge commit, inspect the graph, parents, and diffs relative to each parent:

```bash
git diff <merge-commit>^1 <merge-commit>
git diff <merge-commit>^2 <merge-commit>
```

Cherry-picking a merge commit only takes the diff relative to the chosen parent; it does not recreate the merge topology. If the goal is to integrate an entire branch with its history, merging the branch is usually more appropriate.

## 8. Undoing a Shared Commit With git revert

Suppose faulty commit `B2` was pushed to `main` and teammates may have fetched or branched from it:

```text
main: A --- B1 --- B2 (buggy) --- C
```

Do not rewind `main` back to `B1` with reset and force push as a routine action. Anyone who already pulled `B2` will end up with local history that diverges from the remote branch.

Instead, create a new commit that reverses `B2`'s changes:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git revert <bad-commit>
```

If `main` is protected and changes must go through a pull request, create a revert branch from the updated `main` before reverting:

```bash
git switch -c revert/bad-login
git revert <bad-commit>
git push -u origin revert/bad-login
```

If team policy allows committing directly on local `main`, you can revert there and push if authorized. Always respect your team's branch protection workflow.

`git revert` does not erase the old commit. It computes the inverse of the selected commit and creates a new commit on the current branch. History looks like:

```text
main: A --- B1 --- B2 --- C --- R
                                  ^
                         revert B2
```

Commit `R` preserves shared history while recording the undo. If `main` is protected, create a revert branch and open a pull request per team workflow instead of pushing directly.

Inspect the diff and run tests before sharing the revert commit:

```bash
git show --stat --oneline HEAD
git show HEAD
git status
```

Once verified, push the branch or open a pull request. Revert is safe for shared history because existing commits retain their OIDs and ordering.

## 9. Reverting Multiple Commits in Safe Order

If a sequence of consecutive commits must be undone, understand the dependencies between them. For commits `C1`, `C2`, `C3` applied in that order, revert from newest to oldest:

```bash
git revert <oid-C3>
git revert <oid-C2>
git revert <oid-C1>
```

Reverse order cleanly unwinds dependent changes step by step. However, if commits are independent or only part needs reverting, inspect the diffs and select the exact target range.

You can pass `--no-commit` to apply the inverse changes into the index/working tree without committing immediately:

```bash
git revert --no-commit <bad-commit>
```

Then inspect and verify the combined result:

```bash
git status
git diff
git diff --cached
```

Once the content is right, create a single revert commit with a clear message. Remember `--no-commit` still modifies your index and working tree; it is not a dry-run preview mode.

Never pass a large range to revert without reading the exact commits that range selects. Before reverting in bulk, inspect the graph and confirm every commit in the range truly needs to be reversed.

## 10. Reverting a Merge Commit

Reverting a merge commit requires specifying the mainline parent, just like cherry-picking a merge commit.

Inspect the parents:

```bash
git show --no-patch --pretty=raw <merge-commit>
```

If the main branch is the first parent and the goal is to undo the changes brought in by the merge relative to the main branch:

```bash
git revert -m 1 <merge-commit>
```

`-m 1` picks the first parent as the mainline. Always verify parent ordering instead of assuming parent 1 is always the branch you want to keep.

Reverting a merge commit creates a new commit reversing the diff between the merge result and the chosen mainline. It does not remove the merged branch's commits from history. Git records that the merge's changes were reversed; if you merge that same branch again later, the old commits are still ancestors, so Git will not re-introduce the reverted changes. When those changes need to be reapplied later, teams usually revert the revert commit or create a new commit containing the desired fix.

Because of this impact on future merges, coordinate with maintainers and verify carefully before reverting a merge on a shared branch.

## 11. Distinguishing Reset, Revert, and Restore

These three commands have similar names but operate on different areas:

| Command | Purpose | Effect on history |
|---|---|---|
| `git reset` | Moves HEAD/branch and optionally updates index and working tree | Can rewrite local history |
| `git revert` | Creates a new commit reversing an older commit | Preserves shared commits |
| `git restore` | Restores file contents in the index or working tree | Creates no commits and does not move branches |

Common reset modes:

```bash
git reset --soft HEAD~1
git reset --mixed HEAD~1
git reset --hard HEAD~1
```

- `--soft`: moves branch/HEAD to the target commit, keeping changes in the index and working tree.
- `--mixed`: moves branch/HEAD and updates the index; keeps file contents in the working tree. This is the default when no mode is specified.
- `--hard`: moves branch/HEAD, updates the index, and overwrites the working tree to match the target commit. Uncommitted tracked changes can be lost; untracked files colliding with checked-out paths may also be overwritten.

Reset suits revising private, unshared history—for example, combining commits or dropping unpushed local commits. Do not use reset to remove commits that others have already pulled onto a shared branch unless there is an explicit coordinated history-rewrite plan.

`git restore` operates on files:

```bash
git restore --staged -- src/App.java
git restore --worktree -- src/App.java
```

The first command unstages the file while keeping changes in the working tree. The second restores the working tree file from the current index and can discard unstaged edits in that file.

Before restoring, inspect `git diff` or `git diff --cached` to know what will change. Do not confuse restoring a file with reverting a commit.

## 12. When Is Reset Safe and When Is It Not?

You can use reset on a private local branch when commits have not been shared and you intentionally want to alter history.

For example, dropping the last commit while keeping its changes staged for a new commit:

```bash
git reset --soft HEAD~1
git status
```

Or dropping the last commit and returning its changes to the working tree unstaged:

```bash
git reset --mixed HEAD~1
git status
```

If the commit was already pushed to a shared branch, reset rewinds your local branch while the remote keeps the old commit. A normal push will be rejected as non-fast-forward. Force pushing alters remote history and can orphan commits others have built upon.

For shared branches, the standard choice is `git revert`. If the team genuinely needs to rewrite history on a private feature branch, agree beforehand, check remote state, and use `--force-with-lease` rather than bare `--force`:

```bash
git fetch origin
git push --force-with-lease origin feature/my-private-branch
```

`--force-with-lease` rejects the update if the remote branch no longer matches the commit your local lease expects. It reduces the risk of overwriting someone else's new commits, though it does not make rewriting a shared branch automatically safe. Only use it when the branch is not stable shared history and everyone involved has coordinated.

## 13. Preserving Uncommitted Changes Before Switching Branches

If the working tree has changes, you can make a temporary commit or stash before switching branches.

Inspect first:

```bash
git status --short
git diff
git diff --cached
```

If you need to stash both tracked and untracked changes:

```bash
git stash push -u -m "WIP before switching branch"
```

`-u` includes untracked files in the stash; ignored files are excluded by this flag. Stashes live locally in your repository and are not automatically shared with teammates.

Inspect stashes:

```bash
git stash list
git stash show --stat stash@{0}
```

After switching to the target branch, restore:

```bash
git stash apply stash@{0}
```

`apply` keeps the stash in the list so you can verify the result. Only delete the stash with `git stash drop` once you confirm everything restored cleanly. `git stash pop` both applies and drops the stash if application succeeds, so `apply` is often safer to control while preserving work.

If you want to create a branch from the exact base commit where the stash was created and apply the changes onto it:

```bash
git stash branch rescue/wip stash@{0}
```

This creates a branch from the stash's base commit, applies the changes, and drops the stash if successful. Verify carefully before continuing.

## 14. Recovering a Commit After an Accidental Reset With Reflog

If an accidental reset moves your branch backward to an older commit, the previous commit can usually still be found via reflog for a period of time.

Inspect HEAD movement history:

```bash
git reflog --date=local -n 15
```

Example:

```text
a1b2c3d HEAD@{0}: reset: moving to HEAD~1
e4f5a6b HEAD@{1}: commit: Add login validation
9a8b7c6 HEAD@{2}: checkout: moving from feature/login to main
```

If `e4f5a6b` is the commit to recover, create a rescue branch pointing to it:

```bash
git branch rescue/login-before-reset e4f5a6b
```

Then inspect:

```bash
git log --oneline --decorate -5 rescue/login-before-reset
git show --stat rescue/login-before-reset
```

The reflog is a local log; it is never pushed to remotes and is not permanent storage. Old entries expire over time, and unreferenced objects can eventually be cleaned up by garbage collection. Once you locate a commit you need to keep, create a rescue branch or ref immediately.

If the commit had been pushed earlier, the remote or a teammate's clone might still retain the OID. Still, never rely on someone else's clone as a default backup plan.

## 15. Integrated Practice: Porting a Hotfix and Reverting a Shared Buggy Commit

Scenario: the team has a login bug-fix commit on `feature/login`. The `release/2.x` branch needs only that fix. Later, a different commit merged into `main` causes a production outage and must be safely undone.

### Part A — Porting the Hotfix to the Release Branch

**Step 1: Identify the fix commit.**

```bash
git fetch origin
git log --oneline --decorate origin/feature/login
git show --stat --oneline <fix-commit>
```

Read the diff to confirm the commit contains only the fix to port.

**Step 2: Create a branch from the latest release.**

```bash
git switch -c hotfix/login origin/release/2.x
```

**Step 3: Cherry-pick the commit.**

```bash
git cherry-pick -x <fix-commit>
```

If conflicts occur, resolve them on the hotfix branch and run `git cherry-pick --continue`.

**Step 4: Verify and share.**

```bash
git status
git log --oneline --decorate -5
git show --stat HEAD
git push -u origin hotfix/login
```

Run tests and open a pull request into `release/2.x` per team workflow.

### Part B — Reverting a Buggy Commit on a Shared Branch

**Step 1: Update the main branch.**

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c revert/bad-commit
```

**Step 2: Identify the offending commit.**

```bash
git show --stat --oneline <bad-commit>
git show <bad-commit>
```

Verify the chosen commit is truly the cause to revert and check whether subsequent commits depend on it.

**Step 3: Create the revert commit.**

```bash
git revert <bad-commit>
```

If conflicts occur, resolve files, stage, and continue with `git revert --continue`.

**Step 4: Verify and share.**

```bash
git status
git show --stat HEAD
git show HEAD
```

Run tests, push `revert/bad-commit`, and open a pull request into `main` per team workflow.

The buggy commit remains in history, while a new commit reverses its effect. Other team members can pull the branch without dealing with rewritten remote history.

## 16. Common Issues and How to Handle Them

| Symptom | Common cause | How to resolve |
|---|---|---|
| Cherry-pick reports conflict | Destination branch has incompatible edits | Resolve files, stage, then `--continue` |
| Cherry-pick creates duplicate/empty commit | Equivalent patch already exists on destination branch | Check `git cherry`, log, and diff before continuing |
| Cherry-pick on merge commit asks for mainline | Commit has multiple parents | Inspect parents and pass the right `-m` if cherry-picking the merge is truly intended |
| Revert reports conflict | Subsequent commits changed the same code | Resolve against current state then `git revert --continue` |
| Push after reset rejected as non-fast-forward | Local branch rewrote history diverging from remote | For shared branches, use revert; never force push casually |
| Reset discarded local changes | Used `--hard` or wrong index/working-tree mode | Check reflog, stash, and backup refs; restore recovered commits |
| `git stash pop` hits conflict | Current branch differs from stash base | Use `git stash apply`, resolve conflicts, and drop only after verifying |
| Cannot find commit after reset | Commit is no longer reachable from current branch | Inspect `git reflog` and create a rescue branch from the OID |
| Reverting a merge prevents re-merging old changes later | Git records the merge as already reversed in ancestry | Coordinate with maintainers; revert the revert commit or create a fresh fix commit |

## 17. Checklist Before Porting Fixes or Reverting

Before running an operation:

- [ ] Verified repository, branch, and working tree status.
- [ ] Fetched remote to inspect latest history.
- [ ] Identified the exact OID and read the source commit's diff.
- [ ] Determined whether the commit has already been shared on a remote branch.
- [ ] Safeguarded uncommitted changes via commit or stash.
- [ ] Chose cherry-pick for porting commits and revert for undoing shared history.
- [ ] If handling a merge commit, checked parent order and deliberately chose the mainline.
- [ ] Resolved conflicts and verified `git status`.
- [ ] Ran appropriate tests before pushing or opening a pull request.
- [ ] If rewriting a private branch, coordinated with affected peers and checked remote state before `--force-with-lease`.

After the operation, re-check the graph and status:

```bash
git status --short --branch
git log --oneline --graph --decorate --all -15
git show --stat --oneline HEAD
```

Do not rely solely on a command exiting with zero. Verify that the new commit sits on the right branch and contains the exact intended fix or reversal.

## Conclusion

Use `git cherry-pick` to port a commit's changes onto another branch as a new commit; use `git revert` to reverse the impact of a shared commit without rewriting history. `git reset` is better suited for private, unpublished branches, while `git restore` handles file contents and `git stash` safeguards uncommitted work when switching contexts. When an operation goes wrong, check the reflog and create a rescue ref as soon as you find the commit. Before every operation, fetch the remote, read the diff, protect local work, and verify the outcome using status and the commit graph.

# Rebasing a working branch onto an updated target branch

During development, a target branch such as `main` often continues receiving new commits while you are still working on a feature branch. As a result, your working branch may be based on an older version of `main`. Rebasing places the working branch's unique commits onto the tip of the latest target branch so you can continue developing on an updated base.

For example, suppose you created `feature/payment` from `main` at commit `B`. While you were working, `main` moved forward to commit `C`. Rebasing replays the feature commits after `C`, creating new history while preserving the feature's changes.

Rebase creates new commits for the replayed history. The new commits have different parents and identifiers than the old commits. If the branch belongs only to you, updating it is straightforward. If the branch has already been pushed and teammates depend on it, coordination is required before rewriting shared history.

## 1. Model when the target branch advances

Initially, `feature/payment` was created from commit `B`. Later, `main` receives commit `C`:

```text
P---A---B---C  main
         \
          F1---F2  feature/payment
```

When you rebase `feature/payment` onto `main`, Git replays the feature commits and creates `F1'`, `F2'`:

```text
P---A---B---C  main
             \
              F1'---F2'  feature/payment
```

`F1` and `F2` still exist in the repository if another ref or object keeps them alive, but the local `feature/payment` branch now points to `F2'`. A previously pushed remote branch may still point to `F2` until a remote update is performed.

This causes trouble for teammates. Suppose someone else created commit `G1` based on `F2`:

```text
P---A---B---C
         \
          F1---F2---G1  teammate branch
```

After the shared branch is rewritten to `F1'---F2'`, `G1` still has `F2` as its parent. Git does not automatically guess that `G1` should move onto the new base. The author of `G1` must resync their history according to the agreed procedure.

If the person rebasing force-pushes without notifying anyone, teammates may keep committing onto the old history, hit non-fast-forward errors, or accidentally overwrite each other's work. Rebasing a shared branch is therefore a change to shared history conventions, not merely a private action in a local repository.

## 2. Choosing rebase or merge to update a working branch

Choose the integration method based on who is using the branch and your team's policy:

| Situation | Usually suitable approach |
|---|---|
| Working branch used only by you, unpublished | Rebase is usually convenient for updating the base and keeping linear history. |
| Working branch pushed, but no one else is based on it | Can rebase if the team agrees and you notify others before updating the remote. |
| Multiple people committing to the same working branch | Prefer merge to preserve shared commits. |
| Teammates have created separate branches from commits on the working branch | Only rebase when everyone agrees on a plan to move dependent commits onto the new history. |
| Target branch is a release or protected branch | Follow release procedures and server policies; do not arbitrarily rewrite target branch history. |

Merge keeps existing commits and creates a merge commit (when a merge commit is needed). Rebase recreates the replayed commits. Merge typically shows the integration point clearly in the history graph; rebase typically yields a more linear path, but requires anyone relying on the old commits to resync.

## 3. Before you start: align with teammates

For a shared branch, agree on the following points before proceeding:

1. **Coordinator:** designate one person responsible for rebasing and updating the remote branch.
2. **Freeze window:** announce the start and end times; during this window, team members do not push additional commits to the shared branch.
3. **Commit scope:** identify the new base branch, which commits are kept, which are replayed, and whether merge commits need to be preserved.
4. **Backup of work:** ask each member to commit their own work or create a backup ref so they can return to the pre-sync state.
5. **Post-rebase update procedure:** agree on how members will reset their local branch and replay their own commits onto the new history.

Do not start rewriting history while others are still pushing unaware of the plan. If you cannot pause pushes or confirm everyone has received the notice, use merge to integrate new changes instead.

## 4. Checking state and creating recovery points

Suppose the shared branch is `feature/payment`, the shared remote is `origin`, and the new base branch is `origin/main`. First, inspect your local repository:

```bash
git status
git branch --show-current
git branch -vv
git log --oneline --graph --decorate --all
```

If the working tree or index has uncommitted changes, handle them first. You can commit them as a separate commit or stash them according to your team's workflow. Do not run rebase with unsaved changes unless you clearly understand how Git will handle them.

Fetch to get the latest remote state:

```bash
git fetch origin
```

Determine which unique commits exist on the local and remote branches:

```bash
git log --oneline --left-right --graph origin/feature/payment...feature/payment
git rev-list --left-right --count origin/feature/payment...feature/payment
```

In the output of `rev-list --left-right --count A...B`, the first number is commits only in `A`, and the second is commits only in `B`. If the remote has new commits that local does not, understand and integrate them before deciding to rewrite the branch.

Create a local backup branch to preserve the starting point before integrating teammates' commits:

```bash
git branch backup/feature-payment-before-sync feature/payment
```

The backup branch preserves the current commit of `feature/payment` so you can inspect it if the next integration step does not go as expected. It exists only locally; if a copy on the server is needed, agree on the naming and storage approach with the team before pushing a backup branch.

Record the current OID of the remote branch after this fetch:

```bash
git rev-parse origin/feature/payment
```

Save the printed OID to use as the lease condition when updating the remote. This helps detect if the remote branch changed after the time the team agreed to freeze pushes.

## 5. Integrating teammates' new commits before rebasing

If `origin/feature/payment` has commits not yet on your local branch, do not ignore them. First inspect the commits on both sides:

```bash
# Commits present on remote but not in the local branch
git log --oneline feature/payment..origin/feature/payment

# Commits present locally but not on the remote branch
git log --oneline origin/feature/payment..feature/payment
```

For a branch actively used by multiple people, the least destructive way to bring remote changes into local is via merge:

```bash
git switch feature/payment
git merge origin/feature/payment
```

After merging, your local branch contains the commits pushed by teammates. If the team has decided to rebase the entire shared branch, include those commits in the rebase scope and clearly notify everyone that commits within the rebase scope will be recreated with new OIDs.

Once all commits to keep are integrated and right before rebasing, create another backup ref pointing to the full history about to be rewritten:

```bash
git branch backup/feature-payment-before-rebase feature/payment
```

This ref serves as the main comparison point after rebasing. Choose a different name if that backup ref already exists.

Do not arbitrarily drop remote-only commits just to make the local branch look linear. If there are commits with unclear ownership or you do not know whether anyone depends on them, stop and confirm with the team.

## 6. Performing the rebase according to the agreed plan

Once everyone has paused pushes, the state is backed up, and the commit scope is clear, the coordinator can rebase:

```bash
git switch feature/payment
git rebase origin/main
```

Git identifies commits on the current branch that are not yet in `origin/main` and replays them onto the new base. If the branch contains merge commits and the merge structure must be preserved, evaluate the `--rebase-merges` option separately; a standard rebase may linearize the replayed history.

If the rebase succeeds, inspect the graph and contents:

```bash
git log --oneline --graph --decorate --all
git diff backup/feature-payment-before-rebase...feature/payment
git diff origin/main...feature/payment
```

Compare against the backup branch to see how the result changed, and check the feature branch's changes relative to the new base. Run the project's appropriate checks and tests before updating the remote.

## 7. Resolving conflicts and aborting rebase when needed

If Git pauses due to a conflict, check the status:

```bash
git status
```

Open the reported files, combine the contents according to the intent of the changes, remove conflict markers, and verify the result. After resolving a file:

```bash
git add src/payment/PaymentService.java
git rebase --continue
```

Repeat until the rebase completes. Do not mark a file as resolved if its contents have not been verified.

If you realize the rebase base or scope is wrong, you can cancel the in-progress rebase session:

```bash
git rebase --abort
```

This command restores the branch being rebased to its state before the rebase session started. The backup branch created earlier remains an independent reference point for inspecting the old history.

`git rebase --skip` skips the commit currently causing a conflict. Only use it when the team confirms that commit's changes are no longer needed or were already applied elsewhere; otherwise, you may accidentally lose part of the work.

## 8. Updating the remote branch in a controlled way

After rebasing, your local `feature/payment` has a new history. The remote `origin/feature/payment` still points to the old history until you update it. Because the new history is no longer a direct continuation of the old history, a normal push is usually rejected.

For a shared branch, only force-push after:

- The coordinator has announced completion of the rebase and confirmed no one else is pushing to the branch.
- The local branch has been reviewed and required checks have passed.
- The remote OID recorded before rebasing is still the value you expect to replace.
- The team has agreed that replacing remote history is necessary.

Use `--force-with-lease` with the recorded expected OID:

```bash
git push --force-with-lease=refs/heads/feature/payment:<expected-remote-oid> origin HEAD:refs/heads/feature/payment
```

Replace `<expected-remote-oid>` with the full OID obtained from `git rev-parse origin/feature/payment` before rebasing. The explicit lease syntax requires the remote ref to still have that exact OID. If a teammate pushed a new commit after your check, the remote ref will differ and Git will reject the update; in that case, fetch, inspect the new commit, and re-align instead of trying to push further.

`--force-with-lease` is safer than `--force` because it checks the remote state conditionally. However, it does not replace coordination: if you record the OID after a teammate's commit has already appeared and use that new OID as the expected value, the lease can still allow overwriting that commit. Save the OID before the freeze window and verify with the team.

Do not use generic force-push commands on protected or release branches. The server may block the operation; follow repository governance procedures.

## 9. Guiding teammates to sync after the branch is rewritten

After successfully updating the remote, announce the new OID and when the branch is ready. Each teammate needs to preserve their unintegrated local commits and move onto the new history.

For example, suppose a teammate has a local `feature/payment` branch with a few personal commits created after old commit `F2`. They should:

```bash
# Check and save uncommitted work first
git status

# If uncommitted changes remain and you want to stash them temporarily, include untracked files
git stash push -u -m "before syncing rewritten feature/payment"

# Create a backup branch preserving the branch's current commit
git branch backup/feature-payment-local feature/payment

# Fetch the new history after the coordinator has updated the remote
git fetch origin
```

Next, identify the last commit on the old history that their own commits are based on. In the example, that is `F2`. Create a new working branch from the backup copy and replay the commits after `F2` onto the new remote branch:

```bash
git switch -c feature/payment-rebased backup/feature-payment-local
git rebase --onto origin/feature/payment <old-shared-tip>
```

Replace `<old-shared-tip>` with the OID of the last commit on the old shared history before the rebase. The command replays commits present on the current branch that are not in the history starting from that commit, placing them onto the new `origin/feature/payment`.

If you stashed uncommitted changes in the previous step, restore them after the new branch has been created and verified:

```bash
git stash pop
```

If conflicts occur when applying the stash, resolve and inspect the files as in a normal change integration. Only push verified work to the agreed target branch; you can use a separate new branch to open a pull request if direct updates to the shared branch are not permitted.

If a teammate's local branch contains only the old history with no personal commits, they can recreate the local branch from the remote after saving any changes they want to keep:

```bash
git switch -c feature/payment-fresh origin/feature/payment
```

Only after inspecting the new branch should you decide to rename or replace the old local branch. Do not run `git reset --hard` on a branch containing unsaved work. The backup branch and old OID help pinpoint the exact personal commits that need replaying.

If a teammate created multiple sub-branches based on the old history, each sub-branch also needs to be reviewed. For each branch, identify the old base commit and unique commits, then rebase or cherry-pick according to plan. Do not apply a single blanket reset command for everyone, as each person's work structure may differ.

## 10. Sample coordination workflow for the whole team

| Phase | Coordinator | Other members |
|---|---|---|
| Before rebase | Announce schedule, scope, and executor; fetch and record remote OID | Pause pushes; commit or save personal work; note current base commit |
| During rebase | Create backup ref, rebase, resolve conflicts, and verify result | Do not push to shared branch; do not continue developing on old ref |
| Remote update | Check lease OID, conditional force-push, and confirm result | Wait for confirmation that new branch is ready |
| After rebase | Announce new OID and new base commit | Fetch, back up local branch, replay personal commits onto new history, and verify |
| Wrap-up | Confirm everyone is synced; reopen push permissions per team convention | Resume working on the new history |

If a missing commit is discovered after rebasing, stop pushing further changes. Compare the backup branch, old history, and new history to identify the omitted commit; then use controlled cherry-pick or rebase to recover it. Do not delete backup refs until the team confirms all work has been migrated successfully.

## 11. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Rebase just moves the branch name | Rebase replays commits and creates new commits for the rewritten history; the local branch name then points to the new commit. |
| Local rebase immediately changes the remote | It only updates local; the remote changes only after a successful push. |
| `--force-with-lease` guarantees teammates' work cannot be overwritten | It checks the remote OID against the lease condition; you still need to record the OID at the right time and coordinate with the team. |
| Teammates only need to run `git pull` after a force-push | Their local branches may still be based on old commits; they need to back up, fetch, and replay personal commits as planned. |
| Merge and rebase have the same impact on history | Merge keeps old commits and connects histories; rebase creates new commits for the replayed portion. |
| A shared branch can be rebased anytime | It should only be done when the team agrees on timing, scope, executor, and the resync procedure. |
| `git rebase --skip` is a safe way to bypass conflicts | The command skips the commit currently being replayed; only use it when confirmed that the commit's changes do not need to be kept. |

## 12. Self-check

1. **Why can rebasing a shared branch affect teammates?**
   - Because replayed commits receive new OIDs; teammates' branches or commits may still be based on the old history.
2. **If you cannot ask everyone to pause pushes, which approach should you choose to integrate new changes?**
   - Usually merge, so existing shared commits are preserved.
3. **Why create a backup branch before rebasing?**
   - To keep a ref pointing to the old history, making it easy to inspect and recover if the result is wrong.
4. **What does `--force-with-lease` check?**
   - It only allows updating the ref if the remote value still matches the specified expected OID or the active lease condition.
5. **After the remote branch is rewritten, what should teammates do with their personal commits?**
   - Back up local state, fetch the new history, identify the old base commit, and replay their personal commits onto the new branch.

## Conclusion

Rebasing a shared branch changes the identifiers and parent-child relationships of replayed commits. To do it safely, the team needs to pause pushes, define scope, save backup refs, record the remote OID, rebase and verify the result, and then update the remote conditionally with `--force-with-lease`. Afterward, each member fetches the new history and replays their personal commits. If full coordination is not possible, merge is usually the better choice to preserve the history everyone is sharing.

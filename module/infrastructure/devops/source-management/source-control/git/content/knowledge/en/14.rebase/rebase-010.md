# Recovering from a bad rebase and coordinating shared branch updates

Rebase reorganizes commit history by replaying commits onto a different base. Because this operation creates new commits with new hashes, rebasing can alter a branch's history. If you pick the wrong base branch, the wrong commit range, or resolve conflicts incorrectly, you need to know how to return to the previous state. When the branch has already been pushed and others are using it, recovery also requires coordination so teammates' commits are not lost.

This lesson covers two distinct situations: **an in-progress rebase that needs to be canceled**, and **a completed rebase with the wrong result**. It then explains how to handle cases where history has already been shared on a remote, how to use the reflog and rescue branches, and how to resync teammates' machines after a branch is rewritten.

## 1. Why can a rebase be recovered?

Rebase does not edit old commits in place. Git creates new commits based on each commit's changes and applies them sequentially onto the new base commit. As a result, the hashes of replayed commits usually change.

For example, initially a feature branch has the history:

~~~text
A---B---C  main
     \
      D---E  feature/report
~~~

You intended to place the feature branch on top of a new commit on `main`, but accidentally rebased onto the wrong branch or wrong commit. After the rebase, history might look like:

~~~text
A---B---C---D'---E'  feature/report
~~~

Commits `D'` and `E'` have similar contents to `D` and `E`, but are new commits. If the result is wrong, you need to find the commit the branch pointed to before the rebase and decide whether to restore the branch to that commit.

Git records the movement history of local references in the **reflog**. This is usually the best place to locate the branch's previous position. Git may also record the pre-operation position in `ORIG_HEAD`, though this value can be overwritten by other commands.

## 2. Before recovering: determine the current state

Do not rush to run `reset --hard` or force push. First, inspect the repository and identify what state the rebase is in:

~~~bash
git status
git branch --show-current
git log --oneline --decorate --graph -12
~~~

Questions to answer:

- Is there a message indicating a rebase is in progress?
- Are you on the right branch that needs recovery?
- Has the rebase finished or is it paused at a conflict?
- Which commits were recreated?
- Has the branch already been pushed to the remote?
- Has anyone else fetched, checked out, or created commits based on the new history?
- Does the working tree have uncommitted changes or untracked files that must be preserved?

If the rebase is still running, the procedure differs from when the rebase has finished. If the branch has already been shared, consider the impact on teammates before rewriting the remote.

## 3. Canceling a rebase while it is still in progress

When rebase hits a conflict, Git pauses and waits for you to resolve each commit. If you realize you chose the wrong base branch, wrong range, or do not want to proceed, you can cancel the operation:

~~~bash
git rebase --abort
~~~

This command ends the running rebase and restores the branch to its state before the rebase started. Then verify:

~~~bash
git status
git log --oneline --decorate --graph -12
~~~

If the goal is to completely cancel the rebase operation, `--abort` is the standard choice.

### Distinguishing continue, skip, abort, and quit

| Command | Effect |
|---|---|
| `git rebase --continue` | Continue replaying commits after resolving conflicts and staging files |
| `git rebase --skip` | Skip the commit currently being replayed; only use when intentionally discarding that commit's changes |
| `git rebase --abort` | Cancel the rebase and return the branch to its state before starting |
| `git rebase --quit` | Clear rebase tracking state while keeping the current HEAD, index, and working tree as is |

`--quit` is not the same as `--abort`. Quit does not restore the branch to its starting point; it only stops tracking the rebase progress and leaves the current state untouched. Therefore, when you discover a bad rebase and want to return to the starting point, you should generally not choose `--quit`.

If you are resolving conflicts and have manual edits worth keeping, back them up before aborting. After `--abort`, verify the working tree and previous changes again.

## 4. Finding the pre-rebase commit with reflog

If the rebase has already finished, `git rebase --abort` no longer applies. At this point, locate the pre-rebase position in the reflog.

View HEAD's movement history:

~~~bash
git reflog --date=iso
~~~

Or view the branch's history specifically:

~~~bash
git reflog show feature/report --date=iso
~~~

Illustrative output:

~~~text
8ab31c2 HEAD@{2026-11-17 10:42:10 +0700}: rebase (finish): returning to refs/heads/feature/report
8ab31c2 HEAD@{2026-11-17 10:42:10 +0700}: rebase (pick): Add report export
51d92ef HEAD@{2026-11-17 10:41:52 +0700}: rebase (pick): Add report filters
c7a10bd HEAD@{2026-11-17 10:40:03 +0700}: rebase (start): checkout main
d4f6e20 HEAD@{2026-11-17 10:35:22 +0700}: commit: Add report export
a6b8c91 HEAD@{2026-11-17 10:20:14 +0700}: commit: Add report filters
~~~

In the example, `d4f6e20` is the branch's position before the rebase began. Actual reflog entries and hashes on your machine will differ.

To verify whether a commit is the right recovery point:

~~~bash
git show --stat d4f6e20
git show --oneline --no-patch d4f6e20
~~~

Check the parent commit, contents, and timestamp. Do not pick a commit solely because it sits right before a line containing `rebase`; verify that it was the branch tip before the operation.

### How can ORIG_HEAD help?

Certain operations such as merge, reset, and rebase record the previous position in `ORIG_HEAD`. You can inspect it:

~~~bash
git show --oneline --no-patch ORIG_HEAD
~~~

If that commit matches the pre-rebase tip, it can enable quick recovery. However, `ORIG_HEAD` can be overwritten by other commands. Reflog usually provides more checkpoints, so cross-check rather than relying solely on `ORIG_HEAD`.

### What are the limits of reflog?

The reflog records reference updates in the local repository. It is not history automatically synced to the remote and is not guaranteed to last forever. Entries can expire according to configuration, and unreferenced commits may subsequently be pruned by garbage collection.

Therefore, recover as soon as possible when you spot a mistake. The reflog on a teammate's machine can also be a source for finding commits if another machine has lost that reference, provided the commit still exists in their repository.

## 5. Creating a rescue branch before resetting

Before moving the branch, create a new branch to preserve the current state. A rescue branch is a reference to a commit that lets you return to the state you just inspected if you choose the wrong recovery point.

Suppose you need to recover `feature/report`:

~~~bash
git switch feature/report
git branch rescue/feature-report-after-rebase HEAD
~~~

The name `rescue/feature-report-after-rebase` is just an example; choose a name that does not already exist and is easy to recognize.

If the working tree has uncommitted changes or untracked files, save them first:

~~~bash
git status
git stash push -u -m "before recovering feature/report rebase"
~~~

The `-u` option includes untracked files in the stash. It does not include ignored files; if ignored files must be kept as well, consider `-a` and inspect contents first. Do not treat stash as the sole backup for critical data.

Once you have a rescue branch and saved necessary changes, confirm the recovery commit again using reflog and `git show`.

## 6. Restoring the local branch to its pre-rebase state

Once you have verified the old commit with certainty, you can move the local branch back to it:

~~~bash
git switch feature/report
git reset --hard d4f6e20
~~~

`reset --hard` updates HEAD, the index, and the working tree to match the specified commit. It can discard uncommitted changes in the working tree. Only run it after checking and saving everything you need to keep.

Verify:

~~~bash
git status
git log --oneline --decorate --graph -12
~~~

If you created a stash, inspect the list and reapply it when appropriate:

~~~bash
git stash list
git stash apply stash@{0}
~~~

Use `apply` to keep the stash in the list until you verify the restored contents. Only once you are certain all changes are fully applied should you consider deleting the stash with `git stash drop`.

The rescue branch still preserves the post-rebase commits. If you discover you selected the wrong old commit, you can switch back to the rescue branch or create another branch from that commit to continue investigating.

## 7. If the commit cannot be found in the reflog

First, inspect the reflogs of both HEAD and branches:

~~~bash
git reflog --all --date=iso
~~~

Check `ORIG_HEAD` and any rescue or temporary branches created earlier. Ask teammates whether their local repositories still hold the old commit; each clone maintains its own reflog.

If no clear reference remains, `git fsck` can find unreferenced commit objects:

~~~bash
git fsck --no-reflogs --unreachable
~~~

If you spot a notable commit, inspect its contents with:

~~~bash
git show --stat <commit-id>
~~~

Only after confirming the right commit should you create a rescue branch:

~~~bash
git branch rescue/recovered-report <commit-id>
~~~

This is a last resort, not a guarantee of recovery. If the commit has already been removed by garbage collection and no longer exists in any clone or backup, Git may have no data left to recover.

## 8. Distinguishing local branches from shared branches

A branch that exists only in your local repository can generally have its history amended more flexibly, provided you preserve needed work. Once a branch is pushed to a remote and others depend on it, that branch becomes part of the collaborative workflow.

Distinguish three situations:

| Situation | Usually suitable approach |
|---|---|
| Bad rebase, not yet pushed | Use reflog to find the old tip, create a rescue branch, and recover locally |
| Private branch pushed, no one else relies on the new history | Notify anyone watching, check the remote, then update with lease when genuinely necessary |
| Branch used by multiple people or commits already integrated | Prefer keeping history and creating a corrective commit with revert; only rewrite history with a clear coordination plan |

Force pushing to a shared branch can leave other machines on old history while the remote has switched to new history. If teammates continue pushing based on the old tip, they may hit non-fast-forward errors, create unintended merge commits, or reintroduce replaced commits.

Not every bad rebase requires a force push. If changes have already been published and used by others, preserving history and creating corrective commits is usually less disruptive.

## 9. Planning before rewriting a shared branch

If the team decides the history of a pushed branch must be replaced, maintainers and everyone working on that branch must align beforehand.

A coordination plan should define:

1. **Scope**: which remote branch will be rewritten and why.
2. **Executor**: one person responsible for updating the remote to avoid two competing force pushes.
3. **Timing**: the window during which members pause pushing to that branch.
4. **Recovery point**: save the old tip hash and create a rescue branch if needed.
5. **New tip**: identify the commit that will become the branch tip after rebasing.
6. **Resync procedure**: guide members to fetch, compare, and move their own work onto the new history.

Before making changes, fetch the latest remote state:

~~~bash
git fetch origin
git rev-parse origin/feature/report
~~~

Record the returned hash. This is the remote tip you inspected and agreed to replace. You can also view the history:

~~~bash
git log --oneline --graph --decorate origin/feature/report -12
~~~

Do not begin rewriting if the remote already has new commits you have not reviewed. If you notice a teammate just pushed, pause to decide how to keep that commit.

## 10. Updating a remote branch with force-with-lease

A regular push only accepts fast-forward updates. Rebase creates new commits, so replacing old history on the remote may require a forced update.

Prefer `--force-with-lease` over `--force`:

~~~bash
git push --force-with-lease origin feature/report
~~~

Git checks that the remote ref is still at the value the local repository expects, usually based on the remote-tracking branch. If the remote changed since your fetch or since the tracking value was updated, the push may be rejected. This is a safeguard against accidentally overwriting someone else's new commits.

For stricter control, explicitly specify the inspected remote hash:

~~~bash
git push --force-with-lease=refs/heads/feature/report:<expected-remote-sha> origin feature/report:refs/heads/feature/report
~~~

Replace `<expected-remote-sha>` with the hash recorded before rewriting history. The command updates only if the remote ref still matches that expected value.

Do not treat a lease as a substitute for coordination. It only checks the ref's condition at update time; it does not notify teammates, verify they backed up their work, or inspect their local work.

If the push is rejected, do not immediately switch to `--force`. Fetch, inspect the new commits on the remote, find out who updated it, and integrate that work before trying again.

## 11. When to use revert instead of force push?

If a commit has already been integrated into the main branch, released, or used by many other branches, rewriting history can complicate synchronization. In this case, `git revert` is usually more appropriate.

For example, create a commit that reverses a published commit:

~~~bash
git switch main
git pull --ff-only
git revert <commit-id>
git push origin main
~~~

`git revert` creates a new commit that undoes the changes of the specified commit. Old history remains intact, so people who already fetched or built work on top of that commit do not have to deal with a replaced branch.

If you need to revert a merge commit, identify the mainline parent and use the correct `-m` option. Check dedicated guidance on reverting merges before proceeding.

Revert does not erase the mistaken commit from history, but it clearly records the corrective action. That is usually desirable on public or release branches.

## 12. Resyncing teammates' machines after a branch is rewritten

After the maintainer has updated the remote successfully, machines that previously fetched the old history must resync intentionally. Do not blindly run `git pull`: if local still holds the old branch, pull may try to merge the two rewritten histories and create an unintended commit.

First, fetch and inspect the differences:

~~~bash
git fetch origin
git log --oneline --left-right --graph feature/report...origin/feature/report
~~~

The `<` and `>` markers in the output distinguish commits present only locally versus only on the remote. Determine whether local has any unpushed personal commits.

### Case where local has no personal work to keep

If the working tree is clean and the local branch only holds the replaced old history, create a backup and update local to match the remote:

~~~bash
git switch feature/report
git branch rescue/feature-report-before-sync HEAD
git reset --hard origin/feature/report
~~~

Only use `reset --hard` after confirming there are no uncommitted changes or after saving them. The rescue branch preserves old history for inspection or commit retrieval.

### Case where local has unpushed personal commits

Do not reset away those commits. First, create a rescue branch and identify the last common commit of the old history—that is, the shared branch tip before it was rewritten. Then, once you have accurately identified the boundary, replay the personal commits onto the new tip:

~~~bash
git status
git branch rescue/feature-report-local-work HEAD
git stash push -u -m "before resyncing feature/report"
git rebase --onto origin/feature/report <old-shared-tip> feature/report
~~~

In this command, `<old-shared-tip>` is the last commit of the old shared branch that the maintainer replaced. That anchor must exist in the local branch's history; Git replays commits after that anchor onto the new remote branch. If the local branch does not contain this old tip, find the true divergence point using the commit graph and `git merge-base`, or select your own commits to cherry-pick. Do not guess the upstream boundary.

After the rebase succeeds, check and reapply the stash if one was created:

~~~bash
git status
git stash list
git stash apply stash@{0}
~~~

If the rebase produces conflicts, resolve each file, stage the edited files, and run `git rebase --continue`; only apply the stash after the rebase finishes. If you cannot identify personal commits or the history boundary, keep the rescue branch and review it together with the maintainer before continuing.

If you are unsure which commits belong to old history and which are personal work, stop to compare logs or ask the maintainer for help. For a few distinct commits, you can create a new branch from the remote and cherry-pick the exact commits to keep. Avoid rebasing the entire old history onto the new branch, as it may replay changes that were already replaced.

After syncing, inspect diffs, run tests, and only push when you are certain the new branch has no duplicate commits or unintended changes.

## 13. Practical workflow for recovering from a bad rebase

Suppose you mistakenly rebased `feature/report` onto `release/2.x` instead of `main`, and the rebase already finished but has not been pushed.

**Step 1 — Check status**

~~~bash
git status
git branch --show-current
git log --oneline --graph --decorate -12
~~~

**Step 2 — Find the old tip**

~~~bash
git reflog show feature/report --date=iso
git show ORIG_HEAD --oneline --no-patch
~~~

Identify the hash before the rebase started and inspect that commit with `git show`.

**Step 3 — Preserve the current state**

~~~bash
git branch rescue/feature-report-wrong-rebase HEAD
~~~

If uncommitted changes exist, save them with a stash or a suitable copy before resetting.

**Step 4 — Restore the branch**

~~~bash
git reset --hard <commit-before-rebase>
~~~

**Step 5 — Verify and proceed in the right direction**

~~~bash
git log --oneline --graph --decorate -12
git status
git rebase origin/main
~~~

After rebasing correctly, inspect diffs and run tests before pushing. Because the branch has not been pushed, no forced remote update is needed.

If the branch has already been shared, stop at the state-preservation step and follow the coordination plan from earlier sections. Do not force push on your own while teammates are still working on the old history.

## 14. Mistakes to avoid

| Mistake | Consequence | Recommended approach |
|---|---|---|
| Running `reset --hard` without checking the working tree | Loses uncommitted changes | Check status, stash, or back up first |
| Picking the wrong reflog entry | Restores to the wrong commit | Inspect the commit with `git show`, verify history and timestamp |
| Confusing `--quit` with `--abort` | Stops the process but leaves the in-progress rebase state | Use `--abort` when you want to return to the pre-rebase state |
| Using `--skip` to bypass conflicts without reading the patch | Drops changes from the commit being replayed | Only skip when intentionally discarding that commit |
| Force pushing a shared branch without notice | Causes other machines' history to diverge, risking lost commits | Align on timing, back up, and use a lease |
| Running `git pull` immediately after remote is rewritten | May create a merge between old and new histories | Fetch, compare logs, and choose the right sync method |
| Rebasing a teammate's entire old branch | May replay replaced commits or create duplicate changes | Identify the boundary of personal commits and use `--onto` or cherry-pick |
| Using revert for every situation | May create unnecessary revert commits when changes are local only | Choose local recovery or preserving public history based on the situation |

## 15. Checklist before and after recovery

Before acting:

- [ ] Determine whether the rebase is in progress or already completed.
- [ ] Confirm the right repository and branch.
- [ ] Check the working tree and untracked files.
- [ ] Find the pre-rebase commit via reflog; check `ORIG_HEAD` if helpful.
- [ ] Create a rescue branch for the current state.
- [ ] Determine whether the branch has been pushed or used by others.

If a shared branch must be rewritten:

- [ ] Notify and align with all relevant members.
- [ ] Fetch and record the current remote tip hash.
- [ ] Pause competing pushes during the update window.
- [ ] Use `--force-with-lease` with the appropriate expected value.
- [ ] If the lease rejects, inspect new commits instead of switching to `--force`.
- [ ] Guide teammates to fetch, compare, and preserve personal commits.

After recovery:

- [ ] Check `git status` and the commit graph.
- [ ] Confirm the diff matches the goal.
- [ ] Run required tests.
- [ ] Keep the rescue branch until confirmed no longer needed.
- [ ] Confirm the remote and relevant machines have synced properly.

## 16. Key takeaways

- If a rebase is still running and you want to cancel it, use `git rebase --abort`.
- If the rebase has finished, use reflog to find the pre-rebase tip; `ORIG_HEAD` is only a supplementary reference.
- Create a rescue branch before resetting to preserve the current state.
- `git reset --hard` can delete uncommitted changes; inspect and back up first.
- Rebasing on an unshared local branch is usually easier to recover than on a branch used by multiple people.
- When rewriting a remote branch, notify beforehand, save the old hash, pause competing pushes, and use `--force-with-lease`.
- After a remote is rewritten, teammates must fetch and compare histories; do not blindly pull or reset.
- If commits have been widely published or integrated into the main branch, `git revert` usually keeps history clearer than force pushing.

Rebase recovery is about identifying the exact historical anchor and preserving all valuable work before moving references. When a branch is shared, success also depends on the whole team understanding which history is kept, which history is replaced, and how each machine resyncs safely.

# Restoring a Branch Using a Commit Found in Reflog

A Git branch is simply a reference pointing to a commit. When you accidentally delete a branch, reset by mistake, or move a branch to a different commit, the old commits may still remain in the repository even though no branch points to them anymore. **Reflog** records changes to local references, allowing you to locate the commit before the mistaken operation and create a new branch from that commit.

A safe recovery consists of three parts: finding the right commit in the reflog, verifying the commit's contents, and recreating a branch pointing to that commit. Reflog is a useful rescue tool, but it only exists in each local clone and is not a long-term backup.

## 1. Why Can a Branch Be Restored from Reflog?

In Git, a branch is a name referencing a commit. For example, the branch `feature/report` might point to commit `a1b2c3d`. When you create a new commit on the branch, Git moves that reference to the new commit.

If you accidentally delete the branch or run a command that moves it to the wrong location, the old branch name may disappear or point elsewhere. However, Git usually keeps old commits in the object store for a period of time. Reflog helps retrieve the hash of the commit the branch previously pointed to.

Example before the mistaken operation:

~~~text
A---B---C---D  main
         \
          E---F  feature/report
~~~

You accidentally reset the `feature/report` branch to commit `C`. The current branch becomes:

~~~text
A---B---C  main, feature/report
         \
          E---F  (no branch pointing here)
~~~

Commits `E` and `F` may still exist in the repository. Reflog can show that the branch used to point to `F`; after verifying, you create a new branch from that commit.

## 2. What Is Reflog?

Reflog (reference log) is a local log that records each time the value of Git references changes. Commonly recorded changes include:

- Creating commits and moving HEAD.
- Switching from one branch to another.
- Resetting a branch to another commit.
- Completing a rebase or merge.
- Updating a branch or another reference.

Each entry typically has the commit hash, reflog position, timestamp, and operation description.

View HEAD's reflog:

~~~bash
git reflog
~~~

This command is equivalent to viewing HEAD's log and is usually a good starting point when recovering from a recent operation.

View reflog with readable timestamps:

~~~bash
git reflog --date=local
~~~

View the reflog of a specific branch:

~~~bash
git reflog show feature/report
~~~

View all reflogs that Git still retains:

~~~bash
git reflog --all --date=iso
~~~

Reflog is not the repository's shared commit history. Each clone has its own reflog; when you push commits to a remote, local reflogs are not sent along.

## 3. Reading a Reflog Entry

Illustrative output:

~~~text
f6a91d2 HEAD@{0}: reset: moving to HEAD~2
b72c4e8 HEAD@{1}: commit: Add report export
9d3a1f0 HEAD@{2}: commit: Add report filters
c4e8b21 HEAD@{3}: checkout: moving from main to feature/report
~~~

The components can be read as follows:

| Component | Meaning |
|---|---|
| `f6a91d2` | The commit HEAD pointed to at that entry |
| `HEAD@{0}` | The latest entry of HEAD's reflog |
| `HEAD@{1}` | The entry immediately before the latest entry |
| `reset: moving to HEAD~2` | Description of the operation that changed HEAD |

The index in `HEAD@{n}` is the position in the log, not the number of parent commits. `HEAD@{2}` means the third entry counting from the latest entry, whereas `HEAD~2` means walking back two parent commits in the history graph.

The example above shows HEAD is currently at `f6a91d2` after the reset. The previous entry pointed to `b72c4e8`, and the one before that pointed to `9d3a1f0`. If the goal is to recover the state before the reset, one of those old hashes may be a candidate. You must inspect the contents and history before choosing.

Reflog indices shift whenever new operations occur. Once you find the right commit, note down its full hash for subsequent commands instead of relying indefinitely on `HEAD@{1}`.

## 4. Finding the Commit Before the Mistaken Operation

Suppose you just ran:

~~~bash
git reset --hard HEAD~2
~~~

and realized the two most recent commits on the feature branch disappeared from the branch tip.

Start with:

~~~bash
git status
git reflog --date=local
~~~

Look for the entry describing the mistaken operation, such as `reset: moving to HEAD~2`. The entry right before the reset usually holds the old tip of HEAD.

You can view the branch's own reflog separately if the branch still exists:

~~~bash
git reflog show feature/report --date=local
~~~

If the branch has already been deleted, the branch's dedicated reflog may also have been deleted. In that case, check HEAD's reflog:

~~~bash
git reflog --date=local
~~~

HEAD usually recorded the checkouts and commits when you worked on the branch. This may be where the trace of the final commit before branch deletion still resides.

### Do Not Pick a Commit Based on Position Alone

An entry near the mistaken operation is not guaranteed to be the commit you need. Verify:

1. Does that commit belong to the branch being recovered?
2. Does the creation or checkout time match when you worked on the branch?
3. Does the commit contain the latest changes you want to retrieve?
4. Do the parent commits make sense relative to the base branch?

If unsure, inspect several candidates instead of resetting immediately.

## 5. Verifying the Commit Before Creating a Branch

After finding the hash, inspect the commit metadata:

~~~bash
git show --no-patch --format=fuller b72c4e8
~~~

View the list of files and change statistics:

~~~bash
git show --stat b72c4e8
~~~

View preceding commits:

~~~bash
git log --oneline --graph --decorate -10 b72c4e8
~~~

If you need to inspect the exact diff of the commit:

~~~bash
git show b72c4e8
~~~

Cross-check the commit message, author, timestamp, modified files, and diff contents with the work you want to recover. The hashes in this lesson are examples only; use the hashes obtained from your own repository.

You can retrieve the full hash from an abbreviated hash:

~~~bash
git rev-parse b72c4e8
~~~

Record that value before creating a branch.

## 6. Recreating a Branch from a Reflog Commit

If the old branch name is free, the simplest way is to create a new branch at the verified commit:

~~~bash
git branch feature/report b72c4e8
~~~

This command creates branch `feature/report` pointing to commit `b72c4e8` without automatically switching the working tree to it.

If you want to create and switch to the branch immediately:

~~~bash
git switch -c feature/report b72c4e8
~~~

Then verify:

~~~bash
git status
git branch --show-current
git log --oneline --decorate -8
~~~

If you want to keep the original branch as-is and create a separate recovery branch for inspection first, use a different name:

~~~bash
git switch -c recover/feature-report b72c4e8
~~~

This is usually the cautious approach when you are not yet certain you picked the right commit. The old branch can be restored or the work cherry-picked after verification.

### When the Old Branch Name Still Exists

If `feature/report` still exists but points to the wrong commit, do not try to create a duplicate branch name. First, preserve the current position:

~~~bash
git branch rescue/feature-report-current feature/report
~~~

If you want to move the existing branch back to the located commit, check which worktrees are using that branch:

~~~bash
git worktree list
~~~

Switch off the target branch in all worktrees before updating the reference. Once the branch is no longer checked out, you can update it:

~~~bash
git branch -f feature/report b72c4e8
~~~

If the branch is checked out in the current worktree, switch to another branch before using `git branch -f`. Alternatively, after backing up and inspecting the working tree, you can use `git reset --hard b72c4e8` while on the exact branch you want to move. The reset command modifies HEAD, the index, and the working tree, so use it only once uncommitted changes are safely preserved.

## 7. Restoring a Deleted Branch

Suppose you deleted the branch:

~~~bash
git branch -D feature/report
~~~

Then you realized the branch still had unintegrated commits. If the commit is still retained in HEAD's reflog or elsewhere, you can locate it again.

Inspect HEAD's log:

~~~bash
git reflog --date=local
~~~

Look for entries where you switched to `feature/report`, committed on that branch, or switched away from it. Identify the hash of the final commit you need to keep.

Inspect the commit:

~~~bash
git show --stat <commit-id>
git log --oneline --decorate -8 <commit-id>
~~~

Recreate the branch:

~~~bash
git switch -c feature/report <commit-id>
~~~

Note: deleting a branch with `git branch -d` or `git branch -D` usually deletes that branch's dedicated reflog as well. As a result, `git reflog show feature/report` may return no results. HEAD's reflog or the reflog of another reference may still contain the commit to recover.

## 8. Recovering After Resetting the Wrong Branch

Another scenario is being on branch `feature/report` and accidentally resetting it to `main`'s commit:

~~~bash
git switch feature/report
git reset --hard origin/main
~~~

`reset --hard` alters HEAD, the index, and the working tree; uncommitted changes may be lost. In this example, assume the working tree was clean or any changes to preserve have already been backed up. If this change has not been pushed to the remote, the old tip may still exist in the branch's or HEAD's reflog.

Workflow:

**Step 1 — Identify the current branch and state**

~~~bash
git status
git branch --show-current
~~~

**Step 2 — Find the old tip in reflog**

~~~bash
git reflog show feature/report --date=local
~~~

If the branch reflog is missing or unclear, check:

~~~bash
git reflog --date=local
~~~

**Step 3 — Verify the hash**

~~~bash
git show --stat <old-tip>
git log --oneline --graph -10 <old-tip>
~~~

**Step 4 — Create a rescue branch from the old commit**

~~~bash
git branch recover/feature-report <old-tip>
~~~

**Step 5 — Switch to the rescue branch and inspect**

~~~bash
git switch recover/feature-report
git status
git log --oneline --decorate -10
~~~

If the rescue branch is correct, you can continue developing on it or coordinate with your team to bring the changes back to the main working branch.

## 9. Using Reflog to Recover After a Rebase

Rebase changes the hashes of replayed commits. If a rebase has completed and you realize the branch was rebased onto the wrong base, the reflog may contain the tip from before the rebase began.

Inspect the log:

~~~bash
git reflog show feature/report --date=local
~~~

Look for entries with descriptions such as:

~~~text
rebase (finish): returning to refs/heads/feature/report
rebase (pick): Add report export
rebase (start): checkout main
~~~

The entry before `rebase (start)` is usually the branch tip prior to the rebase. Verify that hash with `git show`, then create a rescue branch:

~~~bash
git branch rescue/feature-report-after-rebase <old-tip>
~~~

If the goal is to return the current branch to its old tip, preserve the post-rebase state with another branch before moving the branch. Once you have checked the working tree and selected the right commit, update the branch appropriately for its checkout state. For a rebase that is still running, use `git rebase --abort` instead of searching the reflog to manually reset mid-progress.

## 10. If Reflog No Longer Has the Target Entry

Reflog has a retention period and exists locally only. Entries can expire per configuration, and unreferenced objects can be cleaned up by Git garbage collection. If the commit is not found in the reflog, you can still try searching for unreferenced objects.

Run:

~~~bash
git fsck --no-reflogs --unreachable
~~~

Git can list objects unreachable from refs or reflogs. Pay attention to lines like:

~~~text
unreachable commit 9f7a2b1...
dangling commit 4c8d6e3...
~~~

Inspect each candidate commit:

~~~bash
git show --stat 9f7a2b1
git log --oneline --graph -8 9f7a2b1
~~~

Once you have verified the right commit, create a branch to retain it:

~~~bash
git branch recover/found-commit 9f7a2b1
~~~

`git fsck` can return many unrelated objects. Do not create a branch from a hash just because it appears in the output; inspect its contents and history.

If the object has already been removed by garbage collection and does not exist in another clone or backup, Git may no longer have enough data to recover it.

## 11. What Reflog Can and Cannot Recover

Reflog records reference changes, not a complete log of every file operation.

| Situation | Can Reflog Help? | Notes |
|---|---|---|
| Mistaken reset loses branch tip | Usually yes | Find the old tip and create a new branch |
| Local branch deleted | Possibly | HEAD's reflog or another reflog may still hold the commit hash |
| Completed wrong rebase | Usually yes | Find the tip before rebase |
| Checked out another branch | Yes | HEAD's reflog records branch switches |
| Uncommitted changes lost | Not directly | Reflog does not store the working tree |
| Untracked file deleted | No | Requires a backup, stash if saved, or file recovery tools |
| Commit cleaned by garbage collection | No longer if object exists nowhere else | Try another clone, backup, or artifact containing the object |

This explains why you should commit important work or save uncommitted changes with stash before risky operations. Reflog is a commit and reference recovery tool; it does not replace backups.

## 12. Reflog Exists Only in the Local Repository

Each clone has its own reflog. For example, if you delete a local branch on machine A, machine B's reflog is unaffected. If a teammate still has the old branch or commit, they can help retrieve the hash.

Conversely, if you push a branch to a remote and later force push, your local reflog does not automatically become a recovery log on the server. Some platforms have their own recovery mechanisms, but you should not assume a remote provides user reflogs by default.

When recovering a commit that was previously shared, consider how to reintroduce it into the team workflow:

- Create a new recovery branch and push it to the remote.
- Open a Pull Request/Merge Request to review the changes.
- If a shared branch needs to be moved, coordinate with maintainers and inspect remote history first.
- Avoid force pushing just to make a branch name look like before if others have already based work on the new history.

## 13. Practical Workflow: Rescuing Branch feature/report After a Mistaken Reset

Suppose you are developing a report. Branch `feature/report` has two unintegrated commits. You accidentally run:

~~~bash
git reset --hard HEAD~2
~~~

Both commits are no longer at the branch tip. Follow this workflow.

**Step 1 — Inspect the repository**

~~~bash
git status
git branch --show-current
git log --oneline --decorate -8
~~~

**Step 2 — Check the reflog**

~~~bash
git reflog --date=local
~~~

Look for the entry before the line `reset: moving to HEAD~2`. Suppose the old tip hash is `b72c4e8`.

**Step 3 — Inspect the commit**

~~~bash
git show --stat b72c4e8
git log --oneline --graph -8 b72c4e8
~~~

Confirm that both report commits to be preserved are present in the history.

**Step 4 — Create a rescue branch**

~~~bash
git branch recover/feature-report b72c4e8
~~~

**Step 5 — Switch to the rescue branch and verify**

~~~bash
git switch recover/feature-report
git status
git log --oneline --decorate -8
~~~

The `recover/feature-report` branch now holds the old history. You can continue working on this branch, compare it with the current branch, or open a PR/MR to bring the changes back into the team workflow.

## 14. Common Errors During Recovery

| Situation | Cause | Resolution |
|---|---|---|
| Cannot find the deleted branch's reflog | Git usually deletes the dedicated reflog when deleting a branch | Check HEAD's reflog and any remaining reflogs |
| Picked the wrong reflog entry | The most recent entry is not necessarily the tip to recover | Inspect the hash with `git show` and `git log` |
| `git branch` says the name already exists | The branch was not deleted or was already recreated | Use a different rescue branch name; do not overwrite without backing up |
| Commit is no longer in reflog | Entry expired or ref was deleted | Try `git fsck --no-reflogs --unreachable` and check other clones |
| Recovered branch seems missing files | Selected a commit older than intended or files were never committed | Check log, diff, and working tree backup |
| Pushing the recovered branch is rejected | Remote has newer history or branch protection rules | Fetch, inspect history, and push a new branch for review |

When encountering errors, verify the branch name, target commit, and local/remote state before deleting or overwriting anything.

## 15. Checklist Before Restoring a Branch

Before creating or moving a branch, verify:

- [ ] Confirm you are in the right repository and operating on the right branch.
- [ ] Run `git status` to check for uncommitted changes.
- [ ] Inspect `git reflog` or `git reflog show <branch>`.
- [ ] Locate the hash of the commit before the mistaken operation.
- [ ] Verify the commit with `git show` and `git log`.
- [ ] Create a rescue branch if the current state needs to be preserved.
- [ ] Create the recovery branch from the verified hash.
- [ ] Check the working tree, diff, and history after recovery.
- [ ] If sharing is needed, push the new recovery branch and coordinate via PR/MR.

## 16. Key Takeaways

- Reflog records the change history of HEAD and Git references in the local repository.
- `git reflog` is a good starting point for finding commits before a reset, rebase, or branch deletion.
- `HEAD@{n}` is a position in the reflog; `HEAD~n` is the number of steps back along parent commits.
- Always verify the commit with `git show`, `git show --stat`, and `git log` before creating a branch.
- `git branch <branch-name> <commit>` creates a new branch at the specified commit.
- If the old branch still exists, create a rescue branch before moving the reference.
- Reflog does not store uncommitted changes and is not shared with the remote.
- When reflog no longer has the entry, you can try `git fsck --no-reflogs --unreachable` or search in another clone.
- Reflogs and unreferenced objects can expire or be cleaned up by garbage collection; recover as soon as possible.

When a branch is lost, the key is finding the commit it previously pointed to. Once you have verified that commit, creating a new branch from its hash preserves the history and brings the work back into the development workflow in a controlled way.

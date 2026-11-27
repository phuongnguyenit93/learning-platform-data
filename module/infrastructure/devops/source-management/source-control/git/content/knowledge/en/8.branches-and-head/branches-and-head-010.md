# Safe Branch Deletion and the Meaning of -d vs -D

A branch in Git is a ref pointing to the tip commit of a branch. Once a feature branch has been integrated, you often delete the branch to keep the branch list clean. The `git branch -d` command is the safe choice because Git checks whether the branch has already been merged into an appropriate reference target. The `-D` option forces branch deletion even when Git detects unmerged commits.

This distinction is critical: deleting a branch only deletes the ref bearing the branch name; it does not immediately delete the commits the branch pointed to. However, if commits are only held by the deleted branch, they can become unreachable and eventually be pruned by garbage collection. Verify history and save a rescue branch/tag before using a force operation.

## 1. A Branch Is a Ref Pointing to a Commit

A local branch such as `feature/payment` is normally stored under the ref `refs/heads/feature/payment`. This ref points to the tip commit of the branch. When a new commit is created on the branch, Git updates the ref to point to the new commit.

Example:

```text
A---B---C---D  main
     \
      E---F    feature/payment
```

In the example, `main` points to D and `feature/payment` points to F. Commits A and B are shared history; E and F are only reachable from feature if no other ref holds them.

When deleting `feature/payment`, Git removes the ref pointing to F. Commit objects E and F are not necessarily deleted immediately; they may still be retained by the reflog, a tag, another branch, or another ref. If no reference path holds them anymore, they can be collected later.

View local branches:

```bash
git branch
git branch -vv
```

`git branch` lists local branches and marks the current branch with `*`. `-vv` adds upstream and ahead/behind status according to currently available remote-tracking data.

## 2. Safe Branch Deletion with git branch -d

Syntax:

```bash
git branch -d <branch-name>
```

Example:

```bash
git branch -d feature/payment
```

`-d` is short for `--delete`. Git deletes the branch only if the branch tip has been fully merged into the branch's upstream. If the branch has no upstream configured, Git checks whether the branch has been merged into the current `HEAD`.

If the condition is met, Git deletes the branch ref. If there are unmerged commits by that criterion, Git refuses and reports that the branch is not fully merged. This is a safeguard so you do not accidentally remove the last reference to in-progress commits.

Example when feature has already been merged into `main`:

```bash
git switch main
git branch --merged main
git branch -d feature/payment
```

Switching to `main` before deleting feature also keeps you from trying to delete the currently checked-out branch. `git branch -d` does not delete files in the current branch's working tree; it deletes the specified branch ref after checking the merge condition.

## 3. Where Does -d Check Whether a Branch Was Merged?

A common point of confusion is that `git branch -d feature` does not always check only the current branch. Git uses the upstream configured for the branch being deleted; if the branch has no upstream, Git uses the current `HEAD`.

For example, the local branch `feature/payment` tracks `origin/feature/payment`. When deleting with `git branch -d feature/payment`, Git checks whether feature's commits are reachable from its upstream `origin/feature/payment`. If there is no upstream, it checks reachability from `HEAD`.

View upstream:

```bash
git branch -vv
git config --get branch.feature/payment.remote
git config --get branch.feature/payment.merge
```

These two `git config` commands illustrate where the remote and upstream branch are configured for a branch. If the branch has no upstream yet, the commands may return no output.

Because an upstream is normally a local remote-tracking ref, fetch before relying on the latest remote state:

```bash
git fetch --all --prune
git branch -vv
```

If the upstream was deleted on the remote and the remote-tracking ref was pruned, the local branch may no longer have a valid upstream. In that case, explicitly identify the target commit to check against and use `git branch --merged <target>` or `git merge-base --is-ancestor` to verify.

## 4. Viewing Merged Branches with --merged

Before deleting, list branches already merged into a specific commit:

```bash
git branch --merged main
```

This command displays branches whose tips are reachable from `main`. Without passing a revision, Git defaults to the current `HEAD`:

```bash
git branch --merged
```

Display only branches not yet merged into the chosen milestone:

```bash
git branch --no-merged main
```

These commands are helpful for auditing before cleaning up branches. Read each branch name and check your team's conventions before deleting; release branches, maintenance branches, or branches used to mark important milestones may need to be kept even after merging.

Workflow example:

```bash
git fetch origin
git branch --merged main
git branch --no-merged main
```

If `main` is the team's integration target, the `--merged main` list shows local branches whose tip is reachable from `main`. However, this criterion does not prove that every change ever made on the branch was preserved content-wise if the team uses squash merges or cherry-picks.

## 5. Checking Ancestor Relationships with merge-base

You can check whether a branch is an ancestor of the target branch:

```bash
git merge-base --is-ancestor feature/payment main
```

Exit code `0` means the tip of `feature/payment` is an ancestor of `main`, meaning that commit is reachable from `main`. A non-zero exit code means the ancestor condition is false (or an error occurred that needs review).

This is an explicit check when confirming a branch has been integrated by commit ancestry:

```bash
if git merge-base --is-ancestor feature/payment main; then
    echo "feature/payment is merged into main"
else
    echo "feature/payment is not an ancestor of main"
fi
```

In PowerShell, you can check `$LASTEXITCODE` after the Git command to inspect the result. Do not rely solely on a merged badge in the hosting UI; understand which target branch is being used as the criterion.

## 6. Why Can git branch -d Refuse After Squash Merge or Cherry-Pick?

`git branch -d` checks reachability in the commit graph. It does not compare patch contents to deduce that changes were integrated through another mechanism.

### Squash Merge

When using a squash merge, the platform or Git command creates a new commit containing the combined changes of the feature without keeping the feature's original commits as ancestors of the new commit.

```text
          F1---F2  feature
         /
A---B---S        main
```

`S` contains the combined contents of F1 and F2, yet F1 and F2 are not ancestors of S. Therefore `git branch -d feature` may refuse even though the pull request was squash-merged successfully.

### Cherry-Pick

Cherry-pick creates a new commit on the target branch. The new commit may contain an equivalent patch to the source commit, but it has a different parent and OID. The source commit does not automatically become an ancestor of the target branch.

### Rebase

Rebase recreates commits onto a new base. The old commits may no longer be reachable from the target branch because the new commits have different OIDs. Depending on the rebase direction and which branch was kept, `-d` may still refuse.

In these cases, do not immediately switch to `-D`. First verify that the changes were genuinely integrated via the pull request, patch, tests, or `git log --cherry`/`git range-diff` where appropriate. Only after confirming the old branch is no longer needed and any commits worth keeping exist elsewhere should you consider force deletion.

## 7. Force Deletion with git branch -D

Syntax:

```bash
git branch -D <branch-name>
```

`-D` is shorthand for `--delete --force`. It instructs Git to delete the branch even if the branch is not merged according to `-d`'s safety check.

Example:

```bash
git branch -D experiment/old-parser
```

This command is useful when you intentionally discard an experimental branch or have verified that unmerged commits are no longer needed. However, `-D` does not verify that branch contents were integrated and does not create a backup of unique commits.

Before using `-D`, inspect commits unique to the branch:

```bash
git log --oneline main..experiment/old-parser
git log --graph --oneline --decorate main...experiment/old-parser
git branch -vv
```

If there are important commits, create a rescue ref first:

```bash
git branch rescue/old-parser experiment/old-parser
```

Only then delete the original branch if still needed:

```bash
git branch -D experiment/old-parser
```

The `rescue/old-parser` branch continues holding commits that might not be reachable elsewhere. Use a clear rescue name and delete it once you confirm recovery is no longer needed.

## 8. Deleting the Current Branch and Branches Used in Other Worktrees

Git does not allow deleting the branch currently checked out by `HEAD` of the current worktree. Switch to another branch first:

```bash
git switch main
git branch -d feature/payment
```

With linked worktrees, a branch may be checked out in another worktree. Check the list:

```bash
git worktree list
```

If the branch to delete is in use in another worktree, switch that worktree to a different branch or remove the worktree following the proper workflow before deleting the branch. Do not try to delete a ref while a working tree still relies on that branch; `-D` is not a substitute for releasing an in-use worktree.

If the secondary worktree is no longer needed, from the main repository:

```bash
git worktree remove ../storefront-feature
```

Only use `git worktree remove` after confirming the path is right and changes in that worktree have been saved. Then recheck `git worktree list` before deleting the branch.

## 9. Deleting Multiple Local Branches in a Controlled Manner

You can pass multiple branch names to a single command:

```bash
git branch -d feature/search feature/payment feature/profile
```

Git checks the safety condition for each branch. If any branch has not been merged, the command may report an error for that branch; read the message and inspect it individually rather than switching everything to `-D`.

To review branches merged into main:

```bash
git branch --merged main
```

Then explicitly choose the feature branches to delete. Avoid running deletion commands based on wildcards or unpreviewed pipelines, especially in repositories with release, maintenance, or other people's branches.

If you want to exclude the current branch and base branches from the candidate list, read the output and execute each branch name explicitly. Branch names can contain `/`; Git treats that as part of the ref name rather than a working directory.

## 10. Deleting a Remote-Tracking Branch vs. Deleting a Branch on the Server

A local branch and a remote-tracking branch are two different refs. For example:

- `feature/payment`: local branch in `refs/heads/`.
- `origin/feature/payment`: local remote-tracking ref in `refs/remotes/origin/` recording the latest remote state.

Delete a local remote-tracking ref:

```bash
git branch -dr origin/feature/payment
```

Or:

```bash
git branch -d -r origin/feature/payment
```

This operation only deletes the remote-tracking ref inside the current clone. It does not send a request to delete the branch on the server.

To delete the actual branch on the remote:

```bash
git push origin --delete feature/payment
```

After a branch is deleted on the server, update and clean up remote-tracking refs in your clone:

```bash
git fetch --prune origin
```

`git remote prune origin` can also clean up remote-tracking refs no longer advertised by the remote, without deleting local branches in `refs/heads/`.

## 11. Does Deleting a Branch Lose Commits?

Deleting a branch deletes a ref name, not a command that directly deletes individual commit objects. After deletion, commits may still be retained by:

- Another branch or tag pointing to that commit.
- A rescue branch you created.
- The reflog recording positions the ref previously pointed to, within the reflog retention period.
- Another ref or object referenced from reachable history.

If no ref or retaining source remains, the commit can become unreachable. Git does not necessarily delete objects immediately; garbage collection reclaims objects according to policy and grace periods. However, do not rely on the reflog or grace periods as a long-term backup.

If you accidentally deleted a branch and need to recover commits, you can check the reflog:

```bash
git reflog --all --date=local
```

Once you find the OID to keep, recreate the branch:

```bash
git branch rescue/recovered-work <COMMIT_ID>
```

Recoverability depends on the objects still existing in the repository and not having been pruned yet. If commits are important, create a rescue ref or tag before deleting the branch.

## 12. Safe Branch Deletion Workflow

Before deleting a feature branch, follow this sequence:

**Step 1: Identify the branch and working state**

```bash
git status --short
git branch -vv
git worktree list
```

Ensure you are in the right repository, the target branch is not the currently checked-out branch, and it is not in use by another worktree.

**Step 2: Update remote info**

```bash
git fetch --all --prune
```

This updates remote-tracking refs before checking upstreams and history.

**Step 3: Inspect commits unique to the branch**

```bash
git log --oneline main..feature/payment
git log --graph --oneline --decorate main...feature/payment
```

If there are unique commits, verify whether they have been integrated via merge commit, squash merge, or cherry-pick.

**Step 4: Check merge status**

```bash
git branch --merged main
git branch --no-merged main
git merge-base --is-ancestor feature/payment main
```

Note: `--merged main` checks reachability from `main`; whereas `git branch -d` uses the branch's upstream or `HEAD` if there is no upstream. Ensure the verification target matches your deletion goal.

**Step 5: Save commits worth keeping**

If valuable unique commits remain, create a rescue branch or tag:

```bash
git branch rescue/payment-before-delete feature/payment
```

**Step 6: Delete with -d or -D**

If the branch is merged by Git's criteria:

```bash
git branch -d feature/payment
```

Only when you have verified unmerged commits are no longer needed or are saved elsewhere:

```bash
git branch -D experiment/old-parser
```

**Step 7: Confirm**

```bash
git branch --list
git branch -vv
git log --oneline --decorate -5
```

Check that the target branch is gone and the main branch still points to the expected commit.

## 13. Common Scenarios

### Branch Merged via Merge Commit

If the feature tip is an ancestor of the target branch, `git branch -d` normally deletes it after checking against its upstream or `HEAD`. Verify with `git merge-base --is-ancestor`.

### Pull Request Squash-Merged, Yet -d Refuses

Git may not consider the feature's original commits to be ancestors of main. Verify the pull request was merged, check that the patch is already in main, and save commits if needed. Only then consider `git branch -D`.

### Unmerged but Stale Branch

Inspect unique commits with `git log main..branch`. If it is an abandoned experiment that does not need to be kept, you can use `-D` after confirming there is no content needing rescue. If unsure, create a rescue branch first.

### Git Reports the Branch Is Used in Another Worktree

Run `git worktree list`, switch branches, or remove the secondary worktree following the proper workflow. Delete the branch once no worktree has it checked out.

### Wanting to Delete a Branch on GitHub/GitLab or Server

`git branch -d` only deletes the local branch. Use `git push <remote> --delete <branch>` to send a request to delete the remote branch, then fetch/prune to update your clone.

## 14. Practice Exercises

In a test repository, create the following branches from `main`:

- `feature/merged`: has one commit and is merged into `main` via a merge commit.
- `feature/squashed`: has one commit brought into `main` via squash merge or simulated by a new commit containing the same change.
- `experiment/unmerged`: has at least two unique unintegrated commits.

Perform:

1. Run `git branch --merged main` and `git branch --no-merged main`; identify which branches appear in each list.
2. Use `git merge-base --is-ancestor feature/merged main` to confirm the ancestor relationship.
3. Try `git branch -d feature/merged`; observe the merged branch being deleted.
4. Try `git branch -d feature/squashed`; explain why Git may refuse even though the content was squashed into main.
5. Use `git log main..experiment/unmerged` to list unintegrated commits.
6. Create a rescue branch `rescue/experiment` pointing to `experiment/unmerged`, then use `git branch -D experiment/unmerged` in the test repository.
7. Confirm the commits remain reachable via the rescue branch and explain why deleting a branch does not immediately delete objects.
8. Create a test bare remote, push a branch to the remote, then distinguish `git branch -dr origin/feature/demo` from `git push origin --delete feature/demo`.
9. Use `git worktree add` to create a secondary worktree checking out a branch, try deleting the in-use branch, and observe Git protecting the ref; then release the worktree and delete the branch properly.

You have completed the exercise when you can explain the safety condition of `-d`, the risk of `-D`, distinguish deleting local branches from remote-tracking/remote branches, and know how to preserve important commits before deleting a ref.

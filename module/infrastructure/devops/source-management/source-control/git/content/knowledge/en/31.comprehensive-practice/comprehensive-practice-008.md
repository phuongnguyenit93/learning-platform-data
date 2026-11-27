# Recovering Deleted or Accidentally Reset Branches Using Reflog

A Git branch is simply a named reference pointing to a commit. When a branch is deleted or accidentally reset, the reference name may disappear or point elsewhere, yet the old commits usually remain in the repository for some time. The **reflog** records local reference updates, letting you locate the prior commit and create a recovery branch.

The key is to find the right commit, anchor it with a new ref, and only then decide how to restore the branch name. Do not rush to run garbage collection, prune objects, or keep resetting before establishing the state. Reflogs have a retention window and do not replace backups.

This lab covers common recovery scenarios: deleting a local branch, an accidental reset, a rebase that shifts the tip, deleting a remote-tracking branch, and finding commits that are no longer referenced.

## 1. Understanding Git Branches Before Recovering

A branch like <code>feature/payment</code> is a ref pointing to the branch's tip commit. When you create a new commit on that branch, the ref updates to point to the new commit.

Example:

~~~text
A---B---C  main
     \
      D---E  feature/payment
~~~

In this example, <code>feature/payment</code> points to commit E. If you delete the branch:

~~~bash
git branch -D feature/payment
~~~

Git removes the ref named <code>refs/heads/feature/payment</code>. Commits D and E are not necessarily deleted from the object database right away. They may still be kept alive by:

- The reflog of HEAD or another ref.
- Another branch, tag, or ref.
- Another clone of the repository.
- Objects not yet removed by garbage collection.

If no ref points to E anymore, the commit becomes unreachable from existing refs. Git can still locate it via the reflog or <code>git fsck</code> until the object is actually pruned.

## 2. What Is the Reflog?

The reflog (reference log) is a local log recording every time a ref changes its value. Reflog helps you see which commits HEAD or a branch previously pointed to.

Common operations recorded in the reflog:

- A new commit updating a branch tip.
- A checkout or switch moving HEAD to another branch/commit.
- A reset moving a branch or HEAD to a different commit.
- A rebase replacing a commit sequence and updating the branch.
- Certain merges, cherry-picks, or other ref updates.

How reflog differs from commit history:

| Commit history | Reflog |
|---|---|
| Describes parent/child relationships between commits | Records changes to refs |
| Shared via push/fetch through commits and refs | Local log only; never pushed to remotes |
| Traversed with <code>git log</code> | Viewed with <code>git reflog</code> |
| Represents project history | Helps find past ref states |

The reflog is not a complete history of every file state that ever existed on disk. It tracks ref movements, not individual uncommitted edits in the working tree.

## 3. HEAD Reflog and Branch Reflog

Git normally maintains a reflog for HEAD and for local branches.

- **HEAD reflog** records movements of HEAD, such as checkout, switch, commit, or reset.
- **Branch reflog** records changes to a specific branch ref's tip.

View the HEAD reflog:

~~~bash
git reflog
~~~

Or explicitly:

~~~bash
git reflog show HEAD
~~~

View the reflog of an existing branch:

~~~bash
git reflog show refs/heads/feature/payment
~~~

View all available reflogs:

~~~bash
git reflog show --all
~~~

You can include readable timestamps:

~~~bash
git reflog show --date=iso
git reflog show HEAD --date=local
~~~

When a branch is deleted, its own branch reflog is normally deleted along with the ref. The HEAD reflog may still hold traces if that branch was ever checked out in this repository. If the branch was never checked out in the current clone, search other reflogs, other clones, or unreachable objects.

## 4. Reading a Reflog Line

Example:

~~~text
a12bc34 HEAD@{0}: checkout: moving from feature/payment to main
e56fa78 HEAD@{1}: commit: Add payment validation
91ab234 HEAD@{2}: commit: Create payment service
~~~

How to read it:

- <code>HEAD@{0}</code> is the most recently recorded position of HEAD.
- <code>HEAD@{1}</code> is the state immediately before the newest entry.
- The OID at the start of the line is the commit the ref pointed to after the recorded update.
- The text after the colon describes the action that triggered the update.

In this example, HEAD currently points to a commit on <code>main</code>. The preceding entry records the commit <code>Add payment validation</code>, likely the latest tip of <code>feature/payment</code> before switching to main.

Never assume <code>HEAD@{1}</code> is always the commit to recover. Reflog indices shift with every new Git operation. Read the message, inspect the OID, and save the full hash before using it.

## 5. Scenario 1: Accidentally Deleting a Local Branch

Suppose you delete a branch:

~~~bash
git branch -D feature/payment
~~~

Then you realize the branch held unmerged commits.

### Step 1 — Check Existing Branches and Refs

~~~bash
git branch -avv
git show-ref
~~~

Confirm whether the local branch is gone or still exists as a remote-tracking ref. If <code>origin/feature/payment</code> still exists, you can recreate the local branch directly from that ref:

~~~bash
git switch -c feature/payment origin/feature/payment
~~~

If the remote-tracking ref is gone too, continue searching via reflog.

### Step 2 — Find Traces in the HEAD Reflog

~~~bash
git reflog show HEAD --date=local
~~~

Look for an entry with a message like:

~~~text
checkout: moving from feature/payment to main
~~~

The entry immediately before it is often the final HEAD commit on the branch before leaving it. Read nearby lines and identify the commit containing the desired work.

### Step 3 — Inspect the Candidate Commit

Suppose the full OID found is <code>e56fa78...</code>:

~~~bash
git show --stat --oneline e56fa78
git show -s --format=fuller e56fa78
git log --graph --oneline --decorate e56fa78
~~~

Verify the author, timestamp, message, and changed files to confirm it is the tip you want to recover.

### Step 4 — Create a Recovery Branch

~~~bash
git branch rescue/payment-before-delete e56fa78
~~~

Or recreate the original branch name directly if that name is free:

~~~bash
git switch -c feature/payment e56fa78
~~~

Creating a new ref makes the commit reachable again and prevents garbage collection from pruning it. Prefer creating a rescue branch first before deciding whether to rename it or update the remote.

## 6. Scenario 2: Accidental Reset With git reset --hard

Suppose you are on <code>feature/payment</code> and accidentally run:

~~~bash
git reset --hard HEAD~3
~~~

The current branch moves back three commits; the index and tracked working tree also revert to that older commit's state. The previous commits can usually still be found in the reflog.

Inspect:

~~~bash
git reflog show HEAD --date=local
git reflog show refs/heads/feature/payment --date=local
~~~

Illustrative output:

~~~text
91ab234 HEAD@{0}: reset: moving to HEAD~3
e56fa78 HEAD@{1}: commit: Add payment validation
a12bc34 HEAD@{2}: commit: Add payment endpoint
~~~

OID <code>e56fa78</code> is the position before the reset. Verify it with <code>git show</code>, then create a rescue branch:

~~~bash
git branch rescue/payment-before-reset e56fa78
~~~

If your goal is to restore the working branch back to its old tip, you can reset the branch to that OID after checking the working tree and protecting any new edits:

~~~bash
git status
git reset --hard e56fa78
~~~

That final reset alters the current branch, index, and tracked working tree. Only run it when you truly intend to restore all three to that commit and have saved any edits you want to keep. If unsure, create only the rescue branch and keep analyzing.

## 7. Distinguishing reset --soft, --mixed, and --hard

The reset modes affect the branch, index, and working tree differently:

| Command | Branch/HEAD | Index | Tracked working tree |
|---|---|---|---|
| <code>git reset --soft &lt;commit&gt;</code> | Moves to target commit | Unchanged | Unchanged |
| <code>git reset --mixed &lt;commit&gt;</code> | Moves to target commit | Set to target commit | Keeps existing files |
| <code>git reset --hard &lt;commit&gt;</code> | Moves to target commit | Set to target commit | Set to target commit |

Reflog can help recover the branch tip after all three reset modes. However, recovery prospects for working tree files differ.

In particular, <code>reset --hard</code> can discard uncommitted tracked changes by overwriting the working tree. Reflog does not store those contents. Untracked files can also be removed if they collide with checked-out paths; other untracked files are not tracked by reflog.

If an accidental reset overwrote uncommitted work, check your IDE local history, backups, filesystem snapshots, or other copies. Reflog cannot promise recovery of overwritten uncommitted files.

## 8. Scenario 3: Rebase Shifted the Branch to a Different History

Rebase creates new commits with new parents, so the OIDs of rebased commits usually change.

Example before rebase:

~~~text
A---B---C  main
     \
      D---E  feature/payment
~~~

After rebasing onto the updated main:

~~~text
A---B---C---D'---E'  feature/payment
~~~

If you rebased by mistake or want to find the pre-rebase tip, inspect the reflog:

~~~bash
git reflog show HEAD --date=local
git reflog show refs/heads/feature/payment --date=local
~~~

Look for entries mentioning rebase or the checkout/reset immediately preceding it. Verify the pre-rebase OID and anchor it with a rescue branch:

~~~bash
git branch rescue/payment-before-rebase <old-commit>
~~~

If the rebase is still in progress and unfinished, check status first:

~~~bash
git status
~~~

If your goal is simply to cancel the active rebase, the standard command is:

~~~bash
git rebase --abort
~~~

This restores the repository to its state before the rebase began, provided Git is still mid-rebase. Once the rebase has finished, use reflog to locate the old tip.

## 9. Scenario 4: Accidentally Resetting the Wrong Branch

Sometimes your terminal is on <code>main</code> when you thought you were on <code>feature/payment</code>. One reset command can accidentally move an important branch.

First, check the current branch and reflogs:

~~~bash
git branch --show-current
git reflog show HEAD --date=local
git reflog show refs/heads/main --date=local
~~~

If <code>main</code> was reset, main's branch reflog usually retains the prior value:

~~~bash
git reflog show refs/heads/main
~~~

Find the pre-reset OID, inspect the commit, and create a rescue branch:

~~~bash
git branch rescue/main-before-reset <old-main-commit>
~~~

Do not rush to reset <code>main</code> back if others already updated the branch or added commits after the incident. Compare against the remote and coordinate with your team before moving shared refs.

## 10. Scenario 5: A Remote Branch Was Deleted

Deleting a remote branch is typically done with:

~~~bash
git push origin --delete feature/payment
~~~

Or via the hosting platform UI. This deletes the ref on the server; it does not automatically erase every copy of those commits in existing clones.

Check local remote-tracking refs:

~~~bash
git branch -r
git show-ref
~~~

You can filter output by branch name. In Git Bash/Linux/macOS use <code>grep</code>; in PowerShell use <code>Select-String</code>:

~~~powershell
git show-ref | Select-String 'feature/payment'
~~~

If <code>origin/feature/payment</code> still exists, recreate the local branch from it. If it was already pruned, check the remote-tracking ref's reflog if still present:

~~~bash
git reflog show refs/remotes/origin/feature/payment
~~~

Remote-tracking reflogs are also local data and may have been deleted along with the ref. If missing, look for the commit in the HEAD reflog, other local branches, tags, teammates' clones, or backups.

### Restoring the Branch on the Remote

Once you have a local rescue branch and verified the commit, you can push the original branch name back:

~~~bash
git push origin rescue/payment-before-delete:refs/heads/feature/payment
~~~

This creates/updates remote branch <code>feature/payment</code> from the rescue branch tip. Before pushing, inspect the remote state to avoid overwriting a new branch someone else already recreated after the incident.

## 11. Reflog Lacks the Entry You Need: Using git fsck

If a branch was deleted and the reflog no longer holds a trace, the commit may still exist as an unreachable object. <code>git fsck</code> helps locate such objects.

Run:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

Git may list lines like:

~~~text
unreachable commit e56fa78...
unreachable tree 91ab234...
unreachable blob a12bc34...
~~~

Focus on the <code>unreachable commit</code> lines. These are candidates that could represent the old branch tip or intermediate commits.

Inspect each candidate:

~~~bash
git show -s --format=fuller e56fa78
git show --stat --oneline e56fa78
git log --graph --oneline e56fa78
~~~

Once you identify the right commit:

~~~bash
git branch rescue/recovered-payment e56fa78
~~~

After creating the rescue branch, the commit becomes reachable again from that ref.

<code>git fsck</code> can list many unrelated objects. Cross-check commit messages, timestamps, parents, and changed files; never pick a commit solely because its timestamp is close to the incident.

## 12. Can You Use git fsck --lost-found?

Git supports:

~~~bash
git fsck --full --no-reflogs --lost-found
~~~

The <code>--lost-found</code> option writes found unreachable objects into <code>.git/lost-found/</code> for manual inspection. Commits and blobs are written to their respective subdirectories.

This writes files into the repository's metadata directory. Only use it if you need a staging place to inspect dangling objects; normally, reading OIDs directly from <code>git fsck</code> output and inspecting them with <code>git show</code> is sufficient.

Do not delete the <code>lost-found</code> directory until you determine whether any objects inside need to be kept.

## 13. Using ORIG_HEAD When Appropriate

Git saves prior HEAD positions before certain major operations in a special ref called <code>ORIG_HEAD</code>. This ref is occasionally useful right after a reset, merge, or rebase.

Inspect:

~~~bash
git show -s --format=fuller ORIG_HEAD
git log -1 --oneline ORIG_HEAD
~~~

If it matches the commit you need to recover, create a rescue branch:

~~~bash
git branch rescue/orig-head ORIG_HEAD
~~~

However, <code>ORIG_HEAD</code> is overwritten by subsequent operations and is not a full history log. Always cross-check against the reflog and commit contents before relying on it.

## 14. Creating a Rescue Branch Before Restoring the Old Branch Name

When you locate a suspect commit, the safest approach is to create a dedicated rescue branch first:

~~~bash
git branch rescue/recovered-feature <commit-oid>
~~~

Then verify:

~~~bash
git show --stat --oneline rescue/recovered-feature
git log --graph --decorate --oneline rescue/recovered-feature
git status
~~~

A rescue branch gives three benefits:

1. Keeps the commit out of an unreachable state.
2. Allows comparing against the current branch.
3. Lets the team review before restoring the official branch name.

Once the commit is verified, if the old name is not taken, you can recreate it:

~~~bash
git switch -c feature/payment rescue/recovered-feature
~~~

If the branch name has already been recreated with a different tip, do not overwrite it immediately. Compare both histories and coordinate with whoever is working on that branch.

## 15. Distinguishing Commit Recovery From Uncommitted Change Recovery

Reflog primarily recovers ref positions, not every state that ever existed in the working tree.

| Lost data | Can reflog help? | Recovery path |
|---|---|---|
| Commit created, then branch deleted | Usually yes | Find OID via reflog or fsck, create a new branch |
| Branch reset back to an older commit | Usually yes | Find pre-reset tip in reflog |
| Commits replaced after rebase | Usually yes | Find pre-rebase tip in reflog |
| Uncommitted tracked changes overwritten by reset --hard | Not directly | IDE local history, backups, or filesystem recovery |
| Untracked files deleted by clean/reset | No | Backups, snapshots, or file recovery tools |
| Staged but uncommitted file overwritten | Not guaranteed | Check backups; index is not a versioned log |
| Commit already pruned from object database | No | Search other clones, remotes, bundles, or backups |

If important uncommitted changes exist, copy the working tree or back up patches before running further recovery commands. Avoid letting new operations overwrite remaining data.

## 16. Why Acting Early Matters

Reflog entries expire over time. Common defaults are:

- Reflog entries expire after roughly 90 days if the commit is still reachable.
- Entries pointing to unreachable commits expire after roughly 30 days.

Actual values depend on configuration and Git version. Check yours:

~~~bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
git config --show-origin --get gc.pruneExpire
~~~

If no explicit value is configured, Git uses the defaults of your installed version.

Once reflog entries expire, objects no longer referenced by any ref can be pruned by garbage collection afterward. Once an object is physically deleted from every copy, reflog cannot reconstruct commit contents.

Therefore, as soon as you spot an accidental reset or deletion:

1. Stop any unnecessary cleanup commands.
2. Locate the commit via reflog.
3. Create a rescue branch to preserve the commit.
4. Resume normal work only after the data is safe.

## 17. Commands to Avoid During Recovery

Before locating and securing the target commits, avoid:

~~~bash
git gc --prune=now
git reflog expire --expire=now --all
git prune
~~~

These commands can erase reflog trails or delete unreferenced objects. In particular, <code>--prune=now</code> bypasses the safety grace period that normally protects newly unreachable objects.

Also avoid running further resets, rebases, or force pushes before recording the OIDs you need to recover. Every operation can add new entries, shifting <code>HEAD@{n}</code> indices and making inspection harder.

There is no need to run <code>git gc</code> just because you recovered a branch. Once a rescue branch anchors the commit, Git manages objects automatically through its normal lifecycle.

## 18. Finding Commits via Other Clones or Backups

Because reflogs are local, another clone may still hold a branch or commit lost in your current clone.

Ask a teammate to check:

~~~bash
git branch -avv
git reflog --all --date=local
git log --all --graph --decorate --oneline
~~~

If they find the commit, they can share the OID and push a rescue branch to the remote per team workflow. Do not send <code>.git</code> directories over insecure channels if the repository contains sensitive data.

Other sources:

- Previously created tags.
- Pull Request / Merge Request refs or commits retained by the hosting platform.
- Previously exported Git bundles.
- Mirror or backup repositories.
- CI/workspace clones still holding the objects.
- Filesystem backups.

Never assume a hosting provider always retains reflogs or deleted objects. Retention policies and recovery capabilities depend on the platform; verify with administrators or the provider.

## 19. Recovering a Deleted Branch When Multiple Clones Exist

In a team, one member might delete a local branch while a teammate still has it. Before rewriting the remote, ask whether the branch still exists in any clone.

If a teammate has the branch:

~~~bash
git log --oneline --decorate feature/payment
git show -s --format=%H feature/payment
~~~

They can create a rescue branch and push it to the remote:

~~~bash
git branch rescue/payment-team-copy feature/payment
git push -u origin rescue/payment-team-copy
~~~

Once the rescue branch appears on the remote, the affected person can fetch and recreate the branch:

~~~bash
git fetch origin
git switch -c feature/payment origin/rescue/payment-team-copy
~~~

This shares commits through a clean new ref without manually transferring object databases. Confirm the OID and permissions before proceeding.

## 20. Complete Recovery Workflow for a Deleted Branch

Suppose <code>feature/report-export</code> was deleted by mistake and its remote-tracking ref is also gone.

**Step 1 — Check current state**

~~~bash
git status
git branch -avv
git show-ref
~~~

Note the current branch and any uncommitted changes.

**Step 2 — Search the reflog**

~~~bash
git reflog show HEAD --date=local
git reflog show --all --date=local
~~~

Look for entries mentioning the last checkout of <code>feature/report-export</code>.

**Step 3 — Inspect the candidate commit**

~~~bash
git show -s --format=fuller <candidate-oid>
git show --stat --oneline <candidate-oid>
git log --graph --oneline <candidate-oid>
~~~

**Step 4 — Create a rescue branch**

~~~bash
git branch rescue/report-export <candidate-oid>
~~~

**Step 5 — Restore the local branch name**

If the old name does not exist yet:

~~~bash
git switch -c feature/report-export rescue/report-export
~~~

If the name already exists, compare both before deciding to rename or update the ref.

**Step 6 — Verify**

~~~bash
git log --graph --decorate --oneline --all
git status
git show-ref
~~~

**Step 7 — Restore on remote if needed**

After confirming the local branch is right and the remote does not hold a branch of the same name with new work:

~~~bash
git push -u origin feature/report-export
~~~

If pushing from a rescue branch to the remote branch name:

~~~bash
git push origin rescue/report-export:refs/heads/feature/report-export
~~~

**Step 8 — Notify the team**

Share the OID and recovery timestamp in the appropriate team channel. Remind teammates to resync refs and avoid force pushing from stale clones.

## 21. Complete Recovery Workflow for an Accidental Reset

Suppose <code>feature/payment</code> was accidentally reset back three commits.

**Step 1 — Do not reset further**

Check:

~~~bash
git status
git branch --show-current
~~~

If new local changes exist, safeguard them first.

**Step 2 — Read the reflog**

~~~bash
git reflog show HEAD --date=local
git reflog show refs/heads/feature/payment --date=local
~~~

Locate the <code>reset: moving to ...</code> entry and the OID prior to that operation.

**Step 3 — Inspect the old commit**

~~~bash
git show --stat --oneline <old-tip>
git log --graph --oneline <old-tip>
~~~

**Step 4 — Create a rescue branch**

~~~bash
git branch rescue/payment-before-reset <old-tip>
~~~

**Step 5 — Choose how to proceed**

- If you only need to keep the old commits accessible, the rescue branch is enough.
- If you want to move the current branch back to the old tip, verify status and then perform an intentional reset.
- If new commits were made after the reset, compare the two branches and choose merge, cherry-pick, or rebase as appropriate.

**Step 6 — Verify and share**

~~~bash
git log --graph --decorate --oneline --all
git status
~~~

Push only after verifying history and coordinating with your team.

## 22. Common Recovery Commands Reference

| Goal | Command |
|---|---|
| View HEAD reflog | <code>git reflog show HEAD</code> |
| View a branch's reflog | <code>git reflog show refs/heads/&lt;branch&gt;</code> |
| View all available reflogs | <code>git reflog show --all</code> |
| Inspect a commit by OID | <code>git show &lt;oid&gt;</code> |
| Inspect commit metadata | <code>git show -s --format=fuller &lt;oid&gt;</code> |
| Create a rescue branch | <code>git branch rescue/&lt;name&gt; &lt;oid&gt;</code> |
| Find unreachable objects | <code>git fsck --full --no-reflogs --unreachable</code> |
| Check ORIG_HEAD | <code>git show ORIG_HEAD</code> |
| View branches and remote refs | <code>git branch -avv</code> |
| Inspect history across all refs | <code>git log --all --graph --decorate --oneline</code> |

Always substitute placeholders with verified full OIDs. Avoid relative references like <code>HEAD@{1}</code> after running additional commands that shift the reflog; save the exact hash first.

## 23. Common Misconceptions

| Misconception | Reality |
|---|---|
| Deleting a branch immediately deletes its commits | It deletes the ref; commits may stay in reflog or unreachable objects |
| Reflogs are pushed to remotes | Local reflogs are never pushed or fetched like branches |
| <code>HEAD@{1}</code> is always the pre-mistake commit | It shifts with recent actions; always verify message and OID |
| Reflog recovers files overwritten by reset --hard | Reflog recovers refs/commits, not uncommitted working tree edits |
| <code>git fsck</code> always recovers every lost commit | It only finds objects still present in the object database |
| Deleting a remote branch deletes it in all clones | Existing clones may still retain local branches or objects |
| ORIG_HEAD always holds the commit you want | It can be overwritten and only tracks certain operations |
| It is safe to run gc right after deleting a branch | Garbage collection can prune unreachable objects once grace periods expire |

## 24. Preventing Accidental Deletions or Resets

Good habits to reduce risk:

- Before deleting a branch, verify whether it is merged or has copies worth keeping.
- Use <code>git branch --merged</code> to list branches already merged into the current branch.
- Verify your current branch name before running reset or rebase.
- Prefer creating a backup branch before major history-rewriting operations.
- Before <code>reset --hard</code>, run <code>git status</code> and save uncommitted work.
- Never run cleanup/gc right after an incident.
- For shared branches, coordinate with the team before force pushing or restoring remote names.
- Maintain backups, bundles, or mirrors for critical repositories.
- Remember that reflogs expire and may not exist in other clones.

You can create a backup ref before any risky operation:

~~~bash
git branch backup/payment-before-rewrite feature/payment
~~~

This ref preserves the current tip until you explicitly delete the backup branch. It is a simple safety checkpoint before an intentional rebase or reset.

## 25. Practice Exercises in a Sandbox Repository

Create a dedicated sandbox repository for practice; never use an active work repository.

### Exercise A — Delete a Branch and Recover It

~~~bash
git init --initial-branch=main recovery-lab
cd recovery-lab
echo base > README.md
git add README.md
git commit -m "Initial commit"
git switch -c feature/demo
echo first > feature.txt
git add feature.txt
git commit -m "Create feature"
echo second >> feature.txt
git commit -am "Extend feature"
git switch main
git branch -D feature/demo
git reflog show HEAD
~~~

The <code>--initial-branch</code> option requires Git 2.28+. On older versions, run <code>git init recovery-lab</code>; after the first commit, rename the initial branch to <code>main</code> with <code>git branch -M main</code> if needed.

Find the last tip commit of the feature branch before switching to main and recreate the branch:

~~~bash
git branch rescue/demo <commit-oid>
git log --oneline rescue/demo
~~~

### Exercise B — Accidental Reset

~~~bash
git switch rescue/demo
git reset --hard HEAD~1
git reflog show HEAD
~~~

Find the pre-reset commit and create a second rescue branch:

~~~bash
git branch rescue/demo-before-reset <old-oid>
git log --oneline rescue/demo-before-reset
~~~

Compare the current branch with the rescue branch:

~~~bash
git diff rescue/demo-before-reset...HEAD
git log --graph --decorate --oneline --all
~~~

### Exercise C — Finding an Unreachable Commit

In the lab repository, delete one of the auxiliary rescue branches to leave an unreachable commit, then locate it:

~~~bash
git branch -D rescue/demo-before-reset
git fsck --full --no-reflogs --unreachable
~~~

Find the <code>unreachable commit</code> line, inspect the commit, and recreate a new branch from it. This exercise demonstrates that commits can still reside in the object database even without a branch name.

## 26. Incident Recovery Checklist

- [ ] Stopped unnecessary reset, rebase, gc, or prune operations.
- [ ] Checked the working tree and safeguarded remaining local changes.
- [ ] Checked branches, tags, remote-tracking refs, and other clones.
- [ ] Read the HEAD reflog and any surviving branch reflogs.
- [ ] Verified candidate commit OIDs via contents, parents, and timestamps.
- [ ] Checked ORIG_HEAD if relevant.
- [ ] Used git fsck if the reflog lacked the target entry.
- [ ] Created a rescue branch to anchor the commit before making further edits.
- [ ] Distinguished commit recovery from uncommitted file recovery.
- [ ] Verified history before pushing or restoring remote branch names.
- [ ] Notified the team if a shared branch was affected.

## 27. Key Points to Remember

- A branch is a ref pointing to a commit; deleting a branch does not immediately delete objects.
- Reflog records local changes to HEAD and branch refs.
- Inspect reflogs with <code>git reflog</code>, <code>git reflog show HEAD</code>, or <code>git reflog show &lt;ref&gt;</code>.
- After deleting a branch, its branch reflog may disappear with the ref; the HEAD reflog or other clones may still hold traces.
- After a reset or rebase, find the old tip in the reflog and inspect the commit before restoring.
- <code>git fsck --full --no-reflogs --unreachable</code> helps locate commits no longer held by refs/reflogs while their objects still exist.
- Create a rescue branch to keep commits from remaining unreachable.
- <code>ORIG_HEAD</code> is occasionally helpful but can be overwritten.
- Reflog does not recover uncommitted working tree changes overwritten by <code>reset --hard</code>.
- Reflogs expire; avoid running expire, prune, or gc until recovery is complete.
- Local reflogs are never pushed; other clones and backups serve as additional recovery sources.

Reflog is one of Git's most important rescue tools. When a branch is accidentally deleted or moved, locate the old commit, verify its contents, create a rescue branch, and only then restore the branch name or update the remote. Acting promptly and avoiding object cleanup greatly increases your odds of recovering lost history.

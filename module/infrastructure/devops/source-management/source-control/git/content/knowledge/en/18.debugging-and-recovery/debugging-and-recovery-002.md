# Reflog Records Reference Movements and Retention Limits

Sometimes you just ran <code>git reset --hard</code>, rebased the wrong branch, amended a commit, or deleted a local branch before realizing you still need the old commit. Regular history via <code>git log</code> may no longer display that commit because it is no longer in the ancestor chain of the current branch. In this situation, the **reflog** is the first place to check: it records movements of local references and can help you locate the commit before the mistaken operation.

Reflog is very useful for recovery, but it is not an indefinite backup. Reflog entries have expiration policies; once an entry expires and the Git object is no longer referenced, garbage collection can clean up unused objects. Understanding what reflog records, where it is stored, and how long it is kept helps you recover in time and avoid relying on it as your sole backup mechanism.

This lesson belongs to the **Debugging and Recovery** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; it also builds skills in collaborating through branches, resolving conflicts, tracing changes, and recovering from mistaken operations while preserving important history. Reflog adds an important perspective for tracing and recovering operations that altered references in the local repository.

## 1. What Is Reflog?

Reflog is short for **reference log**. It is a log that records each time the value of a Git reference is updated in the local repository. A reference is a name pointing to a Git object, usually a commit, for example:

- <code>HEAD</code>: the current location checked out in the repository.
- <code>refs/heads/main</code>: the local branch named <code>main</code>.
- <code>refs/heads/feature/login</code>: the local branch <code>feature/login</code>.
- <code>refs/remotes/origin/main</code>: the remote-tracking branch recording the position of branch <code>main</code> on remote <code>origin</code>.

When a reference moves from one commit to another, Git can record that event in the reflog. For example, when you create a new commit on the current branch, the branch and HEAD are updated. When checking out another branch, HEAD moves to the new position. When resetting, rebasing, or cherry-picking, references can also be updated and the reflog records these movements.

A reflog entry typically shows:

- The commit value the reference points to after the update.
- Action details, such as commit, checkout, reset, or rebase.
- The timestamp when the event occurred.
- The actor's identity according to the current Git environment.

Reflog is data for managing references within the current clone. It is not part of the commit graph shared between collaborators via fetch or push.

## 2. How Does Reflog Differ from git log?

The two commands answer different questions:

- <code>git log</code> displays commits reachable from the selected commit or reference via parent-child relationships.
- <code>git reflog</code> displays the history of updates to local references, even when a commit is no longer part of the branch's current history.

For example, suppose you have the history:

~~~text
A---B---C   main
~~~

Then you run:

~~~bash
git reset --hard HEAD~1
~~~

The <code>main</code> branch moves from commit <code>C</code> back to <code>B</code>:

~~~text
A---B   main
     \
      C   (no longer the tip of main)
~~~

At this point <code>git log main</code> only shows <code>B</code> and its ancestor commits. Commit <code>C</code> is no longer in the history reachable from <code>main</code>. However, the reflog of HEAD or the <code>main</code> branch may still record the position before the reset, helping you find the hash of <code>C</code>.

| Criterion | git log | git reflog |
|---|---|---|
| Records | Commit history by parent-child relationships | Local reference movements |
| Commits no longer on current branch | Usually not visible if no other ref points to them | May still be visible while the reflog entry remains valid |
| Scope | Commit graph reachable from the selected ref | Log within the local repository |
| Shared via push/fetch | Commit history can be shared | Reflog is not pushed/fetched to other machines |
| Retention | Commits persist while referenced or until objects are cleaned | Reflog entries have their own expiration policies |

Reflog does not replace <code>git log</code>. When you want to understand project history and integrated commits, use log. When you want to know where HEAD or a local branch previously pointed, check reflog.

## 3. Operations That Typically Create Reflog Entries

Reflog can record operations that change references, such as:

| Operation | What Can Appear in Reflog |
|---|---|
| <code>git commit</code> | HEAD and the current branch advance to the new commit |
| <code>git switch</code> or <code>git checkout</code> | HEAD moves to another branch or commit |
| <code>git reset</code> | HEAD and the current branch move to the selected commit |
| <code>git commit --amend</code> | HEAD and the branch are updated to the replacement commit |
| <code>git rebase</code> | HEAD and the branch move through the replayed commits |
| <code>git merge</code> | The current branch is updated after the merge completes |
| <code>git cherry-pick</code> | HEAD and the branch move to the new commit after successful application |
| <code>git fetch</code> | Remote-tracking refs may be updated |

Not every Git command creates a reflog entry. Operations that only modify the working tree or index without updating references usually do not create a corresponding reflog entry. For example, editing a file in an editor, running <code>git add</code>, or viewing <code>git diff</code> does not move a branch.

In non-bare repositories, Git normally enables reflog for HEAD and local branches; remote-tracking refs may also have reflogs depending on configuration. The <code>core.logAllRefUpdates</code> setting controls reflog creation for default reference groups. With the value <code>always</code>, Git creates reflogs for more references. Therefore, you should not assume every ref in every repository is guaranteed to have a reflog.

## 4. Viewing the Reflog

Basic commands:

~~~bash
# View the reflog of HEAD
git reflog

# Explicit syntax
git reflog show HEAD

# View the reflog of a local branch
git reflog show main

# View the reflog of all references that have a reflog
git reflog show --all
~~~

The output typically looks like:

~~~text
e4f5a6b HEAD@{0}: reset: moving to HEAD~1
c3d4e5f HEAD@{1}: commit: add payment validation
b2c3d4e HEAD@{2}: commit: create payment endpoint
a1b2c3d HEAD@{3}: checkout: moving from feature/payment to main
~~~

In the example:

- <code>HEAD@{0}</code> is the latest entry in HEAD's reflog.
- <code>HEAD@{1}</code> is the entry immediately before the latest entry.
- The entry with message <code>commit: add payment validation</code> indicates that HEAD once pointed to commit <code>c3d4e5f</code>.
- The latest reset entry records moving HEAD back to <code>HEAD~1</code>.

You can add timestamps to make it easier to identify events:

~~~bash
git reflog --date=local
git reflog show --date=iso main
git reflog show --all --date=relative
~~~

Commonly used date formats include <code>relative</code>, <code>local</code>, <code>iso</code>, and <code>iso-strict</code>. Choose an appropriate format to cross-reference with the time you performed the operation.

### Viewing Details of a Reflog Entry

Reflog displays commit hashes that you can inspect with other commands:

~~~bash
# View the recorded commit contents
git show c3d4e5f

# View the list of changed files
git show --stat c3d4e5f

# View the commit and surrounding history
git log --oneline --graph --decorate c3d4e5f
~~~

Do not recover based solely on a single message line. Verify the hash, commit contents, branch, and timestamp to be certain you select the right state.

## 5. Reflog Reference Syntax

Git allows referencing a reflog entry with the syntax:

~~~text
<ref>@{<selector>}
~~~

Some common selectors:

| Syntax | Meaning |
|---|---|
| <code>HEAD@{0}</code> | The latest reflog entry of HEAD |
| <code>HEAD@{1}</code> | The entry immediately before the latest entry |
| <code>main@{2}</code> | The third entry from the latest in the reflog of branch main |
| <code>HEAD@{yesterday}</code> | HEAD's position at the timestamp parsed by Git as yesterday |
| <code>main@{2.hours.ago}</code> | Position of branch main approximately two hours ago |

The index in <code>@{n}</code> is the reflog entry order, not the number of parent commits. <code>HEAD~2</code> walks back two parent links in the commit graph; <code>HEAD@{2}</code> selects the third most recent reflog entry. These two ways of referencing have completely different meanings.

Examples:

~~~bash
# View HEAD's position at the previous reflog entry
git show "HEAD@{1}"

# View the state of branch main at a point in time
git show "main@{yesterday}"

# Compare the current commit with HEAD's previous state
git diff "HEAD@{1}" HEAD
~~~

In PowerShell, wrap references containing curly braces in double quotes to prevent the shell from interpreting special characters. In Bash or other shells, also quote time references that contain spaces.

## 6. Recovering After git reset --hard

A common scenario is resetting commits by mistake:

~~~bash
# State before the operation
git log --oneline -5

# Mistaken command: moves the branch back one commit and discards changes from index/working tree
git reset --hard HEAD~1
~~~

If you realize right away that the discarded commit is still needed, do not make additional commits or resets. Check the reflog:

~~~bash
git reflog --date=local
~~~

Suppose the reflog entry shows the commit before the reset was <code>c3d4e5f</code>. Before moving the branch, create a rescue branch pointing to that commit:

~~~bash
git show c3d4e5f
git branch rescue/main-before-reset c3d4e5f
~~~

A rescue branch keeps the commit on an easy-to-find reference. After inspecting the contents, if your goal is to bring the current branch back to that commit and you have confirmed there is no new work to keep, you can use:

~~~bash
git switch main
git reset --hard rescue/main-before-reset
~~~

The hard reset command updates the branch, index, and working tree. Run it only after inspecting the state and confirming there are no changes to preserve; if there is new work, integrate or back it up first.

If you only want to retrieve the content to continue working without moving the branch yet, you can create the rescue branch and then compare or cherry-pick the necessary commits. Always choose the least intrusive approach that fits your goal.

**Important limitation:** reflog records reference movements, not uncommitted content in the working tree. If <code>git reset --hard</code> erased edits that were never committed, reflog cannot restore them on its own. Content objects that were once written to Git, such as via staging, can sometimes still be found with object recovery tools, but there is no guarantee.

## 7. Recovering After a Mistaken Rebase or Amend

Rebase and amend typically create new commits, leaving old hashes off the current branch. If you want to return to the history before the operation, check the reflog:

~~~bash
git reflog --date=local
~~~

Example output:

~~~text
91ab234 HEAD@{0}: rebase (finish): returning to refs/heads/feature/report
91ab234 HEAD@{1}: rebase (pick): docs: update report guide
7cd8910 HEAD@{2}: rebase (start): checkout main
45ef678 HEAD@{3}: commit (amend): feat: generate report
12ab345 HEAD@{4}: commit: feat: generate report
~~~

In this case, commit <code>12ab345</code> is the version before the amend. If the rebase altered history undesirably, you can create a rescue branch from the commit before the rebase:

~~~bash
git branch rescue/report-before-rebase 12ab345
~~~

Inspect that commit with <code>git show</code> and compare it with the current branch before deciding to reset or cherry-pick. With a sequence of rewritten commits, you may need to restore the entire branch tip from before the rebase rather than just taking a single commit.

If the rebase is still running and has not finished, the direct way to cancel is usually:

~~~bash
git rebase --abort
~~~

Reflog is more useful when the operation has already finished or the rebase state is no longer active. There is no need to use reflog as a substitute for abort when Git is still managing an in-progress rebase session.

## 8. Recovering a Deleted Local Branch

If you deleted a local branch and later realize you need the last commit on that branch, search for the hash in the reflog:

~~~bash
git reflog show --all --date=local
~~~

Look for entries with checkout, commit, merge, or rebase messages related to the deleted branch. If you find the tip hash from before deletion, recreate the branch:

~~~bash
git branch feature/recovered <commit-hash>
~~~

Deleting a local branch may simultaneously delete that branch's own reflog. In that case, HEAD's reflog or another reference's reflog may still hold the relevant entry. If not found, you may need to inspect unreachable objects with another tool; the outcome depends on whether the object still exists and has not been cleaned by garbage collection.

For a branch deleted on a remote, the local reflog can only help find the commit if your clone previously recorded that commit or still references it. The reflog on your machine is not the Git server's log.

## 9. Where Is Reflog Stored and What Is Its Scope?

Reflog is local data inside the repository. In the traditional Git layout, reflog files typically reside under:

~~~text
.git/logs/HEAD
.git/logs/refs/heads/main
.git/logs/refs/remotes/origin/main
~~~

With linked worktrees, Git may store some data in the common directory or the separate worktree directory; therefore, you should not edit reflog files manually with an editor. Use Git commands to read and manage them.

Key characteristics to remember:

- Reflog belongs to the local clone or repository you are working in.
- Cloning a new repository does not copy reflogs from the source machine.
- Pushing commits does not send reflogs to the server.
- Fetching updates remote-tracking refs and may write local reflogs for those refs if configuration allows.
- A server may have its own reflog for administration, but you cannot view that log using <code>git reflog</code> in a regular clone.

Therefore, when a teammate needs to recover an unreferenced commit in their clone, the reflog on your machine may not help directly. You can share the commit hash or create a rescue branch and push it per team workflow if the object still exists and is permitted to be shared.

## 10. Default Reflog Retention Limits

Reflog does not keep every entry forever. Git has settings controlling expiration times:

| Setting | Common Default | Applies To |
|---|---:|---|
| <code>gc.reflogExpire</code> | 90 days | Reflog entries whose objects are still considered reachable |
| <code>gc.reflogExpireUnreachable</code> | 30 days | Reflog entries pointing to objects no longer reachable from the ref's current tip |

These two limits are Git defaults and can be changed by repository configuration, user configuration, or per-ref configuration. A ref's reflog entries can have a custom policy if the project configures it accordingly.

For example:

- A commit still in the history of the current branch is generally considered reachable. Related older reflog entries can be kept according to the <code>gc.reflogExpire</code> period.
- A commit dropped from the tip after a reset or rebase and no longer held by any other ref may be unreachable. Related reflog entries typically have a shorter retention period under <code>gc.reflogExpireUnreachable</code>.

These limits apply to **reflog entries**, not a guarantee that the commit object will be deleted on that exact day. After a reflog entry expires, the unreachable object may still persist for some time until garbage collection prunes unreferenced objects. Conversely, you should not rely on that grace period to delay recovery.

### Checking Current Configuration

~~~bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
git config --show-origin --get core.logAllRefUpdates
~~~

If the command prints no value, that setting may not be explicitly set and Git is using the default appropriate for its current version or environment. <code>--show-origin</code> indicates the config file providing the value, helping you determine whether it comes from local, global, or system scope.

### Adjusting Retention Limits

If the project needs to retain reflogs longer, you can configure it at the repository level:

~~~bash
# Example: keep reachable entries for 180 days
git config gc.reflogExpire 180.days

# Example: keep unreachable entries for 60 days
git config gc.reflogExpireUnreachable 60.days
~~~

The commands above modify the local configuration of the current repository. If using <code>--global</code>, the values apply to the user's repositories that inherit that configuration. Align on the policy with your team; keeping reflogs longer requires extra storage and still does not replace backups.

You can use the value <code>never</code> to request no expiration under that policy, but it should not be applied indiscriminately to every repository. Understand the storage impact and maintenance workflow before changing it.

## 11. Git gc and Object Cleanup

Garbage collection is a repository maintenance process. Git uses these operations to optimize data and clean up unreferenced objects once the appropriate expiration conditions are met.

The command:

~~~bash
git gc
~~~

can perform repository maintenance and process expired reflogs according to configured policy. In many cases, Git runs maintenance or auto-gc automatically after certain operations; users do not need to run it manually on a frequent basis.

Do not use aggressive cleanup commands such as <code>git reflog expire --expire=now --all</code> or <code>git gc --prune=now</code> while you still need to recover data. They can destroy the trails or unreachable objects you are relying on to locate commits.

If you need to evaluate before cleaning up, check the repository configuration and state, create appropriate backups, and then follow your maintenance policy. Deleting reflog entries and deleting Git objects are related steps, not a single identical operation.

## 12. When Reflog Cannot Find the Commit

If reflog no longer has the entry you are looking for, it may be because:

- The entry expired under the reflog policy.
- The branch's reflog was deleted along with the branch.
- Reflog was not enabled for the reference being checked.
- You are inspecting the reflog of a different clone.
- The commit was never created, or the changes only existed in the working tree/index.
- The Git object was already cleaned up by garbage collection.

If the object may still remain in the Git database without any ref or reflog pointing to it, a diagnostic tool can help find unreachable objects:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

This command lists objects that are no longer reachable within the check's scope. Results may include commits, trees, or blobs. If you find a suspect commit, inspect it with <code>git show</code> and then create a rescue branch to retain it:

~~~bash
git show <commit-hash>
git branch rescue/found-commit <commit-hash>
~~~

Not every unreachable object is the commit you need. Verify the contents and historical relationships before creating a branch or integrating. If the object has already been pruned, neither reflog nor fsck can reconstruct the lost content; at that point, look for another clone, backup, or artifact that still holds the data.

## 13. Reflog-Based Recovery Workflow

When you discover a mistaken Git operation, follow this sequence:

1. Stop operations that could continue moving branches or overwriting state.
2. Run <code>git status</code> to see the current working tree and index.
3. Inspect <code>git reflog --date=local</code> and <code>git reflog show --all</code>.
4. Identify the entry before the mistaken operation using timestamp, message, and hash.
5. Use <code>git show</code> to verify the commit to recover.
6. Create a rescue branch pointing to that commit before moving any ref.
7. Compare the rescue branch against the current state and choose the right recovery method.
8. Only reset or push after checking changes that need to be preserved and coordinating with relevant people.

General example:

~~~bash
# Check status
git status

# Find positions HEAD previously pointed to
git reflog --date=local

# Inspect the suspect commit
git show <commit-hash>

# Preserve the commit with a rescue branch
git branch rescue/recovered-state <commit-hash>

# Compare with the current branch
git log --oneline --graph --decorate rescue/recovered-state
git diff rescue/recovered-state..HEAD
~~~

Creating a rescue branch is a low-impact step that prevents losing track of the commit during analysis. Only afterward should you decide to reset, merge, or cherry-pick depending on your goal.

## 14. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Reflog is a second commit history | Reflog records local ref movements; git log shows parent-child commit relationships. |
| <code>HEAD@{2}</code> is equivalent to <code>HEAD~2</code> | One is the third most recent reflog entry; the other is the ancestor commit two steps back. |
| Reflog is shared across the whole team | Each clone has its own reflog; push and fetch do not transmit reflogs. |
| Reflog keeps every change made in the editor | Reflog tracks refs, not uncommitted edits in the working tree. |
| Reflog keeps commits forever | Entries have expiration limits; unreachable objects can be cleaned up by garbage collection afterward. |
| After a hard reset you can always recover every file with reflog | Reflog can find commits again, but cannot guarantee recovery of data that was never committed. |
| Deleting a branch immediately destroys its commits | Commits may still remain in other reflogs or the object database until cleaned up. |
| Running gc deletes all old commits | Git cleans up unreferenced objects based on conditions and retention limits, not all valid history. |

## 15. Self-Check Exercises

Practice in a test repository:

1. Create two commits on branch <code>feature/reflog-demo</code>, then run <code>git reflog</code>. Identify the entry corresponding to each commit.
2. Switch to another branch and back. Observe the checkout entries in HEAD's reflog.
3. Run <code>git reset --hard HEAD~1</code> in the test repository. Use reflog to find the hash of the commit just dropped from the tip.
4. Create branch <code>rescue/demo</code> pointing to the found hash. Inspect the commit with <code>git show</code>.
5. Compare <code>git log</code> and <code>git reflog</code> after the reset. Why do they display different information?
6. View the branch's reflog using <code>git reflog show feature/reflog-demo</code> and compare it with HEAD's reflog.
7. Check the values of <code>gc.reflogExpire</code> and <code>gc.reflogExpireUnreachable</code>. Explain why the two default limits differ.
8. Try configuring retention limits in the test repository and read them back with <code>git config --show-origin</code>.
9. Explain why reflog cannot guarantee recovery of a file that was edited but never committed.

When you know how to read reflog, pick the right commit by sequence or timestamp, preserve commits with a rescue branch, and understand retention limits, you gain an essential tool for handling mistaken Git operations. Recover as early as possible, verify contents before moving branches, and maintain proper backups for critical data.

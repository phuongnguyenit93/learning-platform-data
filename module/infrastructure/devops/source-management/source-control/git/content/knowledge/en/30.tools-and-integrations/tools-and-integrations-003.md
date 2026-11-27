# Understanding Stage, Sync, Publish, and Discard Buttons in Tools

Graphical Git tools often place buttons like **Stage**, **Sync**, **Publish Branch**, and **Discard Changes** in prominent locations. They help you work quickly without remembering every Git command, but each button affects a different part of the repository. If confused, you can push the wrong branch to a remote, pull unready changes, or lose edits in progress.

This lesson explains the four operations in terms of actual Git state: staging puts changes into the index to prepare a commit; publishing sends a local branch to a remote for the first time and sets up upstream tracking; syncing exchanges commits between local and remote; discarding removes uncommitted changes. You will learn how to read the UI, inspect state before clicking, understand what happens after the action, and recover when errors occur.

This lesson belongs to the **Tools and Integrations** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; it also builds skills in collaborating through branches, resolving conflicts, tracing changes, and recovering from mistakes while preserving important history. Understanding IDE buttons helps you apply the right Git workflow when working through a graphical interface.

## 1. Where do these four buttons act?

An easy way to remember is to distinguish three data areas and two storage locations:

- **Working tree:** the files you currently have open and are editing.
- **Index / staging area:** the file versions selected to be included in the next commit.
- **Local repository:** commits already created on your machine.
- **Remote repository:** the repository on a server such as GitHub, GitLab, or an internal Git server.

| Button in tool | Primary effect | Typical Git command equivalent |
|---|---|---|
| Stage | Select changes from the working tree into the index | <code>git add</code> |
| Publish Branch | Push a new local branch to the remote and configure upstream | <code>git push -u</code> |
| Sync | Exchange commits between the local branch and upstream; usually pull then push | <code>git pull</code> and <code>git push</code> |
| Discard Changes | Remove uncommitted changes in selected files | Typically involves <code>git restore</code>; untracked files may need a separate action |

Buttons may have different labels or detailed behaviors across VS Code, GitHub Desktop, Visual Studio, and JetBrains IDEs. Read the description or confirmation dialog in your tool before proceeding, especially for discard and sync actions.

## 2. Stage: selecting content for the next commit

When you edit a file, changes appear in the working tree. Git does not automatically include all of those changes in a commit. Staging is the step of selecting what content will be recorded in the next snapshot.

For example, you edit:

~~~text
src/PaymentService.java
README.md
~~~

In VS Code's Source Control view, unstaged files usually appear under **Changes**. When you stage a file, the tool moves it to **Staged Changes**. In GitHub Desktop, the equivalent action is usually checking the box next to the file. In JetBrains IDEs, you can select files or partial changes in the Commit tool window.

Equivalent command:

~~~bash
git add src/PaymentService.java
~~~

This command stages all current changes in the file. Then verify:

~~~bash
git status
git diff --staged
~~~

<code>git status</code> shows which files are staged and which still have unstaged changes. <code>git diff --staged</code> displays the exact content selected for the commit.

### Staging does not create a commit

Staging only updates the index. It does not create a commit, send data to the remote, or alter history. You still need to commit after reviewing the content:

~~~bash
git commit -m "Add payment retry handling"
~~~

In the UI, after staging, you usually see a Commit button or a commit message box. Only commit once you have reviewed the staged diff and the message accurately describes the purpose of the change.

## 3. Staging whole files and staging partially

### Staging a single file

Select the file to include in the commit, or run:

~~~bash
git add src/PaymentService.java
~~~

This is appropriate when the file contains a single change with one unified purpose.

### Staging all changes

The **Stage All Changes** button or equivalent action usually places every change detected by the tool into the index. Common command:

~~~bash
git add -A
~~~

This command updates the index for added, modified, and deleted files within the repository scope. Before using it, inspect the file list because a debug file, log, or local config might be staged accidentally.

### Staging individual hunks or lines

A file sometimes contains multiple independent changes. For example, you both fixed payment logic and added temporary logging. If you stage the entire file, both changes end up in the same commit.

Tools commonly support staging individual hunks or lines. In the terminal, you can run:

~~~bash
git add -p src/PaymentService.java
~~~

Git displays each change group and asks whether to stage or skip it. Some common keys in interactive mode:

| Key | Meaning |
|---|---|
| <code>y</code> | Stage the current hunk |
| <code>n</code> | Skip the current hunk |
| <code>s</code> | Split the hunk into smaller pieces if possible |
| <code>e</code> | Manually edit the patch |
| <code>q</code> | Quit |

In a graphical UI, select the lines or hunk to stage and confirm. Then verify:

~~~bash
git diff
git diff --staged
~~~

The first command shows changes remaining in the working tree; the second shows content that will be committed. A single file can have both staged parts and unstaged parts at the same time.

## 4. Unstage: removing changes from the index

If you staged the wrong file or hunk, you can unstage it to remove the change from the index. Content in the working tree remains untouched.

In VS Code, this action is typically named **Unstage Changes** or shown as a minus icon next to a staged file. In GitHub Desktop, uncheck the file's checkbox. JetBrains IDEs may offer an Unstage action or let you uncheck the file in the Commit tool window.

Command:

~~~bash
git restore --staged src/PaymentService.java
~~~

This command resets the file's index state to the version in HEAD. It does not delete the edits in your working tree.

Verify:

~~~bash
git status
git diff
git diff --staged
~~~

If the file no longer has staged changes but still has unstaged changes, your edits in progress are safe. That is the key distinction between **Unstage** and **Discard**.

## 5. Commit: saving a local snapshot

After staging and reviewing the content, you create a commit. Committing records the snapshot from the index into local history.

In a graphical tool:

1. Open Staged Changes or the list of files selected for commit.
2. Inspect the diff.
3. Enter a concise commit message stating the purpose of the change.
4. Click Commit.

Equivalent commands:

~~~bash
git diff --staged
git commit -m "Fix payment timeout handling"
~~~

A commit only saves to the local repository. The local branch advances to the new commit, while the remote remains unchanged until you push or sync.

If the tool offers **Commit and Push** or **Commit and Sync**, understand that it runs multiple actions in sequence: creating the local commit first, then sending the commit to the remote. Do not assume that merely clicking Commit makes your changes visible to teammates.

## 6. Publish Branch: sharing a local branch for the first time

When you create a new branch on your machine:

~~~bash
git switch -c feature/payment-retry
~~~

This branch exists only in your local repository. The remote does not yet have a corresponding branch. Tools like VS Code may display a **Publish Branch** button; GitHub Desktop typically shows **Publish branch** or an equivalent button.

Publishing usually performs two things:

1. Pushes the local branch's commits to the remote.
2. Sets upstream tracking so the local branch knows which remote branch it tracks.

Equivalent command:

~~~bash
git push -u origin feature/payment-retry
~~~

Where:

- <code>origin</code> is the remote name.
- <code>feature/payment-retry</code> is the local branch to share.
- <code>-u</code> or <code>--set-upstream</code> configures upstream tracking.

After publishing, verify:

~~~bash
git branch -vv
git branch -r
git status -sb
~~~

You will typically see the local branch tracking <code>origin/feature/payment-retry</code>. From then on, push or pull commands on that branch can resolve the upstream automatically if configured appropriately.

### Publish is not creating a Pull Request

Publish Branch sends the branch to the remote. It does not automatically mean a Pull Request or Merge Request has been created. Some platforms prompt you to open a PR after publishing, but that is a separate collaboration step.

After publishing, you can open the repository page and create a Pull Request/Merge Request according to your team's workflow.

### Choose the right remote before publishing

If the repository has multiple remotes, such as <code>origin</code> being your fork and <code>upstream</code> being the source repository, confirm where the branch will be pushed:

~~~bash
git remote -v
git branch -vv
~~~

Do not publish to the source repository if you are only meant to work through a fork or if the team requires creating branches on a different remote.

## 7. How does Push differ from Publish?

Both actions send commits from local to remote, but the context is usually different:

| Action | Case |
|---|---|
| Publish Branch | Local branch has no upstream yet or does not exist on the remote; the tool creates the remote branch and sets up tracking |
| Push | Branch has already been published or already has an upstream; sends new local commits to the corresponding remote branch |

For example, after the branch has been published, you create a new commit:

~~~bash
git add src/PaymentService.java
git commit -m "Add retry limit"
git push
~~~

The <code>git push</code> command sends the new commit to upstream. If the branch has no upstream yet, Git may ask you to specify the remote and branch or configure tracking.

## 8. Sync: synchronizing a local branch with the remote

In some tools, the **Sync Changes** button combines fetching/pulling new commits from the remote and pushing local commits to the remote. In VS Code, Sync Changes typically performs a pull followed by a push for the current branch. GitHub Desktop may expose separate Fetch origin, Pull origin, and Push origin buttons.

Sync usually involves two directions:

- **Pull:** retrieve and integrate new commits from upstream into the local branch.
- **Push:** send local commits not yet on upstream to the remote.

Overview diagram:

~~~text
Remote branch (origin/feature)
             |
             | pull / fetch + integrate
             v
        Local branch
             |
             | push
             v
Remote branch (origin/feature)
~~~

Before syncing, check the branch and status:

~~~bash
git branch --show-current
git status -sb
git branch -vv
~~~

You need to know which branch you are on, whether you have uncommitted changes, and which branch is the upstream. If the tool displays ahead/behind commit counts, read that information before clicking.

### Sync does not mean stage or commit

Sync exchanges commits between local and remote. It does not automatically add unstaged changes to the index or commit them. Many tools require a clean working tree before pulling or warn that you need to commit or stash changes.

If you have files edited partway through, decide explicitly:

- Commit the changes if they are ready.
- Partially stage and commit that portion if the changes are independent.
- Stash the changes temporarily if you need to pull first.

Example:

~~~bash
git stash push -m "WIP before sync"
git pull
git stash pop
~~~

Stashes can produce conflicts when reapplied. Check status after each step and do not drop the stash until you confirm your changes were restored safely.

## 9. Sync may use merge or rebase

Pulling involves fetching new commits and integrating them into the current branch. How they are integrated depends on configuration and options:

- Merge creates a merge commit when two histories must be combined.
- Rebase replays local commits on top of new commits from upstream.
- Fast-forward simply moves the branch pointer if local history can advance directly to the new commit.

Configurations that commonly affect this:

~~~bash
git config --get pull.rebase
git config --get pull.ff
~~~

You can also choose explicitly for a single run:

~~~bash
git pull --rebase
~~~

or:

~~~bash
git pull --no-rebase
~~~

A graphical UI may inherit the current Git configuration or provide its own setting. When a team has a merge/rebase convention, stay consistent with it. If unsure, ask the repository maintainer before changing global pull configuration.

## 10. When Sync reports a conflict

If local and remote modified the same area, integration can trigger a conflict. Tools usually list the conflicted files and open a merge editor.

Resolution workflow:

1. Read the conflicted file names.
2. Open the merge editor or conflict resolution tool.
3. Compare the sides and produce the resulting content.
4. Save the file.
5. Stage the resolved file.
6. Continue the merge or rebase as instructed by Git.

Check status:

~~~bash
git status
~~~

If merging:

~~~bash
git add <resolved-file>
git merge --continue
~~~

If rebasing:

~~~bash
git add <resolved-file>
git rebase --continue
~~~

Do not click Sync repeatedly while a previous operation is still in progress. Complete or abort the current integration operation first.

## 11. Discard Changes: removing uncommitted changes

Discard is a destructive operation for edits in progress. When you choose **Discard Changes**, the tool usually tells Git to drop changes in the selected file and revert it to the state recorded in Git. Some tools also support discarding untracked files or deleting new untracked files.

Before discarding, review the diff and ask yourself whether any content needs to be kept. If unsure, make a copy, stash, or create a temporary commit first.

For unstaged changes, the equivalent command is:

~~~bash
git restore -- src/PaymentService.java
~~~

This command restores the file in the working tree to match the current index. Unstaged changes in the file will be removed.

### Discarding staged changes

If the file is already staged, remove it from the index first:

~~~bash
git restore --staged -- src/PaymentService.java
~~~

This command preserves working tree content. If you also want to remove the edits in the working tree:

~~~bash
git restore --worktree -- src/PaymentService.java
~~~

The two commands separate the two steps: unstaging and restoring the working tree. If you want to reset both the index and working tree for the file to HEAD in one step:

~~~bash
git restore --source=HEAD --staged --worktree -- src/PaymentService.java
~~~

Specify the exact path. Before running it, you can inspect:

~~~bash
git status
git diff
git diff --staged
~~~

### Discarding new untracked files

Untracked files are not in the index and have no version in HEAD for <code>git restore</code> to restore. Some UIs provide a separate delete action for untracked files.

In the terminal, preview what would be deleted first:

~~~bash
git clean -n
~~~

Only delete untracked files when the list matches your intent:

~~~bash
git clean -f -- path/to/untracked-file
~~~

For untracked directories, an appropriate recursive flag such as <code>-d</code> is needed. The clean command can delete data that cannot be recovered from Git; always review dry-run output first and never run it with a broad scope without understanding what it will remove.

## 12. Discard is not Undo commit

Discard applies to uncommitted changes in the working tree or index. If changes have already been committed, discard is not the way to remove a commit from history.

To create a new commit that reverses an already shared commit, typically use:

~~~bash
git revert <commit>
~~~

Revert preserves history and creates a new commit undoing the changes. If a commit has not been shared and you need to edit local history, tools like reset or interactive rebase exist, but you must consider their impact on child commits and collaborators.

Do not confuse them:

| Goal | Appropriate action |
|---|---|
| Drop unstaged changes | Discard / <code>git restore</code> |
| Remove staged status while keeping edits | Unstage / <code>git restore --staged</code> |
| Drop both staged and unstaged changes of a file | Restore both index and working tree from HEAD |
| Delete untracked files | Discard untracked in GUI or <code>git clean</code> after dry-run |
| Reverse a shared commit | <code>git revert</code> |
| Move local branch to another commit | <code>git reset</code> when you clearly understand the impact |

## 13. Reading status in the UI before acting

Group names or colors may vary across tools, but you usually need to identify:

- **Changes:** files modified but not staged.
- **Staged Changes:** files or hunks already in the index.
- **Untracked:** new files not yet tracked by Git.
- **Outgoing / Ahead:** local has commits not yet pushed.
- **Incoming / Behind:** remote has commits not yet integrated locally.
- **Conflicts:** files currently in an unmerged state.

Ahead/behind counts depend on the most recent fetch. If you have not fetched, the tool may not yet know the remote has new commits. Some UIs fetch when opening the sync panel or when you click a check-for-updates button.

To verify via terminal:

~~~bash
git status -sb
git branch -vv
git diff
git diff --staged
git log --oneline --decorate --graph --all -12
~~~

These commands help you verify actual state instead of relying solely on icons or colors in the IDE.

## 14. Example UI workflow

Suppose you need to fix a timeout bug in the payment service and share the branch with your team.

**Step 1: create a working branch**

In the UI, select the current branch and create a new branch, such as <code>fix/payment-timeout</code>. Equivalent command:

~~~bash
git switch -c fix/payment-timeout
~~~

**Step 2: edit and stage**

Modify the service file and add tests. In Source Control, inspect each diff and stage the relevant files. If a file contains multiple independent changes, stage individual hunks.

**Step 3: commit**

Enter a message like <code>Fix payment timeout handling</code> and commit. Confirm the commit appears in local history.

**Step 4: publish the branch**

Click Publish Branch or run:

~~~bash
git push -u origin fix/payment-timeout
~~~

**Step 5: continue working and sync**

When new commits arrive from teammates or the remote, fetch/pull according to your team's workflow. Resolve any conflicts. Once the local branch has integrated history properly, push new commits to the remote.

**Step 6: clean up unnecessary changes**

If there are uncommitted debug logs, inspect the diff and discard only the intended file or hunk. If you still need to keep them for later, stash or save a copy instead of discarding.

## 15. The same action can carry different labels

Tools do not share a single mandatory set of labels. The table below describes common names, not a guarantee for every version's UI:

| Intent | VS Code | GitHub Desktop | JetBrains IDEs |
|---|---|---|---|
| Stage file | Stage Changes / plus icon | File checkbox | Select file in Commit tool window |
| Unstage file | Unstage Changes / minus icon | Uncheck checkbox | Uncheck or Unstage |
| Stage partially | Stage Selected Ranges | Select lines/hunk if version supports it | Select parts in diff |
| Publish branch | Publish Branch | Publish branch | Push new branch, configure upstream |
| Sync | Sync Changes | Fetch/Pull/Push origin | Update Project and Push, depending on config |
| Discard | Discard Changes | Discard Changes | Rollback or Revert local changes |

If unsure what a button does, open its context menu or check the tooltip/help for your exact tool version. In particular, **Rollback**, **Revert**, **Reset**, and **Discard** can carry different meanings depending on the IDE.

## 16. Common errors and how to handle them

| Symptom | Possible cause | How to handle |
|---|---|---|
| Stage button not visible | File is already staged, untracked, or tool is showing another group | Check Changes, Staged Changes, and file status |
| Commit lacks expected content | File was not staged or wrong hunk was staged | Check <code>git diff --staged</code> before committing |
| Publish Branch rejected | No push permission or remote branch already exists with different history | Check remote, permissions, and branch name; do not force push blindly |
| Publish not shown after creating branch | Tool already configured upstream or branch was already published | Check <code>git branch -vv</code> |
| Sync asks to commit/stash | Working tree has uncommitted changes or index is not clean | Check diff, commit or stash what you need to keep |
| Sync reports non-fast-forward | Remote has new commits or history diverged | Fetch, inspect history, and integrate with merge/rebase per team convention |
| Sync causes conflicts | Both sides edited the same region or file | Open merge editor, resolve, stage, and continue the right operation |
| Discard lost content | Confirmed discarding unsaved changes | Check Local History, editor history, stash, or backups if supported by tool; recovery is not guaranteed |
| New file does not appear in Changes | File is ignored or located outside the repository | Check <code>git status --ignored</code> and ignore rules |
| Pushed, but teammates do not see the branch | Pushed to a different remote or wrong permissions/target branch | Check <code>git remote -v</code> and <code>git branch -vv</code> |

## 17. Pre-click checklist

Before **Stage**:

- Read the diff and confirm the right file.
- Verify you are not accidentally staging secrets, logs, build files, or unrelated changes.
- When needed, stage individual hunks instead of the entire file.

Before **Publish Branch**:

- Confirm the current branch.
- Confirm the target remote and push permissions.
- Check that the branch name does not collide with another branch serving a different purpose.
- Review which commits will be sent to the remote.

Before **Sync**:

- Confirm the branch and upstream.
- Check for uncommitted changes.
- Check ahead/behind commit counts and fetch if the info is stale.
- Know whether your team uses merge or rebase.
- Be ready to resolve conflicts if histories have diverged.

Before **Discard**:

- Inspect the diff of the file or hunk.
- Confirm the content does not need to be kept.
- If still unsure, stash or make a copy first.
- For untracked files, verify the exact path that will be deleted.

## 18. Self-check exercises

Practice in a test repository:

1. Edit two files, stage one file, and use <code>git status</code> to observe the difference.
2. Stage a single hunk in a file that has two independent changes.
3. Unstage the file and verify the working tree content remains.
4. Commit the staged changes and verify the commit contains only the intended content.
5. Create a new branch, publish the branch, and inspect upstream with <code>git branch -vv</code>.
6. Create a local commit and push; distinguish Publish Branch from Push on subsequent pushes.
7. Create a commit on the remote from another clone, then sync and observe how pull integrates the commit.
8. Create an intentional conflict in the test repository, resolve it with a merge editor, and continue the merge or rebase.
9. Create an untracked file, observe how the tool displays it, and run a dry-run before deleting it with Git.
10. Explain why discarding uncommitted changes differs from reverting a shared commit.

Stage, publish, sync, and discard are small UI actions, yet they represent distinct Git state transitions. When you check the index, branch, upstream, and diff before clicking, you can use your IDE faster while keeping full control over commit contents, data sent to remotes, and discarded changes.
# Keeping Experimental Work While in Detached HEAD

Detached HEAD is the state where Git checks out a commit directly instead of being on a branch. You can still read code, run tests, edit files, and create commits. The key thing to watch out for is that when you create commits in this state, HEAD moves to the new commit, yet no regular branch updates automatically to keep the results. If you switch to another branch without creating a ref to save your experimental commits, it may be difficult to find those results afterward.

In the **Branches and HEAD** chapter of the **SOURCE_CONTROL_GIT** module, this lesson shows how to recognize detached HEAD and preserve your work before leaving that state. You will learn how to create a branch right at the experimental commit, save uncommitted changes using stash, locate left-behind commits using the reflog, and choose the right workflow to continue, share, or discard an experiment.

After this lesson, you will be able to:

- Explain how HEAD behaves in attached and detached states.
- Recognize detached HEAD using git status, git branch, and git symbolic-ref.
- Create commits while detached and understand why the current branch does not move automatically.
- Create a branch at the experimental commit to retain all results.
- Preserve uncommitted changes using a branch or stash.
- Recover commits after leaving detached HEAD using the reflog.
- Distinguish commits still held by a ref from commits only remaining in the reflog.
- Choose how to continue an experiment, share results, or return safely to a working branch.

## 1. Where Does HEAD Normally Point?

HEAD is a reference indicating the current checkout position. In the normal state, HEAD is a symbolic ref pointing to the active working branch.

For example, when you are on the main branch:

~~~text
HEAD
  |
  v
refs/heads/main
  |
  v
commit C
~~~

Logically, the contents of HEAD are equivalent to:

~~~text
ref: refs/heads/main
~~~

When you create a new commit on main, Git updates the ref refs/heads/main to point to the new commit. HEAD still points to the main branch; because the branch moves, the current commit position changes as well.

Check which branch HEAD is attached to:

~~~bash
git branch --show-current
git symbolic-ref --short HEAD
~~~

If you are on main, the commands normally return main. The symbolic-ref command reads the symbolic ref; it fails if HEAD is detached.

## 2. What Is Detached HEAD?

Detached HEAD occurs when HEAD points directly to a commit instead of pointing to a branch. This state typically occurs when you check out:

- A specific commit hash.
- A tag such as v2.0.0.
- A remote-tracking branch such as origin/main.
- A revision expression such as HEAD~2.

Example:

~~~bash
git switch --detach v2.0.0
~~~

HEAD now points directly to the commit that tag v2.0.0 resolves to:

~~~text
HEAD
  |
  v
commit C  <--- tag v2.0.0

refs/heads/main ---> commit D
~~~

The main branch is not moved. The v2.0.0 tag does not change either. You are viewing the snapshot at commit C without standing on a local branch.

Detached HEAD is a valid state, not an error or a corrupted repository. It is useful when reviewing a release, running tests at a specific commit, comparing versions, or experimenting independently.

## 3. Recognizing Detached HEAD

Run:

~~~bash
git status
git branch --show-current
git rev-parse --short HEAD
git symbolic-ref -q HEAD
~~~

Common indicators:

- git status displays a message such as HEAD detached at v2.0.0.
- git branch --show-current prints no branch name.
- git rev-parse HEAD still prints the object ID of the current commit.
- git symbolic-ref -q HEAD returns a non-zero exit code because HEAD is not a symbolic ref.

To view branches and HEAD's position:

~~~bash
git branch --all --verbose
git log -1 --oneline --decorate
~~~

In the log output, HEAD may be shown next to a tag or commit hash instead of a local branch name.

Do not rely solely on which branch git branch marks with an asterisk to conclude you are on that branch. In detached state, the asterisk may not appear next to any local branch.

## 4. You Can Still Edit Files and Create Commits While Detached

Detached HEAD does not lock the repository in read-only mode. You can:

- Edit files in the working tree.
- Stage changes with git add.
- Create commits with git commit.
- Create tags or run other inspection commands.

Example:

~~~bash
git switch --detach v2.0.0
git status --short

# Edit source and tests
git add src/parser.js test/parser.test.js
git commit -m "experiment: improve parser for legacy input"
~~~

After committing, HEAD moves to the new commit, yet no local branch updates automatically:

~~~text
Before commit:

tag v2.0.0 ---> C <--- HEAD
main --------> D

After commit:

tag v2.0.0 ---> C
                 |
                 v
                 E <--- HEAD
main ------------> D
~~~

Commit E exists and has C as its parent. You can still view it with git log or git show while HEAD is there. However, when switching to main, no named branch holds E. If no ref points to E or a child commit of it, the commit can become unreachable after HEAD leaves.

## 5. The Safest Way: Create a Branch to Keep the Results

If the experiment is valuable and you want to continue developing, create a branch at the current position before leaving detached HEAD.

### Creating a Branch Right at the Checked-Out Commit

~~~bash
git switch -c experiment/parser-v2
~~~

This command creates a new branch starting from the current commit and switches HEAD to that branch. If you created one or more commits while detached, the new branch retains the entire chain of commits up to the current HEAD.

After the command:

~~~text
HEAD
  |
  v
refs/heads/experiment/parser-v2
  |
  v
commit E
  |
  v
commit C
~~~

From here, subsequent commits move the experiment/parser-v2 branch normally.

Verify:

~~~bash
git status -sb
git branch --show-current
git log --oneline --decorate -5
~~~

### Creating a Branch First and Switching to It Afterward

The following two commands achieve the equivalent effect:

~~~bash
git branch experiment/parser-v2
git switch experiment/parser-v2
~~~

The git branch command creates a ref at the current commit without moving HEAD. The git switch command then moves HEAD to the newly created branch.

If you only run git branch and stay in detached HEAD, HEAD still points directly to the commit. The new branch already holds the commit, but to continue working on the branch you need to switch to it.

### Creating a Branch from a Specific Commit

If you already have the OID of the commit you need to keep:

~~~bash
git switch -c rescue/parser-experiment <commit-oid>
~~~

Or:

~~~bash
git branch rescue/parser-experiment <commit-oid>
git switch rescue/parser-experiment
~~~

Verify the OID before creating the branch:

~~~bash
git show --stat --oneline <commit-oid>
~~~

Do not guess a commit from an overly short hash prefix; use the full OID or verify that the prefix resolves uniquely.

## 6. Creating a Branch Before Starting an Experiment

If you know in advance that you will edit files and may commit, the cleanest approach is to create a branch right after checking out the commit/tag:

~~~bash
git status -sb
git switch --detach v2.0.0
git switch -c experiment/parser-v2
~~~

Start from a clean working tree or save existing changes separately before checking out a tag. If the repository has uncommitted edits, switching to a tag may be refused by Git or carry those changes along if they do not overwrite files.

Then edit files, stage, and commit:

~~~bash
git add -- src/parser.js test/parser.test.js
git commit -m "experiment: improve parser for legacy input"
~~~

At that point HEAD is already attached to experiment/parser-v2. You do not have to remember to create a branch after finishing the experiment.

If your goal is only a quick inspection and you do not intend to save commits, you can stay in detached HEAD during the review. However, before creating valuable commits, create a branch or record how you plan to preserve them.

## 7. Preserving Uncommitted Changes

Not every experiment has commits yet. You may be in detached HEAD and have only edited files, staged part of them, or created new files.

Check status:

~~~bash
git status --short
git diff
git diff --cached
~~~

If the changes belong to the experiment, you can create a branch right at the current HEAD:

~~~bash
git switch -c experiment/parser-v2
~~~

Changes in the working tree and index are normally preserved when creating a branch from the exact current commit, because the new branch requires no change to the checked-out snapshot. Recheck status after switching.

If you need to move to a branch with different contents, Git may refuse the switch if the operation would overwrite local changes. Do not force a branch switch before saving the work you need to keep.

### Using Stash When You Need to Switch Away Temporarily

If you want to temporarily set aside uncommitted changes:

~~~bash
git stash push -u -m "detached-head parser experiment"
~~~

- git stash push saves tracked changes.
- -u (or --include-untracked) also includes untracked files in the stash.
- Ignored files are not included by default.

If you genuinely need to save ignored files as well, Git has the -a option, but inspect carefully because it can put build outputs or large files into the stash:

~~~bash
git stash push -a -m "detached-head experiment including ignored files"
~~~

After stashing, check:

~~~bash
git stash list
git status --short
~~~

You can switch to another branch and reapply it:

~~~bash
git stash apply 'stash@{0}'
~~~

Prefer apply when you are not yet sure of the outcome because the stash is preserved. Only after inspecting the files and confirming the work is fully restored should you drop the stash if it is no longer needed:

~~~bash
git stash drop 'stash@{0}'
~~~

git stash pop both applies and attempts to drop the stash if application succeeds. If there is a conflict, the stash is normally kept for you to resolve. Whether using apply or pop, inspect status and contents after applying.

If you want to create a branch directly from the base commit where the stash was created and apply the changes onto that branch, you can use:

~~~bash
git stash branch experiment/parser-stashed 'stash@{0}'
~~~

This command creates and switches to a branch from the stash's base commit, then applies the stash contents. When application succeeds, the stash entry is dropped. This is useful if the stash was created in detached HEAD and you want to continue experimenting from the exact original commit; still check status and diff after the command.

Stash fits uncommitted changes and temporary context switches. If you have already created experimental commits, creating a branch to keep the commits is clearer and more durable.

## 8. Leaving Detached HEAD Without Losing Results

Before switching back to the main branch, check whether any experimental commits need to be kept.

~~~bash
git status --short
git log --oneline --decorate -5
git rev-parse HEAD
~~~

If you created commits you need to keep, create a branch:

~~~bash
git switch -c experiment/parser-v2
~~~

Only then switch to another branch:

~~~bash
git switch main
~~~

If you have not created commits yet but have changes worth keeping, you can create a branch right at HEAD and continue editing, or stash before switching branches.

If the experiment does not need to be kept, confirm there are no uncommitted changes and no commits to preserve before leaving detached HEAD. Do not mistake switching branches for an immediate commit deletion; the commit may remain in the reflog for a while, but you should not rely on it as primary storage.

## 9. Remembering an Experimental Commit After Already Leaving Detached HEAD

If you already ran git switch main and then remembered a commit created in detached HEAD, locate the commit via the reflog.

### Step 1: View HEAD History

~~~bash
git reflog --date=local -n 20
~~~

Example:

~~~text
d7a8b9c HEAD@{0}: checkout: moving from e5f6a7b to main
e5f6a7b HEAD@{1}: commit: experiment: improve parser
c3d4e5f HEAD@{2}: checkout: moving from main to v2.0.0
...
~~~

Find the line for the experimental commit and note its OID. Actual output will differ depending on operation history.

### Step 2: Inspect the Located Commit

~~~bash
git show --stat --oneline <commit-oid>
git log --oneline --decorate -5 <commit-oid>
~~~

Confirm this is truly the experimental result, not another commit with a similar message.

### Step 3: Create a Rescue Branch

~~~bash
git branch rescue/parser-experiment <commit-oid>
~~~

The rescue/parser-experiment branch keeps the commit and its ancestor commits from being considered unreferenced.

### Step 4: Switch to the Rescue Branch

~~~bash
git switch rescue/parser-experiment
git status -sb
git log --oneline --decorate -5
~~~

Now you can continue working, compare against main, or open a pull request.

Do not rely mechanically on HEAD@{1}. After a few checkout or reset operations, reflog indices shift. Read the message and OID of each entry and verify with git show.

## 10. How Long Does the Reflog Retain Commits?

The reflog is a local history of ref changes. It typically helps locate commits after amend, reset, checkout, or leaving detached HEAD. However:

- The reflog is not pushed to remotes.
- Each repository or worktree has its own reflog according to the storage layout.
- Reflog entries can expire according to configuration.
- Garbage collection can prune objects no longer held by any ref once expiration conditions are met.

Check expiration configuration:

~~~bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
~~~

Default values depend on Git version and configuration; do not treat the reflog as permanent storage.

Once you locate a commit you need to keep, create an appropriate branch or tag. A new ref is the clear way to preserve results in the repository.

## 11. Sharing Experimental Results

After creating a branch to hold the results, you can push the branch to the remote:

~~~bash
git push -u origin experiment/parser-v2
~~~

This command creates the branch on the remote and sets the upstream for the local branch if the push succeeds.

Before pushing, check:

~~~bash
git status -sb
git log --oneline --decorate --graph -10
git remote -v
~~~

If the experiment started from an old tag, the new branch still contains history starting from that tag's commit. This helps reviewers clearly understand which version the experiment is based on.

Do not push a detached HEAD directly by relying on temporary state. Create a branch with a descriptive name and push that branch. A branch name makes it easy for others to reference, review, and continue the work.

## 12. Distinguishing Checking Out a Tag, Remote Branch, and Local Branch

The following three operations can lead to different states:

~~~bash
git switch main
git switch --detach v2.0.0
git switch --detach origin/main
~~~

- git switch main switches to the local branch main; HEAD is attached.
- git switch --detach v2.0.0 checks out the commit that the tag points to; HEAD is detached.
- git switch --detach origin/main checks out the commit of the remote-tracking branch; HEAD is detached.

If you want to continue developing from a remote-tracking branch, create a local branch tracking it:

~~~bash
git switch -c feature/api --track origin/feature/api
~~~

If you want to experiment independently at a tag, detached HEAD is an appropriate choice. When results need to be kept, create a branch from the current commit.

## 13. Detached HEAD in a Linked Worktree

A linked worktree can be created directly at a commit:

~~~bash
git worktree add --detach ../repo-review v2.0.0
~~~

The new worktree starts in detached HEAD. This approach is useful for reviewing or testing an old version in a separate directory without changing the active working branch in the main worktree.

If you need to keep experimental results in that worktree, create a branch right inside the worktree:

~~~bash
git -C ../repo-review switch -c experiment/review-v2
~~~

The new branch holds the commit at the experimental point. Git normally does not allow the same branch to be checked out simultaneously in two linked worktrees; if a branch is already in use elsewhere, choose a different branch name or handle the worktree holding that branch according to your workflow.

## 14. Complete Workflow: Testing an Old Release

Suppose you need to investigate a bug that only appears on tag v2.4.0 and want to keep the fix if the experiment succeeds.

### Step 1: Confirm the Repository Is Clean

~~~bash
git status -sb
~~~

If there are changes you need to keep, commit, create a branch, or stash before checking out the tag.

### Step 2: Check Out the Tag in Detached HEAD

~~~bash
git switch --detach v2.4.0
git status
git log -1 --oneline --decorate
~~~

Confirm you are at the exact release commit.

### Step 3: Create an Experimental Branch Immediately

~~~bash
git switch -c experiment/fix-v2.4
~~~

From here, HEAD is attached to the experiment/fix-v2.4 branch.

### Step 4: Edit and Commit

~~~bash
git add -- src/legacy-parser.js test/legacy-parser.test.js
git diff --cached
git commit -m "fix(parser): handle legacy escape sequence"
~~~

### Step 5: Verify the Results

~~~bash
git status -sb
git log --oneline --decorate --graph -5
git show --stat --oneline HEAD
~~~

### Step 6: Share if Needed

~~~bash
git push -u origin experiment/fix-v2.4
~~~

The experimental branch is now retained by both local and remote refs. You can open a pull request or continue reviewing without depending on the reflog.

## 15. Common Misconceptions

### Does Detached HEAD Mean Git Lost My Branch?

No. Branches still exist and still point to their commits. Only HEAD is not currently attached to a branch.

### Can You Create Commits While in Detached HEAD?

Yes. New commits are created normally and HEAD points directly to the new commit. Local branches do not move automatically.

### Is Remembering the Commit Hash Enough?

A hash helps find a commit while the object still exists, but it is not a ref that retains the commit long-term. Create a branch or tag to preserve the results.

### Does Creating a Branch After Detached Commits Keep the Whole Chain of Commits?

Yes. If you create a branch at the current HEAD, the branch retains that commit and all of its ancestors. For example, git switch -c experiment/save-results.

### Does Stash Save Untracked Files?

Not by default. Use git stash push -u to include untracked files. Ignored files require the -a option and should be considered carefully.

### Does Leaving Detached HEAD Delete Commits Immediately?

No. Commits may remain in the reflog and object database for a while. However, without a ref holding them, those commits risk being pruned later.

### Is the Reflog Shared via Push?

No. The reflog is local data. To share commits, create a branch/tag and push that ref.

## 16. Self-Check

You check out tag v3.1.0 with:

~~~bash
git switch --detach v3.1.0
~~~

Then you edit code and create two experimental commits E1 and E2. You run git switch main to return to your main work, then realize you have not saved the experimental results with a branch.

Answer:

1. Why is HEAD called detached after checking out the tag?
2. Are the two commits E1 and E2 deleted immediately when switching to main?
3. Which command locates the OID of the experimental commit?
4. Which command creates a rescue branch pointing to E2?
5. If you are still in detached HEAD at E2, which command creates a branch and moves HEAD at the same time?
6. If you have uncommitted changes and untracked files, which stash command saves both?
7. Why is a branch better than the reflog for keeping results long-term and sharing with teammates?

**Hint:** HEAD points directly to the tag's commit instead of a branch. Detached commits are not deleted immediately but can become unreachable after switching away. Use git reflog to find the OID of E2, inspect with git show, then run git branch rescue/experiment <OID> or git switch -c rescue/experiment while still at E2. Use git stash push -u to save tracked and untracked changes. A branch is a named ref stored in the repository and pushable to a remote; the reflog is only a time-limited local history.

## Conclusion

Detached HEAD is the state where HEAD points directly to a commit instead of a branch. You can still edit files and create commits, but local branches do not automatically retain those new commits. When experimental results are valuable, create a branch at the current HEAD using git switch -c before leaving. If you only have uncommitted changes, create a branch to continue or stash with -u when you also need to store untracked files. If you have already switched away, use the reflog to locate the commit, verify the OID, and create a rescue branch. The reflog helps with short-term recovery; a new branch or tag is the clear way to preserve and share results long-term.

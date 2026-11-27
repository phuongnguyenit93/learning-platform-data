# Undoing a Merge Commit with revert -m and Implications for Future Merges

## Why Does Undoing a Merge Commit Require Selecting a Mainline?

In Git, a merge commit records the combination of histories from at least two branches. When a merge introduces unwanted changes into the main branch, you may need to undo those changes while still preserving the commit history shared with the team.

For a regular commit, the git revert command creates a new commit whose content reverses the changes of the specified commit. For a merge commit, Git needs to know which parent branch you want to treat as the main line of development in order to compute the changes to reverse. Therefore, the command requires the -m option:

~~~bash
git revert -m <parent-number> <merge-commit>
~~~

The -m option stands for mainline. The value that follows is the ordinal number of the selected parent, starting at 1. This is the parent index in the merge commit, not a commit hash, branch name, or commit message.

In most situations where a team merges a feature branch into main, parent 1 is the main commit before the merge, and parent 2 is the tip of the merged feature branch. In that case:

~~~bash
git revert -m 1 <merge-commit>
~~~

This command creates a new commit reversing the changes that the merge commit brought in relative to parent 1. The merge history remains in the commit graph. This directly affects any future attempt to merge that same branch again.

## What Does a Merge Commit Store?

A regular Git commit has one parent, pointing to the commit preceding it. A merge commit has two or more parents. In a typical two-branch merge, it usually has two parents:

- Parent 1: the HEAD commit of the branch you were on when performing the merge.
- Parent 2: the tip commit of the branch being merged in.

For example, you are on main and run git merge --no-ff feature/payment. The graph might look like this:

~~~text
          C1---C2  feature/payment
         /       \
A---B---M          main
     parent 1  parent 2
~~~

M is the merge commit. Parent 1 is B, parent 2 is C2. This order reflects the order parents were recorded in the commit, usually corresponding to the current branch first and the merged-in branch second.

If fast-forward is used, Git only moves the branch pointer to the newer commit and does not create a merge commit. In that case, there is no merge commit to pass to git revert -m. If merged via squash merge, the result is usually a single commit with one parent, so undo that commit with regular git revert without -m.

A merge can have more than two parents, such as an octopus merge. In that case, you must clearly identify which parent is the mainline to keep before running revert.

## Identifying the Right Merge Commit and Parent Order

Do not pick a commit based solely on the nearest position in git log. Inspect the graph and commit metadata.

List history as a graph:

~~~bash
git log --oneline --graph --decorate --all
~~~

Filter merge commits:

~~~bash
git log --oneline --merges
~~~

View details of a commit:

~~~bash
git show --no-patch --pretty=raw <merge-commit>
~~~

The output for a merge commit typically includes parent lines like this:

~~~text
commit 7f8a9b0
tree 3d4e5f6
parent 111aaaa
parent 222bbbb
author ...
committer ...
~~~

The first parent line is parent 1, and the second line is parent 2. You can retrieve the commit together with its parent list using:

~~~bash
git rev-list --parents -n 1 <merge-commit>
~~~

Example output:

~~~text
7f8a9b0 111aaaa 222bbbb
~~~

In this example, 111aaaa is parent 1 and 222bbbb is parent 2. Cross-reference the parents with actual branches and commits:

~~~bash
git show --no-patch --oneline 111aaaa
git show --no-patch --oneline 222bbbb
~~~

Also view stats and merge content:

~~~bash
git show --stat --summary <merge-commit>
git diff <merge-commit>^1 <merge-commit>
git diff <merge-commit>^2 <merge-commit>
~~~

The expressions ^1 and ^2 reference parent 1 and parent 2, respectively. Comparing the merge commit against each parent helps clarify how the merge outcome differs from each side.

If you have not yet determined which parent is the main branch to preserve, stop and inspect the history first. Choosing the wrong mainline can reverse the changes you wanted to keep.

## What Do -m 1 and -m 2 Mean?

Suppose merge commit M has two parents:

~~~text
P1 ---\
       M
P2 ---/
~~~

- git revert -m 1 M selects P1 as the mainline. Git computes the changes in M relative to P1 and reverses them on top of the current HEAD.
- git revert -m 2 M selects P2 as the mainline. Git computes the changes in M relative to P2 and reverses them on top of the current HEAD.

In a workflow merging feature into main, you usually want to keep the main development line and reverse what was brought in from feature. When the merge was created from main, parent 1 is usually main before the merge, so -m 1 is usually the choice to use.

Do not assume -m 1 is always right. If the merge was created while checked out on the other branch, the parent order can be reversed. Check the parents before choosing.

The -m option does not mean choosing a commit message, choosing the number of commits to revert, or selecting a branch by name. It specifies which parent is treated as the mainline so Git can calculate the reversing patch.

## Undoing a Merge Commit with git revert -m

Suppose the main branch received merge commit 7f8a9b0 from feature/payment. After deployment, the team discovers changes in that merge cause bugs and needs to undo the merged portion.

Before reverting, check the repository state:

~~~bash
git status
git branch --show-current
~~~

You should start from the branch that needs to receive the undo commit, usually main or the release branch containing that merge commit. If the working tree has uncommitted changes, handle them first according to your team's workflow.

Identify the parents of the merge commit:

~~~bash
git rev-list --parents -n 1 7f8a9b0
~~~

Suppose the output confirms parent 1 is main before the merge. Run:

~~~bash
git revert -m 1 7f8a9b0
~~~

Git applies the inverse of the merge commit onto the current HEAD and creates a new commit. Git may open your editor to confirm the message, for example:

~~~text
Revert "Merge branch 'feature/payment' into main"

This reverts commit 7f8a9b0, reversing
changes made to 7f8a9b0.
~~~

The actual message generated by Git may vary depending on version and configuration. Once complete, inspect the new commit and repository state:

~~~bash
git status
git log --oneline --graph --decorate -n 12
git show --stat --oneline HEAD
~~~

The revert commit is a new commit with one parent, which is the HEAD before the revert. The original merge commit still exists in history and remains an ancestor of the branch.

### Using --no-edit or --no-commit

If you want to use the default message without opening the editor:

~~~bash
git revert --no-edit -m 1 7f8a9b0
~~~

If you want to inspect the reversed result before creating the commit:

~~~bash
git revert --no-commit -m 1 7f8a9b0
~~~

With --no-commit, Git applies the reversed changes to the working tree and staging area without automatically creating a commit. Review them:

~~~bash
git status
git diff
git diff --cached
git diff --cached --check
~~~

After confirming the content, run necessary tests and create the commit according to your team's workflow:

~~~bash
git commit -m "Revert payment feature merge"
~~~

Do not run git revert --no-commit just to experiment if you do not yet understand that the index and working tree will be modified. This modifies your local repository; if the result is wrong, clean up according to the actual state before continuing.

## Reverting a Merge Can Produce Conflicts

If the main branch already has subsequent changes building on the merge commit's content, the reversing patch might not apply automatically. Git will stop and report conflicts.

Start with:

~~~bash
git status
git diff --name-only --diff-filter=U
~~~

Read the conflict regions and determine the desired result. When undoing a merge, the goal is to reverse the merge's changes relative to the selected mainline while preserving other valid changes already present on HEAD after the merge.

After editing the files, stage the results:

~~~bash
git add -- src/PaymentService.java config/application.yml
~~~

If a file needs to be deleted in the revert result:

~~~bash
git rm -- path/to/file
~~~

Check the index and diffs:

~~~bash
git status
git ls-files -u
git diff --cached
git diff --cached --check
~~~

Once all conflicts are resolved, continue the revert operation:

~~~bash
git revert --continue
~~~

If you decide to stop and cancel the in-progress revert:

~~~bash
git revert --abort
~~~

--abort in this context cancels the current revert progress. It is not git rebase --abort and does not delete the original merge commit.

After the revert completes, re-run tests related to the reverted feature and dependent components. A cleanly applied patch does not guarantee the system remains functionally correct.

## Crucial Implication: Reverting a Merge Does Not Erase Merge History

This is an essential point to understand thoroughly before planning to re-merge the branch later.

When running git revert -m 1 M, Git creates a new commit whose content reverses M's changes relative to parent 1. However, commit M and the commits from the merged branch remain in the ancestor graph of main.

Illustration:

~~~text
                 C1---C2  feature/payment
                /       \
A---B-----------M---R     main
                 merge  revert M
~~~

In the diagram:

- M brought C1 and C2 into main's history.
- R is the commit reverting M, reversing the modified content of the merge.
- C1, C2, and M remain ancestors of main through R.

Git decides what needs to be merged based on ancestry and the merge base of the two branches. Revert only changes the working tree content via a new commit; it does not erase the ancestry relationship of the merge commit.

Therefore, if you re-merge the same feature/payment branch without new commits, Git will typically not bring C1 and C2 in again. Those commits are already ancestors of main, even though their content was reverted in the working tree.

A message like Already up to date may appear if the source branch has no new commits to integrate.

## Example: Second Merge Does Not Restore Reverted Changes

Suppose the initial history is:

~~~text
A---B---M---R       main
     \   /
      C1---C2       feature/payment
~~~

M is the merge commit. R is the commit undoing M via git revert -m 1 M.

If feature/payment is still at C2 with no new commits, running:

~~~bash
git switch main
git merge feature/payment
~~~

Git sees that C1 and C2 are already in main's history via M. Commit R did not remove that relationship. Therefore, the merge does not automatically re-apply the changes that R reversed.

This is not a Git bug. It is the expected outcome of the distributed history model: a revert is a new commit modifying content, not rewriting the past.

### If the source branch has new commits

Suppose the team continues developing feature/payment and creates C3 after C2:

~~~text
A---B---M---R          main
     \   /       \
      C1---C2---C3     feature/payment
~~~

When merging feature/payment into main, Git typically only needs to integrate the new commits since the merge base M—namely the changes of C3. Content from C1 and C2 is still considered already merged previously, even though R reversed them in the working tree.

This can create an awkward situation: C3 may depend on functions or data structures that R removed. The merge only brings in the new commit's changes, which may fail to run properly if the old changes have not been restored.

Before merging further, inspect the dependencies of the new commits and decide whether old changes must be restored or the source branch must be adjusted.

## How to Bring Reverted Changes Back

If the team confirms it wants to restore all changes from the reverted merge, the common approach is to revert the revert commit itself.

Suppose:

- M is the original merge commit.
- R is the commit created by git revert -m 1 M.

Run on the branch that needs restoration:

~~~bash
git revert R
~~~

This command reverses the content of R, effectively re-applying the changes that R undid. Git creates a new commit, often called a revert-of-revert.

Illustration:

~~~text
A---B---M---R---RR     main
     \   /       ^
      C1---C2    revert R
~~~

After RR, the content of the original merge is restored in the working tree. Ancestry relationships remain preserved. If feature/payment has an additional C3, the team can continue merging the new commit after verifying status and dependencies.

Inspect the revert commit before reversing it:

~~~bash
git show --stat --oneline R
git show R
~~~

Then execute:

~~~bash
git revert R
~~~

If conflicts arise, resolve them as a regular revert operation, stage the files, and run git revert --continue. Finally inspect diffs, history, and tests.

Do not perform a revert-of-revert solely to stop a subsequent merge from saying Already up to date. Confirm the team truly wants to restore the old behavior. If only part of a feature is needed, you can create a new commit re-implementing the needed part or update the source branch to fit the current state.

## An Alternative Workflow: Creating a New Commit for the Part to Restore

You do not always need to revert the revert commit. If the team only wants part of the changes back, you can create a new commit on main to re-implement the needed portion.

Example:

- The original merge brought the entire payment module into main.
- The merge was reverted because one handler method was unsafe.
- After fixing it, the team only wants to restore the transaction lookup API first.
- Instead of restoring the entire merge, the team creates a new commit bringing back only the fixed and tested lookup API.

This keeps the restoration scope clear. However, note that C1/C2's history is still already merged. The new commit is a new change on main, not a re-merge of those old commits.

If the team wants to continue developing the feature branch, it needs to sync that branch with main and check whether new commits depend on the reverted parts. Rebasing or merging main into the feature branch may be needed according to project conventions.

## Distinguishing Revert Merge, Revert Regular Commit, and Reset

| Operation | When to use | History impact |
|---|---|---|
| git revert <commit> | Reverse a single regular commit | Creates a new commit reversing the changes |
| git revert -m 1 <merge> | Reverse a merge's changes relative to parent 1 | Creates a new commit; original merge remains an ancestor |
| git revert <revert-commit> | Restore changes that were reverted | Creates a new commit re-applying the reversed patch |
| git reset | Move HEAD and optionally change index/working tree | Can rewrite history of the current branch |

For history already shared with a team, revert is usually the clearest way to record an undo without erasing old commits from the graph. Reset can suit unshared local work, but you must understand its impact before using it on a shared branch.

You cannot use git revert -m on a commit that is not a merge commit. If Git reports the commit is not a merge, check the parent count and choose the appropriate operation.

## Situations to Consider Before Reverting a Merge

### Other branches already built on top of the merge commit

If other branches already pulled commits from the merge or depend on the merged content, reverting can alter behavior those branches expect. Discuss with the team and identify dependencies before undoing.

### The merge brought in both good and buggy changes

Reverting the entire merge can remove valid work as well. If only one part caused a bug, consider creating a bugfix commit or selectively reverting appropriate commits if history structure permits. With a merge commit, -m reverses the overall delta relative to the mainline, not a filter selecting individual files or child commits.

### The source branch continues development

After reverting a merge, the old commits are still considered merged. Inform the source branch developers clearly and agree on how changes will be restored: revert-of-revert, selective new commits, or creating a new branch based on the current state of main.

### The merge commit has more than two parents

With an octopus merge or multi-branch merge, identify the exact parent to preserve. -m 1 is not always the release branch. Use git show --pretty=raw or git rev-list --parents to read parent order.

### The merge did not create a merge commit

If the previous operation was a fast-forward, there will be no merge commit for selecting a mainline. If it was a squash merge, the result is usually a single commit with one parent. In those cases, undo the corresponding commit with a regular git revert.

## Practical Workflow from Verification to Confirmation

Example needing to undo merge commit 7f8a9b0 on main:

~~~bash
# Check status and current branch
git status
git branch --show-current

# View history graph and merge commits
git log --oneline --graph --decorate --all
git log --oneline --merges

# Identify parents of the merge commit
git rev-list --parents -n 1 7f8a9b0
git show --no-patch --pretty=raw 7f8a9b0

# Cross-check parents and the merge's changes
git show --no-patch --oneline 111aaaa
git show --no-patch --oneline 222bbbb
git diff 7f8a9b0^1 7f8a9b0

# Once confirmed parent 1 is main before merge, undo it
git revert -m 1 7f8a9b0

# Inspect the revert commit and post-operation state
git status
git log --oneline --graph --decorate -n 12
git show --stat --oneline HEAD

# Run tests and inspect the changes
git diff HEAD^ HEAD
~~~

If reverting produces conflicts, resolve each file, stage the results, and run git revert --continue. If you decide to cancel an in-progress revert, use git revert --abort.

After undoing, if the team wants to restore the original changes, identify the newly created commit R and inspect:

~~~bash
git show --stat --oneline R
git revert R
~~~

Replace R with the actual commit hash. After restoring, check history, diffs, and tests before continuing to merge new commits from the source branch.

## Pre- and Post-Merge-Revert Checklist

- [ ] Identify the exact merge commit to undo.
- [ ] Check the number and order of parents.
- [ ] Identify which parent is the mainline to preserve.
- [ ] Ensure you are on the branch that needs to receive the revert commit.
- [ ] Check the working tree and uncommitted changes.
- [ ] Read the diff of the merge relative to the mainline.
- [ ] Understand which changes will be reversed.
- [ ] Resolve conflicts if any and stage the results properly.
- [ ] Run tests for affected functionality.
- [ ] Confirm the new revert commit and branch state.
- [ ] Notify the source branch developers of the implications.
- [ ] If re-merging is needed later, plan a revert-of-revert or selective new commits.

## Takeaways

A merge commit has multiple parents, so you must specify the mainline when undoing it with git revert -m. In a workflow merging feature into main, parent 1 is usually main before the merge, though you must inspect metadata rather than assuming. The revert command creates a new commit reversing the merge's content while preserving ancestry relationships in history. Consequently, re-merging the same branch usually does not automatically restore old reverted changes; Git only integrates new commits since the merge base. To restore all changes, teams usually revert the revert commit; to restore a portion, you can create selective new commits. Always inspect parents, diffs, dependencies, history, and application behavior before finishing.

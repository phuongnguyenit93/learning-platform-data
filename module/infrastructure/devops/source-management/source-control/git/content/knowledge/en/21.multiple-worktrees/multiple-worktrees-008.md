# Using Worktrees for Hotfixes, Reviews, and Parallel Experiments

When you are working on a feature but need to fix an urgent bug, review another branch, or try two implementation approaches, constantly stashing, creating temporary commits, and switching branches disrupts your flow. Git worktree allows you to create multiple working directories attached to the same repository. Each directory has its own working tree and index, so you can open multiple tasks at once without cloning the repository again.

In the **Multiple Working Directories** chapter of the **SOURCE_CONTROL_GIT** module, this lesson focuses on three practical scenarios: creating a dedicated worktree for a hotfix, opening a worktree strictly for review or testing, and running multiple experiments on independent branches. You will understand which data is shared across worktrees, the rule that a branch can only be checked out in one worktree, and how to manage the worktree lifecycle safely.

After this lesson, you will be able to:

- Explain linked worktrees and how a worktree differs from an independent clone.
- Create, list, lock, move, and remove worktrees.
- Use a dedicated worktree for a hotfix while main work remains open.
- Review a branch or commit in a separate worktree without modifying the current working tree.
- Create experimental worktrees with independent branches.
- Understand how HEAD, index, branches, tags, and the object database are shared or separated.
- Handle stale worktrees, moved paths, and leftover metadata.

## 1. What problem does a worktree solve?

A normal repository has one working tree. When checking out another branch, Git updates the contents of that directory to match the new branch. If there are uncommitted changes, you may have to commit, stash, or resolve conflicts before switching.

Git worktree allows a single repository to have multiple working trees at the same time:

~~~text
Shared Git repository
       |
       +-- Main working tree
       |      branch: feature/payment
       |      separate index
       |
       +-- Linked worktree A
       |      branch: hotfix/login
       |      separate index
       |
       +-- Linked worktree B
              detached HEAD: origin/feature/search
              separate index
~~~

For example, you are implementing payments in the main directory. A critical login bug appears and needs an immediate fix on main. Instead of tucking away the payment work and checking out main, you can create a new worktree in an adjacent directory, check out a hotfix branch there, fix the bug, and run tests. The payment working directory keeps its exact state.

Worktrees are also useful when:

- Reviewing a pull request while continuing to work on the current branch.
- Running tests or builds on two different versions of code.
- Comparing two implementation approaches in parallel.
- Keeping a stable worktree for a demo environment or bug reproduction.
- Opening an older commit to investigate without moving the active branch.

## 2. What do worktrees share and what do they separate?

A linked worktree is not an independent repository. It is attached to the main repository and shares most Git data.

| Component | How it works |
| --- | --- |
| Object database | Shares commit, tree, blob, and tag objects |
| Branch and tag refs | Shared; ref changes in one worktree can be seen from other worktrees |
| Remotes and remote-tracking refs | Shared; fetching from one worktree updates remote info for the entire repository |
| Working tree | Separate for each worktree path |
| Index (staging area) | Separate for each worktree |
| HEAD | Separate for each worktree; each location can check out a different branch or commit |
| Uncommitted modified file state | Separate within the corresponding working tree |

When committing in a linked worktree, the new commit object is written to the shared object database and the branch checked out in that worktree is updated. Other worktrees can see the commit via refs or the new history, while uncommitted contents in their working trees do not change automatically.

Because branch refs are shared, Git enforces an important rule: **a local branch can only be checked out in one worktree at a time**. This rule prevents two independent indexes from writing commits to the same branch, which would make state hard to predict.

For example, if the feature/payment branch is checked out in the main directory, a command to create another worktree that also checks out feature/payment will be rejected. You can create a worktree with a different branch or use detached HEAD to view the same commit without attaching that branch to the second worktree.

## 3. Checking existing worktrees

From any worktree belonging to the repository, run:

~~~bash
git worktree list
~~~

Example:

~~~text
/projects/shop                 2ab34cd [feature/payment]
/projects/shop-hotfix          8de901a [hotfix/login]
/projects/shop-review          4fa567b (detached HEAD)
~~~

The output shows the path, current commit, and checked-out branch. If a worktree is in detached HEAD, Git displays the detached state instead of a branch name.

For structured output that is easier to process:

~~~bash
git worktree list --porcelain
~~~

Porcelain output has fields such as worktree, HEAD, branch, detached, locked, or prunable. It is suitable for scripts or when you need to accurately check the status of each directory.

You can determine the shared Git directory and the Git directory of the current worktree:

~~~bash
git rev-parse --git-dir
git rev-parse --git-common-dir
~~~

In a linked worktree, the separate Git path usually points to metadata dedicated to that worktree; git-common-dir points to the shared data area. Do not manually edit files inside these directories.

## 4. Creating a worktree for a hotfix

Suppose you are working on the payment feature on the feature/payment branch. The team discovers a critical bug on main and needs to create the hotfix/login-timeout branch.

### Step 1: update remote information

From any worktree:

~~~bash
git fetch origin
git status -sb
~~~

Fetch updates remote-tracking branches such as origin/main. It does not alter uncommitted files in the current worktree.

### Step 2: create the hotfix worktree and branch

Create a new working directory at the same level as the current repository:

~~~bash
git worktree add -b hotfix/login-timeout ../shop-hotfix origin/main
~~~

This command:

- Creates a linked worktree at ../shop-hotfix.
- Creates a local branch hotfix/login-timeout from the origin/main commit.
- Checks out the new branch in the newly created worktree.
- Keeps the feature/payment branch and work in progress untouched in the main worktree.

If the hotfix/login-timeout branch already exists and is not checked out in any worktree, use:

~~~bash
git worktree add ../shop-hotfix hotfix/login-timeout
~~~

Do not reuse a branch name that is already checked out in another worktree. If you need to view the same commit without creating a new branch, use detached HEAD as in the review section below.

### Step 3: work in the hotfix directory

Switch your terminal to the new directory:

~~~bash
cd ../shop-hotfix
git status -sb
git branch --show-current
~~~

Make the fix, run tests, and view diffs as in a normal working tree:

~~~bash
git diff
git status
git add -- src/auth/LoginService.java
git diff --cached
git commit -m "fix(auth): handle login timeout"
~~~

### Step 4: push the hotfix branch

~~~bash
git push -u origin hotfix/login-timeout
~~~

Then create a pull request or follow your team's review and release workflow. The main worktree can still continue payment development.

### Step 5: return to main work

Switch your terminal back to the original directory:

~~~bash
cd ../shop
git status -sb
git branch --show-current
~~~

You are still on feature/payment with your previous index and working tree. Once the hotfix has been integrated, you can remove the dedicated worktree following the lifecycle management section.

## 5. Using a worktree to review a branch or commit

Reviewing often requires reading code, running tests, reproducing bugs, and comparing against the target branch. A dedicated worktree lets you do this without disrupting open work.

### Read-only inspection and testing of a remote branch

Update refs first:

~~~bash
git fetch origin
~~~

Create a detached worktree from the remote branch:

~~~bash
git worktree add --detach ../shop-review origin/feature/search
~~~

Detached HEAD means the worktree points directly to the commit, without checking out a local branch. This approach works well when you only need to read, build, or test and do not plan to make review commits.

Enter the review directory:

~~~bash
cd ../shop-review
git status -sb
git log -1 --oneline --decorate
~~~

If you need to test editing a file to verify a comment, you can edit inside this worktree. Uncommitted edits stay only in the review directory. However, if you want to save changes as commits, create a separate branch first:

~~~bash
git switch -c review/search-followup
~~~

Commits created will update the shared review/search-followup branch in the repository.

### Reviewing with a committable local branch

If the remote branch needs inspection and may produce trial fix commits, create a separate local branch from the remote-tracking branch:

~~~bash
git fetch origin
git worktree add -b review/feature-search ../shop-review origin/feature/search
~~~

Check the upstream:

~~~bash
cd ../shop-review
git branch -vv
~~~

If the branch does not yet track the desired remote branch, you can set the upstream explicitly:

~~~bash
git branch --set-upstream-to=origin/feature/search review/feature-search
~~~

The review/feature-search branch is a separate local branch. Committing to or resetting this branch does not directly move origin/feature/search; sharing commits requires pushing according to the team workflow.

### Opening an old commit to reproduce a bug

There is no need to create a branch if you only want to inspect a snapshot:

~~~bash
git worktree add --detach ../shop-old-release 4f8a21c
~~~

The new worktree checks out commit 4f8a21c in detached HEAD. You can run tests, compare behavior, or inspect configuration at that point in time. If you need to keep a new chain of commits from this point, create a branch in the worktree:

~~~bash
git switch -c investigation/old-release
~~~

## 6. Using multiple worktrees for parallel experiments

Suppose the team is considering two caching approaches. You can create two worktrees, each with its own branch:

~~~bash
git worktree add -b experiment/cache-memory ../shop-cache-memory origin/main
git worktree add -b experiment/cache-disk ../shop-cache-disk origin/main
~~~

Both branches start from the same origin/main commit. You can open the two directories in two different IDE windows or terminals:

~~~text
../shop-cache-memory
    branch: experiment/cache-memory
    test in-memory caching

../shop-cache-disk
    branch: experiment/cache-disk
    test disk caching
~~~

Each worktree has its own index and files. You can stage in one directory without changing the staging area of the other. Commits in each place update the corresponding branch and the shared object database.

If you only want a temporary experiment and do not need to keep commits, create a detached worktree:

~~~bash
git worktree add --detach ../shop-prototype <base-commit>
~~~

After experimenting, you can remove the worktree if you do not need to keep the content. If you discover a promising implementation direction, create a branch or commit in that worktree before cleaning up.

A practical note: worktrees separate source code directories, but they do not automatically isolate all resources outside the repository. If two running instances write to the same local database, share a server port, share an external cache directory, or use an absolute configured output directory, they can still conflict. Configure separate ports, databases/schemas, and build paths for each run when needed.

## 7. Branch rules and common issues

### A branch cannot be checked out in two worktrees

Suppose the feature/payment branch is checked out in the main worktree. The command:

~~~bash
git worktree add ../shop-payment-review feature/payment
~~~

will be rejected because that branch is already checked out elsewhere.

There are three ways to handle this:

- Use the existing worktree if the goal is simply to access the branch.
- Create a new branch from feature/payment if you need independent work.
- Use detached HEAD from the branch's commit if you only need to view or test.

Example creating an experimental branch:

~~~bash
git worktree add -b experiment/payment-review ../shop-payment-review feature/payment
~~~

The new branch starts from the commit of feature/payment but has its own ref. New commits on experiment/payment-review do not move feature/payment.

### Do not use force to bypass branch protection

Git has a force option in some worktree operations, but forcing the same branch to be checked out in multiple places can lose Git's protective benefits and create hard-to-control states. Use an independent branch or detached HEAD instead of forcing one branch to share two indexes.

### Do commits in another worktree appear in the current location?

Commit objects are shared, and that commit's branch is also a shared ref. If another branch is updated, you can see it via git branch or log; the current working tree does not automatically check out the new commit.

### Does fetching from one worktree affect other worktrees?

Yes. Remote-tracking refs belong to the repository's shared data. When fetching origin in one worktree, origin/main information is updated and can be used in the remaining worktrees.

### Are stashes isolated per worktree?

Do not treat stash as a separate storage area per worktree. Stashes are managed through a shared repository ref. When multiple worktrees create stashes, write clear messages and inspect git stash list before applying or dropping to avoid mixing up changes.

## 8. Managing the worktree lifecycle

Worktrees should be managed with Git commands so metadata and working directories always stay synchronized.

### Listing before cleaning up

~~~bash
git worktree list --porcelain
~~~

Verify the worktree path, branch, and status. In particular, check whether there are uncommitted changes, whether the branch still needs to be kept, or whether the worktree is locked.

### Removing a clean linked worktree

When the work is finished and the working tree has no remaining changes to keep:

~~~bash
git worktree remove ../shop-review
~~~

The remove command deletes the linked worktree and its corresponding metadata. Git normally refuses if the worktree still has uncommitted changes or untracked files that need protection. This mechanism helps prevent accidentally deleting work.

If the worktree still has changes, check status, commit, stash, or back up first. Only use force when you have confirmed all contents in the worktree can be discarded:

~~~bash
git worktree remove --force ../shop-review
~~~

Force can delete uncommitted data. Do not use it as a quick way to clean up a directory without checking.

After removing a worktree, its branch is not automatically deleted. If the branch is no longer needed and has been integrated, you can delete it separately:

~~~bash
git branch -d review/feature-search
~~~

Only delete a branch after confirming there are no remaining unique commits to keep and the branch has been integrated per team policy. If Git refuses because the branch has not been merged into the current branch, inspect the history before considering another action; do not use -D just to bypass the warning.

### Worktree deleted manually or path no longer exists

If the worktree directory was deleted outside of Git, metadata may remain in the repository. View the worktree list and prunable entries:

~~~bash
git worktree prune --dry-run --verbose
~~~

This command only previews stale metadata that would be cleaned up. After confirming the path truly no longer exists and does not need recovery, run:

~~~bash
git worktree prune --verbose
~~~

Prune cleans up metadata of invalid worktrees; it is not a replacement for remove on a worktree that still exists.

### Locking a worktree to keep long-term

If a worktree resides on a removable drive or a location that is frequently offline, you can lock it so Git does not treat it as a stale worktree when the path is temporarily unreachable:

~~~bash
git worktree lock --reason "release validation on external drive" ../shop-release
~~~

Unlock when the worktree is ready to be managed normally:

~~~bash
git worktree unlock ../shop-release
~~~

Check lock status with git worktree list --porcelain. Locking does not protect contents from a user manually deleting files; it only marks the worktree for management and pruning.

### Moving a worktree

For a linked worktree, use the move command to update both the path and metadata:

~~~bash
git worktree move ../shop-review ../reviews/shop-review
~~~

The main worktree cannot be moved with this command. If the directory was moved manually and metadata went out of sync, Git provides the repair command for appropriate situations:

~~~bash
git worktree repair
~~~

Prefer move over manually moving directories. If you must fix a location outside of Git, review the repair command documentation and verify git worktree list again after the operation.

## 9. Complete workflow: hotfix while still working on a feature

For example, you are on feature/checkout and there is a bug to fix on main.

**Create the hotfix worktree**

~~~bash
git fetch origin
git worktree add -b hotfix/checkout-crash ../shop-hotfix origin/main
~~~

**Fix and test in the new worktree**

~~~bash
cd ../shop-hotfix
git status -sb
git diff
git add -- src/checkout/CheckoutService.java
git diff --cached
git commit -m "fix(checkout): prevent crash on empty cart"
git push -u origin hotfix/checkout-crash
~~~

**Continue the main work**

~~~bash
cd ../shop
git status -sb
git branch --show-current
~~~

The feature/checkout branch and uncommitted changes remain in the original worktree.

**After the hotfix pull request is integrated**

~~~bash
git fetch origin
git worktree list
git worktree remove ../shop-hotfix
~~~

If the local hotfix branch is no longer needed, verify it has been integrated and then delete it separately. Removing the worktree and deleting the branch are two independent operations.

## 10. Checklist before creating or removing a worktree

Before creating:

- Confirm you are in the right repository.
- Fetch remotes if the worktree needs to start from the latest branch.
- Choose a separate, easily recognizable path that is not inside another worktree.
- Choose a new branch, an unchecked-out local branch, or detached HEAD.
- Check where branches are checked out using git worktree list.

Before removing:

- Confirm the exact worktree path.
- Check git status inside the worktree to be removed.
- Commit, stash, or back up content that needs to be kept.
- Confirm the branch has no remaining unique commits to preserve.
- Use git worktree remove and re-verify with git worktree list.

## 11. Common misconceptions

### Does a worktree create another full copy of the repository?

No. A linked worktree has its own file directory, while sharing the repository's object database and much of its metadata. It usually saves disk space and time compared to making an independent clone.

### Can the same branch be checked out in multiple worktrees?

By normal rules, no. Git refuses to prevent two independent indexes from working on the same branch. Create a separate branch or use detached HEAD.

### Is deleting the worktree directory via File Explorer enough?

It is not recommended. Manual deletion can leave stale metadata behind. Use git worktree remove when the directory still exists; if deleted manually, inspect and prune stale metadata after confirming.

### Do commits in one worktree appear in the shared repository?

Yes. The object database and branch refs are shared. However, uncommitted changes in that working tree do not appear in other worktrees.

### Can a worktree with uncommitted changes be removed?

Git normally refuses remove to protect data. Inspect and save changes first; only force remove after confirming those contents can be discarded.

### Is detached HEAD suitable for reviews?

Yes, if you only need to read and test. If you want to create commits to keep, create a branch beforehand or directly inside the worktree.

## 12. Self-check

You are working on the feature/payment branch in the main directory. A critical bug on main needs an immediate fix, while a teammate sends the feature/search branch for you to review. You also want to test two caching approaches in parallel.

Answer:

1. Which command creates a hotfix worktree from origin/main and creates a new branch?
2. Which command creates a detached worktree strictly for reviewing origin/feature/search?
3. If you want to commit a trial fix in the review worktree, what must you do first?
4. Why can't feature/payment be checked out in a second worktree while that branch is in use in the main directory?
5. What branches and paths should the two experimental worktrees use?
6. Are commits in the hotfix worktree visible from the main repository?
7. After the hotfix is integrated, which command removes the worktree and which command deletes the local branch?

**Hint:** Use git worktree add -b hotfix/urgent ../shop-hotfix origin/main to create the hotfix. Use git worktree add --detach ../shop-review origin/feature/search to review. If you need to commit, create a branch with git switch -c review/search-fix. Create a separate branch for each experiment because branch refs are shared and a branch can only be checked out in one worktree. Commit objects and branch refs are shared, while uncommitted changes are separate per directory. Use git worktree remove to remove the directory, then git branch -d after confirming the branch has been integrated.

## Conclusion

Git worktree helps you run multiple tasks in parallel in separate directories while sharing the object database and branch refs of a single repository. Creating a dedicated worktree for a hotfix lets you handle incidents without interrupting a feature in progress; a detached worktree works well for reviewing or testing; separate branches allow independent experimentation and commits. Remember that each local branch can only be checked out in one worktree at a time, check status before removing, and use worktree commands to manage metadata. By clearly distinguishing shared data from per-worktree state, you can switch between multiple tasks quickly while keeping Git history organized.

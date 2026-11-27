# Detached HEAD State and Developing Directly Inside a Submodule

When working with Git submodules, you may see a **HEAD detached** message right after cloning or updating the parent repository. This is normally expected: the parent repository records the exact commit that the submodule must use, so Git checks out that commit instead of automatically picking a moving branch.

Detached HEAD does not prevent you from reading source code, building, or even creating commits inside the submodule. However, if you create commits when HEAD is not attached to a branch, the new commit is not held by a local branch. When you later switch to another commit, it can be difficult to find that commit again if you did not create a ref to keep it.

To develop directly inside a submodule, create or switch to a branch inside the child repository, commit your changes, and push that commit to the submodule's remote. Then return to the parent repository, stage the submodule path, and commit the new gitlink. The two repositories have separate histories and must be shared in the right order.

## 1. Why Is a Submodule Usually in Detached HEAD State?

A submodule is an independent Git repository mounted inside another repository, commonly called the superproject or parent repository. In the parent repository's tree, Git does not store the entire commit contents of the child repository. It stores a **gitlink**: an entry pointing to a specific commit ID of the submodule.

For example, the parent repository might record:

~~~text
Application
├── src/
├── config/
└── libs/payment-engine  -> commit 8a31f2c of repository payment-engine
~~~

When someone checks out a commit of the parent repository, Git needs to align the submodule to the exact recorded commit. That commit may not be the latest tip of the main branch in the child repository. Therefore, Git directly checks out the pinned commit ID, leaving HEAD in a detached state.

Cloning with submodules:

~~~sh
git clone --recurse-submodules https://example.com/team/store-app.git
~~~

Or if the parent repository is already cloned:

~~~sh
git submodule update --init --recursive
~~~

These commands initialize submodules and check out the commits required by the parent repository. Under the default update mode, the submodule is typically in detached HEAD.

### 1.1. Is Detached HEAD an Error?

No. This is how Git guarantees the parent repository references a deterministic submodule version. If Git automatically checked out the submodule's main branch, the same commit of the parent repository could receive different submodule contents at different times as main advances.

Detached HEAD is appropriate when:

- You only need to build or run the project at the pinned version.
- You want to inspect the exact submodule source code required by the parent repository.
- You do not need to develop or create new commits inside the submodule.

When you need to modify the submodule's source code, switch to a branch so new commits have a named ref holding them.

## 2. Identifying the State of a Submodule

Suppose the submodule is located at path libs/payment-engine. You can check its status from the parent repository:

~~~sh
git submodule status
git status --short
~~~

The git submodule status command displays the commit each submodule currently has checked out. The leading character on each line indicates its state:

| Character | Meaning |
|---|---|
| Space | Submodule is initialized and at the commit recorded by the parent repository |
| Minus (-) | Submodule has not been initialized |
| Plus (+) | Checked-out commit differs from the commit recorded by the parent repository |
| U | Submodule has a merge conflict |

Enter the child repository and inspect directly:

~~~sh
git -C libs/payment-engine status -sb
git -C libs/payment-engine branch --show-current
git -C libs/payment-engine rev-parse --short HEAD
git -C libs/payment-engine log -1 --oneline --decorate
~~~

If HEAD is detached, git status typically reports HEAD detached at a commit ID; git branch --show-current returns an empty string because there is no current branch.

You can inspect the submodule's remotes:

~~~sh
git -C libs/payment-engine remote -v
~~~

Do not confuse the parent repository's remote with the submodule's remote. The two repositories may use different URLs, access permissions, and push workflows.

## 3. Creating a Branch in the Submodule Before Developing

### 3.1. Creating a New Branch from the Checked-Out Commit

When in detached HEAD at the commit pinned by the parent repository, create a new branch right at that commit:

~~~sh
git -C libs/payment-engine switch -c feature/add-refund-support
~~~

This command creates the branch feature/add-refund-support pointing to the current commit and switches HEAD to that branch. Subsequent commits will advance the branch, keeping your development history preserved.

Verify:

~~~sh
git -C libs/payment-engine branch --show-current
git -C libs/payment-engine status -sb
~~~

The current branch should be feature/add-refund-support.

### 3.2. Switching to an Existing Branch

If the branch already exists locally:

~~~sh
git -C libs/payment-engine switch feature/add-refund-support
~~~

If the branch only exists on the remote:

~~~sh
git -C libs/payment-engine fetch origin
git -C libs/payment-engine switch --track -c feature/add-refund-support origin/feature/add-refund-support
~~~

The switch --track command creates a local branch tracking the corresponding remote branch. If a local branch already exists, simply switch to it and update it according to your team's conventions.

### 3.3. Choosing an Appropriate Starting Point

You can develop starting from the submodule commit currently pinned by the parent repository, or from a newer branch in the child repository. The two choices have different implications:

- **Starting from the pinned commit:** appropriate when the change must be directly compatible with the submodule version the application currently uses.
- **Starting from a newer branch:** appropriate when the team wants to upgrade the submodule to a newer development version; you must verify compatibility and update the gitlink in the parent repository.

Before deciding, inspect the history and consult the submodule maintainer if the base branch or release policy is unclear:

~~~sh
git -C libs/payment-engine fetch origin
git -C libs/payment-engine log --oneline --graph --decorate --all -15
~~~

Do not assume the submodule's main branch is always the right starting point. The parent repository might be using a release branch or a specifically tested commit.

## 4. Developing and Committing Directly Inside the Submodule

Once you are on a branch, work as you would in any normal Git repository.

### 4.1. Inspecting Changes

~~~sh
git -C libs/payment-engine status
git -C libs/payment-engine diff
git -C libs/payment-engine diff --check
~~~

Only modify files belonging to the child repository. Do not include parent repository changes in a submodule commit.

### 4.2. Staging and Committing in the Child Repository

~~~sh
git -C libs/payment-engine add src/refund-service.ts tests/refund-service.test.ts
git -C libs/payment-engine diff --cached
git -C libs/payment-engine commit -m "Add refund support"
~~~

This commit is created inside the payment-engine repository. It does not automatically create a commit in the parent repository.

Verify:

~~~sh
git -C libs/payment-engine status -sb
git -C libs/payment-engine log -1 --oneline
~~~

If changes remain in the working tree, identify what has not been staged or committed. Do not return to the parent repository and update the gitlink before understanding the exact state of the child repository.

### 4.3. What Happens If You Commit While HEAD Is Detached?

Git still allows you to create commits in detached HEAD. That commit has a SHA and can be viewed with git log, but it is not automatically attached to a branch. If you later check out another commit, the new commit may no longer be referenced by any branch.

If you have already created a commit while detached, you can preserve it by creating a branch right at the current commit:

~~~sh
git -C libs/payment-engine switch -c rescue/refund-work
~~~

The new branch will point to the commit HEAD is currently on, keeping the commit in a named history. Do this before switching to another commit if you want to preserve your work.

## 5. Pushing Commits to the Submodule's Remote

The parent repository can only reference a submodule commit usefully for others if that commit can be fetched from a remote they have permission to access.

### 5.1. Pushing a Branch for the First Time

~~~sh
git -C libs/payment-engine push -u origin feature/add-refund-support
~~~

The -u option sets upstream tracking so subsequent pushes can simply use:

~~~sh
git -C libs/payment-engine push
~~~

If the submodule's remote uses a name other than origin, use the exact remote shown by git remote -v.

### 5.2. Reviewing Submodule Changes

If the submodule is maintained by another team, open a pull request or merge request in the child repository following that team's workflow. The parent repository may reference a branch commit during active development, but before integrating into a main branch or releasing, it should use a reviewed and stably shared commit.

When branches are protected, push your working branch and wait for review instead of attempting to push directly to the main branch.

### 5.3. Why Should You Push the Submodule Before the Parent Repository?

Suppose the parent repository records a new submodule commit 91ab23c. If that commit exists only on your local machine, others cloning the parent repository will not be able to fetch the corresponding content from the submodule remote.

Therefore, the order should be:

1. Commit changes in the submodule.
2. Push the commit or branch containing that commit to the submodule's remote.
3. Return to the parent repository and update the gitlink.
4. Commit and push the gitlink change in the parent repository.

This order ensures the referenced commit is reachable when others initialize submodules.

## 6. Updating the Gitlink in the Parent Repository

After committing in the submodule, the parent repository sees that the submodule path is at a different commit than previously recorded.

Return to the parent repository root:

~~~sh
cd ../..
git status --short
git diff --submodule=log
~~~

The submodule path may appear as modified with new commits information. This indicates the gitlink points to a new commit.

Stage the submodule path:

~~~sh
git add libs/payment-engine
git diff --cached --submodule=log
git status --short
~~~

Running git add in the parent repository records the commit that the submodule currently has checked out. It does not stage individual files inside the child repository; those files were already committed in the child repository.

Create a commit in the parent repository:

~~~sh
git commit -m "Update payment-engine submodule"
~~~

Then push the parent repository:

~~~sh
git push
~~~

The parent repository commit contains the new gitlink, meaning the specific commit ID of the submodule. When others check out that parent commit and run git submodule update --init --recursive, Git checks out that exact pinned submodule commit.

## 7. Understanding the Role of .gitmodules and Branches in Submodules

The .gitmodules file in the parent repository stores the information Git needs to know where a submodule lives and which URL to fetch it from. For example:

~~~ini
[submodule "libs/payment-engine"]
    path = libs/payment-engine
    url = https://example.com/team/payment-engine.git
    branch = main
~~~

Important fields:

- path: the submodule path in the parent repository.
- url: the child repository address.
- branch: the remote branch used when running a remote-tracking update operation such as git submodule update --remote.

The branch field is optional. If omitted, Git uses the remote's default branch according to submodule update --remote behavior.

### 7.1. Declaring a Branch for Remote Updates

You can set the branch with a command:

~~~sh
git submodule set-branch --branch main -- libs/payment-engine
git diff -- .gitmodules
git add .gitmodules
git commit -m "Track payment-engine main branch"
~~~

This change updates configuration in the parent repository. It does not immediately convert a detached submodule into the main branch, nor does it change the currently recorded gitlink.

A special value is a dot:

~~~ini
branch = .
~~~

This value instructs Git to use the branch with the same name as the superproject's current branch when performing remote updates. This approach only works when the team maintains matching branch names across both repositories.

### 7.2. What Does git submodule update --remote Mean?

The command:

~~~sh
git submodule update --remote -- libs/payment-engine
~~~

instructs Git to fetch the remote branch configured for the submodule and update the submodule to the latest commit on that branch. By default, the update method is checkout, so the submodule usually ends up in detached HEAD again.

This differs from standard git submodule update:

- git submodule update checks out the commit recorded by the parent repository.
- git submodule update --remote fetches the new commit from the configured remote branch and updates the submodule to that commit.

After using --remote, the parent repository may report the gitlink as modified. If you want to share the new version, you must stage the submodule path and commit the gitlink in the parent repository.

### 7.3. Updating from a Remote Branch While Working on a Local Branch

If you are developing on your own branch and want to integrate new commits from a remote branch:

~~~sh
git -C libs/payment-engine fetch origin
git -C libs/payment-engine switch feature/add-refund-support
git -C libs/payment-engine merge origin/main
~~~

Or use rebase if team policy allows and others have not based work on your branch:

~~~sh
git -C libs/payment-engine rebase origin/main
~~~

Git also supports telling submodule update to merge or rebase remote commits into the currently checked-out branch:

~~~sh
git submodule update --remote --merge -- libs/payment-engine
~~~

or:

~~~sh
git submodule update --remote --rebase -- libs/payment-engine
~~~

The --merge and --rebase options keep the submodule on its current branch while integrating fetched commits, provided the branch and working tree satisfy the preconditions. Inspect status and resolve conflicts inside the child repository like any regular repository.

## 8. Working with Detached HEAD Without Losing Work

### 8.1. No Files Modified and Only Using the Submodule

If you only need to build or run the project at the pinned commit, you can stay in detached HEAD. There is no need to create a branch just to silence the detached HEAD message.

### 8.2. Files Modified Locally but Not Yet Committed

If HEAD is detached and you already have uncommitted changes, creating a branch at the current position normally preserves your working tree:

~~~sh
git -C libs/payment-engine switch -c feature/local-fix
~~~

Then inspect:

~~~sh
git -C libs/payment-engine status
git -C libs/payment-engine diff
~~~

If Git refuses to switch branches because changes would be overwritten, do not force checkout. Commit the appropriate changes or stash them after reviewing carefully, then switch branches.

### 8.3. Committed in Detached HEAD

If you just created a commit while detached and have not switched away, create a branch to retain the commit:

~~~sh
git -C libs/payment-engine switch -c rescue/keep-detached-commit
~~~

Then push the branch if it needs to be shared:

~~~sh
git -C libs/payment-engine push -u origin rescue/keep-detached-commit
~~~

If you have already switched to another commit and no longer see the new commit on a branch, you can recover it via reflog:

~~~sh
git -C libs/payment-engine reflog --date=local
~~~

Locate the newly created commit entry, then create a branch pointing to that SHA:

~~~sh
git -C libs/payment-engine branch rescue/recovered-work <commit-sha>
~~~

The reflog records movements of HEAD and refs in the local repository for a period of time. It is useful for rescuing commits not held by a branch, though it does not replace pushing or creating backup branches.

### 8.4. Parent Repository Runs Update While You Are Developing

Before running git submodule update, inspect the child repository:

~~~sh
git -C libs/payment-engine status -sb
git -C libs/payment-engine branch --show-current
git -C libs/payment-engine log -1 --oneline
~~~

If there are uncommitted changes or unpushed local commits, save them with commits and a branch, then push or back up as appropriate. Running update in checkout mode can move the submodule back to the commit required by the parent repository; that can move you off the commit you were working on.

## 9. Resolving Conflicts in a Submodule

Conflicts occur inside the submodule repository when merging or rebasing changes of the child repository itself. The resolution process is the same as regular Git:

~~~sh
git -C libs/payment-engine status
~~~

Open each conflicted file, keep the correct logic from each side, then stage and continue:

~~~sh
git -C libs/payment-engine add src/refund-service.ts
git -C libs/payment-engine merge --continue
~~~

If rebasing, use:

~~~sh
git -C libs/payment-engine rebase --continue
~~~

After completing, run tests inside the child repository. If you need to cancel the operation:

~~~sh
git -C libs/payment-engine merge --abort
~~~

or:

~~~sh
git -C libs/payment-engine rebase --abort
~~~

The parent repository can also encounter conflicts when two branches change the gitlink of the same submodule to two different commits. In that case, choose the appropriate submodule commit in the parent repository; if both changes need to be combined, perform the merge/rebase inside the child repository first, push the resulting commit, and then update the parent repository's gitlink to the new commit.

Do not resolve a gitlink conflict by blindly picking one SHA without inspecting the corresponding contents in the child repository.

## 10. How to Inspect Overall State Across Both Repositories

When working directly inside a submodule, inspect both the child repository and the parent repository.

Inside the child repository:

~~~sh
git -C libs/payment-engine status -sb
git -C libs/payment-engine branch --show-current
git -C libs/payment-engine log -3 --oneline --decorate
git -C libs/payment-engine remote -v
~~~

Inside the parent repository:

~~~sh
git status --short
git diff --submodule=log
git submodule status
~~~

These two perspectives answer different questions:

| Check | Question |
|---|---|
| Status inside submodule | Which files in the child repository are modified or staged? |
| Branch inside submodule | Which branch is HEAD on, or is it detached? |
| Log inside submodule | What is the latest commit of the child repository? |
| Status in superproject | Has the submodule's gitlink changed? |
| Submodule diff in superproject | Which submodule commit will the parent repository record? |
| Submodule status | Is the submodule initialized and matching the parent's recorded commit? |

Do not look only at git status in the parent repository and assume every file inside the submodule has been committed. Always inspect directly inside the child repository.

## 11. Sample Workflow: Modifying a Submodule Library and Updating the Application

Suppose the store-app application uses the libs/payment-engine submodule. You need to add refund support to the library.

**Step 1 — Initialize and inspect the submodule**

~~~sh
git submodule update --init --recursive
git -C libs/payment-engine status -sb
git -C libs/payment-engine log -1 --oneline
~~~

**Step 2 — Create a branch in the child repository**

~~~sh
git -C libs/payment-engine switch -c feature/add-refund-support
~~~

**Step 3 — Modify code and commit**

~~~sh
git -C libs/payment-engine add src/refund-service.ts tests/refund-service.test.ts
git -C libs/payment-engine diff --cached
git -C libs/payment-engine commit -m "Add refund support"
~~~

**Step 4 — Push the child repository**

~~~sh
git -C libs/payment-engine push -u origin feature/add-refund-support
~~~

**Step 5 — Review and integrate in the child repository**

Open a PR/MR in payment-engine. Once reviewed, merge according to the child repository's workflow. If the application needs to reference a specific commit before the branch is merged, the team must agree on how to reference it and ensure the commit is pushed to a reachable remote.

**Step 6 — Update the gitlink in the parent repository**

Check out the selected commit inside the submodule, then return to store-app:

~~~sh
git -C libs/payment-engine fetch origin
git -C libs/payment-engine switch --detach <approved-commit>
git add libs/payment-engine
git diff --cached --submodule=log
git commit -m "Update payment-engine submodule"
~~~

In this example, checking out detached is intentional because the parent repository only needs to record the approved commit. Library developers can continue working on branches in the child repository; the application developer's local checkout state can be adjusted after committing the gitlink.

**Step 7 — Push the parent repository**

~~~sh
git push
~~~

Others pull the change:

~~~sh
git pull
git submodule update --init --recursive
~~~

They receive the exact payment-engine commit pinned by store-app.

## 12. Common Mistakes and How to Handle Them

**Seeing detached HEAD and thinking the submodule is broken.** This is the normal state when Git checks out the commit pinned by the parent repository. Only create a branch if you need to develop directly.

**Committing in the submodule but forgetting to push.** The parent repository can record the new gitlink, but others cannot fetch the commit if the submodule remote does not have it. Push the child repository before pushing the parent repository.

**Committing in the submodule but forgetting to commit the gitlink.** Changes in the child repository do not automatically update the parent repository. Run git add on the submodule path and create a commit in the superproject.

**Running git submodule update and moving off your working branch.** The default update command checks out the pinned commit. Before running it, save your commit on a branch and push/back up if needed.

**Committing while detached and then switching away.** Create a rescue branch at that commit or recover it with reflog before garbage collection cleans up unreferenced objects.

**Confusing branch in .gitmodules with the gitlink.** The branch field guides update --remote operations; the gitlink in the parent repository still records a specific commit SHA.

**Pushing to the wrong remote.** The parent repository and the submodule have separate remotes. Check git remote -v in the right repository before pushing.

**Updating a gitlink to an unreachable commit.** Confirm the submodule commit has been pushed to the remote and other users have read access before committing the pointer in the parent repository.

## 13. Checklist for Developing Directly Inside a Submodule

**Before editing**

- [ ] Confirmed the exact submodule path and child repository remote.
- [ ] Checked the commit currently pinned by the parent repository.
- [ ] Checked the working tree and detached HEAD state.
- [ ] Created or switched to an appropriate branch inside the submodule.

**While developing**

- [ ] Modified and staged only files belonging to the child repository.
- [ ] Reviewed diffs and ran submodule tests.
- [ ] Committed on a named branch.
- [ ] Pushed the commit to the submodule remote.
- [ ] Completed review or confirmed which commit should be used.

**When updating the parent repository**

- [ ] Submodule has the exact commit to pin checked out.
- [ ] Inspected git diff --submodule=log.
- [ ] Staged the right submodule path.
- [ ] Committed the gitlink in the parent repository.
- [ ] Pushed the parent repository after ensuring the submodule commit is reachable.
- [ ] Tested git submodule update in another clone or environment if needed.

## 14. Conclusion

Detached HEAD in a submodule is a natural consequence of the parent repository pinning a specific commit of the child repository. This state ensures everyone checks out the same submodule version, though it is not a convenient place for sustained development of new commits.

When you need to modify a submodule, create a branch directly inside the child repository, commit, and push changes to its remote. Then update the gitlink by staging the submodule path and committing in the parent repository. Always check both repositories and ensure the submodule commit is reachable before sharing the parent commit. This practice prevents losing detached commits, pushing to the wrong remote, and leaving the parent repository referencing a submodule version that teammates cannot fetch.

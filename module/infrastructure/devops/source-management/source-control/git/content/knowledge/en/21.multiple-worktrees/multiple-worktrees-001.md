# Git Worktrees Solve Context Switching Between Branches

When developing a long-running feature, you may suddenly need to switch to another branch to fix an urgent bug, review a pull request, or inspect an older version. With only a single working tree, switching branches may require temporary commits, stashing changes, waiting for build tools to stop, or restoring your original working environment. Git provides **worktree** so that a single repository can have multiple working directories at the same time, each checking out its own branch or commit.

With worktrees, you can keep the feature you are working on open in one directory, handle a hotfix in another directory, and keep an additional directory strictly for review. Worktrees share the repository's Git data and references, while each worktree has its own HEAD, index, and working tree. This enables fast context switching without creating multiple independent clones.

This lesson belongs to the **Multiple Working Directories** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; it also builds skills in branch-based collaboration, conflict resolution, tracking down changes, and recovering from mistakes while preserving important history. Worktree is a useful tool when you need to work on multiple tasks in parallel within the same repository while keeping branches and history consistent.

## 1. What is a Git worktree?

A standard repository has one main working tree. When you add a linked worktree, Git creates an additional working directory linked to that repository. Each directory can check out a different branch or a commit in a detached HEAD state.

Example:

~~~text
workspace/
|-- payment-service/          # main worktree, working on feature/payment
|-- payment-hotfix/           # linked worktree, working on hotfix/login
|-- payment-review/           # linked worktree, used to review another branch
|-- payment-investigation/    # linked worktree, inspecting an older commit
~~~

These directories share the repository's common object database and references. Git does not create a full copy of the entire history for each worktree as it does when running multiple independent clone commands.

A linked worktree contains a small <code>.git</code> file pointing to the metadata area managed by the main repository. This file is usually not a full <code>.git</code> directory. Therefore, do not manually copy a worktree to another location and edit the <code>.git</code> file yourself; use <code>git worktree</code> commands to create, move, repair, or remove worktrees.

## 2. What problem does a worktree solve?

Without a worktree, the context-switching workflow usually goes as follows:

1. Stop the work in progress.
2. Create a temporary commit or stash unfinished changes.
3. Check out the branch that needs attention.
4. Fix the bug or perform the review.
5. Switch back to the old branch and restore the working state.

This workflow can disrupt your work, especially when the current branch has changes not yet ready to commit or the project takes a long time to build.

With worktrees, you can keep two branches in two separate directories:

- The first directory continues to hold the feature under development.
- The second directory holds the hotfix branch or the branch to review.

You can open both in your IDE, run tests independently, and switch between them by switching windows or tabs. Each worktree maintains its own working tree and index state, so editing files in one directory does not directly modify files in the other.

Worktrees are especially useful when:

- Working on a feature while needing to fix an urgent bug on a release branch.
- Needing to review a pull request while preserving your current development environment.
- Needing to compare two branches or run tests on two versions.
- Wanting to inspect an older commit without switching the branch you are working on.
- Needing multiple parallel working environments for independent tasks.

## 3. What do worktrees share and what do they isolate?

To use worktrees safely, you need to understand which data is shared and which data belongs exclusively to each directory.

| Component | Scope |
|---|---|
| Object database (commit, tree, blob) | Shared across the repository |
| Local branches and tags | Shared references |
| Remote configuration and most repository settings | Shared per repository configuration |
| HEAD | Specific to each worktree |
| Index / staging area | Specific to each worktree |
| Working tree and untracked files | Specific to each directory |
| HEAD reflog | Per worktree |
| Remote-tracking refs | Shared across the repository |

For example, if you commit in a worktree that has checked out the <code>hotfix/login</code> branch, the <code>hotfix/login</code> branch reference is updated in the shared repository. Other worktrees can see the new commit through history and references, but the file contents in their working trees are not automatically checked out again.

Similarly, if one worktree runs <code>git fetch origin</code>, the remote-tracking refs are updated in the shared repository and other worktrees can see that new information. However, fetching does not automatically merge or rebase changes into the active branch in each directory.

Key point to remember: a worktree has its own index and working tree, but it does not have its own separate copy of branches. Operations that move a local branch affect the shared reference, so avoid updating a branch in a way that surprises other worktrees.

## 4. Inspecting existing worktrees

From any worktree belonging to the repository, run:

~~~bash
git worktree list
~~~

Example output:

~~~text
/workspace/payment-service          a1b2c3d [feature/payment]
/workspace/payment-hotfix           e4f5a6b [hotfix/login]
/workspace/payment-investigation    123abcd (detached HEAD)
~~~

Each line shows the worktree path, the current commit, and the checked-out branch if any. A line with <code>(detached HEAD)</code> indicates that the worktree has checked out a commit directly rather than a local branch.

For output that is easy to parse in scripts:

~~~bash
git worktree list --porcelain
~~~

Porcelain mode outputs each field on its own line, with separators between worktrees. This is the appropriate choice for automation tools because the format depends less on human-readable presentation.

You can also check the branch in use in each directory with:

~~~bash
git branch -vv
git status
~~~

<code>git branch -vv</code> shows local branches and upstreams; <code>git status</code> shows whether the current working tree has staged, unstaged, or untracked changes. Make sure to run these inside the exact worktree directory you want to inspect.

## 5. Creating a new worktree for a new branch

Suppose you are working on a feature in the main worktree and need a hotfix branch based on <code>main</code>. You can create a new worktree and a new branch at the same time:

~~~bash
git fetch origin
git worktree add -b hotfix/login ../payment-hotfix origin/main
~~~

Meaning:

- <code>git worktree add</code> creates a linked worktree.
- <code>-b hotfix/login</code> creates a new local branch named <code>hotfix/login</code>.
- <code>../payment-hotfix</code> is the path to the new working directory.
- <code>origin/main</code> is the base commit for creating the new branch.

After the command, the <code>../payment-hotfix</code> directory is created and the <code>hotfix/login</code> branch is checked out. You can open this directory in your IDE and work on the hotfix independently of the main worktree.

If you want to create the branch from the current local <code>main</code>, you can use:

~~~bash
git worktree add -b hotfix/login ../payment-hotfix main
~~~

Before using <code>main</code> as a starting point, verify that it is updated to the state the team expects. If the base branch needs to be fetched from the server, fetch first and then specify the remote-tracking branch.

### General syntax

~~~bash
git worktree add <path> [<commit-ish>]
git worktree add -b <new-branch> <path> [<commit-ish>]
~~~

If <code>&lt;commit-ish&gt;</code> is omitted, Git uses the current HEAD as the starting point. Place the new worktree in a separate directory, usually a sibling directory to the main repository, so it is easy to identify and manage.

## 6. Creating a worktree for an existing local branch

If the branch has already been created and is not checked out in another worktree, you can add a worktree directly:

~~~bash
git worktree add ../payment-review feature/payment
~~~

The command creates the <code>../payment-review</code> directory and checks out the local branch <code>feature/payment</code> there. This is a convenient way to review a branch without modifying the active development directory.

If the <code>feature/payment</code> branch is not checked out in any other worktree, you can use <code>payment-review</code> to run tests, inspect diffs, and verify the branch. If this branch is currently checked out in the main worktree <code>payment-service</code>, the add worktree command above will be rejected. In that case, create a separate review branch from the same starting point:

~~~bash
git worktree add -b review/payment ../payment-review feature/payment
~~~

Or create a detached worktree if you only need to read source code and run tests:

~~~bash
git worktree add --detach ../payment-review feature/payment
~~~

That way, the main worktree continues to hold the <code>feature/payment</code> branch, while the review directory uses a separate branch or detached HEAD.

If a worktree is created on the <code>feature/payment</code> branch, every commit created in that worktree updates the same shared branch reference in the repository. Therefore, if another worktree is also using that branch, Git will not allow a second worktree to check out the same branch in the normal way.

### When the branch is on the remote

If the branch only exists on the remote and you want to create a local branch for review, you can create a worktree with a tracking branch:

~~~bash
git fetch origin
git worktree add --track -b review/payment ../payment-review origin/feature/payment
~~~

This command creates a local branch <code>review/payment</code> tracking <code>origin/feature/payment</code>, then checks out the new branch in the review worktree. Using a separate name avoids occupying a local branch that might already be in use in the main worktree.

## 7. Creating a detached worktree to inspect a commit

You do not always need to create a branch. When you only want to test an older commit or inspect the contents of a historical point, use detached HEAD:

~~~bash
git worktree add --detach ../payment-investigation 123abcd
~~~

Git creates a worktree at <code>../payment-investigation</code> and checks out commit <code>123abcd</code> without creating a new local branch.

A detached worktree is suitable for:

- Running tests on an older release.
- Comparing behavior before and after a commit.
- Investigating a reported bug that only occurs in a specific version.
- Viewing source code at a historical point without affecting the active branch.

If you create commits in detached HEAD, the new commits are not automatically attached to a local branch. Create a branch before or immediately after creating commits if you want to keep the results easy to find:

~~~bash
git switch -c investigation/fix-at-123abcd
~~~

The command above creates a branch from the current commit in the detached worktree and switches HEAD to the new branch. Once the branch is created, subsequent commits are recorded on that branch.

## 8. Limitation: a local branch can only be checked out in one worktree

Git normally prevents the same local branch from being checked out in multiple worktrees at the same time. This avoids having two directories updating the same branch reference while having separate indexes and working trees, which could cause confusion or lost work.

For example, if <code>feature/payment</code> is checked out in the main worktree, the command:

~~~bash
git worktree add ../payment-second feature/payment
~~~

may be rejected with a message stating that the branch is already in use in another worktree.

This is an intentional safeguard. Choose one of the following approaches:

- Create a new branch from the current branch using <code>git worktree add -b</code>.
- Use a separate review branch tracking the remote branch.
- Use detached HEAD if you only need to read or test a commit.
- Switch the active branch to another worktree after checking status and aligning your work.

The <code>--force</code> option can bypass some protective checks, but you should not use it just to force the same branch to appear in multiple worktrees. Doing so can cause two locations to operate on a single reference and increase the risk of overwrites or confusing states.

## 9. Working independently in each worktree

After creating a worktree, navigate into the appropriate directory:

~~~bash
cd ../payment-hotfix
git status
git branch --show-current
~~~

You can edit files, stage, and commit just as in a normal repository:

~~~bash
git add src/auth/
git diff --staged
git commit -m "fix: handle expired login token"
~~~

The created commit updates the <code>hotfix/login</code> branch. The main worktree keeps its own working tree and index unchanged. When you return to the main directory, you can view the new branch and history; there is no need to fetch to see the newly created local commit because the worktrees belong to the same repository.

Each worktree can run its own builds or tests. However, pay attention to output directories or shared services outside the repository. If two worktrees write to the same development database, use the same server port, or share the same external cache directory, they can still conflict even though the Git files are separated.

## 10. Practical workflow: hotfix in parallel with a feature

Suppose you are developing <code>feature/payment</code>, but the team asks you to fix a login bug on the <code>main</code> branch.

~~~mermaid
flowchart TD
    A["Main worktree: feature/payment"] --> B["Keep work in progress intact"]
    B --> C["Create new worktree from origin/main"]
    C --> D["Hotfix worktree: hotfix/login"]
    D --> E["Fix bug, run tests, and commit"]
    E --> F["Push hotfix and open review"]
    F --> G["Integrate hotfix per team workflow"]
    G --> H["Remove worktree when no longer needed"]
    B --> I["Continue feature/payment"]
~~~

Commands:

~~~bash
# From the main worktree
git status
git fetch origin
git worktree add -b hotfix/login ../payment-hotfix origin/main

# In the hotfix worktree
cd ../payment-hotfix
git status
git add src/auth/
git commit -m "fix: handle expired login token"
git push -u origin hotfix/login

# Return to the main worktree to continue the feature
cd ../payment-service
git status
git branch -vv
~~~

The two branches are developed in two separate directories. You do not need to stash or temporarily commit work in progress on <code>feature/payment</code> just to switch to the hotfix.

## 11. Managing the worktree lifecycle

Worktrees are usually created for a specific task. When the task ends, clean up the worktree so the repository does not accumulate stale directories.

### Listing worktrees

~~~bash
git worktree list
git worktree list --porcelain
~~~

Run the command from an active worktree to see the linked paths and their status.

### Removing a linked worktree

When the hotfix is complete and you no longer need the directory, return to the main worktree or another worktree and run:

~~~bash
git worktree remove ../payment-hotfix
~~~

Git removes the linked worktree and its associated metadata if the worktree meets the safety conditions. By default, Git protects worktrees that have uncommitted changes or untracked files to prevent accidental data loss.

Before removing, check:

~~~bash
git -C ../payment-hotfix status
git -C ../payment-hotfix log --oneline -5
~~~

Ensure that commits you want to keep have been pushed, merged, or are protected by another reference. If the worktree still has uncommitted changes, commit, stash, or back them up before removing.

The <code>--force</code> option can bypass protective checks when removing a worktree. Only use it after confirming the contents inside are no longer needed:

~~~bash
git worktree remove --force ../payment-hotfix
~~~

Do not use <code>--force</code> as a default cleanup step. It can delete local changes that you have not saved elsewhere.

For a locked worktree, Git requires a more explicit force action; some cases require repeating the <code>--force</code> option. Unlock it if possible and recheck its status before removing.

### Deleting the branch after removing the worktree

Removing a worktree does not automatically delete the local branch. If the branch has been integrated and is no longer needed, you can delete it separately:

~~~bash
git branch -d hotfix/login
~~~

<code>-d</code> tells Git to check that the branch has been properly merged before deleting. If the branch has not been integrated, Git will normally refuse. Do not switch to <code>-D</code> unless you have confirmed that unmerged commits are no longer needed.

### Locking and unlocking a worktree

If a worktree is located on a removable drive or network location that may be temporarily unavailable, you can lock it:

~~~bash
git worktree lock --reason "External drive temporarily offline" ../payment-review
~~~

Locking prevents Git from treating an absent worktree as a directory eligible for cleanup during pruning. When the location is ready again, unlock it:

~~~bash
git worktree unlock ../payment-review
~~~

You can view lock status with <code>git worktree list</code>; the lock reason may be displayed alongside the path.

## 12. Pruning metadata of worktrees that no longer exist

If a linked worktree directory is deleted manually via File Explorer or a system tool, the metadata in the repository may still remain. Git may mark that worktree as prunable.

Check first:

~~~bash
git worktree list --porcelain
git worktree prune --dry-run --verbose
~~~

If the list only contains orphaned metadata that you confirm is no longer needed, run:

~~~bash
git worktree prune --verbose
~~~

<code>prune</code> cleans up invalid worktree management metadata; it is not a command to delete an existing worktree, nor does it delete a local branch just because that branch was once checked out in that worktree. Git has an expiration grace period before pruning old metadata, so an entry that has just become prunable might not be cleaned up immediately. If you have confirmed the worktree directory was permanently deleted and want to test immediate cleanup, you can use <code>--expire now</code> after the dry-run step:

~~~bash
git worktree prune --dry-run --verbose --expire now
git worktree prune --verbose --expire now
~~~

Do not run prune when a worktree is only temporarily unreachable, such as an unmounted external drive or an offline network directory. In that case, lock the worktree before the location disappears or wait until it becomes accessible again.

## 13. Moving or repairing a worktree

If you need to move a linked worktree to a new path, prefer the command:

~~~bash
# Ensure the destination parent directory already exists
git worktree move ../payment-review ../reviews/payment-review
~~~

Git updates the metadata so the worktree continues to be recognized at the new location. Do not use this command to move the main worktree; follow Git's guidance for the main directory case.

If the directory was moved manually and the metadata no longer matches, Git provides:

~~~bash
git worktree repair
~~~

The repair command fixes metadata links in cases where the worktree path or main repository path has changed. For specific situations, inspect <code>git worktree list</code> and Git's messages before running repair; avoid manually editing internal management files under <code>.git/worktrees</code>.

## 14. How do worktree and clone differ?

Both worktree and clone can create an additional directory to work in, but their purpose and storage differ.

| Criterion | git worktree | git clone |
|---|---|---|
| Git history data | Shares the original repository's object database | Has its own object database, usually downloading history from a remote |
| Local references | Branches and tags are shared in the repository | Independent local branches in the clone |
| HEAD and index | Separate for each worktree | Separate in the clone |
| Remotes and fetch | Shares repository configuration and refs | Has its own remote configuration and refs |
| Goal | Multiple working directories for the same repository | Creating an independent clone, suitable for collaboration or isolated environments |
| Initial disk usage | Usually economical since it does not duplicate the object database | Can be larger due to having its own Git data store |

Choose worktree when you want to do multiple tasks in parallel within the same repository and accept sharing branch refs. Choose clone when you need a more independent environment, such as testing different Git configurations, working with a different fork, or isolating permissions and repository data.

## 15. Considerations when using worktrees with IDEs and build tools

Each worktree is a separate project directory, so you can open multiple IDE windows at the same time. This is convenient for reviews and parallel development, but there are a few points to manage:

- **Dependencies and caches:** each directory may need to install dependencies or create its own cache, depending on the tool. Some tools use a shared cache outside the repository.
- **Build output:** avoid configuring two worktrees to write to the same output directory outside the project tree.
- **Ports and services:** two applications running in parallel need different ports or separate environment configurations.
- **Local config files:** if a file is ignored and each worktree needs its own configuration, create the corresponding configuration in each directory.
- **IDE metadata:** some IDEs store workspace state by project path; opening a new worktree may create a separate configuration.
- **Path-dependent scripts:** scripts that use absolute paths from the main worktree may not run properly in a secondary worktree.

Worktrees separate the working tree and index, but they do not automatically isolate every resource an application uses. Check databases, containers, network ports, and temporary directories when running multiple instances at once.

## 16. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Cannot check out the same branch in a new worktree | The local branch is already checked out in another worktree | Use a new branch or detached HEAD; do not force with <code>--force</code> without understanding the impact |
| <code>git worktree add</code> reports path already exists | The destination already has contents or mismatched metadata | Choose a new path, or carefully inspect the existing directory before proceeding |
| Worktree shows prunable status | The directory was moved or deleted outside of Git | Verify the path; use <code>repair</code> or <code>prune</code> as appropriate |
| <code>git worktree remove</code> refuses | The worktree has changes, untracked files, or is locked | Check status, save needed data, unlock if appropriate, then remove |
| Worktree removed but branch still exists | Removing a worktree does not delete the local branch | Use <code>git branch -d</code> after confirming the branch is no longer needed |
| Commits in one worktree appear in another worktree | Worktrees share branch refs and the object database | This is normal behavior; verify the active branch and HEAD in each directory |
| Edited files are not visible in another worktree | Working trees and indexes are separate | Each worktree only displays files from its own checkout; integrate changes via commit/merge/rebase |
| Prune is about to remove metadata for an offline drive | Git cannot see the worktree path | Lock the worktree before it goes temporarily offline or wait until the path is accessible again |

## 17. Safe workflow for using worktrees

A workflow you can apply for each parallel task:

1. Identify the base branch and update remote-tracking refs with fetch.
2. Choose a separate worktree path that is easy to identify by purpose.
3. Create the worktree with a new branch, an unused existing branch, or detached HEAD.
4. Check <code>git status</code> and <code>git branch --show-current</code> in the new directory.
5. Work, run tests, and commit as usual.
6. Push or integrate commits according to the team's collaboration workflow.
7. Confirm there are no remaining changes or commits to keep before removing the worktree.
8. Use <code>git worktree remove</code>; only delete the separate branch after confirming the branch has been integrated.
9. Use <code>git worktree list</code> to check which worktrees remain in the repository.

General inspection commands:

~~~bash
git worktree list --porcelain
git branch -vv
git status
~~~

When an issue occurs, preserve directories that still contain needed data and inspect the status before using <code>remove</code>, <code>prune</code>, or <code>--force</code>.

## 18. Self-check exercises

Practice in a test repository:

1. From the main worktree, run <code>git worktree list</code> and note the path along with the current branch.
2. Create a new linked worktree for the <code>hotfix/demo</code> branch from <code>main</code> using <code>git worktree add -b</code>.
3. Open the new directory, make a change, and commit. Return to the main worktree and check whether the branch and history show that commit.
4. Try creating a second worktree for the same checked-out branch. Observe Git's refusal and explain this limitation.
5. Create a detached worktree at an older commit, run tests, then switch to an investigation branch if you want to keep new commits.
6. Run <code>git worktree list --porcelain</code> and distinguish between worktrees on a branch and detached worktrees.
7. Remove a linked worktree after saving changes. Check why the local branch still remains.
8. Create a test worktree directory and delete the directory using an OS tool. Use <code>git worktree prune --dry-run</code> to see the metadata that can be cleaned up.
9. Lock and unlock a test worktree; observe the status information in the list.
10. Explain why worktree is more suitable than clone when handling a parallel hotfix while still sharing a repository.

When you understand that each worktree has its own working tree, index, and HEAD while sharing Git data and branch refs, you can handle multiple tasks in parallel without constantly stashing or switching branches in one directory. Create worktrees with a clear purpose, check status before cleaning up, and preserve any needed commits or local changes.

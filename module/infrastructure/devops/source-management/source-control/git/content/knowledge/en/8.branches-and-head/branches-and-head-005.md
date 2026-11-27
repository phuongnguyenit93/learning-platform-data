# Attached HEAD and Detached HEAD State

HEAD is a special reference name that indicates which commit Git is currently positioned at in the repository. In a normal workflow, HEAD is attached to a local branch such as main or feature/login. In that state, new commits advance the current branch. However, you can also check out a commit, tag, or remote-tracking branch directly; in that case, HEAD points straight to the commit and Git is in the detached HEAD state.

Detached HEAD is not an error. It is a useful state when you need to inspect an old version, test a specific commit, investigate a regression, or have CI check out an exact commit. What you need to understand is that commits created while in detached HEAD do not automatically update any branch. If you want to keep that work long-term, create a branch before leaving the commit.

## 1. What Is HEAD?

Git stores history as commits with parent-child relationships. A local branch is a named reference pointing to the tip commit of a branch. HEAD indicates the current working position of the repository.

When you are on the main branch, the conceptual structure is:

~~~text
HEAD
  |
  v
refs/heads/main
  |
  v
commit C
~~~

HEAD does not normally store a commit hash directly when attached to a branch. It is a symbolic ref pointing to a branch name, such as refs/heads/main. That branch in turn points to the current commit.

Inside the Git directory, the contents of .git/HEAD in this state typically look like:

~~~text
ref: refs/heads/main
~~~

The .git path can be a directory or a file pointing to the Git directory, such as in a linked worktree. Use Git commands to query it rather than relying on the physical location of metadata.

## 2. HEAD and the Branch Move Together When Committing

Suppose main points to commit C and you check out the main branch:

~~~text
      HEAD
        |
        v
main -> C
~~~

After creating a new commit D, Git updates the main branch to point to D. Because HEAD remains attached to main, HEAD's position also resolves to commit D:

~~~text
HEAD
  |
  v
main -> D
         |
         v
         C
~~~

Therefore, when on a normal branch, you do not have to move HEAD manually after each commit. Git updates the current branch ref and the symbolic HEAD continues pointing to that branch.

Check the current position:

~~~bash
git status -sb
git branch --show-current
git rev-parse HEAD
~~~

git branch --show-current prints the name of the currently checked-out local branch. git rev-parse HEAD prints the object ID of the commit that HEAD resolves to.

## 3. Checking Which Branch HEAD Is Attached To

Use git symbolic-ref:

~~~bash
git symbolic-ref HEAD
~~~

When attached to main, the output is:

~~~text
refs/heads/main
~~~

This command asks Git for the symbolic ref that HEAD points to. If HEAD is detached, the command normally returns a non-zero exit code because HEAD is no longer a symbolic ref to a branch.

You can view the short branch name:

~~~bash
git branch --show-current
~~~

If the output is empty, you may be in detached HEAD or the repository may not have a checked-out branch yet, such as before the first commit. Therefore, combine this with git status and git symbolic-ref to determine the exact state.

View the current commit and related branches:

~~~bash
git log -1 --oneline --decorate
git show-ref --heads
~~~

git show-ref --heads lists local branches and their object IDs. HEAD may be pointing to a commit that no branch currently points to directly.

## 4. Switching Branches with git switch

When switching to an existing branch:

~~~bash
git switch main
~~~

Git updates HEAD to be a symbolic ref to refs/heads/main and updates the working tree/index to reflect that branch's snapshot, within safe limits regarding existing local changes.

Create a new branch and switch to it:

~~~bash
git switch -c feature/inventory-search
~~~

This command is equivalent in purpose to creating a branch and then checking it out:

~~~bash
git branch feature/inventory-search
git switch feature/inventory-search
~~~

After switching branches, verify:

~~~bash
git branch --show-current
git symbolic-ref HEAD
git status -sb
~~~

The branch name appears in git branch --show-current, while the symbolic ref is typically refs/heads/feature/inventory-search.

## 5. What Is Detached HEAD?

Detached HEAD occurs when HEAD points directly to a commit instead of pointing to a branch name. For example:

~~~text
HEAD -> commit C

main -> commit D
~~~

HEAD is at commit C, while the main branch still points to commit D. No local branch is moved just because you checked out C.

In .git/HEAD, this state is normally represented by the commit's object ID instead of a ref line:

~~~text
<commit-id>
~~~

Detached HEAD commonly happens when checking out:

- A commit by hash.
- A release tag.
- A remote-tracking branch such as origin/main.
- A revision expression such as HEAD~2.

Git displays this state in git status, usually with a message similar to HEAD detached at ...

## 6. Intentionally Checking Out a Commit to Inspect

For example, inspect the state of the commit prior to the current branch:

~~~bash
git switch --detach HEAD~1
~~~

Or check out a specific commit:

~~~bash
git switch --detach a1b2c3d
~~~

You can read files, run tests, or build at that version without moving the main branch. This is a useful way to identify which commit introduced a bug or to verify an old build.

Verify:

~~~bash
git status -sb
git branch --show-current
git rev-parse HEAD
git symbolic-ref HEAD
~~~

When detached, git branch --show-current normally prints no branch name and git symbolic-ref HEAD fails. git rev-parse HEAD still returns the commit ID currently checked out.

The older command git checkout <commit> can also put the repository into detached HEAD. The git switch --detach syntax clearly expresses the intent to change position without checking out a branch.

## 7. Checking Out a Tag Also Typically Creates Detached HEAD

Tags are typically used to mark a specific version. When you want to view the exact contents at a tag:

~~~bash
git switch --detach v1.4.0
~~~

Git checks out the commit that the tag resolves to. If the tag is an annotated tag, Git peels the tag object to get the target commit. HEAD becomes detached at that commit.

This is the intended behavior when you only need to view or test a release. If you intend to develop a patch from this version, create a new branch instead of continuing to commit in detached state without a branch name holding it.

## 8. Checking Out a Remote-Tracking Branch

A remote-tracking branch such as origin/main is a local ref recording the state of the main branch on the remote at the most recent fetch. It is not a local branch for working on directly.

To inspect the exact commit present on a remote-tracking ref:

~~~bash
git fetch origin
git switch --detach origin/main
~~~

The first command updates remote information. The second checks out the commit that origin/main points to and creates a detached HEAD state.

If you want to continue working on a local branch tracking the remote, create a local branch with an upstream:

~~~bash
git switch --track origin/main
~~~

Or specify the local branch name:

~~~bash
git switch -c main --track origin/main
~~~

If the local main branch already exists, use git switch main to switch to that branch; do not create a duplicate branch name.

## 9. Committing While in Detached HEAD

Git still allows committing in detached state if the working tree and index are valid:

~~~bash
git switch --detach HEAD~1
# edit file
git add src/main/App.java
git commit -m "test: inspect behavior on previous revision"
~~~

A new commit is created with the current commit as its parent. HEAD moves to the new commit, but no local branch automatically updates to point to that commit.

Diagram before and after commit:

~~~text
Before commit:                 After commit:

main -> D                     main -> D
         |                             |
         C  <- HEAD                   C
                                      |
                                      E  <- HEAD
~~~

Commit E exists in the object database and is referenced by HEAD while you are still there. If you later switch to another branch, no branch holds E unless you created a new ref. The reflog usually helps find it again for a period of time, but an unnamed commit may eventually be reclaimed by garbage collection.

## 10. Keeping a Detached Commit by Creating a Branch

If you want to continue developing or keep the commit you just created, create a branch at the current position:

~~~bash
git switch -c fix/legacy-behavior
~~~

This command creates the fix/legacy-behavior branch pointing to the commit where HEAD stands and simultaneously switches HEAD to the new branch.

Diagram after creating the branch:

~~~text
fix/legacy-behavior -> E <- HEAD
                       |
                       C
                       |
                       ...

main ----------------> D
~~~

Commit E is now retained by the new branch. You can continue committing, pushing the branch, or opening a pull request according to your team's workflow.

If you have not created any commits yet and simply want to start developing from the current detached commit, git switch -c <branch> is also a safe way to name the starting point.

## 11. Recovering a Commit After Leaving Detached HEAD

Suppose you created commit E while detached, then switched to main and forgot to create a branch. You can use the reflog to locate the previous HEAD position:

~~~bash
git reflog --date=local
~~~

The reflog records local ref updates, including HEAD movements during checkout and commit. Look for the line with the commit message or hash of the detached commit.

Once you have identified the right commit, create a branch to rescue it:

~~~bash
git switch -c rescue/detached-work <commit-id>
~~~

Or use a reflog expression after verifying the exact entry:

~~~bash
git switch -c rescue/detached-work HEAD@{2}
~~~

The number in HEAD@{2} is only an example; reflog positions change based on actual operations. Read git reflog and substitute the right entry rather than copying the illustrative index verbatim.

The reflog is a local mechanism, is not pushed as part of normal branch history, and can be pruned according to expiry/garbage collection policies. Once you recover a commit you need to keep, create a branch or tag so it has a stable ref.

## 12. Distinguishing HEAD, Local Branches, Remote-Tracking Branches, and Tags

| Name | Ref type | Role |
|---|---|---|
| HEAD | Pseudoref; usually a symbolic ref or detached object ID | Current position of the repository/worktree |
| refs/heads/main | Local branch | Local branch name, usually moves when committing on that branch |
| refs/remotes/origin/main | Remote-tracking branch | Records the remote branch state at the most recent fetch |
| refs/tags/v1.4.0 | Tag ref | Marks an object, usually a release commit |

These refs can all help Git locate a commit, but their meanings and update behaviors differ. Checking out origin/main or v1.4.0 normally creates detached HEAD; checking out main attaches HEAD to the local branch main.

## 13. Inspecting HEAD and Refs with Git Commands

Some useful commands:

~~~bash
git rev-parse HEAD
git symbolic-ref HEAD
git rev-parse --symbolic-full-name HEAD
git branch --show-current
git show-ref --heads
git show-ref --tags
~~~

- git rev-parse HEAD prints the current commit ID.
- git symbolic-ref HEAD prints the symbolic target if HEAD is attached to a ref.
- git rev-parse --symbolic-full-name HEAD displays the full ref name when a symbolic ref can be resolved.
- git branch --show-current prints the current local branch name; detached HEAD usually gives empty output.
- git show-ref --heads lists local branches.
- git show-ref --tags lists tag refs.

To view the HEAD file path directly, you can use:

~~~bash
git rev-parse --git-path HEAD
~~~

This command returns the location of the HEAD file relative to the current Git directory. In a standard repository, it is .git/HEAD; in a linked worktree, the path may lie under the worktree administration directory. Prefer Git commands for querying because they handle both cases.

## 14. HEAD in a Repository Before the First Commit

After git init, Git may already set HEAD as a symbolic ref to the initial branch, such as refs/heads/main, even though the branch ref does not yet exist because the repository has no commits.

This is an unborn branch state, not detached HEAD. Some commands such as git branch --show-current still print main, while git rev-parse HEAD cannot resolve a commit yet.

After the first commit, the main branch is created and points to the new commit. Distinguishing an unborn branch from detached HEAD helps avoid misdiagnosis right after a repository is initialized.

## 15. Independent HEAD in a Linked Worktree

Git worktrees allow one repository to have multiple working trees. Each worktree has its own HEAD position so different branches or commits can be checked out simultaneously.

Example:

~~~bash
git worktree add ../inventory-hotfix -b hotfix/1.4
~~~

The main worktree can be on main, while ../inventory-hotfix has HEAD attached to hotfix/1.4. Both worktrees share the object database and certain metadata, yet each worktree maintains its own checkout state.

Verify:

~~~bash
git worktree list
git -C ../inventory-hotfix status -sb
git -C ../inventory-hotfix symbolic-ref HEAD
~~~

Do not assume every worktree shares a single physical .git/HEAD file. Use git -C or run commands from the corresponding worktree to inspect that workspace's HEAD.

## 16. Operations That Easily Cause Confusion

- **Checking out a hash and committing without creating a branch:** the new commit is not updated onto any local branch; create a branch right away if you want to keep the work.
- **Mistaking detached HEAD for an error:** it is a valid state when inspecting a specific commit or tag.
- **Assuming commits in detached HEAD are lost immediately:** the commits still exist and the reflog usually records them, but a ref is needed to keep them permanently.
- **Checking out origin/main to develop directly:** a remote-tracking ref is not a local branch; use git switch --track origin/main or create a local branch.
- **Assuming tags move with commits:** a tag is a separate ref, typically used as an immutable milestone; creating new commits does not automatically move a tag.
- **Seeing empty output from git branch --show-current and concluding the repository has no branches:** you might be detached or in another state; check git status and git symbolic-ref HEAD.
- **Using HEAD@{n} without reading the reflog:** the index depends on HEAD movement history; verify the entry before creating a rescue branch.
- **Confusing an unborn branch with detached HEAD:** a repository without a first commit yet can still have a symbolic HEAD pointing to a branch that does not exist yet.

## 17. Safe Workflow When Inspecting an Old Commit

1. Check the current working tree status:

   ~~~bash
   git status -sb
   ~~~

2. If there are local changes, commit, stash, or back them up as needed before switching positions.
3. Find the commit to inspect:

   ~~~bash
   git log --oneline --decorate --all
   ~~~

4. Check out the commit in detached mode:

   ~~~bash
   git switch --detach <commit-id>
   ~~~

5. Build/test and observe behavior on that revision.
6. If you create changes you need to keep, create a branch at the current commit:

   ~~~bash
   git switch -c investigate/fix-from-old-revision
   ~~~

7. If you are done inspecting, return to your working branch:

   ~~~bash
   git switch main
   ~~~

8. Confirm the branch and status:

   ~~~bash
   git status -sb
   git branch --show-current
   ~~~

If you forgot to create a branch and already left detached HEAD, use git reflog to find the commit and create a rescue branch as in section 11.

## 18. Takeaways

When HEAD is attached to a branch, it is a symbolic ref to the branch name and new commits advance that branch. When checking out a commit, tag, or remote-tracking ref directly, HEAD points straight to the commit in detached state. You can still read, build, test, and commit; new commits only move HEAD and do not automatically update any branch. Create a branch with git switch -c to keep the work, or use the reflog to recover a detached commit if you have already left it. Always distinguish local branches, remote-tracking branches, tags, detached HEAD, and unborn branches before deciding your next operation.

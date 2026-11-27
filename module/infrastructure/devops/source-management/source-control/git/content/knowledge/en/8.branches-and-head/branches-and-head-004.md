# Creating a New Branch from an Existing Commit or Branch

In Git, creating a new branch means creating a new named reference pointing to an existing commit. You can start a branch from the current commit, the tip of another branch, an older commit, a release tag, or a remote-tracking branch. The starting point determines the history that the new branch inherits.

Creating a branch and switching to that branch are two distinct operations. The git branch command creates a reference while keeping HEAD unchanged; git switch -c both creates the branch and switches HEAD and the working tree to the new branch. Understanding this difference helps avoid creating a branch at the wrong commit or continuing to make edits on the old branch.

## 1. A Branch Is a Reference to a Commit

A branch in Git is not a copy of a source code directory. A branch is a ref usually located in the refs/heads/ namespace and pointing to the tip commit of a line of development.

Example:

~~~text
A---B---C  main
     \
      D---E  feature/report
~~~

In the graph above:

- main points to commit C.
- feature/report points to commit E.
- Both branches share history up to commit B.
- The feature/report branch was created from commit B, and then gained its own commits D and E.

When creating a branch from main at the moment main points to C, the new branch also points to C. Later, when main advances to D or E, the new branch does not automatically move along with it. The two refs are independent and only point to the same commit at the time of creation.

### 1.1. Viewing the Current Branch and Commit

~~~sh
git status -sb
git branch --show-current
git branch --list
git log --oneline --decorate --graph --all
~~~

These commands show the current branch, the list of local branches, and how commits are linked. If you want to see the exact ref along with its object ID:

~~~sh
git show-ref --heads
git rev-parse HEAD
~~~

The current branch is usually identified by an asterisk in git branch. HEAD indicates the current checkout position and is typically a symbolic ref pointing to that branch.

## 2. Choosing a Start Point Before Creating a Branch

Branch creation commands take an optional start-point. A start-point can be:

- HEAD or a local branch name.
- A remote-tracking branch name such as origin/main.
- A commit SHA.
- A tag pointing to a commit.
- A revision expression such as HEAD~2 or main^.

If no start-point is specified, Git uses the current HEAD.

### 2.1. Creating from the Current HEAD

~~~sh
git branch feature/report
~~~

This command creates the feature/report branch at the commit that HEAD currently points to. HEAD does not change; you are still on the old branch.

To create and switch to the new branch immediately:

~~~sh
git switch -c feature/report
~~~

This is the usual way when starting new work from the current branch.

### 2.2. Creating from an Existing Local Branch

Suppose the repository has main and you want to create feature/search from the current tip of main:

~~~sh
git branch feature/search main
~~~

This command creates the feature/search ref pointing to the same commit that main points to. It does not switch branches.

If you want to create and switch to the new branch:

~~~sh
git switch -c feature/search main
~~~

After the command, HEAD points to feature/search and the working tree is updated to match the branch's starting commit.

### 2.3. Creating from a Specific Commit

When you need to start a branch from an older milestone, use a commit SHA:

~~~sh
git log --oneline --decorate -10
git branch hotfix/report-timeout <commit-sha>
git switch hotfix/report-timeout
~~~

Or create and switch in one command:

~~~sh
git switch -c hotfix/report-timeout <commit-sha>
~~~

The new branch points to the chosen commit, even if that commit is not the tip of the current branch. Commits that are descendants of the start point do not automatically appear in the new branch.

### 2.4. Creating from a Revision Expression

You can select a commit using relative expressions:

~~~sh
git switch -c experiment/previous-release main~2
git switch -c hotfix/parent HEAD^
~~~

- main~2 is the commit two steps back from the tip of main along the first-parent chain.
- HEAD^ is the first parent of the commit that HEAD points to.

For merge commits, ^ and ~ have different meanings. If you need to select a specific parent, use HEAD^1 or HEAD^2. Verify the commit before creating the branch:

~~~sh
git show --no-patch --oneline main~2
git rev-parse main~2
~~~

## 3. Creating a Branch from a Release Tag

A tag usually marks a stable version. When you need to fix a bug in a released version, you can create a hotfix branch from a tag pointing to a commit:

~~~sh
git tag --list
git show --no-patch v2.4.0
git switch -c hotfix/2.4.1 v2.4.0
~~~

The hotfix/2.4.1 branch starts at the commit referenced by the v2.4.0 tag. The tag remains unchanged; the new branch can advance as you create fix commits.

Before using a tag, verify which commit the tag points to:

~~~sh
git rev-parse "v2.4.0^{commit}"
~~~

A branch requires a commit as its start point. If a tag points to another object type rather than a commit, that revision is not a suitable start-point.

## 4. Creating a Branch from a Remote-Tracking Branch

A remote-tracking branch such as origin/main is a local ref recording the state of the branch on the remote at the most recent fetch. It is a useful start point when creating a working branch from a shared branch.

First update remote information:

~~~sh
git fetch origin
git branch --remotes
git log --oneline --decorate -5 origin/main
~~~

Create a local branch from origin/main:

~~~sh
git switch -c feature/audit origin/main
~~~

This command creates the local branch feature/audit at the commit that origin/main points to and switches to the new branch. To explicitly set an upstream for convenient pull/push, use the --track option:

~~~sh
git switch --track -c feature/audit origin/main
~~~

You can create the ref first and switch later:

~~~sh
git branch --track feature/audit origin/main
git switch feature/audit
~~~

Verify the upstream:

~~~sh
git branch -vv
git status -sb
~~~

The output usually shows feature/audit tracking origin/main. The upstream is a link configuration so Git knows which branch to use by default when fetching, pulling, or pushing according to configuration.

### 4.1. A Start Point Is a Snapshot, Not a Live Link

When creating feature/audit from origin/main, the local branch receives the commit that origin/main pointed to at creation time. When others push new commits to main, the local branch does not automatically update.

Run fetch to update the remote-tracking ref:

~~~sh
git fetch origin
git log --oneline --decorate --graph feature/audit..origin/main
~~~

Afterward, you decide whether to merge or rebase the new changes into your working branch according to your team's workflow. Do not confuse an upstream with the local branch moving automatically with the remote.

## 5. Creating a Branch Without Switching Branches

Sometimes you want to prepare a branch in advance, while continuing to work on the current branch. Use git branch:

~~~sh
git branch feature/documentation main
git branch --list
git status -sb
~~~

HEAD stays on the current branch. The new branch is simply another ref pointing to main's commit at the time of creation.

When ready to switch:

~~~sh
git switch feature/documentation
~~~

Verify:

~~~sh
git branch --show-current
git rev-parse HEAD
~~~

### 5.1. Comparing Branch Creation Commands

| Command | Creates branch | Moves HEAD | Working tree |
|---|---|---|---|
| git branch name | Yes | No | Unchanged |
| git branch name start-point | Yes | No | Unchanged |
| git switch -c name | Yes | Yes | Checks out new branch |
| git switch -c name start-point | Yes | Yes | Checks out from start-point |
| git checkout -b name start-point | Yes | Yes | Checks out from start-point |

git checkout -b is the traditional syntax combining branch creation and checkout. For newer workflows, git switch usually expresses branch-switching intent more clearly.

## 6. Checking a Branch Name Before Creating It

The branch name becomes part of a ref. Use short, meaningful names that follow team conventions.

Examples:

~~~text
feature/user-search
bugfix/login-timeout
hotfix/2.4.1
release/3.0
experiment/new-index
~~~

Check whether a name is valid:

~~~sh
git check-ref-format --branch feature/user-search
~~~

Some rules:

- Do not use spaces in branch names.
- Avoid names containing .. or special characters forbidden by Git.
- Do not end a name with a dot or .lock.
- Do not begin with a slash or end with a slash.
- Use lowercase letters and hyphens or slashes according to team conventions.

Before creating, check whether the branch already exists:

~~~sh
git branch --list feature/user-search
git show-ref --verify refs/heads/feature/user-search
~~~

If the name already exists, choose another name or confirm clearly whether the existing branch is the one you need to use.

## 7. Creating a Branch When the Working Tree Has Changes

Git can preserve certain uncommitted changes when you switch branches if they do not conflict with contents on the target branch. However, relying on that behavior when creating branches can cause confusion: in-progress changes might be carried over and later committed to the wrong branch.

Before starting:

~~~sh
git status -sb
git diff
git diff --cached
~~~

If the changes belong to new work, the clean approach is to create the branch first and then continue editing:

~~~sh
git switch -c feature/new-export
~~~

If changes were already made on another branch, decide whether to commit, stash, or transfer them according to your team's workflow before switching branches.

### 7.1. Creating a Branch Does Not Automatically Stage or Commit

The git branch command only creates a ref. It does not add files to the index and does not create a commit.

The git switch -c command can update the working tree to match the start point, yet it also does not automatically commit unsaved changes. After switching, inspect:

~~~sh
git status --short
git diff
git diff --cached
~~~

Do not use switch as a way to save changes. Commit or stash when you need to preserve working state.

## 8. Branching from an Old Commit and Detached HEAD

When checking out a commit directly with git switch --detach, HEAD does not point to a local branch but points directly to the commit. This state is called detached HEAD.

~~~sh
git switch --detach <commit-sha>
git status -sb
~~~

Detached HEAD is useful when inspecting a version or testing old history. If you create commits in this state, the new commits are not yet retained by a normal branch. You can create a branch right at the current position to continue developing:

~~~sh
git switch -c experiment/from-old-commit
~~~

This command creates a new branch pointing to the current commit and moves HEAD to that branch. If you want to create a branch from an old commit without entering detached HEAD, use directly:

~~~sh
git switch -c experiment/from-release <commit-sha>
~~~

## 9. When a Branch Already Exists

Normal branch creation commands refuse if the name is already taken:

~~~sh
git branch feature/report
~~~

If feature/report exists, Git reports an error to avoid unintentionally moving a ref.

Before acting, check:

~~~sh
git branch -vv
git log --oneline --decorate feature/report -5
~~~

If the goal is simply to continue working on that branch:

~~~sh
git switch feature/report
~~~

If you need to create a new branch, use a name that does not exist yet. Avoid using a force option just to bypass a duplicate-name error.

### 9.1. Being Careful with -f and -C

git branch -f can move an existing branch to a different start-point. git switch -C can create a branch or reset an existing branch and switch to it. These operations rewrite a branch's position, which can cause its current commit to no longer be referenced by that branch.

Only use them after checking:

- Whether the branch is currently in use in another worktree.
- Whether the old commit is retained by another ref.
- Whether there are uncommitted changes in the working tree.
- Whether moving the ref would lose track of commits the team needs.

Syntax examples:

~~~sh
git branch -f feature/report <new-start-point>
git switch -C experiment/retry <start-point>
~~~

Do not run these commands as a workaround for a duplicate-name error. Determine first why the branch already exists and whether you have permission to move it. Git also refuses some force operations on a branch checked out in another worktree.

## 10. Verifying the New Branch Was Created Correctly

After creating a branch, check its name, commit, and historical relationships:

~~~sh
git branch --show-current
git branch -vv
git rev-parse HEAD
git log --oneline --decorate --graph --all -15
~~~

If you used git branch name start-point and have not switched branches yet, inspect the new ref:

~~~sh
git rev-parse refs/heads/feature/report
git show --no-patch --oneline feature/report
~~~

Compare with the starting point:

~~~sh
git rev-parse main
git rev-parse feature/report
~~~

If the branch was just created from main and has no new commits yet, the two SHAs must match at the time of inspection. If main has moved since creation, compare against the recorded start-point commit rather than expecting the two refs to always remain identical.

## 11. Sample Workflow: Creating a Feature Branch from main

Suppose a team is developing a user search feature. Work needs to start from the latest main.

**Step 1 — update and inspect main**

~~~sh
git switch main
git status -sb
git fetch origin
git log --oneline --decorate -5 origin/main
~~~

If the workflow requires updating local main, integrate origin/main according to the team's policy before creating the branch.

**Step 2 — create a branch from the selected start point**

~~~sh
git switch -c feature/user-search origin/main
~~~

This command creates a new branch at the commit referenced by origin/main and switches to that branch. If you want to set the upstream immediately, use:

~~~sh
git switch --track -c feature/user-search origin/main
~~~

**Step 3 — verify**

~~~sh
git status -sb
git branch -vv
git log --oneline --decorate -3
~~~

**Step 4 — develop**

Edit source code, run tests, stage relevant changes, and create a commit:

~~~sh
git add src/user-search/
git commit -m "feat(search): add user search endpoint"
~~~

**Step 5 — inspect the branch**

~~~sh
git log --oneline --decorate main..HEAD
git status -sb
~~~

When ready to share the branch to the remote, push according to team conventions. Creating a local branch does not automatically create a branch on the remote.

## 12. Sample Workflow: Creating a Hotfix from an Old Release Commit

Suppose version v2.4.0 has been released and the team needs to fix a bug that only appears in that version.

**Step 1 — verify the tag**

~~~sh
git show --no-patch --oneline v2.4.0
git rev-parse "v2.4.0^{commit}"
~~~

**Step 2 — create the hotfix branch**

~~~sh
git switch -c hotfix/2.4.1 v2.4.0
~~~

**Step 3 — verify the start point**

~~~sh
git log --oneline --decorate -5
git rev-parse HEAD
~~~

HEAD must match the commit referenced by the v2.4.0 tag. Newer commits on main do not automatically appear in this hotfix branch.

**Step 4 — fix the bug and commit**

~~~sh
git add src/
git commit -m "fix: handle report timeout in 2.4"
~~~

After testing and releasing, the team can merge or cherry-pick the hotfix into the main development branch according to the release policy.

## 13. Common Errors

**Created a branch but still on the old branch.**

- If using git branch, this is expected behavior.
- Use git switch <name> to switch to the new branch.

**Branch was created from the wrong commit.**

- Check the start-point in the command.
- Use git show or git rev-parse to verify the commit.
- Recreate the branch under a different name if the current branch has already been shared or has new commits.

**Git reports that the branch already exists.**

- Run git branch -a and git branch -vv.
- Check whether it is a local branch or a remote-tracking ref.
- Use the existing branch if it matches your goal; otherwise, choose a new name.

**Cannot find origin/main.**

- Check remotes with git remote -v.
- Run git fetch origin.
- Confirm the remote has a main branch and an appropriate fetch refspec.

**Branch switch refused due to local changes.**

- Read git status.
- Commit or stash changes if needed.
- Do not use force discard before determining which contents need to be kept.

**New branch does not automatically update with the source branch.**

- A branch only points to the source commit at creation time.
- Fetch and merge/rebase when you need to integrate new commits.

**Created commits in detached HEAD.**

- Run git switch -c <new-branch> to retain the current commit with a new branch.
- Verify the SHA and log after switching.

## 14. Branch Creation Checklist

**Before creating**

- [ ] Identified the correct repository and current branch.
- [ ] Checked the working tree and index.
- [ ] Selected the start-point: HEAD, branch, commit, tag, or remote-tracking ref.
- [ ] Fetched the remote if the start-point is a branch on the remote.
- [ ] Verified the branch name is valid and unused.

**When creating**

- [ ] Used git branch if only creating a ref.
- [ ] Used git switch -c if creating and switching branches.
- [ ] Used --track if configuring an upstream for a remote branch.
- [ ] Did not use force without verifying the impact.

**After creating**

- [ ] Confirmed the current branch.
- [ ] Checked the commit SHA of the start point.
- [ ] Viewed the graph to confirm historical relationships.
- [ ] Confirmed upstream if the branch tracks a remote.
- [ ] Checked that the working tree has no unexpected changes.

## 15. Self-Assessment Questions

1. What does a branch in Git store and what type of object does it point to?
2. What is the difference between git branch feature/x and git switch -c feature/x?
3. When creating a branch from main, if main advances afterward, does the new branch move automatically?
4. How do you create a branch from an old commit SHA?
5. When should you create a branch from a release tag?
6. How does a remote-tracking branch like origin/main differ from a local branch?
7. What does the --track option configure?
8. Why should you inspect the working tree before switching branches?
9. What is detached HEAD and how do you keep commits created in that state?
10. Why should you be cautious with git branch -f and git switch -C?

## 16. Conclusion

Creating a branch means selecting a commit as a start point and creating a new ref pointing to that commit. The start-point can be HEAD, a local branch, a specific commit, a tag, or a remote-tracking branch. The start point determines the inherited history; after creation, the new branch and the source branch move independently.

Distinguish git branch from git switch -c, verify the commit before creating, and inspect the working tree after switching. For branches starting from a remote, fetch first and set up tracking when needed. When you clearly understand these steps, you can create branches for features, hotfixes, or experiments while keeping Git history easy to follow.

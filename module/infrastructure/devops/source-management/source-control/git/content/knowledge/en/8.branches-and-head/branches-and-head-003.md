# Switching Branches with git switch and git checkout

In Git, a branch is a named reference pointing to a commit, and HEAD indicates the current working position. When switching to another branch, Git updates HEAD and synchronizes the working tree and index to match the target branch's snapshot. Two common commands for this operation are `git switch` and `git checkout`.

`git switch` is designed specifically for switching branches or moving HEAD to a commit. `git checkout` is the older command that can switch branches, check out commits, create branches, and restore file contents. Because `git checkout` handles multiple responsibilities, newcomers easily confuse branch-switching syntax with file-restoration syntax. Understanding the differences helps you choose a command with clear intent and avoid accidentally overwriting changes in the working tree.

After this lesson, you will be able to:

- Switch branches using `git switch` and `git checkout`.
- Create a new branch and switch to it at the same time.
- Track a remote branch when switching branches.
- Move to a specific commit and understand the detached HEAD state.
- Handle local changes before switching branches.
- Understand when Git refuses to switch branches due to the risk of overwriting data.
- Distinguish branch checkout syntax from path checkout syntax.
- Use `git restore` for file restoration in modern Git.

## 1. HEAD and the Current Branch

A branch in Git is typically a ref pointing to the latest commit on that branch. HEAD normally points indirectly to the current branch:

~~~text
HEAD
  |
  v
refs/heads/feature/search
  |
  v
commit C3
  |
  v
commit C2
~~~

When you create a new commit on the checked-out branch, the branch ref is updated to point to the new commit and HEAD stays attached to that branch.

Check the current branch:

~~~bash
git branch --show-current
git status --short --branch
~~~

Check HEAD:

~~~bash
git rev-parse --short HEAD
git log -1 --oneline
~~~

When switching branches, Git changes which branch HEAD points to, then updates the index and working tree to match the target snapshot.

## 2. Switching Branches with git switch

Introduced in Git 2.23, `git switch` provides a clearer interface for branch-switching operations. Basic syntax:

~~~bash
git switch main
~~~

This command switches to the branch named `main`. If the branch exists and local changes will not cause data loss, Git updates HEAD, the index, and the working tree.

Switch to a feature branch:

~~~bash
git switch feature/search
~~~

Review status:

~~~bash
git status --short --branch
git branch --show-current
~~~

The branch name must be a valid branch ref. If the branch does not exist, Git reports an error unless you use the option to create a new branch or the automatic remote-branch guessing mechanism.

## 3. Switching Branches with git checkout

Before `git switch` existed, the standard way to switch branches was:

~~~bash
git checkout main
~~~

This command is still supported in modern Git. It performs the branch switch similarly to `git switch main`.

Example:

~~~bash
git checkout feature/search
git status --short --branch
~~~

`git checkout` also supports several other modes such as checking out commits, creating branches, restoring files, or retrieving files from a tree-ish. Therefore, the same command can carry different meanings depending on its arguments.

If the goal is solely to switch branches, `git switch` is usually easier to read and understand. In legacy repositories or scripts, you will still encounter `git checkout` and need to identify its context accurately.

## 4. Comparing switch and checkout

| Need | git switch | git checkout |
| --- | --- | --- |
| Switch to an existing branch | `git switch branch-name` | `git checkout branch-name` |
| Create a new branch and switch to it | `git switch -c new-branch` | `git checkout -b new-branch` |
| Create or reset a branch and switch | `git switch -C branch start-point` | `git checkout -B branch start-point` |
| Move to a specific commit, detached HEAD | `git switch --detach commit` | `git checkout --detach commit` |
| Switch branch and merge local changes if conflicts occur | `git switch --merge branch` | `git checkout -m branch` |
| Restore files from the index or a tree | Path mode not supported | Yes, but syntax is easily confused; modern Git has `git restore` |

The main difference is command scope. `git switch` focuses strictly on moving HEAD between branches or commits. `git checkout` still supports file restoration as well, so it has more syntax forms.

## 5. Creating a New Branch and Switching to It

If the new branch does not exist yet:

~~~bash
git switch -c feature/search
~~~

The `-c` option creates a new branch from the current commit and then switches to it. This is equivalent to:

~~~bash
git branch feature/search
git switch feature/search
~~~

The older approach using checkout:

~~~bash
git checkout -b feature/search
~~~

By default, the new branch starts from the current HEAD unless you specify a start point:

~~~bash
git switch -c feature/search main
~~~

This command creates the `feature/search` branch from `main` and switches to the new branch. The start point can be a valid branch, tag, or commit.

### Recreating an Existing Branch with -C or -B

`-C` in switch and `-B` in checkout can create a new branch or reset an existing branch to the start point and switch to it:

~~~bash
git switch -C feature/search main
~~~

Equivalent to:

~~~bash
git checkout -B feature/search main
~~~

This operation can move an existing branch ref and lose an easy path back to the old commit if no other ref holds that commit. Only use it when you intentionally want to reset the branch. Before running it, inspect the current branch, log, and commits you need to keep.

## 6. Switching to a Remote-Tracking Branch

After fetching, the repository may have remote-tracking branches such as `origin/feature/search`:

~~~bash
git fetch origin
git branch -r
~~~

If you want to create a local branch tracking a remote branch:

~~~bash
git switch --track origin/feature/search
~~~

Git creates the corresponding local branch and configures the upstream so the local branch knows which remote branch it tracks.

You can explicitly specify the local branch name:

~~~bash
git switch --track -c feature/search origin/feature/search
~~~

Equivalent using checkout:

~~~bash
git checkout --track -b feature/search origin/feature/search
~~~

After switching:

~~~bash
git status --short --branch
git branch -vv
~~~

`git branch -vv` displays the upstream of each local branch if configured.

## 7. Auto-Guessing a Branch from a Remote

When entering a branch name that does not exist locally but matches a single remote-tracking branch, Git can automatically create a local branch tracking that remote branch:

~~~bash
git switch feature/search
~~~

If there is only one matching remote branch, Git can create a local branch of the same name and set up tracking. This behavior depends on the branch-guessing configuration and whether there is ambiguity across remotes.

The `--no-guess` option disables guessing:

~~~bash
git switch --no-guess feature/search
~~~

When multiple remote branches share the same name, specify the remote explicitly:

~~~bash
git switch --track origin/feature/search
~~~

Or configure a default remote for branch guessing according to your team's rules. Do not rely on automatic guessing in important scripts if remotes or branch names could be ambiguous.

## 8. Moving to a Specific Commit and Detached HEAD

You can move HEAD to a commit without attaching HEAD to a branch:

~~~bash
git switch --detach a1b2c3d
~~~

Or:

~~~bash
git checkout --detach a1b2c3d
~~~

This is the detached HEAD state. HEAD points directly to a commit instead of pointing to a branch:

~~~text
HEAD
 |
 v
commit B

main ------> commit D
~~~

You can read code, run tests, or create temporary commits in this state. However, new commits are not automatically held by a branch. If you leave detached HEAD and no ref points to that commit, the commit can become unreachable and eventually be cleaned up by garbage collection.

If you want to keep experimental changes, create a branch before leaving:

~~~bash
git switch -c experiment/search
~~~

This command creates a branch at the current commit and attaches HEAD to the new branch. Subsequent commits will be preserved in that branch's history.

## 9. Switching Branches When the Working Tree Has Changes

Git normally allows switching branches if local changes will not be overwritten by the target branch. For example, if you modify a file that does not differ between the two branches, Git can keep those changes when switching branches.

However, if the target branch needs to update the same file in a way that conflicts with local changes, Git normally refuses to switch branches to protect your data.

Check beforehand:

~~~bash
git status
git diff
git diff --cached
~~~

To switch branches safely, there are three common options:

1. Commit the changes if they are complete.
2. Stash the changes if you need to set them aside temporarily.
3. Discard the changes if you are sure you do not need to keep them.

### Commit Before Switching

~~~bash
git add -A
git commit -m "Save current search work"
git switch main
~~~

### Stash Before Switching

~~~bash
git stash push -m "WIP search changes"
git switch main
~~~

When returning to the old branch:

~~~bash
git switch feature/search
git stash list
git stash pop
~~~

`git stash pop` applies the stash and removes the stash entry if it applies cleanly. If you want to keep the stash so it can be reapplied later, use `git stash apply`.

### Reverting Changes

If changes are unstaged and you are certain they do not need to be kept:

~~~bash
git restore --worktree -- src/Search.java
~~~

If changes are staged:

~~~bash
git restore --staged --worktree -- src/Search.java
~~~

The second command reverts both the index and working tree of the file to the default source state, HEAD. Review the diff before using it because local changes may be discarded.

## 10. When Git Refuses to Switch Branches

Example when Git reports that local changes would be overwritten:

~~~text
error: Your local changes to the following files would be overwritten by checkout:
    src/Search.java
Please commit your changes or stash them before you switch branches.
Aborting
~~~

This is a safety mechanism. Git detects that switching to the target branch would write different contents over a file that has local changes.

Resolution workflow:

~~~bash
git status --short
git diff
git diff --cached
~~~

Then choose commit, stash, or restore depending on your goal. Do not try to bypass the message just to finish switching branches if you do not yet know which changes would be overwritten.

## 11. Using --merge to Carry Local Changes to the Target Branch

`git switch --merge` instructs Git to attempt merging local changes with the target branch's contents:

~~~bash
git switch --merge main
~~~

The corresponding option in checkout is:

~~~bash
git checkout -m main
~~~

If there are no conflicts, Git can switch branches and preserve local changes by merging them into the working tree. If there is a conflict, the operation pauses for you to resolve it.

Inspect:

~~~bash
git status
git diff
git diff --cached
git ls-files --unmerged
~~~

After resolving conflicts, stage the result with `git add` and continue working on the target branch. `--merge` does not automatically create a commit.

Only use this when you intentionally want to bring local changes across to the target branch and understand the contents being merged. If the changes are not ready or are hard to separate, stashing is usually easier to manage.

## 12. Forcing a Branch Switch and Risk of Data Loss

`git switch --discard-changes` or its short form `-f` discards local changes that block switching branches:

~~~bash
git switch --discard-changes main
~~~

With checkout, you can use:

~~~bash
git checkout -f main
~~~

These options can discard uncommitted changes in the working tree and index. They are not routine troubleshooting fixes. Only use them when you have confirmed that local changes can be discarded or already have a safe backup.

Before using them, inspect:

~~~bash
git status
git diff
git diff --cached
~~~

If you need to keep any part, commit or stash first. Do not use a forced switch as a blind workaround.

## 13. Checkout Syntax That Restores Files

This is the most easily confused aspect of `git checkout`. Besides switching branches, checkout can retrieve file contents from the index or from a tree-ish.

### Restoring a File from the Index to the Working Tree

~~~bash
git checkout -- src/Search.java
~~~

This command takes the file version in the index and writes it to the working tree. It discards unstaged edits to that file. The index is not modified.

### Retrieving a File from a Commit into the Index and Working Tree

~~~bash
git checkout HEAD~1 -- src/Search.java
~~~

This command takes the file contents from the tree of `HEAD~1`, updating both the index and working tree for that path. Afterward, the file becomes a staged change relative to the current HEAD.

### Why -- Is Needed

When a branch and a file share the same name, Git needs to distinguish which name is a branch and which is a path. `--` separates revisions/options from paths:

~~~bash
git checkout branch-name
git checkout -- branch-name
~~~

The first command requests switching to the branch named `branch-name`; the second requests restoring the file with that name from the index. This separator keeps the syntax unambiguous and avoids misinterpretation.

## 14. Using git restore for File Restoration

Git 2.23 added `git restore` to separate file-restoration functionality from `git checkout`.

Restore unstaged changes from the index:

~~~bash
git restore -- src/Search.java
~~~

Restore a file from a specific commit into the working tree:

~~~bash
git restore --source=HEAD~1 --worktree -- src/Search.java
~~~

Restore the index from HEAD:

~~~bash
git restore --staged -- src/Search.java
~~~

Restore both the index and working tree from HEAD:

~~~bash
git restore --staged --worktree -- src/Search.java
~~~

`git restore` does not switch branches and does not move HEAD. If the goal is to switch branches, use `git switch`; if the goal is to restore files, `git restore` expresses intent more clearly.

## 15. Switching Branches with Ambiguous Names

A repository may contain a branch and a file with the same name. Because `git checkout` has multiple modes, name resolution can produce surprises.

Example:

~~~bash
# Switch branch
git switch release

# Restore path named release from index
git restore -- release
~~~

If using checkout:

~~~bash
# Switch branch
git checkout release

# Restore file/path
git checkout -- release
~~~

With revision-plus-path syntax, use the separator:

~~~bash
git checkout main -- docs/release.md
~~~

When writing scripts or instructions for others, use explicit syntax instead of relying on Git to guess your intent.

## 16. Creating a Branch Without Parent History Using --orphan

In some special workflows, you need to create a new branch with no parent commits:

~~~bash
git switch --orphan gh-pages
~~~

Or:

~~~bash
git checkout --orphan gh-pages
~~~

An orphan branch starts in an unborn branch state with no commits yet. The index and working tree are prepared according to the command and options' behavior; check the status before creating a new snapshot.

~~~bash
git status
git log --oneline
~~~

`git log` may not display commits on an orphan branch until you create the first commit. This is not an ordinary branch split from HEAD. Use it when you need an independent history, such as a publishing branch containing only artifacts, and be clear about what contents will go into the first commit.

## 17. Checking Before and After Switching

A basic workflow:

~~~bash
# 1. Identify current branch and changes
git status --short --branch
git branch --show-current

# 2. Inspect local contents
git diff
git diff --cached

# 3. Switch branch
git switch main

# 4. Confirm branch and working tree
git status --short --branch
git log -1 --oneline
~~~

If you need to create a new branch:

~~~bash
git switch -c feature/search
~~~

If you need to track a remote:

~~~bash
git switch --track origin/feature/search
~~~

If you want to inspect an old commit:

~~~bash
git switch --detach v1.2.0
~~~

Choose the command based on your goal and handle local changes before switching.

## 18. Common Mistakes

### Using git checkout Without Knowing Whether It Switches Branches or Restores Files

Checkout has multiple modes. If you want to switch branches, prefer `git switch`. If you want to restore files, use `git restore` or checkout syntax with `--`.

### Switching Branches While Having Uncommitted Changes

Git may keep changes if files are not overwritten, but will refuse if there is a risk of data loss. Check `git status`, then commit, stash, or restore intentionally.

### Thinking switch Always Deletes Local Changes

Incorrect. Git usually preserves local changes if they can be carried safely to the target branch. It refuses when overwriting is required or a safe transition is not possible.

### Using --discard-changes or -f to Bypass Errors

These options can discard uncommitted changes. Review diffs and save changes before using them.

### Creating Commits in Detached HEAD and Then Switching Branches

The commit may no longer be held by any branch. Create a branch with `git switch -c new-branch` before leaving detached HEAD if you want to keep the commits.

### Confusing Local Branches with Remote-Tracking Branches

`origin/feature/search` is a remote-tracking ref, while `feature/search` is a local branch. Use `--track` to create a local branch tracking the remote branch.

### Using Path Checkout Without --

Branch names and paths can collide. Use `--` to separate paths from revisions and options.

## 19. Takeaways

- `git switch branch` is the clear way to switch branches; `git checkout branch` is still supported.
- `git switch -c` and `git checkout -b` create a new branch and switch to it.
- `-C` and `-B` can reset an existing branch to a start point; verify refs and commits before using them.
- `--track` creates a local branch tracking a remote-tracking branch.
- `--detach` moves HEAD directly to a commit; create a branch if you want to keep new commits.
- Local changes can be kept across a branch switch if not overwritten; commit or stash if you need guaranteed preservation.
- `--merge` attempts to merge local changes during the switch; conflicts must be resolved manually.
- `--discard-changes` and `-f` can discard uncommitted changes.
- `git checkout -- path` restores a file from the index; `git checkout <tree-ish> -- path` retrieves a file from a tree into the index and working tree.
- `git restore` is the dedicated interface for restoring files; it does not switch branches.
- Use `--` to separate path names from revisions and options in checkout syntax.

`git switch` makes branch-switching operations clear, while `git checkout` remains necessary when reading or maintaining legacy multi-mode Git workflows. Once you distinguish moving HEAD from restoring files, inspect local changes before switching, and understand detached HEAD, you can switch working contexts safely without losing important changes.

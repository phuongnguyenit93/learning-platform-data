# Branches Are Movable Pointers in the Commit Graph

In Git, a branch is neither a directory copy nor a separate set of files. A branch is a named reference, typically pointing to the latest commit of a line of development. When you create a new commit on the currently checked-out branch, Git creates a new commit object and then moves that reference to the new commit. Older commits remain in the history and are linked to the new commit through parent relationships.

This model explains why creating a branch is very fast, why two branches can point to the same commit, and why merging or rebasing changes branch pointer positions. This lesson focuses on branches, the commit graph, and the role of HEAD: a branch indicates where a line of development currently ends, while HEAD tells Git which branch you are on or which commit you are viewing directly.

This lesson belongs to the **Branches and HEAD** chapter of the **SOURCE_CONTROL_GIT** module. The module guides you through Git from the working tree, staging area, commits, and history to branches, merging, rebasing, remotes, and tags; it also builds skills for collaborating across branches, resolving conflicts, tracking down changes, and recovering from mistakes while preserving important history. Understanding a branch as a pointer in the commit graph is the foundation for using branches, switching branches, and integrating history safely.

## 1. The Commit Graph Is the Foundation of Branches

Each commit is an immutable object containing a snapshot of the project, author/committer metadata, a message, and one or more parent commits. The parent indicates which history the commit was built upon. Parent relationships form a directed acyclic graph (DAG).

An example of a linear history:

~~~text
A --- B --- C
          main
~~~

The <code>main</code> branch points to commit <code>C</code>. Commit <code>C</code> has parent <code>B</code>, and <code>B</code> has parent <code>A</code>. Looking backward from the newest commit, we follow the parents to trace history in reverse.

When creating a new branch from <code>C</code>, Git only needs to create an additional reference pointing to the same commit:

~~~text
A --- B --- C
          main
          feature
~~~

Both branch names point to <code>C</code>. No commits are copied and no directories are duplicated. The two branches only begin to have different positions when one of them is updated with a new commit or a ref-modifying operation.

After creating commit <code>D</code> on <code>feature</code>:

~~~text
A --- B --- C --- D
          main    feature
~~~

<code>main</code> still points to <code>C</code>, while <code>feature</code> points to <code>D</code>. Commit <code>D</code> has parent <code>C</code>. Both branches share the entire history up to <code>C</code>, and then one branch advances further.

## 2. A Branch Is Actually a Reference

Local branches are typically stored under reference names in the namespace:

~~~text
refs/heads/<branch-name>
~~~

For example:

~~~text
refs/heads/main
refs/heads/feature/payment-retry
~~~

A reference contains the object ID of the commit that the branch points to. Git manages references and may store them under the <code>.git/refs/heads/</code> directory or pack them into the <code>packed-refs</code> file. The physical storage layout can vary depending on the repository and maintenance operations; use Git commands to read or update refs instead of editing internal files manually.

Some commands to inspect branches and refs:

~~~bash
# List local branches
git branch

# View the object IDs of local branches
git show-ref --heads

# View the commit that the main branch points to
git rev-parse main

# View the commit that the current HEAD resolves to
git rev-parse HEAD
~~~

A branch name is a human-friendly name for a position in history. The object ID is the actual identifier of the commit. When a branch moves, the branch name stays the same while the object ID it points to changes.

### Branches Do Not Store Uncommitted Changes

A branch points to a commit, not to in-progress edits in the working tree. Unstaged changes reside in the working tree; staged changes reside in the index. They do not become part of the branch's history until they are committed.

Therefore, two branches can point to the same commit while the working tree has uncommitted changes. Those changes belong to the current local state, not to the data stored in a branch reference.

## 3. HEAD Indicates the Current Working Position

In the normal state, <code>HEAD</code> is a symbolic reference pointing to the currently checked-out local branch. For example:

~~~text
HEAD -> refs/heads/main -> commit C
~~~

In that case:

- <code>HEAD</code> indicates that the current branch is <code>main</code>.
- <code>refs/heads/main</code> points to commit <code>C</code>.
- <code>git rev-parse HEAD</code> returns the object ID of commit <code>C</code>.
- When a new commit is created, Git updates <code>refs/heads/main</code>.

Check with:

~~~bash
# Name of the currently checked-out branch
git branch --show-current

# Which ref HEAD symbolically points to
git symbolic-ref HEAD

# The object ID that HEAD resolves to
git rev-parse HEAD
~~~

Normally, <code>git symbolic-ref HEAD</code> prints:

~~~text
refs/heads/main
~~~

HEAD is not a copy of a branch. It is a pointer indicating which branch is currently selected in the current working tree.

## 4. Creating a Branch Only Creates a New Pointer

Suppose you are on <code>main</code>, at commit <code>C</code>. The command:

~~~bash
git branch feature/payment-retry
~~~

creates the <code>feature/payment-retry</code> branch pointing to the same commit that the current HEAD resolves to. This command does not switch to the new branch.

Verify:

~~~bash
git branch --list
git rev-parse main
git rev-parse feature/payment-retry
git branch --show-current
~~~

Immediately after creation, both branches usually have the same object ID and the current branch is still <code>main</code>.

To both create a branch and switch to it:

~~~bash
git switch -c feature/payment-retry
~~~

This command does two things: creates the branch at the current commit and updates HEAD to point to the new branch. It can be written in two steps:

~~~bash
git branch feature/payment-retry
git switch feature/payment-retry
~~~

<code>git switch -c</code> is a more concise way when you want to start working on the new branch right away.

### Creating a Branch from a Specific Commit

You do not have to create a branch from the current HEAD. You can specify a start point:

~~~bash
git branch hotfix/payment-timeout v1.8.0
~~~

If <code>v1.8.0</code> is a tag pointing to the release commit, the <code>hotfix/payment-timeout</code> branch will start at that commit. Switch to the branch:

~~~bash
git switch hotfix/payment-timeout
~~~

When you need to create and switch at the same time from a start point:

~~~bash
git switch -c hotfix/payment-timeout v1.8.0
~~~

## 5. What Happens When Creating a Commit on a Branch?

Suppose you have checked out <code>feature/payment-retry</code>, with the branch pointing to commit <code>C</code>. After editing a file, staging, and committing:

~~~bash
git add src/payment/RetryPolicy.java
git commit -m "Add bounded payment retry"
~~~

Git creates commit <code>D</code> with parent <code>C</code>, then updates the current branch from <code>C</code> to <code>D</code>:

~~~text
A --- B --- C --- D
          |       |
         main   feature/payment-retry
~~~

HEAD still symbolically points to <code>refs/heads/feature/payment-retry</code>. The branch reference is moved to <code>D</code>; HEAD does not need to be renamed or store a separate new commit.

Verify:

~~~bash
git log --oneline --decorate --graph --all
git rev-parse HEAD
git rev-parse feature/payment-retry
git symbolic-ref HEAD
~~~

The output shows that HEAD and the current branch resolve to the same commit <code>D</code>.

If you switch to <code>main</code> and then create a commit, only <code>main</code> is updated. <code>feature/payment-retry</code> still points to <code>D</code> until an operation directly affects that branch.

## 6. Switching Branches Changes HEAD and Updates the Working Tree

The command:

~~~bash
git switch main
~~~

instructs Git to move HEAD to the <code>main</code> branch, while updating the index and working tree to reflect the snapshot of the commit that <code>main</code> points to.

Before switching branches, Git checks local changes to avoid overwriting unsaved data. If changes in the working tree or index could be lost or conflict with the target snapshot, Git typically refuses to switch branches and asks you to commit, stash, or handle the changes first.

Check the branch after switching:

~~~bash
git branch --show-current
git symbolic-ref HEAD
git status --short
~~~

### Branches and the Working Tree Are Two Separate Concepts

A branch is a reference to a commit. The working tree is the files currently visible on disk. When switching branches, Git changes HEAD and typically updates the working tree to match the target branch's snapshot. If two branches point to the same commit, switching may not change file contents, yet HEAD still moves to a different reference.

This is why you can be on either <code>main</code> or <code>feature</code> even when both point to the exact same commit.

## 7. Merging Advances the Target Branch Pointer

Merging combines the history of another branch into the current branch. You must check out the target branch first; the currently checked-out branch is the one that will be updated.

### Fast-Forward Merge

Suppose <code>main</code> points to <code>C</code>, while <code>feature</code> has two additional commits <code>D</code> and <code>E</code> based on <code>C</code>:

~~~text
A --- B --- C --- D --- E
          main            feature
~~~

If you check out <code>main</code> and merge <code>feature</code>:

~~~bash
git switch main
git merge feature
~~~

Git can fast-forward because commit <code>C</code> is an ancestor of <code>E</code>. There is no need to create a merge commit; Git simply moves the <code>main</code> pointer from <code>C</code> to <code>E</code>:

~~~text
A --- B --- C --- D --- E
                          main, feature
~~~

Both branches now point to the same commit. Commits <code>D</code> and <code>E</code> already existed on feature; fast-forward merely updates the reference.

### Merge Commit When History Has Diverged

If both branches have their own commits:

~~~text
          D --- E  feature
         /
A --- B --- C --- F  main
~~~

When merging feature into main, Git creates a merge commit <code>M</code> with two parents: <code>F</code> and <code>E</code>. The <code>main</code> branch moves to <code>M</code>, while <code>feature</code> still points to <code>E</code>:

~~~text
          D --- E -----------.
         /                    \
A --- B --- C --- F ----------- M  (main)
~~~

After the merge, <code>feature</code> still points to <code>E</code>, while <code>main</code> points to <code>M</code>. Commit <code>M</code> has two parents, <code>F</code> and <code>E</code>. Merging does not rewrite old commits; it adds a combined commit and moves the target branch.

You can request creating a merge commit even when fast-forward is possible:

~~~bash
git switch main
git merge --no-ff feature
~~~

This keeps an explicit merge milestone in the history. The policy of using fast-forward or merge commits depends on the team's conventions.

## 8. Rebasing Creates New Commits and Then Moves the Branch

Rebasing replays the commits of the current branch onto a different base commit. Git replays the changes as new commits, because the new parent changes the commit's object ID.

Suppose:

~~~text
          D --- E  feature
         /
A --- B --- C --- F  main
~~~

When checking out feature and running:

~~~bash
git switch feature
git rebase main
~~~

Git replays the changes from <code>D</code> and <code>E</code> onto <code>F</code>, creating new commits <code>D'</code> and <code>E'</code>. The feature branch moves to the last new commit:

~~~text
          D --- E                 (old history)
         /
A --- B --- C --- F --- D' --- E'  feature
                 main
~~~

In the diagram, <code>main</code> still points to <code>F</code>, while <code>feature</code> points to <code>E'</code>. The old commits <code>D</code> and <code>E</code> are not modified in place; they may become unreachable if no refs point to them and can later be cleaned up by garbage collection.

Key points to remember:

- Parent links inside an already-created commit are immutable.
- Rebase creates new commit objects with new parents.
- The current branch is updated to point to the new commit after the rebase succeeds.
- The base branch does not automatically move just because you rebased another branch onto it.

Do not rebase already-shared commits without agreeing with your team, because rewriting history can force others to resynchronize their branches.

## 9. Reset Moves the Current Branch to Another Commit

<code>git reset</code> can move the current branch to another commit. It also has modes that control how the index and working tree are updated.

For example:

~~~bash
git reset --soft HEAD~1
~~~

The command above moves the current branch back by one commit, while keeping the index and working tree intact. The contents of the commit just removed from the tip of the branch remain staged so you can edit and recommit them.

Three common modes:

| Command | Branch ref | Index | Working tree |
|---|---|---|---|
| <code>git reset --soft &lt;commit&gt;</code> | Moves to target commit | Unchanged | Unchanged |
| <code>git reset --mixed &lt;commit&gt;</code> | Moves to target commit | Updated to match target commit | Keeps current file contents |
| <code>git reset --hard &lt;commit&gt;</code> | Moves to target commit | Updated to match target commit | Updated to match target commit, may lose local changes |

If the mode option is omitted, <code>git reset</code> defaults to <code>--mixed</code>.

Simple diagram before and after reset:

~~~text
Before:
A --- B --- C --- D  main

git reset --soft HEAD~1

After:
A --- B --- C  main
          \
           D  (no longer at the tip of the current branch)
~~~

Commit <code>D</code> is not necessarily deleted immediately. The reflog usually records ref movements, helping you find the old commit again if needed:

~~~bash
git reflog
~~~

Resetting on a shared branch can cause local history to differ from remote and cause difficulties for others. Understand the impact before using it, especially with <code>--hard</code>.

## 10. Detached HEAD: HEAD Points Directly to a Commit

HEAD does not always point to a branch. When you check out a commit or tag directly, HEAD can contain an object ID instead of a symbolic ref. This state is called detached HEAD.

For example:

~~~bash
git switch --detach v1.8.0
~~~

Diagram:

~~~text
refs/heads/main ---------> commit C
refs/tags/v1.8.0 --------> commit B
HEAD -------------------> commit B
~~~

In this state:

- You are viewing the snapshot at commit <code>B</code>.
- No local branch is checked out.
- <code>git branch --show-current</code> typically prints empty output.
- If you create a new commit, HEAD moves to the new commit, but the <code>main</code> branch does not move.

Check:

~~~bash
git status -sb
git branch --show-current
git symbolic-ref -q HEAD
git rev-parse HEAD
~~~

The command <code>git symbolic-ref -q HEAD</code> returns an error exit code when HEAD is not a symbolic ref. That is normal in detached HEAD state.

### Keeping Commits Created in Detached HEAD

If you created commits while in detached HEAD and want to continue developing from there, create a branch:

~~~bash
git switch -c experiment/release-fix
~~~

The new branch points to the current commit and HEAD switches to that branch. If you have already left detached HEAD without creating a branch, you can find the commit in the reflog and create a rescue branch:

~~~bash
git reflog
git switch -c rescue/release-fix <commit-id>
~~~

Do not rely on detached commits existing forever. If no ref holds the commit, the object can become unreachable and be cleaned up by Git later.

## 11. Deleting a Branch Deletes a Reference

When deleting a branch:

~~~bash
git branch -d feature/payment-retry
~~~

Git deletes the reference <code>refs/heads/feature/payment-retry</code>. The commits that the branch used to point to are not deleted directly. If those commits are still referenced by another branch, tag, or other ref, they remain reachable.

Git normally refuses <code>-d</code> if the branch has not been merged into its upstream or current HEAD, to avoid deleting a branch with unintegrated commits. The force option:

~~~bash
git branch -D feature/payment-retry
~~~

should only be used when you have confirmed you no longer need that branch. If the commits are only retained by the reflog or have no refs pointing to them, recovery capability may be limited by time and garbage collection policies.

## 12. Local Branches and Remote-Tracking Branches

Local branches and remote-tracking branches are both references, but they serve different roles:

| Ref type | Example | Role |
|---|---|---|
| Local branch | <code>refs/heads/main</code> | Local line of development that you can check out and commit to |
| Remote-tracking | <code>refs/remotes/origin/main</code> | Records the state of the branch on the remote at the most recent fetch |
| Tag | <code>refs/tags/v1.8.0</code> | Marks an object, typically used for release milestones |

A remote-tracking ref is not a branch running on the server. It is a local record updated during fetch:

~~~bash
git fetch origin
git branch -r
git show-ref --verify refs/remotes/origin/main
~~~

When fetch receives new commits from the remote, the <code>origin/main</code> reference may move. The local <code>main</code> branch does not automatically move along with it unless you pull, merge, or rebase.

When a push succeeds, the server updates the remote branch according to the push request. Fetch again when you need to refresh local remote-tracking refs; do not assume every push operation has refreshed this local record.

## 13. Inspecting All Pointers and the Graph

The following commands are useful when you want to know where branches are pointing:

~~~bash
# Display commit graph with branch/tag names
git log --oneline --decorate --graph --all

# List local branches
git branch -vv

# List remote-tracking branches
git branch -r

# List all refs with object IDs
git show-ref

# Check whether HEAD is a symbolic ref
git symbolic-ref -q HEAD

# Resolve HEAD to an object ID
git rev-parse HEAD
~~~

Read the output in order:

1. Identify which branch HEAD points to, or whether it is detached.
2. Identify which commit each local branch points to.
3. Identify which commit each remote-tracking ref currently records.
4. Look at the graph to see which commits are ancestors, which branches have diverged, and where the common ancestor lies.

There is no need to open files inside the <code>.git</code> directory to deduce the state. Git commands read and update references according to the repository's storage format.

## 14. Distinguishing Branches from Tags

Branches and tags are both named refs, but their purposes differ:

- A branch is a pointer that moves along a line of development. When committing on a checked-out branch, the branch advances to the new commit.
- A tag typically marks a specific milestone such as a release. A tag does not normally move automatically when you create new commits.

For example:

~~~bash
git tag v1.8.0
git switch main
git commit -m "Continue development"
~~~

The new commit advances <code>main</code>, while the <code>v1.8.0</code> tag still marks the tagged commit. A tag can be recreated or moved via an explicit operation, but release tags should not be treated like working branches.

## 15. Common Misconceptions

| Misconception | Reality |
|---|---|
| A branch is a directory copy | A branch is a reference pointing to a commit |
| Creating a branch automatically switches to the new branch | <code>git branch</code> only creates a ref; <code>git switch</code> moves HEAD |
| HEAD always directly contains an object ID | Normally HEAD is a symbolic ref; detached HEAD points directly to a commit |
| A new commit advances all branches together | Only the currently checked-out branch is normally updated |
| Merge always creates a new commit | Fast-forward merge only moves the ref; a diverged merge normally creates a merge commit |
| Rebase moves old commits to a new parent | Rebase creates new commits and then updates the branch to the new commit |
| Deleting a branch immediately deletes its commits | Deleting the ref; commits may remain reachable via another ref or reflog |
| <code>origin/main</code> is the live remote branch | It is a local remote-tracking ref updated via fetch |
| Detached HEAD cannot create commits | You can still create commits, but no local branch automatically holds them |

## 16. Self-Check Exercises

Practice in a test repository:

1. Create three linear commits on <code>main</code> and draw the graph using <code>git log --graph --oneline --decorate</code>.
2. Create a <code>feature</code> branch from HEAD; confirm that both branches initially have the same object ID.
3. Create a commit on <code>feature</code>; observe that only the feature pointer moves.
4. Switch back to <code>main</code> and create another commit; explain why the two branches diverged.
5. Create a branch from a tag or an older commit instead of the current HEAD.
6. Try a fast-forward merge and observe the target branch advancing to an existing commit.
7. Create two branches with separate commits and then merge to observe a two-parent merge commit.
8. Rebase an experimental branch onto a base branch and compare object IDs before and after.
9. Check out detached HEAD, create a commit, and then create a rescue branch to keep the commit.
10. Delete a merged branch and determine which branch still keeps the commits reachable.
11. Fetch from the remote and distinguish <code>main</code> from <code>origin/main</code>.
12. Use <code>git reflog</code> to observe movements of HEAD or branch refs.

When reading a commit graph, treat branches as names pointing to commit tips and HEAD as an indicator of your current working position. Commits add nodes and parent links; operations such as switch, merge, rebase, or reset decide which references are moved. Grasping that helps you understand Git history rather than merely memorizing command names.

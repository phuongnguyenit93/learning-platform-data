# Creating, Listing, and Renaming Local Branches

A branch is a named reference pointing to a commit. Through branches, each piece of work can progress independently within the same repository without copying the entire source directory. In Git, creating a new branch typically only creates an additional lightweight reference; this operation does not duplicate the entire commit history.

Three fundamental tasks when managing local branches are creating a branch for new work, listing branches to see which ones exist in the repository, and renaming a branch when its current name is no longer appropriate. Mastering these commands helps organize work by feature, bug fix, or release target, while avoiding confusion between local branches and remote-tracking branches.

In a Git source control service, branches are how development streams are divided. Clear branch names, readable branch lists, and a controlled renaming workflow help teams collaborate better when reviewing, integrating, and handing off changes.

## 1. What Is a Branch?

A branch in Git is a named reference to a commit. For example, `main` may point to the latest commit of the main branch, while `feature/payment-summary` points to the latest commit of the payment feature branch.

Illustration:

~~~text
A --- B --- C  main
           \
            D --- E  feature/payment-summary
~~~

In the diagram:

- `main` points to commit `C`.
- `feature/payment-summary` points to commit `E`.
- Both branches share history from `A` to `C`.
- Commits `D` and `E` belong only to the feature branch history at the time illustrated.

A branch is not a folder copy containing files. It is a ref pointing to a commit. When creating a branch, Git normally only writes a new ref pointing to the current commit or a specified commit.

### HEAD and the Current Branch

`HEAD` indicates the current working position. Normally, `HEAD` is a symbolic ref pointing to the currently checked-out branch. For example, when on `feature/payment-summary`, `HEAD` points to `refs/heads/feature/payment-summary`.

Verify:

~~~bash
git branch --show-current
git symbolic-ref --short HEAD
git rev-parse --short HEAD
~~~

The first two commands show the current branch name when `HEAD` is attached to a branch. The third command displays the commit that `HEAD` points to.

If the repository is in detached HEAD state, `git branch --show-current` may print no branch name and `git symbolic-ref` will not return a branch. This state is different from a lost branch; `HEAD` is pointing directly to a commit. This lesson focuses on local branch operations in the normal working state.

## 2. Checking Before Creating a Branch

Before creating a branch for a task, inspect the repository status:

~~~bash
git status -sb
git branch --show-current
git log --oneline --decorate -5
~~~

These commands help determine:

- Which branch you are on.
- Whether the working tree has uncommitted changes.
- What the current commit is.
- Whether the repository is in a state requiring completion of a merge or rebase.

Creating a branch does not automatically commit existing changes. If the working tree has edits, the new branch still starts from the current commit, while uncommitted edits remain in the working tree and may follow along when switching branches if there are no conflicts.

To keep work easy to manage, make sure you understand which task the current changes belong to before creating or switching branches. If you need to separate two pieces of work, you can commit the completed part or temporarily stash the rest according to your team's workflow.

## 3. Creating a Branch with git branch

Basic syntax:

~~~bash
git branch <branch-name>
~~~

Example:

~~~bash
git branch feature/payment-summary
~~~

This command creates the `feature/payment-summary` branch at the commit that `HEAD` currently points to. It does not automatically switch to the new branch. After this command, the current branch remains the old branch.

Verify:

~~~bash
git branch
git branch --show-current
~~~

In the branch list, the `*` symbol marks the current branch. The newly created branch appears, but without the `*` symbol if you have not switched to it.

### Creating a Branch from a Specific Commit

You can specify a start point:

~~~bash
git branch feature/payment-summary origin/main
~~~

The new branch starts from the commit that `origin/main` points to. A start point can be:

- A local branch name, such as `main`.
- A remote-tracking branch, such as `origin/main`.
- A commit hash.
- A tag.
- A revision expression that Git can resolve to a commit.

Example of creating a branch from a known commit:

~~~bash
git branch fix/payment-timeout a1b2c3d
~~~

Before using a commit ID or ref as a start point, confirm that it belongs to the intended history. If created from the wrong point, the branch is still valid in Git terms, but may contain the wrong codebase foundation.

## 4. Creating a Branch and Switching to the New Branch

In practice, when starting a feature or bug fix, we usually want to create a branch and switch to it immediately.

### Using git switch -c

~~~bash
git switch -c feature/payment-summary
~~~

`-c` stands for create. Git creates a new branch from the current commit and then switches `HEAD` to that branch.

You can specify a start point:

~~~bash
git switch -c feature/payment-summary origin/main
~~~

This command creates a local branch from the commit that the remote-tracking branch `origin/main` points to and switches to the new branch.

### Using git checkout -b

~~~bash
git checkout -b feature/payment-summary
~~~

This is the familiar syntax from before `git switch` was introduced. It also creates a branch and switches to the new branch.

For normal branch operations, prefer `git switch` because the command name clearly describes switching branches. `git checkout` remains useful in legacy workflows and also supports many other operation modes.

### Comparing Branch Creation Commands

| Command | Creates branch? | Switches to new branch? |
| --- | --- | --- |
| `git branch feature/x` | Yes | No |
| `git branch feature/x main` | Yes, from `main` | No |
| `git switch -c feature/x` | Yes | Yes |
| `git switch -c feature/x main` | Yes, from `main` | Yes |
| `git checkout -b feature/x` | Yes | Yes |

There is no need to run `git branch feature/x` followed by `git switch -c feature/x`; since the branch already exists, the second create command will report an error. Choose the one that fits your goal.

## 5. Naming Branches Clearly

A branch name should tell others the type of work and main objective. Some common conventions:

| Work type | Example |
| --- | --- |
| Feature | `feature/payment-summary` |
| Bug fix | `fix/payment-timeout` |
| Hotfix | `hotfix/failed-login` |
| Maintenance task | `chore/update-gradle-wrapper` |
| Documentation | `docs/git-branch-guide` |
| Experiment | `experiment/new-cache-policy` |

Actual conventions depend on the team. Some teams use `feat/`, `bugfix/`, `task/`, or include a ticket ID such as `feature/PROJ-123-payment-summary`. What matters is using it consistently and avoiding generic names like `test`, `new`, or `branch1`.

### Ref Naming Rules

Branch names must follow Git's ref rules. For example, a branch name must not contain certain special characters such as spaces, `~`, `^`, `:`, `?`, `*`, `[`, or backslashes; nor may it contain invalid sequences or structures such as `..`, `@{`, a trailing `/`, or a component ending with `.lock`.

Use Git to validate a name:

~~~bash
git check-ref-format --branch feature/payment-summary
~~~

If the name is valid, the command exits successfully. Otherwise, Git reports an error. You can use this command in branch-creation scripts or hooks that enforce naming conventions.

### Naming Notes

- Use lowercase and hyphens for readability if that is your team's convention.
- Avoid embedding sensitive information in branch names.
- Do not use names reserved for protected branches such as `main`, `release`, or `production`.
- Use meaningful prefixes for filtering and grouping.
- Avoid repeatedly renaming a branch after sharing it with many people.

## 6. Listing Local Branches

Basic command:

~~~bash
git branch
~~~

Git displays the local branches. The `*` symbol marks the current branch.

Example:

~~~text
  feature/payment-summary
* main
  fix/payment-timeout
~~~

In the example, `main` is the current branch. The other two branches exist in the repository but are not checked out.

This command does not display all branches on the remote. To view remote-tracking branches, use the options in the next section.

### Listing by Pattern

~~~bash
git branch --list 'feature/*'
~~~

The command displays only local branches whose names match the `feature/*` pattern.

Other patterns:

~~~bash
git branch --list 'fix/*'
git branch --list '*payment*'
git branch --list 'release/*'
~~~

When passing a pattern with `*`, enclose it in quotes so the shell does not expand the pattern before Git receives it.

### Viewing the Current Branch

~~~bash
git branch --show-current
~~~

This command prints the current branch name and is suitable for scripts that need to know which branch they are operating on. If `HEAD` is detached, the output may be empty.

## 7. Listing Local and Remote-Tracking Branches

Git distinguishes local branches from remote-tracking branches:

- Local branches typically reside under `refs/heads/`, for example `feature/payment-summary`.
- Remote-tracking branches typically reside under `refs/remotes/`, for example `origin/main`.

A remote-tracking branch is a local reference reflecting the remote's state at the last fetch. It is not a checked-out local branch and does not update automatically without fetching.

### Viewing Remote-Tracking Branches

~~~bash
git branch --remotes
~~~

Or the short form:

~~~bash
git branch -r
~~~

Example:

~~~text
  origin/HEAD -> origin/main
  origin/main
  origin/release/2.x
  origin/feature/payment-summary
~~~

### Viewing Both Local and Remote-Tracking Branches

~~~bash
git branch --all
~~~

Or:

~~~bash
git branch -a
~~~

Example:

~~~text
* main
  feature/payment-summary
  remotes/origin/HEAD -> origin/main
  remotes/origin/main
  remotes/origin/feature/payment-summary
~~~

Do not confuse `feature/payment-summary` with `origin/feature/payment-summary`. One is a local branch, and the other is a remote-tracking ref. They may point to the same commit or different commits.

If the remote-tracking branch list does not yet reflect the latest server state, update it with:

~~~bash
git fetch origin
git branch -a
~~~

`fetch` downloads new refs and objects from the remote; it does not automatically switch the current branch.

## 8. Viewing Last Commit Information for Each Branch

Add `-v`:

~~~bash
git branch -v
~~~

Git displays each branch alongside its abbreviated commit hash and the subject of the last commit.

Example:

~~~text
  feature/payment-summary  a1b2c3d Add payment summary
* main                    d4e5f6a Merge release preparation
  fix/payment-timeout     123abcd Handle gateway timeout
~~~

This is a quick way to see which commit each branch has reached without running `git log` separately for each branch.

### Viewing Upstream and Ahead/Behind Status

~~~bash
git branch -vv
~~~

`-vv` adds upstream information if the branch has been configured to track a remote-tracking branch. Example:

~~~text
  feature/payment-summary a1b2c3d [origin/feature/payment-summary: ahead 2] Add payment summary
* main                   d4e5f6a [origin/main] Merge release preparation
  fix/payment-timeout    123abcd [origin/fix/payment-timeout: behind 1] Handle gateway timeout
~~~

The `ahead` and `behind` states reflect the difference between the local branch and its upstream based on commit information currently in the repository. Fetch first if you need to evaluate the latest remote state.

If a branch does not have an upstream yet, `-vv` does not show tracking details for that branch. Having no upstream does not mean the branch is broken; the local branch may simply never have been pushed or configured for tracking.

## 9. Sorting and Formatting the Branch List

When a repository has many branches, the default order may not help you find the branch you need. Use `--sort`:

~~~bash
# Sort by name
git branch --sort=refname

# Newest commit first
git branch --sort=-committerdate

# By commit date ascending
git branch --sort=committerdate
~~~

A `-` sign before the field name reverses the sort order. `committerdate` is the date of the last commit that the branch points to.

### Using --format to Customize Columns

~~~bash
git branch --format='%(refname:short) %(objectname:short) %(subject)'
~~~

Commonly used placeholders:

| Placeholder | Meaning |
| --- | --- |
| `%(refname:short)` | Abbreviated branch name |
| `%(objectname:short)` | Abbreviated commit hash |
| `%(subject)` | Commit subject |
| `%(committerdate:short)` | Commit date in short format |
| `%(upstream:short)` | Abbreviated upstream name if present |

Example:

~~~bash
git branch --sort=-committerdate \
  --format='%(refname:short) | %(committerdate:short) | %(subject)'
~~~

This format is useful when reviewing stale branches, preparing cleanups, or exporting lists for reporting. Remember that `git branch` only displays refs within the selected option scope; the list does not automatically include every branch on the server.

## 10. Filtering Branches by Commit Relationships

Git can filter branches based on whether a branch already contains a commit.

### Branches Already Merged into a Branch

~~~bash
git branch --merged main
~~~

This command lists local branches whose tip is already reachable from `main`, meaning the branch's commits have been integrated into `main`'s history by ancestry.

### Branches Not Yet Merged

~~~bash
git branch --no-merged main
~~~

This command lists local branches not yet merged into `main`. These branches need to be checked before deletion or retirement.

### Branches Containing a Commit

~~~bash
git branch --contains a1b2c3d
~~~

This command lists branches whose history contains the specified commit.

You can invert the condition:

~~~bash
git branch --no-contains a1b2c3d
~~~

These filters help inventory branches, but do not automatically decide which branches are safe to delete. An unmerged branch may contain active work; a merged branch may still be retained for release or audit reasons.

## 11. Renaming the Current Branch

When standing on the branch you want to rename, use:

~~~bash
git branch -m feature/payment-summary
~~~

This command renames the current branch to `feature/payment-summary`. The `-m` option stands for `--move`.

For example, while on `feature/payment`, to rename it to `feature/payment-summary`:

~~~bash
git branch -m feature/payment-summary
~~~

Verify:

~~~bash
git branch --show-current
git status -sb
git branch -vv
~~~

Commits are not recreated just because a branch is renamed. The new branch name still points to the old commit; `HEAD` remains attached to the current branch, only the ref name changed.

### Renaming a Non-Checked-Out Branch

If you are on another branch and want to rename a different local branch:

~~~bash
git branch -m old-feature-name new-feature-name
~~~

Example:

~~~bash
git branch -m feature/payment feature/payment-summary
~~~

This command renames the local ref `feature/payment` to `feature/payment-summary`. The currently checked-out branch does not change if it is a different branch.

## 12. Renaming with --move and --force

Two equivalent forms:

~~~bash
git branch --move old-name new-name
git branch -m old-name new-name
~~~

They are equivalent.

If the target name already exists, `git branch -m` refuses to prevent accidental overwriting. There is an `-M` or `--move --force` option:

~~~bash
git branch -M old-name new-name
~~~

`-M` allows renaming even if the target branch already exists. This operation can replace the ref currently holding the target name; only use it after clearly inspecting the target branch and confirming you intend to replace it.

Before using `-M`, check:

~~~bash
git branch -vv
git log --oneline --decorate old-name -5
git log --oneline --decorate new-name -5
~~~

If the target branch contains work that needs to be kept, do not use force rename to overwrite it. Choose a different name or coordinate integrating the content first.

## 13. What Changes When Renaming a Branch?

Renaming a local branch changes the ref name under `refs/heads/`. It does not automatically change:

- The branch name on the remote server.
- Pull requests or merge requests attached to the remote branch.
- Local branches in other teammates' clones.
- The repository's default branch name.
- Commit contents or commit hashes.

Git may move the reflog and related branch configuration to the new name during a rename. However, the remote may still keep the old branch until it is updated according to the shared workflow.

### Checking After Renaming

~~~bash
git branch --list
git branch -vv
git reflog show feature/payment-summary
git config --get branch.feature/payment-summary.remote
git config --get branch.feature/payment-summary.merge
~~~

The last `git config --get` commands may print nothing if the branch has no upstream yet. This is not necessarily an error.

## 14. Renaming a Branch That Already Has an Upstream

Suppose the local branch `feature/payment` is tracking `origin/feature/payment`. When renaming locally:

~~~bash
git branch -m feature/payment-summary
~~~

The local branch now has the new name. The tracking configuration may still point to the old upstream `origin/feature/payment`; check with:

~~~bash
git branch -vv
~~~

If the team also wants to rename the branch on the remote, perform that separately according to the Git host's workflow. Once the new remote branch is created or pushed, you can set the upstream:

~~~bash
git push -u origin feature/payment-summary
~~~

This command publishes the new local branch to `origin` and configures the corresponding upstream if the push succeeds.

If the old remote branch needs to be deleted, check pull requests, pipelines, branch protections, and anyone actively using it first. Deleting a remote branch is a separate operation; renaming locally does not automatically delete the branch on the server.

## 15. Renaming a Branch Used in Another Worktree?

A repository can have multiple linked worktrees. Each worktree can check out its own branch. Git typically refuses certain rename operations if the branch is currently checked out in another worktree, to avoid altering a ref that another worktree is actively using.

List worktrees:

~~~bash
git worktree list
~~~

If you cannot rename a branch, check whether the branch is checked out in another worktree. Coordinate releasing the branch in that worktree before renaming, or choose a different name if work is proceeding in parallel.

Do not delete a worktree directory using ordinary file operations to bypass Git's check. Use `git worktree` commands appropriate to the actual repository state.

## 16. Renaming an Improperly Named Branch

Suppose the current branch is named `test`, but the team requires the `feature/` prefix:

~~~bash
git branch -m feature/payment-summary
~~~

If the branch has not been pushed yet, the change is mainly local and relatively straightforward. If the branch has already been pushed or appears in a pull request, coordinate to:

1. Announce the new branch name.
2. Push the local branch under the new name.
3. Update the pull request or open a new pull request depending on the platform.
4. Update references in documentation, tickets, and pipelines if applicable.
5. Confirm no users still depend on the old name.
6. Delete the old remote branch if permitted and no longer needed.

A branch name is a reference used by many tools and people. A local rename does not automatically update all external integrations.

## 17. Creating a Branch from the Current Branch or from Upstream?

An important decision is the start point.

### Creating from the Current Branch

~~~bash
git switch -c feature/payment-summary
~~~

The new branch starts from the current commit. This approach is appropriate when you are already on the right base branch and have updated it.

### Creating from a Remote-Tracking Branch

~~~bash
git fetch origin
git switch -c feature/payment-summary origin/main
~~~

The new branch starts from the state of `origin/main` at the most recent fetch. This is a clear choice when the team mandates that all feature branches branch off from `main`.

### Creating a Branch from Another Local Branch

~~~bash
git branch feature/report-export release/2.x
~~~

This command creates a new branch from `release/2.x` without switching to the new branch.

Before creating, verify the exact source commit:

~~~bash
git log --oneline --decorate -1 main
git log --oneline --decorate -1 origin/main
~~~

If local `main` has not been fetched or updated, it may differ from `origin/main`. Choose the ref that matches your project's workflow.

## 18. Creating a Branch Tracking a Remote Branch

When you want to create a local branch corresponding to a remote-tracking branch, you can use:

~~~bash
git switch --track origin/feature/payment-summary
~~~

Git creates a local branch with the matching name and configures the upstream to the specified remote-tracking branch. If you want a different local name:

~~~bash
git switch --track -c payment-summary origin/feature/payment-summary
~~~

This command creates the local branch `payment-summary` tracking `origin/feature/payment-summary`.

This operation links a local branch to an upstream, which differs from merely creating a local branch with `git branch`. An upstream lets commands such as `git status -sb`, `git pull`, and `git push` know the configured remote branch.

## 19. Checking for Duplicate Branch Names

Git does not allow creating a new local branch if that name already exists:

~~~bash
git branch feature/payment-summary
~~~

If the branch already exists, Git reports that the branch name already exists. Check beforehand:

~~~bash
git branch --list feature/payment-summary
git show-ref --verify refs/heads/feature/payment-summary
~~~

If you want to switch to the existing branch:

~~~bash
git switch feature/payment-summary
~~~

If the branch does not exist yet and you want to create a new one, use `git switch -c`. Do not use `-M` just to bypass a duplicate-name error; first check whether the existing branch contains work that must be preserved.

## 20. Distinguishing Rename, Copy, and Creating a New Branch

Each operation has a different goal:

| Operation | Command | Result |
| --- | --- | --- |
| Create a new branch | `git branch new-name` | Creates a new ref pointing to the selected commit |
| Create and switch branches | `git switch -c new-name` | Creates a new ref and switches `HEAD` to it |
| Rename a branch | `git branch -m old-name new-name` | Moves the local ref to the new name |
| Copy a starting point to another branch | `git branch new-name old-name` | Creates a new ref pointing to the current commit of `old-name` |

Git does not have a common `git branch --copy` command parallel to rename; to create another branch with the same starting point, use `git branch new-name old-name`. Both branches initially point to the same commit but can progress independently afterward.

## 21. Branch Names and Ref Structure

Local branches are stored under the `refs/heads/` namespace. For example:

~~~text
refs/heads/main
refs/heads/feature/payment-summary
refs/heads/fix/payment-timeout
~~~

Names containing `/` create a hierarchical appearance when listed, yet Git still treats them as ref names. Prefixes help group and filter branches by convention.

View full refs:

~~~bash
git for-each-ref --format='%(refname) %(objectname:short)' refs/heads/
~~~

View a specific ref:

~~~bash
git show-ref --verify refs/heads/feature/payment-summary
~~~

Understanding refs helps distinguish local branches from remote-tracking branches and tags, which live in different namespaces.

## 22. Common Errors and How to Handle Them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `branch already exists` | The local branch name is already in use | List branches, switch to the existing branch, or choose a new name |
| Created a branch but still on the old branch | Used `git branch`, which only creates a ref | Run `git switch <branch-name>` |
| New remote branch not visible | Have not fetched or only viewing local branches | Run `git fetch` then `git branch -a` |
| `git branch --show-current` prints no name | Possibly in detached HEAD state | Check `git status` and `git symbolic-ref HEAD` |
| Rename reports target branch already exists | The new name is already in use | Check target branch contents; pick another name or only use `-M` when truly intending to replace |
| Cannot rename branch | Branch may be checked out in another worktree | Check `git worktree list` and coordinate releasing the branch |
| After rename, upstream still shows old name | Remote-tracking ref does not rename automatically with local | Check `git branch -vv`, push the new branch, and set upstream as needed |
| Other teammates still see the old name | Rename only changes your local ref | Notify the team and coordinate updating remote/clones |

## 23. Practical Workflow: Creating and Renaming a Feature Branch

Follow these steps in a test repository or a project repository according to your team's workflow:

### Step 1 — Check Status

~~~bash
git status -sb
git branch --show-current
git log --oneline --decorate -5
~~~

Confirm you are on the right base branch and have no merge/rebase in progress.

### Step 2 — Update the Base Branch

~~~bash
git fetch origin
git log --oneline --decorate -1 origin/main
~~~

If the team requires starting from `origin/main`, use this ref as the start point.

### Step 3 — Create the Branch

~~~bash
git switch -c feature/payment-summary origin/main
~~~

Verify:

~~~bash
git branch --show-current
git status -sb
~~~

### Step 4 — List Branches and Commit Info

~~~bash
git branch
git branch -a
git branch -vv
git branch --sort=-committerdate
~~~

Observe the `*` symbol, remote-tracking branches, and upstream details.

### Step 5 — Rename the Local Branch

If the branch name needs adjustment to match conventions:

~~~bash
git branch -m feature/payment-summary-v2
~~~

Verify:

~~~bash
git branch --show-current
git branch -vv
git reflog show feature/payment-summary-v2
~~~

### Step 6 — Hand Off the New Name

If the branch has never been pushed:

~~~bash
git push -u origin feature/payment-summary-v2
~~~

If the old branch was already shared, notify the team and handle the old remote branch according to policy. Do not delete the old remote branch before checking pull requests, pipelines, and active users.

## 24. Local Branch Management Checklist

- [ ] Checked the current branch with `git branch --show-current`.
- [ ] Viewed working tree status with `git status -sb`.
- [ ] Confirmed the right start point before creating a branch.
- [ ] Branch name follows team conventions and passes `git check-ref-format`.
- [ ] Distinguished `git branch` from `git switch -c`.
- [ ] Know how to list local, remote-tracking, and all branches.
- [ ] Checked the latest commit and upstream with `git branch -vv` when needed.
- [ ] Confirmed the target branch does not already exist before renaming.
- [ ] Understand that `-M` can replace the target branch.
- [ ] Checked other worktrees if a rename is refused.
- [ ] Coordinated with the team if the old branch was already pushed or attached to a pull request.

## 25. Knowledge Self-Check

1. What is a branch in Git and what object does it point to?
2. How does `git branch feature/x` differ from `git switch -c feature/x`?
3. How do you create a branch from `origin/main` without switching to the new branch?
4. What does the `*` symbol in `git branch` output indicate?
5. What information do `git branch -r`, `-a`, and `-vv` provide?
6. Why should you run `git fetch` before evaluating remote-tracking branches?
7. How do `git branch --merged main` and `--no-merged main` differ?
8. How do you rename the current branch and a non-checked-out branch?
9. How do `-m` and `-M` differ?
10. Does renaming a local branch automatically rename the branch on the remote?
11. What role does upstream play after a branch is pushed?
12. Why should you check `git worktree list` when renaming a branch is refused?

## Conclusion

`git branch` creates and lists local branches; `git switch -c` creates a branch and then switches to it. Use `git branch -a`, `-r`, `-v`, `-vv`, `--sort`, and `--format` to inspect branches along with their commits and upstreams. When renaming, `git branch -m` moves the local ref; `-M` allows replacing an existing target name and should be used with caution. A local rename does not automatically change branches on the remote or in teammates' clones, so check upstreams and coordinate updating shared references.

# Distinguishing git fetch, git pull, and git push

When working with a remote repository, the three commands `git fetch`, `git pull`, and `git push` frequently appear in the same workflow. They all exchange data between the local repository and the remote, but each command has a distinct purpose and effect:

- `git fetch` retrieves new commits, objects, and reference information from the remote to local so you can inspect them.
- `git pull` retrieves changes from the remote and then integrates them into the current branch according to the chosen merge or rebase policy.
- `git push` sends local commits to the remote and requests updating a branch or tag there.

Understanding these differences helps you know when local history changes, when the working tree may be affected, and what to do when both sides have diverged.

## 1. Local and Remote Model

When you clone a repository, your machine has a local repository with a working tree, staging area, commits, and local branches. The repository on a server such as GitHub, GitLab, or an internal Git server is the remote. The remote is commonly named `origin`, though that name is only a convention; a project can have multiple remotes.

For example, after cloning:

~~~
git clone https://example.com/team/shop.git
cd shop
git remote -v
~~~

The output of `git remote -v` might display:

~~~
origin  https://example.com/team/shop.git (fetch)
origin  https://example.com/team/shop.git (push)
~~~

The name `origin` is a remote name stored in local configuration. It is neither a branch nor a continuously live mirror of the server.

Git commonly uses three key reference types during synchronization:

| Reference | Meaning |
|---|---|
| `main` | Local branch that you can check out and create commits on |
| `origin/main` | Remote-tracking branch recording the most recent `main` position known locally from remote `origin` |
| `HEAD` | Indicates the repository's current position, usually attached to the checked-out branch |

`origin/main` does not automatically update the moment a teammate pushes to the server. It is updated only when you perform a retrieval operation such as `git fetch origin` or `git pull`. A remote-tracking branch is a local reference point for comparing history; you typically do not check it out or commit directly onto it.

## 2. `git fetch`: Downloading New Information for Inspection

`git fetch` contacts the remote, downloads missing objects, and updates remote-tracking branches according to the fetch configuration. This command does not automatically merge or rebase changes into the current local branch, does not move the current local branch, and does not overwrite working files.

Basic command:

~~~
git fetch origin
~~~

After fetching, you may see `origin/main` advance while local `main` remains at the older commit. This is intentional: Git has downloaded the data and given you the opportunity to review it before integrating.

### Inspecting changes after fetch

Suppose you are on the `main` branch. You can view commits present on the remote-tracking branch that are not yet in local:

~~~
git log --oneline main..origin/main
~~~

The reverse direction shows local commits not yet in the remote-tracking reference:

~~~
git log --oneline origin/main..main
~~~

To observe the relationship between branches:

~~~
git log --oneline --graph --decorate --all
git status -sb
~~~

You can also view content differences between the two points:

~~~
git diff main..origin/main
~~~

These comparison commands are useful before deciding to merge or rebase. Remember that `origin/main` reflects the most recent fetch; if you need the latest data from the server, fetch before drawing conclusions.

### Fetching a single branch and pruning stale references

Normally `git fetch origin` retrieves references according to the remote's configuration. You can also request fetching a specific branch:

~~~
git fetch origin main
~~~

If a remote branch has been deleted, the corresponding remote-tracking branch may remain locally until cleaned up. Use `--prune` to remove remote-tracking refs no longer advertised by the remote:

~~~
git fetch --prune origin
~~~

This command only cleans up local tracking references. It does not delete branches on the server. If you have multiple remotes:

~~~
git fetch --all --prune
~~~

`--all` requests fetching from all configured remotes; `--prune` applies stale reference cleanup to those fetches.

### When should you use fetch?

Use fetch when you want to update your information before integrating, for example:

- Before starting work to see what teammates have pushed.
- Before merging or rebasing a branch.
- When you need to review diffs, commits, or inspect changes from the remote.
- When you want to update multiple remote-tracking branches without changing your current branch yet.

Fetch is a controlled inspection step: new data is now in the local repository, while the decision to integrate remains yours.

## 3. `git pull`: Retrieving Changes and Integrating Into the Current Branch

`git pull` is a combined operation: first it fetches data from the remote, then it integrates the upstream branch into the current local branch. How integration happens depends on the options you pass and your Git configuration.

~~~
git pull
~~~

Without arguments, the command normally uses the remote and upstream branch configured for the current branch. For example, if `main` tracks `origin/main`, Git fetches from `origin` and then integrates `origin/main` into local `main`.

### Pulling with merge

With the merge strategy, Git brings upstream history into the current branch. If local is simply behind the remote and has no separate commits to combine, Git can fast-forward: moving the local branch forward to the newer commit without creating a merge commit.

If both local and remote have their own commits, the histories have diverged. Merge combines them and may create a merge commit:

~~~
git pull --no-rebase
~~~

You can visualize a diverged situation like this:

~~~text
          L1---L2  main (local)
         /
A---B---C
         \
          R1---R2  origin/main
~~~

After merging, the history contains a commit combining both branches:

~~~text
          L1---L2
         /       \
A---B---C---------M  main
         \       /
          R1---R2
~~~

Merge preserves the original branching relationship. This is useful when you want to explicitly show that separate lines of work were combined.

### Pulling with rebase

With rebase, Git takes local commits not yet on upstream, moves the local branch to the latest upstream commit, and replays the local commits on top:

~~~
git pull --rebase
~~~

The result usually has a more linear history. However, rebase creates new commits for the replayed changes, so commit IDs will change. You should only rebase unshared local commits or follow a team-agreed workflow rule. Never arbitrarily rebase a public branch that multiple people rely on.

### Pulling only when fast-forward is possible

If you want to update local without creating a merge commit and without rewriting local commits, you can request:

~~~
git pull --ff-only
~~~

The command succeeds when the current branch can advance directly to upstream. If both sides have separate commits, Git stops and asks you to resolve the divergence. This is a useful option when a team wants the main branch history to advance only via fast-forward.

### Why does `git pull` sometimes produce different results?

Git can be configured for how to handle diverged local and upstream branches. Common configurations include:

~~~
git config pull.rebase false
git config pull.rebase true
git config pull.ff only
~~~

The commands above select merge, rebase, or fast-forward-only respectively for the current repository. You can use `--global` instead of repository-level configuration if you want it to apply across your user repositories. Command-line options such as `--rebase`, `--no-rebase`, or `--ff-only` make your intent explicit for a specific pull.

If Git reports that you need to specify how to reconcile divergent branches, choose the policy that fits your project's conventions. Do not pick one at random just to make the command pass; merge and rebase produce different histories.

### Pull can cause conflicts

If changes from remote and local edit the same region in a way that cannot be combined automatically, merge or rebase may pause with a conflict. When that happens:

1. Use `git status` to identify conflicted files.
2. Open each file, inspect the conflict markers, and edit to the desired content.
3. Use `git add <file>` to mark the file as resolved.
4. If merging, complete with `git commit` when Git prompts. If rebasing, continue with `git rebase --continue`.
5. If you need to cancel the operation in progress, use `git merge --abort` or `git rebase --abort` respectively.

Do not delete conflict markers mechanically. Understand both changes and confirm the result remains functionally correct. When there are uncommitted changes in the working tree, commit or stash them appropriately before pulling to avoid disrupting your work.

## 4. `git push`: Sending Local Commits to the Remote

`git push` sends the required objects and requests that the remote update a branch or tag. For example:

~~~
git push origin main
~~~

This command requests updating the `main` branch on remote `origin` with the corresponding local history. Push does not automatically download new commits from the remote and does not integrate teammates' changes into your local branch.

### Pushing a branch for the first time and setting upstream

When creating a new local branch, the remote may not yet have a matching branch. The first push typically uses `-u` or `--set-upstream`:

~~~
git switch -c feature/payment
git push -u origin feature/payment
~~~

This command pushes the branch to `origin` and sets the upstream relationship for the local branch. Next time, while on that branch, you usually only need:

~~~
git push
~~~

An upstream is the remote branch that a local branch uses as its tracking reference. You can inspect this relationship with:

~~~
git branch -vv
~~~

If a branch already exists without an upstream, you can set it explicitly:

~~~
git branch --set-upstream-to=origin/feature/payment feature/payment
~~~

Setting an upstream lets `git status`, `git pull`, and argument-free push commands know the associated remote branch. If a branch tracks the wrong remote or wrong branch, inspect with `git branch -vv` and fix the configuration before synchronizing.

### Why can a push be rejected?

A remote normally rejects a fast-forward push if the branch on the server has moved ahead with commits local does not yet have. For example, a teammate pushed commit `R1` to `origin/main` while your local branch was still based on an older commit and created `L1`:

~~~text
A---B---R1  origin/main
     \
      L1   main (local)
~~~

If `L1` were pushed immediately, updating the remote would drop `R1`, so Git rejects it with a non-fast-forward error. This protects history from accidental overwrites.

The typical resolution workflow is to fetch, inspect history, and integrate remote changes:

~~~
git fetch origin
git log --oneline --graph --decorate --all
git pull --rebase
~~~

Or use merge according to team policy:

~~~
git pull --no-rebase
~~~

After resolving conflicts (if any), verify status and push:

~~~
git status
git push
~~~

If the branch is protected or the account lacks write permission, push can also be rejected even when local history is up to date. In that case, follow the pull request workflow or request appropriate permissions; do not attempt to bypass branch protection policies.

### Caution with force push

`git push --force` can move the remote reference to match local history and discard commits others have pushed. Do not use this command to handle normal non-fast-forward errors.

When a team intentionally rewrites history on a dedicated branch, `--force-with-lease` adds a check verifying that the remote is still at the commit local expects:

~~~
git push --force-with-lease origin feature/payment
~~~

This option reduces the risk of overwriting new commits you were unaware of, but it is still a history-rewriting operation on the remote. Only use it when you understand the impact, have coordinated with collaborators on the branch, and have a specific reason. It does not replace fetching, reviewing, and aligning with the team.

## 5. Quick Comparison of the Three Commands

| Criterion | `git fetch` | `git pull` | `git push` |
|---|---|---|---|
| Primary transfer direction | Remote to local | Remote to local, then integrate | Local to remote |
| Updates objects in local repository | Yes | Yes, via fetch | Not its purpose |
| Updates remote-tracking branch | Yes | Yes, via fetch | No |
| Moves current local branch | No | Possibly, depending on merge/rebase/fast-forward | No |
| Can modify working tree | Does not integrate into working tree | Yes | No |
| Can create conflicts | No during fetch step | Yes, during integration | Typically rejected if non-fast-forward; does not resolve conflicts |
| Typical purpose | Update info for inspection | Sync and integrate upstream | Share commits with others |

A quick way to remember:

- **Fetch:** updates what local knows about the remote.
- **Pull:** retrieves changes and brings them into the current branch.
- **Push:** sends local changes to the remote.

## 6. Common Synchronization Workflows

### Updating the main branch before working

If local `main` tracks `origin/main` and the team uses fast-forward-only:

~~~
git switch main
git fetch origin
git status -sb
git log --oneline main..origin/main
git pull --ff-only
~~~

If your team uses rebase for local branches, replace the last step with `git pull --rebase`. If your team uses merge, use `git pull --no-rebase`. What matters is applying your repository's policy consistently.

### Working on a feature branch

~~~
git switch -c feature/payment
# edit files
git add .
git commit -m "Add payment flow"
git push -u origin feature/payment
~~~

While working, if teammates update the upstream branch:

~~~
git fetch origin
git log --oneline --graph --decorate --all
git pull --rebase
git push
~~~

This example assumes the feature branch has an upstream and the team permits rebasing the branch's own commits. If multiple people are actively using the branch, coordinate before rebasing or choose merge.

### Checking before pushing

Before sharing commits, review the current branch, working tree status, and relationship with upstream:

~~~
git status -sb
git branch -vv
git log --oneline --decorate -5
git diff
git diff --cached
~~~

`git diff` shows unstaged changes; `git diff --cached` shows staged changes. Once you confirm the commits are accurate and the branch is based on the right history, perform the push.

## 7. Common Misconceptions

**Thinking fetch already updated the local branch.** Fetch updates objects and remote-tracking refs. A local branch changes only when you perform an integration step such as merge, rebase, or fast-forward.

**Thinking pull is always just fetch then merge.** Pull always fetches first, but the integration step can be merge, rebase, or fast-forward-only depending on options and configuration.

**Thinking push automatically downloads the latest changes.** Push sends local data to the remote. If the remote has new commits that local has not integrated, push may be rejected.

**Confusing `origin/main` with `main`.** `main` is typically a local branch; `origin/main` is a remote-tracking branch recording the most recent sync with the remote. The two references can point to different commits.

**Using force push to bypass every push error.** A non-fast-forward error usually indicates local has not integrated new history from the remote. Fetch and inspect history first; force push can lose other people's commits.

**Assuming a successful push means changes are released.** Push only updates the remote repository. Building, testing, reviewing, and deploying depend on your project's workflow.

## 8. Command Selection Checklist

- [ ] Want to see what changed on the remote without touching the current branch: use `git fetch`.
- [ ] Already reviewed changes and want to integrate upstream into the current branch: use `git pull` with the agreed strategy.
- [ ] Want to share local commits to the server: use `git push`.
- [ ] Push rejected as non-fast-forward: fetch, inspect history, integrate remote commits, then push again.
- [ ] New branch does not exist on the remote yet: push the first time with `git push -u origin <branch>`.
- [ ] Unsure which remote a branch tracks: inspect with `git remote -v` and `git branch -vv`.

When collaborating, treat fetch as the information-update step, pull as the integration step, and push as the history-sharing step. Choosing the right operation and knowing which branch will move helps you synchronize repositories intentionally, reduce conflicts, and avoid overwriting teammates' work.

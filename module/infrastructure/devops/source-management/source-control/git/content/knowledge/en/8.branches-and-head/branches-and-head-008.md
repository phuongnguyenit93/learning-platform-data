# Distinguishing Local Branches, Remote Branches, and Upstreams

When working with remotes, Git has several branch-like names that represent different things. For example, `main` is a local branch, `origin/main` is typically a remote-tracking branch stored in the local repository, and "the upstream of main" is the branch that the local `main` branch is configured to track. These three concepts are related, yet not synonymous.

Understanding the exact relationship helps you know what `fetch` updates, where `pull` retrieves data from, which branch `push` sends, and why ahead/behind counts sometimes do not yet reflect the latest state on the server.

This lesson belongs to the **Branches and HEAD** chapter of the `SOURCE_CONTROL_GIT` module. The module covers the working tree, staging area, commits, history, branches, merging, rebasing, remotes, and tags; properly managing local branches, remote-tracking branches, and upstreams is the foundation for collaborating safely across multiple remotes.

## 1. Three Concepts to Distinguish

| Concept | Example | Where does it live? | Role |
| --- | --- | --- | --- |
| Local branch | `main`, `feature/payment` | Local repository, ref `refs/heads/...` | Branch you directly check out and commit to |
| Remote-tracking branch | `origin/main`, `upstream/develop` | Local repository, ref `refs/remotes/...` | Records the state of a branch on the remote at the most recent fetch |
| Upstream branch | Upstream of local `main` can be `origin/main` | Configured per local branch | Default target for comparing ahead/behind and used in pull/push according to configuration |

A remote named `origin` is not a branch. `origin` is simply the nickname for a remote repository. `origin/main` is the remote-tracking branch corresponding to the `main` branch on the remote named `origin`.

Similarly, the term "upstream" has two common usages:

- **Upstream branch**: the branch that a local branch is configured to track.
- **A remote named upstream**: a nickname commonly given to the original repository in a fork workflow.

These are two independent concepts. The upstream branch of local `feature/payment` can be `origin/feature/payment` even if there is no remote named `upstream`.

## 2. What Is a Local Branch?

A local branch is a ref in the local repository, usually under `refs/heads/`. It points to the current commit of the branch. When you create a commit on the checked-out branch, the branch ref moves to the new commit.

List local branches:

~~~bash
git branch
~~~

View the current branch name:

~~~bash
git branch --show-current
~~~

View the commit that the current branch points to:

~~~bash
git rev-parse HEAD
~~~

Create a new local branch:

~~~bash
git branch feature/payment
~~~

This command creates the branch without switching to the new branch. To create and switch immediately:

~~~bash
git switch -c feature/payment
~~~

A local branch is where you normally create commits, merge, or rebase. You can rename branches, delete merged branches, or keep branches as work milestones according to team conventions.

## 3. Remotes and Remote-Tracking Branches

A remote is a configuration pointing to another repository. When cloning, Git usually creates a remote named `origin`:

~~~bash
git remote -v
~~~

Example:

~~~text
origin  https://example.com/team/app.git (fetch)
origin  https://example.com/team/app.git (push)
~~~

The name `origin` is just a conventional name. You can add another remote:

~~~bash
git remote add upstream https://example.com/platform/app.git
git remote -v
~~~

Git stores remote-tracking refs locally. For example, the `main` branch on the `origin` remote is normally represented as:

~~~text
refs/remotes/origin/main
~~~

When displayed in short form, Git uses the name `origin/main`.

List remote-tracking branches:

~~~bash
git branch --remotes
~~~

List both local branches and remote-tracking branches:

~~~bash
git branch --all
~~~

### A Remote-Tracking Branch Is Not a Live Branch Running on the Server

`origin/main` is a local record of the `main` branch's state on the remote at the most recent fetch. It does not update in real time when someone pushes to the server.

Example:

1. At the last fetch, `origin/main` pointed to commit A.
2. A teammate pushes commit B to the `main` branch on the server.
3. Your machine still shows `origin/main` pointing to A until you fetch.
4. After `git fetch origin`, Git updates the remote-tracking ref to B.

Therefore, when you want to know the latest state published by the server, fetch before concluding whether a local branch is ahead or behind.

To query the branches currently advertised by the remote directly without relying on the local remote-tracking cache:

~~~bash
git ls-remote --heads origin
~~~

This command lists branch refs from the remote. It does not automatically update remote-tracking refs in your local repository.

## 4. What Is an Upstream Branch?

An upstream branch is a branch configured as the tracked branch for a local branch. In a common workflow, the upstream of local `main` is `origin/main`.

Configuring an upstream tells Git:

- Which branch to use when calculating ahead/behind status.
- Which branch `git pull` uses when you do not specify a source.
- The default target branch for certain uses of `git push`, depending on push configuration.

An upstream is not a second copy of a local branch. It is a configuration relationship between a local branch and another branch.

### Viewing a Branch's Upstream

Use:

~~~bash
git branch -vv
~~~

Example:

~~~text
* main             a1b2c3d [origin/main: ahead 2] Update invoice flow
  feature/payment  e4f5a6b [origin/feature/payment: behind 1] Add payment form
~~~

In the example:

- Local `main` has `origin/main` as its upstream and is ahead by 2 commits according to currently available local info.
- Local `feature/payment` has `origin/feature/payment` as its upstream and is behind by 1 commit.

These counts are calculated from currently existing local refs. If you have not fetched recently, they may be stale.

View the upstream of the current branch with:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

If the current branch has no upstream configured, this command reports an error because it cannot resolve `@{upstream}`.

### Viewing Detailed Upstream Configuration

Git stores the relationship under configuration keys such as:

- `branch.main.remote`: the remote that the `main` branch tracks, for example `origin`.
- `branch.main.merge`: the branch ref on the remote, for example `refs/heads/main`.

Verify:

~~~bash
git config --get branch.main.remote
git config --get branch.main.merge
~~~

View branches that have remote/merge configurations set:

~~~bash
git config --get-regexp '^branch\..*\.(remote|merge)$'
~~~

This configuration lets Git resolve the upstream. If the remote or target branch is renamed/deleted, the tracking relationship may no longer be valid.

## 5. Creating a Local Branch with an Upstream from the Start

When cloning a repository, Git normally sets up the default local branch to track the corresponding remote-tracking branch. For new branches, you can create the tracking relationship at branch creation time.

### Creating a Branch from a Remote-Tracking Branch and Switching to It

~~~bash
git switch --track origin/feature/payment
~~~

Git creates the local branch `feature/payment` from `origin/feature/payment` and configures the corresponding upstream if the branch name can be inferred unambiguously.

If you want to specify the local branch name explicitly:

~~~bash
git switch --create feature/payment --track origin/feature/payment
~~~

### Creating a Branch Without Switching to It Yet

~~~bash
git branch --track feature/payment origin/feature/payment
~~~

This command creates the local branch and sets the upstream while keeping the currently checked-out branch unchanged.

### Creating a New Branch from the Current Branch

~~~bash
git switch -c feature/payment
~~~

This command creates a new local branch from the current commit. An upstream is not automatically configured in every case. On the first push, you can set the upstream with:

~~~bash
git push --set-upstream origin feature/payment
~~~

Short form:

~~~bash
git push -u origin feature/payment
~~~

The `-u` option saves the tracking relationship for the local branch, typically `branch.feature/payment.remote=origin` and `branch.feature/payment.merge=refs/heads/feature/payment`.

## 6. Attaching or Changing the Upstream of an Existing Branch

If a local branch already exists without an upstream, or you want to change its upstream to another branch, use:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

This command sets `origin/main` as the upstream for the local branch `main`. If you omit the final local branch name, Git uses the current branch:

~~~bash
git branch --set-upstream-to=origin/main
~~~

Verify the result:

~~~bash
git branch -vv
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

Changing the upstream only changes tracking configuration. It does not automatically fetch, merge, rebase, reset, or push commits. If the target branch has not been fetched locally yet, update remote-tracking refs first:

~~~bash
git fetch origin
git branch --set-upstream-to=origin/main main
~~~

### Unsetting the Upstream

If you no longer want a local branch to track any branch:

~~~bash
git branch --unset-upstream main
~~~

Or apply to the current branch:

~~~bash
git branch --unset-upstream
~~~

The local branch still exists and no commits are lost. Git only removes the tracking relationship.

## 7. How Does Fetch Update Remote-Tracking Branches?

The command:

~~~bash
git fetch origin
~~~

retrieves objects and refs from the `origin` remote, then updates remote-tracking refs according to the configured fetch refspec. It does not automatically merge new commits into the currently checked-out local branch.

Example before fetch:

~~~text
main        -> A
origin/main -> A
~~~

After a teammate pushes B to the server, fetching updates your local state to:

~~~text
main        -> A
origin/main -> B
~~~

Local `main` still points to A. The remote-tracking branch `origin/main` has updated to B.

To update refs from all remotes:

~~~bash
git fetch --all
~~~

If you want to clean up remote-tracking refs whose corresponding branch no longer exists on the remote:

~~~bash
git fetch --prune origin
~~~

Or preview stale refs that would be pruned:

~~~bash
git remote prune --dry-run origin
~~~

Pruning deletes local remote-tracking refs that have disappeared on the remote; it does not delete local branches such as `main` or `feature/payment`. However, before pruning, make sure you do not need to keep any stale ref as a reference point.

## 8. How Does Pull Use the Upstream?

`git pull` combines fetch with a step that integrates history into the current branch. When no remote and branch are specified, Git normally uses the upstream configured for the current branch.

For example, if local `main` tracks `origin/main`:

~~~bash
git switch main
git pull
~~~

Git fetches from the corresponding remote and then integrates changes from the upstream into `main`. How it integrates depends on options and configuration, commonly merge or rebase.

Choose the integration method explicitly when needed:

~~~bash
git pull --rebase
~~~

Or require fast-forward only:

~~~bash
git pull --ff-only
~~~

`--rebase` replays local commits on top of the newly fetched history; `--ff-only` updates only when a fast-forward is possible, otherwise stopping for you to handle. Understand your team's policy before choosing a default configuration.

If the branch does not have an upstream yet, `git pull` lacks default information on where to fetch from and which branch to integrate. Set up tracking or specify the remote and branch in the command.

## 9. Push and Upstream

An upstream can also help Git determine where to push. However, default push behavior is governed by `push.default` and related settings.

Check configuration:

~~~bash
git config --get push.default
~~~

If unconfigured, modern Git normally uses `simple` mode. In the common case, this mode requires the local branch and its upstream to share the same name before pushing.

Push the current branch and set the upstream for the first time:

~~~bash
git push -u origin HEAD
~~~

`HEAD` in the source position denotes the current branch/commit; this command is useful when you want to create the corresponding branch on the remote and set up tracking.

Once the upstream is configured, the command:

~~~bash
git push
~~~

can use the tracking relationship along with the `push.default` policy to determine where to send commits. When working with multiple remotes or special branches, specifying the remote and branch explicitly reduces confusion:

~~~bash
git push origin feature/payment
~~~

Do not assume the upstream is always the push target in every configuration. An upstream is primarily a tracking relationship; push behavior is also influenced by `push.default`, refspecs, and push options.

## 10. Working with Multiple Remotes: origin and upstream

In a typical fork workflow:

- `origin` usually points to your fork, where you have push permissions.
- `upstream` usually points to the original project repository, from which you fetch new changes.

Add the original remote:

~~~bash
git remote add upstream https://example.com/original/app.git
git remote -v
~~~

Update branches from the original project:

~~~bash
git fetch upstream
~~~

Now you can see remote-tracking branches such as `upstream/main`. This is a local ref reflecting the main branch of the remote nicknamed `upstream` after the most recent fetch.

A common setup:

| Local branch | Upstream branch | Purpose |
| --- | --- | --- |
| `main` | `upstream/main` | Track the official history of the original project |
| `feature/payment` | `origin/feature/payment` | Track your working branch on your personal fork |

You can integrate changes from `upstream/main` into local `main` and then push the result to `origin` according to the contribution workflow. However, a remote named `upstream` does not automatically become the upstream branch for every local branch; each branch has its own tracking configuration.

## 11. What Do Ahead, Behind, and Diverged Mean?

When a local branch has an upstream, Git can compare the two branch tips based on their common ancestor:

- **Ahead N:** the local branch has N commits that the upstream does not have yet.
- **Behind N:** the upstream has N commits that the local branch does not have yet.
- **Diverged:** both sides have their own commits since the common ancestor.

Check status:

~~~bash
git status --short --branch
git branch -vv
~~~

You can count unique commits on each side with:

~~~bash
git rev-list --left-right --count '@{upstream}...HEAD'
~~~

The output contains two numbers: the number of commits only in upstream and the number of commits only in HEAD. Since the argument order is upstream first and HEAD second, read them in the proper order when interpreting.

Ahead/behind information relies on the local remote-tracking branch. If you have not fetched, it does not necessarily reflect the current branch on the server. Update before evaluating:

~~~bash
git fetch
git status -sb
~~~

Do not force-push just because you see diverged. First view the graph and inspect the commits on both sides:

~~~bash
git log --oneline --graph --decorate --left-right 'HEAD...@{upstream}'
~~~

In some shells, the `@{upstream}` notation needs to be quoted so the shell does not interpret it before Git receives the command.

## 12. What Is the Impact of Renaming or Removing a Remote?

Rename a remote:

~~~bash
git remote rename origin personal
~~~

Git renames the remote and the corresponding remote-tracking refs. Branches tracking that remote should also have their tracking configuration checked; Git usually updates several related settings when renaming a remote.

Remove a remote:

~~~bash
git remote remove old-origin
~~~

This operation removes the remote configuration and its remote-tracking refs. Local branches and local commits are not automatically deleted, but upstreams pointing to the removed remote will no longer resolve.

After renaming or removing a remote, check:

~~~bash
git remote -v
git branch -vv
git config --get-regexp '^branch\..*\.(remote|merge)$'
~~~

If needed, reset the upstream for a branch:

~~~bash
git branch --set-upstream-to=personal/main main
~~~

## 13. Common Errors and Resolutions

| Symptom | Possible cause | How to check or resolve |
| --- | --- | --- |
| `git pull` reports no tracking information | Local branch has no upstream yet | Fetch then use `git branch --set-upstream-to` or specify remote/branch |
| `git push` does not know where to push | No upstream yet or push policy does not match | Use `git push -u origin HEAD` or specify remote and branch explicitly |
| `origin/main` does not show new commits | Have not fetched or fetch refspec does not fetch that branch | Run `git fetch origin` and check `git remote show origin` |
| Branch reports unexpected ahead/behind | Remote-tracking ref is stale | Fetch then recheck `git status -sb` and `git branch -vv` |
| Upstream no longer exists | Remote or branch on server was renamed/deleted | Check remote, fetch/prune, and attach a new upstream |
| Checking out `origin/main` creates detached HEAD | Checked out the remote-tracking ref directly instead of creating a local branch | Use `git switch --track origin/main` |
| Two branches share a similar name causing source confusion | Local branch and remote-tracking branch have similar names | Use full names and check `git branch -vv` |
| Fork has new commits but local does not see them | Have not fetched the right remote or upstream is misconfigured | Check `git remote -v`, fetch the right remote, and inspect tracking |

## 14. Workflow for Inspecting Branches and Upstreams

When receiving a new repository or switching to another machine, you can use the following sequence:

~~~bash
# 1. View remotes
git remote -v

# 2. Update remote-tracking refs
git fetch --all --prune

# 3. View local and remote-tracking branches
git branch --all

# 4. View upstreams and ahead/behind
git branch -vv

# 5. Determine the upstream of the current branch
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'

# 6. View tracking config if needed
git config --get-regexp '^branch\..*\.(remote|merge)$'
~~~

If a branch does not have an upstream yet, explicitly decide which branch it should track. For example:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

If a new branch does not yet exist on the remote, push for the first time and configure tracking:

~~~bash
git push -u origin HEAD
~~~

Then verify again:

~~~bash
git status -sb
git branch -vv
~~~

## 15. Relationship Diagram

~~~mermaid
flowchart TD
    A[Remote repository: origin] -->|git fetch| B[Remote-tracking ref: origin/main]
    B -->|configured as upstream| C[Local branch: main]
    C -->|git commit| D[New commit on local main]
    D -->|git push| A
    B -->|git pull: fetch then merge/rebase| C
~~~

The diagram illustrates the roles:

- The remote repository is where branches are stored on the server.
- A remote-tracking branch is a local record updated via fetch.
- A local branch is the branch you directly work on.
- An upstream is the configuration relationship between a local branch and its tracked branch.

Before finishing, confirm for yourself:

1. Do I distinguish a remote nickname from a remote-tracking branch?
2. Do I know that `origin/main` is a local ref reflecting the most recent fetch?
3. Does the current local branch have an upstream yet, and which branch exactly is that upstream?
4. Did I fetch before relying on ahead/behind information?
5. Do I understand that pull integrates the upstream while push is also affected by push policy?
6. When working with a fork, have I distinguished a remote named `upstream` from the concept of an upstream branch?

A local branch is where you develop and create commits; a remote-tracking branch remembers the remote state as of the most recent fetch; an upstream is the configuration relationship that helps Git pick the tracking source for a local branch. Once you distinguish these three layers, you can fetch, pull, push, switch remotes, and handle ahead/behind states without confusing a local branch with the server state.

## References

- [Git documentation: git-branch](https://git-scm.com/docs/git-branch) — listing branches, verbose output, tracking, and setting/unsetting upstream.
- [Git documentation: git-fetch](https://git-scm.com/docs/git-fetch) — updating remote-tracking refs and pruning.
- [Git documentation: git-pull](https://git-scm.com/docs/git-pull) — fetching and integrating upstream.
- [Git documentation: git-push](https://git-scm.com/docs/git-push) — push policy, upstream, and setting upstream.
- [Git documentation: git-remote](https://git-scm.com/docs/git-remote) — managing remotes and remote-tracking branches.
- [Pro Git: Remote Branches](https://git-scm.com/book/en/v2/Git-Branching-Remote-Branches) — local branches, remote-tracking branches, and tracking branches.

# Connecting Multiple Remotes for the Canonical Repository and a Fork

When contributing to an open-source project or collaborating via forks, developers usually work with at least two remote repositories: the project's **canonical repository** and a **fork** under their own account. The canonical repository is where the team maintains the official version; the fork is your own repository where you have permission to push working branches. Git allows a single local repository to store multiple remotes so you can pull changes from one place and send your work to another.

A common pattern is setting the `upstream` remote to point to the canonical repository and `origin` to point to your fork. You fetch from `upstream` to stay up to date with the project, create working branches from the latest history, and then push branches to `origin` to open a pull request or merge request back to the canonical repository.

## 1. Distinguishing the Canonical Repository, Fork, and Remote

**Canonical repository** is the source code repository that the project treats as the official source. The team maintains this repository, reviews contributions, and integrates changes.

**Fork** is an independent repository created from another repository on a code hosting platform. A fork usually belongs to a contributor's personal account or organization. You can have write permissions to your fork even when you only have read access to the canonical repository.

**Remote** is a configuration name in the local repository used to reference a remote repository. The names `origin` and `upstream` are simply common conventions:

| Common Name | Points To | Common Purpose |
|---|---|---|
| `origin` | Your fork | Push personal branches and store work in progress on the server |
| `upstream` | The project's canonical repository | Fetch new changes from the original project |

Git does not inherently treat `origin` as a fork or `upstream` as the canonical repository. They are simply user-defined aliases. You can name them `my-fork`, `canonical`, or anything else; what matters is knowing where each name points.

A fork is also not a Git branch. A fork is a separate repository on the hosting service; branches such as `main` or `feature/login` are commit references inside each repository. Creating a fork is usually done in the web interface of GitHub, GitLab, or a similar service. The `git remote add` command only registers that repository's address in the local repository; it does not create a fork on the server.

## 2. Common Connection Model

Suppose the original project is at `https://github.com/example-org/sample-app.git`, and your fork is at `git@github.com:my-account/sample-app.git`.

```text
       Project's canonical repository
       https://github.com/example-org/sample-app.git
                       |
                       | fetch
                       v
              Remote: upstream
                       |
                       v
             Local repository
                       |
                       | push
                       v
               Remote: origin
                       |
                       v
                  Your fork
       git@github.com:my-account/sample-app.git
```

In the local repository, after fetching, you typically see remote-tracking branches such as `upstream/main` and `origin/main`. These are local references recording the branch states known on each remote at the time of the last fetch. They are not working branches that you edit directly.

The `main` branch is your local branch. You can update it from `upstream/main`, then push the result to `origin/main` to synchronize your fork. Feature branches are usually created from `upstream/main` or from an already synchronized `main`.

## 3. Cloning the Fork and Adding the Canonical Repository Remote

In a typical fork workflow, you first create the fork on the code hosting platform. Then clone the fork to your machine:

```bash
# Clone your fork
git clone git@github.com:my-account/sample-app.git
cd sample-app

# Check the remote created automatically by git clone
git remote -v
```

The `git clone` command usually creates a remote named `origin` pointing to the URL used for cloning. Because the URL above belongs to your fork, `origin` will point to your fork.

Next, add the canonical repository under the name `upstream`:

```bash
git remote add upstream https://github.com/example-org/sample-app.git

# Check both remotes
git remote -v
```

The output looks like:

```text
origin    git@github.com:my-account/sample-app.git (fetch)
origin    git@github.com:my-account/sample-app.git (push)
upstream  https://github.com/example-org/sample-app.git (fetch)
upstream  https://github.com/example-org/sample-app.git (push)
```

Usually you only need read access from `upstream`. If you do not have write permissions to the canonical repository, do not configure or use it as a push destination. The URLs in the example can use HTTPS or SSH depending on the authentication method supported by your organization.

If the `upstream` remote already exists, do not add it again. Check with `git remote -v`; if the address is wrong, update it with:

```bash
git remote set-url upstream https://github.com/example-org/sample-app.git
```

## 4. Fetching from Each Remote and Reading Remote-Tracking Branches

Each remote can have its own history and branches. Use the remote name to choose the fetch source:

```bash
# Fetch new branches and commits from the canonical repository
git fetch upstream

# Fetch the latest state from your fork
git fetch origin

# List remote-tracking branches
git branch -r

# View local branches along with their tracked upstream branches
git branch -vv
```

After `git fetch upstream`, Git updates references such as `upstream/main` according to the configured fetch refspec. After `git fetch origin`, references such as `origin/main` are updated. Fetch does not automatically merge these changes into `main` and normally does not modify the working tree.

You can inspect commit history between two branches:

```bash
# Commits present in the canonical repository but not yet in local main
git log --oneline main..upstream/main

# Commits present in local main but not yet in upstream/main
git log --oneline upstream/main..main

# View the history graph of all remotes and local branches
git log --oneline --graph --decorate --all
```

The two `A..B` expressions represent commits reachable from `B` but not reachable from `A`. They help identify which branch is ahead or has diverged with its own changes.

## 5. Synchronizing the Local Main Branch with the Canonical Repository

Forks often fall behind the canonical repository as the project team continues integrating changes. You should synchronize your fork's main branch before starting new work.

First, ensure the working tree has no unhandled changes:

```bash
git status
```

If there are uncommitted edits, commit or stash them appropriately before switching branches or integrating history. Then fetch and update `main`:

```bash
# Retrieve the latest state of the canonical repository
git fetch upstream

# Switch to the local main branch
git switch main

# Update only if main can advance directly to upstream/main
git merge --ff-only upstream/main
```

`--ff-only` requires a fast-forward update. If local `main` is simply behind `upstream/main`, Git advances the `main` branch to the new commit without creating a merge commit. If the two histories have diverged, the command stops so you can review how to integrate them.

Once local `main` is updated, push it to your fork:

```bash
git push origin main
```

This command updates the `main` branch on your fork if the server permits it and the history satisfies update rules. If the fork has its own commits or has diverged, inspect the graph and follow your project's agreed workflow. You may use merge or rebase per team policy; do not use force push merely to make the command succeed.

If your team allows rebasing and local `main` has unshared local commits, one option is:

```bash
git fetch upstream
git switch main
git rebase upstream/main
```

Rebase replays local `main`'s unique commits on top of `upstream/main` and creates new commits. If conflicts arise, resolve each file, then run `git add` and `git rebase --continue`; if you need to return to the state before rebasing, use `git rebase --abort`. Follow project rules, especially if those commits have already been shared with others.

## 6. Creating a Feature Branch from the Canonical Repository and Pushing to Your Fork

When starting a new change, branch from an up-to-date base. You can create a branch directly from a remote-tracking branch:

```bash
# Update information from the canonical repository
git fetch upstream

# Create a new branch from upstream/main
git switch -c feature/search upstream/main
```

Make edits, review changes, and commit on the `feature/search` branch:

```bash
git status
git add src/search
git commit -m "Add search support"
```

Then push the branch to your fork:

```bash
git push -u origin feature/search
```

The `-u` (or `--set-upstream`) option sets the default remote-tracking branch for the local branch. In this case, local `feature/search` will track `origin/feature/search`. Subsequent pushes or pulls can use the branch defaults without retyping the full remote and branch names.

On the code hosting platform, create a pull request or merge request with:

- **Source/head:** your fork, branch `feature/search`.
- **Target/base:** the canonical repository, branch `main` (or the target branch specified by the project).

The fork hosts your branch for others to review; the canonical repository receives the changes once approved and integrated.

## 7. Updating a Feature Branch When the Canonical Repository Has New Commits

While you are developing, `upstream/main` may continue changing. Fetch periodically to see the latest state:

```bash
git fetch upstream
git switch feature/search
```

If team policy requires a linear history and only you are using the branch, you can rebase the feature branch onto the new base:

```bash
git rebase upstream/main
```

If conflicts occur, Git pauses the rebase. Open the reported files, resolve the contents, mark them as resolved, and continue:

```bash
git add src/search/SearchService.java
git rebase --continue
```

If you decide not to continue:

```bash
git rebase --abort
```

Rebase changes the commit IDs of the replayed commits. If the branch is shared among multiple people, coordinate before rewriting history; in that case, merging `upstream/main` into the feature branch may be more appropriate:

```bash
git merge upstream/main
```

After integrating, push the branch to your fork:

```bash
git push origin feature/search
```

If you already pushed the branch before rebasing, a regular push may be rejected because the remote history is no longer an ancestor of the local history. Evaluate the impact and your team's guidelines before updating a shared branch; do not blindly use `--force`.

## 8. Understanding the Two Upstream Concepts Correctly

In Git, the word "upstream" appears in two easily confused contexts:

1. **A remote named `upstream`:** a user-chosen alias, usually pointing to the project's canonical repository.
2. **The upstream branch of a local branch:** the remote-tracking branch that a local branch is configured to track, such as `origin/feature/search`.

These two concepts are not synonymous. A local branch can track `origin/main`, `upstream/main`, or another branch depending on configuration. After `git push -u origin feature/search`, the upstream branch of `feature/search` is usually `origin/feature/search`, even though the canonical repository is still given the remote name `upstream`.

Check tracking configuration:

```bash
git branch -vv
```

If you need to change which branch local `main` tracks:

```bash
git branch --set-upstream-to=upstream/main main
```

This command only changes the tracking configuration of the local `main` branch; it does not change any remote URL and does not fetch data. Fetch first so the `upstream/main` reference is up to date.

## 9. Commands for Managing Multiple Remotes

| Purpose | Command |
|---|---|
| List remote names | `git remote` |
| View fetch/push URLs | `git remote -v` |
| View details of a remote | `git remote show upstream` |
| Add canonical repository | `git remote add upstream <url>` |
| Change remote URL | `git remote set-url upstream <url>` |
| Rename remote | `git remote rename upstream canonical` |
| Remove remote from local config | `git remote remove upstream` |
| Fetch one remote | `git fetch upstream` |
| Fetch all remotes | `git fetch --all` |

Removing a remote only deletes the connection configuration in the local repository and related remote-tracking references; this operation does not delete the repository on the server. Before renaming or removing a remote, inspect local branches tracking that remote with `git branch -vv` and adjust configuration if needed.

## 10. Common Errors When Working with Forks

| Situation | Common Cause and How to Check |
|---|---|
| Push reports permission denied | You may be pushing to the canonical repository. Check `git remote -v` and use the remote pointing to your fork. |
| New project commits are missing | You may have fetched `origin` without fetching `upstream`. Run `git fetch upstream`. |
| `git remote add upstream` reports remote already exists | The remote is already configured. Check URLs with `git remote -v`; use `git remote set-url` if you need to fix it. |
| `upstream/main` is not visible | You have not fetched the canonical repository, the default branch name is not `main`, or the refspec does not fetch that branch. Check `git branch -r` and `git remote show upstream`. |
| Pushing a feature branch but pulling tracks a different branch | The local branch does not have the desired upstream branch set. Check `git branch -vv` and use `git push -u origin <branch>`. |
| Push rejected as non-fast-forward | The remote branch has commits missing locally or history was rewritten. Fetch, inspect the graph, and integrate per team policy. |

Before every push, especially when a local repository has multiple remotes, confirm the target remote and target branch. A `git push origin ...` command and a `git push upstream ...` command can send the exact same commit to two completely different repositories.

## 11. Self-Check

1. **In a typical fork workflow, where do `origin` and `upstream` usually point?**
   - `origin` points to your fork; `upstream` points to the project's canonical repository.
2. **Which command updates information from the canonical repository without automatically merging into local `main`?**
   - `git fetch upstream`.
3. **Is `upstream/main` a local branch where you commit directly?**
   - No. It is a remote-tracking branch reflecting the state of the `main` branch on the `upstream` remote as of the most recent fetch.
4. **Why use `git push -u origin feature/search`?**
   - To push the branch to your fork and set `origin/feature/search` as the local branch's upstream branch so future syncs are more convenient.
5. **Are a remote named `upstream` and an upstream branch the same thing?**
   - No. One is a remote alias; the other is the branch that a local branch is configured to track.

## Conclusion

Connecting multiple remotes lets a local repository pull history from the canonical repository and send working branches to your fork. By common convention, `upstream` is the update source and `origin` is where personal branches are stored. Check URLs with `git remote -v`, fetch the right remote, synchronize your base branch before developing, create feature branches from an appropriate history point, and use `git push -u origin <branch>` to publish branches to your fork. Clearly identifying the target repository and target branch keeps your contribution process under control.

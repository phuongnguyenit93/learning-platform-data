# Setting the Default Initial Branch and Defaults for clone, fetch, pull, and push

When starting a new repository or cloning a project from a server, Git has to pick several defaults: the initial branch name, the remote name, how to update information from remotes, how to integrate changes when pulling, and how to send commits when pushing. These choices directly affect how team members work and how history is shared across the team.

Git lets you configure those defaults using `git config`. You can set configuration at the system, global, local, or worktree scope, or for a single command invocation. A sensible policy gives new repositories consistent conventions while avoiding having to pass repetitive flags on every operation.

In a Git source control service, understanding the defaults of `init`, `clone`, `fetch`, `pull`, and `push` helps establish a clear working environment and reduces confusion over upstream branches, target remotes, and synchronization across team members.

## 1. Git configuration and scope of application

Git has multiple configuration scopes. A value at a more specific scope can override a value at a broader scope.

| Configuration scope | Coverage | Common way to set |
| --- | --- | --- |
| System | Entire system or machine | `git config --system ...` |
| Global | Current user | `git config --global ...` |
| Local | Current repository | `git config --local ...` |
| Worktree | A specific working tree in a multi-worktree repository | `git config --worktree ...` |
| Command | A single Git invocation | `git -c key=value <command>` |

Example of setting the default branch name for all new repositories created by the user:

```bash
git config --global init.defaultBranch main
```

Setting a repository-specific pull policy for the current repository:

```bash
git config --local pull.rebase true
```

Applying fast-forward only for a single pull:

```bash
git -c pull.ff=only pull
```

### Viewing configuration and value sources

```bash
git config --list --show-origin
git config --show-origin --get init.defaultBranch
git config --show-origin --get-all pull.rebase
```

`--show-origin` shows which file the configuration comes from. `--get-all` displays all declared values for a key, which is helpful when a setting appears at multiple scopes.

You can view help for individual keys:

```bash
git help config
```

Some configuration keys were added in newer Git versions. If a command does not recognize a key or behaves differently from the description, check `git --version` and the documentation corresponding to the version you are using.

## 2. Setting the default branch name when initializing a repository

When running `git init`, Git creates the first branch for the new repository. If no configuration or option specifies a name, Git uses the default name of the installed version/package; the traditional name is `master`, while many teams currently use `main`, `trunk`, or another name according to project conventions.

### Configuring `init.defaultBranch`

Set `main` for newly initialized repositories:

```bash
git config --global init.defaultBranch main
```

Verify:

```bash
git config --global --get init.defaultBranch
```

Create a new repository and inspect the current branch:

```bash
mkdir demo-project
cd demo-project
git init
git branch --show-current
```

Even if the repository has no commits yet, `git branch --show-current` can return the initial branch name, such as `main`. This configuration applies to new `git init` runs; it does not automatically rename branches in existing repositories.

### Specifying the branch name for a single init

You can specify it directly:

```bash
git init --initial-branch=main
```

Or use the short form:

```bash
git init -b main
```

The command-line option applies to that initialization and can be used to override the configured default.

### Renaming an existing branch

If a repository already has a `master` branch and the team decides to rename it to `main`:

```bash
git branch -m master main
```

If you are currently on the branch you want to rename, you can use:

```bash
git branch -m main
```

Renaming a local branch does not automatically rename the branch on the remote or update server configuration. If the branch has already been shared, coordinate updating the remote, upstream tracking, pull requests, and team documentation according to your project's workflow.

### `init.defaultBranch` does not determine the cloned branch

`init.defaultBranch` controls the branch name when creating a new repository with `git init`. When cloning an existing repository, Git normally checks out the branch the remote advertises via `HEAD` (usually the default branch on the server). To choose a different branch when cloning, use `--branch` or `-b`:

```bash
git clone --branch develop https://example.com/team/project.git
```

Do not confuse the local initial branch name with the default branch administered on the server.

## 3. Defaults of `git clone`

`git clone` creates a local repository from another source. Besides the URL and checked-out branch, Git also needs to name the remote representing that source.

### Default remote name `origin`

Normally, cloning creates a remote named `origin`:

```bash
git clone https://example.com/team/project.git
cd project
git remote -v
```

`origin` is a common convention, not a mandatory name. It represents the source repository from which the clone initially fetched data.

### Configuring `clone.defaultRemoteName`

You can configure a different default remote name:

```bash
git config --global clone.defaultRemoteName upstream
```

From then on, new clones can use `upstream` instead of `origin`:

```bash
git clone https://example.com/team/project.git
cd project
git remote -v
```

This setting only changes the remote name created in newly cloned repositories. It does not change the URL, does not change the default branch, and does not affect remotes already configured in existing repositories. The default value is `origin`. This key may be unavailable on some older Git versions; if unsupported, use the `--origin` option when cloning.

### Specifying a remote name for a single clone

```bash
git clone --origin source https://example.com/team/project.git
```

Or the short form:

```bash
git clone -o source https://example.com/team/project.git
```

The new remote will be named `source`. This name is also used in remote-tracking branch names, such as `source/main`.

### Choosing a branch when cloning

```bash
git clone --branch release/2.4 https://example.com/team/project.git
```

`--branch` selects the branch or tag to check out. If you select a branch, Git creates the corresponding local branch and configures tracking for the remote branch. If you select a tag, Git checks out the tag and is normally in a detached HEAD state.

### Other useful clone options

| Option | Meaning |
| --- | --- |
| `--branch <name>` / `-b <name>` | Select the branch or tag to check out |
| `--origin <name>` / `-o <name>` | Set the source remote name instead of the default |
| `--depth <n>` | Create a shallow clone with limited history depth |
| `--single-branch` | Clone history for only a single branch |
| `--no-single-branch` | Fetch branch history per clone/fetch config instead of limiting to one branch |
| `--filter=<spec>` | Use partial clone to filter initially downloaded objects if the server supports it |
| `--sparse` | Start the clone with sparse checkout |

Example of cloning the `develop` branch with limited history:

```bash
git clone --branch develop --depth 20 https://example.com/team/project.git
```

`--depth` normally makes Git fetch only a single branch by default; add `--no-single-branch` if you need history for additional branches.

## 4. Defaults of `git fetch`

`git fetch` downloads data and updates remote-tracking refs according to remote configuration. It does not automatically merge or rebase changes into your current local branch.

### Remote ref mapping

When cloning, Git typically configures a fetch refspec for the remote, for example:

```text
remote.origin.fetch=+refs/heads/*:refs/remotes/origin/*
```

This refspec means that when fetching `origin`, Git retrieves remote branches and updates the corresponding remote-tracking refs such as `origin/main` and `origin/develop`.

Verify configuration:

```bash
git config --get-all remote.origin.fetch
git remote show origin
```

If a remote has a restricted refspec configured, `git fetch origin` updates only the specified refs. Therefore, not every branch on the server is guaranteed to appear locally.

### `fetch.prune`: cleaning up deleted remote-tracking branches

By default, `fetch.prune` is `false`: when a branch is deleted on the remote, the corresponding remote-tracking ref can remain in the local repository until cleaned up. Enable pruning globally:

```bash
git config --global fetch.prune true
```

Or enable it only within a repository:

```bash
git config --local fetch.prune true
```

When fetching, Git removes remote-tracking refs that no longer match the refspec on the remote. You can run it once:

```bash
git fetch --prune origin
```

Pruning affects local remote-tracking references; it does not delete local branches of the same name and does not delete branches on the server.

### `fetch.pruneTags`: cleaning up tags no longer on the remote

Tags are handled differently from branches. By default, tags are fetched via auto-follow when a tag points to a commit reachable in the history being fetched. Local tags are normally not automatically deleted when the corresponding tag is deleted on the remote.

If the team wants to prune tags in sync with the remote, you can configure:

```bash
git config --global fetch.pruneTags true
```

`fetch.pruneTags` defaults to `false`. When enabled, this key instructs Git to prune tags along with pruning; it does not automatically enable `fetch.prune`. Keep in mind that local tags not managed separately can be deleted if they no longer exist on the fetched remote. You can run it explicitly:

```bash
git fetch --prune --prune-tags origin
```

Before enabling a global tag-pruning policy, agree on how the team uses tags. Some local tags may exist only for experiments or personal markers and do not exist on the remote.

### `--no-tags` and `remote.<name>.tagOpt`

If you do not want to fetch tags automatically during a single fetch:

```bash
git fetch --no-tags origin
```

You can set the behavior for a specific remote:

```bash
git config remote.origin.tagOpt --no-tags
```

Normally, Git automatically fetches tags pointing to commits in the history being fetched (auto-follow). Use `--tags` to fetch all tags advertised by the remote, or `--no-tags` to disable auto-follow for that invocation.

## 5. Defaults of `git pull`

`git pull` essentially fetches from the upstream remote and then integrates changes into the current branch via merge or rebase. The integration method affects history and how diverged local and remote branches are handled.

### `pull.rebase`: merge or rebase when pulling?

The default for `pull.rebase` is `false`, meaning pull uses merge. You can set:

```bash
git config --global pull.rebase false
```

In that case, if the local and upstream branches diverge, Git can create a merge commit to combine both histories.

If the team prefers a more linear history, you can set:

```bash
git config --global pull.rebase true
```

When pulling, Git replays local commits not yet on upstream on top of the newly fetched commits. Rebasing creates new commit IDs for the replayed commits; do not use it carelessly on commits already shared that others are basing work on.

Besides `true` and `false`, `pull.rebase` also supports options like `merges` to attempt preserving merge structure during rebase, or `interactive` to use interactive rebase. Check your Git version's documentation before using advanced modes.

### `pull.ff`: fast-forward policy

`pull.ff` controls how Git handles fast-forwards during pull; the default value is `true`:

| Value | Behavior |
| --- | --- |
| `true` | Allow fast-forward if possible; if branches have diverged, merge can create a merge commit |
| `false` | Create a merge commit even when fast-forward is possible |
| `only` | Allow fast-forward updates only; stop if local and upstream histories have diverged |

Example of allowing fast-forward only:

```bash
git config --global pull.ff only
```

This setting suits teams that want safe pulls and prefer to decide explicitly how to handle diverged branches. If `pull.rebase=true` is used, Git will rebase local commits according to that policy; avoid combining conflicting pull settings without understanding how they interact.

### Auto-stashing before merge or rebase

When the working tree has uncommitted changes, a pull can be blocked or run into conflicts during integration. Git provides `merge.autoStash` and `rebase.autoStash` to automatically stash before merging/rebasing and re-apply afterward:

```bash
git config --global merge.autoStash true
git config --global rebase.autoStash true
```

You can request it for a single pull using an option:

```bash
git pull --autostash --rebase
```

Autostash is helpful when local changes do not conflict with pulled changes. If re-applying the stash produces conflicts, the user still has to resolve them manually. It is not a substitute for saving important work or checking status before pulling.

### Specifying policy for a single pull

```bash
git pull --rebase
git pull --no-rebase
git pull --ff-only
```

Command-line options can override configuration for that invocation. When working in a team, agree on a pull convention so history across team members stays predictable.

## 6. Upstream and branch configuration affecting pull

So that `git pull` does not need the remote and branch name passed every time, a local branch normally tracks a remote branch called its upstream.

A local branch can have the following configuration:

```text
branch.main.remote = origin
branch.main.merge = refs/heads/main
```

This indicates that the local `main` branch tracks the `main` branch on the `origin` remote.

Verify:

```bash
git branch -vv
git config --get branch.main.remote
git config --get branch.main.merge
```

### `branch.autoSetupMerge`

When creating a branch from a remote-tracking branch, Git can automatically configure the upstream. `branch.autoSetupMerge` defaults to `true`; this key controls that behavior:

```bash
git config --global branch.autoSetupMerge true
```

Common values include:

- `true`: automatically set up upstream when the starting point is a remote-tracking branch.
- `false`: do not automatically set up upstream.
- `always`: always set up a tracking relationship when creating a branch from an eligible starting point.
- `inherit`: inherit upstream configuration from the starting branch.
- `simple`: only set up automatically when the local branch name and starting branch match according to simple rules.

Example of creating a branch tracking a remote branch:

```bash
git switch --track origin/feature/payment
```

Or creating a branch with a different local name:

```bash
git switch -c payment-work --track origin/feature/payment
```

### `branch.autoSetupRebase`

This key specifies whether to automatically set `branch.<name>.rebase` when creating a branch with an upstream:

```bash
git config --global branch.autoSetupRebase remote
```

Possible values include `never` (default), `local`, `remote`, or `always`. For example, `remote` applies rebase by default for branches tracking a remote branch. This key provides finer-grained control alongside `pull.rebase`; inspect the branch-specific configuration if pull behavior differs from expectations.

## 7. Defaults of `git push`

`git push` sends commits from the local repository to a remote. Git needs to determine the target remote and which branch will be updated.

### `push.default`: choosing which branch is pushed

The `push.default` key governs behavior when running `git push` without passing a refspec. Since Git 2.0, the default value is `simple`:

| Value | Behavior |
| --- | --- |
| `nothing` | Do not push unless an explicit refspec is specified |
| `current` | Push the current branch to a branch of the same name on the target remote |
| `upstream` | Push the current branch to its tracked upstream branch |
| `simple` | Push the current branch to upstream when local and upstream branch names match; this is the common modern default |
| `matching` | Push all local branches that have a matching branch name on the remote |

You can explicitly set the common default:

```bash
git config --global push.default simple
```

`simple` helps avoid accidentally pushing to the wrong branch when a local branch tracks an upstream with a different name. `current` fits if the team wants to always push the current branch to the same-named branch. `matching` has broader impact and can send multiple branches at once, so understand it thoroughly before using.

### `push.autoSetupRemote`: automatically setting up upstream on first push

Normally, the first push of a new branch must specify the remote and branch name while setting upstream:

```bash
git push --set-upstream origin feature/payment
```

`push.autoSetupRemote` defaults to `false`. You can enable automatic upstream setup for default pushes:

```bash
git config --global push.autoSetupRemote true
```

When the current branch has no upstream yet and a default push is used, Git can automatically set up tracking to the branch of the same name on the default remote. This key works well with `push.default=simple` or `current` workflows; check your Git version if you do not observe this behavior.

### Choosing the default push remote with `remote.pushDefault`

In a fork workflow, a branch might fetch from `upstream` yet push to `origin`. You can set the default remote for pushing:

```bash
git config --global remote.pushDefault origin
```

This key selects the default push remote when the branch has no branch-specific push configuration. `branch.<name>.pushRemote` on the current branch takes higher precedence; only if no branch-specific push config exists does Git check `remote.pushDefault` and then other remote/upstream rules. It does not change the upstream remote used for pulling.

### `branch.<name>.pushRemote`: per-branch push remote

A specific branch can override the default push remote:

```bash
git config branch.feature-payment.pushRemote origin
```

While the local branch can still track `upstream/main` for pulling, pushes from `feature-payment` will target `origin`. This configuration is very useful in fork workflows.

### `push.followTags`

When pushing commits, you can also send annotated tags associated with the commits being pushed:

```bash
git config --global push.followTags true
```

`push.followTags` makes a default push behave as if `--follow-tags` were passed: Git pushes annotated tags not yet on the remote that point to commits reachable from the refs being pushed. It does not automatically push all local tags; if you need to push every tag, use `git push --tags`.

## 8. A sample configuration set for a development team

No single set of defaults fits every team. The example below illustrates a common policy for a team that uses `main`, wants to prune stale remote-tracking refs, uses rebase when pulling, and pushes the current branch to its upstream.

```bash
# Default branch when running git init
git config --global init.defaultBranch main

# Default remote created by clone
git config --global clone.defaultRemoteName origin

# Prune remote-tracking branches deleted on the remote
git config --global fetch.prune true

# Pull via rebase to keep linear history
git config --global pull.rebase true

# Automatically set upstream when pushing a new branch the first time
git config --global push.autoSetupRemote true

# Push the current branch to its upstream explicitly
git config --global push.default simple

# Send relevant annotated tags when pushing commits
git config --global push.followTags true
```

If a team prefers fast-forward-only pulls and manual handling when branches diverge, it can choose:

```bash
git config --global --unset pull.rebase
git config --global pull.ff only
```

Choose a pull policy consistent with how the team manages history. Do not copy a sample configuration set without checking the project's review workflow, release process, and branch protection rules.

## 9. Checking effective configuration

When Git behaves differently than expected, inspect the relevant configuration keys before making changes.

```bash
git config --show-origin --get init.defaultBranch
git config --show-origin --get clone.defaultRemoteName
git config --show-origin --get fetch.prune
git config --show-origin --get fetch.pruneTags
git config --show-origin --get pull.rebase
git config --show-origin --get pull.ff
git config --show-origin --get push.default
git config --show-origin --get push.autoSetupRemote
git config --show-origin --get remote.pushDefault
```

Inspect configuration of the current branch:

```bash
git branch -vv
git config --get-regexp '^branch\.'
```

Inspect remote configuration:

```bash
git remote -v
git config --get-regexp '^remote\.'
```

If you need to remove a local or global configuration:

```bash
git config --global --unset pull.rebase
git config --local --unset push.default
```

`--unset` removes the key only in the specified scope. If the key is declared at multiple levels, removing one value may not change the effective value; re-verify using `--show-origin`.

## 10. Common scenarios

| Scenario | Possible cause | How to resolve |
| --- | --- | --- |
| New repository still creates `master` | `init.defaultBranch` is unset or overridden by another scope | Check `git config --show-origin`; use `git init -b main` for a specific creation |
| Clone creates a remote named other than `origin` | `clone.defaultRemoteName` or `--origin` set a different name | Use `git remote -v` to confirm and pass the right remote name in commands |
| Local branch does not automatically track upstream | Branch was created without `--track` or `branch.autoSetupMerge` is not set as expected | Use `git branch --set-upstream-to=<remote>/<branch>` or create the branch with `--track` |
| Pull reports branches have diverged | Both local and upstream have unique commits; pull policy is unresolved | Choose merge, rebase, or fast-forward-only per team convention |
| Pull creates an unintended merge commit | `pull.rebase=false` and fast-forward is not possible | Set `pull.rebase=true` or `pull.ff=only` depending on workflow |
| Push reports no upstream branch | New branch is not linked to an upstream yet | Use `git push -u <remote> <branch>` or consider `push.autoSetupRemote` |
| Push targets the wrong remote | `remote.pushDefault` or `branch.<name>.pushRemote` points to an unexpected remote | Check `git remote -v` and branch/remote configuration |
| Stale remote-tracking branches remain | `fetch.prune` is not enabled | Use `git fetch --prune` or enable `fetch.prune` |
| Local tag disappears after fetch prune | Tag pruning is enabled and tag does not exist on the remote | Review `fetch.pruneTags` policy and how the team manages tags |

### Fork workflow: fetch from upstream, push to origin

Suppose `origin` is the team's fork and `upstream` is the original repository:

```bash
git remote add upstream https://example.com/original/project.git
git config remote.pushDefault origin
git fetch upstream
git switch -c feature/payment upstream/main
git push -u origin feature/payment
```

In this workflow, the feature branch starts from `upstream/main`, yet pushes go to the `origin` fork. Configuring `remote.pushDefault` makes default push commands target the fork; `branch.feature-payment.pushRemote` can be set even more specifically if needed.

## 11. Hands-on practice

Practice in a sandbox repository to observe the effect of each default:

1. Check `git config --show-origin --list` and note existing values.
2. Set `init.defaultBranch` to `main`, create a new repository with `git init`, and check the branch name.
3. Clone a test repository and check the default remote name; try `clone.defaultRemoteName` or `--origin` in another clone.
4. Create a test remote branch, fetch, then delete the branch on the remote; enable `fetch.prune` and fetch again to observe the remote-tracking ref getting pruned.
5. Create two independent commits locally and remotely to make branches diverge; test `pull.rebase=false`, `pull.rebase=true`, and `pull.ff=only` in separate clones.
6. Create a new local branch and try pushing with `push.default=simple`; observe the upstream requirement.
7. Enable `push.autoSetupRemote`, push a new branch, and verify with `git branch -vv`.
8. Simulate a fork workflow with `origin` and `upstream`, set `remote.pushDefault`, and verify the target remote.
9. Test the effect of `fetch.pruneTags` in a repository containing only test tags.

After practicing, explain which keys affect new repositories, which keys only control `fetch`/`pull`/`push` operations, and why local configuration can override global configuration.

## 12. Knowledge self-check

1. How does `init.defaultBranch` affect `git init`?
2. Why does `init.defaultBranch` not automatically determine the branch checked out when cloning?
3. How does `clone.defaultRemoteName` differ from `--origin` in scope of application?
4. Which kind of reference does `fetch.prune` delete, and does it affect local branches?
5. How should `fetch.pruneTags` be understood alongside the pruning policy?
6. Which choices during pull are controlled by `pull.rebase` and `pull.ff`?
7. Which configuration keys store the upstream branch?
8. How does `push.default=simple` differ from `current` and `upstream`?
9. How do `remote.pushDefault` and `branch.<name>.pushRemote` work together?
10. Why is it necessary to inspect configuration sources with `git config --show-origin`?

## Conclusion

`init.defaultBranch` sets the branch name for new repositories; `clone.defaultRemoteName` chooses the default remote name; `fetch.prune` and `fetch.pruneTags` manage stale references; `pull.rebase` and `pull.ff` determine how changes are integrated; `push.default`, `push.autoSetupRemote`, and remote/branch keys determine how commits are pushed. Choose policies aligned with your team's workflow, and inspect configuration sources and upstreams before making changes. When you clearly understand the scope of each key, you can create repositories consistently and reduce errors caused by Git picking the wrong default branch or remote.

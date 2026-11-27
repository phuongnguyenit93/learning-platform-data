# Configuring push.default and Avoiding Pushing the Wrong Branch

The `git push` command sends commits from the local repository to a remote to share with others. When running `git push` without explicitly specifying a remote and destination branch, Git must rely on configuration to decide which branches to send and where to send them. Without understanding these rules, a developer can push the wrong branch, update a shared branch, or send multiple unintended branches.

Git provides the `push.default` option to determine behavior when a push command has no specific refspec. Combining this setting with upstream, push remote, status checks, and explicit refspecs makes repository synchronization much more predictable.

## 1. Distinguishing Local Branch, Remote-Tracking Branch, and Upstream

Before configuring push, understand three concepts that commonly appear together.

### 1.1. Local branch

A local branch is a branch residing in the repository on your machine. For example:

~~~bash
git branch
git switch feature/payment-retry
~~~

In this example, `feature/payment-retry` is the local branch. New commits you create while on this branch update the local branch reference.

Check the current branch:

~~~bash
git branch --show-current
~~~

This command returns the name of the currently checked-out branch. This is essential information to verify before pushing.

### 1.2. Remote-tracking branch

When cloning or fetching from a remote, Git stores references tracking the state of branches on the remote, usually named like:

- `origin/main`
- `origin/feature/payment-retry`
- `upstream/main`

For example, `origin/main` is a remote-tracking branch recording the state of the `main` branch received in the most recent fetch from the remote named `origin`. It is not the local `main` branch, and it does not update automatically the instant the server receives new commits.

Refresh remote information:

~~~bash
git fetch origin
~~~

After fetching, Git updates the corresponding remote-tracking branches. Fetch does not automatically merge changes into the current local branch.

### 1.3. Upstream branch

An upstream branch is the branch that a local branch is configured to track. For example, local branch `feature/payment-retry` can track `origin/feature/payment-retry`.

This configuration tells Git which branch to use for ahead/behind comparisons and serves as the basis for pull or push commands that omit an explicit destination branch.

View upstreams of local branches:

~~~bash
git branch -vv
~~~

The line with `*` is the current branch. The text inside square brackets indicates the upstream, if configured, and may display status such as `ahead 2` or `behind 1`.

View the current branch's upstream with:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

If the command reports no upstream, the current branch does not yet have a tracking branch configured.

You can set an upstream explicitly:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

The command above configures local branch `main` to track `origin/main`. Use it only when that is truly the intended relationship.

## 2. How Does Git Choose Which Remote to Push To?

A remote is a named alias for another repository, commonly `origin`, `upstream`, or a fork name. View configured addresses:

~~~bash
git remote -v
~~~

When running `git push` without specifying a remote, Git must select a target remote. Selection rules can be influenced by settings in priority order:

1. `branch.<branch-name>.pushRemote`: dedicated push remote for the current branch.
2. `remote.pushDefault`: default push remote for branches.
3. `branch.<branch-name>.remote`: remote that the current branch tracks.
4. `origin`: default remote if no other matching configuration exists.

You can inspect relevant settings:

~~~bash
git config --show-origin --get remote.pushDefault
git config --show-origin --get branch.feature/payment-retry.pushRemote
git config --show-origin --get branch.feature/payment-retry.remote
~~~

`git config --get` commands may print nothing if a key is not configured. That is not necessarily an error; Git will continue checking subsequent default sources.

Some teams working with forks fetch code from remote `upstream` but push their own branches to `origin`. In that case, the remote used for retrieving changes and the remote used for pushing differ. You can set a default push remote:

~~~bash
git config remote.pushDefault origin
~~~

Or configure it per branch:

~~~bash
git config branch.feature/payment-retry.pushRemote origin
~~~

Choosing the remote and choosing which branch to push are two separate decisions. `push.default` primarily decides which ref is sent when no refspec is given; remote settings decide the receiving destination.

Additionally, if a remote has `remote.<remote-name>.push` configured, the refspec in that setting determines which refs are pushed when you omit a refspec on the command line. You can inspect it, for example:

~~~bash
git config --show-origin --get-all remote.origin.push
~~~

Writing a refspec directly in the `git push` command makes the source and destination of that push explicit.

## 3. What Is push.default?

`push.default` determines the behavior of `git push` when you do not provide a refspec on the command line and no custom refspec is configured for the remote. This value can be set at the repository level or user level.

Five common values:

| Value | Behavior | Notes |
| --- | --- | --- |
| `nothing` | Does not automatically pick a branch to push; requires an explicit refspec | Safest when you want every push to specify its destination |
| `current` | Pushes the current branch to a branch of the same name on the target remote | Requires no upstream, but you must still pick the right remote |
| `upstream` | Pushes the current branch to its configured upstream branch | Can push to a remote branch with a different name |
| `simple` | In a centralized workflow, pushes the current branch to the same-named upstream and rejects if names differ | Default since Git 2.0; suitable choice for most normal workflows |
| `matching` | Pushes all local branches that have a same-named branch on the remote | Can update multiple branches unintentionally |

### 3.1. nothing — require specifying the destination

~~~bash
git config --global push.default nothing
~~~

With this configuration, the command:

~~~bash
git push
~~~

will stop because no explicit refspec was given. You must specify the branch or source/destination pair:

~~~bash
git push origin feature/payment-retry
~~~

This approach fits people who want to deliberately confirm the branch on every push, or teams with strict release processes. In return, push commands become longer.

### 3.2. current — push the current branch to a branch of the same name

~~~bash
git config --global push.default current
~~~

If you are on local branch `feature/payment-retry`, Git pushes that branch to the branch of the same name on the selected remote.

The advantage is not needing to configure an upstream beforehand. However, `current` does not verify that the same-named remote branch is actually the branch you meant to update. If the wrong remote is chosen or you are on the wrong branch, the outcome can still be unintended.

### 3.3. upstream — push to the tracked branch

~~~bash
git config --global push.default upstream
~~~

This value uses the current branch's upstream branch as the destination. That is helpful when the local branch and remote branch have different names but the tracking relationship was configured intentionally.

For example, local branch `review/payment-retry` might track remote branch `origin/review/PR-42`. With `upstream`, Git directs the push to that upstream branch.

Because the destination can differ from the local branch name, check `git branch -vv` before using it. If the upstream was misconfigured, an argument-free push could update the wrong branch.

### 3.4. simple — safe default for centralized workflows

~~~bash
git config --global push.default simple
~~~

In a centralized workflow, `simple` requires the current local branch to have an upstream and the two branch names to match. If the names differ, Git rejects the push to avoid updating a branch that might not be the intended target.

This is the default value since Git 2.0. In a triangular workflow—such as fetching code from one remote while pushing to a separate fork—`simple` acts like `current`, pushing the current branch to a same-named branch on the push remote.

If the branch has no upstream yet, a default push will ask you to set an upstream. You can do this once with:

~~~bash
git push -u origin feature/payment-retry
~~~

Once the upstream is recorded, subsequent pushes can use `git push` provided you have verified the right branch and remote.

### 3.5. matching — push all matching-name branches

~~~bash
git config --global push.default matching
~~~

This value sends every local branch that has a same-named branch on the remote. For example, if local has `main`, `release/1.4`, and `feature/search`, and the remote has all three corresponding branches, a single push command can update all three.

This can fit intentional multi-branch synchronization workflows, but easily causes surprises if a developer only meant to share one branch. Do not choose `matching` as the default for normal day-to-day workflows.

## 4. Choosing the Right Setting and Inspecting Current Configuration

### 4.1. Checking the effective value

Inspect the configured value and its source:

~~~bash
git config --show-origin --get-all push.default
~~~

If there is no output, Git uses the default for the Git version in use. For modern Git versions, the default is `simple`.

Configuration can exist at multiple scopes:

- System: applies machine-wide.
- Global: applies to the current user.
- Local: applies specifically to the repository and normally overrides global.
- Worktree: applies specifically to a worktree if worktree config is enabled.

Set global configuration:

~~~bash
git config --global push.default simple
~~~

Set configuration specifically for the current repository:

~~~bash
git config --local push.default simple
~~~

If a repository has a local setting different from global, check the configuration origin before changing it. There is no need to reset default values in every repository without a reason.

### 4.2. Selection recommendations

- Use `simple` for most users and centralized workflows.
- Use `nothing` if team policy requires specifying the destination branch on every push.
- Use `upstream` when intentionally working with differently named local and upstream branches.
- Use `current` when you want to push the current branch to a same-named branch without relying on upstream.
- Use `matching` only when you genuinely want to sync multiple branches sharing the same name.

No single value fits every workflow. What matters is that the whole team understands the active configuration and knows which branch an argument-free command will pick.

## 5. Using Refspecs to Specify Exact Source and Destination Branches

### 5.1. Refspec syntax

Basic push syntax:

~~~bash
git push <remote> <source>:<destination>
~~~

Where:

- `<remote>` is the repository receiving commits.
- `<source>` is the local branch or commit being sent.
- `<destination>` is the target branch on the remote.

Example:

~~~bash
git push origin feature/payment-retry:refs/heads/feature/payment-retry
~~~

This command pushes local branch `feature/payment-retry` to the remote branch of the same name on `origin`.

If source and destination names are identical, you can use the shorthand:

~~~bash
git push origin feature/payment-retry
~~~

Remember: this command selects the local branch named `feature/payment-retry`, regardless of which branch you have checked out. Therefore, when wanting to push the current branch, confirm the branch name or use a refspec starting with `HEAD`.

### 5.2. Pushing the current branch's commit to a specified destination

Suppose you are on `feature/payment-retry` and want to push the current state to the same-named remote branch:

~~~bash
git push origin HEAD:refs/heads/feature/payment-retry
~~~

`HEAD` represents the current commit. The destination is written in full as `refs/heads/feature/payment-retry`, so the command clearly states which remote branch will receive the update.

If you want the local branch to start tracking that remote branch:

~~~bash
git push --set-upstream origin HEAD:refs/heads/feature/payment-retry
~~~

The `-u` option is shorthand for `--set-upstream`.

### 5.3. Pushing to a remote branch with a different name

You can deliberately map a local branch to a different remote branch:

~~~bash
git push origin HEAD:refs/heads/review/payment-retry-42
~~~

This command sends the current commit to branch `review/payment-retry-42` on `origin`. Make sure that is the destination agreed upon by the team. If you want the local branch to track this destination, add `-u`:

~~~bash
git push -u origin HEAD:refs/heads/review/payment-retry-42
~~~

Explicit refspecs are often helpful in CI, review-branch workflows, or whenever local and remote branch names differ.

## 6. Safe Pre-Push Workflow

An argument-free push command is concise, but can hide many decisions. Before sending commits, verify the current branch, remote, upstream, and content to be sent.

### 6.1. Checking branch and working tree status

~~~bash
git branch --show-current
git status -sb
git branch -vv
~~~

Confirm:

- You are on the branch dedicated to the work you intend to share.
- The working tree does not contain unreviewed changes.
- The upstream displays the expected remote and branch.
- There are no signs the branch has diverged from the remote without being addressed.

If the branch has uncommitted changes, decide whether to commit or stash them before pushing. Push sends only commits; it does not send uncommitted edits in the working tree.

### 6.2. Checking the target remote

~~~bash
git remote -v
git remote get-url --push origin
~~~

The second command shows the push URL of remote `origin`. A single remote can use different fetch and push URLs. Always verify the exact URL receiving data, especially when working with forks or multiple servers.

If you use a default remote other than `origin`, substitute the corresponding name in the command.

### 6.3. Refreshing remote info and viewing differing commits

~~~bash
git fetch origin
git status -sb
git log --oneline --decorate --graph '@{upstream}..HEAD'
~~~

The last command lists local commits not yet in upstream, if an upstream is configured. You can inspect both sides with:

~~~bash
git log --oneline --left-right '@{upstream}...HEAD'
~~~

The `<` and `>` markers distinguish commits unique to one side. If no upstream exists yet, use an explicit refspec or set upstream before relying on these comparisons.

### 6.4. Dry-running the push

Before sending for real, you can run:

~~~bash
git push --dry-run --porcelain origin HEAD:refs/heads/feature/payment-retry
~~~

`--dry-run` tells Git to simulate the update without actually sending ref updates to the remote. The output lets you verify the source and destination the command targets.

Read the output carefully and confirm:

- The remote is the intended repository.
- The source branch is the current branch.
- The destination branch is the intended working branch.
- No unintended extra branches are listed.

After confirming, execute the actual push with the same refspec:

~~~bash
git push -u origin HEAD:refs/heads/feature/payment-retry
~~~

Do not alter source or destination between the dry-run step and the real push without re-checking.

## 7. Common Situations That Lead to Pushing the Wrong Branch

### 7.1. Being on a feature branch but typing main

Suppose you are on `feature/payment-retry`, yet run:

~~~bash
git push origin main
~~~

Git interprets `main` as the source local branch. The command pushes the local `main` branch to the remote branch of the same name, even though you have a feature branch checked out. This command does not mean "push the current branch."

The fix is to check `git branch --show-current` and specify the right source:

~~~bash
git push origin feature/payment-retry
~~~

Or use `HEAD` with an explicit destination branch as shown earlier.

### 7.2. Being on main when intending to push a feature branch

If you need to share a feature branch, switch to that branch and verify:

~~~bash
git switch feature/payment-retry
git branch --show-current
git status -sb
git push -u origin feature/payment-retry
~~~

Switching branches first reduces the chance of confusion when using argument-free commands later. Even so, every push command still needs checking against the remote and upstream.

### 7.3. Misconfigured upstream

If `git branch -vv` shows a feature branch tracking `origin/main`, stop and determine the intended relationship. If it should instead track `origin/feature/payment-retry`, fix it with:

~~~bash
git branch --set-upstream-to=origin/feature/payment-retry feature/payment-retry
~~~

Then verify again:

~~~bash
git branch -vv
git status -sb
~~~

Only change upstream when that remote branch actually exists and is the branch to track. If the remote branch does not exist yet, use `git push -u` with the exact remote and destination to create it and set upstream.

### 7.4. Push remote differs from fetch remote

In a fork workflow, you might pull updates from `upstream` while pushing your work to `origin`. Without distinguishing the two remotes, you could accidentally push commits to the main project repository.

Check:

~~~bash
git remote -v
git branch -vv
git config --show-origin --get remote.pushDefault
~~~

If the workflow requires pushing to fork `origin`, specify it directly:

~~~bash
git push -u origin feature/payment-retry
~~~

Only use `upstream` as the push remote when you have permission and intentionally want to update that repository.

### 7.5. Using broad-scope push options

Some commands have a scope wider than a single branch:

- `git push --all`: pushes all local branches.
- `git push --tags`: pushes all tags.
- `git push --mirror`: mirrors all refs, which can create, update, and delete refs on the remote.

Never use these options simply because you want to "sync everything." Fully understand their scope and consequences before running them, especially `--mirror`.

## 8. Configuring Push Remote in a Fork Workflow

A common workflow is cloning the original repository and then working through a personal fork. For example:

- `upstream`: main repository for fetching the latest branches.
- `origin`: your fork for pushing work branches.

Configure remotes:

~~~bash
git remote -v
git config remote.pushDefault origin
git config --global push.default simple
~~~

When creating a branch from the main branch:

~~~bash
git fetch upstream
git switch -c feature/payment-retry upstream/main
~~~

After completing work, push the branch to the fork:

~~~bash
git push -u origin feature/payment-retry
~~~

After the first push, the local branch will track the corresponding branch on `origin`. Subsequent runs can use `git push`, though you should still check `git branch -vv` and `git remote -v` when switching between projects or changing configuration.

If different branches have different push remotes, you can configure them individually:

~~~bash
git config branch.feature/payment-retry.pushRemote origin
~~~

This configuration is useful when some branches must be pushed to a fork while others go to a dedicated remote. Do not set configuration out of habit unless the team has agreed which remote is permitted to receive changes.

## 9. Protecting Shared Branches

Local configuration reduces risk, but does not replace server-side branch protection policies. For branches like `main`, `develop`, or `release/*`, teams should use branch protection rules on the code hosting platform to restrict direct pushes, require reviews, or enforce automated checks per workflow.

When needing to update a branch already used by others, avoid arbitrary force pushes. If history must be rewritten, coordinate with the team and understand the impact on other clones. `--force-with-lease` verifies your last known remote state before overwriting, yet can still replace someone else's commits if aimed at the wrong target. It is not a fix for ordinary push errors.

If you discover you pushed the wrong branch:

1. Stop further pushes to avoid complicating the situation.
2. Identify the remote, destination branch, and commits that were sent.
3. Talk with the branch maintainer or team if it is a shared branch.
4. Choose an appropriate recovery method, usually creating a revert commit if changes have already been shared.
5. Re-verify history and remote state before resuming work.

Do not arbitrarily force push to "erase tracks" on a shared branch. History should be corrected following the process agreed upon by the team.

## 10. Quick Reference Table

| Need | Command or Setting |
| --- | --- |
| View current branch | `git branch --show-current` |
| View upstream | `git branch -vv` |
| View remotes and URLs | `git remote -v` |
| View push.default setting | `git config --show-origin --get-all push.default` |
| Set simple default | `git config --global push.default simple` |
| Require specifying destination on push | `git config --global push.default nothing` |
| Push branch and set upstream | `git push -u origin feature/my-branch` |
| Push HEAD to specific destination | `git push origin HEAD:refs/heads/feature/my-branch` |
| Dry-run a push | `git push --dry-run origin HEAD:refs/heads/feature/my-branch` |
| Set default push remote | `git config remote.pushDefault origin` |
| Set push remote for one branch | `git config branch.feature/my-branch.pushRemote origin` |

Keep in mind that `push.default` selects behavior when a refspec is missing; it does not verify whether commit contents meet requirements. Remote and upstream are also two separate configurations, so inspect both before pushing.

## 11. Summary

To avoid pushing the wrong branch, understand local branches, remote-tracking branches, and upstreams; verify the push remote; and choose a push behavior suited to your workflow. `simple` is a sensible default for most centralized workflows because it requires the local branch and upstream names to match. `nothing` works well when you want to enforce specifying the destination; `current`, `upstream`, and `matching` should be chosen only when you clearly understand their behavior.

Before an important push, check the current branch with `git branch --show-current`, inspect upstream with `git branch -vv`, confirm the URL with `git remote -v`, and use an explicit refspec or `--dry-run` to confirm the target branch. These steps turn a short push command into a verifiable and predictable operation.

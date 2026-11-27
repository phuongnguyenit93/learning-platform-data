# Setting Upstream with git push -u and git branch --set-upstream-to

When working with a branch on your personal machine and its counterpart on a remote, Git needs to know which two branches have a tracking relationship. This relationship is called an **upstream** or *tracking branch*. Once an upstream is set, Git can report whether the local branch is ahead or behind the remote, and allows commands like `git pull` and `git push` to determine where to synchronize according to configuration.

Two common ways to configure this relationship are `git push -u` and `git branch --set-upstream-to`. The first is typically used when pushing a local branch to the remote for the first time; the second is used when the remote branch already exists and you want to associate your local branch with it.

## 1. What Is an Upstream?

Suppose a repository has a `feature/login` branch on your personal machine and a `feature/login` branch on the `origin` remote. When a local branch tracks the corresponding remote branch, Git stores the upstream information so it knows where to compare and synchronize.

For example:

```text
Local branch:            feature/login
Remote:                  origin
Remote-tracking branch:  origin/feature/login
Upstream:                origin/feature/login
```

Here it is important to distinguish three concepts:

- **Local branch** (`feature/login`): the branch you develop on in the local repository.
- **Remote branch** (`refs/heads/feature/login`): the actual branch stored in the repository on the server.
- **Remote-tracking branch** (`origin/feature/login`): a local ref reflecting the most recent fetch of that remote branch.

When you run `git fetch origin`, Git updates the remote-tracking branches according to the fetch configuration. A local branch's upstream normally points to a remote-tracking branch such as `origin/feature/login`, rather than connecting directly to the server on every operation.

An upstream helps Git answer these questions:

- Which commits does the local branch have that have not yet been pushed to the remote?
- Which commits does the remote have that local has not yet integrated?
- When running `git pull` on the current branch, which remote and branch should changes be pulled from?
- When running `git push` without specifying a remote and destination branch, which destination should Git use according to push configuration?

## 2. Setting Upstream on the First Push with `git push -u`

This is the convenient method when you have just created a local branch and want to push it to the remote for the first time.

Suppose you are on the `feature/login` branch:

```bash
git switch -c feature/login
```

After creating commits and getting ready to share the branch, run:

```bash
git push -u origin feature/login
```

The `-u` option is short for `--set-upstream`. When the push succeeds, Git sets the pushed remote branch as the upstream for the corresponding local branch. If the remote does not yet have a `feature/login` branch, the push command creates it (provided you have permission and no server-side rule prevents it).

After this first time, while you are still on `feature/login`, you can usually use:

```bash
git push
git pull
```

Git uses the saved upstream together with the push/pull configuration to determine the default source and destination. You can still specify the remote and branch explicitly whenever you want exact control over the operation.

The long form equivalent to `-u` is:

```bash
git push --set-upstream origin feature/login
```

### Example workflow

```bash
# Create a new branch from the current position.
git switch -c feature/login

# Edit and create a commit.
git add src/login/LoginService.java
git commit -m "feat: add login service"

# Push the branch and set upstream.
git push -u origin feature/login

# Subsequent syncs on this branch.
git push
git pull
```

`git push -u` only sets the upstream when the push succeeds or the branch is successfully updated as a result of the push. If the push is rejected—for example due to non-fast-forward or insufficient permissions—resolve the cause first and then re-verify the upstream relationship.

## 3. Attaching an Upstream to an Existing Branch with `git branch --set-upstream-to`

Sometimes a branch already exists on the remote, but the local branch does not yet have an upstream configured. For example, a teammate created and pushed `feature/login`, you fetched the remote, and then created a local branch with the same name without tracking information.

First, update remote information:

```bash
git fetch origin
```

Verify that the remote-tracking branch exists:

```bash
git branch -r
```

If the output includes `origin/feature/login`, set it as the upstream for the local branch:

```bash
git branch --set-upstream-to=origin/feature/login feature/login
```

This command configures the local `feature/login` branch to track `origin/feature/login`. It **does not push**, does not create a branch on the server, and does not automatically merge or rebase content. The command only establishes the tracking relationship in the local repository configuration.

If you are currently on the `feature/login` branch, you can omit the branch name at the end:

```bash
git branch --set-upstream-to=origin/feature/login
```

Git will set the upstream for the current branch. The short form of the option is `-u`, but to avoid confusion with `git push -u`, it is better to use the full name `--set-upstream-to` while learning.

### Case where the local branch does not exist yet

If you want to create a new local branch based on a remote branch and establish tracking immediately at creation time, you can use:

```bash
git switch --track -c feature/login origin/feature/login
```

This command creates the local `feature/login` branch from `origin/feature/login` and configures the upstream. It differs from `git branch --set-upstream-to`, which attaches an upstream to an already existing local branch.

## 4. Comparing the Two Ways of Setting Upstream

| Criterion | `git push -u` | `git branch --set-upstream-to` |
|---|---|---|
| Primary purpose | Push branch and set upstream | Set or change a local branch's upstream |
| Remote branch requirement | May not exist yet; push can create the branch | Target remote-tracking branch must exist locally |
| Sends commits to the server? | Yes, performs a push | No |
| Usable when the remote branch already exists? | Yes | Yes, usually the direct choice when only attaching tracking |
| Common scenario | First time publishing a local branch | Local branch already exists and needs to track an existing remote branch or switch upstream |

Quick examples:

```bash
# New local branch, push to origin and set upstream.
git push -u origin feature/login

# Local branch already exists, remote-tracking branch has been fetched.
git fetch origin
git branch --set-upstream-to=origin/feature/login feature/login
```

Choose the command based on the branch state and your current goal. If you need to share a branch for the first time, `git push -u` performs both actions in one step. If the remote branch already exists and you only need to attach a tracking relationship to the local branch, `git branch --set-upstream-to` makes that intent explicit.

## 5. Verifying the Configured Upstream

After configuring, verify that Git is tracking the intended branch.

### Using git branch -vv

```bash
git branch -vv
```

Example:

```text
  main           1a2b3c4 [origin/main] initial commit
* feature/login  5d6e7f8 [origin/feature/login: ahead 1] add login service
```

The part inside square brackets shows the upstream. `ahead 1` means the local branch has one commit not present in upstream as of the most recent sync. If you see `behind 2`, upstream has two commits that local does not have yet. If you see `ahead 1, behind 2`, both sides have diverged and changes need to be integrated according to your team's workflow.

Ahead/behind information is based on commits and remote-tracking refs currently present locally. To get the latest data from the server, fetch before evaluating:

```bash
git fetch origin
git branch -vv
```

### Using git status

```bash
git status -sb
```

Example:

```text
## feature/login...origin/feature/login [ahead 1]
```

This line indicates the current branch is `feature/login`, the upstream is `origin/feature/login`, and local is ahead by one commit.

### Viewing the upstream name with the @{upstream} expression

```bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
```

If an upstream is configured, the output is usually:

```text
origin/feature/login
```

If the current branch does not yet have an upstream, Git reports an error because it cannot resolve `@{upstream}`.

### Inspecting branch configuration

Git stores the tracking relationship in repository configuration. For branch `feature/login`, you can inspect:

```bash
git config --get branch.feature/login.remote
git config --get branch.feature/login.merge
```

The output is usually:

```text
origin
refs/heads/feature/login
```

`branch.<name>.remote` identifies the tracked remote; `branch.<name>.merge` identifies the branch ref on that remote. Git combines these two values to determine the corresponding upstream.

## 6. Changing or Removing an Upstream

If a local branch is tracking the wrong remote or wrong branch, you can reattach its upstream.

For example, switch local branch `feature/login` to track the branch of the same name on remote `upstream`:

```bash
git fetch upstream
git branch --set-upstream-to=upstream/feature/login feature/login
```

This operation changes the tracking configuration of the local branch. It does not move commits and does not alter working tree contents.

If you want to remove the upstream relationship from a local branch:

```bash
git branch --unset-upstream feature/login
```

Or if you are currently on the branch to unset:

```bash
git branch --unset-upstream
```

After unsetting, the local branch still exists and its commits remain intact. However, commands relying on a default upstream may ask you to specify the remote/branch explicitly or reconfigure tracking.

## 7. Common Errors and How to Handle Them

### No upstream configured

When running `git pull` or `git push` on a branch with no upstream, Git may report that the current branch has no tracking information.

If you want to push the local branch to the remote and set upstream:

```bash
git push -u origin feature/login
```

If the remote branch already exists and you only need to attach tracking:

```bash
git fetch origin
git branch --set-upstream-to=origin/feature/login feature/login
```

### Remote-tracking branch not found

The following command can fail if `origin/feature/login` does not yet exist in the local repository:

```bash
git branch --set-upstream-to=origin/feature/login feature/login
```

First, check the remote and fetch:

```bash
git remote -v
git fetch origin
git branch -r
```

If the branch still does not appear, check branch names on the server with:

```bash
git ls-remote --heads origin
```

Confirm the correct remote, branch name, and access permissions before reconfiguring.

### Push rejected due to non-fast-forward

If the remote already has commits that local has not integrated, push may be rejected as non-fast-forward. `-u` does not resolve history divergence. Fetch and inspect the state first:

```bash
git fetch origin
git status -sb
git log --oneline --graph --decorate --all -20
```

Then choose the integration approach according to team conventions, such as merge or rebase, resolve any conflicts, run required checks, and push again. Avoid using `--force` just to bypass the error before understanding remote history.

### Tracking the wrong branch or wrong remote

If `git status -sb` shows an unexpected upstream, run:

```bash
git branch -vv
git remote -v
```

After confirming the right remote and branch, run `git branch --set-upstream-to=<remote>/<branch> <local-branch>` to fix tracking. Do not change upstream by guessing, because a subsequent `git pull` could integrate changes from an unrelated branch.

### Default push does not target the expected branch

Upstream and the default push destination are related but not identical. How `git push` chooses its target also depends on the `push.default` setting and related options. In many modern repositories, `push.default=simple` is the default: Git typically requires the local branch and upstream branch to have the same name when pushing without an explicit refspec.

When clarity is needed, specify the remote and target branch:

```bash
git push origin feature/login
```

Or check the configuration:

```bash
git config --get push.default
```

Avoid changing global configuration just to handle one branch if you do not yet understand its effect on other repositories.

## 8. Practical Workflow for a New Branch

Suppose you are assigned to develop the login feature and want to share the `feature/login` branch to remote `origin`.

```bash
# 1. Update information from the remote.
git fetch origin

# 2. Create the working branch.
git switch -c feature/login

# 3. Make changes and commit.
git add src/login/LoginService.java
git commit -m "feat: add login service"

# 4. Push for the first time and set upstream.
git push -u origin feature/login

# 5. Verify upstream.
git branch -vv
git status -sb

# 6. Subsequent work cycles.
git pull
git push
```

If the `feature/login` branch was already created on the remote by another teammate, you can fetch, create a local branch based on the remote-tracking branch, and configure tracking immediately:

```bash
git fetch origin
git switch --track -c feature/login origin/feature/login
```

If the local branch already existed beforehand, use `git branch --set-upstream-to` to bind it to the fetched remote-tracking branch.

## 9. Takeaways

An upstream is the relationship between a local branch and the branch it tracks on a remote. This relationship lets Git compare ahead/behind status and determine default sync targets.

- Use `git push -u origin <branch>` when you want to push a branch and set its upstream in the same operation.
- Use `git branch --set-upstream-to=<remote>/<branch> <local-branch>` when the local branch already exists and you want to attach or change its upstream.
- Use `git fetch` before referencing a remote-tracking branch that does not yet exist locally.
- Use `git branch -vv`, `git status -sb`, or `git rev-parse '@{upstream}'` to verify the configuration.

After configuring, check that the upstream points to the intended remote and branch. An accurate tracking relationship keeps repository synchronization clear and reduces the risk of pulling from or pushing to the wrong line of development.

# Pushing the Right Branch and Refspec with git push

When working with a remote repository, `git push` sends commits from the local repository to a remote. A single push command can push one branch, multiple branches, a tag, or even map a local branch to a different branch name on the remote. To control the outcome accurately, you need to understand **refspec**: the rule specifying which source is sent and which destination is updated.

The most common point of confusion is whether the branch name written in the command is the local branch name or the remote branch name. In `git push origin main`, Git takes the local `main` branch and pushes it to the `main` branch of remote `origin`. If you are currently on the `feature/cart` branch, that command still pushes the local `main` branch—it does not automatically push your current branch.

## 1. What Does git push Do?

A Git repository can contain many branches and tags. When pushing, Git sends the necessary commit objects to the destination repository and then requests updating the specified references, such as branch `refs/heads/main`.

Example:

~~~bash
git push origin main
~~~

The command above has three components:

- `push`: sends commits and updates refs in the destination repository.
- `origin`: the remote receiving the data.
- `main`: the local branch selected as the source; in this short form, Git also infers a remote destination branch of the same name.

If the remote rejects the update, the branch on the remote is not changed by that request. The cause may be non-fast-forward history, missing permissions, a protected branch, or server configuration.

Pushing is not the same as merging a Pull Request/Merge Request. Pushing only updates a ref on the remote according to server permissions and rules; the review and merge process usually takes place in a separate step.

## 2. Refspec Syntax and Structure

Common general syntax:

~~~bash
git push [options] <remote> <refspec>...
~~~

An explicit refspec has the form:

~~~text
<src>:<dst>
~~~

Where:

- `<src>` is the source in the local repository, usually a branch name, tag, or `HEAD`.
- `<dst>` is the ref to be updated in the remote repository, usually a branch or tag.
- The colon `:` separates source and destination.

Example:

~~~bash
git push origin feature/cart:feature/cart
~~~

Git takes the local `feature/cart` branch and updates the `feature/cart` branch on `origin`.

You can write the full destination to avoid ref-type ambiguity:

~~~bash
git push origin refs/heads/feature/cart:refs/heads/feature/cart
~~~

`refs/heads/` is the namespace for branches. Tags live under `refs/tags/`. When using short names, Git tries to interpret them from context; full ref names make the command clearer when names might be ambiguous.

### Reading source and destination as a mapping

Suppose the local repository has a `feature/cart` branch, and the team wants that branch to appear on the remote as `review/cart-checkout`:

~~~bash
git push origin feature/cart:refs/heads/review/cart-checkout
~~~

The mapping can be visualized like this:

~~~text
Local repository                         Remote origin
refs/heads/feature/cart  ------------->  refs/heads/review/cart-checkout
       source                                 destination
~~~

The name after the colon determines which ref on the remote will be updated. Swapping the two parts changes the command's meaning. Always read a refspec from left to right: **which source to take, which destination to send to**.

### Wildcard refspecs

When multiple branches need to be mapped by the same rule, a refspec can use the `*` wildcard in both source and destination:

~~~bash
git push origin 'refs/heads/release/*:refs/heads/archive/*'
~~~

For example, the local `release/1.x` branch is mapped to `archive/1.x` on the remote. This pattern fits workflows with consistent branch naming rules; before using it, make sure the pattern matches the exact branches you intend to send.

A leading plus sign `+` on a refspec allows forcing the update at that destination even when the update is non-fast-forward:

~~~bash
git push origin +feature/cart:refs/heads/feature/cart
~~~

This is how force is written directly inside a refspec. Only use it when intentionally replacing history at the destination; the section on force push below explains how to weigh `--force-with-lease`.

## 3. Pushing the Current Branch and Avoiding the Wrong Branch

### Pushing a named branch

~~~bash
git push origin main
git push origin feature/cart
~~~

Each command selects the exact local branch written in the command. The current pointer position does not change the meaning of an explicit branch name.

Check the current branch:

~~~bash
git branch --show-current
~~~

Check local branches:

~~~bash
git branch
~~~

If you are on `feature/cart` and run `git push origin main`, Git still pushes `main`. This is a common reason beginners mistakenly believe Git has sent their active working branch.

### Pushing the current branch to a remote branch with a different name

Use `HEAD` as the source to point to the commit your current branch refers to, and write out the destination:

~~~bash
git push origin HEAD:refs/heads/review/cart-checkout
~~~

This command pushes the current state to the remote `review/cart-checkout` branch. It is useful when sending a privately named local branch to a review or test branch on the server.

### Setting upstream on the first push

When creating a new local branch and wanting to track a remote branch of the same name:

~~~bash
git switch -c feature/cart
# edit and commit
git push --set-upstream origin feature/cart
~~~

You can shorten `--set-upstream` to `-u`. After a successful push, Git records the tracking relationship between the local branch and the remote branch. While on that branch, subsequent runs can usually use:

~~~bash
git push
git pull
~~~

The upstream relationship lets Git infer the remote and tracked branch in commands without an explicit destination. It does not mean every push automatically sends every branch.

## 4. Pushing Multiple Branches at Once

You can pass multiple refspecs in a single command:

~~~bash
git push origin main feature/cart feature/search
~~~

Git will push the listed local branches to branches of the same names on the remote. If one refspec is rejected, read the per-ref output to see which refs updated and which failed.

When different names need to be mapped, write out each source and destination pair:

~~~bash
git push origin main:refs/heads/stable feature/cart:refs/heads/review/cart
~~~

Do not include multiple branches out of habit if your goal is only to send one feature branch. Specifying the exact refspec limits the scope of changes on the remote.

## 5. Pushing Tags

Tags typically mark versions or release milestones. To push a specific tag:

~~~bash
git push origin v1.4.0
~~~

You can write the full ref type:

~~~bash
git push origin refs/tags/v1.4.0:refs/tags/v1.4.0
~~~

To push all local tags to the remote:

~~~bash
git push origin --tags
~~~

The `--follow-tags` option has narrower behavior: in addition to the refs being pushed, Git also pushes annotated tags reachable from the pushed commits that do not yet exist on the remote. This is usually the right choice when you want to send release tags associated with the commits just pushed.

Published tags are generally treated as stable milestones. Before changing or overwriting a tag on the remote, check your team's release conventions.

## 6. Deleting a Branch on the Remote

To delete a remote branch, you can use the readable option:

~~~bash
git push origin --delete feature/old-checkout
~~~

The equivalent refspec syntax leaves the source empty:

~~~bash
git push origin :refs/heads/feature/old-checkout
~~~

In this case, the colon tells Git to delete the destination ref. The command deletes the branch on the remote; the local branch of the same name remains until you delete it locally, for example:

~~~bash
git branch -d feature/old-checkout
~~~

Only delete a remote branch when you are sure it has been merged or the team no longer needs it. The server may reject deleting a protected branch.

## 7. Default Refspecs and Push Configuration

When running `git push` without specifying a remote or refspec, Git must infer where to send and which branch to send from configuration.

Relevant settings include:

| Setting | Role |
|---|---|
| `branch.<name>.pushRemote` | Preferred push remote specifically for that branch |
| `remote.pushDefault` | Default push remote for the repository |
| `branch.<name>.remote` | Remote that the local branch tracks for fetching changes |
| `remote.<name>.push` | Default refspec when pushing to that remote without supplying a refspec on the command |
| `push.default` | Branch selection rule when no explicit refspec or per-remote default refspec is given |

### Common values for push.default

Check the current value:

~~~bash
git config --get push.default
~~~

Common modes:

| Value | Behavior |
|---|---|
| `simple` | Common default mode; in centralized workflows, pushes the current branch to its upstream when names match and errors if names do not match. When pushing to a different remote than the one used for pulling (fork workflow), behaves like `current` |
| `current` | Pushes the current branch to a branch of the same name on the selected remote |
| `upstream` | Pushes the current branch to its configured upstream branch |
| `matching` | Pushes local branches whose names correspond to branches already existing on the remote |
| `nothing` | Does not infer a branch to push; requires specifying a refspec |

For beginners, keeping `simple` mode helps prevent accidentally pushing the wrong branch when local and upstream branch names differ. `matching` mode can push more branches than intended, so understand it thoroughly before using it.

You can set the configuration at the repository level:

~~~bash
git config push.default simple
~~~

Add `--global` if you want it to apply across repositories for the current user:

~~~bash
git config --global push.default simple
~~~

Global configuration affects multiple projects, so change it only once you understand the impact. In fork environments, the remote used for fetching and the remote used for pushing can differ; `pushRemote` or `remote.pushDefault` lets you specify the appropriate push target.

## 8. Checking Before Pushing

Before sending commits to the server, verify the branch, remote, and current changes:

~~~bash
# Verify current repository and branch
git status
git branch --show-current

# View remotes and URLs
git remote -v

# View the latest commit on the current branch
git log -1 --oneline

# View local branches
git branch
~~~

You can list branches currently existing on the remote:

~~~bash
git ls-remote --heads origin
~~~

This command queries branch refs on remote `origin`; unlike `git fetch`, it does not update remote-tracking branches in the local repository.

Use `--dry-run` to preview what Git intends to push without updating the remote:

~~~bash
git push --dry-run origin feature/cart:refs/heads/review/cart
~~~

`--dry-run` is helpful for reviewing a refspec, though it does not guarantee the real push will succeed: permissions, remote state, or server policies could still change afterward.

## 9. When a Push Is Rejected

### Non-fast-forward

Example:

~~~text
! [rejected]  main -> main (non-fast-forward)
error: failed to push some refs
~~~

The remote has commits that the local branch has not integrated yet, so a normal update would lose history on the remote. Retrieve the latest info and inspect history:

~~~bash
git fetch origin
git log --oneline --graph --decorate --all
~~~

Then integrate the remote branch into the local branch following your team's workflow—using merge or rebase—resolve any conflicts, and push again.

### Missing permissions or protected branch

If the server reports missing permissions, failed authentication, or a protected branch, even a correct refspec will not make the push succeed. Check the URL, account, SSH key/token, write permissions, and branch protection policy. For a protected main branch, you typically need to push a feature branch and open a Pull Request/Merge Request.

### Refspec does not match

Errors like `src refspec ... does not match any` usually occur when the source name does not exist, the branch has not been created yet, or the repository has no matching commit.

Verify branch names and commits:

~~~bash
git branch --list
git show-ref
git status
~~~

Fix the source in the refspec to match an actual branch or tag before pushing again.

## 10. Force Push and Protecting History

A rejected update is sometimes caused by history having been rewritten via rebase or amend. By default, Git blocks non-fast-forward updates to prevent overwriting commits others may rely on.

`--force` forces updating the destination ref:

~~~bash
git push --force origin feature/cart
~~~

This command can drop commits currently on the remote if they are not part of the history being pushed. Only use it when you understand the history being replaced and have coordinated with anyone involved.

In many situations, `--force-with-lease` is safer:

~~~bash
git push --force-with-lease origin feature/cart
~~~

Git allows the forced update only if the remote ref is still at the value local expects, usually compared against the known remote-tracking ref. This helps detect whether someone else updated the remote since you last checked. For stricter control, you can specify the expected value explicitly:

~~~bash
git push --force-with-lease=refs/heads/feature/cart:<expected-object-id> origin feature/cart
~~~

Even `--force-with-lease` must be used intentionally. Fetch and inspect history before rewriting a shared branch. Never force push to a main branch or shared branch without consensus and an established workflow allowing it.

## 11. Practical Example: Sending a Feature Branch for Review

Suppose you are developing a shopping cart feature. The local branch is named `feature/cart`, and the team wants to create a review branch `review/cart-checkout` on remote `origin`.

1. Verify you are in the right repository and branch:

~~~bash
git status
git branch --show-current
~~~

2. Review the commits to be sent and update remote info if needed:

~~~bash
git fetch origin
git log --oneline --decorate origin/main..feature/cart
~~~

3. Push the local branch to a differently named review branch while setting upstream:

~~~bash
git push --set-upstream origin feature/cart:review/cart-checkout
~~~

Because the local and remote branch names differ, `push.default=simple` mode may reject a bare `git push` next time. When continuing to use a different destination name, specify the refspec explicitly; or agree on a push configuration suited to your team's workflow.

4. Verify the remote branch has appeared:

~~~bash
git ls-remote --heads origin review/cart-checkout
~~~

5. Open a Pull Request/Merge Request from `review/cart-checkout` into the project's target branch per team process.

If the team wants the review destination to always match the local name, using `git push -u origin feature/cart` is simpler. What matters before pushing is verifying that the local source and remote destination match the review goal.

## 12. Key Takeaways

- A refspec has the form `<src>:<dst>`: the left side is the local source, the right side is the destination ref on the remote.
- `git push origin main` pushes the local `main` branch; it does not mean "push the currently checked-out branch."
- Use `HEAD:refs/heads/<branch-name>` when you want to send the current branch to a specific remote branch name.
- Use `-u` to establish upstream on the first push.
- You can push multiple branches, push tags, or delete remote branches with appropriate refspecs and options.
- When no refspec is given, Git relies on remote configuration and `push.default`; understand your configuration before using shorthand commands.
- Use `--dry-run` to preview an intended push. Force push only when you understand the impact on history and have coordinated with your team.

A safe push begins by clearly identifying three things: **which remote receives the data, which local source is sent, and which ref on the remote will change**. When you can read those three parts in a refspec, you can deliberately push the right branch instead of guessing based on your current branch.

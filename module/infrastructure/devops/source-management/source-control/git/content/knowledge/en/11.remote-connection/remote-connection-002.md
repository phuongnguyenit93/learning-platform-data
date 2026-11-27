# Adding, Renaming, Listing, and Removing Remotes with git remote

## What Is a Remote in Git?

When working with Git, a **remote** is a short alias that a local repository uses to reference another Git repository. A remote typically points to a repository hosted on GitHub, GitLab, Bitbucket, or an organization's Git server. It can also point to a repository on another machine or a local path.

Remotes tell Git where to pull commits from and where to send commits when performing operations like `fetch`, `pull`, and `push`. Each remote has a name, a URL, and associated synchronization settings. Common names include:

- `origin`: the default remote name created when cloning a repository.
- `upstream`: commonly used to refer to the original repository that a fork tracks.
- `backup`: can be used for a standby or backup repository.
- `team`: can be used for a team's internal shared repository.

These names are only conventions. Git does not require using `origin` or `upstream`; users can choose names that fit how their project is organized.

It is important to distinguish three concepts:

- **Remote:** a configuration referencing another repository, such as `origin`.
- **Remote-tracking branch:** a local reference recording the branch state that Git knows about on the remote, such as `origin/main`.
- **Local branch:** a working branch in the local repository, such as `main` or `feature/login`.

`origin/main` is not a branch being worked on directly on the server. It is a local reference updated when fetching data from the remote. The `main` branch is your local branch; the two branches can evolve independently.

## Listing Remotes

The `git remote` command lists the names of remotes configured in the current repository:

~~~bash
git remote
~~~

Sample output:

~~~text
origin
upstream
~~~

To view both the fetch and push URLs, add the `-v` (verbose) option:

~~~bash
git remote -v
~~~

Example:

~~~text
origin    git@github.com:alice/inventory-app.git (fetch)
origin    git@github.com:alice/inventory-app.git (push)
upstream  https://github.com/company/inventory-app.git (fetch)
upstream  https://github.com/company/inventory-app.git (push)
~~~

A remote can have separate fetch and push URLs. Therefore, read both lines if you need to verify where Git is pulling data from and where it is sending data to.

To view detailed information about a remote:

~~~bash
git remote show origin
~~~

This command may connect to the remote to display URLs, the default branch (HEAD), remote branches, and tracking configuration between local and remote branches. If you only want to view locally cached information without querying the network, use:

~~~bash
git remote show -n origin
~~~

If you need to list the remote-tracking branches that the local repository currently knows about:

~~~bash
git branch -r
~~~

The `git branch -r` command lists remote branches that have been fetched into the local repository; it is not a command to list remote names. To view both local branches and remote-tracking branches, use `git branch -a`.

## Adding a Remote with git remote add

Use `git remote add` when you want to connect the current repository to another Git repository. Basic syntax:

~~~bash
git remote add <remote-name> <url>
~~~

Example adding a team's shared repository under the name `origin`:

~~~bash
git remote add origin git@github.com:company/inventory-app.git
~~~

Or adding the original repository to track when working on a fork:

~~~bash
git remote add upstream https://github.com/company/inventory-app.git
~~~

Verify the configuration again:

~~~bash
git remote -v
~~~

### Adding a Remote and Fetching Immediately

By default, `git remote add` only saves the remote configuration. To add a remote and fetch data right away, use the `-f` option:

~~~bash
git remote add -f upstream https://github.com/company/inventory-app.git
~~~

After fetching, you can view the remote-tracking branches:

~~~bash
git branch -r
~~~

Sample output:

~~~text
upstream/HEAD -> upstream/main
upstream/main
upstream/release
~~~

Without `-f`, the remote is still created, but remote branch references are not updated until you run:

~~~bash
git fetch upstream
~~~

Some other options you may encounter:

- `-t <branch>`: specify the branch to track when fetching.
- `-m <branch>`: set the default branch (remote HEAD) for the remote.
- `--no-tags`: do not automatically fetch related tags when fetching from this remote.
- `--tags`: fetch all reachable tags when fetching.
- `--mirror=fetch` or `--mirror=push`: configure the remote in a specialized mirror mode; only use when you understand its impact on references.

In most standard development workflows, the simple add-remote command is sufficient. After adding it, verify the URL with `git remote -v` before pushing to avoid sending source code to the wrong repository.

### Choosing HTTPS or SSH URLs

Git typically connects to remotes via HTTPS or SSH. Examples:

~~~text
HTTPS: https://github.com/company/inventory-app.git
SSH:   git@github.com:company/inventory-app.git
~~~

HTTPS typically uses credentials via a credential manager or tokens according to platform policy. SSH uses an SSH key that has been configured and granted access on the Git hosting service.

Do not embed passwords, tokens, or secret keys directly into the URL and store them in remote configuration. URLs can appear in logs, configuration snapshots, or when sharing diagnostic output.

## Renaming a Remote with git remote rename

Use `git remote rename` when you want to change the name of a remote while preserving its connection and already fetched data:

~~~bash
git remote rename <old-name> <new-name>
~~~

Example renaming `origin` to `company`:

~~~bash
git remote rename origin company
~~~

Verify the result:

~~~bash
git remote -v
git branch -r
~~~

Git updates the remote configuration and renames the corresponding remote-tracking references. For example, the `origin/main` reference moves to `company/main`. Related remote settings are also updated along with the rename operation.

Renaming a remote does not rename the repository on GitHub/GitLab and does not change the repository's URL. If your goal is to switch to a new URL, use `git remote set-url`.

You cannot rename a remote to a name already used by another remote. If the command reports that the target name already exists, choose another name or resolve the duplicate remote after identifying which configuration to keep.

## Changing a Remote's URL

When a repository moves to a new server, changes ownership, changes paths, or switches from HTTPS to SSH, you can update the URL with `git remote set-url`:

~~~bash
git remote set-url origin git@github.com:company/inventory-app.git
~~~

Verify:

~~~bash
git remote -v
git remote get-url origin
~~~

If a remote has multiple URLs, view all URLs with:

~~~bash
git remote get-url --all origin
~~~

Git supports configuring a separate push URL. When you want to change only the URL used for pushing, add `--push`:

~~~bash
git remote set-url --push origin git@github.com:company/inventory-app.git
~~~

You can add an extra push URL with `--add`, or remove a matching URL with `--delete`. Check the result with `git remote -v` after making changes, especially when a remote has multiple URLs. Changing the URL only updates the configuration in the local repository; it does not migrate data or change the repository's address on the server.

## Removing a Remote with git remote remove

Use `git remote remove` when you no longer need a connection to a remote:

~~~bash
git remote remove <remote-name>
~~~

Example:

~~~bash
git remote remove upstream
~~~

The equivalent shorthand command is:

~~~bash
git remote rm upstream
~~~

After removing it, check the list:

~~~bash
git remote -v
~~~

This operation removes the remote configuration and the remote-tracking branches belonging to that remote from the local repository. It **does not delete the Git repository on the server**, does not delete a fork on GitHub/GitLab, and does not delete your local commits or branches.

If a local branch was tracking the newly removed remote, the branch's upstream information may no longer be useful. Check with:

~~~bash
git branch -vv
~~~

If you need to continue tracking another remote, add or select the appropriate remote and reconfigure the upstream, for example:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

Only remove a remote after confirming its exact name. If the repository has multiple remotes, check `git remote -v` first to avoid accidentally deleting a configuration currently used by the team.

## Cleaning Up Stale Remote-Tracking Branches

Removing a remote and cleaning up remote branches that have been deleted on the server are two different operations.

Suppose the `origin` remote still exists, but the `feature/old-report` branch was deleted on the server. The local reference `origin/feature/old-report` may remain until pruned.

Preview the references that will be removed:

~~~bash
git remote prune --dry-run origin
~~~

Perform the cleanup:

~~~bash
git remote prune origin
~~~

Or combine pruning during a fetch:

~~~bash
git fetch --prune origin
~~~

Pruning only removes remote-tracking references that no longer correspond to a branch on the remote. It does not delete local branches such as `feature/old-report` and does not delete branches on the server.

## Practical Workflow: Working with a Fork and Original Repository

A common scenario is a developer forking a project to their personal account, then cloning the fork to their machine. In this example:

- `origin` points to the developer's fork, where they have push permissions.
- `upstream` points to the project's original repository, where the team maintains the primary version.

You can inspect and configure this as follows:

~~~bash
# Clone the fork to the local machine; Git automatically creates the origin remote
git clone git@github.com:alice/inventory-app.git
cd inventory-app

# Add the original repository to receive new changes
git remote add upstream https://github.com/company/inventory-app.git

# View both remotes and their corresponding URLs
git remote -v

# Fetch new commits from the original repository
git fetch upstream

# Switch to the local main branch
git switch main

# Integrate changes from the original repository's main branch
git merge upstream/main

# Share the updated main branch to your own fork
git push origin main
~~~

Data flow in the example:

~~~mermaid
flowchart LR
    U[Original repository<br/>upstream] -->|fetch| L[Local repository]
    L -->|push| O[Personal fork<br/>origin]
~~~

When a project requires keeping a linear history, the team may use `git rebase upstream/main` instead of merge, following agreed collaboration policies. Do not rebase a shared branch that others have already based work on without coordinating with them.

## Commonly Used git remote Commands

| Command | Purpose |
|---|---|
| `git remote` | List remote names |
| `git remote -v` | List remotes along with fetch/push URLs |
| `git remote show origin` | View details about a remote |
| `git remote add origin <url>` | Add a new remote |
| `git remote rename old new` | Rename a remote |
| `git remote set-url origin <url>` | Change a remote's fetch URL |
| `git remote get-url --all origin` | View all URLs of a remote |
| `git remote remove origin` | Remove a remote configuration from the local repository |
| `git remote prune origin` | Remove stale remote-tracking references |
| `git fetch --prune origin` | Fetch and clean up stale remote-tracking references |

## Common Errors and Troubleshooting

### Remote Already Exists

When running `git remote add origin ...` while `origin` is already configured, Git reports that the remote already exists. Check the current URL:

~~~bash
git remote -v
~~~

If you only need to change the URL, use:

~~~bash
git remote set-url origin <new-url>
~~~

If you need to connect an additional repository, choose a different name, such as `upstream`.

### Remote Branches Not Visible After Adding

`git remote add` does not fetch data by default. Run:

~~~bash
git fetch origin
git branch -r
~~~

Then choose a remote-tracking branch to create or update a local branch.

### Pushing to the Wrong Repository

Before pushing, verify the remote and URL:

~~~bash
git remote -v
git push -u origin feature/report
~~~

If the repository has multiple remotes, specify the target remote explicitly in the push command instead of relying on the assumption that `origin` is always where code should be sent.

### Unable to Connect After Changing the URL

Double-check URL spelling, access permissions, SSH keys, or HTTPS credentials. You can test connectivity to the remote with:

~~~bash
git ls-remote origin
~~~

This command reads references from the remote without modifying the current branch. If you lack permissions or valid credentials, fix the access configuration before fetching or pushing.

### Local Branches Still Visible After Removing a Remote

This is normal behavior. `git remote remove` deletes the remote and associated remote-tracking references; local branches such as `main` or `feature/report` still remain. Check with:

~~~bash
git branch
git branch -vv
~~~

## Safe Working Habits

- Use remote names that describe the repository's role, especially when the project has multiple remotes.
- Check `git remote -v` before the first push and after every URL change.
- Use `git fetch` to update information from the remote before deciding to merge or rebase.
- Distinguish `origin/main` from `main`; one is a remote-tracking reference, and the other is a local branch.
- Only remove a remote after confirming it is no longer needed and checking which branches are tracking it.
- Do not store tokens or passwords inside remote URLs.
- Agree with the team on the primary remote, push permissions, and how shared branches are updated.

## Summary

`git remote` manages the connections a local repository uses to exchange data with other Git repositories. Use `git remote` to list, `git remote -v` to inspect URLs, `git remote add` to add, `git remote rename` to rename, `git remote set-url` to change addresses, and `git remote remove` to remove configurations. Keep in mind that a remote is a configuration in the local repository: removing a remote does not delete the repository on the server, changing a URL does not move data, and commits are only shared when pushed to the right remote.

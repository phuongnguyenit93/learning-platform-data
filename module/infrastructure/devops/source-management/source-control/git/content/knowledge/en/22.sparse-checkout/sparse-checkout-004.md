# Limiting downloaded branches with --single-branch and refspecs

A repository on the server may have dozens or hundreds of branches. When cloning a large repository, you may only need to work on one stable branch or a specific release branch. Git provides the **--single-branch** option to limit the history fetched to a single branch, along with **refspecs** to explicitly define which refs are fetched and where they are stored in the local repository.

These two mechanisms reduce the number of remote-tracking branches and limit the synchronization scope. They control **which Git branches and refs are fetched**. They do not select directories or files appearing in the working tree; selecting paths falls under sparse-checkout.

After this lesson, you will be able to:

- Clone a repository tracking only one branch with --single-branch.
- Understand the relationship between --single-branch and remote.origin.fetch.
- Read and write source:destination refspecs.
- Fetch only a single branch or a specific group of branches.
- Expand or change the list of tracked branches after cloning.
- Inspect remote branches with git branch -r and git ls-remote.
- Distinguish branch limiting from sparse-checkout, shallow clone, and partial clone.

## 1. Distinguishing fetched branches from files in the working tree

Git offers multiple ways to narrow the scope of data a copy needs to use. Each controls a different dimension:

| Mechanism | What does it limit? | Example |
| --- | --- | --- |
| --single-branch and refspecs | Branches or refs fetched and updated locally. | Track only main or a few release branches. |
| sparse-checkout | Paths present in the working tree. | Check out only src/service and docs directories. |
| --depth or --shallow-since | Depth of commit history fetched. | Fetch only a certain number of recent commits. |
| Partial clone with --filter | Types of Git objects downloaded immediately. | Defer downloading blobs until needed. |

For example, cloning with `--single-branch` on main still fetches the file tree contents needed for main's history. It does not select only the src/ directory or skip the docs/ directory. Conversely, sparse-checkout can restrict paths in the working tree, but that does not mean only one remote branch was fetched.

In the Sparse Checkout chapter, these techniques can be combined to reduce footprint as needed. Determine whether you want to limit refs, paths, history, or object types before choosing an option.

## 2. --single-branch in git clone

In a normal clone:

~~~bash
git clone https://example.com/team/product.git
~~~

Git creates the default remote named origin, checks out the remote's default branch, and normally configures fetch to track multiple remote branches. Remote-tracking branches can be viewed with:

~~~bash
git branch -r
~~~

If you only need one branch, use:

~~~bash
git clone --single-branch --branch main https://example.com/team/product.git product-main
~~~

This command clones the history leading up to the tip of the main branch and configures the new repository so that subsequent fetches update only the selected branch under single-branch configuration. If `--branch` is omitted, Git uses the branch that the remote's HEAD points to as the default branch:

~~~bash
git clone --single-branch https://example.com/team/product.git
~~~

After cloning, there is typically only one remote-tracking branch:

~~~bash
git branch -r
~~~

Example:

~~~text
origin/main
~~~

Other branches still exist on the server. They are neither deleted nor modified; the local clone simply does not fetch or track them under its current configuration.

### Choosing another branch with --branch

The --branch option selects the branch to check out after cloning. It does not itself limit how many branches are fetched. If you want to fetch only the history of the selected branch, combine both options:

~~~bash
git clone --branch release/2.x --single-branch https://example.com/team/product.git product-release
~~~

This command checks out release/2.x and fetches only that branch's history in single-branch mode. If you omit --single-branch, specifying --branch does not stop other branches from being fetched.

### Allowing all branches to be fetched

If you want to clone normally and track a broader set of branches, you can use:

~~~bash
git clone --no-single-branch https://example.com/team/product.git
~~~

--no-single-branch is also useful when overriding single-branch behavior implicitly enabled by another option in the clone command, such as --depth.

## 3. How is --single-branch stored in the fetch configuration?

After cloning, Git saves the remote's fetch rules in the repository configuration. Check:

~~~bash
git config --get-all remote.origin.fetch
~~~

For a single-branch clone of main, the output usually looks like:

~~~text
+refs/heads/main:refs/remotes/origin/main
~~~

This is a refspec:

- refs/heads/main is the source branch on the remote.
- refs/remotes/origin/main is the destination remote-tracking ref in the local repository.
- The leading + sign allows updating the destination ref even when remote history was rewritten and the update is not a fast-forward.

For a normal clone tracking all branches, the common configuration is:

~~~text
+refs/heads/*:refs/remotes/origin/*
~~~

The * is a wildcard, allowing multiple branches to be mapped using the same pattern. For example, refs/heads/feature/search on the remote maps to refs/remotes/origin/feature/search locally.

Key point: --single-branch is not a mechanism completely separate from fetch. During clone, Git writes a narrow refspec so subsequent fetches update only the chosen branch. Therefore, inspecting remote.origin.fetch tells you exactly which branches the repository is tracking.

## 4. Refspec syntax

A fetch refspec has the general form:

~~~text
[+]SOURCE:DESTINATION
~~~

| Component | Meaning |
| --- | --- |
| SOURCE | The ref on the remote side that Git needs to fetch. |
| DESTINATION | The local ref that receives the result, typically a remote-tracking ref. |
| Optional + sign | Allows updating the destination ref even if the change is not a fast-forward. |

Example mapping one branch:

~~~text
+refs/heads/main:refs/remotes/origin/main
~~~

Example mapping a group of branches:

~~~text
+refs/heads/release/*:refs/remotes/origin/release/*
~~~

In the second example, the release/2.x and release/3.x branches on the remote are mapped to origin/release/2.x and origin/release/3.x locally. The wildcards in source and destination must correspond so Git substitutes the matched part into the destination position.

Refspecs can be passed directly to `git fetch` or saved in remote.origin.fetch. When saved in configuration, they become the default fetch scope for that remote.

### Fetching one branch and specifying the destination explicitly

To fetch the feature/search branch and update the corresponding remote-tracking ref:

~~~bash
git fetch origin +refs/heads/feature/search:refs/remotes/origin/feature/search
~~~

This command states both source and destination explicitly. Using an explicit refspec avoids confusion between fetching a branch into FETCH_HEAD and updating a stably named remote-tracking ref.

If the destination part of the refspec is omitted, Git writes the fetch information to FETCH_HEAD:

~~~bash
git fetch origin refs/heads/feature/search
~~~

FETCH_HEAD records what that fetch retrieved and can be used by a subsequent integration step. If you need a persistent remote-tracking ref for comparison and tracking, specify the destination or configure the corresponding refspec.

## 5. Using refspecs to fetch only specific branches

Suppose a repository has many branches, but the deployment team only needs main and two maintenance branches. You can configure the remote to track only those branches.

Use `git remote set-branches`:

~~~bash
git remote set-branches origin main maintenance/2.x maintenance/3.x
git fetch origin
~~~

The `set-branches` command replaces the list of branches tracked by remote origin with the specified list. After fetching, verify:

~~~bash
git config --get-all remote.origin.fetch
git branch -r
~~~

If you only want to add a branch to the current list while keeping previously configured branches, use --add:

~~~bash
git remote set-branches --add origin feature/search
git fetch origin
~~~

Afterward, the remote-tracking ref origin/feature/search can be used to create a local branch:

~~~bash
git switch --track -c feature/search origin/feature/search
~~~

This command creates the local branch feature/search and sets origin/feature/search as its upstream.

### Configuring via git config

You can also manage refspecs directly in local configuration:

~~~bash
# Replace the entire fetch list with only the main branch
git config --replace-all remote.origin.fetch "+refs/heads/main:refs/remotes/origin/main"

# Add another branch
git config --add remote.origin.fetch "+refs/heads/feature/search:refs/remotes/origin/feature/search"

# Review the currently active refspecs
git config --get-all remote.origin.fetch
~~~

This is configuration specific to the current repository, usually located in `.git/config`. Do not commit this local configuration file as a substitute for team workflow documentation.

If you want to expand scope from single-branch, add a refspec or use `remote set-branches --add`. Run `git fetch` only after confirming the new list is correct.

## 6. Using wildcards to track a group of branches

When branch names follow a convention, wildcards avoid declaring each branch individually. For example, fetching only branches starting with `release/`:

~~~bash
git fetch origin "+refs/heads/release/*:refs/remotes/origin/release/*"
~~~

This command fetches refs matching the pattern and updates remote-tracking refs in the `origin/release/` namespace. It does not create local branches automatically.

To configure this pattern for future fetches:

~~~bash
git config --add remote.origin.fetch "+refs/heads/release/*:refs/remotes/origin/release/*"
git fetch origin
~~~

If the old configuration still contains the broad wildcard:

~~~text
+refs/heads/*:refs/remotes/origin/*
~~~

then adding a `release/*` refspec does not restrict the fetch, because the broad refspec still requests fetching every branch. To actually restrict it, replace the broad refspec with narrow ones—for example using `git remote set-branches origin main "release/*"` or replacing the config with `--replace-all` and `--add`.

In a shell, wrap refspecs containing the `*` character in quotation marks so the shell does not expand the wildcard before Git receives it. Exact quoting rules may differ across Bash, PowerShell, and other shells; the examples above use double quotes suitable for common shells.

## 7. Expanding scope after a single-branch clone

Suppose you initially cloned with:

~~~bash
git clone --single-branch --branch main https://example.com/team/product.git
cd product
~~~

Later, you need to add the `feature/search` branch. You can run:

~~~bash
git remote set-branches --add origin feature/search
git fetch origin
git branch -r
~~~

The resulting remote-tracking branches will include main and feature/search:

~~~text
origin/main
origin/feature/search
~~~

Create a local branch to work on:

~~~bash
git switch --track -c feature/search origin/feature/search
~~~

If later you no longer need to track `feature/search`, you can replace the branch list:

~~~bash
git remote set-branches origin main
~~~

Changing the configuration does not automatically delete the local `feature/search` branch, nor does it necessarily delete existing remote-tracking refs. To clean up remote-tracking refs no longer advertised by the remote within the current refspec scope, you can use prune:

~~~bash
git fetch --prune origin
~~~

Prune operates based on the currently configured fetch mappings. When changing refspecs, inspect the list of refs and understand the prune scope before running it; prune does not delete local branches with the same name.

## 8. Viewing all branches on the remote without fetching

After a single-branch clone, `git branch -r` only displays remote-tracking refs that the local repository already knows about. It is not the complete list of branches existing on the server.

To view remote branches without downloading objects or updating remote-tracking refs, use:

~~~bash
git ls-remote --heads origin
~~~

This command queries branch refs on the remote. You can filter by pattern:

~~~bash
git ls-remote --heads origin "refs/heads/release/*"
~~~

Compare the commands:

| Command | Result |
| --- | --- |
| git branch -r | Lists remote-tracking refs already present locally. |
| git ls-remote --heads origin | Lists branch refs advertised by the remote at query time. |
| git fetch origin <refspec> | Fetches required objects and updates local refs according to the refspec. |

If `git ls-remote` displays a branch but `git branch -r` does not include it, this may simply mean you haven't fetched that branch yet.

## 9. Fetch --all does not mean fetching every branch

A common misconception is that:

~~~bash
git fetch --all
~~~

fetches every branch of every remote. In reality, `--all` requests fetching from all configured remotes, but each remote still uses its own fetch refspecs. If `origin` is configured as single-branch, `fetch --all` still only fetches the ref scope permitted by `origin`'s configuration.

Example:

~~~bash
git remote -v
git config --get-all remote.origin.fetch
git config --get-all remote.upstream.fetch
git fetch --all
~~~

`origin` may track only `main`, while `upstream` tracks every branch. The `fetch --all` command applies those two separate configurations; it does not automatically expand a narrow refspec into a wildcard.

## 10. Prune and stale remote-tracking refs

When a branch is deleted on the remote, the corresponding remote-tracking ref may remain locally until cleaned up. Use:

~~~bash
git fetch --prune origin
~~~

Git deletes remote-tracking refs within the fetch mapping scope that no longer have a corresponding source branch on the remote. This keeps `git branch -r` reflective of the current state.

Prune does not delete local branches:

~~~bash
git branch --list
git branch -r
~~~

A local branch `feature/search` remains even if `origin/feature/search` has been pruned. Deleting a local branch is a separate decision, and you should verify whether its commits have already been merged or saved elsewhere.

If the refspec configuration was narrowed, old remote-tracking refs lying outside the new mapping may no longer be managed by current prune runs. Inspect `git branch -r` and `remote.origin.fetch` before cleaning up manually.

## 11. Combining --single-branch with shallow clone

When a repository is very large, you can combine branch limiting and history depth limiting:

~~~bash
git clone --single-branch --branch main --depth 20 https://example.com/team/product.git product-main
~~~

This command fetches only the history of the `main` branch within the requested depth. `--depth` limits the number of commit history layers; `--single-branch` limits which branch is fetched. The two options address two different dimensions.

Note that `--depth` automatically implies `--single-branch` unless combined with `--no-single-branch`. If you want a shallow clone while still fetching depth-limited history of multiple branches, you can use:

~~~bash
git clone --depth 20 --no-single-branch https://example.com/team/product.git
~~~

A shallow repository has limitations in certain history operations such as merging or tracing distant ancestors. When full history is needed, you can fetch additional commits with `fetch --deepen` or remove the limit with `fetch --unshallow`, depending on repository state.

## 12. Practical workflow: fetching only needed branches

Suppose the team has an `origin` remote with many branches, but the deployment environment only needs `main` and release branches. A workflow could be:

~~~bash
# 1. Clone only the main branch
git clone --single-branch --branch main https://example.com/team/product.git product
cd product

# 2. Verify the single-branch refspec that was created
git config --get-all remote.origin.fetch

# 3. View locally known branches and actual remote branches
git branch -r
git ls-remote --heads origin

# 4. Update configuration to track main and release branches
git remote set-branches origin main "release/*"

# 5. Fetch using the new scope
git fetch origin

# 6. Verify remote-tracking refs
git branch -r

# 7. If you need to work on a specific release branch
git switch --track -c release/2.x origin/release/2.x
~~~

If your shell or Git version does not handle wildcards as expected, you can use explicit refspecs with `git config` or direct `fetch` commands. Always review `remote.origin.fetch` to confirm the actual scope.

## 13. Common errors

### Used --branch but still seeing many remote-tracking branches

--branch only selects the branch to check out. To limit the number of branches fetched, add --single-branch when cloning.

### Already did a single-branch clone but need an additional branch

Use `git remote set-branches --add origin BRANCH` then `git fetch origin`. Afterward, create a local branch from the remote-tracking ref if needed.

### Added a narrow refspec but fetch still pulls many branches

Check all values of `remote.origin.fetch`. A broad wildcard refspec remaining in the configuration will continue requesting all branches; replace it instead of merely adding a narrow refspec.

### git branch -r does not show a branch a teammate says exists

Check with `git ls-remote --heads origin`. If the remote has that branch, add the refspec and fetch.

### Fetched a branch but don't see the corresponding remote-tracking ref

Check whether the refspec has a destination part. Without a destination, the fetch may only record details in FETCH_HEAD. Use a source:destination refspec to update the remote-tracking ref explicitly.

### git fetch --all still does not fetch all branches

--all only expands which remotes are fetched; each remote's branch scope still depends on its respective refspec.

### Thinking --single-branch only downloads one directory

Incorrect. This option limits branches and the history reachable from them. To select directories in the working tree, use sparse-checkout; to reduce downloaded object types, look at partial clone and object filters.

## 14. Key takeaways

- --single-branch limits the cloned branch and the scope of remote-tracking refs updated later.
- --branch selects the checked-out branch; by itself it does not limit fetched branches.
- A refspec has the form SOURCE:DESTINATION and can take a leading + to allow non-fast-forward updates.
- remote.origin.fetch stores the default fetch refspecs of the origin remote.
- git remote set-branches replaces the tracked branch list; --add appends a branch to the current list.
- Wildcard refspecs are useful when tracking a group of branches following a naming convention.
- git branch -r displays local fetched refs; git ls-remote --heads inspects refs currently on the server without fetching.
- git fetch --all still respects each remote's individual refspec.
- --prune cleans up stale remote-tracking refs within the refspec scope; it does not delete local branches.
- Limiting refs with --single-branch/refspecs is distinct from limiting paths with sparse-checkout, limiting history with --depth, and filtering objects with --filter.

When `--single-branch` and refspecs are configured properly, you can keep your local repository tracking only the branches relevant to your current work. This keeps the list of remote-tracking refs tidy and clarifies the sync scope, while still letting you expand the branch list when needs change.

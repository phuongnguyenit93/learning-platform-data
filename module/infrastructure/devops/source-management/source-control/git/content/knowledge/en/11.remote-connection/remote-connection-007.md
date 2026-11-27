# Refspec and Mapping `refs/heads` to `refs/remotes`

When working with a remote, Git needs to know **which refs to retrieve from the remote repository and where to store them in the local repository**. When pushing, Git needs to know **which local ref to read and which ref on the remote to update**. The rule describing both ends of this mapping is called a *refspec*.

Refspecs are fundamental to understanding why after `git fetch origin`, we commonly see `origin/main`; why `main` and `origin/main` can point to two different commits; and why a remote can fetch only certain branches or store remote branches under a custom namespace. This topic belongs to Git's remote connection layer: it connects branches, remotes, fetch, push, upstreams, and the history used when collaborating, resolving conflicts, or tracing changes.

## 1. What Is a Ref?

In Git, a **ref (reference)** is a name that resolves to a Git object, usually a commit. Instead of having to remember long commit hashes, we use names like `main`, `feature/login`, `v1.2.0`, or `origin/main`.

Git stores refs in namespaces. Some common namespaces:

| Namespace | Meaning | Example |
|---|---|---|
| `refs/heads/` | Local branches in the current repository; on a remote repository, this is also the namespace holding that remote's branches. | `refs/heads/main` |
| `refs/remotes/` | Remote-tracking refs stored in the local repository to record branch states fetched from a remote. | `refs/remotes/origin/main` |
| `refs/tags/` | Tags. | `refs/tags/v1.2.0` |
| `refs/notes/` | Git notes attaching additional information to Git objects. | `refs/notes/commits` |

The two most important namespaces in this lesson are `refs/heads/` and `refs/remotes/`.

### 1.1. `refs/heads/` Represents Branches

The local `main` branch is typically stored under the full name:

```text
refs/heads/main
```

The `feature/login` branch corresponds to:

```text
refs/heads/feature/login
```

When you commit on the currently checked-out branch, Git updates that branch ref to point to the new commit. Thus, a branch is a pointer that moves along commit history; it is not a copy of the entire project's contents.

Each repository has its own `refs/heads/` namespace. `refs/heads/main` on a developer's machine and `refs/heads/main` on the server are two refs residing in two different repositories. They may point to the same commit, but they do not synchronize automatically.

### 1.2. `refs/remotes/` Represents Remote-Tracking Refs

When fetching the `main` branch from a remote named `origin`, the default configuration normally stores the retrieved state at:

```text
refs/remotes/origin/main
```

The commonly used shorthand name is `origin/main`. This is a **remote-tracking branch/ref**: a local ref recording the state of the `main` branch that the local repository retrieved from the `origin` remote during the most recent fetch.

`origin/main` is not a branch located directly on the server. The branch on the server is typically `refs/heads/main`; `origin/main` is the local repository's record of that branch's state. It only changes when an operation like fetch updates it, or when you explicitly modify the corresponding ref.

For example, after fetching:

```text
Repository on server origin           Local repository
refs/heads/main          ----------> refs/remotes/origin/main
                                              |
                                              +-- shorthand name: origin/main

refs/heads/main (local branch) ---------------+
        shorthand name: main
```

`main` and `origin/main` are two separate refs. If someone else pushes new commits to `origin/main`, the local `main` branch does not move automatically. After fetching, `origin/main` may be ahead of `main`; you should inspect it and then merge or rebase to integrate the changes.

### 1.3. Full Refs and Shorthand Names

In most daily commands, Git allows using shorthand names:

| Shorthand Name | Typically Corresponding Full Ref |
|---|---|
| `main` | `refs/heads/main` |
| `feature/login` | `refs/heads/feature/login` |
| `origin/main` | `refs/remotes/origin/main` |
| `origin/feature/login` | `refs/remotes/origin/feature/login` |
| `v1.2.0` | `refs/tags/v1.2.0` |

When a shorthand name might be ambiguous, using the full ref specifies the exact object the command references. The following commands are helpful for inspecting refs:

```bash
# List local branches
git branch

# List remote-tracking branches
git branch -r

# List both local branches and remote-tracking branches
git branch -a

# List refs along with the object IDs they point to
git show-ref
```

## 2. What Is a Refspec?

A **refspec (reference specification)** is an expression specifying the source ref and destination ref in a data exchange operation. Basic structure:

```text
[+]<src>:<dst>
```

Where:

- `<src>` is the source ref Git reads from.
- `<dst>` is the destination ref Git updates.
- A leading `+` allows updating the destination even when the update is not a fast-forward, in contexts that support force updates.
- `:` separates source and destination. Depending on the operation, one side may be left empty or the destination part may be omitted.

The key point to remember is that **the same `<src>:<dst>` syntax reverses source and destination perspective depending on the operation**:

| Operation | Where is `<src>`? | Where is `<dst>`? |
|---|---|---|
| Fetch | Remote repository | Local repository |
| Push | Local repository | Remote repository |

Example:

```text
Fetch: +refs/heads/*:refs/remotes/origin/*
       remote source       local destination

Push:  refs/heads/feature/login:refs/heads/feature/login
       local source                         remote destination
```

Therefore, never read a refspec in isolation from the command being used. For fetch, the source is usually a branch on the server and the destination is a local remote-tracking ref. For push, the source is usually a local branch and the destination is a branch on the server.

## 3. Fetch Refspec: Mapping `refs/heads/*` to `refs/remotes/*`

When cloning a remote repository, Git usually sets up the fetch configuration for the `origin` remote like this:

```ini
[remote "origin"]
    url = https://example.com/team/project.git
    fetch = +refs/heads/*:refs/remotes/origin/*
```

The `fetch` line is the standard default refspec. It can be read as:

1. Retrieve refs matching `refs/heads/*` from the `origin` remote.
2. For each retrieved ref, substitute the `*` portion with the corresponding name at the destination `refs/remotes/origin/*` in the local repository.
3. Allow updating the remote-tracking ref even if the remote history was rewritten, thanks to the `+` prefix.

Mapping examples:

| Branch ref on remote | Local ref after fetch |
|---|---|
| `refs/heads/main` | `refs/remotes/origin/main` |
| `refs/heads/develop` | `refs/remotes/origin/develop` |
| `refs/heads/feature/login` | `refs/remotes/origin/feature/login` |
| `refs/heads/release/2.x` | `refs/remotes/origin/release/2.x` |

The `*` character is a wildcard: it matches part of a ref name, and the matched portion is substituted at the `*` position in the destination. One wildcard refspec maps a group of refs under the same rule, instead of having to write each branch individually.

### 3.1. Why Is the Destination `refs/remotes/origin/*`?

A local repository can contain branches developed by the user themselves as well as tracking refs reflecting remote states. Placing remote-tracking refs under `refs/remotes/origin/` helps Git keep the two groups distinct:

```text
refs/heads/
    main
    feature/login

refs/remotes/
    origin/
        main
        develop
        feature/payment
    upstream/
        main
        develop
```

In the example above:

- `refs/heads/main` is the local `main` branch.
- `refs/remotes/origin/main` is the state of the `main` branch fetched from remote `origin`.
- `refs/remotes/upstream/main` is the state of the `main` branch fetched from remote `upstream`.

Two remotes can have branches with the same name while storing them in separate namespaces. This allows you to compare a personal fork with the original repository without mixing up their remote-tracking refs.

### 3.2. Fetch Does Not Automatically Merge into Local Branches

Suppose before fetching, `main` and `origin/main` both point to commit `A`. Another teammate pushes commit `B` to the remote. After running:

```bash
git fetch origin
```

`origin/main` is updated to point to `B`, while `main` still points to `A`:

```text
Before fetch:

A  (main, origin/main)

After the remote receives commit B and we fetch:

A  (main) ---- B  (origin/main)
```

Fetch only downloads objects and updates destination refs according to the refspec. It does not automatically modify the checked-out branch, working tree, or staging area to integrate new commits. After checking status, you can explicitly merge or rebase:

```bash
git status -sb
git log --oneline --left-right main...origin/main

# Integrate by merging
git switch main
git merge origin/main

# Or, if project conventions require linear history
# git rebase origin/main
```

If the two branches have conflicting changes, Git may ask you to resolve conflicts during merge or rebase. The refspec only decides which refs are retrieved and updated; it does not decide how history is integrated into local branches.

### 3.3. Checking Fetch Refspec Configuration

To view the URLs and refspecs currently used for `origin`:

```bash
git remote -v
git config --get-all remote.origin.fetch
```

The second command may output:

```text
+refs/heads/*:refs/remotes/origin/*
```

The leading `+` shown is part of the refspec configuration. Use `--get-all` because a remote can have multiple `remote.<name>.fetch` lines, such as multiple positive mappings and exclusion patterns.

To see which branches the server is advertising:

```bash
git ls-remote --heads origin
```

This command queries the remote and displays refs along with the object IDs the server permits the connection to see. It does not mean local remote-tracking refs have been updated; to update local state, run fetch.

## 4. Reading Detailed Fetch Refspec Syntax

### 4.1. Mapping a Specific Branch

You can fetch a single branch and specify where to store it:

```bash
git fetch origin refs/heads/release/2.x:refs/remotes/origin/release/2.x
```

Git retrieves the `release/2.x` branch on the remote and updates the corresponding remote-tracking ref locally.

If the destination part is omitted:

```bash
git fetch origin refs/heads/release/2.x
```

Git retrieves the specified ref and records fetch details in `FETCH_HEAD`; this command does not specify a target remote-tracking ref in the refspec. `FETCH_HEAD` is temporary metadata for subsequent integration steps, not a persistent local branch name like `origin/release/2.x`.

### 4.2. The `+` Prefix and Non-Fast-Forward Updates

Normally, Git avoids non-fast-forward updates on certain refs because doing so can drop track of referenced history. For remote-tracking refs, the remote may have been force-pushed or a branch may have been intentionally rewritten. The `+` prefix allows fetch to update the destination ref in that situation:

```text
+refs/heads/*:refs/remotes/origin/*
^
Allows force-updating the destination ref when needed
```

This is why the default fetch refspec usually has a `+` prefix. It only controls updating local refs during fetch; it does **not** force-push changes to the server and does not rewrite the local `main` branch.

If a remote branch was rewritten, after fetching, inspect the history and coordinate with your team before integrating. Do not assume the old commit disappeared everywhere: it may still be retained by another branch, tag, reflog, or another teammate's clone.

### 4.3. Negative Refspecs to Exclude Refs

Fetch supports negative refspecs of the form:

```text
^<src>
```

A negative refspec excludes matching refs from the set of refs fetched by positive refspecs. It has no destination part. Configuration example:

```ini
[remote "origin"]
    fetch = +refs/heads/*:refs/remotes/origin/*
    fetch = ^refs/heads/archive/*
```

Meaning:

- The first line fetches branches under `refs/heads/` and maps them into `refs/remotes/origin/`.
- The second line excludes branches matching `refs/heads/archive/*` from that set.

A negative refspec must accompany at least one positive refspec that defines the initial set of refs. This exclusion syntax is used in fetch configuration; do not apply it as a normal push refspec syntax.

### 4.4. Fetching into a Custom Local Namespace

You are not required to store every remote branch under the default name. For example, to fetch release branches into the `refs/remotes/origin/releases/` namespace, you can run:

```bash
git fetch origin "+refs/heads/release/*:refs/remotes/origin/releases/*"
```

Then:

| Remote source | Local destination |
|---|---|
| `refs/heads/release/2.x` | `refs/remotes/origin/releases/2.x` |
| `refs/heads/release/3.x` | `refs/remotes/origin/releases/3.x` |

This is an additional mapping specified in the fetch command. If you want to use it regularly, you can configure an extra `remote.origin.fetch` line; inspect existing lines before modifying, as the configuration may contain multiple refspecs. When adding a line, existing positive refspecs remain active, so the same remote branch may be stored at multiple local destinations.

Example adding an extra mapping:

```bash
git config --add remote.origin.fetch "+refs/heads/release/*:refs/remotes/origin/releases/*"
git config --get-all remote.origin.fetch
```

Afterwards, `git fetch origin` will apply all fetch refspecs configured for that remote. Changing the local namespace does not rename the branch on the server.

## 5. Push Refspec: Mapping Local Branches to Remote

For push, the mapping direction is reversed: the source is local, and the destination is on the remote. The structure remains:

```text
[+]<src>:<dst>
```

For example, to push the local `feature/login` branch to a branch of the same name on remote `origin`:

```bash
git push origin refs/heads/feature/login:refs/heads/feature/login
```

This can be written more concisely:

```bash
git push origin feature/login
```

In the full form, the source is `refs/heads/feature/login` locally and the destination is `refs/heads/feature/login` on the remote. Push updates the branch on the server if access permissions and the remote's update rules allow it.

### 5.1. Pushing a Local Branch to a Different Name on the Remote

Refspecs allow source and destination names to differ:

```bash
git push origin refs/heads/feature/login:refs/heads/review/login
```

As a result, the local `feature/login` branch is used to update the `review/login` branch on the remote. After teammates fetch using the default configuration, they will see the remote-tracking ref `origin/review/login`.

This is useful when a team follows a server-side branch naming convention, or wants to push an experimental branch under a temporary name for review. It does not rename the local `feature/login` branch.

### 5.2. The `+` Prefix in Push

For push, the `+` prefix allows updating the destination ref in a non-fast-forward manner:

```bash
git push origin +refs/heads/feature/login:refs/heads/feature/login
```

This operation can alter history that others rely on. Use it only when you clearly understand the impact and it aligns with team policy. In situations requiring a force push, it is usually preferable to use:

```bash
git push --force-with-lease origin feature/login
```

`--force-with-lease` verifies that the remote ref is still in the state the local repository expects before allowing a forced update, reducing the risk of overwriting new commits someone else just pushed. It is still a history-rewriting operation and requires team coordination.

Note the distinction: the `+` prefix in a fetch refspec allows updating a local remote-tracking ref when the remote rewrites a branch; the `+` prefix in a push refspec allows overwriting a ref on the remote. The same symbol affects two different repositories.

### 5.3. Deleting a Remote Branch with a Refspec

In a push refspec, leaving the source empty while specifying a destination tells Git to delete the destination ref:

```bash
git push origin :refs/heads/feature/old-login
```

A more readable syntax:

```bash
git push origin --delete feature/old-login
```

This command deletes the branch on the remote. The corresponding remote-tracking ref locally may persist until you fetch with prune or run prune separately:

```bash
git fetch --prune origin
```

Deleting a remote branch does not automatically delete a local branch of the same name. Before deleting, make sure the branch is no longer used in open pull requests, pipelines, or ongoing work.

## 6. Remote-Tracking Refs, Upstream, and Local Branches

These three concepts often appear together, each with a distinct role:

- **Local branch:** a branch in `refs/heads/`, such as `main`.
- **Remote-tracking ref:** a ref in `refs/remotes/`, such as `origin/main`, recording the branch state fetched from a remote.
- **Upstream branch:** the branch that a local branch is configured to track. This configuration tells Git where to fetch/pull from and compare against by default for that branch.

For example, the local `main` branch tracks `origin/main`. Git stores the upstream relationship using configuration similar to:

```ini
[branch "main"]
    remote = origin
    merge = refs/heads/main
```

`branch.main.merge` specifies the branch name on the remote side; `remote.origin.fetch` maps that branch to the local remote-tracking ref `refs/remotes/origin/main`. Together, these settings tell Git that `main` tracks `origin/main`.

You can set the upstream with:

```bash
git branch --set-upstream-to=origin/main main
```

Or when pushing a new branch for the first time:

```bash
git push -u origin feature/login
```

The `-u` (or `--set-upstream`) option writes the tracking configuration for the current branch once the push succeeds.

Check upstream relationships:

```bash
git branch -vv
```

This command displays local branches, their current commits, and upstream details if configured. An upstream is not another copy of commits; it is a configuration relationship between a local branch and a remote branch, typically represented via a remote-tracking ref.

## 7. Commands for Inspecting and Diagnosing Ref Mappings

When a branch or remote-tracking ref does not appear as expected, inspect from configuration down to actual data.

### 7.1. Viewing Remotes and Refspecs

```bash
# View remote names and fetch/push URLs
git remote -v

# View all fetch refspecs for origin
git config --get-all remote.origin.fetch

# View current branch configurations
git config --get-regexp '^branch\.'
```

If `remote.origin.fetch` only contains one specific branch, such as:

```text
+refs/heads/main:refs/remotes/origin/main
```

then `git fetch origin` only updates that configured mapping. Other branches on the server may not appear in `git branch -r` because they are not fetched under the current refspec.

### 7.2. Viewing Local Refs and Remote-Tracking Refs

```bash
# Local branches only
git for-each-ref --format="%(refname) %(objectname:short)" refs/heads/

# Remote-tracking refs only
git for-each-ref --format="%(refname) %(objectname:short)" refs/remotes/

# View the object ID a ref name resolves to
git rev-parse refs/heads/main
git rev-parse refs/remotes/origin/main
```

If the last two `rev-parse` commands return different commit hashes, the two refs currently point to different commits. This is normal when the local branch has not yet integrated new changes from the remote or when local has its own commits.

### 7.3. Comparing Local Branches with Remote-Tracking Refs

```bash
# View commits present on only one side
git log --oneline --left-right main...origin/main

# View ahead/behind commit counts via upstream
git status -sb

# View local branches and upstreams
git branch -vv
```

Before comparing, run fetch to update remote-tracking ref information. Without fetching, `origin/main` only reflects the most recent fetch and may be stale compared to the server state.

### 7.4. Checking Branches Advertised by the Server

```bash
git ls-remote --heads origin
```

Compare the result with `git branch -r` and the configured refspecs:

- If the server has the branch but local lacks the remote-tracking ref, check whether the fetch refspec matches that branch.
- If the refspec matches but the local ref is still missing, run `git fetch origin` and inspect any authentication, permission, or connection errors.
- If the remote branch was deleted but the local remote-tracking ref remains, check pruning.

## 8. Pruning and Deleted Remote Refs

When a branch is deleted on the remote, the local ref `refs/remotes/origin/<branch>` may remain behind. Git does not automatically remove stale remote-tracking refs on every default fetch. Use:

```bash
git fetch --prune origin
```

to delete remote-tracking refs corresponding to remote refs that no longer exist, within the scope of the relevant fetch mappings. You can configure pruning for a remote:

```bash
git config remote.origin.prune true
```

Or configure it by default for all remotes:

```bash
git config fetch.prune true
```

Pruning affects local remote-tracking refs according to the mapping; it does not delete local branches in `refs/heads/`. If you have multiple refspecs or custom mappings, review the configuration and prune scope carefully before enabling it automatically.

A helpful preview command:

```bash
git fetch --prune --dry-run origin
```

Review the output before running the actual prune if the repository has complex refspec configurations.

## 9. Tags and Other Namespaces

Tags typically live in the `refs/tags/` namespace, separate from `refs/heads/` branches and `refs/remotes/` remote-tracking refs. The default branch fetch configuration:

```text
+refs/heads/*:refs/remotes/origin/*
```

does not mean all tags are mapped into `refs/remotes/origin/`. Git has a mechanism to automatically fetch tags pointing to downloaded objects in some cases; if you want to fetch all tags from the remote, you can use:

```bash
git fetch origin --tags
```

Or specify a tag refspec explicitly:

```bash
git fetch origin "+refs/tags/*:refs/tags/*"
```

When pushing a specific tag:

```bash
git push origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

Tags are a different ref type from branches. Do not use the branch refspec `refs/heads/*` to assume that tags are mapped by the exact same rule.

## 10. Common Misconceptions

### 10.1. Thinking `origin/main` Is a Branch on the Server

`origin/main` is normally a local ref in `refs/remotes/origin/main`. The branch on the remote has the full name `refs/heads/main`. Fetching is the operation that updates that local record from the remote.

### 10.2. Thinking Fetch Will Update the Local `main` Branch

Fetch updates destinations according to the fetch refspec, typically `refs/remotes/origin/*`. It does not automatically update `refs/heads/main`. To integrate changes, merge or rebase the remote-tracking ref into your local branch.

### 10.3. Thinking Every Remote Branch Appears After Fetch

`git fetch origin` applies the refspecs configured for `origin`. If the configuration only fetches `main`, other branches may not be mapped locally. Check with `git config --get-all remote.origin.fetch`.

### 10.4. Confusing Source and Destination Directions

In fetch, the source is on the remote and the destination is local. In push, the source is local and the destination is on the remote. Note the data flow direction before writing a custom refspec.

### 10.5. Thinking the `+` Prefix Always Has the Same Impact

In fetch, `+` permits non-fast-forward updates to a local remote-tracking ref. In push, `+` permits forced updates to a ref on the remote. Always identify the command being run and which repository is being updated before using it.

### 10.6. Deleting a Remote Branch but Still Seeing `origin/branch`

The local remote-tracking ref may be stale after a remote branch is deleted. Run `git fetch --prune origin` to clean up refs that no longer have a counterpart. A local branch with the same name remains until you delete it separately.

## 11. Practical Workflow: Tracking Branches from a Remote

Suppose your team has an `origin` remote with branches `main`, `develop`, and `feature/search`. You want to verify the mapping, update information, create a local branch tracking `develop`, and push a feature branch to the server.

### Step 1: Check Remote and Fetch Refspecs

```bash
git remote -v
git config --get-all remote.origin.fetch
```

Confirm the `origin` remote points to the right repository and that the fetch configuration maps the branch you want to track. With the default wildcard configuration, branches under `refs/heads/` are mapped to `refs/remotes/origin/`.

### Step 2: Fetch and Inspect Remote-Tracking Refs

```bash
git fetch --prune origin
git branch -r
```

You should see `origin/main`, `origin/develop`, and `origin/feature/search` if those branches are advertised by the remote and match the refspec.

### Step 3: Create a Local Branch Tracking `origin/develop`

```bash
git switch --track -c develop origin/develop
```

Git creates the local `develop` branch at `refs/heads/develop` and sets its upstream to `origin/develop`. Both refs remain independent, while Git knows the tracking relationship between them.

### Step 4: Create a Feature Branch and Commit

```bash
git switch -c feature/search develop
# edit source code
git add src/
git commit -m "feat: add search feature"
```

The `feature/search` branch is a local branch under `refs/heads/feature/search`.

### Step 5: Push and Set Upstream

```bash
git push -u origin feature/search
```

Git uses the local branch as the source and creates/updates the `refs/heads/feature/search` branch on the remote. Once the push succeeds, Git records the upstream relationship for the local branch. In subsequent work, `git status -sb` and `git branch -vv` help inspect that relationship.

### Step 6: Fetch New Changes and Integrate

When teammates update `develop`:

```bash
git fetch origin
git switch develop
git log --oneline --left-right develop...origin/develop
```

After reviewing the commits, choose merge or rebase according to your team's convention:

```bash
git merge origin/develop
```

If conflicts arise, resolve them file by file, verify the result, and finish the merge. Fetching updated the remote-tracking ref; merging is the step that integrates changes into the local branch.

## 12. Key Takeaways

- `refs/heads/` holds branches in the repository under consideration. `refs/heads/main` locally and `refs/heads/main` on the remote are two refs in two different repositories.
- `refs/remotes/<remote>/` holds local remote-tracking refs, such as `refs/remotes/origin/main`; the shorthand name is `origin/main`.
- A refspec has the general form `[+]<src>:<dst>`. For fetch, the source is remote and the destination is local; for push, the source is local and the destination is remote.
- The common default fetch refspec is `+refs/heads/*:refs/remotes/origin/*`, mapping remote branches into local remote-tracking refs.
- Fetch updates destination refs according to the mapping; merge or rebase integrates history into local branches.
- An upstream is a configured relationship between a local branch and a tracked remote branch; it works together with the remote's fetch refspec.
- `git config --get-all remote.origin.fetch`, `git branch -r`, `git branch -vv`, `git show-ref`, and `git ls-remote --heads origin` help diagnose mappings.
- `git fetch --prune origin` cleans up remote-tracking refs removed from the remote; it does not delete local branches.

When you need to write or modify a refspec yourself, clearly identify the source ref, destination ref, which repository holds each ref, and the direction of data flow. From there, reading `origin/main`, controlling which branches are fetched, pushing a branch under a different name, or handling stale refs becomes far more predictable.

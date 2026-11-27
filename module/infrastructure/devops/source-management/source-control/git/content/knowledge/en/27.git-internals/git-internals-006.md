# Refs, Symbolic Refs, packed-refs, and Reflog

Git uses **refs** (references) to assign memorable names to objects in a repository. Instead of having to remember a long object ID, you can use names like `main`, `feature/login`, `v2.1.0`, or `HEAD`. A ref usually points to a commit, though a tag ref can point to a tag object or another object type. Git uses refs to track the current branch, release versions, fetched remote state, and other historical milestones.

A ref can be stored as a standalone file (a loose ref) or bundled inside the `packed-refs` file. Some refs, such as `HEAD`, are **symbolic refs**: instead of holding an object ID directly, they point to another ref. Alongside current refs, Git maintains a **reflog** to record movements of a ref. The reflog often lets you recover commits after a reset, amend, rebase, or accidental branch deletion, provided the objects have not yet been pruned from the object database.

## 1. What is a ref and what does Git use it for?

A ref is a name that resolves to an object ID. For a local branch, the ref normally points to the latest commit on that branch. When you create a commit on that branch, Git updates the ref to point to the new commit.

Common ref namespaces:

| Namespace / name | Example | Purpose |
|---|---|---|
| `refs/heads/` | `refs/heads/main` | Local branches |
| `refs/remotes/` | `refs/remotes/origin/main` | Remote-tracking branches, recording the remote branch state as of the last fetch |
| `refs/tags/` | `refs/tags/v2.1.0` | Tags marking releases or historical milestones |
| `refs/stash` | `refs/stash` | Ref managing the latest stash and the reflog of the stash stack |
| `refs/notes/` | `refs/notes/review` | Git notes attaching extra metadata to objects |
| `refs/replace/` | `refs/replace/<oid>` | Mechanism for replacing objects when reading history |

The short branch name `main` is typically resolved by Git to `refs/heads/main`. The name `origin/main` is typically resolved to `refs/remotes/origin/main`. Using full ref names prevents ambiguity when multiple namespaces have similar names.

A ref does not contain the entire commit. It holds only the name and object ID; the object database stores the actual commit, tree, and blob contents. Consequently, moving a ref changes which commit a branch points to without copying any history.

## 2. Direct refs and symbolic refs

### Direct refs

A direct ref contains the object ID of the object it points to. For example, the branch ref `refs/heads/main` might contain a commit OID. When the branch advances, Git replaces the OID in the ref with the new commit OID.

The following commands let you inspect refs and their values:

```bash
# List refs along with their object IDs
git show-ref

# Inspect only the main branch ref
git show-ref --verify refs/heads/main

# Resolve a branch name to its object ID
git rev-parse refs/heads/main
```

`git show-ref` reads refs through Git's interface without requiring you to know whether a ref lives in an individual file or in `packed-refs`.

### Symbolic refs

A symbolic ref (symref) contains the name of another ref rather than an object ID. `HEAD` is the most important example. When on branch `main`, the logical content of `HEAD` is equivalent to:

```text
ref: refs/heads/main
```

This means `HEAD` points to branch `main`, and branch `main` is the direct ref pointing to the commit. When you switch to `feature/login`, Git updates `HEAD`'s symbolic target to `refs/heads/feature/login`.

Check where `HEAD` is pointing:

```bash
# Show HEAD's target ref if HEAD is a symbolic ref
git symbolic-ref HEAD

# Show the short name of the current branch
git symbolic-ref --short HEAD

# Resolve HEAD to its commit OID
git rev-parse HEAD
```

`git symbolic-ref` fails when `HEAD` is not a symbolic ref, such as in detached HEAD state. `git rev-parse HEAD` still resolves to the commit that `HEAD` points to.

### Detached HEAD

When checking out a commit or tag directly instead of a branch, `HEAD` contains the commit OID directly. This state is called detached HEAD:

```bash
git switch --detach v2.1.0
git status
git rev-parse HEAD
git symbolic-ref -q HEAD
```

In this state, you are not on a local branch. If you create a new commit, `HEAD` moves to the new commit, but no named branch automatically advances with it. Create a branch if you want to keep the work:

```bash
git switch -c experiment/from-v2.1.0
```

## 3. How do HEAD, branches, and remote-tracking refs relate?

When working on `main`, the typical relationship is:

```text
HEAD
 |
 | symbolic ref
 v
refs/heads/main
 |
 | direct ref
 v
commit C3
```

When running `git commit`, Git creates a new commit and updates `refs/heads/main`; `HEAD` still points to `refs/heads/main`. Thus, the branch advances while `HEAD` does not need to change its symbolic target.

A remote-tracking branch such as `origin/main` is a local ref under `refs/remotes/origin/main`. It is not a ref residing on the server and does not update instantaneously when teammates push. Running `fetch` retrieves updates from the remote and updates remote-tracking refs:

```bash
git fetch origin
git show-ref refs/remotes/origin/main
git rev-parse origin/main
```

When pushing, Git asks the remote to update a ref on the server side. A successful push does not send your local reflog to the remote; the reflog is local historical data belonging to each individual repository.

## 4. Loose refs: refs stored as individual files

In the traditional file-based ref backend, unpacked refs typically appear under `.git/refs/`. For example:

```text
.git/
├── HEAD
├── refs/
│   ├── heads/
│   │   ├── main
│   │   └── feature/
│   │       └── login
│   ├── remotes/
│   │   └── origin/
│   │       └── main
│   └── tags/
│       └── v2.1.0
└── packed-refs
```

A direct loose ref normally holds an OID on a single line. A symbolic ref holds a line of the form `ref: <ref-name>`. However, you should not edit ref files directly to change branches or tags. Manual edits bypass concurrency checks, reflog updates, and formatting rules enforced by Git.

Commands that create or move loose refs:

```bash
# Create a local branch from the current HEAD
git branch feature/login

# Switch to the new branch
git switch feature/login

# Show the target ref name of HEAD
git symbolic-ref --short HEAD
```

These high-level commands should be preferred because they update refs and working state following Git's supported workflows.

## 5. `packed-refs`: bundling many refs into one file

When a repository has many refs, Git can pack them into the `packed-refs` file instead of keeping every ref as a separate file under `.git/refs/`. This reduces the number of individual ref files and can improve ref lookup performance in large repositories.

You can instruct Git to pack refs:

```bash
git pack-refs --all
```

In the traditional file backend, `packed-refs` is a text file structured like this:

```text
# pack-refs with: peeled fully-peeled sorted
<object-id-1> refs/heads/main
<object-id-2> refs/remotes/origin/main
<tag-object-id> refs/tags/v2.1.0
^<peeled-object-id>
```

Regular lines contain an OID and a ref name. Lines starting with `^` store the peeled OID of an annotated tag—that is, the object the tag object points to, usually the tagged commit.

A loose ref with the same name takes precedence over the corresponding entry in `packed-refs`. When Git updates a packed ref, it may create a new loose ref to store the current value; Git manages merging and cleaning up stale records on future repacks.

To inspect refs, use `git show-ref`, `git for-each-ref`, or `git rev-parse`. Never edit `packed-refs` in a text editor and never delete it manually. Beyond the traditional file backend, Git can also use alternative ref storage backends; Git commands serve as the stable interface for manipulation.

## 6. Listing and querying refs

Useful commands for exploring refs:

```bash
# Display refs known to Git
git show-ref

# List local and remote-tracking branches
git branch -a

# List tags
git tag --list

# Iterate refs with name and object ID
git for-each-ref --format='%(objectname) %(refname)' refs/heads refs/remotes refs/tags

# Verify a specific ref exists
git show-ref --verify refs/heads/main
```

`git for-each-ref` lets you filter by namespace and format fields such as `%(refname)`, `%(objectname)`, `%(upstream)`, or `%(subject)`. It is the right choice for scripts that need to enumerate refs without reading internal storage directly.

To resolve a name to an object ID:

```bash
git rev-parse HEAD
git rev-parse main
git rev-parse refs/remotes/origin/main
```

When a script needs to verify that a ref exists and resolves to a commit, use the appropriate verification syntax, such as:

```bash
git rev-parse --verify 'refs/heads/main^{commit}'
```

The `^{commit}` suffix instructs Git to peel the object down to a commit. This is useful for tags that may point to a tag object before reaching the commit.

## 7. `git update-ref`: updating refs with checks

`git update-ref` is a low-level command to create, update, or delete refs. Higher-level commands like `git branch`, `git tag`, and `git reset` are normally better suited for daily work. `update-ref` is useful in scripts or when conditional ref updates are needed.

Create a new ref pointing to a known commit:

```bash
git update-ref refs/heads/review/candidate <commit-oid>
```

Update a ref only if its current value equals the expected OID:

```bash
git update-ref refs/heads/review/candidate <new-oid> <old-oid>
```

The `<old-oid>` parameter acts as a precondition check. If the current ref no longer points to that OID, Git refuses the update. This prevents overwriting another process's changes if the ref moved after you read it.

Delete a ref conditionally based on its current value:

```bash
git update-ref -d refs/heads/review/candidate <old-oid>
```

Use full ref names and expected OIDs when safe operations are required. Do not use `update-ref` to arbitrarily modify refs unless you understand which branches or tags depend on them.

## 8. What is the reflog?

The reflog (reference log) records updates to a ref's value in the local repository. For example, when `HEAD` switches from `main` to `feature/login`, or when a branch moves due to a commit, reset, amend, or rebase, Git records a corresponding reflog entry.

The reflog differs from commit history:

| Commit history (`git log`) | Reflog (`git reflog`) |
|---|---|
| Follows commit parent relationships | Records ref movements |
| Reflects commit history reachable from the selected ref | Reflects the local history of a ref over a retention window |
| Shareable via fetch/push as commits and refs | Not pushed or cloned as shared history |
| Does not necessarily show which commit a branch pointed to before a reset | Can show what commit `HEAD` or a branch previously pointed to |

The reflog typically records the old OID, new OID, updater identity, timestamp, and an action description message. It is a helpful recovery tool, not a permanent backup.

## 9. Viewing the reflog for HEAD and branches

View the reflog of `HEAD`:

```bash
git reflog
git reflog show HEAD
git reflog show --date=iso HEAD
```

View the reflog of a branch:

```bash
git reflog show main
git reflog show feature/login
```

You can use `git log -g` to walk the reflog in log format:

```bash
git log -g --oneline HEAD
```

Sample output:

```text
9ac31d2 HEAD@{0}: commit: Add login validation
6b2e811 HEAD@{1}: reset: moving to HEAD~1
9ac31d2 HEAD@{2}: commit: Add login validation
```

Each entry represents a past state of the ref. The syntax `HEAD@{1}` means the value of `HEAD` one reflog entry ago—not the first parent of the current commit. Indexes shift whenever new operations occur, so read the current output right before using an entry.

You can also reference states by time, such as `main@{yesterday}` or `HEAD@{2.hours.ago}`. Resolution depends on Git's revision syntax and whether the reflog data is still retained.

## 10. Recovering commits after reset, amend, or rebase

Suppose you accidentally reset a branch to an older commit:

```bash
git reset --hard HEAD~2
```

If the newer commits have not been pruned, the reflog can help locate the OID that `HEAD` previously pointed to:

```bash
git reflog --date=local
```

Once you identify the right commit, create a rescue branch to preserve it before performing any further operations:

```bash
git branch rescue/before-reset <recovered-commit-oid>
```

Inspect its contents:

```bash
git log --oneline --decorate rescue/before-reset -10
git show --stat rescue/before-reset
```

Creating a rescue branch keeps the commit referenced so you no longer depend on whether the reflog entry survives. After verifying, you can merge, cherry-pick, or reset your working branch according to plan. Avoid running `reset --hard` again before protecting the commits you need to keep.

### After amend or rebase

`git commit --amend` and `git rebase` create new commits with new OIDs. The old commits may no longer be referenced by the current branch, yet the reflog of `HEAD` or the branch may still record the previous position:

```bash
git reflog show --date=local HEAD
```

Locate the entry prior to the amend/rebase, verify the commit with `git show`, and create a rescue branch pointing to that OID. This lets you review the old state or recover dropped commits.

### After deleting a branch

If a local branch is accidentally deleted, Git typically deletes that branch's own reflog as well. However, `HEAD`'s reflog may still retain traces if you had checked out or committed while on that branch. Check all remaining reflogs:

```bash
git reflog --all --date=local
```

`git reflog --all` only lists existing reflogs; it does not restore a reflog deleted along with its branch. If the tip commit is not found there, try searching for unreachable objects with `git fsck` before they are pruned. Once you find the OID, recreate the branch:

```bash
git branch rescue/restored-feature <recovered-commit-oid>
```

## 11. Reflog time and scope limits

Reflogs are stored locally. When you clone a repository, you do not receive anyone else's reflog; when you push, you do not send your reflog to the server. If you need to preserve a commit long-term or share it with the team, create an appropriate branch or tag and push that ref.

Git has configuration settings controlling reflog expiration, including:

| Setting | Meaning |
|---|---|
| `gc.reflogExpire` | Default expiration period for reflog entries, typically 90 days |
| `gc.reflogExpireUnreachable` | Shorter expiration period for entries no longer reachable from the current tip, typically 30 days by default |
| `core.logAllRefUpdates` | Controls whether Git records reflogs for refs according to the configured scope |

Defaults can vary depending on repository type, Git version, and local configuration. Inspect current settings:

```bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
git config --show-origin --get core.logAllRefUpdates
```

An expired reflog entry does not necessarily mean the object is deleted at that exact moment. Garbage collection and pruning remove unreachable objects once expiration criteria are met. Still, never rely on the reflog as permanent storage.

Commands like `git reflog expire`, `git gc`, and `git prune` can reduce or eliminate recovery opportunities. Before cleaning up a repository, verify that no needed commits remain accessible only through the reflog.

## 12. Reflog and maintenance commands

The following commands are useful when inspecting and managing reflogs:

```bash
# View HEAD's reflog
git reflog show HEAD

# View reflogs for all refs that have one
git reflog show --all

# View the most recent entries with timestamps
git reflog --date=local -20

# Delete a specific reflog entry (destructive to recovery data)
git reflog delete 'refs/heads/old-feature@{2}'
```

`git reflog delete` and `git reflog expire` are maintenance commands that can remove traces needed for recovery. Use them only when you clearly understand the goal and retention policy. Never delete a reflog to fix a broken branch before inspecting the commits and creating a rescue ref.

## 13. Safe inspection and recovery workflow

When you suspect a commit was lost due to a reset, amend, rebase, or branch deletion:

1. Halt cleanup operations such as `git gc --prune=now`, `git prune`, or reflog expiration.
2. Run `git status` to assess current working tree and index changes.
3. Run `git reflog --all --date=local` to find when the ref moved.
4. Use `git show <oid>` or `git log <oid>` to verify the commit you want to keep.
5. Create a rescue branch with `git branch rescue/<name> <oid>`.
6. Only after the commit is anchored by a ref, choose the appropriate merge, cherry-pick, or recovery method.
7. If not found in the reflog, consider `git fsck --full --no-reflogs --unreachable` to locate remaining objects.

Example:

```bash
git status
git reflog --all --date=local
git show <recovered-commit-oid>
git branch rescue/lost-work <recovered-commit-oid>
git log --oneline --decorate rescue/lost-work -10
```

Do not check out or reset to a newly discovered OID before creating a rescue ref. Once a rescue branch exists, the commit stays reachable and is safer to inspect.

## 14. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| `HEAD` always directly contains a commit OID | When on a branch, `HEAD` is normally a symbolic ref pointing to `refs/heads/...`; only detached HEAD directly contains an OID. |
| `origin/main` is a ref on the server | It is a local remote-tracking ref updated when you fetch. |
| `packed-refs` stores commit objects | It stores a mapping between ref names and OIDs; actual objects live in the object database. |
| Every ref is always a file under `.git/refs` | Refs can be packed inside `packed-refs` or stored in a different ref backend. |
| The reflog is commit history like `git log` | The reflog records ref movements; `git log` follows commit parent relationships. |
| Reflogs are shared when pushing | Reflogs are local data and are not pushed like branches or tags. |
| Reflogs keep commits forever | Entries can expire and unreachable objects can be pruned. |
| `HEAD@{1}` is the parent of the current commit | It is the value of `HEAD` one reflog entry ago; parent commits are accessed via `HEAD^` or `HEAD~1`. |
| It is safe to edit `packed-refs` manually | Use Git commands such as `show-ref`, `update-ref`, and `pack-refs` to avoid corrupting refs or skipping checks. |

## 15. Self-check

1. **What is a ref?**
   - A name that resolves to an object ID, commonly used to reference commits or other objects in a repository.
2. **What is the difference between a direct ref and a symbolic ref?**
   - A direct ref holds an OID; a symbolic ref holds the name of another ref.
3. **When on branch `main`, what does `HEAD` normally point to?**
   - `refs/heads/main`.
4. **Does `packed-refs` store commit contents or ref names with OIDs?**
   - It stores a mapping of ref names to OIDs; object contents reside in the object database.
5. **How does the reflog differ from `git log`?**
   - The reflog records ref movements; `git log` displays commits along parent relationships.
6. **After an accidental reset, what is the first step to protect a commit found in the reflog?**
   - Create a rescue branch pointing to that commit's OID before performing any other recovery steps.
7. **Is the reflog sent to the remote?**
   - No. The reflog is local data belonging to the repository.

## Conclusion

Refs provide memorable names for objects; symbolic refs such as `HEAD` point to another ref, while direct refs contain an OID. In the traditional file backend, refs can exist as loose files or be bundled into `packed-refs`; use Git commands to query and update them rather than editing internal files. The reflog records ref movements and often helps recover commits after a reset, amend, rebase, or branch deletion. Because reflogs can expire and unreachable objects can be pruned, create a rescue branch or tag as soon as you identify a commit to keep.

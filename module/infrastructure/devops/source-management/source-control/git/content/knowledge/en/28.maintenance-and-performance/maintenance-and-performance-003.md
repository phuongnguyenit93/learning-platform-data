# Impact of prune, reflog expire, and concurrent operations

Git retains objects so you can view history, switch branches, and recover operations you have performed. Over time, a repository can accumulate objects no longer referenced by any branch or tag, old reflog entries, and packed data. Maintenance commands such as `git prune`, `git reflog expire`, and `git gc` help reclaim data that is no longer needed, but they can also eliminate the opportunity to recover commits or objects dropped from history.

Risk increases when multiple Git processes read and write to the repository concurrently. Git has locking mechanisms to protect certain update operations, but running aggressive cleanup while another process is creating objects or updating refs can cause errors or lose data that has not yet been referenced. You need to understand the relationship between reachability, reflogs, expiration periods, and locks before running manual maintenance.

## 1. Which objects are considered still needed?

Git stores commits, trees, blobs, and tags as objects in the object database. An object can be found starting from roots such as branches, tags, other refs, the index, and reflogs. Git follows links from those starting points to determine which objects remain reachable.

Example:

```text
refs/heads/main ------> commit C ----> tree ----> blob
refs/tags/v1.0 -------> tag object ---> commit A
reflog HEAD ----------> commit B
```

In this example, commits A, B, and C and the objects they reference can all be retained even if one commit is no longer a current branch tip. If commit B was dropped from a branch after a reset but remains in the reflog, Git can still keep the object to support recovery.

An **unreachable** object is an object that can no longer be found from the references and roots considered by the reachability check. Unreachable does not mean the object is deleted immediately. Git has a grace period to avoid deleting objects that were just created or recently unreferenced.

Inspect unreachable objects:

```bash
git fsck --full --unreachable
```

This command helps detect objects no longer reachable within the check scope. To also find objects not retained by reflogs, you can use:

```bash
git fsck --full --no-reflogs --unreachable
```

Do not treat `fsck` output as a list of objects guaranteed safe to delete. An object that is currently unreachable might still be needed for recovery, an in-progress operation, or a branch you have not fetched yet.

## 2. What does git prune do?

`git prune` removes **loose objects** that are no longer reachable and are older than the selected expiration cutoff. Loose objects are objects stored individually in `.git/objects`, outside packfiles.

Preview command without deleting:

```bash
git prune --dry-run --verbose
```

When run without `--dry-run`, Git can delete objects matching the prune criteria:

```bash
git prune --verbose
```

By default, prune keeps objects newer than the grace period (typically two weeks). You can specify an explicit expiration cutoff:

```bash
git prune --expire=2.weeks.ago --dry-run --verbose
```

To preview the effect of a more aggressive prune without deleting:

```bash
git prune --expire=now --dry-run --verbose
```

`--expire=now` makes all unreachable loose objects immediately eligible based on the timestamp cutoff. Do not omit `--dry-run` if you are only surveying.

### Prune does not mean cleaning every object in the repository

`git prune` focuses on loose objects. A repository may contain objects inside packfiles or cruft packs; packing, splitting, and removing data from packs is coordinated by `git repack` and `git gc`, with behavior depending on the Git version and configuration. Therefore, do not assume that running `git prune` will reclaim the full disk space of all unreachable objects.

## 3. What does git reflog expire do?

Reflogs record when a local ref changes. For example, the `HEAD` reflog can record branch checkouts, commits, resets, or rebases. Reflogs are local logs of a clone and are not pushed to remotes with branches.

View reflogs:

```bash
git reflog --date=local
git reflog show --all
```

If you reset by mistake, the reflog can help locate the commit a branch used to point to. However, reflogs have expiration policies. `git reflog expire` deletes old entries based on time cutoffs:

```bash
git reflog expire --dry-run --verbose --all
```

This is a preview mode. Once you understand the affected entries, you can run the actual expire command according to the chosen policy:

```bash
git reflog expire --all
```

Do not run this command routinely while investigating an incident or before backing up commits that might need recovery.

### Two commonly used expiration thresholds

Git has two common default settings:

| Setting | Common default | Meaning |
|---|---:|---|
| `gc.reflogExpire` | 90 days | Expire old reflog entries under the general policy |
| `gc.reflogExpireUnreachable` | 30 days | Expire entries earlier if they point to commits no longer reachable from the current ref tip |

Values can be overridden at the system, global, or repository level; per-ref pattern configurations can also apply separately. Check the effective configuration and its origin:

```bash
git config --show-origin --get-all gc.reflogExpire
git config --show-origin --get-all gc.reflogExpireUnreachable
```

The `--expire` and `--expire-unreachable` flags in `git reflog expire` let you specify the policy for that single run:

```bash
git reflog expire --expire=90.days.ago --expire-unreachable=30.days.ago --all --dry-run --verbose
```

`--expire` controls old entries in general; `--expire-unreachable` controls entries leading to commits no longer reachable from the current ref tip. These measure the retention age of reflog entries, not the age of objects in the object database.

## 4. How are reflog expire and prune related?

The two operations have distinct effects and typically follow one another:

1. A commit is dropped from a branch after a reset or rebase.
2. The reflog still records that the ref previously pointed to that commit, so the commit can remain reachable via the reflog.
3. `git reflog expire` removes expired reflog entries.
4. The commit and related objects can become unreachable if no other ref or index retains them.
5. `git prune` or `git gc` can delete unreachable objects once the corresponding grace period has passed.

Diagram:

```text
Commit dropped from branch
          |
          v
   Reflog still has entry?
       /       \
     Yes        No
      |          |
      v          v
 Object still   Check refs, index,
  retained      and other sources
      |
      v
 Reflog expire deletes entry
          |
          v
 Object may become unreachable
          |
          v
 Grace period elapsed?
          |
          v
   prune / gc may delete
```

This is a conceptual model. An object is only deleted if it is no longer retained by any other ref or reachability source, and it meets both the age criteria and the object type handled by the cleanup operation.

## 5. git gc combines maintenance tasks

`git gc` is a composite maintenance command. Depending on version and configuration, it can expire reflog entries according to policy, clean temporary files, pack loose objects, consolidate packs, update auxiliary data, and prune expired objects. Thus, a single GC run can both drop old reflog milestones and make unreferenced objects eligible for cleanup.

View options:

```bash
git gc -h
```

Run standard garbage collection:

```bash
git gc
```

Git can also automatically run `git gc --auto` after certain operations if the number of loose objects or packs reaches a threshold. Settings such as `gc.auto`, `gc.autoPackLimit`, and `gc.pruneExpire` affect when or how maintenance runs.

View configuration:

```bash
git config --show-origin --get-regexp '^gc\.'
```

By default, `git gc` uses a grace period when pruning (typically around two weeks). You can specify the prune cutoff for a run:

```bash
git gc --prune=2.weeks.ago
```

Avoid running:

```bash
git gc --prune=now
```

on a repository where another process is writing objects or updating refs. Having no grace period increases the risk that newly written objects not yet referenced will be pruned away.

## 6. Pruning remote-tracking refs vs. pruning objects

Command names are easy to confuse:

- `git prune`: cleans unreachable loose objects in the object database.
- `git remote prune origin`: deletes remote-tracking refs for `origin` that the remote no longer advertises.
- `git fetch --prune origin`: fetches and simultaneously cleans stale remote-tracking refs.

Examples:

```bash
git remote prune --dry-run origin
git fetch --prune origin
```

A remote-tracking ref such as `refs/remotes/origin/feature/old` can be deleted when the corresponding branch has been deleted on the server. This operation does not directly delete commit objects. However, if no other ref retains the commit and related reflogs expire, the objects can later become candidates for garbage collection.

To preview which refs would be pruned, use `--dry-run`. Do not confuse `git fetch --prune` with `git prune --expire=now`; one cleans remote reference names, while the other cleans objects.

## 7. How does Git handle concurrent operations?

Multiple Git commands can read a repository simultaneously. When updating critical metadata files, Git uses lock files and typically writes to a temporary file before atomically renaming it upon completion.

Examples:

- `git add` can create `index.lock` before updating the index.
- Ref updates can create corresponding `.lock` files inside `refs/` or the ref management area.
- Config updates can use `config.lock`.
- Packing and garbage collection operations have their own locking mechanisms to prevent multiple GC processes from overlapping.

If another process holds a lock, a second command may report errors such as `Unable to create ... .lock` or `cannot lock ref`. This usually indicates another operation is updating the same data, or a previous process stopped abnormally and left behind a lock file.

Do not delete `.lock` files immediately when seeing an error. First, check whether any Git process, IDE, GUI client, hook, or CI task is running. If the process is still active, wait for it to finish. Consider removing a leftover lock file only after confirming no process owns the lock and understanding which operation created the file.

## 8. Risks of running prune or GC concurrently with write processes

A dangerous scenario can occur:

1. Process A writes a new object into the object database.
2. Process A has not yet updated a ref so a commit or branch references that object.
3. Process B runs prune with an expiration cutoff of `now`.
4. The new object may appear unreachable and get deleted before Process A finishes updating the ref.

This is why the default grace period matters. Newly created objects are typically protected for a period so write operations have time to complete. When you use `--prune=now`, you remove that layer of protection.

Other concurrent operations also need consideration:

| Running process | Potential impact during concurrent maintenance |
|---|---|
| `git add` or `git commit` | Contention over index/ref updates; commands may wait or fail due to locks |
| `git fetch` or `git receive-pack` | Objects are downloaded/written before refs are updated; overly aggressive prune can endanger new objects |
| Another `git repack` or `git gc` | Packing, lock, or pack modification contention; let Git coordinate instead of running multiple manual cleanups |
| IDE auto-fetching, committing, or refreshing the repository | Can trigger background Git operations unseen in the terminal |
| Hooks or CI runners sharing the repository | May write objects/refs concurrently with manual maintenance |

Git has locks and safeguards to handle many common situations, but you should not rely on them to run immediate pruning while the repository is being written to. Schedule maintenance when no write processes are active, preserve the grace period, and avoid manipulating the `.git` directory directly.

## 9. Signs that another process is using the repository

Before running manual maintenance, check Git processes and applications using the repository:

```bash
git status
git count-objects -vH
```

On Windows PowerShell, you can check for Git processes:

```powershell
Get-Process git -ErrorAction SilentlyContinue
```

On Linux/macOS:

```bash
ps -ef | grep '[g]it'
```

These commands only aid observation and do not prove the repository is completely free of write processes. A GUI client or IDE may invoke Git briefly. If CI tasks, scheduled jobs, or IDE auto-fetch are active, pause or wait for them according to workflow before running manual GC.

If you encounter a lock error:

```text
fatal: Unable to create '.git/index.lock': File exists.
```

Check for processes that may be using the index. Do not run two staging/commit commands concurrently in the same worktree. If a lock remains after a process terminated abnormally, inspect the lock file's contents and timestamp before taking action.

## 10. Safe maintenance workflow

Before cleaning objects or reflogs:

1. **Confirm the right repository.** Check `git rev-parse --show-toplevel` and remotes.
2. **Check the working tree and index.** Run `git status`; commit or save changes you want to keep.
3. **Check refs.** Inspect branches, tags, and remote-tracking refs; fetch any branches you need to keep before cleaning.
4. **Check reflogs.** Use `git reflog --all` to find commits that might need recovery.
5. **Survey unreachable objects.** Run `git fsck --full --unreachable` and consider saving important commits to a rescue branch.
6. **Preview expire/prune scope.** Run `git reflog expire --dry-run --verbose --all` and `git prune --dry-run --verbose`.
7. **Ensure no write processes are active.** Check terminals, IDEs, GUI clients, hooks, and CI runners.
8. **Run maintenance with an appropriate grace period.** Prefer default `git gc`; change expire/prune cutoffs only with clear reason and backups.
9. **Verify after maintenance.** Run `git status`, `git fsck --full`, and inspect object statistics.

If you need to keep a commit currently retained only in the reflog, create a rescue ref before expiring:

```bash
git branch rescue/before-cleanup <COMMIT_ID>
```

Once the commit is referenced by a branch, it remains reachable through that ref. Make sure the rescue branch is stored in the right repository and has a clear name.

## 11. Example investigation before expiring reflogs

Suppose you just reset a branch and want to be sure you do not lose old commits:

```bash
git reflog --date=local -20
git fsck --full --no-reflogs --unreachable
```

Find the commit prior to the reset, then create a rescue branch:

```bash
git branch rescue/pre-reset <COMMIT_ID>
```

Verify the new branch:

```bash
git log --oneline --decorate -5 rescue/pre-reset
```

Only after confirming no commits remain that need recovery should you consider expire policies or GC. You do not need to run `git reflog expire` manually merely to save space; regular `git gc` and maintenance already handle most of the work under default policies.

## 12. Hands-on exercises

Perform these in a disposable test repository:

1. Create a few commits and note the latest commit OID.
2. Use `git reset --hard HEAD~1` to drop a commit from the branch tip, then locate the old commit in `git reflog`.
3. Run `git fsck --full --unreachable` and `git fsck --full --no-reflogs --unreachable` to observe the difference when reflogs are included.
4. Run `git reflog expire --dry-run --verbose --all` to see entries that could expire.
5. Create a rescue branch pointing to the old commit and confirm the commit remains reachable.
6. Run `git prune --dry-run --verbose --expire=now` to survey objects that could be pruned; do not omit `--dry-run` in the exercise without a backup.
7. Run `git count-objects -vH` before and after a standard `git gc` run to observe repository statistics.
8. Describe a scenario in which running `git gc --prune=now` concurrently with `git fetch` or `git commit` could cause risk.

You have completed the exercise when you can distinguish deleting reflog entries from deleting objects, distinguish `git prune` from `git remote prune`, explain the grace period, and know how to check processes/locks before maintenance.

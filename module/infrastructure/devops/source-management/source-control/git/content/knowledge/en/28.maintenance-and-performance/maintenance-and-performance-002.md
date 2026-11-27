# Garbage collection with `git gc` and retention periods for unreferenced objects

During development, Git creates many objects to store commits, trees, and blobs. When a branch is deleted, commits are rewritten by rebase or reset, or files are replaced across multiple commits, some objects may no longer be referenced by any branch or tag. Git does not delete them immediately because they may still be needed to recover an operation or because another process has just created them. Over time, objects that are no longer needed can be collected to reduce disk usage and improve repository performance.

`git gc` (garbage collection) performs maintenance tasks such as packing loose objects into packs, optimizing storage, updating certain references, and pruning objects that are no longer retained. When cleanup happens depends on reflogs, prune expiration periods, and repository configuration. Understanding these timeframes helps you know when a commit removed from a branch can still be recovered, as well as avoid deleting data too early.

In Git source code management services, repository maintenance is part of keeping history stable and fast to access. Treat `git gc` as an object database administration operation with data retention rules, not as an arbitrary junk-file deletion command.

## 1. What objects does Git store?

Git stores content and history as objects in the object database. The four basic object types are:

| Object type | Content |
| --- | --- |
| Blob | File content, without filename or path |
| Tree | Directory structure, filenames, and references to blobs or subtrees |
| Commit | Recorded snapshot, parent commits, author, committer, and message |
| Tag object | Metadata of an annotated tag, potentially including tagger, message, and signature |

A commit points to its tree and can point to one or more parent commits. Trees point to blobs and subtrees. Refs such as branches, tags, and `HEAD` help Git locate the necessary commits. From those commits, Git follows parent and tree relationships to determine which objects are still in use.

Simple example:

```text
refs/heads/main
       |
       v
    Commit C3
       |
       v
      Tree
      /  \
   Blob  Tree
           |
          Blob
```

When a branch is deleted, the tip commit may no longer be referenced by that ref. However, the commit may still be kept by another branch, a tag, a reflog, or another ref. An object only becomes a candidate for collection when no reference path considered a root by Git retains it.

## 2. Reachable, unreachable, and dangling objects

To understand garbage collection, distinguish three concepts:

- **Reachable object:** an object reachable from a root Git is considering, such as a ref, the index, or a reflog. This object is still in use and is not a normal deletion candidate.
- **Unreachable object:** an object no longer reachable from the roots being considered. Examples include old commits after resetting a branch or commits on a deleted branch.
- **Dangling object:** an object that is unreachable and not referenced by other objects in a way that forms a chain still in use. A dangling commit is typically the tip of a history segment no longer attached to any ref.

A commit can be unreachable from a branch yet still be found via a reflog. Therefore, "no longer visible in `git log --all`" does not mean the object has been deleted. `git log --all` primarily traverses from existing refs; the reflog is a separate source of history.

Example after a reset:

```text
Before reset:

A --- B --- C  main
              ^ HEAD

After `git reset --hard B`:

A --- B  main
     \
      C  (no longer pointed to by branch main)
```

Commit `C` may still remain in the reflog of `main` or `HEAD`. If the reflog still retains that entry, you can usually create a new branch pointing to `C`. Only after retention mechanisms expire and the object passes the prune expiration period can Git collect that object.

## 3. What tasks does `git gc` perform?

Basic command:

```bash
git gc
```

Git performs maintenance tasks appropriate for the repository and Git version in use. Common tasks include:

- **Repack objects:** combine multiple loose objects or small packs into larger packs, reducing overhead and improving access efficiency.
- **Prune unretained objects:** remove unreachable objects that have passed the safety expiration period.
- **Expire reflogs:** remove reflog entries that have exceeded configured expiration periods.
- **Pack refs:** consolidate eligible refs into the packed-refs file.
- **Clean auxiliary data:** perform certain maintenance steps such as cleaning old rerere or worktree data depending on configuration and version.

Do not assume every Git version executes the exact same sequence of internal commands. The goal of `git gc` is to maintain the object database and related data according to the repository's policies.

### Loose objects and packfiles

When Git creates objects, they may initially be stored as individual files in `.git/objects`. As the number of loose objects grows, Git can consolidate them into packfiles in `.git/objects/pack`.

Packfiles store many objects together and can use delta compression to store differences between similar objects. This generally saves disk space, especially for closely related file versions.

Inspect object counts and sizes:

```bash
git count-objects -vH
```

Common fields:

| Field | Meaning |
| --- | --- |
| `count` | Number of loose objects |
| `size` | Size of loose objects, in KiB |
| `in-pack` | Number of objects in packfiles |
| `packs` | Number of packfiles |
| `size-pack` | Total size of packfiles, in KiB |
| `prune-packable` | Loose objects that already have corresponding copies in a pack and can be pruned |
| `garbage` | Number of invalid or unrecognized files in the object database |

After running GC, the number of loose objects or packfiles may decrease, while the total number of retained objects remains similar. GC does not necessarily shrink a repository significantly if most objects are still referenced.

## 4. Reflogs preserve history that left a branch

The reflog records when a ref changes position. For example, on a new commit, checkout, reset, rebase, or branch update, Git can record the old and new positions in the reflog.

View the reflog of `HEAD`:

```bash
git reflog
```

View the reflog of a branch:

```bash
git reflog show main
```

View entries for all refs:

```bash
git reflog show --all
```

Reflogs are useful when you need to recover a commit after an operation such as `reset --hard`, rebase, or branch deletion. For example, if you accidentally reset, you can find the pre-reset commit in the reflog and create a rescue branch:

```bash
git reflog show --date=local main
git branch rescue/before-reset <commit-id>
```

The rescue branch creates a new ref to retain the commit and all history reachable from it. Inspect the commit with `git show <commit-id>` before creating the branch if you are unsure whether it is the exact point to restore.

### Reflogs are local only

Reflogs are stored in the local repository and are not pushed to remotes like commits or branches. Another teammate may not have the same reflog. When you need to protect an important commit, create an explicit branch or tag and push it according to team workflow instead of relying on the reflog as a shared backup.

## 5. Reflog retention periods

Git has two main configuration settings controlling how long reflog entries are kept:

| Configuration | Common default | Meaning |
| --- | --- | --- |
| `gc.reflogExpire` | `90 days` | Retention period for general reflog entries |
| `gc.reflogExpireUnreachable` | `30 days` | Retention period for reflog entries leading to commits no longer reachable from the ref's current tip |

The values above are common Git defaults and may be overridden by system, global, local, or per-ref configuration. Reflog entries pointing to still-reachable history can be kept longer than entries leading to commits that have left the current tip.

Check configuration:

```bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
```

If the command returns no output, Git may be using the default value. You can configure it per repository:

```bash
git config --local gc.reflogExpire 90.days.ago
git config --local gc.reflogExpireUnreachable 30.days.ago
```

Or set a user-level policy:

```bash
git config --global gc.reflogExpire 90.days.ago
git config --global gc.reflogExpireUnreachable 30.days.ago
```

Git also supports per-ref configuration using `gc.<pattern>.reflogExpire` and `gc.<pattern>.reflogExpireUnreachable`. This is useful if a team wants to keep reflogs for certain refs longer. Check the Git documentation for your installed version to choose the exact pattern.

### Considerations when adjusting retention periods

Increasing reflog retention gives more time to recover old commits, but also keeps more objects and can increase repository disk usage. Decreasing retention cleans up faster but shortens the recovery window. Do not shorten retention merely to save disk space without an alternative backup and recovery policy in place.

## 6. Prune expiration period for unreferenced objects

`gc.pruneExpire` controls when unreachable objects become eligible to be pruned. The default is typically `2 weeks ago`. This waiting period acts as a safety buffer to avoid deleting objects that were just created but not yet referenced because another Git process is still performing an operation.

Check configuration:

```bash
git config --show-origin --get gc.pruneExpire
```

You can set it per repository:

```bash
git config --local gc.pruneExpire 2.weeks.ago
```

Or keep unreachable objects longer:

```bash
git config --local gc.pruneExpire 30.days.ago
```

Prune expiration and reflog expiration are two separate mechanisms:

- Reflog retains old ref positions so you can locate commits again.
- Prune expiry specifies how much longer unreachable objects are kept before becoming eligible for deletion.

For example, a commit recently dropped from a branch may still be retained by the reflog. Once the reflog entry expires, the commit becomes a collection candidate; if the object is still within the prune period, Git continues keeping it. When no retaining root remains and the prune period has elapsed, the object can be removed during an appropriate GC run.

Do not think of these two milestones as a single timer starting when a branch is deleted. Reflogs and objects have separate timestamps, reachability states, and retention rules; actual outcomes also depend on packfiles, cruft packs, and Git version.

## 7. Cruft packs and unreachable objects in modern Git

In newer Git versions, unreachable objects can be consolidated into a **cruft pack** instead of remaining solely as loose objects or being removed immediately. A cruft pack is a packfile containing unreachable objects, accompanied by metadata recording when each object was placed in the pack so Git can apply prune policies later.

This helps Git manage large numbers of unreachable objects more efficiently while still retaining them within the safety period. As a result, you will not always see unreachable objects as individual files in `.git/objects`.

Related settings:

```bash
git config --show-origin --get gc.cruftPacks
git config --show-origin --get gc.maxCruftSize
```

`gc.cruftPacks` controls the use of cruft packs in supported versions. `gc.maxCruftSize` can limit cruft pack size. Available settings and defaults depend on the Git version; do not change them unless you understand how the repository stores packs.

Cruft packs are not long-term backups. Objects can still be removed once the prune period expires and GC processes them. If a commit needs to be kept, create a branch or tag referencing it.

## 8. Standard workflow for running `git gc`

Before running manual GC, check the repository:

```bash
git status -sb
git count-objects -vH
git reflog --all --date=relative
```

If a rebase, cherry-pick, merge, or another Git process is currently running, wait for it to finish. Do not run aggressive cleanup commands while another process is writing to the object database.

Run standard GC:

```bash
git gc
```

Then verify:

```bash
git count-objects -vH
git status -sb
git fsck --full
```

`git fsck --full` checks the integrity of the object database. It may report unreachable or dangling objects if the repository still has unreferenced objects; these messages do not necessarily indicate data corruption. Read the message types and evaluate whether any objects need recovery.

### Automatic execution

Many Git commands can trigger `git gc --auto` when the number of loose objects or packfiles exceeds configured thresholds. This mechanism keeps the repository maintained incrementally without requiring users to run GC manually after every commit.

Check the thresholds:

```bash
git config --show-origin --get gc.auto
git config --show-origin --get gc.autoPackLimit
```

In many Git versions, `gc.auto` triggers by default when loose objects exceed roughly 6,700; `gc.autoPackLimit` triggers by default when packfiles exceed roughly 50. These are common default thresholds and can vary by version or configuration. Setting `gc.auto` to `0` disables automatic GC triggering from the loose object threshold; this does not disable all other maintenance activities.

## 9. Prune and aggressive options

### Specifying the prune cutoff

```bash
git gc --prune=2.weeks.ago
```

This command prunes only objects eligible according to the specified timestamp. It is an explicit way to apply the common default grace period.

You can preserve unreachable objects during this GC run:

```bash
git gc --prune=never
```

The `never` option is useful when you need to repack without pruning objects yet. Check the Git version and command documentation if an older environment does not support this syntax.

### Why be careful with `--prune=now`?

```bash
git gc --prune=now
```

`now` bypasses the normal safety waiting period. If another process is writing objects and has not yet created a ref pointing to them, GC could delete newly created objects and break the ongoing operation. Only use it when you have ensured no other Git process is accessing the repository and have a clear reason to clean up immediately. In routine maintenance, keeping the default grace period is safer.

### `git gc --aggressive`

```bash
git gc --aggressive
```

This option requests a more intensive repack to search for better delta compression. It can consume significant time and CPU, and does not guarantee the repository will always become substantially smaller. Do not run it on a routine schedule or treat it as a universal fix for every performance issue. Measure disk usage, access times, and pack counts first; test only on a copy or during a maintenance window when evidence shows deep optimization is needed.

## 10. Finding unreferenced objects before GC

If you have recently deleted a branch, reset by mistake, or mis-rebased, locate and protect the commits before running aggressive GC.

### Step 1: Check the reflog

```bash
git reflog --all --date=iso
```

Find the commit ID prior to the mistaken operation. Inspect the commit:

```bash
git show --stat <commit-id>
```

If it is indeed the work you want to keep, create a rescue branch:

```bash
git branch rescue/recovered-work <commit-id>
```

### Step 2: Find unreachable objects no longer in the reflog

If the reflog does not help, you can inspect the object database:

```bash
git fsck --full --no-reflogs --unreachable
```

`--no-reflogs` instructs `fsck` not to use reflogs as roots when computing reachability. The command can list commits, trees, or blobs unreachable from remaining refs. The output may be large; focus on objects of type `commit` first if you are looking for lost branch history.

Inspect candidate commits:

```bash
git show --stat <commit-id>
git log --oneline --decorate <commit-id> -10
```

If it is the commit you need to keep, create a ref:

```bash
git branch rescue/from-unreachable <commit-id>
```

Once the branch is created, the commit and objects reachable from it are retained through the new ref.

### Step 3: View dangling objects

```bash
git fsck --full --dangling
```

This command focuses on reporting dangling objects. A dangling commit can be the tip of a commit chain dropped from a branch. Use `git show` to inspect its contents before deciding to keep or discard it.

Do not mechanically create branches for every listed object. Trees and blobs may simply be parts of an old snapshot; locate the appropriate root commit and inspect its contents.

## 11. When is an object actually deleted?

Consider a commit `C` that was just removed from a branch:

1. **Branch/ref moves or is deleted:** `C` may no longer be reachable from that ref.
2. **Reflog still records the old position:** `C` can still be found and retained under the reflog policy.
3. **Reflog entry expires:** if no other ref or root holds `C`, the object becomes unreachable from GC's perspective.
4. **Prune period expires:** the object becomes eligible for removal when GC runs pruning; if stored in a cruft pack, Git uses the corresponding expiration metadata.
5. **GC completes:** the object may no longer exist in the local object database and cannot be recovered via reflog or `fsck` in that repository.

```text
Commit C referenced by branch
          |
          v
Branch is reset/deleted
          |
          v
Reflog still retains old position
          |
          v
Reflog entry expires
          |
          v
Object unreachable, still in prune grace period
          |
          v
GC prunes after expiration
          |
          v
Object removed from local object database
```

This is a conceptual model. An object may still be retained by another branch, tag, hidden ref, index, alternate object database, or another copy of the repository; therefore, you cannot conclude an object will be deleted solely because the original branch disappeared.

## 12. Recovering commits before objects are pruned

Example of an accidental branch reset:

```bash
git reset --hard HEAD~2
```

If you need to find the old tip:

```bash
git reflog --date=local
```

Suppose the reflog shows `HEAD@{1}` was the position before the reset. Create a rescue branch:

```bash
git branch rescue/before-reset HEAD@{1}
```

Then confirm:

```bash
git log --oneline --decorate rescue/before-reset -10
git show --stat rescue/before-reset
```

If the commit is no longer in the reflog but the object still exists:

```bash
git fsck --full --no-reflogs --unreachable
```

Find the matching commit and create a branch by its hash. Work on a copy or create the rescue ref before running further GC to avoid losing the recovery window.

If the object has already been pruned from the local repository, `reflog` and `fsck` cannot reconstruct deleted content. In that case, look in teammates' clones, remotes that still hold the branch/tag, backups, or mirror copies. Another clone's reflog may still hold commits that the current clone has lost.

## 13. Caution with manual reflog expire and prune

You can expire reflogs manually:

```bash
git reflog expire --expire=90.days.ago --expire-unreachable=30.days.ago --all
```

This command removes reflog entries older than the specified thresholds. Once a reflog entry is deleted, the ability to recover a commit kept only by that reflog is also lost. If GC subsequently prunes the object, the commit may disappear from the local repository.

You can combine expire and GC:

```bash
git reflog expire --expire=90.days.ago --expire-unreachable=30.days.ago --all
git gc --prune=2.weeks.ago
```

This maintenance operation affects recoverability. Before running it, inspect the reflog and verify that no important commits are kept only there. Do not use expire commands with shortened periods while investigating an incident or before confirming branches are backed up.

`git prune` is a lower-level command and usually does not need to be run separately in standard workflows. Prefer `git gc` because GC coordinates repacking, reflog expiration, and pruning according to appropriate policies.

## 14. Commonly used GC settings

| Setting | Role | Common default |
| --- | --- | --- |
| `gc.auto` | Loose object threshold triggering automatic GC | `6700` |
| `gc.autoPackLimit` | Packfile threshold triggering automatic repack | `50` |
| `gc.pruneExpire` | Retention period for unreachable objects before pruning | `2 weeks ago` |
| `gc.reflogExpire` | Retention period for general reflog entries | `90 days` |
| `gc.reflogExpireUnreachable` | Retention period for unreachable reflog entries | `30 days` |
| `gc.cruftPacks` | Enables cruft packs to store unreachable objects | Depends on version/configuration |

View current settings and their origin:

```bash
git config --show-origin --get-regexp '^gc\.'
```

Set configuration per repository:

```bash
git config --local gc.pruneExpire 30.days.ago
git config --local gc.reflogExpire 180.days.ago
git config --local gc.reflogExpireUnreachable 60.days.ago
```

This example extends the recovery window. In return, the repository may retain more objects and reflog data. Choose timeframes according to audit requirements, backup capabilities, storage capacity, and internal policies.

## 15. Safe maintenance workflow

A repository maintenance workflow can include:

### Before GC

1. Check `git status -sb` and ensure no Git operation is in progress.
2. Check important branches, tags, and remote-tracking refs.
3. Inspect the reflog if a reset, rebase, or branch deletion happened recently.
4. Create rescue branches/tags for commits that need to be kept.
5. Record storage metrics with `git count-objects -vH`.
6. Confirm no other Git process is writing to the repository, especially before aggressive pruning.

### During GC

Run the command matching your goal:

```bash
git gc
```

Specify a non-default prune cutoff only when backed by a clear policy. Avoid `--prune=now` in environments with concurrent Git processes. Do not run `--aggressive` without metrics showing deep optimization is needed.

### After GC

```bash
git count-objects -vH
git fsck --full
git status -sb
```

Compare object counts and sizes before and after. If `fsck` reports missing or corrupt objects, halt further write operations and inspect backups, packfiles, filesystem health, and recently run processes. Unreachable/dangling warnings may simply be old uncollected data and do not mean the repository is corrupted.

## 16. Common issues and scenarios

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Repository does not shrink after GC | Most objects are still reachable or data is already well compressed | Check `git count-objects -vH`, identify packs and large objects before optimizing |
| Commit no longer appears in `git log --all` | Branch/ref was deleted or moved | Check `git reflog --all` before concluding the commit is lost |
| `git fsck` reports unreachable/dangling | Objects are no longer retained by current refs | Inspect commits; create a rescue branch if needed |
| Cannot find commit in reflog | Reflog expired or commit originated in another clone | Try `git fsck`, search other clones/remotes/backups |
| Commit unrecoverable after GC | Object was pruned and no copies remain | Search backups or other clones; cannot recover from local reflog alone |
| GC takes a long time | Repository has many objects, large packs, or is repacking | Allow the operation to finish, check disk usage, and consider scheduled maintenance |
| GC removes newly created objects | Pruned too early while another process wrote to the repository | Avoid `--prune=now`, keep the grace period, and avoid concurrent runs |
| Reflog is too large or retains history too long | Expiration period is set too long | Assess recovery requirements before shortening expiration periods |

## 17. Practice

Practice on a test repository to observe object lifecycle:

1. Create a `feature/gc-lab` branch and make several commits.
2. Record the tip commit ID using `git log --oneline`.
3. Delete the test branch or reset to an earlier commit.
4. Use `git reflog --all` to find the commit that left the branch.
5. Create a `rescue/gc-lab` branch pointing to the commit to preserve.
6. Run `git count-objects -vH` to record object counts and sizes.
7. Run `git gc`, then re-check with `git count-objects -vH` and `git fsck --full`.
8. In another test repository, create an unreachable commit and use `git fsck --full --no-reflogs --unreachable` to observe the object.
9. Inspect `gc.reflogExpire`, `gc.reflogExpireUnreachable`, and `gc.pruneExpire`.
10. Explain why `git gc --prune=now` should not be used while other Git processes are running.

Do not test aggressive expire or prune commands on repositories containing real work. If you want to observe objects being collected, use a separate repository that can be deleted and recreated.

## 18. Self-check questions

1. What basic object types does the Git object database store?
2. How do reachable, unreachable, and dangling objects differ?
3. What maintenance tasks does `git gc` typically perform?
4. Why can a commit that left a branch still be recovered via the reflog?
5. How do `gc.reflogExpire` and `gc.reflogExpireUnreachable` differ?
6. What timeframe does `gc.pruneExpire` control?
7. Why are reflog expiration and prune expiration two separate mechanisms?
8. How do cruft packs help manage unreachable objects?
9. What risk does `git gc --prune=now` carry when a repository is being written to concurrently?
10. If a commit has been pruned locally, where can you look for recovery copies?

## Conclusion

`git gc` maintains the object database by repacking, expiring reflogs, and pruning objects no longer retained under policy. Reflogs typically keep old ref history for around 90 days, entries leading to unreachable commits typically have a shorter retention of around 30 days, and unreachable objects have a default prune grace period of around two weeks; these thresholds are configurable and version-dependent. When recovery is needed, check the reflog and `git fsck`, and create a rescue branch before GC removes objects. Keep the default grace period, avoid pruning immediately when concurrent processes exist, and only shorten retention periods once appropriate backups and recovery policies are in place.

# Verifiable backups and distinguishing mirrors from historical backups

A Git repository stores history using objects and refs, yet a repository copy is not automatically a backup that can recover from an incident. If a copy is continuously synchronized to the current state, deleting a branch or rewriting history at the source can propagate to the copy. A true backup must retain historical snapshots at different points in time, have its integrity verified, and be restorable in an independent environment.

This lesson belongs to the **Maintenance and Performance** chapter of the SOURCE_CONTROL_GIT module. The module covers the working tree, staging area, commits, history, branches, merges, rebases, remotes, and tags; verifiable backups help protect collaborative history and ensure recoverability when a repository encounters an incident.

## 1. Mirrors and historical backups solve two different needs

A **mirror** is a replica reflecting the current refs and objects of a source repository. It is useful when you need a replica close to the current state for server migration, access failover, or a synchronized copy.

A **historical backup** consists of point-in-time snapshots retained under a retention policy and not immediately overwritten when the source changes. It enables recovering branches, tags, or commits that were deleted or rewritten.

| Characteristic | Mirror | Point-in-time historical backup |
| --- | --- | --- |
| Goal | Reflect current refs of the source | Preserve repository milestones across multiple points in time |
| Updates | Synced on schedule or on demand | Creates new snapshots while retaining older ones per retention |
| When source deletes a branch | Mirror may delete the corresponding ref on prune | Older snapshots still preserve the ref and objects if stored separately |
| When source force-pushes | Mirror may move the ref to the new history | Prior snapshots still preserve the old commits |
| Recovering history lost at source | Old commits may no longer exist | Can select a pre-incident snapshot |
| Best suited for | Replica, migration, standby | Disaster recovery, auditing, history recovery |

A mirror is very useful, but it should not be your sole backup. If a mirror is synced with pruning or reflects force-updated refs, it can absorb the very destructive change you want to recover from.

## 2. Creating a mirror with git clone --mirror

To create a mirror of a remote repository:

~~~bash
git clone --mirror https://example.com/team/app.git /backup/app.git
~~~

`--mirror` creates a bare repository and configures fetch to map all refs from the source into the destination repository. A mirror has no regular working tree. It is suitable for holding a replica of refs/objects for synchronization and migration.

Inspect the mirror repository:

~~~bash
git -C /backup/app.git rev-parse --is-bare-repository
git -C /backup/app.git show-ref
git -C /backup/app.git remote -v
~~~

`rev-parse` typically returns `true` because a mirror is a bare repository. `show-ref` lists existing refs, and `remote -v` displays the mirror source.

### Updating a mirror

You can update the mirror from its source using:

~~~bash
git -C /backup/app.git remote update --prune
~~~

`remote update` fetches configured remotes; `--prune` removes refs deleted at the source according to the corresponding refspec. In a mirror clone, the refspec is configured to broadly map refs.

This behavior fits when your goal is a replica reflecting current state. However, if a branch is deleted or force-pushed at the source, the mirror may also remove or move that ref. Once old commits are no longer referenced, Git may clean up unreachable objects during maintenance/GC cycles.

### Caution with git push --mirror

`git push --mirror` synchronizes all refs from the local repository to the destination remote. Refs absent at the source can be deleted at the destination; existing refs can be force-updated to match the source.

~~~bash
git push --mirror backup
~~~

Only use this command when the destination remote is dedicated as a mirror and you intentionally want to synchronize the entire refs namespace. Never run it against a primary working remote or a repository with separate refs you want to keep. Before running it, inspect `git remote -v`, `git show-ref`, and explicitly verify the destination remote.

## 3. Why is a mirror not an immutable historical backup?

Suppose the source repository has branch `main` pointing to commit A. The mirror also has `main` pointing to A.

Later, someone force-pushes the source so `main` points to commit B. When the mirror updates, ref `main` moves from A to B as well. If no other ref holds A, commit A can become unreachable in the mirror. After time passes and garbage collection runs, object A may be reclaimed.

Similarly, when a branch is deleted at the source and the mirror runs with prune, that branch ref is deleted from the mirror. The mirror accurately reflects current state, but does not preserve old history on its own.

A mirror without pruning may retain some refs that disappeared at the source, but it does not fully address force-pushes replacing existing refs. Do not rely on stale refs or dangling objects as a verifiable backup policy.

To preserve history, create distinctly named and timestamped snapshots, or use a backup system with versioning/immutability. Do not overwrite an older snapshot when creating a new one.

## 4. Creating historical snapshots with Git bundles

A Git bundle packages objects and refs into a single file that can be archived or transferred to another machine. Bundles are very useful for point-in-time backups, offline archival, and moving history across systems.

Create a complete bundle from existing refs:

~~~bash
git bundle create /backup/app-2026-11-17.bundle --all
~~~

`--all` includes all refs in the bundle; Git packs the objects needed to restore those refs. Each backup should use a distinct filename with a timestamp or snapshot ID instead of overwriting old files.

Inspect refs inside a bundle:

~~~bash
git bundle list-heads /backup/app-2026-11-17.bundle
~~~

Verify the bundle:

~~~bash
git bundle verify /backup/app-2026-11-17.bundle
~~~

`verify` checks bundle structure and required prerequisites. A standalone bundle created from all refs requires no prerequisite commits from another repository. If creating incremental bundles, prerequisites must be available during restoration.

### Restoring from a bundle into a new repository

You can clone directly from a bundle:

~~~bash
git clone /backup/app-2026-11-17.bundle /restore/app
~~~

Then verify refs and history:

~~~bash
git -C /restore/app show-ref
git -C /restore/app log --oneline --decorate --all -20
git -C /restore/app fsck --full
~~~

Restoring into a new directory allows independent verification without affecting the active repository. Only after verifying required branches, tags, and commits should you move the restored repository into production use.

### What does a bundle include and exclude?

| Component | Included in bundle? |
| --- | --- |
| Commits, trees, blobs reachable from packed refs | Yes |
| Branch/tag refs selected in the bundle | Yes |
| Objects only in reflogs or unreachable, not held by refs | Not by default |
| Uncommitted working tree changes | No |
| Untracked/ignored files | No |
| Git config, hooks, and credentials | No |
| Actual Git LFS objects | No; Git stores only pointer blobs |
| Submodule repositories | No; superproject stores only gitlink commits |

A bundle is a Git history backup at the refs/objects level. To protect the entire development environment, back up components outside the bundle's scope separately.

## 5. Protecting deleted or rewritten commits

A bundle with `--all` stores objects reachable from refs. If a commit exists only in the reflog or as a dangling object, it may not be included in a normal bundle.

If you discover an important commit about to lose its ref, create a clearly named backup ref before garbage collection removes the object:

~~~bash
git branch backup/recovered-commit <commit-id>
~~~

Or create a backup tag if repository policy allows:

~~~bash
git tag backup/pre-rewrite-2026-11-17 <commit-id>
~~~

Then create a bundle with `--all` to include the backup ref in the snapshot. Do not create arbitrary refs on shared repositories; establish clear namespaces and retention so they do not mix with development branches.

If investigating a lost commit, you can inspect the reflog:

~~~bash
git reflog --all
~~~

Reflogs are useful for finding commits a branch used to point to, but reflogs have retention limits and can expire. They are a short-term recovery tool, not a long-term backup.

## 6. Backing up mirrors in a recoverable way

A common workflow is maintaining a mirror for a fast replica while creating independent periodic snapshots:

~~~text
Source repository
      |
      +----> Scheduled mirror updates
      |
      +----> Point-in-time bundle snapshots
                   |
                   +----> Versioned/offline storage
                   |
                   +----> Verification and restore drills
~~~

Example operational schedule:

| Task | Suggested frequency | Purpose |
| --- | --- | --- |
| Update mirror | Hourly or daily depending on change rate | Maintain a replica close to current state |
| Create bundle snapshot | Daily or at release milestones | Preserve refs/objects at a specific point in time |
| Verify bundle | After every creation | Catch corrupted snapshots early |
| Restore drill | Periodically per RPO/RTO | Verify restoration actually works |
| Store offline/immutable copy | According to retention policy | Protect if source accounts or servers are compromised |

Never store all backups solely on the same server, volume, or credential domain as the source repository. If a data deletion incident or ransomware hits the source, backups in the same domain could be affected too.

## 7. Consistency when backing up an active repository

A repository can be updated while a backup is running. If multiple refs change between listing refs and packing objects, the snapshot may not represent a coherent business state desired by the team.

For server-side repositories or systems with concurrent pushes, use platform-supported snapshot/storage backups or pause writes during the backup window to obtain a clean consistency point. If creating a bundle from a separate freshly fetched clone, record the timestamp and which refs were retrieved.

For filesystem backups of bare repositories, ensure the snapshot consistently covers the entire Git directory, including the object database, refs, and packed-refs. Never copy a few individual directories while Git is updating them and treat the result as a valid backup.

After creating a snapshot, record accompanying metadata:

- Repository name and backup source.
- Snapshot timestamp, timezone, and run ID.
- Git version and backup method.
- Ref list or `git bundle list-heads` output.
- Verification/fsck results.
- Hash/checksum of the backup file.
- Storage location and retention period.

## 8. Verifying integrity

A backup is only useful if it can be read and restored. Verify at multiple layers.

### Verify the bundle

~~~bash
git bundle verify /backup/app-2026-11-17.bundle
git bundle list-heads /backup/app-2026-11-17.bundle
~~~

### Verify the restored repository

~~~bash
git -C /restore/app fsck --full
git -C /restore/app show-ref
git -C /restore/app log --oneline --decorate --all -20
~~~

`git fsck --full` checks the integrity and connectivity of the Git object database. It does not validate application business logic, does not verify LFS objects on the server, and does not prove that all system configuration has been backed up.

### Verify backup file checksums

On Linux:

~~~bash
sha256sum /backup/app-2026-11-17.bundle
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'D:/backup/app-2026-11-17.bundle'
~~~

Store checksums separately from the backup file to detect data corruption during storage or transfer.

## 9. Components that must be backed up separately

### Git LFS

Git commits store only pointer files; Git bundles and mirrors do not automatically contain actual LFS content. If the repository uses Git LFS, back up the LFS object store as well or use the LFS server's backup functionality.

You can fetch LFS objects for all refs into the local cache with:

~~~bash
git lfs fetch --all origin
~~~

Check configuration and storage location:

~~~bash
git lfs env
git lfs ls-files
~~~

Then back up the LFS object store at the actual path reported by `git lfs env`, or back up server-side storage directly. A Git bundle containing only pointers without the corresponding LFS objects will not restore large file contents.

### Submodules

The superproject stores submodule paths and gitlink commits. The history content of each submodule repository lives in its own repository. Therefore, back up each submodule repository and ensure referenced commits remain accessible.

The `.gitmodules` file resides in the superproject's history, but it does not contain submodule object databases.

### Config, hooks, and server policies

Bundles and mirror clones are not complete copies of server configuration or the operational environment. Back up required recovery components separately:

- Necessary repository and remote configuration.
- Server-side hooks or hook path configuration.
- Branch protection, access control, deploy keys, and review policies.
- CI/CD, webhook, and integration configurations.
- Issue, pull request, release, or artifact metadata if stored outside Git by the platform.
- Credentials and secrets through a dedicated secret backup process with encryption and access control.

Never include tokens, private keys, or secrets in bundles or public backups. Backups themselves must also be protected with least-privilege access and proper encryption.

### Uncommitted working tree

Git bundles and mirrors only protect history retained by refs. They do not contain uncommitted changes, untracked files, or ignored files.

If local work needs protection, commit it to an appropriate branch or create a separate archive/filesystem snapshot for the working tree. Before archiving, check:

~~~bash
git status --short
git diff
git diff --cached
~~~

Do not assume stash is a long-term backup; stashes are still refs inside the repository and can be deleted or lost along with the repository.

## 10. Designing retention and recoverability

A backup policy must answer two questions:

- **RPO (Recovery Point Objective):** how much data loss since the most recent backup is acceptable?
- **RTO (Recovery Time Objective):** how long can it take to restore the repository and service back to operation?

For example, if RPO is 24 hours, daily snapshots may fit, provided run timing and completion duration are accounted for. If RPO is 1 hour, more frequent backups or higher-frequency replication/snapshot solutions are required.

You can apply the 3-2-1 rule:

- Keep at least three copies of data.
- Use at least two different storage media or domains.
- Keep at least one copy offsite or in an independent administrative domain.

For critical repositories, maintain at least one immutable or offline backup so anyone with permission to delete the source repository cannot also delete historical backups. Retention periods should be long enough to catch accidental deletions or delayed history alterations.

## 11. Running restore drills instead of just checking file existence

A successful backup job or the presence of a bundle file is not enough. Periodically create a test restore directory and restore a snapshot into it.

Example:

~~~bash
git bundle verify /backup/app-2026-11-17.bundle
git clone /backup/app-2026-11-17.bundle /restore-drill/app
git -C /restore-drill/app fsck --full
git -C /restore-drill/app show-ref
git -C /restore-drill/app log --oneline --decorate --all -20
~~~

Then confirm:

1. Do critical branches point to the exact commits at the snapshot timestamp?
2. Are release tags intact and pointing to the right commits?
3. Are the commits needed for recovery readable?
4. Can submodules be cloned and checked out at their corresponding commits?
5. Can LFS objects be downloaded with matching sizes/hashes?
6. Can configuration, hooks, access permissions, and pipelines be recreated?
7. Does restore duration meet the RTO?

Run restore drills in an isolated environment. Never overwrite a production repository or active remote during a test.

## 12. Sample backup workflow

A Git bundle snapshot workflow for a repository with an existing local clone:

~~~bash
# 1. Update refs from remote
git fetch --all --tags --prune

# 2. Check source status and integrity
git status
git fsck --full

# 3. Create a uniquely named snapshot
git bundle create /backup/app-2026-11-17.bundle --all

# 4. Verify bundle and ref list
git bundle verify /backup/app-2026-11-17.bundle
git bundle list-heads /backup/app-2026-11-17.bundle

# 5. Compute checksum
sha256sum /backup/app-2026-11-17.bundle

# 6. Practice restore in a separate directory
git clone /backup/app-2026-11-17.bundle /restore/app-2026-11-17
git -C /restore/app-2026-11-17 fsck --full
~~~

Note: `git fetch --all --tags --prune` updates remote-tracking refs and may prune refs deleted on the remote. That becomes the state you choose to snapshot. If you need to keep local refs or refs deleted at the source, locate and create backup refs before fetching/pruning; do not let synchronization accidentally erase traces you want to preserve.

For repositories experiencing concurrent writes from many users, take snapshots from a dedicated fetched backup clone or use the server's consistent snapshot mechanism. If refs must be preserved at an exact point in time, record the snapshot timestamp and avoid updating refs while packaging.

## 13. Backup method selection diagram

~~~mermaid
flowchart TD
    A[Need to protect repository] --> B{Need current-state replica?}
    B -- Yes --> C[Create bare mirror with clone --mirror]
    C --> D[Sync on schedule]
    B -- No --> E{Need to recover old history?}
    D --> E
    E -- Yes --> F[Create point-in-time bundle snapshot]
    E -- No --> G[Evaluate retention and recovery goals]
    F --> H[Verify, checksum, and restore drill]
    G --> H
    H --> I{Repository has LFS or submodules?}
    I -- Yes --> J[Back up LFS objects and each submodule separately]
    I -- No --> K[Back up config, hooks, and non-Git metadata]
    J --> K
    K --> L[Store immutable/offline copy and verify periodically]
~~~

Before finishing, verify for yourself:

1. Do I need a mirror for current failover or a snapshot to recover history?
2. Does the mirror prune or force-update refs in a way that causes old history to disappear?
3. Does the bundle snapshot contain all refs that need protection?
4. Did I protect commits existing only in reflogs or dangling objects before GC?
5. Have LFS objects, submodules, config, hooks, and working trees been handled separately?
6. Has the bundle been verified, checksummed, and test-restored?
7. Does the backup include an offline/immutable copy and retention matching RPO/RTO?

A mirror provides a replica close to the current state; point-in-time snapshots preserve history for recovery after refs are deleted or rewritten. A reliable Git backup strategy combines both when needed, stores LFS and non-Git data separately, verifies integrity, and runs restore drills regularly. Only when you can restore into an independent environment do you have proof that your backup actually works.

## References

- [Git documentation: git-clone](https://git-scm.com/docs/git-clone) — bare clones and mirror clones.
- [Git documentation: git-bundle](https://git-scm.com/docs/git-bundle) — creating, listing, verifying, and restoring bundles.
- [Git documentation: git-fsck](https://git-scm.com/docs/git-fsck) — checking object database integrity.
- [Git documentation: git-push](https://git-scm.com/docs/git-push) — mirror push semantics and ref updates.
- [Git LFS documentation](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-fetch.adoc) — downloading LFS objects and the `--all` option.
- [Pro Git: Git Internals - Maintenance and Data Recovery](https://git-scm.com/book/en/v2/Git-Internals-Maintenance-and-Data-Recovery) — object database, reflogs, and data recovery.

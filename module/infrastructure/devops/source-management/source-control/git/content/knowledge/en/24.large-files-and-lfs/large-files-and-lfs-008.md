# Migrating Existing History Files to LFS and Commit-Rewriting Consequences

Git LFS helps a repository manage large files by storing a small **pointer file** in Git while storing the actual content in a separate LFS store. If a large file was committed before the team enabled LFS, merely running `git lfs track` will not convert old blobs in history to LFS. To replace them, you need to migrate history with `git lfs migrate import`.

This operation rewrites commits containing the selected files. Because commit hashes depend on tree contents and parent commits, affected commits and all subsequent descendant commits will receive new SHA hashes. When history has already been shared on a remote, publishing the rewritten history requires coordinated force-pushing and updating other clones.

## 1. Why Migrate Instead of Just Tracking?

When you run:

```bash
git lfs track "*.psd"
```

Git LFS adds a rule to `.gitattributes`, typically looking like:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
```

This rule ensures future `git add` commands process `.psd` files through the LFS filter. Content staged in new commits is replaced by a pointer file in Git, while the actual object is stored in LFS.

However, older commits still contain the original binary blobs. Git does not retroactively modify history simply because `.gitattributes` changed. If a 500 MB file appeared across multiple commits, the blobs corresponding to each content version remain in history and make cloning the repository heavy.

To convert content already present in history, run:

```bash
git lfs migrate import --include="*.psd"
```

This command finds files matching the pattern within the migrated ref scope, replaces their content with LFS pointers, and rewrites the affected commits. It also updates `.gitattributes` so future additions continue using LFS.

## 2. Understanding Pointer Files and LFS Objects

After migration, Git stores a small text file in place of the large blob. Example pointer content:

```text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac19622fc3ada9c0fdeadb33f88f367b541f38b891c6c6f2f3d2f4f5f6a7b8
size 52428800
```

The pointer contains the specification version, the SHA-256 hash of the actual content, and the byte size. Actual content is stored in the LFS object store and transferred through the server's LFS endpoint. Git commits contain only pointers, so routine Git operations do not need to download large blobs into Git's object database.

On checkout, Git LFS uses the pointer to download the corresponding content into the working tree. This means anyone cloning needs Git LFS installed and permission to access the LFS endpoint to retrieve the real files.

## 3. Preparing Before Rewriting History

Migrating history affects commit hashes and refs. Before starting, prepare thoroughly:

1. **Notify the team.** Agree on the migration window, which branches/tags will be affected, and who is responsible for pushing the rewritten history.
2. **Verify remote LFS support.** Confirm the server has Git LFS enabled, your account has permission to upload objects, and LFS storage/bandwidth quotas are sufficient.
3. **Install Git LFS.** Check `git lfs version`, then run `git lfs install` in the environment you will use.
4. **Use a full clone.** If the repository is a shallow clone, fetch full history first; migration can only process history and refs present locally.
5. **Fetch the refs to migrate.** Update relevant branches and tags. In a single-branch clone, fetch the additional branches that need processing.
6. **Save in-progress work.** Commit or stash changes you want to keep and ensure the working tree is clean.
7. **Create a backup.** Keep a mirror clone or bundle containing pre-migration refs and Git objects; if the repository already had LFS objects, back up the required LFS object store as well.

Check status and environment:

```bash
git status
git rev-parse --is-shallow-repository
git remote -v
git lfs version
git lfs env
```

If the repository is still shallow, fetch full history before migrating:

```bash
git fetch --unshallow origin
```

Only run this when the remote can provide full history. If the remote or upstream clone is also restricted, handle the history scope according to server policy.

### Creating a Backup of Refs Before Migration

A bundle can preserve the refs and Git objects currently in the repository:

```bash
git bundle create ../before-lfs-migration.bundle --all
```

A bundle does not include uncommitted working tree files and is not a copy of the LFS object store. Therefore, save uncommitted changes separately and back up LFS objects if the repository already used LFS previously. A mirror clone from the remote is also useful to preserve pre-update remote state, though it only contains refs advertised by the remote.

## 4. Inspecting Large Files Before Migrating

Git LFS provides `migrate info` to analyze files in history without rewriting commits:

```bash
git lfs migrate info --everything
```

This helps inspect file size distribution across history and identify file groups suitable for moving to LFS. You can filter by pattern:

```bash
git lfs migrate info --everything --include="*.psd,*.zip,*.mp4"
```

You can also focus only on files exceeding a size threshold:

```bash
git lfs migrate info --everything --above=50MB
```

The analysis helps define the migration scope. Carefully review which files genuinely belong in LFS: not every large file needs migration, and some generated files or build artifacts should instead be excluded from the repository using `.gitignore`.

`--everything` instructs the tool to examine local refs supported by the command, including branches, tags, and fetched remote-tracking refs. It does not modify the remote server directly. If a branch or tag has not been fetched into the current clone, it cannot be migrated in this local clone.

## 5. Migrating Files Already in History

### Migrating File Types Across Local Refs

Suppose the repository already contains Photoshop files, archives, and videos in history. To convert them across all fetched local refs:

```bash
git lfs migrate import --everything --include="*.psd,*.zip,*.mp4"
```

Meaning:

- `import`: converts regular Git blob contents into LFS objects and pointers.
- `--everything`: applies the migration to all local refs supported by the tool, rather than only the currently checked-out ref.
- `--include`: selects paths/file patterns to convert.

Patterns in `--include` are comma-separated. You can use filename or path patterns, such as `"*.psd,assets/**/*.tif"`. Quote the string so the shell does not expand wildcards before Git LFS receives them.

### Migrating Only a Specific Ref

If you only want to convert history on branch `main`, restrict the ref:

```bash
git lfs migrate import --include="*.psd,*.zip" --include-ref=refs/heads/main
```

`--include-ref` accepts the ref name to migrate. This is useful when a team wants to test on one branch or roll out in phases. Other unmigrated branches/tags may still hold old large blobs.

### Excluding Specific Paths

If an include pattern is broad yet certain files should remain Git blobs, add `--exclude`:

```bash
git lfs migrate import --everything --include="*.zip,*.7z" --exclude="fixtures/*.zip"
```

Verify rules against the actual directory structure. Do not rely on filenames visible in the working tree if the same filename appears across multiple paths.

### Verifying Converted Files

After migration:

```bash
git lfs ls-files --all
git lfs migrate info --everything --include="*.psd,*.zip,*.mp4"
git status
```

`git lfs ls-files --all` lists LFS files across the history/refs reachable to the command. Inspect `.gitattributes` to confirm patterns were recorded. You can verify a specific file:

```bash
git check-attr filter diff merge text -- assets/design.psd
```

For an LFS-tracked file, output typically shows `filter: lfs`, `diff: lfs`, `merge: lfs`, and `text: unset`.

## 6. Ref Scope and Why Choosing It Properly Matters

By default, without specifying refs or `--everything`, `git lfs migrate import` typically migrates only the current branch. This can work for testing, but is insufficient if large blobs remain in other branches or old tags.

| Scope | How to Specify | Consequence |
|---|---|---|
| Current branch | No extra ref specified | Only history reachable from the current branch is processed |
| Specific ref | `--include-ref=refs/heads/main` | Refs outside scope may still contain old blobs |
| Multiple local refs | `--include-ref` per ref or `--everything` | Suitable when processing multiple fetched branches/tags |

If the repository has multiple branches and release tags, list all refs to migrate beforehand. An old tag pointing to a commit containing a large blob can continue retaining that blob in history even after the main branch has been migrated to LFS.

`--everything` only operates on local refs in the repository where you run the command; it cannot automatically update branches on the server or other people's forks. The remote only changes after you push the rewritten refs.

## 7. Why Do Commit Hashes Change?

A Git commit is identified by a hash computed from its tree, parent commits, author/committer metadata, and commit message. When a large blob is replaced by a pointer, the commit's tree changes. That commit therefore receives a new hash. Descendant commits inherit the new parent, so their hashes also change even when other files in those commits remain untouched.

Example before migration:

```text
A---B---C---D  main
        |
        B contains assets/design.psd as a Git blob
```

After migration, history can become:

```text
A---B'---C'---D'  main
```

`B'` holds an LFS pointer instead of the blob; `C'` and `D'` have a new parent and thus receive new commit hashes as well. The old commits are not modified in place. They become objects no longer referenced by the rewritten refs and may linger in local copies, reflogs, backups, or the remote until cleaned up per storage retention policies.

### Consequences for Tags and Signatures

- Tags pointing to old commits may need to be updated to point to the corresponding rewritten commits.
- Signed annotated tags cannot retain their old signatures if the tag object or target object changes; they must be recreated and re-signed per release procedures.
- Commit signatures on rewritten commits are no longer valid for the new commits; if policy requires signed commits, signatures must be regenerated appropriately.
- Releases on code hosting platforms may still reference old SHAs. Check releases, pull requests, CI, and external integrations after migration.

Do not assume every tag automatically preserves its intended meaning after migration. Identify which tags should be migrated, which tags must remain immutable historical milestones, and how the team publishes new versions.

## 8. Pushing LFS Objects and New History to the Remote

After migrating, the local repository contains pointers in Git and corresponding LFS objects in the local LFS store. The remote needs both the LFS objects and the rewritten refs.

You can push all LFS objects referenced by local refs:

```bash
git lfs push --all origin
```

Then update the rewritten branches. For example, if all local branches were migrated:

```bash
git push --force origin --all
```

If tags were also migrated and need updating on the remote:

```bash
git push --force origin --tags
```

Force-push commands replace history/refs on the remote. Run them only after the team has agreed on the timing, confirmed the remote has no unintegrated new commits, and ensured you have permission to update the relevant branches/tags. If only one branch was migrated, push that specific branch instead of force-pushing all branches:

```bash
git lfs push --all origin
git push --force origin main
```

If the remote enables branch protection or blocks force pushes, an administrator must adjust rules temporarily or execute within an approved maintenance window. Do not remove protections arbitrarily.

Git LFS normally installs a pre-push hook to upload relevant LFS objects when pushing Git refs. `git lfs push --all` is a useful explicit step to ensure LFS objects referenced by all local refs are uploaded before publishing rewritten refs.

## 9. Impact on Teammates and Existing Clones

After force-pushing migrated history, teammates' clones still hold the old commits. If they continue pushing old branches, merging old history into rewritten branches, or opening pull requests based on old commits, the repository can reintroduce old history or run into hard-to-resolve conflicts.

Before migration, ask everyone to:

- Commit or back up unshared local changes.
- Pause pushing to branches within the migration scope.
- Note down local branches and commits that need to be preserved.
- Avoid creating additional commits on old history during the migration window.

Once migration finishes, the simplest and safest approach for clones with no local work to keep is to re-clone the repository. If local work must be preserved, save patches or separate branches first, sync the rewritten branch from the remote, and cherry-pick verified unshared commits.

Example updating an existing clone after the team announces migration completion:

```bash
git fetch origin
git switch main
git reset --hard origin/main
```

`reset --hard` discards uncommitted tracked changes in the working tree and index of that branch. Only run it after backing up or saving all work you need to keep. When there are multiple branches, tags, or complex local changes, re-cloning is usually less risky.

Forks and other remotes are not updated automatically. Each fork owner must sync per team guidelines; otherwise they may retain old history and bring large blobs back when submitting changes.

## 10. What Migration Does Not Automatically Solve

- **Does not immediately delete old Git data everywhere.** Old blobs may persist in object databases, reflogs, backups, forks, and remotes until garbage-collected.
- **Does not automatically update all remotes.** The migrate command rewrites local refs; new refs must be pushed to every relevant remote.
- **Does not guarantee the remote has enough LFS storage.** The server can reject uploads due to quotas, file size limits, or access permissions.
- **Does not install Git LFS for others.** New clones need Git LFS to download actual content from pointers.
- **Does not convert unselected files.** Files outside `--include` remain regular Git blobs.
- **Does not alter intended business content.** However, commit hashes change because file representations in trees changed.

After new refs are published and all clones are updated, server administrators may need a separate garbage-collection process to reclaim old Git objects. Timing and reclaim behavior depend on the hosting platform; LFS objects also continue consuming LFS storage according to server retention policies.

## 11. Sample Migration Workflow for a Repository

Suppose a team wants to convert all `.psd` and `.mp4` files across all local branches/tags to LFS.

**Step 1: Prepare Clone and Backup**

```bash
git status
git fetch --all --tags
git bundle create ../before-lfs-migration.bundle --all
git lfs install
```

Ensure the working tree is clean, the repository is not shallow, and the remote supports LFS. If using a single-branch clone, fetch additional branches to migrate.

**Step 2: Inspect Scope**

```bash
git lfs migrate info --everything --include="*.psd,*.mp4"
```

Review the file list and size to be converted. Confirm no files intended to remain Git blobs are mistakenly included.

**Step 3: Migrate Local History**

```bash
git lfs migrate import --everything --include="*.psd,*.mp4"
```

This rewrites local refs within the `--everything` scope and updates `.gitattributes`. Wait for completion and read all messages carefully.

**Step 4: Verify Pointers and LFS Objects**

```bash
git lfs ls-files --all
git lfs migrate info --everything --include="*.psd,*.mp4"
git check-attr filter diff merge text -- assets/design.psd
git status
```

Confirm files are listed as LFS, `.gitattributes` has the right patterns, and the working tree has no unexpected modifications. You can run `git lfs fsck` to verify integrity of local LFS objects within supported scope.

**Step 5: Publish New History**

```bash
git lfs push --all origin
git push --force origin --all
git push --force origin --tags
```

Only force-push after coordinating and obtaining approval to update remote refs. If migrating only one branch, push that branch instead of `--all`; if tags are out of scope or must stay immutable, follow the team's tag policy.

**Step 6: Sync Team and Pipelines**

Announce the new commit hashes, instruct teammates to re-clone or sync local branches after backing up, update CI to install Git LFS, and verify LFS endpoints/quotas. Validate with a clean clone that real files check out and download properly.

## 12. Hands-On Exercise

In a test repository, create a sufficiently large dummy binary file, commit it at several points, and create an additional branch. Do not use a production repository for exercises.

1. Run `git lfs migrate info --everything --above=1MB` to inspect large files in history.
2. Create a backup using `git bundle create ../before-lfs.bundle --all`.
3. Run `git lfs migrate import --include="*.bin" --include-ref=refs/heads/main` to migrate only the `main` branch.
4. Use `git lfs ls-files --all`, `git log --oneline --all`, and `git check-attr` to verify the results.
5. Compare commit SHAs before and after migration, and explain why descendant commits also changed hashes.
6. Try migrating all refs in another test clone using `--everything`, then identify which branches/tags need updating on the remote.
7. Write a communication plan covering teammate notification, backups, force-pushing, and re-syncing clones after rewriting history.

You have completed the exercise when you can distinguish `git lfs track` from `git lfs migrate import`, choose an appropriate ref scope, and explain the impact of commit rewriting on remotes, tags, pull requests, and teammates' clones.

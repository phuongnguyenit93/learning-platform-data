# Rewriting History with Dedicated Filtering Tools and Clone Synchronization Plans

Git stores history as objects with content-based identifiers. When a commit's contents change, that commit's ID changes; child commits also receive new IDs because their parent changed. Consequently, deleting a file from the latest commit does not remove the file from earlier commits. If a repository ever contained secrets, sensitive data, or large binary files, you may need to rewrite history to strip that content from the relevant commits.

Rewriting history is an administrative operation that affects every copy relying on old commits. It requires the right tool, a complete backup, a write-freeze window, and a synchronization plan for clones, forks, pull requests, CI, and dependent systems. This lesson focuses on `git filter-repo`, verifying results, updating remotes, and bringing team clones onto the new history.

In Git source-code management services, history rewriting is typically used to purge accidentally committed secrets, remove files that do not belong in Git, or transform history layout under a new policy. This is not a routine commit-fixing operation; perform it only with a clear goal and after aligning on its impact with repository users.

## 1. Why rewrite history?

Some common scenarios:

- A `.env` file, private key, token, or credential was committed at some point.
- Build files, archives, or large binaries were added across multiple commits, bloating repository size.
- A directory or file must be purged from all history for legal or retention-policy compliance.
- The repository needs a path structure transformation across all branches.
- The team needs to standardize author identities or commit metadata during a controlled migration.

Deleting a file in the latest commit only creates a new commit recording the deletion. Previous commits still contain the old blob:

```text
Before deleting the file:

A --- B --- C --- D  main
          |
          +-- B contains secrets.env

After running git rm and committing:

A --- B --- C --- D --- E  main
          |
          +-- B still contains secrets.env
                         E only records the file deletion
```

To remove the file from older commits, the commits containing that file must be recreated. After rewriting, history takes a new form:

```text
A' --- B' --- C' --- D' --- E'  main
        (secrets.env is no longer in the filtered snapshots)
```

The commit IDs are regenerated. This change affects branches, tags, pull requests, and every clone using the old history.

## 2. How rewriting history differs from revert or a deletion commit

| Approach | Result | Does old history still retain the content? |
| --- | --- | --- |
| `git rm` then commit | Removes file from the latest snapshot | Yes |
| `git revert <commit>` | Creates a new commit reversing an earlier commit's changes | Yes |
| `git filter-repo` | Recreates commits/trees according to filter rules | Filtered objects can be excluded from new history; old clones and backups may still hold them |

If the goal is to undo a published change, `git revert` is usually appropriate because it preserves public history. If the goal is to eliminate sensitive data from history, revert is insufficient. If the goal is to reduce size caused by large blobs, deleting in a new commit does not free the old blobs either.

**For exposed secrets, revoke or rotate the secret immediately before rewriting Git history.** Rewriting history does not invalidate old tokens and does not delete copies that others or services have already downloaded.

## 3. Choosing a dedicated filtering tool

### `git filter-repo`

`git filter-repo` is the dedicated tool currently recommended for most Git history filtering and rewriting needs. It supports filtering by path, blob content, size, refs, and many other criteria. It is generally faster and safer than workflows based on `git filter-branch`.

Check the tool:

```bash
git filter-repo --version
```

If unavailable, install it according to the official instructions appropriate for your OS and Python/package manager version. After installing, confirm `git filter-repo` is in your PATH.

### `git filter-branch`

`git filter-branch` is a legacy tool long provided by Git, but it has performance limitations and is error-prone when writing filter scripts. For new projects, prefer `git filter-repo`; only maintain `filter-branch` when compatibility with legacy environments is required and the risks are understood.

### BFG Repo-Cleaner

BFG is another option for common tasks like removing large files or replacing sensitive content. It has its own usage model and can fit when a team already has an established BFG workflow. This lesson uses `git filter-repo` as the primary example because it supports diverse filtering modes and fine-grained control over ref scope.

## 4. Planning before rewriting

History rewriting should be treated as a scheduled maintenance window, especially for shared repositories.

### Defining scope

Answer these questions:

1. What content needs to be removed or modified: one path, multiple paths, secret strings, oversized blobs, or metadata?
2. Must all branches/tags be filtered or only a specific set of refs?
3. Which release tags, maintenance branches, forks, and pull requests are affected?
4. Are there related LFS objects, submodules, packages, release assets, or artifacts?
5. Which teams must synchronize clones and when are writes allowed to resume?

### Freezing writes

Before running the filter:

- Announce the maintenance window and request a pause on pushes, pull request merges, tag creation, and branch updates.
- Pause pipelines capable of pushing back to the repository.
- Record the list of existing branches and tags.
- Identify special refs created by the Git hosting service, such as pull request refs or internal refs that users cannot push directly.
- Assign who is responsible for running the filter and who will verify the results.

If someone pushes during filtering, the rewrite may miss new commits or overwrite newly pushed work. A write freeze ensures everyone starts from a consistent snapshot.

### Protecting data and backups

Create a full Git backup before filtering. If the repository uses Git LFS, back up LFS objects separately because a Git mirror clone does not guarantee all LFS content has been downloaded.

Example:

```bash
git clone --mirror https://git.example.com/team/project.git project-backup.git
git -C project-backup.git lfs fetch --all origin
```

The second command is only needed if the repository uses LFS and Git LFS is installed in the environment. Confirm both the mirror clone and LFS fetch complete. Protect the backup with appropriate access controls; if the rewrite is due to an exposed secret, the backup still contains the old secret and must be stored in a restricted location.

Do not use a backup containing sensitive data as a routine working remote. When incident response procedures permit, archive or destroy the backup in accordance with security and retention policies.

## 5. Inventorying refs and storage size before filtering

In the clone used for rewriting, record existing refs:

```bash
git show-ref
git for-each-ref --format='%(refname) %(objectname)'
```

Check branches and tags:

```bash
git branch -a
git tag --list
```

Measure object storage size:

```bash
git count-objects -vH
```

For large files, you can analyze objects and paths before choosing filter criteria. `git filter-repo` provides an analysis mode:

```bash
git filter-repo --analyze
```

This mode generates analysis reports in filter-repo's metadata directory. Review the reports to identify paths or blobs consuming significant space, then decide clearly which files genuinely need removal. Do not delete a file solely because it tops the size list; it might be an asset that should be moved to LFS or an artifact repository.

## 6. Executing in a fresh mirror clone

For shared repositories, perform filtering inside a fresh mirror clone created specifically for the rewrite. Example:

```bash
git clone --mirror https://git.example.com/team/project.git project-rewrite.git
```

A mirror clone is a bare repository containing the refs advertised by the server and has no working tree. It is the right choice when rewriting multiple branches and tags simultaneously.

Enter the repository:

```bash
cd project-rewrite.git
git show-ref
git remote -v
```

`git filter-repo` normally requires a fresh clone to reduce the risk of accidentally rewriting a repository containing local work. If the tool refuses to run because the repository does not appear to be a fresh clone, create a new clone and run it there. Only use `--force` when you understand the warning, have a backup, and have a clear reason to run on the current repository; do not use `--force` merely to bypass default safety checks.

## 7. Removing one or more paths from entire history

Suppose `config/secrets.env` was committed at multiple points and must be removed from all snapshots:

```bash
git filter-repo --path config/secrets.env --invert-paths
```

Meaning:

- `--path config/secrets.env` selects the path to keep within the filter scope.
- `--invert-paths` inverts the selection, thereby excluding that path from history.

To remove multiple paths:

```bash
git filter-repo \
  --path config/secrets.env \
  --path deploy/private-key.pem \
  --invert-paths
```

Paths are evaluated relative to the repository root. If a file was ever renamed or moved, include all old and new paths in the filter list. If you filter only the current name, versions at old paths may remain in historical commits.

Example where a file existed at two locations:

```bash
git filter-repo \
  --path old/config/secrets.env \
  --path config/secrets.env \
  --invert-paths
```

If you only want to retain one directory or set of files, omit `--invert-paths` and list the `--path` entries to keep. Verify the tool's path-matching behavior before filtering to avoid unintentionally inverting the scope.

## 8. Replacing sensitive strings in historical content

When a secret was copied into many files or commits, you can use `--replace-text` to substitute strings in historical blobs.

Create an expressions file outside the working repository, e.g., `../replacements.txt`:

```text
literal:EXAMPLE_OLD_TOKEN_VALUE==>***REMOVED***
literal:old-password-for-demo==>***REMOVED***
```

The strings above are mock values only. Never put real secrets into shell commands, logs, or guide documentation. Protect the expressions file if it contains real sensitive strings.

Run the filter:

```bash
git filter-repo --replace-text ../replacements.txt
```

`--replace-text` replaces matching content in processed blobs. The expressions file supports formats such as `literal:`, `regex:`, or `glob:` depending on your tool version's syntax. Check `git filter-repo --help` before using complex expressions.

Replacing strings in Git history does not revoke secrets. Tokens, passwords, and private keys must be revoked or rotated in the systems that issued them. Additionally, secrets may appear in different encodings, encrypted forms, binary files, logs, or copies outside the repository; run secret scanning tools and investigate per incident scope.

## 9. Removing oversized blobs or filtering by object list

If the repository contains many large blobs that should not be stored in Git, you can use:

```bash
git filter-repo --strip-blobs-bigger-than 50M
```

The command strips blobs exceeding the threshold from filtered history. This is a broad operation: it may remove legitimate assets such as videos, models, or test data. Analyze first with `--analyze`, identify files to keep, and consider moving them to LFS or artifact storage.

If you already have a specific list of blobs to remove, you can use `--strip-blobs-with-ids` with a file containing object IDs in the format expected by the tool. This is more targeted than stripping every blob above a size threshold.

After stripping blobs, commits whose snapshots changed may be rewritten; empty commits or degenerate merges may be handled according to the tool's rules. Carefully inspect the new history and important merge commits.

## 10. Filtering only specific refs

Not every rewrite needs to affect all refs. `git filter-repo` supports `--refs` to limit the scope of rewritten refs, for example:

```bash
git filter-repo \
  --path config/obsolete.yml \
  --invert-paths \
  --refs refs/heads/main refs/heads/release/2.x
```

Before using a limited scope, understand the relationships among branches and tags. A commit can be referenced by multiple refs; if you rewrite only some refs, unselected refs may continue pointing to old history. This can be intentional when fixing only one dedicated branch, but does not satisfy removing data from the entire repository.

For secret incidents, you normally must inventory and process every ref that can reach sensitive content, including branches, tags, and provider-advertised refs. Do not assume `--refs` is a safer default; the scope must match the remediation goal.

## 11. Verifying results after filtering

Do not push immediately after the filter command finishes. First, inspect the new refs and contents.

### Checking history and removed files

```bash
git log --all --oneline --decorate -20
git show-ref
git log --all -- config/secrets.env
```

The last command should return no commits recording the removed path within the filtered refs scope. Also check old paths if the file was ever moved.

### Checking objects and integrity

```bash
git fsck --full
git count-objects -vH
```

Dangling or unreachable warnings may appear depending on object types and tool behavior; determine whether they belong to the excluded scope or are other legitimately retained data. Never ignore missing/corrupt object errors.

### Checking with a secret scanner

Run a secret scanner or history inspection tool on the filtered repository. For known secrets, confirm the string no longer appears in advertised history. Avoid using `grep` with a real secret in a way that prints the value to the terminal or saves it in logs.

### Inspecting the generated commit map

`git filter-repo` can generate metadata files such as `commit-map` and `ref-map` inside `.git/filter-repo` (in a bare mirror clone, metadata resides in the corresponding Git directory). These maps allow cross-referencing old and new commit IDs, useful when notifying the team or updating references in systems outside Git.

Store necessary maps in controlled maintenance records. Do not publish maps or logs if they could expose sensitive information or commit IDs leading to purged data.

## 12. Restoring the remote after filter-repo

To prevent accidental pushes, `git filter-repo` typically removes the `origin` remote from repository configuration after running. Check:

```bash
git remote -v
```

If `origin` is gone, re-add the official URL:

```bash
git remote add origin https://git.example.com/team/project.git
git remote -v
```

Verify the URL points to the exact target repository and contains no embedded username/token. Do not add the backup remote as a target and push to it by mistake.

## 13. Pushing new history to the remote

This step directly impacts others. Perform it only during the announced maintenance window after verifying backups, ref scope, and filter results.

### Pushing rewritten branches

For a regular repository, you can update local branches:

```bash
git push --force --all origin
```

This command force-updates local branches to the remote. It does not automatically delete remote branches that no longer exist locally and does not replace handling provider-specific special refs.

### Pushing rewritten tags

```bash
git push --force --tags origin
```

Tags pointing to old commits must be updated per plan. Annotated tags may be recreated; signatures on old tags no longer validate for new objects. If release policy requires signatures, re-sign tags after rewriting and check tag protection policies.

If a tag must be completely deleted, removing that tag from the local clone does not automatically delete it on the remote when running `git push --tags`. Delete remote tags explicitly by name after confirming scope:

```bash
git push origin --delete v1.2.3
```

Only delete release tags when the release owner and team agree; if the tag must keep its name while pointing to a new commit, recreate/update it following the project's signing and release process.

### When mirroring all refs

When a mirror clone is complete and confirmed as the canonical source for all refs that the remote allows managing, you can use:

```bash
git push --force --mirror origin
```

`--mirror` synchronizes all refs managed by the mirror clone and can delete refs on the remote if they no longer exist locally. This is a broad operation; do not run it on a shared remote without first inventorying hidden refs, pull request refs, provider-managed refs, and branch/tag policies.

### `--force-with-lease` and the freeze window

When updating a specific branch, `--force-with-lease` helps reject the push if the remote has changed from what local expects:

```bash
git push --force-with-lease origin main
```

However, for a full-repo ref rewrite, plan individually for each ref and remote state. Intentional force-pushing is only safe when the team has frozen writes, inventoried refs, and confirmed there are no new commits that must be kept. If unplanned updates occurred, stop and handle them before overwriting.

## 14. Systems that may still retain old history

After updating the remote, old data may still persist in:

- Local clones of developers and build machines.
- Repository forks.
- Server-managed pull request or merge request refs.
- CI/CD caches, mirrors, backups, and runner workspaces.
- Tags, release assets, packages, or artifacts built from old commits.
- Logs, patches, bundles, archives, documentation, or externally stored commit links.
- LFS servers if large files are managed by Git LFS.

Rewriting primary refs does not automatically purge every copy or cache across these systems. When handling secrets, treat every old copy as potentially exposed and revoke secrets at the source. When handling storage size, check retention settings for each system and plan separate cleanup.

## 15. Plan for synchronizing team clones

Old clones have local branches and reflogs pointing to old commits. If users continue pushing old branches, they can reintroduce purged history back onto the remote. Therefore, synchronizing clones is a mandatory part of any rewrite.

### Recommended option: re-clone

For most team members, creating a fresh clone is the simplest and lowest-risk method:

1. Save patches or unpushed commits to keep from the old clone.
2. Close IDEs, Git GUIs, and tools using the old clone.
3. Rename or move the old clone to a temporary archive directory per team policy.
4. Re-clone the repository from the rewritten remote.
5. Restore personal changes by applying patches or cherry-picking appropriate commits onto the new history.
6. Delete the old clone after confirming no work remains to be salvaged and handling backups per policy.

Example:

```bash
git clone https://git.example.com/team/project.git project-clean
```

Do not merge an old branch directly into a new branch, as doing so can stitch old history back in. Transfer only the work changes you need via patches or cherry-pick after reviewing their contents.

### Option: updating an existing clone

Use this only when the user thoroughly understands their local branches, unpushed commits, and working tree. First, save uncommitted work:

```bash
git status -sb
git diff > ../worktree-changes.patch
git diff --cached > ../staged-changes.patch
```

Untracked files must be backed up separately or handled appropriately. Record local commits to keep and create rescue branches if needed. After backing up, fetch the new history:

```bash
git fetch --prune origin
```

Move the working branch to the new ref only after confirming no local commits need to be preserved:

```bash
git switch main
git reset --hard origin/main
```

`reset --hard` discards uncommitted tracked changes in the working tree and index. Do not run it without saving them first. For other local branches, handle each branch against its corresponding ref; delete old branches only after confirming no unique commits are needed.

If you have local commits of your own, create patches or cherry-pick those commits onto a new branch:

```bash
git switch -c feature/work-on-new-history origin/main
git cherry-pick <local-commit-id>
```

Do not merge old local branches containing pre-rewrite history into new branches. That can make old commits reachable again.

### Synchronizing local tags

Old tags may still point to old commits. Inventory tags before updating. After saving any tags that must be kept, delete old local tags and fetch new tags per team instructions:

```bash
git tag --list
git fetch --tags --force origin
```

Fetching tags with force can overwrite existing local tags; use it only after confirming the new remote tags are canonical. If a tag was deleted from the remote, delete the corresponding local tag with `git tag -d <tag-name>` after confirming the old reference is no longer needed. For signed release tags, verify the new signatures per release policy.

## 16. Synchronizing forks, pull requests, and CI

### Forks

A fork is a separate repository and may still hold old history. Fork owners must sync or recreate their forks following the hosting provider's workflow. If sensitive data was exposed, notify fork owners and service administrators to handle copies, caches, and refs that users cannot modify themselves.

### Pull requests / merge requests

Pull requests may reference old commits and platform-managed refs. After a rewrite, some PRs may no longer update properly or may need to be recreated. Check review state, CI checks, comments, and commit links before closing or reopening a PR. Do not assume force-pushing a branch updates all hidden PR refs.

### CI/CD and build caches

Runners may retain old clones or cached objects. After a rewrite:

- Cancel or finish running jobs before allowing new jobs.
- Clear Git workspaces/caches according to the CI platform's procedure.
- Re-clone/fetch from the rewritten remote.
- Update checkout refs, tags, pinned commits, and submodule references if affected.
- Check whether artifacts or packages published from old commits need to be replaced or revoked.

If CI has push permissions, ensure old jobs do not re-run and push pre-rewrite refs back to the remote after the rewrite concludes.

## 17. Submodules, LFS, and external references

Rewriting a parent repository's history can change the commits submodules point to. Check `.gitmodules` and gitlinks in the new commits. If a child repository was also rewritten, update URLs, commit pointers, and synchronized clone instructions.

Git LFS stores binaries on a separate server. Filtering pointers out of Git history does not mean LFS objects have been deleted from LFS storage. If the goal is removing sensitive content or reclaiming LFS storage, use the provider's tools and procedures to inspect/delete LFS objects after ensuring no valid refs still need them.

External systems may store old commit IDs in deployment manifests, release notes, package metadata, tickets, or documentation. Use the commit map generated by filter-repo to cross-reference when updating those references.

## 18. Impact on signatures, tags, and commit identifiers

When commits are recreated, new hashes are computed from new content and parents. This has several consequences:

- Web links to old commits may no longer be valid references.
- Old commit GPG/SSH signatures do not validate for new commits.
- Annotated tags pointing to old objects must be handled; tag signatures may become invalid if tag objects change.
- Commit IDs stored in tickets, documentation, or deployment systems may need updating.
- Local branches and remote-tracking refs in old clones do not automatically switch to new commit IDs.

After rewriting, if the project requires signed commits/tags, re-sign them per procedure and verify the new signatures. Do not copy old signatures onto rewritten commits.

## 19. End-to-end workflow from backup to synchronization

A controlled rewrite can follow this sequence:

### Phase A: Preparation

1. Define the exact content to filter and ref scope.
2. If secrets are involved, revoke/rotate them before other steps.
3. Announce and freeze pushes, merges, tags, and write-capable CI.
4. Inventory refs, forks, PRs, LFS, submodules, and dependent systems.
5. Create a mirror backup and back up LFS objects if present.
6. Create a fresh mirror clone to work in.

### Phase B: Filtering and verification

1. Run `git filter-repo --analyze` if you need to inspect storage usage.
2. Run the filter with reviewed criteria, such as `--path ... --invert-paths` or `--replace-text`.
3. Inspect the commit map, ref map, branches, tags, and diffs.
4. Run `git fsck --full` and a secret scanner.
5. Confirm excluded content no longer exists in advertised refs.
6. Re-add the official remote and verify the URL.

### Phase C: Updating the remote

1. Confirm everyone is still holding off on pushes.
2. Push rewritten branches/tags within the approved scope.
3. Handle deleted refs or platform-managed refs.
4. Create a fresh clone from the remote and verify history after pushing.
5. Confirm the secret scanner and content checks pass on the fresh clone.

### Phase D: Synchronizing users and systems

1. Instruct developers to re-clone or update existing clones per procedure.
2. Rebase/cherry-pick local work to keep; do not merge old history back in.
3. Synchronize forks, pull requests, tags, submodules, and CI caches.
4. Inspect related release assets, packages, and artifacts.
5. Re-enable push permissions once teams confirm synchronization.
6. Handle old backups according to security and retention policies.

## 20. Common errors and resolutions

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `git filter-repo` refuses to run | Repository is not recognized as a fresh clone | Create a fresh mirror clone; only use `--force` when risks are understood and backup exists |
| File still appears in history | File was renamed or had old paths not filtered | List all historical paths to remove and re-run in a new rewrite clone |
| Secret scanner still detects token | Token has variants, different encoding, or resides in unfiltered refs | Revoke token, check all refs, and run scanner across full history |
| Push is rejected | Protected branch/tag or insufficient force-update permissions | Use the host's admin/maintenance workflow; do not bypass protections |
| `origin` remote disappeared after filter | filter-repo removes remote to prevent accidental pushes | Verify URL then re-add the official remote |
| Old clone causes old commits to reappear on remote | Member pushed an unsynchronized branch | Temporarily lock writes, locate the newly pushed old ref, remediate, and remind to sync clones |
| Pull request does not update properly | PR ref is host-managed or base commit changed | Check host tools, update, or recreate the PR |
| LFS storage still holds filtered file | LFS objects live outside the Git object database | Use the provider's LFS object management process |
| Commit/tag signatures are invalid | Objects were recreated | Re-sign commits/tags according to project policy |

## 21. Checklist before concluding a rewrite

- [ ] Secrets revoked/rotated if ever exposed.
- [ ] Required Git and LFS object backups created.
- [ ] Branches, tags, and special refs inventoried.
- [ ] Filter criteria reviewed on a dedicated clone.
- [ ] Commit map/ref map stored per policy.
- [ ] `git fsck --full` reports no missing or corrupt object errors.
- [ ] Secret scanner finds no excluded content in filtered refs.
- [ ] Remote updated during the write-freeze window.
- [ ] Fresh clone from the remote verified.
- [ ] Synchronization planned for developers, forks, PRs, CI, submodules, and artifacts.
- [ ] No old pipelines or clones can push pre-rewrite history.
- [ ] Old backups protected or disposed of per retention policy.

## 22. Practice

Practice on a dedicated test repository without using real tokens or real data:

1. Create a repository with several commits and a mock file `config/demo-secret.txt`.
2. Add commits modifying that file so it appears across multiple snapshots.
3. Clone the repository with `git clone --mirror` into a separate directory.
4. Run `git filter-repo --analyze` and inspect the report.
5. Run `git filter-repo --path config/demo-secret.txt --invert-paths`.
6. Check `git log --all -- config/demo-secret.txt`, `git show-ref`, and `git fsck --full`.
7. Inspect the commit map and ref map generated by the tool.
8. Re-add a test remote if the tool removed `origin`, then push the new history to a test remote.
9. Re-clone the remote and confirm the demo file is gone from the new history.
10. Create an old pre-rewrite clone, try fetching, and observe why local branches still point to old commits; discuss how to re-clone or cherry-pick work to keep.

Do not run force push against a real repository during practice. The goal is to understand commit ID changes and the clone synchronization workflow.

## 23. Self-check questions

1. Why does `git rm` followed by a commit fail to remove a file from earlier commits?
2. When should you use `git filter-repo` instead of `git revert`?
3. Why should you run the filter in a fresh mirror clone and create a backup beforehand?
4. What does `--path` combined with `--invert-paths` mean?
5. If a file was renamed in the past, what must be done to purge all path versions?
6. What types of data does `--replace-text` support and why must secrets still be rotated?
7. Why can filter-repo remove the `origin` remote and what must you verify before re-adding it?
8. How does a force push affect clones, forks, and pull requests?
9. Why is re-cloning usually safer than continuing to use an old clone?
10. How do you bring local commits you need to keep onto the new history without reconnecting old history?

## Conclusion

`git filter-repo` rewrites history by path, content, size, or ref scope. Because commit IDs and related references change, you must create Git/LFS backups, freeze writes, filter in a dedicated clone, verify all refs, and only then update the remote. Afterward, instruct developers to re-clone or migrate personal work via patches/cherry-pick, synchronize forks, pull requests, and CI, and prevent old clones from pushing old history back. For exposed secrets, revoke or rotate them immediately; rewriting history only handles content in filtered refs and does not erase copies outside the repository.

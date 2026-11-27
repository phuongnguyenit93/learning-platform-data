# Committing, Cloning, Pulling, and Pushing in an LFS-Enabled Repository

Git Large File Storage (Git LFS) helps manage large files such as design images, videos, test data, 3D models, or build binaries without putting their entire content into standard Git history. When using LFS, Git still manages commits and branches as before, but large files are replaced by a **pointer file** in Git; the actual content is stored on the LFS server.

Therefore, the workflow includes an extra data-transfer layer: when committing, Git records the pointer; when cloning or pulling, Git LFS downloads the corresponding object to the working tree; when pushing, Git LFS uploads objects before Git updates the branch on the remote. Understanding this exact order prevents situations where commits exist on the remote yet teammates cannot download files, or a branch push succeeds while LFS objects were never uploaded.

## 1. How Does Git LFS Change Large File Storage?

In standard Git, adding a binary file stores its content as a blob in the object database. Subsequent file versions can bloat the repository, especially for hard-to-compress or frequently updated formats like PSD, video, archives, and data files.

Git LFS replaces tracked file content with a small pointer. The pointer contains the information needed to locate the real content on the LFS server, typically including:

- Pointer format specification version.
- SHA-256 object ID of the actual content.
- Content size in bytes.

Example pointer file:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac19622fc3ada9c0fdeadb33f88f367b541f38b891c2a3f6f3f7a1c2b3d4e5
size 84977953
~~~

The hash and size above are illustrative examples. Git commits this pointer as a small text file. The 84,977,953-byte binary content is stored separately in LFS storage.

On checkout, Git LFS uses the pointer to download the object matching that OID, then places the actual content into the working tree. When staging the file again, the Git LFS clean filter generates the corresponding pointer for Git to commit.

## 2. How Do Git and Git LFS Coordinate?

The workflow can be divided into two layers:

| Component | Role |
|---|---|
| Git repository | Stores commits, branches, tags, trees, and pointer files |
| Git LFS local client | Applies clean/smudge filters, manages object cache, and talks to the LFS API |
| LFS server | Stores and serves large file content |
| Git remote | Receives Git refs such as branches and tags |
| Git LFS pre-push hook | Uploads required LFS objects before pushing Git refs |

Simplified diagram:

~~~text
Working tree
  actual binary file
       |
       | git add (LFS clean filter)
       v
Git index / commit
  small pointer file
       |
       | git push
       +--------------------------+
       |                          |
       v                          v
Git remote                    LFS server
  branch/commit                 binary object
       |                          |
       +------------+-------------+
                    |
             Teammate clone/pull
                    |
          Git fetches pointer and LFS object
                    |
                    v
          Working tree has actual binary
~~~

Git and Git LFS have separate endpoints, authentication mechanisms, and storage capacity. A single push can involve uploading objects to the LFS server first and then updating the branch on the Git remote.

## 3. Installing and Initializing Git LFS

Git LFS is an extension installed separately alongside Git. Check whether it is installed:

~~~bash
git lfs version
~~~

If the command is missing, install Git LFS for your operating system or using the installer approved by your organization.

After installing, initialize configuration and hooks:

~~~bash
git lfs install
~~~

This typically configures Git LFS filters in user-level config and installs required hooks, notably the pre-push hook. Usually it only needs to be run once per user account on a machine.

To configure only within the current repository:

~~~bash
git lfs install --local
~~~

You can re-run install to ensure filters and hooks are set up. Check environment details:

~~~bash
git lfs env
~~~

The output shows the Git LFS version, Git paths, LFS endpoint, and related configuration. Do not share raw output verbatim if it exposes internal paths or sensitive environment details.

**Note:** installing Git LFS does not automatically convert all large files to LFS. The repository needs tracking rules in <code>.gitattributes</code>, and files must be staged through the LFS filter.

## 4. Declaring File Types to Track with git lfs track

Inside the repository, choose file patterns to store with LFS. For example, track Photoshop files:

~~~bash
git lfs track "*.psd"
~~~

Also track videos and archives:

~~~bash
git lfs track "*.mp4"
git lfs track "*.zip"
~~~

The <code>git lfs track</code> command updates <code>.gitattributes</code>. Illustrative contents:

~~~gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
~~~

Meaning of the attributes:

- <code>filter=lfs</code>: uses the Git LFS clean/smudge filters.
- <code>diff=lfs</code>: uses the LFS diff mechanism for tracked files.
- <code>merge=lfs</code>: declares the LFS merge driver.
- <code>-text</code>: disables text/line-ending conversion used for text files.

Prefer using <code>git lfs track</code> to update <code>.gitattributes</code> rather than writing rules manually, unless you thoroughly understand Git attributes rules.

### Checking Whether Rules Apply to a File

~~~bash
git check-attr filter diff merge text -- assets/design.psd
~~~

Expected output includes <code>filter: lfs</code>, <code>diff: lfs</code>, <code>merge: lfs</code>, and <code>text: unset</code>.

List files tracked by LFS in the repository:

~~~bash
git lfs ls-files
~~~

This confirms which files are currently managed by Git LFS. Patterns in <code>.gitattributes</code> must be committed with the changes so other machines receive the same rules.

## 5. Staging and Committing Large Files

Suppose the project has <code>assets/product-model.psd</code>. After configuring patterns, stage both the rule and the file:

~~~bash
git add .gitattributes
git add assets/product-model.psd
git status
~~~

When <code>git add</code> runs, the Git LFS clean filter reads the binary content and creates a pointer to put into the index. The file in the working tree remains the actual binary so you can keep opening it in your design application.

Inspect staged changes:

~~~bash
git diff --cached --stat
git diff --cached --summary
git ls-files --stage -- assets/product-model.psd
~~~

To view the pointer currently in the index:

~~~bash
git show :assets/product-model.psd
~~~

If the file has been committed, view the pointer in the commit:

~~~bash
git show HEAD:assets/product-model.psd
~~~

The output is typically a few pointer lines rather than binary data. This is normal when the file is stored via LFS.

After verifying:

~~~bash
git commit -m "Add product model asset"
~~~

The Git commit only stores the pointer and changes to <code>.gitattributes</code>. The actual LFS object may already be in the local LFS cache, though it is not necessarily uploaded to the server yet.

### Why Must .gitattributes Be Committed?

<code>.gitattributes</code> is part of the repository. If you only configure LFS on a personal machine without committing this file, other team members may not know which files should go through LFS.

Include <code>.gitattributes</code> in the same commit or in a shared configuration commit. This ensures cloning, checking out, diffing, and staging on other machines apply the same rules.

## 6. What Happens When Cloning an LFS Repository?

When Git LFS is installed and configured before cloning, Git normally invokes the smudge filter during checkout. The filter reads the pointer, downloads the matching object from the LFS server, and writes the real file into the working tree.

Typical clone workflow:

~~~bash
git lfs install
git clone https://example.com/team/design-assets.git
cd design-assets
git lfs ls-files
~~~

After a successful clone, LFS files required for the checked-out branch typically contain their actual content. Verify by opening a file or checking its size in the working tree.

### If Cloned Before Installing Git LFS

If Git LFS was not installed/configured when cloning, Git may check out pointers as text files. After installing LFS, run:

~~~bash
git lfs install
git lfs pull
~~~

<code>git lfs pull</code> fetches the LFS objects needed for the current ref and checks them out into the working tree.

If files remain pointers, check filter configuration, skip-smudge environment variables, LFS endpoint permissions, and command logs.

### Skipping LFS Object Downloads on Clone

Some environments only need source code for quick inspection and do not need large assets yet. You can skip smudging on clone:

~~~bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://example.com/team/design-assets.git
cd design-assets
~~~

At this point, LFS files may appear as pointers in the working tree. When you need the actual content:

~~~bash
git lfs pull
~~~

In PowerShell, you can set the environment variable for the current terminal session:

~~~powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://example.com/team/design-assets.git
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
Set-Location design-assets
git lfs pull
~~~

The environment variable only skips automatic downloads; it does not delete pointers or objects from the repository. Remember to unset it before checkout operations where you want LFS to download files automatically.

## 7. Distinguishing git lfs fetch, checkout, and pull

The three commands are related but serve different purposes:

| Command | Effect |
|---|---|
| <code>git lfs fetch</code> | Downloads LFS objects into the local cache without updating files in the working tree |
| <code>git lfs checkout</code> | Populates the working tree with objects already in the cache for matching LFS files |
| <code>git lfs pull</code> | Combines fetch and checkout for the current ref |

Example downloading objects from remote origin for branch main:

~~~bash
git lfs fetch origin main
~~~

Then, once objects are in the cache, you can check them out:

~~~bash
git lfs checkout
~~~

Or run the commonly used combined command:

~~~bash
git lfs pull
~~~

<code>git lfs fetch</code> is useful when pre-fetching objects in a separate step, such as warming a cache for a build job. <code>git lfs pull</code> is more convenient when you want real files immediately in the working tree.

### Fetch Is Not the Same as Git fetch

<code>git fetch origin</code> retrieves standard Git commits, trees, and blobs and updates remote-tracking refs per Git configuration. It does not mean all required LFS objects have been downloaded into the working tree.

<code>git lfs fetch origin main</code> downloads LFS objects for the specified ref without automatically updating local Git branches. The two commands operate on two different data layers.

## 8. Pulling New Changes from a Remote

When teammates push new commits containing LFS pointers, you need to fetch both the Git changes and the corresponding LFS objects.

Typical workflow:

~~~bash
git switch main
git pull --ff-only
git lfs pull
~~~

<code>git pull</code> fetches commits and integrates them into the current branch according to your pull config. During checkout or merge, Git LFS may download objects automatically via configured filters and hooks. Explicitly running <code>git lfs pull</code> ensures LFS files needed for the current ref are downloaded and checked out, especially when clone/pull skipped smudge or hooks did not run.

If you only want to fetch objects first without changing the working tree:

~~~bash
git lfs fetch origin main
~~~

Later, when you need the files:

~~~bash
git lfs checkout
~~~

### Pulling with Local Changes

Before pulling, inspect:

~~~bash
git status
git lfs status
~~~

If you are editing a large file, save or commit your changes first. Git LFS manages file content via filters, but merge conflicts on binary files usually cannot be auto-resolved like text files. The team must decide which version to keep or use a specialized tool to merge content.

## 9. Pushing a Branch Containing LFS Files

When commits contain LFS pointers, pushing the branch requires uploading the corresponding objects to the LFS server. <code>git lfs install</code> typically installs a pre-push hook to handle this automatically.

Example:

~~~bash
git status
git lfs status
git push -u origin feature/design-assets
~~~

General workflow:

1. Git determines which commits/refs will be pushed.
2. The Git LFS pre-push hook finds LFS objects referenced by the commits being sent.
3. Git LFS uploads missing objects to the LFS server.
4. Once the upload succeeds, Git proceeds to update the branch on the Git remote.

Consequently, pushing can take longer when there are large files or many new objects. During upload, do not close the terminal or disconnect before confirming completion.

### Checking Before Pushing

~~~bash
git lfs status
git lfs ls-files
git status
~~~

<code>git lfs status</code> displays LFS objects related to local changes and their push status. If an expected file does not appear in the LFS list, inspect <code>.gitattributes</code> and filters before pushing.

### Uploading LFS Objects Manually

If the pre-push hook did not run or you need to upload objects beforehand, you can run:

~~~bash
git lfs push origin feature/design-assets
~~~

Then push the Git branch:

~~~bash
git push origin feature/design-assets
~~~

<code>git lfs push</code> uploads LFS objects referenced by the specified ref. Do not confuse it with <code>git push</code>: the former handles LFS objects, while the latter updates Git branches/tags.

Avoid bypassing the pre-push hook or setting <code>GIT_LFS_SKIP_PUSH=1</code> in standard workflows. If a Git branch is updated while its objects are missing from the LFS server, others will receive pointers and fail to download actual content.

## 10. LFS Server and Authentication

The Git remote and the LFS endpoint can be two separate service addresses. For example, the remote might use SSH for Git transport while the LFS client uses HTTPS and the Batch API to upload/download objects.

Check which endpoint Git LFS is using:

~~~bash
git lfs env
git remote -v
~~~

If clone/pull/push reports authentication errors, check:

- Does the account or token have read permission for LFS objects?
- Does the pusher have write permission for LFS objects?
- Is the credential helper supplying the right credentials?
- Does the LFS endpoint match the repository or organization?
- Has the token expired or does it lack required scopes?

Some platforms share the same credentials for Git and LFS, while others use separate credentials or tokens. Never assume an SSH key used for Git push automatically grants access to the LFS endpoint.

If a repository configures a custom LFS endpoint via <code>.lfsconfig</code>, review that file as data-source configuration. Never place tokens, passwords, or secrets inside <code>.lfsconfig</code> or commits.

## 11. Working with Branches and Pull Requests / Merge Requests

In branch-based workflows, each branch can add or update LFS objects. Example:

~~~bash
git switch -c feature/new-texture
git lfs track "*.tif"
git add .gitattributes
git add assets/textures/stone.tif
git commit -m "Add stone texture"
git push -u origin feature/new-texture
~~~

Then open a Pull Request / Merge Request like any normal Git change. Reviewers can inspect pointers, metadata diffs, and commit history; actual binary content must be inspected using suitable tools.

Points to check during review:

- Verify <code>.gitattributes</code> has accurate patterns.
- Verify new files are actually stored as LFS pointers.
- Confirm LFS objects have been uploaded so CI and reviewers can download them.
- For binary files, describe the content, source, and how it was tested in the PR/MR.
- If multiple people edit the same binary, agree on an owner for updates to avoid overwriting versions.

When merging a branch, Git integrates pointer files and <code>.gitattributes</code>; the LFS server already stores objects by OID. Subsequent clones download objects matching the pointers in the new commit.

## 12. Are LFS Files Downloaded Automatically in CI/CD?

CI runners need both the Git LFS client and access to the LFS server if jobs consume large file content.

A general workflow:

~~~bash
git lfs install
git clone https://example.com/team/game-assets.git
cd game-assets
git lfs pull
./gradlew test
~~~

If your pipeline uses a platform-provided checkout step, enable its LFS support option or run the corresponding commands after checkout. Option names vary by CI system.

If a job only builds code that does not need large assets, you can skip smudge to save time:

~~~bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://example.com/team/app.git
~~~

Then fetch only required files in jobs that actually use them. However, tests or builds requiring binaries will fail if <code>git lfs pull</code> or appropriate object fetching has not been called.

### LFS Caching in CI

Git LFS stores objects in a local cache. Runners can reuse caches across jobs if supported by the platform and configured safely.

Ensure that:

- Caches are keyed appropriately by repository or LFS object identity.
- Jobs do not consume caches from untrusted sources.
- On a cache miss, the runner still has permission to download objects from the LFS server.
- Local caches are not treated as the authoritative archive of assets.

The LFS server remains the shared source of truth; caches only reduce repeated transfers.

## 13. Common Errors When Cloning, Pulling, and Pushing

| Symptom | Possible Cause | How to Check and Resolve |
|---|---|---|
| Files in working tree only show a few pointer lines | Smudge filter skipped, Git LFS not installed, or object download failed | Run <code>git lfs version</code>, <code>git lfs env</code>, then <code>git lfs pull</code> |
| Clone succeeds but opening LFS files fails | LFS objects not downloaded or missing access permission | Verify endpoint, authentication, and run <code>git lfs pull</code> |
| Branch push reports missing LFS objects | Pre-push hook did not run or objects were not uploaded | Check <code>git lfs install</code>, <code>git lfs status</code>, run <code>git lfs push origin &lt;branch&gt;</code> |
| Git reports file exceeds size limit | File was committed as a normal Git blob | Check <code>git check-attr</code>, <code>.gitattributes</code>; if already in history, consider migrating |
| <code>git lfs track</code> ran but file is still a Git blob | File was not re-staged after adding rule or pattern did not match | Run <code>git check-attr filter -- &lt;file&gt;</code>, re-stage file, and verify pointer |
| HTTP 401/403 when downloading LFS | Credentials lack permission or token expired | Refresh credentials and verify LFS read/write permissions |
| LFS endpoint returns 404 | Wrong endpoint, object not uploaded, or server does not hold object | Check <code>git lfs env</code>, remote, and object status |
| Pull finished but file still contains pointer | Skip-smudge still enabled or checkout filter inactive | Unset skip-smudge variable and run <code>git lfs pull</code> |
| Push is very slow | Many large objects or low bandwidth | Check <code>git lfs status</code>, file sizes, and server limits |
| Server reports quota or bandwidth exceeded | Storage or transfer quota exhausted | Check service quotas and team policy |

When errors occur, separate Git ref issues from LFS object issues. A Git branch can exist normally while its corresponding LFS object cannot be downloaded yet.

## 14. Files Committed Before Starting to Use LFS

<code>git lfs track</code> only sets rules for subsequent staging and commits. It does not automatically convert existing history to LFS.

If a large file was already committed as a standard Git blob, earlier commits still hold that blob. To convert history, Git LFS provides the migrate command:

~~~bash
git lfs migrate import --include="*.psd"
~~~

This operation can rewrite commit history, change commit hashes, and require a force push. Only perform it after:

1. Backing up or creating a backup clone.
2. Agreeing on the file scope to migrate.
3. Notifying everyone using the repository.
4. Verifying the outcome in a test repository.
5. Planning how teammates will re-clone or sync with the rewritten history.

For widely shared repositories, do not run migrate unilaterally on the main branch. If you only need LFS management starting from the next version, add the rule and re-commit the file via LFS; old history will retain the original blobs.

## 15. Managing Storage and Cache

LFS shrinks regular Git objects, but does not eliminate storage costs. Actual content still consumes space on the LFS server and may count toward storage quotas or bandwidth.

Key practices:

- Only put appropriate files into LFS: large binaries, hard-to-diff assets, or frequently changing files.
- Avoid tracking everything with an overly broad pattern if the repository has many small files.
- Deleting a file from the working tree and committing does not necessarily delete the LFS object from the server.
- Deleting a branch or tag also does not mean the LFS object is immediately deleted; garbage collection policies belong to the server.
- Maintain backups of critical assets per project policy.

Inspect local LFS info and files:

~~~bash
git lfs env
git lfs ls-files
~~~

Clean up unneeded objects from the local cache with:

~~~bash
git lfs prune
~~~

<code>git lfs prune</code> only cleans the local LFS cache according to the tool's safety rules; it does not delete objects on the LFS server. However, after pruning, if you need an old file again, your machine may have to download the object from the server. Ensure important objects exist on the server or in backups before pruning cache.

## 16. Verifying LFS Object Integrity

If you suspect an object is missing or corrupted, verify with:

~~~bash
git lfs fsck
~~~

This checks consistency between pointers and related LFS objects in the repository. If errors appear, read the output to identify which pointer or object does not match.

You can list LFS files:

~~~bash
git lfs ls-files
~~~

Compare the OID and size in the pointer with the locally stored object. Never manually edit an OID inside a pointer to "make errors go away"; the pointer must match the hash of the actual content.

If an object is missing locally but still exists on the server, fetch or pull it again. If the object is absent from the server and no longer in any cache or backup, you must recover the original from its creator or another storage source.

## 17. Sample Workflow from Creating a Commit to Teammate Cloning

Suppose a team manages 3D models and textures in repository <code>game-assets</code>.

### Author Creating Changes

~~~bash
git lfs install
git lfs track "*.blend"
git lfs track "*.tif"

git add .gitattributes
git add assets/character.blend assets/texture.tif
git lfs status
git commit -m "Add character model and texture"
git push -u origin feature/character-assets
~~~

Git commits pointers and <code>.gitattributes</code>. On push, the pre-push hook uploads required objects to the LFS server, and Git then updates the branch.

### Another Member Cloning and Retrieving Content

~~~bash
git lfs install
git clone https://example.com/team/game-assets.git
cd game-assets
git lfs ls-files
~~~

If the clone downloaded LFS objects, files in the working tree contain their real content. If the clone skipped smudge or objects were not downloaded:

~~~bash
git lfs pull
~~~

### Syncing New Commits

When new changes land on main:

~~~bash
git switch main
git pull --ff-only
git lfs pull
~~~

Inspect files and run required build/test tools. If files remain pointers, review LFS configuration and permissions.

## 18. Pre-Commit and Pre-Push Checklist

- [ ] Git LFS is installed and <code>git lfs install</code> has been run.
- [ ] Patterns for files to track are present in <code>.gitattributes</code>.
- [ ] <code>git check-attr filter -- &lt;file&gt;</code> returns <code>lfs</code>.
- [ ] Files were staged after adding the LFS rules.
- [ ] <code>git lfs ls-files</code> lists the expected files.
- [ ] Pointers in the index/commit have valid OIDs and sizes.
- [ ] <code>git lfs status</code> reports no missing objects needing push.
- [ ] The pre-push hook is not bypassed.
- [ ] The LFS endpoint is reachable and the account has write access.
- [ ] CI and teammates have permission to download objects after the branch is pushed.
- [ ] For previously committed large files, has the team decided whether history migration is needed or LFS applies only from new commits onward?

## 19. Key Points to Remember

- Git LFS stores large file content on an LFS server; Git commits small pointer files.
- <code>git lfs track</code> creates/updates <code>.gitattributes</code>; commit this file to share rules.
- <code>git add</code> places pointers into the index via the clean filter; the working tree keeps the real binary.
- <code>git commit</code> records the pointer, which does not mean the object has been uploaded yet.
- <code>git lfs install</code> configures filters and hooks; the pre-push hook normally uploads LFS objects before Git updates branches.
- Clone/pull typically downloads objects via the smudge filter; <code>git lfs pull</code> downloads and checks out objects for the current ref.
- <code>git lfs fetch</code> downloads objects to the cache; <code>git lfs checkout</code> writes cached objects to the working tree.
- Git fetch/push and LFS fetch/push handle two distinct data layers.
- If you see pointers in the working tree, check Git LFS installation, skip-smudge settings, endpoint, and permissions.
- <code>git lfs track</code> does not convert old history; migration can rewrite commits and requires coordination.
- LFS still incurs quotas, bandwidth, and storage costs; local cache does not replace the server or backups.

When working with an LFS-enabled repository, remember the two paired parts of the workflow: Git manages pointers and history, while Git LFS manages large file content. Committing accurate pointers, uploading objects on push, and downloading objects on clone/pull ensures every team member receives the same version of both source code and assets.

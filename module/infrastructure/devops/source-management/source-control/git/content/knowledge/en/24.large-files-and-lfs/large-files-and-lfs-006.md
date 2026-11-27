# Checking Tracked Files and Status with git lfs ls-files and status

Git LFS (Large File Storage) helps manage large files such as design images, videos, 3D models, training datasets, or binary packages. Instead of storing the entire large content as a Git blob in repository history, Git stores a small pointer file containing an identifier and size; the actual content is stored in the LFS object store and transferred through an LFS server.

When working with Git LFS, you need to answer questions such as: which files are managed by LFS, whether the current version is a pointer or full content, which files have changed and need to be committed, and which objects still need to be uploaded on push? Two key commands for inspection are `git lfs ls-files` and `git lfs status`.

This lesson focuses on reading the output of both commands, selecting inspection scopes, distinguishing LFS status from standard Git status, and investigating when a large file has not been downloaded or uploaded yet.

## 1. What Does Git LFS Store in a Repository?

### 1.1. Pointer Files and Actual Content

When a path is managed by Git LFS, Git typically stores a pointer file like:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
size 52428800
~~~

This is an illustrative example. The pointer contains:

- **version:** pointer format version.
- **oid:** SHA-256 hash identifying the LFS content.
- **size:** size of the actual content in bytes.

The actual binary content is stored in the local LFS store and synced with the LFS server. Git commits the pointer as a small blob, while Git LFS handles downloading and uploading the corresponding large content.

### 1.2. Clean Filter and Smudge Filter

Git LFS integrates with Git through filters:

- **clean:** when adding a file to the index, the filter converts large content into a pointer for Git to store in commits.
- **smudge:** on checkout, the filter reads the pointer and locates or downloads the actual content to place into the working tree.

Git LFS also installs a `pre-push` hook to upload required LFS objects before Git updates the branch on the remote. If the LFS upload fails, the push operation is typically aborted to prevent updating commits without their corresponding LFS data.

Consequently, the same path can take different forms depending on location:

| Location | Typically observed content |
| --- | --- |
| Git commit | Pointer file |
| Git index | Pointer blob prepared for commit |
| Working tree after successful checkout | Actual file content |
| Working tree when smudge is skipped or object not downloaded | Pointer file |

This is why inspecting LFS requires checking both Git and LFS object state.

### 1.3. Verifying Git LFS Is Installed

Check version:

~~~bash
git lfs version
~~~

View the Git LFS environment:

~~~bash
git lfs env
~~~

Configure filters and hooks for the current user:

~~~bash
git lfs install
~~~

Typically you only need to run `git lfs install` once per user account on a machine. It configures clean/smudge filters and installs the pre-push hook for the current repository if invoked inside a repository.

If the repository uses `core.hooksPath` or custom hooks, inspect the configuration to ensure Git LFS hooks are integrated without overwriting other hooks. Do not delete existing hooks simply to make LFS work.

## 2. Identifying Paths Configured to Be Tracked by LFS

### 2.1. Viewing Rules in .gitattributes

Git LFS uses Git attributes to decide which paths pass through the LFS filter. Running:

~~~bash
git lfs track
~~~

displays currently configured patterns. For example, if the repository tracks PSD and video files:

~~~gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
~~~

These rules are typically stored in `.gitattributes` at the repository root or in subdirectories.

Add new patterns:

~~~bash
git lfs track "*.psd"
git lfs track "*.mp4"
~~~

Then commit `.gitattributes` changes alongside related files:

~~~bash
git add .gitattributes
git add design/banner.psd
git commit -m "Track design assets with Git LFS"
~~~

`git lfs track` updates attribute rules. It does not automatically convert all old versions in Git history to LFS.

### 2.2. Checking Attributes of a Path

Use:

~~~bash
git check-attr filter diff merge -- design/banner.psd
~~~

If the path is configured properly, the output typically shows `filter`, `diff`, and `merge` set to `lfs`.

This command checks the attribute rules applied to a path. It does not prove the current content is already stored as an LFS pointer in commits or that the object has been uploaded.

### 2.3. Patterns Do Not Mean Files Are Already Converted

A common situation occurs when you add a pattern to `.gitattributes` after files are already tracked by Git as normal blobs. Merely adding a new rule does not automatically convert existing blobs into pointers.

For already-tracked files, renormalize the index according to the new attributes:

~~~bash
git add --renormalize .
git status
git diff --cached
~~~

After reviewing the diff, commit the conversion. If you want to convert old history to LFS as well, that is a separate migration operation that can rewrite repository history; it cannot be accomplished with `git lfs track` or `git add` alone.

## 3. Listing LFS Files with git lfs ls-files

### 3.1. Listing LFS Files in the Current Branch

Basic command:

~~~bash
git lfs ls-files
~~~

Without a revision argument, Git LFS scans the currently checked-out branch tree and lists paths stored as LFS in that revision.

Illustrative output example:

~~~text
3c2f7aedfb * design/banner.psd
a8149c30de - assets/model.bin
~~~

Each line typically contains the LFS identifier, a status marker, and the path.

- An asterisk `*` after the OID indicates a full object.
- A hyphen `-` indicates an LFS pointer.

By default, the OID may be abbreviated for readability. Use `--long` if you need the full SHA-256 hash.

**Note:** the `*` and `-` markers are display status indicators from the command, not cryptographic integrity checks. How the command determines whether content is checked out relies on working tree state; in some situations, this marker does not prove the local object cache has complete content or a valid hash. When object verification is needed, use `git lfs fsck` and appropriate checks.

### 3.2. Displaying Full OIDs with --long

~~~bash
git lfs ls-files --long
~~~

By default the command may shorten the OID for brevity. `--long` displays the full 64-character OID.

Use this when you need to:

- Cross-reference a pointer with an object in LFS storage.
- Compare two versions of a large file.
- Record identifiers in an investigation report.
- Pinpoint the exact LFS content referenced by a commit.

An OID is a content identifier, not a human-friendly version name. To find which commit a version belongs to, combine it with `git log`, `git show`, or a specific revision.

### 3.3. Displaying Sizes with --size

~~~bash
git lfs ls-files --size
~~~

The `--size` option appends the object size at the end of each line. This is useful when verifying whether the repository is managing the expected large assets.

The size in the listing comes from LFS object metadata. It does not indicate whether the object was uploaded successfully or exists in the local cache.

### 3.4. Displaying Only Filenames with --name-only

~~~bash
git lfs ls-files --name-only
~~~

Use this when you only need a list of paths, for instance to check directory naming conventions or audit asset scope.

This option omits the OID and marker, so it is unsuitable when you need to distinguish pointers from full objects.

### 3.5. Viewing Debug Information

~~~bash
git lfs ls-files --debug
~~~

`--debug` outputs extra details for manual troubleshooting. The debug output format may vary across Git LFS versions; do not rely on it as a stable interface for automated scripts.

### 3.6. Filtering by Path

You can view only paths matching a pattern:

~~~bash
git lfs ls-files --include="assets/**"
~~~

Exclude a group:

~~~bash
git lfs ls-files --exclude="assets/archive/**"
~~~

Or combine them:

~~~bash
git lfs ls-files --include="assets/**" --exclude="assets/archive/**"
~~~

Include/exclude patterns help narrow listings in large repositories. Pattern syntax follows Git LFS path filtering rules; quote patterns so the shell does not expand wildcards before Git LFS receives the argument.

## 4. Inspecting History and Deleted Files with ls-files

### 4.1. Listing LFS Files in a Revision

You can pass a branch name, tag, or commit:

~~~bash
git lfs ls-files main
git lfs ls-files v2.0.0
git lfs ls-files 4a1b2c3
~~~

This is useful when checking which LFS objects are referenced by a specific release version or branch.

### 4.2. Comparing Two Revisions

Syntax:

~~~bash
git lfs ls-files <old-ref> <new-ref>
~~~

Example:

~~~bash
git lfs ls-files main feature/new-assets
~~~

This lists LFS files that changed between the two revisions. Deleted paths are not listed in this two-ref comparison mode. If you need to investigate deleted files, use history options like `--all` or `--deleted` depending on your goal.

### 4.3. Viewing Full History with --all

~~~bash
git lfs ls-files --all
~~~

`--all` inspects the entire repository history rather than only the tree of HEAD or a specified revision. Results can include older LFS versions no longer present in the current tree.

This is useful for:

- Finding LFS files that were committed and later deleted.
- Investigating why a repository still retains old LFS objects.
- Auditing history before a migration.
- Locating asset versions referenced by an older branch or tag.

Repositories with long histories can return many lines. Combine `--include` or `--exclude` when inspecting only a subset of paths.

### 4.4. Including Deleted Objects with --deleted

~~~bash
git lfs ls-files --deleted main
~~~

The `--deleted` option shows history for the specified revision, including objects deleted from the current tree. Use it when tracking down an asset no longer in the latest version that was previously stored with LFS.

Do not confuse `--deleted` with restoring files. The command only lists historical metadata; to recover content, identify the relevant commit or pointer and fetch/check out the corresponding object.

## 5. Reading Status with git lfs status

### 5.1. What Does This Command Check?

Run:

~~~bash
git lfs status
~~~

This displays the status of LFS objects in the working tree. It groups paths into three main categories:

1. **Not yet pushed to the LFS server:** objects that can be uploaded when running `git push`.
2. **Differences between index and HEAD:** objects queued for the next commit.
3. **Differences between working tree and index:** modified files that can be staged with `git add`.

The command must be run inside a non-bare repository.

### 5.2. Example Output

Illustrative output may look like:

~~~text
On branch feature/design-refresh

Objects to be pushed to origin/feature/design-refresh:

    design/banner.psd (sha256:...)

Objects to be committed:

    design/banner.psd (sha256:...)

Objects not staged for commit:

    assets/model.bin (sha256:...)
~~~

Section headings and exact formatting may vary by Git LFS version and repository state. Focus on the meaning:

- **Objects to be pushed:** LFS objects still needing upload to the LFS server for commits to be pushed.
- **Objects to be committed:** LFS pointer changes already in the index waiting to be recorded in a commit.
- **Objects not staged for commit:** LFS changes in the working tree not yet added to the index.

If a category has no entries, Git LFS may omit paths under that section.

### 5.3. Distinguishing git status from git lfs status

The two commands complement each other:

| Command | Focus | Question |
| --- | --- | --- |
| `git status` | Standard Git state: branch, staged, unstaged, untracked | Which paths have changed in the repository? |
| `git lfs status` | LFS object state: to commit, to stage, to upload | Which LFS objects are pending at each stage? |

An LFS file can appear in `git status` as a modified file, while `git lfs status` shows whether the corresponding object still needs to be uploaded or staged.

Do not rely on only one of the two commands when troubleshooting LFS issues.

### 5.4. Step-by-Step Status Checking

Before committing:

~~~bash
git status
git lfs status
git diff
git diff --cached
~~~

If there are unstaged changes, stage the file:

~~~bash
git add assets/model.bin
~~~

Check again:

~~~bash
git status
git lfs status
git diff --cached
~~~

After committing:

~~~bash
git commit -m "Update 3D model asset"
git lfs status
~~~

After pushing:

~~~bash
git push origin feature/design-refresh
git lfs status
~~~

If the pre-push hook is working, Git LFS uploads the required objects before updating the Git branch on the remote. After a successful push, the objects-to-be-pushed section typically disappears. However, `git lfs status` does not replace server-side confirmation or object integrity checks.

## 6. Using Structured Output for Scripts

### 6.1. Porcelain Output

`git lfs status` supports:

~~~bash
git lfs status --porcelain
~~~

This option produces output easier to parse in scripts than human-oriented formatting. When writing automation, check the format for the Git LFS version installed on your system and avoid parsing normal output by splitting strings arbitrarily.

### 6.2. JSON Output

You can request JSON:

~~~bash
git lfs status --json
~~~

JSON works well when another tool needs structured status data. If combined with `--porcelain`, porcelain mode takes precedence.

For `git lfs ls-files`, you can use:

~~~bash
git lfs ls-files --json
~~~

When `--debug` is used alongside `--json`, debug takes precedence according to command documentation. When consuming JSON in scripts, check the schema against the installed version and handle command failures or repositories without LFS files.

Do not treat JSON output as proof that objects were uploaded or hash-verified; it merely serializes the information gathered by the command.

## 7. Distinguishing Listed Status from Object Integrity

### 7.1. ls-files Is Not a Checksum Verification Command

`git lfs ls-files` identifies LFS paths, OIDs, sizes, and full-object/pointer markers. It does not replace verifying object content.

In particular, the `*` marker should not be interpreted as a guarantee that the object in the local cache definitely exists and has a valid SHA-256 content hash. The marker primarily reflects how Git LFS sees the file checked out in the working tree; in certain skip-smudge or cache scenarios, the display may not fully reflect object storage state.

### 7.2. Using fsck to Verify

Check LFS objects in HEAD:

~~~bash
git lfs fsck
~~~

Verify referenced objects and their presence on disk:

~~~bash
git lfs fsck --objects
~~~

Verify pointer formatting and whether files matching LFS attributes are properly stored as pointers:

~~~bash
git lfs fsck --pointers
~~~

You can specify a revision or commit range:

~~~bash
git lfs fsck --pointers main..HEAD
~~~

`git lfs fsck` verifies object/pointer consistency within the specified scope. When corrupted objects are found, Git LFS may move damaged objects into `.git/lfs/bad`; read the help output and consider `--dry-run` if you want to check without moving objects.

### 7.3. Inspecting Pointer Content in a Commit

You can inspect what Git stores for a path:

~~~bash
git show HEAD:design/banner.psd
~~~

If the file is stored with LFS, the output is typically pointer text rather than actual PSD data.

You can compare the pointer's OID and size against `git lfs ls-files --long --size`. If the pointer is malformed or a file intended for LFS was stored as a regular blob, inspect `.gitattributes`, filters, and the staging process.

## 8. Troubleshooting When the Working Tree Shows a Pointer Instead of the Real File

### 8.1. Recognizing a Pointer File

If opening what should be an image, video, or large asset shows content like:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:...
size ...
~~~

then the working tree contains a pointer instead of the actual content.

Possible causes:

- Git LFS is not installed or `git lfs install` has not been run.
- Clone or checkout was performed with skip smudge enabled.
- LFS objects have not been downloaded yet.
- The LFS server is unreachable or the user lacks permission.
- Hooks/filters are misconfigured or overridden by another tool.

### 8.2. Checking Installation and Status

~~~bash
git lfs version
git lfs env
git lfs ls-files
git lfs status
git status --short
~~~

If filters/hooks are not installed:

~~~bash
git lfs install
~~~

Download objects and update the working tree for the current ref:

~~~bash
git lfs pull
~~~

`git lfs pull` typically fetches LFS objects for the current ref and checks out the needed content into the working tree. It does not create a new commit.

If objects are already downloaded yet the working tree still has pointers, re-check out the LFS content:

~~~bash
git lfs checkout
~~~

Before running it, confirm the working tree has no local changes you need to preserve. Checkout can overwrite LFS file contents in the working tree.

### 8.3. When Cloning with Skip Smudge

Some environments intentionally disable automatic LFS downloads during clone to save time or memory. For example, setting `GIT_LFS_SKIP_SMUDGE=1` causes Git LFS to skip converting pointers to actual content during checkout.

After cloning, download content on demand:

~~~bash
git lfs pull
~~~

If you only need specific paths, use the include/exclude options supported by fetch/pull to limit scope. Check help for your installed Git LFS version:

~~~bash
git lfs pull -h
~~~

Do not mistake a pointer file for a corrupted file. A pointer can be the expected state when smudge is disabled or objects have not been checked out yet.

## 9. Troubleshooting When LFS Objects Have Not Been Uploaded

### 9.1. Checking the Objects to Be Pushed Group

After committing an LFS file, run:

~~~bash
git lfs status
~~~

If the file still appears under objects to be pushed, check remote and upstream settings:

~~~bash
git remote -v
git branch -vv
git status -sb
~~~

Confirm you are pushing to the right remote and branch. Git remote URLs and LFS endpoints can be configured separately; inspect the LFS environment:

~~~bash
git lfs env
~~~

### 9.2. Checking the pre-push Hook

Git LFS uses the pre-push hook to upload objects before Git updates refs on the remote. If the hook is missing, overwritten, or bypassed, Git commits may be pushed without their LFS objects uploaded.

Check the hook path setting:

~~~bash
git config --show-origin --get core.hooksPath
~~~

If `core.hooksPath` is unset, hooks normally live in the repository's Git directory. You can reinstall hooks/filters with:

~~~bash
git lfs install
~~~

If the repository uses custom hooks, integrate the Git LFS logic with existing hooks according to your team's guidelines; do not overwrite hooks performing security or release checks.

### 9.3. Pushing and Re-Verifying

Perform the push following your workflow:

~~~bash
git push origin main
~~~

Then verify:

~~~bash
git lfs status
git status -sb
~~~

If upload fails, read error messages regarding authentication, quotas, size limits, endpoints, or network connectivity. Do not rely solely on the Git branch appearing on the remote to conclude LFS objects are available.

You can use `git lfs push --dry-run` to preview objects that would be pushed without actually uploading:

~~~bash
git lfs push --dry-run origin main
~~~

Dry-run previews the object scope, though it does not guarantee the server will accept the upload when executed for real.

## 10. Pre-Commit and Post-Commit LFS Verification Workflow

Suppose you update `assets/scene.fbx`.

**Step 1 — Confirm the path is tracked**

~~~bash
git check-attr filter diff merge -- assets/scene.fbx
git lfs track
~~~

**Step 2 — View the LFS listing**

~~~bash
git lfs ls-files --long --size
~~~

Verify the file appears and its OID/size are appropriate.

**Step 3 — Check changes**

~~~bash
git status
git lfs status
git diff
git diff --cached
~~~

**Step 4 — Stage and review again**

~~~bash
git add assets/scene.fbx
git status
git lfs status
git diff --cached
~~~

**Step 5 — Commit**

~~~bash
git commit -m "Update environment scene"
~~~

**Step 6 — Check objects needing upload**

~~~bash
git lfs status
git lfs push --dry-run origin main
~~~

**Step 7 — Push**

~~~bash
git push origin main
~~~

**Step 8 — Verify after pushing**

~~~bash
git lfs status
git lfs ls-files --long --size
git status -sb
~~~

If local object integrity verification is needed:

~~~bash
git lfs fsck --objects
~~~

This sequence clearly distinguishes whether a file is configured for LFS, whether the pointer is committed, whether objects still need upload, and whether local content passes verification.

## 11. Quick Reference Table

| Need | Command |
| --- | --- |
| Check Git LFS version | `git lfs version` |
| View LFS environment | `git lfs env` |
| List LFS files on current branch | `git lfs ls-files` |
| Show full OIDs | `git lfs ls-files --long` |
| Show sizes | `git lfs ls-files --size` |
| Show paths only | `git lfs ls-files --name-only` |
| View LFS history | `git lfs ls-files --all` |
| View deleted objects | `git lfs ls-files --deleted` |
| Compare two revisions | `git lfs ls-files main feature/assets` |
| Check LFS status | `git lfs status` |
| Script-friendly output | `git lfs status --porcelain` |
| JSON output | `git lfs status --json` |
| Check file attributes | `git check-attr filter diff merge -- path/to/file` |
| Download LFS objects and check out | `git lfs pull` |
| Check out downloaded objects | `git lfs checkout` |
| Verify local objects | `git lfs fsck --objects` |
| Verify pointers | `git lfs fsck --pointers` |
| Preview objects to push | `git lfs push --dry-run origin main` |

## 12. Summary

`git lfs ls-files` answers which LFS files the repository references, along with their OIDs and sizes, and can expand scope across revisions or full history. `git lfs status` shows which objects still need to be uploaded, which changes are staged to commit, and which changes remain in the working tree.

The two commands do not replace each other: `ls-files` focuses on listing and looking up LFS paths, whereas `status` focuses on change state across Git stages. Combining them with `git status`, `git check-attr`, `git lfs pull`, and `git lfs fsck` helps distinguish tracking configuration, pointers, checked-out content, objects to commit, and objects to upload.

When investigating, identify the exact path and revision, inspect index/working tree state, verify local objects, and only then draw conclusions about server upload state. Doing so enables teams to manage large files with control while keeping Git history compact and collaborative.

## References

- [git lfs ls-files — Git LFS reference](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-ls-files.adoc)
- [git lfs status — Git LFS reference](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-status.adoc)
- [git lfs fsck — Git LFS reference](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-fsck.adoc)
- [Git LFS specification](https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md)

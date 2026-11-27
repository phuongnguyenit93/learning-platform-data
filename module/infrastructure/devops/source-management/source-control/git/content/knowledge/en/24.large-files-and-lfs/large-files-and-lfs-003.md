# Pointer Files, the LFS Object Store, and the Role of .gitattributes

Git is optimized for managing source code and change history. When a repository contains many large binary files such as videos, design images, 3D models, datasets, or audio files, every clone and sync can become heavy. Git Large File Storage (Git LFS) solves this problem by storing a small pointer in Git history while storing the actual content in a separate LFS object store.

For this mechanism to work properly, the repository must declare file types via `.gitattributes`, developer machines must have Git LFS installed, and the remote must provide a corresponding LFS storage service. This lesson belongs to the **Large Files and LFS** chapter of the SOURCE_CONTROL_GIT module, where you learn how to manage the working tree, staging area, commits, branches, remotes, and tags for traceable collaboration and releases.

## 1. Why Is Git LFS Needed?

In standard Git, the content of each file version is stored as a blob in the object database. Git can compress and store deltas between versions, yet for many large binary files, changing even a small portion can produce a new blob of substantial size. When cloning or fetching history containing those files, users may have to download large amounts of data not needed for their current work.

Git LFS separates large content from the Git object database:

- Git stores a small **pointer file**, which can be committed, merged, and tracked in history like other files.
- The large file content is stored as an **LFS object** in the LFS storage on the server.
- The pointer contains a content identifier (OID) and size, enabling Git LFS to locate the right object during checkout or download.

For example, instead of storing a 300 MB `assets/product-demo.mp4` file directly in a Git blob, Git commits a pointer of just a few lines. The video content is uploaded to LFS storage on push and downloaded when another machine needs to check out that file.

Git LFS does not replace Git. Git still manages commits, branches, tags, and pointers; LFS manages the large binary content referenced by those pointers.

## 2. How Is a Pointer File Structured?

A typical version 1 LFS pointer is a small UTF-8/ASCII text file with the following fields:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac196e6f2f4c2f7d5a1c9f6b8e3d4a2c1f0e9d8b7a6c5d4e3f2a1b0c9d8e7f
size 314572800
~~~

This is an illustrative format example; an actual OID must be the SHA-256 hash of the corresponding file content.

| Field | Meaning |
| --- | --- |
| version | Git LFS pointer specification version |
| oid sha256:<hash> | Content identifier based on SHA-256 |
| size <bytes> | Original content size in bytes |

The OID allows Git LFS to identify objects by content. If two paths or two commits reference the same content, they can share a single LFS object because the OID is identical. When the content changes, the SHA-256 changes and the pointer references a different object.

The pointer does not contain the filename. Names and paths reside in Git trees just like other entries; the pointer only identifies the content to retrieve. The specification can include additional extension metadata in cases where LFS extensions are used, though the three fields above are the common baseline form.

### Distinguishing the LFS OID from the Git Blob ID

These are two distinct identifiers:

- **The OID in the LFS pointer** is the SHA-256 hash of the large file's content.
- **The Git blob ID** is the hash of the pointer text stored by Git in the object database. Depending on repository format, Git may use SHA-1 or SHA-256 for object IDs.

Because Git stores the pointer text, inspecting the blob of an LFS file in a commit usually shows a few lines of pointer text rather than the original binary content:

~~~bash
git show HEAD:assets/product-demo.mp4
~~~

In the working tree after LFS smudging succeeds, `assets/product-demo.mp4` once again contains the actual video content.

## 3. Where Are LFS Objects Stored?

Git LFS stores content by OID in a separate object store, distinct from the Git object database. In a standard setup, the local object copy lives under the Git directory, typically at:

~~~text
.git/lfs/objects/
~~~

The exact path can vary depending on `lfs.storage` configuration, linked worktrees, or repository layout. Run the following command to view the paths and endpoint currently used by Git LFS:

~~~bash
git lfs env
~~~

LFS objects are usually organized into subdirectories by leading OID prefixes to avoid putting too many files into one directory. Do not manually move, rename, or edit objects in this store; let Git LFS manage them via fetch, pull, push, and prune commands.

On the server, LFS objects are stored in an LFS storage service, which may be integrated with the Git platform or deployed separately. The Git repository and the LFS store are two separate storage layers:

| Component | Stored data | Role |
| --- | --- | --- |
| Git object database | Commits, trees, blobs, and tags | History, directory structure, and pointer files |
| LFS object storage | Large binary content | Actual data referenced by pointers |
| Git remote refs | Branches and tags | Indicates which commit is the current tip or release version |
| LFS endpoint | LFS HTTP/API service | Authenticates and transfers LFS objects between client and server |

Because of this separation, a successful Git commit push does not by itself prove every LFS object is on the server. A normal push workflow requires Git LFS to upload objects before updating the Git ref.

## 4. The Role of .gitattributes

`.gitattributes` tells Git which paths should be processed by Git LFS. When you run `git lfs track`, Git LFS adds patterns to this file.

Example:

~~~gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
~~~

Meaning of the attributes:

| Attribute | Role |
| --- | --- |
| filter=lfs | Specifies the Git LFS clean/smudge/process filters |
| diff=lfs | Uses the LFS diff driver for pointers and LFS file details |
| merge=lfs | Uses the LFS merge driver to handle pointers during merges |
| -text | Disables text-style line-ending normalization for binary files |

`.gitattributes` is committed into the repository so every team member receives the same path rules. Git LFS filter execution settings are configured on each machine via `git lfs install`.

### Tracking a File Type

After installing Git LFS, run:

~~~bash
git lfs install
git lfs track "*.psd"
git lfs track "*.mp4"
git lfs track "*.zip"
~~~

`git lfs track` updates `.gitattributes`. Review and commit this file along with your changes:

~~~bash
git status
git diff -- .gitattributes
git add .gitattributes
~~~

Patterns must be quoted when invoked from a shell so Git LFS receives the literal pattern instead of the shell expanding the wildcard against existing files.

### Checking Effective Attributes

Use `git check-attr` to see how Git will process a path:

~~~bash
git check-attr filter diff merge text -- assets/design.psd
~~~

Expected output for an LFS-tracked file looks similar to:

~~~text
assets/design.psd: filter: lfs
assets/design.psd: diff: lfs
assets/design.psd: merge: lfs
assets/design.psd: text: unset
~~~

If the attributes are not as expected, check the pattern, the location of `.gitattributes`, and higher-priority attribute files such as `$GIT_DIR/info/attributes`.

## 5. How Do Clean, Smudge, and Process Filters Work?

Git LFS integrates with Git through filters. The two core operations are clean and smudge:

- **Clean filter** runs when content is added to Git, typically via `git add`. It stores the actual content in the local LFS object store and returns a pointer for Git to put in the index and commit.
- **Smudge filter** runs when Git checks out content from the index/commit to the working tree. It reads the pointer, looks up the matching LFS object in the cache, downloads it from the LFS endpoint if missing, and writes the actual content to the file.

Modern Git LFS typically configures a process filter as well to handle multiple requests more efficiently. `git lfs install` sets up the required filter configuration keys for Git.

### Flow When Adding a File

Suppose you add `assets/scene.psd`:

1. `.gitattributes` matches the `*.psd` pattern.
2. You run `git add assets/scene.psd`.
3. Git invokes the LFS clean/process filter.
4. Git LFS computes the SHA-256, writes the content into the local LFS object store, and generates a pointer.
5. The Git index receives the text pointer instead of the full PSD content.
6. On commit, Git stores the pointer as a Git blob.

### Flow When Checking Out

When a team member clones or checks out a commit containing a pointer:

1. Git reads the pointer blob from the Git object database.
2. Git invokes the LFS smudge/process filter based on attributes.
3. Git LFS looks up the OID in the local object store.
4. If the object is missing locally, Git LFS requests the object from the LFS endpoint.
5. Git LFS verifies the content against the OID/size and writes the actual file into the working tree.

If smudging was skipped or the LFS object could not be downloaded, the working tree may display pointer text instead of the original content. This does not mean the pointer is corrupted; it indicates the LFS content has not been materialized into the working directory.

## 6. Working with Git LFS

### Step 1: Install Git LFS

Install Git LFS for your OS or via a package manager, then initialize the configuration:

~~~bash
git lfs install
git lfs version
~~~

`git lfs install` configures the required filters and hooks in the corresponding Git config scope. If you only want to set it up for the current repository:

~~~bash
git lfs install --local
~~~

Every team member and CI environment needs Git LFS to automatically convert pointers into file content or upload/download objects.

### Step 2: Declare Patterns in .gitattributes

~~~bash
git lfs track "*.psd"
git lfs track "*.mp4"
git diff -- .gitattributes
git add .gitattributes
~~~

Commit `.gitattributes` so the rules are shared with the entire team.

### Step 3: Add Large Files

~~~bash
git add assets/design.psd assets/product-demo.mp4
git status
git lfs ls-files
~~~

`git lfs ls-files` lists files managed by Git LFS within the ref/index scope being inspected. Inspect the pointer in the commit after committing:

~~~bash
git commit -m "Add design assets with Git LFS"
git show HEAD:assets/design.psd
~~~

Here `git show` displays the pointer, not the PSD data.

### Step 4: Push to Remote

~~~bash
git push origin main
~~~

With the `pre-push` hook configured by `git lfs install`, Git LFS uploads the objects required for the pushed ref before Git updates the branch on the remote. Git then pushes the commits and pointers as usual.

If the hook is bypassed or not installed, the remote may receive commits containing pointers without the corresponding LFS objects. Others will see pointers but fail to download file content. In special workflows, you can upload explicitly:

~~~bash
git lfs push origin main
~~~

Do not disable the `pre-push` hook in standard workflows.

### Step 5: Clone and Download Content on Another Machine

The receiving machine needs Git LFS installed before cloning:

~~~bash
git lfs install
git clone https://example.com/team/large-app.git
~~~

During checkout, the smudge filter downloads the necessary LFS objects and replaces pointers with actual content. If you want to clone the repository while temporarily skipping LFS downloads:

~~~bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://example.com/team/large-app.git
~~~

In PowerShell, you can set the environment variable for a session:

~~~powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://example.com/team/large-app.git
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
Set-Location large-app
git lfs pull
~~~

## 7. Distinguishing LFS fetch, pull, checkout, and push

Git LFS provides dedicated commands for managing content:

| Command | Effect |
| --- | --- |
| git lfs fetch origin main | Downloads LFS objects needed for the specified ref to the local cache without automatically updating the working tree |
| git lfs checkout | Writes LFS objects already in the cache to the working tree for matching pointers |
| git lfs pull origin main | Fetches LFS objects for the ref and then checks out the content into the working tree |
| git lfs push origin main | Uploads LFS objects needed for the ref to the LFS server |
| git lfs ls-files | Lists paths managed by LFS |
| git lfs env | Displays Git LFS version, storage directories, and endpoints |

Git's `git fetch` retrieves standard Git commits/trees/blobs and updates remote-tracking refs; it is not equivalent to `git lfs fetch`. Similarly, `git pull` integrates Git history while LFS content is handled by filters or the corresponding LFS commands.

If you want to prepare LFS content before going offline, fetch objects for the branch you need:

~~~bash
git lfs fetch origin main
git lfs checkout
~~~

## 8. What Happens When a File Was Committed Before LFS Tracking?

`git lfs track` only adds rules for future Git file handling. If a large file was previously committed as a normal Git blob, adding a pattern does not automatically convert all old history into pointers.

To switch the current version to LFS after adding the pattern, re-stage the file so the clean filter runs:

~~~bash
git lfs track "*.psd"
git add .gitattributes
git add --renormalize assets/design.psd
git status
~~~

This ensures the next staged version uses an LFS pointer. However, older commits still contain the large blob in Git history.

If you want to remove those files from old history and convert history to LFS, you need a migration tool:

~~~bash
git lfs migrate info --everything
git lfs migrate import --include="*.psd,*.mp4" --everything
~~~

`git lfs migrate import` rewrites commit history to replace matching blobs with LFS pointers. Commit hashes change, so this operation affects everyone using the old history. Only perform it when the team agrees on a plan, has backups, and has a coordinated schedule for force-pushing and updating clones. Do not run migrations arbitrarily on shared branches or released repositories.

## 9. Security, Access Control, and Storage Quotas

LFS objects can contain large or sensitive data such as internal videos, product designs, or datasets. LFS access is typically authenticated through the Git/LFS endpoint service; users need appropriate read/write permissions for the objects.

Limits to verify:

- Maximum size per LFS object.
- LFS storage quota and download bandwidth.
- Upload/download permissions per repository or group.
- Retention, backup, and server-side object deletion policies.
- Git LFS support capabilities of your hosting provider or self-managed server.

Deleting a pointer from a branch or deleting a tag does not necessarily delete the LFS object from the server immediately. The object may still be referenced by another commit or branch, or retained per storage policy. Never delete data directly inside LFS storage manually.

## 10. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Checkout shows a few pointer lines instead of the real file | Smudge was skipped, Git LFS is not installed, or the object was not downloaded | Run `git lfs install`, verify config, and run `git lfs pull` |
| Git push succeeds but others cannot download the file | LFS object was not uploaded or `pre-push` hook did not run | Run `git lfs push origin <branch>` and check hooks/permissions |
| `git add` stores the whole large file as a Git blob | Pattern did not match or `.gitattributes` was not active when staging | Run `git check-attr`, track the pattern, and re-stage |
| Clone reports an LFS authentication error | Account lacks LFS access or credentials are invalid | Check repository permissions, credential helper, and endpoint |
| LFS download rejected or quota exceeded | Server quota or policy limits | Check quotas, object sizes, and access permissions |
| New machine only has pointers | Git LFS is not installed or smudge was skipped | Install Git LFS and run `git lfs pull` |
| Repository remains huge after enabling LFS | Old history still contains large Git blobs | Inspect `git lfs migrate info`; plan a migration if rewriting history is needed |

Useful diagnostic commands:

~~~bash
git lfs version
git lfs env
git lfs ls-files
git check-attr filter diff merge text -- path/to/large-file
git status
~~~

## 11. End-to-End Workflow

~~~mermaid
flowchart TD
    A[Choose large file types to manage] --> B[Install Git LFS]
    B --> C[git lfs track pattern]
    C --> D[Commit .gitattributes]
    D --> E[git add large file]
    E --> F[Clean filter creates LFS object and pointer]
    F --> G[Commit pointer to Git]
    G --> H[Pre-push uploads LFS object]
    H --> I[Push Git commits and refs]
    I --> J[Another machine clones/fetches pointers]
    J --> K[Smudge or git lfs pull downloads content]
    K --> L[Working tree has actual file]
~~~

Before adopting Git LFS in a project, verify:

1. Are the chosen file types and patterns appropriate for the data being managed?
2. Has `.gitattributes` been committed and does `git check-attr` return the expected attributes?
3. Has `git lfs install` been executed on developer machines and CI environments?
4. Does the pointer have a valid OID and size, and is the actual content present in the LFS object store?
5. Does the `pre-push` hook upload objects before the branch is updated on the remote?
6. Can receiving machines authenticate and download LFS objects?
7. If the files already exist in Git history, has the team decided whether migration is needed?

Git LFS separates pointers from large binary content so Git history stays lighter and syncing can be more flexible. `.gitattributes` specifies which paths use LFS; the clean filter turns content into pointers when staging; the smudge filter restores content during checkout; and LFS object storage holds the actual data and serves it via an endpoint. Understanding each layer enables you to accurately diagnose pointer, upload, and download errors and manage large files in collaborative workflows.

## References

- [Git LFS documentation](https://git-lfs.com/) — overview of Git Large File Storage.
- [Git LFS specification](https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md) — pointer file format and LFS protocol.
- [Git LFS command reference](https://github.com/git-lfs/git-lfs/tree/main/docs/man) — track, fetch, pull, push, migrate, and env commands.
- [Git documentation: gitattributes](https://git-scm.com/docs/gitattributes) — filter, diff, merge, and path-based attributes.

# Distinguishing Git LFS from Git's Native Object Storage

Git can store any type of content as objects, including images, videos, design files, 3D models, and large binaries. However, the fact that Git can store a file does not mean the repository will stay compact or that clone, fetch, and push operations will remain efficient when large files change frequently. Git LFS (Large File Storage) adds a mechanism that stores large content on a separate server, while the Git repository only stores a small pointer file identifying the exact content version to use.

The key distinction is: **Git stores file content directly in the object database; Git LFS stores a pointer in Git and offloads the actual content to an external LFS store.** Both mechanisms still work together so each commit pins the exact version of every file.

## 1. How Does Git Store Files as Objects?

Git uses a content-addressable storage model. Each piece of content is stored as an object whose identifier is computed from its object type and data. For a regular file, Git creates a **blob object** containing the file's content.

Some fundamental object types:

| Object | Role |
|---|---|
| Blob | Stores the content bytes of a file; does not store the filename or path itself |
| Tree | Stores a list of names, modes, and referenced objects within a directory |
| Commit | Records a tree, parent commits, author, committer, timestamp, and message |
| Tag | Can be a lightweight ref or an annotated tag object with metadata pointing to another object |

For example, when committing an image `assets/banner.png`, Git stores the image bytes in a blob. The tree for the `assets/` directory records the name `banner.png` along with its mode and the blob's object ID. The commit points to the tree containing this directory.

Filenames and paths are not stored inside the blob. Therefore, the same content can be referenced by multiple trees or commits without storing a separate blob copy simply because the file was renamed.

## 2. How Does Git Store Versions of Large Files?

Git stores a snapshot of content at each commit. When a file changes, the new version can produce a new blob with a new object ID. If the content is identical to an existing blob, Git can reuse that object thanks to content-addressable naming.

In real repositories, Git typically packs objects into packfiles. When packing, Git can use compression and delta compression to store differences between similar objects instead of keeping complete duplicate copies. This saves significant space for many text files or content with similar structure.

However, large binary files such as video, compressed images, design files, or archives rarely produce small deltas. Even a small edit in the file can change most bytes, causing the new version to still consume substantial space. As a result, the repository can grow rapidly with each new version of a large file.

Git does not enforce a single fixed file size limit across all repositories. Practical limits can come from hosting providers, server configuration, filesystems, memory, transfer time, or team policies. A large file might commit successfully on a local machine yet be rejected by the remote on push.

## 3. Why Can Storing Large Files Directly in Git Be Inconvenient?

When large files are stored directly in the object database, their objects become part of repository history. Operations like clone or fetch may need to download those objects depending on the history and refs retrieved.

Common consequences include:

- **Repository size growth:** multiple versions of binary files can cause packfiles to grow steadily.
- **Slow clones and fetches:** contributors who only need source code may still have to download many large objects belonging to the fetched history.
- **Time-consuming pushes:** new versions of large files must be transmitted to the remote alongside other Git objects.
- **Hard to remove committed data:** deleting a file in a new commit does not automatically delete old blobs from history; removing them requires rewriting history and coordinating with repository users.
- **Difficulty meeting hosting limits:** providers may enforce per-object size limits or total repository size quotas.

Not every large file requires LFS. If a file rarely changes, has moderate size, needs full offline availability, or fits the repository's storage policy, storing it directly in Git may be simpler. LFS is valuable when large or binary files change frequently and the cost of downloading the entire history becomes a problem.

## 4. How Does Git LFS Change the Storage Model?

Git LFS keeps large files in a separate LFS object store, typically served by the hosting platform or an LFS server. Inside the Git repository, the file content is replaced by a small text **pointer file**.

Example LFS pointer:

```text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac19622fc3ada9c0fdeadb33f88f367b541f38b8914d9d6c6f9c1e6c9a4f1b
size 84977953
```

Line meanings:

- `version` identifies the pointer format specification version.
- `oid sha256` is the SHA-256 hash of the actual file content stored in the LFS store.
- `size` is the actual file content size in bytes.

Git commits the pointer file just like a normal blob. On checkout, Git LFS uses the OID and size in the pointer to locate the exact binary content on the LFS server and places that content into the working tree.

Thus, Git still manages version history: commit A can point to the first pointer OID, and commit B can point to the second pointer OID. Each commit pins the exact large file version needed without storing all bytes of the large file in Git's object database.

## 5. Comparing Git Object Storage and Git LFS

| Criterion | Direct Git Storage | Git LFS |
|---|---|---|
| Content in Git commit | Blob containing actual file bytes | Blob containing text pointer |
| Where large content lives | Git repository object database | External LFS store outside Git object database |
| Version identified by | Git blob object ID | SHA-256 OID inside the LFS pointer |
| Repository clone | May need to download large objects in fetched history | Downloads pointers; LFS downloads required content per checkout config |
| Push | Sends Git objects to Git remote | Uploads LFS objects and updates Git refs |
| Binary file diff | Usually unhelpful without a custom diff driver | Pointer changes when LFS content changes; large content still needs suitable tools to compare |
| Service dependencies | Only requires Git remote | Requires both Git remote and accessible LFS endpoint |
| Storage usage | Increases Git object database size | Increases LFS storage and bandwidth usage |
| Best suited for | Source code, text, small/medium or rarely changing files | Large, binary, frequently changing files |

LFS does not eliminate storage costs. It shifts the cost of storing large content to the LFS service while helping keep the Git repository's pointer history more compact. LFS providers may still meter storage quotas and download bandwidth.

## 6. Git LFS Uses Clean and Smudge Filters

Git LFS integrates with Git through the filter mechanism:

- **Clean filter:** when content is added to the index, the filter converts the large file into an LFS pointer before Git creates the blob.
- **Smudge filter:** when content is checked out to the working tree, the filter reads the pointer and replaces it with the actual file downloaded or retrieved from the LFS cache.

The `git lfs install` command configures the required filters and installs supporting hooks for the current user. Therefore, when cloning or checking out a repository containing LFS pointers, the machine needs Git LFS installed and configured to automatically fetch the actual content.

If Git LFS is not installed, Git can still check out the text pointer as a regular file. In that case, you may see content starting with `version https://git-lfs.github.com/spec/v1` instead of the expected binary file.

## 7. Installing and Configuring Git LFS

Git LFS is an extension installed separately alongside Git. After installing according to your operating system's instructions, verify:

```bash
git lfs version
```

Install configuration for the current account:

```bash
git lfs install
```

This command sets up filters and hooks for Git to integrate with Git LFS. In CI environments or shared machines, verify the target account and installation location; do not assume every machine cloning the repo already has Git LFS.

Inspect LFS environment details:

```bash
git lfs env
```

This displays the endpoint, local LFS object storage directory, and related settings. Avoid sharing raw output if it contains internal paths or private organizational endpoint details.

## 8. Choosing Which Files Are Managed by LFS

Git LFS uses `.gitattributes` to specify file patterns routed through the LFS filter. For example, to track all PSD files:

```bash
git lfs track "*.psd"
```

This updates `.gitattributes` with a rule similar to:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
```

You can track additional file types:

```bash
git lfs track "*.mp4"
git lfs track "*.zip"
git lfs track "*.blend"
```

Patterns in `.gitattributes` determine which paths use LFS. Verify that rules are written accurately and avoid routing unnecessary files into LFS.

After configuring patterns, add both `.gitattributes` and the large file:

```bash
git add .gitattributes
git add assets/banner.psd
git status
git check-attr filter diff merge text -- assets/banner.psd
```

The `git check-attr` command confirms whether the file has the expected LFS attributes. Then create the commit:

```bash
git commit -m "Track design assets with Git LFS"
```

The commit stores `.gitattributes` along with the LFS file pointer in Git. The binary content is managed separately by Git LFS.

## 9. `git lfs track` Does Not Automatically Convert Old History

A common point of confusion: running `git lfs track "*.psd"` does not automatically move PSD blobs already present in previous commits into the LFS store. The command only updates `.gitattributes` rules so subsequent `git add` operations handle matching files via LFS.

If a file is already tracked directly by Git, after adding the pattern you must run it through a new add/commit flow so the new version becomes a pointer. Older versions remain as Git blobs in history.

If the goal is to convert old versions in history to LFS, a migration tool may be needed:

```bash
git lfs migrate import --include="*.psd" --everything
```

This operation rewrites relevant commits to replace regular blobs with LFS pointers. Because commit objects change, commit hashes and related branch/tag histories can change. This affects the entire repository and requires planning, backups, team coordination, and a clone-update procedure before pushing the rewritten history. Do not run migrations on shared branches arbitrarily.

## 10. Cloning a Repository with Git LFS

When Git LFS is installed and `git lfs install` has been run, cloning a repository normally downloads pointers and the LFS content needed for the working tree:

```bash
git clone https://git.example.com/team/design-assets.git
```

Git clones the repository and checks out the commit; the LFS filter processes pointers to fetch actual file content from the LFS endpoint. Without access to the LFS endpoint, the clone may succeed for the Git repository while failing to retrieve the large files.

In environments needing a fast clone or when you do not want to download LFS files immediately, you can skip smudging during clone and pull later:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://git.example.com/team/design-assets.git
cd design-assets
git lfs pull
```

In PowerShell on Windows, you can set the environment variable for the current process before cloning:

```powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://git.example.com/team/design-assets.git
Set-Location design-assets
git lfs pull
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
```

When smudge is skipped, the working tree may hold pointers instead of actual file content until you run `git lfs pull` or the corresponding LFS checkout operation.

## 11. Fetching and Pulling LFS Content

Git fetch downloads Git objects and updates remote-tracking refs. LFS content is downloaded via Git LFS's own mechanism.

Common commands:

```bash
git lfs fetch origin main
```

This downloads LFS objects referenced by the specified ref range into the local cache; it does not necessarily replace pointers in the working tree.

```bash
git lfs pull origin main
```

`git lfs pull` combines LFS fetch with checking out LFS content into the working tree for the current ref/checkout in the way Git LFS supports. This is useful after switching branches or when retrieving LFS content that was skipped during clone.

To download only a subset of files matching patterns, use include/exclude:

```bash
git lfs fetch --include="assets/**/*.psd" --exclude="assets/archive/**" origin main
```

Include/exclude scoping reduces downloaded data when a repository contains many LFS files. Verify patterns and refs before downloading.

## 12. Pushing Commits Containing LFS Files

When pushing commits with LFS pointers, Git must ensure the corresponding LFS content has been uploaded to the LFS server. The `pre-push` hook installed by `git lfs install` normally uploads required objects automatically before Git updates refs on the remote:

```bash
git push origin main
```

If hooks are disabled or the push environment does not execute hooks, Git refs may be pushed without the required LFS objects being uploaded; others will encounter errors when downloading files. When explicit upload is needed, you can run:

```bash
git lfs push origin main
```

Or upload all LFS objects referenced by local refs:

```bash
git lfs push --all origin
```

`--all` can transfer a large amount of data, so consider size and permissions before using it. In normal workflows, having the hook properly installed and running `git push` is usually sufficient.

## 13. Checking Which Files Use LFS

List LFS-tracked files:

```bash
git lfs ls-files
```

Check LFS status:

```bash
git lfs status
```

Inspect attributes applied to a file:

```bash
git check-attr filter diff merge text -- assets/banner.psd
```

View the pointer committed in Git:

```bash
git show HEAD:assets/banner.psd
```

If the file has been converted to LFS, the command above typically displays the text pointer rather than binary content. This confirms the Git object database stores a pointer for that path.

Conversely, `git lfs ls-files` shows the paths recognized as LFS in the current revision along with their corresponding OIDs. Combining both commands clarifies which mechanism manages each file.

## 14. Distinguishing Git Size from LFS Size

The following command reports object statistics in the local Git store:

```bash
git count-objects -vH
```

The output reflects Git's loose objects and packfiles. It does not measure total LFS usage on the server. The local LFS cache is stored in the location configured by Git LFS; view the path with:

```bash
git lfs env
```

LFS storage on the server must be checked via the provider's UI, API, or administration console. Git cannot infer remaining storage quotas or bandwidth from the local object database alone.

If a repository remains very large after moving some files to LFS, old blobs may still remain in Git history. Determine whether large files were previously committed directly and whether a history-rewriting migration is needed.

## 15. Limitations and Trade-Offs of Git LFS

Git LFS solves large-file storage and transfer challenges, but introduces operational dependencies:

- **Requires an LFS server:** the Git remote and LFS endpoint may have separate permissions, URLs, and policies.
- **May incur quotas:** providers may meter storage capacity and download bandwidth.
- **Not all tools understand pointers:** build tools, archivers, or external file processors may receive pointers if LFS has not materialized the content.
- **Offline work requires preparation:** un-downloaded LFS files will not have actual content in the working tree.
- **Migrations affect history:** moving old blobs to LFS can rewrite commits and require other clones to re-sync.
- **Does not replace artifact management:** build outputs, release packages, and deployment data may fit an artifact registry or dedicated object storage better.

LFS also does not automatically solve collaborative binary editing. When multiple people edit design or media files concurrently, Git LFS can support file locking on configured servers and workflows, yet teams still need processes to avoid overwriting one another's versions.

## 16. Choosing Between Git and Git LFS for a File Type

Consider the following factors:

| Question | If the answer is "Yes" |
|---|---|
| Is the file large and frequently modified? | Consider Git LFS |
| Is the file a hard-to-delta-compress binary like video, PSD, 3D model, or archive? | LFS is usually better when history grows rapidly |
| Does every member need an immediate full offline clone? | Storing directly in Git may be simpler; if using LFS, establish clear download/cache steps |
| Does the Git server support LFS and does the team have suitable quota? | LFS is viable; verify storage and bandwidth costs |
| Is the file a reproducible build artifact or deployment data? | Consider an artifact registry or object storage instead of Git/LFS |
| Is the file small, text-based, and in need of line-by-line diff/merge? | Direct Git storage is usually more appropriate |

Do not choose LFS based on file extension alone. Base the decision on size, update frequency, diffability, offline needs, hosting policies, and history retention requirements.

## 17. End-to-End Practical Workflow

Suppose a project has a large design file `assets/product-mockup.psd` and the team decides to manage it with LFS.

1. Install Git LFS and verify the tool:

   ```bash
   git lfs version
   git lfs install
   ```

2. Register the pattern:

   ```bash
   git lfs track "*.psd"
   ```

3. Verify and stage `.gitattributes` along with the design file:

   ```bash
   git check-attr filter diff merge text -- assets/product-mockup.psd
   git add .gitattributes assets/product-mockup.psd
   git status
   ```

4. Create the commit:

   ```bash
   git commit -m "Add product mockup through Git LFS"
   ```

5. Confirm Git stores the pointer and LFS recognizes the file:

   ```bash
   git show HEAD:assets/product-mockup.psd
   git lfs ls-files
   git lfs status
   ```

6. Push to an LFS-enabled remote:

   ```bash
   git push origin main
   ```

7. In another clone with Git LFS, clone the repository and confirm the actual content is downloaded:

   ```bash
   git clone https://git.example.com/team/product.git
   git -C product lfs ls-files
   ```

If the clone was performed with `GIT_LFS_SKIP_SMUDGE=1`, run `git lfs pull` inside the repository to download and materialize the content.

## 18. Key Takeaways

Git stores file content directly as blobs in the object database; packfiles and delta compression can reduce size, but do not guarantee that large, frequently changing binaries will be cheap to store and transfer. Git LFS keeps small pointers in Git while storing actual content on an LFS server and downloading it when needed at checkout. Commits still pin exact versions via the OID and size inside each pointer. Choose LFS based on file characteristics and operational costs, install Git LFS on developer machines and CI runners, verify endpoints and quotas, and remember that `git lfs track` does not automatically migrate old blobs already in history.

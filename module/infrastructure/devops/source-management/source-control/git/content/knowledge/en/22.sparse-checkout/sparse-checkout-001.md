# Distinguishing shallow clone, partial clone, and sparse checkout

When working with large repositories, Git provides three mechanisms commonly used to reduce the amount of data downloaded or the number of files you need to work with at once: shallow clone, partial clone, and sparse checkout. Their names sound fairly similar, but they solve three different problems.

- **Shallow clone** limits the depth of commit history fetched.
- **Partial clone** filters the Git objects downloaded from the remote, usually file blob contents.
- **Sparse checkout** limits which paths are present in the working tree.

These three mechanisms can be used individually or combined. To choose the right one, you first need to identify whether the bottleneck is overly long history, oversized objects/files, or a working tree with too many unrelated directories.

## 1. Viewing the three mechanisms across three different layers

A Git repository can be viewed across three layers:

1. **Commit graph:** the chain of commits and parent-child relationships that form the history.
2. **Object database:** the commit, tree, blob, and tag objects that Git stores to reconstruct history, directories, and file contents.
3. **Working tree:** the files and directories currently checked out on disk for you to read and edit.

Shallow clone, partial clone, and sparse checkout operate on different layers:

| Mechanism | Primary limit | What is reduced | What is not automatically reduced |
|---|---|---|---|
| Shallow clone | Commit history depth | Number of commits and portion of history to download | Number of files in the currently checked-out snapshot |
| Partial clone | Type or size of objects downloaded | Objects transferred and stored locally, usually blobs | Number of paths in the working tree if still checking out everything |
| Sparse checkout | Paths checked out | Number of files/directories present in the working tree | Commit history and objects already present in the local repository |

Examples:

- A repository has ten years of history, but the latest snapshot is small: shallow clone can reduce the time to fetch history.
- A repository contains many large binary files or lots of source code you don't need to read: partial clone can defer downloading blobs.
- A monorepo has hundreds of services, but you only develop one service: sparse checkout makes the working tree show only the relevant part.
- If a monorepo has long history, many large blobs, and many unneeded directories, you can combine all three.

You should not treat the three mechanisms as three names for the same kind of trimmed-down clone. A shallow clone can still check out every file at the current commit. A sparse checkout does not automatically delete history or objects from the local database. A partial clone can still expose all files if the entire repository is checked out and Git downloads the required blobs.

## 2. Shallow clone: fetching limited commit history

Shallow clone creates a repository whose commit history is truncated at a specific boundary. The simplest way is to limit the number of commits:

~~~bash
git clone --depth 1 https://example.com/team/inventory.git inventory
~~~

The `--depth 1` option requests fetching history with a depth of one commit for the cloned branch. Git still checks out the snapshot of that commit. If the snapshot contains 20,000 tracked files, the working tree can still have all 20,000 files.

Some other ways to limit history:

~~~bash
git clone --depth 20 https://example.com/team/inventory.git inventory
git clone --shallow-since="2025-01-01" https://example.com/team/inventory.git inventory
git clone --shallow-exclude=v1.0.0 https://example.com/team/inventory.git inventory
~~~

- --depth <n> limits the number of commits starting from the tip of the fetched branch.
- --shallow-since=<date> limits history by a point in time.
- --shallow-exclude=<revision> excludes history reachable from the specified revision from what is fetched.

### 2.1. Consequences of --depth

When using --depth, Git defaults to cloning only a single branch (--single-branch), unless you request --no-single-branch.

~~~bash
git clone --depth 1 --no-single-branch https://example.com/team/inventory.git inventory
~~~

This approach is useful when you need shallow history for multiple remote branches. Consider the number of refs to track because it can increase the volume of commits downloaded.

Check whether a repository is a shallow clone:

~~~bash
git rev-parse --is-shallow-repository
~~~

A result of true means the repository currently has a shallow boundary; false means the history is no longer shallow as far as Git knows.

You can inspect the available history:

~~~bash
git log --oneline --decorate --all
git log --oneline --all --graph
~~~

The displayed history is limited to the fetched commits. Not seeing old commits does not mean those commits have been deleted from the remote.

### 2.2. Deepen or remove the shallow limit

When you need more history to find a merge base, run blame, bisect, or view older commits, you can fetch deeper:

~~~bash
git fetch --deepen=50 origin main
~~~

The command requests fetching 50 additional commits from the current shallow boundary for the specified branch. The actual number of commits may be fewer if the remote no longer has enough history along that branch.

To fetch all remaining history from a full remote:

~~~bash
git fetch --unshallow origin
~~~

--unshallow converts a shallow repository into a repository with full history if the fetch source provides full history. If the source is also a shallow repository, the result cannot exceed the history the source currently has.

Verify again:

~~~bash
git rev-parse --is-shallow-repository
git log --oneline --all --max-count=30
~~~

If you need more history without downloading everything yet, use --deepen instead of unshallowing immediately.

### 2.3. Pros and limitations of shallow clone

**Pros**

- Reduces the number of commits to download and process when cloning.
- Useful for CI running tests against the latest commit or branch.
- Reduces initialization cost when history is very long but the task only needs the current snapshot.

**Limitations**

- Commands that traverse backward through history may not see enough commits or a merge base.
- git log, git blame, git bisect, branch comparisons, and some merge/rebase operations may require fetching more history.
- Shallow clone does not automatically reduce the number of files in the checked-out snapshot.
- When investigating an old bug, you may need to deepen or unshallow.

Choose shallow clone when the task truly only needs recent history. If your work frequently requires tracing root causes across many months or multiple branches, consider a full clone or setting a sufficient depth.

## 3. Partial clone: filtering objects downloaded from the remote

Partial clone allows the client to ask the remote to omit certain objects during the initial clone. Git records the remote as a promisor remote: the remote promises it can provide missing objects when the client needs them.

The most common case is not downloading blobs up front:

~~~bash
git clone --filter=blob:none https://example.com/team/monorepo.git monorepo
~~~

blob:none requests not downloading blobs during the initial object fetch. Necessary commits and trees are still fetched so Git knows the history and directory structure. When an operation needs the contents of a missing blob, Git can lazy-fetch that blob from the promisor remote.

A blob is an object containing file contents. A tree is an object describing names, modes, and referenced objects in a directory. Therefore, blob:none does not mean the repository doesn't know filenames or directory structure; it defers file contents.

### 3.1. Common filters

| Filter | Meaning | Use case |
|---|---|---|
| blob:none | Do not fetch blobs initially; download on demand | Want history/structure first, only download contents of files that are used |
| blob:limit=1m | Skip blobs at or above the specified size threshold | Want to download most small files while deferring large files |
| tree:0 | Treeless clone, deferring tree objects until needed | Commit-focused workflows that accept multiple on-demand object fetches |

Example filtering large blobs:

~~~bash
git clone --filter=blob:limit=1m https://example.com/team/assets.git assets
~~~

The threshold can use size suffixes such as k, m, g. This filter skips blobs that reach or exceed the specified limit; smaller blobs are still downloaded according to the filter rules.

tree:0 is an advanced option. It can significantly reduce initially downloaded objects, but operations that traverse structure or check out files can cause Git to fetch additional tree objects. For beginners or typical development workflows, blob:none is easier to understand and combine with sparse checkout.

### 3.2. How does lazy fetch work?

Suppose you clone with --filter=blob:none. Git has the commits and trees to know the repository contains src/, docs/, assets/, but some blobs are not yet local. If the clone performs a full checkout, Git needs to download the blobs belonging to the checked-out snapshot to create files in the working tree; blobs that only appear in other historical commits can still be deferred.

When you check out or open a file that needs such a blob, Git requests the missing object from the promisor remote. Once downloaded, the blob is stored locally and subsequent reads can use the cached object.

This means partial clone does not guarantee all operations work offline. If a blob that hasn't been downloaded yet is needed without connectivity to the remote, the operation can fail.

Some commands can cause Git to fetch more blobs than you expect, such as checking out the full working tree, exporting an archive of many files, searching contents across the entire repository, or running a tool that reads all source files. The benefit depends on your actual workflow, not just the clone command.

### 3.3. Checking partial clone configuration

For a clone that used a filter, check:

~~~bash
git config --get remote.origin.promisor
git config --get remote.origin.partialclonefilter
~~~

Typically, the promisor remote has the value true; the filter may be blob:none or the chosen filter. If those settings are absent, the repository may not be a partial clone in that way.

Partial clone requires a supporting Git client and a server that allows object filtering. If the server does not support filters, Git may warn and perform an unfiltered clone instead of what you expected. Read the clone command output and check the configuration afterward; don't just see --filter in the command and assume data was reduced.

### 3.4. Pros and limitations of partial clone

**Pros**

- Defers downloading file contents that aren't needed yet.
- Useful for repositories with many large files, heavy blob history, or many rarely accessed areas.
- Can keep full commit history without downloading all file contents up front.

**Limitations**

- Requires the remote to support filtering and lazy fetch.
- Operations that read many files can trigger downloading many blobs, reducing the initial savings.
- Depends on network connectivity when missing objects are needed.
- Older tooling or scripts that assume objects are always local may behave unexpectedly.
- Partial clone does not automatically restrict paths in the working tree; to reduce checked-out files, combine it with sparse checkout.

## 4. Sparse checkout: showing only the paths you need to work on

Sparse checkout controls which tracked paths are checked out into the working tree. Files outside the sparse patterns are not present in the working tree under normal checkout, but they still belong to the repository.

You can apply sparse checkout to an existing clone:

~~~bash
git sparse-checkout init --cone
git sparse-checkout set services/catalog shared/java
~~~

In the example, the working tree will show the files at the root and the contents inside the two selected directories. Cone mode is optimized for selecting directories; it fits monorepos where you want to work on one or a few services along with shared libraries.

Check the currently selected directories:

~~~bash
git sparse-checkout list
~~~

Add a directory while keeping the already selected directories:

~~~bash
git sparse-checkout add services/pricing
~~~

### 4.1. Cone mode

--cone is the recommended mode for most cases. Instead of manually writing complex patterns, you specify the directories to check out:

~~~bash
git sparse-checkout set services/catalog shared/java docs/api
~~~

Cone mode is optimized for sets of nested directories. It keeps files at the repository root, files located directly in parent directories along the path to a selected directory, and the full contents of the selected directories. Unselected sibling directories are not populated in full into the working tree.

One benefit is that patterns are easy to read, easy to inspect, and can be efficiently represented by Git using a sparse index in large repositories.

If you need to select individual files or custom `.gitignore`-style patterns, Git has non-cone mode (--no-cone). This mode is more flexible but harder to write and can be less efficient. For selecting a few project directories in a monorepo, prefer cone mode.

### 4.2. Enabling sparse checkout right at clone time

You can ask clone to initialize sparse checkout:

~~~bash
git clone --sparse https://example.com/team/monorepo.git monorepo
cd monorepo
git sparse-checkout set services/catalog shared/java
~~~

The --sparse option starts with a narrow checkout, initially only fetching files at the root level. Then `git sparse-checkout set` expands the working tree to the directories you need.

If you already cloned normally, you do not need to re-clone just to use sparse checkout. Run `git sparse-checkout init --cone` and then `git sparse-checkout set` on the existing repository.

### 4.3. Viewing and disabling sparse checkout

List the currently selected scope:

~~~bash
git sparse-checkout list
~~~

Disable sparse checkout and bring all tracked files back into the working tree:

~~~bash
git sparse-checkout disable
~~~

This command expands the working tree back to the full current snapshot. In a partial clone, missing blobs for the newly populated files may need to be downloaded from the promisor remote.

Sparse checkout does not delete commits or objects from the repository. If you previously did a full clone, files outside the sparse set may still have their blobs locally. It only changes the checked-out contents and the index state related to the sparse working tree.

### 4.4. Sparse checkout is not an access control mechanism

Files outside the sparse set are merely hidden from the current working tree. That does not mean a user cannot access their contents if the objects are already local or can be fetched from the remote.

Do not use sparse checkout to protect secrets, sensitive source code, or enforce access separation. Use repository permissions, branch protection, server-side access control, and proper secret management practices.

## 5. Comparing impact and trade-offs

The table below helps you choose the right tool for your needs:

| Question | Shallow clone | Partial clone | Sparse checkout |
|---|---|---|---|
| Reduces commit history? | Yes | No, keeps history per clone request by default | No |
| Filters blob/tree objects during download? | Not via object filter | Yes | Does not filter objects itself |
| Reduces files present in the working tree? | No | No if checking out in full | Yes |
| Can download more data later? | Can deepen/unshallow | Has lazy object fetch | Can expand sparse set; partial clone can fetch newly needed blobs |
| Depends on server filter support? | No object filter needed | Yes | No object filter needed |
| Most useful for | CI or tasks needing short history | Object-heavy repositories, large blobs | Monorepos with many unneeded directories |

### 5.1. Choose shallow clone when

- CI only needs to check out the commit under test.
- The build does not need `git describe` based on old tags, long changelogs, or merge history.
- You want to reduce history fetch time in short-lived pipelines.

Do not choose depth 1 if the pipeline needs to compute versions from tags, run `git log` to generate a changelog, or use `git merge-base` with branches that have distant history.

### 5.2. Choose partial clone when

- The repository has many large blobs or lots of rarely accessed content.
- You want to keep commit history while deferring file content downloads.
- The remote supports filtering and the environment can lazy-fetch when needed.

If you always check out and scan the entire repository, partial clone may simply shift blob download time from clone time to build/test time.

### 5.3. Choose sparse checkout when

- A monorepo has many independent services or projects.
- Developers only work on a subset of directories.
- You want a small working tree, fewer files indexed by the IDE, and less noise when searching.

If the clone already has all objects, sparse checkout mainly reduces the number of files on disk and the number of files tools have to process; it does not shrink the repository object database.

## 6. Combining all three for a large monorepo

In a very large monorepo, you may need:

- Short history for pipelines that only test the latest commit.
- Downloading blobs only when needed.
- Checking out only the relevant service and libraries.

Example of cloning the main branch with depth 1, a blob filter, and sparse checkout:

~~~bash
git clone \
  --depth 1 \
  --filter=blob:none \
  --sparse \
  --branch main \
  https://example.com/team/monorepo.git monorepo
~~~

Then select the working areas:

~~~bash
cd monorepo
git sparse-checkout set services/catalog shared/java
~~~

Verify the three states:

~~~bash
git rev-parse --is-shallow-repository
git config --get remote.origin.promisor
git config --get remote.origin.partialclonefilter
git sparse-checkout list
git status -sb
~~~

Expected results:

- Shallow repository returns true.
- Promisor remote is configured and the filter shows blob:none.
- Sparse list shows services/catalog and shared/java.
- The working tree only shows root files along with the selected areas in cone mode.

Important note: --depth implies --single-branch by default. If a pipeline needs multiple branches, consider --no-single-branch, though that can increase the amount of history fetched. Only expand branch refs when the task actually requires it.

If a developer needs full history to bisect or inspect old commits, they can deepen or unshallow later:

~~~bash
git fetch --deepen=100 origin main
~~~

If files from another area are needed, expand the sparse set:

~~~bash
git sparse-checkout add services/pricing
~~~

If the full working tree is needed:

~~~bash
git sparse-checkout disable
~~~

These operations address different limitations: deepen adds commit history; lazy fetch retrieves missing objects; sparse add/disable changes the checkout scope.

## 7. Practicing each mechanism individually

Replace the example URL with a remote repository you are authorized to clone. Use a test repository or a read-only clone to observe behavior.

### 7.1. Trying shallow clone

~~~bash
git clone --depth 1 --branch main https://example.com/team/project.git project-shallow
cd project-shallow
git rev-parse --is-shallow-repository
git log --oneline --all
git ls-files
~~~

Observations:

- The repository is marked shallow.
- Displayed history is short.
- `git ls-files` can still list all tracked files of the main snapshot.

Fetch more history:

~~~bash
git fetch --deepen=20 origin main
git log --oneline --all --max-count=30
git rev-parse --is-shallow-repository
~~~

If full history is needed and the remote has all objects:

~~~bash
git fetch --unshallow origin
git rev-parse --is-shallow-repository
~~~

### 7.2. Trying partial clone

~~~bash
git clone --filter=blob:none https://example.com/team/project.git project-partial
cd project-partial
git config --get remote.origin.promisor
git config --get remote.origin.partialclonefilter
~~~

Observe the promisor and filter configuration. Because this clone checks out the full snapshot by default, Git may download the blobs of files in the current snapshot during checkout; the filter still defers blobs referenced only by unneeded historical commits. When opening a file or running a command that needs missing blob contents, Git can fetch the object from the remote.

To see the impact more clearly in a large repository, combine this with sparse checkout in the next section. If you clone normally and immediately check out all source code, Git may have to download most blobs needed for the working tree, reducing initial savings.

### 7.3. Trying sparse checkout on an existing clone

~~~bash
git clone https://example.com/team/monorepo.git project-sparse
cd project-sparse
git sparse-checkout init --cone
git sparse-checkout set services/catalog shared/java
git sparse-checkout list
git status -sb
~~~

Observe the working tree: the selected directories have contents, while other areas are not checked out. Branch history and refs remain as before.

Expand and then restore in full:

~~~bash
git sparse-checkout add services/pricing
git sparse-checkout list
git sparse-checkout disable
~~~

After disable, tracked files in the current snapshot are checked out in full. If the repository is a partial clone, this operation can trigger downloading missing blobs.

## 8. Limitations to plan ahead for

### 8.1. Shallow clone and history-dependent operations

The following tasks may require additional commits:

- Finding the merge base between two branches.
- Rebasing or merging a branch whose history lies outside the shallow boundary.
- Running `git bisect` across a long span of history.
- Using `git blame` or `git log` to trace old changes.
- Generating changelogs or versions from distant tags.

When a command cannot find the required ancestor or history, check:

~~~bash
git rev-parse --is-shallow-repository
git log --oneline --all --decorate
~~~

Then deepen intentionally or unshallow if the task requires full history.

### 8.2. Partial clone and remote connectivity

If a required object is not yet local, Git needs to contact the promisor remote to lazy-fetch it. Network-isolated CI environments or expired credentials can cause file reads to fail.

Before running offline tasks, ensure the needed objects have been downloaded or use a full clone suited to your needs. Do not assume `git clone --filter=blob:none` has already downloaded all file contents.

### 8.3. Sparse checkout and external tools outside Git

Some IDEs, formatters, build tools, or scripts assume all source directories are present. With sparse checkout, they may report missing projects or skip modules not in the working tree.

Select all required directories such as source, shared libraries, build scripts, schemas, test fixtures, and configuration. When a build needs a module outside the sparse set, use `git sparse-checkout add` to expand it instead of concluding the repository is missing files.

### 8.4. Sparse index is a separate option

Sparse checkout can use a sparse index to reduce the number of entries in the index in very large repositories:

~~~bash
git sparse-checkout init --cone --sparse-index
~~~

A sparse index collapses directory portions outside the sparse set into directory entries instead of keeping every individual file entry in the index. It can improve performance for certain Git operations.

However, external tools that read the index structure directly may not yet be compatible with a sparse index. Enable it only when your Git version and team tooling support it; sparse checkout can still be used without a sparse index.

## 9. How to verify you chose the right mechanism

Use the following commands to inspect instead of relying solely on the directory name or clone output:

| What to verify | Command | What to observe |
|---|---|---|
| Whether the repository is shallow | git rev-parse --is-shallow-repository | true or false |
| Partial clone filter | git config --get remote.origin.partialclonefilter | For example, blob:none |
| Promisor remote | git config --get remote.origin.promisor | Usually true |
| Sparse paths | git sparse-checkout list | List of currently selected directories |
| Tracked files in the index | git ls-files | List of tracked paths; sparse checkout does not remove them from the repository |
| Working tree | git status -sb | Status of currently checked-out files and local changes |

You can also view branches and remotes:

~~~bash
git branch -avv
git remote -v
git status --short --branch
~~~

Do not use `git ls-files` alone to conclude that sparse checkout is not working: this command lists tracked files in the index, including paths currently absent from the working tree due to sparse patterns. If sparse index is enabled, some commands have options to show a condensed view that can represent directories outside the sparse set as directory entries.

## 10. Choosing a configuration by scenario

| Scenario | Suggested configuration | Reason |
|---|---|---|
| CI only builds the current commit | git clone --depth 1 ... | No need to download the entire commit history |
| Need full history, but repository has many large blobs | git clone --filter=blob:none ... | Keeps the commit graph, defers blobs |
| Monorepo, working on one service, clone is already full | git sparse-checkout set services/catalog | Shrinks working tree without re-downloading the repository |
| Large monorepo, need a few services and shared libraries | --filter=blob:none --sparse then sparse-checkout set | Both defers blobs and limits checkout |
| CI needs to be fast while using part of a monorepo | --depth 1 --filter=blob:none --sparse | Reduces history, initial objects, and working tree; verify build tasks have enough data |
| Investigating a years-old regression | Full clone or deepen/unshallow | Needs complete ancestry, tags, and old commits |

There is no single optimal configuration for every repository. Measure clone time, local object size, number of checked-out files, and build time in your actual workflow.

## 11. Common misconceptions

- **Shallow clone only downloads a few files:** false. It limits commit history; the checked-out snapshot can still contain all files.
- **Partial clone never downloads blobs:** false. Blobs are deferred and can be lazy-fetched when an operation needs their contents.
- **Sparse checkout deletes files from the repository:** false. Files outside the sparse set are simply not checked out into the working tree.
- **Sparse checkout automatically reduces commit history:** false. It does not change history depth.
- **Partial clone automatically reduces the number of checked-out files:** false if the full repository is still checked out; sparse checkout is needed to restrict paths.
- **Shallow clone and partial clone are mutually exclusive:** false. You can combine depth and object filters in the same clone command.
- **Sparse checkout is a security measure:** false. It is not an access boundary.
- **Cloning with --filter guarantees the clone was filtered:** not necessarily. The server must support filtering; check warnings and promisor/filter configuration.
- **Disabling sparse checkout restores missing history:** false. `git sparse-checkout disable` expands the working tree; to fetch history, use fetch/deepen or unshallow.
- **Unshallowing downloads blobs skipped by a filter:** not necessarily. Shallow history and object filters are two separate mechanisms; a partial clone can still retain its filter after history is expanded.

## 12. Checklist before choosing

- [ ] Identify whether the problem is commit history, object size, or number of files in the working tree.
- [ ] Check whether the task needs git log, blame, bisect, merge base, or old tags.
- [ ] Confirm the remote supports partial clone if using --filter.
- [ ] Select the right branch and branch ref scope if using --depth.
- [ ] Select all required source, shared code, build scripts, test data, and config directories if using sparse checkout.
- [ ] Check promisor/filter, shallow state, and sparse list after cloning.
- [ ] Verify build/test works in the selected working tree.
- [ ] Evaluate the impact on offline workflows, IDEs, and team tooling.
- [ ] Document how to expand history, fetch additional objects, and widen sparse paths when needed.

## 13. Key takeaways

Shallow clone reduces commit history depth; partial clone filters downloaded objects, typically deferring blobs; sparse checkout limits which paths are present in the working tree. They address three independent bottlenecks and can be combined. For CI that only needs the latest commit, shallow clone is often sufficient. For blob-heavy repositories, partial clone enables downloading contents on demand. For monorepos, sparse checkout keeps only the projects you are working on visible. When combining them, check history, promisor/filter, and sparse paths, and ensure builds and tests have all the source files and objects they need.

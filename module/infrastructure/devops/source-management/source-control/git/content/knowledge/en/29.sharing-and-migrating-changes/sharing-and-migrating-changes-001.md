# Exporting Source Code at a Reference Point with git archive

When you need to send source code to testers, create a release package, provide examples to partners, or store a snapshot for building, you may want to export the exact contents of a commit without sending the entire Git history. The `git archive` command creates an archive package from the file tree of a Git reference point such as a commit, branch, or tag.

Unlike clone or bundle, an archive contains only the files belonging to the selected snapshot and does not include commit history or the `.git` metadata directory. Therefore, it is suitable for creating a source code package at a specific version, though it is not a method for backing up an entire repository.

This lesson covers how to select the export reference point, create ZIP or TAR archives, set a root directory using a prefix, restrict paths, control contents with `.gitattributes`, and check limitations regarding uncommitted changes, submodules, and Git LFS.

## 1. What is git archive used for?

### 1.1. Exporting a snapshot of a Git tree

Basic syntax:

~~~bash
git archive <tree-ish>
~~~

Where `tree-ish` is a Git reference or expression that resolves to a directory tree, commonly:

- HEAD: the current commit.
- Branch name: for example `main`.
- Tag: for example `v1.2.0`.
- Commit ID: for example `4a1b2c3`.
- Fetched remote-tracking branch: for example `origin/main`.

Example exporting source code at a release tag:

~~~bash
git archive --format=zip --output=../app-v1.2.0.zip v1.2.0
~~~

The command creates a ZIP file in the parent directory of the working tree, containing the files recorded in the tree of tag `v1.2.0`.

If `HEAD` is used, the archive reflects the current commit of `HEAD`:

~~~bash
git archive --format=zip --output=../app-current.zip HEAD
~~~

### 1.2. An archive is not a copy of the working tree

`git archive` exports content from the Git tree of the selected `tree-ish`. It does not grab everything currently sitting on disk.

Therefore, a standard archive:

- Includes tracked files already present in the selected commit.
- Does not include changes that are only staged and not yet committed.
- Does not include unstaged changes in the working tree.
- Does not include untracked files.
- Does not include the `.git` directory, commit history, or local configuration.

For example, if you edit `README.md` without committing, running `archive HEAD` still exports the version of `README.md` in the `HEAD` commit. The uncommitted edits on disk are not included in the package.

Check status before exporting:

~~~bash
git status --short --branch
git log -1 --oneline --decorate
~~~

If the goal is to export a reviewed or released commit, choose the exact tag or commit instead of accidentally using `HEAD` while it points to a development branch.

### 1.3. When should you use git archive?

Suitable scenarios:

- Creating a source code package for a release.
- Sending a snapshot to testers or partners.
- Providing example source code without sharing internal history.
- Creating a source package for a build pipeline.
- Exporting a subdirectory of a monorepo.
- Saving the contents of a tag for later reference.

If the recipient needs to continue development with commit history, branches, and remotes, use `clone` or `bundle` instead of `archive`.

## 2. Selecting the right reference point to export

### 2.1. Exporting from HEAD

~~~bash
git archive --format=zip --output=../source-head.zip HEAD
~~~

Use this when you want to export a snapshot of the current commit. Before running, check the branch and commit:

~~~bash
git branch --show-current
git log -1 --format="%H %s"
~~~

The `archive` command does not modify the branch, index, or working tree.

### 2.2. Exporting from a branch

~~~bash
git archive --format=zip --output=../source-main.zip main
~~~

A branch is a movable reference. If `main` advances to a new commit later, re-running the command may produce a different archive.

To record the exact exported point, save the commit ID:

~~~bash
git rev-parse main
~~~

In release documentation, record both the tag/branch name and the actual commit ID.

### 2.3. Exporting from a release tag

~~~bash
git archive --format=zip --output=../app-v2.1.0.zip v2.1.0
~~~

Tags are commonly used to mark release versions. For an annotated tag, Git resolves the tag to the tagged object and retrieves the corresponding commit's tree.

Check which commit a tag points to:

~~~bash
git show -s --format=fuller v2.1.0
git rev-parse 'v2.1.0^{commit}'
~~~

Tags can be moved or recreated if someone has permission to alter refs. For release processes requiring strict control, store the commit ID and verify the tag according to your team's tag signing/verification policy.

### 2.4. Exporting from a remote-tracking branch

To export the latest snapshot you have fetched from the remote:

~~~bash
git fetch origin
git archive --format=zip --output=../app-origin-main.zip origin/main
~~~

`origin/main` is a local remote-tracking branch. It only reflects the remote state at your most recent fetch; if the remote has new commits that you haven't fetched yet, the archive will not include those commits.

You do not need to check out a branch to archive a `tree-ish` already present in the repository.

### 2.5. Exporting from a specific commit ID

~~~bash
git archive --format=zip --output=../app-4a1b2c3.zip 4a1b2c3
~~~

Use a commit ID when you need to recreate a specific snapshot or when a branch has moved. For automated workflows, store the full commit ID rather than just the branch name.

You can check the tree that a commit references:

~~~bash
git rev-parse '4a1b2c3^{tree}'
~~~

The command prints the OID of the corresponding tree, helping confirm the selected snapshot.

## 3. Creating archives in ZIP and TAR formats

### 3.1. Creating a ZIP file

Syntax:

~~~bash
git archive --format=zip --output=../project-v1.0.zip v1.0.0
~~~

ZIP is convenient for Windows, macOS, and Linux users because many extraction tools support it.

You can view the archive formats currently supported by Git:

~~~bash
git archive --list
~~~

If ZIP does not appear in the list, check the Git version and packaging you are using.

### 3.2. Creating a TAR file

~~~bash
git archive --format=tar --output=../project-v1.0.tar v1.0.0
~~~

TAR is commonly used in Unix/Linux environments, containers, and build pipelines.

To create a gzip-compressed TAR in Bash:

~~~bash
git archive --format=tar v1.0.0 | gzip -c > ../project-v1.0.tar.gz
~~~

Git generates a TAR stream; `gzip` compresses that stream. This approach does not require Git to support a separate format named `tar.gz`.

On Windows, you can create a ZIP directly or use Git Bash/WSL and the `gzip` utility if the workflow requires TAR.GZ.

### 3.3. Using --output to write a file

Example:

~~~bash
git archive --format=zip --output=../release.zip v1.2.0
~~~

If `--output` is omitted, the archive data is written to standard output:

~~~bash
git archive --format=tar v1.2.0 > ../release.tar
~~~

Explicitly specifying `--format` makes the command easier to read and avoids relying on Git inferring the format from the filename.

### 3.4. Archive filenames should indicate the source reference point

Name the package with a version or commit:

~~~text
app-v1.2.0.zip
app-v1.2.0.tar.gz
app-4a1b2c3.zip
~~~

Avoid generic names like `latest.zip` if the package needs to be archived long-term, because that name does not show which snapshot was packaged.

## 4. Setting the root directory in an archive with --prefix

### 4.1. Why is a prefix needed?

If an archive is extracted into a directory that already contains other files, the root-level files may get mixed with the existing contents.

Use `--prefix` to place all paths inside the archive under a single directory:

~~~bash
git archive --format=zip --prefix=app-v1.2.0/ --output=../app-v1.2.0.zip v1.2.0
~~~

When extracted, the structure will look like:

~~~text
app-v1.2.0/
├── README.md
├── src/
├── docs/
└── pom.xml
~~~

The prefix should end with a `/` so Git concatenates it with the paths in the tree.

### 4.2. Prefix does not rename files in the repository

`--prefix` only changes paths inside the archive. It does not rename files in the working tree, does not change the index, and does not create a commit.

You can use a directory name with the version, product name, or build ID so recipients know which version the package belongs to.

### 4.3. Combining prefix with TAR

~~~bash
git archive --format=tar --prefix=app-v1.2.0/ v1.2.0 | gzip -c > ../app-v1.2.0.tar.gz
~~~

When extracted, the files still reside under the `app-v1.2.0` directory.

## 5. Exporting only part of a repository with pathspec

### 5.1. Exporting a subdirectory

`git archive` accepts pathspecs after the `tree-ish`. Use `--` to separate the revision from the paths:

~~~bash
git archive --format=zip --output=../docs-v1.2.0.zip v1.2.0 -- docs
~~~

The command exports only the contents in the `docs` directory belonging to the tree of tag `v1.2.0`.

### 5.2. Exporting multiple directories

~~~bash
git archive --format=zip --output=../source-subset.zip HEAD -- src docs scripts
~~~

The archive contains the specified paths and their corresponding sub-contents.

If you specify subdirectories, root-level files such as `README.md` or `LICENSE` may be excluded. Explicitly add the required paths:

~~~bash
git archive --format=zip --output=../source-package.zip HEAD -- README.md LICENSE src
~~~

### 5.3. Pathspec must belong to the tree-ish

The archive retrieves paths from the tree of the selected commit. An untracked file or one newly created in the working tree will not appear simply because you list its path in the pathspec.

If the pathspec does not match a path in the `tree-ish`, Git may report an error or fail to export the expected contents. Check the paths in the commit:

~~~bash
git ls-tree -r --name-only v1.2.0
~~~

Do not use pathspec as a way to add local uncommitted files to an archive. If you need to package files generated outside Git, perform a separate step and clearly document their source.

## 6. Controlling contents with .gitattributes

`git archive` can apply several special attributes to decide which files are exported and to substitute placeholders within file contents.

### 6.1. Excluding files from an archive with export-ignore

You can mark paths to be excluded from the archive using the `export-ignore` attribute.

Example in `.gitattributes`:

~~~gitattributes
docs/internal/meeting-notes.md export-ignore
*.map export-ignore
~~~

When exporting an archive, paths matching the rules will be skipped:

~~~bash
git archive --format=zip --output=../public-source.zip v1.2.0
~~~

This attribute is useful for excluding internal documentation, map files, or development-only files from a distributed source package.

Remember:

- `export-ignore` only affects the archive output.
- The file may still exist in commits and Git history.
- Anyone with access to the repository can still read that file.
- Do not use `export-ignore` as a secret protection measure or as a substitute for repository access control.

If a file contains a password, token, or private key, do not commit it. If it has already been committed, treat it as a secret leak incident.

### 6.2. Substituting commit information with export-subst

The `export-subst` attribute allows Git to replace placeholders in the form `$Format:...$` inside files when creating an archive.

For example, add to `.gitattributes`:

~~~gitattributes
VERSION.txt export-subst
~~~

Contents of `VERSION.txt` in the repository:

~~~text
Project build information
Commit: $Format:%H$
Commit date: $Format:%cI$
Subject: $Format:%s$
~~~

When archiving from a commit:

~~~bash
git archive --format=zip --output=../project-release.zip v1.2.0
~~~

Git replaces the placeholders with information from the archived commit. The file in the working tree and its contents when viewed directly from the commit retain the placeholders; the substitution applies only to the exported copy.

Some useful format strings:

| Placeholder | Content |
| --- | --- |
| %H | Full commit ID |
| %h | Abbreviated commit ID |
| %cI | Committer date in strict ISO 8601 format |
| %s | Commit subject |

Do not place tokens, passwords, or secret data in placeholders. `export-subst` is merely a commit metadata substitution mechanism, not a secret management system.

### 6.3. Using attributes from the exported commit

By default, Git reads `.gitattributes` from the tree being archived. Therefore, `export-ignore` and `export-subst` rules are versioned alongside the commit.

This ensures the same commit has consistent export rules even if the branch later modifies `.gitattributes`.

### 6.4. --worktree-attributes

You can instruct Git to use `.gitattributes` from the current working tree:

~~~bash
git archive --worktree-attributes --format=zip --output=../custom-export.zip HEAD
~~~

This option is useful when testing uncommitted export rules. However, file contents in the archive still come from the selected `tree-ish`, while attribute decisions can come from the working tree.

Therefore, the result may not fully reflect the policy committed at that point. For reproducible release archives, use the attributes in the commit rather than `--worktree-attributes`, unless there is a clear reason.

## 7. Exporting an archive from a remote

### 7.1. Using --remote

`git archive` can request a remote to provide an archive directly:

~~~bash
git archive --remote=ssh://git@example.com/team/project.git --format=tar v1.2.0
~~~

This command requires the server to support the `git-upload-archive` service. Not all Git hosting providers enable or permit this service.

If the server does not support it, the command may report that `upload-archive` is unsupported or fail to open the service. In that case, fetching/cloning the repository locally and running `git archive` on the downloaded ref is the common alternative.

### 7.2. Specifying the server-side program with --exec

In some environments, the path to the server-side `upload-archive` program is not in the default location. You can specify it with `--exec`:

~~~bash
git archive --remote=ssh://git@example.com/team/project.git --exec=git-upload-archive --format=tar v1.2.0
~~~

Only use this when the administrator or server documentation provides the exact required path/program. This option does not automatically enable the service on the server.

### 7.3. Remote archive does not take a remote name

The value of `--remote` is the server-side repository address, not simply a configured remote name like `origin`. For example:

~~~bash
git archive --remote=origin v1.2.0
~~~

is not a universal way to request an archive from a remote named `origin`. Pass the URL or repository address accepted by the `upload-archive` service.

For standard workflows, a more controllable approach is:

~~~bash
git fetch origin --tags
git archive --format=zip --output=../app-v1.2.0.zip v1.2.0
~~~

The archive is created from the locally fetched ref, and you can verify the commit ID before exporting.

## 8. Verifying the archive after creation

### 8.1. Checking that the file exists and has a reasonable size

After the command succeeds, confirm that the output file was created. Do not rely solely on wrapper script messages.

In PowerShell:

~~~powershell
Get-Item ..\app-v1.2.0.zip | Select-Object Name, Length, LastWriteTime
~~~

In Bash:

~~~bash
ls -lh ../app-v1.2.0.zip
~~~

If the file is 0 bytes or unusually small, check the ref, pathspec, format, and write permissions.

### 8.2. Listing ZIP contents

Using unzip:

~~~bash
unzip -l ../app-v1.2.0.zip
~~~

Or 7-Zip:

~~~bash
7z l ../app-v1.2.0.zip
~~~

Check the following points:

- Is the root directory/prefix correct?
- Are `README`, `LICENSE`, and necessary build files present?
- Are internal files that should be excluded absent?
- Are all required source code and resource files included for distribution?

### 8.3. Listing TAR contents

~~~bash
tar -tf ../app-v1.2.0.tar
~~~

For TAR.GZ:

~~~bash
tar -tzf ../app-v1.2.0.tar.gz
~~~

Inspect the listing before extracting into a shared location or release directory.

### 8.4. Computing a checksum for the exported package

So recipients can verify the file was not altered during transfer:

In PowerShell:

~~~powershell
Get-FileHash ..\app-v1.2.0.zip -Algorithm SHA256
~~~

On Linux/macOS:

~~~bash
sha256sum ../app-v1.2.0.zip
~~~

Send the checksum through an appropriate release channel. A checksum only verifies integrity against a reference value; it does not prove the package source is trustworthy if both the package and checksum come from the same compromised source.

### 8.5. Verifying the archive matches the right commit

Record the commit ID before exporting:

~~~bash
git rev-parse v1.2.0
git rev-parse 'v1.2.0^{tree}'
~~~

You can store this information in release notes or artifact metadata. If the tag is moved later, the commit ID helps identify the exact snapshot used to build the package.

## 9. Limitations with submodules and Git LFS

### 9.1. git archive does not automatically package submodule contents

In a Git tree, a submodule is represented by a gitlink pointing to a commit in a child repository. `git archive` does not automatically clone or recursively export submodule repository contents.

If the project depends on submodules, an archive of the parent repository may lack contents needed to build. Check:

~~~bash
git submodule status
git ls-tree HEAD
~~~

The packaging process must fetch the exact submodule commit recorded in the parent repository's tree, then create a separate archive or check out the submodule contents at that commit and place them in the appropriate path within the release package.

Do not arbitrarily grab the latest branch of a submodule; it may differ from the commit pinned by the parent repository.

### 9.2. Git LFS: archives may contain pointers instead of large content

Git stores Git LFS pointer files in the commit tree. Therefore, a standard `git archive` exports the committed pointer blob and does not automatically download the actual LFS content to substitute into the archive.

A pointer looks like:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:...
size ...
~~~

If the release package requires actual images, videos, or binary models, running `git archive` alone may produce a package containing pointer text.

You can check the pointer in a commit:

~~~bash
git show v1.2.0:assets/scene.fbx
~~~

If the output is a pointer, another packaging step is required to fetch the actual content. For example:

1. Check out the exact tag/commit in a separate working tree.
2. Run `git lfs pull` to download the corresponding objects.
3. Confirm the file contents are real data.
4. Use a packaging tool on the materialized working tree directory.

Do not assume `git archive` runs smudge filters to download LFS objects. Always inspect the final artifact contents before releasing.

### 9.3. Checking components outside the Git tree

A complete build package may additionally require:

- Submodule contents.
- Checked-out Git LFS objects.
- Auto-generated files.
- Dependencies downloaded from a package registry.
- Uncommitted environment configurations.

These components need to be managed with an explicit build/packaging process. `git archive` only exports the Git tree at the selected reference point along with any applicable archive rules.

## 10. Security when exporting source code

### 10.1. Archives do not automatically strip secrets

If a commit contains `.env` files, tokens, private keys, or passwords, the archive may include them unless excluded via `export-ignore` or a pathspec.

Do not rely on `export-ignore` to handle secret incidents. This attribute only affects the archive, while the secret remains in the repository and commit history.

Before sharing a package:

~~~bash
git status --short
git ls-tree -r --name-only v1.2.0
~~~

Review the paths and use an appropriate secret scanner. If a committed credential is discovered, revoke or rotate the credential before cleaning history.

### 10.2. Archives omit .git but can still expose data

Omitting `.git` prevents recipients from receiving commit history and local configuration. However, contents in the commit tree may still include:

- Internal source code.
- Documentation not intended for external parties.
- Configuration files with private endpoints.
- Accidentally committed certificates or keys.
- Sample data containing personal information.

Define the scope of distributable paths and inspect the archive before sending.

### 10.3. Do not use archive as a history data removal mechanism

Excluding a file from an archive does not remove the file from Git. If a file must be removed from a repository, handle the tracked content and, if needed, the history via a separate procedure. If the file contains credentials, revoke the credentials first.

## 11. Comparing archive with clone, bundle, and checkout

| Method | Contents | Has commit history? | Purpose |
| --- | --- | --- | --- |
| git archive | Snapshot of a tree-ish | No | Source package at a reference point |
| git clone | Repository and working tree | Yes, depending on clone/filter | Development and collaboration |
| git bundle | Packaged objects and refs | Yes, within bundle scope | Transferring repository/refs without direct remote |
| git checkout/switch | Updates working tree to match ref | Repository keeps local history | Switching versions to work |

Choose the tool based on your needs:

- Recipient only needs source code of one version: `archive`.
- Recipient needs to continue committing, branching, or merging: `clone`.
- Need to transfer history via file without a remote connection: `bundle`.
- Need to switch versions in an existing repository: `switch`/`checkout`.

An archive is usually smaller because it contains no history, but it cannot be used as a full Git repository to continue committing or viewing logs.

## 12. End-to-end example: creating a source package for a release

Suppose the team is preparing to release version `v2.4.0`.

### Step 1 — Fetch tag and confirm reference point

~~~bash
git fetch origin --tags
git show -s --format=fuller v2.4.0
git rev-parse 'v2.4.0^{commit}'
~~~

Confirm the tag points to the approved commit.

### Step 2 — Check archive attributes

~~~bash
git show v2.4.0:.gitattributes
~~~

Check whether `export-ignore` and `export-subst` match the release policy. If needed, inspect `VERSION.txt` in the commit:

~~~bash
git show v2.4.0:VERSION.txt
~~~

### Step 3 — Create ZIP with prefix

~~~bash
git archive --format=zip --prefix=product-v2.4.0/ --output=../product-v2.4.0.zip v2.4.0
~~~

### Step 4 — Inspect contents

~~~bash
unzip -l ../product-v2.4.0.zip
~~~

Confirm `README`, `LICENSE`, source code, and required resources are in the package, and that internal files to be excluded do not appear.

### Step 5 — Check dependencies outside the Git tree

~~~bash
git submodule status
git lfs ls-files
~~~

If the project uses submodules or LFS, perform a step to retrieve the corresponding contents at the pinned commit and package them additionally. Do not release a package containing only pointers or empty submodule directories when the application needs the real contents.

### Step 6 — Generate checksum and save metadata

In PowerShell:

~~~powershell
Get-FileHash ..\product-v2.4.0.zip -Algorithm SHA256
~~~

Record:

- Tag: `v2.4.0`.
- Full commit ID.
- Archive filename.
- SHA-256 of the archive.
- Packaging tool version if required by the process.
- Additional submodule/LFS components included.

Then upload the artifact to the approved release storage location.

## 13. Quick reference table

| Need | Command |
| --- | --- |
| Export HEAD to ZIP | git archive --format=zip --output=../source.zip HEAD |
| Export tag to ZIP | git archive --format=zip --output=../release.zip v1.2.0 |
| Export to TAR | git archive --format=tar --output=../source.tar HEAD |
| Export TAR.GZ | git archive --format=tar HEAD, then pipe through gzip -c > ../source.tar.gz |
| Set root directory in archive | git archive --format=zip --prefix=app-v1.2.0/ --output=../app.zip v1.2.0 |
| Export only docs directory | git archive --format=zip --output=../docs.zip HEAD -- docs |
| Export multiple directories | git archive --format=zip --output=../subset.zip HEAD -- src docs |
| List supported formats | git archive --list |
| View commit of tag | git rev-parse 'v1.2.0^{commit}' |
| View tree of tag | git rev-parse 'v1.2.0^{tree}' |
| View paths in commit | git ls-tree -r --name-only v1.2.0 |
| Inspect ZIP archive | unzip -l ../source.zip |
| Inspect TAR archive | tar -tf ../source.tar |
| Compute SHA-256 in PowerShell | Get-FileHash ..\source.zip -Algorithm SHA256 |

## 14. Summary

`git archive` exports a snapshot of a `tree-ish` into an archive without carrying commit history or the `.git` directory. Choosing the right `HEAD`, branch, tag, or commit lets you create a source code package at the desired reference point. Use `--format` to choose ZIP/TAR, `--output` to write to a file, `--prefix` to create a root directory, and pathspecs to limit which parts of the tree are exported.

`.gitattributes` can control archiving via `export-ignore` and `export-subst`. `--worktree-attributes` allows testing rules from the working tree, though it can make export policies differ from committed metadata. Always verify the file list, checksum, and dependent components before releasing.

Remember that archives do not include uncommitted changes, do not automatically recurse into submodule contents, and typically contain pointers rather than actual Git LFS contents. If recipients need Git history, use `clone` or `bundle`. If you need a source package of a single version, `git archive` is a simple and verifiable option.

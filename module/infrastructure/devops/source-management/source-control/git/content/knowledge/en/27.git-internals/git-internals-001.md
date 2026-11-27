# Object Model: Blob, Tree, Commit, and Annotated Tag

Git stores history using immutable **objects** identified by a content hash. The four most common object types are **blob**, **tree**, **commit**, and **tag**. They link together to describe file contents, directory structure, project snapshots, and release milestones.

Understanding this model helps explain why Git can compare two versions, why multiple files with identical content can share data, why a branch is simply a movable reference, and why an annotated tag differs from a lightweight tag. This is the foundation for reading history, inspecting objects, and understanding how Git stores data in a repository.

## 1. Git stores snapshots using objects

A commit in Git is not a patch containing only the lines that changed. A commit points to a **tree** that describes the entire directory state at the time of the commit. That tree, in turn, points to blobs containing file contents and subtrees describing subdirectories.

```text
Commit C
  |
  +-- tree: root
        |
        +-- blob: README.md
        |
        +-- tree: src
        |     |
        |     +-- blob: Main.java
        |     +-- blob: Parser.java
        |
        +-- tree: docs
              |
              +-- blob: guide.md
```

Each object has a content identifier (object ID, commonly abbreviated as OID). A tree stores the name, mode, type, and OID of each entry inside it. A commit stores the OID of the root tree along with history metadata. An annotated tag stores information about a tagged object, typically a release commit.

Objects link to one another by OID rather than by absolute paths on disk. Therefore, the same commit can be checked out into multiple different working directories while still referencing the same object database.

## 2. The four main object types

| Object type | What does it store? | References |
|---|---|---|
| **blob** | Raw bytes of a file's content | Does not reference other objects |
| **tree** | List of entries in a directory: name, mode, type, and OID | Blobs, subtrees, or gitlinks to submodule commits |
| **commit** | A snapshot along with metadata and commit message | One tree and zero or more parent commits |
| **tag** | Metadata of an annotated tag and tag message | A tagged object, usually a commit |

File names are not stored in blobs. File names and locations live in trees. A commit does not directly store all file contents; it points to a tree. An annotated tag does not create a new snapshot; it creates an object describing the label and the target object.

## 3. Blob: file content

A blob (binary large object) stores the content bytes of a file. It does not store the file name, path, modification time, or operating system file ownership.

For example, two files in different directories with identical byte contents can point to the same blob:

```text
tree root
  |
  +-- README.md --------+
  |                     |
  +-- docs/intro.txt ---+----> blob B
```

Git identifies blobs by content, so it does not need to store two separate object copies just because a file appears at two different paths. If the content changes, the OID will generally differ; hash collisions are theoretically possible, though Git uses algorithms designed to make this very difficult to exploit.

You can retrieve the OID of a committed file's content:

```bash
git rev-parse HEAD:README.md
```

Then inspect the object type and content:

```bash
git cat-file -t HEAD:README.md
git cat-file -p HEAD:README.md
git cat-file -s HEAD:README.md
```

- **-t** prints the object type; for a regular file the result is `blob`.
- **-p** prints the object content.
- **-s** prints the content size in bytes.

The expression **HEAD:README.md** means resolving the object at path `README.md` in the tree referenced by the `HEAD` commit. If the file does not exist in that commit or the path is incorrect, Git reports that the object cannot be resolved.

### Creating and inspecting blobs with hash-object

You can ask Git to compute the OID for content without adding a file to the repository:

```bash
printf 'hello\n' | git hash-object --stdin
```

This command returns the OID of the corresponding blob. By default, `git hash-object` only computes the hash; it does not write the object into the object database.

Add the **-w** option to write the object into the repository:

```bash
printf 'hello\n' | git hash-object -w --stdin
```

Git prints the OID of the newly written object. Replace **<blob-oid>** with the actual OID to inspect it:

Strings enclosed in angle brackets such as `<blob-oid>`, `<commit-oid>`, or `<target-oid>` are placeholders in examples; replace them with real OIDs before running the commands.

```bash
git cat-file -t <blob-oid>
git cat-file -p <blob-oid>
git cat-file -s <blob-oid>
```

This is a useful plumbing command when exploring the object database or building tooling. An object written with `-w` that is not yet referenced by any branch, tag, or commit may remain an unreachable object until it is linked into history.

## 4. Tree: directory structure

A tree describes the direct entries inside a directory. Each entry consists of a mode, object type, OID, and name. Example output of:

```bash
git ls-tree HEAD
```

might look like this:

```text
100644 blob 7a1b...    README.md
040000 tree 9c2d...    src
040000 tree 1e8f...    docs
100755 blob 4d6a...    scripts/build.sh
```

The columns represent:

1. **Mode**: the file type/permissions tracked by Git for that entry.
2. **Type**: the type of object being referenced.
3. **OID**: the object identifier.
4. **Name**: the entry name inside the directory.

Some common modes:

| Mode | Meaning |
|---|---|
| **100644** | Regular file without the executable bit |
| **100755** | Regular file with the executable bit |
| **120000** | Symbolic link; the blob content stores the link target |
| **040000** | Directory represented by a subtree |
| **160000** | Gitlink to a submodule commit |

A tree only lists entries immediately inside that directory. When encountering a tree entry, Git references a subtree to describe the contents of deeper directories. Empty directories are not stored as standalone entries in a tree; Git stores files and the structure needed to reconstruct paths that have content.

Inspect the root tree and all entries underneath:

```bash
git cat-file -p 'HEAD^{tree}'
git ls-tree -r HEAD
git ls-tree -r --name-only HEAD
```

- **HEAD^{tree}** resolves the current commit to its root tree.
- **-r** recurses into subtrees.
- **--name-only** prints only the paths, omitting mode/type/OID.

A tree does not store timestamps or file owners like a filesystem. Git focuses on content, names, structure, and the minimal modes required to reconstruct the working tree.

## 5. Commit: snapshot and history

A commit object records a snapshot of the project and information about how that snapshot participates in history. A typical commit contains:

- The OID of the root tree.
- One or more parent commits; the first commit of a repository normally has no parent.
- Author information: the person who created the change.
- Committer information: the person who created that commit object.
- Timestamps and corresponding time zones.
- Commit message.
- Optional additional headers such as a GPG/SSH signature or encoding.

You can inspect the contents of a commit object:

```bash
git cat-file -p HEAD
```

Example structure:

```text
tree <root-tree-oid>
parent <parent-commit-oid>
author Nguyen Van A <a@example.com> 1700000000 +0700
committer Nguyen Van A <a@example.com> 1700000100 +0700

Add parser support
```

The OIDs and timestamps in the example are purely illustrative. The `parent` header may appear multiple times in a merge commit; a root commit has no `parent` header.

**Author** is the person credited with making the change. **Committer** is the person who created the current commit object. These two fields can differ—for example, when a maintainer cherry-picks a commit from another author.

A commit references a tree, so it describes a complete snapshot at that point in time. Git determines what changed between two commits by comparing the trees they reference, rather than requiring the commit itself to store a full precomputed diff.

### Parents form history

A commit with a single parent usually sits on a linear history:

```text
A --- B --- C
            ^
           HEAD
```

A merge commit has two or more parents:

```text
      B ---- C
     /        \
A --           M
     \        /
      D ---- E
```

Commit M references the tree resulting from the merge and has both parents. Parent relationships allow Git to traverse history, find merge bases, determine ancestors, and compare branches.

Inspect commit parents:

```bash
git cat-file -p HEAD
git rev-list --parents -n 5 HEAD
git log --oneline --graph --decorate --all
```

`git rev-list --parents` displays commit OIDs along with their parent OIDs. `git log --graph` draws the history relationships so you can easily see branches and merges.

## 6. Annotated tag: an object for a milestone with metadata

Git provides two common ways to create tags:

- **Lightweight tag**: a simple ref pointing directly to an object, usually a commit. It does not create a separate tag object.
- **Annotated tag**: creates a `tag` object containing the tag name, tagger, timestamp, message, and target object. The tag can be digitally signed if needed.

Create a lightweight tag:

```bash
git tag v1.0.0
```

Create an annotated tag:

```bash
git tag -a v1.0.0 -m "Release 1.0.0"
```

You can also specify the target commit:

```bash
git tag -a v1.0.0 <commit-oid> -m "Release 1.0.0"
```

An annotated tag object has the general structure:

```text
object <target-oid>
type commit
tag v1.0.0
tagger Nguyen Van A <a@example.com> 1700000200 +0700

Release 1.0.0
```

- **object** is the OID of the tagged object.
- **type** indicates the target object type, usually `commit`.
- **tag** is the label name.
- **tagger** is the person who created the annotated tag and when it was created.
- Everything after the blank line is the tag message.

Annotated tags are generally suited for releases because they carry a message and tagger metadata. Lightweight tags are suited for temporary labels or simple internal markers. A tag object can point to another object type—even to another tag object—though pointing to a commit is the typical case.

Check the tag's object type:

```bash
git cat-file -t v1.0.0
```

If it is an annotated tag, the result is `tag`. If it is a lightweight tag pointing directly to a commit, the result is normally `commit`.

Inspect the contents of an annotated tag:

```bash
git cat-file -p v1.0.0
git show v1.0.0
```

For an annotated tag, `cat-file -p` displays the tag object; `git show` goes on to display the tagged object and its associated content.

## 7. Object ID and content-addressable storage

Git computes the OID from the object type, content size, and the content itself. Conceptually, the data before hashing has the form:

```text
<type> <size>\0<content>
```

For example, a blob containing the six bytes `hello` followed by a newline has the conceptual header:

```text
blob 6\0hello\n
```

The NUL byte in the representation above terminates the header; it is not part of the content. Git hashes the entire object byte stream including the header, not just the file content alone.

Because the OID depends on type, size, and content:

- Identical content and identical object type produce the same OID within the same object format.
- Changing a single byte of content produces a different OID.
- The same bytes with a different object type also produce a different OID.
- The file name does not affect a blob's OID; file names are stored in trees.

Git has traditionally used SHA-1 with 40-hex-character OIDs. Modern versions of Git also support repositories using SHA-256 with 64-hex-character OIDs. The object format algorithm is chosen when initializing a repository; you cannot simply flip a regular configuration setting to convert an entire existing SHA-1 repository to SHA-256.

Check the object format:

```bash
git rev-parse --show-object-format
```

Initialize a new repository using SHA-256 (an example for a new repository only):

```bash
git init --object-format=sha256 new-project
```

Not all older Git tools or hosting systems support SHA-256, so check compatibility before selecting an object format for projects requiring broad collaboration.

An OID enables Git to identify objects by content. It is not an encryption mechanism: hashing does not keep content secret. Nor does an OID by itself prove who created an object; commit/tag signatures and identity verification workflows address trust at a different layer.

## 8. Object database: loose objects and packfiles

Objects are stored in the repository's object database. For a loose object, Git typically compresses the object content with zlib and stores it at a path derived from the OID:

```text
.git/objects/ab/cdef...
```

In a repository with a standard Git directory, the first two characters of the OID form the directory name, and the remaining characters form the file name. However, you should not open and edit data directly inside the object database. This is internal data managed by Git.

When a repository accumulates many objects, Git can bundle them into packfiles to save space and improve lookup efficiency. Packfiles can use delta compression: instead of storing repeated copies of whole objects, Git stores only the differences relative to another object where appropriate. An accompanying index file helps Git locate objects within the pack.

You can view object database statistics:

```bash
git count-objects -v
```

This reports the number of loose objects, disk usage, and related pack information. Exact output depends on the repository and garbage collection state.

Git can run garbage collection to pack objects and prune unreferenced objects according to retention policies:

```bash
git gc
```

Normally Git manages this automatically; users do not need to run it frequently. Do not manually delete files inside `.git/objects` or packfiles, as doing so can corrupt history and the object database.

## 9. Refs and HEAD are not objects

An important point is that branch and tag names themselves are generally not objects. They are **refs** (references) containing an object OID.

For example:

```text
refs/heads/main  ------> commit C
refs/tags/v1.0.0 ------> tag object T
                              |
                              +----> commit C

HEAD -----------------> refs/heads/main
```

- Branch `main` is a ref pointing to the current commit on the branch.
- Annotated tag `v1.0.0` is a ref pointing to a tag object; the tag object in turn points to the commit.
- Lightweight tag `v1.0.0` is a ref pointing straight to the commit.
- `HEAD` is normally a symbolic ref pointing to the current branch. In detached HEAD state, it points directly to a commit OID.

When creating a new commit on a branch, Git creates a new commit object and updates the branch ref to point to the new OID. The old object is not modified in place; it continues to exist as long as it remains referenced or has not been pruned by garbage collection.

Inspect refs:

```bash
git show-ref
git show-ref --heads
git show-ref --tags
git symbolic-ref HEAD
git rev-parse HEAD
```

`git symbolic-ref HEAD` displays the branch that `HEAD` is tracking in the normal state. If `HEAD` is detached, this command cannot resolve a symbolic ref; use `git rev-parse HEAD` to get the current commit OID.

## 10. Tracing a commit from end to end

You can use the following sequence of commands to trace the objects of the current commit:

**Step 1: Identify the commit.**

```bash
git rev-parse HEAD
git cat-file -t HEAD
```

The object type of `HEAD` should be `commit`.

**Step 2: Read the commit object.**

```bash
git cat-file -p HEAD
```

Look for the `tree` line to get the root tree OID and the `parent` line to see the parent commit.

**Step 3: Inspect the entries in the tree.**

```bash
git ls-tree HEAD
git cat-file -p 'HEAD^{tree}'
```

Read the mode, type, OID, and name of each entry. If an entry is a subtree, you can continue using that tree's OID with `git ls-tree`.

**Step 4: View the blob content of a file.**

```bash
git cat-file -t HEAD:README.md
git cat-file -p HEAD:README.md
```

Git resolves the path inside the commit's tree to a blob and displays its contents.

**Step 5: Inspect tags if the commit has any.**

```bash
git tag --points-at HEAD
git cat-file -t v1.0.0
git cat-file -p v1.0.0
```

The last `cat-file -p` command is for an annotated tag. If the tag is lightweight, its object type will be `commit` and the command will display the commit object instead of tag metadata.

This inspection chain shows that a commit does not contain every file directly. It links to a tree, the tree links to blobs/subtrees, and a tag can add another layer of metadata pointing to the commit.

## 11. How do the index and working tree relate to objects?

The working tree consists of the files you see and edit. The index (staging area) is the prepared state for the next commit. The object database stores the recorded objects.

When running:

```bash
git add README.md
```

Git reads the file content, applies clean filters/attributes if configured, creates or reuses the corresponding blob, and updates the index so the `README.md` entry points to that blob. The index also retains mode and path information.

When creating a commit, Git writes tree objects from the index state and then creates a commit object referencing that tree. Therefore, staged content forms the basis of the new snapshot, not necessarily whatever is currently in the working tree if the file was modified again after staging.

You can instruct Git to create a tree object from the index using a plumbing command:

```bash
git write-tree
```

The command returns the OID of the tree created from the current index. It does not create a commit or move a branch on its own. If the tree object is not referenced by any ref, it may remain an unreachable object until used in a commit or another object.

This explains the three commonly referenced areas:

| Area | Role |
|---|---|
| Working tree | File contents currently being worked on |
| Index | Snapshot prepared for the next commit |
| Object database | Blobs, trees, commits, tags, and objects stored by Git |

## 12. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| A blob stores both file name and content | A blob only stores content bytes; names and paths live in trees |
| A commit is a diff | A commit points to a snapshot tree and parents; diffs are computed by comparing snapshots |
| A tree is a physical folder in `.git` | A tree is an object describing the entries inside a directory |
| A branch name is a commit object | A branch is a ref pointing to a commit and can move |
| Lightweight tags and annotated tags are the same | A lightweight tag is a direct ref; an annotated tag has its own tag object |
| Every file has a separate blob even with identical content | Identical content can share the same blob object |
| Git stores all filesystem metadata | Git tracks a minimal set of modes, not full owners, mtimes, or all filesystem permissions |
| An OID encrypts the content | An OID is a digest identifying content; it does not provide confidentiality or creator authentication |
| You can edit files directly in `.git/objects` | The object database is internal data; use plumbing commands to inspect or manipulate it |

## Conclusion

Git builds history out of objects linked by OIDs. Blobs store file content, trees store directory structure and modes, commits store snapshots along with parents/metadata, and annotated tags store information about a labeled milestone. Branch and tag names are refs pointing to objects; they do not replace objects and can point differently depending on tag type. Use `git cat-file`, `git ls-tree`, `git rev-parse`, `git hash-object`, and `git count-objects` to observe this model without directly modifying the repository's internal data.

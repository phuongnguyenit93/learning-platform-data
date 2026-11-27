# Content-Addressable Storage and the Role of Object Hashes

Git identifies data using **content-addressed storage**: every object is identified by a hash computed from the serialized content of that object. Because the hash depends on the data, the same object in a repository always has the same object ID; if the data changes, the ID changes as well. Thanks to this mechanism, Git can store snapshots, reuse duplicate data, and verify the integrity of history.

An Object ID (OID) is commonly called a hash or digest. OIDs appear in commits, trees, tags, the index, the reflog, and Git lookup commands. To understand how Git stores history, you need to distinguish object hashes from branch/tag names, understand which components are included in the hash computation, and know what a hash can and cannot prove.

## 1. What is content-addressable storage?

In conventional storage systems, data is typically looked up by file name or location. With content-addressable storage, the system computes an identifier from the data itself and uses that identifier as the address. Git applies this idea to its objects.

For example, when two files in different directories have the exact same byte content, Git can store a single shared blob object. File names and paths are not stored in the blob; they live in tree objects. Therefore, renaming a file without changing its content does not change the blob ID, even though the tree containing that path will change.

Conceptual model:

```text
Object content
       |
       v
Serialization: type + size + content bytes
       |
       v
Object hash function
       |
       v
Object ID (OID)
       |
       v
Address to store, look up, and reference the object
```

An OID is not a commit sequence number. It does not tell you whether a commit is newer or older, which branch contains the commit, or which release version the commit belongs to. It solely identifies an object based on its content and the repository's object format.

## 2. How does Git compute an object ID?

Git does not hash the raw file content bytes alone. Before hashing, Git prepends a header consisting of the object type and content size, in the form:

```text
<type> <size>\0<payload>
```

Where:

- `<type>` is the object type, such as `blob`, `tree`, `commit`, or `tag`.
- `<size>` is the payload size in bytes, represented as a decimal number.
- `\0` is the NUL byte separating the header and the payload.
- `<payload>` is the actual serialized content of the object.

For a repository using SHA-1, the calculation can be pictured as:

```text
OID = SHA1("blob " + decimal(size) + NUL + payload)
```

For a blob object containing `hello\n`, Git hashes the header string `blob 6`, a NUL byte, and then the six content bytes. The header ensures that identical byte sequences belonging to different object types produce different IDs. Size is also part of the hashed input.

Git uses the hash function specified by the repository's object format. SHA-1 is the long-standing default format, while Git now also supports the SHA-256 object format in compatible versions and systems. Therefore, you should not assume every OID has the same length or is always SHA-1.

## 3. The four main object types

Git stores history using several object types with distinct roles:

| Object type | What does the payload contain? | Role |
|---|---|---|
| Blob | File content | Stores content bytes; does not store file name or path |
| Tree | List of entries with mode, name, and child OID | Describes directory structure and links files/subtrees |
| Commit | Tree OID, parent commits, author, committer, timestamps, and message | Records a snapshot along with its relationship to prior history |
| Annotated tag | Target OID, target type, tag name, tagger, timestamp, message, and optional signature | Attaches a metadata-rich label to an object, usually a release commit |

### Blob: hash of file content

A blob stores file content. File names are not stored in blobs, so two files with identical content can share the same blob ID.

Example:

```text
src/config.yml  ----+
                   +----> blob 9f... (same content)
backup/config.yml -+
```

If you rename `src/config.yml` to `src/app-config.yml` without modifying its contents, the blob can still be reused. The tree containing the old name and the tree containing the new name have different contents, so they have different OIDs.

### Tree: hash of directory structure

A tree object records child entries. Each entry has a mode, name, and OID of a blob or subtree. Because names and directory layout live in trees, renaming a file or moving a directory changes the corresponding tree, even when the file's blob has not changed.

Inspect the tree of the current commit:

```bash
git ls-tree HEAD
git ls-tree -r HEAD
```

`git ls-tree` displays the mode, object type, OID, and entry name. The `-r` option recurses into subtrees.

### Commit: hash of snapshot and parent history

A commit object references a tree representing the snapshot at the time of the commit. It also contains author information, committer information, timestamps, a commit message, and one or more parent commits.

Illustrative example of commit content:

```text
tree 8a...
parent 3c...
author An Nguyen <an@example.com> 1730000000 +0700
committer An Nguyen <an@example.com> 1730000000 +0700

Add payment validation
```

The commit hash depends on the tree, parents, and metadata together. Consequently, the same file changes committed at a different time, with a different message, or with a different parent will normally have a different OID.

A merge commit typically has two or more parents. Rebasing creates new commits with new parents, so replayed commits receive new OIDs even when the file changes match the original commits.

### Annotated tag: object with its own metadata

An annotated tag is a standalone object that can contain a message and a signature. A lightweight tag is merely a ref pointing directly to the target object, so it has no separate tag object.

Inspect the contents of an annotated tag:

```bash
git cat-file -p refs/tags/v1.2.0
```

A tag object's payload contains the target OID and tagger information. If the tag is signed, the signature is also part of the tag object's content; changing the content or target object results in a different tag object.

## 4. An OID is an object address, not a branch name

Branches and tags are **refs** (references) pointing to objects. They are not object IDs and do not share the same immutability property.

Example:

```text
refs/heads/main  ---------> commit 4a...
refs/heads/feature -------> commit 9c...
refs/tags/v1.2.0 --------> tag object 7e... ---> commit 4a...
```

When you create a new commit on `main`, Git updates the `refs/heads/main` ref to point to the new commit. The old commit remains intact as long as it is still referenced or has not been pruned. Conversely, the OID of an already-created object never changes when a branch moves.

`HEAD` is normally a symbolic ref pointing to the current branch, such as `refs/heads/main`. In detached HEAD state, `HEAD` directly contains a commit OID rather than a branch name.

Inspect refs:

```bash
git symbolic-ref -q HEAD
git rev-parse HEAD
git show-ref --heads --tags
```

The first command shows the branch `HEAD` points to if it is in the symbolic state; the second prints the current commit OID; the third lists branch and tag refs with their corresponding OIDs.

## 5. Hands-on: computing and writing objects with git hash-object

`git hash-object` lets you compute an object's OID without creating a commit. For example, compute the ID of a file:

```bash
git hash-object README.md
```

By default, the command computes the OID without writing the object to the object database. To both compute and store the object, use `-w`:

```bash
git hash-object -w README.md
```

You can supply content from standard input:

```bash
git hash-object --stdin < README.md
```

Store an object computed from standard input:

```bash
git hash-object -w --stdin < README.md
```

After writing with `-w`, the object can be looked up by its OID:

```bash
git cat-file -t <OID>
git cat-file -s <OID>
git cat-file -p <OID>
```

- `-t` prints the object type.
- `-s` prints the payload size.
- `-p` displays the decoded content formatted according to the object type.

If the object is a blob, `-p` prints the file content. If it is a tree, commit, or tag, Git displays the corresponding structure. `hash-object` is very useful for observing that identical content in the same object format produces the same blob OID.

### Testing content immutability

In a test repository, create two files with identical byte contents:

```bash
git hash-object file-a.txt
git hash-object file-b.txt
```

If both files have identical byte contents and are processed the same way, both commands print the same OID. Then change one character in `file-b.txt` and recompute; the OID will change.

The file name is not included in the blob payload. However, if you stage or commit these two files, their names and paths are recorded in the tree object.

## 6. Looking up objects with git cat-file

`git cat-file` is the tool for reading objects by OID or by a revision expression that resolves to an OID.

For example, read the current commit:

```bash
git cat-file -t HEAD
git cat-file -p HEAD
```

Get the tree OID that the commit points to:

```bash
git rev-parse 'HEAD^{tree}'
```

Read the tree:

```bash
git cat-file -p 'HEAD^{tree}'
```

Read a blob by path at a commit:

```bash
git rev-parse 'HEAD:README.md'
git cat-file -p 'HEAD:README.md'
```

`HEAD:README.md` uses the `revision:path` syntax. Git locates the object referenced by that path in `HEAD`'s tree and returns the corresponding OID or content.

To look up many objects efficiently, `git cat-file --batch` accepts a list of OIDs or revisions from standard input and outputs information for each object. Batch mode is useful for scripts analyzing large repositories because it avoids spawning a separate Git process for each object.

## 7. How do object IDs help Git reuse data and detect changes?

### Reusing duplicate content

Because blobs are identified by content, if multiple files or multiple snapshots contain the same data bytes, Git can reference the same blob object. This saves space and avoids storing redundant copies.

For example, a `LICENSE` file that remains unchanged across 100 commits does not require 100 separate blobs. The trees for each snapshot can continue referencing the same blob OID.

### Detecting mismatched content

When reading an object, Git can recompute the hash from the header and payload to verify that it matches the OID. If data is corrupted or altered without updating the identifier accordingly, integrity checks can catch the error.

Check the object database:

```bash
git fsck --full
```

`git fsck` verifies the connectivity and consistency of objects in the repository, including objects that may no longer be referenced by any ref. This command is useful when suspecting object corruption or missing references in history.

### Small changes can cascade into many new OIDs

If you edit a file, that file's blob gets a new OID. The tree containing that file gets a new OID; parent trees may change as well; the commit referencing the new tree also gets a new OID. If that new commit becomes the parent of other commits, any recreated child commits also get new OIDs.

```text
Edit a byte in a file
       |
       v
New blob OID
       |
       v
New tree OID
       |
       v
New commit OID
       |
       v
Recreated child commits have a new parent
```

This is why rebasing, amending, or filtering history changes commit hashes even when only a single file in an older commit was modified.

## 8. OIDs in loose objects and packfiles

When Git writes a new object, it may be stored as a **loose object** inside `.git/objects`. The path is derived from the OID: the first two characters form the directory name, and the remaining characters form the file name. Object content is compressed, typically with zlib.

Example path format:

```text
.git/objects/ab/cdef0123456789...
```

In large repositories, Git commonly packs objects into **packfiles** to save disk space and reduce file count. Packfiles can use delta compression: storing differences between related objects rather than repeating full payloads.

The key point is that an OID is computed from the uncompressed logical object content, not from the compressed bytes or the object's position inside a packfile. Git can change how an object is packed without changing that object's OID.

Check object statistics:

```bash
git count-objects -vH
```

This command shows the count of loose objects, disk usage, and pack information. To inspect object details inside a pack, you can use `git verify-pack -v` against the corresponding `.idx` file in `.git/objects/pack/`.

## 9. SHA-1 and SHA-256 in Git

A SHA-1 OID normally has 40 hexadecimal characters (160 bits). Git also supports repositories using SHA-256 with 64-hexadecimal-character OIDs (256 bits), depending on the Git version and hosting/tooling support.

Check the object format of the current repository:

```bash
git rev-parse --show-object-format
```

The output is usually `sha1` or `sha256`.

Create a test repository using SHA-256:

```bash
git init --object-format=sha256 sha256-lab
```

This command requires the installed Git version to support the SHA-256 object format. Before using it in a real project, confirm that your Git server, CI tools, IDEs, Git libraries, and other integrations all support the same format. SHA-1 and SHA-256 repositories cannot be treated as drop-in equivalents simply by changing OID length; you need compatibility mechanisms supported by your ecosystem.

SHA-1 has practical collision attacks in cryptography. Git includes collision-detection mitigations in certain code paths, but SHA-1 should not be viewed as a modern collision-resistant security foundation. SHA-256 provides a wider safety margin, though choosing an object format also depends on server and tooling compatibility.

## 10. Hashes are not encryption and do not prove identity

Some common misconceptions:

- **A hash is not encryption.** You cannot decrypt an OID to recover the object content. To read an object, you need the object data in the repository.
- **A hash does not hide content.** Anyone with access to the repository can still read blobs and commits; an OID is an identifier, not a data-confidentiality mechanism.
- **A hash does not prove who created an object.** Commits have author/committer fields, but those fields are just data inside the object, not verified proof of identity.
- **A hash does not replace digital signatures.** A signed commit or signed tag can prove that the holder of a key signed the corresponding object, provided the key and identity are properly verified.
- **Collisions are a theoretical and practical possibility depending on the algorithm.** Do not interpret an OID as a value guaranteed unique under all possible conditions.

To verify release provenance, use commit/tag signatures and proper key management workflows. To protect private content, use repository access controls and appropriate security mechanisms rather than relying on OIDs being hard to guess.

## 11. Workflow for tracing OIDs in a repository

When you need to see how a file or commit is stored as objects, you can follow these steps:

1. **Check the object format.** Run `git rev-parse --show-object-format` to see the repository's hash algorithm.
2. **Find the commit OID.** Use `git rev-parse HEAD` or `git log --oneline`.
3. **Read the commit object.** Use `git cat-file -p HEAD` to view the tree, parents, author, committer, and message.
4. **Get the tree OID.** Use `git rev-parse 'HEAD^{tree}'`, then read the tree with `git cat-file -p` or `git ls-tree`.
5. **Find the file's blob.** Use `git rev-parse 'HEAD:path/to/file'`, then inspect it with `git cat-file -t` and `-p`.
6. **Check integrity.** Run `git fsck --full` if investigating missing or corrupted objects.

Example:

```bash
git rev-parse --show-object-format
git rev-parse HEAD
git cat-file -p HEAD
git ls-tree HEAD
git rev-parse 'HEAD:README.md'
git cat-file -p 'HEAD:README.md'
```

These commands show the path from the `HEAD` ref to the commit, from the commit to the tree, and from the tree to the blob containing the file's content.

## 12. Hands-on exercises

In a test repository:

1. Create two files with identical byte contents and run `git hash-object` on both. Record the OIDs.
2. Rename one file while keeping its content unchanged; stage the change and compare the blob OID against the previous tree entry.
3. Modify a single character in the file, recompute the OID, and explain why the blob hash changed.
4. Run `git cat-file -t`, `-s`, and `-p` on a blob OID, then try them on `HEAD` to compare object types.
5. Use `git cat-file -p HEAD` to find the tree and parent commits; use `git ls-tree` to inspect file and directory OIDs.
6. Create a new commit and compare the commit OID before and after. Explain the effect of the tree, parent, author/committer, and message.
7. Run `git count-objects -vH` and `git fsck --full` to view statistics and check the object database.
8. In a separate test-only repository, try `git init --object-format=sha256` if your Git version supports it and compare the OID length with a SHA-1 repository.

You have completed the exercises when you can explain that Git hashes both the header and payload, distinguish blob/tree/commit/tag objects, understand why branches can move while object OIDs remain constant, and recognize the security limitations of hashes.

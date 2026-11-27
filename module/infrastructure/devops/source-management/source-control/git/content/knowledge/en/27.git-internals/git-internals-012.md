# Why Commit IDs Change When Content, Metadata, or Parents Change

## What is a Commit ID?

In Git, every commit is an object stored in the object database. Git assigns that object a content identifier (object ID or OID) by hashing the serialized data of the object.

Therefore, a commit ID is not a sequential number, a random string, or a server-issued identifier. It is computed directly from the content of the commit object itself. Two commits with identical object bytes and the same hash algorithm will have the exact same object ID; changing even a single byte in the object's data will almost certainly produce a different hash.

This explains why a commit can change its ID even when the visible source code appears unchanged. Metadata, parent commits, commit message, signatures, or tree structure all participate in the hashed data.

## How does Git hash an object?

Git does not hash only the raw payload of an object. Before hashing, Git constructs a byte stream of the general form:

~~~text
<type> <size>\0<payload>
~~~

Where:

- **type** is the object type, such as `blob`, `tree`, `commit`, or `tag`.
- **size** is the byte length of the payload.
- **\0** is the NUL byte separating the object header from the payload.
- **payload** is the actual object data.

For a commit object, Git hashes the object header together with the entire commit payload. Consequently, the object type, size, and every single byte of the object data affect the resulting object ID.

Conceptual example:

~~~text
commit 180\0
tree 0123...
parent 4567...
author Linh <linh@example.invalid> 1700000000 +0700
committer Linh <linh@example.invalid> 1700000100 +0700

Add report validation
~~~

The snippet above only illustrates the structure. The actual commit ID is computed from the exact serialized bytes of the object, not from formatted or re-wrapped text shown here.

### Hash algorithms and object formats

Traditional Git repositories use SHA-1 to produce 40-hex-character object IDs. Git now also supports repositories using SHA-256, producing 64-hex-character object IDs.

Check the object format of the current repository:

~~~bash
git rev-parse --show-object-format
~~~

Initialize a new repository using SHA-256:

~~~bash
git init --object-format=sha256 new-project
~~~

You cannot determine the algorithm merely by looking at an abbreviated hash string. Always inspect the repository's object format.

SHA-1 has collision weaknesses demonstrated in research and practice. Git includes mitigations against SHA-1 collision risks, yet an object ID should never be treated as a digital signature or proof of who authored a commit. Commit signatures, access controls, and server policies serve those goals.

A SHA-1 repository and a SHA-256 repository do not produce the same object ID for identical content because the hash algorithm and object format differ. Interoperability between repositories with different object formats also depends on the Git version and surrounding tooling; never unilaterally change the format of a shared repository.

## Structure of a commit object

A commit object's payload contains headers and a commit message. A typical commit has the general structure:

~~~text
tree <tree-object-id>
parent <parent-commit-id>
author <name> <email> <timestamp> <timezone>
committer <name> <email> <timestamp> <timezone>
[optional headers]

<commit message>
~~~

The bracketed `[optional headers]` indicate optionality, not literal text required in every commit.

Role of each component:

| Component | Role |
|---|---|
| `tree` | Root tree object describing the commit's file snapshot |
| `parent` | Parent commit; normal commits have one parent, merge commits have two or more |
| `author` | Person credited with creating the change and the author timestamp |
| `committer` | Person who created this commit object and the committer timestamp |
| optional headers | Additional metadata such as encoding, signatures, or merge tag information |
| commit message | Descriptive text of the commit, beginning after the blank line separating headers and message |

Headers follow a specific order and serialization. Whenever any part of the payload changes, the commit's object ID changes.

Inspect the structure of the current commit:

~~~bash
git cat-file -p HEAD
~~~

Or view the commit information in raw form:

~~~bash
git show --no-patch --pretty=raw HEAD
~~~

View author and committer metadata in a human-readable format:

~~~bash
git show --no-patch --pretty=fuller HEAD
~~~

`git cat-file -p` prints the decompressed payload of the object. It lets you read the tree, parents, author, committer, and message; the `commit <size>` object header is handled by Git outside the payload.

## How does snapshot content affect the commit ID?

A commit does not store the full contents of every file directly. The `tree` header points to a tree object representing the directory snapshot at that commit. That tree object points to blobs, subtrees, or gitlinks.

You can picture it as:

~~~text
Commit
  |
  +-- tree
       |
       +-- blob: src/App.java
       |
       +-- tree: config/
       |     |
       |     +-- blob: application.yml
       |
       +-- blob: README.md
       |
       +-- gitlink: libs/ui-kit
~~~

Blobs hold file content. Trees hold names, modes, entry types, and object IDs of each entry in a directory. A gitlink inside a tree points to a submodule commit.

### Changing file content

Suppose `src/ReportService.java` has content A. Git stores that content as a blob. When the content changes to B, the blob ID changes.

~~~text
Before:
tree T1
  └── ReportService.java -> blob A

After:
tree T2
  └── ReportService.java -> blob B
~~~

Because tree T2 references blob B instead of blob A, the tree ID changes. The commit points to tree T2 instead of T1, so the commit ID changes as well, even when parents and other metadata remain unchanged.

You can compute the blob ID of a file in the working tree:

~~~bash
git hash-object src/ReportService.java
~~~

This computes the object ID as a blob without writing the object to the object database unless `-w` is passed. The file path is not included in the blob payload; Git hashes the file contents as a blob object.

Inspect the blob stored by a commit for a path:

~~~bash
git rev-parse HEAD:src/ReportService.java
git cat-file -p HEAD:src/ReportService.java
~~~

These two commands return the object ID and the content of the blob referenced by `HEAD`'s tree.

### Adding or deleting files

Adding a new file adds an entry in the tree referencing the new blob. Deleting a file removes the corresponding entry from the tree. In both cases, the tree ID changes and the commit ID changes too.

~~~text
Before:
tree T1
  ├── App.java -> blob A
  └── README.md -> blob R

After adding LICENSE:
tree T2
  ├── App.java -> blob A
  ├── README.md -> blob R
  └── LICENSE -> blob L
~~~

Even when all existing files retain identical content, the tree differs because its entry list changed.

### Renaming or moving files

Git does not store a rename action as a separate object inside a commit. A rename is represented in the new snapshot by removing the entry at the old path and adding an entry at the new path.

If the file content did not change, the blob ID can remain the same. However, the tree containing the entry name and path has changed, so the tree ID and commit ID change.

When displaying history, Git can infer renames based on content similarity. That is rename detection during `diff`/`log` presentation; it does not mean the commit object stores a dedicated rename field.

### Changing file permissions or modes

A tree entry stores a mode—such as regular file, executable, symbolic link, or gitlink. Because the mode lives inside the tree, flipping the executable bit changes the tree ID even though the blob's content bytes are unchanged.

Example:

~~~bash
git update-index --chmod=+x scripts/deploy.sh
git diff --cached --summary
~~~

When the mode change is committed, the new tree holds a different mode and the commit ID changes.

### Changing symbolic links or submodules

For a symbolic link, Git stores the link's target path in the blob and marks the tree entry with symlink mode. Changing the link target changes the blob; changing the entry type or mode also affects the tree.

For a submodule, the tree entry uses gitlink mode and records the submodule commit ID pinned by the superproject. If the superproject updates the submodule to another commit, the gitlink changes, the tree ID changes, and the new superproject commit receives a different ID.

## Metadata that changes the commit ID

Even when the file snapshot is identical, changing metadata in the commit object produces a different payload.

### Author and committer are two distinct identities

Author is the person credited with originally creating the change. Committer is the person who created the commit object recording that change in the current history.

In a standard commit, both fields are usually identical. However, during a cherry-pick, rebase, or patch application from someone else, the original author is typically preserved while the committer becomes the person performing the new operation.

Example:

~~~text
author Alice <alice@example.invalid> 1700000000 +0700
committer Bob <bob@example.invalid> 1700005000 +0700
~~~

Changing the author or committer name or email changes the commit payload and therefore changes the object ID.

Configure identity for new commits:

~~~bash
git config user.name "Developer Name"
git config user.email "dev@example.invalid"
~~~

Inspect the metadata recorded in a commit:

~~~bash
git show --no-patch --pretty=fuller HEAD
~~~

Changing `user.name` or `user.email` in configuration only affects future commits. It does not modify metadata of existing commits.

### Timestamps and time zones

Author date and committer date are stored in the commit object as Unix timestamps alongside time zone offsets. The same instant represented with a different offset produces different header bytes and therefore a different object ID.

Example of two headers representing the same instant in time with different offsets:

~~~text
author Dev <dev@example.invalid> 1700000000 +0700
author Dev <dev@example.invalid> 1700000000 +0000
~~~

These two lines are not byte-identical, so commit objects containing them have different hashes.

Git can accept dates from environment variables or command flags during certain operations. When investigating why a commit ID differs, inspect both author date and committer date, not only name and email.

### Commit message

The commit message is part of the payload. Changing even a single character, punctuation mark, space, or trailing newline in the message changes the commit ID.

For example:

~~~text
Add report validation
~~~

and:

~~~text
Add report validation.
~~~

are two different messages. Even if all other fields are identical, the commit objects differ because the messages differ.

Edit the message of the latest commit:

~~~bash
git commit --amend -m "Add report validation"
~~~

Amending creates a new commit object. Even if file contents did not change, the committer date is normally updated; if the message or metadata differs, the ID is guaranteed to change.

### Encoding and optional headers

A commit can include extra headers such as `encoding` when the message uses an explicit character encoding, `gpgsig` when the commit is signed, or `mergetag` in certain tag-merge scenarios.

These headers are part of the commit object data. Adding, removing, or modifying them changes the payload and produces a different object ID.

A commit signature is not metadata stored outside the commit object. The signature header is embedded inside the signed commit object itself, so a signed commit has a different ID from an unsigned commit with otherwise identical content and metadata.

Signatures verify commits against cryptographic keys and trust policies. An object ID only identifies object content; it does not replace signature verification.

## How do parent commits affect the commit ID?

The `parent` header stores the object ID of each parent commit. Consequently, a commit's ID depends on the parent commits it references.

Example:

~~~text
A---B---C
~~~

Suppose commit `C` has parent `B`. If a new commit `B2` is created with the same snapshot and message as `B` but different metadata, `B2` gets a different ID. When replaying `C`'s changes onto `B2`, the new commit `C2` must reference `B2` as its parent.

~~~text
A---B---C

A---B2---C2
~~~

Even when `C2` has the exact same file snapshot and message as `C`, the different parent ID makes the commit object different. Therefore `C2` has a different ID than `C`.

This creates the chained linkage of Git history. Because every commit references its parents by object ID, rewriting an older commit cascades new IDs to all recreated descendant commits.

### Merge commits store multiple parents

A merge commit typically has two or more parents. Parent order is part of the commit object payload.

Example:

~~~text
A---B-------M
     \     /
      C---D
~~~

Commit `M` may record:

~~~text
parent B
parent D
~~~

If the parent order changed to `D` followed by `B`, the payload would differ and the object ID would differ, even though the resulting tree might be identical.

Parent order also affects the semantics of certain commands, such as selecting the mainline when reverting a merge with `git revert -m`. Therefore, parents cannot be treated as an unordered set.

## Why do amend, rebase, and cherry-pick usually create new commit IDs?

These operations create new commit objects or replay commits onto a different historical base. They never edit the bytes of an old commit in place.

### git commit --amend

`amend` replaces the tip commit with a new commit. It can change the tree, message, author/committer, or timestamps.

~~~bash
git commit --amend
~~~

If only changing the message:

~~~bash
git commit --amend -m "Clarify report validation"
~~~

Even if you only update metadata while keeping the tree identical, the commit object is still different. The old commit is not modified directly; the branch ref is simply moved to point to the new commit.

### git rebase

Rebase replays a branch's commits onto a different base. The parent of each replayed commit changes, and committer metadata is normally regenerated. Because parent IDs are part of the commit object, the new commits get new IDs.

~~~bash
git rebase main
~~~

If an old commit `C` had parent `B`, after rebasing it becomes `C'` with parent `B2`. Even if the patch and final snapshot match, `C'` is a distinct commit object.

Once one commit is replayed, its child commits must reference the new parent. Thus, rebasing a chain of commits usually generates new IDs for the entire replayed chain.

### git cherry-pick

Cherry-pick applies the changes from a source commit onto the current `HEAD` and creates a new commit:

~~~bash
git cherry-pick <source-commit>
~~~

The new commit normally has the current `HEAD` as its parent, which differs from the source commit's parent. Author metadata is usually preserved, while committer metadata reflects the new commit creation. Because either the parent or committer differs, the commit ID normally differs.

In principle, if you cherry-pick a commit onto the exact same parent and reproduce every byte identically, the object ID would match; in practice, operations generate new committer metadata, so you should never expect matching hashes.

### Squash merge

A squash merge combines changes from multiple commits into a single new commit on the target branch. The new commit has its own parent and metadata; even if the combined diff matches the source branch, its object ID is not any of the original commits' IDs.

## Changing refs does not change commit objects

Another important point: branch names and tag names are not stored inside commit objects.

A Git branch is fundamentally a ref pointing to a commit. For example, `refs/heads/main` points to commit `A`. When the branch moves from `A` to `B`, commits `A` and `B` are not modified; only the ref value changes.

~~~text
Before:
refs/heads/main -> A

After:
refs/heads/main -> B
~~~

Likewise, checking out another branch or creating a new branch does not alter the object IDs of existing commits.

Commands that only update refs:

~~~bash
git branch feature/report
git branch -f main <commit-id>
git update-ref refs/heads/recovery <commit-id>
~~~

These commands create or move references. They never alter the payload of commit objects.

### HEAD is also not part of a commit

`HEAD` normally points to the current branch via a symbolic ref, or directly to a commit in detached HEAD state. Moving `HEAD` with `switch` or `checkout` does not change any commit ID.

Inspect `HEAD` and the current branch:

~~~bash
git symbolic-ref -q HEAD
git rev-parse HEAD
git branch --show-current
~~~

In detached HEAD state, `symbolic-ref` returns no branch; that is not an error in any commit object.

### Two kinds of tags

A lightweight tag is simply a ref pointing to an object, usually a commit. Renaming or moving a lightweight tag ref does not change the commit object.

An annotated tag is a separate tag object containing the target object ID, tagger, timestamp, message, and optional signature. The tag object has its own object ID. Changing an annotated tag's metadata or message changes the tag object ID, without altering the commit the tag points to.

Inspect the object a tag references:

~~~bash
git cat-file -t v1.0.0
git show --no-patch --format=fuller v1.0.0
~~~

For an annotated tag, the object type is `tag`. For a lightweight tag pointing straight to a commit, the object type is `commit`.

## Changing an older commit can change the entire downstream hash chain

Because every commit embeds its parent IDs, Git history is chained together. If you rewrite an older commit, every recreated child commit must reference the new parent.

Initial example:

~~~text
A---B---C---D  main
~~~

Suppose `B` is rewritten as `B2`. When commits `C` and `D` are replayed onto `B2`, they become `C2` and `D2`:

~~~text
A---B---C---D

A---B2---C2---D2
~~~

`C2`'s tree may match `C` and `D2`'s tree may match `D`, but the parent chain differs. Therefore, all commit IDs after the rewrite point differ as well.

This is why rebasing or amending an already-shared commit causes local history to diverge from remote history and requires coordination before updating a shared branch.

If the old commits remain referenced by another branch, tag, or reflog, the old objects remain accessible. Moving the main branch to the new history does not mean the old objects were edited or immediately deleted.

## Analyzing a commit ID with Git commands

### View the current commit ID

~~~bash
git rev-parse HEAD
git log -1 --oneline --decorate
~~~

`git rev-parse HEAD` returns the full object ID of the current commit in the repository's object format.

### View object type and payload

~~~bash
git cat-file -t HEAD
git cat-file -s HEAD
git cat-file -p HEAD
~~~

- `-t` prints the object type.
- `-s` prints the payload size in bytes.
- `-p` displays the object contents in human-readable form.

For a commit, the payload shows the tree, parents, author, committer, optional headers, and message.

### View the tree and entries

~~~bash
git ls-tree HEAD
git ls-tree -r HEAD
~~~

`git ls-tree` prints mode, object type, object ID, and entry name in the tree. The `-r` option recurses into subtrees.

Inspect the tree object directly:

~~~bash
git rev-parse HEAD^{tree}
git cat-file -p HEAD^{tree}
~~~

The `^{tree}` syntax tells Git to resolve to the tree object of the specified commit or tag.

### Compare two commits

~~~bash
git diff <old-commit> <new-commit>
git diff-tree --no-commit-id --name-status -r <new-commit>
~~~

The first command compares the snapshots of two commits. The second lists files changed in the specified commit relative to its default parent; for merge commits, choose an appropriate comparison mode because there are multiple parents.

Inspect the metadata fields of two commits:

~~~bash
git show --no-patch --pretty=raw <old-commit>
git show --no-patch --pretty=raw <new-commit>
~~~

Compare tree IDs, parent IDs, author, committer, and message to pinpoint which component changed.

### Check a blob's object ID

~~~bash
git hash-object src/ReportService.java
git rev-parse HEAD:src/ReportService.java
~~~

The first command hashes the current working-tree file content as a blob. The second retrieves the blob ID referenced by the `HEAD` commit for that path. If they differ, the current content does not match the committed blob, or differences stem from read/clean filters that need further checking.

To hash content after applying clean filters configured for a path, Git provides the `--path` option:

~~~bash
git hash-object --path=src/ReportService.java src/ReportService.java
~~~

This is helpful in repositories using attributes and clean filters. When investigating hashes, compare using the same normalization rules Git applies.

## Practical example: same file content, different commit ID

Suppose you create a commit on a `feature` branch:

~~~bash
git add src/ReportService.java
git commit -m "Add report validation"
git rev-parse HEAD
~~~

Then amend solely to change the message:

~~~bash
git commit --amend -m "Add report input validation"
git rev-parse HEAD
~~~

Compare the commit IDs before and after. Even though the file did not change, the message changed and the committer date normally changed as well; therefore, a new object ID is produced.

To check whether the snapshot itself changed, compare the trees:

~~~bash
git rev-parse HEAD^{tree}
~~~

Record the tree ID before amending, then compare after amending. If the tree IDs match while the commit IDs differ, the difference lies in the commit object's headers or message, not in the file snapshot.

## Practical example: parent changes after rebase

Suppose `feature` was branched from `main` at `B`:

~~~text
A---B---C---D  feature
     \
      E---F    main
~~~

Rebase `feature` onto `main`:

~~~bash
git switch feature
git rebase main
~~~

After rebase:

~~~text
A---B---E---F---C'---D'  feature
~~~

`C'` and `D'` are new commits replayed on top of `F`. They have new parents and usually new committer metadata, so their IDs differ from `C` and `D`.

Verify:

~~~bash
git log --oneline --graph --decorate --all
git show --no-patch --pretty=raw <old-commit>
git show --no-patch --pretty=raw <new-commit>
~~~

In practice, replace `<old-commit>` and `<new-commit>` with the actual commit IDs recorded before and after rebasing.

## Things that do not change a commit ID

The following actions do not alter the bytes of an existing commit object:

- Renaming the branch pointing to the commit.
- Creating or deleting another branch.
- Switching `HEAD` to another branch or detached HEAD.
- Fetching additional objects or refs from a remote.
- Pushing a commit to a remote without rewriting objects.
- Adding a lightweight tag pointing to the commit.
- Moving a tag or branch ref.
- Changing `user.name` or `user.email` after the commit was already created.

They can change repository state or object reachability, but they do not modify stored commit objects.

The following operations usually produce a new commit ID:

- Editing snapshot contents and committing.
- Adding, deleting, renaming, or changing file modes in the snapshot.
- Changing parents or parent order.
- Changing author, committer, timestamps, or time zones.
- Changing the commit message.
- Adding, removing, or modifying headers such as signatures.
- Amending, rebasing, cherry-picking, or squashing to create a new commit.

The word "usually" is used because object IDs are determined by the final serialized bytes. If all object bytes remain identical under the same hash format, the ID will be identical regardless of which command produced the object.

## Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| A commit ID only hashes file contents | A commit ID hashes the entire commit object, including tree, parents, metadata, headers, and message |
| Renaming a branch changes commit IDs | A branch is just a ref pointing to a commit; changing a ref does not modify commits |
| Two commits with identical files share the same ID | Different parents, metadata, or messages still produce different IDs |
| Rebase merely moves old commits | Rebase replays commits onto a new parent, creating new commit objects |
| Blobs also store file names | Blobs store content; names and modes live in trees |
| Author and committer are always identical | They can differ, especially during cherry-pick, rebase, or patch application |
| SHA-1 is a verification signature | An object ID is a content identifier; digital signatures are a separate mechanism |
| Reset immediately deletes or edits commit objects | Reset mainly moves a ref and optionally updates index/working tree; old objects may still remain |
| Annotated tags and commits are the same object | An annotated tag has its own tag object pointing to the target object |

## Checklist when investigating why a commit ID changed

- [ ] Recorded the repository object format using `git rev-parse --show-object-format`.
- [ ] Inspected the commit object using `git cat-file -p`.
- [ ] Compared tree IDs before and after.
- [ ] Checked parents and parent order.
- [ ] Cross-checked author, committer, timestamps, and time zones.
- [ ] Compared the commit message and optional headers.
- [ ] Checked modes, paths, symlinks, and gitlinks if the tree changed.
- [ ] Identified whether the operation was an amend, rebase, cherry-pick, or squash.
- [ ] Distinguished commit object changes from branch/tag/HEAD ref updates.
- [ ] Verified full object IDs rather than only abbreviated hashes.

## Key takeaways

A commit ID is the hash of a serialized Git commit object, not just a hash of files. A commit object points to a tree and parents, and includes author, committer, timestamps, message, and optional headers. Trees, in turn, store names, modes, and object IDs of blobs, subtrees, or gitlinks. Therefore, changing snapshot content or structure, metadata, message, signatures, parents, or parent order all change the commit ID. Conversely, renaming branches, switching `HEAD`, or moving tags only changes refs without modifying commit objects. When investigating why a commit ID changed, compare the commit payload, tree ID, parents, and metadata rather than looking only at an abbreviated hash.


# What a Commit Contains: File Tree, Parent Commits, Author, Timestamp, and Message

A Git commit is not simply a copy of the project directory or a bundle containing changed lines of code. A commit is an object that records a snapshot of the file tree, links to parent commits, and stores metadata such as author, committer, timestamp, message, and possibly a digital signature. Together, these components form the traceable history of a repository.

In the **Creating Commits** chapter of the **SOURCE_CONTROL_GIT** module, this lesson explains the internal structure of a commit and how Git links a commit to trees, blobs, and parent commits. You will learn why the author differs from the committer, why a merge commit has multiple parents, why timestamps do not determine history order, and why even a small change in metadata can produce a completely different commit ID.

After this lesson, you will be able to:

- Describe the main fields in a commit object.
- Explain how a commit points to a tree snapshot instead of storing diffs directly.
- Distinguish between parent commits and the file tree recorded by a commit.
- Read parent relationships for regular commits, root commits, and merge commits.
- Distinguish between author, committer, author date, and commit date.
- Explain the role of the commit message, body, and trailers.
- Use git cat-file, git show, git log, git rev-list, and git ls-tree to inspect commit structure.
- Understand how a commit ID is generated from the entire object content and why amend/rebase creates a new ID.

## 1. A Commit Is a Structured Object

Git stores data in an object database. The basic object types include:

| Object | Role |
| --- | --- |
| blob | Stores file content |
| tree | Stores a list of entries in a directory: name, mode, and object ID |
| commit | Records a tree snapshot, parents, and history metadata |
| tag | Stores annotated tag metadata and points to another object |

A commit object typically has the following components:

~~~text
tree <tree-object-id>
parent <parent-commit-id>
author <name> <email> <timestamp> <timezone>
committer <name> <email> <timestamp> <timezone>

<commit message>
~~~

A commit can have multiple parent lines if it is a merge commit. A root commit has no parent line. In addition to the main fields, the object can contain other headers such as encoding, GPG/SSH signatures, or mergetag.

Key point: a commit points to a tree object representing the entire repository snapshot at commit time. The tree in turn points to blobs and subtrees. A commit does not store a diff of added/removed lines. Diffs are computed by Git when comparing the trees of two commits.

## 2. A Tree Is a Snapshot of the Directory Tree

The tree field in a commit contains the object ID of the root directory's tree. The tree describes the file structure at that commit.

For example, a tree might contain:

~~~text
100644 blob  1a2b3c...  README.md
100644 blob  4d5e6f...  app.js
100755 blob  7a8b9c...  scripts/build.sh
040000 tree  0a1b2c...  src
~~~

Key fields:

- Mode indicates the entry type and certain file attributes.
- Object type indicates whether the entry points to a blob or a tree.
- Object ID identifies the content or subtree.
- Entry name is the file or directory name within the tree.

Common modes:

| Mode | Meaning |
| --- | --- |
| 100644 | Regular file without execute permission |
| 100755 | Regular file with execute permission |
| 120000 | Symbolic link; the blob contains the target path |
| 040000 | Subtree, representing a directory |
| 160000 | Gitlink, referencing a submodule commit |

A tree does not store absolute file paths. Each tree stores the entries directly inside it; Git traverses subtrees to resolve the full path.

### Viewing a Commit's Tree

Get the object ID of the tree pointed to by HEAD:

~~~bash
git rev-parse 'HEAD^{tree}'
~~~

List entries in the root directory:

~~~bash
git ls-tree HEAD
~~~

List all files recursively:

~~~bash
git ls-tree -r HEAD
~~~

View the contents of a tree object:

~~~bash
git cat-file -p 'HEAD^{tree}'
~~~

To view the contents of a file at a commit:

~~~bash
git show HEAD:src/app.js
~~~

Git locates the src/app.js entry in HEAD's tree and reads the corresponding blob. If the file changed between two commits, the blob may have a different object ID; if the content is identical and unchanged by filters, Git can reuse the same blob.

## 3. Commits Record Snapshots, Not Lists of Changed Lines

Suppose commit A has tree T1 and commit B has tree T2:

~~~text
Commit A                  Commit B
   |                         |
   v                         v
 Tree T1                   Tree T2
   |                         |
   +-- README.md             +-- README.md
   +-- app.js                +-- app.js
   +-- config.json           +-- config.json
~~~

Commit B typically stores tree snapshot T2 with A as its parent. When you run git show or git diff to view changes between A and B, Git compares T1 with T2 and computes the differences.

This has several consequences:

- A commit contains the full state of the file tree, including files unchanged from the parent through object reuse.
- A commit does not need to store a new copy of every file if the blob/tree has not changed.
- Any two commits can be compared, even if they are not directly adjacent.
- A commit can have the same tree as its parent yet still be a distinct commit, such as an empty commit.

Creating an empty commit:

~~~bash
git commit --allow-empty -m "chore: mark maintenance checkpoint"
~~~

The new commit's tree may be identical to its parent's tree, but the commit object is still different because the parent, metadata, or message differs. Empty commits are occasionally useful for automation or marking events, though you should not create them without a clear purpose.

## 4. Parent Commits Form the History Graph

The parent field links a new commit to its predecessor. A regular commit has one parent:

~~~text
A --- B --- C
          ^
          HEAD
~~~

Commit C records B as its parent. Git can walk backward along parent links to reconstruct history.

### Root Commit

The first commit in a history has no parent:

~~~text
Root
  |
  v
  A --- B
~~~

There is no parent line in a root commit's object. A repository can have multiple root commits if histories were created independently and later combined.

### Merge Commit

When merging two branches, Git typically creates a commit with at least two parents:

~~~text
       A1 --- A2
      /        \
Base             M
      \        /
       B1 --- B2
~~~

Merge commit M has two parents. The first parent is typically the tip of the checked-out branch when the merge was run; the second parent is the commit being merged in. In an octopus merge, a commit can have more than two parents.

Parent order matters for commands like HEAD^1, HEAD^2, and how first-parent history is displayed. You should not view a merge commit merely as a commit containing combined changes; it also records which histories were joined together.

### Viewing a Commit's Parents

Display a commit along with its parents:

~~~bash
git rev-list --parents -n 1 HEAD
~~~

Get only the parent OIDs:

~~~bash
git show -s --format=%P HEAD
~~~

Get the tree OID:

~~~bash
git show -s --format=%T HEAD
~~~

Count the number of parents by reading the output of %P or running git cat-file -p HEAD. Zero parents means a root commit; one parent means a regular commit; two or more parents means a merge commit.

## 5. Commits Do Not Contain Branch Names

Branch names are not recorded inside the commit object. A branch is a movable ref pointing to the current commit of that branch.

For example:

~~~text
refs/heads/main -----------+
                           |
refs/heads/release --------+----> Commit C
                           |
HEAD ---------------------+
~~~

Multiple refs can point to the same commit. When a branch advances to a new commit, the ref changes, while the old commit still exists as long as it remains referenced or has not been garbage-collected.

Inspecting refs:

~~~bash
git show-ref --heads
git branch --contains HEAD
git rev-parse HEAD
~~~

A commit object does not record the branch name that created it, the remote URL, or the state of the working tree or staging area after the commit. That information belongs to refs, configuration, or repository state outside the commit.

## 6. Author and Committer Are Two Different Roles

A commit typically has two identity fields:

- **author**: the person who originally wrote the change recorded in the commit.
- **committer**: the person or process that created the current commit object.

In simple situations, the same person both writes and commits the change, so both fields match. However, when a commit is applied, rewritten, or generated by automation, they can differ.

For example:

~~~text
author Alice Nguyen <alice@example.com> 1763371200 +0700
committer Bob Tran <bob@example.com> 1763457600 +0700
~~~

In this example, Alice is the author of the change; Bob is the person who created the commit object stored in the repository. Timestamps are for illustration only.

### Common Scenarios

| Operation | Author | Committer |
| --- | --- | --- |
| Creating a regular commit | Person who created the change | Person who ran git commit |
| Cherry-pick | Usually preserves the author of the picked commit | Person who ran cherry-pick |
| Rebase | Usually preserves the author information of replayed commits | Person creating new commits during rebase |
| Applying a mailbox with git am | Follows the author metadata in the patch | Person applying the patch |
| Creating a commit via CI/bot | May be the designated author | Bot or account running the job |

These are common default behaviors; options and environment variables can alter metadata. For example, --reset-author or GIT_AUTHOR_* variables can change the author.

### Viewing Author and Committer

~~~bash
git show -s --format=fuller HEAD
~~~

The fuller output displays Author, AuthorDate, Commit, CommitDate, and the message. You can extract individual fields:

~~~bash
git show -s --format='%an <%ae>' HEAD
git show -s --format='%cn <%ce>' HEAD
git show -s --format='%aI' HEAD
git show -s --format='%cI' HEAD
~~~

In the format string:

- %an and %ae are the author name/email.
- %cn and %ce are the committer name/email.
- %aI is the author date in strict ISO 8601 format.
- %cI is the committer date in strict ISO 8601 format.

## 7. Timestamps and Timezones

In a commit object, author and committer dates are stored as:

~~~text
<Unix timestamp> <timezone offset>
~~~

For example:

~~~text
author Linh Le <linh@example.com> 1763371200 +0700
committer Linh Le <linh@example.com> 1763371500 +0700
~~~

The timestamp is the number of seconds since the Unix epoch. The timezone offset indicates the timezone offset recorded at the time, such as +0700 for UTC+7. Git does not store a zone name like Asia/Ho_Chi_Minh in this field.

The author date and committer date can differ. The author date usually reflects when the change was created; the committer date reflects when the current commit object was created.

### Timestamps Do Not Determine History Order

History order is determined by parent links, not solely by timestamps. System clocks can be wrong, commits can be imported from other machines, or dates can be overridden. Therefore:

- A commit with a newer timestamp is not necessarily a descendant of a commit with an older timestamp.
- Two commits on different branches can have overlapping or out-of-order timestamps.
- By default, git log sorts history based on the graph and display options; you should not infer ancestor relationships solely from dates.

To check an ancestor relationship, run:

~~~bash
git merge-base --is-ancestor <older> <newer>
~~~

The command returns exit code 0 if older is an ancestor of newer. This checks history relationships based on the parent graph, which is more reliable than comparing timestamps.

## 8. Where Does Git Get Identity and Time?

Default identity usually comes from Git config:

~~~bash
git config --global user.name "Linh Le"
git config --global user.email "linh@example.com"
~~~

Check the configuration source:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

Git also accepts environment variables that override configuration values:

| Variable | Affected Field |
| --- | --- |
| GIT_AUTHOR_NAME | Author name |
| GIT_AUTHOR_EMAIL | Author email |
| GIT_AUTHOR_DATE | Author date |
| GIT_COMMITTER_NAME | Committer name |
| GIT_COMMITTER_EMAIL | Committer email |
| GIT_COMMITTER_DATE | Committer date |

These variables are commonly used in scripts, CI, or when metadata needs to be reproduced. Avoid setting them persistently at the user level without intent, because subsequent commits could record incorrect identity or timestamps.

### Specifying the Author Date for a Commit

You can use the --date option:

~~~bash
git commit --date="2026-11-17T09:30:00+07:00" -m "docs: add setup guide"
~~~

--date specifies the author date for the commit. The committer date still reflects the time the commit is created, unless controlled separately via environment variables. Avoid altering timestamps just to make history look tidy; metadata should accurately reflect origin and workflow.

## 9. Commit Messages Consist of Subject, Body, and Trailers

After the metadata headers, a commit object has a blank line followed by the commit message.

A typical message structure looks like:

~~~text
fix(auth): reject expired session tokens

Check the token expiry before loading the user session.
Return a clear error so clients can refresh credentials.

Reviewed-by: Minh Nguyen <minh@example.com>
Issue: AUTH-142
~~~

Parts:

- **Subject**: the first line, concisely describing the purpose of the change.
- **Body**: explains context, rationale, and impact if needed.
- **Trailers**: conventional metadata lines at the end of the message.

Git stores the message as the text content of the commit object. Git does not inherently interpret every word in the subject or body; rules like Conventional Commits, Issue IDs, or Reviewed-by are conventions of teams and tools.

### Trailers Are Not Commit Object Headers

Lines like Signed-off-by, Co-authored-by, Reviewed-by, or Issue live inside the message body. They differ from the author, committer, and cryptographic signature headers at the top of the commit object.

For example:

- Signed-off-by is a trailer following the Developer Certificate of Origin (DCO) convention and is not itself a GPG/SSH signature.
- Co-authored-by records co-authors following a convention that platforms can recognize.
- A commit signature is stored as a signature header in the commit object and verified by Git using verify-commit.

Creating a commit with a sign-off trailer:

~~~bash
git commit -s -m "fix(api): validate request body"
~~~

The -s option adds a Signed-off-by trailer based on the committer identity. It is not the same as -S, which requests signing the commit with the configured GPG/SSH key.

## 10. Signature and Encoding Headers in a Commit Object

A commit object can contain headers beyond tree, parent, author, and committer.

For example:

~~~text
tree 1a2b3c...
parent 4d5e6f...
author Linh Le <linh@example.com> 1763371200 +0700
committer Linh Le <linh@example.com> 1763371500 +0700
gpgsig -----BEGIN PGP SIGNATURE-----
 ...
 -----END PGP SIGNATURE-----

fix(auth): reject expired token
~~~

Signatures can use OpenPGP or SSH depending on your Git configuration. The signature header is bound to the commit content; modifying the commit content afterward invalidates the existing signature.

A commit can also have an encoding header if the message was written in a non-default encoding. Most modern workflows use UTF-8. Do not manually edit raw commit objects, because changing even a single byte alters the object ID and can break the signature.

Verifying a signature:

~~~bash
git verify-commit HEAD
~~~

Viewing a commit object:

~~~bash
git cat-file -p HEAD
~~~

## 11. How Is a Commit ID Generated?

Git objects are identified by the hash of the object header and payload. For a commit, the hashed data includes the object type, size, and commit object content. Therefore, the commit ID depends on:

- Tree OID.
- All parent OIDs and their order.
- Author name/email/date.
- Committer name/email/date.
- Commit message.
- Other headers such as encoding and signature.

If any component changes, the commit's object ID changes. SHA-1 and SHA-256 repositories have different object formats, so you should not assume all commit IDs have the same length.

Inspection:

~~~bash
git rev-parse --show-object-format
git rev-parse HEAD
git cat-file -t HEAD
git cat-file -s HEAD
~~~

- --show-object-format shows the repository's hash format.
- rev-parse HEAD prints the object ID.
- cat-file -t confirms the object type is commit.
- cat-file -s displays the size of the object payload.

No two commits with different content share the same ID under the cryptographic security assumptions of the object format; Git relies on content-addressed storage to identify and reuse objects.

## 12. Why Do Amend and Rebase Create New Commit IDs?

Commit objects are considered immutable. When you modify a commit, Git creates a new object with the updated content or metadata.

### Amend

~~~bash
git commit --amend
~~~

Amend creates a new commit replacing the current branch tip commit. The tree may change if the index differs; the message may change; the committer date and metadata may be updated. Even if the tree stays the same, the commit ID usually changes because metadata or the message changed.

If you need to keep the original author, Git preserves the author information by default. The --reset-author option resets the author to the person creating the new commit.

### Rebase

Rebase replays commits onto a new base. Each recreated commit gets a new parent, so its object ID changes even if the file contents at each step match the original commit.

~~~text
Before rebase:

      A --- B (feature)
     /
Base
     \
      C --- D (main)

After rebasing feature onto main:

Base --- C --- D --- A' --- B'
~~~

A' and B' are new commit objects. They have new parents and typically new committer dates; author information is usually preserved. Do not use old hashes to identify commits after a rebase.

### Cherry-pick

Cherry-pick also creates a new commit on the current branch. The content changes may be equivalent to the source commit, but the parent and committer metadata differ, so the commit ID is different.

## 13. Merge Commits Store Multiple Parents

When merging two branches requires creating a merge commit, Git records multiple parent lines in the commit object:

~~~text
tree <result-tree>
parent <current-branch-tip>
parent <merged-branch-tip>
author ...
committer ...

Merge branch 'feature/search'
~~~

The tree is the result after merging. The two parents record the two histories that were joined. If the merge has conflicts, you resolve them first; the tree in the merge commit stores the final resolved result, not the conflict markers that were handled.

Viewing a merge commit:

~~~bash
git cat-file -p HEAD
git rev-list --parents -n 1 HEAD
git show --cc HEAD
~~~

--cc displays a combined diff for merge commits in appropriate cases. A merge commit does not necessarily have a diff that is easy to read against a single parent; be explicit about which parent you want to compare against.

## 14. Reading a Commit Object Layer by Layer

Suppose HEAD is the commit you want to investigate. You can use the following process:

### Step 1: confirm object type and size

~~~bash
git cat-file -t HEAD
git cat-file -s HEAD
~~~

The expected output for object type is commit.

### Step 2: read headers and message

~~~bash
git cat-file -p HEAD
~~~

Look for the tree, parent, author, and committer lines, as well as the message after the blank line. If gpgsig or other headers exist, note that they are object metadata.

### Step 3: inspect the tree

~~~bash
git show -s --format=%T HEAD
git ls-tree HEAD
~~~

Inspect the root snapshot and entries. Use -r to list recursively.

### Step 4: inspect parents

~~~bash
git show -s --format=%P HEAD
git log --graph --oneline --decorate -10
~~~

Determine how many parents the commit has and its position in the history graph.

### Step 5: inspect identity and message

~~~bash
git show -s --format=fuller HEAD
git show -s --format=%B HEAD
~~~

Compare author/committer, dates, and the message. If metadata differs from expectations, check the config and environment variables in the process that created the commit.

## 15. Distinguishing Commit, Tree, and Diff

| Component | What Does It Store? | Does It Store Parents? | Does It Store a Message? |
| --- | --- | --- | --- |
| Commit | Tree OID, parents, author/committer, timestamps, message, and other headers | Yes | Yes |
| Tree | Entry list, modes, names, and OIDs of blobs/subtrees | No | No |
| Blob | File content | No | No |
| Diff | Comparison result between two states | Not a default commit object | No |

A commit does not store the full diff against its parent. Git generates diffs by comparing the commit's tree with its parent's tree or another commit's tree. Therefore, the same commit can be compared against many different milestones and produce different diffs.

For example:

~~~bash
git diff HEAD^ HEAD
git diff main HEAD
git diff HEAD~3 HEAD
~~~

The commands above select different pairs of snapshots to compare. For a merge commit, specify the parent explicitly if you want to see changes relative to a specific branch.

## 16. Common Misconceptions

### Is a commit a full copy of the directory?

A commit points to a tree snapshot. The tree references blobs and subtrees; Git reuses unchanged objects. Not every commit copies all file contents again.

### Does a commit store the diff from its parent?

No. A commit stores a tree OID and parent OIDs. Diffs are computed when comparing trees.

### Are the author and committer always the same person?

No. During cherry-pick, rebase, git am, or automation, the author may be the person who originally wrote the change while the committer is the person who created the current commit object.

### Does the commit date determine which commit came first?

No. History relationships are determined by the parent graph. Timestamps can be skewed by clocks, imported history, or overridden metadata.

### Is the branch name inside the commit?

No. A branch is a ref pointing to a commit. A single commit can be referenced by multiple branches or tags simultaneously.

### Does a merge commit only have one parent?

No. A regular merge commit has at least two parents; a root commit has no parents.

### Is Signed-off-by a cryptographic signature?

No. Signed-off-by is a trailer in the commit message following a convention. Cryptographic signatures are stored in a signature header and verified with git verify-commit.

### Does editing a message with amend keep the same commit ID?

No. The message is part of the commit object. Changing the message creates a new object and a new ID.

## 17. Self-Check

You are inspecting a commit with the following abbreviated output:

~~~text
tree 111aaa...
parent 222bbb...
parent 333ccc...
author An Nguyen <an@example.com> 1763371200 +0700
committer Binh Tran <binh@example.com> 1763457600 +0700

Merge feature/payment
~~~

Answer the following:

1. Which object does this commit point to in order to describe the snapshot?
2. How many parents are there, and what type of commit does that indicate?
3. Who is the author and who is the committer?
4. What do the two timestamps mean?
5. Does the commit object store the diff against its parents?
6. If you only edit the commit message with amend, why does the commit ID change?
7. Which command views tree entries, and which command views the raw commit object?

**Hint:** The Tree OID is the root snapshot. Two parent lines indicate a merge commit with two parents. An is the author, and Binh is the committer. Timestamps include a timezone offset, and author date and committer date can differ. A commit stores the tree and parents, while diffs are computed by comparing trees. The message is part of the commit content, so amend generates a new object ID. Use git ls-tree HEAD to view tree entries and git cat-file -p HEAD to read the commit object.

## Conclusion

A Git commit is an object that links a tree snapshot to one or more parents and records the author, committer, timestamps, message, and other headers. Trees describe files and directories via blob/tree objects; commits do not store diffs, which Git computes by comparing snapshots. The author records the original creator of the change, while the committer records the person or process that created the current commit object. The parent graph determines history relationships, whereas timestamps are purely time metadata. Use git cat-file, git show, git rev-list, and git ls-tree to inspect each component; keep in mind that changing the tree, parents, identity, timestamp, message, or signature can all produce a new commit ID.

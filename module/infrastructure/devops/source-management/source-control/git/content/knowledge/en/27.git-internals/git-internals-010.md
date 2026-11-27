# Creating Trees and Commits with Plumbing Commands to Understand Internals

Familiar Git commands such as <code>git add</code>, <code>git commit</code>, and <code>git status</code> belong to the porcelain group: they provide a convenient interface for daily work. Beneath that interface, Git provides plumbing commands for working directly with the object database, the index, and references. Understanding these commands shows you that a commit is not a vague bundle of changes: it is an object pointing to a tree, the tree points to blobs or subtrees, and a branch is a reference pointing to a commit.

This lesson walks through creating a snapshot and a commit using plumbing commands such as <code>git hash-object</code>, <code>git update-index</code>, <code>git write-tree</code>, <code>git commit-tree</code>, and <code>git update-ref</code>. Afterward, you will use <code>git mktree</code> to construct a tree directly, inspect objects with <code>git cat-file</code>, and compare this workflow against <code>git add</code> and <code>git commit</code>.

This lesson belongs to the **Internals** chapter of the **SOURCE_CONTROL_GIT** module. The module guides Git from the working tree, staging area, commits, and history through branches, merges, rebases, remotes, and tags, while building skills in branch-based collaboration, conflict resolution, tracking down changes, and recovering from mistakes while preserving critical history. Understanding plumbing gives you a solid grasp of staging, snapshots, commits, and refs, enabling more accurate repository diagnostics and Git automation.

## 1. How do porcelain and plumbing differ?

Git divides many of its commands into two groups by purpose:

| Group | Role | Examples |
|---|---|---|
| Porcelain | High-level user interface combining multiple steps into convenient operations | <code>git add</code>, <code>git commit</code>, <code>git switch</code>, <code>git merge</code> |
| Plumbing | Low-level commands for manipulating objects, the index, refs, and internal data | <code>git hash-object</code>, <code>git update-index</code>, <code>git write-tree</code>, <code>git commit-tree</code>, <code>git update-ref</code> |

For example, when running <code>git commit</code>, Git coordinates the index state to build a tree, creates a commit object containing that tree and parents, and then updates the branch ref. With plumbing, you invoke each step individually and are responsible for wiring them together in the right order.

Plumbing is useful when:

- You want to understand precisely how Git stores snapshots and commits.
- Writing low-level scripts or repository management tools.
- Analyzing the object database, index, and references.
- Creating trees or commits inside a specialized automated workflow.
- Investigating repository state when porcelain commands do not reveal enough detail.

In day-to-day work, porcelain commands are safer and more convenient. Plumbing does not validate every high-level intent for you; an incorrect ref update command can point a branch to an unintended commit.

## 2. The data model to keep in mind

A Git commit typically links to objects in the following structure:

~~~text
                  refs/heads/main
                         |
                         v
                      Commit
                    /        \
                 tree        parent
                  |
             +----+------+
             |           |
          blob        subtree
             |           |
          file data    ...
~~~

The components:

- **Blob:** stores the content of a single file. A blob does not store a file name or path itself.
- **Tree:** stores entries consisting of mode, name, and object ID; an entry can point to a blob or a subtree.
- **Commit:** stores the snapshot's root tree, parent commits, author/committer details, timestamps, and message.
- **Reference:** a human-readable name such as <code>refs/heads/main</code> pointing to an object ID, usually a commit.
- **Index:** the staging area associated with the working tree, holding entries that will be used to construct the next tree.

A branch is not a folder copy, nor does it contain all commits. A local branch is normally a ref pointing to the latest commit on that branch. When a new commit is created, Git updates the ref to point to the new commit.

## 3. Preparing a test repository

Practice in a brand-new repository, never in a repository containing real work. The examples below use Bash:

~~~bash
mkdir plumbing-lab
cd plumbing-lab
git init -b main

git config user.name "Git Plumbing Learner"
git config user.email "learner@example.test"
~~~

If your Git version does not support <code>git init -b</code>, run <code>git init</code> and then set the symbolic HEAD:

~~~bash
git symbolic-ref HEAD refs/heads/main
~~~

Verify the repository:

~~~bash
git status
git symbolic-ref HEAD
git rev-parse --show-object-format
~~~

The final command displays the repository's hash format, such as <code>sha1</code> or <code>sha256</code>. Do not assume every object ID has a fixed length of 40 characters; length depends on the object format.

## 4. Step 1: create a blob with git hash-object

Create a file:

~~~bash
printf 'Hello from Git plumbing\n' > hello.txt
~~~

Use <code>git hash-object</code> to compute the object ID:

~~~bash
git hash-object hello.txt
~~~

This computes and prints the object ID without writing the object to the object database. To store the blob in the repository, add the <code>-w</code> option:

~~~bash
blob=$(git hash-object -w hello.txt)
printf '%s\n' "$blob"
~~~

Inspect the newly created object:

~~~bash
git cat-file -t "$blob"
git cat-file -s "$blob"
git cat-file -p "$blob"
~~~

The outputs indicate, in order:

- <code>-t</code>: object type, here <code>blob</code>.
- <code>-s</code>: blob content size in bytes.
- <code>-p</code>: prints the object content.

The blob stores only the content bytes. The name <code>hello.txt</code> is not attached to the blob yet. Names and paths will be recorded in the tree object in a later step.

### What does Git compute the object ID from?

Git does not hash the raw content alone. An object is identified from a header containing the object type and size, a NUL byte, and then the payload:

~~~text
blob <size><NUL><file bytes>
~~~

Thus, identical bytes stored as a blob yield the same object ID under the same object format. If the content changes, the object ID changes as well with an extremely low probability of collision under the repository's hash algorithm.

### Note on attributes and clean filters

The example above uses a simple file with no special filters. In a real repository, <code>.gitattributes</code> may declare clean filters or content-transformation rules applied before Git stores the blob. If you want <code>hash-object</code> to process the file as if it lived at a specific path, use the <code>--path</code> option:

~~~bash
git hash-object -w --path=hello.txt hello.txt
~~~

This matters when building objects manually with plumbing: if you skip a clean filter that porcelain <code>git add</code> would apply, the object you create may differ from what the standard workflow expects.

## 5. Step 2: add the blob to the index with git update-index

The blob is stored, but the index still has no entry for the file. Run:

~~~bash
git update-index --add --cacheinfo "100644,$blob,hello.txt"
~~~

Explanation:

- <code>--add</code> allows inserting a new entry into the index.
- <code>--cacheinfo</code> supplies the mode, object ID, and path directly.
- <code>100644</code> is the standard mode for a regular file without execute permission.
- <code>$blob</code> is the object ID of the blob just created.
- <code>hello.txt</code> is the path name recorded in the index.

Inspect the index:

~~~bash
git ls-files --stage
~~~

Output looks like:

~~~text
100644 <object-id> 0	hello.txt
~~~

Each entry shows mode, object ID, stage, and path. Stage <code>0</code> is a normal resolved entry. During a conflict, the index can hold stages 1, 2, and 3 representing base, ours, and theirs; in that state, a normal tree cannot be written until the conflict is resolved.

### Some common modes

| Mode | Meaning |
|---|---|
| <code>100644</code> | Regular file, non-executable |
| <code>100755</code> | Regular file, executable |
| <code>120000</code> | Symbolic link; the blob stores the target path content |
| <code>040000</code> | Tree entry inside a tree structure |
| <code>160000</code> | Gitlink pointing to a submodule commit |

Mode reflects how Git stores the entry, not full operating system permission metadata.

## 6. Step 3: create a tree from the index with git write-tree

Once the index contains the entries to commit, run:

~~~bash
tree=$(git write-tree)
printf '%s\n' "$tree"
~~~

<code>git write-tree</code> reads the index and creates tree objects representing the staged snapshot. It prints the object ID of the root tree. If the index includes paths in subdirectories, Git creates the necessary subtrees and links them into the root tree.

Inspect:

~~~bash
git cat-file -t "$tree"
git cat-file -p "$tree"
~~~

You will see an entry containing the mode, object type, object ID, and name:

~~~text
100644 blob <blob-object-id>	hello.txt
~~~

The tree stores names and directory relationships. The blob stores content. This separation lets Git reuse identical blobs across many locations or snapshots without duplicating content.

### Conditions for write-tree to succeed

The index must be in a valid state to build a snapshot. If unmerged entries remain from a merge or rebase conflict, <code>git write-tree</code> fails. Resolve all conflicts and bring entries back to stage 0 first.

<code>git write-tree</code> does not create a commit and does not move any branch. It solely builds a tree object from the current index.

## 7. Step 4: create a commit object with git commit-tree

Once you have a tree, you can create a commit:

~~~bash
commit=$(git commit-tree "$tree" -m "Add hello file")
printf '%s\n' "$commit"
~~~

Because this is the first commit, no parent is passed. Git creates a root commit.

Inspect:

~~~bash
git cat-file -t "$commit"
git cat-file -p "$commit"
~~~

A commit object has the general structure:

~~~text
tree <tree-object-id>
author Git Plumbing Learner <learner@example.test> <timestamp> <timezone>
committer Git Plumbing Learner <learner@example.test> <timestamp> <timezone>

Add hello file
~~~

Specific fields include:

- <code>tree</code>: root tree of the snapshot.
- <code>parent</code>: parent commit; root commits omit this line.
- <code>author</code>: person credited with creating the change.
- <code>committer</code>: person who created the commit object.
- Text after the blank line: commit message.

Git obtains author and committer information from configuration or environment variables. If required values are missing, the command can fail. In our test repository, we configured name and email during setup.

### A commit object is not yet a branch update

This is an important point: <code>git commit-tree</code> creates the commit object and prints its object ID, but it does not automatically update the current branch. The commit exists in the object database, yet no convenient ref points to it yet.

While no ref anchors the commit, you can still reach it by the object ID returned. However, an object unprotected by a ref or reflog is unreachable and can be removed by Git during garbage collection after an appropriate grace period. Therefore, if you want to keep the commit, deliberately update a ref after verifying the object ID.

## 8. Step 5: update the branch with git update-ref

The repository was initialized with `HEAD` pointing symbolically to <code>refs/heads/main</code>. After creating the commit, update the branch:

~~~bash
git update-ref refs/heads/main "$commit"
~~~

Verify:

~~~bash
git symbolic-ref HEAD
git rev-parse main
git log --oneline --decorate -1
git status
~~~

`HEAD` still points to branch <code>main</code>; the branch now points to the newly created commit. Because the file in the working tree and index matches the committed snapshot, status will normally be clean.

### Updating a ref with an expected old value

When updating an existing branch, you can pass the old object ID so Git updates the ref only if its current value matches what you expect:

~~~bash
git update-ref refs/heads/main "$new_commit" "$old_commit"
~~~

This is a compare-and-swap operation. If the branch was already updated by another process since <code>$old_commit</code>, the command fails instead of overwriting the newer change. This is useful in scripts or automated tools manipulating refs.

## 9. Creating a second commit and linking a parent

A new commit normally has a parent pointing to the previous commit. Modify the file:

~~~bash
printf 'Hello from Git plumbing\nSecond line\n' > hello.txt
~~~

Create a new blob and update the index:

~~~bash
blob2=$(git hash-object -w hello.txt)
git update-index --cacheinfo "100644,$blob2,hello.txt"
~~~

Create a new tree and commit whose parent is the first commit:

~~~bash
tree2=$(git write-tree)
commit2=$(git commit-tree "$tree2" -p "$commit" -m "Update hello file")
~~~

Update the branch. Pass the old commit as the final argument to guard against unexpected concurrent ref changes:

~~~bash
git update-ref refs/heads/main "$commit2" "$commit"
~~~

Inspect history:

~~~bash
git log --oneline --decorate --graph
git cat-file -p "$commit2"
~~~

The new commit contains the new tree and a `parent` pointing to the prior commit. The new tree references the new blob. The old commit and old blob remain preserved so history can still reconstruct the earlier state.

## 10. Creating a tree directly with git mktree

<code>git write-tree</code> builds a tree from the index. If you want to construct a tree directly from a list of entries, you can use <code>git mktree</code>.

The basic input format for <code>git mktree</code> is:

~~~text
<mode> SP <type> SP <object-id> TAB <name>
~~~

Example creating a tree with a single file:

~~~bash
printf '100644 blob %s\thello.txt\n' "$blob" | git mktree
~~~

The command prints the object ID of the newly created tree. You can inspect it with:

~~~bash
manual_tree=$(printf '100644 blob %s\thello.txt\n' "$blob" | git mktree)
git cat-file -p "$manual_tree"
~~~

This tree can match the tree produced by <code>git write-tree</code> if the entry list and object contents are identical. Because trees are content-addressed, identical tree structure yields the same object ID under the same object format.

### Building a tree with subdirectories

To create the structure:

~~~text
root
└── src
    └── app.txt
~~~

First create the blob:

~~~bash
printf 'print("hello")\n' > app.txt
app_blob=$(git hash-object -w app.txt)
~~~

Create the subtree named <code>src</code>:

~~~bash
src_tree=$(printf '100644 blob %s\tapp.txt\n' "$app_blob" | git mktree)
~~~

Then create the root tree referencing the subtree:

~~~bash
root_tree=$(printf '040000 tree %s\tsrc\n' "$src_tree" | git mktree)
git cat-file -p "$root_tree"
~~~

The output shows that entry <code>src</code> has type <code>tree</code>, not `blob`. When building multiple levels, build trees bottom-up: blobs first, subtrees next, and then parent trees.

<code>git mktree</code> is well suited for understanding the tree format or constructing snapshots from prepared data. In ordinary scripts, updating the index and running <code>git write-tree</code> is usually easier to maintain.

## 11. Multiple parents: creating a merge commit with plumbing

A commit can have multiple parents. A standard merge commit has two parents: the current branch's commit and the merged branch's commit.

Suppose the test repository already has two branches named <code>main</code> and <code>feature</code>:

~~~bash
ours=$(git rev-parse main)
theirs=$(git rev-parse feature)
~~~

After preparing the index with the merged result tree and writing the tree:

~~~bash
merge_tree=$(git write-tree)
merge_commit=$(git commit-tree "$merge_tree" -p "$ours" -p "$theirs" -m "Merge feature")
~~~

The commit object has two `parent` lines in the order provided:

~~~text
tree <merge-tree-id>
parent <ours-commit-id>
parent <theirs-commit-id>
...
~~~

Next, update the target branch provided it still points to the `ours` commit:

~~~bash
git update-ref refs/heads/main "$merge_commit" "$ours"
~~~

This example only illustrates the structure of a merge commit. To produce a proper merge outcome, the index must already hold the combined content with all conflicts resolved. <code>commit-tree</code> does not run a merge algorithm, choose file versions, or resolve conflicts itself.

## 12. Comparing plumbing to git add and git commit

The plumbing workflow just performed corresponds roughly to these porcelain steps:

| Plumbing operation | Corresponding role in the standard workflow |
|---|---|
| <code>git hash-object -w</code> | Create and store a blob for file contents |
| <code>git update-index</code> | Place the file version into the staging area |
| <code>git write-tree</code> | Build a tree from the snapshot in the index |
| <code>git commit-tree</code> | Create a commit object from a tree and parents |
| <code>git update-ref</code> | Move the branch ref to the new commit |

In everyday work, you typically only need:

~~~bash
git add hello.txt
git commit -m "Update hello file"
~~~

Porcelain also handles many additional details such as default commit messages, hooks, signing, cleanup, reflogs, and status checks. The plumbing sequence in this lesson is a learning model to reveal the objects and refs created; it is not a drop-in replacement for every behavior of <code>git commit</code>.

## 13. Inspecting objects and refs after creating a commit

The following commands help trace the resulting structure:

~~~bash
# Inspect the current commit
git cat-file -p HEAD

# Inspect the tree referenced by the commit
git cat-file -p HEAD^{tree}

# List files and subtrees in the snapshot
git ls-tree HEAD
git ls-tree -r HEAD

# Inspect the current index
git ls-files --stage

# Check whether HEAD is a symbolic ref or detached OID
git symbolic-ref -q HEAD
git rev-parse HEAD

# Check where branch refs point
git show-ref --heads
~~~

Distinguish two checks:

- <code>git cat-file -p HEAD</code> displays the contents of the commit object.
- <code>git cat-file -p HEAD^{tree}</code> displays the contents of the commit's root tree.

If <code>HEAD</code> is detached, <code>git symbolic-ref -q HEAD</code> exits with an error code because `HEAD` holds an object ID directly instead of pointing symbolically to a branch.

## 14. Common mistakes when using plumbing

| Symptom | Cause | Resolution |
|---|---|---|
| <code>git write-tree</code> fails | Index still has conflict stages or invalid state | Check <code>git ls-files --stage</code> and resolve conflicts |
| Tree lacks the expected file | Blob was not added to index or wrong path used | Check <code>git ls-files --stage</code> before running `write-tree` |
| Commit created but not visible on branch | <code>commit-tree</code> does not update refs | Run <code>git update-ref</code> after verifying the commit |
| Branch points to wrong commit | Wrong ref updated or wrong object ID passed | Inspect <code>git show-ref</code> and <code>git cat-file -p</code> before fixing |
| <code>hash-object</code> prints an ID but object is missing | Missing <code>-w</code> flag so it only computed the hash | Use <code>git hash-object -w</code> to persist the object |
| Blob content differs from file after porcelain | Clean filter or attributes were not applied | Check attributes and use <code>hash-object --path</code> when appropriate |
| Commit has no parent | <code>-p</code> option was omitted | Root commits have no parent; subsequent commits must specify parents |
| Commit object exists but HEAD did not change | Creating an object does not update HEAD/refs | Update the right branch ref with <code>update-ref</code> |

## 15. End-to-end hands-on workflow

In a test repository, perform the full sequence from scratch without using <code>git add</code> or <code>git commit</code>:

1. Initialize the repository and configure author/committer.
2. Create a text file.
3. Use <code>git hash-object -w</code> to create a blob.
4. Use <code>git update-index --add --cacheinfo</code> to add the entry to the index.
5. Use <code>git ls-files --stage</code> to confirm stage 0.
6. Use <code>git write-tree</code> to create the tree.
7. Use <code>git cat-file -p</code> to inspect the tree.
8. Use <code>git commit-tree</code> to create the commit.
9. Use <code>git update-ref</code> to update the branch.
10. Make a new edit, repeat the sequence, and pass the parent commit.
11. Use <code>git log</code>, <code>git cat-file</code>, <code>git ls-tree</code>, and <code>git show-ref</code> to inspect history.
12. Create an equivalent tree with <code>git mktree</code> and compare object IDs.

Once finished, run the porcelain workflow in a second test repository and compare the object graphs. You will see that Git still creates blobs, trees, commits, and ref updates using the exact same model; porcelain simply automates the steps and adds user-facing safety checks.

## 16. Self-check exercises

1. Explain why blobs do not store file names while trees do store file names.
2. Create two files with identical content using <code>git hash-object -w</code>. Verify whether they share the same blob object ID.
3. Edit one file and create a new blob. Compare the object ID and size.
4. Add both files to the index with <code>update-index</code> and build a tree. Observe that the tree contains both entries.
5. Create a subdirectory with <code>git mktree</code> and link it from a root tree.
6. Create a root commit with <code>commit-tree</code>, confirm no branch ref points to it yet, and then run <code>update-ref</code>.
7. Create a second commit with the <code>-p</code> option and inspect the `parent` line.
8. Create a two-parent commit with <code>commit-tree</code> in a test repository with two branches.
9. Explain why <code>write-tree</code> fails when unmerged entries remain in the index.
10. Describe which steps from the plumbing chain are automated by porcelain <code>git add</code> and <code>git commit</code>.

Once you can independently create blobs, index entries, trees, commits, and ref updates, you understand the path from file content to Git history. Use plumbing for learning and purposeful tooling; in everyday work, prefer porcelain because it bundles steps, checks repository state, and protects the commit workflow more safely.

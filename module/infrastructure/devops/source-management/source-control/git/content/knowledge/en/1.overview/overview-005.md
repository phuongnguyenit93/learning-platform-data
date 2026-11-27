# Snapshot model, commits, and the history graph

Git manages source code history by storing recorded states of a project and linking those states into a graph. To understand how Git works, you need to grasp three closely related concepts: a **snapshot** describing the contents of a version, a **commit** recording a snapshot along with information about its origin, and the **history graph** showing how commits follow one another or branch out.

These concepts explain why Git can compare versions, create branches, merge work, and restore old states while preserving the project's development history.

## 1. Git stores project state as snapshots

Imagine a project with three files: `README.md`, `src/App.java`, and `src/Utils.java`. After finishing a piece of work, you want to record the state of the whole project at that moment. Git creates a snapshot representing the tracked contents at the time of recording.

In Git's data model, a commit points to a **tree** object at the root directory. A tree describes directory entries: files, subdirectories, file modes, and references to objects containing the contents. Sub-trees continue describing the directory hierarchy. The contents of a regular file are stored in a **blob** object.

For example, the conceptual structure might look like this:

```text
commit C1
  |
  +-- tree (root directory)
        |
        +-- README.md ------> blob B1
        |
        +-- src ------------> tree T1
                               |
                               +-- App.java ---> blob B2
                               |
                               +-- Utils.java -> blob B3
```

A blob stores file content, not the filename. A tree associates the name and attributes of a directory entry with the corresponding blob or tree. A commit links the root-level snapshot with history metadata such as author, committer, timestamp, message, and parent commits.

### A snapshot differs from a patch

When inspecting history, we often see Git display additions, edits, and deletions between two versions. That presentation easily leads beginners to think each commit stores only a patch relative to the previous commit. In terms of the data model, a Git commit points to a complete directory tree snapshot.

Git can reuse unchanged content and tree objects. If a file keeps the same content, Git does not need to create a new blob just because you create the next commit. If a directory is unchanged, the corresponding tree can also be reused. As a result, having each commit represent the full state does not mean Git duplicates all data on every commit.

When displaying differences, Git compares two states to derive the changes to present. A diff is an interpretation of the differences between snapshots; it is not the commit's underlying storage model.

## 2. Three state areas to distinguish

Before creating a commit, Git lets you prepare the exact changes to be recorded. This workflow is easier to understand by distinguishing three areas:

| Area | Role | How to inspect |
|---|---|---|
| Working tree | Files and directories currently present in the working directory | `git status`, viewing files directly |
| Staging area (index) | Prepared content selected to go into the next commit | `git diff --cached`, `git ls-files --stage` |
| Repository and `HEAD` | Stored objects together with the current commit position | `git log`, `git show`, `git cat-file` |

You can visualize the basic flow as follows:

```text
Working tree
   |  git add
   v
Staging area (index)
   |  git commit
   v
New commit in repository
   |
   +---- HEAD of current branch is updated
```

The working tree is where you edit source code. When running `git add`, Git takes the content at that moment to update the index. The index is therefore the staging preparation for the next commit. If you continue editing the file after `git add`, the new edits remain in the working tree and do not automatically become staged content.

Example:

```bash
# Check current status
git status

# Put a file into the staging area
git add src/App.java

# Inspect what is staged, i.e., content intended to be committed
git diff --cached

# Inspect what is modified in working tree but not yet staged
git diff

# Record the content in the staging area
git commit -m "Add application entry point"
```

By default, `git diff` compares the working tree with the index. `git diff --cached` (equivalent to `git diff --staged`) compares the index with the commit referenced by `HEAD`. The two commands answer two different questions: what has not yet been staged, and what is ready to go into the commit.

## 3. A commit is an object recording a snapshot

A typical commit contains the following key pieces of information:

- **Tree**: the root directory snapshot recorded by the commit.
- **Parent**: one or more parent commits, indicating which history this commit extends.
- **Author**: the person credited as the author of the change.
- **Committer**: the person or process that created the commit object.
- **Timestamp**: the respective timestamps for the author and committer.
- **Message**: the message explaining the purpose of the commit.

A commit does not contain the literal full source code in one block. It holds a reference to a tree and history metadata; the tree in turn references blobs and sub-trees.

A commit is identified by the hash of the object's content. The full hash is often called the object ID (OID). When the commit's content changes, the object's OID also changes. Because a commit includes references to its tree and parents, the commit OID reflects both the recorded project state and its position in history.

### Parent commits form history relationships

For a regular commit, there is one parent commit. The very first commit in a new repository normally has no parent. A merge commit has two or more parents because it connects diverged lines of history.

Example of a linear chain of commits:

```text
C1 ----> C2 ----> C3
```

The arrows in the diagram represent progression from older commits to newer commits. In terms of the `parent` field stored inside a commit, `C3` points back to `C2`, and `C2` points back to `C1`.

An already-created commit is generally treated as immutable. If you want to change committed content, Git creates a new commit object with a new OID. Operations such as amend or rebase recreate commits, so commit hashes can change even when the visible source code appears similar.

## 4. What is the history graph?

Because each commit references its parent commits, the entire history forms a **directed acyclic graph (DAG)**. Each vertex is a commit; parent relationships connect newer commits to preceding ones. Independent development branches create multiple paths, and merges can reconnect those paths.

An example with a feature branch:

```text
             C2 ---- C3
            /          \
C1 --------+------------ M ---- C5
            \          /
             F1 ------
```

In this diagram:

- `C1` is the initial common commit.
- `C2` and `C3` continue the main line of history.
- `F1` is a commit created on a feature branch starting from `C1`.
- `M` is a merge commit connecting the two lines of history; it has two parents.
- `C5` is created after the merge.

The diagram only illustrates parent-child relationships. Left-to-right or top-to-bottom positioning does not represent duration or the importance of changes.

### Branches and HEAD are references

Branch names like `main` or `feature/login` are not copies of the entire directory. A branch is a movable reference, usually pointing to the latest commit on that line of development. When you create a commit on the checked-out branch, the branch reference is updated to point to the new commit.

`HEAD` indicates the repository's current position. Normally, `HEAD` points indirectly through the checked-out branch name. That situation is called **attached HEAD**. If you directly check out a commit hash instead of a branch, `HEAD` points straight to the commit and the repository is in a **detached HEAD** state.

Example:

```bash
# View the commit HEAD is referencing
git log -1 --oneline

# View branches and the commits they point to
git branch -v

# View HEAD and related references
git show-ref --head

# View history as a graph
git log --oneline --graph --decorate --all
```

`git log --graph` draws connecting lines between commits to make branches and merges easy to spot. `--decorate` shows reference names such as branches or tags next to commits. `--all` tells Git to display history reachable from all selected references rather than only from `HEAD`.

## 5. From change to commit: a complete example

Suppose you are on the `main` branch and want to add a utility to the project.

```bash
# Check current position and status
git branch --show-current
git status

# Create or edit src/Utils.java in the working tree

# Stage the changes to be recorded into the index
git add src/Utils.java

# Inspect the exact content about to be committed
git diff --cached

# Create commit
git commit -m "Add string utility"

# Inspect the new commit and its relationship to prior commits
git show --stat --oneline HEAD
git log --oneline --graph --decorate -5
```

After the `git add` command, the index holds the selected contents of `src/Utils.java`. When you run `git commit`, Git creates the necessary blob/tree objects, creates a commit object pointing to that tree and the current parent commit, and updates the checked-out branch. `HEAD` continues to identify the current position via that branch.

Note: the "Create or edit" comment in the example is an action performed in an editor; Git does not generate file content just by running `git status` or `git add`.

## 6. Reading and inspecting Git objects

The following commands let you observe the data structures used by everyday commands:

```bash
# Show the object type a reference resolves to
git cat-file -t HEAD

# Show the contents of a commit object
git cat-file -p HEAD

# Show the tree referenced by the current commit
git ls-tree HEAD

# Show commit details along with its diff
git show HEAD

# View commit list in compact form
git log --oneline --decorate
```

`git cat-file -p HEAD` typically shows the `tree`, `parent`, `author`, `committer` lines, and the commit message. `git ls-tree HEAD` shows the entries directly inside the root tree. To inspect a sub-tree, you can use that tree's OID or specify an appropriate path to the command.

To compare two snapshots:

```bash
# Compare the states of two commits
git diff <old-commit> <new-commit>

# View only the names and statuses of differing files
git diff --name-status <old-commit> <new-commit>

# View commits reachable from HEAD
git log --oneline HEAD
```

Replace `<old-commit>` and `<new-commit>` with valid commit hashes, tags, or references. The `git diff A B` command displays the differences between the two referenced states; it does not modify either commit.

## 7. Why is this model useful?

**Tracking changes:** Each commit provides a stable reference point for project state. You can compare any two commits to find added, modified, or deleted content.

**Parallel work:** Branches allow multiple lines of development to start from a shared commit. The graph records the relationships between those lines.

**Evidence-based merging:** A merge creates a commit with multiple parents to record joining histories. Git uses ancestor relationships and snapshot contents to compute the merge result.

**Tracing root causes:** When a bug appears, commit history and diffs help identify which change introduced the new behavior into the project. Tools like `git log`, `git show`, and `git blame` leverage this history data.

**Controlled recovery:** Because commits reference snapshots and parent commits, you can create a new commit to reverse a change or move the working tree to a previously recorded state. Choosing the right recovery command requires checking whether the change is committed, staged, or still only in the working tree.

## 8. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| A commit only stores the diff from the previous commit | A commit points to a tree representing the project state; diffs are computed when comparisons are needed. |
| `git add` creates a commit | `git add` updates the index; `git commit` creates the commit object. |
| The staging area is a temporary folder holding file copies | The index is a data structure recording selected contents and metadata for the next commit. |
| A branch is a directory copy | A branch is a movable reference to a commit. |
| Merge always creates exactly one commit | A fast-forward may only move a reference; a merge commit is created when appropriate and can have multiple parents. |
| A commit hash only represents file contents | A commit OID is computed from the commit object's contents, which include tree and parent references along with metadata. |
| Diff is the only data Git uses to understand history | Diff is a way of presenting differences between states; history relationships are described via commits and parents. |

## 9. Self-check

1. **Which object does a regular commit point to in order to describe the project state?**
   - The tree object at the root directory.
2. **After editing a file and running `git add`, where does the prepared content live?**
   - In the staging area (index). If you continue editing the file, the new edits are not automatically staged.
3. **Why can Git history be described as a DAG?**
   - New commits reference parent commits; these relationships form a directed graph with no cycles.
4. **How does a merge commit typically differ from a regular commit?**
   - It has two or more parents, representing the joining of lines of history.
5. **Does the branch name `main` store the entire project content?**
   - No. It is a reference to the current commit of that line of development.

## Conclusion

The snapshot model explains how Git represents project state; a commit binds a snapshot with metadata and parent commits; parent-child relationships combine into the history graph. Once you distinguish the working tree, index, commits, and branch references, you will better understand what happens after every `git add`, `git commit`, `git branch`, or `git merge` command, and read project history proactively.

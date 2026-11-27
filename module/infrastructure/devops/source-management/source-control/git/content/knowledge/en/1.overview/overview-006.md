# Repository, working tree, and index (staging area)

Git helps manage source code changes through history milestones that can be inspected and restored. To use Git safely, you first need to understand the three areas you work with most often: the **repository**, the **working tree**, and the **index (commonly called the staging area)**. These three areas are connected but serve distinct roles. Once you distinguish them, you will know where a change resides, what content will go into the next commit, and how to adjust your staging selection when needed.

This lesson belongs to the **Overview** chapter of the **SOURCE_CONTROL_GIT** module. The module guides you through Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; it also builds skills in collaborating through branches, resolving conflicts, tracing changes, and recovering from mistaken operations while preserving important history. Therefore, understanding the repository, working tree, and index is the foundation for Git operations in the upcoming lessons.

## 1. Three areas to distinguish

### Repository – Git repository

The repository is where Git stores the project's data and version history. In a regular repository, the hidden <code>.git</code> directory contains the object database, branch metadata, commit references, configuration, and other management data. Git uses objects such as blobs, trees, and commits to store file contents, directory structure, and history.

A commit represents a snapshot of the project at a point in time. A commit can reference parent commits, author information, timestamp, and a descriptive message. Through these links, Git forms a history that you can inspect, compare, or switch back to at an appropriate milestone.

In everyday conversation, the word "repository" is sometimes used to refer to the entire project directory cloned onto a machine. Conceptually, you should distinguish the data Git manages from the files checked out for editing. A bare repository typically stores only Git data and has no working tree; this type is commonly used as a central repository on a server.

### Working tree

The working tree is the collection of files and directories visible on your filesystem for reading, creating, editing, or deleting. This is where you write code, update documentation, run the application, and perform daily work.

The working tree can contain:

- **Tracked files:** Git already knows the file's path via a commit or the index.
- **Untracked files:** new files present in the project directory that have not yet been added to the index.
- **Unstaged changes:** the content of a tracked file differs from the version currently in the index.
- **Deleted or renamed files:** filesystem operations creating differences compared to the index.

Saving a file in an editor only changes the working tree. Git does not automatically put new content into a commit just because you pressed Save.

### Index – staging area

The index is the intermediate area that records the content and paths to be used for creating the next commit. Saying "stage a file" means updating that file's version in the index. The typical command is <code>git add</code>.

The index is not simply a list of filenames to commit. It stores the information needed to build the next snapshot, including paths, file modes, and content object identifiers. When staging a file, Git records the corresponding content in the object database and updates the entry in the index.

Right after checking out a commit, the index normally matches that commit's snapshot. When you edit a file, the working tree changes while the index retains the previously staged version. When you run <code>git add</code>, Git updates the index with the file's current content. Therefore, if you continue editing a file after staging it, the new edits stay in the working tree and must be staged again if you want them in the commit.

During a merge with conflicts, the index can also store multiple versions for the same path so Git and the user can identify the content to resolve. After finishing edits on a conflicted file, run <code>git add</code> on that file to record the resolved result into the index.

## 2. How do repository, working tree, index, and HEAD relate?

HEAD indicates the current commit the repository is positioned at. Normally HEAD references the current branch; in a detached HEAD state, HEAD references a commit directly. When checking out or switching branches, Git uses the selected commit to update the working tree and index.

The basic flow can be visualized as follows:

~~~mermaid
flowchart TD
    H["HEAD: current commit"] -->|"checkout / switch"| I["Index: intended snapshot for next commit"]
    H -->|"checkout / switch"| W["Working tree: files on disk"]
    W -->|"git add"| I
    I -->|"git commit"| C["New commit"]
    C -->|"current branch updated"| H2["HEAD: new commit"]
~~~

Three primary operations have distinct meanings:

1. **Editing files:** changes the working tree.
2. **Staging with <code>git add</code>:** updates the index with the current content of the selected path.
3. **Committing with <code>git commit</code>:** creates a commit from the snapshot currently in the index and updates the current branch.

Because commits are created from the index, Git lets you choose precisely which changes belong in a commit. Unstaged edits stay in the working tree and are not automatically included in a normal commit.

| Area | What does it contain? | Operations that typically modify it |
|---|---|---|
| Repository (<code>.git</code>) | Git objects, commits, branches, references, and configuration | <code>git commit</code>, <code>git branch</code>, <code>git fetch</code>, and history management commands |
| Working tree | Project files currently visible on disk | Text editor, build tools, <code>git restore</code>, <code>git checkout</code>, or <code>git switch</code> |
| Index | Intended snapshot for the next commit | <code>git add</code>, <code>git rm</code>, <code>git restore --staged</code> |
| HEAD | Current commit position | <code>git commit</code>, <code>git switch</code>, <code>git checkout</code>, some forms of <code>git reset</code> |

In practice, Git commands can affect multiple areas at once. The table above describes primary roles to orient you; read each command's documentation before using options that can overwrite content.

## 3. Tracking status with git status

<code>git status</code> is a command you should run frequently, especially before staging, committing, switching branches, or handling conflicts. This command shows the current branch and differences between HEAD, the index, and the working tree.

~~~bash
git status
git status --short
~~~

In short mode, Git typically displays two status characters before the path: <code>XY path</code>.

- Character **X** describes the path's status in the index compared to HEAD.
- Character **Y** describes the working tree's status compared to the index.

Some common statuses:

| Output | Meaning |
|---|---|
| <code>?? notes.txt</code> | Untracked file |
| <code> M README.md</code> | Tracked file modified in working tree, not staged |
| <code>M  README.md</code> | Change staged in the index |
| <code>MM README.md</code> | File staged, then edited further in the working tree |
| <code>A  new-file.txt</code> | New file staged |
| <code>D  old-file.txt</code> | File deletion staged |
| <code> D old-file.txt</code> | Tracked file deleted in working tree, deletion not yet staged |
| <code>UU src/App.java</code> | File in conflict state needing resolution |

A space in a position is meaningful too: for example, <code> M</code> means the index column has no changes while the working tree column has changes. Do not just look at the letter <code>M</code>; check which column it sits in.

<code>git status</code> may also report that the current branch is ahead of or behind the upstream branch. This is information about the relationship between local and remote history, not the staging status of individual files.

## 4. Staging and inspecting content to be committed

### Adding changes to the index

Some common staging commands:

~~~bash
# Stage a specific file
git add README.md

# Stage multiple specific paths
git add src/App.java docs/setup.md

# Stage all changes in the working tree
git add -A

# Stage changes of already-tracked files
git add -u

# Interactively select hunks of changes to stage
git add -p
~~~

<code>git add -A</code> updates the index with new files, modified files, and deleted files across the working tree. <code>git add -u</code> updates only already-tracked paths, so it does not add new untracked files. <code>git add .</code> applies to the current directory and its subdirectories; if you are inside a subdirectory, its scope may be narrower than the entire repository.

For projects with many independent changes, it is good practice to stage by path or hunk-by-hunk using <code>git add -p</code>. This keeps each commit focused on changes with a single purpose, making history easier to read and review.

### Viewing differences before committing

Git provides diff commands to compare each pair of areas:

~~~bash
# Compare working tree with index: modified but unstaged changes
git diff

# Compare index with HEAD: what will go into the next commit
git diff --staged

# Equivalent syntax to --staged
git diff --cached

# Compare working tree with HEAD, including both staged and unstaged changes
git diff HEAD
~~~

Remember:

- <code>git diff</code> helps inspect what is unstaged.
- <code>git diff --staged</code> helps inspect what is staged and intended for commit.
- <code>git diff HEAD</code> gives an overall view of current differences compared to the checked-out commit.

Standard diff commands do not show contents of untracked files because those files are not yet in the index. To bring a new file into the staging comparison flow, run <code>git add</code> first; this only updates the index and does not create a commit.

### Example: staging does not equal committing

Suppose you are working on <code>README.md</code>:

1. Open the file and add a section of instructions. At this point the working tree has changed, while the index has not.
2. Run <code>git status --short</code>; you may see <code> M README.md</code>.
3. Run <code>git diff</code> to view the new content.
4. Run <code>git add README.md</code>; the current content is placed into the index.
5. Run <code>git status --short</code>; the status changes to <code>M  README.md</code>.
6. Run <code>git diff --staged</code> to verify the exact selected content.
7. Run <code>git commit -m "docs: update README"</code> to create a commit from the index.

If after step 4 you continue editing <code>README.md</code>, Git will have one version in the index and a newer version in the working tree. <code>git status --short</code> usually displays <code>MM README.md</code>. The next commit will contain only the version staged in step 4; the subsequent edits remain uncommitted until you stage them again.

## 5. Unstaging and restoring changes

Sometimes you stage the wrong file or want to split a change into multiple commits. You can update the index without losing the content currently in the working tree.

~~~bash
# Unstage one file, keeping content in the working tree intact
git restore --staged README.md

# Unstage all paths
git restore --staged .

# Discard unstaged changes of one file, restoring from the index
git restore README.md
~~~

The two <code>git restore</code> commands above solve two different tasks:

- <code>git restore --staged &lt;path&gt;</code> updates the index from HEAD for the chosen path. Content in the working tree is preserved. For a new file not yet in HEAD, this operation removes the file from the index so it returns to untracked status.
- <code>git restore &lt;path&gt;</code> updates the working tree from the index. Unstaged edits on that path will be discarded.

Therefore, before running a restore command, check <code>git status</code> and <code>git diff</code>. If you are unsure which content will be replaced, back up or save the changes you want to keep. Avoid running <code>git restore</code> broadly without clearly identifying the scope.

Some commands related to removing from tracking:

~~~bash
# Remove the file from the working tree and stage the deletion
git rm path/to/file.txt

# Remove the file from the index while keeping it on disk
git rm --cached path/to/file.txt
~~~

<code>git rm --cached</code> is often useful when you accidentally added a file to Git and want to stop tracking it. If the file should be ignored going forward, add an appropriate rule to <code>.gitignore</code>. <code>.gitignore</code> rules apply primarily to untracked files; they do not automatically untrack a file already in history. For an already-tracked file, you must remove it from the index with the appropriate operation.

## 6. New files, deleted files, renames, and conflicts

### New files and ignored files

When you create a new file in the working tree, <code>git status</code> reports it as untracked. Git has not included the file's content in a commit. Run <code>git add &lt;path&gt;</code> to start tracking the file and put its current version into the index.

If you do not want Git to suggest certain files, such as build artifacts, logs, or machine-specific developer configs, you can declare patterns in <code>.gitignore</code>. Example:

~~~gitignore
build/
*.log
.env.local
~~~

The patterns above respectively ignore the <code>build</code> directory, files with the <code>.log</code> extension, and the <code>.env.local</code> file. Check ignore rules carefully to avoid accidentally ignoring source files that belong in the repository. An already-tracked file continues to be tracked even if it later matches a pattern in <code>.gitignore</code>.

### Deletions and renames

If you delete a tracked file directly in a file manager, the working tree records the file's absence, but the index is not updated yet. <code>git status</code> will report an unstaged deletion. Run <code>git add -A</code> or <code>git rm &lt;path&gt;</code> to stage the deletion.

When renaming a file, Git typically represents the change in the index by removing the old path and adding the new path. Git does not store a rename as a separate object type; when displaying history or diffs, Git detects renames based on content similarity. Therefore, the filename shown in a diff can depend on similarity detection.

### Merge conflicts

When a merge or rebase encounters a conflict, a path can have multiple versions in the index, corresponding to the base, the current side, and the incoming side. <code>git status</code> marks that path as unmerged, for example <code>UU</code>.

The resolution workflow typically consists of:

1. Run <code>git status</code> to identify conflicted files.
2. Open each file and read the conflict markers inserted by Git.
3. Edit the content to the desired final version and remove the markers.
4. Run <code>git add &lt;path&gt;</code> to record the resolved result in the index.
5. Run <code>git status</code> and <code>git diff --staged</code> to verify before completing the merge or rebase following Git's instructions.

While files are still conflicted, do not treat the index as a complete snapshot for a regular commit. Staging the file after editing is the signal to Git that you have chosen the conflict-resolution content.

## 7. A safe workflow before every commit

A concise yet effective workflow:

~~~bash
# 1. Check current status
git status

# 2. Review unstaged changes
git diff

# 3. Select changes to include in the commit
git add -p
# Or use git add <path> to select the entire file

# 4. Inspect the intended snapshot
git status
git diff --staged

# 5. Create commit
git commit -m "feat: describe the change"

# 6. Verify status after committing
git status
~~~

The commit message should describe the purpose of the change in a short, clear sentence. Before committing, answer three questions for yourself:

- Do the staged files belong strictly to the scope of this task?
- Does the content in <code>git diff --staged</code> contain secrets, build files, or unintended changes?
- Are there changes still in the working tree that you intended to include in the commit but forgot to stage?

You do not need to stage the entire project on every commit. A small, focused commit is usually easier to read, review, revert, and trace back to root causes.

## 8. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Saving a file in the editor means it is committed | Saving a file only updates the working tree. You need to stage and then commit to create a history milestone. |
| <code>git add</code> creates a commit | <code>git add</code> only updates the index; <code>git commit</code> creates the commit. |
| Once staged, all subsequent edits are automatically staged too | The index holds the version at the time of staging. Editing the file afterward creates new differences in the working tree. |
| <code>git commit</code> always grabs every change on disk | A regular commit creates a snapshot from the index. Unstaged changes are not included in the commit. |
| <code>.gitignore</code> will untrack every matching file | <code>.gitignore</code> does not automatically untrack already-tracked files. |
| Git stores rename operations as a separate object type | Git primarily stores snapshots and infers renames when rendering diffs or history. |
| The index is just a list of files | The index contains information to build a snapshot, including path, file mode, and content ID; during conflicts, one path can even have multiple stages. |

Do not directly edit internal files inside <code>.git</code> or the index to change repository state. Use the appropriate Git commands so Git updates data consistently.

## 9. Self-check exercises

Practice in a test repository so you do not affect active work:

1. Create a new file <code>notes.txt</code> and run <code>git status</code>. Why is the file reported as untracked?
2. Run <code>git add notes.txt</code>, then run <code>git status</code> and <code>git diff --staged</code>. How do the status and displayed content change?
3. Edit <code>notes.txt</code> to add one line without running <code>git add</code>. Why can the status become <code>MM</code>?
4. Run <code>git restore --staged notes.txt</code>. Is the file content on disk lost? Check using <code>git diff</code>.
5. Stage the file again, create a commit, and then run <code>git status</code>. Why does the index normally return to a state matching HEAD?
6. Add a log file to <code>.gitignore</code>. Try with a new log file and an already-tracked log file to observe the difference.

If you can explain which files are in the working tree, which version is in the index, and where the next commit will take its content from, you have mastered the most important foundation of the staging area. From this foundation, creating commits, switching branches, merging, rebasing, and resolving conflicts will become much more predictable.

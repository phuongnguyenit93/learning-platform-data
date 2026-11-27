# File Lifecycle: untracked, tracked, modified, staged, and committed

Git does not track files the way a typical file manager tracks directories on disk. Git stores content snapshots inside commits and uses the index (staging area) to prepare the next snapshot. The working tree consists of the files you see and edit on your machine.

Consequently, a file can transition through multiple states while you work: newly created (untracked), tracked by Git (tracked), modified in content (modified), selected for the next commit (staged), and recorded in a commit (committed). These labels describe different aspects: tracked does not mean clean, and a staged file can still become modified again if you edit it further.

This lesson explains the relationship between HEAD, the index, and the working tree, how to read file states with git status, how to transition files across each stage with add/commit/restore/rm/mv, and how to avoid accidentally including unintended content in a commit.

## 1. Three places that determine a file's state

### 1.1. HEAD — the most recently committed snapshot

HEAD normally points to the current commit of the checked-out branch. That commit's file tree is the baseline Git uses to compare new states.

Inspect HEAD:

~~~bash
git log -1 --oneline
git show --stat --oneline HEAD
~~~

If you are in a detached HEAD state, HEAD points directly to a commit rather than through a local branch. The snapshot concept remains the same: HEAD identifies the current commit.

### 1.2. Index — the snapshot prepared for the next commit

The index is also called the staging area. When you run git add, Git updates the index with the content you selected to include in the next commit.

Inspect staged changes:

~~~bash
git diff --cached
~~~

The index is not a full duplicate of the working directory. It is a Git data structure used to record the intended snapshot. A file can be staged at one version and then edited on disk into another version.

### 1.3. Working tree — files on disk

The working tree comprises the files and directories in the project that you open with an editor or command-line tools. When you edit and save a file, the working tree content changes.

View unstaged changes compared to the index:

~~~bash
git diff
~~~

Git compares these three areas to know which content is already committed, which content is selected for the next commit, and which content still exists only on disk.

### 1.4. Three-layer model

~~~text
             git commit
HEAD  <------------------  Index
 |                           ^
 |                           |
 |                       git add
 |                           |
 +----------------------- Working tree
       compare state
~~~

The comparisons can be understood as follows:

| Command | Comparison | Meaning |
| --- | --- | --- |
| git diff | Working tree vs. index | Unstaged changes |
| git diff --cached | Index vs. HEAD | Staged changes |
| git diff HEAD | Working tree vs. HEAD | Total changes compared to the current commit |
| git status | HEAD, index, and working tree | Summary of repository state |

If the working tree and index match, git diff shows no changes. If the index and HEAD match, git diff --cached shows no staged changes.

## 2. Untracked — new files not yet tracked by Git

### 2.1. What is untracked?

A file is untracked when Git has not recorded it in the index or a commit and no ignore rule excludes it from status reporting.

For example, you create a file:

~~~bash
printf "Hello Git\n" > notes.txt
~~~

Check:

~~~bash
git status
~~~

Git may display:

~~~text
Untracked files:
  notes.txt
~~~

The file exists on disk but is not yet part of the snapshot Git prepares to commit. If you commit immediately without adding the file to the index, notes.txt will not be included in the commit.

### 2.2. Listing untracked files

~~~bash
git ls-files --others --exclude-standard
~~~

This command lists files not tracked by the index and excludes paths ignored under standard rules.

To view short status:

~~~bash
git status --short
~~~

Example:

~~~text
?? notes.txt
~~~

Two question marks indicate an untracked path.

### 2.3. Turning untracked into tracked with git add

To stage a new file:

~~~bash
git add notes.txt
~~~

Check:

~~~bash
git status
git diff --cached
~~~

The file has been placed into the index and will become part of the next snapshot if you commit. Once added to the index, Git begins tracking that path.

Note: git add does not create a commit. It only updates the index.

### 2.4. Untracked and ignored are different

Untracked files can appear in git status. Ignored files are excluded from standard listings by ignore rules.

For example, a .env file can be added to .gitignore:

~~~gitignore
.env
*.log
build/
~~~

Afterward, Git no longer lists paths matching those patterns as untracked in standard status output.

Check which rule is ignoring a path:

~~~bash
git check-ignore -v .env
~~~

If a file is ignored but you genuinely want to add it, you can use git add -f. Only do so after confirming the file does not contain secrets, auto-generated data, or content that should not be committed.

### 2.5. Empty directories are not tracked by Git

Git stores files and tree objects, but does not store an empty directory as a standalone object. If you need to preserve an empty directory, teams commonly place a purposefully named file such as .gitkeep inside it.

.gitkeep is merely a filename convention, not a special Git feature.

## 3. Tracked — files already tracked by Git

### 3.1. Tracked does not mean unchanged

A tracked path is one Git already knows about through a commit or the index. A tracked file can be clean, modified, staged, staged and modified, or deleted from the working tree.

Example:

- README.md is already committed in HEAD: tracked.
- You edit README.md without staging: still tracked, modified state.
- You run git add README.md: still tracked, with staged changes.
- You commit: the new content becomes part of HEAD.

Tracked describes a path's relationship to the repository, not its current content state.

### 3.2. Viewing tracked files

~~~bash
git ls-files
~~~

This command displays paths in the index. Under normal state, this is the list of files Git is tracking and has recorded in the index.

You can filter by directory:

~~~bash
git ls-files -- src/
~~~

Note: during a merge conflict, the index may contain unmerged stages. In that situation, git ls-files --stage or git ls-files -u helps inspect the detailed structure.

### 3.3. The clean state

A tracked file is in a clean state when its content and Git-tracked metadata in the working tree match the index, and the index matches HEAD for that path.

If the repository has no changes, git status typically reports:

~~~text
On branch main
nothing to commit, working tree clean
~~~

Clean is a comparison state at the moment of inspection. If you edit the file afterward, it transitions to modified.

## 4. Modified — tracked files that have changed

### 4.1. Editing a file without staging

Suppose README.md has already been committed. You open the file, change a line, and save it.

Check:

~~~bash
git status
git diff -- README.md
~~~

Git reports README.md as modified in the working tree. The new content has not been added to the index yet, so the next commit will not include that change.

### 4.2. Staging one version and continuing to edit

This is an important scenario:

~~~bash
git add README.md
~~~

At this point, the current version of README.md is stored in the index. Then you edit the file again and save.

Now there are two different versions:

- Index: the staged version.
- Working tree: the newer, unstaged version.

Check:

~~~bash
git status
git diff --cached -- README.md
git diff -- README.md
~~~

Git may display the same path in both the staged group and the unstaged group. That is not an error. You selected one version for commit, and then continued modifying the file after that staging step.

### 4.3. Re-staging the latest version

If you want to include all current content in the next commit:

~~~bash
git add README.md
~~~

This command updates the index entry with the latest working tree content. Afterward:

~~~bash
git diff --cached -- README.md
git diff -- README.md
~~~

If no further edits were made after the last add, git diff will be empty for that file.

### 4.4. Modified does not only mean text content

Git can detect changes in:

- File content.
- The file's executable bit.
- Path changes due to rename or delete.
- Symbolic links.
- Certain metadata related to object type.

Therefore, when git status reports modified, check the diff or mode information if text content shows no obvious difference.

## 5. Staged — changes selected for commit

### 5.1. What does staging mean?

Staged means the change has been recorded in the index. It is a candidate for the next commit's snapshot.

Common staging command:

~~~bash
git add README.md
~~~

Inspect staged content:

~~~bash
git diff --cached
~~~

Only changes in the index are included in a normal commit. Other changes sitting in the working tree remain unstaged.

### 5.2. Staging new, modified, and deleted files

Common usages:

~~~bash
git add new-file.txt
git add src/PaymentService.java
git add -A
~~~

- git add file: stages a specific path, including new or modified content.
- git add -A: updates the index for all changes in the working tree, including additions, modifications, and deletions. If a pathspec is provided, updates only within that pathspec scope.
- git add -u: stages changes to already tracked paths, including modifications and deletions; does not add new untracked files. If a pathspec is provided, applies only within the specified scope.

If you want to restrict to a directory:

~~~bash
git add -A -- src/
~~~

When running these commands without a pathspec, Git updates the entire working tree. Use a pathspec such as src/ if you only want to stage part of the repository.

### 5.3. Partial staging with git add -p

When you only want to include certain hunks in a commit:

~~~bash
git add -p
~~~

Git displays each change hunk one by one and asks whether to stage each piece. Common choices:

- y: stage the current hunk.
- n: skip the current hunk.
- s: split the hunk if possible.
- e: edit the patch.
- q: quit.

Then review again:

~~~bash
git diff --cached
git diff
~~~

This approach is useful when a single file contains changes belonging to multiple tasks.

### 5.4. Staging does not lock file contents

The index holds the staged snapshot; it does not lock files on disk. You can still continue editing the file, and the new edits become unstaged.

This is why you should check both git diff --cached and git diff before committing.

## 6. Committed — snapshots recorded in history

### 6.1. Commit turns the index into history

When you run:

~~~bash
git commit -m "Update project documentation"
~~~

Git creates a commit from the current index contents. The commit references a tree object describing the snapshot; it also stores parent, author, committer, and message metadata.

After committing, the committed changes become part of HEAD. If the working tree has no other modifications, the repository returns to a clean state.

### 6.2. Inspecting commit contents

~~~bash
git show --stat --oneline HEAD
git show --format=fuller HEAD
git log -1 --oneline
~~~

To view a file inside a commit:

~~~bash
git show HEAD:README.md
~~~

This command displays the version of README.md stored in the HEAD commit, not uncommitted working tree contents.

### 6.3. Commit takes only staged content

Example:

1. You edit A.java and B.java.
2. You run git add A.java only.
3. You run git commit.

The commit only contains the staged changes of A.java. Changes in B.java stay in the working tree and continue to be reported as modified.

Check before committing:

~~~bash
git diff --cached --name-status
git diff --cached
git status
~~~

Do not guess what a commit will contain just by looking at files on disk; inspect the index.

### 6.4. The git commit -a option

You can use:

~~~bash
git commit -am "Update tracked files"
~~~

The -a option tells Git to automatically stage modifications and deletions of already tracked files before committing. It does not automatically add new untracked files.

If you just created a new file, you still need git add for that file before committing.

### 6.5. Amending the most recent commit with --amend

If you just committed and want to add or revise changes:

~~~bash
git add README.md
git commit --amend
~~~

This command recreates the last commit with the updated index contents and edited commit metadata. The commit ID will change.

Only use this when you understand the impact on history. If the commit has already been pushed and others depend on it, amending can force the team to deal with rewritten history.

## 7. Transitioning between states with Git commands

### 7.1. Unstaging a file while keeping working tree contents

If you staged something by mistake:

~~~bash
git restore --staged README.md
~~~

This command restores the path's index entry to match HEAD while keeping the working tree contents intact. If the file is new and has never been committed, the command removes the staged entry from the index and the file remains on disk as untracked.

Check:

~~~bash
git status
~~~

In older Git versions, you may encounter this form:

~~~bash
git reset HEAD -- README.md
~~~

This is a way to unstage a path without deleting working tree changes.

### 7.2. Discarding unstaged working tree changes

If you want to restore a tracked file from the index and discard unstaged edits:

~~~bash
git restore README.md
~~~

This command can overwrite unstaged local content. Inspect or back up anything you need to keep before running it.

If the file already has staged changes and you run restore without --staged, Git restores the working tree to match the index; the staged portion is preserved.

### 7.3. Restoring both index and working tree to HEAD

If you want to discard both staged and unstaged changes for a tracked file:

~~~bash
git restore --source=HEAD --staged --worktree -- README.md
~~~

This command updates both the index and the working tree from HEAD. It can discard all uncommitted changes to that path.

Only run this once you have verified the exact file and no longer need the current changes.

### 7.4. Removing a tracked file

To delete a file and stage the deletion:

~~~bash
git rm -- old-file.txt
~~~

Then verify:

~~~bash
git status
git diff --cached
~~~

When you commit, the new snapshot will no longer include that path. Older commits still retain the file's contents in history.

### 7.5. Untracking a file while keeping it on disk

If you want to keep a file locally but remove it from the index and future commits:

~~~bash
git rm --cached -- .env
~~~

Usually combined with .gitignore:

~~~gitignore
.env
~~~

Then:

~~~bash
git add .gitignore
git commit -m "Stop tracking local environment file"
~~~

Note: if .env previously contained committed secrets, stopping tracking does not remove those secrets from history. Revoke credentials before cleaning history according to security procedures.

### 7.6. Renaming a file with git mv

~~~bash
git mv old-name.txt new-name.txt
~~~

This command moves the file and updates the index. Git does not store a dedicated rename object type; when viewing diffs, Git infers renames based on content and paths between two snapshots.

You can check:

~~~bash
git status --short
git diff --cached --summary
~~~

If you rename manually in a file manager, Git can still detect the rename when comparing content, but git mv makes updating both the working tree and index explicit.

## 8. Reading status with git status

### 8.1. Full format

~~~bash
git status
~~~

Git normally splits the output into:

- Changes to be committed: staged changes.
- Changes not staged for commit: tracked changes not yet staged.
- Untracked files: new files not yet tracked.

A file can appear in both the staged and unstaged groups if you edit it after staging.

### 8.2. Short format

~~~bash
git status --short
~~~

Example:

~~~text
 M README.md
M  src/App.java
MM config/app.yml
A  notes.txt
?? scratch.txt
D  old.txt
~~~

The first column describes the index state relative to HEAD; the second column describes the working tree relative to the index.

| Code | Common meaning |
| --- | --- |
| M | Modified |
| A | Added |
| D | Deleted |
| R | Renamed |
| C | Copied |
| ?? | Untracked |
| !! | Ignored, when showing ignored files is requested with --ignored |

Example:

- ` M README.md`: tracked file modified in the working tree, not staged.
- `M  src/App.java`: staged change, no additional working tree modifications.
- `MM config/app.yml`: one version staged, then edited further in the working tree.
- `A  notes.txt`: new file staged.
- `?? scratch.txt`: untracked file.

To also show ignored paths:

~~~bash
git status --short --ignored
~~~

For complex states such as renames or conflicts, read both columns and the full status message to understand accurately.

### 8.3. Porcelain output for scripts

~~~bash
git status --porcelain=v1
~~~

Porcelain output has a more stable format than human-facing output, suitable for scripts and automation tools. If you need to handle filenames with special characters or newlines, use the NUL option:

~~~bash
git status --porcelain=v1 -z
~~~

Do not parse standard output by splitting on whitespace, because filenames can contain spaces or special characters.

## 9. Complete example of a file's lifecycle

Suppose the repository already has an initial commit and you want to add new documentation.

### Step 1 — Create the file

~~~bash
printf "Deployment notes\n" > deployment.md
git status --short
~~~

The output might be:

~~~text
?? deployment.md
~~~

The file is untracked.

### Step 2 — Stage the file

~~~bash
git add deployment.md
git status --short
~~~

Output:

~~~text
A  deployment.md
~~~

The file has been added to the index. It is still a new file relative to HEAD, but it is now staged.

### Step 3 — Edit the file after staging

~~~bash
printf "Rollback procedure\n" >> deployment.md
git status --short
~~~

You may see:

~~~text
AM deployment.md
~~~

The index still holds the previously staged version; the working tree contains the newer content.

### Step 4 — Inspect both versions

~~~bash
git diff --cached -- deployment.md
git diff -- deployment.md
~~~

The first command shows the staged content; the second shows the unstaged addition.

### Step 5 — Stage the latest version

~~~bash
git add deployment.md
git diff --cached -- deployment.md
git diff -- deployment.md
~~~

Now all intended content resides in the index.

### Step 6 — Commit

~~~bash
git commit -m "Add deployment notes"
~~~

The file has been recorded in a new commit.

### Step 7 — Verify

~~~bash
git status
git show --stat --oneline HEAD
~~~

If no other changes remain, the working tree returns to a clean state. deployment.md is now tracked and its latest snapshot is committed.

## 10. Special cases to remember

### 10.1. File deleted outside Git

If you delete a tracked file using File Explorer or the shell rm command, Git detects that the working tree is missing the file compared to the index.

~~~bash
git status
~~~

To stage the deletion:

~~~bash
git add -u -- path/to/file
~~~

Or:

~~~bash
git rm -- path/to/file
~~~

If you want to restore the file from the index:

~~~bash
git restore -- path/to/file
~~~

### 10.2. Ignored file that needs to be added intentionally

If a file matches a .gitignore rule, normal git add may reject or skip it. You can force-add it:

~~~bash
git add -f path/to/file
~~~

Before using -f, verify the file does not contain secrets, build outputs, or content prohibited from the repository.

### 10.3. Binary files

For binary files, git diff may only report that the files differ without displaying human-readable content. Tracked/modified/staged states still work the same way.

You can view statistics:

~~~bash
git diff --stat
git diff --cached --stat
~~~

For large files, consider Git LFS according to repository policy.

### 10.4. Renames are inferred by Git

Git does not store a separate rename event in commits. When comparing two trees, Git detects potential renames based on content similarity.

Therefore, the same move operation may appear as a rename or as a delete + add if content changes too much or similarity thresholds differ.

### 10.5. A directory with multiple states

If a directory contains new files, modified files, and deleted files, git status can list each path with its own state. Do not infer the state of an entire directory from a single line.

Use:

~~~bash
git status --short -- src/
git diff --stat
git diff --cached --stat
~~~

## 11. Common mistakes

- **Thinking git add creates a commit:** git add only updates the index; git commit is required to record the snapshot in history.
- **Thinking tracked always means clean:** tracked only means Git manages the path; its contents can still be modified.
- **Thinking staged cannot be edited further:** you can keep editing a file after staging; new edits become unstaged.
- **Running git commit without checking the index:** commits take staged content, not everything open in your editor.
- **Assuming git add -A only adds new files:** it updates additions, modifications, and deletions within scope.
- **Assuming git commit -a adds untracked files:** -a only applies to already tracked files.
- **Thinking .gitignore stops tracking already committed files:** git rm --cached is needed to remove the file from the index; older history remains.
- **Using git restore without checking:** restore can overwrite local changes not saved elsewhere.
- **Confusing ignored with untracked:** ignored files do not normally appear in regular untracked listings.
- **Thinking Git tracks empty directories:** Git requires at least one file to store a directory path in a tree.

## 12. Quick reference table

| Goal | Command |
| --- | --- |
| View repository status | git status |
| View short status | git status --short |
| List tracked files in index | git ls-files |
| List untracked files | git ls-files --others --exclude-standard |
| View unstaged changes | git diff |
| View staged changes | git diff --cached |
| Stage a file | git add path/to/file |
| Stage all changes in scope | git add -A |
| Stage changes to tracked files | git add -u |
| Stage hunk by hunk | git add -p |
| Commit the index | git commit -m "message" |
| Unstage a file | git restore --staged path/to/file |
| Discard unstaged edits | git restore path/to/file |
| Delete tracked file and stage deletion | git rm path/to/file |
| Untrack while keeping local file | git rm --cached path/to/file |
| Rename and update index | git mv old-name new-name |
| Check ignore rule | git check-ignore -v path/to/file |
| View latest commit | git log -1 --oneline |

## 13. Summary

The file lifecycle in Git is best understood across three layers: HEAD is the committed snapshot, the index is the snapshot prepared for the next commit, and the working tree is the content on disk. A new file can begin in the untracked state; after git add, it becomes tracked and staged; after git commit, its content is recorded in history. For tracked files, editing produces the modified state; staging selects a version into the index; committing writes that version into a new snapshot.

Use git status to observe the big picture, git diff to inspect unstaged changes, git diff --cached to inspect staged changes, and git show to verify commit contents. Before each commit, confirm the index contains only intended changes. When you need to unstage or restore content, choose the right restore/rm command and understand clearly which data will be modified.

Mastering these states helps you control commit contents accurately, avoid adding unintended files, and work more safely with Git repositories.

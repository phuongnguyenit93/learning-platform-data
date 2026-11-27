# Differences Between Content in the Index and the Latest Edits on Disk

In Git, a single file can simultaneously have three different versions: the committed version in HEAD, the version placed into the staging area (index), and the newest version sitting on disk in the working tree. When you edit a file after running git add, the index still holds the previously staged snapshot, while the working tree contains the newer edits. Therefore, a single file can have both staged changes and unstaged changes at the same time.

In the **Files and Index** chapter of the **SOURCE_CONTROL_GIT** module, this lesson focuses on how to recognize and inspect differences between the index and the working tree. You will understand which two sides git diff compares, read the two-column status of git status, view the exact staged content, and choose how to stage or unstage without losing edits you need to keep.

After this lesson, you will be able to:

- Distinguish HEAD, the index, and the working tree.
- Explain why editing a file after git add does not automatically update the staging area.
- Use git diff, git diff --cached, and git diff HEAD for their intended purposes.
- Read the two status columns in git status --short.
- Inspect the blob content currently sitting in the index and its corresponding object ID.
- Stage an entire file or only part of it using git add -p.
- Unstage while preserving content in the working tree.
- Recognize untracked files and conflicted index entries.
- Check differences caused by line endings or Git content filters.

## 1. Three Places Storing a File's State

Git does not take all content directly from disk to create a commit. Git uses the index as the snapshot prepared for the next commit.

| Storage Location | Content | Role |
| --- | --- | --- |
| HEAD | Snapshot of the current commit | Latest committed version on the checked-out branch or commit |
| Index (staging area) | Snapshot selected for the next commit | Holds content staged via git add or equivalent operations |
| Working tree | Actual files in the project directory | Where you open, create, edit, and delete files |

You can visualize the data flow:

~~~text
                git add
Working tree  ------------>  Index  ------------>  HEAD
   file on disk                staged snapshot       commit
                                      git commit

git diff:          compares Index vs. Working tree
git diff --cached: compares HEAD vs. Index
git diff HEAD:     compares HEAD vs. Working tree
~~~

HEAD is the current commit reference. The index is the snapshot of changes you selected to include in the commit. The working tree can continue changing after staging. Git keeps these three states separate so you can prepare one commit while continuing to edit files.

The index is not a folder containing full copies of every file. It is a data structure recording the path, file mode, object ID, and required metadata. Staged file content is stored as a blob in the object database; the index references that blob.

## 2. Why Can a File Be Both Staged and Modified?

Suppose src/app.js initially has the content:

~~~javascript
function greet(name) {
  return "Hello " + name;
}
~~~

You edit the file and stage it:

~~~bash
git add src/app.js
~~~

At this moment, the index holds the snapshot after the first edit. Then you continue editing the file on disk:

~~~javascript
function greet(name) {
  if (!name) return "Hello guest";
  return "Hello " + name;
}
~~~

Now:

- HEAD still holds the old version in the commit.
- The index holds the previously staged version.
- The working tree holds the newer version with the name check line.

Git does not automatically stage the second edit. The index only changes when you run an operation that updates the staging area, such as git add, git add -p, or an equivalent Git command.

This is a normal state, not an error. It lets you stage part of your changes, keep editing another part, and create a commit containing only what you selected.

## 3. Three Most Important Diff Commands

### git diff: Index vs. Working Tree

~~~bash
git diff
~~~

This command shows unstaged changes: content in the working tree that differs from content currently in the index. If you edited a file after the most recent git add, the new edits appear here.

### git diff --cached: HEAD vs. Index

~~~bash
git diff --cached
~~~

--cached is equivalent to --staged. This command shows staged changes that will go into the next commit if you commit right now.

### git diff HEAD: HEAD vs. Working Tree

~~~bash
git diff HEAD
~~~

This command compares the current commit snapshot with tracked content in the working tree. It shows the total changes on disk relative to HEAD, including both staged and unstaged parts. It does not include untracked file contents in the standard diff.

Summary:

| Command | Comparison | Question Answered |
| --- | --- | --- |
| git diff | Index ↔ Working tree | What did I edit since the last stage? |
| git diff --cached | HEAD ↔ Index | What have I selected for the next commit? |
| git diff HEAD | HEAD ↔ Working tree | How does disk currently differ from the current commit? |

Example inspecting a single file:

~~~bash
git diff -- src/app.js
git diff --cached -- src/app.js
git diff HEAD -- src/app.js
~~~

The -- separates options/revisions from paths. It is especially useful when a filename resembles a branch name or starts with a hyphen.

## 4. Reading a Diff Example When a File Has Two Layers of Changes

Suppose HEAD commit has:

~~~javascript
const timeout = 1000;
connect(timeout);
~~~

You change timeout to 2000 and stage it:

~~~bash
git add src/config.js
~~~

Then you further edit the connect call:

~~~javascript
const timeout = 2000;
connect(timeout, { retry: true });
~~~

Result:

**git diff --cached** shows the staged portion:

~~~diff
-const timeout = 1000;
+const timeout = 2000;
 connect(timeout);
~~~

**git diff** shows the edits made after staging:

~~~diff
 const timeout = 2000;
-connect(timeout);
+connect(timeout, { retry: true });
~~~

**git diff HEAD** shows the total changes relative to the commit:

~~~diff
-const timeout = 1000;
+const timeout = 2000;
-connect(timeout);
+connect(timeout, { retry: true });
~~~

If you run git commit now, Git creates a commit from the content in the index. The retry: true part is not staged and therefore is not included in that commit.

## 5. Reading the Two Status Columns of git status --short

Run:

~~~bash
git status --short
~~~

Each line normally has two status characters before the path:

~~~text
XY path
~~~

- Column **X** describes the status of the index compared to HEAD.
- Column **Y** describes the status of the working tree compared to the index.

Example:

~~~text
 M src/app.js
M  src/config.js
MM src/service.js
A  src/new-file.js
AM src/another-file.js
?? notes.txt
~~~

Meaning:

| Status | Column X | Column Y | Interpretation |
| --- | --- | --- | --- |
| X blank, Y=M | Unchanged vs. HEAD | Modified vs. index | Unstaged changes only |
| X=M, Y blank | Modified vs. HEAD | Unchanged vs. index | Has staged changes |
| X=M, Y=M | Modified vs. HEAD | Edited further after staging | Both staged and modified |
| X=A, Y blank | New file staged | Unchanged vs. index | New file will be added to the commit |
| X=A, Y=M | New file staged | File modified further | Commit takes the staged snapshot, not the latest edits |
| X=?, Y=? | Not yet in index | Not yet tracked by Git | Untracked file |

Other statuses may include D (deleted), R (renamed), C (copied), or U (unmerged). For deleted files:

- X=D: deletion is staged.
- Y=D: file is deleted on disk, but the index still holds its content.

Do not read the two-column status as a single symbol. With MM, the first character and the second character answer two different questions.

### Viewing Full Status Output

~~~bash
git status
~~~

Full output is typically grouped into:

- Changes to be committed: changes in the index.
- Changes not staged for commit: unstaged changes in the working tree.
- Untracked files: files not yet tracked.

If you need stable machine-readable output, use porcelain:

~~~bash
git status --porcelain=v1
~~~

Porcelain is a format meant for scripts. Do not write scripts relying on human-readable status prose, which can vary across versions or languages.

## 6. Inspecting Exact Content Currently in the Index

When a file on disk has further edits, opening the file in an editor only shows you the working tree. To view the currently staged version, use:

~~~bash
git show :src/app.js
~~~

The :path syntax fetches content from the index. It is useful when you need to confirm what the next commit will contain.

View the index entry and object ID:

~~~bash
git ls-files --stage -- src/app.js
~~~

Output looks like:

~~~text
100644 1a2b3c4d... 0    src/app.js
~~~

The fields include:

- File mode, e.g., 100644 for a regular file or 100755 for an executable file.
- Object ID of the blob referenced by the index.
- Stage number.
- Path.

In normal state, the stage number is 0. You can use the object ID to check the object type and content:

~~~bash
git cat-file -t 1a2b3c4d
git cat-file -p 1a2b3c4d
~~~

The object ID in the example is illustrative; replace it with the actual ID from your output.

If you want to view the file content in the HEAD commit:

~~~bash
git show HEAD:src/app.js
~~~

Three views:

| Command | Version Viewed |
| --- | --- |
| Open file in editor | Working tree |
| git show :src/app.js | Index |
| git show HEAD:src/app.js | HEAD commit |

## 7. git add Captures a Snapshot at Execution Time

git add does not mark a file in a "stage all future changes automatically" way. This command updates the index with the path's current content at the moment it runs.

Example:

~~~bash
git add src/app.js
git diff --cached -- src/app.js
~~~

Then you edit the file again:

~~~bash
# Open editor and continue editing src/app.js
git diff -- src/app.js
~~~

The new edits appear in git diff because the index still holds the earlier snapshot.

To put the latest edits into the index:

~~~bash
git add src/app.js
~~~

At this point git diff -- src/app.js typically shows no difference if no other new edits exist.

### git add -A and git add -u

- git add -A updates the index for new files, modified files, and deleted files within the target scope.
- git add -u updates already-tracked files, including modifications and deletions; it does not add new untracked files.
- git add <path> updates only the specified path.

Before running git add -A in a large repository, check git status to know which new files will be added to the index.

## 8. Partial Staging with git add -p

When a file has multiple unrelated changes, you can stage only selected hunks:

~~~bash
git add -p src/app.js
~~~

Git shows each hunk and asks how to handle it. Common options:

| Key | Meaning |
| --- | --- |
| y | Stage the current hunk |
| n | Skip the current hunk |
| q | Quit without processing remaining hunks |
| a | Stage the current hunk and all remaining hunks in the file |
| d | Skip the current hunk and all remaining hunks in the file |
| s | Split the current hunk into smaller hunks if possible |
| e | Edit the hunk's patch before staging |
| ? | Show help |

After selecting a portion:

~~~bash
git diff --cached
git diff
git status --short
~~~

You can see the same file appearing in both staged and unstaged sections. This is how to build small, focused commits even when changes live in the same file.

If a hunk contains both changes to commit and changes not yet ready, try s first to split it smaller. Only use e when you understand unified diff format; editing a patch incorrectly can make the hunk invalid or stage the wrong content.

## 9. Unstaging While Keeping Edits on Disk

If you staged the wrong file or hunk, you can revert the index back to HEAD content without changing the working tree:

~~~bash
git restore --staged src/app.js
~~~

After this command:

- The index entry for src/app.js returns to the version in HEAD.
- Edits on disk are preserved.
- Changes will appear in git diff instead of git diff --cached.

This is a common operation when you need to re-select what gets committed.

Equivalent command in older usage:

~~~bash
git reset HEAD -- src/app.js
~~~

When specifying a path, git reset updates the index to HEAD and does not move the branch.

### Partially Unstaging

You can use patch mode to choose hunks to revert in the index:

~~~bash
git restore --staged -p src/app.js
~~~

Review each hunk and decide which parts to remove from the staging area. Afterward, verify both diffs.

## 10. Being Careful Between Unstaging and Discarding Disk Edits

The following two commands have different effects:

~~~bash
git restore --staged src/app.js
git restore --worktree src/app.js
~~~

- --staged updates the index and preserves the working tree.
- --worktree updates the file on disk from the index, which can discard unstaged edits.

If you run git restore --worktree src/app.js when the index has a staged snapshot, the content on disk will be replaced by the snapshot in the index. Any unstaged edits in that file can be lost.

Before running a command that modifies the working tree, check:

~~~bash
git status --short
git diff -- src/app.js
git diff --cached -- src/app.js
~~~

If you need to discard both staged and unstaged changes, that operation can lose all edits made since HEAD. Only perform it after confirming the content does not need to be kept or already has a safe copy/commit.

Do not use git reset --hard merely to fix a staged/unstaged state when you do not yet know which files will be affected.

## 11. Commits Take Content from the Index

When you run:

~~~bash
git commit -m "fix: handle empty name"
~~~

Git creates the commit from the snapshot in the index, not from all the latest content on disk.

If a file is in the MM state:

- Part X is the staged change relative to HEAD.
- Part Y is the further edit on disk relative to the index.
- The commit records only part X.
- Part Y stays in the working tree after committing.

Check after committing:

~~~bash
git status --short
git show --stat --oneline HEAD
git diff
~~~

If unstaged changes remain, they continue to appear in git diff. This is expected behavior.

### Does git commit -a Automatically Stage All Files?

No. -a automatically stages modifications and deletions of already-tracked files before creating the commit. It does not automatically add new untracked files. Like every other commit method, content is taken from the index after that auto-staging step.

~~~bash
git commit -am "fix: update tracked config"
~~~

Be careful if a file currently has both staged and unstaged parts: -a can pull all changes of tracked files into the index before committing, causing the commit to contain more content than you originally staged. If you need exact control, review the diff and use a standard git commit.

## 12. Untracked Files Do Not Appear in Normal git diff

A new file not yet staged typically has status ??:

~~~text
?? notes.txt
~~~

git diff and git diff HEAD do not show untracked file contents by default because the file has no entry in the index yet. git status still lists it.

To put the file into the index:

~~~bash
git add notes.txt
git diff --cached -- notes.txt
~~~

If you want to view the new file's content as a diff before staging, you can compare it with an empty file using git diff --no-index:

~~~bash
git diff --no-index -- /dev/null notes.txt
~~~

On Windows, /dev/null does not exist in this form in every shell; use the corresponding null device mechanism or open the file to review. A simple, consistent approach in a Git workflow is inspecting the file, then running git add and checking git diff --cached.

Another option is marking intent-to-add:

~~~bash
git add -N notes.txt
git diff -- notes.txt
~~~

-N (intent-to-add) creates a temporary entry in the index so Git can present a diff of the new file without staging the full content like a regular git add. This state may behave differently from a fully staged file; check status and diff before committing.

## 13. The Index During a Merge Conflict

During a conflicted merge or rebase, a single path can have multiple entries in the index instead of a single stage 0 entry.

Check:

~~~bash
git status
git ls-files -u
~~~

Common stages:

| Stage | Meaning in a Merge Conflict |
| --- | --- |
| 1 | Common base version |
| 2 | Ours version |
| 3 | Theirs version |

View object ID and mode of each version:

~~~bash
git ls-files --stage -- src/app.js
~~~

After editing the file to the desired result, run:

~~~bash
git add src/app.js
git ls-files --stage -- src/app.js
~~~

git add replaces the conflicted entries with a single stage 0 entry representing the resolved result. Afterward, check git status and continue the pending merge/rebase Git command.

Do not confuse index stages 1/2/3 with columns X/Y in git status --short. Stage numbers describe multiple versions of a conflicted file; X/Y describe states across HEAD, the index, and the working tree.

## 14. How Does Git Detect That a File on Disk Has Changed?

The index stores the object ID of staged content along with file metadata such as mode and stat information. Git can use metadata like modification time and size to quickly detect files that may have changed. When needed, Git reads content and computes hashes to determine differences.

This avoids Git having to read and re-hash every file in the repository on every status run. However, filesystem metadata can be affected by sync tools, low-resolution timestamps, or operations outside Git. If you suspect status has not refreshed:

~~~bash
git update-index --refresh
git status
~~~

--refresh asks Git to refresh stat information of index entries against the working tree; it does not mean staging new file content. If the file actually changed, the modified state is still detected and you still need git add to update content in the index.

Do not use git update-index --assume-unchanged or --skip-worktree merely to hide changes without understanding their purpose. These flags affect how Git checks the working tree and can mislead users about file state.

## 15. Line Endings and Filters Can Make Index Content Differ Byte-for-Byte from Disk

Git may apply clean/smudge filters or line ending normalization according to .gitattributes and configuration. Therefore, the blob content staged in the index may not match the file on disk byte-for-byte, even though Git treats them as logically identical under conversion rules.

For example, a repository normalizes text to LF in the object database, while the working tree on Windows uses CRLF. In that case:

- The file on disk may use CRLF.
- Staged/committed content may be normalized to LF.
- git diff typically presents differences according to the conversion rules Git applies.

If widespread diffs appear after switching machines or editors, check:

~~~bash
git ls-files --eol -- src/app.js
git check-attr text eol -- src/app.js
git config --show-origin --get core.autocrlf
~~~

Do not assume the index is wrong just because line ending bytes on disk differ from the staged blob. Check the repository's attributes and clean/smudge rules.

## 16. Practical Workflow: Stage Partially Then Keep Editing the File

Suppose you are editing src/payment.js with two changes:

1. Fixing a payment total calculation bug, ready to commit.
2. Adding diagnostic logs, needing further checks before committing.

### Step 1: view initial status

~~~bash
git status --short
git diff -- src/payment.js
~~~

### Step 2: stage the bug fix

~~~bash
git add -p src/payment.js
~~~

Choose y for the bug-fix hunk and n for the log hunk. If Git merges both into one hunk, use s to split if possible or e to edit the patch carefully.

### Step 3: confirm the staged portion

~~~bash
git diff --cached -- src/payment.js
git diff -- src/payment.js
git status --short
~~~

Make sure diff --cached contains only the total calculation bug fix. The remaining log edits should show up in git diff.

### Step 4: commit the selected portion

~~~bash
git commit -m "fix(payment): calculate total correctly"
~~~

### Step 5: check the remaining changes

~~~bash
git status --short
git diff
~~~

The unstaged log part remains in the working tree after the commit. You can continue editing, staging, and committing it in a separate commit when ready.

## 17. Quick Diagnostic Commands

| Goal | Command |
| --- | --- |
| View unstaged changes | git diff |
| View staged changes | git diff --cached |
| View total changes vs. HEAD | git diff HEAD |
| View short two-column status | git status --short |
| View snapshot of file in index | git show :path/to/file |
| View snapshot of file in HEAD | git show HEAD:path/to/file |
| View OID and stage of index entry | git ls-files --stage -- path/to/file |
| List conflicted entries | git ls-files -u |
| Re-stage current content | git add -- path/to/file |
| Unstage, keep file on disk | git restore --staged -- path/to/file |
| Stage hunk by hunk | git add -p -- path/to/file |
| Check whitespace in diff | git diff --check |

When reviewing a specific file, put the path after -- to prevent Git from misinterpreting the filename as a revision or option.

## 18. Common Misconceptions

### After git add, are all subsequent edits staged automatically?

No. git add captures content at the time it runs. Subsequent edits stay in the working tree until staged again.

### Does git diff show all changes relative to the commit?

No. git diff compares the index with the working tree by default. To compare with the current commit, use git diff HEAD.

### Does git diff --cached show the newest content on disk?

No. It shows content in the index compared to HEAD. If the file was edited after staging, the newer part appears in git diff.

### Does commit take files from the working tree?

Commit takes the snapshot from the index. Unstaged edits are not included in a standard commit.

### Will untracked files appear in git diff?

No. git status lists untracked files. To bring one into the staged diff, run git add; you can use git add -N to inspect intent-to-add.

### Does unstaging lose changes on disk?

git restore --staged only updates the index and keeps the working tree. git restore --worktree can overwrite unstaged changes with index content, so verify first.

### Does MM in git status mean two different files?

No. It is one file with changes at both layers: index differs from HEAD, and working tree differs from index.

## 19. Self-Check

You edit src/service.js, run git add, then continue editing the file. git status --short displays:

~~~text
MM src/service.js
~~~

Answer the following:

1. Which comparisons do columns X and Y describe?
2. Which changes does git diff display?
3. Which part does git diff --cached display?
4. If you run git commit right now, what content goes into the commit?
5. Which command shows the exact content of src/service.js currently in the index?
6. Which command removes the file from the staging area while keeping changes on disk?
7. If you want to re-stage all current content, which command do you use?

**Hint:** X is index vs. HEAD; Y is working tree vs. index. git diff shows edits made since the last stage; git diff --cached shows what is staged vs. HEAD. Commit takes index content. Use git show :src/service.js to view the staged snapshot. Use git restore --staged src/service.js to unstage while keeping the working tree. Use git add src/service.js to re-stage current content.

## Conclusion

HEAD, the index, and the working tree are three distinct file states. git add updates the snapshot in the index at execution time; any edits afterward remain on disk until staged again. Use git diff to inspect unstaged changes, git diff --cached to view content prepared for commit, and git diff HEAD to see the total difference from the current commit. Read both X/Y columns of git status --short, inspect staged content with git show :path, and unstage with git restore --staged when you need to preserve files on disk. Understanding these three state layers helps you create intentional commits, avoid accidentally committing unwanted changes, and preserve unfinished work safely.

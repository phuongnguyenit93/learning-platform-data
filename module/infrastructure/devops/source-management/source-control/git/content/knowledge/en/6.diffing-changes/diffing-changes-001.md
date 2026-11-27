# Comparing the Working Directory with the Index Using git diff

## Objectives

In Git, you can edit files multiple times before creating a commit. Part of your changes may already be placed in the staging area, while another part remains in the working tree. The `git diff` command helps you see the exact differences between these two areas.

This lesson focuses on the comparison between the **working tree and the index**:

~~~bash
git diff
~~~

This command is used to inspect changes in files that are tracked by Git but have not yet been staged. After this lesson, you will be able to:

- Distinguish between the working tree, the index, and the current commit (`HEAD`).
- Understand exactly which two states `git diff` compares.
- Read added lines, removed lines, and changed regions (hunks) in a diff.
- Inspect changes for only a single file or a specific set of paths.
- Identify staged, unstaged, and untracked files.
- Selectively stage or unstage changes.
- Inspect whitespace, binary files, mode changes, and special diff cases.
- Use diffs to verify the exact content that will go into the next commit.

## Three States to Distinguish

When working with Git, a file can be viewed across three important states:

1. **HEAD:** snapshot of the current commit on the checked-out branch.
2. **Index (staging area):** snapshot prepared for the next commit.
3. **Working tree:** actual file contents in your working directory.

Typical change flow:

~~~text
              HEAD
        commit snapshot
                 |
                 | git diff --cached
                 v
               Index
          staging area
                 |
                 | git diff
                 v
            Working tree
        files being edited
~~~

Two directly related comparisons:

- `git diff`: compares the index with the working tree.
- `git diff --cached`: compares HEAD with the index.

If you want to view the total changes in tracked files compared to the current commit:

~~~bash
git diff HEAD
~~~

This command compares HEAD with the working tree, so it includes both staged and unstaged changes. Untracked files still do not automatically appear in this diff.

### The Index Is Not Another Directory

The index is a Git data structure used to store the contents and metadata of paths selected for the next commit. It is usually stored in `.git/index`, though you should not edit this file directly.

When you run:

~~~bash
git add src/PaymentService.java
~~~

Git updates the index with the file's current content at the time of staging. If you subsequently continue editing `PaymentService.java`, the working tree will differ from the index. `git diff` will display those new edits.

Therefore, the staging area is not simply a list of filenames. For a staged file, the index holds a specific version of the content prepared to be committed.

## git diff Compares the Working Tree with the Index

Suppose `README.md` in the current commit has the following content:

~~~text
Project: Payment Service
Status: active
Owner: Platform Team
~~~

You edit the Status line to `Status: in development`, without staging it yet:

~~~text
Project: Payment Service
Status: in development
Owner: Platform Team
~~~

Run:

~~~bash
git diff
~~~

Git displays the differences between the version currently in the index and the version of the file in the working tree. Because the index still holds the content from the current commit, the output may look like this:

~~~diff
diff --git a/README.md b/README.md
index 3a7b1c2..8d4e5f6 100644
--- a/README.md
+++ b/README.md
@@ -1,3 +1,3 @@
 Project: Payment Service
-Status: active
+Status: in development
 Owner: Platform Team
~~~

Reading the output:

- Lines starting with `-` are present in the index but no longer in the working tree.
- Lines starting with `+` are present in the working tree but not in the index.
- Lines starting with a space are unchanged context lines.
- `--- a/README.md` and `+++ b/README.md` indicate the two sides being compared.
- `@@ -1,3 +1,3 @@` indicates the starting line and line count in both versions.

In this example, the file has unstaged changes. No commit has been created yet, and the index still retains the old version.

### Why Doesn't Git Compare Directly with the Remote?

By default, `git diff` does not access the remote. It compares local states: the index and the working tree. If the remote has new commits, that does not affect this comparison.

To view changes between two commits or two branches, you must specify the two comparison targets explicitly, for example:

~~~bash
git diff main origin/main
~~~

That serves a different purpose from inspecting unstaged changes in the working tree.

## Reading Unified Diff Structure

A diff typically contains the following sections:

~~~diff
diff --git a/src/PaymentService.java b/src/PaymentService.java
index 4a12abc..7b34def 100644
--- a/src/PaymentService.java
+++ b/src/PaymentService.java
@@ -10,6 +10,8 @@ public class PaymentService {
     public void validate() {
-        checkAmount();
+        checkAmount();
+        checkCurrency();
+        checkAccountStatus();
     }
 }
~~~

### File Header Line

`diff --git a/... b/...` indicates which path's changes Git is presenting. The prefixes `a` and `b` represent the two sides of the comparison, not actual directory names.

### Index Line

`index <old>..<new> <mode>` typically shows the abbreviated blob object IDs on both sides and the file mode. When a file's content is modified, its blob ID usually changes.

### --- and +++ Lines

- `---` describes the old side (the index).
- `+++` describes the new side (the working tree).

In a diff for a new file marked with intent-to-add, or in other diff formats, one side may be represented as `/dev/null`. Always read the surrounding context rather than inferring every case from a single header line.

### Hunk Header @@

For example:

~~~text
@@ -10,6 +10,8 @@
~~~

The `-10,6` part indicates the starting line and line count of the old region. The `+10,8` part indicates the starting line and line count of the new region. Hunks help you focus on each changed area instead of re-reading the entire file.

### +, -, and Space Markers

| Symbol | Meaning |
|---|---|
| `+` | Line added in the working tree side |
| `-` | Line removed from the version in the index |
| Space | Unchanged context line |
| `\ No newline at end of file` | One side of the file lacks a trailing newline |

Do not confuse the `+` marker in a diff with staging. A diff only describes differences; to place content into the index, you still need `git add` or an equivalent staging action in your GUI.

## Observing Changes Before and After Staging

This is the most important sequence of operations for understanding `git diff`.

### Step 1: Edit a File

Suppose you edit `src/PaymentService.java`. View unstaged changes:

~~~bash
git diff -- src/PaymentService.java
~~~

The output shows where the working tree differs from the index.

### Step 2: Stage the Current Changes

~~~bash
git add src/PaymentService.java
~~~

After staging, the index is updated to match the file content at the time the command is run. Since the working tree and the index are now identical, running:

~~~bash
git diff -- src/PaymentService.java
~~~

typically prints no output.

However, the changes are still waiting to be committed. Inspect the staged portion with:

~~~bash
git diff --cached -- src/PaymentService.java
~~~

This command compares the index with HEAD. The newly staged content appears here.

### Step 3: Edit the File Again After Staging

Suppose you add another validation check to the same file without running `git add` again.

The file now has two different pending versions:

- Index: contains the changes staged in Step 2.
- Working tree: contains both the staged changes and the new edits from Step 3.

Run both commands:

~~~bash
git diff -- src/PaymentService.java
git diff --cached -- src/PaymentService.java
~~~

The first command shows only the edits made since the last stage. The second command shows the staged changes compared to HEAD.

You can check the total changes compared to the current commit:

~~~bash
git diff HEAD -- src/PaymentService.java
~~~

This command includes both staged and unstaged changes for the tracked file.

### Summary Table

| File State | `git diff` | `git diff --cached` | `git diff HEAD` |
|---|---|---|---|
| Edited only, not staged | Shows changes | Shows nothing | Shows changes |
| Staged, no further edits in working tree | Shows nothing | Shows changes | Shows changes |
| Staged, then edited further | Shows additional edits | Shows staged changes | Shows total changes |
| No changes | Shows nothing | Shows nothing | Shows nothing |

This table applies to files tracked by Git. Untracked files must be handled separately.

## Do Untracked Files Appear in git diff?

By default, no. `git diff` compares paths that Git can match between the index and the working tree. A new untracked file does not yet have a normal entry in the index, so `git diff` does not display its contents.

For example:

~~~bash
git status --short
~~~

Output:

~~~text
 M README.md
?? notes.txt
~~~

- `README.md` is tracked by Git and has changes.
- `notes.txt` is an untracked file.

`git diff` will display the changes in `README.md`, but will not display the new contents of `notes.txt`.

To start tracking the new file:

~~~bash
git add notes.txt
~~~

After staging, the new file is added to the index. Then:

~~~bash
git diff --cached -- notes.txt
~~~

displays the content that will be added to the next commit.

### Using intent-to-add to Diff a New File Without Staging Its Content

If you want Git to recognize a new path so it appears in diffs without putting all of its content into the staging area yet, you can use:

~~~bash
git add -N notes.txt
git diff -- notes.txt
git diff --cached -- notes.txt
~~~

`git add -N` (intent-to-add) creates a special entry in the index so Git knows the path will be added. The file's content is still treated as unstaged changes; `git diff` can show the new content compared to an empty file. This is not equivalent to a normal `git add notes.txt`.

If you want to remove the intent-to-add entry, you can run:

~~~bash
git restore --staged -- notes.txt
~~~

Afterward, `notes.txt` returns to being an untracked file. If you actually want to stage its content, run `git add notes.txt`.

## Comparing a Single File or a Group of Paths

You do not need to view the diff of the entire repository. You can specify paths after `--`:

~~~bash
git diff -- README.md
git diff -- src/PaymentService.java
git diff -- src/
~~~

The `--` separator distinguishes Git options from pathspecs. This syntax is useful when a filename might collide with an option name or start with a hyphen.

You can view multiple paths:

~~~bash
git diff -- README.md src/PaymentService.java
~~~

View only change statistics:

~~~bash
git diff --stat
git diff --stat -- src/
~~~

List only filenames:

~~~bash
git diff --name-only
~~~

List filenames along with their change status:

~~~bash
git diff --name-status
~~~

Common status codes:

| Code | Meaning |
|---|---|
| `M` | Modified |
| `A` | Added |
| `D` | Deleted |
| `R` | Renamed (when Git detects a rename) |
| `C` | Copied (when copy detection is enabled and thresholds are met) |

With the default `git diff`, new unstaged files remain untracked and do not appear. The `A` status is usually more useful when inspecting the diff between the index and HEAD via `git diff --cached`.

## Viewing Changes by Line or Word

When a small change occurs on a long line, line-by-line diffs can be hard to read. You can use word diff:

~~~bash
git diff --word-diff
~~~

Or highlight changed words with color:

~~~bash
git diff --color-words
~~~

Limit the number of context lines:

~~~bash
git diff -U1
~~~

By default, Git displays several lines of context before and after each hunk. The `-U1` option reduces this to one line; `-U0` shows only the changed lines, which is convenient for quick scans but can strip away helpful context.

Word diffs are useful for Markdown, JSON, or long configuration lines. For source code, always read enough context to understand whether a change affects surrounding logic.

## Checking Whitespace and Line Formatting

Diffs can help catch accidental whitespace errors:

~~~bash
git diff --check
~~~

This command checks unstaged changes for common whitespace errors such as trailing whitespace or spaces before tabs in certain contexts. It does not replace a project's formatter or linter.

Check staged changes:

~~~bash
git diff --cached --check
~~~

If you need to inspect whitespace differences:

~~~bash
git diff --ignore-space-change
git diff --ignore-all-space
git diff --ignore-space-at-eol
~~~

These options only change how Git evaluates and displays whitespace differences in the diff. They do not modify files. Use them carefully because they can hide meaningful changes in whitespace-sensitive files such as Makefiles, YAML, or indentation-sensitive formats.

## When Files Are Deleted, Mode-Changed, or Moved

### Deleted Files

If you delete a tracked file from the working tree without staging the deletion, `git diff` displays the removed lines:

~~~bash
git diff -- src/LegacyPayment.java
~~~

After staging the deletion:

~~~bash
git add -u
git diff --cached --stat
~~~

At this point, the change moves to the staged area and no longer appears in the default `git diff`.

### File Executable Bit or Mode Changes

Git tracks certain file modes. If the executable permission changes and the filesystem/Git is configured to detect it, the diff may show a mode change even when the file content is unchanged.

Example output:

~~~diff
old mode 100644
new mode 100755
~~~

- `100644`: regular non-executable file.
- `100755`: regular executable file.

Check the mode tracking configuration:

~~~bash
git config --get core.filemode
~~~

On some filesystems, permission changes may not be detected by Git as expected. Do not rely on the mode shown on one operating system to make absolute assumptions about permissions on another operating system.

### Renamed Files

Git stores snapshots and tree entries rather than storing an explicit rename operation in a commit. If you rename a file in the working tree without staging the new path, the old file may appear as deleted and the new file as untracked. Because the new file is not yet tracked, the default `git diff` may only show the deletion of the old file.

Use `git status` to see both paths. After staging the changes:

~~~bash
git add -A
git diff --cached --summary
git diff --cached --find-renames
~~~

Git can infer renames from content similarity when rendering a diff. Rename detection is heuristic; it does not prove that a commit contains a discrete rename operation.

## Binary Files and Content Filters

For binary files such as images, PDFs, or archives, Git generally does not display line-by-line diffs. You may see a message like:

~~~text
Binary files a/assets/logo.png and b/assets/logo.png differ
~~~

The `--text` option forces Git to treat the content as text to attempt generating a diff:

~~~bash
git diff --text -- assets/data.bin
~~~

Do not use `--text` by default for large binary files or non-text data; the output can be unreadable and meaningless.

Git attributes and clean/smudge filters can also affect how content is normalized when entering the index or displaying diffs. For example, a file may have line endings normalized or text conversion applied. When a diff appears different from the raw bytes on disk, inspect:

~~~bash
git check-attr -a -- path/to/file
git config --show-origin --get core.autocrlf
~~~

Do not change line-ending settings just to make a diff look cleaner without first understanding the project's `.gitattributes` conventions.

## Useful git diff Options

| Command | Purpose |
|---|---|
| `git diff` | Working tree vs. index |
| `git diff --cached` | Index vs. HEAD |
| `git diff --staged` | Alias for `--cached` |
| `git diff HEAD` | Working tree vs. HEAD, including staged and unstaged |
| `git diff -- path` | Inspect only a specific path |
| `git diff --stat` | Summary of changed files and line counts |
| `git diff --name-only` | Print only filenames |
| `git diff --name-status` | Print filenames and change statuses |
| `git diff --check` | Check for whitespace errors in the diff |
| `git diff -U0` | Show zero context lines |
| `git diff --word-diff` | Show word-by-word differences |
| `git diff --ignore-space-change` | Ignore changes in the amount of whitespace when comparing |
| `git diff --no-ext-diff` | Disable external diff drivers |
| `git diff --binary` | Generate diffs applicable to binary changes when creating patches |

Options can be combined, for example:

~~~bash
git diff --stat -- src/
git diff --cached --name-status
git diff -U0 -- README.md
git diff --check
~~~

### Exit Codes of git diff

In scripts, you may need to check whether a diff contains any changes:

~~~bash
git diff --quiet
~~~

Typically:

- Exit code `0`: no differences.
- Exit code `1`: differences exist.
- Exit code greater than `1`: an error occurred while running the command.

The `--exit-code` option also causes the command to return a non-zero exit code when differences exist. This is useful in automation, but be careful to distinguish "changes exist" from "the command failed".

Example in a POSIX shell:

~~~bash
if git diff --quiet; then
  echo "No unstaged changes"
else
  result=$?
  if [ "$result" -eq 1 ]; then
    echo "Unstaged changes exist"
  else
    echo "git diff failed"
    exit "$result"
  fi
fi
~~~

If using PowerShell, check `$LASTEXITCODE` immediately after running Git; `$?` reflects the status of the most recent PowerShell statement and does not reliably replace the exit code of native executables in all scenarios.

## Pre-Commit Review Workflow

A practical daily workflow:

~~~bash
# 1. Inspect the status of all files
git status --short

# 2. Review unstaged changes
git diff

# 3. Select the content to include in the commit
git add src/PaymentService.java

# 4. Verify the exact staged content
git diff --cached

# 5. Check remaining unstaged changes
git diff

# 6. Check whitespace in the staged changes
git diff --cached --check

# 7. View summary statistics of the planned commit
git diff --cached --stat
~~~

Before committing, make sure that:

- The content in `git diff --cached` matches the intended goal of the commit.
- Changes you do not want to commit yet remain in `git diff`.
- No sensitive files or unwanted artifacts have been staged.
- Untracked files have been reviewed; Git does not include them automatically.
- Deleted files or mode changes are intentional.

After committing, `git diff --cached` is normally empty because the index now matches the new HEAD. `git diff` is also empty if the working tree has no further edits.

## Practice: Observing the Index and Working Tree Simultaneously

The following exercise creates a small repository so you can verify these comparisons yourself.

### Step 1: Create a Test Repository

~~~bash
mkdir diff-working-index-lab
cd diff-working-index-lab
git init
git config user.name "Git Learner"
git config user.email "learner@example.test"
~~~

Create `README.md` with the following content:

~~~text
Payment service
Status: draft
Owner: Platform
~~~

Then commit it:

~~~bash
git add README.md
git commit -m "docs: add initial payment readme"
~~~

### Step 2: Edit the File Without Staging

Change `Status: draft` to `Status: in review`.

Run:

~~~bash
git status --short
git diff
git diff --cached
git diff HEAD
~~~

Expected output:

- `git diff` shows the changed Status line.
- `git diff --cached` is empty.
- `git diff HEAD` shows the change.
- `git status` reports the file as modified and unstaged.

### Step 3: Stage and Then Edit Further

Stage the current changes:

~~~bash
git add README.md
~~~

Then change the Owner line from `Platform` to `Developer Experience` without staging again.

Run:

~~~bash
git diff
git diff --cached
git diff HEAD
~~~

Expected output:

- `git diff` shows only the new Owner change.
- `git diff --cached` shows the staged Status change.
- `git diff HEAD` shows both the Status and Owner changes.

This scenario demonstrates that the index stores its own snapshot taken at the time of staging.

### Step 4: Stage the Remaining Changes and Review

~~~bash
git add README.md
git diff
git diff --cached
git diff --cached --check
git diff --cached --stat
~~~

Expected output: `git diff` is empty and all changes appear in `git diff --cached`.

### Step 5: Create a New File and Observe Untracked Behavior

Create `notes.txt` without staging it:

~~~bash
git status --short
git diff
~~~

`notes.txt` appears in `git status` as untracked, but its content does not appear in the default `git diff`.

Stage the file:

~~~bash
git add notes.txt
git diff --cached -- notes.txt
~~~

Now the new file's content is displayed as part of what will be added to the commit.

### Step 6: Unstage While Keeping the File Content

~~~bash
git restore --staged -- notes.txt
git status --short
~~~

The file returns to untracked status while its content remains in the working tree. Unstaging does not mean deleting the file.

If you want to move the file back to staged status, run `git add notes.txt`.

## Distinguishing Restore Commands Related to Diffs

The following commands have different effects:

~~~bash
# Unstage while keeping content in the working tree
git restore --staged -- README.md

# Restore the working tree to match the content in the index
git restore --worktree -- README.md

# Restore both the index and the working tree to match HEAD
git restore --source=HEAD --staged --worktree -- README.md
~~~

Notes:

- `git restore --staged` resets the index to the default source state (usually HEAD), while the file in the working tree keeps its current content.
- `git restore --worktree` overwrites unstaged changes with the content in the index.
- The last command can discard both staged and unstaged changes for the specified file.

Before running any restore command that can overwrite data, inspect the diff and back up anything you need to keep. Do not run `git restore` just to make `git diff` empty before determining which content needs to be preserved.

## Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| `git diff` compares the working tree with the HEAD commit | By default, it compares the working tree with the index |
| Staging a file modifies the current commit | Staging only updates the index; no commit is created yet |
| `git diff` shows all new files | Untracked files do not appear by default |
| An empty `git diff` means the repository is clean | There may still be staged or untracked files |
| `git diff --cached` is the working tree diff | It compares the index with HEAD |
| Editing a file after staging automatically updates the index | Subsequent edits remain unstaged until staged again |
| A `+` line means it is already staged | It only indicates a line present on the new side of the comparison |
| Git stores an explicit rename operation | Git stores snapshots and infers renames when rendering diffs |
| Unstaging deletes changes | `git restore --staged` keeps the working tree content |
| Ignoring whitespace is always safe | It can hide meaningful changes in certain file formats |

## Diff Review Checklist

- [ ] Ran `git status --short` to distinguish modified, staged, and untracked files.
- [ ] Inspected `git diff` to check unstaged changes.
- [ ] Inspected `git diff --cached` to check the content that will be committed.
- [ ] Used `git diff HEAD` when needing to inspect total changes in tracked files.
- [ ] Checked new files and understood that untracked files do not appear in the default diff.
- [ ] Reviewed individual hunks when staging only part of a file.
- [ ] Checked whitespace and file modes if unexpected changes appeared.
- [ ] Confirmed no sensitive files or unintended artifacts are in the index.
- [ ] Backed up or clearly identified data before running restore commands that can overwrite files.
- [ ] Confirmed the index contains the exact desired snapshot before committing.

## Key Takeaways

By default, `git diff` compares the working tree with the index, so it displays changes in tracked files that have not yet been staged. `git diff --cached` compares the index with HEAD to show the content selected for the next commit. `git diff HEAD` compares the working tree with the current commit and reveals the combined staged and unstaged changes for tracked paths. Untracked files do not appear in the default diff; use `git status` to identify them and stage them when needed. Before every commit, inspect both `git diff` and `git diff --cached` to know what remains in the working tree and what actually resides in the index.

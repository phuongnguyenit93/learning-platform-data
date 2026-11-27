# Reading Patches: File Paths, Hunks, and Added or Removed Lines

When viewing changes in Git, you frequently encounter a patch in **unified diff** format. A patch describes which files changed, where the changes occurred, and which lines were kept, added, or removed. Being able to read this structure helps you review code, inspect content before committing, understand merge results, and pinpoint the exact changes without re-reading an entire file.

In Git source control, a patch is a representation of the differences between two states of a repository. A patch does not necessarily contain the entire file; it usually contains only the regions around changed lines, along with a few context lines so the reader can locate them.

## 1. What Sections Make Up a Unified Diff Patch?

A typical diff may include:

1. **File header:** indicates the file path on the old side and the new side.
2. **Metadata:** OIDs, file modes, create/delete/rename status, or additional details.
3. **Hunk header:** indicates which line ranges of the old and new versions are being shown.
4. **Hunk body:** context lines, removed lines, and added lines.

Abbreviated example:

~~~diff
diff --git a/src/greeting.js b/src/greeting.js
index 12ab34c..56de78f 100644
--- a/src/greeting.js
+++ b/src/greeting.js
@@ -10,4 +10,5 @@ function greet(name) {
   const normalized = name.trim();
-  return "Hello " + normalized;
+  const message = "Hello " + normalized;
+  return message;
 }
 
~~~

Reading from top to bottom:

- The file being compared is src/greeting.js.
- The index line shows the abbreviated OIDs of the old and new contents; 100644 is the file mode.
- --- is the old side, +++ is the new side.
- The hunk starts around line 10 in both versions.
- Lines starting with a space are context; - indicates a removed line; + indicates an added line.

## 2. Reading the File Header and a/, b/ Paths

The first line of each file diff usually looks like:

~~~diff
diff --git a/src/greeting.js b/src/greeting.js
~~~

In Git's unified diff convention:

- a/ is the prefix for the path on the old side.
- b/ is the prefix for the path on the new side.
- The portion after the prefix is the corresponding path in the file tree.

Two identical paths usually indicate the same file had its content modified. If the paths differ, the diff may represent a file rename or move, depending on accompanying metadata.

The next lines are usually:

~~~diff
--- a/src/greeting.js
+++ b/src/greeting.js
~~~

--- and +++ identify the filenames on both sides in patch format. When adding a new file, the old side is usually /dev/null; when deleting a file, the new side is usually /dev/null:

~~~diff
diff --git a/docs/new-guide.md b/docs/new-guide.md
new file mode 100644
--- /dev/null
+++ b/docs/new-guide.md
@@ -0,0 +1,2 @@
+# New guide
+Installation steps
~~~

Example of deleting a file:

~~~diff
diff --git a/docs/old-guide.md b/docs/old-guide.md
deleted file mode 100644
--- a/docs/old-guide.md
+++ /dev/null
@@ -1,2 +0,0 @@
-# Old guide
-Deprecated instructions
~~~

The a/ and b/ prefixes are naming conventions within the diff output; they do not mean your repository contains real directories named a and b.

## 3. Metadata in a Diff

Before the content, Git may display metadata describing the objects and file state:

~~~diff
index 12ab34c..56de78f 100644
~~~

- 12ab34c is the abbreviated OID of the old blob.
- 56de78f is the abbreviated OID of the new blob.
- 100644 is the mode of a regular non-executable file on Unix-like systems.

Common file modes:

| Mode | Meaning |
|---|---|
| 100644 | Regular file, non-executable |
| 100755 | Regular file, executable |
| 120000 | Symbolic link |
| 160000 | Gitlink, typically used for submodules |

When executable permissions change, Git may display:

~~~diff
old mode 100644
new mode 100755
~~~

When creating or deleting a file, metadata may include new file mode or deleted file mode. These changes matter because diffs do not only describe text content; they can also record metadata changes managed by Git.

## 4. Reading the Hunk Header @@

A hunk header in a unified diff has the form:

~~~text
@@ -<old-start>,<old-count> +<new-start>,<new-count> @@ <context>
~~~

Example:

~~~diff
@@ -10,4 +10,5 @@ function greet(name) {
~~~

Meaning:

- -10,4: the displayed region starts at line 10 of the old version and spans 4 lines.
- +10,5: the corresponding region starts at line 10 of the new version and spans 5 lines.
- function greet(name) {: optional context text helping identify the function or section being modified.

The line numbers on the - side always refer to the old version; the line numbers on the + side refer to the new version. The two line counts may differ because a hunk can add or remove lines.

### When the Line Count Is Omitted

If a region consists of only a single line, the diff format may omit ,count:

~~~diff
@@ -8 +8 @@
~~~

This is equivalent to one line in the old version and one line in the new version. If the count is 0, Git writes ,0 explicitly, for example:

~~~diff
@@ -0,0 +1,2 @@
~~~

This represents adding two lines at the beginning of a file: the old side has zero lines in that region, while the new side has two lines starting at line 1.

### Hunk Context Is Not a Changed Line

The text after the second @@ is typically context chosen by Git, such as a function name or enclosing structure near the change. It is not a new line in the patch body and does not add to the line count tracked in the hunk header.

## 5. Distinguishing Context, Added, and Removed Lines

In the hunk body, the first character of each line tells you how to read it:

| Leading Character | Meaning | Present in Old Version? | Present in New Version? |
|---|---|---:|---:|
| Space | Context line, unchanged | Yes | Yes |
| - | Removed line | Yes | No |
| + | Added line | No | Yes |

Example:

~~~diff
@@ -20,3 +20,4 @@
 const enabled = true;
-const timeout = 1000;
+const timeout = 2500;
+const retries = 3;
 startService();
~~~

Interpretation:

- const enabled = true; and startService(); are context lines.
- const timeout = 1000; existed in the old version and was removed from the new version.
- const timeout = 2500; was added in the new version to replace the old value.
- const retries = 3; is a newly added line.

An adjacent pair of - and + lines usually represents a modified line. However, Git only expresses textual differences; whether the two lines have equivalent meaning still requires a reviewer who understands the source code.

## 6. Counting the Lines of a Hunk Yourself

The hunk header states the line counts for both sides. You can verify this by counting markers in the hunk body:

- Lines starting with a space count toward both old and new.
- Lines starting with - count only toward old.
- Lines starting with + count only toward new.
- Metadata lines such as \ No newline at end of file do not count as content lines in the hunk.

In the previous example:

~~~diff
@@ -20,3 +20,4 @@
 const enabled = true;
-const timeout = 1000;
+const timeout = 2500;
+const retries = 3;
 startService();
~~~

The old side has 3 lines: two context lines and one removed line. The new side has 4 lines: two context lines and two added lines. Therefore, the header -20,3 +20,4 matches the hunk body.

When reviewing a real patch, if the line count you tally does not match the hunk header, check whether you missed a context line, an added/removed line, or an end-of-file marker.

## 7. A File Can Have Multiple Hunks

Git normally groups nearby changes into a single hunk. If two edited regions are far apart, the diff may display multiple separate hunks:

~~~diff
diff --git a/src/config.js b/src/config.js
--- a/src/config.js
+++ b/src/config.js
@@ -4,3 +4,3 @@
-const host = "localhost";
+const host = "127.0.0.1";
 const port = 8080;
 const secure = false;
@@ -40,3 +40,4 @@
 function connect() {
+  validateConfig();
   return openConnection();
 }
~~~

Each hunk has its own starting line and line-count pair. The second hunk does not continue counting from the first hunk; it points to a different region in the same file.

By default, Git includes several context lines around changes so readers can see where they sit. You can increase or decrease the number of context lines with the -U option:

~~~bash
# Show no context lines
git diff -U0

# Show 5 context lines around each change
git diff -U5
~~~

Less context makes patches shorter but harder to orient yourself in. More context makes reviews easier at the cost of longer output.

## 8. End-of-File Marker: No newline at end of file

A special line can appear after a hunk:

~~~text
\ No newline at end of file
~~~

This notice indicates that the corresponding version does not end with a newline character. This line is not actual file content and is not counted in the hunk line totals. Text files should generally end with a trailing newline so Unix tools, diffs, and text processors behave consistently.

If both the old and new versions lack a trailing newline, the marker may appear for both sides. If only one side lacks a newline, the marker appears next to the line belonging to that side.

## 9. Reading Additions, Deletions, Renames, and Mode Changes

### New Files

New files usually include new file mode, /dev/null as the old side, and a hunk starting at old position -0,0.

### Deleted Files

Deleted files usually include deleted file mode, /dev/null as the new side, and a hunk containing only - lines.

### Renames or Moves

Git can detect renames based on similarity between old and new contents. Example:

~~~diff
diff --git a/src/old-name.js b/src/new-name.js
similarity index 92%
rename from src/old-name.js
rename to src/new-name.js
~~~

similarity index is the level of similarity Git estimates between the two versions. If a file is renamed without modifying its content, similarity can be 100%. If a file is both renamed and edited, the content patch may appear after the rename metadata.

Git does not store a separate object type for rename operations. Renames are inferred when comparing two file trees based on content and detection thresholds.

### Executable Permission Changes

~~~diff
old mode 100644
new mode 100755
~~~

This is a file mode change, not necessarily a content change. On certain filesystems or configurations, Git may not detect all permission differences; the core.fileMode setting affects mode checking in the working tree.

## 10. Diffs of Binary Files and Submodules

Binary files such as images, PDFs, archives, or executables cannot be safely displayed as ordinary text lines. Git may show:

~~~text
Binary files a/assets/logo.png and b/assets/logo.png differ
~~~

To generate a binary patch, you can use --binary:

~~~bash
git diff --binary > changes.patch
~~~

This patch can contain encoded binary data to apply changes. Do not read that data as source text; use appropriate tools to compare or preview the file.

For submodules, a diff in the parent repository usually describes the gitlink changing from one commit OID to another. You can request the commit log to be shown:

~~~bash
git diff --submodule=log
~~~

This helps reviewers see which commit the submodule moved from and to. The contents of files inside the child repository still belong to the submodule's own history.

## 11. Reading Diffs in Different Git Contexts

The same patch format can be generated when comparing different pairs of states. Always be clear about which two sides are being compared:

| Command | Compares | Question Answered |
|---|---|---|
| git diff | Working tree vs. index | What did I edit without staging? |
| git diff --cached | Index vs. HEAD | What will go into the next commit? |
| git diff HEAD | Working tree and index vs. current commit | What are all uncommitted changes? |
| git diff <commit-A> <commit-B> | Two commits | How do two historical states differ? |
| git show <commit> | Commit vs. parent, plus metadata | What did this commit change? |
| git diff <branch-A>...<branch-B> | Merge base of A vs. B | What has branch B changed since diverging from A? |

Example of reviewing changes prepared for commit:

~~~bash
git status --short
git diff
git diff --cached
git diff --check
git diff --cached --check
~~~

Do not look at a single git diff command and assume the commit will contain that content. When both staged and unstaged changes exist at the same time, inspect both areas.

## 12. Useful Options When Reading Patches

Several options make diff output easier to read:

| Option | Purpose |
|---|---|
| --stat | Summarize changed files and added/removed line counts |
| --numstat | Output added/removed line counts in a script-friendly format |
| --name-only | List only changed filenames |
| --name-status | List filenames along with A/M/D/R/C status |
| --summary | Display metadata such as file creation/deletion, mode, rename |
| -U<n> | Adjust the number of context lines |
| --word-diff | Compare word by word instead of only line by line |
| --color-words | Highlight word-level changes in color |
| --ignore-space-change | Ignore certain differences in whitespace quantity |
| --ignore-all-space | Ignore whitespace differences when comparing |
| --find-renames | Enable rename detection |
| --no-prefix | Omit the a/ and b/ prefixes |
| --src-prefix, --dst-prefix | Customize path prefixes in output |

Examples:

~~~bash
git diff --stat
git diff --name-status
git diff --summary
git diff --word-diff
git diff -U8
~~~

Options that ignore whitespace can help when reviewing large formatting changes, but they can also hide meaningful differences in code or configuration files. Re-check the full diff before accepting a patch.

## 13. Combined Diff When Viewing Merge Commits

Merge commits have multiple parents. When viewing the diff of a merge commit, Git may use a combined diff with @@@ headers instead of @@:

~~~text
diff --cc src/config.js
index <parent-1-oid>,<parent-2-oid>..<result-oid>
--- a/src/config.js
+++ b/src/config.js
@@@ -10,3 -10,3 +10,4 @@@
~~~

A combined diff uses multiple columns to represent content relative to multiple parents. It is more complex to read than a standard two-way unified diff. If you want to compare the merge result against each parent individually, run:

~~~bash
git diff HEAD^1 HEAD
git diff HEAD^2 HEAD
~~~

These two commands produce familiar two-way diffs, helping you review the merge result relative to each parent branch.

## 14. Step-by-Step Process for Reading a Patch During Review

When receiving a patch from a teammate or reading git diff output, read in this order:

1. **Determine the scope:** inspect file headers and the file list to see which areas are affected.
2. **Check metadata:** look for new/deleted files, renames, mode changes, symlinks, submodules, or binary files.
3. **Read hunk headers:** identify old and new line ranges; note when multiple hunks appear in the same file.
4. **Read added/removed lines:** compare old and new logic; context lines help orient the surrounding code.
5. **Check whitespace and newlines:** watch for end-of-file markers and formatting changes.
6. **Verify the compared states:** confirm whether the patch compares the working tree, the index, or two commits.
7. **Inspect broader context:** if logic changed, read callers, tests, and related configuration.

A short patch can still cause major behavioral changes. Added/removed line counts are merely text metrics, not a measure of risk or quality.

## 15. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| A + line is from the old version | No. + is a line present in the new version; - is a line from the old version. |
| A line starting with a space is a change | No. A leading space marks a context line present on both sides. |
| @@ -10,4 +10,5 @@ means the change starts at line 10 and adds 5 lines | It describes a 4-line old region and a 5-line new region; it does not mean all 5 lines were added. |
| a/ and b/ are real directories in the project | No. They are path prefixes used by Git's diff convention. |
| The hunk header points to the first changed line | It indicates the start of the hunk region; the hunk also contains context lines. |
| A rename is a separate object type in Git | No. Git infers renames when comparing file trees. |
| Every diff is human-readable text | No. Binary diffs may only report that files differ or contain encoded data when using --binary. |
| git diff always shows what will be committed | No. git diff compares the working tree with the index; use git diff --cached to inspect staged content. |
| A merge commit's combined diff is identical to a two-way hunk | No. Combined diffs can use @@@ and represent multiple parents. |

## 16. Self-Check

1. **In a unified diff, what do + and - represent?**
   - + is a line added in the new version; - is a line removed from the old version.
2. **What does a line starting with a single space inside a hunk mean?**
   - It is a context line, present in both the old and new versions.
3. **What does @@ -12,4 +12,6 @@ indicate?**
   - The hunk starts at line 12 on the old side spanning 4 lines and line 12 on the new side spanning 6 lines.
4. **Why can a hunk have different old and new line counts?**
   - Because lines were added or removed within that region.
5. **When does /dev/null appear in a file header?**
   - When the old side has no file (new file) or the new side has no file (deleted file).
6. **Which command views staged changes?**
   - git diff --cached or git diff --staged.
7. **How does Git detect renames?**
   - By comparing contents and estimating similarity between old and new paths.
8. **Is the \ No newline at end of file marker counted in the hunk line totals?**
   - No. It is metadata indicating that the file lacks a trailing newline.

## Conclusion

A unified diff shows the paths on both sides, file metadata, the line ranges compared, and the added, removed, and context lines. Read the file header first, then read the @@ hunk header to identify old and new line counts, and distinguish space, -, and + markers in the body. Check rename/mode metadata, binary notices, and the exact states being compared to understand the patch's true scope. During review, combine git diff, git diff --cached, git diff --stat, and appropriate context options to verify the exact content that will be committed.

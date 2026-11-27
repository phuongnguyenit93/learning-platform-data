# Viewing Change Statistics with --stat, --name-only, and --name-status

When reviewing a change, sometimes you do not need to read every diff line right away. First, you want to know how many files were affected, which directory the changes are concentrated in, which files were added or deleted, and whether any files were renamed. Git provides statistics options to answer those questions quickly.

The three commonly used options are <code>--stat</code>, <code>--name-only</code>, and <code>--name-status</code>. <code>--stat</code> shows the scale of changes per file with added/removed line counts and a bar chart; <code>--name-only</code> lists only file paths; <code>--name-status</code> lists paths alongside statuses such as added, modified, deleted, or renamed. They can be combined with different comparison scopes, from the working tree and staging area to two commits or two branches.

This lesson belongs to the **Diffing Changes** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; it also builds skills in branch collaboration, conflict resolution, tracking down changes, and recovering from mistakes while preserving important history. Knowing how to read statistics helps you evaluate the scope of changes before inspecting detailed diffs, committing, or integrating branches.

## 1. Why View Change Statistics?

A diff can contain thousands of lines. Before reading the details, determine the scope:

- How many files changed?
- Which files were added, modified, deleted, or renamed?
- Which directory or component are the changes concentrated in?
- Did any file have an unusually large number of changes?
- Did a commit touch only documentation or also affect source code?
- Which paths differ between two branches?

Statistics do not replace reviewing the content. They serve as an orientation step so you know which files to open and what to watch for.

## 2. Understanding the Three Core Options

| Option | Displayed Content | Best Used When |
|---|---|---|
| <code>--stat</code> | Each file, added/removed line counts, and a bar chart; followed by total files/lines | Quickly assessing the scale of changes |
| <code>--name-only</code> | Only the paths of changed files | Extracting a file list to inspect or pass to another tool |
| <code>--name-status</code> | Change status and file path | Knowing whether files were added, modified, deleted, renamed, or copied |

Example:

~~~bash
git diff --stat
git diff --name-only
git diff --name-status
~~~

These three commands use the default comparison scope of <code>git diff</code>: changes in the working tree compared to the index. Therefore, the output does not necessarily include staged content.

## 3. Choosing the Right Comparison Scope Before Viewing Statistics

Statistics options only change how the output is formatted. What matters most is which two states you are comparing.

### Working Tree vs. Index

~~~bash
git diff --stat
git diff --name-only
git diff --name-status
~~~

These are unstaged changes. If you just edited files without running <code>git add</code>, they appear here.

### Index vs. Current Commit

~~~bash
git diff --cached --stat
git diff --cached --name-only
git diff --cached --name-status
~~~

<code>--cached</code> is an alias for <code>--staged</code>. These commands show staged content compared to <code>HEAD</code>, meaning what will go into the next commit if you commit now.

### All Uncommitted Changes

To inspect the working tree relative to <code>HEAD</code>, including both staged and unstaged changes:

~~~bash
git diff HEAD --stat
git diff HEAD --name-only
git diff HEAD --name-status
~~~

This is often a helpful way to inspect the total scope of changes before committing. In a new repository without an initial commit, <code>HEAD</code> does not yet exist; in that case, check the index and working tree states separately.

### Untracked Files Do Not Appear in Normal Diffs

<code>git diff</code> commands do not automatically include untracked files in their output because those files are not yet in the index. Check them with:

~~~bash
git status --short
~~~

Untracked files usually show status <code>??</code>. If you need to view a new file's changes in diffs before staging all of its content, you can mark it intent-to-add:

~~~bash
git add -N path/to/new-file.txt
git diff --stat
git diff --name-status
~~~

<code>git add -N</code> creates an intent-to-add entry in the index so Git can include the new file in diffs; it does not stage the file's full content like normal <code>git add</code>. After inspecting, you can stage the file completely or remove the entry as needed. Ignored files also do not appear automatically; use <code>git status --ignored</code> to check if you suspect an ignore rule is hiding a file.

### Comparing Two Commits

~~~bash
git diff --stat <commit-a> <commit-b>
git diff --name-only <commit-a> <commit-b>
git diff --name-status <commit-a> <commit-b>
~~~

Git displays the paths that differ between the snapshots of the two commits. The order of the two endpoints matters for the add/delete direction in <code>--name-status</code>: a file present in the second commit but absent in the first is treated as added.

### Comparing the Current Commit with Its Parent

~~~bash
git diff --stat HEAD^ HEAD
git diff --name-status HEAD^ HEAD
~~~

For a normal commit, these are the changes introduced by the latest commit. A merge commit has multiple parents; <code>HEAD^</code> defaults to the first parent. If you need to compare against another parent, specify it explicitly, such as <code>HEAD^2</code>.

### Comparing Two Branches

Compare the snapshots at the tips of two branches:

~~~bash
git diff --stat main feature/payment
git diff --name-status main feature/payment
~~~

If you want to view changes on the feature branch since the point where the two branches diverged, use the three-dot syntax:

~~~bash
git diff --stat main...feature/payment
git diff --name-status main...feature/payment
~~~

With <code>git diff</code>, <code>main...feature/payment</code> is equivalent to comparing the merge base of the two branches with the tip of <code>feature/payment</code>. It is useful when reviewing what the feature branch brings relative to the base branch. This syntax does not have the same meaning across all Git commands; notably, three-dot usage in <code>git log</code> is interpreted differently.

## 4. Reading --stat Output

Example:

~~~text
 src/payment/RetryPolicy.java | 24 ++++++++++++++++++------
 src/payment/RetryPolicyTest.java | 18 ++++++++++++++++++
 README.md | 4 ++--
 3 files changed, 38 insertions(+), 8 deletions(-)
~~~

Meaning:

- The first column is the file path.
- The number after <code>|</code> is the total number of changed lines reported for that file.
- The <code>+</code> symbols represent added lines.
- The <code>-</code> symbols represent removed lines.
- The bar chart helps compare relative change size across files.
- The final line summarizes the number of changed files, insertions, and deletions.

In the example, three files changed, with a total of 38 insertions and 8 deletions. This does not mean the application gained exactly 30 lines of meaningful source code: diffs count lines according to how Git compares content, and formatting changes or replaced lines are also counted.

For binary files, Git does not count lines like text files. <code>--stat</code> may show something like <code>Bin old-size -> new-size bytes</code>; read it as a size change of the compared object/file, not as added or removed lines.

### Reading the Bar Chart Correctly

The bar chart is a relative visual aid for spotting which files have larger changes. Bar length depends on width settings and display limits. Do not use bar length to deduce exact line counts; read the numbers preceding the bars.

A file with many changed lines is not necessarily the most complex. For example, a generated file or dependency lockfile might change thousands of lines yet require less logic review than a small change in authorization handling.

### Customizing Statistics Width

<code>--stat</code> lets you adjust the overall width, filename column width, and maximum number of files:

~~~bash
# Limit overall width
git diff --stat=100

# Overall width, filename column width, number of files displayed
git diff --stat=100,60,20
~~~

If filenames are truncated or the output is too wide in your terminal, adjust these values. Omit the limits if you need complete output to read or save in a report.

## 5. Listing Only Files with --name-only

Example:

~~~bash
git diff --name-only HEAD
~~~

Output might be:

~~~text
README.md
src/payment/RetryPolicy.java
src/payment/RetryPolicyTest.java
~~~

This option is useful when you only want to know the file scope without needing insertion/deletion counts or change types.

Common scenarios:

- Building a list of files for manual review.
- Identifying which files changed between two releases.
- Verifying whether a commit only touched a documentation directory or affected source code.
- Combining with other commands to filter or group paths.

Example of listing only the files changed in the latest commit:

~~~bash
git diff-tree --no-commit-id --name-only -r HEAD
~~~

Or using <code>git show</code>:

~~~bash
git show --format= --name-only HEAD
~~~

With history commands, choose the right commit or commit range. <code>git diff --name-only HEAD</code> does not list the files of only the latest commit; when given a single endpoint, Git compares the working tree against that commit.

## 6. Knowing the Change Type with --name-status

<code>--name-status</code> prepends a status code before each path:

~~~bash
git diff --name-status HEAD^ HEAD
~~~

Example:

~~~text
M	README.md
A	src/payment/RetryPolicy.java
D	src/legacy/OldRetry.java
R087	src/payment/RetryHandler.java	src/payment/RetryPolicy.java
~~~

Common codes:

| Code | Meaning |
|---|---|
| <code>A</code> | Added — file was added |
| <code>M</code> | Modified — file was modified |
| <code>D</code> | Deleted — file was deleted |
| <code>R</code> | Renamed — file was detected as renamed |
| <code>C</code> | Copied — file was detected as a copy |
| <code>T</code> | Type changed — file type or mode changed |
| <code>U</code> | Unmerged — file is in a conflicted state |
| <code>X</code> | Unknown — Git could not determine status |
| <code>B</code> | Pairing broken — file pairing broken in certain diff outputs |

For renames or copies, Git may include a similarity score from 0 to 100, such as <code>R087</code> meaning a rename detected with 87% similarity. This is a detection result based on content and configured thresholds, not proof that the file was renamed via a specific operation.

### Rename Detection

Git stores file snapshots rather than storing an independent rename operation as a mandatory event. When comparing two snapshots, Git attempts to recognize a deleted file and an added file with sufficiently similar content as a rename.

To adjust this:

~~~bash
# Enable rename detection
git diff --find-renames --name-status HEAD^ HEAD

# Use a 60% similarity threshold
git diff --find-renames=60% --name-status HEAD^ HEAD

# Disable rename detection
git diff --no-renames --name-status HEAD^ HEAD
~~~

If rename detection is disabled, a rename may appear as <code>D</code> for the old path and <code>A</code> for the new path. When inspecting refactoring history or moved files, consider enabling rename detection.

### Copy Detection

Copy detection can be requested with:

~~~bash
git diff --find-copies --name-status <commit-a> <commit-b>
~~~

Git needs to identify potential copy sources. The <code>--find-copies-harder</code> option instructs Git to consider unmodified files as copy sources as well, though this can significantly increase computation cost in large repositories:

~~~bash
git diff --find-copies-harder --name-status <commit-a> <commit-b>
~~~

Enable this mode only when thorough copy detection is needed and increased processing time is acceptable.

## 7. Combining Statistics with git show and git log

### Viewing Statistics for One Commit

~~~bash
git show --stat <commit>
~~~

To list only filenames:

~~~bash
git show --format= --name-only <commit>
~~~

To view file statuses:

~~~bash
git show --format= --name-status <commit>
~~~

By default, <code>git show</code> displays commit details and the diff. The options above change how the diff section is presented.

### Viewing Statistics Across Multiple Commits

~~~bash
git log --stat -5
~~~

This command displays the five most recent commits along with change statistics for each commit.

Variants:

~~~bash
git log --name-only -5
git log --name-status -5
~~~

You can combine these with limits by branch, author, time, or path:

~~~bash
git log --stat --since="2 weeks ago" main
git log --name-status --author="Linh" -10
git log --name-only -- src/payment/
~~~

Note that <code>git log --name-only -- src/payment/</code> filters history by the specified path. It does not mean showing only files in that directory for unrelated commits.

## 8. Additional Statistics Formats

Beyond the three main options, Git has other formats useful for reading or automation.

### --shortstat

Displays only the final summary line without listing individual files:

~~~bash
git diff --shortstat
~~~

Example:

~~~text
 3 files changed, 38 insertions(+), 8 deletions(-)
~~~

Use this when you only need aggregate totals for reports or quick checks.

### --numstat

Displays added lines, removed lines, and paths in a format convenient for script processing:

~~~bash
git diff --numstat
~~~

Example:

~~~text
18	6	src/payment/RetryPolicy.java
18	0	src/payment/RetryPolicyTest.java
2	2	README.md
~~~

For binary files, the two numeric columns are typically <code>-</code> because Git does not count line insertions/deletions as it does for text files.

### --compact-summary

Displays compact statistics alongside metadata such as modes, file creation, or file deletion:

~~~bash
git diff --compact-summary
~~~

This option is useful when you want a more compact report than <code>--stat</code> while still seeing file type or mode changes.

### --summary

Displays a high-level summary of changes such as file creations, deletions, mode changes, or detected renames and copies:

~~~bash
git diff --summary
~~~

### --dirstat

Summarizes the distribution of changes by directory:

~~~bash
git diff --dirstat
~~~

Variants:

~~~bash
# Calculate by content changes
git diff --dirstat=changes

# Calculate by number of files
git diff --dirstat=files

# Include cumulative percentages in parent directories
git diff --dirstat=cumulative
~~~

<code>--dirstat</code> is helpful when you want to see which components of the repository hold most of the changes. It is a metric based on the chosen calculation mode, not a measure of risk or business criticality.

## 9. Using Statistics to Review a Branch

Suppose you are about to review the <code>feature/payment-retry</code> branch before merging it into <code>main</code>.

First, update remote information:

~~~bash
git fetch origin
~~~

Check the file count and scale of changes since the branch point:

~~~bash
git diff --stat origin/main...feature/payment-retry
~~~

See which files were touched:

~~~bash
git diff --name-only origin/main...feature/payment-retry
~~~

Check the change types:

~~~bash
git diff --name-status origin/main...feature/payment-retry
~~~

Then open the detailed diff:

~~~bash
git diff origin/main...feature/payment-retry
~~~

This workflow takes you from overall scope down to individual changed lines. If statistics reveal production config files, database migrations, or large dependency updates, prioritize reviewing those files.

## 10. Filtering Statistics by Path

You can restrict statistics to a single file or directory:

~~~bash
git diff --stat HEAD^ HEAD -- src/payment/
git diff --name-status main...feature/payment -- src/payment/
~~~

The <code>--</code> separator distinguishes options/commit ranges from pathspecs. It tells Git to treat everything after it as paths, even if a path name might otherwise be mistaken for a revision.

Example viewing only one file:

~~~bash
git diff --name-only HEAD^ HEAD -- README.md
~~~

If a pathspec contains special characters or you want to match a path literally, explore pathspec magic signatures such as <code>:(literal)</code> or <code>:(glob)</code>.

## 11. Using Output in Scripts and Other Tools

<code>--name-only</code> and <code>--name-status</code> are easy for humans to read, but file paths can contain spaces, tabs, or even newlines. If a script parses output line by line or splits on tabs, it may mishandle special filenames.

For scripts, prefer the <code>-z</code> option to use NUL as the delimiter:

~~~bash
git diff --name-only -z <commit-a> <commit-b>
git diff --name-status -z <commit-a> <commit-b>
git diff --numstat -z <commit-a> <commit-b>
~~~

NUL-delimited output must be read with tools that support byte strings/NUL delimiters; do not store it directly in ordinary shell variables since many shells cannot preserve NUL characters.

Bash example for safely processing a list of filenames:

~~~bash
while IFS= read -r -d '' path; do
    printf 'Changed path: %q\n' "$path"
done < <(git diff --name-only -z HEAD^ HEAD)
~~~

With <code>--name-status -z</code>, the parser must handle the number of paths per status type: A/M/D typically have one path; R/C have both a source path and a destination path. Consult the <code>git diff</code> documentation for the NUL format of your Git version rather than assuming every record contains only one path.

### When Line Counts Are Needed for Machine-Readable Reports

~~~bash
git diff --numstat -z origin/main...HEAD
~~~

<code>--numstat</code> provides individual insertion/deletion counts per file. Binary files may output <code>-</code> in the two numeric columns. Do not coerce those values to 0 without retaining the fact that the file is binary.

## 12. Combining with Diff Filters

Git provides the <code>--diff-filter</code> option to display only specific types of changes:

~~~bash
# Only added or modified files
git diff --name-status --diff-filter=AM

# Only deleted files
git diff --name-only --diff-filter=D

# Added, modified, renamed, or copied files
git diff --name-status --diff-filter=AMRC
~~~

The letters correspond to statuses such as A, C, D, M, R, T, U, X, and B. Lowercase letters can be used to exclude the corresponding status in certain combinations; check <code>git help diff</code> for exact syntax.

Diff filters are very useful when looking for newly added files, identifying deleted files, or generating a report of renames only. Combine with <code>--name-status</code> to preserve status information.

## 13. Common Misconceptions

| Misconception | Reality | How to Check Correctly |
|---|---|---|
| <code>git diff --stat</code> shows all uncommitted changes | By default it only compares the working tree with the index | Use <code>git diff HEAD --stat</code> to compare against HEAD |
| <code>--name-only</code> tells whether a file was added or deleted | It only prints paths | Use <code>--name-status</code> |
| <code>--stat</code> accurately indicates risk level | It only summarizes line/file counts | Read the diff and understand the business context |
| Renames are always recorded as status R | Git detects renames when comparing snapshots | Use <code>--find-renames</code> and check thresholds |
| <code>git diff A...B</code> is the same as <code>git log A...B</code> | Three dots are interpreted differently depending on the command | For diff, it compares the merge base of A and B with B |
| Binary files do not appear in statistics | Files can still appear, just without text line counts | Use <code>--stat</code>, <code>--name-status</code>, or <code>--summary</code> |
| Line-oriented output is always safe for scripts | Paths may contain tabs or newlines | Use <code>-z</code> and a NUL-aware parser |
| <code>--name-status</code> returns only one path per line | Renames/copies include both source and destination paths | Handle R/C statuses separately |

## 14. Statistics Check Workflow Before Committing or Merging

Before committing:

~~~bash
# Unstaged changes
git diff --stat
git diff --name-status

# Staged changes
git diff --cached --stat
git diff --cached --name-status

# Exact content that will be committed
git diff --cached
~~~

Before merging a branch:

~~~bash
git fetch origin
git diff --stat origin/main...feature/payment-retry
git diff --name-status origin/main...feature/payment-retry
git diff origin/main...feature/payment-retry
~~~

After receiving a commit:

~~~bash
git show --stat --oneline HEAD
git show --format= --name-status HEAD
~~~

Statistics are the first filtering step. Whenever you notice an unfamiliar file, an unusual jump in line counts, or an unexpected rename, open the detailed diff and verify the reason before accepting the change.

## 15. Self-Check Exercises

Create a test repository with a few commits:

1. Create a new file, edit an existing file, and delete another file.
2. Run <code>git diff --stat</code>, <code>git diff --name-only</code>, and <code>git diff --name-status</code> before staging.
3. Stage part of the changes and re-run the three commands with <code>--cached</code>.
4. Compare <code>git diff HEAD --stat</code> with <code>git diff --stat</code> to see the scope difference.
5. Create a new commit and view its statistics with <code>git show --stat HEAD</code>.
6. Rename a file and compare the results of <code>--find-renames</code> and <code>--no-renames</code>.
7. Create two branches and compare <code>main...feature</code> with <code>main feature</code>.
8. Run <code>--shortstat</code>, <code>--numstat</code>, <code>--summary</code>, and <code>--dirstat</code>; explain which question each format suits best.
9. Create a file with spaces in its name and use <code>-z</code> to extract a script-safe list.
10. Use <code>--diff-filter</code> to list only newly added files or deleted files.

When reading statistics, identify the exact two comparison endpoints first, then choose the appropriate format: <code>--stat</code> to assess scale, <code>--name-only</code> to retrieve a list of paths, and <code>--name-status</code> to see change types. Afterward, open the detailed diff to confirm the actual content and impact.

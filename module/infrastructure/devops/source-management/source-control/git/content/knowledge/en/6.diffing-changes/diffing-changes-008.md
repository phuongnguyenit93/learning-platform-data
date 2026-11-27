# Rename and Copy Detection and the Limits of Similarity Heuristics

Git stores snapshots of the directory tree in every commit. A snapshot records which path points to which object; it does not store a separate operation called "rename" or "copy." When displaying differences between two snapshots, Git can infer that a file deleted at an old path was moved to a new path, or that a file's content was copied to another file. This inference relies primarily on content similarity.

Rename and copy detection make history easier to read when files are moved, renamed, or duplicated. However, it is a heuristic: Git does not know the author's intent. Similarity thresholds, the number of files, and the choice of source candidates all affect the result. Understanding these limits helps you read output accurately, select appropriate options, and avoid confusing Git's diff presentation with the actual data structures stored in a commit.

After this lesson, you will be able to:

- Explain why renames and copies are inferred when displaying diffs.
- Use -M or --find-renames to detect renames.
- Use -C or --find-copies to detect copies.
- Adjust similarity thresholds and understand R/C codes with percentages.
- Use --find-copies-harder when copy sources are unmodified.
- Disable or limit rename/copy detection when needed.
- Read results using --name-status, --summary, and --raw.
- Recognize situations where heuristics miss or mispair files.

## 1. Git Stores Snapshots, Not Rename Operations

Suppose you rename:

~~~text
src/OldParser.java  ->  src/Parser.java
~~~

At the snapshot level, the new directory tree simply records:

- The path src/OldParser.java no longer exists.
- The path src/Parser.java points to the corresponding content object.

If the file content is largely unchanged, when comparing two commits Git can recognize that this delete/add pair is very similar and present it as a rename.

This means:

- The commit tree does not contain a "rename file" operation record.
- Rename detection is a diff-analysis step to make output easier to understand.
- The same pair of commits can be presented differently if rename-detection options or similarity thresholds change.
- A file that is moved and heavily rewritten may be displayed as deleting the old file and adding a new file.

Similarly, a copy is inferred when a new path has content similar to an existing path. Git does not store a "copy from file A to file B" record in a commit.

## 2. Git Detects Renames via Similarity

Rename detection looks for pairs of deleted and added files across the two sides of a diff, then estimates how similar their contents are. If the similarity score meets the threshold, Git can pair them as a rename.

Similarity is expressed as a percentage:

- 100%: identical content.
- 90%: most content is preserved, with a few changes.
- 50%: common default threshold for rename detection.

This score reflects similarity according to Git's algorithm, not a semantic evaluation of the source code. Two files can share high textual similarity without having any historical relationship; conversely, a genuinely renamed file that was almost completely rewritten may fall below the threshold.

### Example: Renaming with git mv

In the working tree:

~~~bash
git mv src/OldParser.java src/Parser.java
git status --short
~~~

git mv moves the file and updates the index. Git can show the rename status in git status thanks to its similarity detection mechanism.

You can also perform the move with filesystem tools and then stage the changes:

~~~bash
mv src/OldParser.java src/Parser.java
git add -A
~~~

The result stored in the index is the same snapshot with the old path removed and the new path added. git mv is a convenience utility that moves and stages in sync; it does not create a special rename object type.

## 3. Using -M or --find-renames

The -M option enables rename detection. Its long form is --find-renames:

~~~bash
git diff -M HEAD~1 HEAD
git diff --find-renames HEAD~1 HEAD
~~~

In many common diff commands, rename detection is enabled by default configuration. Writing -M explicitly clarifies the command's intent and makes it easy to adjust the threshold.

If you want to require at least 80% content similarity:

~~~bash
git diff --find-renames=80% HEAD~1 HEAD
~~~

-M<n> or --find-renames=<n> sets the similarity threshold. For example, --find-renames=90% requires a higher similarity match than --find-renames=50%.

Include the % sign explicitly when specifying a threshold to avoid ambiguity in how numeric values are parsed. Higher thresholds make Git more conservative when pairing files; lower thresholds help detect files that were edited more heavily, at the risk of producing less convincing pairings.

## 4. Reading Rename Results

View filenames and statuses:

~~~bash
git diff --name-status -M HEAD~1 HEAD
~~~

Example:

~~~text
R095    src/OldParser.java    src/Parser.java
~~~

In --name-status output, R095 indicates that Git detected a rename with a 95% similarity score. Depending on the changes, the output may contain only the rename line or include other changes as well.

View summary details:

~~~bash
git diff --summary -M HEAD~1 HEAD
~~~

Example:

~~~text
rename src/OldParser.java => src/Parser.java (95%)
~~~

View the content diff after Git detects the rename:

~~~bash
git diff -M HEAD~1 HEAD -- src/
~~~

When a rename also includes content edits, Git can show the diff from the old file's content to the new file's content. Readers see the changed lines within one logical file instead of seeing one file deleted and a new file added.

## 5. Adjusting the Rename Threshold

The threshold is a trade-off between sensitivity and confidence:

~~~bash
# Lower threshold: can detect files that changed substantially
git diff --find-renames=30% BASE TARGET

# Higher threshold: pairs only very similar files
git diff --find-renames=90% BASE TARGET
~~~

Examples:

- A file renamed with only a single line edited easily passes a high threshold.
- A file renamed while refactoring most of its contents may only satisfy a low threshold.
- Two independent files sharing similar boilerplate can occasionally be mispaired at a low threshold.

There is no single correct threshold for every repository. If rename output looks unreasonable, try a different threshold and inspect the contents on both sides.

## 6. Detecting Copies with -C

Rename detection pairs a deleted file with an added file. Copy detection looks for a still-existing source file and a new file with similar content.

The -C or --find-copies option enables copy detection:

~~~bash
git diff -C BASE TARGET
git diff --find-copies=80% BASE TARGET
~~~

When a copy is detected, the output can use code C along with a similarity score, such as C100.

### Example: Copying a File

Suppose you keep src/BaseParser.java intact and create src/StrictParser.java by copying it and editing a few lines:

~~~bash
cp src/BaseParser.java src/StrictParser.java
# Edit src/StrictParser.java
git add src/StrictParser.java
~~~

When comparing the index or commits, copy detection can recognize that the new file originated from an existing file:

~~~bash
git diff --cached --find-copies=80%
~~~

The result depends on whether Git considers the source file an eligible candidate. By default, copy detection typically only examines source files that were modified in the same changeset, to avoid comparing against every unmodified file.

## 7. When Do You Need --find-copies-harder?

If the source file is unmodified, default copy detection may not consider it as a source. Use --find-copies-harder together with -C so Git inspects unmodified files as source candidates too:

~~~bash
git diff -C --find-copies-harder BASE TARGET
~~~

For example, src/BaseParser.java remains untouched while src/StrictParser.java was created from it. --find-copies-harder allows Git to compare the new file against unmodified source files as well.

This option can take significant time in large repositories because the number of file pairs to compare increases. Use it only when you need to find a copy source from an unmodified file, rather than enabling it routinely for every diff.

You can combine it with a threshold:

~~~bash
git diff -C80% --find-copies-harder BASE TARGET
~~~

Or use the long form:

~~~bash
git diff --find-copies=80% --find-copies-harder BASE TARGET
~~~

--find-copies-harder does not replace -C; enable copy detection with -C or --find-copies alongside this option.

## 8. Distinguishing Renames and Copies

| Scenario | Signal in Snapshot | Possible Diff Result |
| --- | --- | --- |
| File renamed, content unchanged | Old path gone, new path appears | R100 |
| File renamed and partially edited | Old path gone, new path appears with similar content | Rnnn if threshold is met |
| File copied, source kept | Source path remains, new path appears | Cnnn if copy detection finds the source |
| Copied from unmodified source file | Source path has no changes in changeset | Requires -C --find-copies-harder to consider that source |
| File completely rewritten after rename | Old path gone, new path appears with low content similarity | May display D and A |

R and C are presentation labels generated by diff. They are not distinct status types stored directly in the commit tree.

## 9. Disabling Rename Detection with --no-renames

Sometimes you want to see changes strictly as deletions and additions without Git pairing files as renames:

~~~bash
git diff --no-renames BASE TARGET
~~~

This command is useful when:

- Checking whether the heuristic mispaired a set of files.
- Wanting to inspect the deleted old file and added new file independently.
- Simplifying output for a downstream tool that does not expect rename detection.
- Comparing results with and without rename detection.

Compare:

~~~bash
git diff -M --name-status BASE TARGET
git diff --no-renames --name-status BASE TARGET
~~~

If a pair appears as R in the first command, the second command may show D for the old path and A for the new path.

## 10. Limiting the Cost of Rename/Copy Detection

Rename/copy detection must compare deletion, addition, and copy-source candidates. When a changeset has a very large number of files, the number of comparisons grows rapidly and can slow down diffs.

The -l<num> option limits the number of rename/copy candidates:

~~~bash
git diff -M -l200 BASE TARGET
~~~

If the number of targets to inspect exceeds this limit, Git may skip rename/copy detection to avoid excessive cost. This value is a performance limit, not a similarity threshold.

You can configure a default limit for the repository or user:

~~~bash
git config diff.renameLimit 200
~~~

The per-command -l option sets the limit directly. When investigating why Git did not detect a rename in a large changeset, check both the similarity threshold and the rename/copy limit.

## 11. Related Settings

Git has the diff.renames setting to control detection:

~~~bash
# Enable rename detection
git config diff.renames true

# Disable rename detection
git config diff.renames false

# Enable copy detection along with renames
git config diff.renames copies
~~~

Configuration values affect how diff commands present changes. You can inspect active settings and their origin:

~~~bash
git config --show-origin --get diff.renames
git config --show-origin --get diff.renameLimit
~~~

No output usually means the value is not explicitly set; Git uses the defaults for your version and command. Command-line flags such as --no-renames, -M, or -C let you state the desired behavior explicitly for a single run.

## 12. Reading Different Output Formats

### --name-status

Best when you only need filenames and statuses:

~~~bash
git diff --name-status -M -C BASE TARGET
~~~

Main codes:

| Code | Meaning |
| --- | --- |
| A | File added. |
| D | File deleted. |
| M | File modified. |
| Rnnn | Rename with nnn% similarity score. |
| Cnnn | Copy with nnn% similarity score. |

For renames/copies, output typically includes both the source path and the destination path. Do not assume every line contains only one path.

### --summary

Best for a quick overview:

~~~bash
git diff --summary -M -C BASE TARGET
~~~

Output can indicate renames, copies, file mode changes, and created or deleted files.

### --raw

Best when you need modes and OIDs:

~~~bash
git diff --raw -M BASE TARGET
~~~

Raw diffs contain old/new modes, old/new object IDs, and status codes. For renames or copies, output includes the similarity score and both paths. This is a lower-level format suited to specialized tools and harder to scan visually than --name-status.

### --stat

~~~bash
git diff --stat -M BASE TARGET
~~~

Statistics can collapse a rename pair onto a single line showing the old and new paths. It is useful for grasping the scope of changes, though it does not replace reading the content diff.

## 13. Viewing Renames/Copies in Commit History

The same options work when inspecting history:

~~~bash
# Summarize renames in the latest commit
git show --summary -M HEAD

# List changed files across commits
git log --name-status -M

# Show statistics with rename detection
git log --stat -M
~~~

To raise the threshold:

~~~bash
git log --name-status --find-renames=90%
~~~

History commands are still analyzing differences between snapshots. Seeing a commit displayed with a rename does not mean the commit object contains a separate rename operation.

## 14. Cases Where Heuristics Can Miss or Mispair

### Renaming and Rewriting Almost the Entire File

If the new content differs heavily from the old content, the similarity score may fall below the threshold. Git displays delete/add instead of rename. You can try a lower threshold, but confirm the pairing using real context.

### Two Independent Files with Similar Content

Template files, generated files, or multiple modules with identical boilerplate can be mistakenly paired. Lower thresholds increase this risk. Verify paths, contents, and related history.

### Copying from an Unmodified Source File

With -C alone, Git may not consider unmodified source files. Try -C --find-copies-harder when needed, keeping the performance cost in mind for large repositories.

### A Changeset with Too Many Files

Git may skip rename/copy detection due to candidate limits. Check -l<num> and diff.renameLimit, or re-run with a narrower path scope.

### Binary or Auto-Generated Files

Similarity remains a content heuristic; it does not understand business structure or file semantics. For binary files, generated code, or large data files, verify using metadata and change context rather than relying solely on percentages.

## 15. Practical Workflow: Checking a Rename

Suppose you rename and partially modify a file:

~~~bash
git mv src/OldParser.java src/Parser.java
# Edit src/Parser.java
git add -A
~~~

Check status and output:

~~~bash
git status --short
git diff --cached --name-status -M
git diff --cached --summary -M
git diff --cached -M
~~~

If Git does not recognize the rename:

~~~bash
# Try a lower threshold
git diff --cached --find-renames=30%

# Disable rename detection to inspect deletion/addition separately
git diff --cached --no-renames
~~~

Compare the outputs to see how Git pairs the files. Before committing, verify the old path is gone, the new path has the right content, and the diff reflects your intent.

## 16. Practical Workflow: Finding the Source of a Copied File

Suppose src/BaseParser.java still exists, while src/StrictParser.java was created by copying and editing it:

~~~bash
cp src/BaseParser.java src/StrictParser.java
# Edit src/StrictParser.java
git add -A
~~~

Try normal copy detection:

~~~bash
git diff --cached -C --name-status
~~~

If it is not detected because the source is unmodified, try:

~~~bash
git diff --cached -C --find-copies-harder --name-status
~~~

To require higher minimum similarity:

~~~bash
git diff --cached --find-copies=80% --find-copies-harder
~~~

If the output reports Cnnn, inspect both the source file and the destination file. A high similarity score shows that the contents are algorithmically similar, but does not prove the author created the file via a specific copy command.

## 17. Common Pitfalls

### Thinking Git Stores Renames as a Separate Operation

Incorrect. Commits store tree snapshots. Renames are inferred when Git compares deleted paths with added paths.

### Thinking git mv Is Required for Git to Detect a Rename

Incorrect. Moving a file with filesystem tools and staging the changes properly can still be detected. git mv is a convenience helper that moves the file and updates the index together.

### Thinking -C Always Scans Every Possible Copy Source

Incorrect. By default, copy detection typically limits sources to modified files. Use -C --find-copies-harder to include unmodified files as well.

### Lowering the Similarity Threshold Too Far to Force Detection

This can mispair unrelated files. Inspect both paths and their contents instead of forcing an R code.

### Thinking R100 and C100 Are Commit Metadata

These are diff presentation results, not operation-type attributes stored inside the commit.

### Failing to Detect Renames in Large Changesets

Check -l<num> and diff.renameLimit. Git may skip detection due to performance limits.

### Using --find-copies-harder on Every Command

This option can be slow because it expands the copy-source candidate pool. Enable it only when looking for unmodified copy sources.

## 18. Key Takeaways

- Git stores snapshots of paths and objects; renames and copies are inferred when generating diffs.
- -M or --find-renames enables rename detection; -C or --find-copies enables copy detection.
- Thresholds like --find-renames=80% set the minimum similarity required to pair files.
- Rnnn indicates a rename and Cnnn indicates a copy, along with the similarity percentage.
- -C normally looks for copy sources among modified files; -C --find-copies-harder includes unmodified source files as well.
- --no-renames disables rename detection so you can view deletions and additions separately.
- -l<num> and diff.renameLimit bound detection cost.
- --name-status, --summary, --raw, and --stat offer different views of the results.
- Low thresholds can cause mispairings; high thresholds can miss real renames.
- Similarity scores do not prove the author's intent or historical lineage.

Rename and copy detection make diffs easier to read by inferring relationships between files across two snapshots. When you understand similarity thresholds, copy-source selection, and performance limits, you can interpret output more accurately, tune commands for each situation, and avoid treating heuristic results as absolute truth about how a change was authored.

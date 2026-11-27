# Comparing the Index with HEAD Using git diff --staged

Before creating a commit, you need to know the exact changes placed in the staging area. The `git diff --staged` command shows the differences between the index and the current commit (HEAD). This is an important review step: it reveals the snapshot that the next commit will record for the staged files.

This command is commonly used after `git add` or `git add -p`. You can inspect each selected line, catch mistakenly staged files, view statistics, check for whitespace errors, and export patches to share. Understanding the comparison direction also prevents confusing staged content with subsequent edits in the working tree.

After this lesson, you will be able to:

- Explain accurately which two areas `git diff --staged` compares.
- Distinguish between staged diffs, unstaged diffs, and total diffs against HEAD.
- Restrict diffs to specific files or directories.
- Read unified diffs and recognize added lines, removed lines, context, mode changes, and renames.
- Use statistics and pre-commit inspection options.
- View word-level changes, check whitespace, and export patches.
- Combine diffs with selective staging to create properly scoped commits.

## 1. HEAD, Index, and Working Tree

Git has three states to distinguish when reviewing changes:

- **HEAD** normally points to the current commit, i.e., the latest snapshot on the checked-out branch.
- **Index** (staging area) holds the file versions selected for the next commit.
- **Working tree** is the current file content on disk that you are editing.

Typical workflow:

~~~text
                 git add
Working tree ----------------> Index
     |                           |
     | git diff                  | git diff --staged
     v                           v
  Index                         HEAD
                                  ^
                                  |
                               git commit
~~~

The three corresponding comparisons:

| Command | Compares | Question Answered |
| --- | --- | --- |
| `git diff` | Working tree vs. index | What additional edits have I made without staging? |
| `git diff --staged` | Index vs. HEAD | What staged changes will go into the commit? |
| `git diff HEAD` | Working tree vs. HEAD | What are the total tracked changes compared to the latest commit? |

The order of the two sides in a comparison affects the direction of the diff. With `git diff --staged`, Git shows how the index differs from HEAD: added lines are content present in the index but not yet in HEAD; removed lines are content present in HEAD but no longer in the index.

## 2. Running git diff --staged

Basic command:

~~~bash
git diff --staged
~~~

`--staged` is a readable synonym for the `--cached` option. The following two commands are equivalent:

~~~bash
git diff --staged
git diff --cached
~~~

If no commit is specified for comparison, Git uses HEAD as the baseline. In other words, the command shows how the snapshot in the index will change relative to the current commit.

For example, after staging a change:

~~~bash
git add src/Search.java
git diff --staged
~~~

Git prints the diff of `src/Search.java` between the staged content and the version in HEAD. If the file is edited further after staging, those subsequent edits do not appear in this command; they belong to the `git diff` comparison.

`git diff --staged` only inspects paths tracked by Git in the index. Untracked files do not automatically appear in the diff. To include a new file in the staged diff, you must first stage it with `git add`.

## 3. Example: A File with Both Staged and Unstaged Changes

Suppose `src/Search.java` initially returns results directly. You edit the file to normalize the query, then stage it:

~~~bash
git add src/Search.java
~~~

Next, you continue editing the file to handle null values, without staging a second time.

At this point:

~~~bash
git diff --staged
git diff
git status --short
~~~

- `git diff --staged` shows the changes staged by the earlier `git add`.
- `git diff` shows the new edits in the working tree compared to the index.
- `git status --short` may show `MM` for that file: the first column represents changes in the index, and the second column represents changes in the working tree.

If you create a commit right now, Git records the version in the index. The unstaged null-handling edits remain in the working tree after the commit. This is why you should inspect both the staged diff and the unstaged diff before committing whenever you have continued editing after staging.

## 4. Specifying Another Commit as the Comparison Baseline

You can pass a commit or ref after the option:

~~~bash
git diff --staged HEAD
git diff --staged origin/main
git diff --staged abc1234
~~~

If the argument is omitted, Git defaults to HEAD. If you specify `origin/main`, Git compares the index against that local remote-tracking branch. The command does not automatically fetch from the remote; the ref only reflects data already present in the local repository.

This is useful when you want to see how the staged snapshot differs from a base branch before creating a commit or when preparing content to move to another branch.

If the repository does not yet have an initial commit, HEAD does not resolve to a commit. Git can display staged entries as new files compared to an empty tree. This commonly occurs right after initializing a repository and staging the first content.

## 5. Limiting Diffs by File or Directory

If you only want to review a single file:

~~~bash
git diff --staged -- src/Search.java
~~~

Or restrict by directory:

~~~bash
git diff --staged -- src/
~~~

The `--` separator distinguishes options from pathspecs. Using this separator prevents filenames from being misinterpreted as options. You can pass multiple pathspecs:

~~~bash
git diff --staged -- src/Search.java README.md
~~~

Pathspecs allow patterns using Git syntax. When writing scripts, quote patterns appropriately for your shell so the shell does not expand globs before Git receives them.

Note: if a file has not been staged or does not have a matching entry in the index, it will not appear in the staged diff simply because you passed its path. Use `git status` or `git ls-files` to confirm the file is in the index.

## 6. Reading a Unified Diff

A typical diff excerpt:

~~~diff
diff --git a/src/Search.java b/src/Search.java
index 12ab345..67cd890 100644
--- a/src/Search.java
+++ b/src/Search.java
@@ -10,7 +10,7 @@ public class Search {
-    return query;
+    return normalize(query);
 }
~~~

Meaning of the components:

- `diff --git` indicates the old-side and new-side paths.
- `index` shows the old and new OIDs along with the file mode.
- `---` is the old-side file; `+++` is the new-side file.
- A line starting with `@@` is a hunk header, indicating the line position and range.
- A line starting with a space is context, existing on both sides.
- A line starting with `-` existed in the old version but was removed from the new version.
- A line starting with `+` was added in the new version.

A hunk header like `@@ -10,7 +10,7 @@` describes the line region displayed on both sides. Line numbers and line counts may differ if the change adds or removes lines.

A diff describes content changes, not a verbatim copy of the file. Context lines are included to help reviewers understand where changes occur and to give patches an anchor when applying them.

## 7. Viewing Statistics Instead of Full Content

When a staged diff is large, you can get an overview first:

~~~bash
# Lines added/removed per file
git diff --staged --stat

# Single summary line
git diff --staged --shortstat

# Numeric format suitable for script processing
git diff --staged --numstat
~~~

Example `--stat` output:

~~~text
 src/Search.java | 8 ++++----
 README.md       | 4 ++++
 2 files changed, 7 insertions(+), 5 deletions(-)
~~~

`--numstat` typically gives, for each file, the number of added lines, removed lines, and the path. For binary files, line counts may appear as dashes instead of numbers.

List filenames:

~~~bash
git diff --staged --name-only
~~~

List filenames with status:

~~~bash
git diff --staged --name-status
~~~

Common status codes include `A` (added), `M` (modified), `D` (deleted), `R` (renamed), and `C` (copied) when Git detects those cases.

Git infers renames/copies based on content similarity when generating a diff; renames are not stored as explicit rename operations in the commit tree. As a result, detection depends on thresholds and rename-detection options.

## 8. Checking Whitespace Before Committing

Certain whitespace errors are easy to overlook during review:

- Trailing whitespace at the end of a line.
- Missing newline at the end of a file.
- Lines containing whitespace-only indentation issues.

Run:

~~~bash
git diff --staged --check
~~~

This command checks for whitespace errors recognized by Git in staged changes. It does not print a normal diff; instead, it reports problematic locations. The command returns a non-zero exit code when whitespace errors are detected.

You can combine it into your review workflow:

~~~bash
git diff --staged --check
git diff --staged
~~~

`--check` does not replace a formatter, linter, or project formatting rules. It only detects a specific set of whitespace errors. Run the appropriate quality tools if the repository enforces its own conventions.

## 9. Viewing Changes by Word Instead of by Line

For documentation or long lines of text, line-based diffs can make it hard to spot a single modified word. Use:

~~~bash
git diff --staged --word-diff
~~~

Or choose how words are highlighted:

~~~bash
git diff --staged --word-diff=color
~~~

Word diffs help identify added or removed words or character segments within the same line. How words are tokenized depends on configuration and content; it is helpful for reviewing prose, though for complex code structures, line-based diffs are usually still easier to read.

You can use a regular expression to define comparison units:

~~~bash
git diff --staged --word-diff-regex='[[:alnum:]_]+'
~~~

This example treats alphanumeric sequences and underscores as word units. Choose a regex suited to the language or format you are reviewing.

## 10. Adjusting Context Lines

By default, unified diffs display several lines of context around changes. To increase or decrease the number of lines:

~~~bash
# Show 5 lines of context
git diff --staged -U5

# Show only changed lines, with no context
git diff --staged -U0
~~~

More context lines help you follow code flow, though the output becomes longer. Zero context focuses tightly on the changed lines, though it can make it harder for reviewers to identify location or meaning.

When reviewing logic, it is usually best to keep the default context or increase it. When generating machine-readable output or matching exact changed regions, you can reduce context if the tool consuming the patch supports it.

## 11. File Mode Changes, Renames, and Binary Files

Not all changes consist of added or removed lines:

- A file can switch between executable and non-executable modes.
- A file can be deleted or added.
- Git can recognize a delete/add pair as a rename based on similarity.
- Binary files may not produce a human-readable unified text diff.

Run:

~~~bash
git diff --staged --summary
git diff --staged --raw
~~~

`--summary` displays high-level information such as create, delete, mode change, or rename when detected. `--raw` displays lower-level information including modes and OIDs.

If you need to export a patch containing binary data:

~~~bash
git diff --staged --binary > staged-changes.patch
~~~

This patch can be applied with Git in another repository if the base state matches. Never inspect only text diffs and assume there are no binary changes; check file stats and statuses as well.

## 12. Diffs Do Not Include Untracked Files

A new file that has not been staged is not in the index, so it does not appear in:

~~~bash
git diff --staged
~~~

Even `git diff HEAD` does not automatically include untracked file contents in its output. First, you need to decide whether that file belongs in the commit.

For example:

~~~bash
# View new untracked files
git status --short

# Stage the file if you want to include it in the commit
git add docs/new-guide.md

# View the staged new file content
git diff --staged -- docs/new-guide.md
~~~

If you only want to inspect a new file's content before staging, open the file or use an external diff tool. You can run `git diff --no-index` to compare two files or compare a file against other content, but that is a standalone comparison, not the repository's staged diff.

## 13. Using Exit Codes in Scripts

When integrating diffs into scripts, you can use `--exit-code`:

~~~bash
git diff --staged --exit-code
~~~

Exit codes:

- `0` if there are no differences.
- `1` if differences exist.
- Values greater than 1 typically indicate an execution or other error.

If you only need to check whether a diff exists without printing its content:

~~~bash
git diff --staged --quiet
~~~

`--quiet` suppresses output and implies `--exit-code` behavior. Scripts should distinguish "differences exist" from "the command failed"; do not treat every non-zero code as the same condition.

Shell example:

~~~bash
if git diff --staged --quiet; then
    echo "No staged changes."
else
    result=$?
    if [ "$result" -eq 1 ]; then
        echo "Staged changes are present."
    else
        echo "git diff failed with exit code $result."
        exit "$result"
    fi
fi
~~~

In complex scripts, handle repository errors, invalid pathspecs, and permission issues separately; exit codes help distinguish "no changes" from cases where the command could not complete.

## 14. Combining Staged Diffs with Selective Staging

You do not have to stage an entire file. `git add -p` lets you choose individual hunks:

~~~bash
git add -p src/Search.java
~~~

Then review the selected portion:

~~~bash
git diff --staged
git diff
~~~

If the staged diff contains changes that do not belong in the current commit, you can unstage the file or hunk and re-select:

~~~bash
# Unstage the entire file while keeping the working tree intact
git restore --staged src/Search.java
~~~

Then re-select hunks with `git add -p` and inspect the staged diff again.

For older Git versions that do not support `git restore`, you can use:

~~~bash
git reset HEAD -- src/Search.java
~~~

This command updates the index back to HEAD for the selected path while preserving changes in the working tree. Understand the current state before using it, especially if the index already holds staged content you want to keep.

## 15. Pre-Commit Review Workflow

A safe workflow:

~~~bash
# 1. Get an overview
git status

# 2. Review staged changes
git diff --staged

# 3. Check whitespace in what will be committed
git diff --staged --check

# 4. Inspect files and statistics
git diff --staged --name-status
git diff --staged --stat

# 5. Check remaining unstaged changes
git diff

# 6. Create the commit after confirming the scope
git commit
~~~

Before committing, ask yourself:

- Was any file staged by mistake?
- Is any necessary file still untracked or unstaged?
- Are there further edits sitting in the working tree that have not been added to the index?
- Are there any deletions, mode changes, or renames that could easily be overlooked?
- Are there any whitespace errors that need fixing?
- Does the commit message accurately describe the staged diff?

If the commit should only contain part of your changes, return to selective staging instead of committing a broader snapshot than intended.

## 16. Exporting a Staged Diff as a Patch

To share staged changes as a patch:

~~~bash
git diff --staged > staged-changes.patch
~~~

If binary files are included:

~~~bash
git diff --staged --binary > staged-changes.patch
~~~

A patch created from a staged diff describes the difference between the index and HEAD. It does not create a commit and does not automatically carry full commit metadata such as author, committer, or commit message. If you need to transfer commits along with metadata, look into `git format-patch` and `git am`.

The recipient needs a matching base state to apply the patch. You can verify first with `git apply --check staged-changes.patch` and then apply with `git apply`.

## 17. Common Pitfalls

### Running git diff --staged but Not Seeing a Recently Edited File

The file may not have been staged yet, or the new edits may sit in the working tree after a previous stage. Use `git status` and `git diff` to check.

### Assuming git diff --staged Shows All Uncommitted Changes

Incorrect. The command only compares the index with HEAD. Unstaged changes must be inspected with `git diff`; total tracked changes relative to HEAD can be inspected with `git diff HEAD`.

### Untracked Files Do Not Appear in the Diff

That is normal behavior. Stage the file with `git add` if you want it included in the commit.

### Staging a File, Editing It Further, and Thinking the Commit Will Include Everything

Commits take their snapshot from the index. Edits made after the last stage are not automatically included in the commit. Read both `git diff --staged` and `git diff`.

### Using --stat and Assuming You Have Reviewed the Content

Statistics only show the number of files and changed lines. Open the full diff for changes whose logic needs review.

### Using --check and Assuming the Code Is Correct

`--check` only detects certain whitespace errors. It does not run tests, compilers, formatters, or linters.

### Mistaking Rename Detection for a Rename Stored in the Commit

Git stores tree snapshots. Renames are typically inferred when rendering diffs based on similarity between old and new files.

## 18. Key Takeaways

- `git diff --staged` and `git diff --cached` are equivalent.
- By default, a staged diff compares the index with HEAD.
- `git diff` compares the working tree with the index; `git diff HEAD` compares the working tree with HEAD.
- The next commit takes its snapshot from the index, not directly from everything currently on disk.
- Use pathspecs to narrow down files, `--stat` or `--name-status` for an overview, and full diffs to review content.
- Use `--check` to catch certain whitespace errors before committing.
- Use `--word-diff` for long prose and `-U<n>` to adjust context lines.
- Untracked files do not appear in staged diffs until they are staged.
- Use `--exit-code` or `--quiet` in scripts and distinguish the exit code for "differences exist" from execution errors.
- Review both staged and unstaged diffs before committing if you have edited files after staging.

`git diff --staged` is a direct check of the snapshot prepared in the index against HEAD. Combining it with `git status`, `git diff`, and statistics/validation options helps ensure your commit contains only the intended changes, catch missing or mistakenly staged edits, and build a Git history that is easy to review.

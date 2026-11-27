# Comparing Two Commits, Two Branches, and a Specific Path

When reviewing a change, you often need to answer three questions: how do two commits differ in content, what has a feature branch added since diverging from the main branch, and how has a specific file changed. The **git diff** command helps answer these questions by comparing snapshots (trees) or comparing the index with the working tree.

The key is choosing the right two comparison endpoints. `git diff A B` compares the snapshot of A with B; `git diff A...B` compares the merge base of A and B with B. These two forms answer different questions. When you only care about a single file or directory, place a pathspec after `--` to narrow the scope.

## 1. What Does git diff Compare?

Git stores project snapshots in tree objects. Each commit points to a tree describing the directory structure and file contents at the time of the commit.

`git diff` compares two states to display the differences. It does not compare commit messages, authors, or commit timestamps; that information belongs to history metadata and is inspected with commands like `git log` or `git show`.

For example, two commits may differ in:

- The contents of one or more files.
- Added, deleted, or renamed files.
- A file's executable bit.
- Symbolic links or submodule gitlinks.
- Directory path structure in the tree.

Simple diagram:

```text
Commit A                         Commit B
   |                                |
   v                                v
 Tree A                           Tree B
   |                                |
 README.md: "v1"                 README.md: "v2"
 src/App.java                    src/App.java
 src/Old.java                    src/New.java
   \                                /
    +--------- git diff -----------+
                  |
                  v
       Patch describing A -> B
```

Comparison direction matters: the patch from `git diff A B` describes how to transform the content in A into the content in B. Swapping the two endpoints reverses the direction of the changes.

## 2. Comparing Two Commits by OID or Reference Name

Basic syntax:

```bash
git diff <commit-A> <commit-B>
```

Example:

```bash
git diff a1b2c3d e4f5a6b
```

Git compares the trees of the two commits and prints the diff. You can use full OIDs or any reference name that Git resolves to a commit, such as `HEAD`, a branch, a tag, or a revision expression.

Some examples:

```bash
git diff HEAD~1 HEAD
git diff v1.2.0 v1.3.0
git diff main release/2.x
```

- `HEAD~1` is the first parent commit of HEAD.
- `v1.2.0` and `v1.3.0` can be tags pointing to commits or tag objects resolved to their target objects.
- `main` and `release/2.x` are branch names if they exist in the repository.

To view the changes introduced by a regular commit compared to its parent:

```bash
git diff <commit>^ <commit>
```

Or use:

```bash
git show <commit>
```

`git show` typically displays commit metadata alongside the diff. `git diff` focuses purely on the difference between two snapshots.

For a root commit with no parent, `<commit>^` cannot be used. You can view the initial snapshot with:

```bash
git show --root <root-commit>
```

## 3. Distinguishing A..B and A...B in git diff

This is a very common point of confusion when comparing branches.

With `git diff`:

- `git diff A B` directly compares the tree of A with the tree of B.
- `git diff A..B` has the exact same meaning as `git diff A B`.
- `git diff A...B` compares the tree at the merge base of A and B with the tree of B.

This differs from how `git log` interprets revision ranges. In `git log`, `A..B` typically selects the set of commits reachable from B but not reachable from A. In `git diff`, two dots do not select a set of commits to output; it is merely an alternate syntax for a two-endpoint comparison.

### Example with Two Diverged Branches

Suppose the history is:

```text
             F1 --- F2   feature
            /
A --- B --- C --- D      main
```

Both branches share the common ancestor `C`. `main` continues to `D`, while `feature` has `F1` and `F2`.

Compare the current snapshots of the two branches:

```bash
git diff main feature
```

This command shows every difference between the tip of `main` and the tip of `feature`. The patch goes in the direction from `main` to `feature`, so it may include changes introduced independently on `main`.

If you want to view only the changes introduced by `feature` since the branch point:

```bash
git diff main...feature
```

This command is equivalent to comparing the merge base of `main` and `feature` with `feature`. It shows the changes on the feature side since the two branches diverged.

To view changes on the main side since the branch point:

```bash
git diff feature...main
```

These three commands answer three different questions. Do not use them interchangeably without clarifying your review goal.

### Inspecting the Merge Base Directly

You can find the closest common ancestor that Git selects as the merge base:

```bash
git merge-base main feature
```

Then compare explicitly:

```bash
git diff <merge-base-oid> feature
```

This is useful when you want to record the exact base used in a review or verify why a three-dot diff has its particular scope.

If history contains multiple best merge bases, `git merge-base` by default may print only one result. In complex histories, inspect the commit graph and merge bases rather than assuming there is always only a single common ancestor.

## 4. Comparing a Local Branch and a Remote-Tracking Branch

A local branch name may not yet reflect the latest state on the server. Before reviewing a branch against a remote, update remote-tracking refs:

```bash
git fetch origin
```

Then compare:

```bash
git diff main origin/main
git diff origin/main...feature/login
```

- The first command compares the local `main` snapshot with the latest fetched snapshot of `origin/main`.
- The second command shows the changes on `feature/login` since its merge base with `origin/main`.

You can view the separate commit lists before inspecting the diff:

```bash
git log --oneline --left-right --graph origin/main...feature/login
```

`git log` and `git diff` complement each other: the log shows which commits differ, and the diff shows where the snapshot contents differ.

If the remote is not named `origin` or the main branch is not named `main`, substitute your project's actual remote and branch names.

## 5. Comparing a Specific Path Between Two Commits

Add `--` followed by the path you want to restrict to:

```bash
git diff <commit-A> <commit-B> -- src/App.java
```

Example:

```bash
git diff main feature/login -- src/auth/Authenticator.java
```

Git displays only the differences for that path between the two snapshots. If the file does not exist on one side, the diff may show the entire content as an added or deleted file.

You can restrict to an entire directory:

```bash
git diff main feature/login -- src/auth/
```

A directory pathspec generally includes subdirectories and nested paths. This is helpful when reviewing a specific package or module without reading the entire diff.

Relative paths in a pathspec are resolved from your current working directory. If you run Git from a subdirectory, write the path relative to that location or change to the repository root before comparing to avoid filtering the wrong scope.

### Why Is -- Needed?

The `--` separator distinguishes preceding revisions and options from the trailing pathspec. It prevents Git from misinterpreting a filename as a branch name or revision.

Example:

```bash
git diff main feature/login -- README.md
git diff main feature/login -- -notes.txt
```

If a path begins with a hyphen, `--` ensures Git recognizes it as a pathspec. If a filename contains glob characters or special characters, you can quote it for the shell and use a literal pathspec:

```bash
git diff main feature/login -- ':(literal)src/[legacy].java'
```

`:(literal)` tells Git to treat the remainder as a literal path rather than interpreting characters as patterns. Quoting rules also depend on the shell; PowerShell, Bash, and CMD have different argument-passing rules.

## 6. Comparing a File with the Current Working Tree

Both endpoints do not always have to be commits. If you pass only one commit and a pathspec, Git compares that commit's snapshot with the current working tree:

```bash
git diff HEAD -- src/App.java
git diff main -- README.md
```

The first command shows how the current `src/App.java` differs from `HEAD`, including both staged and unstaged changes. The second command compares `README.md` on the `main` branch with the corresponding file in the current working tree.

If you want to view a file in a specific commit without comparing it to the working tree:

```bash
git show <commit>:src/App.java
```

The expression `<commit>:<path>` retrieves the blob content at that path in the commit's tree. This command displays the file content rather than generating a diff.

## 7. Properly Understanding HEAD, Index, and Working Tree

In daily work, `git diff` is commonly used to check changes across three areas:

```text
             git diff --cached
      HEAD ----------------------> Index
        \                            |
         \                           | git diff
          \                          v
           --------------------> Working tree
                  git diff HEAD
```

Commands:

| Command | Compares | Question Answered |
|---|---|---|
| `git diff` | Index vs. working tree | After staging, what unstaged edits remain? |
| `git diff --cached` or `--staged` | HEAD vs. index | What am I preparing to commit? |
| `git diff HEAD` | HEAD vs. working tree | Overall, how do tracked files currently differ from the current commit? |

Example:

```bash
git add src/App.java
# Continue editing README.md after staging
git diff
git diff --cached
git diff HEAD
```

- `git diff` shows the new unstaged edits to `README.md`.
- `git diff --cached` shows the staged changes to `src/App.java`.
- `git diff HEAD` shows both staged and unstaged changes across tracked files.

If you want to view staged changes for a single file:

```bash
git diff --cached -- src/App.java
```

If you want to view unstaged changes for a single file:

```bash
git diff -- src/App.java
```

These commands help verify the exact content to be committed. `git status` only summarizes file states; `git diff` shows the concrete content.

## 8. Reading Diff Output

A unified diff typically has the following structure:

```diff
diff --git a/src/App.java b/src/App.java
index 1234567..89abcde 100644
--- a/src/App.java
+++ b/src/App.java
@@ -10,5 +10,6 @@
 public class App {
-    System.out.println("Hello");
+    System.out.println("Hello Git");
+    validateConfig();
 }
```

Main parts:

- `diff --git`: begins the diff section for a path.
- `index`: old and new blob OIDs along with the mode.
- `--- a/...`: the before-change side.
- `+++ b/...`: the after-change side.
- `@@ -10,5 +10,6 @@`: position and line counts of the diff section (hunk).
- Lines starting with a space are context, `-` indicates removed content, and `+` indicates added content.

Unified diffs typically show a few context lines around changes. Increase or decrease the number of context lines:

```bash
git diff --unified=0 main...feature/login
git diff -U10 main...feature/login
```

`-U0` shows only changed lines, while `-U10` shows 10 context lines on each side. More context helps clarify surrounding logic; less context produces a shorter patch.

## 9. Choosing the Right Output Format for Reviews or Scripts

You do not always need the full patch. Git provides summary modes:

| Option | Result |
|---|---|
| `--stat` | Summary table of changed files and added/removed line counts |
| `--shortstat` | Single total summary line |
| `--numstat` | Added/removed line counts per file |
| `--name-only` | Print only changed path names |
| `--name-status` | Print file status such as added, modified, deleted, or renamed |
| `--summary` | Summarize create/delete modes, renames, and certain metadata changes |
| `--check` | Check for whitespace errors such as trailing whitespace |
| `--word-diff` | Display changes at the word level |
| `--color-moved` | Highlight moved lines in the diff |

Examples for getting an overview of a feature branch:

```bash
git diff --stat main...feature/login
git diff --name-status main...feature/login
git diff --numstat main...feature/login
```

If you only need to know which files changed:

```bash
git diff --name-only main...feature/login
```

If you need to check whitespace before committing:

```bash
git diff --check
git diff --cached --check
```

`--check` is helpful for catching trailing whitespace or unwanted spaces. It does not replace a project's formatter or linter.

### Using Word Diff When Changes Occur Within a Long Line

If a long JSON line, documentation line, or sentence only changes a few words, a line-based diff may mark the entire line as deleted and re-added. Use:

```bash
git diff --word-diff
```

You can choose how markers are rendered:

```bash
git diff --word-diff=plain
git diff --word-diff=color
```

Word diffs are useful when reviewing prose, though word boundaries depend on how Git splits tokens. For source code, always inspect line-based diffs as well to understand structural changes.

## 10. Detecting Renames and Copies

Git does not store an explicit rename operation as mandatory metadata in a commit. When comparing two trees, Git infers renames based on content similarity.

By default, `git diff` typically enables rename detection where appropriate. You can request it explicitly:

```bash
git diff -M main feature/login
```

`-M` enables rename detection. You can set a similarity threshold, for example:

```bash
git diff -M90% main feature/login
```

A higher threshold requires the old and new file contents to match more closely to be detected as a rename. You can enable copy detection:

```bash
git diff -C main feature/login
```

By default, copy detection usually only considers source files that were modified or deleted. If you need to detect files copied from an unmodified source file, use `--find-copies-harder`; this takes more effort because Git must inspect more files:

```bash
git diff --find-copies-harder -C main feature/login
```

If you want to view changes as a deletion and addition instead of a rename:

```bash
git diff --no-renames main feature/login
```

Rename/copy results are inferences from content and detection thresholds, not definitive proof of the author's intent. When reviewing, inspect the actual diff of the new file to confirm the moved content is correct.

## 11. Comparing Files with Binary or Submodule Changes

For text files, Git typically displays line-by-line diffs. For binary files, Git usually only reports that the two files differ because it cannot present the content meaningfully line by line.

You can view statistics:

```bash
git diff --stat <commit-A> <commit-B> -- assets/
```

If you need to generate a patch that carries binary data, use `--binary` when exporting the diff:

```bash
git diff --binary <commit-A> <commit-B> > changes.patch
```

For submodules, the superproject stores a gitlink pointing to a commit in the child repository. A diff can show that the gitlink OID changed; to view the child commit log between the two points, run:

```bash
git diff --submodule=log <commit-A> <commit-B> -- libs/shared-utils
```

The output depends on whether the child repository has the necessary commits locally. If not, fetch the submodule/child repository according to your project's workflow before analyzing further.

## 12. Merge Commits and Comparing Against Each Parent

A merge commit has multiple parents, so answering "what did the merge add?" requires specifying which parent serves as the comparison baseline.

View the list of parents:

```bash
git show --no-patch --pretty=raw <merge-commit>
```

Compare the merge result against its first parent:

```bash
git diff <merge-commit>^1 <merge-commit>
```

Compare against its second parent:

```bash
git diff <merge-commit>^2 <merge-commit>
```

The two diffs can look very different because each parent represents one of the branches before merging. To see how the merge brought changes from the second branch into the first branch, you typically inspect the diff against the first parent while also reading the commit graph and checking conflict resolutions.

Never inspect only one diff and draw conclusions about the entire merge; a merge commit may contain conflict resolution decisions and additional adjustments made during integration.

## 13. Checking Differences in Scripts Using Exit Codes

By default, `git diff` prints a patch and usually returns exit code 0 even when differences exist. If a script needs to check whether two states differ, use `--exit-code` or `--quiet`.

Example:

```bash
if git diff --quiet main...feature/login; then
  echo "No differences"
else
  echo "Differences exist or diff command failed"
fi
```

`--quiet` suppresses diff output. Exit code 0 means no differences; exit code 1 means differences exist. Other codes may indicate an error, so serious scripts should distinguish exit code 1 from execution failures.

Explicit handling in Bash:

```bash
git diff --quiet main...feature/login
rc=$?

case "$rc" in
  0) echo "No differences" ;;
  1) echo "Differences exist" ;;
  *) echo "Unable to compare" >&2; exit "$rc" ;;
esac
```

If the shell has `set -e` enabled, a command returning exit code 1 can terminate the script before reading `$?`. Place the command inside an `if` condition or handle the exit code using an appropriate shell construct.

If you want to print the diff while still using exit codes:

```bash
git diff --exit-code main...feature/login
```

The command returns exit code 1 when differences exist. This behavior is useful in CI, but configure the job to treat exit code 1 here as "diff present" rather than necessarily a Git failure.

## 14. Avoiding Misleading Results When Ignoring Whitespace

Git allows ignoring certain whitespace differences:

```bash
git diff -w main feature/login
git diff --ignore-space-at-eol main feature/login
```

`-w` ignores whitespace differences when comparing content; `--ignore-space-at-eol` ignores whitespace at the end of lines.

These options can help review formatting-only changes, but they can also mask meaningful differences in certain files. For example, whitespace can affect Makefiles, YAML, Python, or string literals. Never use a whitespace-ignoring diff as the sole proof that two versions are equivalent.

You can switch diff algorithms to make moved or refactored changes easier to read:

```bash
git diff --patience main...feature/login
git diff --histogram main...feature/login
```

These algorithms change how Git aligns context and hunk lines; they do not change the contents of the two trees being compared.

## 15. Workflow for Reviewing a Feature Branch

Suppose you need to review `feature/login` before merging it into `main`.

**Step 1: Fetch the latest information.**

```bash
git fetch origin
```

**Step 2: Identify commits and the merge base.**

```bash
git log --oneline --left-right --graph origin/main...feature/login
git merge-base origin/main feature/login
```

**Step 3: Inspect the scope of changes introduced by the feature.**

```bash
git diff --stat origin/main...feature/login
git diff --name-status origin/main...feature/login
```

**Step 4: Read the diff for each key area.**

```bash
git diff origin/main...feature/login -- src/auth/
git diff origin/main...feature/login -- tests/
git diff origin/main...feature/login -- README.md
```

**Step 5: Check whitespace and verify tests.**

```bash
git diff --check origin/main...feature/login
```

Run tests using the project's test command and check CI results. A diff helps review the changed content; it does not prove that the logic is correct or that tests pass.

**Step 6: If you need to see differences between the two current tips**, run:

```bash
git diff origin/main feature/login
```

This is a comparison of the final snapshots of both branches, useful when you want to know how their complete states differ. It differs from the feature-specific scope since the merge base.

## 16. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| `git diff A..B` gives different semantics from `git log A..B` | The two commands have different revision semantics | For diff, `A..B` is equivalent to comparing A with B |
| `git diff main feature` shows changes exclusive to main | Comparing two tip snapshots | Use `git diff main...feature` to view the feature side since the merge base |
| Three-dot diff does not show changes on main | Three dots compare the merge base with the second endpoint | Swap the order to `git diff feature...main` |
| Specific file is not found | Wrong pathspec or Git parsed the name as a revision | Use `--`, verify the path, and quote according to your shell |
| Diff does not show new commits | Diff compares trees, not commit lists | Use `git log` to view commits; use `git diff` to view snapshot content |
| Local staged changes do not appear | Running default `git diff` | Use `git diff --cached` or `git diff HEAD` |
| Rename shows up as delete/add | Rename detection did not find sufficient similarity | Try `-M`, adjust the threshold, or inspect both files directly |
| Binary files only report that they differ | Git cannot display line-by-line diffs | Use `--stat`, or `--binary` when generating a patch |
| Script treats having a diff as a Git error | Failing to distinguish exit code 1 from error codes | Handle exit codes 0, 1, and other codes separately |
| Diff hides important differences | Using `-w` or ignore-whitespace options | Re-read the full diff, especially for whitespace-sensitive files |

## 17. Checklist Before Concluding Two Versions Differ

- [ ] Identified the exact two commits/refs you actually want to compare.
- [ ] Fetched the remote if using a remote-tracking branch.
- [ ] Decided between tip-to-tip comparison and merge-base-to-branch comparison.
- [ ] Distinguished the semantics of `A..B` vs. `A...B` in `git diff`.
- [ ] Placed `--` before pathspecs.
- [ ] Checked important files or directories individually.
- [ ] Inspected both staged and unstaged changes if reviewing the working tree.
- [ ] Read the full diff before using options that ignore whitespace.
- [ ] Accounted for exit codes if diff is invoked from a script or CI.
- [ ] Checked merge parents if reviewing a merge commit.

## Conclusion

Use `git diff A B` to directly compare two snapshots; `git diff A..B` has the same meaning. Use `git diff A...B` to compare the merge base of A and B with B, which is typically appropriate when reviewing the changes introduced by a branch since it diverged. Append `-- path` to restrict to a single file or directory, use `--cached` to inspect staged content, and choose `--stat`, `--name-status`, `--check`, or `--word-diff` depending on your goal. Before drawing conclusions, clearly identify both comparison endpoints and the patch direction Git is displaying.

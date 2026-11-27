# Tracking Renamed File History with git log --follow

During development, a file may be renamed or moved to another directory multiple times. If you only run `git log -- <current-path>`, you may only see the history since the file took on its current name. Git provides the `--follow` option to continue tracing a file's history across detected renames.

The commonly used command is:

```bash
git log --follow -- <path/to/file>
```

Git does not store a dedicated "rename" event inside a commit. Each commit stores a snapshot of the directory tree; when generating diffs, Git infers renames by comparing the contents of deleted and added files. Thus, `--follow` is a similarity-based detection mechanism rather than an absolute filename ledger. This lesson explains how to read the results, tune detection thresholds, and handle complex histories.

## 1. Why Track History Across Renames?

Suppose a file started at `src/LegacyPayment.java`, was later renamed to `src/PaymentService.java`, and continued receiving edits. Querying only the new name may not show all commits prior to the rename.

Example history:

```text
commit A: create src/LegacyPayment.java
commit B: fix payment logic
commit C: rename LegacyPayment.java to PaymentService.java
commit D: add retry handling to PaymentService.java
```

When standing on the current version, you want to see commits A, B, C, and D. `git log --follow` instructs Git to continue looking up the file's history across detected renames so older commits still appear in the output.

This is useful when:

- Finding the root cause of a bug that existed before the file was renamed.
- Determining who added a piece of logic back when the file had its old name.
- Reviewing large changes after source code was moved across directories.
- Auditing a refactoring while preserving historical context.
- Preparing to modify or remove a legacy API while needing to understand its prior history.

## 2. How Does Git Detect Renames?

Git stores snapshots per commit. In a commit's tree, Git records path names and object IDs; the commit does not contain a separate field stating "path A changed to path B".

When comparing two commits, Git can recognize a paired change:

- An old path disappears (*delete*).
- A new path appears (*add*).
- The contents of both files are sufficiently similar according to the rename detection threshold.

If similarity meets the threshold, Git presents that change pair as a rename. For example:

```text
R100    src/LegacyPayment.java    src/PaymentService.java
```

`R100` means Git detected a rename with 100% similarity. If the file was renamed and modified in the same commit, the result might be `R85`, `R72`, or another score.

This is inferred from content and diffs. Two unrelated files with identical or similar contents could also be paired as a rename by Git in the right comparison context. Conversely, a renamed file that was heavily edited might not be detected as a rename.

## 3. Viewing File History with git log --follow

To view the history of the current file across renames:

```bash
git log --follow -- src/PaymentService.java
```

Git prints commits affecting that path while attempting to trace history backward across detected renames. By default, output includes commit hash, author, date, and commit message depending on the configured log format.

For compact output:

```bash
git log --follow --oneline -- src/PaymentService.java
```

To limit to the most recent commits:

```bash
git log --follow --oneline -10 -- src/PaymentService.java
```

To inspect history on a specific branch:

```bash
git log main --follow -- src/PaymentService.java
```

Specifying a branch makes results clearer when the repository has multiple branches renaming or evolving different versions of the file. If `--all` is used, Git may show history across multiple refs; read branch labels and the graph carefully.

**Note:** `--follow` only supports tracking one file path at a time. Do not use it to track multiple files simultaneously or the entire history of a renamed directory.

## 4. Displaying Old and New Paths with --name-status

Reading commit messages alone may not tell you which rename Git detected. Add `--name-status` to display statuses and paths:

```bash
git log --follow --name-status -- src/PaymentService.java
```

Abbreviated example output:

```text
commit d4e5f6a
Author: Developer
Date:   2026-05-12

    refactor: rename payment service

R100    src/LegacyPayment.java    src/PaymentService.java

commit a1b2c3d

    fix: handle empty order

M       src/LegacyPayment.java
```

Common status codes:

| Symbol | Meaning |
|---|---|
| `A` | File added |
| `M` | File modified |
| `D` | File deleted |
| `Rnnn` | Rename detected; `nnn` is the similarity percentage |
| `Cnnn` | Copy detected when copy detection is enabled |
| `T` | Object type or mode changed |

When Git detects a rename, `--name-status` prints both the source and destination paths. This helps you trace back to the old name to inspect pre-rename commits.

You can combine this with a short commit format and date:

```bash
git log --follow --name-status --format="%h %ad %s" --date=short -- src/PaymentService.java
```

This makes it easy to scan which commits modified the file and which commit performed the rename. If you want to see change sizes instead of status codes:

```bash
git log --follow --stat -- src/PaymentService.java
```

## 5. Inspecting the Commit That Performed a Rename

After finding a commit with status `Rnnn`, inspect that commit:

```bash
git show --summary --find-renames <commit>
```

Example output may contain:

```text
 rename src/LegacyPayment.java => src/PaymentService.java (100%)
```

To inspect path statuses of a commit relative to its parent:

```bash
git diff-tree --no-commit-id -r -M --name-status <commit>^ <commit>
```

`-M` enables rename detection in the comparison. For merge commits, specify which parent to compare against because merges can have multiple parents. `<commit>^` defaults to the first parent.

You can also view contents before and after the rename with `git show`:

```bash
# Contents of the old path in the parent before the rename commit.
git show <commit>^:src/LegacyPayment.java

# Contents of the new path in the rename commit.
git show <commit>:src/PaymentService.java
```

These two commands are helpful when verifying whether a file was moved nearly intact or renamed alongside a major rewrite.

## 6. Adjusting the Detection Threshold with -M

Git uses a similarity threshold to decide whether a delete/add pair counts as a rename. With `-M` or `--find-renames`, you can specify a percentage threshold.

Example using the default or 50% threshold:

```bash
git log --follow -M50% --name-status -- src/PaymentService.java
```

If the file changed substantially in the same commit as the rename, try a lower threshold:

```bash
git log --follow -M30% --name-status -- src/PaymentService.java
```

If you want to require files to be very similar:

```bash
git log --follow -M90% --name-status -- src/PaymentService.java
```

Practical implications:

- **Lower threshold:** Git detects renames more easily even after heavy edits; conversely, it may falsely pair two unrelated files.
- **Higher threshold:** Git only detects renames when content is very similar; conversely, it may miss genuine renames that included significant edits.
- **Default threshold:** typically 50% when rename detection is enabled without an explicit value.

Test a few thresholds and verify against actual contents. No single threshold fits every repository; source files, documentation, generated files, and large structured files behave differently.

## 7. Tracking Across Multiple Renames

A file can be renamed multiple times:

```text
src/LegacyPayment.java
        |
        | rename
        v
src/PaymentService.java
        |
        | move
        v
services/payment/PaymentService.java
```

If Git detects the consecutive renames, `--follow` can trace backward from the current path to older names:

```bash
git log --follow --name-status -- services/payment/PaymentService.java
```

To review old paths and transition commits:

```bash
git log --follow --name-status --format="%h %s" -- services/payment/PaymentService.java
```

Whenever you see an `Rnnn` line, note both paths and the corresponding commit. You can inspect each commit with `git show` to verify the change. If one rename step is not detected, try `-M` with an appropriate threshold and check the diff between parent and commit.

If a file was split into multiple new files, or multiple files were merged into one, history is no longer a one-to-one rename chain. `--follow` may not capture the full lineage. In that case, trace the transition commits using `git log`, `git grep`, `git blame`, and inspect parent contents directly.

## 8. Distinguishing Rename and Copy

Rename means an old path is replaced by a new path in the comparison. Copy means a new path is created with similar content while the source file continues to exist.

`--follow` focuses on tracing a single path's history across renames. It is not a general-purpose tool for tracking all copies of content.

To enable copy detection in diff/log, you can use:

```bash
git log --find-copies --find-copies-harder --name-status -- src/NewHandler.java
```

`--find-copies-harder` instructs Git to consider unchanged files as copy sources as well, which can be resource-intensive in large repositories. Copy detection only surfaces copy relationships in diffs; it does not give the new file the commit history of the source file.

If you need to find the origin of copied code, search for its content or distinctive strings across history:

```bash
git log --all -S"calculateTotal" --oneline -- '*.java'
git log --all -G"calculateTotal\(" --oneline -- '*.java'
```

`-S` finds commits that change the occurrence count of a string; `-G` finds diffs with lines matching a regex. These two options complement content-origin tracing, though they do not replace rename detection.

## 9. Tracing History After File Deletion

If a file has been deleted from the current version, you can still query its history using its last known path:

```bash
git log --follow --name-status -- src/OldPayment.java
```

The deletion commit appears with status `D`; earlier commits can still be shown if Git detects renames in older history.

To view the file's contents at the commit right before deletion:

```bash
git show <commit-before-delete>:src/OldPayment.java
```

Or view contents at a specific commit:

```bash
git show <commit>:<path-at-that-commit>
```

The path must match the name stored in that commit's tree. The current filename does not necessarily exist in older commits.

## 10. Scope and Limitations of --follow

`--follow` is very useful, though it has several important limitations:

- **Single path only:** `--follow` works on only one file at a time; do not pass multiple pathspecs.
- **Does not track directories as objects:** Git stores trees and file paths; a directory has no standalone rename identity to follow.
- **Similarity-based detection:** renames accompanied by major refactoring may fall below the threshold.
- **Not copy lineage:** a newly copied file does not automatically inherit the source file's commit history.
- **Complex merges:** when renames occur across multiple branches or inside merge commits, inspect individual parents and the graph rather than relying on a single log line.
- **History scoped by ref:** by default the command reads history reachable from `HEAD`; to inspect another branch, specify the ref explicitly.

In particular, avoid using `--first-parent` if your goal is to see every commit on side branches. That option only follows the first parent and can hide history created on merged branches.

## 11. Troubleshooting When Git Fails to Detect a Rename

If output only shows `A` and `D` instead of `Rnnn`, check in order:

1. Confirm the right branch/ref and exact current path.
2. Inspect the suspected commit's diff with `git show --summary --find-renames <commit>`.
3. Try a lower threshold with `git log --follow -M30% --name-status -- <path>`.
4. Verify whether the old and new files truly share the same origin or merely have similar contents.
5. If multiple files were split or combined, consider copy detection or content search with `-S`/`-G`.
6. If merges are involved, inspect each parent of the merge commit and related branches.

Do not drop the threshold too low just to force Git to print `R`. A false rename match can lead you into the history of a completely different file. Always verify via contents, commit details, and change context.

## 12. Example Workflow: Investigating a Bug in a Renamed File

Suppose a payment-processing bug appears in `services/payment/PaymentService.java`, and the team suspects the logic already existed when the file was named `LegacyPayment.java`.

### Step 1: View full history from the current path

```bash
git log --follow --oneline -- services/payment/PaymentService.java
```

### Step 2: Inspect the renames

```bash
git log --follow --name-status --format="%h %ad %s" --date=short -- services/payment/PaymentService.java
```

Locate `Rnnn` lines to identify old names and rename commits.

### Step 3: Inspect the suspected commit

```bash
git show --summary --find-renames <rename-commit>
git show <rename-commit>^:src/LegacyPayment.java
git show <rename-commit>:services/payment/PaymentService.java
```

### Step 4: Find the change that introduced the bug

After identifying the old path, inspect commits modifying the logic:

```bash
git log --follow -p -- services/payment/PaymentService.java
```

`-p` shows patches for the commits. You can limit the time window or commit count to keep the log readable:

```bash
git log --follow -p --since="2025-01-01" -- services/payment/PaymentService.java
```

### Step 5: Verify lines of code across versions

Once you locate the relevant commit, run `git show <commit>` or `git blame` on the path at that point in time to see who changed the logic and which branch integrated it.

Combining rename history with patches and commit context yields a far more reliable answer than looking only at the current filename.

## 13. Common Commands

| Goal | Command |
|---|---|
| History across renames | `git log --follow -- path/to/file` |
| Compact history | `git log --follow --oneline -- path/to/file` |
| Show paths and statuses | `git log --follow --name-status -- path/to/file` |
| Show change statistics | `git log --follow --stat -- path/to/file` |
| Show patch per commit | `git log --follow -p -- path/to/file` |
| Adjust rename threshold | `git log --follow -M30% -- path/to/file` |
| Inspect rename commit | `git show --summary --find-renames <commit>` |
| Inspect commit path status | `git diff-tree --no-commit-id -r -M --name-status <parent> <commit>` |
| View content before/after rename | `git show <commit>^:<old-path>` and `git show <commit>:<new-path>` |
| Search changed content | `git log -S"text" --all -- pathspec` or `git log -G"regex" --all -- pathspec` |

## 14. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Git stores a separate rename record in each commit | Git stores snapshots; renames are inferred when comparing trees |
| `git log --follow` tracks every file in a directory | It only supports a single file path at a time |
| Renames are always detected 100% of the time | Git relies on similarity and can miss renames when content changes heavily |
| `R100` means Git has exact rename metadata | It is a detection result indicating 100% similarity in the comparison |
| Lowering the rename threshold is always better | Low thresholds can produce false matches between unrelated files |
| `--follow` finds all copies | It focuses on tracking renames; copy detection is a separate mechanism |
| A new file's history starts at the rename | When renames are detected, `--follow` can display commits prior to the current name |
| Missing older commits mean history is lost | It may be due to wrong ref/path, undetected rename, or truncated history |

## 15. Summary

To trace a file's history across renames, start with:

```bash
git log --follow --name-status -- path/to/current-file
```

Git infers renames from snapshots and content similarity rather than dedicated rename metadata. Use `-M` to adjust the threshold, `--name-status` to see old/new paths, `--stat` or `-p` to inspect the scope of changes, and `git show --summary --find-renames` to inspect the rename commit itself.

`--follow` applies to a single file and does not track copies or directories as units. When a rename is not detected, check the ref, path, similarity threshold, commit details, and merge parents. Always verify results against actual file contents before drawing conclusions about a file's history.

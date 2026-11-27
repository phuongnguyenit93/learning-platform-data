# Splitting a Large Change Into Purpose-Built Commits Using Partial Staging

While working on a feature, you may edit several files and accidentally mix multiple kinds of work in the same working tree: bug fixes, function renames, added tests, documentation updates, and new behavior. If you stage everything and commit all at once, the history becomes hard to review and hard to partially revert.

Git lets you selectively add parts of your changes to the **index** using `git add -p` (patch mode). You can stage certain hunks or lines, commit them for one purpose, and then stage the remaining changes for the next commit. This technique helps break a large change into small, understandable commits that can be verified independently.

## 1. Practice Objectives

You will practice on a working tree with interleaved changes and create commits grouped by purpose. For example, while working on a payment flow, you have:

- Extracted validation logic out of a large handler function to improve readability.
- Fixed a bug in negative amount validation.
- Added tests for invalid payment amounts.
- Added a tax validation rule for a new feature.
- Updated API documentation.

These changes may sit inside the same file or span multiple files. The goal is to produce clearly scoped commits, such as:

1. `Refactor payment validation` — code restructuring only, preserving existing behavior.
2. `Fix negative payment amount` — the bug fix and corresponding regression tests.
3. `Add tax validation` — the new behavior, tests, and related documentation.

You do not need to create exactly three commits in every project. Group changes by purpose and dependencies: each commit should clearly explain what it changes and why.

## 2. Understanding the Two Diff Areas Before Partial Staging

Git tracks three states you need to watch when preparing a commit:

- `HEAD`: the snapshot of the current commit.
- Index: the staged content that will go into the next commit.
- Working tree: the current content on disk.

Two essential diff commands:

```bash
# Unstaged changes: working tree compared to index
git diff

# Staged changes: index compared to HEAD
git diff --cached
```

For example, if a file contains both staged edits and unstaged edits, `git diff --cached` shows only what is slated for the next commit; `git diff` shows the remainder relative to the index.

Run an overview check before taking action:

```bash
git status --short
git diff --stat
git diff
git diff --cached
```

Do not start partial staging until you understand what changes are in your working tree. If there are leftover changes from earlier work, commit or store them separately so they do not mix into the current commit sequence.

## 3. Creating Test Changes With Multiple Purposes

Suppose the repository contains these files:

```text
src/payment.js
tests/payment.test.js
docs/payment-api.md
```

In `src/payment.js`, you renamed a variable and extracted a validation helper while also adding a tax-check branch. In the test file, you added both tests for the negative-amount bug and tests for the tax rule. The API documentation relates only to the tax feature.

Inspect all changes:

```bash
git status
git diff -- src/payment.js
git diff -- tests/payment.test.js
git diff -- docs/payment-api.md
```

When different changes reside in the same file, do not stage the entire file with `git add src/payment.js`, as that puts every change in the file into the index. Use patch mode to pick only the parts you need.

## 4. Selecting Hunks With git add -p

Syntax:

```bash
git add -p [<pathspec>...]
```

Without a pathspec, Git walks through all eligible changes in the working tree. Specifying paths focuses the session on specific files:

```bash
git add -p -- src/payment.js tests/payment.test.js
```

Git displays one hunk (a group of changed lines) at a time and asks whether you want to stage it. Press `y` to stage the hunk, or `n` to skip it and move to the next hunk.

Common keys in interactive mode:

| Key | Meaning |
|---|---|
| `y` | Stage the currently displayed hunk into the index |
| `n` | Do not stage this hunk; move to the next hunk |
| `q` | Quit, keeping previously staged hunks |
| `a` | Stage this hunk and all remaining hunks in the current file |
| `d` | Skip this hunk and all remaining hunks in the current file |
| `s` | Split the hunk into smaller hunks if possible |
| `e` | Open the patch for manual editing |
| `?` | Display help for the available options |

Depending on your Git version and interactive mode, navigation or hunk search keys may also be available. Type `?` at the prompt to see the exact list supported by your version.

### Selecting Changes by Purpose

For example, first you want to create the refactoring commit. Run:

```bash
git add -p -- src/payment.js tests/payment.test.js
```

At each hunk, select only the lines belonging to function extraction and variable renaming. Skip hunks that add tax rules. In the test file, select changes that solely support the refactoring if needed to verify existing behavior is preserved; skip the tax tests because they belong to the later feature commit.

Once done selecting, review the index:

```bash
git diff --cached
git diff
```

Read `git diff --cached` as the draft of the first commit. If it includes tax logic or API docs, unstage the parts that do not belong to that purpose.

## 5. Splitting a Large Hunk With the s Key

Git groups nearby changed lines into a single hunk to provide enough context. One hunk can contain multiple independent changes. If Git displays:

```text
@@ -20,5 +20,6 @@ function calculatePayment(order) {
-  const subtotal = getSubtotal(order);
-  if (subtotal < 0) throw new Error("Invalid subtotal");
+  const amount = getSubtotal(order);
+  if (amount < 0) throw new Error("Invalid subtotal");
   const fee = calculateFee(order);
-  return subtotal + fee;
+  const tax = calculateTax(order);
+  return amount + fee + tax;
 }
```

This hunk mixes refactoring and the tax feature. At the patch prompt, enter:

```text
s
```

Git will attempt to split the hunk into smaller pieces based on gaps between changes. You can then stage the rename/normalization piece separately and leave the tax logic for a later commit.

Not every hunk can be split. If changed lines are adjacent or interdependent, Git may report that it cannot split the hunk. In that case, consider editing the patch manually with `e`, or breaking the edits in the working tree into steps that are easier to stage separately.

## 6. Editing a Patch Manually With e

When `s` cannot split a hunk the way you want, the `e` key opens the patch in your editor so you can pick individual lines. This approach is powerful, though it requires understanding the unified diff format.

In a patch:

- Lines starting with a space are context lines, used to locate where the patch applies.
- Lines starting with `-` are old content being replaced or deleted.
- Lines starting with `+` are new content being added.
- Lines starting with `@@ ... @@` are hunk headers describing the hunk range.

When editing, keep the necessary context lines and retain only the changes you want to stage. For a replacement change, ensure the old and new lines in the patch describe a valid transformation. If the patch is malformed or fails to apply, Git may reject that hunk; re-check the index and working tree after closing the editor.

Because manual patch editing can easily produce an invalid intermediate version, prefer `s` whenever possible. After using `e`, always inspect:

```bash
git diff --cached
git diff
```

Ensure the index holds the exact lines to commit and the working tree still retains the remaining lines. Do not edit hunk headers or line numbers unless you understand their effect.

## 7. Creating the First Commit and Continuing With the Rest

After selecting the hunks for the first purpose, inspect the content and create the commit:

```bash
git diff --cached --check
git diff --cached
git status --short
git commit -m "Refactor payment validation"
```

`git diff --cached --check` checks for common whitespace errors in the staged changes. `git commit` creates a commit from the current index; unstaged changes in the working tree remain intact afterward.

Check status after committing:

```bash
git show --stat --oneline HEAD
git status --short
git diff
git diff --cached
```

The changes for the negative-amount bug and the tax feature remain in the working tree. Next, select the changes for the second commit:

```bash
git add -p -- src/payment.js tests/payment.test.js
git diff --cached
git diff
git diff --cached --check
git commit -m "Fix negative payment amount"
```

Finally, stage the tax feature and documentation:

```bash
git add -p -- src/payment.js tests/payment.test.js
git add docs/payment-api.md
git diff --cached
git diff --cached --check
git commit -m "Add tax validation"
```

In the final step, `git add docs/payment-api.md` is appropriate if every change in that document belongs to the tax feature. If the documentation file also contains mixed purposes, use `git add -p` for it as well.

## 8. When to Use git add -p, git add -e, and Path-Based git add?

| Staging method | Best used when | Limitations |
|---|---|---|
| `git add <path>` | All changes in the file belong to the same commit | Stages unrelated changes in the same file |
| `git add -p` | You want to pick individual hunks across one or more files | A hunk may contain tightly mixed changes that are hard to split |
| `git add -e` | You need to edit a patch to select individual lines inside a hunk | Easy to produce an invalid patch if structure is edited incorrectly |
| `git add -A` | You want to stage every change across the repository | Usually unsuitable when splitting commits by purpose |

You can invoke edit mode directly:

```bash
git add -e -- src/payment.js
```

This command opens the patch for the chosen path so you can edit the patch content. If you only need to pick hunks, `git add -p` is usually easier to control.

## 9. Unstaging Partially if You Selected by Mistake

If you accidentally staged a hunk, you can remove just that hunk from the index using patch mode:

```bash
git restore --staged -p -- src/payment.js
```

Git shows the differences between `HEAD` and the index so you can pick which hunks to restore. Choose `y` for the hunk you want to unstage. The working tree remains untouched.

Traditional equivalent:

```bash
git reset -p -- src/payment.js
```

Both commands adjust only the index for the chosen hunks without deleting edits on disk. Re-check afterward:

```bash
git diff --cached -- src/payment.js
git diff -- src/payment.js
```

If you want to unstage an entire file, use:

```bash
git restore --staged -- src/payment.js
```

Do not use `git restore --worktree` when your goal is only to unstage; that option modifies file contents in the working tree.

## 10. Keeping Commits Independent and Testable

Splitting commits is not only about making history tidy. Each commit should leave the codebase in a state that is understandable and, whenever possible, independently testable.

Example of a sound ordering:

1. Refactor validation logic without changing behavior.
2. Fix the negative-amount validation bug and add regression tests.
3. Add the tax rule, tests, and API documentation.

If a new feature depends on a refactoring, the refactoring commit should come before the feature commit. If tests only pass once the new behavior exists, place the tests in the same commit as that behavior. Avoid creating an initial commit that does not compile or leaves tests failing without a clear reason.

After each commit, you can inspect:

```bash
git show --stat --oneline HEAD
git show --format=fuller --no-ext-diff HEAD
```

If you need to test the exact staged snapshot before committing, you can use `git stash push --keep-index` to temporarily stash unstaged changes, run tests against the current index, and then restore the rest with `git stash pop`. Only do this when you understand the working tree state and verify the stash afterward so unstaged changes are not forgotten.

## 11. Common Pitfalls When Partial Staging

### Staging an Entire File Unintentionally

You run `git add src/payment.js` after already selecting a few hunks. That command stages the entire current state of the file, including earlier changes you left unstaged. Use `git add -p` for subsequent selections and inspect `git diff --cached` before committing.

### A Hunk Contains Multiple Purposes and Cannot Split

Git cannot split with `s` because the edits are too close together. Use `e` if you understand patch syntax, or separate the code edits into independent steps in the working tree and re-run `git add -p`.

### Missing Required Parts in a Commit

You stage the code but forget to stage the necessary tests or documentation. Before committing, read the full `git diff --cached` output and verify the file list with `git status --short`. If the commit was created locally and not yet shared, you can amend it with `git commit --amend`; if already shared, consider creating a follow-up commit according to team workflow.

### Using git commit -a After Patch Selection

`git commit -a` automatically stages changes in tracked files before committing, which can pull in changes you intentionally left behind. When splitting commits via patch mode, use plain `git commit` to commit only the current index.

### New Files or Binary Files

Patch mode is primarily useful for text diffs of tracked files. Binary files cannot be split line by line like text files. For a new untracked file, stage by path if the entire file serves one purpose; if its contents need to be split, structure the content or separate files appropriately before staging.

## 12. Pre-Commit Verification Checklist

Before every commit, run a consistent check:

```bash
# What will go into the commit
git diff --cached

# What remains in the working tree, unstaged
git diff

# File status list
git status --short

# Check whitespace in staged changes
git diff --cached --check
```

Ask yourself three questions:

1. Do all changes in the index serve a single purpose?
2. Does this commit contain enough code, tests, and documentation to understand and verify the change?
3. Are any local config files, secrets, build outputs, or unrelated changes accidentally staged?

If any answer is unclear, continue adjusting the index with `git add -p` or `git restore --staged -p` before committing.

## 13. Comprehensive Practice Exercise

In a test repository, create a baseline commit and then edit at least two text files for three distinct purposes: refactoring, bug fixing, and adding a feature. Make changes in at least one file interleave within the same hunk.

1. Use `git status`, `git diff`, and `git diff --stat` to survey all changes.
2. Run `git add -p` and stage only the hunks belonging to the refactoring.
3. If a hunk contains both refactoring and feature work, try `s`; if it cannot be split, use `e` in your editor to select the right lines.
4. Use `git diff --cached` and `git diff` to confirm the index and working tree hold two distinct sets of changes.
5. Run `git diff --cached --check`, create the refactoring commit, and inspect it with `git show --stat HEAD`.
6. Next, stage the bug fix along with its regression tests and create the second commit.
7. Stage the feature along with its tests and documentation, and create the third commit.
8. Intentionally mis-stage a hunk in the test environment, then use `git restore --staged -p` to unstage that hunk while keeping the working tree contents intact.
9. Run `git log --oneline -3` and explain the purpose of each commit.

You have completed the exercise when you have created separate, purpose-driven commits without losing the remaining working tree changes and can verify each commit's contents with `git show` or `git diff --cached` prior to committing.

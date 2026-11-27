# Shelving Only Partial Changes with --patch, --staged, and --keep-index

During development, there are times when you are working on multiple things simultaneously and only need to temporarily shelve part of them to handle another task. For example, you have finished and staged one part for a commit, yet still have a few unfinished experimental lines. Or you only want to shelve specific sections within the same file without affecting the rest.

The `git stash` command can temporarily save changes so the working tree fits the next task. In addition to shelving all changes, Git supports selecting partial changes with `--patch`, shelving only staged content with `--staged`, or keeping staged content in the working tree while shelving unstaged content with `--keep-index`.

These three options solve different needs. Understanding them clearly helps you switch working contexts without losing unfinished work or accidentally including unrelated content in a commit.

## 1. Reviewing the working tree and staging area

Before using partial stash, you need to distinguish between content in the working tree and in the index.

| Area | Content | Verification command |
| --- | --- | --- |
| HEAD | Current commit of the branch | `git log --oneline -5` |
| Index (staging area) | Content selected to include in the next commit | `git diff --cached` |
| Working tree | Current file content on disk | `git diff` |

For example, you modify two files:

- `src/PaymentService.java`: input validation has been staged.
- `docs/payment-flow.md`: partially edited and not yet staged.

Check:

~~~bash
git status
git diff --cached
git diff
~~~

`git diff --cached` displays the differences between the index and HEAD. `git diff` displays the differences between the working tree and the index. A single file can contain both staged and unstaged changes if you continue editing after running `git add`.

When you want to temporarily shelve a part, determine accurately which part should be saved into the stash and which part must remain in the working tree.

## 2. Basic stash syntax

Common syntax:

~~~bash
git stash push -m "Work description"
~~~

This command saves tracked changes currently in the index and working tree into a stash entry, then removes them from the working tree according to default behavior.

View the stash list:

~~~bash
git stash list
~~~

View the contents of the latest stash:

~~~bash
git stash show --stat 'stash@{0}'
git stash show -p 'stash@{0}'
~~~

Each stash entry can be referenced by names such as `stash@{0}`, `stash@{1}`. `stash@{0}` is the newest entry. When creating a new stash, the indices of older entries can shift.

By default, stash does not include files not yet tracked by Git. If you need to shelve those files too, use `-u` or `--include-untracked`. The `-a` or `--all` option also includes ignored files. Think carefully before putting configuration files or local data into a stash.

## 3. Selecting individual changes with --patch

### 3.1. How does --patch work?

The `--patch` option lets you select individual hunks (change chunks) to put into a stash:

~~~bash
git stash push --patch -m "Temporarily shelve partial changes"
~~~

Git opens interactive mode and prompts you sequentially for each hunk to ask whether you want to shelve it. You can decide which hunks to keep in the stash and which hunks to leave in the working tree.

Some commonly used keys in the interactive prompt:

| Key | Meaning |
| --- | --- |
| `y` | Shelve the current hunk |
| `n` | Do not shelve the current hunk |
| `s` | Split the hunk into smaller parts if possible |
| `e` | Manually edit the patch before applying |
| `q` | Quit interactive mode |
| `?` | View help for options |

Depending on the Git version and context, the list of options may differ. Read the prompt guide shown directly in the terminal before entering input.

Once finished, the selected hunks are saved into the stash and removed from the working tree. Unselected hunks remain.

### 3.2. Example: selecting specific hunks in the same file

Suppose you are editing `src/PaymentService.java` with three changes, and all three hunks are currently unstaged:

1. Add an empty payment code check — completed.
2. Experiment with a new logging approach — incomplete.
3. Adjust variable naming — undecided.

You need to temporarily shelve only the logging part to continue working on another task. Run:

~~~bash
git stash push --patch -m "Temporarily shelve logging experiment"
~~~

When Git prompts for each hunk:

- Choose `n` for the payment code check to keep it in the working tree.
- Choose `y` for the logging part to put it into the stash.
- Choose `n` for the variable renaming if you want to keep it in the working tree.

Then check:

~~~bash
git status
git diff
git stash list
git stash show -p 'stash@{0}'
~~~

The expected result is that the logging hunk is in the stash, while the unselected hunks remain in the working tree. Do not rely solely on the success message; inspect the diff to confirm the exact content was shelved.

### 3.3. --patch keeps the index by default

`git stash push --patch` implicitly enables `--keep-index`. That means the index state is preserved while the selected hunks are temporarily saved. If you need behavior that does not keep the index, you can use `--no-keep-index` to override this default:

~~~bash
git stash push --patch --no-keep-index -m "Temporarily shelve partial changes"
~~~

For beginners, it is best to use the default first and check `git status`, `git diff --cached`, and `git diff` after the operation. Only use `--no-keep-index` when you clearly understand how staged and unstaged changes will be handled.

### 3.4. Selecting hunks from staged changes

You can combine `--patch` with `--staged` to interactively select parts from staged changes:

~~~bash
git stash push --staged --patch -m "Temporarily shelve staged subset"
~~~

This approach is useful when you have staged many changes but only want to temporarily shelve a few hunks. Read each choice in the interactive prompt and re-check the index after finishing.

## 4. Shelving only staged changes with --staged

### 4.1. What does --staged do?

The `--staged` option puts only changes already in the index into the stash:

~~~bash
git stash push --staged -m "Temporarily shelve staged changes"
~~~

Unstaged changes in the working tree are kept. This option is suitable when you have selected part of your content to prepare a commit, yet want to temporarily shelve that exact part, for example to switch to handling an urgent task.

`--staged` has been available since Git 2.35. If your Git version does not recognize this option, check:

~~~bash
git --version
git stash push -h
~~~

On older versions, you can use alternatives such as stashing by pathspec or temporarily staging/moving content according to an appropriate workflow.

### 4.2. Example: shelving staged changes, keeping unstaged changes

Suppose you edit the same file:

- Part A: fix payment validation condition and already ran `git add`.
- Part B: add diagnostic logs, not ready to commit yet.

Check beforehand:

~~~bash
git status
git diff --cached
git diff
~~~

Shelve only the staged part:

~~~bash
git stash push --staged -m "Temporarily shelve staged validation"
~~~

Then check:

~~~bash
git status
git diff
git diff --cached
git stash show -p 'stash@{0}'
~~~

The staged part is saved into the stash. The unstaged part remains in the working tree so you can edit or commit it for another purpose. If a single file has both staged and unstaged content, inspect `git diff --cached` and `git diff` separately afterward to confirm both parts were handled as expected.

When restoring the stash, you may need `--index` to recover the original staging state. See the restore section below.

### 4.3. Distinguishing --staged from --keep-index

These two options are often confused because both relate to the index, yet their purposes are opposite:

- `--staged`: shelves the staged part into the stash; the unstaged part is kept.
- `--keep-index`: keeps the staged part in place; shelves the unstaged part into the stash.

Identify which part needs to be temporarily shelved before choosing an option. If you pick the wrong one, the content may still exist in the stash or working tree, just not in the state you expect.

## 5. Keeping staged changes with --keep-index

### 5.1. What does --keep-index do?

The `--keep-index` option keeps staged changes in the index and working tree, while stashing unstaged changes:

~~~bash
git stash push --keep-index -m "Temporarily shelve unstaged changes"
~~~

This is a common approach when you want to test only the staged part before committing. Unstaged changes are shelved away so they do not affect the test run.

If the same file has both staged and unstaged changes, `--keep-index` keeps the staged version in the index and working tree; the unstaged difference is shelved into the stash. After the command, `git diff --cached` shows what will be committed, while `git diff` helps confirm no unexpected unstaged edits remain.

Example:

1. Edit multiple parts across the project.
2. Stage only the files or hunks you want to commit.
3. Stash the unstaged part with `--keep-index`.
4. Run tests on the remaining state.
5. Restore the stash to continue the unfinished work.

### 5.2. Example: testing staged changes

Suppose you are doing two things:

- Fixed payment validation logic and staged it.
- Added logs to investigate a bug, unstaged.

View status:

~~~bash
git status
git diff --cached
git diff
~~~

Shelve the unstaged part while keeping the staged part:

~~~bash
git stash push --keep-index -m "Temporarily shelve experimental logs"
~~~

Now the working tree holds the staged part. Run tests:

~~~bash
./gradlew test
~~~

The test command is just an example for a Gradle project; use the test command appropriate for your actual repository.

If the tests pass, you can commit the staged part:

~~~bash
git commit -m "Validate payment amount"
~~~

Then restore the shelved work:

~~~bash
git stash pop
~~~

If the tests fail, you can still edit the staged part or review the diff. The stash of unstaged changes remains stored separately for later restoration.

### 5.3. --keep-index is not a commit

`--keep-index` does not create a commit and does not turn staged content into a shared version. It only keeps content in the index and working tree so you can continue working or testing.

If you want to record a milestone in history, create a commit after verification. Stash is a temporary holding place, not a substitute for commits with clear messages and history.

## 6. Comparing the three options

| Option | What is shelved | What is kept | How selection works |
| --- | --- | --- | --- |
| `--patch` | Interactively selected hunks | Unselected hunks; index is kept by default | Pick individual change chunks |
| `--staged` | Staged content | Unstaged content in the working tree | Shelve what was selected for commit |
| `--keep-index` | Unstaged content | Staged content in the index and working tree | Keep commit-ready changes for testing |

A quick way to remember:

- Want to pick chunks yourself: use `--patch`.
- Want to shelve staged changes: use `--staged`.
- Want to keep staged changes and shelve the rest: use `--keep-index`.

Avoid combining multiple options just because you want a “partial stash”. Identify your goal and use combinations supported by Git. `--staged` can be combined with `--patch`; `--patch` implies `--keep-index` by default, which can be overridden with `--no-keep-index`.

## 7. Shelving changes from specific files with pathspec

Besides selecting by hunk, Git allows restricting a stash by path:

~~~bash
git stash push -m "Temporarily shelve payment docs" -- docs/payment-flow.md
~~~

The command only shelves changes belonging to `docs/payment-flow.md`. Other files not matching the pathspec remain in the working tree.

You can specify multiple paths:

~~~bash
git stash push -m "Temporarily shelve two files" -- src/PaymentService.java docs/payment-flow.md
~~~

Pathspecs can be combined with `--patch` to limit which files are prompted interactively:

~~~bash
git stash push --patch -m "Select part of file" -- src/PaymentService.java
~~~

Use `--` before pathspecs to clearly separate options from filenames, especially when a path name might start with a hyphen.

## 8. Viewing and restoring partial stashes

### 8.1. Listing and inspecting contents

~~~bash
git stash list
git stash show --stat 'stash@{0}'
git stash show -p 'stash@{0}'
~~~

`git stash show -p` displays the stash diff so you can verify the shelved content. If there are multiple stashes, select the right entry by message and creation time, rather than assuming `stash@{0}` is always the work you need to restore.

### 8.2. Restoring with apply

~~~bash
git stash apply 'stash@{0}'
~~~

`apply` applies changes from the stash into the working tree while keeping the entry in the list. This is the right choice when you want to verify the result before deciding to delete the stash.

To attempt restoring the saved index state as well:

~~~bash
git stash apply --index 'stash@{0}'
~~~

The `--index` option asks Git to attempt restoring the staging state too. If there are conflicts or incompatible current changes, the operation may not complete as intended. Check `git status` and the diff after applying.

### 8.3. Restoring with pop

~~~bash
git stash pop 'stash@{0}'
~~~

`pop` applies the stash and deletes the entry from the list if the application succeeds. If a conflict occurs, the stash is typically kept so you can resolve it and retry.

Do not use `pop` when you are unsure which entry is selected or when you want to keep the stash entry for reference. When safety is needed, use `apply`, verify the result, and then `drop`.

### 8.4. Deleting a stash after verification

View the list:

~~~bash
git stash list
~~~

Delete a specific entry:

~~~bash
git stash drop 'stash@{0}'
~~~

This command deletes the reference to the specified stash entry. Run it only after you are sure the changes have been restored or are no longer needed. Avoid running `git stash clear` out of habit because it deletes the entire stash list.

## 9. Handling conflicts when applying a stash

A stash was created at an earlier repository state. If you modified the same lines on the current branch, Git may not be able to merge automatically when applying the stash.

Resolution workflow:

1. Check status with `git status`.
2. Open conflicted files and choose the correct content.
3. Stage resolved files with `git add`.
4. Run tests and inspect the diff.
5. Keep or delete the stash depending on the application outcome.

Example:

~~~bash
git stash apply 'stash@{0}'
git status
~~~

If conflicts occur, resolve each file and then check:

~~~bash
git diff
git diff --cached
git status
~~~

If you used `apply`, the entry remains in the list. If you used `pop` and a conflict occurred, Git typically keeps the entry so you do not lose the temporary save.

When a stash contains staged changes and you want to keep that state, consider `git stash apply --index`. If you only need the content back in the working tree and will re-stage manually, use regular `apply` and verify carefully.

## 10. Limitations to remember

- **Stash is temporary storage in the local repository:** it is not automatically sent to a remote and does not replace backups or commits.
- **Untracked files are not saved by default:** use `-u` if you want to include them in the stash; `-a` also includes ignored files.
- **Patch only selects changes Git recognizes:** binary files or untracked files are not suitable for standard text hunk selection.
- **Options can affect the index state:** always check `git status`, `git diff`, and `git diff --cached` after stashing.
- **Applying a stash can cause conflicts:** a stash is not guaranteed to apply cleanly on every branch.
- **New stashes shift reference order:** the `stash@{0}` entry can change after every stash creation or deletion.
- **Do not use stash as long-term work storage:** if a piece of work is complete and stands on its own, create a commit on an appropriate branch.

## 11. Comprehensive example: keeping staged changes to test, shelving the rest

You are editing a payment feature and have three groups of changes:

- Fix amount validation — staged.
- Add edge-case tests — staged.
- Logging experiment — unstaged.

You want to run tests with only the staged part, then continue with the logging part.

**Step 1 — Check changes**

~~~bash
git status
git diff --cached
git diff
~~~

**Step 2 — Shelve the unstaged part**

~~~bash
git stash push --keep-index -m "Temporarily shelve payment logs"
~~~

**Step 3 — Check the remaining state**

~~~bash
git status
git diff --cached
git diff
~~~

The index still holds the amount fix and tests. The logging part has been shelved.

**Step 4 — Run tests on the staged part**

~~~bash
./gradlew test
~~~

If the tests pass, create a commit:

~~~bash
git commit -m "Validate payment amount"
~~~

**Step 5 — Restore the logging part**

~~~bash
git stash list
git stash pop
~~~

Check again:

~~~bash
git status
git diff
~~~

The logging part is brought back into the working tree for further editing. If it is no longer needed, you can discard that part according to your workflow after verifying its content.

## 12. Quick reference table

| Goal | Command |
| --- | --- |
| Select hunks to stash | `git stash push --patch -m "message"` |
| Stash only staged changes | `git stash push --staged -m "message"` |
| Keep staged, stash unstaged | `git stash push --keep-index -m "message"` |
| Select hunks from staged changes | `git stash push --staged --patch -m "message"` |
| Stash specific paths | `git stash push -m "message" -- path/to/file` |
| View stash list | `git stash list` |
| View stash diff | `git stash show -p 'stash@{0}'` |
| Apply and keep stash | `git stash apply 'stash@{0}'` |
| Apply including index state | `git stash apply --index 'stash@{0}'` |
| Apply then delete if successful | `git stash pop 'stash@{0}'` |
| Delete one stash | `git stash drop 'stash@{0}'` |

## 13. Summary

`git stash --patch`, `--staged`, and `--keep-index` give you finer control over which changes are temporarily shelved. `--patch` is used to pick individual hunks, `--staged` shelves the staged part, while `--keep-index` keeps the staged part in place and shelves the unstaged part.

Before and after each operation, check `git status`, `git diff`, and `git diff --cached`. When restoring, pick the right stash entry, weigh `apply` versus `pop`, and use `--index` if you need to recover the staging state. This workflow helps you switch tasks flexibly, preserve work in progress, and avoid mixing unrelated changes into the same commit.

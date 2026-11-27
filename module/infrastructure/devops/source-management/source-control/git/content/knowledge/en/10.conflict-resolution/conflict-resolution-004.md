# Finding Conflicted Files with git status and git diff

When merging, rebasing, cherry-picking, or applying changes from elsewhere, Git may encounter edits it cannot combine automatically. For example, two branches might modify the same section in `LoginService.java`, or one branch might delete a file while the other continues editing it. Git marks the affected paths as **unmerged** so the developer can decide the final content.

Before resolving, you need to know exactly which files are in conflict and what kind of conflict each file has. `git status` shows the overall repository state; `git diff` helps filter the list of unmerged paths and inspect the differences that need handling. Combining these two commands helps you scope the work before editing.

## 1. When Does Git Consider a File Conflicted?

While integrating two lines of history, Git attempts to combine changes automatically. If it cannot determine a single unambiguous result, Git retains information about the involved versions in the *index* (staging area) and marks the path as an *unmerged path*.

Some common scenarios:

- **Modifying the same content region:** two branches change overlapping lines in the same file.
- **Adding the same path:** two branches independently create a file with the same name but different content.
- **Deleting and modifying:** one branch deletes a file while the other edits that file.
- **Renaming or moving:** the branches perform rename, delete, or add operations that Git cannot reconcile into a clear outcome.
- **Binary conflict:** both sides modify the same binary file, such as an image or design file, so Git cannot merge content line-by-line as it does with text.

For text content conflicts, the file in the working tree usually contains delimiter markers such as `<<<<<<<`, `=======`, and `>>>>>>>`. However, not all conflicts have these markers. Delete/modify, rename, or binary conflicts may not produce a marker block inside a file. Therefore, Git's unmerged state is the authoritative source for identifying conflicts; searching for markers is only an aid for reading certain types of text conflicts.

## 2. Using git status to Inspect Conflict State

First, run the command in a directory inside the repository:

```bash
git status
```

When a merge operation hits a conflict, the output typically shows the current branch, the operation in progress, and the file groups. For example:

```text
On branch feature/login
You have unmerged paths.
  (fix conflicts and run "git commit")
  (use "git merge --abort" to abort the merge)

Changes to be committed:
        new file:   src/login/Validator.java

Unmerged paths:
  (use "git add/rm <file>..." as appropriate to mark resolution)
        both modified:   src/login/LoginService.java
        deleted by them: src/login/LegacyLogin.java
        both added:      src/config/security.yml
```

The `Unmerged paths` section lists the paths Git could not merge. In the example above, there are three files to examine. `Changes to be committed` is the group of staged changes; this group may contain files that have already been resolved or independent changes, so it is not equivalent to the list of remaining conflicts.

### Viewing the Short Status

For compact output that is easy to scan or include in notes, run:

```bash
git status --short
```

Example:

```text
M  README.md
UU src/login/LoginService.java
UD src/login/LegacyLogin.java
AA src/config/security.yml
```

The first two characters on each line represent the status in the index and the working tree. For unmerged codes, you can read them as follows:

| Code | Meaning |
|---|---|
| `DD` | Both sides deleted the file |
| `AU` | File added on the current side, not yet merged with the other side |
| `UD` | The other side deleted the file |
| `UA` | The other side added the file |
| `DU` | The current side deleted the file |
| `AA` | Both sides added the same path |
| `UU` | Both sides modified the file |

These codes describe conflict states in the short format of `git status`. The letter `U` means *updated but unmerged*. The line `M  README.md` in the example is a normal staged change, not an unmerged code.

The terms "current side" and "other side" must be understood in the context of the active operation. In a merge, `ours` is usually the branch you are on and `theirs` is the branch being merged in. In a rebase, the actual meaning of `ours` and `theirs` can confuse newcomers: `ours` is typically the target/upstream branch onto which commits are being replayed, while `theirs` is the commit from the branch being rebased. Always check the current operation before choosing content from one side.

## 3. Using git diff to Filter the Exact List of Unmerged Files

`git diff` can filter by change status. The `U` filter represents unmerged paths. To retrieve only the names of conflicted files, run:

```bash
git diff --name-only --diff-filter=U
```

Example output:

```text
src/login/LoginService.java
src/login/LegacyLogin.java
src/config/security.yml
```

This is the most useful command when you only need the list of paths still in conflict. It does not include files that are merely modified or normally staged. If there is no output, Git currently has no remaining unmerged paths detected by this command; use `git status` to check whether the merge/rebase operation is finished or still waiting for its completion step.

Some useful variations:

```bash
# Show filenames along with the U filter status.
git diff --name-status --diff-filter=U

# View the diffs of unmerged paths.
git diff --diff-filter=U

# View change statistics for unmerged paths.
git diff --stat --diff-filter=U
```

If you need to inspect a specific path, place the path after `--` so Git treats it as a pathspec, even if the filename contains special characters:

```bash
git diff -- "src/login/LoginService.java"
```

To view the combined diff of a conflicted file, you can use:

```bash
git diff --cc -- "src/login/LoginService.java"
```

The combined diff format shows the lines involved across the conflict sides. For a text file with conflict markers, opening the file directly in an editor also helps clearly read the `<<<<<<<`, `=======`, `>>>>>>>` blocks and the content to choose or combine.

## 4. Distinguishing Conflicted Files from Normal Changes

Not every file shown in `git status` or `git diff` is a conflicted file. A repository can simultaneously contain:

- Unstaged changes in the working tree.
- Staged changes ready to be committed.
- Files untracked by Git.
- Unmerged paths that need resolution.

The following commands serve different purposes:

| Command | Primary content |
|---|---|
| `git status` | Overall state, including branch and file groups |
| `git status --short` | Compact status for each path |
| `git diff` | Differences between the working tree and index for normal changes |
| `git diff --staged` | Staged differences compared to the current commit |
| `git diff --name-only --diff-filter=U` | Names of unmerged paths only |
| `git diff --diff-filter=U` | Diff filtered to unmerged paths |

If your goal is to list files still in conflict, do not use `git diff --name-only` by itself, because that command can list normal changes and make the scope of conflict work look broader than it is. Add `--diff-filter=U`.

## 5. Inspecting a Conflicted File in Detail

After identifying paths with `git status` or `git diff --name-only --diff-filter=U`, you can inspect each file.

### Viewing Conflict Markers in a Text File

For example, `LoginService.java` might contain:

```java
public User authenticate(String username) {
<<<<<<< HEAD
    return userRepository.findByUsername(username);
=======
    return userRepository.findActiveUser(username);
>>>>>>> feature/active-user
}
```

The sections typically mean:

- `<<<<<<< HEAD`: starts the content on one side of the conflict.
- `=======`: separates the two sides.
- `>>>>>>> feature/active-user`: ends the other side; the label usually indicates the source of the change.

If the repository is configured to use the `diff3` or `zdiff3` conflict style, the `|||||||` marker may appear to display the *base* version as well. Do not assume every conflict consists of just two simple lines; read the entire relevant block and the surrounding function or configuration context.

### Comparing the Working Tree Against Each Version in the Index

When you need to see how the current content differs from each side, Git provides options specifically for unmerged paths:

```bash
# Compare against the common base version.
git diff --base -- "src/login/LoginService.java"

# Compare against the ours version.
git diff --ours -- "src/login/LoginService.java"

# Compare against the theirs version.
git diff --theirs -- "src/login/LoginService.java"
```

These commands show the differences between the working tree and each version stored in the index. They are useful when markers in the file are hard to read or when you need to understand which side introduced a change. Remember that `ours` and `theirs` depend on the merge/rebase context as explained above.

## 6. Workflow for Scoping Conflicts

When an integration operation stops due to a conflict, you can proceed step by step:

1. Run `git status` to confirm what state the repository is in and what operation Git reports as pending.
2. Run `git status --short` to quickly scan the status of each path.
3. Run `git diff --name-only --diff-filter=U` to get the exact list of remaining unmerged paths.
4. For each path, check the conflict type in `git status`, open the file if it is text, and use `git diff --cc -- <path>` or the `--base`, `--ours`, `--theirs` options when comparisons are needed.
5. Note the files to handle and decide on the content within the context of the corresponding feature, configuration, or resource.

For example, a team might run the following commands to start inspecting:

```bash
git status
git status --short
git diff --name-only --diff-filter=U
git diff --cc -- "src/login/LoginService.java"
```

After editing and resolving a file, `git add <path>` (or `git rm <path>` if you decide to delete the file) informs Git that the path has been handled. At that point, the path is no longer in the unmerged state. Repeat the check:

```bash
git diff --name-only --diff-filter=U
git status
```

When the filter command no longer lists any paths, read `git status` to see whether a final step to finish the merge, rebase, or cherry-pick is still pending. Do not assume the entire operation is complete solely because the unmerged list is empty.

## 7. Additional Checks and Common Pitfalls

### Checking Diff Formatting

```bash
git diff --check
```

This command detects certain whitespace errors in the diff, such as trailing whitespace. It is useful after editing, but it **does not replace** `git diff --name-only --diff-filter=U` and does not prove that all conflicts have been resolved.

### Using Stable Output in Scripts

If you need to feed status into a script, you can use:

```bash
git status --porcelain=v1
```

The porcelain format is designed to be more stable for machine parsing than human-oriented descriptive output. When processing the output, keep in mind that filenames may contain spaces or special characters; do not naively split lines by whitespace.

### Common Mistakes

- **Running `git diff --name-only` and treating all results as conflicts:** this command does not filter specifically for unmerged paths. Use `--diff-filter=U`.
- **Searching only for `<<<<<<<` in source code:** binary, delete/modify, or rename conflicts may have no markers. Check `git status`.
- **Seeing the markers gone and thinking Git has recorded the resolution:** editing text does not automatically clear the unmerged state in the index. You must stage the result with `git add` or confirm deletion with `git rm`.
- **Confusing staged changes with conflicted files:** read the `Unmerged paths` section or filter by `U` status to identify the right group.
- **Misinterpreting ours/theirs during a rebase:** inspect the operation details in `git status` and identify both the target branch and the commit being replayed before choosing a side.
- **Assuming an empty unmerged list means the merge is finished:** there may still be a commit creation step or a rebase/cherry-pick continue step remaining. Check the overall status.

## 8. Key Takeaways

`git status` is the starting point for understanding the repository state and seeing what Git is waiting to have resolved. `git status --short` helps scan status codes quickly; `git diff --name-only --diff-filter=U` is the direct way to retrieve the list of unmerged paths. Once you have the list, use `git diff --cc`, the `--base`/`--ours`/`--theirs` options, and the file content to understand each case.

Always re-verify with `git status` after handling conflicts. Git relies on the state in the index to know a path is resolved; merely editing or deleting conflict markers in an editor is not enough to complete this step.

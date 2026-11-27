# Why Conflicts Occur and the Limits of Automatic Merging

When multiple people modify the same Git history, Git can combine independent changes together. However, if changes compete with each other or require understanding program semantics, Git cannot decide the correct outcome on its own. Understanding when Git merges automatically and when human review is needed helps you resolve conflicts intentionally, preserve necessary changes, and avoid losing other people's work.

## 1. How Does Automatic Merging Work?

Git typically merges by comparing three versions of the content:

- **Base**: the closest common ancestor version from which both branches diverged.
- **Ours**: the version on the current branch, i.e., the branch you are on when performing the merge.
- **Theirs**: the version on the branch being brought in.

This is a *three-way merge*. Git does not simply pick one file as the standard and copy the other file over it. Git looks at what each branch has changed relative to the base, then attempts to combine the two sets of changes.

For example, the base has the following content:

```java
int timeout = 30;
boolean enabled = true;
```

The current branch changes the first line to `int timeout = 60;`, while the other branch changes the second line to `boolean enabled = false;`. The two changes are in independent regions, so Git can produce a result containing both:

```java
int timeout = 60;
boolean enabled = false;
```

A successful automatic merge only means Git found a way to combine the changes according to its rules. It does not prove that the result is functionally correct or runs properly.

## 2. Why Do Conflicts Occur?

Conflicts occur when Git cannot automatically determine a single, safe merge result under the active merge rules. Some common scenarios include:

### 2.1. Two Branches Modify the Same Region

Suppose the base contains:

```java
int retryCount = 3;
```

The current branch changes it to `int retryCount = 5;`, while the merged branch changes it to `int retryCount = 8;`. Both modify the same line in two different ways. Git does not know which value reflects the final requirement, so it marks a conflict.

### 2.2. One Branch Modifies, the Other Deletes

If one branch edits a file while the other deletes that file, Git cannot infer the intent on its own: is the file obsolete and supposed to be deleted, or should the new changes be kept? This is a *modify/delete* conflict.

### 2.3. Two Branches Create the Same Path

Two branches adding a file at the same path with different contents can create an *add/add* conflict. Git cannot automatically choose which content is the desired version.

### 2.4. Renaming, Moving, or Changing File Structure

One branch renames or moves a file while the other modifies the old file, or both branches rename it in different directions. Git can detect some rename operations, but combining the related changes can still be ambiguous. The outcome depends on the content, structure, and Git's rename detection capabilities.

### 2.5. Structural or Object-Type Conflicts

Conflicts can also involve binary files, executable permissions, symbolic links, or submodules. These cases cannot necessarily be represented using text conflict markers. You need to inspect the index state and Git's messages to identify the specific conflict type.

## 3. Conflict Markers in Text Files

For standard text content conflicts, Git can write delimiters into the file:

```text
<<<<<<< HEAD
int retryCount = 5;
=======
int retryCount = 8;
>>>>>>> feature/retry-policy
```

- `<<<<<<<` opens the changes on the current side.
- `=======` separates the two sides.
- `>>>>>>>` closes the changes from the merged branch.

The label after `<<<<<<<` is usually `HEAD` during a merge. The branch name at the end usually helps identify the other side. When using rebase, the way Git presents "ours" and "theirs" can confuse beginners: during a rebase, `ours` is typically the target branch being rebuilt onto, while `theirs` is the commit being applied. Read the operation status and actual content rather than relying solely on the labels.

If `diff3` or `zdiff3` conflict style is enabled, the conflict region may also include the base section, usually introduced by `|||||||`. This section shows the original content before both sides changed it, which is very useful for understanding why the two changes are incompatible.

These markers are only guides for the person resolving the conflict to inspect. You should not delete them mechanically or pick one entire side without understanding both sides' changes.

## 4. Inspecting the Status Before Resolving

When Git reports a conflict, first identify which operation is paused and which paths remain unresolved:

```bash
git status
git diff --name-only --diff-filter=U
git diff
```

`git status` indicates whether you are in a merge, rebase, or another related operation, and lists the unmerged paths. `git diff --name-only --diff-filter=U` lists the files still in an unmerged state. `git diff` displays the differences to assist with review.

To inspect the versions currently stored in the index, use:

```bash
git ls-files -u
```

In a standard content conflict, the index may contain three stages:

| Stage | Meaning |
|---|---|
| 1 | Common base version |
| 2 | Ours version |
| 3 | Theirs version |

You can view each version of a file with:

```bash
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
```

Replace `path/to/file` with the actual path. Not every conflict type has all three stages; for example, a newly added or deleted file may be missing a stage. For binary file conflicts or structural conflicts, rely on the information in `git status` and `git ls-files -u` to determine which versions actually exist.

## 5. Controlled Conflict Resolution Workflow

1. **Identify the goal of the operation.** Check which branch you are merging, which commit you are rebasing, or how changes are being applied. Read `git status` before editing.
2. **Understand both sides and the base.** Inspect the conflict region, related history, and the staged versions if needed. Find out why each change was made; ask the change authors when intent is unclear.
3. **Create an intentional combined result.** Edit the content to satisfy the requirements of both sides. Sometimes you need to keep one side, combine both sides, rewrite the code block, or keep the file deletion; the decision must be based on the actual intent.
4. **Mark the file as resolved.** After editing and removing all remaining conflict markers, use `git add path/to/file` to put the result into the index. If you decide to delete the file, use `git rm path/to/file`.
5. **Verify the result.** Run `git status`, inspect the staged diff with `git diff --cached`, search for any leftover `<<<<<<<`, `=======`, `>>>>>>>` markers, and run appropriate checks such as project tests or builds.
6. **Continue or abort the operation based on status.** Once the merge conflicts are resolved, use `git merge --continue` (or complete the merge commit as instructed by Git). Once the rebase conflicts are resolved, use `git rebase --continue`. If you need to return to the state before the operation, you can use `git merge --abort` or `git rebase --abort` respectively, after understanding the impact on any existing changes.

Example verification after editing a file:

```bash
git add src/main/java/RetryPolicy.java
git status
git diff --cached -- src/main/java/RetryPolicy.java
```

`git add` in this workflow both marks the path as resolved and updates the index with the chosen content. If you edit the file further afterward, you must stage it again so the index holds the exact final version.

## 6. Limits of Automatic Merging

Git primarily handles differences at the content and structural levels it can recognize. It does not fully understand program semantics, business rules, or author intent. Therefore, there are situations where Git merges successfully but the result is still broken:

- One branch renames a function while the other adds a call to it elsewhere; the result combines cleanly, but the call may no longer be valid.
- One branch changes units from seconds to milliseconds while the other changes a numeric value; the text may merge cleanly, but the calculation uses the wrong factor.
- Two branches independently modify separate configuration or source files; the final result may violate cross-file constraints.
- One change updates an API while the other still uses the old contract; no text regions overlap, yet the program may be incompatible.
- An auto-generated file or a binary file with a custom format; Git cannot understand the domain content to produce a valid combined version.

Additionally, the merge outcome depends on the base Git identifies, the merge strategy, the configured merge driver, and path attributes. Custom drivers can change how certain file types are handled, but they cannot guarantee business correctness either.

Therefore, it is important to distinguish between two concepts:

| Concept | What it confirms | What it does not confirm |
|---|---|---|
| Automatic merge succeeded | Git produced a result according to the merge rules | Code is correct, tests pass, or business requirements are met |
| Conflict marked as resolved | The user updated the index so Git can continue | Content has been thoroughly reviewed or is free of logic errors |

## 7. Practices That Easily Cause Lost Changes

- **Choosing "Accept Current" or "Accept Incoming" for an entire file without reading the content.** This can discard valid work from the other side.
- **Deleting conflict markers while leaving two incompatible code blocks behind.** The file may compile, but the logic remains wrong or processes a case twice.
- **Using `git checkout --ours` or `git checkout --theirs` out of habit.** These commands replace the working tree content of a path with one side; you must understand what ours/theirs means in the current operation before using them. For deleted files or special conflict types, behavior and available versions must be checked carefully.
- **Staging the file too early.** If you continue editing after staging, the index may still hold the old version; stage again and inspect `git diff --cached`.
- **Assuming no conflict markers means you are done.** You must inspect the diff, repository status, and run appropriate tests before continuing.

## 8. Practical Example: Merging a Retry Policy

Suppose the base has this configuration:

```java
class RetryPolicy {
    int maxAttempts = 3;
    int delaySeconds = 2;
}
```

The `feature/retry-limit` branch increases `maxAttempts` to `5`. The `feature/retry-delay` branch increases `delaySeconds` to `4`. Because the two changes are on independent lines, Git can usually merge them automatically. Even so, you still need to inspect the diff and run tests to confirm the new policy is appropriate.

In another scenario, both branches modify `maxAttempts`: one sets it to `5`, the other sets it to `8`. Git may report a conflict because it lacks enough information to choose a value. The resolver needs to check the requirements or talk to the authors of both changes. If the final requirement is a maximum of `8` attempts while also retaining an environment-based limit condition, the result may require rewriting the logic rather than picking one side verbatim.

After editing, for example:

```java
class RetryPolicy {
    int maxAttempts = 8;
    int delaySeconds = 4;
}
```

Stage the file, inspect the staged diff, and run tests for `RetryPolicy` before continuing the merge or rebase operation.

## 9. Key Takeaways

A conflict is a signal that Git needs more information to finish combining changes. Use the base, both branch versions, and the intent behind each change to make your decision. After resolving, verify both the content and the program behavior; only continue to complete the merge or rebase once the result has been verified.

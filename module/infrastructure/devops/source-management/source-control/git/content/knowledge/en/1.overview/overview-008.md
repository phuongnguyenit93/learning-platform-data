# The working loop: edit files, inspect, stage, and commit

A well-managed change in Git usually goes through a short loop: check current status, edit files, inspect the changes just made, select content to put into the staging area, review the selected content, and then create a commit. Repeating this loop for each unit of work keeps Git history reflecting intentional, readable, and traceable changes.

After this lesson, you will be able to:

- Distinguish the working tree, staging area (index), and repository.
- Read file statuses to know which step a change is at.
- View and inspect diffs before staging changes.
- Stage whole files or select individual parts of a file.
- Verify the exact content that will be stored in a commit.
- Create meaningful commits and check the result afterward.

## 1. Understanding the three places Git manages changes

When working in a repository, Git tracks content across three main areas:

| Area | Meaning | Common actions |
| --- | --- | --- |
| Working tree | The files you are opening, creating, editing, or deleting on your machine. | Editing source code, docs, configs; running the application and tests. |
| Staging area (index) | A snapshot of the changes you selected for the next commit. | `git add`, `git restore --staged`, `git diff --cached`. |
| Repository (Git database) | Recorded commits along with history and relationships between them. | `git commit`, `git log`, `git show`. |

Basic data flow:

```text
Working tree  -- git add -->  Staging area  -- git commit -->  Repository
     ^                              |
     |                              |
     +------- continue editing -----+
```

Editing a file only modifies the working tree. `git add` captures the content at the time the command runs and places that snapshot into the staging area. `git commit` records whatever is in the staging area as a commit. Therefore, a file can have both staged changes and additional unstaged edits.

Commits are created on your local machine. Committing does not automatically send changes to a remote; sharing commits with the team is a separate step, typically done with `git push`.

## 2. Start by checking repository status

Before editing or staging anything, check what state the repository is in:

```bash
git status
git status --short --branch
```

The first command outputs a human-readable description. The second displays a compact format, convenient for frequent checks. In the short output, the two characters at the start of each line represent the status in the index and the working tree:

| Symbol | Meaning |
| --- | --- |
| ` M file` | File modified in the working tree, not yet staged. |
| `M  file` | File change has been staged. |
| `MM file` | File has staged changes plus newer unstaged changes. |
| `A  file` | New file has been staged. |
| ` D file` | File deleted in the working tree, deletion not yet staged. |
| `D  file` | Deletion has been staged. |
| `?? file` | New file, untracked by Git. |

The first character describes the index; the second describes the working tree. For example, ` M` means the working tree differs from the index, whereas `M ` means the index differs from the current commit. When you see `MM`, understand that the content in the index and the content currently on disk do not match.

If `git status` reports a clean working tree, it means Git sees no uncommitted changes in tracked files and no new untracked files. You can start a new task from a clear state.

## 3. Edit files and inspect changes

Make changes with a specific scope: fix a bug, add a behavior, update documentation, or adjust a configuration. Then use `git diff` to see what Git detects:

```bash
git diff
git diff -- path/to/file
git diff --stat
```

- `git diff` compares the working tree with the staging area, so it shows unstaged changes in tracked files.
- `git diff -- path/to/file` restricts the output to a single path.
- `git diff --stat` summarizes the number of files and lines changed.

A diff hunk typically looks like:

```diff
diff --git a/src/Greeter.java b/src/Greeter.java
index 12ab345..67cd890 100644
--- a/src/Greeter.java
+++ b/src/Greeter.java
@@ -4,7 +4,7 @@ public class Greeter {
     public String greeting(String name) {
-        return "Hello " + name;
+        return "Hello, " + name + "!";
     }
 }
```

Lines starting with `-` are old content removed; lines starting with `+` are new content added. The `@@` header indicates the line range being compared. Read the diff as a preview of your change: are the filenames right, is the logic right, did any debug lines or out-of-scope edits slip in?

Note: regular `git diff` does not display the content of new untracked files. Git has no previous version to compare against. Inspect the file in your editor and confirm it shows up in `git status`; after staging, you can view its content with `git diff --cached`.

## 4. Check before staging

Diffs help inspect content, while the project's check commands verify the change does not break existing behavior. Depending on the project type, run the appropriate steps, for example:

```bash
# Detect trailing whitespace and whitespace formatting issues in the diff
git diff --check

# Example: run the test suite provided by the project
./gradlew test
```

`./gradlew test` is only an example for a project using the Gradle Wrapper; use the actual check command of the repository you are working in. For documentation changes, you may need to check links, spelling, or a Markdown linter. For source code changes, run relevant tests and add broader checks when the scope of the change calls for it.

If a check fails, read the error output, fix the root cause, and re-run the relevant check. After each follow-up edit, review `git diff` again because the working tree has changed.

## 5. Put the right changes into the staging area

The staging area is where you select content for the next commit. Stage according to the scope of your task:

```bash
# Stage a specific file
git add src/Greeter.java

# Stage several specific files
git add src/Greeter.java docs/usage.md

# Stage all changes in the repository: additions, edits, and deletions
git add -A
```

`git add -A` is convenient when you have reviewed all changes and want to include everything in one commit. If the repository has multiple independent tasks, prefer specifying explicit paths to avoid accidental staging. `git add .` also stages relative to the current directory; its scope depends on where you are located, so understand pathspecs before using it.

You can also stage parts of a single file:

```bash
git add -p src/Greeter.java
```

Git will display change blocks (hunks) one by one and ask whether you want to stage each block. This is helpful when a single file contains multiple edits that you want to split into separate commits. Read each hunk carefully before deciding; you can ask Git to split a hunk further or skip the current hunk.

After staging, check again:

```bash
git status --short
```

Do not treat `git add` running without error as proof that you staged the right thing. Repository status only tells you which paths entered the index; the next step is inspecting the actual content in the index.

## 6. Review the exact content to be committed

The `git diff` and `git diff --cached` commands answer two different questions:

```bash
# Modified but unstaged changes
git diff

# Staged changes, which will go into the next commit
git diff --cached

# Check whitespace in staged changes
git diff --cached --check

# Summary of staged changes
git diff --cached --stat
```

`git diff --cached` can also be written as `git diff --staged`. This is a critical review step before committing. Confirm that:

1. All required files are present.
2. There are no temporary files, logs, build artifacts, or secrets.
3. The staged content forms one change with a clear purpose.
4. Any remaining edits in `git diff` are intentional and will be handled later.

A file can be in `MM` status if you stage it and then continue editing. In that case, `git diff --cached` shows the staged version; `git diff` shows the edits made after staging. Committing records only the version in the index. If you want to include the newer edits in the same commit, run `git add` again and re-check the staged diff.

If you staged a file by mistake but want to keep the edited content in the working tree, remove the file from the index with:

```bash
git restore --staged path/to/file
```

This command removes the content from the staging area while preserving edits in the working tree. Afterward, re-stage only what is needed. Conversely, `git restore path/to/file` replaces the working tree content with the version in the index and can discard unstaged edits to that file; use it only when you clearly understand what will be discarded.

## 7. Create a commit

Once the staged diff looks right and required checks pass, create the commit:

```bash
git commit -m "Fix greeting punctuation"
```

Git creates a commit from the content currently in the staging area. Unstaged changes are not included in that commit. If nothing is in the index, Git normally reports there are no changes to commit.

A good commit message helps readers understand the purpose of the change. Write concisely, use clear verbs, and describe the main outcome. For example:

```text
Add validation for empty usernames
Fix incorrect timeout calculation
Document the local setup workflow
```

Avoid uninformative messages like `update`, `fix`, `changes`, or `test`. If the change needs further explanation, use the commit body to state the reason, approach, and notable impact.

After committing, verify the result:

```bash
git show --stat --oneline HEAD
git status --short --branch
```

`git show` displays the commit just created and the files recorded. `git status` confirms whether the working tree still has uncommitted changes. If changes remain, determine whether they belong to the next task or were accidentally left behind.

## 8. A complete loop in practice

Suppose you need to fix how greetings are generated in `src/Greeter.java` and update the usage guide in `docs/usage.md`. You can follow this sequence:

```bash
# 1. Check status before starting
git status --short --branch

# 2. Edit the two files in your editor

# 3. Inspect changes in the working tree
git diff -- src/Greeter.java docs/usage.md

# 4. Run appropriate checks
git diff --check
./gradlew test

# 5. Stage only the two files
git add src/Greeter.java docs/usage.md

# 6. Review the content to be committed
git diff --cached
git diff --cached --check

# 7. Create the commit
git commit -m "Improve greeting behavior and usage docs"

# 8. Verify the result
git show --stat --oneline HEAD
git status --short --branch
```

The comment lines describe manual actions in your editor and the intent of each step. Replace the paths, test command, and commit message with the actual details of your task. If a check finds an error, go back to edit the files and restart the diff review from the beginning; if you edit a file after staging, stage the parts to commit again.

## 9. Handling common situations

### Edited a file, but `git diff` does not show the expected content

Run `git status --short` to determine whether the file is tracked yet. New files have status `??`, so they do not appear in a standard diff. If a file is ignored, check the active ignore rules before deciding whether the file needs to be added to the repository.

### Already staged but edited further; the commit does not include the new edits

That is expected behavior: the index holds a snapshot from the time of `git add`. Run `git diff` to see the newly edited parts, then `git add` the file again and check `git diff --cached`.

### Staged the wrong file

Use `git restore --staged path/to/file` to remove the file from the index while keeping its content in the working tree. Verify again with `git status --short` and the staged diff before staging the right parts.

### A file does not appear in Git status

The file may be outside the repository, match a rule in `.gitignore`, or have not been saved from the editor to disk. Check the current path, file status, and ignore rules. `.gitignore` mainly prevents untracked files from showing up as new files; it does not automatically untrack a file that was previously committed.

### Commit is rejected by a hook or missing author info

Read the message Git returns. A hook may require formatting fixes, running tests, or following project commit conventions. If Git does not yet know your author name or email, configure your identity according to your workspace policy and try committing again. Do not bypass a hook just to force a commit through without understanding why the hook failed.

### Want to discard edits in the working tree

First check `git diff` to see what content will be lost. `git restore path/to/file` restores the file to the version in the index and can discard unstaged edits. If changes need to be kept, back them up or commit/stash them appropriately before restoring. Avoid sweeping commands like `git reset --hard` before clearly identifying scope and consequences.

## 10. Habits for safe and reviewable commits

- Check `git status` before starting and before committing.
- Edit toward one small goal at a time; avoid mixing unrelated tasks into a single commit.
- Read the diff after editing and read the staged diff again after staging.
- Run checks suited to the type of change and resolve failures before committing.
- Stage by path or by hunk when the repository has multiple changes.
- Never put passwords, tokens, private keys, personal environment files, or unnecessary build artifacts into a commit.
- Write commit messages describing the purpose and outcome of the change.
- Verify the new commit with `git show` and remaining status with `git status`.

Remember that the staging area is the exact content Git will record in the next commit. Therefore, a reliable loop always includes two diff reviews: one after editing to understand changes in the working tree, and one after staging to confirm the exact content about to be saved to history.

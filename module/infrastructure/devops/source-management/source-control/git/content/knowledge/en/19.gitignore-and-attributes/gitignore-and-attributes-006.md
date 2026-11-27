# Why Adding `.gitignore` Does Not Stop Tracking Committed Files

When a project begins generating build files, logs, caches, or machine-specific configurations on a developer's machine, we usually add those paths to `.gitignore`. However, if a file has already been tracked and committed by Git beforehand, adding the filename to `.gitignore` **does not make Git stop tracking that file**.

The reason lies in how Git distinguishes two things: **ignore rules determine whether to ignore an untracked file; the index (staging area) records which paths Git is actively tracking to include in commits**. Once a path is already in the index, Git continues tracking it even if that path matches a pattern in `.gitignore`.

To stop tracking a file while keeping the current copy on your machine, you need to remove the path from the index with `git rm --cached`, and then commit that change. This lesson explains why the two steps serve different roles and how to perform them safely.

## 1. How Does Git Distinguish Tracked, Untracked, and Ignored?

Git handles paths in a repository under different states:

| State | Meaning | Does Git track changes to the file? |
|---|---|---|
| **Tracked** | The path is already in the index or present in a commit managed by Git. | Yes. Git detects content modifications, deletions, or renames. |
| **Untracked** | The file exists in the working tree but has not been placed into the index by Git. | Not yet. Git can display the file as untracked. |
| **Ignored** | The file is untracked and matches an effective ignore rule. | Git normally does not list it as untracked in standard status output. |

A tracked file can be edited, staged, committed, and followed across multiple revisions. An ignored file is typically a file not yet added to Git that we do not want to bring into the repository.

### 1.1. The Index Determines Which Paths Git Tracks

When running:

```bash
git add config/local.json
git commit -m "chore: add local config"
```

Git places `config/local.json` into the index and records it in the commit. From that point onward, the path is tracked. If you later add the following line to `.gitignore`:

```gitignore
config/local.json
```

Git still tracks `config/local.json`, because that path is already managed by the index. If the file's contents change, `git status` still reports the modification as usual.

An ignore rule does not remove a path from the index, does not create a commit deleting the file, and does not modify existing history.

### 1.2. Why Doesn't Git Automatically Untrack Files?

If `.gitignore` could automatically untrack committed files, a new rule could silently make project files disappear for teammates who are using them. Git requires the user to perform an explicit index-modifying operation so that untracking is recorded in a commit.

This is intentional behavior: ignore rules help control files not yet added to the repository; the index and commits determine which content is currently managed.

## 2. Example: Adding `.gitignore` Yet the File Still Appears in `git status`

Suppose the project previously committed the `build/` directory. You add the rule:

```gitignore
/build/
```

Then run:

```bash
git status
```

If a tracked file inside `build/` changes, Git still shows that modification. The `/build/` rule only prevents untracked files inside `build/` from being reported as untracked; it does not remove files already in the index.

You can check whether a path is currently tracked:

```bash
git ls-files -- build/
```

If the command lists files inside `build/`, they are still in the index. Therefore, adding `.gitignore` alone does not solve the problem.

## 3. Untracking While Keeping the Local File with `git rm --cached`

The command to remember is:

```bash
git rm --cached -- config/local.json
```

`--cached` tells Git to remove the path from the index while keeping the file in the working tree. After this command:

- Git stages the removal of the path from the repository for the next commit.
- The current copy of the file remains on the machine running the command.
- If `.gitignore` has a matching rule, the local file is kept and no longer appears as a normal untracked file.
- Older commits still contain the previously committed versions.

For an entire directory, use `-r`:

```bash
git rm -r --cached -- build/
```

This command untracks the files inside `build/` in the index while keeping the directory contents in the current working tree. Before running it, verify the exact path so you do not accidentally untrack source code that should remain managed.

If Git refuses because the contents in the index and working tree differ, stop and inspect `git status`, `git diff`, and `git diff --cached` to determine which parts need to be kept. Do not add `-f` reflexively: force removal can discard a staged version from the index. Preserve any needed patch or backup copy before deciding how to proceed.

### 3.1. Complete Workflow for a Single File

Suppose `config/local.json` was already committed, but from now on each developer needs to keep machine-specific settings locally.

**Step 1: Add the ignore rule**

In `.gitignore` at the repository root:

```gitignore
# Developer-machine-specific configuration
/config/local.json
```

**Step 2: Remove the path from the index, keeping the local file**

```bash
git rm --cached -- config/local.json
```

**Step 3: Verify status**

```bash
git status --short
git ls-files -- config/local.json
git check-ignore -v --no-index -- config/local.json
```

Expected results:

- `git status` shows the index removal is staged.
- `git ls-files -- config/local.json` no longer lists that path.
- `git check-ignore` points to the line in `.gitignore` matching the file.
- `config/local.json` still exists on the current machine.

**Step 4: Commit the changes**

```bash
git add .gitignore
git commit -m "chore: stop tracking local config"
```

After the commit, the repository records the removal of the file from the current revision along with the new ignore rule. Subsequent edits to `config/local.json` on this machine are no longer tracked by Git in normal status.

### 3.2. Workflow for an Auto-Generated Directory

Suppose the `build/` directory is currently tracked and you want to remove it from the repository:

```gitignore
/build/
```

Run:

```bash
git rm -r --cached -- build/
git status --short
git add .gitignore
git commit -m "chore: stop tracking build output"
```

After the commit, Git no longer manages the files inside `build/` in the current revision. The build directory on the current machine remains intact. When teammates pull the new commit, Git will apply the deletion of those paths from their working trees; if they need the generated artifacts, they must rebuild them or save them separately per the project's workflow.

This point is especially important: `--cached` keeps the local file for the person running the command, but the commit deleting the tracked paths is shared with the entire team. It does not mean every other clone will also retain the files after pulling.

## 4. Understanding the Output in `git status`

After `git rm --cached`, Git usually displays the path as a staged change removing it from the index. Example:

```text
D  config/local.json
M  .gitignore
```

Meaning:

- `D` in the staged status column: the next commit will remove the path from the repository.
- `M` in the staged status column: `.gitignore` has been modified and is waiting to be committed.

The local file remains on disk. You can verify by viewing the file in your file manager or using an OS-appropriate command. If the file matches an ignore rule, `git status --short --ignored` can display it with the ignored marker.

Do not confuse Git showing `D` in the staged area with the file having been deleted from disk. `git rm --cached` removes from the index; `git rm` without `--cached` also deletes the file from the working tree.

## 5. Checking Ignore Rules and Tracked Paths

When a `.gitignore` rule does not behave as expected, check both sides: whether the file is currently tracked and which rule matches.

### 5.1. Checking Currently Tracked Paths

```bash
git ls-files -- path/to/file
```

If Git prints the path, the file is in the index. If there is no output, the file may be untracked or the provided path may be inaccurate.

To list tracked files that match ignore rules:

```bash
git ls-files -ci --exclude-standard
```

This command is useful when `.gitignore` was recently added, yet the repository already had matching files committed earlier.

### 5.2. Checking Which Rule Is Ignoring a File

```bash
git check-ignore -v -- path/to/file
```

The output displays the rule source, line number, and matched pattern, if the path is subject to being ignored. `git check-ignore` skips tracked paths by default because ignore rules do not apply to them.

If you need to test ignore patterns even for a tracked path, add `--no-index`:

```bash
git check-ignore -v --no-index -- path/to/file
```

This command helps separate two questions:

- Does the path match an ignore rule?
- Is the path currently tracked by Git?

A file can match `.gitignore` and still be tracked. In that case, `--no-index` lets you see the matching rule, while `git ls-files` tells you it is still in the index.

### 5.3. Viewing Ignored Files

```bash
git status --short --ignored
```

This command adds ignored statuses to the output. Typically, `!!` is the symbol for an ignored path. It helps verify that rules work on untracked files, though it does not prove that a tracked file has been removed from the index.

## 6. Places Where Ignore Rules Can Be Defined

Git has several sources for ignore rules:

| Source | Scope |
|---|---|
| `.gitignore` at repository root | Rules shared via commits with the whole team. |
| `.gitignore` in a subdirectory | Rules applied relative to that `.gitignore` file's location and subdirectories beneath it. |
| `.git/info/exclude` | Rules specific to the local repository, not committed as a project file. |
| Global excludes file | Personal rules applied across repositories on the machine per Git configuration. |

These sources only decide whether to ignore untracked paths. No ignore source automatically removes an already-tracked path from the index.

Check the configured global excludes file:

```bash
git config --get core.excludesfile
```

If there is no output, the repository or machine may not have a global excludes file configured. Do not add project rules to the global file if you want the whole team to apply them; place shared rules in the committed `.gitignore`.

## 7. Writing `.gitignore` Patterns Properly

Some common patterns:

```gitignore
# Ignore the build directory at the repository root
/build/

# Ignore log files at every level
*.log

# Ignore a specific local configuration file
/config/local.json

# Ignore environment files
.env
.env.*

# Allow keeping a shared configuration template
!.env.example
```

Several principles:

- A leading `/` restricts the path relative to that `.gitignore` file's location.
- A trailing `/` indicates a directory.
- `*` matches part of a path name within one level; `**` can match across multiple directory levels.
- `!` negates a previous ignore rule to bring a path back into consideration.
- If a parent directory is already ignored, you cannot negate a child file inside it without making the required parent directories traversable again.
- Ignore rules do not prevent `git add -f` from adding a file to the index; a user can still intentionally force-add an ignored file.

For example, wanting to ignore all `.log` files while keeping `important.log` at the repository root:

```gitignore
*.log
!/important.log
```

These patterns affect untracked files. If `important.log` or another `.log` file was already committed, Git continues tracking it until the path is removed from the index by a separate operation.

## 8. `.gitignore` Does Not Delete Previously Committed Data in History

A serious misconception is that adding a sensitive file to `.gitignore` removes it from the repository. In reality:

1. `.gitignore` does not remove the file from the index.
2. `git rm --cached` only records untracking in a new commit; it does not modify older commits.
3. Anyone with access to history can still inspect the file version in earlier commits.
4. If a file containing passwords, tokens, or private keys was committed, that information must be treated as exposed.

If a secret was accidentally committed:

- Revoke or rotate the credentials immediately per the system's security procedure.
- Remove the file from tracking and add appropriate ignore rules if it is local data.
- If policy requires removing the secret from history, use a controlled history-rewriting workflow, coordinate with everyone using the repository, and handle other clones, forks, caches, or copies.
- Re-check the repository and deployment systems to ensure new secrets are not committed again.

Rewriting history may require a force push and cause clones to re-synchronize. It cannot be accomplished merely by adding `.gitignore` or deleting the file in a new commit.

## 9. How Does `.gitignore` Differ from `.gitattributes`?

The two files have similar names but different purposes:

| File | Primary role | Example |
|---|---|---|
| `.gitignore` | Ignores untracked paths when Git evaluates new files. | Do not add `build/`, `.env`, `*.log` to the index. |
| `.gitattributes` | Assigns attributes to paths managed by Git, affecting content handling. | Normalize line endings, choose a diff driver, merge driver, or filter. |

`.gitattributes` does not replace `.gitignore` and does not decide to untrack a committed file. If you need to stop tracking, update the index with `git rm --cached`.

## 10. Common Errors and How to Handle Them

### 10.1. Added `.gitignore` Yet `git status` Still Reports the File as Modified

Cause: the file is already tracked. Check:

```bash
git ls-files -- path/to/file
```

If output is returned, remove the path from the index if the goal is to stop tracking:

```bash
git rm --cached -- path/to/file
```

Then commit the change along with `.gitignore`.

### 10.2. Ran `git rm --cached` Yet the File Disappeared from Disk

Verify the exact command that was run. `git rm --cached` is designed to keep the working-tree file; plain `git rm` removes both the index entry and the working-tree file. If the file has disappeared, do not rush to recreate or overwrite it. Check backups, commits, and reflog if applicable, and recover the needed content first.

### 10.3. Teammates Pull and Lose Their Local File

The untracking commit records removing the path from the repository. When teammates pull that commit, the previously tracked file may be deleted from their working trees. They need to recreate the local file or use a shared configuration template. Before untracking a file, provide a template file or instructions if members still need it.

### 10.4. The File Still Appears Even After Adding a Pattern

Check:

```bash
git check-ignore -v --no-index -- path/to/file
git status --short --ignored
```

If no rule matches, inspect the `.gitignore` location, `/` usage, wildcards, and negation rules. If a rule matches yet the file remains tracked, you need to update the index.

### 10.5. Wanting to Remove a File from History by Only Using `git rm --cached`

`git rm --cached` only changes revisions from the next commit onward. Older history still holds the contents. For exposed secrets, prioritize revoking credentials; cleaning history is a separate task requiring coordination and assessing impact on collaborators.

## 11. Practice Workflow and Checklist

When you want to untrack a committed file while keeping the local copy, proceed in order:

1. Identify the exact path with `git ls-files -- path/to/file`.
2. Check whether the file has staged or unstaged changes worth keeping with `git status` and `git diff`.
3. Add the appropriate rule to `.gitignore`.
4. Run `git rm --cached -- path/to/file` or `git rm -r --cached -- directory/`.
5. Confirm the file still exists in the working tree and no longer appears in `git ls-files`.
6. Use `git check-ignore -v --no-index` to verify the pattern matches.
7. Check `git status`, inspect the staged diff, and ensure the commit removes only the intended path from the repository.
8. Commit `.gitignore` along with the index change.
9. Inform teammates how to recreate their local file or use the template file if they still need that content.

Consolidated verification commands:

```bash
git status --short
git ls-files -- path/to/file
git check-ignore -v --no-index -- path/to/file
git diff --cached -- .gitignore path/to/file
```

Do not use `git rm -f` or `git clean` as a quick fix without checking staged contents, the working tree, and files to keep.

## 12. Takeaways

- `.gitignore` ignores untracked files; it does not automatically remove already-tracked files from the index.
- Committed files continue to be tracked by Git even if they match an ignore pattern.
- Use `git rm --cached -- <path>` to remove a file from the index while keeping the local copy; use `-r` for directories.
- Committing that operation records removing the path from the repository revision; teammates may lose their tracked copy on pull and need to recreate the local file.
- `git ls-files` checks tracked paths; `git check-ignore -v --no-index` tests rules even against tracked paths.
- `git rm --cached` does not remove versions in older commits. Committed secrets must be revoked or rotated, with history handled separately if needed.
- `.gitignore` controls ignoring paths; `.gitattributes` controls attributes and how Git processes content.

When a file has already been committed, think of the index before thinking of ignore rules. Add `.gitignore` to prevent new files from being added; use `git rm --cached` to intentionally stop tracking files already in the repository.

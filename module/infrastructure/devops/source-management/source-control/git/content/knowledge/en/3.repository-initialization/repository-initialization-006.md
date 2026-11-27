# Distinguishing Untracked, Ignored, and Tracked Files

When working inside a Git repository, not every file in the project directory has the same status. Git distinguishes between **tracked**, **untracked**, and **ignored** files. These three states determine whether a file is included in the next snapshot or appears in git status output.

Understanding the difference helps you avoid accidentally committing auto-generated files, avoid missing new source files, and avoid mistakenly assuming that adding a .gitignore rule automatically untracks already-committed files. This article uses the working tree, index, and commits to explain file states, then shows how to inspect and handle each type.

## 1. Three file states in Git

Git manages content using commits, the index (staging area), and the working tree. For a given path, you can distinguish three categories:

| State | Does Git record the path in the index? | Can it appear in default git status? | Meaning |
|---|---:|---:|---|
| **Tracked** | Yes | When there are changes relative to index or HEAD | Git already knows the path and tracks its state |
| **Untracked** | No | Yes, if not ignored | File exists in the working tree but has not been added to the index |
| **Ignored** | Normally no | Not in the regular untracked list; can be shown with --ignored | File is untracked and matches an ignore rule |

A newly created file in a project directory normally starts as untracked. After running git add, Git places the file's content into the index; the file becomes tracked in the staging state, even before any commit contains it. When you commit, the new snapshot records that file in history.

Ignored is a way of filtering untracked files out of the untracked list that Git normally displays. Ignore rules do not delete files, automatically stage files, or automatically remove a file from the index.

## 2. Tracked: files monitored by Git

A file is tracked when its path is present in the index. Normally, a file is tracked because it appeared in a previous commit or was staged with git add.

For example, a repository has:

```text
project/
├── README.md
├── src/
│   └── Main.java
└── config/
    └── app.yml
```

If these files have been committed, Git tracks them. When you edit README.md, the file remains tracked; only its contents differ compared to the index or current commit.

Check tracked files:

```bash
git ls-files -- README.md
git ls-files -- src/Main.java
```

If the path is printed, the file has an entry in the index. By default, git ls-files lists paths in the index, making it useful for determining which files Git is tracking.

Check status:

```bash
git status --short
```

Example:

```text
 M README.md
M  src/Main.java
```

The two status columns have different meanings:

- The first column (X) describes changes in the index compared to HEAD.
- The second column (Y) describes changes in the working tree compared to the index.

Therefore:

- ` M` README.md: tracked file modified in the working tree, but changes are not yet staged.
- `M ` src/Main.java: changes have been staged in the index.
- `MM` README.md: file has staged changes, and was then edited further in the working tree.

Tracked does not mean a file is always clean or up to date with the latest commit. It simply means Git manages that path; the file can still be modified, staged, deleted, or unmerged.

## 3. Untracked: files not yet tracked

Untracked refers to a file present in the working tree that has no corresponding entry in the index and is not excluded from regular listings by an ignore rule.

For example, you just created src/Helper.java:

```bash
git status --short
```

Output:

```text
?? src/Helper.java
```

The ?? marker indicates Git is not tracking this file yet. Git does not include the file's content in a commit until you stage it.

If the file needs to be managed in the repository:

```bash
git add -- src/Helper.java
git status --short
```

Output may be:

```text
A  src/Helper.java
```

`A ` indicates a new file added to the index. From this moment on, the file is tracked in the index, even though a commit has not been created yet. If you continue editing the file after staging, Git may show both staged and unstaged changes.

To list untracked files, use:

```bash
git ls-files --others --exclude-standard
```

- --others requests listing files not in the index.
- --exclude-standard applies standard ignore sources such as .gitignore, .git/info/exclude, and the global file configured via core.excludesFile.

If you want to see every file inside an untracked directory instead of a single collapsed directory entry:

```bash
git status --short --untracked-files=all
```

This option is useful when you need to verify exactly which new files will be added to a commit.

## 4. Ignored: excluded files

Ignored refers to a file that is untracked and matches an ignore rule. Git normally omits these files from the untracked section of git status.

For example, a .gitignore file contains:

```gitignore
# Build output directory
/build/

# Log files
*.log

# Local configuration
.env
```

If the repository has build/output.class, debug.log, and .env, those files are ignored according to the patterns above, provided they are not already tracked.

Inspect ignored files as well:

```bash
git status --short --ignored
```

Example output:

```text
 M README.md
?? src/Helper.java
!! .env
!! build/
!! debug.log
```

The !! marker indicates an ignored path. Depending on how Git collapses directories, the output may display the ignored directory rather than every nested file.

Ignored does not mean the file is deleted or missing. The file still resides on disk and programs can still read it; Git simply skips that file during normal new-file detection.

## 5. Quick comparison using inspection commands

The following commands help identify the state of a path:

| Goal | Command |
|---|---|
| Check whether a file is in the index | git ls-files -- path/to/file |
| View tracked and untracked changes | git status --short |
| Show every individual untracked file | git status --short --untracked-files=all |
| Show ignored files as well | git status --short --ignored |
| List untracked files that are not ignored | git ls-files --others --exclude-standard |
| List ignored files | git ls-files --others --ignored --exclude-standard |
| Find the ignore rule matching a file | git check-ignore -v -- path/to/file |

You can combine commands to diagnose:

```bash
git status --short --untracked-files=all --ignored
git ls-files -- path/to/file
git check-ignore -v -- path/to/file
```

The git check-ignore command does not replace git ls-files: it checks ignore rules, while git ls-files checks whether a path is in the index.

## 6. Using git check-ignore to find the cause

When a file does not appear in the untracked list, it may be ignored. Use:

```bash
git check-ignore -v -- build/output.class
```

If the file matches a rule, Git may print the source, line number, pattern, and path, for example:

```text
.gitignore:4:/build/    build/output.class
```

The output shows that the /build/ pattern on line 4 of .gitignore caused the inspected path to be ignored.

The -v (verbose) option helps pinpoint the exact ignore file and pattern causing the match. Common ignore sources:

- .gitignore inside the repository or subdirectories.
- .git/info/exclude applying only to the current repository.
- The global file configured via core.excludesFile.

If git check-ignore prints nothing, the file may not be ignored, the path may be wrong, or the file may already be tracked. By default, git check-ignore does not report tracked files as ignored because ignore rules do not untrack them.

To test patterns even for tracked files, add --no-index:

```bash
git check-ignore -v --no-index -- config/app.yml
```

This command only checks whether the path matches an ignore pattern, disregarding whether the file is in the index. It does not untrack the file.

## 7. Ignore rules do not affect already tracked files

This is the most common source of confusion. Suppose config/app.yml has already been committed. Then you add to .gitignore:

```gitignore
config/app.yml
```

Git still tracks config/app.yml. If you edit the file, git status still reports changes. Ignore patterns only prevent untracked files matching the pattern from appearing as untracked.

Check:

```bash
git ls-files -- config/app.yml
git status --short -- config/app.yml
git check-ignore -v --no-index -- config/app.yml
```

You can receive two results simultaneously:

- git ls-files prints the path: the file is tracked.
- git check-ignore --no-index indicates the file also matches an ignore pattern.

There is no contradiction. Ignoring does not automatically remove a file from the index.

If the goal is to stop tracking the file while keeping the local copy, use:

```bash
git rm --cached -- config/app.yml
```

This command stages removing the path from the index while keeping the file in the working tree. After committing that change, the file is no longer tracked; if it still matches .gitignore, Git will ignore it in subsequent untracked checks.

Verify before committing:

```bash
git status --short
git diff --cached -- config/app.yml
Test-Path config/app.yml
```

Test-Path is a PowerShell cmdlet to confirm the file still exists in the working tree. In Bash, you can use test -f config/app.yml.

Note: git rm --cached does not erase file contents from past commits. If the file contained committed passwords, tokens, or secrets, handle credential exposure and history cleanup according to dedicated security procedures; adding .gitignore does not purge data already stored in history.

## 8. Intentionally adding an ignored file

Sometimes a file matches .gitignore, yet you still want to add it to the repository, such as a template file or a specifically chosen artifact to preserve.

You can force-add a specific file:

```bash
git add -f -- path/to/file
```

-f (force) allows adding an ignored path. Once the file is in the index, Git tracks its changes like a regular tracked file.

Before using -f, verify the file truly needs to be shared. In particular, never force-add .env, credentials, private keys, or files containing sensitive data just to clear an ignore warning.

A better approach for local configuration files is providing a template file:

```text
project/
├── .env.example   # Committed, contains variable names and sample values
└── .env           # Ignored, contains private configuration
```

Example .gitignore:

```gitignore
.env
!.env.example
```

The file .env.example does not match the .env pattern because the name differs; the negation line is only needed if a broader pattern ignores the template file as well.

## 9. Ignore rules and basic patterns

Ignore files use patterns relative to the directory containing that ignore file. Some common examples:

| Pattern | Meaning |
|---|---|
| *.log | Ignore files or directories with matching names at levels below |
| /build/ | Ignore the build directory directly at the level of the ignore file |
| build/ | Ignore directories named build at any level within scope |
| config/local.yml | Ignore path relative to the ignore file |
| !important.log | Negate a previous ignore rule to re-include the path if Git can traverse to it |

A few points to remember:

- Lines starting with # are comments.
- A leading ! in a pattern negates a previous ignore rule.
- A trailing / in a pattern restricts the pattern to directories.
- Patterns without an internal slash can typically match names at multiple levels below the ignore file.
- A .gitignore file in a subdirectory applies to that directory and its subdirectories; patterns are evaluated relative to that file's location.

Example:

```gitignore
# Ignore build output at root
/build/

# Ignore all log files
*.log

# Ignore local configuration file
/config/local.yml
```

If a parent directory has already been ignored, negating only a child file may not be enough because Git does not traverse into an ignored parent directory. When you need to keep a child file, you must re-include the necessary parent directories first.

Ignore rules are evaluated by source and location. Within the same precedence level, the last matching pattern determines the outcome. Deeper .gitignore files can override rules in parent directories; rules in .gitignore take precedence over .git/info/exclude and global files. Use git check-ignore -v to find the effective rule instead of guessing precedence.

## 10. Distinguishing deleted files from ignored files

If a tracked file is deleted from the working tree, Git reports a deleted status, for example:

```text
 D README.md
```

After staging the deletion:

```bash
git add -u -- README.md
git status --short
```

Git may display:

```text
D  README.md
```

This is a change to a tracked file, not an ignored file. The file has disappeared from the working tree and the deletion is awaiting commit.

Conversely, an ignored file still exists in the working tree, but is excluded from the regular untracked list by an ignore rule. You can view ignored files with:

```bash
git status --short --ignored
```

Do not use git clean to deal with a file merely because it does not show up in normal git status. Before cleaning, verify whether the file is untracked or ignored and preview the list of files that would be removed.

Example previewing only non-ignored untracked files:

```bash
git clean -nd
```

Previewing only ignored files:

```bash
git clean -ndX
```

-n is dry-run, -d includes directories, and -X restricts to ignored files. Removing -n performs the deletion; read the output carefully before running the real command. Avoid git clean -fdx unless you fully understand it, as it can delete both ignored and untracked files.

## 11. Practical example in a project

Suppose a Java project has these files:

```text
java-app/
├── .gitignore
├── README.md
├── src/
│   ├── Main.java
│   └── Helper.java
├── build/
│   └── classes/
│       └── Main.class
├── .env
└── notes.txt
```

Suppose:

- README.md and src/Main.java are already committed.
- src/Helper.java is newly created, unstaged.
- build/ and .env match ignore rules.
- notes.txt is newly created and not ignored.

The .gitignore file:

```gitignore
/build/
/.env
```

Check:

```bash
git status --short --untracked-files=all --ignored
```

Illustrative output:

```text
?? notes.txt
?? src/Helper.java
!! .env
!! build/classes/Main.class
```

README.md and src/Main.java do not appear because they are tracked and unmodified. Helper.java and notes.txt are untracked. .env and Main.class are ignored.

If you want to include Helper.java in a commit:

```bash
git add -- src/Helper.java
git status --short
```

It changes from ?? to A . notes.txt remains untracked. .env and Main.class remain ignored.

If you need to save notes.txt in the repository, stage that file separately:

```bash
git add -- notes.txt
```

There is no need to add build files or local configuration files.

## 12. Decision workflow before staging

Before running git add . or git add -A, classify your files:

1. **Tracked and modified:** inspect the diff to verify the content to commit.
2. **Untracked:** determine whether the file is source code, documentation, or an asset that should be shared.
3. **Ignored:** verify the ignore rule and only force-add when there is a clear reason.
4. **Deleted:** confirm the deletion is intentional before staging.
5. **Local configuration or secret files:** keep them out of history; if needed, provide a safe template file.

You can use the following command sequence to check before staging:

```bash
git status --short --untracked-files=all --ignored
git diff
git diff --cached
git check-ignore -v -- path/to/suspected-file
git ls-files -- path/to/suspected-file
```

You do not need to run every command for every file. Choose the command appropriate for the state you need to verify. After staging, re-check git status and git diff --cached to ensure the index contains only the changes intended for commit.

## 13. Common mistakes

| Symptom | Common cause | Resolution |
|---|---|---|
| New file does not appear in git status | File is ignored or outside the repository/pathspec | Use git status --ignored and git check-ignore -v |
| Added .gitignore pattern, yet file still reports modified | File is already tracked | Use git ls-files; ignoring does not remove a file from the index |
| git add rejects file | File is currently ignored | Check patterns; use git add -f only when genuinely necessary |
| Untracked files appear as an entire directory | Git is collapsing an untracked directory | Use --untracked-files=all |
| git check-ignore prints nothing for committed file | Skips tracked paths by default | Use --no-index to test patterns |
| Deleted file, yet Git reports D | Tracked file was removed from working tree | Verify and stage the deletion if intentional |
| git rm --cached causes file to appear as untracked | File was removed from index and matches no ignore rule | Add an appropriate ignore rule if you want to keep the local file untracked |
| Ignored file disappears after running clean | Clean command deleted ignored files | Use git clean -ndX to preview; back up data you need to keep |

## Conclusion

Tracked files are recorded in the index; untracked files are not in the index and not ignored; ignored files are untracked files matching an exclusion rule. Use git ls-files to inspect the index, git status --short --ignored to view statuses, and git check-ignore -v to locate matching patterns. Remember that .gitignore does not affect already tracked files: to stop tracking while keeping a local file, use git rm --cached, inspect the staged diff, and commit the change. Before bulk staging or cleaning files, always classify and verify paths accurately.

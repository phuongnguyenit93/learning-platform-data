# Staging Files into the Index with git add by File, Directory, and Entire Repository

After editing a project, Git does not automatically include your changes in a commit. You need to select the content to be recorded using the `git add` command. This command updates the **index** (also called the staging area), which stores the snapshot that the next commit will use. You can stage a single file, multiple files, an entire directory, or the whole repository depending on the scope of your work.

Choosing the right staging scope keeps commits focused on a clear purpose. For example, you can commit just the bug fix in `src/`, leaving the documentation in `docs/` unstaged. If you run `git add` across the entire repository without reviewing the changes, unrelated files may end up in the commit as well.

## 1. How Does `git add` Update the Index?

Git has three common state areas:

- **Working tree:** the current files on disk, where you edit source code.
- **Index / staging area:** the snapshot of content and metadata that will be used for the next commit.
- **Repository history:** the commits that have already been created.

`git add` reads the current content of a path in the working tree and updates the corresponding entry in the index. The command does not create a commit and does not push changes to a remote.

```text
Working tree                Index                 Commit
-------------------         ----------------      ----------------
src/app.js modified --add-> new snapshot   --commit--> new history
docs/guide.md new           unstaged
```

Important point: `git add` stages the content at the moment the command runs. If you edit the file further after staging it, the index still holds the old snapshot; the new edits appear as unstaged changes.

Example:

```bash
# Edit src/app.js
git add src/app.js

# Continue editing src/app.js after staging
# The index still holds the version from when git add first ran
git status
```

In this case, the same file can have both staged changes and unstaged changes. This is normal behavior and lets you split one editing session into multiple commits with separate purposes.

## 2. Staging a Specific File

When you only want to include one file in a commit, pass the file path to `git add`:

```bash
git add src/app.js
```

If the path contains spaces or special characters, wrap it in quotes:

```bash
git add -- "src/feature flag.js"
```

`--` marks the end of options. Everything after it is interpreted as a pathspec, preventing filenames starting with `-` from being misinterpreted as an option.

Stage multiple files by passing multiple paths:

```bash
git add -- src/app.js src/auth/login.js docs/setup.md
```

You can stage new files, modified files, and file deletions if the paths match. Git will update the corresponding entries in the index.

### Checking Before and After Staging

```bash
# Before staging
git status --short

# Stage the exact file to commit
git add -- src/app.js

# View status after staging
git status --short

# View staged content
git diff --cached -- src/app.js
```

`git diff --cached` (equivalent to `git diff --staged`) displays the difference between the index and the current commit. This is how you verify the actual content the next commit will record.

## 3. Staging All Files in a Directory

To stage a directory and its contents, pass the directory path:

```bash
git add src/
```

This command updates matching files inside `src/`, including new and modified files; tracked files that were deleted within that scope are also recorded as deleted. Subdirectories are traversed recursively.

You can stage multiple directories at once:

```bash
git add -- src/ tests/ docs/
```

This is a suitable option when a piece of work lies in a clearly defined area, such as modifying source code and corresponding tests while not yet wanting to stage documentation in another folder.

### Directory Scope Depends on the Path You Pass

If you are at the repository root, `git add src/` stages changes under `src/`. If you are in a subdirectory, relative paths are resolved from the current directory:

```bash
# At repository root
git add src/

# Inside directory src/services
git add auth/
```

The second command targets only `src/services/auth/`. If you want paths to start from the repository root, you can use the `:/` pathspec magic:

```bash
# From any subdirectory inside the repository
git add -- ':(top)src/app.js'
```

For beginners, the simplest approach is to move to the repository root before staging by project path, then check `git status` again.

## 4. Staging the Entire Repository

When you want to put all current changes in the working tree into the index, use:

```bash
git add --all
```

Or the short form:

```bash
git add -A
```

Without a pathspec, `git add -A` updates the entire repository working tree, regardless of which subdirectory you are currently in. This command records:

- New untracked files that are not ignored.
- Modified content of tracked files.
- Tracked files deleted from the working tree.
- Path changes such as moves or renames, represented in the index as deletions/additions.

Example:

```bash
# From repository root or a subdirectory
git add --all

# View all staged content
git status
git diff --cached --stat
git diff --cached
```

`git add -A` does not automatically add ignored files. If a file matches `.gitignore` or another ignore rule, Git continues to ignore it unless you explicitly use `-f`.

### Comparing `git add .` and `git add -A`

Two commands that are often confused:

| Command | Scope |
|---|---|
| `git add .` | Stages changes under the current directory and its subdirectories |
| `git add -A` | Stages all changes across the entire working tree when no pathspec is given |
| `git add -A -- src/` | Stages all changes within the `src/` scope |

For example, if you are in `src/services/`, `git add .` targets only `src/services/` and what is below it. `git add -A` without a pathspec still updates the entire repository. To avoid depending on terminal location, move to the root when you want to stage the whole project and use `git add --all`.

## 5. Staging Changes to Already-Tracked Files with `-u`

If you only want to stage changes to tracked files without adding new files, use `-u` (`--update`):

```bash
git add --update
```

This command updates modified content and records deletions for tracked files. It does not add new untracked files into the index.

You can narrow the scope:

```bash
git add -u -- src/
```

Comparison of options:

| Command | Modified tracked files | Deleted tracked files | New untracked files |
|---|---:|---:|---:|
| `git add <path>` | Yes, if matching pathspec | Yes, if matching pathspec | Yes, if matching pathspec and not ignored |
| `git add -u` | Yes | Yes | No |
| `git add -A` | Yes | Yes | Yes, if not ignored |
| `git add .` | Yes within current scope | Yes within current scope | Yes within current scope, if not ignored |

`-u` is useful when you want to update managed files without adding new files into the commit yet.

## 6. Staging New Files, Modifications, and Deletions

### New Files

When you create a new file, Git displays it as untracked. Put the file into the index with:

```bash
git add README.md
```

After this command, the file becomes staged and will be saved in the next commit unless you unstage it.

### Modified Files

When you edit a tracked file, Git shows changes in the working tree. Stage the new version:

```bash
git add src/app.js
```

If you continue editing afterward, you need to run `git add` again to update the new snapshot into the index.

### Deleted Files

If you delete a file via the OS, you can stage the deletion with:

```bash
git add -- docs/old-guide.md
```

Or use the dedicated command:

```bash
git rm docs/old-guide.md
```

`git rm` both deletes the file from the working tree and updates the index. If you want to keep a local copy on disk while removing the file from the index, use `git rm --cached <path>`; this is a different operation from staging a file that was already deleted from disk.

## 7. Renaming or Moving Files

Git does not store a separate rename operation as an independent object. In the index, a rename is typically represented by deleting the old path and adding the new path. When displaying a diff, Git can detect renames based on content similarity.

For example, after renaming `docs/start.md` to `docs/quickstart.md`, stage both sides:

```bash
git add -A -- docs/
git diff --cached --summary
git diff --cached --find-renames
```

Or use:

```bash
git mv docs/start.md docs/quickstart.md
```

`git mv` performs the rename in the working tree and updates the index. If you use File Explorer or `mv` to rename, `git add -A` in the appropriate scope can also stage the result.

## 8. Intentionally Staging Ignored Files

Normal `git add` skips paths matched by ignore rules. Check why a file is ignored:

```bash
git check-ignore -v build/output.log
```

If you have confirmed the file needs to be included in the repository, you can force-stage it with `-f` (`--force`):

```bash
git add -f build/required-fixture.dat
```

Do not use `-f` just to make ignore notices disappear. Files like secrets, credentials, personal logs, or build artifacts are usually ignored intentionally; verify the content and project policy before force-adding.

## 9. Using Pathspecs to Select Exact Scope

The path arguments to `git add` are processed by Git as pathspecs. You can pass specific paths, directories, or file-selection patterns. Use quotes to ensure the shell passes the pattern literally to Git:

```bash
# Stage a single file
git add -- src/app.js

# Stage Markdown files under docs
git add -- 'docs/*.md'

# Stage a directory from repository root
git add -- ':(top)src/services/'
```

The `:(top)` pathspec magic anchors the path to the repository root, even when the command is run from a subdirectory. There are several other pathspec modes, but in daily work, explicit paths and `--` are usually enough to avoid confusion.

If a filename starts with a hyphen, always place `--` before the pathspec:

```bash
git add -- -draft.md
```

## 10. Inspecting the Exact Staged Content

After running `git add`, do not rely solely on the command returning without errors. Check that the index contains the exact content you intended:

```bash
# Status summary
git status --short

# List of staged file names
git diff --cached --name-status

# Staged line change statistics
git diff --cached --stat

# View full staged diff
git diff --cached

# View changes remaining in working tree
git diff
```

In `git status --short`, the first column character represents the staged state; the second column represents unstaged changes. A line with both characters indicates the same file currently has changes in both the index and the working tree.

Example:

```text
M  src/app.js
 M docs/setup.md
A  tests/app.test.js
 D src/legacy.js
```

Here `src/app.js` is staged; `docs/setup.md` has unstaged changes; `tests/app.test.js` is staged as a new file; `src/legacy.js` has an unstaged deletion. Read both columns before committing.

## 11. Practical Example: Staging Part of Your Work

Suppose you are working on changes consisting of:

```text
sample-app/
├── src/
│   ├── auth.js          <- login logic fix
│   └── profile.js       <- unfinished experiment
├── tests/
│   └── auth.test.js     <- added tests for login
└── docs/
    └── notes.md        <- incomplete personal notes
```

You want to commit the login logic and its corresponding tests, keeping the rest for later work:

```bash
# Stage only the two relevant files
git add -- src/auth.js tests/auth.test.js

# View what is about to be committed
git diff --cached --stat
git diff --cached

# Confirm the rest is unstaged
git diff
git status
```

After checking, commit:

```bash
git commit -m "Add authentication validation"
```

`src/profile.js` and `docs/notes.md` remain in the working tree for you to continue later. Purposeful staging makes commits easier to review, easier to revert, and gives a cleaner history.

## 12. Notes When Using `git add`

- `git add` does not create a commit; it only updates the index.
- `git add` does not push data to a remote.
- Staging a file does not mean all future edits to that file are automatically staged.
- Ignored files are not added normally; `-f` can override ignore rules.
- `git add -A` does not delete files from the working tree; it records add/modify/delete states into the index.
- If resolving a merge conflict, `git add <path>` is commonly used to mark the path as resolved and stage the result.
- For a submodule, `git add <submodule-path>` updates the gitlink to the commit currently checked out in the submodule; files inside must be committed in the child repository first.

## 13. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| `git add` creates a commit | No. It updates the index; `git commit` creates the commit. |
| `git add file` stages all future edits to the file | No. It stages the snapshot at the time it runs; further edits require staging again. |
| `git add .` and `git add -A` always have the same scope | No. `.` is limited to the current directory; `-A` without a pathspec updates the entire working tree. |
| `git add -u` also adds new files | No. It only updates already-tracked paths, including modifications and deletions. |
| `git add -A` automatically adds all files including ignored ones | No. Ignored files are still skipped unless `git add -f` is used. |
| `git add -A` deletes files from the machine | No. It only records deletions that have already occurred into the index. |
| Git stores a rename operation as a separate object type | No. Renames are inferred from deleting the old path and adding the new path. |
| Running `git add .` from a subdirectory stages the whole repository | No. It is limited to the current directory and its subdirectories. |

## 14. Self-Check

1. **Which area of Git does `git add` update?**
   - The index (staging area).
2. **Which command stages a specific file?**
   - `git add -- <path>`.
3. **Which command stages changes across the entire working tree?**
   - `git add --all` or `git add -A` without passing a pathspec.
4. **How does `git add -u` differ from `git add -A`?**
   - `-u` only updates already-tracked files; `-A` also adds new non-ignored files.
5. **Why must you run `git add` again after editing an already-staged file?**
   - Because the index stores the snapshot from the time of staging; new edits are not automatically added to the index.
6. **Which command displays staged content?**
   - `git diff --cached` or `git diff --staged`.
7. **To stage an ignored file after verifying it, what do you use?**
   - `git add -f -- <path>`.

## Conclusion

`git add` puts path snapshots into the index in preparation for a commit. Use `git add <file>` to pick individual files, `git add <directory>/` to stage an area, and `git add --all` or `git add -A` to update the entire working tree. `git add -u` updates only tracked files; `git add .` scopes to the current directory. After each stage, check `git status`, `git diff --cached`, and `git diff` to make sure the commit contains only the changes you intend to record.

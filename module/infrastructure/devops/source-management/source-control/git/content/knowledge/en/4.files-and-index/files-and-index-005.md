# Removing Content from the Index with git restore --staged

In Git, `git add` puts file content into the **index** (staging area) in preparation for the next commit. If you staged the wrong file or want to pull part of your changes out of the upcoming commit, use `git restore --staged`.

This command restores the index entry from a selected source, defaulting to `HEAD`. It modifies only the staging area; content in the working tree remains untouched. As a result, after unstaging, your edits typically become unstaged changes so you can keep editing or re-select them.

## 1. Basic Syntax

Syntax:

```bash
git restore --staged [--source=<tree>] [--] <pathspec>...
```

Where:

- `--staged` instructs Git to update the index.
- `--source=<tree>` specifies the tree/commit used as the source; if omitted, Git uses `HEAD`.
- `--` separates options from paths, useful when a filename starts with a hyphen.
- `<pathspec>` is one or more paths to unstage.

Example unstaging a single file:

```bash
git restore --staged src/config.yml
```

Example unstaging multiple files:

```bash
git restore --staged README.md src/app.js tests/payment.test.js
```

The command does not delete files from the working tree. It only returns the index state of the selected paths to match the version in `HEAD`.

## 2. Understanding the Index and Working Tree Before Unstaging

Git tracks two separate areas after the current commit:

- **Index:** content that will be put into the commit if you run `git commit` right now.
- **Working tree:** file content currently on disk, which may contain edits newer than the staged content.

Suppose `src/config.yml` initially has content A. You edit it to B and stage it; then edit it further to C:

```bash
# Change A to B
git add src/config.yml

# Continue editing B to C after staging B
git status
```

At this point the index holds B, and the working tree holds C. If you run:

```bash
git restore --staged -- src/config.yml
```

the index reverts to A from `HEAD`, while the working tree remains C. Consequently, the change A → C stays in the working tree as unstaged.

Before and after model:

```text
Before git restore --staged
HEAD:         A
Index:        B       (staged)
Working tree: C       (edited further after staging)

After git restore --staged
HEAD:         A
Index:        A       (matches HEAD)
Working tree: C       (preserved)
```

This is the most important takeaway: `git restore --staged` is not a command to undo edits in the file you are working on. It only removes content from the commit preparation area.

## 3. Verifying Results with git status and git diff

Before and after unstaging, you should check status:

```bash
git status --short
git diff --cached
git diff
```

- `git status --short` displays short file statuses.
- `git diff --cached` compares the index against `HEAD`, i.e., what is staged.
- `git diff` compares the working tree against the index, i.e., what is unstaged.

After running `git restore --staged <file>`, the file's staged changes normally disappear from `git diff --cached`. If the working tree still differs from `HEAD`, those changes will appear in `git diff`.

Full workflow example:

```bash
git status
git diff --cached -- src/config.yml
git restore --staged -- src/config.yml
git status
git diff --cached -- src/config.yml
git diff -- src/config.yml
```

If the file returns to matching `HEAD` completely in both the index and the working tree, `git status` will no longer show changes for that file.

## 4. Unstaging a New Never-Committed File

Suppose you create a new file `notes/draft.md` and stage it:

```bash
git add notes/draft.md
git status --short
```

Because the file does not exist in `HEAD`, the command:

```bash
git restore --staged -- notes/draft.md
```

removes that entry from the index. The file stays on disk and becomes **untracked**:

```bash
git status --short
```

You can continue editing, restage it, or delete the file via filesystem operations if you genuinely want to remove it. `git restore --staged` does not delete new files from the working tree.

This is a safe way to fix accidentally staging a new file, such as a log file or draft file, before committing.

## 5. Unstaging a Deleted File

If you delete a tracked file from the working tree and stage the deletion:

```bash
git rm src/legacy-config.yml
```

The index records the file deletion. If you want to unstage the deletion while keeping the file deleted in the working tree, run:

```bash
git restore --staged -- src/legacy-config.yml
```

Git restores the index entry back to the version from `HEAD`, without automatically restoring the file into the working tree. As a result, the index considers the file still present while the working tree lacks it; `git status` will show an unstaged deletion.

If your goal is to restore the file in the working tree as well, that is a different operation:

```bash
git restore --worktree -- src/legacy-config.yml
```

That command takes content from the current index and writes the file back to disk. Clearly distinguish `--staged` from `--worktree` to avoid overwriting content you want to keep.

## 6. Unstaging Partial Changes with Patch Mode

If a file has multiple staged hunks and you only want to pull some hunks out of the index, use interactive mode:

```bash
git restore --staged --patch -- src/app.js
```

Git displays each hunk differing between the restore source (default `HEAD`) and the index. You pick which hunks to restore in the index. Changes in the working tree are preserved.

Common keys in patch mode:

| Key | Meaning |
|---|---|
| `y` | Apply the displayed hunk to the index (unstage that hunk) |
| `n` | Keep the hunk in the index |
| `q` | Quit interactive mode |
| `s` | Split the hunk into smaller parts if possible |
| `?` | View help for the options |

With `git restore --staged --patch`, pressing `y` restores the hunk in the index to the content from the source, usually `HEAD`; it does not delete the hunk from the working tree. After finishing, check again:

```bash
git diff --cached -- src/app.js
git diff -- src/app.js
```

Patch mode is helpful when you have staged part of a file and then realize a few changes are not ready for the commit.

## 7. Selecting Another Source with --source

By default, `git restore --staged` uses `HEAD` as its source. You can select another commit or tree:

```bash
git restore --staged --source=HEAD~1 -- src/config.yml
```

This command sets the index entry of `src/config.yml` to the version in the parent commit of `HEAD`. The working tree stays unchanged. Afterward, if you stage the file again with `git add`, content in the working tree will replace the index entry.

You can use a tag or commit hash:

```bash
git restore --staged --source=v1.2.0 -- docs/release-notes.md
git restore --staged --source=<COMMIT_ID> -- src/api/schema.json
```

When using a source other than `HEAD`, inspect the index content carefully afterward because you are choosing an older version or one different from the current commit. `git restore --staged` does not move the branch and does not alter commits.

## 8. Paths, Directories, and Pathspecs

You can specify a directory to unstage all entries inside it:

```bash
git restore --staged -- src/generated/
```

Relative paths are normally resolved from the current directory where you run Git. If you want to specify a path relative to the repository root, you can use pathspec magic:

```bash
git restore --staged -- ':(top)src/config.yml'
```

If a filename begins with `-`, use `--` so Git does not interpret the name as an option:

```bash
git restore --staged -- -draft.txt
```

For paths containing spaces, enclose them in quotes according to your shell:

```bash
git restore --staged -- "docs/release notes.md"
```

On Windows PowerShell, double quotes typically suit this example well. Check `git status` before operating on multiple paths or broad patterns.

## 9. Distinguishing git restore --staged from Related Commands

| Command | Effect on Index | Effect on Working Tree | Purpose |
|---|---|---|---|
| `git restore --staged -- <path>` | Restores entry from `HEAD` into index | Preserved | Unstage |
| `git restore --worktree -- <path>` | Preserved | Restores file from index | Discard unstaged changes |
| `git restore --staged --worktree -- <path>` | Restores index from `HEAD` | Restores working tree from source per command rules | Reset both areas to source state |
| `git reset -- <path>` | Restores index from `HEAD` | Preserved | Legacy syntax to unstage |
| `git rm --cached -- <path>` | Removes entry from index | Keeps file on disk | Stop tracking file in the next commit |

The following two commands are often confused:

```bash
git restore --staged -- config/local.yml
git rm --cached -- config/local.yml
```

The first returns the index entry to its state in `HEAD`. If the file has already been committed, it continues to be tracked. The second removes the entry from the index, making the file untracked (unless ignored); this is typically used when you want to stop tracking a file while keeping the local copy.

`git reset <path>` is the traditional way to unstage. In modern Git, `git restore --staged` expresses intent more clearly and separates restoring the index from moving `HEAD` with `git reset`.

## 10. Things to Check Before Unstaging

- View `git status` to see which files are staged and which still have unstaged changes.
- Use `git diff --cached` to verify what content is currently in the index.
- If a file has both staged and unstaged changes, remember that unstaging the whole file resets the index to the source while preserving all content in the working tree.
- If you only want to unstage a few hunks, use `--patch` instead of unstaging the whole file.
- If a new file does not yet exist in `HEAD`, it becomes untracked after unstaging.
- If a file deletion was staged, unstaging restores the index entry but does not restore the file on disk.
- Check `git diff --cached` again before committing to ensure the commit contains only the intended content.

## 11. Example Workflow: Accidentally Staging a Config File

Suppose you are preparing to commit a login feature. You stage the files:

```bash
git add src/auth/LoginService.java src/auth/LoginController.java config/local.yml
```

Then you realize `config/local.yml` contains machine-specific settings and should not be included in the commit. Inspect:

```bash
git status --short
git diff --cached -- config/local.yml
```

Unstage the config file:

```bash
git restore --staged -- config/local.yml
```

Verify again:

```bash
git status --short
git diff --cached
git diff -- config/local.yml
```

If the file still needs to exist locally, keep the working tree intact and add an appropriate ignore rule if it is a machine-specific config file. If a file containing a secret was previously committed in the past, unstaging it now does not remove the secret from history; handle the secret exposure incident and history-removal procedure separately.

Once the staged content is right:

```bash
git diff --cached
git commit -m "Implement login flow"
```

## 12. Practice Exercises

In a test repository, create an initial commit containing `README.md` and `src/app.js`.

1. Edit `README.md`, run `git add README.md`, then use `git diff --cached` to view the staged content.
2. Edit `README.md` again after staging and check both `git diff --cached` and `git diff`.
3. Run `git restore --staged -- README.md`, then confirm the changes remain in the working tree but are no longer in the index.
4. Create a new file `notes/draft.md`, stage the file, then unstage it and confirm the file becomes untracked while remaining on disk.
5. Delete a tracked file, stage the deletion, then use `git restore --staged` to confirm the file stays deleted in the working tree while the index entry is restored.
6. Stage multiple hunks in one file and use `git restore --staged -p` to unstage just one hunk.
7. Use `--source=HEAD~1` in a repository with at least two commits, then check which commit the index content was taken from.
8. Compare `git restore --staged`, `git restore --worktree`, and `git rm --cached` using `git status`.

You have completed the exercises when you can unstage a file or partial changes without losing working tree content, and explain the difference between restoring the index, restoring a file on disk, and untracking a file.

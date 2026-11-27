# Removing Untracked Files with git clean and Previewing with -n

During development, the working tree often accumulates files not tracked by Git (*untracked files*), such as log files, build outputs, temporary files, or test data. When you want to clean up these files, Git provides the `git clean` command. This command deletes directly from the filesystem, so you must inspect the target list before executing it.

The `-n` (*dry run*) option lets you preview what Git would delete without actually deleting anything. A safe workflow typically starts with `git status`, followed by `git clean -n` or `git clean -nd` to preview, and only then running the command with `-f` after confirming the exact scope.

## 1. What Is an Untracked File?

Git categorizes files in the working tree by tracking status:

- **Tracked:** files already recorded by Git in a commit or the index. A file can be clean, modified, staged, or deleted in the working tree.
- **Untracked:** files currently present in the working tree that are not yet tracked by Git in the index/commits.
- **Ignored:** files not tracked by Git that match ignore rules, typically declared in `.gitignore`, `.git/info/exclude`, or a global ignore configuration.

For example, after running a build, a project might generate `build/output.log`. If the file is not tracked by Git and not ignored, `git status` usually shows it under *Untracked files*. If `build/` is declared in `.gitignore`, the file may not appear in normal status output and is considered ignored.

`git clean` is primarily used to delete untracked files and untracked directories. By default, the command does not delete modified or staged tracked files, and it also skips ignored files. Those groups can be targeted with specific options, so you must understand the filters before running it.

## 2. Checking Status Before Cleaning

First, check the repository status:

```bash
git status
```

To view short status including untracked and ignored files:

```bash
git status --short --ignored
```

Example:

```text
 M src/App.java
?? notes/tmp-plan.txt
?? scratch/
!! build/
```

Meaning in the example:

- ` M src/App.java`: tracked file with unstaged changes.
- `?? notes/tmp-plan.txt`: untracked file.
- `?? scratch/`: untracked directory.
- `!! build/`: ignored path.

If you need to see every individual file inside untracked or ignored directories, ask Git for more detail:

```bash
git status --short --untracked-files=all --ignored
```

Reading status before cleaning helps avoid confusing active work files with disposable data. In particular, never treat being ignored as proof that a file is unimportant: a build directory can be regenerated, whereas local config files or test data may need to be kept.

## 3. Previewing with git clean -n

Basic command:

```bash
git clean -n
```

`-n` is short for `--dry-run`. Git only prints the items slated for removal, typically looking like:

```text
Would remove notes/tmp-plan.txt
```

This command does not delete files or directories. It is a critical verification step before running the actual clean command.

### Previewing untracked directories too with -d

By default, `git clean` does not descend into and delete untracked directories. Use `-d` to include untracked directories along with their contents:

```bash
git clean -nd
```

Example:

```text
Would remove notes/tmp-plan.txt
Would remove scratch/
```

`-d` is useful when you want to clean temporary directories or directories created during experimentation. If you only run `git clean -n`, an untracked directory might not be listed as an item to remove; therefore, add `-d` when you want to inspect directories as well.

## 4. Deleting After Inspecting the List

After confirming the list from the dry run, you can run:

```bash
git clean -f
```

`-f` (*force*) allows Git to perform the deletion. If you also need to delete untracked directories:

```bash
git clean -fd
```

In many configurations, Git requires `-f` because `clean.requireForce` is enabled by default. The `-n` and `-i` options are preview or interactive modes that do not delete immediately; for non-interactive deletion, use `-f` after previewing.

A common cycle:

```bash
# 1. Check repository status.
git status --short --ignored

# 2. Preview untracked files and directories.
git clean -nd

# 3. Only after confirming the list, delete.
git clean -fd

# 4. Re-check status.
git status
```

Do not skip the dry run step in repositories holding important local data or when you do not yet understand the project's ignore rules.

## 5. Distinguishing -x and -X When Handling Ignored Files

By default, `git clean` respects ignore rules. Two options alter that scope:

| Option | Scope |
|---|---|
| Neither `-x` nor `-X` | Deletes non-ignored untracked items; skips ignored files |
| `-x` | Ignores ignore rules, treating ignored files as eligible for deletion too |
| `-X` | Deletes only ignored items; keeps non-ignored untracked files |

### Previewing ignored files too with -x

```bash
git clean -ndx
```

This command previews untracked files/directories, including ignored ones. If you truly want to delete that entire scope:

```bash
git clean -fdx
```

This is a broad operation. For example, if `.gitignore` ignores `.env.local`, `build/`, and `coverage/`, `-x` can include all of them in the deletion list. `.env.local` may contain private configuration that cannot be regenerated; do not run this command merely to clear build outputs.

### Previewing only ignored files with -X

```bash
git clean -ndX
```

Capital `-X` selects only ignored items. After previewing, if those are the exact targets to clean:

```bash
git clean -fdX
```

This option is useful when you want to delete ignored build outputs while keeping other untracked files, such as notes or experimental files that are not ignored.

## 6. Limiting Scope with Pathspecs and Excluding with -e

You can restrict the clean command to a specific path. For example, preview only untracked items inside the `scratch` directory:

```bash
git clean -nd -- scratch/
```

After checking, if you want to delete that exact scope:

```bash
git clean -fd -- scratch/
```

`--` separates options from the pathspec. This ensures Git interprets what follows as paths to filter.

If you want to clean most untracked files while keeping a specific pattern, use `-e` to add an exclusion rule:

```bash
# Preview while keeping .local files.
git clean -nd -e '*.local'
```

`-e <pattern>` adds a pattern to the exclude list for that clean run. You can pass `-e` multiple times when keeping multiple groups:

```bash
git clean -nd -e '*.local' -e 'scratch/keep/'
```

Check the dry run output to confirm the pattern excludes the exact items you want to keep. Ignore/exclude patterns follow specific path-matching rules; if the output does not match expectations, narrow the pathspec or adjust the pattern and re-run the dry run.

## 7. Using Interactive Mode -i

When the target list contains many kinds of files and you want to choose item by item, you can use:

```bash
git clean -i
```

Interactive mode displays the list and an action menu. Depending on your Git version, choices typically include:

- `clean`: execute deletion of the selected items.
- `filter by pattern`: filter the list by pattern.
- `select by numbers`: choose items by number.
- `ask each`: prompt for confirmation on each item.
- `quit`: exit without proceeding.
- `help`: view menu help.

`-i` is suitable when manually reviewing a large list. Even so, read each path and verify before selecting the `clean` action.

## 8. Special Cases to Watch Out For

### Tracked files are not deleted by git clean

If `src/App.java` is tracked by Git and has uncommitted edits, `git clean -fd` is not the command to undo those changes. `git clean` targets untracked items; do not use it to handle tracked changes. Check `git status` and pick the tool suited to that file's state.

### Directories containing nested Git repositories

Git is cautious with untracked directories that contain another Git repository inside them. Regular `git clean -fd` will not delete such a nested repository. A second force level (`-ff`) is needed to allow deleting nested repository directories:

```bash
git clean -ndff
```

Only run the corresponding delete command after carefully reviewing the list. A nested repository can contain independent history and work; deleting the entire directory removes that repository's data from the filesystem.

### Ignored files may be data worth keeping

Directories like `build/`, `dist/`, or `coverage/` can usually be regenerated. However, `.env`, certificate files, local databases, or test data may be ignored because they should not be committed—not because they are disposable. Check the source of ignore rules before using `-x` or `-X`:

```bash
git check-ignore -v .env.local
```

This command shows the pattern and configuration file causing the path to be ignored (if a rule matches).

### git clean has no built-in undo

Files deleted by `git clean` are not placed into the reflog or a new commit. If the data has not been backed up or stored elsewhere, Git usually cannot recover that content. Dry runs, narrow pathspecs, and backups are your safeguards before deleting.

## 9. Safe Cleanup Workflow

Suppose you want to delete the `scratch/` directory and temporary untracked files, while keeping ignored configuration and all source code changes.

```bash
# View all changes, including ignored files.
git status --short --ignored

# Preview untracked files and directories while respecting ignore rules.
git clean -nd

# If you only want to clean scratch, limit with a pathspec.
git clean -nd -- scratch/

# Confirm the list again before executing.
git clean -fd -- scratch/

# Check status after cleaning.
git status --short --ignored
```

If you need to clean ignored outputs, run a separate dry run pass:

```bash
git clean -ndX
```

Read the list carefully, confirm those files can be regenerated or are backed up, and only then consider:

```bash
git clean -fdX
```

Do not switch mechanically from `-n` to `-f`. Keep the exact same filters and pathspecs between the preview step and the delete step so the actual scope matches what you reviewed.

## 10. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| `git clean -n` deletes files immediately | `-n` only simulates and prints items slated for removal |
| `git clean` deletes every file not in a commit by default | By default it respects ignore rules and does not delete ignored files |
| `git clean -d` deletes every directory in the project | It targets untracked directories; directories containing nested Git repositories require an extra force level |
| `-x` and `-X` are the same | `-x` includes ignored files; `-X` selects only ignored files |
| `git clean` undoes source code changes | It does not delete changes to tracked files; use a different operation for those states |
| You can recover via reflog after cleaning | Reflog tracks ref/HEAD positions, not copies of deleted untracked files |

## 11. Takeaways

`git clean` is a tool for cleaning up untracked files. Use `-n` to preview, add `-d` when directories should be included, and only add `-f` after confirming the list. By default Git preserves ignored files; `-x` expands scope to include ignored files, while `-X` selects only ignored items. `-e` and pathspecs help narrow the scope.

Before deleting, check `git status --short --ignored`, run a dry run with the exact options you intend to use for deletion, and read every path. `git clean` deletes data from the filesystem and has no built-in undo mechanism, so previewing beforehand is essential for protecting local work.

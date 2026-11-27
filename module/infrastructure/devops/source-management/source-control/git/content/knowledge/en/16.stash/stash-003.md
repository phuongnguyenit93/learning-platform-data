# Including Untracked or Ignored Files in a Stash with -u and -a

The standard `git stash` command shelves changes to files already tracked by Git. If you have just created new files or have files ignored by `.gitignore`, those files may remain in the working tree after stashing. The `-u` and `-a` options expand the stash scope so you can switch branches or handle other tasks while still preserving these files. It is important to understand the difference because `-a` also includes ignored files in the stash and removes them from the working tree.

## 1. Distinguishing tracked, untracked, and ignored

Git classifies files in the working tree according to tracking state:

| State | Meaning | Example |
|---|---|---|
| Tracked | A file already known to Git via a commit or added to the index | `src/main/App.java` |
| Untracked | A file not yet tracked by Git, not yet added to a commit or the index | Newly created `src/main/NewService.java` |
| Ignored | An untracked file matching an ignore rule in `.gitignore`, `.git/info/exclude`, or global exclude configuration | `build/`, `.env.local`, log files |

A new file does not automatically become tracked simply because it resides in the repository directory. You need `git add` to place the file into the index. If a new file matches an ignore rule, Git normally does not list it as untracked in regular status output.

Check the status before stashing:

```bash
git status --short
git status --short --ignored
```

The second command also displays ignored items, typically marked with `!!`. To see which rule is ignoring a specific file:

```bash
git check-ignore -v .env.local
```

This command reports the rule file and line that matched if the file is ignored. The fact that a file is ignored does not mean it is harmless or safe to delete; it could be local configuration, auto-generated data, or sensitive information.

## 2. What does stash save by default?

When you run:

```bash
git stash push
```

Git saves changes to tracked files in the index and working tree into a stash entry, then restores tracked files back to the `HEAD` state as supported by stash. Untracked and ignored files are not included in the stash by default, so they remain in the working tree.

For example, before stashing you have:

- Modified `src/main/App.java` (tracked).
- Created `src/main/NewService.java` (untracked).
- Have `build/output.log` which is ignored.

After `git stash push`, the changes in `App.java` are shelved, but `NewService.java` and `build/output.log` remain. If your goal is to clean the working tree to switch to another branch, the two remaining files could still get in the way or be confused with work on the new branch.

## 3. Using `-u` to stash untracked files

The `-u` option is shorthand for `--include-untracked`. It tells Git to include untracked files in the stash along with tracked changes:

```bash
git stash push -u -m "WIP: add report service"
```

After this command:

- Changes in tracked files are saved into the stash.
- Untracked files are saved with the stash entry.
- Ignored files remain in the working tree.

For example, if `src/main/NewService.java` is a newly created unadded file, `-u` helps shelve that file so you can switch branches without committing partial unfinished work.

You can use the equivalent long form:

```bash
git stash push --include-untracked -m "WIP: add report service"
```

`-u` does not mean including every new file regardless of ignore rules. Files that are already ignored are not included by this option.

## 4. Using `-a` to stash ignored files as well

The `-a` option is shorthand for `--all`. It includes both untracked and ignored files in the stash:

```bash
git stash push -a -m "WIP: local build and config files"
```

Long form:

```bash
git stash push --all -m "WIP: local build and config files"
```

Unlike `-u`, `-a` includes ignored files and cleans them from the working tree after saving. This is useful when you need to clean the entire working area, including auto-generated files or local configuration ignored by `.gitignore`.

Example:

| File | State | `stash push` | `stash push -u` | `stash push -a` |
|---|---|---|---|---|
| Modified `src/main/App.java` | Tracked | Yes | Yes | Yes |
| Newly created `src/main/NewService.java` | Untracked | No | Yes | Yes |
| Ignored `build/output.log` | Ignored | No | No | Yes |

`-a` has a broader scope. Before using it, inspect `git status --short --ignored` to see which files will be included in the stash. Large build directories can make the stash grow significantly; cache files or auto-generated data may not need to be saved.

## 5. Caution with sensitive and auto-generated files

`.gitignore` is commonly used to exclude from commit history files such as local passwords, tokens, private config files, logs, caches, or build directories. Using `-a` places ignored files into stash objects in the local repository. Stash does not encrypt content and is not a secrets store.

Before running `git stash push -a`, consider:

- Do not put private keys, passwords, tokens, or unnecessary secrets into a stash.
- Check the size of build directories, caches, and auto-generated data.
- Only use `-a` when you truly need to preserve ignored files for later restoration.
- If ignored files contain valuable data, ensure an appropriate and permitted storage approach is in place.

Do not assume ignored files can be safely deleted. The `-a` option removes those files from the working tree after stashing; understand the scope before running it.

## 6. Naming and inspecting stash entries

It is good practice to add a short message to identify the purpose of each stash:

```bash
git stash push -u -m "WIP: report endpoint"
git stash push -a -m "WIP: local config before branch switch"
```

List existing stashes:

```bash
git stash list
```

Example:

```text
stash@{0}: On feature/report: WIP: local config before branch switch
stash@{1}: On main: WIP: report endpoint
```

`stash@{0}` is the newest entry at the time of inspection. When creating another stash or deleting an entry, indices can shift. Therefore, re-read `git stash list` before operating on a specific entry.

View a summary of changes:

```bash
git stash show --stat stash@{0}
```

View the detailed diff:

```bash
git stash show --patch stash@{0}
```

To also view the contents of untracked files saved in the stash:

```bash
git stash show --include-untracked --stat stash@{0}
git stash show --include-untracked --patch stash@{0}
```

For stashes created with `-a`, inspect the saved ignored content by viewing the entry and verifying specific files after restoring in a safe working tree. Do not print secret file contents to the terminal or share inspection logs unnecessarily.

## 7. Restoring a stash with apply or pop

There are two common ways to restore:

```bash
git stash apply stash@{0}
```

`apply` applies the stash contents back to the working tree, but by default does not attempt to restore the original staged state in the index; changes may appear as unstaged. The entry remains in the list so you can inspect or re-apply it when needed.

```bash
git stash pop stash@{0}
```

`pop` applies the stash and then deletes the entry if the application succeeds. If a conflict occurs or the apply operation fails, Git typically keeps the entry so you can retry after resolving the issue.

If you need to restore the staged state saved in the stash as well, use `--index`:

```bash
git stash apply --index stash@{0}
```

This option asks Git to attempt restoring the index state, including changes that were staged before stashing. Restoration can fail if the current contents are no longer compatible.

After restoring, check:

```bash
git status --short --ignored
```

For stashes with untracked or ignored files, check the restored paths as well and confirm they do not overwrite newer existing data.

## 8. Handling when untracked or ignored files already exist

A stash may contain the file `src/main/NewService.java`. While the stash was shelved, you or another tool may have created a file at the same path on the current branch. When applying the stash, Git cannot safely overwrite the existing file automatically, and the operation may fail or require manual handling.

Before running apply/pop, check the status and paths at risk of colliding. If the current file is valuable, save or move it according to your workflow before restoring. Do not run broad cleanup commands like `git clean -fdx` just to force a stash to apply; that command can delete untracked and ignored files not contained in the stash.

If apply produces conflicts in tracked files, resolve them like a normal Git conflict, reviewing both current content and stashed content. After resolving, check the diff and run tests before continuing work.

## 9. Creating a new branch from a stash

If a stash was created on an older branch and you want to continue the work on a dedicated branch, you can use:

```bash
git stash branch feature/report-wip stash@{0}
```

Git creates and switches to a new branch at the commit where the stash was created, then applies the stash onto that branch. This approach often reduces conflicts when the stash was created on a different base than the current branch. If the application succeeds, the used entry is removed from the stash list.

Check `git status` after creating the branch. If you need to keep the stash for reuse or are unsure whether the operation restored everything completely, use `apply` first and only `drop` after confirming the result.

## 10. Deleting a stash after verification

Once you have restored and verified the work completely, you can delete a specific entry:

```bash
git stash drop stash@{0}
```

The `drop` command removes the entry from the stash list. Read `git stash list` right before running it because indices may have shifted.

The following command deletes all stash entries:

```bash
git stash clear
```

`clear` has a broad scope and is harder to recover from; only use it when you have checked and are certain no stashes remain that need to be kept. Do not delete a stash immediately after `apply` if you have not verified that untracked/ignored files returned to their proper locations.

## 11. Practice example: switching branches with new and ignored files

You are working on `feature/report` with this state:

- Modified `src/main/ReportService.java` (tracked).
- Created `src/main/ReportMapper.java` (untracked).
- Have `build/generated/report-schema.json` which is ignored.

If you only need to preserve tracked changes and the new file, without keeping build output, use:

```bash
git status --short --ignored
git stash push -u -m "WIP: report mapper"
git status --short --ignored
git switch main
```

`ReportService.java` and `ReportMapper.java` are shelved; the ignored build file remains. If the goal is to shelve the ignored build file as well to clean the working tree, after confirming it contains no secrets or data that must be kept separately, use `-a`:

```bash
git stash push -a -m "WIP: report work and local generated files"
```

When returning to the feature branch:

```bash
git switch feature/report
git stash list
git stash apply stash@{0}
git status --short --ignored
```

Review the restored files and run necessary checks. If everything is complete, delete the used entry:

```bash
git stash drop stash@{0}
```

In practice, read `git stash list` before choosing `stash@{0}` because newer stashes may have been created while you worked on another branch.

## 12. Key takeaways

`git stash push` saves tracked changes by default. Use `-u` (`--include-untracked`) to also save untracked files; use `-a` (`--all`) to save both untracked and ignored files while cleaning those files from the working tree. Inspect the scope before stashing, set a recognizable message, review the entry before restoring, and only delete the stash after confirming that all data is completely restored.

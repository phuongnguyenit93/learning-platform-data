# Using git mergetool and Marking Files as Resolved

When Git encounters a conflict, you must produce the final content for each file before continuing a merge, rebase, or cherry-pick. You can edit conflict markers directly in a text editor, but with multiple changed regions or many files, a visual merge tool makes it easier to compare versions and select individual parts. Git calls this workflow **mergetool**.

Once the content is right, Git needs to know that the file is resolved. This is recorded in the index, usually via `git mergetool` or `git add`. Simply closing the tool window or deleting `<<<<<<<`, `=======`, and `>>>>>>>` markers inside the file is not enough to finish a conflict.

## 1. What Does Mergetool Do?

A three-way conflict usually has three input versions:

- **BASE**: the common ancestor version before both sides changed.
- **LOCAL**: the version from the current side of the operation, typically corresponding to stage 2 (ours).
- **REMOTE**: the version from the incoming side, typically corresponding to stage 3 (theirs).
- **MERGED**: the output file you edit to hold the merged content.

BASE, LOCAL, and REMOTE are the inputs for comparison. MERGED is the final result. In two-way or three-way tools, the UI layout can vary; identify the output pane and save that result before closing the tool.

The interpretation of LOCAL and REMOTE also depends on the operation:

| Operation | LOCAL / current side | REMOTE / incoming side |
|---|---|---|
| Merge | Branch checked out when running merge | Branch being merged in |
| Rebase | New base at HEAD, including upstream and replayed commits | Commit currently being rebased |
| Cherry-pick | Current branch receiving the commit | Commit being cherry-picked |

During a rebase, LOCAL is usually the new base and REMOTE is the commit being replayed. Therefore, do not choose content solely based on the words "local" or "remote" in the UI. When unsure, inspect the file stages with `git show :2:path/to/file` and `git show :3:path/to/file` before deciding.

Mergetool helps you view diffs, pick parts from each side, and edit the result. The tool does not know the program's business requirements on its own; the person resolving the conflict must still understand which changes should be kept.

## 2. Selecting and Configuring a Merge Tool

Git supports many merge programs such as Meld, KDiff3, Vimdiff, Neovim Diff, Beyond Compare, or other tools depending on the operating system and installation. The tool must be installed on the machine and Git must be able to find its executable command.

List the tools Git recognizes:

```bash
git mergetool --tool-help
```

You can specify a tool for a single run without changing configuration:

```bash
git mergetool --tool=meld
```

The command above tells Git to use Meld for conflicted files. If you only want to handle one file:

```bash
git mergetool --tool=meld -- src/config.yml
```

Replace `meld` with a tool name available on your machine. If Git reports the tool cannot be found, check that the program is installed and its executable directory is in `PATH`.

If you regularly use the same tool in the current repository, save a local configuration:

```bash
git config --local merge.tool meld
git config --get merge.tool
```

A `--local` setting applies only to the current repository. Use `git config --global merge.tool meld` if you want to set the default tool for all repositories of your user account. You can also override the default configuration by passing `--tool=<tool-name>` when invoking `git mergetool`.

Some useful configuration options:

| Configuration | Effect |
|---|---|
| `merge.tool` | Sets the default merge tool |
| `mergetool.<tool>.trustExitCode` | Lets Git trust the tool's exit code to determine whether the merge succeeded |
| `mergetool.prompt` | Controls the prompt before launching the tool for each file |
| `mergetool.keepBackup` | Keeps or removes `.orig` backup files after merging |

For example, if Meld on your machine returns a reliable exit code when the user finishes merging, you can configure:

```bash
git config --local mergetool.meld.trustExitCode true
```

Only enable this option when you already know the tool's exit code behavior. Otherwise, keep the default so Git prompts you to confirm the result after the tool closes. Git often keeps a backup file with a `.orig` extension; this is a backup of the pre-merge file. Inspect these files before deleting them or changing `mergetool.keepBackup`.

## 3. Workflow for Using Mergetool

Suppose you are on branch `main` and want to merge branch `feature`:

```bash
git switch main
git merge feature
```

If Git reports conflicts, start by checking status and listing unresolved files:

```bash
git status
git diff --name-only --diff-filter=U
```

The second command lists only paths still in an unmerged state. Next, launch the tool:

```bash
git mergetool --tool=meld
```

Git opens each conflicted file one by one in the chosen tool. For each file:

1. Compare BASE, LOCAL, and REMOTE to understand what changed on each side.
2. Inspect the context around the conflict region, including function names, related configs, and call sites.
3. Choose one side per region where appropriate, or combine the changes into a new result.
4. Inspect the MERGED pane to verify it reflects the exact desired outcome.
5. Save the output file in the tool and close the window as required by the tool.

Some tools provide buttons to pick an entire side or pick individual hunks. These buttons only help copy content; they do not replace reading and verifying the result. If changes from both sides need to be kept, combine them instead of accepting one entire side.

After closing the tool, Git may prompt:

```text
Was the merge successful [y/n]?
```

If you have inspected the result and it is correct, answer `y`. When Git is configured to trust the tool's exit code, this confirmation step may be decided automatically. If the result is not yet right or you forgot to save the file, do not confirm success; reopen and continue editing.

## 4. Marking Files as Resolved

In the index, a conflicted file typically has stage 1, stage 2, and stage 3 versions. When the resolution is accepted, Git replaces the unmerged stages with stage 0 containing the final content. This is what **marking a file as resolved** means.

`git mergetool` usually stages the file into the index when the tool is confirmed successful or its exit code is configured to signal success. Even so, verify the actual state, because tool behavior and settings can vary:

```bash
git status
git diff --name-only --diff-filter=U
```

If the file is still unmerged, or you resolved it manually after the tool closed, save the final content and add the file to the index:

```bash
git add -- src/config.yml
```

If the final decision is to delete the file, record the deletion with:

```bash
git rm -- src/obsolete-config.yml
```

Do not use `git add` to mark a deleted file if the path no longer exists; `git rm` explicitly expresses the deletion result and updates the index.

Verify remaining conflicted files and staged content:

```bash
git diff --name-only --diff-filter=U
git diff --cached -- src/config.yml
git diff --cached --check
git status
```

If the first command lists no files, Git no longer has unmerged states for those paths. `git diff --cached` lets you inspect the content placed in the index; read it carefully to avoid missing changes or accidentally keeping wrong content. `git diff --cached --check` checks for common whitespace errors in staged changes.

You can inspect a file's index entries directly:

```bash
git ls-files -u -- src/config.yml
```

If the file has been resolved, this command no longer prints unmerged stages for that file. When you need to review the pre-resolution versions, run:

```bash
git show :1:src/config.yml
git show :2:src/config.yml
git show :3:src/config.yml
```

These stages only exist while Git still retains the corresponding unmerged versions. For add/add, modify/delete, or cases without all three sides, a stage may not exist.

## 5. When Mergetool Cannot Handle the Conflict

Mergetool is especially helpful for line-comparable text files. Certain situations require manual decisions:

- **Binary files:** text diff tools may not display meaningful content. Use an application suited to the file format, pick the version to keep or recreate the file, then record the result.
- **One side deletes, the other edits:** decide whether to keep the edited content or accept the deletion. If keeping, ensure the file exists with the right content and run `git add`; if deleting, run `git rm`.
- **Renaming or moving files:** read the full output in `git status`, identify the final path, and ensure old/new paths are handled properly.
- **Tool closed with incomplete output:** reopen the file or edit it in a text editor, then stage manually. Do not confirm success just to dismiss the prompt.

If you want to edit conflict markers manually, open the file and produce the final content, for example:

```text
<<<<<<< HEAD
timeout = 30
=======
timeout = 60
>>>>>>> feature
```

The right result might be keeping one value, or it might require a third value per application requirements. After editing, remove all leftover markers, save the file, and run:

```bash
git add -- path/to/file
```

Mergetool is a tool to assist comparison and editing; the final decision must still be verified against the content in the working tree and index.

## 6. Continuing the Operation After Resolving Everything

Once all files are handled, verify again:

```bash
git status
git diff --name-only --diff-filter=U
git diff --cached
```

Read the staged diff, run tests or builds appropriate for the change, and then continue the paused Git operation:

```bash
# If merging
git merge --continue

# If rebasing
git rebase --continue

# If cherry-picking
git cherry-pick --continue
```

Rebase and cherry-pick may stop on a subsequent commit and introduce new conflicts. When that happens, repeat the process of inspecting, launching mergetool, saving the result, staging the file, and continuing.

If you need to abort the active operation, the corresponding commands are:

```bash
git merge --abort
git rebase --abort
git cherry-pick --abort
```

Only use an abort command when you genuinely want to cancel the entire current operation. It is not a way to mark conflicts as resolved. Before starting an integration operation, safeguard uncommitted changes to avoid losing work in progress.

## 7. Complete Example

The workflow below illustrates a merge using Meld. Assume Meld is installed and Git recognizes the tool:

```bash
# Switch to the receiving branch and start the merge
git switch main
git merge feature

# Inspect conflicted files
git status
git diff --name-only --diff-filter=U

# Open the merge tool for conflicted files
git mergetool --tool=meld

# Verify status and staged content
git status
git diff --name-only --diff-filter=U
git diff --cached

# After all conflicts are resolved and verified
git merge --continue
```

If a file is not yet staged after closing Meld, edit/save the result and run `git add -- path/to/file`. If the outcome is to delete the file, run `git rm -- path/to/file`. Only run `git merge --continue` when no unmerged paths remain and the staged diff has been reviewed.

## 8. Common Errors

| Symptom | Common cause | How to handle |
|---|---|---|
| Git reports mergetool not found | Tool is not installed or not in `PATH` | Install the tool, check `PATH`, and re-run `git mergetool --tool-help` |
| Closed the window but the file still conflicts | Tool did not save output or merge was not confirmed successful | Reopen, save output, and check `git status`; stage with `git add` if needed |
| Git asks if the merge was successful | Git is not configured to trust the tool's exit code | Answer yes only after verifying content; enable `trustExitCode` only when the exit code is reliable |
| `.orig` files appear | Git keeps a pre-merge backup | Keep while verifying; delete once sure recovery is not needed |
| Wrong LOCAL/REMOTE content chosen during rebase | Confusing rebase sides with standard merge understanding | Check `git status`, stages 2/3, and the commit being replayed |
| `git merge --continue` still reports conflicts | Unmerged files remain or an unhandled conflict exists | Run `git diff --name-only --diff-filter=U` and resolve the remaining files |

## Conclusion

Use `git mergetool` to compare base and both sides, create the MERGED content, and save the result. Then check `git status` and the staged diff to confirm Git recorded the file as resolved; if not, run `git add` or `git rm` depending on the final outcome. Once all conflicts are handled, continue with the command matching merge, rebase, or cherry-pick.

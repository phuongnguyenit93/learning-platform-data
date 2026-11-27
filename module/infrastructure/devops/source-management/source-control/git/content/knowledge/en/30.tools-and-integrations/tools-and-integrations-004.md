# Integrating External Diff and Merge Tools

When reviewing changes or resolving merge conflicts, viewing plain text diffs in the terminal alone is sometimes not visual enough. An external diff tool can display two versions side by side, highlight changed lines, and support directory comparisons. An external merge tool can display the base version, both sets of changes, and the merged result in a three- or four-pane interface.

Git supports integrating these tools via `git difftool` and `git mergetool`. Git is responsible for determining which versions to compare, creating the necessary temporary files, and updating the index after the user resolves conflicts. The external tool focuses on displaying and editing content. Understanding each component's role helps you configure the right tool, avoid accidentally overwriting changes, and properly complete a merge or rebase workflow.

In Git source code management, diff and merge tools make code reviews more accurate, reduce errors when reconciling changes from multiple branches, and support team collaboration. Tools should be configured consistently, launch cleanly from Git, and return results in a way Git understands.

## 1. How do a diff tool and a merge tool differ?

| Tool | Goal | Typical inputs | Edits the output file? |
| --- | --- | --- | --- |
| Diff tool | Compare two versions to review differences | Local version and remote/other version | Usually no; primarily for viewing |
| Merge tool | Reconcile conflicting versions | Base, local, remote, and output file | Yes; the user edits the output file |

A diff tool answers the question "where do two versions differ?". A merge tool helps answer "how should these changes be combined into the final content?".

Git has two corresponding commands:

```bash
git difftool
git mergetool
```

`git difftool` is an interface that invokes a comparison program on file pairs identified by Git. `git mergetool` invokes a program to handle files that currently have conflicts. Neither command decides which change is correct on its own; the reviewer or conflict resolver must still understand the context and choose the appropriate result.

## 2. Common tools

Several graphical tools commonly used with Git:

| Tool | Commonly supported platforms | Strengths |
| --- | --- | --- |
| Visual Studio Code | Windows, macOS, Linux | Two-file diff, integrated editor, and Merge Editor in Source Control |
| Meld | Linux, Windows, macOS depending on package | File/directory comparison and three-way merge |
| KDiff3 | Windows, Linux, macOS depending on package | Displays three versions and the merged output |
| Beyond Compare | Windows, macOS, Linux | File/directory comparison, many formats, and merge UI |
| P4Merge | Windows, macOS, Linux depending on version | Visual comparison and merging |
| Vimdiff | Anywhere Vim is available | In-terminal comparison, split windows, and fast editing |

Git can also use command-line tools like `vimdiff`. You do not have to choose the same application for diff and merge; a team might use VS Code to inspect diffs while using KDiff3 or Meld to resolve conflicts.

Before configuring, install the tool and confirm the command runs from the terminal. Some applications may require adding their installation directory to `PATH` or specifying the executable path in Git config.

## 3. Checking which tools Git recognizes

List diff tools Git knows how to invoke:

```bash
git difftool --tool-help
```

List merge tools:

```bash
git mergetool --tool-help
```

The list varies by Git version and platform. A tool appearing in the list does not mean the application is installed on your machine; Git may recognize the tool name but fail to find the executable when running it.

Check current configuration:

```bash
git config --show-origin --get diff.tool
git config --show-origin --get merge.tool
git config --show-origin --get-regexp '^difftool\.'
git config --show-origin --get-regexp '^mergetool\.'
```

The `--show-origin` commands show whether a value comes from system, global, or local configuration. This is helpful when tools are configured at multiple levels and actual behavior differs from expectations.

## 4. Configuring the default diff tool

Git stores the default diff tool name in `diff.tool`. For example, using Meld:

```bash
git config --global diff.tool meld
```

Or using Vimdiff:

```bash
git config --global diff.tool vimdiff
```

This setting applies only to the current user account. If you want it to apply only to the current repository, replace `--global` with `--local`.

Run the diff tool:

```bash
git difftool
```

Git will compare the working tree against the index by default. You can specify two commits or revisions:

```bash
git difftool main feature/payment
```

This command opens the tool for files that differ between the two branches. You can limit it to a specific path:

```bash
git difftool main feature/payment -- src/PaymentService.java
```

### Comparing staged and unstaged changes

```bash
# Changes in the working tree compared to the index
git difftool

# Staged changes compared to HEAD
git difftool --cached

# Compare two commits
git difftool HEAD~1 HEAD
```

The version pairs match `git diff` usage: the default shows unstaged changes; `--cached` or `--staged` shows staged changes; two revisions show differences between snapshots.

## 5. Configuring the default merge tool

Git stores the default merge tool in `merge.tool`. For example, using Meld:

```bash
git config --global merge.tool meld
```

Or KDiff3:

```bash
git config --global merge.tool kdiff3
```

Once configured, when conflicts occur, run:

```bash
git mergetool
```

Git opens the tool for each conflicted file. To pick a different tool for a single run:

```bash
git mergetool --tool=kdiff3
```

The `--tool` option does not permanently change the default configuration. To save a default, update `merge.tool` with `git config`.

If Git cannot find the executable automatically, check `PATH` or configure the specific path for the tool using `mergetool.<tool>.path`. For example, when Git needs to invoke an executable outside `PATH`, you can set an absolute path:

```bash
git config --global mergetool.kdiff3.path "/path/to/kdiff3"
```

Replace the example path with the application's actual location on your machine. Path syntax and executable names vary across Windows, macOS, and Linux.

## 6. Using VS Code to view diffs

VS Code has a built-in file comparison UI. If the `code` command is in `PATH`, you can configure a custom diff tool:

```bash
git config --global diff.tool vscode
git config --global difftool.vscode.cmd 'code --wait --diff "$LOCAL" "$REMOTE"'
```

Git provides two environment variables for custom diff commands:

- `$LOCAL`: the file version on the local side of the comparison.
- `$REMOTE`: the file version on the other side of the comparison.

`--diff` tells VS Code to open both files in comparison mode; `--wait` instructs the CLI process to wait until the diff window closes so Git manages the command lifecycle properly.

Try it:

```bash
git difftool --tool=vscode HEAD~1 HEAD
```

If Git prompts to confirm opening each file, you can adjust the prompt setting for diff tools:

```bash
git config --global difftool.prompt false
```

Disable the prompt only once you are comfortable with Git automatically opening every changed file. For large changes, keeping the prompt can help you review each file before opening it.

## 7. Using VS Code Merge Editor to resolve conflicts

VS Code provides a Merge Editor in the Source Control UI. When a file has conflicts, open it from the Merge Changes list or choose Open in Merge Editor. The UI shows changes from both sides alongside the merged output, helping you select or edit each region.

Basic workflow:

1. Run a merge or rebase so Git detects conflicts.
2. Open the repository in VS Code.
3. In Source Control, select a file under Merge Changes.
4. Open the Merge Editor if VS Code detects the conflict.
5. Inspect content from both sides, accept appropriate changes, or edit the result directly.
6. Save the result file.
7. Check the diff and run relevant tests.
8. Stage the resolved file via Source Control or `git add`.
9. Continue the merge/rebase according to Git's state.

VS Code may display buttons such as Accept Current, Accept Incoming, or Accept Both. Button names and positions may vary by version and conflict type. Do not accept options blindly just to make conflict markers disappear; understand both sides before accepting.

The Merge Editor is an interface for editing the output. Saving the file does not automatically complete the merge or rebase; Git still requires the file to be staged and the corresponding continue command to be run.

## 8. Understanding BASE, LOCAL, REMOTE, and MERGED

When invoking a custom merge tool, Git can provide these environment variables:

| Variable | Meaning |
| --- | --- |
| `$BASE` | Common base version before both sides diverged |
| `$LOCAL` | Version on the current side that Git treats as local in the merge operation |
| `$REMOTE` | Version from the side being merged in |
| `$MERGED` | Path to the output file where the tool should write the merged content |

In a regular merge, `LOCAL` usually corresponds to the current branch (ours), while `REMOTE` corresponds to the branch being merged in (theirs). However, during a rebase or certain other operations, the meaning of "ours/theirs" can be counterintuitive because Git is replaying commits onto a new base. Rely on Git's messages and the contents of each version rather than assuming `ours` is always your feature branch.

For a three-way content conflict, Git typically has:

- Base: content at the common ancestor before both sides made edits.
- Local: content from the current side.
- Remote: content from the side being integrated.
- Merged: final output produced by the user or tool.

Some tools display four panes so the user can view all three inputs plus the result. Two-way tools can still work, though the conflict resolver must manually cross-check the base and both sides to understand the changes.

## 9. Conflicted file stages in the Git index

When a file has a conflict, Git stores multiple versions in the index instead of a single normal staged entry. Three key stages:

| Stage | Content |
| --- | --- |
| `:1:path` | Base, the common version before branching |
| `:2:path` | Ours, the local/current side in the active operation |
| `:3:path` | Theirs, the incoming side |

View unresolved entries:

```bash
git ls-files -u
```

Inspect each version:

```bash
git show :1:src/PaymentService.java
git show :2:src/PaymentService.java
git show :3:src/PaymentService.java
```

These commands help you inspect input data before opening a merge tool. For add/add or modify/delete conflicts, some stages may not exist; not every conflicted file has all three stages 1, 2, and 3.

When running via `git mergetool`, Git usually marks the file as resolved (staged) once it detects the tool exited successfully. With custom tools, this depends on the exit code, changes to the output file, and `mergetool.<tool>.trustExitCode`. If you open the Merge Editor directly from an IDE instead of running `git mergetool`, stage the file after checking the result:

```bash
git add src/PaymentService.java
```

`git add` replaces the unmerged entries with a normal entry in the index. Verify:

```bash
git status --short
git ls-files -u
```

If `git ls-files -u` no longer lists the handled file, its conflict entries have been cleared from the index. You still need to review the content before continuing.

## 10. Configuring a custom merge tool

Git lets you define a custom command when a tool is not built in. General configuration example:

```bash
git config --global merge.tool mymerge
git config --global mergetool.mymerge.cmd 'my-merge-app "$LOCAL" "$BASE" "$REMOTE" --output "$MERGED"'
```

This is an illustrative template, not a built-in executable name. Replace `my-merge-app` with the actual application and adjust parameter order according to the application's documentation. The tool must write the final result to `$MERGED` and return an appropriate exit code.

Useful settings:

```bash
git config --global mergetool.prompt true
git config --global mergetool.keepBackup true
git config --global mergetool.keepTemporaries false
```

- `mergetool.prompt`: prompt before opening each conflicted file.
- `mergetool.keepBackup`: keep `.orig` backup files after the merge tool succeeds; usually `true` by default.
- `mergetool.keepTemporaries`: keep temporary files Git creates for the merge tool; usually `false` by default.

Do not disable backups until you understand the workflow and have another recovery mechanism. `.orig` files can be helpful when you need to compare the merged output against the content before running the tool. After verifying the result, you can delete backup files per workspace policy.

## 11. Controlling how Git trusts merge tool results

Git needs to know whether the tool resolved the conflict successfully. `mergetool.<tool>.trustExitCode` controls whether Git trusts the tool's exit code.

Example:

```bash
git config --global mergetool.meld.trustExitCode true
```

When `trustExitCode` is `true`, Git relies on the program's exit code to determine the outcome. Without this option enabled, Git checks the modification timestamp of the output file; if the file was not updated, Git asks the user to confirm whether the merge succeeded. Only set `true` if the application returns reliable exit codes and returns success only after writing a valid result.

If a tool closes without writing the output file, or returns a success exit code even though conflicts remain unresolved, Git may need additional verification. Always inspect `$MERGED`, `git status`, and unmerged entries before continuing.

## 12. Running difftool and mergetool with options

Useful commands:

```bash
# Run diff with the default tool
git difftool

# Choose a specific tool for this run
git difftool --tool=meld HEAD~1 HEAD

# Compare staged files
git difftool --cached

# Run merge tool with the default tool
git mergetool

# Choose a specific merge tool
git mergetool --tool=kdiff3

# Open each conflicted file with default prompt
git mergetool
```

`git difftool` supports options similar to `git diff` for revisions and pathspecs. `git mergetool` only processes files Git currently records as unmerged; if there are no conflicts, the command may not open any tool.

To view exact invocation details for your installed version:

```bash
git help difftool
git help mergetool
```

## 13. Conflict resolution workflow using a merge tool

Suppose you are merging `feature/payment` into `main`:

```bash
git switch main
git merge feature/payment
```

If Git reports conflicts, check status:

```bash
git status
git diff --name-only --diff-filter=U
```

Open the merge tool:

```bash
git mergetool
```

For each file:

1. Read base to understand the content before the two branches diverged.
2. Compare local and remote, identifying the goal of each change.
3. Combine valid content into the output pane.
4. Check imports, syntax, conditions, and related changes.
5. Save the output file and close the tool.

After resolving:

```bash
git status --short
git diff
git diff --cached
git ls-files -u
```

When `git mergetool` detects successful resolution, Git usually stages the file automatically. If you opened the Merge Editor directly in an IDE or the file remains unmerged, check the result and stage manually:

```bash
git add src/PaymentService.java
```

Once all files are resolved and staged, re-check and complete the merge:

```bash
git status
git diff --check
git commit
```

If Git is in a merge state with a prepared message, you can use `git merge --continue` to finish the current workflow. `git commit` can also complete the merge once all conflicts are resolved and staged. Do not use `git commit` to skip tests or code review.

## 14. Conflict resolution workflow during rebase

During a rebase, Git replays the current branch's commits one by one onto a new base. If a conflict occurs:

```bash
git status
git mergetool
```

Resolve the file, verify the index state, then continue:

```bash
git status --short
git ls-files -u
git rebase --continue
```

If you opened the tool from an IDE instead of calling `git mergetool`, stage the resolved file with `git add src/PaymentService.java`. When using `git mergetool`, Git typically stages the file after confirming the tool completed successfully.

If you need to skip the commit currently being replayed:

```bash
git rebase --skip
```

If you want to abort the entire rebase session and return to the state before starting:

```bash
git rebase --abort
```

Do not confuse `git mergetool` with the rebase continue command. The merge tool only edits the file and helps clear the unmerged state; `git rebase --continue` advances the rebase process itself.

During a rebase, ours/theirs labels can feel backward to beginners: `ours` is usually the base/upstream onto which commits are being replayed; `theirs` is usually the feature commit being applied. Inspect `git status`, `git show :2:path`, `git show :3:path`, and rebase messages to identify each side accurately.

## 15. Diff tools in code review workflows

Diff tools are useful before committing, before pushing, and when reviewing pull requests. For example:

```bash
# View unstaged changes
git difftool

# View changes that will go into the commit
git difftool --cached

# View changes between current branch and main
git difftool origin/main...HEAD
```

With `origin/main...HEAD`, Git compares from the merge-base to `HEAD`, which is typically useful for viewing changes unique to the current branch relative to the base branch. Verify the merge-base properly if history has multiple branches or has been rebased.

A diff tool does not replace tests, linting, security checks, or logic review. A diff may look small yet alter critical behavior; read call contexts, input data, and impacts on other modules.

## 16. Common issues

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Git says tool not found | Application not installed or executable not in `PATH` | Install the app, verify standalone execution, and configure `*.path` if needed |
| `git difftool` opens editor instead of diff mode | Custom command missing diff flag or file arguments | Check `difftool.<tool>.cmd` and how `$LOCAL`, `$REMOTE` are passed |
| Git does not wait for the app to close | Command lacks wait mode or parent process exits early | Use the app's wait flag, e.g. `--wait` for VS Code |
| `git mergetool` opens no files | Index has no unmerged entries | Check `git status` and `git ls-files -u` |
| Merge tool opens wrong versions | Confused local/remote or handling a rebase | Check base, stages 2/3, and Git messages before editing |
| Closed tool but Git still reports conflict | Output file not staged or tool did not write `$MERGED` | Save result, verify file, and run `git add` |
| Git asks if merge succeeded even though tool exited cleanly | `trustExitCode` disabled or tool exit code ambiguous | Check config and verify content before answering |
| `.orig` files remain | `mergetool.keepBackup` is enabled | Inspect result and remove backups once confirmed unneeded |
| Merge finished but app does not run | Wrong merged content chosen or related changes missed | Run tests, check diff, and fix result before finalizing |

## 17. Safety principles when using external tools

- Only run tools installed from trusted sources and approved by your organization.
- Verify the right repository and file before confirming writes.
- Keep `.orig` backups or copies until you are confident in the merged result.
- Do not blindly accept all "ours", "theirs", or "both" without understanding the impact.
- Do not stage all files with `git add .` when unreviewed files remain.
- After merging, run tests and `git diff --check` to catch formatting or whitespace errors.
- For binary files, use a tool capable of viewing/merging that format; Git cannot produce meaningful merged output using plain text merge.
- Do not open files containing secrets in tools with cloud sync or unapproved plugins.

## 18. Team setup checklist

1. Choose diff tools and merge tools supported by the team.
2. Install the same or compatible versions across team machines.
3. Configure `diff.tool` and `merge.tool` at the appropriate scope.
4. If using a custom command, verify `$LOCAL`, `$REMOTE`, `$BASE`, and `$MERGED` variables.
5. Ensure the tool waits for completion and returns an appropriate exit code.
6. Standardize whether `.orig` files are kept or cleaned up.
7. Document how to open the Merge Editor and stage files after resolution.
8. Agree that merge/rebase only continues after verifying conflicts and running tests.

You do not necessarily need to force every developer to use the same GUI. What matters is that everyone understands the Git flow, knows how to verify results, and does not let tools make business-logic decisions automatically.

## 19. Hands-on practice

Practice in a test repository:

1. Install a diff tool such as VS Code, Meld, or KDiff3.
2. Configure `diff.tool` and run `git difftool HEAD~1 HEAD`.
3. Compare staged and unstaged changes using `git difftool --cached` and `git difftool`.
4. Create two branches that edit the same region of a file.
5. Merge the two branches to trigger a conflict.
6. Run `git status` and `git ls-files -u` to inspect the unmerged state.
7. Open the conflict using `git mergetool` or VS Code's Merge Editor.
8. Inspect base, local, remote, and result; combine the content manually.
9. Save the file, stage with `git add`, and confirm `git ls-files -u` returns no entries.
10. Run tests and complete the merge.
11. Repeat the exercise with rebase to recognize the difference between `git merge --continue` and `git rebase --continue`.

## 20. Knowledge check

1. What two distinct goals do `git difftool` and `git mergetool` serve?
2. How do `diff.tool` and `merge.tool` configurations differ?
3. Which files do `$LOCAL`, `$REMOTE`, `$BASE`, and `$MERGED` represent?
4. Why is the `--wait` flag needed when integrating some editors?
5. Which stages does the Git index store when a file is in conflict?
6. Why does saving a file in the Merge Editor not complete the merge?
7. How does `mergetool.<tool>.trustExitCode` affect how Git confirms the result?
8. Why must you be careful with ours/theirs semantics during a rebase?
9. When should `.orig` files be kept?
10. After resolving conflicts, what checks and commands should be run before continuing a merge or rebase?

## Conclusion

`git difftool` integrates Git with a comparison viewer to review two versions; `git mergetool` passes conflicted files to a content reconciliation tool. Configuring `diff.tool`, `merge.tool`, and `difftool.*`/`mergetool.*` settings helps Git launch the right application. When resolving conflicts, understand base, local, remote, and the output file, save and stage the verified content, and only then continue the merge or rebase. Tools assist with viewing and editing; choosing the right content still belongs to the operator and must be verified with diffs, tests, and reviews.

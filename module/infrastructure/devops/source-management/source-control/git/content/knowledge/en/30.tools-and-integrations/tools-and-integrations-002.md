# Mapping UI Actions to status, diff, and log

IDEs and Git GUI applications help you view changed files, stage partial edits, create commits, switch branches, and read history through visual interactions. However, the UI is just one way of interacting with a repository. Behind every button are specific Git states and operations.

When you understand how to map UI actions to the three command groups `status`, `diff`, and `log`, you can check exactly what is happening, spot differences between staged and unstaged changes, verify whether a commit contains the right content, and investigate history when the UI display is unclear.

The key principle is to always determine the state of `HEAD`, the index, and the working tree before drawing conclusions. A file list with dots or colors in an IDE is no substitute for understanding where Git is storing changes.

## 1. What is the Git UI displaying?

Most IDEs have panels such as Changes, Source Control, Commit, Branches, History, or Log. Names and layouts differ across tools, but they typically reflect the same Git model.

~~~text
                  HEAD
          current branch commit
                    |
                    v
              ┌──────────┐
              │  Index   │  <- Staging area
              └──────────┘
                    |
                    v
              ┌──────────┐
              │ Working  │
              │  tree    │
              └──────────┘

HEAD vs. Index: staged content (git diff --cached)
Index vs. Working tree: edited but unstaged content (git diff)
~~~

- **HEAD:** the commit the repository is currently positioned at, usually via the current branch.
- **Index (staging area):** the next snapshot that will be included in a commit.
- **Working tree:** the actual files on disk, which may differ from the content in the index or a commit.

UIs typically group files into Staged Changes and Changes. The Staged Changes group corresponds to the difference between the index and HEAD; the Changes group usually corresponds to the difference between the working tree and the index.

Some tools merge or hide these groups. When unsure, use `status` and `diff` to confirm.

## 2. Map of UI actions and Git commands

The table below maps common actions. Button names may vary across VS Code, Visual Studio, IntelliJ IDEA, Android Studio, GitKraken, and other GUIs.

| UI action | Meaning in Git | Command to check or execute |
|---|---|---|
| Refresh / Refresh Changes | Re-read repository state | git status |
| Stage file | Put file content into the index | git add &lt;path&gt; |
| Stage hunk / Stage selected lines | Stage only part of a diff | git add -p |
| Unstage file | Remove content from index, keep edits in working tree | git restore --staged -- &lt;path&gt; |
| Unstage hunk | Remove part of changes from the index | git restore --staged -p -- &lt;path&gt; |
| Discard changes | Restore working tree file to match index | git restore -- &lt;path&gt; |
| Discard selected hunk | Discard part of unstaged edits | git restore -p -- &lt;path&gt; |
| View staged diff | View content that will be committed | git diff --cached |
| View unstaged diff | View unstaged content | git diff |
| Commit | Create a commit from the index | git commit |
| View commit details | View metadata and patch of a commit | git show &lt;commit&gt; |
| Open history / Log | View reachable commits | git log |
| Compare branches | Compare two refs or two branches | git diff &lt;base&gt;...&lt;branch&gt; |
| Create branch | Create a new branch | git branch &lt;name&gt; or git switch -c &lt;name&gt; |
| Checkout / Switch branch | Switch branch | git switch &lt;name&gt; |
| Fetch | Retrieve objects and update remote-tracking refs | git fetch &lt;remote&gt; |
| Pull | Fetch then integrate into current branch | git pull |

This is a semantic mapping. A Sync, Update, or Commit & Push button may run multiple commands in sequence. Check the tool's details or output if you need to know the exact command sequence.

## 3. Reading state with git status

The Changes panel in an IDE is usually built from the status returned by Git. When you need an independent check, start with:

~~~sh
git status
git status -sb
git status --short
~~~

- git status provides full information, including branch, staging state, unstaged changes, untracked files, and conflicts.
- git status -sb shows the branch along with compact status.
- git status --short uses a two-column format to make index and working tree changes easy to distinguish.

### 3.1. Understanding the two columns in status --short

Each line in short format has the structure:

~~~text
XY path
~~~

- X describes the status in the index (staging area).
- Y describes the status in the working tree compared to the index.

Examples:

| Symbol | Meaning |
|---|---|
| M  file.txt | File has staged changes |
|  M file.txt | File is modified but not staged |
| MM file.txt | File has staged changes and further modifications in the working tree |
| A  file.txt | New file is staged |
| D  file.txt | File deletion is staged |
|  D file.txt | File is deleted in the working tree but deletion is not staged |
| ?? file.txt | Untracked file |
| UU file.txt | File has an unresolved conflict |

For renames or copies, Git may show R or C along with source/destination paths depending on format and configuration. For conflicts, the two characters in the two columns represent the state of both sides; use full git status to view resolution guidance.

Example:

~~~text
 M src/order-service.ts
M  README.md
MM package.json
?? notes.txt
~~~

Interpretation:

- order-service.ts has unstaged modifications.
- README.md is staged.
- package.json has staged content and newer unstaged modifications.
- notes.txt is not tracked by Git.

### 3.2. Why does a file appear in two groups?

Suppose you edit package.json, stage it in the IDE, and then continue editing it. The index still holds the snapshot from the first stage; the working tree contains newer content. Git shows MM because both areas differ.

Inspect:

~~~sh
git diff --cached -- package.json
git diff -- package.json
~~~

The first command shows the staged portion. The second command shows the edits made after staging. The two portions can be placed into two separate commits if desired.

### 3.3. Untracked and ignored files

New files may appear in the IDE without being staged yet. Confirm with:

~~~sh
git status --short
~~~

Ignored files usually do not appear in the default list. To view them:

~~~sh
git status --short --ignored
git check-ignore -v path/to/file
~~~

If the GUI does not show a file, do not conclude that the file does not exist. The file may be ignored, hidden by an IDE filter, or located outside the repository.

### 3.4. Viewing branch and remote status

~~~sh
git status -sb
git branch -vv
git fetch origin
git status -sb
~~~

Status may report that the current branch is ahead or behind its upstream. These numbers are based on the most recently fetched remote-tracking ref. If you have not fetched, the numbers shown in the GUI may be stale.

Fetch only updates information from the remote; it does not automatically merge or rebase changes into the current branch.

## 4. Mapping Stage and Unstage

The Stage button in an IDE usually corresponds to git add. Staging does not create a commit; it selects the content to include in the next commit.

### 4.1. Staging a file

UI: select the file under Changes and click Stage.

CLI:

~~~sh
git add src/order-service.ts
git status --short
git diff --cached -- src/order-service.ts
~~~

After staging, the file usually moves from Changes to Staged Changes. The staged diff should reflect the exact content you want to commit.

### 4.2. Unstaging a file

UI: click Unstage or move the file out of Staged Changes.

CLI:

~~~sh
git restore --staged -- src/order-service.ts
~~~

This command restores the file's content in the index to its state in HEAD. Modifications in the working tree are preserved. Check:

~~~sh
git status --short
git diff -- src/order-service.ts
~~~

### 4.3. Staging part of the changes

Many GUIs let you stage individual hunks or lines. The CLI equivalent is:

~~~sh
git add -p src/order-service.ts
~~~

Git displays each diff hunk and asks whether to stage it. This is a way to create small commits that separate different change intents within the same file.

Verify after partial staging:

~~~sh
git diff --cached -- src/order-service.ts
git diff -- src/order-service.ts
~~~

Both diffs should show the intended staged and unstaged portions. Do not rely solely on line coloring in the GUI.

### 4.4. Unstaging partially

You can use patch mode to choose which parts to remove from the index:

~~~sh
git restore --staged -p -- src/order-service.ts
~~~

This command only modifies the index according to your selections; edits in the working tree remain intact. Afterward, review both the staged diff and the unstaged diff.

## 5. Mapping Discard and Restore

The Discard button usually deletes modifications. You must determine whether the GUI discards staged changes, unstaged changes, or both.

### 5.1. Discarding unstaged modifications

CLI:

~~~sh
git restore -- src/order-service.ts
~~~

This command restores the working tree to match the index. If the file has both staged and unstaged parts, it discards the unstaged part and keeps the staged content.

### 5.2. Discarding part of unstaged modifications

~~~sh
git restore -p -- src/order-service.ts
~~~

Git lets you choose individual hunks to restore. Check the diff before and after to ensure the parts you want to keep are not discarded.

### 5.3. Discarding both staged and unstaged content?

Do not use a generic Discard button when you are unsure of its scope. If the goal is to discard all changes to a file back to the current commit state, the operation must affect both the index and the working tree. You can use:

~~~sh
git restore --source=HEAD --staged --worktree -- src/order-service.ts
~~~

This command resets both the index and the working tree to match HEAD. Uncommitted content in the file can be lost. Run it only after inspecting and backing up anything you need to keep.

## 6. Mapping IDE Diff to git diff

Diff is how you inspect differences between two states. When opening a file's diff tab in a GUI, you need to know which two sides are being compared.

| Purpose | Command | Two sides compared |
|---|---|---|
| View unstaged modifications | git diff | Index vs. working tree |
| View staged content | git diff --cached | HEAD vs. index |
| View all changes vs. current commit | git diff HEAD | HEAD vs. working tree |
| View changed file names | git diff --name-only | List of paths in the diff |
| View changed file statuses | git diff --name-status | Added/modified/deleted/renamed status |
| View statistics | git diff --stat | Lines added/removed per file |
| Check whitespace | git diff --check | Whitespace errors in the diff |

### 6.1. When the GUI displays the diff of an edited file

A diff tab may compare:

- The version in HEAD vs. the working tree version.
- The version in the index vs. the working tree version.
- The version in HEAD vs. the index version.
- Two selected commits or two selected branches.

If unclear, run each command:

~~~sh
git diff -- path/to/file
git diff --cached -- path/to/file
git diff HEAD -- path/to/file
~~~

Compare the output against the diff tab. Do not assume every tab named Changes shows the exact same scope.

### 6.2. Comparing branches like in a pull request

To see changes on a feature branch since it diverged from main:

~~~sh
git diff main...feature/report
~~~

With git diff, the triple-dot syntax compares the tip of the second branch with the merge-base of the two branches. This is usually close to the changes proposed in a pull request.

To see commits present on feature that are not yet on main:

~~~sh
git log --oneline main..feature/report
~~~

The two commands answer different questions: diff shows the content changes; log shows which commits produced those changes.

### 6.3. Viewing diffs by output format

~~~sh
git diff --stat
git diff --name-status
git diff --numstat
git diff --word-diff
~~~

These options help quickly inspect the scope of changes before opening the full patch. However, they can still expose internal file names or metadata if shared.

## 7. Mapping GUI Commit to Git

The Commit panel usually lets you enter a message, choose staged files, and click Commit. Git creates a commit from the content in the index, not from every change currently in the working tree.

### 7.1. Confirming what will be committed

Before clicking Commit:

~~~sh
git status
git diff --cached
git diff --cached --check
~~~

- Status confirms which files are staged.
- Diff confirms the exact content in the index.
- Diff check catches common whitespace mistakes.

If the GUI has a Commit All button, verify whether it automatically stages all files. Some tools stage every change before committing; others only commit already-selected content.

### 7.2. Committing and verifying the result

CLI:

~~~sh
git commit -m "feat(order): add order search"
git status -sb
git show --stat --oneline HEAD
~~~

After committing:

- HEAD points to the new commit.
- The index normally returns to a state matching the new commit.
- Unstaged changes may still remain in the working tree.
- Unselected files may still appear in status.

If the GUI reports commit success while status still shows modified files, check whether they are edits made after staging, unstaged files, or new untracked files.

### 7.3. Viewing commit contents

~~~sh
git show --format=fuller --stat HEAD
git show --format=fuller HEAD
~~~

The first command shows metadata and statistics. The second shows the full patch as well. This is how you confirm the author, committer, message, and content actually recorded in the commit.

## 8. Reading history with git log

The History or Log view in an IDE typically shows a list of commits, branch graph, tags, and metadata. That information comes from the history Git can reach through refs.

### 8.1. Viewing basic logs

~~~sh
git log
git log --oneline
git log --oneline --decorate --graph --all
~~~

- git log shows detailed commit information.
- --oneline condenses each commit to a single line.
- --decorate shows branches and tags pointing to commits.
- --graph draws branching and merge relationships.
- --all traverses commits reachable from the refs Git inspects.

### 8.2. Viewing a specific commit

~~~sh
git show <commit-sha>
git show --stat <commit-sha>
git show --name-status <commit-sha>
~~~

When clicking a commit in a GUI, inspect the patch details and file list. Use git show to confirm the exact commit SHA and contents.

### 8.3. Filtering history

~~~sh
git log --author="An"
git log --since="2026-01-01" --until="2026-12-31"
git log --grep="order"
git log -- path/to/file
~~~

Filters in a GUI typically correspond to these conditions. Note that the author filter matches author metadata, not code content; grep searches commit messages; path filtering limits history to commits affecting that path.

### 8.4. File history and renames

~~~sh
git log --follow --oneline -- path/to/file
git log -p --follow -- path/to/file
~~~

--follow attempts to continue tracking history across file renames. It applies to a single path at a time and has some limitations with complex histories.

Some IDEs display file history but may not stitch together every rename. When investigating, use log --follow and verify specific commits.

## 9. Mapping branch graph and ahead/behind

The graph in a GUI helps visualize branches and merges. To verify via CLI:

~~~sh
git log --oneline --graph --decorate --all
git branch -vv
git status -sb
~~~

A branch may be shown as:

- Ahead: has local commits not yet on upstream.
- Behind: upstream has commits not yet integrated into the local branch.
- Diverged: both sides have distinct commits.

Ahead/behind counts are based on fetched remote-tracking refs. If you have not fetched, the UI may display outdated counts.

To view commits present only on one side:

~~~sh
git log --oneline "HEAD..@{upstream}"
git log --oneline "@{upstream}..HEAD"
~~~

The first command lists commits on upstream that HEAD does not have; the second lists local commits that upstream does not have. If the branch has no upstream configured, `@{upstream}` cannot be resolved.

## 10. Mapping Fetch, Pull, and Push actions

Some GUIs bundle synchronization actions into a Sync button. You need to understand the underlying commands:

| Action | Command | Effect |
|---|---|---|
| Fetch | git fetch origin | Updates objects and remote-tracking refs |
| Default Pull | git pull | Fetches then integrates upstream branch per configuration |
| Pull with rebase | git pull --rebase | Fetches then rebases local commits onto upstream |
| Push | git push | Sends local commits/refs to the remote |

Before pulling:

~~~sh
git status -sb
git fetch origin
git log --oneline --graph --decorate "HEAD...@{upstream}"
git diff "HEAD...@{upstream}"
~~~

The log command with three dots shows commits present on only one of the two sides. The three-dot diff compares upstream content against the merge-base per git diff semantics; do not confuse the two meanings of triple-dot syntax.

After Pull or Push, verify again:

~~~sh
git status -sb
git log --oneline --decorate -5
git branch -vv
~~~

If the GUI reports Sync succeeded while the branch is still ahead/behind, determine whether it executed fetch, pull, push, or only part of the sequence.

## 11. Mapping conflict resolution

When a merge or rebase hits a conflict, GUIs typically mark the files needing resolution and offer choices to keep Current, Incoming, or Both. These labels depend on the tool's perspective and the operation in progress.

Check status:

~~~sh
git status
git diff
git diff --cc
~~~

After editing conflicts, stage the resolved file:

~~~sh
git add path/to/conflicted-file
git status
~~~

If merging:

~~~sh
git merge --continue
~~~

If rebasing:

~~~sh
git rebase --continue
~~~

Do not click Continue simply because conflict markers are gone from the file. Read the diff, run tests, and verify the logic from both sides.

If you need to cancel:

~~~sh
git merge --abort
git rebase --abort
~~~

Only run the command matching the operation in progress. Abort can restore the state prior to the merge/rebase, though pre-existing changes should still be reviewed.

## 12. Verification workflow before and after a GUI action

A helpful habit is checking via CLI at key points.

### 12.1. Before staging or committing

~~~sh
git status -sb
git diff
git diff --cached
~~~

The goal is to know which files are new, which are staged, and what content will be committed.

### 12.2. After staging

~~~sh
git status --short
git diff --cached --stat
git diff --cached
~~~

The goal is to confirm the index contains the exact intended changes.

### 12.3. After committing

~~~sh
git status -sb
git show --stat --oneline HEAD
git show --format=fuller --no-ext-diff HEAD
~~~

The goal is to confirm the new commit and its contents while spotting any remaining modifications.

### 12.4. After remote synchronization

~~~sh
git fetch origin
git status -sb
git branch -vv
git log --oneline --graph --decorate --all -20
~~~

The goal is to confirm the branch and remote-tracking ref are in the expected state.

## 13. When the UI and CLI display different things

If the IDE and Git commands appear out of sync, check in order:

1. **Open repository:** the IDE may have a subdirectory or a different repository open in the workspace.
2. **Refresh:** the UI may not have re-read the filesystem after changes from the terminal or another tool.
3. **Index and working tree:** a file may have both staged and unstaged changes.
4. **Ignored and untracked:** IDE filters may be hiding files.
5. **Submodule:** the parent repository displays a gitlink, while file contents live inside the child repository.
6. **Rename detection:** the GUI and Git may pair renames differently based on similarity thresholds.
7. **Whitespace and line endings:** display filters may hide CRLF/LF or whitespace differences.
8. **External diff tool:** the IDE may use a separate diff tool with different presentation.
9. **Git executable and config:** the IDE may use a different Git binary, environment, or configuration than the terminal.

Check:

~~~sh
git rev-parse --show-toplevel
git rev-parse --git-dir
git --version
git config --show-origin --get core.autocrlf
git config --show-origin --get core.pager
~~~

Do not assume the CLI and IDE share the same environment if the IDE has its own Git executable or environment configuration. When spotting discrepancies, inspect the repository root and actual configuration before modifying files.

## 14. Useful status, diff, and log commands to remember

| Need | Command |
|---|---|
| View repository overview | git status -sb |
| View short status | git status --short |
| View ignored files | git status --short --ignored |
| View unstaged edits | git diff |
| View staged edits | git diff --cached |
| View all changes vs. HEAD | git diff HEAD |
| View changed file names | git diff --name-status |
| View change statistics | git diff --stat |
| Check whitespace | git diff --check |
| View log as a graph | git log --oneline --graph --decorate --all |
| View latest commit | git show --stat HEAD |
| View a file's history | git log --follow -- path/to/file |
| View commits on feature branch | git log --oneline main..feature |
| View branch diff from divergence point | git diff main...feature |

These commands are enough to verify most information that appears in an IDE's Source Control, Changes, Diff, and History panels.

## 15. Common misconceptions

**Seeing a file in Changes and assuming it is staged.** Check the X/Y columns with git status --short. The file may only be modified in the working tree.

**Seeing a file in Staged Changes and assuming all edits are staged.** The file may have status MM if further edits were made after staging. Inspect both git diff --cached and git diff.

**Clicking Commit All without checking the index.** Some GUIs auto-stage every file; others only commit staged content. Check status and staged diff before committing.

**Thinking Discard only deletes what is currently visible.** The button may discard the entire file or both staged and unstaged parts depending on the tool. Read the confirmation prompt and check scope.

**Comparing two branches with log and concluding their contents match.** Log shows commits; diff shows whether file contents differ.

**Trusting ahead/behind counts without fetching.** Remote-tracking refs may be stale. Fetch first, then re-check.

**Assuming GUI and terminal always use the same Git.** The IDE may use a different Git binary or configuration. Check repository root and config when discrepancies occur.

**Ignoring ignored files because they do not appear in the list.** Use status --ignored or check-ignore to identify them.

## 16. Checklist for working with Git GUI and CLI

**Before making changes**

- [ ] Confirm repository root and current branch.
- [ ] Refresh status in the IDE.
- [ ] Run git status -sb.
- [ ] Distinguish staged, unstaged, untracked, and ignored files.

**Before committing**

- [ ] Review git diff.
- [ ] Review git diff --cached.
- [ ] Confirm the right files and hunks are staged.
- [ ] Run git diff --cached --check.
- [ ] Check the commit message.

**After committing**

- [ ] View git show --stat HEAD.
- [ ] Confirm commit contents.
- [ ] Run git status -sb to spot any remaining changes.

**When viewing history or syncing**

- [ ] Use git log to confirm commits and branches.
- [ ] Fetch before trusting ahead/behind counts.
- [ ] Use diff to compare content, log to compare history.
- [ ] Check conflicts with status and diff before continuing.

## 17. Conclusion

Git UIs provide visual operations, while status, diff, and log provide independent verification. Status tells you whether changes are in the index or working tree; diff tells you how contents differ between states; log tells you commits and historical relationships.

Once you understand these three command groups, you can map Stage, Unstage, Discard, Commit, History, Fetch, and Sync buttons to Git's actual behavior. Inspect the staged diff before committing, review commits after creating them, and fetch before evaluating remote status. That habit prevents committing the wrong files, losing edits, or misinterpreting what the UI is showing.
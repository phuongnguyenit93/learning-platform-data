# Combining Git CLI with GUI Clients and IDEs

## Why combine multiple Git interfaces?

Git is a version control system. The command line, graphical user interface (GUI) clients, and Git integrations built into IDEs are simply different ways to interact with the same repository.

You can use the terminal to check exact status, inspect history, or perform less common operations; then use an IDE to view diffs alongside source code, stage partial changes, and resolve conflicts with a visual editor. Conversely, you can create branches and commit in a GUI, then use Git commands to verify the result.

Combining interfaces is useful because:

- The terminal provides explicit commands that can be documented and repeated in documentation or scripts.
- A GUI presents branches, commits, diffs, and file statuses visually.
- An IDE places Git changes right next to source code, flags syntax errors, and supports navigating across files.
- Graphical tools often make comparing two versions and handling conflicts easier to inspect.
- The command line helps inspect cases where a UI hides details or does not provide full support.

The key point is that all interfaces operate on the same working tree, index, repository, and refs. When one interface stages a file, another interface sees that staged state after refreshing or re-reading the repository. There is no separate set of commits for the IDE and a separate set of commits for the terminal.

## Understanding state areas before switching interfaces

To coordinate accurately, you need to know where Git stores changes:

~~~text
                ┌────────────────────┐
                │   Working tree     │
                │  Files being edited│
                └─────────┬──────────┘
                          │ git add
                          v
                ┌────────────────────┐
                │       Index        │
                │   Staging area     │
                └─────────┬──────────┘
                          │ git commit
                          v
                ┌────────────────────┐
                │     Repository     │
                │ Commits & history  │
                └────────────────────┘
~~~

- **Working tree:** the files you are viewing and editing in the project directory.
- **Index (staging area):** the content selected to be included in the next commit.
- **Repository:** the Git objects and commits that have been created.
- **Refs:** names such as branches and tags that point to commits.
- **Remote-tracking refs:** local information about the state of branches on a remote after fetching.

GUIs and IDEs may refer to the index with names like Staged Changes, Index, or Staged Files. Unstaged files are usually shown under Changes, Unstaged Changes, or Local Changes. Exact names depend on the tool.

A file can appear in both groups simultaneously if you stage a version and then continue editing that file. The staged part is the content selected for the commit; the unstaged part consists of newer edits that have not been staged yet.

For example:

1. You edit `PaymentService.java`.
2. Stage the current changes.
3. You edit that file further.
4. Git can show the file in both Staged and Unstaged.

In this situation, a commit only records the staged content. If you want to include the newer edits in the same commit, you must stage those edits as well.

## One repository can be opened by multiple tools

For example, a project is opened simultaneously with:

- A terminal in the repository directory.
- An IDE to edit source code.
- A Git GUI to view history and branches.

All three read and write data in the same working directory. However, each application may cache state in memory and only refresh periodically or upon file events.

Therefore, after performing an operation in one tool, if another tool does not update immediately:

- Refresh the Git Changes or Source Control view.
- Switch tabs and switch back if the application needs to re-read the state.
- Run `git status` in the terminal to check the actual state.
- Avoid continuing operations based on a screen that has not updated yet.

Do not open the same repository in multiple windows and perform concurrent write operations such as commit, rebase, or checkout in multiple places. Some operations use lock files or modify the index and HEAD; running them concurrently can cause a process to be rejected or display confusing intermediate states.

### Identifying the exact repository you are operating on

In the terminal, check:

~~~bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git branch --show-current
git status --short --branch
~~~

These commands confirm:

- The root path of the working tree.
- The Git directory the repository is using.
- The current branch.
- Existing changes.

In a GUI or IDE, check the repository path in the status bar, Git window, or project list. Do not assume the open project folder is also the repository root; a workspace may contain nested repositories or multiple modules.

If an IDE opens a monorepo with multiple sub-repositories, check the repository selector before committing or pushing. Selecting the wrong repository can commit changes into a different history than intended.

## CLI and GUI/IDE operation mapping

Button names and layouts may differ across GitHub Desktop, Sourcetree, GitKraken, VS Code, IntelliJ IDEA, and other IDEs. The table below describes equivalent operation meanings, not fixed menu locations.

| Goal | Git CLI | Common GUI or IDE action |
|---|---|---|
| View status | `git status` | Open Git Changes, Source Control, or Commit view |
| View file changes | `git diff` | Select a file in the Unstaged/Changes group |
| View staged content | `git diff --cached` | Open the Staged Changes group |
| Stage a file | `git add <file>` | Choose Stage or the plus icon next to the file |
| Unstage | `git restore --staged <file>` | Unstage or move the file back to Changes |
| Stage partially | `git add -p` | Stage hunk or stage selected lines |
| Commit | `git commit` | Enter a message and choose Commit |
| View history | `git log --graph --oneline --all` | Open History or Log |
| Create a branch | `git switch -c <branch>` | New Branch |
| Switch branch | `git switch <branch>` | Select a branch and choose Checkout/Switch |
| Fetch | `git fetch origin` | Fetch or Refresh Remote |
| Pull | `git pull` | Pull |
| Push | `git push` | Push or Publish Branch |
| Merge | `git merge <branch>` | Choose Merge Into Current |
| Rebase | `git rebase <branch>` | Rebase Current onto Selected |
| Resolve conflicts | Edit the file, then `git add <file>` | Merge Editor, Resolve, Mark Resolved/Stage |
| View remotes | `git remote -v` | Repository Settings or Remotes |
| View tags | `git tag --list` | Tags in History or Repository view |

Understand the Git command corresponding to each GUI action. When a GUI presents options such as Update, Sync, Commit & Push, or Pull with Rebase, read the description to know whether the tool will run a single command or a sequence of commands.

## Reviewing changes and deciding commit contents

### Checking status with CLI and IDE

Start with:

~~~bash
git status
~~~

Example:

~~~text
On branch feature/payment
Changes to be committed:
  modified:   src/PaymentService.java

Changes not staged for commit:
  modified:   README.md

Untracked files:
  src/PaymentValidator.java
~~~

How to read it:

- `PaymentService.java` is staged.
- `README.md` is modified but not staged.
- `PaymentValidator.java` is a new file not yet tracked by Git.

GUIs usually separate these into corresponding groups. Check Staged, Unstaged, and Untracked groups before committing.

Short status command:

~~~bash
git status --short --branch
~~~

Example:

~~~text
## feature/payment
M  src/PaymentService.java
 M README.md
?? src/PaymentValidator.java
~~~

The two status columns help distinguish changes in the index and in the working tree. A GUI may use icons, colors, or labels to represent the same information.

### Viewing diffs of the right area

Key commands:

~~~bash
# Unstaged changes
git diff

# Staged changes
git diff --cached

# Compare the entire working tree against HEAD
git diff HEAD
~~~

In an IDE, select individual files to view diffs. Most tools allow switching between two versions:

- HEAD vs. Working Tree.
- HEAD vs. Index.
- Index vs. Working Tree.

Choose the right comparison pair. A diff showing only HEAD vs. working tree may combine both staged and unstaged changes; if you want to know what the upcoming commit will record, inspect Index/Staged Changes.

### Stage the whole file or stage partially?

Stage the whole file:

~~~bash
git add src/PaymentService.java
~~~

Unstage a file:

~~~bash
git restore --staged src/PaymentService.java
~~~

If a file contains multiple changes serving different purposes, you can stage only selected hunks:

~~~bash
git add -p src/PaymentService.java
~~~

GUIs/IDEs usually provide Stage Hunk, Stage Selected Lines, or a plus sign next to each diff block. The exact name depends on the tool.

For example, `PaymentService.java` has two changes:

- Hunk 1: fix an amount validation bug.
- Hunk 2: add temporary debug logging.

If the commit should only contain the bug fix, stage hunk 1 and leave hunk 2 unstaged. Before committing, verify with:

~~~bash
git diff --cached
git diff
~~~

Do not blindly choose Stage All if the working tree contains generated files, logs, personal configs, or changes that are not ready.

### Reading the diff before committing

A short verification workflow:

~~~bash
git status --short
git diff --check
git diff --cached --check
git diff --cached --stat
git diff --cached
~~~

- `git diff --check` checks whitespace issues in unstaged changes.
- `git diff --cached --check` checks staged changes.
- `--stat` shows the scope of changes.
- The full diff lets you inspect the exact commit content.

A GUI may display whitespace markers or warnings, but when you need to verify the index and working tree state, use the CLI to cross-check.

## Committing in the IDE and verifying via CLI

GUIs usually provide a commit message input box and a Commit button. Before clicking, verify:

1. Correct repository and branch.
2. Staged file list matches the intended scope.
3. No secrets, logs, or unwanted artifacts.
4. Staged diff has been reviewed.
5. Commit message accurately describes the change.

Commit from the terminal:

~~~bash
git commit -m "feat(payment): validate payment amount"
~~~

Committing from an IDE creates the same kind of commit object as running the CLI. After committing, verify:

~~~bash
git status
git log -1 --oneline --decorate
git show --stat --oneline HEAD
git show --no-patch --pretty=fuller HEAD
~~~

If the GUI reports that the commit succeeded while the terminal shows a different state, check whether both applications have the same repository and working tree open. Also check whether hooks modified files or rejected part of the workflow.

### Commit and Push are two separate actions

Some GUIs have a Commit & Push or Commit and Sync button. This button runs multiple steps in sequence:

1. Create a local commit.
2. Send the commit to the remote.

If the push fails, the local commit may already have been created successfully. Do not create another identical commit just because the final notification reports a push error.

Check:

~~~bash
git log -1 --oneline
git status -sb
git branch -vv
~~~

If the commit already exists locally but has not reached the remote yet, resolve the cause of the push failure and retry pushing:

~~~bash
git push
~~~

## Managing branches with GUI and CLI

### Creating and switching branches

Create a new branch from the current HEAD:

~~~bash
git switch -c feature/payment
~~~

Switch to an existing branch:

~~~bash
git switch main
~~~

GUIs usually have a branch list and options like New Branch, Checkout, or Switch. Before creating a branch, confirm the base branch is correct. If branching from another commit or branch, select the right starting point.

Verify after switching:

~~~bash
git branch --show-current
git status -sb
git log -1 --oneline --decorate
~~~

### Uncommitted changes when switching branches

A GUI may show a dialog asking whether you want to:

- Carry/Bring Changes: bring the changes over to the other branch.
- Stash: temporarily store the changes.
- Force Checkout/Discard: discard changes in order to switch branches.

Understand the consequences before choosing. The equivalent CLI commands can be:

~~~bash
git stash push -m "WIP before switching branch"
git switch main
~~~

Then restore when needed:

~~~bash
git stash list
git stash pop
~~~

Do not choose Discard or Force Checkout unless you have confirmed the changes can be dropped. When unsure, make a temporary commit or stash first.

### Tracking branches and remote-tracking branches

View branches:

~~~bash
git branch -vv
git branch -avv
~~~

GUIs usually group Local Branches and Remote Branches separately. A remote branch shown in a GUI is typically a remote-tracking ref, such as `origin/main`, updated after fetch.

Fetch does not automatically update local branches. It downloads objects and updates remote-tracking information:

~~~bash
git fetch origin
git log --oneline --decorate --graph --all
~~~

If the GUI shows a new commit on `origin/main`, that does not mean the local `main` branch has updated automatically. To integrate, use pull, merge, or rebase according to your team's convention.

## Fetch, Pull, Push, and Sync buttons

### Fetch before integrating

Fetch retrieves changes from the remote and updates remote-tracking refs:

~~~bash
git fetch origin
~~~

This is useful when you want to see whether the remote has new commits without changing your current branch or working tree.

A GUI may call this button Fetch, Fetch All, or Refresh. After fetching, open History or Graph to view new commits.

### Pull is Fetch plus integration

Pull typically runs fetch followed by merge or rebase depending on configuration and options:

~~~bash
# Pull using merge
git pull --no-rebase

# Pull using rebase
git pull --rebase
~~~

A Pull button in a GUI may use `pull.rebase`, `pull.ff`, or tool-specific settings. Inspect the configuration:

~~~bash
git config --show-origin --get pull.rebase
git config --show-origin --get pull.ff
git config --show-origin --get branch.main.rebase
~~~

If it is unclear whether the GUI will merge or rebase, fetch first, inspect the graph, and choose the integration operation explicitly.

### Pushing a branch

Push the current branch for the first time and set upstream:

~~~bash
git push -u origin feature/payment
~~~

Once upstream is configured, you can use:

~~~bash
git push
~~~

A GUI may display Publish Branch if the branch does not yet have a remote-tracking branch or upstream configured. Check:

~~~bash
git branch -vv
git status -sb
~~~

If the push is rejected, read the server message. Causes can include non-fast-forward updates, missing write permissions, branch protection, or required checks. Do not repeatedly click Push without understanding the cause.

### Be careful with Sync

Some tools provide a Sync button that combines Pull and Push. Depending on configuration, it may fetch/pull first and then push local commits.

Before using it, check:

- Which local branch and upstream branch are involved.
- Whether pull will merge or rebase.
- Whether there are uncommitted changes.
- Whether the remote has new commits.
- Whether pushing is restricted by branch protection.

If you need step-by-step control, use Fetch, inspect history, and run Pull/Rebase and Push separately.

## Viewing history and comparing commits

CLI:

~~~bash
git log --oneline --graph --decorate --all
~~~

View a single commit:

~~~bash
git show <commit-id>
~~~

Compare two commits:

~~~bash
git diff <base>..<target>
~~~

GUIs/IDEs usually provide History, Log, Timeline, or Graph views. From there you can:

- Select a commit to view changed files.
- Compare two commits or two branches.
- Inspect parent commits and merge commits.
- Search commits by message or author.
- Open a file at an earlier version.
- View blame/annotate to find the commit that modified a line.

If the GUI only shows the history of the current branch, enable All Branches or check with `git log --all`. Do not conclude that a commit is lost just because it does not appear in the currently selected view.

### Using blame in the IDE and CLI

CLI:

~~~bash
git blame -L 20,45 src/PaymentService.java
~~~

In an IDE, Annotate or Git Blame typically displays the commit, author, and modification date next to each line.

Blame identifies the most recent commit that changed a line as tracked by Git; it does not by itself prove who holds business responsibility or why the change was made. Open the corresponding commit and review its diff, message, code review, or related issue to understand the context.

## Resolving conflicts with a Merge Editor or terminal

### Recognizing an in-progress merge state

When a merge hits conflicts, Git keeps an in-progress merge state. GUIs/IDEs usually open a Merge Editor with three panes:

- **Current/Ours:** the version from the current branch.
- **Incoming/Theirs:** the version from the branch being merged in.
- **Result:** the resulting content you choose or edit.

Labels can vary across tools. In the terminal, check:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Do not rely solely on red/green highlighting in the GUI; read the content of both sides and the context of the changes.

Note that Current/Ours and Incoming/Theirs labels can be confusing during a rebase. Rebase replays each commit onto a new base, so the way Git assigns roles to the two sides can be the opposite of the intuition that Ours is always your feature branch. Read the Merge Editor's labels and descriptions, check state with `git status`, and compare the contents of each side before choosing.

### Completing conflict resolution

Typical workflow:

1. Open each conflicted file in the Merge Editor.
2. Compare Current and Incoming.
3. Combine the logic to keep into Result.
4. Save the file.
5. Mark Resolved or Stage the file.
6. Review the diff again.
7. Continue the merge commit.

In the terminal, the staging step after editing is:

~~~bash
git add src/PaymentService.java
~~~

Verify there are no remaining unmerged paths:

~~~bash
git diff --name-only --diff-filter=U
git status
~~~

If merging, complete with:

~~~bash
git commit
~~~

A GUI may show a Complete Merge or Commit Merge button. That button creates the merge commit after all conflicts are resolved and staged.

### Distinguishing merge conflicts from rebase conflicts

Both merge and rebase can require conflict resolution, but the state and next step differ.

| Case | After editing and staging |
|---|---|
| Merge conflict | Continue with `git commit` if the merge did not auto-commit |
| Rebase conflict | Run `git rebase --continue` |
| Cherry-pick conflict | Run `git cherry-pick --continue` |

Abort an in-progress operation using the corresponding command:

~~~bash
git merge --abort
git rebase --abort
git cherry-pick --abort
~~~

A GUI may provide Abort, Continue, or Skip buttons. Before choosing Skip during a rebase or cherry-pick, understand that it drops the commit currently being applied; do not use it as a Resolve button.

### When the Merge Editor and terminal show different states

The IDE may not have saved the Result file, marked it resolved, or refreshed the index. Check:

~~~bash
git status
git ls-files -u
git diff
git diff --cached
~~~

If `git ls-files -u` still outputs entries, the index still contains conflict stages. Save the file, re-stage it, and refresh the GUI.

Do not edit conflict markers directly in the terminal while simultaneously clicking version choices in the Merge Editor. Choose one resolution method at a time, save the result, stage it, and verify again.

## Using the integrated terminal in the IDE

Most IDEs have an integrated terminal. This terminal typically starts a shell in the project directory or a configured directory.

Before running commands:

~~~bash
pwd
git rev-parse --show-toplevel
git status -sb
~~~

On PowerShell, use `Get-Location` instead of `pwd` if you prefer PowerShell's native output; Git commands work normally either way.

The integrated terminal helps you:

- Run Git commands that do not have a corresponding UI button.
- See raw error messages.
- Run scripts, tests, and builds.
- Inspect configuration and remotes.
- Copy commands to reproduce issues in reports.

Keep in mind that the integrated terminal may open in a subdirectory. Git will look up the nearest parent repository, so in a multi-repository workspace, verify the root before running write commands.

## Configuring the Git executable and credentials in the IDE

An IDE may use:

- Git installed on the operating system.
- Git bundled with the application.
- A Git executable selected in IDE settings.

If the CLI and IDE produce different results, check the executable path and version:

~~~bash
git --version
where.exe git
~~~

On Windows PowerShell or CMD, `where.exe git` lists the Git executables found in PATH. On macOS/Linux, use `which git` to see the executable found by the shell. In the IDE, open Version Control or Git Settings/Preferences to check the configured Git path.

Version differences can cause an option to be unsupported or change how status is displayed. Do not change the Git executable in the IDE randomly just to test on a repository that has an operation in progress.

### Credentials and SSH agents

The terminal and IDE may use different authentication mechanisms. For example:

- The terminal uses an SSH agent with loaded keys.
- The IDE uses a credential manager or a signed-in account.
- Git for Windows uses its own credential helper.
- CI environments use tokens or deploy keys.

Check remote URLs:

~~~bash
git remote -v
~~~

Check credential helper configuration without printing secrets:

~~~bash
git config --show-origin --get-all credential.helper
~~~

Do not share logs containing tokens, passwords, private keys, or HTTP authorization headers. If the terminal can push while the IDE reports authentication failed, inspect the account and credential provider the IDE is using instead of changing the remote URL by embedding a token.

## Hooks and automation can run in both GUI and CLI

When Git performs a commit, push, or other hook-triggering operation, hooks may execute whether the command originates from the terminal or GUI, provided the tool invokes Git and does not bypass hooks.

For example, pre-commit may run a formatter or tests. If committing from the IDE fails while the terminal succeeds, or vice versa, read the hook output and compare the environments:

- Does PATH contain the required tools?
- Are the shell or runtime the same?
- Does the IDE have the right repository open?
- Are the files staged?
- Does the GUI have an option enabled to bypass hooks?
- Does the Git executable point to the same installation?

Some applications may create commits through an internal library or provide an option to skip hooks. Therefore, verify the behavior of the tool you are using rather than assuming every Commit button runs the exact same sequence of commands.

## Sample combined workflow for a feature

Suppose you are developing a payment validation feature and want to use the terminal together with an IDE.

### Step 1: Confirm the repository and branch

In the integrated terminal:

~~~bash
git rev-parse --show-toplevel
git status -sb
git switch -c feature/payment-validation
~~~

In the IDE, verify that the branch selector shows `feature/payment-validation`.

### Step 2: Edit in the IDE

Modify `PaymentService.java` and add `PaymentValidator.java`. Use the IDE to navigate code, run tests, and check compilation errors.

### Step 3: Review changes with GUI and CLI

In the GUI, inspect the files under Changes and read the diffs. Then verify in the terminal:

~~~bash
git status --short
git diff
git diff --check
~~~

Confirm there are no logs, auto-generated build files, or personal machine configs.

### Step 4: Stage selectively

If both files belong to the same feature:

~~~bash
git add src/PaymentService.java src/PaymentValidator.java
~~~

If only part of a file should be committed, use Stage Hunk in the IDE or:

~~~bash
git add -p src/PaymentService.java
~~~

Verify:

~~~bash
git diff --cached
git diff
~~~

### Step 5: Commit

You can commit in the IDE or terminal:

~~~bash
git commit -m "feat(payment): validate payment amount"
~~~

Verify:

~~~bash
git show --stat --oneline HEAD
git status -sb
~~~

### Step 6: Fetch, update, and push

~~~bash
git fetch origin
git log --graph --oneline --decorate --all
~~~

If the team requires updating the branch from main using rebase:

~~~bash
git rebase origin/main
~~~

Resolve any conflicts using the Merge Editor or terminal. After the rebase finishes, verify tests and history, then push:

~~~bash
git push -u origin feature/payment-validation
~~~

If the branch was already pushed before rebasing and history was rewritten, follow your team's convention; do not force push a branch that others are using without coordinating first.

## Diagnostic workflow when GUI and CLI disagree

When the displayed state differs, check in order:

1. **Is it the right repository?** Check the project path, repository selector, and `git rev-parse --show-toplevel`.
2. **Has the GUI refreshed?** Refresh Git Changes or History.
3. **Does the index differ from the working tree?** Run `git status`, `git diff`, and `git diff --cached`.
4. **Is an operation in progress?** Check merge, rebase, or cherry-pick status in `git status`.
5. **Is the Git executable the same?** Compare versions and paths.
6. **Are hooks or credential providers different?** Read the output and inspect configuration.
7. **Are files ignored or filtered?** Check `git check-ignore -v <path>` and attributes if files do not appear as expected.

Additional diagnostic commands:

~~~bash
git status
git diff --name-status
git diff --cached --name-status
git branch -vv
git remote -v
git config --show-origin --show-scope --list
~~~

Before sharing configuration output, redact URLs containing credentials and any sensitive values.

## Common pitfalls when using multiple interfaces

| Symptom | Possible cause | How to handle |
|---|---|---|
| IDE does not see a commit just created in terminal | Wrong repository open or History not refreshed | Verify repository root and refresh |
| Terminal reports file staged, GUI still shows Changes | IDE has not updated index or file has unstaged parts | Refresh and inspect both Staged and Unstaged |
| GUI commits more files than intended | Stage All selected or auto-commit of unreviewed files enabled | Check staged list and diff before committing |
| Commit button is disabled | No files staged or commit message missing | Check status and tool requirements |
| Commit succeeded but Push failed | Local commit created, remote rejected push | Check branch/upstream, permissions, and remote history |
| IDE and terminal use different Git versions | IDE points to a different Git executable | Check executable configuration and version |
| Hook runs in terminal but fails in IDE | Different PATH, shell, or runtime | Standardize environment and read hook output |
| Merge Editor shows resolved but Git still has conflicts | File not staged or index not updated | Run `git ls-files -u`, re-stage the file |
| Pull in GUI creates an unexpected merge commit | Pull uses merge configuration instead of rebase | Fetch first and choose strategy explicitly |
| Sync unexpectedly pulls and pushes | Sync button executes multiple steps | Use Fetch, Pull, and Push separately when control is needed |

## Safe habits when combining CLI, GUI, and IDE

- Confirm the repository root and branch before write operations.
- Read the staged diff before every commit.
- Understand the difference between Working Tree, Index, and HEAD.
- Do not click Stage All or Commit & Push without reviewing scope.
- Refresh the GUI after terminal operations.
- Do not run merge, rebase, checkout, or commit simultaneously across multiple applications.
- Use the terminal to check status when the UI is unclear.
- Read Stash, Discard, Force Checkout, and Abort dialogs carefully.
- Check hooks, the Git executable, and credential providers when behavior differs.
- Use Fetch before deciding on Pull/Rebase if you need to inspect remote changes.
- Do not share logs or configs containing secrets.
- Follow your team's branch, review, and push conventions.

## Key takeaways

The terminal, GUI, and IDE are interfaces operating on the same Git repository. A GUI makes inspecting diffs, staging hunks, viewing history, and resolving conflicts visual; an IDE puts Git right alongside source code and build tools; the terminal lets you check exact state and perform repeatable operations. To combine them safely, always distinguish between working tree, index, and commit, confirm the right repository and branch, review staged diffs before committing, understand what Pull/Sync buttons execute, and use `git status` to verify whenever the UI is unclear. A good interface assists your workflow; Git's actual state and command output are the source of truth confirming that changes were recorded as intended.

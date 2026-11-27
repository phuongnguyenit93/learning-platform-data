# Choosing an Editor, Diff Tool, and Merge Tool

Git often needs to open an editor so you can write a commit message, edit the todo list during an interactive rebase, or enter tag annotation text. When inspecting differences between two versions, you may want to use a diff tool with a visual interface. When merge or rebase produces conflicts, a three-way merge tool helps compare changes from both branches against a common base version and produce the final output.

Git lets you configure each type of tool independently. You can use VS Code as your editor, a dedicated diff tool to review changes, and a merge tool to resolve conflicts. This lesson explains how to select, configure, verify, and use those tools in personal or team repositories.

This lesson belongs to the **Installation and Configuration** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history through branches, merging, rebasing, remotes, and tags; it also trains collaboration across branches, conflict resolution, tracking down changes, and recovering from mistakes while preserving important history. Configuring the right tools makes working with commit messages, reviewing diffs, and resolving conflicts more consistent.

## 1. Three types of tools and their roles

Git can invoke external programs to perform different tasks:

| Tool | Purpose | Example Git operations |
|---|---|---|
| Editor | Compose text requested by Git | <code>git commit</code>, <code>git tag -a</code>, <code>git rebase -i</code> |
| Diff tool | Display differences between two versions | <code>git difftool</code> |
| Merge tool | Combine changes from multiple sides when conflicts occur | <code>git mergetool</code> |

The three tools can be three different applications or the same application. For example, VS Code can serve as an editor, display diffs, and assist with conflict resolution. Vim can also be used for editing, viewing diffs, and resolving conflicts via vimdiff mode.

Do not confuse them:

- An editor edits the text content Git asks you to enter.
- A diff tool helps inspect where two versions differ; it does not automatically decide which version is right.
- A merge tool helps produce a combined result from the versions; the user still has to review and confirm the final contents.

## 2. How does Git choose an editor from configuration?

When Git needs to open an editor, it searches for a command in this common precedence order:

1. The <code>GIT_EDITOR</code> environment variable.
2. The Git configuration <code>core.editor</code>.
3. The <code>VISUAL</code> environment variable.
4. The <code>EDITOR</code> environment variable.
5. The Git environment's default editor if none of the above sources are set.

Therefore, if you have configured <code>core.editor</code> yet Git still opens a different program, check whether <code>GIT_EDITOR</code> is overriding it.

Interactive rebase also has its own dedicated configuration, <code>sequence.editor</code>. This setting determines the editor used to edit the rebase todo list. If unset, Git falls back to the regular editor according to existing configuration.

## 3. Choosing an editor for commits and Git messages

### Using VS Code

If VS Code is installed and the <code>code</code> command is in PATH, configure:

~~~bash
git config --global core.editor "code --wait"
~~~

The <code>--wait</code> option tells the CLI command to wait until the opened window/document is closed. Without this option, Git may proceed with the commit before you finish writing the message.

Verify:

~~~bash
git config --global --get core.editor
~~~

Try creating a commit without the <code>-m</code> option:

~~~bash
git commit
~~~

Git will open VS Code for you to enter the message. Save and close the document in a way recognized by the VS Code CLI; Git resumes once the editor exits.

### Using Vim

~~~bash
git config --global core.editor "vim"
~~~

In Vim:

- Press <code>i</code> to enter insert mode.
- Write the commit message.
- Press <code>Esc</code> to return to normal mode.
- Type <code>:wq</code> and press Enter to save and exit.
- Type <code>:q!</code> if you want to quit without saving; Git will not receive the edited content.

### Using Nano

~~~bash
git config --global core.editor "nano"
~~~

In Nano, enter the message, press <code>Ctrl+O</code> to save, Enter to confirm the filename, then <code>Ctrl+X</code> to exit.

### Using Notepad on Windows

You can use Notepad if Git recognizes the command:

~~~bash
git config --global core.editor "notepad"
~~~

Notepad is suitable for simple message editing. If the editor launches asynchronously or Git does not wait at the right moment, use a launcher command with a wait mechanism or choose VS Code with <code>--wait</code>.

### Using Notepad++

If Notepad++ is installed and its executable path is in PATH:

~~~bash
git config --global core.editor "notepad++ -multiInst -notabbar -nosession -noPlugin"
~~~

Launch options depend on the installation method and Notepad++ version. Test whether Git waits for the editor to close before using this configuration for commits or rebases. An additional wait flag may be needed depending on the application version.

## 4. Setting an editor for a single repository only

Not every project needs the same editor. You can set a local configuration inside the current repository:

~~~bash
git config --local core.editor "code --wait"
~~~

This command writes to the repository's local configuration and takes higher precedence than global configuration when no environment variable overrides it.

Comparison:

| Scope | Command | Effect |
|---|---|---|
| System | <code>git config --system</code> | Applies to users on the machine via system config; usually requires admin privileges |
| Global | <code>git config --global</code> | Applies to the current user's repositories |
| Local | <code>git config --local</code> | Applies only to the current repository |
| Worktree | <code>git config --worktree</code> | Applies to the current worktree when the repository enables the required config extension |

When you need per-worktree configuration, check first whether the repository has enabled <code>extensions.worktreeConfig</code>. Do not assume all local settings are automatically isolated per worktree.

## 5. Configuring a separate editor for interactive rebase

When running:

~~~bash
git rebase -i HEAD~3
~~~

Git opens a todo list for you to change <code>pick</code>, <code>reword</code>, <code>squash</code>, or other actions. You can choose a separate editor for this list:

~~~bash
git config --global sequence.editor "code --wait"
~~~

Or use Vim:

~~~bash
git config --global sequence.editor "vim"
~~~

Verify:

~~~bash
git config --show-origin --get sequence.editor
~~~

To temporarily use another editor for a single run, you can set the <code>GIT_SEQUENCE_EDITOR</code> environment variable in the current shell session. This variable applies specifically to the rebase instruction list editor; it does not change the default commit editor.

## 6. Using environment variables to override the editor temporarily

Environment variables are useful when you want to test an editor without saving a permanent configuration.

Example in Bash:

~~~bash
GIT_EDITOR="vim" git commit
~~~

In PowerShell:

~~~powershell
$env:GIT_EDITOR = "code --wait"
git commit
Remove-Item Env:GIT_EDITOR
~~~

To override the editor for the interactive rebase todo list:

~~~powershell
$env:GIT_SEQUENCE_EDITOR = "code --wait"
git rebase -i HEAD~3
Remove-Item Env:GIT_SEQUENCE_EDITOR
~~~

Environment variables in PowerShell persist in the current session until removed or the session ends. Remove them after testing if you do not want them to keep overriding configuration.

## 7. Checking and unsetting editor configuration

Some diagnostic commands:

~~~bash
# View configuration value and origin
git config --show-origin --get core.editor
git config --show-origin --get sequence.editor

# List related editor configurations
git config --show-origin --get-regexp '^(core|sequence)\.editor$'

# Inspect environment variables in Bash
env | grep -E '^(GIT_EDITOR|GIT_SEQUENCE_EDITOR|VISUAL|EDITOR)='
~~~

In PowerShell:

~~~powershell
Get-ChildItem Env:GIT_EDITOR, Env:GIT_SEQUENCE_EDITOR, Env:VISUAL, Env:EDITOR
~~~

If you want to remove local or global configuration so Git falls back to a lower-precedence source:

~~~bash
git config --local --unset core.editor
git config --global --unset core.editor
~~~

Run the command only at the scope you intend to modify. Removing local configuration does not remove global configuration; removing global also does not clear an overriding environment variable.

## 8. What is a diff tool used for?

The <code>git diff</code> command displays differences as text directly in the terminal. This is fast and suitable for most source code changes:

~~~bash
# Compare working tree against index
git diff

# Compare index against current commit
git diff --staged

# Compare two commits
git diff main..feature/payment
~~~

When changes are large or span many files, a graphical diff tool can help inspect both sides side by side, navigate between hunks, and view directory structure.

Git invokes the configured external diff tool with:

~~~bash
git difftool
~~~

This command displays differences using the configured tool. You can narrow the scope with a pathspec or specify two commits just as with <code>git diff</code>.

## 9. Configuring a diff tool

### Viewing tools recognized by Git

~~~bash
git difftool --tool-help
~~~

The list depends on your Git version and applications installed on the machine. Common tools include Vimdiff, Meld, KDiff3, Beyond Compare, Araxis, and other comparison tools.

### Using Vimdiff

~~~bash
git config --global diff.tool vimdiff
~~~

Then:

~~~bash
git difftool
~~~

Vimdiff displays two versions in split windows. This is a good choice if you are already familiar with Vim and want to work directly inside the terminal.

### Using Meld

~~~bash
git config --global diff.tool meld
~~~

Git will invoke Meld if the application is installed and discoverable in PATH. Depending on the OS and installation package, the executable name may differ; verify that the command to launch the app works from the terminal first.

### Using VS Code as a diff tool

You can declare a custom tool:

~~~bash
git config --global diff.tool vscode
git config --global difftool.vscode.cmd 'code --wait --diff "$LOCAL" "$REMOTE"'
~~~

In the custom command:

- <code>$LOCAL</code> is the local-side content Git passes to the tool.
- <code>$REMOTE</code> is the other side to compare against.
- <code>--diff</code> instructs VS Code to open both files in diff comparison mode.
- <code>--wait</code> tells Git to wait for the tool to exit before continuing.

The <code>$LOCAL</code> and <code>$REMOTE</code> variables are placeholders that Git substitutes when running difftool. Do not replace them manually with hardcoded paths on your machine.

### Running a diff tool once without changing the default

~~~bash
git difftool --tool=vimdiff
git difftool --tool=meld
~~~

If you want to invoke a declared custom tool:

~~~bash
git difftool --tool=vscode
~~~

## 10. Useful options for git difftool

| Option | Effect |
|---|---|
| <code>--tool=&lt;tool&gt;</code> | Choose a tool for the current run |
| <code>--tool-help</code> | List available tools |
| <code>--no-prompt</code> | Do not prompt before opening each diff |
| <code>--prompt</code> | Require confirmation before each tool launch |
| <code>--dir-diff</code> | Compare by directory instead of opening file pairs one by one |
| <code>--extcmd=&lt;command&gt;</code> | Run the specified external command instead of the configured tool |

Examples:

~~~bash
# Open diff tool without prompting per file
git difftool --no-prompt

# Compare two branches using the configured tool
git difftool main..feature/payment

# Compare the entire directory tree
git difftool --dir-diff main..feature/payment
~~~

You can configure Git not to prompt every time:

~~~bash
git config --global difftool.prompt false
~~~

If you want prompting again, set it to <code>true</code> or unset it to use the default.

## 11. Merge tools and conflict resolution

A merge tool assists with resolving conflicts when Git cannot automatically combine changes. For example, two branches modify the same region in the same file:

~~~text
<<<<<<< HEAD
timeout = 30
=======
timeout = 60
>>>>>>> feature/performance
~~~

These are conflict markers in the working tree. The top section normally represents the current side (ours), the bottom section represents the incoming side being integrated (theirs); the divider line separates the two sides. During a rebase, the meaning of ours/theirs can feel counterintuitive because the branch is being replayed onto a new base. Read Git's messages and identify your goal rather than relying solely on the labels.

A merge tool typically shows three versions:

- **Base:** the common content before the two sides diverged.
- **Local / ours:** content from the current side in the merge operation.
- **Remote / theirs:** content from the side being integrated.

The application helps you inspect the differences and produce the resulting file. Not every tool uses the exact same interface or names for the three panes.

## 12. Configuring a merge tool

### Viewing available merge tools

~~~bash
git mergetool --tool-help
~~~

Git can recognize tools such as Vimdiff, KDiff3, Meld, Beyond Compare, P4Merge, Araxis, and others depending on the platform.

### Using Vimdiff

~~~bash
git config --global merge.tool vimdiff
~~~

When a conflict occurs:

~~~bash
git mergetool
~~~

Vimdiff opens the versions for you to compare and edit the result. After saving and exiting, inspect the file in the working tree before marking it resolved.

### Using Meld

~~~bash
git config --global merge.tool meld
git mergetool
~~~

Meld typically provides a three-way interface or an interface matching the configuration invoked by Git. Check that the application is in PATH and confirm that the output is written to the file Git expects.

### Using VS Code as a merge tool

You can declare a custom tool that opens the merged output file in VS Code:

~~~bash
git config --global merge.tool vscode
git config --global mergetool.vscode.cmd 'code --wait "$MERGED"'
~~~

<code>$MERGED</code> is the path to the output file that Git expects the tool to edit. VS Code opens the file with conflict markers; you can use Accept Current, Accept Incoming, Accept Both, or open the Merge Editor to resolve them. After choosing and saving the result, close the window so Git continues.

This invokes the editor on the merged file. If you want a dedicated three-way view in another tool, configure that tool's command properly and pass <code>$BASE</code>, <code>$LOCAL</code>, <code>$REMOTE</code>, and <code>$MERGED</code> according to its documentation.

### Selecting a merge tool for a single run

~~~bash
git mergetool --tool=vimdiff
git mergetool --tool=meld
~~~

There is no need to change your default configuration if you only want to try a tool once.

## 13. Variables Git passes to a merge tool

When configuring a custom merge tool, Git provides key variables:

| Variable | Meaning |
|---|---|
| <code>$BASE</code> | File containing the common base version |
| <code>$LOCAL</code> | File from the local/ours side in the current operation |
| <code>$REMOTE</code> | File from the integrated/theirs side |
| <code>$MERGED</code> | Resulting output file that the tool must produce or update |

A custom configuration can use all four variables:

~~~bash
git config --global merge.tool custom
git config --global mergetool.custom.cmd 'my-merge-app "$BASE" "$LOCAL" "$REMOTE" "$MERGED"'
~~~

Replace <code>my-merge-app</code> with the actual command for your installed tool. Parameter syntax depends on the application; read the application's documentation before using it. Do not assume every tool takes the four paths in the same order.

## 14. Conflict resolution workflow with mergetool

Suppose you are merging a feature branch into the current branch:

~~~bash
git switch main
git merge feature/payment
~~~

If Git reports conflicts:

~~~bash
# View list of conflicted files
git status

# Open the conflict resolution tool
git mergetool
~~~

After the tool exits, check status:

~~~bash
git status
git diff
git diff --staged
git diff --check
~~~

If the result is correct, mark each file as resolved with <code>git add</code>. If a file needs to be deleted per the merge resolution, use <code>git rm</code>:

~~~bash
git add src/PaymentService.java
git rm src/LegacyPaymentAdapter.java
~~~

Then verify no unmerged paths remain:

~~~bash
git status
git diff --staged
~~~

Finish the merge with:

~~~bash
git merge --continue
~~~

In a standard merge workflow, Git may ask to create a merge commit via the editor. Unless there is a special requirement, <code>git commit</code> can also complete the merge once all conflicts are resolved.

## 15. Finishing the right workflow if conflicts occur during rebase or cherry-pick

The merge tool only helps edit file contents. It does not decide which high-level Git operation should continue.

| In-progress operation | After resolving conflicts and staging files |
|---|---|
| Merge | <code>git merge --continue</code> or complete the merge with commit |
| Rebase | <code>git rebase --continue</code> |
| Cherry-pick | <code>git cherry-pick --continue</code> |

If you want to cancel:

~~~bash
git merge --abort
git rebase --abort
git cherry-pick --abort
~~~

Only run the abort command corresponding to the operation currently in progress. Check <code>git status</code> to identify which state Git is in.

## 16. Common mergetool options

| Configuration / option | Meaning |
|---|---|
| <code>merge.tool</code> | Default merge tool |
| <code>mergetool.&lt;tool&gt;.cmd</code> | Custom command to invoke the tool |
| <code>mergetool.prompt</code> | Whether to prompt before opening the tool |
| <code>mergetool.keepBackup</code> | Whether to keep <code>.orig</code> backup files after resolution |
| <code>mergetool.trustExitCode</code> | Whether to trust the tool's exit code to determine merge outcome |

Example of not keeping `.orig` backup files after resolution:

~~~bash
git config --global mergetool.keepBackup false
~~~

Only change this setting if you already have a solid workflow for saving and verifying results. While learning or handling complex conflicts, keeping backups can be useful for comparison.

You can check current settings and their origins:

~~~bash
git config --show-origin --get merge.tool
git config --show-origin --get mergetool.keepBackup
git config --show-origin --get mergetool.prompt
git config --show-origin --get difftool.prompt
~~~

## 17. Comparing diff tools and merge tools

| Need | Recommended command | Result |
|---|---|---|
| View unstaged changes | <code>git diff</code> | Textual diff |
| View staged changes | <code>git diff --staged</code> | Diff between index and HEAD |
| Open app to compare two versions | <code>git difftool</code> | Launches diff tool |
| Resolve conflicted file | <code>git mergetool</code> | Launches merge tool |
| Confirm contents to be committed | <code>git diff --staged</code> | Inspects snapshot in index |
| Confirm all conflicts are gone | <code>git status</code> | Checks unmerged state |

A diff tool does not replace a merge tool. When reviewing a normal change, you need to compare two versions. When Git holds a conflicted state, you must produce valid combined contents and then stage them.

## 18. Team and repository configuration

Some projects standardize on an editor, diff tool, or merge tool so everyone has a similar experience. However, global configuration typically depends on individual machines, and you should not assume every team member has the same application installed.

Ways to coordinate:

- Document the team's recommended tools and how to install them.
- Use well-known tool names or custom configs with clear setup instructions.
- Store configuration in the repository only when it does not contain absolute paths specific to one machine.
- Keep global configuration for personal applications and reserve local configuration for project-specific requirements.
- Test custom commands across the operating systems supported by the team.

Never commit personal executable paths such as <code>C:/Users/.../App.exe</code> into shared configuration if other machines do not share that layout. For tools not available on all operating systems, provide alternative instructions.

## 19. Common errors and troubleshooting

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Git does not open the desired editor | <code>GIT_EDITOR</code> or configuration at another scope overrides it | Check environment variables and <code>git config --show-origin</code> |
| Commit finishes before you finish typing | Editor opens asynchronously, missing wait flag | Use a wait mechanism such as <code>code --wait</code> |
| Interactive rebase opens a different editor | <code>sequence.editor</code> or <code>GIT_SEQUENCE_EDITOR</code> is set | Check the dedicated sequence editor config |
| <code>git difftool</code> reports application not found | Tool is not installed or executable is not in PATH | Install the app, verify launch command, then reconfigure |
| VS Code diff opens a window without comparing | Custom command is missing <code>--diff</code> or path variables are wrong | Check <code>difftool.&lt;tool&gt;.cmd</code> and both placeholders |
| <code>git mergetool</code> does not open a three-way view | Tool opens only the output file or custom command does not pass all sides | Check configuration and the app's argument documentation |
| Conflicts remain after closing merge tool | Changes were not saved or not staged | Save the file, check markers, run <code>git add</code>, then check <code>git status</code> |
| Git creates <code>.orig</code> files | Backup retention setting is enabled | Inspect files for reference; change <code>mergetool.keepBackup</code> if workflow allows |
| Merge fails to continue after resolving | Not all files marked resolved or another operation is active | Run <code>git status</code> and use the right continue command |

## 20. Recommended setup workflow

A personal setup using VS Code for editing, diffing, and resolving conflicts can start as follows:

~~~bash
# Editor for commits and Git messages
git config --global core.editor "code --wait"

# Editor for interactive rebase todo lists
git config --global sequence.editor "code --wait"

# VS Code diff tool
git config --global diff.tool vscode
git config --global difftool.vscode.cmd 'code --wait --diff "$LOCAL" "$REMOTE"'

# VS Code merge tool, opening the output file to resolve conflicts
git config --global merge.tool vscode
git config --global mergetool.vscode.cmd 'code --wait "$MERGED"'
~~~

After configuring, verify:

~~~bash
git config --show-origin --get core.editor
git config --show-origin --get sequence.editor
git config --show-origin --get diff.tool
git config --show-origin --get merge.tool
~~~

Test each feature individually:

~~~bash
git commit
git rebase -i HEAD~2
git difftool
git mergetool
~~~

The last two commands only have content to open when the repository has relevant diffs or conflicts. If none exist yet, create a sandbox repository to test so you avoid creating unnecessary conflicts in an active project.

## 21. Self-check exercises

Practice in a sandbox repository:

1. Set <code>core.editor</code> to VS Code with <code>--wait</code>, then create a commit without <code>-m</code>.
2. Set a separate <code>sequence.editor</code> and run <code>git rebase -i HEAD~2</code>. Confirm the todo list opens in the right editor.
3. Temporarily override the editor using an environment variable, then unset the variable and verify configuration reverts.
4. Configure Vimdiff as your diff tool and compare two commits.
5. Configure a custom VS Code diff tool using <code>$LOCAL</code> and <code>$REMOTE</code>.
6. Create a conflict in a sandbox repository, configure a merge tool, and open it with <code>git mergetool</code>.
7. After resolving the conflict, use <code>git status</code> and <code>git diff --staged</code> to verify contents before continuing.
8. Explain the difference between an editor, a diff tool, and a merge tool.
9. Use <code>git config --show-origin</code> to locate the source of a configuration overriding your desired setting.

Once you know how to choose an editor, diff tool, and merge tool independently, you can tailor Git to your workflow while keeping full control over configuration sources and operation outcomes. Test tools in a sample repository, review contents after every conflict resolution, and continue a merge or rebase only once Git confirms all files are properly handled.

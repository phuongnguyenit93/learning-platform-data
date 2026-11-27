# Configuring the Terminal, Display Colors, and Reading Error Messages

The terminal is where you enter Git commands, inspect repository status, and read the output of every operation. A properly configured terminal keeps commands easy to read, renders Vietnamese filenames properly, highlights diffs with color, and prevents error messages from scrolling out of sight. When Git reports an error, it is important to read the full output to pinpoint which step failed before choosing how to respond.

This lesson focuses on the terminal/shell environment, configuring colors and the pager, displaying filenames with Unicode characters, and analyzing common Git error messages. The configurations presented can be applied globally for your account or locally for a single repository.

## 1. Distinguishing terminal, shell, and Git

Three components typically appear together yet serve different roles:

- **Terminal emulator** is the application that renders the command-line window, captures keyboard input, and displays text and ANSI colors. Examples: Windows Terminal, Terminal on macOS, or Linux Terminal apps.
- **Shell** is the program that reads and executes the commands you type. Examples: PowerShell, Git Bash, Bash, or Zsh.
- **Git** is the program invoked by the shell to operate on repositories.

Some common combinations:

| Operating system | Available terminals | Common shells |
|---|---|---|
| Windows | Windows Terminal, IDE integrated terminal | PowerShell, Git Bash |
| macOS | Terminal, iTerm2 | Zsh, Bash |
| Linux | GNOME Terminal, Konsole, and other terminals | Bash, Zsh |

Basic Git commands are identical across these shells. However, directory navigation syntax, environment variables, and quoting rules can differ. For example, PowerShell uses `Get-Location` to print the current directory, whereas Bash/Zsh typically use `pwd`.

Before running commands, ensure the terminal is inside the repository you intend to work on. You can verify:

```bash
git --version
git rev-parse --show-toplevel
git status
```

- `git --version` confirms Git is installed and runnable from the current shell.
- `git rev-parse --show-toplevel` prints the root directory of the repository.
- `git status` shows the current branch and changes in the working tree/index.

If the second command reports it is not a repository, change into the project directory before running Git commands that require a repository.

## 2. Choosing a readable terminal with Unicode support

Your terminal should use a monospace font containing all characters you normally work with, support UTF-8, and render ANSI colors. These details are especially helpful when a repository contains Vietnamese filenames or commit messages.

On Windows, you can use Windows Terminal with PowerShell or Git Bash. Git Bash is convenient if you want Unix-style commands such as `pwd`, `ls`, `grep`, and the `less` pager. PowerShell integrates well with Windows and runs the Git CLI normally.

On macOS and Linux, the default Terminal along with Bash/Zsh usually supports UTF-8 out of the box. If Vietnamese characters appear as boxes or question marks, check the terminal's encoding/locale and font. Changing the terminal's font or encoding does not alter content stored inside the repository.

Git has the `core.quotepath` option to control how paths containing non-ASCII characters are displayed. Set:

```bash
git config --global core.quotepath false
```

Git will display Unicode filenames directly instead of escaping non-ASCII characters in certain outputs. This setting affects only how Git quotes paths when printing them; it does not convert file encodings and does not replace terminal UTF-8 configuration.

If you want to apply it to only one repository:

```bash
git config --local core.quotepath false
```

Check the value and where it is declared:

```bash
git config --show-origin --get core.quotepath
```

On older Windows/console versions, the code page can affect display. In Command Prompt you can check it with `chcp`; if UTF-8 is needed, you can try `chcp 65001` in the current window. That is a console session setting, not a repository configuration. Windows Terminal and modern shells generally handle Unicode better when the application, font, and environment all support UTF-8.

## 3. Enabling color for Git output

Colors help distinguish file states, branches, added/deleted lines in diffs, and sections of history. Git provides the general setting `color.ui`:

```bash
git config --global color.ui auto
```

Common values:

| Value | Behavior |
|---|---|
| `auto` | Use color when output goes to a color-capable terminal; usually the best choice |
| `always` | Always emit color codes, even when output is piped or redirected to a file |
| `never` | Disable colors |

`auto` is the right choice for most interactive environments. If you use `always`, color escape sequences may end up inside log files or make downstream tools harder to parse. If you want to disable colors for a single command run, use:

```bash
git -c color.ui=never status
```

The `-c` option applies the setting only to that command without writing changes to config files.

Some command groups have dedicated color settings:

| Setting | Output controlled |
|---|---|
| `color.branch` | Branch lists |
| `color.status` | `git status` output |
| `color.diff` | Diffs |
| `color.grep` | Search results from `git grep` |
| `color.interactive` | Git interactive menus |

You can inspect current color configurations:

```bash
git config --show-origin --get-regexp '^color\.'
```

If no dedicated configuration is set, Git uses defaults and the overall `color.ui` value.

## 4. Customizing colors for diff and status

You can set specific colors for diff components. Example:

```bash
git config --global color.diff.meta "bold blue"
git config --global color.diff.frag "cyan"
git config --global color.diff.old "red"
git config --global color.diff.new "green"
git config --global color.status.untracked "yellow"
```

Common attributes:

- `color.diff.meta`: diff metadata lines, such as `diff --git`, `index`, `---`, `+++`.
- `color.diff.frag`: hunk header lines starting with `@@`.
- `color.diff.old`: removed lines.
- `color.diff.new`: added lines.
- `color.status.untracked`: untracked files in status.

Git supports basic colors such as `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`, and `black`, as well as attributes like `bold`, `dim`, `ul`, and `reverse`. You can combine multiple attributes in a single value, such as `"bold yellow"`.

Verify the result:

```bash
git status
git diff
git diff --cached
git log --oneline --decorate --graph -10
```

If colors do not appear, check whether the terminal supports ANSI, whether `color.ui` is set to `never`, and whether output is being piped/redirected. Certain terminals, pagers, or intermediary applications may strip or fail to render color codes.

Do not rely solely on red and green to distinguish changes if you or reviewers have trouble differentiating those two colors. You can combine colors with bold styling, symbols, and the `+`/`-` markers built into diffs.

## 5. Understanding the pager when Git outputs many lines

Commands such as `git log`, `git diff`, or `git show` can produce long output. Git usually pipes output through a pager so you can read one screen at a time instead of flooding the terminal with all text at once.

The default pager is usually `less`. Some useful keys while viewing:

| Key | Action |
|---|---|
| `Space` or `PageDown` | Next screen |
| `b` or `PageUp` | Previous screen |
| `/` followed by keyword | Search in output |
| `n` | Next search match |
| `N` | Previous search match |
| `g` | Jump to top |
| `G` | Jump to bottom |
| `q` | Quit pager |

If the pager does not render colors, a common configuration with `less` is:

```bash
git config --global core.pager "less -FRX"
```

Meaning of the options:

- `-F`: exit immediately if the content fits on one screen.
- `-R`: allow rendering ANSI color control sequences.
- `-X`: do not clear the terminal screen when the pager exits.

This command only works when the shell can locate the `less` program. Git Bash typically includes Unix utilities; in other environments, check that `less` is installed and in PATH. If a pager setting makes output hard to read, you can unset the custom configuration so Git uses its default:

```bash
git config --global --unset core.pager
```

You can also bypass the pager for a single command:

```bash
git --no-pager log --oneline -20
git --no-pager diff
```

To see where the pager is configured from:

```bash
git config --show-origin --get core.pager
```

If output is redirected to a file or piped, consider using `--no-pager` and controlling color separately to suit the receiving tool.

## 6. Inspecting and managing Git's terminal configuration

Git reads configuration from multiple scopes. Common scopes:

| Scope | How to set | Effective scope |
|---|---|---|
| System | `git config --system` | Machine users; usually requires admin privileges |
| Global | `git config --global` | Current user account |
| Local | `git config --local` | Current repository |
| Command | `git -c key=value ...` | A single command |

Configuration at a narrower scope normally overrides values at a broader scope. For example, `color.ui=false` locally can turn off color in one repository even when global has `auto` enabled.

View configuration values and sources:

```bash
git config --show-origin --list
```

Search specifically for terminal-related settings:

```bash
git config --show-origin --get-regexp '^(color\.|core\.pager|core\.quotepath)'
```

Edit the global config file with:

```bash
git config --global --edit
```

Edit the current repository's local config:

```bash
git config --local --edit
```

If a setting does not take effect as expected, use `--show-origin` to find out which file supplied the value. This helps uncover local settings overriding global ones or another configuration file being read.

Some config inspection commands may display sensitive details if tokens or credentials were stored in the wrong place. Before sharing `git config --list` output, review and redact secrets.

## 7. How to read a Git error message

A Git error message usually contains one or more parts:

1. **The command you just ran:** identifies exactly which operation failed.
2. **The target object:** filename, branch, commit, remote, or path Git was processing.
3. **The immediate cause:** for example, path not found, permission denied, or update rejected.
4. **Git's hint:** some errors include a `hint:` line suggesting how to proceed.
5. **Exit code:** the program returns a non-zero code when a command fails; scripts can inspect this code to decide the next step.

When reading an error, do not read only the last line. Read from top to bottom to find the referenced object and see whether Git provided a hint. Then inspect repository state before running a corrective command.

A basic diagnostic sequence:

```bash
git status
git branch --show-current
git rev-parse --show-toplevel
git log --oneline --decorate -5
```

You do not need to run all four every time. Choose commands matching the error message: for path errors, inspect paths and current directory; for push errors, inspect branch, remote, and history; for checkout errors, inspect working tree state.

## 8. Common error messages and how to handle them

### `fatal: not a git repository`

Example:

```text
fatal: not a git repository (or any of the parent directories): .git
```

Git could not find a repository in the current directory or any parent directories. You may be outside the project, inside a subdirectory that does not belong to a repository, or in the wrong terminal.

Check your current directory:

```bash
pwd
git rev-parse --show-toplevel
```

In PowerShell, use `Get-Location` instead of `pwd` if you want a PowerShell path object. Navigate to the project directory and run the command again.

### `pathspec ... did not match any files`

Example:

```text
error: pathspec 'src/App.java' did not match any file(s) known to git
```

Git could not find a path or ref name matching the pathspec in the command's context. Possible causes include typos, letter casing mismatches, running from a subdirectory so relative paths resolve differently than expected, or an untracked file.

Check:

```bash
git status --short
git ls-files -- src/App.java
```

If it is a branch/ref, use `git branch --list` or `git tag --list` to confirm the actual name. Do not add quotes or change names at random before verifying the path and command context.

### `src refspec ... does not match any`

Example:

```text
error: src refspec main does not match any
error: failed to push some refs to 'origin'
```

Git could not find the source ref `main` in the local repository. The current branch may have a different name, the branch may not have been created yet, or the repository may have no commits yet.

Check:

```bash
git branch --show-current
git branch --list
git log -1 --oneline
```

If a new repository has no commits yet, create the first commit after staging the required contents. If the branch has a different name, push the right source and destination refs instead of assuming the name is always `main`.

### `rejected ... non-fast-forward`

Example:

```text
! [rejected]        main -> main (non-fast-forward)
error: failed to push some refs
hint: Updates were rejected because the tip of your current branch is behind
```

The remote has commits that local history does not yet contain, so Git rejects updates that could discard remote history. Fetch and inspect both sides first:

```bash
git fetch origin
git log --oneline --left-right --graph HEAD...origin/main
```

Replace `origin/main` with the correct remote-tracking branch. After understanding the diverging commits, integrate changes via merge or rebase per team convention, resolve any conflicts, and push again. Never use `--force` merely to bypass a non-fast-forward message.

### `Permission denied (publickey)`

Example:

```text
git@host.example: Permission denied (publickey).
fatal: Could not read from remote repository.
```

The remote uses SSH, yet the current machine could not authenticate with a matching key, or the account lacks permission to access the repository.

Check the remote URL:

```bash
git remote -v
```

Confirm you are using the right account, the SSH key has been added to the source hosting service, and the SSH agent has loaded the required key. The command to test SSH connectivity depends on the server; for example, with a service using hostname `host.example`:

```bash
ssh -T git@host.example
```

Replace the hostname with the actual server. Never send your private key or secret agent contents to anyone else.

### `detected dubious ownership`

Git may refuse to operate on a repository if it detects the directory is owned by a different user than the one running Git. This commonly happens when a repository was created under another account, runs in a shared environment, or after ownership changes.

First, verify the path and repository owner. Only when you trust that repository should you add the exact path to the safe list:

```bash
git config --global --add safe.directory "/path/to/trusted/repository"
```

Replace the path with the actual path. Do not add a wildcard to trust every repository broadly, and do not use this setting to mask an unexamined ownership issue.

### Line ending warnings

Example:

```text
warning: LF will be replaced by CRLF the next time Git touches it
```

This is a warning about line-ending conversion, not necessarily an error causing a command to fail. Check attributes and configuration:

```bash
git check-attr text eol -- path/to/file
git ls-files --eol -- path/to/file
git config --show-origin --get core.autocrlf
```

Compare the output against the project's `.gitattributes` conventions. Do not mass-change line-ending configuration just to silence a warning without knowing the impact on other team members.

## 9. Distinguishing errors, warnings, and hints

Not every line containing `error`, `warning`, or `hint` means the same thing:

| Message type | Common meaning | How to respond |
|---|---|---|
| `fatal:` | Git cannot continue the operation | Read the cause and check status before fixing |
| `error:` | A step or object is invalid | Check filename, ref, option, and context |
| `warning:` | There is an issue worth noting, yet the command may still complete | Verify the impact; do not assume the operation failed |
| `hint:` | Suggestion from Git regarding cause or next steps | Read alongside error lines; evaluate whether the hint fits your repository |

Exit codes are also useful when using Git in scripts:

```bash
git status
echo $?
```

In Bash/Zsh, `$?` is the exit code of the last command executed; `0` typically indicates success, while non-zero indicates an error or special condition. In PowerShell, use the automatic variable `$LASTEXITCODE` to read the exit code of native programs like Git. Do not reuse the same variable syntax across different shells if a script needs to run in multiple environments.

## 10. Checklist when terminal output is hard to read or Git errors

When output has incorrect colors, garbled characters, or confusing messages, check these items in order:

1. Does your terminal support ANSI colors and does the font include the needed glyphs?
2. Is the shell inside the right repository? Run `git rev-parse --show-toplevel`.
3. Is color configuration overridden locally or globally? Run `git config --show-origin --get-regexp '^color\.'`.
4. Is the pager working properly? Try `git --no-pager log --oneline -10`.
5. Are Unicode filenames displaying properly? Check `core.quotepath` and terminal encoding.
6. Which file, branch, commit, or remote does the error message mention? Verify that exact object.
7. Did the command actually fail or only emit a warning? Check the output text and exit code.
8. Before running a corrective command, do you understand the working tree and index state? Run `git status`.

When asking someone else for help, share the command you ran, the full relevant error output, and the output of `git status`. Redact tokens, passwords, private keys, URLs containing credentials, and sensitive data before sharing.

## Conclusion

Use a terminal emulator and shell suited to your operating system, ensure UTF-8 and ANSI support, enable `color.ui=auto`, and customize the pager when reading long output. Use `core.quotepath=false` if you want Unicode filenames displayed directly. When encountering errors, read the full message, identify the file/ref/remote involved, and inspect repository state before acting. Configuration can be traced with `git config --show-origin`, helping locate the source overriding your desired settings.

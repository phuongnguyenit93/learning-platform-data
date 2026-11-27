# Checking Version, Help, and Command Compatibility

Git has evolved across many versions. A machine may have Git installed via a standalone installer, a package manager, Git for Windows, or bundled with an IDE. As a result, two terminals on the same machine sometimes invoke two different Git installations. A command that runs on your machine may also not exist or may not support the same options on a teammate's machine or in a CI environment.

Before using a new command, writing an automated script, or writing instructions for a team, identify the exact Git version being invoked, consult the help documentation for that specific command, and verify the available options in the actual environment. This lesson explains how to check the version, look up help documentation, and evaluate compatibility to use Git consistently.

## 1. Checking the running Git version

### 1.1. Using git --version

The most basic command:

~~~bash
git --version
~~~

Example output:

~~~text
git version 2.43.0.windows.1
~~~

The output shows the version of the Git program found by the shell when running the command. The suffix may indicate the packaging or platform, such as the Windows build. Do not strip or ignore the suffix when investigating differences between distributions.

Git versions typically follow the format:

`major.minor.patch`

- **major:** major version.
- **minor:** minor version, usually adding features and improvements.
- **patch:** bug-fix release within the version line.

Some distributors append suffixes or build information. Therefore, do not compare version strings with naive character comparisons; use proper version comparison rules or test command capabilities directly.

### 1.2. Checking the exact Git binary invoked by the terminal

A machine can have multiple Git installations. For example, Git for Windows may be located in `C:\Program Files\Git`, while an IDE may use a bundled Git or a separately configured path.

On Windows PowerShell:

~~~powershell
Get-Command git -All | Format-Table CommandType, Source, Definition -AutoSize
~~~

In Command Prompt:

~~~bat
where.exe git
~~~

In Bash or a similar shell on Linux/macOS:

~~~bash
type -a git
~~~

These commands show which executables or aliases named `git` the shell can find. If there are multiple results, the first entry in resolution order is typically the command invoked when you type `git`.

Then run:

~~~bash
git --version
~~~

to confirm the version of the program currently selected.

If your IDE has its own Git path configuration, check the IDE's settings and run the version check from the IDE's integrated terminal. Results from the system terminal do not guarantee that the IDE is using the same executable.

### 1.3. Why might the displayed version differ?

Some common causes:

- PATH contains multiple Git installation directories and the search order differs.
- An IDE or GUI tool uses a bundled Git.
- The terminal was opened before PATH changed, so it retains the old environment.
- The machine uses Git from a package manager, while another terminal invokes Git for Windows or a standalone installation.
- CI uses an image or runner with a different Git version than the development machine.

When encountering "command not found", "unknown option", or differing behavior, check the executable and version in the exact environment where the error occurs. Do not jump to the conclusion that the repository is corrupted.

## 2. Viewing Git build and environment information

In addition to the version number, Git can provide build information:

~~~bash
git version --build-options
~~~

Depending on the distribution, the output may show details about the compilation or runtime environment. This is useful diagnostic data when two Git installations have the same version number but are packaged differently.

You can view the directory containing Git's helper programs:

~~~bash
git --exec-path
~~~

This command returns the path Git uses to locate internal executables. It is not always the full path to the `git.exe` file or `git` binary invoked by the shell. To identify the actual executable, use `Get-Command`, `where.exe`, or `type -a` as shown earlier.

View the Git metadata directory of the current repository:

~~~bash
git rev-parse --git-dir
git rev-parse --show-toplevel
~~~

- `--git-dir` shows the location of the Git directory.
- `--show-toplevel` shows the root directory of the working tree.

These two commands help confirm which repository you are in, especially when the terminal is opened inside nested directories or when using a linked worktree.

## 3. Using Git's general help

### 3.1. git --help and git help

To view general help:

~~~bash
git --help
~~~

Or:

~~~bash
git help
~~~

The general documentation introduces syntax, command groups, and how to access manual pages. Display behavior depends on the operating system and documentation viewer configuration: Git may open a man page, a text viewer, or an HTML page.

If you only need to view the command list in the terminal:

~~~bash
git -h
~~~

The short output shows general usage syntax and the main command groups.

### 3.2. Listing available commands

View Git commands:

~~~bash
git help -a
~~~

View overview guides:

~~~bash
git help -g
~~~

These commands are useful when you know your goal but do not remember the command name. For example, `git help -g` may point to guides on revisions, attributes, hooks, or workflows depending on the version.

Not every command in the list is one users frequently need to invoke directly. Some commands are for administration, internal plumbing, or advanced workflows. Read the corresponding help page before using them.

### 3.3. Finding configuration documentation

To view documentation on the configuration system:

~~~bash
git help config
~~~

To view documentation on commit and revision syntax:

~~~bash
git help revisions
~~~

These guide pages explain concepts shared across many commands. For example, understanding revisions helps read expressions such as `HEAD~1`, `main..feature`, or `tag^{commit}` more accurately.

## 4. Viewing help for a specific command

### 4.1. Using -h for short syntax

When you need a quick syntax check:

~~~bash
git commit -h
git switch -h
git stash push -h
~~~

The `-h` option typically displays the usage section and the list of options for the command. This is a fast way to check whether an option is supported by the current Git version.

For example, before using a newer stash option, inspect:

~~~bash
git stash push -h
~~~

If the help output does not list that option, the current version may not support it yet, or the command's syntax differs from the documentation you are reading.

### 4.2. Using git help for full documentation

~~~bash
git help commit
git help switch
git help stash
~~~

The full documentation usually explains:

- Syntax and meaning of each option.
- Default values.
- Interactions with configuration settings.
- Edge cases.
- Examples and behavioral notes.

If `git help <command>` fails to open a man page, the system may lack a documentation viewer or have an unsuitable viewer configuration. On many Git installations, you can try opening the HTML documentation:

~~~bash
git help -w commit
~~~

Depending on packaging, HTML documentation may not be installed. In that case, use `git <command> -h` for short syntax or read the official documentation matching the version you are using.

### 4.3. Reading the relevant sections

A long help page does not mean you have to read all of it every time. Look for these sections:

- **NAME / SYNOPSIS:** command name and syntax.
- **DESCRIPTION:** what the command does.
- **OPTIONS:** options and their effects.
- **CONFIGURATION:** related configuration keys.
- **EXAMPLES:** usage scenarios.
- **SEE ALSO:** related commands or concepts.

In particular, check how a command interacts with the working tree, index, and history before using options capable of overwriting files or rewriting commits.

## 5. Determining whether a command is compatible with your version

### 5.1. Not every command exists in every version

Git gains new commands and options over time. A guide may use syntax that only appeared in a newer version.

Examples:

- `git switch` and `git restore` were introduced in Git 2.23. They provide dedicated interfaces for certain tasks previously performed with `git checkout`.
- The `git stash push --staged` option requires Git 2.35 or later.

If your machine runs an older version, the command may report an unrecognized subcommand or option. That does not necessarily mean you mistyped it; check the feature's version requirement.

### 5.2. Checking via the command's own help

For example, to find out whether the current Git supports `switch`:

~~~bash
git switch -h
~~~

To find out whether `stash push` has the `--staged` option:

~~~bash
git stash push -h
~~~

This is a direct check against the executable being invoked. It is usually more reliable than merely reading an online tutorial that does not specify a version.

Note: some commands return a non-zero exit code when printing usage only. During interactive checks, read the output; do not assume a command does not exist based solely on its exit code.

### 5.3. Using compatible commands on older versions

If the environment does not support `git switch`, you can use `git checkout` for switching branches:

~~~bash
git switch main
~~~

Equivalent in older versions:

~~~bash
git checkout main
~~~

Creating a branch and switching to the new branch:

~~~bash
git switch -c feature/login
~~~

Older approach:

~~~bash
git checkout -b feature/login
~~~

If `git restore --staged` is unavailable, you can unstage a file with:

~~~bash
git reset HEAD -- path/to/file
~~~

On newer versions:

~~~bash
git restore --staged path/to/file
~~~

If `git restore` is unavailable for restoring working tree contents from the index, the older approach commonly used is:

~~~bash
git checkout -- path/to/file
~~~

Older commands have more modes of operation and syntax that is easier to misuse. Read the help before using them, especially with `checkout`, since this command can both switch branches and update paths.

Do not substitute commands mechanically if the task differs. Clarify whether you want to switch branches, unstage a file, or restore file contents.

## 6. Distinguishing version errors from syntax and environment errors

When a command fails to run, classify the root cause.

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `git: command not found` or unrecognized command | Git is not installed or PATH lacks the executable | `Get-Command git -All`, `where.exe git`, `type -a git` |
| `unknown option` | Version does not support the option or syntax is wrong | `git --version`, `git command -h` |
| `not a git repository` | Terminal is outside a working tree or Git directory | `pwd`, `git rev-parse --show-toplevel` |
| `pathspec did not match` | Path or branch name is incorrect in the current context | `git status`, `git branch --all`, `git ls-files` |
| Help fails to open | Missing man viewer, HTML docs, or viewer config | Use `git command -h`, try `git help -w command` |
| IDE behaves differently from terminal | IDE uses a separate Git executable | Check the Git path in IDE settings and integrated terminal |

Do not immediately upgrade Git when encountering an error. First check the executable, syntax, working directory, and repository state. Proper classification prevents changing the environment when the actual cause is simply a mistyped path or being in the wrong repository.

## 7. Checking configuration that affects command behavior

The same Git command can produce different results due to configuration. For example, pull behavior can depend on `pull.rebase`, default push behavior depends on `push.default`, and diff rendering can depend on `diff.external` or the pager.

View configuration along with its source origin:

~~~bash
git config --show-origin --list
~~~

View a specific key:

~~~bash
git config --show-origin --get pull.rebase
git config --show-origin --get push.default
~~~

Configuration can come from multiple levels:

- System: applies machine-wide.
- Global: applies to the current user.
- Local: applies to a specific repository.
- Worktree: applies to a specific worktree when supported.

More specific levels can override values set at broader levels. When command behavior differs from expectations, inspect both the value and where it is defined.

Do not share full configuration output publicly if it contains internal repository URLs, usernames, or sensitive environment details. Only excerpt the relevant section after reviewing the contents.

## 8. Checking compatibility across teams and CI

### 8.1. Agreeing on a minimum version

If a project uses newer commands or options, agree on a minimum Git version for:

- Team members' development machines.
- IDEs or GUIs supported by the team.
- Build and CI machines.
- Containers or deployment images that run Git.

You can document the requirement in onboarding docs, for example:

~~~text
Git 2.35 or later
~~~

This is only an example. Choose the minimum version based on the features your project actually uses; do not copy this number if the repository does not require those features.

### 8.2. Checking the version in CI

In CI jobs, you can print the Git version at the start of the log:

~~~bash
git --version
~~~

If a script depends on a specific option, explicitly define the minimum version or check command capability before running. This ensures CI logs show the actual environment rather than simply failing a command at the end of the pipeline.

### 8.3. Do not rely solely on version strings

Some distributions may backport bug fixes or features without changing the version number in the way you expect. Conversely, version strings with vendor suffixes can make naive string comparisons inaccurate.

For automated scripts:

- If a feature has an official minimum version, declare and check that condition.
- Where possible, check the specific capability via help output or a safe probe.
- Do not run destructive commands just to test whether they exist.
- If conditions are not met, fail fast with a clear message instead of continuing with unverified fallback behavior.

For systems supporting multiple Git versions, run tests on both the minimum and the latest versions your project officially supports.

## 9. A lookup workflow before using a new command

When reading a Git tutorial or receiving a command from a teammate, you can follow this sequence:

**Step 1 — Identify the environment**

~~~bash
git --version
git rev-parse --show-toplevel
~~~

Confirm the current version and repository.

**Step 2 — Check command syntax**

~~~bash
git <command> -h
~~~

Replace `<command>` with the actual command name, such as `switch`, `restore`, or `stash`. Angle brackets in documentation are placeholders only; do not type them literally into the terminal.

**Step 3 — Read the full documentation when needed**

~~~bash
git help <command>
~~~

Focus on options, default values, and repository impact.

**Step 4 — Check relevant configuration**

~~~bash
git config --show-origin --list
~~~

Inspect only the necessary keys and keep in mind that values can be set at multiple levels.

**Step 5 — Test on a safe repository or branch**

For read-only operations like `git log`, `git status`, or `git diff`, you can test directly. For operations that modify history or overwrite files, test in a sandbox repository or ensure you have a recovery path.

**Step 6 — Document version requirements if sharing with the team**

If the instructions require a new feature, note the minimum version or provide a verified compatible alternative.

## 10. End-to-end example: guiding a team to use git switch

A team member writes onboarding documentation and includes the command:

~~~bash
git switch -c feature/profile
~~~

A teammate using an older Git version gets an error saying the `switch` command is not recognized.

How to investigate:

1. Check the version on the machine where the error occurred:

~~~bash
git --version
~~~

2. Identify the executable being invoked:

- PowerShell: `Get-Command git -All`.
- Command Prompt: `where.exe git`.
- Bash: `type -a git`.

3. Check help:

~~~bash
git switch -h
~~~

4. If the version is older than Git 2.23, use compatible syntax:

~~~bash
git checkout -b feature/profile
~~~

5. Update the onboarding documentation to explicitly state the requirement for Git 2.23 or later if the team wants to use `switch`, or provide the older syntax for environments that have not yet upgraded.

6. Test the same command in the IDE terminal and CI to ensure supported environments use an appropriate version.

This example shows that identifying the exact version and executable often resolves discrepancies without needing to change the repository.

## 11. Quick reference table

| Need | Command |
| --- | --- |
| View Git version | `git --version` |
| View build information | `git version --build-options` |
| View executable in PowerShell | `Get-Command git -All` |
| View executable in Command Prompt | `where.exe git` |
| View executable in Bash | `type -a git` |
| View helper programs directory | `git --exec-path` |
| View Git directory | `git rev-parse --git-dir` |
| View working tree root | `git rev-parse --show-toplevel` |
| General help | `git --help` |
| List of commands | `git help -a` |
| List of guides | `git help -g` |
| Short help for a command | `git <command> -h` |
| Full documentation for a command | `git help <command>` |
| HTML documentation if available | `git help -w <command>` |
| View configuration and sources | `git config --show-origin --list` |

## 12. Summary

`git --version` reports the version of the executable that the shell is invoking. When a machine has multiple Git installations, check the path using the appropriate tool for your shell and separately check the Git used by your IDE or CI.

General help lets you discover commands; `git <command> -h` provides quick syntax; `git help <command>` explains options and behavior in full. Before using a new feature, verify the version and help in your actual environment.

Compatibility depends not only on the version number, but also on the executable, operating system, shell, filesystem, configuration, and CI environment. When writing guides or scripts for a team, state the minimum required version, verify relevant features, and provide verified alternatives. This practice keeps Git commands repeatable and consistent across different development environments.

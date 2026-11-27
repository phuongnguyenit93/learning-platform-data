# Environment Variables, Git Paths, and Configuration Precedence

A single machine can have multiple Git installations, open repositories from multiple terminals, and use different configurations per project. In such cases, the `git` command runs, yet it might invoke the wrong executable, read the wrong repository, or pick up an unexpected configuration value. The cause usually lies in `PATH`, process environment variables, and the precedence order of Git configuration files.

In the **Installation and Configuration** chapter of the **SOURCE_CONTROL_GIT** module, this lesson helps you distinguish three layers that are often confused: the shell locating the Git program via `PATH`; `GIT_*` environment variables controlling the behavior of the Git process; and `git config` supplying settings across scopes. You will learn how to check which Git binary is actually running, trace the origin of a configuration value, resolve conflicts across scopes, and set environment variables safely on Windows, Linux, or macOS.

After this lesson, you will be able to:

- Explain how `PATH` determines which Git executable the shell invokes.
- Check the location and version of the running Git binary.
- Distinguish operating system environment variables from settings in `git config`.
- Identify common `GIT_*` variables that affect the repository, index, object database, and remote authentication.
- Explain the precedence order of system, global, local, worktree, and command scopes.
- Trace the config file supplying a value using `git config --show-origin` and `--show-scope`.
- Set, inspect, and unset environment variables in PowerShell or Unix-style shells.
- Diagnose scenarios where terminals, IDEs, and CI use different configurations.

## 1. Three configuration layers to distinguish

When running a Git command, multiple layers can affect the outcome simultaneously:

1. **Program path (PATH)**: where the shell looks for the `git` executable and which installation it selects if multiple exist.
2. **Environment variables**: the Git process receives values from the shell or operating system. Certain variables alter how Git locates the repository, index, object database, configuration, or remote connections.
3. **Git config**: configuration files storing settings such as `user.name`, `user.email`, `core.editor`, `pull.rebase`, and `remote.<name>.url`.

You can picture the execution flow as:

~~~text
Terminal / IDE / CI
        |
        | PATH: selects executable
        v
      git.exe / git
        |
        | Environment: GIT_DIR, GIT_INDEX_FILE, ...
        | Git config: system -> global -> local -> worktree -> command
        v
 Repository and Git operations
~~~

These three layers interact, yet they do not form a single flat precedence table. `PATH` selects the program before Git starts. Environment variables can govern specific behaviors. Git config follows scope-based merging rules. Therefore, when a setting looks wrong, identify the exact layer causing the effect instead of blindly editing a config file.

## 2. PATH determines which Git command runs

`PATH` is the list of directories the shell searches when you type a program name. If the machine has multiple Git installations—such as Git for Windows, a Git bundled with an IDE, or one installed via a package manager—the order of directories in `PATH` can decide which one gets invoked.

On Windows, check using PowerShell:

~~~powershell
Get-Command git -All
where.exe git
~~~

`Get-Command` shows all commands named `git` that PowerShell finds, including aliases or functions if any exist. `where.exe` lists `git` executables found on `PATH`. If multiple results appear, check their order and locations before concluding which installation is being used.

Get the path of the command chosen by PowerShell:

~~~powershell
(Get-Command git).Source
git --version
~~~

On Linux or macOS:

~~~bash
type -a git
command -v git
git --version
~~~

`type -a` can list all definitions and locations matching the command name; `command -v` shows the command resolved by the shell. If the shell caches executable paths, open a new terminal or refresh the shell cache after modifying `PATH`.

Different Git builds may report differences in version, features, or bundled helpers. If an IDE and terminal produce different results, inspect the executable path in both environments.

### `git --exec-path` is not the path to `git.exe`

The command:

~~~bash
git --exec-path
~~~

returns the directory containing internal helper programs that Git invokes during execution, such as certain helpers. It is not necessarily the location of the `git` executable invoked by the shell. To find the executable, use `Get-Command`/`where.exe` on Windows or `type`/`command` on Unix-like systems.

## 3. Checking and editing PATH on Windows

Git for Windows typically provides `git.exe` in a directory such as:

- `C:\Program Files\Git\cmd`
- `C:\Program Files\Git\bin`

The actual path depends on the installation location. Some tools may place Git in their own directory or provide an embedded Git.

To inspect the current `PATH` in PowerShell:

~~~powershell
$env:Path -split ';'
~~~

If you want to test a Git directory in the current PowerShell session, you can prepend it to the process `PATH`:

~~~powershell
$gitBin = 'C:\Program Files\Git\cmd'
$env:Path = "$gitBin;$env:Path"
Get-Command git
git --version
~~~

Replace the example path with the actual directory containing `git.exe`. This change applies only to the current PowerShell process and child processes launched from it; opening a new terminal will not inherit this change automatically.

To make a persistent change, use the Windows Environment Variables interface:

1. Open the account or system environment variables editor.
2. Select the `Path` variable in the appropriate scope.
3. Add the directory containing the Git executable to the list.
4. Set the proper order if multiple Git installations exist.
5. Open a new terminal and verify with `Get-Command git -All`, `where.exe git`, and `git --version`.

The User `Path` affects only the current user; the System `Path` has broader scope and usually requires administrative privileges. Only add trusted directories provided by the Git installer. Avoid replacing the entire `PATH` with a short string, as other programs could become unreachable.

Do not use `setx PATH` with an arbitrarily concatenated value. In some environments, this can truncate existing `PATH` entries or hit length limits. The Environment Variables UI lets you view and edit individual entries more clearly.

## 4. PATH on Linux and macOS

In Unix-style shells, `PATH` is typically a colon-separated list of directories. Inspect it:

~~~bash
printf '%s\n' "$PATH"
type -a git
command -v git
~~~

To prepend a directory to `PATH` in the current session:

~~~bash
export PATH="/opt/git/bin:$PATH"
~~~

To persist the setting, place the `export` command in the startup file appropriate for your shell and login session type, such as `~/.bashrc`, `~/.bash_profile`, or `~/.zshrc`. Not every terminal reads the same file; identify your shell with:

~~~bash
echo "$SHELL"
ps -p $$ -o comm=
~~~

After editing the shell config file, reload the corresponding file or open a new terminal and re-verify the Git location. On macOS, `PATH` can also be configured by shell startup files, package managers, or IDE environments.

## 5. How are environment variables passed to processes?

Environment variables are name-value pairs a process inherits from the environment that launched it. When a terminal starts the Git program, Git receives the environment variables supplied by the terminal. Child processes typically inherit their parent process's environment.

This explains why:

- Git run in a terminal can behave differently from Git run inside an IDE.
- A new terminal may not see a variable just set in an older terminal.
- A CI runner may have a different `HOME`, `PATH`, or `GIT_*` values than a developer's machine.
- A script run via a different shell may not read the same startup files.

### PowerShell: setting a variable in the current session

~~~powershell
$env:GIT_TERMINAL_PROMPT = '0'
git fetch
~~~

Inspect the value:

~~~powershell
$env:GIT_TERMINAL_PROMPT
~~~

Remove the variable from the current session:

~~~powershell
Remove-Item Env:GIT_TERMINAL_PROMPT
~~~

### PowerShell: persisting a variable at user scope

~~~powershell
[Environment]::SetEnvironmentVariable('MY_TOOL_MODE', 'review', 'User')
~~~

The value is saved for subsequent login processes of the user. Already-open terminals or IDEs usually do not pick up the new value automatically; start a new process to verify. You can delete a saved variable:

~~~powershell
[Environment]::SetEnvironmentVariable('MY_TOOL_MODE', $null, 'User')
~~~

### Bash or Zsh: setting and unsetting variables

~~~bash
export GIT_TERMINAL_PROMPT=0
printf '%s\n' "$GIT_TERMINAL_PROMPT"
unset GIT_TERMINAL_PROMPT
~~~

`export` sets the variable for the shell and child processes. `unset` removes the variable from the current shell environment. To persist it, place `export` in the appropriate shell startup file.

Never place sensitive variables in files committed to a repository. For tokens or credentials, use a credential manager, CI secret store, or appropriate security mechanism.

## 6. Common `GIT_*` variables

Git has many environment variables. You do not need to memorize all of them; what matters is recognizing variables that can cause Git to operate on a different repository or dataset than expected.

| Variable | General effect | When to pay attention |
| --- | --- | --- |
| `GIT_DIR` | Specifies the Git directory path instead of standard repository discovery | Commands unexpectedly operate on another repository's metadata |
| `GIT_WORK_TREE` | Specifies the working tree corresponding to the Git directory | Git uses the wrong source directory |
| `GIT_COMMON_DIR` | Specifies the common Git directory in certain repository/worktree layouts | Investigating linked worktrees or shared metadata |
| `GIT_INDEX_FILE` | Selects an index file instead of the default index | Status or commit does not reflect the staging area you are looking at |
| `GIT_OBJECT_DIRECTORY` | Specifies the primary object database directory | Git cannot find objects where expected |
| `GIT_ALTERNATE_OBJECT_DIRECTORIES` | Adds alternate object directories for object lookup | Repository uses a shared object store |
| `GIT_CEILING_DIRECTORIES` | Limits where Git stops searching upward for a parent repository | Commands in nested directories fail to find a repository as expected |
| `HOME` | Affects the home directory used by Git and related tools | Global config or SSH keys are searched in an unexpected location |
| `XDG_CONFIG_HOME` | Can alter the config file location per XDG standard | Global config resides inside an XDG config directory |
| `GIT_CONFIG_GLOBAL` | Selects an alternate global config file | `--global` values are not in the familiar file |
| `GIT_CONFIG_SYSTEM` | Selects an alternate system config file | System configuration differs from the standard environment |
| `GIT_CONFIG_NOSYSTEM` | Skips the system config file when enabled | Results differ due to skipped system config |
| `GIT_EXEC_PATH` | Specifies the directory containing Git's internal helpers | Git fails to locate or uses the wrong helper |
| `GIT_SSH` or `GIT_SSH_COMMAND` | Selects the SSH program/command for remote connections | Authentication failures or wrong SSH key used |
| `GIT_TERMINAL_PROMPT` | Controls whether Git prompts for input in the terminal | Non-interactive CI hangs or cannot prompt for password |
| `GIT_TRACE` | Enables tracing to diagnose Git execution | Investigating helper calls or child processes |

Some advanced variables should only be set for an explicit purpose. For instance, `GIT_DIR` and `GIT_WORK_TREE` can make a `git` command run inside the current directory while acting on a repository elsewhere. `GIT_INDEX_FILE` can make `git status` and `git commit` use a different staging area. If you observe unusual behavior, check these variables before attempting repository repairs.

Inspect related environment variables in PowerShell:

~~~powershell
Get-ChildItem Env:GIT*
~~~

In Bash/Zsh:

~~~bash
env | grep '^GIT_'
~~~

When sharing output for troubleshooting, redact tokens, private paths, or credentials before sending.

## 7. Distinguishing environment variables from `git config`

Not every Git setting is an environment variable. For example:

| Goal | Mechanism typically used |
| --- | --- |
| Choose the Git executable | Shell/OS `PATH` |
| Set default commit name and email | `git config` `user.name` and `user.email` |
| Choose default editor | `git config core.editor` or the environment's editor variable |
| Specify Git directory | `GIT_DIR` or the `-C` option to choose working directory |
| Select a different index | `GIT_INDEX_FILE` |
| Choose SSH command | `GIT_SSH_COMMAND` or SSH config |
| Choose pull integration method | `git config pull.rebase` or `pull.ff` |
| Choose global config file | `GIT_CONFIG_GLOBAL` |

For example, setting the default commit identity:

~~~bash
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"
~~~

This is a setting in Git config. Git also has variables such as `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and `GIT_COMMITTER_EMAIL` to override author or committer details for a specific process. They are not a good substitute for everyday identity configuration.

Inspect configured identity:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

If a commit has an author or committer different from the values you see in config, check `GIT_AUTHOR_*` and `GIT_COMMITTER_*` in the environment running the command.

## 8. Git config precedence order

Git reads configuration from multiple scopes. When the same key has multiple values, the value from the higher-precedence scope is typically used for single-valued reads.

Precedence order from lowest to highest:

~~~text
System
   |
   v
Global
   |
   v
Local (repository)
   |
   v
Worktree
   |
   v
Command
~~~

| Scope | Coverage | Common way to set |
| --- | --- | --- |
| system | Entire machine or Git installation | `git config --system` |
| global | Current user | `git config --global` |
| local | Current repository | `git config --local` |
| worktree | Specific worktree when worktree config is enabled | `git config --worktree` |
| command | Single Git invocation | `git -c key=value ...` |

For example, the same `pull.rebase` key can be set at multiple levels:

~~~bash
git config --global pull.rebase false
git config --local pull.rebase true
git -c pull.rebase false pull
~~~

In that repository, the local value overrides global. For the `git -c` invocation specifically, the command value takes higher precedence than saved configs and affects only that command.

The order above applies to configuration values of the same key that merge across scopes. Some keys are multi-valued or have special rules; do not assume every key holds only a single value. Whenever you need certainty, inspect all sources and read the documentation for that specific key.

## 9. Where are configuration files located?

Common locations:

| Scope | Common location | Notes |
| --- | --- | --- |
| system | `/etc/gitconfig` on Unix-like; system config file in Git install folder on Windows | May be managed by machine administrators |
| global | `~/.gitconfig` or `$XDG_CONFIG_HOME/git/config` | Tied to the user account |
| local | `.git/config` or corresponding common Git directory | Applies to the repository only |
| worktree | `config.worktree` in the worktree's Git directory | Used only when `extensions.worktreeConfig` is enabled |

Actual paths depend on the operating system, `HOME`, `XDG_CONFIG_HOME`, Git installation location, and repository layout. With linked worktrees, local config is typically shared per repository; worktree config allows certain settings to differ across worktrees.

Check which configuration files and scopes are supplying values:

~~~bash
git config --list --show-origin --show-scope
~~~

If your Git version does not support `--show-scope`, use:

~~~bash
git config --list --show-origin
~~~

These flags show which file each value comes from and, on supported versions, its corresponding scope. This is a quick way to see why a global setting is being overridden locally or per worktree.

### Worktree configuration

In a repository using linked worktrees, you can enable per-worktree configuration:

~~~bash
git config extensions.worktreeConfig true
~~~

Once the extension is enabled, Git can store certain separate settings in `config.worktree`. For example, setting a specific editor for the current worktree:

~~~bash
git config --worktree core.editor "code --wait"
git config --worktree --get core.editor
~~~

The command affects only the current worktree. Understand your repository structure before enabling the extension on a repository used by multiple tools or differing Git versions; certain settings that inherently belong per worktree should be reviewed when switching configurations. Worktree config is a Git configuration mechanism, not an environment variable.

## 10. Checking a value and its configuration source

To inspect a specific key along with its source:

~~~bash
git config --show-origin --get core.editor
git config --show-origin --get pull.rebase
git config --show-origin --get user.email
~~~

If a key can have multiple values, use:

~~~bash
git config --show-origin --get-all remote.origin.fetch
~~~

To search all related keys:

~~~bash
git config --show-origin --show-scope --get-regexp '^(core|pull|user)\.'
~~~

When you suspect environment variables are altering behavior, inspect everything together:

~~~powershell
Get-ChildItem Env:GIT*
git config --list --show-origin --show-scope
git status -sb
git rev-parse --show-toplevel
~~~

These commands answer four distinct questions:

- Are any `GIT_*` variables being passed into the process?
- Which configs is Git reading, and from which scopes?
- What state are the working tree and current branch in?
- Which repository root directory is Git recognizing?

On Bash/Zsh, replace the first command with `env | grep '^GIT_'`.

## 11. Using `git -c` for a single invocation

When you need to test a setting without editing config files, use the `-c` option:

~~~bash
git -c core.pager=cat log --oneline -10
git -c pull.rebase=true pull
git -c advice.detachedHead=false switch --detach <commit>
~~~

The setting after `-c` applies only to that single Git invocation. It is useful for testing a hypothesis or running a specialized operation in CI.

If you need to supply a config value via an environment variable without writing sensitive values directly on the command line, Git supports the `--config-env` option on versions that include this feature. Check `git --version` and your version's documentation before using it in scripts.

Do not alter global config just for a one-time test. Changing global settings can affect all of the user's repositories and make bugs harder to reproduce in other environments.

## 12. Common diagnostic scenarios

### Terminal and IDE run two different Git builds

Symptom: `git --version` in the terminal reports a different version than the IDE reports, or one side has a helper while the other does not.

Check:

~~~powershell
Get-Command git -All
where.exe git
git --version
~~~

Then check the Git path in your IDE settings. Choose an appropriate Git installation and standardize it across your terminal, IDE, scripts, and CI if the project requires identical behavior.

### One repository uses a different `user.email` than another repository

Symptom: commits in project A use your corporate email, while project B uses your personal email.

Check:

~~~bash
git config --show-origin --get user.email
git config --show-origin --get user.name
~~~

Global config may supply the default identity while local config overrides it for one repository. This is valid behavior when configured intentionally.

### Git operates on a different repository

Symptom: running `git status` inside what appears to be project A displays the branch of project B.

Check:

~~~powershell
Get-ChildItem Env:GIT_DIR,Env:GIT_WORK_TREE
git rev-parse --show-toplevel
git rev-parse --git-dir
~~~

If `GIT_DIR` or `GIT_WORK_TREE` is set by a terminal, script, or IDE, it can redirect which repository Git uses. Unset the unwanted variable from the process and check again.

### Staging area appears out of sync

Symptom: `git status` or `git commit` does not reflect what you thought you staged.

Check:

~~~powershell
$env:GIT_INDEX_FILE
git rev-parse --git-path index
git status
~~~

`GIT_INDEX_FILE` may point to an alternate index. If the variable was set unintentionally, unset it and re-run status. Do not delete the alternate index file before confirming whether it contains changes you need to keep.

### CI cannot prompt for credentials

Symptom: `fetch`/`push` commands running in CI fail because they cannot open a prompt.

`GIT_TERMINAL_PROMPT=0` instructs Git not to prompt in the terminal. This may be an intentional CI setting to fail fast when credentials are missing. The right fix is configuring credentials/SSH tokens in a secret store and supplying them to the job securely—not enabling interactive prompts on an unattended runner.

## 13. Consistent setup workflow for a development machine

You can verify and configure in the following order:

### Step 1: confirm the executable

~~~powershell
Get-Command git -All
where.exe git
git --version
~~~

Choose the right Git installation and confirm a new terminal invokes the intended executable.

### Step 2: inspect environment variables

~~~powershell
Get-ChildItem Env:GIT*
~~~

Unset `GIT_DIR`, `GIT_WORK_TREE`, or `GIT_INDEX_FILE` if they are left over from an old script and no longer intended.

### Step 3: inspect current configuration

~~~bash
git config --list --show-origin --show-scope
~~~

Review the sources of `user.name`, `user.email`, `core.editor`, `core.autocrlf`, `pull.rebase`, and other key settings.

### Step 4: set identity at the right scope

If one identity applies to all repositories:

~~~bash
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"
~~~

If a project requires a different identity, set it locally inside that repository:

~~~bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@company.example"
~~~

### Step 5: re-verify

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
git status -sb
~~~

Confirm both the effective value and its source. If an IDE or CI uses a separate environment, repeat these checks inside that environment.

## 14. Safety principles when using environment variables and config

- Do not prepend untrusted directories to `PATH`. A malicious executable could be invoked before the real Git binary.
- Never place tokens, passwords, or private keys in a repository or committed configuration files.
- Do not set `GIT_DIR`, `GIT_WORK_TREE`, or `GIT_INDEX_FILE` at the user level without a clear need; they can cause Git commands to operate on the wrong data.
- Use `--global` for personal defaults and `--local` for project-specific rules.
- Use `-c` when a change is needed for only one command.
- Use `--show-origin` and `--show-scope` to determine the source before overriding a value.
- After making persistent changes to `PATH` or environment variables, open a new process to verify.
- In CI, scope variables to the job and use a secret store for sensitive information.

## 15. Common misconceptions

### Is `PATH` a setting inside `git config`?

No. `PATH` belongs to the shell/OS environment and determines which executable runs. Git config is only read after a Git program has already been launched.

### Does `git --exec-path` tell you where `git.exe` is located?

No. It shows the directory of Git's internal helpers. Use `Get-Command`, `where.exe`, or `type -a` to find the executable.

### Is `GIT_DIR` the same as `git config core.worktree`?

No. `GIT_DIR` is an environment variable that can override how Git locates the Git directory for a process. `core.worktree` is a configuration key intended for specifying the working tree. Do not use them interchangeably without understanding repository layout.

### Does `global` always beat `local` because it applies to every repository?

No. `local` has higher precedence than `global` for standard single-valued keys. A local setting can override a global value solely within that repository.

### Does setting an environment variable in PowerShell persist after closing the terminal?

Not if you only use `$env:NAME = value`. That sets it only for the current process and child processes. To persist across future login sessions, use Environment Variables or `SetEnvironmentVariable` at the `User`/`System` scope.

### Are all `GIT_*` variables part of Git config?

No. They are environment variables with distinct effects. Some control the location of the repository, index, object store, or helpers; others can supply configuration values. Look up each specific variable instead of applying `git config` scope rules to all of them.

## 16. Self-check

A Windows machine has two Git installations. In PowerShell, `git --version` reports `2.x`; the IDE reports `1.x`. In the current repository, `user.email` differs from the global value. A CI script runs `fetch` yet cannot open a prompt.

Answer the following:

1. Which command lists all Git locations that PowerShell can find?
2. Why might the IDE run a different Git build than the terminal?
3. Which command identifies the config file supplying `user.email`?
4. If local config overrides global, which scope has higher precedence?
5. Which variable can cause Git to use a different index?
6. Which variable can disable interactive prompts in CI?
7. Why should tokens never be stored in `PATH` or committed config files?

**Hint:** Use `Get-Command git -All` and `where.exe git` to find executables; the IDE may have a separate path configured. Use `git config --show-origin --get user.email` to find the source. Local has higher precedence than global. `GIT_INDEX_FILE` selects an alternate index; `GIT_TERMINAL_PROMPT=0` disables terminal prompts. Tokens should be stored in a secret store or credential manager, never in shareable content.

## Conclusion

When Git behaves differently across a terminal, IDE, and CI, inspect in order: the executable selected via `PATH`, the environment variables received by the process, and then `git config` values along with their scopes and origins. `PATH` determines which program runs; `GIT_*` variables can redirect the repository, index, object store, or helpers; and Git config merges settings across system, global, local, worktree, and command scopes. Use `Get-Command`/`where.exe`, `env`, `git config --show-origin`, and `--show-scope` to trace root causes before making edits. Configuring at the right scope keeps development environments consistent and prevents unintended side effects in other repositories.

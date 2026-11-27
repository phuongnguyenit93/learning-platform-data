# Inspecting Effective Configuration with `git config --list --show-origin`

Git reads configuration from multiple locations: system-wide configuration, user-level configuration, repository-specific configuration, per-worktree configuration, and options passed directly when running a command. Therefore, when `git commit`, `git pull`, or another operation behaves unexpectedly, opening just a single config file is often not enough to find the cause.

The `git config --list --show-origin` command lists Git configuration entries along with the source that provided each entry. Combined with `--show-scope`, you can see the configuration scope; combined with `--get` or `--get-all`, you can query a single key specifically. This is a practical way to discover why a particular value is being used and which file needs to be edited.

## 1. Running the command to view all configuration

Inside a repository directory, run:

```bash
git config --list --show-origin
```

The command displays the configuration entries Git reads, along with the origin of each entry. A shortened example:

```text
file:C:/Program Files/Git/etc/gitconfig    core.autocrlf=false
file:C:/Users/An/.gitconfig                user.name=An Nguyen
file:C:/Users/An/.gitconfig                init.defaultbranch=main
file:D:/work/app/.git/config               user.email=an@example.com
file:D:/work/app/.git/config               core.editor=code --wait
```

The paths and values in the example are illustrative only. On Linux or macOS, the system and user configuration paths will differ.

Each line helps answer two questions:

- Which configuration key is declared?
- Which file or source did that declaration come from?

This is especially helpful when the same key appears in multiple files. For example, `user.name` may be set globally while the current repository has a local value overriding it.

## 2. Viewing both configuration origin and scope

To clearly see the scope, add `--show-scope`:

```bash
git config --list --show-origin --show-scope
```

Example:

```text
system  file:C:/Program Files/Git/etc/gitconfig    core.autocrlf=false
global  file:C:/Users/An/.gitconfig                user.name=An Nguyen
global  file:C:/Users/An/.gitconfig                init.defaultbranch=main
local   file:D:/work/app/.git/config               user.email=an@example.com
local   file:D:/work/app/.git/config               core.editor=code --wait
command command line:                               core.pager=cat
```

`--show-origin` shows the specific source; `--show-scope` shows the logical scope Git assigns to the setting. The origin is usually `file:/path/to/file`, though some invocations can display sources such as `command line`, `standard input`, or `blob:<object-id>`.

Common scopes:

| Scope | Coverage | Typical config location |
|---|---|---|
| `system` | Applies to all users or repositories on the machine depending on how Git is installed. | System file, typically `etc/gitconfig` in the Git installation folder or `/etc/gitconfig`. |
| `global` | Applies to the current user across multiple repositories. | `~/.gitconfig` or `$XDG_CONFIG_HOME/git/config`. |
| `local` | Applies to a single repository. | `.git/config` or the corresponding Git directory. |
| `worktree` | Applies specifically to a single linked worktree when the repository enables worktree config. | `config.worktree` inside the worktree's Git directory. |
| `command` | Applies to the currently running command, with the highest precedence among standard configuration scopes. | `git -c key=value` or command-scope configuration environment variables. |

Not every repository has all scopes. For example, if per-worktree configuration has not been enabled, there will be no `config.worktree` file to read.

## 3. Precedence order of scopes

When the same single-valued key is declared in multiple scopes, configuration read later normally overrides configuration read earlier. The standard precedence order from lowest to highest is:

```text
system
   ↓
global
   ↓
local
   ↓
worktree
   ↓
command
```

For example, suppose:

```text
system: core.autocrlf=false
global: core.autocrlf=input
local:  core.autocrlf=true
```

In that repository, the local value `true` is the effective value for the single-valued key `core.autocrlf`, because it takes higher precedence than the system and global values.

However, do not assume every key holds only a single value. Some keys are **multi-valued** and allowed to repeat, such as `remote.origin.fetch`. For those keys, values can accumulate rather than the last value replacing all others. Exact behavior also depends on how Git defines that key.

Therefore, `--list` is a tool for inspecting all declarations, not always a single summary of the final value used. When you need to know the value of a specific key, query that key directly.

## 4. Querying a key and inspecting its source

### 4.1. Viewing a single value

For example, checking the author name:

```bash
git config --show-origin --show-scope --get user.name
```

The output shows the value and the source that provided it. You can inspect other keys similarly:

```bash
git config --show-origin --show-scope --get user.email
git config --show-origin --show-scope --get core.editor
git config --show-origin --show-scope --get init.defaultBranch
```

If the command returns no output and reports that the key was not found, that key may simply not be configured in any of the sources being read.

### 4.2. Viewing all values of a multi-valued key

For keys that can appear multiple times, use `--get-all`:

```bash
git config --show-origin --show-scope --get-all remote.origin.fetch
```

For example, a remote may have multiple fetch refspecs. If you look at only one line, you may miss another mapping that is still in effect.

### 4.3. Finding a group of keys

`--get-regexp` helps search for keys using a regular expression:

```bash
git config --show-origin --show-scope --get-regexp '^core\.'
git config --show-origin --show-scope --get-regexp '^remote\.origin\.'
git config --show-origin --show-scope --get-regexp '^branch\.'
```

These commands are useful when checking a group of settings related to line endings, remotes, or branch upstreams.

## 5. Common Git configuration files

### 5.1. System config

System config is typically set by an administrator or the Git installer. It can establish shared defaults for users on the machine.

The path depends on the operating system and how Git was installed. Some examples:

- Linux: `/etc/gitconfig`.
- Windows: the `etc/gitconfig` file inside the Git installation directory, such as `C:/Program Files/Git/etc/gitconfig`.
- macOS: may be `/etc/gitconfig` or a location used by the Git distribution.

View system config specifically:

```bash
git config --system --list --show-origin
```

Modifying system config typically requires administrative privileges. Do not modify this scope if your goal is only to adjust the behavior of a single repository.

### 5.2. Global config

Global config belongs to the current user. It is suited for personal settings shared across multiple repositories, such as name, email, editor, or aliases.

View:

```bash
git config --global --list --show-origin
```

On Windows, the file is typically located at `%USERPROFILE%\.gitconfig`; on Linux/macOS, typically `~/.gitconfig` or the XDG file `$XDG_CONFIG_HOME/git/config` (often defaulting to `~/.config/git/config`). The actual path should be confirmed using `--show-origin`.

### 5.3. Local config

Local config applies to the current repository. This is usually where remotes, branch tracking, certain project options, or repository-specific committer details are configured.

View:

```bash
git config --local --list --show-origin
```

The file is usually `.git/config`. With a linked worktree, `.git` may be a file pointing to the Git directory rather than a directory itself; therefore, use `--show-origin` to see the actual path instead of guessing its location.

### 5.4. Worktree config

A repository can have multiple linked worktrees. When the `extensions.worktreeConfig` extension is enabled, Git supports a separate config file for each worktree.

Check:

```bash
git config --local --get extensions.worktreeConfig
```

If enabled, you can inspect the configuration of the current worktree:

```bash
git config --worktree --list --show-origin
```

Worktree config is helpful when each worktree needs different settings. Only use `--worktree` when the repository is already configured to support it; otherwise, Git may return an error or lack the corresponding scope.

### 5.5. Command scope

You can pass configuration for a single execution only:

```bash
git -c core.pager=cat log --oneline
```

The `core.pager=cat` setting applies only to that `git log` command. It does not modify global or local files. When you run another command, the temporary configuration is no longer in effect.

You can inspect the command scope source with:

```bash
git -c core.pager=cat config --list --show-origin --show-scope
```

## 6. Include and includeIf: why does one config file pull in another?

Git config supports the `include` directive so one configuration file can load contents from another file. Example:

```ini
[include]
    path = ~/.gitconfig-work
```

When Git reads a file containing this directive, it also reads the included file. Thus, a key appearing in `git config --list --show-origin` may come from a file you did not expect.

Git also supports conditional includes. Example:

```ini
[includeIf "gitdir:D:/work/company/"]
    path = ~/.gitconfig-company

[includeIf "gitdir:D:/work/personal/"]
    path = ~/.gitconfig-personal
```

In this example, repositories under the work directory can load corporate configuration; personal repositories can load personal configuration. Other conditions can match on the checked-out branch or remote URL, depending on the Git version and supported syntax.

When includes are processed, `--show-origin` helps identify which included file a key comes from. If you need to view the list without expanding includes, you can use:

```bash
git config --list --show-origin --no-includes
```

This command is useful for distinguishing entries declared directly in the file being read from values loaded through includes.

## 7. Environment variables can also alter the configuration being read

In addition to configuration files, certain environment variables can change configuration sources or inject configuration values into the current run. Notable variables include:

| Variable | Effect |
|---|---|
| `GIT_CONFIG_SYSTEM` | Specifies an alternate system config file. |
| `GIT_CONFIG_GLOBAL` | Specifies an alternate global config file. |
| `GIT_CONFIG_NOSYSTEM` | Skips system config when enabled. |
| `GIT_CONFIG_COUNT` along with `GIT_CONFIG_KEY_n` and `GIT_CONFIG_VALUE_n` | Passes one or more key/value pairs into configuration for the Git process. |

PowerShell example, setting a temporary configuration for Git commands in the current session:

```powershell
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'core.pager'
$env:GIT_CONFIG_VALUE_0 = 'cat'

git config --list --show-origin --show-scope

Remove-Item Env:GIT_CONFIG_COUNT
Remove-Item Env:GIT_CONFIG_KEY_0
Remove-Item Env:GIT_CONFIG_VALUE_0
```

In practice, environment variables may be set by an IDE, script, or CI. If results differ from opening a standard terminal, inspect the environment of the process running Git.

Not every environment variable affecting Git is a config key. For example, certain `GIT_AUTHOR_*`, `GIT_COMMITTER_*`, or repository-control variables can affect behavior without appearing as an entry in `git config --list`. Therefore, listing config is not a complete inventory of the entire process environment.

## 8. Editing the right configuration source once you find the cause

Once you know where the incorrect value comes from, choose the right scope to fix it.

### 8.1. Editing global configuration

```bash
git config --global user.name "An Nguyen"
git config --global user.email "an@example.com"
```

These values apply to the user across repositories, unless a higher-precedence configuration overrides them.

### 8.2. Editing local configuration

```bash
git config --local user.name "An Nguyen"
git config --local user.email "an@company.example"
```

These values apply only to the current repository and can override global configuration. This is the common choice when a corporate repository requires a separate commit email.

### 8.3. Replacing, adding, or removing values

```bash
# Replace the value of a key
git config --local --replace-all core.editor "code --wait"

# Add a new value for a multi-valued key
git config --local --add remote.origin.fetch "+refs/heads/release/*:refs/remotes/origin/release/*"

# Remove all values of the key in the local scope
git config --local --unset-all remote.origin.fetch
```

Only use `--unset-all` when you truly want to remove all values for that key in that scope. For multi-valued keys, you may need to review and re-add required mappings after deleting them.

### 8.4. Which file should you edit?

If `--show-origin` indicates the wrong value lives in the global file, edit global. If it comes from `.git/config`, edit local. If the value comes from an included file, edit the corresponding include file or include condition. If the value comes from the command scope, inspect the script or command invoking Git rather than modifying persistent configuration files.

After editing, run again:

```bash
git config --list --show-origin --show-scope
git config --show-origin --show-scope --get core.editor
```

Compare both the value and the origin to ensure the configuration takes effect as intended.

## 9. Things to watch out for when reading results

### 9.1. `--list` shows every declaration, not just the final value

If `user.name` appears in both global and local, both may be listed. Do not see the global value and conclude that it is the one used in the repository. Inspect the scope and query the specific key.

### 9.2. Multi-valued keys can accumulate

Keys such as `remote.origin.fetch` can have multiple valid entries. Use `--get-all` to inspect them thoroughly. Deleting or replacing one value without understanding the remaining mappings can cause fetches to miss branches.

### 9.3. Includes distribute configuration across files

A global file may include separate files by directory or branch. When you see a value coming from an unfamiliar file, inspect `--show-origin` and check the include conditions before editing.

### 9.4. Output may contain sensitive information

`git config --list --show-origin` can print remote URLs containing tokens, HTTP extra headers, credential helpers, or other internal information. Never post the raw output to public issues, team chats, or CI logs. When asking others for help, filter to the relevant keys and redact tokens, passwords, and sensitive internal addresses.

### 9.5. Configuration is not everything Git uses

Behavior can also be influenced by environment variables, command-line options, the Git version, external system configuration, or the tool invoking Git. If you have verified the config key is correct yet behavior still differs, inspect the actual command and process environment.

## 10. Troubleshooting workflow for misconfiguration

Suppose commits are using the wrong email even though global config is set properly. Follow these steps in order:

**Step 1: Confirm the current repository**

```bash
git rev-parse --show-toplevel
```

**Step 2: View all declarations and origins**

```bash
git config --list --show-origin --show-scope
```

**Step 3: Query the exact key**

```bash
git config --show-origin --show-scope --get user.email
```

**Step 4: If it is a multi-valued key, inspect all values**

```bash
git config --show-origin --show-scope --get-all remote.origin.fetch
```

**Step 5: Check includes and environment if the source is still unclear**

```bash
git config --list --show-origin --no-includes
```

In PowerShell, you can inspect related configuration environment variables:

```powershell
Get-ChildItem Env:GIT_CONFIG*
```

**Step 6: Fix the right scope**

If the wrong email comes from local config, fix local instead of changing global:

```bash
git config --local user.email "an@company.example"
```

**Step 7: Re-verify**

```bash
git config --show-origin --show-scope --get user.email
```

If you need to inspect the author metadata of a commit already created, inspect that commit:

```bash
git log -1 --format=fuller
```

Changing configuration does not retroactively rewrite author information on existing commits. Changing metadata on past commits requires a separate history-rewriting operation.

## 11. Key takeaways

- `git config --list --show-origin` lists configuration entries along with the file or source providing them.
- Add `--show-scope` to see `system`, `global`, `local`, `worktree`, or `command`.
- The typical ascending precedence order is: system → global → local → worktree → command.
- `--list` displays every declaration; it is not always a summary of the final effective value.
- Use `--get` for a single key, `--get-all` for multi-valued keys, and `--get-regexp` to search a group of keys.
- `include` and `includeIf` can load configuration from other files; `--show-origin` helps find which file actually supplies the value.
- Environment variables and the `git -c` option can alter configuration for a single run.
- Edit the right scope and re-verify the origin afterward.
- Never share raw configuration output without checking for tokens, passwords, or internal details.

When a Git command behaves unexpectedly, start with `git config --list --show-origin --show-scope`, then query the specific key. Identifying the exact source before making changes prevents unnecessary global edits or unintentionally affecting other repositories.

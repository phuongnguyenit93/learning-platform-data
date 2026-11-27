# Configuration Scopes: system, global, local, worktree, and the -c Option

## Why does Git have multiple configuration scopes?

Git has many settings that affect how it works: the name and email recorded in commits, the editor, color output, pull behavior, line endings, credential helpers, hooks, and many other options. If all settings lived in a single file, it would be difficult to share common rules across every repository while still customizing settings per project or per working tree.

Git solves this problem with multiple **configuration scopes**. Each scope has a different area of application:

- **system:** applies to all users on the machine.
- **global:** applies to the current user, typically shared across that user's repositories.
- **local:** applies to a single repository.
- **worktree:** applies specifically to a single working tree when the repository has the worktree config mechanism enabled.
- **command:** applies to a single Git invocation via the `-c` option or the corresponding command configuration mechanism.

The typical precedence order from lowest to highest:

~~~text
system
   ↓
global
   ↓
local
   ↓
worktree
   ↓
command (-c)
~~~

When the same single-valued configuration key is set at multiple scopes, the value at the higher-precedence scope is normally used. For example, `user.email` in `local` can override the `global` value when committing in that repository. The `-c` option has higher precedence than configuration files and affects only that single invocation.

Not every key is single-valued. Some keys allow multiple values, such as multiple `remote.*.fetch` or `credential.helper` entries. For those keys, values may be accumulated or handled by the program invoking Git according to its own rules. Therefore, you should not assume that a higher-precedence value always erases all lower-precedence values.

## Seeing where Git reads configuration from

Before modifying configuration, inspect the current values and their sources:

~~~bash
git config --list --show-origin --show-scope
~~~

The output may look like:

~~~text
system  file:C:/Program Files/Git/etc/gitconfig  core.autocrlf=false
global  file:C:/Users/dev/.gitconfig             user.name=Developer
global  file:C:/Users/dev/.gitconfig             init.defaultbranch=main
local   file:.git/config                         user.email=work@example.invalid
command command line:                            color.ui=always
~~~

This is an illustrative example; actual paths, key names, and values depend on the machine and repository.

- `--show-origin` shows the file or source providing the value.
- `--show-scope` shows the configuration scope.
- `--list` lists the values Git is reading.

If your Git version does not support one of these options, you can use `--show-origin` or `--list` individually to inspect. Run the command from inside a repository when you want to see `local` and `worktree` configuration as well.

### Inspecting a specific key

To see the effective value of a key:

~~~bash
git config --get user.name
git config --get user.email
git config --get core.autocrlf
~~~

If the key is not set, `--get` may print nothing and return a non-zero exit code. That does not necessarily mean the repository is broken.

For multi-valued keys, use `--get-all`:

~~~bash
git config --get-all credential.helper
git config --get-all remote.origin.fetch
~~~

To filter keys by regular expression:

~~~bash
git config --get-regexp '^user\.'
~~~

This command is useful when checking the group of settings related to commit identity.

### Inspecting each scope individually

You can list each scope using the corresponding options:

~~~bash
git config --system --list
git config --global --list
git config --local --list
~~~

Inside a repository with worktree config enabled:

~~~bash
git config --worktree --list
~~~

The `--system` command may require appropriate read permissions depending on how Git is installed. You do not need to run every scope each time; choose the scope you need to investigate.

## The system scope: machine-wide shared configuration

System configuration applies to all users using the Git installation on the machine. The file location depends on the platform and installation method; on Windows it typically resides in the Git installation's config directory, while on Unix-like systems it typically resides in Git's system configuration location.

This scope is suited for rules managed by machine administrators or the development environment, for example:

- Shared proxy configuration.
- Certain security settings or default behaviors.
- A credential helper installed and managed by the organization at the machine level.
- Shared rules for build machines or shared development machines.

Reading system configuration:

~~~bash
git config --system --list --show-origin
~~~

Setting a system value requires write permission to the Git installation's configuration file:

~~~bash
git config --system core.autocrlf false
~~~

This example only illustrates syntax. Do not change system settings on a corporate or shared machine unless you have authorization and understand the impact on other users.

Removing a system key:

~~~bash
git config --system --unset core.autocrlf
~~~

If the key has multiple values, inspect them with `--get-all` and only use `--unset-all` when you truly want to remove every value for that key.

## The global scope: configuration for the current user

Global configuration is commonly used to set your commit identity and personal preferences across multiple repositories.

Some common settings:

~~~bash
# Identity recorded in commits
git config --global user.name "Developer Name"
git config --global user.email "dev@example.invalid"

# Default branch when initializing a new repository
git config --global init.defaultBranch main

# Default editor
git config --global core.editor "code --wait"
~~~

The address `example.invalid` is only a placeholder address; do not use it as a real email. Replace it with the name and email required by your organization or Git platform.

Checking global values:

~~~bash
git config --global --get user.name
git config --global --get user.email
git config --global --list --show-origin
~~~

Global configuration works well when you want the same identity or settings across most of your repositories. If you use multiple identities, such as personal repositories and corporate repositories, you can set separate values at the local or worktree scope to override global.

### Commit identity is not login credentials

`user.name` and `user.email` specify the author/committer information recorded in commit metadata. They do not grant push permissions, do not authenticate your GitHub/GitLab account, and do not replace SSH keys or credential managers.

If commits display the wrong name or email, inspect the effective configuration before creating your next commit. Changing configuration does not retroactively modify the metadata of commits already created.

You can require Git not to auto-guess an identity when none is configured:

~~~bash
git config --global user.useConfigOnly true
~~~

This setting makes Git require `user.name` and `user.email` to be explicitly configured instead of falling back to inferred values in certain cases. Only enable it if you have already configured appropriate identities for the repositories you will use.

### Removing or changing global configuration

Changing a value:

~~~bash
git config --global user.email "new-address@example.invalid"
~~~

Removing a single-valued key:

~~~bash
git config --global --unset user.email
~~~

Opening the global file in an editor:

~~~bash
git config --global --edit
~~~

After editing, verify again:

~~~bash
git config --global --get user.email
git config --show-origin --get user.email
~~~

The `--unset` option is appropriate for single-valued keys. For multi-valued keys, inspect all entries before deleting; `--unset-all` removes every matching value for that key.

## The local scope: repository-specific configuration

Local configuration is stored in the repository's config, typically the `.git/config` file. It applies to that repository and can override global settings.

Local scope is appropriate when a project has specific requirements, such as:

- A work email different from your personal email.
- Team pull or merge rules.
- Repository-specific remotes and URLs.
- Project-specific diff, merge tool, or hook path settings.

Example of setting a specific identity for the current repository:

~~~bash
git config --local user.name "Work Developer"
git config --local user.email "work@example.invalid"
~~~

Setting a project-specific pull rule:

~~~bash
git config --local pull.rebase true
~~~

The example above tells `git pull` to prefer rebasing per configuration; only set it when it matches your team's collaboration conventions.

Verification:

~~~bash
git config --local --list --show-origin
git config --get user.name
git config --show-origin --get user.email
~~~

The final `git config --get` commands read the effective value across scopes, whereas `--local --list` lists only local configuration.

### Do local settings affect other team members?

The `.git/config` file is not committed as an ordinary tracked file in the repository. Therefore, local settings normally apply only to your local clone. Other team members do not automatically receive those values when they pull or clone.

If you want to share project rules, consider documentation, `.gitattributes`, build configuration, or mechanisms supported by the repository. Never place personal credentials into shared configuration.

Opening the local file:

~~~bash
git config --local --edit
~~~

Removing a local value:

~~~bash
git config --local --unset pull.rebase
~~~

After removing a local value, a global or system value may become the effective value. Therefore, re-check with `git config --show-origin --get <key>` rather than assuming the key now has no value at all.

## The worktree scope: per-working-tree configuration

A repository can have multiple working trees managed with `git worktree`. The working trees share history and the object database, but may need certain settings tailored to each working directory.

By default, local configuration in `.git/config` is shared across all worktrees of the same repository. To store separate configuration per worktree, Git supports worktree config via the `extensions.worktreeConfig` extension.

Checking the extension:

~~~bash
git config --local --get extensions.worktreeConfig
~~~

When the extension is enabled, Git can read and write worktree configuration using the `--worktree` option. For example, setting a separate email for the current working tree:

~~~bash
git config --worktree user.email "feature-team@example.invalid"
~~~

Verification:

~~~bash
git config --worktree --list --show-origin
git config --show-origin --get user.email
~~~

Calling `--get` without specifying a scope returns the effective value; `--show-origin` helps identify which file that value comes from.

### Enabling worktree config

In a repository you manage, you can enable the extension with:

~~~bash
git config --local extensions.worktreeConfig true
~~~

Once enabled, Git uses a separate config file per worktree alongside the shared config. Before enabling it on a repository that already has multiple worktrees, read the Git documentation matching your version and inspect settings that only make sense per working tree. Certain configurations related to paths and checkout state must be placed in the right location so worktrees do not interfere with each other.

Do not arbitrarily enable the extension on a shared repository without checking how the team manages worktrees. Enabling the extension changes how Git reads configuration for that repository.

### When should you use the worktree scope?

For example, suppose you have two working trees:

- `../app-main` for fixing bugs on the `main` branch.
- `../app-feature` for feature development.

If each working tree requires a different commit email, you can configure separate identities using the worktree scope once the extension is enabled. Configuration in one working tree does not overwrite the configuration of the other working tree.

This configuration scope is helpful when working on multiple parallel tasks within the same repository. If you do not use multiple worktrees or do not need per-worktree settings, global and local are usually sufficient.

## The command scope: temporary overrides with the -c option

The `-c` option passes configuration for a single Git invocation. Syntax:

~~~bash
git -c <key>=<value> <command>
~~~

For example, forcing `status` to always display color:

~~~bash
git -c color.ui=always status
~~~

Or using a different identity for a single commit:

~~~bash
git -c user.name="Release Bot" -c user.email="release-bot@example.invalid" commit -m "Prepare release"
~~~

Values passed via `-c` take higher precedence than system, global, local, and worktree configuration files for that invocation. Once the command finishes, the values are not persisted to permanent configuration files.

You can use `-c` to test a setting before deciding whether to save it to global or local:

~~~bash
git -c pull.rebase=true pull
~~~

The command above runs `pull` with `pull.rebase=true` for that single run. It does not change `pull.rebase` in `.gitconfig` or `.git/config`.

### Passing multiple -c arguments

You can pass multiple key/value pairs in the same command:

~~~bash
git -c color.ui=always -c core.pager=cat log --oneline
~~~

If a value contains spaces, wrap it in quotes according to the rules of your shell. For example, PowerShell, Bash, and CMD have differences in how they handle quoting; verify the command is passed as intended.

`-c` is useful for scripts, automation, testing, and one-off operations. Do not use it as a substitute for global/local configuration if a setting needs to apply consistently across many commands.

## How to determine the effective value and find why configuration is overridden

When a Git command behaves differently from expectations, do not rush to edit configuration files. First, identify which key is effective and where its value originates.

For example, when `user.email` is wrong:

~~~bash
git config --show-origin --show-scope --get-all user.email
git config --get user.email
~~~

If there are multiple values, inspect the entire list and check whether the key is multi-valued. For single-valued keys, the value in the higher-precedence scope normally wins. For multi-valued keys, Git or the program reading the key may process multiple values according to its own rules.

For example, `core.autocrlf` is set in global, but local overrides it:

~~~bash
git config --global core.autocrlf false
git config --local core.autocrlf true
~~~

When running inside that repository, local normally takes precedence over global. Determine the actual source:

~~~bash
git config --show-origin --show-scope --get-all core.autocrlf
git config --get core.autocrlf
~~~

If you remove the local value:

~~~bash
git config --local --unset core.autocrlf
~~~

The global value will become the effective value if no higher scope overrides it. That is why after unsetting a configuration at one scope, you must re-verify the entire precedence chain.

### Checking included configuration files

Git allows one configuration file to load another via `include.path`. You can use `includeIf` to load a file only when conditions on the repository path or branch match.

Example:

~~~ini
[includeIf "gitdir:~/work/"]
    path = ~/.gitconfig-work
~~~

When a repository resides under a matching directory, Git can load additional settings from the specified file. This is useful when you have multiple groups of repositories and want to use different identities or rules.

Inspect the actual source using:

~~~bash
git config --list --show-origin --show-scope
~~~

If a value originates from an included file, inspect both the parent file containing the include directive and the included file. Do not mistakenly edit the main global file when the actual value comes from a conditional file.

## Multi-valued configuration keys

Not every key holds only a single value. Some keys are allowed to appear multiple times. For example, a remote can have multiple fetch refspecs:

~~~bash
git config --get-all remote.origin.fetch
~~~

`--add` appends a value without replacing existing values:

~~~bash
git config --local --add remote.origin.fetch "+refs/heads/release/*:refs/remotes/origin/release/*"
~~~

`--replace-all` replaces matching values with a new value:

~~~bash
git config --local --replace-all remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
~~~

`--unset-all` removes every value for the key:

~~~bash
git config --local --unset-all remote.origin.fetch
~~~

The examples above directly affect how remotes are fetched. Only use them when you clearly understand existing refspecs and your configuration goal. For multi-valued keys, inspect `--get-all` before modifying to avoid accidentally deleting part of a required setup.

## Checking data types and value syntax

Git supports reading configuration with explicit data types to avoid misinterpreting values.

Example of reading a boolean:

~~~bash
git config --type=bool --get pull.rebase
~~~

Reading an integer:

~~~bash
git config --type=int --get gc.auto
~~~

Reading a path value:

~~~bash
git config --type=path --get core.excludesfile
~~~

Boolean values typically accept forms such as `true`, `false`, `yes`, `no`, `on`, `off`, `1`, and `0` according to Git's rules. Use `--type=bool` so Git converts the value and reports an error if it is invalid.

Not every key has a simple type. Consult the documentation for the specific key if the value is a path, duration, URL, or special structure.

## Editing configuration files directly

You can use `--edit` to open the configuration file at the desired scope:

~~~bash
git config --system --edit
git config --global --edit
git config --local --edit
~~~

Worktree config can be edited when the extension is enabled:

~~~bash
git config --worktree --edit
~~~

Git configuration uses an INI-style syntax. Example:

~~~ini
[user]
    name = Developer Name
    email = dev@example.invalid

[init]
    defaultBranch = main

[pull]
    rebase = true
~~~

After editing the file directly, verify syntax and values again:

~~~bash
git config --list --show-origin --show-scope
git config --get user.name
git config --type=bool --get pull.rebase
~~~

Prefer using `git config` to add, replace, or remove ordinary keys. Editing the file directly is helpful when you need to inspect section structure, add comments, or adjust many keys at once. Avoid modifying a configuration file concurrently from multiple Git processes.

## Protecting sensitive information in configuration

Some settings may contain or reference sensitive information, for example:

- Remote URLs with embedded usernames or tokens.
- HTTP extra headers used for authentication.
- Paths to credential files or private keys.
- Credential helper arguments.
- Internal paths or corporate server details.

Do not pass tokens, passwords, or private keys directly in `git config` commands if they could be recorded in shell history, logs, or inappropriate configuration files. Prefer credential managers or secret distribution mechanisms supported by your organization.

When sharing `git config --list` output, inspect and redact sensitive details first. Use `--show-origin` to identify the configuration source, without exposing authentication secrets.

## Practical workflow: setting identity per repository

Suppose you use your personal email for private repositories, but need your corporate email for work repositories.

First, set your default global identity:

~~~bash
git config --global user.name "Developer Name"
git config --global user.email "personal@example.invalid"
~~~

Enter the work repository and set the local identity:

~~~bash
cd path/to/company-project
git config --local user.name "Work Developer"
git config --local user.email "work@example.invalid"
~~~

Check the sources and effective values:

~~~bash
git config --show-origin --show-scope --get-all user.name
git config --show-origin --show-scope --get-all user.email
git config --get user.name
git config --get user.email
~~~

Create a test commit on a work branch if appropriate for your workflow, then inspect the metadata:

~~~bash
git log -1 --format=fuller
~~~

The `Author` and `Commit` fields will show the name/email recorded in the commit. Subsequent configuration changes affect only new commits and do not retroactively alter older commits.

## Practical workflow: testing temporary configuration with -c

Suppose you want to test whether pulling with rebase suits a repository before saving the setting permanently.

Inspect the current configuration:

~~~bash
git config --show-origin --show-scope --get-all pull.rebase
~~~

Test it once:

~~~bash
git -c pull.rebase=true pull
~~~

If the result fits your team's workflow, consider saving it locally:

~~~bash
git config --local pull.rebase true
~~~

Re-verify:

~~~bash
git config --show-origin --get pull.rebase
~~~

If you do not want to keep the setting, simply do not write it to a configuration file. If you already saved it locally and want to remove it:

~~~bash
git config --local --unset pull.rebase
~~~

After removing it, check whether global or system holds another value that will become the effective value.

## Common errors

| Situation | Possible cause | How to resolve |
|---|---|---|
| Global is set, yet Git still uses another value | Local, worktree, or command has higher precedence | Use `--show-origin --show-scope --get-all` to find the source |
| `git config --local` reports not inside a repository | Running outside a repository or in the wrong directory | Change into the repository you want to configure |
| `git config --worktree` does not work | `extensions.worktreeConfig` is not enabled or unsupported context | Check the extension and repository state |
| Key removed, yet Git still returns a value | Key still exists in another scope or an included file | Inspect all sources and scopes |
| `git config --get` prints only one value | Key has multiple values | Use `--get-all` |
| Changed `user.name`, yet old commits still show the old name | Commit metadata was recorded earlier | Check new commits; fixing old commits requires an appropriate history-rewriting operation |
| `-c` is not retained for subsequent commands | `-c` applies only to the current invocation | Use `git config --global`, `--local`, or `--worktree` if persistence is needed |
| Config command returns permission error | Insufficient permissions to write system file or protected file | Use an appropriate scope or ask an administrator |
| Invalid boolean value | Incorrect syntax or configuration value | Verify with `git config --type=bool --get <key>` |

## Safe configuration management habits

- Put personal settings you want shared across repositories in `global`.
- Put rules specific to a single repository in `local`.
- Only use `worktree` scope once you have enabled and understood the worktree config mechanism.
- Use `-c` to test or override settings for a single command.
- Use `--show-origin` and `--show-scope` before modifying a hard-to-trace value.
- Use `--get-all` for keys that can hold multiple values.
- Verify effective values after adding, modifying, or removing settings.
- Never store secrets in configuration files or unsafe logs.
- Document project rules in shared documentation or managed configurations when team members need identical settings.

## Key takeaways

Git reads configuration from multiple scopes: `system` for the machine, `global` for the user, `local` for a repository, `worktree` for an individual working tree when the extension is enabled, and `command` for a single invocation via `-c`. Higher-precedence scopes normally override single-valued keys from lower scopes, though multi-valued keys can accumulate. Use `git config --list --show-origin --show-scope` to locate sources, `--get` or `--get-all` to read, `--global`/`--local`/`--worktree` to write at the proper scope, and `-c` to test temporary configuration. Always verify effective values after changes and protect credentials from shared config files or logs.

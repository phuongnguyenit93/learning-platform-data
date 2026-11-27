# Directory-Based Configuration Using include and includeIf

A single machine may work with many repositories belonging to different organizations or purposes. You might need to use a corporate commit identity inside repositories under a work folder, a personal identity inside private repositories, or a set of settings dedicated to one project. Git supports splitting configuration into multiple files and loading them automatically with `include` or `includeIf`. That way, you can organize configuration by repository location, checked-out branch, or remote URL without editing `user.name`, `user.email`, and other options every time you switch projects.

## 1. Git reads configuration from multiple scopes

Git can read configuration from multiple files and sources. The common scopes, from lowest to highest precedence, are:

| Configuration scope | Coverage | Example location or way to set |
|---|---|---|
| System | All users on the machine | The `gitconfig` file in the Git installation directory |
| Global | Current user, across multiple repositories | `~/.gitconfig` or `$XDG_CONFIG_HOME/git/config` |
| Local | One repository and its associated worktrees by default | `$GIT_DIR/config` or common config |
| Worktree | A specific worktree when `extensions.worktreeConfig` is enabled | The `config.worktree` file |
| Command | One specific command invocation | `git -c key=value ...` or supported config environment variables |

A value in a higher-precedence scope normally overrides a value with the same key in a lower scope. For a single-valued key like `user.email`, Git normally uses the last effective value. Some keys allow multiple values, such as `insteadOf` URL rules, so inspect all values rather than assuming there is only one.

Inspect configuration along with its source and scope:

```bash
git config --list --show-origin --show-scope
```

The output tells you which file a value comes from and which scope it belongs to. Whenever you suspect configuration is being overridden, this is the command to run before editing files.

## 2. Splitting configuration into files with `include`

`include.path` instructs Git to read an additional configuration file at the point of declaration. Entries in the included file are treated as if they appeared directly at the position of the include line in the parent file.

For example, in `~/.gitconfig`:

```ini
[include]
    path = ~/.gitconfig-common
```

The `~/.gitconfig-common` file can contain shared settings:

```ini
[init]
    defaultBranch = main
[pull]
    ff = only
[core]
    editor = code --wait
```

When Git reads global config, the contents of `.gitconfig-common` are also loaded at the global scope. You can put related settings into separate files—for instance, one file for editor settings, one for signing, or one for aliases.

### 2.1. Path of the included file

The `path` value can be an absolute or relative path:

- A path starting with `~/` is expanded relative to the user's home directory.
- A relative path is resolved relative to the directory containing the configuration file declaring the include.
- Paths containing spaces must be written as a valid config value; in an INI file, shell quotes are not needed, but ensure the entire path remains on a single value.

For example, a configuration file located in the home directory can use:

```ini
[include]
    path = config/git/aliases.ini
```

Git will look for the file relative to the directory containing that configuration file. Therefore, when moving a parent config file to another location, re-check relative paths.

On Windows, Git accepts forward slashes in configuration paths, for example:

```ini
[include]
    path = C:/Users/Alice/.gitconfig-common
```

If a folder name contains spaces, place the entire path after `path =` as a single value, such as `C:/Users/Alice/Work Settings/git.ini`.

### 2.2. Nested includes

An included file can include another file. This lets you organize configuration hierarchically:

```ini
# ~/.gitconfig
[include]
    path = ~/.config/git/base.ini
```

```ini
# ~/.config/git/base.ini
[include]
    path = aliases.ini
[core]
    autocrlf = input
```

Nested include files are read at the position where they are declared. Avoid creating cycles—for example, file A includes B while B also includes A. Circular structures make configuration confusing, and Git can stop reading when it detects recursive includes or exceeds depth limits.

## 3. Using `includeIf` to load configuration conditionally

`includeIf` loads a file only when the specified condition is satisfied. General syntax:

```ini
[includeIf "<condition>:<pattern>"]
    path = <config-file>
```

Git supports several condition types, the most common being `gitdir`, `onbranch`, and `hasconfig:remote.*.url`. Exact capabilities depend on the Git version; if a command does not recognize a condition, check your installed Git version and its matching documentation.

## 4. Choosing configuration by repository directory with `gitdir`

The `gitdir` condition checks the path to the Git directory (`$GIT_DIR`) of the current repository. This is a popular way to apply a specific identity or settings for repositories residing under a given directory.

Example in `~/.gitconfig`:

```ini
[includeIf "gitdir:~/src/work/"]
    path = ~/.gitconfig-work

[includeIf "gitdir:~/src/personal/"]
    path = ~/.gitconfig-personal
```

File `~/.gitconfig-work`:

```ini
[user]
    name = Work Contributor
    email = work@example.invalid
[commit]
    gpgsign = true
```

File `~/.gitconfig-personal`:

```ini
[user]
    name = Personal Contributor
    email = personal@example.invalid
```

When Git operates in a repository whose Git directory lies under `~/src/work/`, the work file is included. Repositories under `~/src/personal/` receive the personal configuration.

### 4.1. `gitdir` patterns

The pattern is matched against the path of the Git directory, not directly against the path of the file being edited. Some notable rules:

- Patterns starting with `~/` expand to the home directory.
- Patterns starting with `./` are resolved relative to the configuration file containing the condition.
- `*` matches within a single path segment; `**/` can match across multiple directory levels.
- Patterns ending with `/` are expanded by Git to match subdirectories underneath.
- `gitdir` is case-sensitive on systems where matching is case-sensitive; use `gitdir/i` for case-insensitive matching.

Example configuration for a work folder on Windows:

```ini
[includeIf "gitdir/i:C:/Users/Alice/Source/Work/"]
    path = C:/Users/Alice/.gitconfig-work
```

`gitdir/i` makes the pattern behave more reliably when letter casing in paths varies. Use `/` in patterns to avoid confusion with config file escape characters.

### 4.2. Note when using linked worktrees

With a linked worktree, the `.git` entry in the working directory is a file pointing to the worktree's separate metadata. The `$GIT_DIR` value normally resides under the repository's shared administrative directory, such as `.git/worktrees/<id>`, rather than under the worktree directory path you see.

Consequently, a condition like `gitdir:~/src/work/` may fail to match a linked worktree even though its working directory is under `~/src/work/`; Git is matching against the Git directory path. If you need configuration based on the checked-out branch, see the `onbranch` condition. If you need to distinguish linked worktrees by physical location, verify the actual values with:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
```

Do not assume a worktree directory and its Git directory always share the same parent path.

## 5. Choosing configuration by branch with `onbranch`

The `onbranch` condition checks the name of the currently checked-out branch. It is useful when you want to enable certain settings across a group of branches regardless of which directory the repository sits in.

Example:

```ini
[includeIf "onbranch:release/"]
    path = ~/.gitconfig-release

[includeIf "onbranch:feature/experiment"]
    path = ~/.gitconfig-experiment
```

On the `release/2.0` branch, `~/.gitconfig-release` is included. On `feature/experiment`, the second config file is included.

A pattern ending with `/` matches branches with that prefix. `onbranch` depends on the current branch; when in a detached HEAD state, branch-based conditions do not match as they do when a named branch is checked out.

Some settings make sense per branch, such as enabling commit signing for release branches or defining a release-specific alias/setting. However, `user.name` and `user.email` should generally be tied to an identity or repository rather than changing arbitrarily just because you switched branches.

## 6. Choosing configuration by remote URL with `hasconfig`

Git supports the `hasconfig:remote.*.url:<pattern>` condition to include a file if a remote URL in the current configuration matches a pattern. This is helpful when repositories are cloned in different locations yet belong to the same server or organization.

Example:

```ini
[includeIf "hasconfig:remote.*.url:https://github.com/acme/**"]
    path = ~/.gitconfig-acme
```

When a remote URL matches `https://github.com/acme/**`, Git loads `~/.gitconfig-acme`. URL patterns support glob syntax; inspect actual URLs with `git remote -v` before writing conditions.

This condition has a special restriction to prevent cycles when Git must read URLs in order to evaluate includes: a file included by `hasconfig:remote.*.url` must not define additional remote URLs. Keep `[remote "..."]` declarations in regular configuration and place only the conditional settings inside the included file.

`hasconfig` is available in newer Git versions. If you are using an older Git version, use `gitdir` or explicit global/local configuration instead.

## 7. Combining multiple conditions

You can declare multiple `includeIf` entries in the same file. Each condition is evaluated independently; multiple matching files can all be loaded if multiple conditions are satisfied.

Example:

```ini
[includeIf "gitdir:~/src/work/"]
    path = ~/.gitconfig-work

[includeIf "onbranch:release/"]
    path = ~/.gitconfig-release
```

When working in a repository under `~/src/work/` with the `release/2.0` branch checked out, both files can be included. If both files set `user.email`, the effective value depends on read order and configuration scope; run `git config --show-origin --show-scope --get-all user.email` to see where each value comes from.

Avoid creating too many overlapping conditions for the same key. If a value changes unexpectedly, narrow the pattern or consolidate settings into a single file with clear responsibility.

## 8. Includes do not create a new configuration scope

An important point: an included file does not have its own precedence level. It is read as part of the configuration file that included it.

For example, `~/.gitconfig` at the global scope includes `~/.gitconfig-work`. Values inside the work file are also treated as global values. They do not become local simply because the included file has a distinct name or lives in another folder.

Similarly, if a repository's `.git/config` includes another file, values in that file are read at the local scope. If worktree config is enabled and `config.worktree` includes a file, its values are read in the worktree context.

Include order also matters. The included file's contents appear at the exact point of declaration during parsing. If the same single-valued key is set multiple times at the same scope, the value read later normally takes effect. A higher configuration scope can still override values from a lower scope.

## 9. Structuring directory-based identity configuration in practice

A simple organization keeps the global config as a coordinator and splits identities into two files:

`~/.gitconfig`:

```ini
[user]
    name = Default Contributor
    email = default@example.invalid

[includeIf "gitdir:~/src/company/"]
    path = ~/.gitconfig-company

[includeIf "gitdir:~/src/oss/"]
    path = ~/.gitconfig-oss
```

`~/.gitconfig-company`:

```ini
[user]
    name = Company Contributor
    email = company@example.invalid
```

`~/.gitconfig-oss`:

```ini
[user]
    name = Open Source Contributor
    email = oss@example.invalid
```

With this layout, repositories in `~/src/company/` use the corporate identity; repositories in `~/src/oss/` use the open-source contributor identity; repositories elsewhere use the default identity.

After creating the files, verify that the actual Git directory path of each repository matches the pattern. A repository might be cloned elsewhere, use a linked worktree, or have a `.git` file pointing to a different administrative directory. Do not rely solely on the path shown in File Explorer while overlooking `$GIT_DIR`.

## 10. Verifying config files and value sources

The following commands help diagnose configuration after adding includes:

```bash
git config --list --show-origin --show-scope
git config --show-origin --show-scope --get user.name
git config --show-origin --show-scope --get user.email
git config --show-origin --show-scope --get-all user.email
```

- `--list` shows effective configuration entries.
- `--show-origin` shows the file or source supplying each value.
- `--show-scope` shows the configuration scope such as system, global, local, worktree, or command.
- `--get-all` lists every value of keys that can appear multiple times.

If an included file is not being loaded, check:

1. Whether the parent configuration file has valid INI syntax and correct section names.
2. Whether the path after `path` exists and is resolved relative to the right location.
3. Whether the `gitdir`, `onbranch`, or URL condition matches the actual state.
4. Whether your Git version supports the condition type being used.
5. Whether a higher-precedence configuration file is overriding the newly included value.

To inspect your current location and branch:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git branch --show-current
git remote -v
```

Compare the output against your condition patterns. `git branch --show-current` returns empty when HEAD is detached; in that state, `onbranch` conditions do not trigger as they do when a regular branch is checked out.

## 11. Editing configuration at the right scope

You can open the global config with:

```bash
git config --global --edit
```

Open the local configuration of the current repository:

```bash
git config --local --edit
```

Set a value via command instead of editing files directly:

```bash
git config --global user.name "Default Contributor"
git config --global user.email "default@example.invalid"
```

If you want to add an include to global config:

```bash
git config --global include.path ~/.gitconfig-common
```

With multiple includes in the same section, use `--add` to append instead of replacing the existing value:

```bash
git config --global --add include.path ~/.gitconfig-aliases
```

`includeIf` conditions are usually easier to read and review when declared directly in the INI file. If using `git config` to set keys containing dots in section names, ensure section and key syntax are passed properly; verify afterward with `git config --list --show-origin`.

## 12. Common pitfalls and how to avoid them

- **Using `gitdir` expecting it to match the working tree path.** This condition matches `$GIT_DIR`; for linked worktrees, that path usually resides under the shared administrative directory.
- **Forgetting a trailing `/` on directory patterns.** Patterns ending with `/` have convenient recursive matching behavior; omitting it may prevent matching nested subdirectories as intended.
- **Using a relative include path from the wrong base directory.** Relative paths are resolved from the configuration file containing the directive.
- **Assuming an included file gets its own precedence scope.** It inherits the scope of the parent file; values can still be overridden by higher scopes.
- **Creating multiple includes modifying the same key without checking order.** Use `--show-origin`, `--show-scope`, and `--get-all` to trace sources.
- **Using `onbranch` during detached HEAD.** There is no current branch name for the condition to match.
- **Defining remote URLs inside a file included by `hasconfig`.** This rule can cause errors or cycles; remote URLs should be declared in regular configuration.
- **Using newer features on older Git versions.** Check `git --version` and version-specific docs before relying on `onbranch` or `hasconfig`.
- **Putting secrets in shared configuration files.** Never store tokens, passwords, or private keys in global/local files that are committed or shared more broadly than necessary.

## 13. Setup and verification workflow

When you need separate configuration per repository directory:

1. Identify the folder containing the repositories and obtain the actual `$GIT_DIR` with `git rev-parse --git-dir`.
2. Choose the keys to isolate, typically `user.name`, `user.email`, signing settings, or personal aliases/preferences.
3. Create the separate configuration file with the required sections.
4. Add `includeIf "gitdir:<pattern>"` to global config and point `path` to the separate file.
5. Open a repository within the scope to verify `git config --list --show-origin --show-scope`.
6. Check repositories outside the scope to ensure the default configuration still applies.
7. If using linked worktrees, inspect `$GIT_DIR` for each worktree before concluding the pattern is right.
8. Document the convention in team documentation if it affects how commits or releases are created.

Example verifying the active identity:

```bash
git config --show-origin --show-scope --get user.name
git config --show-origin --show-scope --get user.email
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

The two `git var` commands show the author and committer identities Git will use in the current repository. They are useful for confirming that your include configuration produces the right identity before committing.

## 14. Key takeaways

`include` splits configuration into manageable files; `includeIf` loads a file only when the repository, branch, or remote matches a condition. For directory-based configuration, `gitdir` matches the Git directory path, so verify the actual `$GIT_DIR`, especially in linked worktrees. Included files inherit the parent file's configuration scope and remain subject to the precedence order of system, global, local, worktree, and command. Use `git config --show-origin --show-scope` to determine exactly where a value comes from before making edits.

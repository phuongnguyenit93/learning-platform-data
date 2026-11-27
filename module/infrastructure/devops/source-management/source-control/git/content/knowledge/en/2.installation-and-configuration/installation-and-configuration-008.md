# Creating Aliases for Common Operations

When working with Git every day, you frequently repeat commands like `git status`, `git log`, `git switch`, `git diff`, or `git restore`. Git aliases let you assign short names to these commands to reduce typing, making familiar workflows easier to remember and more consistent.

For example, instead of typing `git status --short --branch`, you can create an alias `st` and then run `git st`. An alias can be a simple Git command, a Git command with fixed arguments, or a shell command when more complex processing is needed.

An alias is merely a shorthand. Users still need to understand the underlying real command, especially for aliases that can alter history or delete data.

## 1. How do Git aliases work?

Git reads entries in the `alias` section of configuration files to expand shorthand commands. Example:

~~~sh
git config --global alias.st "status --short --branch"
~~~

After creating it, you can run:

~~~sh
git st
~~~

Git interprets this command as equivalent to:

~~~sh
git status --short --branch
~~~

The alias name appears after the word `git`. Thus, `git st` is a Git alias; it differs from a shell alias like `gs`, which is expanded by the shell before invoking Git.

Aliases are commonly used to:

- Shorten long commands that are used frequently.
- Standardize how status and history are viewed.
- Give memorable names to option combinations.
- Create helper commands for team-specific workflows.
- Wrap a small shell command when a single Git command is not enough.

Git aliases do not change how Git stores commits, branches, or remotes. They simply make invoking commands more convenient.

## 2. Creating aliases across configuration scopes

Git supports multiple configuration scopes. Choose the appropriate scope so the alias is available wherever it is needed.

### 2.1. Global aliases for the user

`--global` saves configuration at the user level. The alias generally applies across repositories that the user works in:

~~~sh
git config --global alias.st "status --short --branch"
~~~

The global config file is typically `~/.gitconfig` or a file specified via environment variables and XDG configuration. You do not need to edit the file manually; `git config --global` lets Git write the correct format.

### 2.2. Repository-specific aliases

`--local` saves the alias in the current repository's configuration, typically `.git/config`:

~~~sh
git config --local alias.st "status --short --branch"
~~~

A local alias applies only to that repository on the current machine. The `.git/config` file is not committed and is not automatically shared with teammates when they clone.

### 2.3. One-off aliases

If you only want to try an alias for a single command, use `-c`:

~~~sh
git -c alias.st="status --short --branch" st
~~~

This configuration exists only for that single Git invocation. It is useful for testing an alias before deciding to save it globally or locally.

### 2.4. Which scope should you choose?

| Scope | How to declare | When to use |
|---|---|---|
| System | `git config --system ...` | Administrator configuring shared machine-wide settings |
| Global | `git config --global ...` | Personal aliases used across multiple repositories |
| Local | `git config --local ...` | Aliases serving only one repository on the current machine |
| Worktree | `git config --worktree ...` | Per-worktree config when the repository has worktree config support enabled |
| Command | `git -c alias.name=... name` | Experimentation or one-time use |

For personal aliases, `--global` is usually the convenient choice. If a team wants every member to share certain commands, document them or provide a reviewed setup script; do not assume local aliases travel with the repository when cloned.

## 3. Creating commonly used basic aliases

### 3.1. Viewing concise status

~~~sh
git config --global alias.st "status --short --branch"
~~~

Usage:

~~~sh
git st
~~~

This command displays working tree status in short format along with the current branch. It is a useful alias for quick checks before committing, switching branches, or syncing.

### 3.2. Switching branches and creating a new branch

~~~sh
git config --global alias.co switch
git config --global alias.cob "switch -c"
~~~

Usage:

~~~sh
git co main
git cob feature/order-search
~~~

`git co main` is equivalent to `git switch main`; `git cob feature/order-search` is equivalent to `git switch -c feature/order-search`.

If a project still has to support older Git versions without `git switch`, consider aliases based on `checkout` or agree on a minimum Git version for the team.

### 3.3. Viewing history as a graph

~~~sh
git config --global alias.lg "log --oneline --graph --decorate --all"
~~~

Usage:

~~~sh
git lg
git lg --max-count=20
~~~

This alias displays commits across branches and tags in graph form, making it easy to inspect branching and merge history at a glance.

### 3.4. Viewing the latest commit

~~~sh
git config --global alias.last "log -1 --stat"
~~~

Usage:

~~~sh
git last
~~~

The output shows the most recent commit along with file change statistics. If you need to view the full commit diff and content, use `git show`.

### 3.5. Viewing staged changes

~~~sh
git config --global alias.dfs "diff --staged"
~~~

Usage:

~~~sh
git dfs
~~~

This alias is equivalent to `git diff --cached`, showing changes added to the staging area that have not yet been committed.

### 3.6. Unstaging a file

~~~sh
git config --global alias.unstage "restore --staged --"
~~~

Usage:

~~~sh
git unstage src/orders/order-service.ts
~~~

This command resets the file's contents in the index back to the current commit while keeping your edited contents in the working tree. It unstages changes without deleting uncommitted edits.

## 4. A starter alias set

You can create a common set of aliases with these commands:

~~~sh
git config --global alias.st "status --short --branch"
git config --global alias.co switch
git config --global alias.cob "switch -c"
git config --global alias.br "branch --sort=-committerdate"
git config --global alias.lg "log --oneline --graph --decorate --all"
git config --global alias.last "log -1 --stat"
git config --global alias.dfs "diff --staged"
git config --global alias.unstage "restore --staged --"
~~~

Then you can run:

~~~sh
git st
git co main
git cob feature/login
git br
git lg
git last
git dfs
git unstage README.md
~~~

There is no need to create many aliases right away. Pick a small set of repetitive commands, try them for a few days, and adjust according to your habits and project conventions.

## 5. Aliases can accept arguments

For an alias that invokes a regular Git command, arguments passed after the alias are forwarded to that command.

Example:

~~~sh
git config --global alias.ls "log --oneline --decorate"
~~~

Invoke:

~~~sh
git ls -5
~~~

Git expands this into the `log` command with the option limiting the commit count. Similarly, the `co` alias can accept a branch name or commit:

~~~sh
git co release/2.x
~~~

When designing aliases, pick names that do not collide with built-in commands and verify how Git forwards arguments. An alias does not need to parse arguments manually if the underlying Git command already supports them.

## 6. Shell aliases for more complex operations

If an alias value begins with an exclamation mark, Git treats the remainder as a shell command. This allows running multiple commands or calling a shell function.

### 6.1. A read-only shell alias

Example of creating an alias to list contributors:

~~~sh
git config --global alias.authors '!f() { git shortlog -sn --all "$@"; }; f'
~~~

Usage:

~~~sh
git authors
git authors --since="2026-01-01"
~~~

The function `f` receives arguments via `"$@"` and forwards them to `git shortlog`. Wrapping `"$@"` in double quotes preserves each argument intact, even when arguments contain spaces.

Shell aliases are suitable when you need to:

- Combine multiple commands.
- Compute or normalize arguments.
- Invoke external tools.
- Perform conditional operations.

If a simple alias only invokes a single Git command, there is no need to add an exclamation mark.

### 6.2. Distinguishing Git aliases from shell aliases

| Criterion | Git alias | Shell alias |
|---|---|---|
| How to invoke | `git st` | `gs` |
| Where configured | Git config | Shell configuration file |
| Scope | By system/global/local/worktree/command | By shell and user environment |
| Runs from scripts invoking Git? | Yes, if the corresponding Git config is in effect | Usually depends on the shell loading the alias and interactive mode |
| Can invoke Git commands? | Yes | Yes |

Example shell alias in Bash:

~~~sh
alias gs='git status --short --branch'
~~~

After loading the shell configuration, you can type `gs`. Meanwhile, the Git alias `st` is invoked as `git st` and is read by Git from its configuration.

Do not confuse the two mechanisms when instructing teammates. Someone with a global Git alias but no shell alias can still run `git st`; conversely, a shell alias `gs` does not automatically appear in Git config.

## 7. Checking existing aliases

List effective aliases:

~~~sh
git config --get-regexp "^alias\."
~~~

View aliases along with their origin and configuration scope:

~~~sh
git config --show-origin --show-scope --get-regexp "^alias\."
~~~

The output helps identify which config file an alias comes from and at which scope. This is useful when an alias is declared multiple times in global and local configs.

You can check a specific alias:

~~~sh
git config --global --get alias.st
git config --local --get alias.st
~~~

If the command returns no output, the alias may simply not be declared in that scope. When diagnosing, check the relevant scopes rather than concluding the alias does not exist anywhere.

## 8. Editing and deleting aliases

### 8.1. Updating an alias value

Run `git config` again with the same key to update it:

~~~sh
git config --global alias.st "status --branch"
~~~

Or open the global configuration file:

~~~sh
git config --global --edit
~~~

In the configuration file, aliases typically reside in the section:

~~~ini
[alias]
    st = status --short --branch
    lg = log --oneline --graph --decorate --all
~~~

Prefer `git config` whenever possible so Git handles escaping and formatting. If editing directly, maintain valid INI structure and avoid unintentionally creating duplicate values for the same alias.

### 8.2. Deleting an alias

Delete a global alias:

~~~sh
git config --global --unset alias.st
~~~

Delete a local alias in the current repository:

~~~sh
git config --local --unset alias.st
~~~

Deleting in one scope affects only that scope. If the alias still exists in global, system, or worktree, Git may continue recognizing it. Use `--show-origin --show-scope` to locate the exact source before deleting.

### 8.3. Testing changes before saving permanently

You can run a temporary alias with `-c`:

~~~sh
git -c alias.st="status --short --branch" st
~~~

Only save with `--global` or `--local` once the result is right. This approach is helpful when testing an alias with multiple options or checking behavior in a specific repository.

## 9. Configuration precedence and alias conflicts

An alias can be declared in multiple scopes. For single-valued settings, the value from the higher-precedence scope is used. The general ascending order is:

1. System.
2. Global.
3. Local.
4. Worktree, if the repository enables worktree config.
5. Command line via `git -c`.

For example, if global declares:

~~~sh
git config --global alias.st "status --short"
~~~

but the current repository declares:

~~~sh
git config --local alias.st "status --short --branch"
~~~

then inside that repository, the local alias takes precedence. In other repositories, the global alias can still be used.

In addition, built-in Git commands take precedence over aliases with the same name. You cannot use an alias to replace or override a built-in Git command like `status`, `commit`, or `switch`. Choose distinct abbreviations like `st`, `ci`, `co`, or `lg`.

## 10. Principles for naming memorable aliases

A good set of aliases should be short yet easy to guess. You can apply these principles:

- Use short names for very frequent commands such as `st`, `co`, `lg`.
- Use descriptive names for less frequent actions such as `unstage`, `authors`.
- Keep conventions consistent across repositories.
- Avoid names easily confused with built-in Git commands.
- Do not create multiple very similar aliases with different behavior without documenting them.
- Favor read-only aliases before creating aliases that modify data.
- Document aliases that include default flags or special side effects.

Alias names are a personal preference, but avoid overly cryptic abbreviations if you plan to share your workflow with teammates.

## 11. Being cautious with destructive aliases

Aliases can shorten dangerous commands too. Example:

~~~sh
git config --global alias.hardreset "reset --hard"
~~~

Then `git hardreset <commit>` can discard uncommitted changes in the working tree and index. Short aliases make dangerous operations easy to run out of habit.

Do not create destructive aliases without a clear reason. If necessary, choose a name that communicates the consequence, check repository status before running, and understand the exact scope of impact.

Some reminders:

- `reset --hard` can discard uncommitted changes.
- `clean -fd` can delete untracked files and directories.
- `push --force` can overwrite remote history that others rely on.
- Shell aliases can execute any command the user account is permitted to run.

In particular, never copy a shell alias from an untrusted source and run it immediately. Read the full alias value, especially parts starting with an exclamation mark, before saving it to configuration.

## 12. Sharing aliases within a team

Global Git aliases belong to personal configuration, and local aliases live in `.git/config`. Neither is automatically shared like commits in a repository.

If a team wants to standardize certain aliases:

1. Pick a small set of aliases useful to many members.
2. Explain the actual Git command behind each alias.
3. Put the setup commands in onboarding docs or a reviewed configuration script.
4. State the minimum required Git version if an alias uses newer commands or options.
5. Make sure everyone still knows how to run the underlying Git commands when aliases are not configured.

Example onboarding section:

~~~sh
git config --global alias.st "status --short --branch"
git config --global alias.lg "log --oneline --graph --decorate --all"
git config --global alias.unstage "restore --staged --"
~~~

Do not require team members to use a secret alias configured only on the documentation author's machine. Documentation and CI workflows should use standard Git commands or provide clear alias setup instructions.

## 13. Example usage in a working session

Suppose you frequently check branches, create feature branches, inspect history, and unstage a file.

**Step 1 — Create aliases**

~~~sh
git config --global alias.st "status --short --branch"
git config --global alias.cob "switch -c"
git config --global alias.lg "log --oneline --graph --decorate --all"
git config --global alias.unstage "restore --staged --"
~~~

**Step 2 — Check repository status**

~~~sh
git st
~~~

**Step 3 — Create a branch**

~~~sh
git cob feature/search
~~~

**Step 4 — View history**

~~~sh
git lg --max-count=15
~~~

**Step 5 — Unstage a file while keeping edited content**

~~~sh
git unstage src/search/search-service.ts
git st
~~~

These aliases shorten repetitive commands while preserving Git's exact behavior. Whenever you need to understand precisely what happens, you can inspect the configuration or run the corresponding underlying command.

## 14. Alias management checklist

**When creating an alias**

- [ ] Chose the right scope: global, local, or command.
- [ ] Alias name is memorable and does not collide with built-in Git commands.
- [ ] Understood the actual Git command behind it.
- [ ] Tested the alias on an appropriate repository.
- [ ] Carefully inspected any shell alias starting with an exclamation mark.

**When managing aliases**

- [ ] Can list aliases with `git config --get-regexp "^alias\."`.
- [ ] Know the configuration source when aliases share the same name.
- [ ] Remove from the right scope when an alias is no longer needed.
- [ ] Avoid running destructive aliases out of habit.

**When sharing with a team**

- [ ] Documentation explains the underlying command.
- [ ] Clear setup instructions are provided.
- [ ] Do not assume local/global aliases travel automatically with the repository.
- [ ] Do not expect aliases to replace understanding of Git commands.

## 15. Conclusion

Git aliases help shorten common operations and create more consistent workflows. You can store aliases globally to use across repositories, locally for a single repository, or on the command line for a one-time test. Simple aliases typically invoke a Git command directly; aliases starting with an exclamation mark can execute shell commands and should be reviewed carefully.

Start with read-only aliases such as status, log, and diff, then add aliases for frequent actions such as switch or unstage. Always inspect configuration sources, understand the effect of the underlying command, and document aliases when sharing with a team. Good aliases speed up work without making users forget what Git is actually doing.

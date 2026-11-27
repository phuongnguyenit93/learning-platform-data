# Selecting Paths with Pathspecs and Separating Options Using `--`

Git commands frequently accept paths to limit the scope of an operation: staging a few files, viewing a directory's diff, restoring a file, or searching a module's history. Git uses **pathspecs** to describe the set of paths to select. A pathspec can be a specific filename, a directory, a wildcard pattern, or an expression with magic signatures like `:(glob)`, `:(top)`, `:(literal)`, and `:(exclude)`.

A leading `-` in a filename can cause Git to misinterpret it as an option. The `--` separator resolves this ambiguity by telling Git that all subsequent arguments are paths/pathspecs. It also separates revisions from paths in commands like `git log` and `git diff`.

This lesson belongs to the **Files and Index** chapter of SOURCE_CONTROL_GIT. You will learn how to choose the right path scope, control wildcards, exclude directories, handle special filenames, and use `--` safely in daily workflows.

## 1. What Is a Pathspec?

A pathspec is Git's syntax for specifying one or more paths. It appears in many commands, for example:

```bash
git add -- src/app.js
git diff -- src/
git restore --staged -- README.md
git log --oneline -- src/app.js
git ls-files -- '*.js'
```

In these examples, the pathspec can be a single file, a directory, or a pattern matching multiple files. The Git command applies its action to paths matching the pathspec according to that command's rules.

A pathspec is not always just a literal path string. It can contain wildcards or magic signatures controlling how Git performs matching. Therefore, understand pathspecs before using them in commands that affect the index or working tree.

### 1.1. Specific Paths

The simplest pathspec is a relative path:

```bash
git add -- src/app.js
git diff -- src/app.js
```

If you pass a directory:

```bash
git add -- src/
```

Git applies the command to matching paths inside that directory and its subdirectories. This is convenient when operating on a single module.

### 1.2. Pathspecs Are Normally Relative to the Current Directory

Regular pathspecs are interpreted relative to the current working directory. Suppose the repository is:

```text
project/
  src/
    api/
      client.js
    web/
      app.js
  docs/
    setup.md
```

If you are in the root directory `project`, the command:

```bash
git add -- src/api/client.js
```

selects `src/api/client.js`. However, if you are inside `project/src/api`, the pathspec:

```bash
git add -- client.js
```

is what points to that same file. Running the pathspec `src/api/client.js` from `src/api` no longer refers to the path from the repository root.

If you want a pathspec to always resolve from the repository root, use the `top` magic or its shorthand `:/`.

## 2. Using `--` to End the Options Section

In many Git commands, `--` acts as a separator between preceding options/arguments and the trailing list of pathspecs.

Example:

```bash
git add -p -- src/app.js
git diff --cached -- src/app.js
git restore --staged -- src/app.js
git rm -- src/old-file.js
```

Git treats everything after `--` as a pathspec and stops parsing them as command options.

### 2.1. When a Filename Starts with `-`

Suppose the repository has a file named `-draft.txt`. If you run:

```bash
git add -draft.txt
```

Git may interpret `-draft.txt` as an option and fail with an error. Instead, use:

```bash
git add -- -draft.txt
```

Or write the explicit relative path:

```bash
git add -- ./-draft.txt
```

Similarly with other commands:

```bash
git diff -- --draft.txt
git restore --staged -- -draft.txt
git rm -- -draft.txt
```

### 2.2. `--` Is Not Part of the Pathspec

In the command:

```bash
git add -- src/app.js
```

the pathspec is `src/app.js`; `--` is only a separator. Do not include `--` inside filenames or patterns.

### 2.3. `--` in Commands Accepting Both Revisions and Paths

Some commands accept both revisions and paths. Example:

```bash
git log --oneline HEAD -- src/app.js
git diff HEAD~1 HEAD -- src/app.js
git show HEAD -- src/app.js
```

Revision arguments go before `--`; pathspecs go after `--`. This prevents Git from confusing a path name with a branch name, tag, or revision.

With `git log`, if you only want to view history of a path from the current HEAD:

```bash
git log --oneline -- src/app.js
```

If you want to inspect a specific branch as well:

```bash
git log --oneline origin/main -- src/app.js
```

## 3. Distinguishing Pathspecs from Shell Wildcards

When typing commands in a terminal, wildcards may be expanded by the shell before Git receives the arguments. This is a common source of confusion.

Example:

```bash
git add *.js
```

In some shells, `*.js` is expanded by the shell into a list of filenames in the current directory before calling Git. In that case, Git does not receive a single wildcard pathspec, but rather multiple path arguments already expanded by the shell.

If you want Git itself to process the pattern, quote it:

```bash
git add -- '*.js'
```

Exact quoting rules depend on your shell. The example above uses single quotes in Bash, zsh, and PowerShell to pass the pattern as a single argument. In scripts, quote every variable holding a pathspec and avoid concatenating data into command strings.

### 3.1. Why Quote Pathspecs?

Quoting helps:

- Prevent the shell from expanding `*`, `?`, or `[]` before Git processes them.
- Preserve spaces inside filenames.
- Avoid splitting one pathspec into multiple unintended arguments.
- Keep examples more consistent across shells.

Example filename with spaces:

```bash
git add -- 'docs/meeting notes.md'
```

Without quotes:

```bash
git add docs/meeting notes.md
```

the shell may pass `docs/meeting` and `notes.md` as two separate arguments, causing Git to look up the wrong paths.

### 3.2. Wildcards Processed by Git

When a pattern is quoted, Git receives the pattern and applies its own pathspec rules. To avoid relying on default wildcard interpretation, you can explicitly use `:(glob)` when you want glob-style matching.

Example:

```bash
git add -- ':(glob)src/**/*.js'
```

With glob magic:

- `*` matches characters within a single path component without crossing `/`.
- `?` matches a single character within a path component.
- `**` has special meaning to match across multiple directory levels.
- `**/` can match zero or more directory levels.

The pattern `:(glob)src/**/*.js` matches `src/app.js`, `src/api/client.js`, and `.js` files nested deeper inside `src`.

## 4. Pathspec Magic

Git allows prefixing a pathspec with magic signatures to alter how matching works. Long form:

```text
:(magic[,magic...])pattern
```

Example:

```bash
git add -- ':(top,glob)src/**/*.js'
```

Here `top` and `glob` are magic signatures applied simultaneously to the pattern.

### 4.1. `top`: Resolve from the Repository Root

The `top` magic forces the pathspec to be resolved from the working tree root, regardless of which subdirectory the command is run from:

```bash
git add -- ':(top)src/api/client.js'
```

The shorthand form is `:/`:

```bash
git add -- ':/src/api/client.js'
```

This is useful in scripts invoked from different directories. The `:(top)` pathspec makes the scope independent of the current working directory.

### 4.2. `literal`: Treat All Characters Literally

The `literal` magic tells Git not to interpret wildcards or magic inside the pattern portion:

```bash
git add -- ':(literal)src/[draft]*.txt'
```

This pathspec searches for the exact path containing the characters `[draft]*.txt` literally, instead of treating `[]` and `*` as pattern operators.

When paths come from users or external data and must match exact names, `literal` prevents wildcards from accidentally matching extra files.

### 4.3. `glob`: Explicitly Use Glob Syntax

The `glob` magic applies glob-style rules to the pathspec:

```bash
git ls-files -- ':(glob)docs/**/*.md'
git diff --cached -- ':(glob)src/**/*.ts'
```

With `glob`, `*` and `?` do not match the directory separator `/`; use `**` when crossing multiple levels. `glob` magic cannot be combined with `literal` because the two modes have opposite purposes.

### 4.4. `icase`: Case-Insensitive Matching

The `icase` magic makes matching case-insensitive:

```bash
git ls-files -- ':(icase)readme.md'
```

It is helpful when searching for paths in repositories that may have been created on different filesystems. However, avoid using `icase` to mask filename casing inconsistencies in a project if the team needs uniform casing conventions.

### 4.5. `exclude`: Exclude a Subset of Paths

The `exclude` magic (short form `:!` or `:^`) excludes matching pathspecs from the selected set. It normally requires at least one positive pathspec beforehand.

Example staging content in `src/` while skipping auto-generated code:

```bash
git add -A -- ':(top)src' ':(exclude,top)src/generated'
```

Here:

- `:(top)src` selects paths under `src` from the repository root.
- `:(exclude,top)src/generated` removes `src/generated` from that set.

Short form:

```bash
git add -A -- ':/src' ':!/src/generated'
```

When using exclusions, review the result:

```bash
git status --short
git diff --cached --name-status
```

If a negative pathspec does not match as expected, check the root anchor, `/`, wildcards, and pathspec order. Never commit solely on the assumption that a directory was excluded.

### 4.6. `attr`: Select Paths by Git Attributes

The `attr` magic lets you select paths based on attributes assigned in `.gitattributes`:

```bash
git ls-files -- ':(attr:filter=lfs)'
```

This example finds paths whose `filter` attribute has the value `lfs`. You can use negated or unset attribute conditions per the attr pathspec syntax. This is an advanced feature; ensure `.gitattributes` is read properly in the repository and understand attribute rules before using it to stage or delete files.

## 5. Using Pathspecs in Common Git Commands

Pathspecs are used by many commands to narrow scope. `--` is commonly placed right before the pathspec to clearly separate options or revisions.

| Goal | Example Command |
|---|---|
| Stage a single file | `git add -- src/app.js` |
| Stage a directory | `git add -- src/api/` |
| Stage all `.js` files by glob | `git add -- ':(glob)**/*.js'` |
| Stage and exclude generated directory | `git add -A -- ':(top)src' ':(exclude,top)src/generated'` |
| View diff of one file | `git diff -- src/app.js` |
| View staged diff of a directory | `git diff --cached -- src/api/` |
| Unstage a file | `git restore --staged -- src/app.js` |
| Restore file from HEAD | `git restore --source=HEAD --worktree -- src/app.js` |
| Delete and stage deletion | `git rm -- src/old.js` |
| View file history | `git log --oneline -- src/app.js` |
| List tracked files by pattern | `git ls-files -- ':(glob)docs/**/*.md'` |

### 5.1. With `git add`

`git add` updates the index according to the pathspec:

```bash
git add -- ':(top,glob)src/**/*.js'
```

Only paths matching the pattern are considered. Then use:

```bash
git diff --cached --name-status
```

to inspect the set of staged files.

### 5.2. With `git restore`

The pathspec specifies which paths to restore. Example unstaging a group of files:

```bash
git restore --staged -- ':(glob)src/**/*.js'
```

Restore working tree contents from the HEAD commit:

```bash
git restore --source=HEAD --worktree -- ':(top,glob)src/**/*.js'
```

The second command can overwrite unstaged changes on matching paths. Inspect `git diff` or back up content before running.

### 5.3. With `git reset`

To unstage a path using legacy syntax:

```bash
git reset HEAD -- src/app.js
```

The pathspec after `--` specifies which part of the index to update. When resetting only a pathspec, Git does not move the branch the way `git reset --hard <commit>` does; however, always read the command and arguments carefully before running because `reset` has multiple modes.

### 5.4. With `git log` and `git diff`

When a command takes both revisions and paths, `--` separates them:

```bash
git log main -- src/api/
git diff main...feature -- src/api/
```

In the second example, `main...feature` is the revision range of the diff; `src/api/` is the pathspec. Without `--`, a name may be resolved ambiguously as a revision or path depending on the command.

## 6. Handling Special Path Names

Filenames in a repository can contain spaces, wildcards, quotes, or start with `-`. Combine quoting, pathspec magic, and `--` appropriately.

| Filename | Clear Selection Method |
|---|---|
| `meeting notes.md` | `git add -- 'meeting notes.md'` |
| `-draft.txt` | `git add -- -draft.txt` |
| `[draft].txt` | `git add -- ':(literal)[draft].txt'` |
| `report*.txt` (literal `*`) | `git add -- ':(literal)report*.txt'` |
| `src/file.js` from any subdirectory | `git add -- ':(top)src/file.js'` |

### 6.1. Using `./` to Clarify Relative Paths

If a pathspec looks ambiguous or starts with a special character, you can write `./`:

```bash
git add -- ./-draft.txt
```

However, `./` does not replace `--` in every situation. Using both is the clearest approach when a filename begins with a hyphen.

### 6.2. Do Not Use `eval` to Handle Filenames

In scripts, avoid building strings like:

```bash
eval "git add $user_path"
```

If `user_path` contains quotes, semicolons, or shell syntax, the command may be interpreted unexpectedly. Pass the pathspec as a separate argument, quote the variable, and put `--` before the path list:

```bash
git add -- "$user_path"
```

If multiple pathspecs are needed, use an array in Bash or your scripting language's argument-list mechanism; do not concatenate into a shell command string.

## 7. Pathspecs in Scripts and Automation

### 7.1. Selecting Pathspecs from the Repository Root

Scripts may be invoked from various directories. Determine the root:

```bash
repo_root=$(git rev-parse --show-toplevel) || exit $?
```

Then change to the root before running commands:

```bash
cd "$repo_root" || exit $?
git diff --cached -- ':(top,glob)src/**/*.js'
```

Or use the `top` magic so it does not depend on the current directory:

```bash
git diff --cached -- ':(top,glob)src/**/*.js'
```

### 7.2. Handling Path Lists Safely

If retrieving filenames from Git, prefer NUL delimiters:

```bash
git diff --name-only -z --cached
```

Filenames can contain newlines, so do not use line-based `while read` or command substitution to split lists. Use a NUL-safe parser suited to your shell or language. When passing a path back to Git, put `--` before the pathspec.

### 7.3. Pathspecs and Untrusted Input

A pathspec can select more files than intended if it contains wildcards or magic. If a path comes from a user and must match a single exact name, use a literal pathspec:

```bash
git add -- ":(literal)$user_path"
```

In Bash, quoting the variable passes a single argument; the `literal` magic tells Git not to interpret wildcards inside the name. Even if the name starts with magic syntax, literal mode preserves the path meaning.

`--` only stops Git from treating subsequent arguments as options. It does not replace shell quoting, does not stop shell expansion if a pattern is unquoted, and does not prevent command injection on its own if a script uses `eval`.

## 8. Common Errors

### 8.1. Git Reports Unknown Option When Filename Starts with `-`

Cause: the path is parsed as an option. Use:

```bash
git add -- -draft.txt
```

### 8.2. Git Reports Pathspec Did Not Match Any Files

Possible causes include:

- Typo in the path or wrong letter casing.
- Standing in a subdirectory where the relative pathspec is no longer valid.
- Pattern does not match under the active glob rules.
- The file does not yet exist or is outside the scope examined by the command.
- The file is ignored or its state does not fit the operation.

Check your location and paths:

```bash
git rev-parse --show-toplevel
git status --short
git ls-files -- ':(top)src/app.js'
```

To check a literal name containing wildcard characters:

```bash
git ls-files -- ':(literal)src/[draft].js'
```

### 8.3. Wildcard Selects Too Many or Too Few Files

Quote the pattern so the shell does not expand it first. If explicit glob rules are needed, use `:(glob)` and understand `*`, `?`, `**`. Run `git ls-files -- <pathspec>` or `git status --short` to preview the scope before using the pathspec with a command that modifies the index.

### 8.4. Pathspec Behaves Differently When Run from a Subdirectory

Regular paths depend on the current working directory. Use `:(top)` or `:/` when you want resolution from the repository root.

### 8.5. Placing `--` in the Wrong Position

Options must come before the separator:

```bash
git add -p -- src/app.js
```

Do not place command options after `--` expecting Git to still parse them as options; after the separator, arguments are treated as pathspecs.

## 9. Safe Path Selection Workflow

Before staging, deleting, or restoring multiple files with a pathspec, follow these steps:

1. Confirm the repository and current directory:

   ```bash
   git rev-parse --show-toplevel
   ```

2. Clearly define the scope: one file, one directory, the whole repository, or a pattern.
3. If a name starts with `-`, place `--` before the pathspec.
4. If a pattern contains wildcards, quote it so Git receives the pattern intact.
5. If root-relative paths are needed, use `:(top)` or `:/`.
6. If a name must match literally, use `:(literal)`.
7. If excluding a directory, combine a positive pathspec with `:(exclude)`.
8. Preview the set of paths using `git ls-files`, `git status`, or `git diff` with the same pathspec.
9. Run the command that modifies the index or working tree.
10. Re-check `git status --short` and `git diff --cached`.

Example staging all `.js` files in `src` while omitting auto-generated code:

```bash
git ls-files -- ':(top,glob)src/**/*.js'
git add -A -- ':(top,glob)src/**/*.js' ':(exclude,top)src/generated'
git diff --cached --name-status
```

The first command verifies which tracked paths currently match. If new files need to be included too, `git status` should also be checked because `git ls-files` only lists files in the index. After staging, `git diff --cached --name-status` shows the actual changes selected.

## 10. Key Takeaways

- A pathspec is Git's syntax for selecting one or more paths.
- Regular pathspecs are resolved relative to the current directory; `:(top)` or `:/` resolves from the repository root.
- `--` ends the option/revision section and begins the pathspec list; it is not part of a filename.
- Use `--` when a path starts with `-` or when a command takes both revisions and paths.
- Quote wildcards so Git processes the pattern rather than having the shell expand it beforehand.
- `:(glob)` uses glob-style matching; `**` supports matching across multiple directory levels.
- `:(literal)` matches names literally; `:(icase)` is case-insensitive; `:(exclude)` removes paths from the selected set; `:(attr:...)` selects by Git attributes.
- A positive pathspec combined with an exclusion selects a directory while omitting specific subdirectories.
- In scripts, pass pathspecs as separate arguments, quote variables, use NUL-safe filename parsers, and avoid `eval`.
- Preview the scope before running commands that can alter the index or working tree.

When a Git command affects the wrong files, the cause usually lies in how the pathspec was resolved or how the shell transformed arguments before Git received them. Separate options with `--`, pick the right pathspec mode, and verify the scope before executing the operation.

# Ignore Scopes: .gitignore, .git/info/exclude, and core.excludesFile

Git provides several places to declare paths that should not show up as untracked files in the working tree. Three common locations are the `.gitignore` file in the repository, the per-repository `.git/info/exclude` file, and the file configured via `core.excludesFile` for the user. All three use similar ignore pattern syntax, but they differ in sharing scope and intended purpose.

Choosing the right place for rules helps a team ignore auto-generated files together while still allowing each person to ignore personal files or files relevant only to their own machine. Understanding precedence order and how Git evaluates patterns also helps identify why a file is being ignored or why a new rule has not taken effect yet.

## 1. How Do the Three Ignore Locations Differ?

| Location | Scope | Shared via Git? | When to use |
|---|---|---|---|
| `.gitignore` | Repository or a subdirectory and directories beneath it | Yes, when the file is committed | Shared project rules: build output, auto-generated files, caches |
| `.git/info/exclude` | Current repository only | No | Personal files you only want to ignore in this repository |
| `core.excludesFile` | Repositories sharing the user's Git configuration (typically configured globally) | No, unless the user shares the config file manually | OS, IDE, or personal tool files that appear across multiple projects |

### .gitignore: Project Rules

A `.gitignore` file is usually placed at the repository root. You can also place a file of the same name in a subdirectory to apply rules to that directory and the directories beneath it.

Example layout:

```text
project/
├── .gitignore
├── src/
│   └── Main.java
├── build/
└── tools/
    └── .gitignore
```

The `project/.gitignore` file can hold shared rules for the entire project. The `project/tools/.gitignore` file only governs paths inside `tools/` and its subdirectories.

Because `.gitignore` is a file in the working tree, the team can commit it so everyone shares the same rules. When adding or editing rules, include the `.gitignore` file itself in a commit if you want the change to be shared.

### .git/info/exclude: Repository-Specific Rules

Each repository can have an exclude file inside the Git metadata directory. The usual path is `.git/info/exclude`:

```text
.git/
└── info/
    └── exclude
```

This file does not live in the regular working tree and is not committed. It is suited for auxiliary files that only exist on your machine in the current repository, such as personal notes or experimental tool configurations.

The Git directory is not always inside a standard `.git` folder. With linked worktrees or certain repository layouts, `.git` may be a file pointing to the actual Git directory. Use the following command to get the exact path:

```bash
git rev-parse --git-path info/exclude
```

The command returns the path to the exclude file currently used by the active repository.

### core.excludesFile: User-Specific Rules

You can configure an ignore file outside the repository using the `core.excludesFile` configuration variable. When set in the global configuration, all repositories for that user share the patterns in that file:

```bash
git config --global core.excludesFile "$HOME/.config/git/ignore"
```

Create the file at the configured path and add your personal rules, for example:

```gitignore
# Operating system files
.DS_Store
Thumbs.db

# Personal editor configuration files
.idea/
.vscode/
```

These rules are not shared with the repository. If the team needs to ignore a specific IDE configuration directory because it does not belong in the deliverable, consider placing the rule in `.gitignore`; if only you want to ignore your own editor settings, use the global file.

To check the current value and configuration source:

```bash
git config --show-origin --get core.excludesFile
git config --global --show-origin --get core.excludesFile
```

The first command searches for the effective configuration across all scopes Git reads; the second queries only the global configuration. If nothing is configured, the command may print no value.

## 2. How Does Git Prioritize Ignore Sources?

When an untracked path matches multiple rules, Git applies a precedence order from highest to lowest:

1. Patterns passed directly via exclusion options of Git commands that support this mechanism.
2. `.gitignore` files applicable to that path. A file in a deeper directory has higher precedence than a file in a parent directory.
3. The repository's `.git/info/exclude` file.
4. The file specified by `core.excludesFile`.

Within the same precedence level, the pattern that appears last decides the outcome if multiple patterns match. Therefore, a rule in a subdirectory's `.gitignore` can override a rule in a parent file; `.gitignore` files also have higher precedence than `.git/info/exclude` and the global file.

For example, the global file has:

```gitignore
*.log
```

But the repository has `.gitignore`:

```gitignore
!important.log
```

Within the scope of the `.gitignore` file, this rule can re-allow the `important.log` file even though it matches the global `*.log` pattern.

Precedence order does not mean every negated pattern can rescue a file. If a parent directory has already been ignored, Git does not traverse into that directory to look for re-enabled child files. The next section illustrates this case.

## 3. Common Pattern Syntax

`.gitignore`, `.git/info/exclude`, and `core.excludesFile` use the same basic pattern syntax.

| Pattern | Meaning |
|---|---|
| `*.log` | Ignore files or directories whose names end with `.log` at any directory level |
| `/build/` | Ignore only the `build` directory at the same level as the ignore file containing the pattern |
| `build/` | Ignore directories named `build` at any level within the applicable scope |
| `/config/local.yml` | Ignore only that path relative to the directory containing the ignore file |
| `doc/*.pdf` | Ignore PDF files directly inside the `doc` directory, without matching deeper subdirectories |
| `**/cache/` | Ignore the `cache` directory at any depth |
| `!important.log` | Negate a previous ignore rule, allowing a matching file again if Git can traverse to it |

Several important pattern-reading rules:

- Blank lines create no rule.
- Lines starting with `#` are comments. Use `\#` if you want `#` to be part of the pattern name.
- A leading `!` in a pattern negates a previous ignore rule. Use `\!` if the actual filename starts with an exclamation mark.
- A trailing slash restricts the pattern to directories; for example, `cache/` matches a directory named `cache`, not a regular file of the same name.
- If a pattern contains no slash (other than a trailing slash indicating a directory), it can match at any level beneath the directory containing the ignore file.
- If a pattern contains a middle slash or starts with a slash, the path is evaluated relative to the directory containing that ignore file.
- `**` has special meaning in certain positions, allowing multi-level directory matching.

Example:

```gitignore
# Ignore log files at every level
*.log

# Ignore the build directory right at the repository root
/build/

# Ignore every cache directory within this file's scope
cache/

# Ignore PDF files inside doc and its subdirectories
doc/**/*.pdf
```

Patterns in a child `.gitignore` are evaluated relative to the directory containing that child file, not always from the repository root. When moving rules from the root file down into a subdirectory, review the pattern paths because the relative scope has changed.

## 4. Using Negation to Re-Allow Files

The `!` prefix allows excluding a path from the set ignored by an earlier pattern. For example:

```gitignore
# Ignore all log files
*.log

# But keep this file
!important.log
```

If `important.log` is untracked, Git will treat it as an addable file even though the `*.log` pattern matches its name.

For directories, Git must be able to enter the parent directory. The following configuration does not achieve the goal of re-allowing the file:

```gitignore
build/
!build/keep.txt
```

The reason is that `build/` already excluded the entire directory from traversal; Git does not enter it to look for `keep.txt`.

You can instead ignore only the items inside the directory, then negate the file you want to keep:

```gitignore
/build/*
!/build/keep.txt
```

Here the `build` directory itself is not directly ignored, so Git can evaluate the entries inside it. The negated pattern re-allows `keep.txt`. If you need to re-allow a file nested deep inside subdirectories, you must also re-allow each required parent directory so Git can traverse to that file.

## 5. Tracked Files Do Not Disappear Because of .gitignore

Ignore rules apply primarily to files not yet tracked by Git. If a file has already been added to the index and committed, adding it to `.gitignore` does not cause Git to stop tracking that file.

For example, an `.env` file was committed before you added:

```gitignore
.env
```

Git continues to track changes to `.env`. To remove the file from the index while keeping the file on disk in the working tree:

```bash
git rm --cached -- .env
```

Then inspect and commit both the index change and the ignore rule:

```bash
git status
git add .gitignore
git commit -m "Stop tracking local environment file"
```

After the commit, the `.env` file still exists on your machine but is no longer tracked in subsequent commits. Note that older commits still contain the file's contents. If the file ever contained passwords, tokens, or secret information, untracking it does not erase data from history; you must handle the secret exposure incident and clean history using an appropriate procedure.

You should not ignore a template configuration file that the project needs to provide to others. A common practice is to commit `.env.example` with variable names and dummy values, while ignoring `.env` which contains machine-specific settings.

## 6. Choosing the Right Place for Rules

You can use the question "who needs this rule?" to choose where to declare it:

- **Everyone on the project should ignore it:** add to `.gitignore` and commit.
- **Only the repository on my machine needs to ignore it:** add to `.git/info/exclude`.
- **Every repository under my account needs to ignore it:** add to the file configured by `core.excludesFile`.

Selection examples:

| File or directory | Usually appropriate location | Reason |
|---|---|---|
| `build/`, `dist/`, compiler-generated files | `.gitignore` | Shared outputs that should not enter project history |
| Cache file specific to a tool used only on your machine | `.git/info/exclude` | Does not need to apply to the whole team |
| `.DS_Store`, `Thumbs.db` | `core.excludesFile` or `.gitignore` | Can be a personal preference or a shared rule depending on the team |
| Personal editor configuration | `core.excludesFile` | Should not impose one person's editor setup on the whole team |
| Local configuration file containing secrets | `.gitignore` | Everyone must avoid committing private config files; still provide a safe template file |

These are purpose-based guidelines, not mandatory rules. For instance, a team may agree to commit a rule ignoring `.DS_Store` in `.gitignore` so all members share it.

## 7. Checking Why a File Is Ignored

When a file does not appear in the untracked files list, look up the matching rule instead of guessing which file is causing the issue.

Use `git check-ignore -v` to view the source, line number, and pattern:

```bash
git check-ignore -v -- path/to/file.log
```

Example output might report:

```text
.gitignore:12:*.log    path/to/file.log
```

That means the `*.log` pattern on line 12 of `.gitignore` ignored the inspected path.

If the file is already tracked, `git check-ignore` by default usually does not report it as ignored because tracked files are not excluded from the index by ignore rules. You can add `--no-index` to test patterns even against tracked files:

```bash
git check-ignore -v --no-index -- path/to/file.log
```

To view ignored files in repository status:

```bash
git status --short --ignored
```

Ignored entries are typically shown with `!!`. This command is useful when you want to see which files are being hidden from the normal untracked list.

Check whether a file is currently tracked:

```bash
git ls-files -- path/to/file.log
```

If the command prints the path, the file is in the index. In that case, editing `.gitignore` will not stop tracking the file; you need to decide whether to remove it from the index with `git rm --cached`.

## 8. Workflow for Adding and Verifying Ignore Rules

A concise workflow when an auto-generated file appears in the repository:

1. Determine whether the file needs to be committed for the project.
2. Check if the file is already tracked using `git ls-files -- path/to/file`.
3. Choose the ignore source matching the scope: `.gitignore`, `.git/info/exclude`, or `core.excludesFile`.
4. Write the pattern with the correct path scope and verify with `git check-ignore -v`.
5. If the file is already tracked, remove it from the index with `git rm --cached` after confirming you want to keep the local file.
6. Check `git status --short --ignored` and the staged diff before committing.
7. If the rule should be shared, commit the `.gitignore` file along with the related change.

Example of adding a rule to ignore a build directory at the project root:

```gitignore
/build/
```

Then verify:

```bash
git check-ignore -v -- build/output.class
git status --short --ignored
```

If `build/output.class` is already tracked, inspect and untrack it with:

```bash
git rm --cached -- build/output.class
```

If multiple files in the directory are already tracked, you can pass the directory path to `git rm -r --cached -- build/` after carefully reviewing the list of files that will be removed from the index. This command keeps the files in the working tree but removes them from the index; inspect the staged diff before committing.

## 9. Common Errors

| Symptom | Common cause | Resolution |
|---|---|---|
| Added pattern, but file still shows in diff | The file is already tracked | Check `git ls-files`; if appropriate, use `git rm --cached` |
| Ignore rule has no effect | Pattern written relative to the wrong directory or wrong slashes | Use `git check-ignore -v` and check the ignore file location |
| Personal file ignored on teammates' machines | Personal rule was accidentally added to `.gitignore` and committed | Move the rule to `.git/info/exclude` or the global file |
| File to keep is still ignored | Negation pattern does not match or parent directory is already ignored | Re-allow the parent directory first, then re-allow the child file |
| Global ignore is not taking effect | `core.excludesFile` points to the wrong path or file does not exist yet | Check with `git config --show-origin --get core.excludesFile` |
| Cannot find `.git/info/exclude` at the expected path | Repository uses a different Git directory, such as a linked worktree | Use `git rev-parse --git-path info/exclude` |
| Untracked the file, yet changes still appear in older history | Ignore does not erase previous commits | If secrets were involved, handle both the secrets and history separately |

## Conclusion

Use `.gitignore` for shared rules across the project, `.git/info/exclude` for private exceptions in the current repository, and `core.excludesFile` for shared ignore habits across your account. Git prioritizes patterns by source and file location; the last pattern within the same precedence level decides the outcome. Use `git check-ignore -v` to trace rules, and remember that ignoring does not make an already-tracked file disappear from the index.

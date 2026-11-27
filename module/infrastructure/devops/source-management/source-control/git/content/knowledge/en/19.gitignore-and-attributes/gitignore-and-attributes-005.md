# Diagnosing Ignore Rules with git check-ignore -v

When a file does not appear in `git status`, the common cause is that an ignore rule is being applied to the file. That rule may reside in the root `.gitignore`, a nested `.gitignore`, `.git/info/exclude`, or the user's global ignore file. Looking only at the filename or the contents of the root `.gitignore` can cause you to miss the actual source causing Git to ignore the path.

The `git check-ignore -v` command helps identify **the rule source, line number, pattern, and path** that matched. With that, you can find the exact file to edit, understand why a file is ignored, or learn why a `!pattern` exception has not taken effect. This command is diagnostic only; it does not edit `.gitignore`, delete files, or modify the index.

## 1. Why Diagnose Ignore Rules?

In a project, Git typically ignores files generated during work such as build outputs, caches, logs, or local configuration files. For example:

```gitignore
build/
*.log
.env.local
```

These rules help avoid committing temporary files or developer-machine-specific data. However, when a new file does not appear in `git status`, you need to know the exact rule that excluded it.

Common situations:

- A log file is ignored, but you do not know which `.gitignore` contains the rule.
- A rule in a nested `.gitignore` overrides a rule in a parent directory.
- A file that needs to be tracked is matched by an overly broad ignore pattern.
- You added `!pattern` to keep an exception, yet Git still ignores the file.
- A file was previously committed, so adding it to `.gitignore` does not make Git stop tracking it.
- The file is ignored by global configuration, even though the repository has no corresponding rule.

`git check-ignore -v` helps distinguish these cases before editing rules.

## 2. Basic Syntax

Common syntax:

```bash
git check-ignore -v -- <path>...
```

Where:

- `git check-ignore`: asks Git to check whether paths are ignored.
- `-v` or `--verbose`: displays the matched rule along with its source and line number.
- `--`: ends the options section; subsequent arguments are interpreted as paths.
- `<path>`: the path to inspect, typically written relative to the current directory.

Example:

```bash
git check-ignore -v -- build/output.log
```

Illustrative output:

```text
.gitignore:12:build/    build/output.log
```

The result tells you:

| Component | Meaning |
|---|---|
| `.gitignore` | File containing the matched rule; may be a relative or absolute path depending on the source |
| `12` | Line number in the file containing the rule |
| `build/` | Ignore pattern that matched the path |
| `build/output.log` | Path that was checked |

For a global ignore file or `.git/info/exclude`, the source column points to the corresponding file. This is the most important piece of information for knowing where to edit.

## 3. Reading Verbose Output

When running:

```bash
git check-ignore -v -- notes/debug.log
```

You might receive output like:

```text
config/gitignore:8:*.log    notes/debug.log
```

That means line 8 in `config/gitignore` contains the pattern `*.log`, and this pattern is ignoring `notes/debug.log`.

The rule source can be:

- `.gitignore` at the repository root.
- `.gitignore` inside a subdirectory, applying to that directory and directories beneath it.
- `.git/info/exclude`, effective in the current repository but not committed with the project.
- The file configured via `core.excludesFile`, typically a shared ignore file for the user on the machine.

Therefore, if the output points to a path such as `C:/Users/.../.config/git/ignore`, the cause may lie in global configuration rather than the repository. Do not rush to add an exception in the project's `.gitignore` before checking this source.

## 4. Which Rule Takes Precedence When Multiple Patterns Match?

Git can read multiple ignore sources at once. In precedence order from highest to lowest:

1. Patterns passed directly via command-line options on Git commands that support that kind of filtering; `git check-ignore` focuses on diagnosing configured ignore sources.
2. `.gitignore` files applicable to the path. A file in a deeper directory can override a file in a parent directory.
3. `$GIT_DIR/info/exclude` of the current repository.
4. The global ignore file configured via `core.excludesFile`.

Within the same precedence level, the pattern appearing last takes effect if multiple patterns match. The `!` prefix creates a negation rule to remove the path from the ignored set, provided parent directory conditions allow Git to evaluate that path.

Example structure:

```text
project/
├── .gitignore
├── src/
│   └── .gitignore
└── logs/
    ├── app.log
    └── keep.log
```

Root `.gitignore` might contain:

```gitignore
*.log
```

The `src/.gitignore` file can add rules specific to source code. When checking a path inside `src/`, `git check-ignore -v` reports the exact file and line that determine the outcome. Rules in a child file can create exceptions or add rules for its scope.

## 5. Diagnosing Overly Broad Patterns

Suppose you want to track `reports/release.log`, but the repository has the rule:

```gitignore
*.log
```

Check:

```bash
git check-ignore -v -- reports/release.log
```

Git will point to the line containing `*.log`. You can adjust the pattern to match your actual intent. For example, if you only want to ignore logs inside the `logs/` directory:

```gitignore
logs/*.log
```

After editing, check again:

```bash
git check-ignore -v -- reports/release.log
git status --short -- reports/release.log
```

If `check-ignore` no longer reports a matching rule and the file is untracked, the file can appear in `git status` as untracked. If the file is already tracked, status output will reflect tracked status instead of untracked.

Do not narrow a pattern just to make one file appear without checking other paths that depend on that rule. A change in `.gitignore` can affect multiple team members and multiple project outputs.

## 6. Diagnosing !pattern Negation Rules

A pattern starting with `!` is used to create an exception for a path already ignored by another pattern.

For example, wanting to ignore logs in general while keeping one file:

```gitignore
*.log
!release.log
```

If `release.log` is within the exact scope where the pattern applies, the negation rule can bring the file back to untracked status so Git displays it in status.

Verify the result:

```bash
git check-ignore -v -n -- release.log
```

The `-n` (`--non-matching`) option asks Git to display non-ignored paths as well; it is useful when checking whether a negation pattern is the last matching rule. When combined with `-v`, you get additional information to analyze the source and pattern. For a path matching no rule, the pattern field will be empty.

### Why Do Exceptions Fail Inside an Ignored Directory?

Git does not descend into an already-ignored directory to look for negated child files. For example:

```gitignore
logs/
!logs/keep.log
```

The `logs/` rule excludes the entire directory; Git does not evaluate `logs/keep.log`, so the exception may not work. Another way to structure this is to ignore the contents inside while leaving the directory traversable:

```gitignore
logs/*
!logs/keep.log
```

After changing, verify both the directory and the file:

```bash
git check-ignore -v -n -- logs logs/keep.log
```

If the exception is nested multiple levels deep, you may need to un-ignore each parent directory so Git can descend to the file to keep. Use `check-ignore` output to verify each path rather than guessing from line order.

## 7. When a File Is Already Tracked Yet Still Matches an Ignore Rule

Ignore rules primarily apply to untracked files. When a file is already in the index and committed, adding a matching pattern to `.gitignore` does not automatically stop tracking that file.

For example, `config/local.yml` was already committed. Later the team added:

```gitignore
config/local.yml
```

The file remains tracked. Because `git check-ignore` by default does not report files currently tracked by the index, the following command may print nothing:

```bash
git check-ignore -v -- config/local.yml
```

To check whether any ignore rule matches when ignoring index state, use `--no-index`:

```bash
git check-ignore -v --no-index -- config/local.yml
```

`--no-index` instructs Git not to consult the index when checking. This is a useful diagnostic option when you suspect a file was added/committed before the ignore rule was created.

If the actual goal is to stop tracking the file while keeping the local copy, that action must be done separately:

```bash
git rm --cached -- config/local.yml
```

Then commit the index change along with the appropriate ignore rule. `git rm --cached` removes the file from the index while keeping the file in the working tree; make sure the team no longer needs to track that file before committing.

## 8. Checking the Global Ignore File and Local Excludes

If `check-ignore -v` points to a source outside the repository, check the configuration:

```bash
git config --show-origin --get core.excludesFile
```

The command reports the value of `core.excludesFile` and where that configuration is set. If there is no value, Git may not be using a global ignore file declared this way.

To inspect the repository's local exclude rules, open:

```text
.git/info/exclude
```

This file is suited for machine/repository-specific rules that you do not want to commit to the shared `.gitignore`. Because the file is not shared as project content, another member may see different ignore results on the same repository.

If you want to verify the repository root location before looking for ignore files:

```bash
git rev-parse --show-toplevel
```

This helps avoid running commands from another directory and mistaking relative paths.

## 9. Checking Multiple Paths and Using in Scripts

You can pass multiple paths in a single invocation:

```bash
git check-ignore -v -- build/app.jar coverage/index.html notes/todo.txt
```

Git prints rules for the ignored paths. If you also want to see paths that are not ignored:

```bash
git check-ignore -v -n -- build/app.jar coverage/index.html notes/todo.txt
```

With a list of paths passed via standard input:

```bash
git check-ignore -v --stdin
```

By default, `--stdin` reads one path per line. If filenames contain newlines or you need safe script communication, use NUL mode:

```bash
git check-ignore -v -z --stdin
```

`-z` uses the NUL character as a delimiter to avoid misinterpreting filenames with spaces or newline characters. When parsing `-z` output, scripts must also split on NUL rather than splitting by lines.

### Using Exit Codes to Check Whether Any Path Is Ignored

Exit codes useful for automation:

- `0`: at least one path was identified as ignored.
- `1`: none of the paths were identified as ignored.
- `128`: a fatal error occurred while running the command.

Therefore, when using the command in a script, do not treat every non-`0` code as a system failure; exit code `1` can simply mean no paths were ignored. When diagnosing individual paths, use `-v` to retrieve the source and pattern rather than relying solely on the exit code.

## 10. Practical Diagnostic Workflow

Suppose `config/dev-local.yml` does not show up in `git status`, and you want to determine why.

```bash
# 1. Check status, including ignored files.
git status --short --ignored -- config/dev-local.yml

# 2. Find the source, line number, and matched pattern.
git check-ignore -v -- config/dev-local.yml

# 3. If the file is already tracked, check rules without consulting the index.
git check-ignore -v --no-index -- config/dev-local.yml

# 4. If no output appears, request showing non-matching cases too.
git check-ignore -v -n -- config/dev-local.yml

# 5. Inspect the global ignore source if output points to user configuration.
git config --show-origin --get core.excludesFile
```

After identifying the cause, choose the appropriate fix:

- If a pattern is too broad, edit the right ignore file and re-check related paths.
- If a `!pattern` exception is blocked by a parent directory, adjust rules so Git can traverse to the file to keep.
- If the rule is in the global ignore file yet affects only one project, consider moving the rule to the repository's `.gitignore` or adjusting personal configuration.
- If the file is already tracked, remember that ignore rules do not automatically stop tracking; use `git rm --cached` only when the goal is to remove the file from the index.

## 11. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| `git check-ignore -v` lists every `.gitignore` file in the repository | The command only shows rules relevant to the checked paths |
| No output means the file is definitely not ignored | Tracked files are usually not reported by default; try `--no-index` and check `git status` |
| Rules in the root `.gitignore` always win | Deeper `.gitignore` files can override parent directory rules; order and negation also affect results |
| Adding a file to `.gitignore` untracks a committed file | Ignore does not affect tracked files; a separate index operation is needed to stop tracking |
| `!file` always brings the file back | Git cannot re-evaluate files inside an ignored parent directory without un-ignoring that directory |
| Global ignore is shared with the whole team | `core.excludesFile` is machine/user-scoped; `.git/info/exclude` is local-repository-specific |

## 12. Takeaways

When you need to know why a path is being ignored, start with:

```bash
git check-ignore -v -- <path>
```

Read the four pieces of information in the output: rule source, line number, pattern, and path. If you need to see non-matching cases too, add `-n`; if the file may already be tracked, add `--no-index`. When checking in bulk, use `--stdin` and `-z` if special filenames need handling.

Always remember that ignore rules exist to decide whether to track new files. They do not delete files, do not remove an already-tracked file from the index, and are not shared uniformly if placed in global config or `.git/info/exclude`. Diagnosing the exact source before editing keeps ignore rules clear and prevents unintended side effects on other files in the project.

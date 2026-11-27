# Distinguishing .gitignore from .gitattributes

In a Git repository, there are files you do not want to include in history, such as build directories, logs, private configuration files, or data generated at runtime. There are also files that need to be processed by Git under consistent rules across machines, such as normalizing line endings, identifying binary files, or choosing how to diff or merge. Git provides two separate mechanisms for those two sets of needs: **`.gitignore` determines which paths should be ignored when looking for untracked files; `.gitattributes` specifies attributes and how Git processes the content of a path**.

Both files can coexist in a project, but they solve different problems. `.gitignore` does not change how Git handles the content of an already-tracked file. `.gitattributes` likewise does not make a file disappear from `git status` or prevent Git from adding a file to the index.

## 1. Purpose of Each File

| Criterion | `.gitignore` | `.gitattributes` |
|---|---|---|
| Purpose | Ignore untracked paths matching a pattern | Assign attributes to paths so Git handles them consistently |
| Question to answer | Which file or directory should not be suggested for adding to the repository? | How should Git normalize, diff, merge, or export this file? |
| Primary impact | Affects discovering and adding untracked files | Affects how Git interprets and processes the content of a path |
| Does it apply to tracked files? | Ignore rules do not stop tracking already-managed files | Yes. Attributes can apply to both tracked and untracked files |
| How is it usually shared? | Commit `.gitignore` so the whole team shares the ignore rules | Commit `.gitattributes` so the whole team shares the file-handling rules |
| Examples | `build/`, `*.log`, `.env` | `*.sh text eol=lf`, `*.png binary` |

You can remember it concisely: `.gitignore` selects which paths do not need to be put into history; `.gitattributes` describes what Git should do with that path when processing its content.

## 2. How Does `.gitignore` Work?

Git uses patterns in `.gitignore` to identify untracked files that you do not want Git to suggest adding to the index. For example, a Java project may generate `target/`, `.class` files, logs, and private environment configuration. You can put the following rules in `.gitignore` at the root directory:

```gitignore
# Build output directories
/target/
/build/

# Log and bytecode files
*.log
*.class

# Private environment configuration
.env
!.env.example

# Personal IDE configuration
.idea/
```

When matching paths are untracked, Git will not list them as regular untracked files in `git status` and will skip them when scanning to add files. This rule helps avoid putting build artifacts, logs, secrets, or machine-specific settings into commits.

### Ignoring Does Not Untrack Already-Committed Files

A common misconception is that adding a file to `.gitignore` causes Git to stop tracking that file. This is not true. If `config/local.json` has already been committed, adding the `config/local.json` pattern to `.gitignore` does not remove the file from the index, and Git still continues to detect changes to it.

To stop tracking the file while keeping the copy on your machine, use:

```bash
# Add the path to .gitignore first
git rm --cached config/local.json

# Check changes in the index
git status
git diff --cached

# Record removing the file from the repository
git commit -m "Stop tracking local configuration"
```

`git rm --cached` removes the path from the index while keeping the file in the working tree. After committing, the repository no longer manages that file; each machine needs a way to provide its own appropriate configuration. Make sure the file has been backed up or the necessary values have been moved to a safe configuration mechanism before untracking it.

If you truly want to add an ignored file, you can use `git add -f <path>`. This is an intentional action to override ignore rules; only do it when you have confirmed the file is appropriate to include in history.

## 3. Pattern Syntax and Scope in `.gitignore`

Each line is typically a pattern. Blank lines are ignored; lines starting with `#` are comments. A leading `!` in a pattern is used to exclude a path from a preceding ignore rule, provided the parent directory rules allow Git to traverse into that path.

| Pattern | Meaning |
|---|---|
| `*.log` | Ignore files with the `.log` extension at any directory level beneath the ignore file's location |
| `/build/` | Ignore the `build` directory right at the location of this `.gitignore` |
| `build/` | Ignore directories named `build` at levels beneath the ignore file's location |
| `doc/*.pdf` | Ignore PDF files directly inside the corresponding `doc` directory |
| `**/target/` | Ignore the `target` directory at any level beneath the ignore file's location |
| `*.tmp` | Ignore temporary files with the `.tmp` extension |
| `!important.log` | Exception to a previous pattern for `important.log`, provided the parent directory is not excluded from traversal |

A leading `/` in a pattern anchors the pattern to the directory containing `.gitignore`. A `/` in the middle of a pattern makes the path evaluated relative to the ignore file's location. A pattern without `/` (other than a trailing `/` indicating a directory) can match at multiple levels below. A trailing `/` applies only to directories.

### Order and Scope of Application

Git can read multiple ignore sources:

- `.gitignore` files in the directory containing the file and parent directories. A `.gitignore` file closer to the path can override rules from a parent directory.
- `$GIT_DIR/info/exclude`, reserved for local repository-specific rules and not committed.
- A global ignore file specified by `core.excludesFile`, commonly used for files generated by IDEs or operating systems on a personal machine.

Within the same precedence level, the last matching rule usually determines the ignore status. Rules in a higher-precedence source can override lower-precedence sources. Use `git check-ignore -v` to see the exact file and line that produced the result.

For example, a team can commit shared rules in `.gitignore` at the root, while each developer adds personal rules to `.git/info/exclude` or a global ignore file:

```bash
# View the current global ignore configuration
git config --get core.excludesFile

# Set a global ignore file for the current user
git config --global core.excludesFile ~/.config/git/ignore
```

Do not put rules that only serve a personal machine into the shared `.gitignore` if they are not suitable for the whole team. Conversely, build directories or project-generated files should be declared in the committed `.gitignore` so everyone gets the same behavior.

### Exceptions Inside an Ignored Directory

If you ignore an entire directory with `cache/`, Git does not traverse into that directory to look for an excepted child file. To keep a child file, ignore the entries inside and then open a specific exception:

```gitignore
cache/*
!cache/keep.txt
```

When you need to open an exception multiple levels deep, parent directories along the path must also be allowed to be traversed. For instance, if `cache/generated/` is still ignored as a directory, merely adding `!cache/generated/keep.txt` may not be enough. Design the patterns so that Git can traverse to the file that needs to be kept.

## 4. How Does `.gitattributes` Work?

`.gitattributes` assigns attributes to paths. Attributes tell Git how to normalize content, how to display diffs, how to merge, or how to process data when exporting an archive. A line has the general form:

```gitattributes
<pattern> <attribute> <attribute>...
```

Example:

```gitattributes
# Automatically detect text files and normalize content
* text=auto

# Specify line-ending style in the working tree
*.sh text eol=lf
*.bat text eol=crlf

# Identify binary formats
*.png binary
*.jpg binary
*.pdf binary
```

In this example, Git automatically detects most text files for normalization; shell scripts use LF, batch files use CRLF, and images and PDFs are treated as binary. Attribute rules can affect tracked files, even those that are not ignored.

### Four States of an Attribute

An attribute can be in one of the following states:

| Syntax | State | Meaning |
|---|---|---|
| `text` | Set | Enables the attribute, equivalent to boolean true |
| `-text` | Unset | Disables the attribute, equivalent to boolean false |
| `text=auto` | Set value | Assigns the string value `auto` to the attribute |
| `!text` | Unspecified | Clears the previously assigned state so the attribute returns to unspecified |

Having no line assigning the attribute also means the attribute is unspecified. The unset and unspecified states differ: unset is an explicit decision to turn off the attribute; unspecified allows Git or a lower-precedence configuration source to decide according to its defaults.

Within the same `.gitattributes` file, if multiple lines match the same path and the same attribute, the last matching line takes effect for that attribute. Different attributes can be taken from different lines.

### Scope and Precedence of Attributes

Git can obtain attributes from several places:

1. `$GIT_DIR/info/attributes` has the highest precedence and applies only to the local repository.
2. `.gitattributes` files in the directory containing the path and parent directories. A file in a directory closer to the path has higher precedence than a file in a parent directory.
3. The global attributes file configured via `core.attributesFile`.

Within the same file, the last matching line determines the value of the corresponding attribute. A `.gitattributes` committed in the repository is the right place for a team to standardize file-handling rules. `info/attributes` and the global file are suitable for machine-specific or local repository adjustments.

Unlike `.gitignore`, attribute syntax does not allow a negated pattern starting with `!` to exclude a path from a preceding rule. To change an attribute, assign a new state to the attribute you want to adjust, such as `-text` or `!text` on a matching line.

## 5. Important Example: Line-Ending Normalization

Windows typically uses CRLF (`\r\n`) in the working tree, while Linux and macOS typically use LF (`\n`). If each person commits with their own setting, diffs can show the entire file as changed just because of line endings. `.gitattributes` helps a repository standardize how text content is stored.

Example root configuration:

```gitattributes
# Git automatically detects text files to normalize when storing in the repository
* text=auto

# File types that need LF in the working tree
*.sh text eol=lf
*.py text eol=lf

# Batch files need CRLF in the working tree
*.bat text eol=crlf

# Binary files do not undergo line-ending conversion
*.png binary
*.jpg binary
*.pdf binary
```

With `text=auto`, Git automatically detects text content and normalizes line endings in the repository according to text normalization rules. The `eol` attribute specifies the line-ending style when checking out to the working tree. For example, `text eol=lf` stores normalized content and produces a working tree using LF; `text eol=crlf` still normalizes content in the repository but checks out as CRLF.

`binary` is a built-in attribute macro, equivalent to configuring a file as non-text for the relevant operations: disabling text normalization, text-based diffs, and normal merges. For binary files, Git should not attempt to merge lines like source code.

If a repository already contains many files with inconsistent line endings, adding `.gitattributes` does not automatically clean up every working tree immediately. The team needs to agree on a renormalize workflow, usually using `git add --renormalize .` after reviewing the impact, then inspecting the diff before committing. Before running this on an active project, you should create a commit or backup so changes can be compared.

## 6. Attributes for Diff, Merge, and Filter

Besides line-ending handling, `.gitattributes` also controls other behaviors:

| Attribute | Purpose | Example |
|---|---|---|
| `diff` / `-diff` | Enable or disable text-based diff display for the path | `*.pdf -diff` |
| `merge` / `-merge` | Enable or disable normal text merge or select a merge driver | `*.lock -merge` |
| `filter=<name>` | Specify a configured clean/smudge filter | `*.asset filter=asset-clean` |
| `export-ignore` | Exclude the path from an archive created with `git archive` | `docs/internal/ export-ignore` |
| `export-subst` | Replace certain placeholders such as `$Format:%H$` when creating an archive | `VERSION.txt export-subst` |
| `working-tree-encoding=<encoding>` | Declare the encoding in the working tree for Git to convert on storage and checkout | `*.ps1 working-tree-encoding=UTF-16LE` |

Attributes such as `diff=<driver>`, `merge=<driver>`, or `filter=<driver>` may require additional configuration in the machine's Git config. Simply writing the driver name in `.gitattributes` is not enough for a custom command to run automatically on every machine. The team needs to align on installation, executable paths, versions, and how to handle cases where the driver is unavailable.

For example, a project using Git LFS can mark large files with the corresponding filter:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
```

These lines only assign attributes; Git LFS and the filter configuration must be installed and properly set up on collaborators' machines. `.gitattributes` does not automatically install Git LFS or automatically download LFS content if the tool is not yet configured.

## 7. Both Files Can Apply to the Same Path

A file can be subject to both ignore rules and attributes at the same time, yet the two mechanisms remain independent. For example:

`.gitignore`:

```gitignore
/build/
*.log
.env
```

`.gitattributes`:

```gitattributes
* text=auto
*.sh text eol=lf
*.png binary
```

In this situation:

- An untracked `build/app.log` will be ignored by `.gitignore`.
- `src/run.sh` can still be added and committed; `.gitattributes` instructs Git to treat it as a text file with LF in the working tree.
- `assets/logo.png` can still be added and committed; Git applies the `binary` attribute.
- An untracked `.env` will be ignored; if `.env` is already tracked, Git still tracks changes to it even though the ignore pattern matches.

Do not use `.gitattributes` to try to hide secret files, and do not use `.gitignore` to control content conversion. If a sensitive file has already been committed, you must handle untracking it and assessing the history containing the secret under a separate security procedure; merely adding an ignore pattern does not remove already-published data.

## 8. Checking Ignore Rules and Attributes

### Finding the Rule That Ignored a Path

Use `git check-ignore -v` to see the pattern, file, and line number that produced the result:

```bash
git check-ignore -v build/output.log
```

If you also want to check a tracked path to see which ignore pattern would match, add `--no-index`:

```bash
git check-ignore -v --no-index config/local.json
```

`git check-ignore` is mainly for diagnosing ignored paths; if no rule matches, the command may print no output. The `-v` option helps trace back the rule source rather than having to guess across multiple ignore files.

### Viewing Effective Attributes

Use `git check-attr`:

```bash
# View the attributes assigned to a path
git check-attr --all -- src/run.sh

# Check the text and eol attributes specifically
git check-attr text eol -- src/run.sh

# Check the binary/diff attributes
git check-attr binary diff -- assets/logo.png
```

If you want to inspect the `.gitattributes` version already in the index rather than the working tree version, you can use `--cached`:

```bash
git check-attr --cached --all -- src/run.sh
```

This is useful when you have just edited `.gitattributes` without staging it yet, or want to compare the configuration about to be committed with the configuration currently in the working tree.

## 9. A Project Setup Workflow

When starting a new project or standardizing an existing repository, you can follow this sequence:

1. List directories and files generated by builds, tests, IDEs, logs, caches, and personal environment configs.
2. Put shared ignore rules into `.gitignore` at the root; keep machine-specific rules in `.git/info/exclude` or the global ignore file.
3. Identify file types needing special handling: text, binary, scripts, large files, or files requiring a merge driver or filter.
4. Put shared handling rules into `.gitattributes` and verify with `git check-attr`.
5. Check whether any tracked files are accidentally matched as ignored; if untracking is needed, perform `git rm --cached` intentionally.
6. Review the diff, stage both configuration files, and commit so the whole team receives consistent rules.

Example check before committing:

```bash
git status --short
git check-ignore -v build/output.log
git check-attr --all -- src/run.sh assets/logo.png
git diff -- .gitignore .gitattributes
git diff --cached -- .gitignore .gitattributes
```

The final `git diff` commands help inspect unstaged and staged changes. Make sure the new rules do not accidentally ignore source files that should be committed or apply inappropriate conversions to binary data.

## 10. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Adding a file to `.gitignore` removes the file from the repository | No. Already-tracked files remain tracked; use `git rm --cached` if you want to remove it from the index while keeping the local copy. |
| `.gitattributes` prevents Git from adding files | No. Attributes control how paths are processed and do not replace the ignore mechanism. |
| `.gitignore` only takes effect if committed | A local ignore file can also work; commit it to share rules with the whole team. |
| `.git/info/exclude` is shared via commits | No. It is a local repository-specific configuration. |
| All global ignore rules should be placed in the project's `.gitignore` | Personal IDE or operating system rules belong in a global ignore file. |
| `binary` and ignore have the same effect | `binary` assigns a content-handling attribute; ignore skips untracked paths. |
| Adding `text=auto` immediately fixes every existing file | You need to review and potentially run a controlled renormalize workflow to standardize existing content. |
| Assigning `filter=name` is enough for the filter to run on every machine | The driver must be configured and installed appropriately on each user's machine. |

## 11. Self-Check

1. **What problem does `.gitignore` solve?**
   - It ignores untracked paths matching patterns so they are not suggested for addition to the repository.
2. **What problem does `.gitattributes` solve?**
   - It assigns attributes so Git processes a path's content appropriately, such as line-ending normalization, diff, merge, or filters.
3. **Does a tracked file stop being tracked when added to `.gitignore`?**
   - No. You must explicitly remove the file from the index with `git rm --cached` and commit that change.
4. **Which command shows the `.gitignore` file and line that matched a path?**
   - `git check-ignore -v <path>`.
5. **Which command inspects the effective attributes of a file?**
   - `git check-attr --all -- <path>`.
6. **Why should `.gitattributes` be committed in the repository?**
   - So every member uses the same content-handling rules, reducing differences caused by operating systems or personal configurations.

## Conclusion

`.gitignore` controls ignoring untracked paths; `.gitattributes` specifies how Git processes the content of paths. Use `.gitignore` for build directories, logs, and private configurations; use `.gitattributes` for text normalization, line endings, diffs, merges, filters, and archives. When diagnosing, `git check-ignore -v` shows which ignore rule matched, while `git check-attr` shows which attributes are in effect. Properly distinguishing these two mechanisms keeps the repository cleaner and makes Git behavior consistent across team members.

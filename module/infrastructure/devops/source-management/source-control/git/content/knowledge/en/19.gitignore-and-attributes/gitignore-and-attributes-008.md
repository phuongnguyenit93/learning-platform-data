# Checking Effective Attributes with git check-attr

The `.gitattributes` file lets a repository specify how Git handles each file type. Attributes can control line-ending normalization, binary file detection, diffs, merges, or content filters. When results do not match expectations, you need to know which attributes are actually in effect for a specific path.

The `git check-attr` command answers that question. It computes attribute values according to the rules and Git configuration sources currently applied, then displays the result for the requested path. This command is especially useful when multiple `.gitattributes` files or attribute configurations affect a single file.

## 1. What Is a Git Attribute?

An attribute is a name and state/value pair attached to a path. Git uses these attributes to decide how to process file contents during certain operations.

A line in `.gitattributes` has the general form:

```text
<pattern> <attribute> <attribute>...
```

Example:

```gitattributes
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
*.md diff=markdown
```

In the example above:

- Shell files are treated as text and use LF in the working tree.
- Batch files are treated as text and use CRLF in the working tree.
- PNG files disable text normalization because they are binary data.
- Markdown files are assigned a diff driver named `markdown` if that driver is configured.

Git does not require every attribute to be a built-in attribute. Some attributes such as `text`, `eol`, `diff`, `merge`, `filter`, and `export-ignore` have special meaning to Git; other names can be used by project tools or scripts.

## 2. Attribute Assignment Syntax

An attribute can be in one of four states:

| Syntax in `.gitattributes` | Meaning | Typical output from `git check-attr` |
|---|---|---|
| `text` | Set (enable) the attribute | `text: set` |
| `-text` | Unset (disable) the attribute | `text: unset` |
| `text=auto` | Assign the string value `auto` | `text: auto` |
| `!text` | Return the attribute to the unspecified state | `text: unspecified` |

If no rule assigns an attribute, its state is also `unspecified`. The unspecified state differs from unset: unset is an explicit decision to disable the attribute, whereas unspecified means the attribute has no assigned value. Writing `!text` actively resets the attribute to unspecified to cancel a value assigned by a lower-precedence rule.

Example:

```gitattributes
*.txt text
*.bin -text
special.txt !text
*.dat encoding=utf-8
```

`special.txt` has its `text` state reset to unspecified by the last line matching that file. `encoding=utf-8` is an attribute with a custom value; Git only acts on it if a mechanism or tool understands that attribute.

Within a `.gitattributes` file, a later matching rule can override the attribute state set by an earlier matching rule. Overrides apply per attribute and do not necessarily replace all attributes on the previous line.

## 3. Basic git check-attr Command

Common syntax:

```bash
git check-attr <attribute>... -- <path>...
```

Example checking the `text` and `eol` attributes of a shell file:

```bash
git check-attr text eol -- scripts/deploy.sh
```

Illustrative output:

```text
scripts/deploy.sh: text: set
scripts/deploy.sh: eol: lf
```

Each line shows the path, attribute name, and effective value. The value can be `set`, `unset`, `unspecified`, or an assigned string such as `lf`, `crlf`, `auto`, or a filter name.

Check multiple files at once:

```bash
git check-attr text eol -- scripts/deploy.sh scripts/build.bat
```

Check all attributes currently assigned to a file:

```bash
git check-attr --all -- assets/logo.png
```

`--all` is useful when you do not yet know which attributes affect a file. The command lists only attributes that have assigned values; to query a specific attribute explicitly and also see `unspecified` states, name that attribute:

```bash
git check-attr text eol filter diff merge -- assets/logo.png
```

Place `--` before the path list to clearly separate attribute names/options from paths. This also avoids mistaking filenames starting with a hyphen for command options.

## 4. Reading Results and Identifying Effective Attributes

Suppose the `.gitattributes` file at the repository root has these contents:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
*.jpg binary
```

Check the files:

```bash
git check-attr text eol -- README.md
git check-attr text eol -- scripts/deploy.sh
git check-attr text eol -- scripts/build.bat
git check-attr text diff merge -- images/logo.jpg
```

The output might look like:

```text
README.md: text: auto
README.md: eol: unspecified
scripts/deploy.sh: text: set
scripts/deploy.sh: eol: lf
scripts/build.bat: text: set
scripts/build.bat: eol: crlf
images/logo.jpg: text: unset
images/logo.jpg: diff: unset
images/logo.jpg: merge: unset
```

In this example, `binary` is a built-in attribute macro equivalent to disabling `diff`, `merge`, and `text`. If you check `text`, `diff`, and `merge`, Git displays the corresponding unset states.

Do not inspect only the root `.gitattributes` file and jump to a conclusion. A `.gitattributes` file closer to the file can override parent directory rules; additionally, local or global configurations may also participate. `git check-attr` lets you see the result after Git applies its precedence order.

## 5. Attribute Sources and Precedence Order

Git can read attributes from several places. In precedence order from highest to lowest:

1. `$GIT_DIR/info/attributes` of the current repository.
2. `.gitattributes` files in the directory containing the file and parent directories, with files closer to the path having higher precedence than files in parent directories.
3. The global attributes file specified by the `core.attributesFile` setting.
4. System-level attributes file, if installed.

Within the same `.gitattributes` file, a later matching rule can override an attribute set by an earlier matching rule. Across different files, the higher-precedence source wins over the lower-precedence source for each assigned attribute.

Example layout:

```text
repository/
|-- .gitattributes
|-- src/
|   |-- .gitattributes
|   `-- main.c
`-- .git/
    `-- info/
        `-- attributes
```

If all four sources set the `diff` attribute for `src/main.c`, the configuration in `.git/info/attributes` has the highest precedence. If there is no rule there, `.gitattributes` inside `src/` has higher precedence than the file at the repository root.

### Checking the Global Attributes Configuration

View the `core.attributesFile` setting along with its declaration source:

```bash
git config --show-origin --get-all core.attributesFile
```

If the command returns no output, an explicit global attributes file may not be configured. Git may still use an environment default path. This setting is separate from the global `.gitignore`; `core.excludesFile` is the dedicated setting for ignore rules.

### Checking the Local info/attributes File

`$GIT_DIR/info/attributes` has high precedence but is not committed with the repository. It is useful for exceptions applying only on the current machine, yet it can also cause results to differ between two machines. When attributes seem unexpected, remember to check this local source.

## 6. Checking Attributes in Working Tree, Index, and Commits

During edits, the contents of `.gitattributes` in the working tree may differ from the staged contents. Consequently, inspection results can vary depending on which attribute source you want to examine.

### Checking According to Current Configuration

The standard command reads `.gitattributes` files currently in the working tree along with other attribute sources:

```bash
git check-attr text eol -- src/main.c
```

This is a quick way to inspect the rules currently effective while working in the working tree.

### Checking Staged `.gitattributes` Contents

If you have just edited `.gitattributes` and run `git add`, you can inspect against the index:

```bash
git check-attr --cached text eol -- src/main.c
```

`--cached` tells Git to use the `.gitattributes` files in the index rather than the working tree copies. This option is useful when you want to know which attribute configuration will accompany staged contents in the next commit.

### Checking Against a Specific Commit or Tree

When you need to compare against a committed revision, use `--source`:

```bash
git check-attr --source=HEAD text eol -- src/main.c
git check-attr --source=HEAD~1 text eol -- src/main.c
```

The first command checks against the tree of `HEAD`; the second checks against the parent commit. This is useful when investigating why a file previously had different line endings or diff behavior. `--source` is available in modern Git versions; if Git reports an invalid option, check `git check-attr -h` to confirm your version and supported syntax.

The three checks answer three different questions: working tree reflects current edits, `--cached` reflects staged configuration, and `--source` reflects configuration in the specified tree.

## 7. Attributes Commonly Inspected

### `text` and `eol`: Line-Ending Normalization

Example:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
```

- `text` enables or disables text content normalization when Git stores content into the index.
- `text=auto` lets Git automatically detect text files appropriate for normalization.
- `eol=lf` requests LF in the working tree.
- `eol=crlf` requests CRLF in the working tree.
- `-text` disables text processing for binary files.

Check:

```bash
git check-attr text eol -- scripts/deploy.sh
git check-attr text eol -- scripts/build.bat
```

If the result differs from expectations, inspect `.gitattributes` files by directory, `info/attributes`, `core.attributesFile`, and the `core.autocrlf` setting. Attributes tell you the assigned rule; existing files in the index may still need to be renormalized through a separate step, such as re-staging files after changing rules.

### `diff` and `merge`: How Git Compares and Merges

Some examples:

```gitattributes
*.jpg binary
*.md diff=markdown
generated/** -diff -merge
```

- `diff` enables default text diff behavior; `-diff` disables standard text diff for that path.
- `diff=<driver>` selects a named diff driver, if that driver is configured.
- `merge` enables default merge handling; `-merge` tells Git not to use standard text merge for that file.
- `merge=<driver>` selects a custom merge driver if already configured.

Check:

```bash
git check-attr diff merge -- images/logo.jpg
git check-attr diff merge -- docs/guide.md
```

The output shows only the effective attribute. It does not verify that a custom driver is installed properly or will run successfully. For custom drivers, also inspect corresponding configurations such as `diff.<driver>.*` or `merge.<driver>.*`.

### `filter`: Clean/Smudge Filters

The `filter` attribute binds a driver name to a file:

```gitattributes
*.data filter=normalize-data
```

The driver can be configured using keys such as:

```bash
git config filter.normalize-data.clean "command-to-clean"
git config filter.normalize-data.smudge "command-to-smudge"
```

`clean` processes content when storing files into Git; `smudge` processes content when checking out to the working tree. Filters can handle data formats or Git LFS integration. Check the attribute:

```bash
git check-attr filter -- datasets/sample.data
```

If the output is `filter: normalize-data`, that only confirms the filter name is assigned. It does not prove the clean/smudge commands exist or can run. Check the filter configuration and external tool status.

### `export-ignore` and `export-subst`

These attributes affect contents when creating an archive with `git archive`:

```gitattributes
docs/internal-notes/** export-ignore
src/version.txt export-subst
```

`export-ignore` excludes paths from the archive; `export-subst` enables substituting certain commit placeholders inside file contents when exporting an archive. Check:

```bash
git check-attr export-ignore export-subst -- docs/internal-notes/plan.md
git check-attr export-ignore export-subst -- src/version.txt
```

These attributes do not delete files from the repository and are not ignore rules when Git displays working tree status.

## 8. Distinguishing git check-attr from git check-ignore

The two commands have similar names but solve two different problems:

| Command | Question | Example |
|---|---|---|
| `git check-attr` | Which attributes are in effect for the path? | `git check-attr text eol -- src/main.c` |
| `git check-ignore` | Which ignore rule causes the path to be ignored? | `git check-ignore -v build/output.log` |

`.gitattributes` controls how Git handles files; `.gitignore` controls which untracked files are ignored when displaying status and evaluating normal adds. A file can be ignored yet still have attributes, or be tracked and still be governed by attributes. The two mechanisms are independent.

Example:

```bash
git check-ignore -v .env.local
git check-attr --all -- .env.local
```

The first command finds the ignore rule; the second displays attributes assigned to the path. Even if a file is ignored, `git check-attr` can still return attributes because querying attributes does not mean adding the file to the repository.

## 9. Workflow for Troubleshooting Unexpected Attributes

When Git handles a file with the wrong line endings, diff, or filter, check in order:

1. **Identify the exact path.** Attributes apply by path, so use a path relative to the repository root or appropriate location.
2. **List effective attributes.** Run `git check-attr --all -- <path>` to see which attributes are currently assigned.
3. **Query suspected attributes directly.** Use `git check-attr text eol diff merge filter -- <path>` to also see `unspecified` states.
4. **Compare working tree with index.** Also run `git check-attr --cached ...` if `.gitattributes` has been staged.
5. **Compare against a commit.** Use `--source=HEAD` or another commit to determine where rules changed.
6. **Check higher-precedence sources.** Inspect `.git/info/attributes`, `.gitattributes` in parent paths, and `core.attributesFile`.
7. **Check driver/filter configuration.** If an attribute has a driver name value, verify the corresponding driver is configured and external tools are ready.

Example set of diagnostic commands:

```bash
git check-attr --all -- src/main.c
git check-attr text eol diff merge filter -- src/main.c
git check-attr --cached text eol -- src/main.c
git check-attr --source=HEAD text eol -- src/main.c
git config --show-origin --get-all core.attributesFile
```

`git check-attr` displays the final value Git computed, but does not tell you the exact line in which file produced that value. When you need to trace the source, search matching rules across each `.gitattributes`, `info/attributes`, and the global attributes file in precedence order.

## 10. Practice Exercise

In a test repository, create a `.gitattributes` file at the root with these contents:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
*.jpg binary
```

Create sample files or use corresponding paths in a project, then perform:

1. Run `git check-attr text eol -- scripts/deploy.sh` and explain the two values returned.
2. Run `git check-attr text eol -- scripts/build.bat` to verify the CRLF rule.
3. Run `git check-attr --all -- images/logo.jpg` and explain the `binary` macro.
4. Add a `.gitattributes` in the `scripts/` directory to override `eol` for a specific file, then check again.
5. Stage the `.gitattributes` change, modify the working tree copy further, and compare `git check-attr` with `git check-attr --cached`.
6. Commit the configuration, then use `git check-attr --source=HEAD~1` to compare with the previous revision.
7. Explain why `git check-attr` does not replace `git check-ignore`.

You have completed the exercise when you can determine the effective attributes for a path, explain which precedence source decided the outcome, and distinguish values in the working tree, index, and commits.

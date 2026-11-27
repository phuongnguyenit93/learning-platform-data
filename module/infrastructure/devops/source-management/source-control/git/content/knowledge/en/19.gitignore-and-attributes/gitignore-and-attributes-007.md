# Scope and Precedence Order of File Attributes

Git attributes let you specify how Git processes each file type, such as normalizing line endings, displaying diffs, merging contents, or applying filters when storing data into and retrieving data from the repository. An attribute can be declared at the repository-wide level, inside a subdirectory, in the repository's private configuration, or in a user's shared configuration file. Understanding scope and precedence order helps you know which rule takes effect when multiple files declare attributes for the same path.

## 1. What Are Git Attributes Used For?

Git attributes are rules that bind attributes to paths. They are typically declared in a `.gitattributes` file. Git and various integrated tools read these attributes to decide how to handle content.

Some common attributes:

| Attribute | General effect |
|---|---|
| `text` | Controls line-ending normalization when storing content into Git |
| `eol` | Specifies the line-ending style in the working tree, typically `lf` or `crlf` |
| `diff` | Controls how Git generates diffs for the file type |
| `merge` | Specifies behavior or driver when merging files |
| `filter` | Specifies a clean/smudge filter when data enters or leaves the repository |
| `working-tree-encoding` | Declares the file encoding in the working tree for Git to convert on storage and retrieval |
| `ident` | Enables `$Id$` keyword expansion per Git's mechanism |
| `export-ignore` | Excludes the path from archives created with `git archive` |
| `export-subst` | Enables replacing certain placeholders when creating an archive |

Example `.gitattributes` file in the root directory:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.png binary
```

In this example, Git automatically detects and normalizes text content according to `text=auto`; shell files are checked out with LF, batch files with CRLF, and PNG files are processed as binary data. `binary` is a built-in attribute macro, equivalent to turning off text processing, normal diffs, and normal merges (`-text -diff -merge`).

Attributes apply to paths in the repository, including both tracked and untracked files when Git needs to determine attributes. They do not decide whether a file is included in commits; that is the role of the index and ignore rules.

## 2. Distinguishing `.gitattributes` from `.gitignore`

The two files have similar pattern syntax but solve different problems:

| File | Purpose | Example |
|---|---|---|
| `.gitignore` | Ignore untracked files so Git does not continually list them as untracked | `build/`, `.env.local` |
| `.gitattributes` | Assign attributes so Git processes content or paths according to defined rules | `*.sh text eol=lf` |

Adding a path to `.gitignore` does not automatically stop tracking an already-committed file. Likewise, assigning `-text` in `.gitattributes` does not make a file disappear from `git status` or exclude it from the repository.

A repository can use both files for the same kinds of paths. For example, `.gitignore` ignores the `build/` directory, while `.gitattributes` specifies how tracked text files in `src/` are handled.

## 3. Locations Where Attributes Can Be Declared

Git can read attributes from multiple sources. The key sources include:

1. **`$GIT_DIR/info/attributes`**: a private file for the current repository, with the highest precedence. Usually used for local rules you do not want to commit or share with the team.
2. **`.gitattributes` in the repository**: a file in the same directory as the path or in parent directories. The closer a file is to the evaluated path, the higher its precedence.
3. **User's global attributes file**: the path configured via `core.attributesFile`, serving as default rules for that user's repositories.
4. **System-level attributes file**: default rules at the Git installation level, with the lowest precedence.

This order is evaluated from highest to lowest precedence. Thus, a local rule in `info/attributes` can override a rule in the project's `.gitattributes`; rules in the project can override global or system-level rules.

The `.gitattributes` file is committed into the repository so it can be shared with all members. `info/attributes` and the global attributes file are typically not committed with the project, so they are suited for machine-specific or user-specific exceptions.

## 4. Scope of `.gitattributes` by Directory

A `.gitattributes` file applies to paths inside the directory containing that file and its subdirectories according to pattern rules. When Git evaluates a path, it reads `.gitattributes` in the path's directory first, then walks up through parent directories.

Example layout:

```text
project/
  .gitattributes
  src/
    .gitattributes
    main/
      App.java
    vendor/
      .gitattributes
      Legacy.java
  docs/
    Guide.md
```

Suppose the files declare:

`project/.gitattributes`

```gitattributes
*.txt text eol=lf
```

`project/src/.gitattributes`

```gitattributes
*.txt eol=crlf
```

`project/src/vendor/.gitattributes`

```gitattributes
*.txt -text
```

For `src/vendor/notes.txt`, Git checks the file closest to the path first. `-text` from `src/vendor/.gitattributes` can override the `text` state declared at the parent level. For `src/notes.txt`, the rule in `src/.gitattributes` overrides `eol=lf` from the root file while still retaining the `text` attribute inherited from the root file because the two lines affect two different attributes.

A `.gitattributes` file in a subdirectory does not reach upward to parent directories or across to sibling directories. For example, `src/.gitattributes` does not change how Git handles `docs/Guide.md`.

## 5. Precedence Order When Multiple Sources Declare Rules

When multiple sources assign values to the same attribute for the same path, the source with higher precedence determines the result. Within the repository's `.gitattributes` files, a file closer to the path has higher precedence than a file in a parent directory.

General order:

```text
$GIT_DIR/info/attributes             highest
          |
          v
<file-directory>/.gitattributes
          |
          v
<parent-directory>/.gitattributes
          |
          v
<root-directory>/.gitattributes
          |
          v
core.attributesFile (user/global)
          |
          v
system-level attributes              lowest
```

For example, the root file declares:

```gitattributes
*.md text eol=lf
```

The `docs/.gitattributes` file declares:

```gitattributes
*.md eol=crlf
```

For `docs/Guide.md`, the `text` attribute can still be `set`, while `eol` is `crlf`. Git resolves per attribute rather than selecting an entire line or an entire file as a single all-or-nothing result.

## 6. Order of Lines Within the Same File

If multiple patterns in the same file match the same path, a later line can override a value set by an earlier line. Overrides occur on a per-attribute basis.

Example:

```gitattributes
*.txt text eol=lf
generated/*.txt -text
generated/keep.txt text
```

- For `notes.txt`, the first line sets `text` and `eol=lf`.
- For `generated/output.txt`, the second line sets `text` to unset; the `eol` attribute from the first line is not modified by the second line.
- For `generated/keep.txt`, the last line sets `text` back to set.

When multiple rules exist, read all matching patterns and determine which attribute is overridden. Do not assume a later line wipes out the entire effect of an earlier line.

## 7. Four States of an Attribute

An attribute can be in one of four states:

| Syntax | State | Meaning |
|---|---|---|
| `text` | Set | Attribute is enabled |
| `-text` | Unset | Attribute is disabled |
| `eol=lf` | Value | Attribute has a specific string value |
| `!text` | Unspecified | Resets the attribute to an unspecified state |

Example:

```gitattributes
*.txt text
archive/*.txt -text
archive/legacy.txt !text
```

`archive/legacy.txt` has the `text` attribute state as unspecified because the last line resets the attribute state. `!text` differs from `-text`: `-text` explicitly disables the attribute, whereas `!text` marks the attribute as unspecified in the result.

Note: `!text` is attribute state syntax. It is not a path negation pattern. Negated path patterns like `!path` are not allowed in `.gitattributes`; to configure an exception, write a more specific pattern and set the corresponding attribute state.

## 8. Pattern Syntax and Matching Scope

Patterns in `.gitattributes` are interpreted relative to the directory containing that `.gitattributes` file. The rules resemble `.gitignore`, with a few key differences to remember:

- Patterns without `/` generally match filenames at levels beneath the directory containing `.gitattributes`.
- Patterns containing `/` are evaluated relative to the directory containing that `.gitattributes` file.
- `*` matches part of a name within a single path component; `**` can match across multiple directory levels.
- Negation patterns starting with `!` are not supported in `.gitattributes`.
- A pattern matching a directory does not automatically apply recursively to every file inside that directory; use a form like `directory/**` if you want to match contents beneath it.

Example:

```gitattributes
*.java text
src/generated/** -text
docs/*.md text eol=lf
```

`*.java` can apply to Java files at levels beneath the `.gitattributes` file. `src/generated/**` scopes the rule to contents inside the auto-generated directory. `docs/*.md` restricts to Markdown files directly inside the `docs` directory relative to the `.gitattributes` file's location.

If you need an exception for a file, add a more specific pattern after the general pattern:

```gitattributes
*.sh text eol=lf
scripts/vendor/*.sh -text
```

This keeps rules easier to read and inspect than creating many overlapping broad patterns.

## 9. Configuring a Global Attributes File

You can declare default attributes for your own repositories using the `core.attributesFile` setting:

```bash
git config --global core.attributesFile <path-to-global-attributes-file>
```

Then create the file at the configured path, for example:

```gitattributes
*.psd -text -diff
*.docx -text -diff
```

Global rules are useful when you want to handle certain formats identically across all local repositories. However, because it is not committed in the project, teammates may not share the same rules. Formatting requirements that must be unified for the whole team should be declared in the repository's `.gitattributes`.

Check the configuration and file source:

```bash
git config --show-origin --get core.attributesFile
git rev-parse --git-path info/attributes
```

The first command shows the configuration source of `core.attributesFile` if set. The second prints the location of the `info/attributes` file in the current repository. You can inspect these two files to find local or global rules affecting a path.

## 10. Using `info/attributes` for Repository-Specific Exceptions

The `$GIT_DIR/info/attributes` file has the highest precedence among attribute sources. It is suitable when you need to override project rules only on the current machine, such as testing a diff driver or disabling a filter during investigation.

Example contents:

```gitattributes
large-data/sample.csv -diff
```

This rule can override the committed `.gitattributes` configuration for `large-data/sample.csv` in the current repository. Other members do not receive this rule when cloning or pulling because `info/attributes` is not part of commit history.

Because of its high precedence, an old rule in `info/attributes` can make it look like the project's `.gitattributes` is not working. When results differ from expectations, check this file before modifying shared team rules.

## 11. Inspecting Actual Attributes with `git check-attr`

There is no need to guess which source is taking effect. Use `git check-attr` to ask Git for the attribute state of a path:

```bash
git check-attr text eol diff merge filter -- src/main/App.java
```

The output reports each attribute as `set`, `unset`, a specific value, or `unspecified`. To list all attributes currently assigned to a path:

```bash
git check-attr --all -- src/main/App.java
```

If you want to inspect attributes according to the index contents rather than the `.gitattributes` file in the working tree, use:

```bash
git check-attr --cached text eol diff -- src/main/App.java
```

The `--cached` option is useful when you have just edited `.gitattributes` without staging it yet and want to see what the current index specifies. The output of `git check-attr` shows the final state; to locate the declaring source, check `.gitattributes` from the file's directory up to the root directory, `info/attributes`, and the global file.

## 12. Consolidated Example: Normalizing Line Endings by Directory

Suppose a Java project has the layout:

```text
project/
  .gitattributes
  src/
    .gitattributes
    main/App.java
    generated/Model.java
  docs/
    .gitattributes
    Guide.md
```

Root file:

```gitattributes
* text=auto
*.java text eol=lf
*.md text eol=lf
```

`src/.gitattributes` file:

```gitattributes
generated/** -text
```

`docs/.gitattributes` file:

```gitattributes
*.md eol=crlf
```

Expected results:

- `src/main/App.java` receives `text` and `eol=lf` from the root file.
- `src/generated/Model.java` has `text` unset by the closer rule in `src/.gitattributes`.
- `docs/Guide.md` still has `text` enabled from the root file, while `eol` is overridden to `crlf` from `docs/.gitattributes`.

Check each path:

```bash
git check-attr text eol -- src/main/App.java
git check-attr text eol -- src/generated/Model.java
git check-attr text eol -- docs/Guide.md
```

If results do not match expectations, also inspect `info/attributes` and `core.attributesFile`, since those two sources can override files in the repository.

## 13. Common Misconceptions

- **Assuming `.gitattributes` only exists as one file at the root directory.** Git can read files in multiple directories; a file closer to the path has higher precedence.
- **Assuming one line overrides all previous attributes.** Overrides happen per attribute; unaffected attributes retain their previously determined values.
- **Confusing `!attr` with `-attr`.** One state is unspecified, while the other is unset.
- **Using negation patterns like `.gitignore`.** Path negation patterns are not supported in `.gitattributes`.
- **Forgetting `info/attributes`.** This is the highest-precedence source and can make project rules appear ineffective.
- **Placing shared team requirements in the global attributes file.** Other members do not automatically receive that local configuration; put shared rules in the repository.
- **Using `.gitattributes` to ignore files.** Ignoring untracked files belongs in `.gitignore`; attributes control how Git processes paths.
- **Failing to check the index after editing `.gitattributes`.** The working tree and the index may contain two different versions of rules; use `git check-attr --cached` when you need to inspect the staged version.

## 14. Workflow for Determining Effective Attributes

When a file is processed differently than expected, follow this sequence:

1. Identify the repository-relative path and the attributes to inspect.
2. Run `git check-attr` for that path to view the final state.
3. Read `.gitattributes` in the file's directory, then check parent directories in order.
4. Check `$GIT_DIR/info/attributes` since this file has the highest precedence.
5. Check `core.attributesFile` and system-level rules if the source still has not been found.
6. Check the order of matching patterns within each file; later lines can override earlier lines per attribute.
7. If recently edited rules are not yet staged, compare working tree results with the index using `git check-attr --cached`.
8. After adjusting, re-verify attributes and confirm actual behavior such as diff, line endings, or filters.

## 15. Takeaways

Git attributes are merged from multiple sources in precedence order: `info/attributes` highest, followed by `.gitattributes` closest to the path and files in parent directories, then the global and system-level attributes files. Within a single file, a later matching pattern can override attributes from an earlier pattern; overrides occur independently for each attribute. Use `git check-attr` to see what Git actually applies, and keep a clear distinction between shared repository rules and machine-local exceptions.

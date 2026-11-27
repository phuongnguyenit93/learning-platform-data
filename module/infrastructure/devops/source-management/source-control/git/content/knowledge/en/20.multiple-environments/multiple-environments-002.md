# Coordinating `core.autocrlf`, `core.eol` with `text` and `eol` attributes

A Git project is often developed across multiple operating systems. Windows commonly uses CRLF (`\r\n`) as the line-ending character, while Linux and macOS commonly use LF (`\n`). If different machines save the same file with different line-ending styles, Git may display many modified lines even though the logic has not changed. Some tools may even fail when reading scripts or configuration files that have the wrong line-ending style.

Git provides two layers of control to handle this issue. The `core.autocrlf` and `core.eol` configurations govern how Git converts line endings in the local environment; `.gitattributes` attributes with `text` and `eol` define the policy for each file type in the repository. When properly coordinated, a project can store text content in a unified standard inside Git while checking out the line-ending style suitable for the tools or operating systems in use.

In Git source code management, this is part of multi-environment collaboration. A clear policy reduces noisy diffs, avoids false conflicts, and keeps scripts, source code, and documentation working reliably across different machines.

## 1. What are LF and CRLF?

Line-ending characters mark where a line breaks in a text file. The two common styles are:

| Type | Symbol | Byte representation | Common environments |
| --- | --- | --- | --- |
| LF | Line Feed | `0A` | Linux, macOS, and many modern developer tools |
| CRLF | Carriage Return + Line Feed | `0D 0A` | Windows and some legacy text formats |

For example, the following two files may look identical in a text editor:

```text
Hello
Git
```

However, their actual bytes differ:

```text
LF file:    48 65 6C 6C 6F 0A 47 69 74 0A
CRLF file:  48 65 6C 6C 6F 0D 0A 47 69 74 0D 0A
```

If Git does not normalize line endings, converting a file from LF to CRLF can cause Git to treat every line as modified. This makes code reviews hard to read, increases the likelihood of merge conflicts, and obscures actual logic changes.

### Where does Git store content?

When committing, Git stores a snapshot of file contents in the object database. For text files configured for normalization, Git typically stores them as LF in the blob, while on checkout it can convert them to CRLF or LF depending on the policy. Therefore, the line-ending style visible in the working tree does not necessarily match the bytes stored in the blob.

You can visualize the workflow as:

```text
Working tree
  CRLF or LF file
        |
        | clean conversion during git add
        v
Normalized index / blob
  Text content using LF
        |
        | smudge conversion during checkout
        v
Working tree
  Line-ending style based on attributes and configuration
```

Git performs conversions through clean steps when moving content into the index and smudge steps when writing content out to the working tree. `.gitattributes` determines which files need processing; local configuration influences the line-ending style on checkout.

## 2. What does `core.autocrlf` control?

`core.autocrlf` is a local Git configuration, typically set based on user preference or working environment. There are three common values:

| Value | When adding content to Git | When checking out to the working tree |
| --- | --- | --- |
| `true` | Converts CRLF to LF | Converts LF to CRLF |
| `input` | Converts CRLF to LF | Does not automatically convert LF to CRLF |
| `false` | Does not automatically convert via this setting | Does not automatically convert via this setting |

### `core.autocrlf=true`

```bash
git config --global core.autocrlf true
```

This setting is commonly used on Windows. Git normalizes CRLF to LF when adding content to the index and converts LF to CRLF on checkout. It is roughly equivalent to applying a `text=auto` policy with CRLF checkout for files detected as text.

For example: a Java file in the repository is stored with LF, but when checked out on a Windows machine it may appear as CRLF in the working tree. When staged and committed, Git converts CRLF back to LF to keep the stored content normalized.

### `core.autocrlf=input`

```bash
git config --global core.autocrlf input
```

This setting suits environments that typically use LF, such as Linux or macOS. Git converts CRLF to LF when adding content to the index, but does not automatically convert LF to CRLF on checkout. Checked-out files generally keep LF.

### `core.autocrlf=false`

```bash
git config --global core.autocrlf false
```

Git does not automatically convert line endings via `core.autocrlf`. Working tree content is preserved according to the existing data and applicable attribute rules. If a repository requires a normalization policy, declare it explicitly in `.gitattributes` rather than relying on every machine having the same global setting.

### Viewing and setting configuration

```bash
git config --show-origin --get core.autocrlf
git config --global --get core.autocrlf
git config --local core.autocrlf false
```

`--show-origin` shows which configuration file the value comes from. `--global` sets it for the current user; `--local` sets it only for the current repository. If `--get` returns no output, the setting may not be configured and Git will use its default.

Do not arbitrarily change global `core.autocrlf` across multiple projects with different policies. Global configuration affects many repositories; local configuration lets you adjust behavior for a specific project.

## 3. `core.eol` sets line endings on checkout

`core.eol` specifies the line-ending style Git uses when checking out files treated as text. Common values:

| Value | Result on checkout |
| --- | --- |
| `lf` | LF |
| `crlf` | CRLF |
| `native` | The default line-ending style of the current operating system |

Example:

```bash
git config --local core.eol lf
```

Or:

```bash
git config --local core.eol crlf
```

`core.eol` mainly applies to files marked as text. Git uses this setting when `core.autocrlf` is unset or set to `false`. When `core.autocrlf` is `true` or `input`, that setting determines the default checkout behavior and `core.eol` is no longer the deciding factor. Therefore, when analyzing a specific file, inspect both the configuration and the file's attributes.

Check the configuration:

```bash
git config --show-origin --get core.eol
```

If `core.eol` is not set, the default value is `native` in cases where Git relies on this configuration to determine the checkout style.

## 4. `.gitattributes` and the role of the `text` attribute

`.gitattributes` is a policy file committed alongside the repository. It allows a team to define how Git processes each file type without relying solely on individual machine configurations.

The `text` attribute controls line-ending normalization:

- `text`: treats the file as text and normalizes CRLF to LF when adding to the index.
- `text=auto`: lets Git auto-detect text files and then normalize detected files.
- `-text`: does not perform line-ending normalization for the file; commonly used for binary files.

Example root `.gitattributes` file:

```gitattributes
# Auto-detect text files by default and normalize to LF in Git
* text=auto

# Source code and documentation use LF in the working tree
*.java text eol=lf
*.kt text eol=lf
*.js text eol=lf
*.ts text eol=lf
*.json text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.md text eol=lf
*.sh text eol=lf

# Batch files and some Windows scripts use CRLF on checkout
*.bat text eol=crlf
*.cmd text eol=crlf

# Binary files do not undergo line-ending conversion
*.png -text
*.jpg -text
*.jar -text
*.zip -text
```

The `* text=auto` rule serves as the baseline policy for files Git detects as text. The specific rules below it explicitly specify the checkout style for each extension. Adjust the list to match the project's actual file types; not every file sharing an extension necessarily requires the same policy.

### Why do binary files need `-text`?

Binary files such as images, archives, fonts, or executables do not have a concept of text line endings. If Git attempts to convert CRLF/LF bytes inside those files, the data can be corrupted. Marking them `-text` prevents Git from applying line-ending normalization.

You can use the `binary` attribute for binary files:

```gitattributes
*.png binary
*.jpg binary
*.pdf binary
```

The `binary` macro attribute is equivalent to disabling text diff, text merge, and text normalization for that file. If you only need to control line endings, `-text` is sufficient.

## 5. The `eol` attribute specifies the checkout style per file

The `eol` attribute lets the repository enforce the working tree line-ending style for a group of files:

- `eol=lf`: checks out the file with LF.
- `eol=crlf`: checks out the file with CRLF.

Example:

```gitattributes
*.sh text eol=lf
*.bat text eol=crlf
```

For `*.sh`, Git normalizes stored content in the repository to LF and checks it out as LF. This is important because Linux shells often fail on CRLF in scripts, leading to errors such as unexpected `\r` characters at the end of command lines or interpreter errors.

For `*.bat`, Git still normalizes stored content in the repository to LF but checks it out as CRLF to suit certain Windows tools. As a result, users on both operating systems can work on the same repository without generating mass line-ending changes.

When a file has `eol=lf` or `eol=crlf`, Git treats it as a text file and applies the specified checkout style. This declares policy much more explicitly than relying on each machine's `core.eol`.

## 6. Coordinating `core.autocrlf`, `core.eol`, `text`, and `eol`

These mechanisms do not completely replace one another. Their roles can be summarized as follows:

| Mechanism | Scope | Role |
| --- | --- | --- |
| `core.autocrlf` | Local user/repository configuration | Enables general automatic conversion rules for files detected as text |
| `core.eol` | Local configuration | Chooses the default checkout style for text files when no more specific rule governs them |
| `text` | Path-based attribute in `.gitattributes` | Enables or disables line-ending normalization when adding content to Git |
| `eol` | Path-based attribute in `.gitattributes` | Specifies LF or CRLF for a file on checkout |

Order of reasoning when inspecting a file:

1. Determine whether the file is treated as text via `text`, `text=auto`, or `-text`.
2. Check whether the file specifies `eol=lf` or `eol=crlf`.
3. If there is no specific checkout style, inspect `core.autocrlf` and `core.eol` to understand local behavior.
4. Inspect the actual line endings in the index and working tree.

A repository policy can be written clearly as:

```gitattributes
* text=auto
*.java text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
```

Meanwhile, each machine can set local configuration appropriate for its environment:

```bash
# Example configuration on a Windows machine
git config --global core.autocrlf true

# Example configuration on a Linux/macOS machine
git config --global core.autocrlf input
```

Explicit attributes in `.gitattributes` unify behavior across team members. Local configuration remains helpful for files without specific rules or for repositories that do not provide a detailed policy.

### Avoiding misunderstandings about precedence

`.gitattributes` defines path-based policy and can override the default behavior provided by local configuration. `core.autocrlf` and `core.eol` are not project configuration files that get synced to the entire team; they belong to each machine's Git configuration. When a file has a specific `eol` attribute, treat that as the file's checkout rule rather than trying to infer it from global `core.eol`.

## 7. Inspecting applied attributes and actual line endings

Do not guess solely from the operating system. Git provides commands to inspect active attributes and line endings in each area.

### Using `git check-attr`

```bash
git check-attr text eol -- src/main/java/example/App.java
git check-attr --all -- scripts/deploy.sh
```

The first command shows the `text` and `eol` values Git applies to the Java file. The second lists all active attributes for the script. Results can indicate an attribute is set, unset (`unset`), or has no specific rule (`unspecified`).

### Using `git ls-files --eol`

```bash
git ls-files --eol
git ls-files --eol -- '*.java'
```

This command displays line endings in the index, the working tree, and the applied attributes for each file. Example:

```text
i/lf    w/crlf  attr/text eol=crlf    src/main/java/example/App.java
i/lf    w/lf    attr/text eol=lf      scripts/deploy.sh
```

Meaning:

- `i/lf`: content in the index uses LF.
- `w/crlf`: file in the working tree uses CRLF.
- `w/lf`: file in the working tree uses LF.
- `attr/text eol=...`: active text attribute and checkout style.

If you see `i/crlf`, the repository may be storing CRLF in the index, or the file has not yet been normalized according to the desired policy. If you see `w/mixed`, the file may contain multiple line-ending styles; inspect it before normalizing.

### Checking actual configuration

```bash
git config --show-origin --get-all core.autocrlf
git config --show-origin --get-all core.eol
git config --show-origin --get-all core.safecrlf
```

`--show-origin` helps identify whether configuration comes from system, global, or local scope. Multiple values may exist across configuration levels; verify the effective value and its source before making changes.

## 8. `core.safecrlf` and unsafe conversion warnings

`core.safecrlf` helps Git warn about or reject certain line-ending conversions that cannot be safely reversed. Common values:

| Value | Behavior |
| --- | --- |
| `false` | Disables this safety check |
| `warn` | Warns when a conversion is detected that could cause information loss |
| `true` | Rejects the operation when the conversion is not reversible according to Git's check |

Example:

```bash
git config --global core.safecrlf warn
```

This setting is useful when a team is transitioning line-ending policies or when a file might contain mixed line endings. It helps catch situations where Git normalization risks making unwanted byte changes.

`core.safecrlf` does not replace `.gitattributes` and does not guarantee every file has consistent line endings. Combine it with explicit attributes, `git ls-files --eol` checks, and careful diff reviews before committing.

## 9. Normalizing a repository with an inconsistent line-ending history

If a repository has existed for a long time, some files may be stored as LF, others as CRLF, or a single file may have mixed line endings. Adding `.gitattributes` does not automatically rewrite existing blobs. You must instruct Git to re-apply clean rules to tracked files.

### Step 1: Protect current work

Check status:

```bash
git status -sb
```

Commit or stash in-progress changes and ensure you can recover if the normalization results are unexpected. Normalization can produce a large diff in the index.

### Step 2: Create `.gitattributes`

Example policy for a project:

```gitattributes
* text=auto
*.java text eol=lf
*.kt text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.png -text
*.jpg -text
*.jar -text
```

Adjust rules to fit your actual technology stack and tools. Stage the attributes file first:

```bash
git add .gitattributes
```

### Step 3: Re-normalize tracked files

```bash
git add --renormalize .
```

`--renormalize` instructs Git to re-run the clean process on all tracked files to update the index according to the new attributes. This option implicitly updates tracked files (`-u`); it does not automatically add new untracked files such as `.gitattributes` if that file is not yet staged.

### Step 4: Inspect the diff

```bash
git status --short
git diff --cached --stat
git diff --cached --ignore-space-at-eol
git ls-files --eol
```

Ensure the changes are primarily line-ending normalization. If the diff shows logic content being deleted or modified, stop and check attributes, encoding, or files with mixed line endings before committing.

`git diff --ignore-space-at-eol` ignores end-of-line differences when comparing content, but that does not mean every change in the diff is safe. Still inspect the modified files and verify any lines whose content actually differs.

### Step 5: Commit the normalization changes

```bash
git commit -m "Normalize text file line endings"
```

Policy changes and normalization should be performed in a dedicated commit, not mixed with refactoring or feature work. Reviewers will easily recognize that this commit only standardizes line endings.

After committing, notify the team so everyone updates their repository and avoids triggering another wave of line-ending diffs. If team members have local changes, they should save their work before syncing with the normalization commit.

## 10. Example policy for Windows, Linux, and macOS teams

Suppose a Java project has team members on Windows, Linux, and macOS. The team decides:

- Java, Kotlin, JSON, YAML, Markdown, and shell scripts are stored as LF in the repository and checked out as LF.
- Windows `.bat` and `.cmd` scripts are checked out as CRLF.
- Images, archives, and packaged libraries do not undergo line-ending conversion.

`.gitattributes` file:

```gitattributes
* text=auto

*.java text eol=lf
*.kt text eol=lf
*.json text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.md text eol=lf
*.sh text eol=lf

*.bat text eol=crlf
*.cmd text eol=crlf

*.png -text
*.jpg -text
*.gif -text
*.jar -text
*.zip -text
```

Windows team members can set:

```bash
git config --global core.autocrlf true
```

Linux or macOS team members can set:

```bash
git config --global core.autocrlf input
```

Files configured with `eol=lf` or `eol=crlf` follow the repository policy. Local configuration acts as a fallback for files without specific rules.

After cloning, each team member checks:

```bash
git check-attr text eol -- src/main/java/example/App.java
git ls-files --eol -- src/main/java/example/App.java scripts/deploy.sh scripts/deploy.bat
```

The output should confirm that the index is normalized and the working tree uses the appropriate line-ending style per file type. If a team member sees many files marked modified immediately after checkout, inspect configuration and attributes before staging or committing.

## 11. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| `core.autocrlf` is a shared repository policy | It is a local setting; per-file policy should be shared via `.gitattributes` |
| `core.eol` automatically normalizes all files | It controls checkout style for text files when applicable; attributes determine which files are processed |
| `text` and `eol` are the same | `text` enables normalization; `eol` specifies the exact checkout style |
| Git always stores CRLF on Windows | Normalized text files can be stored as LF in blobs even when the working tree uses CRLF |
| Changing config alone normalizes old history | Tracked files must have rules re-applied via `git add --renormalize .` |
| Image files can safely use `text=auto` | Binary files should be marked `-text` or `binary` |
| `core.safecrlf` automatically fixes files with mixed line endings | It warns or rejects certain conversions; the user still needs to inspect and fix the file |
| A large `git diff` is always a logic change | It may be line-ending differences; inspect with `git ls-files --eol` and diff ignoring EOL |

## 12. Common errors and troubleshooting

| Symptom | Possible cause | How to check or resolve |
| --- | --- | --- |
| Many files report modified after checkout | Inconsistent `autocrlf` setting or changed attributes | Check `git config --show-origin`, `git check-attr`, `git ls-files --eol` |
| Commit creates a whole-file diff | Working tree line endings differ from current stored style | Add `.gitattributes` policy, normalize, and review separately |
| Shell script fails with `^M` character errors | Script file has CRLF in an environment requiring LF | Set `*.sh text eol=lf`, normalize, and re-verify |
| Binary file is unexpectedly modified | File was treated as text | Set `-text` or `binary` for that file type |
| Git emits a safecrlf warning | Conversion may be irreversible or file has mixed line endings | Inspect bytes, attributes, and content before staging |
| `git add --renormalize .` produces a large diff | New policy changes many files or files are inconsistent | Verify scope, attributes, content, and isolate in a normalization commit |
| One machine has different config from teammates | Differences in global/local config | Use `.gitattributes` as project policy and check local configuration |

If you want to see whether a specific file is being converted, inspect its attributes and EOL status:

```bash
git check-attr --all -- path/to/file
git ls-files --eol -- path/to/file
```

To verify the content actually stored in the blob, extract the blob to a temporary file or inspect the bytes with an appropriate tool. Do not draw conclusions solely from how an editor displays lines.

## 13. How do `.gitattributes` and `.editorconfig` work together?

`.gitattributes` controls how Git processes content during add, checkout, diff, and merge. `.editorconfig` guides text editors on how to create or format files while users edit them, such as line-ending style, charset, and indentation.

Example `.editorconfig`:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true

[*.bat]
end_of_line = crlf
```

The two files should be consistent: `.gitattributes` defines the standard when storing/sharing via Git; `.editorconfig` helps editors produce compliant files from the start. An editor does not replace Git's rules, and Git does not guarantee every editor obeys `.gitattributes` while users are typing content.

## 14. Practice

Carry out the following on a test repository containing at least one text file and one binary file:

1. Run `git config --show-origin --get core.autocrlf` and `git config --show-origin --get core.eol` to record the current configuration.
2. Run `git ls-files --eol` to inspect line endings in the index and working tree.
3. Create `.gitattributes` with `* text=auto`, one `eol=lf` rule, one `eol=crlf` rule, and one `-text` rule.
4. Use `git check-attr --all -- <file>` to verify each rule.
5. Stage `.gitattributes`, then run `git add --renormalize .`.
6. Inspect `git diff --cached --stat`, `git diff --cached --ignore-space-at-eol`, and `git ls-files --eol`.
7. Confirm the binary file is not normalized and scripts have the appropriate checkout style.
8. Commit the policy and normalization changes separately after reviewing.
9. Clone the repository in an environment or account with a different `core.autocrlf` and compare `git ls-files --eol`.

After practicing, explain why blobs in Git can use LF while the working tree on Windows uses CRLF, and why per-file attributes enable more reliable team collaboration than asking everyone to set the same `core.autocrlf` value.

## 15. Knowledge self-check

1. Which bytes differ between LF and CRLF?
2. How do `core.autocrlf=true`, `input`, and `false` differ during add and checkout?
3. Which part of the conversion process does `core.eol` control?
4. What effect does the `text` attribute have on content in the index?
5. What problems do `eol=lf` and `eol=crlf` solve?
6. Why do binary files need `-text` or `binary`?
7. Which command displays the attributes applied to a file?
8. What information does `git ls-files --eol` provide?
9. When should you run `git add --renormalize .`?
10. How do `.gitattributes` and `.editorconfig` differ?

## Conclusion

`core.autocrlf` and `core.eol` control line-ending behavior in the local environment; `text` and `eol` in `.gitattributes` define per-file policy that can be shared alongside the repository. Choose a consistent storage standard, explicitly specify files requiring LF or CRLF, exclude binary files from normalization, and verify with `git check-attr` and `git ls-files --eol`. When changing policy for an existing repository, use `git add --renormalize .` after protecting in-progress work and carefully reviewing the diff before committing.

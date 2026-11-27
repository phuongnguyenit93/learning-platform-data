# Normalizing tracked files with git add --renormalize

When multiple people work on Windows, macOS, and Linux, the same text file can appear with different line-ending styles: LF or CRLF. If Git is not configured consistently, changes solely to line-ending characters can make a file look completely modified, create very large diffs, or make history hard to read.

Git provides `git add --renormalize` to re-run the clean process on tracked files and update the corresponding content in the index. This command is especially useful after changing text attributes in `.gitattributes` or line-ending conversion settings. When used properly, the repository stores text content in a standardized form, while each working tree can use the line-ending style suited to its environment.

## 1. Why do files need normalization?

In a multi-OS repository, the same line of text can be stored with two ending styles:

- **LF** (`\n`): commonly used on Linux and macOS.
- **CRLF** (`\r\n`): commonly encountered on Windows.

Without clear rules, one team member may commit a file with CRLF, and another checks it out and re-saves it as LF. Git may display mass line changes even though the program's logic has not changed.

For example, consider a 100-line file. If only the line-ending style changes, the diff may report all 100 lines deleted and re-added. This creates noise during code review and makes it harder to find actual changes.

One solution is to standardize the content stored in the Git index/repository as LF, and then let Git convert it to the desired line-ending style when checking out to the working tree.

## 2. Where does Git convert line endings?

You can visualize the workflow as follows:

```text
Working tree
  (CRLF or LF depending on environment)
        |
        | clean filter during git add
        v
Index / Git object database
  (normalized content, usually LF)
        |
        | smudge / checkout conversion
        v
Working tree
  (LF or CRLF depending on attributes)
```

When you run `git add`, Git reads content from the working tree and applies the clean process before writing the content into the index. On checkout, Git applies the reverse conversion or smudge filter to generate the content in the working tree.

For line endings, attributes in `.gitattributes` tell Git which files are text and what line-ending style is desired. Common attributes:

| Attribute | Meaning |
|---|---|
| `text` | Treats the file as text and normalizes line endings in the index |
| `text=auto` | Lets Git auto-detect text files before normalizing |
| `-text` | Disables text normalization for matching paths |
| `eol=lf` | Checks out text files with LF |
| `eol=crlf` | Checks out text files with CRLF |

For example, `text` causes text content in the index to be normalized to LF. The `eol` attribute specifies the line-ending style when Git writes files out to the working tree.

## 3. Declaring rules with .gitattributes

To give the repository clear rules for all team members, create or update the `.gitattributes` file in the root directory.

Example:

```gitattributes
# Auto-detect text files and normalize line endings
* text=auto

# Shell scripts use LF
*.sh text eol=lf

# Windows batch scripts use CRLF
*.bat text eol=crlf
*.cmd text eol=crlf

# Binary files do not undergo line-ending conversion
*.png -text
*.jpg -text
*.jpeg -text
*.pdf -text
```

These rules serve the following purposes:

- `* text=auto` lets Git auto-detect text files and normalize files detected as text.
- `*.sh text eol=lf` ensures shell scripts are checked out with LF.
- `*.bat` and `*.cmd` are checked out with CRLF, which suits certain Windows tools.
- Image files and PDFs are marked `-text` so they are not treated as text.

You can adjust the extension list according to the project's actual file types. For binary formats or specialized text formats, declare attributes explicitly rather than relying entirely on auto-detection.

The `.gitattributes` file should be committed with the repository so everyone receives the same rules. Attributes apply to paths relative to the `.gitattributes` file's location; a file in a subdirectory can define separate rules for files beneath it.

Check the attributes Git currently applies to a file:

```bash
git check-attr text eol -- src/Main.java
git check-attr text eol -- scripts/build.sh
git check-attr text eol -- tools/build.bat
```

The output shows the effective attribute values such as `text: auto`, `text: set`, `eol: lf`, or `eol: crlf`. If the result is `unspecified`, there is no explicit rule for that attribute in the evaluated sources.

## 4. What does git add --renormalize do?

Basic syntax:

```bash
git add --renormalize .
```

The command asks Git to re-apply the clean process to tracked files within the `.` pathspec, and then update the index with the new results. The `--renormalize` option is equivalent to re-applying the clean process to tracked files and implicitly includes updating tracked paths (`-u`).

This means:

- Tracked files are re-read from the working tree and processed according to current attributes/configuration.
- The index is updated if the cleaned content differs from what is currently stored.
- Untracked files are not automatically added just because you run `--renormalize`.
- The command does not automatically create a commit and does not push changes to a remote.
- The pathspec determines the scope; running from a subdirectory with `.` affects only paths beneath that directory.

Therefore, if you just created a new `.gitattributes` file, stage that file separately:

```bash
git add .gitattributes
```

Then run renormalize on the repository from the root directory:

```bash
git add --renormalize .
```

Staging `.gitattributes` separately is necessary when the new file is untracked, because `--renormalize` only processes tracked files. If `.gitattributes` is already tracked, its changes will also be updated when running renormalize.

## 5. Safe normalization workflow

Before normalizing, check the repository status:

```bash
git status
```

It is best to start from a clean working tree to avoid accidentally pulling in-progress changes into the same normalization pass. If there are changes to keep, commit or stash them first; note those changes clearly so you can restore them later.

A common workflow:

**Step 1: Define the project's line-ending rules.**

Decide which files are text, the line-ending style in the index, and the desired line-ending style on checkout. Do not change global configuration or add patterns arbitrarily before understanding which files need normalization.

**Step 2: Create or update .gitattributes.**

Example:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
```

**Step 3: Stage the rules file.**

```bash
git add .gitattributes
```

If `.gitattributes` is already tracked, this stages changes to the file. If it was newly created, the command adds the new file to the index.

**Step 4: Normalize tracked files.**

Run from the repository root directory:

```bash
git add --renormalize .
```

Git re-runs the clean process for tracked files across the repository.

**Step 5: Inspect the scope of changes.**

```bash
git status
git diff --cached --stat
git diff --cached --check
git diff --cached
```

Review the list of modified files and the diff content. If more files changed than expected, re-check attributes, filters, and line endings before committing.

**Step 6: Commit verified changes.**

```bash
git commit -m "Normalize tracked files"
```

The commit usually includes both the `.gitattributes` file and the normalized contents in the index. If the team prefers to separate rule changes and data changes into two commits, staging and committing can be planned separately, while ensuring the first commit does not leave the repository with inconsistent rules.

## 6. Checking line endings in the index and working tree

Git has a useful command to inspect the line-ending status of each file:

```bash
git ls-files --eol
```

Example output:

```text
i/lf    w/crlf  attr/text eol=crlf    scripts/build.bat
i/lf    w/lf    attr/text eol=lf      scripts/build.sh
i/-text w/-text attr/-text            images/logo.png
```

Column meanings:

- `i/`: line ending of content in the index.
- `w/`: line ending in the working tree.
- `attr/`: attributes applied to that path.

For example, `i/lf w/crlf attr/text eol=crlf` is a valid state: Git stores LF-normalized content in the index, while checking it out to the working tree as CRLF according to the attribute. Do not conclude a file is wrong just because the `i` and `w` columns differ; compare against the intended attributes.

Combine with `git check-attr` to verify the rules:

```bash
git check-attr --all -- scripts/build.bat
git ls-files --eol -- scripts/build.bat
```

If attributes are not as expected, review the `.gitattributes` location, patterns, and other attribute sources. If attributes are correct but the working tree file does not yet have the desired line-ending style, you may need to re-checkout the file after safeguarding any uncommitted changes.

## 7. Distinguishing renormalize from other add commands

`git add` commands have different purposes:

| Command | Primary effect |
|---|---|
| `git add file` | Stages the current content of the specified file |
| `git add .` | Stages changes and new files within the current pathspec |
| `git add -A` | Stages additions, modifications, and deletions within the specified scope (entire working tree by default if no pathspec) |
| `git add -u` | Stages modifications and deletions of tracked files; does not add new files |
| `git add --renormalize .` | Re-runs the clean process for tracked files within the pathspec and updates the index |

The key difference is that `--renormalize` tells Git to re-apply the clean process, making it suitable after changing `.gitattributes` or line-ending rules. Plain `git add .` does not express the intent to re-normalize all tracked files under new rules.

If you need to add new files, use regular `git add` for those files. If you need to normalize tracked files, use `--renormalize` with a clear pathspec.

## 8. Impact of core.autocrlf and the text attribute

Git has the `core.autocrlf` setting to support environment-based line-ending conversion:

| Value | General behavior |
|---|---|
| `true` | Converts LF in content detected as text to CRLF on checkout in appropriate environments; normalizes CRLF to LF on add |
| `input` | Normalizes CRLF to LF on add; does not convert LF to CRLF on checkout |
| `false` | Does not enable automatic conversion via this setting |

View the current value and configuration source:

```bash
git config --show-origin --get core.autocrlf
git config --show-origin --get core.safecrlf
```

`core.autocrlf` is usually a per-user machine preference. `.gitattributes` lets the repository describe rules for each file type more explicitly, so team members do not have to rely solely on personal configuration.

When changing `core.autocrlf` or the `text` attribute, content already in the index is not automatically refreshed just because the configuration changed. This is a typical case for running:

```bash
git add --renormalize .
```

Do not change `core.autocrlf` for all team members simultaneously without a project convention. Agree on `.gitattributes`, normalize the index in a reviewed commit, and instruct the team to update to that commit.

## 9. Cases requiring caution

**Binary files:** Do not apply text normalization to images, archives, executables, or other binary files. Use `-text` for file groups that need protection from line-ending conversion. With `text=auto`, Git tries to detect text files, but projects should still declare important formats explicitly.

**Custom clean/smudge filters:** `--renormalize` re-runs the clean process, including any filters configured for the file. If a filter transforms content, the outcome may differ significantly from merely changing CRLF/LF. Before running on a large repository, inspect filters and test on a representative set of files.

**Uncommitted changes:** Because the command updates the index from the working tree content of tracked files, in-progress edits on those files may be staged alongside the normalization pass. Commit or stash separate work before running.

**Pathspec scope:** `git add --renormalize .` covers only the current directory and paths below it. If run from a subdirectory, tracked files elsewhere in the repository are not processed. Run from the repository root to normalize everything.

**Deleted files:** Because this option implicitly includes updating tracked paths, deletions within the pathspec may also be staged into the index. Carefully inspect `git status` and the staged diff before committing.

**Committed history:** Renormalize updates only the current index. It does not rewrite old commits and does not remove earlier versions of files from Git history.

## 10. Handling an overly large diff after renormalize

If after running the command, Git reports hundreds of changed files, do not commit right away. Check in this order:

1. Confirm `.gitattributes` is staged and contains the right patterns.
2. Use `git check-attr text eol -- <file>` to inspect attributes on several representative files.
3. Use `git ls-files --eol` to view line endings in the index and working tree.
4. Inspect `git diff --cached --stat` and `git diff --cached` to distinguish line-ending changes from actual content changes.
5. Check clean filters if the project configures custom filters.
6. If a rule is wrong, fix `.gitattributes`, and then re-run `git add --renormalize .` while preserving any edits you need to keep.

If a file had real logic changes before normalization, identify and review those changes separately. The goal is to ensure the normalization commit contains only changes the team understands and accepts.

## Conclusion

Use `.gitattributes` to unify how Git processes files across multiple environments, then run `git add --renormalize .` from the repository root to re-apply the clean process to tracked files. Stage `.gitattributes` separately if it is a new file, inspect the index and working tree with `git ls-files --eol`, verify attributes with `git check-attr`, and review the staged diff before committing. Renormalize updates the current index; it does not automatically add untracked files and does not rewrite past history.

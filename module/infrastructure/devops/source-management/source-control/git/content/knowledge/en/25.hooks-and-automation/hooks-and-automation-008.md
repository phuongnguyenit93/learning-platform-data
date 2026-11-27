# Using Git in Scripts with git status --porcelain and NUL Delimiters

Automation scripts often need to know which files in a repository have changed, which files are untracked, and whether conflicts exist. The human-oriented `git status` command prints readable output, yet its formatting can vary based on configuration, colors, path quoting, and terminal width. When writing scripts, use the **porcelain format** designed for machine parsing.

For filenames containing spaces, tabs, quotes, or newline characters, line-by-line parsing can still corrupt data. The `-z` option tells Git to terminate each pathname field with a NUL byte. Because filenames on standard filesystems cannot contain a NUL byte, it serves as a safe delimiter for scripts to read paths intact.

## 1. Why Should Scripts Use Porcelain?

The default output of:

```bash
git status
```

is optimized for humans. Git may group files by section, add colors, abbreviate details, or quote filenames depending on configuration. Scripts relying on phrases like `Changes to be committed` or `Untracked files` easily break when Git changes presentation or when the environment uses a different locale or configuration.

Use:

```bash
git status --porcelain
```

Git returns a shorter, more stable format intended for scripts. `--porcelain` is currently equivalent to `--porcelain=v1`. When writing automation, specify the version explicitly:

```bash
git status --porcelain=v1
```

Pinning the version tells readers the exact record structure the script parses. Git also offers porcelain v2 with richer metadata fields; choose v1 or v2 deliberately and write a parser matching that exact version.

Porcelain only changes output formatting. It does not automatically stage files, commit, modify the working tree, or replace content inspection commands.

## 2. Reading the Porcelain v1 Structure

A typical porcelain v1 record has the form:

```text
XY PATH
```

The two characters `X` and `Y` describe the path's status:

- `X`: status in the index, compared against the `HEAD` commit.
- `Y`: status in the working tree, compared against the index.

Example:

```text
 M src/App.java
M  README.md
A  src/NewService.java
?? tmp/output.txt
D  old-config.yml
```

Interpretation:

| Code | Meaning |
|---|---|
| ` M` | Tracked file modified in working tree, change not yet staged |
| `M ` | File modification has been staged in the index |
| `MM` | File has part of its changes staged and was subsequently modified again in the working tree |
| `A ` | New file has been staged |
| `D ` | File has been deleted and the deletion is staged |
| ` D` | Tracked file deleted in working tree, not yet staged |
| `??` | Untracked file |
| `!!` | Ignored file; appears only when ignored files are requested |

Common status characters include:

- Space: no change on the corresponding side.
- `M`: modified.
- `A`: added.
- `D`: deleted.
- `R`: renamed.
- `C`: copied.
- `U`: unmerged.
- `?`: untracked or special status per format.
- `!`: ignored.

For conflicts, porcelain v1 can output pairs such as `DD`, `AU`, `UD`, `UA`, `DU`, `AA`, and `UU`. They indicate conflict states between the index and the working tree; scripts should generally treat any status containing `U` or known unmerged codes as requiring manual resolution.

Never check only a single character at the first position. Read both columns to distinguish staged changes from unstaged changes.

## 3. Why Is a NUL Delimiter Needed?

Valid filenames can contain spaces, tabs, and newline characters. For example, all of the following names can appear in a repository:

```text
notes meeting.txt
reports/line
break.txt
quotes/"draft".md
```

If a script splits output by lines, a file with a newline in its name will be misread as two records. If it splits by whitespace, a filename with spaces will be broken into multiple tokens.

Use the `-z` option:

```bash
git status --porcelain=v1 -z
```

With `-z`:

- Each record is terminated by a NUL byte (`\0`), not a newline.
- Paths are not quoted or escaped according to `core.quotePath`; Git emits raw pathname bytes.
- For rename/copy records, `->` is omitted and the order of the two pathnames is reversed compared to normal display: the destination path comes first, followed by the source path, each terminated by NUL.

A NUL byte cannot appear inside filenames on filesystems supported by Git in normal usage, so parsers can rely on it as an unambiguous boundary. This ensures proper handling of filenames containing newlines, tabs, spaces, quotes, or non-UTF-8 bytes.

A command commonly used in scripts:

```bash
git status --porcelain=v1 -z --untracked-files=all
```

`--untracked-files=all` requests listing each untracked file individually instead of collapsing untracked directories. This is helpful when automation must make per-file decisions.

## 4. Understanding Rename and Copy Records with -z

Without `-z`, a rename record is typically displayed as:

```text
R  old-name.txt -> new-name.txt
```

When using `-z`, Git omits the `->` string and reverses the order of the two paths:

```text
R  new-name.txt\0old-name.txt\0
```

In the representation above, `\0` denotes an actual NUL byte. The first path is the new/destination name; the following path is the old/source name.

Therefore, a parser cannot assume every record always contains only one pathname. Whenever the two status characters contain `R` or `C`, read an additional NUL-delimited pathname to obtain the source path.

Git can detect renames based on configuration and file content. If automation does not need to distinguish renames and prefers simpler delete/add changes, rename detection can be disabled:

```bash
git status --porcelain=v1 -z --no-renames
```

This is a script-logic choice. If you need to preserve rename relationships for syncing or auditing, keep rename detection enabled and handle both pathnames.

## 5. Useful Status Options for Automation

| Option | Purpose |
|---|---|
| `--porcelain=v1` | Select machine-readable format v1 |
| `--porcelain=v2` | Select machine-readable format v2 with richer metadata |
| `-z` | Use NUL as the pathname/record terminator |
| `--untracked-files=all` | List every untracked file individually |
| `--ignored` | Include ignored files |
| `--ignore-submodules=none` | Show all submodule changes when checking |
| `--no-renames` | Disable rename detection; changes are represented more simply |
| `--branch` | Add branch metadata in porcelain v2 |
| `--` | End options and start pathspecs |

Example checking only a single directory:

```bash
git status --porcelain=v1 -z --untracked-files=all -- src/
```

Example including ignored files:

```bash
git status --porcelain=v1 -z --untracked-files=all --ignored
```

Example forcing display of status inside submodules:

```bash
git status --porcelain=v1 -z --ignore-submodules=none
```

Include only options suited to your goal. For instance, if a script only needs tracked changes to run tests, listing ignored files may be unnecessary. If cleaning or reporting untracked files, use `--untracked-files=all`.

## 6. Parsing NUL-Delimited Output in Bash

In Bash, `read` can read up to a NUL byte using `-d ''`. Combine with `-r` to preserve backslashes in filenames.

Example script reading porcelain v1, identifying untracked/ignored files, and handling renames/copies:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo=${1:-.}
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

# Write raw byte output to a file; do not store NUL in shell variables.
git -C "$repo" status --porcelain=v1 -z \
  --untracked-files=all --ignored > "$tmp"

while IFS= read -r -d '' record; do
  # First two characters are XY; the third character is the separating space.
  xy=${record:0:2}
  path=${record:3}

  case "$xy" in
    "??")
      printf 'untracked: %q\n' "$path"
      ;;
    "!!")
      printf 'ignored: %q\n' "$path"
      ;;
    *R*|*C*)
      # With -z, the first pathname is destination; the next pathname is source.
      if ! IFS= read -r -d '' source_path; then
        printf 'Missing source pathname for rename/copy\n' >&2
        exit 1
      fi
      printf '%s: %q -> %q\n' "$xy" "$source_path" "$path"
      ;;
    *)
      printf '%s %q\n' "$xy" "$path"
      ;;
  esac
done < "$tmp"
```

Several points to note:

- The script writes output to a temporary file first to check `git status`'s exit code. If Git fails, `set -e` halts the script before the parser runs.
- Avoid command substitution like `output=$(git status -z)` because shells cannot store NUL bytes in variables.
- `IFS= read -r -d ''` reads the raw pathname up to NUL; `-r` prevents backslash interpretation.
- `%q` prints pathnames safely escaped in Bash logs, making newlines or tabs visible.
- For renames/copies, the parser reads the second pathname field. Skipping this field would cause the next iteration to misread the source path as a new record.

If distinguishing renames/copies is unnecessary, add `--no-renames` to the status command and remove the branch reading the second pathname. Every record then has exactly one pathname.

## 7. Parsing in Python While Preserving Pathnames

Python should capture stdout as raw bytes rather than converting to strings and splitting by lines. `subprocess.run` with `stdout=subprocess.PIPE` preserves NUL bytes and pathname bytes.

Example porcelain v1 parser:

```python
import os
import subprocess

result = subprocess.run(
    [
        "git", "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored",
    ],
    check=True,
    stdout=subprocess.PIPE,
)

# Each element is bytes; pathnames are never split by newlines.
records = result.stdout.split(b"\0")
if records and records[-1] == b"":
    records.pop()

i = 0
while i < len(records):
    record = records[i]
    i += 1

    if len(record) < 3 or record[2:3] != b" ":
        raise ValueError(f"Unexpected porcelain record: {record!r}")

    xy = record[:2].decode("ascii")
    path = record[3:]

    if "R" in xy or "C" in xy:
        if i >= len(records):
            raise ValueError("Missing source path for rename/copy")
        source_path = records[i]
        i += 1
        print(
            f"{xy}: {os.fsdecode(source_path)!r} "
            f"-> {os.fsdecode(path)!r}"
        )
    else:
        print(f"{xy} {os.fsdecode(path)!r}")
```

`check=True` makes Python raise an error if Git returns a non-zero exit code. `split(b"\0")` splits on NUL bytes, unaffected by newlines in pathnames. `os.fsdecode` decodes pathname bytes using the environment's filesystem encoding; the example uses `repr` so newlines and special characters are clearly visible.

If an application needs to store or pass pathnames to another command, keep them as bytes or use APIs taking an argument list rather than interpolating pathnames into a shell command string.

## 8. Porcelain v2: When Richer Metadata Is Needed

Porcelain v2 provides a more detailed structure than v1. You can request:

```bash
git status --porcelain=v2 -z --branch
```

The output has these primary record types:

| Record Type | Meaning |
|---|---|
| `#` | Header metadata, such as branch OID, branch name, upstream, and ahead/behind |
| `1` | Ordinary changed entry for a path |
| `2` | Rename or copy; record includes additional source/destination info |
| `u` | Unmerged path in a conflict state, with metadata for stages |
| `?` | Untracked path |
| `!` | Ignored path when requested |

Type `1` records contain XY status, submodule info, modes, and related OIDs. Type `2` records add rename/copy scores and the second pathname. Type `u` records contain modes/OIDs for conflicting sides. Header `#` lines appear when requesting metadata like `--branch`.

Porcelain v2 is useful when automation needs to distinguish record types, submodule status, or retrieve ahead/behind counts without running multiple separate commands. However, the parser must understand each record type accurately; never apply a v1 parser to v2 because v2 uses different record prefixes and field counts.

With `-z`, pathnames in v2 records are still terminated by NUL. For renames/copies, destination and source pathnames are separated. Consult the v2 format specification and write a parser per record type rather than arbitrarily splitting strings on whitespace.

If you only need to know which files changed to run a formatter or tests, porcelain v1 is usually sufficient and simpler to parse. If you need to report detailed branch, submodule, and conflict states, consider v2.

## 9. Unsafe Parsing Patterns

Avoid the following patterns:

```bash
# Unsafe: filenames with spaces/newlines get split
for file in $(git status --short); do
  echo "$file"
done

# Unsafe: line-by-line reading, pathnames may contain newlines
git status --porcelain | while read line; do
  ...
done

# Unsafe: shell variables cannot hold NUL bytes
output=$(git status --porcelain -z)
```

Specific problems:

- Command substitution strips trailing newlines, and shell word splitting breaks pathnames apart.
- `read` reads up to a newline by default, not NUL.
- Filenames can contain tabs or newlines, so one line does not equal one file.
- NUL bytes cannot be preserved inside ordinary shell variables.
- If a parser assumes every record has a single pathname, renames/copies throw off all subsequent parsing.

The safe approach is using `-z`, reading up to NUL, and handling the full record structure. If you prefer not to write a custom parser, invoke Git through an API or library supporting porcelain/NUL output and keep pathnames as argument arrays.

## 10. git status Exit Code Does Not Mean Clean/Dirty

A common automation mistake is treating exit code `0` from `git status` as meaning the working tree is clean. In reality, `git status` normally returns exit code `0` even when files are modified, staged, untracked, or conflicted. Stdout content is what tells you the repository's state.

Example:

```bash
if git status --porcelain=v1 -z > status.bin; then
  # Status command succeeded; must read status.bin to see if changes exist.
  :
else
  echo "Unable to read Git status" >&2
  exit 1
fi
```

If the output file is empty, there are no records within the requested options scope. If records exist, inspect their statuses to determine what kind of changes they represent. For example, with `--ignored`, ignored files also produce `!!` records; hence "non-empty output" does not necessarily mean there are changes to commit.

It is best to clarify your exact objective before checking:

- Want to know if tracked/untracked changes need handling? Omit `--ignored`, or filter out `!!`.
- Want to know if ignored files exist? Add `--ignored` and match `!!`.
- Want to block the pipeline if conflicts exist? Parse XY and detect unmerged states.
- Want to know if Git ran the status command successfully? Check the exit code separately.

Never use a single boolean condition for all purposes.

## 11. Scope of Checks and Configuration Effects

Status results depend on the options you pass and certain repository settings:

- `status.showUntrackedFiles` affects how untracked files are shown when not explicitly specified.
- `status.renames` affects rename detection.
- `submodule.<name>.ignore` can affect how `git status` reports submodule changes; `diff.ignoreSubmodules` affects diff commands.
- Pathspecs restrict which paths are inspected.
- `--ignored` alters the set of returned records.

For automation requiring predictable results, specify key options explicitly:

```bash
git status --porcelain=v1 -z \
  --untracked-files=all \
  --ignore-submodules=none
```

If you want to omit ignored files, do not add `--ignored`. If checking only a specific directory, append `--` followed by the pathspec:

```bash
git status --porcelain=v1 -z -- src/
```

Use `git config --show-origin --get-regexp '^status\.'` to inspect status settings that might affect output. Even though porcelain output is stable for scripts, different flags still yield different sets of paths.

## 12. Workflow for Designing Scripts That Read Git Status

A safe workflow applicable to Bash, Python, or other automation tools:

1. **Choose the porcelain version.** Use `--porcelain=v1` for a simpler parser; choose v2 when detailed metadata is needed.
2. **Choose the scope.** Decide whether untracked files, ignored files, submodules, and pathspecs are needed.
3. **Use NUL delimiters.** Add `-z` whenever pathnames are passed to a program.
4. **Check Git's exit code.** Separate command execution failures from repository having changes.
5. **Parse per record.** Read both XY columns and handle renames/copies with their second pathname.
6. **Preserve pathnames.** Do not split on whitespace/newlines and do not store NUL in shell variables.
7. **Act within strict bounds.** If the script stages, deletes, or formats files, act only on clearly classified paths.
8. **Verify afterward.** Re-run porcelain status to confirm the final state.

A status-reporting script should run with minimal privileges: read the repository and print results. If a script automatically stages or commits, isolate that step into dedicated logic, log selected files clearly, and provide a dry-run mode where appropriate.

## 13. Common Mistakes When Using Porcelain

| Symptom | Cause | Fix |
|---|---|---|
| Filenames with spaces split into parts | Splitting on whitespace or shell word splitting | Use `-z` and read pathnames up to NUL |
| Filenames with newlines break record parsing | Reading line by line | Use NUL-delimited records |
| Renames produce a "weird" extra record | Parser reads only one pathname | When XY contains R/C, read the additional source pathname |
| Unicode names appear escaped | Output omits `-z` or `core.quotePath` is active | Use `-z` for machine data; do not rely on display escaping |
| Script thinks repo is clean despite modified files | Checking only exit code | Parse stdout; exit code only shows whether the command succeeded |
| Untracked files in directories are not listed | Git collapses untracked directories | Use `--untracked-files=all` |
| Changes inside submodules are missing | Ignore setting filters status | Use `--ignore-submodules=none` and inspect inside submodules |
| v1 parser fails on v2 output | Mismatched schema | Pin `--porcelain=v1` or write a separate v2 parser |

## Conclusion

Use `git status --porcelain=v1 -z` so scripts receive repository status in a stable format with NUL-delimited pathnames. Read both XY columns to distinguish the index from the working tree; handle rename/copy records specially because they carry two pathnames whose order is reversed under `-z`. Never parse by lines, whitespace, or command substitution. Always evaluate the exit code separately from stdout content, choose untracked/ignored/submodule scopes explicitly, and re-verify status after automation performs actions.

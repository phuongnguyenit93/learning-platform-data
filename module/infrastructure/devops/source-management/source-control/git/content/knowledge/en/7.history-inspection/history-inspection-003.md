# Formatting git log Output for Quick Reading or Data Extraction

Git history can contain hundreds or thousands of commits. If you only use the default `git log`, you often have to read more information than needed; if you want to generate changelogs, reports, or feed data into scripts, the output needs a consistent structure.

Git provides presets such as `--oneline`, `--stat`, and `--graph`, along with `--pretty=format:` for custom formatting per commit. You can choose which fields to display, such as OID, author, date, subject, parents, and refs pointing to the commit. This article focuses on formatting and controlling output, while distinguishing commit selection from commit presentation.

## 1. Separating Commit Selection from Output Formatting

A `git log` command typically has two parts:

- **Revisions and filters** determine which commits are included in the results.
- **Formatting options** determine how each commit is displayed.

Example:

```bash
git log --since="2026-01-01" --author="Lan" --pretty=oneline
```

`--since` and `--author` filter the commit set. `--pretty=oneline` formats the output of the selected commits.

Some commonly used filters:

| Option | Meaning |
|---|---|
| `-n 10` or `-10` | Limit to at most 10 commits |
| `--since="2 weeks ago"` | Select commits with committer date from this timestamp onward |
| `--until="2026-11-01"` | Limit up to this timestamp |
| `--author="Lan"` | Filter by author identity |
| `--committer="Maintainer"` | Filter by committer identity |
| `--grep="fix"` | Search string in commit messages |
| `--all` | Traverse commits reachable from all known refs |
| `-- path/to/file` | Restrict history by path |

Example viewing the 15 most recent commits for a file:

```bash
git log -15 --oneline -- src/auth/LoginService.java
```

Example finding commits by an author whose message mentions parser:

```bash
git log --author="Lan" --grep="parser" --oneline
```

If no commit matches, Git prints nothing. Changing the format does not alter the selected set of commits.

## 2. Presets for Quick Reading

Git includes built-in presentation formats. Common ones:

| Option | Content |
|---|---|
| `--oneline` | Abbreviated OID and subject on one line |
| `--pretty=short` | Author info and commit message |
| `--pretty=medium` | Default format with author, date, and message |
| `--pretty=full` | Adds committer |
| `--pretty=fuller` | Shows both author date and committer date |
| `--pretty=reference` | Compact reference format suitable for citing commits |
| `--pretty=raw` | Displays commit object contents in raw format |

View compact history:

```bash
git log --oneline -10
```

Example output:

```text
a31f8d2 Add login validation
c2e14b9 Fix token expiration
7a9d310 Create authentication service
```

`--oneline` corresponds to the `oneline` format combined with an abbreviated OID. It is very useful for quick scanning, though it does not contain enough fields for detailed reporting.

View complete author and committer information:

```bash
git log --pretty=fuller -5
```

`author` is the person recorded as creating the change; `committer` is the person who created the current commit object. The two people and dates can differ, for example when a maintainer cherry-picks a commit written by someone else.

## 3. Displaying Branches and Commit Relationships with a Graph

When multiple branches evolve in parallel, a linear list can obscure merge relationships. Combine `--graph`, `--decorate`, and `--oneline`:

```bash
git log --graph --oneline --decorate --all
```

Example:

```text
* a31f8d2 (HEAD -> main, origin/main) Merge feature/login
|\
| * 51c3e90 (feature/login) Add login validation
| * 82ad1f4 Add token service
* | c2e14b9 Fix token expiration
|/
* 7a9d310 Initial project
```

Meaning:

- `--graph` draws branches using ASCII characters.
- `--decorate` displays branch, tag, and ref names associated with commits.
- `--all` tells Git to traverse commits reachable from all known refs in the repository.
- `--oneline` keeps each commit on a single line so the graph stays readable.

You can control how decorations are displayed:

```bash
git log --decorate=short --oneline --all
git log --decorate=full --oneline --all
git log --no-decorate --oneline -10
```

`short` typically shows names like `main` or `origin/main`; `full` shows full ref names like `refs/heads/main`. Use `--no-decorate` when you need output without ref labels.

If you only want to inspect history following the first parent of the main branch:

```bash
git log --first-parent --oneline --graph main
```

This option follows only the first parent at merge commits, helping review main integration milestones. It is not the complete history of every merged branch.

## 4. Custom Formatting with --pretty=format

When you need exact control over output fields, use:

```bash
git log --pretty=format:"<format>"
```

`--format` is shorthand for `--pretty=format:`. You can combine literal text with placeholders starting with `%`.

Example displaying abbreviated OID, date, author, and subject:

```bash
git log -10 --date=short --pretty=format:"%h %ad | %an | %s"
```

Sample output:

```text
a31f8d2 2026-10-20 | Lan Nguyen | Add login validation
c2e14b9 2026-10-18 | Minh Tran | Fix token expiration
7a9d310 2026-10-15 | Lan Nguyen | Create authentication service
```

This format is suited for quick scanning because every commit has the same field order. In scripts, specify an explicit format instead of relying on default output that can vary by configuration.

## 5. Essential Placeholders

Placeholders extract specific fields from commits. Commonly used ones:

| Placeholder | Value |
|---|---|
| `%H` | Full commit OID |
| `%h` | Abbreviated OID |
| `%T` / `%t` | Full / abbreviated tree OID |
| `%P` / `%p` | Full / abbreviated parent OIDs |
| `%an` / `%aN` | Author name / author name respecting mailmap |
| `%ae` / `%aE` | Author email / author email respecting mailmap |
| `%cn` / `%cN` | Committer name / committer name respecting mailmap |
| `%ce` / `%cE` | Committer email / committer email respecting mailmap |
| `%s` | Subject, i.e., first line of commit message |
| `%f` | Sanitized subject suitable for filenames |
| `%b` | Commit message body |
| `%B` | Full commit message, including subject and body |
| `%N` | Commit notes |
| `%d` | Ref decorations, typically in parentheses |
| `%D` | Ref decorations without parentheses |
| `%n` | Newline |
| `%xNN` | Print byte with hex code NN, e.g. `%x09` is tab |

Example:

```bash
git log -5 --pretty=format:"%H%nParents: %P%nAuthor: %an <%ae>%nSubject: %s%n"
```

The output shows OID, parents, author identity, and subject on separate lines.

Mailmap-aware placeholders like `%aN` or `%aE` help normalize identities when the same person uses multiple name/email variants. If the repository lacks a matching mailmap, the output matches the original field.

Do not confuse author with committer: use `%an`, `%ae`, `%aI` for author; use `%cn`, `%ce`, `%cI` for committer.

## 6. Date Formatting

Git stores timestamps for both author and committer. Date placeholders support multiple representations:

| Placeholder | Meaning |
|---|---|
| `%ad` | Author date formatted according to `--date` |
| `%aD` | Author date in RFC2822 format |
| `%ar` | Relative author date, e.g. `2 weeks ago` |
| `%at` | Author timestamp as Unix epoch |
| `%aI` | Author date in strict ISO 8601 format |
| `%as` | Author date in `YYYY-MM-DD` format |
| `%cd` | Committer date according to `--date` |
| `%cD` | Committer date in RFC2822 format |
| `%cr` | Relative committer date |
| `%ct` | Committer timestamp as Unix epoch |
| `%cI` | Committer date in strict ISO 8601 format |
| `%cs` | Committer date in `YYYY-MM-DD` format |

Select the date format with `--date`:

```bash
git log -5 --date=short --pretty=format:"%h %ad %s"
git log -5 --date=relative --pretty=format:"%h %ad %s"
git log -5 --date=iso-strict --pretty=format:"%h %ad %s"
```

- `short` prints dates as year-month-day.
- `relative` prints elapsed time relative to when the command runs.
- `iso-strict` prints ISO 8601 format with timezone offset.

If you need consistent data across machines and pipelines, prefer `%aI` or `%cI` over relative dates. `relative` changes depending on query time and is unsuitable for long-term reference data.

Example placing author date and committer date side by side:

```bash
git log -5 --pretty=format:"%h | author=%aI | committer=%cI | %s"
```

This is useful when investigating commits created from an older change that was cherry-picked or reapplied at a different time.

## 7. Multi-Line Formats and Record Separation

You can use `%n` for newlines and `%xNN` for control characters:

```bash
git log -3 --pretty=format:"Commit: %H%nAuthor: %an <%ae>%nDate: %aI%nSubject: %s%n"
```

If you want each commit separated by a blank line:

```bash
git log -3 --pretty=format:"%h %s%nAuthor: %an%nDate: %aI%n"
```

`format:<format>` and `tformat:<format>` differ in record separation:

- `format:<format>` uses the format string and places separators between commits.
- `tformat:<format>` uses the format string and places a terminator after every commit. If the format does not end with a newline itself, `tformat` still terminates the record with a newline.

Example:

```bash
git log -3 --pretty=tformat:"%h %s"
```

For line-oriented output, `tformat` is often easier to process because every commit gets its own trailing newline, including the last commit.

You can also write:

```bash
git log -3 --format="%h %s"
```

This is an alias for `--pretty=format:`; do not mistake the `--format` option name for a structured data format such as JSON or CSV. It is strictly Git's placeholder substitution mechanism.

## 8. Combining Colors and Alignment

Git can colorize placeholders to make output easier to scan:

```bash
git log -10 --pretty=format:"%C(yellow)%h%C(reset) %C(green)%ad%C(reset) %s" --date=short
```

Common forms:

- `%C(yellow)`, `%C(green)`, `%C(red)`: select color.
- `%C(bold)`: enable bold text.
- `%C(reset)`: reset to default color.
- `%C(auto)`: let Git decide when to apply color.

You can also use alignment in custom formats:

```bash
git log -10 --pretty=format:"%C(yellow)%<(8)%h%C(reset) %<(12,trunc)%an %s"
```

Alignment placeholders such as `%<`, `%>`, or `%><` reserve width for the next field. The `trunc` option truncates content when it exceeds the allocated width.

Colors are helpful for interactive terminals. When redirecting output to files or pipelines, disable color:

```bash
git log --no-color --pretty=format:"%h %ad %s" --date=short
```

Do not write ANSI color codes into CSV files or machine-readable data unless intentionally required.

## 9. Combining Formats with File Statistics

`git log` can display commit metadata together with change statistics:

```bash
git log --stat -5
git log --shortstat -5
git log --numstat -5
```

| Option | Content |
|---|---|
| `--stat` | Filenames and added/deleted line bar chart |
| `--shortstat` | Single summary line with file count, insertions, and deletions |
| `--numstat` | Added/deleted line counts per file, more convenient for scripts |
| `--summary` | Summary of create/delete modes, renames, and metadata changes |

If you only need a list of changed files:

```bash
git log --name-only --format="%h %s" -5
```

If you also need file statuses:

```bash
git log --name-status --format="%h %s" -5
```

Common status codes include `A` (added), `M` (modified), `D` (deleted), `R` (renamed), and `C` (copied). Rename/copy detection relies on content similarity and Git options, so it is not fixed rename metadata stored inside the commit.

You can suppress patch output and keep only metadata:

```bash
git log --no-patch --format="%h %ad %s" --date=short -5
```

If you want file statistics, run `--stat` as needed:

```bash
git log --stat -5
```

`--no-patch` is useful when you want commit reports without printing full diffs.

## 10. Extracting Only Required Fields for Reports

Example commit report with OID, date, author, and subject:

```bash
git log -20 --date=short --format="%H,%ad,%an,%s"
```

The output looks like CSV, though it is not safe CSV in every case. Author names or subjects can contain commas, quotes, or newlines; feeding it straight into a spreadsheet can split columns incorrectly.

If using a tab delimiter:

```bash
git log -20 --format="%H%x09%aI%x09%an%x09%s"
```

`%x09` inserts a tab character. This produces TSV convenient for internal data when field contents are controlled. However, tabs can still appear in commit data; choose an appropriate delimiter and escape/quote values when high reliability is needed.

Another example extracting OID, parents, and subject for history analysis:

```bash
git log -20 --format="%H%x09%P%x09%s"
```

If you need a format that is easier to parse reliably, use a rare delimiter byte such as NUL:

```bash
git log -20 --pretty=tformat:"%H%x00%P%x00%aI%x00%an%x00%s"
```

`%x00` inserts a NUL byte between fields. The reader tool must support binary data and NUL-delimited splitting; do not use ordinary shell command substitution to hold NUL bytes because many shells strip them or cannot represent them in variables. `tformat` still appends a terminator per record, so parsers must account for the record terminator.

For long-term integrations, treat `git log --format` as a structured text interface you define, not an automatic JSON schema. Explicitly choose fields, delimiters, encoding rules, and handling for multi-line messages.

## 11. Generating a Short Changelog from Commit Messages

A simple changelog can extract commit subjects since the latest tag:

```bash
git log v2.3.0..HEAD --no-merges --pretty=format:"- %s"
```

- `v2.3.0..HEAD` selects commits reachable from HEAD but not reachable from tag `v2.3.0`.
- `--no-merges` excludes merge commits.
- `%s` extracts each commit's subject.

If you want to include abbreviated OID and author:

```bash
git log v2.3.0..HEAD --no-merges --date=short --pretty=format:"- %s (%h, %an, %ad)"
```

This is only a basic changelog. Quality depends on the project's commit message conventions. If subjects do not clearly describe changes, clean formatting cannot automatically produce accurate release notes.

If you need history ordered from oldest to newest:

```bash
git log --reverse v2.3.0..HEAD --no-merges --pretty=format:"- %s"
```

`--reverse` reverses the display order of selected commits. Verify the baseline tag and commit set before using the output for a release.

## 12. Filtering and Formatting for a Single File

You can combine a pathspec with a custom format:

```bash
git log --format="%h %ad %an %s" --date=short -- src/auth/LoginService.java
```

This command only displays commits affecting that path according to Git's path history rules.

To follow a file across a rename, you can use `--follow`:

```bash
git log --follow --format="%h %ad %s" --date=short -- src/auth/LoginService.java
```

`--follow` supports only one path and has limitations with complex histories or multiple renames. It is a rename-inference tracing mechanism, not a guarantee of finding all rename history across every graph.

If you only want the first or most recent commit affecting a file:

```bash
git log -1 --format="%H %s" -- src/auth/LoginService.java
```

You can combine `--author`, `--since`, or `--grep` to narrow down history before formatting.

## 13. Output for Scripts: Key Principles

When scripts parse `git log` output, avoid parsing default human-oriented output. Default output can change with configuration, locale, colors, or Git versions.

Recommended practices:

1. Explicitly specify required placeholders using `--format`.
2. Choose full OIDs (`%H`) when you need stable commit identifiers; do not use abbreviated OIDs as long-term data keys.
3. Use `%aI` or `%cI` when you need timestamps with timezones in strict ISO format.
4. Pick a delimiter that does not collide with data, or use NUL if the reader supports it.
5. Disable color with `--no-color`.
6. Define encoding and multi-line message handling explicitly if extracting `%b` or `%B`.
7. Handle the case where no commits match.
8. Separate commit metadata output from changed-file lists.

Example of a minimal log command for machine-readable reporting:

```bash
git log -100 --no-color --date=iso-strict --format="%H%x09%aI%x09%an%x09%s"
```

If file statuses are needed, use `--name-status` or `--numstat` and parse the multi-line structure Git outputs. Do not assume each commit always occupies a single line when file-listing flags are enabled.

For data requiring exact parsing, test against repositories containing spaces, commas, tabs, Unicode characters, or special characters in author names, subjects, and file paths. Build parsers around actual delimiters and encoding rather than visual column positions.

## 14. Advanced Placeholders and Modifiers

Beyond basic fields, format strings support several modifiers:

| Syntax | Meaning |
|---|---|
| `%C(...)` | Control color |
| `%m` | Boundary/left/right marker in certain traversal modes |
| `%w(width,indent1,indent2)` | Control message wrapping |
| `%<(N)` | Left-align next field to minimum width N, padded on the right |
| `%<(N,trunc)` | Truncate next field if it exceeds width N |
| `%>(N)` | Right-align next field within width N |
| `%><(N)` | Center next field within width N |
| `%xNN` | Insert byte by hex code |
| `%n` | Newline |

Example wrapping the body:

```bash
git log -3 --pretty=format:"%h %s%n%w(72,4,4)%b%n"
```

Example aligning OID and author name fields:

```bash
git log -10 --pretty=format:"%<(10)%h %<(20,trunc)%an %s"
```

Not every placeholder is meaningful in every traversal mode. For example, `%m` is useful with multi-sided selection options like `--left-right` or `--boundary`; in regular logs, it may not provide useful information.

## 15. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| Branch/tag missing from log | Only traversing from HEAD or refs not fetched | Use `--all` and fetch remote if needed |
| OID is truncated | Using `--oneline` or `%h` | Use `%H` when full OID is needed |
| Author and committer dates differ | Commit was cherry-picked, rebased, or recreated | Display both `%aI` and `%cI` |
| Multi-line output is hard to read | Format lacks a clear separator | Use `%n`, `format:`, or `tformat:` intentionally |
| CSV columns shift | Subject/name contains commas or quotes | Use an appropriate delimiter and quote/escape data |
| Script fails on NUL | Shell variables cannot hold NUL bytes | Use files/pipes and binary-safe parsers |
| Color codes appear in output file | Git colorizes terminal output automatically | Use `--no-color` |
| File stats mix into message | Combining `--stat`/`--name-status` with format without accounting for output layout | Use `--no-patch` or parse the stats section separately |
| Changelog misses commits | Wrong range, unfetched tag, or overly narrow filter | Check `git log <tag>..HEAD` and refs |
| `--follow` misses older history | Rename detection has limits | Inspect individual rename milestones and relevant tree diffs |

## 16. Practical Workflow: Creating a Release History Report

Suppose the team needs a report of commits since `v2.3.0` to prepare a release.

**Step 1: Update refs and verify the tag.**

```bash
git fetch --all --tags
git show -s --format="%H %s" v2.3.0
```

**Step 2: Review the selected commit list.**

```bash
git log --oneline --decorate v2.3.0..HEAD
```

Confirm the range matches the release branch and baseline tag.

**Step 3: Generate a human-readable report.**

```bash
git log --reverse --no-merges --date=short --format:"%h | %ad | %an | %s" v2.3.0..HEAD
```

**Step 4: Inspect changed file statistics.**

```bash
git log --stat --oneline v2.3.0..HEAD
```

**Step 5: Export consistent data for scripts.**

```bash
git log --reverse --no-merges --no-color --format="%H%x09%cI%x09%an%x09%s" v2.3.0..HEAD
```

If writing data to a file or sending it to another system, define encoding, delimiters, quoting rules, and handling for subjects containing separator characters before automating.

## 17. Checklist Before Using git log for Reporting

- [ ] Defined revision range and commit filters.
- [ ] Fetched required branches/tags if data comes from remote.
- [ ] Selected appropriate preset or custom format.
- [ ] Used `%H` if full commit identifiers are required.
- [ ] Distinguished author from committer.
- [ ] Used ISO dates if data will be compared across environments.
- [ ] Checked `--graph`, `--decorate`, or `--all` if branch/ref relationships are needed.
- [ ] Selected `--stat`, `--numstat`, or `--name-status` when file details are needed.
- [ ] Defined delimiters and newline/NUL handling for scripts.
- [ ] Disabled color and tested the zero-results case.

## Conclusion

Use `--oneline`, `--graph`, and `--decorate` to scan history quickly; use `--pretty=fuller` when you need to distinguish author and committer; use `--format` with placeholders like `%H`, `%an`, `%aI`, and `%s` to control output fields. Combine `--stat`, `--numstat`, or `--name-status` when file change metrics are needed. If the output is consumed by scripts, explicitly define delimiters, encoding, date formats, and multi-line handling; do not parse default human-readable output.

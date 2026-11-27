# Filtering Commits by Author, Time, Message, and Path

Git history can contain thousands of commits across many contributors, branches, and development phases. When you need to find who made a change, when a change appeared, or whether a commit mentions a bug ID or file, you do not have to read the entire history. The **git log** command provides filters to narrow down the commit list by metadata and paths.

In the **History Inspection** chapter of the **SOURCE_CONTROL_GIT** module, this lesson guides you through filtering commits by author, committer, time, message content, and affected files/directories. You will learn how to combine conditions, distinguish filter criteria from output formatting, handle file rename history, and avoid wrong conclusions when timestamps or display names do not reflect the full origin of a change.

After this lesson, you will be able to:

- Find commits by author or committer.
- Restrict history using relative or absolute timestamps.
- Search for commits containing keywords in the subject, body, or trailers.
- Filter commits touching a specific file or directory.
- Combine multiple filters and understand how Git evaluates conditions.
- Use revision ranges to scope branches before filtering.
- Customize output to view author, date, message, and changed files.
- Track a file's history after a rename using --follow.
- Recognize the limitations of metadata filtering and verify results before drawing conclusions.

## 1. Getting Started with git log

Basic command:

~~~bash
git log
~~~

Git displays commits reachable from HEAD in the default history order, usually showing commit hash, author, date, and message. You can use the compact form:

~~~bash
git log --oneline
~~~

To view the branch graph:

~~~bash
git log --oneline --graph --decorate --all
~~~

Before filtering, define the history scope. If no revision or revision range is passed, git log normally starts from HEAD. Use --all to view commits reachable from all refs that Git includes in that scope, including relevant branches and tags.

Example:

~~~bash
git log main
git log origin/main
git log main..feature/payment
git log --all --oneline
~~~

The command main..feature/payment finds commits reachable from feature/payment but not reachable from main. Author, time, message, or path filters will then further narrow down this commit range.

## 2. Filtering by Author with --author

The author is the person recorded as having originally written the change in a commit. Use --author to display only commits whose author field matches a pattern:

~~~bash
git log --author="An Nguyen"
~~~

The pattern can match the name or email in the author header. For example:

~~~bash
git log --author="an@example.com"
git log --author="An Nguyen <an@example.com>"
~~~

--author uses regular expressions, not exact string equality. If you want to match a literal string, you can use --fixed-strings with --grep for messages; for author, write a sufficiently specific pattern and verify the output.

### Searching by Partial Name or Email

~~~bash
git log --author="example.com"
git log --author="^An Nguyen"
~~~

The first pattern can match multiple email addresses sharing the same domain. The second pattern uses the regex ^ anchor to require the name to start with that string. Results depend on the actual author data stored in commits.

### Distinguishing Author and Committer

A commit may be written by Alice but cherry-picked, rebased, or applied by Bob. In that case, author and committer differ.

~~~bash
git log --author="Alice"
git log --committer="Bob"
~~~

- --author filters by the author header.
- --committer filters by the committer header.

If you want to find who brought the commit into the current history, committer can be useful. If you want to find who is recorded as the original author of the change, use author.

Note: --author does not automatically search trailers like Co-authored-by in the commit message. It only inspects the commit's author field. To search co-authors listed in the message, use --grep.

## 3. Filtering by Committer with --committer

Use --committer to find commits whose committer info matches a pattern:

~~~bash
git log --committer="build-bot"
git log --committer="ci@example.com"
~~~

This filter is useful when:

- One person applies a patch written by someone else.
- Commits were created via git am or cherry-pick.
- CI/bots create automated commits.
- You need to investigate who or which process created the current commit object.

Do not infer the original author solely from the committer. Display both fields when you need to cross-check:

~~~bash
git log --format="%h | author=%an <%ae> | committer=%cn <%ce> | %s"
~~~

## 4. Filtering by Time

Git supports options to restrict commits by date.

| Option | Meaning |
| --- | --- |
| --since or --after | Show only commits newer than the timestamp |
| --until or --before | Show only commits older than the timestamp |
| --since-as-filter | Filter by the since bound while continuing to traverse the full range instead of stopping early at an older commit |

Example finding commits after January 1, 2026:

~~~bash
git log --since="2026-01-01"
~~~

Finding commits before April 1, 2026:

~~~bash
git log --until="2026-04-01"
~~~

Restricting to a time range:

~~~bash
git log --since="2026-01-01" --until="2026-03-31"
~~~

The --after option is equivalent to --since; --before is equivalent to --until.

### Using Relative Times

Git understands various time expressions:

~~~bash
git log --since="2 weeks ago"
git log --since="yesterday"
git log --since="last month"
git log --since="3 days ago"
~~~

Relative times are convenient when investigating recent work. Results depend on when the command is run and how Git interprets the environment's timezone.

### Using Absolute Timestamps with Timezones

In reports or scripts that may run across different machines, specify the date, time, and UTC offset:

~~~bash
git log --since="2026-03-01T00:00:00+07:00" --until="2026-04-01T00:00:00+07:00"
~~~

ISO 8601 with explicit offsets avoids confusion between local time and UTC. Git uses its date parser to interpret values; use a consistent format in scripts and verify on the Git version in your deployment environment.

### Notes on Author Date vs. Committer Date

Time filters in git log rely on commit dates as Git traverses history, typically the committer date. A commit with an old author date that was cherry-picked today may show up in a recent time window because its committer date is new.

You can inspect both dates:

~~~bash
git log --format="%h author=%aI committer=%cI %s"
~~~

Do not use timestamps as sole proof of historical order. The parent graph is what determines which commit is an ancestor of which.

### --since-as-filter When Commit Dates Are Non-Monotonic

Git may stop traversing a branch of history when it encounters a commit with a committer date older than --since. This is usually fast, but history can contain imported or created commits whose dates do not follow graph order. When you need to traverse the entire range and then filter by timestamp, use:

~~~bash
git log --since-as-filter="2026-01-01"
~~~

This option does not change commit dates; it changes traversal behavior so earlier commits in the graph are not skipped simply because an older-dated commit was encountered.

## 5. Filtering by Commit Message with --grep

A commit message can consist of a subject, body, and trailers. Use --grep to search for a pattern in the message:

~~~bash
git log --grep="fix"
git log --grep="AUTH-142"
git log --grep="breaking change"
~~~

--grep searches the entire commit message content, not just the subject line. Thus, keywords in the body or trailers can also match a commit.

### Case-Insensitive Search

~~~bash
git log -i --grep="timeout"
~~~

-i or --regexp-ignore-case makes regex matching case-insensitive.

### Searching for a Fixed String Instead of Regex

~~~bash
git log --fixed-strings --grep="fix(auth):"
~~~

--fixed-strings (short form -F) treats the --grep pattern as a literal string. This is useful when the message contains parentheses, dots, or characters with special regex meaning.

### Multiple Keywords: OR and AND

By default, multiple --grep options are combined with OR: commits matching at least one pattern are displayed.

~~~bash
git log --grep="AUTH-142" --grep="AUTH-198"
~~~

If you want commits to match all --grep patterns, add --all-match:

~~~bash
git log --all-match --grep="auth" --grep="security"
~~~

Here each pattern is still checked against the whole message. --all-match requires the commit to match every pattern passed via --grep.

### Inverting Message Search Results

~~~bash
git log --invert-grep --grep="WIP"
~~~

--invert-grep excludes commits whose message matches the pattern and keeps those that do not. This option only inverts the message grep condition, not author, date, or path filters.

### Combining Subject and Body

If you only want to display the subject:

~~~bash
git log --format="%h %s"
~~~

If you want to view the full message:

~~~bash
git log --format="%h%n%B"
~~~

Filtering with --grep still inspects the full message even when output only displays the subject.

## 6. Filtering by File or Directory

To view only commits that modified a file:

~~~bash
git log -- src/api/auth.js
~~~

The path must come after -- so Git distinguishes revisions/options from pathspecs. Without the separator, a path name might be mistaken for a revision name.

Find commits affecting a directory:

~~~bash
git log -- src/api/
~~~

Find commits affecting several files:

~~~bash
git log -- src/api/auth.js src/api/session.js
~~~

If multiple pathspecs are passed, Git shows commits with changes matching at least one specified path.

### Seeing Which Files Changed in Each Commit

~~~bash
git log --name-only -- src/api/
git log --stat -- src/api/
git log --name-status -- src/api/
~~~

- --name-only displays file names.
- --stat displays change statistics.
- --name-status displays file statuses such as A, M, D, or R.

To view the patch for each commit:

~~~bash
git log -p -- src/api/auth.js
~~~

-p or --patch shows the diff of each matching commit. If history is long, limit the commit count with -n:

~~~bash
git log -p -n 5 -- src/api/auth.js
~~~

### Tracking a File After a Rename

If a file was renamed, the new path may not show older history the way you expect. Use --follow:

~~~bash
git log --follow -- src/api/client.js
~~~

--follow attempts to continue following a single file's history when a rename is detected. This option only supports one path and has limitations with complex histories, especially across merges or branches with differing renames. Git detects renames based on content similarity rather than storing renames as separate objects.

### Advanced Pathspecs

Pathspecs can restrict matches using patterns:

~~~bash
git log -- ":(glob)**/*.js"
git log -- ":(icase)readme.md"
~~~

- :(glob) applies glob patterns according to pathspec syntax.
- :(icase) requests case-insensitive path matching.

To exclude a path from a pathspec set, use the exclude magic signature:

~~~bash
git log -- "src/" ":(exclude)src/generated/"
~~~

Advanced pathspecs are helpful in large repositories; for everyday tasks, putting explicit paths after -- is easier to read and less error-prone.

## 7. Combining Multiple Filters

You can combine author, committer, time, message, and path in the same command.

Example finding commits by An in the first quarter of 2026 whose message mentions AUTH-142 and that modified files in src/auth:

~~~bash
git log --author="An Nguyen" --since="2026-01-01" --until="2026-04-01" --grep="AUTH-142" -- src/auth/
~~~

Filter groups for author, committer, time, message, path, and revision range are generally combined with AND: a commit must satisfy each specified condition group.

Specifically when repeating certain filters:

- Multiple --grep options default to OR; use --all-match to require all grep patterns.
- Multiple --author options can match any of the specified author patterns.
- Multiple --committer options can match any of the specified committer patterns.
- Multiple pathspecs select commits touching at least one matching path.

Example finding commits by Alice or Bob:

~~~bash
git log --author="Alice" --author="Bob"
~~~

Example requiring a message to contain both keywords:

~~~bash
git log --all-match --grep="security" --grep="token"
~~~

If results are unexpected, split each condition into separate commands to see which filter excludes commits.

## 8. Scoping Branches Before Filtering

Metadata filters do not determine which branch you want to search. By default git log traverses from HEAD. Use a revision or range to select history:

~~~bash
git log main --author="An"
git log origin/main --since="1 month ago"
git log main..feature/api -- src/api/
git log --all --grep="migration"
~~~

Common scope forms:

| Revision | Scope |
| --- | --- |
| HEAD | History reachable from the current commit |
| main | History reachable from branch main |
| origin/main | History reachable from the remote-tracking branch |
| A..B | Commits reachable from B but not reachable from A |
| A...B | Symmetric difference between histories A and B |
| --all | History reachable from all refs Git includes in the all scope |

Example:

~~~bash
git log main..feature/api --author="Lan" -- src/api/
~~~

This command considers only commits in feature/api that are not in main, then filters by author and path.

To find commits dropped from the current branch that might still be held by another ref, --all can broaden the scope. If a commit is no longer reachable from any ref and has been pruned from the object database, git log cannot find it.

## 9. Customizing Output to Read Results

When filtering by multiple conditions, default output sometimes does not show enough information to verify results.

### Compact Display

~~~bash
git log --oneline --decorate
~~~

### Displaying Author, Committer, Dates, and Subject

~~~bash
git log --format="%h | %an <%ae> | %cn <%ce> | %aI | %cI | %s"
~~~

Common placeholders:

| Placeholder | Content |
| --- | --- |
| %H | Full commit hash |
| %h | Abbreviated commit hash |
| %an / %ae | Author name / email |
| %cn / %ce | Committer name / email |
| %aI | Strict ISO 8601 author date |
| %cI | Strict ISO 8601 committer date |
| %s | Subject |
| %b | Body |
| %B | Full subject and body |
| %P | Parent hash or hashes |

### Choosing How Dates Are Displayed

The --date option controls the date format in output, for example:

~~~bash
git log --date=short
git log --date=iso-strict
git log --date=relative
~~~

--date only formats the printed date; it does not change time filter behavior. Use --since/--until for filtering, and --date for presentation.

### Limiting Output Count

~~~bash
git log -n 10
git log --max-count=20
git log --skip=10 -n 10
~~~

-n or --max-count limits the number of commits displayed.
- --skip skips the first N commits in the traversal results.

When filtering with multiple conditions, remember -n limits the number of results after Git applies the filters, not the raw number of commits examined before filtering.

## 10. Practical Examples

### Finding Who Modified a File Over the Past Month

~~~bash
git log --since="1 month ago" --format="%h %an <%ae> %cI %s" -- src/payment/processor.js
~~~

Check author to see who is credited with the change, committer date to see when the commit was created, and subject to understand the intent.

### Finding Commits Related to a Ticket ID

~~~bash
git log --all --fixed-strings --grep="PAY-284"
~~~

--all expands history across refs; --fixed-strings ensures the ticket ID is searched as a literal string.

### Finding Bot Commits in a Directory

~~~bash
git log --committer="release-bot@example.com" -- src/release/
~~~

If the bot only appears in the author field or message trailer, pick the corresponding filter; --committer only checks the committer header.

### Excluding Commits Whose Message Contains WIP

~~~bash
git log --invert-grep --grep="WIP"
~~~

--invert-grep inverts the grep condition and keeps commits whose message does not match WIP. If you need complex logic like "contains fix but not WIP", do not assume multiple --grep options with --invert-grep form two independent conditions; separate the search steps or process results in a script with explicit checks.

### Viewing Commits That Added or Deleted Files in History

~~~bash
git log --diff-filter=A --name-status -- src/config/
git log --diff-filter=D --name-status -- src/config/
~~~

--diff-filter restricts commits by diff change type: A for added, D for deleted, M for modified. Combine with --name-status to see the corresponding files.

### Finding Commits That Changed a Specific Line

git log filtering by file is not the best tool for pinpointing exact lines of code. Use -S or -G:

~~~bash
git log -S"calculateTotal" -- src/payment/
git log -G"timeout[[:space:]]*=" -- src/config/
~~~

-S finds commits that change the number of occurrences of a string.
-G finds commits whose diff contains lines matching a regex.

These two options search content changes inside diffs; they complement path filters rather than replacing --author, --since, or --grep.

## 11. Distinguishing Commit Filtering from Other Content Searches

| Need | Appropriate Tool |
| --- | --- |
| Find commits by author, date, message, path | git log |
| Find commits that change string occurrence count | git log -S |
| Find commits with diff lines matching a regex | git log -G |
| Find who modified each line in the current file | git blame |
| View full details of a commit | git show |
| View commit relationship graph | git log --graph |
| Find commits by known file content | git log -S or git log -G |

git blame identifies the most recent commit attributed to each current line, though it cannot always trace the full origin of a change that was moved or rewritten. Metadata-filtered git log lets you examine multiple commits and broader context.

## 12. Limitations to Understand When Reading Results

### Author Name/Email May Be Inconsistent

One person may use multiple email addresses or names. --author="An Nguyen" may miss commits recorded under another email or abbreviated name. For thorough investigations, search multiple patterns or inspect author metadata directly.

### Messages Are Not Strictly Structured Metadata

Ticket IDs might appear in the subject, body, or trailers, or might be omitted from the message entirely. --grep only searches message text, not source code or branch names.

### Timestamps May Differ from Actual Work Dates

Author dates may be preserved across cherry-picks or rebases; committer dates typically reflect when the new commit object was created. Machine clocks or timezones may also be inaccurate. For historical ordering, inspect the parent graph.

### Path Filters Reflect Diffs and History Simplification

Git may simplify history when filtering by path, especially around merge commits. A merge can be handled under history simplification rules; therefore, when investigating changes across multiple branches, try viewing the graph with --graph, --full-history, or inspecting each parent.

### Renames Are Detected by Content

Git does not store a standalone rename event in commit objects. When computing diffs, Git detects renames based on similarity. --follow can follow a single rename chain, though it supports only one path and has limitations.

## 13. Investigation Workflow by Requirement

Suppose you need to find commits by an engineer that affected src/auth in February and mentioned token.

### Step 1: Determine branch scope

~~~bash
git branch -a
git log --oneline --decorate --all -n 20
~~~

Choose the branch or revision range suited to the question. If you need history already on the remote, fetch first according to team workflow and use the remote-tracking branch.

### Step 2: Filter by time

~~~bash
git log --since="2026-02-01T00:00:00+07:00" --until="2026-03-01T00:00:00+07:00"
~~~

### Step 3: Add author and message

~~~bash
git log --since="2026-02-01T00:00:00+07:00" --until="2026-03-01T00:00:00+07:00" --author="engineer@example.com" --grep="token"
~~~

### Step 4: Restrict path

~~~bash
git log --since="2026-02-01T00:00:00+07:00" --until="2026-03-01T00:00:00+07:00" --author="engineer@example.com" --grep="token" -- src/auth/
~~~

### Step 5: Read content and verify

~~~bash
git log -p --since="2026-02-01T00:00:00+07:00" --until="2026-03-01T00:00:00+07:00" --author="engineer@example.com" --grep="token" -- src/auth/
~~~

Read each commit's diff, check its parents, and verify author/committer when needed:

~~~bash
git show --format=fuller <commit>
git show --stat <commit>
~~~

Do not conclude that one person performed all the work merely because the author pattern matched. Verify email, committer, review records, and branch context if the information is used for audits or reporting.

## 14. Common Misconceptions

### Does --author find whoever ran git commit?

Not necessarily. It searches the author header. The person who ran the command is usually the committer; the two fields can differ.

### Does --since filter by AuthorDate?

Typically, git log time bounds rely on the committer date. If you need to see both author date and committer date, display them using %aI and %cI.

### Does --date=short only show commits from today?

No. --date formats dates in the output. --since and --until are the time filters.

### Do multiple --grep flags require all keywords by default?

No. Multiple --grep flags default to OR. Use --all-match to require all patterns.

### Does git log -- file also match commits whose message mentions the filename?

No. Path filters select commits with changes affecting the path in their diff. To search messages mentioning a filename, use --grep.

### Does --follow support multiple files at once?

No. --follow applies to a single path. If you need to track multiple files, run separate commands or use other history traversal approaches.

### Does git log return every commit that ever existed in the repository?

No. git log only traverses commits reachable from the revisions/refs in scope. Commits no longer referenced by any ref may not appear, even if their objects have not been pruned yet.

## 15. Self-Check

You need to find commits created by someone with the email dev@example.com in May 2026, whose message contains both keywords security and token, and that modified files in src/auth. You want to view author, committer, dates, and subject.

Answer the following:

1. Which option filters by author?
2. Which options restrict the time window?
3. How do you require the message to match both keywords?
4. Which separator comes before the pathspec?
5. Which format placeholders display author, committer, both dates, and subject?
6. If the file was renamed, which option can follow the old filename's history?
7. Why should you not rely solely on author date to conclude when a commit object was created?

**Hint:** Use --author, --since, and --until; use --all-match with two --grep flags; place -- before src/auth. Useful placeholders are %an/%ae, %cn/%ce, %aI/%cI, and %s. Use --follow for a single file after a rename. Author date can be preserved during cherry-pick or rebase, whereas committer date usually reflects when the current commit object was created.

## Conclusion

git log can filter history by author, committer, time, message, and path. Select the right branch scope first, combine conditions intentionally, and remember that multiple --grep flags default to OR while --all-match requires all grep patterns to match. Use -- to separate pathspecs, --follow to trace a single file across renames, and --format to print the metadata needed for verification. When investigating the origin of a change, distinguish author from committer and author date from committer date; if the result matters for audits, read the diff and parent graph rather than relying on a single filter.

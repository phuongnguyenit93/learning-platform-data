# Tracing Line-by-Line Attribution with git blame and Its Interpretation Limits

## Objectives

When reading a file in a project, you sometimes need to know which commit introduced a line into history, who is recorded as the author of that commit, and when the change happened. Git provides `git blame` to trace the origin of each line in a given version of a file.

The basic command:

~~~bash
git blame src/PaymentService.java
~~~

`git blame` helps answer the question: **which commit is recorded as having last modified this line?** It does not by itself answer who holds business ownership, who made the design decision, who reviewed it, or why the change was made.

After this lesson, you will be able to:

- Look up the commit attributed to each line in a file.
- Inspect only a specific line range or function.
- Blame a file at a selected commit, branch, or tag.
- Read the metadata fields in blame output.
- Use `-w`, `-M`, and `-C` to reduce noise from formatting or moved code.
- Skip bulk formatting commits using ignore-revs when justified.
- Use reverse blame to find the last revision in a history range where a line still existed.
- Combine blame with `git show`, `git log`, and diffs to investigate in context.
- Present findings accurately without turning Git's line attribution into conclusions about personal accountability.

## How Does git blame Work?

Git stores history as linked commits. Each commit holds a directory tree snapshot and references its parent commits. When running `git blame`, Git starts at the requested revision (defaulting to `HEAD`) and walks backward through history to determine the most recent commit that changed each line of the file.

You can visualize it as:

~~~text
Commit A: creates file and adds initial lines
        |
        v
Commit B: modifies line 12
        |
        v
Commit C: renames variable on line 20
        |
        v
Commit D: reformats entire file
        |
        v
HEAD: current version
~~~

When blaming a line at `HEAD`, Git finds the most recent commit it attributes to that line's content. If a line remained unchanged across many commits, the result can point back to a commit older than the latest commit that touched the file.

Git performs this matching based on content and history structure. When lines are detected as moved or copied, the right options help Git trace further back. This is an algorithmic attribution process, not an audit log of everyone who ever touched the line of code.

### Simple Example

Suppose a file has the following content:

~~~java
public class PaymentService {
    public void validateAmount(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Invalid amount");
        }
    }
}
~~~

Run:

~~~bash
git blame src/PaymentService.java
~~~

Sample output:

~~~text
a12bc34d (An Nguyen     2025-02-10 09:30:00 +0700 1) public class PaymentService {
b23cd45e (Binh Tran     2025-02-12 14:20:00 +0700 2)     public void validateAmount(long amount) {
b23cd45e (Binh Tran     2025-02-12 14:20:00 +0700 3)         if (amount <= 0) {
b23cd45e (Binh Tran     2025-02-12 14:20:00 +0700 4)             throw new IllegalArgumentException("Invalid amount");
a12bc34d (An Nguyen     2025-02-10 09:30:00 +0700 5)         }
a12bc34d (An Nguyen     2025-02-10 09:30:00 +0700 6)     }
a12bc34d (An Nguyen     2025-02-10 09:30:00 +0700 7) }
~~~

The commit hashes and identities here are placeholder data for illustration. Real output depends on your repository's history.

How to read each line:

- The hash at the start is the commit Git attributes to the line.
- The name and timestamp are author metadata from that commit.
- The line number indicates the line's position in the blamed file.
- The trailing text is the line content.

If adjacent lines map to the same commit, Git often compacts commit display formatting for readability. Do not rely on whitespace or field repetition to write automated parsers against default output.

## Basic Syntax

General form:

~~~bash
git blame [options] [revision] -- <path>
~~~

Where:

- `options` control line ranges, move detection, or output format.
- `revision` specifies the historical snapshot to inspect; if omitted, Git uses `HEAD`.
- `--` separates revisions/options from the file path.
- `<path>` is the path relative to the repository root or resolved by Git in the working tree.

Examples:

~~~bash
# Blame file at HEAD
git blame -- src/PaymentService.java

# Blame file on branch main
git blame main -- src/PaymentService.java

# Blame file at a specific commit
git blame a12bc34d -- src/PaymentService.java

# Blame file at a release tag
git blame v2.4.0 -- src/PaymentService.java
~~~

When specifying a revision, Git inspects the file's contents at that revision. If the path does not exist in the chosen revision, the command errors or has no contents to attribute.

Use explicit revision names and verify the commit before including results in a report:

~~~bash
git rev-parse main
git show --no-patch --oneline main
~~~

This prevents confusing branches or tags when a repository has multiple active lines of development.

### Blame Does Not Read Uncommitted Changes in the Working Tree

`git blame` inspects content at a committed revision, defaulting to `HEAD`. If you edit a file without committing, the newly modified lines in the working tree do not automatically become blame input. Commit changes on a test branch if you need attribution on that version, or target an existing historical revision. Use `git diff` to view uncommitted changes.

## Inspecting Only a Line Range with -L

In large files, you often only need to investigate one block of code. The `-L` option restricts the line range.

### Specifying Start and End Line Numbers

~~~bash
git blame -L 20,45 -- src/PaymentService.java
~~~

This inspects only lines 20 through 45 of the file at the default `HEAD` revision.

You can use a start line plus a line count:

~~~bash
git blame -L 20,+10 -- src/PaymentService.java
~~~

This starts at line 20 and covers 10 lines.

You can repeat `-L` to inspect multiple ranges:

~~~bash
git blame -L 20,35 -L 80,95 -- src/PaymentService.java
~~~

### Specifying a Range with a Regular Expression

`-L` can also accept a regular expression to locate the starting line:

~~~bash
git blame -L '/public void validateAmount/,+20' -- src/PaymentService.java
~~~

This finds the line matching the pattern, then includes 20 lines starting from that match.

You can use two patterns to mark both ends of the range:

~~~bash
git blame -L '/public void validateAmount/','/^[[:space:]]*}/' -- src/PaymentService.java
~~~

Pattern syntax must account for how Git and your shell handle quotes. If the command uses multiple quotes or special characters, test it in your shell and verify the resulting line span.

### Why Use -L?

Restricting the line range helps:

- Reduce output when files are very long.
- Focus on a single function or logic block.
- Compare results before and after refactoring more easily.
- Speed up lookups in large repositories.
- Avoid distraction from unrelated edits in the same file.

However, looking at only a small slice can hide declarations, helpers, or conditions outside that range. Once you identify a commit, widen your context using `git show` or your IDE.

## Reading Fields in Blame Output

Default output is formatted for human reading. Each line typically shows an abbreviated commit hash, author info, date, line number, and line content.

Example:

~~~text
d34ef56a (Chi Le 2025-03-04 11:15:00 +0700 42) return account.isActive();
~~~

How to interpret it:

- `d34ef56a`: commit hash attributed by Git to the line.
- `Chi Le`: author name recorded in commit metadata.
- `2025-03-04 11:15:00 +0700`: author timestamp recorded in the commit, with timezone offset.
- `42`: line number in the blamed file.
- Text after the closing parenthesis: line content.

Author metadata does not necessarily identify the person who typed the line directly. A commit may be created by someone else with the original author preserved, such as during a cherry-pick or patch application.

### Displaying Author Email

Use `-e` to display email instead of name:

~~~bash
git blame -e -L 42,55 -- src/PaymentService.java
~~~

Email is also commit metadata. It is not proof of identity verification outside Git. An email can be a personal address, corporate address, platform-anonymized address, or an arbitrarily configured string.

Do not include emails or personal information in public reports unnecessarily.

### Date Formatting

You can control date formatting:

~~~bash
git blame --date=short -- src/PaymentService.java
git blame --date=iso -- src/PaymentService.java
~~~

The displayed date still comes from commit metadata. It does not prove when the change was deployed to production or when users first encountered a bug.

### Machine-Readable Output

Do not write scripts that depend on column alignment in default output. Use porcelain format:

~~~bash
git blame --line-porcelain -- src/PaymentService.java
~~~

`--line-porcelain` outputs structured metadata for every line, making it better suited for script processing. It repeats metadata fields per line, so output is substantially longer.

Another option is:

~~~bash
git blame --porcelain -- src/PaymentService.java
~~~

Porcelain format also provides structured fields while optimizing size by omitting repeated metadata when consecutive lines share the same commit. If you need to parse each line independently, `--line-porcelain` is easier to handle.

When writing automation:

- Check the format documentation for your Git version.
- Handle full commit hashes rather than assuming fixed hash length.
- Support Unicode characters in author names and line contents.
- Do not assume every commit has identical email or metadata fields.
- Separate metadata records from source code content.
- Check exit codes and handle cases where the file does not exist at the requested revision.

## When Lines Were Reformatted: Using -w

A whitespace-only or formatting change can cause blame to attribute many lines to a formatter commit even though logic did not change.

Example:

~~~text
Commit A:
if (amount <= 0) {
    reject();
}

Commit B:
if (amount <= 0)
{
    reject();
}
~~~

If standard blame treats line layout differences as edits, output may point to Commit B. The `-w` option instructs Git to ignore whitespace changes when tracing line origin:

~~~bash
git blame -w -- src/PaymentService.java
~~~

You can combine this with a line range:

~~~bash
git blame -w -L 20,45 -- src/PaymentService.java
~~~

`-w` is useful when a project has code-formatting commits, indentation changes, or whitespace normalization.

However, not all whitespace is meaningless. In some languages and formats, whitespace affects parsing or behavior, such as Python, Makefiles, YAML, or string literals. `-w` only changes how blame attributes lines; it does not prove that a whitespace change had no effect on program behavior.

Compare standard blame with `-w` blame, then read the formatter commit's diff to confirm it was strictly formatting.

## When Lines Were Moved or Copied: Using -M and -C

Refactoring can move a block of code elsewhere or into another file. With default blame, Git may attribute those lines to the commit that performed the move or copy.

The `-M` and `-C` options help Git search for similar content elsewhere in history.

### -M: Detecting Lines Moved Within the Same File

Use:

~~~bash
git blame -M -- src/PaymentService.java
~~~

`-M` tells Git to detect lines moved or copied within the same file. This is useful when a function is reordered or a block of code is relocated inside the same file.

Git uses a similarity threshold to decide whether contents match closely enough. You can pass a threshold to `-M` when tuning is needed; a lower threshold finds more matches but can also falsely link common short snippets.

### -C: Detecting Lines Moved from Other Files

Use:

~~~bash
git blame -C -- src/PaymentService.java
~~~

`-C` extends the search to other files modified in the same commit. This is useful when refactoring extracts a class or function into a new file.

You can widen the search scope by repeating `-C`:

~~~bash
git blame -M -C -- src/PaymentService.java
git blame -M -C -C -- src/PaymentService.java
git blame -M -C -C -C -- src/PaymentService.java
~~~

In summary:

- One `-C`: searches content moved/copied from other files modified in the same commit.
- Two `-C`s: also searches other files in the commit that created the blamed file.
- Three `-C`s: extends the search across other files in history.

Broader search modes take longer, especially in large repositories. Git still relies on heuristics and similarity thresholds; it may fail to find the original source if content changed substantially or snippets are too short.

### Combining -w, -M, and -C

When a file was both reformatted and split into separate functions, try:

~~~bash
git blame -w -M -C -- src/PaymentValidator.java
~~~

To investigate thoroughly, run each variant and compare results:

~~~bash
git blame -- src/PaymentValidator.java
git blame -w -- src/PaymentValidator.java
git blame -M -C -- src/PaymentValidator.java
~~~

Do not assume more flags automatically yield a truer answer. Inspect the commit Git identifies and confirm the code was genuinely moved or copied from that source.

## Skipping Bulk Formatting Commits with ignore-revs

A commit that only changes formatting, line endings, or style conventions can make blame noisy. Git lets you ignore specific revisions during attribution.

### Ignoring a Specific Commit

~~~bash
git blame --ignore-rev a12bc34d -- src/PaymentService.java
~~~

Git attempts to ignore changes made by the specified revision and continue tracing attribution back to earlier meaningful commits.

This does not delete the commit from history. The commit still exists, appears in `git log`, and affects repository snapshots. The option only changes how blame interprets that revision.

Only ignore a commit after verifying its scope, such as a pure code-formatting commit with no logic changes. Never ignore a commit containing business-logic changes just because it clutters blame output.

### Managing a List of Revisions to Ignore

In projects with several large formatting commits, you can store their hashes in a version-controlled file such as `.git-blame-ignore-revs`:

~~~text
a12bc34d
b23cd45e
~~~

Then run:

~~~bash
git blame --ignore-revs-file .git-blame-ignore-revs -- src/PaymentService.java
~~~

You can configure Git locally to use this file automatically:

~~~bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
~~~

When tracked in the repository, the team can align on consistent blame lookups. Document the file's purpose clearly and only add reviewed commits.

### Notes When Using ignore-revs

- An ignore-revs file does not rewrite commit history.
- Different developers may have different local configs, so blame output can differ if everyone does not use the same list.
- An ignored commit might still hide unintended logic changes; review before adding.
- When reporting findings, state whether ignore-revs was used.

## Choosing How to Traverse Merge Commits with --first-parent

A merge commit has multiple parents. When tracing history, Git can follow different branches to find a line's source commit.

If you want to follow only the first parent when encountering merge commits, use:

~~~bash
git blame --first-parent main -- src/PaymentService.java
~~~

The first parent is usually the branch checked out at merge time, though that depends on how the merge was created. It does not always mean the `main` branch.

`--first-parent` is useful when inspecting history along the project's main integration line. Results can differ from default blame because commits on secondary parents are not traversed the same way.

Compare:

~~~bash
git blame main -- src/PaymentService.java
git blame --first-parent main -- src/PaymentService.java
~~~

If the two outputs differ, inspect the merge commit and its parents:

~~~bash
git log --graph --oneline --decorate --all
git show --no-patch --pretty=raw <merge-commit>
~~~

Do not treat `--first-parent` as a filter for "who is accountable". It merely restricts path traversal through the commit graph.

## Using Reverse Blame to See Up to Which Revision a Line Existed

Default blame walks backward from the current revision to find the commit that introduced a line into the inspected version.

`--reverse` walks forward across a revision range, helping find the last revision where a line still existed:

~~~bash
git blame --reverse v1.0.0..main -- src/PaymentService.java
~~~

This requires a revision range of the form `START..END`. The path must exist at the start of the range so Git can track lines forward from that baseline.

Reverse blame is useful when investigating:

- A line that existed in an older release but has since disappeared.
- Roughly when a line was deleted or replaced.
- Up to which commit in a branch legacy content remained intact.

Reverse blame is not a tool for finding every commit that ever modified a line. It answers a different question from normal blame. To see all modifications over time, use `git log -p` or history search commands.

## Going from Blame to Commit and Diff

Blame points you to a commit worth investigating further. Next, open that commit and inspect the actual change.

### Viewing the Full Commit

~~~bash
git show --format=fuller <commit-id>
~~~

The output shows:

- Author and committer.
- Author date and commit date.
- Commit message.
- Parent commits.
- Commit diff.

View changes for only one file:

~~~bash
git show <commit-id> -- src/PaymentService.java
~~~

View metadata without printing the patch:

~~~bash
git show --no-patch --format=fuller <commit-id>
~~~

Inspect the file version prior to the commit:

~~~bash
git show <commit-id>^:src/PaymentService.java
~~~

For a regular single-parent commit, `^` points to the first parent. If the commit is a merge, specify which parent to compare against; you can use `^1` or `^2`.

### Viewing File History

~~~bash
git log --oneline -- src/PaymentService.java
~~~

View patches of commits modifying the file:

~~~bash
git log -p -- src/PaymentService.java
~~~

Follow the file across renames in the log:

~~~bash
git log --follow --oneline -- src/PaymentService.java
~~~

`--follow` works well for a single file path and linear rename history; it has limitations with complex histories or copy operations. Combine with `git blame -M -C` when investigating moved or copied code.

### Finding Commits That Added or Removed a String

If a line is no longer in the current file, blaming the current version cannot point to the commit that deleted it. Search history instead:

~~~bash
git log -S'validateAmount' --oneline -- src/
~~~

`-S` finds commits changing the occurrence count of the specified string in diffs.

If you need to search by a regular expression matching diff lines:

~~~bash
git log -G'validateAmount|checkAmount' --oneline -- src/
~~~

`-G` finds patches with added or removed lines matching the pattern. `-S` and `-G` have different semantics; choose based on the question you need answered.

## Practical Workflow for Investigating a Line of Code

Suppose a bug is discovered on the amount validation line in `PaymentService.java`, and you want to understand where that change came from.

### Step 1: Verify the Repository and Version

~~~bash
git rev-parse --show-toplevel
git status --short --branch
git rev-parse HEAD
~~~

Confirm you are looking at the right repository, branch, and working tree. If investigating a released version, target the corresponding tag or commit instead of defaulting to HEAD.

### Step 2: Blame the Target Line Range

~~~bash
git blame -L 35,55 HEAD -- src/PaymentService.java
~~~

Record the commit ID attributed to the target line. Do not conclude accountability solely from the author name in the output.

### Step 3: Check Formatting or Code Movement Cases

~~~bash
git blame -w -L 35,55 HEAD -- src/PaymentService.java
git blame -M -C -L 35,55 HEAD -- src/PaymentService.java
~~~

If the output changes, compare the commits and inspect contents to see how Git handled whitespace or moved blocks.

### Step 4: Inspect the Attributed Commit

~~~bash
git show --format=fuller --find-renames <commit-id> -- src/PaymentService.java
~~~

Read the patch, author, committer, message, and parents. Verify whether the commit actually modified the logic under investigation or merely reformatted/moved code.

### Step 5: Check Surrounding History Before and After

~~~bash
git log --oneline --decorate -- src/PaymentService.java
git log -p --follow -- src/PaymentService.java
~~~

If the commit is part of a merge or code came from another file, inspect the graph and parents to understand the full path.

### Step 6: Look Up the Reason Behind the Change

Git commit messages can offer clues, but technical decisions usually live in:

- Pull Requests or Merge Requests.
- Review comments and approvals.
- Related issues or tickets.
- Design documents.
- Team technical discussions.
- Tests added or updated in the same commit.

`git blame` does not store code review threads or business rationale. Open the corresponding work-tracking system to find that context.

### Step 7: Record Findings with Clear Boundaries

An accurate way to document findings:

> Git blame on `src/PaymentService.java` at commit `<revision>` attributes line 42 to commit `<commit-id>`. The commit records `<author>` as author with message `<message>`. The diff shows the commit modified the amount validation condition. Review/ticket records should be checked to confirm rationale and design decisions.

This phrasing separates observable Git data from conclusions about people or root causes.

## Important Limitations of git blame

### Blame Does Not Identify Accountability

The commit author is a metadata field. It does not prove that person typed the code, owns the module, approved the change, or is accountable for a bug.

A commit may result from pair programming, cherry-picking, a bot, an external patch, or automation. Author metadata can be preserved while someone else is the committer.

### Blame Reflects Only Contents in Git History

Git does not know:

- Who discussed the requirements.
- Who reviewed and approved the change.
- Who made the architectural decision.
- Who tested it in staging or production.
- Why the change was deployed.
- Who owns post-release operations.

That context may live in PRs/MRs, issue trackers, CI, deployment systems, or internal docs.

### Moves and Copies Can Shift Attribution

Without `-M` or `-C`, blame can attribute lines to the commit that moved or copied them. With those flags enabled, Git uses heuristics to find similar source content. Short, common, or repeatedly edited snippets can produce ambiguous results.

Always inspect the source commit's diff and prior paths.

### Formatting Commits Can Obscure History

Formatters, line-ending normalization, or indentation changes can attribute many lines to a single large commit. Use `-w` or ignore-revs where appropriate, after confirming the commit truly made no logic changes.

### Merge Strategy Affects History Traversal

Merge commits have multiple parents. Default blame and `--first-parent` can lead to different commits. Know whether your question asks for full branch history or the main integration line.

### Deleted Lines Do Not Appear in the Current File

Blaming HEAD only inspects lines present in the selected file version. If a line was deleted, inspect an older revision where the line existed or use `git log -S`, `git log -G`, and `git log -p`.

### Shallow Clones or Missing History Produce Incomplete Results

If a clone holds only partial history, Git cannot access older unfetched commits. Check:

~~~bash
git rev-parse --is-shallow-repository
~~~

If the repository is a shallow clone and you are permitted to fetch full history, fetch deeper or unshallow according to project policy:

~~~bash
git fetch --unshallow origin
~~~

Then re-run blame. Do not conclude the displayed commit is the original source if prior history is missing from the clone.

### Generated Files or Vendored Code May Not Reflect True Authorship

A generated file, bundle, vendored dependency, or code copied from an external library will be attributed to whoever ran the generator or imported the dependency. Blame shows the commit that brought the content into the repository; it does not identify the original upstream author.

Check generator scripts, dependency manifests, upstream sources, and vendoring procedures.

## Common Commands

| Command | Purpose |
|---|---|
| `git blame -- file` | Blame lines at HEAD |
| `git blame main -- file` | Blame at branch main |
| `git blame <rev> -- file` | Blame at a specific commit/tag |
| `git blame -L 20,45 -- file` | Restrict to a line range |
| `git blame -L '/pattern/,+20' -- file` | Select a range starting from a pattern |
| `git blame -w -- file` | Ignore whitespace differences in attribution |
| `git blame -M -- file` | Detect moved lines within the same file |
| `git blame -C -- file` | Detect lines moved from other files |
| `git blame --ignore-rev <rev> -- file` | Ignore a single revision during blame |
| `git blame --ignore-revs-file <path> -- file` | Ignore a list of revisions |
| `git blame --first-parent main -- file` | Follow only the first parent at merges |
| `git blame --reverse A..B -- file` | Find the last revision in range where lines existed |
| `git blame --line-porcelain -- file` | Structured per-line output |
| `git show <rev> -- file` | View commit patch for the file |
| `git log -p -- file` | View file patch history |
| `git log --follow -- file` | Follow file history across renames |
| `git log -S'text' -- file` | Find changes in string occurrence count |
| `git log -G'regex' -- file` | Find patches with lines matching regex |

## Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Blame shows who is accountable for a line of code | Blame attributes lines to commits and their author metadata |
| Author is the person who directly typed the code | Author is a metadata field that can be preserved or configured |
| The blamed commit is the first commit that created the line | It is the most recent commit Git attributes to the current line content |
| Blame always finds the true source after refactoring | Heuristics `-M`/`-C` and diff inspection are needed |
| `-w` proves whitespace is meaningless | It only ignores whitespace during attribution |
| Ignore-revs deletes commits from history | It only changes how blame interprets those commits |
| Blaming current HEAD finds deleted lines | Must target an older revision or search with log/pickaxe |
| `--first-parent` identifies the project's primary authors | It only restricts traversal through merge commits |
| Emails in blame verify identity | Email is commit metadata, not authentication proof |
| A blame line represents the entire change history | Log, diff, merges, PRs/MRs, and tickets are needed for full context |

## Checklist When Investigating with git blame

- [ ] Confirmed the right repository, branch, and revision.
- [ ] Identified the exact file and line range to investigate.
- [ ] Recorded the commit ID attributed by blame.
- [ ] Distinguished author from committer.
- [ ] Inspected the commit with `git show`.
- [ ] Checked file history with `git log`.
- [ ] Tried `-w`, `-M`, or `-C` when formatting/moves/copies were suspected.
- [ ] Considered ignore-revs if agreed bulk formatting commits exist.
- [ ] Accounted for merges and `--first-parent` behavior.
- [ ] Checked whether the repository is shallow or missing history.
- [ ] Checked PRs/MRs, reviews, or tickets when rationale is needed.
- [ ] Framed results as Git attribution data rather than substituting for ownership verification.

## Summary

`git blame` shows which commit Git attributes to each line in a version of a file along with that commit's author metadata. Use `-L` to focus on a line range, `-w` to ignore whitespace changes, `-M` and `-C` to trace moved or copied lines, ignore-revs to skip verified formatting commits, and `--first-parent` or `--reverse` when your question requires a specific history traversal. After finding a commit, open `git show`, inspect `git log`, and check related PRs/MRs or tickets. Blame is a tool for tracing content origin in Git history; it is not standalone proof of accountability, design rationale, or the entire development process.

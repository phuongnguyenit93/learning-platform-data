# Finding Commits That Added or Removed Content with git log -S and -G

When a function, configuration variable, or error message appears in code, you may need to find which commit introduced it, changed how it is used, or removed it. Reading every commit in history is slow and error-prone. Git provides two filters for searching content changes across history: **`git log -S`** and **`git log -G`**.

These two options are commonly called *pickaxe* filters. They find commits based on diff contents rather than relying solely on author names, dates, or commit messages. The key distinction is:

- `-S<string>` finds commits that change the **number of occurrences** of a string in file contents.
- `-G<regex>` finds commits that have added or removed lines **matching a regular expression**.

Understanding the difference helps you choose the right filter, locate commits that added/removed an expression, trace API renames, or identify when a logic condition was modified.

## 1. Searching Content Changes in History

### 1.1. Standard git log Searches Commits by History

The basic command:

~~~bash
git log --oneline
~~~

displays commits reachable from HEAD. You can limit the count:

~~~bash
git log --oneline -10
~~~

When you know the time range, author, or branch, you can use those respective filters. However, to locate commits that added or removed a specific piece of code, searching diff contents is usually much more effective.

### 1.2. git log -S and -G Are Pickaxe Filters

General syntax:

~~~bash
git log -S'<string>' [options] [-- <pathspec>]
git log -G'<regex>' [options] [-- <pathspec>]
~~~

Examples:

~~~bash
git log --oneline -S'calculateTax' -- src/
git log --oneline -G'calculateTax\(' -- src/
~~~

Both commands search history for commits involving content containing the function name `calculateTax`, but their commit selection criteria differ.

### 1.3. They Search History, Not the Entire Working Tree

`git log -S` and `git log -G` examine diffs between commits in the selected history range. They do not simply search for strings in the current files on disk.

If you only want to search content in the current working tree, use:

~~~bash
git grep 'calculateTax'
~~~

If you want to find commits that changed the content, use pickaxe:

~~~bash
git log -S'calculateTax' -- src/
~~~

These two goals are distinct:

| Need | Tool |
| --- | --- |
| Search for a string in the current snapshot | `git grep` |
| Find commits changing the occurrence count of a string | `git log -S` |
| Find commits with added/removed lines matching a regex | `git log -G` |
| Find commits by commit message | `git log --grep` |
| Find the last commit that modified a specific line | `git blame` |

## 2. Understanding git log -S Precisely

### 2.1. -S Checks for Changes in Occurrence Count

`-S<string>` selects commits where the number of occurrences of the specified string changed between the version before and after the commit.

For example, before the commit, the file contains:

~~~java
boolean enabled = featureEnabled();
return enabled;
~~~

After the commit, the file contains:

~~~java
boolean enabled = featureEnabled();
audit(featureEnabled());
return enabled;
~~~

The string `featureEnabled` appeared once before the commit and twice after the commit. Because the occurrence count changed, the command:

~~~bash
git log -S'featureEnabled' -- src/
~~~

can find that commit.

### 2.2. Finding Commits That Added a String

If you want to know when a function was first introduced:

~~~bash
git log --all --oneline -S'calculateTax' -- src/
~~~

The results include commits where the occurrence count of `calculateTax` changed within the selected paths and refs Git is searching.

To inspect patches of matching commits:

~~~bash
git log --all -p -S'calculateTax' -- src/
~~~

Read the patches to determine which commit actually defined the function, which changed how it is called, or which merely added or removed another occurrence.

### 2.3. Finding Commits That Removed a String

If a condition or function is removed, the string's occurrence count decreases. For example:

~~~bash
git log --all -p -S'legacyAuthorization' -- src/
~~~

Commits removing the last occurrence of `legacyAuthorization` will appear in the output. If the string remains elsewhere and the net occurrence count stays the same, a commit deleting one line containing it might not be selected by `-S`.

### 2.4. -S Does Not Only Find Additions

The term "pickaxe string" sometimes leads learners to think `-S` only finds added strings. In fact, it detects any change in occurrence count:

- Increases from 0 to 1: added.
- Increases from 2 to 3: one more occurrence added.
- Decreases from 1 to 0: removed.
- Decreases from 4 to 2: two occurrences removed.
- Count stays unchanged: not selected solely by count.

Therefore, `-S` is ideal when you care about whether a token or expression was introduced into or disappeared from the codebase.

### 2.5. When the Occurrence Count Stays Unchanged

Suppose a commit changes:

~~~java
return validateAddress(input);
~~~

to:

~~~java
boolean valid = validateAddress(input);
return valid;
~~~

The string `validateAddress` still appears once before and once after. Its occurrence count did not change, so:

~~~bash
git log -S'validateAddress' -- src/
~~~

may not return this commit.

This is a key limitation of `-S`: it tracks occurrence counts, not every modified line containing the string.

## 3. Understanding git log -G Precisely

### 3.1. -G Finds Added or Removed Lines Matching a Regex

`-G<regex>` selects commits that have added or removed lines matching a regular expression. It inspects changed lines in the diff.

Example:

~~~bash
git log --all --oneline -G'validateAddress' -- src/
~~~

This finds commits with added or removed lines containing `validateAddress`.

To view the changed lines:

~~~bash
git log --all -p -G'validateAddress' -- src/
~~~

### 3.2. -G Catches Changes Even When Occurrence Count Is Unchanged

In this example:

~~~diff
- return validateAddress(input);
+ boolean valid = validateAddress(input);
+ return valid;
~~~

The occurrence count of `validateAddress` remains one, so `-S` can miss the commit by default. However, both the deleted old line and the added new line contain `validateAddress`, so:

~~~bash
git log -G'validateAddress' -- src/
~~~

will find the commit.

### 3.3. -G Can Find Usage Changes

Suppose you want to locate the commit that changed the parameters passed to a function:

~~~diff
- sendRequest(url, timeout);
+ sendRequest(url, timeout, retryPolicy);
~~~

Use:

~~~bash
git log -G'sendRequest\(' -p -- src/
~~~

This finds commits whose added/removed lines match the function call pattern. Read the patch to see which parameters changed.

### 3.4. -G Does Not Match Merely Because the Regex Exists in a File

If a line containing `validateAddress` was not changed in a commit, it is only context rather than an added or removed line. Simply being present in the file is not enough for a commit to be selected.

This differs from `git grep`, which searches current contents regardless of whether the line changed in a particular commit.

## 4. Comparing -S and -G with Concrete Examples

### 4.1. Case Where Occurrence Count Stays Unchanged

Before:

~~~java
return checkPermission(user);
~~~

After:

~~~java
if (!checkPermission(user)) {
    throw new AccessDeniedException();
}
return true;
~~~

The occurrence count of `checkPermission` did not change (still once), though the line containing it changed.

- `-S'checkPermission'`: may not find the commit because the occurrence count remains one.
- `-G'checkPermission'`: finds the commit because the added/removed lines match the regex.

### 4.2. Case Where Occurrence Count Increases

Before:

~~~java
if (featureEnabled()) {
    startFeature();
}
~~~

After:

~~~java
if (featureEnabled()) {
    audit(featureEnabled());
    startFeature();
}
~~~

The occurrence count increased from one to two.

- `-S'featureEnabled'`: finds the commit.
- `-G'featureEnabled'`: also finds the commit because the added line matches the regex.

### 4.3. Tool Selection Table

| Scenario | -S | -G |
| --- | --- | --- |
| Adding a new occurrence of a string | Yes | Yes if added line matches regex |
| Removing the last occurrence | Yes | Yes if deleted line matches regex |
| Editing a line while total count stays the same | Not for that string alone | Yes if added/removed line matches |
| Changing a line containing a target token | Only if occurrence count changes | Yes if changed line matches regex |
| String only appears in unchanged context lines | No | No |
| Matching multiple pattern variations | Use `--pickaxe-regex` if regex is needed | Regex natively |

### 4.4. Quick Selection Rules

- To find when a string was added or disappeared: start with `-S`.
- To find when a line containing a token was modified, even if the count did not change: use `-G`.
- Unsure which kind of change occurred: run both, then inspect patches of the resulting commits.

Neither filter understands code semantics on its own. Results still need to be read and verified in context.

## 5. Using Literal Strings and Regular Expressions

### 5.1. -S Accepts a Literal String by Default

Example:

~~~bash
git log -S'config.timeout' -- config/
~~~

Here the dot is a literal dot character in the search string, not a regex wildcard.

If the string contains spaces or special shell characters, wrap it in quotes:

~~~bash
git log -S'connection pool size' -- .
~~~

Quotes ensure the shell passes the exact string as a single argument to Git.

### 5.2. Using --pickaxe-regex with -S

If you want `-S` to count occurrences of a regular expression, add:

~~~bash
git log --pickaxe-regex -S'validate[A-Za-z]+' -- src/
~~~

Then the `-S` argument is interpreted as a POSIX extended regular expression instead of a literal string.

This example finds changes in the match count of identifiers starting with `validate` followed by one or more letters.

### 5.3. -G Always Accepts a Regex

Example:

~~~bash
git log -G'validate[A-Za-z]+' -- src/
~~~

`-G` uses a regular expression to test added/removed lines. If you want to match a literal opening parenthesis in a function call, escape it:

~~~bash
git log -G'validate[A-Za-z]+\(' -- src/
~~~

### 5.4. Useful Regex Patterns

| Goal | Example Regex |
| --- | --- |
| Lines calling a validate function | `validate[A-Za-z0-9_]*\(` |
| Lines assigning a timeout variable | `timeout[[:space:]]*=` |
| Lines containing TODO or FIXME | `TODO|FIXME` |
| Calls to old or new API | `oldClient\(|newClient\(` |
| Lines returning false | `return[[:space:]]+false;` |
| Config keys starting with feature | `feature[A-Za-z0-9_]*[[:space:]]*=` |

These examples use POSIX extended regex syntax. Characters like parentheses, dots, plus signs, or vertical bars have special meaning; escape them to match literally.

### 5.5. Do Not Assume Programming-Language Regex Syntax by Default

Git pickaxe regexes are based on POSIX extended regex (ERE), not JavaScript, Java, or PCRE in all respects. For example, `\s` is not portable whitespace in POSIX ERE; use `[[:space:]]`.

If a regex gets complex, start with a simple pattern, verify the output, and then narrow it down.

## 6. Scoping History Search Ranges

### 6.1. Searches from HEAD by Default

~~~bash
git log -S'calculateTax' -- src/
~~~

By default, Git searches commits reachable from HEAD. If a commit lives on another branch not yet merged into the current branch, it will not appear.

### 6.2. Searching Across All Refs with --all

~~~bash
git log --all --oneline -S'calculateTax' -- src/
~~~

`--all` searches history reachable from all known refs in Git, including local branches, tags, and fetched remote-tracking refs.

It cannot find commits on a remote that the local repository has not fetched or does not have objects for.

Update remote-tracking refs first if needed:

~~~bash
git fetch --all --prune
~~~

Then re-run the search. `git fetch` updates refs and objects from remotes according to configuration; it does not merge into the current branch.

### 6.3. Scoping to a Specific Branch

~~~bash
git log feature/payment -S'calculateTax' -- src/
~~~

This inspects only history reachable from the `feature/payment` ref.

### 6.4. Finding Commits Unique to One Branch

~~~bash
git log main..feature/payment --oneline -S'calculateTax' -- src/
~~~

The range `main..feature/payment` selects commits reachable from `feature/payment` that are not in `main`.

This is useful when searching for changes inside an unintegrated branch.

### 6.5. Scoping by Time Range

~~~bash
git log --since="2025-01-01" --until="2025-03-31" -S'calculateTax' -- src/
~~~

Add a time window when you know roughly when the change happened. Dates filter commits by commit metadata timestamps; they do not replace choosing the right refs or pathspecs.

### 6.6. Ordering Results Chronologically

By default, git log displays newer commits first. To view from oldest to newest:

~~~bash
git log --reverse --oneline -S'calculateTax' -- src/
~~~

This helps reconstruct the lifecycle: when a string was first introduced, modified, and eventually removed.

## 7. Path Filtering and Renames

### 7.1. Using -- to Separate Revisions and Pathspecs

Example:

~~~bash
git log -S'calculateTax' -- src/billing/
~~~

Everything before `--` is a revision or filter; everything after is a pathspec. Use the explicit separator so Git does not confuse a path name with a ref name or option.

You can search the entire repository:

~~~bash
git log -S'calculateTax' -- .
~~~

### 7.2. Searching Inside a Specific File

~~~bash
git log -p -S'calculateTax' -- src/billing/TaxService.java
~~~

This restricts results to the history of the selected file or path.

### 7.3. When a File Was Renamed

If a file was renamed, querying by the new path may not automatically include every pre-rename commit. Use:

~~~bash
git log --follow -p -S'calculateTax' -- src/billing/TaxService.java
~~~

`--follow` tells Git to continue tracing history across renames for a single path. This option has limits and relies on content-based rename detection; it does not handle every copy, complex rename, or branching history cleanly.

If you do not know the old name yet, check renames in the log:

~~~bash
git log --summary --find-renames -- src/billing/
~~~

### 7.4. Pathspecs Can Cause You to Miss Results

If a string previously lived in another file, searching only a current file path will miss commits that modified the old path or a different file.

When the location is unknown:

~~~bash
git log --all --oneline -S'calculateTax'
~~~

After finding candidate commits, inspect affected filenames with:

~~~bash
git show --name-status --format= <commit>
~~~

Then narrow the pathspec if needed.

## 8. Displaying Patches of Matching Commits

### 8.1. Add -p to Read Patches

~~~bash
git log -p -S'calculateTax' -- src/
~~~

`-p` prints the patch of each matching commit. This is usually the best way to understand how the string was added, modified, or removed.

With a regex:

~~~bash
git log -p -G'calculateTax\(' -- src/
~~~

### 8.2. Use --oneline to Build a Candidate List

~~~bash
git log --oneline -S'calculateTax' -- src/
~~~

One-line format lets you scan hashes and subjects quickly. Once you spot an interesting commit:

~~~bash
git show <commit>
~~~

to read its full metadata and patch.

### 8.3. Use --stat to See Commit Scope

~~~bash
git log --stat -S'calculateTax' -- src/
~~~

Statistics show which files the commit touched and the scale of insertions/deletions. This helps distinguish a small targeted fix from a large refactor touching the same keyword.

### 8.4. Use --pickaxe-all to See All Changes in Matching Commits

Normally, pickaxe may restrict the displayed diff to files whose changes matched the pickaxe condition. When a commit matches and you want to see the entire changeset of that commit, use:

~~~bash
git log -p --pickaxe-all -S'calculateTax' -- src/
~~~

The `--pickaxe-all` option gives fuller context: a commit may touch many files while only some of them triggered the pickaxe match.

### 8.5. Inspecting Each Candidate Commit with git show

Example search output:

~~~text
a12bc34 Add tax calculation for invoices
d45ef67 Replace legacy tax helper
f89ab01 Remove obsolete tax flag
~~~

Inspect specific commits:

~~~bash
git show --format=fuller a12bc34
git show --format=fuller d45ef67
git show --format=fuller f89ab01
~~~

Read author, committer, dates, message, and patch. Do not draw conclusions from the subject line alone, as a commit may contain broader changes than its title suggests.

## 9. Analyzing Practical Examples

### 9.1. Finding the Commit That Added a Feature Flag

Suppose you want to find when `newCheckoutEnabled` was added:

~~~bash
git log --all --reverse --oneline -S'newCheckoutEnabled' -- config/
~~~

If you want to view the patches:

~~~bash
git log --all -p -S'newCheckoutEnabled' -- config/
~~~

Read the oldest result first to identify the initial addition. Inspect the file and flag value at that commit.

### 9.2. Finding Commits That Removed a Legacy API

Suppose the API `legacyClient.request` is no longer in use:

~~~bash
git log --all -p -G'legacyClient\.request\(' -- src/
~~~

The regex finds added/removed lines matching the API call. Inspect the commits to learn whether the API was replaced, moved to another module, or simply rewritten.

### 9.3. Finding When Permission Checks Changed

~~~bash
git log --all -p -G'hasPermission|isAuthorized' -- src/security/
~~~

This finds commits with changed lines containing either function name. Read the patches to determine whether checks were added, removed, or reordered.

### 9.4. Finding When a Default Value Changed

~~~bash
git log --all -p -G'defaultTimeout[[:space:]]*=' -- config/
~~~

The regex matches configuration assignment lines. If you want to match exact occurrence changes of a literal string, use:

~~~bash
git log --all -p -S'defaultTimeout = 30' -- config/
~~~

The two approaches differ in breadth: regex matches varying whitespace or values, whereas a literal string matches only the exact specified text.

### 9.5. Finding Commits That Added or Removed TODOs

~~~bash
git log --all -p -G'TODO|FIXME' -- src/
~~~

Finds changed lines containing TODO or FIXME. It does not match existing TODO lines that remained untouched in a commit.

### 9.6. Finding Changes That Increased or Decreased API Calls

~~~bash
git log --all -p -S'httpClient.send(' -- src/
~~~

This finds changes in the occurrence count of the API call string. If a call was rewritten while the total count remained the same, use `-G` to match changed lines:

~~~bash
git log --all -p -G'httpClient\.send\(' -- src/
~~~

## 10. Combining Pickaxe with Other Filters

### 10.1. Combining with Author

~~~bash
git log --all --author='Nguyen Van An' -S'calculateTax' -- src/
~~~

Use this when narrowing results by recorded author. Note that author metadata does not by itself prove real-world identity; it is strictly a filter on commit metadata.

### 10.2. Combining with Commit Message

~~~bash
git log --all --grep='tax' -S'calculateTax' -- src/
~~~

`--grep` filters the commit message, while `-S` filters content changes. Only commits satisfying both conditions appear.

If you want regex matching on commit messages, Git has separate flags like `--extended-regexp`; do not confuse them with `--pickaxe-regex`, which controls how `-S` interprets its search string.

### 10.3. Combining with Time and Branch

~~~bash
git log feature/payment --since="2025-01-01" -G'paymentStatus' -- src/
~~~

Results only inspect history from the specified branch, within the selected time window, and with changed lines matching the regex.

### 10.4. Combining with Result Limits

~~~bash
git log --all --oneline -S'calculateTax' -n 20 -- src/
~~~

`-n 20` limits the number of displayed commits. When results are numerous, start with a short list and remove the limit if you need to dig deeper into history.

## 11. Special Cases to Watch Out For

### 11.1. Merge Commits

By default, Git omits standard diffs for merge commits in many log modes. If the change you are looking for was introduced inside a merge resolution, pickaxe may not show the merge commit as you expect.

Try requesting diffs against each parent separately:

~~~bash
git log --all -m -p -S'calculateTax' -- src/
~~~

Or with a regex:

~~~bash
git log --all -m -p -G'calculateTax' -- src/
~~~

After locating a merge commit, inspect both sides:

~~~bash
git show -m <merge-commit>
git show --cc <merge-commit>
~~~

Use `-m` to view diffs against each parent individually; use `--cc` for a combined diff. Never infer merge contents from a compact commit list alone.

### 11.2. Root Commits

The initial commit has no parent. When a file or string was first added in the root commit, Git can compare its contents against an empty tree.

Search:

~~~bash
git log --reverse -S'initialSetting' -- .
~~~

If the match is the root commit, you cannot use `<commit>^` to read a prior version because no parent exists. Read the snapshot directly:

~~~bash
git show <root-commit>:config/app.yml
~~~

### 11.3. Binary Files

`-G` checks added/removed lines against a regex, making it unsuitable for binary contents lacking normal text lines. Nor should `-S` be treated as a reliable content search across arbitrary binary formats.

To investigate a binary file, identify commits modifying its path:

~~~bash
git log --all --name-status -- path/to/asset.bin
~~~

Then compare OIDs, extract specific versions, and use format-appropriate tools to inspect contents.

### 11.4. Submodules

The superproject stores a submodule as a gitlink pointing to a commit in the child repository. Running pickaxe in the superproject does not search inside the submodule's source code.

If the string resides in a submodule, change into the submodule repository and run `git log -S` or `-G` there.

### 11.5. Git LFS

In repositories using Git LFS, Git typically stores text pointer files rather than large file payloads. Running pickaxe in the main repository only inspects committed pointers or metadata, not external binary payloads.

To search inside LFS contents, fetch the LFS objects and use tools suitable for that file format. Do not assume `git log -S` searches inside images, videos, or model files.

### 11.6. Renames and Copies

Git infers renames/copies when comparing trees. For a renamed path, a pathspec naming only the new path may not cover older filename history. Use `--follow` on a single file and inspect `--summary --find-renames` to verify results.

Rename detection relies on content similarity and may not catch every case automatically.

### 11.7. Empty Results Do Not Prove a String Never Existed

Empty output can happen because:

- Searching from HEAD while the commit lives on another branch.
- Remote changes have not been fetched yet.
- Pathspec restricted the search to the wrong directory or filename.
- The string was modified without changing its occurrence count, so `-S` did not match.
- Regex did not follow POSIX ERE syntax.
- The change happened in a merge commit, binary file, or submodule.
- The file was renamed and older history resides under a different path.

When output is empty, widen the scope step by step instead of jumping to conclusions.

## 12. Investigation Workflow from String to Commit

Suppose you see the function `authorizePayment` in code and want to find the commit that changed how it is used.

### Step 1 — Search in the Current Working Tree

~~~bash
git grep 'authorizePayment'
~~~

Identify which files and paths currently contain the string.

### Step 2 — Find Commits Changing Occurrence Count

~~~bash
git log --all --oneline -S'authorizePayment' -- src/
~~~

If you want to view all patches:

~~~bash
git log --all -p -S'authorizePayment' -- src/
~~~

### Step 3 — Also Find Line Edits Where Count Stayed the Same

~~~bash
git log --all --oneline -G'authorizePayment\(' -- src/
~~~

Compare output against `-S`. Commits appearing only in `-G` results are often call-site updates or logic restructurings where the total call count stayed constant.

### Step 4 — Inspect Interesting Commits

~~~bash
git show --format=fuller <commit>
~~~

Read author, committer, timestamps, message, and patch.

### Step 5 — Verify Before and After Versions

Suppose the commit modified `src/payment/PaymentService.java`:

~~~bash
git show <commit>^:src/payment/PaymentService.java
git show <commit>:src/payment/PaymentService.java
~~~

The first command reads the file at the parent; the second reads it after the commit. If the commit is the root commit or the file did not yet exist in the parent, the first command will fail or return nothing.

### Step 6 — Follow Subsequent Changes

~~~bash
git log --oneline <commit>..HEAD -- src/payment/PaymentService.java
~~~

Inspect commits after the discovered commit on the current branch. If you need to know who last modified each current line, run:

~~~bash
git blame src/payment/PaymentService.java
~~~

`git blame` answers where current lines came from; pickaxe answers which commits changed content matching your pattern.

### Step 7 — Record Evidence-Based Conclusions

When reporting a root cause, record:

- Full commit hash.
- Branch/ref and history scope searched.
- File paths.
- Patch demonstrating the change.
- Before and after versions if needed.
- Checked edge cases such as renames, merges, or submodules.

Never conclude a commit is the root cause merely because it matches a keyword. Read the patch and verify behavior in context.

## 13. Common Mistakes

- **Thinking -S and -G are identical:** `-S` compares occurrence counts; `-G` matches added/removed lines.
- **Using -S when the string count stayed unchanged:** the commit may be skipped. Try `-G`.
- **Treating -G like a whole-file search:** it inspects added/removed lines in diffs, not unchanged context lines or the working tree.
- **Forgetting -- before pathspecs:** Git may misinterpret arguments. Separate revisions and paths explicitly.
- **Searching only from HEAD:** commits on other branches may be missed. Use `--all` when broadening scope is needed.
- **Forgetting to fetch remotes:** `--all` only searches known local refs and objects; fetch to update remote-tracking refs.
- **Confusing -S with regex:** `-S` treats input as a literal string by default; add `--pickaxe-regex` when regex is needed.
- **Using regex syntax from another language:** pickaxe uses POSIX extended regex; double-check escaping and character classes.
- **Reading only commit subjects:** commit messages do not prove content changes. Use `-p` or `git show`.
- **Overlooking merge commits:** if a change may come from a merge, try `-m` and inspect each parent.
- **Searching binaries/submodules like normal source files:** pickaxe does not automatically descend into external objects or child repositories.
- **Treating empty results as definitive proof:** check refs, pathspecs, renames, occurrence counts, and regex syntax first.

## 14. Quick Reference Table

| Need | Command |
| --- | --- |
| Find commits changing literal occurrence count | `git log -S'featureFlag' -- .` |
| Find commits with changed lines matching regex | `git log -G'featureFlag[[:space:]]*=' -- .` |
| View patches of commits matching -S | `git log -p -S'calculateTax' -- src/` |
| View patches of commits matching -G | `git log -p -G'calculateTax\(' -- src/` |
| Search across all known local refs | `git log --all -S'calculateTax' -- .` |
| View matching commits in one-line format | `git log --oneline -S'calculateTax' -- src/` |
| Search by regex with -S | `git log --pickaxe-regex -S'validate[A-Za-z]+' -- src/` |
| Show all changes in matching commits | `git log -p --pickaxe-all -S'calculateTax' -- src/` |
| Search within a specific branch | `git log feature/payment -S'calculateTax' -- src/` |
| Search commits unique to a branch | `git log main..feature/payment -S'calculateTax' -- src/` |
| Track a file across renames | `git log --follow -p -S'calculateTax' -- src/TaxService.java` |
| Search merge commits per parent | `git log -m -p -S'calculateTax' -- src/` |
| Inspect a discovered commit | `git show --format=fuller <commit>` |
| View file content after commit | `git show <commit>:path/to/file` |
| View file content at parent | `git show <commit>^:path/to/file` |
| Search string in current working tree | `git grep 'calculateTax'` |
| Inspect origin of current lines | `git blame path/to/file` |

## 15. Summary

`git log -S` and `git log -G` let you search commits by diff content. `-S` selects commits that change the occurrence count of a string; `-G` selects commits with added or removed lines matching a regex. When an edit keeps the token count constant while changing the line, `-G` is usually the better fit. When you want to know when a string was added or disappeared, start with `-S`.

Combine pickaxe with `-p`, `--all`, pathspecs, and revision ranges to narrow history, then use `git show` to inspect commits and verify before/after snapshots. When facing empty results, check ref scope, renames, merges, regex syntax, and limitations of binaries, submodules, or Git LFS.

The key practice is using pickaxe to locate candidates, then reading the patches and verifying behavior. This approach traces when code was added, modified, or removed without manually reading the entire history.

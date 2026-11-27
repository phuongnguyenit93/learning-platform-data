# Order of Application and the Limitation on Re-Including Files Inside Ignored Directories

In a real-world repository, an ignore rule can be declared in multiple places: in a `.gitignore` file at the root directory, in a subdirectory's `.gitignore`, in the repository's private configuration, or in personal configuration on the machine. When rules match the same path, Git must determine which rule takes effect. Furthermore, ignoring an entire directory introduces an important limitation: you cannot simply write a negation rule to bring a child file back if Git still ignores its parent directory.

This lesson explains the precedence order of ignore sources, how rules across multiple `.gitignore` files interact, how to use the negation prefix, and how to design patterns to keep specific necessary files inside a directory containing many auto-generated files.

After this lesson, you will be able to:

- Identify which ignore source has higher precedence.
- Explain how the last rule matching a path determines the outcome.
- Understand the scope of patterns in `.gitignore` at the root directory and in subdirectories.
- Use `!` to bring a file back into tracking scope.
- Recognize why a file beneath an ignored parent directory cannot be re-included directly.
- Design patterns so Git still enters the parent directory and identifies the files to keep.
- Use `git check-ignore` to find the rule causing an ignored state.
- Distinguish ignore functionality from file attributes in `.gitattributes`.

## 1. Where Does Git Look for Ignore Rules?

Git has multiple sources of ignore rules. For an untracked path, these sources have different precedence levels:

| Precedence | Source | Scope |
| --- | --- | --- |
| Highest | Patterns passed directly to Git commands that support exclude patterns. | Applies only to that command invocation. |
| Next | `.gitignore` files in the directory containing the path and its parent directories. | Shared with the repository; deeper files can override higher-level files. |
| Next | `.git/info/exclude`. | Current local repository only; not committed or shared via remote. |
| Lowest | Global ignore file configured via `core.excludesFile`. | Applies to the user on the current machine. |

Not all Git commands accept patterns directly on the command line; the first level applies only to commands that support that exclude mechanism. In day-to-day work, the three sources that matter most are `.gitignore`, `.git/info/exclude`, and the global ignore file.

View the currently configured global ignore file:

~~~bash
git config --show-origin --get core.excludesFile
~~~

View all relevant configuration values:

~~~bash
git config --show-origin --get-all core.excludesFile
~~~

The `.gitignore` file is usually committed for the whole team to share. `.git/info/exclude` is suited for repository-specific files on your machine, while `core.excludesFile` is suited for personal files commonly generated across many projects, such as editor temporary files.

## 2. Precedence Between Multiple .gitignore Files

A repository can have multiple `.gitignore` files:

~~~text
project/
+-- .gitignore
+-- src/
|   +-- .gitignore
|   +-- main.java
|   +-- generated/
|       +-- .gitignore
+-- build/
    +-- output.bin
~~~

Patterns in a `.gitignore` file are applied relative to the directory containing that file. When the same path matches multiple rules across `.gitignore` files, a file deeper in the directory tree has higher precedence than a file in a parent directory. Within the same file, the last matching rule determines the outcome.

For example, the root `.gitignore` file:

~~~gitignore
*.log
~~~

The `src/.gitignore` file:

~~~gitignore
!debug.log
~~~

For `src/debug.log`, the pattern in `src/.gitignore` is deeper so it can negate the `*.log` rule from the root file, provided parent directories are not ignored. A file `src/trace.log` remains ignored by the root directory rule because no deeper rule brings it back.

If two matching rules appear in the same file:

~~~gitignore
*.log
important.log
!important.log
~~~

The last rule matching `important.log` is `!important.log`, so the file is brought back. If the order is reversed:

~~~gitignore
!important.log
*.log
~~~

The `*.log` rule comes later and matches again, so `important.log` is ignored.

Rule to remember: first evaluate the precedence level of the source, then evaluate matching rules within that source. Do not stop at finding a `!pattern` line and conclude the file is definitely tracked; you still need to check whether a higher-precedence rule or a later rule matches it again.

## 3. Pattern Scope by File Location

A pattern without a middle slash can typically match a name at any directory level beneath the `.gitignore` file containing that pattern.

Example in the root `.gitignore`:

~~~gitignore
*.tmp
~~~

This pattern can ignore:

~~~text
draft.tmp
src/cache.tmp
src/generated/output.tmp
~~~

If a pattern has a leading slash or a middle slash, it is interpreted relative to the directory containing the `.gitignore` file:

~~~gitignore
/build/
src/generated/
~~~

In the root `.gitignore` file:

- `/build/` matches only the `build` directory right at the repository root.
- `src/generated/` matches only the path `src/generated` relative to the repository root.

In the `src/.gitignore` file, the pattern `/generated/` instead matches only the `src/generated` directory, because the pattern's anchor is the `src` directory.

A trailing slash indicates matching directories only:

~~~gitignore
cache/
~~~

This pattern matches directories named `cache` and the contents inside them, not a regular file named `cache`.

A few illustrative patterns:

| Pattern | Matching scope |
| --- | --- |
| `*.class` | Files with the `.class` extension at any level beneath the `.gitignore` file. |
| `/dist/` | The `dist` directory right beside the `.gitignore` file. |
| `docs/*.pdf` | PDF files directly inside `docs`, not matching deeper levels. |
| `**/cache/` | A `cache` directory at any level beneath the pattern's location. |
| `logs/**` | All contents inside the `logs` directory, including subdirectories. |

Patterns can use double asterisks to describe multiple directory levels. When patterns are complex, test with `git check-ignore` rather than reasoning purely by eye.

## 4. How Does the Negation Prefix ! Bring Files Back?

A pattern starting with `!` negates a previous ignore rule. Example:

~~~gitignore
*.log
!keep.log
~~~

All `.log` files are ignored, except `keep.log` within the scope of that `.gitignore` file.

Specific paths can be used:

~~~gitignore
/logs/*
!/logs/release.log
~~~

The pattern `/logs/*` ignores items directly inside `logs`. It does not ignore the `logs` directory itself. Because the parent directory is still entered by Git, the rule `!/logs/release.log` can bring `release.log` back.

The `!` prefix does not track a file by itself. It only ensures the file is no longer ignored by patterns at the corresponding precedence level. The file still needs to be seen by Git and added with `git add` if it is not yet tracked.

If a filename begins with `#` or `!`, escape the leading character with a backslash to distinguish a filename from a comment or negation pattern. Trailing spaces in patterns also have special handling rules; if you genuinely want to match a trailing space in a name, escape that space.

## 5. Key Limitation: Cannot Re-Include Files if a Parent Directory Is Ignored

This is the most frequently misunderstood limitation of `.gitignore`. If a directory is ignored, Git generally does not enter that directory to look for files inside it. Therefore, a negation rule targeting a child file has no effect if its parent directory is still being ignored.

Example that does not work as expected:

~~~gitignore
/artifacts/
!/artifacts/release.json
~~~

You want to ignore the entire `artifacts` directory while keeping `release.json`. However, `/artifacts/` ignores the parent directory itself. Git does not enter it to discover `release.json`, so the trailing negation line cannot bring the file back.

Picture it like this:

~~~text
Repository
|
+-- artifacts/       <- ignored
|   +-- debug.log
|   +-- package.zip
|   +-- release.json <- negation rule is never evaluated
~~~

Git ignores the `artifacts` directory right at the parent level. It does not traverse the contents of this directory to apply the rule for `release.json`.

This is an intentional limitation so Git does not have to scan every file in already-excluded directory trees. Therefore, to keep a child file, you must let Git continue entering every parent directory along that path.

## 6. How to Write Patterns to Keep a File Directly Inside a Directory

If you want to ignore all immediate contents inside `artifacts` while keeping `release.json`, ignore the items inside instead of ignoring the directory itself:

~~~gitignore
/artifacts/*
!/artifacts/release.json
~~~

The `/artifacts/*` pattern matches entries inside the `artifacts` directory, while the `artifacts` directory itself remains traversable. The negation line brings `release.json` back.

Result:

~~~text
Repository
|
+-- artifacts/          <- not ignored
|   +-- debug.log       <- ignored
|   +-- package.zip     <- ignored
|   +-- release.json    <- re-included
~~~

If you want to keep a subdirectory along with a file inside it, you must bring the subdirectory back first:

~~~gitignore
/artifacts/*
!/artifacts/release/
/artifacts/release/*
!/artifacts/release/manifest.json
~~~

Expected result:

~~~text
artifacts/
|   +-- debug.log                 <- ignored
|   +-- package.zip               <- ignored
|   +-- release/                  <- re-included for Git to traverse
|       +-- build.log             <- ignored
|       +-- manifest.json         <- re-included
~~~

If `manifest.json` sits one level deeper, every intermediate directory must also be re-included. For example, keeping `artifacts/release/meta/manifest.json`:

~~~gitignore
/artifacts/*
!/artifacts/release/
/artifacts/release/*
!/artifacts/release/meta/
/artifacts/release/meta/*
!/artifacts/release/meta/manifest.json
~~~

Each parent directory matched by an ignore pattern must have a corresponding negation rule before Git can evaluate files inside it. In practice, if a directory structure has many levels and changes frequently, it is better to design patterns so the parent directory is not ignored in the first place; that approach is usually easier to read and less error-prone.

## 7. Distinguishing Two Ways to Ignore a Directory

The following two patterns look nearly identical but behave differently:

~~~gitignore
/build/
~~~

and:

~~~gitignore
/build/*
~~~

The `/build/` pattern ignores the `build` directory itself. Git does not traverse items inside, so `!/build/keep.txt` alone cannot bring a child file back.

The `/build/*` pattern ignores immediate items inside `build` without ignoring the `build` directory itself. This allows subsequent rules to bring a specific item back:

~~~gitignore
/build/*
!/build/keep.txt
~~~

If you want to bring a subdirectory back, you must negate that directory and then decide on the items inside it:

~~~gitignore
/build/*
!/build/reports/
/build/reports/*
!/build/reports/summary.txt
~~~

Do not mechanically replace every pattern ending in `/` with `/*`. Choose the syntax according to your goal:

- If you do not need to keep any contents, ignore the whole directory with `/build/`.
- If you need to selectively keep contents inside, keep the parent directory traversable and ignore child items with `/build/*`.

## 8. Rules in a Child .gitignore Can Override Root Rules, but Cannot Bypass an Ignored Parent Directory

A `.gitignore` file in a subdirectory can adjust root rules for paths beneath it, provided Git can enter that subdirectory.

Example:

Root `.gitignore` file:

~~~gitignore
*.log
~~~

`src/.gitignore` file:

~~~gitignore
!debug.log
~~~

`src/debug.log` is re-included because the ignore file in `src` has higher precedence than the root file.

However, the following example does not work:

Root `.gitignore` file:

~~~gitignore
/src/
~~~

`src/.gitignore` file:

~~~gitignore
!debug.log
~~~

Git does not traverse `src` because this directory is already ignored. Consequently, `src/.gitignore` is not read to apply the rule for `debug.log`.

If you need to selectively keep files inside `src`, change the root rule so it does not ignore the directory itself:

~~~gitignore
/src/*
!/src/debug.log
~~~

Place rules where they are easiest to understand, and avoid creating multiple `.gitignore` files with overlapping exceptions unless genuinely needed.

## 9. Identifying Exactly Which Rule Is Ignoring a Path

When a file does not appear in `git status`, do not rush to add multiple negation lines. First, ask Git which rule is matching:

~~~bash
git check-ignore -v path/to/file
~~~

The `-v` option displays the rule source, line number, and matched pattern. For example, the output might show that the root `.gitignore` file, line 12, pattern `/artifacts/` ignored the path.

To check an already-tracked file as well, you can use:

~~~bash
git check-ignore -v --no-index path/to/file
~~~

`--no-index` instructs the command to evaluate ignore rules even when the path is already in the index. By default, tracked files are not affected by the ignore mechanism in the way untracked files are.

To check multiple paths:

~~~bash
git check-ignore -v path/to/file path/to/another-file
~~~

If there is no output, the path may not match an ignore rule. Check whether the file has been saved to disk, which repository it belongs to, and whether it is excluded from scanning by an ignored parent directory.

## 10. .gitignore Does Not Untrack Already-Committed Files

Ignore rules primarily affect untracked files. If a file has already been committed, adding its filename to `.gitignore` does not remove the file from the index and does not stop tracking it.

For example, the `.env` file has already been committed. Then you add:

~~~gitignore
.env
~~~

Git continues to track changes to `.env`. If you want to keep the file on your machine while stopping tracking in future commits:

~~~bash
git rm --cached .env
git add .gitignore
git commit -m "Stop tracking local environment file"
~~~

`--cached` removes the path from the index while keeping the file in the working tree. After the commit, new clones or checkouts will no longer receive that file from the repository, while the current machine retains the local file. If the file ever contained passwords or tokens, removing it from the index in a new commit does not remove the secret from earlier history; handle the secret and history according to the team's security workflow.

## 11. Role of .git/info/exclude and Global Ignore

Not every generated file needs a rule in the committed `.gitignore`. For example, one member might want to ignore a personal IDE workspace file while the team still wants others to track that kind of file.

In this case, you can add patterns to `.git/info/exclude`:

~~~gitignore
# Applies only to the repository on this machine
.idea/workspace.xml
local-notes.txt
~~~

Or configure a global ignore file:

~~~bash
git config --global core.excludesFile ~/.config/git/ignore
~~~

The global ignore file can contain:

~~~gitignore
.DS_Store
Thumbs.db
*.swp
~~~

These sources have lower precedence than the repository's `.gitignore`. Thus, a global ignore rule cannot use `!` to bring back a file that the project's `.gitignore` has already ignored. If an exception is needed for the whole team, edit the rules in the shared `.gitignore`.

## 12. Do Not Confuse .gitignore with .gitattributes

The two files have similar names but solve two different problems:

| File | Role | Example |
| --- | --- | --- |
| `.gitignore` | Determines which untracked paths should be ignored. | Ignore `build/`, `*.log`, or local `.env` files. |
| `.gitattributes` | Assigns attributes to paths managed or processed by Git. | Choose line-ending normalization via `text`/`eol`, diff/merge drivers, or filters. |

Example `.gitattributes`:

~~~gitattributes
*.sh text eol=lf
*.png binary
*.md text
~~~

These attributes affect how Git handles file contents, such as normalizing line endings or treating a file as binary in diffs. They are not rules for bringing an ignored file back and do not replace `.gitignore`.

If a file is ignored because of a parent directory, adding an attribute for it in `.gitattributes` does not make Git start traversing that directory. You must first adjust the ignore rules so the path is recognized; then the appropriate attributes apply.

## 13. Workflow for Diagnosing and Fixing an Ignore Exception

Suppose the repository ignores the `generated` directory, yet the team needs to keep `generated/manifest.json`:

~~~text
project/
|-- .gitignore
+-- generated/
|   +-- cache.bin
|   +-- preview.log
|   +-- manifest.json
~~~

Step 1: Check status and rules:

~~~bash
git status --short
git check-ignore -v generated/manifest.json
~~~

Step 2: If the current rule is:

~~~gitignore
/generated/
~~~

replace it with:

~~~gitignore
/generated/*
!/generated/manifest.json
~~~

Step 3: Verify again:

~~~bash
git check-ignore -v generated/cache.bin
git check-ignore -v generated/preview.log
git status --short
~~~

`manifest.json` should appear as an untracked file if it has never been added. `cache.bin` and `preview.log` remain ignored. If `manifest.json` sits in a subdirectory, bring back each necessary parent directory before negating the file.

Step 4: Add the right file to track and verify staging:

~~~bash
git add .gitignore generated/manifest.json
git status --short
git diff --cached
~~~

Only commit after the staged diff contains the exact rule file and exception file intended to be shared.

## 14. Common Errors

### Writing !file Yet the File Remains Ignored

Check whether a parent directory is ignored. If so, replace the rule ignoring the entire directory with a rule ignoring only the entries inside, then bring the file to keep back.

### Rules in a Child File Have No Effect

Check whether the directory containing the child `.gitignore` is ignored by a parent file. Git does not enter an excluded directory to read rules inside it.

### The ! Prefix Does Not Override the Desired Rule

Check the order of lines in the same file and the precedence level of the file containing the pattern. The last matching rule at the same level takes effect; a deeper `.gitignore` file can override a parent-level file.

### Committed File Still Shows Changes Even After Adding to .gitignore

This is normal behavior. Use `git rm --cached` if the goal is to stop tracking the file while keeping it on your machine.

### Global Ignore Causes Teammates to See Different Results

Check `core.excludesFile` and `.git/info/exclude` on your machine. If a rule needs to be shared with the whole team, place it in the repository's `.gitignore` rather than relying on personal configuration.

## 15. Takeaways

- Ignore sources have a precedence order: command-line patterns where supported, `.gitignore` by directory level, `.git/info/exclude`, then the global ignore file.
- Across `.gitignore` files, a deeper file can override a parent-level file; within the same file, the last matching rule wins.
- Patterns are evaluated relative to the location of the `.gitignore` file containing them.
- The `!` prefix negates an ignore rule, but cannot bring a file back if its parent directory remains ignored.
- To keep certain files inside a large directory, usually ignore entries inside using `/dir/*` rather than ignoring `/dir/` itself.
- For deep paths, Git must be allowed to enter every parent directory along that path.
- Use `git check-ignore -v` to find the source, line number, and matched pattern.
- `.gitignore` does not stop tracking already-committed files; use `git rm --cached` when you need to remove from the index while keeping the local file.
- `.gitattributes` controls how Git processes file contents; it does not replace the ignore mechanism.

When you understand precedence order and directory traversal limits, you can write predictable ignore rules, keep the exact files needed, and avoid accidentally committing auto-generated data into the repository.

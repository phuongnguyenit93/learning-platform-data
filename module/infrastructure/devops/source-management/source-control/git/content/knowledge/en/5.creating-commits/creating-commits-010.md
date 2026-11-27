# Inspecting Commit Identifiers and Contents with git show

After running `git commit`, you need to verify that the commit was created properly: which identifier was generated, who the author and committer are, whether the message is accurate, which files changed, and whether the patch content matches your objective. The `git show` command is the direct tool for inspecting a commit along with its metadata and changes.

For the latest commit, `git show` typically uses `HEAD` as the target object. You can choose to display the full patch, metadata only, statistics, file lists, or raw data. When inspecting a specific file, distinguish two syntaxes: `git show HEAD -- path/to/file` shows the file's diff in the commit; `git show HEAD:path/to/file` prints the entire file content stored in that snapshot.

This lesson explains how to identify commit IDs, read metadata, inspect patches and file lists, view file contents at a commit, compare with parents, handle merge commits, and recognize limitations with binary files, submodules, and Git LFS.

## 1. What Is git show Used For?

### 1.1. Inspecting a Git Object

General syntax:

~~~bash
git show [options] <object>
~~~

`<object>` can be:

- Commit: `HEAD`, commit hash, branch, or tag.
- Annotated tag: Git displays the tag details and the object the tag points to.
- Tree: lists entries in the tree.
- Blob: prints the contents of a file object.

In a commit creation workflow, the most common target is `HEAD`, because HEAD points to the current commit after a successful commit.

For example:

~~~bash
git show HEAD
~~~

For a regular commit, the output includes commit details and its diff relative to its parent. The initial commit has no parent; Git can display its content as additions relative to an empty tree.

### 1.2. git show Does Not Create or Modify Commits

`git show` is a read-only command. It does not change:

- HEAD or the current branch.
- The index (staging area).
- The working tree.
- Commit messages or metadata.
- The remote repository.

Therefore, you can use it for post-commit inspection without altering repository state.

### 1.3. Distinguishing git show and git status

| Command | Purpose |
| --- | --- |
| `git status` | Shows current branch, staged, unstaged, and untracked changes |
| `git show HEAD` | Reads the current commit, its metadata, and its changes |
| `git log` | Walks through a list of commits in history |
| `git diff` | Compares two states or two trees |
| `git show HEAD:path` | Reads a file's contents in a commit's snapshot |

A repository may be clean after committing while you still need `git show` to verify the commit you just created. Conversely, `git status` reports whether uncommitted changes remain, rather than fully explaining the contents of a commit.

## 2. Identifying the Newly Created Commit

### 2.1. HEAD Is the Current Commit

After `git commit` succeeds, HEAD is normally updated to the new commit on the current branch.

Check the latest commit:

~~~bash
git log -1 --oneline --decorate
git show --no-patch --oneline HEAD
~~~

Sample output:

~~~text
a81c9f2 (HEAD -> feature/billing) Validate billing address before checkout
~~~

In this example:

- `a81c9f2` is the abbreviated commit ID.
- `HEAD -> feature/billing` indicates the current branch pointing to that commit.
- The remainder is the commit subject.

### 2.2. Getting the Full Commit ID

Run:

~~~bash
git rev-parse --verify HEAD^{commit}
~~~

Or:

~~~bash
git show -s --format=%H HEAD
~~~

The result is the commit's full object ID. ID length depends on the repository's object format; do not assume every repository uses a 40-character string.

Check the object format:

~~~bash
git rev-parse --show-object-format
~~~

A repository may use SHA-1 or SHA-256. When recording a commit ID in tickets, release notes, or reports, use the full value to avoid ambiguity across abbreviated hashes.

### 2.3. Abbreviated IDs Can Vary by Context

An abbreviated ID is usually enough for Git to resolve a commit if it does not collide with another object. The abbreviation length can vary based on the number of objects in the repository and configuration.

To record the exact commit just created:

~~~bash
git show -s --format="%H" HEAD
~~~

Do not truncate hashes manually when storing evidence or cross-system references.

### 2.4. Confirming the Commit Belongs to the Intended Branch

~~~bash
git status --short --branch
git branch --show-current
git log -1 --decorate --oneline
~~~

If you are in a detached HEAD state, `git show HEAD` still shows the current commit, yet the new commit might not be attached to the branch you intended. Verify the branch before pushing or opening a pull request.

## 3. Reading Commit Metadata and Identity

### 3.1. Viewing Full Metadata with --format=fuller

~~~bash
git show --format=fuller --no-patch HEAD
~~~

Output may look like:

~~~text
commit a81c9f2...
Author:     Nguyen Van An <an@company.example>
AuthorDate: Mon Mar 10 09:30:00 2025 +0700
Commit:     Nguyen Van An <an@company.example>
CommitDate: Mon Mar 10 10:05:00 2025 +0700

    Validate billing address before checkout
~~~

Key fields:

- `commit` line: identifier of the commit object.
- Author: person credited with writing the change.
- AuthorDate: timestamp when the author is recorded as having created the change.
- `Commit:` line in metadata: committer identity, the person who created the current commit object.
- CommitDate: timestamp when the commit object was created.
- Message: the commit message.

Author and committer can differ during cherry-pick, rebase, or applying patches from others.

Author and email fields are metadata supplied by the commit creator; on their own, they do not prove real-world identity or account ownership. If a repository requires signed commits, verify the signature with:

~~~bash
git verify-commit HEAD
~~~

Signature verification results also depend on configured public keys and trust policy. A valid signature confirms the commit was signed by the corresponding key; it does not by itself prove every author detail in metadata is accurate.

### 3.2. Displaying Timestamps in ISO 8601

~~~bash
git show --format=fuller --date=iso-strict --no-patch HEAD
~~~

Strict ISO format makes date, time, and timezone offset easy to read, for example:

~~~text
AuthorDate: 2025-03-10T09:30:00+07:00
CommitDate: 2025-03-10T10:05:00+07:00
~~~

Use this format when cross-referencing review systems, tickets, or release logs that store timestamps.

### 3.3. Printing Only Needed Fields

You can format the output yourself:

~~~bash
git show -s --format="Commit: %H%nTree: %T%nParents: %P%nAuthor: %an <%ae>%nAuthor date: %aI%nCommitter: %cn <%ce>%nCommitter date: %cI%nSubject: %s" HEAD
~~~

Common placeholders:

| Placeholder | Meaning |
| --- | --- |
| `%H` | Full commit hash |
| `%h` | Abbreviated commit hash |
| `%T` | Snapshot tree hash |
| `%P` | Parent hashes |
| `%an` | Author name |
| `%ae` | Author email |
| `%aI` | Author date in strict ISO 8601 |
| `%cn` | Committer name |
| `%ce` | Committer email |
| `%cI` | Committer date in strict ISO 8601 |
| `%s` | Subject |
| `%b` | Commit message body |

The `-s` or `--no-patch` option suppresses the diff. This is appropriate when you only need metadata.

### 3.4. Viewing Raw Commit Data

~~~bash
git show --format=raw --no-patch HEAD
~~~

Raw format clearly shows:

- The tree object referenced by the commit.
- The parent commit or parents.
- Author and timestamp.
- Committer and timestamp.

You can read the object directly:

~~~bash
git cat-file -p HEAD
~~~

`git cat-file -p` is a plumbing command that prints object contents. `git show` is more convenient for reading commits from a user perspective and can render diffs.

### 3.5. Checking the Message

~~~bash
git show -s --format=%B HEAD
~~~

`%B` prints the full commit message, including subject and body. Use it to confirm the message was not truncated, missing explanation, or containing information that should not enter history.

If the message includes issue references, ticket IDs, or Conventional Commits formatting, check it against the project's rules.

## 4. Viewing Commit Changes

### 4.1. Viewing a Commit with the Default Patch

~~~bash
git show HEAD
~~~

The output typically includes commit metadata and the patch comparing the commit's snapshot to its parent.

The patch uses:

- Lines starting with minus: content present in the parent and removed.
- Lines starting with plus: content added in the commit.
- Lines without plus/minus: context helping locate the change.

Example:

~~~diff
-    if (address == null) {
-        return true;
-    }
+    if (address == null || address.isBlank()) {
+        return false;
+    }
~~~

Read the surrounding context as well to understand the change in execution flow, not just the added or removed lines.

### 4.2. Combining Metadata and Patch

~~~bash
git show --format=fuller --patch HEAD
~~~

This is useful when reviewing a newly created commit: the top shows who created the commit and when, and the bottom shows what changed.

If the output is very long, use statistics or path filters before reading the whole patch.

### 4.3. Viewing Only the Patch, Hiding Metadata

~~~bash
git show --format= --patch HEAD
~~~

An empty format omits the commit header while keeping the patch displayed. This is useful when focusing purely on content changes or piping a patch to another step.

### 4.4. Viewing a Word Diff

~~~bash
git show --word-diff HEAD -- docs/api/checkout.md
~~~

Word diff highlights changed words or tokens rather than whole lines. It is useful for documentation, JSON, configuration, or long lines.

You can select a mode:

~~~bash
git show --word-diff=plain HEAD -- docs/api/checkout.md
~~~

This produces cleaner output when multiple words change on the same line.

### 4.5. Checking Whitespace in the Patch

~~~bash
git show --check HEAD
~~~

This checks for common whitespace issues in the diff, such as trailing whitespace or spacing errors on new lines. It does not replace a formatter, linter, or tests.

## 5. Viewing Statistics and Changed File Lists

### 5.1. Statistics with --stat

~~~bash
git show --stat HEAD
~~~

Example:

~~~text
 src/order/CheckoutService.java       | 12 ++++++++----
 src/order/AddressValidator.java      | 18 ++++++++++++++++++
 test/order/CheckoutServiceTest.java  | 24 ++++++++++++++++++++++++
 docs/api/checkout.md                 |  6 +++++-
 4 files changed, 54 insertions(+), 6 deletions(-)
~~~

Statistics help answer:

- How many files changed?
- Which files have many insertions/deletions?
- Does the commit have an unexpectedly broad scope?

Use the compact form combined with subject:

~~~bash
git show --stat --oneline HEAD
~~~

### 5.2. Listing Only Filenames with --name-only

~~~bash
git show --name-only --format= HEAD
~~~

This prints affected paths without outputting the patch. Useful for confirming commit scope.

### 5.3. Listing Names and Change Types with --name-status

~~~bash
git show --name-status --format= HEAD
~~~

Common status codes:

| Code | Meaning |
| --- | --- |
| A | Added file |
| M | Modified file |
| D | Deleted file |
| R | Renamed |
| C | Copied |

For renames or copies, Git may append a similarity percentage, such as `R095`.

### 5.4. Using --numstat for Line Counts

~~~bash
git show --numstat HEAD
~~~

Output typically has three tab-separated columns:

~~~text
12    6    src/order/CheckoutService.java
18    0    src/order/AddressValidator.java
24    0    test/order/CheckoutServiceTest.java
~~~

The first two columns are added and deleted line counts. For binary files, Git usually shows dashes instead of line numbers.

### 5.5. Viewing Raw Diff and Mode/OID

~~~bash
git show --raw HEAD
~~~

The raw diff shows:

- Old mode and new mode.
- Old and new object IDs.
- Change status.
- Affected paths.

This is helpful when changes involve executable bits, symbolic links, submodules, or OID cross-checking.

## 6. Selecting the Right Commit to Inspect

### 6.1. Viewing the Current Commit

~~~bash
git show HEAD
~~~

HEAD is the most appropriate target right after a commit succeeds.

### 6.2. Viewing an Earlier Commit

~~~bash
git show HEAD^
~~~

`HEAD^` is the first parent of HEAD. In normal linear history, this is the commit immediately before HEAD.

~~~bash
git show HEAD~2
~~~

`HEAD~2` walks back two steps along first parents from HEAD.

Note: `git show HEAD^` displays that parent commit itself along with its diff against its own parent; it is not the command for showing the diff between HEAD and HEAD^.

### 6.3. Viewing a Commit by Hash

~~~bash
git show a81c9f2
~~~

You can use a full hash or a short hash unique within the repository. If recording evidence or storing in external systems, prefer the full hash.

### 6.4. Viewing a Commit by Branch or Tag

~~~bash
git show main
git show v1.2.0
~~~

For a branch, Git resolves the branch to the commit its ref points to. For an annotated tag, `git show` can display tag details and the target commit.

To confirm which commit a tag points to:

~~~bash
git rev-parse 'v1.2.0^{commit}'
~~~

### 6.5. Viewing Multiple Commits

~~~bash
git show HEAD HEAD^
~~~

This displays each specified object. If the goal is browsing a range of history, `git log` is usually better suited:

~~~bash
git log --oneline -5
~~~

Then use `git show <commit>` to inspect individual commits in detail.

## 7. Viewing Changes for a Specific File

### 7.1. Syntax for Viewing a File's Diff in a Commit

~~~bash
git show HEAD -- src/order/CheckoutService.java
~~~

`--` separates the revision from the pathspec. The command displays changes to that file in HEAD compared to the commit's parent.

This is the right syntax to answer: "How did the commit I just created modify this file?"

### 7.2. Syntax for Viewing Full File Contents at a Commit

~~~bash
git show HEAD:src/order/CheckoutService.java
~~~

The `<tree-ish>:<path>` syntax prints the blob content stored at that path in the commit's snapshot.

These two commands serve different goals:

| Command | Result |
| --- | --- |
| `git show HEAD -- path/to/file` | The file's patch in the commit |
| `git show HEAD:path/to/file` | Full file content at the commit |

Do not put `--` between HEAD and the colon when using the blob-reading syntax.

### 7.3. Comparing a File Between the New Commit and Its Parent

View the file before the commit:

~~~bash
git show HEAD^:src/order/CheckoutService.java
~~~

View the content after the commit:

~~~bash
git show HEAD:src/order/CheckoutService.java
~~~

You can compare the two states with Git's diff:

~~~bash
git diff HEAD^ HEAD -- src/order/CheckoutService.java
~~~

This lets you verify exactly how a file changed between two snapshots.

### 7.4. Viewing Files in a Commit When Paths Contain Spaces

Wrap the pathspec in quotes:

~~~bash
git show HEAD -- "docs/release notes.md"
~~~

To read blob content:

~~~bash
git show "HEAD:docs/release notes.md"
~~~

Quotes ensure the shell passes the full path as a single argument. For filenames with special characters, make sure the pathspec syntax is passed accurately.

### 7.5. Files Deleted in the Commit

If a commit deletes a file, `git show HEAD:path/to/file` cannot read a blob at that path in the new snapshot because the path no longer exists.

You can read the pre-deletion version:

~~~bash
git show HEAD^:path/to/file
~~~

And view the deletion diff:

~~~bash
git show HEAD -- path/to/file
~~~

### 7.6. New Files Added in the Commit

For a new file, no version exists in the parent:

~~~bash
git show HEAD:path/to/new-file
~~~

prints the file content in the new commit. Meanwhile:

~~~bash
git show HEAD -- path/to/new-file
~~~

shows the file-addition patch, typically consisting of added lines.

## 8. Understanding Commit ID, Tree, and Parents

### 8.1. Commit ID Identifies Commit Content

A commit hash is computed from the commit object's content, including tree, parents, author, committer, and message. Thus, changing the message or metadata alters the commit hash even if file contents do not change.

Get the hash:

~~~bash
git show -s --format=%H HEAD
~~~

### 8.2. Tree ID Identifies the File Snapshot

A commit references a tree object containing the directory structure and files at that snapshot.

View the tree ID:

~~~bash
git show -s --format=%T HEAD
~~~

Two commits can share the same tree yet have different commit hashes if author, committer, parents, or message differ.

### 8.3. Parent Commits

View parents:

~~~bash
git show -s --format=%P HEAD
~~~

A regular commit has one parent; a root commit has no parent; a merge commit typically has two or more parents.

Parent information tells you which snapshot the commit is being compared against.

### 8.4. Viewing the Raw Commit Object

~~~bash
git show --format=raw --no-patch HEAD
~~~

This output helps inspect the tree and parents referenced by the commit. When you need exact object contents, combine with:

~~~bash
git cat-file -p HEAD
~~~

Never edit objects in the object database manually. If metadata is wrong, use amend or an appropriate history-rewriting workflow.

## 9. Inspecting Merge Commits

### 9.1. Merge Commits Have Multiple Parents

A merge commit typically has at least two parents. When you run:

~~~bash
git show HEAD
~~~

Git may render a combined diff for the merge commit. A combined diff looks different from a linear commit patch and follows its own display rules.

View parents:

~~~bash
git show -s --format="%H%n%P" HEAD
~~~

### 9.2. Viewing Separate Diffs Against Each Parent with -m

~~~bash
git show -m HEAD
~~~

The `-m` option produces a separate diff for each parent of the merge commit. This is useful when you want to see what the merge commit changed relative to each parent branch.

### 9.3. Viewing the Merge Result Against the First Parent

Compare the merge tree against the first parent:

~~~bash
git diff HEAD^1 HEAD
~~~

Against the second parent:

~~~bash
git diff HEAD^2 HEAD
~~~

This is often easier to read when checking how the final state differs from the target branch or the merged-in branch.

### 9.4. Combined Diff with --cc

~~~bash
git show --cc HEAD
~~~

Combined diff focuses on relevant differences between the merge result and its parents. Not every change from each parent appears the same way as in a standard linear diff.

If you need to audit each side individually, use `-m` or `git diff HEAD^1 HEAD` and `git diff HEAD^2 HEAD`.

## 10. Viewing Renames, Modes, and Binary Files

### 10.1. Detecting Renames

~~~bash
git show --summary --find-renames HEAD
~~~

Git infers renames by comparing contents and paths between snapshots. A rename is not a separate object type inside a commit.

You can adjust the similarity threshold:

~~~bash
git show --find-renames=80% HEAD
~~~

If content changed substantially, Git may show a deletion and addition rather than a rename.

### 10.2. Detecting Mode Changes

~~~bash
git show --raw HEAD
~~~

For example, changing an executable bit switches the mode from `100644` to `100755` even when file content is unchanged.

This is why you should not inspect text patches alone; check raw diff or summary when a commit modifies file permissions.

### 10.3. Binary Files

For binary files, Git usually does not print a human-readable text patch. Use:

~~~bash
git show --stat HEAD
git show --numstat HEAD
git show --raw HEAD
~~~

to inspect the path, relative size change, and OIDs.

The `--binary` option generates a binary patch representation usable by `git apply`:

~~~bash
git show --binary HEAD
~~~

It does not make binary data human-readable. If you need to verify an image, archive, or model file, extract it and inspect it with format-appropriate tools.

### 10.4. Submodules

In the parent repository's commit, a submodule is represented by a gitlink pointing to a commit in the child repository. `git show` can show that the submodule OID changed, yet it does not automatically display the entire child repository's contents.

You can view submodule summary info in the diff:

~~~bash
git show --submodule=log HEAD
~~~

To inspect actual changes, enter the submodule repository and view the recorded commit. Ensure the submodule sits at the exact commit referenced by the parent repository's tree.

### 10.5. Git LFS

In a commit, Git typically stores an LFS pointer rather than the large binary payload. Therefore:

~~~bash
git show HEAD:assets/model.bin
~~~

may print the plain-text pointer containing version, OID, and size, rather than the real model file.

To retrieve actual content, Git LFS and the corresponding object must be downloaded. `git show` only prints the blob stored by Git in the commit; it does not fetch LFS objects from the server.

## 11. Filtering and Formatting Output

### 11.1. Show Only Statistics Without Patch

~~~bash
git show --stat --no-patch HEAD
~~~

Suitable for quickly confirming scope without reading the entire diff.

### 11.2. Show Only Filenames and Status

~~~bash
git show --name-status --format= HEAD
~~~

Suitable for review checklists or scripts that need to verify which files were added, modified, deleted, or renamed.

### 11.3. Show Only the Patch for One Directory

~~~bash
git show HEAD -- src/order/
~~~

Use a pathspec to limit output to a specific area. This is especially helpful in monorepos.

### 11.4. Limit Context Lines

~~~bash
git show -U3 HEAD -- src/order/CheckoutService.java
~~~

`-U3` displays three lines of context around each hunk. Increase or decrease based on review needs.

### 11.5. Disable External Diff and Textconv for Direct Output

~~~bash
git show --no-ext-diff --no-textconv HEAD
~~~

Some repositories configure external diff drivers or textconv filters for specialized rendering. These options force Git to use its internal diff and ignore textconv, useful when you want output independent of external tools.

### 11.6. Colors and Pager

Whether output is colored or opened in a pager is display behavior of your environment, not commit content.

Disable the pager for one command:

~~~bash
git --no-pager show HEAD
~~~

Or disable color:

~~~bash
git -c color.ui=false show HEAD
~~~

When saving output to logs or automation, pick a stable format and avoid parsing human-facing text with brittle line splitting.

## 12. Workflow for Verifying a Newly Created Commit

Suppose you just created the commit `Validate billing address before checkout`.

### Step 1 — Confirm commit and branch

~~~bash
git status --short --branch
git branch --show-current
git show -s --format="%H%n%s" HEAD
~~~

Ensure HEAD is on the intended branch and the subject is right.

### Step 2 — Check author, committer, and timestamps

~~~bash
git show --format=fuller --date=iso-strict --no-patch HEAD
~~~

Confirm name, email, author date, and committer date.

### Step 3 — Check file list and statistics

~~~bash
git show --stat --oneline HEAD
git show --name-status --format= HEAD
~~~

Verify there are no temporary files, secrets, or out-of-scope edits.

### Step 4 — Read the patch

~~~bash
git show --format=fuller HEAD
~~~

Review logic, tests, and documentation in the commit. To focus on a single file:

~~~bash
git show HEAD -- src/order/CheckoutService.java
~~~

### Step 5 — Inspect a file's final snapshot

~~~bash
git show HEAD:src/order/CheckoutService.java
~~~

Cross-check against the content you intended to commit. To inspect the previous version:

~~~bash
git show HEAD^:src/order/CheckoutService.java
~~~

### Step 6 — Check whitespace and remaining state

~~~bash
git show --check HEAD
git status --short --branch
~~~

If changes remain in the working tree, determine whether they were intentionally set aside or accidentally left out.

### Step 7 — Record commit evidence when needed

~~~bash
git show -s --format="%H %aI %cI %s" HEAD
~~~

Record the full commit ID alongside release or ticket information if your process requires it. There is no need to copy the entire patch into another document when the commit itself is already the authoritative history record.

## 13. Common Mistakes

- **Using git show HEAD:path when wanting to see a diff:** that syntax prints the entire file content in the commit. Use `git show HEAD -- path` to view the patch.
- **Thinking HEAD^ is the diff of the current commit:** HEAD^ is the parent; `git show HEAD^` displays the parent commit. Use `git diff HEAD^ HEAD` to compare the two snapshots.
- **Only checking the subject:** a right message does not guarantee a right patch. Read the diff and file list.
- **Only checking --stat:** statistics do not show logic changes. Read the patch during review.
- **Confusing author with committer:** inspect both identities and timestamps.
- **Assuming hashes are always 40 characters long:** length depends on object format. Run `git rev-parse --show-object-format`.
- **Ignoring binary files:** patches may not display contents. Check OID, size, and open with an appropriate tool.
- **Assuming git show downloads LFS objects:** Git only prints the committed pointer blob. Download LFS objects with Git LFS.
- **Assuming submodules store full source in the parent commit:** the parent tree only records a gitlink to the child repository's commit.
- **Reading a merge commit like a linear commit:** use `-m`, `--cc`, or compare against each parent individually.
- **Parsing human-facing output in scripts:** use proper formats/porcelain options or stable structures; filenames can contain spaces and special characters.

## 14. Quick Reference Table

| Need | Command |
| --- | --- |
| View latest commit | `git show HEAD` |
| Get full hash | `git show -s --format=%H HEAD` |
| Check object format | `git rev-parse --show-object-format` |
| View author/committer | `git show --format=fuller --no-patch HEAD` |
| View ISO timestamps | `git show --format=fuller --date=iso-strict --no-patch HEAD` |
| View full message | `git show -s --format=%B HEAD` |
| View tree and parents | `git show --format=raw --no-patch HEAD` |
| Verify commit signature if present | `git verify-commit HEAD` |
| View full patch | `git show --format=fuller HEAD` |
| View statistics | `git show --stat HEAD` |
| List files and status | `git show --name-status --format= HEAD` |
| View added/deleted line counts | `git show --numstat HEAD` |
| View raw diff | `git show --raw HEAD` |
| View diff of one file | `git show HEAD -- path/to/file` |
| View file content at commit | `git show HEAD:path/to/file` |
| View file content before commit | `git show HEAD^:path/to/file` |
| Compare commit with parent | `git diff HEAD^ HEAD` |
| View merge diff per parent | `git show -m HEAD` |
| View combined merge diff | `git show --cc HEAD` |
| Check whitespace | `git show --check HEAD` |
| View committed LFS pointer file | `git show HEAD:assets/model.bin` |
| Check working tree status | `git status --short --branch` |

## 15. Summary

`git show` verifies a newly created commit from its identifier through its metadata and snapshot content. Start with `git show --format=fuller --no-patch HEAD` to inspect author, committer, timestamps, and message; use `git show HEAD` or `git show --format=fuller HEAD` to read the patch; use `--stat`, `--name-status`, `--numstat`, or `--raw` to check change scope.

Remember to distinguish `git show HEAD -- path` (the file's diff in the commit) from `git show HEAD:path` (the file's content in the snapshot). When comparing against the prior version, use `HEAD^` or `git diff HEAD^ HEAD`. For merge commits, inspect each parent separately; for binaries, submodules, and Git LFS, also verify the associated objects or repositories.

A solid verification workflow does not stop at seeing that the commit succeeded. Check the branch, hash, identity, message, file list, patch, and remaining status. Doing so catches out-of-scope commits or inaccurate metadata early before sharing to a remote.

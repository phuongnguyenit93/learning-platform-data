# Inspecting a Commit's Changes with git show

When reading Git history, knowing which commits exist is only the first step. You also need to answer which files a commit changed, what the content looked like before and after, who created the commit, whether the commit belongs to a specific branch or tag, and whether the content you are viewing is the actual saved snapshot or merely uncommitted changes on your machine.

The `git show` command is the direct tool for inspecting a commit. For a commit, Git displays metadata, the commit message, and the diff introduced by that commit. You can also request only statistics, filenames, signature status, or the contents of a file at a specific snapshot.

This lesson belongs to the **History Inspection** chapter of the `SOURCE_CONTROL_GIT` module. The module covers working tree, staging area, commits, history, branches, merges, rebases, remotes, and tags; reading commits accurately helps trace changes, review bugs, and understand collaboration history.

## 1. What Does git show Tell You?

Basic syntax:

~~~bash
git show <commit>
~~~

Example viewing the current commit:

~~~bash
git show HEAD
~~~

This command typically displays:

1. The commit identifier and metadata header.
2. The author and when the change was originally created.
3. The committer and when the current commit object was created.
4. The commit message.
5. The diff describing changes introduced by that commit.

For a regular commit, the diff shows the difference between the commit's snapshot and its parent. For the initial commit with no parent, you can use the root option to display added files relative to an empty tree.

A commit stores a snapshot of the repository at a point in time. The diff presented by git show helps you understand how that snapshot differs from its parent; it is not a direct comparison against the current working tree.

## 2. Selecting the Right Commit to Inspect

git show accepts a commit hash, branch name, tag, and many revision expressions that Git can resolve to an object.

### Viewing the Current Commit and Preceding Commits

~~~bash
git show HEAD
git show HEAD~1
git show HEAD~2
~~~

- HEAD is the commit that the current branch points to.
- HEAD~1 is the first parent of HEAD.
- HEAD~2 is the first parent of the first parent.

You can use a full hash or an abbreviated hash:

~~~bash
git show a1b2c3d
~~~

An abbreviated hash is valid only if Git resolves it uniquely to a single object in the repository.

### Distinguishing ^ and ~

The ~n notation follows the first parent repeatedly n times. The ^n notation selects the nth parent of the current commit.

~~~bash
git show HEAD^
git show HEAD^1
git show HEAD^2
git show HEAD~2
~~~

For a regular commit with only one parent, HEAD^ and HEAD^1 are identical. For a merge commit with two or more parents, HEAD^1 is the first parent and HEAD^2 is the second parent. Therefore, HEAD~1 does not mean "the previous commit across any branch"; it always follows the first parent.

### Viewing a Commit by Branch or Tag

~~~bash
git show main
git show release/v2.1
git show v2.1.0
~~~

A branch name points to the current tip commit of that branch. A tag can be a lightweight tag pointing directly to a commit or an annotated tag with its own tag object. For annotated tags, git show can display the tag information followed by the object referenced by the tag.

To verify that a tag name resolves to a commit:

~~~bash
git rev-parse --verify "v2.1.0^{commit}"
~~~

The ^{commit} suffix instructs Git to peel/resolve the tag or object to a commit. This is useful when scripts need to ensure the target object is specifically a commit.

## 3. Reading Metadata Without Viewing the Patch

When you only need to know who created a commit, when, and its message, use --no-patch:

~~~bash
git show --no-patch --format=fuller HEAD
~~~

--format=fuller displays Author, AuthorDate, Committer, and CommitDate in full.

Some commonly used formats:

| Option | Content |
| --- | --- |
| --format=oneline | Hash and subject on a single line |
| --format=short | Commit header and subject |
| --format=medium | Standard metadata and commit message |
| --format=fuller | Adds full author/committer date details |
| --format=raw | Close to raw commit object contents, including tree and parents |
| --no-patch | Suppresses diff output |

Example viewing metadata and parents:

~~~bash
git show --no-patch --format=raw HEAD
~~~

Raw format is useful when investigating merges, parents, or verifying commit structure. It is still an object view, not a file content comparison.

### Distinguishing Author and Committer

Author is the person recorded as having originally written the change. Committer is the person who created the current commit object. The two people can differ during cherry-picks, rebases, patch application, or commits recreated on someone else's behalf.

Example:

~~~text
Author:     Nguyen An <an@example.com>
AuthorDate: Mon Nov 16 09:10:00 2026 +0700
Commit:     Tran Binh <binh@example.com>
CommitDate: Mon Nov 16 10:25:00 2026 +0700
~~~

Do not infer remote access permissions from names/emails inside commits. That is historical metadata; remote authentication is a separate mechanism.

## 4. Viewing a Commit's Patch

To view the patch with full metadata:

~~~bash
git show --format=fuller HEAD
~~~

Each diff section typically looks like:

~~~diff
diff --git a/src/payment.js b/src/payment.js
index 12ab34c..56de78f 100644
--- a/src/payment.js
+++ b/src/payment.js
@@ -10,6 +10,9 @@ function calculateTotal(items) {
   return items.reduce((sum, item) => {
     return sum + item.price;
   }, 0);
+}
+
+function calculateTax(total, rate) {
+  return total * rate;
 }
~~~

How to read it:

- diff --git a/... b/... indicates the before and after paths in the diff.
- index displays the old and new object IDs along with the file mode.
- --- represents the old side; +++ represents the new side.
- Lines starting with a minus sign were removed in the new snapshot.
- Lines starting with a plus sign were added in the new snapshot.
- Lines without a plus or minus sign are context lines helping locate the change.
- The @@ -x,y +a,b @@ header indicates line ranges in the old and new versions.

Context lines are not changes committed by this commit. Only added/removed lines represent differing content in that hunk.

### Easier Patch Reading with Context or Word Diffs

Reduce context lines:

~~~bash
git show -U2 HEAD
~~~

Increase context lines:

~~~bash
git show -U10 HEAD
~~~

For short text changes, you can inspect differences word by word:

~~~bash
git show --word-diff HEAD
~~~

--word-diff helps spot a phrase or expression modified mid-line. It does not replace normal diff review, especially for structured source code or binary files.

## 5. Viewing Only a Single File or Directory in a Commit

To view the patch for a specific path introduced by that commit, put the -- separator before the pathspec:

~~~bash
git show HEAD -- src/payment.js
~~~

The -- separator separates revisions/options from paths. It prevents Git from mistaking a filename for a branch or revision name.

You can specify multiple paths:

~~~bash
git show HEAD -- src/payment.js tests/payment.test.js
~~~

Or a directory:

~~~bash
git show HEAD -- src/
~~~

The output is the diff for those paths in the selected commit compared to its corresponding parent.

### Viewing Filenames and Change Statuses

~~~bash
git show --name-status --format=medium HEAD
~~~

Common status codes:

| Symbol | Meaning |
| --- | --- |
| A | Added — file was added |
| M | Modified — file was modified |
| D | Deleted — file was deleted |
| R | Renamed — Git detected a rename |
| C | Copied — Git detected a copy when copy detection is enabled/configured |

Git stores snapshots and objects, not rename operations as standalone object types. Statuses R or C are inferred by content similarity algorithms when rendering diffs.

If you only need a list of paths:

~~~bash
git show --name-only --format= HEAD
~~~

To view only change statistics:

~~~bash
git show --stat --oneline HEAD
~~~

These options are helpful when scoping a commit before reading individual diff hunks.

## 6. Viewing a File's Snapshot at a Commit

Another important syntax:

~~~bash
git show <commit>:<path>
~~~

This syntax reads the object contents at that path in the commit's snapshot rather than showing a patch.

Example viewing file contents at HEAD:

~~~bash
git show HEAD:src/payment.js
~~~

Viewing the same file at an earlier commit:

~~~bash
git show HEAD~3:src/payment.js
~~~

Compare two snapshots using git diff with the appropriate two revisions/paths.

Distinguish the two forms:

| Command | Result |
| --- | --- |
| git show HEAD -- src/payment.js | Patch of commit HEAD for that path |
| git show HEAD:src/payment.js | Full contents of the file in snapshot HEAD |

If the path does not exist in the selected snapshot, Git reports an error because no object is found at that path.

### Viewing Binary File Contents

Do not print binary blobs directly to the terminal. You can redirect the snapshot contents to a temporary file and open it with an appropriate application:

~~~bash
git show HEAD:assets/diagram.png > /tmp/diagram-at-head.png
~~~

In PowerShell:

~~~powershell
git show HEAD:assets/diagram.png > "$env:TEMP/diagram-at-head.png"
~~~

This command only writes the commit's stored content to the target file. Choose a separate temporary path to avoid overwriting working files.

## 7. Comparing a Commit with Its Parent vs. Comparing Two Snapshots

git show <commit> generally shows what changes that commit introduced relative to its parent. If you want to compare any two snapshots, use git diff:

~~~bash
git diff HEAD~2 HEAD
~~~

The difference:

| Need | Command |
| --- | --- |
| See what a commit added/modified/deleted relative to its parent | git show <commit> |
| Compare snapshots of two commits | git diff <commit-A> <commit-B> |
| View changes from a commit up to HEAD | git diff <commit> HEAD |
| View file contents at a snapshot | git show <commit>:path/to/file |
| View unstaged changes | git diff |
| View staged changes compared to HEAD | git diff --cached |

For example, to view all changes from commit A to commit B:

~~~bash
git diff A B
~~~

If you run git show B, you are only viewing changes introduced by commit B relative to B's parent. The two results can differ significantly if there are multiple commits between A and B.

## 8. Checking What Changed in a Commit Using Output Modes

git show offers several options to narrow down output:

| Option | When to Use |
| --- | --- |
| --stat | View added/deleted line counts per file |
| --shortstat | View only total files and lines added/deleted |
| --numstat | Numeric statistics, convenient for scripts |
| --name-only | List paths only |
| --name-status | List paths with A/M/D/R... |
| --summary | Show mode changes, renames, or summary info |
| --raw | Inspect changes at mode and object ID level |
| --check | Check for whitespace errors in the patch |
| --no-patch | Display commit header only, without diff |

Example:

~~~bash
git show --shortstat HEAD
git show --numstat HEAD
git show --summary HEAD
git show --check HEAD
~~~

--check is helpful when reviewing whitespace issues such as trailing whitespace or spaces before tabs. It is not a code quality linter or application test suite.

### Combining Multiple Options

~~~bash
git show --format=fuller --stat --summary HEAD
git show --format= --name-status HEAD
git show --format= --numstat HEAD
~~~

Use --format= to omit the message/metadata header when you only want file lists or statistics. In scripts, fix the format explicitly so output does not vary with a machine's format.pretty setting.

## 9. Reading Merge Commits

A merge commit has two or more parents. When inspecting a merge commit, understand how the diff is generated because there is no single parent representing all pre-merge history.

View metadata and parent list:

~~~bash
git show --no-patch --format=raw <merge-commit>
~~~

View patches against each parent:

~~~bash
git show -m <merge-commit>
~~~

-m instructs Git to show diffs of the merge commit against each parent. This is useful for seeing how the merge changed the result relative to each incoming branch.

View combined diff:

~~~bash
git show --cc <merge-commit>
~~~

Combined diff focuses on parts that differ from all parents in the merge result. It may omit changes that only differ from one parent; therefore, for full analysis, also inspect -m or diff against each individual parent.

Example comparing merge result against the first parent:

~~~bash
git diff <merge-commit>^1 <merge-commit>
~~~

Compare against the second parent:

~~~bash
git diff <merge-commit>^2 <merge-commit>
~~~

Do not rely on a single diff format alone to conclude what a merge brought into a branch. Identify the parents and comparison perspective before reading.

## 10. Reading Root Commits and Special Commits

A root commit is the initial commit in history, with no parents. To inspect its information:

~~~bash
git show --no-patch --format=fuller <root-commit>
~~~

To show files added relative to an empty tree:

~~~bash
git show --root --stat <root-commit>
~~~

A commit can be an empty commit (changing nothing in the tree relative to its parent) while still having metadata and a message. When git show prints no patch, the commit is not necessarily broken; it may simply contain no file content changes.

## 11. Verifying Commit Signatures When Needed

If a project requires signed commits, you can display signature details alongside commit info:

~~~bash
git show --show-signature --no-patch HEAD
~~~

Verify a specific commit:

~~~bash
git verify-commit HEAD
~~~

Signatures verify that the commit object was signed with the corresponding key and that the signed content has not been tampered with. Trust outcomes also depend on public keys, trust configuration or allowed signers, and installed signing tools.

Author name/email shown in git show is just metadata. It does not prove the person authenticated with the remote or that the commit signature is valid.

## 12. Notes on Git LFS and Submodules

git show <commit>:path reads the blob content stored by Git in that snapshot. For files managed by Git LFS, the blob stored in Git is typically a pointer text file rather than the actual large file content.

Example:

~~~bash
git show HEAD:assets/video.mp4
~~~

You will usually see a pointer containing version, OID, and size. To fetch actual LFS contents, you need Git LFS and the corresponding object on the LFS server.

For submodules, the superproject stores a gitlink containing the commit ID that the submodule is expected to check out. In diffs, you may see the submodule's commit ID change; git show in the superproject does not automatically show the full patch inside the submodule repository. Change into the submodule directory and run git show in that repository to inspect the corresponding commit.

## 13. Commit Review Workflow

A practical workflow when asked to "check what this commit changed":

**Step 1: Identify the commit**

~~~bash
git rev-parse --verify "<revision>^{commit}"
~~~

Use a specific hash or ref to avoid accidentally inspecting a branch tip that has moved.

**Step 2: Inspect metadata and message**

~~~bash
git show --no-patch --format=fuller <commit>
~~~

Check author, committer, timestamps, parents, and commit message.

**Step 3: Check file scope**

~~~bash
git show --stat --summary <commit>
git show --name-status --format= <commit>
~~~

Identify which files were added, modified, deleted, or renamed.

**Step 4: Read the patch**

~~~bash
git show --format=fuller <commit>
~~~

Read each hunk, paying attention to added/removed lines and affected files.

**Step 5: Cross-check snapshots if needed**

~~~bash
git show <commit>:path/to/file
git diff <commit>^ <commit> -- path/to/file
~~~

The first command shows file contents in the snapshot; the second shows the patch for that path against the first parent. For merge commits, explicitly specify which parent to compare against.

**Step 6: Check the working tree separately**

~~~bash
git status --short
git diff
git diff --cached
~~~

These commands show current local changes. They are not part of any saved commit unless staged and committed.

## 14. Common Misconceptions

- **Assuming git show HEAD shows current working tree contents:** the command displays commit HEAD; uncommitted changes are not in that snapshot.
- **Confusing git show commit -- file with git show commit:file:** the first displays a patch; the second displays the file's contents in the snapshot.
- **Assuming git show compares any two commits:** it focuses on the selected object and a commit's parent; use git diff A B to compare two snapshots.
- **Using HEAD~2 as the second parent:** ~ follows the first parent; use ^2 to select the second parent of a merge commit.
- **Reading only metadata and assuming you understand the commit:** also inspect the file list and patch when the goal is understanding the change.
- **Reading merge commits like regular commits:** identify the parents and choose -m, --cc, or git diff accordingly.
- **Assuming Git stores renames as separate object types:** renames are detected during diff rendering by comparing contents.
- **Assuming git show decodes LFS content:** Git normally stores only pointer blobs; LFS objects are managed separately.
- **Running git show <commit>:<path> to the terminal on binary files:** output can flood the terminal with garbage characters; redirect to a file instead.
- **Sharing output without checking for sensitive data:** commit messages, diffs, or paths may contain internal information.

## 15. Command Selection Diagram

~~~mermaid
flowchart TD
    A[Need to inspect a commit] --> B[Select revision and verify it resolves to a commit]
    B --> C{Which part do you need to view?}
    C -- Metadata --> D[git show --no-patch --format=fuller]
    C -- File list --> E[git show --name-status]
    C -- Statistics --> F[git show --stat]
    C -- Patch --> G[git show commit]
    C -- File content at snapshot --> H[git show commit:path]
    G --> I{Is it a merge commit?}
    I -- Yes --> J[Choose -m, --cc, or diff with parent]
    I -- No --> K[Read patch relative to parent]
    D --> L[Cross-check with status/index if needed]
    E --> L
    F --> L
    H --> L
    J --> L
    K --> L
~~~

Before concluding your review, verify for yourself:

1. Did I select the right commit hash/ref and confirm it resolves to a commit?
2. Do I need metadata, file list, statistics, patch, or snapshot contents?
3. Did I distinguish the commit snapshot from the current working tree/index?
4. If it is a merge commit, did I identify the parents and diff perspective?
5. If LFS or submodules are involved, did I inspect the data in the corresponding storage/repository?
6. Did I read all relevant patches and check for sensitive data before sharing?

git show is a fast way to inspect a commit from metadata down to its patch. When you need filenames, statistics, snapshot contents, or signatures, choose the matching options; when comparing two snapshots or analyzing a merge, specify parents explicitly and use git diff when appropriate. Always keep committed history separate from the index and working tree so you draw accurate conclusions about what is actually stored in a commit.

## References

- [Git documentation: git-show](https://git-scm.com/docs/git-show) — displaying commits, tags, trees, blobs, and diffs.
- [Git documentation: gitrevisions](https://git-scm.com/docs/gitrevisions) — HEAD~n, HEAD^n syntax and revision expressions.
- [Git documentation: git-diff](https://git-scm.com/docs/git-diff) — comparing two trees/snapshots and diff modes.
- [Git documentation: diff-merges](https://git-scm.com/docs/git-log#_diff_formatting) — how merge commit diffs are displayed.
- [Git documentation: git-verify-commit](https://git-scm.com/docs/git-verify-commit) — verifying commit signatures.
- [Pro Git: Viewing the Commit History](https://git-scm.com/book/en/v2/Git-Basics-Viewing-the-Commit-History) — reading and filtering commit history.

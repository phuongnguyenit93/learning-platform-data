# Limitations of git commit -a for Untracked Files

The command `git commit -a` is often misunderstood as “commit all changes”. In reality, the `-a` option automatically stages modifications and deletions on files already tracked by Git. It does not automatically add new untracked files to the index.

The key point is that after the automatic staging step, Git still creates the commit from everything currently in the index. Therefore, a new file that was staged earlier will still appear in a `-a` commit; a new file sitting only in the working tree will not.

This lesson belongs to the **Creating Commits** chapter of the `SOURCE_CONTROL_GIT` module. The module covers the working tree, staging area, commits, history, branches, merging, rebasing, remotes, and tags; understanding `git commit -a` accurately helps you control commit scope and avoid missing new files or accidentally recording unintended changes in history.

## 1. First: Tracked, Untracked, and the Index

Git distinguishes files based on whether they have been added to the index/history.

- **Tracked file:** a path managed by Git, usually already present in a commit or added to the index.
- **Untracked file:** a file present in the working tree that has not yet been added to the index.
- **Staged change:** content or an add/modify/delete operation recorded in the index in preparation for the next commit.
- **Unstaged change:** a change in the working tree that has not yet been updated in the index.

Suppose a repository has this layout:

~~~text
project/
  README.md
  src/
    app.js
    config.js
  docs/
    setup.md
~~~

Assume `README.md`, `src/app.js`, and `src/config.js` have already been committed. You modify `src/app.js`, delete `src/config.js`, and create `docs/setup.md`.

| Path | Status | Does Git Already Know the Path? |
| --- | --- | --- |
| `src/app.js` | Modified | Yes, tracked |
| `src/config.js` | Deleted | Yes, tracked |
| `docs/setup.md` | Untracked | Not yet, if not staged |

This is the distinction that determines how `git commit -a` behaves.

## 2. What Does git commit -a Do?

The command:

~~~bash
git commit -a -m "Update application"
~~~

or in shorthand form:

~~~bash
git commit -am "Update application"
~~~

automatically stages modifications and deletions of tracked files into the index, then creates a commit from the index.

Put simply:

1. Git finds tracked files with changes in the working tree.
2. Git stages the new content of modified tracked files and stages the deletion of deleted tracked files.
3. Git creates a commit from all content currently in the index.

The third step is critical: the commit does not contain only the changes just staged by `-a`. Everything already present in the index is also included in the commit, including new files you staged earlier with `git add`.

### Example: Modifying and Deleting Tracked Files

Suppose:

- `src/app.js` was committed and is currently modified.
- `src/config.js` was committed and has been deleted.
- No changes have been staged beforehand.

Run:

~~~bash
git commit -am "Update app and remove old config"
~~~

Git automatically stages the edits in `src/app.js`, stages the deletion of `src/config.js`, and creates the commit. Both changes are recorded in history.

### Example: New Untracked File

Suppose you create `docs/setup.md` but have not run `git add`:

~~~bash
git status --short
~~~

The output might look like:

~~~text
 M src/app.js
 D src/config.js
?? docs/setup.md
~~~

Run:

~~~bash
git commit -am "Update application"
~~~

The commit will include the changes to `src/app.js` and the deletion of `src/config.js`. `docs/setup.md` remains untracked and does not appear in the commit.

After committing, check:

~~~bash
git status --short
~~~

You will still see:

~~~text
?? docs/setup.md
~~~

This is the core limitation of `-a`: Git does not decide on its own to add new files because you have not explicitly indicated that you want them tracked.

## 3. Previously Staged New Files Are Still Committed

Distinguish two cases:

- A new file exists only in the working tree: not in the index yet, so `git commit -a` skips it.
- A new file has already been added with `git add`: already in the index, so `git commit -a` commits it along with other changes in the index.

For example:

~~~bash
git add docs/setup.md
git commit -am "Add setup guide and update app"
~~~

Here `docs/setup.md` is committed because you staged it beforehand. The `-a` option did not add this file itself; it only performed the additional staging step for tracked files.

If you staged some changes earlier, inspect `git diff --cached` before committing. Those staged changes will be included in the same commit even if they are not directly related to what you expected `-a` to handle.

## 4. Comparing git commit -a, git add -u, and git add -A

These commands look similar but serve different purposes:

| Command | Modified/Deleted Tracked Files | New Untracked Files | Creates a Commit? |
| --- | --- | --- | --- |
| `git commit -a -m "..."` | Auto-stages | Does not auto-stage | Yes |
| `git add -u` | Stages | Does not stage | No |
| `git add -A` | Stages | Stages if not ignored | No |
| `git add .` | Stages within current pathspec scope | Stages within current pathspec scope if not ignored | No |
| `git commit -m "..."` | Does not auto-stage unstaged edits | Does not auto-stage | Yes, from the current index |

### git add -u: Only Update Tracked Paths

~~~bash
git add -u
~~~

This command stages modifications and deletions on tracked paths within the applicable scope. It does not add untracked files.

You can then inspect the index contents:

~~~bash
git diff --cached
git status --short
~~~

Once satisfied, create the commit:

~~~bash
git commit -m "Update tracked files"
~~~

This approach is useful when you want to separate staging from committing so you can review what will be written to history.

### git add -A: Add, Modify, and Delete

~~~bash
git add -A
~~~

This command updates the index with all changes Git sees within the applicable scope: new files, modified files, and deleted files. Ignored files are still not added in the normal way.

When run from the repository root, it is commonly used to stage all valid repository changes. Then review and commit:

~~~bash
git diff --cached --stat
git diff --cached
git commit -m "Update project"
~~~

### git add .: Depends on Current Directory

~~~bash
git add .
~~~

The `.` is a pathspec for the current directory. Therefore, if run from a subdirectory, the staging scope may cover only that directory and paths beneath it, not necessarily the entire repository.

Pay attention to your current working directory when using this command. If you want to stage the entire repository, move to the root and run `git add -A`.

## 5. File Deletion and Renaming Scenarios

`git commit -a` automatically stages the deletion of a tracked file. However, if you rename a file manually via a file manager or OS command, Git may see two events:

- The old path is tracked and has been deleted.
- The new path is untracked.

Manual rename example:

~~~text
src/old-name.js  ->  src/new-name.js
~~~

If the new path has not been staged, running:

~~~bash
git commit -am "Rename module"
~~~

may commit only the deletion of `src/old-name.js`. `src/new-name.js` remains untracked. Git normally detects renames by comparing content after paths are staged/committed; a rename is not a separate object type inside a commit.

The explicit way is to use `git mv`:

~~~bash
git mv src/old-name.js src/new-name.js
git status --short
git commit -m "Rename module"
~~~

`git mv` updates the index for the rename operation. If you renamed manually, stage both the new path and the deletion of the old path:

~~~bash
git add -A -- src/old-name.js src/new-name.js
git diff --cached --summary
git commit -m "Rename module"
~~~

## 6. -a Can Undo Partial Staging Intent

This is an important limitation when you use `git add -p` to split one file across multiple commits.

Suppose `src/app.js` has two independent changes:

- Hunk A: fixes a billing calculation bug.
- Hunk B: adds debug logging.

You only want to stage hunk A:

~~~bash
git add -p src/app.js
~~~

Then inspect:

~~~bash
git diff --cached -- src/app.js
git diff -- src/app.js
~~~

`git diff --cached` shows hunk A staged; `git diff` shows hunk B remaining in the working tree.

If you next run:

~~~bash
git commit -am "Fix invoice calculation"
~~~

`-a` automatically stages current working-tree changes of tracked file `src/app.js`. This can pull hunk B into the index as well, putting both changes into the commit. Therefore, `git commit -a` is unsuitable when you want to preserve partial staging boundaries on modified tracked files.

To keep only what was selected, run:

~~~bash
git commit -m "Fix invoice calculation"
~~~

A regular `git commit` commits only what is already in the index. Hunk B stays in the working tree for you to handle in a later commit.

If you want tight control over individual parts, the workflow should be:

~~~bash
git add -p src/app.js
git diff --cached
git diff
git commit -m "Fix invoice calculation"
~~~

Before committing, check other staged files as well, because committing always uses the entire index, not just the single hunk you most recently selected.

## 7. git commit -a Still Commits Everything Already Staged

The `-a` flag might make you think the commit includes only the tracked changes it auto-stages. In practice, the commit command still takes the entire index.

For example:

~~~bash
git add docs/new-guide.md
git add src/feature.js
git commit -am "Update feature"
~~~

The commit will include both `docs/new-guide.md` and `src/feature.js`, if both are staged. If you do not want `docs/new-guide.md` in this commit, inspect the index first and unstage that path:

~~~bash
git restore --staged -- docs/new-guide.md
git diff --cached --name-status
git commit -am "Update feature"
~~~

`git restore --staged` removes the change from the index while keeping working tree content. For a repository without an initial commit yet, note that `HEAD` does not exist yet; you can use `git rm --cached` for a newly staged file you want to keep on disk.

Avoid running `git commit -a` without knowing what is currently in the index.

## 8. Ignored Files and Tracked Files

`.gitignore` mainly prevents untracked files from being added to the index normally. It does not automatically stop tracking files that have already been committed.

For example, `config/local.yml` is already tracked, and later you add a pattern to `.gitignore`:

~~~gitignore
config/local.yml
~~~

The file remains tracked. If you edit it, `git commit -a` can still stage the edit and commit the new content.

To check whether a file is tracked:

~~~bash
git ls-files -- config/local.yml
~~~

To check ignore rules:

~~~bash
git check-ignore -v -- config/local.yml
~~~

If a file is already tracked and the team decides to stop tracking it, intentionally update the index, for example:

~~~bash
git rm --cached -- config/local.yml
~~~

This command keeps the local file on disk while removing it from the index for the next commit. Coordinate with your team before changing a configuration file shared across multiple members.

## 9. How to Check Before Using git commit -a

Before running commit, check overall status:

~~~bash
git status --short
~~~

View unstaged changes:

~~~bash
git diff
~~~

View staged content:

~~~bash
git diff --cached
~~~

List untracked files that are not ignored:

~~~bash
git ls-files --others --exclude-standard
~~~

List ignored files if you need to audit them:

~~~bash
git ls-files --others --ignored --exclude-standard
~~~

You can also ask Git to run a dry-run preview:

~~~bash
git commit --dry-run -a
~~~

Dry-run previews a summary of what the commit command expects to process without creating a commit. To review the exact content that will be committed, inspect the index and working tree diffs; if you want to verify the auto-staging step separately, run `git add -u`, inspect `git diff --cached`, and then commit with a regular `git commit`.

Note that `git add -u` updates the index for tracked files. If you are relying on partial staging, this operation can also overwrite your selective staging for those files. Choose the workflow that matches your commit intent.

## 10. Practical Example: Committing Both Tracked Edits and New Files

Suppose you are working on a feature and have these changes:

~~~text
 M src/payment.js
 M README.md
?? tests/payment-new.test.js
?? docs/payment-flow.md
~~~

You want to commit all four paths.

Using `git commit -a` alone will skip the two new files. There are two appropriate approaches.

**Option 1: Stage the new files first, then use -a for tracked changes**

~~~bash
git add tests/payment-new.test.js docs/payment-flow.md
git commit -am "Add payment flow and tests"
~~~

The commit includes the newly staged files and the tracked changes auto-staged by `-a`.

**Option 2: Stage everything, then commit normally**

~~~bash
git add -A
git diff --cached --stat
git diff --cached
git commit -m "Add payment flow and tests"
~~~

The second option lets you review the index before committing. This is usually easier to control when changes span multiple file types or require careful content inspection.

## 11. When Should You Use or Avoid git commit -a?

| Scenario | Should You Use -a? | Reason |
| --- | --- | --- |
| Edited a few tracked files and want a quick commit | Acceptable | -a auto-stages modifications |
| Deleted tracked files and want to commit the deletion | Acceptable | -a auto-stages deletions |
| Have unstaged new files | Not sufficient | New files will be skipped |
| New files were staged beforehand | Acceptable, after reviewing index | Commit will include staged additions too |
| Using git add -p for partial commits | Avoid | -a may stage unselected hunks |
| Index already holds changes from other work | Check carefully | Commit will include the entire index |
| Want full review before committing | Prefer explicit staging | git add separately then inspect git diff --cached |

`git commit -a` works well for quick operations on tracked files when you intentionally want to commit all their changes. When new files, partial staging, or multiple independent changes are involved, explicit staging is usually easier to control.

## 12. Decision Flowchart

~~~mermaid
flowchart TD
    A[Need to create a commit] --> B{Tracked files modified or deleted?}
    B -- No --> C{Any staged content?}
    B -- Yes --> D{New untracked files to commit?}
    D -- No --> E{Partial staging needed?}
    E -- No --> F[git commit -a -m]
    E -- Yes --> G[Review index and run git commit]
    D -- Yes --> H[Stage new files with git add]
    H --> I{Auto-stage all tracked changes?}
    I -- Yes --> J[Review index then git commit -a]
    I -- No --> K[Stage selectively then git commit]
    C -- Yes --> L[Review git diff --cached then git commit]
    C -- No --> M[Check status and decide what to stage]
~~~

Before using `git commit -a`, verify for yourself:

1. Are all files I want to commit already tracked or already staged?
2. Are there any new untracked files that need to be added with `git add`?
3. Are there staged changes from other work sitting in the index?
4. Am I using partial staging and needing to keep unselected hunks out?
5. Have I checked `git diff`, `git diff --cached`, and `git status`?
6. Does the commit message accurately describe everything that will be committed?

`git commit -a` is a convenience option to auto-stage modifications and deletions of tracked files before committing. It does not auto-add new untracked files, yet it still commits everything already present in the index. Once you understand the boundary between the working tree, the index, and tracked files, you will know when `-a` is quick and safe and when explicit staging is needed to keep commits accurate.

## References

- [Git documentation: git-commit](https://git-scm.com/docs/git-commit) — behavior of `-a`, `--all`, `--dry-run`, and committing from the index.
- [Git documentation: git-add](https://git-scm.com/docs/git-add) — updating the index with new, modified, and deleted files.
- [Git documentation: git-status](https://git-scm.com/docs/git-status) — distinguishing staged, unstaged, and untracked files.
- [Git documentation: git-diff](https://git-scm.com/docs/git-diff) — viewing differences across the working tree, index, and commits.
- [Pro Git: Recording Changes to the Repository](https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository) — the staging area and commit workflow.

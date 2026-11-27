# Git reset --hard and Conditions for Protecting Uncommitted Changes

The **git reset --hard** command moves the current branch (or detached HEAD) to a target commit while updating the staging area and working tree to match that commit. This is a powerful operation: staged and unstaged changes on files tracked by Git can be removed from the working tree. If you have not checked the repository state and protected the work you need to keep, you can lose uncommitted edits.

Within the **Switching and Undoing** chapter of the **SOURCE_CONTROL_GIT** module, this lesson focuses on accurately understanding the impact of a hard reset and the conditions to verify before running it. The goal is to know when to use the command to bring a repository to a desired state, how to protect work in progress, and how to handle an accidental reset.

After this lesson, you will be able to:

- Explain how a hard reset changes HEAD, the index, and the working tree.
- Distinguish between committed snapshots, staged changes, unstaged changes, untracked files, and ignored files.
- Inspect repository state before resetting.
- Protect work using a commit, stash, or appropriate backup copy.
- Choose a target commit and verify the result after resetting.
- Recognize recovery limits after running an unintended reset.

## 1. Three Areas to Understand Before Resetting

Git works with three main areas:

1. **HEAD and commit history**: HEAD usually points to the current commit through the checked-out branch. A commit stores a snapshot of the content recorded at the time of the commit.
2. **Index (staging area)**: holds the content that will go into the next commit. A file can have a staged version that differs from its current content in the working tree.
3. **Working tree**: the files and directories currently visible in the working directory. This is where you edit source code and documentation.

Beyond these three areas, there are **untracked** files not yet managed by Git and **ignored** files excluded from normal status by ignore rules. Neither of these file types is a commit or content in the index.

For example, after editing a file and staging part of it:

~~~text
HEAD (commit A)
       |
       v
Index:        staged version
Working tree: latest version being edited
Untracked:    new file not yet tracked by Git
~~~

Before running a reset command, identify which changes reside in each area. A git status check shows modified, staged, or untracked files; diff commands help read the exact differences.

## 2. What Does git reset --hard Affect?

General syntax:

~~~bash
git reset --hard <commit>
~~~

Git performs three main actions:

- Moves HEAD and the current branch to the target commit.
- Makes the index match the target commit's snapshot.
- Updates the working tree to match that index.

As a result, the tracked state in both the index and working tree is reset to the target commit. Staged or unstaged changes on tracked files will be replaced by the target commit's content.

For example, the current branch is at commit C and you want to move back to B:

~~~text
Before:
A---B---C  (HEAD -> feature)

After git reset --hard B:
A---B      (HEAD -> feature)
     \
      C    (no longer pointed to by branch feature)
~~~

The feature branch now points to B. Commit C is no longer in the history reachable from that branch, though it may still be found via the reflog for a period of time. Reset does not immediately delete all data of commit C from the Git object database.

If run without specifying a target commit:

~~~bash
git reset --hard
~~~

Git uses the current HEAD as the target. This command does not move the branch to another commit, yet it still makes the index and working tree match HEAD. Thus, staged and unstaged tracked changes can be discarded.

**Important point:** reset does not switch to another branch. It moves the current reference (when HEAD is attached to a branch) and updates the working content to match the target commit. If HEAD is detached, it updates the detached HEAD.

## 3. Distinguishing reset --soft, --mixed, and --hard

The three reset modes differ in how they handle the index and working tree:

| Mode | Moves HEAD/branch | Updates index | Updates working tree |
| --- | --- | --- | --- |
| --soft | Yes | Unchanged | Unchanged |
| --mixed | Yes | Resets to target commit | Keeps changes in files |
| --hard | Yes | Resets to target commit | Resets to target commit |

If no mode is specified, git reset defaults to --mixed.

For example, if the current branch is at C and you want to go back to B:

~~~bash
git reset --soft B
~~~

Commit C is removed from the current branch tip, yet commit C's changes remain in the index and working tree. They are ready to create a different commit.

~~~bash
git reset --mixed B
~~~

Commit C is removed from the current branch tip. The index returns to B, while the changes are kept in the working tree as unstaged. This is commonly used when you want to revise content or re-split staging before committing.

~~~bash
git reset --hard B
~~~

Commit C is removed from the current branch tip, and both the index and working tree are reset to B. Uncommitted tracked changes are no longer in the working tree.

Choose the mode according to your desired outcome. If you only want to unstage a file while keeping edits in the working tree, using git restore --staged <file> is usually clearer than resetting the entire branch. If you want to discard working tree changes for one file, you can use git restore <file> after confirming you do not need that content.

## 4. Which Changes Are at Risk of Being Lost?

Not every type of file is handled the same way when running a hard reset.

| Content type | Typical impact of git reset --hard |
| --- | --- |
| Already-created commit | The current branch may be moved away from that commit if the target commit is older. The commit can still be recovered via reflog while retained. |
| Staged tracked changes | Index and working tree are reset to the target commit; uncommitted content may be lost. |
| Unstaged tracked changes | Working tree is updated to match the target commit; uncommitted content may be lost. |
| Untracked files not obstructing tracked files | Usually left intact. |
| Untracked files or directories obstructing writing a tracked file from the target commit | Git may delete them in order to write the required tracked content. |
| Ignored files | Usually left intact, though they can be affected if they obstruct checking out/writing a tracked path. |

Therefore, saying that a hard reset deletes all untracked files is inaccurate. The command primarily synchronizes tracked content with the target commit, though untracked files can be deleted if they sit in a location that blocks Git from writing a tracked file. Ignored files should not be assumed safe in every situation either.

The git clean command is a separate tool for deleting untracked files. For example:

~~~bash
git clean -nd
~~~

The -n option only previews and -d includes untracked directories. Do not add -f before carefully reviewing the list; git clean -fd actually deletes the listed items. Ignored files require other options such as -X or -x, and need even more careful previewing because they may include build outputs, local data, or private configuration files.

## 5. Conditions for Protecting Uncommitted Changes

Before running git reset --hard, verify the following conditions:

1. **Know the exact target commit**: confirm the exact branch, commit hash, or remote-tracking branch you want to reset to.
2. **Inspected the working tree**: know which files are staged, which have unstaged edits, which are untracked, and which ignored files hold valuable data to keep.
3. **No tracked changes left to keep in the index or working tree**, or they have already been saved in a recoverable place.
4. **Protected untracked/ignored files that could be overwritten** if they share paths with tracked files in the target commit.
5. **Understood the impact on history**: if resetting back past already-pushed commits, the local branch will differ from the remote; do not force-push over shared history without coordination.
6. **Have a way to verify after the operation**: know what the current commit should be and which files need checking.

A clean working tree is a favorable condition but not sufficient to conclude all local data is safe. git status does not list ignored files by default, and untracked files may not appear in condensed status output unless you request detailed display. Check the exact file types that could be affected.

## 6. Pre-Reset Verification Workflow

### Step 1: identify the current repository and branch

~~~bash
git status -sb
git branch --show-current
git log -1 --oneline --decorate
~~~

Read the current branch name and commit. If in detached HEAD state, understand that reset will move the detached HEAD; if you need to keep the current state, create a protective branch first.

### Step 2: view staged and unstaged changes

~~~bash
git diff --cached
git diff
~~~

git diff --cached shows the content in the index compared to HEAD. git diff shows changes in the working tree compared to the index. Read both so you do not miss cases where a file has part staged and another part unstaged.

### Step 3: list untracked files

~~~bash
git status --short --untracked-files=all
~~~

The --untracked-files=all option displays individual untracked files instead of collapsing directories. Identify which files contain data to keep and whether the target commit has tracked files at the same paths.

### Step 4: check ignored files when needed

~~~bash
git status --short --ignored
~~~

This command helps identify ignored files, such as local config files, caches, build directories, or generated data. Not all ignored files are important, but some may contain data that is hard to recreate. If they sit on paths where the target commit needs to write tracked files, back them up first.

### Step 5: verify the target commit

~~~bash
git show --no-patch --oneline <target>
git log --oneline --decorate -8 <target>
~~~

Replace <target> with the intended commit hash or reference, such as HEAD~1 or origin/main. Make sure that commit belongs to the right repository and branch you intend to use as a baseline.

### Step 6: decide whether to reset or add further protection

If all uncommitted tracked changes can be discarded and no important untracked/ignored files are blocked by tracked paths, you may proceed. When in doubt, commit or stash before resetting.

## 7. Protecting Work Before Running reset --hard

There are multiple ways to save changes. Choose the method suited to the content type and your workflow goal.

### Method 1: create a temporary commit when changes are clear enough

If the changes are meaningful and can be saved as a commit, create a temporary commit:

~~~bash
git add -A
git diff --cached
git commit -m "wip: save work before reset"
~~~

A commit saves the tracked snapshot and newly staged files. Afterward, if you need to keep the current point even though the branch will be reset, you can create a protective branch:

~~~bash
git branch backup/before-reset
~~~

Do not create a temporary commit if gathering all files with git add -A could accidentally include secrets, auto-generated files, or unrelated data. Inspect the staged diff before committing.

### Method 2: use stash for work in progress

Stash saves staged and unstaged tracked changes so the working tree becomes cleaner:

~~~bash
git stash push -m "before reset --hard"
~~~

If you want to save untracked files as well:

~~~bash
git stash push -u -m "before reset --hard"
~~~

The -u (or --include-untracked) option includes untracked files in the stash. Ignored files are not included with -u; if you truly need to save ignored files too, you can use -a:

~~~bash
git stash push -a -m "before reset --hard"
~~~

-a includes ignored files, which can make the stash very large or store auto-generated data. Only use it after confirming those files need protection.

After stashing, check:

~~~bash
git status --short --untracked-files=all
git stash list
~~~

Confirm the new stash appears and the changes you need to keep are saved. Do not rely solely on the working tree looking clean; inspect the stash contents if the work is important.

Once the reset is finished, apply the stash:

~~~bash
git stash apply --index 'stash@{0}'
~~~

--index asks Git to attempt restoring the original staging state as well. If applying succeeds, inspect diffs, run tests, and confirm all files are intact. Only delete the stash after verifying the content has been recovered:

~~~bash
git stash drop 'stash@{0}'
~~~

If conflicts occur when applying, resolve them like an integration of changes. Keep the stash until you confirm all content is recovered.

### Method 3: save patches and back up untracked files separately

For tracked changes, you can save diffs to files in a safe location, ideally outside the working tree:

~~~bash
git diff > working-tree.patch
git diff --cached > staged.patch
~~~

git diff writes a patch for unstaged changes (working tree vs. index). git diff --cached writes a patch for staged changes (index vs. HEAD). These two patches do not contain untracked file contents and are not a full backup of the repository. Copy untracked files or local data you need to keep to a separate safe location.

After resetting, you can inspect the patches before applying them:

~~~bash
git apply --stat working-tree.patch
git apply --stat staged.patch
~~~

Re-applying patches may need adjustment if the target content has changed. Do not delete patch copies or backup files before verifying the result.

## 8. Performing a Controlled reset --hard

Once you have verified the target commit and protected any changes you need to keep, run the command:

~~~bash
git reset --hard <target>
~~~

For example, reset the current branch to the immediately preceding commit:

~~~bash
git reset --hard HEAD~1
~~~

Or align the local branch to the exact state of a remote-tracking branch after fetching:

~~~bash
git fetch origin
git reset --hard origin/main
~~~

The second command moves the current local branch to the commit referenced by origin/main. Make sure you are on the exact local branch you intend to change. If the local branch has unshared local commits, resetting to origin/main will leave the branch no longer pointing to those commits; create a protective branch or save commits first if you need to keep them.

After the command succeeds, check:

~~~bash
git status -sb
git log -1 --oneline --decorate
git diff
git diff --cached
~~~

Confirm HEAD is on the target commit and the index and working tree have no unexpected tracked changes. Verify important untracked and ignored files remain intact if they needed protection.

## 9. Cases Where You Should Not Run It Immediately

### Working tree still has unreviewed changes

If git status shows modified or staged files whose diffs you have not read and you have not decided whether to keep them, conditions are not met for a hard reset. Categorize and commit, stash, or back them up first.

### Untracked files contain important data

Untracked files are not always deleted by reset, yet they can be deleted if they block Git from writing a tracked file from the target commit. If that data is important, stash with -u or copy it to a safe location first.

### Ignored files contain local data

Ignored files usually do not appear in standard git status output. Check git status --ignored and back up important files if there is any chance of overwriting them. Do not use git clean -fdx as a casual cleanup step; that command can delete ignored files too.

### On a shared branch and intending to reset history backward

Resetting a local branch to an older commit does not by itself change the remote. However, if you subsequently force-push, remote history can be rewritten and affect teammates. Coordinate beforehand, check remote state, and use --force-with-lease if your workflow permits rewriting history.

### Unsure whether the target commit is right

Do not use HEAD~1, origin/main, or a hash copied from elsewhere out of habit. Inspect the commit with git show, log, and branch names before running. A syntactically valid commit target can still be the wrong point functionally.

## 10. If You Accidentally Ran reset --hard

First, stop further overwriting operations. Do not run additional resets, cleans, garbage collection, or repository cleanup operations before checking recovery options.

### Check the reflog

Reflog records local reference updates, including HEAD movements. View the history:

~~~bash
git reflog --date=local
~~~

Find the entry right before the accidental reset. You can inspect that commit:

~~~bash
git show --stat <old-commit>
~~~

If confirmed as the commit to recover, create a protective branch pointing to the old commit:

~~~bash
git branch rescue/before-reset <old-commit>
~~~

You can then decide whether to move the current branch back to this commit or cherry-pick the needed commits. Creating a rescue branch keeps a reference to the commit while you continue investigating.

Git usually updates ORIG_HEAD during a reset, though this value can be overwritten by other operations. Inspect it before using it:

~~~bash
git show --no-patch --oneline ORIG_HEAD
~~~

Do not assume ORIG_HEAD is always the desired commit.

### Recovery limits for uncommitted changes

Reflog tracks references and commits, not snapshots of every content state ever present in the working tree. If a hard reset replaced uncommitted tracked changes, Git usually has no commit or reflog entry to restore that exact content.

You can try checking your IDE's local history, system backups, patch files, previously created stashes, or data recovery tools. Results depend on the tool and system; there is no guarantee uncommitted content can be recovered. This is why changes must be protected before running the command.

## 11. Common Confusions

### Does git reset --hard delete commits from the repository immediately?

No. The command moves the branch away from old commits. Commits can still be found via reflog or other references for a period of time. Once no references remain and the retention period expires, Git may prune unused objects.

### Does git reset --hard delete all untracked files?

No. Untracked files are generally kept if they do not block writing tracked files from the target commit. However, an untracked file sitting at the exact path Git needs to create or update may be deleted. Check and back it up if you need to keep it.

### Is git reset --hard the same as git clean?

No. Reset synchronizes HEAD, the index, and the tracked working tree to the target commit. Clean deletes untracked files according to specified options. The two commands have different scopes; do not combine them without understanding the list of files that will be deleted.

### Can you use git reset --hard to discard a single file?

If you only want to restore one tracked file, use git restore --source=HEAD --staged --worktree -- <file> after confirming you do not need that file's changes. This command only affects the specified path, avoiding resetting the entire branch.

### Does stash save ignored files?

Not with the default stash command or -u. To include ignored files in a stash, use -a; consider size and local data before choosing it.

## 12. Self-Check Before a Reset

Suppose branch feature/report is at commit C, and commit B is the previous commit. You edited ReportService.java, staged part of the changes, created an untracked file report-local.json, and have an ignored local configuration file.

Before running:

~~~bash
git reset --hard B
~~~

Ask yourself:

1. What will the command do to HEAD, the index, and the working tree?
2. Will the staged and unstaged parts of ReportService.java be preserved?
3. Is report-local.json guaranteed to be safe?
4. Which command is needed to check for ignored files?
5. If you want to keep all tracked changes and untracked files before resetting, which command can you use?
6. After resetting, if you realize you dropped a needed commit from the branch, where should you check first?

**Hint:** HEAD/branch, index, and tracked working tree will be reset to B. Both parts of the tracked file's changes may be lost. Untracked files usually remain if they do not obstruct tracked paths in B, though you should not rely on that assumption if the data is important. Use git status --short --ignored to see ignored files. Use git stash push -u -m "before reset --hard" to save tracked and untracked changes; if you also need to keep ignored files, consider -a. If a commit was dropped from the branch, inspect git reflog and create a rescue branch once the right commit is identified.

## Conclusion

git reset --hard sets HEAD/branch, the index, and the tracked working tree to a target commit, so it can discard uncommitted tracked changes. Before running it, confirm the right repository, branch, and commit; inspect staged, unstaged, untracked, and ignored files; protect work to keep with a commit, stash, or backup copy; and read back the status afterward. Reflog can help find commits dropped from the branch tip, but does not guarantee recovery of uncommitted working tree content. Discipline in checking and backing up before resetting is the most reliable way to avoid losing work.

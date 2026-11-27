# Resolving Conflicts When Applying a Stash and Creating a Branch with stash branch

## What does stash save and when can conflicts occur?

Git stash helps temporarily shelve uncommitted changes so you can switch to other work. When needed, you reapply the shelved content into the current working tree. Stash normally saves changes in files tracked by Git; additional options can include untracked or ignored files in the stash.

Stash is not a regular commit on the current branch and is not a long-term backup. Stash entries are stored in a separate list, typically referenced by names such as stash@{0}, stash@{1}. The newest entry normally has index 0.

A stash can apply cleanly when the current branch is still close to the state when the stash was created. Conflicts can appear when:

- The current branch modified the same code region as the shelved changes.
- A file was renamed or deleted after creating the stash.
- Another branch created a file at the same path as an untracked file in the stash.
- Configuration, dependencies, or directory structure changed.
- Shelved changes depend on a commit or API that no longer exists on the current branch.

When Git cannot merge automatically, the apply or pop operation stops with files in an unmerged state. You need to resolve the contents just as when handling a merge conflict, then verify and stage the result.

Two things to remember from the start:

- git stash apply applies the stash while keeping the entry in the list so it can be reused or deleted later.
- git stash pop both applies and attempts to delete the entry if application succeeds. If there is a conflict, Git does not delete that entry.

## Checking the stash before applying

Before bringing changes back, view the stash list:

~~~bash
git stash list
~~~

Example:

~~~text
stash@{0}: On feature/search: WIP add search filters
stash@{1}: On main: WIP update report layout
stash@{2}: On fix/login: WIP handle expired session
~~~

Each entry can have a message to help identify the work. If you need to view a summary:

~~~bash
git stash show 'stash@{0}'
~~~

View the full patch of the stash:

~~~bash
git stash show -p 'stash@{0}'
~~~

You can also view untracked files saved in the stash using:

~~~bash
git stash show --include-untracked -p 'stash@{0}'
~~~

If the stash was created with an option including ignored files, inspect those files carefully before applying. Build files, caches, or local data may not belong on another branch.

Before applying or popping, check the working tree status:

~~~bash
git status
git branch --show-current
~~~

If the working tree already has uncommitted changes, clearly understand which task they belong to. Applying a stash onto a working tree containing other changes can cause extra conflicts or make it hard to distinguish the origin of each change.

### Choosing the right stash entry

Do not assume stash@{0} is always the entry to apply. If there are multiple stashes, read the message and contents of each entry.

You can view the base commit from which the stash was created:

~~~bash
git log -1 --oneline 'stash@{0}^1'
~~~

A stash entry has its own commit structure, where the first parent represents the HEAD commit at the time the stash was created. This information is useful when you need to identify the original branch or base state.

If you want to view all metadata of the stash:

~~~bash
git show --no-patch --pretty=raw 'stash@{0}'
~~~

Note down the right entry before operating. Stash indices can shift when adding or deleting other entries.

## Applying a stash with git stash apply

The apply command brings the stash's contents into the current working tree:

~~~bash
git stash apply 'stash@{0}'
~~~

If no entry is passed, Git applies the newest stash by default. In team collaboration or when multiple stashes exist, specify the entry explicitly to avoid picking the wrong one.

After applying, check:

~~~bash
git status
git diff
git diff --cached
~~~

Normally, changes are applied to the working tree. If the stash also stored staged content, you can use the --index option to ask Git to restore the staging state as well:

~~~bash
git stash apply --index 'stash@{0}'
~~~

--index is useful when you want to keep the distinction between staged and unstaged parts as they were when the stash was created. However, restoring the index can fail if the current state has conflicts or cannot recreate the old entries cleanly. In that case, check git status and decide to re-stage manually after resolving.

Unlike pop, apply does not automatically delete the stash entry after succeeding. You can inspect, run tests, commit, or reapply the stash at another time.

## Recognizing conflicts after apply or pop

Suppose you shelved changes to SearchService on the feature/search branch. Meanwhile, the main branch modified the same method. When switching to main and applying the stash, Git cannot combine the two versions automatically.

Start with:

~~~bash
git status
~~~

Git will list paths currently in both modified, added by us, deleted by them, or the corresponding unmerged state.

To list the exact paths still in conflict:

~~~bash
git diff --name-only --diff-filter=U
git ls-files -u
~~~

For standard content conflicts, the index has these stages:

| Stage | Meaning |
|---|---|
| 1 | Common base version (merge base), if any |
| 2 | Current side version (ours) |
| 3 | Applied side version from stash (theirs) |

In the context of applying a stash, understanding ours/theirs must align with the Git operation being performed. Ours is usually the content of the current branch and working tree; theirs is the content taken from the stash. Do not pick one side entirely based only on the name, because you might lose changes on the other side.

View the versions currently in the index:

~~~bash
git show :1:src/SearchService.java
git show :2:src/SearchService.java
git show :3:src/SearchService.java
~~~

Some conflict types like add/add, modify/delete, or rename do not have all three stages. If a command cannot find a corresponding stage, check the conflict type and file status.

## Conflict resolution workflow after stash apply

### Step 1: Identify shelved changes and current changes

Before editing, view the stash patch:

~~~bash
git stash show -p 'stash@{0}'
~~~

View the working tree diff and index status:

~~~bash
git diff
git diff --cached
git status
~~~

If needed, inspect each side's content using git show :1:, :2:, and :3: as above.

Determine:

- Which changes already exist on the current branch?
- What behavior does the stash intend to add or modify?
- Can both parts be combined while preserving correct logic?
- Do any APIs, configurations, schemas, or tests depend on this change?
- Are there any added, deleted, or renamed files requiring a clear decision?

### Step 2: Edit the final content

For example, the current branch added a permission check, while the stash contains changes adding a date filter for reports. Both changes touch the same method:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    // Permission check and date filter are conflicting here
}
~~~

The final result needs to preserve both behaviors:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    permissionService.requireCanExport(user);

    return reportService.createReport(filter);
}
~~~

This is an illustrative example. For real source code, check authorization conditions, empty-filter handling, time zones, and edge cases according to the application's contract.

If the conflict is in a configuration file, verify keys, data types, default values, and profiles. If it is in a dependency manifest or lockfile, confirm compatible versions and regenerate the lockfile following the project's workflow. For deleted or renamed files, clearly decide the final path that should exist.

### Step 3: Search for conflict markers

Text files may contain these markers:

~~~text
<<<<<<< HEAD
Current side content
=======
Content taken from stash
>>>>>>> Stashed changes
~~~

After editing, search for markers in the files that had conflicts:

~~~bash
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/SearchService.java config/application.yml
~~~

If there are no matches and the command returns exit code 1, no matching lines were found. If the tool reports an error reading a file or path, resolve that error before drawing conclusions. Marker strings can legitimately appear in documentation or test fixtures, so evaluate them in context.

### Step 4: Re-read the diff

~~~bash
git diff
git diff --check
~~~

Ensure the final content preserves the intent of both current changes and the stash. Do not simply delete markers to stop Git from reporting conflicts; verify logic, error handling, security checks, and edge cases.

### Step 5: Stage the result

Once resolved, add each file to the staging area:

~~~bash
git add -- src/SearchService.java config/application.yml
~~~

If deciding to delete a file:

~~~bash
git rm -- path/to/obsolete-file
~~~

Verify status and staged diff:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git diff --cached
git diff --cached --check
~~~

Having no unmerged paths left is a prerequisite to proceed. If you want to keep part of the changes unstaged, you can use git add -p to pick parts selectively; then check both git diff and git diff --cached.

### Step 6: Verify behavior after combining

Run checks close to what was edited:

- Unit tests for the related class or package.
- Syntax or config-loading checks if configuration files had conflicts.
- Build of the affected module.
- Integration tests if the changes involve APIs, databases, or inter-component communication.

If the stash was created from another branch, verify whether the applied changes remain compatible with the current code version. Git having no remaining conflicts does not guarantee the functionality works properly.

## What happens to the stash after apply or pop?

This is a key difference when handling conflicts.

### After git stash apply

Apply does not delete the stash entry, even when application succeeds:

~~~bash
git stash apply 'stash@{0}'
git stash list
~~~

If there is a conflict, the stash is still kept. After resolving, staging, testing, and committing if needed, you can keep the entry as a backup or delete it manually once certain it is no longer needed:

~~~bash
git stash drop 'stash@{0}'
~~~

Before dropping, re-check the list because stash indices can change if new stashes were created or other entries were deleted while working. Do not drop an entry just because apply finished running; confirm the contents were completely restored.

### After git stash pop

Pop applies the stash and then tries to delete the entry if application succeeds:

~~~bash
git stash pop 'stash@{0}'
~~~

If pop encounters a conflict, Git does not delete the stash entry. You resolve the files and continue working as with normal changes in the working tree. There is no git stash --continue command for this operation.

After resolving conflicts, check:

~~~bash
git status
git stash list
~~~

If the stash still exists and you have confirmed the contents were fully applied, you can delete the entry with:

~~~bash
git stash drop 'stash@{0}'
~~~

If unsure, keep the stash. You can review the patch again, run tests, or create a safe commit before deciding to drop.

### Do not reapply the stash just because conflicts remain

When apply or pop has stopped due to conflicts, the changes have already been partially placed into the working tree and index. Do not immediately re-run the same apply/pop command, as that can make the state harder to understand or create more conflicts.

Resolve the current state first. The stash entry remains intact so you can compare against it or retry on another branch if needed.

## Creating a branch from a stash with git stash branch

Sometimes a stash was created on a branch with an older code base. Later, you switch to a branch that has changed significantly and apply encounters conflicts. If the shelved changes belong to the old base, an appropriate approach can be creating a new branch directly from the stash's original base commit.

Syntax:

~~~bash
git stash branch <branch-name> [<stash>]
~~~

Example:

~~~bash
git stash branch feature/resume-search 'stash@{0}'
~~~

Git will:

1. Create and switch to the branch feature/resume-search.
2. Position the new branch at the commit where the stash was created.
3. Apply the changes saved in the stash into the working tree and index of the new branch.
4. If application succeeds, delete the specified stash entry.

This approach is useful when the current branch has moved far ahead of the original base and the stash cannot apply cleanly. Starting from the original commit usually helps Git find a context close to when the changes were created.

The command does not automatically create a commit for the restored contents. After creating the branch, you still need to check status, read the diff, run tests, and commit according to workflow.

### Why can stash branch reduce conflicts?

Suppose you created a stash on feature/search at commit A. Later, main advances to commit D and you switch to main. If you apply the stash directly onto D, files may have changed significantly.

~~~text
A---B---C---D  main
^
feature/search at A when stash was created
~~~

The stash entry stores changes based on commit A; it is saved separately and is not a Git branch. If you apply the stash onto D, Git has to combine changes created on base A with current code at D. If both sides edited the same area, conflicts can arise.

Using stash branch:

~~~bash
git stash branch feature/resume-search 'stash@{0}'
~~~

Git creates the branch from A and applies the stash at the original base. Then you can inspect, commit the work, and update the branch according to your team's merge or rebase workflow.

This brings the work back into its original context. It does not guarantee zero conflicts: if the stash itself has changes incompatible with the base commit or contains file conflicts, you will still need to resolve them.

### If stash branch encounters conflicts

If creating the branch succeeds yet applying the stash stops due to conflicts:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

You are on the new branch created from the stash's base. Resolve conflicts as in a normal apply workflow: edit, check markers, stage files, and run tests.

There is no git stash branch --continue command. After resolving, continue working on the new branch and check the stash list. Git only auto-drops the stash when the apply step of stash branch succeeds; if an error occurred, do not assume the entry was deleted.

If the stash remains, drop it only after confirming the changes were fully restored:

~~~bash
git stash list
git stash drop 'stash@{0}'
~~~

Make sure stash@{0} is still the right entry before dropping; indices may shift according to the current list.

Before calling git stash branch, ensure the working tree and index allow switching to the stash's base commit. If a previous git stash apply left conflicts behind, do not run stash branch directly on that unmerged state. Finish the current resolution or intentionally restore the repository to the pre-apply state while preserving all prior changes; only then create a branch from the stash.

## Comparing apply, pop, and branch

| Command | Where it applies | Stash entry after success | On conflict |
|---|---|---|---|
| git stash apply | Current working tree | Kept | Resolve like normal changes; stash remains |
| git stash pop | Current working tree | Deleted if apply succeeds | Entry not deleted on conflict |
| git stash branch | New branch from stash's original base commit | Deleted if apply succeeds | Resolve on the new branch; check entry before dropping |

Choose the command by goal:

- Use apply when you want to keep the stash to verify or possibly reapply.
- Use pop when you want to restore work and delete the stash upon success.
- Use branch when you want to restore work on the original base because the current branch has changed extensively.

## Handling untracked and ignored files

By default, git stash push does not include untracked files and ignored files.

If you want to save untracked files too:

~~~bash
git stash push -u -m "WIP include untracked files"
~~~

If you want to save ignored files too:

~~~bash
git stash push -a -m "WIP include ignored files"
~~~

When applying or popping, Git may fail to restore a file if the current working tree already has a file at the same path. This can be an untracked-file restoration error rather than a standard content conflict with markers.

Check files and status before handling:

~~~bash
git status --short
git stash show --include-untracked -p 'stash@{0}'
~~~

If there is a file with the same name, decide which content to keep and intentionally move or rename the existing file before attempting to restore. Do not overwrite a file just to make the stash command succeed.

For ignored files, especially personal machine config files, build data, or secrets, verify they truly need to be moved to the new branch before applying.

## Practical example: recovering unfinished work

Suppose you are working on a search feature, with changes in SearchService and a new test file. You need to switch to main to handle an urgent bug.

~~~bash
# Shelve work in progress, including untracked files
git stash push -u -m "WIP search filter"

# Switch to another branch and handle urgent work
git switch main

# After finishing, return to the feature branch
git switch feature/search

# View stash and contents before applying
git stash list
git stash show -p 'stash@{0}'

# Try restoring while keeping the stash
git stash apply 'stash@{0}'

# If conflicts occur, check unresolved files
git status
git diff --name-only --diff-filter=U
git ls-files -u

# Edit files, then stage and inspect
git add -- src/SearchService.java src/test/java/SearchServiceTest.java
git diff --cached
git diff --cached --check

# Run appropriate tests, then commit if changes are complete
git commit -m "Add search filter"

# Only delete the stash after confirming work is fully restored
git stash list
git stash drop 'stash@{0}'
~~~

If you know ahead of time that feature/search has diverged far from the original base, use stash branch from the start to avoid applying the stash onto a branch with an unsuitable context. If you already ran apply and hit conflicts, resolve or safely restore the pre-apply state first; do not switch branches while the index is still unmerged. Once the repository is ready, create a branch from the stash's original commit:

~~~bash
git stash branch feature/resume-search 'stash@{0}'
~~~

After creating the branch, check status, run tests, and continue working on that branch.

## Common errors

| Situation | Possible cause | How to handle |
|---|---|---|
| Apply reports conflict | Current branch modified the same region as stash | Resolve each file, stage, and verify behavior |
| Pop reports conflict | Stash cannot apply cleanly | Resolve conflicts; stash entry remains |
| New file missing after apply | Untracked file was not saved in original stash | Check whether stash was created with -u or -a |
| Apply --index fails to restore staging cleanly | Current index cannot accept the old state | Resolve conflicts then stage manually |
| Stash branch fails to create branch | Branch name already exists or invalid stash ref | Check branch name and git stash list |
| Stash still exists after pop | Pop hit conflict so entry was not dropped | Verify content before dropping manually |
| Changes lost after drop | Wrong stash deleted or recovery not verified | Inspect stash list and entry content before dropping |
| Cannot restore untracked file | Working tree already has a file at the same path | Check and resolve path collision before restoring |

## Checklist before finishing a stash operation

- [ ] Identified the right stash entry and read its message.
- [ ] Viewed the patch to know the exact shelved content.
- [ ] Checked the current branch and working tree status.
- [ ] Identified unmerged files if any conflicts occurred.
- [ ] Properly combined changes from the current branch and the stash.
- [ ] Searched for leftover markers in edited files.
- [ ] Staged the right files and read the staged diff.
- [ ] Ran checks appropriate for the changes.
- [ ] Confirmed whether the stash still exists or was deleted.
- [ ] Dropped the stash only when certain contents were completely restored.

## Key takeaways

When applying or popping a stash hits conflicts, inspect git status, the unmerged path list, and the stash patch to understand both sides before editing. Then stage the result, check the diff, and run tests just like with normal changes. Apply always keeps the stash; pop only deletes the stash when application succeeds, so the entry remains on conflict. When the current branch has diverged far from the original base, git stash branch can create a branch from the stash's base commit to recover work in a more suitable context. Always check the stash list and confirm contents were restored before dropping the entry.

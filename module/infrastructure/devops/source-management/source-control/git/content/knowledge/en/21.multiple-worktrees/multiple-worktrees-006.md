# Removing Worktrees Properly and Cleaning Stale Metadata with Prune

Git worktree allows a repository to have multiple working directories at the same time. You can keep the main branch in the main directory, open a feature branch in a second directory, and use a third directory to review another branch. Worktrees share Git data and common history, while each worktree has its own working directory, index, and HEAD.

When a piece of work ends, you need to close the worktree properly so Git releases its management information. If you only delete the directory via File Explorer or a directory removal command, Git may still retain metadata for the missing worktree. The git worktree prune command is used to clean up such stale metadata.

This lesson covers how to inspect status, safely remove a linked worktree, handle worktrees with remaining changes or locks, and use prune to clean up leftover information.

After this lesson, you will be able to:

- List worktrees and identify the worktree to remove.
- Inspect the branch, commits, and unsaved changes in that worktree.
- Use git worktree remove to properly delete a linked worktree.
- Understand when --force is needed and its risks.
- Recognize stale metadata after a worktree directory has been deleted manually.
- Use git worktree prune to preview and clean up expired metadata.
- Distinguish removing a worktree from deleting a Git branch.

## 1. What parts make up a worktree?

A repository can have a main worktree and multiple linked worktrees:

~~~text
project/
|-- .git/
|-- src/
|-- README.md
|
../project-feature/
|-- .git              <- file pointing to the linked worktree's metadata
|-- src/
|-- README.md
|
../project-review/
|-- .git              <- file pointing to the linked worktree's metadata
|-- src/
|-- README.md
~~~

The main worktree usually contains the repository's .git directory. In a linked worktree, the .git entry is usually a file pointing to the corresponding administrative directory inside the main repository, typically at .git/worktrees/ID.

Worktrees share the repository's object database and branch/tag references. Each worktree has its own HEAD and index, so you can check out different branches and stage changes independently in each directory.

Example:

| Worktree | Checked-out branch | Role |
| --- | --- | --- |
| project | main | Main work |
| project-feature | feature/search | Feature development |
| project-review | bugfix/session-timeout | Review or bug fixing |

A normal branch can only be checked out in one worktree at a time. This rule helps avoid two directories updating the same branch in confusing ways. A worktree can be in detached HEAD state if it does not check out a branch.

Removing a linked worktree does not delete the shared repository and does not automatically delete the branch that the worktree had checked out.

## 2. Listing and identifying the right worktree

Before removing, inspect all worktrees managed by the repository:

~~~bash
git worktree list
~~~

To get machine-parseable output, use:

~~~bash
git worktree list --porcelain
~~~

Readable output may look like this:

~~~text
worktree C:/dev/project
HEAD 7a21d3f...
branch refs/heads/main

worktree C:/dev/project-feature
HEAD 9b82e10...
branch refs/heads/feature/search

worktree C:/dev/project-review
HEAD 4f10c2a...
detached
~~~

Each block begins with worktree and the directory path. Subsequent lines indicate the HEAD commit, checked-out branch, or detached state. Actual output may contain additional details such as locked or prunable.

Do not rely solely on directory names. Verify:

- Does the path match the exact worktree you intend to end?
- Which branch is the worktree checking out, or is it in detached HEAD?
- Are there uncommitted changes or untracked files?
- Is someone else or a build/test process using that directory?

If you are in the main directory, you can inspect another worktree without switching terminals:

~~~bash
git -C ../project-feature status --short --branch
git -C ../project-feature log --oneline -n 8
~~~

The -C option tells Git to execute the command as if running from the specified directory. On Windows, you can use an absolute path or a relative path suited to your current terminal location.

## 3. Checking and preserving work before removing

A normal remove command only deletes a worktree when it is clean. Therefore, check the status of the exact worktree to be removed:

~~~bash
git -C ../project-feature status --short --branch
~~~

If there are changes, decide how to keep them before removing:

- Commit if the work is finished and should become part of history.
- Stash if you need to temporarily tuck changes away per team workflow.
- Create a patch or back up files if you need to move the contents elsewhere.
- Discard changes only after confirming they are no longer needed.

Check both untracked files and ignored files if they contain important data. Git status does not always display every ignored file; you may need to inspect the directory with a file manager or an appropriate listing command.

For example, if you want to keep a completed change:

~~~bash
git -C ../project-feature add src/SearchService.java
git -C ../project-feature commit -m "Add search service"
~~~

Then recheck:

~~~bash
git -C ../project-feature status --short --branch
~~~

If you need to stash:

~~~bash
git -C ../project-feature stash push -u -m "Save feature work before removing worktree"
~~~

The -u option includes untracked files in the stash. Ignored files are not included in the stash with -u; if you need to keep them, back them up or use an appropriate option after inspecting the contents. Stashes are stored in the shared repository and can be applied from another worktree.

Do not remove a worktree without knowing which changes will be lost. Deleting a directory is not a substitute for committing, stashing, or backing up.

## 4. Removing a linked worktree with git worktree remove

Once you have confirmed the exact path and handled all changes you need to keep, run from another worktree, such as the main worktree:

~~~bash
git worktree remove ../project-feature
~~~

Git checks whether the worktree can be safely removed, then deletes the linked worktree directory and its corresponding administrative metadata. This is the standard way to end the lifecycle of a linked worktree.

After removing, verify:

~~~bash
git worktree list
git status --short --branch
~~~

The removed worktree is no longer in the list. Branches and commits in the repository still exist if referenced by a branch, tag, or another ref.

The git worktree remove command is for linked worktrees. The repository's main worktree cannot be removed with this command. If you want to delete the entire repository, that is a separate repository directory management operation and requires verifying that all work you want to keep has been saved.

Do not run the remove command from inside the very worktree directory you intend to delete. Switch your terminal to another worktree or an appropriate directory before running it.

## 5. When to use --force?

If a linked worktree still has uncommitted changes, the normal remove command refuses in order to protect your work. The --force option bypasses that safety check:

~~~bash
git worktree remove --force ../project-feature
~~~

This command can delete a worktree containing uncommitted changes, untracked files, or local content you have not backed up. Treat this as a potentially data-losing operation.

Before using --force:

1. Run git -C PATH status --short --branch.
2. Inspect modified contents and untracked files.
3. Commit, stash, or back up what needs to be kept.
4. Confirm the path truly belongs to the worktree you want to remove.
5. Only use --force if you intentionally accept discarding the rest.

A worktree can be locked with git worktree lock to avoid unintentional pruning or deletion, for example when the directory is on an external drive or a temporary location not always connected. If remove reports the worktree is locked, check the reason and owner before unlocking:

~~~bash
git worktree unlock ../project-feature
git worktree remove ../project-feature
~~~

Do not unlock just to bypass a warning without understanding why the worktree was locked. If a worktree is both dirty and locked, both conditions need to be addressed; --force is not a reason to skip checking your work.

## 6. Distinguishing remove from manual directory deletion

If you delete a linked worktree directory via File Explorer, rm, or Remove-Item, the directory itself disappears, but the administrative metadata inside the repository still remains.

Example:

~~~text
Main repository
|
+-- .git/
    +-- worktrees/
        +-- project-feature/
        +-- project-review/

Linked worktree directories:
../project-feature/       <- deleted manually
../project-review/        <- still exists
~~~

Git may still keep metadata for project-feature because the directory deletion did not notify Git that the worktree ended. As a result, git worktree list may display a nonexistent worktree or mark it as prunable.

If the directory still exists, prefer git worktree remove. If the directory was deleted manually and the metadata has become stale, use git worktree prune to clean up the leftover metadata.

Do not manually delete the .git/worktrees/ID directory by hand. Metadata holds links and administrative information that Git needs to recognize worktrees; let worktree commands manage them.

## 7. What is prune and what does it clean up?

Command:

~~~bash
git worktree prune
~~~

Prune cleans up administrative metadata of linked worktrees that no longer have a corresponding working directory and have reached their expiration threshold. It handles stale worktree records in the repository's administrative area.

Prune does not:

- Delete an existing worktree directory.
- Delete the local branch that a worktree once had checked out.
- Delete commits just because a worktree was removed.
- Delete tags or remote branches.
- Substitute for backing up or committing unsaved work.

For example, if the ../project-feature directory was deleted manually, prune can remove the stale metadata for that worktree. The feature/search branch still remains if its branch ref still exists.

## 8. Previewing before pruning

Before cleaning metadata, list the worktrees:

~~~bash
git worktree list --porcelain
~~~

Then run preview mode:

~~~bash
git worktree prune --dry-run --verbose
~~~

--dry-run tells Git to only report what would be pruned without performing deletion. --verbose shows details of items considered or removed.

Read the output and confirm that items marked as stale truly belong to deleted worktrees or worktrees no longer in use. If the path was simply moved, repair the worktree links instead of pruning its metadata.

Once confirmed, run:

~~~bash
git worktree prune --verbose
~~~

The command applies the current expiration policy to remove eligible stale metadata. If you need to clean stale entries immediately instead of waiting for expiration:

~~~bash
git worktree prune --expire now --verbose
~~~

--expire now causes eligible stale metadata to be considered immediately expired. It does not turn existing worktrees into stale entries and does not delete intact working directories.

Always use --dry-run first, especially in repositories with multiple linked worktrees or locked worktrees.

## 9. Meaning of expiration time and locked worktrees

Git can delay deleting stale metadata to avoid prematurely cleaning up a temporarily unreachable worktree. The --expire TIME option controls the minimum age of stale metadata eligible for pruning.

Example:

~~~bash
git worktree prune --dry-run --verbose --expire "30.days.ago"
~~~

The command above previews stale metadata older than 30 days. Relative time syntax is parsed according to Git's date/time format.

To view the expiration setting related to garbage collection:

~~~bash
git config --show-origin --get gc.worktreePruneExpire
~~~

If there is no custom setting, Git uses the default value for the running version. Because the default policy can depend on configuration and Git version, preview results instead of relying on a fixed duration.

Locked worktrees are normally not pruned automatically. This is a safeguard for worktrees located on devices or paths that are not always present. If a worktree has truly ended, verify the lock reason, intentionally unlock it, and then remove or prune according to the actual state.

## 10. What if the worktree was moved?

A worktree can be moved via filesystem operations, such as moving a directory from one drive to another. In that case, metadata in the repository may still store the old path.

If the worktree is intact but moved, do not run prune immediately. Fix the metadata links with:

~~~bash
git worktree repair ../project-feature-moved
~~~

Run the command from the repository or an appropriate worktree and provide the moved worktree path as Git requires. Then verify:

~~~bash
git worktree list
git -C ../project-feature-moved status --short --branch
~~~

Repair is for worktrees that still exist whose link information needs updating. Prune is for metadata of worktrees that no longer have a corresponding directory. Confusing the two cases can cause you to clean up metadata of a worktree that still has data you need to keep.

## 11. Removing a worktree does not mean deleting the branch

Suppose the ../project-feature worktree has checked out the feature/search branch. After running:

~~~bash
git worktree remove ../project-feature
~~~

The feature/search branch still remains in the repository. Verify:

~~~bash
git branch --list
git branch -vv
~~~

If you want to delete the branch after the worktree has been removed, that is a separate decision:

~~~bash
git branch -d feature/search
~~~

-d only deletes the branch when Git determines it has been safely merged. If the branch is not merged, Git refuses in order to protect unintegrated commits.

Do not use -D just to tidy up the branch list. -D force-deletes a branch even if unmerged and can make commits hard to recover if no other ref points to them. Before deleting a branch, inspect the log, merge status, and confirm the work has been integrated where needed.

If the branch is still checked out by another worktree, Git will also refuse normal deletion. Check git worktree list first.

## 12. Complete workflow: remove worktree then prune stale metadata

### Case A: the worktree directory still exists

~~~bash
# 1. View worktrees
git worktree list --porcelain

# 2. Inspect the worktree to be removed
git -C ../project-feature status --short --branch
git -C ../project-feature log --oneline -n 8

# 3. Commit or stash work to keep if any

# 4. Properly remove the linked worktree
git worktree remove ../project-feature

# 5. Verify
git worktree list
git branch -vv
~~~

Normally, remove already deletes the corresponding metadata, so there is no need to prune immediately afterward. You can run prune periodically to clean up stale metadata left over from previous manual deletions.

### Case B: the worktree directory was deleted manually

~~~bash
# 1. View worktree entries and prunable status
git worktree list --porcelain

# 2. Preview metadata to be cleaned up
git worktree prune --dry-run --verbose

# 3. After confirming, clean up stale metadata
git worktree prune --verbose

# 4. Recheck the list
git worktree list
~~~

If the metadata is not old enough to expire under the current policy, yet you have confirmed the worktree no longer exists, you can use --expire now after previewing.

### Case C: cleaning up both the worktree and the completed branch

~~~bash
# Remove the worktree first
git worktree remove ../project-feature

# Check whether the branch has been merged
git branch --merged main

# Only delete branches that are complete and no longer in use
git branch -d feature/search

# Final check
git worktree list
git branch --list
~~~

Deleting the branch is a separate step, not an effect of remove or prune.

## 13. Common errors

### Remove refuses because the worktree still has changes

Run git -C PATH status --short --branch, then commit, stash, or back up what needs to be kept. Only use --force when you accept deleting unsaved contents.

### Remove reports the worktree is locked

Check the lock reason and confirm the worktree is no longer being protected for another device or user. If safe, run git worktree unlock PATH and retry remove.

### Prune does not delete an entry visible in the list

Check whether the path still exists, whether the entry is locked, and whether the expiration time has been reached. Use --dry-run --verbose and --expire now only after confirming the entry is truly stale.

### Prune finished but the branch still exists

That is expected behavior. Prune only cleans up worktree metadata. Deleting a branch is a separate operation and requires confirming the branch is merged or no longer needed.

### Worktree still exists but Git shows the old path

The directory may have been moved. Use git worktree repair to fix the links instead of pruning.

### Directory deleted but Git still reports the worktree

That is stale metadata. Run git worktree prune --dry-run --verbose to preview, then prune if the worktree truly no longer exists.

## 14. Key takeaways

- Worktrees share the object database and branch refs, while having separate working trees, HEAD, and indexes.
- Use git worktree list to identify the exact path and branch before removing.
- Use git worktree remove for an existing linked worktree; inspect and save all changes you need to keep beforehand.
- --force can lose uncommitted content or local files in the worktree.
- If the directory was deleted manually, git worktree prune cleans up remaining stale metadata.
- Use --dry-run --verbose before pruning; --expire now should only be used after confirming stale entries.
- A locked worktree may need inspection and intentional unlocking.
- If the directory was only moved, use git worktree repair instead of prune.
- Remove and prune do not automatically delete branches; deleting a branch is a separate decision.

When you finish a worktree following the proper workflow, you preserve needed history and branches while removing unused metadata. Building the habit of inspecting before removing and previewing before pruning prevents accidentally deleting work or cleaning up a worktree that is still needed.

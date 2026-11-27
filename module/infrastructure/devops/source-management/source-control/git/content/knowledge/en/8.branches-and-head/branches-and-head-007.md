# Conditions for Switching Branches with Uncommitted Changes

While editing code, you may need to switch to another branch to handle a bug, review a pull request, or start a new task. If the working tree still has uncommitted changes, Git must determine whether those changes can be preserved when checking out the target branch's snapshot.

Git allows switching branches when local changes will not be overwritten by the target branch's snapshot. If switching branches risks losing in-progress edits, Git normally refuses and asks you to handle them first. You can make a temporary commit, stash, create a new branch, or intentionally use merge mode when you understand the outcome. This article explains those conditions and how to choose a safe workflow.

## 1. Three Areas to Inspect Before Switching Branches

Git works with three main areas:

- **HEAD**: the current commit that the branch or detached HEAD points to.
- **Index (staging area)**: contents staged in preparation for the next commit.
- **Working tree**: the files currently present in the working directory.

Uncommitted changes can reside in the index, the working tree, or both. Therefore, glancing at a single summary line is not enough to decide whether switching branches is safe.

Diagram:

```text
HEAD (current commit) -- git diff --cached --> Index (staged)
Index ------------------ git diff -----------> Working tree
HEAD ------------------ git diff HEAD -------> Working tree
```

Start with:

```bash
git status --short --branch
git diff
git diff --cached
```

- `git status` shows the current branch, staged, unstaged, untracked files, and conflict status.
- `git diff` shows unstaged changes.
- `git diff --cached` shows staged changes relative to HEAD.

If you also need to see untracked and ignored files:

```bash
git status --short --untracked-files=all --ignored
```

Untracked files are not in the index. However, they can still block a branch switch if the target branch has a tracked file at the same path.

## 2. When Does Git Allow Switching Branches?

Suppose the current branch is `feature/a` and the target branch is `feature/b`. Git needs to update the index and working tree to reflect the target branch's snapshot.

Switching branches is possible when local changes can be preserved without overwriting contents that need to be checked out from the target branch. For example:

- You edit `README.md` on the current branch.
- The target branch has not changed `README.md` relative to the common commit, or updating files does not discard your local edit.
- Git can keep the local change intact in the working tree when switching to the target branch.

In that case:

```bash
git switch feature/b
```

can succeed, and the local changes remain after switching branches. You still need to check `git status` to confirm what state those changes are in.

Git normally refuses to switch branches if the target snapshot needs to overwrite a file that has local changes. For example:

```text
Branch feature/a: src/App.java = version A
Working tree:     src/App.java locally modified
Branch feature/b: src/App.java = different version B
```

If switching to `feature/b` would lose the contents being edited, Git stops and reports that local changes would be overwritten by checkout/switch.

This is a data protection mechanism. When encountering this message, read the list of files Git reports and preserve those changes before retrying.

## 3. How Do Staged and Unstaged Changes Affect Switching?

Git checks both the index and the working tree. Both kinds of changes can coexist:

```text
 M src/App.java
M  README.md
A  src/NewFeature.java
```

Meaning:

- ` M`: a tracked file modified in the working tree but not yet staged.
- `M `: changes to the file have been staged in the index.
- `A `: a new file has been staged.

A staged change is still an uncommitted change. Having run `git add` does not mean that content is already saved in commit history.

If the target branch does not need to overwrite the modified paths, Git can preserve them across the branch switch. If there is a risk of overwriting, Git refuses. Do not assume staged changes are inherently safer than unstaged changes; both must be preserved.

Inspect the two areas separately:

```bash
git diff
git diff --cached
git status --short
```

If you staged part of a file and then continued editing another part, you may see the same file appear in both status columns. Understand what is in both the index and working tree before switching branches.

## 4. Untracked Files Can Block Branch Switching

Untracked files are not tracked by Git, yet they can still be affected by checkout.

For example, the current branch has an untracked file:

```text
src/Experimental.java
```

If the target branch has a tracked file at the same path `src/Experimental.java`, Git cannot write the target branch's file over the local file without risking data loss. The switch command normally refuses.

Inspect untracked files in detail:

```bash
git status --short --untracked-files=all
git ls-files --others --exclude-standard
```

There are three common ways to handle this:

1. Include the file in a commit if it belongs to the current branch's work.
2. Stash untracked files as well using `git stash push -u`.
3. Move or back up the file to a safe location and then switch branches.

Do not delete untracked files just to make the switch command succeed before confirming they can be discarded.

Ignored files also deserve attention. Some ignored files can be overwritten by checkout when the target branch needs to create a file at the same path. If a local file is valuable, back it up before switching branches; `git status --ignored` helps detect them.

## 5. Attempting a Switch and Reading Git's Messages

Simple workflow:

```bash
git status --short --branch
git switch feature/b
```

If it succeeds, check immediately:

```bash
git status --short --branch
git branch --show-current
```

If it fails due to local changes, Git normally lists the files at risk of being overwritten. Do not add `--force` or `--discard-changes` by reflex. Identify which changes need to be kept and choose an appropriate preservation method.

If Git reports unmerged paths or an unfinished merge/rebase/cherry-pick operation, resolve the in-progress operation first. Switching branches while the index still has conflicts can be refused because the repository is not in a suitable state.

## 6. Method 1: Commit Changes Before Switching Branches

If the changes are clear enough and belong to the current branch, the most direct approach is to create a commit:

```bash
git status
git add -- src/App.java
git diff --cached
git commit -m "Update application behavior"
git switch feature/b
```

Committing saves the index snapshot into history. After a successful commit, the changes are no longer uncommitted; the current branch holds that commit.

If the work is still in progress but you want to keep it in local history, you can create a temporary commit with a recognizable message:

```bash
git add -A
git commit -m "WIP: save progress before switching"
```

Then switch branches. When you return, you can continue editing or clean up private history with appropriate operations, such as amend or interactive rebase if the commit has not been shared.

Only use `git add -A` after reviewing the file list. This command stages additions, modifications, and deletions across the repository; ignored files are not added automatically. If there are local files or secrets that must not be committed, stage paths explicitly or use `git add -p`.

## 7. Method 2: Stash Changes to Switch Branches Temporarily

If you do not want to create a commit yet, you can set changes aside in the stash:

```bash
git stash push -m "WIP before switching branch"
git status --short --branch
git switch feature/b
```

By default, stash saves tracked changes in the index and working tree and resets the working tree to a clean state matching HEAD. Untracked files are not included in the stash by default.

If you need to stash untracked files as well:

```bash
git stash push -u -m "WIP including untracked files"
```

The `-u` option is equivalent to `--include-untracked`. Ignored files are still not included in the stash with this option.

If you genuinely need to stash ignored files as well:

```bash
git stash push -a -m "WIP including ignored files"
```

`-a` is equivalent to `--all`, including both untracked and ignored files. Inspect carefully before using it because local config files, caches, or needed data could be removed from the working tree after stashing.

List stashes:

```bash
git stash list
git stash show --stat stash@{0}
```

After finishing work on the other branch, return to the original branch and apply the stash:

```bash
git switch feature/a
git stash apply stash@{0}
```

`apply` keeps the stash in the list, giving you time to verify that contents were fully restored. Once certain, drop the entry with:

```bash
git stash drop stash@{0}
```

`git stash pop` both applies and drops the stash if application succeeds. When changes are important, `apply` followed by verification before `drop` is easier to control.

## 8. Stashing Only Unstaged or Staged Parts

Sometimes you have staged the changes you want to commit, while other parts remain unstaged. Depending on your goal, you can use `--keep-index` to keep staged contents in the index and stash only the rest:

```bash
git add -- src/App.java
git stash push --keep-index -m "Stash unstaged work"
```

This option is useful when you want to keep staged changes to run tests or commit while stashing unstaged work. Check `git status` after the command to confirm exactly what remains.

If you want to stash specific paths only, use a pathspec:

```bash
git stash push -m "Save documentation edits" -- docs/
```

A stash can be applied onto another branch and may cause conflicts if the underlying contents differ. A stash is not a commit on a branch and is not automatically shared with a remote.

## 9. Method 3: Create a New Branch from the Current State

If you realize local changes actually belong to a new task, you can create a new branch right at the current commit:

```bash
git switch -c feature/new-task
```

This command creates a new branch from the current HEAD and switches to it. Because the new branch starts at the same commit, Git normally keeps uncommitted changes in the index and working tree intact.

Example:

```text
Before:
main (HEAD) ---- A
                  \
                   working tree has local changes

After git switch -c feature/new-task:
main ------------ A
feature/new-task  A (HEAD)
                   \
                    same local changes remain in working tree/index
```

After creating the branch, verify:

```bash
git status --short --branch
git branch --show-current
```

Now you can commit the changes onto the new branch. This is the right approach when you accidentally started editing on `main` but have not committed yet.

If the new branch needs to start from a different commit, preserve the changes first using stash or a commit before switching. Do not expect `git switch -c <new-branch> <other-start-point>` to carry all local changes onto a different base without conflicts.

## 10. Method 4: Using git switch --merge When You Want Git to Merge Local Changes

`git switch --merge <branch>` asks Git to attempt merging local changes with the target branch's contents using a three-way merge.

Example:

```bash
git switch --merge feature/b
```

This method can be useful when you intentionally want to bring local changes onto the target branch and Git can merge them. However, the operation can produce conflicts if the same regions of content were changed in different ways.

After the command, inspect:

```bash
git status
git diff
git diff --cached
git diff --name-only --diff-filter=U
```

If there are conflicts:

1. Open each file and combine the contents appropriately with the target branch.
2. Stage resolved files with `git add`.
3. Recheck the index and working tree.
4. Create a commit if you want to save the merged changes.

Example:

```bash
git add -- src/App.java
git status
git diff --cached
```

`switch --merge` does not replace reviewing the result. If you are unsure how Git will combine the changes, stashing first is easier to control.

## 11. Do Not Use --discard-changes to Bypass Messages

Git provides the option:

```bash
git switch --discard-changes feature/b
```

This option requests discarding changes in the index and working tree in order to switch to the target branch. Uncommitted tracked contents may be overwritten. Untracked or ignored files blocking checkout may also be at risk depending on the path and checkout operation.

Only use it when you have confirmed every needed change has already been committed, stashed, or backed up elsewhere.

Before considering it:

```bash
git status --short --untracked-files=all --ignored
git diff
git diff --cached
```

If in doubt, do not use `--discard-changes`. Stash or create a safe backup first, then switch branches normally.

Similarly, avoid using `git reset --hard` just to make the working tree clean. That command moves HEAD/index and rewrites tracked files to match the target commit, which can lose local contents.

## 12. If a Merge, Rebase, or Cherry-Pick Is in Progress

When Git is in the middle of an integration operation, the index may contain conflict stages or sequencer metadata. Switching branches at this time is normally refused.

Check:

```bash
git status
git ls-files -u
```

If merging and you want to finish, resolve conflicts and then:

```bash
git add -- <resolved-path>
git merge --continue
```

If you want to cancel an in-progress merge:

```bash
git merge --abort
```

For rebase:

```bash
git rebase --continue
# or
git rebase --abort
```

For cherry-pick:

```bash
git cherry-pick --continue
# or
git cherry-pick --abort
```

Only abort when you understand which changes will be restored or discarded. If there was unpreserved work before starting the operation, inspect `git status` and current diffs before deciding.

After the integration operation finishes, confirm there are no remaining unmerged paths before switching branches.

## 13. Switching to a Remote Branch While Local Changes Exist

If you want to switch to a remote branch that does not yet have a local branch, you can create a local tracking branch:

```bash
git fetch origin
git switch --track origin/feature/review
```

This command creates the local branch `feature/review` tracking `origin/feature/review` and switches to it. The conditions for preserving local changes remain the same as switching between two local branches: if checkout does not overwrite changes, Git can preserve them; if there is a risk of overwriting, Git refuses.

If a local branch with the same name already exists, check its upstream and status before switching:

```bash
git branch -vv
git switch feature/review
```

Do not use `git pull` as a workaround for local changes blocking a switch. Pull integrates remote history into the current branch; it is not a stash or working-tree preservation command for switching branches.

## 14. Restoring a Stash When the Target Branch Has Changed

After stashing, the target branch may have modified the same files. When applying the stash, Git may encounter conflicts.

Use `apply` to keep the stash if applying fails:

```bash
git stash apply stash@{0}
git status
```

If there are conflicts, resolve the files, stage, and inspect the contents. Only after everything is fully restored should you drop the stash:

```bash
git stash drop stash@{0}
```

If you want to create a branch from the stash's base commit and apply the changes onto that branch:

```bash
git stash branch rescue/work-in-progress stash@{0}
```

This command typically restores the stash on the exact base where it was created, reducing conflict risk caused by the current branch advancing. If it succeeds, Git deletes the used stash entry.

If the stash included untracked files, verify they were restored:

```bash
git status --short --untracked-files=all
git stash list
```

Do not drop a stash solely because apply returned a success exit code; inspect important files and diffs first.

## 15. Practical Example: Switching to an Urgent Bug Fix Mid-Edit

You are on the `feature/report` branch and have modified two files:

- `src/ReportService.java` is staged.
- `src/ReportFormatter.java` is unstaged.
- `notes/debug.txt` is an untracked file.

There is an urgent request to fix a bug on the `hotfix/payment` branch.

**Step 1: Check full status.**

```bash
git status --short --untracked-files=all
git diff
git diff --cached
```

**Step 2: Stash both tracked and untracked changes.**

```bash
git stash push -u -m "WIP report before payment hotfix"
```

**Step 3: Confirm the working tree is clean and switch branches.**

```bash
git status --short --branch
git switch hotfix/payment
```

**Step 4: Fix the bug, test, and commit on the hotfix branch.**

```bash
git add -- src/PaymentService.java
git commit -m "Fix payment validation"
```

**Step 5: Return to your previous work.**

```bash
git switch feature/report
git stash list
git stash apply stash@{0}
```

**Step 6: Verify restored changes.**

```bash
git status --short --untracked-files=all
git diff
git diff --cached
```

If everything is back in place, drop the corresponding stash entry:

```bash
git stash drop stash@{0}
```

If while working on the hotfix `feature/report` was updated from the remote or had other changes, applying the stash may conflict. Resolve based on the new contents, and do not drop the stash before verifying.

## 16. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| `git switch` reports local changes would be overwritten | Target branch needs to overwrite an edited file | Commit, stash, or preserve the file first |
| Switch succeeds yet changes remain | Git was able to carry non-conflicting changes | Check `git status`, do not assume switch commits automatically |
| Untracked file blocks switch | Target branch has a tracked file at the same path | Stash with `-u`, move, or back up the file |
| Ignored file risks being overwritten | Checkout needs to create a file at the same path | Check `--ignored` and back up important files |
| Stash does not contain untracked files | Used default stash | Use `git stash push -u` |
| Stash does not contain ignored files | `-u` does not include ignored files | Only use `-a` if you truly want to stash all ignored files |
| Stash apply triggers conflicts | The base branch changed | Resolve conflicts, verify, then drop the stash |
| `git switch -c` reports branch already exists | The local branch name is already in use | Check branches with `git branch -vv`, pick another name, or switch to the existing branch |
| Cannot switch during merge/rebase | Repository has an unfinished integration operation | Continue or abort the operation after preserving your work |
| Using `--discard-changes` lost edits | Instructed Git to discard local changes | Recover from stash/backup if available; verify before using this option |

## 17. Pre-Switch Checklist

- [ ] Ran `git status --short --branch`.
- [ ] Inspected `git diff` and `git diff --cached`.
- [ ] Checked untracked and ignored files that might be affected.
- [ ] Confirmed whether a merge, rebase, cherry-pick, or conflict is in progress.
- [ ] Decided between committing, stashing, creating a new branch, or using merge.
- [ ] If stashing, chose the right scope for tracked, untracked (`-u`), and ignored (`-a`) files.
- [ ] Did not use `--discard-changes` or `reset --hard` without confirming contents can be discarded.
- [ ] After switching, verified the branch and local status.
- [ ] After applying a stash, verified contents before dropping the stash.

## Conclusion

Git can switch branches when local changes can be preserved without being overwritten by the target branch's snapshot. If there is a risk of losing content, Git normally refuses; read the message and inspect the index, working tree, and untracked files before proceeding. Committing is appropriate when you want to save progress into history, stashing when you need temporary storage, creating a new branch when changes belong to a different task, and `git switch --merge` when you intentionally want Git to merge local changes. Only use `--discard-changes` once you have confirmed all relevant changes can be discarded. After every branch switch or stash restore, recheck `git status` and diffs to ensure your work remains intact.

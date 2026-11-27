# Applying Changes Without Creating a Commit Using cherry-pick --no-commit

In a project, sometimes you need to bring in a change from another branch while deciding the commit's content and timing yourself. For instance, a bugfix commit on the development branch needs to be ported to a maintenance branch; or several small commits need to be combined into a single commit on the target branch. Git supports this with <code>git cherry-pick --no-commit</code> (abbreviated <code>git cherry-pick -n</code>).

The <code>--no-commit</code> option tells Git to apply the selected commit's changes into the **working tree and index**, without automatically creating a commit. You can inspect the diff, edit the content, select a subset of changes, or combine multiple commits before committing according to the target branch's purpose.

This lesson belongs to the **Switching and Undoing** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; it also builds skills in collaborating through branches, resolving conflicts, tracing changes, and recovering from mistakes while preserving important history. Clearly understanding the index, working tree, and HEAD during a non-committing cherry-pick lets you transfer changes across branches with control.

## 1. Regular Cherry-Pick vs. cherry-pick --no-commit

<code>git cherry-pick</code> takes the changes introduced by one or more source commits and applies them onto the current branch. Git does not switch the current branch to the source commit; it creates a new commit on the target branch with the corresponding changes.

With regular cherry-pick:

~~~bash
git switch release/2.x
git cherry-pick a1b2c3d
~~~

If it applies cleanly, Git automatically creates a new commit on <code>release/2.x</code>. The new commit has changes corresponding to the source commit, though it typically has a different hash because its parent commit and metadata differ.

With <code>--no-commit</code>:

~~~bash
git switch release/2.x
git cherry-pick --no-commit a1b2c3d
~~~

Git applies the changes to the working tree and index, stopping before the commit step. HEAD and the current branch continue pointing to the old commit until you explicitly run <code>git commit</code> or perform another operation that moves the branch.

| Usage | Working tree | Index | HEAD / current branch |
|---|---|---|---|
| <code>git cherry-pick &lt;commit&gt;</code> succeeds | Contains snapshot after applying | Updated | Moves to the new commit |
| <code>git cherry-pick --no-commit &lt;commit&gt;</code> succeeds | Contains applied content | Contains staged changes | Stays in place |

With a clean working state beforehand, the applied changes typically appear as staged. Therefore, <code>git diff --staged</code> is the key command to view the content that will go into the next commit.

## 2. When Should You Use --no-commit?

Several suitable scenarios:

- **Combining multiple commits into one:** take small commits from a feature branch, inspect the result, and create a single consolidated commit on the target branch.
- **Porting partial changes:** apply a source commit, then select only the files or hunks to include in the commit.
- **Adjusting before committing:** apply a bug fix from another branch, then update names, configurations, or details to fit the current branch.
- **Preparing changes for a maintenance branch:** take the needed fixes from the development branch without preserving the source branch's commit structure.
- **Inspecting before deciding:** bring the patch into the index to review and run tests before creating a commit.

<code>--no-commit</code> is especially helpful when the content to port is right, yet you want the final commit to reflect the target branch's purpose. For example, the source branch may have three commits covering code fixes, added tests, and documentation updates; the release branch may need a single fully tested commit.

## 3. Preparing Before Cherry-Picking

First, verify that the current branch is the target branch and that the source commit contains the right changes to take.

~~~bash
# Check branch and working status
git branch --show-current
git status

# View branches and recent history
git branch -a
git log --oneline --graph --decorate -20

# Inspect the source commit content
git show --stat a1b2c3d
git show a1b2c3d
~~~

It is best to start with a clean working tree and a clean index so changes created by cherry-pick are easy to distinguish. If there are local changes you need to keep, commit or save them safely before continuing. <code>--no-commit</code> allows the current index to differ from HEAD, yet if the index already holds previously staged changes, the next commit may end up containing both those changes and the cherry-picked patch.

A simple preparation workflow:

1. Confirm the right repository and target branch.
2. Fetch if the source commit is on a remote and not yet local.
3. Inspect the source commit with <code>git show</code>.
4. Confirm those changes are not already present on the target branch.
5. Check the working tree and index; save any local changes to keep.

Example:

~~~bash
git fetch origin
git switch release/2.x
git status
git show --stat a1b2c3d
~~~

If the source commit only exists on a remote-tracking branch, you can use the commit hash or a reference name like <code>origin/feature/payment-fix</code>.

## 4. Applying One Commit Without Creating a New Commit

Suppose commit <code>a1b2c3d</code> contains an amount validation bug fix and you want to apply it onto branch <code>release/2.x</code>:

~~~bash
# Switch to the target branch
git switch release/2.x

# Apply changes without creating a commit
git cherry-pick --no-commit a1b2c3d

# Check status and staged content
git status
git diff --staged
~~~

After the cherry-pick command, Git has applied the patch to the index and working tree. HEAD stays at the previous commit. If <code>git status</code> shows staged files, this is normal when the operation succeeds without conflicts.

You can also inspect all differences relative to the current commit:

~~~bash
# Staged changes compared to HEAD
git diff --staged

# Further edits in the working tree not yet staged
git diff

# Total working tree differences compared to HEAD
git diff HEAD

# Check for whitespace issues
git diff --check
~~~

If the content is right and tests pass, create a commit with a message appropriate for the target branch:

~~~bash
git commit -m "fix: validate payment amount on release branch"
~~~

This commit is a new commit created by you on the target branch. Git does not automatically preserve the source commit's message or author identity the way regular cherry-pick does; you decide the final commit message and content. If source traceability is needed, record the original commit hash or ticket reference in the commit message or pull request.

## 5. Combining Multiple Commits into One Commit

A major benefit of <code>--no-commit</code> is being able to apply multiple commits sequentially without creating intermediate commits.

Suppose branch <code>feature/export</code> has three commits:

~~~text
a111111 feat: add export endpoint
b222222 test: cover export endpoint
c333333 docs: describe export endpoint
~~~

You want to bring all three changes to <code>release/2.x</code> and create a single commit:

~~~bash
# Switch to the target branch
git switch release/2.x

# Apply in order from oldest commit to newest commit
git cherry-pick --no-commit a111111 b222222 c333333

# Review all staged changes
git status
git diff --staged

# Run tests and create a combined commit
git commit -m "feat: add export endpoint to release"
~~~

Apply in dependency order, usually from older commits to newer commits. If the test commit depends on source code added by an earlier commit, the code commit must be applied first so the test patch has the proper foundation.

The source commits continue existing on branch <code>feature/export</code>. On the target branch, one new commit holds the combined applied changes. The target branch history does not automatically acquire the source commits as ancestors, because cherry-pick copies changes rather than merging ancestry like merge does.

You can list source commits from oldest to newest with:

~~~bash
git log --oneline --reverse release/2.x..feature/export
~~~

Only use that range when <code>release/2.x</code> is a suitable baseline for comparing against <code>feature/export</code>. If the two branches already have divergent histories or have previously cherry-picked from one another, inspect the commit graph and identify the exact hashes to apply.

## 6. Selecting a Subset of Changes Before Committing

After cherry-picking without committing, the entire patch is typically already in the index. You can unstage a file or a subset of changes and decide the final commit content.

### Unstaging an entire file while keeping content

~~~bash
git restore --staged -- src/ExportController.java
~~~

This command returns the file's staged content in the index to its state in HEAD while keeping the changes in the working tree. The file moves from staged to modified unstaged. You can edit further or re-stage only what is needed.

### Unstaging by individual hunks

~~~bash
git restore --staged -p -- src/ExportController.java
~~~

Git prompts you hunk by hunk whether you want to unstage each part of the change. Select the hunks to remove from the index. Unstaged parts remain in the working tree, so you can commit the staged parts first and handle the rest later.

On older Git versions or by habit, you can use:

~~~bash
git reset -p -- src/ExportController.java
~~~

This updates the index hunk by hunk without moving HEAD when used in this pathspec form.

### Re-staging the part to commit

After selecting, inspect both areas:

~~~bash
# Part that will be committed
git diff --staged

# Remaining part in the working tree
git diff

# Status by path
git status --short
~~~

Once the staged part is right, create the commit:

~~~bash
git commit -m "fix: apply selected export validation changes"
~~~

Unstaged parts remain in the working tree after committing. Handle them separately so you do not accidentally include them in the next commit.

## 7. Editing Content After Cherry-Picking

<code>--no-commit</code> lets you modify the patch before creating the commit. For example, the source commit uses configuration names suited for development, while the release branch requires different defaults. You can edit the file after cherry-picking and check again:

~~~bash
# After editing the file
git status
git diff
git diff --staged

# Stage the final content
git add config/application-release.yml

# Inspect the snapshot to be committed
git diff --staged
~~~

If a file was already staged from the cherry-pick, editing it further creates an unstaged difference. Thus, the same file can appear in both <code>git diff --staged</code> and <code>git diff</code>: the first is the version applied from the source commit, and the second is your subsequent edit.

Do not just look at the working tree and assume all content is already in the commit. Regular <code>git commit</code> takes its snapshot from the index. Always check <code>git diff --staged</code> before committing.

## 8. Handling Conflicts During cherry-pick --no-commit

If the patch does not apply cleanly onto the target branch, Git pauses and reports the conflicted files. Some files may already have applied cleanly while others are in an unmerged state. Never assume the entire operation failed or all changes finished cleanly.

Resolution workflow:

~~~bash
# Identify conflicted files
git status

# Open and edit files containing conflict markers
# After choosing the final content:
git add src/ExportController.java

# Inspect staged changes
git diff --staged
git status

# Continue the cherry-pick process if Git is holding sequencer state
git cherry-pick --continue
~~~

For a single cherry-pick, after resolving conflicts, follow the status and guidance Git displays. For a multi-commit sequence, <code>--continue</code> lets you proceed with the remaining commits in the paused operation. Because <code>--no-commit</code> is used, the end goal remains leaving changes in the index and working tree without automatically creating a commit.

If you do not want to continue the paused operation:

~~~bash
git cherry-pick --abort
~~~

<code>--abort</code> cancels the Git-managed cherry-pick process and restores the state before the process started. This command applies when Git reports an incomplete cherry-pick, such as due to a conflict.

If cherry-pick <code>--no-commit</code> applied cleanly and exited normally, there is no active process left to abort. In that case, if you want to discard the newly applied patch, identify the exact affected paths and make sure they hold no local changes to keep before restoring from HEAD:

~~~bash
# Only use on paths that were clean before cherry-pick
git restore --source=HEAD --staged --worktree -- src/ExportController.java
~~~

The restore command above replaces both the index and working tree of the specified path with content from HEAD. It discards any other edits on that same path as well, so do not use it if you already had separate changes to keep. When unsure, back up or save your changes before restoring.

## 9. Cherry-Picking a Merge Commit

A merge commit has more than one parent. When cherry-picking a merge commit, Git needs to know which parent is treated as the mainline to determine the changes to apply. If omitted, Git usually errors out asking you to specify a mainline.

Example:

~~~bash
git cherry-pick --no-commit -m 1 <merge-commit-hash>
~~~

<code>-m 1</code> tells Git to treat the first parent as the mainline and apply the diff between the merge commit and that parent. Choosing the wrong parent can apply changes other than what you intended. Inspect the merge commit first:

~~~bash
git show --no-patch --pretty=raw <merge-commit-hash>
git diff <merge-commit-hash>^1 <merge-commit-hash>
git diff <merge-commit-hash>^2 <merge-commit-hash>
~~~

The diff commands help show how the merge result differs from each parent. Only select <code>-m</code> after identifying the exact base branch to preserve. For complex changes, it may be safer to pick specific commits rather than cherry-picking an entire merge commit.

## 10. Distinguishing cherry-pick --no-commit from Other Patch Application Methods

| Approach | Input source | Primary result |
|---|---|---|
| <code>git cherry-pick &lt;commit&gt;</code> | A Git commit | Applies changes and automatically creates a new commit |
| <code>git cherry-pick -n &lt;commit&gt;</code> | One or more Git commits | Applies changes to index/working tree without automatically creating a commit |
| <code>git merge &lt;branch&gt;</code> | A branch's history | Integrates history and may create a merge commit or fast-forward |
| <code>git apply &lt;patch&gt;</code> | A patch/diff file | Applies patch; does not rely on commit hashes or parent-child commit relationships |
| <code>git revert &lt;commit&gt;</code> | An existing commit | Creates changes reversing that commit; with <code>-n</code>, does not automatically commit |

<code>git cherry-pick -n</code> fits when the change source is a commit inside the repository and you want to leverage Git's patch resolution, application, and conflict handling. If you only have a standalone patch file, <code>git apply</code> may be more suitable. If you want to integrate a branch's entire history, consider merge.

### Comparing with git revert --no-commit

The two commands have opposite meanings:

- <code>git cherry-pick --no-commit &lt;commit&gt;</code> applies the changes introduced by the source commit.
- <code>git revert --no-commit &lt;commit&gt;</code> applies changes that reverse the selected commit.

Both can leave results in the index and working tree without yet creating a commit. Clarify whether your goal is to bring in a change or undo a change before choosing the command.

## 11. Things to Note When Committing the Result

Once you have applied one or more commits with <code>--no-commit</code>, the final commit you create can differ from the source commits:

- The commit message is written by you, so it should describe the result on the target branch.
- Content may have been edited, filtered, or combined.
- The author/committer of the new commit depends on your configuration and details used when committing.
- Source commits remain on the original branch; cherry-pick does not delete them.
- Target branch history only gets the new commit if you create the commit yourself.

If you need to preserve origin tracking, mention the original commit hash, ticket, or pull request in the commit message. For workflows requiring attribution, follow your team's convention for <code>Co-authored-by</code> or origin notes.

After committing, verify the branch and history:

~~~bash
git status
git log --oneline --graph --decorate -10
git show --stat HEAD
~~~

If the commit on the target branch needs to be shared:

~~~bash
git push origin release/2.x
~~~

Make sure you are pushing to the right branch and have permission to update it. If the remote has moved ahead, fetch and integrate per your team's workflow instead of force-pushing just to replace history.

## 12. Common Errors and How to Handle Them

| Symptom | Possible cause | How to check or handle |
|---|---|---|
| Ran <code>cherry-pick -n</code> and see no new commit | This is expected behavior; <code>-n</code> does not create a commit | Check <code>git status</code> and <code>git diff --staged</code> |
| Next commit contains unwanted changes | Index already had staged changes beforehand or extra files were staged out of scope | Check <code>git diff --staged</code>, unstage unneeded parts, and re-verify |
| One file has both staged and unstaged changes | You edited the file after cherry-picking | Inspect <code>git diff --staged</code> and <code>git diff</code> separately |
| Cherry-pick reports conflict | Patch does not apply automatically onto the target branch state | Resolve files, <code>git add</code>, verify, and continue |
| <code>--abort</code> has no effect after applying cleanly | The cherry-pick process already finished; no state remains to abort | Restore the exact paths from HEAD if they were clean before the operation |
| Cherry-picking a merge commit says mainline needed | Merge commit has multiple parents | Inspect parents and use <code>-m</code> with the appropriate parent |
| Some changes from source commit are missing | Later commit depends on earlier commit or patch already exists on target branch | Inspect history and apply in proper order |
| Final commit does not preserve source message | <code>--no-commit</code> does not auto-create commit metadata from source commit | Write a new message and record origin if traceability is needed |

## 13. Safe Practice Workflow

The workflow below suits taking a change from a feature branch to a maintenance branch:

~~~bash
# 1. Update remote information
git fetch origin

# 2. Inspect the source commit
git show --stat <source-commit>
git show <source-commit>

# 3. Switch to target branch and check status
git switch release/2.x
git status

# 4. Apply without creating a commit
git cherry-pick --no-commit <source-commit>

# 5. Inspect change areas
git status
git diff --staged
git diff
git diff --check

# 6. Run tests, edit, and stage final content
# git add <path>

# 7. Create commit when content is right
git commit -m "fix: describe the backported change"

# 8. Verify the result
git status
git show --stat HEAD
~~~

For multiple commits, replace step 4 with a list of hashes in dependency order:

~~~bash
git cherry-pick --no-commit <oldest-commit> <next-commit> <newest-commit>
~~~

Do not blindly apply multiple commits at once. Confirm each commit belongs to the same goal, inspect dependencies, and review the entire diff after applying.

## 14. Self-Check Exercise

Practice in a test repository with two branches:

1. On branch <code>feature/demo</code>, create a commit adding a small function and push the branch to remote.
2. Switch to branch <code>release/demo</code> and check <code>git status</code>.
3. Run <code>git cherry-pick --no-commit &lt;commit-hash&gt;</code>. Observe whether HEAD changes and what state the files appear in.
4. Run <code>git diff --staged</code> to view the applied patch.
5. Edit a line in a file after cherry-picking. Compare <code>git diff --staged</code> with <code>git diff</code>.
6. Use <code>git restore --staged -p</code> to unstage one hunk, then observe what remains staged and what remains in the working tree.
7. Commit the selected part, then check whether the unstaged change is still present.
8. Create two interdependent commits on the source branch and apply both with one <code>cherry-pick --no-commit</code> command; observe the application order.
9. Create a conflict scenario in the test repository, resolve and continue; repeat to test <code>git cherry-pick --abort</code>.
10. Explain the difference between <code>git cherry-pick --no-commit</code> and <code>git revert --no-commit</code>.

When you understand that <code>cherry-pick --no-commit</code> puts changes into the index and working tree while leaving HEAD unchanged, you can filter, edit, and combine patches before creating a commit. Always check <code>git status</code> and <code>git diff --staged</code> so the final commit contains only what you intend to introduce onto the target branch.

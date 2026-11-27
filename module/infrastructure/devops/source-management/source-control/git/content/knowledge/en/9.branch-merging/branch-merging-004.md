# Selecting the Target Branch and Checking Scope Before git merge

The `git merge` command integrates the history of one branch into the current branch. Therefore, before running the command, you must clearly identify the **target branch** (where the changes are received) and the **source branch** (the branch providing commits). Git does not infer the target branch from the argument name: the currently checked-out branch—that is, the current HEAD—is the branch that receives the merge.

A common operation is bringing a feature from `feature/payment` into `main`:

~~~bash
git switch main
git merge feature/payment
~~~

If you are currently on `feature/payment` and run `git merge main`, the result is reversed: Git integrates `main` into the feature branch. Choosing the wrong direction can alter history unexpectedly, especially when merges are performed on shared branches.

This lesson guides you through verifying target/source, checking repository status and ref freshness, reading commits and change scope before merging, understanding fast-forward and merge commits to the required level, and executing a controlled merge and verifying the result.

## 1. Distinguishing Target Branch and Source Branch

### 1.1. The Target Branch Is the Currently Checked-Out Branch

Syntax:

~~~bash
git merge <source>
~~~

Git integrates commits reachable from `<source>` into the **current branch**. The current branch is the branch that HEAD points to.

For example, to bring a feature into main:

~~~bash
git switch main
git merge feature/payment
~~~

In this example:

- Target: `main`.
- Source: `feature/payment`.
- HEAD before merge: tip commit of `main`.
- Argument to `git merge`: `feature/payment`.

The branch name after `git merge` is the source. Git does not have a `git merge <target> <source>` syntax to specify both sides that way.

### 1.2. Checking HEAD and Branch Before Merging

Use:

~~~bash
git branch --show-current
git status --short --branch
git log -1 --oneline --decorate
~~~

These three commands help verify:

- The name of the current branch.
- Whether the repository has uncommitted changes.
- Which commit HEAD points to and which refs are attached to that commit.

If `git branch --show-current` prints no branch name, you may be in a detached HEAD state. Do not merge before clearly determining which ref will hold the resulting commit.

### 1.3. Checking Both Branch Names Before Running the Command

~~~bash
git branch --list
git show -s --oneline main
git show -s --oneline feature/payment
~~~

If the source is a remote-tracking branch:

~~~bash
git show -s --oneline origin/feature/payment
~~~

Do not rely on similar-looking names like `main`, `master`, `release`, `origin/main`, or `origin/release`. Verify the exact ref you intend to use.

### 1.4. Merge Direction Diagram

~~~text
feature/payment  (source)
        |
        |  git merge feature/payment
        v
main             (target / current branch)
        |
        v
   HEAD after merge
~~~

The merge command is run while `main` is checked out. Source commits are integrated into the target's history. The source branch is not automatically deleted after merging.

### 1.5. The Argument Name Does Not Determine the Target

Example:

~~~bash
git switch feature/payment
git merge main
~~~

The command above brings commits from `main` into `feature/payment`. It does not bring the feature into main.

If you want to reverse the direction, switch to the target first and then merge the source:

~~~bash
git switch main
git merge feature/payment
~~~

Before running, say to yourself: "I am currently on branch ___ and want to integrate branch ___ into here." If you cannot fill in both names clearly, do not run the merge yet.

## 2. Ensuring the Working Tree Is Ready

### 2.1. Checking Local Changes

~~~bash
git status
git status --short
~~~

A merge may be rejected by Git if uncommitted changes are at risk of being overwritten. Even when Git allows it, local changes can make the outcome confusing when conflicts arise.

It is recommended to start a merge with a clean working tree and index. If you have work to preserve, commit it as an appropriate commit or stash it according to your team's workflow.

### 2.2. Distinguishing Staged, Unstaged, and Untracked

~~~bash
git diff
git diff --cached
git ls-files --others --exclude-standard
~~~

- `git diff`: changes in the working tree compared to the index.
- `git diff --cached`: staged changes compared to HEAD.
- `git ls-files --others --exclude-standard`: untracked files that are not ignored.

Check all three groups. An untracked file can be overwritten by a merge if the source adds a file at the same path. Git generally protects local files and aborts the operation when it detects data loss risk, but you should not rely on Git catching every situation the way you expect.

### 2.3. Handling Uncommitted Work Before Merging

If local changes belong to a complete unit of work, you can commit them:

~~~bash
git add -- path/to/file
git commit -m "Save current work"
~~~

If you need to temporarily set them aside:

~~~bash
git stash push -u -m "Work before merging feature/payment"
~~~

The `-u` option includes untracked files in the stash. Ignored files are not included unless you use another option such as `-a`; understand the scope before using it.

After the merge completes, restore:

~~~bash
git stash list
git stash pop
~~~

`stash pop` can cause conflicts. Do not drop the stash until you verify the changes have been fully restored.

### 2.4. Checking Whether Another Git Operation Is in Progress

~~~bash
git status
~~~

If the repository is in the middle of a merge, rebase, cherry-pick, or revert, finish or abort that operation properly before starting a new merge. One repository cannot safely handle multiple integration operations simultaneously on the same working tree.

You can check for conflict entries:

~~~bash
git ls-files -u
~~~

If there is output, the index still has unmerged paths. Resolve or abort the current operation first.

## 3. Updating Branch Information from Remote

### 3.1. Fetching First to Know the Latest Source and Target

Remote-tracking branches such as `origin/main` only reflect the state from the most recent fetch.

Update refs:

~~~bash
git fetch origin --prune
~~~

Or all remotes:

~~~bash
git fetch --all --prune
~~~

`fetch` downloads commits and updates remote-tracking refs according to configuration. It does not automatically merge changes into the current branch.

### 3.2. Distinguishing Local Branches and Remote-Tracking Branches

View branches along with their upstreams:

~~~bash
git branch -vv
~~~

Example:

~~~text
* main             a12bc34 [origin/main: behind 2] Prepare release
  feature/payment  d45ef67 [origin/feature/payment] Add payment validation
~~~

Here local `main` is two commits behind `origin/main`. If you merge the feature into main while local main is outdated, the target may not reflect the latest state of the main branch on the remote.

### 3.3. Updating Local Target Before Receiving Source

After fetching, switch to the target:

~~~bash
git switch main
~~~

Check the relationship with the remote:

~~~bash
git status -sb
git log --oneline main..origin/main
git log --oneline origin/main..main
~~~

- `main..origin/main`: commits present on origin/main that are not yet in local main.
- `origin/main..main`: commits present in local main that are not yet in origin/main.

If local target is merely behind and has no unique commits, you can fast-forward:

~~~bash
git merge --ff-only origin/main
~~~

`--ff-only` updates only when it can advance directly by ancestry; if the two branches have diverged, Git refuses instead of automatically creating a merge commit.

If local and remote have diverged, stop and follow your team's synchronization workflow. Do not use reset or force update to make the two branches look alike before understanding the separate commits.

### 3.4. When Source Is a Remote Branch

You can merge a remote-tracking branch directly after fetching:

~~~bash
git merge origin/feature/payment
~~~

Or check out the local source if your workflow requires it:

~~~bash
git switch feature/payment
git pull --ff-only
git switch main
git merge feature/payment
~~~

The second approach updates the local feature branch first, but use it only when the local branch has an appropriate upstream and team policy permits it.

Do not run `git pull` blindly on the target if you want explicit control over which remote and which ref are integrated. Pull is fetch plus integration according to configuration; read `git status -sb` and `git branch -vv` first.

## 4. Checking the History Relationship Between Target and Source

### 4.1. Viewing the Two-Branch Graph

~~~bash
git log --oneline --graph --decorate --all -20
~~~

The graph helps reveal:

- Source is ahead of target.
- Target is ahead of source.
- The two branches have diverged.
- There are merge commits on one of the two sides.

Do not look only at branch names; inspect the commit graph.

### 4.2. Identifying the Merge Base

~~~bash
git merge-base main feature/payment
~~~

The merge base is the appropriate common ancestor commit that Git uses as the starting point for a three-way merge in standard cases.

You can view commit details:

~~~bash
git show -s --oneline $(git merge-base main feature/payment)
~~~

In PowerShell, if you want to avoid command substitution syntax differences across shells, you can run `git merge-base` separately, copy the hash, and pass it to `git show`.

If there is no merge base, the two repositories or histories may share no common ancestor. Do not add `--allow-unrelated-histories` just to bypass the error; first verify whether you have the right repository and source.

### 4.3. Checking Whether Source Is Already in Target

~~~bash
git merge-base --is-ancestor feature/payment main
~~~

If the exit code is 0, the tip of source is an ancestor of target; the source commits are already reachable from target. If the exit code is 1, source is not an ancestor of target.

Conversely:

~~~bash
git merge-base --is-ancestor main feature/payment
~~~

If the exit code is 0, target is an ancestor of source. When merging source into target, this is the condition where a fast-forward can occur if target remains at that commit.

`--is-ancestor` commands use the exit code and normally print no output. In a shell, inspect the exit code immediately after the command.

### 4.4. Determining Which Branch Is Ahead

You can use:

~~~bash
git rev-list --left-right --count main...feature/payment
~~~

The output contains two numbers:

~~~text
2    4
~~~

With the order `main...feature/payment`, the first number is commits reachable only from main; the second number is commits reachable only from feature/payment. This example shows main has 2 unique commits and feature has 4 unique commits.

This is a quick way to detect whether two branches have diverged.

## 5. Inspecting Commits to Be Brought into Target

### 5.1. Listing Commits in Source That Are Not Yet in Target

~~~bash
git log --oneline main..feature/payment
~~~

The range `main..feature/payment` selects commits reachable from source but not reachable from target. This is usually the list of commits you want to review before merging.

View details:

~~~bash
git log --format=fuller main..feature/payment
~~~

Check subject, author, timestamps, and commit content. If there are experimental commits, debug commits, or out-of-scope changes, pause and discuss cleaning up the source branch before merging.

### 5.2. Viewing Both Sides of a Diverged History

~~~bash
git log --left-right --graph --oneline main...feature/payment
~~~

The `<` marker typically denotes commits only on the left side (main), while `>` denotes commits only on the right side (feature/payment). This is the symmetric difference of the two branches, excluding shared history.

Use this command to understand both what the target has changed since the common point and how the source has developed.

### 5.3. Ignoring Patch-Equivalent Commits During Review

~~~bash
git log --left-right --cherry-pick --oneline main...feature/payment
~~~

`--cherry-pick` omits commits that have an equivalent patch on the opposite side in certain cases, which is useful when commits were cherry-picked between two branches and have different hashes.

This is a review aid; it does not replace checking actual content or your team's merge conventions.

### 5.4. Viewing Changed Files in Source

~~~bash
git diff --name-status main...feature/payment
git diff --stat main...feature/payment
~~~

With the triple-dot syntax in `git diff A...B`, Git compares the merge base of A and B against B. Thus, the command shows changes on the source side since the common point.

It is helpful for answering: "What changes does the source branch bring compared to when the two branches diverged?"

### 5.5. Reading the Proposed Patch from Source

~~~bash
git diff main...feature/payment
~~~

Read the hunks to verify:

- Which logic was added or changed.
- Which files were deleted or renamed.
- Which APIs or schemas changed.
- Whether there are config files, secrets, or auto-generated data.
- Whether there are changes outside the feature scope.

This is the diff from the merge base to the source, not a full simulation of the final merge result.

### 5.6. Distinguishing Triple-Dot and Two-Argument Diffs

The following two commands answer different questions:

~~~bash
git diff main...feature/payment
git diff main feature/payment
~~~

- `git diff main...feature/payment`: compares the merge base against source, showing what source has changed since the common point.
- `git diff main feature/payment`: directly compares the two tip trees, showing how the current file states differ between the two branches.

If main also has its own changes, a two-argument diff will include differences from the target side as well. To review what the source contributes, usually start with the triple-dot diff.

### 5.7. Checking Whitespace and Unexpected Files

~~~bash
git diff --check main...feature/payment
git diff --name-only main...feature/payment
~~~

`--check` detects certain whitespace errors in the patch. The file list helps cross-check scope against the ticket or pull request.

No diff alone proves a merge will be conflict-free. Conflicts also depend on how both sides changed the same content regions and on the merge algorithm.

## 6. Confirming the Target Matches the Merge Policy

### 6.1. Checking Branch Conventions

Before merging into an important branch such as `main`, `release`, or `production`, confirm:

- Is a pull request / code review required?
- Are green CI checks or approvals required?
- Is there a fast-forward-only policy or an always-merge-commit policy?
- Is commit signing or signature verification required?
- Is branch protection enabled on the remote?
- Are release notes, migrations, or version bumps needed?

Local Git does not automatically know every hosting platform policy. If the repository requires merging via pull request, use that process instead of merging directly to bypass controls.

### 6.2. Selecting the Reviewed Source Ref

Pull requests normally display the source branch and target branch clearly. Match both names against local refs after fetching.

If the PR targets `release/2.x` while you happen to be on `main`, do not change the target on a whim just because main is a familiar branch.

### 6.3. Checking CI Status and the Latest Source Commit

~~~bash
git log -1 --format=fuller feature/payment
git show --stat --oneline feature/payment
~~~

Ensure the tip commit you plan to merge is the exact commit that was reviewed/tested. If the source branch advanced with new commits after review, the actual scope may differ from the approved pull request.

## 7. Performing the Merge After Preflight Checks Pass

### 7.1. Switching to the Target Once More

~~~bash
git switch main
git status --short --branch
git branch --show-current
~~~

Confirm the current branch is the target. Verify HEAD has not been moved by another operation since your review.

### 7.2. Merging Source

~~~bash
git merge feature/payment
~~~

Git may:

- Fast-forward the target if the target is an ancestor of the source.
- Create a merge commit if the two branches diverged and automatic merging succeeds.
- Stop with conflicts for you to resolve.
- Report Already up to date if the source brings no new commits into the target.

The outcome depends on the ancestry relationship, the contents of both branches, and merge configuration.

### 7.3. Allowing Fast-Forward Only

If policy requires the target to advance linearly without creating a merge commit:

~~~bash
git merge --ff-only feature/payment
~~~

If the two branches have diverged, the command refuses. This is a signal to handle history according to team conventions, not a reason to drop the option and merge arbitrarily.

### 7.4. Always Creating a Merge Commit When Integrating

If the team wants to keep a commit marking the integration event:

~~~bash
git merge --no-ff feature/payment
~~~

This option forces creating a merge commit even when fast-forward is possible, unless there is nothing new to integrate.

Choose `--ff`, `--ff-only`, or `--no-ff` per repository policy. This is a history decision and does not change target/source roles.

### 7.5. Previewing the Merge Result with no-commit

When you need to inspect the integration result before creating a merge commit:

~~~bash
git merge --no-commit --no-ff feature/payment
~~~

The command starts the merge, updates the index and working tree, and stops before creating the commit if there is content to integrate. Combine `--no-ff` to guarantee a pause point even when the merge could fast-forward; `--no-commit` alone does not prevent fast-forward.

This is not a dry run: the repository has entered a merge state. Afterward:

~~~bash
git status
git diff
git diff --cached
~~~

Run tests and review the content. If satisfied, create the merge commit:

~~~bash
git commit
~~~

To cancel the paused merge:

~~~bash
git merge --abort
~~~

Make sure local changes were preserved before starting; abort is not a backup mechanism for all local data.

## 8. If You Discover You Selected the Wrong Target Branch

### 8.1. Caught Before Running Merge

If you are on the source instead of the target, simply switch to the target:

~~~bash
git switch main
git branch --show-current
~~~

Then run preflight checks again. There is no need to create or delete branches just to fix merge direction.

### 8.2. Merge In Progress and Not Yet Committed

If you started merging on the wrong target and Git is still in a merge state, check:

~~~bash
git status
~~~

Once confirmed that you need to cancel:

~~~bash
git merge --abort
~~~

After aborting:

~~~bash
git status --short --branch
git branch --show-current
~~~

Switch to the correct target and re-run the checks.

### 8.3. Merge Already Completed on the Wrong Branch

If the merge has already completed, stop before running reset, revert, or force push. Determine:

- Was the merge a fast-forward or a merge commit?
- Has the wrong branch already been pushed?
- Has anyone fetched or created commits on top of the result?
- Does the correct target also need those same changes?
- Were any local changes made after the merge?

For an unshared merge commit, there may be ways to adjust history; for an already-shared branch, reverting or making a corrective commit is usually safer than rewriting history. Choose the action based on actual state and team policy.

Do not run `git reset --hard` solely to move the branch back to its pre-merge position; that command can delete unrelated local changes.

## 9. Checking Conflicts and Merge Results

### 9.1. Conflicts Do Not Mean Target/Source Were Swapped

If Git reports conflicts, the merge is still executing on the current target. Confirm:

~~~bash
git branch --show-current
git status
git ls-files -u
~~~

HEAD normally remains at the target commit until the merge commit is created. The source is recorded in the merge state and the index contains the versions needing resolution.

### 9.2. Resolving Conflicts by Content

Open each conflicted file, compare changes from both sides, and edit the final result. Do not pick the entire ours or theirs version if both sides contain logic that needs to be kept.

After resolving:

~~~bash
git add -- path/to/resolved-file
git status
git ls-files -u
~~~

When no unmerged entries remain, inspect the staged diff and run tests.

### 9.3. Continuing or Aborting the Merge

Once all conflicts are resolved:

~~~bash
git diff --cached
git diff --check
git merge --continue
~~~

For a regular merge, Git may ask you to create the commit with `git commit`; `git merge --continue` is an explicit way to express continuing while in a merge state.

If you decide to cancel:

~~~bash
git merge --abort
~~~

Do not manually delete conflict markers or edit `.git/MERGE_HEAD` to exit the state. Use the corresponding Git commands.

## 10. Verifying After Merging

### 10.1. Checking Branch and Status

~~~bash
git status --short --branch
git branch --show-current
git log -1 --oneline --decorate
~~~

Ensure you are still on the intended target and the repository has no ongoing merge state remaining.

### 10.2. Viewing the Graph After Merging

~~~bash
git log --graph --oneline --decorate --all -20
~~~

The graph shows whether source was integrated via fast-forward or via a merge commit. Verify that the source commits are reachable from the target.

### 10.3. Checking Parents If a Merge Commit Was Created

~~~bash
git show -s --format="%H%n%P%n%s" HEAD
~~~

A standard merge commit has multiple parents. The first parent is typically the target tip before the merge; the second parent is typically the merged source tip. Parent order matters when inspecting history and when reverting a merge.

### 10.4. Confirming Source Was Integrated

~~~bash
git merge-base --is-ancestor feature/payment main
~~~

If the exit code is 0, the tip of source is now an ancestor of target. This is a useful post-merge ancestry check. If the source branch has advanced after the merge, this check may return 1 even though the earlier source commits were integrated; in that case, check the specific reviewed commit hash or merge base.

### 10.5. Running Tests and Checking Remaining Changes

~~~bash
git diff
git diff --cached
git status
~~~

Run appropriate project build/test commands. If the merge introduced unwanted changes or tests fail, do not push immediately; identify the root cause and handle it according to team workflow.

## 11. Complete Example: Bringing a Feature into Main

Suppose the team needs to bring `feature/payment` into `main`.

### Step 1 — Fetch refs

~~~bash
git fetch origin --prune
~~~

### Step 2 — Select target

~~~bash
git switch main
git status --short --branch
git branch --show-current
~~~

Verify you are on main and the working tree is clean.

### Step 3 — Sync target

~~~bash
git status -sb
git log --oneline main..origin/main
git log --oneline origin/main..main
~~~

If main is only behind and has not diverged:

~~~bash
git merge --ff-only origin/main
~~~

### Step 4 — Inspect source and history

~~~bash
git show -s --oneline feature/payment
git log --oneline main..feature/payment
git log --left-right --graph --oneline main...feature/payment
~~~

### Step 5 — Review source scope

~~~bash
git diff --stat main...feature/payment
git diff --name-status main...feature/payment
git diff --check main...feature/payment
~~~

Read the full patch and verify the files belong to the payment feature.

### Step 6 — Run tests on source

You can switch to source to test separately if needed, then return to target and verify status. Or use CI/pull request per team workflow. Do not accidentally carry local changes generated during testing over to the target.

### Step 7 — Merge into target

~~~bash
git switch main
git status --short --branch
git merge --no-ff feature/payment
~~~

Use `--no-ff` only if team policy wants to preserve a merge commit; otherwise use the default merge policy or `--ff-only` accordingly.

### Step 8 — Verify the result

~~~bash
git status --short --branch
git log --graph --oneline --decorate -15
git merge-base --is-ancestor feature/payment main
~~~

Run post-merge tests. Once all checks pass and the branch is permitted to update the remote, push according to your team's workflow.

## 12. Common Mistakes

- **Standing on source and running merge target:** this integrates target into source. Always verify the current branch first.
- **Thinking the argument to git merge is the target:** the argument is the source; the target is the checked-out branch.
- **Not fetching before reviewing:** local remote-tracking refs may be stale and not reflect the latest commits on the server.
- **Looking only at branch names:** two refs with similar names may point to different commits. Check the log and hashes.
- **Ignoring uncommitted changes:** local work can be overwritten or mixed into conflict resolution. Preserve it before merging.
- **Using git diff A...B as a direct diff between two tips:** with diff, triple-dot compares the merge base against B; two arguments compare the two trees directly.
- **Assuming a clean diff means no conflicts:** a diff helps review scope but does not guarantee automatic merging.
- **Using pull without knowing configuration:** pull may integrate via merge or rebase per config. Fetch first, then explicitly choose ref and command when control is needed.
- **Ignoring separate commits on target:** source is not the only side that changes; inspect the graph and both sides of history.
- **Using --no-commit like a dry run:** merge already modifies the index/working tree. Combine with --no-ff to pause before commit when review is needed.
- **Running reset --hard after a mistaken merge:** can lose local data. Check status and pick an appropriate recovery method.
- **Pushing right after merging without testing:** the merged result must be verified like any new change.

## 13. Pre-Merge Checklist for git merge

- [ ] Clearly identified target and source.
- [ ] Confirmed current branch is the target.
- [ ] Not in detached HEAD state.
- [ ] Working tree and index are clean or local changes are preserved.
- [ ] No ongoing merge/rebase/cherry-pick/revert.
- [ ] Fetched remote and checked ref freshness.
- [ ] Checked whether local target has diverged from upstream.
- [ ] Inspected source commits not yet in target.
- [ ] Checked graph and merge base.
- [ ] Reviewed triple-dot diff to understand changes from source.
- [ ] Checked files, whitespace, tests, and ticket scope.
- [ ] Confirmed merge policy of the target branch.
- [ ] Selected the proper fast-forward/merge commit option per convention.
- [ ] Know how to abort if a merge stalls mid-way.

## 14. Quick Reference Table

| Goal | Command |
| --- | --- |
| Confirm current branch | `git branch --show-current` |
| View status and upstream | `git status -sb` |
| View branches and upstreams | `git branch -vv` |
| Update remote-tracking refs | `git fetch --all --prune` |
| Switch to target | `git switch main` |
| View latest commit of source | `git show -s --oneline feature/payment` |
| List source commits not yet in target | `git log --oneline main..feature/payment` |
| View diverged history on both sides | `git log --left-right --graph --oneline main...feature/payment` |
| Count unique commits on each side | `git rev-list --left-right --count main...feature/payment` |
| Find merge base | `git merge-base main feature/payment` |
| Check if source is already ancestor of target | `git merge-base --is-ancestor feature/payment main` |
| View files changed by source | `git diff --name-status main...feature/payment` |
| View stats of source changes | `git diff --stat main...feature/payment` |
| Read patch of source changes | `git diff main...feature/payment` |
| Check whitespace | `git diff --check main...feature/payment` |
| Merge source into current target | `git merge feature/payment` |
| Allow fast-forward only | `git merge --ff-only feature/payment` |
| Force creating a merge commit | `git merge --no-ff feature/payment` |
| Pause before commit to review | `git merge --no-commit --no-ff feature/payment` |
| Cancel an ongoing merge | `git merge --abort` |
| View graph after merging | `git log --graph --oneline --decorate --all` |

## 15. Summary

In Git, the target is the currently checked-out branch; the source is the ref passed to `git merge`. To bring `feature/payment` into `main`, you must first check out main, verify HEAD and working tree state, and only then merge feature/payment.

Before merging, fetch the remote to update refs, check whether local target has diverged from upstream, inspect source commits not yet in target, and examine the merge base, graph, and diff. `git log target..source` lists commits unique to source; `git diff target...source` shows source changes since the merge base. These commands help you understand scope, though they do not guarantee whether conflicts will occur.

Once preflight checks pass, choose the fast-forward or merge commit policy per project conventions, perform the merge, resolve any conflicts, run tests, and verify the branch, commit graph, and repository status. Checking merge direction and scope beforehand prevents integrating into the wrong branch and keeps history easy to review and trace.

# Pausing Before Creating a Commit with git merge --no-commit

When merging a branch, Git normally prepares the resulting snapshot and immediately creates a merge commit if the two histories have diverged. In certain situations, you want to inspect the combined result before committing: see which files changed, run tests, review configuration, or verify conflict resolution content. The <code>git merge --no-commit</code> option lets you pause at that point so you can decide whether to create the merge commit.

What matters is understanding the exact pause point: Git has already performed the combination into the index and working tree, but has not recorded a merge commit and has not moved the current branch to the resulting commit. If the merge produces conflicts, Git also pauses for you to resolve them. If a fast-forward is possible, <code>--no-commit</code> alone cannot prevent the branch from moving because fast-forward does not create a merge commit; when you need to inspect before committing, combine <code>--no-ff --no-commit</code>.

This lesson belongs to the **Branch Merging** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from working tree, staging area, commits, and history to branches, merging, rebasing, remotes, and tags; it also builds skills in branch-based collaboration, conflict resolution, tracking down changes, and recovering from mistakes while preserving important history. Knowing how to pause a merge before committing helps you verify the integration snapshot and record history only after checking the result.

## 1. What Does a Normal git merge Do?

Suppose you are on the <code>main</code> branch and want to integrate the <code>feature/payment</code> branch. When the histories have diverged, the command:

~~~bash
git switch main
git merge feature/payment
~~~

typically performs these steps:

1. Find the merge base, i.e., the common commit serving as the baseline for combining changes.
2. Compare the snapshots of the base, the current branch, and the branch being merged.
3. Combine the changes into the index and working tree.
4. If there are no conflicts and a merge commit is needed, create the merge commit.
5. Move the current branch to the new merge commit.

Example history before merging:

~~~text
          D --- E  feature/payment
         /
A --- B --- C --- F  main
~~~

If the three-way merge succeeds, Git creates commit <code>M</code> with two parents, <code>F</code> and <code>E</code>:

~~~text
          D --- E -----------.
         /                    \
A --- B --- C --- F ----------- M  main
~~~

The merge commit stores the combined snapshot. The <code>main</code> branch moves from <code>F</code> to <code>M</code>; the source branch <code>feature/payment</code> still points to <code>E</code>.

In a normal conflict-free merge, you may not get a chance to inspect the final snapshot before the merge commit is created. That is where <code>--no-commit</code> is useful.

## 2. Where Does --no-commit Pause?

Run:

~~~bash
git switch main
git merge --no-commit feature/payment
~~~

If a merge commit is required, Git performs the combination and pauses right before the commit creation step. At that point:

- The current branch still points to the pre-merge commit, e.g., <code>F</code>.
- <code>HEAD</code> still resolves to that current commit.
- The index contains the staged merge result if there were no conflicts.
- The working tree reflects the merged result content.
- Git retains a pending merge state, including information about the commit being merged.
- No new merge commit exists in history yet.

Illustration:

~~~text
Branch history remains as before:
          D --- E  feature/payment
         /
A --- B --- C --- F  main, HEAD

Index and working tree:
Snapshot resulting from combining F with E
waiting to be inspected and committed.
~~~

You can inspect the staged content:

~~~bash
git status
git diff --cached --stat
git diff --cached
~~~

After inspecting and deciding to accept the result:

~~~bash
git commit
~~~

Git uses the pending merge information to create the merge commit. Only then does the current branch advance to the new merge commit.

If you decide not to proceed, you can cancel the merge with <code>git merge --abort</code>; this is covered in later sections.

## 3. Why Must You Pair --no-ff with --no-commit?

This is the most easily misunderstood aspect of this option.

### When the Merge Can Fast-Forward

Suppose <code>main</code> is at <code>C</code>, while <code>feature</code> has two additional commits <code>D</code> and <code>E</code>:

~~~text
A --- B --- C --- D --- E
          main            feature
~~~

Commit <code>C</code> is an ancestor of <code>E</code>. Git can fast-forward by moving the <code>main</code> branch straight to <code>E</code>, without creating a merge commit.

The following command does not guarantee pausing before updating the branch:

~~~bash
git merge --no-commit feature
~~~

Because there is no merge commit to create, Git can fast-forward and update <code>main</code> immediately. The <code>--no-commit</code> option does not prevent this operation.

### Forcing a Pause Before the Merge Commit

Combine both options:

~~~bash
git merge --no-ff --no-commit feature
~~~

- <code>--no-ff</code> prevents fast-forward, requiring a merge commit even when fast-forward is possible.
- <code>--no-commit</code> requests pausing before creating the merge commit.

As a result, Git prepares the merge state for you to inspect while the <code>main</code> branch remains at the old commit. When you run <code>git commit</code>, the new merge commit is created and the branch advances.

| Option | Can fast-forward occur? | Pauses before merge commit? |
|---|---|---|
| No options | Yes, if history allows | No |
| <code>--no-commit</code> | Yes | Not guaranteed; fast-forward creates no merge commit |
| <code>--no-ff</code> | No | No; merge commit is typically created immediately |
| <code>--no-ff --no-commit</code> | No | Yes, if a merge needs to be performed and is not stopped by another error |

If the two branches are already up to date and there is nothing to integrate, Git does not create a merge commit just to satisfy the options. <code>--no-commit</code> also does not turn a no-change merge into a pending merge session.

## 4. Preparing Before a Merge with Inspection

Before running the merge, verify the target branch, source branch, and local state.

### Confirming the Current Branch

~~~bash
git branch --show-current
git status --short --branch
~~~

The current branch is the branch that will be updated. If you want to integrate feature into <code>main</code>, check out <code>main</code> first.

### Checking Uncommitted Changes

~~~bash
git diff
git diff --cached
~~~

You should start with a clean working tree and index so that inspecting the merge result is not mixed with prior personal changes. If there is work to keep, commit or stash it according to your team's workflow before merging.

### Updating Remote-Tracking Refs

If the source or target branch comes from a remote:

~~~bash
git fetch origin
git branch -vv
~~~

Fetch updates local remote-tracking refs such as <code>origin/main</code> and <code>origin/feature/payment</code>. It does not automatically update the local <code>main</code> branch.

### Checking Change Scope Before Merging

~~~bash
git log --oneline --graph --decorate main..feature/payment
git diff --stat main...feature/payment
git diff --name-status main...feature/payment
~~~

These commands let you see commits unique to feature and the scope of changed files since the branch point. If the content is unclear, read the detailed diff before starting the merge.

## 5. Step-by-Step Merge and Inspection Workflow

For example, suppose you want to merge local branch <code>feature/payment</code> into <code>main</code> and inspect the snapshot before creating the commit.

### Step 1: Switch to the target branch

~~~bash
git switch main
~~~

Verify:

~~~bash
git branch --show-current
git status --short
~~~

### Step 2: Run the merge with a pause point

~~~bash
git merge --no-ff --no-commit feature/payment
~~~

If there are no conflicts, Git prepares the result in the index and working tree and stops before creating the merge commit.

### Step 3: Check the merge state

~~~bash
git status
git rev-parse HEAD
git rev-parse MERGE_HEAD
~~~

<code>MERGE_HEAD</code> records the commit being merged into the pending merge process. For a simple two-branch merge, it usually resolves to the tip of the source branch at the time the merge began. If <code>rev-parse MERGE_HEAD</code> reports that the revision cannot be found, there may be no pending merge—for instance, the operation fast-forwarded or there was nothing to merge.

### Step 4: Inspect the prepared snapshot

~~~bash
# Overview of changed files relative to HEAD
git diff --cached --stat

# Change types per file
git diff --cached --name-status

# Staged result content
git diff --cached
~~~

Because Git has already placed the merge result into the index, <code>git diff --cached</code> is the primary command for inspecting the snapshot that will be recorded in the merge commit. <code>git diff</code> only shows unstaged changes relative to the index; if you have not edited anything after the merge, this command may produce no output.

### Step 5: Run project checks

Run appropriate tests, builds, or manual checks. For example:

~~~bash
./gradlew test
~~~

Or for a project using npm:

~~~bash
npm test
~~~

These are illustrative examples; use your project's actual verification commands. If tests generate or modify files, re-check status so unintended artifacts are not included in the merge commit.

### Step 6: Create the merge commit once accepted

~~~bash
git status
git diff --cached
git commit
~~~

Git opens the editor with the default merge message or uses a prepared message. You can edit the message if team conventions allow, then save and close the editor.

Verify after committing:

~~~bash
git log --oneline --graph --decorate -5
git show --stat --oneline HEAD
git status
~~~

The <code>main</code> branch now points to the new merge commit. The working tree should be clean if no post-merge changes were made.

## 6. Inspecting What Is Staged After Merging

In a conflict-free merge, Git normally writes the combined result into the index at stage 0. Therefore:

~~~bash
git diff --cached
~~~

shows the difference between the index and the current HEAD. This is the content that gets recorded in the commit if you complete the merge.

Other helpful commands:

~~~bash
# List files and statuses
git diff --cached --name-status

# Per-file statistics
git diff --cached --stat

# Check for whitespace errors
git diff --cached --check

# View the index by stage
git ls-files --stage
~~~

If you edited files after the merge without re-staging them, the new edits reside in the working tree. In that case:

~~~bash
git diff
git diff --cached
~~~

show two different parts: what is already in the index and what was modified afterward. Decide whether to include those subsequent edits in the merge commit before committing.

## 7. When the Merge Produces Conflicts

<code>--no-commit</code> does not mean Git will always prepare a complete result. If both branches modify the same region or make changes that cannot be combined automatically, Git stops in a conflict state for you to resolve.

Inspect:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Unresolved files can appear in the index across multiple stages:

| Stage | Content |
|---|---|
| 1 | Merge base |
| 2 | Ours, i.e., version from the current branch |
| 3 | Theirs, i.e., version from the branch being merged |

During a conflict, there is no complete stage 0 entry for that path until you resolve it and stage the result.

### Reading Conflict Markers

In text files, Git may insert markers:

~~~text
<<<<<<< HEAD
Content from current branch
=======
Content from branch being merged
>>>>>>> feature/payment
~~~

Treat these as hints showing both sides, not a rule forcing you to pick one side wholesale. You can combine both, adjust the logic, or write new content to preserve the intended behavior.

### Resolving and Staging Files

After editing the content:

~~~bash
git add src/payment/PaymentService.java
~~~

Verify no unmerged entries remain:

~~~bash
git diff --name-only --diff-filter=U
git status
~~~

Once all conflicts are resolved, inspect the resulting snapshot:

~~~bash
git diff --cached --check
git diff --cached --stat
git diff --cached
~~~

Run appropriate tests, then create the merge commit:

~~~bash
git commit
~~~

Do not commit while unmerged files remain. If you want to discard the entire ongoing merge and return to the pre-merge state, see <code>git merge --abort</code>.

## 8. --no-commit Is Not --squash

Both options can let you inspect content before creating a commit, but the resulting history differs.

| Criterion | <code>--no-commit</code> | <code>--squash</code> |
|---|---|---|
| Purpose | Pause before creating a merge commit | Prepare source branch changes as a single combined change to commit |
| Preserves merge parent info | Yes, upon completing the merge commit | No |
| Merge state | Has a pending merge state, typically with <code>MERGE_HEAD</code> | Does not record merge parents like a regular merge |
| Resulting commit | Merge commit with parents of the combined histories | Regular commit with one parent (current HEAD) |
| How to finish | <code>git commit</code> | <code>git commit</code> to create a regular commit |

Squash example:

~~~bash
git switch main
git merge --squash feature/payment
git diff --cached
git commit -m "Add payment retry support"
~~~

The final commit contains the feature's changes but does not record a parent link to the feature tip like a merge commit. Choose squash when you want to collapse changes into a single linear commit per team conventions; choose <code>--no-commit</code> when you want a merge commit but need to inspect before recording it.

## 9. Distinguishing --no-commit from --no-ff

The two options solve different problems:

- <code>--no-ff</code> controls how Git integrates history, preventing fast-forward so a merge commit is created.
- <code>--no-commit</code> controls when the merge commit is created, pausing before the commit-writing step.

Example:

~~~bash
git merge --no-ff --no-commit feature/payment
~~~

This command both requires preserving a merge node and lets you review the result before creating that node.

If you only run:

~~~bash
git merge --no-ff feature/payment
~~~

Git still creates the merge commit immediately after combining succeeds, without waiting for manual review.

If you only run:

~~~bash
git merge --no-commit feature/payment
~~~

Git can fast-forward if history permits, in which case there is no merge commit to pause before.

## 10. Aborting a Merge or Exiting the Merge State

If the merge result is wrong or you want to start over, you can use:

~~~bash
git merge --abort
~~~

This command attempts to restore the index and working tree to their state before the merge began. It is especially useful when dealing with conflicts or when paused in a pending merge state awaiting commit.

If you want to end tracking of the merge state while keeping the current index and working tree as-is, there is:

~~~bash
git merge --quit
~~~

The two commands are not the same:

| Command | Effect |
|---|---|
| <code>git merge --abort</code> | Cancels the merge and attempts to restore the pre-merge state |
| <code>git merge --quit</code> | Removes tracked merge state while keeping the index and working tree |

<code>--quit</code> is not a safe substitute for abort if you want to discard merge results. It can leave combined files or conflict markers in the working tree/index without merge metadata to continue.

### Note on Local Changes Before Merging

Git recommends not starting a merge when uncommitted changes exist that might be overwritten. In some cases Git can preserve local changes, but <code>git merge --abort</code> may not always restore perfectly if complex uncommitted content existed prior to the merge.

Therefore, before running a merge with a pause point:

1. Check <code>git status</code>.
2. Commit or stash content you need to keep.
3. Run the merge.
4. If aborted, re-check the working tree and index with <code>git status</code>.

## 11. Inspecting Merge State Using Internal Indicators

While a merge is pending completion, Git keeps metadata indicating an ongoing process. You can inspect it via Git commands:

~~~bash
# Check repository status
git status

# Check source commit of the pending merge
git rev-parse -q --verify MERGE_HEAD

# Check current commit before merge commit is created
git rev-parse HEAD

# Check files still in conflict
git diff --name-only --diff-filter=U
~~~

Do not manually edit or delete state files in the <code>.git</code> directory. Use merge/commit/abort commands so Git updates metadata consistently.

In multi-head merges or complex scenarios, there may be more parent information than in a simple two-branch merge. Do not assume <code>MERGE_HEAD</code> always has only one line; use Git commands to inspect rather than writing scripts based on internal file structure.

## 12. Using merge --no-commit in a Review Workflow

Suppose a team requires verifying tests and configuration files before merging a feature:

~~~bash
# Update remote-tracking refs
git fetch origin

# Ensure we are on target branch and working tree is clean
git switch main
git status --short

# Preview scope of changes
git diff --stat origin/main...feature/payment
git diff --name-status origin/main...feature/payment

# Prepare merge without creating merge commit yet
git merge --no-ff --no-commit feature/payment

# Inspect staged snapshot
git diff --cached --check
git diff --cached --stat
git diff --cached

# Run project tests
./gradlew test

# If checks pass, create merge commit
git commit
~~~

If tests fail or unacceptable changes are discovered:

~~~bash
git merge --abort
git status
~~~

Then switch back to the source branch to make fixes, or discuss with the branch author. Do not proceed to commit merely because Git has already prepared the snapshot; the merge commit should reflect a result the team has approved.

## 13. Situations Without a Merge Commit to Pause Before

<code>--no-commit</code> is only meaningful when Git is preparing to create a merge commit. There are cases where a merge command does not create a commit:

| Situation | Outcome |
|---|---|
| Source branch is already integrated, no new changes | Git reports up to date; no pending merge state |
| Fast-forward is allowed | Target branch can move directly; <code>--no-commit</code> does not block it |
| Using <code>--no-ff --no-commit</code> when fast-forward is possible | Git creates merge state and pauses before merge commit |
| Merge has conflicts | Git stops to resolve conflicts; no merge commit created yet |
| Merge rejected due to unsafe local state | Git does not perform the merge; handle working tree/index and retry |
| Merge canceled with <code>--abort</code> | Returns to pre-merge state as far as Git can restore |

## 14. Common Errors and Misconceptions

| Symptom | Cause | How to handle |
|---|---|---|
| <code>--no-commit</code> yet branch advanced | Merge fast-forwarded | Add <code>--no-ff</code> |
| Cannot find <code>MERGE_HEAD</code> | Merge fast-forwarded, was up-to-date, or no merge pending | Check log, branch, and status |
| <code>git diff</code> does not show merge results | Results are already in the index | Use <code>git diff --cached</code> |
| <code>git commit</code> reports unmerged files remain | Not all conflicts resolved | Check <code>git diff --name-only --diff-filter=U</code> |
| Merge commit created immediately despite wanting review | Missing <code>--no-commit</code> | Use <code>--no-ff --no-commit</code> next time |
| Used <code>--squash</code> expecting two parents | Squash does not create merge parent relationships | Use normal merge with <code>--no-commit</code> if a merge commit is needed |
| Used <code>--quit</code> thinking it restored pre-merge state | Quit only removes merge state, keeps index/working tree | Use <code>--abort</code> when you need to cancel merge results |
| Local changes still visible after abort | Pre-merge changes existed or data could not be auto-restored completely | Inspect diff, stash/backups, and status before continuing |
| Merge rejected due to local changes | Working tree/index contains content that could be overwritten | Commit or stash changes to keep, then retry |

## 15. Checklist Before Creating a Merge Commit

Before running the merge:

- Confirm target branch with <code>git branch --show-current</code>.
- Confirm source branch and update remote-tracking refs if needed.
- Inspect working tree and index.
- Preview commits and files to be integrated.
- Decide whether you need to preserve a merge commit or want to squash.

While the merge is pending:

- Check <code>git status</code> and <code>MERGE_HEAD</code>.
- Use <code>git diff --cached</code> to inspect the prepared snapshot.
- Resolve all unmerged entries if any.
- Run tests/build and check whitespace.
- Confirm no unintended changes were added to the index.

Before finishing:

- Re-read the staged diff.
- Confirm an appropriate merge message.
- Run <code>git commit</code> once approved.
- Inspect the commit graph and working tree after merging.

## 16. Self-Check Exercises

Practice in a test repository with two branches:

1. Create a feature branch with two commits ahead of main and run <code>git merge --no-commit</code>; observe that Git can fast-forward.
2. Reset the test repository to its initial state and run <code>git merge --no-ff --no-commit</code>; confirm the target branch has not moved yet.
3. Use <code>git status</code>, <code>git rev-parse HEAD</code>, and <code>git rev-parse MERGE_HEAD</code> to confirm a merge is pending.
4. Use <code>git diff --cached --stat</code> and <code>git diff --cached</code> to inspect the snapshot.
5. Make a local edit after the merge is prepared, then distinguish the output of <code>git diff</code> vs. <code>git diff --cached</code>.
6. Complete the merge with <code>git commit</code> and observe the merge commit has two parents.
7. Repeat in another test repository, but cancel using <code>git merge --abort</code>.
8. Compare the state after <code>git merge --abort</code> and <code>git merge --quit</code>; only execute when you understand what data will remain.
9. Intentionally create a conflict, resolve it, stage it, and complete the merge.
10. Try <code>git merge --squash</code> and compare the parent of the resulting commit against a regular merge commit.
11. Write a merge review workflow for your team, specifying when running tests before committing is mandatory.

<code>git merge --no-commit</code> creates a pause point for you to inspect the combined result before recording a merge commit. Remember to pair <code>--no-ff</code> when you need to prevent fast-forward, inspect the snapshot with <code>git diff --cached</code>, resolve all conflicts, and commit only after accepting the result.

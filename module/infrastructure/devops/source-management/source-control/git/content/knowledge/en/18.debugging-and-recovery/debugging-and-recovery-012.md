# Verifying Content, History, and Test Results After Recovery

## Why Verify After Recovery?

Recovery in Git means bringing source code or history back to a desired state after a mistaken operation, lost commits, overwritten files, a broken merge, or misapplied changes. Operations such as restore, reset, revert, cherry-pick, stash apply, merge --abort, and rebase --abort each affect the working tree, staging area, commits, and branch references differently.

A command exiting with code 0 only tells you that Git executed the requested operation. That alone does not prove:

- The right files and the right versions were restored.
- Valid changes created after the recovery point were not lost.
- The current branch points to the desired commit.
- Commit history still preserves proper parent-child relationships and required milestones.
- No incomplete merge, rebase, cherry-pick, or revert operation remains.
- The application still compiles, passes tests, and fulfills expected business behavior.

For example, git reset --hard can return the working tree to the specified commit and make git status report clean. However, if the wrong old commit was chosen, the repository looks clean while the branch was rolled back to the wrong state. Similarly, git revert can successfully create a reverting commit, yet remaining logic may still depend on the functionality that was just removed.

Therefore, post-recovery verification requires checking three layers:

1. **Content:** what do the files, staging area, and working tree currently hold?
2. **History:** do HEAD, the branch, and any new commits match the target?
3. **Behavior:** do builds, tests, and affected user flows work properly?

## Start by Recording Repository State

Before performing any further operations, check the current state:

~~~bash
git status
git status --short
git branch --show-current
git rev-parse --show-toplevel
git rev-parse HEAD
~~~

These commands tell you:

- Which repository you are in.
- Which branch is currently checked out.
- Which commit HEAD points to.
- Whether the working tree and staging area have changes.
- Whether Git is in the middle of a multi-step operation.

If you need to record the current commit for reference, save the commit hash from git rev-parse HEAD in your work notes or terminal session. Do not overwrite files inside the repository just to store inspection notes.

### Reading git status --short Correctly

The short format uses two characters to describe status:

~~~text
 M src/ReportService.java
M  src/ReportRepository.java
MM src/ReportController.java
A  src/ReportFilter.java
D  src/LegacyReport.java
?? notes/recovery-check.txt
~~~

The first character describes the status in the staging area; the second character describes changes in the working tree relative to the index.

| Symbol | Common Meaning |
|---|---|
| ␠M | Tracked file with unstaged changes |
| M␠ | File with staged changes |
| MM | File with both staged changes and newer unstaged changes |
| A␠ | New file staged |
| D␠ | File staged for deletion |
| ?? | File not tracked by Git |

Filenames may be displayed with rename or copy details depending on configuration and diff format. When you need full certainty, run git status instead of relying on a single symbol.

A clean working tree normally produces no lines in git status --short. However, clean does not mean correct: you still need to confirm HEAD is at the desired commit and that commit's contents align with the recovery goal.

## Verifying Content in the Working Tree and Staging Area

Git has three areas to distinguish when inspecting content:

- **HEAD:** snapshot of the current commit.
- **Staging area (index):** content that will be written into the next commit.
- **Working tree:** files currently on disk after local edits.

Diff commands help verify differences across these areas.

~~~bash
# Unstaged changes in the working tree
git diff

# Staged changes compared to HEAD
git diff --cached

# Total changes of tracked files compared to HEAD
git diff HEAD
~~~

If a file was both staged and edited further, both git diff and git diff --cached can show output. Checking only one command will not give you the full picture.

### Check the List of Changed Files

~~~bash
git diff --name-status
git diff --cached --name-status
git diff HEAD --name-status
~~~

These commands help identify which files were modified, added, deleted, or renamed in each comparison scope.

If you want to view statistics:

~~~bash
git diff --stat
git diff --cached --stat
git diff HEAD --stat
~~~

Compare the list against the expected recovery scope. If you only meant to restore one file yet see many unrelated files changed, find out why before continuing.

### Comparing a File Against the Desired Version

Suppose you need to confirm that ReportService.java was restored to the exact version from commit 4a5b6c7.

View the file contents in the commit:

~~~bash
git show 4a5b6c7:src/ReportService.java
~~~

Compare the current working tree against the version in that commit:

~~~bash
git diff 4a5b6c7 -- src/ReportService.java
~~~

If the command outputs no differences, the Git-tracked contents of the file in the working tree match the specified commit's snapshot. If differences appear, read the diff to determine whether they are expected changes or a sign of incomplete recovery.

Note: git show <commit>:<path> reads the content stored in the commit. It does not prove the current file on disk was written properly unless you compare it against the working tree.

For a staged file, you can inspect the index version:

~~~bash
git show :src/ReportService.java
~~~

The stage syntax without a number after the colon reads the version in the index. If the file is unmerged, inspect stages 1, 2, and 3 instead of using this syntax.

### Checking Untracked and Ignored Files

Standard git diff does not display the contents of untracked files. Therefore, if the recovery operation involves new files, inspect them separately:

~~~bash
git status --short
git ls-files --others --exclude-standard
~~~

The second command lists untracked files that are not ignored.

To view ignored files:

~~~bash
git status --short --ignored
~~~

Do not mistake an ignored file for a deleted or unrecovered file. If an important file is ignored, verify the ignore rule and its path.

### Checking Unmerged Paths

If the recovery operation introduced conflicts, first identify unresolved files:

~~~bash
git diff --name-only --diff-filter=U
git ls-files -u
~~~

While unmerged entries remain, the recovery operation cannot be considered complete. Edit each file, stage the result, re-read the diff, and continue or abort the active operation properly.

## Verifying History and Branch References

Correct file contents are not enough if the branch points to the wrong commit or history changed unexpectedly.

Inspect the current commit:

~~~bash
git log -1 --oneline --decorate
git show --no-patch --pretty=fuller HEAD
git rev-parse HEAD
~~~

Inspect the recent history graph:

~~~bash
git log --oneline --graph --decorate -n 20
~~~

If you need to view both local and remote-tracking branches:

~~~bash
git branch -avv
~~~

Confirm:

- The current branch name matches the work being recovered.
- HEAD points to the desired commit.
- Commits that need to be preserved are still reachable.
- Any new commit has appropriate content and parents.
- The branch was not moved unintentionally.
- A remote-tracking branch is not mistaken for the latest remote state if you have not fetched yet.

To view the list of parents of a commit:

~~~bash
git rev-list --parents -n 1 HEAD
~~~

A normal commit has one parent; a merge commit has two or more parents. When recovering merge-related history, verify the exact parent count and order.

### Comparing Before and After Recovery

If you know the pre-operation commit and post-operation commit, you can compare snapshots:

~~~bash
git diff <before-commit> <after-commit>
git diff --stat <before-commit> <after-commit>
~~~

This command compares the contents of two snapshots. It does not by itself describe the full commit sequence between them.

To see commits present in the after branch but not in the before branch:

~~~bash
git log --oneline <before-commit>..<after-commit>
~~~

To see commits only on the before side:

~~~bash
git log --oneline <after-commit>..<before-commit>
~~~

The two dots here specify the set of commits reachable from the right side that are not in the left side. Do not confuse this result with git diff A..B, which is a notation for comparing two content trees.

### Confirming a Commit Remains in Branch History

If you need to check whether commit C is an ancestor of HEAD:

~~~bash
git merge-base --is-ancestor C HEAD
~~~

Exit code 0 means C is an ancestor of HEAD; exit code 1 means it is not. Other exit codes may indicate an argument or repository error, so read the error message.

You can list branches containing the commit:

~~~bash
git branch --contains C
git branch -r --contains C
~~~

These commands are useful when restoring lost commits or verifying which branches have integrated a commit.

## Using Reflog to Verify and Trace Previous States

Reflog records updates to local references, such as HEAD switching branches, commits, resets, or rebases. When recovering from a mistaken operation, reflog often helps locate the commit a branch previously pointed to.

Inspect HEAD's reflog:

~~~bash
git reflog --date=iso
~~~

Limit to recent lines:

~~~bash
git reflog -n 20 --date=iso
~~~

Example:

~~~text
a1b2c3d HEAD@{0}: reset: moving to HEAD~2
d4e5f6a HEAD@{1}: commit: Add report validation
1122334 HEAD@{2}: checkout: moving from feature/report to main
~~~

In the example, HEAD@{1} is the state before the reset recorded at HEAD@{0}. You can inspect that commit:

~~~bash
git show --stat --oneline HEAD@{1}
~~~

Reflog is a local log and is not pushed to remotes like commits. Entries can expire over time per configuration; garbage collection can cause objects to no longer be retained. Therefore, once you locate a commit to keep, create an appropriate recovery branch or tag after verifying it.

Example creating a branch referencing the commit to recover:

~~~bash
git branch recovery/report-before-reset d4e5f6a
~~~

The command above creates a new branch pointing to the commit without moving the current branch. Afterward, you can inspect the recovery branch and compare contents before deciding to merge, cherry-pick, or switch branches.

Do not assume HEAD@{1} is always the right commit. Reflog shifts with every new operation; read the message, timestamp, and commit contents before using it.

## Verifying by Type of Recovery Operation

Each recovery command has a different effect. Choose checks suited to the operation you used.

### After git restore

git restore can restore file contents in the working tree or staging area depending on options. Example:

~~~bash
git restore --source=HEAD --worktree -- src/ReportService.java
~~~

The command above only restores the working tree; if the index currently holds staged changes, they are kept. If your goal is to restore both the index and working tree to HEAD, use:

~~~bash
git restore --source=HEAD --staged --worktree -- src/ReportService.java
~~~

Re-verify:

~~~bash
git status --short
git diff HEAD -- src/ReportService.java
git diff --cached -- src/ReportService.java
git show HEAD:src/ReportService.java
~~~

The git diff HEAD command compares total tracked content in the working tree against HEAD's snapshot; git diff --cached shows specifically the staged differences. If the goal is to return both the index and working tree of the file to match HEAD's snapshot, both corresponding diffs will show no differences.

Do not rely solely on repository-wide clean status if the command targeted only a single path. Inspect the exact targeted path.

### After git reset

reset moves HEAD and can modify the index or working tree depending on --soft, --mixed, or --hard.

After reset, inspect:

~~~bash
git rev-parse HEAD
git status
git log --oneline --decorate -n 12
git reflog -n 12
~~~

Compare HEAD against the target commit. With --soft, changes from the rolled-back commits may remain in the staging area. With --mixed, changes typically reside in the unstaged working tree. With --hard, the index and tracked working tree are reset to the target commit, meaning local tracked changes may have been discarded.

A clean repository after reset --hard does not prove you chose the right commit. Always verify the hash, branch, and contents.

### After git revert

revert creates a new commit undoing an older commit. Inspect the new commit and reverted contents:

~~~bash
git log -1 --oneline
git show --stat --oneline HEAD
git diff HEAD^ HEAD
~~~

If reverting a merge commit, the new revert commit is still typically a single-parent commit. The original merge remains in history; verify both ancestor relationships and implications for future merges.

Run tests covering both the removed behavior and any behaviors depending on it. A textually clean reverse patch can still break business workflows.

### After git cherry-pick

cherry-pick creates a new commit on the current branch with changes taken from a selected commit. Inspect:

~~~bash
git log -1 --oneline --decorate
git show --stat --oneline HEAD
git diff HEAD^ HEAD
~~~

Compare the new commit with the source commit:

~~~bash
git show --stat <source-commit>
git show --stat HEAD
~~~

The new commit's hash normally differs from the source commit because its parent, timestamp, and metadata differ. Do not expect the two hashes to match; verify the contents and change message.

If cherry-picking multiple commits or resolving conflicts, inspect commit order and state after each --continue.

### After git stash apply or pop

Inspect the restored changes:

~~~bash
git status
git diff
git diff --cached
git stash list
~~~

apply retains the stash entry. pop removes the entry only when application succeeds; if conflicts occur, the entry remains. Do not drop the stash before thoroughly verifying contents, running tests, and creating a commit or another safe form of storage.

### After git merge --abort or git rebase --abort

Both abort commands cancel an ongoing operation and attempt to return the repository to its state before the corresponding operation began.

Inspect:

~~~bash
git status
git branch --show-current
git rev-parse HEAD
git log --oneline --graph --decorate -n 15
~~~

If there were changes before starting the merge or rebase, confirm they are still preserved in their original state. If autostash was used, inspect the stash list and reapplied changes.

Do not assume abort restored every file exactly as expected if the original working tree contained complex local changes. Read the diff and compare against the pre-operation marker if you recorded one.

## Verifying Test Results After Recovery

Git verifies content and history state. Compilers, linters, and tests verify the rest of the system. Choose checks according to the risk of the recovered change.

### Start with Checks Closest to the Changed Area

Examples:

- Run unit tests for the class or package just recovered.
- Compile the module containing affected files.
- Run a linter or type checker.
- Validate syntax and config loading if YAML, JSON, TOML, or other configuration files were recovered.
- Run integration tests if changes affect APIs, databases, message queues, or inter-service communication.

Use the exact build/test commands defined by the project. Do not assume a Gradle, Maven, npm, or other command applies to every repository.

### Expand Testing Based on Impact Scope

Once narrow checks pass, expand by scope:

| Testing Level | Objective |
|---|---|
| Unit test | Confirm logic of affected classes or functions |
| Integration test | Confirm interactions between components |
| Contract/API test | Confirm requests, responses, schemas, and error codes |
| Full module build | Catch compilation and dependency errors |
| End-to-end or acceptance test | Confirm real user workflows |
| CI | Verify in the environment and configuration used by the team |

There is no need to re-run the entire suite repeatedly if you already have valid results and no new changes occurred. However, if recovery altered dependencies, configuration, schemas, or multiple modules, expand test scope accordingly.

### Verify Both Recovered Behavior and Behavior That Must Remain Unaffected

For example, after recovering a commit that fixed report access permissions, test:

| Case | Expected Outcome |
|---|---|
| Authorized user | Accesses or exports report successfully |
| Unauthorized user | Denied and receives no data |
| Expired token | Returns authentication error per contract |
| Invalid filter | Returns appropriate validation error |
| Report with no data | Returns empty result as specified |

If recovering an older version of configuration or schema, check compatibility with running data and services. A successful build does not guarantee migrations can run safely or existing data is read properly.

### Read Test Results Honestly

When recording outcomes, clearly distinguish:

- Tests that ran and PASSED.
- Tests that ran and FAILED.
- Tests that were skipped or could not run due to environment issues.
- Tests that have not been run yet.

If tests fail, read the logs to determine the cause. Do not mark PASS merely because a build command succeeded if the business test suite has not run.

If possible, compare against results on the base commit or a reference environment to determine whether a failure comes from the recovered change or was pre-existing. Record the exact command, exit code, and affected tests.

## Checking Secrets, Data, and Configuration After Recovery

A recovery operation can bring back older content, including outdated configuration or previously removed sensitive information.

After recovery, inspect:

- Whether tokens, passwords, private keys, or credentials appear in recovered files.
- Whether configuration files point to the right endpoints, databases, or environments.
- Whether default values alter security behavior.
- Whether dependencies and lockfiles remain compatible with manifests.
- Whether migrations or schemas match current data.
- Whether generated files, caches, or local files were accidentally included in commits.

Do not place real secrets in test logs, screenshots, or reports. If you discover a secret was committed or shared, follow your organization's secret exposure response procedure; deleting the file in a new commit does not erase the secret from older history.

## When Git Reports Success Yet the Result Is Still Wrong

There are several common causes:

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| Clean working tree yet application has wrong version | HEAD points to an unintended commit | Check git rev-parse HEAD and git log |
| File restored yet still differs from target version | Picked the wrong source commit or path | Compare with git diff <expected> -- <path> |
| Old commit does not appear on branch | Only restored content without creating required ref or commit | Check reflog and git branch --contains |
| Revert succeeded yet dependent feature breaks | Subsequent commits relied on the reverted content | Inspect history and run integration tests |
| Local tests pass yet CI fails | Different environment, config variables, or dependency cache | Read CI logs and compare configuration |
| Stash still present after pop | Pop hit a conflict | Check git stash list and restored contents |
| Untracked file missing from diff | git diff does not display untracked files | Check git status --short and git ls-files |
| Commit not found in log | Commit is no longer reachable from current branch | Check reflog and other refs |

Do not rush to run additional resets, cleans, or force pushes before understanding the state. Those operations can further reduce recoverability.

## Handling When the Commit to Recover Cannot Be Found

If the commit does not appear in git log of the current branch, check the reflog first:

~~~bash
git reflog --all --date=iso
~~~

If you find the commit hash, verify the object still exists:

~~~bash
git cat-file -e 'd4e5f6a^{commit}'
git show --stat --oneline d4e5f6a
~~~

If confirmed to be the right commit, create a recovery branch to hold the reference:

~~~bash
git branch recovery/restore-lost-work d4e5f6a
~~~

Then inspect contents, history, and tests on the recovery branch before integrating.

If the reflog no longer has a matching entry yet you suspect the commit object still exists, you can check for unreachable objects with:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

This command can print many unreferenced objects. Inspect each object and use git show or git cat-file to determine its type, contents, and relationships. Do not automatically pull every found object into a branch.

Finding an object does not guarantee recovering the entire uncommitted working tree. Changes that were never committed or saved in a stash may lack any recoverable object. Distinguish lost commits from lost uncommitted content.

## Recording Recovery Evidence

Once content, history, and tests are confirmed, save enough information for others to evaluate the outcome.

A recovery report can include:

| Item | Details to Record |
|---|---|
| Incident | Mistaken operation or change needing recovery |
| Method | restore, reset, revert, cherry-pick, stash, or reflog |
| Source marker | Commit or stash used as source |
| Post-recovery state | Branch, HEAD, and working tree status |
| Affected files | List of restored or modified files |
| History | New commits, parents, and related refs |
| Testing | Commands run and PASS/FAIL/BLOCKED status |
| Remaining work | Unrun checks or dependencies to monitor |

You can use the following commands to gather information:

~~~bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline --decorate
git show --stat --oneline HEAD
git diff --check
git diff --cached --check
~~~

If sharing the report, do not include secrets, tokens, credentials, or personal data in it.

## Sample Post-Recovery Verification Workflow

Suppose you just recovered a needed commit after a mistaken reset by creating a branch from the reflog. You can verify in order:

~~~bash
# 1. Confirm repository, branch, and HEAD
git status
git branch --show-current
git rev-parse HEAD

# 2. Confirm the recovered commit and its contents
git show --stat --oneline HEAD
git show --format=fuller --no-patch HEAD

# 3. Inspect the history graph and related references
git log --oneline --graph --decorate -n 20
git branch -avv

# 4. Check changes in the index and working tree
git diff
git diff --cached
git status --short

# 5. Check whitespace and unmerged paths
git diff --check
git diff --cached --check
git diff --name-only --diff-filter=U
git ls-files -u

# 6. Run unit tests, build, and project-appropriate checks
# Record the actual commands and PASS/FAIL/BLOCKED results

# 7. Check final state
git status
git log -1 --oneline --decorate
~~~

If the recovery operation created a new commit, verify the contents of the new commit against its parent. If the operation only restored the working tree, verify files against the source snapshot and decide whether a commit is needed per team workflow.

## Post-Recovery Completion Checklist

- [ ] Identified the right repository, branch, and target commit.
- [ ] Checked the working tree and staging area.
- [ ] Verified the contents of each critical file against the desired version.
- [ ] Checked untracked, ignored, and deleted files if applicable.
- [ ] No unexpected unmerged paths remain.
- [ ] HEAD and commit history accurately reflect the recovery outcome.
- [ ] Commits that must be kept remain reachable.
- [ ] No out-of-scope changes were included in commits.
- [ ] Ran appropriate tests and accurately recorded results.
- [ ] Checked related configuration, dependencies, schemas, and secrets.
- [ ] Confirmed stashes or recovery refs are still retained if needed.
- [ ] Recorded evidence and remaining work.

## Takeaways

After a recovery operation, verify content in the working tree and index, confirm HEAD and branch history, and re-run tests across the affected scope. A clean git status only reflects Git-tracked file state relative to HEAD; it does not prove the target commit is right or the application behaves properly. Use diff to verify content, log and reflog to verify history, tests to confirm behavior, and save evidence before sharing results. The goal is restoring the exact desired state while preserving essential changes and history milestones.

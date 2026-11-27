# Evaluating Merge Results with Diff, Log, and Testing

A successful `git merge` execution only tells you that Git updated the history or working tree according to the selected merge strategy. It does not prove the final result meets requirements. A conflict-free merge can still drop necessary behavior; a merge with conflicts can be syntactically resolved yet choose the wrong logic. After merging, you must inspect the commit graph, compare the resulting snapshot against the input branches, and run tests on the exact merged state.

In the **Branch Merging** chapter of the **SOURCE_CONTROL_GIT** module, this lesson shows how to evaluate a merge using three sources of evidence: diff shows what content changed, log shows which history was connected, and tests verify the behavior of the result. You will learn how to compare a merge commit against each parent, inspect conflict resolutions, distinguish merge commits from fast-forward or squash merges, and establish a verification workflow before sharing results.

After this lesson, you will be able to:

- Record the starting and ending commits of branches before merging.
- Read the history graph and determine which commits were integrated.
- Use `git diff` to compare the result with the target and source branches.
- Read the first parent, second parent, and combined diff of a merge commit.
- Inspect changes introduced by conflict resolution.
- Distinguish merge commits, fast-forwards, and squash merges when evaluating history.
- Check the index, working tree, whitespace, and leftover conflict markers.
- Select appropriate tests and verify on the exact merge result.
- Write a concise report covering content, history, and test results.

## 1. Why Evaluate After Merging?

A merge combines branch histories and produces a new code state. The result can differ from both input branches because the two branches changed independent parts, edited the same code region, or the person resolving conflicts chose one side, combined both sides, or rewrote logic. The merge strategy can also affect how Git produces the result.

Post-merge evaluation needs to answer three questions:

1. **Content:** Does the final result contain the expected changes without carrying unintended out-of-scope edits?
2. **History:** Were the intended commits integrated properly, and are the parent relationships sound?
3. **Behavior:** Do build, test, lint, and relevant checks succeed on the merged result?

No single command answers all three questions. Combine diff, log, status, and tests.

## 2. Recording Baselines Before Merging

To evaluate the result, you need to know the initial state of both the target branch and the source branch. Without recording pre-merge OIDs, branches may have moved and it becomes difficult to isolate which changes belong to the integration you are reviewing.

Suppose you are on the `main` branch and want to merge `origin/feature/payment`.

### Step 1: update remote information

~~~bash
git fetch origin
git status -sb
git branch --show-current
git log -1 --oneline --decorate
~~~

`fetch` updates remote-tracking refs without automatically merging into the current branch. Do not start a merge when the working tree or index has unhandled changes. Commit, stash, or preserve them appropriately.

### Step 2: record the OIDs of both inputs

~~~bash
git rev-parse HEAD
git rev-parse origin/feature/payment
~~~

Call these two values `target-before` (the tip commit of the target branch before the merge) and `source-before` (the tip commit of the source branch at merge time). Save both OIDs in review notes or shell variables for reuse. In the examples below, replace `<target-before>` and `<source-before>` placeholders with the actual recorded OIDs.

### Step 3: inspect history and change scope before merging

~~~bash
git log --graph --oneline --decorate --boundary main...origin/feature/payment
git diff --stat main...origin/feature/payment
git diff --check main...origin/feature/payment
git merge-base main origin/feature/payment
git log --oneline --decorate main..origin/feature/payment
~~~

Triple-dot notation means different things depending on the command:

- With `git log A...B`, Git lists the symmetric difference: commits reachable from only one side.
- With `git diff A...B`, Git compares the merge base of A and B against B. This is typically how you review changes contributed by the source branch since the common ancestor.

Do not read these two expressions as the same calculation. The command `git log main..origin/feature/payment` lists commits reachable from the source branch but not reachable from the target branch at the time it is run.

## 3. Identifying the Merge Result Type

After merging, first determine what kind of history Git created. Not every merge operation creates a merge commit.

### Merge commit

A merge commit typically has at least two parents. The first parent is normally the tip of the checked-out branch; the second parent is the tip of the branch merged in.

~~~text
          A1 --- A2  (feature)
         /          \
Base ---              M  (main)
         \          /
          B1 --- B2
~~~

`M` records that two histories were joined and stores the tree of the merged result.

### Fast-forward

If the tip of the target branch is an ancestor of the source branch, Git can advance the target branch without creating a merge commit:

~~~text
Before:
A --- B  (main)
       \
        C --- D  (feature)

After:
A --- B --- C --- D  (main, feature)
~~~

In this case, `HEAD` after the merge is usually the source tip itself. History has no new commit with two parents.

### Squash merge

`git merge --squash` prepares the source branch's changes in the index and working tree without recording parent links to the source branch in the subsequent commit. When you commit the result, the new commit typically has one parent: the target branch before the merge.

Therefore, the log will not show the original feature commits as ancestors of the target branch, even though the feature's content has been brought in. When evaluating a squash merge, compare trees and contents against the recorded `source-before` tip rather than checking ancestry alone.

## 4. Reading the History Graph After Merging

~~~bash
git log --graph --oneline --decorate --all -20
~~~

Components:

- `--graph` draws branch relationships using characters.
- `--oneline` condenses each commit to one line.
- `--decorate` displays branches, tags, and refs at corresponding commits.
- `--all` includes all local and remote-tracking refs in the traversal scope.

The graph helps you see whether a merge commit connected the branches or the branch simply fast-forwarded. However, the output can be long and the display order is not always intuitive in repositories with many branches.

### Viewing First-Parent History Separately

~~~bash
git log --first-parent --oneline --decorate main
git log --first-parent --oneline <target-before>..HEAD
~~~

First-parent history follows only the first parent of each commit. This is a useful perspective for viewing integrations into `main`, especially when the team uses merge commits.

Because this option only follows the first parent, it omits commits that reside solely on second-parent branches. To view source branch commits, use `git log target-before..source-before` or view the full graph.

### Checking Whether the Source Commit Became an Ancestor

For standard merge commits or fast-forward merges:

~~~bash
git merge-base --is-ancestor <source-before> HEAD
~~~

Exit code `0` means `source-before` is an ancestor of `HEAD`. If the command fails, the merge may not have integrated the source tip, the branch may have changed, or you may be evaluating a squash/rebase workflow that does not preserve original source commit IDs.

Verify the old target branch is still an ancestor:

~~~bash
git merge-base --is-ancestor <target-before> HEAD
~~~

In a normal merge, `target-before` normally remains an ancestor of the result. Do not use ancestry checks as the sole proof for a squash merge: squash preserves content without preserving parent relationships to source commits.

## 5. Identifying the Merge Commit and Parents

If `HEAD` is a merge commit, inspect its OID, tree, and parents:

~~~bash
git show -s --format="commit=%H%ntree=%T%nparents=%P%nsubject=%s" HEAD
git rev-list --parents -n 1 HEAD
git cat-file -p HEAD
~~~

In a normal two-branch merge:

- `HEAD^1` is the first parent, usually the target branch before merging.
- `HEAD^2` is the second parent, usually the source branch before merging.

Do not assume parent order solely from branch names in the commit message. Read the parent OIDs and verify them against the OIDs you recorded:

~~~bash
git rev-parse 'HEAD^1'
git rev-parse 'HEAD^2'
~~~

If the first parent equals `target-before` and the second parent equals `source-before`, the parent structure matches the expected merge. Octopus merges have more than two parents; inspect the full list in `%P`.

If `HEAD` does not have two parents, the result may be a fast-forward, a squash commit, a regular commit, or you may be standing on a different commit. Do not run `HEAD^2` comparisons before confirming the parent count.

## 6. Comparing the Result Against the Pre-Merge Target Branch

This is usually the most important comparison for knowing what the merge added to the target branch.

~~~bash
git diff --stat <target-before> HEAD
git diff --name-status <target-before> HEAD
git diff <target-before> HEAD
~~~

Meaning:

- `--stat` shows change scope by file and line count.
- `--name-status` lists files alongside added, modified, deleted, or renamed status.
- The full diff shows the exact content added or removed.

This comparison answers: between the pre-merge target branch snapshot and the current snapshot, what changed in the repository?

Inspect all files belonging to the merge request, unexpectedly deleted or modified files, configuration, migrations, dependencies, and tests. Confirm that changes from the pre-merge target branch were not lost and that conflict resolution lines preserve the intent of both sides.

If you only inspect `git show HEAD`, you may see the merge commit's changes relative to one default parent without full context. Using explicit baseline OIDs makes the comparison clear and reproducible.

## 7. Comparing the Merge Result Against Each Parent

For a merge commit `M` with two parents, inspect both sides:

~~~bash
git diff --stat 'HEAD^1' HEAD
git diff 'HEAD^1' HEAD

git diff --stat 'HEAD^2' HEAD
git diff 'HEAD^2' HEAD
~~~

Comparing against the first parent shows all changes needed for the pre-merge target branch to become the merged result. This is typically the appropriate diff when reviewing the merge's impact on `main`.

Comparing against the second parent shows how the final result differs from the source branch. It can reveal changes originating from the target branch or conflict resolution decisions made during the merge.

~~~text
First parent (main before merge):      M
Second parent (feature before merge):  F
Merge result:                          R

diff M..R: changes added to main
diff F..R: difference between final result and feature
~~~

If `R` differs from `F`, that does not automatically mean the merge is wrong. `main` may contain changes that needed to be kept, or the conflict resolver may have combined two implementations. Read each hunk and verify against functional requirements.

Fast-forward creates no merge commit, so `HEAD^2` normally does not exist. A squash commit also typically has only one parent. In those two cases, use the recorded `target-before` and `source-before` baselines to compare.

## 8. Using Combined Diff to Inspect a Merge Commit

~~~bash
git show --cc HEAD
git show --combined-all-paths --cc HEAD
~~~

`--cc` requests a combined diff for a merge commit. This display format is useful for focusing on sections that differ from multiple parents, especially regions with unique merged outcomes.

Combined diff formats plus/minus signs and hunk headers differently from a standard unified diff. It does not necessarily list every change of the merge relative to each parent. If you need to review all content, still inspect the diffs against the first parent and second parent separately.

Combined diff also typically shows only files that differ from all parents. Therefore, not seeing a file in `--cc` output does not mean that file is unchanged relative to a specific parent.

### Using --remerge-diff to Inspect Conflict Resolutions

On supported Git versions:

~~~bash
git show --remerge-diff HEAD
~~~

Git reconstructs the automatic merge result from the parents and compares it against the actual tree of the merge commit. This diff highlights manual edits made to resolve conflicts.

This is valuable evidence when reviewing a merge commit, though it only applies to merge commits and the reconstructed result depends on the merge machinery and Git version. Not every difference between parents and the merge result is a conflict fix; it can also be another intentional edit. If an older Git version does not support this option, use per-parent diffs and inspect the commit manually.

## 9. Verifying Conflict Resolution Content

A merge can complete while its conflict resolution still contains broken logic. For example, two branches both edit a condition:

~~~text
main:     if (user.isActive) { allow(); }
feature:  if (user.hasAccess) { allow(); }
~~~

The correct result may require both conditions:

~~~javascript
if (user.isActive && user.hasAccess) {
  allow();
}
~~~

If the conflict resolver kept only one side, the merge can still produce a commit and existing tests may not cover the missing case.

### Checking That No Unmerged Entries Remain in the Index

~~~bash
git ls-files -u
~~~

After a merge completes, this command normally prints no entries. If output remains, the index still contains unresolved stages; the merge was not concluded properly.

### Checking Repository Status

~~~bash
git status
git status --porcelain=v1
~~~

With a completed merge commit, status normally no longer reports an ongoing merge or unmerged files. The working tree may still contain new post-merge changes created by the user; distinguish those from the commit's contents.

### Searching for Leftover Conflict Markers

You can search for common markers in text files:

~~~bash
git grep -n -E '^(<<<<<<<|=======|>>>>>>>)'
~~~

This is a helpful scan, not absolute proof. A line like `=======` can be valid content in documentation or other files; matches must be opened and verified manually. Certain conflicts in binaries, config files, or data structures cannot be detected by searching for markers.

### Reading the Diff of Previously Conflicted Files

~~~bash
git diff 'HEAD^1' HEAD -- src/config.js
git diff 'HEAD^2' HEAD -- src/config.js
~~~

Inspect the final content, cross-check both parents, and confirm the merge decision preserves requirements from both sides.

## 10. Checking Whitespace and Formatting Issues

~~~bash
git diff --check <target-before> HEAD
git diff --check
~~~

The first command checks whitespace in the merge changes relative to `target-before`. The second checks unstaged changes between the working tree and the index within `git diff --check`'s default scope.

Common issues include trailing whitespace at end of line, unintended newlines or formatting shifts, line endings converted globally, and broken indentation or config delimiters.

`git diff --check` does not catch logic bugs, syntax errors across all languages, or conflict markers in every file type. It is just one small step in the workflow. If the repository has formatting or lint rules, run the exact project-required commands on the merge result.

## 11. Evaluating When the Merge Is a Fast-Forward

Fast-forward does not create a merge commit, so there is no second parent to inspect. Use the pre-merge baselines instead:

~~~bash
git diff --stat <target-before> HEAD
git diff --name-status <target-before> HEAD
git diff <target-before> HEAD
git log --oneline --decorate <target-before>..HEAD
~~~

If `source-before` was the source branch tip at merge time:

~~~bash
git merge-base --is-ancestor <source-before> HEAD
~~~

A successful exit confirms the source tip is now in the current history. If `HEAD` equals `source-before`, this is a classic fast-forward.

Check the current branch and tip commit:

~~~bash
git status -sb
git log -1 --oneline --decorate
~~~

Do not conclude no merge happened merely because you see no merge commit. Fast-forward is a valid type of merge; history was updated by moving the ref.

## 12. Evaluating When Using Squash Merge

With squash, Git does not record the source commits as parents of the new commit. Consequently:

- The new commit usually has one parent: `target-before`.
- `source-before` may not be an ancestor of `HEAD`.
- `git log target-before..HEAD` typically shows only the new squash commit.
- Content can still include all intended changes from the source branch.

Verify:

~~~bash
git show --stat --oneline HEAD
git diff <target-before> HEAD
git diff <source-before> HEAD
~~~

Comparing `target-before` with `HEAD` shows what changes were added to the target branch. Comparing `source-before` with `HEAD` shows how the final result differs from the source branch snapshot.

With squash, not seeing source commits in the log does not necessarily mean changes are missing. Evaluate both the tree and contents, not just parent relationships.

## 13. Evaluating History with Log and Commit Ranges

Diff shows how snapshots differ; log shows which commits and messages entered history.

~~~bash
git log --oneline --decorate <target-before>..HEAD
git log --graph --oneline --decorate --all -20
git log --first-parent --oneline <target-before>..HEAD
git log --format=fuller -5 HEAD
~~~

Cross-check the expected feature commits, commit messages, unrelated commits, commits missed because the source branch wasn't fetched or the wrong base was selected, and the merge commit's parents.

If the source branch still exists:

~~~bash
git log --left-right --cherry-pick --oneline main...origin/feature/payment
~~~

The `<` and `>` markers indicate which side each commit belongs to. `--cherry-pick` omits certain patch-equivalent commit pairs within the comparison range, which is helpful when history involves cherry-picks or rebases. This command helps detect history differences, though it does not prove code works correctly.

## 14. Tests Must Run on the Merge Result

After merging, code must be tested on the exact snapshot you intend to share. If tests only ran on the source branch before merging, they did not test changes coming from the target branch or conflict resolutions.

| Layer | Purpose | Example checks |
| --- | --- | --- |
| Unit test | Verify individual functions or modules | Calculation rules, validation, edge cases |
| Integration test | Verify integrated components | API with database, service with queue |
| Regression test | Ensure existing behavior is not broken | Previously fixed bugs, critical flows |
| Lint/static analysis | Catch formatting errors and code issues | Linter, type checker, static analyzer |
| Build/package | Verify the project produces artifacts | Compile, bundle, package |
| End-to-end/manual | Check user or system flows | Login, payment, test deployment |

Not every project has all of these layers. Choose the test suite according to risk and the repository's CI requirements.

### Run Focused Tests First

If the merge changed a parser, start with parser tests and boundary-input tests. If schema or migrations changed, test upgrading from data states supported by the project.

### Run All Required Checks

After focused tests, run the full test suite, lint, type checks, and build according to project documentation. Do not guess commands from another stack; use the repository's official scripts or CI jobs.

### Record the Exact Tested Commit

~~~bash
git rev-parse HEAD
git status --short
~~~

Record the OID in the test report. If `HEAD` changes after testing, prior results do not prove the new commit was tested.

## 15. When Tests Fail After Merging

A failing test after merging is not enough to conclude the merge itself caused the bug. Narrow down the change scope and determine where the failure comes from.

~~~bash
git log -1 --oneline --decorate
git status -sb
git diff <target-before> HEAD -- path/to/affected-file
git log --oneline -- path/to/affected-file
~~~

For a merge commit, compare the file against each parent:

~~~bash
git diff 'HEAD^1' HEAD -- path/to/affected-file
git diff 'HEAD^2' HEAD -- path/to/affected-file
~~~

If a line differs only from the source parent, it may come from conflict resolution or a change on the target branch. Read the logic and tests to determine the true intent. Also verify test data, environment variables, dependencies, and supporting services; failures can stem from environment issues or flaky tests.

If the merge result was already committed, create a follow-up fix commit or follow your team's bug-fix workflow. Do not directly rewrite an already-shared merge commit without team agreement.

## 16. Final Status Check Before Sharing

~~~bash
git status -sb
git status --porcelain=v1
git ls-files -u
git diff --check
git log --graph --oneline --decorate -12
git show --stat --oneline HEAD
git rev-parse HEAD
~~~

Expected:

- No merge still in progress.
- No unmerged index entries remaining.
- No unexpected local modifications.
- No whitespace errors in the checked diff.
- The recorded OID matches the commit on which tests ran.

If the working tree has changes created after the merge, do not lump them into the merge result report. Commit or store them separately per team workflow, then re-run necessary checks.

## 17. Complete Merge Evaluation Workflow

Suppose the `main` branch needs to merge `feature/payment`. You want to verify changes, history, and tests before pushing.

### Before merging

~~~bash
git fetch origin
git switch main
git status -sb
git rev-parse HEAD
git rev-parse origin/feature/payment
git merge-base main origin/feature/payment
git log --graph --oneline --decorate main...origin/feature/payment
git diff --stat main...origin/feature/payment
~~~

Record the `target-before` and `source-before` OIDs. Review diffs and source commits, confirming the exact scope.

### Performing the merge

~~~bash
git merge --no-ff --no-edit origin/feature/payment
~~~

This example requests creating a merge commit if the merge can complete; depending on team policy, you may use fast-forward or squash instead. The merge command is only the integration step, not the final verification.

### After merging

~~~bash
git status -sb
git rev-list --parents -n 1 HEAD
git log --graph --oneline --decorate --all -20
git diff --stat <target-before> HEAD
git diff <target-before> HEAD
git diff 'HEAD^1' HEAD
git diff 'HEAD^2' HEAD
git show --cc HEAD
git show --remerge-diff HEAD
~~~

Only run parent comparison commands when `HEAD` is a merge commit with those parents. If your Git version does not support `--remerge-diff`, skip that option and review diffs against each parent.

### Checks and testing

~~~bash
git ls-files -u
git diff --check <target-before> HEAD
~~~

Next, run focused tests, full test suite, lint, build, and integration checks per project requirements. Record the tested OID along with the results.

### Report

A review-friendly merge report should list the source and target branches, `target-before`/`source-before`/merge result OIDs, result type, key files and changes, resolved conflicts, test/lint/build commands run with their outcomes, and any untested limitations.

## 18. Common Misconceptions

### A successful merge means the code is right?

No. Git only confirms the merge operation completed according to its rules. You still have to review diffs and run tests.

### `git show HEAD` always shows all changes from both branches?

Not necessarily. For a merge commit, default `git show` may not display diffs the way you expect. Use `git diff` against each parent and `git show --cc` to view different perspectives.

### `HEAD^1` is always `main` and `HEAD^2` is always `feature`?

No. The first parent is normally the checked-out branch, but you should verify parent OIDs against the baselines recorded before merging.

### No merge commit means the merge failed?

No. Fast-forward updates the ref without creating a merge commit. Squash merge creates a regular commit containing the result without recording source branch parents.

### `git log A...B` and `git diff A...B` have the same meaning?

No. `git log` uses symmetric difference of reachable commits; `git diff` uses the merge base of A and B to compare snapshots. Choose the command based on your question.

### `git diff --check` replaces testing?

No. It detects certain whitespace errors in diffs; it does not check logic, build, or runtime behavior.

### No remaining conflict markers means conflicts were resolved correctly?

No. Markers may have been deleted while logic remains wrong. Compare against both parents and test the relevant cases.

### Squash merge must make the source branch an ancestor?

No. Squash does not preserve parent relationships to source commits. Evaluate using tree contents and diffs, not ancestry alone.

## 19. Self-Check

You merge `feature/search` into `main` and Git creates merge commit `M`. Before merging, you recorded `main`'s OID as `T` and `feature/search`'s OID as `S`. After merging, `HEAD` is `M`.

Answer the following:

1. Which command views the history graph after the merge?
2. Which command identifies the parents of `M`?
3. Which comparison shows the impact of the merge on `main`?
4. Which comparison shows how the final result differs from `feature/search`?
5. Why should you inspect `git show --cc` and `--remerge-diff` when the merge had conflicts?
6. Which command confirms `S` has become an ancestor of `M` in a standard merge?
7. Why must tests run on `M` instead of only on `S`?
8. If the merge was a squash, why might the ancestry check for `S` fail even though its content was integrated?

**Hint:** Use `git log --graph --oneline --decorate --all` to view the graph; `git rev-list --parents -n 1 M` to view parents. Use `git diff T M` to see changes relative to pre-merge `main`, and `git diff S M` to see differences relative to `feature`. Combined/remerge diff helps inspect merge results and conflict edits. Use `git merge-base --is-ancestor S M` for topology-preserving merges. Test on `M` because that is the actual tree containing both sides and conflict resolutions. Squash only records one parent, so it does not store source commit `S` in ancestry.

## Conclusion

Evaluating a merge requires combining diff, log, and testing. Record the target and source branch OIDs before merging, identify the post-merge result type, inspect the graph and parents, and compare the final snapshot against each input. For a merge commit, diffing against the first parent shows the impact on the target branch; diffing against the second parent reveals how the result differs from the source branch; combined diff and remerge diff aid in reviewing conflict resolutions. For fast-forward or squash, use pre-merge baseline OIDs instead of assuming two parents always exist. Finally, confirm the index and working tree are clean with no unmerged entries, run tests on the exact merge result, and record the verified OID before sharing.

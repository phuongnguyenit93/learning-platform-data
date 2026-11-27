# Locating a Bug-Introducing Commit with `git bisect`

When a bug appears in a project, we often know an earlier version worked and the current version is broken, yet we do not know which commit introduced the bug into the codebase. Manually reading hundreds of commits to find the cause can take a long time. `git bisect` solves this by performing a binary search over commit history: Git repeatedly selects a commit in the middle of the range, you test whether that commit is still good or already bad, and the range narrows until the first commit causing the issue is identified.

In Git source code management, `git bisect` is a key tool for tracing changes and performing evidence-based recovery. It helps isolate the root cause before deciding to fix the code, revert a commit, or issue a patch. Results are most valuable when you have a clear test criterion and can reliably classify a commit as `good` or `bad`.

## 1. The Idea of Binary Search in Git History

Suppose the application ran fine at commit `A`, but a bug has appeared by commit `H`. Between the two commits there are many changes:

```text
A --- B --- C --- D --- E --- F --- G --- H
good                                      bad
```

Instead of checking every commit from `A` to `H`, Git picks a commit in the middle of the range, such as `E`. If `E` is still good, the bug-introducing commit lies after `E`; if `E` is already bad, the bug-introducing commit lies in the portion from `A` to `E`. With each check, the candidate range shrinks by roughly half.

```text
Step 1: A --- B --- C --- D --- E --- F --- G --- H
                              ^ check E

If E is good:                   E --- F --- G --- H
                                      ^ check midpoint of remaining range

If E is bad:  A --- B --- C --- D --- E
                  ^ continue searching in first half
```

For a linear history with N candidate commits, binary search typically requires around log base 2 of N checks instead of up to N checks. For example, a range of 128 commits usually takes only about 7 checks to find the boundary. Actual counts may vary due to DAG structure, skipped commits, or inconsistent test results.

`git bisect` does not inherently understand what a bug is. The operator must supply two reliable markers:

- **Good:** a commit where the test criterion confirms the bug has not appeared yet.
- **Bad:** a commit where the test criterion confirms the bug is already present.

Git uses ancestor relationships between commits to narrow the search area. The result is usually the first commit along the inspected history path where the state transitions from good to bad.

## 2. Preparing Before Running Bisect

First, define the bug symptom and a repeatable way to test it. For example:

- An API returns HTTP 500 instead of HTTP 200.
- A unit test that previously passed now fails.
- A build command fails after a recent change.
- A UI interaction no longer works in the new version.

The criterion must be specific enough that the same commit always produces a consistent result. If the bug only occurs intermittently or depends on external data or environment state, stabilize the test conditions before bisecting.

Inspect the repository and save uncommitted work:

```bash
git status -sb
git log --oneline --decorate -10
```

`git bisect` moves `HEAD` across many commits, typically placing the repository into a detached HEAD state. Therefore, you should have a clean working tree. Commit or stash work in progress before starting; back up important untracked files separately if a default stash does not include them.

Identify the two markers:

```bash
git log --oneline --decorate --all
```

Pick an older commit confirmed to be good and a newer commit confirmed to be bad. You can use a commit hash, branch name, tag, or revision expression. For example:

```text
v2.3.0       version that still works
HEAD         current version with the bug
```

If you need to check whether the good marker is an ancestor of the bad marker:

```bash
git merge-base --is-ancestor v2.3.0 HEAD
```

The command returns exit code 0 when `v2.3.0` is an ancestor of `HEAD`. In a standard bisect workflow, the good marker should lie on the history line leading to the bad marker so the search range is clearly defined.

## 3. Running `git bisect` Manually

The basic workflow has three phases: starting, evaluating the selected commit, and ending.

### Step 1: Start the Bisect Session

```bash
git bisect start
```

This command initializes the bisect session. Next, mark the current commit as bad and an older commit as good:

```bash
git bisect bad HEAD
git bisect good v2.3.0
```

You can pass both markers immediately when starting:

```bash
git bisect start HEAD v2.3.0
```

In this syntax, the first commit is the bad marker and the second commit is the good marker. Use the separate commands if you want to record each marker individually or double-check before starting the search.

### Step 2: Test the Commit Git Selects

After receiving both markers, Git checks out a commit in the middle of the range. Its output usually indicates how many candidate commits remain and the current commit hash.

Inspect the state:

```bash
git status -sb
git log -1 --oneline --decorate
```

Run the exact reproduction procedure. If the bug has not appeared, mark it good:

```bash
git bisect good
```

If the bug appears, mark it bad:

```bash
git bisect bad
```

Git continues checking out another commit within the narrowed range. Repeat testing and marking until Git identifies the first bad commit.

### Step 3: Read the Result

When the boundary is found, Git displays a message similar to:

```text
<commit-id> is the first bad commit
```

This output identifies the first commit that the bisect process found to have bad status, within the given range and according to the evaluations provided. Inspect the commit details:

```bash
git show --stat <commit-id>
git show <commit-id>
```

Read the commit message, file list, and diff to understand which change may have caused the bug. If the commit contains many unrelated changes, analyze the diff further, run tests, or use other tracing tools to pinpoint the exact lines of code.

### Step 4: End the Bisect Session

```bash
git bisect reset
```

This command ends the bisect session and returns `HEAD` to its position before the session began, usually the branch and commit you were originally on. Then verify:

```bash
git status -sb
git branch --show-current
```

You should run `git bisect reset` after recording the offending commit hash and necessary details. There is no need to leave the repository in detached HEAD once the search is complete.

## 4. Complete Example: Finding a Regression in an Application

Suppose the team receives a report that the login feature returns an error when users enter a valid password. The team confirms:

- Tag `v1.8.0` still logs in normally.
- Current `HEAD` reproduces the bug.
- Running `./gradlew test --tests LoginServiceTest` can verify it.

Workflow:

```bash
# Start bisect and specify both markers
git bisect start
git bisect bad HEAD
git bisect good v1.8.0

# Git checks out a commit in the middle of the range
# Run the test at the current commit
./gradlew test --tests LoginServiceTest

# If the test passes:
git bisect good

# If the test fails due to the exact regression being investigated:
git bisect bad

# Repeat testing and marking until Git finds the first broken commit

# Inspect the resulting commit and end the session
git show --stat <first-bad-commit>
git bisect reset
```

In practice, never run both `good` and `bad` for the same test run. Choose exactly one outcome based on the defined criterion. If the test fails due to an unrelated build or environment issue rather than the regression, do not mark it bad; use `git bisect skip` as covered in the next section.

## 5. Skipping Commits That Cannot Be Evaluated with `git bisect skip`

Not every commit can be built or run in the current environment. An intermediate commit might:

- Lack configuration files or dependencies added only in a later commit.
- Have a build error independent of the bug under investigation.
- Only run with a JDK, compiler, or service version that is no longer available.
- Be unable to reproduce the bug due to missing test data.

If you cannot conclude whether a commit is good or bad, use:

```bash
git bisect skip
```

Git skips the current commit and selects another commit. You can specify multiple commits or a revision range to skip:

```bash
git bisect skip <commit-a> <commit-b>
git bisect skip <good-base>..<bad-tip>
```

Check the range before skipping a large span. The more commits skipped, the less precise the result may be.

If skipped commits lie near the good/bad boundary, Git may only identify a set of candidate commits as potentially the first bad one instead of a single commit. The result message will list the range or candidate commits. When that happens, manually inspect the remaining commits or fix the environment to re-evaluate.

Do not use `skip` merely because a test failure is confusing. First verify whether the test is actually measuring the target bug; if the commit introduced the regression, it still needs to be marked bad even if secondary errors exist.

## 6. Automating with `git bisect run`

If you already have a test script that returns consistent exit codes, you can let Git run the test automatically at each commit:

```bash
git bisect start HEAD v1.8.0
git bisect run ./scripts/check-login-regression.sh
```

Git checks out each candidate commit, runs the script, and determines the state based on its exit code:

| Script Exit Code | How Git Interprets It |
| --- | --- |
| `0` | Good: test confirms the bug has not appeared |
| `1` to `127`, except `125` | Bad: test confirms the bug is present |
| `125` | Skip: cannot test this commit |
| `128` or higher | Aborts bisect run because the script or command encountered a fatal error |

### Example Check Script

On Linux/macOS or an environment with a POSIX shell, you can create a script:

```sh
#!/bin/sh

if [ ! -x ./gradlew ]; then
    # Wrapper does not exist or is not executable at this commit.
    exit 125
fi

./gradlew test --tests LoginServiceTest
result=$?

if [ "$result" -eq 0 ]; then
    exit 0
fi

# If the test could not run due to environment/missing dependency,
# distinguish that case from an actual regression.
if [ "$result" -eq 125 ]; then
    exit 125
fi

# Other test failures are considered bad per the check's criterion.
exit 1
```

The script above is only appropriate if every non-zero test failure represents the regression being hunted. If the build fails because a dependency is unavailable or an older commit does not support the test command, the script should detect that case and return `125` to skip. Do not mechanically treat every build failure as bad.

Set executable permissions if required by the environment:

```bash
chmod +x scripts/check-login-regression.sh
```

Then run `git bisect run`. When finished, Git prints the first bad commit and exits the automated loop; you should still review the result, inspect the diff, and run an independent verification. Finally:

```bash
git bisect reset
```

### Requirements for Automated Scripts

- Output must accurately reflect the agreed good/bad criterion.
- The script must be repeatable across every candidate commit.
- It must not depend on leftover state from a previous run.
- It must not overwrite user data or files outside the test scope.
- It must distinguish real test failures from environment or build errors that cannot be evaluated.
- It must return `125` when no conclusion can be reached for the current commit.

The script must be accessible at every commit Git may check out. If the script was only added in a newer commit, Git will not find that path when bisect checks out an older commit. You can place the script outside the working tree or ensure it exists across the entire history range being inspected. The script may also generate build files, caches, or logs; these files must not alter test outcomes on subsequent commits. If needed, safely clean generated files inside the script, or run in a dedicated environment/build directory.

## 7. Tracking and Saving a Bisect Session

Git provides commands to observe and record decisions during a bisect session:

```bash
git bisect log
git bisect visualize
git bisect terms
```

- `git bisect log` displays the commands and good/bad/skip decisions recorded in the session.
- `git bisect visualize` opens a history viewer for commits remaining in the search range; `git bisect view` is an equivalent alias.
- `git bisect terms` shows the terms currently used for the two old/new states (defaults to good/bad).

You can save the log to reproduce or share with teammates:

```bash
git bisect log > ../bisect-session.log
```

If running the command from the repository root, the path `../bisect-session.log` places the log file outside the working tree so an untracked file will not interfere with Git checking out candidate commits. If running from another directory, use an absolute path outside the repository.

After ending the session, if you need to replay the decisions in another bisect session, start bisect and replay the log:

```bash
git bisect start
git bisect replay ../bisect-session.log
```

The log stores the markers and decisions made. If repository history changes or refs no longer exist, replay may not reconstruct the entire session. Keep the log file along with repository version and test environment details when filing a bug report.

## 8. Using Different Terms Instead of Good/Bad

In some situations, the terms good/bad can be confusing. For example, when locating the first commit that added a feature, you may want to use `old` and `new` instead of good/bad:

```bash
git bisect start --term-old=old --term-new=new
git bisect new HEAD
git bisect old v1.8.0
```

`old` represents the state before the target change existed; `new` represents the state after the change appeared. You can pick even clearer names:

```bash
git bisect start --term-old=without-feature --term-new=with-feature
```

Then use the corresponding keywords when marking commits. Keep your terminology aligned with your search objective; avoid generic `good`/`bad` labels when investigating the introduction of a feature or an intentional behavior change.

## 9. Bisecting on History with Merge Commits

Git history is usually a DAG rather than a straight line. A feature branch may be merged into `main`, giving the search space multiple paths. Git bisect still works over ancestor relationships, but a selected commit might lie on a side branch or be a merge commit.

If you want to test only commits along the first-parent chain of the main branch, start with:

```bash
git bisect start --first-parent HEAD v2.3.0
```

`--first-parent` restricts the search to the first-parent sequence. This is useful when you want to find which integration introduced a bug into the main branch, such as a pull request merge commit. It may not pinpoint the exact commit inside the feature branch that created the bug; if you need to drill down inside the side branch, bisect that branch's history range separately.

When the offending commit turns out to be a merge commit, inspect its parents and integrated changes:

```bash
git show --no-patch --pretty=raw <merge-commit>
git show --stat <merge-commit>
git diff <merge-commit>^1 <merge-commit>
```

The first parent is typically the branch that received the merge in standard workflows, though this should be confirmed from actual history. Comparing the merge commit against its first parent shows the changes brought into the main branch by that integration.

## 10. Limitations and Causes of Misleading Results

### Unstable Test Criterion

If the same commit sometimes passes and sometimes fails, Git can receive inconsistent good/bad labels and produce wrong results. Stabilize data, timing, external services, configuration, and execution environment before bisecting.

### Regression Appears and Disappears

Binary search assumes a sufficiently clear boundary between the good and bad regions in the chosen range. If one commit adds a bug and a later commit fixes it, the state can go good -> bad -> good. In that case, there is no simple boundary for bisect to pinpoint in the usual way. Narrow the range, determine when the bug appeared and vanished, or use a more specific test criterion.

### Intermediate Commits Fail to Build

A commit may be incompatible with the current compiler, dependencies, or build layout. Classify such commits as skip if they cannot be evaluated. If too many commits are skipped, restore the historical environment or craft a more compatible test.

### Environment-Dependent Failures

Failures caused by operating system differences, environment variables, external services, test data, or permissions can keep results from reflecting commit contents. Pin these factors before running.

### Wrong Good/Bad Markers Selected

If a commit marked good was already broken or a bad commit still worked, Git will search for a boundary based on false premises. When in doubt, re-check both markers and run the test directly before starting.

## 11. After Finding the Bug-Introducing Commit

`git bisect` locates the change; the next step is understanding why that change caused the bug and choosing the right fix.

### Inspect Commit Contents and Context

```bash
git show --format=fuller --stat <first-bad-commit>
git show <first-bad-commit>
git log --oneline --decorate --ancestry-path <good-commit>..<first-bad-commit>
```

Check the author, timestamp, message, changed files, and preceding commits along the history path. Read the code surrounding the change to identify the true root cause.

### Choose How to Fix

- If the change is wrong and does not need to be kept, create a fix commit or revert the offending commit per team workflow.
- If the change is valid but misses an edge case, add tests and fix the logic.
- If the bug only appears when multiple commits interact, inspect interactions across changes rather than looking at a single line of code.
- If the bug affects a release branch, determine how to backport the fix and verify on that exact version.

Do not revert immediately just because bisect pointed to a commit. That commit might be a valid change that exposed a latent bug in another component. Analyze the diff and reproduce the issue before deciding to fix or revert.

## 12. Commonly Used Commands

| Command | Purpose |
| --- | --- |
| `git bisect start` | Start a search session |
| `git bisect bad <rev>` | Mark a commit as broken |
| `git bisect good <rev>` | Mark a commit as working |
| `git bisect skip [<rev>...]` | Skip commits that cannot be evaluated |
| `git bisect run <cmd>` | Automatically run a test command on each commit |
| `git bisect log` | View decisions recorded in the session |
| `git bisect replay <file>` | Replay decisions from a log file |
| `git bisect visualize` | View commits remaining in the range |
| `git bisect terms` | View status terms currently in use |
| `git bisect reset` | End the session and return to the pre-bisect position |

## 13. Bisect Execution Checklist

Before starting:

1. Describe the bug with a repeatable test criterion.
2. Confirm one reliable good commit and one reliable bad commit.
3. Ensure the good marker lies in the history leading to the bad marker.
4. Commit or stash unfinished work and check the working tree.
5. Prepare an environment capable of building/testing historical commits.

During the search:

1. Verify you are testing the exact commit Git checked out.
2. Run the same test or scenario on each iteration.
3. Mark good or bad strictly based on the defined result.
4. Use skip only when no conclusion can be made.
5. Record logs and environment info if results need to be shared.

After finding the commit:

1. Record the commit hash and message.
2. Read the diff and inspect related changes.
3. Reproduce the bug and verify the root cause.
4. Choose the appropriate fix, revert, or backport.
5. Run `git bisect reset` and re-check repository status.

## 14. Practice

Create a test repository with an intentional commit sequence:

1. Create an initial commit adding a small program and confirm it runs correctly.
2. Create several additional commits with various edits.
3. In a middle commit, intentionally introduce an automatically testable bug, such as changing a condition so a test fails.
4. Create a few more commits afterward without fixing the bug.
5. Confirm the first commit in the chain is good and the last commit is bad.
6. Run `git bisect start`, mark the two boundaries, and test each commit Git selects.
7. Confirm Git pinpoints the commit where the bug was intentionally introduced.
8. Finish with `git bisect reset`.
9. Repeat the exercise using a script and `git bisect run`.
10. Create an unbuildable intermediate commit and practice skipping it to observe the impact on result precision.

## 15. Self-Check Questions

1. What principle does `git bisect` use to narrow down the number of commits to test?
2. Why must you have at least one reliable good marker and one reliable bad marker?
3. What state does Git check out during bisect, and why do you typically see detached HEAD?
4. When should `git bisect skip` be used?
5. How does `git bisect run` interpret exit codes `0`, `125`, and other exit codes?
6. Why can an unstable test produce wrong bisect results?
7. In what scenario is `--first-parent` useful, and what are its limitations?
8. After finding the first bad commit, what information should you inspect before reverting?
9. What do `git bisect log` and `git bisect replay` help with?
10. Why must you run `git bisect reset` after completing the search?

## Conclusion

`git bisect` uses binary search to pinpoint the first commit that changed state from good to bad within a history range. Start with two verified markers, run the same test criterion on each commit, and use `skip` when a commit cannot be evaluated. For automatable tests, `git bisect run` reduces manual effort; for history with merges, `--first-parent` helps focus on integration events. After locating the commit, read the diff, verify the cause, and end the session with `git bisect reset` before fixing or restoring the codebase.

# Automating Bisect with a Test Command and Handling Untestable Commits

When a bug appears in a project with many commits, reading through the entire history one by one can take a long time. Git provides the **git bisect** command to locate the first commit that changed state from good to bad using binary search. If you have a reliable test command, you can use **git bisect run** to test each commit automatically without manually marking good or bad.

In practice, not every historical commit builds or runs in the current environment. A commit might lack dependencies, lack an appropriate test, depend on an old runtime version, or fail to start a service. It is important to distinguish a commit that actually introduced the bug from one that cannot be tested. Git supports marking untestable commits with exit code 125 or the git bisect skip command.

## 1. What Problem Does git bisect Solve?

Suppose a feature worked properly at commit A, yet a bug has appeared by commit Z. Between A and Z there are hundreds of commits. Checking each commit sequentially could require a huge number of trials.

git bisect uses a binary search over the commit range:

1. Pick a commit known to be good.
2. Pick a commit known to be bad.
3. Git selects a commit in the middle of the range to test.
4. If the middle commit is good, the search range shifts to the second half.
5. If the middle commit is bad, the search range shifts to the first half.
6. Repeat until the first commit that transitions state from good to bad is found.

~~~text
A---B---C---D---E---F---G---H
good                       bad

Step 1:            D
Step 2:       B or F (depending on Step 1 result)
Next steps:   continue halving the remaining range
~~~

With linear history and consistent test results, the number of checks is typically close to log2(N), where N is the number of commits in the search range. For example, a range of 1,024 commits usually needs only about 10 checks to narrow down the range.

git bisect does not inherently understand application bugs. The user must supply two milestones with known states and a criterion to determine whether the current commit is good or bad.

## 2. Conditions for Meaningful Bisect Results

Before running automation, verify several assumptions:

- **Reliable good marker:** You have confirmed the bug did not exist at that commit.
- **Reliable bad marker:** You have confirmed the bug exists at that commit.
- **Clear test criterion:** You can determine whether the outcome is broken or working using a concrete check.
- **Reproducible bug:** The same commit under the same conditions must yield a consistent result.
- **Valid history relationship:** The commit range between the two markers must contain the development path leading to the bug under investigation.

Binary search assumes the state can be partitioned along a single good-then-bad boundary within the inspected history. If the bug appears, disappears, and reappears, or depends on external data outside the repository, the result may not reflect a single clean boundary.

If there are multiple independent regressions, complex merge branches, or flaky tests, narrow the range, select the proper history line, or investigate individual changes separately.

## 3. Preparing Before Running Bisect

### 3.1. Inspect the Repository

Ensure you are in the right repository and understand its current state:

~~~
git rev-parse --show-toplevel
git status -sb
git log --oneline --decorate -15
~~~

Start with a clean working tree. git bisect checks out historical commits, usually placing HEAD in a detached HEAD state during the investigation. Uncommitted changes can block switching commits or cause you to misinterpret results.

If you have work in progress, commit or stash it after reviewing its contents:

~~~
git stash push -m "WIP before bisect"
git stash list
~~~

Do not use git reset --hard or git clean just to clean the repository without confirming whether those changes need to be kept.

### 3.2. Identify Good and Bad Commits

For example, the current version on main is broken, while an older version was confirmed to work:

~~~
git log --oneline --decorate --all
git show --no-patch --oneline <known-good-commit>
git show --no-patch --oneline <known-bad-commit>
~~~

Record the two specific commit hashes rather than relying solely on branch names that may continue moving. Once you select the markers:

- The good commit must genuinely be free of the bug under investigation.
- The bad commit must genuinely exhibit that bug.
- Both markers must belong to the same history lineage capable of isolating the offending change.

If you do not yet know a good or bad commit, locate reproducible markers before running bisect. Picking either marker incorrectly invalidates the search from the start.

### 3.3. Design the Test Command

The test command should:

- Focus specifically on the bug being hunted, avoiding running the entire test suite unnecessarily.
- Produce a clear and deterministic result.
- Run across as many historical commits as possible.
- Require no manual steps or user interaction.
- Avoid depending on unstable external services if fixtures or an isolated test environment can be used instead.
- Return exit codes following the contract understood by git bisect run.

For example, instead of generically checking "the application starts", use a test that reproduces the exact bug such as "search is case-insensitive" or "order total must include shipping fee".

## 4. Exit Code Contract of git bisect run

git bisect run invokes the command you provide at each commit Git selects. The command's exit code determines how Git classifies that commit.

| Exit Code | Meaning to git bisect run | Usage |
|---|---|---|
| 0 | Good | Test passed, bug has not appeared |
| 1 to 127, except 125 | Bad | Test confirmed the bug is present |
| 125 | Skip | Cannot reliably test this commit |
| Greater than 127 | Abort | Stops the bisect process due to execution error or abnormal signal |

Code 125 is a special value. It does not mean the commit is good or bad; it means no conclusion can be drawn at the current commit and Git should skip it and continue searching.

Any code other than 0 within 1 to 127, except 125, is treated as bad. Therefore, if a test command returns 2 due to missing configuration or 127 because a program was not found, Git may classify the commit as bad even though the real issue is just the test environment. That is why you need a test wrapper to normalize outcomes.

Exit codes greater than 127 cause bisect run to stop. For instance, a process terminated by a signal can yield an exit code in this group. When the run aborts abnormally, read the logs and fix the cause before continuing.

## 5. Writing a Wrapper to Distinguish Software Bugs from Environment Errors

A standard test runner may return a non-zero exit code for many reasons:

- Assertion failure: the tested behavior regressed.
- Failure to compile because the commit itself broke the source code: may be bad if that matches the investigation criterion.
- Missing JDK, SDK, or dependency: cannot yet conclude whether the commit has the bug.
- Test service fails to start: environment is not ready.
- Test does not exist in older commits: that commit cannot run the current check.

Do not treat every non-zero code as bad. Create a wrapper to translate the test harness outcome into git bisect's contract.

### 5.1. Defining Test Harness Exit Codes

Suppose a dedicated test script follows this convention:

| Test Harness Code | Meaning |
|---|---|
| 0 | Correct behavior, bug not reproduced |
| 10 | Assertion reproduced the exact target bug |
| 20 | Untestable: missing environment, dependency, or non-applicable test |
| Other codes | Unclassified, needs investigation |

Codes 10 and 20 are conventions for this example, not defaults of Git or Gradle. The project needs to standardize this contract in its test harness.

### 5.2. Sample Shell Wrapper

Place the wrapper in a location accessible throughout the entire bisect run, such as outside the working tree or in a stable tool unaffected by checking out different commits.

~~~sh
#!/bin/sh

# Do not use set -e because we need to read the test harness exit code.
set -u

if [ ! -x "./gradlew" ]; then
    echo "SKIP: Gradle wrapper does not exist at this commit" >&2
    exit 125
fi

./scripts/check-regression.sh
result=$?

case "$result" in
    0)
        echo "GOOD: test did not reproduce the bug"
        exit 0
        ;;
    10)
        echo "BAD: test reproduced the bug"
        exit 1
        ;;
    20)
        echo "SKIP: environment or test not ready"
        exit 125
        ;;
    *)
        echo "SKIP: unclassified exit code $result" >&2
        exit 125
        ;;
esac
~~~

In this example, check-regression.sh is a project-defined test harness. It must distinguish assertion failures from an inability to run the test. The wrapper translates code 10 to 1 so Git treats it as bad, and translates code 20 or unclassified codes to 125 to skip.

Not every project needs to skip unknown exit codes. If a specific exit code is confirmed to represent a software bug, map it to bad. If that code could be an environment failure, avoid automatically labeling it bad before investigating.

### 5.3. Why Place the Wrapper Outside the Repository?

git bisect run checks out each commit. If the wrapper resides inside the repository but was only added in a newer commit, the file may not exist at older commits. In that case the shell may return exit code 127 (command not found), and Git interprets that as bad.

There are two options:

- Place the wrapper outside the working tree, such as in a personal tools directory or a temporary directory.
- Place the wrapper inside the repository while ensuring it exists with the same semantics across every commit in the bisect range.

Example running a wrapper outside the repository:

~~~
git bisect run sh /tmp/bisect-runner.sh
~~~

The /tmp path is an example for POSIX or compatible Git Bash environments. On Windows, use a path accessible to the shell running Git, or invoke the wrapper via Git Bash/WSL according to your project setup.

Ensure the wrapper has read and execute permissions, required tools are installed, and the test command executes from the repository root. git bisect run executes the command inside the working tree being bisected.

## 6. Running Automated Bisect

### 6.1. Start the Bisect Session

You can start and then mark the two boundaries:

~~~
git bisect start
git bisect bad <known-bad-commit>
git bisect good <known-good-commit>
~~~

Or pass both markers immediately upon starting:

~~~
git bisect start <known-bad-commit> <known-good-commit>
~~~

Git then selects a commit in the middle of the range and checks it out for testing.

### 6.2. Hand Over Testing to Git

Run the wrapper:

~~~
git bisect run sh /tmp/bisect-runner.sh
~~~

Git will:

1. Invoke the wrapper at the commit currently under test.
2. Read the exit code.
3. Mark the commit as good, bad, or skip.
4. Select the next commit.
5. Repeat until a result is determined or the range can no longer be narrowed.

If the run succeeds and history has a clear boundary, Git reports the first commit identified as bad. Record the SHA and commit message for investigation.

### 6.3. Inspect Results and Confirm Manually

After bisect finishes:

~~~
git show --stat --oneline <first-bad-commit>
git show <first-bad-commit>
~~~

Read the diff of the found commit to understand which change likely caused the bug. Afterward you can check out or create a separate investigation branch if you need to run additional checks:

~~~
git switch -c debug/inspect-first-bad <first-bad-commit>
~~~

This command creates a new branch at the discovered commit. If you simply want to continue bisecting or return to the original branch, use git bisect reset as described at the end.

## 7. Handling Untestable Commits

Not every commit can run the same test. You may encounter cases such as:

- Older commits lack the test harness or test scripts.
- The project changed its build structure, so the current command no longer applies.
- A dependency was removed from the registry or no longer has a compatible version.
- The commit requires an older runtime, compiler, or operating system.
- A service or test dataset is no longer available.
- The commit lies mid-migration of an API so the current test does not apply yet.

If you cannot conclude good or bad, skip the commit.

### 7.1. Automatic Skipping with Exit Code 125

In the wrapper, return 125 when unable to test:

~~~sh
if [ ! -f "./gradlew" ]; then
    echo "SKIP: commit does not have Gradle wrapper yet" >&2
    exit 125
fi
~~~

When git bisect run receives code 125, it skips the current commit and continues searching within the remaining range.

Only use skip when testing is truly impossible. If the build fails because the change under investigation broke compilation, that may be a bad result rather than a skip. The decision depends on your investigation's failure criterion.

### 7.2. Manually Skipping a Commit

If you are running bisect manually and notice the current commit cannot be tested:

~~~
git bisect skip
~~~

You can specify one or more commits:

~~~
git bisect skip <commit-a> <commit-b>
~~~

This command marks the specified commits as unusable for classification. Git will continue picking another commit in the search range.

### 7.3. Skipping a Commit Range

If you know in advance that a span of history is untestable, you can skip a range:

~~~
git bisect skip <first-commit>..<last-commit>
~~~

The range uses two-dot syntax, excluding first-commit while including commits reachable from last-commit without going through first-commit. Verify the exact range before using it because skipping too broadly can prevent pinpointing the offending commit.

Do not skip an entire range just because a build command is failing. First identify whether the cause is the environment, an inapplicable test, or genuinely broken source code.

## 8. Bisect Results Can Be Ambiguous When Commits Are Skipped

Skipping lets the search continue, but it cannot supply information the test failed to measure. If the first bad commit lies inside a skipped region, Git cannot tell exactly which commit in that region caused the bug.

Example:

~~~text
A---B---C---D---E---F---G
good       ?   ?       bad
           skip
~~~

If C and D are untestable while B is good and E is bad, the first bug-introducing commit could be C, D, or E depending on history and outcomes. Git can narrow the range, yet still report a group of candidate commits rather than a single commit.

When you receive a message stating the first bad commit may be among skipped commits:

1. Read the list of candidate commits Git displays.
2. Check whether you can reconstruct the historical environment to test some of those commits.
3. Find a test compatible with the older version or build an adapter for the legacy API/build.
4. Use manual inspection or a different criterion applicable to that region.
5. Re-run bisect with more suitable markers or test commands.

Do not randomly pick one commit in the skipped region as the first bad commit. Your conclusion should explicitly note the indistinguishable range if no further evidence exists.

## 9. Distinguishing Regressions from Test and Environment Errors

This is what determines the quality of automated results. A command returning non-zero does not automatically prove a commit is buggy.

| Situation | Appropriate Classification | Reason |
|---|---|---|
| Assertion reproduces the exact bug | Bad | Buggy behavior has appeared |
| Test passes and does not reproduce the bug | Good | Tested behavior is still correct |
| Missing runtime or external dependency | Skip | Cannot execute the check |
| Test did not exist at historical commit | Skip or use a compatible test | Cannot evaluate with the current test yet |
| Build fails because the commit itself broke source code | Bad if build success is the criterion | Build failure is the regression under investigation |
| Test times out due to external service disconnection | Skip or rerun under controlled conditions | Insufficient evidence about source code |
| Flaky test, results vary across runs | Unclassified | Stabilize the test first |

### 9.1. Compilation Errors Can Be Bad

If the investigation goal is "which commit broke project compilation", a compile error is a bad signal. Do not skip simply because the build failed.

Conversely, if the goal is "which commit caused search to return wrong results", a commit that cannot build due to an incompatible JDK on the test machine is not necessarily bad. Determine whether the proper historical toolchain can be set up.

### 9.2. Test Did Not Exist in Older Commits

If the test was added after the bug already existed, older commits lack that test. You can store the test outside the repository and write an adapter to call the corresponding API for each era, or use a behavioral test through a stable interface.

If a compatible test cannot be built, skip the inapplicable commits and document the limitation of the result.

### 9.3. Flaky Tests

A flaky test can mark the same commit good one time and bad another. This breaks bisect's fundamental assumption. You should:

- Run the test multiple times to measure stability.
- Isolate data and dependent services.
- Disable randomness or pin seeds where appropriate.
- Separate environment failures from assertions.
- Start bisect only once the criterion is sufficiently reliable.

## 10. Saving and Replaying a Bisect Session

git bisect records good, bad, and skip decisions in a log. You can save the log to reproduce the investigation:

~~~ 
git bisect log > bisect-session.log
~~~

Then replay it in an appropriate repository:

~~~ 
git bisect reset
git bisect replay bisect-session.log
~~~

The log helps share marker choices and skipped commits with teammates. However, the log does not bundle the environment, dependencies, or test scripts. For others to reproduce, also record the wrapper version, test harness, toolchain requirements, and test data details.

During an active session, view the log:

~~~ 
git bisect log
~~~

You can use git bisect visualize to inspect remaining relevant commits in the search range using the configured log viewer.

## 11. Ending Bisect and Restoring the Branch

Once you have found the commit or want to stop the investigation, run:

~~~ 
git bisect reset
~~~

Git exits bisect mode and returns to the original position before starting the session, usually the branch or commit you were on when running git bisect start.

If you need to return to a specific position:

~~~ 
git bisect reset <branch-or-commit>
~~~

Before resetting, save the required SHA and logs. If you created an investigation branch at the discovered commit, that branch still points to the investigated commit after exiting bisect.

Do not confuse git bisect reset with git reset. The first ends the bisect session; the second moves HEAD or updates the index/working tree depending on options and can discard changes if misused.

## 12. Complete Example: Finding the Commit That Broke Search

Suppose the team discovers search is no longer case-insensitive. Commit v1.2.0 was verified to work, while current main is broken.

**Step 1 — Verify Markers**

~~~ 
git status -sb
git fetch origin
git show --no-patch --oneline v1.2.0
git show --no-patch --oneline origin/main
~~~

**Step 2 — Start Bisect**

~~~ 
git bisect start
git bisect bad origin/main
git bisect good v1.2.0
~~~

**Step 3 — Run Automated Testing**

Suppose the wrapper is outside the repository and the test harness follows the agreed exit code contract:

~~~ 
git bisect run sh /tmp/bisect-search.sh
~~~

During execution:

- Commits with test exit code 0 are marked good.
- Commits reproducing the regression are mapped by the wrapper to 1 and marked bad.
- Commits lacking a suitable environment or test are mapped by the wrapper to 125 and skipped.

**Step 4 — Read Results**

~~~ 
git show --stat --oneline <first-bad-commit>
git show <first-bad-commit>
git bisect log
~~~

If Git reports a single commit, re-verify by running the test at that commit and its parent commit. If the result is ambiguous due to skipped commits, investigate the candidate region and improve the test before concluding.

**Step 5 — End the Session**

~~~ 
git bisect reset
~~~

Afterward, record the offending commit, test used, skipped commits, skip reasons, and result limitations in the ticket or investigation report.

## 13. Common Mistakes When Automating Bisect

**Wrong exit code mapping.** Environment failures may be marked bad. Build a wrapper with a clear contract and test exit codes before running the full bisect.

**Runner missing in older commits.** If the script is checked out with the repository and did not exist in older history, the shell may return 127; Git treats this as bad. Place the runner outside the repository or ensure it exists across all commits.

**Using set -e and failing to read the exit code.** In shell scripts, set -e can abort the script immediately when the test returns non-zero. If you need to map exit codes, invoke the command, capture the exit code in a variable, and use case or if to classify it.

**Skipping too many commits.** Broad skipping can leave Git only able to identify a range of candidates. Try reconstructing the toolchain or writing a compatible test.

**Using flaky tests.** Unstable results send bisect down the wrong branch. Stabilize the test before running.

**Not saving the log.** Without saving git bisect log, it is hard for the team to reproduce the good, bad, and skip decisions.

**Forgetting to exit bisect.** After investigating, run git bisect reset to return to the original branch or commit.

**Equating compile failure with functional failure.** Define the goal of your investigation. A build failure is only bad when buildability is the criterion being tested or the failure was caused directly by the commit's changes.

## 14. Checklist for an Automated Bisect Session

**Before Running**

- [ ] Confirmed the right repository and a clean working tree.
- [ ] Selected good and bad commits backed by evidence.
- [ ] Defined a reproducible test criterion.
- [ ] Verified the test harness can run across historical commits.
- [ ] Placed the runner in a location that persists throughout the entire bisect session.
- [ ] Defined clear exit codes for good, bad, and skip.

**During Execution**

- [ ] Code 0 is used only when the test confirms good state.
- [ ] Codes 1 through 127, excluding 125, are used only when bad is confirmed.
- [ ] Code 125 is used when testing cannot be performed.
- [ ] Fatal execution errors are handled so bisect stops.
- [ ] Flaky tests or external service failures are not mistaken for regressions.

**After Execution**

- [ ] Saved the first bad commit and git bisect log.
- [ ] Re-verified the found commit and its parent commit.
- [ ] Reviewed the list of skipped commits and assessed ambiguity.
- [ ] Documented limitations if a single unique commit could not be identified.
- [ ] Ran git bisect reset to end the session.

## 15. Conclusion

git bisect run automates finding a bug-introducing commit by executing a test command at each selected commit. For accurate results, the test command must use a stable criterion and return proper exit codes: 0 for good, 1 through 127 except 125 for bad, 125 for untestable commits, while codes above 127 abort the run.

Untestable commits must be skipped intentionally rather than guessed as good or bad. When multiple commits are skipped, the result may point to a group of candidates. Save the log, investigate ambiguous ranges, re-verify the located commit, and end the session with git bisect reset. This workflow helps teams pinpoint regression causes faster while preserving the reliability of conclusions.

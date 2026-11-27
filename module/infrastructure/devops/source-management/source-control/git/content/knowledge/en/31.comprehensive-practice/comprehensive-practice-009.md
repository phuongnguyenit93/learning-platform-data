# Finding the Bug-Introducing Commit With Bisect and a Reproducible Test

When a bug appears in the current version and you do not know which commit introduced it, reading through the entire history sequentially takes too much time. `git bisect` narrows down the search range via binary search: you supply one known good commit and one known bad commit, and Git checks out midpoint commits one by one for you to evaluate. After each evaluation, Git selects the next half of the remaining history.

The best results come when you have a reliable **reproducible test case**. The test must fail on the buggy revision, pass on the good revision, and produce consistent results across repeated runs. Once you have such a test, `git bisect run` can automatically execute it on each commit to pinpoint the exact commit that first introduced the bug.

## 1. When Should You Use git bisect?

`git bisect` fits well when:

- A bug is present on the current branch, whereas the feature worked previously.
- You know an older good commit or tag and a newer bad commit.
- History contains enough commits between those two points to search.
- A relatively fast check can run on each commit.

Example: a payment application worked cleanly at `v2.4.0`, yet by `v2.8.0` total calculation occasionally returns the wrong amount. There are 80 commits in that range. Instead of testing every commit in order, bisect can locate the offending commit in roughly 6 to 7 evaluations if history is linear and no commits must be skipped.

You need two trustworthy boundaries:

- **Good:** a commit where the test confirms behavior is still correct.
- **Bad:** a commit where the test confirms the bug is present.

Bisect assumes the bug has a consistent transition boundary within the search range: moving from good toward bad, there is a commit where the state flips from good to bad. If a bug appeared and was later fixed, depends on environment quirks, or only reproduces intermittently, narrow the range or stabilize the test first.

## 2. Preparation Before Starting

Before running bisect, define the bug and how to verify it precisely. A good description includes:

1. Input or reproduction conditions.
2. Expected outcome.
3. Actual outcome on the buggy version.
4. A repeatable verification command.
5. Required environment dependencies such as runtime, database, environment variables, and external services.

Example:

```text
Scenario: order with subtotal = 100 and discount = 10
Expected: total = 90
Actual at v2.8.0: total = 110
Check: run test payment-total-regression
```

Inspect the working tree before starting:

```bash
git status --short
git branch --show-current
git log --oneline -10
```

Commit or set aside any uncommitted changes. During bisect, Git checks out multiple commits and puts `HEAD` into a detached state; local edits can block checkouts or skew test results so they no longer reflect the commit being tested.

Ensure you have sufficient history. If working in a shallow clone, fetch full history or unshallow before bisecting. Example:

```bash
git rev-parse --is-shallow-repository
git fetch --unshallow origin
```

`--unshallow` only works when the remote can provide the missing history. If the repository is already complete, skip this command.

## 3. Creating a Reproducible Regression Test

A reproduction (regression) test is an automated or manual check proving the bug occurs. The test should target the broken behavior without coupling to unrelated implementation details.

A good test has these qualities:

- **Repeatable:** the same commit in the same environment produces the same result.
- **Separates good from bad:** passes on good commits, fails on bad commits.
- **Fast:** each bisect iteration does not take too long.
- **Low-dependency:** avoids network calls, wall-clock timing, production data, or external services unless strictly necessary.
- **Clear output:** on failure, states clearly which assertion failed.

Example of a simple JavaScript test:

```javascript
import { calculateTotal } from "../src/payment.js";

test("applies discount before returning total", () => {
  const total = calculateTotal({ subtotal: 100, discount: 10 });
  expect(total).toBe(90);
});
```

This test is illustrative only. Adjust imports, syntax, and test runner to your real project. Crucially, the same test command must run across the commits bisect checks out.

### A Newly Written Test Might Not Exist in Older Commits

This detail is often overlooked. If you just wrote the regression test at the current commit, older commits in the bisect range will not contain that test file or possibly the test runner itself. The test command will fail due to a missing file, and Git may mistake that failure for a bad commit if the script returns a normal error exit code.

Several ways to handle this:

1. Use an existing test or script that already exists across the entire commit range.
2. Keep the test harness outside the working tree and point it at the source code of the currently checked-out commit.
3. Have a bisect script temporarily apply the test patch to each commit, run the test, and clean up the patch before the next checkout.
4. Narrow the search range to commits where the test runner and project layout already exist.

If using an external test harness, make sure it always reads source code from the bisected working tree rather than accidentally importing an old installed package or reusing build artifacts from another commit. You may need to clear caches and build output between runs.

## 4. Starting a Manual Bisect Session

Standard syntax:

```bash
git bisect start
git bisect bad <bad-commit>
git bisect good <good-commit>
```

For example, current `HEAD` is buggy and tag `v2.4.0` was good:

```bash
git bisect start
git bisect bad HEAD
git bisect good v2.4.0
```

You can also pass both bounds directly on start:

```bash
git bisect start HEAD v2.4.0
```

In this shorthand, the first argument is bad and subsequent arguments are good. Once the session starts, Git checks out a commit near the midpoint of the range. `HEAD` enters a detached state; that is normal behavior.

Check which commit is currently under test:

```bash
git status --short
git log -1 --oneline --decorate
git rev-parse HEAD
```

Run your reproduction test on that commit. If the test passes, mark it good:

```bash
git bisect good
```

If the test fails with the bug you are investigating, mark it bad:

```bash
git bisect bad
```

Git uses your result to choose the next commit in the remaining range. Continue testing and marking until Git identifies the first commit where behavior transitioned from good to bad.

## 5. Understanding the Binary Search Process

Suppose linear history has commits A through H:

```text
A---B---C---D---E---F---G---H
    good                    bad
```

You know B is good and H is bad. Git picks a midpoint commit, such as E:

```text
A---B---C---D---E---F---G---H
    good        ?           bad
```

If E is good, the bug must lie after E; if E is bad, the bug lies between B (exclusive) and E. Git keeps halving the remaining range.

Across roughly 64 candidate commits, binary search typically takes about 6 evaluations instead of testing 63 commits sequentially. The actual step count can increase if commits are skipped, merge topology is complex, or tests cannot run on certain revisions.

You can inspect the current state and bisect session log:

```bash
git bisect log
git bisect visualize
```

`git bisect visualize` displays the list/graph of remaining candidate commits using the configured log viewer. To inspect the good/bad marks recorded so far, `git bisect log` is easy to review and save.

## 6. Skipping Untestable Commits With git bisect skip

Some commits cannot build or run tests due to missing dependencies, temporary build breakage, or incomplete structure. Do not automatically mark such revisions as bad.

Use:

```bash
git bisect skip
```

Git excludes the current commit from evaluation and picks another revision. You can skip one or multiple revisions:

```bash
git bisect skip <commit-1> <commit-2>
```

If commits right around the transition boundary are skipped, Git may not be able to narrow down a single first bad commit. It will report a range or set of candidate commits instead. In that case, refine your test/harness, supply closer good/bad bounds, or inspect the remaining candidates manually.

Only use `skip` when a commit genuinely cannot be classified. If the test fails due to the bug under investigation, mark it bad; if it passes, mark it good.

## 7. Automating With git bisect run

Once you have a test command that reliably classifies commits, use `git bisect run` so Git executes it automatically at each revision:

```bash
git bisect start
git bisect bad HEAD
git bisect good v2.4.0
git bisect run <command> [<arg>...]
```

For example, if the test runner exists across every commit in the range:

```bash
git bisect run npm test -- --runInBand tests/payment-regression.test.js
```

Git checks out the next commit, runs the command, reads its exit code, and automatically marks good, bad, or skip. It repeats until it identifies the first bad commit or cannot narrow further due to skipped commits.

### Exit Code Conventions for bisect run Commands

Exit codes are critical. `git bisect run` interprets exit status as follows:

| Exit code | Meaning to bisect |
|---:|---|
| `0` | Good commit: test passed |
| `1` to `124` | Bad commit: test failed |
| `125` | Skip commit: this revision cannot be tested/classified |
| `126`, `127` | Treated as bad per exit-code rules, usually command execution failures; guard against environment errors being misread as product bugs |
| `128` and above | Aborts the `bisect run` session due to abnormal termination or signal |

Because `126` and `127` count as bad, your script should check for required tools and files upfront. If a dependency is missing or the test cannot run for environmental reasons, return `125` to skip instead of letting an error code mark the commit bad. Exit codes `128` and above halt `bisect run`.

## 8. Writing a Test Script for bisect run

A shell script can normalize test outcomes into three states: pass, fail, and untestable.

Example `bisect-test.sh`:

```bash
#!/bin/sh

# Cannot test if runtime or test harness is missing.
command -v npm >/dev/null 2>&1 || exit 125
[ -f package.json ] || exit 125
[ -f tests/payment-regression.test.js ] || exit 125

# Run the exact regression test.
npm test -- --runInBand tests/payment-regression.test.js
result=$?

if [ "$result" -eq 0 ]; then
    exit 0
fi

# Test runner may return 125 to signal untestable state.
if [ "$result" -eq 125 ]; then
    exit 125
fi

# All other test failures count as bad.
exit 1
```

Place the script somewhere accessible throughout the entire bisect session. If the script lives inside the repository but did not exist in older commits, checking out an older commit will make it disappear. Keep the script outside the working tree, or ensure it stays intact and is not overwritten by Git across the tested revisions.

Run:

```bash
chmod +x /path/to/bisect-test.sh
git bisect run /path/to/bisect-test.sh
```

The sample script assumes the test runner returns `0` on pass and non-zero on test failure. If your test tool can return non-zero codes for infrastructure failures, distinguish infrastructure failures from assertion failures and map infrastructure errors to `125`. Do not treat every build error or missing dependency as bad.

### Notes for Running on Windows

Git for Windows provides the `sh` shell via Git Bash. You can run a POSIX script by invoking `sh` explicitly:

```bash
git bisect run sh /c/tools/bisect-test.sh
```

Paths must match the shell environment invoked by Git. If using a PowerShell script, call PowerShell with an absolute path and ensure exit codes strictly follow `0`, `1`–`124`, `125`, or `128+`. Test your script standalone against one known good commit and one known bad commit before automating the whole range.

## 9. Building Tests That Remain Stable Across Revisions

A test may work cleanly on `HEAD` yet fail on older commits because test runner APIs changed, dependencies did not exist yet, or module layout differed. That does not necessarily mean the commit has the bug you are hunting.

To improve reliability:

- Test at the public behavior boundary rather than relying on internal function names if APIs shifted.
- Pin or install dependencies per each commit's lockfile whenever possible.
- Clean build outputs and caches left over from previous revisions if they could affect results.
- Use fixed fixtures and data; avoid wall-clock time, random test ordering, or live network services.
- Keep the same runtime/toolchain version where possible; if the project switched toolchains within the range, classify unbuildable commits as skip until the environment aligns.
- Verify the script on at least one known good commit and one known bad commit before running `git bisect run`.

If the bug only triggers with a database or external service, spin up an isolated test environment or stub data so runs are repeatable. Every bisect iteration should start from a clean environment state rather than reusing a database mutated by the prior run.

## 10. When History Contains Merge Commits

History is not always a straight line. Merge commits have multiple parents, and a bug can arise from combining two branches even when neither branch was broken on its own.

By default, bisect walks the commit graph across revisions in range. If you want to restrict the search to first-parent history (for example, only checking commits integrated onto the mainline via merges), start with:

```bash
git bisect start --first-parent HEAD v2.4.0
```

`--first-parent` follows the first-parent chain, fitting certain mainline merge workflows. However, it can bypass individual commits inside a feature branch that introduced the bug. If the bug entered via a commit on a side branch, bisecting the full graph may be necessary.

If a merge commit is flagged as the first bad commit, inspect both parents and the merged changes:

```bash
git show --cc <MERGE_COMMIT>
git diff <MERGE_COMMIT>^1 <MERGE_COMMIT>
git diff <MERGE_COMMIT>^2 <MERGE_COMMIT>
```

These commands compare the merge result against each parent. Never assume the bug sits in a side-branch commit just because the merge commit was marked bad; the bug could stem from conflict resolution or an interaction between both branches.

## 11. Investigating the Identified Commit

When Git finds the first bad commit, it prints the commit along with `first bad commit`. Record the OID and inspect the details:

```bash
git show --stat <BAD_COMMIT>
git show --format=fuller <BAD_COMMIT>
git diff <BAD_COMMIT>^ <BAD_COMMIT>
```

Read the diff, author, timestamp, and parent commit. If the commit touches many files, inspect each file and correlate it with the reproduction test.

You can also view the bisect session log:

```bash
git bisect log
```

Attach this log to your incident notes or ticket so others can verify which good/bad/skip points were evaluated. Never share only a commit hash without the reproduction test, environment details, and steps to reproduce; those details make the finding independently verifiable.

When finished investigating, exit bisect mode and return to your previous branch:

```bash
git bisect reset
```

Reset ends the bisect state and checks out the original position (or a specified revision). Verify:

```bash
git status --short
git branch --show-current
```

If you made experimental edits in the working tree, save or clean them appropriately before resetting so nothing is lost on checkout.

## 12. Other Useful Bisect Commands

| Command | Purpose |
|---|---|
| `git bisect start` | Start a bisect session |
| `git bisect good <rev>` | Mark a revision as good |
| `git bisect bad <rev>` | Mark a revision as bad |
| `git bisect skip [<rev>...]` | Skip revisions that cannot be evaluated |
| `git bisect log` | Print recorded bisect steps |
| `git bisect replay <file>` | Replay a saved bisect log |
| `git bisect visualize` | View commits remaining in the search range |
| `git bisect terms` | Show current good/bad term names |
| `git bisect reset` | Finish bisecting and return to the original position |

If you prefer custom labels instead of good/bad, configure custom terms:

```bash
git bisect start --term-new=broken --term-old=fixed
git bisect broken HEAD
git bisect fixed v2.4.0
```

This helps when a team prefers terminology suited to the incident (such as performance regressions or behavior changes), provided you use the terms consistently across commands. In this example, `broken` maps to bad and `fixed` maps to good.

## 13. Common Pitfalls When Using Bisect

### Choosing Wrong Good or Bad Bounds

If the commit marked good already had the bug, or the commit marked bad did not yet have it, results will be wrong. Run the reproduction test on both boundary commits before starting. If unsure, pick a safer boundary or check nearby tags/releases.

### Flaky Tests

A test that passes sometimes and fails other times due to race conditions, timing, network calls, or random data will misclassify commits during bisect. Isolate the test, fix fixtures, and verify repeatability before automating.

### Environment Drift Across Commits

Dependencies or runtimes may be incompatible with older commits. Distinguish product bugs from environment breakage; use `skip` for untestable revisions rather than marking them bad.

### Test Harness Missing in Older Commits

If your script or test file lives inside the repository and vanishes when checking out older revisions, `bisect run` can misclassify commits. Keep the harness outside the working tree or ensure it exists across all tested revisions.

### Forgetting About Detached HEAD

During bisect, `HEAD` is normally not on a branch. Do not make fix commits directly in that detached state unintentionally; finish bisect first or create a rescue branch if you need to save an experiment.

### Forgetting to Reset After Finding the Commit

After recording your findings, run `git bisect reset` to return to your original branch. Forgetting leaves you working on a detached commit without realizing it.

## 14. End-to-End Sample Investigation Workflow

Suppose the payment total bug appears at `HEAD`, while tag `v2.4.0` is known good. You already have a stable reproduction test and an external harness script outside the working tree.

**Step 1: Verify status and boundary commits**

```bash
git status --short
git show --no-patch --oneline HEAD
git show --no-patch --oneline v2.4.0
```

Run the test on `HEAD` to confirm it fails and on `v2.4.0` to confirm it passes.

**Step 2: Start bisect**

```bash
git bisect start
git bisect bad HEAD
git bisect good v2.4.0
```

**Step 3: Automate test execution**

```bash
git bisect run /path/to/bisect-test.sh
```

Git checks out candidate commits and runs the harness. The harness returns `0` if the test passes, `1` if it fails with the target bug, and `125` if the commit cannot be evaluated.

**Step 4: Inspect the first bad commit**

```bash
git show --stat <BAD_COMMIT>
git show <BAD_COMMIT>
git bisect log
```

Compare the commit's changes against the reproduction conditions. If the result seems off, re-check the test, good/bad bounds, and any skipped commits.

**Step 5: End the session**

```bash
git bisect reset
git status --short
```

Document the commit OID, test executed, environment, skipped commit count, and conclusion so the team can verify independently.

## 15. Hands-On Practice Exercise

In a sandbox repository, create a history of roughly 8–16 commits. Have one commit in the middle intentionally introduce a calculation bug; have subsequent commits update docs or add features while leaving the bug intact.

1. Write a reproduction test and confirm it passes before the buggy commit and fails after it.
2. Start `git bisect` and mark the good and bad bounds.
3. Observe intermediate commits being checked out, run the test, and mark `good`/`bad` manually.
4. Repeat the bisect session using `git bisect run` with a script returning proper exit codes.
5. Intentionally make one commit unbuildable and update your script to return `125`; observe how Git skips that commit.
6. Inspect `git bisect log`, record the first bad commit, and use `git show` to analyze the change.
7. Run `git bisect reset` and confirm your original branch and working tree are restored cleanly.
8. Test a flaky or environment-dependent check in the sandbox repository, explain why bisect results can go wrong, and show how to make the test deterministic.

You have completed the exercise when you can pinpoint the offending commit using both manual marking and `git bisect run`, explain the role of a reproducible test, and properly classify good, bad, and skip commits.

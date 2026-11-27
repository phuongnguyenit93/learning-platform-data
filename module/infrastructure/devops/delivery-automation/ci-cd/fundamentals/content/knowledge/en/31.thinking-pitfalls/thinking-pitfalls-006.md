# Ignoring Failing Tests or Retrying Indefinitely to Get Green

A green pipeline is commonly treated as a signal that a change has passed the necessary checks. Yet green only has meaning when checks actually ran, results were preserved, and critical failures were not hidden. If a team ignores failing tests, enables continue-on-error modes, or keeps hitting retry until it passes, the pipeline can turn green while the software still contains unexamined defects.

This is a common thinking pitfall in CI/CD: treating the final status as the goal rather than treating test evidence as the basis for a decision. A subsequent successful run does not erase the previous failure. It merely adds a new observation under execution conditions that may have changed.

This lesson helps identify behaviors that produce false green states, classify failures before retrying, design bounded retry limits, manage flaky tests, and keep quality gates accurately reflecting change risk.

## 1. Understanding the True Meaning of Green

A pipeline can finish successfully for very different reasons:

- All required checks ran and passed on the first attempt.
- A clearly identified transient infrastructure error occurred, a safe operation was retried within bounds, and it succeeded.
- A test failed on the first run but passed on re-run due to non-determinism.
- A critical job was skipped, marked allowed-to-fail, or excluded from the verification flow.
- The pipeline ran a smaller subset of tests than intended due to misconfigured path filters or job conditions.

These cases do not carry equal confidence. The final status is one piece of the outcome, but it must be read alongside attempt history, the list of checks executed, skipped steps, and exception rationales.

We can distinguish the following states:

| State | Meaning | How to Use |
|---|---|---|
| Passed on first attempt | All required checks passed on the first run | Strong evidence for the tested commit and environment |
| Passed after transient retry | Transient error was classified; bounded retry succeeded | Can recover the flow, but retry history must be retained |
| Flaky | Same inputs and equivalent conditions yield inconsistent results | Test outcome is not yet trustworthy; needs investigation |
| Failed | A required check failed or the error is not retryable | Blocks the corresponding quality gate |
| Quarantined | Test removed from main gate under a controlled exception | Must have an owner, expiration, and compensating check |
| Not run / skipped | Check was not executed | Must never be interpreted as passed |

A report that only says "success" erases the difference between these states. The system should clearly show whether a run passed on the first attempt or after retry, which tests are quarantined, and which jobs did not run.

## 2. Why Do Teams Easily Chase Green?

Delivery pressure often pushes teams to prioritize finishing the pipeline so a pull request can merge or a release can proceed. When a test fails intermittently, clicking retry can be the fastest way to clear the immediate bottleneck. If the next run passes, everyone feels the issue is resolved.

Several thoughts lead to this behavior:

- "It passed the second time, so the first failure was probably just random."
- "This test fails a lot; let's skip it so the other team can keep working."
- "As long as the build succeeds, we can release."
- "If we retry enough times, it'll pass eventually."
- "Pipeline green rate is a KPI; don't let one test slow down the release."
- "Fixing the test takes way longer than just re-running it."

These assumptions equate completing an action with reducing risk. A "random" failure can still indicate a race condition, data contention, environment dependency, or lack of isolation. A long-flaky test may be guarding an essential business flow that the team has no other way to verify.

The goal of CI is not to force every run to green at any cost. The goal is to deliver reliable feedback so the team knows whether a change is qualified to move forward.

## 3. Classify Failure Types Before Deciding to Retry

Retrying only makes sense when the team understands the kind of failure encountered. A timeout message or nonzero exit code does not explain its own cause. Combine logs, metrics, attempt history, runner status, and recent changes to classify failures.

| Failure Type | Common Symptoms | Initial Handling |
|---|---|---|
| Deterministic code failure | Wrong assertion, compile error, test catching regression | Fix code or test per contract; never retry past it |
| Configuration error | Missing variable, wrong permission, wrong endpoint, invalid env config | Fix config or permissions; retry after condition is fixed |
| Transient infrastructure error | Runner disconnected, registry returned 503/429, connection reset | Bounded retry allowed if operation is safe |
| Flaky test | Same commit and equivalent conditions, yet intermittently passes/fails | Investigate determinism; time-bounded quarantine if needed |
| External dependency failure | Slow sandbox API, test service unavailable, unsynced data | Check dependency health, timeouts, and backoff |
| Security or policy failure | Secret scan, artifact signature, policy gate, or access check failed | Keep gate failed until valid evidence exists |

Different causes can share identical symptoms. For example, a test timeout could stem from hung code, a deadlock, an under-resourced runner, a slow database response, or an overly tight timeout setting. Never automatically classify every timeout as transient.

### 3.1. Deterministic Failures Do Not Become Transient After One Retry

If an assertion reports an actual value differing from the expected value, re-running does not change the software's contract. If a compile error occurs because an API changed, another retry will not fix the source code. For deterministic errors, stop and investigate.

A test assertion that fails and then passes on a subsequent run does not prove the initial assertion can be ignored. It shows the test or environment is non-deterministic. The result must be classified as flaky until an evidence-backed explanation is found.

### 3.2. Infrastructure Errors Can Be Retried, Under Conditions

A preempted runner or a registry temporarily returning `503` can be appropriate retry cases. Before retrying, verify:

- Is the error code on the approved list of transient errors?
- Has the dependent system recovered or is it likely to recover?
- Is the operation safe to execute again?
- Does the retry stay within total time and attempt limits?
- Is evidence from the first failure preserved?

If configuration, authentication, or policy errors are misclassified as transient, retrying only adds load and delays fixing the real problem.

## 4. How Infinite Retries Create False Green States

Suppose a test job fails with a 20% probability on each independent run. If the system keeps re-running until it succeeds, the probability of eventually getting at least one pass approaches 100% as attempts increase. That probability does not mean the test became more reliable; it simply means the team waited long enough to hit a favorable outcome.

With flaky tests, the independence assumption is rarely strictly true. Still, the principle holds: the more unlimited retries you allow, the less the final status reflects the reliability of the initial verification.

~~~mermaid
flowchart TD
    A["Test starts"] --> B{"Result?"}
    B -->|Pass| C["Passed on first attempt"]
    B -->|Fail| D{"Classify failure"}
    D -->|Deterministic failure| E["Keep failed state"]
    D -->|Allowed transient failure| F{"Retry budget left?"}
    D -->|Flaky or unknown| G["Record instability and investigate"]
    F -->|Yes| H["Save attempt and wait backoff"]
    H --> A
    F -->|No| I["Failed after bounded retries"]
    C --> J["Aggregate quality gate"]
    E --> J
    G --> J
    I --> J
~~~

When pipelines loop until passing, teams face several consequences:

- **Masking regressions:** tests fail initially, yet the final status is reported as if no error ever happened.
- **Creating unnecessary load:** runners, databases, registries, and test services must handle repeated executions.
- **Lengthening feedback:** pull requests wait longer and completion times become unpredictable.
- **Increasing side-effect risks:** deployments, migrations, message publishing, or resource creation may execute multiple times.
- **Distorting metrics:** final pass rates look high while initial failure rates and retries climb.
- **Eroding trust in quality gates:** developers learn to click retry instead of reading and fixing errors.

A pipeline that retries three times and passes is not equivalent to one that passes on the first attempt. Reporting and release decisions must preserve that distinction.

## 5. Designing Bounded, Justified Retries

Retry should be an explainable policy, not an infinite loop waiting for a favorable roll.

A practical policy must define:

1. The list of explicitly retryable errors.
2. Maximum attempt count per operation type.
3. Maximum total retry duration.
4. Wait interval between attempts.
5. Idempotency conditions or duplicate-execution guards.
6. Data that must be saved for each attempt.
7. How retry outcomes affect quality gates.

General logic example:

~~~text
MAX_ATTEMPTS = 2

for attempt in 1..MAX_ATTEMPTS:
    result = run_check()
    save_attempt_evidence(attempt, result)

    if result.is_success:
        if attempt == 1:
            return PASSED_FIRST_ATTEMPT
        return PASSED_AFTER_RETRY

    if not is_explicitly_retryable(result.failure):
        return FAILED

    if attempt == MAX_ATTEMPTS:
        return FAILED_AFTER_RETRY

    wait_with_backoff_and_jitter(attempt)
~~~

This is illustrative pseudocode, not syntax for a specific CI vendor. Limit values should be grounded in failure type, dependency recovery time, and operation safety. For some actions, one retry is enough; certain read-only tasks might carry a different budget. Never apply one uniform number to every job.

### 5.1. Avoid Nested Retries

A job might retry an entire pipeline stage while an inner script also retries HTTP requests and the test framework automatically reruns failed tests. If each layer allows three attempts, actual executions can multiply dramatically.

Define which layer owns retries and pass remaining budget down to lower layers. Logs should show the overall attempt count, not just a script's local retry counter.

### 5.2. Use Backoff and Jitter for Rate-Limited Dependencies

When a registry or API returns `429` or `503`, immediate retries can add load and slow recovery. Exponential backoff increases wait intervals with each attempt; jitter adds a random offset so many jobs do not retry at the exact same instant.

Honor `Retry-After` headers when provided by the service. If total wait time exceeds the pipeline budget, fail with a clear diagnostic message.

### 5.3. Do Not Retry Operations with Side Effects Without Controls

A read command is usually safer than a write command. Retrying deployments, migrations, package publishes, or event emissions can create duplicate outcomes if the system already accepted the command before the connection dropped.

Before retrying, determine the status of the prior operation. Use idempotency keys, transactions, state reconciliation, or completion checks. If state cannot be determined, stop and investigate rather than resending blindly.

## 6. Preserve Evidence from Every Attempt

Each attempt should carry an attempt ID or clear link to the same pipeline run. Never overwrite logs from the first attempt with logs from the next.

At minimum, store:

| Field | Purpose |
|---|---|
| Pipeline run ID and job ID | Link related executions |
| Attempt number | Know which attempt this was |
| Commit SHA and pipeline definition revision | Confirm inputs remained unchanged |
| Test name or command | Identify the exact check |
| Runner ID, image, and environment | Compare execution conditions |
| Dependency versions and cache state | Detect differing inputs |
| Start/end times and exit code | Reconstruct the timeline |
| Failure category and retry reason | Explain why it was retried |
| Artifact/log reference | Enable follow-up investigation |

Evidence must be protected from accidental modification. If logs might contain secrets, redact before sharing and restrict access to raw originals.

A useful report can display:

~~~text
Pipeline: run-1842
Commit: a1b2c3d
Check: order-api-contract-test

Attempt 1:
  Result: FAILED
  Category: FLAKY_SUSPECTED
  Runner: linux-pool-03
  Exit code: 1

Attempt 2:
  Result: PASSED
  Category: PASSED_AFTER_RETRY
  Runner: linux-pool-07

Final quality state: UNSTABLE
Reason: Same test failed then passed; investigation required
~~~

This example shows a job that had a passing run, yet overall quality still must be flagged as unstable according to team policy.

## 7. Manage Flaky Tests Instead of Ignoring Them

A flaky test is a test that can yield different outcomes given supposedly equivalent inputs and conditions. Causes can include:

- Dependence on execution order or leftover state from prior tests.
- Shared files, databases, ports, queues, or accounts across multiple tests.
- Race conditions and insufficient synchronization.
- Dependence on time, timezones, random seeds, or schedules.
- Uncontrolled calls to external services.
- Variable runner resources or overly tight timeouts.
- Incomplete cleanup after tests finish.

### 7.1. Investigate by Making the Test Reproducible

An investigation workflow can include:

1. Record test name, commit, seed, input data, and environment.
2. Run the test standalone to check for order dependencies.
3. Run in a loop in a controlled environment to estimate failure frequency.
4. Run in parallel to uncover resource or data contention.
5. Replace external dependencies with fakes or test doubles where appropriate.
6. Inspect logs, traces, and post-cleanup state.
7. Rewrite the test to verify a clear, repeatable contract.

Repeated runs are an intentional, bounded, and documented diagnostic technique. That differs from retrying in the pipeline until getting green.

### 7.2. Quarantine Is Only a Temporary Measure

When a flaky test blocks the entire team, it can be temporarily separated from the main gate if risk has been assessed and a suitable replacement control exists. Quarantine does not mean deleting the test or marking it as passed.

A quarantine exception needs:

- Specifically identified test or test group.
- Rationale, evidence, and risk scope.
- An owner accountable for fixing it.
- A tracking ticket and expiration date.
- A way to run the test outside the main gate to keep collecting signal.
- An explicit decision on whether releases are allowed to proceed.

Never silently quarantine security tests, artifact signature checks, migrations, critical contracts, or data-protection tests. If a critical check cannot run reliably, an approved compensating verification measure is required before allowing release.

A quarantine without an expiration turns a temporary defect into a permanent fixture of the process. Dashboards should show the age of each quarantine and alert when overdue.

## 8. Do Not Turn Mandatory Checks into Optional Ones

Several configurations can turn a pipeline green even when jobs fail or do not run:

- Allowing a job to fail while the pipeline continues.
- Using shell commands that swallow exit codes, such as chaining with a construct that always returns success.
- Marking a job optional without rationale or an owner.
- Using conditions that run tests only on certain branches while reports hide what was skipped.
- Skipping scans or signature checks when the scanning service errors out.
- Reusing stale artifacts or invalid caches to avoid re-running verification steps.

Mechanisms like `continue-on-error` or `allow-failure` can be useful for informational jobs, experiments, or non-mandatory checks. However, they must be clearly categorized and never used on release-protecting gates.

A quality gate should define:

| Property | Question to Answer |
|---|---|
| Required check | Which checks are mandatory before merge or release? |
| Optional check | Which jobs are informational only, and why? |
| Skip condition | Under what conditions is skipping permitted? |
| Failure policy | Which errors block the pipeline, and which follow an exception process? |
| Retry policy | Which failure types are retryable, and up to how many attempts? |
| Exception owner | Who is authorized to approve exceptions and for what duration? |
| Evidence | Which logs and results prove the gate actually ran? |

If a mandatory check fails to run due to a missing secret, unavailable runner, or unreachable scanner service, the outcome must be unverified or failed per policy. Never interpret "no result" as "passed."

## 9. Define Decision Rules for Quality Gates

Teams should define how results are aggregated before a pipeline is used to decide merges or releases.

Example rule set:

| Outcome | Pull Request | Production Release |
|---|---|---|
| Required tests pass on first attempt | Allow to proceed if other gates pass | Allow to proceed if other gates pass |
| Transient infra failure, bounded retry passes | Allow per policy, record as recovered | Allow if artifact/inputs unchanged and gate not weakened |
| Test assertion fails then passes on retry | Mark unstable, require action per risk level | Do not treat as clean pass; require review or compensating test |
| Required security/signature gate fails | Block | Block |
| Required test skipped outside policy | Block or require exception approval | Block |
| Retry budget exhausted | Block related gate | Block corresponding release |
| Test under controlled quarantine | Follow exception and risk | Proceed only with approved compensating verification |

This table is a sample policy. Each organization must tailor it to criticality, product type, and security requirements. The key principle is never letting a pass after retry automatically turn a flaky test into clean evidence.

Aggregation logic can be expressed as:

~~~text
if any_required_check_is_missing:
    gate = NOT_VERIFIED
else if any_required_check_has_deterministic_failure:
    gate = FAILED
else if any_security_or_integrity_gate_failed:
    gate = FAILED
else if any_required_test_is_flaky:
    gate = UNSTABLE
else if only_approved_transient_failures_recovered_within_budget:
    gate = RECOVERED
else:
    gate = PASSED
~~~

The `RECOVERED` state should be displayed distinctly or accompanied by metadata, never folded invisibly into `PASSED_FIRST_ATTEMPT`. An organization may allow `RECOVERED` to proceed per policy while retaining the data to spot instability trends.

## 10. Example: A Test Fails Once and Then Passes

A pull request modifies fee calculation logic. The contract test runs the first time and reports that the total amount differs from the expected value. The developer clicks retry; the second run passes.

If the pipeline only checks the final attempt, the pull request might get merged. However, the team does not know whether the first run was:

- A regression caused by stale data or leftover state.
- A race condition when multiple tests write data concurrently.
- A test dependent on execution order.
- A real bug in fee calculation that only triggers on a certain dataset.
- An infrastructure error preventing the test from reading a dependency or service.

The proper process is to retain both attempts and compare inputs, runners, data, and logs. If a transient infrastructure fault is confirmed, record `recovered` per retry policy. If the same test produces different results under equivalent conditions, mark it flaky and investigate. If regression evidence exists, fix the code and require the test to pass stably.

Because the test involves money calculation, the team must treat risk as high. Never use quarantine or retry to bypass financial contract checks without approved compensating verification.

## 11. Measure Quality Instead of Just Counting Green Pipelines

Tracking only the final pipeline success rate can inadvertently incentivize retries and ignoring failures. Add metrics reflecting what happens before the pipeline finishes.

| Metric | How to Calculate or Read | Meaning |
|---|---|---|
| First-attempt failure rate | Jobs failing on attempt 1 / total jobs run | Early failure signal |
| Retry rate | Jobs with at least one retry / total jobs | Reliance on retries |
| Pass-after-retry rate | Jobs failing first but passing after retry / retried jobs | Recovery rate after retry |
| Flaky test rate | Tests with inconsistent outcomes / tests observed across sufficient repeats | Test suite reliability |
| Retry amplification | Total attempts / logical jobs | Execution cost caused by retries |
| Quarantine age | Duration tests stay in quarantine | Quality debt backlog |
| Skipped required checks | Required gates not run or skipped | Verification gaps |
| Escaped defect rate | Post-merge/release defects linked to bypassed gates | Impact of weak quality gates |

For instance, if 1,000 jobs have 100 fail on the first run and 70 pass after retry, the final pass rate looks very good. Yet the first-attempt failure rate is 10%, and those 70 jobs need classification to reveal how many were truly transient infra faults versus flakiness or regressions.

Agree on denominators, time windows, and how attempts are grouped. Do not count every attempt in the denominator as if it were an independent logical job, as that distorts ratios.

Never use metrics to rank individuals or pressure teams into hitting green rates at all costs. The purpose is to identify which parts of the system generate recurring failures and verify whether improvements actually work.

## 12. Assign Ownership So Failures Are Not Abandoned

When a test fails, whoever detects it should provide enough evidence for the owning team to inspect. The owner of the test or related component is responsible for investigating and fixing it. The platform team assists when signs point to runners, networking, registries, or CI configuration.

A practical ownership split:

- **Pull request author:** reads the initial failure, performs initial triage, and never bypasses required checks unilaterally.
- **Test owner:** checks test data, assertions, isolation, timeouts, and determinism.
- **Platform/CI owner:** checks runners, queues, networking, caches, and retry mechanics.
- **Release owner:** evaluates the impact of `unstable`, `quarantine`, or exceptions prior to release.
- **Security owner:** decides handling when scans, signatures, policies, or secret verification cannot complete.

Every flaky test needs a specific owner and ticket. A generic group name is not an accountable owner capable of driving resolution to completion.

## 13. Pitfalls to Avoid

| Behavior | Why It Is Dangerous | Change to Make |
|---|---|---|
| Retrying until pass | Turns instability into false green | Cap attempts and store every attempt |
| Ignoring long-flaky tests | Loses protection on critical contracts | Time-bound quarantine, owner, and compensating check |
| Using `continue-on-error` on mandatory gates | Pipeline goes green even when checks fail | Separate required and informational jobs |
| Treating pass-after-retry as a clean pass | Hides reliability signals | Record `recovered` or `unstable` state |
| Retrying config and auth failures | Wastes resources without fixing the failing condition | Fix root cause before re-running |
| Retrying non-idempotent deployments | Can create duplicate releases or side effects | Reconcile state and enforce idempotency |
| Measuring only final success rate | Misses initial failures and retry cost | Track first-attempt failure, retry, and flaky rates |
| Quarantining without an expiration date | Exceptions become permanent | Track age and alert when overdue |
| Checking only jobs that ran | Overlooks skipped gates | Report unexecuted required checks |

## 14. Checklist Before Accepting a Green Pipeline

- [ ] All required checks ran, or were skipped under an exception with a clear owner and rationale.
- [ ] No deterministic failures were retried merely waiting for a pass.
- [ ] Every retry has explicit conditions, attempt caps, and total time limits.
- [ ] The initial failure and all subsequent attempts are preserved.
- [ ] Pass-after-retry results are distinguished from first-attempt passes.
- [ ] Flaky tests have an owner, ticket, quarantine expiration, and compensating verification.
- [ ] Security, signature, provenance, and policy gates are never skipped to reach green.
- [ ] Operations with side effects are checked for idempotency before retrying.
- [ ] Pipeline reports clearly distinguish `failed`, `recovered`, `flaky`, `quarantined`, and `skipped`.
- [ ] Quality gates have decision rules for pull requests and production releases.
- [ ] Metrics track first-attempt failure, retry rate, and quarantine age.
- [ ] Exceptions are reviewed and removed once root causes are resolved.

## 15. Closing Principle

A green status is trustworthy only when it reflects checks that genuinely executed and their preserved evidence. Ignoring a failure or retrying indefinitely can make a pipeline finish, yet it neither makes software safer nor makes tests more reliable.

When facing a failure, preserve evidence, classify the error, apply bounded retries only when justified, investigate flaky tests, and keep quality gates honest. A pipeline must sometimes stay red to protect release decisions. That is valuable feedback: it shows the team exactly what needs fixing before risk travels any further.

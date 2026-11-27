# Selecting a Rerun Scope While Preserving Valid Verification Evidence

A CI/CD pipeline can run through many steps: checking out source code, installing dependencies, building artifacts, running unit tests, running integration tests, executing security checks, publishing, and deploying. If a job fails due to a runner disconnect or a temporarily unavailable external service, teams often want to re-run it to finish the pipeline.

However, re-running the entire pipeline is not always necessary or safe. It might build a new artifact, repeat side effects, create duplicate releases, redeploy an already working version, or discard context from checks that already passed. Conversely, re-running only a single job may also be insufficient if source code, dependencies, configuration, or the environment changed since the previous run.

The key question is not merely "which job failed?" but also: **which verification evidence remains valid for the exact commit and artifact under consideration?**

This article explains how to choose a rerun scope in CI/CD, distinguish automatic retries from intentional reruns, determine conditions for reusing passed results, handle flaky tests and infrastructure failures, and avoid repeating side effects during publish/deploy. The goal is to recover the pipeline with just enough work while preserving a traceable chain of evidence.

## 1. Rerun is a decision about scope and evidence

A pipeline typically follows a dependency graph. For example:

~~~text
                 Source commit
                      |
                      v
                    Build
                      |
             +--------+--------+
             |                 |
             v                 v
          Unit test       Static analysis
             |                 |
             +--------+--------+
                      |
                      v
                Integration test
                      |
                      v
                 Package artifact
                      |
                      v
                Security / scan
                      |
                      v
                   Publish
                      |
                      v
                    Deploy
                      |
                      v
                Post-deploy verify
~~~

When a step fails, preceding steps may still remain valid. If an integration test fails because the test database temporarily went down, there is no need to rebuild source or re-run static analysis. However, if the commit changed, unit test and static analysis results from the old commit do not prove the new commit is valid.

Therefore, reruns must consider two dimensions:

1. **Execution scope:** which step, job, stage, workflow, or full pipeline needs to run again?
2. **Evidence scope:** which build, test, scan, and artifact results still prove properties of the current source/artifact?

Do not select a scope solely based on whatever button the CI platform provides. Decide based on dependency relationships and evidence validity.

## 2. Distinguishing automatic retry, rerun, and resume

These concepts are often lumped together as "re-running," yet their purposes differ.

| Concept | Purpose | Example |
|---|---|---|
| Retry | Re-attempt an operation after a failure deemed transient | Calling a registry again on HTTP 503 |
| Rerun | Re-launch a completed job or pipeline scope | Re-running `integration-test` for the same commit |
| Resume | Continue a long-running process from saved state/checkpoint | Resuming a backfill from the last committed batch |
| Rebuild | Produce a new artifact from source and build inputs | Rebuilding after updating a dependency |
| Re-deploy | Re-execute a deployment operation to an environment | Continuing a rollout for the same image digest |
| Revert/rollback | Return the system to a previous version or state | Shifting traffic back to the prior artifact |

Retries typically happen inside a job. A rerun may create a new attempt for a job or workflow. Resume leverages saved progress. Rebuild creates a new output and therefore requires fresh evidence. Re-deploy can cause side effects, so it requires idempotency or state lookup mechanisms.

Using the right term helps operators understand what action will happen and which evidence can be preserved.

## 3. Possible rerun scopes

### Step or command

Re-running a command within the same job can be useful when the runner is still alive and the prior operation definitely produced no side effects—for example, refetching metadata or re-running a pure read-only check.

The risk is that shell state, temporary files, background processes, or mutated workspace data can make the second run differ from the first. Only retry a step when workspace state and side effects are well understood.

### Job

The job is the most common rerun unit—for example, re-running `integration-test` while keeping prior build and unit-test results.

This is appropriate when:

- The source commit remains the exact same SHA.
- Input artifacts carry the same digest as the previous run.
- Dependencies and toolchains have not changed.
- The job does not rely on lost ephemeral state.
- Results from other jobs are still stored by the platform and tied to the right run/commit.
- No environment change has invalidated the prior results.

### Stage

A stage groups multiple jobs in the same phase. Re-running a stage may be needed when several jobs rely on a shared service or when artifacts from the preceding stage expired.

However, identify which jobs cause side effects and which only verify. Re-running an entire stage can publish or write data multiple times if the stage mixes responsibilities.

### Workflow or pipeline

Re-running an entire workflow/pipeline can make sense when:

- Runners or workspaces across multiple jobs failed.
- Intermediate artifacts are gone or expired.
- Pipeline configuration changed.
- Dependent jobs cannot reuse prior results.
- You want to verify the entire flow on a new revision.

This is usually the most expensive scope and can repeat side effects. Before choosing it, check whether the pipeline builds new artifacts, publishes packages, creates releases, or deploys.

### Deployment operation

A deployment operation should be tracked by an operation ID or release identity. If a deploy job times out, the next run should query the previous deployment's status and continue/reconcile the same operation instead of creating an unrelated new deployment.

## 4. What does verification evidence consist of?

A single green checkmark is not enough to prove a commit or artifact has been verified. Evidence should be bound to concrete inputs.

| Evidence | Identifiers to record | Property proven |
|---|---|---|
| Build | Commit SHA, build inputs, toolchain, artifact digest | Artifact was produced from defined inputs |
| Unit test | Commit SHA, test suite/version, test report | Executed tests passed on specific source |
| Integration test | Commit/artifact digest, service version, environment/config revision | Components interacted properly in a defined environment |
| Static analysis | Commit SHA, rule set, analyzer version | Source meets a specific analysis rule set |
| Dependency scan | Lockfile hash, database/rule version, scanner version | Dependencies checked against specific scanner data |
| Container scan | Image digest, scanner version, policy version | Specific image satisfies scan policy |
| Publish | Artifact digest, registry/repository, signature/provenance | Artifact published with verifiable identity |
| Deploy | Artifact digest, environment, deployment operation ID | Specific version deployed to environment |
| Post-deploy verification | Deployment ID, timestamp, environment, test/check version | Post-deployment state verified |

Evidence needs enough metadata to answer: what was checked, on which version, with which tool and policy, in which environment, at what time, and with what outcome?

## 5. When do passed results remain valid?

A verification result can be reused if the inputs it depends on remain identical and policy permits reuse.

### Unchanged source commit

Unit tests passing on commit A do not prove commit B passes, even if B only changed one line. The commit SHA is the exact identifier of the source tree. If source changes, at least source-dependent checks must re-run or be backed by an explicitly accepted impact analysis mechanism.

Never use a green status from a previous commit to satisfy required checks for a new commit.

### Unchanged artifact digest

If integration tests and security scans ran on image digest D, that evidence can be reused when deploying the exact digest D, provided the environment and relevant policies have not changed.

If a rebuild produces digest D2—even if the tag remains `latest` or the version text looks identical—never automatically attribute D's scan results to D2. Tags can move; a new digest is the proper immutable content identifier.

### Unchanged dependencies and toolchain

Changes to lockfiles, build plugins, JDK, compiler flags, or base images can alter the resulting artifact. When these change, builds and dependent tests must be re-evaluated.

Even when the source SHA is unchanged, different build inputs can produce a different artifact. Record dependency lock hashes, toolchain versions, and build configurations.

### Unchanged configuration and environment

Integration tests depend on database versions, service contracts, feature flags, network policies, and config revisions. If these factors change, old results may no longer represent the current environment.

For instance, tests passing on PostgreSQL 15 do not automatically prove compatibility with PostgreSQL 17. Staging results captured before rotating credentials or altering schemas are not necessarily sufficient for subsequent deployments either.

### Unchanged policy and scanner data

Security scans may depend on rule database versions, vulnerability feeds, and policy thresholds. An image scanned last week may need re-scanning if the vulnerability database receives critical updates or policy requires scanning close to release time.

Evidence validity can therefore have an expiration window.

## 6. Decision matrix for selecting rerun scope

| Cause or change | Typically appropriate scope | Evidence that can be preserved |
|---|---|---|
| Runner loses network while fetching dependencies, no build output yet | Retry step or build job | Independent results from other jobs on the same commit |
| Integration test service temporarily down | Rerun `integration-test` | Build, unit tests, and static analysis if inputs are unchanged |
| Unit test fails due to code bug | Fix source, push new commit, re-run source-dependent checks | Never reuse old commit's passing tests for the new commit |
| Scanner service temporarily errors, artifact digest unchanged | Rerun scan job | Build and tests on the same digest |
| Lockfile or toolchain changed | Rebuild and re-run dependent checks | Checks independent of changed inputs, if policy allows |
| Artifact expired or deleted | Rebuild/repackage, re-verify artifact | Source tests may be kept if source and inputs are unchanged; artifact evidence must bind to new digest |
| Deploy job times out after submitting request | Query operation and resume/reconcile | Valid build, scan, and approvals for the exact digest |
| Staging environment changed | Rerun relevant integration/post-deploy checks | Unit tests on source may be kept |
| Pipeline YAML changed | Re-run jobs affected by workflow logic; may need full pipeline | Keep only evidence independent of changed logic |
| New commit pushed | Run checks for the new commit | Never treat old SHA checks as checks for the new SHA |
| Flaky test fails first then passes on retry | Investigate and record both attempts | Never erase failure history; pass status must follow retry policy |
| Release publish succeeded but response was lost | Query package by digest/version | Do not publish a second time if matching artifact already exists |

This is a scoping guide, not an automatic rule for every platform. Actual dependency graphs and required check policies determine which jobs must re-run.

## 7. Decision workflow before clicking rerun

Before re-running, answer these in sequence:

1. At which step did the job fail, and is the failure transient?
2. Is the source SHA still identical to the original run?
3. Do input artifacts still exist, and do their digests match?
4. Have the toolchain, dependency lockfile, or config revision changed?
5. Which side effects did the job already produce before failing?
6. Which artifacts, reports, or outputs from upstream jobs does this job depend on?
7. Is evidence from already-passed jobs still retained by the platform and bound to the right commit/run?
8. Could retrying the job overwrite or duplicate data?
9. If the job is deploy/publish, can the operation status be queried first?
10. After the rerun, which required checks and release records must be verified?

If it is unclear whether an operation happened, do not create a new operation just because the job reported a timeout. Query status or reconcile first.

## 8. Automatic retries are only for recoverable failures

Automatic retries help handle short-lived errors without operator intervention. However, retries cannot fix code bugs, wrong test assertions, missing permissions, or invalid configurations.

| Failure group | Example | Handling approach |
|---|---|---|
| Transient infrastructure | Network reset, runner host unavailable | Bounded retry |
| Rate limit | HTTP 429 | Honor `Retry-After` |
| Temporary service failure | HTTP 502/503/504 | Backoff and retry if operation is safe |
| Resource contention | Lock busy, queue full | Wait or retry within budget |
| Authentication/authorization | HTTP 401/403 | Stop and fix identity/policy |
| Validation/configuration | Schema error, missing required variable | Stop; do not retry same input |
| Test assertion failure | Expected differs from actual | Investigate code/test; do not retry for green |
| Security policy failure | Vulnerabilities exceed threshold | Remediate finding or request exception via process |
| Unknown outcome | Timeout after sending side effect | Query state before resubmitting |

Do not classify every non-zero exit code as transient. Jobs should emit meaningful error types or exit codes so retry policies can decide accurately.

## 9. Exponential backoff, jitter, and retry budget

When a service is temporarily unavailable, retrying immediately can increase load and prolong the outage.

Exponential backoff increases wait duration across attempts:

~~~text
delay = min(max_delay, base_delay * 2^attempt)
wait  = random(0, delay)
~~~

Jitter introduces randomness so multiple runners do not retry at the exact same instant. For example, base delay 2 seconds, max delay 60 seconds, up to 4 retries. Values should match SLAs and target system guidance.

### Retry budget

A retry budget caps the number of attempts or total retry duration for an operation:

- Max attempts.
- Max elapsed time.
- Request timeout.
- Backoff cap.
- Honor `Retry-After`.
- Stop immediately on terminal errors.
- Record `UNKNOWN` status when outcome cannot be determined.

If an HTTP client retries 3 times, an SDK retries 3 times, and a CI job retries 3 times, one operation can generate 27 requests. Layers should share a deadline or retry budget to prevent amplification.

### Circuit breaker

A circuit breaker prevents callers from hammering a failing dependency. It typically has three states:

- **Closed:** requests are allowed through; error counters are tracked.
- **Open:** once errors exceed a threshold, new requests fail fast for a cooldown period.
- **Half-open:** after cooldown, allow a few probe requests; if the dependency recovered, close the circuit; if still failing, reopen.

In CI, circuit breakers help when many jobs share a registry, test environment, or common service. They prevent retry storms and return clear errors so pipelines can be retried later. Circuit breakers do not turn an unexecuted check into a pass and do not replace retry budgets or side-effect status checks.

### Never retry test assertions to turn failures into passes

A failed test assertion signals something about software behavior or test quality. Retries can help diagnose flaky tests, but the pipeline must retain the failure history and follow explicit policy. Never turn a failed test into a pass simply by running it until a green attempt occurs.

## 10. Flaky tests and multi-attempt evidence

A flaky test can yield different outcomes when re-run on the same commit under supposedly equivalent conditions.

Common causes:

- Time or timezone dependencies.
- Shared data between tests.
- Parallel test execution without resource isolation.
- Unstable network or external services.
- Race conditions.
- Test ordering or leftover state.
- Overly tight timeouts.
- Incomplete cleanup.

### Recording results per attempt

A thorough report should distinguish:

| Attribute | Meaning |
|---|---|
| Logical test/job ID | Logical identifier of the test or job |
| Attempt number | Which execution attempt this is |
| Commit SHA | Source under test |
| Environment | Execution environment |
| Started/finished time | Execution window |
| Initial result | Outcome of the first attempt |
| Retry result | Outcomes of retry attempts |
| Final policy result | Outcome per pipeline rules |
| Failure reason | Cause or failure classification |

If the first attempt fails and the second passes, history must show both. Policy may allow the pipeline to proceed under flaky retry rules, but the test must not be recorded as stable like a consistently passing test.

### Controlled quarantine

If a severely flaky test blocks pipelines, the team may temporarily quarantine it. Every quarantined test needs an owner, reason, ticket, expiration date, and dedicated reporting. A quarantined test should not count as verified behavioral proof.

## 11. Keeping links intact between commit, artifact, and test results

A pipeline can have many runs on the same branch. Storing only branch names or tags risks attributing an older run's results to newer source.

Bind every piece of evidence to:

- Repository and commit SHA.
- Workflow run ID and attempt.
- Artifact name and digest.
- Build toolchain and dependency lock hash.
- Test suite and report ID.
- Environment/config revision.
- Scanner and policy version.
- Timestamp and outcome status.

Example evidence manifest:

~~~json
{
  "repository": "acme/order-service",
  "commit": "a1b2c3d4...",
  "workflowRun": "run-4812",
  "artifact": {
    "name": "order-service",
    "digest": "sha256:..."
  },
  "checks": {
    "unitTest": "passed",
    "integrationTest": "passed",
    "dependencyScan": "passed"
  },
  "toolchain": {
    "jdk": "21",
    "gradle": "8.x"
  }
}
~~~

This structure is illustrative. In real systems, manifests must be generated from trusted sources, signed or backed by provenance as needed, and never allow untrusted PR jobs to self-assert passing results.

## 12. Artifacts and caches during reruns

Re-running a job may require artifacts from an earlier job. Distinguish immutable output artifacts from speed-up caches.

### Artifacts

Artifacts are outputs stored for downstream jobs or reviewers—such as JARs, container images, test reports, or scan reports.

When re-running:

- Verify the artifact belongs to the right commit and run.
- Verify its digest before using it.
- Check that the artifact is still within its retention window.
- Never use an untrusted PR artifact for a release just because filenames match.
- If rebuilding creates a new digest, generate a fresh set of evidence for that artifact.

If the old artifact is gone, a rebuild may be required. In that case, do not assume the new artifact is byte-for-byte identical unless the build is reproducible; record the new digest and re-run artifact-dependent checks.

### Caches

Caches exist for speed, not verification evidence. Caches can expire, mutate, or become incompatible with new inputs.

If a cache is corrupted, clear the relevant cache scope and re-run the job. Ensure caches never store secrets and caches from untrusted contexts are never fed into trusted inputs.

Never treat a cache hit as proof that dependencies were verified. Dependencies require lockfiles, checksums, or dedicated verification mechanisms.

## 13. Selecting reruns from the dependency graph

If job B consumes outputs from job A, whenever A changes or A's output is regenerated, determine whether B must run again.

Example:

~~~text
                 build
                   |
             artifact digest D1
                   |
          +--------+---------+
          |                  |
          v                  v
       unit test       container scan
          |                  |
          +--------+---------+
                   |
                   v
            integration test
                   |
                   v
                publish
~~~

If `integration-test` fails due to the database environment, you can re-run `integration-test` against artifact D1. Unit tests and container scans can still be kept if their inputs and policies did not change.

If a rebuild yields digest D2, checks performed on D1 do not automatically apply to D2. Jobs depending on the artifact—such as container scan and integration tests—must re-run.

If only a scan policy changed, re-running the scanner against the existing digest may suffice. Rebuilding source is unnecessary if the scanner can read the existing artifact and policy does not require a fresh build.

### Change impact analysis

You can describe each job by its input set:

- Build depends on source, lockfile, toolchain, and build config.
- Unit tests depend on source, test code, and test runtime.
- Integration tests depend on artifact, service versions, and environment config.
- Scans depend on artifact, scanner/rule database, and policy.
- Deploy depends on artifact digest, environment, and deployment config.

When an input changes, only evidence depending on that input needs to be invalidated. This underpins incremental CI, though it must be configured and reviewed carefully to avoid missing hidden dependencies.

## 14. GitHub Actions example: re-running failed jobs

GitHub Actions supports re-running failed jobs or re-running the entire workflow depending on operator action and repository permissions. Exact menu labels may vary by platform UI.

With independent jobs, a pipeline can be structured like this:

~~~yaml
name: verify

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./gradlew --no-daemon assemble
      - uses: actions/upload-artifact@v4
        with:
          name: application-package
          path: build/libs/*.jar

  unit-test:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./gradlew --no-daemon test

  integration-test:
    needs: build
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: artifacts
      - run: ./scripts/run-integration-tests.sh
~~~

This example only illustrates the job graph. The integration test script reads the package from `artifacts`; in production usage, verify the package digest and initialize test services at pinned versions.

If `integration-test` fails because the test database was temporarily unavailable, you can rerun that job as long as the build artifact still exists, matches the commit, and has not expired. If the `build` job re-runs and produces a different package, `integration-test` must consume the new artifact and old results no longer apply to the new artifact.

### Never use reruns to fix source issues

If unit tests fail due to an assertion or logic error, fix the code, create a new commit, and run checks on the new SHA. Re-running the same commit may help identify flaky tests, but it is no substitute for fixing the defect.

## 15. GitLab CI example: conditional retry

GitLab CI supports configuring retries for specific failure types. You can limit max retries and narrow eligible failure conditions.

Example:

~~~yaml
integration_test:
  stage: test
  script:
    - ./gradlew --no-daemon integrationTest
  retry:
    max: 2
    when:
      - runner_system_failure
      - stuck_or_timeout_failure
~~~

This configuration illustrates retrying runner errors or timeouts. Verify the supported retry condition names for your GitLab version. Never add code or assertion failure categories to this list just to get a green pipeline.

A job may retry multiple times; reports should retain attempts and per-attempt outcomes. If a retry already created artifacts or side effects, the job must handle idempotency or cleanup before running again.

### Retries do not make side effects safe automatically

If a job script sends messages, creates releases, or writes data, GitLab job retries can repeat those side effects. Design idempotency keys, state checks, or split side-effect steps into separate gated jobs.

## 16. Re-running jobs with side effects: publish and deploy

Builds and tests can generally re-run safely when inputs are immutable. Publish and deploy mutate external state, so they require extra care.

### Publishing artifacts

If a registry accepted a package but the response was lost, the job may fail even though the package already exists.

Before publishing again:

1. Identify the package name/version and digest.
2. Query the registry.
3. If the package exists and the digest matches, record the publish as completed.
4. If the package exists with a different digest, stop and handle the conflict.
5. If it does not exist yet, publish according to policy.
6. Record the registry location and digest.

Never overwrite an immutable version with different content just because of a rerun.

### Deploying

If a deploy job times out after sending a request, query the deployment operation or workload status. If the exact artifact digest is already running, proceed to verification. If a rollout is underway, continue monitoring. If it was never accepted and the operation is idempotent, resubmit with the same operation identity.

Never create a new deployment or re-run migrations solely because the CI job missed a response.

### Separating verification jobs from side-effect jobs

Test/scan jobs should not hold publish/deploy permissions. Publish/deploy jobs should run only once mandatory evidence has passed and consume the approved artifact digest. Separating permissions prevents verification reruns from accidentally repeating release side effects.

## 17. Approvals and required checks during reruns

A release may require approvals from reviewers, security, or environment owners. Reruns must preserve the link between approvals and the approved subject.

Approvals should bind to:

- Commit SHA.
- Artifact digest.
- Target environment.
- Release version.
- Relevant configuration changes.
- Timestamp and approver identity.

If the artifact digest changes after approval, determine whether policy requires re-approval. Never reuse an approval from an older artifact for a new artifact merely because the version string matches.

### Required checks

Required checks must reflect the exact commit being merged. When a new commit is pushed, statuses from an earlier commit do not replace required checks for the new commit.

When re-running a job, verify that the final status reports to the right check context and SHA. Never use optional jobs or skipped statuses to substitute for required jobs.

### Audited manual reruns

Manual reruns should record the requester, reason, scope, commit/artifact, and attempt. This distinguishes automated retries from operator actions and supports incident investigation.

## 18. Evidence expiration policies

Not all evidence stays valid indefinitely.

Examples:

- Dependency scans must re-run when vulnerability databases update or policy dictates.
- Integration tests must re-run if the environment or dependent services change.
- Production approvals may expire after a set window.
- Artifacts may be purged under retention policies.
- Certificates or signatures may expire or be revoked.
- Performance test results may stop being representative after infrastructure configuration changes.

Each evidence type should have a freshness policy:

| Evidence | Common invalidation triggers |
|---|---|
| Unit test | Source/test inputs change |
| Build | Source, dependency, toolchain, or build config changes |
| Integration test | Artifact, service version, or environment changes |
| Security scan | Artifact or scanner/policy data changes per policy |
| Approval | Artifact, environment, scope, or approval window expires |
| Post-deploy verification | New deployment or runtime state changes |
| Performance test | Workload, topology, or capacity changes significantly |

Freshness policies should be defined by quality/security owners rather than applying one arbitrary TTL to every evidence type.

## 19. Retaining rerun history and audit trails

A pipeline can have multiple attempts for the same commit. Keep history to see which attempt failed, which passed, and why.

Details to capture:

- Pipeline/workflow run ID.
- Job ID and attempt number.
- Commit SHA.
- Artifact digest.
- Trigger source: push, pull request, schedule, manual rerun.
- Requester of manual rerun, if applicable.
- Failure classification.
- Retry policy and attempt count.
- Timestamps per attempt.
- Environment/config revision.
- Reused artifacts/reports.
- Final outcome and acceptance rationale.

Never delete logs from failed attempts when a subsequent attempt passes. A fail-then-pass history reveals flaky tests, infrastructure issues, or environment quality problems.

### Useful dashboards

Track metrics such as:

- First-pass pipeline success rate.
- Percentage of jobs requiring retries.
- Retry success rate.
- Flaky test rate.
- Manual reruns per repository/team.
- Pipeline duration including reruns.
- Duplicate publish/deploy invocation count.
- Evidence expirations prior to release.
- Passing pipelines containing skipped or quarantined jobs.

These metrics help uncover root causes instead of normalizing reruns as routine workarounds needing no investigation.

## 20. Operational runbook for pipeline failures

A simple runbook:

1. Open the run and find the first failing job, not just the last cancelled job.
2. Read the logs and classify the error: transient, code/test, config, permission, policy, or unknown outcome.
3. Confirm the commit SHA and artifact digest.
4. Check whether passed jobs still share identical inputs and remain within retention.
5. Check dependencies of the failed job and artifacts required for a rerun.
6. Determine whether the job has side effects.
7. If transient, retry the job within the retry budget.
8. If code/test error, fix the source and push a new commit.
9. If build inputs changed, rebuild and re-run dependent checks.
10. If deploy/publish outcome is unknown, query the operation/registry before resubmitting.
11. Confirm required checks, approvals, and provenance match the commit/artifact.
12. Record the rerun reason and final result in the audit trail.

If you cannot prove prior evidence is still valid, re-run the necessary checks. If side effects are uncertain, reconcile before issuing a new operation.

## 21. Anti-patterns to avoid

| Anti-pattern | Consequence | Better approach |
|---|---|---|
| Re-running the entire pipeline for every failure | Wastes time and repeats side effects | Scope reruns via the dependency graph |
| Carrying over green checks from an old commit to a new commit | Evidence does not cover current source | Bind checks strictly to commit SHA |
| Using mutable tags instead of digests | May verify one image but deploy another | Bind evidence to immutable digests |
| Retrying test assertions until they pass | Hides bugs or flaky tests | Store every attempt and classify |
| Treating cache hits as build/test proof | Caches do not prove correctness | Use identified reports and provenance |
| Re-running publish without checking if registry received it | Creates duplicate packages/versions or conflicts | Query by version and digest |
| Re-running deploy after timeout without reconciling | Causes overlapping deployments | Query operation and observed state |
| Reusing old approvals for a new artifact | New release lacks valid approval | Bind approvals to digest |
| Ignoring skipped/allowed-failure jobs | Green pipeline lacks mandatory checks | Review statuses and policy |
| Deleting failed attempt logs | Loses visibility into flakiness and infra failures | Keep full audit trail |
| Re-running a job without its dependency artifact | Job runs with missing files or wrong run data | Verify artifact lineage and retention |
| Unlimited retries | Extends incidents and amplifies load | Retry budget, deadlines, and circuit breakers |

## 22. Checklist for selecting a rerun scope

### Verify inputs

- [ ] Is the run's commit SHA still the revision targeted for release?
- [ ] Is the artifact digest identified and still present?
- [ ] Did lockfiles, toolchains, or build config change?
- [ ] Did environment/config revisions change?
- [ ] Are scanner/policy data still within the freshness window?

### Choose scope

- [ ] Is the failure classified as transient?
- [ ] Can a single independent step/job be retried safely?
- [ ] Do downstream dependent jobs need to re-run?
- [ ] Can input artifacts be reused safely?
- [ ] Will re-running the stage/workflow repeat publish, deploy, or migrations?
- [ ] Is a rebuild needed instead of a rerun?

### Preserve valid evidence

- [ ] Test reports are bound to the right commit SHA.
- [ ] Scan reports are bound to the right artifact digest and policy version.
- [ ] Integration results are bound to environment/service versions.
- [ ] Required checks reflect the exact commit being merged.
- [ ] Approvals are bound to the deployed artifact and environment.
- [ ] Skipped/quarantined jobs are surfaced clearly.
- [ ] Attempt history is preserved.

### Control side effects

- [ ] Publish checks package/version/digest before repeating.
- [ ] Deploy uses an operation ID or reconciliation mechanism.
- [ ] Migrations and data jobs have proper idempotency/checkpoints.
- [ ] Retries have caps and backoff.
- [ ] Manual rerun requester and reason are audited.

## Conclusion

Re-running a pipeline is a decision about both execution scope and evidence validity. Bind builds, tests, scans, approvals, and deployments to their respective commit SHAs, artifact digests, toolchains, policies, and environments. When failures are transient, re-running the right job preserves independent passing results; when source or build inputs change, dependent checks must re-run; when publish or deploy outcomes are unclear, query state before repeating side effects. Retain history across all attempts and advance releases only when required checks, approvals, and provenance remain valid for the exact artifact being shipped.

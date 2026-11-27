# Optimizing Pipeline Duration While Ignoring Wait Time and Reliability

## Learning Objectives

After this lesson, learners can:

- Explain why reducing job execution time does not necessarily change software delivery lead time.
- Distinguish elapsed time, execution time, queue time, dependency wait, approval wait, and environment wait time.
- Analyze the end-to-end time from when a change is created until the release is verified.
- Identify hidden wait times masked in pipeline dashboards.
- Evaluate the reliability of pipelines, test suites, runners, and dependent services.
- Use percentiles, flow efficiency, critical path, and Little's Law to find bottlenecks.
- Choose improvements grounded in baselines and guardrails, avoiding cutting duration by dropping tests or lowering quality.
- Design dashboards and improvement workflows that balance speed, reliability, and software delivery outcomes.

## 1. Mistake: Looking Only at Job Execution Time

A pipeline can be optimized from 20 minutes down to 8 minutes, yet developers still wait hours or days for changes to reach production. The reason is that job execution time is only one slice of overall software delivery time.

Examples:

- Build and test jobs take only 8 minutes, but waiting for a runner takes 12 minutes.
- Pull requests wait two days for a reviewer.
- After merging, releases are only allowed to run during a Friday night change window.
- Deployment finishes, yet waits for an operator's confirmation.
- Flaky tests force the pipeline to retry multiple times.
- A shared integration test environment is occupied by another pipeline.
- Unstable external scanners or registries force jobs to wait or re-run.

If a dashboard only displays job execution time, these wait intervals disappear from the team's view. As a result, the team optimizes what is easy to measure without addressing what actually keeps users waiting.

Distinguish two questions:

1. **How fast does the pipeline execute?** This is a question about job duration, critical path, runners, and tooling.
2. **How fast and reliably are changes delivered to users?** This is a question about the entire flow from commit, review, testing, approval, release, deployment, to verification.

Optimizing pipeline duration is a valid goal. The mistake arises when treating it as a proxy for software delivery speed while ignoring wait times and reliability.

## 2. Breaking Down End-to-End Time

To understand how long a change takes, clearly define the start and end points and break the elapsed interval into stages.

A reference model:

~~~text
Change created
    |
    v
Review wait
    |
    v
Review and revision
    |
    v
CI queue wait
    |
    v
Build / test / scan execution
    |
    v
Dependency or environment wait
    |
    v
Approval / release wait
    |
    v
Deployment execution
    |
    v
Post-deploy observation and verification
    |
    v
Verified release
~~~

Total time can be broken down as follows:

| Component | Meaning | Example |
|---|---|---|
| Review wait | Time spent waiting for a reviewer | PR waiting for reviewer |
| Review/rework | Time spent discussing and revising | Review comments, code updates |
| CI queue wait | Job is ready but no runner is available | Runner pool saturated |
| CI execution | Time spent executing build, test, scan | Compile, unit tests |
| Dependency wait | Waiting for another job or workflow | Waiting for artifact, upstream pipeline |
| Environment wait | Waiting for environment or test data | Staging occupied |
| Approval wait | Waiting for a decision or approval | Production approval |
| Release wait | Waiting for release schedule or batch release | Deploying only in change windows |
| Deployment execution | Time spent applying the change | Rollout, migration |
| Verification | Waiting and running post-deploy checks | Smoke tests, canary analysis |

Not every system has all stages. What matters is capturing meaningful wait intervals rather than collapsing them into a single pipeline duration number.

A simple formula:

\[
T_{end-to-end} =
T_{active} + T_{waiting}
\]

Where:

- \(T_{active}\) is time actively spent processing work.
- \(T_{waiting}\) is time spent waiting for people, runners, dependencies, environments, or decisions.

This is a workflow-level breakdown. When multiple jobs run in parallel, you cannot sum every job's execution time to get wall-clock duration. Use the critical path and actual start/end timestamps.

## 3. Distinguishing Different Types of Wait Time

### 3.1. Event and Workflow Initialization Wait

A commit may already be pushed while the workflow has not started because:

- Webhooks arrive delayed or are processed in batches.
- The CI system is overloaded.
- The workflow is throttled by concurrency limits.
- The pipeline is waiting for an upstream workflow.
- Trigger filters did not match or events require manual handling.

If you only measure from when the runner starts, the time beforehand never shows up.

Record timestamps for the source event, workflow creation, and job readiness when provided by the platform.

### 3.2. Runner Queue Wait

The job is ready, yet no suitable runner has been assigned.

Common causes:

- Insufficient runners.
- Runner labels or architectures do not match.
- Concurrency quotas are exhausted.
- Runners are still provisioning or booting.
- A fan-out job burst consumed all capacity.
- Pipeline priority does not match demand.

Adding runners can help, but inspect queues by runner class and workload type. A Linux runner may sit idle while jobs needing Windows or specialized hardware wait.

### 3.3. Dependency Wait

A job can be blocked by dependencies even when runners are available.

Examples:

- Integration tests waiting for service dependencies to start.
- Deploy waiting for artifacts to be published.
- Release waiting for security scan results.
- Downstream pipeline waiting for an upstream pipeline to finish.
- Migration waiting for a preceding schema change.

Dependency wait must be separated from runner queue time. Adding runners will not help if a job is not yet eligible to start.

### 3.4. Environment Wait

Shared environments routinely become bottlenecks:

- Staging is currently used by another team.
- The test database is running migrations.
- A namespace has not been cleaned up yet.
- Test accounts are locked or in use.
- An external sandbox hit its quota.
- Environment provisioning takes a long time.

Wait times can be reduced using ephemeral environments, isolated test data, dedicated namespaces, or bounded queues. However, maintain sufficient parity with production.

### 3.5. Approval and Release Window Wait

A pipeline may pass all checks yet still not be permitted to deploy.

Examples:

- Waiting for product owner sign-off.
- Waiting for a security exception.
- Waiting for a change manager.
- Waiting for the production on-call engineer.
- Waiting for a change window.
- Waiting for a release train batching multiple changes.

Do not blindly delete approvals merely to lower lead time. Identify which approvals genuinely control risk, which repeat the exact same information, and which can be converted into automated policy.

### 3.6. Post-Deployment Verification Wait

A release should not be considered complete the instant the deploy command returns success.

You may need to wait for:

- Readiness across all instances.
- Completion of traffic shifting.
- Canary observation windows.
- Smoke tests.
- Error rate and latency stabilization.
- Queue backlog draining.
- Business transaction verification.

This is intentional waiting to reduce risk. Never strip it out simply because dashboards show a longer pipeline.

## 4. Wait Time and Execution Time Must Be Measured Separately

A useful dashboard should at least separate:

| Metric | Interpretation | Action When Rising |
|---|---|---|
| Event-to-workflow delay | From event to workflow creation | Inspect webhooks and CI control plane |
| Queue time | Job ready until runner starts | Check capacity, labels, and quotas |
| Provisioning time | Time to spin up runner or environment | Optimize images, autoscaling, and provisioning |
| Job execution time | Active job runtime | Profile commands, caching, and workload |
| Dependency wait | Waiting on dependent jobs or workflows | Review DAG and upstream bottlenecks |
| Environment wait | Waiting on environments or test resources | Isolation, ephemeral environments, queuing |
| Approval wait | Waiting on human or policy approval | Clarify owners, SLAs, and suitable automation |
| Deployment time | Actual rollout duration | Inspect strategy, health, and capacity |
| Verification time | Observation and verification duration | Inspect tests, telemetry, and observation windows |

Standardize timestamps and definitions. For example, queue time should start when a job becomes ready, not at workflow creation if the job is still waiting on a dependency.

If timing data is incomplete, record the missing segment explicitly. Never misclassify unknown intervals as execution time or waiting time.

## 5. Reliability Is Part of Speed

A fast pipeline that frequently yields false or unstable results increases total software delivery time.

Forms of unreliability:

- Flaky tests.
- Runner disconnections.
- Dependency repository outages.
- Caches returning incompatible data.
- Unstable external test services.
- Scanner timeouts.
- Artifact upload/download failures.
- Non-idempotent migrations.
- Partial deployment successes.
- Missing reports or reports from stale runs.

Every retry consumes time and can erode trust in the pipeline. If a team grows accustomed to retrying until green, real defects can be masked.

Measure not only the final run, but also attempt history:

- First-attempt success rate.
- Retry rate.
- Flaky test rate.
- Infrastructure failure rate.
- Tool/service availability.
- Artifact publication failure rate.
- Deployment success and partial deployment rates.
- Quality gate false-positive/false-negative rates where determinable.

Predictable, reliable speed generally outperforms a very fast run that demands multiple attempts.

## 6. Retries Can Make a Pipeline Look Artificially Faster or Healthier

Suppose a test suite has a 90% first-attempt pass rate, yet the pipeline automatically retries up to three times and reports only the final status. If the second attempt passes, the dashboard may record success.

However, the developer still waited for an extra run, and the test suite's reliability remains low.

Distinguish between:

- **First-attempt success:** percentage passing on the initial run.
- **Eventual success:** percentage eventually passing after retries.
- **Retry rate:** percentage of runs or jobs requiring retries.
- **Retry recovery:** percentage of retries that succeed.
- **Flaky failure:** non-reproducible failures under equivalent conditions.
- **Infrastructure failure:** failures caused by runners, networking, or external services.
- **Product failure:** genuine code or application behavior defects.

Reasonable retries for transient errors make systems more resilient. Unlimited retries or retrying every failure class inflates time, load, and hides root causes.

Put in place:

- Classification of retryable errors.
- Limits on retry count.
- Exponential backoff and jitter where appropriate.
- Recording outcomes for every attempt.
- Alerts when retry rates exceed baseline.
- Owners assigned to fix flaky tests or unstable dependencies.

## 7. Do Not Cut Duration by Dropping Tests

An artificial way to speed up pipelines is stripping out slower steps:

- Dropping integration tests.
- Dropping security scans.
- Reducing test cases without risk analysis.
- Disabling flaky tests instead of fixing them.
- Using unverified caches.
- Skipping post-deployment verification.
- Bypassing quality gates when pipelines run slow.
- Running tests on only one module even when changes span multiple modules.

These shortcuts may shrink job duration, yet they drive up defect escapes, incidents, and recovery times.

Instead of dropping checks, optimize execution:

- Run independent tests in parallel.
- Run change-scoped tests quickly while keeping full suites on required gates or schedules.
- Tier tests by criticality and duration.
- Improve test data and environment provisioning.
- Remove duplicate tests with evidence.
- Fix flaky tests.
- Optimize fixtures and dependency startup.
- Use contract tests to catch integration issues early.
- Retain smoke tests and post-deploy verification for critical flows.

If test scope must change, require a risk assessment, owner, and guardrails. Never treat cutting tests as an improvement simply because the pipeline became shorter.

## 8. Critical Path and Parallel Jobs

Pipelines are typically DAGs. Overall elapsed duration is governed by the critical path, not the sum of all job durations.

Example:

~~~mermaid
flowchart TD
    A["Checkout"] --> B["Lint"]
    A --> C["Unit tests"]
    A --> D["Dependency scan"]
    B --> E["Package"]
    C --> E
    D --> E
    E --> F["Integration tests"]
    F --> G["Approval"]
    G --> H["Deploy"]
    H --> I["Post-deploy verification"]
~~~

Lint, unit tests, and dependency scans can run in parallel. However, if integration tests wait on packaging, that dependency cannot be eliminated.

Optimize the critical path by:

- Finding the longest-running job along the critical path.
- Reducing queue wait on critical-path jobs.
- Balancing test shards.
- Avoiding artificial dependencies.
- Caching dependencies safely.
- Provisioning environments before jobs need them.
- Preparing artifacts and test data early.
- Ensuring adequate runner capacity.

Do not scale concurrency infinitely. Too many concurrent jobs can saturate CPU, memory, disk, registries, or external APIs, making every job slower and flakier.

## 9. Little's Law Helps Explain Queues and WIP

Little's Law describes the relationship between average work in the system, throughput, and average cycle time:

\[
L = \lambda W
\]

Where:

- \(L\): average number of work items in the system (WIP).
- \(\lambda\): average throughput, completed items per unit of time.
- \(W\): average time an item spends in the system.

For example, if an average of 20 jobs are waiting or running and the system completes 10 jobs per hour, average time in the system is approximately 2 hours in a steady-state model.

This law does not say increasing WIP automatically increases throughput. When capacity is fixed, pushing more jobs into the queue typically lengthens wait time. When the system is unstable or throughput fluctuates sharply, apply the formula with caution.

Use Little's Law to ask:

- Is WIP rising because more jobs are arriving or because jobs are finishing slower?
- Is throughput constrained by runners or approvals?
- Are long queues caused by excessive fan-out?
- Can we lower WIP by capping runs or breaking changes smaller?

## 10. Percentiles Matter More Than Looking Only at Averages

Pipeline durations typically follow a skewed distribution: many runs are fast while a few are very slow.

Track:

- p50: typical experience.
- p90: slower tail of runs.
- p95: high tail latency.
- p99: useful when volume is large enough to examine rare outliers.
- Mean: useful for total resource sizing, yet easily distorted by outliers.

Example:

| Metric | Before Optimization | After Optimization |
|---|---:|---:|
| Pipeline duration p50 | 12 min | 8 min |
| Pipeline duration p95 | 35 min | 38 min |
| Queue time p50 | 2 min | 1 min |
| Queue time p95 | 18 min | 25 min |
| First-attempt success | 96% | 88% |
| Retry rate | 7% | 19% |

The median improved, yet p95 and reliability degraded. Likely, higher fan-out overloaded the runner pool; some jobs ran faster while others waited longer and retried more often.

Reporting only p50 masks this problem. Inspect full distributions, sample counts, and segments by runner class, repository, workflow type, and peak hours.

## 11. Flow Efficiency: Value-Adding Time vs. Wait Time

Flow efficiency compares active processing time against total elapsed time.

A simple definition:

\[
Flow\ Efficiency =
\frac{Active\ Time}{Total\ Elapsed\ Time}
\times 100\%
\]

For instance, a change takes 5 days from start to verified production:

- 4 hours writing code and tests.
- 2 hours actual code review.
- 1 hour of CI execution.
- The remainder is waiting for reviews, approvals, release windows, and environments.

Flow efficiency under this definition is quite low. That alone does not prove every wait is waste: some waits may be intentional approvals or safe observation windows. Classify waiting time into:

- Necessary waits to reduce risk.
- Waits caused by insufficient capacity.
- Waits caused by dependencies.
- Waits caused by unclear ownership.
- Waits caused by batching or release schedules.
- Waits caused by failures and retries.

The goal is not eliminating all wait time. The goal is cutting non-value-adding waits while keeping necessary controls intact.

## 12. Optimizing Approvals Without Dropping Controls

Approval wait often accounts for a significant share of lead time. However, blindly removing approvals increases risk.

Classify approvals:

- Mandatory approvals by policy or separation of duties.
- Risk-based approvals for changes.
- Approvals duplicating checks already automated.
- Approvals that are merely informational notifications.
- Approvals delayed by missing owners or on-call rotations.

Ways to improve:

- Define primary owners and backups.
- Set response SLAs for approvals.
- Send requests bundled with evidence and a risk summary.
- Auto-approve low-risk changes meeting policy criteria.
- Require human approval only where genuine decisions are made.
- Use protected environments and policy-based approvals.
- Log reasons for rejections or holds.

Never turn approval into a rubber-stamp button. If approvers lack context or cannot verify evidence, the step adds delay without adding safety.

## 13. Optimizing Environments and Dependencies

Shared test or staging environments can make pipelines slow and unstable.

Solutions:

- Spin up ephemeral environments per pull request or run ID.
- Use isolated databases or schemas.
- Seed deterministic, reproducible test data.
- Run test dependencies in containers.
- Cache images and packages safely.
- Health-check readiness before running tests.
- Enforce cleanup by owner and TTL.
- Use contract tests when standing up the full system is unnecessary.
- Cap concurrency to match external sandbox quotas.

Not every environment should be purely ephemeral. Performance testing or production-like integration may require managed shared environments. In those cases, add queuing, scheduling, isolation, and wait-time telemetry.

Ensure test environments maintain enough parity with production on traits that affect outcomes. An overly divergent environment might run fast yet miss real bugs.

## 14. Optimizing Caching and Dependencies Without Sacrificing Correctness

Caching reduces dependency download and build times, yet wrong or unsafe caches make outputs untrustworthy.

Require:

- Cache keys derived from lockfiles, toolchains, OS, and relevant configs.
- Never using caches as the authoritative source for artifacts.
- Verifying dependency checksums or signatures where appropriate.
- Partitioning caches by trust boundary.
- Preventing untrusted jobs from writing caches consumed by trusted release jobs.
- A mechanism to invalidate caches and run clean builds.
- Tracking cache hit rates alongside failure rates or cache corruption.

If a build is only fast with a cache and cannot reproduce cleanly from scratch, the pipeline depends on hidden state. Schedule periodic clean builds or run them on critical releases to verify.

## 15. Reliability Metrics Must Accompany Speed Metrics

A dashboard showing only duration and deployment frequency invites misguided optimization. Add reliability metrics.

| Category | Suggested Metric | Question |
|---|---|---|
| Pipeline reliability | First-attempt success rate | How many runs pass on the first try? |
| Test reliability | Flaky test rate | Do tests produce consistent results? |
| Infrastructure | Runner failure rate | Are runners disrupting workflows? |
| Dependency | External service failure rate | Are registries/scanners/test services stable? |
| Artifact | Publish/verification failure rate | Are artifacts built and verified cleanly? |
| Deployment | Partial/failed deployment rate | Do rollouts finish in the right state? |
| Recovery | Retry/recovery duration | How long does returning to healthy take? |
| Service | SLO, error rate, latency | Is the service stable post-release? |
| Delivery | Change failure rate | Do changes trigger remediation? |

Distinguish product bugs from infrastructure failures. If a registry outage breaks builds, it is still a delivery system incident even though it is not a code bug. Classification directs action to the right owner and fix.

## 16. Balancing Speed and Reliability with Guardrails

Every improvement should pair a primary metric with guardrails.

Examples:

| Improvement | Primary Metric | Guardrail |
|---|---|---|
| Increase runner capacity | Queue time p50/p95 | Cost, utilization, failure rate |
| Parallelize tests | Critical path duration | Flaky rate, resource saturation |
| Cache dependencies | Build duration | Cache corruption, reproducibility |
| Reduce approval wait | Approval wait | Change failure, policy compliance |
| Ephemeral environments | Environment wait | Cost, environment parity, cleanup failures |
| Change-scoped testing | Feedback time | Defect escape, full-suite coverage |
| Increase deploy frequency | Lead time | Change failure, SLO, recovery time |
| Shorten canary window | Release duration | Detection delay, escaped incidents |

Never declare an optimization successful solely because the primary metric dropped. If queue time drops while runner costs multiply and failure rates climb, re-evaluate.

Guardrails expose side effects and stop teams from optimizing one part of the system by shifting cost onto another.

## 17. Workflow for Diagnosing Slow Pipelines

When pipelines or delivery flows slow down, follow this sequence:

1. **Define scope:** one job, one workflow, one repository, one environment, or all projects?
2. **Define measurement points:** event-to-workflow, job-ready-to-runner, or commit-to-verified-production?
3. **Break down time:** queue, execution, dependency, environment, approval, deployment, and verification.
4. **Inspect distributions:** p50, p90/p95, and outliers.
5. **Segment:** by runner, workflow type, branch, service, peak hours, and change type.
6. **Check reliability:** retries, flaky tests, runner failures, external dependencies, and partial deployments.
7. **Find critical path:** identify which segment dominates completion time.
8. **Form a hypothesis:** pick one evidence-backed cause.
9. **Experiment with guardrails:** make a small scoped change and re-measure.
10. **Standardize or revert:** keep the improvement only when both speed and reliability meet targets.

~~~mermaid
flowchart TD
    A["Slow pipeline / delivery"] --> B["Break down elapsed time"]
    B --> C{"Does wait time dominate?"}
    C -- "Yes" --> D["Queue / dependency / approval / environment"]
    C -- "No" --> E["Execution / critical path"]
    D --> F["Check reliability and owners"]
    E --> F
    F --> G["Identify bottleneck with evidence"]
    G --> H["Test improvement with guardrails"]
    H --> I{"Do speed and reliability both pass?"}
    I -- "Yes" --> J["Standardize improvement"]
    I -- "No" --> K["Adjust or revert"]
~~~

If data is insufficient to separate queue from execution time, the first step may be adding timestamps and instrumentation rather than adding runners or rewriting workflows.

## 18. Example: Fast Build, Yet Pull Requests Remain Slow

A Java service team observes these numbers:

| Component | Median Time |
|---|---:|
| PR waiting for first reviewer | 9 hours |
| Review and rework | 5 hours |
| CI queue | 8 minutes |
| Build/test/scan execution | 11 minutes |
| Waiting for integration environment | 2 hours |
| Integration test execution | 18 minutes |
| Waiting for release approval | 1 day |
| Deploy and verification | 25 minutes |

The team decides to optimize the build from 11 minutes down to 6 minutes. Total elapsed time drops by only 5 minutes across a multi-day flow.

The larger bottlenecks are:

- PR waiting for reviewers.
- Shared integration test environment.
- Release approval.

More suitable experiments:

- Set up reviewer rotation and stale-PR alerts.
- Provision per-run environments or a managed queue with an owner.
- Send evidence bundles to approvers and define SLAs.
- Automate low-risk approvals under an approved policy.

Only after cutting those major waits should they focus next on execution time and the critical path.

## 19. Example: Parallel Optimization Degrades Reliability

A team expands a test matrix from 4 to 24 concurrent jobs to cut duration. Pipeline p50 drops from 30 to 17 minutes, yet:

- Runner CPU and disk frequently saturate.
- The test database faces contention from many jobs.
- p95 climbs from 50 to 75 minutes.
- Flaky test rate rises.
- Several jobs time out and retry.
- External sandboxes begin returning rate-limit errors.

This change pushed concurrency beyond real system capacity.

Remediation:

1. Measure resource utilization across runners and test environments.
2. Cap max parallelism per workload type.
3. Split the test suite into balanced shards.
4. Provide isolated databases/schemas or environment isolation.
5. Throttle requests to external sandboxes.
6. Monitor p50, p95, first-attempt success, and retry rate.
7. Selectively scale capacity where evidence proves resource scarcity.
8. Weigh cost against benefit after the change.

The goal is optimizing the critical path within sustainable capacity, not maximizing simultaneous job count.

## 20. Designing a Balanced Dashboard

A dashboard should include speed, wait times, and reliability together.

It can be organized into sections:

**Flow**

- Commit-to-verified-production lead time.
- PR review wait.
- Approval wait.
- Deployment frequency.
- WIP and throughput.

**Pipeline**

- Queue time p50/p95.
- Job execution duration.
- Critical path duration.
- Pipeline duration p50/p95.
- Runner provisioning time.

**Reliability**

- First-attempt success rate.
- Retry rate.
- Flaky test rate.
- Infrastructure failure rate.
- Artifact publish failures.
- Partial deployment rate.

**Service outcomes**

- Change failure rate.
- Recovery time.
- SLO/error budget.
- Post-deploy error rate and latency.

Every chart needs:

- Metric definition.
- Time window.
- Sample size.
- Segmentation by repository/service/workflow.
- Owner.
- Links to runs or release records.
- Annotations when calculation methods change.

Do not collapse all metrics into a single pipeline health score. A single composite score can hide a fast pipeline backed by untrustworthy tests or a degrading production service.

## 21. Common Anti-Patterns

| Anti-pattern | Risk | Improvement |
|---|---|---|
| Measuring only job execution time | Ignores queue and approval waits | Measure full elapsed time by segment |
| Using pipeline duration as lead time | Hides review and release bottlenecks | Track commit-to-verified-production |
| Adding runners for every type of wait | Fails to solve dependency or approval waits | Classify queues and blocking reasons accurately |
| Retrying until pass | Masks flaky tests and real defects | Track first-attempt success, retry rate, and failure classes |
| Dropping integration/security tests for speed | Increases defect escapes and incidents | Optimize test execution; never remove gates arbitrarily |
| Scaling concurrency without limits | Overloads runners and environments | Cap by capacity; monitor p95 |
| Optimizing p50 while ignoring p95 | Slow tail runs continue hurting teams | Track percentiles and segment data |
| Removing approvals without risk analysis | Weakens release governance | Automate low-risk cases per policy |
| Treating rollback command as full recovery | Data and service may remain unstable | Verify SLOs, business flows, and data integrity |
| Using unverified caches | Unreproducible builds or wrong data | Key caches properly, verify integrity, run clean builds |
| Red/green-only dashboards | Hides causes and owners | Display queue, execution, retries, and blocking reasons |
| Optimizing a single metric | Shifts cost elsewhere | Pair primary metrics with guardrails |

## 22. Safe Pipeline Optimization Checklist

Before rolling out an optimization, confirm:

- [ ] Start and end measurement boundaries are clearly defined.
- [ ] Queue time is separated from job execution time.
- [ ] Review, dependency, environment, and approval waits are measured appropriately.
- [ ] Pipeline duration is not substituted for delivery lead time.
- [ ] The critical path has been identified.
- [ ] Both p50 and p90/p95 are tracked, not just the mean.
- [ ] First-attempt success and retry rates are tracked.
- [ ] Flaky tests are logged and assigned owners.
- [ ] Runner capacity and resource saturation are checked.
- [ ] Test scope and security gates are not arbitrarily reduced.
- [ ] Test environments are sufficiently stable and representative.
- [ ] Caches have proper keys, integrity checks, and a clean-build strategy.
- [ ] Approvals have clear owners, SLAs, and policies.
- [ ] Post-deployment verification still satisfies risk targets.
- [ ] Both a primary metric and guardrails are defined for the change.
- [ ] Baseline and evaluation window exist.
- [ ] Results are segmented by workload and service.
- [ ] Metrics link back to pipeline runs, releases, and deployments.
- [ ] The change does not push defect escape, change failure, or recovery time past thresholds.

## 23. Self-Assessment Exercise

A team reports their pipeline is faster after an optimization effort:

- Pipeline duration p50 dropped from 24 to 12 minutes.
- Queue time p50 dropped from 5 to 2 minutes.
- Pipeline duration p95 rose from 42 to 60 minutes.
- First-attempt success dropped from 97% to 89%.
- Retry rate rose from 4% to 18%.
- Integration tests frequently wait on a shared database.
- Median PR review wait is 1.5 days.
- Median production approval wait is 18 hours.
- Change failure rate rose from 3% to 9%.

Analyze:

1. Which metrics show the pipeline got faster in the typical case?
2. Why did p95 and first-attempt success degrade?
3. What problems could the rising retry rate be masking?
4. Which wait times lie outside pipeline execution?
5. Should they add more runners or concurrency? What evidence is needed?
6. How can database integration wait time be reduced?
7. How should PR review and approval waits be improved while maintaining control?
8. Which tests or quality gates must never be dropped merely to shrink duration?
9. Which guardrails should be monitored if optimization continues?
10. How should change failures be linked back to release and deployment IDs?

A strong plan keeps the helpful p50 gains, investigates the root causes behind rising p95 and retries, isolates test databases, streamlines reviewer/approval flows, and analyzes change failures before increasing deployment frequency. Conclusions must rest on both speed and reliability data.

## Conclusion

Optimizing pipeline execution time addresses only part of software delivery time. Queues, reviews, dependencies, environments, approvals, and post-deploy verification can consume the majority of elapsed time. A fast pipeline that is flaky, relies on heavy retries, or skips essential checks makes delivery less reliable and can lengthen recovery time.

Break down end-to-end elapsed time, measure waiting separately from execution, examine the critical path alongside percentiles, and monitor first-attempt success and retries. Choose improvements based on evidence-backed bottlenecks, preserve necessary quality gates, and enforce guardrails across change failure rate, SLOs, cost, and user experience. The goal is cutting unnecessary wait time while sustaining a predictable, trustworthy release flow.

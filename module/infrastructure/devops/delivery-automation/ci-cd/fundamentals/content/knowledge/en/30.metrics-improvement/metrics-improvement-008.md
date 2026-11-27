# Choosing a Small Improvement and Checking Its Impact After Rollout

CI/CD improvement does not have to start with a massive pipeline overhaul project. Many valuable results come from a small, clearly scoped, measurable change: reducing one job's wait time, removing a redundant dependency installation step, clarifying an error message, reducing flaky tests, or shortening the time from push until developers get feedback.

What matters is verifying whether the change produces the desired result. A faster pipeline that skips tests, increases failure rates, or creates extra investigation work is not a good improvement. Teams must start from existing data, pick the right problem, state a testable hypothesis, change one factor in a small scope, and measure both desired outcomes and side effects.

This lesson presents a practical CI/CD improvement loop: measure the current state, pick a small opportunity, run a controlled experiment, compare before/after, decide to keep or revert, and document lessons so the next improvement rests on solid evidence.

## 1. An improvement is a hypothesis that must be tested

An idea that sounds reasonable is not guaranteed to work in a real system.

Examples:

- "Enabling cache will make the pipeline faster."
- "Running more jobs in parallel will shorten feedback time."
- "Adding retries will reduce red pipelines."
- "Moving slow tests to nightly will make PRs faster."
- "Increasing runner size will cut build time."

Each statement above is only a hypothesis. Caching can speed things up yet also cause stale outputs; raising parallelism can worsen queues or contention; retries can mask flaky tests; moving tests to nightly can delay catching critical bugs.

A strong hypothesis describes:

1. The observed problem.
2. The likely root cause of the problem.
3. The concrete change to try.
4. Expected outcome and how it will be measured.
5. Quality-protection conditions.
6. Observation window or run count required.
7. Stop or rollback criteria.

Example: "Gradle test jobs re-download dependencies across many runs. If we enable dependency caching for Linux jobs on pull requests, the job's median execution time will drop by at least 15% after the warm-up period, while test failure rate, cache restore errors, and test outcomes remain virtually unchanged."

This hypothesis can be falsified with data. That is the essential trait of a well-designed improvement experiment.

## 2. Start with operational questions, not tools

Before editing workflows, identify what is actually causing friction for the team.

Helpful questions:

- How long must developers wait to know a pull request has an error?
- How much time sits in queues versus setup, build, test, or deploy?
- Which job fails or requires reruns most often?
- At which step are bugs detected and how long does root-cause diagnosis take?
- Is the pipeline repeating unnecessary work?
- Does a small change trigger too many projects or tests?
- Is a manual step regularly causing delays or mistakes?
- What workarounds is the team forced to maintain?

Data can come from CI providers, build scans, test reports, deployment history, issue trackers, or developer observations. Team opinions help locate where to look; data quantifies severity and verifies results.

Do not pick a new tool merely because it is popular. If the bottleneck sits in queue times due to scarce runners, switching build tools may not solve anything. If tests dominate total time, optimizing checkout may yield a negligible difference.

## 3. Define the right metrics and calculations

A metric needs a definition clear enough that two people measuring the same event arrive at comparable numbers.

For CI/CD, consider these metric groups:

| Group | Metric | Question |
|---|---|---|
| Feedback time | Time from push to first result | How early do developers get signal? |
| Queue | Time waiting for a runner | Does the system have sufficient execution capacity? |
| Execution | Build/test/deploy time | Which step actually consumes time? |
| Reliability | Job failure rate from product or infrastructure | Is the pipeline stable? |
| Flakiness | Rate of tests yielding inconsistent outcomes | Are red results trustworthy? |
| Rework | Rerun counts or investigation time | How much effort does the team spend handling feedback? |
| Delivery | Time from accepted change to production | How fast do changes traverse the system? |
| Recovery | Recovery time after failed deploys | How effectively does the team recover? |

Distinguish queue time from execution time. If a job starts after waiting 12 minutes for a runner and runs for only 4 minutes, optimizing scripts may not alter overall wait experience. Similarly, time from push to first result differs from time to full workflow completion.

Metric definitions should specify start point, end point, unit, job scope, and how canceled or retried runs are handled.

## 4. Pick one primary metric and guardrails

An experiment should have one primary metric to evaluate the hypothesis. In addition, define guardrail metrics to detect side effects.

Example when optimizing CI time:

- **Primary metric:** median execution time of the target job.
- **Guardrail 1:** test failure rate does not rise above an acceptable threshold.
- **Guardrail 2:** mandatory tests are not skipped or narrowed in scope.
- **Guardrail 3:** cache restore/save errors do not destabilize jobs.
- **Guardrail 4:** runner and storage costs do not surge unexpectedly.
- **Guardrail 5:** artifacts and test results remain traceable.

If you only look at averages, a few ultra-fast runs can mask a majority of unchanged jobs. Medians are usually more resilient to outliers; high percentiles like p90 expose the experience of slower runs.

Do not pick too many primary metrics. If every metric is a goal, the team cannot tell which criterion defines experiment success. Keep one primary objective and a concise set of guardrails protecting quality.

## 5. Record a baseline before changing anything

A baseline is current-state data used as the comparison reference. Without a baseline, teams easily mistake unrelated system shifts for the impact of an improvement.

Before modifying the pipeline:

1. Pick the workflow/job to improve.
2. Specify which run types enter the comparison.
3. Collect data over a sufficiently representative time window.
4. Record median, p90, run count, and failure rate.
5. Record runner, OS, branch, matrix, and trigger type.
6. Note other ongoing changes that might influence results.

For example, a baseline may span 10 business days or a minimum run count large enough to show variance. The required sample depends on run cadence and system stability; low-PR projects may need longer windows.

Never rely on a single pre-change run. A build could be unusually fast due to a warm cache, or slow because shared runners were temporarily overloaded.

## 6. Compare equivalent conditions

Before/after comparisons are meaningful only when both datasets represent reasonably similar conditions.

Verify:

- Same workflow and job scope.
- Same OS/runner class and architecture.
- Same test suite and matrix.
- Same trigger type, e.g., PR vs. PR.
- Same concurrency policy.
- Same time calculation method.
- Same handling of retries and canceled runs.
- Roughly comparable change volume or test size.

If there were 20 test jobs before the change and only 12 jobs afterward, duration may have dropped due to reduced test scope. That is not proof of a more efficient pipeline if coverage quality declined.

If runner images or dependencies change simultaneously, document them as confounding factors. Whenever possible, change only one factor per experiment so results remain easy to interpret.

## 7. Pick a small improvement with controlled scope

A small improvement typically has these traits:

- Affects only one workflow, job, or service.
- Can be toggled on/off via configuration or a minor edit.
- Can roll out to a subset of runs first.
- Has metrics available to measure it.
- Can be rolled back quickly.
- Does not weaken quality or security gates.

Suitable examples:

- Enabling dependency caching for a single job.
- Removing a tool-install step for a tool already preinstalled in the runner image.
- Splitting test reports to identify slow suites.
- Running lint before integration tests for earlier feedback on simple errors.
- Eliminating a redundant checkout or artifact download.
- Fixing one flaky test whose root cause has been identified.
- Producing clearer error messages when a secret reference is missing.

Examples too large in scope for a first experiment:

- Replacing the entire CI provider.
- Migrating all builds to a brand-new system.
- Rewriting every pipeline at once.
- Removing many tests to cut duration.
- Changing runners, build tools, dependencies, and test strategy all at once.

Small scope isolates cause and effect and limits blast radius if the change underperforms.

## 8. Write an experiment plan before rollout

A brief plan aligns the team on goals before results arrive.

| Element | Example |
|---|---|
| Problem | Integration job repeatedly re-downloads dependencies |
| Baseline | Median 12 minutes, p90 17 minutes over 2 weeks |
| Hypothesis | Dependency caching cuts execution time |
| Change | Enable dependency cache and build cache for Linux PR job |
| Primary metric | Median execution time |
| Guardrails | Test failures, cache errors, storage, and coverage |
| Scope | One workflow, one runner group |
| Measurement window | 2 weeks post warm-up |
| Keep criteria | Median drops at least 15%, guardrails hold |
| Stop criteria | Test discrepancies, cache errors, or cost over threshold |
| Owner | Workflow maintainer |
| Rollback | Disable cache configuration and re-run checks |

Thresholds in the table are illustrative. Teams should choose thresholds based on change cost, baseline variance, and business value. Do not set targets so low that every change counts as success, or so high that experiments cannot realistically pass.

## 9. Execute the change step by step

Once the experiment starts, stick to the planned scope:

1. Create a small change and review it.
2. Confirm test and security gates remain intact.
3. Deploy to the target branch or workflow.
4. Record the exact start timestamp.
5. Watch the initial runs and any new errors.
6. Wait out any warm-up phase for caches or mechanisms needing initial state.
7. Collect the planned number of runs.
8. Do not alter additional variables before recording and evaluating impact.

Do not lower the success bar after seeing missed results. If an initial condition turns out unreasonable, document it clearly and design the next experiment.

## 10. Practical example: enabling Gradle build cache for one CI job

Suppose a Java project's integration test job runs Gradle, frequently downloading dependencies and re-executing tasks whose outputs could be reused.

The team observes the job spends significant time in dependency resolution and repeated build tasks. The idea is to enable Gradle build cache or dependency cache within a strict scope, then measure impact.

Distinguish two cache types:

- **Dependency cache:** stores downloaded dependency artifacts so subsequent runs avoid re-downloading unchanged dependencies.
- **Build cache:** stores reusable task outputs when corresponding inputs have not changed.

Build cache is safe only when tasks declare inputs/outputs accurately and remain reproducible. A custom task missing an input declaration may return stale invalid outputs. Therefore, do not enable remote caching broadly across all tasks without verifying cache correctness.

### 10.1. Hypothetical baseline

Illustrative data over two weeks:

| Metric | Before change |
|---|---:|
| Run count | 80 |
| Median execution time | 12 minutes 20 seconds |
| p90 execution time | 17 minutes |
| Median queue time | 2 minutes |
| Test failure rate | 5.0% |
| Cache hit rate | Unmeasured or disabled |

This example illustrates the method. In real projects, pull data from the CI provider/build scans and record how runs were filtered.

### 10.2. Hypothesis and scope

Hypothesis: enabling dependency cache and build cache for the Linux integration job will lower median execution time by at least 15% after warm-up, without changing test results or increasing cache-related failures.

Experiment scope:

- Apply only to one integration job.
- Use only the same Linux runner class as the baseline.
- Keep the test suite and matrix identical.
- Do not simultaneously change runner size or Gradle version.
- Cache only reproducible content with proper keys.

### 10.3. Configuration example

You can enable build cache in the Gradle command:

```bash
./gradlew --build-cache integrationTest
```

With GitHub Actions, you can configure Gradle dependency caching via the appropriate setup action or an organization-approved caching mechanism. Conceptual workflow example:

```yaml
steps:
  - uses: actions/checkout@v4

  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '21'
      cache: gradle

  - name: Run integration tests with build cache
    run: ./gradlew --build-cache integrationTest
```

This is an illustrative example. Check action versions and your repository's action-pinning policy. Dependency caching and Gradle build caching are two separate mechanisms; enabling dependency cache does not automatically turn on build cache.

If using a remote build cache, define read/write permissions, trust boundaries between trusted branches and pull requests from forks, retention, cache keys, and cache invalidation. Never allow an untrusted job to write outputs into a cache consumed by trusted release jobs.

### 10.4. Monitoring cache correctness

A cache hit does not automatically prove correct output. Verify:

- Do tasks declare complete inputs and outputs?
- Do tasks depend on undeclared time, environment variables, or external files?
- Do cache keys distinguish toolchains or required configurations?
- Are any tasks non-deterministic?
- Can uncached builds run for comparison when suspicious?
- Do cached artifacts pass the exact same tests and verification?

Early on, scope caching narrowly, preserve the ability to run uncached for comparison, and watch cache hit/miss behavior. If discrepancies appear, disable caching for the suspect task, investigate input/output declarations, and only then re-enable.

### 10.5. Hypothetical post-experiment results

After warm-up and two weeks of observation:

| Metric | Before | After | Interpretation |
|---|---:|---:|---|
| Run count | 80 | 82 | Roughly equivalent workload |
| Median execution time | 12:20 | 9:40 | Down roughly 21.6% |
| p90 execution time | 17:00 | 13:00 | Slower run cohort also improved |
| Median queue time | 2:00 | 2:05 | Practically unchanged |
| Test failure rate | 5.0% | 5.1% | 0.1 percentage-point delta; more samples needed to assess variance |
| Cache hit rate | Unmeasured | 72% | Cache reuse achieved |

Hypothetical results show execution time dropped while queue time stayed nearly flat. A 0.1 percentage-point difference in failure rate across ~80 runs per group is not enough to conclude real impact either way; monitor longer and inspect individual failure causes. If real data meets the set criteria, the team can expand the experiment to similar jobs.

Do not conclude caching was definitely the sole cause if runners or dependencies also changed at the same time. Record those factors and consider a follow-up measurement window.

## 11. Calculating improvement magnitude

You can compute relative improvement for a metric where lower values are better:

\[
\text{Improvement (\%)} =
\frac{\text{Baseline} - \text{After}}{\text{Baseline}} \times 100
\]

For median execution time in the example:

\[
\frac{12.33 - 9.67}{12.33} \times 100
\approx 21.6\%
\]

Keep units consistent during calculation. Computing in seconds avoids minute/second conversion errors.

For metrics where higher values are better, such as cache hit rate or deployment success rate, flip the relative difference formula accordingly. For failure rates, report both percentage-point change and relative change so readers are not misled.

For example, failure rate rising from 5.0% to 5.1% is a 0.1 percentage-point increase, equivalent to a 2% relative increase. Both expressions answer different questions.

## 12. Do not look only at the median

Medians show the midpoint of a distribution, yet they can hide very slow runs or a single troubled runner group.

Inspect additionally:

- p50: typical experience.
- p90 or p95: slow-run cohort.
- Min/max: useful for spotting outliers, not as primary conclusions.
- Distributions by runner/OS/branch.
- Queue time and execution time separately.
- Run counts and runs excluded from the dataset.

If the median drops while p90 jumps sharply, a segment of developers may still face very slow feedback. Inspect distributions and segments before declaring success.

Do not pool different job types into a single shared median. A 3-minute unit test job and a 30-minute integration job must be analyzed separately or normalized by type.

## 13. Ensure enough samples and observation time

One or two runs are never enough to conclude a CI/CD change's effectiveness. Results can be skewed by cold caches, runner contention, traffic, test counts, or time of day.

Choose the measurement window based on:

- Actual run cadence.
- Metric variance.
- Number of representative branches/PRs.
- Nightly or release cycles.
- Time needed for cache warm-up or workload stabilization.
- Risk level of continuing the experiment.

If a project runs hundreds of times daily, sample size may be reached within days. If there are only a few releases per month, observe longer or use a controlled test set.

Include sample counts alongside every summary figure. Never report "median dropped 20%" without stating how many runs and over what time window the median was computed.

## 14. Identifying confounding factors

A before/after comparison can be influenced by changes outside the experiment.

Common factors:

- Runner image or machine type changed.
- Test count changed due to other commits.
- Different branch or PR workloads.
- Dependency registry unusually slow or fast.
- Cache warm in one group but cold in the other.
- Execution timing coinciding with peak hours.
- Concurrency or runner quotas changed.
- New jobs sharing the same resources appeared.
- Gradle/JDK or plugins were upgraded.
- Retry policy changed.
- A flaky test was quarantined during the same period.

Ways to reduce noise:

1. Keep runner class and workflow scope stable.
2. Compare identical trigger types.
3. Record toolchain versions and matrices.
4. Separate cold runs from warm runs when caching is under test.
5. Avoid deploying multiple changes simultaneously.
6. Note uncontrollable external changes.
7. When needed, use a control group or cohort rollout.

It is not always possible to eliminate every confounder. The goal is making conclusion boundaries explicit and avoiding overclaiming beyond what data supports.

## 15. Using control groups or cohort rollouts

For changes toggleable by group, you can keep a comparable group as a short-term control.

Example:

- Group A keeps running the existing CI configuration.
- Group B enables the new cache.
- Both groups use equivalent runner classes and test scopes.
- Compare execution time, failure rate, and cache errors.

Not every project has enough workload to split groups. You can roll out by repository, branch, or job. Avoid splitting in ways where one group gets light tasks while the other gets heavy tasks.

If using a control group, document grouping rules, sample counts, and conditions. If not, use a controlled before/after design and state inference limits clearly.

## 16. Setting guardrails and stop criteria

An improvement must not continue merely because the primary metric improves. Stop criteria are required when quality or security suffers.

Example guardrails for caching:

- No tests skipped or coverage reduced.
- No discrepancies between cached and uncached builds on essential checks.
- Cache restore/save error rate stays below threshold.
- No corrupted artifacts or stale outputs.
- No cache poisoning between untrusted and trusted workflows.
- Storage and network costs stay within limits.
- Job failure rate does not rise beyond acceptable tolerance.

When a guardrail is breached:

1. Halt further expansion.
2. Disable or restrict the change if it risks corrupting outcomes.
3. Preserve logs/reports for investigation.
4. Identify root cause.
5. Fix and run a fresh experiment with clear baselines/conditions.
6. Document the decision and impact.

Do not wait out the measurement window if signs appear of bad artifacts, bypassed security checks, or falsified test results.

## 17. Deciding to keep, adjust, or roll back

At the end of an experiment, outcomes are not always a simple binary pass/fail.

| Outcome | Condition | Action |
|---|---|---|
| Keep | Primary metric met, guardrails hold | Retain and expand in a controlled manner |
| Extend | Positive signal yet insufficient sample size | Keep measuring in current scope |
| Adjust | Metric missed yet specific cause and small fix exist | Revise plan and run a new experiment |
| Roll back | Guardrail breached or major side effects | Revert and verify prior state |
| Reject | Benefit too small relative to cost | Do not roll out broadly |
| Inconclusive | Missing data or heavy confounders | Do not claim success; redesign measurement |

Decisions should record the accountable owner and supporting data. If keeping the change, determine whether to expand to other workflows or keep it scoped to the current job.

## 18. Measuring impact beyond the primary metric

A small change can affect groups outside the modified job.

For example, raising parallelism may speed up one job while lengthening queues for another repository. Caching may cut downloads while increasing storage cost. Moving tests to nightly may shorten PR duration while delaying regression detection.

Therefore, examine:

- Impact on developer feedback.
- Impact on runner quotas and cost.
- Impact on storage/network.
- Impact on result trustworthiness.
- Impact on defect detection latency.
- Impact on shared workflows or projects.
- Impact on security and access controls.

This is why system-level guardrails are needed whenever a change touches shared resources.

## 19. Recording outcomes so the team can learn

Every experiment should leave a brief record, enough for others to understand what was tried and why the decision was made.

The record can include:

- Experiment name and owner.
- Problem and scope.
- Hypothesis.
- Baseline window and sample count.
- Primary metric and guardrails.
- Implemented change, commit, or PR.
- Start and end timestamps.
- Before/after results.
- Confounding factors.
- Incidents or exceptions.
- Decision: keep/extend/adjust/rollback/reject.
- Next steps and owner.

You do not need a lengthy report for every small change. A table inside an issue or pull request can suffice. However, outcomes must be stored where the team can look them up when planning the next improvement.

## 20. Avoiding improvements that make numbers look good while degrading quality

Certain tactics can make metrics look better short-term while making the system less trustworthy:

- Deleting slow tests instead of optimizing tests.
- Moving critical tests off PRs without a compensating release gate.
- Adding infinite retries to turn red jobs green.
- Ignoring failures on a specific platform.
- Using unsafe caches without verifying outputs.
- Shrinking timeouts until jobs get killed before reporting useful errors.
- Measuring only the faster job while ignoring queue wait.
- Comparing a cold run against a warm run.
- Changing multiple variables and crediting all gains to one change.
- Ignoring runner/storage costs or maintenance effort.

Meaningful improvements raise efficiency while preserving reliability, traceability, and committed quality levels.

## 21. Another example: reducing flaky tests by fixing root causes

Suppose an integration test fails randomly on roughly 4% of runs due to depending on a test service's startup timing.

A small change is waiting for an explicit readiness condition rather than a fixed sleep.

Plan:

- Baseline: record current run count, failure rate, and wait duration.
- Hypothesis: readiness polling will cut false failures without noticeably increasing duration.
- Change: replace fixed sleep with bounded-timeout polling and clear error output.
- Guardrails: tests still fail if the service never becomes ready; do not raise timeouts indefinitely.
- Measure: compare failure rate, p90 test duration, and timeout counts.
- Decision: keep if false failures drop while real defects are still caught.

Never merely increase retry counts to hide flaky tests. Retries can help with transient infrastructure failures when classified, bounded, and logged; they do not replace fixing why a test is unstable.

## 22. Continuous improvement in small loops

Once an experiment finishes, the team can repeat:

1. Review metrics and developer feedback.
2. Identify the next high-impact bottleneck.
3. Verify root cause instead of guessing.
4. Write a hypothesis and guardrails.
5. Pick one small change.
6. Measure baseline.
7. Test within a controlled scope.
8. Compare and decide.
9. Update documentation, workflows, and ownership.
10. Move on to the next issue.

Avoid running overlapping experiments on the same metric if impacts cannot be separated. When multiple changes must happen concurrently, define how to isolate measurements or accept that results can only be evaluated at the combined change-group level.

Improvement is not a campaign that ends when one number is hit. Pipelines, dependencies, runners, and product needs evolve continuously; teams must maintain the habit of inspecting data and adjusting based on evidence.

## 23. Checklist before applying a small improvement

- [ ] Problem is backed by data or concrete examples.
- [ ] Metric has a clear definition and calculation method.
- [ ] Baseline includes time window and sample count.
- [ ] Queue time is separated from execution time where appropriate.
- [ ] One primary metric exists for evaluation.
- [ ] Guardrails exist for tests, security, artifacts, and cost.
- [ ] Hypothesis can be confirmed or falsified.
- [ ] Change has small scope and an owner.
- [ ] Rollout and rollback plans exist.
- [ ] Before/after comparison conditions are equivalent.
- [ ] Confounding factors are documented.
- [ ] Measurement window and sample size are appropriate.
- [ ] Test coverage and gates are not lowered to polish numbers.
- [ ] Stop criteria exist for guardrail breaches.
- [ ] A keep, extend, adjust, rollback, or reject decision is made.
- [ ] Results are recorded and shared with the team.

## Conclusion

Choosing a small improvement and verifying its impact after rollout turns CI/CD improvement into a repeatable learning practice. Teams should start from observed problems, define metrics and baselines, state hypotheses, change one factor in a controlled scope, and measure both expected gains and guardrails.

A change should be kept only when data demonstrates clear benefit while quality, security, cost, and traceability remain protected. If samples are insufficient or confounders interfere, keep measuring or redesign the experiment. If guardrails break, stop and revert. This approach lets teams improve step by step without trading away release process reliability.

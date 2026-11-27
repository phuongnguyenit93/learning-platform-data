# Distinguishing Execution Time from Waiting Time

A CI/CD pipeline completing in 40 minutes does not mean the team or machines actually worked for 40 minutes. Building and testing might have taken only 12 minutes, while the remainder was spent waiting for a runner in the queue, waiting for an environment to become ready, or waiting for a release approval. In other cases, a pipeline reports a running status for 20 minutes, yet most of that duration is spent waiting for an external service to respond.

To improve software delivery speed, you must separate **execution time** from **waiting time**. These two measurements answer different questions:

- Execution time tells you how long work takes to finish once a resource or owner actually begins processing it.
- Waiting time tells you how long work sits idle before the next step can start or before a required decision is made.

If you only look at total pipeline duration, it is hard to know whether to optimize the build, scale runner capacity, streamline approvals, or address an external dependency.

## 1. Key Concepts to Distinguish

### Elapsed Time

**Elapsed time** is the actual wall-clock duration between a chosen start milestone and end milestone:

\[
T_{\text{elapsed}} = t_{\text{end}} - t_{\text{start}}
\]

In a software delivery flow, the start milestone might be when a commit is pushed, when a pull request is opened, when a change is merged, or when the pipeline starts. The end milestone might be when an artifact is produced, when deployment completes, or when post-deployment verification succeeds.

No single milestone pair fits every question. For example, time from opening a pull request to merging reflects part of the review workflow; time from commit to verified production reflects the broader delivery flow. When comparing teams or runs, you must use the exact same definition of start and end milestones.

### Execution Time

**Execution time** (or process time) is the duration during which work is genuinely being processed. The actor doing the work can be a machine or a human:

- A runner compiling source code.
- A test process running automated tests.
- A deployment tool updating a service.
- An engineer reading changes, inspecting evidence, and making an approval decision.

For pipelines, the time a job spends in a running state only indicates that the job started and has not yet finished. It does not guarantee that all of that duration was productive execution time. A process might be sleeping, waiting on a lock, waiting on an API, hitting a rate limit, or waiting on another service. If telemetry cannot distinguish these intervals yet, record it as **job run duration** rather than labeling all of it execution time.

### Waiting Time

**Waiting time** is the duration during which work is ready or requires a downstream condition, yet cannot proceed because it is waiting for resources, dependencies, schedules, or decisions.

Common scenarios in CI/CD include:

| Scenario | Common Classification | Signals to Record |
|---|---|---|
| Job created but no runner available | Resource wait | Timestamp when job became ready and when runner picked it up |
| Tests eligible to run but waiting for a worker | Queue wait | Timestamp when dependency finished and when tests started |
| Pull request waiting for a reviewer | Handler wait | Timestamp when review was requested and when reviewer started |
| Release waiting for production approval | Decision wait | Timestamps for request, review start, and decision |
| Deployment environment being provisioned | Environment wait | Timestamp when requested and when environment became ready |
| Job waiting on a shared environment lock | Coordination wait | Timestamp when lock was requested and when lock was acquired |
| Process waiting on an API or rate limit | External dependency wait | Request send time, response time, and retry attempts |

Some intervals contain both waiting and execution. For instance, 30 minutes between requesting approval and receiving a decision might consist of 25 minutes waiting for a reviewer and 5 minutes of reviewer inspection. If you only capture the request time and decision time, you only know **approval latency** is 30 minutes; you lack evidence to conclude all 30 minutes were waiting time.

### Waiting Time Differs from Human Execution Time

Never treat every interval without active CPU usage as waiting time for the overall process. Code review, test result analysis, and release approval are valuable work even though they consume minimal compute resources.

When measuring human-in-the-loop steps, separate at least three milestones:

1. Timestamp when the task is assigned or the request is sent.
2. Timestamp when the owner actually begins working on it.
3. Timestamp when the owner completes it and issues a decision.

The interval from milestone 1 to milestone 2 is handler waiting time. The interval from milestone 2 to milestone 3 is human execution time. If the system cannot capture milestone 2, report the end-to-end latency of that step and explicitly note the data limitation.

## 2. Example: Reading Timing Data from a CI/CD Flow

Suppose a commit enters the pipeline at 09:00. Deployment is only considered complete after production verification finishes at 10:18. The pipeline has the following intervals:

| Time Interval | Activity | Time Type | Duration |
|---|---|---:|---:|
| 09:00–09:10 | Job waiting for runner | Waiting | 10 minutes |
| 09:10–09:18 | Build artifact | Execution | 8 minutes |
| 09:18–09:23 | Test job waiting for worker | Waiting | 5 minutes |
| 09:23–09:38 | Run automated tests | Execution | 15 minutes |
| 09:38–10:03 | Waiting for reviewer to start approval review | Waiting | 25 minutes |
| 10:03–10:08 | Reviewer inspects evidence and approves | Execution | 5 minutes |
| 10:08–10:13 | Deploy to production | Execution | 5 minutes |
| 10:13–10:18 | Post-deployment verification | Execution | 5 minutes |
| **Total** | **Commit to successful verification** | **Elapsed time** | **78 minutes** |

In this example:

\[
T_{\text{execution}} = 8 + 15 + 5 + 5 + 5 = 38 \text{ minutes}
\]

\[
T_{\text{waiting}} = 10 + 5 + 25 = 40 \text{ minutes}
\]

\[
T_{\text{elapsed}} = 38 + 40 = 78 \text{ minutes}
\]

Execution time accounts for roughly 48.7% of total time; waiting time accounts for roughly 51.3%. The largest wait is the 25 minutes before the reviewer begins processing. Shaving 2 minutes off the build only cuts total delivery time by about 2 minutes. Reducing review wait time while keeping review quality intact can have a far greater impact.

This example assumes sequential, non-overlapping intervals and availability of the reviewer-start timestamp. With real production data, verify these assumptions before summing durations.

### How to Interpret Ratios

You can use flow efficiency to observe what share of elapsed time goes into active execution:

\[
\text{Flow efficiency} =
\frac{T_{\text{execution}}}{T_{\text{elapsed}}} \times 100\%
\]

In the example above, this ratio is roughly 48.7%. Treat it as a diagnostic indicator for bottlenecks, not a metric to maximize at any cost. A security test gate or risk approval naturally takes time to protect the system. The goal is to eliminate unnecessary waiting, make deliberate processing time visible, and maintain required safeguards.

## 3. Measuring from Events Instead of Estimates

To separate the two time categories, each step needs well-defined event timestamps. For an automated job, record at minimum:

- Timestamp when the step became ready to run.
- Timestamp when the runner or process actually started.
- Timestamp when the step finished.
- Outcome, run ID, and failure reason if applicable.

Example record for a build step:

~~~json
{
  "run_id": "pipeline-2026-11-18-001",
  "commit_sha": "a1b2c3d4",
  "stage": "build",
  "ready_at": "2026-11-18T09:00:00+07:00",
  "started_at": "2026-11-18T09:10:00+07:00",
  "finished_at": "2026-11-18T09:18:00+07:00",
  "outcome": "success"
}
~~~

From this record:

- Pre-run waiting time = `started_at` minus `ready_at` = 10 minutes.
- Step run duration = `finished_at` minus `started_at` = 8 minutes.

For an approval gate, also capture when the handler begins reviewing:

~~~json
{
  "stage": "production-approval",
  "requested_at": "2026-11-18T09:38:00+07:00",
  "review_started_at": "2026-11-18T10:03:00+07:00",
  "decided_at": "2026-11-18T10:08:00+07:00",
  "decision": "approved"
}
~~~

This separates 25 minutes waiting for a reviewer from 5 minutes of review processing. If only `requested_at` and `decided_at` exist, report 30 minutes as approval latency. Do not guess the reviewer's execution time from that span.

### Practical Measurement Workflow

**Step 1: Choose flow boundaries.** Define explicitly whether you are measuring from commit, pull request, merge, or pipeline start, and ending at artifact, deployment, or production verification. Pick boundaries based on the question being asked and keep them consistent across measurements.

**Step 2: Attach end-to-end identifiers.** Use run ID, commit SHA, artifact ID, and environment to correlate events across source control, CI, artifact repositories, deployment systems, and verification tools. Without shared identifiers, timestamps from different runs can be mismatched.

**Step 3: Collect timestamps at every step.** For automated jobs, capture ready, started, and finished timestamps. For reviews or approvals, capture when the request was sent, when the handler started, and when the decision was made. Use timestamps with explicit time zones and synchronized clocks across systems.

**Step 4: Tag waiting causes.** Categorize waits by runner queue, test queue, review, approval, environment provisioning, shared locks, external dependencies, release schedules, or retries. Cause labels turn numbers into actionable next steps.

**Step 5: Check for gaps and overlaps.** Ensure intervals belong to the same flow and use the same unit of measurement. If an interval has an unknown cause, keep it in an unclassified bucket rather than arbitrarily assigning it to execution or waiting. When jobs run in parallel, analyze the critical path separately.

**Step 6: Track distributions, not just averages.** Report the median (p50) and high percentiles such as p85 or p95 for delivery time, runner queue wait, review wait, and deployment duration. Averages can hide a small group of runs that get stuck waiting for a very long time.

## 4. Handling Parallel Jobs

In a pipeline with parallel branches, the sum of individual job durations does not equal the elapsed time of the pipeline. Suppose after a build, two test suites run concurrently:

- Test suite A runs for 12 minutes.
- Test suite B runs for 9 minutes.
- The next step can only begin once both suites finish.

The elapsed time of this parallel segment is 12 minutes because the pipeline must wait for the longest branch. Total runner execution time is 21 job-minutes. These two measurements serve different purposes:

- **Critical-path time** shows how much that segment contributes to end-to-end delivery time.
- **Total job execution time** shows how much compute capacity or machine work was consumed.

Never subtract 12 elapsed minutes from 21 aggregate execution minutes to compute waiting time; that calculation is invalid because the two jobs overlapped. When analyzing flow speed, trace the dependency chain that determines when the final step can proceed. When analyzing cost or runner capacity, sum individual job durations and report them separately.

The same applies when multiple pull requests wait on a shared integration environment. One change may do zero active work while waiting on a lock while another change is deploying to that environment. Tie events to the exact run ID and resource to avoid double-counting or misattributing time.

## 5. Common Sources of Waiting and How to Improve Them

| Cause | Diagnostic Questions | Improvement Direction |
|---|---|---|
| Overloaded runners | Do queues spike during peak hours or for a specific job type? | Tune concurrency, autoscaling, pool sizing, or route runners by workload type |
| Dependent jobs waiting on each other | Which step is blocking downstream steps? | Remove unnecessary dependencies, split independent tasks, and parallelize safely |
| Slow builds or tests | Where is execution time concentrated? | Use caching properly, incremental builds, smart test splitting, and optimize true bottlenecks |
| Slow reviews or approvals | How long do requests sit before someone picks them up? | Clarify ownership, assign backup reviewers, present scannable evidence, and agree on SLAs |
| Environment not ready | How much time goes into provisioning or configuring environments? | Automate provisioning, standardize environments, and use ephemeral environments where suitable |
| Shared environment locks | Are multiple pipelines competing for the same lock? | Narrow lock scope, shorten lock hold duration, and avoid serializing independent changes |
| Slow external services | Is the job actively working or waiting on an API, registry, or test service? | Track dependency latency, use bounded retries with backoff, and ensure operations are idempotent |
| Flaky tests | Are runs being retried or waiting on manual confirmation? | Fix root causes of flakiness; if quarantining tests, enforce an owner and resolution deadline |
| Waiting for release windows | Is a build ready yet held for a deployment schedule? | Align release cadence and process to risk level; adopt progressive delivery where suitable |

Not all waiting time should be eliminated. Testing, security scanning, high-risk change approvals, and post-deployment verification protect quality. Improvements should focus on cutting time that adds no extra assurance, increasing readiness beforehand, and routing evidence to the right people at the right time.

For instance, if a release waits 25 minutes for approval because the reviewer missed the notification, improve notification routing and assign backup approvers. If the reviewer needs 5 minutes to inspect evidence, do not aim to eliminate those 5 minutes by bypassing the check. Similarly, reducing runner wait time by raising concurrency must be paired with resource limits and cost controls.

## 6. Common Pitfalls When Reading Metrics

### Treating Entire Job Duration as Execution Time

A running state can include sleep time, API waits, lock waits, or retries. Use logs, traces, and event timestamps to separate them. When data is insufficient, label the metric job duration instead of execution time.

### Summing Parallel Job Durations as Sequential

Total job-minutes reflect resource consumption. Delivery time depends on the critical path of the dependency graph. Report these two metrics separately.

### Using Inconsistent Start and End Milestones

Comparing merge-to-deploy in one team against PR-open-to-deploy in another leads to false conclusions. State definitions clearly and enforce consistent boundaries on dashboards.

### Looking Only at Averages

A handful of runs stuck for hours can be masked by many fast runs. Use p50 to understand typical experience and p85 or p95 to spot long tails.

### Treating Every Wait as Waste

Waiting time can stem from risk controls, release schedules, or necessary dependencies. Before shortening a gate, identify its control objective, the risk it mitigates, and the substitute evidence required if the process changes.

### Ignoring Failed Runs and Retries

Measuring only the final successful run hides time lost to broken builds, flaky tests, rollbacks, or retries. For delivery experience, measure from the initial trigger event to the final outcome, while separately categorizing retry time and recovery time.

## 7. Designing Dashboards to Find the Right Bottleneck

A useful dashboard lets you drill down from the high-level view to root causes:

| Metric Group | Metrics to Track | Question Answered |
|---|---|---|
| End-to-end flow | Time from commit to verified deployment; p50, p85, p95 | How long does a change take to reach users? |
| Execution | Duration of build, test, deploy, and verification | Which activities genuinely take the most processing time? |
| Queues | Runner wait, worker wait, and environment lock wait times | Which resource or coordination point constrains the flow? |
| Human steps | Review pickup wait, review duration, approval latency | Is work stalled at handoffs or requiring substantial inspection time? |
| Reliability | Failure rate, retry count, recovery time | Which failures are stretching delivery time? |
| Post-release quality | Verification pass rate, rollbacks, post-deploy defects | Is speed paired with quality and recoverability? |

Filter metrics by repository, pipeline type, branch, environment, runner type, and time of day. A system-wide aggregate can hide that one runner pool or one environment is severely overloaded.

When reading a dashboard, follow this order:

1. Confirm whether end-to-end time actually increased.
2. Identify whether the increase came from execution, waiting, or unclassified intervals.
3. Locate the stage and cause contributing the most along the critical path.
4. Inspect high percentiles to see if the issue is systemic or isolated to specific runs.
5. Propose targeted changes addressing the root cause and monitor speed, reliability, and quality together.

For example, if p50 stays flat while p95 spikes sharply, speeding up every build may not solve the problem. Check for runner pool exhaustion spikes, prolonged locks on shared environments, unstable external dependencies, or retries concentrated on specific branches.

## 8. Practical Rules

- Always state the start milestone, end milestone, and unit of measurement before publishing any timing figure.
- Separate ready, started, and finished timestamps; for human-involved steps, capture when the owner actually starts working.
- Distinguish waiting time from end-to-end latency whenever data cannot separate active work from idle waiting.
- For parallel pipelines, use the critical path to analyze delivery time and total job-minutes to analyze resource consumption.
- Tag causes for major waits, then fix the highest-impact bottleneck first.
- Preserve necessary control gates; shorten the flow through automation, clearer evidence, and better coordination.

Once execution time and waiting time are separated, a team can pinpoint specifically why a change takes long to reach production. That clarity points to the right remedy: optimize the software and pipeline when processing is slow, add capacity or fix coordination when work is waiting, and improve reliability when retries or recoveries are dragging out delivery.

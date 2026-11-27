# Tracking Job Progress, Success Rates, and Per-Job Costs

A background processing system can receive thousands or millions of jobs, run them on workers, containers, VMs, or serverless functions, and return results after some time. Knowing only how many messages sit in a queue or how many worker processes are running is insufficient to answer operational questions: which jobs are running slow, how far along they are, what the true success rate is, how many resources retries are consuming, and how much a completed job costs.

Accurate tracking requires treating a **job as a first-class business entity with its own identifier and lifecycle**. Every job needs state, timestamps, progress, attempt counts, outcomes, and resource usage metadata. That data must correlate with queues, workers, function invocations, containers/VMs, and billing records. Operations teams can then trace a job from intake to final outcome, separate transient errors from terminal failures, and attribute costs to completed work.

This lesson covers job data models and lifecycles, how to measure progress and success rates, how to record retries and partial failures, how to allocate compute costs per job, how to build dashboards and alerts, and reconciliation workflows for measurable batch operations.

## 1. Distinguishing jobs, tasks, attempts, and messages

These terms are often used interchangeably yet carry distinct meanings:

- **Job:** the business unit of work requested by a user or system, such as processing an invoice batch or generating a monthly report.
- **Task/item:** a smaller unit within a job, such as one invoice, one file, or one record.
- **Attempt:** a single execution try of a job or task. A job may have multiple attempts due to retries.
- **Message:** a payload delivered by a queue or event bus to a consumer. One message may represent an entire job, one task, or a batch item.
- **Worker invocation:** a single invocation of a worker, container, or function to process work.
- **Execution:** the actual interval during which a process/function runs an attempt or part of an attempt.

For example, a November 2026 monthly report job processes 1 million records. The system splits the data into 100 partitions. Each partition is a task; each task may retry one or more times. A worker invocation may process one task or a batch of multiple tasks.

Counting only messages might show 100 messages published even though several tasks retried multiple times. Counting only invocations might show 110 executions even though only 100 tasks ultimately succeeded. Maintain explicit relationships across job, task, attempt, and invocation.

### Relationship model

~~~mermaid
flowchart TD
    J["Job"] --> T1["Task / partition 1"]
    J --> T2["Task / partition 2"]
    J --> T3["Task / partition N"]
    T1 --> A11["Attempt 1"]
    T1 --> A12["Attempt 2 (retry)"]
    T2 --> A21["Attempt 1"]
    A11 --> I1["Worker invocation"]
    A12 --> I2["Worker invocation"]
    A21 --> I3["Worker invocation"]
    I1 --> R1["Resource usage"]
    I2 --> R2["Resource usage"]
    I3 --> R3["Resource usage"]
~~~

Jobs are the unit for reporting business progress and total cost. Tasks track granular progress. Attempts explain retries and failures. Invocations paired with resource usage reconcile compute resources.

## 2. Defining the job lifecycle

A job needs a well-defined state machine. Common states:

| State | Meaning |
|---|---|
| `CREATED` | Job created but not yet accepted into a queue |
| `QUEUED` | Job accepted and waiting for a worker |
| `SCHEDULED` | System selected an execution time or target worker |
| `RUNNING` | An attempt is actively executing |
| `RETRY_WAIT` | Attempt failed transiently and job is waiting to retry |
| `PARTIALLY_SUCCEEDED` | Some tasks succeeded while others remain incomplete or failed |
| `SUCCEEDED` | Job completed per business criteria |
| `FAILED` | Job terminated with an unrecoverable error or exhausted retries |
| `CANCEL_REQUESTED` | Cancellation requested but termination not yet confirmed |
| `CANCELED` | Job stopped as requested |
| `TIMED_OUT` | Job or overall deadline exceeded allowed duration |
| `EXPIRED` | Job expired before starting or is no longer valid |

Not every system needs every state. What matters is consistent state semantics, valid transitions, and clear terminal conditions.

### State is not a log message

Do not infer final state by grepping log strings like "done" or "error". Logs can be dropped, delayed, or duplicated. State must live in an authoritative store with timestamps, versions, or sequences to prevent out-of-order overwrites.

### Valid state transitions

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> QUEUED
    QUEUED --> RUNNING
    RUNNING --> SUCCEEDED
    RUNNING --> RETRY_WAIT
    RETRY_WAIT --> RUNNING
    RUNNING --> PARTIALLY_SUCCEEDED
    PARTIALLY_SUCCEEDED --> RUNNING
    RUNNING --> FAILED
    QUEUED --> CANCELED
    RUNNING --> CANCEL_REQUESTED
    CANCEL_REQUESTED --> CANCELED
    QUEUED --> EXPIRED
~~~

A job already in `SUCCEEDED` must not revert to `RUNNING` due to a late-arriving stale event. If business logic requires rerunning, create a new job or a new generation linked to the prior job. This preserves history and avoids skewing success rate reports.

### State transitions must be atomic

If two workers receive the same job due to duplicate delivery, they must not both update state and write results uncoordinated. Use:
- Conditional updates based on current state.
- Optimistic concurrency with versions.
- Time-bounded leases/locks.
- Unique constraints on attempts or idempotency keys.
- Transactions persisting both results and completion state.

Job state must reflect actual work completed, not merely whether a queue message was acked.

## 3. Designing job tracking data

A job record can store:

| Field | Purpose |
|---|---|
| `job_id` | Unique job identifier |
| `job_type` | Business type or pipeline type |
| `tenant_id` / `owner` | Owning entity or team per data policy |
| `status` | Current state |
| `created_at` | Creation timestamp |
| `accepted_at` | System acceptance timestamp |
| `started_at` | First execution start timestamp |
| `completed_at` | Final completion timestamp |
| `deadline_at` | Completion deadline |
| `progress_current` | Completed units count |
| `progress_total` | Expected total units |
| `progress_unit` | Items, files, records, partitions, or other units |
| `success_count` | Succeeded task/item count |
| `failure_count` | Failed task/item count |
| `retry_count` | Retry count |
| `attempt_count` | Total attempts |
| `result_ref` | Reference to results or artifacts |
| `error_code` | Final or latest error code |
| `version` | State version to prevent overwrites |
| `correlation_id` | Links logs, traces, and workflows |

Not every job knows its total item count upfront. For streaming jobs or crawls of unknown size, `progress_total` can be null and UIs should show indeterminate progress rather than fabricating a percentage.

### Attempt table

Storing attempts separately enables tracking retries and costs:

| Field | Meaning |
|---|---|
| `attempt_id` | Attempt identifier |
| `job_id` / `task_id` | Parent job or task |
| `attempt_number` | Sequential attempt number |
| `worker_id` | Worker or execution environment |
| `started_at` / `ended_at` | Execution interval |
| `outcome` | Success, transient failure, permanent failure, timeout, canceled |
| `error_code` | Error code |
| `retryable` | Whether eligible for retry per policy |
| `resource_ref` | Invocation, pod, container, or VM ID |
| `cpu_time` | CPU time if measurable |
| `memory_peak` | Peak memory |
| `gpu_time` | Accelerator time if applicable |
| `bytes_read` / `bytes_written` | Data volume |
| `cost_estimate` | Estimated cost if calculable |

Do not overwrite previous attempts on retry. Each attempt is an immutable historical record.

### Storing event history

Maintain both a current-state job table and an append-only event table:
- `JobCreated`.
- `JobQueued`.
- `JobStarted`.
- `ProgressUpdated`.
- `AttemptFailed`.
- `RetryScheduled`.
- `TaskCompleted`.
- `JobCompleted`.
- `JobCanceled`.

The current-state table serves fast queries; event history supports auditing, reconstructing progress, and investigating discrepancies. Include sequence numbers/versions to handle delayed or duplicate events.

## 4. Measuring job progress

Progress should reflect completed work relative to expected total work.

When items carry roughly equal weight:

\[
Progress(\%) = \frac{CompletedItems}{TotalItems} \times 100
\]

For example, a job has 2,000 files and 1,500 files have finished:

\[
Progress = \frac{1500}{2000} \times 100 = 75\%
\]

This is progress by item count. If files vary widely in size or processing time, 75% of files does not mean 75% of total work or 25% of remaining time.

### Weighted progress

When items vary in weight, use weights:

\[
Progress(\%) =
\frac{\sum_{i \in completed} w_i}
{\sum_{i \in all} w_i} \times 100
\]

Weights can be:
- Bytes to process.
- Record counts.
- Page counts.
- Frame counts.
- Estimated CPU units.
- Calibrated complexity scores.

Choose weights tailored to the workload. Byte counts fit file transfers well, yet may poorly reflect decompression or content-analysis complexity.

### Stage-based progress

Multi-stage jobs can report per stage:
1. Download inputs.
2. Validate.
3. Transform.
4. Persist outputs.
5. Publish results.

You can assign weights per stage—for instance 10%, 10%, 55%, 20%, 5%. Total progress equals the sum of completed stage weights plus fractional progress of the active stage.

Calibrate weights using historical duration or effort. If `Transform` takes 80% of runtime yet receives only 20% weight, the percentage shoots up quickly and stalls, misleading users.

### Do not double-count progress on retries

If a task completes on attempt 1 yet the message redelivers due to an ack failure, attempt 2 must not increment progress again. Progress must key off task identity and terminal outcome, not successful attempt counts.

Use unique task IDs or idempotency keys so each business completion counts only once.

### Can progress decrease?

For jobs over a fixed dataset, progress should generally increase monotonically. However, if discovery uncovers additional items mid-run or validation drops items, the denominator shifts and percentages can drop.

Choose one approach:
- Lock the total before starting.
- Display `completed / discovered` and indicate the total is still changing.
- Separate discovery and processing phases.
- Label progress as an estimate while the total remains unstable.

Never silently mutate the denominator so users think the job regressed.

### ETA (estimated time remaining)

When processing rates are relatively steady:

\[
ETA \approx \frac{RemainingWork}{ObservedThroughput}
\]

For example, with 3,000 records remaining and a recent average rate of 100 records/second:

\[
ETA \approx 30\ seconds
\]

Use windowed moving averages or percentiles to prevent wild ETA swings. Treat ETAs as estimates, especially when item sizes, retries, or dependency latencies fluctuate.

## 5. Tracking progress at job, task, and attempt levels

Three levels provide three perspectives:

- **Job-level:** overall business state, progress, deadline, result, and total cost.
- **Task-level:** which tasks are pending, running, retrying, succeeded, or failed.
- **Attempt-level:** which executions consumed how much time/resources and why they failed.

A dashboard showing only job-level metrics cannot explain why a job is slow. Task-level exposes stuck partitions; attempt-level pinpoints recurring errors by worker, zone, or dependency.

### Key timestamps

- `created_at`.
- `accepted_at`.
- `enqueued_at`.
- `dequeued_at`.
- `started_at`.
- `heartbeat_at`.
- `progress_updated_at`.
- `attempt_ended_at`.
- `retry_scheduled_at`.
- `completed_at`.

From these you can derive:
- Admission delay = `accepted_at` - `created_at`.
- Queue wait = `started_at` - `enqueued_at`.
- Execution duration = `attempt_ended_at` - `started_at`.
- Retry wait = `next_attempt_started_at` - `previous_attempt_ended_at`.
- End-to-end duration = `completed_at` - `created_at`.
- Deadline slack = `deadline_at` - `completed_at`.

Standardize timezones and synchronize clocks across producers, queues, workers, and databases. Clock skew can produce negative durations or inverted event sequences.

## 6. Defining success rates properly

No single success rate fits every goal. Explicitly specify the denominator, time window, and retry treatment.

### Final job success rate

Computed over jobs reaching a terminal state within the chosen cohort:

\[
FinalSuccessRate =
\frac{SucceededJobs}
{SucceededJobs + FailedJobs + TimedOutJobs + CanceledJobs}
\times 100
\]

User-canceled jobs may be excluded from the denominator when measuring technical execution reliability, provided the rule is documented. Do not include currently running jobs in the denominator when measuring terminal outcomes; doing so artificially depresses success rates during peak load.

### First-attempt success rate

Measures the proportion of jobs/tasks succeeding on their very first try:

\[
FirstAttemptSuccessRate =
\frac{JobsSucceededOnFirstAttempt}
{JobsWithAtLeastOneAttempt}
\times 100
\]

This metric reveals baseline stability and reliance on retries.

### Eventual success rate

Measures the proportion of jobs that ultimately succeed after exhausting policy-allowed retries:

\[
EventualSuccessRate =
\frac{JobsEventuallySucceeded}
{EligibleJobsWhoseRetryWindowClosed}
\times 100
\]

Wait until the retry window closes or jobs reach terminal states. Computing too early misclassifies actively retrying jobs.

### Task success and partial success

For multi-task jobs:

\[
TaskSuccessRate =
\frac{SuccessfulTasks}
{CompletedTasks + FailedTasks}
\times 100
\]

A job can end as `PARTIALLY_SUCCEEDED` if business rules permit partial completion. Define:
- What minimum task threshold makes the job acceptable?
- Can failed tasks be skipped?
- Must a list of failed items be exported?
- Are partial results usable?
- Who decides whether a partial-success job counts as succeeded or failed?

Never count a partial job as a full success if business rules require 100% of items processed.

### On-time success rate

When deadlines apply:

\[
OnTimeSuccessRate =
\frac{JobsSucceededBeforeDeadline}
{EligibleTerminalJobs}
\times 100
\]

A job finishing past its deadline may be a technical success yet a business SLA failure. Track final success and on-time success separately.

## 7. Distinguishing errors, retries, and final outcomes

Retries boost eventual success while masking baseline quality issues and inflating costs.

### Classifying attempt outcomes

- **Success:** attempt completed with valid outputs.
- **Transient failure:** temporary error likely to recover, such as throttling or network resets.
- **Permanent failure:** invalid input or business error unfixable by retrying.
- **Timeout:** attempt exceeded its execution deadline.
- **Canceled:** stopped by user request or policy.
- **Unknown outcome:** worker lost connectivity after triggering a side effect; uncertain whether it committed.

Unknown outcomes are especially critical. Never retry blindly when a side effect may already have occurred. Use idempotency keys, transaction records, or reconciliation.

### Retry metrics

Monitor:
- Attempts per job.
- Retry count per task.
- First-attempt failure rate.
- Retry success rate.
- Retry exhaustion rate.
- Dead-letter count.
- Duplicate delivery count.
- Retry delay.
- Cost spent on failed attempts.

A job succeeding after 5 retries still counts as one succeeded job, yet incurred 5 attempts and may have consumed several times the normal resources.

### Backoff and retry budgets

Use capped exponential backoff with jitter to prevent synchronized worker retries. Bound attempt counts, total retry age, or total retry budgets. Route permanent failures to terminal failure states or DLQs instead of looping endlessly.

### Idempotency and duplicates

Queues provide at-least-once delivery in many setups. Consumers can receive the same message multiple times. Use:
- Business-operation idempotency keys.
- Unique constraints or conditional writes.
- Inbox/deduplication records.
- Transactions recording both results and state.
- Outboxes when emitting events post-commit.

Never use `attempt_id` as a business idempotency key because every retry generates a new `attempt_id`. Keys must remain invariant across redeliveries.

## 8. Measuring per-job costs

Per-job cost should encompass all resources consumed to produce the outcome, including failed attempts, retries, and allocated overhead.

A general model:

\[
JobCost =
ComputeCost + StorageCost + NetworkCost +
AcceleratorCost + OrchestrationCost + SharedCost
\]

Depending on architecture, include databases, queues, observability, licensing, and data transfers.

### Compute cost

For VMs/nodes billed by allocated duration:

\[
ComputeCost =
\sum_{r} BillableHours_r \times EffectiveRate_r
\]

If jobs share nodes across multiple workloads, allocate node costs by CPU/memory requests, actual usage, or reserved capacity.

For functions/containers billed by resource-time:

\[
ComputeCost =
CPUTime \times CPUUnitRate +
MemoryTime \times MemoryUnitRate
\]

Use this formula only when the provider genuinely meters CPU and memory separately. Other services bill by instance configuration or request/duration formulas.

### Cost per successful job

\[
CostPerSuccessfulJob =
\frac{TotalAllocatedJobCost}
{SuccessfulJobs}
\]

To measure the cost of meeting deadlines:

\[
CostPerOnTimeJob =
\frac{TotalAllocatedJobCost}
{OnTimeSuccessfulJobs}
\]

Align time windows, workload scopes, currencies, and cost bases. While a job is still running, current cost is only an estimate.

### Retry costs

Total cost must sum across all attempts:

\[
JobCost = \sum_{a=1}^{n} AttemptCost_a + AllocatedOverhead
\]

Do not count only the final successful attempt. If attempt 1 ran for 10 minutes and timed out, and attempt 2 ran for 2 minutes and succeeded, all 12 minutes of resource-time may incur charges.

### Queue wait is not necessarily a compute charge

Time spent waiting in a queue generally consumes no worker compute, though it can incur queue/storage charges or standby capacity costs. Distinguish:
- Queue wait.
- Worker execution.
- Provisioned idle capacity.
- Retry delay.
- Orchestration state duration.

If worker VMs stay running continuously waiting for jobs, idle costs should be allocated to workloads according to policy.

## 9. Allocating shared resource costs

Multiple jobs often share a worker pool or Kubernetes node. Cloud billing may report only VM/node-hours without per-job breakdowns. Choose an allocation driver.

| Resource | Suggested allocation driver |
|---|---|
| Shared VM/node CPU | CPU-seconds or CPU request-time |
| Shared VM/node memory | Memory working-set-time or memory request-time |
| GPU workers | GPU-seconds, VRAM allocation, or device-time |
| Object storage | Bytes stored × retention duration |
| Data transfer | Bytes read/written per job |
| Queues | Message count/bytes or operation count |
| Databases | Query time, transaction time, or resource usage |
| Orchestration | State transitions, execution duration, or fixed share |
| Monitoring/logging | Log/trace bytes per job or service share |

### CPU and memory allocation

When workers run multiple jobs concurrently, CPU time can be measured per process/container or cgroup. Memory is trickier because jobs can share caches and heaps. You can allocate via memory request-time or per-worker working-set estimates, while explicitly documenting it as an allocation model.

Never attribute a worker's full RSS to every concurrent job—that double-counts memory. If per-job memory cannot be isolated directly, use a reasonable driver and tag its confidence level.

### Allocating idle capacity

If a worker pool keeps spare headroom for latency or availability, idle costs can be allocated:
- Proportional to each workload's peak capacity share.
- By CPU/memory reservations.
- Proportional to actual usage.
- As shared platform overhead.

Pick a stable policy so reports remain comparable across periods. Do not change allocation drivers every month just to make one workload look cheaper.

## 10. Linking costs to jobs via correlation and resource telemetry

To tie jobs to billing costs, propagate identifiers across every layer:

`job_id` → `task_id` → `attempt_id` → `worker_id` → `invocation_id` / `pod_uid` / `container_id` / `vm_id` → billing meter.

### Minimum metadata

Logs/traces/metric events should include where appropriate:
- `job_id`.
- `task_id`.
- `attempt_id`.
- `job_type`.
- `tenant`/`team` or `cost_center`.
- `worker_id`.
- Execution environment.
- Region/zone.
- Function version or image digest.
- `correlation_id`/`trace_id`.

Do not attach `job_id` as a metric label at high scale if your metrics backend cannot handle high cardinality. Millions of jobs will explode into millions of time series. Keep `job_id` in structured logs, traces, or fact tables; aggregate metrics by `job_type`, queue, status, and environment.

### Context propagation

When a job invokes another function or publishes a new message, carry `correlation_id` and business `job_id` in message metadata. Never rely on thread-locals or process memory, as work crosses queues, separate workers, and distinct execution environments.

### Resource mapping

For containers, record Pod UID and container ID alongside attempts. For VM workers, log worker process IDs and execution windows. For serverless, record invocation/request IDs per provider support. Then join resource telemetry with billing exports by resource ID/SKU/time window.

## 11. Example tracking table structure

Logical tables can be structured as follows:

~~~sql
CREATE TABLE jobs (
    job_id           VARCHAR(128) PRIMARY KEY,
    job_type         VARCHAR(80) NOT NULL,
    status           VARCHAR(32) NOT NULL,
    created_at       TIMESTAMP NOT NULL,
    accepted_at      TIMESTAMP,
    started_at       TIMESTAMP,
    completed_at     TIMESTAMP,
    deadline_at      TIMESTAMP,
    progress_current BIGINT,
    progress_total   BIGINT,
    progress_unit    VARCHAR(32),
    success_count    BIGINT DEFAULT 0,
    failure_count    BIGINT DEFAULT 0,
    retry_count      BIGINT DEFAULT 0,
    version          BIGINT NOT NULL
);

CREATE TABLE job_attempts (
    attempt_id       VARCHAR(128) PRIMARY KEY,
    job_id           VARCHAR(128) NOT NULL,
    task_id          VARCHAR(128),
    attempt_number   INTEGER NOT NULL,
    started_at       TIMESTAMP,
    ended_at         TIMESTAMP,
    outcome          VARCHAR(32),
    error_code       VARCHAR(80),
    worker_id        VARCHAR(128),
    resource_ref     VARCHAR(256),
    cpu_seconds      DECIMAL(18,6),
    memory_gib_sec   DECIMAL(18,6),
    bytes_read       BIGINT,
    bytes_written    BIGINT
);
~~~

This is an illustrative schema. Production tables need indexes on `job_id`, `status`, `created_at`, and `job_type`, plus time-based partitioning for high volumes. Enforce appropriate retention, encryption, access controls, and data deletion policies.

### Updating progress safely

When a task completes, update the task result and aggregate progress atomically in a transaction or via a deduplicating event consumer. Never increment `progress_current` on every message receipt if messages can redeliver.

Use a unique key on `(job_id, task_id)` so each task's terminal result counts once. If jobs are partitioned, persist per-partition state so aggregates can be recomputed if events are dropped or delayed.

## 12. Job tracking dashboards

Dashboards should serve three audiences: job requesters, operations teams, and FinOps/cost teams.

### User/business dashboard

Display:
- Job ID and job type.
- Current status.
- Progress and unit of measurement.
- Succeeded/failed/in-progress item counts.
- ETA when sufficient data exists.
- Start time and projected completion.
- Outcomes or artifact download links.
- Cancel or retry actions where authorized.

Never display fake percentages when total size is unknown. Show "processed 2,400 items" instead of "60%".

### Operations dashboard

Break down by job type, queue, and worker pool:
- Jobs `queued`/`running`/`retry_wait`.
- Oldest queued job age.
- Queue wait p50/p95/p99.
- Execution duration p50/p95/p99.
- Jobs `succeeded`/`failed`/`timed_out`.
- First-attempt and eventual success rates.
- Retry counts and retry exhaustion.
- Partial successes.
- DLQ depth.
- Worker concurrency and utilization.
- Missed deadlines and throughput.

### Cost dashboard

Display:
- Total job cost.
- Cost per successful job.
- Cost per on-time job.
- Cost by `job_type`/tenant/team.
- Compute, storage, network, accelerator, and shared costs.
- Cost of retries/failures.
- Estimated cost for active jobs.
- Actual cost reconciled against billing.
- Unallocated cost and confidence level.

Enable drill-down from month → job type → job → task → attempt to investigate cost spikes.

## 13. Essential metrics and alerts

### Progress and throughput metrics

- `jobs_created_total`.
- `jobs_queued`.
- `jobs_running`.
- `jobs_succeeded_total`.
- `jobs_failed_total`.
- `tasks_completed_total`.
- `tasks_failed_total`.
- `job_progress_ratio`.
- `job_queue_wait_seconds`.
- `job_execution_seconds`.
- `job_end_to_end_seconds`.
- `completed_items_per_second`.

Counters should increase monotonically; gauges represent point-in-time counts like active jobs. Histograms fit durations and queue wait times.

### Quality metrics

- `first_attempt_success_rate`.
- `eventual_success_rate`.
- `on_time_success_rate`.
- `retry_attempts_per_job`.
- `partial_success_jobs`.
- `dead_letter_jobs`.
- `duplicate_task_events`.
- `job_timeout_total`.

Success rates are usually computed in dashboard queries from counters or fact tables by cohort rather than emitting raw gauges without clear denominators.

### Cost metrics

- `job_cost_estimated`.
- `job_cost_actual`.
- `job_compute_seconds`.
- `job_cpu_seconds`.
- `job_memory_gib_seconds`.
- `job_gpu_seconds`.
- `job_bytes_processed`.
- `job_retry_cost`.
- `cost_per_successful_job`.

Cost metrics do not all have to be emitted directly by workers. They can be computed in FinOps pipelines by joining attempt telemetry with billing exports.

### Example alerts

- Jobs queued longer than SLA.
- Running job missing heartbeats beyond threshold.
- Success rate drops below threshold.
- Abnormal spike in retry rates.
- DLQ depth climbing continuously.
- On-time success rate drops.
- Cost per successful job exceeds baseline.
- Individual job exceeds resource budget.
- Unallocated cost exceeds allowed percentage.
- Job runs longer than p99 baseline or deadline.

Alerts need defined windows, thresholds, owners, and runbooks. Avoid firing alerts simply because a job runs long if that job type is designed for multi-hour execution.

## 14. Detecting hung jobs and stalled progress

A job in `RUNNING` without recent progress updates is not necessarily hung; it might be processing a massive item or waiting on a dependency.

Use heartbeats or leases:
- Workers emit periodic heartbeats.
- Scheduler detects overdue heartbeats.
- Job/task is flagged as suspect.
- System inspects leases and attempt states.
- If the worker truly died, close the attempt and retry the task per policy.

Never conclude failure from heartbeats alone. Workers can pause or hit network partitions. Enforce lease expiry, fencing tokens, or attempt generations to stop old workers from writing after a task is reassigned.

### Progress heartbeats

Heartbeats can carry:
- `attempt_id`.
- `worker_id`.
- `last_progress_at`.
- Current item or checkpoint.
- `lease_expiry`.
- Worker health.

Do not emit heartbeats too frequently for jobs with millions of tasks; pick an appropriate cadence and batch updates or separate heartbeats from progress events.

### Stale progress

A job may send heartbeats while progress stays frozen. Investigate:
- Is the current item unusually large?
- Is the worker blocked on an API/database?
- Is there lock contention?
- Are queue consumers paused?
- Is there memory pressure or CPU throttling?
- Are checkpoints failing?
- Is the job waiting on a business condition?

Inspect execution traces and dependency metrics to diagnose rather than blindly retrying in a loop.

## 15. Handling partial success and final outcomes

Batch jobs can often succeed partially. Define clear outcome models:
- All-or-nothing.
- Partial success accepted.
- Partial success requires operator review.
- Failed items can be retried.
- Certain items can be skipped under business rules.

For instance, an import job processes 10,000 records: 9,950 succeed and 50 are rejected for bad data. If business rules allow importing valid records, the job can finish as `PARTIALLY_SUCCEEDED` alongside an error report. If all-or-nothing is required, roll back/compensate or mark `FAILED`.

### Outcome reporting

Persist:
- Total items discovered.
- Items attempted.
- Items succeeded.
- Items permanently failed.
- Items skipped.
- Items retried.
- Items pending.
- Error summary by code.
- Output artifacts and failed-item list.

Do not save just one generic error string; users need to know which items failed and how to fix/retry them.

### Retrying failed items

You can spawn a child job or retry tasks within the same job generation. Preserve links:
- `parent_job_id`.
- `original_task_id`.
- `retry_job_id` or `attempt_id`.
- Failure reason.
- Operator/action if manually retried.

When partially retrying, overall progress must reflect terminally completed tasks without double-counting tasks that succeeded in the previous run.

## 16. Computing ETAs and completion forecasts

ETAs are useful when total volume is known upfront and processing rates are reasonably steady.

Simple formula:

\[
ETA = \frac{RemainingUnits}{AverageUnitsPerSecond}
\]

Using throughput from a recent window reflects current speed better than lifetime averages. However, too short a window makes ETAs noisy; too long a window lags behind load shifts.

### Multi-stage jobs

Compute ETA across stages:
- Remaining time in the current stage.
- Expected duration of subsequent stages from historical runs.
- Finalization/publish time.
- Expected retries or backoff.

Never sum ETAs of parallel tasks as if they ran sequentially. With N concurrent workers, aggregate throughput comes from job-wide task completions.

### Jobs with unknown totals

For crawls or streams:
- Display throughput and elapsed time.
- Display discovered item counts.
- Show status "discovering" or "total unknown".
- Omit ETAs if no reliable estimate exists.

Display an ETA range rather than a falsely precise single number.

## 17. Example: tracking an invoice processing job

A job processes 50,000 invoices in batch. Each invoice is a task. The system runs 20 workers.

After 10 minutes:
- 32,000 tasks succeeded.
- 1,000 tasks failed transiently and are retrying.
- 500 tasks failed permanently.
- 16,500 tasks have no terminal outcome yet.
- 200 attempts succeeded via retries among prior tasks.

If progress counts terminally completed tasks:

\[
Progress = \frac{32{,}000 + 500}{50{,}000} \times 100 = 65\%
\]

Depending on business rules, permanent failures may count as "processed" for progress yet not as successes. Dashboards should separate:
- Processed: 32,500.
- Succeeded: 32,000.
- Failed: 500.
- Pending/retrying: 17,500.

Success rate across tasks with terminal outcomes:

\[
TaskSuccessRate =
\frac{32{,}000}{32{,}000 + 500} \times 100
\approx 98.46\%
\]

Do not include the 17,500 pending tasks in this denominator. Report first-attempt success rate and eventual success rate separately as well.

Suppose total allocated cost to date is 42 currency units. This is an estimate while the job is running. When the job finishes, total cost is 60 and 49,500 invoices were accepted:

\[
CostPerAcceptedInvoice = \frac{60}{49{,}500}
\approx 0.001212
\]

Because 500 permanently failed invoices were rejected, the denominator should not be 50,000. Reports can include cost per attempted invoice alongside it to evaluate total workload spend.

## 18. Example: calculating attempt and retry costs

One task runs across three attempts:

| Attempt | Outcome | Compute cost | Storage/network cost |
|---|---|---:|---:|
| 1 | Timeout after 90 seconds | 0.030 | 0.004 |
| 2 | Dependency throttling after 30 seconds | 0.010 | 0.002 |
| 3 | Success after 45 seconds | 0.015 | 0.003 |
| **Total** |  | **0.055** | **0.009** |

Total task cost:

\[
0.055 + 0.009 = 0.064
\]

Counting only the final succeeded attempt gives 0.018, understating actual cost by roughly 72% in this example. Retry costs must roll back up to the originating job/task.

When multiple tasks run concurrently, sum attempt costs and allocate orchestration/worker-pool overhead per policy. Never charge the entire node's full cost to every individual task.

## 19. Reconciling job telemetry with billing

Billing exports generally report usage by resource, SKU, region, and time window. They rarely contain `job_id`. Use telemetry to allocate costs.

Procedure:
1. Capture attempt start/end timestamps and resource identities.
2. Capture CPU/memory/GPU/storage/network usage per attempt if available.
3. Extract billing usage by resource ID/SKU/time window.
4. Apportion usage across attempts or workload allocation drivers.
5. Add retry costs and shared overhead.
6. Compare total allocated cost against total billing charges.
7. Record unallocated remainder and variances.

### Reconciling by resource and time

If one worker VM runs 20 jobs concurrently, billing shows a single instance-hour line item. Allocate by each job's CPU-seconds; allocate idle time and system overhead separately. Relying strictly on wall-clock duration can overcharge CPU costs to I/O-bound jobs.

### Estimated vs. actual cost

While a job runs, cost estimates can use resource telemetry and current rate cards. Once billing exports finalize, update to actuals. Label figures clearly:
- `estimated`.
- `reconciled`.
- `provisional`.
- `final`.

Never present estimates as final invoices. Billing data can arrive delayed or change due to discounts, credits, and rounding.

### Variances to investigate

- Worker terminated before writing attempt end timestamps.
- Delayed billing records.
- VMs running outside job execution windows.
- Multiple jobs sharing a single worker.
- Retry attempts missing correlation IDs.
- Ancillary resources like disks, NAT, or logs left unallocated.
- Meters billing by provisioned time rather than actual CPU time.
- Commitment discounts applied at the account level.

Reports should include allocated percentage and unallocated percentage so readers understand confidence levels.

## 20. Retention, security, and access control for job data

Job telemetry may contain customer details, file references, error messages, or business metadata. Ensure:
- Store only necessary data.
- Never log sensitive payloads.
- Encrypt data at rest and in transit.
- Enforce authorization by tenant/team.
- Restrict who can view result artifacts.
- Set retention for job details, attempts, and logs.
- Purge or anonymize data per policy.
- Audit cancel, retry, and redrive actions.

Do not expose stack traces or internal resource IDs to end users unnecessarily. UIs can display error codes and remediation steps while restricting technical details to operators.

### Cardinality and observability costs

Never create metric labels for individual `job_id` or `task_id` values at large scale. Instead use:
- Aggregated metrics by `job_type`, queue, status, region, and worker pool.
- Structured logs to query individual jobs.
- Traces for sampled or selected executions.
- Fact tables/warehouses to compute unit costs and cohort success rates.

Logs and traces also carry ingestion/retention costs; instrument enough for debugging without emitting giant payloads per item.

## 21. Operating and investigating a job

When users report a slow or failed job:

1. Look up the job by `job_id`.
2. Inspect status, created/accepted/started timestamps, and deadline.
3. Check progress, total, and `last_progress_at`.
4. Identify which tasks are pending or failed.
5. Open attempt history for failing tasks.
6. Check error codes, workers, regions, and dependencies.
7. Classify as transient, permanent, or unknown outcome.
8. Check retry budgets, DLQs, and duplicates.
9. Check CPU, memory, queue wait, and dependency latency.
10. Inspect estimated cost and retry spend.
11. Decide whether to retry tasks, retry the job, cancel, or reconcile manually.
12. Record final outcome and root cause afterward.

Do not retry an entire job because one task failed if other tasks already triggered non-repeatable side effects. Retry per task or partition with idempotency.

### Runbook for stuck jobs

- Verify heartbeats and leases.
- Check whether the worker is alive or disconnected.
- Verify the attempt still holds write ownership.
- Inspect queue visibility/ack state.
- Check dependency timeouts.
- Compare latest progress events.
- If the lease expired, fence the old worker before reassigning.
- Record attempt failure reason.
- Retry within budget or route to DLQ.
- Verify results and deduplicate after recovery.

## 22. Workflow for building a job tracking system

1. **Define jobs:** business purpose, owner, inputs/outputs, and deadlines.
2. **Define tasks:** granular units, keys, partitions, and retry boundaries.
3. **Design state machine:** states, transitions, and terminal states.
4. **Design schemas:** job, task, attempt, and event history tables.
5. **Choose progress model:** item counts, weighted work, or stage progress.
6. **Define success:** first-attempt, eventual, partial, and on-time criteria.
7. **Instrument workers:** start/end, heartbeats, progress, resource usage, and outcomes.
8. **Propagate correlation:** job/task/attempt/resource IDs across queues and workers.
9. **Design idempotency:** duplicate delivery, retries, and side effects.
10. **Collect billing:** usage quantities, SKUs, resource IDs, and effective rates.
11. **Choose cost allocation:** direct, shared, idle, and retry overhead.
12. **Build dashboards:** business progress, operational health, and unit costs.
13. **Configure alerts:** stale progress, queue age, failures, retries, and cost anomalies.
14. **Reconcile:** compare allocated costs against billing totals.
15. **Review:** update baselines, thresholds, and retention as workloads evolve.

## 23. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Counting invocations instead of jobs | Retries inflate job counts | Track `job_id` and `attempt_id` separately |
| Computing progress from message acks | Ack does not equal business completion | Update upon committing task results |
| Incrementing progress on every successful retry | Progress exceeds 100% | Deduplicate by task identity |
| Putting running jobs in success rate denominator | Artificially lowers success rate | Use terminal cohorts and publish windows |
| Blending first-attempt and eventual success | Masks baseline reliability | Report both metrics separately |
| Treating partial success as full success | Misstates business outcomes | Define accepted outcome criteria |
| Ignoring retry costs | Artificially low unit costs | Sum all attempts and overhead |
| Assigning full VM cost to every job | Double-counts expenses | Apportion shared nodes via drivers |
| Using `job_id` as a metric label | Explodes cardinality and metric bills | Use logs/traces/fact tables |
| Treating heartbeats as completion proof | Jobs can stay alive without progressing | Track progress and leases |
| Not handling late-arriving events | State regresses or overwrites | Use versions/sequences and conditional updates |
| Unaligned time windows | Costs and outputs fall in mismatched periods | Standardize on UTC and cohorts |
| Labeling estimates as actuals | Causes flawed budget decisions | Tag status as provisional/reconciled/final |

## 24. Production checklist

### Job model and progress
- [ ] Stable `job_id` and `job_type` exist.
- [ ] Jobs, tasks, attempts, and invocations are clearly distinguished.
- [ ] State machine defines explicit transitions and terminal states.
- [ ] Task identity prevents double-counting progress.
- [ ] Progress defines units, totals, and rules when totals are unknown.
- [ ] Weighted progress is calibrated when items vary in size.
- [ ] ETAs are labeled as estimates.

### Success and reliability
- [ ] First-attempt success rate is defined.
- [ ] Eventual success rate is defined.
- [ ] Running jobs are excluded from terminal success denominators.
- [ ] Partial success follows explicit business rules.
- [ ] Retries and attempts are persisted separately.
- [ ] Idempotency and deduplication are enforced.
- [ ] Heartbeats, leases, and fencing exist where needed.
- [ ] DLQs, retry budgets, and redrive runbooks exist.

### Cost and observability
- [ ] Every attempt records timestamps and resource references.
- [ ] Retry costs roll up to the job.
- [ ] Shared resources have documented allocation drivers.
- [ ] Idle capacity and orchestration overhead are accounted for.
- [ ] Cost per successful job and per on-time job are calculated.
- [ ] Cost estimates are separated from billing actuals.
- [ ] Total allocated cost reconciles against billing exports.
- [ ] Unallocated cost percentage is tracked.
- [ ] Metrics avoid high-cardinality `job_id` labels.
- [ ] Logs/traces carry correlation IDs.
- [ ] Dashboards slice by job type, status, queue, and cost.
- [ ] Alerts exist for stale progress, queue age, retries, failures, and cost anomalies.

### Governance
- [ ] Each job type has an owner and deadline.
- [ ] Retention and access policies exist for job/attempt data.
- [ ] Cancel/retry/redrive operations are audited.
- [ ] Runbooks exist for investigating stuck jobs.
- [ ] Baselines and review cadences exist for success rates and unit costs.

## Conclusion

Effective job tracking requires stable identifiers and a data model separating jobs, tasks, attempts, and worker invocations. Progress should reflect completed tasks or weighted work rather than delivered messages or retry counts. Success rates must distinguish first-attempt, eventual, partial, and on-time outcomes, with denominators scoped strictly to eligible terminal cohorts. Per-job costs must sum all attempts, retries, and policy-allocated shared resources; billing exports anchor actuals while telemetry enables attribution and root-cause explanation. Combining state machines, progress events, heartbeats/leases, correlation IDs, dashboards, and reconciliation lets operations teams see exactly where every job stands, whether results are trustworthy, and how many resources each completed outcome consumes.

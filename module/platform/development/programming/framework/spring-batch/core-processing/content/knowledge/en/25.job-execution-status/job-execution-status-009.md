# Mapping Status to Monitoring

In Spring Batch, Job and Step statuses indicate the execution lifecycle of a run. A monitoring system needs to translate these statuses into clear operational signals so dashboards, alerts, and support runbooks can answer key questions: is the Job running or finished, did it succeed, was it intentionally stopped, is there an error requiring intervention, and is progress stalled?

Mapping must distinguish **BatchStatus**, **ExitStatus**, and business outcomes. These three concepts are related but not synonymous. Looking at only one status field can cause monitoring to report success when output data fails validation, or report an error when the Job is merely waiting to stop on an operational request.

## 1. Why Map Statuses?

Spring Batch persists execution statuses in JobRepository. These statuses serve Job orchestration, restarts, and progress tracking. Monitoring typically needs a simpler model to display lifecycles on dashboards and trigger alerts.

For example, a dashboard might need categories such as:

- **Queued / Pending:** Job has been requested but has not started executing. This is usually a status of the scheduler or external orchestrator, not BatchStatus.
- **Starting:** Job is initializing.
- **Running:** Job is executing.
- **Stop requested:** Stop has been requested but the Job has not finished yet.
- **Succeeded:** Job completed technically.
- **Failed:** Job ended due to an error.
- **Stopped:** Job stopped on request or flow condition.
- **Abandoned:** Execution marked not to continue.
- **Unknown / Needs investigation:** Reliable status could not be determined.

Consistent mapping helps:

- Dashboards present a uniform view across multiple Jobs.
- Alerts fire only when status requires operator intervention.
- Track runtime, queue wait time, and processing time.
- Separate technical errors from business outcomes.
- Reconcile JobExecution with schedulers, message brokers, and target systems.
- Build SLA reports and run histories.

Never alter raw statuses in JobRepository just to make dashboard rendering easier. Keep Spring Batch statuses intact and build a mapping layer in the monitoring tier.

## 2. Distinguishing BatchStatus and ExitStatus

Spring Batch stores two important status types for JobExecution and StepExecution:

| Property | Meaning | Used for |
| --- | --- | --- |
| **BatchStatus** | Execution lifecycle status managed by Spring Batch | Knowing whether Job/Step is running, completed, failed, or stopped |
| **ExitStatus** | Outcome code used for flow routing and describing execution outcome | Selecting transitions and expressing granular outcomes |

BatchStatus is an enum with common values:

- STARTING
- STARTED
- STOPPING
- STOPPED
- COMPLETED
- FAILED
- ABANDONED
- UNKNOWN

ExitStatus is an object containing an exit code and description. Common default codes include COMPLETED, EXECUTING, FAILED, NOOP, STOPPED, and UNKNOWN. Applications can also create custom exit codes to describe business outcomes.

For example, a Step may end with BatchStatus COMPLETED while its ExitStatus is a custom code such as COMPLETED_WITH_SKIPS. That means the Step completed execution-wise, yet some items were skipped.

Conversely, a flow may handle a failed Step branch using a recovery Step and end the Job with another status. Therefore, inspect both JobExecution and the associated StepExecutions.

### Do not use ExitStatus in place of BatchStatus

BatchStatus answers “what lifecycle state is the execution in?”. ExitStatus answers “what outcome code did the execution end with and which branch should the flow follow?”.

Monitoring should store both fields:

~~~text
job_execution_id = 8124
batch_status     = COMPLETED
exit_code        = COMPLETED_WITH_SKIPS
exit_description = 12 records were skipped
~~~

If you map exit code COMPLETED_WITH_SKIPS directly to FAILED, dashboards misrepresent the execution lifecycle. If you map BatchStatus COMPLETED directly to business success, dashboards miss the fact that 12 records were rejected.

## 3. Mapping BatchStatus to Operational Status

A basic mapping can look like this:

| BatchStatus | Suggested Monitoring Status | Operational Meaning |
| --- | --- | --- |
| STARTING | STARTING | Job/Step is initializing and preparing resources |
| STARTED | RUNNING | Execution is currently running |
| STOPPING | STOP_REQUESTED | Stop requested, awaiting safe termination |
| STOPPED | STOPPED | Execution stopped; may require restart or operational action |
| COMPLETED | SUCCEEDED | Execution completed technically |
| FAILED | FAILED | Execution failed; inspect exceptions and restartability |
| ABANDONED | ABANDONED | Execution marked not to continue |
| UNKNOWN | UNKNOWN | Cannot determine status reliably |

This is a reference operational mapping. Depending on business rules, COMPLETED may need to be combined with ExitStatus, skip count, or output data checks before being labeled SUCCESS.

### Pending is not a BatchStatus

A Job sitting in a scheduler queue not yet invoked by JobLauncher does not have a running JobExecution. If a dashboard needs to show PENDING, that status must come from the scheduler, request intake API, or application orchestration table.

Do not create a fake JobExecution solely to represent a waiting Job. Link external pending status to JobParameters or a business request ID once the Job is actually launched.

## 4. Mapping in Java

You can translate BatchStatus into an application-specific enum:

~~~java
public enum OperationalStatus {
    STARTING,
    RUNNING,
    STOP_REQUESTED,
    STOPPED,
    SUCCEEDED,
    FAILED,
    ABANDONED,
    UNKNOWN
}
~~~

Mapping function:

~~~java
public OperationalStatus mapStatus(BatchStatus status) {
    return switch (status) {
        case STARTING -> OperationalStatus.STARTING;
        case STARTED -> OperationalStatus.RUNNING;
        case STOPPING -> OperationalStatus.STOP_REQUESTED;
        case STOPPED -> OperationalStatus.STOPPED;
        case COMPLETED -> OperationalStatus.SUCCEEDED;
        case FAILED -> OperationalStatus.FAILED;
        case ABANDONED -> OperationalStatus.ABANDONED;
        case UNKNOWN -> OperationalStatus.UNKNOWN;
    };
}
~~~

The example uses a Java switch expression. If the project targets an older Java version, write an equivalent switch statement or if/else chain.

This function maps lifecycle status only. It does not determine business outcome. You can build a separate evaluation function using ExitStatus, skip count, business validation, and output data.

## 5. Mapping Technical Outcomes to Business Outcomes

A Job may complete technically while its business outcome requires finer classification.

Example:

| BatchStatus | ExitStatus | Skip count | Possible Monitoring Outcome |
| --- | --- | ---: | --- |
| COMPLETED | COMPLETED | 0 | SUCCEEDED |
| COMPLETED | COMPLETED_WITH_SKIPS | 12 | SUCCEEDED_WITH_WARNINGS |
| COMPLETED | NO_DATA | 0 | COMPLETED_NO_DATA |
| FAILED | FAILED | any | FAILED |
| STOPPED | STOPPED | any | STOPPED |
| UNKNOWN | UNKNOWN | unknown | NEEDS_INVESTIGATION |

Exit codes like COMPLETED_WITH_SKIPS or NO_DATA are application conventions, not mandatory Spring Batch defaults. Define codes consistently and document their meanings clearly in operational runbooks.

Example classification method:

~~~java
public String mapBusinessOutcome(
        JobExecution execution,
        long totalSkipCount) {

    if (execution.getStatus() == BatchStatus.FAILED) {
        return "FAILED";
    }

    if (execution.getStatus() == BatchStatus.STOPPED) {
        return "STOPPED";
    }

    if (execution.getStatus() == BatchStatus.UNKNOWN) {
        return "NEEDS_INVESTIGATION";
    }

    if (execution.getStatus() == BatchStatus.COMPLETED
            && totalSkipCount > 0) {
        return "SUCCEEDED_WITH_WARNINGS";
    }

    if (execution.getStatus() == BatchStatus.COMPLETED
            && "NO_DATA".equals(
                    execution.getExitStatus().getExitCode())) {
        return "COMPLETED_NO_DATA";
    }

    if (execution.getStatus() == BatchStatus.COMPLETED) {
        return "SUCCEEDED";
    }

    return "IN_PROGRESS";
}
~~~

This is illustrative logic. Condition order must reflect the Job's business rules. If a Job has a recovery flow or custom ExitStatus, explicitly define which states count as success, warning, or business failure.

Do not rely solely on skip count to judge data quality. One Job may tolerate a number of skipped errors; another Job must fail if even a single item is skipped. You may need to inspect rejection rates, error categories, or reconciliation results before publishing data.

## 6. Job Status and Step Status Can Differ

A Job comprises multiple Steps. Each StepExecution has its own BatchStatus and ExitStatus. The final status of JobExecution is determined by the flow and the Job's execution outcome.

Example flow with recovery:

~~~text
importStep -> FAILED
      |
      v
recordFailureStep -> COMPLETED
      |
      v
flow ends along configured branch
~~~

If the flow handles the error branch and terminates normally, the Job can have a different status from the Step that failed. Thus, a job-level dashboard alone is insufficient for diagnostics.

Display:

- Job BatchStatus and ExitStatus.
- List of StepExecutions with their statuses.
- First failed Step or the Step that triggered the error branch.
- Whether the recovery Step ran.
- Root exceptions and failure details.
- Item read, write, filter, and skip counts.

### Do not inspect only the last StepExecution

The last Step may be a summary or recovery Step. That Step being COMPLETED does not mean all earlier Steps succeeded. Inspect every StepExecution belonging to the JobExecution along with the flow rules applied.

## 7. Collecting Status via JobExecutionListener

JobExecutionListener provides callbacks before and after the Job:

~~~java
public class JobMonitoringListener implements JobExecutionListener {

    private final MonitoringPublisher publisher;

    public JobMonitoringListener(MonitoringPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        publisher.publishStarted(
                jobExecution.getId(),
                jobExecution.getJobInstance().getJobName());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        publisher.publishFinished(
                jobExecution.getId(),
                jobExecution.getStatus().name(),
                jobExecution.getExitStatus().getExitCode(),
                jobExecution.getStartTime(),
                jobExecution.getEndTime());
    }
}
~~~

Register the listener on the Job:

~~~java
return new JobBuilder("dailyImportJob", jobRepository)
        .start(importStep)
        .listener(jobMonitoringListener)
        .build();
~~~

Listeners are well suited for emitting start/finish events, writing structured logs, or updating monitoring systems. However, afterJob only runs when the Job ends per framework lifecycle; it is not a continuous heartbeat for a running Job.

If the publisher calls an external system and fails, never let metric or notification errors unintentionally alter the business outcome. Use logging, an outbox, or an independently retried event publishing mechanism.

## 8. Collecting Status at the Step Level

StepExecutionListener helps track each Step:

~~~java
public class StepMonitoringListener implements StepExecutionListener {

    private final MonitoringPublisher publisher;

    public StepMonitoringListener(MonitoringPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        publisher.publishStepStarted(
                stepExecution.getJobExecutionId(),
                stepExecution.getStepName(),
                stepExecution.getId());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        publisher.publishStepFinished(
                stepExecution.getJobExecutionId(),
                stepExecution.getStepName(),
                stepExecution.getStatus().name(),
                stepExecution.getExitStatus().getExitCode(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getSkipCount());

        return null;
    }
}
~~~

Returning null in afterStep keeps the current ExitStatus unchanged. Returning a different ExitStatus can combine with or change the Step's result per listener rules. Therefore, monitoring listeners should only observe and never arbitrarily alter ExitStatus.

For long-running Steps, beforeStep and afterStep only mark start/end points. To show continuous progress, poll JobRepository via JobExplorer, emit metrics per chunk, or update a heartbeat from an appropriate processing component.

## 9. Using JobExplorer to Read Status

JobExplorer is a read-only API for querying metadata of JobInstance, JobExecution, and StepExecution. It suits dashboards or monitoring services that should not mutate JobRepository directly.

Example retrieving a JobExecution:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    log.info(
            "job={}, status={}, exitCode={}, start={}, end={}",
            execution.getJobInstance().getJobName(),
            execution.getStatus(),
            execution.getExitStatus().getExitCode(),
            execution.getStartTime(),
            execution.getEndTime());
}
~~~

Retrieving per-Step info:

~~~java
if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, exitCode={}, read={}, write={}, skips={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus().getExitCode(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getSkipCount());
    }
}
~~~

Given a Job name, you can look up running executions using the corresponding JobExplorer API, such as findRunningJobExecutions(jobName). When building historical dashboards, paginate by JobInstance/JobExecution rather than loading the entire history into memory.

Do not use JobExplorer to modify statuses. Stop/restart actions belong to JobOperator or an appropriate orchestration API and must enforce operational permissions.

## 10. Monitoring with Micrometer Metrics

Spring Batch supports Micrometer integration to record metrics for Jobs and Steps. In versions with corresponding instrumentation, you can observe timers for Job and Step execution durations, commonly registered under meter names such as spring.batch.job and spring.batch.step.

Metrics help track:

- Job/Step execution duration.
- Run counts per Job or Step.
- Completion status when attached as tags.
- Processing time trends across runs.
- Item volumes and skip counts via configurable counters or supplemental application metrics.

Meter names, tags, and granularity may vary by Spring Batch version, Micrometer registry, and observability configuration. Inspect actual meters in your registry rather than assuming all tags exist.

### Standard metrics and business metrics

Framework metrics show how long executions take. Applications typically need additional business metrics:

| Metric | Meaning |
| --- | --- |
| items_read_total | Total items read |
| items_written_total | Total items written |
| items_skipped_total | Total items/errors skipped |
| chunk_commit_total | Number of chunk commits |
| chunk_rollback_total | Number of chunk rollbacks |
| job_duration_seconds | Job execution duration |
| job_last_success_timestamp | Timestamp of most recent successful Job |
| rejected_ratio | Ratio of rejected records |
| queue_lag_seconds | Message lag if the Job reads from a queue |

These names are illustrative application conventions, not all built-in Spring Batch metrics. Define consistent units, counter/gauge/timer types, and reset semantics.

### Avoiding excessive cardinality

Do not use JobExecution ID, order ID, customer ID, or message ID as metric tags. Each distinct value creates a new time series and rapidly explodes cardinality in the monitoring backend.

Appropriate tags are typically Job name, Step name, environment, status, or data source type with a bounded set of values. High-cardinality IDs belong in logs or traces.

## 11. Structured Logging

Logs help investigate a specific execution. Include searchable, correlatable fields:

- jobName
- jobInstanceId
- jobExecutionId
- stepName
- stepExecutionId
- batchStatus
- exitCode
- startTime and endTime
- readCount, writeCount, skipCount
- exceptionType and errorCode
- correlationId or businessRunId if available

Log example:

~~~java
log.info(
        "batch_job_finished jobName={} jobExecutionId={} status={} exitCode={} durationMs={}",
        jobExecution.getJobInstance().getJobName(),
        jobExecution.getId(),
        jobExecution.getStatus(),
        jobExecution.getExitStatus().getExitCode(),
        durationMillis);
~~~

Do not log entire JobParameters if they may contain tokens, personal info, or sensitive data. Only log approved identifying values required for reconciliation.

Start, finish, and error logs should use stable event names so log aggregation systems can filter them cleanly. Do not rely on free-form message prose as the sole classification label.

## 12. Events and Near Real-Time Status

Dashboards needing near real-time status can receive events from listeners or poll JobExplorer.

An event can have a structure such as:

~~~json
{
  "eventType": "JOB_FINISHED",
  "jobName": "dailyImportJob",
  "jobExecutionId": 8124,
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED_WITH_SKIPS",
  "readCount": 10000,
  "writeCount": 9988,
  "skipCount": 12,
  "occurredAt": "2026-11-15T10:30:00Z"
}
~~~

Events should carry the execution ID and emission timestamp so consumers can handle duplicates or out-of-order delivery. For instance, a STARTED event could arrive after a FINISHED event due to network or queue delays; dashboards must avoid overwriting a terminal status with a stale event.

You can persist events to an outbox in the same metadata or business data transaction if guaranteed delivery is required. If publishing directly from a listener, account for publish failures or redeliveries and design idempotent consumers.

Polling JobExplorer is simpler, though polling frequency must be controlled to avoid overloading the metadata repository. Choose polling intervals based on freshness requirements and Job volume.

## 13. Designing Dashboards for Jobs and Steps

A useful dashboard should show both current status and historical trends:

### Job overview

- Number of currently running Jobs.
- Number of succeeded, failed, and stopped Jobs over a time window.
- Jobs missing a recent success within SLA.
- Jobs running longer than expected thresholds.
- Success rate by Job name.

### JobExecution details

- Job name and JobExecution ID.
- JobInstance ID and sanitized identifying parameters.
- BatchStatus and ExitStatus.
- Start time, end time, and duration.
- List of StepExecutions with their statuses.
- Failure exceptions and controlled stack traces.
- Read/write/filter/skip counts.
- Checkpoints or progress if supplied by the application.

### Step details

- Step name and status.
- Read, process, write, and skip counts.
- Commit and rollback counts.
- Execution duration.
- Partition or worker info if the Step is distributed.
- Most recent error and retry count if metrics are available.

Avoid showing just a single red/green indicator for the whole Job. A COMPLETED_WITH_SKIPS Job may warrant a yellow warning, whereas a STOPPED Job may represent an intentional action.

## 14. Status- and Duration-Based Alerting

Alerts should evaluate status together with context, not just a single enum value:

| Condition | Suggested Action |
| --- | --- |
| Job FAILED | Alert operations team, attach JobExecution ID and failed Step |
| Job UNKNOWN | High-severity alert because status requires reconciliation |
| Job STOPPED outside maintenance window | Alert or require confirmation |
| Job STOPPING for too long | Check workers, transactions, and shutdown behavior |
| Job STARTED exceeding SLA | Check progress, locks, queue lag, and heartbeat |
| Job COMPLETED with skip ratio above threshold | Data quality alert |
| No success within SLA window | Alert on missed schedule or repeated Job failures |
| Continuously growing queue backlog | Check worker throughput and consumption capacity |

### Distinguishing long-running Jobs from stuck Jobs

A Job in STARTED for a long time is not necessarily stuck. It may be processing a large dataset or waiting on I/O. Combine:

- Elapsed time against historical SLA.
- lastUpdated or application-emitted heartbeats.
- Progress in read/write/commit counts.
- Queue lag or worker activity.
- Database locks and query duration.
- Latest Step logs.

If status does not change yet read/write counts keep rising, the Job is likely active. If status does not change, no heartbeat arrives, and no progress occurs for an extended period, investigation is warranted.

Never automatically kill a Job simply for exceeding one generic time threshold. Some Jobs are naturally long-running; use per-Job SLAs and safe stop mechanisms.

## 15. STOPPING, STOPPED, and Stop Requests

STOPPING means a stop request has been recorded, yet the execution has not finished stopping. STOPPED is the stopped state.

When an operator requests a Job to stop, dashboards should clearly display:

1. Who or which system requested the stop.
2. Timestamp of the request.
3. JobExecution ID.
4. Current state: STOPPING or already STOPPED.
5. Which Step/chunk is completing or rolling back.
6. Whether the Job can restart next or needs manual handling.

Do not map STOPPED to FAILED by default. A Job can be stopped intentionally to await approval, maintenance, or source data changes.

Conversely, do not map STOPPED to SUCCEEDED. It is a distinct stopped state and must be represented accurately in monitoring.

## 16. FAILED, ABANDONED, and UNKNOWN

These three statuses require different handling:

**FAILED:** Job/Step terminated due to an error. Inspect exceptions, evaluate restartability, and check committed side effects.

**ABANDONED:** Execution was marked not to continue. This is not a success state; monitoring should retain history and require operational action if needed.

**UNKNOWN:** The framework or repository could not determine status reliably. Never automatically map UNKNOWN to FAILED or COMPLETED. Alert and reconcile metadata before restarting.

For UNKNOWN, avoid launching another execution with the same business input before determining how far the prior execution committed data. Doing so risks duplicate processing.

## 17. Status Mapping in Multi-Tier Systems

A real-world system may include a scheduler, request intake API, Spring Batch manager, workers, and a monitoring system. Each tier has its own lifecycle:

~~~text
Scheduler
  PENDING / SCHEDULED
       |
       v
API / Orchestrator
  ACCEPTED
       |
       v
Spring Batch JobExecution
  STARTING -> STARTED -> COMPLETED / FAILED / STOPPED
       |
       v
Worker StepExecution
  STARTING -> STARTED -> COMPLETED / FAILED
       |
       v
Monitoring
  Operational status + business outcome + metrics
~~~

Do not collapse all statuses into one single enum when tiers have different semantics. Store separately:

- Orchestration status: request/scheduler status.
- Batch status: JobExecution status.
- Step status: status of each StepExecution.
- Business outcome: business result evaluated by the application.

A request can be ACCEPTED without a JobExecution yet. A JobExecution can be STARTED while a worker is waiting on resources. A Job can be COMPLETED while business outcome is REJECTED if final validation finds invalid data.

## 18. Restarts and Monitoring

Monitoring should provide enough context for operators to decide whether restarting is safe:

- JobInstance ID and identifying JobParameters.
- Failed JobExecution ID.
- BatchStatus and ExitStatus.
- Failed StepExecution.
- Committed checkpoints and progress.
- Output data already written.
- Non-transactional side effects already executed.
- Root cause and remediation steps.

JobOperator can support stop/restart operations via corresponding APIs. Never let dashboards auto-restart every FAILED Job without verifying safety, restart limits, and data state.

If JobExecution is FAILED, the same JobInstance can be restarted when the Job allows it and restart conditions are met. If JobExecution is COMPLETED, the same identifying parameters usually cannot start a new run for the same instance. If status is UNKNOWN, investigate before acting.

## 19. Common Pitfalls

### Monitoring only BatchStatus

BatchStatus does not capture full business outcomes. Combine with ExitStatus, skip counts, and output validation.

### Monitoring only ExitStatus

ExitStatus can be a custom code. Use BatchStatus for lifecycle state and ExitStatus for outcomes/flow routing.

### Mapping every COMPLETED to business success

A Job can complete with skips or recovery. Model a separate business outcome when needed.

### Mapping STOPPED to FAILED

STOPPED may be an intentional stop request. Display it separately and retain who requested the stop.

### Mapping UNKNOWN to success or failure

UNKNOWN means status could not be determined. Alert and reconcile before restarting.

### Inspecting only the last JobExecution

A recovery Step can complete after a business Step failed. Inspect all StepExecutions and flow transitions.

### Using a listener to alter ExitStatus when only recording metrics

A listener returning an ExitStatus can affect Step outcomes. Monitoring listeners should leave status intact unless a business rule requires changing it.

### Creating metric tags from execution ID or item ID

Cardinality grows rapidly and overloads the monitoring backend. Put granular IDs in logs/traces and use tags with bounded value sets.

### Treating long-running STARTED Jobs as stuck

Verify progress, heartbeats, SLA, and worker activity before alerting or stopping the Job.

### Emitting events without idempotency

Monitoring messages can arrive duplicated or out of order. Attach execution ID, event time, and sequence/version so consumers handle them properly.

## 20. Workflow for Building Status Mapping

When designing monitoring for Spring Batch, determine:

1. Do you need to track JobExecution, StepExecution, or both?
2. Which BatchStatus maps to which operational status?
3. Which scheduler or API provides pending/queued states?
4. What do default ExitStatus and custom exit codes mean?
5. When a Job is COMPLETED with skips, what is the business outcome?
6. Can a recovery flow cause the Job to complete after a FAILED Step?
7. Which listeners emit start, finish, and failure events?
8. How is JobExplorer used for polling or querying history?
9. Which Micrometer metrics are available out of the box and which business metrics must be added?
10. Do logs include correlation IDs and execution IDs sufficient for investigation?
11. Which alerts rely on status, SLA, heartbeat, or data quality?
12. Does the dashboard distinguish STOPPED, ABANDONED, and UNKNOWN?
13. Does the restart workflow verify JobInstance, checkpoints, and side effects?

Test mapping against every BatchStatus, custom ExitStatus codes, Jobs with recovery Steps, Jobs with skips, stopped Jobs, and executions in UNKNOWN status. Check dashboards, alerts, and logs together to guarantee every system interprets the same status using the same rules.

## Conclusion

Mapping status to monitoring requires keeping BatchStatus, ExitStatus, Step status, and business outcomes distinct. BatchStatus describes execution lifecycle; ExitStatus describes outcome codes and flow routing; business outcomes reflect application data rules. You can collect status via JobExecutionListener, StepExecutionListener, JobExplorer, and Micrometer, then combine structured logs, metrics, events, and SLA-based alerts. Display STOPPING, STOPPED, ABANDONED, and UNKNOWN distinctly, inspect all StepExecutions when recovery flows exist, and avoid concluding business success solely from BatchStatus COMPLETED.

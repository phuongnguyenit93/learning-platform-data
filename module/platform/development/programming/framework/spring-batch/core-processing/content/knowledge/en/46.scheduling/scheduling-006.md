# Rerunning After Failure in Spring Batch Scheduling

## 1. Why Is a Post-Failure Rerun Mechanism Needed?

A batch Job may run automatically at 02:00 daily to import orders, settle transactions, reconcile records, or build reports. During a run, the database connection can drop, an external API can time out, a message broker can become temporarily unavailable, or a bad data record can cause the Job to end in `FAILED` status.

If the system only has a `@Scheduled` cron launching the Job the next day, yesterday's failed batch can be left behind. If the system immediately creates a new `JobInstance` to “run again,” already-committed data can be processed twice. Therefore, **rerunning after failure** is a coordination problem across **`JobRepository`**, **retry/restart policies**, and **the scheduler**.

After this lesson, you will understand and be able to implement:

- Distinguishing within-Step retry, restarting a failed `JobInstance`, and running a new `JobInstance`.
- Deciding which failures can be rerun automatically versus stopped for manual intervention.
- Scheduling reruns based on `FAILED` `JobExecution`s with cooldowns, attempt limits, and history tracking.
- Using `JobOperator` or `JobLauncher` properly without accidentally creating new `JobInstance`s.
- Ensuring checkpoints, transactions, and idempotency when a Job has partially committed data.
- Preventing two schedulers or two workers from restarting the same `JobInstance` simultaneously.
- Designing tests for failure, recovery, downtime, and repeated failures.

The context is **Spring Batch Core Processing**, where scheduled execution may be driven by Spring Scheduling, Quartz, Kubernetes CronJob, Airflow, or an external orchestrator. The rules for `JobInstance` and `JobRepository` remain the same regardless of scheduler.

## 2. Three Concepts That Must Not Be Equated

| Concept | Scope | When to use | Metadata |
| --- | --- | --- | --- |
| **Retry within a Step** | An item, chunk, or Step operation within the **same JobExecution** | Transient errors like timeouts that may succeed on immediate retries | Current `JobExecution` keeps running; skip/retry counts reflect handling. |
| **Restart Job** | Creates a **new JobExecution for the same JobInstance** | Job is `FAILED`/`STOPPED` and must resume the prior batch | `JobRepository` preserves execution history and `ExecutionContext` for recovery. |
| **Run a new JobInstance** | Different Job name or identifying `JobParameters` | Processing a new business period/date/batch | Creates a new `JobInstance`; does not use the prior failed batch's checkpoints. |

For example, `dailySettlement` runs with identifying parameter `businessDate=2026-11-16`. After 30 minutes, the Job fails after committing the first portion:

~~~text
Job: dailySettlement
Identifying parameters: businessDate=2026-11-16
                 |
                 v
           JobInstance #12
             /         \
            /           \
 JobExecution #91    JobExecution #92
       FAILED          COMPLETED
     02:00-02:30      restart at 02:45
~~~

The 02:45 run must create **JobExecution #92 for JobInstance #12**. If you add identifying parameter `run.id=2` or change `businessDate`, Spring Batch treats it as a different `JobInstance` and may reprocess all data.

### `JobInstance` and `JobParameters`

In Spring Batch, `JobInstance` identity is defined by **Job name** and **identifying `JobParameters`**. Example in Spring Batch 5.x:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("requestedBy", "nightly-scheduler", false)
        .toJobParameters();
~~~

The `businessDate` parameter identifies the batch; `requestedBy` only describes the caller and does not alter `JobInstance` identity. To restart, preserve the same identity. A new `JobExecution` is created when the framework resumes the failed `JobInstance`.

### When Is `launchJob` with the Same Parameters a Restart?

In Spring Batch 5.x, `JobLauncher.run(job, parameters)` looks up the `JobInstance` by parameters. If the old instance is `FAILED` and restartable, the framework can create a new execution to continue; if the instance is already `COMPLETED`, Spring Batch rejects rerunning with the same identifying parameters.

However, at the operational layer **prefer `JobOperator.restart(failedExecutionId)`** when the explicit goal is recovering a failed batch. This states intent clearly and prevents callers from accidentally passing a new parameter set. New batch schedules should use `JobLauncher.run` or the version's start API.

## 3. What Happens When a Job Fails Mid-Run?

Suppose a Step reads five records in order `1,2,3,4,5`, with a chunk size of two items. The processor throws an unconfigured (non-skippable, non-retryable) error at item `3`:

~~~text
First execution:
   read [1,2] -> write [1,2] -> COMMIT
   read [3]   -> processor throws -> ROLLBACK current chunk
   JobExecution = FAILED
   committed target = [1,2]
   checkpoint after record 2

Restart execution:
   open reader from saved checkpoint
   read [3,4] -> write [3,4] -> COMMIT
   read [5]   -> write [5]   -> COMMIT
   JobExecution = COMPLETED
   final target = [1,2,3,4,5]
~~~

This holds true only if the Job is designed to be restartable:

- Readers persist `ExecutionContext` or query only uncompleted records.
- Read ordering is deterministic (e.g., `ORDER BY id` on a suitable source) or checkpoints use business keys.
- Writers write within proper transaction boundaries; uncommitted chunks roll back.
- Out-of-transaction side effects such as HTTP calls, emails, or message broker publishes have **idempotency**.
- `JobRepository` and `BATCH_*` metadata tables remain intact and are not deleted after failure.

**Restart does not automatically mean “exactly once.”** If a writer sent an HTTP payment request and the response was lost, the framework assumes the chunk failed and calls it again on restart. The target system must support idempotency keys or reconciliation so payment is not made twice.

## 4. Failure Policy: Auto-Rerun or Manual Intervention?

A scheduler must not blindly restart every `FAILED` Job. Classify failures and define operational policies.

| Failure category | Examples | Recommended behavior |
| --- | --- | --- |
| **Transient errors** | Network timeouts, 503, brief DB disconnect | Can auto-restart after cooldown/backoff, up to a limit. |
| **Data errors** | Bad CSV schema, missing required field, invalid record | Stop and alert owners; fix data before restarting. |
| **Configuration errors** | Missing secret, wrong URL, missing permissions | Do not keep auto-restarting; fix configuration first. |
| **Resource errors** | Disk full, out of memory, quota exhausted | Assess resources and recovery readiness before retrying. |
| **Code bugs** | `NullPointerException`, wrong business logic | Fix, deploy compatible version, and check checkpoint compatibility. |
| **Post-external-side-effect errors** | API accepted command but Step timed out | Reconcile/check idempotency before auto-retrying/restarting. |
| **Operator-initiated stop** | Planned maintenance | Do not auto-restart unless explicitly authorized. |

Policy can be expressed in configuration:

~~~yaml
batch:
  recovery:
    enabled: true
    max-executions-per-instance: 3
    initial-delay: 5m
    max-delay: 1h
    scan-interval: 1m
    eligible-jobs:
      - dailySettlement
      - importOrders
~~~

These are **application-defined illustrative properties**, not built-in Spring Batch properties. The application must implement logic to read these values, persist recovery plans, and enforce the policy.

**Max executions = 3** means one initial run plus at most two restarts. To allow three restarts, the total execution limit would be four.

## 5. Backoff, Cooldown, and Attempt Limits

If the database is down for 20 minutes, restarting every second adds load and worsens the outage. A recovery plan should include:

- **Initial delay:** wait a minimum interval after failure before the first retry.
- **Exponential backoff:** increase wait intervals across failures, e.g., 5, 10, 20, 40 minutes.
- **Jitter:** add/subtract slight randomness so multiple Jobs do not wake simultaneously and hammer a recovering system.
- **Maximum delay:** cap wait times from growing unbounded.
- **Maximum attempts:** once reached, transition to awaiting manual action and send alerts.
- **Time window/expiry:** skip automatic restarts if the batch is too stale or past a business cutoff.

Example with a 5-minute initial delay doubling on each failure:

| Failed execution | Next attempt (if eligible) |
| --- | --- |
| Attempt 1, 02:10 | Earliest 02:15 |
| Attempt 2, 02:16 | Earliest 02:26 |
| Attempt 3, 02:28 | Earliest 02:48 |
| Limit reached | Stop auto-restarting; alert/reconcile |

Illustrative formula:

~~~text
delay(n) = min(maxDelay, initialDelay * 2^(n-1)) + jitter

n = number of failures that have occurred for this JobInstance
~~~

**Scheduler backoff differs from in-Step retry policies.** A Step might retry the same item three times within one execution before marking the Job `FAILED`. The scheduler policy then decides whether to create a new execution. Without bounding both layers, total calls to an external API can exceed expectations.

## 6. Designing Scheduling and Recovery Flows

A clean architecture separates two flows:

1. **New-batch schedule:** creates `JobInstance`s for new business periods, such as Nov 17.
2. **Failed-batch recovery schedule:** queries `FAILED` `JobInstance`s, applies policy, and restarts the same instance.

~~~text
        Nightly schedule (02:00)
                   |
                   v
       launch(Job, businessDate=D)
                   |
                   v
              JobRepository
                   |
          +--------+---------+
          |                  |
      COMPLETED            FAILED
          |                  |
          v                  v
       Finished        Failure classifier
                             |
              +--------------+--------------+
              |                             |
       Not retryable                  Retryable
              |                             |
              v                             v
         Alert/manual           Durable recovery plan
                                    (dueAt, attempts)
                                           |
                                           v
                                  Recovery scheduler
                                           |
                                           v
                                 Re-read JobRepository
                                           |
                              still FAILED & eligible?
                                  /             \
                                no               yes
                                |                 |
                                v                 v
                           reconcile      JobOperator.restart
                                                  |
                                                  v
                                          new JobExecution
                                                  |
                                         monitor final state
~~~

Key takeaway: **the scheduler decides when and whether to request a restart; Spring Batch and `JobRepository` decide which `JobInstance`/Steps re-execute**. With multiple schedulers, coordinate so two schedulers never process the same recovery plan concurrently.

## 7. Scheduling New Jobs with Spring Scheduling

The example below uses **Spring Boot 3.x + Spring Batch 5.2.x**, Java 17+, with `JobLauncher`. It assumes a JDBC `JobRepository` and `@EnableScheduling` are configured.

~~~java
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailyImportSchedule {

    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private final JobLauncher jobLauncher;
    private final Job dailyImportJob;

    public DailyImportSchedule(
            JobLauncher jobLauncher,
            @Qualifier("dailyImportJob") Job dailyImportJob) {
        this.jobLauncher = jobLauncher;
        this.dailyImportJob = dailyImportJob;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
    public void runDailyBatch() throws Exception {
        LocalDate businessDate = LocalDate.now(BUSINESS_ZONE);

        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .toJobParameters();

        jobLauncher.run(dailyImportJob, params);
    }
}
~~~

In application configuration:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class BatchApplication {
    public static void main(String[] args) {
        org.springframework.boot.SpringApplication.run(
            BatchApplication.class, args);
    }
}
~~~

The schedule `0 0 2 * * *` runs at 02:00 daily in the specified timezone. With `businessDate` as an identifying parameter, two launch requests on the same day share the same `JobInstance` identity.

Important caveats:

- `@Scheduled` fires triggers only within the live Spring process. If the app is down at 02:00, the trigger can be missed; upon restart it does not automatically “catch up” missed runs. You need catch-up logic, a persistent scheduler, or durable job schedules.
- When deploying **multiple application instances**, each instance can fire the same `@Scheduled`. Use leader coordination, distributed locks, or a central scheduler if only one trigger is wanted.
- If the Job uses an async executor, `JobLauncher.run` can return while the Job is still running; do not equate “no exception thrown” with `COMPLETED`.
- When yesterday's Job is still `FAILED`, today's cron run for today's `businessDate` creates a **new batch**. A dedicated recovery mechanism is needed so yesterday's batch is not forgotten.
- If the Job already `COMPLETED` for that identity, the launcher rejects duplicate launches; never generate a random `run.id` just to bypass that error.
- If the domain settles **the previous day's** figures, calculate `businessDate` from business rules (e.g., yesterday) rather than defaulting to the current date. Cron represents trigger time, not necessarily data period.

## 8. Restarting a FAILED Job via `JobOperator`

In Spring Batch 5.2.x, `JobOperator.restart(long executionId)` explicitly creates a new execution from a failed `JobExecution`.

~~~java
import java.util.Comparator;
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class FailureRestartService {

    private static final int MAX_EXECUTIONS = 3;

    private final JobExplorer jobExplorer;
    private final JobOperator jobOperator;

    public FailureRestartService(
            JobExplorer jobExplorer,
            JobOperator jobOperator) {
        this.jobExplorer = jobExplorer;
        this.jobOperator = jobOperator;
    }

    public long restartLatestFailedExecution(long failedExecutionId)
            throws Exception {

        JobExecution failed =
                jobExplorer.getJobExecution(failedExecutionId);

        if (failed == null) {
            throw new IllegalArgumentException(
                "Unknown execution: " + failedExecutionId);
        }

        JobInstance instance = failed.getJobInstance();
        List<JobExecution> history =
                jobExplorer.getJobExecutions(instance);

        JobExecution latest = history.stream()
                .max(Comparator.comparingLong(JobExecution::getId))
                .orElseThrow();

        if (!latest.getId().equals(failedExecutionId)) {
            throw new IllegalStateException(
                "A newer execution already exists for this instance");
        }

        if (latest.getStatus() != BatchStatus.FAILED) {
            throw new IllegalStateException(
                "Only FAILED execution can use auto recovery");
        }

        if (history.size() >= MAX_EXECUTIONS) {
            throw new IllegalStateException(
                "Execution budget exhausted");
        }

        // Must be called only after the failure is confirmed retryable
        // and nextAttemptAt has arrived.
        return jobOperator.restart(failedExecutionId);
    }
}
~~~

**Purpose of this service:** illustrates pre-restart guardrails using an explicit ID and total execution cap. It does not classify failures, check deadlines, or persist schedules; enforce those in the recovery policy layer before calling. Reading status then calling restart is not an atomic transaction: if another node restarts concurrently, the framework may throw because an execution is already running or the instance changed state. That is a **valid conflict** to catch and reconcile.

### When a Job Fails Multiple Times

Suppose:

~~~text
JobInstance #70:
  #200 FAILED     02:02
  #201 FAILED     02:12
  #202 FAILED     02:40
~~~

With max executions = 3, the policy forbids a fourth automatic run. After configuration fixes or operator approval, a new policy decision can apply. Never delete `JobRepository` history to “reset” the counter: doing so destroys identity, checkpoints, and audit trails.

## 9. Scheduling Automatic Restart Requests

In simple setups, a `@Scheduled` job might scan metadata for `JobInstance`s whose latest execution is `FAILED`. However, blindly auto-scanning **all failures** easily reruns non-retryable Jobs. Production systems should manage a **durable recovery plan table**, enqueuing only failures classified as retryable.

### 9.1. Recovery Plan Table

Conceptual schema example:

~~~sql
CREATE TABLE batch_recovery_plan (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    job_instance_id BIGINT NOT NULL,
    failed_execution_id BIGINT NOT NULL,
    state VARCHAR(24) NOT NULL,
    attempt_count INTEGER NOT NULL,
    next_attempt_at TIMESTAMP NOT NULL,
    lease_until TIMESTAMP,
    last_error VARCHAR(1000),
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_recovery_instance UNIQUE (job_instance_id)
);
~~~

Custom-defined states can include:

| Plan state | Meaning |
| --- | --- |
| `PENDING` | Failure classified and retry scheduled. |
| `CLAIMED` | A worker holds a lease and is executing the restart request. |
| `WAITING` | Restarted; awaiting the new `JobExecution` outcome. |
| `DONE` | `JobInstance` completed or plan resolved. |
| `PARKED` | No longer eligible for auto-retry; awaiting operations. |

**This is an application recovery table**, not part of Spring Batch's default `BATCH_*` schema. Authoritative `JobExecution` state still lives in `JobRepository`. The plan table stores **when to retry, who holds the lease, retry limits, and policy decisions**.

If the database timezone differs from the JVM, store `next_attempt_at` in UTC or a timezone-aware type, and standardize comparisons when polling.

### 9.2. Scheduler Algorithm

~~~text
every 60 seconds:
    claims = acquireDuePlans(now, limit = 20)

    for each plan:
        latest = JobExplorer.getJobExecutions(plan.jobInstance)
                            .maxBy(executionId)

        if latest.status == COMPLETED:
            markPlanDone()
            continue

        if latest.status == STARTED / STARTING / STOPPING:
            markPlanWaitingOrReconcile()
            continue

        if latest.status != FAILED:
            parkOrReclassify()
            continue

        if retryBudgetExhausted or deadlineExpired:
            parkPlanAndAlert()
            continue

        if failureNotApprovedAsRetryable:
            parkPlanAndAlert()
            continue

        if not dueYet:
            releaseClaimUntil(nextAttemptAt)
            continue

        newId = JobOperator.restart(latest.id)

        recordNewExecutionId(newId)
        markPlanWaiting()
~~~

Operations on the **plan table** must be transactional, especially lease claiming and state transitions. With multiple concurrent workers, only one worker may claim a plan at a time. Use conditional updates on state/version, or `SELECT ... FOR UPDATE SKIP LOCKED` if supported by your database. Exact SQL syntax, isolation, and locking depend on the database engine.

**Do not hold a database transaction/row lock open while a Job runs for minutes or hours.** Claim the plan in a short transaction, execute the Job, and update the plan state from the outcome. A bounded lease lets another worker reclaim a plan if the owner crashes, provided reclamation re-reads `JobRepository` before restarting to avoid duplicate runs.

### 9.3. Scheduled Poller

In Spring Scheduling, the poller can be structured as follows:

~~~java
import java.util.List;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class RecoveryPoller {

    private final RecoveryPlanStore planStore;
    private final FailureRestartService restartService;

    public RecoveryPoller(
            RecoveryPlanStore planStore,
            FailureRestartService restartService) {
        this.planStore = planStore;
        this.restartService = restartService;
    }

    @Scheduled(fixedDelay = 60_000L)
    public void processDuePlans() {

        // claimDuePlans must use a database lock or compare-and-set
        // to prevent multiple nodes from claiming simultaneously.
        List<RecoveryPlan> plans = planStore.claimDuePlans(20);

        for (RecoveryPlan plan : plans) {
            try {
                long newExecutionId =
                        restartService.restartLatestFailedExecution(
                            plan.failedExecutionId());

                planStore.markWaiting(
                    plan.id(), newExecutionId);

            } catch (Exception error) {
                // Classify error: retryable, race/conflict, or fatal.
                // Re-read JobRepository before deciding to requeue.
                planStore.recordFailure(plan.id(), error);
            }
        }
    }
}
~~~

`RecoveryPlanStore` and `RecoveryPlan` are **application abstractions to implement** over `batch_recovery_plan`; Spring Batch does not provide these two types. The snippet shows the scheduler's responsibilities, not a copy-paste-buildable example without defining those types.

In a complete implementation:

- `claimDuePlans` fetches only due plans and grants leases atomically.
- `markWaiting` stores the new execution ID; it does not mark success merely because restart was accepted.
- `recordFailure` classifies errors; if another node already restarted the Job, update the plan to the new execution instead of wrongly incrementing attempts.
- A listener or reconciler reads `JobRepository` to check whether the latest `JobExecution` became `COMPLETED` or `FAILED`, updating the plan to `DONE`, `PENDING`, or `PARKED`.
- If the process dies **after restart succeeds but before `markWaiting`**, the next poll must inspect `JobExecution` history and detect the new execution instead of restarting from the old `failedExecutionId`.

### 9.4. Should You Use `JobExecutionListener`?

`JobExecutionListener.afterJob` can detect a `FAILED` Job and request creating a recovery plan:

~~~java
@Override
public void afterJob(JobExecution execution) {
    if (execution.getStatus() == BatchStatus.FAILED) {
        // Only record a recovery event / upsert a plan.
        // Do not restart directly in an unbounded loop inside this callback.
        recoveryService.registerFailure(execution);
    }
}
~~~

The benefit is fast reaction after failure. However, if the process crashes abruptly, `afterJob` may **not run**. Furthermore, writing the event/plan and updating metadata may span separate transactions.

Thus, a reliable design usually combines:

1. A listener to emit an early signal whenever possible.
2. A periodic scheduler or reconciler scanning `JobRepository` to catch failed executions the listener missed.
3. A unique constraint per `JobInstance` and idempotent upsert logic so duplicate plans are never created.

Never call `JobOperator.restart` immediately inside a listener on every Job failure: deterministic errors will create an infinite loop, bypass backoff, and mask root causes.

## 10. Restart, Stop, and Recovery When Processes Die

Not every unsuccessful run leaves `FAILED`. When an application is killed abruptly or loses power, `JobRepository` may still show `STARTED` even though the process is dead.

| Latest `JobExecution` status | Auto-restart immediately? | Explanation |
| --- | --- | --- |
| `FAILED` | Possibly, if policy allows | Must verify retryability, deadline, backoff, and attempt limit. |
| `STOPPED` | Usually requires explicit policy/approval | May reflect an intentional maintenance stop. |
| `COMPLETED` | No | Same `JobInstance` already finished. |
| `STARTED`, `STARTING` | No | Job may still be running, or metadata is stale after a crash. |
| `STOPPING` | No | Wait for complete stop before considering restart. |
| `ABANDONED` | No | Marked abandoned; do not restart normally. |
| `UNKNOWN` | No | Must inspect metadata/consistency. |

For abnormal process termination:

~~~text
Monitor detects execution still STARTED
               |
               v
Verify old process/pod is genuinely no longer running
               |
               v
Inspect committed data, side effects, checkpoints
               |
               v
Fix status via the version's recovery mechanism
               |
               v
Apply policy to restart/reconcile/abandon
~~~

**Spring Batch 6.x** provides `JobOperator.recover(JobExecution)` to handle executions stuck `STARTED` after an abrupt shutdown. Use it only after confirming no old worker is still active. In **Spring Batch 5.2.x**, stale-status handling relies on version-appropriate APIs and runbooks; never arbitrarily edit the `STATUS` column in `BATCH_JOB_EXECUTION`. Do not confuse recover with restart: recover fixes stale execution metadata; restart launches a new execution for the `JobInstance`.

## 11. Scheduling in Multi-Instance Systems

A Spring Boot application may run three replicas:

~~~text
Pod A: @Scheduled 02:00 --> start dailyImport(D)
Pod B: @Scheduled 02:00 --> start dailyImport(D)
Pod C: @Scheduled 02:00 --> start dailyImport(D)
                         |
                         v
                   JobRepository
                   shared JDBC DB
~~~

Sharing a metadata store helps the framework recognize the same `JobInstance` and prevent certain duplicate launches, **but does not replace scheduler coordination design**. Two nodes can still read the same failure simultaneously and both decide to restart before either actually starts.

Common safeguards:

- **A single scheduler owner/leader** for launches, or a central external scheduler.
- **Distributed locks/leases** for recovery plans; claim atomically before calling `JobOperator`.
- **Unique constraints** on business keys and `JobInstance`; never use new timestamps to bypass conflicts.
- **Idempotent writers** and reconciliation when out-of-transaction external systems may receive duplicate effects.
- **Tracking new execution IDs** to know which batch is running rather than relying on an in-memory `processing` boolean.
- **Re-reading metadata** upon conflict exceptions, because another node may already have restarted successfully.

When using Kubernetes CronJob, understand that `concurrencyPolicy` governs only Jobs belonging to that CronJob, not exclusivity against another scheduler writing to `JobRepository`. To catch up schedules missed during downtime, configure the appropriate mechanism in Quartz, Airflow, or your chosen orchestrator.

## 12. Designing Business Logic Safe for Restart

### 12.1. Idempotency

In payment systems, writes can rely on a unique key:

~~~sql
CREATE TABLE settlement_result (
    business_date DATE NOT NULL,
    order_id BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (business_date, order_id)
);
~~~

If a Job restarts and attempts to rewrite the same `(business_date, order_id)` pair, the database detects the duplicate. Depending on domain rules, apply idempotent upserts or skip already-finalized records instead of failing the Job permanently on a key violation. Explicitly define behavior when keys match but amounts differ: never silently overwrite settled figures without an adjustment rule.

For HTTP, generate **business-stable** idempotency keys such as `settlement:2026-11-16:order-101`; never use `JobExecution` ID because execution IDs change on restart.

### 12.2. Checkpoints and Mutable Data Sources

Offset-based readers work reliably when the source is immutable between executions. However, if rows are inserted/deleted before the offset, restarts can skip or re-read items. For volatile sources, consider input snapshots, strictly increasing key queries, staging tables, versioning, or per-item processing flags.

### 12.3. Transactions and Retry Limits

When a Step uses `chunk(100)`, an error on item 250 normally rolls back the current chunk within the configured transaction, while the first two chunks remain committed. The scheduler cannot roll back those two committed chunks. Therefore, tests and runbooks must clearly define the **unit of recovery**: chunk, item, partition, or whole Job.

If a Step has `retryLimit(3)` and the scheduler permits up to three `JobExecution`s, an item can be attempted multiple times across executions. Do not infer total external system calls solely from `max-executions-per-instance`.

## 13. Metrics, Auditing, and Alerting

An operable recovery system should answer:

- Which `JobInstance` is failing, and what are its identifying `JobParameters`?
- Which execution failed most recently; which Step failed; what are `ExitStatus` and the exception?
- Under what rule was the failure classified as retryable or fatal?
- How many automatic attempts have run, and when is the next attempt scheduled?
- Is any worker holding a lease or is a new `JobExecution` running?
- Has the batch completed, and has output data been reconciled?

Suggested metrics:

~~~text
batch_job_failures_total{job="dailySettlement"}
batch_job_restarts_total{job="dailySettlement",result="accepted"}
batch_job_recovery_exhausted_total{job="dailySettlement"}
batch_job_recovery_pending{job="dailySettlement"}
batch_job_recovery_oldest_pending_seconds{job="dailySettlement"}
batch_job_last_success_timestamp_seconds{job="dailySettlement"}
~~~

These are **application-defined illustrative metric names**; Spring Batch does not emit all of these by default. Avoid putting high-cardinality values like `executionId`, `orderId`, or per-item `businessDate` into metric labels; keep those in logs, traces, and audit tables.

When attempts are exhausted or business deadlines pass, send alerts containing Job name, business key, latest execution ID, failure category, and links to dashboards/runbooks. Never log credentials, tokens, or sensitive data from `JobParameters`.

## 14. Testing Post-Failure Rerun Scenarios

Schedule recovery tests must go beyond calling `restart` once and asserting `COMPLETED`. A thorough suite should cover:

| Scenario | What to verify |
| --- | --- |
| Transient failure, then recovery | Scheduler waits the proper delay and restarts the same `JobInstance`; next run `COMPLETED`. |
| Non-retryable data failure | No new `JobExecution` created; plan moves to `PARKED` and alerts fire. |
| Consecutive failures | Delay grows via backoff; total execution budget is never exceeded. |
| Restart after committing a chunk | Final data is complete with no duplicates; read/checkpoints are accurate. |
| Already-`COMPLETED` `JobInstance` | Scheduler never recreates the old batch or writes new side effects. |
| Later run changes identifying parameter | Creates a new `JobInstance` as designed, not treated as a restart. |
| Scheduler downtime across cron time | Catch-up or reconciliation detects missing batches per policy. |
| Two schedulers pick up the same plan | Only one worker claims; races produce no duplicate side effects. |
| Crash between sending restart and acking plan | Reconciliation detects the new execution and does not restart from the old `failedExecutionId`. |
| Execution stays `STARTED` after power loss | Never auto-restarted; verifies worker dead and recovers metadata safely. |
| Intentional stop | Never auto-restarts `STOPPED` if policy requires approval. |
| Writer sends HTTP then loses response | Same idempotency key across attempts; business effect occurs only once. |

### 14.1. Testing with a Controllable Clock

Avoid relying on `Thread.sleep(60000)` to test backoff. Extract `nextAttemptAt` calculation using an injectable `Clock` and test with `Clock.fixed` or `Clock.offset`.

Pure function example for computing delay:

~~~java
import java.time.Duration;

public final class RecoveryBackoff {

    private RecoveryBackoff() {}

    public static Duration delayAfterFailure(int failureCount) {
        if (failureCount < 1) {
            throw new IllegalArgumentException("failureCount >= 1");
        }

        long minutes = 5L;
        for (int i = 1; i < failureCount; i++) {
            minutes = Math.min(minutes * 2, 60L);
        }

        return Duration.ofMinutes(minutes);
    }
}
~~~

Expected: first failure waits 5 minutes, second waits 10 minutes, third waits 20 minutes, capped at 60 minutes. Jitter can be added in the scheduler component, while tests inject a controllable random source.

### 14.2. Testing Restart Against a Real `JobRepository`

An integration test should use `spring-batch-test` and a JDBC `JobRepository`:

~~~java
// Pseudocode for Spring Batch 5.x:
// First launchJob(params) creates a FAILED JobExecution.
// Use the same identity via JobOperator.restart(failedExecutionId).
// JobRepository should then have 1 JobInstance and 2 JobExecutions.
// COMPLETED steps do not rerun by default.
// Verify business data: no gaps, no duplicates.

JobExecution first = jobLauncherTestUtils.launchJob(params);
assertEquals(BatchStatus.FAILED, first.getStatus());

long restartedExecutionId = jobOperator.restart(first.getId());

JobExecution second =
        jobExplorer.getJobExecution(restartedExecutionId);

// If running async, wait for terminal state via test synchronization.
assertEquals(first.getJobInstance().getInstanceId(),
             second.getJobInstance().getInstanceId());
~~~

When a Job runs asynchronously, do not assert `COMPLETED` immediately after calling restart. Use bounded waits/conditions and re-read the repository. Never wipe `BATCH_*` tables between the failure run and restart run, as that destroys checkpoints and identity.

For scheduling tests, separate **deciding when it is time to run** from **actually sending the restart command**. Unit tests cover backoff math, failure classification, and eligibility; integration tests verify `JobOperator`/`JobRepository` and persisted data.

## 15. Differences Between Spring Batch 5.2.x and 6.x

Core rules for `JobInstance`, `JobExecution`, and checkpoints remain unchanged. However, execution APIs change across major versions:

| Operation | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Start Job from code | `JobLauncher.run(Job, JobParameters)` | `JobOperator.start(Job, JobParameters)` is the primary operational API. |
| Restart old `JobExecution` | `JobOperator.restart(long executionId)` returns execution ID | `JobOperator.restart(JobExecution)` returns new `JobExecution`. |
| Look up execution | `JobExplorer.getJobExecution(id)` | Uses `JobRepository.getJobExecution(id)` in the new API model. |
| Stop | `JobOperator.stop(long executionId)` | `JobOperator.stop(JobExecution)`. |
| Recover stale `STARTED` metadata | Needs runbook matching 5.2 | `JobOperator.recover(JobExecution)` after verifying worker death. |
| Test launcher | `JobLauncherTestUtils.launchJob(params)` | `JobOperatorTestUtils.startJob(params)`. |

In Spring Batch 6.x, `@EnableBatchProcessing` by default may configure resourceless infrastructure. Restart tests and real recovery schedules need a **JDBC `JobRepository`**, `BATCH_*` schema, and a database lasting across all executions of the same `JobInstance`. Configure the JDBC repository according to your exact Batch/Boot version documentation.

Example start/restart in 6.x:

~~~java
// Assumes JobOperator, JobRepository, and Job are injected.
JobExecution first = jobOperator.start(job, parameters);

// When an execution is known FAILED and eligible for recovery:
JobExecution previous =
        jobRepository.getJobExecution(failedExecutionId);
JobExecution resumed = jobOperator.restart(previous);
~~~

These are two independent usage contexts; do not call restart while `first` is still running. In schedulers, always check persisted status and policy before restarting.

## 16. Common Pitfalls

**Using tomorrow's schedule to “self-heal” yesterday's batch.** Tomorrow's cron usually passes a different `businessDate`, creating a different `JobInstance`; yesterday's batch stays `FAILED`. Separate discovery/recovery is needed.

**Adding an identifying timestamp to `JobParameters` on every failure.** This bypasses restart semantics and can duplicate data processing. Reuse the same identity and restart the appropriate `JobExecution`.

**Restarting immediately inside `afterJob` without attempt limits.** Deterministic config or data errors cause endless failure loops. Move to a durable plan with backoff, budgets, and alerts.

**Treating `STARTED` after a crash as `FAILED`.** The process might still be running; restarting without verification can double-process the same batch. Investigate and recover metadata per procedure.

**Assuming stop rolls back all data.** Only uncommitted chunks roll back transactionally; committed portions remain and must be respected on restart.

**Relying solely on `@Scheduled` when catch-up is required.** Spring Scheduling does not persist triggers missed while the app was down. Reconcile business periods and use a persistent scheduler or queue if required.

**Treating `JobRepository` as a complete retry queue.** The repository stores execution metadata; it does not provide policies, backoff, deadlines, lease claims, or failure classification. Those belong in the recovery service/scheduler.

**Deleting metadata to allow reruns.** Destroys history, checkpoints, and duplicate guards; risks data loss or duplication. Clean up `BATCH_*` only in isolated test databases between independent tests.

## 17. Practice Exercises

### Exercise 1 — Scheduled Runs with `businessDate`

Create `dailyImportJob` and a `@Scheduled` trigger at 02:00 using `businessDate` as an identifying parameter. Simulate failure on day D while day D+1's cron still launches a new batch; verify in `JobRepository` that **two distinct `JobInstance`s** exist, one `FAILED` and one running or `COMPLETED`.

### Exercise 2 — Automatic Restart with Backoff

Create `batch_recovery_plan` with `job_instance_id`, `failed_execution_id`, `next_attempt_at`, `state`, and attempt count. Build a scheduler scanning due plans and restarting the latest execution via `JobOperator`. Simulate a transient error and verify one instance has two `JobExecution`s and finishes `COMPLETED`.

### Exercise 3 — Blocking Fixed-Error Loops

Make the processor always throw a bad-data exception. Set total execution budget to 3. Verify that after three failed executions, the plan transitions to `PARKED` and no fourth execution is spawned even as the scheduler continues polling.

### Exercise 4 — Two Competing Schedulers

Run two workers reading the same due plan. Implement transactional claiming with unique constraints/leases and prove only one worker successfully triggers the restart. In a race, the other worker must re-read status and reconcile.

### Exercise 5 — Crash Between Restart and Ack

Simulate `JobOperator` creating a new execution while the recovery worker crashes before updating the plan. When another worker reclaims the lease, it must inspect `JobRepository`, recognize the new execution, and **not** restart again from the old `failedExecutionId`.

### Exercise 6 — Out-of-Transaction Writer

Call a mocked HTTP endpoint with a stable idempotency key per `businessDate` and `orderId`. Have the HTTP server succeed while the client times out. Restart the Job and verify the mock server applies the business effect only once.

### Exercise 7 — Post-Downtime Reconciliation

Shut down the scheduler app across two days. On startup, implement a reconciler comparing mandatory business periods against existing `JobInstance`s, creating missing batches and scheduling recovery for `FAILED` ones without creating duplicate `JobInstance`s.

## 18. References

- [Spring Batch — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html)
- [Spring Batch — Advanced Metadata Usage / JobOperator](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Batch 5.2 — JobOperator API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/launch/JobOperator.html)


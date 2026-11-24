# Auditing Spring Batch Job Launches from a Scheduler

## 1. The Problem: Knowing How Each Scheduler Requested a Job Run

In scheduled batch systems, operational questions are rarely limited to “did the job succeed?” They also ask:

- At 01:00 today, did the scheduler **actually issue a launch request**?
- Did the request come from cron, an operator, a backfill action, or an external scheduler?
- Which data period did the scheduler ask to process, and what parameters did it send?
- Was the request accepted by Spring Batch, rejected as already completed, rejected as already running, or failed before creating an execution?
- If accepted, which `JobExecution` corresponds to the request? Did that execution ultimately finish `COMPLETED` or `FAILED`?
- When two triggers arrived for the same period, did the system record both requests and how did it handle the duplicate?

That is the role of **launch auditing**: recording a trace every time a component actively asks Spring Batch to start a job, including cases where **no `JobExecution` is created**.

This lesson belongs to the *Scheduling* group in *Spring Batch Core Processing*. After completing it, you will be able to design an audit model, implement a coordinator wrapping `JobLauncher`, correlate audits with Spring Batch metadata, distinguish launch outcomes from processing outcomes, and test duplicates, restarts, failures, and connection drops.

Examples use Java 17+, Spring Boot 3.x, Spring Batch 5.x, JDBC, and PostgreSQL. The ideas apply equally with Quartz, Kubernetes CronJob, or other orchestrators.

## 2. Three Event Layers to Distinguish

A **scheduler trigger** is the time event or command action; a **launch attempt** is the application's invocation of the launch mechanism; a **JobExecution** is the execution attempt recorded by Spring Batch.

```text
                  Cron schedule 01:00 / manual run request
                                 |
                                 v
                           Trigger event
                                 |
                                 v
                    Launch attempt (audit_id)
                    status = REQUESTED
                                 |
                                 v
                       JobLauncher.run(...)
                             /       \
                            /         \
                        Rejected    Accepted
                           |           |
                           v           v
                   Audit rejection  JobExecution ID
                                       |
                                       v
                                   Job / Steps
                                       |
                                       v
                              COMPLETED / FAILED
                                       |
                                       v
                          Audit execution outcome
```

For example, the scheduler resends the exact parameters of an already-completed `JobInstance`. Spring Batch typically throws `JobInstanceAlreadyCompleteException`. **There is a launch attempt, but no new `JobExecution`**. Inspecting only `BATCH_JOB_EXECUTION` tables would miss this rejected request entirely.

Conversely, a valid launch can create a `JobExecution` that later fails due to bad data. Here **the launch was accepted**, even though **the job failed**. If an audit system stores only a single `success=true/false` flag, the two events get conflated.

| Layer | Observable entity | Example |
| --- | --- | --- |
| Trigger | A due schedule tick or operational request | 01:00 cron, backfill command for day D |
| Launch attempt | One application request to run a job | Request recorded, accepted, or rejected |
| JobInstance | One logical processing period | `dailySalesJob` + `businessDate=D` |
| JobExecution | One execution attempt of an instance | First run `FAILED`, restart `COMPLETED` |
| StepExecution | Per-step execution status and counts | Read 5,000 records, wrote 4,990 records |

One `JobInstance` can have multiple `JobExecution`s due to restarts. One `JobInstance` can also be associated with multiple launch attempts, including rejected ones. Therefore, never use `jobInstanceId` or `jobExecutionId` as the unique primary key of a launch-request audit record.

## 3. Leveraging Spring Batch Metadata While Adding Scheduler Context

Spring Batch persists metadata in standard tables such as:

- `BATCH_JOB_INSTANCE`: job name and instance identity.
- `BATCH_JOB_EXECUTION`: timestamps, status, and result of each execution.
- `BATCH_JOB_EXECUTION_PARAMS`: parameters bound to an execution, including the identifying flag.
- `BATCH_STEP_EXECUTION`: execution state of each step.
- Execution context tables: state needed for restarts and recovery.

Metadata is invaluable for answering **what the job ran**. However, it cannot answer every question about **what the scheduler tried to launch**.

For instance, a job is already `COMPLETED` and the scheduler sends an identical request the next day: Batch rejects it; the repository does not create another execution. From execution metadata alone, you cannot see that an extra rejected trigger occurred.

An audit table adds fields:

| Field | Meaning |
| --- | --- |
| `audit_id` | Unique ID for **each launch request** |
| `trigger_source` | `SCHEDULED`, `MANUAL`, `BACKFILL`, `EXTERNAL`... |
| `trigger_key` | Schedule period ID or event key; may repeat across redeliveries |
| `job_name` | Spring Batch Job name |
| `business_date` | Business period requested, as an example identifying parameter |
| `requested_at` | Timestamp when the app received/issued the launch request |
| `launch_outcome` | `REQUESTED`, `ACCEPTED`, `ALREADY_RUNNING`, `ALREADY_COMPLETED`... |
| `job_execution_id` | `JobExecution` ID when created; may be `NULL` |
| `launch_error_code` | Error classification code when launch could not be confirmed |
| `batch_status` / `exit_code` | Final execution outcome, once known |
| `updated_at` | Timestamp when the audit record was last updated |

Additional columns can be included as needed: `scheduler_name`, `tenant_id`, `environment`, `requested_by`, `correlation_id`, `scheduled_at`, `received_at`, `hostname`, and `trace_id`.

**Do not equate `scheduled_at` with `requested_at`.** The scheduler may fall due at 01:00 while the application receives the event late at 01:04. With a simple `@Scheduled`, the invoked method does not receive an authoritative “planned fire time”; do not fabricate `scheduled_at` from the current clock. If Quartz or an external scheduler supplies the planned time, record it separately.

## 4. Designing Audit States

Separate **request submission outcome** from **job execution status**.

### 4.1. Launch Outcome

| Outcome | Meaning |
| --- | --- |
| `REQUESTED` | Request persisted before calling `JobLauncher` |
| `ACCEPTED` | `JobLauncher` returned a valid `JobExecution` |
| `ALREADY_COMPLETED` | Duplicate request for an already-completed instance |
| `ALREADY_RUNNING` | An execution of the same instance is currently active |
| `RESTART_REJECTED` | Instance cannot be restarted per configuration/state |
| `INVALID_PARAMETERS` | `JobParameters` invalid for the job |
| `LAUNCH_ERROR` | Error calling launcher; must verify whether an execution was created |

`LAUNCH_ERROR` intentionally means **execution creation is unconfirmed**. Under certain infrastructure errors or timeouts, the caller cannot determine whether the repository already persisted a `JobExecution`. Avoid recording “did not run” without proof.

### 4.2. Batch Status

`batch_status` is meaningful only when an execution exists, e.g., `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, or `STOPPED`. `ExitStatus` may carry custom exit codes, so keep both fields when investigating Batch flows.

Example:

| Audit ID | Launch outcome | JobExecution ID | Batch status |
| --- | --- | --- | --- |
| A-001 | `ACCEPTED` | 5001 | `COMPLETED` |
| A-002 | `ALREADY_COMPLETED` | `NULL` | `NULL` |
| A-003 | `ACCEPTED` | 5002 | `FAILED` |
| A-004 | `ACCEPTED` | 5003 | `COMPLETED` |
| A-005 | `LAUNCH_ERROR` | `NULL` | `NULL` |

If A-003 and A-004 share the same job name and identifying parameters, they can be two executions of the **same `JobInstance`**. A-002 was a rejected launch, so it has no new execution to link.

## 5. Relationship Between `trigger_key`, `audit_id`, and Identifying Parameters

These three keys serve three distinct purposes:

1. **`audit_id`:** a UUID generated for each launch attempt by the application. Two deliveries of the same trigger still get two distinct audit IDs.
2. **`trigger_key`:** identifies the schedule event or expected period. A redelivered event may carry the same trigger key for reconciliation.
3. **`businessDate` (identifying parameter):** identifies the Spring Batch `JobInstance`, e.g., the date the job actually processes.

Example of a scheduler sending two launch requests for the same date:

```text
trigger_key = daily-sales:2026-11-15
businessDate = 2026-11-15

Attempt #1:
  audit_id = 4bc...
  launch_outcome = ACCEPTED
  jobExecutionId = 5001

Attempt #2:
  audit_id = 0d7...
  launch_outcome = ALREADY_COMPLETED
  jobExecutionId = NULL
```

Do not place `UNIQUE(trigger_key)` on the **audit attempt** table if the goal is recording every request attempt. You can maintain a separate **accepted schedule events** table with a unique constraint to deduplicate incoming triggers, which is a distinct responsibility.

To correlate an execution with its audit, add `auditId` as a **non-identifying parameter**:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", businessDate.toString(), true)
    .addString("auditId", auditId, false)
    .toJobParameters();
```

If `auditId` were marked identifying, every scheduler redelivery would create a new `JobInstance`, defeating duplicate-run and restart protections for the same day.

## 6. Reliable Audit Architecture

A minimal workflow:

```text
Scheduler
   |
   v
LaunchCoordinator
   |
   +--> 1. Write REQUESTED to audit DB
   |          |
   |          v
   |       COMMIT
   |
   +--> 2. JobLauncher.run(job, params with auditId)
   |          |
   |          +--> Rejected --> update launch outcome
   |          |
   |          +--> Returns JobExecution --> store execution ID
   |                                      |
   |                                      v
   |                            JobExecutionListener
   |                                      |
   |                                      v
   |                            Store final BatchStatus
   |
   v
Operational queries & alerts
```

**Persisting `REQUESTED` before launching** is critical. If audits are written only after `JobLauncher.run(...)` succeeds, every rejected attempt or pre-return failure goes unrecorded.

In transactional applications, audit writes should use **short, independent transactions** separate from chunk processing transactions. If an audit write shares a large transaction that rolls back on job failure, the very record needed to investigate the failure disappears.

Note that metadata persistence and audit storage do not form a single atomic transaction in this example. After the repository creates an execution and before the audit updates, the process could crash. Therefore, include a **reconciliation** step using the `auditId` stored in `JobParameters`.

## 7. Audit Table Schema (PostgreSQL)

Example storing one row per launch attempt:

```sql
CREATE TABLE batch_launch_audit (
    audit_id          VARCHAR(36) PRIMARY KEY,
    trigger_key       VARCHAR(160),
    trigger_source    VARCHAR(32) NOT NULL,
    job_name          VARCHAR(100) NOT NULL,
    business_date     DATE NOT NULL,
    requested_at      TIMESTAMPTZ NOT NULL,

    launch_outcome    VARCHAR(32) NOT NULL,
    job_execution_id  BIGINT,
    launch_error_code VARCHAR(80),

    batch_status      VARCHAR(20),
    exit_code         VARCHAR(128),
    updated_at        TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_batch_launch_audit_job_date
    ON batch_launch_audit (job_name, business_date, requested_at);

CREATE INDEX idx_batch_launch_audit_trigger
    ON batch_launch_audit (trigger_key);

CREATE INDEX idx_batch_launch_audit_execution
    ON batch_launch_audit (job_execution_id);
```

In this schema, `job_execution_id` can be `NULL` when launch is rejected or unconfirmed. A foreign key to Batch metadata tables is not mandatory: audits may have different retention windows or backup strategies than operational metadata.

Since this sample audit stores one example business key `business_date`, systems with diverse jobs can use a more general structure: `identifying_params_json`, `tenant_id`, `dataset_key`, and schema versioning. When storing parameter JSON, allowlist fields strictly; strip passwords, access tokens, and unnecessary personal data.

## 8. Implementing `AuditStore` with `JdbcTemplate`

Example dedicated repository performing three operations: recording the request, recording launch outcome, and recording final status. Public methods are invoked **from another bean** so `@Transactional(REQUIRES_NEW)` takes effect via Spring proxy.

```java
import java.sql.Date;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;

import org.springframework.batch.core.BatchStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class LaunchAuditStore {

    private final JdbcTemplate jdbc;
    private final Clock clock;

    public LaunchAuditStore(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordRequested(
            String auditId,
            String triggerKey,
            String source,
            String jobName,
            LocalDate businessDate,
            Instant requestedAt) {

        jdbc.update(
            "INSERT INTO batch_launch_audit (" +
            "audit_id, trigger_key, trigger_source, job_name, " +
            "business_date, requested_at, launch_outcome, updated_at" +
            ") VALUES (?, ?, ?, ?, ?, ?, 'REQUESTED', ?)",
            auditId,
            triggerKey,
            source,
            jobName,
            Date.valueOf(businessDate),
            Timestamp.from(requestedAt),
            Timestamp.from(requestedAt)
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordLaunchOutcome(
            String auditId,
            String outcome,
            Long executionId,
            String errorCode) {

        jdbc.update(
            "UPDATE batch_launch_audit SET " +
            "launch_outcome = ?, job_execution_id = ?, " +
            "launch_error_code = ?, updated_at = ? " +
            "WHERE audit_id = ?",
            outcome,
            executionId,
            errorCode,
            Timestamp.from(clock.instant()),
            auditId
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFinished(
            String auditId,
            BatchStatus batchStatus,
            String exitCode) {

        jdbc.update(
            "UPDATE batch_launch_audit SET " +
            "batch_status = ?, exit_code = ?, updated_at = ? " +
            "WHERE audit_id = ?",
            batchStatus.name(),
            exitCode,
            Timestamp.from(clock.instant()),
            auditId
        );
    }
}
```

This assumes a `JdbcTemplate` and transaction manager matching the audit datasource. With multiple datasources/transaction managers, explicitly specify the transaction manager on `@Transactional`.

Create the audit table via migrations before the scheduler runs. Under a **mandatory audit** design, if `recordRequested` fails, the app must not proceed to launch the job because launch intent can no longer be guaranteed recorded. Other systems may choose best-effort policy depending on requirements, while documenting its semantics and risks.

## 9. Coordinator Layer for Launching and Recording Outcomes

Create a centralized service shared by cron, backfills, and manual launches. Each call generates an `auditId`, persists the request first, adds non-identifying `auditId` to `JobParameters`, and invokes the launcher.

```java
import java.time.Clock;
import java.time.LocalDate;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class BatchLaunchCoordinator {

    private static final Logger log =
        LoggerFactory.getLogger(BatchLaunchCoordinator.class);

    private final JobLauncher launcher;
    private final Job dailySalesJob;
    private final LaunchAuditStore auditStore;
    private final Clock clock;

    public BatchLaunchCoordinator(
            JobLauncher launcher,
            @Qualifier("dailySalesJob") Job dailySalesJob,
            LaunchAuditStore auditStore,
            Clock clock) {

        this.launcher = launcher;
        this.dailySalesJob = dailySalesJob;
        this.auditStore = auditStore;
        this.clock = clock;
    }

    public String launch(
            LocalDate businessDate,
            String source,
            String triggerKey) {

        String auditId = UUID.randomUUID().toString();

        // 1. Persist before calling launcher.
        auditStore.recordRequested(
            auditId,
            triggerKey,
            source,
            dailySalesJob.getName(),
            businessDate,
            clock.instant()
        );

        // 2. auditId is non-identifying.
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("auditId", auditId, false)
            .toJobParameters();

        try {
            // 3. Repository decides new creation, restart, or rejection.
            JobExecution execution =
                launcher.run(dailySalesJob, parameters);

            // May return before job finishes if launcher is async.
            auditStore.recordLaunchOutcome(
                auditId,
                "ACCEPTED",
                execution.getId(),
                null
            );

            log.info(
                "Batch launch accepted: auditId={}, executionId={}",
                auditId,
                execution.getId()
            );

        } catch (JobInstanceAlreadyCompleteException ex) {
            auditStore.recordLaunchOutcome(
                auditId, "ALREADY_COMPLETED", null, null
            );

        } catch (JobExecutionAlreadyRunningException ex) {
            auditStore.recordLaunchOutcome(
                auditId, "ALREADY_RUNNING", null, null
            );

        } catch (JobRestartException ex) {
            auditStore.recordLaunchOutcome(
                auditId, "RESTART_REJECTED",
                null, ex.getClass().getSimpleName()
            );

        } catch (JobParametersInvalidException ex) {
            auditStore.recordLaunchOutcome(
                auditId, "INVALID_PARAMETERS",
                null, ex.getClass().getSimpleName()
            );

        } catch (Exception ex) {
            // Do not assert with certainty whether an execution was created.
            auditStore.recordLaunchOutcome(
                auditId, "LAUNCH_ERROR",
                null, ex.getClass().getSimpleName()
            );

            log.error("Cannot confirm batch launch: auditId={}",
                      auditId, ex);
            throw new IllegalStateException(
                "Batch launch outcome is uncertain: " + auditId, ex
            );
        }

        return auditId;
    }
}
```

**Why catch each exception separately?** On the same launcher call, Spring Batch can reject due to an already-completed instance, active run, invalid restart, or invalid parameters. Audits must capture the exact reason so operators distinguish schedule errors, duplicate triggers, and configuration bugs.

This illustrates the primary flow. In production, failures **persisting the audit outcome after the launcher created an execution** must be monitored separately. If the audit update fails, never assume the job did not run, and never automatically replay with new identifying parameters. Reconciliation against Batch metadata is essential.

Also distinguish **`JobInstance` idempotency** from **business-output idempotency**. On restart, writers still need transactions, unique keys, or safe write logic so already-processed records are not duplicated.

## 10. Connecting the Scheduler to the Coordinator

For a daily cron, the application can configure:

```yaml
spring:
  batch:
    job:
      enabled: false

app:
  scheduling:
    cron: "0 10 1 * * *"
    zone: "Asia/Ho_Chi_Minh"
```

Here `spring.batch.job.enabled=false` stops Spring Boot from auto-running jobs via its startup runner; launches are requested by the `@Scheduled` component. Enable scheduling in the app:

```java
import java.time.Clock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchApplication.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Create the scheduler:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailySalesScheduler {

    private static final ZoneId BUSINESS_ZONE =
        ZoneId.of("Asia/Ho_Chi_Minh");

    private final BatchLaunchCoordinator coordinator;
    private final Clock clock;

    public DailySalesScheduler(
            BatchLaunchCoordinator coordinator,
            Clock clock) {
        this.coordinator = coordinator;
        this.clock = clock;
    }

    @Scheduled(
        cron = "${app.scheduling.cron}",
        zone = "${app.scheduling.zone}"
    )
    public void scheduledDailySales() {
        // At 01:10 today, process yesterday's transactions.
        LocalDate businessDate =
            LocalDate.now(clock.withZone(BUSINESS_ZONE)).minusDays(1);

        coordinator.launch(
            businessDate,
            "SCHEDULED",
            "daily-sales:" + businessDate
        );
    }
}
```

When re-triggered for the same date, `trigger_key` stays identical while a new `auditId` is generated. Thus the audit logs every request attempt while `JobInstance` remains identified by `businessDate`.

If business zone is configurable, `businessDate` calculation must read the same configuration rather than hardcoding a different zone than cron. Injecting `Clock` lets tests exercise near-midnight behavior without relying on the wall clock.

### Notes on `trigger_source`

A backfill API might call:

```java
coordinator.launch(
    LocalDate.parse("2026-11-11"),
    "BACKFILL",
    "backfill-request-783:2026-11-11"
);
```

When APIs have authenticated users, populate `requested_by` from the server-side authentication context rather than trusting a client-supplied value. For external schedulers, take `trigger_key` from the event ID or schedule identifier provided by that system.

## 11. Recording Final Status via `JobExecutionListener`

When `JobLauncher.run(...)` returns, the job may still be running if using an asynchronous launcher. Never set `batch_status=COMPLETED` merely because the call threw no exception.

Use `JobExecutionListener` to record terminal status:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class LaunchAuditJobListener
        implements JobExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(LaunchAuditJobListener.class);

    private final LaunchAuditStore auditStore;

    public LaunchAuditJobListener(LaunchAuditStore auditStore) {
        this.auditStore = auditStore;
    }

    @Override
    public void afterJob(JobExecution execution) {
        String auditId =
            execution.getJobParameters().getString("auditId");

        if (auditId == null) {
            log.warn(
                "No auditId on JobExecution {}",
                execution.getId()
            );
            return;
        }

        try {
            auditStore.recordFinished(
                auditId,
                execution.getStatus(),
                execution.getExitStatus().getExitCode()
            );

        } catch (Exception ex) {
            // Never drop audit failure signals completely.
            log.error(
                "Cannot store final job status: auditId={}, executionId={}",
                auditId,
                execution.getId(),
                ex
            );
            // Needs metrics/alerts and subsequent reconciliation.
        }
    }
}
```

Register the listener on the job:

```java
@Bean("dailySalesJob")
Job dailySalesJob(
        JobRepository jobRepository,
        Step dailySalesStep,
        LaunchAuditJobListener auditListener) {

    return new JobBuilder("dailySalesJob", jobRepository)
        .start(dailySalesStep)
        .listener(auditListener)
        .build();
}
```

Assume `dailySalesStep` is already defined in Batch configuration. The same job must use a stable name so Spring Batch identifies instances via identifying parameters.

### A Valid Race Condition

With a synchronous launcher, `afterJob()` can update `batch_status` **before** `launcher.run(...)` returns and the coordinator records `launch_outcome=ACCEPTED`. Because the code above updates **two disjoint sets of columns**, both final values are preserved.

With an asynchronous launcher, the reverse order is typical: the audit updates to `ACCEPTED` first, then the listener updates the execution result. In between, `batch_status` remains `NULL`. That is a normal in-progress state, not data corruption.

If compliance demands an immutable audit trail, store append-only events in a separate table, e.g., `LAUNCH_REQUESTED`, `LAUNCH_ACCEPTED`, `EXECUTION_FINISHED`. Summary status tables can be projected from those events. The single-row update approach in this lesson is kept concise for clarity.

## 12. Sample Event Sequence

`dailySalesJob` runs for `businessDate=2026-11-15` and succeeds on the first try:

```text
01:10:00  Cron fires trigger daily-sales:2026-11-15
01:10:00  Audit A1: REQUESTED
01:10:01  JobLauncher creates JobExecution 8001
01:10:01  Audit A1: ACCEPTED, job_execution_id=8001
01:10:32  Job finishes
01:10:32  Audit A1: batch_status=COMPLETED
```

An operator clicks “run now” for the same date:

```text
02:00:00  Operator submits request with same businessDate
02:00:00  Audit A2: REQUESTED
02:00:00  JobLauncher rejects:
          JobInstanceAlreadyCompleteException
02:00:00  Audit A2: ALREADY_COMPLETED
          job_execution_id=NULL
```

If the first run fails and is later restarted:

```text
01:10  Audit B1: ACCEPTED -> Execution 8101 -> FAILED
01:30  Audit B2: ACCEPTED -> Execution 8102 -> COMPLETED

B1, B2 have different audit_ids.
Executions 8101, 8102 have different IDs but the same JobInstance.
```

This is why operational reports should show **launch requests**, **accepted launches**, and **successful executions**, instead of collapsing everything into one “run count.”

## 13. Handling Crashes, Timeouts, and Audit Reconciliation

Because writing the audit and creating `JobExecution` do not share a single atomic transaction, failure windows exist:

| Failure point | Observed audit state | What may actually have happened |
| --- | --- | --- |
| Writing `REQUESTED` fails | No audit record | Under fail-closed policy, launcher was not called |
| After writing `REQUESTED`, before calling launcher | `REQUESTED` lingers | Request not sent yet; process may have crashed |
| While launcher is executing | `REQUESTED` or `LAUNCH_ERROR` | Uncertain whether execution was created |
| After execution created, before writing `ACCEPTED` | `REQUESTED` lingers | Job may be running or already completed |
| After writing `ACCEPTED`, process crashes | `ACCEPTED`, no terminal status | Must query `JobRepository` to see if execution finished |
| Listener fails to update audit | Completed execution exists, audit lacks `batch_status` | Recover outcome from metadata |

Because `JobParameters` stores non-identifying `auditId`, links can be recovered from `BATCH_JOB_EXECUTION_PARAMS` and `BATCH_JOB_EXECUTION` when needed. You can also query `JobExplorer` by job name, business date, and execution list.

In operations, a periodic reconciliation task can:

1. Find `REQUESTED` or `LAUNCH_ERROR` audits older than a reasonable threshold.
2. Query Batch metadata by `auditId` and business period.
3. If a matching execution is found, link `job_execution_id` and its status.
4. If no execution evidence exists, classify as `UNKNOWN` or flag for investigation; never assume a job definitely did not run based solely on a timeout.
5. Alert on audits missing outcomes or due schedule periods lacking a successful execution.

Never retry by changing identifying parameters just to “make sure it runs.” That bypasses `JobInstance` guards and risks duplicate processing.

## 14. Auditing in Multi-Scheduler and Multi-Replica Environments

Every replica with `@Scheduled` can fall due simultaneously:

```text
           Cron 01:10
         /     |      \
    Replica A  B       C
       |       |       |
     Audit A  Audit B  Audit C
       |       |       |
       +-------+-------+
               |
        Shared JobRepository
               |
        Same businessDate
```

With a properly configured shared repository, launches for the same instance produce one valid execution while other requests are rejected as running or completed. The audit should still record **all three attempts**, revealing that the scheduler fired duplicates.

However, `JobRepository` does not solve every requirement for a **cluster-wide single trigger**. Depending on architecture, use Quartz JDBC JobStore, distributed locks, a leader scheduler, or an external scheduler. Launch audits help verify whether your coordination mechanism actually prevents duplicate triggers.

When multiple different data periods run concurrently, they are typically distinct `JobInstance`s. Check destination resources, schedule overlaps, and business-key constraints beyond Batch metadata.

## 15. Observability via Logs, Traces, and Dashboards

Database audits should pair with structured logs and metrics. Every launch-related log line should carry clear correlation keys:

```text
event=launch.requested
job=dailySalesJob
auditId=3fe...
triggerSource=SCHEDULED
triggerKey=daily-sales:2026-11-15
businessDate=2026-11-15
```

Once accepted:

```text
event=launch.accepted
auditId=3fe...
jobExecutionId=8001
```

Upon completion:

```text
event=job.finished
auditId=3fe...
jobExecutionId=8001
batchStatus=COMPLETED
exitCode=COMPLETED
```

If using MDC or distributed tracing, attach `auditId` to trace context from scheduler to launcher. Across async threads, propagate correlation context explicitly or persist `auditId` in `JobParameters`; never assume `ThreadLocal` MDC crosses every executor automatically.

Useful metrics include:

- Launch attempts by job, source, and outcome.
- Rate of triggers rejected as `ALREADY_RUNNING` or `ALREADY_COMPLETED`.
- Count of `FAILED`, `COMPLETED`, `STOPPED` executions.
- Latency from schedule due time to launch, when `scheduled_at` is supplied.
- Due business periods lacking a successful execution before SLA.
- Unreconciled `REQUESTED`/`LAUNCH_ERROR` audit records.

**Never attach raw `auditId`, UUIDs, or high-cardinality business keys as metric labels** unless your metrics backend is designed for it. Keep those in logs, traces, or audit tables; keep metric tags to low-cardinality dimensions like job name, source, and outcome.

## 16. Security, Retention, and Scope of Launch Audits

Because audit records trace operational actions, design retention and security policies:

- Store timestamps with timezone or consistently in UTC; store business zone separately when schedule explanation is needed.
- Persist only allowlisted identifying parameters. Never log or audit passwords, tokens, card numbers, PII payloads, or raw exception messages containing sensitive data.
- For manual launches, obtain requester identity from server-side authentication, never trusting a client-supplied `requestedBy` field.
- Restrict write access to the coordinator and Batch service; give observers read-only access.
- Define audit retention, archiving, and query SLAs; decouple audit retention from operational metadata retention if needed.
- If audits must be tamper-evident or serve legal compliance, use append-only storage/event logs with change controls rather than treating an updatable status table as an immutable log.

Launch status auditing does not replace **business-impact auditing**. A `COMPLETED` `JobExecution` does not prove a writer avoided sending duplicate external messages; verify transactions, idempotency keys, and output datasets as well.

## 17. Testing Launch Auditing

Include both **unit tests** for the coordinator and **integration tests** against a real `JobRepository` and audit database. Never wait for real cron wall-clock times: invoke the method or coordinator directly with `Clock.fixed(...)`.

### 17.1. Testing an Accepted Request

With a mocked launcher and audit store, verify exact parameters and identifying flags:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class BatchLaunchCoordinatorTest {

    @Test
    void acceptedLaunchHasAuditCorrelation() throws Exception {
        JobLauncher launcher = mock(JobLauncher.class);
        Job job = mock(Job.class);
        JobExecution execution = mock(JobExecution.class);
        LaunchAuditStore auditStore = mock(LaunchAuditStore.class);

        when(job.getName()).thenReturn("dailySalesJob");
        when(execution.getId()).thenReturn(101L);
        when(launcher.run(eq(job), any(JobParameters.class)))
            .thenReturn(execution);

        Clock clock = Clock.fixed(
            Instant.parse("2026-11-16T01:10:00Z"),
            ZoneOffset.UTC
        );

        BatchLaunchCoordinator service =
            new BatchLaunchCoordinator(
                launcher, job, auditStore, clock
            );

        String auditId = service.launch(
            LocalDate.parse("2026-11-15"),
            "SCHEDULED",
            "daily-sales:2026-11-15"
        );

        ArgumentCaptor<JobParameters> captor =
            ArgumentCaptor.forClass(JobParameters.class);

        verify(launcher).run(eq(job), captor.capture());

        JobParameters params = captor.getValue();

        assertEquals(
            "2026-11-15",
            params.getString("businessDate")
        );
        assertTrue(
            params.getParameter("businessDate").isIdentifying()
        );
        assertEquals(auditId, params.getString("auditId"));
        assertFalse(
            params.getParameter("auditId").isIdentifying()
        );

        InOrder order = inOrder(auditStore, launcher);
        order.verify(auditStore).recordRequested(
            eq(auditId),
            eq("daily-sales:2026-11-15"),
            eq("SCHEDULED"),
            eq("dailySalesJob"),
            eq(LocalDate.parse("2026-11-15")),
            any(Instant.class)
        );
        order.verify(launcher).run(
            eq(job), any(JobParameters.class)
        );
        order.verify(auditStore).recordLaunchOutcome(
            auditId, "ACCEPTED", 101L, null
        );
    }
}
```

The test's core assertion is ordering: **record `REQUESTED` before calling the launcher**, then update the outcome. It also verifies `auditId` does not alter `JobInstance` identity.

### 17.2. Testing a Rejected Launch

Mock `JobLauncher` to throw `JobInstanceAlreadyCompleteException` or `JobExecutionAlreadyRunningException`. Assert:

- Each request has its own audit record with the matching outcome.
- No fake execution ID is recorded when the launcher rejects.
- Rejected requests still capture `job_name`, `source`, `business_date`, and `requested_at`.
- An attempt with no `JobExecution` is never marked `batch_status=FAILED`.

In integration tests, run a real job to `COMPLETED`, then reuse the same identifying parameters for a second request. The audit table must contain two rows while Batch metadata contains only one `JobExecution`.

### 17.3. Testing Restart After Failure

Let the first execution end `FAILED`, then launch again with the same `businessDate`:

| Attempt | `audit_id` | `JobInstance` | `JobExecution` | Final `BatchStatus` |
| --- | --- | --- | --- | --- |
| 1 | Distinct | Same ID | Execution X | `FAILED` |
| 2 | Distinct | Same ID | Execution Y | `COMPLETED` |

Verify both attempts are `ACCEPTED` with distinct execution IDs belonging to the same `JobInstance`. This clearly separates launch auditing from per-instance execution history.

### 17.4. Testing Audit Write Errors, Crashes, and Async Launchers

Additional scenarios to cover:

| Scenario | Expected behavior |
| --- | --- |
| Writing `REQUESTED` fails | Under mandatory audit policy, launcher is never called |
| Writing `ACCEPTED` fails after launcher runs | Audit lacks outcome, yet `JobExecution` remains reconcilable |
| Launcher times out / infrastructure error | Outcome does not falsely claim no job was created |
| Async launcher | Temporary `ACCEPTED` state, then listener writes terminal status |
| Same trigger hits two nodes | Each attempt gets an audit ID; only valid execution runs for identifying parameters |
| Scheduler never fires at all | Zero audit attempts; caught by comparing against expected schedules and absence-of-success checks |
| Clock near date boundary | Business period computed cleanly by zone, audit timestamp consistent |

For concurrency tests, use synchronization primitives like `CountDownLatch` to guarantee the first execution is active before sending the second attempt; avoid timing guesses with `Thread.sleep`.

## 18. Diagnostic Queries

### 18.1. Inspecting Every Attempt for a Period

```sql
SELECT
    audit_id,
    trigger_source,
    trigger_key,
    requested_at,
    launch_outcome,
    job_execution_id,
    batch_status,
    exit_code
FROM batch_launch_audit
WHERE job_name = 'dailySalesJob'
  AND business_date = DATE '2026-11-15'
ORDER BY requested_at, audit_id;
```

This query may return multiple rows even though Spring Batch has only one `JobInstance`. That is the exact goal of auditing every scheduler launch attempt.

### 18.2. Finding Requests Without a Clear Outcome

```sql
SELECT
    audit_id,
    job_name,
    business_date,
    requested_at,
    launch_outcome
FROM batch_launch_audit
WHERE launch_outcome IN ('REQUESTED', 'LAUNCH_ERROR')
  AND requested_at < CURRENT_TIMESTAMP - INTERVAL '15 minutes'
ORDER BY requested_at;
```

The 15-minute window is illustrative; tune it for SLA, job type, and launcher mode. Returned rows are **reconciliation candidates**, not automatic proof the job failed to run.

### 18.3. Summarizing Launch Outcomes by Date

```sql
SELECT
    business_date,
    launch_outcome,
    COUNT(*) AS attempts
FROM batch_launch_audit
WHERE job_name = 'dailySalesJob'
GROUP BY business_date, launch_outcome
ORDER BY business_date, launch_outcome;
```

This report reveals spikes in `ALREADY_RUNNING` (overlapping schedules or multi-node firing), `INVALID_PARAMETERS` after a deployment, or bursts of `LAUNCH_ERROR` coinciding with infrastructure incidents.

## 19. Common Design Mistakes

| Issue | Consequence | Fix |
| --- | --- | --- |
| Auditing only after `JobLauncher.run` succeeds | Loses visibility into rejected requests | Persist `REQUESTED` before calling launcher |
| Reading only `BATCH_JOB_EXECUTION` | Misses triggers that created no execution | Maintain a dedicated launch-attempt table |
| Using `jobExecutionId` as audit primary key | Cannot store rejected attempts | Generate a dedicated `auditId` |
| Making `auditId` an identifying parameter | Restarts/duplicate triggers become new instances | Mark `auditId` non-identifying |
| Treating `ACCEPTED` as job success | False reporting when job fails or runs async | Track final `BatchStatus` separately |
| Writing audit inside a large rolling-back transaction | Audit vanishes when job fails | Use independent audit transactions |
| Retrying with a new identifying UUID on audit update error | Risks double-processing business periods | Preserve business keys and reconcile metadata |
| Storing raw `JobParameters` or exception messages | Leaks tokens and personal data | Allowlist fields and standardize error codes |
| Auditing only `ACCEPTED` requests | Fails to catch missing scheduler ticks | Compare against expected periods |
| Using `auditId` as a metric tag | Unbounded metric cardinality | Keep `auditId` in logs/traces/audit DB |
| Deleting audits alongside Batch metadata cleanup | Destroys investigation history | Apply separate retention policies |
| Running multiple replicas without duplicate visibility | Hides coordination bugs | Record source, trigger key, and audit outcome |

## 20. Practice Exercise

Build a `dailySettlementJob` running daily at 02:00, processing the previous day's transactions and storing metadata in Spring Batch's repository. Create the `batch_launch_audit` table and a coordinator similar to the example.

Exercise four scenarios: first launch succeeds; duplicate trigger for the same period is rejected; first execution fails then restarts and succeeds; audit outcome update fails after the repository creates an execution. In each case, inspect audit row counts, outcomes, `JobInstance` ID, `JobExecution` ID, and final `BatchStatus`.

Next, simulate two schedulers firing for the same date. Write a query counting attempts per `trigger_key` and trigger an alert when a scheduled period receives unexpected duplicate requests. Finally, build a reconciliation task finding overdue `REQUESTED` rows and linking outcomes from Batch metadata via `auditId`.

## 21. Conclusion

Launch auditing separates three distinct facts: **whether the scheduler requested a run**, **whether Spring Batch accepted the request**, and **whether the job ultimately succeeded**. Because many requests can be rejected without creating a `JobExecution`, systems must persist an audit record for every attempt before calling `JobLauncher`. Pairing a non-identifying `auditId` for metadata correlation, a listener for terminal status, and reconciliation for infrastructure faults creates a trustworthy execution trail for testing, operations, and incident investigation.

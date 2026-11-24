# Re-running a COMPLETED Job as a Restart: A Common Pitfall in Spring Batch

## 1. Context and Symptoms

A common scenario in Spring Batch operations:

1. A data import job finishes with status `COMPLETED`.
2. An operator discovers that the report is missing a field or that the source data was corrected.
3. They resubmit the **same job name and the same identifying parameters**, expecting the job to "restart and run again".
4. Spring Batch rejects the request with `JobInstanceAlreadyCompleteException`.

The message typically reads along these lines:

```text
A job instance already exists and is complete for identifying parameters
```

This is not a spontaneous failure of `JobRepository`. **Spring Batch intentionally refuses to restart an already completed `JobInstance`.** This mechanism protects a finished processing period from unintended duplicate execution.

This lesson belongs to the **Common Pitfalls** group of **Spring Batch Core Processing**, focusing on **"Re-running a COMPLETED job as a restart"**. After this lesson, you will:

- Understand the exact relationship between `Job`, `JobParameters`, `JobInstance`, and `JobExecution`.
- Distinguish between **restarting an incomplete instance** and **running a new instance to reprocess data**.
- Know why the same identifying parameters are rejected once an instance is `COMPLETED`.
- Avoid using timestamps or random `run.id` values to bypass the error without control.
- Choose a controlled approach when completed data genuinely needs to be redone.
- Design idempotent writers, auditing, checkpoints, and tests to prevent duplicate writes.
- Handle the error properly in schedulers, operations APIs, and Spring Boot applications.

The examples use Java 17+, Spring Boot 3.x, and Spring Batch 5.x. The principles regarding JobInstance and restart are similar across other versions, though some APIs and metadata schemas may differ.

## 2. Four Concepts You Must Not Confuse

First, identify **which object** is being re-run.

| Concept | Meaning | Example |
| --- | --- | --- |
| `Job` | Logical definition of steps | `dailySettlementJob` |
| `JobParameters` | Set of parameters provided at launch; has identifying and non-identifying fields | `businessDate=2026-11-15` |
| `JobInstance` | Identity of **one logical processing period**: job name + identifying parameters | Settlement for 2026-11-15 |
| `JobExecution` | **One execution attempt** of a JobInstance | First attempt failed, next restart succeeded |

Model:

```text
Job: dailySettlementJob
         |
         +-- JobInstance 1001
         |   identifying: businessDate=2026-11-15
         |       |
         |       +-- JobExecution 5001: FAILED
         |       +-- JobExecution 5002: COMPLETED
         |
         +-- JobInstance 1002
             identifying: businessDate=2026-11-16
                 |
                 +-- JobExecution 5003: COMPLETED
```

The two executions 5001 and 5002 belong to the **same JobInstance** because they process the same business period. Execution 5003 belongs to a different instance because `businessDate` differs.

For instance 1001, once execution 5002 is `COMPLETED`, sending the same identifying parameters to "restart a third time" will be rejected.

### JobInstance Identity Formula

```text
JobInstance identity
    = jobName + identifying JobParameters
```

This formula does not mean every parameter is used to distinguish instances. Only parameters marked **identifying** contribute to identity.

For example:

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedAt", "2026-11-15T18:10:00Z", false)
    .toJobParameters();
```

- `businessDate` is identifying: same business date ⇒ same instance.
- `requestedAt` is non-identifying: can change between requests without creating a new instance identity.

**Consequence:** If the job is already `COMPLETED` for `businessDate=2026-11-15`, changing `requestedAt` will not cause the job to restart or run anew. Spring Batch still sees that the old instance is already complete.

## 3. What Is Restart and What Is Reprocess?

This is the core point of the lesson.

### Restart

**Restart** means continuing a `JobInstance` whose previous run did not finish successfully—typically in `FAILED` or `STOPPED` status—if the job configuration and metadata allow it.

For example:

```text
Job name: dailySettlementJob
Identifying parameters: businessDate=2026-11-15

JobExecution 5001 -> FAILED
  stepA -> COMPLETED
  stepB -> FAILED

Restart with the same identifying parameters:
JobExecution 5002 -> COMPLETED
  stepA -> typically skipped
  stepB -> re-run using checkpoint/restart state
```

Spring Batch relies on `JobRepository` and `ExecutionContext` to determine which steps have completed and which state needs to be restored.

### Intentional Reprocess or Rerun

**Reprocess** means reprocessing already-completed data due to a new business decision: for instance, the source was fixed, calculation logic changed, or a report must be regenerated. For a `COMPLETED` instance, this is **not a restart**.

If you want Spring Batch to perform a new run, you must define a **new JobInstance** via a different set of identifying parameters or a different job name by intentional design. At the same time, the application must define what happens to the old results.

For example:

```text
JobInstance 1001:
  businessDate=2026-11-15
  revision=1
  JobExecution -> COMPLETED

JobInstance 1002 (controlled reprocess):
  businessDate=2026-11-15
  revision=2
  JobExecution -> COMPLETED
```

Both instances relate to November 15, but their processing revisions differ. **Revision must carry business meaning, be managed, and be audited**, not be a random value generated merely to dodge an exception.

### Quick Decision Table

| Previous state | Desired outcome | Appropriate action |
| --- | --- | --- |
| No instance yet | Run a new period | Launch with the period's business key |
| `FAILED`, restartable | Continue the old period after fixing the bug | Re-launch with the same identifying parameters |
| `STOPPED`, eligible for restart | Continue the stopped period | Restart with the same identifying parameters |
| `STARTED` or `STARTING` | User sent a duplicate request | Monitor the existing execution; do not run concurrently |
| `COMPLETED` | Scheduler re-sent with no business change | Ignore as a valid duplicate |
| `COMPLETED` | Want to correct published results | Versioned reprocess workflow, target data strategy, and audit |
| `COMPLETED` | Want to run another period | Change the business key to the new period |

## 4. Why Does Spring Batch Reject a COMPLETED Job?

When calling:

```java
JobExecution execution =
    jobLauncher.run(dailySettlementJob, parameters);
```

Spring Batch uses the repository to look up the `JobInstance` matching the job name and identifying parameters. Once a JobInstance has completed, the job launcher will not create a new JobExecution to re-run that same instance. The request may receive the exception:

```java
org.springframework.batch.core.repository
    .JobInstanceAlreadyCompleteException
```

This is a data-protection rule. If every re-run request were accepted, the system could:

- Record duplicate transactions or billing entries.
- Re-send emails, notifications, or events already dispatched.
- Double-count total revenue.
- Overwrite old reports without an audit trail.
- Conflict with the next processing period.
- Produce unexplainable results because the source changed.

Protection at the JobInstance level does not automatically guarantee exactly-once across every external system, but it prevents a common source of duplicate runs.

### An Exception Does Not Always Prove the Scheduler Is Broken

If a scheduler runs on a daily cron but due to misconfiguration always sends the same `businessDate`, the job succeeds the first time and subsequent runs are rejected. At the Spring Batch level, the protection rule is doing the right thing. **The bug is in the scheduler's period-calculation logic**, not in `JobRepository`.

Conversely, if an operator intentionally resubmits the same period to check status, `JobInstanceAlreadyCompleteException` can be treated as a valid answer: "this period is already complete, not launching again".

## 5. Example: Same Parameters After COMPLETED

Suppose you define:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();

JobExecution first =
    jobLauncher.run(dailySettlementJob, parameters);
```

If `first.getStatus() == BatchStatus.COMPLETED`, then calling:

```java
JobExecution second =
    jobLauncher.run(dailySettlementJob, parameters);
```

does not create a new execution; instead, the launcher rejects it because the instance is already complete.

Nor is it solved by merely adding a **non-identifying** parameter:

```java
JobParameters later = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedAt", "2026-11-16T03:00:00Z", false)
    .toJobParameters();
```

Because the identifying part remains identical, Spring Batch still finds the same `COMPLETED` JobInstance.

## 6. A Dangerous Mistake: Adding run.id or Timestamp to Every Run

A commonly seen "fix":

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
```

With the default builder methods, added parameters are identifying unless specified otherwise. When `run.id` changes, each invocation can become a **new JobInstance** even though it still processes November 15.

Result:

```text
dailySettlementJob + date=2026-11-15 + run.id=101
    -> JobInstance A, COMPLETED

dailySettlementJob + date=2026-11-15 + run.id=102
    -> JobInstance B, COMPLETED

dailySettlementJob + date=2026-11-15 + run.id=103
    -> JobInstance C, COMPLETED
```

The job runs again, but these are **three different instances**, not a restart. If the writer is not idempotent, data may be written three times.

**Do not automatically increment `run.id` just to "bypass" the exception** when the real problem is resuming a failed instance or preventing reprocessing of a completed period.

### JobParametersIncrementer and startNextInstance

Spring Batch provides the `JobParametersIncrementer` mechanism and APIs related to **start next instance**, such as an incrementer that increments `run.id`. This is a tool for launching the **next JobInstance** with changed parameters, not for restarting an already completed instance.

| Action | Meaning |
| --- | --- |
| `JobLauncher.run(job, sameIdentifyingParameters)` after FAILED | Can restart the existing instance |
| `JobLauncher.run(job, sameIdentifyingParameters)` after COMPLETED | Rejected |
| `JobOperator.startNextInstance(jobName)` with incrementer | Creates the next instance per the incrementer's rule |
| Running with identifying `revision=2` | New instance representing a business processing revision |

If an incrementer only increments an ID without describing the data period, the application still needs to know exactly which source will be processed and how target data is updated.

## 7. Scenarios Where COMPLETED Data Must Be Redone

Not every "rerun" request is wrong. There are legitimate business cases:

1. The Nov 15 file was missing part of its data and a corrected source was received later.
2. The commission calculation formula had a bug and an old period needs recalculation.
3. The exported report output was corrupted in a file storage system outside Batch.
4. A reference source (exchange rates, catalog, policy) was adjusted.
5. Users need to generate a **new report revision**, keeping the old one for comparison.

In those cases, you need an **intentional reprocess** workflow, not a trick on the restart mechanism.

One pattern can use identifying parameters like:

```java
JobParameters reprocessParameters =
    new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("revision", 2L, true)
        .addString("requestedBy", "operations", false)
        .addString("reasonCode", "SOURCE_CORRECTION", false)
        .toJobParameters();
```

`revision=2` is managed by the operations system as a valid version. It creates a different JobInstance from `revision=1`.

However, changing `revision` **does not automatically make target data right**. The writer must have a clear policy:

- Write into a versioned staging table, then validate and publish.
- Upsert/replace the period's results by unique key.
- Write a new version and switch an "active version" pointer under control.
- Use compensating events when old side effects cannot be rolled back.
- Prevent duplicate notifications/payments with a business idempotency key.

A new revision record can be created for recalculation, but that does not mean sending the email or charging the customer a second time.

## 8. Designing Version-Safe Reprocessing

A suitable pipeline:

```text
       Request reprocess date D, revision R
                       |
                       v
            Verify permissions and reason
                       |
                       v
              Lock source snapshot
              checksum/rule version
                       |
                       v
           Create new JobInstance: (D,R)
                       |
                       v
                Write to staging
                       |
                       v
                 Validate data
                       |
                     PASS?
                  /         \
                Yes          No
                |              |
                v              v
       Controlled publish    Keep old results
       / switch active ver   + report error
                |
                v
       Audit revision, execution,
       source hash, and outcome
```

Illustrative data tables:

```sql
CREATE TABLE settlement_result_version (
    business_date DATE NOT NULL,
    revision BIGINT NOT NULL,
    account_id VARCHAR(100) NOT NULL,
    net_amount DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (business_date, revision, account_id)
);

CREATE TABLE settlement_active_version (
    business_date DATE PRIMARY KEY,
    revision BIGINT NOT NULL
);
```

When running a reprocess, the writer writes the new `(business_date, revision, account_id)` into staging/result-version. Only after reconciliation succeeds does the system update the active version table or replace current results inside an appropriate transaction.

This design helps:

- Query old results.
- Prevent duplicates within a single version.
- Compare deltas across revisions.
- Maintain an audit trail and controlled business rollback.
- Clearly distinguish a **technical run** from a **published data version**.

If the system already has a target table that does not support versions, upsert or replace options may also work. However, you must control foreign keys, transactions, downstream impacts, and the case where the job stops midway through replacing data.

## 9. Distinguishing Restart from Reprocess in a Scheduler

Schedulers typically emit business periods by date/time:

```text
Cron 01:10 on 2026-11-16
      |
      v
businessDate = 2026-11-15
      |
      v
dailySettlementJob + date=2026-11-15
```

The first request is accepted. If the scheduler accidentally fires the same period again at 01:15:

- If the previous execution is still running, you may receive `JobExecutionAlreadyRunningException`.
- If the previous execution is `COMPLETED`, you receive `JobInstanceAlreadyCompleteException`.
- If the previous execution is `FAILED`, it may restart, depending on job configuration and orchestration policy.

The scheduler must record the different outcomes rather than catching `Exception` and blindly incrementing a timestamp.

An orchestration service can return business statuses:

| Launch status | Meaning for scheduler |
| --- | --- |
| `ACCEPTED_NEW` | A new JobInstance was launched |
| `ACCEPTED_RESTART` | A new JobExecution for an incomplete instance was created |
| `ALREADY_RUNNING` | An execution is active; do not fire another |
| `ALREADY_COMPLETED` | Period already finished; ignore duplicate trigger |
| `RESTART_REJECTED` | Configuration/state needs inspection |
| `INVALID_PARAMETERS` | Request needs fixing |
| `UNKNOWN_ERROR` | Reconcile with JobRepository before retrying |

The strings above are **application-defined codes**, not standard Spring Batch enums. When a launcher runs asynchronously, the request being accepted does not prove the job has finished. You must monitor the final status of the JobExecution.

## 10. Handling JobInstanceAlreadyCompleteException Properly

A safe pattern is classifying exceptions and reporting clear information to the user or orchestrator:

```java
import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
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
public class SettlementLaunchService {

    private static final Logger log =
        LoggerFactory.getLogger(SettlementLaunchService.class);

    private final JobLauncher launcher;
    private final Job settlementJob;

    public SettlementLaunchService(
            JobLauncher launcher,
            @Qualifier("dailySettlementJob") Job settlementJob) {
        this.launcher = launcher;
        this.settlementJob = settlementJob;
    }

    public LaunchResult launchScheduled(LocalDate businessDate) {
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .toJobParameters();

        try {
            JobExecution execution =
                launcher.run(settlementJob, parameters);

            log.info(
                "event=batch.launch.accepted job={} date={} " +
                "instanceId={} executionId={} status={}",
                settlementJob.getName(),
                businessDate,
                execution.getJobInstance().getInstanceId(),
                execution.getId(),
                execution.getStatus()
            );

            // Do not infer SUCCESS from launcher.run() returning;
            // the launcher may be asynchronous.
            return new LaunchResult(
                "ACCEPTED",
                execution.getId()
            );

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info(
                "event=batch.launch.skipped reason=already_completed " +
                "job={} date={}",
                settlementJob.getName(),
                businessDate
            );
            return new LaunchResult("ALREADY_COMPLETED", null);

        } catch (JobExecutionAlreadyRunningException ex) {
            log.info(
                "event=batch.launch.skipped reason=already_running " +
                "job={} date={}",
                settlementJob.getName(),
                businessDate
            );
            return new LaunchResult("ALREADY_RUNNING", null);

        } catch (JobRestartException |
                 JobParametersInvalidException ex) {
            log.error(
                "event=batch.launch.rejected job={} date={}",
                settlementJob.getName(),
                businessDate,
                ex
            );
            return new LaunchResult("REJECTED", null);

        } catch (Exception ex) {
            log.error(
                "event=batch.launch.error job={} date={}",
                settlementJob.getName(),
                businessDate,
                ex
            );
            // Do not generate run.id to retry.
            return new LaunchResult("UNKNOWN_ERROR", null);
        }
    }

    public record LaunchResult(String outcome, Long executionId) {
    }
}
```

This code illustrates how to record the outcome of a launch request; it does not replace a monitoring API. `UNKNOWN_ERROR` can include infrastructure errors occurring after the JobExecution was created but before the caller received a response; reconcile with the repository before concluding the job has not run.

`ALREADY_COMPLETED` for a duplicate trigger is handled as a **completed period**, not automatically logged as a critical system error. If the request comes from an approved reprocess operation, a separate API/handler path must be used to create a new revision.

## 11. Why Is JobRestartException Not JobInstanceAlreadyCompleteException?

Several exception groups relate to state and configuration:

| Exception | Typical situation | What to check |
| --- | --- | --- |
| `JobInstanceAlreadyCompleteException` | Instance with same identifying parameters is already complete | Do not restart; ignore duplicate or design a new reprocess |
| `JobExecutionAlreadyRunningException` | Instance currently has an active execution | Wait for the old execution; do not fire duplicates |
| `JobRestartException` | Restart is forbidden or invalid due to configuration/state | Check `preventRestart()`, Step state, metadata |
| `JobParametersInvalidException` | Request is missing or has invalid parameters | Fix parameters per `JobParametersValidator` |
| Other infrastructure exceptions | Launch outcome cannot be confirmed | Check metadata before retrying |

If a job has already finished, changing a step's `ExitStatus` or start count does not turn it into a restartable instance. Job-level status must be understood separately from individual step statuses.

## 12. BatchStatus and ExitStatus: Do Not Confuse COMPLETED with Exit Code

`BatchStatus` represents lifecycle status, such as `STARTED`, `COMPLETED`, `FAILED`, or `STOPPED`. `ExitStatus` is an exit code that can be customized by the application, often used for flow routing.

For example, a job processing an empty source can finish with:

```text
BatchStatus = COMPLETED
ExitStatus  = NO_DATA
```

If policy treats "no data" as a valid completion case, the instance is still considered completed, and sending the same identifying parameters again will not make it restart.

Conversely, an execution with a log stating "processed 1000 items" but `BatchStatus=FAILED` is still not completed. Do not rely solely on a log line, a custom exit code, or the launcher returning an object to decide actual status.

### A Custom ExitStatus Does Not Automatically Enable Restart

A listener may return `ExitStatus("WARNING")` or `ExitStatus("NO_DATA")`. This **does not automatically convert** `BatchStatus.COMPLETED` into `FAILED`. If a data quality failure should fail the job, you must design the flow/step and final status explicitly.

## 13. Be Careful with allowStartIfComplete(true)

Spring Batch provides the method:

```java
Step step = new StepBuilder("revalidateStep", repository)
    .tasklet(revalidateTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
```

`allowStartIfComplete(true)` allows a **COMPLETED step** to run again inside a **new JobExecution of a restartable JobInstance**. It does not bypass the rule that a **COMPLETED JobInstance cannot be restarted**.

For example:

```text
JobInstance K:
  JobExecution 1: FAILED
    prepareStep: COMPLETED
    writeStep: FAILED

Restart JobInstance K:
  prepareStep has allowStartIfComplete(true)
    -> can run again even though the step previously COMPLETED
  writeStep -> runs again from checkpoint
```

But:

```text
JobInstance K:
  JobExecution 2: COMPLETED

Resubmit the same identifying parameters:
  -> JobInstanceAlreadyCompleteException
  -> allowStartIfComplete(true) cannot help
```

This is a common confusion: **controlling step re-execution** is different from **allowing an entire job instance to restart**.

Similarly, setting `restartable=true` or not calling `preventRestart()` does not mean Spring Batch allows re-running an already completed instance.

## 14. Should You Delete Metadata to Re-run a Job?

A dangerous practice in production is deleting data from:

- `BATCH_JOB_INSTANCE`
- `BATCH_JOB_EXECUTION`
- `BATCH_JOB_EXECUTION_PARAMS`
- `BATCH_STEP_EXECUTION`
- The corresponding execution context tables

so that Spring Batch "forgets" the `COMPLETED` instance.

**Never use this approach to reprocess.** Deleting metadata erases execution history, breaks restart/checkpoint relationships, hinders auditing, and can create inconsistencies with data already committed in the target system.

Even when the repository has no metadata left, **previous business results may still reside in the database, files, APIs, or queues**. The re-run job will not know what was written earlier and may create duplicates.

### Test Environments

In integration tests, using a utility such as `JobRepositoryTestUtils.removeJobExecutions()` to isolate metadata between tests is reasonable when running against an **isolated test database**.

That is **not an operational procedure for re-running a completed job in production**.

If you need to preserve a new version of processed data, design a reprocess flow with meaningful identifying parameters and an explicit target update strategy.

## 15. What Happens to Target Data When Creating a New Instance?

Spring Batch controls execution identity, but **does not automatically delete or deduplicate business results**.

Some writer types and risks:

| Writer type | When creating a new instance for the same period | Mitigation |
| --- | --- | --- |
| `INSERT` without unique constraint | Inserts duplicate records | Unique key/constraint, staging, idempotency rules |
| `INSERT` with unique constraint | May fail with duplicate key | Intentional upsert/replace design |
| `UPDATE` by business key | May overwrite old results | Auditing, versioning, verifying correctness and downstream impact |
| Writer producing a fixed file | May overwrite or append to old file | File naming/versioning, write to temporary file then publish |
| Writer sending emails | Emails may be sent again | Deduplicate by business event; never re-send unconditionally |
| Writer calling payment API | Risk of duplicate financial impact | Idempotency key and state reconciliation |
| Writer publishing messages | Events may be re-emitted | Outbox/dedupe key and idempotent consumer |

PostgreSQL example:

```sql
CREATE TABLE daily_settlement (
    business_date DATE NOT NULL,
    account_id VARCHAR(100) NOT NULL,
    net_amount NUMERIC(18, 2) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (business_date, account_id)
);
```

A primary key on `(business_date, account_id)` helps prevent logical duplicates in the table. If a reprocess must update amounts, an `UPSERT` can be designed:

```sql
INSERT INTO daily_settlement (
    business_date, account_id, net_amount
)
VALUES (:businessDate, :accountId, :netAmount)
ON CONFLICT (business_date, account_id)
DO UPDATE SET
    net_amount = EXCLUDED.net_amount,
    updated_at = CURRENT_TIMESTAMP;
```

This prevents row counts from doubling, but **does not automatically guarantee business correctness**: which fields are allowed to update, whether downstream systems already read old results, and whether changes must be audited? For financial data, it may be more appropriate to write results under a new version and only switch the active version after reconciliation.

## 16. Guide to Handling JobInstanceAlreadyCompleteException

When encountering this error, follow a structured sequence instead of immediately changing parameters:

**Step 1 — Identify the data period.** Record the job name, identifying parameters, rule/source version, and business requirement: why do you want to run it again?

**Step 2 — Inspect instance history.** Use `JobExplorer` or query metadata to confirm the instance is `COMPLETED` and identify the last execution.

**Step 3 — Classify the request.** If it is a duplicate trigger, ignore it and report "already processed". If it was a previously failed, incomplete job, look into restart. If it is a reprocess, move to the next step.

**Step 4 — Assess data impact.** Determine which tables/files/APIs already hold results, which downstream systems consumed them, and whether any irreversible side effects occurred.

**Step 5 — Design the identity of the new processing run.** Choose an identifying `revision` or `reprocessVersion`, along with reason and approval; the source snapshot must have an explicit version/checksum.

**Step 6 — Execute under control.** Write to staging or use upsert/versioning with idempotency; avoid unchecked overwrites.

**Step 7 — Reconcile and audit.** Verify counts, total amounts, business keys, changes versus old results, and publish status.

**Step 8 — Close the request.** Store the request ID, approver, reason, new JobInstance ID/JobExecution ID, reconciliation result, and effective time of the new data.

If current status cannot be verified, do not automatically reprocess solely because the caller timed out. The launcher call might already have created an execution before the caller failed to receive a response.

## 17. Using JobExplorer to Observe Instances and Executions

A metadata-reading service helps distinguish completed runs from running or failed ones.

Example lookup by job name and parameters:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class SettlementHistoryReader {

    private final JobExplorer explorer;

    public SettlementHistoryReader(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public List<JobExecution> executions(
            String jobName,
            JobParameters parameters) {

        JobInstance instance =
            explorer.getJobInstance(jobName, parameters);

        if (instance == null) {
            return List.of();
        }

        return explorer.getJobExecutions(instance);
    }
}
```

For Spring Batch 5.x, `JobExplorer.getJobInstance(jobName, parameters)` lets you look up a JobInstance by parameter set. In projects spanning multiple Batch versions, adjust to the active API interface.

The list of `JobExecution`s should be inspected alongside `BatchStatus`, `ExitStatus`, and execution timestamps. Do not infer that the last execution is `COMPLETED` solely from item counts or scheduler log lines.

### SQL to Inspect Metadata

You can query standard Spring Batch tables in **read-only** mode:

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE AS ji
JOIN BATCH_JOB_EXECUTION AS je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailySettlementJob'
ORDER BY ji.JOB_INSTANCE_ID, je.JOB_EXECUTION_ID;
```

With the Spring Batch 5.x schema, the parameters table usually has a corresponding structure:

```sql
SELECT
    je.JOB_EXECUTION_ID,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION AS je
JOIN BATCH_JOB_EXECUTION_PARAMS AS p
    ON p.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
ORDER BY je.JOB_EXECUTION_ID, p.PARAMETER_NAME;
```

Metadata table/column names may differ across Spring Batch versions and customized schemas. These queries only illustrate **reading history**, and updating status directly via SQL is not recommended.

## 18. Example Job Definition Restartable After FAILED

A standard Job is restartable if configuration and metadata allow it. This does not alter the rule against restarting an already completed instance.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SettlementJobConfig {

    @Bean("dailySettlementJob")
    Job dailySettlementJob(
            JobRepository repository,
            @Qualifier("settlementStep") Step step) {

        return new JobBuilder("dailySettlementJob", repository)
            .start(step)
            .build();
    }
}
```

If the step fails:

```text
JobInstance K
    |
    +-- JobExecution 1: FAILED
```

The same identifying parameters can launch JobExecution 2. If the second attempt succeeds:

```text
JobInstance K
    |
    +-- JobExecution 1: FAILED
    +-- JobExecution 2: COMPLETED
```

From that point on, JobInstance K cannot be restarted again with the same identity.

### preventRestart()

Spring Batch lets you forbid restarts even when a job fails:

```java
Job job = new JobBuilder("oneShotJob", repository)
    .start(step)
    .preventRestart()
    .build();
```

In that case, attempting to restart an instance that already has an execution may throw `JobRestartException`. This option **does not** make a completed job runnable again; it makes the restart policy stricter.

## 19. Integration Test Example: COMPLETED Cannot Restart

The test below runs a real job through `JobLauncher` and `JobRepository` against an H2 database dedicated to the test. The job has a counting tasklet so we can observe which instance was actually launched.

Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Example:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = CompletedInstanceTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:completed_job_test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
    }
)
class CompletedInstanceTest {

    @Autowired
    private JobLauncher launcher;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("demoJob")
    private Job job;

    @Autowired
    @Qualifier("runCounter")
    private AtomicInteger counter;

    @BeforeEach
    void reset() {
        repositoryTestUtils.removeJobExecutions();
        counter.set(0);
    }

    private JobParameters parameters(
            String businessDate,
            String requestId,
            Long revision) {

        JobParametersBuilder builder =
            new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("requestId", requestId, false);

        if (revision != null) {
            builder.addLong("revision", revision, true);
        }

        return builder.toJobParameters();
    }

    @Test
    void sameIdentityAfterCompletedIsRejected() throws Exception {
        JobParameters firstRequest =
            parameters("2026-11-15", "request-A", null);

        JobExecution first = launcher.run(job, firstRequest);

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertEquals(1, counter.get());

        // requestId changes but is NON-identifying.
        JobParameters duplicateRequest =
            parameters("2026-11-15", "request-B", null);

        assertThrows(
            JobInstanceAlreadyCompleteException.class,
            () -> launcher.run(job, duplicateRequest)
        );

        // Tasklet is not invoked again.
        assertEquals(1, counter.get());
    }

    @Test
    void newBusinessDateCreatesAnotherInstance() throws Exception {
        JobExecution d1 = launcher.run(
            job, parameters("2026-11-15", "A", null)
        );

        JobExecution d2 = launcher.run(
            job, parameters("2026-11-16", "B", null)
        );

        assertEquals(BatchStatus.COMPLETED, d1.getStatus());
        assertEquals(BatchStatus.COMPLETED, d2.getStatus());

        assertNotEquals(
            d1.getJobInstance().getInstanceId(),
            d2.getJobInstance().getInstanceId()
        );
        assertEquals(2, counter.get());
    }

    @Test
    void explicitRevisionCreatesNewInstanceNotRestart()
            throws Exception {

        JobExecution original = launcher.run(
            job, parameters("2026-11-15", "A", 1L)
        );

        JobExecution reprocessed = launcher.run(
            job, parameters("2026-11-15", "B", 2L)
        );

        assertEquals(BatchStatus.COMPLETED, original.getStatus());
        assertEquals(BatchStatus.COMPLETED, reprocessed.getStatus());

        // Two different JobInstances.
        assertNotEquals(
            original.getJobInstance().getInstanceId(),
            reprocessed.getJobInstance().getInstanceId()
        );
        assertEquals(2, counter.get());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean("runCounter")
        AtomicInteger runCounter() {
            return new AtomicInteger();
        }

        @Bean("demoStep")
        Step demoStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("runCounter") AtomicInteger counter) {

            return new StepBuilder("demoStep", repository)
                .tasklet((contribution, context) -> {
                    counter.incrementAndGet();
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean("demoJob")
        Job demoJob(
                JobRepository repository,
                @Qualifier("demoStep") Step step) {

            return new JobBuilder("demoJob", repository)
                .start(step)
                .build();
        }
    }
}
```

### Meaning of the Three Tests

1. **`sameIdentityAfterCompletedIsRejected`:** same `businessDate`, changing non-identifying `requestId` is still rejected. The tasklet does not run again.
2. **`newBusinessDateCreatesAnotherInstance`:** a different date creates another instance; this is a normal new processing period.
3. **`explicitRevisionCreatesNewInstanceNotRestart`:** same date with a different identifying revision creates a new instance. The test only proves identity; it does not mean reprocessing is adequately controlled in business terms.

The example uses in-memory H2 and a counter for easy observation, and **does not run Content QA in STEP 4**. With a real writer, integration tests must also verify target tables, transactions, and idempotency before considering reprocessing safe.

## 20. Testing Restart After FAILED for Comparison

To avoid confusion, add a case where the job fails before completing. Suppose a tasklet throws an error once:

```java
AtomicBoolean failOnce = new AtomicBoolean(true);

Step flakyStep = new StepBuilder("flakyStep", repository)
    .tasklet((contribution, context) -> {
        if (failOnce.getAndSet(false)) {
            throw new IllegalStateException("Simulated failure");
        }
        return RepeatStatus.FINISHED;
    }, transactionManager)
    .build();
```

With fixed identifying `JobParameters`:

```text
First run:
  JobInstance ID = 2001
  JobExecution ID = 6101
  BatchStatus = FAILED

Second run (same identifying params):
  JobInstance ID = 2001
  JobExecution ID = 6102
  BatchStatus = COMPLETED

Third run (same identifying params):
  JobInstanceAlreadyCompleteException
```

This case illustrates **true restart**: the first execution did not finish; the subsequent execution is a new attempt of the same instance. Once the restart completes, the instance can no longer be restarted.

With real step/chunk failures, tests must verify that previously `COMPLETED` steps are skipped per restart configuration, committed data is not double-written, and the reader's checkpoint is restored accurately.

## 21. Test Matrix for "Restarting a COMPLETED Job"

| Scenario | Identifying parameters | Previous state | Expected outcome |
| --- | --- | --- | --- |
| First run | Date D | No instance yet | Creates instance and execution |
| Resubmitted identically | Date D | `COMPLETED` | `JobInstanceAlreadyCompleteException` |
| Changed non-identifying request ID | Date D | `COMPLETED` | Still rejected |
| Changed identifying businessDate | Date D+1 | D is `COMPLETED` | New instance |
| Changed identifying revision | Date D, revision 2 | D/revision 1 `COMPLETED` | New instance, **not a restart** |
| First run FAILED | Date D | `FAILED` | Can restart same instance |
| First run STOPPED | Date D | `STOPPED` | Can restart per policy |
| First run currently running | Date D | `STARTED` | Rejects duplicate launch |
| Job has `preventRestart()` | Date D | `FAILED` | Restart rejected |
| Step has `allowStartIfComplete(true)` | Date D | Job is `COMPLETED` | Still does not restart job |
| Job `COMPLETED` with `ExitStatus=NO_DATA` | Date D | `COMPLETED` | Still does not restart job |
| Source changed while keeping identity | Date D | `COMPLETED` | Rejected; requires versioned reprocess |
| Deleted test metadata then ran | Date D | Metadata cleaned in test | May create instance, **not a production solution** |
| Two nodes fire the same trigger | Date D | Launch contention | One valid execution; other requests may be rejected |

For concurrent tests, use synchronization primitives like `CountDownLatch` to ensure the first execution is genuinely running before the second trigger arrives, rather than relying on `Thread.sleep`.

## 22. Anti-Patterns to Avoid

| Anti-pattern | Consequence | Solution |
| --- | --- | --- |
| Treating `JobInstanceAlreadyCompleteException` as a bug to "fix with run.id" | Duplicate execution of business period | Distinguish duplicate triggers from reprocess requests |
| Adding an identifying timestamp on every launch | Every trigger creates a new instance | Use a deterministic business key; tracing timestamps are non-identifying |
| Changing non-identifying parameters and assuming a new instance was created | Still rejected | Understand the identifying flag clearly |
| Thinking `allowStartIfComplete(true)` lets a completed Job restart | Error still occurs | Distinguish step policy from job policy |
| Removing `preventRestart()` to re-run a COMPLETED Job | Does not solve the completed case | Use intentional reprocess/new instance by design |
| Deleting `BATCH_*` tables to bypass the error | Loss of history and state, duplicate risk | Keep the repository; manage revisions/reprocessing |
| Using `startNextInstance` when you actually want to restart FAILED | Creates a new instance | Keep identifying parameters for restart |
| Not checking status before firing auto-triggers | Useless error logs, retry loops | Query metadata and classify outcomes |
| Ignoring impact on the target database | Reports/money doubled | Upsert/versioning/outbox/idempotency |
| Not recording the reprocess reason | Hard to audit why the same period has multiple versions | Audit revision, source hash, approver |
| Reprocessing on changed source without versioning | Cannot reproduce results | Source snapshot and checksum |
| Only testing whether JobLauncher runs without throwing | Fails to catch double-writes | Assert target data and business invariants |
| Confusing `ExitStatus` with `BatchStatus` | Wrong conclusion about restartability | Inspect both statuses |
| Using JobExecution ID as deduplication key | Restart gets a new ID, causing duplicate effects | Use a durable business key |
| Handling `UNKNOWN_ERROR` by immediately creating a new instance | May double-process an already created execution | Reconcile with JobRepository before retrying |

## 23. Practice Exercises

Build a `dailyRevenueJob` with two steps:

1. `loadTransactionsStep` reads transactions for a `businessDate`.
2. `writeRevenueStep` saves total revenue by `businessDate` and `merchantId`.

Requirements:

- **Case A:** run date D the first time to `COMPLETED`; resubmit the same identifying parameters, verify it is rejected and the writer writes nothing further.
- **Case B:** add a non-identifying `requestId` and call again; explain why it is still rejected.
- **Case C:** simulate a failure on the first run so the job becomes `FAILED`; re-launch with the same identifying parameters and verify a new JobExecution is created under the same JobInstance.
- **Case D:** add identifying `revision=2` for a justified reprocess request; verify a different JobInstance is created, yet target data is not duplicated.
- **Case E:** first step `COMPLETED`, second step `FAILED`; restart and check whether the first step runs again. Try adding `allowStartIfComplete(true)` to observe the difference.
- **Case F:** perform a reprocess when the source changes; record the source checksum and approval workflow before publishing.
- **Case G:** run the scheduler twice for the same day and identify which logs/monitoring reflect the duplicate trigger and the final execution.

In your results table, record job name, identifying parameters, JobInstance ID, JobExecution ID, BatchStatus, ExitStatus, and target record count before/after each attempt.

Explain which case is a **true restart**, which is a **new instance**, which must **ignore the duplicate**, and which requires an **audited reprocess**.

## 24. Summary

**You cannot restart a `COMPLETED` JobInstance by re-invoking with the same identifying JobParameters.** Spring Batch intentionally rejects it via `JobInstanceAlreadyCompleteException` to protect data and processing history.

Restart is strictly for an instance that has not yet completed successfully and remains eligible for recovery. When completed results need to be reprocessed, treat it as a **business reprocess**, intentionally create a new identity/revision, and protect target data with transactions, versioning, or idempotency. Do not increment `run.id` arbitrarily, delete metadata, or enable `allowStartIfComplete(true)` expecting to override JobInstance rules.

Understanding the distinction between **JobInstance**, **JobExecution**, **restart**, **new instance**, and **reprocess** enables safe error handling, preserves auditability, and prevents duplicate runs that can corrupt data.

# Using the Current Time to Always Create a New JobInstance — A Common Pitfall in Spring Batch

## 1. Problem: "Adding a Timestamp to Re-run a Job" Can Break Restart

A very common snippet when first getting started with Spring Batch:

```java
JobParameters parameters = new JobParametersBuilder()
    .addLong("runAt", System.currentTimeMillis())
    .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

The author wants to avoid the "job already completed" or "job instance already exists" error when running the same job multiple times. Each invocation takes the current time and attaches it to the parameters so Spring Batch treats it as a different run.

This approach may satisfy the **requirement of creating an independent run** in a demo, but it is a **serious design flaw** if used habitually for all batch jobs. Spring Batch can no longer recognize that two runs are processing **the same business work**. A failed execution can be abandoned; the next run starts as a brand-new job without reading the old checkpoint, potentially loading duplicates or emitting repeated side effects.

Example of an invoice import job on 2026-11-16:

```text
Run 1:
  jobName    = invoiceImportJob
  businessDate = 2026-11-16
  runAt      = 1794800000000  [identifying]
  JobInstance #100
  JobExecution #200 -> FAILED after 60,000/100,000 records

Run 2:
  jobName    = invoiceImportJob
  businessDate = 2026-11-16
  runAt      = 1794800100000  [identifying, different value]
  JobInstance #101
  JobExecution #201 -> starts over from the beginning

Desired:
  Restart JobInstance #100 with a new JobExecution
  and restore the checkpoint of the incomplete step.
```

The timestamps above are illustrative values only. The core issue does not lie in the numbers, but in the fact that each invocation uses a **different identifying parameter**.

> **Rule to remember:** A re-run after a failure should usually create a **new `JobExecution` of the same `JobInstance`**, not create a new `JobInstance` by changing a timestamp. The current time should only become part of the identity when the business domain truly defines each trigger as an independent unit of work.

This lesson belongs to the **Common Pitfalls** chapter of the **Spring Batch Core Processing** module. Examples are based on Java 17+, Spring Boot 3.x, and Spring Batch 5.x. When using Spring Batch 6.x, check API changes, but the principles of identity and restart must still be preserved.

### Learning Outcomes

After this lesson, you will be able to:

- Explain how Spring Batch identifies a `JobInstance` from `jobName` and identifying `JobParameters`.
- Recognize why `System.currentTimeMillis()`, `Instant.now()`, or an identifying UUID "bypass restart".
- Distinguish between a new period run, a restart after failure, an intentional reprocess, a rerun, and a backfill.
- Design identifying parameters based on a **business key/nominal schedule slot** rather than the time the request arrives at the server.
- Use `JobLauncher`, `JobOperator`, `JobExplorer`, and metadata to make safe decisions.
- Test identity stability, restart checkpoints, concurrency, idempotency, and business outcomes.
- Plan how to fix an existing job that misused timestamps without losing processing history.

---

## 2. Three Foundational Concepts: `Job`, `JobInstance`, and `JobExecution`

### 2.1. `Job` Is the Work Definition

A `Job` describes the processing flow: steps, state transition order, and restart configuration. For example:

```text
invoiceImportJob
   |
   +-- validateInputStep
   |
   +-- importInvoiceStep
   |
   +-- reconcileTotalsStep
```

A `Job` is not synonymous with a specific run.

### 2.2. `JobInstance` Is a Logical Unit of Work

Spring Batch uses the **job name** plus the set of **identifying job parameters** to identify a `JobInstance`.

For example:

```text
jobName = invoiceImportJob

Identifying parameters:
  tenantId     = merchant-42
  businessDate = 2026-11-16

=> one JobInstance for that business date of that tenant
```

Two launches with the same job name and the same identifying values usually refer to the **same `JobInstance`**. The framework must inspect the instance's state to decide whether to create a new execution or reject the request.

A `JobInstance` is not merely a timestamp or how many times you clicked the Run button. It is a **logical unit of business work that needs to be completed**.

### 2.3. `JobExecution` Is a Single Execution Attempt of an Instance

An instance can have multiple executions when the job fails and is later restarted:

```text
JobInstance #100
  invoiceImportJob(tenantId=merchant-42, businessDate=2026-11-16)
       |
       +-- JobExecution #200: FAILED
       |       validateInputStep: COMPLETED
       |       importInvoiceStep:  FAILED
       |
       +-- JobExecution #202: COMPLETED (restart)
               validateInputStep: typically skipped
               importInvoiceStep:  resumes from checkpoint
               reconcileTotalsStep: COMPLETED
```

A job designed properly for restart can resume work from persisted metadata. If you change an identifying parameter, Spring Batch treats it as a different instance and will not automatically apply checkpoints belonging to instance #100.

### 2.4. The Relationship Expressed as a Formula

Written concisely:

\[
\operatorname{JobInstanceIdentity}
=
(\operatorname{jobName},
\operatorname{identifyingJobParameters})
\]

Pay attention to **the name, value, data type, and identifying flag** of parameters. Do not just compare a string map that "looks similar".

For example, `businessDate` as a `String` versus a `LocalDate` across compatible representations/versions should not be assumed to produce the same identity. In practice, choose one stable representation and one consistent convention across the entire system.

---

## 3. `JobParameters` Have Two Groups: Identifying and Non-Identifying

### 3.1. Identifying by Default

In Spring Batch 5.x, the common overloads of `JobParametersBuilder.addString`, `addLong`, and `addDate` when no identifying flag is passed typically default to **identifying=true**.

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("tenantId", "merchant-42")
    .addLong("runAt", System.currentTimeMillis())
    .toJobParameters();
```

Here, **all three** parameters are treated as identifying according to the default behavior of these overloads. When `runAt` changes, the logical identity changes, even though `businessDate` and `tenantId` stay the same.

### 3.2. Non-Identifying Is Auxiliary Metadata

You can mark a parameter so it does not participate in identity:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("tenantId", "merchant-42", true)
    .addLong("requestedAtEpochMs",
        System.currentTimeMillis(), false)
    .toJobParameters();
```

In that case, `requestedAtEpochMs` is only supplementary information and does not change the `JobInstance`.

However, two important limitations must be understood:

1. **A non-identifying timestamp does not make a `COMPLETED` instance runnable again.** If the same instance has already completed, Spring Batch may throw `JobInstanceAlreadyCompleteException`.
2. **A non-identifying timestamp does not replace request/execution auditing.** If you want to record when a user clicked the button, which request ID it was, or who approved it, it is better to have a dedicated audit log/event because multiple requests can point to the same instance and some requests may be rejected before creating an execution.

### 3.3. Which Parameters Should Be Identifying?

A simple rule of thumb: **If two requests differ on this parameter, must they complete two independent units of business work?**

| Parameter | Usually identifying? | Explanation |
| --- | --- | --- |
| `businessDate` | Yes | Two different processing periods |
| `tenantId` | Yes, if the job runs per tenant | Prevents mixing data across tenants |
| `sourceFileId` | Yes, if each file is an independent import | A specific file should only have one logical ingestion |
| `feedVersion` | Yes, if a version is a distinct unit of work | Depends on the contract |
| `scheduledSlot` | Yes, when each nominal slot is a unit of work | Backfill and duplicate dispatch for the same slot |
| `requestedAt` | Usually no | Request submission time is not necessarily identity |
| `traceId` / `correlationId` | Usually no | Used for tracing |
| `operatorName` | No | The operator triggering a restart does not create new business work |
| `retryAttempt` | No | Retries must belong to the same instance |
| `run.id` | Only when intentionally creating a new instance | Do not use to mask restart failures |
| `runUuid` | Only when each request is truly new work | Unsuitable for reprocessing the same input |

Whether a parameter is identifying is a **domain decision**, not merely a trick to evade exceptions.

---

## 4. Why Does a Timestamp Turn a Restart into a New Job?

### 4.1. Behavior of the Faulty Code

```java
public void runImport() throws Exception {
    JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addLong("timestamp", System.currentTimeMillis(), true)
        .toJobParameters();

    jobLauncher.run(importJob, params);
}
```

Suppose the first execution fails after two chunks have been committed and their corresponding checkpoints saved. On the next invocation, `timestamp` is different:

```text
Run 1:
  timestamp=T1 -> JobInstance A -> FAILED
  metadata saves A's ExecutionContext

Run 2:
  timestamp=T2 -> JobInstance B -> STARTED
  B has no step/checkpoint history from A
  reader may start from the first item
```

Spring Batch has no mechanism to guess that A and B should be one just because they share the same business date. To the framework, two different sets of identifying parameters mean two different logical jobs.

### 4.2. Impact on Checkpoints

For example, a step importing 100,000 transactions with chunk size 1,000:

```text
JobInstance A:
  chunk 1..60 COMMITTED       60,000 transactions
  chunk 61 FAILED
  last persisted checkpoint 60,000

New run using timestamp T2:
  JobInstance B:
  reader.open(new context)
  starts from record 1
```

The consequences depend on the writer:

- Writer performs `INSERT` without a unique constraint: may create **60,000 duplicate records**.
- Writer has a unique constraint but is not idempotent: the new job may immediately become `FAILED` due to a duplicate key.
- Writer uses upsert: data may not duplicate, but resources are wasted and audits/triggers/events may fire again.
- Writer sends emails or external payments: side effects may repeat and be hard or impossible to roll back.
- Writer uses an append-only file: may output a duplicate file or re-append already written rows.

**There is no default mechanism in Spring Batch that guarantees "each record appears only once" when you force creating a new instance to reprocess the same data.**

### 4.3. Operational Impact

Using an identifying timestamp on every Run click also causes:

- Dashboards cluttered with dozens of `JobInstance FAILED` entries instead of a single instance with a clear restart progression.
- Operators unable to tell which execution is the authoritative run and which was an accidental re-run.
- A retry scheduler that can spawn multiple logical instances for the same business date.
- Difficulty computing SLAs such as "has day N finished processing?" from metadata.
- Multiple concurrent executions of **different instances** still able to write to the same data.
- More complex metadata cleanup and business reconciliation.
- Business reconciliation struggling to distinguish valid records from re-written records.

### 4.4. Timestamps Are Not Even Guaranteed to Be Unique

The lesson title "always create a new `JobInstance`" describes the anti-pattern's intent, but `System.currentTimeMillis()` only has millisecond resolution and the system clock can be adjusted. Two calls within the same millisecond or across nodes with unsynchronized clocks **can produce the same value**.

Therefore, a timestamp is not only wrong in domain semantics, it also **does not guarantee absolute uniqueness**. Switching to a UUID reduces collisions but still does not fix the root flaw: creating a new instance for the same work.

---

## 5. States and Outcomes When Running with the Same Parameters

In Spring Batch, the result of `jobLauncher.run(job, parameters)` depends on the existing `JobInstance` state:

| Instance/execution state | Request with same identifying params | How to handle |
| --- | --- | --- |
| Does not exist yet | Creates the instance and first execution | Valid initial launch |
| Has `FAILED` execution, job is restartable | Can create a new execution for the same instance | Restart after resolving root cause |
| Has `STOPPED` execution, job is restartable | Can be restarted per configuration | Check stop reason/checkpoint |
| Already has `COMPLETED` execution | Usually rejected with `JobInstanceAlreadyCompleteException` | If a new run is needed, choose a **meaningful** new identity |
| Currently `STARTING`/`STARTED` | Does not create a second execution of the same instance | Monitor the active execution |
| Job configured with `preventRestart()` | Cannot restart an already executed instance | Review business rules/policy |
| Old execution in inconsistent state | Do not force-launch | Investigate metadata/actual process |

Some common exceptions:

- `JobExecutionAlreadyRunningException`: the instance already has a running execution.
- `JobInstanceAlreadyCompleteException`: the instance has already completed.
- `JobRestartException`: cannot restart given the current state/job definition.
- `JobParametersInvalidException`: parameters failed the validator.

**These exceptions are usually signals about the correctness of job identity and lifecycle**, not a reason to add a timestamp to work around them.

---

## 6. Distinguishing Four Business Actions

### 6.1. Initial Launch

A job needs to process a new period, such as data for the 17th, while the 16th has already completed.

```text
invoiceImportJob(tenant=merchant-42, businessDate=2026-11-16)
  => JobInstance #100 COMPLETED

invoiceImportJob(tenant=merchant-42, businessDate=2026-11-17)
  => JobInstance #101 (new)
```

Here, a new instance is right because of the **new businessDate**.

### 6.2. Restart After Failure

Same businessDate, same tenant, job not yet completed:

```text
JobInstance #100
   JobExecution #200 FAILED
   JobExecution #201 COMPLETED (after restart)
```

The requirement is to continue the existing work, not to arbitrarily change identity. You can use `JobOperator.restart(failedExecutionId)` in Spring Batch 5.x when the operator and job registry are properly configured.

### 6.3. Rerunning a Completed Period

This requirement is **different from restart**: after the report for the 16th is `COMPLETED`, the business wants to recalculate it because the source was corrected.

You must decide clearly:

- Should a new **report revision** be created?
- Should the old version be replaced atomically?
- Should old result history be kept for audit?
- Could events or payments be re-emitted?
- What is the business key of the revision?

One approach is to use an identifying `revision` or `reprocessRequestId` **managed by the business domain**, rather than taking the current timestamp unconditionally. For example, `businessDate=2026-11-16, revision=2` means an approved recalculation. The writer must write results by version and avoid mixing results.

### 6.4. Backfilling Missed Schedules

The scheduler was down from the 11th to the 13th. If each day requires a separate report, create/recover instances by nominal business date:

```text
businessDate=2026-11-11 -> JobInstance for the 11th
businessDate=2026-11-12 -> JobInstance for the 12th
businessDate=2026-11-13 -> JobInstance for the 13th
```

Do not use **the system recovery time** as the identity for all three slots; if all three run at 09:00 on the 13th, they must still process periods 11, 12, and 13 accurately.

---

## 7. The Simple Fix: Define Identity Using a Business Key

### 7.1. Example: Import by Date and Tenant

Replace the faulty snippet:

```java
// Anti-pattern: every call creates a new identity unrelated to business logic.
JobParameters params = new JobParametersBuilder()
    .addString("tenantId", tenantId)
    .addString("businessDate", businessDate.toString())
    .addLong("runAt", System.currentTimeMillis())
    .toJobParameters();
```

with one whose meaning is explicit:

```java
JobParameters params = new JobParametersBuilder()
    .addString("tenantId", tenantId, true)
    .addString("businessDate", businessDate.toString(), true)
    .toJobParameters();
```

If tracing information is needed for the request:

```java
JobParameters params = new JobParametersBuilder()
    .addString("tenantId", tenantId, true)
    .addString("businessDate", businessDate.toString(), true)
    .addString("correlationId", correlationId, false)
    .toJobParameters();
```

The same tenant + businessDate point to the same `JobInstance`; changing `correlationId` does not make it a different instance.

### 7.2. Example: Importing a Specific File

If the input is a file with a stable ID:

```java
JobParameters params = new JobParametersBuilder()
    .addString("feedName", "orders-feed", true)
    .addString("sourceFileId", fileId, true)
    .addString("fileChecksum", checksum, false)
    .toJobParameters();
```

However, the role of `fileChecksum` must be decided:

- If the same `fileId` with changed content means **different** work that needs re-importing, the checksum/version may need to participate in identity.
- If the same file ID is only allowed to be imported once and the checksum only verifies immutability, the checksum can be non-identifying, but the job must **reject** when different content is detected instead of silently processing it as the old file.
- If the file path changes depending on storage location while the content/business ID stays the same, the path is usually not a good identity.

The essence is having a clear contract about *what counts as the same source*.

### 7.3. Example: Syncing by Time Window

For a job processing events within explicit open/close bounds:

```java
JobParameters params = new JobParametersBuilder()
    .addString("windowStartUtc",
        windowStart.toString(), true)
    .addString("windowEndUtc",
        windowEnd.toString(), true)
    .addString("streamName", streamName, true)
    .toJobParameters();
```

`windowStart` and `windowEnd` should be derived from a **nominal** schedule or a durable watermark, not by calling `Instant.now()` each time a request reaches the server and inventing a new window.

---

## 8. A Launch Service with an Explicit Policy

An administrative API typically receives `businessDate` and `tenantId`. The following service explicitly derives instance identity from the domain:

```java
package example.batch.launch;

import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.stereotype.Service;

@Service
public class InvoiceImportLaunchService {

    private final JobLauncher jobLauncher;
    private final Job invoiceImportJob;

    public InvoiceImportLaunchService(
            JobLauncher jobLauncher,
            Job invoiceImportJob) {
        this.jobLauncher = jobLauncher;
        this.invoiceImportJob = invoiceImportJob;
    }

    public JobExecution launch(
            String tenantId,
            LocalDate businessDate) throws Exception {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                "tenantId is required");
        }
        if (businessDate == null) {
            throw new IllegalArgumentException(
                "businessDate is required");
        }

        JobParameters parameters = new JobParametersBuilder()
            .addString("tenantId", tenantId, true)
            .addString("businessDate",
                businessDate.toString(), true)
            .toJobParameters();

        return jobLauncher.run(invoiceImportJob, parameters);
    }
}
```

The service does not force every call to succeed by generating a new ID. If a request is re-sent and the instance is already `COMPLETED`, the exception is a meaningful operational outcome; the API layer can map it to a "this period has already been processed" response or return the status of the existing execution after verification.

**Do not swallow the exception and re-run with a timestamp**:

```java
// Wrong: bypassing lifecycle policy on error.
try {
    jobLauncher.run(job, businessParams);
} catch (JobInstanceAlreadyCompleteException ex) {
    // Do not change runAt just to 'retry'.
}
```

If the user genuinely requests rerunning a completed period, create a separate **reprocess workflow** with authorization, auditing, and version/target semantics.

---

## 9. Restarting Properly with `JobOperator`

### 9.1. Use the Failed Execution ID Instead of "Running New"

In Spring Batch 5.x:

```java
import org.springframework.batch.core.launch.JobOperator;

Long newExecutionId =
    jobOperator.restart(failedExecutionId);
```

- `failedExecutionId` is the **ID of the previous `JobExecution`**, not the `JobInstance ID`.
- `restart` uses metadata to look up the job definition and old parameters.
- The framework creates a new `JobExecution` attached to the **same `JobInstance`**.
- Steps that were previously `COMPLETED` are normally skipped, unless configured otherwise such as `allowStartIfComplete(true)`.
- Incomplete steps can use the persisted `ExecutionContext` to restore reader/writer state.

### 9.2. Example Restart Service with Precheck

```java
package example.batch.launch;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class InvoiceRestartService {

    private final JobExplorer explorer;
    private final JobOperator operator;

    public InvoiceRestartService(
            JobExplorer explorer,
            JobOperator operator) {
        this.explorer = explorer;
        this.operator = operator;
    }

    public long restartFailed(long oldExecutionId)
            throws Exception {

        JobExecution previous =
            explorer.getJobExecution(oldExecutionId);

        if (previous == null) {
            throw new IllegalArgumentException(
                "Unknown execution: " + oldExecutionId);
        }

        if (previous.getStatus() != BatchStatus.FAILED
                && previous.getStatus() != BatchStatus.STOPPED) {
            throw new IllegalStateException(
                "Cannot restart execution in state "
                    + previous.getStatus());
        }

        // Check permissions, DB health, side effects, job definition,
        // and concurrency at the business layer before operating.
        return operator.restart(oldExecutionId);
    }
}
```

A precheck is not a race-condition lock: between reading the status and calling restart, another node may have launched the same instance. `JobRepository`/`JobOperator` will enforce conditions at operation time; the API layer must handle "already running/already completed" messages clearly.

### 9.3. Do Not Assume the Restart Call Has Already Finished

`JobOperator.restart(...)` returns the new execution ID. With an asynchronous launcher, the execution may still be `STARTING` or `STARTED`. Monitor it via `JobExplorer` or your monitoring system until a terminal state, then verify the business outcome.

```text
restart(#200) -> newExecutionId=#202
                       |
                       v
             JobExplorer.getJobExecution(202)
                       |
              +--------+--------+
              |                 |
         STARTED             COMPLETED
              |                 |
      keep monitoring       verify output
```

If the new execution becomes `FAILED` again, investigate the new cause; do not create a new `JobInstance` with a timestamp to avoid the old failed instance.

---

## 10. Metadata and What Spring Batch Actually Compares

With a JDBC `JobRepository`, some key tables include:

| Table | Information |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Instance ID, job name, key representing identifying parameters |
| `BATCH_JOB_EXECUTION` | Executions of each instance, statuses, timestamps |
| `BATCH_JOB_EXECUTION_PARAMS` | Parameter name/type/value and identifying flag per schema version |
| `BATCH_STEP_EXECUTION` | Step status, counts, commits, rollbacks |
| `BATCH_STEP_EXECUTION_CONTEXT` | Step state/checkpoint for restart |
| `BATCH_JOB_EXECUTION_CONTEXT` | Job-level context |

### 10.1. `JOB_KEY` Is Not a Request ID

`BATCH_JOB_INSTANCE.JOB_KEY` is a value generated by the repository from identifying parameters using the framework's mechanism. Do not treat `JOB_KEY` as a human-readable business key or manually edit the hash to "merge" instances created by timestamps.

If two executions have different identifying timestamps, they can belong to two different `BATCH_JOB_INSTANCE` rows, even when the business date is identical.

### 10.2. How to Inspect Abnormal Instances

A simple diagnostic query, without yet depending on the parameter schema, can be:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'invoiceImportJob'
ORDER BY ji.JOB_INSTANCE_ID, je.JOB_EXECUTION_ID;
```

If you see numerous separate instances for executions of the same business date, cross-check the parameters in `BATCH_JOB_EXECUTION_PARAMS`.

In **Spring Batch 5.x**, the standard schema includes the columns `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE`, and `IDENTIFYING`:

```sql
SELECT
    p.JOB_EXECUTION_ID,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS p
WHERE p.JOB_EXECUTION_ID IN (200, 201, 202)
ORDER BY p.JOB_EXECUTION_ID, p.PARAMETER_NAME;
```

The metadata schema differs across major versions; do not apply this SQL verbatim if the project has customized the schema or still uses Spring Batch 4.x.

### 10.3. JobInstance Identity Is the Repository's Responsibility

Do not attempt to edit `BATCH_JOB_INSTANCE` or `BATCH_JOB_EXECUTION_PARAMS` directly to "merge" different instances. Metadata tables have relationships, versioning, and associated execution contexts. If historical data migration is required, design it under a controlled plan with backups, auditing, and reconciliation, not ad hoc SQL hash edits.

---

## 11. Anti-Pattern Signs in the Codebase

When reviewing Java code or operational docs, the following patterns should be examined closely:

```java
// Every request creates a new identifying timestamp:
new JobParametersBuilder()
    .addLong("time", System.currentTimeMillis())
    .toJobParameters();
```

```java
// Every request creates a new identifying UUID:
new JobParametersBuilder()
    .addString("requestId", UUID.randomUUID().toString())
    .toJobParameters();
```

```java
// Changing run.id to bypass a job being COMPLETED or FAILED:
new JobParametersBuilder()
    .addLong("run.id", nextSequence())
    .toJobParameters();
```

```java
// Catching a lifecycle error and forcing another instance:
try {
    return jobLauncher.run(job, stableParams);
} catch (JobInstanceAlreadyCompleteException ex) {
    return jobLauncher.run(job, withTimestamp(stableParams));
}
```

```java
// Scheduler using actual start time as period identity:
@Scheduled(cron = "0 0 2 * * *")
public void scheduled() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
        .addString("period", Instant.now().toString())
        .toJobParameters();
    jobLauncher.run(reportJob, parameters);
}
```

Not every line is automatically wrong. **It is wrong when the new value does not represent new work**. For a state-snapshot task where "each request is an independent snapshot" and the writer records meaningful versions, a unique ID can be valid. Even then, use a managed `snapshotRequestId` or request domain ID rather than grabbing the current time just to make the framework accept it.

---

## 12. Is `RunIdIncrementer` the Solution?

Spring Batch provides `RunIdIncrementer`, which can be used to supply an incrementing `run.id` parameter when intentionally starting a new instance:

```java
@Bean
Job reportJob(
        JobRepository jobRepository,
        Step reportStep) {

    return new JobBuilder("reportJob", jobRepository)
        .start(reportStep)
        .incrementer(new RunIdIncrementer())
        .build();
}
```

Distinguish carefully:

- `RunIdIncrementer` helps compute the **parameters of the next instance**; it does not automatically "fix unrestartable failures".
- `JobOperator.startNextInstance(jobName)`, when configured, is an operation that **intentionally starts the next instance** using the job incrementer.
- If the business requires each run to be a completely new batch, this approach can make sense.
- If the business needs to **resume a FAILED instance**, use restart, not an incrementer.
- If the same business date must not produce two independent reports, a new `run.id` is not sufficient to define correctness.

### 12.1. Comparison Table

| Goal | API / technique | Identity |
| --- | --- | --- |
| Run a period for the first time | `JobLauncher.run(job, params)` | Period's business key |
| Retry/restart a failed period | `JobOperator.restart(executionId)` or launch with same identifying params per contract | **Keep unchanged** |
| Run the next period | New businessDate/window/fileId; incrementer may be used when appropriate | **Intentionally new** |
| Rerun a completed period | Separate revision/reprocess flow with explicit business ID | New by version/revision |
| Investigate failure | `JobExplorer`, metadata, step failure | Unchanged |
| Log trigger timestamp | Audit event / non-identifying metadata | No need to change identity |

An operational script saying "if already completed, keep incrementing run.id until launch succeeds" is a sign the workflow lacks a business decision.

---

## 13. Scheduler: Use Nominal Slots Instead of `Instant.now()`

### 13.1. The Problem with Actual Launch Time

Suppose a report runs daily at 02:00, but the node restarts at 09:00. If the scheduler receives a recovery trigger and passes `Instant.now()` as an identifying parameter, the run will have an identity of 09:00 and cannot tell which day it represents.

Especially when the scheduler retries the same trigger:

```text
02:00:00 slot S
02:00:05 attempt A -> timeout
02:00:06 attempt B -> identifying runAt changes
02:00:07 attempt C -> identifying runAt changes

Three potential JobInstances for the same slot S.
```

Instead, you need a **nominal scheduled slot** independent of when the request is actually sent.

### 13.2. Mapping a Slot to JobParameters

```java
public JobParameters paramsForSlot(
        String tenantId,
        Instant scheduledAt,
        LocalDate businessDate) {

    return new JobParametersBuilder()
        .addString("tenantId", tenantId, true)
        .addLong("scheduledAtEpochMs",
            scheduledAt.toEpochMilli(), true)
        .addString("businessDate",
            businessDate.toString(), false)
        .toJobParameters();
}
```

This example assumes `tenantId + scheduledAt` is the stable key for a scheduled slot. `businessDate` can be marked identifying if it is a critical part of identity; the decision must stay consistent with how the job is scheduled. Do not build a complete identifier from a nominal slot and then still append the actual start time.

### 13.3. When Using `@Scheduled`

`@Scheduled` normally only invokes a method at the callback time and does not provide a persistent "list of all nominal slots missed during downtime". To reliably cover every period, it is better to separate:

```text
@Scheduled tick
      |
      v
Schedule reconciler
      |
      v
Find PENDING / FAILED slots in ledger
      |
      v
Launch with stable slot key, or restart existing execution
```

Illustrative sketch:

```java
@Scheduled(fixedDelayString = "PT1M")
public void reconcileDueReports() {
    // Read schedule from persisted expected slots table.
    // For each due slot: claim exclusively.
    // Query JobRepository to launch/restart/reconcile.
    scheduleReconciler.runDueSlots();
}
```

This is an illustrative architecture; `scheduleReconciler` is an application-written business service. Do not infer all missed slots during downtime solely from `LocalDate.now()` inside the callback.

### 13.4. Quartz and Misfires

Quartz has misfire policies such as `DoNothing`, `FireAndProceed`, and `IgnoreMisfires`, but these policies do not by themselves guarantee that every past business date has a completed Batch job.

A Quartz adapter can use the current trigger's `scheduledFireTime` to build parameters, yet when a misfire is adjusted (especially `FireAndProceed`), you should not assume that timestamp represents the complete list of missed slots. For backfills, use a **slot ledger** and a predefined business calendar.

---

## 14. Stable Identity Still Needs Race Condition Protection

Switching from an identifying timestamp to a fixed `businessDate` is the right step, but it does not solve every concurrency scenario.

For example, two requests:

```text
Node A: launch(tenant=A, businessDate=2026-11-16)
Node B: launch(tenant=A, businessDate=2026-11-16)
```

When sharing a JDBC `JobRepository` and using the same identifying params, the framework has mechanisms to manage instance/execution creation and check state. One request may be accepted while the other is rejected because the instance is already running or completed. That is better than two parallel instances, but the API layer must still handle the race and return a clear response.

### 14.1. Detecting Duplicate Requests at the Business Layer

One possible model:

```sql
CREATE TABLE batch_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    business_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL,
    job_execution_id BIGINT,
    CONSTRAINT uq_batch_request
        UNIQUE (job_name, tenant_id, business_date)
);
```

This table is a **business request ledger**, not built-in Spring Batch metadata. The unique constraint prevents two nodes from claiming two independent business requests for the same period.

Suggested workflow:

1. Receive a request with a business key.
2. Insert-if-absent or atomically claim the existing row.
3. Query `JobExplorer`/`JobRepository` to see which instance is running/completed/failed.
4. Perform the initial launch or restart the old instance depending on its state.
5. Update the ledger and reconciler to handle crashes between steps.
6. Return the instance/execution ID instead of inventing a new timestamp.

### 14.2. `JobRepository` Protects Identity, Not Every Side Effect

Two `JobInstance`s with different business keys that read/write the same physical resource can still contend with each other. For example, importing file A and file B that contain the same external order ID. You still need unique constraints, partition ownership, idempotent writers, and transaction discipline alongside Spring Batch metadata.

### 14.3. When a Request Times Out Without Knowing Whether It Launched

A client sends a launch request but times out before receiving the `JobExecution ID`:

```text
Client -------- request --------> Server
Client <------- timeout ---------x
                              Did the server create an execution?
```

Do not generate a new identifying timestamp and resend. Query by the stable business key to identify any existing job instance/execution. If an execution is running, continue monitoring; if completed, return the result; if failed, recover according to the runbook.

---

## 15. Checkpoints and `ExecutionContext`: Why Does Restarting the Same Instance Work?

In chunk-oriented processing, readers/writers can implement `ItemStream` to save/restore state. For example, a file reader keeping the line position:

```text
JobInstance A
  StepExecution 1:
    open(context offset=0)
    chunk 1 commit -> offset=100
    chunk 2 commit -> offset=200
    chunk 3 fails, rollback
  Repository checkpoint: offset=200

JobInstance A, StepExecution 2 (restart):
    open(context offset=200)
    continues processing the uncommitted portion

JobInstance B, new timestamp:
    open(new context, offset=0)
    processes everything from the beginning
```

In a step with item filtering, retries, skips, or paging, checkpoints can be more complex than an offset number. Yet the principle holds: **restart relies on the step/execution state of the old instance**, not on the job name being the same or the input data looking similar.

### 15.1. `allowStartIfComplete` Does Not Fix the New-Instance Mistake

A step can be configured as:

```java
Step step = new StepBuilder("validateStep", jobRepository)
    .tasklet(validateTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
```

This setting allows a step to run again **during a restart of the same instance** even if it previously completed. It does not force Spring Batch to treat two instances with different timestamps as one. Do not use it as a substitute for proper identifying parameter design.

### 15.2. `preventRestart` and `startLimit`

`preventRestart()` on a job can forbid restarts. `startLimit` on a step limits how many times the step can start within the same instance. If you always create a new instance using a timestamp, restart limits **tied to the old instance** can be bypassed. This is dangerous when those limits are in place to guard side effects, costs, or once-only business operations.

### 15.3. Why Resetting `ExecutionContext` Is Not the Solution

If a checkpoint is no longer valid because the reader implementation or source data changed, do not create a new instance just to ignore the error. Evaluate checkpoint migration, a reprocess policy, or running a versioned remediation. A "quick fix" with a timestamp only hides the mismatch between data and metadata.

---

## 16. Designing Idempotent Writers for Reruns and Retries

Even when restarting the right `JobInstance`, some chunks may be reprocessed if the commit outcome was unclear or the metadata checkpoint was not yet persisted. Therefore, the writer must have a contract for duplicate items.

### 16.1. Business Keys in the Database

For example:

```sql
CREATE TABLE imported_invoices (
    tenant_id VARCHAR(100) NOT NULL,
    external_invoice_id VARCHAR(120) NOT NULL,
    business_date DATE NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    CONSTRAINT uq_imported_invoice
        UNIQUE (tenant_id, external_invoice_id)
);
```

The unique key enforces that an invoice appears only once under the example contract. With real data, you may also need a version or `businessDate` if external IDs are reused; the key must reflect the domain.

### 16.2. UPSERT Is Not a Silver Bullet

A PostgreSQL writer might use:

```sql
INSERT INTO imported_invoices (
    tenant_id,
    external_invoice_id,
    business_date,
    amount
)
VALUES (?, ?, ?, ?)
ON CONFLICT (tenant_id, external_invoice_id)
DO UPDATE SET
    amount = EXCLUDED.amount,
    business_date = EXCLUDED.business_date;
```

This approach can be idempotent regarding row state if the input has not changed. However, repeated UPDATEs can fire triggers/events, insert new audit rows, or overwrite legitimately amended versions of data. For financials, an append-only ledger or write-once + correction events may be required instead of arbitrary upserts.

### 16.3. Side Effects Outside the Transaction

Sending emails, payment requests, or Kafka events from a processor/writer can happen before the checkpoint commits. Using a new identifying timestamp does not solve duplicate side effects; on the contrary, it increases the likelihood of replaying everything.

Appropriate techniques:

- Idempotency keys per business operation.
- Transactional outbox when appropriate.
- Consumer deduplication.
- Unique constraints and reconciliation.
- Verifying external delivery/payment state before rerunning.

### 16.4. Correctness Must Be Verified Against Business Output

A `COMPLETED` job does not prove there are no duplicates if it reprocessed everything. Check:

- Count of unique invoices/orders by business key.
- Total amount/checksum for the period.
- Only one published report version if required by the contract.
- No duplicate events/payment requests.
- No orphaned failed instances left unreconciled.

---

## 17. Unit Testing to Verify JobParameters Identity

You do not need to boot a Spring context to test a service that builds parameters.

### 17.1. Pure Factory

```java
package example.batch.launch;

import java.time.LocalDate;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

public final class InvoiceJobParametersFactory {

    public JobParameters create(
            String tenantId,
            LocalDate businessDate,
            String correlationId) {

        return new JobParametersBuilder()
            .addString("tenantId", tenantId, true)
            .addString("businessDate",
                businessDate.toString(), true)
            .addString("correlationId", correlationId, false)
            .toJobParameters();
    }
}
```

### 17.2. Testing Same Business Key, Different Correlation ID

```java
import java.time.LocalDate;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameter;
import org.springframework.batch.core.JobParameters;

import static org.junit.jupiter.api.Assertions.*;

class InvoiceJobParametersFactoryTest {

    private final InvoiceJobParametersFactory factory =
        new InvoiceJobParametersFactory();

    @Test
    void identifyingValuesStayStableAcrossRequests() {

        LocalDate date = LocalDate.of(2026, 11, 16);

        JobParameters first =
            factory.create("merchant-42", date, "trace-A");
        JobParameters second =
            factory.create("merchant-42", date, "trace-B");

        Map<String, JobParameter<?>> a =
            first.getIdentifyingParameters();
        Map<String, JobParameter<?>> b =
            second.getIdentifyingParameters();

        assertEquals(a, b);
        assertEquals(2, a.size());
        assertFalse(a.containsKey("correlationId"));
    }

    @Test
    void aDifferentBusinessDateChangesIdentity() {
        JobParameters first = factory.create(
            "merchant-42",
            LocalDate.of(2026, 11, 16),
            "trace-1");

        JobParameters second = factory.create(
            "merchant-42",
            LocalDate.of(2026, 11, 17),
            "trace-2");

        assertNotEquals(
            first.getIdentifyingParameters(),
            second.getIdentifyingParameters());
    }
}
```

The example uses `getIdentifyingParameters()` from `JobParameters` in Spring Batch 5.x. The test compares the identifying parameter set as a direct expression of design intent; integration tests with `JobRepository` are still required to verify the real lifecycle.

### 17.3. Test to Catch the Anti-Pattern

A test can call the factory twice with the same business key at two different times and assert that the identifying parameters remain equal. If someone adds `System.currentTimeMillis()` as identifying, the test will catch the unintended identity change. You can inject a `Clock` to control test time instead of using sleep, avoiding flaky tests.

---

## 18. Integration Test: Job Fails Then Restarts on the Same Instance

An integration test needs to prove not only that parameters are stable, but also that the `JobInstance` is actually reused on restart.

### 18.1. Test Scenario

```text
invoiceImportJob
  prepareStep  : always COMPLETED
  importStep   : attempt 1 throws exception
                 attempt 2 succeeds

Launch with identifying businessDate=2026-11-16:
  JobExecution #1 FAILED

Restart execution #1:
  JobExecution #2 COMPLETED

Assertions:
  execution IDs are different
  JobInstance IDs are equal
  prepareStep executes only once
  importStep executes twice
```

### 18.2. Test Configuration

Example Gradle setup with Spring Boot BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`src/test/resources/application-identity-test.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
  datasource:
    generate-unique-name: true
```

In-memory H2 is suitable for testing two executions **within the same context**. Restarting across a real JVM/container restart requires a durable metadata repository.

### 18.3. JUnit 5 / Spring Batch 5 Integration Test

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = StableIdentityRestartTest.TestApp.class
)
@ActiveProfiles("identity-test")
class StableIdentityRestartTest {

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    JobOperator operator;

    @Autowired
    JobExplorer explorer;

    @Autowired
    AtomicInteger prepareCalls;

    @Autowired
    AtomicInteger importCalls;

    @Test
    void restartCreatesNewExecutionOnSameInstance()
            throws Exception {

        JobParameters params = new JobParametersBuilder()
            .addString("tenantId", "merchant-42", true)
            .addString("businessDate", "2026-11-16", true)
            .toJobParameters();

        JobExecution first = launcher.launchJob(params);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(1, prepareCalls.get());
        assertEquals(1, importCalls.get());

        Long restartedId = operator.restart(first.getId());
        JobExecution restarted =
            explorer.getJobExecution(restartedId);

        // Test assumes synchronous JobLauncher; async launchers
        // must poll until terminal status before asserting.
        assertNotNull(restarted);
        assertEquals(
            BatchStatus.COMPLETED,
            restarted.getStatus());

        assertNotEquals(first.getId(), restarted.getId());
        assertEquals(
            first.getJobInstance().getId(),
            restarted.getJobInstance().getId());

        assertEquals(1, prepareCalls.get());
        assertEquals(2, importCalls.get());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(TestJobs.class)
    static class TestApp { }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestJobs {

        @Bean
        AtomicInteger prepareCalls() {
            return new AtomicInteger();
        }

        @Bean
        AtomicInteger importCalls() {
            return new AtomicInteger();
        }

        @Bean
        AtomicBoolean failFirst() {
            return new AtomicBoolean(true);
        }

        @Bean
        Step prepareStep(
                JobRepository repository,
                PlatformTransactionManager tx,
                AtomicInteger prepareCalls) {

            return new StepBuilder("prepareStep", repository)
                .tasklet((contribution, context) -> {
                    prepareCalls.incrementAndGet();
                    return RepeatStatus.FINISHED;
                }, tx)
                .build();
        }

        @Bean
        Step importStep(
                JobRepository repository,
                PlatformTransactionManager tx,
                AtomicInteger importCalls,
                AtomicBoolean failFirst) {

            return new StepBuilder("importStep", repository)
                .tasklet((contribution, context) -> {
                    importCalls.incrementAndGet();

                    if (failFirst.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Simulated temporary failure");
                    }

                    return RepeatStatus.FINISHED;
                }, tx)
                .build();
        }

        @Bean
        Job invoiceImportJob(
                JobRepository repository,
                Step prepareStep,
                Step importStep) {

            return new JobBuilder(
                "invoiceImportJob", repository)
                .start(prepareStep)
                .next(importStep)
                .build();
        }
    }
}
```

**Explanation:**

- `AtomicBoolean` is a fixture that injects a one-time failure; it is not a business checkpoint.
- `JobLauncherTestUtils` in this context has only one job to choose from. In a context with multiple jobs, configure the job under test explicitly.
- `prepareStep` completed on the first run, so it is skipped by default on restart.
- `importStep` failed on the first run and executes again on the second run.
- `operator.restart(first.getId())` creates a new execution under the same instance.
- `JobExplorer` reads persisted metadata back to verify the instance/execution relationship.
- If using an async launcher, reading once right after restart is not sufficient to assert terminal `COMPLETED`.

### 18.4. Dedicated Test for the Timestamp Anti-Pattern

Create a side-effect-free test job and launch it twice with the same `businessDate` but two **distinct identifying timestamps explicitly set by the test**. Assert that the repository creates two different `JobInstance`s. This test demonstrates the identity semantics deterministically without relying on `Thread.sleep` or hoping two `System.currentTimeMillis()` calls differ.

Then run the same job with stable parameters; if the first instance has already completed, launching again will not create another execution as a new instance. That is the desired lifecycle safeguard.

### 18.5. Testing Real Checkpoints

A simple tasklet fixture does not prove that a reader restarts with the right checkpoint. With a chunk job reading 100 items, commit interval 20, intentionally failing after several chunks and restarting:

- Verify the checkpoint persisted in `ExecutionContext`.
- Verify the reader implements `ItemStream` and receives the right state on `open`.
- Verify the number of unique output records after restart is 100.
- Verify already-committed items are not reprocessed or double-written outside the contract.
- If the test uses an idempotent writer, assert the final output rather than merely counting method calls.

---

## 19. Migration: Fixing a Production Job That Has Long Used Timestamps

If code currently always adds an identifying `runAt`, removing that parameter will change `JobInstance` identity from the moment of deployment. Historical failed instances still remain in metadata. Do not assume a one-line code change will automatically merge old instances into one.

### 19.1. Survey Before Changing

1. List all jobs that use identifying timestamps/UUIDs/`run.id`.
2. Classify by business category: independent snapshots, file imports, daily reports, settlements, backfills, etc.
3. Query `BATCH_JOB_INSTANCE`/`BATCH_JOB_EXECUTION_PARAMS` to inspect instance counts per business key.
4. Identify which instances are `COMPLETED`, `FAILED`, currently `STARTED`, or have unreconciled output.
5. Reconcile business data: are there already duplicate rows/events/file exports?
6. Check whether an external orchestrator or API is still sending timestamps under the old contract.
7. Approve the new business identity and the policy for reprocessing completed periods.

### 19.2. Grouping Historical Data

| Legacy data | Usually sensible handling |
| --- | --- |
| Instance completed, output valid | Keep for audit; mark the period completed in the business ledger |
| Multiple completed instances for the same period | Reconcile versions/output, determine the authoritative record, and clean up duplicates |
| Instance failed, checkpoint still valid | Consider restarting **that exact old instance** before removing the timestamp mechanism entirely |
| Instance failed, checkpoint no longer compatible | Controlled remediation/reprocess procedure; do not merge manually via SQL |
| Instance stuck in `STARTED` after a process crash | Verify the worker has stopped and perform appropriate metadata recovery |
| No execution found but output already exists | Reconcile output and request logs before launching anew |

### 19.3. Avoid Manual Schema or Metadata Edits

Do not delete the `runAt` parameter from `BATCH_JOB_EXECUTION_PARAMS` or edit `JOB_KEY` to force Spring Batch to merge old instances. These operations break identity/metadata relationships and can destroy restartability, auditability, or state consistency.

A more sustainable approach:

- Leave Spring Batch history intact.
- Build/migrate a **business request ledger** keyed by a stable key.
- Separate "launch new period" logic from "restart old execution" logic.
- Allow handling legacy failed instances via a runbook.
- If reprocessing is mandatory, create a revision with clear semantics and an idempotent writer.
- Add unit/integration tests to prevent identifying timestamps from creeping back in.

### 19.4. Careful Rollout Strategy

```text
Phase 1: observe
  - Log jobName/identifying parameters
  - Count duplicate business keys
  - Map failed instances and checkpoints

Phase 2: add business identity
  - Create params factory + tests
  - Create request/slot ledger if needed
  - Add queries/reconciliation

Phase 3: switch scheduler/API
  - Use stable identifying params
  - Return existing status on duplicate requests
  - Call restart for FAILED instances

Phase 4: verify
  - No new JobInstance created for same-period retries
  - No duplicate business output
  - Monitor restart success rate
```

This is an example rollout, not a replacement for change management in environments with critical data.

---

## 20. Rules for APIs and Operational Runbooks

### 20.1. Do Not Turn Every "Run" Button into a New Request

An operations UI can provide three clear actions:

| Action | Purpose | Parameter semantics |
| --- | --- | --- |
| **Start business period** | Process a period that has never run | Stable tenant/date/file/slot key |
| **Restart failed execution** | Continue the same failed work | Old execution ID, same instance |
| **Reprocess completed period** | Create a new revision upon approval | Revision ID + target output policy |

Separating actions prevents the situation where an operator clicks "Run again" without knowing whether the job will resume, start over from scratch, or overwrite results.

### 20.2. Before Restarting

- Inspect job name, JobInstance ID, identifying parameters, JobExecution ID, and status.
- Verify the instance has not already `COMPLETED` in a newer execution.
- Check that the job definition/step names and `ExecutionContext` are compatible.
- Confirm the root cause of failure has been resolved.
- Reconcile side effects and transaction outcomes if failure occurred near a commit.
- Confirm no other execution/worker is currently running.
- Audit who/what requested the restart; do not manually alter identifying parameters.

### 20.3. After Restarting

- Record the new JobExecution ID.
- Monitor through to a terminal status.
- Check checkpoints and read/write/skip/rollback counts.
- Reconcile business output against source data.
- Mark a period completed only when the business result is accurate.
- Do not treat "the API returned an execution ID" as equivalent to job success.

### 20.4. When Data Has Already Been Duplicated

If multiple instances with different timestamps wrote the same data, **do not just delete rows in `BATCH_JOB_INSTANCE`**. Prioritize:

1. Stopping duplicate requests.
2. Classifying output by business key and version.
3. Determining which record/event is authoritative via audit records.
4. Performing business remediation with transactions/reconciliation.
5. Checking downstream side effects.
6. Preserving enough history to explain the incident.

Spring Batch metadata does not automatically decide how an externally sent payment/email/file should be recalled.

---

## 21. Reliable Architecture for Scheduled and Manual Batch

```text
       Scheduler / REST / Operator
                   |
                   v
          Business request layer
          - tenant
          - businessDate / sourceFileId
          - optional revision
                   |
                   v
          Stable parameters factory
          - identifying business keys
          - non-identifying trace details
                   |
                   v
        Query JobExplorer / Repository
                   |
          +--------+----------+
          |                   |
     No instance           Existing instance
          |                   |
          v             +-----+---------------------+
   JobLauncher.run      |           |              |
                    FAILED       STARTED        COMPLETED
                       |           |              |
                       v           v              v
                JobOperator     monitor       return status /
                restart        existing       explicit reprocess
                       |
                       v
                 JobExecution new
                 same JobInstance
                       |
                       v
          Validate business output
```

The business request layer can use a ledger table with a unique constraint on the business key to prevent concurrent requests or network retries from racing. Use `JobExplorer` to look up executions, but do not rely on "check then launch" as an absolute lock; the repository and an atomic claim in the database must still be designed properly.

For multi-tenant jobs, authorization must not rely solely on the client knowing a JobExecution ID. A restart endpoint must verify job/tenant ownership and role before calling the operator.

---

## 22. Frequently Asked Questions

### 22.1. "If I want to run a job every day, why not use the current date/time?"

You can use the **business date** to identify a new period, but you should not use the **timestamp when the request hit the node** as a unique ID. For daily jobs, `businessDate` or a nominal schedule slot is a more meaningful key. If a batch runs at 02:00 to process the previous day's data, the identifying value should be the data date to process rather than simply the current date.

### 22.2. "Does marking the timestamp `identifying=false` solve everything?"

No. It prevents that timestamp from creating a new `JobInstance`, but you still need clear policies for:

- Duplicate requests while an instance is running.
- Requests after an instance has completed.
- Restarting a failed instance.
- Auditing who sent the request and when.
- Identifying the source data/processing batch.
- Potential repeated side effects when commit outcomes are uncertain.

### 22.3. "Should every job be restartable?"

No. Some jobs are designed to be non-restartable because their operations cannot be safely repeated. In those cases, a separate compensation/reprocess procedure is needed. However, creating a new `JobInstance` via timestamp **does not automatically make an unsafe operation safe**; it can even bypass `preventRestart()` placed there to protect the business.

### 22.4. "What if I want to re-run a `COMPLETED` job?"

A completed `JobInstance` cannot be restarted under the normal lifecycle. Define the genuine reprocessing objective, the result version, and downstream impact. If a new logical run is needed, create an explicit **business revision** (for example `revision=2`) rather than silently using a timestamp to spawn another instance.

### 22.5. "Is using a UUID instead of a timestamp better?"

A UUID helps avoid ID collisions if you genuinely need every request to be an independent unit of work. But if this is a retry for the same business period or the same source file, an identifying UUID still causes **a different `JobInstance`**, so it will not restore the old checkpoint. The issue is the semantics of identity, not the choice of ID generation algorithm.

### 22.6. "Do JobParameters need to carry all business information?"

No. Put only the attributes needed to identify the logical run into identifying params. Large/sensitive data or data that varies per item should be stored in dedicated data sources and accessed by ID rather than stuffed into JobParameters. Audit fields can live in non-identifying params or a request log.

### 22.7. "Can I restart using `JobLauncher.run` with the same parameters?"

There are cases where the framework can restart a failed instance when launching the same job with the same identifying parameters, if state and configuration permit. However, in operations, `JobOperator.restart(executionId)` expresses intent clearly and leverages the old execution's metadata. Whichever method you use, **do not alter identifying parameters arbitrarily**.

### 22.8. "What if `System.currentTimeMillis()` returns the same value for two requests?"

Two requests can unintentionally share the same identity; the framework will handle them according to the corresponding instance state, potentially rejecting a request while running or already completed. Timestamps are not proper business IDs; if each invocation truly needs to be independent, design a durable request ID/sequence, along with an appropriate data contract and idempotency.

---

## 23. Practice Exercises

### Exercise 1 — Determine the Number of `JobInstance`s

Given three parameter sets for the same `invoiceImportJob`:

```text
A: businessDate=2026-11-16 [true], runAt=1000 [true]
B: businessDate=2026-11-16 [true], runAt=2000 [true]
C: businessDate=2026-11-16 [true], runAt=3000 [true]
```

Determine how many logical instances the framework will see. Then change `runAt` to `identifying=false` and explain what changes; note that completed/running states still govern launchability.

### Exercise 2 — Write a JobParameters Factory

Create a `JobParametersFactory` for an invoice import job keyed by tenant + business date, adding a non-identifying `correlationId`. Write unit tests:

- Same tenant/date, different correlation -> identifying params are equal.
- Different tenant or date -> identifying params differ.
- No identifying timestamp/UUID.
- Ensure timezone and `businessDate` formatting are standardized.

### Exercise 3 — Simulate a Restart Failure

Create a chunk job importing 100 items, chunk size 20, intentionally failing after 40 items have committed. Try two approaches:

1. Re-run with a new identifying timestamp.
2. Restart the old execution using `JobOperator`.

Compare JobInstance IDs, reader checkpoints, number of records received by the writer, and number of unique records written. Explain why approach 1 can cause duplicates.

### Exercise 4 — Scheduler After Downtime

Suppose a cron runs daily at 02:00, the application stops on days 11–12 and restarts at 09:00 on day 13. Build the list of missed nominal slots and map each slot to stable identifying parameters.

Write a reconciler that can receive duplicate requests without creating a new JobInstance for the same slot; add a backfill cap of at most two slots per run.

### Exercise 5 — Approved Completed Rerun

The report for the 16th is `COMPLETED`, the source was fixed, and recalculation is needed. Design `revision` and a published reports table so the rerun produces version 2 instead of creating uncontrolled duplicate files/rows. Describe how to retain version 1 history and avoid re-emitting side effects.

### Exercise 6 — Detecting Improper Historical Instances

Using `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, and `BATCH_JOB_EXECUTION_PARAMS`, write a query/listing to identify executions sharing the same business date but having different identifying `runAt` values. Build a runbook to classify failed/completed instances and reconcile output before changing code.

### Exercise 7 — API Idempotency

Two requests for the same tenant/date arrive within the same millisecond and one request times out after the server already created an execution. Design a unique business request ledger, atomic claim, and lookup of existing execution state. Demonstrate that no timestamp is needed for the caller to receive a consistent response.

---

## 24. Checklist Before Releasing a Batch Launcher

- [ ] Every identifying parameter represents a meaningful part of **business identity**.
- [ ] Request timestamps/trace IDs never become identifying just to dodge duplicates.
- [ ] Every period or source file has a stable key format across retries and deployments.
- [ ] `FAILED`/`STOPPED` states have a clear restart path.
- [ ] `STARTED` states are monitored instead of spawning a new instance.
- [ ] `COMPLETED` states are returned clearly instead of "incrementing run.id to run again".
- [ ] Reprocessing completed periods has its own revision, audit, and output policy.
- [ ] Schedulers use nominal slots and have a mechanism to handle missed schedules when needed.
- [ ] Writers have unique business keys/idempotency matching retry/restart requirements.
- [ ] `JobRepository` is durable across process restarts, preserving `ExecutionContext` for checkpoints.
- [ ] Unit tests verify identifying params; integration tests verify JobInstance ID and restart.
- [ ] Metrics/logs distinguish new JobInstances, restarts, and completed business periods.

When launcher code is forced to generate the current time just to "make Spring Batch willing to run", treat that as a sign that **identity and lifecycle** need redesigning. The solution is usually stable business keys for prior work, restarting the right execution, and a dedicated rerun workflow for genuinely new work.

## 25. References

- [Spring Batch Reference — Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobParameters`, completed/running states, and job launch.
- [Spring Batch Reference — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobOperator`, `JobExplorer`, and restart by execution ID.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): managing execution/instance metadata.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, and identifying parameters.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoints and recovery state.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` and job test utilities.
- [Spring Batch 5.2 API — JobParametersBuilder](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/JobParametersBuilder.html): specifying identifying/non-identifying parameters.
- [Spring Batch 5.2 API — JobOperator](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/JobOperator.html): restart and startNextInstance.

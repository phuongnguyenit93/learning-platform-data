# Metadata for Auditing in Spring Batch

In batch processing systems, operational questions do not stop at "did the batch run succeed?" After an import, reconciliation, report export, or order status transition, operations teams and auditors also need to know **which job ran, which data period it processed, when it started and finished, how many records were read/written/skipped, what errors occurred, and what actual results were produced**.

**Metadata for auditing** is the set of information used to reconstruct batch execution history and link that history to business data. In **Spring Batch Core Processing**, the most important foundation is `JobRepository` metadata: `JobInstance`, `JobExecution`, `StepExecution`, `JobParameters`, and `ExecutionContext`. However, Spring Batch's internal metadata is designed primarily for **operations, monitoring, and restarts**, and does not automatically satisfy every requirement for an independent, tamper-evident audit log or retention policy.

Therefore, distinguish three layers of information:

| Layer | Question answered | Example |
| --- | --- | --- |
| Spring Batch execution metadata | What did the framework run and what state is it in? | `JOB_EXECUTION_ID`, timestamps, `BatchStatus`, read/write/skip counts |
| Business audit | Which source data, which period, who/what triggered it, and what result was accepted? | `businessDate`, `sourceFileId`, checksum, document count, output artifact |
| Monitoring/observability | Is there an anomaly right now or in recent trends? | Duration metrics, SLA alerts, tracing, error logs |

A complete system **links** all three using `jobExecutionId`, job name, period key, and correlation ID. This article moves from Spring Batch's built-in metadata to building a meaningful audit trail for investigating any run.

## 1. Built-in Metadata in Spring Batch

Spring Batch stores execution state in `JobRepository`. With a JDBC-backed repository, metadata tables typically use the `BATCH_` prefix:

```text
                         BATCH_JOB_INSTANCE
                          (JOB_INSTANCE_ID)
                                 |
                              1 : N
                                 v
                         BATCH_JOB_EXECUTION
                         (JOB_EXECUTION_ID)
                            /          \
                         1 : N         1 : N
                         /                \
                        v                  v
                BATCH_STEP_EXECUTION   BATCH_JOB_EXECUTION_PARAMS
                  (STEP_EXECUTION_ID)    (JobParameters)
                        |
                        v
              BATCH_STEP_EXECUTION_CONTEXT

             BATCH_JOB_EXECUTION_CONTEXT
               (per JOB_EXECUTION_ID)
```

`BATCH_JOB_EXECUTION_CONTEXT` links directly to `BATCH_JOB_EXECUTION` and holds job-scoped state. `BATCH_STEP_EXECUTION_CONTEXT` links to a step execution and holds step-scoped state. Neither context table is a "log of every change": they typically reflect state saved at the latest checkpoints.

### 1.1. `JobInstance`: Identity of the Logical Job

A `JobInstance` is identified by **job name + set of identifying `JobParameters`**. For example:

```text
Job name:      dailySettlementJob
businessDate:  2026-11-16   (identifying)
region:        HCM          (identifying)

=> one JobInstance for this data period/region pair
```

If the same instance is restarted after a failure, it can have multiple `JobExecution`s. If a random `runId` is accidentally added as an identifying parameter on every invocation, the framework treats each run as a separate instance even for the exact same business data. When auditing a period, understand exactly how the application selects identifying parameters.

### 1.2. `JobExecution`: Individual Run Attempts

`JobExecution` represents a single attempt to run a job. Key details include:

- `JobExecution.getId()`: execution ID, useful for linking logs, metrics, and audit events.
- `getJobInstance()`: reference to the logical job and job name.
- `getJobParameters()`: parameters for this run, such as `businessDate` or source file ID.
- `getCreateTime()`, `getStartTime()`, `getEndTime()`: execution lifecycle timestamps, when available.
- `getStatus()`: `BatchStatus` values such as `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPING`, `STOPPED`, `ABANDONED`, `UNKNOWN`.
- `getExitStatus()`: exit code/description set by the job or listeners; its semantics may differ from `BatchStatus`.
- `getAllFailureExceptions()` or step-level exceptions: failure causes saved in execution metadata when available.

**Key takeaway:** `BatchStatus` is lifecycle state managed by the framework. `ExitStatus` describes the outcome used by flows and listeners for routing. For instance, a step may complete technically yet set a custom exit code to branch to manual review. Audits should capture both when business explanations are needed.

### 1.3. `StepExecution`: Evidence of Each Processing Step

`StepExecution` contains statuses and counters that are very helpful for auditing:

| Field/method | Typical meaning |
| --- | --- |
| `getStepName()` | Executed step |
| `getStatus()` and `getExitStatus()` | Step status and exit code |
| `getStartTime()`, `getEndTime()` | Step start/end timestamps |
| `getReadCount()` | Number of items returned by the reader for processing |
| `getWriteCount()` | Number of items successfully written by the framework via the writer at the step level |
| `getFilterCount()` | Number of items filtered by the processor returning `null` |
| `getReadSkipCount()` | Number of items skipped due to reader errors |
| `getProcessSkipCount()` | Number of items skipped due to processor errors |
| `getWriteSkipCount()` | Number of items skipped due to writer errors |
| `getCommitCount()` | Number of recorded chunk/transaction commits |
| `getRollbackCount()` | Number of recorded rollbacks |
| `getFailureExceptions()` | Errors associated with the step |

Counters describe **framework activity** within the step, and do not by themselves prove that every record in the target system is valid. For example, a writer producing an aggregate file may write only a few output lines even though the reader read millions of items. Or a writer might call an external API that silently rejects records: metadata may not reflect what the external system actually accepted if the writer does not report errors properly.

### 1.4. `JobParameters`: Tracing Keys for the Data Period

Spring Batch supports both identifying and non-identifying parameters. For auditing, both are useful with different roles:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")        // identifying by default
    .addString("region", "HCM")                      // identifying
    .addString("requestedBy", "nightly-scheduler", false)
    .toJobParameters();
```

In this example, `businessDate` and `region` identify the `JobInstance`; `requestedBy` is merely an extra execution attribute. Do not place tokens, passwords, customer PII, or sensitive file contents in `JobParameters`, since they can be persisted in the repository and appear in logs and operational UIs.

### 1.5. `ExecutionContext`: Checkpoints, Not an Immutable Audit Log

Jobs and steps have an `ExecutionContext` to store restart state, such as the current file name, offset, or pages read:

```java
stepExecution.getExecutionContext().putLong("lastProcessedLine", 5000L);
```

The framework persists the context at checkpoints. When a key is updated multiple times, prior values are no longer present in the current snapshot. Therefore, **never use `ExecutionContext` as a store for full audit events**. Also avoid stuffing large lists or sensitive data into the context: it bloats metadata, increases data-exposure risk, and causes serialization/restart issues.

## 2. JDBC Metadata Tables to Know

Column names and some schema details vary across Spring Batch versions and databases. The examples below follow the common structure in **Spring Batch 5.x**:

| Table | Typical columns | Audit purpose |
| --- | --- | --- |
| `BATCH_JOB_INSTANCE` | `JOB_INSTANCE_ID`, `JOB_NAME`, `JOB_KEY` | Identifies logical work and groups executions of the same instance |
| `BATCH_JOB_EXECUTION` | `JOB_EXECUTION_ID`, `JOB_INSTANCE_ID`, `CREATE_TIME`, `START_TIME`, `END_TIME`, `STATUS`, `EXIT_CODE`, `EXIT_MESSAGE`, `LAST_UPDATED` | Tracks each run and its outcome |
| `BATCH_JOB_EXECUTION_PARAMS` | `JOB_EXECUTION_ID`, `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE`, `IDENTIFYING` | Explains inputs and identity of the job execution |
| `BATCH_STEP_EXECUTION` | `STEP_EXECUTION_ID`, `JOB_EXECUTION_ID`, `STEP_NAME`, `STATUS`, read/write/skip/commit/rollback counters | Audits each step |
| `BATCH_JOB_EXECUTION_CONTEXT` | `JOB_EXECUTION_ID`, `SHORT_CONTEXT`, `SERIALIZED_CONTEXT` | Context snapshot for job restarts |
| `BATCH_STEP_EXECUTION_CONTEXT` | `STEP_EXECUTION_ID`, `SHORT_CONTEXT`, `SERIALIZED_CONTEXT` | Checkpoint snapshot of the step |

**Do not manually update `BATCH_*` tables for auditing.** They are owned by Spring Batch. Modifying `STATUS`, counters, or contexts directly via SQL can break restarts, falsify history, or leave executions in an inconsistent state. For custom audit needs, create separate tables and use framework APIs/listeners.

### 2.1. Querying Job and Step History

A read-only query for an operations screen or audit report:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.CREATE_TIME AS job_created_at,
    je.START_TIME  AS job_started_at,
    je.END_TIME    AS job_finished_at,
    je.STATUS      AS job_status,
    je.EXIT_CODE   AS job_exit_code,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS      AS step_status,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.FILTER_COUNT,
    se.READ_SKIP_COUNT,
    se.PROCESS_SKIP_COUNT,
    se.WRITE_SKIP_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_NAME = 'dailySettlementJob'
ORDER BY je.JOB_EXECUTION_ID DESC, se.STEP_EXECUTION_ID;
```

Each row represents a step execution or a job execution without steps yet. Because of the one-to-many join, job-level fields repeat across step rows; when aggregating reports, **do not sum job durations or job run counts across every row**.

To inspect the `businessDate` parameter in the Spring Batch 5.x schema:

```sql
SELECT
    je.JOB_EXECUTION_ID,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_EXECUTION_PARAMS p
  ON p.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE je.JOB_EXECUTION_ID = :execution_id
  AND p.PARAMETER_NAME IN ('businessDate', 'region');
```

`:execution_id` represents a SQL client/framework bind parameter, not literal syntax supported by every interactive SQL tool. In applications, pass values via prepared statements or `NamedParameterJdbcTemplate` to avoid direct SQL string concatenation.

If using **Spring Batch 4.x, 6.x, or a customized schema**, inspect the DDL of your deployed version before querying directly. For example, Spring Batch 4.x uses typed parameter columns, unlike 5.x's `PARAMETER_TYPE`/`PARAMETER_VALUE` structure.

### 2.2. Prefer Framework APIs When Appropriate

When developing Spring Batch applications, you can use `JobExplorer` to read metadata instead of coupling directly to table names:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public class ExecutionLookupService {
    private final JobExplorer jobExplorer;

    public ExecutionLookupService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution find(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

This snippet uses Spring Batch 5.x packages. `getJobExecution(...)` can return `null` if not found. Depending on the version, `JobExplorer` also provides methods to look up instances, executions by job, and running executions. It lets you build audit/monitoring screens without accessing the schema directly, though you still must manage access permissions and query volume.

## 3. Designing a Business-Meaningful Audit Record

Runtime metadata answers *"What did Spring Batch do?"*. A business audit must add *"Which dataset was this job run on, why was it triggered, and what output data was accepted?"*.

Consider a job importing a period's transaction file:

```text
Input:
  businessDate = 2026-11-16
  sourceFileId = bank-feed-20261116-001
  sourceChecksum = sha256:...

Batch:
  jobName = importPaymentsJob
  jobInstanceId = 302
  jobExecutionId = 517
  status = COMPLETED

Result:
  expectedRecords = 10000
  acceptedRecords = 9988
  rejectedRecords = 12
  outputManifestId = batch-output-20261116-001
```

Collect the following groups of fields, tailored to your needs:

| Group | Suggested fields | Why useful |
| --- | --- | --- |
| Execution identity | `jobName`, `jobInstanceId`, `jobExecutionId`, `stepName`, `stepExecutionId` | Links audit records to framework metadata |
| Data period identity | `businessDate`, `tenantId`, `region`, `windowStart`, `windowEnd` | Traces which period the actual data belongs to |
| Trigger source | `triggerType`, `schedulerName`, `requestedBy`, `correlationId`, `requestId` | Distinguishes automated schedules, manual runs, and backfills |
| Input source | `sourceSystem`, `sourceFileId`, `objectVersion`, checksum, input count | Proves which version of data was processed |
| Timestamps | `scheduledAt`, `startedAt`, `finishedAt`, `eventRecordedAt` | Measures latency, checks SLAs, investigates downtime |
| Technical outcome | `BatchStatus`, `ExitStatus`, step statuses, read/write/skip counts | Identifies execution path and framework outcome |
| Business outcome | `acceptedCount`, `rejectedCount`, `totalAmount`, `outputManifestId`, output checksum | Reconciles batch runs with business data |
| Errors/warnings | `errorCode`, `failureCategory`, reconciliation code, error artifact path | Investigation and accountability |
| Processing version | `appVersion`, `rulesetVersion`, `schemaVersion` | Explains differing outputs for identical inputs after upgrades |

**You do not need to store every field above in every event.** A job-level event can hold summary outcomes while file- or step-level events hold detailed info. What matters is clear linking keys and consistent metric definitions.

### 3.1. What Is Metadata Enough to Confirm?

Suppose `StepExecution` records:

```text
READ_COUNT         = 10000
FILTER_COUNT       = 10
PROCESS_SKIP_COUNT = 2
WRITE_COUNT        = 9988
STATUS             = COMPLETED
```

These numbers show how the step processed items under Spring Batch mechanics. They **do not on their own prove** how many transactions the bank accepted, whether financial totals reconcile, or that the output file was not tampered with after export. For financial auditing requirements, the application must also verify actual output, checksums, total amounts, and delivery/acknowledgment trails from target systems.

### 3.2. Event Audits vs. Snapshots

Two complementary models exist:

**Current-state snapshot:** a `batch_run_summary` row updated from `RUNNING` to `FAILED`/`COMPLETED`. Easy for latest-status reports, but previous values can be overwritten.

**Append-only audit events:** each significant transition creates a new row, e.g., `JOB_REQUESTED`, `JOB_STARTED`, `STEP_COMPLETED`, `JOB_FAILED`, `JOB_COMPLETED`, `OUTPUT_PUBLISHED`. This reconstructs the timeline and avoids losing history via overwrites.

```text
2026-11-17 02:00:00  JOB_REQUESTED   businessDate=2026-11-16
2026-11-17 02:00:01  JOB_STARTED     jobExecutionId=517
2026-11-17 02:05:30  STEP_COMPLETED  read=10000, write=9988
2026-11-17 02:05:31  OUTPUT_PUBLISHED manifest=batch-output-...
2026-11-17 02:05:31  JOB_COMPLETED   jobExecutionId=517
```

For true append-only storage, restrict update/delete permissions, manage retention, and consider immutable storage if required by organizational compliance. **A table to which the app only issues `INSERT` does not automatically become tamper-proof**: DBAs or privileged accounts can still alter records without additional controls.

## 4. Recording Audits via Spring Batch Listeners

Spring Batch provides lifecycle callbacks for jobs and steps. In **Spring Batch 5.x**, `JobExecutionListener` provides `beforeJob` and `afterJob`; `StepExecutionListener` provides `beforeStep` and `afterStep`. These are convenient places to record job/step-level audits after the framework creates metadata.

```text
Scheduler / REST / CLI
        |
        v
   JobLauncher
        |
        v
  JobExecution
        |
        +-- beforeJob()  -> audit JOB_STARTED (if needed)
        |
        +-- Step A ----- Step B ----- Step C
        |
        +-- afterJob()   -> audit JOB_FINISHED
                             |
                             v
                     application audit table
```

Listeners fit **lifecycle summaries**. When auditing an exact business action like `PAYMENT_ACCEPTED`, emit the event where that action actually commits or is acknowledged by the target system—do not assume `afterJob()` holds complete proof.

### 4.1. Defining a Dedicated Audit Event Table

Simple illustrative DDL for standard SQL databases:

```sql
CREATE TABLE batch_audit_event (
    event_id          VARCHAR(100) PRIMARY KEY,
    job_execution_id  BIGINT NOT NULL,
    event_type        VARCHAR(40) NOT NULL,
    event_recorded_at TIMESTAMP NOT NULL,
    job_name          VARCHAR(120) NOT NULL,
    business_date     VARCHAR(10),
    batch_status      VARCHAR(30) NOT NULL,
    exit_code         VARCHAR(100),
    read_count        BIGINT NOT NULL,
    write_count       BIGINT NOT NULL,
    skip_count        BIGINT NOT NULL
);

CREATE INDEX idx_batch_audit_execution
    ON batch_audit_event (job_execution_id);
```

This is an **application-owned table**, not a `BATCH_*` table managed by Spring Batch. `event_id` acts as an idempotency key preventing duplicate inserts for the same logical event. A production schema may add `tenant_id`, `trigger_id`, `source_manifest_id`, `output_manifest_id`, `event_version`, access controls, and data partitioning strategies.

`TIMESTAMP` does not store full timezone information across every database engine. For multi-region apps or strict auditing requirements, pick the right DB timestamp type and enforce UTC storage consistently across the system.

### 4.2. Audit-Writing Listener and Service

The example below uses `JdbcTemplate`, Spring transactions, and Spring Batch 5.x:

```java
package com.example.batch.audit;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class BatchAuditListener implements JobExecutionListener {

    private final BatchAuditService auditService;

    public BatchAuditListener(BatchAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        auditService.recordFinishedJob(jobExecution);
    }
}
```

Service writing the audit record in a separate transaction:

```java
package com.example.batch.audit;

import java.sql.Timestamp;
import java.time.Instant;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BatchAuditService {

    private final JdbcTemplate jdbcTemplate;

    public BatchAuditService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFinishedJob(JobExecution execution) {
        long readCount = execution.getStepExecutions().stream()
            .mapToLong(StepExecution::getReadCount)
            .sum();

        long writeCount = execution.getStepExecutions().stream()
            .mapToLong(StepExecution::getWriteCount)
            .sum();

        long skipCount = execution.getStepExecutions().stream()
            .mapToLong(step ->
                step.getReadSkipCount()
                + step.getProcessSkipCount()
                + step.getWriteSkipCount())
            .sum();

        String eventId = "job-" + execution.getId() + "-finished";
        String businessDate = execution.getJobParameters()
            .getString("businessDate");

        jdbcTemplate.update("""
            INSERT INTO batch_audit_event (
                event_id, job_execution_id, event_type, event_recorded_at,
                job_name, business_date, batch_status, exit_code,
                read_count, write_count, skip_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            eventId,
            execution.getId(),
            "JOB_FINISHED",
            Timestamp.from(Instant.now()),
            execution.getJobInstance().getJobName(),
            businessDate,
            execution.getStatus().name(),
            execution.getExitStatus().getExitCode(),
            readCount,
            writeCount,
            skipCount
        );
    }
}
```

Attach the listener to the job:

```java
@Bean
Job importPaymentsJob(JobRepository jobRepository,
                      Step importPaymentsStep,
                      BatchAuditListener auditListener) {
    return new JobBuilder("importPaymentsJob", jobRepository)
        .listener(auditListener)
        .start(importPaymentsStep)
        .build();
}
```

This example demonstrates separating the listener and service. `@Transactional(REQUIRES_NEW)` takes effect when invoked from another Spring bean through a proxy, such as the listener calling `BatchAuditService`. It ensures the audit write uses a separate transaction under a properly configured transaction manager; it does not mean the event and all batch side effects commit atomically together.

**Important limitations of this pattern:**

1. `afterJob()` is an in-process callback. If the JVM/Pod is killed abruptly, the callback may **not run**. A system with strict audit requirements needs a reconciliation job to detect abnormally terminated executions or missing events.
2. If the audit database is unavailable, `jdbcTemplate.update()` can fail. Establish a clear policy: log an alert and backfill, route through a durable outbox/queue, or treat missing audits as a critical failure per business rules. Never swallow errors silently.
3. Computing `eventId` from `jobExecutionId` helps catch duplicate writes. If the callback runs again for the same execution, a second `INSERT` violates the primary key. In production, implement a dialect-appropriate idempotent insert/upsert or handle duplicate keys per contract.
4. Summing counters across all `StepExecution`s aggregates **step activity**, which may cover multiple stages processing the same item. It is not automatically the count of unique business records processed. If a job has multiple steps reading a record at different stages, summed `readCount` can exceed the unique source count.
5. Recording a single `JOB_FINISHED` audit event does not create history of intermediate transitions. If every transition or business event must be audited, emit events at those milestones.
6. Spring Batch 5.x's `JobExecution` uses different APIs/packages from some Spring Batch 6.x types. Adjust imports and configuration for your actual major version; do not mix code across versions.

### 4.3. Step-Level Auditing

When you need to know exactly which step produced skips or which output was generated, use `StepExecutionListener` to record individual outcomes:

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepAuditListener implements StepExecutionListener {
    private final StepAuditService auditService;

    public StepAuditListener(StepAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        auditService.recordStepResult(stepExecution);
        return null; // keep existing ExitStatus unchanged
    }
}
```

`StepAuditService` here is an application-implemented service, not a built-in Spring Batch class. A step-level event can include `stepExecutionId`, `stepName`, `jobExecutionId`, read/write/filter/skip/rollback counts, and the corresponding output artifact. In `afterStep`, returning `null` means the listener proposes no change to the step's exit status.

In systems that must audit every rejected item, use a skip listener or write to a dedicated rejected-records table. Record **error codes and record keys** rather than copying entire sensitive item payloads into logs/audits.

## 5. Auditing Business Events and Transaction Consistency

A completed `JobExecution` does not guarantee that external side effects were acknowledged. Consider a step sending payments:

```text
Reader -> Processor -> Payment API -> Database update
```

If the Payment API accepted a request yet the process dies before database commit, Spring Batch may record the step as failed or lose the final metadata update. Meanwhile, the Payment API may have already executed the side effect. Looking at `BatchStatus` alone cannot prove whether a transaction was or was not processed.

For genuine auditability, record correlation identifiers such as `paymentRequestId`, `idempotencyKey`, external response codes, and acknowledgment timestamps. Useful patterns include:

- **Transactional outbox:** write business data and the event to publish in the same database transaction, then let a publisher relay events externally; supports safe retries and reconciliation when publishing fails.
- **Idempotency keys:** assign a stable identifier to the same business request so target systems recognize retries.
- **Inbox/deduplication:** consumers track processed messages to avoid applying side effects multiple times.
- **Output manifests:** once output is written and verified, create a manifest containing name/version/checksum and record count, linking it to the execution.
- **Reconciliation:** periodically compare audit records, batch metadata, and target data to catch omissions or discrepancies.

No technique makes **all out-of-transaction side effects** roll back automatically with `JobRepository`. Audits must truthfully describe known state, including `UNKNOWN`/"pending reconciliation," rather than guessing from a `COMPLETED` flag.

## 6. Distinguishing Job Status from Business Period Status

`BatchStatus` is an attribute of **one execution**, whereas "November 16 period has been settled" is a business state that may span multiple executions.

Example:

```text
businessDate=2026-11-16

  JobInstance #302
      JobExecution #517  FAILED
      JobExecution #519  COMPLETED (restart)

  Business audit:
      Period 2026-11-16 = SETTLED
      finalExecutionId = 519
      outputManifestId = settlement-20261116-v1
```

To build a daily summary table, do not count `COMPLETED` execution rows and assume "one run per day." A period may be restarted, backfilled, or processed across multiple partitions. Define an explicit business key and an "output accepted" criterion independent of how many times the framework ran.

A period status table might contain:

```text
business_date | region | settlement_status | final_execution_id
2026-11-16    | HCM    | SETTLED           | 519
2026-11-16    | HN     | NEEDS_REVIEW      | 522
```

This table differs from Batch metadata: the application defines when a period qualifies as `SETTLED`. It may require an approval workflow, monetary balance checks, or external system reconciliation before accepting the outcome.

## 7. Auditing Under Retry, Skip, Failure, and Restart

### 7.1. Retry

In a chunk-oriented step, an item can be retried multiple times due to transient errors. Metadata provides aggregated signals such as rollback count, but does not automatically log every API call or retry attempt. If retries must be audited, log events with `attemptNumber` or request ID and link them to the final outcome. Do not assume each retry creates a new `JobExecution`; retries normally happen inside the current execution.

### 7.2. Skip

Skip count only tells you how many items were skipped by the error mechanism. To explain *why* and *which items*, store them in a dedicated rejected-items table:

```text
job_execution_id | step_execution_id | record_key | reason_code
517              | 8301              | PAY-0091   | INVALID_IBAN
517              | 8301              | PAY-0204   | DUPLICATE_REFERENCE
```

Do not store full account numbers, personal data, or sensitive payloads when record keys and error codes suffice. You can use a stable token/hash aligned with security policies to link back to authorized source systems.

### 7.3. Failed Jobs

An audit of a failed execution should record:

- `jobExecutionId` and the business period.
- `BatchStatus=FAILED`, `ExitStatus`, and the failing step if identifiable.
- Failure timestamp and previously completed steps.
- Committed/recorded counters, temporary files, or intermediate data produced.
- Next action: `RETRY_SCHEDULED`, `RESTART_PENDING`, `MANUAL_REVIEW`, or `ABANDONED` per application workflow.

A failed execution does not mean all side effects rolled back. The audit must document what actually committed or was accepted by external systems.

### 7.4. Restart

With a proper restart, `JobInstance` remains the same while `JobExecution` changes. Link audit events via `jobInstanceId` or business key and add `restartOfExecutionId` when the business needs to trace the chain of attempts.

**Avoid altering identifying `JobParameters` just to force a new run** when the goal is resuming from a checkpoint. That causes Spring Batch to create a different instance, breaking the framework's restart linkage and risking reprocessing already-committed data.

## 8. Evidence of Inputs and Outputs

To answer "which exact file did that day's batch use?", filename alone is usually insufficient: a file can be replaced while keeping the same name.

### 8.1. Input Manifest

At minimum, record:

```json
{
  "sourceSystem": "bank-feed",
  "sourceObjectId": "payments/2026-11-16/input.csv",
  "sourceVersion": "v-1024",
  "contentSha256": "<hexadecimal-sha256>",
  "byteLength": 487226,
  "businessDate": "2026-11-16",
  "recordCount": 10000
}
```

`contentSha256` in this example is a placeholder for the real hash computed from the file's bytes; **never** write a placeholder string into production audits. If the file lives in versioned object storage, store the object key alongside its version ID so the exact source version can be retrieved. Hashing detects data tampering, though it does not prove sender authenticity without source authentication or digital signatures.

### 8.2. Output Manifest

When a job writes report files or exports data to another system, the audit record can link to `outputManifestId`, `outputPath`, record count, checksum, publish timestamp, and acknowledgment status.

```text
JOB_COMPLETED
  jobExecutionId=519
  businessDate=2026-11-16
  outputManifestId=settlement-20261116-v1
  outputRecordCount=9988
  outputSha256=...
  publishedAt=2026-11-17T02:05:31Z
```

If a job writes multiple files or partitions, use a manifest listing every artifact. If output is partially created and the job fails, keep status as `PARTIAL` or `NOT_PUBLISHED` and never mark an unverified file as "published." Audits should distinguish **file creation**, **outcome commit**, and **publishing to consumers**.

## 9. Timestamps and Time Synchronization

Auditing often requires comparing logs across the scheduler, Spring Batch, databases, and external systems. Establish clear time conventions to avoid misreadings:

- Use **UTC for stored timestamps and cross-system exchange** wherever possible; convert to business timezones in UIs/reports.
- Record `businessDate` or the business window separately; **business date is not identical to the date of `createdAt` or `startedAt`**.
- In Java, prefer `Instant` or offset-aware types when emitting events; Spring Batch timestamp fields may use `LocalDateTime` depending on version and carry no timezone.
- Synchronize host/container clocks; clock skew makes cross-system timestamp ordering unreliable.
- Never interpret `END_TIME = null` as always meaning "currently running": the process may have died before updating metadata. Cross-check infrastructure state and heartbeats/health when building operational views.

Example timestamps for a batch processing **the previous day's** data:

```text
businessDate = 2026-11-16
scheduledAt  = 2026-11-17T02:00:00+07:00
startedAt    = 2026-11-16T19:00:01Z
finishedAt   = 2026-11-16T19:05:31Z
```

Here `scheduledAt` and `startedAt` express instants in two different timezones; to compare durations, convert everything to one unified convention.

## 10. How Auditing Differs from Monitoring Metrics and Logs

| Aspect | Batch metadata | Application logs | Metrics/traces | Audit trail |
| --- | --- | --- | --- | --- |
| Purpose | Framework execution/restart | Detailed diagnostics | Performance and distributed monitoring | Accountability for events and outcomes |
| Granularity | Job/step/counters/context | Free-form log lines | Counters, histograms, spans | Structured events with business keys |
| Lifecycle | Persisted and purged per repository policy | Per log retention | Per monitoring backend | Per dedicated audit retention/controls |
| Schema stability | Depends on Spring Batch | Easily changes with log format | Depends on instrumentation | Should version schema and control changes |
| Evidentiary value | Processing status | Supplements root cause | Anomaly signals | Evidence linking events to business data |

Logs are useful but typically lack an immutable schema, get rotated, and are not guaranteed complete on crashes. Metrics catch SLA slowdowns or rising skips, yet are **unsuitable for storing period codes or record IDs** as labels due to high cardinality. Audits should store detailed identifiers in tables/event stores; metrics should use only low-cardinality labels like job name, outcome group, or environment.

### Correlation ID

Carry a `correlationId` end-to-end across scheduler → batch launcher → step → downstream API/DB. When logging, place `jobExecutionId` and `correlationId` into MDC on the executing thread. However, because batches may run in parallel, use async task executors, or partition work, MDC does not propagate automatically across threads. Explicitly propagate context via appropriate executor/tracing mechanisms.

## 11. Storage, Security, and Metadata Access Control

The `BATCH_*` tables may contain `JobParameters`, exception messages, contexts, and resource names. They can inadvertently expose internal paths, customer IDs, query strings, or payloads if applications write them carelessly.

### 11.1. Minimizing Sensitive Data

- Never place passwords, secrets, access tokens, or unnecessary personal data in `JobParameters`, `ExecutionContext`, or `EXIT_MESSAGE`.
- Record `recordKey`/reference codes or tokens instead of entire failing payloads.
- Redact stack traces and error messages before surfacing them to unauthorized users.
- Classify audit data and enforce role-based access: operators view statuses, auditors view periods and outcomes, and engineers view detailed stack traces as authorized.

### 11.2. Retention Rules

Do not treat Spring Batch metadata as permanent archival storage. `JobRepository` grows with every run, step, and context; keeping it forever slows queries and inflates backup costs. Conversely, purging metadata too early can strip unfinished jobs of restartability or erase investigative evidence.

A sound policy distinguishes:

1. **Active data still needing restartability:** keep repository and context intact until the business lifecycle completes.
2. **Operational history metadata:** retain per operational SLAs and housekeeping policies, extracting summary reports before cleanup if needed.
3. **Audit trails and artifacts under retention mandates:** store in a dedicated repository with appropriate permissions, retention, backups, and integrity verification.

Exact retention periods depend on legal, contractual, and organizational requirements; no single number of days or months fits all batches. When purging data, use procedures designed for the relationships among job instances, executions, steps, and contexts; avoid ad-hoc `DELETE` SQL statements on an active repository.

### 11.3. Reliability of the Audit Trail

For systems requiring high assurance, apply:

- Append-only write permissions at the application layer and separation of read, write, and admin privileges.
- Durable event storage, periodic backups, and recovery drills.
- `eventVersion` and `schemaVersion` fields for controlled evolution of the audit contract.
- Hashes/signatures or immutable-policy storage when tamper detection is required.
- Periodic reconciliation among audit events, JobRepository, and business data.

These safeguards must be designed as part of the architecture, because simply adding a `createdAt` column or a listener does not produce tamper-evident audit proof.

## 12. Detecting Missing Metadata or Inconsistent States

Not every failure ends cleanly with `BatchStatus.FAILED` written to the repository. A process may lose power or be killed while an execution is `STARTED`; the `afterJob` audit callback never ran, and `END_TIME` was never updated.

A periodic **reconciliation process** should:

1. List the data periods expected to run according to business schedules or the scheduler.
2. Check whether each period has a `JobInstance`/`JobExecution`.
3. Inspect executions exceeding expected runtime that remain `STARTED`/`STARTING`, alongside actual process/worker health.
4. Cross-check `JOB_FINISHED` audit events and output manifests; spot missing events, unpublished files, or mismatched target data.
5. Raise alerts or manual reconciliation tasks; restart/rerun only under approved policies.

Example report:

| Data period | Latest JobExecution | Audit event | Output | Conclusion |
| --- | --- | --- | --- | --- |
| 2026-11-14 | `COMPLETED` | `JOB_FINISHED` present | Valid manifest | Reconciled |
| 2026-11-15 | `FAILED` | `JOB_FINISHED` present | Not published | Needs restart or error handling |
| 2026-11-16 | `STARTED` past SLA | No final event | Unknown | Check worker; do not assume failed |
| 2026-11-17 | No execution | None | None | Possible missed trigger/scheduler |

**Never manually flip `BATCH_JOB_EXECUTION.STATUS` to `FAILED` just to "clean up a monitoring screen."** Spring Batch has its own operational mechanisms and APIs; any metadata recovery must evaluate impacts on restarts.

## 13. Testing Metadata and Auditing

For auditing, unit-testing event formatting alone is insufficient. You need integration tests proving that data is persisted durably and linked to the right execution.

### 13.1. Unit Tests

Verify audit payload construction from mock or fixture `JobExecution`/`StepExecution` objects—for example, confirming `businessDate`, `jobExecutionId`, `readCount`, `writeCount`, `skipCount`, `status`, and the idempotent event ID are computed properly.

Unit tests are fast and ideal for covering missing `JobParameters`, itemless steps, or custom exit codes. They do not prove SQL transactions or that listeners are wired onto the real job.

### 13.2. Integration Tests

Run a real job/step against a test database, then verify:

- `JobExecution` and `StepExecution` exist in `JobRepository` with the expected IDs and statuses.
- `batch_audit_event` contains the matching `job_execution_id`, `event_type`, and post-callback outcomes.
- Business tables/output files contain the expected fixture data.
- When the job is `FAILED`, auditing records the failure status; on restart, each `JobExecution` leaves its own trail and links back to the same business period.
- Duplicate writes of the same logical event are handled idempotently as designed.
- If the audit service is temporarily unavailable, the system detects and handles missing audits as specified.

Example assertion after an integration test using `JdbcTemplate` and the `execution` variable from Spring Batch 5.x `JobLauncherTestUtils`:

```java
Long auditRows = jdbcTemplate.queryForObject(
    """
    SELECT COUNT(*)
      FROM batch_audit_event
     WHERE job_execution_id = ?
       AND event_type = 'JOB_FINISHED'
    """,
    Long.class,
    execution.getId()
);

assertThat(auditRows).isEqualTo(1L);
```

For tests needing content verification, also query `batch_status`, `business_date`, `read_count`, `write_count`, and `skip_count` rather than only counting events. Test repositories must live in a dedicated test database, never production data. When testing restarts, preserve metadata and output across attempts of the same test case and clean up afterward.

## 14. Common Audit Design Mistakes

| Symptom | Root issue | Remediation |
| --- | --- | --- |
| Storing only `COMPLETED` and runtime | Missing data period, input source, and accepted output | Record business keys, input/output manifests, and execution IDs |
| Using `ExecutionContext` as an action log | Context is a restart snapshot and gets overwritten | Write events to a dedicated audit store |
| Attaching a new identifying UUID on every restart | Creates a new `JobInstance`, breaking linkage and risking duplicates | Design identifying parameters by period and use real restarts |
| Assuming `WRITE_COUNT` equals target-confirmed transactions | Counter reflects only writer/framework logic | Reconcile against database, output, or external acknowledgments |
| Writing audits solely in `afterJob` | Crashes skip the callback | Add reconciliation, commit-point events, or an outbox as needed |
| Swallowing exceptions when writing audits | Missing trails with nobody noticing | Define alert/retry/reconciliation policies or fail per requirements |
| Storing full error payloads and tokens in context | Data exposure risk through metadata/logs | Minimize data, redact, and enforce access control |
| Deleting metadata immediately after a job | Loses history and restartability | Separate operational retention from audit retention and keep needed data |
| Treating long-lived `STARTED` as proof the job is alive | Process may have died without updating status | Check heartbeats, workers, and reconciliation |
| Summing read counts across steps as "unique records" | The same item may be read multiple times across steps | Measure business metrics at appropriate data boundaries |
| Logging audits without correlation IDs | Hard to connect scheduler, worker, API, and batch execution | Propagate business key + execution ID + correlation ID end-to-end |
| Querying the wrong version's schema directly | Column names and parameter schemas vary across major versions | Use `JobExplorer` or version-matched DDL |

## 15. Sample Audit Record for a Batch Execution

A readable audit report is usually not a raw dump of technical tables, but a consolidated record traceable back to source data:

```text
Job                     : importPaymentsJob
Business date           : 2026-11-16
Region                  : HCM
Source system           : bank-feed
Source object           : payments/2026-11-16/input.csv (version v-1024)
Source checksum         : sha256:<actual-hash-value>

Job instance ID         : 302
Job execution ID        : 519
Trigger                 : nightly-scheduler
Correlation ID          : import-payments-20261116-hcm
Started at              : 2026-11-16T19:00:01Z
Finished at             : 2026-11-16T19:05:31Z
Batch status            : COMPLETED
Exit code               : COMPLETED

Read count              : 10000
Write count             : 9988
Filter count            : 10
Process skip count      : 2

Business accepted count : 9988
Business rejected count : 12
Output manifest         : settlement-20261116-hcm-v1
Audit event             : job-519-finished
Audit reconciliation    : VERIFIED
```

Values only illustrate report formatting. In real systems, fields like `Business accepted count`, `Output manifest`, or `Audit reconciliation` must be **computed/reconciled from business data**, never assumed from `BatchStatus`. For example, `filterCount` and skip counts reflect two different mechanisms; business-rejected counts must be explicitly defined and may not equal the sum of those two counters in every job.

A properly linked record lets investigators jump from a business period to `JobExecution`, inspect each `StepExecution`, verify source/output files, and confirm why a restart or backfill was performed.

## 16. Guiding Principles

1. **Use Spring Batch metadata for execution history and restartability.** The primary source is `JobRepository`, not custom logs acting as a complete replacement.
2. **Attach business keys to metadata properly.** `businessDate`, `region`, input version, and job identity must stay consistent across runs.
3. **Never confuse counters with reconciled business outcomes.** Result audits must rely on actual data, manifests, and target-system acknowledgments.
4. **Record audit events outside `BATCH_*` tables when an independent business history is needed.** Use listeners for lifecycle events; use commit-point events or outboxes for high-assurance business side effects.
5. **Design for failures and crashes.** Include idempotency, access control, retention, and reconciliation to catch missing audit events.
6. **Keep enough information for traceability without leaking sensitive data.** Prefer reference keys, error codes, and checksums over unnecessary payloads.

When structured properly, audit metadata transforms a batch run from a bare `COMPLETED`/`FAILED` status into verifiable history: **which data was processed, by which program version, through which steps, what outcomes were recorded, and what remains to be reconciled**.

## References

- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): tables and relationships storing `JobInstance`, `JobExecution`, `StepExecution`, parameters, and contexts.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): job definitions, listeners, and lifecycle components.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): repository mechanisms and execution metadata management.
- [Spring Batch Reference — JobExplorer](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): Batch metadata query APIs.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): distinguishing execution monitoring from runtime signals.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries and `@Transactional`.

# Recovery via Retry or Restart in Spring Batch

## 1. Goal

A batch job can read millions of records, write data in chunks, and run for hours. Along the way, database timeouts, API disconnects, transaction locks, interrupted files, or invalid business data can occur. If every failure forced the entire job to start over from scratch, processing costs would soar and duplicate writes would threaten correctness. Yet retrying forever ties up resources, amplifies failures, and misses deadlines.

**Failure recovery in Spring Batch** is the practice of recovering at the right level: retrying an operation within the same execution, intentionally skipping a bad record, or restarting a job from saved checkpoints after a prior run failed.

This lesson—"Recovery via Retry or Restart"—belongs to the *Failure recovery* group of *Spring Batch Core Processing*, helping you:

- Understand boundaries between **retry**, **restart**, **skip**, and **launching a new JobInstance**.
- Decide which errors should retry in-step versus failing the job for controlled restart.
- Configure retry limits, backoff, exception classification, and listeners in chunk-oriented steps.
- Use `JobRepository`, `JobParameters`, and `ExecutionContext` to restart the same JobInstance.
- Design restartable and idempotent readers/writers that never double business effects.
- Test successful retries, exhausted retries, restarts after failures, already-completed jobs, and mutated inputs.
- Determine final job outcomes from persisted metadata rather than inferring from exception logs alone.

Examples use Java 17+, Spring Boot 3.x, Spring Batch 5.x, and JUnit 5. On other Spring Batch versions, configuration APIs may differ, yet principles of JobInstance identity, metadata, transactions, and idempotency remain foundational.

## 2. How Retry, Restart, and Recovery Differ

Errors can be handled at several levels:

| Mechanism | Scope | When to Use | Creates a New JobExecution? |
| --- | --- | --- | --- |
| **In-step retry** | A single read/process/write attempt inside the same JobExecution | Transient errors likely to clear quickly, e.g., network timeout | No |
| **Skip** | One item that cannot or need not be processed per policy | Invalid record permitted to be excluded from output | No |
| **Business fallback/recovery** | Alternate path designed by the application | Route record to manual review queue or valid fallback value | Usually no |
| **Restart** | A JobInstance whose previous execution did not finish successfully | Persistent issue resolved; resume from persisted state | New JobExecution in the same JobInstance |
| **New instance** | A new business period or uniquely identified run | Processing another date, file, or data version | New JobInstance and new JobExecution |

Overall flow:

```text
                   Running JobExecution
                            |
                            v
                   Step read/process/write
                            |
                         Exception?
                       /            \
                     No              Yes
                      |               |
                      v               v
                Continue chunk   Retry policy?
                                    /       \
                                  Yes        No
                                  |           |
                                  v           v
                                Retry    Skip/fallback?
                                /   \       /       \
                           Success Still  Yes        No
                              |    fails   |          |
                              |      |     v          v
                              |    Retry  Skip or   Step FAILED
                              |   exhaust recovery       |
                              |      |                   v
                              +------+--------------  Job FAILED
                                                         |
                                               Fix root cause
                                                         |
                                                         v
                                             Restart with same identity
                                                         |
                                                         v
                                                New JobExecution
```

The diagram illustrates the concept. In Spring Batch, exact retry/skip behavior also depends on whether the exception was thrown in the reader, processor, or writer, whether the transaction rolled back, and fault-tolerance settings.

A **successful retry** can leave the job `COMPLETED` despite transient error logs. A **successful restart** means a JobInstance had at least one prior incomplete JobExecution and a subsequent execution completed.

## 3. When to Retry vs. When to Restart

Classify failures by **short-term self-recoverability**, **safety of repeating the operation**, and **resource holding cost**.

| Failure Scenario | Typical Suitable Approach | Reason |
| --- | --- | --- |
| HTTP 503, brief network blip | Bounded retry with backoff | Service likely recovers in seconds |
| Deadlock or transient DB error | Bounded transaction/chunk retry | Often succeeds once contention clears |
| API returning HTTP 429 | Retry within limits/wait window if API contract allows | Avoids adding overload |
| Missing required column in file | Fail fast or skip per policy | Retrying identical data cannot fix schema |
| Negative amount in record | Skip/reject with reporting if business permits | Invalid data, not a transient glitch |
| Missing credentials or bad config | Fail and fix config before restarting | Rapid retries are futile |
| Extended database outage | Fail job after bounded retries, then restart | Do not tie up workers indefinitely waiting on infra |
| Abrupt JVM/container termination | Reconcile metadata and controlled restart | Old process may not have persisted terminal status |
| Partial external write then timeout | Check idempotency and target state before retrying | Response timeout does not prove the action failed |

**Core rule:** retries and restarts are safe only when re-execution never produces wrong outcomes. If a writer calls a debit API, sends emails, or publishes events, establish idempotency, business keys, or reconciliation before permitting retries.

Never treat retry as a universal cure for every `Exception`. A `NumberFormatException` from bad data will fail identically on every retry over the same input.

## 4. Metadata Determines Restartability

Spring Batch stores state via `JobRepository`. Key concepts:

- `Job`: job definition, e.g., `importPaymentsJob`.
- `JobParameters`: runtime inputs; some parameters are **identifying**.
- `JobInstance`: Job name combined with identifying parameters.
- `JobExecution`: a single attempt to execute a JobInstance.
- `StepExecution`: state of one step within a JobExecution.
- `ExecutionContext`: checkpoint state needed for restarts.

Example:

```text
Job: importPaymentsJob

JobInstance ID=1201
  identifying: businessDate=2026-11-15
     |
     +-- JobExecution ID=9001: FAILED
     |      validateStep: COMPLETED
     |      persistStep: FAILED
     |
     +-- JobExecution ID=9002: COMPLETED
            validateStep: typically skipped on restart
            persistStep: reruns from saved state

JobInstance ID=1202
  identifying: businessDate=2026-11-16
     |
     +-- JobExecution ID=9003: COMPLETED
```

One JobInstance can have multiple JobExecutions through restarts, yet once a JobInstance is `COMPLETED`, requesting it again with **the same identifying parameters** is normally rejected with `JobInstanceAlreadyCompleteException`.

### Identifying vs. Non-Identifying Parameters

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
```

`businessDate` identifies the instance; `requestedBy` is strictly for tracing. If you alter `businessDate` or add a random identifying timestamp on the second run, you request **a different instance**, not a restart of the old one.

A common mistake:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
```

Under standard `JobParametersBuilder` usage, added parameters default to identifying. A changing `run.id` turns each launch into a new JobInstance, risking duplicate processing for the same day.

## 5. Configuring Retry in a Chunk-Oriented Step

Suppose a job reads payment data, a processor normalizes records, and a writer persists to a database. Selected transient data-access errors may retry.

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step paymentStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentRow> reader,
        ItemProcessor<PaymentRow, AcceptedPayment> processor,
        ItemWriter<AcceptedPayment> writer) {

    return new StepBuilder("paymentStep", repository)
        .<PaymentRow, AcceptedPayment>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
```

This assumes `PaymentRow`, `AcceptedPayment`, and Reader/Processor/Writer beans are defined. Step names and JobRepository wiring follow Spring Batch 5.x APIs.

Meaning:

- `chunk(100, transactionManager)` processes chunks of up to 100 items using the configured transaction manager.
- `faultTolerant()` enables skip/retry support on the step builder.
- `retry(TransientDataAccessException.class)` declares retryable exceptions.
- `retryLimit(3)` bounds attempts under the step's RetryPolicy; verify exact call counts in tests for your chosen policy and framework version.
- If retries exhaust without a fallback/skip policy, the step typically transitions to `FAILED`.

### Retrying Read, Process, and Write Are Not Identical

| Phase | Failure Point | Risk to Watch |
| --- | --- | --- |
| `read()` | Connection/parse/source query | Post-rollback re-reads may occur; reader must maintain accurate position |
| `process()` | Validation, API calls, transformation | An item may be passed to processor multiple times; avoid side effects |
| `write()` | SQL/HTTP/file output | Writer may have executed partial effects before throwing |

Writer retries require extra scrutiny when writing to systems **not participating in the step's transaction**. An HTTP request that timed out may already have succeeded on the server; retrying without an idempotency key can duplicate the effect.

### Never Retry Every Exception

Configuring `.retry(Exception.class)` causes data errors, programming bugs, and config errors to retry needlessly. Use it only when your application enforces a controlled exception hierarchy where every subtype in that branch is genuinely retryable.

In real systems, classify exceptions near infrastructure adapters: e.g., translate HTTP client timeouts into a custom `RemoteServiceTemporaryException`, while never lumping HTTP 400 with 503.

## 6. Backoff and Resource Limits

Immediate continuous retries can trigger a *retry storm* against a struggling target service: hundreds of workers resend requests together, blocking recovery.

Spring Retry supports backoff policies. On a fault-tolerant step, you can configure exponential backoff:

```java
import org.springframework.retry.backoff.ExponentialBackOffPolicy;

ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
backoff.setInitialInterval(500);
backoff.setMultiplier(2.0);
backoff.setMaxInterval(5_000);

Step step = new StepBuilder("paymentStep", repository)
    .<PaymentRow, AcceptedPayment>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .backOffPolicy(backoff)
    .build();
```

Intervals shown here are 500 ms, doubling by 2 up to 5 seconds. Backoff applies only when another attempt actually occurs. Align retry limits, API timeouts, worker concurrency, and job SLAs together.

In distributed setups, **jitter** (randomized wait variance) prevents all instances from retrying in lockstep. Choose a jitter-capable backoff or client-layer retry strategy; avoid spawning ad-hoc threads/Timers per item.

If a step handles multiple exception types, ensure the retry policy classifies each appropriately and caps total elapsed time. A job handling millions of items must not spend hours retrying an ongoing infrastructure outage.

## 7. Retry and Skip: Two Distinct Recovery Paths

In Spring Batch, **skip** means an item failing with an allowed exception is bypassed so the step can process remaining items. Skip does not mean retry succeeded.

Example:

```java
Step step = new StepBuilder("paymentStep", repository)
    .<PaymentRow, AcceptedPayment>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidPaymentException.class)
    .skipLimit(5)
    .build();
```

In this example:

- Transient infrastructure failures under `TransientDataAccessException` are retried.
- Business data errors (`InvalidPaymentException`) can be skipped within limits.
- Exceeding `skipLimit` fails the step.
- If the processor returns `null` to filter an item, `filterCount` increments; that is **not** a skip and does not consume the skip limit.

Decision table:

| Data / Error | Retry? | Skip? | Expected Outcome |
| --- | --- | --- | --- |
| Valid record | No | No | Processed successfully |
| Brief timeout that clears | Yes | No | Continues within same execution |
| Bad format allowed to drop | Usually no | Yes | Skip recorded, step continues |
| Prolonged network failure past retries | Bounded attempts made | By policy, usually no | Step `FAILED` |
| Bad record requiring fix | No | No | Step `FAILED`; fix source then restart per procedure |

**Business rules must be explicit:** some jobs may complete with 5 skipped bad records; financial reconciliation jobs may have to fail if a single record is wrong. Skip settings are data-completeness decisions, not just tricks to boost job pass rates.

## 8. RecoveryCallback Is Not the Job Restart Mechanism

When an operation uses `RetryTemplate` directly, Spring Retry can invoke a `RecoveryCallback` after retries exhaust:

```java
import org.springframework.retry.support.RetryTemplate;

RetryTemplate template = RetryTemplate.builder()
    .maxAttempts(3)
    .retryOn(RemoteServiceTemporaryException.class)
    .build();

String status = template.execute(
    context -> remoteClient.lookupStatus(paymentId),
    context -> {
        // Fallback option defined by the application.
        return "MANUAL_REVIEW";
    }
);
```

This assumes `remoteClient`, `paymentId`, and the domain exception exist. `"MANUAL_REVIEW"` is not a standard Spring Batch status, only an application-defined fallback value.

Calling `RetryTemplate` inside an `ItemProcessor` **already configured with Batch step retries** creates nested retries. Outer 3 attempts times inner 3 attempts can invoke an operation far more times than expected. Decide clearly which layer owns retries.

By contrast, **restart** creates a new JobExecution from persisted metadata; it does not run a Spring Retry `RecoveryCallback`. To recover an entire job after prolonged outages, use Spring Batch's restart mechanism.

## 9. Conditions for Restarting a JobInstance

A restart typically applies when:

1. The JobInstance has a prior JobExecution.
2. That prior execution ended in a restartable status, such as `FAILED` or `STOPPED`, depending on context.
3. The job is configured as restartable (the default with standard builders).
4. JobLauncher receives **the exact same Job name and identifying parameters**.
5. JobRepository metadata remains intact and consistent.
6. Readers/writers/steps can resume from committed state.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();

// First run: JobExecution 9001 may become FAILED.
JobExecution first = jobLauncher.run(importPaymentsJob, parameters);

// After fixing infrastructure failure, invoke again with the same parameters:
// Creates execution 9002 if the instance is eligible for restart.
JobExecution restarted = jobLauncher.run(importPaymentsJob, parameters);
```

In production code, inspect the prior execution status and request restarts only when appropriate. If the JobInstance already completed, the second call is rejected. If a prior execution is still running, the launcher also rejects the duplicate request.

### Common Exceptions

| Exception | Typical Meaning |
| --- | --- |
| `JobInstanceAlreadyCompleteException` | Instance already finished; cannot rerun under that identity |
| `JobExecutionAlreadyRunningException` | An execution of this instance is currently active |
| `JobRestartException` | Restart invalid, e.g., non-restartable job or ineligible status |
| `JobParametersInvalidException` | Parameters failed job validation |

Never catch these exceptions and bump `run.id` just to "make the job run." That alters instance identity and risks reprocessing the prior period's data twice.

## 10. Which Steps Rerun on Restart?

Spring Batch can skip steps that already `COMPLETED` in a prior JobExecution and rerun incomplete steps. Example two-step job:

```text
validateInputStep -> persistPaymentsStep
```

First run:

```text
JobExecution 9001: FAILED
  validateInputStep: COMPLETED
  persistPaymentsStep: FAILED
```

After restarting the same JobInstance:

```text
JobExecution 9002: COMPLETED
  validateInputStep: typically skipped
  persistPaymentsStep: reruns using step checkpoint/state
```

This saves significant work when a validation step takes 30 minutes: restarts avoid redoing completed steps unnecessarily.

### `allowStartIfComplete` and `startLimit`

If a step must rerun **even when already completed** in a prior execution, configure:

```java
Step validationStep = new StepBuilder("validateInputStep", repository)
    .tasklet(validationTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
```

Use this intentionally, e.g., when a step re-checks current preconditions or prepares resources for later steps. Never put `allowStartIfComplete(true)` on a non-idempotent write step just to "rerun everything."

`startLimit(n)` caps how many times a step may start across a JobInstance's lifecycle per framework rules. It prevents runaway step restarts, distinct from `retryLimit` for transient in-step errors.

A job can forbid restarts altogether:

```java
Job job = new JobBuilder("oneTimeImportJob", repository)
    .start(step)
    .preventRestart()
    .build();
```

The job still runs the first time for new parameters; once an execution exists and a restart is attempted, Spring Batch throws `JobRestartException`.

## 11. `ExecutionContext` and Checkpoints for Restarts

Checkpoints allow resuming from persisted state instead of always restarting at row 1. Spring Batch uses `ExecutionContext` to store recovery data such as items read, file positions, or reader-managed state.

In a chunk-oriented step, the general flow:

```text
Read 1..100   -> process/write -> commit -> save state
Read 101..200 -> process/write -> commit -> save state
Read 201..300 -> pre-commit failure -> rollback

Restart:
  resumes from last committed state,
  may re-read items belonging to the rolled-back chunk
```

Example using `FlatFileItemReader` persisting state as an `ItemStream`:

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<PaymentRow> paymentReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<PaymentRow>()
        .name("paymentCsvReader")
        .resource(new FileSystemResource(inputFile))
        .linesToSkip(1)
        .delimited()
        .names("paymentId", "amount")
        .fieldSetMapper(fieldSet -> new PaymentRow(
            fieldSet.readString("paymentId"),
            fieldSet.readBigDecimal("amount")
        ))
        .saveState(true)
        .strict(true)
        .build();
}
```

This snippet requires importing `@Bean`, `@StepScope`, `@Value`, and defining `PaymentRow`. `inputFile` comes from JobParameters; ensure the exact same source file is supplied on restart with unchanged content and line ordering unless explicitly handled.

When using standard readers, rely on built-in restartability by giving stable reader names, enabling `saveState(true)`, and using proper scope. Writing custom readers without checkpoint support can cause restarts to re-read from the beginning or drop records.

### `ExecutionContext` Is Not for Holding Whole Datasets

Store only compact state needed for recovery, such as offsets, file positions, or the last committed key:

```java
executionContext.putLong("lastCommittedId", lastId);
executionContext.putString("sourceFileKey", fileKey);
```

Never store lists of millions of items in `ExecutionContext`. Doing so strains heap/serialization and slows down the metadata repository.

More importantly, a custom `lastCommittedId` works only if source ordering stays stable and checkpoints persist atomically with commits. If source ordering shifts, a naive "read after ID" query can miss new rows or write duplicates.

## 12. Transactions, Rollbacks, and External Side Effects

A chunk reads and processes multiple items, invokes the writer, and commits a transaction. When a pre-commit error strikes, the database transaction rolls back; on retry or restart, items in that chunk may execute again.

Example:

```text
Chunk 1: items 1..100
  DB write -> COMMIT

Chunk 2: items 101..200
  Partial DB write -> failure
  DB transaction -> ROLLBACK

Restart:
  Chunk 1 remains committed
  Chunk 2 can be reprocessed
```

On the same datasource/transaction manager, rollbacks protect database writes made inside that transaction. However, effects on external systems (HTTP, email, non-transactional message brokers, files, or payment gateways) **do not roll back**.

### Example Duplication Risk

A writer sends a request to an external API. The API saves the payment, yet the connection times out before returning a response. Spring Batch sees an exception, retries, and sends the identical request again. If the API lacks idempotency, the payment can execute twice.

Mitigations include:

- Use a stable **idempotency key** derived from the item's business key and operation, independent of JobExecution ID.
- Write business data and an outbox row in the same DB transaction, dispatching messages post-commit.
- Enforce unique constraints on target tables, e.g., `UNIQUE(business_date, payment_id)`.
- Design APIs supporting status lookups prior to retrying.
- Reconcile external state whenever an exception leaves outcomes ambiguous.

**The goal is accurate business outcomes after any valid number of retries or restarts.** Spring Batch manages step metadata and transactions, not universal exactly-once guarantees across external systems.

### Never Use JobExecution ID as an Idempotency Key

Restarts assign a new JobExecution ID to the same JobInstance. Using execution ID to track whether a payment happened makes restarts look like "brand-new requests" to external systems.

Idempotency keys should derive from business entities such as `paymentId` plus operation type/period per the target system's contract.

## 13. Recovery After Abrupt JVM or Container Termination

If a step throws an exception while the process stays alive, Spring Batch usually updates metadata to `FAILED`. Yet if the JVM is forcibly killed or loses repository connectivity mid-run, metadata may stay `STARTED` or `STARTING`.

Calling `JobLauncher.run(...)` immediately afterward can throw `JobExecutionAlreadyRunningException` because the repository still thinks the previous execution is active.

This is never a reason to wipe or hack metadata arbitrarily. Recovery requires:

1. Confirming the old execution is genuinely dead on all nodes.
2. Inspecting JobExecution/StepExecution, transactions, logs, and target data state.
3. Following supported operational procedures to resolve the stale execution and determine restart eligibility.
4. Verifying checkpoints and out-of-transaction effects.
5. Triggering restart with the same identifying parameters.
6. Monitoring terminal status and reconciling business totals.

Spring Batch provides APIs such as `JobOperator` and metadata via `JobExplorer` for operations, though crashes must be handled according to your version and deployment model. Never run ad-hoc SQL updates against `BATCH_JOB_EXECUTION`/`BATCH_STEP_EXECUTION` to force a rerun without a verified recovery procedure.

### Scheduler Recovery vs. Step Recovery

A scheduler may periodically trigger unfinished JobInstances. Retrying blindly on failure without classifying root causes creates infinite restart loops:

```text
Scheduler fires trigger D
       |
       v
JobExecution FAILED
       |
       v
Scheduler retries immediately with D
       |
       v
JobExecution FAILED
       |
       +--> infinite loop, wastes resources
```

Enforce max restart counts, cooldown intervals, error classification, and operator escalation when auto-recovery cannot succeed. For config errors or deterministically invalid data, restart only after fixing the root cause.

## 14. Logs and Metrics to Confirm Recovery Truly Succeeded

A solid system distinguishes **attempt failed** from **job ultimately failed**.

Signals to track:

| Category | Fields |
| --- | --- |
| Identity | Job name, JobInstance ID, JobExecution ID, businessDate |
| Retry | Step, phase READ/PROCESS/WRITE, exception type, failed attempt count |
| Skip | Read/process/write skip counts, data reason codes |
| Transaction | Commit count, rollback count |
| Step outcome | `BatchStatus` and `ExitStatus` of StepExecution |
| Job outcome | `BatchStatus`, `ExitStatus`, start/end timestamps |
| Restart | New execution linked under the same JobInstance as the old execution |
| Business | Output record counts, monetary totals, idempotency keys, reconciliation gaps |

`RetryListener` can log per-attempt errors; `SkipListener` logs items actually skipped; `StepExecutionListener` and `JobExecutionListener` log terminal outcomes.

**Do not count exception log lines as failed business records.** One item can throw multiple times across retries or replay after rollback/restart. To count excluded items, use skip counters, reject tables, and business reconciliation.

Illustrative log sequence:

```text
WARN event=batch.retry.error jobExecutionId=9001 step=paymentStep retryFailureCount=1 exceptionType=TransientDataAccessResourceException

WARN event=batch.retry.error jobExecutionId=9001 step=paymentStep retryFailureCount=2 exceptionType=TransientDataAccessResourceException

INFO event=batch.step.finished jobExecutionId=9001 step=paymentStep status=COMPLETED readCount=1000 writeCount=1000 skipCount=0

INFO event=batch.job.finished jobInstanceId=1201 jobExecutionId=9001 status=COMPLETED
```

The initial `WARN` lines do not mean the job failed. The final status confirms retries allowed execution to finish.

When a step genuinely becomes `FAILED`, log the cause and correlation ID without flooding thousands of duplicate stack traces. Avoid logging tokens, PII, payment payloads, or full `JobParameters` unnecessarily.

## 15. Integration Example: Restarting After a Step Failure

The example below uses a two-step job:

1. `validateStep` always succeeds and counts invocations.
2. `persistStep` can be configured to fail once and then succeed.

The test proves restart creates **a new JobExecution under the same JobInstance** and skips the already `COMPLETED` step by default.

Test dependencies with Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-batch'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.batch:spring-batch-test'
testRuntimeOnly 'com.h2database:h2'
```

JUnit 5 integration test:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
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
    classes = RestartIntegrationTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:restart_test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
    }
)
class RestartIntegrationTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    private JobExplorer jobExplorer;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("recoveryDemoJob")
    private Job job;

    @Autowired
    @Qualifier("validationCalls")
    private AtomicInteger validationCalls;

    @Autowired
    @Qualifier("persistCalls")
    private AtomicInteger persistCalls;

    @Autowired
    private AtomicBoolean failNextPersist;

    @BeforeEach
    void reset() {
        repositoryTestUtils.removeJobExecutions();
        validationCalls.set(0);
        persistCalls.set(0);
        failNextPersist.set(false);
    }

    @Test
    void restartKeepsInstanceAndSkipsCompletedStep()
            throws Exception {

        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

        // First run: validate succeeds, persist fails.
        failNextPersist.set(true);
        JobExecution first = jobLauncher.run(job, parameters);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(1, validationCalls.get());
        assertEquals(1, persistCalls.get());

        // Second run: restart same JobInstance.
        JobExecution second = jobLauncher.run(job, parameters);

        assertEquals(BatchStatus.COMPLETED, second.getStatus());

        assertEquals(
            first.getJobInstance().getInstanceId(),
            second.getJobInstance().getInstanceId()
        );
        assertNotEquals(first.getId(), second.getId());

        // validateStep already COMPLETED so skipped by default.
        assertEquals(1, validationCalls.get());

        // persistStep failed in first execution, reruns in next execution.
        assertEquals(2, persistCalls.get());

        assertEquals(
            2,
            jobExplorer.getJobExecutions(
                second.getJobInstance()
            ).size()
        );
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean("validationCalls")
        AtomicInteger validationCalls() {
            return new AtomicInteger();
        }

        @Bean("persistCalls")
        AtomicInteger persistCalls() {
            return new AtomicInteger();
        }

        @Bean
        AtomicBoolean failNextPersist() {
            return new AtomicBoolean(false);
        }

        @Bean
        Step validateStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("validationCalls")
                    AtomicInteger validationCalls) {

            return new StepBuilder("validateStep", repository)
                .tasklet((contribution, context) -> {
                    validationCalls.incrementAndGet();
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean
        Step persistStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("persistCalls")
                    AtomicInteger persistCalls,
                AtomicBoolean failNextPersist) {

            return new StepBuilder("persistStep", repository)
                .tasklet((contribution, context) -> {
                    persistCalls.incrementAndGet();

                    if (failNextPersist.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Simulated transient failure"
                        );
                    }

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean("recoveryDemoJob")
        Job recoveryDemoJob(
                JobRepository repository,
                @Qualifier("validateStep") Step validateStep,
                @Qualifier("persistStep") Step persistStep) {

            return new JobBuilder("recoveryDemoJob", repository)
                .start(validateStep)
                .next(persistStep)
                .build();
        }
    }
}
```

The test uses `AtomicBoolean` strictly for **test fault control**, not as a production recovery strategy. Real project jobs implement business logic in readers/processors/writers/tasklets with proper transactions and idempotency.

Here, the first run ends with `JobExecution FAILED`, the second ends `COMPLETED`, the JobInstance ID stays unchanged, and `validateStep` does not re-execute. The contrast between **retry** and **restart** is clear: the test creates two separate JobExecutions rather than retrying one operation inside a single execution.

## 16. Testing Retry with Controlled Transient Errors

For chunk-step retries, a test can use `AtomicInteger` to count dependency invocations.

Illustrative processor calling a simulated service:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.dao.TransientDataAccessResourceException;

AtomicInteger calls = new AtomicInteger();

ItemProcessor<PaymentRow, PaymentRow> flakyProcessor = item -> {
    int attempt = calls.incrementAndGet();

    if (attempt == 1) {
        throw new TransientDataAccessResourceException(
            "Temporary database outage"
        );
    }

    return item;
};
```

When paired with a fault-tolerant step having `.retry(TransientDataAccessException.class)` and a suitable limit, tests should verify:

- Final JobExecution is `COMPLETED`.
- The dependency was re-invoked after failing.
- Output item was written once per business contract.
- Zero items were skipped when retry succeeded.
- Metadata reflects read/write counts per framework rules.
- No second JobExecution was created solely for an in-step retry.

If the step processes multiple items, a shared `AtomicInteger` measures only total calls; to track per-item attempts, key by business ID or use a single-item fixture to avoid ambiguity.

A companion test where the dependency **always throws** verifies exhausted retries transition the step to `FAILED`. Avoid guessing exact invocation counts in assertions when retry policies, rollbacks, or readers can alter attempt counts; assert against your concrete configuration.

## 17. Recovery Test Matrix

| Scenario | Setup | Core Assertions |
| --- | --- | --- |
| Zero errors | Reader/processor/writer succeed | `COMPLETED`, accurate output, no restart |
| Single transient error | Dependency fails once then succeeds | Retry within same JobExecution, zero duplicates |
| Persistent transient error | Dependency always throws retryable error | Retries exhaust, Step/Job `FAILED` |
| Non-retryable error | Exception outside retry policy | No fruitless retries, expected status |
| Invalid record skipped | `skip(InvalidPaymentException.class)` configured | Skip count increments, valid records still write |
| Skip limit exceeded | More errors than `skipLimit` | Step `FAILED`, committed chunks intact |
| Restart after `FAILED` | Reuse identifying parameters | JobInstance ID unchanged, new JobExecution ID |
| Prior step completed | Multi-step job, final step fails | Prior `COMPLETED` step typically skipped |
| `allowStartIfComplete(true)` | Step intentionally set to rerun | Completed step starts per config |
| `preventRestart()` job | Fails then relaunched for same instance | Restart rejected |
| `COMPLETED` instance | Relaunched with same identifying parameters | `JobInstanceAlreadyCompleteException` |
| Running execution | Duplicate trigger mid-run | `JobExecutionAlreadyRunningException` |
| Restart with mutated source file | File/ordering altered between runs | Test catches missing/duplicate rows; enforce immutable sources |
| Sudden container kill | Metadata not updated to `FAILED` | Controlled reconciliation procedure, no ad-hoc SQL hacks |
| API processed yet response timed out | Writer calls external service | Idempotency key prevents duplicate effects |

When testing concurrent executions, use coordination signals such as `CountDownLatch` to confirm the first job is genuinely active before triggering the second, avoiding fragile `Thread.sleep` guesses.

## 18. Common Mistakes When Implementing Recovery

| Symptom | Common Cause | Remedy |
| --- | --- | --- |
| Every restart creates a new JobInstance | `run.id`/timestamp is identifying | Keep business identifying keys stable |
| Job succeeded yet keeps getting rerun | Confusing restart with reprocess | Build a separate reprocessing flow for completed instances |
| Retries thousands of times then still fails | Non-self-healing exception or huge limit | Classify errors, add backoff, cap retries |
| API called twice after timeout | Out-of-transaction side effect lacking idempotency | Idempotency keys and target reconciliation |
| Restart re-reads entire file | Reader lacks checkpoints or misconfigured state | Use ItemStream, saveState, stable reader names |
| Restart drops records | Input/sort order changed after checkpoint | Use immutable source snapshots and stable sort keys |
| Completed step writes data again | Misplaced `allowStartIfComplete(true)` | Review step restart policy and writer idempotency |
| Old step stays `STARTED` after crash | Process died before persisting metadata | Verify execution is dead; follow operational procedure |
| Using `System.out` to judge success | Logs are not authoritative terminal state | Query JobExecution, StepExecution, and target data |
| Retry error logs appear on `COMPLETED` job | Error succeeded on retry | Separate attempt errors from terminal outcomes |
| Retries exhaust yet job hangs | Client layer lacks timeouts | Enforce network/DB timeouts and bounded retries |
| Both RetryTemplate and Batch retry | Nested retry layers | Assign one retry layer; count combined attempts |
| Restart succeeds yet output doubles | Non-idempotent writer, rollback misses external systems | Unique keys, outbox, transactions/compensation |
| Deleting metadata to "start fresh" | Destroys JobInstance state/checkpoints | Preserve metadata and manage reprocessing separately |
| Tests pass alone yet fail in suite | Shared DB metadata and fixtures unisolated | Isolate schemas/DBs or clean state deterministically |

## 19. Decision Workflow for a Real Failure

Suppose `paymentImportJob` is processing 2 million transactions and hits a writer timeout after committing 900,000 transactions. Operations must decide how to recover.

**Step 1 — Determine actual state:** read JobExecution, StepExecution, error timestamps, and checkpoint metadata. Never rely on a single `ERROR` log line.

**Step 2 — Classify the failure:** is the timeout transient or is the API down long-term? Is retrying safe? Might the write have succeeded before timing out?

**Step 3 — Inspect transactions and checkpoints:** which database holds the 900,000 committed items? Did the last chunk roll back? Are there out-of-transaction external side effects?

**Step 4 — Verify idempotency:** do business keys block duplicates? Can the writer safely rewrite a rolled-back chunk? Are outboxes or idempotency tokens in place?

**Step 5 — Choose retry or restart:** brief glitches can be resolved by in-step retries during the active run; if the job became `FAILED`, fix infrastructure and restart with the same identifying parameters.

**Step 6 — Verify final output:** confirm the JobInstance has a new `COMPLETED` execution, target row counts, totals, and error counts match expectations. If completed data must be reprocessed, use a separate audited workflow with replacement semantics.

**Step 7 — Add preventive controls:** tune retry policies, timeouts, backoff, alerts, or source immutability checks so future failures recover cleanly.

Recovery succeeds only when **business output is accurate and execution history is traceable**, not merely when exceptions stop appearing in logs.

## 20. Practice Exercises

Build a job `dailySettlementJob` with two steps: `validateFileStep` and `persistSettlementStep`.

Requirements:

1. The first step validates the source file, computes its checksum, and persists source metadata so restarts can confirm the file did not change.
2. The second step uses chunk size 50, reads payments, and writes results to an H2 table with a unique constraint on `businessDate + paymentId`.
3. Simulate a transient DB failure on one item and configure bounded retry/backoff so the job still completes.
4. Simulate a prolonged DB outage so the first execution becomes `FAILED`; after fixing it, restart with the same `businessDate` and verify `JobInstance` stays unchanged.
5. Supply one invalid data record. Choose an explicit skip or fail policy, then verify read/write/skip counts.
6. Fail `persistSettlementStep` mid-chunk and verify target row counts before and after restart with zero duplicates.
7. Trigger another run once the instance is `COMPLETED` and explain the resulting exception.
8. Change `businessDate` to another period to confirm a new instance is created as intended by business semantics.

In your test report, explicitly note which cases used **in-step retry**, **skip**, **restarting an old instance**, or **creating a new instance**. The same exception can demand different strategies depending on transactions, side effects, and SLAs.

## 21. Conclusion

**Retry** handles fast-recovering errors within one step/execution; **restart** resumes a JobInstance after an incomplete prior run via a new JobExecution and persisted checkpoints. Spring Batch provides `JobRepository`, `ExecutionContext`, fault-tolerant chunks, skip/retry policies, and listeners to implement both.

A dependable recovery strategy classifies errors, caps attempt counts, bounds wait times, protects transactions and idempotency, keeps identifying parameters stable on restarts, and verifies target output after every recovery. When those pieces are explicit, batch jobs survive transient infrastructure glitches and recover from outages without trading away data correctness.

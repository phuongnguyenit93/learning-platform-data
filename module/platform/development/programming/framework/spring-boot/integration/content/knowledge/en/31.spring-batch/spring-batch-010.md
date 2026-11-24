# Skip, Retry, and Distinguishing Data Errors from System Errors

A Spring Batch job importing 500,000 CSV lines may encounter a few malformed rows, a database deadlock, or a dropped connection to a partner API. Those three failures demand three distinct responses: **skip** the bad record if the contract allows, **retry** a transiently failed operation if safe, and **fail** the job when the system cannot guarantee correct results. Treating infrastructure failures like bad records allows a job to report completion while dropping most of the dataset.

This lesson belongs to the **Spring Batch** chapter in **SPRING_BOOT_INTEGRATION**. Within Spring Boot integration across HTTP clients, databases, caches, message brokers, and Spring Integration adapters, it focuses on configuration management, data contracts, transactions, error classification, deduplication, testing, and observability for production batch flows.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish permanent data errors, transient system errors, configuration errors, and indeterminate outcomes.
2. Describe how errors in **ItemReader**, **ItemProcessor**, and **ItemWriter** impact chunks, transactions, skips, and retries.
3. Configure Spring Batch 5.x with **faultTolerant**, **skipLimit**, **retryLimit**, skip listeners, and rollback policies.
4. Design quarantine, idempotency, checkpoints, and restarts so jobs recover without losing or duplicating data.
5. Test skip thresholds, exhausted retries, deadlocks, timeouts after side effects, and crash recovery.
6. Interpret JobExecution/StepExecution metrics accurately to assess data quality and ingestion reliability.

## 2. Foundation: Chunk-Oriented Processing

In Spring Batch, a **Job** contains one or more **Steps**. In a chunk-oriented step, the framework reads items from an **ItemReader**, transforms/validates them via an **ItemProcessor**, batches outputs, and invokes an **ItemWriter**. A transaction typically wraps processing of one chunk, covering resources capable of joining the declared transaction manager.

~~~mermaid
flowchart TD
    J["Job / Step"] --> R["ItemReader.read()"]
    R -->|Item returned| P["ItemProcessor.process()"]
    R -->|null: end of data| FINISH["Complete step when conditions met"]
    P -->|Returns item| B["Accumulate chunk"]
    P -->|Returns null| FILTER["Filter: not a skip"]
    B --> W["ItemWriter.write(chunk)"]
    W --> TX["Commit transaction / save checkpoint"]
    TX --> R
    R -->|Exception| C["Classify failure"]
    P -->|Exception| C
    W -->|Exception| C
    C --> D{"Safe to continue?"}
    D -->|Bounded retry| RETRY["Retry with backoff"]
    D -->|Skip within budget| SKIP["Drop item + record error"]
    D -->|No| FAIL["Step FAILED / Job FAILED"]
~~~

This diagram shows the conceptual decision flow. In practice, writer failures can trigger rollbacks and partial chunk reprocessing, while reader resumption depends on reader type and saved state. **Skip** and **retry** do not promise exactly-once guarantees.

### 2.1. Terms That Must Be Kept Distinct

| Term | Meaning | Example |
|---|---|---|
| **Filter** | Processor returns **null** to intentionally omit an item from output; not an error | Record outside the requested sync time window |
| **Skip** | Bypass an item whose exception is declared acceptable | A CSV row with an unparseable date format |
| **Retry** | Re-attempt an operation due to a potentially recoverable error | Temporary DB deadlock |
| **Rollback** | Undo effects of an uncommitted transaction | Writer fails while persisting a chunk |
| **Fail** | Halt step/job when the contract can no longer be honored | Bad schema, DB auth failure, bad-record threshold exceeded |
| **Quarantine** | Store traces of failed items for investigation, repair, and re-ingestion | A `rejected_records` table recording source, locator, and reason |
| **Restart** | Resume a failed JobInstance using persisted state | Continue reading a file from the last committed checkpoint |

Returning **null** in `ItemProcessor` increments **filterCount**, not **processSkipCount**. Deliberately returning null on bad data to avoid hitting the skip limit silently hides data loss.

### 2.2. Key Metrics

**StepExecution** tracks counters including **readCount**, **writeCount**, **filterCount**, **readSkipCount**, **processSkipCount**, **writeSkipCount**, **commitCount**, and **rollbackCount**. They measure different processing stages. Never treat `rollbackCount` as a retry count: rollbacks arise from multiple causes, and items may re-execute after rollback.

## 3. Classifying Errors by Cause and Contract

| Error Category | Scenario | Recommended Policy |
|---|---|---|
| **Isolated bad data** | Invalid date, missing required field, unsupported currency | Bounded skip + quarantine **if business permits** |
| **Verified duplicate** | External ID already stored with identical content and version | Idempotent no-op or explicit filter; retain evidence |
| **Transient error** | Deadlock, lock contention, 429 throttling, recoverable 503 | Bounded retry + backoff when safe |
| **Connection/timeout error** | TCP reset, response timeout, DB connection drop | Verify side effects and safety before retrying |
| **Contract/config error** | Wrong credentials, missing DB column, broken file schema, 403 | Fail-fast; fix source or configuration |
| **Programming bug** | `NullPointerException`, bad mapping, broken invariant | Fail and fix code; never skip `RuntimeException` |
| **Systemic data corruption** | 70% of rows fail parsing because vendor changed format | Fail/hold the batch for inspection once threshold trips |
| **Indeterminate outcome** | HTTP POST succeeded remotely yet response was lost | Reconcile by request ID/idempotency key before replaying |

**Exception class name alone is not enough for a decision.** For example, `DataIntegrityViolationException` can indicate an idempotent duplicate ID—or a missing foreign key, unmigrated schema, or invalid field. Adapters should translate understood causes into specific business exceptions rather than skipping an entire database exception hierarchy.

### 3.1. Decision Tree

~~~mermaid
flowchart TD
    E["Exception in read/process/write"] --> Q{"Fault belongs to one identified item?"}
    Q -->|Yes| S{"Contract permits skip?"}
    S -->|Yes| SL{"Skip budget left?"}
    SL -->|Yes| SK["Skip + quarantine"]
    SL -->|No| F["Fail"]
    S -->|No| F
    Q -->|No / unclear| T{"Transient failure?"}
    T -->|No| F
    T -->|Yes| I{"Is retry safe/idempotent?"}
    I -->|Unclear| REC["Reconcile or stop safely"]
    I -->|Yes| L{"Retry budget left?"}
    L -->|Yes| RT["Backoff + retry"]
    L -->|No| F
~~~

Classification must answer four questions: is the error specific to **one item** or **the environment**, is dropping the record allowed, did the operation already cause side effects, and can the failure resolve on its own without fixing data or config?

## 4. Skip: Controlled Removal of Bad Data

In Spring Batch 5.x, a fault-tolerant chunk step declares skippable exception classes and an overall skip cap.

~~~java
// Part of a FaultTolerantStepBuilder configuration chain.
.faultTolerant()
.skip(InvalidImportRowException.class)
.skipLimit(50)
~~~

**`skipLimit(50)`** caps total skips across the step across **read**, **process**, and **write** combined—not 50 per phase. When the 51st skippable item appears, the step fails per policy.

### 4.1. Skips in Reader, Processor, and Writer

| Phase | Example Failure | Key Consideration |
|---|---|---|
| **ItemReader** | `FlatFileItemReader` cannot parse a row | Line numbers can be read from `FlatFileParseException`; reader must advance past bad lines rather than looping forever |
| **ItemProcessor** | Data fails validation | Input item is available for quarantine; throw a skippable exception rather than returning null |
| **ItemWriter** | One specific item violates a data constraint | Batched writers make pinpointing the bad item harder; rollback and item-level retries add cost |

**Dangerous mistake:**

~~~java
// Never use for critical data jobs.
.faultTolerant()
.skip(RuntimeException.class)
.skipLimit(Integer.MAX_VALUE)
~~~

This hides connection drops, bugs, and schema mismatches, letting jobs reach COMPLETED even with severe data loss. Define dedicated exception types for malformed records separate from system failures.

### 4.2. Filter vs. Skip

~~~java
// Intentional filter: record falls outside requested scope.
if (!row.inRequestedPeriod()) {
    return null;
}

// Data error: must count toward skips and enter quarantine.
if (row.externalId() == null || row.externalId().isBlank()) {
    throw new InvalidImportRowException("Missing externalId");
}
~~~

In financial jobs, even malformed records may **not be allowed to skip**: the contract requires rejecting the entire file and asking the partner to resend. Skip is a business decision before it is a technical setting.

### 4.3. When Must the Entire File Be Blocked?

If headers, encoding, delimiters, or schema version are wrong, every subsequent row may be misread. Perform preflight header/schema, checksum, and source/version validation before entering the main step to catch batch-wide contract errors immediately instead of skipping tens of thousands of rows first.

## 5. Retry: Re-Attempting Transient Failures Without Infinite Loops

~~~java
// Fault-tolerant step fragment for transient DB errors.
.faultTolerant()
.retry(org.springframework.dao.TransientDataAccessException.class)
.retryLimit(3)
~~~

**`retryLimit(3)`** bounds attempts (including the initial attempt per Spring Retry semantics). Retry only when the failure is plausibly recoverable, repeating the operation is safe, and time budget remains.

For example, a DB transaction deadlock usually succeeds upon retry. By contrast, retrying a timed-out **POST /payments** request can double-charge if the server already committed before the response vanished.

### 5.1. Backoff and Combined Limits

Instead of immediate retries, use bounded exponential backoff with jitter so multiple workers do not retry in lockstep:

~~~text
Attempt 1: initial execution
Transient error -> wait ~200 ms (+/- jitter)
Attempt 2: retry
Transient error -> wait ~400 ms (+/- jitter)
Attempt 3: retry
Still failing -> stop retrying per policy
~~~

These timings are illustrative only, not Spring Batch defaults. Honor HTTP **429 Retry-After** headers from partners. Never stack independent retries in the HTTP client, service layer, and batch step without a shared attempt cap or overall deadline.

### 5.2. What Happens When Retries Exhaust?

- If a transient DB/network outage affects the whole chunk: **fail the step** or wait for operational orchestration—never skip unwritten valid items.
- If the error belongs to an individual record and the contract permits: use an explicit skip policy with limits and quarantine.
- If a side effect's outcome is unknown: persist **PENDING_RECONCILIATION** and query by business key before replaying.

Retry only fixes timing. A deterministic exception caused by an invalid date will not turn valid after three processor invocations.

## 6. Spring Boot 3.x / Spring Batch 5.x Example

Suppose the app provides an **ItemReader<ImportRow>** reading CSV, an **ItemWriter<ImportEntity>** writing idempotently to DB by `externalId`, plus `JobRepository` and `PlatformTransactionManager`. The configuration below allows up to 50 bad data records, retries transient DB errors up to 3 attempts, and fails if valid data cannot be written.

~~~java
import java.math.BigDecimal;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

record ImportRow(String externalId, String currency, BigDecimal amount) {}
record ImportEntity(String externalId, String currency, BigDecimal amount) {}

class InvalidImportRowException extends RuntimeException {
    InvalidImportRowException(String message) { super(message); }
}

@Configuration
class ImportBatchConfig {
    @Bean
    ItemProcessor<ImportRow, ImportEntity> importProcessor() {
        return row -> {
            if (row.externalId() == null || row.externalId().isBlank()) {
                throw new InvalidImportRowException("Missing externalId");
            }
            if (row.amount() == null || row.amount().signum() <= 0) {
                throw new InvalidImportRowException(
                        "Invalid amount: " + row.externalId());
            }
            return new ImportEntity(
                    row.externalId(), row.currency(), row.amount());
        };
    }

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<ImportRow> importReader,
            ItemProcessor<ImportRow, ImportEntity> importProcessor,
            ItemWriter<ImportEntity> importWriter,
            SkipListener<ImportRow, ImportEntity> importSkipListener) {

        return new StepBuilder("importStep", jobRepository)
                .<ImportRow, ImportEntity>chunk(100, transactionManager)
                .reader(importReader)
                .processor(importProcessor)
                .writer(importWriter)
                .faultTolerant()
                .skip(InvalidImportRowException.class)
                .skip(org.springframework.batch.item.file.FlatFileParseException.class)
                .skipLimit(50)
                .retry(TransientDataAccessException.class)
                .retryLimit(3)
                .listener(importSkipListener)
                .build();
    }

    @Bean
    Job importJob(JobRepository jobRepository, Step importStep) {
        return new JobBuilder("importJob", jobRepository)
                .start(importStep)
                .build();
    }
}
~~~

This is a **configuration skeleton**; the application must supply the reader, writer, listener, datasource, and launch mechanism. The writer needs unique constraints/version checks; otherwise retries or restarts can write duplicates. Adjust the positive-amount rule to match your real contract; refund workflows may treat negative amounts as valid.

### 6.1. Observing Skips via Listener

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SkipAuditConfig {
    private static final Logger log =
            LoggerFactory.getLogger(SkipAuditConfig.class);

    @Bean
    SkipListener<ImportRow, ImportEntity> importSkipListener() {
        return new SkipListener<>() {
            @Override
            public void onSkipInRead(Throwable failure) {
                log.warn("skip phase=read reason={}",
                        failure.getClass().getSimpleName());
            }

            @Override
            public void onSkipInProcess(ImportRow item, Throwable failure) {
                log.warn("skip phase=process id={} reason={}",
                        item.externalId(), failure.getClass().getSimpleName());
            }

            @Override
            public void onSkipInWrite(ImportEntity item, Throwable failure) {
                log.warn("skip phase=write id={} reason={}",
                        item.externalId(), failure.getClass().getSimpleName());
            }
        };
    }
}
~~~

This listener performs minimal logging and **does not persist a durable quarantine**. In production, store the record identifier, file/cursor position, error category, source version, run ID, and a reference to raw data in an appropriately secured store. If the listener writes to a different DB transaction or calls HTTP, rollbacks/restarts can skew the error log; design transactions or an outbox accordingly.

### 6.2. Using `noSkip` and `noRetry` Appropriately

When working with broad parent exception classes, the DSL lets you exclude subclasses that must never be skipped or retried:

~~~java
// DSL fragment example; applies only inside a faultTolerant() chain.
.skip(SomeBroadInputException.class)
.noSkip(InvalidFileSchemaException.class)
.retry(org.springframework.dao.TransientDataAccessException.class)
.noRetry(InvalidImportRowException.class)
~~~

Do not look for **SomeBroadInputException** and **InvalidFileSchemaException** in Spring Batch—these represent **custom domain exceptions you define** during implementation. Better yet, list explicit, narrow exception groups directly and test each classification branch. When the same exception is configured as both retryable and skippable, exact behavior depends on policy configuration; verify via tests rather than assuming "try N times then auto-skip."


## 7. Rollbacks and Chunk Re-Execution

Writer failures typically roll back the active transaction. Spring Batch can retry or step item by item to isolate failing records under skip policies, so **a single item may be read, processed, or passed to the writer multiple times** during a job's lifecycle.

~~~mermaid
sequenceDiagram
    participant R as Reader
    participant P as Processor
    participant W as DB Writer
    participant T as Transaction Manager
    R->>P: Items A, B, C
    P->>W: Chunk [A, B, C]
    W->>T: Write changes in transaction
    T--xW: Deadlock -> rollback
    Note over R,W: Framework may re-execute part of the chunk
    W->>T: Retry after rollback (if permitted)
    T-->>W: Commit / or fail once retries exhaust
~~~

**A transaction only rolls back resources enlisted in that transaction.** If `ItemProcessor` already called an HTTP API to create an order or `ItemWriter` published a broker message before the DB transaction rolled back, those external side effects have occurred and will not automatically undo.

Therefore:

- Keep hard-to-reverse side effects out of processors unless backed by idempotency and reconciliation.
- Place rollback-capable DB writes inside the writer's transaction.
- When events must emit upon DB commit, consider a **transactional outbox**: commit business data and pending event records in the same DB transaction, then have a worker publish with deduplication.
- Use **noRollback** only when you thoroughly understand reader/writer lifecycles and can prove continuing leaves state valid.
- Distinguish rollbacks from business errors versus deadlocks, writer failures, and commit-time errors. Never assume every rollback corresponds to a retry.

### 7.1. Timeout After Side Effect: A Particularly Hazardous Scenario

~~~mermaid
sequenceDiagram
    participant B as Batch Writer
    participant A as External API
    participant D as External Database
    B->>A: POST create-payment (requestId=R17)
    A->>D: Commit payment R17
    D-->>A: Commit OK
    A--xB: Response lost / client timeout
    Note over B: Outcome from client view is UNKNOWN
    B->>A: GET payment by requestId=R17
    A-->>B: Payment already exists
    Note over B: Confirm status then complete without creating a second time
~~~

A **`SocketTimeoutException`** does not prove the API never received the request. Unconditional retries can double-record revenue or payments. Solve this with **fixed idempotency keys**, status lookup by request ID, or persisting a reconciliation-pending state instead of guessing failure or success prematurely.

## 8. Handling Duplicates Across Retries, Rollbacks, and Restarts

Spring Batch fault tolerance prioritizes resuming work after failure, so **duplicate execution** must be expected by design.

For example, the target DB write commits, then the app loses connectivity before receiving confirmation. On restart, that item may be sent again. If the writer runs a plain INSERT without a business key, it creates duplicate rows.

An idempotency contract typically includes:

1. **Stable identifier:** `externalId` combined with `sourceSystem`/`tenant` or `eventId`, never a fresh UUID generated per retry.
2. **Destination constraints:** unique constraints on business keys, not just an app-level `EXISTS` check before insert (which suffers race conditions).
3. **Duplicate rules:** identical key and payload/version → no-op; identical key with conflicting payload → raise conflict.
4. **Ordering rules:** only allow updates advancing to a newer version; never assume "arrived later" means "newer data."
5. **Reconciliation:** for actions outside the DB transaction, support querying committed state before re-executing.

### 8.1. Recognizing Duplicates Is Different from Skipping

A record already written in an earlier run is not necessarily "bad data." With an idempotent writer, encountering the same external ID again can be recorded as a **`duplicate_noop`** under its own metric. Throwing every duplicate as a skippable exception inflates skip counts and can fail the step on restart even though business state is valid.

When you need numeric visibility, add a dedicated **duplicate** counter or update staging status rather than inferring duplicates from `readSkipCount`.

### 8.2. Spring Batch Does Not Provide Exactly-Once Across HTTP and Brokers

`JobRepository` persists Step checkpoints; a DB transaction ensures atomicity inside that database. That transaction does not automatically merge with webhooks, Kafka, RabbitMQ, Redis, or target HTTP services into a global atomic transaction.

Use transactional outbox/inbox, idempotent consumers, and business-key reconciliation when messages replay. Guarantees like **at-most-once**, **at-least-once**, and **effectively-once** must be engineered into the integration contract—never assumed from **`retryLimit`** alone.

## 9. Quarantine and Data Quality Thresholds

When items are skipped for bad data, logging "skip succeeded" does not provide traceability. Persist rejected records, reasons, and recovery statuses.

| Quarantine Field | Example | Purpose |
|---|---|---|
| `source_system` / `source_file` | partner A / file_20261121.csv | Trace origin |
| `source_checksum` / `source_version` | checksum, schema version | Prove input was not altered |
| `job_execution_id` / `step` | 18321 / importStep | Link to Spring Batch metadata |
| `record_locator` | line 1483 / externalId=PAY-1473 | Pinpoint the record |
| `failure_phase` / `code` | process / INVALID_CURRENCY | Categorize and repair |
| `safe_payload_reference` | access-restricted object-storage key | Re-ingest without exposing sensitive data |
| `status` / `retry_history` | NEW, FIXED, REPROCESSED | Coordinate remediation |

Apply strict rules for sensitive data. Never write card numbers, tokens, secrets, passwords, or raw personal data into logs; rely on error codes and protected references.

### 9.1. A Flat Skip Limit Is Insufficient When Batch Sizes Vary

**`skipLimit(50)`** represents 50% of a 100-row batch, yet only 0.005% of a million-row batch. Business rules often require both an **absolute cap**, an **error rate**, **mandatory fail-fast error classes**, and a defined **evaluation scope** (per file, tenant, step, or job).

A custom **`SkipPolicy`** can classify exceptions and skip counts:

~~~java
import org.springframework.batch.core.step.skip.SkipPolicy;

SkipPolicy policy = (failure, skipCount) -> {
    boolean dataError =
            failure instanceof InvalidImportRowException
            || failure instanceof org.springframework.batch.item.file.FlatFileParseException;

    // skipCount is the number of skips already recorded before this item.
    return dataError && skipCount < 50;
};

// Register on FaultTolerantStepBuilder via skipPolicy(policy).
~~~

When enforcing a percentage threshold, define the exact denominator (source lines, valid records, or total input) and evaluation point. Avoid dividing by `readCount` casually when chunks may roll back. For wrong file schemas, fail in preflight rather than waiting to trip the skip threshold.

### 9.2. Quarantine Must Survive Rollbacks

**`SkipListener`** is designed to record genuinely skipped items, yet callbacks sending HTTP or writing to another DB can diverge from the transaction. When storing quarantine records in the same DB, align the transaction manager and enforce a unique key per failure. When emitting to a broker, use an outbox or post-commit publish with deduplication.

When a repaired record is re-ingested later, **link it back to the prior skip** so one error is not counted repeatedly as unresolved.

## 10. Checkpoints, `ExecutionContext`, and Restarts

Spring Batch stores metadata via **`JobRepository`**, where **`JobExecution`** and **`StepExecution`** track each attempt's state. **`ExecutionContext`** lets readers/writers implementing **`ItemStream`** persist state needed for restarts.

### 10.1. Restart vs. Retry vs. Rerun

| Mechanism | When It Happens | Key Requirements |
|---|---|---|
| Retry | Within the current `StepExecution` | Operation is repeatable; bounded attempts and backoff |
| Restart | Resuming a `FAILED`/`STOPPED` `JobInstance` | Accurate metadata/checkpoints; stable source data |
| New rerun | New identifying `JobParameters` spawn a new `JobInstance` | May reprocess from start; requires source-wide idempotency |

**`JobInstance`** is identified by job name and **identifying `JobParameters`**. Attaching a new timestamp identifying parameter on each retry creates a distinct JobInstance that may re-read the entire file. Never treat a rerun as an automatically safe restart.

### 10.2. Checkpoint Traps

- File contents modified while reusing line/byte checkpoints: risks skipping or misreading records.
- Custom reader fails to implement `ItemStream` **`open/update/close`** properly: restarts begin at the wrong position.
- Reader reads an external cursor outside DB transactions: SQL rollbacks do not rewind external cursors.
- Batch wrote target data yet commit/checkpoint status was indeterminate: restarts may re-send items.
- Step uses internal queues or async processing: reader checkpoints do not guarantee async side effects completed.

**Restart runbooks** should verify JobExecution/StepExecution, skip counts, unchanged source checksum/schema, uncertain side effects, and idempotent writers. Restart an instance only once outcomes can be reconciled. Never edit `JobRepository` metadata by hand without verifying the recovery procedure for your Spring Batch version.

## 11. Integrating HTTP, Databases, and Brokers in Batch Jobs

| Boundary | Common Failures | Required Behavior |
|---|---|---|
| Paginated HTTP reader | 429, 5xx, expired cursor | Bounded retry, honor Retry-After, stable cursor/checkpoint |
| HTTP writer | Timeout after server committed | Request ID, idempotency key, and status check before replay |
| DB reader | Deadlocks, concurrent mutations | Appropriate isolation/cursor, snapshot if needed |
| DB writer | Unique violations, lock timeouts, connection resets | Classify duplicates, retry transient errors, verify unknown commits |
| Broker consumer | Message redelivery on reconnect/rollback | Ack at the right time, idempotent handler, and DLQ |
| Broker producer | Publish succeeded yet ACK lost | Outbox, dedup/correlation ID |
| File/SFTP | Incomplete writes, duplicate filenames, mutated inputs | Ready markers, checksums, fingerprints, and versioning |

### 11.1. Durable Ingestion Before Outbound Dispatch

~~~mermaid
flowchart LR
    SRC["CSV / API / message source"] --> VALID["Parse + validate"]
    VALID -->|Skippable item error| Q[("Quarantine")]
    VALID -->|Valid| TX[("Staging DB + inbox/outbox transaction")]
    TX --> W["Idempotent worker"]
    W --> DEST["HTTP / broker / downstream"]
    DEST --> ACK["ACK or reconcile"]
~~~

An ingestion step can commit into a staging DB and outbox; a separate worker executes non-transactional side effects with independent retries and idempotency. This clarifies when work is "durably accepted" versus "business-processed." For events that cannot be dropped, test outbox behavior and retention under crash tests.

## 12. When a Job Has Multiple Partitions or Workers

With multi-threaded steps, partitioning, or remote chunking, each worker/partition can own its **own `StepExecution`**. Configuring `skipLimit(50)` per partition allows total skips across the whole job to exceed 50. Enforce a **file-wide/job-wide** threshold if the contract requires it, and aggregate statuses before publishing final results.

Prepare:

1. Non-overlapping partition keys/ranges, or atomic claims so two workers never process the same item.
2. Unique constraints/idempotency in writers when partitions retry or restart.
3. Combined caps on total connection pools, HTTP concurrency, and retries across all workers.
4. Job-wide aggregation of skips, quarantine counts, duplicates, and failures.
5. Partitioning by business key or version checks when ordering matters, rather than trusting thread scheduling.
6. Clear policy when one partition fails after sibling partitions already committed.

Increasing concurrency while a DB suffers transient contention amplifies retry storms. Never add workers to mask resource failures.

## 13. Operational Observability

To confirm a job ran properly, measure **progress**, **data quality**, **durability**, and **business impact**—never rely solely on `COMPLETED`.

| Group | Metric / State | Purpose |
|---|---|---|
| Progress | `readCount`, `writeCount`, `commitCount`, current cursor, throughput | Detect stalled or slow jobs |
| Quality | `filterCount`, `readSkipCount`, `processSkipCount`, `writeSkipCount`, quarantine count | Prove records were dropped strictly per policy |
| Fault tolerance | Retry attempts by error class, `rollbackCount`, backoff duration | Spot overloaded dependencies or retry loops |
| Consistency | Duplicate counts, conflicts, pending reconciliation | Identify data loss or double-write risks |
| Resources | DB pool, HTTP 429/503, CPU, memory, broker lag | Catch cascading failures from retries or batches |
| Operations | `jobInstance`, `jobExecution`, `stepExecution`, source checksum, schema version | Support restarts and audits |

Use **Micrometer/Actuator** for metrics, **JobRepository/JobExplorer** to inspect runs, and **StepExecution** for counters. Label metrics by job name, step, and normalized exception category; never attach per-item `externalId`s as metric labels due to high cardinality. Logs must carry correlation IDs and redact sensitive fields.

Alerts should target **skip rates exceeding thresholds**, jobs breaching SLAs, excessive retries, stalled progress, aging quarantine queues, or growing pending reconciliations. A `COMPLETED` job may still require a "blocked from publishing" business state if error counts exceed commercial tolerances.

## 14. Testing Fault Tolerance

| Scenario | How to Simulate | What to Assert |
|---|---|---|
| Unparseable CSV row | Invalid date format | `readSkipCount` increments, error recorded, continues within cap |
| Processor validation error | Missing `externalId` | `processSkipCount` increments, exact record quarantined |
| Valid filter | Out-of-scope record | `filterCount` increments; skip counts remain unchanged |
| At skip limit | 50 bad records skipped | Step can reach `COMPLETED` if no other errors |
| Exceeding skip limit | 51 bad records | Step `FAILED` with proof batch halted |
| Transient deadlock | Writer throws transient error once then succeeds | Retried within cap, single business effect committed |
| Prolonged DB outage | Writer fails connectivity persistently | Fails once retries exhaust; never skips entire chunk |
| Broken schema | Missing DB column or altered file header | Fail-fast, no pointless retries |
| Timeout after side effect | API commits then drops response | Deduplication/reconciliation preserves exactly one effect |
| Crash before chunk commit | Kill app mid-chunk | Resumes and processes uncommitted items |
| Crash after commit before checkpoint | Simulate indeterminate state | Zero duplicate data thanks to idempotency |
| Multiple partitions | Run multiple workers over shared source | Disjoint slices, global skip totals enforced |

### 14.1. Contract-Driven Assertions

~~~text
A. [valid, invalid, valid]
   -> 2 target records, 1 quarantined record,
      processSkipCount = 1, Step COMPLETED if contract permits skip.

B. [valid] + one-time DB deadlock
   -> retry occurs, 1 target record, no duplicates.

C. [valid] + persistent DB disconnect
   -> Step FAILED, system error never converted into skip.

D. API created transaction then response dropped
   -> retry/restart reconciles using request ID;
      target system holds exactly 1 transaction.

E. Batch quality threshold breached
   -> job must not automatically publish results as finalized.
~~~

For transactions, deadlocks, unique constraints, and restarts, run integration tests against a real database or transaction-equivalent environment. Mocks cannot prove rollbacks or unknown commit outcomes. Measure both writer execution count and **actual persisted side effects** at the target; they often differ.

## 15. End-to-End Scenario: End-of-Day Reconciliation Ingestion

A Spring Boot app reads a 200,000-line partner revenue file. Some lines have bad dates; the target database occasionally deadlocks during peak hours; partners sometimes re-send corrected files.

**Contract:**

- Individual parser errors are quarantined and skipped up to 100 items, subject to a per-file error-rate cap.
- Bad headers/schemas are whole-file failures; the job must fail before writing data.
- Deadlocks receive bounded retries; if the DB remains unavailable, the job FAILS cleanly so it can restart.
- Identical external ID, version, and payload count as an idempotent duplicate; identical external ID and version with conflicting data routes to investigation.
- Any operation with an unknown commit outcome must be queried by business key before re-execution.

~~~mermaid
flowchart TD
    FILE["Versioned/checksummed CSV source"] --> PREF["Preflight header/schema check"]
    PREF -->|Contract broken| FAIL["Fail job"]
    PREF -->|Valid| READ["FlatFileItemReader + checkpoint"]
    READ --> PROC["Validate + normalize"]
    PROC -->|Skippable item error| Q[("Quarantine")]
    PROC -->|Valid| W["Idempotent DB writer"]
    W -->|Transient error| RET["Bounded retry"]
    RET --> W
    W -->|Commit succeeds| DB[("Business DB + unique/version key")]
    W -->|Persistent system error| FAIL
    DB --> REPORT["Reconcile source/target totals"]
    Q --> REPORT
~~~

The end-of-job report must state: total source lines, valid items read, filtered items, skipped items with reasons, idempotent duplicate no-ops, committed records, and items pending reconciliation. Never use **`COMPLETED`** alone as evidence that every business record was accepted.

## 16. Pre-Deployment Checklist

- [ ] Data errors, infrastructure failures, configuration errors, and indeterminate outcomes are classified by explicit contract.
- [ ] Mandatory records are never skipped merely because retries exhausted.
- [ ] No `skip(RuntimeException.class)` or `skip(Exception.class)` with unbounded limits.
- [ ] Skip limits, error rates, step/partition/job scopes, and breach actions are agreed upon.
- [ ] Returning `null` to filter is strictly limited to valid out-of-scope records.
- [ ] Retries have bounded attempts, backoff, timeouts, and idempotent/reconciled side effects.
- [ ] Writers enforce business keys, unique constraints, and version checks where needed.
- [ ] Readers/checkpoints restart cleanly over immutable inputs with durable execution metadata.
- [ ] HTTP/broker side effects are guarded by outboxes or explicit deduplication.
- [ ] `SkipListener`/quarantine captures sufficient evidence while protecting sensitive fields.
- [ ] Tests cover exceeding skip limits, exhausted retries, rollbacks, unknown-outcome timeouts, and restarts.
- [ ] Metrics, batch-quality alerts, recovery runbooks, and pre-publish reconciliation are in place.

**Core principle:** **skip** is a business decision permitting an item to be dropped, **retry** is a technical decision to re-attempt a recoverable condition, and **fail** protects correctness when continuing safely is impossible. Spring Batch reliability in system integration stems from accurate error classification, sound transaction boundaries, idempotency, and reconciliation evidence—not merely high retry or skip counts.

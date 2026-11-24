# Quarantining Invalid Items in Spring Batch

In a data ingestion batch job, not every record is valid. A CSV row may be missing a column, an order may reference a non-existent ID, an amount may be negative, or a customer code may fail to match the catalog. If every such case causes the entire job to fail, valid data may be blocked. On the other hand, if you merely skip invalid records without keeping evidence, data disappears from the pipeline and becomes very hard to reconcile.

**Quarantining invalid items** means routing records that fail rules into a controlled isolation area, together with **origin, failure reason, processing status, and link to the batch run**. Valid records can continue to the destination, while quarantined records wait for inspection, source data correction, or reprocessing under a separate workflow. This is a key technique in the **Data quality** chapter of **Spring Batch Core Processing**.

```text
                 File / Database / Message
                            |
                            v
                     ItemReader<I>
                            |
                            v
                    ItemProcessor<I,O>
                            |
             +--------------+---------------+
             |                              |
        Valid item                    Known data error
             |                              |
             v                              v
        ItemWriter<O>                SkipListener / route
             |                              |
             v                              v
      Business table                  Quarantine store
             |                              |
             +--------------+---------------+
                            |
                            v
                  Reconciliation & monitoring
                            |
                            v
                    Fix / reprocess
```

Quarantine must be tied to a **clear data policy**. Not every exception proves an item is invalid: database disconnection, out-of-memory, deadlock, or programming bugs are system issues; automatically routing the affected items into quarantine can report "success" while the job actually dropped valid data.

## 1. Distinguishing Quarantine, Filter, Skip, Retry, and Fail

These terms are often used interchangeably, yet they mean different things:

| Behavior | When to Use | Effect in Spring Batch | Auto-Creates Quarantine Record? |
| --- | --- | --- | --- |
| **Filter** | Item is valid but outside output scope, e.g., previously closed transaction | `ItemProcessor.process()` returns `null`; increments `filterCount` | No |
| **Skip** | Item cannot be processed and the error is permitted to be skipped by policy | Fault-tolerant step skips item; increments appropriate skip counter | No, unless a listener or custom persistence mechanism is added |
| **Retry** | Error is likely transient, e.g., timeout/serialization conflict | Retries operation per retry policy; if still failing, proceeds per policy | Should not default to quarantine as a data error |
| **Fail** | Error is not skippable or exceeds skip limit | Step/job transitions to failed status | May record a final failure for investigation, but no default quarantine row |
| **Quarantine** | Need to keep the invalid item and reason for review/reprocess | Application stores the failed record separately with metadata | Yes, implemented by the application |

**Skip is a framework decision about control flow; quarantine is an application decision about data audit retention.** The two concepts can work together: configure skip for a known set of business exceptions, then use a `SkipListener` to persist skipped items into the quarantine store.

Example with input data:

```text
payment_id,amount
P001,100.00
P002,-50.00
P003,20.00
P004,not-a-number
```

If the rule is that amount must be greater than 0, then `P002` and `P004` must go to quarantine with specific error codes; `P001` and `P003` are written to the target table. The job may complete with skips if the error count is within limits, yet it must still report **received 4 rows, accepted 2, quarantined 2**.

## 2. Classifying Errors Before Deciding to Quarantine

There is no single `.skip(Exception.class)` configuration that is safe for every case. Build an error taxonomy with cause categories, for example:

| Error Type | Examples | Behavior to Consider |
| --- | --- | --- |
| Malformed data structure | Missing CSV column, wrong date format, unparseable JSON | Quarantine if the source line and identifier remain traceable |
| Business rule violation | Negative amount, invalid status, wrong region code | Quarantine with reason code and source details |
| Reference data mismatch | Product code not yet in catalog | Quarantine or wait for master data addition, depending on policy |
| Duplicate already-processed data | Same business key sent twice | Deduplicate/filter, reject, or quarantine depending on contract |
| Transient timeout/API error | Slow external endpoint | Bounded retry, then fail/re-orchestrate; do not label item invalid |
| Database infrastructure error | Lost connection, deadlock, exhausted connection pool | Retry if safe or fail step; restore infrastructure |
| Programming/config error | `NullPointerException`, SQL schema mismatch, missing bean | Fail to fix the application; do not bulk-quarantine |

You should have **stable reason codes** (`INVALID_AMOUNT`, `UNKNOWN_CURRENCY`, `INVALID_CSV_LAYOUT`) alongside error messages. Messages may vary by locale or application version; reason codes are far easier to aggregate, chart on dashboards, and drive remediation workflows. If you need to separate self-correctable errors from errors requiring human confirmation, add `resolution_type` or business-defined severity groups.

### Filter Is Not the Same as Quarantine

In Spring Batch, `ItemProcessor` returning `null` means **filtering the item out of output**, without triggering `onSkipInProcess`. If the requirement is "every row failing validation must appear in quarantine," do not silently return `null` for validation failures. Instead, throw a dedicated business exception and configure skip, or design the processor to return a `ProcessingResult` and explicitly route valid/invalid branches to appropriate writers.

## 3. Skip Trigger Points and Collectible Data

In a chunk-oriented step, errors can occur at different stages:

```text
Reader.read() -----------> onSkipInRead(Throwable)
     |
     v
Processor.process(item) --> onSkipInProcess(item, Throwable)
     |
     v
Writer.write(chunk) -----> onSkipInWrite(item, Throwable)
```

`SkipListener<I,O>` provides three corresponding callbacks. However, **available data differs**:

- `onSkipInRead(Throwable)`: the framework has not yet created an item of type `I`, so only the exception is passed. With `FlatFileParseException`, you can extract the line number and raw line text; with database/network errors, there is usually no specific bad record.
- `onSkipInProcess(I, Throwable)`: the original input item is available, making it easy to capture source ID, line number, and business key.
- `onSkipInWrite(O, Throwable)`: the skipped output item after processing is available, so you should preserve source identity inside `O` if you need to trace back to the input record.

An important policy: **only configure skip for exceptions confirmed to be data errors**. With a SQL writer, for instance, `DataIntegrityViolationException` might come from a specific bad record, or from a schema change or new constraint; understand the error before adding an entire exception group to the skip policy.

### `skipLimit` Protects Data Quality

```java
.faultTolerant()
.skip(InvalidPaymentException.class)
.skip(FlatFileParseException.class)
.skipLimit(10)
```

In this example, the step is allowed to skip at most **10 errors** in total across the declared types. The next error exceeding the limit causes the step to fail, unless a different classification policy is configured. `readSkipCount`, `processSkipCount`, and `writeSkipCount` indicate which stage failed. Choose the limit based on business needs: sometimes even one bad item must fail the job; other times a small threshold is acceptable, such as combining an absolute limit and an error percentage with custom control logic.

## 4. Designing the Quarantine Area

Quarantine is not just a file named `bad-records.csv`. It must answer: which item, from which source, at which stage, why it failed, whether it has been reviewed, and what the reprocessing outcome was.

An illustrative SQL table model:

```sql
CREATE TABLE payment_quarantine (
    source_id         VARCHAR(160) NOT NULL,
    source_line       INTEGER NOT NULL,
    failure_stage     VARCHAR(16) NOT NULL,
    reason_code       VARCHAR(64) NOT NULL,
    payment_id        VARCHAR(100),
    job_execution_id  BIGINT NOT NULL,
    step_execution_id BIGINT NOT NULL,
    review_status     VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    created_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (source_id, source_line, failure_stage)
);

CREATE INDEX idx_payment_quarantine_review
    ON payment_quarantine (review_status, created_at);
```

This is an **application-owned** table, not Spring Batch's `BATCH_*` metadata tables. `source_id` should represent an **immutable** source version (such as object key + version ID or a unique import ID); `source_line` identifies the line position within that source. `failure_stage` is `READ`, `PROCESS`, or `WRITE`.

The unique key `(source_id, source_line, failure_stage)` is one example of a duplicate-write prevention strategy. In a pipeline where one item can suffer multiple error types at the same stage or be processed under multiple rule versions, extend the identity, store status history, or design a separate event ID. Do not blindly use `jobExecutionId` as the unique key, because a restart can create a new execution for the same failed item.

### 4.1. Recommended Fields

| Group | Suggested Fields | Purpose |
| --- | --- | --- |
| Origin | `sourceSystem`, `sourceId`, `sourceVersion`, `lineNumber`, `recordKey` | Trace exact record and input version |
| Error | `failureStage`, `reasonCode`, `errorCategory`, `schemaVersion` | Consistent classification and remediation |
| Batch | `jobName`, `jobInstanceId`, `jobExecutionId`, `stepExecutionId`, `businessDate` | Link to batch execution history |
| Data preservation | `rawPayloadRef`, checksum, format/encoding | Reconstruct failed data without scattering sensitive payloads |
| Remediation workflow | `reviewStatus`, `reviewedBy`, `reviewedAt`, `resolution`, `reprocessExecutionId` | Track from quarantine until resolved |
| Governance | `createdAt`, `retentionClass`, `tenantId` when needed | Access control, retention, and controlled deletion |

If raw content contains personal or financial information, store only a **reference to an encrypted object** in a dedicated store, while the quarantine table keeps the hash, line number, and reason code. Never write full tokens, passwords, account numbers, or raw error payloads into logs or exception messages.

### 4.2. File Storage vs. Database Storage?

| Form | Benefits | Risks to Address |
| --- | --- | --- |
| Dedicated SQL table | Easy to query, attach review status, shares transaction with writer when on the same datasource | Needs schema, indexes, retention, access control, and duplicate-write prevention |
| Quarantine CSV/JSON file | Easy to hand off to data stewards, fits file-based batch flows | Flush/append and rollback do not auto-sync with database; must manage temp files and restarts |
| Object storage (S3/MinIO...) | Suits large inputs, supports versioning/retention, encryptable | Needs manifest and record linkage; object writes are not necessarily atomic with Batch commits |
| Queue or event stream | Useful for automated review flows or downstream systems | Redelivery, ordering, and idempotency issues; hard to guarantee end-to-end exactly-once |

Choose the storage form based on queryability, scale, access control, and transaction needs. For a simple JDBC step, a quarantine table in the **same datasource and transaction manager** is usually the easiest starting point to reason about.

## 5. Spring Batch 5.x Example: Quarantining on Processor Failure

The following example uses **Spring Batch 5.x, Spring Boot 3.x, Java 17+**, and PostgreSQL. Input rows are payment lines with `sourceId`, line number, and amount as a string. The processor permits positive amounts; if the amount is malformed or not greater than 0, it throws a business exception with a clear error code.

### 5.1. Input Model, Output Model, and Business Exception

```java
package com.example.batch;

import java.math.BigDecimal;

public record PaymentRow(
    String sourceId,
    int sourceLine,
    String paymentId,
    String amountText
) {}

public record AcceptedPayment(
    String sourceId,
    int sourceLine,
    String paymentId,
    BigDecimal amount
) {}
```

The `record` types above can be placed in two separate Java files in the same package. A dedicated exception avoids accidentally skipping every `IllegalArgumentException` (which could originate from a programming bug):

```java
package com.example.batch;

public final class InvalidPaymentException extends RuntimeException {
    private final String reasonCode;

    public InvalidPaymentException(String reasonCode, String message) {
        super(message);
        this.reasonCode = reasonCode;
    }

    public String getReasonCode() {
        return reasonCode;
    }
}
```

Processor:

```java
package com.example.batch;

import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public final class PaymentValidationProcessor
        implements ItemProcessor<PaymentRow, AcceptedPayment> {

    @Override
    public AcceptedPayment process(PaymentRow row) {
        if (row.paymentId() == null || row.paymentId().isBlank()) {
            throw new InvalidPaymentException(
                "MISSING_PAYMENT_ID", "Payment ID is required");
        }

        final BigDecimal amount;
        try {
            amount = new BigDecimal(row.amountText().trim());
        } catch (RuntimeException ex) {
            throw new InvalidPaymentException(
                "INVALID_AMOUNT_FORMAT", "Amount is not numeric");
        }

        if (amount.signum() <= 0) {
            throw new InvalidPaymentException(
                "AMOUNT_NOT_POSITIVE", "Amount must be positive");
        }

        return new AcceptedPayment(
            row.sourceId(), row.sourceLine(), row.paymentId(), amount);
    }
}
```

The exception message here contains only a safe description, while `reasonCode` is used for dashboards and quarantine. Validation code can be unit-tested independently of Batch infrastructure. In a real system, also define scale, currency, amount bounds, and payment ID validity rules.

### 5.2. Valid Data Table

```sql
CREATE TABLE accepted_payment (
    source_id   VARCHAR(160) NOT NULL,
    source_line INTEGER NOT NULL,
    payment_id  VARCHAR(100) NOT NULL,
    amount      NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (source_id, source_line)
);
```

The key `(source_id, source_line)` prevents duplicate writes of the same input record if a new run is triggered unintentionally. If you need a business key such as `payment_id` to prevent duplicates across multiple sources, design an additional unique constraint and corresponding upsert/deduplication policy.

### 5.3. Batch Writer for Valid Items

```java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

@Bean
JdbcBatchItemWriter<AcceptedPayment> acceptedPaymentWriter(
        DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<AcceptedPayment>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO accepted_payment
                (source_id, source_line, payment_id, amount)
            VALUES (:sourceId, :sourceLine, :paymentId, :amount)
            """)
        .beanMapped()
        .build();
}
```

`beanMapped()` reads properties from `AcceptedPayment` to bind to named parameters. This write uses the JDBC transaction managed by the chunk step. For simplicity of illustration, a duplicate-key input causes the writer to throw an exception and fail the step; we do **not** configure skipping all database exceptions.

### 5.4. `SkipListener` Writing Quarantine Records

The listener below only saves when the processor throws `InvalidPaymentException`. The example uses PostgreSQL `ON CONFLICT DO NOTHING` to avoid inserting two quarantine rows for the same source, line number, and stage. Adjust the SQL if using another database.

```java
package com.example.batch;

import java.sql.Timestamp;
import java.time.Instant;

import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.SkipListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class PaymentQuarantineListener
        implements SkipListener<PaymentRow, AcceptedPayment> {

    private final JdbcTemplate jdbc;
    private final StepExecution execution;

    public PaymentQuarantineListener(
            JdbcTemplate jdbc,
            @Value("#{stepExecution}") StepExecution execution) {
        this.jdbc = jdbc;
        this.execution = execution;
    }

    @Override
    public void onSkipInProcess(PaymentRow item, Throwable error) {
        InvalidPaymentException invalid = (InvalidPaymentException) error;

        jdbc.update("""
            INSERT INTO payment_quarantine (
                source_id, source_line, failure_stage, reason_code,
                payment_id, job_execution_id, step_execution_id,
                review_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_id, source_line, failure_stage)
            DO NOTHING
            """,
            item.sourceId(),
            item.sourceLine(),
            "PROCESS",
            invalid.getReasonCode(),
            item.paymentId(),
            execution.getJobExecutionId(),
            execution.getId(),
            "PENDING",
            Timestamp.from(Instant.now())
        );
    }
}
```

`@StepScope` lets the listener receive the current run's `StepExecution`; do not use mutable singleton fields to hold state across executions. In this setup, because the skip policy only allows `InvalidPaymentException` from the processor, casting in `onSkipInProcess` is grounded. If you expand the policy, classify exceptions inside the callback instead of casting unchecked.

**The relationship with transactions is critical:** Spring Batch invokes `SkipListener` at the appropriate moment before transaction commit to reduce the risk of repeated callbacks for the same item after rollback. If `JdbcTemplate` writing quarantine uses the **same datasource and transaction manager** as the writer, the quarantine insert participates in the same chunk transaction. On pre-commit failure, both valid chunk data and uncommitted quarantine rows roll back, preserving consistency.

Do not casually add `@Transactional(propagation = REQUIRES_NEW)` to the quarantine write method just to "ensure the error log is always saved." A separate transaction can commit quarantine even when the chunk rolls back, causing an item to be marked quarantined while also being reprocessed on retry/restart. If you need to record every failed attempt, separate **attempt audit events** from **the quarantine record of an actually rejected item**, with two distinct contracts.

### 5.5. Configuring the `Step` with a Skip Policy

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentRow> paymentReader,
        JdbcBatchItemWriter<AcceptedPayment> acceptedPaymentWriter,
        PaymentQuarantineListener quarantineListener) {

    return new StepBuilder("importPaymentsStep", jobRepository)
        .<PaymentRow, AcceptedPayment>chunk(100, transactionManager)
        .reader(paymentReader)
        .processor(new PaymentValidationProcessor())
        .writer(acceptedPaymentWriter)
        .faultTolerant()
        .skip(InvalidPaymentException.class)
        .skipLimit(10)
        .listener(quarantineListener)
        .build();
}
```

The example assumes `paymentReader` is configured from a test file/database and returns `PaymentRow` with source identity. `faultTolerant()`, `skip(...)`, and `skipLimit(...)` are Spring Batch 5.x mechanisms. Each item skipped in the processor triggers an `onSkipInProcess` event; the listener stores the item with its `reasonCode`.

One point not to overlook: **just adding `.skipLimit(10)` does not complete a data quality policy**. Business rules may require failing when the error rate exceeds 1%, when any `UNKNOWN_ACCOUNT` error occurs, or when mandatory input data is missing. Such aggregate rules must be designed at the step/job level and verified with corresponding fixtures.

## 6. Quarantining Bad Rows Directly at `ItemReader`

A malformed CSV line can prevent `FlatFileItemReader` from creating a `PaymentRow`. In that case `onSkipInProcess` does not run; use `onSkipInRead` to extract details from the exception.

### 6.1. Reader Capturing Source Identity and Line Number

Example reader configuration in Spring Batch 5.x:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<PaymentRow> paymentReader(
        @Value("#{jobParameters['inputPath']}") String inputPath,
        @Value("#{jobParameters['sourceId']}") String sourceId) {

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setDelimiter(",");
    tokenizer.setNames("paymentId", "amount");
    tokenizer.setStrict(true);

    FlatFileItemReader<PaymentRow> reader = new FlatFileItemReader<>();
    reader.setName("paymentReader");
    reader.setResource(new FileSystemResource(inputPath));
    reader.setLinesToSkip(1); // header
    reader.setLineMapper((line, lineNumber) -> {
        var fields = tokenizer.tokenize(line);
        return new PaymentRow(
            sourceId,
            lineNumber,
            fields.readString("paymentId"),
            fields.readString("amount")
        );
    });
    return reader;
}
```

This sample targets simple two-field CSV and does not cover commas inside quoted strings, multi-line logical records, or complex escaping. Real-world CSV data needs a tokenizer/reader configured for the exact source format. `FlatFileItemReader` wraps mapping errors into `FlatFileParseException`, providing the line number and raw content of the failing line.

When configuring the step, add:

```java
.skip(FlatFileParseException.class)
```

For read skips, the listener can inspect the exception:

```java
@Override
public void onSkipInRead(Throwable error) {
    if (!(error instanceof FlatFileParseException parse)) {
        return;
    }

    // sourceId is injected via JobParameters in the @StepScope listener.
    // parse.getLineNumber() is the line in the original file.
    // Save reasonCode = INVALID_CSV_LAYOUT, failureStage = READ.
    // Only store raw line when security policy allows.
}
```

For the listener in section 5, implementing this callback requires injecting `sourceId` in the constructor and calling a shared `saveQuarantine(sourceId, parse.getLineNumber(), "READ", ...)` method. On read errors prior to mapping, `PaymentRow` does not exist yet, so there is no reliable `paymentId` to store. If raw input must be retained, compute a checksum or encrypt it keyed by `sourceId`/line number; do not log `parse.getInput()` by default.

**Do not skip every reader exception.** Missing resources, lost connections, or sudden file changes can compromise data completeness; fail the job so operations can inspect. Read quarantine is only appropriate when a single bad record is identified and the reader can safely advance to the next record.

## 7. Quarantining on Writer Failure: Extra Caution Needed

`onSkipInWrite(O item, Throwable)` can supply the skipped output item. However, writer failures often occur **at the batch/chunk level** or transaction level, not necessarily for a single item. Spring Batch may have to split the batch or retry writes individually to isolate the offending item, depending on the writer type and fault-tolerance mechanism.

For example:

- `DuplicateKeyException` for an existing payment ID might be a data error under the contract, or it might be **an item already written successfully in a previous run**. Routing it straight to quarantine could turn a valid restart into a false rejection.
- `DataAccessResourceFailureException`, timeouts, or deadlocks are system failures; skipping an item does not fix the root cause and can drop data.
- A writer calling an external API may have caused a side effect yet timed out; quarantining the item and resending it later risks duplicate transactions.

Only enable writer skip if errors can be attributed to the **exact item**, transactions/rollbacks are reliable, and business policy permits it. For invalid reference codes or amounts, it is usually better to **validate in the processor** before the writer executes. When unsure whether a failure stems from data, let the step fail, preserve `JobRepository`, and restart after fixing infrastructure.

## 8. Transactions, Rollback, and Consistency Between Two Destinations

Suppose a chunk has 3 payments:

```text
P001 (valid)
P002 (negative amount)
P003 (valid)
```

With `skip(InvalidPaymentException.class)` and a listener writing quarantine to the **same database and same chunk transaction**:

```text
BEGIN TRANSACTION
  process P001 -> valid
  process P002 -> skip, mark for quarantine
  process P003 -> valid

  INSERT accepted_payment(P001)
  INSERT accepted_payment(P003)
  INSERT payment_quarantine(P002, AMOUNT_NOT_POSITIVE)
  write Spring Batch checkpoints/metadata
COMMIT
```

Expected outcome when the transaction commits successfully: the target table contains `P001`, `P003`; quarantine contains `P002`; the step has `readCount=3`, `processSkipCount=1`, `writeCount=2` under this fixture.

If the transaction rolls back before commit, inserts within that transaction do not persist. When the framework reprocesses the items, the listener may be called during the subsequent successful attempt. The transactional behavior of `SkipListener` and your datasource should be tested with failure injection rather than assuming the listener runs strictly once under every custom configuration.

### 8.1. When Quarantine Lives in a Different Datasource

If valid data is written to database A while quarantine is sent over REST or written to object storage B, **no local JDBC transaction guarantees both destinations commit simultaneously**. One side can succeed while the other fails.

Architectural options:

1. **Transactional outbox:** within the business transaction, store valid records and an outbox event for quarantined items; a publisher emits to the quarantine store/queue after commit. The publisher must be idempotent and support retries.
2. **Staging + reconciliation:** write both valid results and rejection statuses into a controlled staging area, then fan out to destinations after reconciliation.
3. **Independent audited quarantine:** when every attempt must be logged, accept eventual consistency but attach `eventId`, source identity, and status `PENDING/CONFIRMED` so uncommitted events are not mistaken for final rejections.

"Fire-and-forget" quarantine that sends async messages inside `onSkipInProcess()` is especially risky: the callback may run while sending fails, or the message may be sent before the final chunk transaction commits. If you must send messages, use an outbox or an appropriate transactional mechanism.

### 8.2. Writing Quarantine Files

When writing quarantine to a file, account for buffering, flushing, appending, and restarts. Files do not automatically roll back like JDBC transactions. A writer may need to manage `ItemStream.open/update/close`, track the last written position, and use separate output paths per job instance. When exporting files for human review, write temporary files by source version, and only publish the manifest/quarantine file after the step/job completes and counts are reconciled.

## 9. Avoiding Duplicate Quarantine Records on Retry and Restart

In Spring Batch, a failed `JobInstance` can have multiple `JobExecution` records upon restart. Items may be reprocessed if a prior chunk did not commit. Therefore, you need an idempotency key based on **source record identity**, not solely on the run execution.

```text
sourceId = bank-feed-20261116-object-version-v4
sourceLine = 875
stage = PROCESS

Run #1: item fails, chunk transaction rolls back
Run #2: restart, item fails again

=> only one final quarantine record is recognized
   for (sourceId, sourceLine, stage)
```

A unique key as in the SQL example and `INSERT ... ON CONFLICT DO NOTHING` ensures idempotency in PostgreSQL, but you still need a policy when a failed record is corrected or business rules change. If the source updates its content, issue a new source version or record a *correction event*, rather than silently mutating the raw content of an already quarantined record.

**Do not automatically assume a record already in quarantine may be skipped forever.** Once source data is fixed, it can become valid and require reprocessing. Handling must be driven by review status, source version, and run policy, not merely key existence.

### 9.1. `JobInstance` vs. `JobExecution`

```text
Job: importPaymentsJob
Identifying JobParameters: sourceId=feed-v4

JobInstance 220
  +-- JobExecution 801  FAILED
  +-- JobExecution 805  COMPLETED (restart)
```

If the scheduler adds a new identifying UUID on every run, it creates a new `JobInstance` for the same `sourceId`, causing the import to start over from the beginning. Deduplication via business/quarantine keys is still needed, but it is better to design `JobParameters` around the true processing period semantics and use official restarts when appropriate.

### 9.2. Skip Listener and At-Least-Once

Spring Batch strives to invoke the skip listener once per skipped item at the right point in the transaction. Even so, distributed systems or external side effects cannot guarantee **exactly-once** solely from a callback. Quarantine persistence still requires idempotency, and per-attempt audit events need their own `eventId` if retry history is desired.

## 10. Lifecycle of a Quarantined Record

Quarantine only matters if a person or process acts on it. A suggested lifecycle:

```text
PENDING
   |
   +-- REVIEWING
          |
          +-- READY_FOR_REPROCESS
          |       |
          |       +-- REPROCESSED
          |       +-- REPROCESS_FAILED -> REVIEWING
          |
          +-- REJECTED_PERMANENTLY
          |
          +-- DUPLICATE / NOT_ACTIONABLE
```

These states are illustrative; names and transition conditions must be defined by the business. Each state transition should record who performed it, timestamp, reason, corrected data version, and `reprocessExecutionId` when applicable. Do not overwrite a single `status` column and lose approval history.

### 10.1. Reprocessing with Corrected Input

A safe workflow:

1. Read quarantine records in a correctable state; authorized reviewers inspect the error and identify source data.
2. Create a **corrected** input version or a dedicated correction payload without overwriting original source evidence.
3. Assign a new source with `sourceVersion`/correction ID and explicitly specify the target business period.
4. Run a reprocessing job/step with the same validation as the main ingestion flow; use idempotency keys to avoid duplicate output.
5. Verify results at the target and update status to `REPROCESSED` along with the new execution ID.

Reprocessing quarantined records is usually an **intentional business reprocessing action**, not necessarily a `restart` of the old batch job. Spring Batch restart primarily resumes a failed `JobInstance` from a checkpoint; reprocessing after data correction may require a new input version and new run to keep auditing transparent.

### 10.2. Count Reconciliation

For a flow where one input record produces at most one output record, you can expect:

```text
Successfully read input records
  = valid records written
  + intentionally filtered records
  + records skipped in processor
  + records skipped in writer

Lines failing parse before item creation
  are tracked separately via readSkipCount
```

This formula is **illustrative for a 1:1 pipeline with no uncommitted retries and no item expansion/aggregation**. In practice, writer skips, rollbacks, one-to-many transformations, and multi-step flows can make simple counter reconciliation inaccurate. When reconciliation is critical, count unique inputs, committed business outputs, and confirmed quarantine records by business key/source version.

For example, a file with four data lines where three parse into `PaymentRow` and one is malformed; among the three parsed rows, one has a negative amount. If the step completes with skips, `readCount=3`, `readSkipCount=1`, `processSkipCount=1`, `writeCount=2` is a reasonable result for that fixture; the number of source data rows excluding header is `4`.

## 11. Monitoring and SLAs for Quarantined Data

Routing bad items into quarantine is insufficient without monitoring. Track **by data period and source**:

| Metric | Meaning | Suggested Action |
| --- | --- | --- |
| `quarantine_count` | Total quarantined records | Alert on sudden spikes |
| `quarantine_ratio` | Ratio of quarantined records to input | Detect widespread data quality degradation |
| `quarantine_by_reason` | Distribution of error codes | Distinguish schema drift, missing master data, business rule failures |
| `oldest_pending_age` | Age of oldest unreviewed record | Track remediation SLAs |
| `reprocess_success_rate` | Rate of successful reprocessing | Measure effectiveness of data fixes |
| `duplicate_quarantine_attempts` | Count of duplicate idempotency-key attempts | Detect abnormal retries/reruns |
| `skipped_items` from StepExecution | Skips in read/process/write | Reconcile against actually persisted quarantine rows |

When exporting metrics to Prometheus/Micrometer, only use **low-cardinality** labels such as `jobName`, `reasonCode`, `stage`, or source group. Do not put per-item `paymentId`, `sourceLine`, or `jobExecutionId` into metric labels, as high label cardinality can overload the monitoring system. Detailed identifiers belong in the audit/quarantine database or structured logs with proper retention.

`BatchStatus.COMPLETED` with skips may still be **technical success**, while the business considers the data period `COMPLETED_WITH_REJECTIONS` or `NEEDS_REVIEW`. Define that status in dedicated reports/workflows; do not equate `COMPLETED` with "100% of data was accepted."

## 12. Testing Invalid Item Quarantine

Combine unit tests for classification with integration tests for transaction/skip behavior. A test calling only `PaymentValidationProcessor.process()` does not prove quarantine rows are actually persisted, nor does it guarantee restarts do not create duplicates.

### 12.1. Processor Unit Test

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class PaymentValidationProcessorTest {
    private final PaymentValidationProcessor processor =
        new PaymentValidationProcessor();

    @Test
    void acceptsPositiveAmount() {
        AcceptedPayment result = processor.process(
            new PaymentRow("feed-v4", 2, "P001", "100.00"));

        assertThat(result.amount()).isEqualByComparingTo("100.00");
    }

    @Test
    void rejectsNonPositiveAmountWithReasonCode() {
        assertThatThrownBy(() -> processor.process(
            new PaymentRow("feed-v4", 3, "P002", "-50.00")))
            .isInstanceOf(InvalidPaymentException.class)
            .extracting("reasonCode")
            .isEqualTo("AMOUNT_NOT_POSITIVE");
    }
}
```

This unit test verifies business validation and reason codes. It requires neither a Spring context nor a `JobRepository`.

### 12.2. Step Integration Test with Bad Data

Prepare a test database with `accepted_payment` and `payment_quarantine` tables and an input file:

```csv
paymentId,amount
P001,100.00
P002,-50.00
P003,20.00
```

In Spring Batch 5.x with `@SpringBatchTest`, you can use `JobLauncherTestUtils.launchStep(...)` and `JobParameters` passing `sourceId` and `inputPath` to the reader:

```java
JobParameters params = new JobParametersBuilder()
    .addString("sourceId", "feed-test-v1")
    .addString("inputPath", input.toAbsolutePath().toString(), false)
    .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchStep(
    "importPaymentsStep", params);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

StepExecution step = execution.getStepExecutions()
    .iterator().next();

assertThat(step.getReadCount()).isEqualTo(3);
assertThat(step.getProcessSkipCount()).isEqualTo(1);
assertThat(step.getWriteCount()).isEqualTo(2);

Integer accepted = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM accepted_payment", Integer.class);
Integer quarantined = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM payment_quarantine", Integer.class);

assertThat(accepted).isEqualTo(2);
assertThat(quarantined).isEqualTo(1);
```

This is an **illustrative test excerpt**, assuming beans, schema, database, and `input` are already set up in the test fixture. For production tests, do not just count rows; assert `source_id`, `source_line`, `reason_code`, amounts of valid records, and absence of bad data. Each test needs isolated inputs and schema/transaction state to avoid depending on prior runs.

### 12.3. Failure Paths to Verify

1. **Malformed input during read:** a CSV row missing a column must increment `readSkipCount`; if skippable and `onSkipInRead` is configured, quarantine has the exact `sourceId`/line number.
2. **Validation error:** negative amount or missing ID increments `processSkipCount`; valid data is still written.
3. **Exceeding `skipLimit`:** the job/step fails as configured, never silently accepting a batch with too many errors.
4. **Quarantine insert fails:** when sharing the same datasource/transaction, verify the chunk does not commit inconsistently between accepted and quarantine.
5. **Rollback then retry:** no durable quarantine row remains from a rolled-back attempt; when the item is finally skipped successfully, the exact record appears.
6. **Restart after failure:** keeping the same identifying parameters, verify output/quarantine are not duplicated and no unwanted new `JobInstance` is created.
7. **Resending the same source version:** unique keys or upsert prevent unwanted duplicates, while tests still accurately report input quality.
8. **External system timeout:** do not misclassify as `INVALID_PAYMENT`; the batch must retry/fail as designed.
9. **Reprocess after correction:** a corrected data version is written to the target table and the old quarantine record transitions status cleanly.

If testing both reader parse and processor validation in a four-row file, you can expect `readSkipCount=1`, `processSkipCount=1`, `writeCount=2` when configured to skip both `FlatFileParseException` and `InvalidPaymentException`. Ensure **the listener actually persists both error types** before asserting two quarantine rows.

## 13. Quarantine Data Governance

Quarantine often holds "bad" data that is still sensitive information. Establish permissions and retention from the start:

- **Restrict read access:** reviewers see only necessary fields; accessing raw payloads requires separate authorization and clear justification.
- **Do not log full input:** parser exceptions may contain the original CSV line; log only reason codes, source references, line numbers, or redacted text.
- **Encryption and storage separation:** raw objects should be encrypted at rest and in transit, with access controls independent of summary tables.
- **Audit edits:** record who fixed it, timestamp, reason, updated data version, and reprocessing execution.
- **Retention and deletion:** quarantine retention depends on business/legal rules; avoid keeping raw payloads forever just in case "we might need to debug."
- **Do not purge batch metadata too early:** keep `JobRepository` long enough for executions that may still need restart, alongside appropriate audit/quarantine retention.

A quarantine record should never be edited directly into "good data" by erasing its reason code. Provenance and handling decisions must be preserved to explain why input data was originally rejected.

## 14. Common Implementation Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| `.skip(Exception.class)` | Hides programming/infra bugs, skips even valid data | Only skip classified business exceptions |
| Processor returns `null` for all bad items | Filter count increases with no quarantine record | Use dedicated exception + skip listener or structured result routing |
| Omitting `sourceId` and line/record key | Cannot tell where a bad item came from | Include source identity/version in input model and audit |
| Writing quarantine in a separate transaction in callback | Rejects can persist from rolled-back chunks | Prefer shared transaction or outbox with explicit contract |
| Quarantining the same item repeatedly on restart | Duplicate error lists and wrong counts | Unique key by source/record/stage, idempotent insert |
| Skipping all writer errors | May ignore transient database or API failures | Retry/fail by error type; validate before writer when possible |
| Only checking job `COMPLETED` | Unknown how many records were quarantined | Assert counts, target tables, quarantine, and business rules |
| Reprocessing by editing original data in place | Loses audit trail and breaks reconciliation | Store correction version, event, and reprocessing execution |
| Logging raw exceptions/payloads | Sensitive data leak | Redaction, references, checksums, and access control |
| No owner for reviewing quarantine | Backlog grows indefinitely | Review workflow, SLAs, alerts, and retention |
| Assuming `readSkipCount` means items with a `PaymentRow` | Read skips usually happen before mapping | Use parse exceptions/source lines for traceability |
| Generating a new identifying UUID on every restart | Creates new instances, risks duplicate writes | Keep identifying parameters for proper restarts |

## 15. Choosing a Quarantine Strategy by Scenario

A practical decision can follow these questions:

```text
Problematic item detected
            |
            v
Error caused by specific data with identifiable item?
       |                         |
      Yes                        No
       |                         |
       v                         v
Is error allowed to skip?     Retry/fail/investigate
       |                      infrastructure or code
       |
   +---+---+
   |       |
  Yes      No
   |       |
   v       v
Bounded   Fail step/job
 skip
   |
   v
Save quarantine with exact source + reason
in appropriate transaction/outbox
   |
   v
Reconcile metrics + review + reprocess
```

For an order import batch, you might quarantine `UNKNOWN_PRODUCT` and `INVALID_AMOUNT`, yet halt the entire job if the input file is missing or the database is unreachable. For a critical financial batch, even a single invalid record may require failing the job and demanding sign-off; quarantine can still be recorded for investigation, but the policy for **allowing completion with errors** must be defined separately.

## Conclusion

Quarantining invalid items is part of a **data quality and operability** architecture, not just a `SkipListener`. A sound design must **classify errors accurately**, preserve immutable source identity, store reason codes and review statuses, guarantee consistency between valid output and the quarantine store, bound skipped errors, and support restart and reprocessing without duplicating results.

When Spring Batch reports `COMPLETED` with skips, the system must still be able to answer: **how many items were accepted, how many were quarantined, why they were rejected, who will handle them, and how corrected data returns to the pipeline in a controlled manner**.

## References

- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): how to configure `faultTolerant`, `.skip(...)`, and `.skipLimit(...)`.
- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): `SkipListener`, callbacks, and step/chunk lifecycle.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): distinguishing transient errors needing retry from invalid items.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): managing `ExecutionContext` and reader/writer restarts.
- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): parsing, line mapping, and `FlatFileItemReader`.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): testing jobs/steps, skips, and output data.

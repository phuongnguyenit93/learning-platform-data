# Never Let Skip Become Silent Data Loss in Spring Batch

A Spring Batch job can finish with status `COMPLETED` while its output data is **missing hundreds or thousands of records**. Sometimes the cause is not an obvious crash: the step was configured with `faultTolerant().skip(...)` and silently dropped items it could not process. Without rejection reporting, input–output reconciliation, and publish gating, downstream consumers see an incomplete dataset without knowing records were dropped.

In **Spring Batch Core Processing → Data quality**, this lesson explains how to use skip as an **intentional, bounded, auditable** fault-tolerance mechanism rather than a way to hide bad data. It walks from the `skip`/`filter`/`retry` model, `StepExecution` counters, and safe rejection recording, through ratio and completeness checks, to designing a **quality gate** before publishing data. Examples use **Java 17, Spring Boot 3.x, Spring Batch 5.x, JUnit 5, and JDBC**.

## 1. The Problem: `COMPLETED` Does Not Always Mean "No Data Lost"

Suppose a nightly job imports 100,000 orders whose results must be consumed by reporting systems the next morning:

```text
Input: 100,000 orders
       |
       v
FlatFileItemReader
       |
       v
ItemProcessor
       |-- 450 invalid items ---> SKIP
       |-- 100 cancelled items -> FILTER (return null)
       v
ItemWriter
       |
       v
Output: 99,450 orders

Step status: COMPLETED
```

If policy permits skipping up to 500 items, the step above can finish `COMPLETED`: Spring Batch executed its **technical** configuration accurately. Yet if business rules allow at most 50 invalid items, **this result must not be published**. If 100 orders were filtered without an approved business rule, that can also constitute data loss.

Therefore distinguish:

- **Technical success:** the job/step finished according to the framework's configured flow and fault-tolerance policy.
- **Data quality success:** the output satisfies error thresholds, completeness rules, reconciliation, uniqueness, value totals, and business conditions.
- **Publication success:** only a verified result is published for downstream consumption.

These three conditions do not substitute for one another. A batch "running to completion" does not mean the data is "complete and accurate."

## 2. How Do Skip, Filter, Retry, and Rollback Differ?

### 2.1. `skip`: Bypassing a Failing Item

In a chunk-oriented step with `.faultTolerant()`, Spring Batch can skip an item when the thrown exception belongs to the configured skip list and total skips remain below the limit.

Example:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(20)
```

With this policy, the step can continue after up to 20 skipped items under the active rules. On the 21st skippable item, the step fails due to exceeding the limit. **`skipLimit` caps total skips across read/process/write phases**, not 20 per phase.

**Consequence:** skipped items do not appear in the writer's normal output. When completeness is required, skipping must be approved and leave an audit trail for correction or make-up delivery.

### 2.2. `filter`: Processor Intentionally Withholding an Item from the Writer

An `ItemProcessor` can return `null`:

```java
@Override
public Order process(RawOrder item) {
    if ("CANCELLED".equals(item.status())) {
        return null; // Intentional filter.
    }
    return map(item);
}
```

This is **filtering**, not skipping. It increments `filterCount` rather than `skipCount`. If code accidentally executes `return null` on a mapping error, data can vanish without ever touching `skipLimit`.

So always ask: **which records may be filtered, why, and must filter counts be reconciled?** Never use `return null` as a default catch-all for exceptions.

### 2.3. `retry`: Retrying Before Deciding the Outcome

An API may time out on the first call and succeed on the next. When an exception is retried, the initial error **does not mean the item was skipped**:

```text
order-010:
    attempt 1 -> TemporaryServiceException
    attempt 2 -> TemporaryServiceException
    attempt 3 -> SUCCESS -> writer

Result: 1 item written, 0 items skipped.
```

Conversely, a malformed date will not fix itself on retry. Separate **transient errors** from **permanent data errors** so you never retry or skip arbitrarily.

### 2.4. `rollback` and `restart` Do Not Undo Previously Committed Data

When a chunk fails, that chunk's transaction rolls back. However, **earlier committed chunks** do not automatically roll back just because the job later ends `FAILED`. On restart, Spring Batch uses `JobRepository` and checkpoints to determine what work remains; writers must be designed to be idempotent.

```text
Chunk 1 -> COMMITTED (100 rows)
Chunk 2 -> COMMITTED (100 rows)
Chunk 3 -> FAILED

JobExecution -> FAILED
Yet the 200 rows from chunks 1 and 2 may remain in the database.
```

This is especially critical when writing straight to production tables: readers can observe partial data. **Staging + quality gate + conditional publish** prevents that hazard.

## 3. Turning "Silent Data Loss" into Concrete Scenarios

Not every record absent from the writer is a bug. Yet **every path an item takes** must have a reason and reconcilable counts.

| Item Path | Example | How Detected | What Must Be Controlled |
| --- | --- | --- | --- |
| Accepted | Valid order | `writeCount`, output count | Written exactly once with exact values |
| Skipped in read | Malformed CSV row | `readSkipCount` | Source locator for fixing; never mask schema failure |
| Skipped in process | Business-invalid data | `processSkipCount` | Reason code and rejection record |
| Skipped in write | DB rejects a skippable item | `writeSkipCount` | Never turn system DB failures into dropped data |
| Filtered | Canceled transaction per rule | `filterCount` | Approved filter criteria and explicit stats |
| Retried then succeeded | API timeout then recovered | Separate retry metric | Do not count as final rejection |
| Read failed fatally | Bad file/header across source | Job/step `FAILED` | Do not publish incomplete results |
| Lost before reader | Truncated file, missing partition | Preflight/manifest | `skipCount` can be 0 while data is still missing |
| Duplicated on restart | Committed chunk replayed | Business key/reconciliation | Do not count rows alone; verify uniqueness |

**Key conclusion:** `skipCount=0` does not prove data completeness. The source may be missing records, the reader may stop early, or the processor may filter items. Conversely, `skipCount>0` does not automatically require rejecting the whole result: the **data-quality contract** for each batch decides.

## 4. Defining a Data Quality Contract Before Configuring Skip

An input contract should clearly state:

1. **Source and version:** `sourceBatchId`, `businessDate`, file version/snapshot ID, and schema version.
2. **Completeness:** expected record count, required partitions or files, manifest, and checksum.
3. **Validation:** required fields, data types, value ranges, references, and uniqueness.
4. **Allowed rejects:** skippable error types, max count, max ratio, and critical rules.
5. **Allowed filters:** intentionally excluded items and whether counts/ratios are bounded.
6. **Reconciliation:** how record counts, amount totals, unique keys, or checksums are compared.
7. **Publication:** conditions to mark the batch `PUBLISHED` and expose it downstream.
8. **Recovery:** how items are fixed, rejects replayed, source versions replaced, restarted, and audited.

Example rules for a 20,000-order batch:

```yaml
sourceBatchId: orders-20261116-v1
schemaVersion: 2
expectedRecords: 20000
quality:
  rejectAbsoluteMax: 25
  rejectRatioMax: 0.001
  criticalErrorCodes:
    - MISSING_ORDER_ID
    - DUPLICATE_BUSINESS_KEY
  allowedFilters:
    - CANCELLED_BY_SOURCE
  publishRequires:
    - manifestValid
    - sourceToOutputReconciled
    - quarantineDurable
    - totalsMatched
```

This is a **business contract example**, not YAML automatically parsed by Spring Batch. `rejectRatioMax: 0.001` is 0.1%; across 20,000 records that allows at most 20 rejects. With both an absolute cap of 25 and a 0.1% ratio, **both must hold**, so the effective limit at this scale is 20.

If `MISSING_ORDER_ID` is treated as a critical error, even **one** item with that code can block publishing, even while total rejects stay below 20.

### 4.1. Classifying Errors by Tolerance Level

| Error Group | Examples | Policy |
| --- | --- | --- |
| Row-level recoverable data issue | Optional field malformed yet fixable later | Skip/quarantine within budget |
| Business-critical invalidity | Missing identifier key, negative total in financial reconciliation | Fail or block publish |
| Source-wide error | Wrong header, unsupported schema version, checksum mismatch | Fail in preflight before writing |
| Infrastructure transient | Database deadlock, HTTP 503 | Bounded retry; do not label item invalid |
| Programmer/configuration error | Unexpected null pointer, missing table, broken mapping | Fail; never `.skip(Exception.class)` |

Never configure skip solely to raise `COMPLETED` job percentages. A batch skipping 90% of its items and finishing `COMPLETED` is a **quality policy failure**, not a data success.

## 5. Configuring Bounded Skip in Spring Batch 5

Suppose a job imports an order CSV, the reader reads fields as strings, the processor validates, and the writer inserts into a **staging table**. When a record has an invalid amount, the processor throws a classified business exception.

### 5.1. Data Models and Exception

```java
package com.example.batch;

import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String status,
        String amountText) {}

public record AcceptedOrder(
        String orderId,
        BigDecimal amount) {}

public class InvalidOrderException extends RuntimeException {
    private final String reasonCode;

    public InvalidOrderException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
```

In real Java projects, each `public` top-level type lives in its own file (`RawOrder.java`, `AcceptedOrder.java`, `InvalidOrderException.java`). They are grouped here to show all related types together. `reasonCode` must belong to an approved safe code set, never containing raw CSV lines or personal data.

### 5.2. Processor: Intentional Filter, Errors Throw Exceptions

```java
package com.example.batch;

import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class OrderValidationProcessor
        implements ItemProcessor<RawOrder, AcceptedOrder> {

    @Override
    public AcceptedOrder process(RawOrder row) {
        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("MISSING_ORDER_ID");
        }

        // Approved filter rule that must be reconciled.
        if ("CANCELLED".equals(row.status())) {
            return null;
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(row.amountText());
        } catch (NumberFormatException | NullPointerException ex) {
            throw new InvalidOrderException("INVALID_AMOUNT");
        }

        if (amount.signum() <= 0) {
            throw new InvalidOrderException("NON_POSITIVE_AMOUNT");
        }

        return new AcceptedOrder(row.orderId(), amount);
    }
}
```

This processor does not swallow exceptions and return `null` for invalid items. It filters only when `status=CANCELLED`, following an explicit business rule. Records with bad amounts throw `InvalidOrderException` so the framework counts skips and the rejection mechanism records reasons.

Another business decision might be **never filtering canceled orders** and instead storing them with a canceled status. In that case, change both the processor and quality contract rather than blindly copying this example's filter rule.

### 5.3. CSV Reader and Dedicated Preflight

Suppose the file has a header:

```csv
order_id,status,amount
o-001,ACTIVE,150.00
o-002,ACTIVE,BAD
o-003,CANCELLED,200.00
o-004,ACTIVE,50.00
```

The reader uses `@StepScope` to resolve the validated path from `JobParameters`:

```java
@Bean
@StepScope
FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("order_id", "status", "amount")
            .fieldSetMapper(fields -> new RawOrder(
                    fields.readString("order_id"),
                    fields.readString("status"),
                    fields.readString("amount")))
            .build();
}
```

This bean requires imports from `org.springframework.batch.item.file.*`, `org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder`, `org.springframework.batch.core.configuration.annotation.StepScope`, Spring `@Bean`, `@Value`, and `FileSystemResource`.

**Important point:** `.linesToSkip(1)` only skips the header; **it does not prove the header is valid**. In real jobs, include a `validateSourceStep` checking the manifest, schema version, column list, checksum, file/partition counts, and source immutability. File-wide errors must fail before processing or publishing; never turn 20,000 parse errors into 20,000 skipped records.

The `inputFile` parameter must also resolve inside authorized directories/sources rather than accepting arbitrary untrusted user paths.

### 5.4. Step Skipping Only Known Exceptions

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> reader,
        OrderValidationProcessor processor,
        ItemWriter<AcceptedOrder> stagingWriter,
        SkipListener<RawOrder, AcceptedOrder> rejectListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<RawOrder, AcceptedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(stagingWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(25)
            .listener(rejectListener)
            .build();
}
```

Reader, processor, writer, and reject listener beans are project-configured components. With Spring Batch 5, `StepBuilder` uses the `JobRepository` and transaction manager passed to the chunk step. Here the writer **must write to staging**, never exposing partially skipped data directly downstream.

This configuration:

- Permits skipping at most **25 items** when `InvalidOrderException` occurs within policy scope.
- Does not auto-skip `SQLException`, connection errors, unexpected `NullPointerException`, or arbitrary exceptions.
- Does not itself know the 0.1% **ratio** threshold or critical error codes: a quality gate in later sections handles that.
- Does not itself guarantee durable rejection writes: the listener must pair with an appropriate quarantine/audit store.

This example targets validation errors in the processor. If certain `FlatFileParseException`s in the reader must also be skippable, add that **deliberately**, after defining how read errors are recorded and traced. Never skip all read errors by default.

## 6. Reading `StepExecution` Counters Accurately

Spring Batch maintains several counters, each with a specific meaning:

| Counter | Core Meaning | Do Not Misinterpret As |
| --- | --- | --- |
| `getReadCount()` | Items successfully read per the step | Physical file line count in all cases |
| `getReadSkipCount()` | Skips during read | Failed input file count |
| `getProcessSkipCount()` | Skips during process | Every time processor threw an exception |
| `getWriteSkipCount()` | Skips during write | Every write failure or rollback |
| `getSkipCount()` | Total skips | Retry count |
| `getFilterCount()` | Items filtered by processor (`null`) | Skipped invalid items |
| `getWriteCount()` | Items written by writer per step | Actual DB rows existing or published in every design |
| `getRollbackCount()` | Recorded rollbacks | Failed item count |
| `getCommitCount()` | Recorded commits | Logical source chunk count |

For the four-record CSV example in section 5, if the step allows skips:

```text
Input records: 4
readCount: 4
processSkipCount: 1   (o-002 INVALID_AMOUNT)
filterCount: 1        (o-003 CANCELLED)
writeCount: 2         (o-001 and o-004)
skipCount: 1
```

When **one input yields at most one output**, with no duplicates, no non-transactional outputs, and standard reader/processor/writer assumptions, you can reconcile:

```text
input_count = accepted_count + rejected_count + filtered_count
4 = 2 + 1 + 1
```

Never apply that sum blindly if the processor emits multiple outputs, the reader parses multiline records, the writer writes multiple tables, the job uses upserts, items are dropped before the reader, or a `JobExecution` restarted across multiple runs. **Quality reports must define their units of measurement explicitly.**

### 6.1. Logging a Post-Step Summary

Use `StepExecutionListener` to log a summary:

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class QualitySummaryListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(QualitySummaryListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "event=batch_step_quality step={} execution_id={} "
                + "status={} read={} write={} filter={} skip={} "
                + "read_skip={} process_skip={} write_skip={}",
                step.getStepName(),
                step.getId(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getSkipCount(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount());

        return null; // Keep the step's ExitStatus if no change is desired.
    }
}
```

This listener makes **visible** the difference between `COMPLETED` and "zero rejections." Still, a summary log is not the source of truth for publishing. Publish decisions must rest on verified durable metrics and evidence, rather than parsing a log line.

## 7. Recording Each Skipped Item Without Leaking Data

Every skipped item needs **a reason, origin, and remediation path**. Yet logging raw objects for convenience is dangerous:

```java
log.warn("Skipped item={} cause={}", item, error);
```

`item.toString()` or exception messages may contain emails, account numbers, raw CSV lines, SQL statements, and sensitive fields. Instead, use a safe reference token together with an approved reason code:

```text
event=batch_item_skipped
job=importOrdersJob
step=importOrdersStep
source_batch_ref=orders-20261116-v1
stage=process
item_ref=7e12d3cf18c51a9b
reason_code=INVALID_AMOUNT
```

`item_ref` can be derived from a stable business ID using **HMAC-SHA-256 with a secret key**, or a random token with a protected mapping. Never use `hashCode()`, MD5, or unkeyed SHA-256 on guessable emails/order IDs and assume they are anonymized. If policy prohibits item-level references in logs, log step-level counters and place details in an access-controlled quarantine store.

### 7.1. `SkipListener` Records Final Skips, Not Every Retry

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class SafeRejectListener
        implements SkipListener<RawOrder, AcceptedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(SafeRejectListener.class);

    private final SafeReferenceFactory references;

    public SafeRejectListener(SafeReferenceFactory references) {
        this.references = references;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        // No reliable RawOrder is available in the read phase.
        log.warn("event=batch_item_skipped stage=read "
                + "item_ref=unavailable reason_code=READ_REJECTED");
    }

    @Override
    public void onSkipInProcess(RawOrder item, Throwable error) {
        log.warn(
                "event=batch_item_skipped stage=process "
                + "item_ref={} reason_code={}",
                references.forOrder(item.orderId()),
                safeReason(error));
    }

    @Override
    public void onSkipInWrite(AcceptedOrder item, Throwable error) {
        log.warn(
                "event=batch_item_skipped stage=write "
                + "item_ref={} reason_code=WRITE_REJECTED",
                references.forOrder(item.orderId()));
    }

    private String safeReason(Throwable error) {
        if (error instanceof InvalidOrderException e) {
            return switch (e.reasonCode()) {
                case "INVALID_AMOUNT" -> "INVALID_AMOUNT";
                case "NON_POSITIVE_AMOUNT" -> "NON_POSITIVE_AMOUNT";
                case "MISSING_ORDER_ID" -> "MISSING_ORDER_ID";
                default -> "INVALID_ORDER";
            };
        }
        return "UNCLASSIFIED_FAILURE";
    }
}
```

In this example, `SafeReferenceFactory` is a **project-implemented service** whose `forOrder(String)` method returns a protected token. This is a placeholder contract, **not a built-in Spring Batch class**. When `orderId` is blank or `null`, the service should return `"unavailable"` rather than printing the raw ID or throwing an exception inside the listener.

`READ_REJECTED` and `WRITE_REJECTED` are high-level examples; in real applications, classify specific approved exceptions without logging verbatim `getMessage()` strings.

Spring Batch calls `SkipListener` when an item is **genuinely skipped** by a fault-tolerant step. Meanwhile, `ItemProcessListener.onProcessError()` can fire on an attempt that later succeeds on retry. **Never rely on `onProcessError` event counts to compute final rejections.**

### 7.2. Quarantine Is Not the Same as Logs

To let data teams fix items, maintain a **durable reject/quarantine store** with attributes:

| Field | Purpose |
| --- | --- |
| `source_batch_id` | Source batch that sent the record |
| `source_version` | Immutable file/snapshot version |
| `record_locator` | Source key or versioned record position |
| `stage` | Read/process/write |
| `reason_code` | Fixed error code for grouping |
| `rejected_at` | Timestamp recorded |
| `job_execution_id` | Traces the run |
| `payload_pointer` | Location of encrypted/access-controlled raw payload |
| `review_status` | NEW, CORRECTED, REPLAYED, DISMISSED, etc. |

Sensitive payloads do not have to live in the same log/audit table: store a **pointer** to the immutable source file or protected object storage accessible only to authorized remediation tools.

`SkipListener` can record rejection metadata, yet mind **transaction boundaries**. Logs sent to a logging backend do not roll back with chunks. Writes to a separate datasource also do not automatically join the writer's transaction. Where strict auditability is required, design a reject store/outbox with idempotency keys and aligned transactions, and check quarantine write failures. Never let quarantine fail while the batch still reports successful publication.

### 7.3. Preserving Traceability on Parse Failures

`onSkipInRead(Throwable)` receives no item because the reader could not construct an object. For CSV files, record `source_file_version` and `line_number` **if the reader reliably exposes them**. Still, parse exceptions can contain the raw input line; never print full exceptions or log `FlatFileParseException.getInput()` to general logs.

If files can mutate across restarts, line numbers alone cannot identify records. Pair immutable file versions/checksums with technical positions, or extract a record ID from a protected source.

## 8. Quality Gate: Checking Before Publishing

`skipLimit(25)` only guards against exceeding **25 skipped items in one `StepExecution`**; it does not check reject ratios, critical error codes, manifest completeness, or data freshness. Place a **separate quality gate** between import and publish:

```text
Validate source / manifest
        |
        v
Import to staging
        |        \
        |         \--> Rejected items --> Quarantine
        v
Reconcile + Quality gate
        |
        +-- reject > allowed ----------> FAILED / NOT_PUBLISHED
        +-- critical reject -----------> FAILED / NOT_PUBLISHED
        +-- manifest mismatch ---------> FAILED / NOT_PUBLISHED
        +-- output totals mismatch ----> FAILED / NOT_PUBLISHED
        |
        v
Publish approved snapshot
        |
        v
Downstream readers
```

Here the staging table carries `source_batch_id` or version so downstream **never reads in-flight data**. Only when the gate passes does the job publish a snapshot or atomically update `published_version` by design. A job failing at the gate step does not roll back earlier committed chunks; they stay in staging for investigation or cleanup per policy.

### 8.1. Quality Result Model Independent of Batch Status

```java
package com.example.batch.quality;

public record QualitySnapshot(
        long sourceExpected,
        long accepted,
        long rejected,
        long filtered,
        long criticalRejected,
        boolean sourceVerified,
        boolean quarantineVerified,
        boolean businessTotalsMatched) {}

public record QualityDecision(
        boolean publishAllowed,
        String reasonCode) {}
```

Here `accepted`, `rejected`, and `filtered` are **contract-reconciled figures**, not necessarily pulled directly from a single `StepExecution`. This matters when a job restarts across multiple executions, uses multiple steps/partitions, or has an upserting writer.

### 8.2. Easily Testable Pure-Java Policy

Example policy allowing at most 25 rejects and a ratio no higher than 0.1%, while tolerating zero critical errors:

```java
package com.example.batch.quality;

public final class QualityPolicy {

    private static final long ABSOLUTE_MAX_REJECTED = 25;
    private static final long MAX_REJECT_PER_MILLION = 1_000;
    // 1,000 / 1,000,000 = 0.001 = 0.1%.

    public QualityDecision evaluate(QualitySnapshot s) {
        if (!s.sourceVerified()) {
            return new QualityDecision(false, "SOURCE_NOT_VERIFIED");
        }
        if (!s.quarantineVerified()) {
            return new QualityDecision(false, "REJECT_AUDIT_INCOMPLETE");
        }
        if (!s.businessTotalsMatched()) {
            return new QualityDecision(false, "BUSINESS_TOTAL_MISMATCH");
        }
        if (s.sourceExpected() <= 0) {
            return new QualityDecision(false, "INVALID_EXPECTED_COUNT");
        }
        if (s.accepted() < 0 || s.rejected() < 0
                || s.filtered() < 0 || s.criticalRejected() < 0) {
            return new QualityDecision(false, "INVALID_COUNTS");
        }
        if (s.criticalRejected() > 0) {
            return new QualityDecision(false, "CRITICAL_REJECT");
        }
        if (s.rejected() > ABSOLUTE_MAX_REJECTED) {
            return new QualityDecision(false, "REJECT_COUNT_EXCEEDED");
        }

        // Avoid floating-point arithmetic when comparing ratio thresholds.
        // BigInteger prevents overflow when multiplying very large longs.
        var rejectsScaled = java.math.BigInteger
                .valueOf(s.rejected())
                .multiply(java.math.BigInteger.valueOf(1_000_000L));
        var allowedScaled = java.math.BigInteger
                .valueOf(s.sourceExpected())
                .multiply(java.math.BigInteger.valueOf(
                        MAX_REJECT_PER_MILLION));

        if (rejectsScaled.compareTo(allowedScaled) > 0) {
            return new QualityDecision(false, "REJECT_RATIO_EXCEEDED");
        }

        var accounted = java.math.BigInteger.valueOf(s.accepted())
                .add(java.math.BigInteger.valueOf(s.rejected()))
                .add(java.math.BigInteger.valueOf(s.filtered()));

        if (!accounted.equals(
                java.math.BigInteger.valueOf(s.sourceExpected()))) {
            return new QualityDecision(false, "COUNT_MISMATCH");
        }

        return new QualityDecision(true, "QUALITY_APPROVED");
    }
}
```

All `record`s and classes in the example live in their matching files under `com.example.batch.quality`. `QualityPolicy` is application business code, not a built-in Spring Batch API.

The ratio check uses integer multiplication to avoid premature rounding. With `sourceExpected=20,000`, 0.1% allows at most **20 rejects**; `rejected=21` must be blocked even though it is below the absolute cap of 25.

**Counting condition:** `accepted + rejected + filtered == sourceExpected` applies when each input record falls into **exactly one** of the three buckets. If a job aggregates many records into one output, splits one record into many outputs, deduplicates, or upserts, build an equivalent reconciliation using business keys and transformation rules. Never tweak the policy to "pass" an unexplained mismatch.

### 8.3. Wiring the Quality Gate into the Job Flow

Implement the gate in a tasklet after import, running publish only if the gate succeeds:

```java
@Bean
Step qualityGateStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        QualityReportRepository reports,
        QualityPolicy policy) {

    return new StepBuilder("qualityGateStep", repository)
            .tasklet((contribution, chunkContext) -> {
                String sourceBatchId =
                        (String) chunkContext.getStepContext()
                                .getJobParameters()
                                .get("sourceBatchId");

                QualitySnapshot snapshot =
                        reports.loadFinalSnapshot(sourceBatchId);
                QualityDecision decision = policy.evaluate(snapshot);

                if (!decision.publishAllowed()) {
                    throw new IllegalStateException(
                            "QUALITY_GATE_FAILED:" + decision.reasonCode());
                }
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

`QualityReportRepository` here is a **project-defined business interface** whose `loadFinalSnapshot(String)` returns durable reconciled figures from manifest, staging, quarantine, and other verification sources. It is **not** a built-in Spring Batch repository; the example focuses on gate integration.

When the gate step throws an exception, the step/job becomes `FAILED` and the downstream publish step **does not run in the default linear flow**. Avoid transition rules like "run publish even on FAILED." Reason codes inside the exception are sanitized to avoid leaking sensitive data.

With beans `validateSourceStep`, `importOrdersStep`, `qualityGateStep`, and `publishStep`, the overall flow is:

```java
@Bean
Job importOrdersJob(
        JobRepository repository,
        Step validateSourceStep,
        Step importOrdersStep,
        Step qualityGateStep,
        Step publishStep) {

    return new JobBuilder("importOrdersJob", repository)
            .start(validateSourceStep)
            .next(importOrdersStep)
            .next(qualityGateStep)
            .next(publishStep)
            .build();
}
```

Real code needs imports for `org.springframework.batch.core.Job`, `org.springframework.batch.core.Step`, `JobBuilder`, `StepBuilder`, `JobRepository`, `RepeatStatus`, `PlatformTransactionManager`, `@Bean`, and the project's quality classes. The job flow is a template; reader, writer, preflight, and publish steps must be implemented alongside it.

## 9. Source, Staging, and Quarantine Must Be Reconcilable

### 9.1. Example Batch-Scoped Result Tables

A system might maintain business tables:

```sql
CREATE TABLE import_batch (
    source_batch_id VARCHAR(100) PRIMARY KEY,
    business_date DATE NOT NULL,
    expected_count BIGINT NOT NULL,
    source_verified BOOLEAN NOT NULL,
    quality_status VARCHAR(30) NOT NULL,
    publish_status VARCHAR(30) NOT NULL
);

CREATE TABLE staging_order (
    source_batch_id VARCHAR(100) NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (source_batch_id, order_id)
);

CREATE TABLE rejected_record (
    source_batch_id VARCHAR(100) NOT NULL,
    record_locator VARCHAR(200) NOT NULL,
    reason_code VARCHAR(60) NOT NULL,
    payload_pointer VARCHAR(500),
    review_status VARCHAR(30) NOT NULL,
    PRIMARY KEY (source_batch_id, record_locator)
);
```

This DDL is a minimal example omitting indexes, audit timestamps, foreign keys, partitioning, or encryption. If a record can be rejected multiple times for multiple reasons, expand `rejected_record`'s key or add a history table. Tie `source_batch_id` to an **immutable source version** rather than just a file path.

### 9.2. Reconciliation Is More Than Row Counts

Example showing two different situations with the same 99,990 output count:

```text
Case A: 10 records missing, 0 duplicates.
Case B: 20 records missing, 10 records duplicated.

Output count can be 99,990 in both cases.
```

Therefore verify across multiple dimensions:

| Reconciliation Check | What It Detects |
| --- | --- |
| Source total vs. accepted + rejected + filtered | Records lacking an explicit outcome |
| Unique business key count | Duplicate writes or missing uniqueness |
| Value/grouped totals | Missing/wrong records or amounts |
| Checksum / manifest | Incomplete or altered source |
| Source key set minus accepted/rejected/filtered | Unclassified lost records |
| Publish status by `source_batch_id` | Downstream reading unapproved data |

When the source is an event stream without a manifest "expected row count," use **offset ranges, watermarks, snapshot tokens, or input partition contracts** as the baseline. "The reader returned all currently available records" does not prove upstream emitted every event.

### 9.3. Atomic Publishing

After the quality gate passes, a safe pattern updates a **pointer to the approved version** inside a transaction:

```text
staging snapshot v1  --> QUALITY_FAILED, unpublished
staging snapshot v2  --> QUALITY_APPROVED
                             |
                             v
                   published_version = v2
                             |
                             v
                    downstream reads v2
```

When publishing files, build the complete file in a temporary area and **rename/mark ready using atomic semantics appropriate** for the filesystem/object store. When publishing in a database, use transactions and unique keys so incomplete snapshots are never exposed. Exact mechanics depend on storage.

Never let downstream run `SELECT * FROM staging_order` without filtering `publish_status`; when a job is `FAILED`, committed staging chunks remain present yet unapproved.

## 10. Restart and Replay: Skips Need a Recovery Path

Suppose `orders-20261116-v1` has 12 rejects; the system allows temporary publishing since 12 is within threshold, while those 12 still need fixing:

1. Persist rejected records in quarantine with `sourceBatchId` and `recordLocator`.
2. Route reason codes to the source owner through an access-controlled channel.
3. Produce a corrected data version or a replay bundle of rejected records.
4. Execute replay with stable business keys; the writer uses matching unique constraints/upserts/idempotency.
5. Reconcile totals after replay and update quarantine status to `REPLAYED`.
6. If an earlier report was published, decide whether to publish a **new result version** and notify downstream.

Never adopt "skip and forget." Even if the business temporarily tolerates a small loss rate, enforce a **reject-fix SLA** or a policy documenting the final accepted outcome.

### 10.1. Restarting the Same Instance vs. Replaying a New Batch

- **Restart:** a `FAILED` or `STOPPED` job reruns with the **same identifying `JobParameters`** and metadata/checkpoints; Spring Batch creates a new `JobExecution` under the same `JobInstance` when permitted.
- **Replay / new version:** the source was fixed or replaced as `sourceBatchId=v2`; typically starts a new `JobInstance` to process the new immutable source with duplicate protection.

**Never swap the source file under the same path/checkpoint and expect restarts to work.** Reader positions may point to wrong records after edits. Keep sources immutable or versioned, and choose restart vs. replay intentionally.

### 10.2. Observing Metrics Across Restarts

Counters in `StepExecution` belong to **one step execution**. When a restart skips a step that already finished `COMPLETED` in the prior run, you cannot inspect `jobExecution.getStepExecutions()` of the new run to infer total batch counts. A reliable quality gate must read durable metrics keyed by `sourceBatchId` across manifest, staging, quarantine, and execution history. That is why section 8 used `QualityReportRepository` instead of reading `skipCount` from the latest step alone.

## 11. When Data Fails En Masse, Fail Fast

Scattered validation errors differ from thousands of rows breaking because the source schema changed:

```text
09:00: New source schema deployed
01:00: Nightly import starts
01:01: First 200 records cannot be parsed
01:02: Skip count keeps rising
```

If the job uses `.skip(Exception.class).skipLimit(1000000)`, it may burn hours skipping nearly the whole file. A better strategy:

- **Preflight** headers, schemas, file completeness, and manifests.
- Use a skip allowlist strictly for permitted record errors.
- Halt immediately on critical reason codes (`MISSING_ORDER_ID`, incompatibility).
- Set `skipLimit` as a **technical circuit breaker** to stop runaway errors.
- Use a **quality gate** to enforce reject ratios and completeness.
- Alert immediately when error rates spike within a sliding window, without waiting for job completion.

Also, infrastructure errors like HTTP 503 or database unavailability **must never be turned into invalid data and bulk-skipped**. Use bounded retries, backoff, concurrency limits, and stop/restart strategies once dependencies recover.

## 12. Observability and Alerting Against Silent Data Loss

Record batch-level metrics:

| Metric | Purpose |
| --- | --- |
| `source.expected` | Expected source records/units |
| `source.verified` | Source verification status |
| `batch.accepted` | Business-accepted items |
| `batch.rejected` | Rejected items with durable reject records |
| `batch.filtered` | Intentionally filtered items |
| `batch.unaccounted` | Items lacking outcomes or reconciliation |
| `batch.reject.ratio` | Reject ratio relative to source total |
| `batch.critical.rejected` | Count of critical rejects |
| `quarantine.pending` | Items awaiting fix/replay |
| `publish.approved` | Whether batch passed the quality gate |
| `publish.age` | Freshness/lag of latest published snapshot |

Logs should include `job_name`, `step_name`, `job_execution_id`, `source_batch_ref`, `reason_code`, and permitted summary states. Avoid logging full `JobParameters`, payloads, emails, or stack traces holding source data. Per-item/quarantine IDs belong in access-controlled searchable logs, **never in metric labels** due to high cardinality.

Sample alert policy:

```text
WARN:
  reject_ratio > 0.05% over the last 5,000 records

CRITICAL:
  reject_ratio > 0.1%
  OR critical_rejected > 0
  OR source_expected != accounted_records
  OR quality_gate = FAILED
  OR quarantine_write_failed
```

These percentages are **illustrative thresholds** that must be calibrated to business data. On small batches, ratios over the first few records fluctuate wildly; for early alerts, require a minimum sample size so brief spikes are not mistaken for systemic failure.

## 13. Testing Skip and Data Quality with JUnit 5

Tests must not stop at asserting job `COMPLETED`. Explicitly test item counts across every branch, error thresholds, and publish gating.

### 13.1. Fixture Suite

Create test files:

```text
src/test/resources/orders/
  ├── all-valid.csv
  ├── one-rejected.csv
  ├── filter-and-reject.csv
  ├── reject-limit-exceeded.csv
  ├── invalid-header.csv
  └── truncated-source.csv
```

Example `filter-and-reject.csv`:

```csv
order_id,status,amount
o-001,ACTIVE,150.00
o-002,ACTIVE,BAD
o-003,CANCELLED,200.00
o-004,ACTIVE,50.00
```

Expected counts under the section 5 processor: accepted 2, rejected 1, filtered 1. Real integration tests need dedicated test staging, audit, and `JobRepository` tables to avoid wiping data in shared environments.

### 13.2. Testing Quality Policy Independently

Because `QualityPolicy` takes a snapshot and returns a decision, it can be tested without booting Spring:

```java
package com.example.batch.quality;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class QualityPolicyTest {

    private final QualityPolicy policy = new QualityPolicy();

    @Test
    void approvesReconciledSmallRejectCount() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_975, 20, 5, 0,
                true, true, true);

        QualityDecision result = policy.evaluate(snapshot);

        assertThat(result.publishAllowed()).isTrue();
        assertThat(result.reasonCode()).isEqualTo("QUALITY_APPROVED");
    }

    @Test
    void rejectsTooManyRelativeToSource() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_974, 21, 5, 0,
                true, true, true);

        QualityDecision result = policy.evaluate(snapshot);

        assertThat(result.publishAllowed()).isFalse();
        assertThat(result.reasonCode())
                .isEqualTo("REJECT_RATIO_EXCEEDED");
    }

    @Test
    void rejectsCriticalProblemEvenUnderLimit() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_994, 1, 5, 1,
                true, true, true);

        assertThat(policy.evaluate(snapshot).reasonCode())
                .isEqualTo("CRITICAL_REJECT");
    }

    @Test
    void rejectsMissingRecordsEvenWithZeroSkips() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_900, 0, 0, 0,
                true, true, true);

        assertThat(policy.evaluate(snapshot).reasonCode())
                .isEqualTo("COUNT_MISMATCH");
    }

    @Test
    void rejectsMissingQuarantineEvidence() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_975, 20, 5, 0,
                true, false, true);

        assertThat(policy.evaluate(snapshot).reasonCode())
                .isEqualTo("REJECT_AUDIT_INCOMPLETE");
    }
}
```

These tests distinguish **within ratio**, **exceeds ratio**, **critical error**, **unaccounted records**, and **missing quarantine evidence**. They do not replace step integration tests, yet provide fast feedback on publish-gate logic.

### 13.3. Integration with `@SpringBatchTest`

In a Spring Boot + Gradle project, add:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

A typical integration test should:

1. Launch the job via `JobLauncherTestUtils` with dedicated `sourceBatchId` and `inputFile`.
2. Assert `StepExecution.getReadCount()`, `getFilterCount()`, `getProcessSkipCount()`, and `getWriteCount()`.
3. Query staging to verify actual record counts and business values.
4. Query quarantine to confirm each rejection persisted durably with the right reason code and locator.
5. Verify the quality gate **prevents publish from running** when ratio/count/critical rules fail.
6. For valid data within thresholds, verify the published version and checksum/totals.
7. Trigger a restart after a deliberate failure using the **exact same identifying parameters**; confirm zero duplicate writes.

Example assertion excerpt after launching a test job (beans and fixtures prepared by the application):

```java
JobExecution execution =
        jobLauncherTestUtils.launchJob(testParameters);

StepExecution importStep = execution.getStepExecutions().stream()
        .filter(step -> "importOrdersStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow();

assertThat(importStep.getReadCount()).isEqualTo(4);
assertThat(importStep.getProcessSkipCount()).isEqualTo(1);
assertThat(importStep.getFilterCount()).isEqualTo(1);
assertThat(importStep.getWriteCount()).isEqualTo(2);
```

This is an **assertion snippet**, not a standalone runnable test file; `jobLauncherTestUtils`, `testParameters`, `assertThat`, and job configuration must exist in the test class. For flows with quality gates and publish steps, also assert final status, target tables, and publish metadata. Restart tests must account for steps that finished `COMPLETED` in the prior execution rather than assuming every step reappears in the new execution.

### 13.4. Essential Test Matrix

| Scenario | Expected Skip / Quality / Publish Behavior |
| --- | --- |
| 100% valid items | Zero skips, zero out-of-policy filters; publish |
| 1 permitted invalid item | Skip recorded, durable quarantine; publish if gate passes |
| 1 item with `status=CANCELLED` | `filterCount` increments; tracked separately from skips |
| 21 rejects / 20,000 items, 0.1% limit | Under `skipLimit(25)`, yet gate blocks publish |
| 26 rejects / 20,000 items with `skipLimit(25)` | Step exceeds skip limit and fails |
| One critical reason code | Gate rejects despite tiny reject count |
| Wrong file-wide header | Fails in preflight; not treated as row skips |
| Manifest declares 20,000 yet file has 19,900 | Blocks publish even with `skipCount=0` |
| Quarantine write fails | Reject outcome rather than allowing un-audited data loss |
| Retries twice then succeeds | Does not count as final skip |
| Writer failure causes rollback | Committed output counts stay accurate; staging/idempotency verified |
| Restart or replay | Zero duplicate writes; quality snapshot reflects entire batch |

## 14. Common Implementation Pitfalls

| Mistake | Why It Is Dangerous | Prevention |
| --- | --- | --- |
| `.skip(Exception.class)` and huge `skipLimit` | Masks widespread data defects and infra outages | Skip only classified exceptions |
| Checking only `BatchStatus.COMPLETED` | Hides how many items were dropped | Check skips, filters, reconciliation, and publish status |
| Processor `catch(Exception)` then `return null` | Turns errors into un-audited filters | Filter only by business rule; errors raise exceptions |
| Missing manifest/preflight | Truncated files still show `skipCount=0` | Verify source/partitions/checksums |
| Logging full rejected items | Sensitive data leak | Fixed reason codes and safe tokens |
| Not persisting quarantine | Nobody knows which records need fixing | Reject store with locator, version, reason |
| Async quarantine without confirmation | Job may publish while evidence is lost | Outbox/ack/reconciliation before publish |
| Writing straight to production tables | Job fails after committed chunks, downstream sees gaps | Stage first, then conditionally publish |
| Using `skipCount` as batch-wide error total | Restarts/partitions have multiple executions and scoped counters | Aggregate by source batch and durable audits |
| Reconciling row counts alone | Missing and duplicate rows can cancel out | Check keys, business totals, checksums |
| Creating new `run.id` to restart | Loses continuation on the same `JobInstance` | Keep identifying parameters on restart |
| Mutating source file while reusing checkpoint | Reader resumes at wrong offset | Immutable source versions, v2 replays |
| Putting item IDs in metric labels | Cardinality explosion, data exposure | Label by job/step/reason code |

## 15. Practice Exercise

Build `importOrdersJob` with `validateSourceStep`, `importOrdersStep`, `qualityGateStep`, and `publishStep`, given a 20,000-record input batch, `skipLimit=25`, 0.1% max reject ratio, and zero tolerance for `MISSING_ORDER_ID`.

1. Create a 20,000-record valid fixture. Run the job and confirm source, staging, quarantine, and published counts reconcile.
2. Add 10 records with invalid amounts. Verify they are skipped/quarantined, and the job publishes only when both ratio and reconciliation pass.
3. Increase errors to 21 records. Demonstrate the difference between `skipLimit=25` (step can complete) and the 0.1% threshold (gate must reject).
4. Increase to 26 errors. Verify the step halts due to exceeding `skipLimit` and staging data remains unpublished.
5. Create one item missing its order ID. Assign `MISSING_ORDER_ID` and confirm the gate rejects despite the tiny reject count.
6. Add 50 `CANCELLED` items and have the processor filter them per policy. Confirm `filterCount` increments while `skipCount` does not.
7. Have the manifest declare 20,000 items while the file contains only 19,900. Verify the job blocks publishing even when zero exceptions were skipped.
8. Inject a quarantine or outbox write failure. Verify the job cannot mark a batch eligible to publish without durable rejection evidence.
9. Simulate a writer failure after two committed chunks. Restart the job with the same identifying parameters, reconciling staging and unique keys to avoid duplicates.
10. Create source version v2 containing corrected records. Replay per defined policy, update quarantine statuses, and publish a new snapshot if needed.

**Core principle:** `skip` is an **item-level error handling decision**, not a license to drop data silently. Every source item must end with an accounted-for **accepted, rejected, or filtered** outcome under an explicit contract; rejects must have durable evidence and a recovery path; and data may only be published after passing count, ratio, completeness, and business-rule checks. Only then can Spring Batch tolerate item-level faults while preserving full trust in output data.

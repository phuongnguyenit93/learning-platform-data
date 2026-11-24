# Overly Broad Skip Hiding Data Errors in Spring Batch

In Spring Batch, `skip` allows a `Step` to skip a failing item and continue processing the remaining items, provided the exception type and skip count satisfy the configured policy. This is a useful mechanism when data sources are imperfect: a malformed CSV line, an optional record failing validation, or a single corrupt record need not halt an entire batch of millions of records.

However, **overly broad skip** is a dangerous design flaw. When an application allows skipping nearly every exception, a job can finish `COMPLETED` while thousands of transactions are dropped, mandatory data goes unwritten, a schema change causes every record to fail, or the writer could not even connect to the database. An operator seeing only a green status will assume all data was loaded completely.

**Core principle:** *skip must be a scoped, bounded, reconcilable data-quality decision—not a blanket way to hide every failure.* In **Spring Batch Core Processing → Common Pitfalls**, this lesson explains how skip works across reader/processor/writer, why `.skip(Exception.class)` can be dangerous, how to classify errors, how to configure appropriate limits, how to handle rejects/quarantine, verify outputs, and build tests that prevent silent data loss.

Examples use Spring Batch 5.x or later with Java 17+, `JobRepository`, and chunk-oriented steps. Domain classes like `InvalidPaymentRecordException` are illustrative application-defined classes.

## 1. Signs of an Overly Broad Skip Policy

Suppose a job imports 10,000 payment rows from a CSV file into a database. Due to a data-type misconfiguration, 7,500 rows fail, yet the step skips every exception with a huge limit:

~~~java
// Anti-pattern: can mask many failures that are not isolated bad records.
.faultTolerant()
.skip(Exception.class)
.skipLimit(Integer.MAX_VALUE)
~~~

If the thrown exceptions are handled by the skip mechanism without exceeding the limit, the step can finish successfully with very few records written. "COMPLETED" only reflects that the job reached the end under its policy; **it does not prove output data is complete**.

A dashboard showing only:

~~~text
Job importPaymentsJob: COMPLETED
~~~

will hide the truth:

~~~text
Expected source:      10,000 records
Read/written:          2,500 records
Skipped:               7,500 records
Result:               potential severe business data loss
~~~

This is not always a framework bug. Spring Batch is doing exactly what the configuration asked for: **skipping eligible errors up to the limit**. The bug lies in the data quality contract and an inappropriate skip policy.

### Why Do Developers Fall Into This Trap?

- Wanting to "let the batch finish" before a deadline, so raising `skipLimit` to an enormous number.
- Not distinguishing **input record** exceptions from **infrastructure** exceptions.
- Running into various unfamiliar errors and picking `Exception.class` instead of identifying root causes.
- Confusing `COMPLETED` with "every record was processed successfully".
- Lacking a reject report or reconciliation between input and output record counts.
- Tests asserting only status without checking actual committed data.
- Wanting to avoid halting the job for a bad record while lacking a quarantine mechanism to handle it later.

## 2. How Does Skip Differ from Retry, Filter, and Fail?

In a chunk-oriented step, each mechanism carries a distinct meaning:

| Mechanism | Behavior | When is it appropriate? | Data impact |
|---|---|---|---|
| **Filter** | `ItemProcessor.process(...)` returns `null`; item is not sent to writer. | Valid record outside processing scope, e.g., `amount = 0` per published rules. | Intentionally excludes the record; `filterCount` increments. |
| **Skip** | An exception is deemed skippable by policy; step continues. | Isolated bad record, within an acceptable limit and with reporting. | Record may be absent from output; skip counter increments. |
| **Retry** | Re-attempts operation after specified exceptions. | Likely transient errors, such as deadlocks or flaky connections. | May re-invoke reader/processor/writer; replay must be safe. |
| **Fail** | Step stops with failure status. | Misconfiguration, inaccessible data, invalid mandatory data, or errors exceeding threshold. | Preserves incident trace for fix/restart; prior chunks may have committed. |

Examples:

- A row with status `CANCELLED` when the job only processes `APPROVED`: can be **filtered** if the contract explicitly states so.
- A malformed CSV row permitted to be excluded from a reference export: can be **skipped** within a limit.
- Database reports a brief deadlock: can be **retried** with backoff.
- Target database table is missing after a migration: must **fail** and fix infrastructure, not skip every item.
- A mandatory ledger transaction has an illegal negative amount: usually must **fail** or move the job into an unapproved state; never auto-skip and report the ledger complete.

An exception in a processor does not automatically mean the record may be skipped. Ask: **must this record be included in the result?**, **is the cause input data or code?**, and **is excluding the record approved by the business?**

## 3. How Spring Batch Counts Skips

In a fault-tolerant step, `SkipPolicy` decides whether a `Throwable` may be skipped given the current skip count. Common builder APIs:

~~~java
.faultTolerant()
.skip(InvalidPaymentRecordException.class)
.skipLimit(5)
~~~

Here:

- `.faultTolerant()` enables retry/skip controls for the chunk step.
- `.skip(...)` specifies exception types allowed to be skipped.
- `.skipLimit(5)` sets the **total skip budget for the step**: read, process, and write skips all contribute to the step's skip count per step mechanics. Exceeding the limit causes the step to fail.
- Exceptions not configured for skipping normally fail the step unless handled by another retry/handler mechanism.

In common Spring Batch configurations, if `skipLimit` is omitted when configuring skip this way, the builder's default limit is **10**; do not rely on defaults for critical quality requirements. Declare thresholds explicitly in configuration and operational docs.

### Three Skip Types

`StepExecution` provides the counters:

| Counter | Where the error occurs | Interpretation |
|---|---|---|
| `getReadSkipCount()` | `ItemReader`, e.g., failure parsing a CSV line. | An input unit could not be read as a valid item and was skipped by policy. |
| `getProcessSkipCount()` | `ItemProcessor` throws an exception. | Item was read but produced no output due to a skipped error. |
| `getWriteSkipCount()` | `ItemWriter` fails to write an item per policy. | Item was excluded during write; may require rollback and writer re-invocation to isolate. |
| `getSkipCount()` | Total skips for the step. | Sum across skip stages recorded by `StepExecution`. |

Do not confuse `filterCount` with skips. When a processor returns `null`, that is a **filtered** item, not a skipped error.

`readCount` typically counts items successfully returned by the reader, **not necessarily the physical lines in a file**. Headers, configured skipped lines, and reader-specific handling can create differences. When reconciling files, define clearly how physical data lines are counted and work against a fixed source snapshot.

### An Absolute Skip Limit Does Not Equal a Safe Error Rate

Suppose `skipLimit=50`:

- On a 1,000,000-line file, 50 rejects represent a tiny fraction.
- On a 20-line file, 19 rejects still stay under 50; the job can finish with almost no input producing output.

Therefore, an absolute threshold alone may be insufficient. Many domains also need a **percentage threshold**, **per-error-type thresholds**, and a **strict no-skip rule for certain record groups**. Percentage thresholds are not a built-in `skipLimit` property; they can be checked in a post-processing quality gate step using the data source and reject report.

## 4. Why Is .skip(Exception.class) Dangerous?

`Exception.class` is a very broad superclass covering checked exceptions and many runtime exceptions. Configuring:

~~~java
.faultTolerant()
.skip(Exception.class)
.skipLimit(1000000)
~~~

can treat all errors **that pass through the skip mechanism** as skip candidates, such as:

- `FlatFileParseException` from malformed CSV data.
- `IllegalArgumentException` or `IllegalStateException` from broken processor logic.
- `NullPointerException` from an application bug on a branch.
- `DataIntegrityViolationException` from violated data constraints.
- Exceptions from the reader failing to fetch expected data.
- Exceptions from the writer failing to write to the database or call an external system.

Not every framework or transaction failure can be skipped cleanly. Some errors still fail the step despite a broad policy because safe recovery is impossible. Even so, **having just a few critical errors skipped is enough to corrupt data**.

### Example 1: Schema Changed

Upstream CSV renames a column from `amount` to `amount_cents`, while reader/processor still expect the old name. If every row throws and gets skipped, the job can read the whole file while producing almost zero output.

This is a **file-wide contract error**, not a few isolated bad rows. The right action is **fail-fast in a preflight step** (checking headers, column counts, schema version) before bulk processing.

### Example 2: Writer Lost Write Permissions

The runtime role loses `INSERT` permission on the target table after a migration. Every chunk fails. If an overly broad skip policy tries to isolate individual items, the system may perform wasteful work, increase load, and distort output counts.

A database permission error must be **fixed in infrastructure**, not turned into "invalid records".

### Example 3: Processor Has a Bug

~~~java
public PaymentOutput process(PaymentInput payment) {
    // A refactor introduced a bug when currency is null.
    String currency = payment.currency().toUpperCase();
    return new PaymentOutput(payment.id(), currency, payment.amount());
}
~~~

If `currency == null` triggers a `NullPointerException`, `.skip(Exception.class)` can hide the fact that code failed to handle input per contract. The fix may be explicit validation or a policy for missing currency—**not treating every NPE as a record to discard**.

### Example 4: Non-Idempotent HTTP Writer

The writer sends a transaction to an API and gets a timeout after the API already processed it. If the error is skipped without reconciliation, the job may report the transaction as skipped even though the side effect occurred at the partner. If retried without an idempotency key, the side effect may even double.

This is not merely a skip-limit issue. It involves **transaction boundaries**, **uncertain outcomes**, and **recoverability** of targets outside the database.

## 5. Classify Exceptions Before Setting a Policy

The safe approach is to explicitly define error categories, responses, and remediation owners:

| Error category | Example | Usually appropriate decision |
|---|---|---|
| **Isolatable malformed record** | A CSV line with wrong column count under allowed reject policy. | Bounded skip, record error location/quarantine. |
| **Permitted business validation reject** | Optional field badly formatted or record outside acceptance rules. | Skip the exact business exception type, with audit. |
| **Mandatory record** | Payment transaction that must be processed in full. | Fail or block publish; never auto-skip. |
| **Source-wide schema/format error** | Wrong header, missing required column, wrong file charset. | Fail-fast before step or upon structural error detection. |
| **Programming bug** | NPE, class cast, impossible state. | Fail and fix the code. |
| **Database transient** | Deadlock, temporary lock timeout. | Bounded retry with backoff when safe. |
| **Database permanent** | Missing table, invalid SQL, missing privileges, mandatory data constraint. | Fail; fix schema/privileges/data. |
| **Non-transactional side effect** | HTTP timeout after POST. | Query status or use idempotency; never skip blindly. |
| **Resource exhaustion** | Disk full, quota exceeded, sustained connection pool exhaustion. | Fail, restore resources, then restart. |

Classifying by **business semantics** matters more than exception class names. For instance, `DataIntegrityViolationException` could be an allowed duplicate or a foreign-key violation reflecting broken data. If the mechanism cannot distinguish them, do not skip the whole class.

### Use Dedicated Business Exceptions

Instead of throwing `IllegalArgumentException` everywhere, represent records permitted for rejection with a dedicated type:

~~~java
public final class SkippablePaymentValidationException
        extends RuntimeException {

    private final String errorCode;

    public SkippablePaymentValidationException(String errorCode) {
        super(errorCode); // Do not embed sensitive data in the message.
        this.errorCode = errorCode;
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

And another exception for mandatory data violations:

~~~java
public final class CriticalPaymentException extends RuntimeException {
    public CriticalPaymentException(String errorCode) {
        super(errorCode);
    }
}
~~~

Only `SkippablePaymentValidationException` goes into the skip list. `CriticalPaymentException` fails the step under standard policy. Separating exceptions must align with approved business rules; renaming a class does not by itself make an error safe to skip.

## 6. Example: Small Dataset Showing Valid vs. Dangerous Skip

Suppose we process a payment file:

~~~csv
event_id,currency,amount
PAY-001,VND,100000
PAY-002,VND,50000
PAY-003,VND,abc
PAY-004,VND,0
PAY-005,VND,-20000
PAY-006,VND,70000
PAY-007,VND,30000
~~~

Illustrative rules:

1. Every positive amount with a valid currency is written exactly once.
2. `amount=0` is **intentionally filtered**, because the job only imports balance-affecting transactions.
3. Unparseable amount on an isolated line may be **read skipped**, up to the allowed threshold.
4. Negative amounts are rejected; in a **non-financial reference** job it may be process-skipped by policy; in a mandatory accounting ledger job it must **fail** without applying a skip policy.
5. If the `amount` header is missing or many lines fail schema together, the entire file must **fail preflight**, never treated as "a batch of bad records".

With a policy allowing rejects on items 3 and 5, expected outcomes:

| Record | Outcome | Reason |
|---|---|---|
| `PAY-001` | Written | Valid amount. |
| `PAY-002` | Written | Valid amount. |
| `PAY-003` | Read skip | `abc` cannot parse as a number. |
| `PAY-004` | Filter | Amount equals 0 per contract. |
| `PAY-005` | Process skip | Negative amount, reject policy permits it in this illustrative problem. |
| `PAY-006` | Written | Valid amount. |
| `PAY-007` | Written | Valid amount. |

~~~text
sourceDataLines   = 7        (excluding header)
readCount         = 6        (items parsed successfully)
readSkipCount     = 1
filterCount       = 1
processSkipCount  = 1
writeSkipCount    = 0
writeCount        = 4
actualOutputRows  = 4
expectedAmountVND = 250000
~~~

Source breakdown:

~~~text
7 source lines
  ├── 1 read reject      (PAY-003)
  └── 6 items read successfully
        ├── 1 filtered    (PAY-004)
        ├── 1 process reject (PAY-005)
        └── 4 accepted/written
~~~

In this example, the difference `7 - 4 = 3` is cleanly accounted for by 1 read skip, 1 process skip, and 1 filter. If the job were mandatory accounting that forbids rejecting PAY-005, that single record appearing is already a **data incident that must block publishing**, even if the job had technical skip configured.

Note: equations like `sourceDataLines = readSkip + filter + processSkip + written` only hold when **every line is classified exactly once**, mapping is 1:1, there is no special deduplication, and counters reflect a completed execution. In practice, also reconcile committed target data against the source manifest.

## 7. Narrow Skip Configuration in Spring Batch 5

A safer step configuration:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> reader,
        ItemProcessor<PaymentInput, PaymentOutput> processor,
        ItemWriter<PaymentOutput> writer,
        SafePaymentSkipListener skipListener) {

    return new StepBuilder("importPaymentsStep", jobRepository)
        .<PaymentInput, PaymentOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(SkippablePaymentValidationException.class)
        .skipLimit(5)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .listener(skipListener)
        .build();
}
~~~

Here:

- Only validation exceptions explicitly marked as permissible rejects are in the skip list.
- `.skipLimit(5)` bounds total skips across the step, not five separate skips per stage.
- Transient database access errors are directed to **retry**, not skip.
- SQL schema errors, missing permissions, and NPEs are not in the skip list, so they are never legitimized as arbitrary rejects.
- `chunk(100, transactionManager)` defines transaction boundaries; if the writer fails and rolls back, items may be re-entered for processing.

The example uses application-defined `PaymentInput`, `PaymentOutput`, and `SafePaymentSkipListener` beans. You cannot copy the fragment verbatim without those beans/classes; the code's goal is to illustrate **policy configuration**.

### When Skipping CSV Parse Errors

`FlatFileItemReader` can throw `FlatFileParseException` when a line fails to parse. You can add:

~~~java
.skip(org.springframework.batch.item.file.FlatFileParseException.class)
.skipLimit(5)
~~~

**Only do so once you are certain parse errors are isolatable at the line level.** `FlatFileParseException` can arise from many parse/mapping errors, including source format changes. Skipping the entire class without validating headers, column counts, version/schema, and anomaly thresholds can still mask **an entire incompatible file**.

A better design:

1. Preflight the file: validate header, encoding, schema version, path, and manifest.
2. In the reader: allow skipping only contract-permitted line errors; record line location and standardized error code.
3. At the quality gate: fail if reject count/rate exceeds policy or the source shows signs of widespread errors.

There is no need to allow skipping parse failures in every batch. For "all-or-nothing" sources like closing ledger tables, a single bad line may be reason to halt the entire job.

## 8. Custom SkipPolicy When Rules Are More Complex

When errors must be classified dynamically by exception type and current skip count, Spring Batch supports `SkipPolicy`. Example policy skipping only `SkippablePaymentValidationException` with a budget of five:

~~~java
import org.springframework.batch.core.step.skip.SkipPolicy;

public final class NarrowPaymentSkipPolicy implements SkipPolicy {

    private static final long MAX_SKIPS = 5;

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount) {
        if (!(throwable instanceof SkippablePaymentValidationException)) {
            return false; // Other errors must follow failure handling.
        }

        // Some framework paths may probe the classifier with skipCount < 0:
        // evaluate only the error type without enforcing the count limit.
        if (skipCount < 0) {
            return true;
        }

        return skipCount < MAX_SKIPS;
    }
}
~~~

Registration:

~~~java
.faultTolerant()
.skipPolicy(new NarrowPaymentSkipPolicy())
~~~

This example is a **pure deterministic** policy: the same error type and same skip count yield the same decision. It avoids a mutable self-incrementing counter inside a singleton, since the classifier callback may be called at different moments or to probe skippability. If you need multiple error categories with separate budgets, design stateful counters aligned with execution/transaction boundaries, or run an audited quality gate.

Cases requiring more care than this policy:

- Exceptions wrapped in one or more `cause`s. If unwrapping, use a trusted wrapper list so infrastructure failures are never mistaken for validation errors.
- One record having multiple errors. Define error code precedence and a single reject outcome.
- Rules based on business data like "VIP records must not be skipped". Prefer throwing a **different exception** for critical records or checking eligibility in validation rather than guessing from raw exception messages.
- Error-rate thresholds across the whole file. `skipCount` alone does not know final source row counts; use the manifest and quality gate.
- Parallel steps: each step/partition has its own counters, so job-wide limits require aggregation and additional checks.

Do not rely on `SkipPolicy` to compensate for a missing data contract. Policies must be derived from business questions: **which record types may be dropped, how many at most, and who remediates the dropped items?**

## 9. Retry the Right Errors, Never Turn Infrastructure Failures into Rejects

If a database deadlocks or is briefly unreachable, the error may disappear on retry. With a JDBC writer participating in the chunk transaction, retrying after rollback can make sense if writes are safe to replay.

Example:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(SkippablePaymentValidationException.class)
.skipLimit(5)
~~~

Key points:

- **Retry** transient errors with bounded attempts and appropriate backoff.
- **Skip** only approved rejectable data errors—never skip database connectivity loss.
- When retries are exhausted, the step must **fail** or follow a purposefully designed policy. Never default to turning retry-exhausted errors into skips.
- Do not use `.retry(Exception.class)` for bugs or bad data; schema or logic bugs will not heal themselves.

### Writer Errors May Not Be Safe to Skip

In chunk-oriented processing, a writer may receive a whole chunk of items. If one item in the chunk throws, the framework may roll back and re-invoke the writer to isolate the failing item per fault-tolerance mechanics. This assumes prior write attempts can be rolled back or safely replayed.

Suppose the writer sends POSTs to an API outside the transaction; a timed-out request may still have been processed by the API. Skipping the item after a timeout **does not prove** the item produced no side effect. Before allowing writer skips:

1. Check whether the target shares a transaction/rollback with the chunk.
2. Can target status be queried by event ID?
3. Is there a stable idempotency key for re-invocation?
4. Does the exception indicate an **individual item** or an entire target outage?
5. If skipped, does output still satisfy the business contract?

If you cannot answer these, prefer **fail, reconcile, and recover under control** instead of auto-skipping.

## 10. SkipListener: Log Reject Reasons Without Exposing Data

One problem with overly broad skips is that **no one knows which records were dropped**. Spring Batch provides `SkipListener` for all three stages:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class SafePaymentSkipListener
        implements SkipListener<PaymentInput, PaymentOutput> {

    private static final Logger log =
        LoggerFactory.getLogger(SafePaymentSkipListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn("batch.item.skipped stage=READ category=FILE_FORMAT");
    }

    @Override
    public void onSkipInProcess(PaymentInput item, Throwable error) {
        log.warn("batch.item.skipped stage=PROCESS category=VALIDATION");
    }

    @Override
    public void onSkipInWrite(PaymentOutput item, Throwable error) {
        log.warn("batch.item.skipped stage=WRITE category=OUTPUT_REJECTED");
    }
}
~~~

This is an **illustrative safe-logging listener** without quarantine persistence logic. In real applications, classify the error category accurately by exception and handling policy; not every reader error is `FILE_FORMAT`, nor is every writer error a data error.

Avoid doing this:

~~~java
log.warn("Skipped item={} exception={}", item, error);
~~~

`item.toString()` may contain names, emails, account numbers, amounts, or tokens. `FlatFileParseException.getInput()` may return the entire failing CSV line; exception messages/causes may also expose data. Log **jobExecutionId, stepExecutionId, errorCode, resource alias, and line number** when verified safe—never dump raw items.

### Routing Bad Records to Quarantine

For critical sources, rejects need a follow-up workflow. You can create a **quarantine store** with fields:

| Field | Role |
|---|---|
| `batchKey` | Identifies the period/source version. |
| `sourceId` / `resourceAlias` | Identifies the logical source. |
| `sourceRecordRef` | Opaque ID or line number when appropriate; avoids exposing sensitive data. |
| `stage` | READ, PROCESS, or WRITE. |
| `errorCode` | Standardized error code, containing no raw messages. |
| `jobInstanceId` / `jobExecutionId` | Traces the run that detected the error. |
| `disposition` | NEW, UNDER_REVIEW, CORRECTED, REPROCESSED, or REJECTED_FINAL. |
| `recordPayloadRef` | Reference to access-controlled sensitive data storage if needed. |

Quarantine is a **protected data store**, not a general logger. Access permissions, retention, and encryption must match data classification.

Watch the interaction of skip callbacks, rollbacks, and transactions: if a listener writes a record to a non-transactional system, it may be re-invoked or leave artifacts inconsistent with the final commit state. Ensure **idempotency** for quarantine records, such as a unique key on `(batchKey, sourceRecordRef, errorCode)` when business semantics permit. If no source record ID exists on a read error, use a designed surrogate like `(fileVersion, lineNumber)`.

Do not assume a simple `SkipListener` guarantees exactly-once across multi-threaded or remote steps. Quarantine records must be reconciled against durable skip counts after the step finishes.

## 11. Protecting Data with Reconciliation, Not Just Job Status

A job can finish `COMPLETED` with many valid skips. To know whether results can be published, perform a source-to-target reconciliation:

~~~mermaid
flowchart TD
    A["Source snapshot + manifest"] --> B["Read / Process / Write"]
    B --> C["StepExecution counters"]
    B --> D["Reject / filter audit"]
    B --> E["Committed output"]
    C --> F["Reconciliation + quality gate"]
    D --> F
    E --> F
    F --> G{"Meets contract?"}
    G -->|Yes| H["Publish / report success"]
    G -->|No| I["Block publish + report error"]
~~~

A simple reconciliation equation in a 1:1 pipeline on fixed data:

\[
\text{sourceDataRows}
= \text{readRejected} + \text{filtered}
+ \text{processRejected} + \text{writeRejected} + \text{acceptedOutputRows}
\]

This equality is **conditional**: every row must be classified exactly once, inputs must not change mid-run, there must be no 1:n or n:1 outputs, no special deduplication policy, and values must reflect final committed outcomes. Otherwise, adjust the grain and calculation.

### Minimum Quality Gate

For an import job, you can enforce:

- `sourceDataRows` comes from the locked manifest, not from `writeCount`.
- Every reject has an error category and traceable source reference.
- `totalSkipCount` does not exceed the **absolute threshold**.
- `rejectRate` does not exceed the approved **percentage threshold**.
- **Critical** record categories are never skipped.
- `expectedAcceptedRows` equals **the count of unique business keys in committed output**, under a 1:1 contract.
- If data carries monetary values, totals per currency must also reconcile with zero discrepancy outside defined tolerance.
- No missing/extra keys even when total counts match.

Example:

~~~text
batchKey           = 2026-11-15:warehouse-A:v1
sourceDataRows     = 7
readRejected       = 1
filtered           = 1
processRejected    = 1
writeRejected      = 0
expectedOutputRows = 4
actualOutputRows   = 4
expectedAmountVND  = 250000
actualAmountVND    = 250000
qualityResult      = PASS_WITH_REJECTS
~~~

`PASS_WITH_REJECTS` is an **application-defined quality status**, not a default `BatchStatus`. It is accepted only if rejects stay within business policy. For a system that forbids rejects in a payment group, those exact same numbers must produce `FAIL`.

### Do Not Compare Counts Alone

Valid input has IDs `A, B, C`; output has `A, B, B`. Both counts equal 3, yet **C is missing and B is duplicated**. If a unique constraint makes the writer drop duplicates via `ON CONFLICT DO NOTHING`, `writeCount` still does not always equal newly inserted rows.

Therefore, compare by **business key**, such as finding missing IDs with a SQL anti-join, in addition to comparing counts and amount totals.

## 12. Make the Quality Gate a Separate Step

An easily operated pattern is **load → reconcile → publish**:

~~~java
@Bean
Job importPaymentsJob(
        JobRepository jobRepository,
        Step loadPaymentsStep,
        Step reconcilePaymentsStep,
        Step publishPaymentsStep) {

    return new JobBuilder("importPaymentsJob", jobRepository)
        .start(loadPaymentsStep)
        .next(reconcilePaymentsStep)
        .next(publishPaymentsStep)
        .build();
}
~~~

`loadPaymentsStep` may be `COMPLETED` even after skips within budget. `reconcilePaymentsStep` evaluates policy from the source snapshot, reject counters/audits, and committed output. On mismatch or quality threshold breach, the step should fail appropriately to prevent `publishPaymentsStep` from running on the success path.

Benefits:

1. Batch status reflects not only whether code finished running, but also whether data meets publishing conditions.
2. A discrepancy below `skipLimit` yet exceeding the reject rate or violating critical groups can still be blocked.
3. Dashboards can separate **infrastructure failures**, **record rejects**, and **reconciliation failures**.
4. Results can be durably stored alongside `batchKey`, source version, timestamp, and execution ID for audit.

In systems where output cannot be "recalled" once the writer commits, write into **staging partitioned by batch/version** and publish only after the quality gate. Never expose unreconciled output to downstream consumers if the contract requires batch-level all-or-nothing.

### Example SQL to Verify Output

Suppose output is stored by processing period:

~~~sql
CREATE TABLE processed_payment (
    batch_key VARCHAR(120) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, event_id)
);

SELECT
    COUNT(*) AS actual_rows,
    COUNT(DISTINCT event_id) AS distinct_ids,
    COALESCE(SUM(amount), 0.00) AS actual_amount
FROM processed_payment
WHERE batch_key = :batchKey
  AND currency = 'VND';
~~~

When multiple currencies exist, reconcile per currency instead of summing different currencies together. Ensure the expected amount is computed from the **normalized source** excluding rejects/filters per rules—never copy expected from output.

If missing keys must be checked, use a staging table `accepted_payment` containing the locked accepted record set:

~~~sql
SELECT a.event_id
FROM accepted_payment a
LEFT JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND p.event_id IS NULL;
~~~

The result must be empty when every accepted record must have exactly one output. For outputs present outside the accepted set, run the anti-join in the reverse direction. Use this comparison only when `accepted_payment` is genuinely an independent expected source.

## 13. Overly Broad Skip Under Partitioning and Parallel Execution

When using partitioned steps, multi-threaded steps, or remote chunking, the risk of "skips still under threshold" grows if each worker/partition has its own budget.

For example:

~~~text
partition-A: skipLimit=10, skipped=9
partition-B: skipLimit=10, skipped=9
partition-C: skipLimit=10, skipped=9

Job-wide total: 27 records dropped
~~~

If the business permits **at most 10 rejected records for the entire period**, giving each partition `skipLimit=10` does not enforce the global constraint. Each partition's `StepExecution` has its own counters; the manager may aggregate per partitioning mechanics, yet business policy must be verified against **the final job-wide result set**.

With multiple workers:

- Quarantine needs a unique key to avoid duplicate reject entries when workers retry.
- Read/write/skip figures across attempts must not be summed mechanically when replay occurs.
- Link rejects to `batchKey` and `partitionId`, yet verify unique business keys globally.
- Run the quality gate only after all required partitions have finished/been verified.
- If a partition suffers an infrastructure failure, never treat its entire missing output as "permissible skipped records".

A check against the source manifest and target database avoids relying solely on local worker statistics.

## 14. Retry, Rollback, Restart, and Idempotency Interactions with Skip

A writer error can roll back the chunk transaction and re-invoke the writer. If an item is skipped after several attempts, **writer invocations** do not equal successfully written items. Listeners and logs may fire at different moments under retry/rollback, so do not infer output counts from log message counts.

### Earlier Chunks Can Still Have Committed

~~~text
chunkSize=3

Chunk 1: A, B, C  -> COMMITTED
Chunk 2: D, E, F  -> writer error -> ROLLBACK
JobExecution #1: FAILED

JobExecution #2: restart of the same JobInstance
          -> reprocesses uncommitted portion from checkpoint
~~~

If the skip policy on chunk 2 is too broad, the system may drop D/E/F and report the step complete even though mandatory output is missing. Once fixed and restarted, earlier chunks still exist; hence the writer needs idempotency and metadata must remain intact.

Do not delete `BATCH_*` tables or add a new `run.id` merely to get past a failed state. Creating a new `JobInstance` with random identifying parameters can re-run the entire input and duplicate side effects.

### Reject Auditing and Restart

Suppose the first run recorded `REJECTED` for record R; after fixing the source, the restart processes R. Define clearly:

- Is record R retained in reject history with status `RESOLVED`, or is a new audit entry created?
- Does the quality gate of the **current source version** count R as accepted or rejected?
- May input be edited when restarting the same `JobInstance`, or must a new source version/revision be created to preserve snapshots?
- If a write committed before the checkpoint was acknowledged on the same resource, could the record reappear?

A sound design stores `batchKey` + `sourceVersion` + business key + final outcome, while keeping attempt history separate when needed. **Do not sum every reject across all execution attempts as if it were the count of unique permanently dropped records.**

## 15. A Minimal Test Suite to Catch Overly Broad Skip

Testing only the happy path fails to detect silently dropped data. Use fixtures small enough to know exactly which category every record belongs to:

| Scenario | Data/exception | Expectation |
|---|---|---|
| Valid records | 3 valid items | Zero skips, 3 outputs. |
| Permitted validation reject | 1 `SkippablePaymentValidationException` | Process skip counter increments, quarantine records reason. |
| Exceeding skip limit | 6 skippable records, `skipLimit=5` | Step `FAILED` when limit is exceeded. |
| Critical record error | `CriticalPaymentException` | Step `FAILED` immediately per policy, no skip. |
| Programming bug | `NullPointerException` from processor | Step `FAILED`, not legitimized as a reject. |
| Permitted reader format error | 1 malformed CSV line | Read skip recorded, data position preserved safely. |
| Wrong header/schema | Missing required column | Preflight fails before bulk processing. |
| Transient database error | Deadlock first, succeeds next | Retries within limit, output written once. |
| Database lacks privileges | Writer denied permissions | Step `FAILED`, no mass write skips. |
| Reject rate exceeds threshold | 10-line file, 4 rejects, `skipLimit=5` | Quality gate `FAIL` if 40% rate is disallowed. |
| Rule-based filtering | Amount 0 | `filterCount` increments, not counted as skip. |
| Count matches but key missing | A, B, C → A, B, B | Reconciliation catches missing C / duplicate B. |
| Writer fails mid-chunk | Partial write in transaction then error | Chunk rolls back; uncommitted rows are not counted. |
| Job restart | One chunk committed before failure | Final output has no duplicates and all business keys. |

### Example Counter Assertions After Integration Test

Assuming `JobLauncherTestUtils` and configured test beans:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;

JobExecution execution = jobLauncherTestUtils.launchJob(testParameters);

assertThat(execution.getStatus())
    .isEqualTo(BatchStatus.COMPLETED);

StepExecution step = execution.getStepExecutions()
    .stream()
    .filter(s -> s.getStepName().equals("importPaymentsStep"))
    .findFirst()
    .orElseThrow();

assertThat(step.getReadSkipCount()).isEqualTo(1);
assertThat(step.getProcessSkipCount()).isEqualTo(1);
assertThat(step.getWriteSkipCount()).isZero();
assertThat(step.getFilterCount()).isEqualTo(1);
assertThat(step.getWriteCount()).isEqualTo(4);

// Important: query the output database by batchKey and verify:
// 4 exact business keys; no duplicates; VND total = 250000.
~~~

This is an illustrative test fragment; `jobLauncherTestUtils`, `testParameters`, and the specific step are initialized in the test context. `BatchStatus.COMPLETED` only makes sense when **policy permits the fixture's rejects**. For jobs that forbid dropping records, tests must expect `FAILED` rather than forcing the assertions above to pass.

### Test to Guard Against Broad Exceptions

A regression test should intentionally have the processor throw `NullPointerException` or an infrastructure exception, then assert:

~~~java
assertThat(execution.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(step.getProcessSkipCount()).isZero();
~~~

That way, if someone changes the configuration from `.skip(SkippablePaymentValidationException.class)` to `.skip(Exception.class)`, the test catches the dangerous change.

Checking **actual committed output** always matters more than checking loggers or a single `writeCount` number. In cases with UPSERT/dedup or writers emitting multiple outputs per item, compare at the exact business grain.

## 16. Operational Alerting When Skips Spike

A job can run "green" for days, then a vendor changes a file format and skips jump 100x. If the system only alerts on `BatchStatus.FAILED`, the data incident can linger undetected.

Metrics to track:

| Metric | How to use |
|---|---|
| `readSkipCount` | Detect abnormal spikes in parse/source read errors. |
| `processSkipCount` | Detect validation or business mapping violations. |
| `writeSkipCount` | Detect rejected output records; check transactions/idempotency. |
| `filterCount` | Track shifts in the distribution of filtered valid records. |
| `skipped / sourceDataRows` | Reject ratio against locked source, not divided by an ambiguous counter. |
| `writeCount` vs. actual output rows | Reconcile writer activity against real data. |
| `errorCode` frequency | Pinpoint rising reject causes like file schema, missing field, invalid amount. |
| `batchKey` / source version | Trace data periods without merging versions or execution attempts. |

Alert tiers you can configure:

- **Warning:** skips rise above baseline, yet remain within quality thresholds.
- **Critical:** any "must-not-skip" error appears, reject rate breaches policy, or key/amount reconciliation fails.
- **Block publish:** do not publish output when the batch fails the quality gate, even if the load step `COMPLETED`.

Avoid using `jobExecutionId` or individual record IDs as standard metric labels due to high cardinality. Use logs/audits for detailed IDs, and metrics for bounded dimensions like `jobName`, `stepName`, `errorCode`, and `status`.

### Safe Handling of Sensitive Information

Do not print full CSV lines or entire items to explain a skip. Failing records may hold accounts, emails, national IDs, or tokens. Logs can contain:

~~~json
{
  "event": "batch.item.skipped",
  "batchKey": "2026-11-15:warehouse-A:v1",
  "jobExecutionId": 8102,
  "stepName": "importPaymentsStep",
  "stage": "PROCESS",
  "errorCode": "INVALID_AMOUNT",
  "sourceRecordRef": "line-6"
}
~~~

This is an **application-defined log schema**. Raw data stays only in the source or access-controlled quarantine. `sourceRecordRef` must be designed safely; never use emails/phone numbers as log keys.

## 17. Remediation Workflow When Overly Broad Skip Is Discovered

Suppose operations discovers a job reported `COMPLETED` yet output is missing data. Do not immediately re-run with random `JobParameters`. Follow a sequence:

1. **Halt publishing/consumption of suspect output** if possible, or flag the period as failing quality checks.
2. **Scope the incident:** jobName, business key, source version, JobInstance/JobExecution, timestamp, and affected targets.
3. **Inspect `StepExecution` counters:** read/process/write skips, filters, read/write/rollback counts; analyze exception types safely.
4. **Reconcile source against target:** counts, unique IDs, amounts, or checksums; identify missing/extra/erroneous records.
5. **Identify the true root cause:** schema shift, scattered bad input, processor bug, writer lost privileges, or non-transactional side effects.
6. **Fix the policy:** narrow exception classes, tighten skip limits, add preflight and quality gates. Do not merely lower `skipLimit` if errors remain misclassified.
7. **Choose a recovery path:** fix data and restart the right `JobInstance` if appropriate, or reprocess a new source revision with explicit output versioning.
8. **Protect idempotency:** unique business keys, checkpoints, and reconciliation before replay; do not duplicate committed chunks.
9. **Audit rejects and fixes:** who approved dropping records, reason, post-correction status, and final reconciliation result.
10. **Add regression tests** for dangerous exception classes and abnormal reject rates before redeploying.

During recovery, **never delete `BATCH_*` just to re-run**: metadata holds execution history and checkpoints required for restart. Never assume all output rolled back when a step previously failed; many chunks may have committed.

### What If Some Records Were Dropped Permanently?

An unwritten record may require:

- Fixing the source and reprocessing a new **batch revision**.
- Backfilling via a compensating job with an independent business key.
- Quarantining for authorized human review.
- Retaining final rejected status if the business truly permits it.

The choice depends on business requirements and writer idempotency. Simply "replaying the whole file" may not be safe when the database or API already absorbed partial side effects.

## 18. Common Mistakes When Configuring Skip

**"`.skip(Exception.class)` makes the job more resilient."** It can make bugs, infrastructure failures, or broken contracts look like bad data. Resilience means recovering properly from transient faults, not forging ahead by dropping output.

**"A huge `skipLimit` lets the whole file finish."** Perhaps, yet that does not prove complete data. On small files, a high reject percentage can still pass under an absolute limit.

**"Processor returning `null` or throwing an exception are the same."** No. `null` is a filter; a policy-skipped exception is a reject; counters and business meanings differ.

**"If the job `COMPLETED`, there is no need to check skip counts."** False. A step can finish successfully with allowed skips; output quality must pass a quality gate.

**"I logged the exception, so I can find the item later."** Exceptions can leak sensitive raw data, and logs do not guarantee sufficient retention/auditability. Use error codes, record references, and proper quarantine.

**"`DataIntegrityViolationException` means a bad item that can be skipped."** Not always: it can indicate a schema error, missing reference data, or mandatory data constraint. Classify before skipping.

**"If the writer fails, just skip the last record."** When a writer receives a whole chunk, the failing item may not yet be isolated. Rollbacks and replays must be safe; with non-transactional APIs, outcomes may be uncertain.

**"Transient database errors should be skipped so the batch stays fast."** Temporary connectivity glitches may call for retry/backoff. Dropping items because of weak infrastructure is not a data-quality strategy.

**"The number of rows in the reject table equals the number of skipped items."** Listeners and retries/rollbacks can duplicate entries if auditing is not idempotent. Reconcile outcomes by business key and execution.

**"If each partition has `skipLimit=10`, the job also has at most 10 errors."** Never assume that; partition/step limits do not automatically enforce a job-wide budget.

**"Fewer outputs than inputs is a bug."** Not always when valid filters, rejects, or aggregations exist. What matters is explaining and reconciling at the right grain.

**"Outputs equal in count to inputs means correctness."** Not always: one ID may be missing and another duplicated, or amounts wrong while row counts match. Check key sets and business values.

## 19. Guide to Designing a Safe Skip Policy

When building a new job or fixing one with overly broad skips:

1. **Write an input/output contract.** Define mandatory records, optional records, filters, rejects, and source data rules.
2. **Preflight the source.** Check headers, schema version, encoding, manifest, and whole-file failure conditions. Never use row skips to mask a structurally broken file.
3. **Classify exceptions.** Use dedicated business exceptions for skippable errors; fail-fast on code, security, configuration, and critical data errors.
4. **Separate retry from skip.** Retry transient errors with bounded attempts and safe replay; skip only approved isolated record errors.
5. **Set explicit budgets.** Have an absolute `skipLimit`, percentage quality gates, and per-error-group / critical-group rules.
6. **Record traceable rejects.** Standardized error codes, business/source references, access-controlled and idempotent quarantine; never log full items.
7. **Reconcile after writing.** Use the source snapshot, counts, keys, sums, and committed output; never rely on `BatchStatus` alone.
8. **Publish only on quality pass.** Distinguish `loadStep COMPLETED` from `batch data approved`.
9. **Preserve restartability.** Never delete/alter metadata recklessly; keep identifying parameters and design idempotent writers.
10. **Test non-skippable errors.** Intentionally trigger NPEs, schema errors, DB permission errors, writer timeouts, and policy-breaching reject rates.

A sound policy is often documented as a decision table:

| Condition | Action | Evidence stored |
|---|---|---|
| Record has bad optional field, reject allowed | Bounded skip | Error code + source reference + quarantine |
| Critical record invalid | Fail | Job/step IDs + standardized business error |
| Bad file header/schema | Fail preflight | Source version + schema mismatch code |
| DB transient | Bounded retry | Retry count + infrastructure status |
| DB lost privileges/schema | Fail | Error category + component, no credential logs |
| HTTP timeout with unknown outcome | Reconcile before retry | Idempotency key + remote status |
| Reject rate exceeds threshold | Block publish | Reconciliation report |
| All conditions met | Publish | Batch key + quality result + output totals |

## Conclusion

In Spring Batch, **overly broad skip can turn data or system failures into "false successes"**. Configuring `.skip(Exception.class)` or raising `skipLimit` indefinitely can let a job run to the end without guaranteeing complete, accurate output. `COMPLETED` only holds within the scope of the programmed policy—it is not a certificate of data quality.

To prevent silent data loss, **skip narrowly by exception and business rule**, distinguish filters/retries/failures, set both absolute and percentage thresholds, maintain safe reject audits/quarantine, reconcile the source snapshot against committed output by business key, and publish results only when the quality gate passes. Only then can a bad record be intentionally excluded without **masking incidents that ought to halt the job**.

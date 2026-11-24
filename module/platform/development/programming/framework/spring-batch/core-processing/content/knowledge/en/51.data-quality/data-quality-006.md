# Duplicate Detection in Spring Batch: Detecting Duplicates and Handling Them Consistently

## 1. What Is Duplicate Detection?

In **Spring Batch Core Processing**, *duplicate detection* is identifying two or more input records representing **the same entity, the same event, or the same business operation** according to defined rules.

An order import job can encounter duplicates because:

- A partner file contains the same order twice.
- The same file is resent or rerun after a network drop.
- A paginated API returns one record across two pages.
- A message broker redelivers an unacknowledged event.
- A job rolls back and retries or restarts, seeing previously processed records again.
- Two workers or two concurrent jobs fetch data for an overlapping time window.

Without detecting and handling duplicates, a batch job can create two orders, post two accounting entries, or send notifications twice. However, **not every pair of records sharing a field value is a duplicate**. For example, a customer placing two orders of the same amount is normal; two status updates for the same order may also be two valid events.

The first goal is defining **what counts as a duplicate**, then choosing the right inspection point and handling policy.

Example:

```text
File orders-20250512.csv

source,order_id,amount
PARTNER_A, O-101 ,120000
PARTNER_A,O-102,50000
PARTNER_A,o-101,120000
PARTNER_B,O-101,30000
```

If the duplicate key rule is `(source, normalized_order_id, business_date)`, the first and third rows are duplicates; the fourth row is not a duplicate because it belongs to `PARTNER_B`. If order IDs are globally unique system-wide, the conclusion differs. Rules must derive from the business model, never from two strings merely looking alike.

### Expected Outcomes

After ingesting data, the system needs to distinguish:

| Outcome | Meaning |
|---|---|
| `ACCEPTED` | New record, permitted to proceed |
| `EXACT_DUPLICATE` | Same key and same content per agreed criteria |
| `CONFLICTING_DUPLICATE` | Same key but differing business content |
| `INVALID_KEY` | Cannot form a valid key (blank, malformed, missing required field) |
| `REPLAYED_EVENT` | Event already processed in an earlier run |
| `POSSIBLE_DUPLICATE` | Similar only under fuzzy rules, requiring further review |

Do not lump everything into a single "duplicate" label and discard it. **Exact duplicates**, **data key conflicts**, and **a valid new event for the same entity** may require three distinct behaviors.

## 2. Distinguishing Duplicate Scopes

| Scope | Example | Suitable Technique |
|---|---|---|
| **Within one chunk** | Two items with the same ID in a 200-item write batch | In-batch key check; unique constraint remains the final safeguard |
| **Across chunks in the same execution** | Item in chunk 1 duplicates item in chunk 5 | Staging table / unique index or durable state |
| **Across runs / restarts** | Job rereads events already committed in an earlier run | Business idempotency key, DB unique/upsert |
| **Across files / sources** | Same order sent in two different files | Key including source namespace or global business identifier per contract |
| **Across workers / partitions** | Two workers process the same ID | Unique constraint / atomic operation on shared storage |
| **Fuzzy duplicates** | Similar name, address, email | Probabilistic matching rules, review/quarantine |

An in-memory `HashSet` in one JVM only sees the state of that single JVM instance. It does not properly handle two independent workers, committed data from an earlier run, or crash recovery.

## 3. Designing the Business Key Before Writing Code

A **business key** is the combination of attributes that identifies a record or operation under business rules.

Examples:

- Orders: `(sourceSystem, externalOrderId)`.
- Payment transactions: `(provider, providerTransactionId)`.
- Update events: `(sourceSystem, sourceEventId)`.
- Daily summary records: `(businessDate, accountId, metricType)`.
- Versioned snapshots: `(entityId, effectiveDate, version)`.

If an order amendment arrives as a **new event** with the same `externalOrderId` yet a different `eventId` or `version`, deduplicating on `externalOrderId` alone drops valid updates.

### 3.1. Three Questions to Lock Down the Key

1. **Does the key include the source?** Is `O-101` from two partners the same order?
2. **Does the key include date or version?** Is the same ID on two business dates a new record or replayed data?
3. **How long does the key live?** Forever, over a seven-day window, or only within a single import batch?

No single key fits every table. Document the rules in the data contract and processing code so they can be audited or reprocessed.

### 3.2. Normalizing Keys Before Comparing

Data often differs in whitespace, letter casing, and formatting. For example:

```text
" O-101 "
"o-101"
"O-101"
```

If the partner defines order IDs as **case-insensitive**, all three represent the same key. Normalize using `strip()` and `toUpperCase(Locale.ROOT)`.

```java
import java.util.Locale;

public final class BusinessKeyNormalizer {

    private BusinessKeyNormalizer() {
    }

    public static String normalizeRequired(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Business key is missing");
        }

        String canonical = raw.strip().toUpperCase(Locale.ROOT);

        if (canonical.isBlank()) {
            throw new IllegalArgumentException("Business key is blank");
        }

        return canonical;
    }
}
```

`Locale.ROOT` keeps case conversion independent of the host's default locale. Still, normalization **must follow the data source's contract**: a case-sensitive ID may treat `abc` and `ABC` as distinct values. Do not automatically strip Vietnamese diacritics, strip punctuation, or convert `00123` to `123` if those differences carry business meaning.

For Unicode, some systems normalize character forms via `java.text.Normalizer` (NFC/NFKC) for stable comparison; verify clearly that normalization does not erroneously merge valid distinct identifiers.

### 3.3. Avoiding Nullable Keys

If an order ID is missing, do not assign a placeholder key like `UNKNOWN` to all records. Doing so merges unrelated records into false "duplicates."

Validate and route such items to the invalid-data bucket (`INVALID_KEY`), or fail the step per policy. With databases, note that some RDBMS engines allow multiple `NULL`s in a unique constraint; declare dedup key columns `NOT NULL` when required by the contract.

## 4. Choosing a Duplicate Handling Policy

After identifying duplicate keys, decide which item is kept.

| Policy | Description | When to Use |
|---|---|---|
| **First wins** | Keep first occurrence, drop later ones | File has reliable priority ordering |
| **Last wins** | Keep last occurrence under a deterministic order | Newer snapshot supersedes older snapshot |
| **Latest event time wins** | Pick by event timestamp plus tie-breaker | Source emits multiple versions with business timestamps |
| **Highest version wins** | Pick highest version | Data carries a monotonic version |
| **Reject all conflicts** | Do not ingest when same key has different content | Strict financial or audit data |
| **Merge** | Combine selected fields from multiple records | Consolidating customer profiles with explicit rules |
| **Manual review** | Route to quarantine | Cannot safely choose via automated rules |

**First wins by read order** is only well-defined when data order is guaranteed. If a reader paginates without `ORDER BY`, files are ingested in parallel, or partitions run concurrently, "the first record" can change across runs.

Define an explicit **tie-breaker**. For example, pick the latest by `eventTime DESC, eventSequence DESC, immutableEventId DESC`, assuming those attributes are stable and trustworthy. If two records share the same `eventTime` with different values, picking one arbitrarily makes tracing difficult.

### 4.1. Exact Duplicates vs. Conflicting Duplicates

Example of two records with the same key:

```json
{"source":"PARTNER_A","orderId":"O-101","amount":120000}
{"source":"PARTNER_A","orderId":"O-101","amount":120000}
```

This can be treated as a replay that does not change data.

By contrast:

```json
{"source":"PARTNER_A","orderId":"O-101","amount":120000}
{"source":"PARTNER_A","orderId":"O-101","amount":900000}
```

This is a **data conflict**. `ON CONFLICT DO NOTHING` silently drops the second record, which can hide a valid amendment or a critical error. If the requirement is "each order has only one amount," inspect payload, version, and conflict policy, then halt or quarantine accordingly.

## 5. Where Does Duplicate Detection Live in Spring Batch?

A chunk-oriented step typically follows this chain:

```text
ItemReader
    |
    v
ItemProcessor
    |
    v
ItemWriter
    |
    v
Transaction commit / ExecutionContext checkpoint
```

Duplicate checks can live in three places, with different consequences.

### 5.1. In the Reader or Source Query

The reader can read an already deduplicated dataset via SQL or a staging step—for example, a query selecting one row per key under deterministic rules.

Pros: fewer items reach the processor/writer. Cons: may lose full history of dropped records unless raw data is preserved, and complex queries can increase database load.

### 5.2. In the Processor

The processor can normalize keys, detect certain duplicates, and return `null` to **filter** the item.

```java
@Override
public CleanOrder process(RawOrder item) {
    if (isDuplicate(item)) {
        return null; // Filter; not an exception skip.
    }
    return normalize(item);
}
```

This is conceptual only: `isDuplicate(...)` must be designed for consistency, transactions, and concurrency. If the processor uses a mutable in-JVM `HashSet`, rollbacks/retries/restarts can cause bugs, as explained next.

In Spring Batch:

- Processor returns `null` ⇒ increments `filterCount`.
- Reader throws a skippable exception ⇒ increments `readSkipCount`.
- Processor throws a skippable exception ⇒ increments `processSkipCount`.
- Writer throws a skippable exception ⇒ increments `writeSkipCount`.

**Duplicates excluded by business rule are usually filters or explicit database outcomes, not exceptions thrown to inflate skip counts.**

### 5.3. In the Writer / Database

A database `UNIQUE` constraint protects uniqueness even under **multiple competing workers or processes**. With SQL supporting atomic operations such as PostgreSQL `ON CONFLICT`, the writer can insert if absent, ignore duplicates, or update according to an explicit policy.

This is typically the final guarantee when duplicates can reappear after rollbacks/restarts or across multiple sources.

## 6. Why a `HashSet` in ItemProcessor Can Be Unsafe

A simple example:

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.batch.item.ItemProcessor;

public class InMemoryDedupProcessor
        implements ItemProcessor<String, String> {

    private final Set<String> seen = new HashSet<>();

    @Override
    public String process(String item) {
        return seen.add(item) ? item : null;
    }
}
```

This works in a simple list traversal, yet is **unsafe for fault-tolerant production Spring Batch**.

### 6.1. Failure After Rollback

Suppose the processor sees `O-101` and adds it to `seen`. Later the writer fails and the transaction rolls back:

```text
Process O-101
    |
    +-- seen.add("O-101") -> true
    |
Writer fails
    |
Database transaction rolls back
    |
Retry chunk
    |
Process O-101 again
    |
    +-- seen.add("O-101") -> false
    |
Filter O-101 even though it was never committed
```

`HashSet` lives in Java memory and **does not roll back with the database transaction**. Reprocessing can drop valid records.

In addition, depending on configuration, Spring Batch may cache processor outputs during retries. Exact behavior depends on fault-tolerance settings and whether processor transactionality is enabled. Safe designs must never assume the processor runs strictly once per item.

### 6.2. Failure on Restart

If a job commits several chunks and then crashes, the `HashSet` in a fresh JVM starts empty. Records written in the prior run are no longer known to that set. Conversely, storing `seen` inside `ExecutionContext` makes the key set huge, expensive to serialize/checkpoint, and risks consistency issues between checkpoints and side effects.

### 6.3. Failure Under Parallel Execution

Standard `HashSet` is not thread-safe; separate worker JVMs each have their own set. Switching to `ConcurrentHashMap.newKeySet()` only handles concurrency within the **same JVM**; it does not make the set durable or transaction-rollback-aware.

**Appropriate usage:** `HashSet` can be useful for small, purely in-memory validation over a fixed computation unrelated to commits/restarts. To guarantee uniqueness when writing batch data, rely on business keys and storage with atomic operations.

## 7. Stable Architecture: Normalize in Processor, Deduplicate in Database

A common architecture:

```text
             CSV / API / Message
                       |
                       v
                   ItemReader
                       |
                       v
             Normalize / Validate
                 ItemProcessor
                       |
                       v
              JDBC Batch Writer
                       |
                       v
        PostgreSQL UNIQUE business key
               /             \
       insert succeeds      conflict
               |             |
               v             v
          stage_orders    DO NOTHING / audit / reject
               |
               v
          Commit chunk
```

Keys are normalized deterministically in the processor. The database is the final arbiter of uniqueness via indexes/constraints. When a chunk rolls back, uncommitted inserts roll back too, so retries can re-attempt safely.

### 7.1. Designing the Staging Table

Suppose the business defines an order as unique by `(businessDate, sourceName, normalizedOrderId)`:

```sql
CREATE TABLE stage_orders (
    business_date DATE NOT NULL,
    source_name VARCHAR(64) NOT NULL,
    order_id_norm VARCHAR(128) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    inserted_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_stage_order
        UNIQUE (business_date, source_name, order_id_norm)
);
```

This is example SQL **for PostgreSQL**. If the same order can span multiple dates yet must remain globally unique, do not include `business_date` in the unique key merely because the batch runs daily. Conversely, if data is a daily snapshot, including `business_date` can be right.

A `UNIQUE` constraint works regardless of JVM count, thread count, partition count, or arrival timing, as long as all flows write to the **same authoritative store**.

### 7.2. Java Records for Reader and Processor

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record RawOrder(
        String sourceName,
        String orderId,
        BigDecimal amount
) {
}

public record CleanOrder(
        LocalDate businessDate,
        String sourceName,
        String normalizedOrderId,
        BigDecimal amount
) {
}
```

`RawOrder` represents read input; `CleanOrder` holds the normalized key and business date.

### 7.3. Pure-Function Processor

```java
import java.time.LocalDate;

import org.springframework.batch.item.ItemProcessor;

public final class NormalizeOrderProcessor
        implements ItemProcessor<RawOrder, CleanOrder> {

    private final LocalDate businessDate;

    public NormalizeOrderProcessor(LocalDate businessDate) {
        this.businessDate = businessDate;
    }

    @Override
    public CleanOrder process(RawOrder raw) {
        String source = BusinessKeyNormalizer.normalizeRequired(
                raw.sourceName());

        String orderId = BusinessKeyNormalizer.normalizeRequired(
                raw.orderId());

        if (raw.amount() == null) {
            throw new IllegalArgumentException("Amount is missing");
        }

        return new CleanOrder(
                businessDate,
                source,
                orderId,
                raw.amount()
        );
    }
}
```

The processor holds no `seen` state, makes no network calls, and performs no database writes itself. The same input and `businessDate` yield the same output; thus reprocessing an item after rollback **creates no side effects inside the processor**.

If negative or out-of-range amounts are data errors, add appropriate validation per the business contract. Do not mix duplicate rules with other validation rules when designing exceptions/skips.

### 7.4. Reader Using a Fixed File and JobParameters

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<RawOrder> rawOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("rawOrderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .saveState(true)
            .linesToSkip(1)
            .delimited()
            .names("source", "order_id", "amount")
            .fieldSetMapper(fields -> new RawOrder(
                    fields.readString("source"),
                    fields.readString("order_id"),
                    fields.readBigDecimal("amount")))
            .build();
}
```

`@StepScope` binds the reader to the step execution while allowing `inputFile` injection from `JobParameters`. `saveState(true)` enables checkpoint/restart when the source stays intact; never modify the file between failure and restart expecting offsets to remain valid.

### 7.5. Processor Receiving a Fixed Business Date

```java
import java.time.LocalDate;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
ItemProcessor<RawOrder, CleanOrder> normalizedOrderProcessor(
        @Value("#{jobParameters['businessDate']}")
        String businessDateText) {

    return new NormalizeOrderProcessor(
            LocalDate.parse(businessDateText)
    );
}
```

The business date is fixed for the execution. Never derive keys from `LocalDate.now()` per processor call, because the date can flip if a batch runs past midnight or restarts on another day.

### 7.6. Writer Using `JdbcBatchItemWriter` and `ON CONFLICT`

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<CleanOrder> stagingOrderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<CleanOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO stage_orders (
                    business_date,
                    source_name,
                    order_id_norm,
                    amount
                )
                VALUES (
                    :businessDate,
                    :sourceName,
                    :normalizedOrderId,
                    :amount
                )
                ON CONFLICT (
                    business_date,
                    source_name,
                    order_id_norm
                ) DO NOTHING
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("businessDate", item.businessDate())
                            .addValue("sourceName", item.sourceName())
                            .addValue("normalizedOrderId",
                                    item.normalizedOrderId())
                            .addValue("amount", item.amount()))
            .assertUpdates(false)
            .build();
}
```

PostgreSQL's `ON CONFLICT DO NOTHING` makes the insert **atomic per the unique constraint**: the first row is stored, and subsequent inserts with the same key add nothing. Under concurrent workers, the database constraint arbitrates.

On the writer, `assertUpdates(false)` allows an insert statement to affect zero rows due to a duplicate. If `assertUpdates(true)` were enabled, the writer would treat a zero update count as an error, contradicting the "ignore duplicates" intent.

**Critical limitation:** this configuration implements **first committed row wins** at storage. It does not check whether two payloads sharing a key have different amounts. If conflicting duplicates can occur, design raw persistence, payload comparison, and an explicit conflict policy before picking a winner.

### 7.7. Configuring the Chunk and Transaction Step

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step dedupStageStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> rawOrderReader,
        ItemProcessor<RawOrder, CleanOrder> normalizedOrderProcessor,
        ItemWriter<CleanOrder> stagingOrderWriter) {

    return new StepBuilder("dedupStageStep", repository)
            .<RawOrder, CleanOrder>chunk(200, transactionManager)
            .reader(rawOrderReader)
            .processor(normalizedOrderProcessor)
            .writer(stagingOrderWriter)
            .build();
}
```

`chunk(200, ...)` is an example commit interval, not a duplicate limit. What matters is that the writer and transaction manager manage **the same database transaction** for the staging table. If custom code opens an outside connection and commits item by item, rollback/restart semantics change.

For multi-step jobs, build a `Job` with `JobBuilder` and place `dedupStageStep` in the flow. These examples use **Spring Batch 5.x** builder styles.

### 7.8. Actual Records Written

For the example file with three logical rows:

```text
PARTNER_A, O-101 ,120000
PARTNER_A,O-102,50000
PARTNER_A,o-101,120000
```

The processor returns **3 `CleanOrder`s**; the writer receives three items, yet the unique constraint leaves only **2 rows** in the staging table.

Therefore:

- `StepExecution.readCount` is `3`.
- `StepExecution.writeCount` is `3` (the writer received and processed three items per Batch accounting).
- `StepExecution.filterCount` is `0` (the processor never returned `null`).
- `StepExecution.skipCount` is `0` (no exception was skipped).
- **Actual inserted rows** is `2`.

Never use `writeCount` to conclude three records exist in the table. To report duplicates accurately, derive counts from outbox/audit/staging tables or policy-driven reconciliation.

## 8. When Duplicate Reporting Is Required: Persist Raw Staging First

`ON CONFLICT DO NOTHING` gives idempotent writes, yet if the requirement is to **count, classify, and explain every duplicate**, keeping only one winning row loses information.

You can split ingestion into stages:

```text
Step 1: persist each row verbatim into raw staging
        (with file ID, line number, payload, event time)
    |
    v
Step 2: normalize keys and classify duplicate groups
    |
    +-- unique records         --> accepted
    +-- exact duplicates       --> duplicate audit
    +-- conflicting duplicates --> quarantine/review
    |
    v
Step 3: apply accepted records to business tables
```

### 8.1. Table Storing All Input Records

PostgreSQL example:

```sql
CREATE TABLE raw_order_import (
    ingest_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    import_id VARCHAR(128) NOT NULL,
    business_date DATE NOT NULL,
    source_name VARCHAR(64) NOT NULL,
    order_id_norm VARCHAR(128) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL,
    source_line_no BIGINT NOT NULL,
    CONSTRAINT uq_raw_source_line
        UNIQUE (import_id, source_line_no)
);
```

The `(import_id, source_line_no)` key prevents re-inserting the **exact same line of the same file/import** on retry/restart. `import_id` must stay stable across restarts—such as a file checksum or intake ID—never randomly generated on each run.

Storing all raw rows enables exact duplicate counting and preserves evidence when two records share a business key but differ in amount.

### 8.2. Finding Duplicate Groups with SQL

```sql
SELECT
    business_date,
    source_name,
    order_id_norm,
    COUNT(*) AS occurrence_count,
    COUNT(DISTINCT amount) AS distinct_amount_count
FROM raw_order_import
WHERE import_id = :importId
GROUP BY
    business_date,
    source_name,
    order_id_norm
HAVING COUNT(*) > 1
ORDER BY occurrence_count DESC, source_name, order_id_norm;
```

If `distinct_amount_count=1`, records agree at least on `amount`; that **does not guarantee** exact duplication if payloads have other fields. To evaluate exactness, compare all meaningful business fields or a defined canonical hash.

If `distinct_amount_count>1`, the group has an amount conflict requiring its own handling policy.

### 8.3. Selecting the Winner Deterministically

For example, business rules require keeping the record with the latest `event_time`, breaking ties by higher `source_line_no`, and finally stable `ingest_id`:

```sql
WITH ranked AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                business_date, source_name, order_id_norm
            ORDER BY
                event_time DESC,
                source_line_no DESC,
                ingest_id DESC
        ) AS rn
    FROM raw_order_import r
    WHERE import_id = :importId
)
SELECT
    business_date,
    source_name,
    order_id_norm,
    amount,
    event_time
FROM ranked
WHERE rn = 1;
```

This illustrates **last by event-time wins**, not a universal default for all data. If source `event_time` is unreliable or file order can change, base precedence on reliable business metadata. `ROW_NUMBER()` guarantees deterministic selection only when `ORDER BY` has a stable tie-breaker.

In particular, never run a "pick latest" query on data that already dropped other candidates via `DO NOTHING`.

## 9. Distinguishing Duplicate Handling from Spring Batch Counters

Spring Batch provides read/write/filter/skip counters, yet **has no standard "duplicateCount" counter covering every business policy**.

| Behavior | `readCount` | `filterCount` | `skipCount` | DB Row Count |
|---|---|---|---|---|
| Processor receives item and returns object | Increments | Unchanged | Unchanged | Depends on writer |
| Processor returns `null` due to duplicate | Increments | Increments | Unchanged | Item not written |
| Processor throws skippable error | Increments on read | Not necessarily | Process skip increments | Skipped item not written |
| Writer uses `ON CONFLICT DO NOTHING` | Increments on read | Unchanged | Unchanged | May not increment |
| Writer throws unique constraint error and fails step | Increments by read items | Not necessarily | Unchanged if not skipped | Chunk may roll back |

Therefore, dashboards should expose **dedicated business metrics**:

```text
inputRecords      = 100000
normalizedValid   = 99900
duplicateExact    = 50
duplicateConflict = 20
invalidKey        = 30
acceptedUnique    = 99900 - 50 - 20 = 99830
```

These are illustrative numbers assuming each item belongs to one mutually exclusive bucket. If the system selects one winner from each conflict group, the accepted formula must reflect actual winners and dropped items.

**A useful duplicate rate** is:

```text
duplicateRate = duplicateOccurrences / totalEligibleInputRows
```

Define the **denominator** and "occurrence" clearly: does a group of five identical rows count as **four extra occurrences** or **one duplicate group**? Those are two different metrics and should be named accordingly.

## 10. Idempotency Across Retry, Rollback, and Restart

Deduplication and idempotency are related, yet not identical:

- **Duplicate detection** asks: "Does this record duplicate another under the rules?"
- **Idempotency** asks: "If the same operation runs again, does the final state change unexpectedly?"

In Spring Batch, idempotency is especially important because chunks can roll back, jobs can retry, or operators can restart.

### 10.1. Duplicates Within the Same Chunk

Suppose input contains two `O-101` rows with chunk size 100. If the writer inserts both, the unique constraint and `ON CONFLICT DO NOTHING` ensure only one row appears in the database. Behavior also depends on the chosen duplicate-payload policy.

### 10.2. Duplicates Across Chunks

`O-101` appears in chunk 1 and chunk 20. Because both target the same table with a unique constraint, the database handles the second occurrence per the conflict policy. There is no need to hold every key from the start of the job on the JVM heap.

### 10.3. Chunk Rollback

```text
Chunk 1: O-101, O-102 -> COMMIT
Chunk 2: O-103, O-104 -> writer error -> ROLLBACK
Retry chunk 2:
   O-103, O-104 -> retried -> COMMIT
```

When the writer participates in the Spring Batch-managed transaction, rolled-back inserts from chunk 2 are no longer committed. Retries can reinsert them cleanly. A processor holding a non-transactional `HashSet` can produce the wrong result.

### 10.4. Restarting a New Execution

After a failed `JobExecution`, restarting creates a new `JobExecution` for the same `JobInstance`. An `ItemStream`-capable reader restores its checkpoint, yet some items may still be re-read depending on commit timing and recovery. A unique constraint on the business key lets the writer absorb replays without duplicating data.

**Never use `jobExecutionId` as a business dedup key** if you want duplicate protection across restarts: execution IDs change. Use a stable source or business key matching what must be protected.

### 10.5. Side Effects Outside the Database

Suppose when writing an order, the writer also makes an HTTP call to send an SMS. Database transaction rollback **does not undo an already-sent SMS**. Even if a unique constraint prevents duplicate orders, a user may receive two SMS messages on retry.

A better design:

```text
Batch transaction:
  insert/update order
  insert outbox event with unique business key
  COMMIT
     |
     v
Outbox publisher
     |
     v
Idempotent consumer processes event
```

Outbox and consumer idempotency must be designed explicitly; **there is no exactly-once guarantee across two independent systems solely from a Spring Batch transaction**. For redelivered events, consumers check a durable key before applying business effects.

## 11. Parallel Execution, Partitioning, and Duplicate Race Conditions

When batch concurrency increases, two workers can encounter the same record simultaneously:

```text
Worker A                       Worker B
--------                       --------
check key O-101: absent        check key O-101: absent
       |                              |
       +---------- insert ------------+
                      |
              database UNIQUE
                      |
             only one insert wins
```

**"SELECT to check existence then INSERT"** is not atomic: both workers can observe "absent." Without a unique constraint, two rows get written.

**Solution:** Use a unique constraint and an appropriate atomic database write, such as PostgreSQL `INSERT ... ON CONFLICT`. On duplicate, apply `DO NOTHING`, `DO UPDATE`, or fail + quarantine per policy.

### 11.1. Does Key-Based Partitioning Help?

If partitions are split by a stable hash of the business key, identical keys usually route to the same worker. This reduces contention and improves locality. However, partitioning **does not replace a unique constraint** because:

- Input may contain duplicates within the same partition.
- A partition may retry/restart.
- Another job may run concurrently.
- Partition rules or mappings may change with worker counts.
- Historical data may already exist in the table before the job runs.

### 11.2. Time-Windowed Uniqueness

Some systems only deduplicate within 24 hours—for instance, event IDs may be reused after that window. Schema, TTL, and partitioning must reflect the retention window.

Be careful: purging old keys before a delayed redelivery arrives allows the same event to be processed twice. Choose TTLs based on real redelivery/retry intervals and business contracts, not merely desired cache size.

### 11.3. Caches / Bloom Filters

Redis `SETNX` or a Bloom filter can help detect seen records early, yet:

- Redis has TTLs and separate transactions from the primary database; failures between them leave divergent state.
- Bloom filters have **false positives**, so they can wrongly flag a new record as a duplicate.
- A cache is not a durable source of truth for audits or cross-restart deduplication.
- When using a cache to shed load, still verify against the authoritative store before permanently dropping critical records.

Especially for financial data, never rely on a probabilistic Bloom filter as the sole condition for dropping valid records.

## 12. Duplicate Detection by Business Entity vs. by Event

Two common models choose keys differently.

### 12.1. Snapshots or Master Data

For example, receiving daily customer profiles. The same `customerId` in a new file may be a valid update. If you key on `customerId` and discard every later occurrence, data never updates.

Design options:

- Entity key: `customerId`.
- Version key: `(customerId, sourceVersion)`.
- Pick the highest `sourceVersion` or update using optimistic locking.
- Reject older versions, optionally recording an audit trail.

### 12.2. Event Logs

For example, one order has three events:

```text
event-001: OrderCreated(orderId=O-101)
event-002: PaymentConfirmed(orderId=O-101)
event-003: OrderShipped(orderId=O-101)
```

All three share `orderId`, yet they are **not duplicates**. If the broker redelivers `event-002`, deduplicate by **`eventId`**, not `orderId`.

An inbox event table:

```sql
CREATE TABLE processed_inbox (
    source_system VARCHAR(80) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_system, event_id)
);
```

Within the same transaction as the business update, the application checks/inserts the inbox key and applies only new events. Ensure "marking processed" and the business effect share compatible transaction semantics; marking processed prematurely in another transaction can drop an unprocessed event on retry.

## 13. Fuzzy Duplicates and Data Matching

Not all data has exact IDs. In CRM or customer datasets, two records may be similar:

```text
"Nguyen Van A", "090 123 4567"
"Nguyễn Văn A", "0901234567"
```

This is a **record linkage / fuzzy matching** problem, harder than exact duplicate detection. Techniques can include:

- Normalizing phone numbers by country format.
- Normalizing addresses and Unicode characters.
- Weighted multi-field scoring.
- Edit distance, Jaro–Winkler, or token similarity.
- Blocking on a coarse key to bound candidate pairs.
- Splitting into auto-accept, auto-reject, and human-review buckets.

When using a similarity threshold, measure **false positives** (merging two distinct people) and **false negatives** (failing to merge actual duplicates). Never use fuzzy scores instead of a business event ID when a reliable identifier already exists.

For sensitive data, matching designs must protect access and comply with retention rules; never dump names, phone numbers, or addresses into metric tags.

## 14. Testing Duplicate Detection with Fixed Fixtures

### 14.1. Key Normalization Unit Test

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class BusinessKeyNormalizerTest {

    @Test
    void normalizesWhitespaceAndCase() {
        assertEquals(
                "O-101",
                BusinessKeyNormalizer.normalizeRequired(" o-101 ")
        );
    }

    @Test
    void rejectsMissingOrBlankKey() {
        assertThrows(
                IllegalArgumentException.class,
                () -> BusinessKeyNormalizer.normalizeRequired(null)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> BusinessKeyNormalizer.normalizeRequired("  ")
        );
    }
}
```

This is a pure Java unit test; no Spring context or database is needed.

### 14.2. Pure-Function Processor Unit Test

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;

class NormalizeOrderProcessorTest {

    @Test
    void sameLogicalKeyProducesSameCanonicalKey() throws Exception {
        NormalizeOrderProcessor processor =
                new NormalizeOrderProcessor(
                        LocalDate.of(2025, 5, 12));

        CleanOrder first = processor.process(new RawOrder(
                "PARTNER_A", " O-101 ", new BigDecimal("120000")));

        CleanOrder replay = processor.process(new RawOrder(
                "partner_a", "o-101", new BigDecimal("120000")));

        assertEquals(first.sourceName(), replay.sourceName());
        assertEquals(
                first.normalizedOrderId(),
                replay.normalizedOrderId());
        assertEquals(first.businessDate(), replay.businessDate());
    }
}
```

This test confirms canonical key stability. It **does not prove database deduplication**; verifying atomic uniqueness and transactions requires integration tests.

### 14.3. Integration Test with PostgreSQL

Because the writer example uses PostgreSQL `ON CONFLICT`, run critical tests against a **PostgreSQL test database** (e.g., Testcontainers) rather than assuming H2 has identical semantics.

A scenario:

```text
Input:
  PARTNER_A, O-101 ,120000
  PARTNER_A,O-102,50000
  PARTNER_A,o-101,120000

Step:
  readCount   = 3
  filterCount = 0
  writeCount  = 3
  skipCount   = 0

DB after commit:
  2 rows in stage_orders
  PARTNER_A / O-101 / 120000
  PARTNER_A / O-102 / 50000
```

Tests can use `spring-batch-test` and `JobLauncherTestUtils.launchJob(parameters)`. Example assertions once the test context, job, and PostgreSQL database are configured:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class DedupJobAssertions {

    @Autowired
    JobLauncherTestUtils batchTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void shouldPersistOnlyUniqueCanonicalOrders() throws Exception {
        // Fixture contains the three example rows and was created in test setup.
        String inputFile = "/tmp/dedup-orders-fixture.csv";

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2025-05-12")
                .addString("inputFile", inputFile)
                .toJobParameters();

        JobExecution result = batchTestUtils.launchJob(parameters);
        StepExecution step = result.getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, result.getStatus());
        assertEquals(3L, step.getReadCount());
        assertEquals(3L, step.getWriteCount());
        assertEquals(0L, step.getFilterCount());

        Integer inserted = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM stage_orders
                WHERE business_date = ?
                """,
                Integer.class,
                LocalDate.of(2025, 5, 12));

        assertEquals(2, inserted);
    }
}
```

The snippet above is an **assertion skeleton**, not a standalone runnable test class without Spring context, PostgreSQL datasource, schema, and fixture setup. In real tests, create the fixture with `@TempDir` and pass the actual path, enable `@SpringBatchTest`/`@SpringBootTest` for the job configuration, and isolate `JobRepository` so test runs do not collide on identifying `JobParameters`.

Add assertions verifying **exact amount/source/key values**, rather than count alone, so you do not miss cases where two duplicate-key records retain the wrong payload.

### 14.4. Testing Rollback and Restart

Induce a writer failure at the end of a chunk to trigger database rollback. Then allow the writer to succeed and rerun from the checkpoint. Expectations:

- No missing orders due to an unrolled-back in-memory processor key set.
- No duplicated rows in the database.
- No duplicate external side effects on replay.
- The new `JobExecution` uses the same identifying business parameters on restart.
- With immutable input, the final unique record count matches a clean end-to-end run from scratch.

Another test should run **two concurrent jobs** attempting to insert the same key to verify unique-constraint concurrency protection. Never test a `HashSet` with two threads and assume deduplication is safe.

### 14.5. Testing Conflicting Duplicates

Input:

```csv
source,order_id,amount
PARTNER_A,O-101,120000
PARTNER_A,O-101,900000
```

If the policy is **reject conflicting duplicate**, the test must verify neither record is silently accepted as normal data; audit/quarantine captures the source ID, protected payload, and conflict reason. If the policy is **highest version wins**, the fixture needs explicit version fields and ordering.

## 15. Monitoring: Counting Duplicates and Detecting Anomalies

Duplicate rate is a key data quality indicator because it can reveal:

- Upstream resending files.
- Overlapping scheduler triggers.
- API pagination issues or event broker redeliveries.
- Broken dedup keys after a schema change.
- Retry/restart loops causing unintended replays.
- Key normalization changes accidentally collapsing distinct IDs.

A dashboard might show:

| Metric | Example | Purpose |
|---|---:|---|
| `input_rows_total` | 100,000 | Total ingested rows |
| `unique_keys_total` | 99,820 | Distinct business keys |
| `duplicate_extra_rows_total` | 180 | Extra duplicate occurrences |
| `conflicting_keys_total` | 7 | Groups with conflicting payloads |
| `invalid_keys_total` | 15 | Records lacking a valid key |
| `duplicate_rate` | 0.18% | Track trend fluctuations |
| `dedup_stage_duration_seconds` | Per execution | Deduplication step performance |

These are illustrative numbers. A group of five identical rows creates **four extra rows** yet only **one duplicate group**.

**Never put individual `orderId`, `eventId`, `jobExecutionId`, or payload content into Prometheus labels.** Per-item labels cause high cardinality and can leak data. Keep labels low-cardinality such as `jobName`, `sourceSystem`, `duplicateType`, and store granular IDs in access-controlled logs/audits.

### 15.1. Alert Thresholds by Source

Do not apply one threshold to every data type. An at-least-once message feed may normally have a baseline replay rate, whereas daily bank settlement files may tolerate zero conflicting duplicates.

Example operational policy:

```text
duplicateExactRate > 2%       -> alert to inspect upstream
conflictingDuplicateCount > 0 -> block data publishing
invalidKeyCount > 0           -> route to quarantine
```

Thresholds are illustrative and must align with real SLAs/data quality requirements. Also monitor **sudden spikes relative to each source's baseline**, because a rate considered "normal" today could signal an upstream bug if yesterday had almost zero duplicates.

## 16. Performance and Scale of Duplicate Detection

Exact deduplication has several options, with no single winner for all datasets.

| Approach | Java Memory | Restartability | Concurrency | Key Pros / Cons |
|---|---|---|---|---|
| `HashSet` in processor | Grows with key count | Poor without durable state | JVM-local only | Fast for small data; breaks on rollback |
| Sort + compare adjacent rows | Small if input is pre-sorted | Depends on checkpoint and source order | Needs ordered partitions | Efficient for large, deterministically sorted sources |
| SQL `GROUP BY`/`ROW_NUMBER()` on raw staging | Mostly in DB | Good if staging is durable | Handled by DB | Easy to audit; can incur sort/index cost |
| DB `UNIQUE` + atomic insert | Small in JVM | Good with retry/restart | Good if DB is tuned | Storage-enforced uniqueness; needs conflict policy |
| External dedup cache | Depends on cache | Per retention/durability | Infra-dependent | Fast load shedding; must stay synced with DB |
| Bloom filter | Small | Depends on state persistence | Distributable | False positives; unsuitable as final check |

### 16.1. Indexes and Key Size

Unique indexes prevent duplicates yet carry write and storage overhead. At tens of millions of rows, evaluate:

- Column sizes of `sourceName`, `orderId`, and composite keys.
- Date partitioning if the business key genuinely includes date.
- Ratio of new inserts vs. conflicted inserts.
- Concurrent writers and lock contention.
- Batch/chunk size and transaction log/WAL pressure.
- Staging cleanup policy after retention expires.

If business keys are very long, you can consider a key digest for storage efficiency, but **hashes have collision probabilities**. Where strict ID distinction is mandatory, retain or compare original values during verification rather than relying solely on a truncated digest.

### 16.2. Checking Keys with SELECT Before INSERT

A common pattern:

```text
SELECT count(*) WHERE key = ?
if 0:
    INSERT ...
```

This adds an extra query per item and suffers from race conditions under concurrency. When the database supports unique constraints and atomic upserts, prefer those. Use `SELECT` when you need the prior payload to resolve conflicts, while keeping the final write safe against concurrent changes.

## 17. Data Quality Design Workflow for Duplicates

When building a new ingestion pipeline, follow this sequence:

1. **Define source identity and event/business semantics.** Is the same order ID a duplicate or an update version?
2. **Lock down the canonical key.** Specify whitespace, casing, Unicode, nullability, and namespace.
3. **Define scope.** Deduplicate within a file, within a business date, across files, or across all history?
4. **Define policy.** First/last/version/merge/reject; how are payload conflicts handled?
5. **Preserve lineage.** File ID, source line, source event ID, business date, and version sufficient to trace.
6. **Choose the final enforcement point.** Use a unique constraint or storage with atomic conditional writes.
7. **Design retry/restart.** Test chunk rollbacks, checkpoints, and external side effects.
8. **Define metrics.** Distinguish extra rows, duplicate groups, conflicts, and accepted unique records.
9. **Test concurrency.** Two workers and two executions writing the same key.
10. **Design recovery.** Support replaying imports, reclassifying conflicts, and exporting audits without losing raw data.

Document these decisions in a data contract. A seemingly minor change to a normalization function can collapse millions of previously distinct keys, so version rules if historical data can be impacted.

## 18. Anti-Patterns to Avoid

| Anti-Pattern | Risk | Better Approach |
|---|---|---|
| Treating equal amounts as identical transactions | Drops valid transactions | Use source transaction ID and proper scope |
| Mutable `HashSet` in processor for production dedup | Does not roll back, loses state on restart | Unique constraint / atomic store |
| Assuming `ConcurrentHashMap` is safe across JVMs | Other workers do not share memory | Shared transactional storage |
| Using `jobExecutionId` as cross-restart dedup key | Each restart gets a new ID | Stable business/event key |
| Using `ON CONFLICT DO NOTHING` for all conflicts | Hides valid updates and amount mismatches | Separate exact duplicates from conflicts |
| Picking "the last row" without stable ordering | Outcome varies by schedule/parallelism | Version/event time + tie-breaker |
| Using `skip(Exception.class)` to handle duplicates | Hides database and code bugs | Controlled filter or conflict SQL |
| Treating `writeCount` as newly inserted DB rows | Misreports counts when INSERTs conflict | Query actual rows or use dedicated audit |
| `SELECT` then `INSERT` without a unique index | Race condition across workers | Atomic insert/upsert + unique constraint |
| Discarding raw data before deduplication | Cannot explain conflicts | Raw staging/quarantine with lineage |
| Dropping data solely via Bloom filter | False positives lose valid records | Confirm against authoritative store |
| Cache keys with overly short TTL | Late redeliveries processed twice | Retention aligned with redelivery contract |
| Modifying files between restarts | Checkpoints point to wrong records | Immutable files/versions/checksums |
| Testing only single-threaded runs | Misses race conditions | Concurrent integration tests |
| Missing conflict metrics | Job "succeeds" with corrupt data | Report explicit data-quality outcomes |
| Logging full customer payloads | Data exposure and log bloat | Safe IDs/lineage, controlled quarantine |

## 19. Practice Exercise: Multi-Source Order Import

Design the `importPartnerOrders` job to ingest daily CSV files from two partners with these fields:

```csv
source,order_id,amount,event_id,event_time,source_version
PARTNER_A,O-101,120000,E-001,2025-05-12T00:00:00Z,1
PARTNER_A,o-101,120000,E-001,2025-05-12T00:00:00Z,1
PARTNER_A,O-101,130000,E-008,2025-05-13T00:00:00Z,2
PARTNER_B,O-101,30000,E-200,2025-05-12T00:00:00Z,1
```

Requirements:

1. Define the **event duplicate** key `(source, event_id)` and the **entity** key `(source, normalized_order_id)`. Explain why the same key must not be used for both.
2. Write an ID normalization function using `strip()` and `Locale.ROOT`, and test blank or missing inputs.
3. Create a raw staging table storing every input row with file ID and line number, preventing re-insertion of the same line on restart.
4. Create an event inbox table with a unique constraint on `(source, event_id)`.
5. Design a rule: same event ID with identical payload counts as a replay; same event ID with differing payload goes to quarantine.
6. Design an order update rule: higher version applies; equal version with differing payload is a conflict.
7. Use `JdbcBatchItemWriter` or a custom JDBC writer for atomic insert/upsert within the step transaction.
8. Create a chunk containing duplicate records and induce a rollback. Prove retry does not drop valid items.
9. Restart from a failed execution with the exact same `JobParameters`. Prove no duplicate inbox events or orders are created.
10. Run two concurrent workers inserting `E-001`. Verify the unique constraint prevents duplicates.
11. Write a PostgreSQL integration test with a fixed fixture; assert final data, conflict rows, duplicate counts, and `StepExecution` counters.
12. Design a dashboard showing input rows, unique events, replay count, conflict count, batch duration, and errors per partner.

**Review question:** A job has `readCount=1000`, `writeCount=1000`, `filterCount=0`, and zero skips. The writer uses PostgreSQL `INSERT ... ON CONFLICT DO NOTHING`. Can you conclude the table gained 1,000 new rows?

**Answer:** **No.** `writeCount` counts items Spring Batch passed to the writer under framework mechanics, whereas `DO NOTHING` may insert no new row for keys that already exist. To know how many rows were actually inserted, read reliable update results, use an audit/outbox table, or reconcile database state under the defined contract.

## 20. References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): `read/process/write` cycle, chunks, and transactions.
- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): `ItemProcessor` returning `null` to filter items.
- [Spring Batch Reference — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): using `JdbcBatchItemWriter` and JDBC readers.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): fault tolerance and retries.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): distinguishing skippable exceptions from filtered items.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `ExecutionContext`, checkpoints, and restarts.
- [Spring Framework JDBC — Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html#jdbc-batch): batched database operations.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT DO NOTHING` and `DO UPDATE` semantics.
- [PostgreSQL — Unique Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS): enforcing uniqueness in the database.
- [PostgreSQL — Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): `ROW_NUMBER()` and ranking for deterministic record selection.

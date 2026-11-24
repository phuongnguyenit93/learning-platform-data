# Duplicate Data in Spring Batch Testing

## 1. What is duplicate data and why test it?

In a batch job, **duplicates** are records processed multiple times even though business rules allow recording them only once. Duplicates can appear within a single input file, across two separate files, across two chunks, across two job runs, or when a job restarts after a failure.

For example, a system ingests payment transactions with an `eventId`. One file contains two lines carrying `eventId=PAY-001`. If `eventId` is a unique event identifier, inserting both rows could double-count the amount. Conversely, if each row represents a valid adjustment with its own transaction ID, dropping a row merely because `customerId` repeats would lose legitimate data.

Hence, **"duplicate" must be defined by business key and processing policy**, never solely by two rows looking similar.

In the context of **Spring Batch Core Processing → Test data**, duplicate data is an **essential test fixture category** that answers:

- Which key does the job use to detect duplicates: the full row, `eventId`, `orderId`, or a composite key?
- Are duplicates dropped, updated, merged, sent to quarantine, or treated as a job failure?
- Are two duplicate records sitting in different chunks handled consistently?
- Does re-running the same data, retrying a chunk, or restarting a job trigger the business effect a second time?
- When the key matches but payload differs, does the job detect the conflict instead of silently ignoring it?
- Are `readCount`, `filterCount`, `writeCount`, and actual database row counts interpreted accurately?

Spring Batch does not deduplicate automatically. `ItemReader` reads items as configured, `ItemProcessor` transforms/filters if coded to do so, and `ItemWriter` performs writes. Business requirements and implementation design dictate how a job responds to duplicate data.

## 2. Classifying duplicates for accurate test design

| Category | Example | What to verify |
| --- | --- | --- |
| Exact row duplicate (*exact duplicate*) | `PAY-001,C01,100.00` appears twice | Only one business effect is recorded if each event processes once |
| Matching key, differing content (*conflicting duplicate*) | `PAY-001,C01,100.00` and `PAY-001,C01,900.00` | Conflict detected; never silently drop bad data unless business allows |
| Duplicate after normalization | `pay-001` and ` PAY-001 ` | Trim/case-folding rules applied consistently |
| Cross-chunk duplicate | Row 1 and row 7 match, chunk size = 3 | Deduplication still holds across separate chunk transactions |
| Cross-file duplicate | Two sources both send `PAY-001` | Idempotency key spans beyond a single file |
| Cross-run duplicate | Today's job re-reads yesterday's file | Re-running causes no unintended extra side effects |
| Retry/restart duplicate | Committed or partially sent chunk replays after failure/restart | Database and external systems do not receive double effects |
| Parallel-processing duplicate | Two partitions/threads encounter `PAY-001` simultaneously | Deduplication stays correct under concurrency |

Not every repeated value is a duplicate. `customerId=C01` can appear across thousands of valid transactions. The chosen key is typically an **event ID**, **source transaction ID**, or a composite like `(sourceSystem, externalTransactionId)`. Without a trustworthy key, clarify the data contract before discarding rows.

### Difference between business duplicates and Spring Batch metadata

Two concepts are often confused:

1. **Business data duplicates:** two input items representing the same event that must be counted once.
2. **Duplicate `JobInstance`:** launching the same job name with identical **identifying `JobParameters`**. Spring Batch enforces its own rule preventing re-execution of a completed instance.

Changing `run.id` creates a new `JobInstance` so the job can run again, yet **does not automatically stop business tables from inserting duplicates**. Conversely, wiping `BATCH_*` tables does not delete written business rows. Both state layers must be tested independently.

## 3. Processing flow model and duplicate control points

```text
CSV/API/Queue
     |
     v
 ItemReader  ------> readCount: items read
     |
     v
 ItemProcessor
   |-- validate
   |-- normalize business key
   |-- return null to intentionally filter item
   |       \------> filterCount: number of filtered items
   v
 ItemWriter   ------> writeCount: items successfully passed to writer
     |
     v
 Database / API / File
   |-- unique constraint
   |-- INSERT ... ON CONFLICT / idempotent operation
   \-- final business data
```

A chunk is normally written inside one transaction. With a 7-row file and `chunk(3)`, groups may be `[1,2,3]`, `[4,5,6]`, `[7]`. A duplicate between row 1 and row 7 surfaces only in a later chunk. Any check inspecting only the current chunk fails to catch cross-chunk duplicates.

Critically: **`writeCount` does not necessarily equal the number of new rows inserted into the database**. If `ItemWriter` receives 5 items and executes `INSERT ... ON CONFLICT DO NOTHING` to ignore 2 duplicates, Spring Batch still counts 5 items passed to the writer while the table grows by only 3 rows. Assert both batch metadata **and actual output state**.

## 4. Designing duplicate datasets with explicit expectations

Suppose job `importPaymentEventsJob` reads a CSV file where each event has three fields:

| Field | Meaning |
| --- | --- |
| `event_id` | Unique event identifier provided by the source |
| `customer_id` | Associated customer; allowed to repeat across distinct events |
| `amount` | Event amount |

Example rules:

- Normalize `event_id` by stripping leading/trailing whitespace and uppercasing with `Locale.ROOT`.
- Same `event_id` and identical content: process once; subsequent occurrences are exact duplicates.
- Same `event_id` with different `customer_id` or `amount`: treat as a **data conflict**, raising an error or routing to exception handling per business contract.
- Same customer with different `event_id`: distinct events that must all be retained.

Baseline fixture at `src/test/resources/batch/payment-events-duplicate.csv`:

```csv
event_id,customer_id,amount
PAY-001,C01,100.00
PAY-002,C02,250.00
PAY-001,C01,100.00
PAY-003,C01,75.00
PAY-002,C02,250.00
```

With chunk size = 2, the first and second `PAY-001` rows land in different chunks. This dataset catches deduplication logic scoped only to a single chunk.

Expected business outcome after one load:

| Metric | Expectation | Explanation |
| --- | ---: | --- |
| Data rows read by reader | 5 | Excluding CSV header row |
| Unique `event_id` keys | 3 | `PAY-001`, `PAY-002`, `PAY-003` |
| Exact duplicates | 2 | One duplicate `PAY-001` and one duplicate `PAY-002` |
| New rows in output table | 3 | Under record-each-event-once policy |
| Total amount of unique events | 425.00 | 100 + 250 + 75 |

To test **key normalization** specifically, create a separate fixture containing `PAY-001`, `pay-001`, and ` PAY-001 `. Do not blindly normalize `customerId`, dates, or amounts with the same rule: each field has its own contract.

### Conflict dataset

```csv
event_id,customer_id,amount
PAY-010,C01,100.00
PAY-010,C01,900.00
```

Here, both rows cannot simultaneously be treated as one valid transaction. If the system blindly uses `ON CONFLICT DO NOTHING`, the second row vanishes without anyone noticing the `amount` mismatch. Tests must state the **expectation** clearly: controlled failure, dead-letter/quarantine routing, or conflict reporting for operator reconciliation.

### Recommended test data matrix

| ID | Input | Test question |
| --- | --- | --- |
| D01 | All distinct IDs | Valid data is not mistakenly filtered |
| D02 | Two identical adjacent rows | Are intra-chunk duplicates written twice? |
| D03 | Two identical non-adjacent rows | Are cross-chunk duplicates written twice? |
| D04 | Differing only by case/whitespace | Is normalization policy consistent? |
| D05 | Same event ID, different amount | Are conflicts detected rather than ignored? |
| D06 | Same customer ID, different event ID | Are all valid events preserved? |
| D07 | Re-run same file with new job parameters | Does output grow erroneously again? |
| D08 | Fail mid-file then restart | Are pre-checkpoint effects duplicated? |
| D09 | Two threads process same event ID | Any check-then-insert race condition? |
| D10 | Null/blank/invalid event ID | Do validation and skip/fail match contract? |

Designing data whose **results can be proved numerically** (row counts, total amounts, ID lists, quarantine tables) makes tests far stronger than asserting `BatchStatus.COMPLETED` alone.

## 5. Three common duplicate-handling strategies

### 5.1. Filtering inside ItemProcessor

An `ItemProcessor` can return `null` to **filter** an item; this is not a `skip` error. Example suitable only for a single sequential step processing data once:

```java
@Bean
@StepScope
ItemProcessor<PaymentEvent, PaymentEvent> filterDuplicatesWithinStep() {
    Set<String> seen = new HashSet<>();

    return item -> {
        String key = item.eventId().strip().toUpperCase(Locale.ROOT);
        return seen.add(key) ? item : null;
    };
}
```

For the 5-row fixture, this processor returns `null` for 2 duplicates. If the writer receives the rest, metadata typically shows `readCount=5`, `filterCount=2`, and `writeCount=3`.

Limitations of this approach:

- The `HashSet` lives only for the step execution and remembers nothing from earlier runs.
- `seen` state **does not roll back** when a chunk rolls back. Under retry, restart, or checkpoints, results can break unless state/transactions are carefully designed.
- `HashSet` is unsafe across multiple threads or partitions; synchronizing the collection still fails to guarantee consistency across processes.
- With millions of IDs, holding all keys in RAM creates memory pressure.
- If you normalize the key for lookup yet return the raw `item`, output and matching rules diverge; normalize data before saving.

Therefore, `Set`-based processor filtering suits **unit tests, small datasets, sequential processing, or temporary pre-filtering** where cross-execution idempotency is not required.

### 5.2. Unique constraints and idempotent writes

For critical business data requiring deduplication across chunks, job runs, or workers, the standard approach enforces a **unique constraint** in the database on the true event key.

PostgreSQL example:

```sql
CREATE TABLE processed_payment_event (
    event_id     VARCHAR(80) PRIMARY KEY,
    customer_id  VARCHAR(80) NOT NULL,
    amount       NUMERIC(18, 2) NOT NULL
);
```

If IDs are unique only within one source, use a composite unique key like `(source_system, event_id)` rather than assuming global uniqueness for `event_id`.

To allow reprocessing an event **without inserting duplicates**, the writer can use PostgreSQL-specific syntax:

```sql
INSERT INTO processed_payment_event(event_id, customer_id, amount)
VALUES (:eventId, :customerId, :amount)
ON CONFLICT (event_id) DO NOTHING;
```

When two transactions concurrently attempt to insert the same `event_id`, the unique constraint serves as the final safeguard. Avoid splitting `SELECT COUNT(*)` followed by `INSERT` into two operations: another transaction can insert that ID in between.

**Note on business conflicts:** `DO NOTHING` only makes inserts idempotent by key. It **does not detect** when a later record shares the key but carries a different `amount`. If the contract requires detecting such conflicts, add payload/hash comparison, locking or proper transactions, and a conflict table. Never overwrite values simply because a record arrived later unless business rules permit it.

In H2, MySQL, or Oracle, equivalent syntax differs (for instance `MERGE` or database-specific upserts). Integration tests should run on the exact database engine used in production, especially when verifying concurrency and transaction semantics.

### 5.3. Staging and dedicated duplicate handling

When **every raw row** must be retained for reconciliation and root-cause analysis, a staging model fits well:

```text
Raw CSV/API
    |
    v
staging_event  (stores source file, row number, raw payload)
    |
    +-- new key + valid -------------> processed_event
    |
    +-- exact duplicate -------------> duplicate_audit
    |
    +-- same key, different payload -> conflict_quarantine
    |
    +-- malformed -------------------> validation_error
```

With this model, tests must verify all outputs: processed table, duplicate audit log, and conflict list. Retaining `sourceFile`, `lineNumber`, `eventId`, and rejection reason helps operators trace back to the source row.

## 6. Example batch configuration to test duplicates with PostgreSQL

The example below targets **Spring Batch 5.x / Spring Boot 3.x, Java 17+**. `PaymentEvent` is the input model:

```java
import java.math.BigDecimal;

public record PaymentEvent(
        String eventId,
        String customerId,
        BigDecimal amount
) {}
```

### Reader: reading 5 rows from CSV

```java
@Bean
@StepScope
FlatFileItemReader<PaymentEvent> paymentEventReader() {
    return new FlatFileItemReaderBuilder<PaymentEvent>()
            .name("paymentEventReader")
            .resource(new ClassPathResource(
                    "batch/payment-events-duplicate.csv"))
            .linesToSkip(1)
            .delimited()
            .names("event_id", "customer_id", "amount")
            .fieldSetMapper(fields -> new PaymentEvent(
                    fields.readString("event_id"),
                    fields.readString("customer_id"),
                    fields.readBigDecimal("amount")
            ))
            .build();
}
```

The CSV path corresponds to `src/test/resources/batch/payment-events-duplicate.csv`. Place the file under `src/test/resources` if this job is strictly for integration tests; in production, the resource can be passed via `jobParameters`.

### Processor: normalizing keys and validating

```java
@Bean
ItemProcessor<PaymentEvent, PaymentEvent> normalizePaymentEvent() {
    return row -> {
        String eventId = row.eventId() == null
                ? ""
                : row.eventId().strip().toUpperCase(Locale.ROOT);

        if (eventId.isBlank()) {
            throw new IllegalArgumentException("event_id is required");
        }

        return new PaymentEvent(
                eventId,
                row.customerId().strip(),
                row.amount()
        );
    };
}
```

In this example, the processor **does not filter duplicates**. It passes all 5 items forward, leaving unique-key enforcement to the database. If `customer_id`/`amount` are required, validate them per input contract too. Exception handling (`fail`, `skip`, or quarantine) must also be explicitly configured on the step if the job should continue past bad records.

### Writer: idempotent insert

```java
@Bean
ItemWriter<PaymentEvent> paymentEventWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> {
        for (PaymentEvent row : chunk) {
            jdbcTemplate.update("""
                    INSERT INTO processed_payment_event
                        (event_id, customer_id, amount)
                    VALUES (?, ?, ?)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    row.eventId(),
                    row.customerId(),
                    row.amount()
            );
        }
    };
}
```

`ItemWriter.write(Chunk<? extends PaymentEvent>)` receives a chunk. Within each chunk, the writer attempts to insert every item. New rows are inserted; rows with an existing `event_id` are ignored by PostgreSQL without creating duplicates. To preserve chunk transaction semantics, configure `JdbcTemplate` and `JobRepository` with matching transaction manager/DataSource; external outputs like HTTP or message brokers need dedicated idempotency design.

### Step and Job

```java
@Bean
Step importPaymentEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<PaymentEvent> paymentEventReader,
        ItemProcessor<PaymentEvent, PaymentEvent> normalizePaymentEvent,
        ItemWriter<PaymentEvent> paymentEventWriter) {

    return new StepBuilder("importPaymentEventsStep", jobRepository)
            .<PaymentEvent, PaymentEvent>chunk(2, transactionManager)
            .reader(paymentEventReader)
            .processor(normalizePaymentEvent)
            .writer(paymentEventWriter)
            .build();
}

@Bean
Job importPaymentEventsJob(
        JobRepository jobRepository,
        Step importPaymentEventsStep) {

    return new JobBuilder("importPaymentEventsJob", jobRepository)
            .start(importPaymentEventsStep)
            .build();
}
```

Place these beans in a `@Configuration` class inside the test's Spring context, ensuring valid `DataSource`, `JdbcTemplate`, `JobRepository`, and transaction manager beans are available. Key imports:

```java
import java.util.Locale;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
```

**Version note:** The example uses Spring Batch 5.x packages/models. Spring Batch 6 changes several packages and APIs; adjust imports and launcher utilities to match your project's version. `ON CONFLICT` is PostgreSQL syntax and must run against PostgreSQL when used verbatim.

## 7. Integration test: verifying results when a file has duplicates

The test uses `spring-batch-test`, JUnit Jupiter, and Spring Boot Test. Configure a **dedicated test PostgreSQL database** (for instance via Testcontainers) with `processed_payment_event` and Spring Batch metadata tables created. Disable job auto-run at context startup so the test controls execution:

```properties
spring.batch.job.enabled=false
```

In test environments, Boot can initialize metadata tables via `spring.batch.jdbc.initialize-schema=always`, or you can run existing migrations. Business tables need their own DDL. **Never point this test at a shared database** because it deletes fixture data.

Spring Batch 5.x test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class DuplicatePaymentEventIT {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("importPaymentEventsJob")
    private Job importPaymentEventsJob;

    @BeforeEach
    void resetFixture() {
        launcher.setJob(importPaymentEventsJob);
        repositoryTestUtils.removeJobExecutions();
        jdbcTemplate.update("DELETE FROM processed_payment_event");
    }

    @Test
    void ghiDungBaEventKhiFileCoHaiBanSao() throws Exception {
        var parameters = new JobParametersBuilder()
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = launcher.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        StepExecution step = execution.getStepExecutions()
                .iterator().next();

        assertEquals(5, step.getReadCount());
        assertEquals(5, step.getWriteCount());

        Integer rows = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM processed_payment_event",
                Integer.class
        );
        assertEquals(3, rows);

        BigDecimal total = jdbcTemplate.queryForObject(
                "SELECT SUM(amount) FROM processed_payment_event",
                BigDecimal.class
        );
        assertEquals(0, new BigDecimal("425.00").compareTo(total));
    }
}
```

### Meaning of the assertions

- `BatchStatus.COMPLETED`: the step finished with a success status, though this status alone **does not prove** deduplication worked.
- `readCount=5`: the reader consumed all five items from the fixture.
- `writeCount=5`: all five items were passed to the writer (since the processor did not filter). This is not the count of SQL rows inserted.
- `COUNT(*)=3`: the unique constraint plus idempotent insert kept three unique keys.
- `SUM(amount)=425.00`: duplicates did not double-count amounts.

If choosing a processor-filtering policy instead, metadata expectations shift—for example, `filterCount=2` and `writeCount=3` when no rollbacks/retries occur. Tests must assert against the **actual design**, rather than forcing one set of counters on every strategy.

### Testing re-running the same file

With three rows already in the test database from the first run, launch the job a second time with a **different set of identifying parameters**. Both runs read five rows, yet business data must still hold three events.

You can add the following method to the test class above:

```java
@Test
void chayLaiFileKhongLamTangSoEvent() throws Exception {
    JobExecution first = launcher.launchJob(
            new JobParametersBuilder()
                    .addString("run.id", "first-" + UUID.randomUUID())
                    .toJobParameters()
    );

    JobExecution second = launcher.launchJob(
            new JobParametersBuilder()
                    .addString("run.id", "second-" + UUID.randomUUID())
                    .toJobParameters()
    );

    assertEquals(BatchStatus.COMPLETED, first.getStatus());
    assertEquals(BatchStatus.COMPLETED, second.getStatus());

    Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM processed_payment_event",
            Integer.class
    );
    assertEquals(3, count);
}
```

In this test, `@BeforeEach` runs **once before the method**, so rows from the first launch remain for the second launch to verify idempotency. Truncating the business table between the two launches would defeat the test's purpose.

## 8. Testing duplicates under retry, rollback, and restart

Testing with duplicate data often uncovers bugs missed by happy-path tests:

### 8.1. Retry and rollback at chunk boundaries

A scenario:

1. Reader reads events `PAY-001`, `PAY-002` in a chunk.
2. Writer writes to the database, then a technical fault rolls back the chunk transaction.
3. Spring Batch retries processing per configuration.
4. Items are read/processed/written again; the final outcome must still be one record per event.

When output uses the same transactional database as the chunk along with idempotent inserts, rollback undoes inserts from the uncommitted transaction. However, if the writer also calls an HTTP API or publishes messages, those side effects **may already have happened despite JDBC rollback**. You need receiver-side idempotency keys or outbox/transactional messaging; inspecting `JobRepository` alone is insufficient.

### 8.2. Restart after some chunks committed

Another scenario:

1. The job commits the first chunk and persists progress in `ExecutionContext`.
2. The next chunk hits an error and the job stops with `FAILED`.
3. The test restarts the **same `JobInstance` using real restart mechanics**.
4. Already-processed events produce no duplicates; remaining events finish.

Test both questions: whether the reader resumes at the right offset, and whether the writer stays idempotent if an item is replayed. Simply swapping `run.id` and re-launching **creates a new instance** without testing restart/checkpoints. Deleting `BATCH_*` metadata before restarting also invalidates the measurement.

For stateful readers, configure a reader name and `saveState` properly so Spring Batch saves `ExecutionContext`. If a processor keeps an in-memory `HashSet`, `seen` state is lost across process restarts, making database uniqueness essential.

### 8.3. Multi-threaded or partitioned execution

Two threads can simultaneously see `PAY-001` as "not yet present". If code runs `SELECT` then `INSERT` without atomic enforcement, both can attempt to insert. Parallel tests should verify that:

- The database ends up with exactly one `PAY-001` event.
- No unexpected unique-constraint failure crashes the job (or errors follow the contract).
- Outbound API call counts, emitted messages, and total amounts are not doubled.

In concurrent tests, safeguards must reside at the **shared state boundary** (database/consumer idempotency store), rather than relying on an in-process `Set`.

## 9. Distinguishing filter, skip, failure, and duplicates

Spring Batch provides distinct technical mechanisms:

| Mechanism | When to use | What to observe in tests |
| --- | --- | --- |
| `ItemProcessor` returning `null` | Intentionally excluding an item from output | `filterCount` increments |
| `skip` a configured exception | Faulty item allowed to be bypassed within skip limit | `readSkipCount`, `processSkipCount`, `writeSkipCount` depending on fault phase |
| `retry` transient exception | Error recoverable upon re-attempt | Verify attempt counts, rollbacks, and final output |
| Unique constraint + `DO NOTHING` | Valid duplicate rows handled idempotently | Actual row count increases by 0; `writeCount` may still increment |
| Quarantine/conflict table | Same key with conflicting payload needing investigation | Error record holds full ID, payload, source, reason |
| Fail job | Duplicates treated as severe violations | `BatchStatus.FAILED` and data rolled back/retained per policy |

Never configure unconditional skipping on every `DuplicateKeyException`. Some "duplicate key" errors signal **real conflicts**, bad data constraints, race conditions, or mapping bugs. Skipping an exception in a writer can also trigger chunk rollback and single-item retries to isolate the offending item; tests must check actual runtime behavior and post-transaction database state.

## 10. Test data and computing expected outcomes

When creating fixtures, always pair three elements: **input**, **policy**, and **expected output**. Looking at a file that merely "has duplicate rows" is not enough to determine the right outcome.

Example with the five-row baseline fixture:

```text
Input             Business key    Expected action
----------------------------------------------------
PAY-001 C01 100   PAY-001         INSERT
PAY-002 C02 250   PAY-002         INSERT
PAY-001 C01 100   PAY-001         DUPLICATE -> IGNORE
PAY-003 C01  75   PAY-003         INSERT
PAY-002 C02 250   PAY-002         DUPLICATE -> IGNORE
----------------------------------------------------
Read: 5            Unique keys: 3       Newly inserted: 3
Business total amount: 425.00
```

When generating large-scale test data, construct reproducible record classes:

- `N` records with unique business keys.
- `D` exact copies injected at the beginning, middle, and end of the file.
- `C` records sharing keys with differing payloads to test conflicts.
- `V` key format variations (casing, whitespace, Unicode if allowed by contract).

The expected unique key count is `N` **provided** `D` only copies keys from `N` and `C` introduces no new keys. Counts of valid records, duplicates, and conflicts must still be computed separately per business policy. Use a fixed random seed when generating fixtures so failures reproduce; if testing load distribution, log the seed of every run.

### Isolating fixtures from stale state

A reliable test must know its starting state:

```text
Initial database: 0 events
Fixture: 5 rows, 3 unique event_ids
Result after run 1: 3 events
Result after run 2: still 3 events
```

If the initial database already contains `PAY-002`, run 1 adds only two rows; that makes sense for a "duplicate against existing data" test, yet **must not** happen accidentally when testing "duplicates within one file".

Sources of cross-test dependency include reused databases, uncleaned output files, unreset dedup caches, `@Singleton` beans holding `seen` sets, or reused `JobParameters`. Use isolated test databases/schemas and fixtures with clear ownership.

## 11. Common mistakes

### Counting only records read by the reader

Reading five rows accurately does not prove writes are right. The job may have inserted five business rows, doubling amounts. Assert `COUNT(DISTINCT business_key)`, `COUNT(*)`, aggregates, or actual API state.

### Using DISTINCT across the entire row

`SELECT DISTINCT *` only eliminates identical rows. Two rows sharing `eventId` with different timestamps, amounts, or descriptions both survive. If `eventId` is the key, deduplicate by that key and enforce a policy for conflicting payloads.

### Sharing a Set across all job runs

If a `Set` lives in a singleton processor, a second job run can over-filter because the set retains IDs from the first run. With `@StepScope`, each step execution gets a fresh set, which fails to deduplicate across runs or restarts. Understand bean lifecycles.

### Assuming chunk boundaries bound duplicates

Duplicates are not confined to a single chunk. Duplicates at the end of a file, in another file, or from parallel inputs must obey the same policy.

### Using "upsert" without defining conflicts

`ON CONFLICT DO NOTHING` suits immutable events, yet is dangerous when matching keys arrive with conflicting values that ought to raise an alert. `ON CONFLICT DO UPDATE` is not automatically right either: some systems must keep the first record, others keep the latest version, and others reject all updates.

### Clearing Batch metadata and assuming the test is clean

`JobRepository` manages execution metadata; business tables, output files, and external side effects must be cleaned separately. If testing restart, do not delete metadata before restarting at all.

### Assuming external APIs share the database transaction

An HTTP request can succeed at the receiver right before a network timeout, causing retry to resend it. For payments, emails, or message publishing, test idempotency at the system boundary. A chunk's JDBC transaction cannot roll back HTTP side effects.

## 12. Practice exercises: expanding from happy path to restart

For `importPaymentEventsJob`, implement these exercises in order:

1. **Baseline:** create a file with three distinct event IDs; assert the output table has three rows and the expected total amount.
2. **Intra-run duplicates:** use the five-row fixture above; assert still only three rows and total `425.00`.
3. **Cross-chunk:** keep `chunk(2)` and place the copy of `PAY-001` at the end of the file; verify no extra record is created.
4. **Normalization:** add `pay-001` and ` PAY-001 ` variants; verify they resolve to the same key after normalization if allowed by contract.
5. **Conflict:** add `PAY-001,C01,900.00` and implement a conflict-reporting policy; assert error details exist for reconciliation without silent data loss.
6. **Rerun:** launch the job again with new job parameters without resetting the output table; assert event count and total amount remain unchanged.
7. **Restart:** induce a controlled failure in a chunk after an earlier chunk commits; restart the same `JobInstance` and verify no duplicate writes occur.
8. **Concurrency:** run two workers or two job executions containing the same event; verify unique constraints and conflict policies still hold.

In each exercise, inspect both batch metadata (`BatchStatus`, `readCount`, `filterCount`, `writeCount`, skip counts) and actual data state. The exercise is complete when repeating the same fixture yields identical **business outcomes**, even if reader/writer invocation counts vary due to retries.

## 13. Conclusion

Duplicate data is a core test case for proving a batch job's **business-level once-only accuracy**. Spring Batch provides chunking, retry, restart, and metadata tracking, yet neither defines what makes an event a duplicate nor guarantees non-transactional side effects happen once. To test reliably, define the true business key, normalize inputs by rule, build fixtures covering intra-chunk, cross-chunk, and cross-run duplicates, and reconcile **final output** against expected results. For repeatable or parallel jobs, unique constraints and idempotent write designs provide vital protection alongside processor-level checks.

### References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — ItemProcessor](https://docs.spring.io/spring-batch/reference/processor.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [PostgreSQL — INSERT and ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)

# Bulk Bad Data in Spring Batch: Detection, Isolation, and Recovery

A nightly import batch job may encounter a few invalid records, yet occasionally **thousands of records fail together** because an upstream system changed formats, a file was truncated, data was exported under the wrong version, or an external dependency went down. Simply setting a huge `skip` limit so the job always reports `COMPLETED` can lose most of the dataset. Immediately halting the job on the first error blocks remaining valid records from processing and leaves operations unsure of the incident's scope.

This lesson belongs to **Spring Batch Core Processing → Failure recovery**, focusing on handling **bulk bad data**: classifying root causes, defining acceptance thresholds, configuring retry/skip/fail, isolating bad records in quarantine, blocking incomplete outputs from publishing, designing restarts/replays, and testing mass-error scenarios. Examples use **Java 17, Spring Boot 3.x, Spring Batch 5.x, JDBC, and JUnit 5**.

## 1. What Does "Bulk Bad Data" Mean?

Suppose `importOrdersJob` imports 100,000 orders from CSV. On a normal day, 12 lines have malformed amounts. The next day, the supplier renames a column and 78,000 lines fail to parse. Both produce exceptions, yet they **require different responses**.

| Situation | Symptom | Reasonable Handling |
| --- | --- | --- |
| A few business-invalid items | Scattered, low rate, clear cause | Bounded skip, store bad records, process remaining data |
| Failure across a whole data slice | Same `sourceFile`, tenant, partition, or business date | Isolate the failing slice; keep other slices if architecture permits |
| Source schema/format change | Bad header, many rows with wrong column count | Fail early before writing output; verify data contract |
| Corrupted or truncated file | Missing tail, bad checksum, abnormal line count | Reject source; request complete file/snapshot resend |
| Target database failure | Multiple writer calls hit timeouts/deadlocks | Bounded retry, investigate infrastructure; **never skip all items** |
| Auxiliary API outage | Processors hit 503/timeouts en masse | Backoff, cap retries/concurrency; fail/stop to rerun later |
| Missing source data in a partition | One partition has zero items | Check completeness/manifest; do not treat `COMPLETED` as sufficient |

One core rule: **deterministic data errors** (such as negative amounts or invalid date formats) rarely disappear when retrying the same item; **transient infrastructure errors** can recover after a few attempts. Never apply the same policy to both categories.

### 1.1. States to Distinguish

```text
Item is read
    |
    +--> valid ------------------------------> process / write
    |
    +--> bad data ---------------------------> SKIP + quarantine?
    |                                                |
    |                                                +--> budget left?
    |                                                       |       |
    |                                                      Yes      No
    |                                                       |       |
    |                                                   continue  FAILED
    |
    +--> transient error --> bounded RETRY --> succeeded? ----> write
                                                 |
                                                 No
                                                 |
                                          fail/skip per policy
```

**Retry** re-attempts a failed operation within one execution; **skip** bypasses an item per policy; **restart** creates a new `JobExecution` for the same `JobInstance` after a job failed or stopped; **replay/backfill** is an explicit process to reprocess source data or previously rejected records. Each serves a different scenario.

## 2. Define the Data Quality Contract Before Running

You cannot choose a sound `skipLimit` without knowing what constitutes a **complete and accurate** dataset. For every batch source, define:

1. **Source batch identity:** `sourceBatchId`, file/snapshot version, business date, and data slice.
2. **Expected record counts:** a manifest specifying row count, monetary total, checksum, or other control totals.
3. **Valid-item rules:** required fields, data types, unique keys, value ranges, and referential integrity.
4. **Allowed error thresholds:** absolute error count, error ratio, and non-skippable error categories.
5. **Publish conditions:** when output may be exposed to downstream consumers; whether partial results are ever acceptable.
6. **Correction and resubmission workflow:** who owns bad data, remediation SLA, how to rerun, and how recovery is verified.

Example business policy:

```text
Source: orders-import
Batch: sourceBatchId=orders-20261116-v1
Expected records: 100,000

Fail immediately:
  - missing/invalid header
  - invalid manifest or checksum
  - incompatible schema version

Allowed row rejects:
  - at most 100 invalid records
  - at most 0.5% of input
  - invalid monetary total must not exceed business tolerance

Publish:
  - only after reconciliation passes
  - accepted records and rejected records are accounted for
```

This is a **policy example**, not values provided automatically by Spring Batch. With 100,000 records, 0.5% equals 500 records, making the absolute limit of 100 stricter. If *both* must hold, 100 errors already trip the gate. On a 1,000-line file, 10 errors represent 1% even though below 100; the percentage policy rejects the batch.

Header, manifest, and version checks should normally run **before the data-writing step**. A file broken structurally across all rows must not be fed into a step attempting to skip tens of thousands of individual items.

## 3. Preparing Fixtures for Bulk Errors

Separating business data from failure scenario descriptions keeps tests reproducible. Example small CSV suite:

```text
src/test/resources/bulk-errors/
├── mostly-valid.csv
├── too-many-invalid.csv
├── invalid-header.csv
├── truncated-file.csv
└── manifest.json
```

`mostly-valid.csv`:

```csv
order_id,customer_id,amount
o-101,c-01,120.00
o-102,c-02,NOT_A_NUMBER
o-103,c-03,0.00
o-104,c-04,77.50
o-105,c-05,25.00
```

This set has **five source records**, three valid and two with invalid `amount`. A test with `skipLimit >= 2` permitting the validation exception to skip can finish the step with three items written and two skipped in the processor.

`too-many-invalid.csv` might contain hundreds of rows like:

```csv
order_id,customer_id,amount
o-201,c-01,BAD
o-202,c-02,BAD
o-203,c-03,BAD
o-204,c-04,BAD
o-205,c-05,BAD
```

The sample above is abbreviated for illustration. When building real fixtures, generate e.g. 1,000 records with 300 invalid rows and verify against limits of 100, 0.5%, or internal thresholds. Use synthetic IDs in tests rather than placing real customer data in repositories or logs.

`invalid-header.csv`:

```csv
id_customer,total_amount,currency_code
c-01,120.00,VND
```

This file has column names differing from the `order_id,customer_id,amount` contract. To **detect header changes**, perform an explicit header check before processing; simply calling `FlatFileItemReader.linesToSkip(1)` skips the first line blindly without validating column names.

Example manifest:

```json
{
  "sourceBatchId": "orders-20261116-v1",
  "schemaVersion": 3,
  "recordCount": 5,
  "businessDate": "2026-11-16",
  "checksumSha256": "example-only-replace-with-real-checksum"
}
```

The checksum field above is a placeholder, not a valid digest. In production, verify the checksum over the agreed source content, confirm the file finished writing (e.g., via `.done` file or atomic publish), and avoid reading files still being mutated by upstream.

## 4. Classifying Exceptions So System Errors Are Never Skipped

Spring Batch configures fault tolerance in chunk steps via `faultTolerant()`. You can categorize:

| Error Category | Example Exception | Recommended Policy |
| --- | --- | --- |
| Invalid business data | `InvalidOrderException` | Bounded skip + quarantine |
| Malformed CSV row | `FlatFileParseException` | Bounded skip if allowed, or fail fast when occurring en masse |
| Transient connection/API timeout | `TransientDataAccessException`, custom service exception | Bounded retry with backoff |
| Whole-file contract violation | `SourceSchemaMismatchException` | Fail before ingestion |
| Misconfiguration, missing target schema | Non-recoverable config/SQL exception | Fail; investigate before rerunning |
| DB unique constraint | `DuplicateKeyException` | Follow dedicated idempotency/duplicate rules; do not auto-skip all DB errors |

Avoid writing:

```java
.skip(Exception.class)
.skipLimit(1000000)
```

That hides system failures and programming bugs, letting the job proceed with incomplete output. Likewise, retrying every exception endlessly keeps reprocessing deterministically bad data that can never succeed.

### 4.1. What Does `skipLimit` Count?

With:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skip(FlatFileParseException.class)
.skipLimit(20)
```

Spring Batch permits **at most 20 skipped items in a StepExecution**, summed across read/process/write skips per policy. On the 21st skippable failure, the step typically transitions to `FAILED` for exceeding the limit. `skipLimit(20)` does not mean "20 errors per phase," nor "20 retries."

`readSkipCount`, `processSkipCount`, `writeSkipCount`, and `skipCount` on `StepExecution` track skipped failures. An attempt that fails and then succeeds on retry does not necessarily increment `skipCount`. Measure exact retry attempts using a dedicated listener/metric.

## 5. Building a Sample Job for Bounded Bad-Record Handling

Suppose the source is a three-column CSV and output goes to `accepted_orders`. We read all raw fields as strings first and convert/validate in the processor, separating **structural parse errors** from **business validation errors**.

### 5.1. Models and Business Exception

File `OrderModels.java` (types in the example package):

```java
package com.example.batch;

import java.math.BigDecimal;

record RawOrder(
        String orderId,
        String customerId,
        String amountText) {}

record ValidOrder(
        String orderId,
        String customerId,
        BigDecimal amount) {}

class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String reasonCode) {
        super(reasonCode);
    }
}
```

In real applications, `reasonCode` should come from an approved code set. Never pass entire CSV lines, emails, account numbers, or sensitive fields into exception messages since stack traces can be logged.

### 5.2. Reader Receiving Filename from `JobParameters`

Example step-scoped bean configuration:

```java
package com.example.batch;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
class OrderReaderConfig {

    @Bean
    @StepScope
    FlatFileItemReader<RawOrder> orderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<RawOrder>()
                .name("orderReader")
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .delimited()
                .names("order_id", "customer_id", "amount")
                .fieldSetMapper(fields -> new RawOrder(
                        fields.readString("order_id"),
                        fields.readString("customer_id"),
                        fields.readString("amount")))
                .build();
    }
}
```

`@StepScope` resolves `inputFile` at runtime. With default `DelimitedLineTokenizer`, rows with the wrong column count raise read errors such as `FlatFileParseException`; `amount=NOT_A_NUMBER` still reads cleanly as a `String` and is rejected by the processor.

**Operational note:** filenames from `JobParameters` must be validated against directory allowlists, source versions, and read permissions; never accept arbitrary paths from untrusted sources. This snippet only illustrates file reading. Add a preflight step verifying headers, checksums, manifests, and file completion before letting the job write data.

### 5.3. Processor Validating Data

```java
package com.example.batch;

import java.math.BigDecimal;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderProcessorConfig {

    @Bean
    ItemProcessor<RawOrder, ValidOrder> orderProcessor() {
        return row -> {
            if (row.orderId() == null || row.orderId().isBlank()) {
                throw new InvalidOrderException("ORDER_ID_REQUIRED");
            }
            if (row.customerId() == null
                    || row.customerId().isBlank()) {
                throw new InvalidOrderException("CUSTOMER_ID_REQUIRED");
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

            return new ValidOrder(
                    row.orderId(), row.customerId(), amount);
        };
    }
}
```

With `mostly-valid.csv`, `o-102` throws `INVALID_AMOUNT` and `o-103` throws `NON_POSITIVE_AMOUNT`; remaining items convert to `ValidOrder`. If too many errors appear in one batch, step policy should halt or block publishing rather than silently dropping the dataset.

### 5.4. Writer and Fault-Tolerant Step

Example writer using Spring JDBC sharing the datasource/transaction manager to write to the database:

```java
package com.example.batch;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.batch.item.file.FlatFileParseException;

@Configuration
class ImportOrdersJobConfig {

    @Bean
    JdbcBatchItemWriter<ValidOrder> orderWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<ValidOrder>()
                .dataSource(dataSource)
                .sql("""
                     INSERT INTO accepted_orders
                         (order_id, customer_id, amount)
                     VALUES (:orderId, :customerId, :amount)
                     """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("orderId", item.orderId())
                                .addValue("customerId", item.customerId())
                                .addValue("amount", item.amount()))
                .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> orderReader,
            @Qualifier("orderProcessor")
            ItemProcessor<RawOrder, ValidOrder> processor,
            JdbcBatchItemWriter<ValidOrder> writer) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<RawOrder, ValidOrder>chunk(100, transactionManager)
                .reader(orderReader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(TransientDataAccessException.class)
                .retryLimit(3)
                .skip(InvalidOrderException.class)
                .skip(FlatFileParseException.class)
                .skipLimit(20)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository jobRepository,
            @Qualifier("importOrdersStep") Step step) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .start(step)
                .build();
    }
}
```

This assumes `accepted_orders` and `BATCH_*` tables exist in the database. In production, target tables need business key constraints and idempotency so restarts/replays do not duplicate rows. Prefer staging tables over published tables as shown in Section 8.

`retryLimit(3)` in Spring Batch sets **a maximum of three attempts including the initial call** per policy; transient DB errors can be retried. The two data exceptions are allowed to skip within a limit of 20. Never add `Exception.class` to `skip` or `retry` just to make a job "finish the file."

### 5.5. When to Fail Fast Instead of Skipping

For wrong headers, mismatched checksums, incompatible schema versions, or abnormal manifests, **do not feed the entire file into a step with a huge `skipLimit`**. Run a preflight step before importing:

```text
validateSourceStep
    |
    +-- schema/manifest invalid --> JOB FAILED, no import
    |
    +-- source valid -----------> importOrdersStep
                                       |
                                       v
                               reconcileAndPublishStep
```

`validateSourceStep` can be a tasklet verifying header, checksum, version, and expected record count. If preflight fails, throw an appropriate exception so the job halts before writing output. Multi-step jobs should design flow transitions around business rules, not step names alone.

## 6. Error Thresholds: Absolute Counts and Ratios

Spring Batch handles **absolute** limits directly via `skipLimit`. However, **error-rate** limits (e.g., over 0.5%) must be implemented explicitly because `skipLimit` does not know the expected total record count.

### 6.1. When Total Input Items Are Known Up Front

Suppose the manifest declares `recordCount=1000` and policy allows at most 0.5% errors:

```text
expectedRows = 1000
maxRejectedByRatio = floor(expectedRows * 0.005) = 5
maxRejectedAbsolute = 100
effectiveAllowed = min(5, 100) = 5
```

For an import step, you can set the computed skip limit for that batch—e.g., `skipLimit(5)`. When the limit varies by `JobParameters`/manifest, build a properly scoped policy rather than hardcoding 5 on a shared singleton step.

### 6.2. When Exact Totals Are Unknown at Start

Without a trusted manifest, check the ratio after the step completes or track rolling counters and alert by observation window. Be very careful with denominators:

- `readCount`: successfully read items, not necessarily raw source line counts in every reader.
- `readSkipCount`: read errors skipped.
- `processSkipCount`: items skipped in processor.
- `writeSkipCount`: items skipped in writer.
- `skipCount`: total step skips per framework logic.

For simple line-oriented files, `readCount + readSkipCount` approximates attempted records, yet headers, filtered items, multi-line records, retries, or custom readers can make it diverge from logical business records. For strict reconciliation, use **manifests or explicitly defined source counters**.

If a post-import ratio check fails, block publishing even though staging writes completed. Modifying `ExitStatus` in `StepExecutionListener.afterStep` does not roll back already-committed chunks; for official outputs, use staging with a conditional publish gate.

### 6.3. Why Multi-Tier Thresholds Matter

Practical policies often combine tiers:

| Condition | Example | Response |
| --- | --- | --- |
| Single bad item | 1 invalid record | Skip + quarantine |
| Rising rate still under cap | 0.3% errors across 10,000 items | Alert and heighten monitoring |
| Error ratio exceeded | 1.2% errors vs. 0.5% limit | Block publish; fail flow per policy |
| Absolute count exceeded | 101 rejects vs. 100 limit | Stop step processing |
| Whole-source structural error | Missing header/schema mismatch | Fail immediately in preflight |
| Mass infrastructure error | DB unavailable, continuous HTTP 503s | Cap retries; controlled stop/restart |

No single formula fits every batch: financial reconciliation may demand **zero rejects**, whereas non-critical ingestion can tolerate a small error rate.

## 7. Quarantine: Preserving Bad Records for Investigation and Repair

**Quarantine** is a controlled storage area for rejected data. The goal is preserving evidence needed to fix upstream sources without polluting official target tables with invalid items.

A quarantine record can include:

| Field | Role |
| --- | --- |
| `source_batch_id` | Identifies the original file/snapshot batch |
| `record_locator` | Source position or stable row ID for lookup |
| `stage` | `READ`, `PROCESS`, or `WRITE` |
| `reason_code` | Fixed error code such as `INVALID_AMOUNT` |
| `rejected_at` | Timestamp when the error was recorded |
| `status` | `NEW`, `REVIEWED`, `CORRECTED`, `REPLAYED`, ... |
| `payload_pointer` or encrypted payload | Path/key to original record in an access-restricted store |
| `job_execution_id` | Links back to run metadata |

Simply logging `row invalid` and moving on leaves no way to fix records when failures occur at scale. Conversely, **never dump raw payloads into logs** for debugging convenience; payloads may hold emails, account numbers, or sensitive PII. Quarantine stores require access controls, encryption, retention policies, and audit trails.

### 7.1. Using `SkipListener` to Record Skipped Items

`SkipListener<I,O>` in Spring Batch 5 provides:

```java
void onSkipInRead(Throwable error);
void onSkipInProcess(I item, Throwable error);
void onSkipInWrite(O item, Throwable error);
```

Example listener logging structured events and safe references **without printing raw items or exceptions**:

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class SafeRejectLogListener
        implements SkipListener<RawOrder, ValidOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(SafeRejectLogListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        // When parsing fails, a valid RawOrder may not exist to extract a key.
        log.warn("event=order_rejected stage=read "
                + "record_ref=unavailable reason=BAD_SOURCE_RECORD");
    }

    @Override
    public void onSkipInProcess(RawOrder item, Throwable error) {
        log.warn("event=order_rejected stage=process "
                + "reason={}", safeReason(error));
    }

    @Override
    public void onSkipInWrite(ValidOrder item, Throwable error) {
        log.warn("event=order_rejected stage=write "
                + "reason=WRITE_REJECTED");
    }

    private String safeReason(Throwable error) {
        if (error instanceof InvalidOrderException) {
            // Fixed code, do not return Throwable.getMessage().
            return "INVALID_ORDER";
        }
        return "UNCLASSIFIED_FAILURE";
    }
}
```

This listener shows **when an item is actually skipped**; it is not a complete quarantine store. Attach it via `.listener(rejectListener)` after `faultTolerant()` in Section 5's step builder. To persist raw records or exact locators for repair, a dedicated `RejectRepository`/quarantine writer must handle transactions and access control.

### 7.2. Why `onSkipInRead` Has No `item`

When a parser fails to construct `RawOrder`, the read-skip callback has no valid item to pass. Some readers include line numbers or source offsets in the exception, yet `FlatFileParseException` can also hold **the entire raw input line**. Never call `getInput()` or log full exceptions to general log streams. For replays, use approved file/version identifiers and offsets to look up records in protected source storage.

### 7.3. Transactional and Idempotent Quarantine

`SkipListener` is invoked by Spring Batch along the fault-tolerant step lifecycle. When writing quarantine rows to a database, clarify:

- Does the reject table share **the same datasource and transaction manager**, or use a separate transaction?
- If a chunk rolls back, do reject rows roll back too?
- If the process crashes right after commit, is there reconciliation to catch unsynced rejects?
- On restart/replay, how do you avoid inserting duplicate reject rows or duplicate output?

For high-reliability quarantine, write rejects/outbox rows in the same transaction as staging data using a unique key on `(source_batch_id, record_locator, reason_code)` or suitable business key. Post-commit, another worker can push records to a restricted quarantine store. Depending on source and skip mechanics, test failures across read/process/write; never assume every log line or callback produces exactly one durable record in all cases.

## 8. Using Staging and a Conditional Publish Gate

With bulk failures, the core issue is not only `FAILED` vs. `COMPLETED`, but **whether downstream consumers are allowed to read incomplete data**. A safer architecture:

```text
Incoming source + manifest
        |
        v
ValidateSourceStep  ---- invalid ---> FAILED + alert
        |
        v
ImportToStagingStep
        |            \
        |             \-- invalid rows --> Quarantine (restricted)
        v
ReconcileStep
        |
        +-- rejected > allowed ------> No publish, FAILED
        +-- counts/checksum mismatch -> No publish, FAILED
        |
        v
PublishStep
        |
        v
Published snapshot / ready marker
        |
        v
Downstream consumers
```

Staging tags rows with `sourceBatchId`/`runId` to isolate in-flight work from published data. Only when all quality gates pass does `PublishStep` promote the new snapshot to active status (e.g., flipping a version pointer in one transaction or atomically publishing a verified file).

If an ingestion step writes directly into production tables, failing on item 20,001 leaves earlier chunks committed; `JobExecution` becoming `FAILED` **does not roll back previously completed chunks**. That is why staging/publish gates are vital whenever bulk failures threaten completeness.

### 8.1. Distinguishing Technical Completion from Business Completion

A step can finish `COMPLETED` with 20 skipped items because that is within `skipLimit`. That means the framework honored the technical policy, **not necessarily that output is acceptable**. You may need a `reconcileAndPublishStep` checking:

```text
source_expected_count
  = accepted_count
  + rejected_count
  + filtered_count (if any, per separate rule)
```

Do not apply this formula mechanically when records span multiple lines, duplicates are collapsed, upserts overwrite rows, or one input spawns multiple target rows. The reconciliation contract must define exactly what each counter measures.

Beyond counts, financial data may require amount sums, key checksums, source versions, and group subtotals. Matching total row counts alone can mask one dropped record canceled out by one duplicate.

## 9. Restart and Replay Once Data Is Fixed

Suppose on Nov 16 `sourceBatchId=orders-20261116-v1` failed after exceeding `skipLimit`. After the source team fixes the file, two options exist:

### 9.1. Restarting the Same `JobInstance`

When source inputs and checkpoints remain valid, you can **restart** the `FAILED` job using the exact same identifying `JobParameters`:

```text
JobInstance(importOrdersJob, sourceBatchId=orders-20261116-v1)
├── JobExecution #1: FAILED
└── JobExecution #2: restart attempt
```

Preconditions:

- `JobRepository` retains metadata and the job/step allow restarts.
- The reader maintains valid checkpoints; source input stayed **immutable** relative to already-read positions.
- Writers and quarantine are idempotent so replayed chunks create no duplicates.
- Policy prohibits silently swapping source files under the same ID.

If the source file was edited in place while keeping the same path and old checkpoint, restarting may resume at an offset that no longer lines up with original records. In bulk-error scenarios caused by bad files, this is a serious risk.

### 9.2. Replaying from Fixed Source or a New Batch Version

When source data was repaired or replaced, the safer path is creating **a new source version**:

```text
orders-20261116-v1  -> REJECTED / NOT_PUBLISHED
orders-20261116-v2  -> VALIDATED -> INGESTED -> PUBLISHED
```

Rerun with a new identifying `sourceBatchId`, record `supersedes=v1`, and explicitly handle old staging rows. If replaying only quarantined items:

- Require a stable business/source key to identify corrected items.
- Never accidentally re-ingest previously accepted records improperly.
- Enforce upserts or unique constraints per the data contract.
- Re-reconcile total counts and business sums after replay.
- Mark rejected items as fixed, replayed, and resolved.

**Changing identifying parameters creates a new `JobInstance`**, not a restart of the old instance. This is right when ingesting a new source version, provided target tables prevent duplicates.

### 9.3. Never Delete `BATCH_*` Tables to Rerun

Deleting metadata destroys reconciliation, checkpoints, and restart integrity. In operations, rely on Spring Batch APIs, explicit source versioning, and controlled replay workflows; never manually hack `JobExecution` statuses just to force a run.

## 10. Mass Infrastructure Errors Need Different Handling from Bad Data

When the database goes unreachable or an API returns 503 for every item, routing thousands of items to quarantine as "invalid" is semantically wrong. The items **may be completely valid**; the external dependency failed.

Example processor calling a service:

```text
item 1: HTTP 503 -> retry -> HTTP 503
item 2: HTTP 503 -> retry -> HTTP 503
item 3: HTTP 503 -> retry -> HTTP 503
...
```

If each item retries three times, an outage easily fires millions of useless requests. Instead:

1. Classify dependency failures with dedicated exceptions, such as `PartnerUnavailableException`.
2. Apply bounded retries with `retryLimit` and backoff; never retry validation failures.
3. Bound concurrent requests and total retry budgets per job/window.
4. When infrastructure error rates spike, trip fail/stop/circuit breakers at the orchestrator or service layer to relieve load.
5. Restart once the dependency recovers using **the same identifying parameters** if resuming the old instance.

Spring Batch supports retries inside fault-tolerant steps; whole-job circuit breakers and global error-rate cutoffs usually require additional logic or tooling. Do not assume `.retryLimit(3)` stops systemic outages when every item still gets three tries.

## 11. Observing Bulk Failure Scope via Metrics and Logs

A dashboard should show **blast radius**, not just per-item exception dumps:

| Metric | Meaning |
| --- | --- |
| `source_expected_count` | Expected total records from manifest |
| `read_count` | Items successfully read per Spring Batch |
| `read_skip_count` | Skipped read errors |
| `process_skip_count` | Items skipped in processor |
| `write_skip_count` | Items skipped in writer |
| `skip_count` | Total step skips |
| `accepted_count` | Business items accepted per contract |
| `quarantined_count` | Records durably stored in quarantine |
| `retry_attempt_count` | Retry attempts measured by listener/custom metric |
| `unpublished_batch_count` | Batches failing publish preconditions |
| `error_rate_by_reason` | Error rate broken down by classified reason code |

`StepExecution` provides core counters:

```java
for (var step : jobExecution.getStepExecutions()) {
    log.info(
            "event=batch_step_summary step={} status={} "
            + "read={} write={} skip={} read_skip={} "
            + "process_skip={} write_skip={} rollback={}",
            step.getStepName(),
            step.getStatus(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getSkipCount(),
            step.getReadSkipCount(),
            step.getProcessSkipCount(),
            step.getWriteSkipCount(),
            step.getRollbackCount());
}
```

This illustrates logging where `jobExecution` and logger `log` are in scope. Never infer retry counts directly from `readCount`, `writeCount`, or `rollbackCount`, because transactions and fault tolerance can re-invoke operations in ways that do not shift counters intuitively.

Never log raw `item.toString()`, CSV lines, or unfiltered `Throwable`s. Parse exceptions can carry raw input, and `JobParameters` may hold sensitive details. Log fixed reason codes, job/step execution IDs, and approved references. Keep high-cardinality fields like `record_id` or `sourceBatchId` out of metric labels; index them in access-controlled logs/audits instead.

### 11.1. Early Alerting on Error Spikes

An absolute skip cap only trips once enough items fail. For huge files, add **sliding-window** monitoring, such as >20% errors across the last 500 items or 50 identical error codes within 60 seconds. Such rules need thread-safe counters or time-windowed telemetry and guards against false positives on small sample sizes.

Job-level metrics/alerts complement `skipLimit` rather than replacing it. Alerts can trigger a `STOPPING` signal or flag the source for review, using safe stop/rollback mechanics so partial data is not exposed.

## 12. Testing Recovery Under Mass Bad Records

Test both **counts** and **business outcomes**, not merely `BatchStatus.COMPLETED`.

### 12.1. Test Matrix

| Scenario | Test Data | Expected Result |
| --- | --- | --- |
| Zero errors | 1,000 valid records | `COMPLETED`, full output |
| Few validation errors | 1,000 records, 2 bad | `COMPLETED` if policy allows; 2 quarantined |
| Exactly at skip limit | 100 records, 20 bad with `skipLimit(20)` | May be `COMPLETED` if all other checks pass |
| Exceeding skip limit | 100 records, 21 bad | Step/job `FAILED` on next skippable error |
| Bad header/schema | Wrong file version | Preflight `FAILED`, zero staging writes |
| Truncated file | Checksum/line-count mismatch | File rejected before publish |
| DB/API outage | All items hit transient failures | Bounded retry/backoff, eventually fails/stops |
| Chunk writer error | Transaction fails after earlier chunks committed | Incomplete staging data not published |
| Restart after failure | Same identifying parameters, metadata preserved | Resumes from checkpoint with zero duplicates |
| Replay fixed source | v2 file with new source batch | Accurate data, quarantine reconciled |
| Quarantine writer failure | Rejected record fails to persist | Never silently reports success when evidence is lost |

### 12.2. Example Integration Test with `JobLauncherTestUtils`

In a Spring Boot project, add:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

The test class below assumes the job beans from Section 5 are loaded, H2 has `BATCH_*` and `accepted_orders` tables, and `src/test/resources/bulk-errors/mostly-valid.csv` holds the five records from Section 3:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
})
class BulkInvalidOrdersTest {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job job;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void prepare() {
        launcher.setJob(job);
        // Clean only the output table in the isolated test database.
        jdbcTemplate.update("DELETE FROM accepted_orders");
    }

    @Test
    void skipsTwoInvalidOrdersAndWritesThree() throws Exception {
        String path = new ClassPathResource(
                "bulk-errors/mostly-valid.csv")
                .getFile()
                .getAbsolutePath();

        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", path)
                .addString("sourceBatchId", "fixture-mostly-valid")
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution result = launcher.launchJob(params);

        assertThat(result.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        StepExecution step = result.getStepExecutions()
                .iterator().next();

        assertThat(step.getReadCount()).isEqualTo(5);
        assertThat(step.getProcessSkipCount()).isEqualTo(2);
        assertThat(step.getSkipCount()).isEqualTo(2);
        assertThat(step.getWriteCount()).isEqualTo(3);

        Integer saved = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM accepted_orders",
                Integer.class);
        assertThat(saved).isEqualTo(3);
    }
}
```

`ClassPathResource.getFile()` works in tests when resources live directly on the filesystem; it will not work verbatim for resources packaged inside an executable JAR. This test uses a unique `run.id` per run to avoid colliding with completed `JobInstance`s; **never change identifying parameters when testing same-instance restarts**.

The test above checks only the case **under** `skipLimit(20)` against one test table. To verify bulk-error cutoffs, add a test with 21 invalid rows asserting `FAILED` and verifying data was not published. When using staging, tests should assert publish status alongside technical counters.

### 12.3. Testing Restarts and Source Immutability

A complete scenario:

1. Create file version `v1`, manifest with checksum, and a stable batch ID.
2. Run the job, fail the writer on a chosen chunk, and assert `FAILED`.
3. Keep `v1`, `JobRepository`, and **the same identifying `JobParameters`** intact; rerun to verify restart.
4. Confirm output rows have no duplicates, quarantine has no duplicates, and checkpoints match processed work.
5. Supply corrected `v2` with a new `sourceBatchId`; run replay per the replace/remediation policy.
6. Reconcile input, accepted, rejected, and published output rather than checking `COMPLETED` alone.

If sharing a database across multiple tests, isolate data/metadata by schema or container. Never wipe all batch metadata on a database with active executions.

## 13. Common Design Mistakes

| Mistake | Harm | Better Practice |
| --- | --- | --- |
| `skip(Exception.class)` with huge limit | Hides system failures and programming bugs | Allowlist specific data exceptions to skip |
| Retrying validation failures endlessly | Wastes CPU, I/O, and time on static bad data | Route to reject/quarantine |
| No header/manifest validation | Rejects rows en masse due to schema changes | Preflight file before ingesting |
| Setting only absolute skip counts without ratios | Small batches can lose most of their data | Add ratio thresholds over a well-defined total |
| Publishing immediately on `COMPLETED` | Output may lack many skipped items | Reconcile and publish behind a gate |
| Writing directly to production tables before failing | Earlier chunks committed; downstream sees partial data | Staging + versioning + atomic publish |
| Dropping failed items without saving them | No input left for repair/replay | Quarantine with source locator and reason code |
| Logging raw CSV/exceptions | Leaks customer PII | Fixed error codes and protected references |
| Swapping source file while keeping old checkpoint | Restart reads at wrong offsets/records | Keep sources immutable; bump version on changes |
| Changing `run.id` to restart | Creates new instance, risks duplicate processing | Preserve identifying parameters |
| Treating HTTP 503 outages as invalid items | Quarantines valid records en masse | Bounded retry/backoff; fail on infra outages |
| Replaying without idempotency | Duplicates output rows and reject entries | Unique keys/upserts, versioning, audit, reconciliation |
| Counting log lines as error counts | Retries/rollbacks duplicate log entries | Use StepExecution and transactional audit stores |

## 14. Practice Exercises

Extend `importOrdersJob` in an isolated test database:

1. Create three files: 1,000 valid records, 1,000 records with 10 scattered errors, and 1,000 records with 300 errors. Ensure all IDs and values are synthetic.
2. Write a preflight step checking header, manifest, checksum, record count, and schema version. A wrong header must fail the job before staging writes.
3. Configure skips for `InvalidOrderException` and permitted parse errors with `skipLimit(20)`. Observe runs with 10, 20, and 21 invalid items.
4. Add a 0.5% error-rate policy. For 1,000 records, explain why 10 errors breach the policy even though under the absolute cap of 20.
5. Build quarantine storage with `sourceBatchId`, source locator, reason code, and status. Verify no sensitive payloads hit logs.
6. Switch the writer from production tables to staging tables, publishing only when counts and business totals match. Fail the job in a later chunk and confirm downstream does not see the new snapshot.
7. Simulate an API outage returning 503 for all items: apply bounded retry with backoff, track request counts, and halt per policy.
8. Create a `FAILED` job, rerun with the exact identifying `JobParameters`, and confirm restart creates zero duplicates.
9. Create repaired file `v2` with a new `sourceBatchId` to replay. Reconcile the new snapshot against `v2` and mark the old batch unpublished.
10. Produce an operational per-batch report: total input, accepted, rejected, errors by category, batch status, publish status, and next remediation step.

**Key takeaway:** When bad data arrives in bulk, recovery is not just raising `skipLimit`. The system must **separate data errors from infrastructure outages, validate source contracts, bound rejections, preserve traces for remediation, and publish outputs only after reconciliation**. Combining Spring Batch fault tolerance with staging, quarantine, source versioning, and controlled restarts/replays recovers safely without silently losing business data.

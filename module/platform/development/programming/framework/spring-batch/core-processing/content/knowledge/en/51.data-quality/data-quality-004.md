# Input-Output Total Reconciliation in Spring Batch: Controlling Data Quality

A Spring Batch job ending with status `COMPLETED` is not enough to prove that all data requiring processing reached the right destination without omissions, duplicates, or wrong values. For example, if a job reads 10,000 transactions from CSV yet creates only 9,997 rows in the database, the three-row difference could be transactions filtered by rule, skipped after data errors, dropped as duplicates by an UPSERT, or genuinely lost. Without **input–output reconciliation**, those cases are very hard to tell apart.

In **Spring Batch Core Processing → Data quality**, "input-output total reconciliation" means proving via counts, value totals, and business identifiers that **source data is fully accounted for and target data matches the processing rules**. The focus is not merely comparing two numbers; you must define *what is being counted*, *when it is counted*, and *which transformations alter counts or values*.

This lesson uses Spring Batch 5.x or later with chunk-oriented processing, `StepExecution`, `JobRepository`, JDBC, and a small CSV dataset for illustration. The principles also apply to ETL, order ingestion, payments, reporting, data synchronization, and pipelines reading/writing outside a database.

## 1. Why Reconcile When the Job Already Reports COMPLETED?

`BatchStatus.COMPLETED` primarily indicates that the job or step finished along its configured control flow. That status can still appear when:

- The processor intentionally returns `null` to **filter** out-of-scope rows.
- The step is allowed to **skip** a number of invalid records within a threshold.
- The writer uses `INSERT ... ON CONFLICT DO NOTHING`, sending many items to the writer while fewer new rows appear.
- The writer expands one item into multiple target rows, or aggregates multiple items into one row.
- Outputs in non-database systems have latency or provide only *at-least-once* delivery.
- An output file was created but is missing rows, has wrong encoding, or has not been safely published.
- Target data already contains records from a prior run, so the final row count does not reflect the current run alone.

Conversely, `FAILED` does not mean every result was rolled back. In a chunk-oriented step, previously committed chunks typically remain when a later chunk fails. Therefore, reconciliation must inspect **actual data state**, not just execution status.

### Three Foundational Questions

1. **What is the input?** All physical lines in the file, data rows after the header, items successfully parsed by the reader, or the set of unique business records?
2. **What is the output?** Items passed to the writer, items recorded by `writeCount`, committed rows, unique transactions, or published amount totals?
3. **Which differences are allowed?** Are filtering, skipping, cancellations, aggregation, splitting, deduplication, currency conversion, and rounding described in the data contract?

Without answering these questions, the formula `inputCount == outputCount` can trigger false alarms or miss real bugs.

## 2. Reconciliation Levels

| Level | Reconciliation Metric | Example | What Does It Catch? |
|---|---|---|---|
| **Count** | Number of lines, items, records, or business keys | 7 source rows → 4 target rows + 3 accounted-for rows | Missing/extra records by volume |
| **Value (control total)** | Total amount, weight, points, or item quantity | Valid total 200.00 → target total 200.00 | Wrong value totals even when row counts match |
| **Identifier (key reconciliation)** | Accepted source ID set vs. target ID set | `TX-001, TX-002, TX-006, TX-007` | One missing ID and one duplicate ID even when counts match |
| **Grouped** | Count and sum by date, source, status, currency | USD matches but VND is missing 1 record | Errors hidden when looking only at global totals |
| **Content** | Field-by-field values, canonical checksum with stable rules | Same ID but different amount | Record exists yet data is wrong |
| **Point-in-time** | Snapshot, cutoff, watermark, version | File version v2 vs. output v2 | Comparing two datasets from different periods |
| **Uniqueness** | Duplicate count per business key | Each `event_id` must appear once | Duplicates from retry/restart or source |

Not every job needs all levels. For monetary imports or financially impactful workflows, **count + sum + key** is far stronger than count alone. For many-to-one aggregated outputs, compare at the same *grain* instead of forcing source and target row counts to be equal.

## 3. Defining Grain and the Reconciled Dataset

**Grain** is the unit each record represents. For example:

- Input: one CSV line = one payment event.
- Output: one `ledger_entry` row = one accepted payment event.
- Or output: one `daily_summary` row = total amount for an entire day and currency.

In the first case, valid event count can be expected to equal target row count. In the latter case, several thousand source events may collapse into a handful of summary rows; physical counts should not be equal.

At the same time, lock down **data boundaries**:

| Component | Example | Rule |
|---|---|---|
| `businessDate` | `2026-11-15` | The business date, never inferred from execution wall-clock time. |
| `sourceId` | `warehouse-A` | Identifies the source, avoiding mixing multiple feeds. |
| `sourceVersion` | `v1` or source checksum | Distinguishes a changed file from an earlier run. |
| `batchKey` | `2026-11-15:warehouse-A:v1` | Key linking input, output, and reconciliation results. |
| `cutoffTime` | Fixed snapshot boundary | Never compare pre-cutoff input against output mutating post-cutoff. |
| `currency` | `VND` or `USD` | Never sum different currencies without conversion rules. |

Before reading files or querying a live mutating source, obtain a **manifest/snapshot**: logical source name, version, cutoff timestamp, expected data row count, and checksum when applicable. Simply recounting a source receiving live transactions while the job runs can yield differing numbers even when the batch is completely correct.

## 4. Understanding Spring Batch Counters Properly

`StepExecution` provides important counters for a step execution. These values help explain an item's path, yet **they do not replace independent verification at source and target**.

| `StepExecution` Field | Typical Meaning in a Chunk-Oriented Step |
|---|---|
| `getReadCount()` | Items successfully read as recorded by the step. |
| `getReadSkipCount()` | Failed items/reads skipped during the read stage. |
| `getFilterCount()` | Items filtered by the processor, typically when `process(...)` returns `null`. |
| `getProcessSkipCount()` | Items failing in the processor and skipped. |
| `getWriteCount()` | Items recorded by the step as successfully written through the writer. |
| `getWriteSkipCount()` | Items skipped during the writer stage. |
| `getCommitCount()` | Recorded commit count. |
| `getRollbackCount()` | Recorded rollback count. |
| `getStatus()` / `getExitStatus()` | Step execution status and exit result. |

Interpretation notes:

- `readCount` counts **successfully read items**, not necessarily physical lines in a file. Headers, blank lines, skipped-line callbacks, and reader configuration can change this relationship.
- `readSkipCount` does not necessarily include every physical line ignored by reader configuration; some lines may never become items in the first place.
- `filterCount` usually reflects the processor returning `null` by policy. That is not an error to alert on if it follows the contract.
- `writeCount` measures items under Spring Batch's model, **not guaranteeing the same committed row count** when a writer performs UPSERTs that ignore rows, splits/merges items, or writes to a non-transactional system.
- Counters are scoped to a `StepExecution`; when a job restarts with a new execution or reruns a step, never blindly sum counters across all history to derive the final unique record count.

### A Counting Equation with Explicit Assumptions

In a **completed step**, if each successfully read item yields at most one output item, filters and skips exclude items from the writer, there is no one-to-many transformation, and the writer actually writes one row per item, a useful sanity check is:

\[
\text{readCount} =
\text{filterCount} + \text{processSkipCount} +
\text{writeSkipCount} + \text{writeCount}
\]

At the source file level, if **every data line** is classified by the reader as either a successfully read item or a skippable read error with no silently dropped data lines, then:

\[
\text{sourceDataLines} = \text{readCount} + \text{readSkipCount}
\]

Both equations are **conditional invariants**, not formulas guaranteed for every Spring Batch configuration. With complex retries, writers with side effects, multi-resource writers, readers that skip lines internally, non-1:1 writer outcomes, or interrupted jobs, adjust counting methods and data sources accordingly. For critical data, always reconcile against **actual committed output**.

## 5. End-to-End Example: Seven Input Rows, Four Output Records

Suppose a job receives a payment CSV. Business rules: positive amounts are written, zero amounts are filtered, negative amounts are rejected in the processor, and unparseable amount strings are skipped in the reader. Each accepted item produces one target record.

`payments-test.csv`:

~~~csv
event_id,customer,amount
TX-001,An,100.00
TX-002,Binh,50.00
TX-003,Chi,abc
TX-004,Dung,0.00
TX-005,Ha,-20.00
TX-006,Lan,30.50
TX-007,Mai,19.50
~~~

The first line is the header; there are **7 data rows**. Expected outcomes:

| Event | Amount | Outcome | Deciding Layer |
|---|---:|---|---|
| `TX-001` | 100.00 | Write | Writer |
| `TX-002` | 50.00 | Write | Writer |
| `TX-003` | `abc` | Read skip due to type parse error | Reader |
| `TX-004` | 0.00 | Filter per assumed rule | Processor |
| `TX-005` | -20.00 | Process skip due to validation | Processor |
| `TX-006` | 30.50 | Write | Writer |
| `TX-007` | 19.50 | Write | Writer |

After one complete execution, with appropriate fault-tolerance configuration and no unexpected retries/write skips:

~~~text
sourceDataLines  = 7
readCount        = 6
readSkipCount    = 1
filterCount      = 1
processSkipCount = 1
writeSkipCount   = 0
writeCount       = 4
outputRows       = 4
acceptedAmount   = 200.00
outputAmount     = 200.00
~~~

Reconciliation breakdown:

~~~text
Source:                7 data rows
  ├─ Read skip:        1  (TX-003)
  └─ Read succeeded:   6
       ├─ Filter:        1  (TX-004)
       ├─ Process skip:  1  (TX-005)
       └─ Write:         4  (TX-001, TX-002, TX-006, TX-007)

7 = 1 + 1 + 1 + 4
Accepted amount total: 100.00 + 50.00 + 30.50 + 19.50 = 200.00
Persisted amount total: 200.00
~~~

Notable point: **7 not equaling 4 is the right result**, because the three-row difference has categorized causes. If you only assert `sourceDataLines == outputRows`, the test fails falsely. Conversely, if you only check `writeCount == 4` while the database actually holds only three rows, data is still missing.

### Defining the "Accepted" Count

A clear formulation:

\[
\text{acceptedInputCount}
= \text{sourceDataLines}
- \text{readRejectedCount}
- \text{filteredCount}
- \text{processRejectedCount}
\]

In this example, `acceptedInputCount = 4`. Distinguish **rejected** from **filtered**:

- *Rejected*: data that cannot or must not be processed under the contract, usually requiring error reporting/quarantine.
- *Filtered*: valid data excluded strictly by business rules.

Do not lump both into "lost records." Data error rate, filter rate, and records requiring reprocessing carry different operational meanings.

## 6. Count Reconciliation Alone Can Still Miss Errors

Suppose valid input has four IDs `A, B, C, D`, and after the job the database also has four rows, yet they are `A, B, C, C`. Comparing counts gives `4 == 4`, while **D is missing and C is duplicated**.

Another case: input has amounts `100` and `200`; output has `150` and `150`. Record counts still match, and sums still equal 300, yet **every individual record's value is wrong**.

Therefore, for critical data, verify across multiple dimensions:

| Check | Question Answered |
|---|---|
| `COUNT(*)` | How many target rows exist? |
| `COUNT(DISTINCT event_id)` | How many unique event keys exist? |
| Accepted `event_id` set minus target `event_id` set | Which IDs are missing? |
| Target set minus accepted set | Which IDs are extra? |
| `SUM(amount)` per business group | Is any value total wrong? |
| Comparing amount by `event_id` | The record is present, but is its data accurate? |
| Canonical checksum/digest with fixed rules | Is the normalized content equivalent? |

Key sets and per-key record comparisons are usually **stronger evidence** than a pair of totals. For large datasets, reconcile using SQL joins, anti-joins, or indexed aggregations; there is no need to load every ID into the JVM.

## 7. Storing Input Evidence Independently of Output

For reliable reconciliation, establish "expected figures" from a source independent of the target write operation. If a job merely writes four rows and then declares "expected output = the four rows I wrote," the check becomes meaningless.

A simple **source manifest** can contain:

~~~json
{
  "batchKey": "2026-11-15:warehouse-A:v1",
  "sourceId": "warehouse-A",
  "businessDate": "2026-11-15",
  "sourceVersion": "v1",
  "fileName": "payments-2026-11-15.csv",
  "dataLineCount": 7,
  "fileSha256": "<digest-of-original-file>",
  "encoding": "UTF-8"
}
~~~

`fileSha256` is an illustrative checksum, which should be computed from **the bytes of the finalized file**, not from a file changing while the job runs. The manifest must specify how headers and blank lines are counted; `dataLineCount=7` in the example **excludes the header**. Do not use checksums to replace business key rules or item-level validation.

A snapshot can be produced by an upstream data contract, an independent preflight step, or the file ingestion gateway before job processing. If the same reader computes the manifest itself, it remains operationally useful, though the check's independence is lower; always understand where the numbers originate.

### Tracking Per-Record Status via Quarantine/Audit

To explain discrepancies, persist processing states in an appropriate store:

~~~text
batchKey=2026-11-15:warehouse-A:v1
TX-001 -> ACCEPTED
TX-002 -> ACCEPTED
line 4 -> READ_REJECTED
TX-004 -> FILTERED
TX-005 -> PROCESS_REJECTED
TX-006 -> ACCEPTED
TX-007 -> ACCEPTED
~~~

Note: a row that fails during read may not yet yield an `event_id`, so use a source identifier like `sourceLineNumber` or an opaque record reference for reconciliation. Audit/quarantine records may contain sensitive data; store only what is necessary and enforce proper access controls and retention.

If audits are written inside a listener **outside the transaction**, a retry or rollback can create duplicate audit rows. Design an idempotency key per event/status or coordinate transactions properly. Never assume audit row count equals actual item count merely because the listener fired once in a trivial test.

## 8. Reconciling Committed Output with SQL

Suppose the writer inserts into a PostgreSQL table:

~~~sql
CREATE TABLE processed_payment (
    batch_key VARCHAR(120) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, event_id)
);
~~~

`batch_key` ties output to a processing period/version. The primary key constraint prevents duplicate writes of the same event within a batch. If the business requires an event ID to be unique across **all batches**, adjust the unique constraint per that policy; a key containing `batch_key` only protects within that batch.

After the write step completes, reconcile against the **target database**:

~~~sql
SELECT
    COUNT(*) AS output_rows,
    COUNT(DISTINCT event_id) AS distinct_events,
    COALESCE(SUM(amount), 0.00) AS output_amount
FROM processed_payment
WHERE batch_key = :batchKey;
~~~

For the example in section 5, the expected result is:

~~~text
output_rows     = 4
distinct_events = 4
output_amount   = 200.00
~~~

The strength of this query is that row counts and amounts reflect **final data visible in the database**, not merely how many items the step passed to the writer. However, if the job is still running and chunks are committing continuously, the query can observe an intermediate state. Reconcile after the write step finishes or under an explicitly defined snapshot/isolation level.

### Checking for Duplicate Keys

If the table lacks a unique constraint or you need to inspect historical data:

~~~sql
SELECT event_id, COUNT(*) AS occurrences
FROM processed_payment
WHERE batch_key = :batchKey
GROUP BY event_id
HAVING COUNT(*) > 1;
~~~

The ideal query result is **zero rows**. Yet `COUNT(DISTINCT event_id)` only checks for duplicate IDs within the filtered dataset; it does not prove all expected IDs are present.

### Finding Missing or Extra IDs

Suppose the system has a staging table `accepted_payment` holding the list of **accepted inputs**, stored consistently:

~~~sql
-- Events accepted but missing from output.
SELECT a.event_id
FROM accepted_payment a
LEFT JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND p.event_id IS NULL;

-- Events present in output but not in the accepted set.
SELECT p.event_id
FROM processed_payment p
LEFT JOIN accepted_payment a
  ON a.batch_key = p.batch_key
 AND a.event_id = p.event_id
WHERE p.batch_key = :batchKey
  AND a.event_id IS NULL;
~~~

Both queries ideally return **0 rows** when the contract requires 1:1 mapping. The `accepted_payment` set must be designed as a sufficiently independent expectation source; if it is merely populated afterward by copying from `processed_payment`, the anti-join loses all meaning.

### Finding Value Mismatches on the Same Key

~~~sql
SELECT
    a.event_id,
    a.expected_amount,
    p.amount AS actual_amount
FROM accepted_payment a
JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND a.expected_amount <> p.amount;
~~~

With exact `NUMERIC/DECIMAL`, comparisons operate on normalized units. If rounding rules, currency conversions, or tolerances apply, compute `expected_amount` using those exact rules; do not run arbitrary inequality checks.

## 9. Reconciling Monetary Totals

Having the right row count does not guarantee the total amount is right. For financial data, the control total is a critical metric:

\[
\text{expectedOutputAmount}
= \sum_{\text{item accepted}} \text{transformedAmount}
\]

\[
\text{amountDifference}
= \text{actualOutputAmount}
- \text{expectedOutputAmount}
\]

In our example:

~~~text
expectedOutputAmount = 100.00 + 50.00 + 30.50 + 19.50
                     = 200.00
actualOutputAmount   = 200.00
amountDifference     = 0.00
~~~

### Do Not Sum Different Currencies Together

If input contains both VND and USD, a table-wide `SUM(amount)` can be meaningless. Reconcile grouped by currency:

~~~sql
SELECT
    currency,
    COUNT(*) AS row_count,
    COALESCE(SUM(amount), 0.00) AS amount_total
FROM processed_payment
WHERE batch_key = :batchKey
GROUP BY currency;
~~~

This query assumes the extended schema includes a `currency` column. If the job converts currencies, lock in the exchange rate, rate timestamp, rounding rules, and post-conversion expected amount; never directly compare raw original totals with converted totals.

### Use BigDecimal Instead of double

In Java, monetary values should use `BigDecimal` or an appropriate exact numeric type, avoiding `double` when reconciling amounts:

~~~java
import java.math.BigDecimal;

BigDecimal expected = new BigDecimal("200.00");
BigDecimal actual = new BigDecimal("200.00");

boolean equalByValue = expected.compareTo(actual) == 0;
BigDecimal difference = actual.subtract(expected);
~~~

`BigDecimal.equals(...)` also compares scale: `200.0` and `200.00` are not `equals` even though they are numerically equal. Unless the contract requires identical scale, use `compareTo(...) == 0`. For workflows requiring rounding rules, apply the defined `scale` and `RoundingMode` before comparing.

### Tolerance in Reconciliation

For non-monetary data, reconciliation sometimes allows a tolerance:

\[
|\text{actual} - \text{expected}| \le \text{tolerance}
\]

Do not pick a large tolerance just to make tests pass. Tolerance must originate from the transformation contract, measurement precision, or accepted rounding. For accounting money in normalized minor units, many systems require a discrepancy of **zero**.

## 10. Placing Reconciliation in the Job Flow

A common design separates input admission, processing/writing, and reconciliation:

~~~mermaid
flowchart TD
    A["Preflight: lock input snapshot/manifest"] --> B["Load: chunk-oriented read, process, and write"]
    B --> C["Reconcile: count and reconcile target data"]
    C --> D{"Meets quality contract?"}
    D -->|Pass| E["Publish: release output"]
    D -->|Fail| F["Job FAILED / pending investigation"]
~~~

For critical outputs, the **publish** step should happen **after reconciliation passes**—such as moving data from staging to the published set, flipping a version pointer, or emitting a "batch ready" event. If publishing happens inside each writer chunk before global checks, downstream consumers may consume corrupt output before the reconciliation step detects it.

Spring Batch 5.x job example:

~~~java
@Bean
Job importPaymentsJob(
        JobRepository jobRepository,
        Step preflightStep,
        Step loadPaymentsStep,
        Step reconcilePaymentsStep,
        Step publishPaymentsStep) {

    return new JobBuilder("importPaymentsJob", jobRepository)
        .start(preflightStep)
        .next(loadPaymentsStep)
        .next(reconcilePaymentsStep)
        .next(publishPaymentsStep)
        .build();
}
~~~

The steps here are separately configured beans. In the default linear flow, the next step runs only when state transitions permit; if `reconcilePaymentsStep` reports `FAILED`, the job does not proceed to the publish step in a normal successful flow.

Separating steps lets monitoring report: **load succeeded, but reconciliation failed**, rather than seeing an anonymous exception at the end of a writer.

## 11. A Tasklet Reconciling Counts and Amounts After Writing

Suppose preflight stored expectations in a dedicated `batch_expected_total` table:

~~~sql
CREATE TABLE batch_expected_total (
    batch_key VARCHAR(120) PRIMARY KEY,
    expected_rows BIGINT NOT NULL,
    expected_amount NUMERIC(18, 2) NOT NULL
);
~~~

This table holds **the normalized row count and total amount for the accepted item set**. These figures must come from a trusted expectation source under known skip/filter policies and remain durable for reconciliation. It must not simply recompute `COUNT(*)`/`SUM(amount)` from the output table.

An illustrative `Tasklet` using `JdbcTemplate`:

~~~java
import java.math.BigDecimal;

import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.jdbc.core.JdbcTemplate;

record Totals(long count, BigDecimal amount) {}

public class ReconcilePaymentsTasklet implements Tasklet {

    private final JdbcTemplate jdbc;

    public ReconcilePaymentsTasklet(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String batchKey = (String) chunkContext.getStepContext()
            .getJobParameters().get("batchKey");

        Totals expected = jdbc.queryForObject("""
                SELECT expected_rows, expected_amount
                FROM batch_expected_total
                WHERE batch_key = ?
                """,
            (rs, rowNum) -> new Totals(
                rs.getLong("expected_rows"),
                rs.getBigDecimal("expected_amount")),
            batchKey);

        Totals actual = jdbc.queryForObject("""
                SELECT COUNT(*) AS row_count,
                       COALESCE(SUM(amount), 0.00) AS amount_total
                FROM processed_payment
                WHERE batch_key = ?
                """,
            (rs, rowNum) -> new Totals(
                rs.getLong("row_count"),
                rs.getBigDecimal("amount_total")),
            batchKey);

        if (expected == null || actual == null
                || expected.count() != actual.count()
                || expected.amount().compareTo(actual.amount()) != 0) {
            throw new IllegalStateException(
                "RECONCILIATION_MISMATCH for batch key");
        }

        return RepeatStatus.FINISHED;
    }
}
~~~

Registering the `Tasklet` as a step:

~~~java
@Bean
Step reconcilePaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("reconcilePaymentsStep", jobRepository)
        .tasklet(
            new ReconcilePaymentsTasklet(jdbcTemplate),
            transactionManager)
        .build();
}
~~~

Conditions for this example:

1. `batchKey` is a validated job parameter. The job must supply it at launch, and the expectation table must contain a matching row.
2. Expected counts in `batch_expected_total` represent the **final items that ought to be written** after valid filters/rejects, not raw physical lines.
3. `processed_payment` is reconciled by `batch_key`, preventing mixing data from other runs.
4. On mismatch, the tasklet throws an exception, failing the reconciliation step so the downstream publish step does not execute in the success flow.
5. The error message intentionally avoids logging raw customer data. For investigation, record safe summary counts/sums or write to an access-controlled audit table.

This is a minimal **count + sum** example; it does not replace missing/extra key checks, per-row amount checks, per-currency reconciliation, or job-specific rules. In production, represent errors with clear error codes, persist reconciliation reports, and add contract-specific verifications.

### Recording Status and Publishing After Reconciliation

If you persist `PASS`/`FAIL` in an audit table, design a clear result lifecycle: input snapshot, expected/actual values, discrepancies, timestamp, job/step execution IDs, and data version. Never write `PASS` before all required checks finish. If a run fails and restarts, decide how to overwrite or version audits so you do not end up with conflicting `PASS`/`FAIL` entries with ambiguous ordering.

For batch-level atomic publishing, write output to staging keyed by `batchKey`, reconcile, and then **publish the version** via a corresponding transaction or pointer swap. Chunk-level commits alone do not provide atomicity for the whole job.

## 12. Reconciling with Filter, Skip, and Non-1:1 Writers

Not all differences carry the same meaning. Document the accounting rules for each pipeline.

| Processing Pattern | Example | Valid Formula |
|---|---|---|
| Pure 1:1, no skip/filter | One input event → one output row | `acceptedInputCount == outputCount` |
| Intentional filter | Drop events with `amount = 0` | `sourceCount = filtered + rejected + accepted` |
| Skip invalid data | Bad CSV type or invalid field | `sourceCount = readRejected + processRejected + filtered + accepted`, assuming each row is classified once |
| Deduplicate | 2 events with same business key → 1 row | Compare `COUNT(DISTINCT businessKey)` and unique output count; track duplicate count |
| 1:n | One order generates multiple line items | Compare source orders with target `COUNT(DISTINCT order_id)` and line-item counts per mapping |
| n:1 | Many transactions → one daily/currency total | Compare group count, group key sets, and summed amounts; do not require equal row counts |
| Value transformation | Fees, taxes, FX, rounding | Compare post-transform expected against post-transform actual |
| Multiple targets | Database + file + broker | Reconcile each target independently by period/version; note each system's latency and semantics |

### Deduplication

Suppose the source has three rows `A, B, B` and the policy keeps only one event per business key. `sourceDataLines=3` while output rows = 2 can be completely correct, yet must be reported explicitly:

~~~text
sourceDataLines = 3
duplicateLines  = 1
acceptedUnique  = 2
outputUnique    = 2
~~~

If the writer executes `ON CONFLICT DO NOTHING`, `writeCount` may not correspond directly to newly inserted rows; query the target via SQL to verify uniqueness and actual row counts.

### Many-to-One and 1:n

When processors/writers generate aggregated outputs, reconciliation must match the same grain:

~~~sql
-- Example: source expectations normalized by date and currency.
SELECT business_date, currency, SUM(amount) AS expected_total
FROM accepted_payment
WHERE batch_key = :batchKey
GROUP BY business_date, currency;
~~~

Compare each group against the target summary table by the same `business_date`/`currency`. Matching global totals can still hide misallocation between two currencies or two dates.

In 1:n outputs, verifying the parent key set and parent–child foreign-key integrity can be more important than comparing a single total row count.

## 13. Restart, Retry, and Why You Must Not Mechanically Sum Counters

Suppose a `JobInstance` processing the 15th has its first execution `FAILED` after committing two chunks. A subsequent execution restarts and completes. Two `JobExecution` records and multiple `StepExecution` records appear in `JobRepository`.

~~~text
JobInstance=410
  |
  +-- JobExecution=8102 FAILED
  |     chunks 1 and 2 committed
  |
  +-- JobExecution=8103 COMPLETED
        resumed remaining work
~~~

Do not sum `writeCount` from both executions and assume that equals unique rows in the database:

- Some items may be replayed due to rollbacks or checkpoints/business databases in separate transactions.
- The writer may UPSERT or drop duplicates.
- A step may re-run from the start or be skipped on restart depending on configuration.
- Rows from an earlier run may already exist in the target table.
- Some non-database side effects may have occurred during the old attempt without idempotency controls.

**Final reconciliation must rely on the target dataset keyed by business key/version after recovery**, combined with the source snapshot and step audit trail. `StepExecution` helps explain each attempt, but it is not the sole source confirming final business state.

### Keeping the Same Batch Key Across Restarts

When restarting the same `JobInstance`, keep identifying `JobParameters` stable and bind output to the same business key. If each restart changes `batchKey` using a timestamp, old and new data fall into different scopes; counts can report shortages or hide duplicates.

If the business genuinely needs to reprocess an already completed period with v2 source data, create a **new meaningful `sourceVersion`/revision** and define how v2 results publish relative to v1. Do not simply append a random run ID and sum row counts across all versions for the same period.

### Transactions and Post-Commit Reconciliation

With a JDBC writer participating in the chunk transaction, a mid-chunk failure normally rolls back the chunk's uncommitted changes. Already-committed chunks remain. If the target database and `JobRepository` do not share the same transaction, a crash at a sensitive point can desynchronize checkpoints and outputs; idempotency and reconciliation become especially critical.

If the writer calls a non-transactional API/broker, a request timeout does not prove the side effect did not occur. Query target state by event ID or use an idempotency key/outbox before deciding to replay, then reconcile final outcomes once the target reaches a verifiable state.

## 14. Partitioning and Parallel Processing

With `PartitionStep`, remote chunking, or parallel workers, reconciliation must avoid double-counting across partitions.

For example, the source is partitioned by:

~~~text
partition-0: event_id A000-A999
partition-1: event_id B000-B999
partition-2: event_id C000-C999
~~~

Ranges must **not overlap and must cover the full input** per contract. If partitions 0 and 1 both read the same event, summing `readCount` can exceed unique source events without necessarily causing a writer error.

Controls:

1. Define exact predicates/ranges for each partition, including start/end boundaries.
2. Use a **unique business key** to identify items and outputs.
3. Aggregate counts per partition and **verify key sets** at the whole-job level.
4. Reconcile against a source snapshot with the same cutoff, avoiding partitioning over a mutating dataset.
5. When a partition is retried or a worker reruns, deduplicate by record/batch key before computing final totals.

If per-partition metrics are needed, store `partitionId` in audits, but do not sum all callbacks or execution attempts to count unique events. Final totals should reflect the normalized durable dataset.

## 15. Using Reconciliation Results to Control Job Flow

A reconciliation step can return three distinct business statuses:

| Outcome | Condition | Action |
|---|---|---|
| **PASS** | Counts/keys/sums match the contract; no disallowed discrepancy | Allow publishing / mark batch ready. |
| **PASS_WITH_REJECTS** | Rejects/skips are within allowed policy, all cases explained and audited | Publish if business permits; surface reject report. |
| **FAIL** | Missing/extra IDs, wrong sum, exceeded reject limit, incomplete data, or mismatched snapshot | Halt publishing, raise error, retain staging results for investigation. |

These are **application-defined** status names, not default Spring Batch `BatchStatus` values. You can map them via `ExitStatus` to drive flow transitions, while ensuring **a job is never marked successful** when data fails published quality standards.

### When Permitted Error Data Exists

A system may permit up to 0.5% bad lines or up to 10 invalid records. Yet "error rate below threshold" alone is insufficient:

- Were error records properly classified and persisted?
- Are there transaction types **not allowed to be skipped** even when the overall rate is low?
- Does the total amount of accepted items match the output?
- Are there duplicates or missing items not recorded as rejections?

Quality thresholds must be agreed business rules, never added arbitrarily just to reduce job failure rates.

## 16. Logging and Dashboards for Reconciliation

A summary log should contain batch identifiers and numbers, without dumping full source payloads or customer data:

~~~json
{
  "event": "batch.reconciliation.completed",
  "batchKey": "2026-11-15:warehouse-A:v1",
  "jobName": "importPaymentsJob",
  "jobExecutionId": 8103,
  "result": "PASS",
  "sourceDataLines": 7,
  "readRejected": 1,
  "filtered": 1,
  "processRejected": 1,
  "expectedOutputRows": 4,
  "actualOutputRows": 4,
  "expectedAmount": "200.00",
  "actualAmount": "200.00",
  "missingKeys": 0,
  "unexpectedKeys": 0
}
~~~

This is an illustrative schema for **structured logging**, not JSON generated by Spring Batch by default. In systems holding sensitive data, even totals for small groups may require access restrictions; never put raw items, emails, account numbers, or full files into logs.

For metrics, track:

- Total `PASS`/`FAIL` reconciled batches by bounded `jobName` and `sourceId`.
- Counts of rejected, filtered, missing/unexpected, and duplicate records per period.
- Number of batches with non-zero amount discrepancies per currency.
- Latency from source receipt to reconciliation completion.
- Age of unresolved `FAILED` batches.

Never put every unique `eventId`, `jobExecutionId`, or `correlationId` into regular metric tags: cardinality can explode. Keep granular IDs in logs/audits/traces; use metrics for aggregated indicators.

### What Should a Reconciliation Report Store?

A durable report record can include:

~~~text
batchKey
sourceVersion / fileChecksum
jobInstanceId / jobExecutionId
sourceDataLines / parsedItems / rejectedItems / filteredItems
expectedOutputCount / actualOutputCount
expectedTotalsByCurrency / actualTotalsByCurrency
missingKeyCount / unexpectedKeyCount / duplicateKeyCount
result / errorCode / completedAt
~~~

For auditability, the report can also reference lists of missing/extra IDs stored in an access-controlled area. Metadata locked to a period/version and reconciliation timestamp is invaluable when jobs restart or when investigating data weeks later.

## 17. Testing Input–Output Reconciliation

A strong test suite should use small enough datasets to enumerate every event and explain why it is or is not at the target:

| Scenario | Input | Expected Reconciliation |
|---|---|---|
| Valid 1:1 | 3 valid rows, 3 outputs | `PASS` with exact count and sum. |
| Read skip present | One row `amount=abc` | Failing row accounted for in read rejects; remaining outputs accurate. |
| Filter present | One row `amount=0` | Filter count increments; excluded from expected output. |
| Process skip present | One row negative amount | Rejected per policy with audit trail; remaining outputs accurate. |
| Matching count, wrong key | Output missing A and extra E | Key reconciliation **FAILs** even though counts match. |
| Matching count, wrong amount | One ID's amount altered | Value reconciliation **FAILs** even though counts match. |
| Duplicate ID | Source has A, B, B | Deduplication policy applied; distinct and duplicate counts accurate. |
| Writer UPSERT drops duplicates | Writer receives multiple items with same ID | Physical rows and business keys match; do not infer from `writeCount`. |
| Final chunk with one item | 3 items, chunk size 2 | All three outputs present; trailing chunk not dropped. |
| Mid-chunk writer failure | Chunk partially writes then throws | Rolls back as designed; uncommitted data not counted as final output. |
| Restart after committed chunk | First `JobExecution` FAILED, next COMPLETED | Final output complete and unique per batch key. |
| Many-to-one | Many transactions → one daily summary | Compare by groups and sums; do not force equal row counts. |
| Multiple currencies | VND and USD | Discrepancy in either currency detected. |
| Input changes between counts | File v1 swapped for v2 | Source version/checksum mismatch detected; unverifiable result not published. |

In integration tests, let the job write to a test database with fixed input data, then query the actual target and assert `expectedOutputCount`, `expectedAmount`, and the key set. Tests asserting only `BatchStatus.COMPLETED` or `writeCount == 3` do not prove output quality.

### Java Expectation Example

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.math.BigDecimal;
import java.util.Set;

// actualRows is queried from the test database by batchKey.
assertThat(actualRows).hasSize(4);

Set<String> actualIds = actualRows.stream()
    .map(PaymentRow::eventId)
    .collect(java.util.stream.Collectors.toSet());

assertThat(actualIds).containsExactlyInAnyOrder(
    "TX-001", "TX-002", "TX-006", "TX-007");

BigDecimal actualAmount = actualRows.stream()
    .map(PaymentRow::amount)
    .reduce(BigDecimal.ZERO, BigDecimal::add);

assertThat(actualAmount.compareTo(new BigDecimal("200.00")))
    .isZero();
~~~

`PaymentRow` and `actualRows` are objects constructed by the test from target data; the example focuses on assertions. Add a duplicate check if `Set` could hide duplicates: assert `actualRows.size() == actualIds.size()` or rely on a unique constraint/database query.

## 18. Common Mistakes

**"Job COMPLETED means the data is right."** COMPLETED can include filters/skips, and writers may UPSERT, write files, or call external APIs with their own semantics. Always verify final data against the contract.

**"Input count must always equal output count."** False whenever filtering, rejecting, deduplicating, aggregating, or splitting occurs. Define grain and transformations before comparing.

**"readCount is the file line count."** Headers, blank lines, parse errors, and reader rules make the two distinct. If you need physical line counts, include an inventory step with explicit counting rules.

**"writeCount is the committed row count."** Not a general guarantee, especially with UPSERTs, writers emitting multiple rows per item, or non-transactional side effects. Query the target after commit.

**"If counts match, no data can be lost."** You can miss ID A and have an extra ID E. Key reconciliation catches errors that count alone misses.

**"If sums match, every record is right."** Two amounts can err in offsetting directions. Compare by key or critical groups.

**"Summing writeCount across all JobExecutions gives output count."** Restarts/retries, replays, chunk rollbacks, and UPSERTs make summed counts diverge from durable unique records.

**"You can reconcile live input against final output."** The source can mutate while the batch runs. Use the same snapshot, cutoff, or version to avoid comparing two different datasets.

**"Any discrepancy below a small percentage can be ignored."** For money or mandatory transactions, even one missing record can be severe. Thresholds must be defined by the business.

**"Reconciling from the output table itself is independent enough."** If expected values are derived by re-reading output without checking the source, missing data gets legitimized. Use source evidence or an accepted staging baseline.

**"Correct data in the DB means the job is done."** If output must also be published to files, message brokers, or external systems, verify each destination's state. Accurate DB staging does not guarantee downstream consumers received it.

## 19. Practical Workflow for Applying This in a Real Job

1. **Define the data contract.** Lock down grain, business key, processing period, currency, filter/skip/dedup/transform rules, and `PASS` criteria.
2. **Lock the source.** Produce a source manifest/snapshot or watermark with clear count and checksum rules.
3. **Track every processing branch.** Use `StepExecution` counters and appropriate audit/quarantine records to classify read rejects, process rejects, filters, duplicates, and accepted outputs.
4. **Write target data safely for replay.** Choose unique business keys, chunk transactions, idempotent writers, or equivalent mechanisms.
5. **Query committed output.** Reconcile counts, distinct keys, sums, and breakdowns across key groups.
6. **Detect missing/extra/mismatched keys.** For critical data, never stop at total counts or sums.
7. **Separate reconciliation from loading.** Publish output only when quality criteria pass, or explicitly publish an allowed-rejects status.
8. **Support retry/restart.** Keep `batchKey`/`sourceVersion` stable, treat execution metadata as attempt history, and re-reconcile final durable data.
9. **Persist traceable results.** Store summary counts/sums, discrepancies, execution IDs, outcome, and reconciliation timestamp without exposing sensitive data.
10. **Test discrepancy scenarios too.** Inject missing IDs, extra IDs, wrong amounts, duplicates, rollbacks, restarts, and version-swapped inputs to verify reconciliation genuinely catches issues.

## Conclusion

**Input-output total reconciliation** in Spring Batch is about proving that all source data is **accurately accounted for along its path** and that target results **match the business contract**. `readCount`, `writeCount`, skip/filter counters, and `COMPLETED` status are useful operational signals, yet they do not replace counting committed data and checking keys, sums, snapshots, or versions.

For 1:1 pipelines with filters/skips, account cleanly for **source = accepted + filtered + rejected**, then verify **actual output = accepted set** by count, value, and identity. For aggregating/splitting, deduplicating, or multi-target pipelines, adapt reconciliation to the matching grain and semantics. When reconciliation becomes a formal pre-publish gate, data quality is governed by verifiable evidence even across retries, restarts, or distributed execution.

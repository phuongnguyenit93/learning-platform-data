# Missing Record Detection in Spring Batch

## 1. What Is a Missing Record?

In a Spring Batch data processing system, a **missing record** is a record **required to appear in the output per the processing contract**, yet not found in the persisted or published output at reconciliation time. Detecting missing records is an important part of **data quality**: a job can complete all Steps and report \`COMPLETED\` while some records still never reach the destination.

Example order import job:

~~~text
Input source                  Output
-------------                -------------
O101 (valid)   -------------> O101
O102 (valid)   -------------> O102
O103 (CANCELLED)             [validly filtered]
O104 (valid)   -------------> [absent]
O105 (INVALID)               [excluded per policy]
O106 (valid)   -------------> [absent]
~~~

In this example **O104 and O106 are missing records**, assuming the contract requires every valid, actionable order to produce exactly one row in the target table.

Not seeing a record in the output is **not enough** to conclude it is missing due to a bug. Before checking, answer:

- Does the record **belong to the dataset that must be processed**?
- Was it filtered or excluded **according to policy**?
- Has the Job/Step finished and has output **committed**?
- Which table, file, topic, partition, version, or batch holds the output?
- Is there legitimate processing latency or an event awaiting downstream confirmation?

Therefore, missing record detection must clearly define the **expected set**, the **observed actual set**, and the **reconciliation point in time**.

## 2. Distinguishing Missing, Filtered, Skipped, Duplicate, and Unexpected

| Case | Meaning | Considered Missing? |
|---|---|---|
| **Missing** | Record must produce output yet is absent | **Yes** |
| **Filtered** | Processor intentionally returns \`null\` under valid rules | No, if the contract allows omission |
| **Skipped** | Framework skips record after an exception per skip policy | Depends on contract: may be a quality error or an accepted exclusion |
| **Duplicate** | One output key appears multiple times unexpectedly | A different error; can coexist with missing |
| **Unexpected/extra** | Output contains a record outside the permitted set | A different error; cannot offset a missing record |
| **Late** | Record has not arrived due to async delivery within allowed latency window | Not yet missing before the deadline expires |
| **Rejected** | Record rejected per rules with audit and clear reason | No, if the contract defines an excluded set |

**Do not equate \`filterCount\` or \`skipCount\` with missing records.** Spring Batch counters describe processing mechanics, whereas missing detection must compare actual keys/data against business requirements.

A frequently missed bug: output has the exact same total row count as the source, yet one order is missing and another order was written twice. \`COUNT(*)\` matches, yet the dataset is still incomplete.

## 3. Building the Expected Contract Before Checking

Suppose the system ingests from \`staging_order\` and writes to \`processed_order\`. Business contract:

1. Consider only records belonging to the **batchId** under inspection.
2. Only records with \`status = 'READY'\` and \`is_valid = TRUE\` must be emitted.
3. Each \`(batch_id, source_id)\` in the valid set must have **exactly one** record at the target.
4. Target records must preserve exact \`amount\` and \`currency\` under published transformation rules.
5. Source data must be a **stable snapshot** of the batch. Never mutate the expected set between job execution and verification.
6. A batch is marked **READY_FOR_CONSUMPTION** only after reconciliation succeeds.

A logical model:

- \(E\): set of keys **expected** to have output.
- \(A\): set of keys **actually** found in committed output.
- \(M = E \setminus A\): **missing** set.
- \(U = A \setminus E\): **unexpected** set.

For a 1:1 relationship, data completeness requires **\(|M| = 0\)**. If the contract also forbids extra records and duplicates, we require both \(|U| = 0\) and no key appearing more than once.

Note that \`A\` in the formula is a **set of unique keys**. To check duplicates, also inspect occurrence counts per key, because set difference cannot represent multiplicity.

### Why Scope by Batch?

Suppose two runs write into the same table:

~~~text
batchId=B20261116: O101, O102, O104, O106
batchId=B20261117: O201, O202
~~~

If you only compare table-wide row counts or join only by \`source_id\` without \`batch_id\`, records from another batch can skew results. In multi-tenant systems, the reconciliation key may need **tenantId + businessDate + batchId + sourceId + outputVersion**.

Do not use \`jobExecutionId\` alone as the output business key when a \`JobInstance\` can restart multiple times: one logical batch may be written across multiple \`JobExecution\`s yet must be reconciled as **one final result set**.

## 4. Example Input and Output Data

Suppose the source table contains:

| batch_id | source_id | status | is_valid | amount |
|---|---|---|---|---:|
| B42 | O101 | READY | TRUE | 100.00 |
| B42 | O102 | READY | TRUE | 45.50 |
| B42 | O103 | CANCELLED | TRUE | 20.00 |
| B42 | O104 | READY | TRUE | 80.00 |
| B42 | O105 | READY | FALSE | 15.00 |
| B42 | O106 | READY | TRUE | 25.00 |

The expected set is **O101, O102, O104, O106**. Actual output table after the job finishes:

| batch_id | source_id | amount |
|---|---|---:|
| B42 | O101 | 100.00 |
| B42 | O102 | 45.50 |
| B42 | O102 | 45.50 |
| B42 | O107 | 12.00 |

Both expected record count and target row count are **4**, yet:

- **Missing:** O104 and O106.
- **Unexpected:** O107.
- **Duplicate:** O102 appears twice.
- **Valid unique target records:** only O101 and O102.

The illustrative dataset intentionally permits duplicates at the target to demonstrate the scenario. In production, enforce a unique constraint on the business key and design an idempotent writer; a constraint prevents physical duplicates, yet **does not by itself guarantee that all other records arrived**.

## 5. Designing Schemas to Support Missing Record Detection

PostgreSQL DDL example:

~~~sql
CREATE TABLE staging_order (
    batch_id   VARCHAR(64) NOT NULL,
    source_id  VARCHAR(64) NOT NULL,
    status     VARCHAR(20) NOT NULL,
    is_valid   BOOLEAN NOT NULL,
    amount     NUMERIC(18, 2) NOT NULL,
    currency   VARCHAR(3) NOT NULL,
    PRIMARY KEY (batch_id, source_id)
);

CREATE TABLE processed_order (
    batch_id   VARCHAR(64) NOT NULL,
    source_id  VARCHAR(64) NOT NULL,
    amount     NUMERIC(18, 2) NOT NULL,
    currency   VARCHAR(3) NOT NULL,
    PRIMARY KEY (batch_id, source_id)
);

CREATE INDEX idx_staging_order_expected
    ON staging_order (batch_id, status, is_valid, source_id);
~~~

In a test environment simulating duplicates, you can use a temporary table without a primary key or a separate staging output. In real systems, a unique constraint prevents duplicates at write time.

If source keys are not yet unique, decide whether duplicate source records are **dirty data that must fail** or should be merged per business rules; never let a \`DISTINCT\` silently mask bugs.

Indexes should match actual reconciliation queries. For large batches, column ordering in indexes, date partitioning, and index size must be evaluated against concrete workloads.

## 6. SQL to Detect Missing Records via Anti-Join

### 6.1. Determining the Expected Count

~~~sql
SELECT COUNT(*) AS expected_count
FROM staging_order
WHERE batch_id = :batchId
  AND status = 'READY'
  AND is_valid = TRUE;
~~~

For batch B42 in the example, `expected_count` is **4**.

Preliminary check against target total:

~~~sql
SELECT COUNT(*) AS actual_count
FROM processed_order
WHERE batch_id = :batchId;
~~~

If the two numbers differ, there is definitely a condition to investigate under a 1:1 contract. Yet **equality does not prove completeness**, because missing, extra, and duplicate rows can cancel out.

### 6.2. \`NOT EXISTS\` Query — The Standard Approach

~~~sql
SELECT s.source_id, s.amount, s.currency
FROM staging_order s
WHERE s.batch_id = :batchId
  AND s.status = 'READY'
  AND s.is_valid = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM processed_order t
      WHERE t.batch_id = s.batch_id
        AND t.source_id = s.source_id
  )
ORDER BY s.source_id;
~~~

Meaning: each valid source record must find at least one record with the same key in the target table. If none exists, it is missing. The example yields **O104, O106**.

The advantage of \`NOT EXISTS\` is that it directly expresses absence checks and avoids \`NULL\` pitfalls of \`NOT IN\`. For nullable business keys, normalize or establish a null policy before reconciling; essential keys are best declared \`NOT NULL\`.

### 6.3. \`LEFT JOIN ... IS NULL\`

Equivalent query when the right-side key column is non-nullable:

~~~sql
SELECT s.source_id
FROM staging_order s
LEFT JOIN processed_order t
  ON t.batch_id = s.batch_id
 AND t.source_id = s.source_id
WHERE s.batch_id = :batchId
  AND s.status = 'READY'
  AND s.is_valid = TRUE
  AND t.source_id IS NULL;
~~~

Target-table filter predicates must go in the appropriate \`ON\` clause if \`output_version\`, \`tenant_id\`, or publish status is added. Putting target predicates in \`WHERE\` by mistake can accidentally turn a left join into an inner join and hide the very missing records you want to detect.

### 6.4. Counting Missing Records

~~~sql
SELECT COUNT(*) AS missing_count
FROM staging_order s
WHERE s.batch_id = :batchId
  AND s.status = 'READY'
  AND s.is_valid = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM processed_order t
      WHERE t.batch_id = s.batch_id
        AND t.source_id = s.source_id
  );
~~~

To retain investigation evidence, record the **full count** along with a sample of missing keys. Never cap a \`COUNT\` query with \`LIMIT 100\` and report that only 100 records are missing. For very large datasets, run a dedicated count query and a separate bounded sample query.

## 7. Checking Unexpected, Duplicate, and Mismatched Values Together

Missing detection is usually part of full result-set reconciliation. When input expects four records and output has four rows yet two are missing, a simple count cannot reveal the root cause.

### 7.1. Unexpected Output

~~~sql
SELECT t.source_id
FROM processed_order t
WHERE t.batch_id = :batchId
  AND NOT EXISTS (
      SELECT 1
      FROM staging_order s
      WHERE s.batch_id = t.batch_id
        AND s.source_id = t.source_id
        AND s.status = 'READY'
        AND s.is_valid = TRUE
  );
~~~

The result must be empty. If not, it may indicate output from invalid input, leftover rows from a prior run, or a batch-partitioning bug.

### 7.2. Duplicate Output

~~~sql
SELECT batch_id, source_id, COUNT(*) AS occurrences
FROM processed_order
WHERE batch_id = :batchId
GROUP BY batch_id, source_id
HAVING COUNT(*) > 1;
~~~

The result must be empty under a 1:1 contract. If the table has primary key \`(batch_id, source_id)\`, duplicates cannot exist across those two columns; tests must still verify writer error handling when replaying already-written data.

### 7.3. Field Value Mismatches

~~~sql
-- PostgreSQL example: assuming amount and currency are copied unchanged.
SELECT s.source_id,
       s.amount   AS expected_amount,
       t.amount   AS actual_amount,
       s.currency AS expected_currency,
       t.currency AS actual_currency
FROM staging_order s
JOIN processed_order t
  ON t.batch_id = s.batch_id
 AND t.source_id = s.source_id
WHERE s.batch_id = :batchId
  AND s.status = 'READY'
  AND s.is_valid = TRUE
  AND (
      s.amount IS DISTINCT FROM t.amount
      OR s.currency IS DISTINCT FROM t.currency
  );
~~~

\`IS DISTINCT FROM\` provides \`NULL\`-aware comparisons in PostgreSQL; other RDBMS engines may require equivalent syntax. If the processor applies rounding, currency conversion, or status normalization, compare against **post-transform expected values** rather than mechanically against raw input.

For monetary data, also reconcile \`SUM(amount)\` **per currency**. Equal totals can still hide two offsetting errors; key-level verification remains necessary when the contract demands per-record accuracy.

## 8. Avoiding False Positives: Snapshots, Watermarks, and Verification Timing

A common bug occurs when the job reads one input version but reconciles against a mutated input version:

~~~text
10:00  Job starts; reader sees 1,000 records
10:03  Upstream inserts 25 new records into source table
10:05  Job finishes, writing all 1,000 read records
10:06  Verification query sees 1,025 source records
       -> Reports 25 missing records even though they were not part of the run
~~~

To avoid **false positives**, freeze the input set using one of these strategies:

- **Staging snapshot:** copy batch records into a dedicated table tagged with \`batchId\` and close the snapshot before the Job runs.
- **Watermark:** store a cutoff timestamp/sequence/offset that both reader and verifier use as the boundary.
- **Source version:** use \`sourceVersion\`, file checksum, or a fixed manifest.
- **Snapshot transaction:** use suitable transaction isolation for short runs, though never assume holding a single read transaction open across a long-running job.

If the reader uses \`JdbcPagingItemReader\` while the source mutates during processing, use a stable sort key and change-handling rules; unstable offsets/paging or ordering can cause missing or duplicate records.

**The source cutoff point must be recorded as part of the batch contract**, not merely grabbed as an arbitrary timestamp at verification time.

### Final Data Should Only Be Verified When Ready

If a writer writes to an open file, publishes events to a broker, or delivers data with latency, reconciling immediately when an internal Step finishes can observe temporarily missing output. Specify clearly:

1. The producer has finished and committed/closed the artifact.
2. The receiver has acknowledged at the required level, if the contract includes downstream processing.
3. The eventual-consistency wait window has elapsed or a `READY` marker exists.
4. Output version and reconciliation scope are immutably defined.

Do not wait indefinitely to "legitimize" an unemitted record; enforce a clear deadline and **PENDING/FAILED** states.

## 9. Relating to Spring Batch Read, Process, Write, Skip, and Filter

Suppose a Step reads 1,000 items, filters 100, allows 5 skips, and the writer expects to emit one record per remaining item. The expected output count **may be 895** if all 100 filters and 5 skips are accepted by the contract.

However, do not apply this formula blindly:

\[
\text{expectedWriteCount} =
\text{readCount} - \text{filterCount} - \text{skipCount}
\]

This formula does not always hold because \`readSkipCount\` can reflect items excluded from \`readCount\`, the processor may emit 1:n outputs, the writer may upsert/aggregate, transactions can roll back, or components may hold state.

In Spring Batch:

- \`readCount\`: items successfully read per Step accounting.
- \`readSkipCount\`: read errors skipped per configuration.
- \`processSkipCount\`: processor errors skipped.
- \`writeSkipCount\`: write errors skipped under appropriate mechanics.
- \`filterCount\`: items where processor returned \`null\`, never reaching the writer.
- \`writeCount\`: items recorded by the framework at the writer, not necessarily unique committed rows in external systems.
- \`rollbackCount\`: rollbacks recorded by the Step.

Counters are **signals for investigation**. To pinpoint exact missing records, you still need the **expected key list** and **actual key list**.

### When Does Skipping Cause Missing Records?

If business rules require every valid order to reach the destination, an item skipped due to an API outage or parse failure creates **missing output under the business contract**. The Job may still be \`COMPLETED\` if \`skipLimit\` allows it, yet verification must fail or record an explicitly policy-approved rejection.

If the contract permits dropping invalid records, maintain a **rejection register** with \`batchId\`, \`sourceId\`, reason code, and acceptance decision. Then the expected set is defined as the source snapshot **minus policy-approved rejections**. Never use "every record absent from output was validly skipped" as circular proof.

## 10. Turning the Check into an Output Verification Step

A robust Spring Batch pattern is running a **verifyMissingRecordsStep** after the main processing Step. If data is missing, the tasklet throws an exception so the **verification Step becomes FAILED**, preventing the job from ending normally as \`COMPLETED\` in the default sequential flow.

~~~text
importOrdersStep
       |
       v
verifyMissingRecordsStep
       |
       +------ Missing/unexpected/duplicate found ----> FAILED
       |
       +------ Complete and accurate -------------------> publishOutputStep
                                                              |
                                                              v
                                                          COMPLETED
~~~

Putting verification in a formal Step makes job status meaningful. Checking only after the job is already \`COMPLETED\` inside \`JobExecutionListener.afterJob\` is unreliable, because throwing from a listener is not a dependable way to flip an already-finished job to FAILED.

### Database Verification Step Example

Suppose \`staging_order\` and \`processed_order\` share a datasource queryable via \`JdbcTemplate\`. Spring Batch 5+ example:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step verifyMissingRecordsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("verifyMissingRecordsStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                Object rawBatchId = chunkContext.getStepContext()
                        .getJobParameters().get("batchId");
                if (!(rawBatchId instanceof String batchId)
                        || batchId.isBlank()) {
                    throw new IllegalArgumentException(
                            "Missing job parameter batchId");
                }

                Long expected = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM staging_order
                        WHERE batch_id = ?
                          AND status = 'READY'
                          AND is_valid = TRUE
                        """,
                        Long.class, batchId);

                Long actual = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM processed_order
                        WHERE batch_id = ?
                        """,
                        Long.class, batchId);

                Long missing = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM staging_order s
                        WHERE s.batch_id = ?
                          AND s.status = 'READY'
                          AND s.is_valid = TRUE
                          AND NOT EXISTS (
                              SELECT 1
                              FROM processed_order t
                              WHERE t.batch_id = s.batch_id
                                AND t.source_id = s.source_id
                          )
                        """,
                        Long.class, batchId);

                Long unexpected = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM processed_order t
                        WHERE t.batch_id = ?
                          AND NOT EXISTS (
                              SELECT 1
                              FROM staging_order s
                              WHERE s.batch_id = t.batch_id
                                AND s.source_id = t.source_id
                                AND s.status = 'READY'
                                AND s.is_valid = TRUE
                          )
                        """,
                        Long.class, batchId);

                Long duplicates = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM (
                            SELECT source_id
                            FROM processed_order
                            WHERE batch_id = ?
                            GROUP BY source_id
                            HAVING COUNT(*) > 1
                        ) d
                        """,
                        Long.class, batchId);

                if (expected == null || actual == null
                        || missing == null || unexpected == null
                        || duplicates == null
                        || !expected.equals(actual)
                        || missing != 0L
                        || unexpected != 0L
                        || duplicates != 0L) {
                    throw new IllegalStateException(
                            "Output reconciliation failed for batchId="
                                    + batchId
                                    + ", expected=" + expected
                                    + ", actual=" + actual
                                    + ", missing=" + missing
                                    + ", unexpected=" + unexpected
                                    + ", duplicateKeys=" + duplicates);
                }

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
~~~

In a real application, this \`@Bean\` method lives inside a \`@Configuration\` class and requires the appropriate Batch infrastructure beans. The tasklet above checks a 1:1 relationship and assumes the **input snapshot is locked**. It does not yet verify \`amount\` or \`currency\` fields; if the contract requires it, add data comparisons as in section 7.

**A verification failure does not automatically roll back committed chunks from the preceding Step.** Therefore, keep output in a staging/non-READY state so consumers do not read incomplete data while waiting for fixes and re-reconciliation.

### Wiring Verification into the Flow

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        @Qualifier("importOrdersStep") Step importOrdersStep,
        @Qualifier("verifyMissingRecordsStep") Step verifyMissingRecordsStep,
        @Qualifier("publishOutputStep") Step publishOutputStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .next(verifyMissingRecordsStep)
            .next(publishOutputStep)
            .build();
}
~~~

\`importOrdersStep\` and \`publishOutputStep\` are assumed to be defined in other configurations. Under normal sequential flow, the next Step runs only when the preceding Step completes with matching transition conditions.

If checking from an external system after the job ends, use `JobExplorer` to read status and a separate reconciliation service. Maintain business batch statuses such as **VERIFICATION_PENDING**, **VERIFIED**, or **REJECTED**, because \`BatchStatus.COMPLETED\` alone does not prove output met external Batch contracts.

## 11. Detecting Missing Records in CSV, JSON, or XML Files

For file outputs, matching must read **logical records** rather than merely counting physical lines:

~~~csv
batchId,sourceId,amount
B42,O101,100.00
B42,O102,45.50
~~~

Typical checks:

1. The output file belongs to the exact **batchId/version**; never read an old file by mistake.
2. The writer has closed the file and output is published per contract.
3. The parser reads the full CSV/JSON/XML with valid schema and encoding.
4. Extract the actual **sourceId** set from parsed records.
5. Compare expected keys with actual keys to locate missing/unexpected records; check duplicate keys.
6. Reconcile critical values and checksums when required.
7. Emit the manifest/READY marker only after verification succeeds.

**Never count newline characters to measure CSV record count**: a valid quoted field can contain embedded newlines; JSON can hold multiple records in an array on one line.

For large files, if all keys cannot fit in RAM, you can:

- Extract expected/actual keys into two sorted files and perform a sorted **merge-diff**.
- Load keys into a temporary staging table to run SQL anti-joins.
- Hash-partition by key and reconcile each partition independently.
- Use checksums/totals for fast detection, while still running key reconciliation when the contract demands exact missing detection.

**Checksums alone cannot tell which record is missing.** Bloom filters can save RAM for preliminary membership checks, yet have false positives and therefore are not absolute proof that no record is missing.

### Safe File Publishing Workflow

~~~text
orders-B42.csv.part
       |
       v
Writer closes file
       |
       v
Parse + count + exact-key reconciliation
       |
       +------ FAIL --> Quarantine / hold temporary version
       |
       v
Publish orders-B42-v1.csv + READY manifest
       |
       v
Consumers begin reading
~~~

Atomic rename can only be assumed under suitable filesystem semantics; with object storage, publish an immutable object/version and then create the marker/manifest.

## 12. Missing Records in Kafka, APIs, and Asynchronous Systems

Not every output appears immediately after a successful writer call:

- A Kafka producer may acknowledge writing to the broker before the consumer finishes processing.
- An HTTP service may return \`202 Accepted\` and process asynchronously afterward.
- A data warehouse or search index may have ingest/refresh lag.
- A Step may emit an outbox event while an independent publisher has not yet forwarded it.

In these cases, define **the level that counts as output present**:

| Level | Signal | Sufficient to Confirm Record Reached Final Target? |
|---|---|---|
| Writer calls API without error | Normal method return | Not necessarily; depends on API semantics |
| Broker confirms publish | Message accepted by broker | Does not prove consumer processed it |
| Downstream ACK by business key | Consumer confirms record | Can be sufficient if ACKs are durable per contract |
| Record appears in target system | Queryable by key/version | Usable if state is committed and reads are consistent |
| READY manifest after reconciliation | Batch version published | Suitable if manifest is created only after validation |

For HTTP services, issue requests with a stable **idempotency key**, store the receipt ID, and poll status by receipt before declaring a record missing. Do not blindly resend requests instead of checking status, as that can cause duplicate side effects.

For Kafka, you may need an acknowledgement table keyed by \`batchId + sourceId\` at the consumer or a durable audit sink. **Committed Kafka offsets** do not always equate to records persisted in a separate business database unless the architecture/transaction semantics guarantee it.

### Allowed Latency Window

If the contract grants downstream up to five minutes after publishing:

~~~text
10:00  Producer emits event
10:02  Consumer has not written output yet -> PENDING
10:04  Consumer writes successfully ---------> PRESENT
10:05  Deadline; if still absent, conclude MISSING
~~~

Once the deadline expires, verification must report genuine missing records and trigger investigation or recovery; never extend wait windows indefinitely to mask failures.

## 13. Partitioning, Parallel Steps, and Restarts

### Missing Records from Parallel Processing

A job may partition input by range:

~~~text
Partition 0: source_id 0000..2499
Partition 1: source_id 2500..4999
Partition 2: source_id 5000..7499
Partition 3: source_id 7500..9999
~~~

If one partition fails, drops its result before reporting to the manager, or is mistakenly marked complete, output can miss an entire slice of records. Therefore, in addition to whole-batch exact-set reconciliation, record:

- Partition ID and input boundaries.
- Expected record count/keys per partition.
- `StepExecution` status and read/write/skip/rollback counters per partition.
- Commit timestamp and partition completion marker.
- Missing count per partition after verification.

Do not sum partition counts and call it complete if partition boundaries overlap or skip keys. One partition writing 100 duplicate records overlapping another partition can make total counts look right even when records in a third partition are missing.

### Missing Records After Restart

A `JobInstance` can have multiple `JobExecution`s:

~~~text
JobInstance B42
  |
  +-- JobExecution #701
  |      Chunks 1..5 committed
  |      Chunk 6 failed
  |
  +-- JobExecution #705 (restart)
         Resume from checkpoint
         Write remaining records
~~~

When reconciling **final batch output**, count all valid committed records across executions belonging to the same batch, not just \`writeCount\` of the latest execution. Counting only rows written during the restart easily produces false missing alerts.

Conversely, if checkpoints advance ahead of output because metadata and business databases use separate transactions, restarts can skip unwritten records. If output advances ahead of checkpoints, restarts can duplicate writes. Missing record detection catches gaps; combine it with duplicate detection and idempotent writers to handle the other side.

### Never Mutate Input During Position-Based Restarts

With `FlatFileItemReader` or paging readers using positional checkpoints, inserting, deleting, or re-sorting input between two executions can skip records or process them twice. Keep snapshots, watermarks, or input files/versions immutable for the `JobInstance`, and reconcile against that exact version.

## 14. When Mapping Is Not 1:1

Not every source item maps to one output row:

| Processing Pattern | How Expected Is Defined |
|---|---|
| **1:1** | Each valid `source_id` has exactly one output |
| **1:n** | Each `source_id` must have all expected child keys, e.g., \`(orderId, lineNo)\` |
| **n:1** | Input groups aggregate into one record per group key, e.g., \`(businessDate, currency)\` |
| **Valid filter** | Expected includes only inputs matching filter rules |
| **Soft delete/update** | May require the record to hold the right final state rather than inserting a new row |
| **Event stream** | May expect event type and event version, not merely business key |

### 1:n Example

An order O101 has three line items; output must have keys:

~~~text
(O101, line1)
(O101, line2)
(O101, line3)
~~~

If output contains only \`line1\` and \`line3\`, simply checking "O101 exists" will **miss the missing line2**. The expected key must be \`(orderId, lineNo)\`, not just \`orderId\`.

### n:1 Example

A job aggregating transactions by date and currency may emit one record per \`(date, currency)\`. Missing detection checks **expected group keys**, total record count, contributing transaction counts, total amounts, and transformation formulas. You cannot compare individual transaction IDs directly against an aggregated summary table.

Before writing queries, specify **cardinality** and **result keys**. Otherwise, the system may falsely report thousands of missing records simply by misunderstanding the data model.

## 15. Optimizing Reconciliation for Large Batches

With millions of records, slow reconciliation or long-held DB locks can hurt throughput. Design strategies:

**1. Scope by batch/version.** Always filter with \`batch_id = ?\`, date, or partition predicates. Avoid scanning full history on every run.

**2. Use stable keys and indexes.** An index on \`(batch_id, source_id)\` is critical for anti-joins. On the source table, indexes can include columns used to filter the expected set.

**3. Partition verification.** Only when partitions have non-overlapping boundaries covering the full expected set should you aggregate results into a global batch verdict.

**4. Tiered checks.** Counts and checksums enable fast detection, while key reconciliation remains necessary when strict completeness is required.

**5. Avoid pulling all IDs into the JVM.** Use SQL \`NOT EXISTS\`, staging tables, set-based operations, or streaming sort/merge instead of loading millions of keys into \`List<String>\`.

**6. Bound audit writes.** Store the full \`missingCount\` along with up to N sample keys; export complete lists to a separate artifact if bulk remediation is needed.

**7. Ensure read consistency.** Running multiple reconciliation queries while another writer mutates data can observe inconsistent states. Lock the output version and use appropriate transaction/snapshot isolation.

**8. Plan for timeouts.** Large verification queries can time out; never treat a timeout as "zero missing." The result must stay unverified or `FAILED`.

### Tiered Verification Flow

~~~text
Stage 1: Is batch/output version finalized?
          |
          v
Stage 2: Count + high-level business totals
          |
          v
Stage 3: Exact missing/extra/duplicate keys
          |
          v
Stage 4: Value/schema checks
          |
          v
Stage 5: READY + audit
~~~

For small datasets, run all tiers every time. For very large datasets, run cheap checks per partition and deep checks at the end, without trading away guarantees required by the business contract.

## 16. Auditing, Metrics, and Alerts for Missing Records

A verification result must link to a specific job, input, and output:

~~~text
event=output.reconciliation.completed
jobName=importOrdersJob
jobInstanceId=301
jobExecutionId=910
batchId=B42
sourceVersion=2026-11-16-v1
outputVersion=v3
expectedCount=400000
actualCount=399998
missingCount=2
unexpectedCount=0
duplicateKeyCount=0
valueMismatchCount=0
verificationStatus=FAILED
verifiedAt=2026-11-16T09:30:00+07:00
~~~

This is illustrative data. When records are missing, log only log-safe keys, reason codes, and relevant partitions. Never write personal data or sensitive payloads into logs and metrics.

Suggested metrics:

| Metric | Meaning |
|---|---|
| \`batch_expected_records\` | Number of records required to have output |
| \`batch_actual_records\` | Number of output records observed |
| \`batch_missing_records\` | Number of expected records absent |
| \`batch_unexpected_records\` | Number of outputs outside expected set |
| \`batch_duplicate_keys\` | Number of duplicated keys |
| \`batch_reconciliation_failures_total\` | Count of failed reconciliations |
| \`batch_last_verified_timestamp\` | Timestamp of most recent completed verification |
| \`batch_verification_duration_seconds\` | Duration of verification run |

These names are application suggestions, **not default Spring Batch metrics**. To avoid high cardinality in Prometheus, never use \`sourceId\`, \`jobExecutionId\`, or \`batchId\` as labels on every time series. Those belong in logs, traces, or an audit database.

### Alerting Policy

For financial batches or mandatory completeness datasets, **missingCount > 0** past the deadline must usually block publishing and trigger alerts. For best-effort pipelines, a defined tolerance may exist, yet you must specify which record sets and impact levels apply; even 0.01% can be severe if it hits a critical customer or transaction.

Common alerts:

- Expected set is locked, yet no output exists past the deadline.
- Verification fails due to missing/duplicate/unexpected records.
- Verification failed to run or encountered data access errors.
- Sudden spike in missing records by source/partition/job.
- Job \`COMPLETED\`, yet no VERIFIED/READY marker appeared within the allowed window.

## 17. Testing Missing Record Detection

To test this mechanism, use a **test database with a real schema** and fixtures with concrete keys. A test must prove the check catches missing records **even when total row counts match**.

### Scenario Matrix

| Fixture | Expected | Actual | Outcome |
|---|---|---|---|
| Complete, all keys right | O1,O2,O3 | O1,O2,O3 | PASS |
| Missing one key | O1,O2,O3 | O1,O2 | Missing O3; FAIL |
| One missing and one extra | O1,O2,O3 | O1,O2,O4 | Missing O3, unexpected O4; FAIL despite equal count |
| One missing and one duplicate | O1,O2,O3 | O1,O2,O2 | Missing O3, duplicate O2; FAIL despite equal count |
| Record validly filtered | O1,O2 | O1,O2 (CANCELLED record not expected) | PASS |
| Unapproved skip | O1,O2,O3 | O1,O2 | Missing O3; FAIL |
| Approved audited skip | O1,O2 after policy drops O3 | O1,O2 | PASS if contract permits |
| Record in another batch | B42: O1,O2 | B42: O1; B43: O2 | Missing O2 in B42 |
| Restart partially wrote | Expected O1..O6 | Combined outputs across two executions equal O1..O6 | PASS |
| Value mismatch | Keys complete, wrong amount | Keys complete | FAIL on value check |
| Output not yet READY | Expected complete, downstream still working | Not yet fully observed | PENDING until deadline; unpublished |
| Cannot query target | Expected complete | DB unavailable | Verification FAILED/UNKNOWN; never auto-PASS |

### Verification Step Integration Test Example

The example below uses Spring Batch Test and Spring Boot, assuming the test context registers **verifyMissingRecordsStep** and the database has the two tables from section 5. The test launches the **verification Step** in isolation to test the reconciliation algorithm without running the entire import job.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class MissingRecordVerificationIT {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @BeforeEach
    void resetFixtures() {
        // Use an isolated test database; do not run on a shared DB.
        jdbcTemplate.update("DELETE FROM processed_order");
        jdbcTemplate.update("DELETE FROM staging_order");
    }

    @Test
    void failsWhenAnExpectedRecordIsMissing() throws Exception {
        insertExpected("B-TEST-1", "O1", "10.00");
        insertExpected("B-TEST-1", "O2", "20.00");
        insertExpected("B-TEST-1", "O3", "30.00");

        insertActual("B-TEST-1", "O1", "10.00");
        insertActual("B-TEST-1", "O2", "20.00");

        JobExecution result = launchVerification("B-TEST-1");
        assertEquals(BatchStatus.FAILED, result.getStatus());

        Long missing = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM staging_order s
                WHERE s.batch_id = ? AND s.status = 'READY'
                  AND s.is_valid = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM processed_order t
                      WHERE t.batch_id = s.batch_id
                        AND t.source_id = s.source_id
                  )
                """,
                Long.class, "B-TEST-1");
        assertEquals(1L, missing);
    }

    @Test
    void completesWhenExpectedAndActualKeysMatch() throws Exception {
        insertExpected("B-TEST-2", "O1", "10.00");
        insertExpected("B-TEST-2", "O2", "20.00");
        insertActual("B-TEST-2", "O1", "10.00");
        insertActual("B-TEST-2", "O2", "20.00");

        JobExecution result = launchVerification("B-TEST-2");
        assertEquals(BatchStatus.COMPLETED, result.getStatus());
    }

    private JobExecution launchVerification(String batchId)
            throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("batchId", batchId)
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();
        return jobLauncherTestUtils.launchStep(
                "verifyMissingRecordsStep", params);
    }

    private void insertExpected(
            String batchId, String orderId, String amount) {
        jdbcTemplate.update(
                """
                INSERT INTO staging_order
                    (batch_id, source_id, status, is_valid, amount, currency)
                VALUES (?, ?, 'READY', TRUE, ?, 'USD')
                """,
                batchId, orderId, new java.math.BigDecimal(amount));
    }

    private void insertActual(
            String batchId, String orderId, String amount) {
        jdbcTemplate.update(
                """
                INSERT INTO processed_order
                    (batch_id, source_id, amount, currency)
                VALUES (?, ?, ?, 'USD')
                """,
                batchId, orderId, new java.math.BigDecimal(amount));
    }
}
~~~

With \`@SpringBatchTest\`, provide test infrastructure and matching Job/Step beans, and configure \`JobLauncherTestUtils\` if the context holds multiple Jobs. \`spring.batch.job.enabled=false\` prevents Spring Boot from auto-running jobs on context startup. The test uses a **dedicated test database**, because table-wide \`DELETE\` is unsafe under parallel tests or shared environments.

After testing the Step in isolation, add an integration test running the **entire Job flow**: deliberately make the import Step drop O3, verify the verification Step becomes FAILED, and confirm the publish Step does not run. This tests the contract connecting processing, reconciliation, and output publishing.

## 18. Handling Workflow When Missing Records Are Detected

When verification detects missing records, do not merely log a warning and let consumers read the output:

1. **Isolate batch/version:** capture `jobExecutionId`, `jobInstanceId`, `batchId`, source snapshot, and output location.
2. **Block publishing:** mark output as INVALID/QUARANTINED or withhold the READY marker.
3. **Collect evidence:** full missing count, sample keys, `StepExecution`, and involved partitions.
4. **Identify root cause:** reader dropped record, wrong filter/skip, writer failure, commit/rollback, checkpoint skew, lost partition, or downstream lag.
5. **Choose recovery method:** restart the right `JobInstance`, replay missing keys via an idempotent writer, or create an explicit correction batch.
6. **Prevent duplicates:** check business keys, committed output, and external API side effects before replaying.
7. **Re-run verification:** verify missing/unexpected/duplicates and critical values after remediation.
8. **Publish verified version:** transition to READY only when all mandatory checks pass and store the audit.

### Example: Missing Records Due to Checkpoint and Output Skew

If `JobRepository` and business data use different transactions, a chunk can update its checkpoint while the writer fails to commit, or vice versa:

~~~text
Expected: O001..O200
Committed output: O001..O100
Recorded checkpoint: read up to O150

Restart from checkpoint:
  Continues O151..O200
  O101..O150 remain missing
~~~

Missing detection against the expected set catches O101..O150; trusting a restart \`COMPLETED\` status is insufficient. Once detected, reconcile by key and ensure no other job is processing the same batch concurrently before replaying.

### Example: Missing Records Due to Misclassified Filtered Records

If a processor returns \`null\` when an external service times out (instead of throwing to retry/fail), the item is **mistakenly filtered** and the job still succeeds. If the contract only permits filtering \`CANCELLED\` orders, valid records go missing from output. Reconciling expected keys against output catches this bug even when \`filterCount\` looks plausible.

## 19. Common Mistakes

**Comparing only \`COUNT(*)\`.** One missing record can be masked by an extra or duplicate record. Use anti-joins and check unexpected/duplicate records.

**Using the entire source as expected while ignoring filter rules.** Generates false positives for records that should not appear. Lock expected criteria per the contract.

**Treating every skip as valid.** A record skipped due to a system error can be a critical missing record. Exclude from expected only with explicit policy and auditing.

**Querying live input instead of the run's snapshot.** Records inserted after the job started are falsely flagged missing. Use immutable watermarks/versions.

**Confusing `batchId` and `jobExecutionId`.** A batch may restart multiple times; final output usually must be reconciled across the whole batch, not just the last execution.

**Checking output before the writer commits/closes files.** Causes transient shortages or reading half-written files. Define output readiness states.

**Using \`NOT IN\` on nullable columns without SQL semantics awareness.** \`NULL\` can make predicates evaluate to UNKNOWN. Use \`NOT EXISTS\` or normalize keys.

**Joining without all composite-key columns.** Records from another tenant or batch can hide real missing records. Join on every identifying dimension.

**Defining expected from what the writer wrote.** If the writer drops items, using the same flawed source for expected and actual self-validates the bug. Expected must derive from an independent locked source.

**Treating matching checksums as proof for all keys.** Checksums may not identify which record is missing or may collide. Use exact-key reconciliation when completeness is required.

**Failing to verify consumer state in async systems.** Broker receipt does not prove the target business system persisted the record. Define ACKs/receipts and clear deadlines.

**Not blocking publish when verification is FAILED.** A job may leave partially committed output; consumers must not treat that as final data.

**Using \`writeCount\` instead of querying actual output.** Writers may update multiple rows, trigger non-transactional side effects, or accumulate output across restarts.

**Ignoring 1:n or n:1 mappings.** Comparing one source key to one target key mismatches the model and misses child records or aggregate groups.

**Reporting only missing count without keys and scope.** When fixing issues, engineers need to know which batch/version/partition and which records are missing.

## 20. Principles for Implementing Missing Record Detection

Reliable missing record detection in Spring Batch requires:

1. **An explicit expected set** derived from a locked source snapshot and business rules.
2. **Exact reconciliation keys**, including batch/tenant/version and business keys matching cardinality.
3. **A durable actual set**, inspecting only committed output or receiver-confirmed records.
4. **Exact-key checks**, combining missing, unexpected, duplicate, and value checks when needed.
5. **A stateful verification Step or audit workflow**, so data quality failures block output publishing.
6. **Restart/idempotency design**, enabling recovery of missing records without creating duplicates.
7. **Monitoring and runbooks**, recording counts, sample keys, error sources, and recovery SLAs.

The purpose of **missing record detection** is ensuring that records obligated to appear actually arrive in the final result, regardless of how many items the job read or what status it reported. When the expected set is frozen, output is reconciled by key, and publishing depends on verification, batch systems can catch silent data loss and recover before incomplete data propagates downstream.

# Post-Job Reconciliation in Spring Batch

## 1. What Is Reconciliation?

In **Spring Batch Core Processing**, a Job can end with **BatchStatus.COMPLETED** while the data in the target system still fails to meet business requirements. For example: the Job read an order file and the writer threw no exceptions, yet some orders were dropped, some amounts were written inaccurately, or data from a previous period appeared in the current period.

**Reconciliation** is the process of comparing **actual post-processing data** against a trusted expected source to verify completeness, accuracy, and consistency. It is a core activity of **Data quality**, because technical execution status does not replace business result verification.

A good reconciliation report must answer:

- Was all source data for the period/batch received?
- How many valid items should appear in the target?
- Are any rows missing, extra, or duplicating a business key?
- Are total counts, total amounts, and critical fields accurate?
- Are filtered, rejected, or skipped items properly accounted for?
- Is the outcome **PASS**, **MISMATCH**, or **PENDING/INCONCLUSIVE**?
- When a discrepancy is detected, does the system block data publishing, preserve evidence, and support reprocessing?

Example order ingestion flow:

~~~text
Source file / source database
               |
               v
       Staging + validation
               |
               v
      Spring Batch import
               |
               v
        Target database
               |
               v
       Reconciliation
        /     |      \
      PASS  MISMATCH  INCONCLUSIVE
       |       |          |
    Publish  Alert     Wait/retry
             + audit
~~~

**PASS** is valid only when all defined rules are satisfied. **MISMATCH** is a confirmed discrepancy. **INCONCLUSIVE** means data is insufficient or the source is not yet stable enough to decide; never treat this as PASS.

## 2. Levels of Reconciliation

Not every case requires comparing every column of millions of records. Progressive verification layers can be applied:

| Level | Content | Example |
| --- | --- | --- |
| Source intake | File row count, checksum, manifest, batch ID | All 10,000 rows received |
| Data structure | Format, required fields, bad data | 3 rows with invalid dates |
| Processing flow | Read, filter, skip, write | `readCount`, `filterCount`, `skipCount`, `writeCount` |
| Business count | Expected record count vs. actual count | 9,990 / 9,990 |
| Value totals | Total amount, total quantity, total balance | `SUM(amount)` matches |
| Business key | Missing, extra, duplicate keys | O-103 missing, O-999 extra |
| Attributes | Wrong amount, currency, status, customer ID | Amount off by 10.00 |
| Downstream | Receipt/acknowledgement in the receiving system | All messages confirmed consumed |

**Equal counts do not prove data is accurate.** If the target is missing O-103 yet has an extra O-999, counts still match. Amount totals can also match by coincidence when two errors offset each other. Therefore, for critical data, check **business keys and detailed values** alongside aggregates.

## 3. Establish an Independent Expected Source

If both expected and actual values are computed from the target table itself, results will always match and fail to catch missing data. The expected source should come from:

- An immutable input file and manifest confirmed by the provider.
- A staging table holding a finalized source snapshot.
- A pre-determined input dataset for the business period.
- Control figures computed independently from the source system.
- Versioned and independently tested business rules.

Each reconciliation must have a specific **scope**:

| Field | Example Value | Reason |
| --- | --- | --- |
| batchId | batch-20261115-001 | Distinguishes each data batch |
| businessDate | 2026-11-15 | Distinguishes the business period |
| sourceVersion | snapshot-v3 | Identifies which source version is compared |
| ruleVersion | order-import-v2 | Ties acceptance/filtering conditions |
| currency | VND | Avoids summing different currency units |
| jobExecutionId | 8542 | Traces the Job run |
| reconciliationRunId | recon-001 | Distinguishes re-check runs |

The source must remain **stable** during reconciliation. If a thread is inserting into staging while the service queries expected counts, comparisons can fail due to differing read timestamps. Use a **SOURCE_FINALIZED** state, an immutable snapshot, proper transaction isolation, or an explicit watermark.

For late-arriving data, define deadlines and cutoff times. If the source keeps updating after the Batch finishes, reconciliation must check against the **exact snapshot the Job actually used**, rather than drifting to a newer dataset.

## 4. Example Fixture: 10 Source Rows, 8 Written Rows

Suppose the input file has 10 data rows, excluding the header:

- **8 READY rows**, valid, distinct `orderId` values, total amount **1,250.00**.
- **1 CANCELLED row**, filtered by the processor returning **null**.
- **1 INVALID row**, throwing an exception configured as skippable in the processor.

| Row | orderId | Amount | Disposition | Outcome |
| ---: | --- | ---: | --- | --- |
| 1 | O-101 | 100.00 | READY | Write |
| 2 | O-102 | 200.00 | READY | Write |
| 3 | O-103 | 150.00 | READY | Write |
| 4 | O-104 | 100.00 | READY | Write |
| 5 | O-105 | 250.00 | READY | Write |
| 6 | O-106 | 100.00 | READY | Write |
| 7 | O-107 | 200.00 | READY | Write |
| 8 | O-108 | 150.00 | READY | Write |
| 9 | O-109 | 300.00 | CANCELLED | Filter |
| 10 | O-110 | -50.00 | INVALID | Process skip |

The expected result is **8 orders O-101 through O-108**, total amount **1,250.00**. The CANCELLED and INVALID rows must not be written to the target.

In a simple run with no read skips or other retry/rollback scenarios, `StepExecution` might have:

~~~text
readCount         = 10
writeCount        = 8
filterCount       = 1
processSkipCount  = 1
skipCount         = 1
~~~

Those counters describe the processing flow; reconciliation must still verify the **exact keys and amounts** in the target table. A writer writing the wrong `orderId` would still increment `writeCount` normally.

Filter/skip conditions must reflect the **business agreement**. Do not assume every skipped item is acceptable: if critical data fails, policy may require the Job to become `FAILED` rather than allowing skips.

## 5. Staging Table and Target Table

Example relatively database-agnostic SQL schema:

~~~sql
CREATE TABLE staging_order (
    batch_id        VARCHAR(64) NOT NULL,
    line_number     BIGINT NOT NULL,
    order_id        VARCHAR(64),
    amount          DECIMAL(18, 2),
    disposition     VARCHAR(16) NOT NULL,
    PRIMARY KEY (batch_id, line_number)
);

CREATE TABLE imported_order (
    batch_id        VARCHAR(64) NOT NULL,
    order_id        VARCHAR(64) NOT NULL,
    amount          DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (batch_id, order_id)
);

CREATE INDEX idx_staging_order_recon
    ON staging_order (batch_id, disposition, order_id);
~~~

**staging_order** uses a key on `line_number` to preserve every input row, even when multiple rows share the same `orderId`. **imported_order** enforces uniqueness within a batch. If the business forbids duplicate `orderId` system-wide, the target unique key must reflect system-wide scope rather than just batch scope.

A shared bug in disposition logic and import logic could cause expected and actual to both be wrong. For sensitive or financial data, maintain a manifest/source checksum or an independent check source to reduce the risk of both sides sharing the same bug.

## 6. Comparing Counts and Amount Totals

Expected totals:

~~~sql
SELECT
    COUNT(*) AS expected_count,
    COALESCE(SUM(amount), 0) AS expected_amount
FROM staging_order
WHERE batch_id = :batchId
  AND disposition = 'READY';
~~~

Actual totals:

~~~sql
SELECT
    COUNT(*) AS actual_count,
    COALESCE(SUM(amount), 0) AS actual_amount
FROM imported_order
WHERE batch_id = :batchId;
~~~

With the fixture data:

~~~text
expected_count  = 8
actual_count    = 8
expected_amount = 1250.00
actual_amount   = 1250.00
~~~

Use **DECIMAL/NUMERIC** in the database and **BigDecimal** in Java when comparing money. Never use `float`/`double` for financial reconciliation. When comparing with `BigDecimal`, **`compareTo() == 0`** checks numeric equality; **`equals()`** also compares scale so `1.0` and `1.00` differ under `equals`.

When multiple currencies exist, group by **currency** and reconcile separately. If conversion is mandatory, agree on exchange rate source, rate timestamp, and rounding policy.

Matching amount totals alone is insufficient. For example:

~~~text
O-101: expected 100.00, actual  90.00  (-10.00)
O-102: expected 200.00, actual 210.00  (+10.00)
~~~

The total remains unchanged even though **two rows have wrong values**. That is why comparison by business key is required.

## 7. Detecting Missing, Extra, Wrong-Amount, and Duplicate Keys

### Missing Expected Keys

~~~sql
SELECT s.order_id
FROM staging_order s
WHERE s.batch_id = :batchId
  AND s.disposition = 'READY'
  AND NOT EXISTS (
      SELECT 1
      FROM imported_order t
      WHERE t.batch_id = s.batch_id
        AND t.order_id = s.order_id
  )
ORDER BY s.order_id;
~~~

### Extra Keys or Keys Not in Accepted Data

~~~sql
SELECT t.order_id
FROM imported_order t
WHERE t.batch_id = :batchId
  AND NOT EXISTS (
      SELECT 1
      FROM staging_order s
      WHERE s.batch_id = t.batch_id
        AND s.order_id = t.order_id
        AND s.disposition = 'READY'
  )
ORDER BY t.order_id;
~~~

This query also catches a `CANCELLED` key accidentally written by the writer.

### Amount Mismatches on Keys Present on Both Sides

~~~sql
SELECT
    s.order_id,
    s.amount AS expected_amount,
    t.amount AS actual_amount
FROM staging_order s
JOIN imported_order t
  ON t.batch_id = s.batch_id
 AND t.order_id = s.order_id
WHERE s.batch_id = :batchId
  AND s.disposition = 'READY'
  AND s.amount <> t.amount
ORDER BY s.order_id;
~~~

If **NULL** carries business meaning, the **<>** operator misses NULL-related mismatches. Use database-appropriate null-safe comparisons or ensure required fields are verified `NOT NULL` before reconciling.

### Duplicate Keys in the Source

~~~sql
SELECT order_id, COUNT(*) AS occurrences
FROM staging_order
WHERE batch_id = :batchId
  AND disposition = 'READY'
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

If the business intentionally aggregates multiple source rows into one target row, change expected to **GROUP BY order_id** with the corresponding amount/quantity aggregation rule. Then duplicates in staging can be valid, while comparison still operates by key and the defined transformation.

If the writer applies transformations (rounding, normalization, splitting a transaction into multiple ledger entries), expected values must also apply the **transformation contract**, rather than naively comparing raw staging values against target data.

## 8. Writing a Reconciliation Service with Spring JDBC

Example with Spring Boot 3.x, Spring Batch 5.x, Java 17, and **NamedParameterJdbcTemplate**. The service takes a locked `batchId` and returns a report; the example tables from earlier must exist.

~~~java
import java.math.BigDecimal;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderReconciliationService {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderReconciliationService(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public ReconciliationResult reconcile(String batchId) {
        Map<String, ?> params = Map.of("batchId", batchId);

        Totals expected = queryTotals("""
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(amount), 0) AS amount_total
            FROM staging_order
            WHERE batch_id = :batchId
              AND disposition = 'READY'
            """, params);

        Totals actual = queryTotals("""
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(amount), 0) AS amount_total
            FROM imported_order
            WHERE batch_id = :batchId
            """, params);

        long missing = queryCount("""
            SELECT COUNT(*) FROM staging_order s
            WHERE s.batch_id = :batchId
              AND s.disposition = 'READY'
              AND NOT EXISTS (
                  SELECT 1 FROM imported_order t
                  WHERE t.batch_id = s.batch_id
                    AND t.order_id = s.order_id
              )
            """, params);

        long unexpected = queryCount("""
            SELECT COUNT(*) FROM imported_order t
            WHERE t.batch_id = :batchId
              AND NOT EXISTS (
                  SELECT 1 FROM staging_order s
                  WHERE s.batch_id = t.batch_id
                    AND s.order_id = t.order_id
                    AND s.disposition = 'READY'
              )
            """, params);

        long wrongAmount = queryCount("""
            SELECT COUNT(*) FROM staging_order s
            JOIN imported_order t
              ON t.batch_id = s.batch_id
             AND t.order_id = s.order_id
            WHERE s.batch_id = :batchId
              AND s.disposition = 'READY'
              AND s.amount <> t.amount
            """, params);

        long duplicateGroups = queryCount("""
            SELECT COUNT(*) FROM (
                SELECT order_id
                FROM staging_order
                WHERE batch_id = :batchId
                  AND disposition = 'READY'
                GROUP BY order_id
                HAVING COUNT(*) > 1
            ) d
            """, params);

        boolean matched =
                expected.count() == actual.count()
                && expected.amount().compareTo(actual.amount()) == 0
                && missing == 0 && unexpected == 0
                && wrongAmount == 0 && duplicateGroups == 0;

        return new ReconciliationResult(
                batchId, expected, actual,
                missing, unexpected, wrongAmount,
                duplicateGroups, matched);
    }

    private Totals queryTotals(String sql, Map<String, ?> params) {
        return jdbc.queryForObject(sql, params, (rs, rowNum) ->
                new Totals(
                    rs.getLong("cnt"),
                    rs.getBigDecimal("amount_total")));
    }

    private long queryCount(String sql, Map<String, ?> params) {
        Long count = jdbc.queryForObject(sql, params, Long.class);
        if (count == null) {
            throw new IllegalStateException("Count query returned null");
        }
        return count;
    }

    public record Totals(long count, BigDecimal amount) {}

    public record ReconciliationResult(
            String batchId,
            Totals expected,
            Totals actual,
            long missingCount,
            long unexpectedCount,
            long wrongAmountCount,
            long duplicateSourceGroups,
            boolean matched) {}
}
~~~

This puts **expected**, **actual**, and mismatch counts into a structured object, making reporting far clearer than a generic "Job failed" message.

Implementation notes:

- Every query filters by the same **batchId** and uses parameter binding.
- **COUNT(*)** is row count; `duplicateGroups` here is the number of duplicated `orderId` groups, not the number of extra rows.
- If source data is updated concurrently, consecutive queries can read different snapshots. Lock the processing period logically or use proper transaction/snapshot isolation.
- For millions of rows, add proper indexes and consider partitioning/grouped aggregation to avoid repeated full scans.
- Detailed reports can fetch lists of mismatched `orderId`s using the queries in section 7, while keeping payloads/logs bounded and storing full evidence in an appropriate audit store.

## 9. Where to Place Reconciliation in the Job Lifecycle?

"Post-job reconciliation" can be implemented in two patterns, chosen by the **business status contract**.

### 9.1. Final Reconciliation Step in the Same Job

If the Job **is only considered successful once data is reconciled**, add a final Step after the import Step:

~~~text
stageInputStep
      |
      v
importOrdersStep
      |
      v
reconcileOrdersStep
      |
  PASS / FAILED
      |
  Job final status
~~~

Configuration example:

~~~java
@Bean
Step reconcileOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        OrderReconciliationService reconciliationService) {

    return new StepBuilder("reconcileOrdersStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                String batchId = chunkContext.getStepContext()
                        .getStepExecution()
                        .getJobExecution()
                        .getJobParameters()
                        .getString("batchId");

                var result = reconciliationService.reconcile(batchId);
                if (!result.matched()) {
                    throw new IllegalStateException(
                        "Reconciliation failed: batchId=" + batchId
                        + ", missing=" + result.missingCount()
                        + ", unexpected=" + result.unexpectedCount()
                        + ", wrongAmount=" + result.wrongAmountCount());
                }

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}

@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step stageInputStep,
        Step importOrdersStep,
        Step reconcileOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(stageInputStep)
            .next(importOrdersStep)
            .next(reconcileOrdersStep)
            .build();
}
~~~

The example assumes ingestion beans are already defined and **batchId** is an identifying `JobParameter`. If the reconciliation Step throws an unhandled exception, the Step and Job end **FAILED** under normal flow mechanics.

**Audit transaction note:** if you persist a discrepancy report inside the Tasklet's transaction and then throw an exception, that record may be rolled back. Save the report in an appropriate independent transaction or durable audit mechanism before throwing so the Job reflects the true status.

**Restart note:** when a Job finishes the import Step but fails at the reconciliation Step, restarting the same `JobInstance` normally skips `COMPLETED` Steps. If the failure came from bad import data, re-running reconciliation alone will not fix the data. You need an idempotent remedial import/reprocess workflow or a controlled step re-run policy.

### 9.2. Reconciliation Actually Running After the Job Ends

A system may need to wait for downstream data, an external audit service, or multiple Jobs to finish before reconciling. You can use **JobExecutionListener.afterJob(...)** to emit a signal/log:

~~~java
@Component
public class ReconciliationSignalListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ReconciliationSignalListener.class);

    @Override
    public void afterJob(JobExecution execution) {
        if (execution.getStatus() != BatchStatus.COMPLETED) {
            return;
        }

        log.info(
            "Reconciliation required: jobExecutionId={}, batchId={}",
            execution.getId(),
            execution.getJobParameters().getString("batchId"));
    }
}
~~~

**Do not rely on throwing an exception from `afterJob` to force a Job to FAILED.** The callback runs during finalization; if reconciliation must determine Job success/failure, use an explicit Step. When auditing runs **asynchronously outside the Job**, track separate states: **PENDING, RUNNING, PASSED, FAILED, INCONCLUSIVE**.

For example, a Job may be **COMPLETED** while the business workflow remains **PENDING_RECONCILIATION**. Data publishing systems should check reconciliation status before releasing if required by business rules.

Emitting audit notifications must be durable and idempotent; a single log line after the Job does not replace an outbox, a retriable queue, or a reconciliation-request table.

## 10. Discrepancy Reports and Remediation Workflow

A report record should contain:

| Field | Example |
| --- | --- |
| batchId | batch-20261115-001 |
| businessDate | 2026-11-15 |
| sourceVersion | snapshot-v3 |
| jobExecutionId | 8542 |
| reconciliationRunId | recon-003 |
| checkedAt | 2026-11-16T02:15:00Z |
| expectedCount / actualCount | 8 / 7 |
| expectedAmount / actualAmount | 1250.00 / 1150.00 |
| missingCount | 1 |
| unexpectedCount | 0 |
| wrongAmountCount | 0 |
| duplicateSourceGroups | 0 |
| status | FAILED |
| ruleVersion | recon-orders-v2 |

A typical operational workflow includes:

~~~text
PENDING -> RUNNING
             |
         +---+----------+
         |              |
       PASSED         MISMATCH
         |              |
       Publish       Save report
                        |
                    Investigate
                        |
                    Remediate
                        |
                    RECHECK
                        |
                    PASSED / FAILED
~~~

If the source or target system is temporarily unavailable, use **INCONCLUSIVE** and retry per policy. Never mark `PASS` without sufficient evidence.

Reports should record sample mismatched keys for investigation without dumping full sensitive payloads into logs. History of reconciliation runs and remediations must be retained for auditing; never erase old mismatches after fixing data.

## 11. Distinguishing StepExecution Counts from Business Outcomes

Spring Batch provides **StepExecution** with counts such as:

| Count | Meaning | Limitation for Reconciliation |
| --- | --- | --- |
| readCount | Successfully read items | Not always equal to physical lines, especially when the reader skips errors |
| writeCount | Items recorded by the framework as written | Does not guarantee accurate values or keys at the target |
| filterCount | Items for which processor returned `null` | May be valid exclusions per policy |
| read/process/write skipCount | Errors skipped by stage | Does not prove all skips were business-approved |
| commitCount | Recorded transaction commits | Not an item count |
| rollbackCount | Recorded transaction rollbacks | Does not directly state lost items |

For the simple fixture:

~~~text
readCount = 10
filterCount = 1
processSkipCount = 1
writeCount = 8

Expected business rows = 8
Actual rows should be 8, correct keys and amounts
~~~

Final reconciliation is only valid when **expected is derived from a trusted source** and **actual is queried from real target data**. Counters help diagnose how the Step behaved when a mismatch occurs.

## 12. Reconciliation When a Job Restarts

Example:

~~~text
JobInstance: importOrdersJob(batchId=batch-001)
  |
  +-- JobExecution #1: FAILED
  |      First chunk committed
  |      Later chunk rolled back
  |
  +-- JobExecution #2: COMPLETED
         Reader restores checkpoint
         Continues processing remaining data
         Reconciles final outcome
~~~

Rules:

1. Use the **same identifying JobParameters** for restarting a `JobInstance`.
2. Source snapshot and business rules must remain consistent between runs.
3. The writer needs an **idempotency key** or unique constraint to prevent duplicates on replay.
4. Reconcile **final target data by `batchId`**, not just the latest `StepExecution` counters.
5. Never blindly sum counters across multiple `StepExecution`s to conclude unique business record counts.

If an import Step is `COMPLETED` while reconciliation `FAILED`, a restart may run only the reconciliation Step. If target data needs fixing, perform remediation first or design a dedicated safely re-runnable repair Step.

## 13. Downstream and Eventual Consistency

A pipeline often looks like:

~~~text
Spring Batch -> Message broker -> Consumer -> Data warehouse
~~~

The Job may complete right after the producer sends messages, before the warehouse finishes writing. Reconciling immediately when the Job reaches `COMPLETED` will observe temporary missing data.

Distinguish:

- **Producer sent/acknowledged:** data sent to the broker per the producer contract.
- **Consumer processed:** consumer processed the message.
- **Target persisted:** data exists in the target system.
- **Business finalized:** reconciliation `PASS`ed.

Wait for acknowledgements or a watermark by `batchId` with a clear deadline before reconciling. When sync conditions are not yet met, record **PENDING/INCONCLUSIVE** instead of a premature `MISMATCH`. Escalate alerts upon timeout.

In distributed systems, an external API may have received side effects before the Step committed its checkpoint. Restarting can resend the request. **Reconciliation detects post-processing discrepancies**; preventing duplicates requires idempotency, outboxes, deduplication, and target constraints.

## 14. Reconciling Large Datasets

Row-by-row queries over hundreds of millions of records can be I/O-heavy. A practical strategy:

1. **Fast aggregates:** counts, sums, min/max, totals by currency/status.
2. **Scope slicing:** reconcile by `businessDate`, `batchId`, tenant, or partition.
3. **Locate failing groups:** counts and sums by smaller groups to narrow down the discrepancy area.
4. **Key-by-key checks:** SQL anti-joins for missing/extra keys; joins for field mismatches.
5. **Persist results:** surface only small samples on dashboards while storing full discrepancy lists in an appropriate report store.

Example:

~~~sql
SELECT
    batch_id,
    disposition,
    COUNT(*) AS row_count,
    COALESCE(SUM(amount), 0) AS total_amount
FROM staging_order
WHERE batch_id = :batchId
GROUP BY batch_id, disposition;
~~~

Notes:

- Indexes on `batch_id` and join/filter columns reduce full scans.
- For mutating input/target tables, use appropriate snapshot/transaction isolation.
- With read replicas, replication lag can create false mismatches.
- Hashes/checksums help localize mismatched regions, though they do not eliminate collision risks or canonicalization issues.
- Monetary fields need consistent precision, scale, rounding, and currency rules.
- Large datasets can use partitioning and parallel reconciliation, provided partition scopes sum cleanly without overlap.

## 15. Testing Reconciliation

A minimum test suite should cover these scenarios:

| Scenario | Expected | Actual | Outcome |
| --- | --- | --- | --- |
| All 8 orders | 8 keys, total 1250.00 | Keys/amounts match | PASS |
| Missing O-103 | 8 keys | 7 keys | Missing |
| Extra O-999 | 8 keys | 9 keys | Unexpected |
| Wrong amount on O-101 | 100.00 | 90.00 | Wrong amount |
| Two offsetting wrong amounts | Totals still match | Two rows wrong | Field mismatch |
| Two READY rows with same `orderId` | Duplicate key in staging | One key at target | Duplicate source |
| Job fails mid-chunk | Incomplete input | Incomplete data | Pending restart/remediation |
| Downstream lagging | Input finalized | Target still processing | PENDING/INCONCLUSIVE |

### Service Unit/Integration Tests

With Spring Boot Test, seed the test database and invoke the service:

~~~java
@Test
void shouldDetectMissingOrder() {
    String batchId = "missing-order-fixture";

    // Fixture:
    // staging: O-101 and O-102 are both READY.
    // target: only O-101 exists.

    var report = reconciliationService.reconcile(batchId);

    assertThat(report.matched()).isFalse();
    assertThat(report.missingCount()).isEqualTo(1);
    assertThat(report.expected().count()).isEqualTo(2);
    assertThat(report.actual().count()).isEqualTo(1);
}
~~~

Fixtures must be genuinely seeded before the test. Simply mocking queries to return expected counts does not prove the anti-join SQL works properly.

### Full-Job Integration Tests

When reconciliation is the final Step, use **spring-batch-test** and **JobLauncherTestUtils**:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ReconciliationJobTest {

    @Autowired
    private JobLauncherTestUtils testUtils;

    @Test
    void completesWhenReconciliationPasses() throws Exception {
        String batchId = UUID.randomUUID().toString();
        // Seed staging fixture with batchId and expected output.

        JobParameters params = new JobParametersBuilder()
                .addString("batchId", batchId, true)
                .toJobParameters();

        JobExecution job = testUtils.launchJob(params);

        assertThat(job.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(job.getStepExecutions())
                .anyMatch(step ->
                    step.getStepName().equals("reconcileOrdersStep")
                    && step.getStatus() == BatchStatus.COMPLETED);
    }
}
~~~

This assumes a synchronous `JobLauncher`, an existing fixture, the Job properly set on `testUtils`, and prepared source/target tables. Add a second test introducing a target mismatch and verifying **reconcileOrdersStep FAILED**, making the Job fail.

For audits running outside the Job, test **reconciliation status** and data publish gating in the workflow rather than checking `BatchStatus` alone.

### Testing Restart and Idempotency

An important test to run:

1. Let the Job import the first chunk successfully.
2. Inject a controlled failure in a later chunk.
3. Restart the same `JobInstance` keeping source data unchanged.
4. Verify target output is **complete, with no duplicates**.
5. Run reconciliation, require `PASS`, and inspect execution history.

This verifies checkpoint/restart produces accurate data and catches writer bugs that fire side effects twice.

## 16. Common Pitfalls

**Looking only at `BatchStatus.COMPLETED`.** Status reflects technical flow, not data accuracy.

**Comparing only `COUNT(*)`.** Missing one key while adding another keeps counts equal.

**Comparing only `SUM(amount)`.** Opposite discrepancies can cancel out; compare by business key.

**Using `writeCount` as expected.** It is not an independent expectation source.

**Computing expected and actual from the same target table.** The check becomes circular and misses errors.

**Failing to scope by processing period.** Data from other batches leaks into counts/sums.

**Ignoring `NULL`, currency, or rounding.** Values may look equal while being business-wrong or miscompared.

**Using an `afterJob` exception to force `FAILED`.** If reconciliation must decide Job status, use a proper Step.

**Saving failure reports inside a transaction that rolls back.** Reports can vanish when the Step throws an exception.

**Reconciling before downstream stabilizes.** Replication lag or message lag causes false mismatches.

**Not retaining remediation history.** After fixing data, the system loses evidence of the failed reconciliation.

## 17. Production Adoption Checklist

- [ ] Fixed **batchId/businessDate/sourceVersion**.
- [ ] Source snapshot finalized before comparison.
- [ ] READY, CANCELLED, INVALID, and skip rules explicitly defined.
- [ ] Expected source independent of the output under verification.
- [ ] Compare counts, total amounts/quantities, and business key sets.
- [ ] Compare critical fields after applying exact transformation rules.
- [ ] Detect missing, unexpected, duplicate, and mismatched values.
- [ ] Explicitly handle decimal precision, rounding, `NULL`, and currency.
- [ ] Choose a reconciliation Step or external audit matching Job status semantics.
- [ ] Persist outcomes, discrepancies, `ruleVersion`, check runs, and remediation history.
- [ ] Support `PENDING/INCONCLUSIVE` for unstable sources or downstream systems.
- [ ] Policy blocking data publishing until `PASSED`.
- [ ] Safe remediation and restart/idempotency plan.
- [ ] SQL/index/snapshot strategy suited to data scale.
- [ ] Tests covering valid, missing, extra, wrong-amount, duplicate, restart, and downstream-lag cases.

## 18. Reference Operational Flow

~~~text
1. Receive source + manifest
                |
                v
2. Lock staging snapshot by batchId
                |
                v
3. Run Spring Batch import
                |
          +-----+------+
          |            |
       FAILED      Import COMPLETED
          |            |
      Retry /          v
      Restart      Reconciliation
                       |
                +------+------+
                |             |
               PASS        MISMATCH
                |             |
             Publish      Audit + Alert
                              |
                          Remediate
                              |
                           Recheck
~~~

A run truly meets quality requirements only when results are verified by **exact batch, exact period, exact business keys, and exact values** and obey the data publishing policy. `StepExecution` counters explain how processing behaved; reconciliation uses an independent expected source to verify final outcomes. Combining reconciliation with auditing, restarts, and idempotent writers catches discrepancies early, supports remediation, and reduces the risk of propagating bad data downstream.


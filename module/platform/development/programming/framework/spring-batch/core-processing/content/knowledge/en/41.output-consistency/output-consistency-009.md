# Verifying output after job completion

## 1. Why does a completed job still need output verification?

In Spring Batch, a job transitions to **COMPLETED** when its execution flow finishes successfully according to its configuration. This confirms that the processing steps reached a valid termination point, but **does not by itself prove that the output data is complete, duplicate-free, business-accurate, or ready for downstream systems to consume**.

For example, a job reading order data and writing to a target table can report COMPLETED even when:

- The processor accidentally filtered out more records than expected.
- The right number of records were written, but with wrong amounts or wrong customer keys.
- A CSV file has all lines, yet has the wrong header, encoding, or comma-escaping rules.
- The writer wrote to an external API that accepted the request, while asynchronous processing has not completed.
- A re-run overwrote or duplicated data exported by a previous run.

**Verifying output after job completion** is the step of reconciling the data actually persisted or published against a predefined **output contract**. This contract must specify the expected record set, transformation rules, uniqueness, control totals, format, and when the output is considered ready.

A typical implementation flow looks like this:

~~~text
Data source
    |
    v
Read -> Process -> Write output
                    |
                    v
             Commit/close writer
                    |
                    v
             Reconcile output
               |          |
             Pass        Fail
               |          |
               v          v
          Publish      Mark FAILED,
          result       alert and handle
~~~

Ideally, reconciliation is implemented as **a verification Step following the data-writing Step**, so Spring Batch returns COMPLETED for the entire job only when both processing and verification succeed.

## 2. Distinguishing execution status from data correctness

| Signal | What it confirms | What it cannot conclude |
|---|---|---|
| **JobExecution.status = COMPLETED** | The job's control flow finished successfully per configuration | Output values and contents are correct |
| **JobExecution.exitStatus** | Exit code assigned by the job/step; may be a custom code | Output met all business criteria |
| **StepExecution.readCount** | Number of items read according to Step statistics | All those items must appear at the destination |
| **StepExecution.filterCount** | Number of items filtered out by the processor returning null | Whether filtering followed the right rules |
| **StepExecution.writeCount** | Number of items written according to Spring Batch counters | Data is duplicate-free, value-accurate, and durable in all external systems |
| **Skip/rollback counters** | Whether skips or rollbacks occurred during processing | Whether skips are business-acceptable and output is complete |
| **Querying target file/table/API** | Observable output state after writing | Whether output matches expectations without a baseline to reconcile against |

Note: the number of items Spring Batch records **does not necessarily correspond 1:1 with the number of rows in a table**. A processor can filter records, a writer can write multiple rows per item, or a writer can write to an external system not participating in Spring Batch's transaction. Therefore, do not apply a rule like "readCount must equal writeCount" to every job.

**BatchStatus and ExitStatus are different:** BatchStatus represents operational status (COMPLETED, FAILED, STOPPED...), while ExitStatus is the logical outcome that can be customized by listeners or flows. When an application defines a special exit code, inspect both according to the job contract. Do not treat a custom exit code by itself as proof of correct output.

## 3. Defining the output contract before reconciling

Suppose an order-import job has a **batchId** parameter, reads **staging_order**, filters invalid records, and writes to **processed_order**. The contract might specify:

1. **Scope:** only records belonging to the exact batchId; do not use totals across the entire target table.
2. **Completeness:** every valid order in the input set has exactly one corresponding record at the destination.
3. **Uniqueness:** the business key **(batch_id, source_id)** is unique at the destination.
4. **Accuracy:** amount, currency, customer_id, and transformed fields match normalization rules.
5. **Control totals:** total amount or totals by currency, status, and customer match expectations.
6. **Isolation:** run A does not alter output belonging to batch B.
7. **Readiness:** publish the batch to consumers only after verification succeeds.

Express the contract as verifiable criteria:

| Check group | Example pass criterion |
|---|---|
| Count | Target order count equals the number of accepted valid orders |
| Completeness | No valid source_id is missing at the destination |
| No out-of-scope extras | No target source_id falls outside the valid input set |
| Uniqueness | Each (batch_id, source_id) appears exactly once |
| Values | Each amount/currency/status matches the defined transformation result |
| Format | CSV matches schema, delimiter, UTF-8, encoding, and quoting rules |
| Consistency on restart | Re-running creates no extra duplicate records or partial output |

**The expected baseline must be sufficiently independent of the output.** If you compute both expected and actual solely from the target data, the check can validate an incorrect result. Expected values should come from an input snapshot, the accepted record set, business metadata, or a control table locked prior to export.

### Defining data boundaries

Each reconciliation result must be bound to an explicit key, such as **batchId**, business date, tenant, and export version. Avoid checking counts on a shared table when multiple jobs run concurrently. If source data can change during execution, use snapshots, watermarks, or frozen staging tables to guarantee the same dataset is used for both processing and reconciliation.

### Defining clearly how filtered and skipped items are handled

Suppose there are 1,000 input records, 75 records are filtered by business rules, 5 other records are permitted to skip after errors, and each valid item produces exactly one output row. The expectation may be **920 rows** if the contract accepts all 5 skips. If the business cannot afford to lose any valid order, the job must become FAILED rather than automatically treating 920 rows as valid.

Read/write/skip counters aid investigation; **expected valid counts must be determined by business policy**, especially when retries, rollbacks, 1:n mapping, or multi-step transformations are involved.

## 4. Verification sequence after writing finishes

A practical workflow should follow this order:

1. **Confirm completion timing.** Only reconcile committed output with closed writers; if running jobs asynchronously, wait or poll until JobExecution reaches a terminal state.
2. **Inspect Step statuses.** Review executed Steps, failed/skipped Steps, exit codes, and recorded errors.
3. **Isolate the run's output.** Use batchId or an immutable output location/version.
4. **Reconcile counts, keys, and values.** Prefer targeted verification queries over simple total row counts.
5. **Verify physical integrity.** For files: existence, size, schema, parseability, and checksum. For DBs: committed data, unique keys, and publication status.
6. **Record evidence.** Save expected count, actual count, missing/duplicate counts, error samples, timestamp, jobExecutionId, and batchId for traceability.
7. **Publish only on pass.** Mark the batch READY, update the manifest, or emit events to consumers after all criteria pass.

A few "write succeeded" log lines or a single row count assist observability, not contract-based data verification.

## 5. Examples of reconciling database output

Assume the illustrative data model:

- **staging_order(batch_id, source_id, valid, amount, currency)** holds the frozen input.
- **processed_order(batch_id, source_id, amount, currency)** is the output.
- For **valid = TRUE**, each source_id must have exactly one output row with amount and currency transformed per business rules. The examples below focus on completeness and uniqueness; value checks must be added according to the actual transformation.
- The system should place a unique constraint on **processed_order(batch_id, source_id)** to enforce idempotency directly at the data layer.

### 5.1. Counting rows in scope

~~~sql
-- Expected: number of input records permitted for export
SELECT COUNT(*)
FROM staging_order
WHERE batch_id = :batchId
  AND valid = TRUE;

-- Actual: number of records present at the destination
SELECT COUNT(*)
FROM processed_order
WHERE batch_id = :batchId;
~~~

Equal counts are a necessary condition in this 1:1 mapping example, **not a sufficient one**: one missing order and one duplicated order still yield the same total row count.

### 5.2. Finding missing records

~~~sql
SELECT s.source_id
FROM staging_order s
WHERE s.batch_id = :batchId
  AND s.valid = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM processed_order t
      WHERE t.batch_id = s.batch_id
        AND t.source_id = s.source_id
  );
~~~

The result must be empty. If rows appear, save sample source_ids as evidence to investigate filtering, skips, the writer, and transaction status.

### 5.3. Finding extra or invalid records

~~~sql
SELECT t.source_id
FROM processed_order t
WHERE t.batch_id = :batchId
  AND NOT EXISTS (
      SELECT 1
      FROM staging_order s
      WHERE s.batch_id = t.batch_id
        AND s.source_id = t.source_id
        AND s.valid = TRUE
  );
~~~

The result must be empty. This query catches records outside the valid input set, including leftover data from a previous run if a batchId was reused improperly.

### 5.4. Finding duplicates and value mismatches

~~~sql
-- Each source_id must appear exactly once within the batch.
SELECT batch_id, source_id, COUNT(*) AS occurrences
FROM processed_order
WHERE batch_id = :batchId
GROUP BY batch_id, source_id
HAVING COUNT(*) > 1;

-- Example when amount/currency are copied verbatim from staging.
-- If transformed, compare against the EXPECTED post-transform values.
SELECT s.source_id,
       s.amount AS expected_amount,
       t.amount AS actual_amount,
       s.currency AS expected_currency,
       t.currency AS actual_currency
FROM staging_order s
JOIN processed_order t
  ON t.batch_id = s.batch_id
 AND t.source_id = s.source_id
WHERE s.batch_id = :batchId
  AND s.valid = TRUE
  AND (
      s.amount <> t.amount
      OR s.currency <> t.currency
  );
~~~

The final comparison query only illustrates the case where fields are **untransformed** and **non-null**. If transformations involve rounding or currency conversion, compare against post-transformation values and explicitly specify precision/scale. For nullable columns, use null-safe comparisons appropriate to the database; standard **<>** does not properly detect cases where one side is null.

In addition to row-level checks, you can reconcile **SUM(amount)** by currency, totals by status, and distinct customer counts. Do not sum amounts of different currencies together without a conversion rule.

## 6. Attaching verification as a Step after the processing Step

In Spring Batch using builder configurations with **JobRepository** and **PlatformTransactionManager**, one approach is to create a verification tasklet running after the import Step. The sample below uses **JdbcTemplate**, assuming both tables are accessible from the datasource and **processOrdersStep** is defined in another configuration.

~~~java
import java.util.Objects;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrdersJobConfiguration {

    @Bean
    public Step verifyOutputStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbcTemplate) {

        return new StepBuilder("verifyOutputStep", jobRepository)
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
                            WHERE batch_id = ? AND valid = TRUE
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
                            WHERE s.batch_id = ? AND s.valid = TRUE
                              AND NOT EXISTS (
                                  SELECT 1 FROM processed_order t
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
                                  SELECT 1 FROM staging_order s
                                  WHERE s.batch_id = t.batch_id
                                    AND s.source_id = t.source_id
                                    AND s.valid = TRUE
                              )
                            """,
                            Long.class, batchId);

                    Long duplicateKeys = jdbcTemplate.queryForObject(
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

                    if (!Objects.equals(expected, actual)
                            || missing == null || missing != 0L
                            || unexpected == null || unexpected != 0L
                            || duplicateKeys == null || duplicateKeys != 0L) {
                        throw new IllegalStateException(
                                "Output mismatch, batchId=" + batchId
                                + ", expected=" + expected
                                + ", actual=" + actual
                                + ", missing=" + missing
                                + ", unexpected=" + unexpected
                                + ", duplicateKeys=" + duplicateKeys);
                    }

                    // Audit logging and total amount checks can be added here.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    public Job processOrdersJob(
            JobRepository jobRepository,
            @Qualifier("processOrdersStep") Step processOrdersStep,
            @Qualifier("verifyOutputStep") Step verifyOutputStep) {

        return new JobBuilder("processOrdersJob", jobRepository)
                .start(processOrdersStep)
                .next(verifyOutputStep)
                .build();
    }
}
~~~

**Conditions for applying this pattern:** input has unique source_ids within the batch, one valid input produces one output, and no business skips are permitted once the valid set is determined. For 1:n mappings, data aggregation, or controlled skips, adjust expected calculations and reconciliation queries to match the job contract. The sample does not yet check amount/currency; add those checks if required to publish output.

When a reconciliation query detects a discrepancy, the tasklet throws an exception; **verifyOutputStep becomes FAILED and the job does not finish as COMPLETED** in a standard sequential flow. The exception should include batchId, expected/actual counts, and discrepancy metrics; do not log entire sensitive record contents.

Placing checks only in **JobExecutionListener.afterJob** is suitable for logging, auditing, or sending notifications, but **you should not rely on an exception from afterJob to turn an already finished job into FAILED**. To have verification results determine job status, use a verification Step or flow control with an explicit failure branch.

### When to read JobExecution externally?

If a monitoring system runs outside the job, it can look up **JobExecution** via JobExplorer/JobOperator by execution ID and inspect only when status is terminal. Note that a launcher may run asynchronously: the value returned immediately upon launch is not necessarily the final outcome.

~~~java
// This snippet only illustrates reading the status of an already retrieved JobExecution.
if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
    // Reconcile output by the completed run's batchId.
} else if (jobExecution.getStatus() == BatchStatus.FAILED) {
    // Investigate the exception and failed Step before publishing output.
}
~~~

For jobs in **STOPPED**, **FAILED**, or running states, do not treat output as final. If statistical reports are needed, inspect **getStepExecutions()** to read each Step's counters and errors, then reconcile against actual destination data.

## 7. Verifying CSV/JSON/XML file outputs

For file outputs, writer item counts alone do not confirm that consumers can read the file properly. A verification workflow should include:

| Item | How to verify |
|---|---|
| Correct artifact | Path/object name contains batchId or version; no confusion with old files |
| Exists and finished writing | File is completely closed, valid size; not reading a file still being appended |
| Schema | Correct column count, header names, column order when required by contract |
| Parseability | Use an actual CSV/JSON/XML parser; do not count lines by naively splitting on newlines |
| Characters and format | Encoding, BOM, newlines, quoting/escaping, date format, decimal separator |
| Record count | Count logical records after parsing, distinguishing headers/trailers |
| Uniqueness and integrity | Business keys non-duplicated, required fields checked, totals/checksum |
| Publication state | Consumers see only verified files or manifest/READY markers |

Example CSV file:

~~~csv
batch_id,source_id,amount,currency
B20261116,O001,120.00,VND
B20261116,O002,95.50,USD
~~~

In this example, verification must confirm the header has four columns, each record parses validly, batch_id matches, source_id does not repeat, amount parses in the published format, and the set of source_ids matches expected input. **Do not use newline counting** as proof of CSV record count: quoted fields can contain newlines.

When exporting large files, a common arrangement is:

~~~text
orders-B20261116.csv.part
    -> writer closes file
    -> verify schema + records + checksum
    -> publish orders-B20261116.csv
    -> create manifest/READY marker
    -> downstream starts reading
~~~

Atomic rename can be used when **on the same filesystem and supported by that filesystem**; do not assume renames to another storage system are atomic. For object storage, create objects under a unique key/version, verify that exact object (e.g., metadata, size, and checksum), and only then write the manifest/READY marker. Do not treat listing an object as proof that a cross-system transaction completed.

If files must be delivered to another system via SFTP/API, distinguish **upload completed** from **processed by recipient**. Only declare completion at the level defined by the output contract with a corresponding acknowledgment signal.

## 8. Restart, retry, and post-job idempotency

Reconciliation is especially critical when a job wrote partial output and then failed. Spring Batch can manage rollbacks for resources participating in a transaction, but effects on files, HTTP APIs, message brokers, or another datasource **are not automatically rolled back with the transaction**.

Common strategies:

- **Idempotent keys:** unique keys such as (batch_id, source_id), controlled upsert writes, or skipping already-completed records in a controlled manner.
- **Stage then publish:** write output to a temporary area, verify the whole set, then transition status to READY or swap a version pointer.
- **Never write to an actively consumed target file:** write to a temporary name/new version, releasing only after closing and verifying.
- **Track per attempt:** distinguish **JobInstance**, **JobExecution**, and business batchId; a job can have multiple executions on restart.
- **Verify against the final set:** if restart is designed to append onto valid previously written data, expected/actual must reflect the batch's final output set rather than simply taking writeCount from the latest execution.

Example: attempt 1 writes 600/1,000 orders to an external system and fails. Attempt 2 reprocesses and may create 600 duplicate orders if the writer is not idempotent. Even if attempt 2 ends COMPLETED and reports 1,000 items, final output could still contain 1,600 records. Uniqueness and exact-set reconciliation catch defects that a status check misses.

When verification fails, re-runs must follow a **defined remediation procedure**: delete or quarantine temporary output, resume from checkpoint, or reprocess with idempotency keys. Avoid blindly deleting an entire target batch if it contains consumer-acknowledged data or is still used by another job.

## 9. Consistency across multiple systems

A job might simultaneously write to a DB, export a CSV, and emit events. If the three destinations are not in the same transaction, **COMPLETED** does not mean all receivers have reached a consistent state.

Example with an order export workflow:

1. Write orders to an output staging table.
2. Verify committed records in the table are complete and accurate.
3. Mark the batch READY in the same database or create an outbox record within the appropriate transaction.
4. A publisher relays the manifest/events externally and records delivery status.
5. Consumers rely on batchId/version and idempotency keys to avoid duplicate processing.

The **transactional outbox** pattern is useful when consistency between database updates and event emission is needed: write data and an outbox record in one transaction, then let a publisher send events and retry on failure. This supports reliable delivery while still requiring idempotent consumers due to possible duplicate deliveries.

If a target system has update latency, define clearly when data is considered observable and bounded wait/retry mechanisms. **Do not loosen reconciliation indefinitely** just to turn a failing batch into a passing status.

## 10. Auditing, alerting, and handling mismatches

Reconciliation results should produce an audit record sufficient to trace back the output version and next decision:

~~~text
jobName          = processOrdersJob
jobExecutionId   = 98765
batchId          = B20261116
outputVersion    = v3
expectedRecords  = 1000
actualRecords    = 999
missingRecords   = 1
unexpectedRecords= 0
duplicateKeys    = 0
amountMismatch   = 0
verification     = FAILED
verifiedAt       = 2026-11-16T09:30:00+07:00
~~~

This is only an example audit structure, not data taken from a real job. If checks fail:

1. **Block publication** or place the batch in QUARANTINED/INVALID so downstream does not consume it by mistake.
2. **Emit metrics and alerts**: record variance, total amount, duplicate count, verification duration, and batch failure rate.
3. **Collect bounded diagnostic samples**, such as a few missing source_ids, along with execution/Step metadata and correlation IDs.
4. **Check against policy:** certain variances may be permissible if the contract explicitly states thresholds; financial or ledger data generally requires strict reconciliation.
5. **Remediate root cause:** filter bugs, transform logic, retries, commits, incomplete files, changing source data, or asynchronous consumer processing.
6. **Re-reconcile after fixing:** transition to READY only when all mandatory conditions pass with fresh evidence.

The audit must reflect **verification of the specific outputVersion**. If output is rewritten later, an earlier audit is no longer sufficient to prove the new version was verified.

## 11. Test scenarios for the verification mechanism itself

When designing output verification, test at least these scenarios on sample data:

| Scenario | Expected outcome |
|---|---|
| 100 valid orders, all 100 written with correct values | Verification succeeds; job can become COMPLETED |
| 1 order missing even though writer count looks normal | Missing source_id detected; job FAILED/publication blocked |
| 1 order written twice, 1 other order missing | Both duplicate and missing detected even though total row count matches |
| Right row count but wrong amount | Field/amount total check detects mismatch |
| Filtered or skipped items matching policy | No failure reported when expected set reflects approved rules |
| Restart after partial output write | No duplicate records; reconciliation runs on the final set |
| CSV file with wrong header or bad quoting | Parser/schema validation fails |
| Two batches running concurrently | Each batch reconciled independently without cross-contamination |
| Object written successfully but READY marker missing | Consumer does not consider output available for use |
| Cannot access database/file during verification | Verification fails or stays unverified; never treated as passing |

These scenarios prove that verification truly catches **output consistency** errors rather than merely echoing framework status.

## 12. Common mistakes

**Checking only that JobExecution is COMPLETED.** Fix by adding a Step that reconciles actual data against an independent baseline.

**Comparing only readCount and writeCount.** Fix by accounting for filter, skip, transform, and mapping logic before setting count assertions.

**Comparing only COUNT(*).** Fix by reconciling missing/extra/duplicate records, business keys, values, and business totals.

**Reading output before the writer closes or transaction commits.** Fix by placing verification after the writing Step and agreeing on readiness signals.

**Checking the whole table without batchId.** Fix by scoping reconciliation strictly by batch/tenant/version and input snapshot.

**Publishing output before verifying.** Fix by staging, verifying, and only then transitioning to READY or creating a manifest.

**Assuming restarts are always safe.** Fix with idempotency keys, unique constraints, partial-output handling, and post-restart verification.

**Letting an after-job listener throw exceptions as the sole failure mechanism.** Fix by using a verification Step or flow with explicit FAILED handling.

## 13. Principles to apply

A reliable data-processing job needs two layers of confirmation: **proper execution flow** and **contract-compliant output**. With Spring Batch, place data checks after output is durable, make mandatory conditions a Step or verification mechanism with explicit state, retain reconciliation evidence per batch/version, and publish output only when all conditions pass.

As a result, COMPLETED carries more practical meaning: not just "the framework encountered no unhandled errors," but "the batch result has been verified as trustworthy enough for downstream consumption."

# Reconciling input, skipped, and output counts

In Spring Batch, the number of input records, the number of skipped records (*skipped*), and the number of output records are tracked in different counters. To know whether a processing step has processed all data, you must read the counters for the exact `read`, `process`, and `write` phases, and then reconcile them within the same `StepExecution` run.

The key point is that `readCount`, `writeCount`, `filterCount`, and the skip counters do not measure the same thing. A successfully read item may be written out, intentionally filtered, or skipped due to an error during processing or writing. Meanwhile, a read error accepted by the skip policy is recorded separately because that item was never successfully read.

## 1. Define the unit to count

Before comparing numbers, clarify what "one input" and "one output" mean in the step.

- **Input item** is an item that `ItemReader` provides to Spring Batch. It may correspond to a file line, a database row, a message, or an object built from multiple source lines.
- **Output item** is an item passed to `ItemWriter` and written successfully according to the writer's contract.
- **Output record/row** is the number of physical records created in the target system. This number can differ from `writeCount` if one item produces multiple rows or if the writer writes in a different structure.

For example, if an `ItemReader` reads individual orders and an `ItemWriter` writes each order as one row, `writeCount` can be compared directly against the number of output rows. If the writer splits one order into three detail lines, `writeCount` still counts successfully written order items; it does not automatically become the detail-line count.

State the unit explicitly in reports, such as "input items", "written order items", or "database rows". If the source has headers, trailers, comments, or multiple lines forming a single item, the total physical lines in the source does not necessarily equal the number of items the reader processes.

## 2. `StepExecution` counters

Spring Batch stores metrics for each step run in `StepExecution`. Counters commonly used for reconciliation include:

| Counter | Meaning | How to interpret during reconciliation |
|---|---|---|
| `readCount` | Number of items read successfully | Items that passed through the reader and were recognized by the framework as read items |
| `writeCount` | Number of items written successfully | Items whose write completed successfully; not necessarily physical target rows |
| `filterCount` | Number of items filtered by processor | Processor returned `null`; this is usually an intentional business decision, not a skip |
| `readSkipCount` | Number of read errors accepted and skipped | Items not successfully read due to reader errors |
| `processSkipCount` | Number of items skipped due to processor errors | Items that were read, but a processing error was accepted by the skip policy |
| `writeSkipCount` | Number of items skipped due to writer errors | Items that passed earlier stages but were not written due to an accepted write error |
| `skipCount` | Total skips across all three stages | Equals the sum of read skip, process skip, and write skip |
| `commitCount` | Number of transaction commits | Counts commits, not items or output records |
| `rollbackCount` | Number of transaction rollbacks | Useful for investigating transactions/retries; not skipped items |

You can retrieve these counters directly from `StepExecution` using methods such as `getReadCount()`, `getWriteCount()`, `getFilterCount()`, `getReadSkipCount()`, `getProcessSkipCount()`, `getWriteSkipCount()`, and `getSkipCount()`.

### Distinguishing filter and skip

Filter and skip can both keep a read item from appearing in output, but their causes and counters differ:

- **Filter:** the processor actively returns `null`, such as dropping canceled orders per business rules. The item is counted in `filterCount`, not `skipCount`.
- **Skip:** the reader, processor, or writer throws an exception and the configured skip policy permits skipping that error. The item is counted in the skip counter of the corresponding stage.

Therefore, `readCount - writeCount` is not synonymous with `skipCount`. The difference may include filtered items as well as items skipped during process or write.

## 3. Reconciliation formulas

For a chunk-oriented step, when the step finishes normally and every successfully read item reaches a final outcome, the following relationships apply.

**Total skips:**

```text
skipCount = readSkipCount + processSkipCount + writeSkipCount
```

**Breakdown of successfully read items:**

```text
readCount = writeCount
          + filterCount
          + processSkipCount
          + writeSkipCount
```

`readSkipCount` is excluded from the second formula because an item that fails during reading never becomes a successfully read item and is not added to `readCount`.

If the reader processes an entire input set of candidate records where each candidate corresponds to exactly one reader item, we can calculate:

```text
attemptedInputCount = readCount + readSkipCount
```

Combining the two relationships above:

```text
attemptedInputCount = writeCount + filterCount + skipCount
```

The final formula applies only when the entire input scope has been read and the source's counting unit matches the reader's item unit. If the step stops early, the reader skips data via custom logic, or one item is built from multiple source lines, use independent source metrics to explain the variance.

### Reconciliation example

Suppose a file has 1,000 valid records as defined by the application's input specification. The reader successfully reads 990 items and has 10 format-error records skipped during the read stage. Out of the 990 read items:

- The processor filters 40 items because they do not meet business conditions.
- 5 items raise errors in the processor and are skipped.
- 3 items raise errors in the writer and are skipped.
- 942 items are written successfully.

| Metric | Value |
|---|---:|
| Input candidates attempted | 1.000 |
| `readCount` | 990 |
| `readSkipCount` | 10 |
| `filterCount` | 40 |
| `processSkipCount` | 5 |
| `writeSkipCount` | 3 |
| `writeCount` | 942 |
| `skipCount` | 18 |

Verify the relationships:

```text
skipCount = 10 + 5 + 3 = 18

readCount = 942 + 40 + 5 + 3 = 990

attemptedInputCount = 990 + 10 = 1.000

attemptedInputCount = 942 + 40 + 18 = 1.000
```

The numbers match. There are 942 output items written successfully, 40 filtered items, and 18 skipped items. If the writer creates one target row per item, 942 written rows can be expected. If the writer creates multiple rows per item, count target rows via a separate query or metric.

## 4. Reading the exact meaning of each skip type

### Read skip

`readSkipCount` increments when the reader throws an error and the skip policy allows skipping it. A common example is an unparseable file line or a source record that cannot be converted into an item.

Because the item was not successfully read, this failure is not included in `readCount`. When explaining input totals, inspect `readCount` alongside `readSkipCount`, and check whether the reader ignores headers, comments, or records via custom rules.

### Process skip

`processSkipCount` increments when the processor throws an exception and Spring Batch decides to skip that item. The item was provided by the reader so it is already in `readCount`, yet it does not advance to the writer.

Distinguish the case where the processor returns `null`: that case is a filter and is counted in `filterCount`, not `processSkipCount`.

### Write skip

`writeSkipCount` increments when a write operation throws an exception and the skip policy allows skipping the failing item. That item was already successfully read, so it is in `readCount`, but is excluded from `writeCount` for the successful write.

A writer usually receives a chunk of multiple items. When writing a chunk fails, Spring Batch may roll back and repeat necessary operations to isolate the failing item according to the fault-tolerant configuration. Therefore, do not infer the number of skipped items from writer invocation counts or transaction rollback counts. Use the `StepExecution` counters and corresponding skip logs.

## 5. Logging and observing counters

A `StepExecutionListener` can log counters after a step finishes. The example below uses common Spring Batch listener APIs:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepCountLogger implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepCountLogger.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "step={} status={} read={} written={} filtered={} " +
            "readSkipped={} processSkipped={} writeSkipped={} totalSkipped={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getReadSkipCount(),
            stepExecution.getProcessSkipCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getSkipCount()
        );

        // null preserves the current ExitStatus of the step.
        return null;
    }
}
```

Register this listener with the step you want to observe. Logs should contain at least the step name, status, run identifier, and counters. In a system running multiple concurrent jobs, logging counts without `jobExecutionId` or equivalent context makes reconciling runs error-prone.

To know which item was skipped and why, you can add a `SkipListener`. The listener distinguishes three callbacks:

- `onSkipInRead(Throwable t)`: the error occurred in the reader; the callback has no item because the reader failed to produce one.
- `onSkipInProcess(T item, Throwable t)`: the input item is available and the error occurred in the processor.
- `onSkipInWrite(S item, Throwable t)`: the output item is available and the error occurred in the writer.

Log the item's business key when possible, exception type, and source details. For read skips, log the file position, offset, source key, or available reader context. Avoid logging raw sensitive data. If the application saves failed records to a reject/quarantine table, use a correlation key to compare that table against the skip count.

## 6. Reconciling from persisted metadata

Spring Batch typically stores step counters in the `BATCH_STEP_EXECUTION` metadata table. You can query by `JOB_EXECUTION_ID` to inspect the steps of a single run:

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

Table names or prefixes may be customized depending on repository configuration. If the system uses a different prefix, replace `BATCH_` with the configured prefix. Verify the environment's metadata schema before running queries.

When reading results:

1. Select the exact `JOB_EXECUTION_ID` and `STEP_EXECUTION_ID`.
2. Check `STATUS` before applying balance formulas.
3. Sum `skipCount` from the three skip columns to see clearly which stage generated them.
4. Compare `READ_COUNT` against the sum of `WRITE_COUNT`, `FILTER_COUNT`, `PROCESS_SKIP_COUNT`, and `WRITE_SKIP_COUNT`.
5. Reconcile physical output counts using target data or dedicated metrics if the writer does not write one row per item.

You can retrieve the same information through `JobExplorer` and `JobExecution`/`StepExecution` objects instead of querying SQL directly. Whichever approach you use, keep the same run scope when comparing.

## 7. Investigation workflow when numbers do not match

When input and output reports do not balance, follow these steps in order:

1. **Lock down scope:** identify the exact job execution, step execution, time window, and partition being compared. Do not mix numbers from different runs.
2. **Lock down units:** determine whether input is source lines, messages, or reader items; and whether output is writer items or physical rows in the target system.
3. **Check status:** expect the full balance formula to hold only when the step completed and processed all input in scope. A `FAILED`, `STOPPED`, or mid-chunk interrupted step may leave unclassified items.
4. **Compute total skips:** sum `readSkipCount`, `processSkipCount`, and `writeSkipCount`; then check which stage accounts for most skips.
5. **Account for filters:** inspect `filterCount` and processor conditions. Do not lump filters into skips in error reports.
6. **Verify the writer:** check the writer contract, write logs, transactions, and actual row count at the destination. `writeCount` reports items written successfully according to the framework, not independent confirmation of physical rows.
7. **Inspect error and skip logs:** use `SkipListener`, application logs, and reject/quarantine tables to find item-level causes.
8. **Check retries/rollbacks and restarts:** retries can invoke readers, processors, or writers multiple times. `rollbackCount` reflects transaction rollbacks and cannot be added directly to input or skip counts. When a job restarts, distinguish the current execution from prior executions of the same `JobInstance`.

If the step is `COMPLETED`, the reader read the full input scope, and the model passes one item through one processor to the writer, yet:

```text
readCount != writeCount + filterCount
              + processSkipCount + writeSkipCount
```

then look for unclassified items or differences in how the application measures data. Do not blindly assign the discrepancy to skips. Check execution status, data scope, custom readers/processors/writers, and listeners altering the flow.

## 8. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| `readCount - writeCount` is the skip count | The difference may also include `filterCount`, process skips, and write skips |
| Filter is a type of skip | Filters are recorded in `filterCount`; skips are recorded in the three stage-specific skip counters |
| Read skips are already in `readCount` | Read skips are accepted read errors; they are recorded separately in `readSkipCount` |
| `writeCount` always equals database row count | `writeCount` counts items written successfully; a writer may create more or fewer physical rows |
| `commitCount` is the number of saved records | It is the number of transaction commits; one commit can include an entire chunk |
| `rollbackCount` is the number of failed items | One rollback can involve multiple items and retries; read the skip counters separately |
| Summing metrics across all restarts gives total output | Executions may reprocess the same scope; determine which execution is the reporting source and verify writer idempotency |
| A `FAILED` step must balance like a `COMPLETED` step | Mid-chunk failures can leave items read but not yet written, filtered, or skipped |

## 9. Checklist for an output consistency report

Before concluding that a run balances, verify:

- [ ] Comparing the same `JobExecution` and `StepExecution`.
- [ ] Confirmed whether input item, output item, and output record share the same unit.
- [ ] Checked step `STATUS`.
- [ ] Calculated `skipCount` as the sum of the three skip types.
- [ ] Separated `filterCount` from skips.
- [ ] Verified the relationship among `readCount`, `writeCount`, `filterCount`, `processSkipCount`, and `writeSkipCount`.
- [ ] Accounted for `readSkipCount` when reconciling against total source input.
- [ ] Confirmed physical output counts in the target system when `writeCount` does not directly represent row count.
- [ ] Checked error logs, retries, rollbacks, restarts, or partitions when numbers do not balance.

A clear report presents `readCount`, `writeCount`, `filterCount`, each skip type, `skipCount`, step status, and the measurement unit separately. When numbers are drawn from the same execution and data scope, they show how many items were written, filtered, or skipped at each stage, while surfacing any unexplained input variance.

# Skip counts in StepExecution

In Spring Batch, a step can skip a number of failing items if the error belongs to a type configured as skippable. The framework records the number of skipped items in `StepExecution` via counters such as `readSkipCount`, `processSkipCount`, `writeSkipCount`, and total `skipCount`.

These counters help developers and operators see which stage of chunk processing produced errors, the scale of impact, and whether the step completed within its skip limit. To interpret the numbers accurately, distinguish skip from filter, retry, and rollback, and understand how `skipLimit` applies across the entire step.

## 1. What is skip in chunk processing?

A chunk-oriented step typically processes data in a cycle:

```text
ItemReader
    |
    v
ItemProcessor (optional)
    |
    v
ItemWriter
    |
    v
Commit transaction
```

During this process, the reader, processor, or writer can throw exceptions. Not every error should fail the step immediately. For example:

- A malformed CSV line where business rules allow discarding that individual line.
- A record with an invalid customer ID that must be sent to an error list.
- An item that cannot be written due to a constraint violation classified as a skippable error.

Spring Batch supports skip policies to classify exceptions. If an exception is skippable and the limit has not been exceeded, the framework skips the affected item and continues processing according to step policy.

Skip does not mean every exception is bypassed. Infrastructure or unrecoverable errors such as database disconnection, missing input files, or misconfigurations usually need to fail the step so they are handled explicitly.

## 2. Which counters does StepExecution store?

`StepExecution` represents a specific execution of a step. It stores status, timestamps, execution context, and item-processing counters.

Counters directly related to skip include:

| Counter | Meaning |
|---|---|
| `readSkipCount` | Number of times an item was skipped due to an exception during reading. |
| `processSkipCount` | Number of items skipped due to an exception during processing. |
| `writeSkipCount` | Number of items skipped due to an exception during writing. |
| `skipCount` | Total skips across read, process, and write stages. |

In the API, these values can be read via methods such as:

```java
long readSkips = stepExecution.getReadSkipCount();
long processSkips = stepExecution.getProcessSkipCount();
long writeSkips = stepExecution.getWriteSkipCount();
long totalSkips = stepExecution.getSkipCount();
```

Conceptually:

```text
skipCount = readSkipCount
          + processSkipCount
          + writeSkipCount
```

`skipCount` is a quick summary of overall item skipping. The three component counters help determine whether errors concentrate in the reader, processor, or writer.

## 3. Distinguishing skip counts from other counters

`StepExecution` has multiple counters. Do not use `skipCount` to infer the total items read or total items succeeded.

| Counter | Meaning |
|---|---|
| `readCount` | Number of items successfully read by the reader. |
| `writeCount` | Number of items successfully written by the writer per step counter. |
| `filterCount` | Number of items intentionally filtered by the processor returning `null`. |
| `readSkipCount` | Skips in the read stage. |
| `processSkipCount` | Skips in the process stage. |
| `writeSkipCount` | Skips in the write stage. |
| `skipCount` | Sum of the three skip groups. |
| `commitCount` | Number of step transactions committed. |
| `rollbackCount` | Number of rollbacks recorded for the step. |

For example, a step reads 1,000 items, the processor filters 20 items, skips 5 items due to bad data, and writes 975 items. You would see `filterCount=20`, `skipCount=5`, and `writeCount=975` (assuming no other factors affect the counters).

Filter and skip are two distinct concepts:

- **Filter:** processor returns `null` to intentionally exclude an item per business rules. Filtered items are not counted as skips.
- **Skip:** an exception occurs and is permitted by the skip policy. The framework records the bypassed item/read in the corresponding skip counter.

For example, a processor returning `null` for orders with status `CANCELLED` is filtering. If the processor throws `InvalidOrderException` and that exception is configured for skip, the item counts toward `processSkipCount`.

## 4. Three skip types corresponding to three stages

Spring Batch distinguishes skips by where the exception originates.

### Read skip

`readSkipCount` increments when the reader throws an exception allowed to be skipped. For instance, `FlatFileItemReader` encounters an unparseable line and the application configures `FlatFileParseException` as skippable.

In read errors, there is sometimes no valid Java item to pass to the listener because the reader has not built an item yet. Thus `onSkipInRead` receives only the exception, without an item.

### Process skip

`processSkipCount` increments when `ItemProcessor` throws a skippable exception. For example, the processor validates data and throws `InvalidOrderException` when a customer ID is invalid.

The input item was created by the reader, but could not be transformed into an output item. The framework skips that item and continues per configuration.

### Write skip

`writeSkipCount` increments when the writer throws an exception and one or more items are determined to be skippable under the skip policy. This case deserves attention because the writer usually receives an entire chunk. The framework must identify which item caused the write error in order to skip the right item.

For instance, a chunk has 100 orders and one order violates a unique constraint. Depending on writer type, exception, and fault-tolerance mechanism, Spring Batch may have to retry writing or analyze items to pinpoint the failing item. Do not assume every writer can isolate failing items identically or that write skips are always low-cost.

## 5. Configuring skipLimit

To enable skip in a chunk-oriented step, typically use `.faultTolerant()`, `.skip(...)`, and `.skipLimit(...)`.

Example using the Spring Batch 5+ API:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .build();
}
```

In this example:

- `faultTolerant()` enables error-handling configurations such as skip and retry for the step.
- `skip(...)` declares exception types allowed to be bypassed.
- `skipLimit(50)` sets the total skip limit for the step.

The skip limit applies jointly across read, process, and write errors, not 50 per stage. Once the step has skipped 50 items, the next skip fails the step for exceeding the limit.

### Example of how the limit is counted

Suppose `.skipLimit(10)` is configured:

| Skip # | Outcome |
|---:|---|
| 1 to 9 | Permitted if the exception is skippable. |
| 10 | Still within the limit. |
| 11 | Limit exceeded; step fails. |

Crucially, the limit totals across read, process, and write stages. For example, if a step has 4 read skips and 5 process skips, the total is 9. If one write skip occurs next, the total reaches 10; the subsequent skip exceeds the limit of 10.

## 6. Skip exceptions and noSkip

Enabling `faultTolerant()` does not automatically skip all exceptions. The application must explicitly state which exception types are skippable. You can use `.noSkip(...)` to exclude an exception type from the skip policy.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(Exception.class)
        .noSkip(FileNotFoundException.class)
        .skipLimit(20)
        .build();
```

The example above illustrates excluding a specific exception. In practice, a broad skip such as `Exception.class` is risky because it can turn system failures into skipped errors. Declare specific business exceptions that the application can safely bypass.

Key principles:

- Data errors can be skipped if tracking and reconciliation processes exist.
- Connection errors, timeouts, or database unavailability usually require bounded retry or failing the step.
- Configuration errors, missing required files, or schema mismatches generally should not be skipped.
- If one exception type has multiple distinct causes, classify them clearly rather than skipping the entire broad exception type.

## 7. Custom SkipPolicy

When skip rules depend on exception details, data types, or execution context, you can implement a custom `SkipPolicy`.

The interface provides a method deciding whether an exception should be skipped:

```java
public interface SkipPolicy {
    boolean shouldSkip(Throwable t, long skipCount)
            throws SkipLimitExceededException;
}
```

Example policy allowing skips for certain data errors, while disallowing system errors:

```java
public class OrderSkipPolicy implements SkipPolicy {

    private final long limit;

    public OrderSkipPolicy(long limit) {
        this.limit = limit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException
                || throwable instanceof FlatFileParseException) {
            if (skipCount < limit) {
                return true;
            }
            throw new SkipLimitExceededException(limit, throwable);
        }

        return false;
    }
}
```

Attaching the policy to the step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new OrderSkipPolicy(50))
        .build();
```

This example illustrates classification and limit logic. When writing a custom policy, understand the `skipCount` parameter passed by the framework, how the policy is invoked at different stages, and how nested exceptions (causes) are handled. Keep the policy simple, explicitly list permitted error types, and test boundary thresholds.

## 8. How are skip counts in StepExecution updated?

During execution, Spring Batch updates the counters corresponding to each skip type. When the step finishes, `StepExecution` metadata is persisted via `JobRepository`.

You can read counters directly inside a listener or when querying metadata:

```java
long total = stepExecution.getSkipCount();
long read = stepExecution.getReadSkipCount();
long process = stepExecution.getProcessSkipCount();
long write = stepExecution.getWriteSkipCount();
```

These values belong to one specific `StepExecution`. If the job restarts, a new `JobExecution` and new `StepExecution` instances may be created for steps that rerun. Therefore, do not assume a new execution's `skipCount` is the cumulative sum across all prior runs of the same JobInstance.

For a complete historical report, query the `StepExecution` instances belonging to the related `JobExecution`s and aggregate by JobInstance, business date, or batch reference. Keep clear which metrics belong to which execution to avoid double-counting.

## 9. Tracking skips with SkipListener

`SkipListener` provides callbacks for the application to record skipped items at each stage. It is the right place to persist error details, record IDs, and causes instead of relying only on total counters.

Primary callbacks:

| Callback | When invoked | Information received |
|---|---|---|
| `onSkipInRead(Throwable t)` | An exception in the reader is skipped. | Exception; there may be no item because reading failed before creating one. |
| `onSkipInProcess(I item, Throwable t)` | An item is skipped due to an exception in the processor. | Input item and exception. |
| `onSkipInWrite(O item, Throwable t)` | An item is skipped due to an exception in the writer. | Output item and exception. |

Example listener:

```java
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderService rejectedOrderService;

    public OrderSkipListener(RejectedOrderService rejectedOrderService) {
        this.rejectedOrderService = rejectedOrderService;
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        rejectedOrderService.recordReadFailure(
                throwable.getMessage(), throwable.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        rejectedOrderService.recordRejectedOrder(
                item.orderId(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        rejectedOrderService.recordWriteFailure(
                item.orderId(), throwable.getMessage());
    }
}
```

Registering the listener on the step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .listener(orderSkipListener)
        .build();
```

The listener captures per-error details, while `StepExecution` counters supply aggregate numbers. The two mechanisms complement each other.

### Notes when recording skips

SkipListener is designed to receive notifications for items that were decided to be skipped. In chunk processing, callbacks fire near commit time to reduce the risk of recording a skip for a chunk that subsequently rolls back. Even so, error persistence must still align with the transaction manager and resources used by `RejectedOrderService`.

If the listener writes to the database in the same chunk transaction, the error record can commit alongside chunk state. If the listener calls an external system or publishes a message, that operation does not roll back automatically with the database. Use an outbox or idempotency mechanism when duplicate transmissions at commit boundaries must be prevented.

For read skips, the listener has no valid item to supply. If you need to identify the file line, extract details from specialized exceptions such as `FlatFileParseException`, which can hold line content and line number, while avoiding logging sensitive data.

## 10. Monitoring skip counts with StepExecutionListener

`StepExecutionListener` lets you inspect counters after a step finishes. It is a convenient place to log summaries or emit metrics.

```java
public class StepSkipSummaryListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepSkipSummaryListener.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Step {} finished: status={}, readSkips={}, " +
                "processSkips={}, writeSkips={}, totalSkips={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getSkipCount());

        return null;
    }
}
```

`afterStep` receives the `StepExecution` of the step that just ended. Returning `null` indicates the listener does not request altering the current `ExitStatus`. If the listener returns another ExitStatus, it can affect flow routing; only do so when there is a clear business requirement.

Registering the listener:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(stepSkipSummaryListener)
        .build();
```

For long-running jobs or separate status dashboards, you can use `JobExplorer` to query `JobExecution` and `StepExecution` instances after metadata is saved. When querying history, use the exact execution ID or identifying parameters so runs are not confused.

## 11. Skip count and COMPLETED status

A step with a `skipCount` greater than 0 can still end with `BatchStatus.COMPLETED`, as long as all skips stay within the allowed policy and remaining work finishes.

Example:

```text
Step: importOrdersStep
BatchStatus: COMPLETED
readCount: 10000
writeCount: 9950
filterCount: 20
readSkipCount: 5
processSkipCount: 15
writeSkipCount: 5
skipCount: 25
```

The step completed according to execution rules, yet that does not mean all input items were written. Operators must read counters and error lists to understand business results.

If business rules require the job to fail upon any skip, or when skips cross a warning threshold lower than `skipLimit`, use listener/flow logic to evaluate the result and set an appropriate ExitStatus. Do not alter BatchStatus arbitrarily just to display a warning; distinguish technical completion from business outcomes with warnings.

## 12. Skip limit and business thresholds

`skipLimit` is a threshold protecting the step from skipping too many items. It is not a target allowance of errors and does not replace error-rate monitoring.

For instance, the same `skipLimit(100)` means very different things for two batches:

- Batch A reads 10,000,000 items and skips 80 items: very low skip rate.
- Batch B reads 200 items and skips 80 items: very high skip rate.

Therefore, beyond absolute limits, the application may need to track:

- Total skipped items.
- Skip rate over items read or processable items.
- Skips per exception type.
- Skips per data source, business group, or partition.
- Skip trends compared to previous runs.

If the skip rate exceeds a business threshold, the job can finish with a custom ExitStatus such as `COMPLETED_WITH_WARNINGS` or `DATA_QUALITY_FAILED`, depending on policy. Define clearly whether that counts as completion with warnings or a failure that must stop downstream workflows.

## 13. How do skip, retry, and rollback differ?

These three mechanisms can appear together in a fault-tolerant step, serving different purposes.

| Mechanism | Behavior | Effect on skip count |
|---|---|---|
| Skip | Bypasses an item due to a permitted exception. | Increments the corresponding skip counter once confirmed skipped. |
| Retry | Re-attempts an operation/item when an exception is considered recoverable. | Does not automatically increment skip count merely for retrying. Only counts as skip if the item is ultimately skipped. |
| Rollback | Undoes the current transaction via the transaction manager. | May cause operations to re-run; does not equate to skip. |

For example, the writer hits a temporary timeout. The step can retry the writer. If the retry succeeds, the item is written and not skipped. If the error persists and the exception is skippable, the item can be skipped per policy. If the error is unskippable or exceeds limits, the step fails.

Do not use skip to hide infrastructure errors that risk losing data. For transient errors, bounded retry is usually better. For unprocessable data errors, skip can work if tracing and reconciliation processes are in place.

## 14. Skipping in the write stage can be complex

The writer receives a chunk rather than a single item. If writing the whole chunk fails, the framework must pinpoint which item caused the error in order to skip the right item. For some writers and exception types, this isolation may require multiple write attempts or rollbacks.

For example, a chunk contains orders A, B, and C. The writer performs a batch insert and the database reports a duplicate key for one order. If the exception does not pinpoint the failing item or the writer cannot separate it, the framework may be unable to isolate the item to skip and the step fails.

To make write skips reliable:

- Exceptions must be clearly classified and configured as skippable.
- The writer should have deterministic behavior when writing a chunk.
- Do not perform side effects outside the transaction without idempotency.
- Verify the writer supports item-level error handling compatible with a fault-tolerant step.
- Test scenarios where a failing item sits in the middle of a chunk and observe actual counters.

If the error is a severe data conflict, skipping the item can mask deeper issues. You may need to route records to quarantine, check existing data, and determine why duplicates occurred.

## 15. Skip counts upon restart

Skip counters belong to one specific `StepExecution`. When a step is restarted, Spring Batch can create a new `StepExecution` for the new execution attempt. Therefore, when reviewing history, distinguish the previous execution's counters from the new execution's counters.

Example:

```text
JobInstance: importOrdersJob / businessDate=2026-11-15

JobExecution #1
  importOrdersStep StepExecution #101
    status = FAILED
    skipCount = 8

JobExecution #2 (restart)
  importOrdersStep StepExecution #205
    status = COMPLETED
    skipCount = 3
```

Do not look at `skipCount=3` of the new execution and conclude the entire run had only 3 skips. If reporting across restarts is required, query the history of related StepExecutions and aggregate them using clear rules.

However, summing counters across every execution also requires care: some items may have been reprocessed after a rollback or restart. Distinguish historical skip events from unique business records rejected. For unique per-record counts, store item IDs and error statuses in a rejected/error table with an appropriate business key.

## 16. Skip counts in partitioning

With partitioning, each worker step has its own `StepExecution` and skip counters. The manager step holds overall orchestration state, but do not assume the manager's `skipCount` automatically sums all worker skips.

Example:

```text
customerManagerStep
  |
  +-- worker partition0: skipCount = 2
  +-- worker partition1: skipCount = 7
  +-- worker partition2: skipCount = 1
```

Total worker skips in the example equal 10. For accurate monitoring, query each partition's `StepExecution` and sum them for the exact JobExecution/worker step. Also retain partition names or partition keys to see which data range concentrates errors.

If a job restarts, break metrics down by execution and partition. Do not mistakenly add the manager's counter to workers' counters or double-count StepExecutions retrieved across multiple queries.

## 17. Skip counts and JobExplorer

`JobExplorer` lets you read persisted metadata. It is the right way to display counters after an execution has been saved to the repository.

Example querying step executions of a job execution:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        System.out.printf(
                "%s status=%s read=%d write=%d filter=%d " +
                "readSkip=%d processSkip=%d writeSkip=%d totalSkip=%d%n",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getFilterCount(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getSkipCount());
    }
}
```

This example demonstrates reading each step's counters. If history across multiple restarts for the same JobInstance is needed, retrieve all JobExecutions belonging to that instance and read each execution's StepExecutions.

When building monitoring APIs, return the step name, execution ID, status, and all three component counters. A single total number does not reveal whether errors come from reading, processing, or writing.

## 18. Persisting skipped errors for reconciliation

Counters give quantities, not which items were skipped. Real applications typically need a store for detailed errors.

A rejected-record table might include columns:

| Column | Purpose |
|---|---|
| `job_execution_id` | Job execution that recorded the error. |
| `step_execution_id` | Specific step that produced the skip. |
| `item_key` | Business key of the item if identifiable. |
| `skip_phase` | `READ`, `PROCESS`, or `WRITE`. |
| `exception_type` | Exception class. |
| `error_message` | Sanitized error details. |
| `created_at` | Recording timestamp. |
| `partition_name` | Processing partition if the step is partitioned. |

For read skips, `item_key` may be unavailable because the reader did not construct an item. In that case, store the file line number or source position if the exception supplies it.

Use an appropriate unique key if the same item could be recorded multiple times across retries/restarts. For instance, keying by execution, step, item key, and error type helps distinguish per-run history from the deduplicated list of rejected business items.

Do not store full sensitive payloads or unbounded stack traces in error tables. Store only the details needed for investigation, with proper access controls and retention periods.

## 19. Flow decisions based on skip count

A job may need to proceed when skip counts stay within limits, yet take a warning branch if skips cross a business threshold. You can use a listener to evaluate counters and return a custom ExitStatus.

Example listener:

```java
public class SkipThresholdListener implements StepExecutionListener {

    private final long warningThreshold;

    public SkipThresholdListener(long warningThreshold) {
        this.warningThreshold = warningThreshold;
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getSkipCount() > warningThreshold) {
            return new ExitStatus("COMPLETED_WITH_WARNINGS");
        }
        return null;
    }
}
```

This example sets a warning threshold less than or equal to the skip limit. It does not replace `skipLimit`; if the skip limit is exceeded during execution, the step fails before finishing. The listener only evaluates the step's skip count after the step completes.

The job flow can route by ExitStatus:

```java
return new JobBuilder("importOrdersJob", jobRepository)
        .start(importOrdersStep)
            .on("COMPLETED_WITH_WARNINGS").to(warningReportStep)
        .from(importOrdersStep)
            .on("COMPLETED").to(successReportStep)
        .from(warningReportStep)
            .on("*").end()
        .from(successReportStep)
            .on("*").end()
        .end()
        .build();
```

This illustrates the flow-control idea. In real applications, declare complete transitions for failure states and determine the job's final status. Do not let a job finish `COMPLETED` if the skip threshold violated a mandatory business requirement.

## 20. Common mistakes when reading and using skip counts

| Issue | Common cause | Resolution |
|---|---|---|
| `skipCount` is 0 even though items were excluded | Processor returned `null`, which is filtering rather than skipping. | Inspect `filterCount` and processor logic. |
| Step FAILED after the Nth skip | Total skips exceeded `skipLimit`. | Check total skips across read/process/write and adjust policy per business rules. |
| Know total skips, not where errors occurred | Reading only `getSkipCount()`. | Read all three component counters and use SkipListener. |
| Read skip has no item to log | Reader failed before constructing an item. | Log exception, line position, or source details if available. |
| Write skip does not behave as expected | Writer receives a chunk and exception cannot isolate failing item. | Check writer, exception, and fault-tolerant behavior. |
| Counter after restart is smaller than history | Looking at the new StepExecution instead of aggregating runs. | Query related JobExecutions/StepExecutions and aggregate systematically. |
| SkipListener writes duplicate errors | Non-idempotent listener side effect or overlooked transaction boundaries. | Use deduplication key or outbox and store execution/item identity. |
| Job COMPLETED yet data is missing | Skips stayed within limit so the step still completed. | Inspect counters, skip rate, and business output. |
| Too many skips without stopping | Skippable exception list is too broad or skip limit does not reflect requirements. | Narrow skippable exceptions and set clear thresholds. |

## 21. Workflow for analyzing a step with high skip counts

When a step has an abnormal skip count, investigate in order:

1. **Identify execution:** obtain the corresponding JobExecution ID, StepExecution ID, and JobInstance.
2. **Read status:** inspect `BatchStatus`, `ExitStatus`, timestamps, and last exception.
3. **Break down counters:** inspect `readSkipCount`, `processSkipCount`, `writeSkipCount`, and `filterCount`.
4. **Review skip policy:** check which exceptions are skippable and the current `skipLimit`.
5. **Look up error details:** use SkipListener outputs or the rejected-record table to find items, file lines, and exceptions.
6. **Compare with input data:** determine whether errors stem from data quality, mapping, business rules, or target systems.
7. **Evaluate ratios:** compare skip counts against total items and previous runs.
8. **Check restart/retry:** determine if any items were reprocessed or errors recorded multiple times.
9. **Decide remediation:** fix source data, adjust rules, retry transient errors, or send items to reconciliation.
10. **Monitor the next run:** confirm counters drop to expected levels and failing data was addressed.

Do not raise `skipLimit` merely to push a job through. If errors stem from a malformed file structure, database disconnection, or writer schema mismatch, raising the limit can let the job continue while output data is no longer trustworthy.

## 22. Key points to remember

- `StepExecution` stores `readSkipCount`, `processSkipCount`, `writeSkipCount`, and total `skipCount`.
- `skipCount` is the sum of skips in read, process, and write stages.
- Filtering by a processor returning `null` counts toward `filterCount`, not skip count.
- `skipLimit` applies jointly across all three stages; exceeding it fails the step.
- Skip applies only to exceptions permitted by policy; system errors should not be skipped arbitrarily.
- `SkipListener` provides dedicated callbacks for read, process, and write to record error details.
- `StepExecutionListener.afterStep` can read counters for logging or evaluating warning thresholds.
- `BatchStatus.COMPLETED` can still accompany a non-zero skip count if policy allows.
- Counters belong to one specific StepExecution; across restarts, check execution history to aggregate over multiple runs.
- In partitioning, each worker has its own counters; to get totals, sum StepExecutions of the partitions in scope.
- Retry and rollback do not automatically equate to skip; only items decided to be skipped increment skip counters.
- Persist skipped item details and causes for reconciliation, data correction, and quality reporting.

When monitoring a batch job, examine total `skipCount` as well as all three component counters, `filterCount`, step status, and detailed error lists. Together, these tell you where items were dropped, why the step succeeded or failed, and whether the output meets business requirements.

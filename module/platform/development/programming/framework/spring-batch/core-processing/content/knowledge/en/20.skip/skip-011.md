# Skip upon restart

In Spring Batch, **skip** allows a Step to bypass an item when the error belongs to a skippable type and the skip count has not exceeded the configured limit. When a Job fails due to another error or because the skip limit was exceeded, the application can restart the same JobInstance. Upon restart, Spring Batch relies on metadata, Step state, and committed checkpoints to determine which work needs to resume.

It is important to distinguish an item skipped inside a committed chunk from an item that failed inside a rolled-back chunk. An item skipped within committed work usually lies before the checkpoint and is not reread upon restart. If the chunk did not commit, read state and chunk changes may roll back; upon restart, items in that chunk may be read and processed again, causing the skip decision to occur once more.

## 1. What is skip in Spring Batch?

In a chunk-oriented Step, errors can occur while reading, processing, or writing an item. If the exception is configured as skippable and the skip limit has not been exceeded, Spring Batch can discard the failing item and continue processing the remaining items.

Three primary skip locations:

- **Read skip:** `ItemReader` throws an exception while reading data, such as a malformed file line.
- **Process skip:** `ItemProcessor` throws an exception for an invalid item.
- **Write skip:** `ItemWriter` throws an exception while writing an item or group of items; for batch writers, the framework must isolate the failing item using an appropriate mechanism.

Example configuring a Step allowing up to 10 data errors to be skipped:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, ProcessedOrder> processor,
        ItemWriter<ProcessedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(10)
            .build();
}
```

The example assumes `Order`, `ProcessedOrder`, and `InvalidOrderException` are application types. `FlatFileParseException` represents a file line parsing error. Exceptions not classified as skippable fail the Step according to the error-handling policy.

## 2. Skip vs. filter and retry

These three mechanisms serve different purposes:

| Mechanism | How it works | Related counters |
|---|---|---|
| Filter | Processor returns `null`; item is excluded from the pipeline without an exception. | `filterCount` |
| Skip | Reader, Processor, or Writer throws an exception permitted to be bypassed. | `readSkipCount`, `processSkipCount`, `writeSkipCount`, `skipCount` |
| Retry | Framework re-attempts a failing operation, typically for transient errors. | Retries are managed by the retry policy; not skip counts |

Examples:

- Cancelled order with valid data: processor returns `null` to filter.
- Unparseable CSV line allowed to be discarded: read skip.
- Nonexistent customer ID allowed to be discarded: process skip.
- Temporary database deadlock: retry before deciding whether to continue or fail.

Do not return `null` just to avoid Job failure if the record is truly invalid and needs to be recorded. Conversely, do not throw an exception for a normal business filtering condition.

## 3. How is skip limit applied?

`skipLimit(n)` sets the cap on total skips for a Step execution, summed across skippable errors in read, process, and write stages. While the skip count remains within the limit, failing items are bypassed. When a subsequent skippable error exceeds the limit, the Step fails.

Example with `skipLimit(10)`:

| Accumulated skips in Step execution | Outcome |
|---:|---|
| 0 to 9 | Subsequent skippable errors can be skipped. |
| 10 | The 10th error is still within the limit and is skipped. |
| 11 | Next error exceeds the limit; Step fails. |

The limit applies jointly across read, process, and write skips, not 10 errors per stage. Thus, 4 read skips, 3 process skips, and 3 write skips total 10.

Skip limit does not mean every exception is bypassed. You must declare which exception types are skippable; exceptions outside the policy fail the Step. You can use `.noSkip(...)` to exclude an exception type from a broader declared skip group.

Operationally, treat skip limit as the limit for the current Step execution. If business rules require a cumulative cap across multiple restarts or multiple JobExecutions, persist a durable business counter keyed by batch/JobInstance and check it separately; do not rely solely on `skipLimit`.

## 4. What is saved when a chunk commits?

Spring Batch persists execution metadata and state needed for restart through `JobRepository`. For a reader implementing `ItemStream`, `update(ExecutionContext)` can save a checkpoint, such as the current read position. State is persisted at commit boundaries aligned with the chunk transaction.

Example of a Step reading a file with `FlatFileItemReader`:

```java
FlatFileItemReader<Order> reader =
        new FlatFileItemReaderBuilder<Order>()
                .name("orderFileReader")
                .resource(new FileSystemResource("data/orders.csv"))
                .delimited()
                .names("id", "customerId", "amount")
                .targetType(Order.class)
                .saveState(true)
                .build();
```

`saveState(true)` lets the reader persist information needed to restore the read position on restart. With restart-capable readers, checkpoints usually reflect the position processed up to the most recent commit boundary.

A chunk may contain both valid items and skipped items. When the chunk commits successfully, the chunk's data changes and corresponding checkpoint are saved. On restart, the reader normally resumes after that checkpoint; items already processed in committed chunks, including skipped items, do not need to be reread.

## 5. Skip in committed chunks vs. rolled-back chunks

This is the most important distinction when understanding skip during restart.

### Case A: chunk with skips commits

Suppose chunk 1 has 5 items, where the 3rd item is invalid and skipped. The writer persists the remaining valid items; the chunk commits successfully:

```text
Chunk 1
  Item 1 -> written
  Item 2 -> written
  Item 3 -> SKIP
  Item 4 -> written
  Item 5 -> written
       |
       v
    COMMIT
       |
       +--> Written data is retained
       +--> Checkpoint is updated
       +--> Skip already belongs to completed work
```

If the Job fails in chunk 2 and later restarts, the reader can continue after chunk 1's checkpoint. The 3rd item is not reread in a normal restart because the chunk containing it already completed and its checkpoint was saved.

### Case B: chunk does not commit and rolls back

Suppose an item in the chunk is skipped, but then the Writer encounters an unskippable error and fails the chunk transaction:

```text
Chunk 2
  Item 6 -> tentatively written
  Item 7 -> SKIP
  Item 8 -> tentatively written
  Item 9 -> unskippable error
       |
       v
    ROLLBACK
       |
       +--> Chunk's business changes are undone
       +--> New checkpoint was not committed
       +--> Chunk may be reread/reprocessed upon restart
```

After rollback, durable state remains at the previous chunk's checkpoint. On restart, the reader can reread items in chunk 2. Item 7 may fail again and be skipped once more. Therefore, systems persisting reject records or emitting skip notifications need deduplication.

### Summary table

| Situation | Checkpoint | Can skipped item reappear? |
|---|---|---|
| Chunk with skips commits successfully | Updated to the commit boundary | Normally no, if the reader restores the checkpoint properly. |
| Chunk with skips subsequently rolls back | Retains previous committed chunk's checkpoint | Yes, because the item belongs to the chunk that must be reread. |
| Stateless reader (no state saved) | No reliable read checkpoint | May reread much or all data; writer must be idempotent. |
| Job/Step designed to rerun from start | Depends on configuration and data initialization | Yes, requires explicit deduplication policy. |

## 6. Restarting a Job after Step failure

When a Job fails, Spring Batch preserves JobInstance, JobExecution, and StepExecution metadata. If the Job permits restarts, you can relaunch the same Job with the same identifying JobParameters. Spring Batch creates a new JobExecution for the same JobInstance and executes Steps according to prior state.

Example:

```text
JobInstance: importOrders / fileId=orders-2026-11-15
  |
  +--> JobExecution #1: FAILED
  |       importOrdersStep: FAILED
  |       Chunk 1: COMMITTED (with 1 skip)
  |       Chunk 2: ROLLED BACK
  |
  +--> JobExecution #2: COMPLETED
          importOrdersStep: resumes from committed checkpoint
          Chunk 1: not reread in normal restart
          Chunk 2: reread/reprocessed per reader state
```

Prerequisites:

- The Job is not configured with `preventRestart()`.
- The failed Step is restartable.
- The reader supports saving/restoring state if resuming from a checkpoint.
- Reader names remain stable across runs.
- The same identifying JobParameters are used to restart the right JobInstance.
- The writer and side effects can handle re-execution safely.

A `COMPLETED` Step is normally skipped on restart. If `allowStartIfComplete(true)` is configured, a completed Step can rerun; in that case, previously skipped items may also be encountered again depending on the reader and source data.

## 7. Skip count and StepExecution metadata

Spring Batch tracks skip counters on `StepExecution`:

| Property | Meaning |
|---|---|
| `getReadSkipCount()` | Number of read errors skipped in this StepExecution. |
| `getProcessSkipCount()` | Number of process errors skipped. |
| `getWriteSkipCount()` | Number of write errors skipped. |
| `getSkipCount()` | Total skip count. |
| `getReadCount()` | Number of items read. |
| `getWriteCount()` | Number of items written. |
| `getFilterCount()` | Number of items filtered by processor returning `null`. |
| `getRollbackCount()` | Number of rollbacks recorded. |

Counters help investigate a single Step execution. Upon restart, distinguish old StepExecutions from new StepExecutions: each execution has its own metadata. If you need a report of total skipped records across a JobInstance's full history, aggregate related StepExecutions in JobExplorer/JobRepository or persist business metrics in a separate audit table. Do not read only the latest execution's skip count and treat it as the total skips across all runs.

Example reading counters after a Step completes:

```java
for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
    System.out.printf(
            "step=%s, readSkip=%d, processSkip=%d, writeSkip=%d, totalSkip=%d%n",
            stepExecution.getStepName(),
            stepExecution.getReadSkipCount(),
            stepExecution.getProcessSkipCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getSkipCount());
}
```

To aggregate across multiple JobExecutions of the same JobInstance, fetch the corresponding historical executions and sum StepExecution counters according to your report definition. Avoid summing reruns of the same chunk if the report intends to count unique rejected business records rather than total skip occurrences.

## 8. Recording skipped items with SkipListener

`SkipListener` provides dedicated callbacks for read, process, and write skips. It is the appropriate place to log failing records, store causes, or route items into a reject flow.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class OrderSkipListener
        implements SkipListener<Order, ProcessedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Skipping unreadable input: {}", throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable throwable) {
        log.warn("Skipping order {} during processing: {}",
                item.id(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(ProcessedOrder item, Throwable throwable) {
        log.warn("Skipping order {} during writing: {}",
                item.id(), throwable.getMessage());
    }
}
```

Registering the listener on the Step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(10)
        .listener(orderSkipListener)
        .build();
```

`onSkipInRead()` receives no item because the Reader may fail before producing a complete object. With `FlatFileParseException`, you can extract input line details from the exception if reject content must be saved, while limiting sensitive data and log size.

## 9. Avoiding duplicate reject writes on restart

SkipListener can be invoked again if a chunk rolls back and items are reread/reprocessed upon restart. Therefore, do not assume a callback corresponds to a single unique error record across the entire JobInstance lifecycle.

For example, a listener writes rejects to a `batch_reject` table:

```text
batch_reject
-------------------------------------------------
job_instance_key | source_record_key | error_code
-------------------------------------------------
2026-11-15       | ORD-1007           | INVALID_AMOUNT
```

You can place a unique key on the combination of JobInstance key and source record key. When the same item is skipped again after a restart, the reject write uses upsert or controlled insert so no duplicate row is created.

Design options:

1. **Unique key and upsert:** identify rejects by JobInstance/partition/source key and update error info if needed.
2. **Transactional write:** write rejects inside the chunk transaction when resources and transaction manager allow, so reject records roll back with the chunk.
3. **Outbox:** write reject events inside the business transaction and dispatch to external systems after commit.
4. **Idempotency key:** when sending errors to APIs or message brokers, use a unique key so receivers deduplicate repeated events.

If the listener writes files or sends emails directly, those side effects do not automatically roll back with the database transaction. When a chunk rolls back, reruns can produce duplicate files/emails. Decouple notifications from callbacks or use durable deduplication.

## 10. Combining retry and skip on restart

Retry is typically for transient errors, while skip is for permitted item errors. An exception can be retried first; if retries exhaust and the exception belongs to the skippable group, the item can be skipped. If the exception is neither retried nor skipped, the Step fails.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(10)
        .listener(orderSkipListener)
        .build();
```

This example retries transient data-access errors up to the configured limit and skips invalid order errors. When the Job restarts, items in committed chunks are not reprocessed if checkpointing works properly; items in rolled-back chunks can be retried and pass through the retry/skip policy again.

Do not use retry for non-self-healing data errors such as a malformed customer ID. Nor should you immediately skip transient infrastructure errors if a retry could resolve them. Clear exception classification makes Job restart behavior predictable.

## 11. Custom SkipPolicy

When skip rules are more complex than a fixed exception list, you can implement `SkipPolicy`. The policy receives the exception and current skip count, then decides whether skipping is permitted.

```java
import org.springframework.batch.core.step.skip.SkipLimitExceededException;
import org.springframework.batch.core.step.skip.SkipPolicy;

public class BusinessSkipPolicy implements SkipPolicy {

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException) {
            return skipCount < 10;
        }

        return false;
    }
}
```

Registering the policy:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new BusinessSkipPolicy())
        .build();
```

When using `skipPolicy`, the policy itself decides skip conditions and limits. Do not simultaneously configure `skip()`/`skipLimit()` rules in a way that creates confusion about precedence. Custom policies need unit tests for exception types, skip thresholds, and behavior when exceeding thresholds.

If a threshold must accumulate across multiple restarts, the policy may need to query a durable state store keyed by JobInstance/batch ID. Avoid using a mutable `long skipCount` field in a singleton because concurrent JobExecutions or restarts can corrupt the count.

## 12. Cases where a Step does not rerun on restart

Restart does not mean the entire Job always restarts from the first Step. Spring Batch checks Step statuses from the prior JobExecution:

- A `COMPLETED` Step is normally skipped during restart.
- A failed Step can be rerun if the Job and Step allow restarts.
- A Step with `allowStartIfComplete(true)` can rerun even if it completed previously.

How this affects skips:

- If a Step containing skips completed and is skipped on restart, items skipped in that Step are not reread merely because the Job restarted.
- If the Step reruns due to `allowStartIfComplete(true)` or a new JobInstance, data may be reread and failing items may be skipped again.
- If the Step failed in an uncommitted chunk, items in that chunk may be reprocessed from the latest checkpoint.

Enable `allowStartIfComplete(true)` only when the Step can safely run repeatedly. For Steps sending notifications, creating files, or updating external data, establish idempotency or a clear overwrite policy.

## 13. Testing skip and restart

Unit tests for processors or SkipPolicy verify which exceptions are skipped. Integration tests must verify checkpoints, skip counts, reject data, and Job status after restart.

A useful test scenario:

1. Prepare a file with a valid item, a skippable malformed item, and an item causing an unskippable writer failure.
2. Run the Job the first time; verify the chunk before the failure committed, the chunk containing the writer error rolled back, and the Job ended `FAILED`.
3. Verify `StepExecution` saved read/process/write skip counts and checkpoint for that execution.
4. Fix the writer condition so the next run can complete.
5. Restart the same JobInstance using the exact same identifying JobParameters.
6. Verify the reader resumes from the committed checkpoint, items from the rolled-back chunk are reprocessed, and items skipped in committed chunks are not reread.
7. Verify the reject table contains no duplicate rows even if callbacks re-executed for items in the rolled-back chunk.

With Spring Batch Test, `JobLauncherTestUtils` can launch a Job or Step; `JobExplorer`/`JobRepository` help inspect JobExecutions and StepExecutions after each run. When testing restarts, do not add a new UUID identifying parameter between launches because that creates a different JobInstance.

Assertions should include:

- `BatchStatus` and `ExitStatus` of each JobExecution.
- Read/process/write skip counts of each StepExecution.
- Checkpoint or output data after commit.
- Unique reject record count by business key.
- Same JobInstance ID and different JobExecution IDs between the initial run and restart.

## 14. Common mistakes

| Mistake | Cause | Resolution |
|---|---|---|
| Assuming a skipped item never reappears | Item was in a rolled-back chunk or the Step reran. | Distinguish committed skips from skips in uncommitted chunks; make reject persistence idempotent. |
| Treating `skipLimit` as a limit across all JobInstance history | Skip limit applies per Step execution; each execution has separate metadata. | Manage a cumulative business threshold separately if required. |
| Confusing filter with skip | Processor returning `null` is not an exception skip. | Check `filterCount` and skip counts separately. |
| Skipping all exceptions | Infrastructure errors or programming bugs may be hidden. | Only skip specific data exceptions; let critical errors fail the Step. |
| Reject listener writes duplicates after restart | Side effect occurred while chunk didn't commit or callback fired again. | Use a unique key, upsert, outbox, or idempotency key. |
| Stateless reader | Restart may reread from the beginning or fail to restore position. | Use a reader supporting `ItemStream` and save checkpoints. |
| Changing identifying JobParameters on restart | Spring Batch creates a new JobInstance. | Keep identifying parameters identical to restart the right instance. |
| Reading only the newest execution's skip count | Ignores skip history from prior executions. | Aggregate historical StepExecutions or use a business audit table. |

## Conclusion

Skip behavior upon restart depends on Step commit boundaries and checkpoints. Items skipped inside committed chunks normally lie behind the checkpoint and are not reread on a standard restart. Items belonging to rolled-back chunks can be reread and skipped again because durable state remains at the prior checkpoint. Therefore, distinguish skip from filter and retry, configure explicit exceptions and skip limits, use state-saving readers, and persist rejects idempotently. When skips must be bounded across multiple restarts, maintain a durable business counter rather than relying solely on a single Step execution's skip limit.

# A chunk with fewer items than the commit interval

In Spring Batch, `commit-interval` defines the number of items a chunk aims to process before the transaction is committed. However, **not every chunk must have as many items as the commit interval**. The most common case is the last chunk: when `ItemReader` reports no more data before the threshold is reached, Spring Batch still processes and commits the remaining items as a smaller chunk.

For example, a Step has `commit-interval = 100` but the source has only 237 records. Spring Batch processes two full chunks of 100 items and a last chunk of 37 items. The last chunk is still processed in its own transaction and is committed when processing succeeds.

Understanding this behavior correctly helps design the reader, writer, transaction, checkpoint, and monitoring metrics more accurately. It also helps avoid confusion between the number of items read, the number of items the processor keeps, and the number of items the writer actually writes.

## 1. The commit interval is the chunk size threshold

In chunk-oriented processing, Spring Batch performs a cycle of reading items, processing items, writing the results, and then committing the transaction. `commit-interval` is the number of items the framework gathers into a chunk before ending the normal commit cycle.

An example Step configuration with a chunk size of 100:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

With this configuration, Spring Batch tries to read 100 items for a chunk. The framework then processes the items, calls the writer with the remaining results, and completes the chunk's transaction. When EOF is reached sooner, the framework processes the data already read as the last chunk.

Therefore, `100` is the target size of a chunk, not a requirement that every chunk have exactly 100 items. The actual size can be smaller, especially at the end of the data source or when some items are filtered.

## 2. The last chunk has fewer items than the commit interval

Suppose the data source has 237 orders and the Step uses a commit interval of 100. The reader returns orders one at a time; when there are no more items, `read()` returns `null` to signal the end of data.

```text
Total input items:  237
Commit interval:    100

Chunk 1: 100 items  -> process -> write -> commit
Chunk 2: 100 items  -> process -> write -> commit
Chunk 3:  37 items  -> process -> write -> commit
                                  |
                                  +--> Reader reports EOF
```

| Chunk | Items read | Result |
|---|---:|---|
| Chunk 1 | 100 | Process and commit |
| Chunk 2 | 100 | Process and commit |
| Chunk 3 | 37 | Process and commit as the last chunk |
| Total | 237 | 3 chunks |

When the reader returns `null` after the 237th item, Spring Batch knows the source has ended. The 37 items in the chunk are not discarded just because they have not reached 100. The framework continues to process and write this data, then commits the transaction if no error causes the chunk to fail.

If the total number of items is exactly a multiple of the commit interval, for example 200 items with an interval of 100, there will be two full chunks of 100. When the framework starts reading the next chunk and the reader immediately returns `null`, the Step ends without a final data chunk to write.

## 3. Why can the reader end before a chunk is full?

In the `ItemReader` contract, returning `null` means there are no more items to read. Spring Batch uses this signal to end chunk creation. If the number of items read in the current chunk is smaller than the commit interval, the remainder is the last chunk.

A simple reader example:

```java
public class ListOrderReader implements ItemReader<Order> {

    private final Iterator<Order> iterator;

    public ListOrderReader(List<Order> orders) {
        this.iterator = orders.iterator();
    }

    @Override
    public Order read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
```

If the list has 237 elements, `read()` returns 237 items and then returns `null`. With a chunk size of 100, Spring Batch creates two full chunks and a last chunk of 37 items.

The key point is that `null` carries the meaning of EOF. For a data source that temporarily has no items but may have more data later, you should not return `null` to mean "there is no data right now"; doing so tells Spring Batch that the Step has run out of input. A reader for a streaming source or a source that arrives over time needs a waiting mechanism, retry, or its own reading protocol appropriate to the data source.

## 4. The input chunk and the number of items written can differ

Another reason the writer receives fewer items than the commit interval is that `ItemProcessor` can filter items. When the processor returns `null`, Spring Batch understands that the item is excluded from the output and does not pass it to the writer.

For example:

```java
@Component
public class EligibleOrderProcessor implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (!isEligible(order)) {
            return null; // Filter the item, not a skip due to an exception.
        }

        return normalize(order);
    }

    private boolean isEligible(Order order) {
        return order.getTotalAmount().signum() > 0;
    }

    private Order normalize(Order order) {
        // Normalize the data before writing.
        return order;
    }
}
```

Suppose a chunk reads a full 100 items, but the processor drops 10 items. The writer receives only 90 items. The input chunk size is still 100; the number of output items is smaller because of the filter.

| Chunk metric | Illustrative quantity | Meaning |
|---|---:|---|
| Items read | 100 | The reader supplied a full chunk |
| Items filtered | 10 | The processor returned `null` for 10 items |
| Items passed to the writer | 90 | The results remaining after processing |

If all items in a chunk are filtered, the writer has no items to write and Spring Batch does not need to call the writer with an empty output chunk. Filtering is still different from skip: filtering is the processor's normal business decision; skip relates to exceptions configured to be ignored during reading, processing, or writing.

Therefore, when you see the writer receiving fewer items than the commit interval, determine whether it is the last chunk due to EOF, the result after the processor filters, or items skipped by configuration.

## 5. The transaction of a small chunk is still committed per chunk

A last chunk with 37 items does not mean Spring Batch has to open 37 transactions or commit each item individually. It is still a chunk and is processed in that chunk's transaction.

```text
Last chunk's transaction
       |
       +--> Read the remaining 37 items
       |
       +--> Process 37 items
       |
       +--> Writer writes the remaining results
       |
       +--> Commit transaction
```

If processing and writing succeed, the transaction is committed. If the writer or another component throws an exception that makes the transaction fail, the current chunk's transaction can roll back according to the Step's transaction and fault-tolerance configuration.

Chunks committed earlier keep their results. For example, if chunk 1 and chunk 2 have committed but the last chunk fails, the rollback of the last chunk does not automatically undo the previous two chunks. On restart, Spring Batch relies on the saved metadata and checkpoint to continue according to the design of the reader/Step.

This is an important characteristic of chunk processing: the commit interval defines the transaction boundary by group of items, and the last chunk can be smaller than the target group while still having its own commit boundary.

## 6. Effects on checkpoint and restart

With a stateful reader, Spring Batch can save progress in the Step `ExecutionContext` at commit boundaries. When the Step is restarted, the reader restores the saved checkpoint and continues reading from an appropriate position.

Suppose there are 237 items and a commit interval of 100:

1. Chunk 1 processes 100 items and commits; the checkpoint is updated.
2. Chunk 2 processes 100 items and commits; the checkpoint is updated again.
3. The last chunk processes 37 items but the writer hits an error before commit.
4. The last chunk's transaction rolls back; the checkpoint of the uncommitted chunk is not considered completed progress.
5. On restart, the reader continues from the checkpoint of the last committed chunk and reprocesses the part that was not completed.

The reader needs to implement an appropriate state save/restore mechanism, usually through `ItemStream` or the built-in readers that support restart. Do not keep the read position only in a field of a singleton bean, because in-memory state can be lost when the application restarts and can be shared across executions.

For an input source that can change, the checkpoint should be based on a stable identifier such as an ID or an offset, not only on a position if the position can shift. The checkpoint design must ensure that the data re-read after a restart matches the business data that has been committed.

## 7. Distinguishing filter, skip, and the last chunk

Three scenarios can make the number of items the writer writes smaller than the commit interval, but with different causes:

| Scenario | Cause | How to interpret |
|---|---|---|
| Last chunk | The reader returns `null` before the commit interval is reached | No more data; the remaining items are still processed and committed |
| Filter | The processor returns `null` for an item | The item is read but not passed to the writer |
| Skip | An exception configured to be skipped | The failing item is handled per the skip policy; the number of items written may decrease |

For example, a chunk has 100 input items, 5 items are filtered, and 2 items are skipped by configuration. The number of items passed to the writer could be 93. This number does not mean the commit interval has changed to 93; it reflects the processing result of that chunk.

Skip and retry can cause the framework to re-read, re-process, or re-write some items depending on the error type and the fault-tolerant configuration. Therefore, do not try to infer exactly how many times the reader/processor/writer was called from the final chunk size alone.

## 8. Reading StepExecution metrics

`StepExecution` provides counters that are useful for observing the number of items and transactions. Some commonly used metrics:

| Metric | General meaning |
|---|---|
| `readCount` | Number of items read successfully |
| `writeCount` | Number of items written successfully |
| `filterCount` | Number of items filtered by the processor |
| `readSkipCount` | Number of items skipped due to errors in the read phase |
| `processSkipCount` | Number of items skipped due to errors in the processing phase |
| `writeSkipCount` | Number of items skipped due to errors in the write phase |
| `commitCount` | Number of transaction commits recorded for the Step |
| `rollbackCount` | Number of rollbacks recorded for the Step |

You can read these metrics after the Step executes:

```java
public class ImportStepListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "step={}, read={}, written={}, filtered={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getFilterCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

Do not assume `readCount` always equals `writeCount`, or that `writeCount` always equals `commitInterval × commitCount`. Filters, skips, a last chunk smaller than the threshold, rollbacks, and retries can all make the metrics differ. Read the counters according to their proper meaning instead of using one counter to infer everything.

## 9. Choosing an appropriate commit interval

A last chunk smaller than the commit interval is normal behavior, not a sign of misconfiguration. When choosing the commit interval, consider other factors:

- **Transaction cost:** a large chunk reduces the number of commits but holds the transaction and resources longer.
- **Memory:** a large chunk needs to hold many items in memory before writing.
- **Rollback capability:** an error in a chunk can cause many items of that chunk to be reprocessed.
- **Load on the writer and database:** the chunk size affects the number of items sent in each write.
- **Checkpoint latency:** a large commit interval can make checkpoints sparser, so a restart has to reprocess more after an incident.
- **Nature of the data source:** files, database cursors, APIs, and message streams have different read/write characteristics.

For example, an interval of 100 may suit a writer that supports batch insert. But if each item creates a slow I/O operation or the transaction holds locks for a long time, measure and try a smaller size. There is no need to try to make the final item count divisible by the interval; Spring Batch already handles an incomplete last chunk.

## 10. Common misconceptions

**Believing every chunk must be as large as the commit interval.** The last chunk is allowed to have fewer items when the reader reports EOF. The remaining data is still processed as a chunk.

**Believing a smaller chunk will be skipped.** Spring Batch processes and commits the last items if the process completes successfully.

**Believing the writer always receives exactly the number of items the reader read.** The processor can filter items by returning `null`; skips can also reduce the number of items written.

**Using `null` to signal that the source temporarily has no data.** For an ItemReader, `null` means there are no more items and the end of the Step's input. A data source that may keep producing data needs a different suitable reading mechanism.

**Believing a small last chunk commits item by item.** The last chunk is still a unit of processing and a chunk transaction; having fewer items does not change the commit model.

**Comparing readCount and writeCount as two numbers that must be equal.** Filters, skips, and processing errors make the two counters differ. Look further at the filter/skip counts and the Step status.

## 11. The right way to understand it in operations

When you observe a Step with a commit interval of 100 but the writer receives 37 items the last time, check whether the input source has a total of 237 items. If so, this may be just the last chunk after EOF. If the reader has read a full 100 but the writer receives only 90, check whether the processor filters 10 items. If there are exceptions, look at the skip/retry policy, the rollback count, and the checkpoint to understand the actual result.

`commit-interval` specifies the target size of a chunk and the commit boundary per group. Spring Batch still processes the remaining data when the source ends before the threshold. Distinguishing the input chunk size from the number of output items, and understanding transactions and checkpoints, will help you design the Step and read operational metrics accurately.

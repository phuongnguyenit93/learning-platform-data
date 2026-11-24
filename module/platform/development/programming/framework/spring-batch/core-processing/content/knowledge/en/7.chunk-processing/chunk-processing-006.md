# Empty chunks and end of input in Spring Batch

In chunk-oriented processing, Spring Batch reads data in groups of items, processes that group, and then writes the results within a transaction boundary. A job does not always receive the full number of items as configured. The source may have no data from the start, only a small remainder may be left in the last chunk, or the processor may drop all the items in a chunk.

These cases need to be clearly distinguished. **End of input** is a signal from `ItemReader` that there are no more items to read. **A last chunk smaller than the commit interval** is a valid chunk. **An input chunk with no items** can occur when the source is empty. And an **empty output chunk** can appear when the processor filters out all the items that were read. These cases have different effects on the counters, the writer, the step status, and restartability.

## 1. Chunks and the commit interval

A chunk is a group of items that are read, processed, and written in one transaction. With the configuration:

```java
new StepBuilder("importOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .build();
```

`100` is the commit interval: the step tries to gather up to 100 input items for one chunk-processing pass before committing. This is not a commitment that the source must have exactly 100 items, nor is it the minimum size of a chunk.

If the source has 37 items left and then ends, Spring Batch still processes those 37 items in the last chunk and commits according to the chunk's transaction boundary. If the source has no items at all, the step does not need to wait for 100 items; the reader reports no more data and the step can complete normally.

A typical processing cycle can be pictured as follows:

```text
ItemReader
    |
    v
Read up to commit-interval items
    |
    v
ItemProcessor for each item
    |
    v
ItemWriter writes the remaining outputs
    |
    v
Commit transaction
    |
    v
Read the next chunk
```

In the last chunk, the reader may detect EOF before gathering the configured number. The items read before the EOF signal are still processed. The end signal does not discard the valid portion of the chunk that has already been read.

## 2. ItemReader signals end of input with null

The contract of `ItemReader<T>.read()` is to return the next item or to return `null` when there are no more items. Spring Batch uses `null` as the signal for the end of the data source (end of input/end of file, commonly abbreviated EOF).

An example of a simple reader that reads from an iterator:

```java
public class OrderReader implements ItemReader<Order> {

    private final Iterator<Order> iterator;

    public OrderReader(List<Order> orders) {
        this.iterator = orders.iterator();
    }

    @Override
    public Order read() {
        if (!iterator.hasNext()) {
            return null;
        }
        return iterator.next();
    }
}
```

When `read()` returns `null`, Spring Batch understands that the reader has run out of data. The step ends the reading phase and moves on to finishing the remaining work of the last chunk, if any. `null` is not an item to pass to the processor or writer.

In a real job, readers such as `FlatFileItemReader`, `JdbcCursorItemReader`, or custom readers all follow this meaning: return an item while data remains and return `null` when the source has ended. The details of EOF detection depend on the reader type and the data source.

Do not use `null` to represent a valid business record. If the source data has a notion of an empty value, represent it with a non-null object, for example a DTO with empty fields, an empty string, or an appropriate wrapper type. In the `ItemReader` contract, `null` is reserved for the signal that there is no more data.

## 3. Distinguishing EOF from an item with an empty value

An item that is empty in the business sense is not necessarily EOF. For example, if the reader returns an empty string `""`, an object with blank fields, or an empty collection, Spring Batch still treats it as an item because the returned value is not `null`.

| Value from `ItemReader.read()` | How Spring Batch interprets it |
| --- | --- |
| A valid object | There is a new item; pass the item to the processor if configured. |
| Empty string `""` | An item of type `String` with an empty value. |
| Empty collection | An item that is an empty collection, if the reader's item type is a collection. |
| `null` | No more items; the reader has ended the input. |
| Throws an exception | An error occurred while reading; handle per the retry/skip configuration or fail the step. |

This difference is very important with CSV files. A blank line in a file may be mapped by the reader to an empty string or handled according to the tokenizer/line mapper configuration. A blank line does not automatically mean the whole file has ended. Only when the reader has no more lines to read and returns `null` does Spring Batch receive the EOF signal.

If a custom reader returns `null` because of an error parsing a line, the step may end early without reporting an error. Therefore, clearly distinguish normal end of data from corrupted data. A parse error should be expressed with an appropriate exception so that the skip, retry, or fail policy can handle it.

## 4. The last chunk smaller than the commit interval

Suppose the commit interval is 100 but the source has 237 items. The reading and committing process looks like this:

```text
Chunk 1: items 1..100       -> 100 items -> commit
Chunk 2: items 101..200     -> 100 items -> commit
Chunk 3: items 201..237     ->  37 items -> commit
Reader reads again          -> null (EOF)
Step completes
```

A last chunk with 37 items is still a normal chunk. Spring Batch does not require the number of items in the last chunk to equal the commit interval. The reader detects EOF, but the items already read in the last chunk are still passed through the processor and writer according to the step's configuration.

If the total number of items is divisible by the commit interval, for example 200 items with an interval of 100, two full chunks are processed. On the next read, the reader returns `null`; there are no more items to form a new business chunk. The step ends after completing the necessary transactions.

Do not add a dummy item yourself to fill the last chunk. That could cause the writer to write data that does not exist or throw off the counters. The chunk size is the limit of a processing group, not the number of records the source must supply.

## 5. Empty input from the start

If the source has no items, the first `read()` call returns `null`. The step can still run and complete normally:

```text
Start step
    |
    v
ItemReader.read()
    |
    +---- returns null
              |
              v
          No items
              |
              v
         Step COMPLETED
```

For a standard chunk step, this case usually has these characteristics:

- The step's `BatchStatus` is `COMPLETED` if there are no other errors.
- `readCount` is 0 because no items were read.
- `writeCount` is 0 because no items were written.
- The processor is not called because there are no input items.
- The writer has no output to write and is not called for an empty data chunk under the default chunk handling.

The job continues according to the configured flow. If this step is the last step, the job can end with `BatchStatus.COMPLETED`. Therefore, **having no data is not implicitly a technical error**. Whether empty input is a valid business outcome depends on the application's requirements.

For example, a job that aggregates revenue by day may accept a day with no transactions. But a reconciliation job that requires an input file may need to treat an empty file as a business error. Express that rule explicitly instead of relying on the assumption that Spring Batch will automatically treat empty input as a failure.

## 6. Distinguishing an empty input chunk from an empty output chunk

A chunk can have input items but no output items left after processing. A common case is when `ItemProcessor` returns `null` to drop an item.

The processor contract allows returning `null` when an item does not need to be written. This is called filtering. It differs from `ItemReader` returning `null` to signal EOF.

```java
public class ActiveOrderProcessor implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (!order.isActive()) {
            return null; // filter this item out of the output
        }
        return order;
    }
}
```

Suppose the reader reads 10 orders but the processor filters all 10. The input chunk has 10 items and the output chunk has none. This is not the end of input: the reader can still continue reading subsequent chunks.

With default chunk processing, when the output chunk is empty, the writer is not called because there are no items to write. The transaction and the chunk completion process are still managed by the framework. The step continues reading until the reader returns `null` or an error occurs.

The difference shows clearly in the counters:

| Scenario | `readCount` | `filterCount` | `writeCount` |
| --- | ---: | ---: | ---: |
| Empty input from the start | 0 | 0 | 0 |
| Read 10 items, filter all 10 | 10 | 10 | 0 |
| Read 10 items, filter 3 and write 7 | 10 | 3 | 7 |

Therefore, looking only at `writeCount = 0` is not enough to conclude the source is empty. You need to look at both `readCount` and `filterCount` to know whether the step had no input or read the data but filtered it all.

## 7. Distinguishing filtering from skip

Filtering and skip can both cause an item to not appear in the output, but their causes and counters differ.

- **Filtering:** the processor deliberately returns `null` because the item does not need to be written. This is usually a normal business decision and is counted in `filterCount`.
- **Skip:** an exception occurs during reading, processing, or writing, and the skip policy allows ignoring the failing item. The corresponding counters can be `readSkipCount`, `processSkipCount`, or `writeSkipCount`.
- **EOF:** the reader returns `null` because there are no more items. This is the signal that the source has ended, not a filter or a skip.

For example, an inactive order can be filtered; a malformed CSV line can raise a parse exception and be skipped if the configuration allows it; after the last line, the reader returns `null` to end.

Do not use filtering to hide invalid data. If an item is dropped because of a data error and needs to be tallied or investigated, use an exception with a skip policy or a separate business-error recording mechanism.

## 8. What happens when the source ends in the middle of reading a chunk?

Within a chunk, the reader is called repeatedly until the commit interval is reached or EOF is detected. If EOF appears after some items have been read, the current chunk still contains the items already read. Spring Batch passes those items through the processor and writer and then commits according to the chunk's transaction.

For example, with an interval of 5 and a source of 7 items:

```text
Reads 1..5   -> full chunk of 5 items -> process -> write -> commit
Reads 6..7   -> reader continues reading
Next read    -> null (EOF)
                  |
                  v
              last chunk has 2 items
                  |
                  v
              process -> write -> commit
                  |
                  v
              step completes
```

EOF does not cancel a chunk that has items. This helps correctly handle sources whose item count is not divisible by the commit interval.

If the processor filters some items in the last chunk, the writer receives only the remaining outputs. If all items are filtered, the writer has no data to write, but the step still needs to finish processing the chunk and save the necessary state.

## 9. End of input in file, database, and stream readers

### File reader

With a file reader, EOF usually occurs when the reader has read all the lines or records. An empty file makes the first read return `null`. A file with 237 data lines and a commit interval of 100 produces two full chunks and a smaller last chunk.

You need to distinguish an empty file from a file with only a header. Depending on the reader and mapping configuration, the header may be skipped and the result is still no business items. If the business needs to distinguish these two cases, check the file metadata or add a separate validation step.

### Database reader

With a cursor reader, when the result set has no next row, the reader returns `null`. With a paging reader, when there is no next page or row, the reader also signals the end according to its contract. A query that returns 0 rows because the filter condition does not match is usually valid empty input at the framework level.

If data can change while the job runs, determine the snapshot or isolation semantics the reader uses. A continuously changing data source can cause the set of items read to differ from what was expected; that is a consistency issue of the source and the query, not the meaning of an empty chunk.

### Message queue or streaming source

For a data source that may temporarily have no new messages, you must not return `null` merely because the queue is empty at the moment of checking if the job still has to keep waiting for messages. Under the `ItemReader` contract, `null` means there are no more items and the step can end.

If you need to wait for new data, the reader must have an appropriate waiting/polling policy, a timeout, or another orchestration model. Return `null` only when you truly want to signal the end of input for the current run. For a queue that can receive messages continuously, you need to clearly define the termination condition, such as a message count limit, an end marker, or a time window.

## 10. End of input and restart

With a reader that supports restart, Spring Batch can save the read state in the `ExecutionContext` at the commit boundary. When the job fails midway, a restart can restore the reader from the last saved checkpoint.

`ItemStream` defines the important lifecycle callbacks:

- `open(ExecutionContext)` restores or initializes the reader state.
- `update(ExecutionContext)` writes the current state into the execution context for a checkpoint.
- `close()` releases resources after the step ends.

Many built-in readers implement `ItemStream`. A custom reader needs to implement it and save appropriate state if it wants to support restart. For example, a file reader can save the line position or byte position; a paging reader can save the last key it read.

If the job ends normally due to EOF, the step has a completed status. A `JobInstance` that is already `COMPLETED` usually cannot be launched again as a restart. If you need to re-import the same file or re-run the same business unit, clearly determine the mechanism for creating a new instance with appropriate identifying parameters or use a separate reprocessing procedure.

Do not store a home-made EOF flag in memory and expect it to be restored after a restart. The necessary state must be written to the `ExecutionContext` or be derived stably from the data source. Also note that a checkpoint only protects read progress; it does not by itself guarantee that external side effects are not repeated when the business transaction and the metadata do not share the same commit boundary.

## 11. Representing the business meaning when there is no data

By default, a step with no input can still complete with `BatchStatus.COMPLETED`. If the business needs to distinguish `NO_DATA` from a normal `COMPLETED`, you can assign a custom `ExitStatus` based on `readCount`.

An example listener:

```java
public class NoDataExitStatusListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getReadCount() == 0) {
            return new ExitStatus("NO_DATA");
        }
        return null;
    }
}
```

This listener sets the exit code `NO_DATA` when the step reads no items. Returning `null` in the case where data exists keeps the existing `ExitStatus`. You can use that code in the job's flow:

```java
@Bean
Job importJob(JobRepository jobRepository,
              Step importStep,
              Step noDataStep,
              Step reportStep) {
    return new JobBuilder("importJob", jobRepository)
        .start(importStep)
            .on("NO_DATA").to(noDataStep)
        .from(importStep)
            .on("COMPLETED").to(reportStep)
        .from(noDataStep)
            .on("*").end()
        .from(reportStep)
            .on("*").end()
        .end()
        .build();
}
```

In this example, the step's `BatchStatus` can still be `COMPLETED`, while the `ExitStatus` is `NO_DATA`. The flow matches on the exit code to choose a branch. If you do not need a separate branch, you can just log or emit a metric when `readCount` is 0.

If the processor filters out all items, `readCount` is greater than 0 and `filterCount` reflects the number of dropped items. The listener above does not treat that case as empty input. If the business wants to treat "no output" as `NO_DATA`, use a different condition, for example combining `writeCount == 0` with the related counters, and clearly define the meaning of filtering.

## 12. Monitoring counters to recognize empty input

`StepExecution` provides counters that are useful when investigating chunks:

| Counter | Meaning |
| --- | --- |
| `readCount` | Number of items successfully read from the reader. |
| `writeCount` | Number of items successfully written. |
| `filterCount` | Number of items filtered by the processor returning `null`. |
| `readSkipCount` | Number of items skipped due to errors during reading per the skip policy. |
| `processSkipCount` | Number of items skipped due to errors during processing. |
| `writeSkipCount` | Number of items skipped due to errors during writing. |
| `commitCount` | Number of times the chunk transaction was committed. |
| `rollbackCount` | Number of rollbacks recorded for the step. |

Some quick ways to read them:

- `readCount = 0`, `writeCount = 0`: the source may be empty or the reader supplied no items; check the logs and the source metadata.
- `readCount > 0`, `filterCount = readCount`, `writeCount = 0`: all items were filtered by the processor.
- `readCount > 0`, `writeCount = 0`, with a skip count: items may have been skipped due to errors per the skip policy.
- `readCount > writeCount`: this may be due to filters, skips, or other processing rules; do not conclude on your own that data was lost.

The counters reflect the step's activity according to framework rules. When you need to verify that business data was actually stored, cross-check against the target system, especially when the writer calls an API or a database with a different transaction manager.

## 13. Testing the empty chunk and EOF cases

You should have separate tests for an empty source, a source with fewer items than the commit interval, an item count divisible by the commit interval, and the case where the processor filters out all items. These tests help confirm that the reader returns `null` at the right time, that the last chunk is not lost, and that the counters reflect the activity correctly.

An example with a test job using `ListItemReader`:

```java
ItemReader<Order> emptyReader = new ListItemReader<>(List.of());
ItemReader<Order> shortReader = new ListItemReader<>(List.of(
    new Order("A-1"),
    new Order("A-2")
));
```

With a commit interval of 10, `emptyReader` supplies no items; `shortReader` supplies a last chunk of 2 items. You can launch the step/job and check the `StepExecution`:

```java
assertThat(stepExecution.getReadCount()).isEqualTo(0);
assertThat(stepExecution.getWriteCount()).isEqualTo(0);
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

The assertion snippet above is for the empty-input case. With a reader that has 2 items and a writer that writes both, expect `readCount` and `writeCount` to be 2. If the processor filters both, expect `readCount` to be 2, `filterCount` to be 2, and `writeCount` to be 0.

In addition to the counters, you can use a test writer that counts the number of times it is called to confirm that the writer is not called when the output chunk is empty under the default handling. Do not check only the `COMPLETED` status, because both empty input and input with data can complete successfully.

When testing EOF and restart, use a reader with restartable state if the goal is to confirm the checkpoint. A reader that only holds an iterator in memory is fine for a simple test but does not prove that the read state can be recovered after the application context or process is recreated.

## 14. Common mistakes when handling empty chunks and EOF

**Returning null for data that is only temporarily unavailable:** the framework interprets `null` as the end of input and completes the step. For a source that may produce more data, use a waiting or polling mechanism instead of signaling EOF too early.

**Confusing an empty string with EOF:** `""` is a non-null item. If an empty string represents an invalid line, validate or filter according to the business rules.

**Treating a small last chunk as an error:** a last chunk with fewer items than the commit interval is normal behavior. There is no need to add dummy items or change the commit interval just to fill the chunk.

**Confusing a processor returning null with the reader running out of data:** a processor returning null only drops the current item from the output. The reader continues reading the following items.

**Assuming the writer is always called:** if the output chunk is empty, by default the writer has no items to write and is usually not called. Do not put mandatory logic such as updating a "processed" status only in the writer if that logic must run even when there is no output.

**Assuming empty input means a failed job:** the framework can mark the step and job `COMPLETED` when there is no data. If the business requires a distinct status, use a custom exit code or a validation step.

**Ignoring the difference between filter and skip:** the two cases have different counters and meanings. Use the right mechanism to monitor data quality.

**The reader signals EOF early because of an error:** a parse error or connection error wrongly converted into `null` can cause the step to complete with missing data. Throw an appropriate exception when you cannot determine that the source has truly ended.

## 15. How to design end-of-input handling

When designing a chunk step, clearly define the data source's contract: which values are items, when the source truly ends, and whether it may temporarily have no data. The reader must return `null` exactly at EOF and must not use it for error states or for waiting on data.

Next, decide the business rule for empty input. If having no data is normal, let the step complete and record an appropriate metric. If you need a separate processing branch, use a custom `ExitStatus` such as `NO_DATA`. If the data is not allowed to be empty, validate and fail the step in an observable way.

Finally, monitor `readCount`, `writeCount`, `filterCount`, and the skip counts to distinguish an empty source from data that was filtered or skipped. With a reader that supports restart, save the checkpoint through the `ExecutionContext` and confirm that the writer can handle safely when a chunk is performed again.

When you correctly understand the meaning of `null`, the last chunk, and empty output, a Spring Batch application can end input naturally, handle sources of any size correctly, and clearly represent the difference between no data, filtered data, and read errors.

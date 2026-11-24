# Chunk completion when the reader ends in Spring Batch

In a chunk-oriented Step, Spring Batch gathers items into groups according to the commit interval. Normally, a chunk is processed once the configured number of items has been read. But the data source may end before reaching that size. When the **ItemReader returns null**, the framework recognizes that the input has run out and completes the current chunk with the items it has already read.

This means the last chunk does not need to be full to the commit interval in order to be written. If there are items left in the chunk, Spring Batch still passes them through the processor and writer, and then completes the chunk's transaction. If the source ends from the very first read, there are no business items to write, and the Step can complete normally with a read count of 0.

Understanding how a chunk ends helps avoid a common wrong assumption: the chunk size is the maximum number of items gathered for one commit, not a required condition for data to be written. This lesson presents how the last chunk is handled, the cases of an empty source and of item counts that are or are not divisible by the commit interval, and the effects on transactions, checkpoints, metrics, and testing.

## 1. Commit interval and the chunk termination condition

A chunk-oriented Step configured with a commit interval:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .build();
}
~~~

In the example, 100 is the commit interval. Spring Batch reads at most 100 input items to create a chunk. When the item count is reached, the framework processes and writes that chunk in the corresponding transaction.

A chunk can also end early when the reader reports that the data has run out. There are two common conditions that make the framework complete the read phase of a chunk:

- The required number of items has been collected according to the commit interval.
- The reader returns `null`, signaling that the source has no next item.

Therefore, the commit interval is a limit on chunk size, not a requirement that every chunk must have that many items.

~~~mermaid
flowchart TD
    A["Start reading chunk"] --> B["ItemReader.read()"]
    B --> C{"Read result"}
    C -- "Has item" --> D["Add item to chunk"]
    D --> E{"Commit interval reached?"}
    E -- "Not yet" --> B
    E -- "Reached" --> F["Process and write chunk"]
    C -- "null / EOF" --> G["End the read phase"]
    G --> H["Process and write the remaining items"]
    H --> I["Complete transaction"]
    F --> I
    I --> J["Next chunk or end of Step"]
~~~

The diagram describes the conceptual flow. When the reader reports EOF, Spring Batch must still process the items already read in the current chunk before ending the Step.

## 2. The last chunk can be smaller than the commit interval

Suppose the commit interval is 3 and the source has 8 items: A, B, C, D, E, F, G, H.

The chunks are formed as follows:

~~~text
Chunk 1: A, B, C  -> 3 items reached -> write -> commit
Chunk 2: D, E, F  -> 3 items reached -> write -> commit
Chunk 3: G, H     -> reader returns null -> write -> commit
~~~

The last chunk has only 2 items. Spring Batch does not discard these two items just because they haven't reached size 3. The reader returns `null` to signal the end of the source; the framework processes the remaining data and then completes the last chunk's transaction.

Example configuration:

~~~java
new StepBuilder("importStep", jobRepository)
    .<Order, Order>chunk(3, transactionManager)
    .reader(orderReader)
    .writer(orderWriter)
    .build();
~~~

If the reader provides 8 items, the writer will receive output groups corresponding to the chunks that are processed. The last chunk has fewer items than the commit interval but is still written through the normal flow.

### Why must the last chunk be written?

If the framework only wrote chunks with a full 3 items, every source whose count is not divisible by 3 would lose its remainder. With 8 items, the last two items would not be written. With 101 items and a commit interval of 100, the 101st item would be left behind.

The correct behavior is to process the last chunk when the reader ends. This is a basic part of chunk-oriented processing; you don't need to write extra logic to flush the remainder in the ItemWriter.

## 3. What happens when the reader returns null?

The ItemReader contract is to return an item or `null`:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

- Returns an item: the framework adds that item to the input portion of the chunk.
- Returns `null`: the framework knows the source has run out and does not request a next item for this Step.
- Throws an exception: the framework handles the error according to the transaction and the Step's skip/retry/fail policy.

Suppose the chunk size is 5 but the reader has only two items left. The conceptual sequence:

~~~text
read() -> item 1
read() -> item 2
read() -> null
~~~

After receiving `null`, the framework completes the read phase of the chunk. The two items already read are still passed through the processor if there is one, and then the output items are written according to the writer configuration. When the necessary operations succeed, the chunk's transaction is committed.

`null` is the signal for the end of the source. It is not an empty item, not a substitute value for a faulty record, and does not mean discarding the current chunk.

### No need to call the writer yourself to flush

You should not add logic such as:

~~~java
if (readerReturnedNull) {
    writer.write(remainingItems);
}
~~~

in the reader or in a component outside the Step. Spring Batch already manages gathering chunks and calling the writer. If the application calls the writer itself outside this flow, it may write duplicates, bypass the chunk's transaction, or corrupt the StepExecution statistics.

The reader only needs to follow the read contract. The writer only needs to handle the chunk that the framework passes to it.

## 4. Cases where the source ends

You can divide them into three common cases: an empty source, a source with fewer items than the commit interval, and a source whose item count is or is not divisible by the commit interval.

### Case A: the source has no items

Suppose the reader returns `null` on the very first read:

~~~text
read() -> null
~~~

No items are passed to the writer. The Step can end normally if an empty source is a valid input.

The business counters usually have the values:

- `readCount = 0`
- `writeCount = 0`
- `filterCount = 0`

If the Job requires data to be present, you need to check this condition and report an appropriate business status. Don't assume a COMPLETED Step with 0 items is always a business success.

For example, a file containing only a header may be a valid empty file or an input error depending on the requirements. That decision belongs to the Job's or Step's validation, and is not a reason for the reader to return a fake item.

### Case B: the source is smaller than the commit interval

The commit interval is 100 and the source has 25 items.

~~~text
read 25 items
read() -> null
process 25 items
write the output portion
commit the last chunk
~~~

One chunk containing 25 items is completed. There is no need to wait for another 75 items.

### Case C: the source's item count is divisible by the commit interval

The commit interval is 100 and the source has 200 items.

~~~text
Chunk 1: 100 items -> write -> commit
Chunk 2: 100 items -> write -> commit
Next read: null -> end Step
~~~

Both data chunks are full-size. After the second chunk completes, the framework needs to determine that the source has run out. EOF detection can happen on the next read; no 201st item is added to the chunk.

Do not infer the number of reader calls just from the number of chunks. The framework may need an extra `read()` call to detect EOF after a chunk that exactly fills the commit interval.

### Case D: the source is not divisible by the commit interval

The commit interval is 100 and the source has 235 items.

~~~text
Chunk 1: 100 items -> write -> commit
Chunk 2: 100 items -> write -> commit
Chunk 3:  35 items -> EOF -> write -> commit
~~~

The third chunk contains 35 items and is still processed normally.

| Source item count | Commit interval | Data chunks |
|---:|---:|---|
| 0 | 100 | No chunk containing items |
| 25 | 100 | 25 |
| 100 | 100 | 100 |
| 200 | 100 | 100, 100 |
| 235 | 100 | 100, 100, 35 |
| 301 | 100 | 100, 100, 100, 1 |

The table describes the groups of input items by commit interval, before considering processor filters and skipped errors.

## 5. The processing cycle of the last chunk

When the source ends before reaching the commit interval, the last chunk goes through the same processing phases as earlier chunks.

Suppose the commit interval is 4 and the source has only two items left:

~~~mermaid
sequenceDiagram
    participant S as Spring Batch
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant TM as TransactionManager

    S->>TM: Begin transaction
    S->>R: read()
    R-->>S: Item A
    S->>R: read()
    R-->>S: Item B
    S->>R: read()
    R-->>S: null (EOF)
    S->>P: process(A)
    P-->>S: Output A
    S->>P: process(B)
    P-->>S: Output B
    S->>W: write(chunk with 2 outputs)
    W-->>S: Done
    S->>TM: Commit last chunk
~~~

The specific order of internal operations and metadata updates depends on the Step, reader, and transaction manager configuration. In terms of behavior, what to remember is that items read in the last chunk are still processed and written before the Step ends.

### The processor can filter items in the last chunk

If the processor returns `null` for an item, that item counts as read but produces no output for the writer.

For example, the source has three items left and the processor filters one item:

~~~text
Reader:      A, B, C, null
Processor:   A -> A'
             B -> null (filtered)
             C -> C'
Writer:      A', C'
~~~

The last chunk is still completed. The number of items the writer receives can be lower than the number the reader read, because filtering is a separate rule unrelated to EOF.

If all items of the last chunk are filtered, there is no output data to write. The framework must still complete the chunk processing and update the statistics according to the processing flow.

## 6. The last chunk and transaction commit

The last chunk has a transaction just like the other chunks. If the writer succeeds and the transaction commits, the last chunk's data is saved durably.

For example:

- Chunk 1 has 100 items and commits successfully.
- Chunk 2 has 100 items and commits successfully.
- Chunk 3 has 35 items because the reader ended.
- The writer writes the 35 items successfully.
- Chunk 3's transaction commits.
- The Step completes.

~~~mermaid
flowchart TD
    A["Chunk 1: 100 items"] --> B["Commit 1"]
    B --> C["Chunk 2: 100 items"]
    C --> D["Commit 2"]
    D --> E["Last chunk: 35 items"]
    E --> F{"Writer succeeded?"}
    F -- "Yes" --> G["Commit 3"]
    G --> H["Step COMPLETED"]
    F -- "No" --> I["Rollback chunk 3"]
    I --> J["Step FAILED or retry"]
~~~

### EOF does not commit the chunk by itself

The reader returning `null` only signals the end of the source. It does not directly call `commit()` and cannot decide by itself that the transaction succeeds.

Commit only happens when the framework finishes processing the chunk and the transaction manager ends the transaction successfully. If the processor or writer raises an error, the transaction may roll back instead of committing.

Therefore, you need to distinguish:

- EOF: the end of fetching more items.
- Chunk completion: finishing the processing of the current group of items.
- Commit: that group's transaction is confirmed as successful.
- Step completion: the whole Step ends according to the defined status and flow.

These are four related but not identical events.

## 7. What happens if writing the last chunk fails?

Suppose the source has 235 items and the commit interval is 100. The first two chunks have committed; the last chunk has 35 items.

If the writer throws an exception in the last chunk:

1. The last chunk's write operations are performed in the transaction.
2. The writer raises an error.
3. The last chunk's transaction rolls back if the exception and the rollback policy call for it.
4. The earlier chunks still exist because they have committed.
5. The Step can retry, skip according to policy, or fail.
6. On restart, the reader restores the appropriate state to reprocess the uncommitted portion, if the reader supports restart.

~~~text
Chunk 1: 100 items -> COMMIT
Chunk 2: 100 items -> COMMIT
Chunk 3:  35 items -> WRITE ERROR -> ROLLBACK

Result:
  - The 200 items of the first two chunks have been committed.
  - The 35 items of the last chunk have not been committed.
  - The Job can restart from the checkpoint.
~~~

If the writer writes to a resource outside the database transaction, the rollback does not necessarily undo that effect. For example, an API may have received the 35 items while the database rolled back. On restart, the writer may resend the data; idempotency or a reconciliation mechanism is needed.

### Errors occurring while the reader is reading the last chunk

If the reader throws an exception before returning `null`, that is not EOF. The framework handles the read error according to the transaction and the Step's skip/retry policy.

For example, the source has A, B, C, and then reading the next item hits an error:

~~~text
read() -> A
read() -> B
read() -> C
read() -> IOException
~~~

The framework must not treat the IOException as a signal that the source has run out. Depending on the configuration, the Step can retry, skip the read error, or fail. If the reader catches the exception and returns `null`, A, B, C may be processed as a normal last chunk and the real error is hidden.

## 8. Skip and retry in the last chunk

The last chunk follows the Step's fault-tolerant policy like the other chunks.

Example retry configuration for transient database errors:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
~~~

If the writer hits a transient error in the last chunk, Spring Batch can perform a retry according to the policy. The last chunk is not excluded from the retry mechanism just because it is smaller than the commit interval.

Example of skipping parse errors:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(FlatFileParseException.class)
    .skipLimit(10)
    .build();
~~~

If a read error is of a type allowed to be skipped, the framework can skip the faulty item through the fault-tolerant mechanism and continue reading the rest. If the reader then returns `null`, the remaining valid items of the chunk are still completed.

Do not treat EOF as a kind of error to skip. EOF is the normal termination condition of a reader.

### Don't raise the skip limit to handle EOF

A design mistake is to catch an exception at the end of the source or a parse error and convert it into a kind of skip in order to avoid the Step failing. This distorts the meaning of the counters and hides missing data.

Let the reader return `null` exactly when the data runs out; for read errors, throw an appropriate exception and let the policy handle it.

## 9. The reader must determine the end correctly

For the last chunk to be processed correctly, the reader must follow its contract.

A custom reader for a fixed list:

~~~java
public class ListOrderReader implements ItemReader<Order> {

    private final Iterator<Order> iterator;

    public ListOrderReader(List<Order> orders) {
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
~~~

The reader returns each item until the iterator is exhausted. Only the read after the last item returns `null`, so the framework knows when to complete the last chunk.

### Don't return null just because there is no data temporarily

With a source that can continuously produce data, such as a message broker, a poll that finds no message does not necessarily mean the source has ended. If the reader returns `null`, Spring Batch understands the Step has run out of input.

With a streaming or queue source, you need to clearly define the processing window, the termination condition, the timeout, or the polling approach. If you need to wait for more data, the reader must use an appropriate mechanism instead of using `null` to mean "no item available right now".

### Multiple files or multiple delegates

If a reader orchestrates multiple files, the EOF of the first file only means that file has run out. The composite reader must move to the next file and only return `null` when all resources have run out.

~~~java
public Order read() throws Exception {
    while (currentReader != null) {
        Order item = currentReader.read();

        if (item != null) {
            return item;
        }

        currentReader = nextReader();
    }

    return null;
}
~~~

The example above describes the source-switching logic. A real reader needs to save the current file's state and read position in the ExecutionContext if the Job must restart.

If the composite reader returns `null` as soon as the first file runs out, the subsequent files will not be processed and the last chunk of the whole Step will be ended early.

## 10. Checkpoint and restart at the last chunk

Spring Batch uses the ExecutionContext to save the state of readers or writers that support restart. With a chunk-oriented Step, the checkpoint is usually updated at the chunk boundary according to the configuration.

Suppose the source has 235 items and the commit interval is 100:

~~~text
Chunk 1: items 1-100    -> commit + checkpoint
Chunk 2: items 101-200  -> commit + checkpoint
Chunk 3: items 201-235  -> writer error -> rollback
~~~

When the Job restarts, the reader needs to restore its state to reprocess the uncommitted portion. With a reader that supports ItemStream, the framework calls the lifecycle methods to save and restore state.

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

- `open(...)` restores the read position.
- `update(...)` saves the state at the checkpoint.
- `close()` closes resources when the Step ends.

With a standard FlatFileItemReader or paging reader, the read state can be saved according to the configuration. With a custom reader, you need to implement saving and restoring the appropriate position yourself.

### Don't save a checkpoint just because the source has been fully read

EOF does not mean all the data has been committed. The reader may have read to the end of the file but the last chunk's writer still fails. The reader's state must be coordinated with the transaction and the checkpoint so that a restart doesn't skip uncommitted data.

Don't save the last read position to an independent place as soon as the reader sees EOF. The checkpoint must reflect the portion of work that has been confirmed at the commit boundary.

### The source must be stable on restart

If the input file is changed after the first run, the saved line position may point to different content. With database paging, if the data set or the sort key changes, a restart may miss or re-read records.

Some ways to protect against this:

- Use files that are immutable per batch ID.
- Store the size, checksum, or version of the input file.
- Use a fixed data range per batch ID or business date.
- Use a unique and stable sort key for paging.
- Design an idempotent writer if data may be read again.

## 11. The last chunk with FlatFileItemReader

FlatFileItemReader reads line by line and returns `null` when it has read the whole resource. When the number of data lines is not divisible by the commit interval, the end of the file produces a smaller chunk.

For example, a file has 12 data lines and the commit interval is 5:

~~~text
Chunk 1: 5 lines
Chunk 2: 5 lines
Chunk 3: 2 lines
EOF
~~~

Reader configuration:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .delimited()
        .names("customerId", "fullName", "email")
        .fieldSetMapper(fields -> new CustomerInput(
            fields.readString("customerId"),
            fields.readString("fullName"),
            fields.readString("email")
        ))
        .build();
}
~~~

`linesToSkip(1)` skips the header line, which is not a data item. The reader still returns each data line and ends with `null` at EOF. The last chunk contains the remaining data lines.

If the file has only a header, the reader returns no data items. The Step can complete with 0 items; if the business requires at least one line, you need to check that condition separately.

## 12. The last chunk with JdbcPagingItemReader

A paging reader fetches data page by page. Page size and commit interval are two related configurations but do not necessarily have to be equal.

For example:

~~~java
@Bean
JdbcPagingItemReader<Order> orderReader(DataSource dataSource) {
    return new JdbcPagingItemReaderBuilder<Order>()
        .name("orderReader")
        .dataSource(dataSource)
        .selectClause("SELECT order_id, amount")
        .fromClause("FROM source_order")
        .whereClause("WHERE batch_id = :batchId")
        .parameterValues(Map.of("batchId", "BATCH-20261115"))
        .sortKeys(Map.of("order_id", Order.ASCENDING))
        .pageSize(500)
        .rowMapper((rs, rowNum) -> new Order(
            rs.getLong("order_id"),
            rs.getBigDecimal("amount")
        ))
        .build();
}
~~~

If the total number of records is 1,230, the page size is 500, and the commit interval is 200, the reader and the Step can work together to form multiple chunks of 200 items, while pages are fetched in size 500. The last chunk has 30 items.

You need to use a stable and unique sort key. Page size controls the number of rows fetched per query; commit interval controls the number of items gathered for one chunk transaction. Don't confuse these two values.

## 13. The last chunk when the processor filters many items

The commit interval is usually counted based on the number of input items read, while the writer receives the output items after the processor. Therefore, the number of items the writer receives can be smaller than the commit interval.

For example, a commit interval of 5 and a source of 7 items:

~~~text
Chunk 1 input: A, B, C, D, E
Processor:     A -> A'
               B -> null (filtered)
               C -> C'
               D -> null (filtered)
               E -> E'
Writer output: A', C', E'

Chunk 2 input: F, G, null (EOF)
Processor:     F -> F'
               G -> null
Writer output: F'
~~~

The second chunk has two input items before EOF, but only one output item. The chunk is still completed at the EOF boundary.

The counters need to be understood separately:

- `readCount`: the number of items the reader provided.
- `filterCount`: the number of items the processor filtered.
- `writeCount`: the number of items written.
- Skip counts: the number of items or operations skipped according to the error policy.

Do not assume the writer always receives exactly as many items as the commit interval, or that the last item count always equals the remainder of writeCount.

## 14. Commit count and how to read metrics

StepExecution stores counters such as:

| Property | Meaning |
|---|---|
| `readCount` | Number of items the reader returned |
| `writeCount` | Number of items written by the writer |
| `filterCount` | Number of items filtered by the processor |
| `readSkipCount` | Number of read errors skipped |
| `processSkipCount` | Number of processing errors skipped |
| `writeSkipCount` | Number of write errors skipped |
| `commitCount` | Number of commits of the Step |
| `rollbackCount` | Number of rollbacks |

With a 235-item source, a commit interval of 100, and no filters or skips, there are three chunks containing items: 100, 100, and 35. This is how input item groups are calculated.

Do not use a simple formula to assert that `commitCount` always equals `ceil(readCount / commitInterval)` in every situation. Retry, skip, rollback, Tasklet execution, transaction metadata, and the read that confirms EOF can affect the actual figures. Use commitCount to observe the Step's transactions and cross-check it against the other counters.

### Detecting that the last chunk was not written

For important Jobs, you should reconcile an independent source count against readCount, filterCount, skip counts, and writeCount.

For example, the source has 235 records:

~~~text
Expected source count = 235
readCount             = 235
filterCount           = 5
readSkipCount         = 0
processSkipCount      = 0
writeSkipCount        = 0
writeCount            = 230
~~~

In the example, 5 items were filtered and 230 items were written. This can be a valid result if business policy allows filtering those 5 items.

If `readCount = 200` but the source confirms 235 records, you need to investigate the reader, the query conditions, EOF, and the source configuration. You cannot conclude that the last chunk was automatically written just from the Step's COMPLETED status.

## 15. Testing chunk completion behavior when the reader ends

You should test at least these cases:

| Source item count | Commit interval | What to confirm |
|---:|---:|---|
| 0 | 5 | The Step completes with 0 items if an empty input is valid |
| 2 | 5 | The last two items are still written |
| 5 | 5 | The full chunk is written, EOF ends the Step |
| 7 | 5 | The chunk of 5 and the last chunk of 2 are both written |
| 10 | 5 | Two full chunks are written |
| 12 | 5 | Two full chunks and the last chunk of 2 are written |
| 7 | 5, processor filters 2 | read, filter, and write counts reflect correctly |
| 7 | 5, writer fails on the last chunk | The last chunk rolls back or retries according to policy |

### Testing the reader and writer with a fixed list

For example, a Step that uses a source of 7 items and a commit interval of 5:

~~~java
@Bean
ItemReader<Integer> numberReader() {
    return new ListItemReader<>(List.of(1, 2, 3, 4, 5, 6, 7));
}
~~~

A test writer can collect the chunk sizes it receives:

~~~java
@Bean
List<Integer> writtenItems() {
    return new CopyOnWriteArrayList<>();
}

@Bean
ItemWriter<Integer> collectingWriter(List<Integer> writtenItems) {
    return chunk -> writtenItems.addAll(chunk.getItems());
}
~~~

After the Job completes, confirm that the written list has all 7 items and in the right order if the Step is configured as single-threaded. If you need to confirm chunk boundaries, use a test writer that separately records the size of each call.

Expected result for the item groups:

~~~text
write call 1: [1, 2, 3, 4, 5]
write call 2: [6, 7]
~~~

This example illustrates the case with no filter, no skip, and no retry. In real testing, you need to use a test context and a JobRepository appropriate for your application's Spring Batch version.

### Testing an empty source

An empty source needs to be tested separately:

~~~java
@Bean
ItemReader<Integer> emptyReader() {
    return new ListItemReader<>(List.of());
}
~~~

Confirm that the Step ends with the right status, no items are written, and the Job handles the 0-item result according to business requirements.

### Testing an error in the last chunk

Make the writer throw an exception when it receives the last chunk. After the Step fails, confirm:

- The earlier committed chunks still exist.
- The last chunk's changes are rolled back if they participate in the transaction.
- The Step has an appropriate failure status.
- On restart, the reader restores the uncommitted portion.
- The writer does not create duplicate data when reprocessing.

## 16. Common misunderstandings

### Thinking the last chunk must be full to the commit interval

The chunk size is a limit on the number of items gathered for a chunk. EOF can end a chunk early; the remaining items are still processed.

### Discarding the remainder yourself in the reader

Don't keep the last items in a buffer and then discard them when the count hasn't reached the commit interval. Spring Batch will process the remaining part of the chunk when the reader returns `null`.

### Treating null as an error

`null` is the normal end of the source. A read error must be represented by an exception so that the skip/retry/fail policy handles it.

### Calling the writer yourself to write the remainder

The writer is called by the framework in the chunk flow. Calling the writer yourself from the reader or a listener can break the transaction and the statistics.

### Confusing page size with commit interval

Page size controls the amount of data queried per page; commit interval controls the group of items in a chunk transaction. The two values can differ.

### Believing a COMPLETED Job means no data was lost

A Job can complete with fewer items than expected because of source conditions, filters, skips, or the reader returning EOF early. You need to reconcile the source count and the StepExecution counters.

### Deleting the source as soon as the reader returns EOF

The reader having read the whole source does not mean the last chunk has been written and committed by the writer. Only clean up the source after the Step has completed and the necessary steps have confirmed the result.

### Only testing counts divisible by the chunk size

If you only try 100, 200, or 300 items with a commit interval of 100, the test does not cover a last chunk that isn't full. You need cases with 1, 99, 101, or 235 items.

## 17. Procedure to check when data at the end of the source is missing

If the output count is lower than expected, determine whether the discrepancy lies in the reader, processor, writer, or transaction:

1. **Count the source:** determine the number of items belonging to the exact batch or input range.
2. **Check readCount:** confirm whether the reader provided enough items.
3. **Check EOF:** look for the logic that returns `null` in a custom reader, multi-resource reader, or query conditions.
4. **Check filterCount:** identify the items filtered by the processor.
5. **Check skip counts:** see which read, processing, or write errors were skipped.
6. **Check writeCount:** confirm the number of items written successfully.
7. **Check the transaction:** look at rollbackCount, the writer logs, and the state of the last chunk.
8. **Check restart:** confirm whether the checkpoint correctly reflects the committed chunks.
9. **Check the paged source:** confirm the sort key, page size, and source data are stable.
10. **Reconcile the target data:** find the last item written and the first item that is missing.

If the reader returns EOF too early, check conditions such as blank lines, swallowed parse errors, the resource list, query limits, and the iterator state. If readCount is complete but writeCount is low, look at filters, skips, and the writer transaction.

Do not immediately re-run a Job whose writer is not idempotent before determining which chunks have been committed. A wrongly performed restart can create duplicate data or make the reconciliation figures harder to understand.

## 18. Key points to remember

- The commit interval is the maximum size of a chunk, not a required minimum item count.
- When the ItemReader returns `null`, Spring Batch ends reading and processes the current chunk.
- The last chunk can be smaller than the commit interval and is still written and committed normally.
- If the source is empty, there are no business items to write; the Step can complete with 0 items if allowed.
- If the item count is divisible by the commit interval, the full chunks are processed before the framework confirms EOF.
- The processor can filter items in the last chunk; the writer receives the remaining output items.
- EOF does not directly commit the transaction; the transaction manager commits after the chunk is processed successfully.
- An exception while reading differs from EOF and must be handled according to the skip/retry/fail policy.
- The last chunk can roll back if the writer fails; the earlier committed chunks are kept.
- The reader and checkpoint need to support restart to reprocess the uncommitted portion.
- Page size and commit interval control two different aspects.
- Use readCount, filterCount, skip counts, and writeCount to reconcile data, and don't rely on the COMPLETED status alone.
- Test an empty source, a source smaller than the chunk size, and item counts that are and are not divisible by the commit interval.

When the reader ends, Spring Batch still completes the data already read in the last chunk. Designing a reader that follows the contract, a writer that participates in the transaction appropriately, and testing with counts not divisible by the commit interval helps avoid losing the data at the end of the source.


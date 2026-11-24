# A Reader Must Not Unintentionally Skip Items

In Spring Batch, the **ItemReader** is the component that brings data from a source into a Step. The reader is responsible for providing items to the framework one after another. A very important rule of this contract is: **return null only when the input source is exhausted**.

If a reader returns null because it encountered a faulty line, an invalid record, a temporary gap, or a data-reading failure, Spring Batch may conclude that the entire source has ended. The records after it will not be read. This is one of the dangerous causes of a Job completing with missing data and no clear error.

This lesson explains the ItemReader contract, how to distinguish the end of the source from filtering and skipping records, common implementation mistakes, how to configure a reader to avoid losing items, and how to monitor and test data completeness.

## 1. The ItemReader Contract

The basic ItemReader interface:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

Each time Spring Batch calls the read() method, the reader must return one of two results:

- An object of type T if the next item is read.
- null if there are no more items in the input source.

If the data cannot be read or converted, the reader should throw an appropriate exception so that the framework and the Step's error policy handle it. Do not turn errors into null.

~~~mermaid
flowchart TD
    A["Spring Batch calls read()"] --> B{"Items left in the source?"}
    B -- "Yes" --> C["Return the item"]
    C --> A
    B -- "No" --> D["Return null"]
    B -- "Read / parse error" --> E["Throw an exception"]
    E --> F["Step handles it by skip / retry / fail"]
~~~

Spring Batch keeps calling read() until the reader returns null. The null value is the reader's end-of-input signal, not an empty item and not a way to represent an invalid record.

### One Read Corresponds to One Item

A reader is usually called repeatedly in a chunk-oriented Step. The framework manages the number of calls and gathers items according to the commit interval. The application should not call read() again on its own outside the flow managed by the Step, because doing so may consume items before the framework receives them.

For example, if the source has five records A, B, C, D, and E, the normal sequence of results must be:

~~~text
read() -> A
read() -> B
read() -> C
read() -> D
read() -> E
read() -> null
~~~

If the reader returns null right after C, the framework ends reading and D and E will not be passed to the processor or writer. The Job may complete with less data than the actual source.

### Do Not Use null to Report Errors

Some common incorrect ways of writing it:

~~~java
public Customer read() {
    try {
        return readNextCustomer();
    } catch (Exception ex) {
        return null; // Wrong: the error is interpreted as end of data.
    }
}
~~~

~~~java
public Customer read() {
    String line = readNextLine();

    if (line == null || line.isBlank()) {
        return null; // Wrong if a blank line does not mean EOF.
    }

    return map(line);
}
~~~

In the first example, the read error is hidden. In the second example, a blank line may cause the reader to end even though there is still data after it.

The correct approach is to distinguish clearly:

- The source truly has no more data: return null.
- A record is read: return the item.
- A record is malformed or cannot be read: throw an exception.
- A record that needs to be removed per business rules: use a clearly designed filtering mechanism.

## 2. Distinguishing End of Source, Filtering, and Skip

These three concepts have different meanings in Spring Batch.

| Behavior | Component / how it is done | Meaning |
|---|---|---|
| End of source | ItemReader returns null | There are no more items to read |
| Filter an item | ItemProcessor returns null | The item was read but is not passed to the writer |
| Skip a faulty item | Fault-tolerant skip configuration for an exception | Skip the faulty record or operation according to the declared policy |
| Successful read | ItemReader returns an item | The item is passed into the processing flow |

### Filtering with ItemProcessor

If a record is structurally valid but does not need to be output according to a business rule, the ItemProcessor can return null.

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if ("CANCELLED".equalsIgnoreCase(input.status())) {
            return null; // Deliberate filtering.
        }

        return new Order(
            input.orderId(),
            input.customerId(),
            input.amount()
        );
    };
}
~~~

In the example, the reader still reads the cancelled order record and the processor decides to filter it. This is a clearer way of expressing it than having the reader silently drop the record.

Spring Batch can record the number of filtered items in the StepExecution's filterCount. This way, the operations team can distinguish the number of items read from the number of items passed to the writer.

### Skip on Exceptions

If a file line cannot be parsed or an item encounters an error that is allowed to be skipped, you can use the Step's skip mechanism:

~~~java
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
        .skipLimit(10)
        .build();
}
~~~

This configuration allows skipping exceptions of type FlatFileParseException within the declared limit. When the skip limit is exceeded, the Step fails.

Skipping must be a deliberate business decision. If the faulty data needs to be investigated, record information about the line, the source, the cause, and the batch code using a listener or an appropriate audit mechanism. Do not just raise the skip limit to let the Job run past errors without knowing which data was dropped.

### Why Not Filter in the Reader?

A reader can read from a SQL query that fetches only records meeting a business condition. This is a valid choice when that condition is the definition of the input set. However, a custom reader should not silently drop items after reading them without clear rules and statistics.

Distinguish two cases:

- **Selecting the input source:** the SQL has a WHERE clause or the source configuration clearly defines which records belong to the batch to be processed.
- **Filtering items already read:** the processor decides whether an item is passed to the writer.

When using a filter at the source, record the query condition and the expected number of source records. Otherwise, missing data caused by an overly broad WHERE clause or a wrong condition may be mistaken for the reader ending normally.

## 3. Common Mistakes That Cause a Reader to Skip Items

### Returning null on a Blank Line

A blank line is not necessarily EOF. A file may contain a blank line in the middle and many records after it.

If the business format allows blank lines, handle them according to a defined rule: treat as a faulty record, skip with recording, or treat as a line that carries no data. Do not automatically treat every blank line as the end of the file.

### Catching an Exception and Returning null

This is a serious mistake because the exception is hidden and Spring Batch does not know the reader encountered an error. The Job may finish with a COMPLETED status even though only part of the source was read.

Let the exception propagate, or convert it into an exception appropriate for the Step's skip/retry policy. Catch an exception only when you can handle it correctly and still preserve the read contract.

### Skipping Invalid Records Inside the Loop

A custom reader may have a loop that searches for the next item:

~~~java
public OrderInput read() {
    while (iterator.hasNext()) {
        String line = iterator.next();

        if (isValid(line)) {
            return map(line);
        }
    }

    return null;
}
~~~

This code silently drops every invalid line. If the requirement is to check and record data errors, this approach makes faulty records disappear with no skip figures or information for reconciliation.

If you need to filter in the reader by design, you must document the reason, the filter condition, and the number removed. For ordinary business rules, return the raw item and let the processor check and decide.

### Confusing a Source That Temporarily Has No Data with EOF

A source may temporarily return no data while data will still arrive later. If the reader returns null, Spring Batch considers the source ended and the Step may complete.

ItemReader suits sources whose end point can be determined. For a queue or a continuous data stream, you need to design polling, timeouts, data-fetch windows, or a clear loop-control mechanism. Do not use null as a signal for "no message right now" if the source may still produce messages for the same processing run.

### Reading Ahead or Consuming the Iterator Multiple Times

A custom reader may call next() in a check function and then call next() again in the map function. This loses an item between the two reads.

Make sure each source item is consumed exactly once per read() call and that no other code reads from the same iterator or cursor outside the reader.

### Changing the Source Data While Paging

With a paging reader from a database, if the sort order is not stable or data is added/deleted while the Job runs, a record may be repeated or missed between pages.

Use a deterministic order, prefer a unique key, and consider a snapshot or a data-range condition appropriate to the business.

## 4. Configuring FlatFileItemReader So It Does Not End Early

FlatFileItemReader reads a text file line by line and maps each line to an item. The configuration must clearly express the resource, encoding, header, how fields are split, and how they are mapped.

Example:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .strict(true)
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

Some points to note:

- **name:** give the reader a stable name, which helps identify the state in the ExecutionContext.
- **resource:** correctly identifies the file to read.
- **encoding:** use the encoding that matches the file, for example UTF-8.
- **strict(true):** reports an error if the resource does not exist or cannot be opened under strict configuration.
- **linesToSkip(1):** skips only the header line that has been identified, not arbitrary data lines.
- **names(...):** maps the column order correctly.
- **fieldSetMapper:** converts the fields into the application's data types.

### Be Careful with strict(false)

If the reader is configured as non-strict, a file that does not exist may be treated as a source with no data instead of a file-open error. When the input file is mandatory, this is very dangerous: the Job may complete with 0 items without reporting an error as expected.

Use non-strict mode only when the business defines a missing file as meaning no data and that behavior is under control. For a mandatory file, keep strict mode and check the file before starting the import.

### Skip Only the Defined Header

linesToSkip is used to skip a number of lines at the start of the file, usually the header. Do not increase this value to avoid faulty lines at the start of the file. If the file has several kinds of lines such as a header, trailer, or comment, use an appropriate parsing mechanism to recognize each kind and clearly record which lines are excluded.

You can use skippedLinesCallback to read the content of the skipped header lines, for example to confirm the column names or the file format version. If the header is incorrect, the callback can throw an exception to stop the Job early.

## 5. Handling Malformed Lines Instead of Losing Data

FlatFileItemReader uses a LineMapper to convert a text line into an item. If a line does not have the right structure, the mapper or FieldSetMapper can throw an exception.

Example:

~~~java
@Bean
LineMapper<CustomerInput> customerLineMapper() {
    DefaultLineMapper<CustomerInput> mapper =
        new DefaultLineMapper<>();

    DelimitedLineTokenizer tokenizer =
        new DelimitedLineTokenizer();

    tokenizer.setNames("customerId", "fullName", "email");

    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fields -> new CustomerInput(
        fields.readString("customerId"),
        fields.readString("fullName"),
        fields.readString("email")
    ));

    return mapper;
}
~~~

If a line is missing a column or has a value that cannot be converted, decide clearly:

- Stop the Job to require the file to be fixed.
- Skip the line within the allowed limit and record the error information.
- Put the faulty record into a reject file or a quarantine table for later handling.

Do not return null from the mapper or reader to hide the error. Null in the ItemReader contract means there is no next item.

### Example of Recording a Skipped Line

You can use a SkipListener to record read errors:

~~~java
@Bean
SkipListener<CustomerInput, Customer> customerSkipListener(
        RejectedRecordService rejectedRecordService) {

    return new SkipListener<>() {
        @Override
        public void onSkipInRead(Throwable throwable) {
            if (throwable instanceof FlatFileParseException ex) {
                rejectedRecordService.record(
                    ex.getInput(),
                    ex.getLineNumber(),
                    ex.getMessage()
                );
            }
        }

        @Override
        public void onSkipInProcess(
                CustomerInput item,
                Throwable throwable) {
            rejectedRecordService.record(
                item,
                throwable.getMessage()
            );
        }

        @Override
        public void onSkipInWrite(
                Customer item,
                Throwable throwable) {
            rejectedRecordService.record(
                item,
                throwable.getMessage()
            );
        }
    };
}
~~~

The listener illustrates how to record read, processing, and write errors. In a real application, you need to implement a service that stores the reject data and determine an appropriate transaction boundary so the error information is not lost when a chunk rolls back.

## 6. Readers for Databases and Paging

With database data, a reader usually uses a cursor or paging. These two types behave differently but both must return items one by one until the result has been fully read.

### JdbcCursorItemReader

A cursor reader opens a ResultSet and reads the rows in turn. Example:

~~~java
@Bean
JdbcCursorItemReader<CustomerInput> customerCursorReader(
        DataSource dataSource) {

    return new JdbcCursorItemReaderBuilder<CustomerInput>()
        .name("customerCursorReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name, email
            FROM customer_import_source
            ORDER BY customer_id
            """)
        .rowMapper((rs, rowNum) -> new CustomerInput(
            rs.getString("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        ))
        .fetchSize(500)
        .build();
}
~~~

Some important points:

- The query needs to return the entire desired data set.
- ORDER BY should be stable so the results have a deterministic order.
- The RowMapper should not return null to drop a row.
- If converting a column fails, let the error be reported or handled with an appropriate policy.
- You need to understand the transaction, connection, and cursor lifecycle of the datasource.

### JdbcPagingItemReader

A paging reader executes queries page by page. The configuration must have a sort key that determines the order:

~~~java
@Bean
JdbcPagingItemReader<CustomerInput> customerPagingReader(
        DataSource dataSource) {

    return new JdbcPagingItemReaderBuilder<CustomerInput>()
        .name("customerPagingReader")
        .dataSource(dataSource)
        .selectClause("SELECT customer_id, full_name, email")
        .fromClause("FROM customer_import_source")
        .whereClause("WHERE active = true")
        .sortKeys(Map.of("customer_id", Order.ASCENDING))
        .rowMapper((rs, rowNum) -> new CustomerInput(
            rs.getString("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        ))
        .pageSize(500)
        .build();
}
~~~

In the example, the WHERE condition is part of the definition of the source set: only customers with active = true belong to the import batch. The customer_id sort key helps keep the page order stable if this key is unique and does not change while the Job runs.

If the sort key is not unique, rows with the same value may be paginated unstably. Add a unique key or use a set of sort keys that determines the entire order.

### Data Changing While Reading

If the source table is updated while the Job is paging, the result may no longer be a consistent snapshot. Depending on the database and the transaction isolation, adding, deleting, or changing the sort key may cause a record to appear on a different page or be skipped.

Some ways to control this:

- Choose a fixed batch range, for example batch_id or business_date.
- Use snapshot isolation when appropriate.
- Use an ascending key that does not change as the sort key.
- Do not change the input data set while the Job is processing if strict consistency is required.
- Record the query criteria so the source count can be reconciled.

## 7. Custom Readers: Managing Iterator State Correctly

When implementing a custom ItemReader, make sure each read() consumes exactly one item and returns null only when the iterator is exhausted.

Example of a simple reader for a fixed list:

~~~java
public class ListItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public ListItemReader(List<T> items) {
        this.iterator = items.iterator();
    }

    @Override
    public T read() {
        if (!iterator.hasNext()) {
            return null;
        }

        return iterator.next();
    }
}
~~~

This reader suits a small, fixed in-memory data set. It does not support restart on its own because the iterator position is not saved in the ExecutionContext.

### Do Not Use a Loop to Silently Drop Items

If the reader needs to filter data, code like the following can cause records to be lost without a trace:

~~~java
public Customer read() {
    while (iterator.hasNext()) {
        Customer item = iterator.next();

        if (item.isEligible()) {
            return item;
        }
    }

    return null;
}
~~~

In this case, ineligible items are dropped in the reader and are not recorded in filterCount. If this is a business rule, move the check to the processor or create separate statistics for removals.

A more transparent approach:

~~~java
public CustomerInput read() {
    if (!iterator.hasNext()) {
        return null;
    }

    return iterator.next();
}
~~~

Then the processor decides whether an item is kept.

### Do Not Call read() to Check in Advance

Do not call reader.read() in a data-check function, discard the result, and then let Spring Batch call read() again. This approach consumes the first item and the framework never receives it.

If you need to check the source before running, use a separate preflight step or check the source's metadata without consuming its content.

## 8. Restart and Reader State

A reader may read correctly on the first run but lose items or read items twice when the Job restarts if it does not save and restore the read position.

Many readers support ItemStream to save state:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

With a reader that supports ItemStream:

- open() restores the read position from the ExecutionContext.
- update() saves the current state at a checkpoint.
- close() closes resources when the Step ends.

For example, FlatFileItemReader can save the line position it has read. When the Job restarts, the reader uses the ExecutionContext to continue at the position corresponding to the committed chunk.

### saveState

Readers built with a builder usually support configuring saveState. When restart is needed, do not disable state saving without a replacement design.

If saveState is disabled or a custom reader does not save the position:

- A restart may start reading from the beginning again.
- Items already written in a previous chunk may be read and written again.
- If the source changes, the order and the set of items may differ from the first run.
- The count reconciliation may not match.

Not saving state does not mean the reader will return null early in the current run, but it can cause a restart to not continue from the correct position.

### Implementing ItemStreamReader Yourself

A custom reader that needs restart can implement ItemStreamReader and save an index:

~~~java
public class RestartableListReader
        implements ItemStreamReader<String> {

    private final List<String> items;
    private int currentIndex;

    public RestartableListReader(List<String> items) {
        this.items = items;
    }

    @Override
    public String read() {
        if (currentIndex >= items.size()) {
            return null;
        }

        return items.get(currentIndex++);
    }

    @Override
    public void open(ExecutionContext context) {
        currentIndex = context.getInt("current.index", 0);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt("current.index", currentIndex);
    }

    @Override
    public void close() {
        // Close resources if the reader uses any.
    }
}
~~~

This is an illustrative example for a fixed list source. In practice, the source must be stable between the first run and the restart. If the list is re-sorted or its content changes, saving a plain index may cause the reader to skip or repeat items. With a database source, you should usually save the key or the query position using an appropriate mechanism.

## 9. Rollback and Re-reading Items

In a chunk-oriented Step, the reader may have already read some items before the writer fails. When the transaction rolls back, Spring Batch needs to handle re-reading the items belonging to the uncommitted chunk.

Many standard readers support buffering and checkpoint mechanisms so the framework can recover the data read. However, a custom reader needs to understand clearly how it interacts with transactions and rollback.

Some notes:

- Do not delete or acknowledge an item from an external source before the chunk commits unless there is a recovery mechanism.
- With a message queue, you need to understand the broker's acknowledgment and transaction.
- With a reader that has side effects, a database rollback does not automatically undo those side effects.
- A custom reader should support ItemStream if it needs to save a checkpoint.
- Test the scenario where the writer fails to confirm that uncommitted items are not lost.

If the source is a queue, fetching a message may make the message disappear from the queue or move to an in-flight state. You need to configure acknowledgment, transaction, or redelivery appropriately so the message is redelivered when the chunk fails. You cannot rely on a database rollback to ensure the message is returned to the queue.

## 10. Observing Item Counts to Detect Data Loss

A reader that silently drops items can cause a Job to complete without an exception. Therefore, you need to reconcile the figures across the source, reader, processor, and writer.

Some counters in StepExecution:

| Counter | Meaning |
|---|---|
| readCount | Number of items the reader returned successfully |
| writeCount | Number of items the writer wrote successfully |
| filterCount | Number of items the processor filtered by returning null |
| readSkipCount | Number of read errors skipped |
| processSkipCount | Number of processing errors skipped |
| writeSkipCount | Number of write errors skipped |
| commitCount | Number of commits |
| rollbackCount | Number of rollbacks |

Example:

- The source has 1,000 data lines.
- The reader returns 1,000 items.
- The processor filters 20 items.
- The writer writes 980 items.

The result can be reconciled as follows:

~~~text
readCount   = 1000
filterCount = 20
writeCount  = 980
~~~

If the reader silently drops 20 lines, readCount may be only 980 and filterCount 0. When there is no independent source figure to compare against, the Job may look like it processed successfully.

Therefore, for important Jobs, you should record the number of input records from the source or from the batch manifest. After the Step completes, compare the expected count with readCount, filterCount, the skip counts, and writeCount using a reconciliation formula appropriate to the business.

readCount does not always have to equal writeCount. The processor may filter items and the skip policy may skip faulty records. What is needed is that every discrepancy is explained by figures and defined rules.

### ItemReadListener

ItemReadListener provides callbacks to observe the reading process:

~~~java
public interface ItemReadListener<T> {
    void beforeRead();
    void afterRead(T item);
    void onReadError(Exception ex);
}
~~~

You can use a listener to log or collect metrics:

~~~java
@Bean
ItemReadListener<CustomerInput> customerReadListener() {
    return new ItemReadListener<>() {
        @Override
        public void beforeRead() {
            // Can increment a metric for the number of reader calls.
        }

        @Override
        public void afterRead(CustomerInput item) {
            // Record that an item was read successfully.
        }

        @Override
        public void onReadError(Exception ex) {
            // Record the read error for monitoring.
        }
    };
}
~~~

The listener is not invoked as a successful-read callback for the EOF null signal. onReadError is called when the reader throws an exception. If the reader itself returns null to hide an error, the listener cannot recognize it as an error; therefore keeping the read() contract correct is very important.

## 11. Readers with Multiple Sources or Multiple Delegates

A Job may read from multiple sources: multiple files, multiple tables, or multiple APIs. When using CompositeItemReader or a custom reader that coordinates multiple delegates, you need to manage precisely when to switch sources.

Example of a reader that chains two sources in order:

~~~java
public class TwoSourceReader implements ItemReader<CustomerInput> {

    private final ItemReader<CustomerInput> first;
    private final ItemReader<CustomerInput> second;
    private boolean firstFinished;

    public TwoSourceReader(
            ItemReader<CustomerInput> first,
            ItemReader<CustomerInput> second) {
        this.first = first;
        this.second = second;
    }

    @Override
    public CustomerInput read() throws Exception {
        if (!firstFinished) {
            CustomerInput item = first.read();

            if (item != null) {
                return item;
            }

            firstFinished = true;
        }

        return second.read();
    }
}
~~~

In the example, the null from the first reader only marks that the first source has been exhausted. The coordinating reader moves on to the second source; only when the second reader also returns null does the whole reader end.

If a custom reader returns null as soon as the first source is exhausted, the framework will not know there is a second source and will end the Step early.

With multiple delegates, you need to save the current delegate's state in the ExecutionContext so that a restart does not return to the wrong source or skip data that has not been processed. If a delegate has an ItemStream, make sure the delegates are opened, updated, and closed in the proper lifecycle.

## 12. Thread Safety and Parallel Reading

When a Step processes in parallel, multiple threads may access the reader at the same time depending on the configuration. Not every ItemReader is thread-safe.

A reader based on a shared iterator or pointer may suffer from:

- Two threads reading the same item.
- An item being skipped due to an unsynchronized index update.
- The item order changing unexpectedly.
- An inconsistent checkpoint state.

Some design directions:

- Use partitioning so each worker has its own source or data range.
- Use a thread-safe reader or an appropriate synchronized wrapper.
- Avoid sharing an unsynchronized iterator between multiple threads.
- With paging, divide the ranges by key or a non-overlapping partition key.
- Test with real concurrency instead of only running single-threaded.

If processing order matters, you need to determine clearly whether the parallel execution model guarantees order. Do not assume that because the reader returns items in source order, the writer will also complete in that order when multiple threads process together.

## 13. Testing to Detect a Reader Skipping Items

A reader needs to be tested with a source whose item count and order can be determined. Cases to include:

| Source data | Expected behavior |
|---|---|
| A source with many valid items | Returns each item exactly once, then null |
| An empty source | Returns null on the first read |
| A blank line in the middle of the file | Handled according to the defined rule, does not end early |
| A malformed line | Throws an exception or is skipped per the policy |
| A file that does not exist | Reports an error if the file is mandatory |
| A file with only a header | Ends normally with 0 items if that is valid input |
| A reader with multiple delegates | Returns null only when all sources are exhausted |
| The writer fails mid-chunk | Uncommitted items are reprocessed correctly by the restart mechanism |
| Job restart | The reader restores the checkpoint position correctly |

Example of testing a simple reader:

~~~java
@Test
void returnsEveryItemBeforeEndOfInput() throws Exception {
    ListItemReader<String> reader =
        new ListItemReader<>(List.of("A", "B", "C"));

    assertEquals("A", reader.read());
    assertEquals("B", reader.read());
    assertEquals("C", reader.read());
    assertNull(reader.read());
    assertNull(reader.read());
}
~~~

This test confirms that the reader returns all the items and signals EOF only after the last item. For a file or database reader, use a test source with a determined count and order to compare the results.

### Testing That a Faulty Line Does Not End Reading Early

An integration test should have a file containing a faulty line between valid lines:

~~~text
customer_id,full_name,email
C001,An,an@example.test
C002,Binh
C003,Chi,chi@example.test
~~~

If line C002 has the wrong structure, the Job must have the defined behavior: fail, or skip with recording. Line C003 after it must not silently disappear just because the reader returned null when it encountered C002.

If you configure skip for parse errors, confirm that C001 and C003 are processed, C002 is written to the reject log or error table, and the skip count increases correctly.

## 14. Designing a Reader That Is Easy to Control

An operations-friendly reader should have these characteristics:

- It is responsible only for fetching and mapping items from the source.
- It returns null only when it has determined the source is exhausted.
- It does not swallow exceptions and treat an error as EOF.
- It does not filter business items itself without a policy and statistics.
- It uses a stable order when paging.
- It handles headers, comments, blank lines, and malformed formats explicitly.
- It has a checkpoint if the Job needs to restart.
- It does not share read state unsafely between threads.
- It has source figures to compare with readCount and the other counters.

When you need to remove data, determine whether it is business filtering, error skipping, or a source selection condition. Each approach needs to be expressed in the right component so the Job can explain why an item does not appear in the output.

## 15. Process to Follow When Missing Items Are Detected

If a Job completes but the output count is lower than expected, you can investigate in this order:

1. **Determine the source count:** get the number of lines or records under the same batch condition.
2. **Check readCount:** determine how many items the reader returned.
3. **Check filterCount:** see how many items the processor filtered.
4. **Check the skip counts:** see which read, processing, or write errors were skipped.
5. **Check the reader configuration:** resource, WHERE clause, header, encoding, strict mode, page size, and sort key.
6. **Check exceptions/logs:** look for parse errors or source errors that were handled incorrectly.
7. **Check the custom reader:** look for branches that return null, loops that drop items, iterators consumed multiple times, or wrong index state.
8. **Check restart:** confirm the ExecutionContext and checkpoint restore correctly.
9. **Reconcile the output:** compare the written data with the set of input items after filtering and skipping.
10. **Fix the cause:** add checks and metrics so a later run can detect discrepancies early.

Do not immediately rerun a Job whose writer is not idempotent before determining which chunks have been committed. Rerunning incorrectly can create duplicate data and make the investigation harder.

## 16. Points to Remember

- ItemReader returns one item per read; null only means the source is exhausted.
- A blank line, a faulty record, or a source that temporarily has no data does not automatically mean EOF.
- Do not catch an exception and return null, because this turns an error into a normal end.
- Use an ItemProcessor that returns null to filter items by business rules.
- Use a skip policy when you need to skip exceptions that are classified and clearly limited.
- Configure FlatFileItemReader with the right resource, encoding, header, and strict mode.
- With a paging reader, use a stable sort key and a consistent data range.
- A custom reader must consume each item exactly once and manage restart state.
- A reader coordinating multiple sources ends only when all delegates are exhausted.
- Reconcile the source count with readCount, filterCount, the skip counts, and writeCount.
- Test mid-source errors, EOF, restart, and parallel execution to detect lost items.

Keeping the ItemReader contract correct helps Spring Batch clearly distinguish data that was read, data that was filtered, faulty data, and the point at which the source truly ends. This way, the Job avoids completing while silently missing records.


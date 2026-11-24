# ItemReader Reads One Item at a Time

In Spring Batch, an ItemReader is the component that supplies input data to a Step. Its contract is very simple: each time the framework calls read(), the reader returns at most one item; when there is no more data, the reader returns null.

The reader does not decide the chunk size and does not need to collect a list of items to hand to the writer. Spring Batch calls read() repeatedly, gathers the items into a chunk according to the Step configuration, and only then passes the chunk to the processor and writer.

## 1. The ItemReader Contract

The ItemReader<T> interface has one main method:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

Each time read() is called:

- It returns a T object representing the item that was just read.
- It returns null when the data source is exhausted.
- It may throw an exception if the item cannot be read because of a data source error or a conversion error.

The reader returns a logical item, not necessarily a physical line. For example, an item may be a Customer mapped from one CSV line, an Order built from several database columns, or a message that has been converted into a business object.

If the data source has 1,000 records and no item is filtered or skipped, the framework may call read() to receive 1,000 items in turn, and then receive null on the read that determines the end of the source.

~~~text
read() call 1  -> Customer A
read() call 2  -> Customer B
read() call 3  -> Customer C
...
read() call N  -> Customer N
read() call N+1 -> null (no more data)
~~~

This is a forward-only reading model. The reader usually keeps internal state such as the current line position, the result cursor, or the next page of data so that it knows which item the next call must return.

### null has a special meaning

The null value is the end-of-data signal. The framework understands that the reader has no more items to provide in the current run.

Therefore, do not use null to represent an empty business record or a valid null value in the source. If the input data may contain null values, map them to a wrapper object or a data type that can clearly represent that state.

For example, instead of returning null for a blank line that has business meaning, you can return an InputRecord object with an empty value field and an appropriate status. In that case, null remains reserved for the EOF (end of file/end of input) signal.

## 2. How Does Spring Batch Call read() and Create Chunks?

With a chunk-oriented Step, the framework repeats reading until it reaches the commit interval or the reader reports that there is no more data. Then the items that were read are processed and written in one chunk.

Example of configuring a chunk size of 3:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(3, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

Suppose the source has 8 items and there are no errors or filtered items:

~~~text
Chunk 1:
  read() -> A
  read() -> B
  read() -> C
  process A, B, C
  write [A, B, C]
  commit

Chunk 2:
  read() -> D
  read() -> E
  read() -> F
  process D, E, F
  write [D, E, F]
  commit

Chunk 3:
  read() -> G
  read() -> H
  read() -> null
  process G, H
  write [G, H]
  commit
~~~

The last chunk can be smaller than the commit interval because the source is exhausted. The writer receives two items in the last chunk and does not need to wait for a third.

Key points:

- One call to read() returns one item.
- A chunk can contain multiple items.
- The commit interval determines the maximum number of items the framework gathers into a chunk according to the configuration.
- The framework coordinates when the reader, processor, and writer are called and when the transaction is committed.
- The reader does not need to know how many items the current chunk has.

If the processor filters an item or the skip policy skips a failed item, the number of items the writer receives may be smaller than the number of items the reader provided. This does not change the contract of reading one item at a time.

## 3. Distinguishing End of Data, Filter, and Skip

These three situations have different meanings and must be handled correctly in the right component.

### End of data: the reader returns null

When read() returns null, the framework understands that the input source has ended. The Step can complete after writing the last remaining chunk.

~~~java
@Override
public Customer read() {
    if (!iterator.hasNext()) {
        return null;
    }

    return iterator.next();
}
~~~

### Filter: the processor returns null

When the reader returns a valid item but the processor decides not to pass that item down to the writer, the processor returns null.

~~~java
@Bean
ItemProcessor<Customer, Customer> activeCustomerProcessor() {
    return customer -> {
        if (!customer.isActive()) {
            return null;
        }

        return customer;
    };
}
~~~

In this case, the reader has still read the item. The processor deliberately filters the item and the writer does not receive it. The framework distinguishes this filtering from the reader running out of data.

### Skip: an error the policy allows to be skipped

If the reader or processor encounters an error of a type configured for skipping, Spring Batch can skip the failed item and continue processing within the configured skip limit.

~~~java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
~~~

In the example, the Step can skip up to 10 FlatFileParseException errors according to the skip configuration. If the limit is exceeded, the Step fails. A real policy needs to choose appropriate exception types; do not skip errors that cause incorrect business data without a mechanism to record and handle them.

| Situation | Component that signals it | Meaning |
|---|---|---|
| Reader returns null | ItemReader | No more items to read |
| Processor returns null | ItemProcessor | The item is filtered and not written |
| Reader/processor throws a skippable error | ItemReader or ItemProcessor | The failed item is skipped according to the skip policy |
| Reader throws an unhandled error | ItemReader | The Step may fail or retry depending on the configuration |

Do not return null when encountering a parse error or a source access error just to let the Step end normally. Doing so can make the framework wrongly conclude that the source is exhausted and silently miss the remaining data.

## 4. Writing a Simple Custom ItemReader

When the data source has no suitable prebuilt reader, you can implement ItemReader<T>.

The example below reads Customers one by one from an in-memory list:

~~~java
public class CustomerListReader implements ItemReader<Customer> {

    private final Iterator<Customer> customers;

    public CustomerListReader(List<Customer> customers) {
        this.customers = customers.iterator();
    }

    @Override
    public Customer read() {
        if (customers.hasNext()) {
            return customers.next();
        }

        return null;
    }
}
~~~

This reader creates an iterator from the list, each read() call takes one Customer, and when the iterator has no more elements it returns null. It does not pre-build a chunk or return the whole list.

This is an example that illustrates the ItemReader contract. It keeps the iterator in memory, does not save a checkpoint, and is not suitable for very large lists or for requirements to restart after the application restarts. In a real application, use a reader with a state mechanism appropriate to the data source.

If you use a custom reader in Spring, consider the bean's scope. A reader that holds read state should usually be created per StepExecution, for example by using @StepScope, to avoid multiple runs sharing the same iterator or cursor.

## 5. Using Spring Batch's Built-in Readers

Spring Batch provides many readers for working with common data sources. They still follow the principle that each read() call returns one item.

| Reader | Data source / how it reads | When it fits |
|---|---|---|
| FlatFileItemReader | Text files such as CSV or fixed-width | Importing data from files |
| JsonItemReader | JSON based on token/object configuration | Reading JSON files |
| JdbcCursorItemReader | JDBC ResultSet via a cursor | Sequentially reading a large query |
| JdbcPagingItemReader | Reads page by page from the database | When paging suits the database |
| JpaPagingItemReader | Reads entities page by page via JPA | Processing JPA data in groups |
| RepositoryItemReader | Calls a Spring Data repository page by page | Leveraging an existing repository |
| StaxEventItemReader | XML by event and fragment | Reading structured XML |

The choice of reader depends on data size, restartability, data ordering, database resources, and the source's consistency requirements.

### FlatFileItemReader Example

Suppose the CSV file contains one customer per line. FlatFileItemReader can read each line and map it to a String or an object.

A simple example that returns each raw line:

~~~java
@Bean
@StepScope
FlatFileItemReader<String> customerLineReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<String>()
            .name("customerLineReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper((line, lineNumber) -> line)
            .saveState(true)
            .build();
}
~~~

Spring Batch calls read() to get the next line. The reader manages opening the file, reading each line, detecting EOF, and closing the resource according to the Step lifecycle.

If you need to map the CSV to a Customer, you can configure a tokenizer and a FieldSetMapper or an appropriate LineMapper. In that case, each read() call returns a Customer instead of a String.

### JDBC Cursor Reader Example

JdbcCursorItemReader suits sequential reading through a ResultSet:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerCursorReader(
        DataSource dataSource) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerCursorReader")
            .dataSource(dataSource)
            .sql("select id, name, email from customer order by id")
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("name"),
                    rs.getString("email")))
            .saveState(true)
            .build();
}
~~~

The reader opens a cursor and each read() call maps the next row to a Customer. When there are no more rows, it returns null. Using ORDER BY with a stable key keeps the data order clear.

A cursor may hold a connection and database resources for the duration of the Step. Consider timeouts, cursor limits, transactions, and whether the database supports cursors in the deployment environment.

### Paging Reader

JdbcPagingItemReader and other paging readers query data page by page. The framework still sees items one at a time through read(), even though the reader may fetch a page of many rows from the database and then return each row in that page in turn.

With paging, you need a stable and unique sort key or a sufficiently deterministic order. If the order is not stable, records may be repeated or missed between pages, especially when the source data changes while the job is running.

Paging may be suitable when you do not want to keep a database cursor open for the entire Step, but the number of queries and the performance depend on the page size, indexes, the query, and the rate of data change.

## 6. Resource Lifecycle with ItemStream

Many readers work with resources that need to be opened and closed, such as files, cursors, or connections. Spring Batch supports this lifecycle through the ItemStream interface.

ItemStream has three main callbacks:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

A reader that needs to manage state can implement ItemStreamReader<T>, which combines ItemReader<T> and ItemStream.

- **open:** opens the resource and restores state from the ExecutionContext if this is a restart.
- **update:** writes the current state into the ExecutionContext when the framework is about to save a checkpoint.
- **close:** closes the resource and releases resources when the Step ends.

Prebuilt readers such as FlatFileItemReader and JdbcCursorItemReader already integrate resource and state management. When using them, give the reader a stable name and enable saveState if restart is needed.

If you wrap an ItemStream reader inside a delegate or composite reader, make sure the delegate is registered so that the open, update, and close callbacks are invoked. An object being inside another reader does not always automatically mean its lifecycle is managed.

### saveState

With the builders of many prebuilt readers, saveState(true) enables state saving for restart. If you disable saveState or use a reader that does not support ItemStream, the framework may be unable to restore the read position after the Step fails.

Not every reader needs to save state. For example, a reader that reads immutable data from the beginning each time and is designed to be safely reprocessed may not need a checkpoint. But this must be a deliberate decision because it affects rerun time and the ability to avoid duplicate data.

## 7. Reader and Checkpoints on Restart

A restartable reader must save enough state to know which item to provide next after the Job is restarted.

For a file, the state may include the read position or the line number. For database paging, the state may include the page and the position within the page, or the information needed to continue the query. The details depend on the reader's implementation.

Example restart flow:

~~~text
First run:
  read items 1 ... 100
  write chunk 1
  commit checkpoint at item 100

  read items 101 ... 200
  writer encounters an error
  rollback chunk 2
  Step FAILED

Restart the same JobInstance:
  reader reopens from the committed checkpoint
  continues processing from the appropriate position
~~~

The checkpoint is stored in the Step ExecutionContext and the JobRepository metadata. When the same JobInstance is restarted, Spring Batch uses the saved state if the reader supports restart.

You need to keep the source data unchanged or ensure it has a clear version identifier. If a file is replaced, a line is inserted, or the database changes order between two runs, the old checkpoint position may no longer correspond to the same record.

For frequently changing data, consider a snapshot, a staging table, a watermark, or a stable paging key. For example, you can limit the query to a maximum ID captured at the time the Job starts so that newly added records do not change the processing scope between restarts.

## 8. The Reader Should Not Manage Chunks or Write Data

The ItemReader's responsibility is to fetch the next item from the data source. The reader should not call the ItemWriter itself, commit transactions itself, or decide on its own when a chunk ends.

The separated responsibilities:

~~~text
ItemReader
  |
  | one item per read()
  v
ItemProcessor (optional)
  |
  | transform or filter
  v
Chunk
  |
  | reaches commit interval or EOF
  v
ItemWriter
  |
  v
Commit transaction
~~~

This separation allows you to replace the reader without changing the write logic, or replace the writer without changing how data is read.

For example, the same ItemProcessor and ItemWriter can be reused for data coming from a file, a database, or an API, as long as the readers return the same item type and satisfy the same business rules.

The reader also should not hold all of the source data in memory if the source is very large. Sequential reading or paging helps bound memory. If an item is a large aggregate, consider the object size and how related data is loaded.

## 9. Error Handling in read()

read() can fail for many reasons:

- The file does not exist or cannot be read.
- A CSV line is malformed.
- The database loses its connection or the query fails.
- An API times out or returns an invalid response.
- The source data violates conversion rules.

Do not turn every error into null. Returning null means end of data, so if the reader encounters an error midway through a file and returns null, the Step may finish successfully even though the data after that point has not been processed.

Let the exception propagate and configure retry/skip appropriately when needed. For example, a temporary connection error may be suitable for retry; some parse errors may be skipped if the business allows it and the faulty data is recorded. Configuration errors such as a missing file should usually make the Step fail so that the operator can handle them.

When diagnosis is needed, log the position or line number, the record code, and a non-sensitive error type. Avoid logging the entire record content if it contains personal data, tokens, or security information.

## 10. Thread Safety and Multiple Reader Executions

An ItemReader has internal state such as an iterator, a cursor, or a page index. If multiple threads call the same instance concurrently, the reads may race on the state and lead to repeated or skipped items.

When using a multi-threaded Step or partitioning:

- Determine whether the reader instance is shared or created separately for each thread/partition.
- Choose a reader that supports appropriate concurrency.
- If necessary, use a synchronized reader or divide the source into independent ranges.
- Do not share a mutable iterator across multiple StepExecutions.
- Save a separate checkpoint for each partition when the partition model requires it.

@StepScope helps create beans scoped to a StepExecution, which is useful when the reader receives JobParameters or needs its own state. However, step scope does not by itself make a reader thread-safe if the same instance is still called concurrently by multiple threads within the same Step.

With partitioning, it is usually best to give each partition its own data range, for example IDs from A to B, and give each partition its own reader/state. The partitioning approach must ensure that the ranges do not overlap and that they fully cover the target data.

## 11. Testing an ItemReader

A reader should be tested in isolation to confirm the contract of reading item by item and the behavior at the end of the source.

For a simple reader, you can check:

~~~java
@Test
void readReturnsOneItemAtATimeThenNull() throws Exception {
    Customer first = new Customer(1L, "An", "an@example.test");
    Customer second = new Customer(2L, "Binh", "binh@example.test");

    ItemReader<Customer> reader =
            new CustomerListReader(List.of(first, second));

    assertEquals(first, reader.read());
    assertEquals(second, reader.read());
    assertNull(reader.read());
    assertNull(reader.read());
}
~~~

This test confirms that each read() call returns one item, and then returns null once the iterator is exhausted. It does not test restart because the reader in the example only uses an in-memory iterator.

For a reader with an ItemStream, also check:

- open with an empty ExecutionContext starts from the beginning.
- update writes the necessary state.
- open with a saved ExecutionContext restores the read position.
- close releases the resource.
- After the Step restarts, committed data is not missed or read twice.
- Data source errors are propagated with the expected exception type.

For FlatFileItemReader, you should test files with a header, blank lines, special characters, encoding, parse errors, and the empty-file case. For a JDBC reader, check result ordering, paging/cursor, the connection, and data that changes while running.

## 12. Common Mistakes When Implementing an ItemReader

**Returning null when an error occurs.** The framework interprets this as EOF and may end the Step early. Throw an appropriate exception.

**Returning the whole list yourself.** ItemReader has a contract of one item at a time. Let the framework gather chunks.

**Confusing filter with EOF.** If you want to drop an item but keep reading subsequent items, use an ItemProcessor that returns null or an appropriate skip policy; do not return null from the reader.

**Using a stateful singleton reader across multiple runs.** The iterator or cursor may already be at the end when another Job starts. Use an appropriate scope or create a new instance for each StepExecution.

**Not saving state when restart is needed.** If the reader does not support ItemStream or saveState is disabled, the Step may have to read again from the beginning or may be unable to continue as desired.

**A data source without a stable order.** Paging or position-based checkpoints can repeat or miss items if the order changes. Use a stable sort key and a well-defined data range.

**Not closing resources.** A cursor or file may hold resources after the Step ends if the lifecycle is not managed correctly. Prefer prebuilt readers or fully implement ItemStream.

## 13. How to Choose and Configure a Reader

When starting a Step, clearly determine:

1. What is a business item: a file line, a database row, a message, or an aggregate object?
2. Can the data source be read sequentially, by cursor, or by page?
3. What are the data size and the memory limits?
4. Is restart from a checkpoint needed?
5. Can the source data change while running or between restarts?
6. Does the reader need to run concurrently across multiple threads or partitions?
7. Which error types can be retried, which may be skipped, and which must make the Step fail?
8. Who is responsible for opening/closing resources and saving state?

For a stable text file, FlatFileItemReader is usually the natural choice. For a large database query, choose a cursor or paging based on the database characteristics and operational requirements. For an API or a custom source, implement your own ItemReader and add ItemStream if state needs to be saved.

Whichever implementation you choose, the principle does not change: each read() call provides one item; null marks the end of data; Spring Batch coordinates gathering items into chunks, processing, writing, and committing. When the reader fulfills that contract correctly and manages state/resources appropriately, the Step can process data sequentially, track progress, and recover reliably when a restart is needed.


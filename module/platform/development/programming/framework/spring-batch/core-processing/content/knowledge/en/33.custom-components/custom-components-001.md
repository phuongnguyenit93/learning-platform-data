# Writing a Custom ItemReader in Spring Batch

In Spring Batch, `ItemReader` is the component that provides each input item to a chunk-oriented `Step`. A reader can fetch data from a file, API, message queue, device, custom format, or any source that built-in readers do not directly support.

Writing a custom `ItemReader` gives the application control over how to connect to the source, convert data into objects, detect end of data, and store checkpoints for restarts. A reader must follow a small but important contract: each call to `read()` returns one item or returns `null` when data is exhausted. Read errors must be represented by exceptions; never pretend data is exhausted by returning `null`.

A production reader often needs more than just the `read()` method. If it holds a cursor, file handle, page position, or read state, implement `ItemStream` to open resources, save state, and close resources. When properly registered with a `Step`, Spring Batch can invoke that lifecycle and restore the checkpoint on restart.

This lesson covers the `ItemReader` contract, how to write simple and restartable readers, how to read files and paginated APIs, how to integrate with `StepScope`, how to handle errors and resources, as well as testing and concurrency strategies.

## 1. What Does ItemReader Do in a Chunk-Oriented Step?

A chunk-oriented `Step` reads items until the commit interval is reached or data is exhausted. Each item is passed through a processor if present, and then the results are handed to a writer.

~~~mermaid
flowchart LR
    A["Data source"] --> B["ItemReader.read()"]
    B --> C["ItemProcessor"]
    C --> D["ItemWriter.write(chunk)"]
    D --> E["Commit transaction"]
    B --> F["EOF: return null"]
    F --> G["End reading"]
~~~

Example `Step` processing each `Customer`:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerInput, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .build();
}
~~~

The reader provides `CustomerInput`. The processor can normalize or validate the data and return `Customer`. The writer receives a `Chunk<Customer>` to write.

The reader does not decide when to commit. The transaction boundary belongs to the `Step` and the transaction manager. The reader is responsible for supplying data in the right order and according to source state.

## 2. The ItemReader Contract

The basic interface has a single method:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

Each call to `read()`:

- Returns an item if data remains.
- Returns `null` when the source has no more data.
- Throws an exception if data cannot be read or processed according to contract.

Spring Batch keeps calling `read()` until it receives `null`. Therefore, `null` means end of the input source, not an empty item or a temporary error.

### Do Not Return null to Represent Errors

Suppose a reader calls an API and gets HTTP 503. If the reader returns `null`, Spring Batch interprets that the batch has finished its data and completes the `Step` normally. The remaining items may never be read.

The right approach is to throw a meaningful exception:

~~~java
@Override
public CustomerInput read() throws Exception {
    ApiResponse response = client.fetchNext();

    if (response.isTemporarilyUnavailable()) {
        throw new TransientDataAccessException(
            "Data source is temporarily unavailable"
        );
    }

    if (response.isEndOfData()) {
        return null;
    }

    return map(response);
}
~~~

Exceptions can be handled by the `Step`'s retry, skip, or failure policy. Choose appropriate exception types so the policy can distinguish transient errors from data errors.

### The Reader Must Make Progress

Each call to `read()` must advance to the next state or terminate. If a reader returns the same item repeatedly without advancing its cursor, the `Step` can loop indefinitely.

When the source has duplicate data, define a stable key or cursor to ensure the reader makes progress.

## 3. Simple Stateless Readers

If the data source is small, immutable, and does not need restartability, the reader can simply implement `ItemReader`.

~~~java
public class ListItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public ListItemReader(List<T> items) {
        this.iterator = items.iterator();
    }

    @Override
    public T read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
~~~

This works well for small test fixtures, static configuration lists, or pre-loaded bounded sources.

However, this reader does not store its current position in `ExecutionContext`. If the `Job` fails and restarts, Spring Batch does not know how far the iterator had read. A new reader instance will start over from the beginning.

For large datasets or jobs that require restarts, do not load the entire source into a `List` just to use an iterator. Read via a stream, cursor, or page and store checkpoints.

## 4. When Should You Implement ItemStream?

Spring Batch provides `ItemStream` so a reader can participate in the `Step` lifecycle:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

In practice, these methods can throw `ItemStreamException`.

- `open()` opens resources and restores saved state.
- `update()` writes the current state to `ExecutionContext`.
- `close()` releases resources.

A stateful reader should implement `ItemStreamReader`:

~~~java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}
~~~

Use `ItemStreamReader` when the reader needs to open a file or cursor, track read position, persist a page number/offset/record ID, restore position on restart, or close a stream/cursor/connection.

A stateless reader may only need `ItemReader`. A reader with resources or checkpoints should implement `ItemStream` so the framework manages its lifecycle properly.

## 5. Writing a Line-by-Line File Reader

The first example is a custom reader that reads a text file. Each line is a `String` item. The reader tracks the number of lines returned so it can restart from the corresponding position.

~~~java
public class CheckpointingLineReader
        implements ItemStreamReader<String> {

    private static final String LINE_KEY =
        "checkpointingLineReader.currentLine";

    private final Path inputPath;

    private BufferedReader reader;
    private long currentLine;

    public CheckpointingLineReader(Path inputPath) {
        this.inputPath = inputPath;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        close();

        long savedLine = executionContext.getLong(LINE_KEY, 0L);
        BufferedReader candidate = null;

        try {
            candidate = Files.newBufferedReader(
                inputPath,
                StandardCharsets.UTF_8
            );

            for (long skipped = 0; skipped < savedLine; skipped++) {
                if (candidate.readLine() == null) {
                    throw new ItemStreamException(
                        "Checkpoint exceeds the number of lines in the file: "
                            + savedLine
                    );
                }
            }

            reader = candidate;
            candidate = null;
            currentLine = savedLine;
        } catch (IOException | RuntimeException ex) {
            if (candidate != null) {
                try {
                    candidate.close();
                } catch (IOException closeException) {
                    ex.addSuppressed(closeException);
                }
            }

            if (ex instanceof ItemStreamException streamException) {
                throw streamException;
            }

            throw new ItemStreamException(
                "Cannot open or restore file " + inputPath,
                ex
            );
        }
    }

    @Override
    public String read() {
        if (reader == null) {
            throw new IllegalStateException(
                "Reader has not been opened"
            );
        }

        try {
            String line = reader.readLine();

            if (line == null) {
                return null;
            }

            currentLine++;
            return line;
        } catch (IOException ex) {
            throw new ItemStreamException(
                "Error reading file " + inputPath,
                ex
            );
        }
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong(LINE_KEY, currentLine);
    }

    @Override
    public void close() {
        BufferedReader current = reader;
        reader = null;

        if (current != null) {
            try {
                current.close();
            } catch (IOException ex) {
                throw new ItemStreamException(
                    "Cannot close file " + inputPath,
                    ex
                );
            }
        }
    }
}
~~~

This reader has the following characteristics:

- Does not load the entire file into memory.
- Each `read()` call returns at most one line.
- EOF is represented by `null`.
- `currentLine` counts the number of lines returned.
- `update()` saves the position to `ExecutionContext`.
- `open()` skips past lines already recorded in the checkpoint.
- `close()` releases the `BufferedReader` and can be called safely multiple times.

This example illustrates line-count checkpointing. For very large files, skipping lines from the start up to the checkpoint can take time. You can use a byte offset, index, or custom cursor format if faster recovery is needed.

### Why Use Namespaced Keys?

`ExecutionContext` may hold state from multiple readers, writers, and components. A key like `currentLine` is too generic and can overwrite another component's state.

Using a dedicated prefix such as `checkpointingLineReader.currentLine` avoids collisions. Key names must remain stable across restarts and across application versions that may resume old jobs.

## 6. Meaning of a Checkpoint

A checkpoint is state indicating how far the reader has progressed at a safe persistence boundary. Spring Batch uses `ExecutionContext` to store the state of a `StepExecution`.

Example with a commit interval of 3:

~~~text
Source: A B C D E F G H

Chunk 1:
  read A, B, C
  write A, B, C
  commit
  checkpoint after C

Chunk 2:
  read D, E, F
  writer fails
  rollback chunk 2

Restart:
  restore checkpoint after C
  re-read D, E, F
~~~

The checkpoint must match committed data. If a reader writes a position ahead of committed data, a restart may skip items. If the position lags behind, some items may be re-read and the writer must handle idempotency.

Spring Batch calls `ItemStream.update()` during the chunk-managed lifecycle to update `ExecutionContext`. `JobRepository` persists the context according to the `Step`'s transactions and checkpoints. Do not independently write checkpoints to a database without understanding how it coordinates with chunk commits.

### Do Not Persist Checkpoints on Every read() Call

A reader normally writes state only when the framework calls `update()` at an appropriate boundary. If you persist the position to an external source on every `read()`, the reader can move ahead of the chunk transaction. When the writer rolls back, the data is already marked consumed and cannot be re-read.

Let `ExecutionContext` participate in the Spring Batch lifecycle, or design a source mechanism with explicit acknowledgment/transaction semantics.

## 7. Configuring a Custom Reader with Java Configuration

You can define a `@StepScope` bean to receive the file path from `JobParameters`:

~~~java
@Bean
@StepScope
ItemStreamReader<String> customLineReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
            "Missing JobParameter input.file"
        );
    }

    return new CheckpointingLineReader(Path.of(inputFile));
}
~~~

Configuring the `Step`:

~~~java
@Bean
Step importTextStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemStreamReader<String> customLineReader,
        ItemProcessor<String, CustomerInput> parser,
        ItemWriter<CustomerInput> writer) {

    return new StepBuilder("importTextStep", jobRepository)
        .<String, CustomerInput>chunk(100, transactionManager)
        .reader(customLineReader)
        .processor(parser)
        .writer(writer)
        .build();
}
~~~

`@StepScope` defers creating the target reader until the `StepExecution` is active. Therefore, the `jobParameters` expression can resolve the path for the current run.

The reader is declared with type `ItemStreamReader`, so Spring Batch recognizes both the `ItemReader` and `ItemStream` lifecycles.

### Keep State Names and Meanings Stable

Application-defined `ExecutionContext` keys must remain stable across restarts. If you change the meaning of a checkpoint, version it or provide a migration plan.

If an older `JobInstance` restarts with new code where the reader uses a different key, the reader may restart from the beginning or restore the wrong position.

## 8. Parse Data in the Reader or the Processor?

The reader can return a raw `String` line and let the processor parse it into an object:

~~~java
@Bean
ItemProcessor<String, CustomerInput> customerLineParser() {
    return line -> {
        String[] columns = line.split(",", -1);

        if (columns.length != 3) {
            throw new InvalidCustomerLineException(
                "Line does not have 3 columns: " + line
            );
        }

        return new CustomerInput(
            columns[0].trim(),
            columns[1].trim(),
            columns[2].trim()
        );
    };
}
~~~

Separating parsing into the processor can be useful when the reader is responsible only for fetching raw data, transformation rules are business logic that can be unit tested independently, or you want to apply a skip policy to item-level processing errors.

If the source format is complex, the parser may belong in the reader because it is part of the read protocol. In that case, the reader must raise clearly typed exceptions and be tested separately.

Do not use `String.split(",")` for production CSV if fields can contain commas, quotes, or newlines. Use a dedicated CSV parser or `FlatFileItemReader` if it handles the format.

## 9. Paginated API Reader

A REST source may return data in pages:

~~~json
{
  "items": [
    {"id": 101, "name": "An"},
    {"id": 102, "name": "Binh"}
  ],
  "nextPage": 2,
  "hasMore": true
}
~~~

A custom reader can hold the current page number, the list of items on the active page, the next index within the page, a continuation token if the API uses cursors, and a snapshot/cutoff so the source does not shift while the batch runs.

~~~mermaid
flowchart TD
    A["read() is called"] --> B{"Current page has remaining items?"}
    B -- "Yes" --> C["Return next item"]
    B -- "No" --> D{"API has more pages?"}
    D -- "Yes" --> E["Fetch next page"]
    E --> B
    D -- "No" --> F["Return null"]
~~~

Do not call the API up front and load all pages into a `List` if the dataset is large. Buffering only the current page keeps memory bounded.

### Pseudocode for a Paginated Reader

~~~java
public class PagedApiItemReader
        implements ItemStreamReader<ApiRecord> {

    private static final String PAGE_KEY = "pagedApiReader.page";
    private static final String INDEX_KEY = "pagedApiReader.index";

    private final ApiClient client;
    private final String batchId;

    private List<ApiRecord> pageItems = List.of();
    private int page;
    private int index;
    private boolean noMorePages;

    public PagedApiItemReader(ApiClient client, String batchId) {
        this.client = client;
        this.batchId = batchId;
    }

    @Override
    public void open(ExecutionContext context) {
        page = context.getInt(PAGE_KEY, 0);
        index = context.getInt(INDEX_KEY, 0);
        pageItems = List.of();
        noMorePages = false;

        if (index > 0) {
            pageItems = client.fetchPage(batchId, page);
            if (index > pageItems.size()) {
                throw new ItemStreamException(
                    "Invalid checkpoint index"
                );
            }
        }
    }

    @Override
    public ApiRecord read() {
        while (true) {
            if (index < pageItems.size()) {
                return pageItems.get(index++);
            }

            if (noMorePages) {
                return null;
            }

            ApiPage<ApiRecord> response =
                client.fetchPageWithMetadata(batchId, page);

            if (response == null) {
                throw new ItemStreamException(
                    "API returned null response"
                );
            }

            pageItems = response.items();
            index = 0;

            if (!response.hasMore() && pageItems.isEmpty()) {
                noMorePages = true;
                return null;
            }

            if (pageItems.isEmpty() && response.hasMore()) {
                page = response.nextPage();
                continue;
            }

            if (pageItems.isEmpty()) {
                noMorePages = true;
                return null;
            }
        }
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(PAGE_KEY, page);
        context.putInt(INDEX_KEY, index);
    }

    @Override
    public void close() {
        pageItems = List.of();
    }
}
~~~

This is pseudocode illustrating the concept and must be adapted to the concrete API contract. A production implementation must define clearly whether pages are zero-based or one-based, whether the current page is stored before or after fetching, when `nextPage` is updated, and how EOF state is restored.

A safer approach is to checkpoint using a continuation token or the last processed ID instead of page/index if the API supports it. Tokens are usually more stable when source data changes.

### Watch Out for Empty Pages

An empty page does not necessarily mean EOF. An API can return an empty page while still providing a next cursor due to filtering or its consistency model. Only terminate when API metadata confirms no more pages remain.

Conversely, if the API returns `hasMore=true` while repeatedly returning empty pages without changing the cursor, the reader can loop infinitely. Detect non-advancing cursors and throw an exception.

## 10. Stable Cursors for APIs and Databases

When the source changes while the `Job` is running, offset pagination can cause items to be missed or duplicated.

Example API using offsets:

~~~text
GET /records?offset=0&limit=100
GET /records?offset=100&limit=100
~~~

If a new record is inserted at the start of the list between two requests, offset 100 can point to different data than initially expected.

If the API supports cursor or keyset pagination, prefer it:

~~~text
GET /records?afterId=1000&limit=100
~~~

After reading the last item, the reader saves `lastId`. The next request asks for items with IDs greater than `lastId`.

Requirements:

- The ID or sort key must be stable.
- The sort order must be deterministic.
- Two records must not share the same sort key without a tie-breaker.
- A snapshot/cutoff must be fixed if new data must not enter the current batch.
- The API must clearly define inclusive vs. exclusive cursor semantics.

For databases, `JdbcPagingItemReader` already handles most paging and restart concerns. Write a custom reader only when you need a specialized source or rules that built-in readers cannot satisfy.

## 11. Writing a Custom Reader for a Database Source

If you need to read from a database with custom logic, you can use `JdbcTemplate` inside a custom reader. However, consider built-in readers first:

- `JdbcCursorItemReader` for cursors.
- `JdbcPagingItemReader` for paging.
- `RepositoryItemReader` for Spring Data repositories.

A custom database reader must decide who manages the connection, whether the cursor holds a connection across the entire `Step`, which transaction manager manages the resource, whether the reader is thread-safe, whether the checkpoint is an offset or the last key, and whether data can change between chunks.

Example keyset reader:

~~~java
public class CustomerKeysetReader
        implements ItemStreamReader<Customer> {

    private static final String LAST_ID_KEY =
        "customerKeysetReader.lastId";

    private final JdbcTemplate jdbcTemplate;
    private final int pageSize;

    private long lastId;
    private Iterator<Customer> currentPage =
        List.<Customer>of().iterator();
    private boolean exhausted;

    public CustomerKeysetReader(
            JdbcTemplate jdbcTemplate,
            int pageSize) {
        this.jdbcTemplate = jdbcTemplate;
        this.pageSize = pageSize;
    }

    @Override
    public void open(ExecutionContext context) {
        lastId = context.getLong(LAST_ID_KEY, 0L);
        currentPage = List.<Customer>of().iterator();
        exhausted = false;
    }

    @Override
    public Customer read() {
        if (currentPage.hasNext()) {
            Customer customer = currentPage.next();
            lastId = customer.id();
            return customer;
        }

        if (exhausted) {
            return null;
        }

        List<Customer> rows = jdbcTemplate.query(
            """
            SELECT customer_id, full_name
            FROM customer
            WHERE customer_id > ?
            ORDER BY customer_id
            LIMIT ?
            """,
            customerRowMapper(),
            lastId,
            pageSize
        );

        if (rows.isEmpty()) {
            exhausted = true;
            return null;
        }

        currentPage = rows.iterator();

        Customer customer = currentPage.next();
        lastId = customer.id();
        return customer;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID_KEY, lastId);
    }

    @Override
    public void close() {
        currentPage = List.<Customer>of().iterator();
    }
}
~~~

This is an example of keyset paging; you must add system-specific rules such as batch filters, tenant isolation, snapshots, null ID handling, and transaction isolation. The query must have a deterministic order. If multiple records can share the sort key, include a secondary key to break ties.

Because `JdbcTemplate` manages statements/result sets and participates in transactions via the appropriate `DataSource`, the reader does not keep a cursor open. With a custom cursor reader, implement `ItemStream` to open and close the cursor in the proper lifecycle.

### Checkpointing After the Last Item of a Page

In the example, `lastId` updates when an item is returned. When a chunk rolls back, Spring Batch manages `ExecutionContext` and reader state alongside the transaction/checkpoint. Do not independently save `lastId` into an external table on every `read()`, because that can advance ahead of the commit.

## 12. Handling Exceptions in read()

`read()` can throw checked or unchecked exceptions. Spring Batch forwards the error to the `Step`'s fault tolerance mechanism.

You should categorize errors:

| Error type | Example | Typical appropriate behavior |
|---|---|---|
| Transient source error | Timeout, connection reset | Bounded retry |
| Item data error | Malformed line | Skip if business rules allow |
| Configuration error | Invalid file path, missing credentials | Fail the Step |
| Document error | Malformed XML, truncated file | Typically fail the source/file |
| EOF | No more items | Return null |

Create semantic exceptions:

~~~java
public class InvalidCustomerRecordException
        extends RuntimeException {

    public InvalidCustomerRecordException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
~~~

When the parser encounters a bad record:

~~~java
@Override
public CustomerInput read() throws Exception {
    String line = readNextLine();

    if (line == null) {
        return null;
    }

    try {
        return parse(line);
    } catch (IllegalArgumentException ex) {
        throw new InvalidCustomerRecordException(
            "Invalid record at line " + currentLine,
            ex
        );
    }
}
~~~

If the `Step` allows skipping `InvalidCustomerRecordException`, the framework can discard the bad item according to policy. Do not collapse all exceptions into a single type because retry and skip need to distinguish them.

## 13. Retry, Skip, and Reader Position

When an item fails, the reader may already have advanced to the next position. The framework manages rollback and buffering according to the `Step` configuration. A custom reader must keep its state consistent with the `Step` lifecycle.

Principles:

- Do not commit or acknowledge the source inside `read()` before the chunk commits.
- Do not persist durable checkpoints ahead of the commit.
- Do not return `null` when encountering an exception.
- Ensure `read()` does not return the same item endlessly.
- When an item is skipped, the post-commit checkpoint must reflect that the item was handled according to policy.
- For message sources, coordinate acknowledgment/redelivery with the transaction.

If a reader consumes from an API that cannot roll back, you may need a durable cursor or writer-side idempotency. If the API provides cursor tokens, retain the token corresponding to committed items, not merely fetched items.

### Fetching a Page Differs from Committing Items

A reader may prefetch an entire page of 100 items while the `Step` has committed only the first 20 items. If the `Job` fails, the remaining 80 items in the page buffer have not been committed. On restart, the reader must resume from the checkpoint after item 20, not jump to the next page simply because the page was already downloaded.

This is why you must save the consumed index or cursor rather than only the fetched page number.

## 14. Resource-Holding Readers Must Handle Open Failures

A custom reader may open multiple resources: input streams, parsers, connections, or cursors. If `open()` opens the first resource but opening the second fails, it must close the already opened resource itself.

~~~java
@Override
public void open(ExecutionContext context) {
    InputStream candidateStream = null;
    XMLStreamReader candidateParser = null;

    try {
        candidateStream = Files.newInputStream(inputPath);
        candidateParser = xmlInputFactory.createXMLStreamReader(
            candidateStream
        );

        this.inputStream = candidateStream;
        this.xmlReader = candidateParser;
    } catch (Exception ex) {
        closeQuietly(candidateParser);
        closeQuietly(candidateStream);

        throw new ItemStreamException(
            "Cannot open XML source",
            ex
        );
    }
}
~~~

On success, the reader takes ownership of the resources and `close()` must release them. When `open()` fails, cleanup must happen immediately inside `open()` because the framework may not have registered or completed the reader's lifecycle yet.

Close in reverse order of opening: parser first, stream second. Do not close resources owned by another component.

## 15. Do Not Share Stateful Readers Across Threads

A custom reader typically holds mutable state such as current file position, page buffer, cursor, last ID, or end-of-source flag. If the reader bean is a singleton shared across multiple `JobExecution`s, state from concurrent runs can overwrite each other.

You can use `@StepScope` so each `StepExecution` gets its own target reader:

~~~java
@Bean
@StepScope
ItemStreamReader<String> customerLineReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {
    return new CheckpointingLineReader(Path.of(inputFile));
}
~~~

In partitioning, each worker `StepExecution` should have its own reader instance and `StepExecutionContext`. Do not share a single mutable reader across multiple partitions.

`StepScope` does not make a reader thread-safe if multiple threads call the same target within one `StepExecution`. For a multi-threaded `Step`, verify the concurrency contract or use a reader with proper synchronization.

## 16. Registering ItemStream in a Step

When a custom reader is passed directly to `.reader(...)` and implements `ItemStream`, Spring Batch manages the reader's lifecycle automatically.

~~~java
return new StepBuilder("customImportStep", jobRepository)
    .<String, CustomerInput>chunk(100, transactionManager)
    .reader(customLineReader)
    .processor(customerLineParser)
    .writer(customerWriter)
    .build();
~~~

If a wrapper implements only `ItemReader` while holding a delegate that implements `ItemStream`, the framework may not know the delegate needs `open`/`update`/`close`.

Example decorator that does not forward the lifecycle:

~~~java
public class LoggingReader<T> implements ItemReader<T> {

    private final ItemReader<T> delegate;

    public LoggingReader(ItemReader<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public T read() throws Exception {
        T item = delegate.read();
        log.debug("Reader returned an item");
        return item;
    }
}
~~~

If the delegate is an `ItemStreamReader`, the wrapper above does not forward the lifecycle. There are two options:

1. Have the wrapper implement `ItemStreamReader` and forward `open`/`update`/`close`.
2. Register the delegate directly via `StepBuilder.stream(delegate)` when the `Step` structure allows it.

Example forwarding wrapper:

~~~java
public class LoggingStreamReader<T>
        implements ItemStreamReader<T> {

    private final ItemStreamReader<T> delegate;

    public LoggingStreamReader(ItemStreamReader<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public T read() throws Exception {
        return delegate.read();
    }

    @Override
    public void open(ExecutionContext context) {
        delegate.open(context);
    }

    @Override
    public void update(ExecutionContext context) {
        delegate.update(context);
    }

    @Override
    public void close() {
        delegate.close();
    }
}
~~~

When writing a decorator, preserve both the read contract and the lifecycle contract. Otherwise, restarts may break even though the initial run succeeded.

## 17. Readers for Message or Queue Sources

A queue reader must clearly distinguish EOF from temporarily having no messages.

For finite batches, the source should have a deterministic termination condition—for example, processing only messages belonging to a batch ID, reading up to a watermark/timestamp cutoff, an API returning a final continuation token, or snapshotting the queue.

If the queue is unbounded, calling `read()` and blocking forever for messages will never return `null` and the `Step` will never finish. That may fit a streaming consumer design, but it is no longer a standard finite batch.

### Acknowledgment and Checkpointing

If a message is acknowledged before the chunk commits, the `Job` can lose items when the writer rolls back. If it is not acknowledged, the broker may redeliver items after a restart.

The design must coordinate:

- Message ID.
- Visibility timeout or lease.
- Acknowledgment mode.
- Transaction manager and broker transactions if supported.
- Writer idempotency keys.
- Checkpoints storing the last committed ID.

Do not treat closing the consumer as acknowledgment. Closing only releases the connection/subscription; message state depends on the broker protocol.

## 18. Naming and Versioning ExecutionContext Keys

`ExecutionContext` is durable metadata in `JobRepository`. Custom reader keys can persist across multiple restarts and across new application deployments.

Use namespaced names:

~~~java
private static final String CURRENT_LINE_KEY =
    "customerFileReader.currentLine";

private static final String LAST_ID_KEY =
    "customerApiReader.lastId";
~~~

If the checkpoint structure changes, you can store a version:

~~~java
context.putInt("customerFileReader.stateVersion", 2);
~~~

During `open()`:

- Check the version.
- Read the corresponding keys.
- Migrate legacy state if possible.
- If incompatible, throw a clear error requiring a new `JobInstance` or a controlled migration.

Do not arbitrarily rename keys or alter cursor semantics while older `JobInstance`s can still be restarted.

## 19. Unit Testing a Custom ItemReader

A unit test should verify both the `read()` contract and the lifecycle.

~~~java
@TempDir
Path tempDirectory;

@Test
void readsEachLineThenReturnsNull() throws Exception {
    Path input = tempDirectory.resolve("customers.txt");

    Files.writeString(
        input,
        "C001,An\nC002,Binh\n",
        StandardCharsets.UTF_8
    );

    CheckpointingLineReader reader =
        new CheckpointingLineReader(input);

    reader.open(new ExecutionContext());
    try {
        assertEquals("C001,An", reader.read());
        assertEquals("C002,Binh", reader.read());
        assertNull(reader.read());
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}
~~~

This test verifies that the reader opens the file, returns one line per call, preserves data order, returns `null` at EOF, continues returning `null` on subsequent `read()` calls after EOF, and closes the resource.

Add tests for empty files and blank lines. A blank line is a valid item if the source defines it as such; do not silently convert empty strings into EOF.

## 20. Testing Restartability with ExecutionContext

Reader-level restart tests can simulate restarts by sharing the same `ExecutionContext` across two reader instances:

~~~java
@Test
void resumesFromSavedLineCheckpoint() throws Exception {
    Path input = tempDirectory.resolve("customers.txt");

    Files.writeString(
        input,
        "C001,An\nC002,Binh\nC003,Chi\n",
        StandardCharsets.UTF_8
    );

    ExecutionContext context = new ExecutionContext();

    CheckpointingLineReader first =
        new CheckpointingLineReader(input);

    first.open(context);
    assertEquals("C001,An", first.read());
    assertEquals("C002,Binh", first.read());
    first.update(context);
    first.close();

    CheckpointingLineReader restarted =
        new CheckpointingLineReader(input);

    restarted.open(context);
    try {
        assertEquals("C003,Chi", restarted.read());
        assertNull(restarted.read());
    } finally {
        restarted.close();
    }
}
~~~

This test proves the reader can restore a saved checkpoint. It does not prove that Spring Batch persists `ExecutionContext` properly alongside chunk transactions; that requires a `Step` integration test.

### Testing Invalid Checkpoints

Test cases where the checkpoint exceeds the file's line count, the file changed after the checkpoint, encoding differs, the file was truncated, or legacy state keys lack a compatible version.

The reader should fail explicitly if state cannot be restored safely, rather than silently skipping data.

## 21. Testing with StepScope and Step Integration

If the reader receives `JobParameters` via `@Value`, test it in a real scope.

You can use `JobLauncherTestUtils` to run the `Step` with `input.file`:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class CustomReaderStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void readsInputFromJobParameter() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("input.file", "src/test/resources/customers.txt")
            .toJobParameters();

        JobExecution execution =
            jobLauncherTestUtils.launchStep(
                "customImportStep",
                parameters
            );

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution stepExecution =
            execution.getStepExecutions().iterator().next();

        assertEquals(2, stepExecution.getReadCount());
    }
}
~~~

The test configuration must supply the corresponding `Job`/`Step` and dedicated output resources for the test. If tests run repeatedly, avoid sharing an output file that might be overwritten or appended to.

`JobLauncherTestUtils` helps verify that `StepScope` is activated, `JobParameters` are bound, the reader is opened/updated/closed, `JobRepository` stores `StepExecution`, and the read count reflects the number of items.

Do not assert only `BatchStatus`; inspect the output or target data to verify content accuracy.

## 22. Testing Exceptions and EOF

Tests should distinguish EOF from source errors:

| Scenario | Expected result |
|---|---|
| End of file reached | `read()` returns `null` |
| Empty file valid by contract | `read()` returns `null` immediately |
| File does not exist | `open()` throws an error |
| Missing read permissions | `open()` or `read()` throws an error |
| API timeout | `read()` throws a retryable exception |
| API confirms end of data | `read()` returns `null` |
| Malformed line | Throws data exception or returns raw item for processor |
| Reader not opened yet | Throws a clear lifecycle error |

Do not write tests asserting only that every error causes the `Step` to be `FAILED`. If an exception is configured for retry or skip, the final status can differ. Test policies at the `Step` level separately.

## 23. Testing Retry, Skip, and Rollback

A custom reader can throw an exception while reading an item. A fault-tolerant `Step` can retry or skip depending on the exception policy.

~~~java
return new StepBuilder("customImportStep", jobRepository)
    .<String, CustomerInput>chunk(10, transactionManager)
    .reader(customLineReader)
    .processor(customerLineParser)
    .writer(customerWriter)
    .faultTolerant()
    .retry(TransientSourceException.class)
    .retryLimit(3)
    .skip(InvalidCustomerLineException.class)
    .skipLimit(10)
    .build();
~~~

Tests should confirm that transient errors retry up to the limit, item errors are skipped when policy permits, configuration errors are not fruitlessly retried, reader state does not drop items after rollback, skip count is accurate, the writer receives only valid items, and resources are closed when the `Step` ends.

Do not turn document parsing errors or full-source connection failures into item skips if the reader cannot safely continue.

## 24. Concurrency and Partitioning

A custom reader typically holds mutable state. Therefore, do not share the same instance across multiple threads or partitions unless the implementation is designed to be thread-safe.

With partitioning:

- Each worker has its own `StepExecution`.
- Create a separate reader per worker.
- Use `StepExecutionContext` to pass partition ranges or cursors.
- Each reader saves its own checkpoint.
- Key names must be stable and collision-free.
- Resource paths or queries must be scoped to the partition.

Example:

~~~java
@Bean
@StepScope
ItemStreamReader<Customer> partitionReader(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {
    return new CustomerRangeReader(minId, maxId);
}
~~~

In a multi-threaded `Step`, multiple threads may call the same reader target. `StepScope` does not automatically create one instance per thread. If the reader is not thread-safe, add synchronization, use a concurrency-capable reader, or choose partitioning with a dedicated reader per worker.

## 25. Common Design Mistakes

### Returning null on Transient Source Errors

Spring Batch interprets `null` as EOF. Timeouts or HTTP 503 must be thrown as exceptions to retry or fail.

### Not Implementing ItemStream for Stateful Readers

The reader may succeed on the initial run, but restarts will resume from the wrong position. Store checkpoints in `ExecutionContext`.

### Updating Checkpoints Too Early

Persisting the fetched position rather than the committed position can drop items after rollback. Checkpoints must coordinate with chunk transactions.

### Using Page Number Without In-Page Index

If a page is fetched but only some items commit, a restart must resume from the right index or last committed cursor.

### Unstable Source Ordering

Paging without a deterministic `ORDER BY` or a non-unique API sort key can duplicate or miss items.

### Loading All Data into Memory

A custom reader should not convert a large source into a `List` just to simplify code. Use streaming or paging.

### Using a Singleton for a Stateful Reader

Two `JobExecution`s can overwrite cursors or file handles. Use `StepScope` when state belongs to a `StepExecution`.

### Wrappers Dropping ItemStream

A decorator implementing only `ItemReader` can prevent the delegate from being opened/updated/closed. Forward the lifecycle or register the stream separately.

### Not Cleaning Up When open() Fails

If some resources open before an exception is thrown, close the already opened resources yourself before exiting.

### Using a Message Queue as an Infinite Source for a Finite Batch

Without a cutoff or termination condition, `read()` will never return `null` and the `Step` will never finish.

### Not Testing Restarts with Changing Source Data

The checkpoint may no longer match the source. Use snapshots, versions, or stable cursors.

### Not Checking Thread Safety

Mutable buffers and cursors can be accessed concurrently by multiple threads. Define ownership and the concurrency model clearly.

## 26. Custom ItemReader Design Checklist

Before adding a reader to a `Step`, identify:

1. **Data source:** file, database, API, queue, or custom source?
2. **What constitutes an item:** a line, record, page entry, or message?
3. **EOF:** what condition proves no more items remain?
4. **Exceptions:** which errors are transient, data-related, or configuration-related?
5. **State:** what offset, page, token, last ID, or cursor must the reader retain?
6. **Checkpoint:** what state corresponds to committed chunks?
7. **Lifecycle:** where does the reader open and close resources?
8. **Restart:** is the source stable between initial run and restart?
9. **Registration:** are the reader and any `ItemStream` delegate managed by the `Step`?
10. **Scope:** does the reader need `StepScope` to receive `JobParameters`/partition context?
11. **Concurrency:** can the reader be invoked from multiple threads or partitions?
12. **Memory:** are buffers bounded and capable of handling large sources?
13. **Observability:** do logs include batch ID, `StepExecution` ID, and cursor for investigation?
14. **Tests:** have EOF, errors, checkpoints, restarts, cleanup, and `Step` integration been verified?

## 27. When Should You Use Built-In Readers?

Spring Batch provides many readers that already handle hard details like resource lifecycle, checkpointing, and restartability.

| Source | Reader to consider |
|---|---|
| Delimited/fixed-width file | `FlatFileItemReader` |
| XML fragments | `StaxEventItemReader` |
| JDBC cursor | `JdbcCursorItemReader` |
| JDBC paging | `JdbcPagingItemReader` |
| Spring Data repository | `RepositoryItemReader` |
| Multiple file resources | `MultiResourceItemReader` |
| In-memory list | `ListItemReader` |
| Specialized source or cursor API | Custom `ItemReader`/`ItemStreamReader` |

Write a custom reader when you need a dedicated protocol or custom semantics. If you only need to change field mapping for a common source, you can use a built-in reader with a custom mapper or line mapper.

Built-in readers are typically well tested and handle tricky restart scenarios. Custom readers should focus on the parts the application genuinely needs to control.

## 28. Key Takeaways

- `ItemReader.read()` returns an item or `null` when data is exhausted.
- `null` must not be used to represent timeouts, parse errors, or connection failures.
- Simple readers can implement just `ItemReader`, while stateful readers should implement `ItemStreamReader`.
- `open()` restores resources and checkpoints; `update()` persists state; `close()` releases resources.
- `ExecutionContext` keys must be namespaced and stable across restarts.
- Checkpoints must reflect committed data, not merely fetched data.
- API pagination must save both page and consumed index/cursor; prefer stable cursors when the API supports them.
- Database readers must consider keysets, stable ordering, and the transaction manager.
- Use `@StepScope` when the reader takes `JobParameters` or `StepExecutionContext`.
- Wrappers/decorators must forward the `ItemStream` lifecycle or register the delegate with the `Step`.
- Readers with mutable state must not be shared across partitions or threads unless thread-safe.
- When `open()` fails partway through, clean up already opened resources yourself.
- Test `read`/EOF/checkpointing in isolation and test the real `Step` with `JobLauncherTestUtils`.
- Prefer built-in readers when they meet requirements; custom readers should handle only specialized source behavior.

Writing a custom `ItemReader` is not just implementing a `read()` method. A reliable reader requires a clear EOF contract, steady forward progress, checkpoints aligned with transactions, a complete resource lifecycle, and testable restart behavior. When those pieces are designed together, a custom reader integrates naturally into chunk processing and operates safely at scale.


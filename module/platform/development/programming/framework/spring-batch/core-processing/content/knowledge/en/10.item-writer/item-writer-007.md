# Writer Flush and Resource Close

In Spring Batch, **ItemWriter** writes the items that the reader has read and the processor has processed. For a writer that works on files, sockets, streams, or external resources, managing buffers and closing resources is part of the Step lifecycle.

Two operations that are often confused are **flush** and **close**:

- **Flush** pushes data sitting in the application's buffer down to the underlying write layer. The data may have been handed to the operating system but is not necessarily physically and durably written to the storage device.
- **Close** completes the write, usually flushing the remaining data and then releasing resources such as the file handle, stream, or connection that the writer owns.

In Spring Batch, a stateful writer usually participates in the **ItemStream** lifecycle: it opens resources when the Step starts, writes across many chunks, updates state at checkpoints, and closes resources when the Step ends. You need to understand this lifecycle to avoid closing the writer too early, losing data in the buffer, leaking file handles, or producing inconsistent output when a Job fails and restarts.

## 1. ItemWriter and ItemStream

The basic ItemWriter contract focuses on writing a chunk:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

ItemWriter does not directly define flush() or close() methods. A writer that needs to manage state or resources usually implements **ItemStream** as well.

ItemStream provides three lifecycle methods:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

In the actual API, the lifecycle methods may declare ItemStreamException. The interface that combines both contracts is commonly called **ItemStreamWriter**:

~~~java
public interface ItemStreamWriter<T>
        extends ItemStream, ItemWriter<T> {
}
~~~

The meaning of each method:

| Method | Role |
|---|---|
| open(ExecutionContext) | Opens resources and restores state if this is a restart |
| write(Chunk) | Writes the items of the current chunk |
| update(ExecutionContext) | Saves the state needed to continue at a checkpoint |
| close() | Flushes the remainder and releases resources |

For example, a writer that writes a file needs to open the file before receiving the first chunk, write data across many write() calls, and then close the file when the Step ends.

## 2. The Writer Lifecycle in a Step

Spring Batch manages the ItemStreams registered with the Step. At a conceptual level, a writer's lifecycle looks like this:

~~~text
Job starts the Step
       |
       v
writer.open(executionContext)
       |
       v
    Chunk 1
       |
       +--> writer.write(chunk)
       |
       +--> writer.update(executionContext)
       |
       +--> transaction commit
       |
       v
    Chunk 2
       |
       +--> writer.write(chunk)
       |
       +--> writer.update(executionContext)
       |
       +--> transaction commit
       |
       v
   ... subsequent chunks ...
       |
       v
writer.close()
       |
       v
Step ends
~~~

Some important points:

- open() is called when the Step opens the streams before processing data.
- write() can be called many times, usually once for each chunk written.
- update() saves the stream's state at a checkpoint to support restart.
- close() is called when the Step ends or goes through the cleanup path after an error.

A writer should not close its resources after each write(). The Step may need the writer for the next chunk. Closing early causes the next write to hit errors such as a closed stream or an invalid file handle.

Also, do not assume close() always runs in every situation. If the process is forcibly killed, the server loses power, or the JVM crashes, the application's cleanup code may not be executed. You need to rely on the operating system's storage and recovery mechanisms, and also design the Job so it can check and handle incomplete output.

## 3. How Does Flush Differ from a Transaction Commit?

Flush and commit are related but not synonymous.

**Flush** is an operation of the data-writing layer. It pushes data out of the application's buffer to the stream or the underlying operating system.

**Commit** is an operation of the transaction manager, confirming that the changes belonging to the transaction have completed. For a database, a commit makes the transaction's changes into confirmed data according to the database's mechanism.

You can picture it like this:

~~~text
Application writes data
       |
       v
Buffer in the writer
       |
       | flush()
       v
Stream / operating system
       |
       | commit transaction (if the resource participates in the transaction)
       v
Confirmed state
~~~

A flush() call does not commit a database transaction on its own. Conversely, a database commit does not mean every file or HTTP request called in the same chunk has been committed through the same mechanism.

Even when a file flush succeeds, the data may still be in the operating system's cache. If a requirement needs file data synced to the storage device, you need a mechanism such as forceSync or FileChannel.force depending on the writer type and the desired level of guarantee.

Therefore, when saying “the writer has flushed”, you can only conclude that the buffer at the writer layer has been pushed to a lower layer according to the stream's contract. Do not immediately infer that the whole Job has committed or that the data is physically durable.

## 4. When Is Flush Needed?

Flush is usually needed when:

- The writer keeps data in a buffer to reduce the number of system writes.
- The application needs output that another process can read early.
- The writer needs to push the remaining data before closing the resource.
- You need to synchronize data at a boundary the application controls.

However, flushing too often can reduce performance because it increases the number of writes to the stream or the operating system.

For a writer managed by Spring Batch, let the writer perform flush according to its own mechanism and configuration. Do not try to access the internal buffer or call flush arbitrarily after each item if the writer does not provide an appropriate API.

For a built-in file writer, Spring Batch has a buffering mechanism and coordinates with the transaction. Configure the writer instead of grabbing the internal stream to flush.

## 5. FlatFileItemWriter Manages Flush and Close

**FlatFileItemWriter** is a built-in writer for writing data as lines in a file. It manages opening the file, writing chunks, saving state, and closing resources according to the ItemStream lifecycle.

Configuration example with Spring Batch 5:

~~~java
@Bean
public FlatFileItemWriter<Customer> customerFileWriter(
        Resource outputResource,
        LineAggregator<Customer> customerLineAggregator) {

    return new FlatFileItemWriterBuilder<Customer>()
            .name("customerFileWriter")
            .resource(outputResource)
            .lineAggregator(customerLineAggregator)
            .encoding("UTF-8")
            .saveState(true)
            .transactional(true)
            .forceSync(false)
            .build();
}
~~~

Notable configurations:

| Configuration | Meaning |
|---|---|
| name(...) | A stable name to identify the writer's state in the ExecutionContext |
| resource(...) | The output file resource |
| lineAggregator(...) | Converts an item into a line |
| encoding(...) | The file's encoding |
| saveState(true) | Allows saving the writer's state for restart |
| transactional(true) | Uses the writer's transactional buffer mechanism to coordinate with rollback |
| forceSync(false) | Does not require syncing the file descriptor to the device after each write |

The values above are configuration examples. Choose forceSync, transactional, and saveState according to the output requirements, the Spring Batch version, and the actual resource type.

### A writer that writes line by line

LineAggregator converts an item into a string. For example, you can use a dedicated aggregator to format a Customer as a CSV line:

~~~java
public class CustomerLineAggregator
        implements LineAggregator<Customer> {

    @Override
    public String aggregate(Customer customer) {
        return customer.id() + "," +
                customer.name() + "," +
                customer.email();
    }
}
~~~

This example only illustrates mapping fields into a line. If the data has commas, double quotes, or newline characters in a field, you need to use a CSV serializer with correct escaping rules. Simple string concatenation is not enough to produce safe CSV for every input.

After receiving a chunk, FlatFileItemWriter writes the lines in order. The writer retains ownership of the file resource and manages the buffer, flush, and close itself according to the Step lifecycle.

## 6. FlatFileItemWriter's Transactional Buffer

One important aspect of FlatFileItemWriter is that its write mechanism can coordinate with the chunk's transaction. When transactional is enabled, the writer uses a transactional buffer so that the chunk's content is written to the file according to the commit/rollback state.

At a conceptual level:

~~~text
Chunk begins
     |
     v
writer.write(chunk)
     |
     v
Output lines sit in the transactional buffer
     |
     +---- Chunk commit
     |          |
     |          v
     |    Push the chunk's content to the file
     |
     +---- Chunk rollback
                |
                v
          Discard uncommitted content
~~~

This helps avoid the case where the writer writes part of a chunk to the file and then the database transaction rolls back but the file still keeps those lines, within the scope of the writer's transactional buffer mechanism.

You need to distinguish this mechanism from a distributed transaction between a file and a database. It helps the writer coordinate file writing with the Step's transaction, but it does not turn the filesystem into a database transaction with every ACID property. If multiple independent resources participate in the same chunk, you still need to consider errors between the resources and reconciliation capability.

If you configure transactional(false), the writer does not use the same transactional buffer mechanism. In that case, content may be written to the file before the Step's transaction commits. If the chunk rolls back, the lines written directly may still exist. Only use this mode when the application already has a way to handle incomplete output or does not need file rollback by transaction.

## 7. forceSync and File Data Durability

The **forceSync** configuration controls syncing file data after writing. When enabled, the writer requests syncing the content through the file descriptor down to the storage device according to the platform's mechanism.

~~~java
new FlatFileItemWriterBuilder<Customer>()
        .name("customerFileWriter")
        .resource(outputResource)
        .lineAggregator(customerLineAggregator)
        .forceSync(true)
        .build();
~~~

forceSync can increase data durability when the operating system or server experiences a failure, but it usually reduces performance because a physical sync request is more expensive.

Distinguish three layers:

1. **Writer buffer**: data still in the application's buffer.
2. **OS buffer/cache**: data that has been handed to the operating system.
3. **Storage device**: data that has been synced via the hardware and operating system mechanism.

Flush usually pushes data from layer 1 to layer 2. forceSync requests a deeper sync from layer 2. The actual level of guarantee still depends on the filesystem, the device, the operating system configuration, and the platform it runs on.

Do not enable forceSync just to be "safer" without measuring. Enable it when the output durability requirement is worth the performance cost.

## 8. What Are the Responsibilities of Closing a Resource?

When the Step ends, the writer needs to release every resource it owns:

- Flush the remaining data in the buffer if the writer contract requires it.
- Close the BufferedWriter, OutputStream, or file handle.
- Release cursors or resources opened directly.
- Close the client or session only if the writer owns the lifecycle of that object.
- Clear internal references to avoid accidental use after closing.

Close should be safe when called during cleanup after an error. If the writer opens part of the resources and then hits an exception, it needs to release the portion that was opened.

An important rule is to **only close resources the writer owns**. If the writer receives a DataSource, a singleton HTTP client, or a connection pool managed by Spring, it must not close that whole shared object in close(). With JDBC, prefer JdbcTemplate or Spring's connection management mechanism instead of holding a connection for the writer's entire lifecycle.

## 9. A Hand-Written Writer Needs to Implement ItemStream

If the writer opens a file or another resource itself, implement ItemStreamWriter so Spring Batch manages the lifecycle.

The example below illustrates a writer that writes text using BufferedWriter:

~~~java
public class BufferedTextItemWriter
        implements ItemStreamWriter<String> {

    private final Path outputPath;
    private BufferedWriter writer;

    public BufferedTextItemWriter(Path outputPath) {
        this.outputPath = outputPath;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        try {
            writer = Files.newBufferedWriter(
                    outputPath,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.TRUNCATE_EXISTING,
                    StandardOpenOption.WRITE
            );
        } catch (IOException ex) {
            throw new ItemStreamException(
                    "Cannot open output file", ex);
        }
    }

    @Override
    public void write(Chunk<? extends String> chunk)
            throws Exception {

        if (writer == null) {
            throw new IllegalStateException(
                    "Writer has not been opened");
        }

        for (String line : chunk) {
            writer.write(line);
            writer.newLine();
        }
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // This example does not save its own checkpoint.
    }

    @Override
    public void close() {
        if (writer == null) {
            return;
        }

        try {
            writer.close();
        } catch (IOException ex) {
            throw new ItemStreamException(
                    "Cannot close output file", ex);
        } finally {
            writer = null;
        }
    }
}
~~~

This example illustrates how to open the resource in open(), use it in write(), and release it in close(). close() checks for null so it can be called when the resource has not been opened or has already been released.

**This is a resource-management example, not a complete file writer with rollback and restart.** The writer above writes directly to the file, does not save the position, and has no transactional buffer. TRUNCATE_EXISTING will also erase old content when opening the file. If the Step rolls back or the Job restarts, the file may contain data inconsistent with the checkpoint. For file output that needs transactions and restart, prefer FlatFileItemWriter or design a separate temporary-write, checkpoint, and publish mechanism.

## 10. Do Not Close the Writer in write()

A common mistake is to open and close the file inside each write:

~~~java
@Override
public void write(Chunk<? extends String> chunk) throws Exception {
    try (BufferedWriter writer = Files.newBufferedWriter(outputPath)) {
        for (String line : chunk) {
            writer.write(line);
            writer.newLine();
        }
    }
}
~~~

This code closes the writer after each chunk. It can cause several problems:

- If APPEND is not configured, the file may be overwritten on every chunk.
- Continuously opening/closing the file increases I/O cost.
- You cannot use a stable stream to manage state and checkpoints.
- The Step's restart and transactional options are not used properly.

A writer that manages resources via ItemStream should open the resource once in open(), use it across many write() calls, and close it in close().

Also, do not call close() from a processor or listener after a chunk if the writer is still needed for the next chunk.

## 11. Wrapper and Delegate Writers Must Forward the Lifecycle

In some configurations, the actual writer is wrapped by a wrapper, decorator, or composite writer. If the delegate needs open/update/close but the wrapper does not forward the ItemStream calls, the delegate may not be initialized or released properly.

Example of a wrapper that implements ItemStreamWriter and delegates:

~~~java
public class LoggingItemWriter<T>
        implements ItemStreamWriter<T> {

    private final ItemStreamWriter<T> delegate;

    public LoggingItemWriter(ItemStreamWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void open(ExecutionContext context) {
        delegate.open(context);
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
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

If the wrapper does not implement ItemStream, the Step may only recognize the wrapper as an ordinary ItemWriter. In that case, register the delegate as a separate stream using the Step builder's stream(...) mechanism:

~~~java
new StepBuilder("exportCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .writer(loggingWriter)
        .stream(delegateWriter)
        .build();
~~~

When using a built-in composite or decorator, check whether it manages the delegate's stream automatically. Avoid registering or closing the same stream multiple times in ways that cause lifecycle conflicts.

## 12. append, shouldDeleteIfExists, and File Restart

When writing a file, you need to determine what happens if the output already exists.

FlatFileItemWriterBuilder provides commonly used options:

- **append(true)**: continues writing to the existing file.
- **shouldDeleteIfExists(true)**: deletes the existing file when starting a new write according to the writer's conditions.
- **saveState(true)**: saves the writer's state to support restart.

Configuration example for writing a new output:

~~~java
new FlatFileItemWriterBuilder<Customer>()
        .name("customerFileWriter")
        .resource(outputResource)
        .lineAggregator(customerLineAggregator)
        .append(false)
        .shouldDeleteIfExists(true)
        .saveState(true)
        .transactional(true)
        .build();
~~~

On a restart, the writer needs to recognize the old state in the ExecutionContext to continue with the right file and the saved position. Do not treat a restart as a new run and then delete output already created from previously committed chunks.

If you enable append or change the output path between the first run and the restart, it can lead to data being appended repeatedly, writing to the wrong file, or failing to restore the expected position. Keep the resource stable for the same JobInstance and check the restart state before deciding to delete or append to the file.

A safe approach for reports is to write to a temporary file by execution ID, and only publish or rename it to the main file after the Job completes successfully. This way, users do not accidentally read a file that is half-created. Publishing needs a policy for handling a failed rename operation or a stopped Job.

## 13. Close and Data Write Errors

Not every writer error occurs in write(). Some errors only appear on flush or close, for example:

- Out of disk space.
- Write permission revoked.
- Storage device failure.
- The file handle closed from outside.
- The stream or connection lost.
- A sync error with forceSync.

This means earlier chunks may have been processed while the Step still fails at the writer-closing stage. When investigating, look at both errors in write() and errors in close(), and the operating system logs.

Do not catch and ignore IOException in close(). If you cannot complete the write or release the resource, the Step needs to be notified of that error so the application does not mark the Job successful when the output is incomplete.

When you need to both report a flush error and try to close the resource, keep the original error and handle the close error as a suppressed exception or log it appropriately. Avoid letting a cleanup exception mask the original write cause.

## 14. Database Writers and Releasing Connections

Not every writer needs to manage files or streams itself. With JdbcBatchItemWriter, Spring Batch uses the JDBC infrastructure and the transaction manager to perform writes.

Example:

~~~java
@Bean
public JdbcBatchItemWriter<Customer> customerDatabaseWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO customer (id, name, email)
                VALUES (:id, :name, :email)
                """)
            .beanMapped()
            .build();
}
~~~

In this case:

- The writer does not need to open a long-lived connection in open().
- The connection is obtained and returned according to the Spring JDBC mechanism and the current transaction.
- You must not close the DataSource or connection pool in the writer's close().
- The transaction manager is responsible for committing/rolling back connections participating in the transaction.

If you write your own JDBC-based writer, use JdbcTemplate, NamedParameterJdbcTemplate, or DataSourceUtils to participate in the Spring-managed transaction. Only close a connection yourself when your code obtained and owns the connection correctly; do not close a connection that the transaction manager is holding.

## 15. Testing Flush and Close

The writer lifecycle needs to be tested, especially for hand-written writers or writers wrapping a delegate.

Scenarios to check:

| Scenario | What to verify |
|---|---|
| Opening the Step | open() is called and the resource is ready |
| Writing multiple chunks | write() is called multiple times on the same writer |
| Normal completion | close() releases the resource and the remaining buffer is handled |
| The writer hits an error | The Step still goes through the cleanup process |
| open() fails midway | A partially opened resource is released |
| close() is called when not opened | No unexpected error occurs |
| Wrapper with a delegate | open/update/close are forwarded correctly |
| Restart | The writer restores state and continues with the correct output |
| Rollback | Uncommitted data does not appear in the output if the writer supports transactional behavior |

### Testing a hand-written writer with Mockito

You can use a fake writer to verify that the lifecycle is called:

~~~java
@Test
void delegatesItemStreamLifecycle() throws Exception {
    @SuppressWarnings("unchecked")
    ItemStreamWriter<String> delegate =
            mock(ItemStreamWriter.class);

    LoggingItemWriter<String> writer =
            new LoggingItemWriter<>(delegate);

    ExecutionContext context = new ExecutionContext();

    writer.open(context);
    writer.write(new Chunk<>(List.of("A", "B")));
    writer.update(context);
    writer.close();

    verify(delegate).open(context);
    verify(delegate).write(any());
    verify(delegate).update(context);
    verify(delegate).close();
}
~~~

This test verifies that the wrapper forwards the calls. To check an actual file, use a temporary directory and read the content after the writer closes. For transactional behavior and restart, you should run a Step integration test with a suitable JobRepository and transaction manager.

### Testing errors in close()

If you write the writer yourself, create a fake resource that can throw IOException on flush or close. Verify that the Step receives the error and does not falsely report COMPLETED.

With a real file writer, errors such as disk full are hard to simulate reliably in a unit test. You can test the exception-handling logic with an abstraction or a mock, and then add an environment test for the filesystem if operational requirements call for it.

## 16. Common Resource Management Mistakes

### Closing the writer after each chunk

The writer is closed too early and cannot continue receiving chunks. Let the Step manage the lifecycle through ItemStream.

### Not implementing ItemStream for a stateful writer

The framework does not know when to open, save state, or close the resource. Implement ItemStreamWriter or register the delegate stream.

### A wrapper that does not forward open/update/close

The delegate may not be initialized, may not save checkpoints, or may leak resources. Forward the lifecycle or register the delegate with the Step.

### Confusing flush with commit

Flush pushes the buffer to a lower write layer; commit confirms a transaction. The two operations have different scopes.

### Confusing flush with physical sync

Flushed data may still be in the operating system's cache. When a higher level of guarantee is needed, consider forceSync and measure performance.

### Swallowing errors in close()

A Job may be reported successful while the output is incomplete. Let write/close errors propagate to the Step or be handled according to a clear policy.

### Closing shared resources

Closing a DataSource, connection pool, or singleton HTTP client in close() can break other components. Only close resources the writer owns.

### Writing files directly without a rollback mechanism

If a chunk fails, the file may keep uncommitted data. Use FlatFileItemWriter with a transactional buffer or design temporary output and publish after the Job completes.

## 17. Process for Designing a Writer That Manages Resources Safely

When creating a writer with external resources, determine clearly who owns the resource and when the data is considered complete.

1. Choose a built-in writer if it already supports the right kind of output.
2. If writing your own, implement ItemStreamWriter for resources with a lifecycle.
3. Open the resource in open() and restore state from the ExecutionContext if restart is needed.
4. Use write() to write the chunk; do not close the resource here.
5. Update the checkpoint in update() if the writer has state.
6. Let close() flush and release the resource the writer owns.
7. Do not close resources managed by Spring or a shared component.
8. Distinguish flush, transaction commit, and forceSync.
9. Define the behavior when a chunk rolls back, the Job restarts, or close() hits an error.
10. Test wrappers, delegates, and the cleanup paths after errors.

When reading an ItemWriter configuration, look at whether the writer implements ItemStream, where the resource is opened, who is responsible for closing it, when the buffer is flushed, and whether the transaction can roll back the output. If you can answer these questions, you will avoid most data loss, duplicate writes, leaked file handles, and Jobs that report success when the output is incomplete.

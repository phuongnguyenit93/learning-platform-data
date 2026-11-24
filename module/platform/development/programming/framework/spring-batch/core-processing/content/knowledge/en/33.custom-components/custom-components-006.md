# Opening and Closing Resources

In Spring Batch, a custom reader, writer, or tasklet often has to open and release resources such as files, JDBC cursors, sockets, streams, or connections to external services. Opening resources at the right time lets the component consume or write data within a `Step`; closing resources at the right time prevents file descriptor leaks, connection pool exhaustion, and unflushed data.

For components participating in chunk processing, Spring Batch provides the `ItemStream` lifecycle contract with three methods: `open`, `update`, and `close`. A component uses `open` to open resources and restore state, `update` to write checkpoints to `ExecutionContext`, and `close` to release resources. Understanding this contract is fundamental when writing stateful or restartable custom readers/writers.

## 1. Why Is the Resource Lifecycle Important?

A resource often outlives a single `read` or `write` call. For example, a reader may open a file at the start of a `Step`, read thousands of lines across many chunks, and only then close the file. A writer may keep an output stream open to avoid repeatedly opening and closing the file for each item.

Opening a resource on every `read`/`write` call can create excessive connections or file handles. Forgetting to close resources when a `Step` finishes or fails can leave resources held until the process exits.

Common resource types:

- File input/output and `BufferedReader`/`BufferedWriter`.
- JDBC `Connection`, `Statement`, `ResultSet`, or cursors.
- HTTP response bodies, streams, or sockets.
- Readers/writers for object storage or remote filesystems.
- Native resources or handles managed by third-party libraries.

The resource lifecycle must handle both happy-path execution and failure scenarios such as exceptions mid-open, read/write errors, rollbacks, stops, and restarts.

## 2. The Three Methods of ItemStream

`ItemStream` is Spring Batch's contract for components that require a lifecycle and may persist state:

~~~java
public interface ItemStream {

    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
~~~

Each method has a distinct responsibility:

| Method | Timing and purpose |
|---|---|
| `open` | When the `Step` begins using the stream; opens resources and restores saved state |
| `update` | At checkpoints; writes current state to `ExecutionContext` |
| `close` | When the stream ends; flushes and releases resources |

`ItemStream` does not replace `ItemReader` or `ItemWriter`; it augments the component with a lifecycle. Consequently, a stateful custom reader typically implements `ItemStreamReader`, and a stateful custom writer typically implements `ItemStreamWriter`.

~~~java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}

public interface ItemStreamWriter<T>
        extends ItemWriter<T>, ItemStream {
}
~~~

If a component does not need to keep resources open across multiple calls and has no state to restore, it can use `try-with-resources` inside a short processing method. Do not implement `ItemStream` on every class simply because it touches a file or connection.

## 3. Resource Lifecycle in a Step

In a chunk-oriented `Step`, Spring Batch manages the lifecycle of streams registered with the `Step`. A conceptual flow:

~~~text
Step starts
    |
    v
ItemStream.open(ExecutionContext)
    |
    v
Read and process chunk
    |
    +--> ItemStream.update(ExecutionContext)
    |          |
    |          v
    |      Commit chunk/checkpoint
    |
    +--> next chunk
    |
    v
Step ends or fails
    |
    v
ItemStream.close()
~~~

A reader/writer can keep a file or cursor open across multiple chunks. `update` is called so the component records information needed for the next restart. `close` is called when the `Step`'s lifecycle concludes.

Exact ordering and transaction synchronization depend on the `Step` implementation and Spring Batch version. The key distinction is that `update` belongs to the `Step`'s checkpoint lifecycle, whereas `close` belongs to the resource-release lifecycle. Do not use `close` to save the final checkpoint instead of `update`.

## 4. When to Use ItemStream vs. try-with-resources?

Choose the mechanism according to the resource's lifetime:

| Scenario | Appropriate management approach |
|---|---|
| Reader opens a file and reads across many chunks | `ItemStreamReader` |
| Writer keeps an output stream open across the `Step` | `ItemStreamWriter` |
| JDBC cursor that must stay open throughout the `Step` | Reader implementing `ItemStream` |
| `Tasklet` opens a file, reads/writes, and closes within one `execute` call | `try-with-resources` |
| Service opens an HTTP response and processes it within a single method | `try-with-resources` |
| Component needs to save read position for restarts | `ItemStream` and `ExecutionContext` |
| Resource used for a single short statement | Resource-managing API like `JdbcTemplate` |

Example tasklet processing a file in a single invocation:

~~~java
public class ImportManifestTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        Path path = Path.of("/data/input/manifest.txt");

        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

            String firstLine = reader.readLine();
            // Process manifest contents in this call.
        }

        return RepeatStatus.FINISHED;
    }
}
~~~

The resource closes even if processing throws an exception. If a tasklet needs to retain a resource across multiple `execute` calls or checkpoint between calls, design an explicit `ItemStream` lifecycle rather than holding an open handle without recovery.

## 5. Custom Reader Implementing ItemStreamReader

A custom reader can open a file in `open`, return one line per `read`, save the line count in `update`, and close the file in `close`.

Illustrative example:

~~~java
public class LineItemReader
        implements ItemStreamReader<String> {

    private static final String LINE_COUNT_KEY =
            "lineItemReader.lineCount";

    private final Path inputPath;

    private BufferedReader reader;
    private long lineCount;

    public LineItemReader(Path inputPath) {
        this.inputPath = inputPath;
    }

    @Override
    public void open(ExecutionContext context) {
        try {
            reader = Files.newBufferedReader(
                    inputPath, StandardCharsets.UTF_8);

            lineCount = context.containsKey(LINE_COUNT_KEY)
                    ? context.getLong(LINE_COUNT_KEY)
                    : 0L;

            for (long skipped = 0; skipped < lineCount; skipped++) {
                if (reader.readLine() == null) {
                    throw new ItemStreamException(
                            "Checkpoint exceeds input file length");
                }
            }
        } catch (Exception exception) {
            try {
                closeQuietly();
            } catch (Exception closeException) {
                exception.addSuppressed(closeException);
            }
            throw new ItemStreamException(
                    "Cannot open input file: " + inputPath,
                    exception);
        }
    }

    @Override
    public String read() throws Exception {
        if (reader == null) {
            throw new IllegalStateException(
                    "Reader has not been opened");
        }

        String line = reader.readLine();
        if (line != null) {
            lineCount++;
        }
        return line;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LINE_COUNT_KEY, lineCount);
    }

    @Override
    public void close() {
        closeQuietly();
    }

    private void closeQuietly() {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException exception) {
                throw new ItemStreamException(
                        "Cannot close input file: " + inputPath,
                        exception);
            } finally {
                reader = null;
            }
        }
    }
}
~~~

This is a simple example illustrating the lifecycle. For very large files, skipping from the start up to the checkpoint can be slow. Use byte offsets, indexes, record keys, or seekable source formats for faster recovery.

`ExecutionContext` key names must remain stable across restarts. If a reader can appear multiple times in the same `Step` or multiple instances of the same type exist, add a unique identifier to avoid overwriting keys.

## 6. open Must Restore State and Handle Partial Opening

`open` receives the `ExecutionContext` containing state saved at the prior checkpoint. On a first run, the context typically lacks the component's keys. On a restart, it may hold the read position, last processed ID, or metadata needed to reopen the resource at the right spot.

Inside `open`, follow this sequence:

1. Validate configuration and resource paths.
2. Read state to restore from `ExecutionContext`.
3. Open resources.
4. Reposition the resource or restore the cursor.
5. Verify the resource matches the checkpoint.
6. Mark the component ready only after every step succeeds.

If the component opens multiple resources and opening the second fails, close the first before throwing an exception. Never leave partial resources open because `open` did not finish.

Example:

~~~java
@Override
public void open(ExecutionContext context) {
    try {
        input = Files.newInputStream(inputPath);
        index = Files.newBufferedReader(indexPath);
        restorePosition(context);
    } catch (Exception exception) {
        closeResourcesAfterOpenFailure();
        throw new ItemStreamException(
                "Cannot initialize reader resources", exception);
    }
}
~~~

The cleanup helper in this example must be safe when one or more fields are still `null`. Closing resources should be repeatable without triggering secondary errors.

Do not store an `InputStream`, `Connection`, or `ResultSet` directly in `ExecutionContext`. The context is for serializable state like line counts, byte offsets, last keys, or filenames; resource handles must be reopened in `open`.

## 7. update Saves Checkpoints, Not Resource Handles

`update` receives `ExecutionContext` so the component can save state needed for restarts.

Examples of state that can be saved:

- Number of lines read.
- Processed byte offset.
- Last read or written ID.
- Current page and sort key.
- Input filename, version, or checksum.
- Written record count and output position.

Do not store the following objects in `ExecutionContext`:

- `BufferedReader` or `BufferedWriter`.
- `FileInputStream` or `FileOutputStream`.
- JDBC `Connection`, `Statement`, or `ResultSet`.
- Sockets, HTTP responses, or threads.
- Non-serializable objects or objects bound to the current process.

`ExecutionContext` is durable metadata, not a container for open handles. Once a process stops, old handles are invalid; restarts must open fresh resources and recover from saved state.

## 8. update and Chunk Commit Boundaries

In chunk-oriented processing, `update` is invoked at `Step` checkpoints to save reader/writer state. This state is persisted alongside `StepExecution` metadata per `JobRepository` transaction semantics.

Example:

~~~text
Committed chunk 1:
  checkpoint = item 100

Processing chunk 2:
  read items 101..200
  write items 101..200
  update checkpoint = item 200
  commit

If chunk 2 rolls back:
  checkpoint metadata must still reflect the previous commit point
  restart will restore from the persisted checkpoint
~~~

Do not update durable checkpoints for uncommitted items as though they were complete. If a checkpoint moves ahead of destination data, restarts can skip unwritten items. If it lags behind, committed items may be reprocessed; writers need idempotency or deduplication.

For custom writers targeting the filesystem, files and `JobRepository` do not inherently share a transaction. Design flush ordering, offset persistence, and file recovery to minimize divergence between checkpoints and files.

## 9. close Releases Resources

`close` is invoked when the `Step` finishes its lifecycle. A component should:

- Flush buffered data if required by contract.
- Close owned streams, readers, writers, cursors, and statements.
- Release locks or handles.
- Clear references to closed resources.
- Reset the component to a closed state.
- Report cleanup errors via `ItemStream`'s exception mechanism.

`close` must be idempotent: calling it a second time must not raise errors because a resource is already closed or a field is `null`. This is essential because cleanup may run after `open` only partially succeeded.

Example:

~~~java
@Override
public void close() {
    if (reader == null) {
        return;
    }

    try {
        reader.close();
    } catch (IOException exception) {
        throw new ItemStreamException(
                "Failed to close reader", exception);
    } finally {
        reader = null;
    }
}
~~~

If a component owns multiple resources, attempt to close all of them even if one close fails. Capture the first exception, continue closing remaining resources, and throw the primary exception with subsequent failures attached as suppressed exceptions.

Do not swallow all close errors. A flush or close failure can mean data was not completely written. Log it and allow the `Step`/`Job` to reflect the cleanup failure appropriately.

## 10. Closing Resources in Reverse Order

When opening dependent resources sequentially, close them in the reverse order of opening.

Example:
1. Open a `DataSource` connection.
2. Create a `PreparedStatement`.
3. Execute the query and obtain a `ResultSet`.

When closing:
1. Close the `ResultSet`.
2. Close the `Statement`.
3. Return the `Connection` to the pool or release per ownership rules.

With JDBC, if using `JdbcTemplate` or Spring's managed connection APIs, do not manually close connections owned by the transaction manager. Use `JdbcTemplate` or `DataSourceUtils` properly so connections are released in step with transaction synchronization.

If a custom component opens a standalone connection to hold a cursor, the component is responsible for closing its own statement, result set, and connection. Do not confuse a standalone connection with a transaction-managed connection.

## 11. Custom Writer Implementing ItemStreamWriter

A writer can keep an output resource open across the `Step` and save written positions for restarts.

Example writing UTF-8 lines with byte-offset tracking:

~~~java
public class CheckpointLineWriter
        implements ItemStreamWriter<String> {

    private static final String OFFSET_KEY =
            "checkpointLineWriter.byteOffset";

    private final Path outputPath;

    private RandomAccessFile file;

    public CheckpointLineWriter(Path outputPath) {
        this.outputPath = outputPath;
    }

    @Override
    public void open(ExecutionContext context) {
        try {
            file = new RandomAccessFile(
                    outputPath.toFile(), "rw");

            long offset = context.containsKey(OFFSET_KEY)
                    ? context.getLong(OFFSET_KEY)
                    : 0L;

            if (offset > file.length()) {
                throw new ItemStreamException(
                        "Output file is shorter than saved checkpoint");
            }

            // Discard bytes not checkpointed in the previous run.
            file.setLength(offset);
            file.seek(offset);
        } catch (Exception exception) {
            try {
                closeQuietly();
            } catch (Exception closeException) {
                exception.addSuppressed(closeException);
            }
            throw new ItemStreamException(
                    "Cannot open output file: " + outputPath,
                    exception);
        }
    }

    @Override
    public void write(Chunk<? extends String> chunk)
            throws Exception {
        for (String item : chunk) {
            file.write(item.getBytes(StandardCharsets.UTF_8));
            file.write('\n');
        }
    }

    @Override
    public void update(ExecutionContext context) {
        try {
            file.getFD().sync();
            context.putLong(OFFSET_KEY, file.getFilePointer());
        } catch (IOException exception) {
            throw new ItemStreamException(
                    "Cannot save output checkpoint", exception);
        }
    }

    @Override
    public void close() {
        closeQuietly();
    }

    private void closeQuietly() {
        if (file != null) {
            try {
                file.close();
            } catch (IOException exception) {
                throw new ItemStreamException(
                        "Cannot close output file", exception);
            } finally {
                file = null;
            }
        }
    }
}
~~~

This example uses Spring Batch 5 with `write` accepting `Chunk`. In older versions, `ItemWriter` may accept `List` instead of `Chunk`; adjust the method signature to match your project's API version.

The checkpointing idea is saving the byte offset after chunk content is written and synced to disk. On restart, the writer truncates bytes past the saved offset and seeks to that exact position. This handles cases where the file has partially written data whose database checkpoint did not commit.

This remains a minimal example. Real applications must handle missing directories, headers/footers, newline encodings, size limits, file locking, I/O exceptions, and output format compatibility.

## 12. Database Transactions Do Not Automatically Roll Back the Filesystem

A file writer and a database writer may run in the same chunk, but the filesystem does not automatically join JDBC transactions.

Possible failure modes:

- The file wrote the chunk, then the database transaction rolled back.
- The database committed, then the process stopped before finishing the file.
- The file flushed, yet checkpoint metadata failed to commit.
- Metadata committed, yet file data was not synced to durable storage.

Therefore, custom writers need a suitable recovery strategy:
- Write files to a stable staging path.
- Persist byte offsets or record keys in `ExecutionContext`.
- Flush/sync data before saving checkpoints when durability is required.
- On restart, truncate or reconcile uncheckpointed output.
- Publish the file only after the `Job` finishes and results are verified.
- Use manifests, checksums, and record counts for reconciliation.

Do not claim a file writer is atomic with the database unless the application uses a true distributed transaction mechanism supporting both resources.

## 13. Registering a Custom Stream with a Step

Spring Batch needs to know which components have an `ItemStream` lifecycle so it can invoke `open`, `update`, and `close`.

If a custom reader is configured directly via `reader(...)` and implements `ItemStreamReader`, the `Step` discovers its lifecycle through its stream-aware type.

Example:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        LineItemReader lineItemReader,
        ItemWriter<String> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<String, String>chunk(100, transactionManager)
            .reader(lineItemReader)
            .writer(writer)
            .build();
}
~~~

If a stream is not discovered via the primary reader/writer, register it explicitly with `stream(...)`:

~~~java
return new StepBuilder("exportStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .stream(auditFileWriter)
        .build();
~~~

This frequently occurs with delegates or auxiliary resources. If a stream is unregistered, the framework may never invoke `open`/`update`/`close` on it. The first `Job` run might still succeed, while restarts fail to restore state or resources leak.

Do not register the same stream twice through multiple paths unintentionally. Avoid having the same instance receive lifecycle callbacks multiple times unexpectedly.

## 14. Delegate Readers/Writers and ItemStream

A custom reader/writer may wrap another component. For instance, `CompositeItemWriter` invokes multiple child writers, or a filtering reader wraps a delegate reader.

If the delegate implements `ItemStream`, the wrapper must forward the lifecycle:

~~~java
public class AuditingReader<T>
        implements ItemStreamReader<T> {

    private final ItemStreamReader<T> delegate;

    public AuditingReader(ItemStreamReader<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public T read() throws Exception {
        T item = delegate.read();
        if (item != null) {
            // Record appropriate audit metadata.
        }
        return item;
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

The wrapper must ensure the delegate receives `ExecutionContext` and lifecycle callbacks properly. If the wrapper implements only `ItemReader` without forwarding `ItemStream`, the `Step` may remain unaware that the delegate needs opening, checkpointing, or closing.

With multiple delegates, each stream needs distinct state keys. Avoid sharing generic keys like `currentPosition` across all readers; prefix keys stably by component name.

## 15. Custom Tasklets and Resource Lifecycles

A `Tasklet` usually fits an operation that does not need item-by-item reading/writing. If a resource is used within a single `execute` call, use `try-with-resources` to close it immediately within the method scope.

~~~java
public class ArchiveTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        Path source = Path.of("/data/source.txt");
        Path archive = Path.of("/data/archive.txt");

        try (InputStream in = Files.newInputStream(source);
             OutputStream out = Files.newOutputStream(archive)) {
            in.transferTo(out);
        }

        return RepeatStatus.FINISHED;
    }
}
~~~

If a tasklet needs a resource to span multiple `execute` calls or requires checkpoints, implement `ItemStream` alongside `Tasklet` and ensure the stream is registered with the `Step`. Then `open`/`close` manage the resource while `execute` performs each unit of work.

Do not hold file handles or connections in static fields or singleton tasklets without an explicit lifecycle. Another `StepExecution` could reuse the same bean instance and access the wrong resource.

## 16. Listeners Do Not Replace the ItemStream Lifecycle

`StepExecutionListener` has `beforeStep` and `afterStep`; `JobExecutionListener` has `beforeJob` and `afterJob`. Listeners fit logging, metrics, precondition checks, or business notifications.

Do not use `afterStep` as the primary mechanism to close stateful readers/writers when the component already has `ItemStream`. `ItemStream` is designed for resource lifecycles and checkpointing; listeners serve broader orchestration goals.

Comparison:

| Need | Appropriate mechanism |
|---|---|
| Open file reader before reading | `ItemStream.open` |
| Save read position at checkpoint | `ItemStream.update` |
| Close file reader after `Step` | `ItemStream.close` |
| Log `Step` duration | `StepExecutionListener` |
| Send notification after `Job` | `JobExecutionListener` |
| Create output metadata used within `Step` | `Job` listener or `Step` listener depending on scope |
| Resource lives only inside one `Tasklet.execute` | `try-with-resources` |

If a listener opens a resource, you must ensure it closes even if the `Step` partially initializes and fails. Usually `ItemStream` is clearer and less error-prone for custom readers/writers.

## 17. JDBC Resources and Transaction-Aware Connections

For JDBC, the resource lifecycle is more complex than files because connections may be managed by a transaction manager.

When using `JdbcTemplate`, Spring manages connections, statements, and `ResultSet`s for the operation scope. This is usually the simplest choice for short queries.

If a custom component needs a `Connection` directly and must join the active transaction, use `DataSourceUtils`:

~~~java
Connection connection =
        DataSourceUtils.getConnection(dataSource);

try {
    // Perform JDBC work on the connection bound to the current transaction.
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

Do not call `connection.close()` arbitrarily when the connection is bound to the thread by the transaction manager. `DataSourceUtils.releaseConnection` respects transaction-bound connections and returns/closes them only when appropriate.

If a reader needs a cursor open across many chunks and must hold a connection longer, clearly design whether the connection belongs to the reader or the transaction. A dedicated connection with an `ItemStream` lifecycle may be necessary. Do not keep a single database transaction open for the entire `Job` solely to keep a cursor alive unless requirements demand it.

For `ResultSet` and `Statement` instances created by a custom component, always close them in `close` in reverse order of opening. When using `JdbcTemplate`, never close resources managed by `JdbcTemplate`.

## 18. Exception Safety When Opening and Closing Multiple Resources

A component may open multiple resources in sequence. If an intermediate step fails, already opened resources must be closed.

Example:
- Open input file.
- Open output file.
- Initialize parser.
- Connect to external service.

If parser initialization fails, already opened input/output files must be released. Write cleanup logic tolerant of partially initialized state.

When closing multiple resources, do not abort on the first error if other resources remain open. Pattern:

~~~java
@Override
public void close() {
    RuntimeException failure = null;

    try {
        closeInput();
    } catch (RuntimeException exception) {
        failure = exception;
    }

    try {
        closeOutput();
    } catch (RuntimeException exception) {
        if (failure == null) {
            failure = exception;
        } else {
            failure.addSuppressed(exception);
        }
    }

    if (failure != null) {
        throw failure;
    }
}
~~~

This pattern illustrates attempting to close both resources. In an `ItemStream` implementation, wrap the final failure in `ItemStreamException`. Preserve the original exception for logging and diagnosis.

Do not ignore exceptions in `close` just to let the `Job` report `COMPLETED`. If flushing or closing fails, the output may be incomplete.

## 19. Resource Cleanup When a Step Fails or Is Stopped

A `Step` can end as `COMPLETED`, `FAILED`, or `STOPPED`. Resources must be released in every case where the framework terminates the `Step` lifecycle.

Cases to consider:
- Reader opens successfully, then processor throws an exception.
- Writer throws `IOException` mid-chunk.
- Database deadlock triggers a transaction rollback.
- Operator issues a stop request.
- `Job` restarts after a failed execution.
- One resource opens successfully, then the next fails to open.

`close` must not assume every field was fully initialized. `open` may have failed partway through; `close` must check for `null` or resource state before closing.

`kill -9`, power loss, or a JVM crash cannot guarantee `close` callbacks run. Add timeouts, connection leak detection, file staging, and recovery mechanisms on process startup. Do not rely on `close` as the sole safeguard for durable data.

## 20. Do Not Keep Resources in ExecutionContext

`ExecutionContext` is saved in `JobRepository` and can be serialized. Store only the state needed to reopen resources, never the resources themselves.

Appropriate examples:

~~~java
context.putString("input.path", inputPath.toString());
context.putLong("input.lastLine", lastLine);
context.putLong("output.byteOffset", outputOffset);
context.putString("input.version", checksum);
~~~

Inappropriate examples:
- `context.put("reader", bufferedReader)`
- `context.put("connection", jdbcConnection)`
- `context.put("resultSet", resultSet)`
- `context.put("socket", socket)`

These objects are tied to the current process, thread, or session. They cannot be reused after a restart and typically are not serializable.

If input paths or versions affect results, store or verify them to avoid restarting against a resource with altered contents.

## 21. Thread Safety and Multiple StepExecutions

A step-scoped component normally gets its own target per `StepExecution`, yet that does not guarantee all accesses are single-threaded. A multi-threaded `Step` can invoke the same reader/writer instance from multiple threads within a single `StepExecution`, depending on configuration.

When a resource is not thread-safe:
- Do not share a `BufferedReader` or `ResultSet` across multiple threads if the implementation does not support it.
- Use partitioning with dedicated resources and checkpoints per worker where appropriate.
- Synchronize operations only with clear justification and measured impact.
- Do not use static resource handles.
- Do not let two writers write to the same file without explicit coordination.

If a component is used by multiple concurrent `StepExecution`s, guarantee isolated resources per execution or an appropriate pooling/thread-safe mechanism.

## 22. Testing the Lifecycle of Custom Components

Test both the three callbacks individually and integrated behavior within a `Step`.

Unit tests can verify:
- `open` opens resources and restores state.
- `read`/`write` use the open resource.
- `update` saves the right checkpoint.
- `close` releases resources.
- Calling `close` repeatedly causes no errors.
- Mid-open failures clean up already opened resources.
- Calls to `read`/`write` after `close` or before `open` are handled cleanly.

Integration tests with Spring Batch should confirm the framework invokes the lifecycle properly:

| Scenario | What to verify |
|---|---|
| `Step` succeeds | `open`, `update` at checkpoints, and `close` are invoked |
| `Step` fails | Resources are closed when framework terminates `Step` |
| Restart | `open` receives saved `ExecutionContext` and restores position |
| Chunk rollback | Checkpoints do not advance past committed data |
| Stream delegate | Delegate receives all `open`/`update`/`close` calls |
| Second resource fails on `open` | First resource is closed |
| `close` throws exception | Cleanup failure is observed |
| Stop `Step` | Resources are released per lifecycle |
| Multiple `StepExecution`s | No accidental sharing of resources or state |
| Process crash | Restart recovers from durable metadata and resources |

You can use mocks or fake resources to verify callback order. With JDBC, run integration tests against a real matching database/driver to confirm connections return to the pool and cursors close.

## 23. Observing Resources in Operations

Resource leaks may not surface in small single runs. Monitor:

- Active/idle/pending connections in pools.
- Connection hold durations.
- Open file descriptors or handles.
- Cursor open durations and active cursor counts.
- `open`/`close` counts for custom streams.
- I/O, flush, or cleanup error counts.
- `JobExecution`/`StepExecution` completions where resources remain held.

Logs should include `JobExecution` ID, `Step` name, component name, and resource type. Never log credentials, tokens, or sensitive data payloads.

For custom streams, consider debug logs on `open`/`close` and metrics tracking currently open resources. Metrics must avoid high-cardinality tags like individual item IDs or per-run full paths.

## 24. Common Mistakes

**Opening resources on every read/write.** Adds overhead and can exhaust connections or file handles.

**Forgetting ItemStream on stateful components.** Lacks an explicit checkpoint lifecycle and makes restarts unreliable.

**Not registering delegate streams.** Spring Batch will not call `open`/`update`/`close` on resources hidden inside wrappers.

**Closing resources only on the success path.** Exceptions leak connections or file handles.

**Non-idempotent close.** A second cleanup call can throw unnecessary exceptions.

**Storing Connections or streams in ExecutionContext.** Resource handles cannot survive process restarts.

**Saving checkpoints too early.** Metadata can run ahead of committed data and drop items on restart.

**Not flushing before saving byte offsets.** Checkpoints can point to bytes not durably written.

**Manually closing transaction-managed connections.** Can corrupt the active transaction or return connections to the pool prematurely.

**Using listeners instead of ItemStream.** Resource lifecycles and checkpoints become detached from the component that actually owns the resource.

**Assuming close runs after a JVM crash.** Abrupt process termination may skip callbacks.

**Sharing mutable resources across threads.** Causes race conditions, corrupted data, or driver errors.

## 25. Workflow for Implementing Resource Open and Close

When building a custom reader/writer, follow this sequence:

1. Determine whether the resource lives for a single method, a chunk, or the whole `Step`.
2. Use `try-with-resources` for resources needed only within a single method.
3. Use `ItemStreamReader`/`ItemStreamWriter` if the component holds resources or checkpoints across chunks.
4. Open resources in `open` and restore state from `ExecutionContext`.
5. Save small, stable state in `update` at checkpoints.
6. Close all component-owned resources in `close`.
7. Make `close` idempotent and clean up partial failures in `open`.
8. Register delegate streams with the `Step` so the framework invokes their lifecycle.
9. Use Spring transaction-aware APIs for JDBC connections; never manually close connections managed by the transaction manager.
10. Keep files/resources stable across restarts and design reconciliation for non-transactional data.
11. Test success, failure, rollback, stop, restart, and process interruption.
12. Monitor resource pools, handles, cursors, and cleanup errors in production.

`open`, `update`, and `close` form the lifecycle contract for stateful custom components in Spring Batch. `open` prepares resources and restores checkpoints; `update` saves progress at checkpoint boundaries; `close` releases resources. When resource-owning components are properly registered with the `Step`, cleanup is safe, and state is persisted consistently, jobs can process data across chunks, recover from errors, and avoid resource leaks.


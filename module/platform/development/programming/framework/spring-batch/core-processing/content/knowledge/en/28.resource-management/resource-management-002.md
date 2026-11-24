# ItemStream open and close

In Spring Batch, many batch components need to open and release resources during the lifecycle of a Step. A reader may need to open a file or cursor; a writer may need to open an output file; a custom component may need to restore its read position after a Job restarts. The **ItemStream** interface provides the lifecycle contract for Spring Batch to manage these operations.

ItemStream has three callbacks: **open**, **update**, and **close**. open receives the ExecutionContext to restore saved state; update writes the current checkpoint into the context at Step-managed milestones; close releases resources when the Step finishes. Among them, open and close are often mentioned together when discussing resource management, while update is the essential part that enables a reader or writer to support restart.

## 1. What is ItemStream?

ItemStream is a lifecycle interface in Spring Batch:

~~~java
public interface ItemStream {

    void open(ExecutionContext executionContext) throws ItemStreamException;

    void update(ExecutionContext executionContext) throws ItemStreamException;

    void close() throws ItemStreamException;
}
~~~

Reading or writing components can combine this contract with item-processing interfaces:

- **ItemStreamReader<T>** combines **ItemReader<T>** and **ItemStream**.
- **ItemStreamWriter<T>** combines **ItemWriter<T>** and **ItemStream**.
- A custom reader or writer can implement these interfaces directly to both process items and manage resources.

ItemReader only defines how to retrieve items; ItemWriter only defines how to write items. ItemStream adds the lifecycle for opening resources, restoring state, updating checkpoints, and closing resources. This allows the framework to manage the lifecycle uniformly instead of the application manually calling open/close in multiple places.

## 2. Three callbacks in the ItemStream lifecycle

| Callback | When is it called? | Responsibility |
|---|---|---|
| open(ExecutionContext) | When the Step starts and before processing items | Open the resource, read saved state, and restore position |
| update(ExecutionContext) | At Step state-update milestones, typically tied to chunk commit boundaries | Write checkpoints or state needed for recovery |
| close() | When the Step finishes, including when processing fails and the framework performs cleanup | Flush as needed and release resources |

High-level flow of a chunk-oriented Step:

~~~text
Step starts
    |
    v
ItemStream.open(executionContext)
    |
    v
Read / process / write chunk
    |
    v
ItemStream.update(executionContext)
    |
    v
Commit chunk and metadata per transaction
    |
    v
Repeat for next chunks
    |
    v
Step finishes or fails
    |
    v
ItemStream.close()
~~~

This is a high-level lifecycle description. The exact order among streams, listeners, and transactions depends on the Step type and how components are registered. The key point is that the application delegates stream management to Spring Batch by registering the necessary ItemStreams properly.

## 3. open() — opening resources and restoring state

Spring Batch calls open() when the Step prepares to execute. The method receives the ExecutionContext of the current StepExecution. This context may contain a checkpoint saved from a previous run.

An open implementation typically performs:

1. Validate required parameters or resources.
2. Open the appropriate file, stream, cursor, or resource.
3. Read the checkpoint from ExecutionContext if present.
4. Restore the reader/writer to the state corresponding to the checkpoint.
5. Throw ItemStreamException if safe initialization is not possible.

For example, a file reader can open the file and skip the number of lines already processed previously. When the Job restarts, open() receives the persisted context and restores the read position.

~~~java
@Override
public void open(ExecutionContext executionContext) {
    try {
        reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);

        long linesAlreadyRead = executionContext.getLong(READ_COUNT_KEY, 0L);
        for (long i = 0; i < linesAlreadyRead; i++) {
            if (reader.readLine() == null) {
                throw new ItemStreamException(
                        "Checkpoint is beyond the end of the input file");
            }
        }

        currentLine = linesAlreadyRead;
    } catch (IOException ex) {
        throw new ItemStreamException("Cannot open input file: " + path, ex);
    }
}
~~~

This illustrates the concept of restoring checkpoints by line count. In real-world applications, it is necessary to verify that the input file is still the same file/version used previously. If the file was replaced or its content changed, the same line count could point to different data. Additional metadata such as checksum, file size, version, or batch ID can be saved to verify the resource.

Resources should not be opened in a reader's constructor. Bean constructors may execute when the application context starts up, before a StepExecution exists. open() is the proper place to open resources according to the Step lifecycle.

## 4. update() — saving checkpoints

update() allows an ItemStream to write its current state to the ExecutionContext. For a chunk-oriented Step, Spring Batch invokes this callback at checkpoint milestones, typically before the chunk transaction commits. Metadata and chunk data are managed according to transaction/repository configuration to support consistent recovery.

For example, a reader has read up to line 250:

~~~java
@Override
public void update(ExecutionContext executionContext) {
    executionContext.putLong(READ_COUNT_KEY, currentLine);
}
~~~

When the Job restarts, open() retrieves the saved value to resume from the checkpoint. If the application does not write the necessary state to the context, a custom reader may start over from the beginning or fail to restore accurately.

Not every runtime value needs to be put into the context. Store only the small pieces of information required for recovery, such as:

- Number of lines read.
- Last unique key processed.
- Current page or offset.
- Version or snapshot identifier.
- Writer state needed to resume writing.

Do not store the entire list of read items or the full file content in the ExecutionContext. The context is persisted in the metadata repository and must remain small and serializable.

## 5. close() — releasing resources

close() is called by Spring Batch when the Step finishes so the stream component can release opened resources. Typical operations performed:

- Flush buffers if the writer's contract requires it.
- Close open readers or writers.
- Close cursors or streams owned by the component.
- Release handles, temporary resources, or file descriptors.
- Clear runtime references to avoid holding onto resources after the Step finishes.

Example:

~~~java
@Override
public void close() {
    if (reader != null) {
        try {
            reader.close();
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot close input reader", ex);
        } finally {
            reader = null;
        }
    }
}
~~~

close() must be safe when resources were only partially opened. A failure in open() may leave only some resources initialized; cleanup should not produce confusing secondary errors or mask the root exception. Check for null and release each opened resource individually.

Do not silently swallow every exception in close(). If an important resource cannot be closed or flushed, the Step may need to reflect that error. Clearly decide whether cleanup failures should fail the Step or be recorded as secondary errors, depending on data criticality.

## 6. Example of a custom reader implementing ItemStream

The example below creates a reader that reads a text file line by line, saves the line count read, and restores its position on restart:

~~~java
public class CheckpointFileReader
        implements ItemStreamReader<String> {

    private static final String READ_COUNT_KEY =
            "checkpointFileReader.readCount";

    private final Path path;
    private BufferedReader reader;
    private long currentLine;

    public CheckpointFileReader(Path path) {
        this.path = path;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        try {
            reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
            long savedLine = executionContext.getLong(READ_COUNT_KEY, 0L);

            for (long i = 0; i < savedLine; i++) {
                if (reader.readLine() == null) {
                    throw new ItemStreamException(
                            "Saved position exceeds input length");
                }
            }

            currentLine = savedLine;
        } catch (IOException ex) {
            closeQuietly();
            throw new ItemStreamException("Unable to open " + path, ex);
        }
    }

    @Override
    public String read() throws Exception {
        if (reader == null) {
            throw new IllegalStateException("Reader has not been opened");
        }

        String line = reader.readLine();
        if (line != null) {
            currentLine++;
        }
        return line;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong(READ_COUNT_KEY, currentLine);
    }

    @Override
    public void close() {
        try {
            closeQuietly();
        } catch (RuntimeException ex) {
            throw new ItemStreamException("Unable to close reader", ex);
        }
    }

    private void closeQuietly() {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException ex) {
                throw new ItemStreamException("Unable to close file " + path, ex);
            } finally {
                reader = null;
            }
        }
    }
}
~~~

This reader illustrates the core responsibilities:

- open() opens the file and restores the line count from context.
- read() retrieves a line and increments the counter when data is present.
- update() writes the counter to context.
- close() closes the file.

This is a foundational example and does not cover every production scenario. For large files, skipping line by line in open() can be slow when restarting far from the beginning; byte offsets, indexed files, or seek-capable data sources can be used instead. File identity should be verified before restoring, and read/close errors handled explicitly. If the reader needs to be used in Step scope, declare the bean with `@StepScope` when it depends on JobParameters or context.

## 7. Registering an ItemStream with a Step

Spring Batch only manages the lifecycle of streams that the Step recognizes and registers. If a reader or writer is configured directly in the Step and implements ItemStream, the framework usually registers that component's lifecycle automatically.

Example:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemStreamReader<String> reader,
        ItemWriter<String> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<String, String>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

The reader is passed directly into the Step configuration and implements ItemStream, so Spring Batch can invoke open/update/close during the Step lifecycle.

### Delegates hidden inside a composite

Some readers/writers are wrapped inside a composite or adapter. If the wrapper does not implement ItemStream or does not forward lifecycle calls to the delegate, Spring Batch does not automatically know that the delegate needs open/update/close.

In that case, the delegate must be registered as a Step stream:

~~~java
return new StepBuilder("compositeWriteStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(100, transactionManager)
        .reader(reader)
        .writer(compositeWriter)
        .stream(delegateWriter)
        .build();
~~~

The stream(...) method registers an additional ItemStream so the Step invokes its lifecycle callbacks. Separate registration is only needed when the wrapper does not manage the delegate itself. If the composite already implements ItemStream and forwards callbacks to the delegate, avoid duplicate registration that would cause open/update/close to be called twice.

Check the contract of the composite/adapter used in your application's Spring Batch version. Do not assume every wrapper automatically forwards lifecycle calls.

## 8. ItemStream and built-in readers/writers

Many built-in Spring Batch components already implement ItemStream to manage resources and checkpoints:

- **FlatFileItemReader:** opens the file, tracks read position, and supports state restoration.
- **MultiResourceItemReader:** manages a set of resources and the current position in the file list.
- **JdbcCursorItemReader:** manages the cursor/result set and necessary state according to its implementation.
- **JdbcPagingItemReader:** saves page or key information to continue reading.
- **FlatFileItemWriter:** manages the output file, header/footer, append mode, and write state.
- **StaxEventItemReader** and XML readers: manage the resource and processing position according to their supported capabilities.

When using built-in components, prefer configuring their restart/resource properties rather than opening the same resource externally. Check the documentation for your specific version to know whether a reader/writer supports restart and under what conditions.

A reader/writer can implement ItemStream yet not necessarily save all state if state saving is disabled by configuration. For example, some builders have a saveState(false) option. When disabled, the component may not write checkpoints for recovery after restart; only use this when the Step does not need restart or state is managed by another mechanism.

## 9. Stream names and keys in ExecutionContext

Built-in readers/writers typically use the component name to build keys for saving state in the ExecutionContext. This name must remain stable across runs and restarts.

For custom readers, use namespaced keys to avoid collisions with keys from other components:

~~~java
private static final String READ_COUNT_KEY =
        "customerFileReader.readCount";
~~~

Do not use overly generic keys like count, index, or position if the Step has multiple streams. Two streams writing the same key can overwrite each other's state and cause restart at the wrong position.

If renaming a reader or checkpoint key in a new application version, consider compatibility with older JobExecutions that may still need restarting. A key change can prevent the reader from reading previously saved checkpoints. You can support reading legacy keys during a transition period or explicitly decide that old executions will no longer be restarted with the new code.

## 10. open() on restart

When a Job restarts the same JobInstance, Spring Batch restores persisted metadata from the JobRepository. open() receives the ExecutionContext of the re-executed StepExecution, including previously persisted checkpoints.

Example:

~~~text
First run:
  open(context: readCount=0)
  read 100 items
  update(context: readCount=100)
  commit chunk
  read next 100 items
  update(context: readCount=200)
  commit chunk
  error on next chunk
  close()

Restart:
  open(context: readCount=200)
  restore reader after item 200
  continue reading the remaining items
~~~

Checkpoints typically represent state saved at the most recent commit boundary. If the application stops abruptly before a new checkpoint is committed, the reader may restore an older checkpoint and re-read some data. This is why writers need to participate in transactions or have appropriate idempotency.

Restart is only safe when the input resource still matches the checkpoint. If the file was modified, the source table changed, or a paging sort key is unstable, restoring position can lead to skipped or duplicate processing. Use a batch ID, snapshot ID, version, or checksum to verify the source.

## 11. close() and error handling

close() is the place to release resources regardless of whether the Step ends normally or due to an error. Do not invoke close only on the success branch of a reader/writer.

Some principles:

- Close a resource only if it was opened.
- Set resource fields to null after closing to avoid reusing stale handles.
- If there are multiple resources, attempt to close all of them even if closing one fails.
- Do not let cleanup errors mask the root exception from reading/writing if the framework already encountered a primary error.
- Do not close resources managed by the Spring transaction manager or container on behalf of the application.
- Do not keep resources open in singleton fields across multiple StepExecutions.

Example of cleaning up multiple resources:

~~~java
@Override
public void close() {
    ItemStreamException failure = null;

    if (reader != null) {
        try {
            reader.close();
        } catch (IOException ex) {
            failure = new ItemStreamException("Cannot close reader", ex);
        } finally {
            reader = null;
        }
    }

    if (output != null) {
        try {
            output.close();
        } catch (IOException ex) {
            if (failure == null) {
                failure = new ItemStreamException("Cannot close output", ex);
            } else {
                failure.addSuppressed(ex);
            }
        } finally {
            output = null;
        }
    }

    if (failure != null) {
        throw failure;
    }
}
~~~

The example shows the need to continue closing remaining resources even if the first resource fails to close. In production code, a helper or try/finally structure can be used to reduce duplication, while still ensuring all opened resources are released.

## 12. ItemStream does not replace transaction management

ItemStream manages lifecycle and checkpoints. It does not create transactions, commit business data, or guarantee that external side effects are rolled back.

For instance, a writer opens a file and writes data. A database transaction rollback cannot automatically erase bytes already written to the file. If consistent output files on restart are needed, you can:

- Write a temporary file keyed by batch ID and publish/rename it after the Step completes.
- Save offsets/checkpoints and truncate the file back to the committed position before continuing, if the format and filesystem support it.
- Write data to the database first, then generate the file from committed data.
- Use separate output versions and publish only the complete version.

Similarly, close() closing a file does not mean the file content was committed along with the database transaction. Design resource and transaction boundaries according to the system type.

## 13. ItemStream with Tasklet

A Tasklet is typically invoked inside a transaction as configured by TaskletStep. If a Tasklet needs to manage a resource with its own lifecycle, it can implement ItemStream alongside Tasklet or register a separate stream with the Step.

Example structure:

~~~java
public class FileProcessingTasklet implements Tasklet, ItemStream {

    private BufferedReader reader;

    @Override
    public void open(ExecutionContext executionContext) {
        // Open file and restore state if needed.
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {
        // Perform Tasklet work.
        return RepeatStatus.FINISHED;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // Save checkpoint if Tasklet may run multiple iterations.
    }

    @Override
    public void close() {
        // Close resource.
    }
}
~~~

If a Tasklet only opens a resource during a single invocation and can use try-with-resources inside execute, that approach is usually simpler. ItemStream is useful when a resource must persist across the Step lifecycle or state needs to be saved for restart.

When using a custom Tasklet, verify that the stream is registered with the Step so lifecycle callbacks are invoked. If the Tasklet or wrapper is not automatically recognized as an ItemStream, register it via the Step's stream API.

## 14. ItemStream and @StepScope

@StepScope controls bean lifecycle per StepExecution; ItemStream controls the resource lifecycle of a stream component. The two mechanisms complement each other:

- @StepScope enables creating a bean with JobParameters or the StepExecutionContext of the current execution.
- ItemStream opens resources when the Step starts, updates checkpoints, and closes resources when the Step finishes.

Example of a reader needing both a path from context and restart support:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
~~~

Spring creates the reader for the current StepExecution. When the Step runs, Spring Batch invokes the reader's lifecycle to open the file, save checkpoints, and close the resource. @StepScope does not replace open/close; nor does ItemStream replace late-binding inputFile.

## 15. Resource management by component type

Not every resource is opened and closed in the same way. Distinguish between resources owned by an ItemStream and resources managed by the framework or transaction manager.

| Resource | Typically Suitable Management Approach |
|---|---|
| Input file | Reader opens in open, closes in close |
| Output file | Writer opens in open, flushes/checkpoints in update per implementation, closes in close |
| JDBC cursor/result set | Use a built-in reader or ensure the cursor is closed properly in the lifecycle |
| JDBC connection obtained from DataSource | Typically let the Spring transaction manager/JdbcTemplate manage it; do not manually close connections participating in a transaction |
| Shared HTTP client | Typically an application-managed bean; do not create/close clients per item unnecessarily |
| Temporary file | Create and delete per lifecycle, but delete only when certain it is no longer needed for restart or auditing |
| Custom socket/stream | The owning component must close in close and handle cleanup errors |

The principle is that a component only closes resources it owns. Mistakenly closing a connection managed by the transaction manager can corrupt the chunk transaction.

## 16. Error handling in open, update, and close

All three callbacks can throw errors:

- **open error:** resource does not exist, lacks read permission, cannot connect, or checkpoint is invalid. The Step cannot safely start processing.
- **update error:** cannot serialize or persist state. The checkpoint is unreliable; the chunk may fail to commit depending on transaction/repository configuration.
- **close error:** resource cannot be closed or flushed. The Step may record a cleanup error even if earlier processing committed.

Do not turn these errors into a success status by catching exceptions and ignoring them. If an error breaks restartability or leaves output incomplete, let the Step reflect the failure status or record it explicitly per operational policy.

ItemStreamException is the specialized exception used to report stream lifecycle errors. Keep the original exception as the cause so logs can trace the actual root cause.

## 17. Testing the ItemStream lifecycle

The lifecycle should be verified using Step integration tests or component tests combined with Spring Batch Test. Important scenarios:

1. open is called before the reader begins reading.
2. The resource is opened exactly once per StepExecution per the expected lifecycle.
3. update writes the current checkpoint into the ExecutionContext.
4. Restart passes the saved checkpoint into open.
5. close releases the resource after the Step completes.
6. close is still executed on the cleanup path when the Step fails.
7. If open fails, no items are processed from an unready resource.
8. A failed update does not allow the Step to report success with an unreliable checkpoint.
9. Delegate streams are registered and receive all lifecycle callbacks.
10. No file descriptors, cursors, or resources leak across multiple runs.

Example testing callbacks with a stub stream:

~~~java
class RecordingItemStream implements ItemStream {

    boolean opened;
    boolean updated;
    boolean closed;
    long savedPosition;

    @Override
    public void open(ExecutionContext executionContext) {
        opened = true;
        savedPosition = executionContext.getLong("position", 0L);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        updated = true;
        executionContext.putLong("position", savedPosition + 10L);
    }

    @Override
    public void close() {
        closed = true;
    }
}
~~~

A test can register this stream with a Step and assert the flags after launch. To test real restart, use a persistent JobRepository across two JobExecutions and verify the context value is restored, rather than only testing a single open call in a unit test.

## 18. Common Pitfalls

**Implementing only ItemReader and forgetting ItemStream:** a custom reader lacks the lifecycle to open/close resources and save checkpoints. Implement ItemStreamReader when those capabilities are needed.

**Opening files in the constructor:** constructors may run before StepExecution or JobParameters exist. Open resources in open.

**Not restoring state in open:** a restarted Job may re-read from the start or the wrong position. Read checkpoints from ExecutionContext.

**Not writing checkpoints in update:** the reader cannot save necessary progress. Write small, stable keys to the context.

**Forgetting to register a delegate stream:** a wrapper that does not forward the lifecycle leaves the delegate unopened, uncheckpointed, or unclosed.

**Registering a stream twice:** a composite already managing its delegate alongside separate Step registration can cause callbacks to fire twice. Verify the wrapper's contract.

**Not closing resources on error:** file descriptors, cursors, or streams can leak. Cleanup must cover both success and failure paths.

**Closing unowned resources:** manually closing connections managed by the transaction manager can corrupt transactions.

**Saving unstable checkpoints:** changing keys, reader names, or inputs between restarts can render old checkpoints unusable.

**Confusing close with commit:** closing a file or stream does not replace database transaction commit and does not guarantee non-transactional outputs are rolled back.

## Conclusion

ItemStream defines the lifecycle for batch components that need to manage resources and state. open() opens resources and restores checkpoints from ExecutionContext; update() saves state at Step checkpoint milestones; close() releases resources when the Step finishes. Readers/writers implementing ItemStream must be registered with the Step so Spring Batch manages callbacks. When using composites or delegates, ensure the lifecycle is forwarded or register additional streams exactly once. Open resources in open, save small and stable checkpoints in update, close all owned resources in close, and test restarts and failure paths to prevent resource leaks or corrupted data recovery.

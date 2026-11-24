# Closing Resources When a Job Fails in Spring Batch

A Spring Batch Job typically works with many external resources: files, database cursors, streams, connections, message consumers, temporary files, locks, or remote service clients. These resources must be released at the right time, even when a Step throws an exception and the Job ends in the FAILED status.

Closing resources is part of execution lifecycle management. Spring Batch provides the **ItemStream** interface with open, update, and close callbacks to manage readers, writers, and stateful components. For resources that only exist within a single invocation, Java provides try-with-resources. For Step-scoped or Job-scoped resources, listeners or appropriate lifecycle mechanisms can be used.

Three actions must be distinguished: **transaction rollback**, **closing resources**, and **cleaning up temporary data**. Rollback undoes changes of the current transaction; close releases handles or connections; cleanup deletes, quarantines, or reclaims created resources. One action does not automatically replace the other two.

This lesson covers the resource lifecycle when a Step succeeds or fails, how to use ItemStream and listeners, how to close resources after partial initialization, how to handle incomplete output files, and how to protect the application when a process terminates abruptly.

## 1. Why must resources be closed when a Job fails?

A resource typically consumes JVM, operating system, or external system resources. If not closed on time, the application may experience:

- Files keeping open handles, preventing renaming, deletion, or reading by other processes.
- JDBC cursors, statements, or connections held longer than necessary.
- Unclosed HTTP response bodies or streams exhausting the connection pool.
- Message consumers or subscriptions holding resources after the Step ends.
- Leftover temporary files, locks, or leases.
- Unflushed buffers leaving the output file missing data.
- Workers holding resources while the Job is already FAILED, preventing subsequent runs from proceeding.

For example, a reader opens a CSV file at the start of a Step. While reading, the processor throws an unrecoverable exception. Spring Batch marks the Step as failed. If the reader is not closed, the file handle may persist until garbage collection or process termination; that timing is not reliable enough for batch processing.

Good resource management helps:

1. Release resources as soon as their usage scope ends.
2. Prevent file descriptor, connection, and buffer leaks.
3. Ensure restarts or reruns are not blocked by stale resources.
4. Keep temporary and official file states clear.
5. Make failure paths predictable and testable.

## 2. Distinguishing close, rollback, and cleanup

These three operations often occur together when a Job fails, but have different meanings.

| Operation | Purpose | Example |
|---|---|---|
| Rollback | Undo changes within the current transaction | Undo inserts of an uncommitted chunk |
| Close | Release open resources | Close BufferedReader, cursor, or response body |
| Cleanup | Handle created temporary resources or data | Delete temporary files or move failed files to a quarantine directory |

For example, a Step reads a file, writes to a database, and generates a report file:

- When the writer fails, the database transaction can roll back.
- The reader and writer must close open files or cursors.
- Incomplete report files need to be deleted or quarantined per policy.
- If a previous Step already committed data, rolling back the current Step does not delete that data.

Rollback does not automatically close all file handles. Close does not automatically roll back the database. Closing a file also does not automatically delete that file.

~~~mermaid
flowchart TD
    A["Job or Step encounters an error"] --> B["Roll back current transaction"]
    A --> C["Close open resources"]
    A --> D["Handle temporary files, locks, and leases"]
    B --> E["Transaction data is rolled back"]
    C --> F["Handles and connections are released"]
    D --> G["Delete, quarantine, or reclaim"]
~~~

Failure-handling design must decide each of these three branches separately.

## 3. ItemStream lifecycle

Spring Batch provides the ItemStream interface for components that need to manage state and resources within a Step:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

In practice, these methods may declare throwing ItemStreamException.

Meaning:

- **open:** opens the resource and restores state from the ExecutionContext if this is a restart.
- **update:** saves the checkpoint or state needed for recovery.
- **close:** releases the resource when the Step finishes.

Stateful readers and writers typically implement combined interfaces such as ItemStreamReader or ItemStreamWriter.

~~~java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}
~~~

Several built-in Spring Batch readers/writers, such as FlatFileItemReader and JdbcCursorItemReader, already manage resource lifecycles. When properly configured and registered with the Step, the framework invokes the corresponding callbacks.

### Is close called when the Step fails?

During normal Step execution lifecycle, Spring Batch closes registered ItemStreams when the Step completes, including exit paths caused by exceptions. This allows readers/writers to release resources after a Step failure.

However, do not treat this as a guarantee for every kind of incident. If the JVM is killed with kill -9, the machine loses power, the container is forcefully terminated, or the process crashes before the lifecycle completes, the close callback may not run. External resources need additional leases, timeouts, or recovery mechanisms.

In addition, if a resource is opened outside the Step lifecycle, the framework does not automatically know to close it. Manage such resources explicitly using try-with-resources, ItemStream, or an appropriate listener.

## 4. Self-managed reader resources with ItemStreamReader

When writing a custom reader that opens files or streams, implement ItemStreamReader so Spring Batch manages open, update, and close.

Example of a reader reading a text file and saving the number of lines read:

~~~java
public class ManagedLineReader implements ItemStreamReader<String> {

    private final Path path;
    private BufferedReader reader;
    private long lineNumber;

    public ManagedLineReader(Path path) {
        this.path = path;
    }

    @Override
    public void open(ExecutionContext context) {
        try {
            reader = Files.newBufferedReader(
                path,
                StandardCharsets.UTF_8
            );

            lineNumber = context.getLong("managedLineReader.line", 0L);

            for (long i = 0; i < lineNumber; i++) {
                if (reader.readLine() == null) {
                    break;
                }
            }
        } catch (IOException ex) {
            closeAfterOpenFailure();
            throw new ItemStreamException(
                "Unable to open or restore reader",
                ex
            );
        }
    }

    @Override
    public String read() throws Exception {
        if (reader == null) {
            throw new IllegalStateException("Reader has not been opened");
        }

        String line = reader.readLine();
        if (line != null) {
            lineNumber++;
        }
        return line;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("managedLineReader.line", lineNumber);
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
                    "Unable to close reader",
                    ex
                );
            }
        }
    }

    private void closeAfterOpenFailure() {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException ignored) {
                // Preserve the original initialization exception.
            } finally {
                reader = null;
            }
        }
    }
}
~~~

This example illustrates saving a checkpoint by line number. For large files, skipping from the start to the checkpoint can be expensive; production readers can use offsets, indexes, or appropriate seek mechanisms.

### Why does close set reader to null before closing?

Setting the field to null before calling close makes the method more idempotent: if cleanup is called again, the reader is no longer treated as an open resource. This is a useful pattern for resource lifecycles.

Depending on requirements, the application can log resource-closing exceptions or attach them to the primary error. Do not lose the original exception just because close also failed.

## 5. Partial resource initialization must self-cleanup

An easily overlooked bug occurs when open() opens multiple resources but fails midway through.

Example:

1. Opening the input file succeeds.
2. Creating a buffer or temporary output succeeds.
3. Opening an additional auxiliary stream starts.
4. The third step fails.

If open() immediately throws an exception without closing the resources opened in earlier steps, the framework may lack enough information to clean up an object that has not completed initialization.

Ensure open() itself cleans up any created resources if opening fails to complete.

~~~java
@Override
public void open(ExecutionContext context) {
    try {
        input = Files.newInputStream(inputPath);
        output = Files.newOutputStream(
            temporaryOutput,
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING
        );
        writer = new BufferedWriter(
            new OutputStreamWriter(output, StandardCharsets.UTF_8)
        );
    } catch (IOException ex) {
        closeQuietly();
        throw new ItemStreamException(
            "Unable to initialize Step resources",
            ex
        );
    }
}
~~~

The closeQuietly helper should close each existing resource and set fields to null in finally. If multiple resources depend on each other, close them in reverse order of opening.

This principle is similar to try-with-resources: already-opened resources must be released even when initializing the remaining ones fails.

## 6. Registering an ItemStream with a Step

Spring Batch automatically manages a directly configured reader or writer if that object implements ItemStream. However, an auxiliary resource or delegate nested inside a custom component may not be visible to the framework.

Example Step with a reader, writer, and an auxiliary stream:

~~~java
@Bean
Step exportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemWriter<Customer> customerWriter,
        ItemStream auditStream) {

    return new StepBuilder("exportStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .writer(customerWriter)
        .stream(auditStream)
        .build();
}
~~~

The stream(...) method registers an additional ItemStream so the Step invokes its lifecycle.

### Composite reader or writer

If a custom composite contains a delegate that opens resources, the composite must forward open, update, and close to the delegate, or register the delegate separately with the Step via stream(...).

If registration is forgotten:

- The Step may read/write successfully, but the delegate is not closed per lifecycle.
- Checkpoints may not be saved.
- Restart may reopen the resource from the beginning or fail to restore the right position.
- Resources may remain open after the Step finishes.

Check the contract of the composite in use. Some built-in composites already manage ItemStream delegates; custom composites must implement forwarding or register the appropriate streams themselves.

## 7. Closing writer resources

A writer may hold file handles or buffers throughout a Step. If the writer itself implements ItemStreamWriter, close() is the place to flush and close the stream.

Example file writer:

~~~java
public class ManagedCsvWriter implements ItemStreamWriter<Customer> {

    private final Path outputPath;
    private BufferedWriter writer;

    public ManagedCsvWriter(Path outputPath) {
        this.outputPath = outputPath;
    }

    @Override
    public void open(ExecutionContext context) {
        try {
            writer = Files.newBufferedWriter(
                outputPath,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND
            );
        } catch (IOException ex) {
            throw new ItemStreamException(
                "Unable to open output file",
                ex
            );
        }
    }

    @Override
    public void write(Chunk<? extends Customer> chunk)
            throws Exception {
        if (writer == null) {
            throw new IllegalStateException("Writer has not been opened");
        }

        for (Customer customer : chunk.getItems()) {
            writer.write(customer.customerId());
            writer.write(",");
            writer.write(customer.fullName());
            writer.newLine();
        }
    }

    @Override
    public void update(ExecutionContext context) {
        // Position or state needed for recovery can be saved here.
    }

    @Override
    public void close() {
        BufferedWriter current = writer;
        writer = null;

        if (current != null) {
            try {
                current.flush();
                current.close();
            } catch (IOException ex) {
                throw new ItemStreamException(
                    "Unable to flush or close output file",
                    ex
                );
            }
        }
    }
}
~~~

This is a minimal lifecycle example. Production writers need to consider checkpoints, append/truncate on restart, headers, encoding, atomic publishing, and behavior when close fails.

### Close can flush uncommitted data

File writers do not participate in database transactions by default. When close calls flush, buffered content may be written to the file even if the database chunk rolled back. Thus, output files are not automatically transactionally synchronized with the database.

If a file should only be published when the Job succeeds, write to a separate temporary file and publish only after the entire file-generation step has completed. Do not rely on close to decide whether the file is valid.

## 8. Using try-with-resources in a Tasklet

For resources only needed during a single Tasklet invocation, try-with-resources is usually simpler and safer than keeping a field to close in a listener.

Example reading a file in a Tasklet:

~~~java
@Bean
Tasklet validateFileTasklet() {
    return (contribution, chunkContext) -> {
        Path input = Path.of("/data/in/customers.csv");

        try (BufferedReader reader = Files.newBufferedReader(
                input,
                StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                validate(line);
            }
        }

        return RepeatStatus.FINISHED;
    };
}
~~~

Even if validate() throws an exception, Java closes the BufferedReader before the exception leaves the Tasklet. Spring Batch then handles the transaction and Step status according to the exception.

### Do not hold local resources across multiple execute calls

A Tasklet can be invoked repeatedly if it returns RepeatStatus.CONTINUABLE. If each execute call opens a resource, close the resource within that same call. Do not open a file on the first call assuming it will only be invoked once, unless the lifecycle is explicitly designed that way.

If a resource must persist across the entire Step and needs checkpointing, use ItemStream or an appropriate lifecycle mechanism rather than holding a file handle in an unrecoverable local variable.

## 9. Using StepExecutionListener for Step-specific cleanup

StepExecutionListener provides callbacks before and after a Step:

~~~java
public interface StepExecutionListener extends StepListener {
    void beforeStep(StepExecution stepExecution);
    ExitStatus afterStep(StepExecution stepExecution);
}
~~~

afterStep is called when the Step finishes under the normal lifecycle. It can be used to record statistics, release an auxiliary resource not modeled as an ItemStream, or perform lightweight cleanup.

Example:

~~~java
@Bean
StepExecutionListener temporaryDirectoryListener() {
    return new StepExecutionListener() {

        @Override
        public void beforeStep(StepExecution stepExecution) {
            // Create or resolve the working directory of the Step.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            Path workDirectory = resolveWorkDirectory(stepExecution);

            try {
                cleanupEmptyTemporaryFiles(workDirectory);
            } catch (IOException ex) {
                log.error(
                    "Unable to cleanup Step directory {}",
                    stepExecution.getStepName(),
                    ex
                );
            }

            return null;
        }
    };
}
~~~

Attaching the listener:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .listener(temporaryDirectoryListener)
    .build();
~~~

### When to use ItemStream instead of a listener?

If the resource is a reader/writer with open, checkpoint, and close, ItemStream is usually more appropriate because the resource's lifecycle is tied directly to the Step.

Listeners suit actions dependent on Step status or cleanup tasks that do not need checkpoints. Avoid using listeners to replace reader/writer lifecycles when the framework already provides ItemStream.

afterStep should not become the place to execute critical business work that the Job needs to restart. If publishing or cleanup is a mandatory part of the workflow, model it as a separate Step so JobRepository tracks it.

## 10. Job-level cleanup with JobExecutionListener

A Job may create resources shared across multiple Steps, such as a temporary directory or a coordination lease. JobExecutionListener provides callbacks before and after the Job:

~~~java
public interface JobExecutionListener extends JobListener {
    void beforeJob(JobExecution jobExecution);
    void afterJob(JobExecution jobExecution);
}
~~~

Example cleanup based on final status:

~~~java
@Bean
JobExecutionListener jobResourceListener() {
    return new JobExecutionListener() {

        @Override
        public void beforeJob(JobExecution jobExecution) {
            // Prepare Job-level metadata or resources.
        }

        @Override
        public void afterJob(JobExecution jobExecution) {
            if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
                finalizeSuccessfulRun(jobExecution);
            } else {
                quarantineFailedRun(jobExecution);
            }
        }
    };
}
~~~

Registering the listener on the Job:

~~~java
return new JobBuilder("customerImportJob", jobRepository)
    .listener(jobResourceListener)
    .start(validateStep)
    .next(importStep)
    .next(publishStep)
    .build();
~~~

afterJob is suitable for Job-level cleanup or housekeeping after the Steps have finished. Actions inside the listener must be idempotent because operations may need to re-run cleanup after an incident.

### Do not put all business publishing inside afterJob

If publishing is a mandatory step determining whether the Job succeeds, create a final publish Step. When the publish Step fails, JobRepository records the failure status and can restart according to rules.

afterJob is a lifecycle callback, not a Step with its own checkpoint. If the listener runs after the Job has already been marked finished, an exception in the listener is not equivalent to a restartable failed Step. Use listeners for auxiliary cleanup; use Steps for mandatory business work.

## 11. Cleanup order and preserving the original exception

A failure path may encounter two errors:

1. The reader or writer throws the primary exception.
2. close() also throws an exception while trying to release the resource.

The primary error information must be preserved so operations knows why the Job failed. The resource-closing exception still needs to be recorded because it may indicate a leak or corrupted resource.

For self-managed resource code, try-with-resources lets Java attach exceptions occurring during close as suppressed exceptions if the block body already threw an exception.

Example:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
~~~

If process() throws an IOException and close() also fails, the primary exception is preserved and the close error can be accessed via getSuppressed().

For ItemStreams managed by Spring Batch, throw an ItemStreamException with the root cause and log with sufficient context. Do not catch and ignore all close exceptions because doing so hides resource leaks.

### Closing in reverse order

If resource B depends on resource A, typically open A before B, then close B before A.

Example:

1. Open connection.
2. Create statement.
3. Open result set.
4. During cleanup: close result set, statement, then connection if the application owns that connection.

With Spring-managed JDBC, let JdbcTemplate or the transaction manager manage connections. Do not manually close connections bound to the current transaction.

## 12. Database resources when a Step fails

Database resources require distinguishing between application-owned resources and Spring transaction-managed resources.

Common objects:

- Connection.
- PreparedStatement.
- ResultSet.
- Cursor reader.
- EntityManager.

When using JdbcTemplate, NamedParameterJdbcTemplate, or Spring Data repositories, the framework manages most of the statement/result set lifecycle and participates in transactions appropriately.

If opening JDBC resources manually, use try-with-resources:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql);
     ResultSet resultSet = statement.executeQuery()) {

    while (resultSet.next()) {
        processRow(resultSet);
    }
}
~~~

This snippet is appropriate when the application truly owns an independently opened connection. If the connection was obtained from a transaction-aware Spring API and belongs to the Step transaction, do not manually close it in a way that breaks the transaction.

### JdbcCursorItemReader

JdbcCursorItemReader is a stateful reader that manages its cursor/statement/connection according to its lifecycle. When used directly in a Step, let Spring Batch call open, update, and close. Do not grab the internal cursor and close it from another listener.

If the Step fails, the chunk transaction may roll back, but the reader still needs to close the cursor. These two actions have separate roles.

## 13. HTTP resources and external clients

When making HTTP calls, close the response body or stream immediately after reading finishes. Connection pools are usually reused; not every request needs to close the entire HTTP client.

Example using a client with a response resource:

~~~java
try (InputStream body = responseBodyStream) {
    return parseResponse(body);
}
~~~

In practice, the specific API of WebClient, RestClient, HttpClient, or other libraries has its own rules. Use the release/close mechanism of that library.

### Distinguishing client and response lifecycles

- An HTTP client can be an application-wide singleton closed on application shutdown.
- A response body or stream belongs to a single request and must be released after reading.
- A request timeout does not prove the server did not execute the operation.
- Retrying requests requires idempotency if the operation has side effects.

Do not close a singleton HTTP client after each item or after each Step if the client is shared across other Jobs. Only close resources whose ownership belongs to the current scope.

## 14. Incomplete output files when a Job fails

Closing a file does not mean the file is valid. If a writer writes to a file and the Step fails midway, the file may contain partial output.

A safe design is to write to a temporary file and publish after the entire workflow succeeds:

~~~mermaid
flowchart TD
    A["Writer opens staging file"] --> B["Write each chunk"]
    B --> C["Step finishes and closes file"]
    C --> D{"Job processed successfully?"}
    D -- "Yes" --> E["Publish / atomic move"]
    D -- "No" --> F["Quarantine or delete staging file"]
    E --> G["Official output"]
    F --> H["Do not publish incomplete output"]
~~~

Example naming:

~~~java
Path staging = outputDirectory.resolve(
    "customer-summary-" + runId + ".part"
);

Path published = outputDirectory.resolve(
    "customer-summary-" + runId + ".csv"
);
~~~

After the writer closes the file and the publish Step confirms complete data, Files.move with ATOMIC_MOVE can be used if the filesystem supports it. If atomic move is not supported, a controlled fallback is needed to ensure incomplete files are never published.

### Why not delete the file immediately in close()?

close() is typically called whether the Step succeeds or fails. It should only close handles and finish the writer lifecycle. If close always deleted the file, valid output would also be deleted.

The decision to keep, publish, quarantine, or delete a file should depend on Step/Job status and be placed in a publish Step or appropriate cleanup lifecycle.

### Do not write directly to the official file

If a writer opens the official file and the Job fails, downstream consumers might read an incomplete file. Use a separate staging path and move it to the official location only after completion.

## 15. Cleaning up temporary files and working directories

Temporary files may be created by readers, writers, sorts, merges, or transformation steps. Ownership must be defined:

- Which Step creates the file?
- Which Step uses the file?
- When is the file considered no longer needed?
- When the Job fails, should it be kept for debugging or quarantined?
- When can it be safely deleted?
- Could another Job be using the same directory?

Do not use a single fixed temporary filename for multiple concurrent JobExecutions. Generate paths keyed by JobExecution ID, run ID, or a stable batch ID.

Example:

~~~java
Path workDirectory = rootDirectory.resolve(
    "job-" + jobExecution.getId()
);
Files.createDirectories(workDirectory);
~~~

Using a dedicated directory enables per-execution cleanup. Do not delete a shared directory or use broad wildcards that could contain files from other running Jobs.

### Idempotent cleanup

Cleanup may be called again after a failure. Write it to be idempotent:

~~~java
Files.deleteIfExists(temporaryFile);
~~~

If the file was already deleted, the operation still reaches the desired state. For directories, delete only files owned by that JobExecution that are confirmed to no longer be in use.

## 16. Locks, leases, and external resources

A Job may acquire a distributed lock, database advisory lock, file lock, or lease to ensure only one execution processes a batch.

If the Job fails, release the lock or let the lease expire. Do not rely solely on close callbacks because the process could be killed before the callback runs.

A lease design typically includes:

- Owner ID tied to the JobExecution.
- Expiration timestamp.
- Heartbeat or renewal while the Job remains active.
- Takeover mechanism after the lease expires.
- Owner check before releasing to avoid deleting another Job's lock.

Example releasing by owner:

~~~java
lockService.release(
    resourceKey,
    jobExecution.getId().toString()
);
~~~

Release must verify that the current lock belongs to that exact JobExecution. If an older Job finishes late and releases a lock already acquired by a newer Job, it must not delete the new owner's lock.

### Do not use file locks as the sole restart mechanism

File locks may be released by the operating system when the process exits, but they do not replace JobRepository metadata. Restart still requires checking JobExecution, checkpoints, and business state.

## 17. Message consumers and acknowledgment

With message queues, closing a consumer is different from acknowledging that a message was processed.

- Closing a consumer releases the connection or subscription.
- Acknowledging confirms the message was received and processed according to the protocol.
- Transaction rollback can cause messages to be redelivered if the broker and transaction are coordinated properly.
- If acknowledged too early, messages can be lost even if the database transaction rolls back.

Do not acknowledge a message before the chunk or business transaction reaches a safe state. With transactional queue readers, configure and test redelivery/rollback behavior accurately with the broker.

When a Job fails, closing the consumer releases connection resources. It does not by itself determine whether an in-flight message is redelivered; that depends on acknowledgment mode, visibility timeout, and transaction integration.

## 18. Executors and threads

TaskExecutor is usually a Spring-managed bean and may be shared across multiple Steps or Jobs. Do not shut down an executor from afterStep if that executor is not exclusively owned by that Step.

Rules:

- Singleton executors are closed with the application context lifecycle.
- Executors created specifically for a single JobExecution must have clear ownership and shutdown.
- Do not shut down a shared thread pool when a single Step fails.
- Wait for workers to finish within an appropriate timeout.
- Handle interrupts properly and do not swallow the interrupt flag.
- Do not hold resources in ThreadLocal without clearing them in finally.

If a worker thread owns a file or connection, the worker must close the resource within its own lifecycle. A thread manager listener cannot safely close local resources without explicit references and ownership.

## 19. JobExecutionListener and process kill incidents

Lifecycle callbacks work when Spring Batch gets a chance to end the Job/Step along the normal execution path. Callbacks cannot be guaranteed if the process is terminated forcefully.

Scenarios:

| Scenario | Does close/listener callback have a chance to run? | Protection Approach |
|---|---|---|
| Exception in processor/writer | Usually yes within the Step lifecycle | ItemStream and try-with-resources |
| Controlled Step failure | Usually yes | Step listener and Job listener |
| Job stopped via Spring Batch mechanism | Lifecycle has a chance to finish | Stop/interrupt handling and close |
| JVM crash or kill -9 | Not guaranteed | Lease, TTL, recovery scan |
| Machine power loss | Not guaranteed | Durable metadata and cleanup on startup |
| Container forcefully terminated | Not guaranteed without sufficient shutdown time | Graceful shutdown and lease expiry |

### Graceful shutdown

When deploying on servers or containers, configure a shutdown grace period long enough for Jobs to stop cleanly, transactions to finish, and resources to close. However, graceful shutdown only reduces risk; it does not eliminate the possibility of abrupt process death.

### Recovery on application restart

A recovery mechanism can scan staging directories or expired leases:

1. Find resources tied to inactive JobExecutions.
2. Cross-check JobRepository and owner ID.
3. Determine which files or leases can be safely reclaimed.
4. Quarantine or delete per retention policy.
5. Audit the cleanup result.

Do not delete files merely because their age is large. A long-running Job may still be using them. Verify the owner and status before cleanup.

## 20. Closing resources in listeners without causing secondary errors

A listener may encounter errors during cleanup. If cleanup is an auxiliary task, record the error without masking the root cause of the Job failure.

Example:

~~~java
@Override
public void afterJob(JobExecution execution) {
    try {
        releaseJobLease(execution);
    } catch (Exception cleanupException) {
        log.error(
            "Lease cleanup failed for execution {}",
            execution.getId(),
            cleanupException
        );
    }
}
~~~

If the lease cannot be released, TTL or a recovery process must reclaim it later. Do not ignore the error completely; log the owner, resource key, and timestamp.

If cleanup is a mandatory condition for the Job to be considered successful, execute it in a separate Step before the terminal transition. A Step can fail, be tracked, and be restarted by JobRepository.

### Do not arbitrarily alter Job status in listeners

afterJob and afterStep are lifecycle callbacks. Do not manually alter BatchStatus or ExitStatus to hide cleanup errors. If cleanup affects the business outcome, place it in the flow as a Step and define clear terminal states.

## 21. Closing resources during retry and skip

Retry, skip, and close can interact within a single Step:

- Retry may invoke the processor or writer again before the Step ends.
- Skip may cause the framework to roll back and isolate the failing item.
- ItemStream still needs to keep resources open throughout the Step lifecycle and close when the Step finishes.
- Do not close the reader or writer on each retry if the framework needs to reuse it on the next attempt.
- Do not delete staging files immediately when an item is skipped if other items still need to write to the same file.

If an HTTP request creates a separate response body per retry attempt, close that attempt's response body within that invocation. If a reader holds a cursor for the entire Step, let ItemStream manage the cursor until the Step finishes.

Distinguish per-attempt resources from Step-scoped resources:

| Scope | Example | Where to Close |
|---|---|---|
| Single method call | HTTP response body | try-with-resources/finally inside the method |
| Single item attempt | InputStream opened per item | finally of that processing attempt |
| Single Step | Cursor reader, file writer | ItemStream.close |
| Single Job | Shared lease or staging directory | Job lifecycle/cleanup Step |
| Entire application | Shared HTTP client, singleton executor | Application shutdown |

## 22. Resources in partitioning

In a partitioned Step, each worker has its own StepExecution and can open its own resources.

Example:

- Worker partition0 opens a cursor for ID range 1–250.
- Worker partition1 opens a cursor for ID range 251–500.
- Worker partition2 opens a cursor for ID range 501–750.

Each reader should be Step-scoped and manage its own lifecycle. When a worker fails, that worker's resources must close; other workers may still be running or may also terminate according to manager policy.

Do not share a single mutable reader or file handle across partitions if the implementation is not thread-safe.

### Output files per partition

Each worker should write its own file:

~~~text
staging/
  run-42/
    partition0.part
    partition1.part
    partition2.part
~~~

After the manager confirms all workers have completed, a subsequent Step can merge or publish the output. If one worker fails, do not publish the entire set of files as if the Job had completed.

Cleanup must know which partitions completed and which files are still being used by workers. Do not delete files of active workers.

## 23. Resources in a multi-threaded Step

In a multi-threaded Step, multiple threads may use Step components simultaneously. A shared resource requires synchronization or thread safety.

Consider:

- Is the reader thread-safe?
- Can the writer write concurrently?
- Does each thread have its own resource or share one?
- Who owns the resource and who is allowed to close it?
- Could one thread close the resource while another thread is still using it?
- When the Step is interrupted, how are remaining threads stopped and cleaned up?

Do not close a shared resource immediately when one thread encounters an error if other threads are still using it. Let the coordination mechanism finish the workers, then close the resource at the rightful owner.

For thread-local resources, create and close them within the scope of the thread's task. For shared resources, manage them at the Step or application level and close only after all consumers have finished.

## 24. Monitoring resources and detecting leaks

Do not rely only on whether the Job finishes. Monitor signs of resource leaks:

- Active connection count and connection hold duration.
- Number of file descriptors or file handles.
- Connection pool pending/timeout counts.
- HTTP connection pool leased/available counts.
- Number of active consumers/subscriptions.
- Number of old staging files not yet cleaned up.
- Number of expired leases not yet reclaimed.
- Time from Step completion to cleanup completion.

Logs should include:

- Job name and JobExecution ID.
- Step name and StepExecution ID.
- Resource name or resource key.
- Action open/close/release/cleanup.
- Outcome and exception if failed.
- Owner ID if the resource is shared.

Do not log tokens, credentials, or sensitive data payloads in resource logs.

### Useful metrics

Metrics can be created such as:

- batch.resource.open.count
- batch.resource.close.count
- batch.resource.cleanup.failure
- batch.staging.file.count
- batch.lease.expired.count

Actual metric names should follow system conventions. The goal is to detect continuously growing open resource counts or prolonged cleanup failures.

## 25. Testing closing resources when a Job fails

Tests must prove that close is called and resources are actually released, not merely that the Job has FAILED status.

### Testing ItemStream.close when the processor fails

Create a test reader implementing ItemStreamReader and recording the close callback:

~~~java
class TrackingReader implements ItemStreamReader<InputRecord> {

    boolean opened;
    boolean closed;

    @Override
    public void open(ExecutionContext context) {
        opened = true;
    }

    @Override
    public InputRecord read() {
        return new InputRecord("A");
    }

    @Override
    public void update(ExecutionContext context) {
    }

    @Override
    public void close() {
        closed = true;
    }
}
~~~

Configure the processor to throw a non-skippable exception. Run the Step and verify:

- StepExecution finishes FAILED.
- Reader was opened.
- close() was called during the Step completion lifecycle.
- No test resources remain open.

In tests, the reader should have a mechanism to terminate after a number of reads or throw an intentional error to avoid infinite loops.

### Testing close when the writer fails

Create a writer implementing ItemStreamWriter and make write() throw an exception. Verify:

- Chunk transaction rolls back according to policy.
- Step fails.
- Writer close() is called.
- Files or handles are closed.
- Temporary data is handled per separate cleanup policy.

### Testing mid-open failure

Create an ItemStream that opens resource A successfully but fails to open resource B. Verify open() itself closes A before throwing ItemStreamException.

This is an important test because the framework cannot close a resource whose object has not finished initializing and is not fully registered.

### Testing try-with-resources

Make processing inside a Tasklet throw an exception and verify that mocked resources or file streams are closed. Java try-with-resources must be tested on both success and exception paths.

### Testing idempotent cleanup

Invoke cleanup twice and verify it does not cause unexpected errors. For temporary files, on the second call the file may no longer exist. For leases, the second call must not mistakenly release another owner's lease.

### Testing process crash

A standard unit test cannot prove close callbacks run when a process is killed. Instead, test recovery logic:

1. Create metadata simulating an inactive execution.
2. Create an old lease or staging file tied to that execution.
3. Run the recovery scanner.
4. Verify the scanner checks owner and status.
5. Verify only expired and unused resources are reclaimed.

## 26. Common design mistakes

### Closing resources only when the Step succeeds

If close is only in the success branch, exceptions can leave resources behind. Use the ItemStream lifecycle, finally, or try-with-resources.

### Assuming rollback automatically closes files and cursors

Rollback manages transactions, not closing file handles, streams, or consumers.

### Assuming close deletes temporary files

Close releases handles and may flush buffers. Deleting or quarantining is a separate cleanup step.

### Opening resources in a singleton constructor

Resources may outlive a JobExecution and be unintentionally shared. Open them in ItemStream.open, a Tasklet method, or an appropriate lifecycle hook.

### Forgetting to register a custom ItemStream delegate

The framework only manages streams the Step knows about. Register delegates using stream(...) or forward lifecycle calls from composites.

### Closing shared clients in afterStep

A singleton HTTP client or executor may be shared across multiple Jobs. Closing it after one Step can break other Jobs.

### Cleaning up official files during close

close runs even when the Step succeeds. Do not delete valid output in this callback. Use staging and publish/cleanup based on Job status.

### Cleaning up all files in a shared directory

This may delete files of other running Jobs. Use per-execution directories and verify ownership.

### Relying on listeners to handle process crashes

Callbacks cannot run if the process is killed or the machine loses power. Use lease TTLs, startup recovery, and retention policies.

### Swallowing close exceptions

Resource leaks can be hidden. Record cleanup errors along with the resource key and execution ID.

### Manually closing connections owned by the transaction manager

Closing transaction-bound connections can break the Step transaction. Let Spring manage those resources.

### Acknowledging messages before commit

Messages may be lost if the database rolls back. Coordinate acknowledgments, broker transactions, and chunk commits.

## 27. Process for designing Job resource cleanup

When a Job uses external resources, follow this sequence:

1. **Inventory resources:** files, cursors, connections, response bodies, consumers, locks, leases, executors, and temporary outputs.
2. **Determine ownership:** whether the resource belongs to a method, item attempt, Step, Job, or entire application.
3. **Choose lifecycle:** try-with-resources for methods; ItemStream for readers/writers; listeners or cleanup Steps for Step/Job scope.
4. **Register streams:** ensure custom ItemStreams and delegates are managed by the Step.
5. **Handle open failures:** self-close partially opened resources.
6. **Separate transactions:** understand which resources participate in rollback and which require separate cleanup.
7. **Protect output:** use staging, quarantine, and publish after completion.
8. **Design idempotent cleanup:** repeated operations must not corrupt data or release the wrong owner.
9. **Guard against abrupt failures:** use lease TTLs, graceful shutdown, and recovery scanners.
10. **Monitor:** log open/close/cleanup events and resource metrics.
11. **Test:** exceptions in reader, processor, writer, open failures, cleanup failures, and process recovery.

## 28. Key takeaways

- Resources must be released when a Step or Job fails under the normal lifecycle.
- ItemStream provides open, update, and close for stateful readers/writers.
- Spring Batch manages streams registered with the Step; custom delegates must be forwarded or explicitly registered.
- close releases handles; it is not synonymous with rolling back transactions or deleting files.
- Transaction rollback only undoes resources participating in the transaction.
- Use try-with-resources for resources scoped to a single method or execute call.
- Use ItemStream for resources spanning the Step lifecycle that require checkpoints.
- Use listeners or cleanup Steps for work depending on Step/Job status.
- If open() fails midway, initialization code must close already-opened resources itself.
- Do not place mandatory business publishing in afterJob; use a separate Step so JobRepository tracks and restarts it.
- Incomplete output files should stay in staging and be published only after the workflow succeeds.
- Locks and leases need owner IDs, TTLs, and recovery because process crashes can bypass close callbacks.
- Do not close shared clients, executors, or connections owned by another component.
- Message acknowledgments must coordinate with transactions and commits.
- Test both close callbacks and actual resource state after exceptions.

Properly closing resources allows Jobs to fail without leaving file handles, cursors, connections, or leases held indefinitely. By clearly separating rollback, close, and cleanup, and designing recovery for abrupt process termination, Spring Batch can safely release resources and reliably support subsequent runs.


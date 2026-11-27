# Closing Files, Connections, and Resources After Processing

In **Spring Cloud Task**, an application is launched to perform a **finite-duration** job and then terminate: importing a file, generating a report, cleaning up data, or synchronizing with another system. A true completion point is not merely "finished processing the last record." The application must also release files, connections, execution threads, and temporary resources; record the execution outcome; and return a reliable status to the orchestrator.

This lesson belongs to the **Processing Flow** chapter and focuses on **closing files, connections, and resources after processing**. This is the foundation that enables a Spring Cloud Task to run repeatedly on a schedule or on demand without exhausting connections, leaking file descriptors, leaving partial outputs, or hanging because the process fails to exit. The examples use Java, Spring Boot, Spring JDBC, and typical operational configurations; exact implementation details may vary across Spring Boot and Spring Cloud Task versions.

## 1. Why Must Task Termination Include Resource Release?

Suppose a data import task runs every 15 minutes. Each run reads a file, uses database connections, and spawns several processing threads. If the application finishes business logic **without closing resources**, the following can occur:

- **Unclosed files:** the OS holds open file descriptors; temporary files cannot be deleted or moved, which is especially noticeable on Windows.
- **Database connections not returned to the pool:** concurrent runs starve for connections, block until timeout, or fail even though the database is healthy.
- **Unconsumed/unclosed HTTP responses:** network connections cannot be reused, open sockets grow, and subsequent calls slow down.
- **Executor with non-daemon threads:** business work finishes yet the JVM stays alive, making the launcher think the task is still running.
- **Partially written output files:** consumers read a report missing rows even though report generation failed.
- **Abrupt task termination:** external state and metadata may not reflect the same point in time.

Spring Cloud Task's **TaskRepository** tracks **TaskExecution** (such as start time, end time, exit code, and error message), but it does not automatically close every resource created by application code. Resource lifecycle management is a shared responsibility across Java code, Spring Framework, data access libraries, and the runtime environment.

### Overall Flow

~~~mermaid
flowchart TD
    A["Orchestrator launches application"] --> B["Initialize Spring Context and TaskExecution"]
    B --> C["Receive and validate parameters"]
    C --> D["Open resources within required scope"]
    D --> E["Read / process / write results"]
    E --> F{"Processing outcome?"}
    F -- "Success" --> G["Commit data and publish output"]
    F -- "Error" --> H["Roll back within transaction scope, preserve error details"]
    G --> I["Close resources according to ownership"]
    H --> I
    I --> J["Complete Task lifecycle and close ApplicationContext"]
    J --> K["Process exits; launcher receives status"]
~~~

The diagram illustrates **logical responsibilities**, not an absolute internal order of every Spring callback. Some resources close upon leaving a processing block; some beans close when `ApplicationContext` shuts down. Crucially, resources still required to record the final `TaskRepository` status must remain managed by Spring until the appropriate end of the lifecycle.

## 2. Classifying Resources and Determining Who Is Responsible for Closing Them

There is no single close command for all resources. Before writing a task, identify **where a resource is created, who owns it, and when it is no longer needed**.

| Resource | Common Creation | Appropriate Closing Strategy | Common Mistake |
| --- | --- | --- | --- |
| Input file | **Files.newBufferedReader**, **Files.newInputStream**, **ZipFile** | **try-with-resources** directly in the read scope | Forgetting to close when an exception occurs |
| Output file | **Files.newBufferedWriter**, **Files.newOutputStream** | Close/flush before publishing the finished file | Publishing the file before writing finishes |
| Directory stream | **Files.lines**, **Files.list**, **Files.walk** | Close **Stream** after traversal | Assuming a terminal operation automatically closes the file |
| Direct JDBC | **DataSource.getConnection** outside a Spring transaction | **try-with-resources** for Connection, Statement, ResultSet | Failing to return Connection to the pool |
| Spring-managed JDBC | **JdbcTemplate**, **@Transactional** | Let **JdbcTemplate** and the transaction manager manage Connections | Manually closing a Connection bound to a transaction |
| HTTP request/response | Client using a reusable connection pool | Close **response body/response handle** per library API | Failing to release response on HTTP error statuses |
| Shared pools, clients | Spring-configured beans | Let Spring execute lifecycle/destroy when closing context | Closing a singleton mid-task |
| Executor, thread pool | Bean or application-created | Wait for tasks to complete; shut down owned executors | Launching "fire-and-forget" work and ending the Task |
| Temp files, work directories | **Files.createTempFile** or work directory | Delete unpublished files after failure; maintain stale-file cleanup policy | Corrupted files accumulate after each retry |
| Distributed locks/leases | Lock table, Redis, orchestrator | Release lease when possible; enforce TTL and recovery logic | Assuming a `finally` block always executes |

Two concepts must be kept distinct:

1. **Operation-scoped local resources:** such as a `BufferedReader` reading one file. The code that opens it should close it, typically via `try-with-resources`.
2. **Long-lived Spring-managed resources:** such as `HikariDataSource`, HTTP clients configured as beans, and shared executors. Spring is responsible for closing them when `ApplicationContext` stops; business code should not close them prematurely.

Calling **Connection.close()** on a pooled connection usually means **returning the connection to the pool**, not necessarily closing the physical socket. You must still invoke the proper release operation, without closing the entire `DataSource` shared by other components.

## 3. Managing Input Files with try-with-resources

Java provides **try-with-resources** to invoke **close()** automatically on **AutoCloseable** objects upon exiting the block, whether normally or via exception. This is the default choice for `BufferedReader`, `InputStream`, `OutputStream`, `ZipFile`, and similar resources.

### Example: reading a file of order IDs

Suppose the input is a UTF-8 file where **each line holds a single order ID**. The task reads 250 IDs per batch and writes them to the database. This format is intentionally kept simple to focus on resource management; for CSV files with commas, quotes, or embedded newlines, use a proper CSV parser.

~~~java
@Component
public class ImportRunner implements ApplicationRunner {

    private static final int CHUNK_SIZE = 250;
    private final ImportBatchService importService;

    public ImportRunner(ImportBatchService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        List<String> options = args.getOptionValues("input");
        if (options == null || options.size() != 1
                || options.get(0).isBlank()) {
            throw new IllegalArgumentException(
                "Expected exactly one --input=/path/to/file");
        }

        Path input = Path.of(options.get(0));
        List<String> chunk = new ArrayList<>(CHUNK_SIZE);

        try (BufferedReader reader =
                 Files.newBufferedReader(input, StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }

                chunk.add(line.trim());
                if (chunk.size() == CHUNK_SIZE) {
                    importService.upsertChunk(List.copyOf(chunk));
                    chunk.clear();
                }
            }

            if (!chunk.isEmpty()) {
                importService.upsertChunk(List.copyOf(chunk));
            }
        }
    }
}
~~~

**Points to observe:**

- `BufferedReader` exists only within the scope of reading one file; code does not need to remember to close it across every `if` or `catch` branch.
- If **upsertChunk** throws an exception, `BufferedReader` is still closed and the exception continues propagating so Spring Boot detects the failure.
- Each chunk is delegated to a separate service, establishing sensible **transaction boundaries** rather than holding one massive transaction open throughout file reading.
- When there is no data, the task still closes the file cleanly. Whether an empty file counts as success or failure is a **separate business rule** that must be defined upfront.

For **Files.lines(path)**, **Files.list(dir)**, or **Files.walk(dir)**, the `Stream` object must also be closed because it can hold OS resources:

~~~java
try (Stream<String> lines =
         Files.lines(inputPath, StandardCharsets.UTF_8)) {

    long validCount = lines
            .filter(line -> !line.isBlank())
            .count();

    System.out.println("Valid records: " + validCount);
}
~~~

Calling **count()** only terminates traversal; it does not replace **close()**. Never return a file-backed `Stream` outside the scope where its underlying resource is closed.

### What If an Error Occurs While Closing the File?

`try-with-resources` preserves the primary exception from the main body and generally attaches exceptions thrown in **close()** as **suppressed exceptions**. When diagnosing complex I/O failures, do not read only the top-level message: inspect both the root cause and suppressed exceptions in logs. If `close` fails after preceding processing succeeded, the close exception can fail the entire run; this is a signal that warrants investigation, especially when output may not have flushed completely.

## 4. Output Files: Close Completely Before Publishing

Importing files and exporting reports have different requirements. Input files are only read; **output files must avoid exposing partially written contents**.

For example, suppose a report must be created at **report-2026-11-24.csv**. Writing directly to the path users download from risks another application reading an incomplete file with only a few lines. A common pattern is:

1. Create a **temporary file in the same directory/filesystem** as the target file.
2. Write content to the temp file using `try-with-resources`; leaving the block closes the writer.
3. Verify required checks (line count, checksum, format).
4. Transition from the temp file to the official name using an operation appropriate for the storage system.
5. If an error occurs before publishing, delete the temp file or record it for cleanup.

Example using a filesystem that supports atomic moves:

~~~java
public void publishReport(Path outputDir, String reportText)
        throws IOException {

    Path destination = outputDir.resolve("report-2026-11-24.csv");
    Path temporary = Files.createTempFile(
            outputDir, ".report-", ".partial");

    try {
        try (BufferedWriter writer = Files.newBufferedWriter(
                temporary, StandardCharsets.UTF_8)) {
            writer.write(reportText);
        }

        // Rename only after the writer has closed successfully.
        Files.move(temporary, destination,
                   StandardCopyOption.ATOMIC_MOVE);

    } catch (IOException | RuntimeException error) {
        try {
            Files.deleteIfExists(temporary);
        } catch (IOException cleanupError) {
            error.addSuppressed(cleanupError);
        }
        throw error;
    }
}
~~~

**Limitations of the example:** `ATOMIC_MOVE` is not supported by every filesystem; when unsupported, it can throw **AtomicMoveNotSupportedException**. The path in the code is illustrative and should be determined by the actual **report key/version**. Do not rely solely on rename to prevent two processes from publishing the same report simultaneously; deduplication must rely on business keys, naming conventions, versioning, or database constraints. An atomic move also does not guarantee data is durably synced to disk; strict durability requirements need `fsync` workflows and appropriate filesystem guarantees.

For **object storage**, you cannot assume local-filesystem rename semantics. Typically you upload the complete object, verify its checksum/ETag per convention, and then update a **READY** status record or pointer to the finalized object. If upload or status update fails, reruns must detect and clean up orphaned objects.

## 5. Database Connections: Direct JDBC vs. Spring-Managed

Spring Cloud Task uses **TaskRepository** to store execution metadata in a database; the same application may use a different database or the same database to store business data. These two needs can use appropriately configured `DataSource`s. Avoid closing metadata resources before the Task lifecycle finishes.

### 5.1. When Acquiring a Connection Manually via JDBC

If code is **not inside a Spring-managed transaction** and calls **DataSource.getConnection()** directly, return the Connection to the pool with `try-with-resources`:

~~~java
public long countPending(DataSource dataSource) throws SQLException {
    String sql = "SELECT COUNT(*) FROM import_queue WHERE status = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setString(1, "PENDING");

        try (ResultSet resultSet = statement.executeQuery()) {
            resultSet.next();
            return resultSet.getLong(1);
        }
    }
}
~~~

Objects are closed in reverse order of opening: `ResultSet`, `PreparedStatement`, then `Connection`. If an error occurs at any step, already-opened resources are still released.

If you obtain a Connection through **DataSourceUtils.getConnection(...)** participating in a Spring-managed transaction, use Spring's corresponding release mechanism and **do not call close() out of habit**. Better yet, when logic has no special requirements, use **JdbcTemplate** or a Spring data-access abstraction.

### 5.2. When Using JdbcTemplate and @Transactional

Writing a batch from the earlier section can be implemented as follows:

~~~java
@Service
public class ImportBatchService {

    private final JdbcTemplate jdbcTemplate;

    public ImportBatchService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void upsertChunk(List<String> externalIds) {
        jdbcTemplate.batchUpdate(
            "INSERT INTO imported_key (external_id) VALUES (?) "
            + "ON CONFLICT (external_id) DO NOTHING",
            externalIds,
            externalIds.size(),
            (statement, id) -> statement.setString(1, id)
        );
    }
}
~~~

In this example:

- **JdbcTemplate** manages borrowing and releasing JDBC resources within the scope of the call.
- **Transaction manager** manages the transaction of **upsertChunk**; it commits when the method completes or rolls back on errors configured as rollback triggers.
- Because the runner calls **another Spring service** through a proxy, the **@Transactional** annotation takes effect via standard proxy mechanics. Calling another `@Transactional` method on **this** inside the same bean may bypass the proxy.
- The **ON CONFLICT** clause in the example targets PostgreSQL; other database engines use their respective upsert syntax.

**Never close a Connection inside a `@Transactional` method** if the Connection is owned by the transaction manager. Closing it manually can break the active transaction or cause hard-to-trace errors.

### 5.3. Transaction Boundaries and Closing Timing

Do not open one massive transaction and hold a connection while calling slow APIs, reading gigabytes of files, and waiting on worker threads. That easily starves the connection pool, holds locks too long, and rolls back huge amounts of work on error. For batch imports, it is usually best to:

- Read a group of records from the file.
- Pass that group to a service executing a short transaction.
- Commit the group successfully before moving to the next group.
- Persist checkpoints, business keys, or source status to support post-failure reruns.

**Committing a transaction** and **closing a Connection** are not necessarily the same operation. With a pool, a Connection is typically returned to the pool after the transaction or query finishes; the pool itself remains alive to serve other components in `ApplicationContext`.

## 6. Long-Lived Resources Belonging to ApplicationContext

A Spring Boot application may instantiate beans such as **DataSource**, **WebClient/HTTP client**, **Executor**, message producers, object-storage clients, or cache clients. When shared across services, register them as **Spring beans** with an appropriate destruction mechanism.

Example of a custom client with a **close()** method:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

This is an example of a **hypothetical client type**: `ExternalClient` must actually expose an appropriate `close()` method. For real libraries, check that client's lifecycle contract, especially when it manages its own connection pool. Spring also supports bean destruction callbacks such as **@PreDestroy**, **DisposableBean**, or **destroyMethod**.

Resources auto-configured by Spring Boot, such as a standard `DataSource` connection pool, typically already have a matching lifecycle. **Do not manually close the DataSource at the end of ApplicationRunner**: Spring Cloud Task may still need access to `TaskRepository` to record the final outcome and shut down `ApplicationContext` properly.

### A `main` Pattern for Process-Style Tasks

~~~java
@SpringBootApplication
@EnableTask
public class FileImportTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(FileImportTaskApplication.class, args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
~~~

Here **SpringApplication.exit(context)** triggers the `ApplicationContext` shutdown sequence and computes the exit code via configured **ExitCodeGenerator** beans; **System.exit** terminates the JVM with that code. For CLI/batch apps, this prevents contexts and threads from lingering indefinitely. If an error occurs inside **SpringApplication.run(...)**, subsequent statements do not necessarily execute; Spring Boot's startup failure reporting must be handled appropriately. In tests, test the runner/service directly rather than invoking **System.exit**.

**Note:** do not call `SpringApplication.exit()` **inside individual business services**; close the context only after all required work has been awaited and verified. If a `@PreDestroy` callback on one bean needs another bean's resources, avoid relying on incidental ordering; declare bean dependencies explicitly and align shutdown with Spring's lifecycle.

## 7. Do Not Let the Task Finish While Asynchronous Work Is Still Running

A subtle bug occurs when a runner starts background work without waiting:

~~~java
// Wrong example of task lifecycle
@Override
public void run(ApplicationArguments args) {
    executor.execute(() -> importService.importAll());
    // run() exits before importAll() finishes.
}
~~~

Once the runner returns, Spring Cloud Task may record the primary execution as finished while side effects continue running or get cut short by shutdown. Success logs and `TaskExecution` status are no longer trustworthy.

### Waiting for All Child Tasks and Detecting Errors

~~~java
@Override
public void run(ApplicationArguments args) {
    CompletableFuture<Void> first =
        CompletableFuture.runAsync(
            () -> importService.importPartition("A"), executor);

    CompletableFuture<Void> second =
        CompletableFuture.runAsync(
            () -> importService.importPartition("B"), executor);

    // If any branch fails, join() throws CompletionException.
    CompletableFuture.allOf(first, second).join();
}
~~~

You can register a Spring-managed executor:

~~~java
@Bean
public ThreadPoolTaskExecutor processingExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("task-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(60);
    return executor;
}
~~~

The two safeguards serve different purposes: **allOf(...).join()** keeps the runner waiting until work truly finishes and propagates errors; **executor shutdown policy** acts as a fallback when the context must close. Do not treat a 60-second shutdown wait as sufficient proof that business work succeeded.

Thread-bound transactions normally **do not propagate automatically** onto executor threads. Each processing branch needs its own transaction boundary at the service invoked on that thread. Likewise, logging/MDC context or security context needs explicit context-propagation if business rules require it.

If you create an **ExecutorService** outside Spring, the code creating it must include a proper shutdown path (shutdown, bounded `awaitTermination`, then handling unfinished tasks). Never assume the JVM automatically cleans up worker threads the moment the runner returns.

## 8. HTTP, Messaging, Locks, and Out-of-Process Resources

### 8.1. HTTP Clients and Responses

In a data-sync task, an HTTP client may use a reusable connection pool. Practical rules:

- Configure **connect timeout**, **response/read timeout**, and retry limits so the task never blocks indefinitely.
- Close or consume responses per the library's contract, **including HTTP 4xx/5xx**; avoid leaking sockets by ignoring error bodies.
- If the client is configured as a shared bean, keep it alive until context shutdown.
- Guard retries with business/idempotency keys because a closed or timed-out network connection does not tell you whether the remote server processed the request.

For example, a request might time out **after** the partner service already persisted data. Retrying based solely on `TaskExecution` ID can create duplicate partner records. That is why separate request keys and status-check policies before retrying are essential.

### 8.2. Message Brokers and Acknowledgments

A task that reads messages and writes to a database must define the order **process → commit → acknowledgment** per broker and client semantics. Acking too early risks losing messages if the task crashes; acking after commit means messages may be redelivered on crash, so consumers must handle duplicates safely. Use transactions, outboxes, or idempotent consumers as required rather than relying only on `close()`.

Before closing a producer, you may need to **flush** asynchronously buffered messages and await delivery confirmation. Flushing only satisfies library and broker semantics; it does not replace verifying business outcomes.

### 8.3. Distributed Locks and Leases

Maintenance tasks often use locks to prevent two instances from cleaning the same data. The happy path is **releasing the lock in `finally`**; however, if the process is killed or a node loses power, `finally` never runs. Therefore, locks need a **TTL/lease**, lease renewal for long tasks, and ownership checks on release. A takeover task must inspect processed data and checkpoints rather than assuming the prior run rolled back cleanly.

## 9. Handling Errors While Releasing Resources

A task must preserve **the original root cause**. If main processing fails and cleanup subsequently fails as well, never accidentally overwrite the primary exception with the cleanup exception.

For `AutoCloseable`, prefer **try-with-resources** because Java manages suppressed exceptions automatically. For auxiliary resources where that does not apply, use `finally` and attach supplementary errors:

~~~java
Exception primary = null;

try {
    performWork();
} catch (Exception error) {
    primary = error;
    throw error;
} finally {
    try {
        deleteTemporaryScratchFiles();
    } catch (Exception cleanupError) {
        if (primary != null) {
            primary.addSuppressed(cleanupError);
        } else {
            throw cleanupError;
        }
    }
}
~~~

This snippet illustrates the principle for standard **Exception**s; production code must also consider cleanup rules under **Error**, thread interruption, and whether cleanup failure itself should fail the task. If cleanup is mandatory (for instance, flushing/closing output completely to guarantee integrity), cleanup failures must surface as task failure. If it only deletes scratch files that can be swept later, you can log and enqueue a compensating cleanup, while avoiding silently hiding accumulating debris.

Establish **clear classification rules**:

| State | Example | Handling |
| --- | --- | --- |
| Fully completed | Results committed, output closed, reconciliation passed | Report success to launcher |
| Business error | Malformed input data, missing required key | Do not mark successful; surface cause to fix input |
| Transient error | Lost DB or external service connectivity | Roll back uncommitted work; return error for bounded retry |
| Resource-close error | Writer flush failed, HTTP response failed to close | Do not silently ignore; evaluate impact on correctness |
| Abnormal death | SIGKILL, power loss, container OOM | Do not rely on `finally`/`@PreDestroy`; recover via metadata, locks, and idempotency |

**Never** catch all exceptions only to log and return normally. Doing so makes the process and metadata appear successful even though work was left incomplete. For errors representing task failure, let the exception reach the failure-reporting mechanism or return a failure exit code via the application's standard flow.

## 10. Controlled Shutdown in Containers and Scheduled Runs

When a task runs inside a Kubernetes Job/CronJob or another orchestrator, the process may receive a stop signal due to deadlines, redeployments, or operator intervention. Typical stages include:

1. **SIGTERM** requests the process to stop; if the JVM and launcher receive the signal properly, shutdown hooks get a chance to run.
2. The application stops accepting new work, waits within reasonable limits for in-flight operations, and closes beans and resources.
3. If the grace period expires or **SIGKILL** arrives, the process stops immediately; Java cannot guarantee executing any `finally`, `@PreDestroy`, or listener.

Example Job pod configuration:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: one-off-import
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 90
      containers:
        - name: import-task
          image: registry.example/import-task:1.0.0
          args:
            - "--input=/data/orders.txt"
~~~

**terminationGracePeriodSeconds** is how long Kubernetes waits for graceful exit before forcibly killing the container; its real value should reflect the task's transactions, batch size, and resource close duration. Setting it too short increases partial runs; setting it too long delays cluster resource reclamation. This is only an illustrative manifest: volumes, secrets, resource limits, runtime modes, and permissions must be added per environment.

For long-running tasks, also include:

- Process-level and per-I/O-call **timeouts**.
- **Checkpoints** or business keys to resume after interruption.
- **Retry limits** and backoff to avoid connection storms or duplicate writes.
- **Per-execution temp filenames**; cleanup policies for orphaned files based on age and ownership.
- **Status observability** in both `TaskRepository` and the orchestrator; if `START_TIME` exists without `END_TIME`, verify whether the process is still alive or died abnormally.

### Do Not Shut Down the Metadata Source Too Early

Spring Cloud Task needs access to **TaskRepository** to record lifecycle events. If application code closes the metadata database pool right after finishing business data, final status recording can fail. Let Spring close the `DataSource` during `ApplicationContext` destruction. Task completion callbacks or shutdown hooks are for notification and supplementary cleanup, not replacements for core resource lifecycle management.

## 11. Design Patterns for Three Common Task Types

| Task Type | Primary Resources | Critical Close Points | Rerun Rules |
| --- | --- | --- | --- |
| **Data import** | Reader, parser, JDBC connection, temp files | Close reader even when a batch fails; commit transactions per chunk | Source locks and record keys prevent duplicate imports |
| **Reporting** | ResultSet/data stream, BufferedWriter, object-storage client | Close writer before publishing; never expose partial files | Report keys, versions, checksums; avoid duplicate notifications |
| **Maintenance** | JDBC connection, cursor, lock/lease | Short transactions, closed cursors, ownership-checked lease release | Process only records still matching cutoff or checkpoint |

### Real Failure Scenario: Importing 10,000 Records, Crashing on Batch 31

Suppose each transaction writes 250 records. After 30 batches succeed, the process crashes mid-batch 31. Committed batches remain in the database, the uncommitted batch rolls back, and `TaskExecution` metadata may not have updated `END_TIME`. To operate safely:

- The source file or data feed must remain accessible on rerun.
- Each record has a unique business key or an appropriate upsert mechanism.
- Data is reconciled by record count and source identifier; never equate "read entire file" with "persisted successfully."
- Readers, transactions, and executors have clear ownership scopes so the next run does not depend on resources from the dead process.
- If using Spring Batch, checkpoints/`JobRepository` support step/chunk restarts; idempotency is still required for side effects outside the transaction.

Here, **closing resources** supports clean execution, while **safe recovery** also depends on transactions and business state design. No `finally` block alone guarantees recovery after `SIGKILL`.

## 12. Observing and Diagnosing Resource Leaks

A run that succeeds functionally can still leave resource issues behind for subsequent runs. To diagnose root causes, log at least **task execution ID, business key, operation type, record count, duration, status, and errors**; avoid logging passwords, tokens, or sensitive data.

| Symptom | Possible Cause | Where to Investigate |
| --- | --- | --- |
| Task finishes but JVM does not exit | Custom thread pool not shut down, non-daemon threads alive | Thread dumps, bean/executor list, thread creation sites |
| Task waits excessively for DB connections | Connection leak, long transactions, undersized pool | Pool active/idle/waiting metrics, timeouts, transaction history |
| Unable to rename or delete files | Reader, writer, or file stream still open | Inspect all error branches and `try-with-resources` blocks |
| Downloaded report is truncated | Published before closing writer or concurrent file overwrite | Close → validate → publish order, versioning scheme |
| `TaskExecution` missing `END_TIME` | Process still running or killed before final write | Cross-check pod/process status and logs; enforce timeout policy |
| Many leftover `.partial` files | Cleanup skipped when process died | Age-based temp file sweep; check owning tasks |
| Logs say success yet data is missing | Exception caught and ignored, or async futures not awaited | Inspect error-handling branches, future joins, and business reconciliation |

For scheduled tasks, monitor trends in connection counts, thread counts, file descriptors, and temp directory usage across runs. Especially when multiple instances share a pool or storage backend, inspect metrics per instance and per run to distinguish true leaks from legitimate load growth.

## 13. Verification Lab

Build a Spring Cloud Task that imports a file of 1,000 order IDs, writing in chunks to PostgreSQL. Use **ApplicationRunner**, **try-with-resources**, **JdbcTemplate**, **@Transactional** on a dedicated service, and `TaskRepository` to observe each run.

Execute these scenarios in order:

1. **Normal run:** file is read and closed; process exits; record count matches; corresponding execution record exists.
2. **Missing file:** opening `BufferedReader` fails; task returns a clear error and produces no false success.
3. **Mid-run failure:** intentionally corrupt one line between chunks; verify the failed chunk's transaction rolls back while earlier chunks stay consistent; rerunning writes no duplicates.
4. **File held open:** simulate a code path that forgets to close the stream, and compare against `try-with-resources` via file descriptor state or OS ability to rename/delete the file.
5. **Asynchronous processing:** test without awaiting the Future, then add **CompletableFuture.allOf(...).join()**; compare when task status updates against when data writes finish.
6. **Mid-run termination:** send a graceful stop signal and compare against forced termination; inspect `TaskRepository`, logs, committed data, and the rerun plan.

**Acceptance criteria:** every run reports success/failure matching actual data; local resources close on both success and failure paths; the application does not hang after finishing; reruns neither create duplicate records nor publish incomplete files.

## 14. Pre-Production Checklist

| Question | Completion Criterion |
| --- | --- |
| Are all resources opened by the task inventoried? | Clear owner and close timing known for every resource |
| Are all InputStreams, Readers, Writers, and ResultSets/cursors released? | `try-with-resources` or equivalent lifecycle management |
| Are Connections properly returned to the pool? | Spring manages transactions/connections or JDBC code scopes `close` properly |
| Are output files published only after closing? | Temp files, validation checks, and controlled publishing |
| Does the task await all async processing? | No unchecked futures remain when the runner exits |
| Are appropriate timeouts and shutdown configured? | Task can stop cleanly within normal operational windows |
| Are kills without `finally` handled? | Checkpoints, idempotency, TTL/leases, compensating cleanup |
| Is `TaskRepository` metadata persisted through lifecycle end? | Metadata pool/beans are not manually closed too early |
| Can resource-closing errors be diagnosed? | Primary cause, suppressed exceptions, metrics, and required logs captured |

### Key Takeaway

In Spring Cloud Task, **finishing the work** and **terminating the process** must be designed together. Local resources should be closed in the narrowest possible scope via `try-with-resources`; Spring-managed connections and beans should be left for Spring to close during its lifecycle; asynchronous steps must finish or fail explicitly before the task reports an outcome. When combined with **TaskRepository, runtime arguments, error handling, schedules, and Spring Batch**, proper resource release makes every finite execution genuinely reliable and safe to rerun.

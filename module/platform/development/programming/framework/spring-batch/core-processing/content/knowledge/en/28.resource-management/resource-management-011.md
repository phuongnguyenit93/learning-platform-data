# Testing for Resource Leaks in Spring Batch

Spring Batch often runs jobs for extended periods, processes many chunks, and may retry or restart after failures. Each step can open database cursors, connections, file streams, sockets, HTTP responses, temporary files, or threads. If resources are not released on time, a single run might still succeed while subsequent runs gradually exhaust connection pools, file descriptors, threads, or memory.

Testing for resource leaks must verify that resources are closed on both success paths and failure paths. Checking only that JobExecution is COMPLETED is not enough; inspect ItemStream lifecycles, resource ownership, active resource counts, and the ability to run repeatedly without steadily growing held resources.

## 1. What is a resource leak?

A resource leak occurs when an application acquires or creates a resource without releasing it once it is no longer needed. In batch processing, this bug often does not surface immediately in a short run. It can accumulate across many chunks, partitions, or job runs.

| Resource | Leak Symptom | Potential Impact |
| --- | --- | --- |
| JDBC connection | Borrowed connection count rises and never returns to baseline | Connection pool exhaustion, jobs waiting or timing out |
| Statement/ResultSet/cursor | Cursor or statement remains open after step ends | Held connections, locks, or server-side resources |
| File stream/channel | File cannot be renamed/deleted or descriptor count grows | File descriptor exhaustion, locked files |
| HTTP response/body/socket | Response body is not closed | Exhausted HTTP client connections, dangling sockets |
| Temporary file | Intermediate files remain after job finishes | Disk consumption, temporary data exposure, full filesystem |
| Thread/executor | Worker threads stay alive after owner terminates | Stack/CPU consumption, retained classloaders and beans |
| Lock/buffer | Locks or large objects held longer than needed | Deadlocks, heap growth, or cross-execution data bleed |

Not every resource remaining after a step is a leak. A staging file may be retained intentionally for restarts; a thread pool may be a shared singleton shut down only when ApplicationContext closes. Tests must reflect designed ownership and lifecycles.

## 2. Identifying who owns a resource

Before writing tests, identify which component opens a resource and which component must close it. The basic rule is that the component opening a resource is responsible for releasing it, unless ownership is explicitly transferred.

| Where Resource Is Opened | Typically Suitable Management |
| --- | --- |
| Spring Batch reader/writer | ItemStream.open() and ItemStream.close() |
| A Java method | try-with-resources or finally |
| JDBC via JdbcTemplate/repository | Let Spring manage statements, result sets, and connections per transaction |
| Connection obtained via DataSourceUtils | Release using DataSourceUtils.releaseConnection() |
| HTTP response/body | Close response/body via try-with-resources or client's corresponding API |
| Shared executor | Register bean with Spring lifecycle; shut down when application context closes |
| Staging file | Manage per execution ID and retention/restart policy |

Do not close a connection managed by the transaction manager by calling connection.close() arbitrarily. If obtaining a connection via DataSourceUtils, use its matching release API. When using JdbcTemplate or Spring Data repositories, let the framework manage JDBC resource lifecycles.

A resource may be held across multiple chunks, such as a cursor reader. In that case, do not close it after every chunk; close it when the step ends according to the reader's lifecycle contract.

## 3. ItemStream lifecycle: open, update, and close

Spring Batch uses ItemStream to manage reader/writer resources and state:

- open(ExecutionContext): opens the resource and restores necessary state before processing.
- update(ExecutionContext): saves checkpoints or required state at chunk boundaries.
- close(): releases the resource when the step finishes.

A reader managing its own file can implement ItemStreamReader:

~~~java
public class TrackingFileReader implements ItemStreamReader<String> {

    private final Path input;
    private final ResourceProbe probe;
    private BufferedReader reader;

    public TrackingFileReader(Path input, ResourceProbe probe) {
        this.input = input;
        this.probe = probe;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        try {
            reader = Files.newBufferedReader(input);
            probe.opened();
        } catch (IOException ex) {
            closeAfterOpenFailure();
            throw new ItemStreamException("Cannot open " + input, ex);
        }
    }

    @Override
    public String read() throws Exception {
        return reader == null ? null : reader.readLine();
    }

    @Override
    public void update(ExecutionContext context) {
        // Save read position/checkpoint here if the reader supports restart.
    }

    @Override
    public void close() throws ItemStreamException {
        if (reader == null) {
            return;
        }

        try {
            reader.close();
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot close " + input, ex);
        } finally {
            reader = null;
            probe.closed();
        }
    }

    private void closeAfterOpenFailure() {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException ignored) {
                // Keep the resource-open exception as the primary cause.
            } finally {
                reader = null;
            }
        }
    }
}
~~~

This example focuses on lifecycle; production readers must save and restore read positions if restart is needed. close() should be idempotent: calling it multiple times must not double-close or fail because the resource is already released. If open() opens some resources and then fails, open() itself must clean up what was already opened; do not assume the framework always calls close() after a partial open() failure.

Spring Batch manages the lifecycle of ItemStreams registered with the step. When the step ends under normal lifecycle, the framework invokes close on open streams. No Java callback is guaranteed to run if a process is killed with kill -9, the JVM crashes, or the machine loses power; for those cases, design resources so the OS can reclaim them and provide cleanup tasks for leftover artifacts.

## 4. Ensuring ItemStreams are registered with the step

When a reader or writer is configured directly on the step and implements ItemStream, Spring Batch can register its lifecycle via the builder. However, if a custom wrapper only implements ItemReader/ItemWriter and holds an ItemStream delegate inside, the framework may not see the delegate.

Example wrapper that does not expose ItemStream itself:

~~~java
public class LoggingReader<T> implements ItemReader<T> {

    private final ItemStreamReader<T> delegate;

    public LoggingReader(ItemStreamReader<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public T read() throws Exception {
        return delegate.read();
    }
}
~~~

When the wrapper does not forward open, update, and close, register the delegate as a stream on the step:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(loggingReader)
    .stream(delegateReader)
    .writer(writer)
    .build();
~~~

Another option is having the wrapper implement ItemStreamReader itself and forward all three callbacks to the delegate. What matters is that every resource-owning delegate participates in the step lifecycle. Missing stream registration is a common reason close() is not called as expected.

## 5. Testing that readers/writers close resources after step success

A useful test checks not only that the reader returns the right data, but also observes open() and close(). A small probe can be used in tests to count opens/closes and active resources:

~~~java
public class ResourceProbe {

    private final AtomicInteger opened = new AtomicInteger();
    private final AtomicInteger closed = new AtomicInteger();

    public void opened() {
        opened.incrementAndGet();
    }

    public void closed() {
        closed.incrementAndGet();
    }

    public int openCount() {
        return opened.get();
    }

    public int closeCount() {
        return closed.get();
    }

    public int activeCount() {
        return openCount() - closeCount();
    }
}
~~~

After a successful job run:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(probe.openCount()).isEqualTo(1);
assertThat(probe.closeCount()).isEqualTo(1);
assertThat(probe.activeCount()).isZero();
~~~

The fixture must ensure the reader is created for the right step execution and the probe is a shared test object for observation. If the reader runs across multiple executions or partitions, open/close counts will differ from one; assertions should then check that active resources equal zero and close count matches successful open count.

## 6. Testing cleanup when a step fails

Leaks often appear on error paths because code exits early before closing resources. Create an integration test where the reader opens a stream and then the writer intentionally throws an exception:

~~~java
public class FailingOrderWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        throw new IllegalStateException("Simulated writer failure");
    }
}
~~~

Test:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(probe.openCount()).isEqualTo(probe.closeCount());
assertThat(probe.activeCount()).isZero();
~~~

With a fixture that successfully opens a stream before the writer fails, the test confirms the resource is closed even when the step ends FAILED. Do not test only processor exceptions; readers/writers can have different lifecycles and errors can arise at different points.

Have separate tests for:

- Errors in the processor after the reader has opened.
- Errors in the writer after the reader has opened.
- Errors while opening the resource.
- Errors inside close() itself.
- Steps stopped or requested to stop.

For errors occurring midway through open(), test open()'s internal cleanup logic because the framework cannot close a stream whose successful open state it never received.

## 7. Testing that readers/writers close exactly once and idempotently

Do not check only that the active count equals zero. An implementation might close the same resource twice, or callbacks might be invoked again when cleanup code is not designed to be idempotent.

For custom readers, verify:

- close() after a successful open releases the resource.
- Calling close() a second time does not raise unexpected errors.
- Fields holding resources are reset to null.
- close() does not delete checkpoints needed for restart.
- Exceptions during closing do not leave resource references retained permanently in the bean.

Example unit test:

~~~java
@Test
void closeIsSafeWhenCalledMoreThanOnce() throws Exception {
    TrackingFileReader reader = new TrackingFileReader(input, probe);
    reader.open(new ExecutionContext());

    reader.close();
    reader.close();

    assertThat(probe.activeCount()).isZero();
}
~~~

This unit test complements lifecycle integration tests. It does not replace verifying that Spring Batch actually calls close() for streams configured in a step.

## 8. Testing for JDBC connection leaks

JDBC resources typically include connections, statements, and result sets. When using JdbcTemplate, Spring Data repositories, or built-in Spring Batch readers/writers, the framework manages most acquire/release operations. Leaks happen more easily in code that calls DataSource.getConnection() directly or manages cursors manually.

Unsafe code:

~~~java
public List<Order> loadOrders(DataSource dataSource) throws SQLException {
    Connection connection = dataSource.getConnection();
    PreparedStatement statement =
        connection.prepareStatement("select id from orders");
    ResultSet resultSet = statement.executeQuery();
    return map(resultSet);
}
~~~

The example above never closes the result set, statement, or connection. Use try-with-resources when the method owns those resources:

~~~java
public List<Order> loadOrders(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement("select id from orders");
         ResultSet resultSet = statement.executeQuery()) {
        return map(resultSet);
    }
}
~~~

If a connection is obtained via DataSourceUtils inside a Spring transaction, release it with DataSourceUtils.releaseConnection() instead of manually closing a connection managed by the transaction manager. With JdbcTemplate, manual connection management is unnecessary.

## 9. Measuring active connections using the connection pool

An integration test can observe the connection pool before and after a job. With HikariCP, HikariPoolMXBean exposes active, idle, and total connection counts:

~~~java
HikariPoolMXBean pool = hikariDataSource.getHikariPoolMXBean();

int activeBefore = pool.getActiveConnections();

JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(pool.getActiveConnections()).isEqualTo(activeBefore);
~~~

This is an illustrative approach; in real tests, establish the baseline after the application context and test fixtures have stabilized. Metadata repository operations, health checks, or background tasks may borrow connections concurrently, so an immediate assertion equal to baseline can be flaky. You can wait within a short timeout for the pool to return to baseline and verify a stable trend.

Do not blindly assert activeConnections == 0 if the pool holds connections legitimately used by tests or external transactions. Isolate the datasource, disable background traffic during tests, or compare against a measured baseline.

Hikari leakDetectionThreshold is a diagnostic tool for connections held longer than a threshold. It logs warnings and stack traces showing where a connection was borrowed; it does not close leaked connections itself and does not replace test assertions.

## 10. Using a DataSource proxy to count acquire/release

When you need to verify precisely whether application code returned connections, wrap the datasource with a proxy/decorator in tests. The proxy records every getConnection() call and every connection close/release.

A test implementation can use datasource-proxy or a Java DataSource/Connection wrapper. Key considerations:

- Track successfully borrowed connections.
- Verify close()/release occurs exactly once.
- Do not confuse pool Connection.close() with closing a physical socket; pools normally return connections to the pool.
- Check connections obtained via getConnection(username, password) as well.
- Ensure the wrapper does not alter the datasource's transaction semantics.

Proxies help catch buggy custom JDBC management code. However, if a proxy only counts close() calls without understanding transaction-bound connections, tests may report false positives. Combine checks with pool metrics and transaction outcomes.

## 11. Testing ResultSet, Statement, and cursors

A connection might be returned to the pool while a statement or cursor remains open, depending on the driver and usage. With custom JDBC code, close resources in reverse order of opening:

~~~text
Connection
  └── PreparedStatement
        └── ResultSet
~~~

Try-with-resources closes result set, statement, then connection. When using JdbcCursorItemReader, let the reader manage the cursor via the ItemStream lifecycle; never manually close connections/statements inside a processor or listener while the reader is still using them.

Useful tests:

- Verify custom mappers/readers close result sets when data ends.
- Verify errors during row mapping still close statements and connections.
- Verify cursor readers close resources after both step success and failure.
- Run multiple times to detect rising counts of open cursors/connections.

If the driver/database exposes session/cursor metrics, use them to inspect leaks in integration environments. Avoid relying on driver-specific session names or counters in generic unit tests.

## 12. Testing file streams and file descriptors

File readers/writers typically hold file handles throughout a step. Use ItemStream.close() to close handles. Tests can use probes to count opens/closes and then attempt filesystem operations on the file:

~~~java
Path moved = tempDirectory.resolve("input-after-step.txt");

Files.move(inputFile, moved);

assertThat(Files.exists(moved)).isTrue();
~~~

On Windows, an open file can often cause move/delete operations to fail depending on how the handle was opened and sharing flags. Therefore, move/delete operations are an additional signal; lifecycle probes remain the primary, less OS-dependent assertion.

For FlatFileItemReader or FlatFileItemWriter, verify:

- Files are closed after the step finishes.
- Step failures also release streams.
- Input files needed for restart are not deleted.
- Output staging files are retained or deleted per policy.
- Repeated runs do not create unbounded handles/temporary files.

Do not confuse an existing file with a resource leak. Retained output files can be valid business results; a leak is an unclosed handle/descriptor or an unowned temporary artifact.

## 13. Testing temporary files and per-execution cleanup

Temporary files should carry names tied to job/step execution or batch IDs so two concurrent jobs do not overwrite each other. Tests should run both success and failure cases, then inspect temporary files against the designed policy.

Example:

~~~java
Path staging = tempDirectory.resolve(
    "orders-" + jobExecutionId + ".tmp"
);

// Step writes staging file.
// Listener publishes only on success.
// Cleanup job handles failed files per retention policy.
~~~

Assertions may include:

- After success, staging is published as the final artifact or deleted if no longer needed.
- After failure, staging may be kept for restart/diagnostics per design.
- Once an execution passes its restart window, the cleanup job deletes old artifacts.
- Running cleanup twice causes no errors and does not delete another execution's artifacts.
- Two concurrent executions do not share the same temporary path.

Do not delete files immediately when a step enters FAILED status if the job can restart from checkpoints and needs those files. Resource handles must close immediately; durable temporary data is deleted under a separate retention policy.

## 14. Testing HTTP responses and network resources

When a processor or writer calls an HTTP API, the response body may hold a socket/connection from the HTTP client. Reading a response and skipping closing the body can gradually exhaust the client's pool.

Example with Java HTTP client returning an InputStream:

~~~java
HttpResponse<InputStream> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream body = response.body()) {
    return parse(body);
}
~~~

With other clients, use the corresponding close/dispose API for responses/bodies. Do not close only when status code is 2xx; error responses also carry bodies and must be released.

In tests, use a mock server or fake client to count closed responses/bodies. Test success, non-2xx, timeouts, and body parse errors. If the client uses a connection pool, monitor leased/available connections via client metrics if the API supports them.

Do not hold response objects in singleton fields after processing an item. Return needed data from the method and close the response immediately on completion.

## 15. Testing thread and executor lifecycles

A step may use a TaskExecutor to run workers or partitions. Distinguish step-owned executors from application-shared executors:

- Shared Spring-bean executors normally live with the ApplicationContext and shut down when the context closes.
- Executors created manually inside a method or per execution must be shut down by their owning component.
- Do not shut down a singleton executor after each step if other steps still use it.
- Do not spawn new threads per item without bounds or termination mechanisms.

With a Spring-managed ThreadPoolTaskExecutor:

~~~java
@Bean
ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setThreadNamePrefix("batch-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    return executor;
}
~~~

Tests can verify after the step finishes that no worker tasks from that execution remain running. When closing ApplicationContext, confirm the executor shuts down and worker threads terminate within the allowed timeout. Do not demand that a shared thread pool shut down immediately after every job.

## 16. Testing with partitioning and multi-threaded steps

Resource leaks are easily masked when running only a single worker. Partitioning can open many readers, cursors, files, or connections simultaneously. Tests should confirm resources close for each partition, even when only one partition fails.

For example, if four partitions each open a file reader:

~~~text
Manager
  |
  +-- Partition 0 -> open reader 0 -> close reader 0
  +-- Partition 1 -> open reader 1 -> close reader 1
  +-- Partition 2 -> open reader 2 -> exception -> close reader 2
  +-- Partition 3 -> open reader 3 -> close reader 3
~~~

Tests must track active resources per partition or in total. After the manager step completes, resources opened by workers must return to zero. If remote workers run in separate processes, measure resources in the worker processes; the manager cannot directly observe file handles or connections on another node via local probes alone.

When using multi-threaded steps, probes must be thread-safe (AtomicInteger, LongAdder, or synchronized collectors). Never use an unsynchronized mutable ArrayList to record lifecycle events from multiple workers.

## 17. Testing restart and resource lifecycles

Restart is a distinct path that must be tested. After a step fails, resources from the old execution must be closed; on restart, the reader/writer opens new resources and restores checkpoints.

A restart test can:

1. Run the job and make the writer fail after a committed chunk.
2. Verify reader/file/database resources from the first run were closed.
3. Relaunch the same JobInstance with matching parameters.
4. Verify the reader reopens the resource and reads from the checkpoint.
5. Verify after the second run, the new resources are also closed.

Do not reuse an already-closed stream for a restart execution. open() must create new resources and use ExecutionContext to restore position. If a reader stores state in fields without writing to context, restart may read from the wrong position even if no resources leak.

For output files, verify FlatFileItemWriter or custom writers apply state/restart policies correctly. An existing file does not imply an open handle; test contents, checkpoints, and close counts together.

## 18. Running repeatedly to detect cumulative leaks

A single test run can miss small leaks. For a short step, run repeatedly inside the same test ApplicationContext and inspect resources after each run:

~~~text
Run 1: active connections = 0
Run 2: active connections = 0
Run 3: active connections = 0
...
Run N: active connections = 0
~~~

If active connections, open file counts, worker threads, or temporary file counts climb after each run, there may be a leak or an incomplete cleanup policy.

Do not run huge loop counts in unit tests. Pick enough iterations to expose a trend, keep fixtures isolated, and avoid turning tests into benchmarks. For time-dependent leaks, use dedicated stress/integration tests and record metrics per iteration.

Compare against a baseline established after the framework, connection pools, and background threads finish initializing. Some pools intentionally retain idle connections or worker threads; total resource count does not necessarily drop to zero. What must stay flat is the count of resources borrowed/held outside expected scopes.

## 19. Using metrics and diagnostic tools

Test assertions are the primary safeguard; metrics and profilers help pinpoint causes when tests or production detect leaks.

Useful observation sources:

- HikariCP/JMX: active, idle, total connections, and pending threads.
- HTTP client metrics: leased, available connections, pending acquires.
- JVM: live thread count, heap usage, direct buffers, and classloaders.
- OS: open file descriptors/handles and sockets.
- Database: sessions, cursors, locks, and connections by application name.
- Java Flight Recorder: socket, file I/O, thread, and allocation events.
- Logs: stack traces from connection pool or client leak detection.

Set thresholds based on real workloads. Some resources are intentionally pooled for reuse; those are not leaks. Leaks typically manifest as active/leased resources growing without dropping, threads multiplying per execution, or unowned artifacts.

Hikari leakDetectionThreshold warns when a connection is held for too long; it is not an auto-fix mechanism. Use the warning's stack trace to locate the acquire site and find which code branch fails to release.

## 20. Tests should not rely on GC to prove cleanup

Do not call System.gc() and then inspect object counts or file descriptors to prove a resource closed. Garbage collection is not guaranteed to run immediately, and finalizers/cleaners do not replace explicit lifecycles.

Resources such as file streams, JDBC connections, and HTTP responses must be closed explicitly. Verify via probes, proxies, pool metrics, or resource operations after the step completes. Heap assertions are only useful for memory leaks analyzed via profilers and usually belong in separate stress tests.

If a class relies on Cleaner as a last-resort safety net, tests must still prove code calls close/dispose on time. Cleaner is not a step's primary cleanup path.

## 21. Common pitfalls when testing for resource leaks

**Testing only the happy path:** errors in processors/writers can bypass cleanup. Write failure tests after resources have opened.

**Asserting only job status:** a COMPLETED job does not prove connections/files/sockets closed. Track active resources or close callbacks.

**Reader delegate not registered as ItemStream:** wrapper does not expose lifecycle so the delegate may never receive close(). Register .stream(delegate) or forward the full ItemStream contract.

**Manually closing transaction-bound connections:** can break transactions. Use JdbcTemplate, repositories, or DataSourceUtils properly.

**Assuming close() runs after a JVM crash:** callbacks only run within lifecycles where the process can still execute. Design recovery and leftover artifact cleanup.

**Counting pool connections and requiring zero:** pools may retain idle connections or other tests may use them. Compare active count to baseline and isolate tests.

**Deleting staging files immediately on FAILED:** jobs may restart and need those files/checkpoints. Close handles immediately while retaining artifacts per retention policy.

**Shutting down shared executors after each step:** other steps may still need the executor. Manage lifecycle at the ApplicationContext level.

**Using non-thread-safe probes:** multiple partitions updating concurrently can corrupt test counts. Use atomic/concurrent collectors.

**Using GC/finalizers as cleanup:** timing is nondeterministic and unguaranteed. Call close/dispose explicitly.

## 22. Resource lifecycle test matrix

A practical integration test suite should cover the main scenarios:

| Scenario | Resources to Track | Expected Outcome |
| --- | --- | --- |
| Step succeeds | Reader, writer, connections, files | Resources closed; active count returns to baseline |
| Processor throws exception | Reader and opened resources | Step ends per policy; resources released |
| Writer throws exception | Reader, writer, JDBC | No borrowed resources remain after step finishes |
| Reader open fails midway | Partially opened files/channels/connections | open() self-cleans already-created parts |
| Reader delegate inside wrapper | Delegate stream | Delegate receives close lifecycle |
| Step restart | Old and new resources | Old resources close; new resources open and close; checkpoint restored |
| Multiple partitions | Each worker's resources | All resources of finished workers are released |
| Repeated job runs | Pools, threads, temp files | No upward trend in active resources/artifacts beyond policy |
| ApplicationContext closes | Executors and singleton resources | Executors shut down per application lifecycle |

Not every test needs to mock all resources. Choose integration tests for real transactions/lifecycles and unit tests for self-managed resource code. Tests closer to real resources are far more effective at uncovering ownership bugs.

## 23. Process for building tests for a custom ItemStream

When writing a custom reader/writer, design lifecycle observability from the start:

1. Move resource opening out of the constructor and into open().
2. Ensure open() self-cleans resources if opening fails midway.
3. Save checkpoints in update() if the component needs restart.
4. Close resources in close() and reset references in finally.
5. Make close() idempotent.
6. Register every delegate ItemStream with the step.
7. Use probes or wrappers in tests to observe open/close counts.
8. Test success, failure, stop, restart, and concurrent executions.

A custom stream must not hold resources in static fields or pass resources across executions. Each step execution must own its own resources; application-wide shared resources must have their own separate lifecycles.

## 24. How to test for resource leaks in production

First, list the resources a step opens and clearly define owners along with closing points. For Spring Batch readers/writers, use ItemStream.open/update/close; for JDBC, use JdbcTemplate/repositories or transaction-aligned connection management; for HTTP responses, file streams, and sockets, close explicitly; for executors, let Spring manage lifecycles when shared.

Next, write integration tests for both success and failure. Use probes for custom ItemStreams, pool metrics or datasource proxies for JDBC, mock servers for HTTP bodies, and check threads/executors at their proper lifecycle scopes. Include delegate streams, partitioning, and restarts if the step uses those mechanisms.

Finally, run repeated iterations to detect upward trends in resource usage. Compare active resources against baseline, distinguishing legitimate idle pooled resources from leaked ones. In production, monitor connection pools, HTTP pools, threads, file descriptors, and temporary artifacts; use JFR/JMX/logs to trace acquire sites that fail to release.

Testing for resource leaks in Spring Batch means verifying ownership and lifecycles across every execution path. A step properly releases resources only when execution-owned streams, connections, responses, file handles, and workers close after both success and failure while preserving state needed for restart. Probes, pool metrics, repeated runs, and restart tests catch leaks before they accumulate into operational incidents.

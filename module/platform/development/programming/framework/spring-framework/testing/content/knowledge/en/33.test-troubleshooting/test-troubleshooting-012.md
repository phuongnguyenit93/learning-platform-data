# Timeouts Caused by Background Tasks, Data Locks, or Unready Infrastructure

A Spring integration test can time out even when the business logic is correct. A request may be waiting on an incomplete `@Async` task, a transaction may be waiting on a lock held by another test, the connection pool may be exhausted, or a container may be running while the database/broker inside it is not yet ready to accept requests. To resolve it properly, determine precisely which operation is waiting and which layer owns the timeout.

A `Timeout` message only states that a time limit was exceeded. It does not explain the cause on its own. A JUnit timeout can be a consequence of a blocked query; a connection acquisition timeout can be a consequence of an unclosed previous transaction; a timeout sending a message can occur because the broker is not ready or the consumer has not received the message. Locate the first waiting point and trace its dependencies.

## Distinguishing Timeout Layers

An execution flow can pass through several independent time limits:

```text
JUnit test timeout
    |
    +-- waiting on Future / latch / Awaitility
    |       |
    |       +-- async executor queue and worker threads
    |               |
    |               +-- acquiring connection from pool
    |                       |
    |                       +-- waiting for database lock / running query
    |
    +-- waiting for container or service readiness
            |
            +-- connecting to broker / HTTP service / database
```

| Layer | Example | What is being bounded |
|---|---|---|
| Test framework | JUnit `@Timeout` | Total duration of the test method or lifecycle callback |
| Async synchronization | `Future#get`, `CountDownLatch#await`, Awaitility | Wait time for a task or completion condition |
| Executor | Queue capacity, worker threads, task rejection | Ability to accept and execute background tasks |
| Connection pool | Hikari `connectionTimeout` | Wait time to acquire a connection from the pool |
| Database lock | `lock_timeout`, lock wait timeout | Wait time for another transaction to release a lock |
| Database statement | `statement_timeout`, query timeout | Execution time of a single SQL statement |
| Network client | Connect/read/response timeout | Time to establish a connection or wait for a response |
| Test infrastructure | Testcontainers startup timeout, wait strategy | Wait time for a service inside a container to become ready |
| Messaging | Consumer poll/processing timeout | Wait time for a message to be received and processed |

These limits do not substitute for one another. Raising a JUnit timeout from 5 to 60 seconds may make the test wait longer, yet it will not fix a deadlock, a congested executor, or an unready container. Identify the timeout layer before adjusting configuration.

## Setting Per-Layer Time Budgets

Timeouts should reflect a reasonable upper bound for each operation. Inner limits should be small enough to report failures close to the cause, while the overall test timeout should exceed the sum of steps plus buffer for assertions and cleanup.

For example, a test that starts a container, submits an async task, and reads the result:

| Stage | Illustrative limit | Meaning |
|---|---:|---|
| Container startup/readiness | 90 seconds | Allows image startup and health check to succeed |
| Acquiring a connection | 3 seconds | Detects pool exhaustion or unreachable datasource |
| Query/lock wait | 2 seconds | Detects slow queries or blocked locks |
| Async completion | 5 seconds | Waits for background task completion |
| Entire test | 15 seconds after context is ready | Stops hung tests and lets cleanup run |

These are only examples; actual values must match your test SLAs and CI environment. Do not mechanically set all timeouts equal. If the outer timeout is shorter than a sub-step's timeout, the test framework can abort before the sub-step reports its specific cause.

In particular, container startup often occurs before the test method and may be shared across the lifecycle/context. Do not budget startup timeout as if it always fits inside a single method's duration.

## Timeouts Caused by Incomplete Background Tasks

With `@Async`, `TaskExecutor`, `@Scheduled`, or message listeners, the call launching a task can return before the actual work finishes. The test must wait for a meaningful completion signal rather than assuming the work finished the moment the launcher method returned.

### Use `CompletableFuture` Instead of `Thread.sleep`

If the async method returns `CompletableFuture`, await the future with a finite timeout:

```java
@Service
class ReportJob {

    @Async("reportExecutor")
    public CompletableFuture<Report> generate(long reportId) {
        Report report = reportService.generate(reportId);
        return CompletableFuture.completedFuture(report);
    }
}
```

The test must obtain the bean from the Spring context so the call goes through the `@Async` proxy:

```java
@SpringBootTest
class ReportJobTest {

    @Autowired
    private ReportJob reportJob;

    @Test
    void completesReportWithinExpectedTime() throws Exception {
        Report report = reportJob.generate(42L)
                .get(5, TimeUnit.SECONDS);

        assertThat(report.getId()).isEqualTo(42L);
    }
}
```

`Future#get(timeout, unit)` returns the result once the task finishes. If time expires, it throws `TimeoutException`; if the task fails, the caller receives `ExecutionException` and can inspect the cause. This synchronizes the test with the task while preserving worker-thread exceptions.

Do not call `new ReportJob(...)` directly in the test when trying to verify `@Async`. The annotation is enforced via a Spring proxy; self-invocation or calling a manually constructed object can run synchronously.

### Use `CountDownLatch` When the Task Returns `void`

For callbacks or listeners returning `void`, use `CountDownLatch` to signal that an event occurred:

```java
@Test
void waitsUntilBackgroundHandlerFinishes() throws Exception {
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();

    executor.execute(() -> {
        try {
            handler.process(message);
        } catch (Throwable ex) {
            failure.set(ex);
        } finally {
            completed.countDown();
        }
    });

    assertThat(completed.await(5, TimeUnit.SECONDS))
            .as("background handler should finish")
            .isTrue();
    assertThat(failure.get()).isNull();
}
```

The latch must be decremented inside `finally`; otherwise an exception in the task can leave the test waiting until timeout without knowing the worker failed. To inspect a result, store it in an `AtomicReference` or use `CompletableFuture`.

### Use Awaitility for Final State

Some tasks return no direct handle; they update a database, cache, or job status. You can use Awaitility to await the final condition:

```java
await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
                assertThat(jobRepository.findStatus(jobId))
                        .isEqualTo(JobStatus.COMPLETED));
```

Awaitility retries the assertion until it succeeds or times out. It suits eventual consistency states, provided the condition is an unambiguous completion signal. Avoid polling on an intermediate value that might appear before the entire task completes.

Do not poll too aggressively if each check runs a heavy query or loads the service. Pick a reasonable poll interval and a timeout sufficient for test stability in CI.

### Distinguishing Task Submission from Task Completion

The following states are distinct:

1. The task was submitted to the executor.
2. The task was dequeued and started running.
3. The task completed successfully or failed.
4. The task's side effects committed and became visible to another transaction.

An assertion verifying `executor.execute(...)` was called only checks step 1. A thread name or latch at the start of the task checks step 2. Future completion checks step 3. If the task writes to the database, query again after commit in a new transaction to confirm step 4.

### Congested Executor Queue or Thread Pool

A task might never start because the executor exhausted its worker threads and its queue is full. Common signs include:

- The future has not completed, yet logs inside the task body have not appeared.
- Active thread count has reached max pool size.
- Queue size grows or the queue has no remaining capacity.
- Tasks are rejected with `TaskRejectedException` or `RejectedExecutionException`.
- All workers are blocked waiting on the database, HTTP calls, or other locks.

When tests use `ThreadPoolTaskExecutor`, inspect `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection policy, and shutdown lifecycle. Do not solve this by increasing the test timeout if the task never even ran.

In tests, you can use a small, controllable executor to reproduce a full queue. Verify the rejection policy and application behavior when tasks cannot be accepted. For ordinary tests, avoid spawning more concurrent tasks than the executor can handle merely to wait on all of them.

## Timeouts Caused by Data Locks or Held Transactions

Databases use locks to protect data when multiple transactions read and write concurrently. One transaction may have to wait for another to commit or roll back before continuing. If a transaction holds a lock too long, queries or requests will time out even though the database is still healthy.

### Pessimistic Locks and Lock Waits

With JPA, `LockModeType.PESSIMISTIC_WRITE` can instruct the database to hold a write lock on a row:

```java
public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select item from InventoryItem item where item.id = :id")
    Optional<InventoryItem> findForUpdate(@Param("id") long id);
}
```

If transaction A has already locked the row, transaction B calling `findForUpdate` may have to wait. Concurrent tests must make explicit which transaction holds the lock and when it releases it.

Do not wrap a single test method in an outer transaction and expect a separate worker thread to see uncommitted changes. Spring transactions are normally bound to the current thread; the worker thread has its own transaction. This can cause the worker to block or read stale state.

### Deadlock vs. Lock Wait Timeout

| Symptom | Meaning | Sign |
|---|---|---|
| Lock wait timeout | A transaction waited for a lock longer than the limit | One transaction holds the lock; another transaction is waiting |
| Deadlock | Transactions wait on each other's locks in a cycle | The database detects the cycle and aborts one transaction |
| Query timeout | An SQL statement ran too long, possibly from a large scan or lock wait | Statement/client timeout triggers |
| Connection acquisition timeout | Could not borrow a connection from the pool | Pool exhausted or connections not returned |

Deadlocks are normally detected by the database, which chooses one transaction as the victim. A lock wait timeout typically reports only that waiting for a lock exceeded the threshold. Both can surface as persistence errors at the Spring layer, yet their fixes differ.

### Avoid Holding Transactions/Locks During External Service Calls

A common cause is keeping a transaction open too long:

```java
@Transactional
public void reserve(long itemId) {
    InventoryItem item = repository.findForUpdate(itemId).orElseThrow();
    paymentClient.authorize(item.getPrice()); // network call while holding the lock
    item.decreaseAvailable();
}
```

If the HTTP call is slow, the row lock can be held for the entire network wait. Other transactions updating the same row must wait, increasing lock contention.

A better design is usually shortening the transaction boundary, validating preconditions before locking where possible, using expiring reservations/state transitions, or adopting an appropriate saga/outbox flow. You cannot simply remove the transaction if doing so breaks consistency; identify business invariants before changing commit boundaries.

### Testing Lock Contention Deterministically

A concurrency test needs two transactions and clear coordination. You can use `CountDownLatch` to confirm the first transaction holds the lock before the second transaction attempts to acquire it. The test should enforce timeouts on both latches and database operations, and always release transactions in `finally`.

Do not use `Thread.sleep()` hoping transaction A has locked the row before B runs. Instead, transaction A signals immediately after its locking query succeeds; the test starts B only after receiving that signal.

When testing lock timeouts, set a small lock wait limit in test-specific configuration if the database supports it. Do not alter global timeouts of a shared environment. Assert the exact exception/cause thrown by the driver or ORM, as wrapper exceptions vary across databases and versions.

### Optimistic Locking and Retries

With `@Version`, Hibernate/JPA can detect two transactions updating the same entity where one would overwrite an older version. The failure usually surfaces as `OptimisticLockException` or `ObjectOptimisticLockingFailureException`.

This is not a lock wait timeout. The database does not necessarily wait on a lock; instead, the update fails to match the current version. If the application uses retries, tests should verify retries apply only to retryable errors and have a bounded attempt count. Unbounded or improper retries can turn a clear conflict error into a prolonged timeout.

## Exhausted Connection Pools or Unreturned Connections

Spring Boot commonly uses HikariCP for JDBC datasources. `connectionTimeout` is the maximum time a caller waits to borrow a connection from the pool. When the pool runs out of connections, logs may show all connections active, zero idle, and threads waiting.

Common causes:

- Transactions kept open too long.
- Connections or JDBC resources not closed when using manual APIs.
- Many concurrent async tasks all requiring database connections while the pool is too small.
- Parallel test execution exceeding database/pool capacity.
- One task holding a connection while awaiting another task that needs the very same pool.

Example pool configuration in tests:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 4
      connection-timeout: 3000
```

Do not raise `maximum-pool-size` immediately upon seeing a timeout. First inspect active/idle/pending connections, transaction durations, and the number of worker threads hitting the database. Growing the pool when the database cannot handle more connections can make matters worse.

An application-level deadlock can also involve the pool: task A holds a connection and waits on future B, while B needs a connection from an already-exhausted pool. Avoid awaiting another task while holding a transaction/connection if that task needs the same resource.

## Unready Infrastructure Even When the Container Is Running

Testcontainers may report a container as running while the service inside has not finished starting up. A database may still be running recovery; a broker may not have opened its listener yet; an HTTP service may not have loaded configuration or connected to its own dependencies.

Distinguish these states:

```text
Container created
      |
      v
Container process running
      |
      v
Port is listening
      |
      v
Service health check passes
      |
      v
Application-level operation succeeds
```

An open port only proves a process is accepting TCP connections. It does not prove the database is accepting queries, the broker is ready for messages, or an auxiliary service has finished loading its data.

### Use Wait Strategies Instead of Sleep

Testcontainers supports waiting on ports, logs, HTTP endpoints, and Docker health checks. Example HTTP health endpoint:

```java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/report-service:1.4.2"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/actuator/health")
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofMinutes(2)));
```

For databases, prefer dedicated container modules such as `PostgreSQLContainer`, as they come with appropriate wait strategies. For custom services, pick an endpoint or log line that only appears once the service is genuinely ready.

Do not do this:

```java
container.start();
Thread.sleep(5000); // does not guarantee the service is ready
```

Fast machines waste time waiting; slow machines may still not be ready. A wait strategy with a timeout provides both a real completion condition and clearer failure diagnostics.

### Dynamic Endpoints and Spring Context Initialization Order

Containers are usually mapped to dynamic host ports. Never hardcode `localhost:5432` or a default port when Testcontainers assigns another port. Obtain the endpoint via container APIs and register it with Spring using `@DynamicPropertySource` or `@ServiceConnection`:

```java
@Container
@ServiceConnection
static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4-alpine");
```

Or:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

The supplier must return the endpoint of a live container when Spring creates the datasource. If a context stays cached longer than the container, a later test can reuse a context holding the URL of a stopped container. In that case, the failure may surface in another test class even though that class's configuration looks identical.

### Broker and Consumer Readiness

A broker accepting connections does not mean consumers have subscribed, partition assignment has finished, or listener containers are running. If a test publishes a message right after context startup, the message may arrive before the consumer starts listening.

Wait for a concrete consumer readiness signal or verify subscription/assignment using the appropriate API. For Kafka, inspect the listener container and partition assignments; for RabbitMQ, verify queues and bindings exist. When verifying message processing, use correlation IDs or queryable final state.

Do not sleep a fixed number of seconds after publishing. Wait for the successful processing condition using Awaitility or a bounded latch.

## Diagnosing Timeouts by Symptom

| Symptom | Likely cause | Evidence to gather |
|---|---|---|
| Future times out yet task never logged startup | Executor queue full, task rejected, or proxy did not dispatch | Executor active count, queue size, rejection logs, thread names |
| Task starts yet never finishes | Query, HTTP call, lock, or downstream call hung | Thread dump, correlation-ID logs, client timeouts, and DB activity |
| Hikari `Connection is not available` | Pool exhausted or connection leaked | Active/idle/pending counts, transaction duration, leak detection logs |
| Query waits a long time | Lock contention, large scan, or overloaded database | DB lock table, query plan, statement duration |
| Database connection refused right at startup | Container/service unready or wrong endpoint | Container logs, mapped port, JDBC URL, wait strategy |
| Consumer never receives message | Listener not running, wrong topic/queue, or mismatched offset/group | Listener state, topic/queue, partition assignment, consumer lag |
| Fails only when run in parallel | Data collision, shared lock, pool/executor capacity, or shared resource | Test isolation, worker count, DB locks, queue size |
| First run passes, later test fails to connect | Container stopped while context cache retains the old endpoint | Container lifecycle and Spring context cache |
| JUnit `@Timeout` expires before a specific error | Overall timeout shorter than sub-step timeout or test is blocked | Thread dump at timeout and per-layer timeouts |

## Collecting Thread Dumps When Tests Hang

Thread dumps identify which threads are running, waiting on monitors, waiting on conditions, or blocked on I/O. When a test hangs, capture a thread dump of the test JVM before the process is killed if possible.

Notable thread states:

- `BLOCKED`: thread is waiting for a monitor lock held by another thread.
- `WAITING` or `TIMED_WAITING`: thread is waiting on a latch, future, condition, queue, or timer; inspect stack frames to see what it awaits.
- JDBC stack frames: thread may be waiting on the database/driver or connection pool.
- HTTP client stack frames: thread may be waiting on a response or socket read.
- `ThreadPoolExecutor.getTask`: worker is idle waiting for a task; if no workers are active, the task may not have been submitted or the queue is empty.

In environments with JDK tools, `jcmd <pid> Thread.print` or `jstack <pid>` produces a thread dump. In CI, configure saving thread dumps on timeout or right before terminating timed-out test processes. Do not look only at thread states; read stack traces to link them to specific tasks and resources.

Attach correlation IDs/job IDs to background task logs to tie together the initial request, submission, worker start, and completion. This distinguishes an unscheduled task from one that started running and stalled on a dependency.

## Inspecting Database Locks and Waiting Queries

When suspecting a database lock, inspect database state directly while the test is still blocked. In PostgreSQL, inspect sessions, queries, and lock waits via `pg_stat_activity` and `pg_locks`:

```sql
select pid,
       state,
       wait_event_type,
       wait_event,
       now() - query_start as query_age,
       query
from pg_stat_activity
where datname = current_database()
order by query_start;
```

To inspect blocker/waiter relationships:

```sql
select waiting.pid as waiting_pid,
       waiting.query as waiting_query,
       blocking.pid as blocking_pid,
       blocking.query as blocking_query
from pg_stat_activity waiting
join pg_stat_activity blocking
  on blocking.pid = any(pg_blocking_pids(waiting.pid));
```

These queries are for PostgreSQL; visibility into some sessions may depend on role privileges. For MySQL, check `performance_schema.data_locks`, `data_lock_waits`, and `information_schema.innodb_trx`. For other databases, use the corresponding lock monitoring tools.

Once you locate the blocker, identify which transaction holds the lock, which test started it, and whether it is waiting on a network call or another future. Terminate hung transactions in cleanup and shorten lock-holding sections. Never kill sessions arbitrarily on a shared database; do so only on an isolated test database.

## Distinguishing Timeouts from Deadlocks and Data Races

Not every concurrency test failure is a timeout:

| Error | Meaning | Investigation direction |
|---|---|---|
| Timeout | An operation did not finish before its deadline | Identify the waiting point and timeout layer |
| Deadlock | Multiple transactions/threads form a cycle waiting on each other | DB deadlock report or thread dump; check lock acquisition order |
| Optimistic locking conflict | Version changed before update | Check `@Version`, retries, and concurrent writes |
| Unique constraint violation | Two tests/tasks created the same unique key | Check fixtures, namespaces, and test parallelism |
| Lost update | One update overwrote another's change | Check transaction isolation and locking mechanisms |
| In-memory data race | Multiple threads access unsynchronized state | Check thread safety and visibility |

A timeout is sometimes merely the symptom of a deadlock or data race preventing the wait condition from ever becoming true. Preserve exceptions and logs from the database/executor rather than changing timeouts to hide the symptom.

## Test Transaction and Async Worker Run on Different Threads

Spring transactions are normally bound to the current thread. A `@Transactional` test method can open a test-managed transaction; when it calls `@Async`, the worker thread does not automatically join that transaction.

This leads to several situations:

- The test writes uncommitted data, then the async worker queries it and does not see the uncommitted changes.
- The test holds a row lock until the method ends, while the worker needs that row and blocks.
- The test method waits for the future to complete, while the future waits on a database lock held by the test transaction itself.
- The test finishes and rolls back its transaction while the worker is still running and operating on rolled-back data.

An application-level deadlock can form as follows:

```text
Test thread:
  opens transaction A
  locks row X
  submits async task
  waits for Future to complete
          |
          v
Worker thread:
  opens transaction B
  needs lock on row X
  waits for transaction A to release lock

Transaction A only releases the lock when the test thread stops waiting on Future.
```

This is a waiting cycle created by test design. To fix it, commit the writing transaction before the worker reads, avoid holding locks while waiting on async tasks, or structure the test with two clearly ordered transactions. If the test must verify data after commit, read in a new transaction after the writing transaction ends.

For HTTP tests via `RANDOM_PORT`, requests run on server threads with their own transactions. `@Transactional` on the test does not automatically roll back server transactions. Clean up committed data or use a dedicated database/schema.

## Parallel Test Execution and Data Contention

A test that passes alone yet times out in the full suite may be contending over shared data or resources:

- Two tests update the same row and hold conflicting locks.
- Tests share the same email, username, or external reference under a unique constraint.
- Multiple tests share a topic, consumer group, Redis key, or bucket prefix.
- The number of test workers exceeds connection pool or executor capacity.
- A shared container/service has its state reset by one test while another is using it.

The solution is isolating data and namespaces per test/worker, reducing parallelism if resources are genuinely constrained, and avoiding global cleanups on shared resources. Do not disable parallel execution permanently just to mask a race condition; identify which resource is shared first.

When parallel testing is required, design fixtures with unique IDs, short transactions, consistent lock ordering, and cleanup deleting only data owned by the current test. For brokers, use isolated topics/groups or correlation keys; for caches/storage, use isolated key/bucket prefixes.

## Is Retry a Fix for Timeouts?

Retries are useful for transient errors and safely repeatable operations, such as a slow-starting service or an idempotent request hitting a temporary network glitch. Retries are inappropriate for masking:

- Deadlocks caused by inconsistent lock acquisition order.
- Connection leaks or exhausted pools.
- Executors with no available workers.
- Tasks submitted multiple times producing duplicate side effects.
- Shared test fixtures causing unique constraint conflicts.
- Missing readiness configuration where a service may never become ready.

When using retries, set explicit attempt limits and total time budgets, use appropriate backoff, log attempts and causes, and ensure operations are idempotent or carry an idempotency key. Tests should verify retries stop once the budget is exhausted and produce no duplicate side effects.

## Workflow for Troubleshooting Timeouts in Spring Tests

1. **Identify the waiting point:** JUnit method, future/latch, executor, connection pool, SQL lock, network client, or container readiness.
2. **Read causes and logs prior to the timeout:** look for `TimeoutException`, `SQLTransient...`, `CannotGetJdbcConnectionException`, `TaskRejectedException`, HTTP timeouts, or Testcontainers messages.
3. **Inspect state at the moment of hang:** capture thread dumps, executor metrics, pool metrics, DB activity/locks, or container logs.
4. **Check transaction boundaries:** see which thread opened each transaction, which holds locks, and whether workers need uncommitted data.
5. **Check readiness and endpoints:** is the service health-ready, does the port match the current mapped port, and does the context cache retain a stale endpoint?
6. **Tune the right layer:** query timeout for queries, lock timeout for lock waits, connection timeout for pools, wait strategy for containers, future timeout for async completion.
7. **Re-run the test in isolation, then the related suite:** confirm the root cause is gone and no contention remains under parallel execution.

## Quick Diagnostic Reference Table

| Message / symptom | First cause to suspect | Evidence to collect |
|---|---|---|
| `TimeoutException` from `Future.get` | Async task has not finished or never started | Executor metrics, worker logs, thread dump |
| Awaitility timeout | Target state condition never occurred | Current value, polling exceptions, task/job status |
| `TaskRejectedException` | Executor queue/thread capacity or shutdown | Pool size, queue capacity, lifecycle, and rejection policy |
| `Connection is not available, request timed out` | Hikari pool exhausted or connections held | Active/idle/pending connections, leak detection, transaction duration |
| `Lock wait timeout exceeded` | Another transaction holds a row/table lock | DB lock views, blocker session, transaction age |
| `Deadlock found` / deadlock detected | Lock-wait cycle across transactions | Database deadlock report, resource access order |
| `statement timeout` | Query ran too long or waited on a lock | Query plan, DB activity, statement/lock timeout settings |
| Container startup timeout | Service inside container is unready or wait condition is wrong | Container logs, health status, startup command |
| Connection refused right after container start | Wrong endpoint/port or service not listening yet | Mapped port, wait strategy, service logs |
| Consumer test timeout | Listener not subscribed or message not processed | Listener state, topic/queue, consumer lag, correlation ID |
| Times out only when suite runs in parallel | Data contention or resource exhaustion | Test isolation, pool/executor metrics, DB lock views |

## Principles for Setting Stable Timeouts

- Set finite timeouts at every wait point that could hang: futures, latches, Awaitility, network clients, and the test framework.
- Use actual completion signals; avoid `Thread.sleep()` and fixed-time assumptions.
- Distinguish submitted tasks, started tasks, completed tasks, and committed side effects.
- Keep transactions short; never wait on network calls or futures while holding row locks or connections if workers need that same resource.
- Use wait strategies targeting service readiness, not merely checking that the container process is running.
- Isolate database rows, topics, queues, cache keys, and object storage across parallel tests.
- Capture thread dumps, pool metrics, DB lock info, and container logs whenever timeouts occur.
- Only raise a timeout when the current value does not fit a reasonable SLA; never use it to mask deadlocks, leaks, or broken readiness.

When a test times out, the key is finding which component is holding or waiting on a resource. Separating timeouts by layer, synchronizing background tasks with futures/latches, observing locks and connection pools, and waiting on infrastructure via health conditions allow bugs to be pinpointed clearly. Tests become much more stable when transactions are short, resources are isolated, and every wait has an explicit completion condition paired with a bounded time limit.

# Thread-switching timeouts and unrolled-back data

In Spring Framework Testing, a test method can run inside a transaction managed by Spring Test. By default, Spring rolls back this transaction after the test ends so test data does not persist long-term.

That mechanism relies on a crucial condition: **the transaction is bound to the thread executing the test**. Spring associates the transaction with the current JDBC connection or JPA EntityManager via per-thread resource management, typically using ThreadLocal.

If a test uses a timeout mechanism that runs the tested code on another thread, that code does not automatically join the test's transaction. Write operations may run in a separate transaction or in auto-commit mode. When the test ends, Spring rolls back the original transaction but cannot roll back changes already committed by the other thread.

This is a common reason a test appears to roll back successfully yet data still remains in the database.

## 1. How does Spring Test manage transactions?

When a test method is annotated with @Transactional, the Spring TestContext Framework can open a test-managed transaction before running the test method and roll back after the test completes.

Example:

~~~java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesCustomer() {
        customerRepository.save(
                new Customer("Linh", "linh@example.com"));

        assertEquals(1, customerRepository.count());
    }
}
~~~

With Spring Test's default configuration, the test's transaction is rolled back after the test method completes. As a result, records created in the test do not leave persistent data behind.

General sequence:

~~~text
Spring TestContext
      |
      | starts test-managed transaction
      v
Test thread
      |
      | calls repository / service
      | operations join the current transaction
      v
Database
      |
      | test method finishes
      v
Spring TestContext rolls back transaction
~~~

This works because repository and service calls execute on the same thread as the test's transaction, while using the same transaction manager and resources managed by Spring.

### Transactions are bound to the thread

In Spring's imperative transaction model, transaction resources are normally bound to the current thread. TransactionSynchronizationManager stores resource and synchronization information per thread.

When a transaction manager opens a transaction for JDBC or JPA, the corresponding resource is bound to the thread. Subsequent operations on the same thread can retrieve that resource and join the current transaction according to the appropriate propagation.

A new thread does not automatically receive the transaction resources bound on the original thread.

This differs from passing an ordinary Java object. Passing a reference to a service, repository, or EntityManagerFactory to another thread does not cause the original thread's transaction to automatically carry over.

## 2. How can timeouts switch threads?

JUnit Jupiter provides two common timeout assertions:

- **assertTimeout:** executes the executable on the thread calling the assertion; only reports a failure if execution duration exceeded the limit after the executable completes.
- **assertTimeoutPreemptively:** executes the executable on a different thread so it can be interrupted when the limit is exceeded.

This difference is critical when the test runs inside a Spring-managed transaction.

### assertTimeout keeps the same thread

~~~java
@Test
@Transactional
void usesNonPreemptiveTimeout() {
    assertTimeout(Duration.ofSeconds(2), () -> {
        customerRepository.save(
                new Customer("Linh", "linh@example.com"));
    });
}
~~~

The executable runs on the thread executing the test. If the repository joins the current transaction, data changes remain inside the test-managed transaction and can be rolled back when the test finishes.

The point to understand is that assertTimeout does not stop the executable immediately at the moment time expires. It waits for the executable to finish and then compares actual duration against the limit. If code hangs indefinitely, the assertion also waits for it to return.

### assertTimeoutPreemptively switches to another thread

~~~java
@Test
@Transactional
void preemptiveTimeoutCanEscapeTestTransaction() {
    assertTimeoutPreemptively(
            Duration.ofSeconds(2),
            () -> customerRepository.save(
                    new Customer("Linh", "linh@example.com"))
    );
}
~~~

The snippet above carries risk. JUnit runs the callback on a separate thread. That thread does not join the transaction bound by Spring Test to the test-method runner thread.

If the repository call opens its own transaction, that transaction can commit when the repository method completes. The test's transaction on the original thread rolls back afterward, yet the record committed in the other transaction still persists.

### Comparing the two timeout approaches

| Characteristic | assertTimeout | assertTimeoutPreemptively |
|---|---|---|
| Thread executing callback | Current thread | Separate thread |
| Preserves Spring Test's thread-bound transaction | Yes, unless code inside switches threads itself | No |
| Can report timeout before callback finishes | No | Yes |
| Suitable for tests writing to database in a test-managed transaction | Usually more suitable | Risk of writing outside the transaction |
| Can stop hanging code immediately on timeout | No | Can request thread interruption; does not guarantee code always stops |

If the goal is simply detecting a slow test, prefer a timeout mechanism that stays on the same thread when the test depends on a transaction or ThreadLocal context.

## 3. Why does data still remain after the test rolls back?

Consider the following flow:

~~~text
Thread A: JUnit test thread
    |
    +-- Spring opens transaction T1
    |
    +-- assertTimeoutPreemptively(...)
             |
             +-- Thread B: callback thread
                    |
                    +-- repository.save(...)
                    |
                    +-- transaction T2 or auto-commit
                    |
                    +-- writes data and commits
    |
    +-- callback finishes or times out
    |
    +-- Spring rolls back T1
             |
             +-- T2 already committed so it is not rolled back
~~~

There are two independent transactions:

- **T1:** the test-managed transaction opened by Spring on thread A.
- **T2:** a new transaction opened by the repository or service on thread B, or write operations committed under the connection's auto-commit mode.

Rolling back T1 only reverts changes belonging to T1. It cannot undo another transaction that has already committed.

### Repositories can open their own transactions

Write methods on Spring Data JPA repositories are typically configured as transactional. When invoked with no active transaction on thread B, the repository can open its own transaction, perform the operation, and commit when the method completes.

Example:

~~~java
assertTimeoutPreemptively(
        Duration.ofSeconds(1),
        () -> customerRepository.saveAndFlush(customer)
);
~~~

If saveAndFlush runs in its own transaction on thread B, that transaction can commit independently of the test's transaction.

Do not assume that because the test method has @Transactional, every repository call occurring during the test belongs to that transaction. That is only true when the call actually executes within the same transaction context.

### JDBC can also write outside the test's transaction

If the callback thread uses JdbcTemplate, Spring obtains a connection per current thread. The new thread has no connection bound from the test thread, so the operation may acquire a different connection.

Depending on datasource and transaction manager configuration, that operation may:

- Run with auto-commit enabled.
- Join a separate transaction opened by a service or repository.
- Be wrapped by another transaction created by code on the new thread.

In those cases, rolling back the test thread's transaction does not revert the changes.

## 4. Example reproducing data escaping rollback

Suppose there is a repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

A test might create data inside a preemptive timeout:

~~~java
@SpringBootTest
@Transactional
class PreemptiveTimeoutTransactionTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void writesCustomerOnAnotherThread() {
        assertTimeoutPreemptively(
                Duration.ofSeconds(2),
                () -> customerRepository.saveAndFlush(
                        new Customer(
                                "Linh",
                                "linh-timeout@example.com"))
        );
    }
}
~~~

After the test finishes, Spring rolls back the transaction bound to the test thread. However, the saveAndFlush operation may have run and committed in a separate transaction on the callback thread.

Another test running afterward may find the email linh-timeout@example.com even though the test that created the data has ended.

This is an example of the risk, not a recommended way to write tests. If you need to test timeouts and persistence, design explicit transaction boundaries and cleanup.

## 5. @Timeout also requires attention to thread mode

JUnit Jupiter has the @Timeout annotation. This annotation supports configuring thread mode:

- **SAME_THREAD:** runs the test on the current thread and applies timeout in this mode.
- **SEPARATE_THREAD:** runs the test on a separate thread.
- **INFERRED:** takes the mode from JUnit's default configuration.

Example explicitly choosing SAME_THREAD:

~~~java
@Test
@Timeout(
        value = 2,
        unit = TimeUnit.SECONDS,
        threadMode = Timeout.ThreadMode.SAME_THREAD)
@Transactional
void checksOperationWithinTimeoutOnSameThread() {
    customerRepository.save(
            new Customer("Linh", "linh@example.com"));
}
~~~

JUnit Jupiter infers thread mode from global configuration by default; the standard default is SAME_THREAD. However, a project can change the mode via junit-platform.properties or system configuration.

Example default configuration:

~~~properties
junit.jupiter.execution.timeout.thread.mode.default = SAME_THREAD
~~~

If a project sets SEPARATE_THREAD or the annotation explicitly specifies SEPARATE_THREAD, the test can switch threads and lose Spring Test's transaction context.

When reading a test with @Timeout, check all three:

1. threadMode declared directly on the annotation;
2. JUnit's default timeout configuration;
3. whether calls inside the test switch to an executor or another thread themselves.

@Timeout with SAME_THREAD does not make an asynchronous task automatically run inside the test's transaction. It only governs which thread executes the test method under that timeout mode.

## 6. Same-thread timeouts still have limitations

assertTimeout and @Timeout with SAME_THREAD avoid JUnit proactively shifting the callback to another thread. This helps preserve ThreadLocal context during normal execution.

However, they do not solve every issue:

- assertTimeout only reports a timeout overrun after the callback completes.
- Same-thread timeouts can interrupt the test thread on expiration, yet code that does not respond to interruption may keep running.
- A call that spawns a thread or submits tasks to an executor still executes on another thread.
- Timeouts do not roll back already-committed independent transactions.
- Timeouts do not automatically stop a request or task in an external system.

If a test performs irreversible operations, such as sending payments, writing files, or publishing messages, define dedicated cleanup and idempotency mechanisms. Do not treat timeouts as a rollback mechanism.

## 7. Distinguishing test timeouts from real asynchronous processing

A test can switch threads due to a preemptive timeout. An application can also switch threads due to using:

- @Async.
- Executors or thread pools.
- CompletableFuture.
- TaskExecutor.
- Message listener containers.
- Schedulers.
- Reactive pipelines with scheduler switching.

All of these cases can cause code to run outside the thread holding the test's transaction.

Example:

~~~java
@Service
public class CustomerImportService {

    @Async
    public CompletableFuture<Void> importCustomer(CustomerData data) {
        // Write data on the worker thread.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

If a test calls importCustomer while the test thread has a transaction, the worker thread does not automatically join that transaction.

If the method is annotated with @Transactional and invoked through a Spring proxy on the worker thread, a separate transaction may be opened on the worker thread. When the method finishes, that separate transaction can commit. Rolling back the test thread cannot undo an already-committed independent transaction.

### Waiting on a Future does not transfer the transaction to the worker thread

~~~java
@Test
@Transactional
void waitsForAsyncImport() throws Exception {
    CompletableFuture<Void> future =
            customerImportService.importCustomer(data);

    future.get(2, TimeUnit.SECONDS);
}
~~~

future.get() runs on the test thread and waits for the result. Yet waiting does not transfer the test's transaction to the worker thread. The worker still has its own transaction context.

Points to distinguish:

- **Waiting thread:** the test thread, which may hold a test-managed transaction.
- **Executing import thread:** the worker thread, which does not automatically receive the test's transaction.
- **Result:** data written by the worker may have committed independently before the future completes.

If a test verifies an asynchronous flow that writes to the database, verify data across the persistence boundary and provide cleanup for committed data.

## 8. Transaction propagation does not cross thread boundaries

Spring transaction propagation determines how a call joins or creates a transaction within the current execution context.

Some common propagation modes:

| Propagation | Meaning on the same thread |
|---|---|
| REQUIRED | Joins the current transaction if one exists; otherwise creates a new transaction |
| REQUIRES_NEW | Creates a new transaction and temporarily suspends the current transaction |
| SUPPORTS | Joins the transaction if one exists; otherwise runs without a transaction |
| NOT_SUPPORTED | Suspends the current transaction and runs without a transaction |
| MANDATORY | Requires a current transaction to exist |
| NEVER | Requires no current transaction to exist |
| NESTED | Uses a nested transaction if the transaction manager supports it |

These propagation modes do not automatically transfer transactions across threads.

### REQUIRED on a new thread

If a service method has:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void process() {
    // ...
}
~~~

When invoked on thread A, which already has a transaction, the method can join transaction A.

When invoked on thread B, which has no transaction, REQUIRED creates a new transaction on B. That new transaction is independent of the test thread's transaction.

### REQUIRES_NEW even on the same thread

REQUIRES_NEW also presents a notable scenario: it creates an independent transaction even when the same thread already has an outer transaction.

~~~java
@Transactional
public void processOrder() {
    orderRepository.save(order);
    auditService.recordEvent();
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordEvent() {
    auditRepository.save(event);
}
~~~

If recordEvent commits successfully, rolling back the outer transaction afterward still cannot revert the audit record committed in the REQUIRES_NEW transaction.

Thus, test-managed transaction rollback likewise does not automatically clean up effects committed inside a REQUIRES_NEW transaction. This is another cause of leftover data after a test, even without a thread switch.

When testing a flow with REQUIRES_NEW, clearly identify which transactions can commit independently and how to clean up that data.

## 9. How to choose safe timeouts for transactional tests

### Prefer assertTimeout when needing to keep the thread

If a test writes data inside a test-managed transaction and only needs to verify that execution duration stays within a limit, use assertTimeout:

~~~java
@Test
@Transactional
void savesCustomerWithinExpectedDuration() {
    assertTimeout(Duration.ofSeconds(2), () -> {
        customerRepository.saveAndFlush(
                new Customer("Linh", "linh@example.com"));
    });
}
~~~

This keeps the callback on the test thread. Once the callback completes, Spring can still roll back the test's transaction.

The limitation is that the assertion does not preemptively stop the callback when the timeout expires.

### Use @Timeout with SAME_THREAD when test-level timeout is needed

~~~java
@Test
@Transactional
@Timeout(
        value = 3,
        unit = TimeUnit.SECONDS,
        threadMode = Timeout.ThreadMode.SAME_THREAD)
void updatesCustomerWithinTimeout() {
    customerService.updateCustomer(customerId);
}
~~~

This keeps the test method on the current thread during execution. Remember that interruption does not guarantee stopping every operation, and tasks launched by the test on other threads still have independent transactions.

### Avoid assertTimeoutPreemptively around write operations

If the callback can write data through a repository, JdbcTemplate, or transactional service, do not wrap it in assertTimeoutPreemptively in a test relying on default rollback.

If a preemptive timeout is genuinely required, design the test as a test with independent side effects: use uniquely identified data, wait for the worker to finish, and perform cleanup that commits separately.

## 10. When running on another thread is unavoidable

Some tests must use another thread to verify asynchronous behavior or preemptive timeouts. In those cases, do not rely on the test-managed transaction to clean up all changes.

You can apply these principles:

1. **Use isolated data per test:** generate a unique testRunId or identifier.
2. **Scope the data:** every record created by the worker is tagged with testRunId.
3. **Wait for the worker to finish:** do not start cleanup while the worker could still be writing.
4. **Clean up in an independent transaction:** delete operations must actually commit, not roll back with the test transaction.
5. **Verify committed results:** re-query from a new transaction or persistence context.
6. **Clean up dependent data too:** child records, outbox events, or audit records if created in the same flow.

### Example using testRunId

~~~java
@SpringBootTest
class AsyncCustomerImportTest {

    @Autowired
    private CustomerImportService importService;

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private TransactionTemplate cleanupTransaction;

    private final String testRunId = UUID.randomUUID().toString();

    @Test
    void importsCustomerOnWorkerThread() throws Exception {
        CustomerData data = new CustomerData(
                testRunId,
                "Linh",
                "linh@example.com");

        CompletableFuture<Void> future =
                importService.importCustomer(data);

        future.get(5, TimeUnit.SECONDS);

        assertTrue(customerRepository
                .existsByImportRunId(testRunId));
    }

    @AfterEach
    void removeImportedData() {
        cleanupTransaction.executeWithoutResult(status ->
                customerRepository.deleteByImportRunId(testRunId));
    }
}
~~~

This example assumes TransactionTemplate is configured with appropriate propagation so cleanup commits independently if the test has an outer transaction. If the test class has no test-managed transaction, TransactionTemplate's default propagation is typically REQUIRED and can open a new transaction on its own.

If the test method has @Transactional and cleanup runs while that transaction is still active, a default REQUIRED TransactionTemplate can join the test's transaction. In that case, configure the cleanup transaction with REQUIRES_NEW or place cleanup outside the test's transaction.

## 11. Cleaning up with REQUIRES_NEW when the test thread has a transaction

A clear way to express this is configuring a dedicated TransactionTemplate for cleanup:

~~~java
@SpringBootTest
@Transactional
class AsyncCustomerImportTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    private String testRunId;

    @BeforeEach
    void createRunId() {
        testRunId = UUID.randomUUID().toString();
    }

    @AfterEach
    void cleanupCommittedWorkerData() {
        TransactionTemplate cleanup = new TransactionTemplate(
                transactionManager);

        cleanup.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        cleanup.executeWithoutResult(status ->
                customerRepository.deleteByImportRunId(testRunId));
    }
}
~~~

REQUIRES_NEW suspends the current test transaction, opens a separate cleanup transaction, and commits when cleanup finishes. Spring can then roll back the test transaction normally.

This approach is useful when the worker committed data outside the test transaction. However, only run cleanup after the worker has finished or is guaranteed to make no further writes. If the worker is still running, it could recreate the record after cleanup completes.

If the transaction manager does not support propagation or resources do not share the same transaction manager, choose cleanup suited to the underlying infrastructure.

## 12. Managing executors and workers when tests time out

When a test creates its own ExecutorService or submits asynchronous tasks, explicitly manage the executor lifecycle.

Example:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();

try {
    Future<?> future = executor.submit(() -> {
        customerRepository.saveAndFlush(customer);
    });

    future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Request task cancellation.
    // Cancellation depends on whether the task responds to interruption.
} finally {
    executor.shutdownNow();
    executor.awaitTermination(2, TimeUnit.SECONDS);
}
~~~

shutdownNow() sends interrupt requests to running tasks; it does not guarantee every task stops immediately. A task blocked in a native call, ignoring interruption, or handling cleanup improperly may keep running.

When database data could be written from a worker:

- Do not treat a cancelled Future as proof the task stopped.
- Wait for executor termination within an appropriate bound.
- If the worker does not stop, assume test data can continue changing.
- Use a separate namespace or separate database/schema to limit impact.
- Only clean up once you know the worker is no longer writing data.

With application-managed asynchronous code, it is better to inject a controllable executor in tests and have a clear completion-awaiting mechanism.

## 13. Do not rely on rollback for non-database side effects

Even when Spring's transaction stays properly on the same thread, database rollback cannot revert all side effects.

Examples:

- Sent emails.
- HTTP requests sent to a payment provider.
- Messages accepted by a broker.
- Files written to the filesystem.
- Tasks submitted to an executor.
- External caches updated outside the database.
- Committed REQUIRES_NEW transactions.

These side effects require separate testing strategies:

- Use mocks/fakes for email or payment gateways in unit tests.
- Use dedicated test brokers or servers for integration tests.
- Use temporary files and delete them explicitly.
- Use test namespaces to distinguish messages and data.
- Use outbox or compensation mechanisms if production requires consistency guarantees.

A test with @Transactional does not mean the entire system rolls back. That annotation only manages transactions configured for resources participating in the corresponding transaction manager.

## 14. Other ThreadLocal contexts can also be lost

Transactions are not the only context bound to a thread. When switching threads, data relying on ThreadLocal may be absent on the new thread:

- TransactionSynchronizationManager: transaction resources and synchronizations.
- SecurityContextHolder: security context in thread-local storage mode.
- RequestContextHolder: request attributes bound to the request thread.
- LocaleContextHolder: locale context bound to the thread.

Some frameworks have context propagation mechanisms or executor wrappers, yet do not assume every context propagates automatically.

For instance, a test running a callback on another thread might not see authentication set up via @WithMockUser if the security context strategy does not propagate to that thread. Similarly, the test transaction does not automatically appear in the callback thread.

Check the context propagation mechanism for each context type separately. Propagating security context does not mean transaction context is also propagated.

## 15. JUnit 4 timeout cases

If a project still uses JUnit 4, the timeout attribute on @Test has its own execution behavior:

~~~java
@Test(timeout = 1000)
public void writesCustomer() {
    customerRepository.save(customer);
}
~~~

JUnit 4 runs the test method in a separate thread to enforce the timeout. Thus, tests relying on a transaction bound by Spring to the lifecycle-running thread can encounter the same issue: the test method does not run on the thread holding the test-managed transaction.

When maintaining legacy tests, do not assume @Test(timeout=...) is equivalent to a same-thread timeout. Check the JUnit version and Spring Test integration in use.

With JUnit Jupiter, you can explicitly select the thread mode of @Timeout or use non-preemptive assertTimeout when needing to stay on the same thread.

## 16. How to diagnose leftover data after a test

When a test is annotated with @Transactional yet data still remains, identify transaction boundaries step by step instead of arbitrarily adding delete statements.

### Identify the thread executing write operations

Log thread names in the test method and in the callback:

~~~java
System.out.println(
        "test thread = " + Thread.currentThread().getName());

assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
    System.out.println(
            "callback thread = " + Thread.currentThread().getName());

    customerRepository.save(customer);
});
~~~

If the thread names differ, the callback switched threads.

### Check the active transaction

You can observe transaction state per thread:

~~~java
boolean active =
        TransactionSynchronizationManager
                .isActualTransactionActive();

boolean synchronizationActive =
        TransactionSynchronizationManager
                .isSynchronizationActive();
~~~

On the test thread with a test-managed transaction, the state is normally active. On a callback thread running a preemptive timeout, the state may be false before a repository or service opens its own transaction.

If a repository opens its own transaction inside the callback, checking before the repository call will show the thread has no transaction yet. After the repository method completes, that separate transaction may have committed.

### Re-query using a new transaction

Do not merely re-read within the same persistence context holding stale entities. Query from a new transaction or EntityManager to verify data committed in the database.

For example, use an independent transaction and query by testRunId. If data still exists after the test's transaction ended, that indicates effects were committed outside the rolled-back transaction.

### Locate sources of independent transactions

Check:

- assertTimeoutPreemptively or JUnit timeouts running on a separate thread.
- @Async, executors, CompletableFuture, or message listeners.
- Service methods with @Transactional invoked through a proxy on a worker thread.
- Repositories opening their own transaction when no current transaction exists.
- REQUIRES_NEW propagation.
- JDBC connections running with auto-commit.
- Tests with @Commit or @Rollback(false).
- Non-database effects outside the transaction manager.

Not all leftover data is caused by timeouts. Identify the exact root cause before choosing cleanup.

## 17. Ways to write tests by goal

| Goal | Approach | Reason |
|---|---|---|
| Test service logic writing to database inside test transaction | assertTimeout or @Timeout SAME_THREAD | Keeps the call on the test thread |
| Only measure duration of a pure Java computation | assertTimeout or an appropriate benchmark | No transaction resources need propagation |
| Test a service running asynchronously | Call via executor, await Future, and clean up data independently | Worker has its own transaction boundary |
| Test preemptive timeout with write operations | Uniquely identified data, wait for worker to stop, REQUIRES_NEW cleanup | Does not rely on test thread rollback |
| Test REQUIRES_NEW transactions | Integration test with database verifying independent commit | Child transaction can survive outer rollback |
| Test HTTP requests running on server threads | Send request via MockMvc or HTTP client and verify actual outcome | Server requests have their own execution/transaction context |
| Test non-database side effects | Mocks/fakes or dedicated test infrastructure | Database rollback does not revert side effects |

## 18. Common mistakes

### Using assertTimeoutPreemptively in a test with @Transactional

The callback runs on another thread and does not join the test's transaction. Repositories can open their own transaction and commit.

**How to handle:** use assertTimeout or same-thread timeouts when appropriate; if preemptive is mandatory, create isolated data and clean up independently.

### Assuming @Transactional applies to every thread

The annotation does not automatically propagate transaction context to executors or worker threads.

**How to handle:** design transactions for workers explicitly and inspect data after workers complete.

### Thinking Future.get() makes the worker join the test's transaction

Future.get only waits for the result. It does not transfer the transaction from the calling thread to the task-executing thread.

**How to handle:** manage worker transactions and clean up according to their separate transaction boundary.

### Using REQUIRES_NEW and expecting outer rollback to delete the data

REQUIRES_NEW can commit independently. Rolling back the outer transaction does not undo an already-committed transaction.

**How to handle:** verify independent effects and delete them using a separate cleanup transaction.

### Cleaning up before the worker actually stops

Timeout or cancel does not guarantee the worker has finished. The worker may write data after cleanup runs.

**How to handle:** await termination or use isolated test resources and verify no worker remains active before cleanup.

### Cleanup joining the test transaction and getting rolled back

If @AfterEach uses TransactionTemplate with REQUIRED while the test transaction is still active, the delete operation can join that transaction. When Spring rolls back the test transaction, it rolls back the cleanup too.

**How to handle:** use an independent cleanup transaction with REQUIRES_NEW or design tests without a test-managed transaction for worker data.

### Using @DirtiesContext to fix leftover data

@DirtiesContext removes the ApplicationContext from cache; it does not delete committed records in the database.

**How to handle:** clean up the database or use a separate database/schema. Only use @DirtiesContext when needing to reset context state.

### Assuming interrupt always stops a task

A task can ignore interruption or be in an operation that does not respond to interrupts.

**How to handle:** design cancellable tasks, control executors, and avoid cleaning up while a worker can still write.

## 19. Workflow for choosing timeouts and transactions for a new test

1. **Determine whether the test writes data:** if there is no persistence or side effect, transaction risks may not apply.
2. **Identify the transaction owner:** test method, service proxy, repository, worker thread, or message listener?
3. **Identify the executing thread:** does the callback run on the same thread or switch to another thread?
4. **Check timeout mode:** assertTimeout, assertTimeoutPreemptively, @Timeout SAME_THREAD/SEPARATE_THREAD, or globally configured timeout.
5. **Identify propagation:** REQUIRED, REQUIRES_NEW, or which separate transaction boundary is used?
6. **Choose an appropriate timeout:** prefer approaches that keep the thread if test-managed transaction rollback is needed.
7. **If running asynchronously:** use isolated test data, wait for workers to complete, and have independent cleanup.
8. **Verify database state:** query after the transaction using a new persistence context/transaction when needing to prove commit or rollback.
9. **Check other side effects:** messages, files, HTTP requests, and caches need dedicated cleanup or test doubles.

### Pre-writing checklist template

~~~text
Test-managed transaction:
[yes / no]

Callback execution thread:
[test thread / worker thread]

Timeout:
[assertTimeout / assertTimeoutPreemptively / @Timeout mode]

Transaction of the write operation:
[joins test transaction / independent transaction / auto-commit]

Data that may commit outside the test transaction:
[data type and test identifier]

Cleanup:
[cleanup approach and committing transaction]

Worker termination condition:
[how to verify the task is no longer writing data]
~~~

This template helps test authors avoid assuming the @Transactional annotation will clean up every change created during the test.

## 20. References

- [Spring Framework Reference: TestContext Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework Reference: Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework API: TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [JUnit 5 User Guide: Assertions — Timeout Assertions](https://junit.org/junit5/docs/current/user-guide/#writing-tests-assertions)
- [JUnit 5 User Guide: Timeout](https://junit.org/junit5/docs/current/user-guide/#writing-tests-declarative-timeouts)

## Conclusion

Spring Test binds test-managed transactions to the thread executing the test. When preemptive timeouts or asynchronous tasks shift write operations to another thread, those operations do not automatically join the test's transaction and can commit independently. Rolling back the test thread cannot revert another already-committed transaction. For tests needing automatic rollback, prefer timeouts that stay on the same thread; for tests genuinely needing worker threads, use isolated data, manage worker termination, and clean up in an independent transaction.

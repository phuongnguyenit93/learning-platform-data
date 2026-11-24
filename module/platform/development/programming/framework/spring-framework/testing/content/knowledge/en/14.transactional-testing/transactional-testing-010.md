# Propagation of invoked code and the risk of creating independent transactions

The Spring TestContext Framework can open a test-managed transaction for each test method annotated with `@Transactional`. By default, this transaction is rolled back when the method ends. That mechanism is very useful for isolating test data: a test can write data, read it back, and check results without leaving changes in the database.

However, the test's rollback only affects the test transaction it manages. Application code invoked inside the test can declare a different propagation, suspend the current transaction, or open an independent transaction. If the independent transaction commits, the test's rollback cannot revert those already-committed changes. This is a common reason test data still remains in the database after a test has finished.

## 1. What is a test-managed transaction?

When the Spring TestContext Framework detects `@Transactional` on a test class or test method, `TransactionalTestExecutionListener` can start a test-managed transaction before the test method runs. After the method ends, Spring rolls back the transaction by default.

Example:

```java
@SpringBootTest
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void savesAccount() {
        accountRepository.save(new Account("ACC-01"));

        assertTrue(accountRepository.findById("ACC-01").isPresent());
    }
}
```

While the test runs, save and query operations join the same test transaction if they use the same transaction manager and transactional resource. The assertion can read the newly saved record. When the test method ends, Spring rolls back the transaction, so the record is not committed to the database.

You can picture it as:

```text
Spring TestContext
       |
       v
Starts test-managed transaction T0
       |
       v
Runs test method
       |
       +--> accountRepository.save(...)
       |
       +--> accountRepository.findById(...)
       |
       v
Test method finishes
       |
       v
Rolls back T0
       |
       v
Data in T0 is not committed
```

The test transaction is managed by the Spring TestContext Framework. It differs from a transaction opened and committed by a service on its own. Having `@Transactional` on the test does not mean every database operation across the entire system is guaranteed to reside within T0.

## 2. Propagation determines which transaction invoked code joins

Propagation is the policy defining how a transactional method interacts with an existing transaction at the time it is invoked. Spring declares these policies via `Propagation` in `@Transactional`.

Example:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void updateAccount() {
    // ...
}
```

When this method is invoked through a Spring transaction proxy, Spring checks whether a suitable transaction already exists. Depending on propagation, the method joins the current transaction, suspends it, or creates a new transaction.

Main propagation modes:

| Propagation | When a transaction already exists | When no transaction exists |
|---|---|---|
| `REQUIRED` | Joins the current transaction | Creates a new transaction |
| `REQUIRES_NEW` | Suspends the current transaction and creates a new transaction | Creates a new transaction |
| `SUPPORTS` | Joins the current transaction | Runs without a transaction |
| `NOT_SUPPORTED` | Suspends the current transaction and runs without a transaction | Runs without a transaction |
| `MANDATORY` | Joins the current transaction | Throws an error because no transaction exists |
| `NEVER` | Throws an error because a transaction already exists | Runs without a transaction |
| `NESTED` | Participates in the current transaction via a savepoint, if the transaction manager supports it | Creates a new transaction |

This table describes general semantics. Actual behavior also depends on the transaction manager, resource type, proxy invocation, and capabilities of the transaction platform.

## 3. REQUIRED: invoked code joins the test transaction

`REQUIRED` is the default propagation of `@Transactional`. If a transaction already exists, the method joins it. If none exists, Spring starts a new transaction.

Example:

```java
@Service
public class AccountService {

    private final AccountRepository accountRepository;

    public AccountService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void createAccount(String accountId) {
        accountRepository.save(new Account(accountId));
    }
}
```

Test:

```java
@SpringBootTest
@Transactional
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void createsAccountInsideTestTransaction() {
        accountService.createAccount("ACC-02");

        assertTrue(accountRepository.findById("ACC-02").isPresent());
    }
}
```

If `accountService` is invoked through a Spring proxy and uses the same transaction manager as the test, `createAccount()` joins T0 opened by the test. The repository also joins T0. When the test ends, rolling back T0 reverts the save operation.

```text
Test-managed transaction T0
       |
       +--> AccountService.createAccount() [REQUIRED]
       |        |
       |        +--> AccountRepository.save() [REQUIRED]
       |
       v
Test finishes
       |
       v
Rolls back T0
```

This is the case where test rollback works as many people expect: invoked application code joins the same test transaction rather than committing an independent transaction on its own.

## 4. REQUIRES_NEW: creating an independent transaction

`REQUIRES_NEW` always requires a new transaction. If a transaction already exists, Spring suspends the current transaction, creates a new transaction for the invoked method, and then resumes the old transaction once the new transaction finishes.

Example:

```java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String event) {
        auditRepository.save(new AuditRecord(event));
    }
}
```

Another service calls the audit service:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditService auditService;

    public OrderService(
            OrderRepository orderRepository,
            AuditService auditService
    ) {
        this.orderRepository = orderRepository;
        this.auditService = auditService;
    }

    @Transactional
    public void createOrder(String orderId) {
        orderRepository.save(new Order(orderId));
        auditService.record("Created order " + orderId);
    }
}
```

Suppose the test method has test-managed transaction T0 and calls `orderService.createOrder()`:

1. `OrderService.createOrder()` uses `REQUIRED`, so it joins T0.
2. `AuditService.record()` uses `REQUIRES_NEW`, so Spring suspends T0.
3. Spring starts transaction T1 for `record()`.
4. `AuditRepository.save()` joins T1.
5. When `record()` completes normally, T1 commits.
6. Spring resumes T0 and `createOrder()` finishes.
7. After the test method, Spring rolls back T0.

```text
Test-managed transaction T0
       |
       +--> OrderService.createOrder() [REQUIRED]
       |        |
       |        +--> saves Order in T0
       |        |
       |        +--> AuditService.record() [REQUIRES_NEW]
       |                   |
       |                   +--> Suspends T0
       |                   |
       |                   +--> Starts T1
       |                   |
       |                   +--> saves AuditRecord in T1
       |                   |
       |                   +--> Commits T1
       |                   |
       |                   +--> Resumes T0
       |
       v
Test finishes
       |
       v
Rolls back T0

Result:
  Order       -> rolled back
  AuditRecord -> committed, still remains
```

Point to remember: rolling back T0 cannot undo an already-committed T1. Audit data can still persist even though the test method is marked for rollback.

## 5. Example demonstrating the risk of leftover data

Suppose an application has two tables `orders` and `audit_log`. The service creates an order and writes an audit log in an independent transaction:

```java
@Service
public class AuditService {

    private final JdbcTemplate jdbcTemplate;

    public AuditService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordOrderCreated(String orderId) {
        jdbcTemplate.update(
                "insert into audit_log(order_id, event) values (?, ?)",
                orderId,
                "ORDER_CREATED"
        );
    }
}
```

```java
@Service
public class OrderService {

    private final JdbcTemplate jdbcTemplate;
    private final AuditService auditService;

    public OrderService(
            JdbcTemplate jdbcTemplate,
            AuditService auditService
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.auditService = auditService;
    }

    @Transactional
    public void createOrder(String orderId) {
        jdbcTemplate.update(
                "insert into orders(id) values (?)",
                orderId
        );

        auditService.recordOrderCreated(orderId);
    }
}
```

Test:

```java
@SpringBootTest
@Transactional
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void createsOrderAndAuditRecord() {
        orderService.createOrder("ORDER-100");

        Integer orderCount = jdbcTemplate.queryForObject(
                "select count(*) from orders where id = ?",
                Integer.class,
                "ORDER-100"
        );

        Integer auditCount = jdbcTemplate.queryForObject(
                "select count(*) from audit_log where order_id = ?",
                Integer.class,
                "ORDER-100"
        );

        assertEquals(1, orderCount);
        assertEquals(1, auditCount);
    }
}
```

While the test runs, both queries can see their respective records: the order is inside T0, and the audit record was already committed in T1. When the test method finishes, Spring rolls back T0. The record in `orders` disappears, while the audit record remains saved.

If this test runs multiple times with the same `ORDER-100` code, later runs may fail due to leftover audit data from the previous run. This is a common data isolation failure when tests rely solely on the outermost transaction's rollback.

This example assumes the tables already exist and the database supports appropriate transactions. Across different JPA, JDBC, or transaction manager setups, repository and resource configurations must be adapted to the application.

## 6. NOT_SUPPORTED: invoked code runs outside the current transaction

`NOT_SUPPORTED` tells Spring to suspend the existing transaction and execute the method without a transaction. If the method writes data, the writes may occur through the invoked component's own transaction management or the resource's autocommit mode.

Example:

```java
@Service
public class ExternalSyncService {

    private final JdbcTemplate jdbcTemplate;

    public ExternalSyncService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void synchronize(String key) {
        jdbcTemplate.update(
                "insert into sync_log(sync_key) values (?)",
                key
        );
    }
}
```

If test-managed transaction T0 exists and `synchronize()` is invoked through a proxy, T0 is suspended while the method runs. The write does not participate in T0, so rolling back T0 does not automatically revert that operation.

However, do not conclude that `NOT_SUPPORTED` always auto-commits every SQL statement. The method simply has no current Spring transaction; specific commit behavior depends on the resource and underlying components. For instance, another repository called inside could open a new `REQUIRED` transaction since no current transaction exists. With a JDBC connection in autocommit mode, each statement can commit immediately.

Therefore, when `NOT_SUPPORTED` is in a test's call path, inspect how write operations are managed. Do not expect T0's rollback to clean up changes made while T0 was suspended.

## 7. NESTED: nested transactions and savepoints

`NESTED` requests a nested transaction scope inside the current transaction. With a transaction manager and resource that support savepoints, Spring can create a savepoint to roll back the nested work while allowing the outer transaction to continue.

Conceptual example:

```text
Outer transaction T0
       |
       +--> Operation A
       |
       +--> Savepoint S1
       |       |
       |       +--> NESTED method
       |       |
       |       +--> Roll back to S1 if needed
       |
       +--> Operation B
       |
       v
Commit or roll back T0
```

If the entire T0 is a test-managed transaction and rolls back at the end of the test, remaining changes in T0 also roll back. `NESTED` is not equivalent to `REQUIRES_NEW`: a nested transaction relies on a savepoint within the outer transaction, whereas `REQUIRES_NEW` has an independent transaction with its own commit.

Support for `NESTED` depends on the transaction manager. Some JDBC transaction managers support savepoints; do not assume all JPA configurations or all transaction platforms fully support nested transactions. Check the application's actual transaction manager and resource types.

## 8. SUPPORTS, MANDATORY, and NEVER in tests

The remaining three propagation modes can also affect call paths from tests:

**SUPPORTS** joins the current transaction if one exists. If none exists, the method runs without a transaction. When test-managed transaction T0 exists, the method usually joins T0 if using the same transaction manager.

**MANDATORY** requires a current transaction to exist. When called in a test with T0, it can join T0. If the test has not opened a transaction and no other transaction exists, Spring throws a transaction state error.

**NEVER** requires that no current transaction exists. If a test is running inside T0, calling a `NEVER` method through a proxy causes an error because a transaction already exists. If no transaction exists, the method runs without a transaction.

Example table:

| Test setup | Service propagation | Expected outcome |
|---|---|---|
| Test has `@Transactional` | `SUPPORTS` | Joins T0 |
| Test has no transaction | `SUPPORTS` | Runs without a transaction |
| Test has `@Transactional` | `MANDATORY` | Joins T0 |
| Test has no transaction | `MANDATORY` | Throws error due to missing transaction |
| Test has `@Transactional` | `NEVER` | Throws error because a transaction is active |
| Test has no transaction | `NEVER` | Runs without a transaction |

The cases above assume the call is handled by Spring's transaction interceptor. If the call does not pass through a proxy, propagation annotations on the method may not be applied.

## 9. Distinguishing test method propagation from service method propagation

Do not confuse `@Transactional` on a test method with `@Transactional` on application code.

The Spring TestContext Framework has specific limitations for propagation declared directly on a test method or test class. In test-managed transactions, the supported propagation modes for test annotations are `NOT_SUPPORTED` and `NEVER`; other values should not be used to simulate service transactions.

For example, this is not the right way to ask a test method to create an independent transaction on its own:

```java
@Test
@Transactional(propagation = Propagation.REQUIRES_NEW)
void testSomething() {
    // Do not use this propagation to simulate a service's independent transaction
}
```

To test application code that uses `REQUIRES_NEW`, let the test-managed transaction create the outer transaction and call a Spring bean that has a `@Transactional(propagation = REQUIRES_NEW)` method. It is the invoked application method that requests the independent transaction.

Separation of responsibilities:

- Annotations on the test class/method define the test-managed transaction and the test's rollback/commit policy.
- Annotations on services/repositories define business propagation.
- The transaction manager coordinates actual transactions.
- The database determines which data has been committed and remains after the test finishes.

## 10. Propagation only takes effect when the call goes through a Spring proxy

In Spring's default proxy mode, transactions are applied when calls pass through a Spring-created proxy. An internal call from one method to another within the same object (*self-invocation*) bypasses the proxy, so annotations on the target method may not be applied.

Misleading example:

```java
@Service
public class AuditService {

    public void recordFromOrder(String orderId) {
        record(orderId);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId) {
        // Record audit entry
    }
}
```

If `recordFromOrder()` is called through a proxy but internally calls `this.record()` directly, the `record()` call is a self-invocation. The default transaction interceptor does not intercept that internal call; thus, you cannot rely on the `REQUIRES_NEW` annotation to reliably create T1.

A clearer structure is placing the independent method in a separate bean:

```java
@Service
public class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId) {
        // Record audit entry in a separate transaction
    }
}
```

```java
@Service
public class OrderService {

    private final AuditWriter auditWriter;

    public OrderService(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @Transactional
    public void createOrder(String orderId) {
        // Save order in the current transaction
        auditWriter.record(orderId);
    }
}
```

`OrderService` calls `AuditWriter` through an injected bean, so the call can pass through the transaction proxy and apply `REQUIRES_NEW`.

If propagation appears not to work, inspect not just the annotation, but also the call path, whether the bean is managed by Spring, and whether the method is truly invoked through a proxy.

## 11. New transactions can consume additional database connections

When `REQUIRES_NEW` is invoked while T0 holds a connection, Spring normally has to keep T0's resource in a suspended state and acquire another resource for T1. With JDBC, this can require an additional connection from the pool.

If many requests or tests run concurrently, with each thread holding one connection for its outer transaction while waiting for another connection for a `REQUIRES_NEW` transaction, a small connection pool can be exhausted. This is a common cause of hangs or timeouts when systems use nested independent transactions heavily.

Therefore:

- Use `REQUIRES_NEW` when business requirements genuinely demand an independent commit, such as audit logging that must persist even if the outer business transaction rolls back.
- Check connection pool size when multiple outer transactions might simultaneously open new transactions.
- Avoid overusing `REQUIRES_NEW` for every auxiliary operation.
- In tests, observe both leftover data and resource release after tests finish.

Not every transaction manager handles connections identically, yet the resource cost of independent transactions must be accounted for.

## 12. Impact of exceptions and rollback rules

Propagation determines which transaction is used; rollback rules determine whether that transaction ends with commit or rollback when an error occurs.

With `REQUIRES_NEW`, transaction T1 has an outcome independent of T0. If the method inside T1 throws a runtime exception and the error propagates out of the transactional boundary, T1 typically rolls back by default. If T1 completes normally, it can commit before T0 continues.

If an error from the `REQUIRES_NEW` method escapes outward, the caller in T0 may fail as well. Then T0 may roll back when the test ends or be marked rollback-only depending on the handling path. However, if the exception is caught and handled, T0 can continue; that does not change whether T1 already rolled back or committed.

Example:

```java
@Transactional
public void processOrder(String orderId) {
    orderRepository.save(new Order(orderId));

    try {
        auditWriter.record(orderId);
    } catch (AuditException ex) {
        // Business decision: continue or throw error
    }
}
```

If `auditWriter.record()` already committed T1 and returned normally, a subsequent rollback of T0 cannot undo the audit record. If T1 rolled back due to an error, T0 can continue if the error is handled and the outer transaction has not been marked rollback-only.

To test this behavior, clearly define business expectations: must the audit persist even if the order rolls back, or must audit and order succeed/fail together? The answer determines which propagation fits.

## 13. Why do tests with rollback still leave data behind?

There are several common causes:

| Cause | Why test rollback does not clean it up | How to investigate |
|---|---|---|
| Service uses `REQUIRES_NEW` | The new transaction committed independently | Find transactional methods along the call path |
| Service uses `NOT_SUPPORTED` | T0 is suspended; writes may be managed outside T0 | Identify the actual transaction of the write statement |
| Repository or component opens its own new transaction | Writes may commit before the test rolls back | Inspect transaction managers and propagation on called beans |
| Code runs on another thread | The new thread does not automatically join the test transaction bound to the original thread | Check `@Async`, executors, futures, or callbacks |
| Data was already committed before the test | Rolling back T0 does not affect pre-existing data | Check fixtures and initial database state |
| Test uses a different transaction manager | T0 does not govern resources of another transaction manager | Check `transactionManager` and datasource configuration |
| Self-invocation within the same bean | Transaction annotation may not be applied by a proxy | Check self-invocation and bean boundaries |

Spring's imperative transactions are normally bound to the current thread. A task running via an executor or `@Async` does not automatically join the calling thread's test-managed transaction. If that task opens and commits its own transaction, the test rollback cannot clean up committed changes. Tests must also wait for asynchronous tasks to complete before checking data or cleaning up.

With reactive transactions, transaction context is propagated via Reactor Context rather than relying purely on thread-locals. Do not blindly apply thread assumptions from imperative transactions to reactive flows.

## 14. Cleaning up data written by independent transactions

If a test needs to verify `REQUIRES_NEW`, independently committed data must be cleaned up with a dedicated strategy. Rolling back T0 is not enough.

One approach is using `@AfterTransaction` to clean up after the test-managed transaction has finished. The cleanup method calls a dedicated bean with its own transaction:

```java
@Service
public class AuditCleanupService {

    private final JdbcTemplate jdbcTemplate;

    public AuditCleanupService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void deleteByOrderId(String orderId) {
        jdbcTemplate.update(
                "delete from audit_log where order_id = ?",
                orderId
        );
    }
}
```

```java
@SpringBootTest
@Transactional
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private AuditCleanupService auditCleanupService;

    private final String orderId = "ORDER-100";

    @Test
    void createsOrderAndAuditRecord() {
        orderService.createOrder(orderId);

        // Inspect data while the test is running
    }

    @AfterTransaction
    void cleanCommittedAuditRecord() {
        auditCleanupService.deleteByOrderId(orderId);
    }
}
```

`@AfterTransaction` is called after the test-managed transaction finishes. Thus, deleting the audit record is not part of the rolled-back T0. The cleanup service opens its own transaction and commits the delete.

In real projects, test identifiers should be unique so cleanup does not delete another test's data. Where possible, use UUIDs or namespaced keys per test run. With parallel tests, cleanup must target only data created by that test itself.

Other options include:

- Using cleanup scripts executed outside the test transaction.
- Resetting the test database or schema after the test suite.
- Using a dedicated database container for the test run and destroying it upon completion.
- Using fixtures with unique identifiers and deleting them via an independent cleanup transaction.

Do not rely on `@Sql` or repository delete without verifying the transaction of the cleanup operation itself. If cleanup accidentally joins T0, the delete statement will also roll back and the independent data will remain.

## 15. Testing propagation behavior intentionally

When writing tests for propagation, identify which transaction is active at each step and what data is expected to persist after the test finishes.

A useful test scenario can be divided into three parts:

1. Call the service inside a test-managed transaction.
2. Confirm data is readable while the test is running.
3. After the test transaction ends, verify committed state using a test or query running outside the corresponding transaction.

You can use Spring Test's `TestTransaction` to control the test-managed transaction inside the test method. For example, `flagForCommit()` and `end()` let you flag the test transaction to commit and end it; `start()` can begin a new test-managed transaction if conditions permit. This is a tool for controlling the test transaction, not a replacement for service propagation.

Conceptual example:

```java
@Test
@Transactional
void explicitlyEndsTestTransaction() {
    orderService.createOrder("ORDER-200");

    TestTransaction.flagForRollback();
    TestTransaction.end();

    // T0 has ended here.
    // State can be queried outside T0 in an appropriate way.
}
```

If you want to inspect data committed by `REQUIRES_NEW`, observe after T0 ends or from an independent transaction/connection. A query running inside T0 before it ends may be affected by snapshot isolation or persistence context caching and may not always reflect committed state from another transaction as expected.

There is no need to use `TestTransaction` for every test. It is helpful when tests need to inspect the boundary clearly before and after the test transaction ends.

## 16. How to trace propagation along the call path

When a test calls a service and data still remains after rollback, trace the entire call chain:

```text
Test method (@Transactional)
       |
       v
Service A (@Transactional)
       |
       +--> Repository A
       |
       +--> Service B (@Transactional)
                  |
                  +--> Repository B
                  |
                  +--> Async worker?
```

At each step, note:

- Whether the method is called through a Spring proxy.
- What the method's propagation is.
- Whether an active transaction exists at the time of invocation.
- Which transaction manager governs the resource.
- Whether the method spawns a thread or asynchronous task.
- Whether the transaction is committed, rolled back, or merely suspended.
- Whether any operation sits outside the test transaction.

For instance, if Service A uses `REQUIRED`, Service B uses `REQUIRES_NEW`, and Repository B joins the current transaction, data in Repository B is written in Service B's new transaction. If Service B commits, the test's rollback only reverts the portion inside the outer transaction.

If Service B uses `NOT_SUPPORTED`, the outer transaction is suspended while Service B runs. Continue tracing down to the repository to see whether it opens its own transaction or uses autocommit. Looking only at the annotation on Service B is not enough to conclude how data will commit.

## 17. Choosing propagation based on business requirements

Do not choose propagation merely to make tests easier to write. Determine the data consistency relationship required by business rules.

| Requirement | Commonly appropriate propagation |
|---|---|
| All operations must commit or roll back together | `REQUIRED` |
| A recording step must commit independently of the outer business flow | Consider `REQUIRES_NEW` |
| A processing step must not run inside the current transaction | Consider `NOT_SUPPORTED` |
| A sub-operation can roll back to a savepoint inside the outer transaction | `NESTED`, if supported by the transaction manager |
| Method can run inside or outside a transaction | `SUPPORTS` |
| Method strictly requires a transaction from the caller | `MANDATORY` |
| Method must run when no transaction exists | `NEVER` |

For example, independent audit logging may require `REQUIRES_NEW` if rules mandate that the audit persists even when the main business transaction rolls back. Yet if the audit record only makes sense when the order commits, `REQUIRED` may fit better so both succeed or fail together.

Propagation is a decision about consistency and commit boundaries, not merely a technical knob.

## 18. Diagnostic workflow when test rollback does not clean up all data

When data still persists after a test with `@Transactional`, investigate in sequence:

1. **Verify the test-managed transaction:** check whether the test has transaction management and rollback governed by Spring TestContext.
2. **Identify the transaction manager:** check the datasource or resource the test is using.
3. **Trace invoked beans:** find all `@Transactional` methods across the entire call path.
4. **Read propagation:** pay attention to `REQUIRES_NEW`, `NOT_SUPPORTED`, and propagations that require or forbid transactions.
5. **Check proxies:** determine whether calls pass through a Spring proxy or are self-invocations.
6. **Check thread boundaries:** check whether code runs in an executor, `@Async`, or another-thread callback.
7. **Locate actual commits:** find where independent transactions finish normally and commit.
8. **Choose appropriate cleanup:** use `@AfterTransaction`, a separate cleanup transaction, or database reset.
9. **Rerun multiple times:** ensure the test leaves no data that causes subsequent runs to fail.

Once you understand the propagation of invoked code, you can explain why a test-managed transaction rolls back yet some data still remains. `REQUIRED` normally lets application code join the test transaction; `REQUIRES_NEW` can commit independently; `NOT_SUPPORTED` suspends the test transaction; and `NESTED` relies on savepoints if the resource supports them. Properly checking transaction boundaries, proxies, and threads helps design tests with suitable cleanup and prevents data leaks across runs.


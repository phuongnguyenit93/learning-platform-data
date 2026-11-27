# Distinguishing Test Rollbacks from Real Post-Commit Behavior

Spring Data JDBC is commonly tested using integration tests that run inside a transaction. This automatically rolls back test data after every test and reduces manual database cleanup. However, transactions managed by the test framework can mask a service's real commit behavior.

For example, a **`@DataJdbcTest`** saves an aggregate, reads it back, and passes. The test still rolls back its entire transaction at the end of the method. That proves the repository can read and write inside the test's transaction, yet does not prove the data actually committed and became visible to another transaction.

To verify real production behavior, distinguish:

- **Test-managed transaction:** a transaction opened and closed around a test method by Spring TestContext.
- **Application transaction:** a transaction opened by a service or repository via **`@Transactional`**.
- **Actual commit:** a physical transaction committed so data becomes durable per database semantics.
- **Test-isolation rollback:** data cleanup performed by the test framework after assertions finish.

This lesson explains default test-slice transactions, how application transactions join test transactions, how to test real commits and rollbacks, how to use **`@Commit`**, **`@Rollback`**, and **`TestTransaction`**, and scenarios that easily produce misleading test results.

## 1. Why Do Tests Roll Back by Default?

Spring TestContext supports running test methods inside transactions. Test slices such as **`@DataJdbcTest`** are typically configured with transactions so database changes roll back after the test completes.

Example:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void savesAndLoadsAnOrder() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("SO-100")
        );

        PurchaseOrder loaded = orders.findById(saved.getId())
            .orElseThrow();

        assertEquals("SO-100", loaded.getOrderNumber());
    }
}
~~~

The test passes even though the data rolls back immediately after the method exits. This is desirable for repository tests: every test starts cleaner without leaving rows behind for subsequent tests.

### 1.1. Test Rollback Is Not Business Rollback

Suppose a service has a transaction:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createOrder(String orderNumber) {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create(orderNumber)
        );
        return saved.getId();
    }
}
~~~

If a test invokes the service inside the transaction created by **`@DataJdbcTest`**, the service's **`REQUIRED`** transaction normally joins the existing transaction. When the test ends, the test framework rolls back that transaction.

The test proves the service can write data inside the active transaction. It does not prove that an independently opened service transaction will commit when returning during a production request.

### 1.2. Test Slices and SpringBootTest

**`@DataJdbcTest`** is a test slice focused on Spring Data JDBC and is typically marked transactional. Database changes roll back after each test under the slice's default configuration.

**`@SpringBootTest`** does not automatically apply the same rollback semantics to every test method. Only if the test is annotated with **`@Transactional`** does Spring TestContext manage a test transaction per that configuration. Otherwise, transactions opened by services commit just as in normal application execution.

Do not infer behavior from the annotation name alone. Check whether the test class has a test-managed transaction and which transaction manager is selected.

## 2. Three Transaction Scopes to Distinguish

In an integration test, multiple logical transaction scopes can exist:

~~~text
Spring TestContext
    |
    +-- Test-managed transaction T_test
            |
            +-- Test method
                    |
                    +-- OrderService @Transactional(REQUIRED)
                    |       |
                    |       +-- Repository.save()
                    |
                    +-- Repository.findById()
~~~

If the service uses the same transaction manager and `REQUIRED` propagation, it joins `T_test`. The service does not commit independently when returning.

| Scope | Managed By | When It Ends |
|---|---|---|
| Test-managed transaction | Spring TestContext | After the test method; rolls back by default |
| New application transaction | Spring transaction interceptor | When the service method exits |
| Transaction joined via `REQUIRED` | Transaction manager of the active transaction | At the same time the outer physical transaction ends |
| `REQUIRES_NEW` | Service's transaction manager | Commits/rolls back independently when the inner method exits |

Assertions running inside the same transaction can read uncommitted data written by that transaction itself. That does not prove another connection or another application can see the data.

## 3. Testing Repositories Inside the Test Transaction

For repository tests, default rollback is usually appropriate:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void persistsAnOrderWithinTheTestTransaction() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("SO-200")
        );

        assertTrue(orders.findById(saved.getId()).isPresent());
    }
}
~~~

This test verifies mapping and repository behavior inside the test transaction. It does not need committed data to fulfill its goal.

### 3.1. Data Inside a Transaction Is Not Necessarily Committed

A transaction can normally read back its own uncommitted writes. Thus, the following snippet does not prove a commit occurred:

~~~java
orders.save(order);
assertTrue(orders.findById(order.getId()).isPresent());
~~~

Both calls can share the same connection and transaction. To test post-commit visibility, complete the transaction via commit and read in a fresh transaction or connection.

## 4. Testing Real Service Commits with NOT_SUPPORTED

One clear approach is disabling the test-managed transaction for the test method. Then the service opens and closes its own transaction per its annotations.

~~~java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@DataJdbcTest
@Import(OrderService.class)
class OrderServiceCommitTest {

    @Autowired
    OrderService orderService;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void serviceCommitsBeforeReturning() {
        Long id = orderService.createOrder("SO-300");

        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM purchase_orders WHERE id = ?",
            Integer.class,
            id
        );

        assertEquals(1, count);
    }
}
~~~

With **`NOT_SUPPORTED`**, the test method does not run in a test-managed transaction. When **`orderService.createOrder()`** runs, the transaction opened by the service commits on normal return. The subsequent query reads already-committed data.

Notes:

- The test slice still supplies database and repository infrastructure.
- Import the service and its dependencies into the test context.
- The service must use the transaction manager for the DataSource under test.
- Committed data may persist after the test since there is no test transaction to roll back.
- Clean up data using fixture cleanup, isolated schemas, or a dedicated test database.

Never run such tests against a shared database without an explicit cleanup strategy.

## 5. Testing Real Service Rollback

To prove a service rolls back on business failure, let the service manage its own transaction and inspect the database after the method throws an exception.

Service:

~~~java
@Service
public class CheckoutService {

    private final PurchaseOrderRepository orders;
    private final InventoryRepository inventory;

    public CheckoutService(
            PurchaseOrderRepository orders,
            InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void checkout(CreateOrderCommand command) {
        orders.save(PurchaseOrder.create(command));
        inventory.decrease(command.productId(), command.quantity());

        throw new IllegalStateException("Simulated failure");
    }
}
~~~

Test:

~~~java
@DataJdbcTest
@Import(CheckoutService.class)
class CheckoutRollbackTest {

    @Autowired
    CheckoutService checkout;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void rollsBackWritesWhenServiceFails() {
        CreateOrderCommand command = sampleCommand();

        assertThrows(
            IllegalStateException.class,
            () -> checkout.checkout(command)
        );

        Integer orderCount = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM purchase_orders WHERE order_number = ?",
            Integer.class,
            command.orderNumber()
        );

        assertEquals(0, orderCount);
    }
}
~~~

Because the test has no enclosing transaction, **`checkout()`**'s transaction is opened and rolled back by the Spring transaction interceptor when the runtime exception escapes the method. The subsequent query runs outside the rolled-back transaction and confirms the row does not exist.

To test multi-table rollback, query the state of every affected table or repository. Checking only the order table is insufficient if the use case also updates inventory, audit, or outbox tables.

### 5.1. Testing Checked Exceptions

By default, Spring rolls back on **`RuntimeException`** and **`Error`**. Checked exceptions do not automatically trigger rollback under default rules.

If business rules require rollback on a checked exception:

~~~java
@Transactional(rollbackFor = InventoryException.class)
public void checkout(CreateOrderCommand command)
        throws InventoryException {
    orders.save(PurchaseOrder.create(command));
    inventory.reserve(command);
    throw new InventoryException("Reservation failed");
}
~~~

Integration tests should verify the exact rollback rule:

1. Disable the test-managed transaction.
2. Call the service and assert the checked exception is thrown.
3. Query all involved tables.
4. Confirm data rolled back.

If `rollbackFor` is omitted, tests can expose that data actually committed despite the checked exception, depending on how the exception exited the transaction boundary.

## 6. Using @Commit and @Rollback(false)

When you want a test-managed transaction to commit at test end, you can use **`@Commit`**:

~~~java
@DataJdbcTest
class CommittedRepositoryTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    @Commit
    void commitsTestTransaction() {
        orders.save(PurchaseOrder.create("SO-400"));
    }
}
~~~

**`@Commit`** clearly states that the test-managed transaction should commit when the test finishes. **`@Rollback(false)`** has the equivalent meaning:

~~~java
@Test
@Rollback(false)
void commitsTestTransaction() {
    // ...
}
~~~

By default, test-managed transactions roll back. **`@Rollback`** configures that behavior; **`@Commit`** is the dedicated annotation for committing.

### 6.1. Assertions Inside the Test Run Before End-of-Method Commit

With **`@Commit`**, the transaction normally commits only after the test method returns. Therefore, assertions inside the method still execute before the commit.

When you need to assert after commit, use **`TestTransaction`** to explicitly end the transaction before querying:

~~~java
@DataJdbcTest
class ExplicitTestCommitTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Transactional
    void commitsBeforeCheckingFromOutsideTheTestTransaction() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("SO-500")
        );

        TestTransaction.flagForCommit();
        TestTransaction.end();

        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM purchase_orders WHERE id = ?",
            Integer.class,
            saved.getId()
        );

        assertEquals(1, count);
    }
}
~~~

**`TestTransaction.flagForCommit()`** marks the test transaction to commit upon completion; **`TestTransaction.end()`** ends the transaction immediately at the call site. Afterward, the `SELECT` runs outside the committed test transaction.

If further database operations are needed in the same test, call **`TestTransaction.start()`** to begin a new test-managed transaction. Check state with **`TestTransaction.isActive()`** when needed.

### 6.2. Committed Test Data Requires Cleanup

When using **`@Commit`** or **`flagForCommit()`**, data can remain in the database after the test. You must:

- Use a dedicated test database or schema.
- Create data with unique keys to avoid collisions.
- Clean up data via SQL/repository after assertions or reset the schema.
- Stop relying on automatic post-test rollback.

A commit test should retain data only when the test objective genuinely requires post-commit state.

## 7. Using TestTransaction to Test Multiple Phases

**`TestTransaction`** is useful when one test needs to control the test transaction across distinct phases:

~~~java
@Test
@Transactional
void checksStateAcrossCommitAndNewTransaction() {
    PurchaseOrder saved = orders.save(
        PurchaseOrder.create("SO-600")
    );

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertEquals(
        1,
        jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM purchase_orders WHERE id = ?",
            Integer.class,
            saved.getId()
        )
    );

    TestTransaction.start();
    orders.deleteById(saved.getId());
}
~~~

Here:

1. The first test transaction writes the aggregate.
2. The test flags commit and ends the transaction.
3. Assertions verify post-commit data.
4. The test starts a new transaction.
5. Clean up data inside the new transaction; this transaction can roll back when the test ends.

This approach is useful when you want to verify commits while still preserving rollback-based cleanup in a later phase.

## 8. REQUIRES_NEW Can Commit Even When the Test Transaction Rolls Back

A common source of confusion is a service using **`Propagation.REQUIRES_NEW`** while the test already has an open transaction.

~~~java
@Service
public class AuditService {

    private final OrderAuditRepository audits;

    public AuditService(OrderAuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String event) {
        audits.save(new OrderAudit(event));
    }
}
~~~

If the test has transaction `T_test` and invokes the audit service:

1. Spring suspends `T_test`.
2. `AuditService` opens a new physical transaction `T_inner`.
3. `T_inner` commits when the audit method returns.
4. `T_test` resumes.
5. When the test finishes, `T_test` rolls back.

The audit record committed in `T_inner` can still survive. Rolling back the test transaction does not undo an already-committed independent transaction.

This can cause a test slice to leave data behind despite default rollback. Watch out for services using `REQUIRES_NEW`, especially when they write to the same test database.

### 8.1. Intentionally Testing REQUIRES_NEW

When testing independent transaction semantics:

- Create a test with an outer transaction.
- Call the `REQUIRES_NEW` service.
- Confirm the inner transaction result committed.
- Force the outer transaction to roll back.
- Query outside transactions to confirm the inner data still exists.

The test must clean up the independently committed record.

## 9. NESTED and Savepoints in Tests

**`Propagation.NESTED`** uses a savepoint within the active physical transaction if supported by the transaction manager. When the nested scope rolls back to its savepoint, the outer transaction can proceed.

If the outer transaction is the test-managed transaction, all remaining changes still roll back when the test ends.

~~~text
BEGIN T_test
  INSERT order
  SAVEPOINT S1
    INSERT optional_note
  ROLLBACK TO S1
  UPDATE order
ROLLBACK T_test
~~~

After the test:

- The optional note row was rolled back to the savepoint.
- The order change stayed inside `T_test` until test end.
- The final test rollback removed the order change as well.

Do not mistake nested rollback for committing the outer portion. To verify post-commit state, you still must commit the outer transaction.

## 10. Testing Transaction Synchronization and Post-Commit Callbacks

Some code registers callbacks that run after transaction commit, such as via **`TransactionSynchronizationManager`** or event listeners with phase **`AFTER_COMMIT`**.

When the test-managed transaction rolls back by default, `afterCommit` callbacks do not execute as they would in a successful commit. A test that simply invokes a service and ends with rollback proves nothing about post-commit behavior.

Example registering a synchronization:

~~~java
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            // Perform post-commit action.
        }
    }
);
~~~

To test this:

1. Run the test inside a transaction.
2. Verify the callback has not executed before commit.
3. Flag the test transaction for commit.
4. End the transaction.
5. Verify the callback executed.

If the callback publishes a message or calls an external system, use a spy/fake rather than sending real requests in tests. With the outbox pattern, prefer confirming the outbox row commits alongside the aggregate and testing the publisher separately.

## 11. Multiple Transaction Managers in Tests

A Spring Data JDBC application may configure multiple DataSources and transaction managers. Tests must select the right manager to roll back or commit the intended database.

Example:

~~~java
@DataJdbcTest
@Transactional(transactionManager = "ordersTransactionManager")
class OrdersRepositoryTest {
    // ...
}
~~~

If a test touches both orders and inventory, a test-managed transaction bound to `ordersTransactionManager` does not automatically cover inventory manager transactions.

Verify:

- Which DataSource each repository uses.
- Which transaction manager the test transaction uses.
- Whether the service specifies a manager explicitly.
- Whether `REQUIRES_NEW` or independent transactions exist on another database.
- Which data needs commit/rollback and separate cleanup.

Two standard JDBC transaction managers do not form an atomic distributed transaction. Nor can a test prove multi-database atomicity merely by rolling back one manager.

## 12. Preemptive Timeouts Can Break Test Transactions

Spring TestContext transactions are normally bound to the thread executing the test. Certain test framework timeout APIs run code on another thread, such as JUnit's **`assertTimeoutPreemptively`**.

If a test method has a test-managed transaction yet executes code on a different thread, the transaction context does not automatically propagate to that thread. Database operations may run outside the test transaction and commit for real, leaving unexpected data behind.

For tests needing transaction control:

- Avoid preemptive timeouts that run the test body on another thread.
- When timeouts are needed, pick mechanisms that stay on the same thread or manage worker transactions explicitly.
- Clean up data that might commit outside transactions.
- Never assume thread-local transaction context automatically crosses executors or `@Async`.

This is why a seemingly rolled-back test can still leave rows behind if persistence actually executed on another thread.

## 13. Sequences and Generated IDs After Rollback

Rolling back a transaction does not necessarily reclaim allocated sequence or identity values. Many databases allocate sequence values non-transactionally, so gaps in IDs can appear after rollbacks.

Example:

1. Insert receives ID 101.
2. Transaction rolls back.
3. Next insert receives ID 102.

This gap does not mean row ID 101 committed. In tests, assert row presence or business fields rather than assuming contiguous IDs.

Similarly, DDL and certain database statements have distinct transaction semantics. Do not generalize that every database operation rolls back identically to normal `INSERT`/`UPDATE`.

## 14. Verifying Commits Using Another Connection

If the goal is confirming a committed transaction is visible to another transaction, the test must read through a fresh transaction or connection after commit.

Querying inside the writing transaction only proves that transaction sees its own changes. It does not test external visibility.

Ways to do this:

- End the test transaction via `TestTransaction.end()` after `flagForCommit()`, then query again.
- Disable the test-managed transaction with `Propagation.NOT_SUPPORTED` so the service commits independently, then query.
- Use a separate `TransactionTemplate` or independent connection after commit.

When testing read replicas, account for replication lag. Committing on the primary does not guarantee an immediate read on a replica sees the row.

## 15. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Test passes yet data is absent after test | Test-managed transaction rolls back by default | Expected slice behavior; use commit test when post-test persistence must be observed |
| Test sees row yet production does not | Assertion ran inside uncommitted transaction | Commit then read from another transaction/connection |
| Service rollback not verified | Outer test transaction masks service's transaction | Use `NOT_SUPPORTED` so service opens its own transaction |
| Data survives test rollback | Service used `REQUIRES_NEW` and inner transaction committed | Clean up separately or intentionally test independent semantics |
| `AFTER_COMMIT` callback never runs | Test transaction ended in rollback | Use `@Commit` or `TestTransaction.flagForCommit()` |
| Direct SQL rows persist unexpectedly | Code ran on another thread outside test transaction | Avoid preemptive timeouts or manage separate transactions/cleanup |
| IDs skip numbers after rollback | Sequences/identities do not roll back | Assert row presence rather than contiguous IDs |
| Commit test pollutes other tests | Data remains in database | Use isolated test database/schema and cleanup |
| Rollback test misses second database | Test transaction only manages one transaction manager | Select appropriate manager and verify each resource |
| Checked exception does not roll back | Default rollback rules exclude checked exceptions | Configure `rollbackFor` if business rules require it |
| `@Commit` used yet assertion still misses commit | Assertions run before test method completes | Use `TestTransaction.end()` to commit mid-test |
| `NESTED` mistaken for independent transaction | Savepoints are not separate physical transactions | Distinguish savepoint rollback from `REQUIRES_NEW` commit |

## 16. Choosing a Test Strategy by Goal

| Goal | Suitable Test Approach |
|---|---|
| Test mapping and repository CRUD | `@DataJdbcTest` with default rollback |
| Test service joining an existing transaction | Default test transaction; check data within transaction |
| Test service commits on success | `NOT_SUPPORTED`, call service, reload after return |
| Test service rolls back on runtime exception | `NOT_SUPPORTED`, call service, confirm row absent |
| Test checked exception rollback | `NOT_SUPPORTED` and `rollbackFor` |
| Test committing a test transaction | `@Commit` or `TestTransaction.flagForCommit()` |
| Test post-commit callbacks | Explicitly commit using `TestTransaction` |
| Test `REQUIRES_NEW` | Open outer transaction, call inner, roll back outer, confirm inner survives |
| Test `NESTED` | Test savepoint inside outer transaction, then test outer rollback |
| Test multiple DataSources | Select specific transaction managers and verify each database state |

You do not need to disable default rollback across all tests. Use rollback tests for repositories/mappings and write dedicated integration tests for commits, business rollbacks, and independent transactions.

## 17. Workflow for Writing Transaction Integration Tests

When designing tests for a Spring Data JDBC use case:

1. **Identify the goal:** testing mapping, commit, rollback, visibility, or post-commit callbacks?
2. **Identify test transaction:** does the test slice open its own transaction?
3. **Identify application transaction:** which propagation and manager does the service use?
4. **Choose boundaries:** keep default rollback, use `NOT_SUPPORTED`, or commit explicitly?
5. **Execute the use case:** invoke through the Spring bean proxy so the transaction interceptor runs.
6. **Observe at the right scope:** read within the same transaction or post-commit via a new connection?
7. **Check all tables:** aggregates, child rows, audits, outboxes, and related records.
8. **Cleanup:** clean up any independently committed transactions.
9. **Test exceptions:** runtime, checked, caught exceptions, and rollback-only.
10. **Verify environment:** use a database and driver matching the semantics under test.

## 18. Practice Exercises

### Exercise 1 — Observing Default Rollback

1. Create a test with `@DataJdbcTest`.
2. Save an aggregate and read it back inside the test.
3. Finish the test.
4. Use another test or independent query to verify the row rolled back.
5. Explain why the initial assertion still passed.

### Exercise 2 — Testing Real Service Commit

1. Create a service method annotated with `@Transactional`.
2. Write a test with `Propagation.NOT_SUPPORTED`.
3. Invoke the service.
4. Query back using `JdbcTemplate`.
5. Confirm data exists after the service method returns.
6. Clean up the committed data.

### Exercise 3 — Testing Business Rollback

1. Create a service writing to two tables and then throwing `RuntimeException`.
2. Disable the test-managed transaction.
3. Invoke the service and catch the exception.
4. Query both tables.
5. Confirm all changes belonging to the transaction rolled back.

### Exercise 4 — Testing Checked Exceptions

1. Change the failure to a checked exception.
2. Run the test without `rollbackFor`.
3. Observe database state.
4. Add `rollbackFor`.
5. Re-run and compare.

### Exercise 5 — TestTransaction and AFTER_COMMIT

1. Write a test-managed transaction.
2. Save an aggregate and register an after-commit callback.
3. Confirm the callback has not fired prior to commit.
4. Call `flagForCommit()` and `end()`.
5. Confirm the callback fired and data committed.

### Exercise 6 — REQUIRES_NEW

1. Open an outer transaction in a test.
2. Invoke an audit service using `REQUIRES_NEW`.
3. Flag the outer transaction for rollback.
4. End the outer transaction.
5. Confirm the independent audit record still exists.
6. Clean up the audit record.

## 19. Conclusion

Default rollbacks in **`@DataJdbcTest`** and other test transactions isolate data between tests. However, a test transaction can wrap outer calls and cause a service using **`REQUIRED`** to join an uncommitted transaction. An assertion reading data inside that transaction does not prove the service committed.

To verify real service commits or rollbacks, let the service manage its own transaction, typically by disabling the test-managed transaction with **`Propagation.NOT_SUPPORTED`**. When you need to explicitly commit a test transaction, use **`@Commit`**, **`@Rollback(false)`**, or **`TestTransaction.flagForCommit()`** and **`TestTransaction.end()`**. After committing, reload from a new transaction or connection to confirm visibility.

Pay special attention to **`REQUIRES_NEW`**, multiple transaction managers, post-commit callbacks, and code running on other threads. Those scenarios can leave committed data behind even when the outer test transaction rolls back. Pick a test strategy matching the exact behavior you need to prove, and clean up committed data so remaining tests stay unaffected.

# Defining Transaction Boundaries for Modifying Methods

## 1. Why Do Modifying Methods Need Transaction Boundaries?

A single UPDATE statement can modify data successfully, but business operations often consist of multiple steps that must succeed or fail together. For example, when transferring money between two accounts, the system must debit the source account and credit the destination account. If the first step is written but the second step fails, data will become unbalanced unless both operations are in the same transaction.

Spring Data JDBC lets you write direct modifying SQL using `@Modifying` combined with `@Query`. This approach is useful for conditional updates, bulk updates, or operations that do not need to load the entire aggregate. However, a modifying SQL statement does not decide the business transaction boundary by itself. The application must clearly define:

- Where does the transaction begin and end?
- Which write commands must commit or roll back together?
- What happens if a step updates zero rows?
- Which errors must trigger a transaction rollback?
- Does a direct update bypass invariants, versions, or aggregate behavior?

In this lesson, we will design transaction boundaries for modifying methods with Spring Data JDBC, focusing on `@Transactional`, `@Modifying`, `@Query`, and application services.

## 2. What Do Transactions Guarantee?

A database transaction groups one or more operations into a single commit/rollback unit. The commonly referenced ACID properties are:

| Property | Meaning in data-modifying operations |
| --- | --- |
| Atomicity | Changes belonging to the transaction commit together or roll back together. |
| Consistency | Constraints and rules are upheld so data state remains valid after the transaction. |
| Isolation | Concurrent transactions do not observe or interfere with one another beyond the chosen isolation level. |
| Durability | After a successful commit, changes are guaranteed to be persisted by the database according to its policy. |

Spring's `@Transactional` defines the transaction scope for a method invocation. When the method finishes normally, the transaction interceptor commits; when an error covered by the rollback policy occurs, the interceptor rolls back.

Crucially, a transaction **does not automatically enforce all business rules**. It gives database operations within that scope atomicity and applies the corresponding isolation. The application must still define update conditions, check affected row counts, use constraints, and handle concurrency appropriately.

## 3. `@Modifying` and `@Query` in Spring Data JDBC

A regular query method typically returns data:

~~~java
@Query("""
    SELECT id, name, available
    FROM inventory
    WHERE id = :id
    """)
Optional<Inventory> findInventory(@Param("id") Long id);
~~~

When the SQL statement modifies data, mark the method with `@Modifying`:

~~~java
@Modifying
@Query("""
    UPDATE inventory
    SET available = available - :quantity
    WHERE id = :id
    """)
int decreaseAvailable(
        @Param("id") Long id,
        @Param("quantity") int quantity
);
~~~

`@Query` provides the SQL statement. `@Modifying` tells Spring Data JDBC that this is a modifying query, not a query that reads a result set. An integer return type can be used to receive the affected row count, helping the service know how many rows the statement updated.

Key distinctions:

- `@Modifying` is **not** an annotation that opens a transaction.
- `@Query` **does not automatically create** a multi-operation business boundary.
- Calling a repository method does not mean all related write commands automatically share a transaction.
- Configure transactions where the use case is expressed, typically in the application service.

For directly declared query methods, do not assume they have the same transaction configuration as inherited CRUD methods. Default configuration for CRUD repositories and declared query methods are separate matters; place `@Transactional` explicitly on the service or method that needs a transaction.

## 4. Placing Transactions on Application Services

Suppose a system has an inventory reservation use case. When a customer reserves a quantity of goods, the application must:

1. Decrement the available quantity if sufficient stock remains.
2. Create a reservation record.
3. If creating the reservation fails, undo the stock decrement.

This is a multi-write use case. The appropriate boundary is usually the service method executing the entire business operation.

### 4.1. Repository Declaring a Direct Modifying Statement

~~~java
package com.example.inventory;

import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET available = available - :quantity
        WHERE id = :id
          AND available >= :quantity
        """)
    int reserveIfAvailable(
            @Param("id") Long id,
            @Param("quantity") int quantity
    );
}
~~~

The `available >= :quantity` condition lives directly inside the UPDATE statement. The database checks and updates within the same statement. This avoids a pattern prone to race conditions:

~~~text
T1: SELECT available = 5
T2: SELECT available = 5
T1: check 5 >= 4
T2: check 5 >= 4
T1: UPDATE available = 1
T2: UPDATE available = 1
~~~

If both transactions read the old quantity and then write a value computed from that snapshot, the result may fail to reflect both reservations. Conditional updates let the database check and perform the subtraction in a single atomic statement per database semantics.

### 4.2. Service Coordinating Multiple Operations in One Transaction

~~~java
package com.example.inventory;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {

    private final InventoryRepository inventory;
    private final ReservationRepository reservations;

    public ReservationService(
            InventoryRepository inventory,
            ReservationRepository reservations
    ) {
        this.inventory = inventory;
        this.reservations = reservations;
    }

    @Transactional
    public Long reserve(Long inventoryId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        int changed = inventory.reserveIfAvailable(
                inventoryId,
                quantity
        );

        if (changed != 1) {
            throw new IllegalStateException(
                    "Inventory not found or insufficient quantity");
        }

        Reservation reservation = new Reservation(
                inventoryId,
                quantity
        );

        Reservation saved = reservations.save(reservation);
        return saved.id();
    }
}
~~~

In this example, `ReservationRepository` is a CRUD repository for the `reservation` table and `Reservation` is the corresponding aggregate. These classes are omitted to focus on the transaction boundary.

Processing flow:

1. Spring opens a transaction when the call goes through the `ReservationService` proxy.
2. `reserveIfAvailable` executes the conditional UPDATE statement.
3. If the affected row count is not 1, the service throws an exception.
4. If the inventory update succeeds, the service saves the reservation.
5. When the method finishes normally, the transaction commits.
6. If saving the reservation fails and the exception triggers rollback, the inventory change also rolls back.

Both repository operations participate in the same transaction when they use the same transaction manager and the same appropriate resource/database. There is no need to open a separate transaction manually for each statement.

## 5. Checking the Affected Row Count

A modifying method should usually return the number of affected rows:

~~~java
@Modifying
@Query("""
    UPDATE accounts
    SET status = :status
    WHERE id = :id
    """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

The service checks the result:

~~~java
@Transactional
public void blockAccount(Long id) {
    int updated = accounts.updateStatus(id, "BLOCKED");

    if (updated == 0) {
        throw new AccountNotFoundException(id);
    }
    if (updated > 1) {
        throw new IllegalStateException(
                "Expected one account to be updated");
    }
}
~~~

With a unique primary key, valid results are typically 0 or 1:

- 0: no row matched the condition; either the ID does not exist or an extra condition was not met.
- 1: exactly one row was updated.
- Greater than 1: the WHERE condition may be too broad or the schema does not guarantee uniqueness as expected.

Do not assume a row count of 0 always means "not found". If WHERE includes status, tenant, or balance conditions, the row may exist without satisfying those conditions. Design exceptions and responses according to business semantics.

## 6. When to Place `@Transactional` on the Repository vs. on the Service?

`@Transactional` can be placed in multiple layers, but each location expresses a different intent.

### 6.1. On the Application Service — Usually the Preferred Choice

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final AuditRepository audit;

    @Transactional
    public void approve(Long orderId) {
        int changed = orders.markApproved(orderId);
        if (changed != 1) {
            throw new IllegalStateException("Order cannot be approved");
        }

        audit.save(new AuditEntry(orderId, "APPROVED"));
    }
}
~~~

The transaction clearly expresses the `approve` use case: updating the order and writing the audit entry must succeed together. The service has full visibility into all steps and business rules.

### 6.2. On a Repository Method — When a Single Operation Needs a Transaction

A repository method can be annotated with `@Transactional` if that method itself is designed as a complete operation and needs a transaction when called standalone:

~~~java
@Transactional
@Modifying
@Query("""
    UPDATE customers
    SET active = false
    WHERE id = :id
    """)
int deactivate(@Param("id") Long id);
~~~

However, if a service calls multiple repository methods that must commit or roll back together, the service-level transaction remains essential. A transaction opened by the service acts as the outer boundary; inner operations normally join the existing transaction via the default `REQUIRED` propagation.

### 6.3. Do Not Place Transactions Indiscriminately in Both Places

Adding `@Transactional` to every repository method and every service method without understanding propagation can make boundaries hard to read. Choose the owner of the use case:

- Service: transaction spanning a multi-step business operation.
- Repository: transaction for an independent operation when there is a specific reason.
- Do not add the annotation just "to be safe" without knowing whether the method is invoked through a proxy or whether the operations share the same transaction manager.

## 7. Propagation: How Methods Participate in Transactions

`@Transactional` defaults to `REQUIRED` propagation. If no transaction exists, Spring starts a new one; if a transaction already exists, the call joins the current transaction.

| Propagation | General behavior | Use case |
| --- | --- | --- |
| REQUIRED | Joins an existing transaction or creates a new one | Appropriate default for most use cases |
| REQUIRES_NEW | Suspends the current transaction and opens an independent one | An operation that must commit independently of the outer transaction's outcome |
| SUPPORTS | Joins if one exists; otherwise runs non-transactionally | An operation that can run both inside and outside a transaction |
| MANDATORY | Requires the caller to already have a transaction | Enforces that a service is only called inside a caller-managed transaction |
| NOT_SUPPORTED | Suspends the current transaction and runs non-transactionally | An operation that should not run inside a transaction |
| NEVER | Fails if a transaction already exists | Enforces that the caller has not opened a transaction |
| NESTED | Uses a nested transaction/savepoint if the transaction manager supports it | A portion of work that can roll back to a savepoint |

### 7.1. Why Should You Not Use `REQUIRES_NEW` Indiscriminately?

Suppose an outer service updates an order and then calls an audit service with `REQUIRES_NEW`. The audit entry can commit even if the outer transaction later rolls back. This may be right if the audit must record an attempt regardless of main business failure; however, if the audit means "the order was approved", the data will be contradictory.

Choose `REQUIRES_NEW` only when an independent transaction is an explicit business requirement. For most write steps that must succeed or fail together, `REQUIRED` is the natural choice.

### 7.2. Transaction Managers and Database Resources

A transaction only covers operations participating in the same matching transaction manager/resource. If two repositories connect to two independent databases or one step calls an HTTP service, `@Transactional` on a single datasource does not make those operations atomic together.

Across multiple systems, design sagas, outboxes, distributed transactions, or compensating mechanisms as required. Do not assume a single annotation can atomically commit/roll back a database, a message broker, and an HTTP service simultaneously.

## 8. Rollback: Which Exceptions Abort a Transaction?

Under Spring transaction defaults:

- `RuntimeException` and `Error` trigger transaction rollback.
- Checked exceptions do not automatically trigger rollback unless a corresponding rollback policy is configured.

For example:

~~~java
@Transactional
public void updateAndValidate(Long id) {
    repository.updateStatus(id, "ACTIVE");
    throw new IllegalStateException("Validation failed");
}
~~~

Because `IllegalStateException` is an unchecked exception, the transaction rolls back by default.

If business logic throws a checked exception and you want rollback:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importAndSave() throws IOException {
    // Write data...
    throw new IOException("Import failed");
}
~~~

You can configure `rollbackFor` for the appropriate exception types. Do not catch an exception and ignore it while letting the method finish normally:

~~~java
@Transactional
public void updateAccount(Long id) {
    repository.updateStatus(id, "ACTIVE");
    try {
        performAnotherWrite();
    } catch (RuntimeException ex) {
        log.error("Write failed", ex);
        // Swallowing the exception may allow the transaction to commit.
    }
}
~~~

If an error must abort the entire business operation, let the exception escape the transactional method boundary or mark the transaction rollback-only using an appropriate mechanism. Logging and continuing to commit can leave unintended partial state.

## 9. Transactional Proxies and Self-Invocation

In standard Spring configurations, `@Transactional` is applied via a proxy. Calls from another bean go through the proxy and trigger the transaction interceptor.

A common mistake is calling a transactional method on the same object:

~~~java
@Service
public class ImportService {

    public void importAll() {
        saveOne(); // Direct call on this, bypassing the proxy.
    }

    @Transactional
    public void saveOne() {
        // Do not assume a transaction is opened by self-invocation.
    }
}
~~~

Calling `saveOne()` from `importAll()` is self-invocation; in default proxy mode, it does not pass through the proxy and the annotation on `saveOne()` may not be applied as expected.

A clearer structure is to place the transaction on the public method called from outside:

~~~java
@Service
public class ImportService {

    @Transactional
    public void importAll() {
        saveOne();
        saveAnother();
    }

    private void saveOne() {
        // Write operations join importAll's transaction.
    }

    private void saveAnother() {
        // Write operations join importAll's transaction.
    }
}
~~~

Alternatively, extract the use case/transactional operation into another bean if a separate boundary is needed. Also keep in mind proxy limitations such as methods that cannot be proxied under the active configuration, `final`/`private` methods, and the proxy mode in use.

## 10. `readOnly` Is Not a Write Lock Mechanism

A read method is often marked:

~~~java
@Transactional(readOnly = true)
public Customer findCustomer(Long id) {
    return customers.findById(id).orElseThrow();
}
~~~

`readOnly = true` expresses read-only intent and can allow the transaction manager/provider to apply appropriate optimizations. However, do not treat it as a security mechanism or an absolute guarantee that all write commands will be blocked. Exact behavior depends on the transaction manager, database, and driver.

For modifying methods, use a regular write transaction:

~~~java
@Transactional
public void changeStatus(Long id, String status) {
    int changed = customers.updateStatus(id, status);
    if (changed != 1) {
        throw new IllegalStateException("Customer was not updated");
    }
}
~~~

Do not mark a write use case as read-only just because it performs a read step before updating.

## 11. Isolation and Concurrent Updates

`@Transactional` defaults to `DEFAULT` isolation, meaning the default level defined by the database/transaction manager. A transaction guaranteeing atomicity does not mean all race conditions automatically disappear.

### 11.1. Conditional Updates

For an inventory decrement operation, the SQL statement:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE id = :id
  AND available >= :quantity;
~~~

lets the database evaluate the condition at update time. The service must check the affected row count to know whether the operation succeeded.

### 11.2. Optimistic Locking

If you use `@Version` on the aggregate root and call `repository.save(aggregate)`, Spring Data JDBC can use the version to detect concurrent updates. However, a handwritten `@Modifying` SQL statement does not automatically go through the version-aware aggregate save mechanism.

If you want a direct update with optimistic locking, you must put the version in the condition and increment the version in the same statement:

~~~sql
UPDATE accounts
SET balance = :newBalance,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Then check the affected row count:

- 1: update succeeded against the read version.
- 0: ID does not exist or version changed; distinguish according to business needs.

This is a conceptual SQL example. Version type, increment logic, and mapping must be consistent with the model. Do not let a `@Modifying` query ignore the version while other flows rely on optimistic locking.

### 11.3. Pessimistic Locking and Isolation

Some business operations require row locks or higher isolation, though choosing `SELECT ... FOR UPDATE`, isolation levels, or lock timeouts depends on the database and driver. Use them only with clear justification, inspect execution plans/lock behavior, and design a consistent lock ordering to reduce deadlock risk.

Do not raise isolation to the highest level for every method. Higher isolation can prevent certain anomalies but also reduces concurrency or increases lock/retry overhead.

## 12. Direct Updates Can Bypass Aggregate Behavior

A `@Modifying` method runs SQL directly. It does not load the aggregate and invoke domain behavior. As a result, it can bypass:

- Invariants checked inside the aggregate root.
- State transition rules.
- Calculation or normalization logic in the domain model.
- Optimistic locking applied on the save path.
- Callbacks or processes attached by the application to aggregate saving.
- Synchronization of child entities belonging to the aggregate.

For example, if an order can only be cancelled while in `DRAFT` status, the SQL statement:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = :id;
~~~

could cancel an order that has already been submitted. A safer statement must express the condition:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = :id
  AND status = 'DRAFT';
~~~

Then the service checks the row count. Still, if cancelling must also write an audit log, release reservations, or publish an event, an application service must coordinate all of those steps within an appropriate transaction.

Choose direct modifying SQL when the operation fits business policy and necessary invariants can be protected by SQL predicates/constraints. If the operation involves rich domain behavior, loading the aggregate, calling root behavior, and saving is usually clearer.

## 13. Do Not Hold a Database Transaction Open While Calling External Services

Example to avoid:

~~~java
@Transactional
public void approve(Long orderId) {
    orders.markApproved(orderId);
    emailClient.sendApprovalEmail(orderId);
    remoteBilling.capture(orderId);
}
~~~

HTTP/email calls can be slow or fail, causing the database transaction to hold connections and locks for a long time. Moreover, a database transaction cannot roll back an email already sent or a payment already accepted by another system.

A common design pattern:

~~~text
Application service
  -> update business data
  -> write outbox event in the same transaction
  -> commit

Outbox publisher
  -> read committed events
  -> send to broker/external service
  -> retry and mark as sent
~~~

A transactional outbox lets you record business changes and outgoing messages in the same database transaction. Sending to external systems happens after commit and needs appropriate idempotency/retry handling.

For multi-step workflows across multiple services, consider sagas and compensating actions. Do not assume a local `@Transactional` can roll back external resources.

## 14. Batch Updates and Transaction Size

A transaction containing tens of thousands or millions of updates can hold connections for a long time, generate heavy log/undo data, and increase pressure on the database. Grouping an entire batch into one giant transaction is not always best.

There are two approaches:

### One Transaction for the Entire Batch

Suitable when the business requires all rows to be updated together and batch size is bounded.

Pros: simple atomicity. Cons: long-running transaction, expensive rollback, and prolonged locks.

### Splitting the Batch into Small Transactions

Suitable when partial progress is acceptable and resumability is needed:

~~~java
for (List<Long> ids : batches) {
    batchWriter.updateBatch(ids);
}
~~~

In this example, `batchWriter` is another bean with a `@Transactional` method invoked through a proxy:

~~~java
@Service
public class BatchWriter {

    private final CustomerRepository customers;

    public BatchWriter(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public void updateBatch(List<Long> ids) {
        customers.markInactive(ids);
    }
}
~~~

Each batch can commit independently. When a later batch fails, earlier committed batches remain persisted; the job needs checkpointing and must be safe to re-run. If all-or-nothing semantics are required, splitting transactions like this is not appropriate.

## 15. Testing Transaction Boundaries

Testing should not only verify that the repository method runs. It must confirm that operations commit or roll back together as designed.

### 15.1. Testing Rollback When a Subsequent Step Fails

An integration test can:

1. Create inventory with quantity 10.
2. Call the service to reserve 3, forcing reservation creation to fail.
3. Verify the transaction rolled back and inventory is still 10.
4. Call the use case again successfully.
5. Verify inventory is down to 7 and the corresponding reservation exists.

Illustrative test skeleton:

~~~java
@SpringBootTest
class ReservationServiceIntegrationTest {

    @Autowired
    ReservationService service;

    @Autowired
    InventoryRepository inventory;

    @Test
    void rollsBackInventoryWhenReservationCannotBeSaved() {
        // Arrange data and trigger failure at the reservation save step.
        // Call the service in the service's own transaction.
        // Re-read inventory in an appropriate transaction/test context.
        // Assert the quantity was restored.
    }
}
~~~

This is an illustrative skeleton; failure injection can use a real constraint or a test double at the right boundary. Be careful with `@Transactional` on the test itself: an outer test transaction can obscure actual commit timing. When testing service transactions, understand the test's transaction and how data is re-read.

### 15.2. Testing Row Counts

Verify these cases:

- ID exists and condition is met: row count equals 1.
- ID does not exist: row count equals 0.
- Row exists but quantity is insufficient: row count equals 0.
- Input quantity is 0 or negative: service rejects before executing SQL.

### 15.3. Testing Concurrency

For concurrent update operations, use integration tests running multiple real transactions against the target database. H2 does not fully prove the locking/isolation semantics of PostgreSQL, MySQL, or a production database. Check final results, row counts, exceptions, and versions against a real database.

## 16. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `@Modifying` update runs, then fails on a second write operation | Steps are not in the same transaction | Place `@Transactional` on the application service spanning the whole use case. |
| First step committed even though the next step failed | Operations used separate transactions or `REQUIRES_NEW` propagation | Share the transaction manager and use `REQUIRED` when atomicity is needed. |
| Error occurred but data still committed | Exception was caught and swallowed, or was a checked exception outside rollback rules | Let the error propagate or configure `rollbackFor`/rollback-only appropriately. |
| `@Transactional` has no effect | Self-invocation or method did not go through a proxy | Place the annotation on an entry point called through a proxy or extract a separate bean. |
| Update changes zero rows | ID does not exist or `WHERE` condition is not met | Check row count and map to a clear business outcome. |
| Direct update overwrites newer data | Missing version condition or business condition in `WHERE` | Use optimistic locking/conditional updates and check the row count. |
| Transaction holds connection too long | Calling external APIs or processing long batches inside a transaction | Shorten transactions; use outbox/chunking/checkpointing appropriately. |
| Assuming `readOnly` blocks all writes | Misunderstanding `readOnly` as a security mechanism | Use write transactions for modifying use cases and constraints/permissions to protect data. |
| SQL update bypasses domain rules | Direct DML does not invoke aggregate behavior | Put invariants into SQL predicates/constraints or use aggregate behavior and save. |

## 17. Process for Designing Transaction Boundaries

When adding a modifying method, follow these steps:

1. **Describe the use case:** what does the user want to change and what are the success criteria?
2. **List database operations:** how many insert/update/delete statements must be coordinated?
3. **Determine atomicity:** which steps must commit or roll back together?
4. **Choose the entry point:** place `@Transactional` on the application service representing the use case.
5. **Choose direct modifying SQL vs. aggregate save:** weigh invariants, child entities, versions, and cost.
6. **Check row count:** define behavior when zero rows are updated.
7. **Design rollback:** which exceptions abort the transaction, and are any checked or caught?
8. **Check concurrency:** use conditional updates, versions, constraints, or appropriate locks.
9. **Isolate side effects:** do not hold database transactions open while waiting on external services; consider an outbox.
10. **Test commit/rollback:** verify database state after both success and failure.

## 18. Practice Exercises

**Exercise 1 — Conditional update.** Write a repository method using `@Modifying` to decrement inventory when enough stock remains. Return the row count and handle insufficient stock in the service.

**Exercise 2 — Two-step write.** After decrementing inventory, create a reservation. Intentionally make the reservation step fail and verify that the transaction rolls back the inventory change as well.

**Exercise 3 — Self-invocation.** Create two methods in the same service, only one annotated with `@Transactional`, and call it internally. Observe whether the transaction is applied as expected. Move the annotation to the entry point or extract a separate bean to compare.

**Exercise 4 — Rollback rule.** Throw a runtime exception and a checked exception from a transactional method. Compare commit/rollback outcomes, then configure `rollbackFor`.

**Exercise 5 — Optimistic update.** Add a `version` column and write an update with `WHERE id = :id AND version = :expectedVersion`. Increment `version` in the same statement and handle a row count of 0.

**Exercise 6 — `REQUIRES_NEW`.** Write an audit entry using a `REQUIRES_NEW` service, then cause the outer transaction to roll back. Observe whether the audit entry remains and explain whether that matches business intent.

**Exercise 7 — Batch.** Write a job that updates many customers in batches. Compare one large transaction with per-batch transactions; decide how to checkpoint and retry if the third batch fails.

## 19. Takeaways

`@Modifying` marks a query method as executing a data-modifying statement; it does not replace `@Transactional`. For a use case with multiple write operations, place the transaction boundary on the application service so repository methods join one transaction and commit or roll back according to the business outcome.

Check row counts, choose clear rollback rules, understand propagation and proxies, and protect concurrent updates with SQL predicates, versions, or constraints. Direct modifying SQL can bypass aggregate behavior and the save path's optimistic locking, so you must actively ensure necessary invariants are upheld. A database transaction also does not span HTTP calls, emails, or brokers; use outbox/saga patterns when coordinating across systems.

### References

- [Spring Data Relational – Modifying Queries](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework – @Transactional Annotation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
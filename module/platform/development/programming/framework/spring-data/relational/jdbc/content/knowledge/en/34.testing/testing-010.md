# Testing Rollback Across Tables and Multiple Repositories

In **Spring Data Relational JDBC**, a single use case often writes to multiple tables and may invoke multiple repositories. For instance, creating an order might persist the order aggregate, decrement inventory, and write an audit record. If a later step fails, the application typically needs to roll back all changes so the database does not end up with half-completed business state.

To test that behavior, you need to understand Spring transaction boundaries, how Spring Data JDBC shares connections within a transaction, and how test frameworks automatically roll back tests. A test can pass merely because the test's own transaction rolled back, even when the production service lacks a transaction spanning multiple repositories. Therefore, you must pick the right test style for the question you want to confirm.

This lesson focuses on:

- Transactions spanning multiple repositories and multiple tables.
- Differences between test-managed transactions and service transactions.
- Verifying database state after an intermediate step fails.
- Rollback rules for runtime exceptions and checked exceptions.
- Propagation, `REQUIRES_NEW`, multiple DataSources, and asynchronous operations.
- Rollback limits for external systems and using a transactional outbox.

## 1. Why Is Cross-Table Rollback Needed?

Suppose an order placement use case performs three changes:

1. Insert the order and order lines into `order`/`order_line` tables.
2. Decrement stock quantity in the `inventory` table.
3. Write business history into the `order_audit` table.

If steps 1 and 2 succeed yet step 3 fails, the desired outcome is normally to undo every database change:

```text
placeOrder()
    │
    ├── save PurchaseOrder + OrderLine
    │
    ├── update Inventory
    │
    └── insert OrderAudit  ── failure
                  │
                  ▼
              ROLLBACK
                  │
                  ├── Order does not exist
                  ├── OrderLine does not exist
                  ├── Inventory restored to previous quantity
                  └── OrderAudit does not exist
```

Rollback can only undo changes belonging to the same database transaction. If each repository call completes its own separate transaction, earlier steps may already be committed before a later step fails.

## 2. Transaction Boundaries Belong at the Service / Use-Case Layer

Repositories are data-access components. A business flow spanning multiple repository calls usually needs a transaction at the service layer:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;
    private final OrderAuditRepository auditRepository;

    public OrderService(
            PurchaseOrderRepository orderRepository,
            InventoryRepository inventoryRepository,
            OrderAuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public PurchaseOrder placeOrder(PlaceOrderCommand command) {
        InventoryItem item = inventoryRepository
                .findBySku(command.sku())
                .orElseThrow();

        if (item.availableQuantity() < command.quantity()) {
            throw new IllegalStateException("Insufficient inventory");
        }

        PurchaseOrder order = orderRepository.save(
                PurchaseOrder.pending(
                        command.customerId(),
                        command.sku(),
                        command.quantity()
                )
        );

        inventoryRepository.save(
                item.decrease(command.quantity())
        );

        auditRepository.save(
                OrderAudit.created(order.id(), command.customerId())
        );

        return order;
    }
}
```

`@Transactional` on the service creates one transaction wrapping the entire method invocation. Inner repository calls join the active transaction if they use the same transaction manager and DataSource.

If an operation throws a runtime exception that exits the transaction boundary, Spring marks the transaction for rollback by default. Prior writes inside that transaction are not committed.

### 2.1. Why Not Rely Solely on Per-Repository Transactions?

Spring Data repository CRUD methods typically have their own transaction configuration. However, if a service invokes three repositories without an enclosing transaction, each repository call can run in its own transaction:

```text
Service without @Transactional
    │
    ├── orderRepository.save() ── transaction A ── COMMIT
    │
    ├── inventoryRepository.save() ─ transaction B ─ COMMIT
    │
    └── auditRepository.save() ─── transaction C ── ERROR
                                                       │
                                                       ▼
                                  A and B already committed; not rolled back together
```

That is why transaction boundaries belong on the use case when multiple operations must succeed or fail atomically.

### 2.2. Multiple Repositories Can Share One Transaction

The essential requirement is that the repositories participate in the same transaction manager and DataSource. Spring's JDBC transaction manager binds a connection to the current transaction; Spring Data JDBC and `JdbcTemplate` sharing that DataSource participate in the same connection.

For example, a service can combine:

- A Spring Data JDBC repository.
- Another Spring Data JDBC repository.
- `JdbcTemplate` using the same DataSource.
- A custom DAO using Spring's transaction-aware mechanism.

The number of repositories does not determine the number of transactions. One transaction can span multiple repositories and tables as long as they share the same transactional resource.

## 3. Example Model for Rollback Tests

The following examples use three tables: `purchase_order`, `inventory_item`, and `order_audit`. Illustrative PostgreSQL schema:

```sql
CREATE TABLE inventory_item (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    sku VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_audit (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    actor_id VARCHAR(80) NOT NULL
);
```

Repositories:

```java
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}

public interface OrderAuditRepository
        extends CrudRepository<OrderAudit, Long> {
}
```

Domain factories and methods in the example:

```java
public record PlaceOrderCommand(
        Long customerId,
        String sku,
        int quantity,
        boolean failAfterInventoryUpdate
) {}

public record InventoryItem(
        @Id Long id,
        String sku,
        int availableQuantity
) {
    public InventoryItem decrease(int amount) {
        return new InventoryItem(
                id,
                sku,
                availableQuantity - amount
        );
    }
}

public record PurchaseOrder(
        @Id Long id,
        Long customerId,
        String sku,
        int quantity,
        String status
) {
    public static PurchaseOrder pending(
            Long customerId,
            String sku,
            int quantity) {
        return new PurchaseOrder(
                null, customerId, sku, quantity, "PENDING");
    }
}

public record OrderAudit(
        @Id Long id,
        Long orderId,
        String eventType,
        String actorId
) {
    public static OrderAudit created(Long orderId, Long customerId) {
        return new OrderAudit(
                null, orderId, "ORDER_CREATED", customerId.toString());
    }
}
```

Annotation imports and Spring Data types can be placed in your project's respective files. This example shows minimal mapping; in a real application, apply proper naming/schema mapping and domain validation.

To force an intentional error after the first two repositories write, the service can have a test-specific hook or replaceable collaborator in tests:

```java
@Transactional
public PurchaseOrder placeOrder(PlaceOrderCommand command) {
    InventoryItem item = inventoryRepository.findBySku(command.sku())
            .orElseThrow();

    if (item.availableQuantity() < command.quantity()) {
        throw new IllegalStateException("Insufficient inventory");
    }

    PurchaseOrder order = orderRepository.save(
            PurchaseOrder.pending(
                    command.customerId(),
                    command.sku(),
                    command.quantity()
            )
    );

    inventoryRepository.save(item.decrease(command.quantity()));

    if (command.failAfterInventoryUpdate()) {
        throw new IllegalStateException("Simulated failure");
    }

    auditRepository.save(
            OrderAudit.created(order.id(), command.customerId())
    );

    return order;
}
```

In production, never let clients pass an arbitrary flag to trigger failures. Replace the simulation branch with a mockable collaborator in tests, or trigger a natural constraint/validation failure at the final step. The objective is to force the transaction to fail after earlier writes have already run.

## 4. Test Slice: @DataJdbcTest Rolls Back Tests by Default

`@DataJdbcTest` is the test slice for Spring Data JDBC. It configures most JDBC repository infrastructure and by default runs each test inside a transaction rolled back after the test finishes.

Example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;

@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Autowired
    InventoryRepository inventoryRepository;

    @Test
    void repositoryWritesAreRolledBackAfterTest() {
        InventoryItem savedInventory = inventoryRepository.save(
                new InventoryItem(null, "SKU-CHAIR", 10)
        );

        PurchaseOrder savedOrder = orderRepository.save(
                PurchaseOrder.pending(100L, "SKU-CHAIR", 2)
        );

        assertThat(inventoryRepository.findById(savedInventory.id()))
                .isPresent();
        assertThat(orderRepository.findById(savedOrder.id()))
                .isPresent();
    }
}
```

After the test finishes, Spring TestContext rolls back the default transaction. This test is useful for verifying mapping/repositories without manually deleting fixture data after every test.

### 4.1. Automatic Test Rollback Does Not Prove the Service Has a Transaction

If a test method has a transaction created by the test framework, a `@Transactional` service method using default `REQUIRED` propagation joins that outer transaction. When the test completes, the test transaction rolls back regardless of whether the service method itself defines a transaction boundary.

Therefore, a `@DataJdbcTest` can confirm repositories write properly, yet does not suffice to prove an isolated service call rolls back all repositories when a step fails.

To properly verify a service's transaction boundary, let the service manage its own transaction and inspect the database after the service call finishes.

## 5. Integration Test Verifying Real Service Rollback

Use `@SpringBootTest` to load services, repositories, DataSource, and transaction configuration like the real application. For this test, **do not annotate the test method itself with `@Transactional`**. If the test method opens an outer transaction, the service joins it and assertions will no longer prove that the service's own transaction rolled back.

Example:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderServiceRollbackIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    InventoryRepository inventoryRepository;

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Autowired
    OrderAuditRepository auditRepository;

    @BeforeEach
    void setUp() {
        auditRepository.deleteAll();
        orderRepository.deleteAll();
        inventoryRepository.deleteAll();

        inventoryRepository.save(
                new InventoryItem(null, "SKU-CHAIR", 10)
        );
    }

    @Test
    void rollsBackAllRepositoryWritesWhenLaterStepFails() {
        assertThatThrownBy(() -> orderService.placeOrder(
                new PlaceOrderCommand(
                        100L,
                        "SKU-CHAIR",
                        2,
                        true
                )
        )).isInstanceOf(IllegalStateException.class)
          .hasMessage("Simulated failure");

        assertThat(orderRepository.count()).isZero();
        assertThat(auditRepository.count()).isZero();

        InventoryItem inventory = inventoryRepository
                .findBySku("SKU-CHAIR")
                .orElseThrow();

        assertThat(inventory.availableQuantity()).isEqualTo(10);
    }
}
```

The test performs:

1. Seed inventory fixture with quantity 10.
2. Call the service through the Spring bean/proxy.
3. The service inserts the order, updates inventory, then throws a runtime exception.
4. The service's transaction rolls back.
5. The test queries the database after the service call completes.
6. Confirm order/audit do not exist and inventory remains at 10.

Because the test method has no enclosing transaction, assertion queries read the state already rolled back by the service's transaction. This provides direct evidence for cross-repository rollback.

### 5.1. Why Calling the Service Through a Spring Bean Matters

`@Transactional` is normally enforced via a Spring AOP proxy. If a test manually constructs the service using `new OrderService(...)`, the annotation will not create a transaction. Similarly, calling another transactional method on the same instance (self-invocation) normally bypasses the proxy and skips transaction advice.

In integration tests, inject the service from the `ApplicationContext` and invoke it via that bean. Avoid manually instantiating services in tests when verifying Spring transaction behavior.

### 5.2. Which Database Should Be Used?

Test slices can use an embedded database if dependencies and configuration permit. However, if production uses PostgreSQL/MySQL or relies on vendor-specific dialects, constraints, isolation, or data types, run integration tests against the same database type via Testcontainers or an equivalent test environment.

Transaction rollback is a standard database capability, yet SQL behavior, foreign keys, isolation, generated keys, and locking vary across database engines. Passing on H2 does not fully prove behavior on PostgreSQL or MySQL.

## 6. Testing Rollback Across Multiple Tables in One Aggregate

Spring Data JDBC persists an aggregate root together with its owned child entities. For example, an order with a collection of lines:

```java
@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        Long customerId,
        String status,
        @MappedCollection(idColumn = "purchase_order_id")
        List<OrderLine> lines
) {}
```

A single aggregate insert can insert the root row and multiple child rows. If another repository in the same transaction throws an error after saving the aggregate, both root and child rows must roll back alongside changes to other tables.

Tests should confirm both root and children:

```java
assertThat(orderRepository.count()).isZero();
assertThat(orderLineRepository.count()).isZero();
assertThat(inventoryRepository.findBySku("SKU-CHAIR")
        .orElseThrow()
        .availableQuantity()).isEqualTo(10);
```

If children are managed solely via the aggregate root without a separate repository, check directly via SQL query or `JdbcTemplate`. What matters is confirming no orphaned child rows remain after rollback.

## 7. Rollback Rules: RuntimeException and Checked Exceptions

By default, Spring rolls back a transaction when a transactional method exits with a `RuntimeException` or `Error`. Checked exceptions do not trigger automatic rollback under default rules.

Runtime exception example:

```java
@Transactional
public void createOrder() {
    orderRepository.save(...);
    throw new IllegalStateException("Failure");
}
```

By default, the transaction rolls back.

If the method throws a checked exception:

```java
@Transactional
public void createOrder() throws IOException {
    orderRepository.save(...);
    throw new IOException("Cannot read input");
}
```

By default, checked exceptions such as `IOException` do not trigger rollback. To roll back on them, declare:

```java
@Transactional(rollbackFor = IOException.class)
public void createOrder() throws IOException {
    orderRepository.save(...);
    throw new IOException("Cannot read input");
}
```

You can specify a parent exception type in `rollbackFor` when covering a group of failures. Define explicit rules matching the business contract, and avoid overly broad `rollbackFor` when certain errors represent valid outcomes.

### 7.1. Catching Exceptions Inside a Transactional Method

If a method catches an exception and does not rethrow it, the transaction interceptor may treat the method as completing normally and commit:

```java
@Transactional
public void createOrder() {
    orderRepository.save(...);

    try {
        auditRepository.save(...);
    } catch (DataAccessException ex) {
        log.warn("Audit write failed", ex);
        // Method finishes normally: transaction may commit.
    }
}
```

If the failure must roll back, rethrow an exception across the transaction boundary:

```java
@Transactional
public void createOrder() {
    orderRepository.save(...);

    try {
        auditRepository.save(...);
    } catch (DataAccessException ex) {
        throw new OrderCreationException("Cannot write audit", ex);
    }
}
```

Or explicitly mark rollback-only via the appropriate transaction status. Usually, however, it is cleaner to let an exception representing failure cross the boundary and handle it in an outer caller. When caught in a controller or caller outside the proxy, the transaction interceptor has already applied its rollback rules.

## 8. Test-Managed Transactions and @Rollback/@Commit

Spring TestContext supports test transactions via `@Transactional` on a test class or method. By default, test transactions roll back when the test completes.

Example:

```java
@SpringBootTest
@Transactional
class OrderRepositoryTransactionalTest {

    @Test
    void writesAreRolledBackAfterTest() {
        // Test data access inside the test's transaction.
    }
}
```

Common annotations:

| Annotation | Meaning |
| --- | --- |
| `@Transactional` on test | Runs test inside a test-managed transaction if supported by test framework |
| `@Rollback` | Specifies whether the test transaction should roll back on completion |
| `@Commit` | Requests committing the test transaction on completion |
| `@Rollback(false)` | Disables default rollback and commits the test transaction |

Example:

```java
@Test
@Commit
void commitsTestData() {
    // Data is committed when the test finishes.
}
```

Or:

```java
@Test
@Rollback(false)
void alsoCommitsTestData() {
    // Used when explicit commit control is needed.
}
```

Do not enable commit just to verify a rollback operation and leave unexpected test data behind. When committing to inspect state via another connection, manage fixtures and cleanup explicitly.

### 8.1. Test Transactions Can Mask Transaction Boundary Bugs

If a test method already has a transaction, calling a service with `REQUIRED` propagation joins the test transaction. Consequently:

- The service does not open a new transaction.
- Assertions inside the test can still see uncommitted data.
- The final test rollback wipes all changes even if the service lacked its own transaction boundary.

To confirm a service rolls back when called standalone, write a test without `@Transactional` on the method/class, invoke the service through its proxy, catch the exception, and reload data afterward.

## 9. Transaction Propagation and REQUIRES_NEW

Propagation decides whether a transactional method joins the active transaction or creates another transaction.

### 9.1. REQUIRED

This is the default propagation. If a transaction already exists, the method joins it; otherwise, Spring starts a new one.

```java
@Transactional
public void placeOrder() {
    orderRepository.save(...);
    inventoryService.reserve(...); // Default REQUIRED
}
```

If both methods share the same transaction manager, their changes roll back together.

### 9.2. REQUIRES_NEW

`REQUIRES_NEW` always runs in an independent transaction. The outer transaction is suspended while the inner transaction executes:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord(OrderAudit audit) {
    auditRepository.save(audit);
}
```

If the audit transaction commits successfully and then the outer order transaction rolls back, the audit record still exists. This is not all-or-nothing rollback.

This can be useful when recording a failure log independently, yet inappropriate if the audit row must exist if and only if the order succeeds.

`REQUIRES_NEW` usually requires a second connection while the outer transaction holds onto its connection. If the pool is small and many requests nest transactions this way, the pool can be exhausted. Account for connection counts and transaction durations.

### 9.3. NESTED

`NESTED` can use savepoints inside the active transaction if supported by the transaction manager and database. It is not an independently committed transaction like `REQUIRES_NEW`. Support and semantics depend on the transaction manager/driver/database; test them before relying on it.

## 10. Multiple DataSources or Multiple Transaction Managers

A local JDBC transaction typically manages one DataSource. If an application has two DataSources:

```text
OrderRepository ── DataSource A ── Database A
AuditRepository ── DataSource B ── Database B
```

`@Transactional` using DataSource A's transaction manager does not automatically roll back transactions on DataSource B together.

With multiple transaction managers, specify the right manager:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void placeOrder() {
    // Repositories participate in ordersTransactionManager.
}
```

If atomic updates across multiple database resources are required, use an appropriate architecture such as JTA/XA when supported by infrastructure, or design eventual consistency with saga/outbox patterns. Never assume two DataSources pointing to the same server/database automatically share a transaction.

Even if two DataSources share the same JDBC URL, if they are two independent pools/connections with separate transaction managers, operations do not automatically join the same local transaction.

## 11. Asynchronous Work and Side Effects Outside the Transaction

Spring-managed JDBC transactions are normally bound to the current thread. Work executing on another thread—such as via `@Async`, an executor, or a message listener—does not automatically join the caller thread's transaction:

```text
Thread A: @Transactional service
   │
   ├── write order in transaction A
   │
   └── submit async task ─────────────► Thread B
                                         │
                                         └── separate transaction/connection
```

If Thread A rolls back, database operations committed on Thread B do not roll back with it. Likewise, sending emails, calling payment gateways, or publishing messages to a broker cannot be rolled back automatically by the database.

Do not perform external side effects before the database transaction reaches its final outcome if business rules require them only after commit. Use transaction synchronization/after-commit events for simple side effects; for high-reliability requirements, a transactional outbox is usually better.

## 12. Transactional Outbox for Messages That Must Stay Consistent with the Database

Suppose creating an order must publish an `ORDER_CREATED` event. If you write to the database and then send the message:

1. The database commits successfully.
2. The application crashes before sending the message.
3. The order exists, yet consumers never receive the event.

If you send the message first and then the database rolls back, consumers receive an event for a nonexistent order.

A transactional outbox solves this by writing domain data and an outbox record inside the same transaction:

```text
@Transactional
placeOrder()
    │
    ├── INSERT purchase_order
    ├── UPDATE inventory_item
    └── INSERT outbox_event
              │
              ▼
           COMMIT
              │
              ▼
Background publisher reads outbox
              │
              ▼
         Publish message
              │
              ▼
        Mark as sent
```

If the transaction rolls back, the order, inventory change, and outbox record all vanish together. If the commit succeeds yet the publisher temporarily fails, the outbox record remains for retry.

The publisher must handle duplicate delivery (at-least-once), and consumers should be idempotent. An outbox does not turn a database and message broker into a distributed transaction; it provides a reliable way to coordinate eventual consistency.

## 13. Testing Transactions with TransactionTemplate

When you need explicit transaction control in tests or imperative code, you can use `TransactionTemplate`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class OrderWriter {

    private final TransactionTemplate transactionTemplate;
    private final PurchaseOrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderWriter(
            TransactionTemplate transactionTemplate,
            PurchaseOrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.transactionTemplate = transactionTemplate;
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    public void writeThenFail(PurchaseOrder order, InventoryItem item) {
        transactionTemplate.executeWithoutResult(status -> {
            orderRepository.save(order);
            inventoryRepository.save(item);
            throw new IllegalStateException("Force rollback");
        });
    }
}
```

`TransactionTemplate` uses the injected transaction manager and applies rollback rules to the callback. You can mark rollback-only via `status` when ending the callback without throwing an exception:

```java
transactionTemplate.executeWithoutResult(status -> {
    orderRepository.save(order);

    if (shouldAbort()) {
        status.setRollbackOnly();
    }
});
```

In standard Spring Data JDBC applications, `@Transactional` on services is usually more readable. `TransactionTemplate` helps when transaction boundaries must be controlled imperatively per branch or in specialized tests.

## 14. Designing Reliable Rollback Tests

A service-level test should verify both initial data and post-failure state:

1. Use a clean test database or deterministic fixtures.
2. Seed data before invoking the service, e.g., inventory with 10 items.
3. Call the Spring service bean via its proxy, not instantiated with `new`.
4. Make a middle or final step throw an exception after prior writes executed.
5. Catch the exception in the test.
6. Reload data via repositories after the service call completes.
7. Confirm every table in the transaction returned to its prior state.
8. Do not put `@Transactional` on the test if verifying that the service transaction rolls back on its own.
9. Use the same DataSource/transaction manager for all repositories that must roll back together.
10. Run tests on a production-like database engine when relying on dialects, locking, or constraints.

### 14.1. Verify Preserved Baseline Data Too

Rollback does not mean wiping the entire database. Tests should confirm the original fixture still exists:

```java
InventoryItem inventory = inventoryRepository.findBySku("SKU-CHAIR")
        .orElseThrow();

assertThat(inventory.availableQuantity()).isEqualTo(10);
assertThat(orderRepository.count()).isZero();
assertThat(auditRepository.count()).isZero();
```

If you only assert the order does not exist and forget inventory, tests can miss partial rollback bugs.

### 14.2. Verify Child Row Counts

If an aggregate persists a child collection, inspect both root and child rows. A direct verification query can help:

```sql
SELECT COUNT(*)
FROM order_line
WHERE purchase_order_id = ?;
```

After rollback, the row count must be 0 if a new aggregate was created in the failed transaction. For pre-existing fixtures, compare against the original row count rather than always expecting 0.

## 15. Common Errors

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Order saved yet inventory did not roll back | Repositories ran in separate transactions | Put `@Transactional` on the service and share DataSource/manager |
| Tests pass yet production service writes partially | Test method has an outer transaction that rolls back after test | Write integration tests without `@Transactional` on the test method |
| Exception occurs yet data commits | Checked exception excluded by default rules or exception was caught | Configure `rollbackFor` or propagate runtime exception across boundary |
| Audit record survives order rollback | Audit method uses `REQUIRES_NEW` | Verify whether an independent transaction is truly intended |
| Service `@Transactional` does not fire | Self-invocation or service instantiated via `new` | Invoke through the Spring proxy bean |
| Repositories use different connections | Different DataSources/transaction managers | Standardize configuration and specify transaction manager |
| Async task writes data after rollback | Another thread runs in its own transaction | Dispatch command after commit or use outbox |
| Message sent while database rolled back | Published before commit | Use after-commit or transactional outbox |
| Test data left behind after test | Using `@Commit`/`@Rollback(false)` or non-transactional test | Check annotations and clean up fixtures |
| Rollback test wipes setup data | Setup ran inside the same test-managed transaction | Seed fixtures outside the transaction or separate setup/cleanup |
| H2 passes yet production database fails | SQL/constraint/transaction semantics differ | Run integration tests on the target database |
| Connection pool exhausted under `REQUIRES_NEW` | Outer transaction holds connection while inner transaction needs another | Reduce nesting, verify pool sizing, or redesign |

## 16. Practice Exercises

**Exercise 1 — One service, two repositories.** Create a `@Transactional` service saving an order and updating inventory. Intentionally throw `IllegalStateException` after both operations, and confirm both changes roll back.

**Exercise 2 — Add an audit table.** Write `OrderAudit` through a third repository. Fail during the audit step and confirm order, inventory, and audit all retain their initial state.

**Exercise 3 — Aggregate with children.** Save `PurchaseOrder` with an `OrderLine` collection, then fail another repository call. Verify both root and children rolled back.

**Exercise 4 — Compare test transactions.** Write one `@SpringBootTest` with `@Transactional` and one without. Explain why the second test proves independent service rollback better.

**Exercise 5 — Checked exception.** Replace the runtime exception with `IOException`. Observe default behavior, then add `rollbackFor` and verify data rolls back.

**Exercise 6 — Swallowed exception.** Catch `DataAccessException` inside the service without rethrowing. Observe that the transaction can commit; then fix it to roll back and retest.

**Exercise 7 — `REQUIRES_NEW`.** Create an audit method using `REQUIRES_NEW`. Make the order transaction roll back and observe the audit record still commits. Explain when this behavior is useful.

**Exercise 8 — Multiple DataSources.** Configure two datasources and two transaction managers. Confirm a local transaction does not automatically roll back operations on the other datasource; explore appropriate solutions for the business case.

**Exercise 9 — Async side effect.** Invoke an `@Async` task from a transactional service. Observe that the other thread does not join the caller's transaction. Redesign using an outbox or after-commit.

**Exercise 10 — `TransactionTemplate`.** Write a test using `TransactionTemplate`, mark rollback-only, and confirm data is not committed.

**Exercise 11 — Production-like database.** Run rollback tests against PostgreSQL/MySQL with Testcontainers. Compare behavior with an embedded database if used by the project.

**Exercise 12 — Transactional outbox.** Write order and outbox event in one transaction. Fail after writing the outbox to confirm both roll back; then commit and simulate a publisher dispatching the event.

### References

- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxies, and rollback rules.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, and `NESTED`.
- [Spring Framework — Transaction-bound Resources](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html): connections/resources bound to transactions.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/index.html): test slices and integration tests.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions, rollback, and commit.
- [Spring Data Relational Reference](https://docs.spring.io/spring-data/relational/reference/): transactions and persistence in Spring Data JDBC.

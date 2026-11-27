# Propagation: REQUIRED, REQUIRES_NEW, and NESTED

In **Spring Data Relational JDBC**, a transaction defines the scope within which database operations commit or roll back together. When one service calls another service, a key question arises: will the called method join the running transaction, create an independent transaction, or create a rollback point inside the current transaction?

Spring manages this behavior through the **propagation** attribute of `@Transactional`. The three modes you most commonly need to distinguish are:

- **`REQUIRED`**: joins the current transaction; creates a new transaction if none exists.
- **`REQUIRES_NEW`**: suspends the current transaction and creates a new physical transaction.
- **`NESTED`**: if a transaction already exists, creates a savepoint for partial rollback; if none exists, behaves like `REQUIRED`.

These modes are not just three ways of writing an annotation. They determine commit scope, rollback behavior, connection holding, and error handling across services. This lesson uses an order-placement example to explain each mode, how to choose among them, and their limitations when running with a JDBC transaction manager.

## 1. What Is Propagation?

Propagation describes how a method annotated with `@Transactional` interacts with any transaction that already exists when the method is called.

For example, an application service creates an order and then calls an inventory service to reserve stock:

~~~text
OrderApplicationService.createOrder()
    |
    +-- PurchaseOrderRepository.save()
    |
    +-- InventoryService.reserve()
            |
            +-- InventoryRepository.update()
~~~

Both services operate on the database. If creating the order and reserving stock must succeed or fail together, `InventoryService.reserve()` needs to join `createOrder()`'s transaction. This is the classic case for `REQUIRED`.

If an audit service must commit independently even when order creation fails, `REQUIRES_NEW` may fit. If a portion of operations can roll back to a savepoint while the rest continues, `NESTED` may fit when the transaction manager supports savepoints.

### 1.1. Logical Transactions vs. Physical Transactions

Spring can create multiple logical transaction scopes across methods annotated with `@Transactional`. Those logical scopes do not necessarily correspond to multiple physical database transactions.

- With `REQUIRED`, multiple logical scopes can share a single physical transaction.
- With `REQUIRES_NEW`, Spring suspends the outer physical transaction and opens an independent physical transaction.
- With `NESTED`, the inner scope uses a savepoint of the current physical transaction.

This distinction is fundamental to understanding why an error in a child method can roll back the parent transaction, why an audit record can persist after the outer transaction rolls back, and why rolling back a nested scope does not necessarily discard all earlier work.

## 2. How to Declare Propagation

Use `Propagation` from the `org.springframework.transaction.annotation` package:

~~~java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
~~~

Example:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void createOrder() {
    // Database operations.
}
~~~

If `propagation` is omitted, `@Transactional` defaults to `Propagation.REQUIRED`:

~~~java
@Transactional
public void createOrder() {
    // Equivalent to REQUIRED.
}
~~~

Place transaction boundaries at the application/service layer around a complete use case. Spring Data JDBC repositories also have default transaction configuration for CRUD methods, but service-level transactions let multiple repository operations join a single business unit.

## 3. REQUIRED: Join the Current Transaction or Create a New One

`REQUIRED` is the default propagation and is usually the right choice for services collaborating on a single business use case.

Rules:

| State when method is called | Behavior of REQUIRED |
|---|---|
| No active transaction | Creates a new transaction |
| Active transaction exists | Joins the current transaction |

### 3.1. Example: Creating an Order and Reserving Stock

Application service:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final InventoryService inventory;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            InventoryService inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        PurchaseOrder order = PurchaseOrder.create(command);
        PurchaseOrder saved = orders.save(order);

        inventory.reserve(command.items());

        return saved.getId();
    }
}
~~~

Inventory service:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve(List<OrderItem> items) {
        for (OrderItem item : items) {
            inventory.decreaseAvailable(item.productId(), item.quantity());
        }
    }
}
~~~

When `createOrder()` is called from outside with no existing transaction:

1. Spring opens a transaction for `createOrder()`.
2. `orders.save()` runs inside that transaction.
3. `inventory.reserve()` is invoked through the bean proxy and joins the running transaction.
4. Inventory updates share the same physical transaction as saving the order.
5. If the transaction commits, both sets of changes commit.
6. If the transaction rolls back, both sets of changes roll back.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as OrderApplicationService
    participant Inventory as InventoryService
    participant DB as Database
    Client->>Order: createOrder()
    Order->>DB: BEGIN transaction T1
    Order->>DB: INSERT purchase_order
    Order->>Inventory: reserve()
    Note over Inventory,DB: REQUIRED joins T1
    Inventory->>DB: UPDATE inventory
    Order->>DB: COMMIT T1
    Order-->>Client: orderId
~~~

The diagram depicts the success path. If updating inventory throws an exception configured for rollback, all of T1 rolls back.

### 3.2. REQUIRED When the Child Service Is Called Standalone

If `InventoryService.reserve()` is called from a context without an active transaction, `REQUIRED` opens a new transaction for that method automatically. Thus, the same service can either join a caller's transaction or start its own when invoked independently.

### 3.3. Failures in a Joined Transaction

An important detail: an inner `REQUIRED` scope shares the same physical transaction as the outer scope. When the child method's interceptor receives an exception eligible for rollback, the shared transaction can be marked **rollback-only**.

Example:

~~~java
@Service
public class InventoryService {

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve() {
        // Update inventory.
        throw new IllegalStateException("Insufficient stock");
    }
}
~~~

Caller catches the exception:

~~~java
@Transactional
public void createOrder() {
    orders.save(newOrder());

    try {
        inventory.reserve();
    } catch (IllegalStateException ex) {
        // Record error and continue processing.
    }

    // Method exits normally.
}
~~~

If the exception from `reserve()` marks the transaction rollback-only, catching the exception in the caller does not clear the rollback-only flag. When `createOrder()` completes, Spring cannot commit the transaction as if no error occurred. The transaction rolls back and the caller may receive `UnexpectedRollbackException`.

This prevents the caller from believing data was committed when a participating scope had already requested a rollback.

### 3.4. Default Rollback Rules

Under Spring's transaction defaults, `RuntimeException` and `Error` trigger rollback. Checked exceptions do not automatically trigger rollback under default rules.

You can configure explicitly:

~~~java
@Transactional(rollbackFor = BusinessException.class)
public void createOrder() throws BusinessException {
    // Database operations.
}
~~~

Or exclude an exception:

~~~java
@Transactional(noRollbackFor = DuplicateNoticeException.class)
public void recordNotice() {
    // Database operations.
}
~~~

Rollback rules must be evaluated alongside propagation. `REQUIRED` shares rollback state with the current transaction; `REQUIRES_NEW` has independent rollback state; `NESTED` can roll back to a savepoint if supported by the transaction manager.

## 4. REQUIRES_NEW: Creating an Independent Physical Transaction

`REQUIRES_NEW` always executes the method in a new physical transaction. If the caller already has an active transaction, Spring suspends it while the new transaction runs.

Rules:

| State when method is called | Behavior of REQUIRES_NEW |
|---|---|
| No active transaction | Creates a new transaction |
| Active transaction exists | Suspends the current transaction and creates a new one |

The inner transaction can commit or roll back independently of the outer transaction.

### 4.1. Example: Writing an Independent Audit Record

Suppose the system must record an order creation attempt even when order creation fails. An audit service can be used:

~~~java
@Service
public class OrderAuditService {

    private final OrderAuditRepository audits;

    public OrderAuditService(OrderAuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(Long orderId, String outcome) {
        audits.save(new OrderAudit(orderId, outcome));
    }
}
~~~

Outer service:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OrderAuditService audit;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            OrderAuditService audit) {
        this.orders = orders;
        this.audit = audit;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(PurchaseOrder.create(command));

        audit.recordAttempt(saved.getId(), "CREATED");

        // Example: a subsequent business step fails.
        validateShipping(command);

        return saved.getId();
    }
}
~~~

Transaction flow:

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as OrderApplicationService
    participant Audit as OrderAuditService
    participant DB as Database
    Client->>Order: createOrder()
    Order->>DB: BEGIN T1
    Order->>DB: INSERT purchase_order
    Order->>Audit: recordAttempt()
    Note over Order: T1 is suspended
    Audit->>DB: BEGIN T2
    Audit->>DB: INSERT order_audit
    Audit->>DB: COMMIT T2
    Audit-->>Order: return
    Note over Order: T1 resumes
    Order->>Order: validateShipping() fails
    Order->>DB: ROLLBACK T1
    Order-->>Client: exception
~~~

In this example, the audit record commits in T2. If the subsequent validation step causes T1 to roll back, the audit record remains because T2 was independent.

### 4.2. When Is REQUIRES_NEW Useful?

Cases where an independent transaction may be appropriate:

- Recording an audit of an attempt or processing outcome that must survive even if the business transaction rolls back.
- Persisting technical state of a task that must commit separately.
- Updating counters or operational data independent of the business transaction, after evaluating consistency implications.
- Saving partial results whose business contract explicitly dictates independent persistence.

Clarify data semantics before using it. If an audit must describe **a committed business event**, writing the audit with `REQUIRES_NEW` before the outer transaction commits can produce false records: the audit claims an order was created while the order ultimately rolled back.

For outbox events that must exist strictly when business changes commit, normally write the outbox inside the **same transaction** as the aggregate—using `REQUIRED`—so both commit or roll back together.

### 4.3. The Outer Transaction Cannot Roll Back What Committed Inside

Example:

1. T1 updates an order.
2. T2 is opened with `REQUIRES_NEW`.
3. T2 writes an audit and commits.
4. T1 encounters an error and rolls back.

Outcome:

- T1's changes are rolled back.
- T2's audit record is retained.

That is the very purpose of an independent transaction. If child data must not persist when parent data rolls back, `REQUIRES_NEW` is the wrong choice.

### 4.4. Connection Cost and Lock-Wait Risk

When the outer transaction is suspended, its connection and resources usually remain held while the new transaction runs. T2 requires a second connection.

This introduces two risks:

**Connection pool exhaustion:** if many concurrent requests each hold T1's connection while waiting for T2 to acquire a new connection, the pool can run out. Requests block on each other and may time out. Size the pool based on nested transactions and actual concurrency.

**Waiting on locks held by the outer transaction:** if T1 has locked a row and T2 attempts to update that same row, T2 may block waiting for T1 to release the lock. Yet T1 is suspended waiting for T2 to finish. This can lead to lock wait timeouts or deadlocks depending on the database and locking behavior.

Do not use `REQUIRES_NEW` carelessly inside large loops or for operations that modify the same rows locked by the outer transaction.

## 5. NESTED: Using a Savepoint Inside the Current Transaction

`NESTED` lets you create a rollback scope inside the current physical transaction using a JDBC **savepoint**.

Rules:

| State when method is called | Behavior of NESTED |
|---|---|
| No active transaction | Acts like REQUIRED and creates a new transaction |
| Active transaction exists | Creates a savepoint inside the current transaction |

Unlike `REQUIRES_NEW`, a nested scope does not have an independent physical transaction. It shares the connection and transaction with the caller.

### 5.1. How Do Savepoints Work?

Suppose the outer transaction has written an order and then calls an optional data step:

~~~text
BEGIN T1
  INSERT purchase_order
  SAVEPOINT S1
    INSERT optional_order_note
    UPDATE optional_shipping_data
  RELEASE S1
COMMIT T1
~~~

If the nested portion fails and rolls back to the savepoint:

~~~text
BEGIN T1
  INSERT purchase_order
  SAVEPOINT S1
    INSERT optional_order_note
    UPDATE optional_shipping_data
  ROLLBACK TO S1
  -- T1 can still continue
  UPDATE purchase_order
COMMIT T1
~~~

Changes before the savepoint remain in T1. Changes after the savepoint inside the nested scope are undone upon rolling back to S1. The outer transaction can continue and commit the rest if the error is handled properly.

### 5.2. Example with a Separate Service

Service handling optional data:

~~~java
@Service
public class OptionalOrderDataService {

    private final OptionalOrderDataRepository data;

    public OptionalOrderDataService(OptionalOrderDataRepository data) {
        this.data = data;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void addOptionalData(Long orderId) {
        data.insertNote(orderId, "Customer requested gift wrapping");
        data.updateShippingPreference(orderId, "GIFT_WRAP");

        validateOptionalData(orderId);
    }
}
~~~

Caller:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OptionalOrderDataService optionalData;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            OptionalOrderDataService optionalData) {
        this.orders = orders;
        this.optionalData = optionalData;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(PurchaseOrder.create(command));

        try {
            optionalData.addOptionalData(saved.getId());
        } catch (OptionalDataException ex) {
            // Discard optional data; outer transaction continues.
        }

        return saved.getId();
    }
}
~~~

If `addOptionalData()` throws an exception that rolls back the nested scope and the caller catches it, T1 can continue with the saved order. This holds only when nested transactions/savepoints are genuinely supported and the exception has not marked the outer transaction rollback-only via another mechanism.

### 5.3. A Succeeding Nested Scope Does Not Commit Independently

If `addOptionalData()` completes normally, changes from the nested scope still belong to T1. Afterwards:

- T1 commits: both outer and nested changes commit together.
- T1 rolls back: both outer and nested changes roll back together.

NESTED does not preserve inner data if the outer transaction fails. If you need that, consider `REQUIRES_NEW` and its consistency implications.

## 6. Requirements for NESTED to Work with Spring Data JDBC

`NESTED` depends on savepoint support in the transaction manager and JDBC driver/database.

In Spring Data JDBC applications, JDBC transaction managers such as `DataSourceTransactionManager` and `JdbcTransactionManager` can support nested transactions via JDBC savepoints. Verify:

- Whether the active transaction manager supports nested transactions.
- Whether nested transaction support is enabled in configuration.
- Whether the JDBC driver and database support savepoints.
- Whether operations share the same transaction manager and connection resource.

Not every transaction manager supports `NESTED`. For instance, you cannot assume `JtaTransactionManager` or a non-savepoint transaction manager provides the same semantics.

If your Spring Data JDBC app uses Spring Boot, inspect the actual transaction manager bean rather than inferring solely from having the Spring Data JDBC dependency.

### 6.1. NESTED Does Not Mean Nested Objects or Nested Aggregates

The word "nested" here refers to a **transaction savepoint**, not:

- One object nested inside another object.
- A child entity declared with `@MappedCollection`.
- An aggregate root inside another aggregate.

Aggregate relationships are governed by the domain model and Spring Data JDBC mapping. Propagation controls only how a transaction scope interacts with an existing transaction.

## 7. Comparing the Three Propagation Modes

| Criterion | REQUIRED | REQUIRES_NEW | NESTED |
|---|---|---|---|
| Outer transaction exists | Joins outer transaction | Suspends outer, opens a new transaction | Creates a savepoint in outer transaction |
| No outer transaction | Creates a new transaction | Creates a new transaction | Behaves like REQUIRED |
| Physical transaction | Shared | Independent transaction | Shared |
| Connection | Usually uses current transaction's connection | Needs a new connection while outer holds its resource | Uses current transaction's connection |
| Inner commit | Does not commit independently | Can commit independently | Does not commit independently |
| Inner rollback | Can mark shared transaction rollback-only | Rolls back new transaction; outer can continue | Rolls back to savepoint if supported |
| Outer rollback | Rolls back all shared changes | Does not undo committed inner transaction | Undoes both outer and nested work in T1 |
| Savepoint support | Not needed | Not needed | Required |
| Common use case | One workflow across multiple services | Intentional independent writes | Try optional work with local rollback |

### 7.1. Quick Selection Flowchart

~~~mermaid
flowchart TD
    A["@Transactional method called"] --> B{"Active transaction exists?"}
    B -->|No| C["All three modes open a new transaction"]
    B -->|Yes| D{"Propagation"}
    D -->|REQUIRED| E["Join current transaction"]
    D -->|REQUIRES_NEW| F["Suspend outer transaction; open independent transaction"]
    D -->|NESTED| G["Create savepoint in current transaction"]
~~~

When no transaction exists yet, all three modes result in a new transaction, though `NESTED` does not create a savepoint because there is no outer transaction to roll back to.

## 8. Isolation, timeout, and readOnly When Joining a Transaction

Propagation determines how a transaction is joined; other `@Transactional` attributes like `isolation`, `timeout`, and `readOnly` must be understood alongside it.

Example:

~~~java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    readOnly = false
)
public void writeAudit() {
    // Write audit data.
}
~~~

Key principles:

- When `REQUIRED` joins an existing transaction, `isolation`/`timeout`/`readOnly` settings on the inner scope generally do not create a new physical transaction to apply independently. The running outer transaction governs the physical attributes.
- `REQUIRES_NEW` creates a new physical transaction and can apply its own transaction settings, depending on the transaction manager and database.
- `NESTED` shares the physical transaction; a savepoint does not establish a separate isolation level for the nested scope.

If you need to detect when a child method requests a different isolation level than the active transaction, `AbstractPlatformTransactionManager` has a `validateExistingTransaction` option. Evaluate this setting per application; do not assume Spring automatically rejects all attribute mismatches when joining.

`readOnly = true` is a hint to the transaction manager and database. It is not a security mechanism guaranteeing all write statements are blocked across every DBMS.

## 9. Transaction Propagation Works Only When Calls Go Through a Proxy

In Spring AOP proxy-based transaction configuration, `@Transactional` applies when calls pass through the Spring bean proxy.

A misleading example:

~~~java
@Service
public class OrderService {

    public void create() {
        saveAudit(); // self-invocation
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit() {
        // Author expects a new transaction.
    }
}
~~~

Calling `this.saveAudit()` inside the same object does not go through the proxy, so the transaction interceptor typically does not apply `REQUIRES_NEW` propagation to this call.

A cleaner organization is moving the part requiring separate propagation into another bean:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit() {
        // Independent transaction.
    }
}
~~~

~~~java
@Service
public class OrderService {

    private final AuditService audit;

    public OrderService(AuditService audit) {
        this.audit = audit;
    }

    @Transactional
    public void create() {
        // Write order in outer transaction.
        audit.saveAudit(); // Called through Spring proxy of AuditService bean.
    }
}
~~~

With proxy-based transaction management, methods generally must be invoked through the proxy, and visibility must align with the proxy type/configuration. Do not rely on internal calls to start a new transaction. AspectJ transaction weaving has different semantics, but it is not the typical default setup in Spring Boot.

Spring JDBC transactions are normally bound to the current thread. If you spawn new threads, use `@Async`, or submit work to an executor, transactions do not automatically carry over to the other thread. Asynchronous work needs its own transaction boundary.

## 10. Choosing Propagation Based on Business Requirements

### Choose REQUIRED When Changes Must Succeed Together

Examples:

- Creating an order and creating order lines belonging to the aggregate.
- Updating order status and updating inventory within one database transaction.
- Writing an aggregate and writing an outbox event that must commit together.
- Multiple services participating in one use case with no need for independent commit.

This is usually the default choice. If the outer transaction rolls back, `REQUIRED` participants roll back too.

### Choose REQUIRES_NEW When an Independent Outcome Is Intentional

Examples:

- Recording an audit of an attempt that must persist even if the main workflow rolls back.
- Persisting an independent operational state with an explicit contract.
- Saving auxiliary data that business requirements explicitly decouple from the outer transaction commit.

Before choosing it, ask:

- Is it acceptable for the inner record to remain when the outer business workflow fails?
- Could it update rows currently locked by the outer transaction?
- Is the connection pool sized for nested transactions?
- Does committing separately create misleading or inconsistent data?

### Choose NESTED When Partial Rollback Inside the Same Transaction Is Needed

Examples:

- Attempting to apply optional data.
- Processing a group of operations that can be skipped on failure while keeping the main business work valid.
- Rolling back to a savepoint while preserving earlier changes in the same transaction.

Use only when the transaction manager supports savepoints and the caller can handle the error to continue. If the nested scope succeeds and the outer transaction rolls back, all changes are still rolled back.

## 11. Common Design Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Caller catches exception yet entire transaction rolls back | Inner REQUIRED method marked shared transaction rollback-only | Understand rollback rules; do not expect catching an exception to clear rollback-only |
| Audit written, yet audit disappears along with the order | Audit uses REQUIRED and joined outer transaction | Use REQUIRES_NEW only if the audit must truly survive independently |
| Audit says order was created even though order does not exist | Audit written with REQUIRES_NEW before order creation commits | Write outbox/commit-confirmed audit in the same transaction if consistency is needed |
| REQUIRES_NEW blocks for a long time | Outer transaction holds locks needed by inner transaction | Avoid modifying the same rows; revisit transaction boundaries |
| Requests hang when pool runs out | Outer holds a connection while inner needs a new connection | Size connection pool for concurrency and nested transactions |
| NESTED does not create a savepoint | Transaction manager or driver lacks support | Verify JDBC transaction manager and savepoint support |
| Using NESTED, yet outer rollback loses inner data | Nested scope does not commit independently | Use REQUIRES_NEW if an independent commit is genuinely needed |
| `@Transactional` on an internal method has no effect | Self-invocation bypasses the proxy | Extract method to another bean or use appropriate weaving |
| Transaction does not cover async work | Thread-bound transactions do not automatically transfer to new threads | Open a dedicated transaction inside the worker/task |
| Choosing propagation to optimize speed | Confusing propagation with batching/bulk processing | Choose based on commit/rollback semantics; measure performance separately |

## 12. Comprehensive Example: Placing an Order, Auditing, and Handling Optional Data

One use case might use all three modes, though only when each part has a clear requirement:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final InventoryService inventory;
    private final OrderAuditService audit;
    private final OptionalOrderDataService optionalData;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            InventoryService inventory,
            OrderAuditService audit,
            OptionalOrderDataService optionalData) {
        this.orders = orders;
        this.inventory = inventory;
        this.audit = audit;
        this.optionalData = optionalData;
    }

    @Transactional
    public Long create(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create(command)
        );

        // REQUIRED: same transaction as order creation.
        inventory.reserve(command.items());

        // NESTED: optional part can roll back to a savepoint.
        try {
            optionalData.addOptionalData(saved.getId());
        } catch (OptionalDataException ex) {
            // Order can still proceed if business rules allow.
        }

        // REQUIRES_NEW: record attempt independently per audit policy.
        audit.recordAttempt(saved.getId(), "PROCESSING");

        return saved.getId();
    }
}
~~~

Called services must be separate Spring beans with their respective propagation settings. This example only illustrates the mechanism; in a real system, audit statuses should be named accurately. Recording `PROCESSING` in an independent transaction means that status may remain even if the order creation transaction subsequently rolls back.

If the requirement is "only record ORDER_CREATED when the order actually commits," save an outbox event in the same REQUIRED transaction as the order. Do not use REQUIRES_NEW for that commit-confirmation event.

## 13. Hands-On Exercises

### Exercise 1 — REQUIRED and Shared Rollback

1. Create `OrderApplicationService.createOrder()` annotated with `@Transactional`.
2. Call `InventoryService.reserve()` with `REQUIRED`.
3. Have the inventory service throw `IllegalStateException` after updating one item.
4. Invoke the use case and inspect both the order and inventory.
5. Verify both changes roll back together.

### Exercise 2 — REQUIRED and Rollback-Only

1. Have a child REQUIRED method throw a runtime exception.
2. Catch the exception in the caller.
3. Let the caller finish normally.
4. Observe the rollback and `UnexpectedRollbackException` if the transaction was marked rollback-only.
5. Repeat with a checked exception and `rollbackFor` configured.

### Exercise 3 — REQUIRES_NEW

1. Create `OrderAuditService.recordAttempt()` with REQUIRES_NEW.
2. Call it inside the order-creation transaction.
3. Cause the outer transaction to roll back after the audit commits.
4. Verify the audit record persists while the order is rolled back.
5. Observe connection pool behavior and test having the inner transaction update a row locked by the outer transaction.

### Exercise 4 — NESTED

1. Use a JDBC transaction manager that supports savepoints.
2. Create `OptionalOrderDataService.addOptionalData()` with NESTED.
3. Write partial data and intentionally throw a runtime exception.
4. Catch the exception in the caller and continue updating the order.
5. Verify data before the savepoint remains while data after the savepoint rolls back.
6. Cause the outer transaction to roll back and verify all changes in T1 are lost.

### Exercise 5 — Proxies and Self-Invocation

1. Place a REQUIRES_NEW method in the same class as the caller.
2. Invoke it via `this.method()` and observe the transaction.
3. Move the method to another bean.
4. Invoke via dependency injection and compare.

## 14. Conclusion

`REQUIRED` joins an existing transaction or creates a new one. It is the default choice when multiple services must commit or roll back together for a use case. Because REQUIRED scopes share a physical transaction, an error in one scope can mark the entire transaction rollback-only, even if the caller catches the exception.

`REQUIRES_NEW` suspends the outer transaction and creates an independent physical transaction. The inner scope can commit even if the outer transaction rolls back, though consistency, connection pool sizing, and database locks must be carefully evaluated.

`NESTED` creates a savepoint inside the current transaction. It enables partial rollback while letting the outer transaction continue when the transaction manager supports JDBC savepoints. A succeeding nested scope still depends on the outer transaction committing.

Choose propagation based on business commit/rollback semantics. Place transaction boundaries on services, invoke methods through Spring proxies, verify rollback rules, and inspect the actual transaction manager. Once you understand physical transactions, savepoints, and rollback scopes, you can coordinate multiple Spring Data JDBC services while keeping data consistent.

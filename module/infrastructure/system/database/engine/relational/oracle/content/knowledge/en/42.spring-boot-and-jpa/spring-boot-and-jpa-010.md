# @Transactional, Propagation, and Proxy-Based Transaction Boundaries

In Spring Boot and JPA, the **@Transactional** annotation describes how a method invocation participates in a transaction. The annotation itself does not magically turn every line inside a method into a transaction. In Spring's default mode, a **proxy** sitting in front of the bean intercepts external calls, reads @Transactional metadata, starts or joins a transaction, invokes the actual method, and then commits or rolls back when the method completes.

The crucial point is that **a transaction boundary is created when a call passes through the proxy**. If one method calls another method on the same object via `this`, the internal call normally bypasses the proxy, and the annotation on the called method may not be applied. Understanding this boundary prevents bugs such as `REQUIRES_NEW` failing to run in a new transaction, rollbacks not happening as expected, transactions ending prematurely, or seemingly independent operations rolling back together with outer operations.

This lesson explains how Spring proxies enforce @Transactional, the semantics of each propagation mode, how the transaction manager and JPA persistence context participate, rollback rules, interactions with Oracle Database, testing, and sound design patterns.

## 1. What Is a Transaction in a Spring Application?

A transaction is a unit of work handled according to ACID properties:

- **Atomicity**: either all changes commit, or uncommitted changes roll back.
- **Consistency**: the transaction must preserve data rules and constraints.
- **Isolation**: concurrent transactions must not observe intermediate states violating the chosen isolation level.
- **Durability**: once committed successfully, committed data is guaranteed by the database's durability mechanisms.

For example, processing an order may include:
1. Creating an ORDER record.
2. Creating ORDER_ITEM records.
3. Decrementing inventory quantity.
4. Recording internal payment state.
5. Recording an event to send to another system.

If step 3 fails, the database changes in steps 1 and 2 typically must roll back together. A service-layer transaction can wrap these repository calls to achieve this.

### 1.1. Transaction Boundary

A transaction boundary defines when a transaction begins and ends. In Spring declarative transactions, the boundary normally wraps a proxy-intercepted method call:

~~~text
Caller
  |
  v
Spring proxy
  |
  +--> read @Transactional
  |
  +--> begin or join transaction
  |
  +--> invoke target method on target bean
  |
  +--> commit or rollback
  |
  v
Caller receives result or exception
~~~

Commit happens after the target method returns normally and before the proxied call returns to the caller. If commit/flush throws an error, the caller can still receive an exception even though the method body reached its return statement.

### 1.2. Where Should Transaction Boundaries Live?

Typically, place transaction boundaries on service methods representing a business use case:

- Creating an order.
- Finalizing an invoice.
- Transitioning payment status.
- Allocating inventory.
- Canceling a subscription.
- Updating multiple consistency-coupled aggregates.

Repositories focus on data access. One transaction can invoke multiple repositories and keep their changes in a single business unit of work.

Avoid wrapping an entire request in an overly broad transaction if the request makes HTTP calls, sends emails, waits on users, or processes large files. Long transactions hold connections and locks longer, increasing contention and timeout risks.

## 2. Spring Applies @Transactional via Proxies

In Spring Boot, transaction annotations are typically enforced via a Spring AOP proxy. The proxy is the object injected into callers; the target is the object containing the business logic.

### 2.1. Calls Going Through the Proxy

Suppose `OrderService` is a Spring-managed bean and a caller injects `OrderService`:

~~~java
@Service
public class OrderService {

    @Transactional
    public void placeOrder(Long orderId) {
        // read and update data
    }
}
~~~

When another bean calls `orderService.placeOrder(...)`, the call passes through the proxy. The proxy inspects transaction metadata and coordinates the transaction manager before and after invoking the target method.

### 2.2. Self-Invocation Bypasses the Proxy

A common pitfall:

~~~java
@Service
public class ReportService {

    public void generateAll() {
        generateOne(); // internal self-invocation via this
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void generateOne() {
        // write report data
    }
}
~~~

When a caller invokes `generateAll()` through the proxy, the proxy intercepts only `generateAll`. Inside the target object, calling `generateOne()` is a direct call on `this`. It does not re-enter the proxy, so `REQUIRES_NEW` on `generateOne()` is ignored under default proxy mode.

Consequence: `generateOne()` may run without a new transaction, or run inside an existing transaction if `generateAll()` was itself invoked via an outer transaction boundary. Never rely solely on an annotation on `generateOne()` to infer runtime behavior.

### 2.3. Fixing Self-Invocation

**Preferred approach: move the transaction boundary to another bean.**

~~~java
@Service
public class ReportItemService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void generateOne(Long reportId) {
        // write part of report in a separate transaction
    }
}

@Service
public class ReportService {

    private final ReportItemService reportItemService;

    public ReportService(ReportItemService reportItemService) {
        this.reportItemService = reportItemService;
    }

    public void generateAll(List<Long> reportIds) {
        for (Long id : reportIds) {
            reportItemService.generateOne(id);
        }
    }
}
~~~

`ReportService` invokes a separate proxied bean, so `generateOne()` passes through the proxy.

Other options:
- Use `TransactionTemplate` when an explicit transaction boundary is needed inside the same class.
- Self-inject a proxy reference in special cases, though this hurts readability and can create circular dependencies.
- Use AspectJ weaving if the project deliberately adopts it; AspectJ can intercept self-invocation, but requires dedicated weaving setup and operations.

Avoid defaulting to `AopContext.currentProxy()` to solve every self-invocation. That requires exposing proxies and couples code directly to the AOP context.

### 2.4. JDK Dynamic Proxies and CGLIB

Spring can generate:
- **JDK dynamic proxies** based on interfaces.
- **Class-based proxies (CGLIB)** generating a subclass of the target class.

With JDK proxies, callers typically reference the bean via its interface; intercepted methods must exist on the interface. With class-based proxies, Spring subclasses the target, so `private` or `final` methods cannot be overridden/intercepted, and `final` classes cannot be proxied this way.

For clear, proxy-agnostic behavior, place `@Transactional` on `public` service methods called from other beans. Inspect your application's proxy type and AOP config if non-standard method visibility is used.

### 2.5. Calls That Commonly Bypass Proxies

Watch out for:
- A method calling another method on the same instance via `this`.
- Instantiating objects manually with `new` instead of obtaining beans from the Spring container.
- Calling methods from constructors or initialization hooks before the proxy is ready.
- Calling `private`/`final` methods that class proxies cannot intercept.
- Callers holding a reference to the unwrapped target object instead of the proxy.

Having an annotation in source code does not prove runtime calls pass through the interceptor.

## 3. Configuring Transactions in Spring Boot and JPA

Spring Boot typically auto-configures a transaction manager when Spring Data JPA, `EntityManagerFactory`, and a DataSource are present.

### 3.1. Key Components

- **@Transactional**: declares metadata for a transaction boundary.
- **TransactionInterceptor**: interceptor that enforces the metadata.
- **PlatformTransactionManager**: coordinates imperative transactions.
- **JpaTransactionManager**: integrates Spring transactions with the JPA EntityManager.
- **EntityManager**: manages the persistence context and entity state changes.
- **JDBC Connection**: physical connection to Oracle Database.
- **TransactionSynchronizationManager**: holds thread-bound transaction/resource state in standard imperative execution.

When a transaction begins, `JpaTransactionManager` coordinates with `EntityManagerFactory` and the DataSource to bind an EntityManager/connection to the transaction context. Repositories sharing the same `EntityManagerFactory` and DataSource participate in the active transaction.

### 3.2. Service Layer Example

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void placeOrder(Long orderId, Long productId, int quantity) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        Inventory inventory = inventoryRepository.findByProductId(productId)
            .orElseThrow(() -> new IllegalArgumentException("Product not found"));

        inventory.reserve(quantity);
        order.confirm();
    }
}
~~~

When both repositories share the same `JpaTransactionManager`, entity changes are managed in the same transaction. If an operation throws an exception matching rollback rules, the transaction rolls back.

### 3.3. When Is @EnableTransactionManagement Needed?

In Spring Boot apps using standard auto-configuration, transaction management is typically enabled automatically based on configuration and dependencies. Plain Spring applications or custom setups may need `@EnableTransactionManagement`.

Do not add it mechanically if Boot already configures transaction infrastructure. What matters is verifying a transaction manager exists and proxies are actually created.

### 3.4. Selecting a Transaction Manager with Multiple DataSources

If an application has multiple DataSources or `EntityManagerFactory` beans, specify the transaction manager explicitly:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void createOrder() {
    // operations against orders database
}
~~~

The qualifier name must match the configured transaction manager bean. Without it, Spring falls back to a primary/default manager or fails due to ambiguity.

A single JPA transaction manager does not automatically make two independent databases commit atomically together. Distributed transactions require properly configured JTA/XA; in many systems, outbox/saga patterns are more appropriate.

## 4. What Is Propagation?

Propagation specifies how a `@Transactional` method behaves when a caller already has an active transaction or has none.

Propagation does not decide whether the proxy intercepts the call. First the call must reach the transaction interceptor; only then is propagation evaluated.

Spring defines these modes:
- REQUIRED
- REQUIRES_NEW
- SUPPORTS
- NOT_SUPPORTED
- MANDATORY
- NEVER
- NESTED

The default on `@Transactional` is `REQUIRED`.

## 5. REQUIRED — Join Existing Transaction or Create a New One

`REQUIRED` is the default propagation and fits most business use cases.

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void createOrder() {
    // business work
}
~~~

Behavior:
- If no transaction exists: creates a new transaction.
- If a compatible transaction exists: joins the existing transaction.
- An inner method does not create a separate physical transaction when joining an outer one.

### 5.1. Two REQUIRED Methods Sharing One Transaction

~~~java
@Service
public class OrderService {

    private final InventoryService inventoryService;

    @Transactional
    public void placeOrder() {
        // transaction T1 begins
        inventoryService.reserve();
        // transaction T1 commits when placeOrder succeeds
    }
}

@Service
public class InventoryService {

    @Transactional
    public void reserve() {
        // joins T1, does not create T2
    }
}
~~~

If `reserve()` fails under a rollback rule, transaction T1 may be marked rollback-only. Even if `OrderService` catches the exception and continues, T1 will still be unable to commit.

### 5.2. REQUIRED Creates a Logical Scope, Not Necessarily a New Physical Transaction

Each intercepted method gets its own logical transaction scope, while nested `REQUIRED` scopes generally share one physical transaction. Therefore, a rollback-only flag set in an inner scope affects the entire physical transaction.

This is why catching an exception in an outer method does not guarantee the transaction can commit.

### 5.3. When to Use REQUIRED?

Use when multiple steps must succeed or fail together:
- Creating an order and its order items.
- Deducting inventory alongside updating order status.
- Writing an invoice and its invoice lines.
- Updating multiple tables within one use case.
- Calling multiple repositories that must commit together.

## 6. REQUIRES_NEW — Always Create a New Physical Transaction

`REQUIRES_NEW` instructs Spring to create an independent transaction. If the caller already has a transaction, the outer transaction is suspended while the new one runs.

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord() {
    // independent transaction
}
~~~

### 6.1. Flow Diagram

~~~text
Outer method
  |
  +--> Outer transaction T1 active
          |
          +--> call inner bean through proxy
                  |
                  +--> suspend T1
                  |
                  +--> begin T2
                  |
                  +--> execute inner method
                  |
                  +--> commit/rollback T2
                  |
                  +--> resume T1
  |
  +--> continue T1
  |
  +--> commit/rollback T1
~~~

### 6.2. T2 Can Commit Even If T1 Rolls Back

Example:
- T1 creates an order.
- T2 writes an audit record with `REQUIRES_NEW` and commits.
- Afterward T1 hits an error and rolls back.

T2's audit record persists because it committed independently. This is appropriate if audits must record failed attempts, but inappropriate if the audit record must exist only when the order commits.

### 6.3. Connection Pool Exhaustion Risk

While T1 holds a connection and is suspended, T2 may need a second connection. If many concurrent threads each hold a connection for T1 and wait for a second connection for `REQUIRES_NEW`, the pool can deadlock/exhaust.

For example, with a 10-connection pool and 10 requests in outer transactions, if all 10 invoke an inner `REQUIRES_NEW` needing another connection, all threads can block until timeout. Size the pool and concurrency for nested transactions, or redesign boundaries.

### 6.4. Lock Conflicts Between T1 and T2

T1 may hold a row lock. If T2 tries to update the very same row T1 locked, T2 must wait for T1 to finish—while T1 is waiting for T2 to finish before resuming. This causes lock wait timeouts or self-blocking by design.

Never use `REQUIRES_NEW` to update the same data locked by the outer transaction.

### 6.5. JPA Persistence Context

The new transaction gets its own persistence context/transactional resources managed by the transaction manager. When T2 commits, database rows change independently; entities held in T1's persistence context can become stale. Once T1 resumes, do not assume managed entities in T1 automatically reflect T2's updates.

If fresh data is needed, refresh entities, clear/reload, or design T1 not to hold conflicting state.

### 6.6. When to Use REQUIRES_NEW?

Suitable for genuinely independent operations:
- Writing audits independent of business outcome.
- Persisting retry/failure state that must survive outer transaction rollback.
- Recording an independent work unit in a batch.
- Updating metrics/technical records where separate commits are explicitly required.

Never use it just to "make sure it commits." Splitting transactions changes consistency semantics and can leave orphan records behind when primary data rolls back.

## 7. NESTED — Savepoints Inside a Physical Transaction

`NESTED` represents a nested transaction scope backed by a savepoint if supported by the transaction manager. It is not the same as `REQUIRES_NEW`.

~~~java
@Transactional(propagation = Propagation.NESTED)
public void updateOptionalPart() {
    // can roll back to savepoint
}
~~~

### 7.1. Key Differences

- `NESTED` typically shares the physical transaction and creates a savepoint.
- `REQUIRES_NEW` suspends the outer transaction and starts a separate physical transaction.
- Rolling back a nested scope reverts to the savepoint while allowing the outer transaction to continue.
- Committing a nested scope is not independent of the outer commit; an outer rollback still rolls back all changes in the physical transaction.

### 7.2. Support Depends on the Transaction Manager

Not every transaction manager supports nested transactions. `DataSourceTransactionManager` can support JDBC savepoints. `JpaTransactionManager` does not provide full nested JPA persistence-context semantics; savepoint support requires explicit configuration and generally only makes sense for direct JDBC access on the connection.

For JPA entities already modified in the persistence context, rolling back to a JDBC savepoint does not automatically revert Java object state inside the `EntityManager`. This can leave the persistence context out of sync with the database.

Therefore, do not assume `NESTED` behaves like full nested transactions in JPA. Verify the transaction manager, `nestedTransactionAllowed`, JDBC access, and entity state handling before using it.

### 7.3. When to Consider NESTED?

- Using JDBC and needing partial rollback to a savepoint.
- The transaction manager is verified to support savepoints.
- The application cleanly accounts for persistence context state.
- Tests prove state consistency after a nested rollback.

If an independent commit unit is needed, `NESTED` does not replace `REQUIRES_NEW`.

## 8. SUPPORTS — Join If a Transaction Exists

`SUPPORTS` allows a method to join an active transaction without creating a new one if none exists.

~~~java
@Transactional(propagation = Propagation.SUPPORTS)
public List<Order> findOrders() {
    return orderRepository.findRecentOrders();
}
~~~

Behavior:
- Outer transaction exists: joins that transaction.
- No transaction exists: runs without an actual transaction; some transaction synchronization may still be active depending on manager/config.

`SUPPORTS` is often used for read operations that can run inside or outside a transaction. Do not rely on it for write atomicity when callers lack a transaction.

If a method needs a transaction to ensure multiple SQL statements see a consistent scope, use `REQUIRED`.

## 9. NOT_SUPPORTED — Temporarily Suspend Existing Transaction

`NOT_SUPPORTED` runs a method outside any transaction. If the caller has an active transaction, Spring suspends it for the duration of the method.

~~~java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void exportLargeReport() {
    // runs without an enclosing transaction
}
~~~

Useful for:
- Exporting large reports without holding a long database transaction.
- Performing an operation that should not hold outer transaction locks.
- Running an independent step that does not belong in the current transaction.

Note: repository calls inside the method may still start their own transactions if the called repository/service has its own boundary. `NOT_SUPPORTED` does not prohibit downstream code from opening transactions.

When the method finishes, the outer transaction resumes.

## 10. MANDATORY — Require Caller to Have an Active Transaction

`MANDATORY` requires an active transaction. If none exists, Spring throws `IllegalTransactionStateException`.

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public void updateWithinUseCase() {
    // must be called within an existing transaction
}
~~~

Useful for helper/service methods that only make sense as part of a larger transactional use case. It catches callers that forgot to open a transaction.

Do not use `MANDATORY` on service APIs meant to be invoked standalone from multiple entry points.

## 11. NEVER — Prohibit Running Inside a Transaction

`NEVER` requires that no transaction be active. If the caller has an active transaction, Spring throws `IllegalTransactionStateException`.

~~~java
@Transactional(propagation = Propagation.NEVER)
public void runOutsideTransaction() {
    // must only be called when no transaction is active
}
~~~

`NEVER` differs from `NOT_SUPPORTED`:
- `NEVER` rejects the call if the caller has a transaction.
- `NOT_SUPPORTED` suspends the caller's transaction and runs non-transactionally.

`NEVER` helps enforce that an operation is never invoked inside a transaction by design. Still, audit all callers and call paths before applying it.

## 12. Propagation Summary Table

| Propagation | Transaction Currently Active | No Active Transaction |
| --- | --- | --- |
| REQUIRED | Joins current transaction | Creates a new transaction |
| REQUIRES_NEW | Suspends current transaction, creates a new one | Creates a new transaction |
| NESTED | Creates nested scope/savepoint if supported | Typically creates a new transaction |
| SUPPORTS | Joins current transaction | Runs without a transaction |
| NOT_SUPPORTED | Suspends current transaction, runs non-transactionally | Runs without a transaction |
| MANDATORY | Joins current transaction | Throws exception |
| NEVER | Throws exception | Runs without a transaction |

This table summarizes general semantics. `NESTED` savepoint behavior and synchronization details depend on the transaction manager.

## 13. Default Rollback Rules

In Spring declarative transactions, by default:
- `RuntimeException` and subclasses: roll back.
- `Error`: rolls back.
- Checked exceptions: do not roll back by default.

This often surprises developers because Java allows methods to declare `throws Exception`, yet Spring does not assume every checked exception demands a rollback.

### 13.1. Checked Exception Example

~~~java
@Transactional
public void importOrder() throws IOException {
    orderRepository.save(...);
    throw new IOException("File format invalid");
}
~~~

Under default rollback rules, `IOException` is a checked exception, so the transaction does not automatically roll back on it. When the exception exits the proxy, the transaction may commit before the caller receives the exception.

### 13.2. Using rollbackFor

~~~java
@Transactional(rollbackFor = IOException.class)
public void importOrder() throws IOException {
    orderRepository.save(...);
    throw new IOException("File format invalid");
}
~~~

Or with a checked business exception:

~~~java
@Transactional(rollbackFor = PaymentRejectedException.class)
public void capturePayment() throws PaymentRejectedException {
    // operations to roll back when payment is rejected
}
~~~

### 13.3. Using noRollbackFor

When a specific exception represents a business outcome that should still commit:

~~~java
@Transactional(noRollbackFor = DuplicateNotificationException.class)
public void registerNotification() {
    // handle per defined semantics
}
~~~

Only use `noRollbackFor` when post-exception data remains consistent and committing is intentional. Never disable rollback merely to suppress errors.

### 13.4. Strongest Matching Rule

When multiple rollback rules match, Spring selects the most specific/highest-precedence rule per transaction attribute rules. Specify concrete exception classes rather than broad string patterns that can match unintended exceptions.

## 14. Catching Exceptions Inside a Transaction

Catching exceptions changes what the interceptor sees.

### 14.1. Catching Without Rethrowing

~~~java
@Transactional
public void processOrder() {
    try {
        repository.save(...);
        paymentService.record(...);
    } catch (RuntimeException ex) {
        log.error("Processing failed", ex);
    }
}
~~~

If the exception is caught and the method returns normally, the interceptor treats the method as successful and attempts to commit. If an inner `REQUIRED` scope already marked the transaction rollback-only, the commit will still fail.

### 14.2. Rethrowing the Exception

~~~java
@Transactional
public void processOrder() {
    repository.save(...);
    paymentService.record(...);
}
~~~

When a `RuntimeException` exits the method through the proxy, the transaction interceptor applies the default rollback rule.

### 14.3. Marking Rollback-Only

When you must catch an exception to return a result or log it, while still wanting the transaction to roll back:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public Result processOrder() {
    try {
        repository.save(...);
        return Result.success();
    } catch (RuntimeException ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return Result.failure(ex.getMessage());
    }
}
~~~

This is an imperative hook tied to the active transaction status. Only call it inside a managed transaction boundary; do not use it as a substitute for clean exception design.

### 14.4. UnexpectedRollbackException

Scenario:
1. Outer method opens T1.
2. Inner `REQUIRED` method joins T1.
3. Inner method throws `RuntimeException`, marking the transaction rollback-only.
4. Outer method catches the exception and does not rethrow.
5. Outer method returns normally.
6. Spring attempts to commit T1, but the transaction is rollback-only.

The caller receives `UnexpectedRollbackException`. This signals that the outer scope expected to commit while the physical transaction was already marked rollback-only.

Never catch and ignore `UnexpectedRollbackException`. Identify which scope marked rollback-only and define the proper semantics.

## 15. Transaction Timeout, readOnly, and Isolation

Beyond propagation, `@Transactional` offers attributes controlling transaction behavior.

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 30,
    readOnly = true
)
public List<Order> findRecentOrders() {
    return orderRepository.findRecentOrders();
}
~~~

### 15.1. Isolation

Isolation defines how a transaction sees changes from concurrent transactions. With Oracle Database, common levels are `READ COMMITTED` and `SERIALIZABLE`. Oracle provides statement-level read consistency in `READ COMMITTED`; `SERIALIZABLE` provides transaction-level consistency with its own rules.

Spring's `isolation` attribute typically takes effect only when starting a new physical transaction. When joining an existing transaction, the outer transaction's isolation usually governs.

You can configure `validateExistingTransaction` to reject cases where an inner scope requests different isolation/read-only settings than the active transaction rather than silently ignoring the mismatch.

### 15.2. Timeout

`timeout` bounds transaction duration as supported by the transaction manager and underlying resources. It does not replace query timeouts or socket timeouts. Individual SQL statements may need dedicated JDBC/JPA timeouts.

When joining an existing transaction, an inner scope's timeout does not start an independent timer.

### 15.3. Read-Only

`readOnly=true` is a hint to the transaction manager/provider. Hibernate may optimize flush behavior or skip dirty checking in certain setups. It is not a universal security barrier blocking all database writes.

If database-level write prevention is required, enforce database privileges or a dedicated, tested read-only mechanism.

### 15.4. Class-Level vs. Method-Level Attributes

You can place `@Transactional` on a class as a default for its methods and override on specific methods. Method-level metadata takes precedence over class-level metadata.

Explicitly declare propagation on methods using non-default semantics, especially `REQUIRES_NEW`, `NOT_SUPPORTED`, and `MANDATORY`.

## 16. JPA Persistence Context, Flush, and Commit

JPA manages entities inside a persistence context. Java object mutations are not necessarily sent immediately to Oracle.

### 16.1. Dirty Checking

Example:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
}
~~~

The entity is managed. Upon flush, Hibernate/JPA detects the change and issues a SQL `UPDATE`. Calling `repository.save(customer)` is not strictly required for managed entities.

### 16.2. Flush Is Not Commit

Flushing synchronizes persistence context changes to the database connection. It does not end the transaction or make changes visible to other transactions like a commit.

~~~java
@Transactional
public void updateAndFlush(Long id) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName("New name");
    entityManager.flush(); // SQL is sent, transaction remains open
    // commit happens when method exits through proxy
}
~~~

If a `RuntimeException` occurs after `flush()` and the transaction rolls back, the sent SQL changes still roll back.

### 16.3. Commits Can Surface Late Errors

Constraint violations, deadlocks, or write errors can occur at flush/commit rather than on `save()`. Because the interceptor commits after the target method returns, exceptions may arise when the caller thought the method had finished.

### 16.4. Persistence Context and Transactions

A persistence context can outlive a single SQL statement, so design transaction boundaries cleanly. Avoid keeping entities managed across multiple requests or holding transactions open during slow processing.

## 17. Transactions with Oracle Database

Spring coordinates transactions at the application layer; Oracle Database enforces commit, rollback, locking, and consistency on the server.

### 17.1. Oracle's Default READ COMMITTED

Oracle Database defaults to `READ COMMITTED`. Each SQL statement sees data committed at the start of that statement, plus the current transaction's own changes. One transaction can see different results across two `SELECT` statements if another transaction commits in between.

This is statement-level read consistency, not a fixed snapshot for the entire transaction.

### 17.2. Row Locks Are Held Until Transaction End

`UPDATE`/`DELETE` statements or `SELECT FOR UPDATE` hold row locks until commit or rollback. Long transactions keep locks held longer, increasing blocking and deadlock risks.

Example:
- T1 updates an inventory row without committing yet.
- T2 wants to update the same row and blocks.
- If T1 calls a slow service or waits on HTTP before committing, T2 stays blocked longer than necessary.

Avoid calling external APIs or waiting on user input while holding a database transaction whenever possible.

### 17.3. DDL and Implicit Commits

Oracle DDL has implicit-commit semantics. Statements like `CREATE`, `ALTER`, and `DROP` commit the current transaction per Oracle rules. Thus, `@Transactional` does not make DDL roll back alongside ordinary DML.

Never put schema migrations or arbitrary DDL inside business service methods expecting full rollback.

### 17.4. Connections Must Belong to the Same Transaction Manager

When JPA and `JdbcTemplate` share a DataSource integrated with the appropriate transaction manager, JDBC calls join the same transaction. Opening a separate `DriverManager` connection or using another DataSource places those calls outside the JPA transaction.

Never open connections manually with `DriverManager` inside `@Transactional` and expect them to join Spring's transaction.

## 18. Transaction Boundaries and External Side Effects

Database transactions only guarantee atomicity for resources coordinated by the transaction manager. They do not automatically roll back:
- HTTP requests to payment providers.
- Sent emails.
- Messages published to brokers.
- Files written to the filesystem.
- Calls to other microservices.

### 18.1. Publishing Messages Before Commit

If a service writes an order and publishes a message before committing:
- The consumer may process the message.
- Then the database transaction rolls back.
- The consumer acted on an event for an order that does not exist.

If it commits first and then publishes:
- The database commits successfully.
- The application crashes before publishing the message.
- The event is lost.

### 18.2. Transactional Outbox

A common pattern:
1. Within the same database transaction, write business data and an outbox row.
2. Commit both together.
3. A worker reads the outbox and publishes messages.
4. Mark the outbox row as sent.
5. Consumers process idempotently to tolerate duplicates.

The outbox makes event creation atomic with business data. Message delivery remains eventual and still requires retries/idempotency.

### 18.3. AFTER_COMMIT Events

Spring provides `@TransactionalEventListener` with phase `AFTER_COMMIT` to trigger certain side effects after commit:

~~~java
@Component
public class OrderEventListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        // send notification after transaction has committed
    }
}
~~~

`AFTER_COMMIT` listeners avoid sending notifications before the transaction commits. However, the process can still crash after commit and before the listener finishes; when high reliability is required, an outbox is usually preferable.

If an `AFTER_COMMIT` listener needs to write to the database in a new transaction, it can call another bean annotated with `REQUIRES_NEW`. Ensure the call passes through a proxy and handle retries if side effects fail.

## 19. Transactions in Async and Other Threads

In standard imperative mode, Spring binds transaction resources to the current thread. Transactions do not automatically propagate across threads.

### 19.1. @Async Does Not Inherit Transactions

~~~java
@Service
public class ImportService {

    @Transactional
    public void importBatch() {
        asyncWorker.processAsync();
    }
}

@Service
public class AsyncWorker {

    @Async
    public void processAsync() {
        // runs on a different thread
    }
}
~~~

`importBatch()`'s transaction does not enclose `processAsync()`. If the async worker needs a transaction, declare the boundary on the worker method:

~~~java
@Async
@Transactional
public void processAsync() {
    // separate transaction on worker thread
}
~~~

### 19.2. CompletableFuture

If an imperative method opens a transaction and returns a `CompletableFuture`, the transaction typically ends when the method returns the future, without waiting for async work to finish. Never treat the caller thread's transaction as active inside async callbacks.

### 19.3. Reactive Transactions

Reactive transaction managers typically store transaction context in the Reactor Context rather than `ThreadLocal`. Use appropriate reactive transaction support and reactive database drivers; never mix imperative JPA `EntityManager` with reactive transactions expecting a shared transaction context.

## 20. Choosing Propagation by Use Case

| Need | Common Choice | Notes |
| --- | --- | --- |
| Multiple business steps must commit/roll back together | REQUIRED | Default choice |
| Write independent audit even if main transaction rolls back | REQUIRES_NEW | Consumes a second connection; consider outbox/audit policy |
| Partial JDBC work needs rollback to savepoint | NESTED | Requires manager support; JPA persistence context has limits |
| Read can join caller's transaction without requiring one | SUPPORTS | Does not guarantee atomicity when run standalone |
| Run outside an active transaction | NOT_SUPPORTED | Suspends caller's transaction |
| Helper requires caller to already have a transaction | MANDATORY | Fails fast if caller forgot a boundary |
| Prohibit calling inside a transaction | NEVER | Throws exception if a transaction exists |

Never pick propagation solely from a vague wish for "this method to run separately." Ask:
- Which data must commit together?
- When the outer transaction rolls back, should inner data stay?
- Does the inner method need to read uncommitted outer data?
- Does the outer transaction hold any locks?
- Are enough connections available for nested transactions?
- Does the call actually go through a proxy?

## 21. Complete Example: REQUIRED and REQUIRES_NEW

Suppose a system creates orders and records audits. Orders must roll back on insufficient inventory, while failure audits must survive to aid investigation.

~~~java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(Long orderId, String reason) {
        auditRepository.save(new AuditRecord(orderId, reason));
    }
}

@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;
    private final AuditService auditService;

    public CheckoutService(
            OrderRepository orderRepository,
            InventoryService inventoryService,
            AuditService auditService) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
        this.auditService = auditService;
    }

    @Transactional
    public void checkout(Long orderId, Long productId, int quantity) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        try {
            inventoryService.reserve(productId, quantity);
            order.confirm();
        } catch (InsufficientInventoryException ex) {
            auditService.recordFailure(orderId, ex.getMessage());
            throw ex;
        }
    }
}
~~~

In this example:
- `checkout()` opens T1 through its proxy.
- `inventoryService.reserve()` (with `REQUIRED`) joins T1.
- On insufficient inventory, the exception enters `catch`.
- `auditService.recordFailure()` passes through its bean proxy, suspends T1, and runs T2.
- T2 commits the audit record.
- The exception is rethrown, rolling back T1.
- T2's audit record remains persisted.

This is one specific semantic choice. If audits should appear only when orders commit or if durable event delivery is required, use an appropriate audit/outbox pattern instead of defaulting to `REQUIRES_NEW`.

## 22. Common Design Mistakes

### 22.1. Placing @Transactional on Private Methods

Proxies cannot intercept private methods under standard proxy mechanisms. Annotating a private method does not establish an independent boundary as expected.

### 22.2. Self-Invocation with REQUIRES_NEW

Methods in the same class calling each other via `this` bypass the proxy, so the inner annotation is ignored. Split into another bean or use `TransactionTemplate`.

### 22.3. Catching Exceptions and Assuming Rollback Occurred

If an exception is caught and the method returns normally, the transaction may commit. Explicitly decide between rethrowing, `setRollbackOnly`, or converting to an intentional business outcome.

### 22.4. Checked Exceptions Failing to Roll Back

`IOException` or checked business exceptions do not trigger rollback by default. Configure `rollbackFor` appropriately.

### 22.5. Overusing REQUIRES_NEW

It can consume a second connection per outer transaction, increase database load, and cause lock conflicts. Use only when independent commits are genuinely needed.

### 22.6. Using NESTED with JPA Expecting Objects to Revert

Rolling back a JDBC savepoint does not automatically undo mutations on managed Java entities. Understand `EntityManager`/persistence context limits.

### 22.7. Holding Transactions Open Too Long

Holds connections, row locks, and undo longer. Keep HTTP calls, sleeps, large file processing, and user waits outside transactions whenever separable.

### 22.8. Calling Another Database Assuming One Transaction

A separate DataSource/transaction manager does not automatically join the current transaction. Use JTA/XA or an appropriate distributed pattern.

### 22.9. Calling Methods on Objects Created with new

Objects not managed by Spring have no transactional proxy. Annotations have no effect.

### 22.10. Assuming repository.save() Returning Means Committed

JPA can defer SQL until flush/commit. Constraint or I/O errors can still surface at the end of the transaction.

## 23. Testing Transactions Properly

Tests can mask transaction bugs if the test method itself is annotated `@Transactional`.

### 23.1. Test Slices Often Roll Back Test Transactions

`@DataJpaTest` normally runs tests inside a transaction that rolls back after the test. If a service method uses `REQUIRED`, it joins the test's transaction. Since the test rolls back at the end, it does not prove the service commits independently.

### 23.2. Flush and Clear When Testing JPA

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void persistsOrder() {
        Order order = new Order();
        entityManager.persist(order);
        entityManager.flush();
        entityManager.clear();

        Order reloaded = orderRepository.findById(order.getId())
            .orElseThrow();

        assertThat(reloaded.getId()).isEqualTo(order.getId());
    }
}
~~~

`flush` sends SQL to the database; `clear` detaches entities from the persistence context so the subsequent read hits the database. Even then, the test transaction may still roll back when the test finishes.

### 23.3. Verifying Real Commits

When testing that data truly committed and is visible from another transaction:
- Run the test without an enclosing test transaction so the service opens/commits its own.
- Use `TransactionTemplate` and finish the transaction before reading from another connection.
- Use `TestTransaction` to end the test transaction in a controlled way.
- Open a new transaction/connection to verify visibility.

Do not just call `find()` again on the same persistence context, which can return cached entities from the first-level cache.

### 23.4. Testing Self-Invocation

Write tests calling the outer bean method through its proxy and verify whether an inner `REQUIRES_NEW` commits or rolls back as designed. Ensure beans are injected from the Spring context rather than instantiated with `new`.

### 23.5. Testing Rollback Rules

Write dedicated tests for:
- `RuntimeException`.
- Checked exceptions without `rollbackFor`.
- Checked exceptions with `rollbackFor`.
- Caught exceptions.
- Inner `REQUIRED` marking rollback-only.
- `REQUIRES_NEW` committing while outer rolls back.
- `NESTED` savepoints if supported by the transaction manager.

## 24. Using TransactionTemplate for Explicit Boundaries

`TransactionTemplate` fits when:
- Multiple independent transactions are needed within one method.
- Explicit boundaries are needed inside a loop.
- Self-invocation makes proxies awkward.
- Precise control over which code block sits inside a transaction is desired.

Example:

~~~java
@Service
public class BatchService {

    private final TransactionTemplate transactionTemplate;
    private final OrderRepository orderRepository;

    public BatchService(
            PlatformTransactionManager transactionManager,
            OrderRepository orderRepository) {
        this.transactionTemplate =
            new TransactionTemplate(transactionManager);
        this.orderRepository = orderRepository;
    }

    public void processBatch(List<Long> ids) {
        for (Long id : ids) {
            transactionTemplate.execute(status -> {
                Order order = orderRepository.findById(id)
                    .orElseThrow();
                order.process();
                return null;
            });
        }
    }
}
~~~

Each `execute` call runs a transaction using the propagation/isolation/timeout configured on the template. Create a separate template with `REQUIRES_NEW` if a batch needs per-item independent transactions.

Do not switch to programmatic transactions solely because annotations feel confusing. Pick whichever form expresses boundaries clearest for the use case.

## 25. Transactions in Batches and Loops

Wrapping a large batch in one transaction can:
- Hold connections long-term.
- Hold locks and undo segments long-term.
- Bloat the persistence context.
- Make rollbacks expensive.
- Force restarting the entire batch if the final item fails.

Split batches into chunks or per-item transactions when business rules allow. However, splitting transactions alters atomicity: earlier items can commit while later items fail. Design checkpoints, retries, idempotency, and batch status tracking accordingly.

Chunk transaction example:
- Fetch IDs page by page.
- Pass each chunk to a `REQUIRED` method on an external proxied bean.
- Commit each chunk upon completion.
- Persist progress/checkpoints in an appropriate transaction.

Never call an internal `REQUIRES_NEW` method on the same class to simulate chunk transactions; the proxy will be bypassed.

## 26. Observing Transactions at Runtime

To diagnose issues, see which methods open transactions, which transaction manager is selected, and which SQL runs inside boundaries.

Selectively enable logging for:
- `org.springframework.transaction.interceptor`
- `org.springframework.orm.jpa`
- `org.springframework.jdbc.datasource`
- `org.hibernate.SQL`
- `org.hibernate.resource.transaction`

Never enable SQL bind-parameter logging containing sensitive data in production without log-protection policies.

### 26.1. Checking Transaction Synchronization

Spring exposes `TransactionSynchronizationManager` for imperative diagnostics:

~~~java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean synchronizationActive =
    TransactionSynchronizationManager.isSynchronizationActive();
~~~

This is useful runtime diagnostic metadata, not something business logic should couple to. Reactive transactions use a different context mechanism.

### 26.2. Inspecting State in Oracle

DBAs can inspect sessions, SQL, locks, and transactions using dynamic performance views such as `V$SESSION`, `V$TRANSACTION`, `V$LOCK`, and `GV$SESSION` in RAC. Querying requires appropriate privileges.

When investigating blocking:
- Identify blocker and waiter sessions.
- Inspect `SQL_ID`, module, action, and transaction duration.
- Check whether the application holds transactions across external calls.
- Determine which transaction should commit or roll back per business rules.

## 27. @Transactional Design Checklist

Before adding the annotation, answer:

1. Which use case requires atomicity?
2. Which service method should define the boundary?
3. Does the call pass through a Spring proxy?
4. Is the method called from another bean or via self-invocation?
5. Which transaction manager manages the resource?
6. Are multiple DataSources involved?
7. Does propagation need to differ from `REQUIRED`?
8. If an inner method fails, should the outer transaction roll back or continue?
9. Do checked exceptions require `rollbackFor`?
10. Are exceptions caught and swallowed?
11. Is a savepoint or an independent transaction needed?
12. Will `REQUIRES_NEW` require a second connection?
13. Could lock conflicts arise with the outer transaction?
14. Are HTTP, message broker, or filesystem calls made inside the transaction?
15. Is async execution or thread switching involved?
16. Could the persistence context hold stale entities?
17. Do timeout/isolation/readOnly fit the use case?
18. Is the transaction short enough?
19. Do tests truly verify commit/rollback behavior?
20. Can transaction state be inspected in the database when needed?

## 28. Practice Questions

1. Explain what a transaction boundary is in Spring.
2. What does the proxy do before and after invoking the target method?
3. Why does self-invocation bypass the transactional proxy?
4. Distinguish JDK dynamic proxies from CGLIB proxies.
5. Why are `private`/`final` methods unsuitable as transactional boundaries under class proxies?
6. Describe the roles of `PlatformTransactionManager` and `JpaTransactionManager`.
7. Why is the service layer usually the right place for transaction boundaries?
8. Explain `REQUIRED` when the caller has no active transaction.
9. Explain `REQUIRED` when the caller already has an active transaction.
10. Why can an inner `REQUIRED` method mark an outer transaction rollback-only?
11. Distinguish `REQUIRES_NEW` from `NESTED`.
12. Why can `REQUIRES_NEW` require a second connection?
13. Describe the lock conflict when an inner `REQUIRES_NEW` updates a row locked by the outer transaction.
14. Why can entities in the outer persistence context become stale after an inner commit?
15. State the conditions needed for `NESTED` to work via savepoints.
16. Why is `NESTED` not equivalent to a nested JPA persistence context?
17. Distinguish `SUPPORTS` from `REQUIRED`.
18. Distinguish `NOT_SUPPORTED` from `NEVER`.
19. When is `MANDATORY` useful?
20. Which exception types does Spring roll back by default?
21. Why don't checked exceptions roll back automatically?
22. Write a `rollbackFor` example for a checked business exception.
23. What happens if an exception is caught and not rethrown?
24. Explain `UnexpectedRollbackException`.
25. Does the `isolation` attribute always apply when joining an existing transaction?
26. Is `readOnly=true` a security mechanism preventing writes?
27. Distinguish JPA flush from database commit.
28. Why doesn't Oracle DDL roll back like DML?
29. Why doesn't `@Async` inherit the caller's imperative transaction?
30. Design a test proving `REQUIRES_NEW` commits even when the outer transaction rolls back.

**`@Transactional` only takes effect when calls pass through the transaction interceptor; propagation then decides whether the method joins, creates, suspends, or rejects an existing transaction.** Place boundaries at service methods representing business use cases, distinguish `REQUIRED` from `REQUIRES_NEW` and `NESTED`, declare rollback rules for business exceptions, and watch out for self-invocation, connection pools, persistence context state, and external side effects. With JPA on Oracle, remember that flush is not commit, locks are held until transaction end, and DDL triggers implicit commits.

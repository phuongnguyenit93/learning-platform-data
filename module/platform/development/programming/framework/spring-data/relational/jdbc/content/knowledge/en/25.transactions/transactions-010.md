# Programmatic Transaction Management with TransactionTemplate

Spring Data JDBC commonly pairs with declarative transactions using `@Transactional` on services or repositories. However, some use cases require explicit control over where a transaction begins, ends, commits, and rolls back directly inside code. Spring provides **`TransactionTemplate`** for that purpose.

`TransactionTemplate` is an imperative transaction management API. It accepts a `PlatformTransactionManager`, starts or joins a transaction according to its configuration, runs a callback, and completes the transaction when the callback finishes. If the callback throws an exception eligible for rollback, the template instructs the transaction manager to roll back and propagates the error to the caller.

In Spring Data JDBC, repository calls executed inside the callback can participate in the same transaction if they share the same transaction manager and DataSource. As a result, multiple write operations can commit or roll back as a single use case.

This lesson covers configuration, calling `execute`/`executeWithoutResult`, controlling rollback, propagation, isolation, and timeout, as well as considerations around connections, exceptions, and testing.

## 1. When Do You Need TransactionTemplate?

For a typical service, `@Transactional` is usually the simpler and more readable option:

```java
@Transactional
public Long createOrder(CreateOrderCommand command) {
    PurchaseOrder order = new PurchaseOrder(command.orderNumber());
    return orders.save(order).getId();
}
```

Annotations fit well when a transaction spans an entire method with a clear boundary. However, there are cases where code needs to choose a transaction boundary inside a larger method, or execute a callback inside a transaction and then continue with non-transactional work.

For example, checkout needs to:

1. Reserve inventory quantity.
2. Create the order.
3. Write change history.
4. If any step fails, roll back database changes made during the use case.

`TransactionTemplate` lets you pinpoint the exact block of code inside the transaction:

```java
transactionTemplate.execute(status -> {
    inventory.reserve(command.sku(), command.quantity());
    PurchaseOrder saved = orders.save(createOrder(command));
    history.save(OrderHistory.created(saved.getId()));
    return saved.getId();
});
```

If all three repositories share that transaction manager/DataSource, their operations participate in the same transaction. When the callback completes normally, the template commits; when an error requiring rollback occurs, changes in the transaction are rolled back.

### 1.1. Comparing @Transactional and TransactionTemplate

| Criterion | `@Transactional` | `TransactionTemplate` |
| --- | --- | --- |
| Declaration style | Annotation on class/method | Callback in code |
| Transaction boundary | Per method invocation via Spring proxy or equivalent mechanism | Per `execute` call |
| Commit/rollback | Managed by Spring AOP/transaction interceptor | Managed by template around callback |
| Propagation/isolation config | Annotation or transaction manager | Properties on template |
| Conditional transaction per code branch | Possible, though usually requires extracting methods | Can invoke template on the specific branch |
| Reading control flow | Boundary usually visible on annotations | Boundary visible inline in code |

You do not need to replace all `@Transactional` usage with `TransactionTemplate`. Use annotations for service methods with stable transaction boundaries; use templates when explicit programmatic control offers practical benefits.

## 2. Core Components

`TransactionTemplate` belongs to Spring Framework:

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;
```

Component roles:

| Component | Role |
| --- | --- |
| `PlatformTransactionManager` | Abstraction coordinating transactions for a persistence technology. |
| `TransactionTemplate` | Executes callbacks inside a transaction and manages commit/rollback. |
| `TransactionCallback<T>` | Callback returning a result of type `T`. |
| `TransactionStatus` | Allows inspecting status and requesting rollback. |
| `TransactionOperations` | Interface describing transaction execution operations; implemented by `TransactionTemplate`. |

In a Spring Data JDBC application, the transaction manager must manage the exact DataSource used by the repositories. Spring Boot typically auto-configures a transaction manager for the configured datasource. If the app has multiple datasources, select the right manager for each repository group.

## 3. Configuring TransactionTemplate

A common approach is defining a bean from `PlatformTransactionManager`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class TransactionConfiguration {

    @Bean
    TransactionTemplate transactionTemplate(
            PlatformTransactionManager transactionManager) {
        return new TransactionTemplate(transactionManager);
    }
}
```

Spring Boot can auto-provide a transaction manager when a datasource and transaction support are configured. Declaring a `TransactionTemplate` bean explicitly lets application services inject and use it directly.

Service:

```java
@Service
public class CheckoutService {

    private final TransactionTemplate transactionTemplate;
    private final InventoryRepository inventory;
    private final PurchaseOrderRepository orders;

    public CheckoutService(
        TransactionTemplate transactionTemplate,
        InventoryRepository inventory,
        PurchaseOrderRepository orders
    ) {
        this.transactionTemplate = transactionTemplate;
        this.inventory = inventory;
        this.orders = orders;
    }
}
```

If the Spring context has multiple `PlatformTransactionManager` beans, use `@Qualifier` or explicit bean wiring to ensure the template binds to the right manager.

### 3.1. Configure Once Before Use

`TransactionTemplate` holds transaction properties such as propagation, isolation, timeout, and read-only. You can configure them before sharing the bean with services.

Once configured, the template can be reused. Do not mutate properties on a singleton template per request, because multiple threads may use it concurrently.

If two use cases need different settings, define two separate beans/templates or create separate templates with stable configurations per purpose.

## 4. execute(): Executing a Callback and Returning a Result

The `execute` method takes a callback and returns the value produced by that callback:

```java
Long orderId = transactionTemplate.execute(status -> {
    PurchaseOrder order = orders.save(
        new PurchaseOrder("PO-2026-001")
    );

    return order.getId();
});
```

Execution flow:

1. The template asks the transaction manager to start a new transaction or join an existing one according to propagation.
2. The callback executes.
3. Repository calls inside the callback use the active transaction if they share the transaction context.
4. The callback returns a result.
5. The template completes the transaction according to commit/rollback status.
6. The callback's return value is returned to the caller after the transaction completes successfully.

The generic parameter `T` on `TransactionCallback<T>` determines the return type. If the callback returns `Long`, `execute` returns `Long`.

### 4.1. Complete Example with Multiple Repositories

Suppose a use case needs to reserve inventory and then create an order:

```java
@Service
public class CheckoutService {

    private final TransactionTemplate tx;
    private final InventoryRepository inventory;
    private final PurchaseOrderRepository orders;
    private final OrderHistoryRepository history;

    public CheckoutService(
        TransactionTemplate tx,
        InventoryRepository inventory,
        PurchaseOrderRepository orders,
        OrderHistoryRepository history
    ) {
        this.tx = tx;
        this.inventory = inventory;
        this.orders = orders;
        this.history = history;
    }

    public Long checkout(CheckoutCommand command) {
        return tx.execute(status -> {
            int reserved = inventory.reserve(
                command.sku(),
                command.quantity()
            );

            if (reserved != 1) {
                throw new InsufficientStockException(
                    command.sku()
                );
            }

            PurchaseOrder saved = orders.save(
                PurchaseOrder.create(
                    command.orderNumber(),
                    command.sku(),
                    command.quantity()
                )
            );

            history.save(
                OrderHistory.created(saved.getId())
            );

            return saved.getId();
        });
    }
}
```

This code expresses a single transaction boundary. If reserving stock succeeds but saving the order or history raises a runtime exception, the template rolls back changes made within that transaction.

The example assumes all three repositories share the same DataSource and transaction manager. If they point to different datasources/transaction managers, a single `TransactionTemplate` will not automatically create a distributed transaction across all of them.

## 5. executeWithoutResult(): Callback Without a Return Value

If the use case only performs operations and returns no value, use `executeWithoutResult`:

```java
transactionTemplate.executeWithoutResult(status -> {
    inventory.reserve("BOOK-01", 2);
    orders.save(PurchaseOrder.create("PO-2026-002"));
});
```

The callback receives `TransactionStatus` so it can request rollback if needed. This API avoids returning a dummy value solely to satisfy `execute`.

You can use `executeWithoutResult` for:

- Multi-table updates.
- Synchronizing a group of aggregates in the same database.
- Recording history/audit alongside a business operation.
- Multi-step deletions requiring atomicity.

If you need to return an ID, an affected row count, or a business result, use `execute`.

## 6. Default Commit and Rollback

By default, the transaction commits when the callback finishes normally. If the callback throws a `RuntimeException` or `Error`, the template requests rollback and rethrows the exception to the caller.

Example:

```java
Long id = transactionTemplate.execute(status -> {
    PurchaseOrder saved = orders.save(
        PurchaseOrder.create("PO-2026-003")
    );

    if (!isAllowed(saved)) {
        throw new IllegalStateException(
            "Order is invalid"
        );
    }

    return saved.getId();
});
```

If `isAllowed` returns false and the exception is thrown, saving the order in the same transaction is rolled back.

### 6.1. Do Not Swallow Exceptions If You Want Automatic Rollback

The following snippet has a bug:

```java
transactionTemplate.executeWithoutResult(status -> {
    try {
        inventory.reserve("BOOK-01", 2);
        orders.save(PurchaseOrder.create("PO-2026-004"));
    } catch (RuntimeException ex) {
        log.error("Checkout failed", ex);
        // Callback finishes normally so transaction may commit.
    }
});
```

When the exception is caught and not rethrown, the template sees the callback finish normally. The transaction may commit changes performed before the error.

If rollback is required, rethrow the exception:

```java
transactionTemplate.executeWithoutResult(status -> {
    try {
        inventory.reserve("BOOK-01", 2);
        orders.save(PurchaseOrder.create("PO-2026-004"));
    } catch (RuntimeException ex) {
        log.error("Checkout failed", ex);
        throw ex;
    }
});
```

Or mark rollback-only before returning if the use case intentionally handles the error without throwing an exception out.

### 6.2. Checked Exceptions

The `TransactionCallback` callback does not declare checked exceptions. If an operation inside the callback throws a checked exception, code must handle it inside the callback.

One option is wrapping it in an unchecked exception:

```java
transactionTemplate.executeWithoutResult(status -> {
    try {
        importService.importData();
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
});
```

The unchecked exception escapes the callback and triggers rollback by default.

If the application needs to return a business result instead of throwing an exception, call `status.setRollbackOnly()` and return the failure result. Make sure not to continue write operations after deciding to roll back.

## 7. Marking Rollback-Only with TransactionStatus

There are situations where the callback must complete processing to return a structured result, while the transaction still must roll back.

Use:

```java
transactionTemplate.execute(status -> {
    int reserved = inventory.reserve("BOOK-01", 2);

    if (reserved == 0) {
        status.setRollbackOnly();
        return CheckoutResult.rejected("Insufficient stock");
    }

    PurchaseOrder order = orders.save(
        PurchaseOrder.create("PO-2026-005")
    );

    return CheckoutResult.accepted(order.getId());
});
```

`setRollbackOnly` marks the current transaction to roll back when the template finishes. The callback can still return `CheckoutResult`.

The rejected business result is returned to the caller, while database changes inside the transaction are never committed.

### 7.1. isRollbackOnly()

`TransactionStatus` can be inspected:

```java
if (status.isRollbackOnly()) {
    // Transaction has already been marked rollback-only.
}
```

Usually you do not need to check this repeatedly. Use it when callback logic has multiple branches and needs to know whether the transaction has already been marked for rollback.

### 7.2. Rollback-Only Does Not Mean Immediate Rollback at That Line of Code

`setRollbackOnly` records the decision to roll back. Actual rollback happens when the template finishes the callback and finalizes the transaction. Do not proceed to trigger non-database side effects assuming they will also roll back.

For example, sending an email or calling an external API is not undone by a database transaction. Execute side effects after commit or use an appropriate outbox/event pattern.

## 8. Configuring Propagation

Propagation determines how a transaction invocation interacts with an existing transaction.

`TransactionTemplate` defaults to `PROPAGATION_REQUIRED`.

| Propagation | Behavior |
| --- | --- |
| `REQUIRED` | Joins existing transaction; creates a new one if none exists. |
| `REQUIRES_NEW` | Suspends existing transaction and creates a new independent transaction. |
| `SUPPORTS` | Joins if a transaction exists; otherwise runs without a transaction. |
| `MANDATORY` | Requires an existing transaction; fails if none exists. |
| `NOT_SUPPORTED` | Suspends existing transaction and runs without a transaction. |
| `NEVER` | Requires no active transaction; fails if one exists. |
| `NESTED` | Runs a nested transaction if supported by the transaction manager, typically using savepoints. |

### 8.1. REQUIRED: The Default Choice

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);
// Default propagation: PROPAGATION_REQUIRED
```

If a service is already running inside a `@Transactional`-created transaction, the callback typically joins that transaction. If none exists, the template creates a new transaction.

This lets repository calls inside the callback coordinate with an outer transaction.

### 8.2. REQUIRES_NEW: Independent Transaction

You can configure a dedicated template:

```java
@Bean
TransactionTemplate independentTransactionTemplate(
        PlatformTransactionManager transactionManager) {
    TransactionTemplate template =
        new TransactionTemplate(transactionManager);

    template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW
    );

    return template;
}
```

When invoked within an active transaction, the outer transaction is suspended, the template opens a new transaction, finishes it, and then resumes the outer transaction.

For example, this can be used for an independent record that business rules require keeping even if the outer transaction rolls back. Weigh carefully whether data written in a REQUIRES_NEW transaction makes sense if the primary business operation fails.

Furthermore, the outer transaction may hold a connection while the new transaction needs another connection. With a small connection pool and concurrent nested requests, this can cause pool exhaustion or waiting.

### 8.3. NESTED and Savepoints

`PROPAGATION_NESTED` can use a savepoint within a single physical transaction if supported by the transaction manager. It is not equivalent to an independent transaction like `REQUIRES_NEW`.

Nested transaction capability depends on the transaction manager and database configuration. Do not assume every DataSource transaction manager supports nested behavior identically.

## 9. Isolation Level, Timeout, and Read-Only

Besides propagation, a template can configure isolation, timeout, and read-only.

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);

tx.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
tx.setTimeout(30);
tx.setReadOnly(false);
```

### 9.1. Isolation Levels

Common JDBC/Spring isolation levels:

| Isolation | General meaning |
| --- | --- |
| `ISOLATION_DEFAULT` | Uses the database/transaction manager default. |
| `ISOLATION_READ_UNCOMMITTED` | May allow dirty reads if supported by the database. |
| `ISOLATION_READ_COMMITTED` | Reads only committed data per database semantics. |
| `ISOLATION_REPEATABLE_READ` | Protects consistency of repeated reads of the same row per database semantics. |
| `ISOLATION_SERIALIZABLE` | Strictest level; database may lock or abort transactions to preserve serializability. |

Do not choose the highest isolation out of habit. It can increase lock contention, reduce throughput, or cause transactions to abort on conflicts. Start with the database default, then pick an isolation level based on actual invariants and workload.

### 9.2. Isolation Applies Only When a New Transaction Is Created

If the template joins an existing transaction under `REQUIRED`, the outer transaction's isolation is normally preserved. Setting isolation on the template does not automatically upgrade an already-open transaction.

To control behavior when joining a transaction with a different isolation level, the transaction manager can be configured to validate existing transactions. Avoid expecting a template to change isolation mid-flight on a running transaction.

### 9.3. Timeout

`setTimeout(30)` sets a timeout in seconds for a new transaction if supported by the transaction manager/database. A timeout does not always immediately interrupt a running SQL statement; query timeout and transaction timeout are related but distinct mechanisms.

For long queries, you may need separate query timeouts on JDBC/template/repository or database statements.

### 9.4. Read-Only

`setReadOnly(true)` marks the transaction as read-only:

```java
TransactionTemplate readOnlyTx =
    new TransactionTemplate(transactionManager);

readOnlyTx.setReadOnly(true);
```

It can allow the transaction manager/driver/database to apply appropriate optimizations. It is not an absolute authorization mechanism; whether writes are rejected depends on the database and transaction manager.

Use a dedicated read-only template for long read use cases or multi-repository reads that need a shared transaction. Do not mutate `readOnly` on a shared singleton template per request.

## 10. TransactionTemplate with Spring Data JDBC Repositories

Spring Data JDBC repositories use Spring's transaction abstraction. When repositories are called inside `TransactionTemplate.execute` and share a transaction manager/DataSource, their SQL statements share that transaction.

Example:

```java
transactionTemplate.executeWithoutResult(status -> {
    Customer customer = customers.save(
        new Customer(null, "Mai", "mai@example.test")
    );

    orders.save(
        PurchaseOrder.forCustomer(customer.id())
    );

    audit.save(
        AuditEntry.customerCreated(customer.id())
    );
});
```

If any operation throws an unchecked exception and the exception escapes the callback, the transaction rolls back all three changes.

Important conditions:

- Repositories must use the same DataSource or a compatible coordinated transaction setup.
- The template must bind to the transaction manager governing the right datasource.
- Repository calls must run on the same synchronous execution flow within the transaction context.
- Do not offload database work to another thread and assume the transaction propagates automatically.

### 10.1. Query Methods and @Modifying

Custom SQL write methods such as `@Modifying` can also join a template-opened transaction:

```java
transactionTemplate.executeWithoutResult(status -> {
    int updated = inventory.reserve("BOOK-01", 2);

    if (updated != 1) {
        throw new InsufficientStockException("BOOK-01");
    }

    orders.save(PurchaseOrder.create("PO-2026-006"));
});
```

Direct modifying queries do not automatically trigger entity callbacks or auditing like the aggregate save path. TransactionTemplate manages only the transaction; it does not turn direct SQL statements into aggregate persistence.

### 10.2. Repository CRUD Has Default Transactions

Inherited CRUD methods on Spring Data repositories have a default transaction configuration. Separately declared query methods may need an explicit transaction boundary at the service or template level.

When an outer transaction from the template is already active, repository calls join that transaction according to propagation and matching configuration.

## 11. Combining TransactionTemplate and @Transactional

Both mechanisms can be used together. For instance, a service method has a declarative transaction and the callback uses a default REQUIRED template:

```java
@Transactional
public void updateOrder(Long orderId) {
    transactionTemplate.executeWithoutResult(status -> {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow();

        order.markConfirmed();
        orders.save(order);
    });

    notifications.recordConfirmation(orderId);
}
```

Because `REQUIRED` joins the existing transaction, the callback runs inside the outer transaction. Only when the service method finishes does the outer transaction commit.

However, using both for the exact same boundary can make code harder to follow without a clear reason. Pick one owner for the primary transaction boundary so readers know which operations commit or roll back together.

If the template uses `REQUIRES_NEW`, it creates an independent transaction while the outer transaction is suspended. That can be intentional, though it should be justified by business semantics.

## 12. Do Not Let Transactions Cross Thread Boundaries

Spring's imperative JDBC transactions are normally bound to the current thread through transaction synchronization and connection binding.

Therefore, this code:

```java
transactionTemplate.executeWithoutResult(status -> {
    executor.submit(() -> orders.save(order));
});
```

does not make the operation on the executor thread automatically join the callback's transaction. The new thread has its own transaction context or none at all, depending on how it is invoked.

If asynchronous processing is needed:

1. Commit the current transaction.
2. Dispatch work via an appropriate queue/event/outbox mechanism.
3. Have the worker open its own transaction for its work.

Do not hold a connection/transaction open while waiting on a future or async task if that task needs a connection from the same pool currently held.

In reactive stacks like R2DBC, transaction context is managed via the reactive context and requires appropriate APIs such as `TransactionalOperator`; `TransactionTemplate` is an imperative API and is not a substitute for reactive transaction management.

## 13. Handling Errors and Post-Transaction Results

`execute` returns the callback's result only after the transaction completes successfully. If commit/rollback fails, the corresponding exception propagates to the caller.

Example:

```java
CheckoutResult result;

try {
    result = transactionTemplate.execute(status -> {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("PO-2026-007")
        );
        return CheckoutResult.accepted(saved.getId());
    });
} catch (DataAccessException ex) {
    // Handle persistence error after template rolls back per rules.
    throw new CheckoutFailedException(ex);
}
```

Catch errors where there is sufficient context to convert them into business errors or API responses. Do not catch and ignore errors inside the callback if rollback is required.

### 13.1. Side Effects Outside the Database

Emails, HTTP calls, direct message publishing, or file writes are not part of a JDBC transaction. Database rollback cannot undo those side effects.

If events must be emitted only when the transaction commits, consider:

- Transactional event listeners with an appropriate phase.
- The outbox pattern writing the event in the same database transaction, with a worker publishing afterwards.
- Retry/idempotency mechanisms for external systems.

Do not send an email successfully before database commit and expect rollback to unsend the email.

## 14. Testing Commit and Rollback

An integration test must verify that changes are actually rolled back after the callback fails.

Service example:

```java
public void createThenFail() {
    transactionTemplate.executeWithoutResult(status -> {
        orders.save(PurchaseOrder.create("PO-ROLLBACK"));
        throw new IllegalStateException("Simulated failure");
    });
}
```

Test:

```java
@SpringBootTest
class TransactionTemplateIntegrationTest {

    @Autowired
    CheckoutService checkout;

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void rollsBackRepositoryChangesWhenCallbackFails() {
        assertThatThrownBy(() -> checkout.createThenFail())
            .isInstanceOf(IllegalStateException.class);

        assertThat(orders.findByOrderNumber("PO-ROLLBACK"))
            .isEmpty();
    }
}
```

This test must run against the application's real database and transaction manager. Do not annotate the test method with `@Transactional` if you want to observe results after the service transaction finishes; an outer test transaction can alter how reads, commits, and rollbacks are observed.

### 14.1. Testing Rollback-Only

If the callback marks rollback-only yet returns a normal result:

```java
CheckoutResult result = transactionTemplate.execute(status -> {
    orders.save(PurchaseOrder.create("PO-ROLLBACK-ONLY"));
    status.setRollbackOnly();
    return CheckoutResult.rejected("Cancelled");
});
```

Tests should verify:

- The caller receives `CheckoutResult.rejected`.
- The `PO-ROLLBACK-ONLY` row does not exist after the transaction.
- No external side effects are assumed to have rolled back.

### 14.2. Testing Multiple Repositories in the Same Transaction

Write data via two repositories and throw an exception after the second operation. After the transaction finishes, verify neither change exists.

This proves both repositories actually share the same transaction manager/DataSource. If only part of the data rolls back, inspect the datasource, transaction manager, and propagation of each component.

## 15. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Data still commits after catching an exception | Exception swallowed inside callback and callback completes normally. | Rethrow the exception or call `setRollbackOnly`. |
| One repository rolls back while another does not | The two repositories use different datasources/transaction managers. | Use the right transaction manager or design explicit coordination. |
| Template does not join outer transaction | Unexpected propagation setting or different manager used. | Check `REQUIRED`, manager, and transaction boundary. |
| Outer transaction rolls back yet REQUIRES_NEW data remains | The new transaction committed independently. | Confirm this matches the desired business semantics. |
| Connection pool exhausted | Transaction/Stream holds connection too long or REQUIRES_NEW requires a second connection. | Shorten transactions and review pool/concurrency sizing. |
| Update runs inside a read-only transaction | Template or outer transaction configured as read-only. | Use a proper write transaction. |
| Checked exception fails to trigger rollback | Callback cannot throw checked exceptions directly or error is handled as normal. | Wrap in an unchecked exception or mark rollback-only. |
| Async code does not roll back with callback | Transaction context does not automatically propagate to another thread. | Open a separate transaction in the worker or use an outbox. |
| Email sent despite database rollback | Non-database side effects are outside the JDBC transaction. | Emit events after commit or use an outbox. |
| Changing isolation has no effect | Callback joined an already-existing transaction. | Configure isolation on a new transaction and understand propagation. |

## 16. Workflow for Using TransactionTemplate

When programmatic transactions are needed in Spring Data JDBC:

1. Identify which database operations in the use case must commit or roll back together.
2. Select the right `PlatformTransactionManager` managing the repositories' datasource.
3. Create and configure `TransactionTemplate` once.
4. Use `execute` when returning a result or `executeWithoutResult` when no return value is needed.
5. Place all repository calls belonging to the same atomic unit inside the callback.
6. Let exceptions requiring rollback escape the callback or call `setRollbackOnly`.
7. Choose propagation, isolation, timeout, and read-only based on actual requirements.
8. Do not mutate shared template settings per request.
9. Do not move database work to another thread assuming the transaction is inherited.
10. Move non-database side effects after commit or use an outbox/event pattern.
11. Test commit, rollback, and multiple repositories sharing a transaction.
12. Keep transactions short to minimize connection and lock retention.

> **TransactionTemplate opens or joins a transaction, runs a callback, and commits or rolls back based on the outcome.** In Spring Data JDBC, it offers an explicit way to group multiple repository operations into a single transaction when they share a transaction manager and DataSource. Let errors requiring rollback escape the callback or mark rollback-only, configure propagation deliberately, and keep database work inside the same thread-bound transaction.

### References

- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): using `TransactionTemplate` and transaction callbacks.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction abstractions, PlatformTransactionManager, and declarative transactions.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): propagation behaviors and transaction boundaries.
- [Spring Framework — Transaction Isolation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-isolation.html): isolation levels and transaction behavior.
- [Spring Data JDBC — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction support in Spring Data JDBC.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): configuring datasources and transaction managers in Spring Boot.

# Transaction Boundaries per Business Operation

In Spring Data JPA, a transaction boundary should enclose a single business operation that needs to be executed consistently. An operation such as placing an order may read the customer, check inventory, update the product, save the order, record an inventory movement, and create an outbox event. If these changes belong to the same database transaction, they commit together on success or roll back together on an appropriate error.

Therefore, transaction boundaries are typically placed at the Service/Application Service layer, which coordinates the entire use case. Repositories are responsible for data access; the service decides which operations must succeed or fail together.

## 1. What is a transaction boundary?

A transaction is a unit of work that the database processes according to ACID properties:

- **Atomicity:** changes within a transaction are committed together or rolled back together.
- **Consistency:** the transaction must preserve data constraints and consistency rules.
- **Isolation:** concurrent transactions are isolated according to the database's isolation level.
- **Durability:** once committed successfully, data is stored durably according to the database's guarantees.

The transaction boundary defines when a transaction begins and ends. In Spring, **@Transactional** is typically used to declare that boundary.

A business transaction does not necessarily correspond to a single SQL statement or a single Repository call. One use case may call multiple Repositories and issue multiple SQL statements while still belonging to the same transaction.

Order placement example:

~~~text
Place order (one business operation)
        |
        v
BEGIN TRANSACTION
        |
        +--> Read customer
        |
        +--> Read and update inventory
        |
        +--> Save order
        |
        +--> Record inventory movement
        |
        +--> Write outbox event
        |
        v
COMMIT
~~~

If an important step fails and the error causes the transaction to roll back, the database changes in that transaction will not be committed individually.

## 2. Why should transactions be placed at the Service layer?

The service knows what a business operation needs to do. A repository only knows how to read or write one type of data.

Suppose placing an order requires three operations:

~~~java
productRepository.updateStock(productId, quantity);
orderRepository.save(order);
inventoryMovementRepository.save(movement);
~~~

If each operation runs in its own independent transaction, the following scenario can occur:
1. Stock is decreased and the first transaction commits.
2. Saving the order fails.
3. The system is left with reduced stock data but no corresponding order.

Placing **@Transactional** on the service allows all three operations to participate in the same transaction:

~~~java
@Service
public class OrderApplicationService {

    private final ProductRepository productRepository;
    private final OrderRepository orderRepository;
    private final InventoryMovementRepository movementRepository;

    public OrderApplicationService(
            ProductRepository productRepository,
            OrderRepository orderRepository,
            InventoryMovementRepository movementRepository) {
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
        this.movementRepository = movementRepository;
    }

    @Transactional
    public Long placeOrder(CreateOrderCommand command) {
        Product product = productRepository.findById(command.productId())
                .orElseThrow(() ->
                        new ProductNotFoundException(command.productId()));

        product.decreaseStock(command.quantity());

        PurchaseOrder order = PurchaseOrder.create(
                command.customerId(),
                product,
                command.quantity()
        );

        PurchaseOrder saved = orderRepository.save(order);

        movementRepository.save(
                InventoryMovement.forOrder(
                        product.getId(),
                        saved.getId(),
                        command.quantity()
                )
        );

        return saved.getId();
    }
}
~~~

This is an illustrative service snippet; the Entities, commands, Repositories, and factory methods must be defined according to the application's model. What matters is that the placeOrder() method is the coordination point and encloses all changes that need to be atomic.

When placeOrder() is called through the Spring transaction proxy, the transaction is opened before the method body runs. Repositories using the same transaction manager and persistence resource participate in the current transaction. When the method finishes normally, Spring requests a commit; when an appropriate error exits the method, Spring requests a rollback.

## 3. A transaction can span multiple Repositories

There is no need to create one transaction per Repository. Operations across multiple Repositories can participate in the same transaction if they use the same transaction manager and the same managed transactional resource.

Example:

~~~java
@Transactional
public void approveInvoice(Long invoiceId) {
    Invoice invoice = invoiceRepository.findById(invoiceId)
            .orElseThrow(() -> new InvoiceNotFoundException(invoiceId));

    invoice.approve();

    accountRepository.increaseReceivable(
            invoice.getCustomerId(),
            invoice.getTotalAmount()
    );

    auditRepository.save(
            AuditRecord.invoiceApproved(invoiceId)
    );
}
~~~

If the Repositories share the same **PlatformTransactionManager** for the same database, the updates to Invoice, Account, and AuditRecord can commit or roll back together.

This must be distinguished from cases where an application has multiple databases or multiple transaction managers. A standard **@Transactional** is bound to a specific transaction manager; it does not automatically turn multiple independent databases into a distributed transaction.

## 4. When does a transaction begin and end?

With transactions managed by a Spring proxy, the typical flow is:

1. The caller invokes the service method through the proxy.
2. The proxy reads the **@Transactional** metadata.
3. The transaction manager starts a new transaction or joins the existing transaction according to propagation.
4. The service method body executes.
5. Repository/JPA operations participate in the current transaction.
6. If the method returns normally, the proxy performs a commit.
7. If an exception escapes and matches the rollback rules, the proxy performs a rollback.
8. The result or exception is returned to the caller.

The transaction ends at the proxy boundary, not necessarily immediately when save() is called.

Example:

~~~java
@Transactional
public Long createProduct(String name) {
    Product product = productRepository.save(new Product(name));
    return product.getId();
}
~~~

save() does not mean commit. Hibernate may defer sending SQL to the database until flush or commit. When the transaction commits, pending changes are synchronized with the database.

saveAndFlush() requests flushing the persistence context immediately at the call site, but **flush is not commit**. The transaction can still roll back afterward.

## 5. Atomicity of a business operation

Identify which changes form a business invariant.

For example, when placing an order, the invariants might be:
- The order is created.
- Inventory is reduced accordingly.
- The inventory movement is recorded.
- The event to be published is saved to the outbox.

If the application saves the order without reducing inventory, the data no longer reflects the business reality. If inventory is reduced without an order, the system is also inconsistent.

Putting these database changes into the same transaction helps guarantee atomicity:

~~~java
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    Product product = productRepository.findById(command.productId())
            .orElseThrow();

    product.reserve(command.quantity());

    PurchaseOrder order = orderRepository.save(
            PurchaseOrder.create(command, product)
    );

    inventoryMovementRepository.save(
            InventoryMovement.forOrder(order, product, command.quantity())
    );

    outboxRepository.save(
            OutboxEvent.orderPlaced(order.getId())
    );

    return order.getId();
}
~~~

If saving InventoryMovement fails and the exception causes a rollback, the inventory update, Order save, and OutboxEvent save in the same transaction are also rolled back.

Do not split transactions solely by the number of Repositories. Split them according to business consistency boundaries.

## 6. Default rollback behavior with exceptions

Under Spring's standard default rules, a transaction rolls back when a **RuntimeException** or **Error** exits the managed method. Checked exceptions do not automatically trigger a rollback under the default rules.

Unchecked exception example:

~~~java
@Transactional
public void transfer(Long fromId, Long toId, BigDecimal amount) {
    accountRepository.debit(fromId, amount);
    accountRepository.credit(toId, amount);

    if (amount.signum() <= 0) {
        throw new IllegalArgumentException("Amount must be positive");
    }
}
~~~

IllegalArgumentException is a RuntimeException, so if it exits the method, the transaction is rolled back. In real code, amount should be validated before making changes to avoid unnecessary work.

With a checked exception:

~~~java
@Transactional
public void importStatement() throws IOException {
    accountRepository.updateBalance(...);
    throw new IOException("Cannot read statement");
}
~~~

Under the default rollback rules, a checked IOException does not necessarily roll back the transaction. If you want a rollback when that error occurs, declare:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importStatement() throws IOException {
    accountRepository.updateBalance(...);
    throw new IOException("Cannot read statement");
}
~~~

You can use noRollbackFor to declare an exception type that should not trigger a rollback, but use caution because that can cause part of the business operation to commit even though the caller receives an error.

Rollback rules can be configured at the application level in newer Spring versions; check your project's transaction configuration. When there is no special configuration, rely on the default RuntimeException/Error rule and declare rollbackFor for checked exceptions that require rollback.

## 7. Catching exceptions inside a transaction

If an exception is caught and not rethrown, the proxy may see the method complete normally and perform a commit.

Error-prone example:

~~~java
@Transactional
public void processOrder(Long orderId) {
    try {
        orderRepository.markProcessing(orderId);
        paymentRecordRepository.createRecord(orderId);
    } catch (DataAccessException exception) {
        log.error("Could not process order", exception);
        // Neither rethrown nor marked rollback-only.
    }
}
~~~

If the exception does not cause the transaction to be marked rollback-only by the provider or transaction manager, earlier changes may be committed. This usually contradicts the intent that "if the operation fails, nothing is saved."

If the error must fail the business operation, rethrow an appropriate exception:

~~~java
catch (DataAccessException exception) {
    throw new OrderProcessingException(
            "Could not process order",
            exception
    );
}
~~~

If you genuinely need to catch an error and return a normal result, explicitly decide whether the transaction is allowed to commit. You can mark it rollback-only via the transaction API when needed, but catching and swallowing exceptions should not be used as a default error-handling pattern.

Some database errors already cause the transaction to be marked rollback-only. When code continues and attempts to commit, Spring may throw UnexpectedRollbackException to notify that the transaction could not commit as the caller expected.

## 8. Propagation: how nested transactions participate

Propagation defines the behavior when a transactional method is called while a transaction already exists.

| Propagation | Behavior |
|---|---|
| REQUIRED | Joins the current transaction; creates a new one if none exists |
| REQUIRES_NEW | Suspends the current transaction and creates an independent transaction |
| SUPPORTS | Joins if one exists; otherwise runs without a transaction |
| MANDATORY | Requires an existing transaction; otherwise throws an error |
| NOT_SUPPORTED | Suspends the current transaction and runs without a transaction |
| NEVER | Requires no transaction; throws an error if one exists |
| NESTED | Uses a nested transaction/savepoint if supported by the transaction manager |

REQUIRED is the default propagation of **@Transactional**. It is usually the right choice for service methods working together to perform a single business operation.

Example:

~~~java
@Service
public class InventoryService {

    @Transactional
    public void reserve(Long productId, int quantity) {
        // Read and update inventory.
    }
}

@Service
public class OrderService {

    private final InventoryService inventoryService;

    @Transactional
    public void placeOrder(...) {
        inventoryService.reserve(...);
        // Save the order and related changes.
    }
}
~~~

With REQUIRED, reserve() joins the transaction opened by placeOrder(). If the subsequent order-saving step fails and rolls back, the inventory change also rolls back within the same transaction.

## 9. When does REQUIRES_NEW change business semantics?

REQUIRES_NEW creates an independent transaction. The outer transaction is suspended while the new transaction runs; the inner transaction can commit even if the outer transaction later rolls back.

Example:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(Long orderId) {
        auditRepository.save(AuditRecord.attempted(orderId));
    }
}
~~~

If OrderService calls recordAttempt() and the order placement transaction then fails, the audit record can still be committed because it belongs to an independent transaction.

This is only appropriate if the audit attempt genuinely needs to persist even when the main operation fails. If the audit record is part of the data that must be atomic with the Order, use the default REQUIRED.

REQUIRES_NEW can hold the outer transaction's connection while the inner transaction needs an additional connection. Under high load, this can increase connection pool demand and risk connection exhaustion. Do not use REQUIRES_NEW just to "make sure the save succeeds."

## 10. NESTED is not the same as REQUIRES_NEW

NESTED is typically implemented using a savepoint within the same physical transaction if the transaction manager supports it. It allows rolling back part of the work to the savepoint while the outer transaction can continue.

It differs from REQUIRES_NEW:
- NESTED uses a savepoint inside the current transaction when supported.
- REQUIRES_NEW creates an independent transaction with its own commit/rollback.

NESTED support depends on the transaction manager and resource. With JPA/Hibernate, you should not assume every nested transaction is supported like a savepoint for individual Entity operations. Use it only after verifying the actual transaction manager and provider behavior.

In most standard Spring Data JPA use cases, REQUIRED is sufficient.

## 11. Transaction boundaries should not be placed on individual Repository methods

An organization pattern that easily causes fragmentation is letting each Repository operation open its own transaction, with the service calling multiple operations sequentially without an enclosing transaction.

Example:

~~~java
public void placeOrder(...) {
    inventoryRepository.decreaseStock(...);
    orderRepository.save(...);
    movementRepository.save(...);
}
~~~

Without an enclosing transaction, repository methods may execute in separate transactions according to their default configuration. When the last step fails, the earlier steps may have already committed.

The transaction should be placed on the service:

~~~java
@Transactional
public void placeOrder(...) {
    inventoryRepository.decreaseStock(...);
    orderRepository.save(...);
    movementRepository.save(...);
}
~~~

Repositories sharing the same transaction manager will join this transaction. The enclosing transaction creates an atomic boundary that has business meaning.

This does not mean every Repository method must remove **@Transactional**. Spring Data has its own transaction configuration for inherited CRUD methods; the enclosing service transaction will coordinate those calls through appropriate propagation. The key point is not relying on per-Repository transactions to provide atomicity for an entire use case.

## 12. Read transactions and readOnly

For read-only operations, you can use:

~~~java
@Transactional(readOnly = true)
public OrderDetails getOrder(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    return OrderDetails.from(order);
}
~~~

readOnly = true is a hint to the transaction manager/provider and can help optimize certain behaviors such as flush mode. It is not a security mechanism that guarantees database writes are impossible in every configuration.

For write operations, use the default read-write transaction:

~~~java
@Transactional
public void updateOrder(...) {
    // Modify business state and data.
}
~~~

When a service class is annotated with **@Transactional(readOnly = true)**, methods that need to write can override it with **@Transactional** without setting readOnly:

~~~java
@Service
@Transactional(readOnly = true)
public class OrderQueryService {

    public OrderDetails findDetails(Long id) {
        // Read-only.
    }
}

@Service
public class OrderCommandService {

    @Transactional
    public void cancel(Long id) {
        // Modify data.
    }
}
~~~

Separating query services and command services is one way to organize code, though not mandatory. What matters is that the transaction mode reflects the work being done.

## 13. Transaction proxies and self-invocation

Spring typically applies **@Transactional** via a proxy. A call from another bean goes through the proxy, allowing the interceptor to start or join a transaction.

A common mistake is calling another transactional method via `this` within the same object:

~~~java
@Service
public class ImportService {

    public void importAll() {
        this.importOneBatch();
    }

    @Transactional
    public void importOneBatch() {
        // The author may expect this method to always open its own transaction.
    }
}
~~~

The call `this.importOneBatch()` does not go through the Spring proxy, so the annotation on the internally invoked method may not be applied as expected.

A clearer structure is to move the transaction boundary into a separate bean:

~~~java
@Service
public class BatchWorker {

    @Transactional
    public void importOneBatch(List<ImportRow> rows) {
        // Process one batch inside a transaction.
    }
}

@Service
public class ImportCoordinator {

    private final BatchWorker batchWorker;

    public ImportCoordinator(BatchWorker batchWorker) {
        this.batchWorker = batchWorker;
    }

    public void importAll(List<List<ImportRow>> batches) {
        for (List<ImportRow> batch : batches) {
            batchWorker.importOneBatch(batch);
        }
    }
}
~~~

Each call through the BatchWorker bean goes through the proxy and can create a separate transaction according to propagation. This is the right approach when you want each batch to commit independently.

In standard proxy mode, place **@Transactional** on methods called from outside the bean and avoid relying on self-invocation. Also verify proxy type and method visibility according to your Spring version and project configuration.

## 14. Do not wrap long-waiting operations inside a transaction

A transaction holds database resources such as a connection and may hold locks. If you open a transaction and then call a slow HTTP service, send an email, or wait for user confirmation, the transaction can remain open unnecessarily long.

Example to avoid:

~~~java
@Transactional
public void placeOrder(...) {
    orderRepository.save(...);
    paymentGateway.charge(...); // Network call that may take several seconds.
    orderRepository.markPaid(...);
}
~~~

Problems:
- The database connection may be held while waiting on the network.
- Locks may remain held for a long time.
- If the payment gateway succeeds but the database rolls back, the two systems become out of sync.
- A database transaction cannot roll back a payment already executed by an external system.

Instead, design a stateful, idempotent multi-step workflow. For example:
1. Inside a database transaction, create the Order in PENDING status and write an outbox event.
2. Commit the transaction.
3. A worker reads the outbox and calls the payment provider.
4. Based on the result, the worker opens a new transaction to update the Order status.
5. On transient failures, retry using an idempotency key and clear policies.

This is an asynchronous workflow/saga tailored to the business, not an ACID transaction spanning both the database and the payment provider.

## 15. Transactional outbox and post-commit events

If you need to publish an event after saving data, do not casually publish a message before the database transaction commits.

Failure scenario:
- The application publishes OrderPlaced.
- The database commit fails.
- Consumers have received the event, yet the Order does not exist.

Or the reverse:
- The database commit succeeds.
- The application crashes before publishing the event.
- Other systems never receive the notification.

Transactional outbox solves this by writing business data and the event record in the same database transaction:

~~~java
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = orderRepository.save(
            PurchaseOrder.create(command)
    );

    outboxRepository.save(
            OutboxEvent.orderPlaced(order.getId())
    );

    return order.getId();
}
~~~

After commit, a separate worker reads the outbox, sends the message, and marks it processed. You need to design retries, record locking/claiming, duplicate message handling, and consumer idempotency.

**@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)** is also useful when you want to handle an event only after the transaction commits. However, an in-memory listener does not by itself guarantee durable event delivery if the process stops immediately after commit; an outbox is better suited when losing events is unacceptable.

## 16. Lazy loading and transaction scope

Entities with LAZY associations usually load related data only when the property is accessed. If a service returns an Entity and the controller/serializer accesses associations after the transaction has ended, you may encounter a LazyInitializationException or trigger unexpected queries.

A clean approach is to load the required data and map it to a DTO inside the service transaction:

~~~java
@Transactional(readOnly = true)
public OrderDetails getDetails(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    return new OrderDetails(
            order.getId(),
            order.getCustomer().getName(),
            order.getItems().stream()
                    .map(item -> new OrderLineDetails(
                            item.getProduct().getName(),
                            item.getQuantity()
                    ))
                    .toList()
    );
}
~~~

The example requires appropriate mappings and a fetch strategy. If multiple associations are accessed, use a fetch join, EntityGraph, or intentional projection to avoid N+1 queries.

Do not extend a transaction merely to keep an Entity alive until the response is serialized. Explicitly define the data needed for the response and load it within the service scope.

## 17. Isolation and concurrency

A transaction boundary ensures a group of changes belongs to the same transaction, but it does not automatically solve all contention issues between concurrent transactions.

For example, two customers buying the last remaining item at the same time:
1. Transaction A reads stock = 1.
2. Transaction B reads stock = 1.
3. Both check that sufficient stock is available.
4. Both attempt to decrease stock.

Without an appropriate concurrency mechanism, overselling can occur.

Options:
- **Optimistic locking:** add **@Version**; when two transactions modify the same Entity concurrently, one transaction can fail because the version changed.
- **Pessimistic locking:** use appropriate database locks when rows must be locked for the duration of the transaction.
- **Atomic update:** use a conditional UPDATE statement such as `WHERE stock >= :quantity`, then check the affected row count.
- **Database constraint:** use constraints to protect invariants at the data layer.

The default isolation level depends on the database and configuration. Only increase isolation when consistency requirements demand it and you understand the impact on locks, throughput, and deadlocks.

**@Transactional(isolation = Isolation.SERIALIZABLE)** is not a free "absolute safety" switch. It can reduce concurrency or force transactions to retry. Choose a mechanism suited to the specific invariant.

## 18. @Version and concurrent updates

Example of an Entity with optimistic locking:

~~~java
@Entity
public class Product {

    @Id
    private Long id;

    @Version
    private Long version;

    private int stock;

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (stock < quantity) {
            throw new InsufficientStockException(id);
        }
        stock -= quantity;
    }
}
~~~

When Hibernate updates an Entity with **@Version**, the UPDATE statement typically checks both the ID and the old version, then increments the version. If another transaction has already updated the same row, the updated row count may be 0 and the provider throws an optimistic locking exception.

The service should let that error exit the transaction to roll back. If retrying, only retry operations that can be safely retried and re-evaluate the stock state after reading fresh data.

## 19. Multiple databases and transaction managers

A standard Spring transaction manages a single transaction manager. If two Repositories use two independent datasources, placing a single **@Transactional** does not by default guarantee that both databases commit or roll back together.

Scenarios:

- Multiple Repositories sharing one datasource and transaction manager: usually able to participate in the same transaction.
- Two datasources with two local transaction managers: each datasource has its own transaction; one committing while the other fails can leave an inconsistent state.
- Distributed atomicity required: consider JTA/XA if infrastructure and databases support it, or design a saga/outbox and compensating actions.

XA/distributed transactions increase operational complexity and cost. In microservice architectures, stateful workflows, outbox, retries, and compensating actions are usually preferred over holding a database transaction open across multiple services.

## 20. Transactions in batch jobs

For large batches, you should not always open a single transaction for hundreds of thousands of records. A long transaction can:
- Hold connections for a long time.
- Increase lock duration.
- Bloat the persistence context.
- Increase dirty checking overhead and memory usage.
- Make retries difficult if an error occurs near the end of the batch.

You can split the work into smaller batches, each as a business operation with its own transaction:

~~~java
@Service
public class ImportCoordinator {

    private final ImportBatchWorker worker;

    public ImportCoordinator(ImportBatchWorker worker) {
        this.worker = worker;
    }

    public void importRows(List<List<ImportRow>> batches) {
        for (List<ImportRow> batch : batches) {
            worker.processBatch(batch);
        }
    }
}

@Service
public class ImportBatchWorker {

    @Transactional
    public void processBatch(List<ImportRow> batch) {
        // Validate and write one batch.
    }
}
~~~

Separating beans ensures calls go through the proxy. If one batch should fail without affecting previously committed batches, this is the right boundary. If the entire file must be atomic, a different design is needed, accepting either a large transaction or a staging workflow/status switch after the import completes.

## 21. Timeout and lock timeout

A business operation may hang or wait on locks for too long. **@Transactional** supports a timeout in seconds:

~~~java
@Transactional(timeout = 10)
public void confirmOrder(Long orderId) {
    // Operation must complete within the time limit.
}
~~~

Timeout is a hint/setting for the transaction manager and resource; exact enforcement depends on the platform. It does not replace separate timeouts for HTTP clients, message brokers, or external systems.

Lock timeouts can be configured via JPA query hints or provider-specific lock settings. Clearly define behavior upon timeout: rollback, retry, report an error to the user, or transition to a pending state.

## 22. Testing transaction boundaries

You should test not only that each Repository can save data, but also that the entire business operation rolls back together.

Integration test example:

~~~java
@SpringBootTest
class OrderTransactionIntegrationTest {

    @Autowired
    private OrderApplicationService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private ProductRepository productRepository;

    @Test
    void rollsBackAllDatabaseChangesWhenOrderCreationFails() {
        Product product = productRepository.saveAndFlush(
                new Product("Keyboard", 5)
        );

        int stockBefore = product.getStock();

        assertThrows(
                OrderCreationException.class,
                () -> orderService.placeOrder(
                        CreateOrderCommand.invalidForTest(product.getId())
                )
        );

        Product reloaded = productRepository.findById(product.getId())
                .orElseThrow();

        assertEquals(stockBefore, reloaded.getStock());
        assertEquals(0, orderRepository.count());
    }
}
~~~

This is an illustrative structure; fixtures and a controlled failure point in the service are needed to verify rollback. Do not annotate the test class or test method with **@Transactional** if the goal is to observe the service transaction committing/rolling back independently without fully understanding Spring test transactions. Test slices such as **@DataJpaTest** usually run inside a transaction and roll back after the test, so consider how state is verified after the service finishes.

What to test:
1. Success: all expected changes exist.
2. Failure in a later step: earlier database changes roll back.
3. Checked exceptions roll back when rollbackFor is configured.
4. REQUIRED joins an outer transaction.
5. REQUIRES_NEW commits independently when that is the requirement.
6. Optimistic locking detects concurrent updates.
7. Outbox is written in the same transaction as business data.
8. Events are only processed after commit.
9. Batches with separate transactions commit/roll back within their proper scope.
10. No unexpected lazy queries occur outside a transaction.

## 23. Common mistakes

**Placing a separate transaction on each Repository operation**

Operations may commit independently, leaving a use case partially completed. Place the transaction on the service enclosing the changes that need to be atomic.

**Assuming save() means commit**

save() usually only persists/merges in the persistence context; SQL may be flushed later and commit occurs at the transaction boundary.

**Confusing flush with commit**

flush sends pending changes to the database, but the transaction can still roll back.

**Catching an exception and returning normally**

The transaction may commit if the error did not mark the transaction rollback-only. Rethrow the error or mark rollback-only when the business logic requires a rollback.

**Using a checked exception and forgetting rollbackFor**

Checked exceptions do not roll back under the standard default rules. Declare rollbackFor or configure appropriate rollback rules.

**Using REQUIRES_NEW for an operation that must be atomic with the main operation**

The child transaction can commit even if the outer transaction rolls back. Use REQUIRED if the changes belong to the same business invariant.

**Using self-invocation and expecting the proxy to apply the annotation**

Internal calls via `this` do not go through the standard proxy. Split into separate beans or design clear method boundaries.

**Holding a transaction while making HTTP calls or waiting for user input**

Connections and locks can be held for a long time; external systems cannot roll back together with the database. Use outbox/saga or multi-step workflows.

**Assuming one @Transactional covers all databases**

A transaction applies only to the configured transaction manager/resource. Multiple datasources require a dedicated distributed design.

**Failing to control concurrent updates**

Atomicity alone does not prevent lost updates or overselling inventory. Use @Version, locks, atomic updates, or constraints.

## 24. Process for defining transaction boundaries

When designing a use case, answer:

1. What is this business operation and what must a successful outcome guarantee?
2. Which database changes must commit or roll back together?
3. Do the Repositories share the same datasource and transaction manager?
4. Which service method is the entry point of the use case?
5. Is REQUIRED sufficient for child services to join the current transaction?
6. Are there any checked exceptions that must trigger a rollback?
7. Are there HTTP, email, or message broker operations that need to move outside the transaction?
8. Is an outbox or saga needed to coordinate external systems?
9. Is there a risk of concurrent updates, deadlocks, or long-running transactions?
10. Which Page/DTO/fetch plan is needed to read data inside the transaction without causing unexpected lazy loading?
11. Do integration tests prove both commit and rollback of the entire use case?

The design principle is to place the transaction where business invariants are understood, keep it short enough to avoid holding resources for too long, and enclose precisely the database changes that need to be atomic.

## 25. Conclusion

Transaction boundaries in Spring Data JPA should usually be placed on the service method representing a single business operation. A transaction can span multiple Repositories if they use the same transaction manager and appropriate resource. Default REQUIRED lets child services join the current transaction; REQUIRES_NEW creates an independent transaction and can commit even if the outer operation rolls back. Understand rollback rules, proxies/self-invocation, flush versus commit, isolation, and concurrent updates. Network calls and message brokers do not automatically roll back with the database; use an outbox or saga workflow when coordination is needed. Test both the happy path and mid-way failures to prove the entire operation commits or rolls back according to business invariants.
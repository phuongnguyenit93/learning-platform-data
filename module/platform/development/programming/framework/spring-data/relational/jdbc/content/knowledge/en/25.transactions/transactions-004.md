# Coordinating Multiple Repositories in a Single Transaction

In a business use case, an application often needs to modify multiple aggregates through multiple repositories. For example, when placing an order, the system both deducts inventory quantity and creates an order. If deducting inventory succeeds while saving the order fails, the data can end up in an inconsistent state.

Spring Data JDBC uses Spring JDBC's transaction management. To ensure multiple repository calls succeed or roll back together, place the **transaction boundary at the service/facade wrapping the entire use case** using §@Transactional§.

When repositories use the same §DataSource§ and the same JDBC transaction manager, their operations can participate in the same transaction. The default §Propagation.REQUIRED§ creates a transaction if none exists or joins the existing transaction.

This lesson explains how to coordinate multiple repositories in one transaction, the role of the service, how rollback works, limitations when using multiple transaction managers or multiple databases, and common mistakes.

## 1. Why Do We Need a Transaction Wrapping Multiple Repositories?

Suppose an order placement use case must perform two operations:

1. Deduct inventory quantity in the §InventoryItem§ aggregate.
2. Create the §PurchaseOrder§ aggregate.

The two aggregates have separate repositories:

~~~text
PlaceOrderService
       |
       +---- InventoryRepository
       |          |
       |          +---- inventory_items
       |
       +---- PurchaseOrderRepository
                  |
                  +---- purchase_orders
~~~

If each repository call runs in its own transaction, the following can happen:

~~~text
Transaction A: InventoryRepository.save(...)
    COMMIT

Transaction B: PurchaseOrderRepository.save(...)
    ERROR
    ROLLBACK

Result:
    Inventory has been deducted
    Order has not been created
~~~

This is an invalid state for the order placement workflow. The system reserved stock without a corresponding order.

A transaction wrapping both operations yields:

~~~text
PlaceOrderService.placeOrder(...)
    BEGIN

    InventoryRepository.save(...)
    PurchaseOrderRepository.save(...)

    COMMIT if all succeed
    ROLLBACK if an error triggers transaction rollback
~~~

If creating the order fails, the uncommitted inventory change is rolled back as well.

**Repositories manage persistence operations for individual aggregates; services manage the transaction boundary of a multi-step use case.**

## 2. How Does Spring Data JDBC Manage Transactions?

Spring Data JDBC uses Spring JDBC's transaction infrastructure. In a typical JDBC application, the key components are:

- §DataSource§: supplies connections to the database.
- §PlatformTransactionManager§: manages transactions for a resource.
- §JdbcTransactionManager§ or §DataSourceTransactionManager§: transaction manager for JDBC.
- Repositories and §JdbcAggregateTemplate§: perform read/write operations via JDBC.
- §@Transactional§: declares transaction boundaries on services or repositories.

With a single database and a single §DataSource§, the architecture typically looks like:

~~~text
                    Spring Application
                            |
                            v
                   PlaceOrderService
                     @Transactional
                            |
             +--------------+--------------+
             |                             |
             v                             v
      InventoryRepository          OrderRepository
             |                             |
             +--------------+--------------+
                            |
                            v
                    JDBC infrastructure
                            |
                  PlatformTransactionManager
                            |
                            v
                         DataSource
                            |
                            v
                         Database
~~~

The transaction manager binds the JDBC connection to the current transaction. JDBC operations using the same resource and transaction manager can join that transaction instead of committing independently.

### 2.1. Conditions for Multiple Repositories to Share a Transaction

Typically you must ensure:

1. The repositories use the same database resource, i.e., the same §DataSource§ or the same resource managed by the transaction manager.
2. The repositories are configured with the same JDBC transaction manager.
3. The service opens the transaction using that transaction manager.
4. Repository calls execute within the same transaction context, usually the same thread in an imperative Spring application.
5. Operations do not open independent transactions via a different propagation mode.

Having two repositories in the same package or both extending §CrudRepository§ is not enough to guarantee they share a transaction. What matters is the resource and transaction manager they use.

If two repositories access two different schemas on the same database connection/resource, they can still participate in the same transaction. If they use two separate databases and two independent §DataSource§ instances, a standard JDBC transaction manager cannot automatically turn them into a single atomic transaction.

## 3. Placing @Transactional at the Service/Facade

A simple example:

~~~java
@Service
public class OrderManagementService {

    private final InventoryRepository inventoryRepository;
    private final PurchaseOrderRepository orderRepository;

    public OrderManagementService(
            InventoryRepository inventoryRepository,
            PurchaseOrderRepository orderRepository
    ) {
        this.inventoryRepository = inventoryRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public PurchaseOrder placeOrder(
            String sku,
            int quantity
    ) {
        InventoryItem item = inventoryRepository.findBySku(sku)
                .orElseThrow();

        item.reserve(quantity);
        inventoryRepository.save(item);

        PurchaseOrder order = new PurchaseOrder(
                null,
                sku,
                quantity,
                "PLACED"
        );

        return orderRepository.save(order);
    }
}
~~~

§@Transactional§ wraps the entire §placeOrder§ invocation. When the method is called through a Spring transaction proxy:

- A transaction starts before the method body runs if no current transaction exists.
- Repository calls inside join that transaction.
- If the method finishes normally, the transaction is committed.
- If an error matching rollback rules occurs, the transaction is rolled back.

There is no need to put a separate §@Transactional§ around each repository statement inside this service.

### 3.1. Why Put Transactions on the Service?

A repository typically represents persistence operations for a single aggregate. A business use case may require multiple repositories.

Examples:

| Use case | Participating repositories |
| --- | --- |
| Place order | §InventoryRepository§, §PurchaseOrderRepository§ |
| Create account and profile | §AccountRepository§, §ProfileRepository§ |
| Transfer funds | §WalletRepository§, §LedgerRepository§ |
| Assign user roles | §UserRepository§, §RoleRepository§ |
| Complete order | §PurchaseOrderRepository§, §ShipmentRepository§ |

The service knows which steps must succeed together. Therefore, the service is the natural place to declare the transaction boundary.

If transactions are placed only on individual repository methods, each call may run in an independent transaction when no outer transaction exists. Then a failure in the second operation will not necessarily roll back the already-committed first operation.

## 4. Complete Example: Placing an Order and Reserving Inventory

We build two independent aggregate roots:

- §InventoryItem§ manages the stock quantity for a SKU.
- §PurchaseOrder§ manages the purchase order.

Both share the same database and transaction manager.

### 4.1. InventoryItem Aggregate

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("inventory_items")
public record InventoryItem(
        @Id Long id,
        String sku,
        int availableQuantity,
        @Version Long version
) {

    public InventoryItem reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive"
            );
        }

        if (availableQuantity < quantity) {
            throw new InsufficientStockException(sku);
        }

        return new InventoryItem(
                id,
                sku,
                availableQuantity - quantity,
                version
        );
    }
}
~~~

§@Version§ enables Spring Data JDBC to detect certain cases where an aggregate is updated concurrently. If another transaction has changed the version after the aggregate was read, saving can fail with an optimistic locking failure.

Business exception:

~~~java
public class InsufficientStockException
        extends RuntimeException {

    public InsufficientStockException(String sku) {
        super("Insufficient stock for SKU: " + sku);
    }
}
~~~

### 4.2. PurchaseOrder Aggregate

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String sku,
        int quantity,
        String status
) {
}
~~~

### 4.3. Repositories

~~~java
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);
}
~~~

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

The two repositories can be independent in domain terms while sharing the same transaction manager and database resource.

### 4.4. Service Coordinating Both Repositories

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final InventoryRepository inventoryRepository;
    private final PurchaseOrderRepository orderRepository;

    public PlaceOrderService(
            InventoryRepository inventoryRepository,
            PurchaseOrderRepository orderRepository
    ) {
        this.inventoryRepository = inventoryRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public PurchaseOrder placeOrder(
            String sku,
            int quantity
    ) {
        InventoryItem inventory =
                inventoryRepository.findBySku(sku)
                        .orElseThrow();

        InventoryItem reserved = inventory.reserve(quantity);

        inventoryRepository.save(reserved);

        PurchaseOrder order = new PurchaseOrder(
                null,
                sku,
                quantity,
                "PLACED"
        );

        return orderRepository.save(order);
    }
}
~~~

The transaction wraps reading inventory, updating inventory, and creating the order.

### 4.5. What Happens When an Error Occurs?

Suppose inventory is sufficient, but inserting the order violates a constraint:

~~~text
placeOrder("SKU-01", 2)
       |
       v
BEGIN
       |
       v
SELECT inventory_items
       |
       v
UPDATE inventory_items
       |
       v
INSERT purchase_orders
       |
       v
Database reports error
       |
       v
ROLLBACK
       |
       +---- inventory_items changes are undone
       |
       +---- purchase_orders is not created
~~~

The database only confirms changes when the transaction commits. A repository method returning an object after a write command does not mean the outer transaction has committed; commit occurs when the transaction boundary completes.

## 5. Repository Default CRUD Methods and Query Methods

Spring Data JDBC configures repository CRUD methods with default transactions:

- CRUD read operations have the §readOnly = true§ flag.
- CRUD write operations use §@Transactional§ with default settings.

However, user-declared query methods require separate attention. The Spring Data Relational documentation recommends marking query methods as transactional, typically with §@Transactional(readOnly = true)§ on the repository interface or calling them inside a transactional service.

Example:

~~~java
import java.util.List;

import org.springframework.data.repository.CrudRepository;
import org.springframework.transaction.annotation.Transactional;

@Transactional(readOnly = true)
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByStatus(String status);
}
~~~

If a query method is called from a service that already has an active transaction, it joins the outer transaction under the default propagation.

### 5.1. Why Do Query Methods Also Need Transactions?

A Spring Data JDBC aggregate query may require multiple SQL statements to load the root and owned entities inside the aggregate.

Without a shared transaction, the queries loading a single aggregate may execute on different connections. This can:

- Increase pressure on the connection pool.
- Prevent queries in the same read operation from sharing a transaction context.
- Increase the risk of deadlocks when multiple operations hold a connection while requesting another.

Placing a transaction on the service or query method lets the necessary queries participate in a shared transaction.

### 5.2. readOnly Configuration Is Not a Security Barrier

§@Transactional(readOnly = true)§ expresses that the use case is expected to be read-only. This is usually a hint passed to the transaction manager/JDBC driver for optimization.

Do not treat §readOnly = true§ as a strict enforcement check guaranteeing that code cannot execute INSERT or UPDATE. Specific behavior depends on the database and driver; some databases may reject writes inside a read-only transaction.

If a service performs both reads and writes, use the default read-write transaction.

## 6. Transaction Propagation: REQUIRED and REQUIRES_NEW

The §propagation§ attribute determines how a method behaves when a transaction already exists.

### 6.1. REQUIRED Is the Default

§Propagation.REQUIRED§ has two behaviors:

- If no transaction exists, create a new transaction.
- If a transaction exists, join the current transaction.

Example:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(
            InventoryRepository inventoryRepository
    ) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserve(String sku, int quantity) {
        // Read and update inventory
    }
}
~~~

Coordinating service:

~~~java
@Service
public class OrderService {

    private final InventoryService inventoryService;
    private final PurchaseOrderRepository orderRepository;

    public OrderService(
            InventoryService inventoryService,
            PurchaseOrderRepository orderRepository
    ) {
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void placeOrder(String sku, int quantity) {
        inventoryService.reserve(sku, quantity);
        orderRepository.save(
                new PurchaseOrder(null, sku, quantity, "PLACED")
        );
    }
}
~~~

If calling §inventoryService.reserve§ goes through a Spring proxy and uses the same transaction manager, `InventoryService`'s transaction joins the transaction opened by `OrderService`. An error in the order-saving step can roll back the inventory change as well.

### 6.2. REQUIRES_NEW Creates an Independent Transaction

§Propagation.REQUIRES_NEW§ always creates a new physical transaction. The outer transaction is suspended while the inner transaction runs.

Example:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAuditEvent(AuditEvent event) {
    auditRepository.save(event);
}
~~~

If the audit is saved in a REQUIRES_NEW transaction and commits successfully, and then the outer order placement transaction rolls back, the audit record still remains.

This differs from §REQUIRED§.

Only use REQUIRES_NEW when you genuinely want the inner result to commit independently of the outer transaction. If the goal is for order creation and inventory deduction to succeed or fail together, do not use REQUIRES_NEW for either operation.

**REQUIRES_NEW also requires an extra connection/resource while the outer transaction holds its resource.** Under concurrent load, an undersized connection pool can cause connection exhaustion or deadlocks.

### 6.3. NESTED and Savepoints

§Propagation.NESTED§ can use a single physical transaction with a savepoint to roll back part of the inner work while the outer transaction continues.

With JDBC, this mechanism is typically based on savepoints. Availability depends on the transaction manager, database, and savepoint support configuration. Do not assume every database or transaction manager supports it identically.

If there is no explicit partial-rollback requirement, §REQUIRED§ is usually the simpler choice for multi-repository use cases.

### 6.4. Propagation Comparison Table

| Propagation | When no transaction exists | When a transaction exists | Independent rollback? |
| --- | --- | --- | --- |
| §REQUIRED§ | Creates a transaction | Joins the current transaction | No |
| §REQUIRES_NEW§ | Creates a new transaction | Suspends outer transaction, creates a new one | Yes |
| §NESTED§ | Creates a transaction | Uses a savepoint in the current transaction if supported | Rolls back to savepoint |

## 7. Rollback Rules

Spring declarative transaction defaults:

- §RuntimeException§ triggers transaction rollback.
- §Error§ triggers transaction rollback.
- Checked exceptions do not automatically trigger rollback under default rules.

Runtime exception example:

~~~java
@Transactional
public void placeOrder(...) {
    inventoryRepository.save(...);

    throw new InsufficientStockException("SKU-01");
}
~~~

The transaction rolls back because §InsufficientStockException§ extends §RuntimeException§.

### 7.1. Checked Exceptions and rollbackFor

If a method throws a checked exception and the business logic requires rollback, declare it explicitly:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importOrders() throws IOException {
    // Write through multiple repositories
}
~~~

You can specify specific checked exception types rather than rolling back on every §Exception§.

Do not convert all checked exceptions into runtime exceptions just to force rollback if distinguishing error types is meaningful to the API or domain.

### 7.2. Catching an Exception Without Rethrowing

Example:

~~~java
@Transactional
public void placeOrder(...) {
    try {
        inventoryRepository.save(...);
        orderRepository.save(...);
    } catch (DataAccessException ex) {
        log.error("Cannot place order", ex);
        // Not rethrown and not marked rollback-only
    }
}
~~~

If the exception is caught and the method completes normally, the transaction interceptor may consider the method successful and commit earlier changes.

If rollback is required:

- Rethrow the exception so the transaction interceptor detects it.
- Or explicitly mark the transaction rollback-only when the exception must be handled locally.

Rethrow example:

~~~java
@Transactional
public void placeOrder(...) {
    try {
        inventoryRepository.save(...);
        orderRepository.save(...);
    } catch (DataAccessException ex) {
        log.error("Cannot place order", ex);
        throw ex;
    }
}
~~~

Logging an error does not substitute for a rollback decision. Clearly determine which errors must abort the entire use case and which may be handled to continue.

### 7.3. Inner Transaction Marks Rollback-Only

When a method joins an existing transaction and marks it rollback-only, the outer method cannot force the transaction to commit simply by catching the inner exception.

If the outer method finishes normally after the transaction has been marked rollback-only, Spring can throw §UnexpectedRollbackException§ at commit time to report that the transaction actually rolled back.

## 8. Transaction Proxies and Self-Invocation

§@Transactional§ in proxy mode works when method calls pass through a Spring proxy.

Example:

~~~java
@Service
public class OrderService {

    public void submit() {
        placeOrder(); // Self-invocation
    }

    @Transactional
    public void placeOrder() {
        // ...
    }
}
~~~

Calling §placeOrder()§ from the same instance bypasses the proxy, so the annotation on the method may not apply as expected.

A clearer pattern is having another bean invoke the transactional method:

~~~java
@Service
public class OrderService {

    @Transactional
    public void placeOrder() {
        // Multiple repository calls
    }
}

@Component
public class OrderJob {

    private final OrderService orderService;

    public OrderJob(OrderService orderService) {
        this.orderService = orderService;
    }

    public void run() {
        orderService.placeOrder();
    }
}
~~~

When §OrderJob§ calls the §OrderService§ bean through the Spring proxy, the transaction interceptor can open a transaction.

If the application does not use Spring Boot auto-configuration for transactions, enable annotation-driven transaction management with §@EnableTransactionManagement§ or equivalent configuration.

## 9. Choosing the Right Transaction Manager

In a simple application, there is usually a single transaction manager named §transactionManager§, which §@Transactional§ uses by default.

If multiple transaction managers exist, specify the right one explicitly:

~~~java
@Transactional("ordersTransactionManager")
public void placeOrder(...) {
    // ...
}
~~~

Or:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void placeOrder(...) {
    // ...
}
~~~

The specified name must match the actual transaction manager bean.

### 9.1. Repositories Must Use the Matching Manager

When configuring multiple repository groups with §@EnableJdbcRepositories§, the §transactionManagerRef§ attribute specifies the transaction manager used by that repository group.

Example:

~~~java
@EnableJdbcRepositories(
        basePackages = "com.example.orders.repository",
        transactionManagerRef = "ordersTransactionManager"
)
@Configuration
public class OrdersRepositoryConfiguration {
}
~~~

Service using the corresponding transaction manager:

~~~java
@Transactional("ordersTransactionManager")
public void placeOrder(...) {
    // Order repositories
}
~~~

If the service selects a different transaction manager from the repositories, the repositories may not join the same transaction as expected.

## 10. Multiple Repositories on One Database vs. Multiple Databases

This distinction must be clearly understood.

### 10.1. Multiple Repositories, Same DataSource

~~~text
Repository A ----+
                 |
Repository B ----+----> Same DataSource
                 |          |
Repository C ----+          v
                       One JDBC transaction
~~~

A JDBC transaction manager managing the same DataSource can coordinate the repositories. This is the simplest and most common case.

### 10.2. Multiple Repositories, Multiple Schemas, Same Resource

If the schemas live on the same database connection and the transaction manager manages that same resource, they can participate in the same transaction.

Verify schema access permissions, SQL qualification, and datasource configuration, but the transaction boundary can still be a single one.

### 10.3. Multiple Repositories, Multiple DataSources

~~~text
OrderRepository ----> ordersDataSource
                         |
                         v
                  ordersTransactionManager

AccountRepository --> accountDataSource
                         |
                         v
                  accountTransactionManager
~~~

A standard §DataSourceTransactionManager§ or §JdbcTransactionManager§ manages only its own resource. Placing §@Transactional§ on a service does not automatically create an atomic transaction across both databases.

If a service calls two repositories belonging to two independent transaction managers:

- The first database's transaction may commit.
- The second database's transaction may fail.
- There is no automatic rollback across both resources from a single standard §@Transactional§ annotation.

If true atomic commits across multiple resources are required, you need a suitable distributed transaction solution such as JTA/XA with supporting resources and drivers. This choice carries significant configuration and operational overhead.

In many microservice systems, Saga, transactional outbox, and compensating actions are used instead of trying to stretch a JDBC transaction across multiple services or databases.

## 11. Do Not Open a JDBC Transaction Around HTTP Calls

A JDBC transaction only manages the resources controlled by its transaction manager. It cannot roll back an action that already happened in an external system over HTTP.

Example:

~~~java
@Transactional
public void placeOrder(...) {
    inventoryRepository.save(...);
    paymentClient.charge(...);
    orderRepository.save(...);
}
~~~

If §paymentClient.charge§ charges funds successfully and then §orderRepository.save§ fails, a database rollback cannot automatically refund the charge at the payment provider.

In addition, keeping a database transaction open while waiting for HTTP can hold connections and locks for a long time, reducing throughput for other requests.

A common design pattern:

1. Within a database transaction, update inventory and create the order in a pending state.
2. Write an outbox event in the same transaction.
3. Commit the transaction.
4. A worker reads the outbox and calls the payment provider.
5. Update payment/order status in a new transaction.
6. Retry or run a compensating workflow if the external system fails.

Diagram:

~~~text
Database transaction
  +-- reserve inventory
  +-- create pending order
  +-- insert outbox event
             |
             v
           COMMIT
             |
             v
       Outbox publisher
             |
             v
       Payment provider
             |
             v
       Update order status
~~~

The transactional outbox ensures the event to be sent is persisted alongside the database change. It does not make HTTP part of the JDBC transaction; it establishes a durable post-commit communication workflow.

## 12. Transactions in Asynchronous Flows and Multiple Threads

Spring JDBC transactions are normally bound to the current thread. Do not assume a transaction propagates automatically to:

- Methods invoked via §@Async§.
- Tasks submitted to an executor.
- Manually spawned threads.
- Standalone background jobs.
- Other HTTP requests or services.

Example:

~~~java
@Transactional
public void placeOrder() {
    inventoryRepository.save(...);

    asyncService.createOrderAsync();
}
~~~

If §createOrderAsync§ runs on another thread, it does not automatically join the calling thread's JDBC transaction. It may run in its own transaction or without a transaction depending on the target method's configuration.

If a single atomic transaction is needed, execute the required JDBC operations in the same transaction context. If work must run asynchronously after commit, use events/outbox and a separate transaction for the worker.

## 13. Consistent Reads When Coordinating Repositories

Transactions are not just for writes. A service may need to read from multiple repositories to make a business decision.

Example:

~~~java
@Transactional(readOnly = true)
public OrderSummary getOrderSummary(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow();

    Customer customer = customerRepository.findById(order.customerId())
            .orElseThrow();

    return new OrderSummary(
            order.id(),
            customer.name(),
            order.status()
    );
}
~~~

A shared transaction lets the read operations participate in the same transaction context and avoids each repository acquiring an independent transaction.

However, **a transaction does not automatically imply snapshot isolation**. Actual isolation level behavior is determined by the transaction manager/database. If business logic requires consistent reads under specific concurrent modifications, consider appropriate isolation levels, locking, or optimistic versions.

### 13.1. readOnly = true

For read-only use cases, you can use:

~~~java
@Transactional(readOnly = true)
public OrderSummary getOrderSummary(Long orderId) {
    // Read from multiple repositories
}
~~~

The read-only flag is a hint to the transaction infrastructure/driver. It does not replace write authorization checks and does not guarantee that every database will reject mutating statements.

## 14. Transaction Timeouts and Long-Running Transactions

A transaction spanning multiple repositories can grow long if the service:

- Loops over thousands of aggregates.
- Calls external services.
- Waits for users or messages.
- Performs heavy CPU processing.
- Holds locks for an extended duration.

Long transactions can hold connections, locks, and database resources longer than necessary.

You can set a timeout:

~~~java
@Transactional(timeout = 10)
public void placeOrder(...) {
    // Operations expected to finish within a reasonable limit
}
~~~

Specific timeout support and enforcement depend on the transaction manager/database. If a timeout occurs, the transaction infrastructure may mark rollback or throw an error during access/commit.

For large batches, you can split the work into smaller chunks, each in its own transaction. Then each chunk commits independently; if a later chunk fails, earlier chunks remain committed. This changes business semantics and requires checkpoints and appropriate resume/retry mechanisms.

Do not use one massive transaction merely to feel like the entire batch is atomic if the database cannot hold resources that long.

## 15. Common Mistakes

**“Each repository is transactional on its own, so multiple repository calls automatically share one transaction.”** Incorrect. Without an outer transaction, calls may complete in separate transactions. Place §@Transactional§ on the service wrapping the use case.

**“Putting @Transactional on one repository is enough.”** That does not automatically wrap other repository calls made from the service. The boundary must span the entire business operation.

**“Two repositories extending CrudRepository is enough to join a transaction.”** No. They must use the same compatible transaction manager and resource.

**“@Transactional always manages every database in the application.”** No. A standard JDBC transaction manager only manages its own resource. Multiple independent DataSources need a separate coordination strategy if cross-resource atomicity is required.

**“REQUIRES_NEW is the same as REQUIRED.”** No. REQUIRES_NEW creates an independent physical transaction and can commit even if the outer transaction rolls back.

**“You can use REQUIRES_NEW on every repository call to be safe.”** No. That breaks use-case atomicity and can exhaust the connection pool.

**“Catching an exception and logging it means the transaction will roll back.”** No. If the method finishes normally after catching the exception, the transaction may commit. Rethrow or mark rollback-only.

**“Checked exceptions always roll back.”** Not by default. Use §rollbackFor§ if a checked exception must trigger rollback.

**“Calling a transactional method from the same class still goes through the proxy.”** Not in standard proxy mode. Self-invocation bypasses the Spring proxy.

**“@Transactional covers HTTP calls.”** No. A JDBC transaction cannot roll back side effects on external systems.

**“@Async automatically inherits the current transaction.”** No. Imperative JDBC transactions are typically thread-bound; another thread needs its own transaction.

**“readOnly = true strictly blocks all write statements.”** No. It is primarily a hint, depending on the driver/database.

**“A shared transaction always gives a consistent data snapshot.”** No. Consistency depends on the isolation level and database.

**“One long transaction is always better than many small transactions.”** No. Long transactions can hold connections/locks and increase operational risk; choose boundaries based on atomicity needs.

## 16. Process for Designing a Multi-Repository Use Case

When a business workflow needs to coordinate multiple repositories, follow these steps:

1. **Identify operations that must succeed together:** list which repositories participate and what state must be protected.
2. **Identify resources:** verify whether the repositories share the same DataSource/database.
3. **Choose the transaction manager:** ensure the service and repositories use the manager governing the right resource.
4. **Place the boundary on the service:** use §@Transactional§ on the method coordinating the use case.
5. **Keep propagation appropriate:** usually use REQUIRED; only use REQUIRES_NEW/NESTED when semantics explicitly demand it.
6. **Define rollback rules:** RuntimeException/Error roll back by default; configure rollbackFor for checked exceptions that must roll back.
7. **Do not swallow errors:** rethrow or mark rollback-only if the transaction must abort.
8. **Verify proxying:** invoke methods through Spring bean proxies; avoid self-invocation.
9. **Keep transactions short:** do not wait on HTTP calls or run long processing inside a JDBC transaction.
10. **Handle multiple databases:** use JTA/XA if distributed atomicity is truly required, or Saga/outbox for distributed workflows.
11. **Verify with integration tests:** confirm that if one repository write succeeds and the next fails, earlier writes roll back.
12. **Observe transactions:** check the actual transaction manager, datasource, and SQL in a test environment.

~~~mermaid
flowchart TD
    A["Use case needs multiple repositories"] --> B{"Do repositories share the same DataSource/resource?"}
    B -->|Yes| C["Choose the same JDBC transaction manager"]
    B -->|No| D["Evaluate JTA/XA or Saga/Outbox"]
    C --> E["Place @Transactional on service"]
    E --> F["Repositories join with REQUIRED"]
    F --> G{"Rollback error?"}
    G -->|Yes| H["Throw exception / rollback-only"]
    G -->|No| I["Commit"]
    H --> J["Roll back all changes in transaction"]
    D --> K["Design multi-resource coordination"]
~~~

## 17. Testing Transactions Across Multiple Repositories

An integration test should verify not only that each repository works individually, but also the transaction boundary itself.

Example scenario:

1. Prepare initial inventory of 10.
2. Call the service to order 2 items.
3. Verify inventory is 8 and the order was created.
4. Set up a condition causing order insertion to fail after inventory has been saved.
5. Call the service again.
6. Verify inventory remains 10 and no new order was created.

Illustrative test skeleton:

~~~java
@SpringBootTest
class PlaceOrderTransactionTest {

    @Autowired
    PlaceOrderService placeOrderService;

    @Autowired
    InventoryRepository inventoryRepository;

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Test
    void rollsBackInventoryWhenOrderInsertFails() {
        // Arrange:
        // - Create inventory with sufficient stock.
        // - Prepare data causing order insert to fail.

        // Act:
        assertThrows(
                RuntimeException.class,
                () -> placeOrderService.placeOrder("SKU-01", 2)
        );

        // Assert:
        InventoryItem inventory =
                inventoryRepository.findBySku("SKU-01")
                        .orElseThrow();

        assertEquals(10, inventory.availableQuantity());

        // Verify no order was created.
    }
}
~~~

A real test should induce a reproducible database error, such as a constraint violation during order insertion. Do not just throw an exception before calling the second repository, as such a test fails to prove the database actually executed and rolled back the first write.

Also pay attention to the test's own transaction. If the test method is marked §@Transactional§, the test framework may open an outer transaction and roll it back at the end of the test. Design setup and assertions so you can accurately observe the service's transaction boundary.

## 18. Key Takeaways

- A use case spanning multiple repositories should have a transaction boundary at the service/facade wrapping all operations requiring atomicity.
- Spring Data JDBC uses Spring JDBC's transaction management.
- Repositories must share the same DataSource/resource and compatible transaction manager to participate in the same JDBC transaction.
- CRUD repository methods are transactional by default; query methods should be marked transactional or executed inside a service transaction.
- REQUIRED is the default propagation: creates a transaction if none exists or joins the current one.
- REQUIRES_NEW creates an independent physical transaction; inner operations can commit even if the outer transaction rolls back.
- NESTED relies on savepoints and depends on transaction manager/database support.
- RuntimeException and Error roll back by default; checked exceptions requiring rollback must be configured with rollbackFor.
- Catching an exception and returning normally from a method can allow the transaction to commit; rethrow or mark rollback-only.
- @Transactional works via Spring proxies; self-invocation does not trigger the proxy in standard mode.
- One JDBC transaction manager does not automatically coordinate multiple independent DataSources. Use JTA/XA for distributed atomic commits or Saga/outbox for distributed workflows.
- JDBC transactions cannot roll back HTTP side effects; do not hold transactions open while waiting on external systems.
- Imperative transactions are typically thread-bound; @Async and other threads do not automatically inherit transactions.
- Choose isolation, timeout, and transaction length based on workload and consistency needs.

When coordinating multiple repositories, determine **which changes must commit or roll back together**, then place the transaction on the coordinating service and ensure all repositories use the right resource. That keeps a business use case consistent even when data is managed by multiple aggregates and repositories.

## References

- [Spring Data Relational 4.1.2 — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html)
- [Spring Framework — Declarative Transaction Management with @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Transaction Resource Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)

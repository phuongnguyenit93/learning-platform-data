# Choosing the @Transactional Boundary at the Service Layer in Spring Data JDBC

## 1. Why Should the Transaction Boundary Be at the Service Layer?

A business workflow typically consists of multiple persistence operations. For example, creating an order may require saving the order, saving the order lines, reserving inventory, and recording history. If one operation fails midway, the application usually wants all database changes to succeed together or roll back together.

If you rely only on the transaction of each repository method, individual calls may have separate commit boundaries. The first operation could already be committed before the next operation fails.

The service layer coordinates **a business use case**. Therefore, it is usually the right place to declare `@Transactional` wrapping all database operations that require a single combined outcome.

Example:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(
            OrderRepository orders,
            InventoryRepository inventory
    ) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        Order order = Order.create(command);
        Order saved = orders.save(order);

        inventory.reserve(
                command.productId(),
                command.quantity()
        );

        return saved;
    }
}
~~~

If saving the order succeeds but updating inventory raises an exception that rolls back the transaction, the database changes of both operations are rolled back together, provided they share the same transaction manager and DataSource.

The service defines the business boundary; repositories perform persistence operations inside that boundary.

## 2. What Does a Transaction Cover?

A JDBC transaction typically covers SQL statements executed on the same connection managed by the transaction manager. When the transaction commits, the database confirms the changes. When it rolls back, the database discards uncommitted changes in that transaction.

A use case may have this flow:

~~~mermaid
flowchart TD
    A["Controller calls service"] --> B["Open or join transaction"]
    B --> C["Repository saves aggregate"]
    C --> D["Repository updates related data"]
    D --> E["Repository writes history"]
    E --> F{"Rollback error?"}
    F -->|No| G["Commit"]
    F -->|Yes| H["Rollback"]
    G --> I["Return result to caller"]
    H --> J["Throw exception"]
~~~

For example, a funds transfer operation may need to update the source account, update the destination account, and record a transaction entry. If these three operations must succeed or fail together, they should live in a single service-managed transaction.

Do not set transaction boundaries solely based on how many repositories are called. Calling two repositories does not always mean they need one shared transaction; a single repository can also require multiple operations inside the same transaction. Base the decision on the consistency requirements of the use case.

## 3. Repository Default Transactions vs. Service Transactions

Spring Data JDBC provides CRUD implementations for repositories. Inherited CRUD methods generally already have transaction configuration: read operations are typically read-only, while write operations run in a transaction. However, application-declared query methods do not automatically carry the same transaction configuration as inherited CRUD methods.

This leads to two scenarios:

- Calling a CRUD repository method standalone: the repository's default transaction can wrap that call.
- Calling multiple repository methods inside a `@Transactional` service: the repository calls usually join the existing transaction under the default `REQUIRED` propagation.

Example without a service-level transaction:

~~~java
public void createOrder(CreateOrderCommand command) {
    orders.save(Order.create(command));
    inventory.reserve(command.productId(), command.quantity());
}
~~~

Each repository call may be managed in its own transaction according to the repository's configuration. If the first operation commits and the second operation fails, the database may keep the order even though inventory was never reserved.

Placing the transaction on the service:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    orders.save(Order.create(command));
    inventory.reserve(command.productId(), command.quantity());
}
~~~

With a shared transaction manager and DataSource, repository methods join the current transaction. Commit only occurs when the service method completes normally and the transaction has not been marked rollback-only.

**Practical rule:** if multiple database operations form a single business unit, place the transaction on the service method representing that unit.

## 4. Choosing Service Methods as Boundaries

A service can have multiple use cases, each with its own transaction policy:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customers;
    private final AddressRepository addresses;

    public CustomerService(
            CustomerRepository customers,
            AddressRepository addresses
    ) {
        this.customers = customers;
        this.addresses = addresses;
    }

    @Transactional
    public Customer register(RegisterCustomerCommand command) {
        Customer customer = customers.save(
                Customer.newCustomer(command.name(), command.email())
        );

        addresses.save(
                Address.forCustomer(customer.getId(), command.address())
        );

        return customer;
    }

    @Transactional(readOnly = true)
    public CustomerDetails getDetails(Long customerId) {
        Customer customer = customers.findById(customerId)
                .orElseThrow(() -> new CustomerNotFoundException(customerId));

        List<Address> customerAddresses =
                addresses.findByCustomerId(customerId);

        return CustomerDetails.from(customer, customerAddresses);
    }
}
~~~

`register` writes multiple related aggregates, so it needs a write transaction. `getDetails` only reads data, so it is marked read-only.

Not every method in a service must carry the annotation. If a method simply delegates to a single repository operation that already has an appropriate transaction, an extra annotation may be unnecessary. However, when a service method represents a use case requiring multiple atomic operations, declaring the boundary explicitly there makes the contract clearer and more reliable.

### 4.1. Class-Level or Method-Level?

You can place `@Transactional` at the class level:

~~~java
@Service
@Transactional
public class OrderService {
    // Public methods participate in a transaction by default.
}
~~~

Or place it on individual methods:

~~~java
@Service
public class OrderService {

    @Transactional
    public Order placeOrder(...) {
        // Write use case.
    }

    @Transactional(readOnly = true)
    public OrderDetails getDetails(...) {
        // Read-only use case.
    }
}
~~~

Placing it on the class reduces repetition when most methods share the same policy. Placing it on methods makes the distinction between read and write use cases explicit. Method-level annotations override class-level configuration.

For services that mix queries and updates, method-level declarations usually help readers immediately spot the transaction policy at each use case.

## 5. How Spring Applies @Transactional

In standard configurations, Spring manages transactions using an AOP proxy. The caller invokes a method through the proxy; the proxy begins or joins a transaction, invokes the target method, and then commits or rolls back based on the outcome.

~~~mermaid
sequenceDiagram
    participant C as Controller / Caller
    participant P as Spring Proxy
    participant S as Service
    participant R as Repository
    participant DB as Database
    C->>P: placeOrder()
    P->>P: Begin / join transaction
    P->>S: Invoke target method
    S->>R: save()
    R->>DB: INSERT / UPDATE
    DB-->>R: Result
    R-->>S: Saved entity
    S-->>P: Return or exception
    alt Method completes normally
        P->>DB: COMMIT
    else Exception triggers rollback
        P->>DB: ROLLBACK
    end
    P-->>C: Result
~~~

An annotation does not automatically turn every method call into a transaction. The call must pass through Spring's transaction interceptor mechanism.

### 5.1. Self-Invocation Bypasses the Proxy

A common pitfall is a method in the same class calling another `@Transactional` method via `this`:

~~~java
@Service
public class ImportService {

    public void importAll(List<ImportRow> rows) {
        this.importChunk(rows);
    }

    @Transactional
    public void importChunk(List<ImportRow> rows) {
        // Write data.
    }
}
~~~

Calling `this.importChunk(...)` is an internal call on the same object and does not pass through the proxy under default proxy-based transaction management. Consequently, the annotation on `importChunk` may not be applied as expected.

A clearer approach is to place the transaction on the method invoked by external callers:

~~~java
@Service
public class ImportService {

    @Transactional
    public void importAll(List<ImportRow> rows) {
        // Call repositories directly within the use-case transaction.
    }
}
~~~

Or extract chunk processing into another bean if each chunk requires an independent transaction:

~~~java
@Service
public class ImportCoordinator {

    private final ImportChunkService chunks;

    public ImportCoordinator(ImportChunkService chunks) {
        this.chunks = chunks;
    }

    public void importAll(List<ImportRow> rows) {
        for (List<ImportRow> chunk : split(rows, 500)) {
            chunks.importChunk(chunk);
        }
    }
}

@Service
public class ImportChunkService {

    @Transactional
    public void importChunk(List<ImportRow> chunk) {
        // Each call through the bean proxy can have its own transaction.
    }
}
~~~

This snippet illustrates the boundary; the `split` helper must be implemented according to the application. Because each call goes through another bean, `ImportChunkService`'s proxy can apply a transaction to each chunk.

### 5.2. Visibility and Invocation

For predictable behavior in standard proxy configurations, place `@Transactional` on public service methods and invoke them through Spring-managed beans. Specific method visibility support depends on proxy type and Spring version; avoid relying on uncommon behavior unnecessarily.

Do not instantiate services with `new OrderService(...)` and expect annotations to work. Beans must be Spring-managed and callers must go through the corresponding proxy.

## 6. Propagation: Repositories Joining the Service Transaction

The propagation attribute determines how a transactional method interacts with an existing transaction.

The default is `Propagation.REQUIRED`:

- If no transaction exists, Spring creates a new transaction.
- If a transaction already exists, the method joins the current transaction.

Example:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;

    @Transactional
    public void placeOrder(Order order) {
        orders.save(order);
        inventory.reserve(order.getProductId(), order.getQuantity());
    }
}
~~~

Standard repository calls join the open service transaction if they share the same transaction manager/DataSource and compatible propagation.

### 6.1. REQUIRED Is the Standard Choice

`REQUIRED` fits most use cases because all operations belong to the same transaction. If an inner operation fails in a way that marks the transaction rollback-only, the outer transaction cannot commit as if everything succeeded.

Example of service A calling service B, both using `REQUIRED`:

~~~java
@Service
public class CheckoutService {

    private final PaymentRecordService paymentRecords;

    @Transactional
    public void checkout(Order order) {
        // Save order.
        paymentRecords.record(order);
        // Operations in the same transaction.
    }
}

@Service
public class PaymentRecordService {

    @Transactional
    public void record(Order order) {
        // Save payment record.
    }
}
~~~

If both services use the same transaction manager, calling `record` joins `checkout`'s transaction. The commit boundary still belongs to the outermost transaction.

### 6.2. REQUIRES_NEW Creates an Independent Transaction

`Propagation.REQUIRES_NEW` suspends the current transaction and opens an independent transaction for the invoked method.

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordIndependentAudit(AuditRecord record) {
    auditRepository.save(record);
}
~~~

If the outer transaction rolls back, the committed independent audit transaction can still persist. This is sometimes useful for certain technical records, but you must understand the data semantics clearly.

Do not use `REQUIRES_NEW` just to "avoid transaction errors." It can commit data independently of the main business workflow, requires an extra connection while the outer transaction holds one, puts pressure on the connection pool, and leaves audit or auxiliary state behind even when the main use case fails.

If the audit must accurately reflect committed transactions, consider a transactional outbox or writing the audit inside the same transaction rather than detaching it arbitrarily.

### 6.3. NESTED and Savepoints

`Propagation.NESTED` can use a savepoint inside the current transaction if the transaction manager and JDBC driver support it. This is not an independent physical transaction like `REQUIRES_NEW`, and not every environment supports nested transactions in this way.

For most Spring Data JDBC services, start with `REQUIRED`. Only choose another propagation mode when independent commit/rollback requirements are clearly defined.

## 7. Rollback Rules: Which Exceptions Roll Back a Transaction?

Under Spring's default transaction rules, a transaction rolls back when a method exits with a `RuntimeException` or `Error`. Checked exceptions do not automatically trigger rollback.

Example:

~~~java
@Transactional
public void createOrder(Order order) throws IOException {
    orders.save(order);
    throw new IOException("Cannot complete use case");
}
~~~

If `IOException` is a checked exception and there is no additional rollback rule, Spring by default may commit the database transaction even though the method throws an exception to the caller.

If the business requires checked exceptions to also roll back:

~~~java
@Transactional(rollbackFor = IOException.class)
public void createOrder(Order order) throws IOException {
    orders.save(order);
    throw new IOException("Cannot complete use case");
}
~~~

You can specify multiple exception types:

~~~java
@Transactional(rollbackFor = {
        IOException.class,
        ValidationFailureException.class
})
public void process(...) throws IOException, ValidationFailureException {
    // ...
}
~~~

`noRollbackFor` can be used to declare an exception type that should not cause rollback, though use caution because the caller receives an error while database changes still commit.

### 7.1. Catching an Exception and Continuing

Example:

~~~java
@Transactional
public void process(Order order) {
    orders.save(order);

    try {
        inventory.reserve(order.getProductId(), order.getQuantity());
    } catch (InventoryException ex) {
        log.warn("Could not reserve inventory", ex);
        // Do not rethrow the exception.
    }
}
~~~

If the exception is caught and does not mark the transaction rollback-only, the method can complete normally and the transaction commits the changes already made. The result could be a saved order without reserved inventory.

If the business requires both to succeed together, let an appropriate exception propagate or wrap it in a runtime exception:

~~~java
@Transactional
public void process(Order order) {
    orders.save(order);

    try {
        inventory.reserve(order.getProductId(), order.getQuantity());
    } catch (InventoryException ex) {
        throw new OrderPlacementException(
                "Cannot create order",
                ex
        );
    }
}
~~~

If a participating transaction has already been marked rollback-only, the outer transaction may encounter `UnexpectedRollbackException` when attempting to commit. Never swallow an exception and assume the transaction can still safely commit.

## 8. readOnly, isolation, and timeout

`@Transactional` also provides attributes controlling how the transaction runs.

### 8.1. readOnly = true

Used for read-only use cases:

~~~java
@Transactional(readOnly = true)
public OrderDetails getOrderDetails(Long orderId) {
    // Read order and related data.
}
~~~

`readOnly = true` is a transaction hint/attribute for the transaction manager and underlying provider. Depending on the platform, it may enable optimizations or be checked by the database; do not treat this annotation as a security mechanism guaranteeing no write statement can execute.

If a method writes data, do not mark it read-only. If a read-only method joins an existing transaction with a different configuration, the existing transaction's policy usually determines actual behavior.

### 8.2. Isolation

Isolation determines how much a transaction sees concurrent changes from other transactions. It can be specified as:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateInventory(...) {
    // Read and update inventory.
}
~~~

Common isolation levels:

| Isolation | General meaning |
|---|---|
| READ_UNCOMMITTED | May read uncommitted data if supported by the database |
| READ_COMMITTED | Reads only committed data |
| REPEATABLE_READ | Re-reading the same rows within a transaction has higher stability |
| SERIALIZABLE | Requests the highest isolation according to database semantics |

Actual isolation behavior and prevented anomalies depend on the database. Do not raise isolation just to feel "safer"; higher levels can reduce concurrency, increase locking, or cause serialization failures.

When a method joins an existing transaction, a new isolation requirement may not apply as a new transaction. Set isolation at the outermost boundary of the use case and understand the transaction manager configuration.

### 8.3. timeout

You can set a time limit on a transaction:

~~~java
@Transactional(timeout = 10)
public void updateOrder(...) {
    // Use case with expected short execution time.
}
~~~

Timeout is specified in seconds in the annotation attribute. Support and enforcement depend on the transaction manager/driver/database. Transaction timeout does not replace timeouts for HTTP clients or external services.

## 9. Multiple Repositories Must Share the Same Transaction Manager

For repository operations to participate in the same transaction, they must use the same transaction manager and compatible resource, typically the same DataSource.

Example:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example.persistence"
)
public class JdbcConfiguration {
    // Application DataSource and transaction manager.
}
~~~

In Spring Boot, auto-configuration can create a transaction manager based on the DataSource. If the application declares multiple DataSources or multiple transaction managers, specify which manager the service uses:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void placeOrder(...) {
    // Repositories using the DataSource managed by this manager.
}
~~~

If two repositories use two different DataSources and two independent transaction managers, a single standard `@Transactional` does not automatically create a distributed transaction spanning both databases. When true cross-resource atomicity is required, design an appropriate solution such as XA/JTA if infrastructure supports it, or use a saga/outbox pattern with compensation.

Do not assume that injecting two repositories into the same service automatically makes them share a transaction.

## 10. Do Not Extend Transactions Across Non-Database Work

Database transactions should be short and focused on operations that must commit or roll back together.

Avoid keeping a transaction open while calling external APIs over HTTP, sending emails or notifications, waiting for user input, running heavy computations that do not need a connection held, or performing long-running file processing.

What to avoid:

~~~java
@Transactional
public void registerAndNotify(Customer customer) {
    customers.save(customer);
    emailClient.sendWelcomeEmail(customer); // Network call outside database.
}
~~~

If sending the email takes several seconds or times out, the database connection can remain held throughout that time. Emails also cannot roll back with a JDBC transaction: a database rollback cannot unsend a sent email.

A common design pattern is to write business data and an outbox record inside the same transaction:

~~~java
@Transactional
public Customer register(RegisterCustomerCommand command) {
    Customer saved = customers.save(Customer.create(command));

    outbox.save(OutboxMessage.welcomeEmailRequested(
            saved.getId(),
            saved.getEmail()
    ));

    return saved;
}
~~~

A separate worker reads the outbox after the transaction commits and sends the email. If sending fails, the worker can retry using an idempotent policy. Writing the outbox record in the same transaction ensures the event is never emitted if the main business operation rolls back.

If not using an outbox, you can publish an event after commit using an appropriate mechanism such as a transaction-bound event listener, though you still need to consider reliability if the process stops between commit and event dispatch.

## 11. Transactions Do Not Propagate Automatically to Other Threads

JDBC transactions in Spring's imperative model are typically bound to the current thread through the transaction manager. Do not assume a transaction automatically propagates to a new thread.

Example:

~~~java
@Transactional
public void process(Order order) {
    orders.save(order);

    CompletableFuture.runAsync(() -> {
        auditRepository.save(AuditRecord.forOrder(order));
    });
}
~~~

Work inside `CompletableFuture` may run on another thread and does not participate in the outer method's transaction. The outer method may commit before the async task even runs or finishes.

If async work needs data only after commit, emit an event/outbox entry and let the worker open its own transaction. If two operations must be atomic, run them synchronously within the same transaction or design an appropriate distributed protocol.

## 12. Testing Transaction Boundaries

Rollback behavior should be tested at the integration level against the database your application uses.

Example scenario:

1. Service saves an order.
2. Subsequent repository throws an exception.
3. Service lets the exception propagate or wraps it into a runtime exception.
4. Test verifies the order no longer exists in the database after rollback.

~~~java
@SpringBootTest
class OrderServiceTransactionTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orders;

    @Test
    void rollsBackOrderWhenInventoryReservationFails() {
        assertThatThrownBy(() ->
                orderService.placeOrder(commandThatCannotReserveStock())
        ).isInstanceOf(OrderPlacementException.class);

        assertThat(orders.findByExternalReference("REF-001"))
                .isEmpty();
    }
}
~~~

This is an illustrative example; fixtures, exceptions, and repository methods must match the real application.

### 12.1. Watch Out for Test Transactions

Some test slices such as `@DataJdbcTest` run each test inside a transaction and roll back when the test finishes. This is convenient for data isolation, but can obscure the service's actual commit behavior.

If you need to verify that a service transaction commits/rolls back independently, structure the test so the true transaction boundary is observable. Tests must invoke Spring-managed beans so transaction proxies apply, never directly instantiated objects.

Testing on H2 may not fully reflect locking, isolation, SQL dialect, or constraints of the production database. For database-dependent behavior, use Testcontainers or a test environment running the same engine.

## 13. Common Mistakes

| Symptom | Possible cause | Fix |
|---|---|---|
| First repository commits while second fails | No shared transaction on the service | Wrap the use case with `@Transactional` |
| Annotation has no effect | Service is not Spring-managed or caller bypasses proxy | Inject bean and invoke through Spring proxy |
| Self-invocation does not open a new transaction | Method calls another method on the same instance via `this` | Place annotation on entry method or extract a bean |
| Checked exception thrown but data still commits | Default rollback rule does not roll back checked exceptions | Use `rollbackFor` if required by business logic |
| Exception caught but data still commits | Exception swallowed and transaction not marked rollback-only | Rethrow exception or mark rollback-only |
| UnexpectedRollbackException at the end | Participating transaction was marked rollback-only | Find the root exception and fix propagation boundaries |
| REQUIRES_NEW exhausts connection pool | Outer transaction holds a connection while new transaction needs another | Use only when independent commit is needed; size pool carefully |
| Read-only transaction still executes writes | `readOnly` is a hint depending on transaction manager/database | Do not rely on it as authorization or write protection |
| Desired isolation has no effect | Method joined an already open transaction with different isolation | Set isolation on the outermost transaction boundary |
| Two repositories do not roll back together | They use different DataSources/transaction managers | Configure the right manager or design distributed workflow |
| Async work runs outside the transaction | New threads do not inherit JDBC transactions | Open a separate transaction or use outbox/events |
| Transaction holds connection too long | HTTP calls, emails, or slow work inside transaction | Narrow transaction and move side effects outside |
| Test passes but production rollback differs | Test framework wraps test in transaction or DB semantics differ | Run integration tests on target database |

## 14. Process for Choosing @Transactional Boundaries

1. Identify the business use case requested by the caller.
2. List the database operations that must commit or roll back together.
3. Place `@Transactional` on the public service method representing the use case.
4. Ensure participating repositories share the same transaction manager and DataSource.
5. Keep the transaction short; move HTTP calls, emails, and long work outside.
6. Use the default `REQUIRED` propagation unless there is a clear reason for different semantics.
7. Define rollback rules for checked and business exceptions.
8. Use `readOnly = true` for read-only use cases where appropriate.
9. Set custom isolation/timeout only when concurrency requirements and database behavior are understood.
10. Test commit/rollback with a Spring-managed service and an appropriate database.

## 15. Hands-On Exercises

### Exercise 1 — Two Repositories in One Use Case

Create a service that saves an `Order` and then updates `Inventory`. Force the second operation to throw an exception. Compare the database state with and without `@Transactional` on the service.

### Exercise 2 — Repository Transaction vs. Service Transaction

Call a single CRUD repository method standalone, then call two repository methods inside a service. Enable SQL/transaction logging to observe transaction boundaries.

### Exercise 3 — Checked Exceptions

Create a transactional method that saves an entity and then throws a checked exception. Inspect the data after the call. Add `rollbackFor` and compare.

### Exercise 4 — Self-Invocation

Create a service where an outer method calls another method in the same class annotated with `@Transactional`. Compare this with moving the method to another bean and calling through a proxy.

### Exercise 5 — Propagation

Try `REQUIRED` and `REQUIRES_NEW`. Force the outer transaction to roll back after the inner transaction completes. Observe which records remain and explain why.

### Exercise 6 — Read-Only and Isolation

Create a read use case with `readOnly = true`. Verify transaction behavior on the target database. Run two transactions updating the same row to observe isolation and locking.

### Exercise 7 — External Side Effects

Create a use case that saves an order and sends an email. Simulate the email succeeding while the database transaction rolls back. Then design an outbox to decouple email sending from the business transaction.

### Exercise 8 — Async and Thread Boundaries

Invoke an async task from a transactional service. Observe the transaction context on the new thread. Design a worker that opens its own transaction and processes only after the primary data commits.

## 16. Key Takeaways

- Transaction boundaries should reflect **a single business use case**, because the service coordinates operations that must succeed or roll back together.
- CRUD repository methods have default transaction behavior, but multiple independent repository calls do not automatically form a shared business transaction.
- With `Propagation.REQUIRED`, repository/service methods join the current transaction when sharing the same transaction manager and compatible resource.
- `@Transactional` is applied via Spring proxies in standard configurations; self-invocation and manual object instantiation bypass proxies.
- Rollback occurs by default on `RuntimeException` and `Error`; use `rollbackFor` for checked exceptions when required by business logic.
- Do not catch and swallow exceptions if the transaction needs to roll back.
- `REQUIRES_NEW` commits independently and can persist even if the outer transaction rolls back; use it intentionally.
- `readOnly` is a transaction hint, not a security guarantee that the database cannot write.
- Isolation and timeout should be based on actual concurrency, transaction manager, and database behavior.
- Multiple repositories only roll back together when they participate in the right transaction manager and DataSource; separate databases require a dedicated strategy.
- Do not hold JDBC transactions while calling external services or running long work; use an outbox/event pattern when emitting side effects after commit.
- Imperative transactions do not automatically propagate to async threads.

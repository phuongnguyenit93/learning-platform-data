# Multi-Repository Business Operations and Service-Layer Orchestration in Spring Data REST

## Objectives

After this lesson, you can recognize when a business operation needs to coordinate multiple repositories; organize that logic in an application/service layer; define transaction boundaries so data changes succeed or roll back together; and expose a business operation via Spring Data REST or a custom REST endpoint without letting controllers orchestrate persistence directly.

## 1. Why might a business operation need multiple repositories?

A repository typically focuses on accessing a single aggregate or group of entities. However, a real-world use case often has to read and update multiple types of data.

For example, creating an order may require:

- Finding the Customer and checking customer status.
- Finding the Products and checking prices or selling status.
- Checking and decrementing inventory stock.
- Creating the Order along with its OrderLines.
- Recording history or an audit event.

If a controller calls each repository individually to carry out these steps, business logic spreads across the HTTP layer. Another controller or a background job might have to duplicate the same rules, making behavior inconsistent and hard to test.

The application/service layer provides a single orchestration point for a use case. The service accepts input data, validates business rules, calls the required repositories, and defines the transaction boundary. The controller simply delegates the request to the service and turns the result into an HTTP response.

## 2. Dividing responsibilities across repository, service, and controller

Responsibilities can be divided as follows:

| Component | Primary responsibility |
| --- | --- |
| Repository | Query, save, and delete aggregate data; provide required queries |
| Domain model | Hold state and invariants belonging to the entity/aggregate |
| Application service | Orchestrate the use case, call multiple repositories, apply transactions, and coordinate domain operations |
| REST controller | Receive HTTP requests, validate input format, call the service, and build HTTP responses |
| Infrastructure integration | Communicate with message brokers, payment providers, email services, or external systems |

A repository should not become the orchestrator for an entire use case. For example, `OrderRepository` should not call `CustomerRepository`, `InventoryRepository`, and `PaymentGateway` to complete an order. The service understands the full business flow and invokes each collaborator in the proper order.

A service can use multiple repositories:

```java
@Service
public class OrderApplicationService {

    private final CustomerRepository customers;
    private final ProductRepository products;
    private final InventoryRepository inventory;
    private final OrderRepository orders;

    public OrderApplicationService(
            CustomerRepository customers,
            ProductRepository products,
            InventoryRepository inventory,
            OrderRepository orders) {
        this.customers = customers;
        this.products = products;
        this.inventory = inventory;
        this.orders = orders;
    }

    // Use case methods are implemented here
}
```

Constructor injection makes the service's repository dependencies explicit and simplifies replacing collaborators in unit tests.

## 3. Placing transaction boundaries at the service layer

When multiple repositories modify data within a single use case, the transaction boundary should generally reside on the orchestrating service method. When repositories share a single relational database and transaction manager, you can use `@Transactional`:

```java
@Service
public class OrderApplicationService {

    private final CustomerRepository customers;
    private final InventoryRepository inventory;
    private final OrderRepository orders;

    public OrderApplicationService(
            CustomerRepository customers,
            InventoryRepository inventory,
            OrderRepository orders) {
        this.customers = customers;
        this.inventory = inventory;
        this.orders = orders;
    }

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        Customer customer = customers.findById(command.customerId())
            .orElseThrow(() -> new CustomerNotFoundException(
                command.customerId()));

        customer.requireActive();

        inventory.reserve(
            command.productId(),
            command.quantity());

        Order order = Order.create(
            customer,
            command.productId(),
            command.quantity());

        return orders.save(order);
    }
}
```

In the example, `@Transactional` creates a transaction wrapping the service call. Repository operations participate in the active transaction if they use the same transaction manager. When the method finishes normally, the transaction commits. When an exception matching the rollback rules is thrown, the transaction rolls back so changes within that transaction are not partially persisted.

This is a key benefit of the service layer: the transaction describes the entire use case rather than wrapping each individual `save` call.

### Rollback and exception types

By Spring's default, `@Transactional` rolls back on unchecked exceptions (`RuntimeException` or `Error`); checked exceptions do not automatically trigger a rollback under default rules. If checked exceptions must also roll back, configure it explicitly:

```java
@Transactional(rollbackFor = Exception.class)
public Order createOrder(CreateOrderCommand command) throws Exception {
    // Steps of the use case
}
```

You can use `noRollbackFor` for special cases, but design carefully to avoid committing an incomplete business state. Use exceptions to represent meaningful errors and keep a consistent rollback policy at the service boundary.

One technical note: Spring typically applies transactions via proxies. Calling another `@Transactional` method on the same instance via self-invocation may bypass the proxy and fail to activate the transaction as expected. Place transactions on public service entry points invoked by other beans, or structure transactions appropriately for your application.

## 4. Example order creation use case with multiple repositories

Suppose the system has Customer, Product, Inventory, and Order. An order creation request contains customer ID, product ID, and quantity. The service must verify the customer, reserve stock, and save the order.

Input data can be separated into a command:

```java
public record CreateOrderCommand(
        Long customerId,
        Long productId,
        int quantity) {
}
```

Orchestrating service:

```java
@Service
public class OrderApplicationService {

    private final CustomerRepository customers;
    private final ProductRepository products;
    private final InventoryRepository inventory;
    private final OrderRepository orders;

    public OrderApplicationService(
            CustomerRepository customers,
            ProductRepository products,
            InventoryRepository inventory,
            OrderRepository orders) {
        this.customers = customers;
        this.products = products;
        this.inventory = inventory;
        this.orders = orders;
    }

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new InvalidOrderException(
                "Quantity must be greater than zero");
        }

        Customer customer = customers.findById(command.customerId())
            .orElseThrow(() -> new CustomerNotFoundException(
                command.customerId()));

        Product product = products.findById(command.productId())
            .orElseThrow(() -> new ProductNotFoundException(
                command.productId()));

        customer.requireActive();
        product.requireSellable();

        inventory.reserve(product.getId(), command.quantity());

        Order order = Order.create(
            customer,
            product,
            command.quantity(),
            product.getCurrentPrice());

        return orders.save(order);
    }
}
```

The example omits constructors and persistence details to highlight the flow. The price is captured onto the Order at creation time so order history does not change when Product pricing is later updated.

If `inventory.reserve(...)` throws an exception due to insufficient stock, the transaction can roll back the inventory change and avoid saving the Order. This holds true only when the inventory operation and the Order actually share the same transaction manager and transaction resource. If they reside in different databases or services, a separate distributed consistency strategy is needed.

## 5. Do not let controllers orchestrate multiple repositories directly

Spring Data REST automatically generates endpoints for exported repositories. This works well for simple CRUD operations. However, if creating a resource requires multiple business steps, calling the repository endpoint directly may not express the full use case.

You can create a custom REST endpoint that invokes the application service:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderCommandController {

    private final OrderApplicationService orderService;

    public OrderCommandController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        Order order = orderService.createOrder(
            new CreateOrderCommand(
                request.customerId(),
                request.productId(),
                request.quantity()));

        URI location = URI.create("/api/orders/" + order.getId());

        return ResponseEntity.created(location)
            .body(OrderResponse.from(order));
    }
}
```

The controller receives an input DTO, calls a single use-case method, and returns a response. It does not call multiple repositories directly, decide persistence ordering, or manage commit/rollback itself.

In a Spring Data REST application, you can use `@BasePathAwareController` if you want a custom controller to operate under the Spring Data REST base path. If you use a regular `@RestController`, design mappings and base paths carefully to avoid route conflicts with repository resources. Choose a dedicated command URL, such as `/api/orders/commands`, or `/api/orders` if the repository collection endpoint does not occupy the same route.

## 6. Repository endpoints and application service endpoints can coexist

Spring Data REST remains useful for simple CRUD and resource navigation. An application can expose:

- Repository resources to read Order lists, view items, and perform permitted CRUD operations.
- Custom command endpoints to create orders, cancel orders, or confirm payments.
- A shared service layer for HTTP controllers, scheduled jobs, or message consumers.

Crucially, every entry point performing the same business operation should go through the same application service. If a custom controller creates an Order via the service while another repository endpoint permits direct Order writes, clients can bypass inventory checks or business rules. Restrict repository methods and REST exposure so there is no write path that bypasses the use case.

You can hide repository write operations using appropriate Spring Data REST configuration, such as `@RestResource(exported = false)` on a method or `@RepositoryRestResource(exported = false)` on a repository when needed. Hiding endpoints must go hand in hand with API design and authorization; it does not replace service validation.

## 7. Do multiple repositories really share the same transaction?

`@Transactional` does not automatically turn independent storage systems into a single atomic transaction. You must determine:

- Do the repositories use the same database or different databases?
- Do they share the same transaction manager or does each datasource have its own transaction manager?
- Are JPA and JDBC used on the same datasource with compatible transaction integration?
- Are there HTTP calls, emails, or message publications inside the transaction?

With multiple repositories on the same database and transaction manager, Spring can usually coordinate them in one transaction. With multiple datasources, each transaction manager manages its own resource. A local transaction does not automatically roll back a transaction already committed on another database.

If a use case must update two independent databases, consider XA/JTA where the environment supports it and strict atomicity is genuinely appropriate. Many modern systems prefer eventual consistency using an outbox, saga, or compensating workflow instead of synchronous distributed transactions.

## 8. Handling external side effects with Outbox or Saga

Sending emails, calling payment providers, or publishing messages to a broker are side effects outside the database transaction. If an external system is called mid-transaction and the database rolls back, the external system may have already acted without a database record. Conversely, if the database commits and message publishing fails, the systems fall out of sync.

A common approach is the **Transactional Outbox**:

1. Within the same database transaction, save the Order and an OutboxEvent.
2. Commit both together.
3. A background publisher reads unsent outbox records and publishes messages.
4. Mark messages as sent or retry according to policy.
5. Consumers process idempotently so redelivering a message causes no duplicate effects.

Example service writing an outbox record:

```java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = createAndSaveOrder(command);

    outboxRepository.save(
        OutboxEvent.orderCreated(order.getId()));

    return order;
}
```

Outbox ensures the Order and the intent to emit an event are saved in the same transaction. It does not guarantee exactly-once delivery; publishers/consumers still need retries, deduplication, and idempotency.

**Saga** fits long-running workflows spanning multiple steps across independent services or databases. Each step commits locally and emits an event/command for the next step. If a step fails, the saga executes designed compensating actions, such as releasing reserved stock or issuing a refund. A compensating action is separate business logic rather than an ACID database rollback.

## 9. Concurrency: preventing two requests from consuming the same resource

Transactions protect atomicity, but they do not automatically prevent every race condition. For example, two requests read stock as 1, both see enough inventory, and both create an Order. Reading and decrementing via a setter can cause overselling.

Several solutions:

- Use optimistic locking with `@Version` to detect concurrent updates and retry or return conflict per business rules.
- Use pessimistic locking for operations needing a lock on stock during a transaction, such as a query with `@Lock(LockModeType.PESSIMISTIC_WRITE)`.
- Use a conditional update statement such as `UPDATE inventory SET quantity = quantity - :n WHERE product_id = :id AND quantity >= :n`, then check the updated row count.
- Use unique constraints or database constraints for invariants that must be enforced at the storage layer.

Optimistic locking example:

```java
@Entity
public class InventoryItem {

    @Id
    private Long productId;

    private int availableQuantity;

    @Version
    private long version;

    public void reserve(int quantity) {
        if (quantity <= 0 || availableQuantity < quantity) {
            throw new InsufficientStockException();
        }
        availableQuantity -= quantity;
    }
}
```

When two transactions update the same version concurrently, one transaction can receive an optimistic locking failure. The application must decide whether to retry or return a conflict to the client. Do not retry infinitely; only retry transient errors and keep commands idempotent whenever possible.

## 10. Combining orchestration with auditing

When a service orchestrates multiple repositories, audit metadata must accurately reflect the user and timestamp of the use case. Spring Data auditing can automatically populate `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate` for entities configured for auditing.

Example:

```java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Order {

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
```

Enable auditing:

```java
@Configuration
@EnableJpaAuditing
class JpaAuditingConfiguration {
}
```

Provide an `AuditorAware` so Spring knows the current user:

```java
@Bean
AuditorAware<String> auditorAware() {
    return () -> Optional.ofNullable(
        SecurityContextHolder.getContext().getAuthentication())
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
```

The example above must handle anonymous/system users according to application policy. For background jobs or message consumers, an HTTP security context may not exist; supply a dedicated auditor such as `system` or the service name so audit records still have a clear source.

Entity auditing automatically populates metadata when the relevant persistence lifecycle runs. If you need to audit a composite business operation such as “which channel created the order” or “who approved the entire order”, you can also record a domain event or audit record in the same use case. Do not rely solely on `@LastModifiedBy` as a substitute for business history.

## 11. Testing a service that orchestrates multiple repositories

The service layer can be tested independently with unit tests using mock repositories, focusing on business decisions:

- Customer does not exist: do not create Order.
- Customer is inactive: reject the use case.
- Product is not sellable: do not reserve inventory.
- Insufficient stock: do not save Order.
- All conditions valid: reserve inventory and save Order with the price at order time.
- Error saving Order: transaction integration test verifies inventory change rolls back.
- Current auditor: entity records the expected creator/modifier.

Mock unit tests verify order and interactions, but they do not prove a transaction actually rolls back. For rollbacks, optimistic locking, database constraints, and JPA auditing, integration tests running with a Spring context and an appropriate database are required.

For example, rollback verification should run in a separate test transaction or invoke the service through a Spring proxy. Avoid calling internal methods directly on a manually constructed test object and concluding that `@Transactional` works.

## 12. Common design mistakes

**Controller calling multiple repositories directly**

Use-case logic becomes scattered, hard to reuse, and hard to test. Move orchestration into an application service.

**Each repository opening its own transaction**

Steps can commit independently, resulting in partially saved data. Place the transaction boundary at the service entry point for use cases requiring atomicity.

**Assuming all repositories belong to the same transaction**

Verify the datasources and transaction managers. Multiple databases or external systems require a distributed consistency strategy.

**Calling payment/email/message brokers inside a transaction and assuming atomicity**

Database rollback cannot undo side effects that already occurred in external systems. Use outbox, saga, or appropriate compensating mechanisms.

**Repository REST allowing writes that bypass the service**

Restrict REST exposure or move sensitive writes to command endpoints that call the service. Ensure authorization is enforced on every write path.

**Using transactions instead of concurrency control**

Transactions do not automatically prevent all lost updates or overselling. Use optimistic/pessimistic locking or atomic conditional updates for protected invariants.

**Auditing relying solely on HTTP users**

Background jobs and message consumers lack an HTTP security context. Define an auditor for each execution context.

## Summary

- Repositories focus on persistence; application services orchestrate multi-repository use cases; controllers handle only the HTTP protocol.
- Place `@Transactional` at the service boundary so repositories sharing a transaction manager commit or roll back together.
- Spring rolls back on unchecked exceptions by default; configure `rollbackFor` when checked exceptions must also roll back.
- Multiple datasources or external systems do not automatically form one ACID transaction; consider outbox, saga, or compensation.
- Use optimistic/pessimistic locking or atomic updates to protect data under concurrency.
- Use Spring Data auditing and `AuditorAware` to record creator/modifier metadata; add audit events for business history.
- Restrict repository REST write exposure when operations must go through an application service; verify transactions with integration tests.

## References

- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data REST — Repository events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Jakarta Persistence — Locking and version attributes](https://jakarta.ee/specifications/persistence/)

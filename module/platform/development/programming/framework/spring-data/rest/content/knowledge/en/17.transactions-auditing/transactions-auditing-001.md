# Repository Transaction Boundaries and the REST Exporter Call Flow

## Objectives

After this lesson, you can:

- Understand how Spring Data REST maps an HTTP request to a repository call.
- Identify whether a transaction is opened at a repository method or a service method.
- Distinguish a single repository call's transaction from the transaction of an entire use case.
- Configure transactions for CRUD methods and query methods.
- Use a `@Transactional` service to coordinate multiple repositories in a single unit of work.
- Understand the role of repository events, auditing, and transaction-bound events.
- Inspect commits, rollbacks, and audit data in a REST flow.

## 1. What are the roles of the REST exporter and the repository?

Spring Data REST exposes repositories as HTTP resources. When a client calls an endpoint, the REST exporter translates the request into the appropriate repository operation. For example, with a repository managing `Order`:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

Common operations are mapped as follows:

| HTTP request | Repository operation typically invoked |
|---|---|
| GET /api/orders | findAll(Pageable), findAll(Sort), or findAll() |
| GET /api/orders/42 | findById(42) |
| POST /api/orders | save(new order) |
| PUT /api/orders/42 | save(order bound from request) |
| PATCH /api/orders/42 | save(order after applying changes) |
| DELETE /api/orders/42 | corresponding delete(...) |

The REST exporter also publishes repository lifecycle events such as BeforeCreate, AfterCreate, BeforeSave, AfterSave, BeforeDelete, and AfterDelete. These events allow the application to validate entities, enrich data, or react to operations performed through the REST API.

Key point: the REST exporter is the HTTP and representation orchestration layer. Data transactions are determined by the transaction manager together with the actual repository/service calls. Do not assume that every HTTP request automatically becomes a single transaction spanning every step of the exporter, event handlers, and other repositories.

## 2. Default transactions of a Spring Data JPA repository

CRUD methods inherited from CrudRepository typically receive transaction configuration from SimpleJpaRepository:

- Read operations are configured with **readOnly = true**.
- Write operations are configured with regular **@Transactional**.
- Repository fragments with their own transaction attributes use the configuration of the corresponding fragment method.

Example:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

Inherited methods such as findById, findAll, save, and delete already have transaction attributes according to the Spring Data JPA implementation. When the REST exporter calls the repository proxy, the transaction interceptor applies the configuration of the invoked method.

**readOnly = true** is a hint to the transaction manager, JDBC driver, and persistence provider to optimize read operations. It is not an authorization mechanism and not an absolute check that blocks every write statement.

If you need to change the configuration of a CRUD method, you can redeclare the method in the repository:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Override
    @Transactional(timeout = 10)
    List<Order> findAll();
}
~~~

The findAll method in the example is configured with a 10-second timeout and no longer has readOnly=true according to the new declaration.

## 3. Query methods do not have a transaction by default

An easily overlooked point is that query methods declared by the application do not automatically inherit transaction attributes just because the repository extends JpaRepository.

Example:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);
}
~~~

If a query method needs to run inside a transaction, declare it explicitly:

~~~java
@Transactional(readOnly = true)
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    @Modifying
    @Transactional
    @Query("delete from Order o where o.status = :status")
    int deleteByStatus(@Param("status") OrderStatus status);
}
~~~

In the example:

- Read query methods participate in a read-only transaction.
- The delete method is marked with @Modifying and has @Transactional for writing data.
- Method-level configuration overrides interface-level configuration.

Check the actual method type and transaction attributes. Do not assume that every method on a repository automatically runs under the same transaction behavior.

## 4. A repository call is different from a use case

Suppose that when creating an order, the system needs to:

1. Save the Order.
2. Reduce stock in Inventory.
3. Write an audit record.
4. Save payment history.

If the REST exporter only calls OrderRepository.save(), the default transaction of the save method does not automatically span the operations in the other three repositories. If each repository call opens its own transaction, one step may commit while another fails.

Risk example:

~~~java
orderRepository.save(order);
inventoryRepository.reserve(order.getProductId(), order.getQuantity());
auditRepository.save(auditEntry);
~~~

If the reserve step fails after the Order has already committed, the database can be left in an inconsistent state.

For a use case that requires atomicity, place the transaction at the service/facade that orchestrates all operations:

~~~java
@Service
public class OrderWorkflowService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;
    private final AuditRepository auditRepository;

    public OrderWorkflowService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Order createOrder(Order order) {
        Order saved = orderRepository.save(order);

        inventoryRepository.reserve(
            saved.getProductId(),
            saved.getQuantity()
        );

        auditRepository.save(
            AuditEntry.orderCreated(saved.getId())
        );

        return saved;
    }
}
~~~

The transaction of createOrder spans the repository calls inside it if they share the same transaction manager and use the default propagation. If an operation throws an exception that triggers a transaction rollback, the database changes within the same transaction are rolled back together.

## 5. The REST exporter does not automatically call orchestration services

Default Spring Data REST repository resources invoke the exposed repository methods. Creating a `@Transactional` service does not automatically route POST /api/orders through that service.

If the order creation use case requires multiple steps, you can provide a custom endpoint using @RepositoryRestController or an appropriate controller to call the service:

~~~java
@RepositoryRestController
public class OrderWorkflowController {

    private final OrderWorkflowService workflowService;

    public OrderWorkflowController(OrderWorkflowService workflowService) {
        this.workflowService = workflowService;
    }

    @PostMapping(
        path = "/orders/checkout",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_HAL_JSON_VALUE
    )
    public ResponseEntity<?> checkout(@RequestBody Order order) {
        Order saved = workflowService.createOrder(order);
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }
}
~~~

This is a structural example; actual responses should use a representation/assembler appropriate for your application's API. @RepositoryRestController allows the controller to use the Spring Data REST base path and infrastructure. The transaction boundary still resides in the invoked service.

Another option is to keep simple repository endpoints for CRUD and build dedicated business endpoints for operations that coordinate multiple aggregates/repositories. Place the transaction at the boundary of the use case that the application needs to keep atomic.

## 6. Propagation: repository calls join an existing transaction

The default propagation of @Transactional is **REQUIRED**:

- If a transaction already exists, the method joins the existing transaction.
- If no transaction exists, the method creates a new transaction.

Example:

~~~java
@Service
public class OrderWorkflowService {

    private final OrderRepository orderRepository;
    private final PaymentRepository paymentRepository;

    public OrderWorkflowService(
            OrderRepository orderRepository,
            PaymentRepository paymentRepository) {
        this.orderRepository = orderRepository;
        this.paymentRepository = paymentRepository;
    }

    @Transactional
    public void confirmOrder(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.confirm();
        orderRepository.save(order);

        paymentRepository.markReady(orderId);
    }
}
~~~

Repository methods called from confirmOrder join the service's transaction if they use the same transaction manager and compatible propagation.

This is how a clear unit of work is defined. The transaction attribute on the outer service determines the actual transaction that the inner repository calls participate in.

## 7. Rollback and exceptions

A transaction only guarantees rollback according to the rules of the transaction manager. Under default Spring configuration, RuntimeException and Error trigger a transaction rollback. Checked exceptions do not trigger a rollback by default.

Example when business logic can throw a checked exception and must roll back:

~~~java
@Transactional(rollbackFor = Exception.class)
public void createOrder(Order order) throws Exception {
    orderRepository.save(order);
    inventoryRepository.reserve(order.getProductId(), order.getQuantity());

    if (someBusinessConditionFailed()) {
        throw new Exception("Unable to complete the order");
    }
}
~~~

If an exception is caught and not rethrown, the transaction interceptor may not know that the use case failed. When a rollback is required even after handling an exception, explicitly mark the transaction as rollback-only or throw an appropriate exception.

Do not catch every exception and return a success result. Doing so can cause the transaction to commit partial changes that the business logic does not intend.

## 8. Repository events are not transaction boundaries

Spring Data REST publishes events such as:

- BeforeCreate / AfterCreate.
- BeforeSave / AfterSave.
- BeforeLinkSave / AfterLinkSave.
- BeforeDelete / AfterDelete.

They can be handled using ApplicationListener/AbstractRepositoryEventListener or a handler annotated with @RepositoryEventHandler and annotations such as @HandleBeforeSave.

Example:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderEventHandler {

    @HandleBeforeSave
    public void beforeSave(Order order) {
        order.normalizeReference();
    }

    @HandleAfterSave
    public void afterSave(Order order) {
        // React to the REST exporter lifecycle event.
    }
}
~~~

These events describe the operation lifecycle of the REST exporter. They do not create a new transaction, do not replace @Transactional, and do not mean that a transaction has committed.

Spring Data REST events are Spring application events and are published synchronously by default. Synchronous only means the listener is typically invoked on the publishing thread; it does not by itself prove that a database transaction is active at the time the listener runs.

Therefore:

- Use BeforeSave to validate or normalize an entity before the exporter's save operation.
- Use AfterSave to react to a save event in the REST exporter lifecycle.
- Do not assume an event handler always runs inside the same transaction as every repository call.
- If a handler requires multiple repository calls to be atomic, move the orchestration into a `@Transactional` service.
- If you need to react only after a successful commit, use a transaction-bound event mechanism with an event published inside an active transaction.

## 9. Use @TransactionalEventListener when you need the commit outcome

Spring Framework supports @TransactionalEventListener to bind a listener to a transaction phase:

| Phase | Timing |
|---|---|
| BEFORE_COMMIT | Before the transaction commits |
| AFTER_COMMIT | After a successful commit; this is the default |
| AFTER_ROLLBACK | After a rollback |
| AFTER_COMPLETION | After the transaction completes, whether committed or rolled back |

Example:

~~~java
public record OrderCreatedEvent(Long orderId) {
}
~~~

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher events;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher events) {
        this.orderRepository = orderRepository;
        this.events = events;
    }

    @Transactional
    public Order create(Order order) {
        Order saved = orderRepository.save(order);
        events.publishEvent(new OrderCreatedEvent(saved.getId()));
        return saved;
    }
}
~~~

Listener that only runs after commit:

~~~java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        // Send notification after the Order creation transaction commits successfully.
    }
}
~~~

In the example, the event is published inside the service's transaction. The AFTER_COMMIT listener runs only after that transaction commits successfully. If the transaction rolls back, the listener does not run.

If no transaction is active when the event is published, @TransactionalEventListener is not invoked by default. The fallbackExecution attribute can change this behavior, but you should not enable it if the business logic requires knowing for certain that the transaction committed.

Do not treat a Spring Data REST AfterSaveEvent as proof that a transaction has committed. If clear commit semantics are needed, publish a domain event from a service inside a transaction and verify the right transaction manager.

## 10. Write audits in the same transaction or after commit?

There are two common types of auditing:

**Entity auditing metadata** records who created/modified a record and when it was created/modified. Spring Data supports:

- @CreatedBy
- @LastModifiedBy
- @CreatedDate
- @LastModifiedDate

Entity example:

~~~java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    private String orderNumber;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
~~~

Enable auditing:

~~~java
@Configuration
@EnableJpaAuditing
public class JpaAuditConfiguration {
}
~~~

If you need to record usernames via @CreatedBy or @LastModifiedBy, provide an AuditorAware to obtain the current principal. If you only record timestamps, AuditorAware is not required.

**A dedicated audit log** is a business history record—for example, who changed the order status, and what the old and new values were. If the audit row must exist if and only if the Order commits, write the audit row in the same service transaction. Both changes then commit together or roll back together if they use the same database and transaction manager.

If you only need to send an email, call a webhook, or publish a message after commit, do so after the transaction succeeds. For external integrations requiring high reliability, consider the transactional outbox: write an event/outbox row in the same business transaction and have a worker deliver it to the external system. This avoids the case where the database commits but the application crashes before sending the message.

If an AFTER_COMMIT listener needs to write additional data to the database, design a separate transaction for that operation, usually via a service with REQUIRES_NEW propagation. The original transaction has already completed; do not rely on a listener to silently keep writing within a committed transaction.

## 11. What can a single transaction cover?

| Component | Automatically inside the repository save transaction? |
|---|---|
| Persistence statements inside save | Yes, according to the repository method's transaction attribute |
| Another repository call from a `@Transactional` service with the same transaction manager | Can join the existing transaction |
| Independent repository call from an event handler without an outer transaction | Typically has its own transaction per invoked method |
| Sending an email or making an HTTP request to an external system | Not automatically rolled back by a database transaction |
| Writing to another database using a different transaction manager | Not automatically atomic with the current transaction |
| Event listener running asynchronously on another thread | Does not inherit the thread-bound transaction by default |

A regular transaction only protects resources managed by its transaction manager. A database transaction cannot automatically roll back an email that was already sent or an HTTP request already processed by another system.

If a use case updates multiple databases or multiple external systems, choose an appropriate architecture such as outbox, saga, or distributed transactions when the infrastructure truly supports it. Do not put @Transactional on a method and assume every involved system becomes a single atomic transaction.

## 12. Inspecting transactions in a REST flow

When inspecting a Spring Data REST endpoint, identify:

1. Which repository method is the HTTP method calling?
2. Does that method inherit CRUD transaction attributes or is it a custom-declared query method?
3. Is there an outer service/facade with @Transactional?
4. Do the repositories share the same transaction manager and compatible propagation?
5. Are event handlers invoked synchronously or dispatched to another thread?
6. Are audit rows written before commit, after commit, or via an outbox?
7. Which exceptions cause the transaction to roll back?

You can enable transaction logging in development environments to trace begin, commit, rollback, and transaction participation. With Spring Boot, you can configure log levels for the transaction interceptor and transaction manager according to your Spring version.

Illustrative log configuration example:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.orm.jpa.JpaTransactionManager=DEBUG
~~~

Logger names and log levels may vary by Spring version, transaction manager, and persistence technology. Combine application logs with SQL logs and inspect database state to confirm the final outcome.

## 13. Common mistakes

### Assuming every HTTP request is always a single transaction

The REST exporter invokes repository methods, but you should not assume every step of the request and every event handler run inside one overarching transaction. Determine the actual transaction boundary from the service/repository proxy.

### Query methods running without a transaction

Custom-declared finder methods do not have transaction attributes by default. Apply @Transactional at the appropriate repository or service level.

### Multiple repository calls committing individually

If the business logic requires all changes to succeed or fail together, place the transaction on an orchestrating service instead of relying on each repository method's individual transaction.

### Mistaking AfterSave for AFTER_COMMIT

AfterSave is a REST exporter lifecycle event. It is not a transaction phase. Use @TransactionalEventListener with a domain event published inside a transaction when post-commit handling is needed.

### Audit log out of sync with business data

If an audit row must be atomic with the entity, write it in the same transaction. If sending messages externally, use after-commit or an outbox depending on the required reliability.

### Catching exceptions so the transaction still commits

If an exception is swallowed and the transaction is not marked rollback-only, the transaction may commit. Check rollback rules and exception handling.

### Using multiple transaction managers while expecting atomicity

@Transaction only controls the selected transaction manager. Two databases or two external systems do not automatically form a single shared transaction.

### Calling a transactional method via self-invocation

In standard proxy-based configuration, a method in the same class calling another @Transactional method directly may bypass the proxy. Place the transaction boundary on a public service method invoked through a Spring bean proxy, or use an appropriate configuration.

## 14. Key takeaways

- Spring Data REST translates HTTP requests into repository method calls; transactions are determined by the repository/service and transaction manager.
- CRUD methods inherited from SimpleJpaRepository have default transaction attributes; read operations are typically read-only and write operations have @Transactional.
- Custom-declared query methods do not have transactions by default.
- A single repository call does not mean a multi-repository use case is wrapped in the same transaction.
- Use a `@Transactional` service/facade to coordinate multiple repositories in one unit of work.
- Repository events describe the REST exporter lifecycle; they do not replace transaction boundaries or commit phases.
- Use @TransactionalEventListener when an event is published in an active transaction and the listener needs to react to commit/rollback.
- Record audit metadata with Spring Data Auditing; write business audit logs in the same transaction when atomicity is required.
- External side effects need after-commit, an outbox, or an appropriate integration architecture.
- Check rollback rules, propagation, transaction managers, and thread boundaries when debugging.

## References

- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)

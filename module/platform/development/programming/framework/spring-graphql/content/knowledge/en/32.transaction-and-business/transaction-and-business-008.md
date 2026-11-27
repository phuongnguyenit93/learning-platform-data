# Exceptions and Rollback in Spring for GraphQL

In Spring for GraphQL, a GraphQL error and a database rollback are two separate things. GraphQL decides whether the response contains `data`, `errors`, or partial data; Spring transaction management decides whether database changes inside a transaction commit or roll back. A mutation can return a GraphQL error while data has still committed if an exception was caught before the transaction interceptor saw it. Conversely, a transaction can roll back even though the GraphQL framework subsequently converts the exception into a normal error response.

To handle this properly, place transaction boundaries around business use cases, understand `@Transactional` rollback rules, and allow exceptions to pass through the transaction interceptor before mapping them to GraphQL errors. For mutations requiring multiple operations to succeed or fail together, orchestrate those operations in a single service method with a clear transaction.

## 1. A GraphQL Error Does Not Automatically Mean a Rollback

A GraphQL response can contain both data and errors:

~~~json
{
    "data": {
        "createOrder": {
            "id": "order-101",
            "status": "PENDING",
            "payment": null
        }
    },
    "errors": [
        {
            "message": "Payment provider is unavailable",
            "path": ["createOrder", "payment"]
        }
    ]
}
~~~

The response above only indicates that a field failed during GraphQL execution. It does not indicate whether the order creation committed or rolled back. If `createOrder` ended its transaction and committed before the `payment` field was resolved, a failure in `payment` cannot automatically roll back the already-completed transaction.

Distinguish the two layers:

| Layer | Question | Decision Mechanism |
| --- | --- | --- |
| GraphQL execution | Which fields succeeded, which failed, and does the response have partial data? | GraphQL execution engine and exception resolvers |
| Database transaction | Do data writes commit or roll back? | Spring transaction manager and rollback rules |

Never infer database state solely from HTTP status or the presence of `errors`. GraphQL often returns HTTP `200` alongside `errors`; that reveals nothing about whether the transaction committed or rolled back.

## 2. Transaction Boundaries Belong Around Business Use Cases

A typical mutation flow looks like:

~~~mermaid
flowchart TD
    A[GraphQL Mutation request] --> B[Mutation resolver]
    B --> C[Transactional application service]
    C --> D[Repository and domain services]
    D --> E{Does an exception escape the transaction?}
    E -->|No| F[Commit]
    E -->|Yes and rollback rule matches| G[Rollback]
    E -->|Yes without rollback rule| F
    F --> H[Return result to GraphQL]
    G --> I[Exception resolver maps GraphQL error]
    F --> J[GraphQL continues resolving response fields]
    I --> K[GraphQL response]
    J --> K
~~~

`@Transactional` creates a transaction around a method invocation passing through a Spring proxy. When the method finishes normally, the transaction commits. When an exception escapes the method, the transaction interceptor compares the exception against rollback rules to decide whether to roll back or commit.

Therefore, transaction boundaries should wrap a complete business operation, typically at the application service. The resolver only binds GraphQL arguments, extracts necessary principal/context details, calls the service, and returns the result.

## 3. Declaring the Mutation and Application Service

Consider an order-creation use case that must save an order and reserve inventory. Both operations must succeed or fail together.

SDL:

~~~graphql
type Mutation {
    createOrder(input: CreateOrderInput!): Order!
}

input CreateOrderInput {
    productId: ID!
    quantity: Int!
}

type Order {
    id: ID!
    productId: ID!
    quantity: Int!
    status: OrderStatus!
}

enum OrderStatus {
    PENDING
    CONFIRMED
    CANCELLED
}
~~~

Commands and business exceptions:

~~~java
public record CreateOrderInput(String productId, Integer quantity) {}

public record CreateOrderCommand(
        Long productId,
        int quantity,
        String customerId
) {}
~~~

~~~java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(Long orderId) {
        super("Order " + orderId + " was not found");
    }
}
~~~

~~~java
public class InsufficientInventoryException extends RuntimeException {
    public InsufficientInventoryException(Long productId) {
        super("Insufficient inventory for product " + productId);
    }
}
~~~

Example repository reserving stock via a conditional update statement:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository extends JpaRepository<Inventory, Long> {

    @Modifying
    @Query("""
            update Inventory i
               set i.availableQuantity = i.availableQuantity - :quantity
             where i.productId = :productId
               and i.availableQuantity >= :quantity
            """)
    int reserveIfAvailable(
            @Param("productId") Long productId,
            @Param("quantity") int quantity
    );
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserve(Long productId, int quantity) {
        int updated = inventoryRepository.reserveIfAvailable(productId, quantity);
        if (updated == 0) {
            throw new InsufficientInventoryException(productId);
        }
    }
}
~~~

Placing `availableQuantity >= quantity` directly inside the update statement prevents a check-then-act pattern where two concurrent requests read the same stale stock quantity. This method joins the active transaction via `REQUIRED` propagation.

Business-orchestrating service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    public OrderApplicationService(
            OrderRepository orderRepository,
            InventoryService inventoryService
    ) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        if (command.quantity() < 1) {
            throw new InvalidOrderException("quantity must be positive");
        }

        Order order = orderRepository.save(Order.pending(
                command.customerId(),
                command.productId(),
                command.quantity()
        ));

        inventoryService.reserve(command.productId(), command.quantity());

        return order;
    }
}
~~~

If `inventoryService.reserve(...)` throws `InsufficientInventoryException`, the exception escapes `createOrder`. Because it is a `RuntimeException`, the transaction rolls back by default; both the order insert and inventory update in the same transaction are undone.

For two repositories/services to share the same transaction, they must use the same transaction manager and transactional resource (such as the same `DataSource`/JPA `EntityManagerFactory`). With default `REQUIRED` propagation, a transactional method invoked inside an existing transaction joins that transaction.

Resolver:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMutationController {

    private final OrderApplicationService orderService;
    private final CurrentCustomerProvider customerProvider;

    public OrderMutationController(
            OrderApplicationService orderService,
            CurrentCustomerProvider customerProvider
    ) {
        this.orderService = orderService;
        this.customerProvider = customerProvider;
    }

    @MutationMapping
    public Order createOrder(@Argument CreateOrderInput input) {
        Long productId;
        try {
            productId = Long.valueOf(input.productId());
        }
        catch (NumberFormatException exception) {
            throw new InvalidOrderException("productId must be a numeric identifier");
        }

        CreateOrderCommand command = new CreateOrderCommand(
                productId,
                input.quantity(),
                customerProvider.currentCustomerId()
        );
        return orderService.createOrder(command);
    }
}
~~~

The customer ID comes from the server-side principal rather than client input when business rules require customers to create orders only for themselves. GraphQL `ID` binds as `String`, and the resolver converts it to the domain's `Long` identifier.

## 4. Default Rollback Rules of @Transactional

Under default Spring transaction configuration, a transaction rolls back when a method terminates with:

- `RuntimeException` or a subclass.
- `Error` or a subclass.

Checked exceptions (such as `IOException`) do not trigger rollback by default. If a checked exception represents a business failure requiring database rollback, you must declare `rollbackFor`.

| Method Termination | Default | Common Configuration |
| --- | --- | --- |
| `RuntimeException` escapes method | Rollback | No extra rule needed |
| `Error` escapes method | Rollback | No extra rule needed |
| Checked exception escapes method | Commit by default | `rollbackFor = ...` if rollback is required |
| Method returns normally | Commit | Mark rollback-only if business logic must cancel |
| Exception caught and not rethrown | Commit by default | Rethrow the exception or mark rollback-only |

Checked exception example:

~~~java
public class CreditCheckException extends Exception {
    public CreditCheckException(String message) {
        super(message);
    }
}
~~~

~~~java
@Transactional(rollbackFor = CreditCheckException.class)
public Order approveOrder(Long orderId) throws CreditCheckException {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.markApproved();
    creditService.verify(order.getCustomerId());
    return order;
}
~~~

If `creditService.verify(...)` throws `CreditCheckException`, the transaction rolls back because the `rollbackFor` rule matches the exception.

Avoid adding `rollbackFor = Exception.class` out of habit to every method. Identify which exceptions represent failures requiring rollback; some checked exceptions may represent handled outcomes where committing is still valid.

## 5. rollbackFor and noRollbackFor

`rollbackFor` adds rollback rules for specific exceptions. `noRollbackFor` specifies exceptions that should not roll back the transaction even if they are unchecked.

~~~java
@Transactional(rollbackFor = CreditCheckException.class)
public Order submitOrder(CreateOrderCommand command)
        throws CreditCheckException {
    // Persist order, reserve stock and perform credit check.
    return doSubmit(command);
}
~~~

Example of not rolling back on a warning-style exception:

~~~java
@Transactional(noRollbackFor = DuplicateNotificationException.class)
public Notification recordNotification(NotificationCommand command) {
    Notification notification = notificationRepository.save(
            Notification.pending(command)
    );
    notificationPolicy.checkDuplicate(command);
    return notification;
}
~~~

Use `noRollbackFor` only when committing despite the exception is an intentional business requirement. If the exception indicates the primary operation failed, skipping rollback can leave partial state behind.

When an exception listed in `noRollbackFor` escapes the service, GraphQL may still catch the exception and return `errors` while the database transaction has committed. This clearly illustrates why a GraphQL error does not prove a transaction rolled back.

When multiple rules match, Spring chooses the rule most specific to the actual exception. Avoid declaring broad conflicting rules such as `rollbackFor = Exception.class` alongside `noRollbackFor = RuntimeException.class` without a clear reason.

## 6. Catching Exceptions Can Cause the Transaction to Commit

This is a common mistake:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.pending(command));

    try {
        int updated = inventoryRepository.reserveIfAvailable(
                command.productId(), command.quantity());
        if (updated == 0) {
            throw new InsufficientInventoryException(command.productId());
        }
    }
    catch (InsufficientInventoryException exception) {
        // Just log and continue returning a normal result.
        log.warn("Cannot reserve inventory", exception);
    }

    return order;
}
~~~

In this example, the exception is thrown and caught within the same transactional method; it does not pass through the transaction proxy as an escaping exception. The method finishes normally, so the transaction interceptor commits, and the order may be persisted even though inventory was not reserved.

Note: if the exception came from another bean annotated with `@Transactional(REQUIRED)` and escaped that bean's proxy, the participating transaction may already have been marked rollback-only. When the outer method catches the exception and returns, the transaction still rolls back and may throw `UnexpectedRollbackException` at commit time. This scenario is explained in the propagation section.

If business logic requires canceling the whole operation, the clearest approach is rethrowing the exception:

~~~java
catch (InsufficientInventoryException exception) {
    throw exception;
}
~~~

If you must catch the exception to run extra logic while still rolling back, mark the transaction rollback-only:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

catch (InsufficientInventoryException exception) {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    return Order.rejected(command);
}
~~~

Once marked rollback-only, the transaction rolls back on completion even if the method returns normally. However, returning `Order.rejected(...)` does not itself communicate that data rolled back; design responses and business states consistently. When no special return payload is needed, throwing the exception is usually clearer.

## 7. Mapping Exceptions to GraphQL Errors

Exception resolvers convert exceptions that escaped the resolver/service into GraphQL errors. Mapping happens after the transactional service call has passed through the transaction interceptor.

Example `@ControllerAdvice`:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;

@ControllerAdvice
public class OrderGraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleInsufficientInventory(
            InsufficientInventoryException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("The requested quantity is not available")
                .extensions(Map.of("code", "INSUFFICIENT_INVENTORY"))
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleOrderNotFound(
            OrderNotFoundException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Order was not found")
                .extensions(Map.of("code", "ORDER_NOT_FOUND"))
                .build();
    }
}
~~~

`ErrorType.BAD_REQUEST` and `ErrorType.NOT_FOUND` describe client/business errors. For unexpected failures, handle them according to the application's internal error policy; never return stack traces, SQL, connection strings, or sensitive exception messages to clients.

The important sequence:

1. Resolver calls `orderService.createOrder(...)` via the Spring proxy.
2. The transaction interceptor starts the transaction.
3. The service throws `InsufficientInventoryException`.
4. The transaction interceptor rolls back because it is a `RuntimeException`.
5. The exception propagates out to GraphQL execution.
6. `@GraphQlExceptionHandler` maps the exception into a GraphQL error.

The exception handler must not be responsible for deciding business transaction rollback. By the time the handler receives the exception, the service's transaction has already ended according to rollback rules.

## 8. Transaction Propagation

Propagation determines whether a transactional method joins an existing transaction or starts another one.

| Propagation | Behavior | When to Use |
| --- | --- | --- |
| `REQUIRED` | Joins current transaction; creates a new one if none exists | Default, fits most use cases |
| `REQUIRES_NEW` | Suspends current transaction and creates a new one | Independent audit logging that must commit even if outer transaction rolls back |
| `SUPPORTS` | Joins if active; otherwise runs non-transactionally | Reads that can run inside or outside a transaction |
| `MANDATORY` | Requires an existing active transaction | Internal helpers only callable inside an already-open use-case transaction |
| `NOT_SUPPORTED` | Suspends current transaction and runs non-transactionally | Work that should not hold an open transaction |
| `NEVER` | Throws an error if a transaction is active | Ensuring an operation never runs inside a transaction |
| `NESTED` | Uses nested transaction/savepoint if supported by the transaction manager | Partial rollback within an outer transaction when the resource supports it |

`REQUIRED` is the preferred default. For instance, `OrderApplicationService` calls `InventoryService` annotated with `@Transactional(REQUIRED)`: both join one transaction. If reserving inventory fails and the exception escapes the outer transaction, both the order and inventory changes are rolled back.

## 9. REQUIRES_NEW and Independent Data

`REQUIRES_NEW` creates an independent transaction. The outer transaction is suspended while the new transaction runs.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String action, String reference) {
        auditRepository.save(AuditEntry.of(action, reference));
    }
}
~~~

If the order-creation transaction rolls back, the audit record can still commit because it belongs to a separate transaction. This is intentional behavior, yet also a risk: do not use `REQUIRES_NEW` for data that must roll back together with the primary business operation.

`REQUIRES_NEW` typically requires an additional database connection while the outer transaction still holds its connection. Under high load, an undersized connection pool can cause waiting or connection exhaustion. Weigh the cost and avoid overuse.

## 10. NESTED and Savepoints

`Propagation.NESTED` can create a savepoint within the current transaction. If the nested operation fails and rolls back to the savepoint, the outer transaction can continue.

~~~java
@Transactional(propagation = Propagation.NESTED)
public void updateOptionalMetadata(Long orderId) {
    metadataRepository.updateForOrder(orderId);
}
~~~

`NESTED` support depends on the transaction manager and resource. JDBC transaction managers may support savepoints; JPA transaction managers do not provide portable nested transactions across all persistence providers. Do not assume `NESTED` behaves identically across all setups. Check the active transaction manager and write integration tests for the required semantics.

If savepoints are unnecessary, keeping `REQUIRED` and letting errors propagate to the transaction boundary is usually simpler.

## 11. UnexpectedRollbackException

A method joining the current transaction with `REQUIRED` can mark the transaction rollback-only. If the outer method catches the exception and proceeds as if everything succeeded, Spring throws `UnexpectedRollbackException` when the outer transaction tries to commit because the transaction was already marked rollback-only.

Flow example:

~~~java
@Transactional
public void placeOrder() {
    try {
        inventoryService.reserveOrFail(); // REQUIRED, joins this transaction
    }
    catch (InventoryException exception) {
        log.warn("Reservation failed; continuing", exception);
    }

    orderRepository.save(Order.pending());
}
~~~

If `reserveOrFail()` marked the transaction rollback-only before the exception was caught, the outer method cannot restore that transaction to a committable state. As a result, the entire transaction rolls back and the outer caller may receive `UnexpectedRollbackException`.

When an error indicates business failure, let the exception escape. If secondary processing requires an independent transaction, consider `REQUIRES_NEW` with a clear understanding of what data may commit independently.

## 12. Self-Invocation Can Bypass @Transactional

Spring normally applies `@Transactional` through a proxy. A method on the same object directly calling another method on itself bypasses the proxy, so the annotation on the target method may not take effect.

~~~java
@Service
public class OrderService {

    public void importOrders() {
        this.saveOneOrder(); // self-invocation, bypasses the transaction proxy
    }

    @Transactional
    public void saveOneOrder() {
        // Cannot assume this call opens its own transaction.
    }
}
~~~

Place transactions on public application service methods called from other beans, or extract the use case into a separate bean. Avoid self-injecting the class's own proxy merely to invoke a method.

`@Transactional` must also be placed on a Spring-managed method/class. Instantiating an object with `new` instead of dependency injection bypasses the proxy. With proxy-based transaction management, only calls passing through the proxy are intercepted.

## 13. readOnly, Isolation, and Timeout

`@Transactional` also supports configuring transaction attributes:

~~~java
@Transactional(readOnly = true)
public Order findOrder(Long id) {
    return orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
}

@Transactional(timeout = 5)
public Order updateOrder(Long id, UpdateOrderCommand command) {
    // Update within a bounded transaction timeout.
    return doUpdate(id, command);
}
~~~

- `readOnly = true` is a hint for the transaction manager/provider; do not treat it as an authorization mechanism or an absolute guarantee against writes.
- `isolation` controls the isolation level when supported by the transaction manager and database; choose it according to the anomaly you need to prevent rather than raising isolation arbitrarily.
- `timeout` limits transaction duration as supported by the transaction manager/resource. It does not replace dedicated timeouts for HTTP clients or downstream services.

For read-only GraphQL queries, a read-only transaction in the service can ensure a group of read operations run in the same transaction. Do not open a long transaction spanning the entire GraphQL request if the response resolves many fields asynchronously.

## 14. Mutations with Multiple Root Fields Are Not Automatically One Transaction

GraphQL executes top-level mutation fields sequentially. However, that does not mean the entire mutation operation is wrapped in a single database transaction.

Example:

~~~graphql
mutation {
    createOrder(input: { productId: "10", quantity: 2 }) {
        id
    }
    updateCustomer(id: "customer-1", name: "New name") {
        id
    }
}
~~~

If `createOrder` and `updateCustomer` call two separate `@Transactional` service methods, each method can commit independently. If the second field fails, the first field's already-committed transaction does not automatically roll back.

If business logic requires both changes to be atomic, create a single mutation field and one service method orchestrating both:

~~~graphql
type Mutation {
    checkout(input: CheckoutInput!): CheckoutResult!
}
~~~

~~~java
@Transactional
public CheckoutResult checkout(CheckoutCommand command) {
    Order order = orderService.createWithinCurrentTransaction(command.order());
    customerService.updateWithinCurrentTransaction(command.customer());
    return new CheckoutResult(order.getId());
}
~~~

The called methods must participate in the same transaction manager/transaction, such as via `REQUIRED` propagation. Place the boundary at the use-case orchestration layer to accurately express business atomicity.

## 15. Nested Field Resolution Can Run After the Mutation Transaction

The resolver returns an entity after the transactional service commits. GraphQL may then resolve child fields such as `order.customer`, `order.items`, or `order.payment`.

Do not rely on an already-completed service transaction to keep a persistence context alive for child fields. If child fields access lazy associations after the session closes, the application can throw `LazyInitializationException`; if child fields call their own repositories, they run in their own service transactions.

Approaches to handle this:

- Return a DTO/read model fully queried inside the use-case transaction.
- Use projections or fetch plans tailored to the returned data.
- Use DataLoader/`@BatchMapping` to batch-load relationships via a service with its own transaction.
- Do not hold write transactions open while GraphQL resolves a deep response tree or async fields.

Transaction boundaries should enclose business write operations; reading child fields should be designed separately for response needs and performance.

## 16. Exception Handling Should Not Hide Transaction Errors

A resolver must not catch all exceptions and return `null`:

~~~java
@MutationMapping
public Order createOrder(@Argument CreateOrderInput input) {
    try {
        return orderService.createOrder(toCommand(input));
    }
    catch (Exception exception) {
        log.error("Create order failed", exception);
        return null;
    }
}
~~~

If the exception escaped the service proxy, the transaction may have rolled back. Yet swallowing the exception in the resolver prevents GraphQL from receiving a meaningful error, leaving the client with just `null`. If the exception was caught inside the transactional method, the transaction might even commit if it was not marked rollback-only.

Let business exceptions be handled by `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`. There, intentionally map failures to an `ErrorType` and a client-safe message.

Do not use GraphQL `errors` as a substitute for business state. If an operation is valid and produces a rejection outcome (such as an order with status `REJECTED`), you can return a normal business payload. If the operation must roll back due to failure, throw an exception and map it to a GraphQL error.

## 17. Async Execution and Imperative Transactions

Spring's imperative transactions are normally bound to the current thread. If a transactional method launches a `CompletableFuture`, `@Async`, or hands work off to another executor, the transaction context does not automatically follow onto the new thread.

~~~java
@Transactional
public CompletableFuture<Order> createOrderAsync(CreateOrderCommand command) {
    return CompletableFuture.supplyAsync(() -> {
        // Do not assume the outer method's transaction exists on this thread.
        return orderRepository.save(Order.pending(command));
    });
}
~~~

The example above is unsafe if you expect the repository write to execute inside the imperative transaction opened on the calling thread. The transaction may finish before the future completes.

For async work, have the async task invoke another service bean with its own transaction:

~~~java
@Service
public class AsyncOrderWorker {

    private final OrderWriteService orderWriteService;

    public AsyncOrderWorker(OrderWriteService orderWriteService) {
        this.orderWriteService = orderWriteService;
    }

    @Async
    public CompletableFuture<Long> persist(CreateOrderCommand command) {
        Order order = orderWriteService.createOrder(command);
        return CompletableFuture.completedFuture(order.getId());
    }
}
~~~

`OrderWriteService.createOrder` is invoked through a bean proxy on the worker thread and opens its own transaction on that thread. Do not rely on the GraphQL request's transaction to cover offloaded work.

## 18. Reactive Transactions and Reactor Context

With a reactive stack using R2DBC, transactions are managed via the reactive context instead of thread-local imperative transactions. Use the matching reactive transaction manager and keep work inside the same Reactor chain.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository orderRepository;
    private final ReactiveInventoryService inventoryService;

    public ReactiveOrderService(
            ReactiveOrderRepository orderRepository,
            ReactiveInventoryService inventoryService
    ) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public Mono<Order> createOrder(CreateOrderCommand command) {
        return orderRepository.save(Order.pending(command))
                .flatMap(order -> inventoryService.reserve(
                                command.productId(), command.quantity())
                        .thenReturn(order));
    }
}
~~~

Never call `.block()` inside a reactive transaction to switch to imperative flow, or detach the publisher onto a context lacking the transaction. Likewise, do not mix a blocking JPA repository and a reactive R2DBC repository assuming they share one transaction; the two technologies use different transaction managers and resources.

For reactive methods returning `Mono`/`Flux`, the transaction interceptor manages the publisher upon subscription execution. Errors emitted in the reactive chain can trigger rollback per rollback rules. When multiple transaction managers exist, specify the appropriate manager via `@Transactional(transactionManager = "...")`.

## 19. DataLoader and Transaction Boundaries

DataLoader batches field loads to avoid N+1. Batch loaders are typically invoked during the GraphQL field execution phase, potentially after the mutation service has committed.

Do not assume a DataLoader batch shares a transaction with the mutation just because it runs within the same GraphQL request. If a batch loader needs a transaction to read data, place the transaction on the service invoked by the batch loader:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerReadService {

    private final CustomerRepository customerRepository;

    public CustomerReadService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional(readOnly = true)
    public Map<Long, Customer> findAllByIds(Set<Long> ids) {
        return customerRepository.findAllById(ids).stream()
                .collect(Collectors.toMap(Customer::getId, Function.identity()));
    }
}
~~~

The batch loader calls `CustomerReadService` and gets a read transaction scoped to the batch query. This read transaction is independent of the prior write transaction.

If you need to read just-written state within the same transaction, perform that read inside the application service before returning, or design the use case so it does not depend on field resolvers running after commit.

## 20. External Side Effects and Transaction Commit

A database rollback cannot automatically undo already-sent emails, already-called HTTP requests, or messages already published to a broker outside the transaction.

Avoid sending emails before the database commits:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.pending(command));
    emailClient.sendOrderConfirmation(order); // Side effect may already have occurred
    inventoryService.reserve(command.productId(), command.quantity());
    return order;
}
~~~

If inventory reservation fails, the database rolls back while the email may already have been sent. Use transaction synchronization to execute post-commit side effects when appropriate:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OrderNotificationService {

    private final OrderRepository orderRepository;
    private final EmailClient emailClient;

    public OrderNotificationService(
            OrderRepository orderRepository,
            EmailClient emailClient
    ) {
        this.orderRepository = orderRepository;
        this.emailClient = emailClient;
    }

    @Transactional
    public Order createAndNotify(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.pending(command));

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        emailClient.sendOrderConfirmation(order.getId());
                    }
                }
        );

        return order;
    }
}
~~~

The `afterCommit` callback only runs when the transaction commits. Even so, if the process stops after commit and before sending the email, an in-memory callback can be lost. For side effects requiring high reliability, use a transactional outbox: write an event into an outbox table in the same transaction as the order, then have a separate worker publish the event and mark it processed.

If an `afterCommit` callback throws an exception, the database transaction has already committed and cannot be rolled back; the exception may still propagate to the caller, causing the GraphQL response to report an error even though the data was saved. Catch/log callback errors and provide a durable retry mechanism; for critical side effects, an outbox avoids relying on in-memory callbacks.

Spring also provides `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` to handle application events after commit. When durable delivery is required, an outbox is generally preferable to an in-memory event listener.

## 21. Testing Rollback at the Service Layer

Unit tests mocking repositories can verify a service throws an exception, but they do not prove the database transaction actually rolled back. To verify rollback, write an integration test using the real transaction manager and database.

Service-level integration test example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.BDDMockito.willThrow;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class OrderTransactionTests {

    @Autowired
    OrderApplicationService orderService;

    @Autowired
    OrderRepository orderRepository;

    @MockitoBean
    InventoryService inventoryService;

    @Test
    void rollsBackOrderWhenInventoryReservationFails() {
        long before = orderRepository.count();
        willThrow(new InsufficientInventoryException(10L))
                .given(inventoryService).reserve(10L, 2);

        assertThrows(InsufficientInventoryException.class, () ->
                orderService.createOrder(new CreateOrderCommand(10L, 2, "customer-1"))
        );

        assertThat(orderRepository.count()).isEqualTo(before);
    }
}
~~~

This test uses the Spring Boot test context and mocks the inventory collaborator to force the failure branch after saving the order. Crucially, `orderService.createOrder(...)` must pass through the Spring proxy, and assertions must read the database after the call completes.

Do not place `@Transactional` on the test method in this example. If the test opens its own transaction wrapping the entire test, inspecting the commit/rollback outcome of the inner transaction can be obscured by the test transaction. If a test needs transactional fixtures, commit fixtures explicitly or use `TestTransaction` to control commit timing.

## 22. Testing Rollback via GraphQlTester

Integration tests through GraphQL verify both exception mapping and post-execution database state:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.willThrow;

@SpringBootTest
@AutoConfigureHttpGraphQlTester
class OrderMutationRollbackGraphQlTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Autowired
    OrderRepository orderRepository;

    @MockitoBean
    InventoryService inventoryService;

    @MockitoBean
    CurrentCustomerProvider customerProvider;

    @Test
    void returnsGraphQlErrorAndDoesNotPersistOrder() {
        long before = orderRepository.count();
        org.mockito.BDDMockito.given(customerProvider.currentCustomerId())
                .willReturn("customer-1");
        willThrow(new InsufficientInventoryException(10L))
                .given(inventoryService).reserve(10L, 2);

        graphQlTester.document("""
                mutation {
                    createOrder(input: { productId: "10", quantity: 2 }) {
                        id
                        status
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors)
                        .anyMatch(error -> error.getMessage().contains("not available")));

        assertThat(orderRepository.count()).isEqualTo(before);
    }
}
~~~

The test requires fixture setup where product `10` has insufficient inventory and `CurrentCustomerProvider` returns a valid customer. Response assertions verify the GraphQL error; repository assertions verify the actual rollback. Checking only `.errors()` does not prove data was undone.

For checked exceptions, write corresponding tests proving `rollbackFor` takes effect. For `noRollbackFor`, verify data commits as designed. For `REQUIRES_NEW`, verify audit records persist when the outer transaction rolls back.

## 23. Testing Multiple Mutation Fields and Atomicity

If the API allows an operation with multiple root mutation fields, write integration tests proving actual commit behavior. For example, if the first field commits successfully and the second field fails, the first field's data may remain persisted when each field runs its own transaction.

When a use case requires atomicity, tests must send a single orchestrating mutation field and verify all related tables remain unchanged when one step fails. Do not check only that the field returns an error; re-read state from the database after GraphQL execution.

## 24. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| GraphQL returns an error, yet data still persists | Exception caught inside transactional method or error occurred after commit | Review transaction boundaries and let rollback-triggering exceptions escape the service |
| Checked exception does not roll back | Default rollback applies only to unchecked exceptions and `Error` | Declare `rollbackFor` appropriately |
| Resolver returns `null` without a helpful error | Resolver caught and swallowed the exception | Use `@GraphQlExceptionHandler`/`DataFetcherExceptionResolver` |
| Method has `@Transactional` but opens no transaction | Self-invocation, non-Spring-managed object, or call bypassed proxy | Call through bean proxy and place boundary on a service bean |
| Outer method receives `UnexpectedRollbackException` | Inner `REQUIRED` participant marked the transaction rollback-only | Let the exception propagate or intentionally design an independent transaction |
| Audit record remains after rollback | Audit uses `REQUIRES_NEW` | This is independent behavior; use only when required by business rules |
| Nested rollback does not work as expected | Transaction manager/resource does not support savepoints | Check `NESTED` support and write integration tests |
| Async task writes data outside a transaction | Imperative transactions do not propagate automatically across threads | Open a transaction inside the worker service on the execution thread |
| `LazyInitializationException` on child field | Persistence context closed after service transaction | Return DTOs/projections or use a read service/DataLoader |
| Email sent even though mutation rolled back | Side effect ran before commit | Use an after-commit callback or transactional outbox |
| Test fails to catch broken rollback | Test only mocks repositories or opens its own test transaction | Use integration tests and inspect database state after the call |

## 25. Process for Designing Exceptions and Rollback in Mutations

When implementing a data-writing mutation:

1. Identify the atomic business use case and place the transaction on the application service.
2. Keep resolvers thin: bind arguments, retrieve principal/context, invoke the service.
3. Use default `REQUIRED` so participating services/repositories share the transaction.
4. Classify which exceptions are unchecked, checked, or allowed to commit.
5. Declare `rollbackFor`/`noRollbackFor` when diverging from defaults.
6. Never catch and swallow exceptions when business rules require rollback.
7. Map exceptions outside the transaction boundary into safe GraphQL errors.
8. Never assume a GraphQL operation with multiple mutation fields is one transaction.
9. Never hold write transactions open across async field resolution or external network calls.
10. Route high-reliability emails/messages through after-commit or a transactional outbox.
11. Test both the GraphQL response and database state after the request finishes.
12. Verify propagation, self-invocation, transaction managers, and reactive contexts when the system mixes execution models.

Spring transactions manage the atomicity of database operations within a transaction boundary. GraphQL exception handling manages how errors appear to clients. Good design coordinates both mechanisms cleanly: the service decides commit/rollback, while the GraphQL layer translates results or exceptions into appropriate responses.

## References

- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.exceptions)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)

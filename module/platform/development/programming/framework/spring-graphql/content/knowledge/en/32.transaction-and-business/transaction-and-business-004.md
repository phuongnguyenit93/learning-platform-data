# Mutations Calling Transactional Services

In Spring for GraphQL, GraphQL does not automatically define transaction boundaries for mutations. The application decides which units of work must commit or roll back together. In a layered architecture, a manageable pattern is for the GraphQL controller to receive input and call an application service annotated with `@Transactional`. The service forms the unit of work for a business operation, while the controller handles mapping GraphQL arguments and responses.

This organization keeps transactions tied to business operations rather than the entire GraphQL request. For example, an order-placement mutation can validate the product, reserve stock, and create the order within the same transaction. If one step fails and an exception escapes the service, database changes inside the transaction are rolled back according to configured rules.

This lesson walks from schema and resolver to service transactions, explaining Spring proxies, rollback behavior, business errors, multiple mutations in a single request, reactive transactions, and how to test commit/rollback behavior.

## 1. Where Does the Transaction Boundary Lie?

A GraphQL mutation typically flows through these layers:

~~~mermaid
flowchart TD
    A[GraphQL client] --> B[Mutation field]
    B --> C[Controller / resolver]
    C --> D[Application service proxy]
    D --> E[Begin transaction]
    E --> F[Validate business rules]
    F --> G[Repository and domain operations]
    G --> H{All steps succeed?}
    H -->|Yes| I[Commit]
    H -->|No| J[Rollback]
    I --> K[Return result to GraphQL]
    J --> L[Exception handling]
    L --> M[GraphQL errors]
~~~

The resolver acts as an adapter between GraphQL and the application layer. It should receive and bind arguments, convert inputs into application commands, invoke the application service, and return DTOs or results matching the schema.

The application service manages transactions and orchestrates business steps. When the controller invokes the service bean through a Spring proxy, the transaction interceptor opens a transaction before running the method and completes the transaction when the method finishes.

There is no need to open a transaction wrapping the entire GraphQL request just to handle a single mutation. A single request may contain multiple independent fields, whereas a transaction should usually wrap a clearly bounded business operation.

## 2. GraphQL Schema for an Order Mutation

Example schema declaring the input and result:

~~~graphql
input PlaceOrderInput {
    productId: ID!
    quantity: Int!
}

type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}

type Order {
    id: ID!
    status: String!
    quantity: Int!
    customer: Customer
    items: [OrderItem!]!
}

type Customer {
    id: ID!
    name: String!
}

type OrderItem {
    productName: String!
    quantity: Int!
}
~~~

GraphQL validates document structure, field names, argument types, and nullability before invoking the resolver. Errors such as a missing `input`, an invalid scalar, or a non-existent field may be rejected before the service transaction even starts.

The schema does not itself determine how data is committed. It only describes the operations and types clients can send or receive.

## 3. Application Inputs and DTOs

Separating GraphQL inputs from internal commands keeps the application layer independent of the schema:

~~~java
public record PlaceOrderInput(
    String productId,
    Integer quantity
) {
}

public record PlaceOrderCommand(
    String productId,
    int quantity
) {
}

public record OrderView(
    String id,
    String status,
    int quantity
) {
}
~~~

These records simply illustrate the data shapes. In a real project, `PlaceOrderInput` typically lives in the GraphQL adapter; `PlaceOrderCommand` and `OrderView` live in the application layer. Packages/imports are omitted in the DTO snippet to keep focus on layer boundaries.

GraphQL inputs may use wrapper types such as `Integer` to reflect binding and validation. Internal commands can use primitives or appropriate domain types once input has been validated.

Avoid passing JPA entities directly as inputs or responses merely because they have fields similar to the schema. Entities represent the persistence model; DTOs represent the API response contract. Separating them prevents leaking internal columns, out-of-transaction lazy loading, and schema changes from impacting the persistence model.

## 4. Controllers Only Orchestrate GraphQL

The resolver invokes the service and returns the result:

~~~java
package com.example.orders.graphql;

import com.example.orders.application.OrderApplicationService;
import com.example.orders.application.PlaceOrderCommand;
import com.example.orders.application.OrderView;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMutationController {

    private final OrderApplicationService orderService;

    public OrderMutationController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public OrderView placeOrder(@Argument("input") PlaceOrderInput input) {
        PlaceOrderCommand command = new PlaceOrderCommand(
            input.productId(),
            input.quantity()
        );

        return orderService.placeOrder(command);
    }
}
~~~

The controller does not need to call `PlatformTransactionManager` or open transactions manually. Spring injects the `OrderApplicationService` bean; calls go through the proxy when transaction management is configured and the method is annotated appropriately.

You can place `@Transactional` directly on a `@MutationMapping` method, but the service layer is usually a better boundary: the same business operation can be invoked from GraphQL, REST, a message consumer, or a batch job while sharing the same transaction policy.

The Spring for GraphQL documentation presents `@Transactional` directly on `@MutationMapping` as a simple way to create a transaction per controller method. This lesson uses a service boundary because the mutation delegates business logic to an application service and the same service may be called from other adapters. Both approaches are valid. If both the controller and service are annotated with `@Transactional` using the default `REQUIRED` propagation, the service call joins the transaction opened at the controller; there is no need to annotate both just to obtain rollback behavior.

## 5. Placing @Transactional on the Application Service

Example order-creation service:

~~~java
package com.example.orders.application;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final ProductRepository productRepository;
    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    public OrderApplicationService(
            ProductRepository productRepository,
            OrderRepository orderRepository,
            InventoryService inventoryService) {
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public OrderView placeOrder(PlaceOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new InvalidOrderException("Quantity must be positive");
        }

        Product product = productRepository.findById(command.productId())
            .orElseThrow(() ->
                new ProductNotFoundException(command.productId())
            );

        Order order = Order.createPending(product, command.quantity());
        Order saved = orderRepository.save(order);

        inventoryService.reserve(product.getId(), command.quantity());
        saved.confirm();

        return new OrderView(
            saved.getId().toString(),
            saved.getStatus().name(),
            saved.getQuantity()
        );
    }
}
~~~

When `placeOrder` is called through the proxy:

1. Spring selects the appropriate transaction manager.
2. The transaction begins or joins an existing transaction.
3. Repository operations using the same transaction manager participate in that transaction.
4. If the method completes normally, the transaction is committed.
5. If an exception matching the rollback rules escapes the method, the transaction is rolled back.

Default propagation is `REQUIRED`: if a suitable transaction already exists, the method joins it; otherwise, Spring creates a new transaction.

Repositories and services must share the same transaction manager and compatible resource to belong to the same database transaction. Two independent databases or an HTTP call to another service do not automatically form an atomic transaction.

## 6. Why Is the Service Layer a Good Transaction Boundary?

A transaction should encompass a complete business operation. For instance, placing an order might include checking that the product is active, validating the quantity, reserving stock, creating the order and order lines, and recording the initial status.

If each repository method opens its own transaction, one step can commit while a later step fails. When the entire sequence resides inside a single service transaction, operations participating in that transaction can commit or roll back as one unit of work.

A service method is also easier to reuse than a transaction tied directly to a GraphQL controller. If a REST endpoint or message handler later invokes the same business logic, the transaction policy does not need to be duplicated across each adapter.

Do not place a transaction on an overly broad service merely to hold a database connection open for an entire request. Choose methods representing specific business actions.

## 7. Spring Proxies and Self-Invocation

`@Transactional` relies on Spring AOP proxies in the default configuration. Calls must go through the proxy for transaction advice to be applied.

~~~mermaid
flowchart LR
    A[GraphQL controller] -->|Bean reference| B[Spring proxy]
    B --> C[Transaction interceptor]
    C --> D[OrderApplicationService]
    D --> E[Repository]
~~~

Calls from a controller to a Spring-injected service bean normally pass through the proxy. However, an internal call from one method to another on the same object does not pass through the proxy:

~~~java
@Service
public class OrderApplicationService {

    public OrderView placeOrder(PlaceOrderCommand command) {
        return createOrder(command); // self-invocation
    }

    @Transactional
    public OrderView createOrder(PlaceOrderCommand command) {
        // ...
    }
}
~~~

In this example, calling `createOrder` is self-invocation. Under the default proxy mode, the annotation on the internally called method does not create a new transaction.

A cleaner design is placing `@Transactional` on public service methods invoked from other beans, or extracting a collaborator into its own bean if an independent transaction boundary is genuinely needed. Avoid self-injecting the service just to invoke the proxy and work around self-invocation.

## 8. Default Rollback Rules

Spring marks a transaction for rollback by default when a transactional method exits with a `RuntimeException` or `Error`. Checked exceptions do not trigger rollback by default.

Example of a business exception that needs no extra declaration because it extends `RuntimeException`:

~~~java
public class InsufficientStockException extends RuntimeException {

    public InsufficientStockException(String productId) {
        super("Insufficient stock for product " + productId);
    }
}
~~~

If the business logic uses a checked exception, declare the rollback rule explicitly:

~~~java
@Transactional(rollbackFor = PaymentDeclinedException.class)
public OrderView placeOrder(PlaceOrderCommand command)
        throws PaymentDeclinedException {
    // ...
}
~~~

`noRollbackFor` can be used in special cases, but ensure committing when that exception occurs matches the business requirements.

Do not assume every GraphQL error causes a transaction rollback. The transaction manager decides rollback based on exceptions escaping the transactional method and rollback rules, not on whether the GraphQL response contains an `errors` field.

## 9. Do Not Swallow Exceptions When Rollback Is Needed

If the service catches an exception and returns normally, the transaction interceptor may commit:

~~~java
@Transactional
public OrderView placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(Order.pending(command));

    try {
        inventoryService.reserve(command.productId(), command.quantity());
    } catch (InsufficientStockException exception) {
        return new OrderView(
            order.getId().toString(),
            "REJECTED",
            order.getQuantity()
        );
    }

    return new OrderView(
        order.getId().toString(),
        "CREATED",
        order.getQuantity()
    );
}
~~~

The snippet above returns normally after catching the error. If the exception is not rethrown and the transaction is not marked rollback-only, saving the order may be committed.

There is an important nuance: if `inventoryService.reserve` is a proxied method with `@Transactional(propagation = REQUIRED)` and throws a `RuntimeException`, the inner transaction interceptor may mark the shared transaction as rollback-only before the exception reaches the `catch` block. When the outer method returns, the commit step throws `UnexpectedRollbackException` and the data still rolls back. Thus, the outcome depends on whether the transaction was already marked rollback-only, not solely on whether the exception was caught.

If an error must cancel the entire business operation, let the exception escape the method or intentionally mark the transaction rollback-only. Usually it is best to throw a business exception and translate it into a GraphQL error in the error-handling layer.

If the business outcome is a normal result—for example, rejecting an order because stock is depleted and no changes should be persisted—you can return a business payload. But if data was already written earlier and you want to undo those changes, enforce rollback explicitly rather than just returning an error payload.

## 10. Translating Business Exceptions into GraphQL Errors

Spring for GraphQL allows handling exceptions from data fetchers using `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler`.

Example using controller advice:

~~~java
package com.example.orders.graphql;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlBusinessExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleInsufficientStock(
            GraphqlErrorBuilder<?> errorBuilder,
            InsufficientStockException exception) {

        return errorBuilder
            .errorType(ErrorType.BAD_REQUEST)
            .message("Insufficient stock to complete order")
            .build();
    }
}
~~~

An exception thrown by the service passes through the transaction proxy first. The transaction interceptor applies rollback rules and propagates the exception out of the controller invocation; the GraphQL exception handler can then convert the exception into an error in the response.

Never return stack traces, SQL statements, table names, credential details, or personal data in GraphQL error messages. Clients only need stable messages and error codes to handle. Internal logs can record more detail while protecting sensitive data.

If you use a payload type like `OrderResult` with `userErrors`, clearly distinguish whether an error represents a normal business outcome or requires rollback. A response with `userErrors` does not by itself mark a transaction for rollback.

## 11. Validation Before and Inside Transactions

There are two layers of validation:

- GraphQL validation/coercion checks the document, scalars, arguments, and input types before calling the resolver.
- Business validation checks domain state such as stock availability, purchase limits, ownership, or order status.

Pure input checks can run before writing data. Checks that depend on database state should live in the application service and execute within the transaction when consistency is required.

Example:

~~~java
@Transactional
public OrderView placeOrder(PlaceOrderCommand command) {
    if (command.quantity() < 1 || command.quantity() > 20) {
        throw new InvalidOrderException("Quantity is outside allowed range");
    }

    Product product = productRepository.findById(command.productId())
        .orElseThrow(() -> new ProductNotFoundException(command.productId()));

    if (!product.isOrderable()) {
        throw new ProductUnavailableException(command.productId());
    }

    // Reserve stock and persist the order.
}
~~~

Validating before writes avoids wasted work. However, checking stock levels and updating stock must be designed against race conditions—for example, using optimistic/pessimistic locking or conditional updates. Simply opening a transaction does not by itself prevent two concurrent requests from reading the same stock level and both placing orders.

## 12. Nested Fields Are Resolved After the Mutation Transaction

Suppose the mutation returns an `Order`, and the client also requests `customer` and `items`:

~~~graphql
mutation {
    placeOrder(input: { productId: "p-1", quantity: 2 }) {
        id
        status
        customer {
            id
            name
        }
        items {
            productName
            quantity
        }
    }
}
~~~

If the transaction resides solely in `OrderApplicationService.placeOrder`, the transaction ends when the service method returns. GraphQL may then proceed to resolve nested fields such as `customer` and `items`.

Do not assume nested resolvers automatically run inside the root mutation's transaction. If a nested resolver needs to read data, it can call a separate read service with an appropriate transaction/read-only policy. Consider consistency if data can change between the mutation commit and when the nested field is read.

With JPA, avoid returning entities containing lazy relationships and letting GraphQL traverse them after the persistence context closes. You can return a DTO containing fields loaded within the transaction, use projections or queries that fetch exact required data, use a nested resolver that reads data separately through an application service, or use `@BatchMapping`/DataLoader to batch relationship reads.

Do not hold a transaction open merely to avoid designing proper DTOs or resolvers.

## 13. Multiple Mutation Fields in One GraphQL Request

GraphQL permits an operation to contain multiple top-level mutation fields. Per execution semantics, top-level mutation fields execute sequentially in document order. However, sequential execution does not mean they automatically share one transaction.

Example:

~~~graphql
mutation {
    reserveStock(productId: "p-1", quantity: 2) {
        success
    }
    createShipment(orderId: "o-9") {
        id
    }
}
~~~

If each resolver calls a separate `@Transactional` service method without an enclosing transaction, each service invocation gets its own transaction. `reserveStock` can commit before `createShipment` runs. If the second field fails, the first field's transaction does not automatically roll back.

When two actions must be atomic, design a single mutation representing the entire use case:

~~~graphql
input FulfillOrderInput {
    orderId: ID!
    warehouseId: ID!
}

type Mutation {
    fulfillOrder(input: FulfillOrderInput!): Fulfillment!
}
~~~

The resolver calls a single `fulfillOrder` application service. That service reserves stock, creates the shipment, and updates the status within one transaction. This is the simplest way to guarantee the entire sequence commits or rolls back together.

Only use a transaction wrapping the entire GraphQL request when there is a clear requirement and you understand the implications for concurrency, thread model, and resource hold duration.

## 14. Transaction per Mutation Method vs. Request-Wide Transaction

Spring for GraphQL describes two general strategies:

| Strategy | Characteristics | Best Suited When |
| --- | --- | --- |
| Transaction per controller/service method | Each method has its own boundary | Most business mutations |
| Transaction spanning the entire GraphQL execution | Multiple data fetchers participate in one transaction | Special use cases requiring a request-level unit of work |

Request-wide transactions are more complex. With synchronous JDBC/JPA-based transactions, Spring typically binds the transaction to a thread. For multiple data fetchers to share the same transaction, the execution strategy must ensure invocations run sequentially on the same thread. GraphQL can normally execute query fields in parallel; forcing the entire execution to be sequential can reduce concurrency and lengthen transaction duration.

Holding a transaction across multiple resolvers can also hold database connections and locks longer than necessary. Therefore, a transaction per mutation/service method is the more controllable default choice.

## 15. Propagation and Multiple Participating Services

The default propagation value of `@Transactional` is `REQUIRED`.

~~~java
@Service
public class OrderApplicationService {

    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    @Transactional
    public OrderView placeOrder(PlaceOrderCommand command) {
        inventoryService.reserve(command.productId(), command.quantity());

        Order order = orderRepository.save(Order.create(command));
        return OrderView.from(order);
    }
}
~~~

If `InventoryService.reserve` also has `@Transactional` with `REQUIRED` propagation and uses the same transaction manager, it joins the existing transaction. If saving the order fails after reserving stock within the same database transaction, the inventory changes are also rolled back.

Other propagation modes:

- `REQUIRES_NEW`: suspends the current transaction and creates an independent transaction. Data in the new transaction can commit even if the outer transaction rolls back.
- `MANDATORY`: requires an active transaction to already exist.
- `SUPPORTS`: joins a transaction if one exists; otherwise runs non-transactionally.
- `NOT_SUPPORTED`: suspends the current transaction to run non-transactionally.

Do not use `REQUIRES_NEW` just to bypass transaction errors. It changes atomicity: data committed in an independent transaction will not roll back along with the outer transaction.

If multiple transaction managers exist, explicitly specify the manager for the service:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public OrderView placeOrder(PlaceOrderCommand command) {
    // ...
}
~~~

Ensure repositories and writing collaborators use the exact manager/resource intended by the business logic.

## 16. Reactive Mutations and ReactiveTransactionManager

If a service returns reactive types such as `Mono` or `Flux`, Spring can apply reactive transaction management when an appropriate `ReactiveTransactionManager` is available.

~~~java
@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository orderRepository;

    public ReactiveOrderService(ReactiveOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Mono<OrderView> placeOrder(PlaceOrderCommand command) {
        return validate(command)
            .then(orderRepository.save(Order.pending(command)))
            .map(OrderView::from);
    }
}
~~~

Reactive transactions are bound to the Reactor Context rather than relying on thread-locals like standard JDBC transactions. Data operations participating in the transaction must stay within the same reactive pipeline and use the corresponding reactive resource/transaction manager.

Do not call `subscribe()` inside the service to launch a detached pipeline. Do not call `block()` to turn a reactive pipeline into synchronous execution. Return the publisher to the GraphQL runtime so the pipeline is subscribed to and managed under the proper lifecycle.

If a method returns `Mono` while the repository uses imperative JDBC/JPA, Spring does not automatically turn a JDBC transaction into a reactive transaction. Choose the right programming model and transaction manager for the resource in use.

## 17. @Transactional with CompletableFuture

Reactive publishers must be distinguished from `CompletableFuture`. Spring recognizes `Publisher`/Reactor types for reactive transaction management. An imperative method returning `CompletableFuture` does not mean a thread-bound transaction will wait for the future to complete.

~~~java
@Transactional
public CompletableFuture<OrderView> placeOrderAsync(PlaceOrderCommand command) {
    return CompletableFuture.supplyAsync(() -> {
        // JDBC work may run after the method has returned.
        return repository.save(Order.create(command));
    });
}
~~~

The example above is not a safe way to keep a JDBC transaction around asynchronous work. The method returns the future immediately; the imperative transaction can finish when the method returns, before the lambda finishes executing.

As of Spring Framework 6.1, a `Future` that has already completed with an error at the time the method returns can also trigger rollback. This does not mean an imperative transaction waits for an in-flight future to complete before committing.

With JDBC/JPA, keep operations inside the same synchronous call through the transaction proxy, or design a worker/service with its own transaction. For reactive database access, use `Mono`/`Flux` and `ReactiveTransactionManager` throughout the pipeline. Never assume every asynchronous return type is awaited to completion by the transaction interceptor.

## 18. Calling External Services and Transactional Outbox

A database transaction only guarantees atomicity for resources managed by the transaction manager. It does not automatically roll back an HTTP request already sent, an email already dispatched, or a message already accepted by a broker.

For example, if a service updates the database and then calls a payment provider over HTTP, a database rollback cannot undo a charge already accepted by the provider.

Design strategies include:

- Keep database transactions short and perform external calls at an appropriate orchestration step.
- Use idempotency keys when calling external APIs so retries are safe.
- Use a transactional outbox: write the business change and the event to publish in the same database transaction; a separate publisher reads the outbox and sends the message.
- Use sagas/compensation when a workflow spans multiple services and requires compensating actions.

`@TransactionalEventListener(phase = org.springframework.transaction.event.TransactionPhase.AFTER_COMMIT)` can run a listener after the transaction commits. However, an in-memory listener does not replace a durable outbox when you must guarantee the event is not lost if the process stops right after commit.

## 19. Testing Mutation Transactions

`@GraphQlTest` is suitable for verifying that a GraphQL controller calls the right service and returns the expected response shape. Because services are usually mocked in slice tests, it does not prove that a real repository committed or rolled back.

To test transactions, use an integration test with `@SpringBootTest`, a GraphQL tester, and an appropriate test database. Example testing service rollback after a business step fails:

With `HttpGraphQlTester`, add `spring-graphql-test` in test scope and `spring-boot-starter-webflux` in test scope if the application does not already have WebFlux on the classpath. Spring Boot can auto-configure the tester for integration tests; the package of `@AutoConfigureHttpGraphQlTester` differs between Boot 3 and Boot 4 as noted in the example.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

// Spring Boot 4.x package. In Boot 3.x use
// org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester.
import org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class OrderMutationTransactionTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void rollsBackOrderWhenInventoryReservationFails() {
        long before = orderRepository.count();

        graphQlTester.document("""
                mutation {
                    placeOrder(input: {
                        productId: "out-of-stock"
                        quantity: 3
                    }) {
                        id
                    }
                }
                """)
            .execute()
            .errors()
            .expect(error ->
                error.getMessage().contains("Insufficient stock")
            )
            .verify();

        assertThat(orderRepository.count()).isEqualTo(before);
    }
}
~~~

The example assumes the test database has a product fixture `out-of-stock` with stock less than 3, the service persists partial data and then throws `InsufficientStockException`, and the exception handler converts the exception into a GraphQL error. The test method is not annotated with `@Transactional`, so the service transaction commits or rolls back independently before assertions read the database.

Other important tests include success: the order is saved with the right status; business exception: no partial data remains after rollback; checked exception: rollback occurs properly with `rollbackFor`; multiple services with `REQUIRED`: operations roll back together; multiple mutation fields: verifying each service invocation has the expected transaction boundary; external side effects: verifying outbox/events are written in the same transaction.

## 20. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Data persisted despite mutation returning a GraphQL error | Exception was caught and the service returned normally | Rethrow the exception or mark rollback-only |
| Method has `@Transactional` but does not roll back | Self-invocation or bean call bypassed proxy | Call the method through a bean proxy from another collaborator |
| Checked exception still commits data | Default rules do not roll back on checked exceptions | Declare `rollbackFor` |
| Two mutation fields run sequentially, but second error does not undo first | Each service call has its own transaction | Create an orchestrating mutation for operations needing atomicity |
| Nested field cannot read lazy relationship | Mutation service transaction has already ended | Return DTO/projection or use a dedicated read resolver |
| Two requests concurrently order the last item | Transactions do not automatically resolve race conditions | Use locking or conditional updates |
| HTTP payment succeeded while database rolled back | HTTP service does not belong to the DB transaction | Idempotency, outbox, saga, or compensation |
| Reactive transaction does not wrap DB operations | Wrong transaction manager or pipeline was split | Use `ReactiveTransactionManager` and keep the same Reactor pipeline |
| JDBC transaction ends before async task | Method returns `CompletableFuture` immediately | Do not treat a future as a reactive transaction; place transaction in the worker |
| Test fails to catch broken rollback | Test method opens its own transaction or only mocks the service | Use an integration test observing real commit/rollback |

## 21. Implementation Checklist

- Does the resolver only bind inputs and call the application service?
- Does the transaction boundary represent a complete business operation?
- Is the `@Transactional` method invoked through a Spring proxy?
- Do repositories share the same transaction manager when atomicity is needed?
- Do rollback rules match business exceptions?
- Are exceptions prevented from being swallowed before the transaction interceptor handles them?
- Does the GraphQL exception handler only convert errors to responses after the service has exited?
- Do nested fields avoid relying on lazy entities after the transaction closes?
- Do multiple mutation fields have a clear transaction policy?
- Do multi-step atomic operations have an appropriate orchestrating mutation?
- Do reactive services use the right `ReactiveTransactionManager` and Reactor pipeline?
- Do HTTP/message/email calls have an outbox or compensation strategy when needed?
- Do integration tests verify both commit and rollback against a real database/test container?

A mutation is the entry point for a client command, while the application service is the appropriate place for the business transaction. Have the resolver invoke the service via a Spring proxy, group related persistence operations into one transaction, and let rollback rules handle exceptions according to business intent. Multiple mutation fields in the same request can still belong to separate transactions; if an atomic outcome is required, design a single orchestrating mutation. For reactive access, use Reactor transactions properly; for side effects outside the database, use an outbox or compensating mechanism instead of expecting `@Transactional` to span every system.

## References

- [Spring for GraphQL — Data Integration and Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [GraphQL Java — Execution Strategies](https://graphql-java.com/documentation/execution/)




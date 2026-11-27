# Resolver Transaction Boundaries

## Objectives

After this lesson, you will be able to:

- Explain why GraphQL does not automatically define transaction semantics.
- Identify transaction boundaries for `@MutationMapping` and `@SchemaMapping`.
- Use `@Transactional` to scope a resolver invocation within a single transaction.
- Distinguish per-resolver transactions from a transaction spanning the entire GraphQL request.
- Understand why nested fields and DataLoader can execute outside the root resolver's transaction.
- Design a business Mutation that encompasses multiple database operations.
- Distinguish imperative transactions from reactive transactions.
- Handle rollbacks, exceptions, and GraphQL errors properly.
- Recognize the limits of propagation, self-invocation, and external side effects.
- Test transaction boundaries across services and GraphQL operations.

## 1. GraphQL Does Not Automatically Define Transactions

GraphQL defines how clients select operations and fields, how servers execute selection sets, and how `data` and `errors` are returned. GraphQL does not mandate that a request correspond to a single database transaction.

A GraphQL operation can invoke multiple resolvers. Each resolver can access a different repository, service, or data system. GraphQL also allows clients to request only a subset of the object graph, so the server does not necessarily load all data in a single query.

This raises a design question: where should a transaction start and end?

Common options include:

- Each resolver method has its own transaction.
- A business service method coordinates multiple operations inside one transaction.
- The entire GraphQL request runs inside a single transaction.

Each option has different atomicity scopes, isolation characteristics, and resource costs. Applications must choose boundaries suited to business needs rather than assuming a GraphQL request is automatically a transaction.

## 2. What Is a Resolver's Transaction Boundary?

A transaction boundary defines the timespan during which operations on transaction-aware resources participate in the same unit of work.

For a resolver method whose transaction is managed by Spring:

1. The call passes through a Spring transaction proxy.
2. The transaction manager starts a new transaction or joins an existing one.
3. The resolver executes logic and calls services/repositories.
4. If the method completes normally, the transaction is committed.
5. If an exception matching the rollback rules escapes the method, the transaction is rolled back.

Example:

~~~java
@MutationMapping
@Transactional
public Order createOrder(@Argument("input") CreateOrderInput input) {
    // Database operations during this method call
    // participate in the transaction together.
    return orderService.create(input);
}
~~~

In this example, the transaction starts when `createOrder` is called and completes when the method returns or throws an exception. Repositories using the same transaction manager can participate in that transaction.

This transaction wraps the resolver invocation. It does not inherently wrap every other field in the GraphQL request.

## 3. Transaction per Controller Method

Spring for GraphQL supports per-controller-method transactions. You can place `@Transactional` on a `@MutationMapping` method or a `@SchemaMapping` method.

Example:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;
import org.springframework.transaction.annotation.Transactional;

@Controller
class AccountController {

    private final AccountService accountService;

    AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @MutationMapping
    @Transactional
    public Account addAccount(@Argument("input") AccountInput input) {
        return accountService.addAccount(input);
    }
}
~~~

The transaction encompasses the `addAccount` call. Database operations performed by `accountService` during that call join the same transaction if they use the corresponding transaction manager and resource.

Spring for GraphQL describes this as a straightforward approach with a clear entry point, and it is generally recommended when a mutation needs a transaction.

`@Transactional` is only metadata. The application still needs an appropriate transaction manager and enabled transaction management. Spring Boot typically auto-configures this when the corresponding transaction infrastructure is present; in plain Spring Framework configuration, annotation-driven transaction management can be enabled with `@EnableTransactionManagement`.

`TransactionOperations` can be used instead of annotations when programmatic transaction control is needed:

~~~java
import org.springframework.transaction.support.TransactionOperations;

@Controller
class AccountController {

    private final TransactionOperations transactionOperations;
    private final AccountService accountService;

    AccountController(
            TransactionOperations transactionOperations,
            AccountService accountService) {
        this.transactionOperations = transactionOperations;
        this.accountService = accountService;
    }

    @MutationMapping
    public Account addAccount(@Argument("input") AccountInput input) {
        return transactionOperations.execute(status ->
                accountService.addAccount(input)
        );
    }
}
~~~

Declarative annotations are usually easier to read. Programmatic transactions are useful when the boundary applies only to one branch of logic or when you need direct access to the transaction status.

## 4. Place the Transaction in the Resolver or the Service?

There are two common organizational styles. Pick one primary boundary for the use case so readers clearly see where the transaction begins.

**Option A: Transaction in the resolver**

~~~java
@Controller
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    @Transactional
    public Order placeOrder(@Argument("input") PlaceOrderInput input) {
        return orderService.placeOrder(input);
    }
}
~~~

This suits cases where the transaction is tied directly to a GraphQL field and the controller serves as the business entry point for that operation.

**Option B: Transaction in the application service**

~~~java
@Controller
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public Order placeOrder(@Argument("input") PlaceOrderInput input) {
        return orderService.placeOrder(input);
    }
}

@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public Order placeOrder(PlaceOrderInput input) {
        Order order = orderRepository.save(Order.pending(input));
        inventoryRepository.reserve(input.items());
        return order.confirm();
    }
}
~~~

This suits cases where the same use case is invoked from GraphQL, REST, a message consumer, or another entry point. Because the transaction belongs to the business logic, the service can protect its own consistency.

If both the resolver and the service carry `@Transactional` with the default `REQUIRED` propagation and the same transaction manager, the service call normally joins the existing transaction. This does not create two independent transactions, though it can make configuration harder to read. Choose one primary boundary and only declare additional annotations when there is a clear reason.

## 5. Multiple Database Operations in One Mutation

A business mutation often requires multiple interdependent database operations.

For example, placing an order:

1. Create the order in a pending state.
2. Write the order lines.
3. Deduct or reserve inventory.
4. Transition the order to a confirmed state.

~~~java
@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final OrderLineRepository lineRepository;
    private final InventoryRepository inventoryRepository;

    OrderService(
            OrderRepository orderRepository,
            OrderLineRepository lineRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.lineRepository = lineRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public Order placeOrder(PlaceOrderInput input) {
        Order order = orderRepository.save(Order.pending(input));

        lineRepository.saveAll(
                OrderLine.from(order.getId(), input.items())
        );

        inventoryRepository.reserve(input.items());

        order.confirm();
        return orderRepository.save(order);
    }
}
~~~

Because all operations execute within one transactional service method, repositories sharing the same transaction manager can commit or roll back together.

Do not split each repository call into a separate transaction if business logic requires atomicity across them. If a transaction ends after the first step, a failure in a later step will not automatically undo the committed changes.

## 6. Multiple Root Mutations in One GraphQL Request

GraphQL allows a mutation operation to have multiple root fields. According to the GraphQL specification, fields in the top-level selection set of `Mutation` are executed sequentially in the order they appear in the document.

Example:

~~~graphql
mutation {
    reserve: reserveStock(orderId: "order-42")
    confirm: confirmOrder(orderId: "order-42")
}
~~~

The execution order is `reserveStock` followed by `confirmOrder`. However, sequential execution does not mean the two resolvers share a single transaction.

If each resolver method has `@Transactional`, the boundaries are typically:

- `reserveStock` starts and finishes the first transaction.
- After the first field completes, `confirmOrder` starts the second transaction.
- If the second transaction fails, the first already-committed transaction will not automatically roll back.

When two operations must be atomic together, design a single business mutation that accepts all required inputs:

~~~graphql
mutation {
    placeOrder(input: {
        customerId: "customer-1"
        items: [{ productId: "book-42", quantity: 2 }]
    }) {
        id
        status
    }
}
~~~

A single resolver invokes a single transactional application service to execute the entire use case. This is usually the simplest way to guarantee atomicity across related database steps.

## 7. Root Resolvers and Nested Fields Have Separate Boundaries

A mutation can return an object so that GraphQL continues resolving nested fields.

Example:

~~~graphql
mutation {
    addAccount(input: { name: "Northwind" }) {
        id
        name
        owner {
            id
            displayName
        }
    }
}
~~~

The `addAccount` resolver can be protected by a transaction:

~~~java
@MutationMapping
@Transactional
public Account addAccount(@Argument("input") AccountInput input) {
    return accountService.addAccount(input);
}
~~~

After the method returns, `addAccount`'s transaction ends. GraphQL then proceeds to resolve the `owner` field:

~~~java
@SchemaMapping(typeName = "Account", field = "owner")
@Transactional(readOnly = true)
public Person owner(Account account) {
    return personService.findOwner(account.getOwnerId());
}
~~~

The `owner` method runs in a separate transaction. It does not automatically join `addAccount`'s already-completed transaction, even though both methods belong to the same GraphQL operation.

Consequently, data read in a nested field may observe a different state than when the root mutation ran. If consistent data is required, consider loading the necessary data inside the same use-case service or returning a DTO that already holds the relevant data.

Do not hold a transaction open solely to keep a transaction context alive across all nested fields unless there is a specific isolation requirement.

## 8. Transactions with @SchemaMapping and @BatchMapping

`@SchemaMapping` is a resolver method and can have its own transaction if annotated with `@Transactional`.

`@BatchMapping` likewise performs a separate fetch for a group of parent objects. If a batch resolver needs multiple database operations to be atomic, the boundary can be placed on the batch method or on the service it calls.

Example:

~~~java
@BatchMapping(typeName = "Book", field = "author")
@Transactional(readOnly = true)
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

The batch resolver's transaction wraps the batch method invocation. It is not inherited from the root resolver's transaction merely because the batch is triggered within the same request.

DataLoader can defer and group field fetches to run in a batch after parent resolvers have returned. Therefore, do not assume the root resolver's transaction is still open when DataLoader executes.

If the batch needs a transaction, place the boundary at the batch resolver/service. If multiple fields must read the same consistent snapshot, design an explicit query or transaction boundary instead of relying on when DataLoader happens to dispatch.

## 9. Transactions for Queries and readOnly

Queries usually only read data and do not always require an explicit transaction. Repositories can manage per-operation transactions according to Spring Data or persistence technology mechanisms.

If a use case needs consistent reads across multiple database operations, you can use:

~~~java
@QueryMapping
@Transactional(readOnly = true)
public Account account(@Argument("id") UUID id) {
    return accountService.findAccountWithDetails(id);
}
~~~

`readOnly = true` is a hint to the transaction manager and persistence provider. Depending on the platform, it may help optimize or restrict certain write operations, but it should not be treated as a security mechanism guaranteeing writes cannot happen.

If nested fields are resolved by other methods, the root Query's transaction still ends when the root method returns. Obtaining a consistent snapshot for the entire object graph requires a more deliberate strategy.

## 10. Transaction Propagation

Propagation determines how a transactional method behaves when a transaction already exists.

| Propagation | Behavior |
| --- | --- |
| `REQUIRED` | Joins the current transaction; creates a new one if none exists |
| `REQUIRES_NEW` | Suspends the current transaction and creates an independent transaction |
| `SUPPORTS` | Joins if a transaction exists; otherwise executes non-transactionally |

`REQUIRED` is the default. When a resolver has opened a transaction and calls a service method also annotated with `@Transactional`, the service typically joins the same transaction.

`REQUIRES_NEW` is useful when an operation needs to commit independently. However, if the outer transaction rolls back, the committed inner transaction still retains its results. That can break the desired atomicity of business state.

Example:

~~~java
@Transactional
public void placeOrder(PlaceOrderInput input) {
    orderRepository.save(Order.pending(input));
    auditService.recordAttempt(input);
    inventoryService.reserve(input.items());
}
~~~

If `auditService.recordAttempt` uses `REQUIRES_NEW`, the audit record can commit even when reserving inventory subsequently fails and the order transaction rolls back. This may be desirable when auditing must record every attempt, but it must be an intentional business decision.

## 11. Isolation, Timeout, and Read-Only

Besides propagation, `@Transactional` can declare:

- `isolation`: the isolation level for a new transaction.
- `timeout`: time limit for the transaction as supported by the transaction manager.
- `readOnly`: hint for a read-only transaction.
- `rollbackFor` and `noRollbackFor`: exception-based rollback rules.

Example:

~~~java
@Transactional(
        timeout = 5,
        isolation = Isolation.READ_COMMITTED
)
public Order confirmOrder(UUID orderId) {
    // Read and update order status.
}
~~~

Do not increase the isolation level or shorten timeouts arbitrarily. High isolation can increase lock contention and reduce throughput; short timeouts can cause valid use cases to fail when the database is under heavy load.

Choose these attributes based on consistency requirements and the characteristics of the database in use.

## 12. Rollback and GraphQL Error Handling

By default, Spring rolls back a transaction when a method terminates with a `RuntimeException` or `Error`. Checked exceptions do not trigger rollback by default unless additional rules are declared.

Example:

~~~java
@Transactional(rollbackFor = PaymentRejectedException.class)
public Order payOrder(UUID orderId) throws PaymentRejectedException {
    Order order = orderRepository.findById(orderId).orElseThrow();
    paymentService.authorize(order);
    return order.markPaid();
}
~~~

If `PaymentRejectedException` is a checked exception, `rollbackFor` instructs Spring to roll back when that exception escapes the method.

Spring GraphQL can translate exceptions from resolvers into GraphQL errors. Response translation occurs after the exception passes through the method's transaction interceptor. Once the exception escapes the transactional method, the transaction interceptor has the opportunity to apply rollback rules before GraphQL handles the error.

One important detail: if code catches an exception inside the method and returns normally, the transaction interceptor sees the method succeed and may commit.

~~~java
@Transactional
public Order placeOrder(PlaceOrderInput input) {
    Order order = orderRepository.save(Order.pending(input));

    try {
        inventoryService.reserve(input.items());
    }
    catch (InsufficientStockException exception) {
        // If returning normally, the transaction may commit.
        return order.markRejected();
    }

    return order.confirm();
}
~~~

If business logic requires a rollback, let the appropriate exception escape the method or mark the transaction rollback-only as needed. Do not assume that a GraphQL error object or a `DataFetcherResult` containing errors will automatically roll back a transaction; to the transaction interceptor, that can appear as a normal return value.

## 13. Spring AOP Proxies and Self-Invocation

In default proxy mode, `@Transactional` works when calls pass through a Spring proxy. If a method calls another transactional method on the same instance via `this`, that internal call bypasses the proxy.

Example:

~~~java
@Service
class OrderService {

    public Order placeOrder(PlaceOrderInput input) {
        return createOrder(input);
    }

    @Transactional
    public Order createOrder(PlaceOrderInput input) {
        // ...
        return orderRepository.save(Order.pending(input));
    }
}
~~~

If `placeOrder` calls `createOrder` directly on the same object, the annotation may not be applied to that internal call.

A clear way to structure this is to call the transactional method from a separate Spring bean:

~~~java
@Service
class OrderFacade {

    private final OrderWriter orderWriter;

    OrderFacade(OrderWriter orderWriter) {
        this.orderWriter = orderWriter;
    }

    public Order placeOrder(PlaceOrderInput input) {
        return orderWriter.createOrder(input);
    }
}

@Service
class OrderWriter {

    @Transactional
    public Order createOrder(PlaceOrderInput input) {
        // ...
        return orderRepository.save(Order.pending(input));
    }
}
~~~

Use proxy-managed methods, typically public methods on Spring beans. Do not instantiate services manually with `new` when transaction interception is required.

## 14. Imperative Transactions and Reactive Transactions

Spring supports two primary transaction models:

| Model | Transaction Manager | Context |
| --- | --- | --- |
| Imperative | `PlatformTransactionManager` | Typically bound to the current thread |
| Reactive | `ReactiveTransactionManager` | Bound to the Reactor Context |

For methods returning regular objects, Spring uses imperative transactions. For methods returning reactive types such as `Mono` or `Flux`, Spring can apply reactive transactions if an appropriate reactive transaction manager is configured.

Reactive service example:

~~~java
@Service
class ReactiveOrderService {

    private final ReactiveOrderRepository orderRepository;

    ReactiveOrderService(ReactiveOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Mono<Order> confirmOrder(UUID orderId) {
        return orderRepository.findById(orderId)
                .flatMap(order -> {
                    order.confirm();
                    return orderRepository.save(order);
                });
    }
}
~~~

A reactive transaction is attached to the publisher and runs inside the Reactor Context when the publisher is subscribed to. Database operations participating in the transaction must remain within the same reactive pipeline/context.

Do not use blocking JPA/JDBC inside a reactive pipeline and expect imperative transactions to propagate automatically across schedulers. For reactive data access, use reactive repositories and the corresponding `ReactiveTransactionManager`.

## 15. Transaction Boundaries with Subscriptions

A Subscription is a long-lived operation that can emit many events. You should not open a single database transaction for the entire lifetime of a subscription.

If a resolver returns a `Flux` that never completes and a transaction wraps the publisher, the transaction can hold resources for far too long. This causes prolonged locks, connection pool exhaustion, and difficult recovery when clients disconnect.

Instead, separate responsibilities:

- The subscription resolver is responsible for subscribing to the publisher and managing the stream.
- Each event processing step or state update uses its own short transaction.
- Do not keep a database transaction open while waiting for events from a broker or client.
- Handle cancellation and publisher cleanup according to the subscription's lifecycle.

If an event needs to read a consistent snapshot of data, execute that query inside a short transaction when processing the event and then emit the resulting DTO.

## 16. Transactions Spanning the Entire GraphQL Request

It is possible to have a single transaction for the entire request execution so multiple DataFetchers participate in one unit of work. This is an advanced strategy, not the default behavior of Spring for GraphQL.

With an imperative transaction manager, transactions typically rely on thread-bound state (`ThreadLocal`). Therefore, for all DataFetchers to join the same transaction, the execution strategy must run DataFetchers sequentially on the same thread.

Spring for GraphQL mentions `AsyncSerialExecutionStrategy` as a starting point for building a sequential execution strategy. It can be implemented using GraphQL Java `Instrumentation` or a custom `ExecutionStrategy` to open a transaction before the first DataFetcher and commit/roll back after the entire unit of work finishes.

Trade-offs of this approach:

- Multiple independent fields lose the ability to execute in parallel.
- The transaction may remain open for a long time while the server resolves the entire object graph.
- Database connections and locks are held longer.
- An error in a nested field can roll back a broad scope of work.
- Transaction cleanup and error propagation to the GraphQL response must be handled carefully.

Only choose request-wide transactions when business requirements truly demand consistency across multiple resolvers and you have evaluated the impact on concurrency, latency, and resource usage.

For most mutations, a transactional resolver/use-case method with a well-defined boundary is easier to operate and test.

## 17. Database Transactions Do Not Cover External Services

A database transaction only controls resources participating in the same transaction manager. It does not automatically roll back:

- HTTP requests already sent to a payment provider.
- Emails already sent.
- Messages already published to a broker.
- Files already written to object storage.
- Operations on another database using an independent transaction manager.

For example, if a database transaction creates an order and calls a payment provider successfully, and then the database rolls back, the payment provider does not automatically reverse the charge.

For workflows spanning multiple systems, consider:

- Transactional outbox to record events in the same database transaction and publish after commit.
- Sagas or compensating actions for multi-service workflows.
- Idempotency keys so retries do not produce duplicate side effects.
- Intermediate business states such as `PENDING`, `CONFIRMED`, `FAILED`.

Do not hold a database transaction open while waiting on a long HTTP call without a specific reason. That holds connections and locks without providing distributed atomicity.

## 18. Testing Transaction Boundaries

Both success and rollback cases must be tested. A service integration test can verify that database changes are absent after a business step throws an exception.

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderTransactionTests {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void shouldRollbackOrderWhenReservationFails() {
        PlaceOrderInput input = new PlaceOrderInput(
                "request-rollback-1",
                List.of(new OrderItemInput("book-42", 1000))
        );

        assertThatThrownBy(() -> orderService.placeOrder(input))
                .isInstanceOf(InsufficientStockException.class);

        assertThat(orderRepository.findByReference("request-rollback-1"))
                .isEmpty();
    }
}
~~~

This test assumes `OrderService.placeOrder` has `@Transactional`, `inventoryService.reserve` throws `InsufficientStockException`, and the repository queries by reference. Do not annotate the test itself with `@Transactional` at the test level if you want to observe the outcome after the service transaction has independently rolled back or committed.

For GraphQL integration tests, send the Mutation via `GraphQlTester` or `HttpGraphQlTester`, verify the response contains the error per contract, and then query the repository to confirm no data was committed.

Additional checks worth testing:

- Successful mutation persists both the order and order lines.
- A failed database step rolls back preceding steps.
- Nested `@SchemaMapping` has its own transaction if configured.
- Two root mutation fields are not mistakenly assumed to share one transaction.
- `REQUIRES_NEW` still commits when the outer transaction rolls back, if that is the expected behavior.
- Checked exceptions roll back when `rollbackFor` is specified.
- Reactive transactions roll back when the publisher emits an error.
- Subscription cancellation does not leave transactions or connections open.

## 19. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Mutation saves partial data | Each repository call commits individually or boundary is too narrow | Wrap the database steps inside a single resolver/use-case transaction |
| Nested field reads inconsistent data | Root resolver's transaction ended before the nested resolver ran | Design projections/service queries or an appropriate boundary for nested fields |
| Two root Mutation fields do not roll back together | Each resolver has its own transaction | Use a single business mutation coordinating all steps needing atomicity |
| `@Transactional` has no effect | Method does not go through a Spring proxy or transaction management is not enabled | Check bean, proxy, and transaction manager |
| Exception produces GraphQL error but data still commits | Exception was caught and method returned normally | Let the exception escape or mark rollback-only |
| Checked exception does not roll back | Default rollback does not apply to checked exceptions | Declare `rollbackFor` or configure rollback rules |
| Self-invocation does not open a transaction | Internal call bypasses the proxy | Extract the method to another Spring bean |
| DataLoader runs outside the root transaction | Batch is dispatched after the root resolver returns | Place the boundary on the batch resolver/service |
| Reactive transaction does not wrap the query | Wrong transaction manager used or publisher left Reactor Context | Use `ReactiveTransactionManager` and keep the pipeline reactive |
| Subscription holds database connections for too long | Transaction wraps a long-lived publisher | Use short transactions per event |
| Payment call succeeds while order rolls back | External service does not participate in the database transaction | Use an outbox, saga, or compensation |
| Rollback test is unreliable | Test has an outer transaction or asserts inside the same transaction | Check state using an independent transaction after the service finishes |

## 20. Process for Choosing a Transaction Boundary

When designing a GraphQL resolver, follow these steps in order:

1. **Identify the unit of work.** List the data changes that must commit or roll back together.
2. **Choose the entry point.** Use a resolver method or application service as the primary transaction boundary.
3. **Keep transactions short.** Wrap only the database operations that require atomicity.
4. **Distinguish root and nested fields.** Do not assume the root resolver's transaction extends across nested resolvers or DataLoader.
5. **Design multi-Mutation flows.** If multiple steps need atomicity, combine them into one use-case/mutation method.
6. **Choose the transaction manager.** Use `PlatformTransactionManager` for imperative flows or `ReactiveTransactionManager` for reactive pipelines.
7. **Define rollback rules.** Review runtime exceptions, checked exceptions, and any caught exceptions.
8. **Verify proxies.** Ensure transactional calls pass through a Spring bean proxy.
9. **Isolate external side effects.** Use an outbox/saga when coordinating the database with external systems.
10. **Test commit/rollback.** Verify database state after the method or GraphQL operation completes.

## 21. Summary

GraphQL does not automatically define transaction semantics. In Spring for GraphQL, a clean way to control transactions is placing `@Transactional` on a `@MutationMapping` or `@SchemaMapping` method. The transaction starts when the method is invoked and ends when the method finishes; nested resolvers and DataLoader may run outside that boundary.

When multiple database operations must be atomic, group them into a single transactional resolver or application service method. Multiple root Mutation fields execute sequentially but do not inherently share a transaction. Request-wide transactions are an advanced solution requiring control over the execution strategy and can reduce concurrency. For reactive services, use a reactive transaction manager and Reactor Context; for Subscriptions, avoid holding transactions across the stream. Finally, test rollback by inspecting database state after the transaction ends and handle external side effects with an outbox or saga when necessary.

## References

- [Spring for GraphQL – Data Integration: Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [GraphQL Specification – Execution and Serial Mutation Fields](https://spec.graphql.org/October2021/#sec-Normal-and-Serial-Execution)

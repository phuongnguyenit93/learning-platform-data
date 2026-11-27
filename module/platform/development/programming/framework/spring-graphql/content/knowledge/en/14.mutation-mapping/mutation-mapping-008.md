# Mutation Transactions

GraphQL mutations are used to change system data or state. A realistic mutation often comprises multiple related steps: validating input data, reading current state, checking business preconditions, writing one or more records, and producing the response. If one write step succeeds while a subsequent step fails, data can end up in an inconsistent state. A **database transaction** groups operations belonging to the same business workflow into an atomic unit: either all commit together or all roll back together.

In Spring for GraphQL, the **@MutationMapping** annotation only maps a Mutation root field to a Java method. It does not open a transaction on its own. To ensure multiple persistence operations execute within one transaction, applications typically define transaction boundaries on service methods using Spring's **@Transactional**.

## Mutations and Transactions Solve Different Problems

GraphQL defines how clients ask the server to perform a data-modifying operation. Database transactions define how the system guarantees consistency when executing storage operations. The two concepts work together without replacing each other:

- **@MutationMapping** identifies the method handling a mutation field.
- The service orchestrates the use case and invokes repositories or data systems.
- **@Transactional** defines the transaction scope managed by Spring.
- The transaction manager coordinates commit or rollback across the resources it manages.

For example, placing an order requires decrementing inventory and creating an order. Both changes must succeed together. If inventory was decremented but order creation fails, the transaction must roll back so inventory returns to its original state.

## GraphQL Executes Mutations Serially

According to GraphQL execution rules, top-level fields in a Mutation operation execute serially in the order they appear in the selection set. This rule ensures mutation fields within the same operation do not run concurrently with each other.

For example, the client sends:

~~~graphql
mutation {
  reserve: reserveStock(productId: "p-10", quantity: 2) {
    id
  }
  create: createOrder(productId: "p-10", quantity: 2) {
    id
  }
}
~~~

The `reserveStock` field runs before `createOrder`. However, **serial execution does not mean the entire operation automatically runs inside one database transaction**. If each resolver calls a service with its own transaction, the first field's transaction may commit before the second field begins. If the second field fails, the already-committed transaction of the first field will not roll back automatically.

Therefore, design a single mutation field to represent a complete business use case. If placing an order requires checking inventory, decrementing stock, and creating an order, place those steps into one transactional service method rather than asking clients to coordinate multiple mutation fields.

## Defining a Schema for a Business Mutation

Example schema for placing an order:

~~~graphql
type Query {
  order(id: ID!): Order
}

type Mutation {
  placeOrder(input: PlaceOrderInput!): OrderReceipt!
}

input PlaceOrderInput {
  productId: ID!
  quantity: Int!
  requestId: ID!
}

type OrderReceipt {
  orderId: ID!
  productId: ID!
  quantity: Int!
  status: String!
}

type Order {
  id: ID!
  status: String!
}
~~~

`PlaceOrderInput` groups the use case's input data. `requestId` can serve as an idempotency key to detect duplicate requests. `OrderReceipt` is an output DTO describing the created outcome. Output DTOs let the controller return needed data without depending on persistence entities or ORM lazy relationships.

Client mutation operation:

~~~graphql
mutation PlaceOrder($input: PlaceOrderInput!) {
  placeOrder(input: $input) {
    orderId
    productId
    quantity
    status
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "productId": "p-10",
    "quantity": 2,
    "requestId": "req-2025-0001"
  }
}
~~~

## Placing Transaction Boundaries in the Service

A service method should wrap all data operations that must succeed or fail together. Example:

~~~java
@Service
public class OrderService {

    private final ProductRepository productRepository;
    private final OrderRepository orderRepository;

    public OrderService(
            ProductRepository productRepository,
            OrderRepository orderRepository) {
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderReceipt placeOrder(PlaceOrderInput input) {
        Product product = productRepository.findById(input.productId())
                .orElseThrow(() -> new ProductNotFoundException(input.productId()));

        if (input.quantity() <= 0) {
            throw new InvalidOrderException("Quantity must be greater than 0");
        }

        if (product.getAvailableQuantity() < input.quantity()) {
            throw new InsufficientStockException(product.getId());
        }

        product.decreaseAvailableQuantity(input.quantity());

        Order order = Order.create(
                product.getId(),
                input.quantity(),
                OrderStatus.CREATED);

        Order savedOrder = orderRepository.save(order);

        return new OrderReceipt(
                savedOrder.getId(),
                product.getId(),
                input.quantity(),
                savedOrder.getStatus().name());
    }
}
~~~

When `placeOrder` is invoked through Spring's transaction proxy, Spring starts a transaction before executing the method body. Repository operations participate in the same transaction manager. If the method exits normally, the transaction commits. If an exception matching the rollback rules escapes the method, the transaction rolls back.

The controller simply forwards the input to the service:

~~~java
@Controller
public class OrderMutationController {

    private final OrderService orderService;

    public OrderMutationController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public OrderReceipt placeOrder(@Argument PlaceOrderInput input) {
        return orderService.placeOrder(input);
    }
}
~~~

`@MutationMapping` does not need to manage commit or rollback itself. The transaction boundary sits on `OrderService.placeOrder`, which has full business context to decide which operations must be atomic.

## When Do Transactions Open and Close?

With imperative transaction management, Spring typically performs these steps:

1. The call passes through a proxy created by the transaction infrastructure.
2. The transaction manager begins a new transaction or joins an existing one according to propagation.
3. The service executes read and write operations.
4. If the method returns normally, Spring commits the transaction.
5. If an exception triggering a rollback rule escapes the method, Spring rolls back the transaction and rethrows the exception to the caller.

Overview flow:

~~~mermaid
sequenceDiagram
    participant C as GraphQL Client
    participant G as GraphQL Runtime
    participant R as Mutation Resolver
    participant S as Order Service
    participant T as Transaction Manager
    participant DB as Database

    C->>G: mutation placeOrder
    G->>R: Call resolver
    R->>S: placeOrder(input)
    S->>T: Start transaction
    T->>DB: Open transaction
    S->>DB: Read product and inventory
    S->>DB: Update inventory
    S->>DB: Save order
    S->>T: Method ends
    T->>DB: Commit
    S-->>R: OrderReceipt
    R-->>G: Field result
    G-->>C: GraphQL response
~~~

If saving the order throws an exception before the service method finishes, the path switches to rollback instead of commit. The transaction manager only coordinates resources configured to participate in its transaction; never assume external systems automatically participate in the same transaction.

## Default Rollback Rules

With Spring's `@Transactional`, transactions roll back by default when a method terminates with a `RuntimeException` or `Error`. Checked exceptions do not trigger a rollback under default rules.

Example requiring rollback for checked exceptions too:

~~~java
@Transactional(rollbackFor = Exception.class)
public OrderReceipt placeOrder(PlaceOrderInput input) throws OrderProcessingException {
    // Read and write operations within the same transaction
}
~~~

You can use `noRollbackFor` for exceptions that should not roll back, though do so carefully because it can commit partial changes even when business logic signals an error.

Key points to remember:

- Exceptions must escape the transaction boundary for the interceptor to apply rollback rules.
- If code catches an exception, ignores it, and returns normally, Spring normally commits the transaction.
- If you must mark rollback while catching an exception, use the rollback-only mechanism; prefer letting appropriate exceptions cross the boundary when design permits.
- Validation should run before writing data to avoid unnecessarily expanding the scope of changes.

## GraphQL Errors and Database Rollbacks Are Not the Same Concept

A GraphQL response can contain both `data` and `errors`. The presence of `errors` in a response does not prove a transaction rolled back. Transactions decide commit or rollback based on how exceptions cross the transaction boundary and rollback rules.

For instance, if a resolver calls a transactional service, the service throws `InsufficientStockException`, Spring rolls back the transaction, and the error-handling mechanism turns the exception into a GraphQL error. The client may then receive:

~~~json
{
  "data": {
    "placeOrder": null
  },
  "errors": [
    {
      "message": "Insufficient stock",
      "path": ["placeOrder"]
    }
  ]
}
~~~

Conversely, if the service catches an exception after writing data and returns a `success=false` payload, the method completes normally and the transaction may commit. If an error payload must guarantee no changes are saved, ensure no writes occur before detecting the error or explicitly mark the transaction rollback-only.

Translating an exception into a GraphQL message via `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler` after it leaves the service transaction does not alter the rollback decision already executed by the transaction interceptor. Place exception handling in the right layer and verify database state after errors in tests.

## A Single Mutation Operation with Multiple Fields

GraphQL allows a single Mutation operation to contain multiple top-level fields. Those fields run serially, but their transactions depend on how the application defines boundaries:

~~~graphql
mutation {
  first: createDraft(input: { title: "GraphQL Basics" }) {
    id
  }
  second: publishBook(id: "book-101") {
    id
  }
}
~~~

If `createDraft` and `publishBook` are separate resolvers, each calling a `@Transactional` service method, each call normally runs in its own transaction. If the first field commits and the second fails, changes from the first field remain persisted.

When business rules require multiple steps to be atomic, create a single mutation field like `createAndPublishBook` and a single service method enclosing the use case. Do not rely on clients placing multiple fields in one operation to form a shared transaction.

If you genuinely need a transaction spanning an entire GraphQL execution, that requires dedicated execution/transport-level integration with careful design around start time, completion, error handling, and async publishers. It is not the default behavior of `@MutationMapping`.

## Propagation and Nested Service Calls

Spring transaction propagation determines whether a method joins an existing transaction or creates another one. The default is `Propagation.REQUIRED`:

- If no transaction exists, Spring creates a new one.
- If a compatible transaction already exists, the method joins that transaction.

Example:

~~~java
@Service
public class OrderService {

    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    public OrderService(
            InventoryService inventoryService,
            OrderRepository orderRepository) {
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Order createOrder(PlaceOrderInput input) {
        inventoryService.reserve(input.productId(), input.quantity());
        return orderRepository.save(Order.create(input));
    }
}

@Service
public class InventoryService {

    @Transactional
    public void reserve(String productId, int quantity) {
        // Read and update inventory
    }
}
~~~

When `InventoryService.reserve` is called through a bean proxy with default propagation, it joins `OrderService`'s active transaction. If saving the `Order` fails, the inventory update rolls back in the same transaction.

`REQUIRES_NEW` creates an independent transaction and suspends the current one. If used for an operation that ought to roll back with the order, that operation's data may commit separately and will not roll back alongside the outer transaction. Only use non-default propagation when you clearly understand the consistency requirements.

Transaction annotations are proxy-based in standard Spring setups. Calling another transactional method within the same object via self-invocation typically bypasses the proxy, so annotations on internally called methods may not create a new boundary as expected. Splitting logic into separate service beans and invoking via injected dependencies is cleaner and more predictable.

## Isolation, Locking, and Concurrent Updates

Transactions alone do not solve every data contention issue. Two concurrent order requests might both read available stock as 5 and each order 4 items. Without protection, both could exceed available inventory.

Common techniques include:

- **Optimistic locking:** use a version column and JPA `@Version` to detect conflicting updates at commit time.
- **Pessimistic locking:** lock records while the transaction processes, such as querying with an appropriate lock mode.
- **Atomic update:** issue a conditional update statement like `UPDATE product SET available = available - :qty WHERE id = :id AND available >= :qty`, then inspect the updated row count.
- **Isolation level:** pick an isolation level suited to read/write requirements and the database; higher levels can increase cost or contention.

Conditional atomic updates work well for inventory because checking and decrementing happen in a single statement. Still, handle the case where zero rows are updated—such as a missing product or insufficient stock.

Do not mechanically raise the isolation level to fix every concurrency bug. Identify the business invariant, choose an appropriate locking or optimistic concurrency strategy, and test with multiple concurrent transactions.

## Transactions and External Side Effects

Database transactions typically guarantee atomicity only for resources managed by the transaction manager. If a service both writes to the database and makes an HTTP call to a payment provider or sends a message to a broker, a database rollback cannot undo actions already completed in external systems.

Example:

1. Write the order to the database.
2. Call the payment provider and successfully charge the card.
3. Write payment details to the database, which fails.

Rolling back the database does not refund the charge at the payment provider. For distributed workflows, design appropriate patterns:

- **Transactional outbox:** write business data and outbox events in the same database transaction; a separate process reads the outbox and dispatches events after commit.
- **Saga:** split the workflow into local transactions, each paired with a compensating action if a later step fails.
- **Idempotency:** use a unique request key so repeated requests do not create duplicate orders or double charges.
- **Controlled retries:** only retry safely repeatable operations with bounded attempts.

Do not hold a database transaction open waiting on a slow HTTP call if the workflow can be separated. Long-running transactions prolong locks and degrade throughput.

## Reactive Transactions with Spring WebFlux

If the application uses WebFlux and reactive repositories like R2DBC, services can return `Mono` or `Flux`. Spring supports reactive transactions via `ReactiveTransactionManager`. When `@Transactional` is placed on a method returning a reactive publisher, the transaction binds to subscription and the Reactor context rather than thread-locals like imperative transactions.

Reactive service example:

~~~java
@Service
public class ReactiveOrderService {

    private final ReactiveProductRepository products;
    private final ReactiveOrderRepository orders;

    public ReactiveOrderService(
            ReactiveProductRepository products,
            ReactiveOrderRepository orders) {
        this.products = products;
        this.orders = orders;
    }

    @Transactional
    public Mono<OrderReceipt> placeOrder(PlaceOrderInput input) {
        return products.findById(input.productId())
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(input.productId())))
                .flatMap(product -> {
                    if (input.quantity() <= 0
                            || product.getAvailableQuantity() < input.quantity()) {
                        return Mono.error(
                                new InsufficientStockException(product.getId()));
                    }

                    product.decreaseAvailableQuantity(input.quantity());
                    return products.save(product)
                            .then(orders.save(Order.create(input, product)))
                            .map(OrderReceipt::from);
                });
    }
}
~~~

For reactive transactions to work, configure a `ReactiveTransactionManager` matching your data source, such as R2DBC. Operations must stay inside the same reactive pipeline, and errors must propagate so the transaction can roll back.

Do not call `block()` inside the pipeline or offload work to threads without the Reactor context if they are expected to share the reactive transaction. Likewise, do not use an imperative transaction manager for a reactive flow expecting the transaction to follow the publisher. If using blocking JDBC/JPA, choose the appropriate imperative model or isolate blocking parts explicitly; never mix two transaction models without deliberate design.

## Testing Mutation Transactions

A transaction test should verify both the GraphQL response and persisted state after the mutation finishes. You can use `GraphQlTester` to invoke the operation:

~~~java
graphQlTester.document("""
        mutation PlaceOrder($input: PlaceOrderInput!) {
            placeOrder(input: $input) {
                orderId
                status
            }
        }
        """)
    .variable("input", Map.of(
            "productId", "p-10",
            "quantity", 2,
            "requestId", "req-2025-0001"))
    .execute()
    .path("placeOrder.status")
    .entity(String.class)
    .isEqualTo("CREATED");
~~~

In addition to the happy path, test:

| Scenario | What to verify |
| --- | --- |
| Product does not exist | No order created and no inventory change |
| Insufficient stock | Stock is not decremented and no order is created |
| Saving order fails after stock decrement | Stock change is rolled back |
| Checked exception with `rollbackFor` | Transaction rolls back per configuration |
| Client resends same `requestId` | No duplicate business side effects if API supports idempotency |
| Two concurrent order requests | Inventory invariant remains intact |
| Mutation calls external systems | Verify outbox, retries, or compensating actions per design |

To test real rollbacks, the test must inspect the database after the service transaction has finished. Be careful with `@Transactional` on test methods: a transaction wrapping the test itself rolls back test data at test completion, hiding whether the mutation's inner transaction committed or rolled back. For such cases, use explicit transaction management in tests or inspect from an independent transaction after the request completes.

## Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Mutation returns an error yet data changed | Exception was caught and turned into a normal payload inside the transaction | Do not swallow exceptions if rollback is needed; mark rollback-only when appropriate |
| First step commits, second step fails | Each resolver/service has its own transaction | Combine steps into a single use case and single transaction |
| `@Transactional` has no effect | Method called via internal self-invocation or non-proxied bean | Invoke through a Spring bean proxy and use proper visibility |
| Checked exception does not roll back | Default rule only rolls back `RuntimeException` and `Error` | Declare `rollbackFor` when needed |
| Negative inventory under concurrent requests | Missing locks or atomic updates | Use optimistic/pessimistic locking or atomic updates |
| Email/message sent before database rollback | External system is outside local transaction | Use outbox, saga, or compensating actions |
| Reactive transaction fails to roll back | Wrong transaction manager or broken reactive pipeline | Use `ReactiveTransactionManager` and keep errors inside the publisher |
| Lazy field errors after mutation | Transaction closes before GraphQL resolves child fields | Return DTOs/projections with needed data or design explicit fetching |

## Principles for Designing Mutation Transactions

When building mutations in Spring for GraphQL, apply these principles:

1. **Design mutations around use cases.** Each field should represent a complete business action.
2. **Place transactions on services.** Group data operations that must succeed or fail together into one `@Transactional` method.
3. **Understand rollback rules.** Distinguish `RuntimeException`, checked exceptions, and caught exceptions.
4. **Do not confuse GraphQL ordering with transactions.** Mutation root fields run serially, yet do not automatically share a single transaction.
5. **Control concurrency.** Protect invariants with locking, versions, or atomic updates.
6. **Decouple distributed side effects.** Use outbox or sagas when coordinating databases with external systems.
7. **Keep reactive transactions consistent.** Use the proper transaction manager and never block the pipeline.
8. **Return appropriate DTOs.** Do not rely on lazy entities after the transaction closes.
9. **Test database state.** Verify both commits and rollbacks, not just GraphQL responses.

A mutation transaction is the boundary that guarantees atomicity for a state-changing use case. Spring for GraphQL maps mutation fields to resolvers; `@Transactional` service methods coordinate transactions; and the transaction manager commits or rolls back based on execution outcomes. By designing mutations around business workflows, controlling errors and concurrency, and decoupling external side effects with outbox or sagas, your API keeps data consistent even when a processing step fails.

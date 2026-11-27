# Do Not Put Business Logic in Resolvers

In Spring for GraphQL, a resolver (data fetcher) connects a field in the GraphQL schema to the Java code that handles it. A resolver should accept arguments, principals, or parent objects, invoke the application layer, and convert results into a response matching the schema. Business rules—such as pricing calculations, stock checks, order state transitions, money transfers, or ownership verification—belong in the application/domain layer.

Structuring code this way keeps business logic independent of GraphQL. The same use case can be invoked from a GraphQL resolver, a REST controller, a message consumer, or a scheduled job without duplicating rules. Resolvers also become easier to test because they handle only binding and orchestration.

## 1. What Is the Role of a Resolver?

Spring for GraphQL uses annotated controllers to map Java methods to `DataFetcher` instances for schema fields:

| Annotation | Mapped Field |
|---|---|
| `@QueryMapping` | Field on the `Query` type. |
| `@MutationMapping` | Field on the `Mutation` type. |
| `@SubscriptionMapping` | Field on the `Subscription` type. |
| `@SchemaMapping` | Field on a specific object type. |
| `@BatchMapping` | Field resolved across a batch of parent objects. |

Example:

```java
@Controller
class BookController {

    @QueryMapping
    Book bookById(@Argument String id) {
        // Spring for GraphQL registers this method as a DataFetcher.
        return ...;
    }
}
```

`@QueryMapping`, `@MutationMapping`, and `@SubscriptionMapping` are shortcuts for `@SchemaMapping` targeting the three root operation types. They declare where GraphQL fields are resolved; the annotations themselves do not require placing business logic inside controllers.

## 2. Why Shouldn't Business Logic Live in Resolvers?

Resolvers sit at the GraphQL boundary. They know about the GraphQL schema, argument binding, parent objects, selection sets, and GraphQL context. Cramming all business rules into resolvers causes several problems:

- **Transport coupling:** logic only runs through GraphQL; REST or message consumers must call back into it or duplicate code.
- **Hard to test:** testing a pricing rule may require booting GraphQL execution, the schema, and controller context.
- **Hard to control transactions:** repository calls scattered across resolvers and field mappings can create tiny transactions that fail to cover a single business operation properly.
- **Easy to violate invariants:** the same rule may be implemented inconsistently across multiple resolvers.
- **Hard to evolve the schema:** renaming fields or changing input structure forces edits to business logic.
- **Inconsistent error handling:** resolvers may format errors ad hoc, representing the same business failure differently across APIs.
- **Prone to N+1:** field resolvers independently query data for each parent object without batch loading.

Resolvers can perform simple mapping, type conversions at the boundary, or invoke use cases. They should not make business decisions themselves.

## 3. Separating Responsibilities Across Layers

A common layered organization:

```text
GraphQL client
      |
      v
GraphQL schema (SDL)
      |
      v
Resolver / @Controller
  - bind @Argument
  - retrieve Principal / context
  - invoke use case
  - map result to GraphQL DTO
      |
      v
Application service / use case
  - orchestrate one business operation
  - verify permissions and preconditions
  - open transaction
  - call domain and repository
      |
      v
Domain model / domain service
  - invariants
  - calculation rules
  - valid state transitions
      |
      v
Repository / infrastructure
  - persist and read data
  - integrate with database or external systems
```

| Layer | Responsibility | Example |
|---|---|---|
| GraphQL schema | API contract, input/output types, nullability | `PlaceOrderInput`, `Order`. |
| Resolver | Binding and delegation | Extract user from `Principal`, call `PlaceOrderUseCase`. |
| Application | Use-case orchestration and transactions | Place order, transfer money, refund order. |
| Domain | Business rules and invariants | Quantity must be positive, closed orders cannot be re-placed. |
| Infrastructure | Data access and integrations | JPA repository, R2DBC, HTTP client. |

Not every project needs separate packages or classes for every layer. What matters is that business rules have a clear owner and remain decoupled from GraphQL.

## 4. Example: Order Placement Mutation

Suppose an API lets clients place an order. Schema:

```graphql
input OrderItemInput {
    productId: ID!
    quantity: Int!
}

input PlaceOrderInput {
    customerId: ID!
    items: [OrderItemInput!]!
}

type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}

type Order {
    id: ID!
    status: String!
    totalAmount: Float!
}
```

The GraphQL schema is responsible for checking structure and types—for example, `quantity` must be an `Int`, `input` must be non-null, and `items` must be non-null. However, SDL cannot determine whether products are in stock or whether the customer is permitted to place orders.

## 5. Thin Resolvers: Only Bind Input and Invoke the Use Case

Input DTO at the GraphQL boundary:

```java
import java.util.List;

public record OrderItemInput(String productId, int quantity) {}

public record PlaceOrderInput(
    String customerId,
    List<OrderItemInput> items
) {}
```

Application-layer command with no GraphQL awareness:

```java
import java.util.List;

public record PlaceOrderCommand(
    String actorId,
    String customerId,
    List<PlaceOrderLine> lines
) {}

public record PlaceOrderLine(String productId, int quantity) {}
```

The resolver converts input into a command and invokes the use case:

```java
import java.security.Principal;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
class OrderMutationController {

    private final PlaceOrderUseCase placeOrder;

    OrderMutationController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @MutationMapping
    OrderView placeOrder(
            @Argument PlaceOrderInput input,
            Principal principal) {

        PlaceOrderCommand command = new PlaceOrderCommand(
            principal.getName(),
            input.customerId(),
            input.items().stream()
                .map(item -> new PlaceOrderLine(
                    item.productId(), item.quantity()))
                .toList()
        );

        PlaceOrderResult result = placeOrder.execute(command);
        return OrderView.from(result);
    }
}
```

The resolver does not calculate totals, check inventory, update state, or call repositories. It only converts GraphQL input into an application command, retrieves the authenticated identity, and maps the application result to a GraphQL view.

Response model at the GraphQL boundary:

```java
import java.math.BigDecimal;

public record OrderView(
    String id,
    String status,
    BigDecimal totalAmount
) {
    static OrderView from(PlaceOrderResult result) {
        return new OrderView(
            result.orderId(),
            result.status().name(),
            result.totalAmount()
        );
    }
}
```

`OrderView` is the GraphQL response model. It can evolve with the API without forcing changes to the domain aggregate.

The application result also belongs to the application layer, independent of GraphQL:

```java
public record PlaceOrderResult(
    String orderId,
    OrderStatus status,
    BigDecimal totalAmount
) {
    static PlaceOrderResult from(Order order) {
        return new PlaceOrderResult(order.id(), order.status(), order.total());
    }
}
```

## 6. Application Services Orchestrate Business Operations

The application service receives the command and coordinates the steps of a use case:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class PlaceOrderUseCase {

    private final CustomerRepository customers;
    private final ProductRepository products;
    private final OrderRepository orders;
    private final PricingPolicy pricingPolicy;

    PlaceOrderUseCase(
            CustomerRepository customers,
            ProductRepository products,
            OrderRepository orders,
            PricingPolicy pricingPolicy) {
        this.customers = customers;
        this.products = products;
        this.orders = orders;
        this.pricingPolicy = pricingPolicy;
    }

    @Transactional
    public PlaceOrderResult execute(PlaceOrderCommand command) {
        Customer customer = customers.findById(command.customerId())
            .orElseThrow(() -> new CustomerNotFoundException(command.customerId()));

        if (!customer.canBeManagedBy(command.actorId())) {
            throw new OrderNotAllowedException();
        }

        Set<String> productIds = command.lines().stream()
            .map(PlaceOrderLine::productId)
            .collect(Collectors.toSet());

        Map<String, Product> productsById = products.findAllById(productIds)
            .stream()
            .collect(Collectors.toMap(Product::id, Function.identity()));

        List<OrderLine> lines = command.lines().stream()
            .map(line -> {
                if (line.quantity() <= 0) {
                    throw new InvalidOrderQuantityException(line.productId());
                }

                Product product = productsById.get(line.productId());
                if (product == null) {
                    throw new ProductNotFoundException(line.productId());
                }

                if (!product.isAvailableForSale()) {
                    throw new ProductUnavailableException(line.productId());
                }

                return OrderLine.create(product, line.quantity());
            })
            .toList();

        Money total = pricingPolicy.calculate(lines, customer);
        Order order = Order.place(customer, lines, total);
        orders.save(order);

        return PlaceOrderResult.from(order);
    }
}
```

This is an illustrative example; repositories, exceptions, and domain types must match the application's data model. The key point is that all order-creation steps are grouped in one use case with a single clear transaction boundary.

## 7. Place Invariants in the Domain Model

The application service orchestrates the use case; domain objects own the rules protecting their own valid state.

Example:

```java
import java.util.List;
import java.util.UUID;

public class Order {

    private final String id;
    private OrderStatus status;
    private final List<OrderLine> lines;
    private final Money total;

    private Order(
            String id,
            OrderStatus status,
            List<OrderLine> lines,
            Money total) {
        this.id = id;
        this.status = status;
        this.lines = List.copyOf(lines);
        this.total = total;
    }

    public static Order place(
            Customer customer,
            List<OrderLine> lines,
            Money total) {

        if (lines.isEmpty()) {
            throw new EmptyOrderException();
        }

        if (!customer.canPlaceOrder()) {
            throw new CustomerCannotOrderException();
        }

        return new Order(
            UUID.randomUUID().toString(),
            OrderStatus.PLACED,
            lines,
            total
        );
    }

    public void cancel() {
        if (status != OrderStatus.PLACED) {
            throw new OrderCannotBeCancelledException(id);
        }
        status = OrderStatus.CANCELLED;
    }

    public String id() { return id; }
    public OrderStatus status() { return status; }
    public Money total() { return total; }
}
```

The domain model never needs to import `@Controller`, `@MutationMapping`, `GraphQLContext`, or `GraphQLError`. Rules such as "a shipped order cannot be cancelled" must hold whether the cancellation command arrives from GraphQL, REST, a message consumer, or a batch job.

## 8. Distinguishing Input Validation from Business Validation

There are multiple distinct validation layers:

| Check Type | Appropriate Location | Example |
|---|---|---|
| GraphQL type/coercion | SDL and GraphQL Java | `quantity: Int!`, `input: PlaceOrderInput!`. |
| Input structure | DTO and Bean Validation | Product ID string must not be blank, list size is capped. |
| Business rules | Application/domain | Product is available for sale, customer is eligible, balance is sufficient. |
| Access permissions | Security/application policy | Caller is allowed to place orders for that customer. |
| Data constraints | Database | Unique constraints, foreign keys, optimistic locking. |

You can use `@Valid` on resolver arguments to validate input structure:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;

@MutationMapping
OrderView placeOrder(@Argument @Valid PlaceOrderInput input, Principal principal) {
    // bind and invoke use case
}
```

However, never rely solely on resolver validation. Use cases and domain models must enforce invariants because they may be invoked from other entry points.

## 9. Place Transactions at the Use-Case Boundary

GraphQL does not define transaction semantics. The server and application decide which units of work require atomicity and isolation.

For an order-placement mutation, a single transaction typically covers the related database operations:

1. Load customer and products.
2. Verify business conditions.
3. Create the order and order lines.
4. Update inventory or reservations in the same transaction when they share the same database/transaction manager.
5. Persist the result.

Placing `@Transactional` on the application service method aligns the transaction boundary with the use case:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TransferMoneyUseCase {

    private final AccountRepository accounts;

    TransferMoneyUseCase(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public TransferResult execute(TransferCommand command) {
        Account source = accounts.findById(command.sourceId())
            .orElseThrow(AccountNotFoundException::new);
        Account target = accounts.findById(command.targetId())
            .orElseThrow(AccountNotFoundException::new);

        source.withdraw(command.amount());
        target.deposit(command.amount());

        accounts.save(source);
        accounts.save(target);

        return new TransferResult(source.getId(), target.getId());
    }
}
```

The resolver simply calls `transferMoney.execute(command)`. Both balance changes participate in the same transaction and commit or roll back together under the transaction policy.

Spring for GraphQL also supports placing `@Transactional` directly on `@MutationMapping` methods. That wraps the controller method call in a transaction and is a valid choice when the method itself represents the use-case boundary. When business logic must be reusable independently of GraphQL, placing the transaction on the application service method is usually cleaner.

`@Transactional` operates via a Spring proxy. Consequently, calls must pass through the bean proxy; a method in the same class calling another `@Transactional` method directly (self-invocation) normally does not trigger transaction advice. By default, Spring rolls back on unchecked exceptions (`RuntimeException`) and `Error`; if a business exception is a checked exception and must roll back, declare `rollbackFor` accordingly. Verify transaction managers and propagation when a use case calls other services.

## 10. Do Not Hold a Transaction Open for the Entire GraphQL Request

GraphQL lets clients select many independent fields. Nested fields may be resolved at different times, calling multiple services or batch loaders.

Keeping a database transaction open from start to finish across an entire GraphQL request can:

- Hold connections and locks longer than necessary.
- Encompass arbitrary client-selected fields.
- Tie transaction boundaries to the selection set.
- Conflict with asynchronous/reactive data fetchers.
- Increase the risk of long transactions when fields call remote services.

Spring for GraphQL describes transaction-per-controller-method as a simple approach with a clear boundary. In a layered architecture, that same transaction boundary can be placed on the application service method called by the resolver. Request-wide transactions are an advanced technique requiring control over execution strategies, threads/contexts, and cleanup; do not adopt them as the default.

## 11. Multiple Mutations in a Single GraphQL Request

GraphQL permits a single request to contain multiple root mutation fields. Root mutations execute sequentially per GraphQL semantics, yet that does not automatically place all of them inside one database transaction.

Example:

```graphql
mutation {
    reserve: reserveInventory(input: { productId: "p-1", quantity: 2 }) {
        reservationId
    }
    create: createOrder(input: { customerId: "c-1" }) {
        id
    }
}
```

If each resolver invokes a `@Transactional` use case, each use case gets its own transaction. If `reserveInventory` succeeds while `createOrder` fails, the first transaction does not automatically roll back because of the second.

When two steps must succeed or fail together, design a single mutation/use case encompassing the entire business operation:

```graphql
type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}
```

`PlaceOrderUseCase` coordinates reservation and order creation within one transaction when all operations participate in the same transaction manager. Never rely on the client sending multiple mutation fields to form one business transaction.

## 12. Do Not Place Transactions on Nested Field Resolvers to Stitch Business Logic

Example to avoid:

```java
@Controller
class OrderController {

    @MutationMapping
    Order createOrder(@Argument OrderInput input) {
        return orderRepository.save(...);
    }

    @SchemaMapping
    @Transactional
    Customer customer(Order order) {
        return customerRepository.findById(order.customerId()).orElseThrow();
    }
}
```

`createOrder`'s transaction ends when the method returns. The nested `customer` field runs afterward and, if annotated with `@Transactional`, opens its own transaction. Two transactions do not become a single atomic unit merely because they belong to the same GraphQL response.

Let the mutation use case persist all changes requiring atomicity. Nested field resolvers should only fetch related data via query services or DataLoaders as requested by the selection set.

## 13. Separate Query Services and Command Use Cases

Read paths and write paths have different needs:

- Query services read data and support filtering, pagination, projections, and DataLoaders.
- Command use cases modify state, enforce invariants, and manage transactions.

Query resolver example:

```java
import java.security.Principal;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class OrderQueryController {

    private final OrderQueryService orderQueries;

    OrderQueryController(OrderQueryService orderQueries) {
        this.orderQueries = orderQueries;
    }

    @QueryMapping
    OrderView orderById(@Argument String id, Principal principal) {
        return orderQueries.findVisibleOrder(id, principal.getName());
    }
}
```

The query service can use projections or read models to load only the needed data:

```java
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    private final OrderReadRepository repository;

    OrderQueryService(OrderReadRepository repository) {
        this.repository = repository;
    }

    public OrderView findVisibleOrder(String orderId, String actorId) {
        return repository.findViewVisibleTo(orderId, actorId)
            .orElseThrow(OrderNotFoundException::new);
    }
}
```

Read operations typically do not need a write transaction. If business rules require a consistent snapshot or multiple read queries must share an isolation boundary, declare an appropriate read-only transaction on the query service rather than wrapping the entire GraphQL request by default.

## 14. Nested Resolvers Handle Only Field Relationships

A resolver for `Order.customer` can call a query service:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
class OrderFieldController {

    private final CustomerQueryService customers;

    OrderFieldController(CustomerQueryService customers) {
        this.customers = customers;
    }

    @SchemaMapping(typeName = "Order", field = "customer")
    CustomerView customer(Order order) {
        return customers.findById(order.customerId());
    }
}
```

This resolver does not decide whether an order can be cancelled, recalculate prices, or alter status. It only resolves the `customer` relationship to satisfy the field selected by the client.

If a query returns many orders, the resolver above can cause N+1. In that case, use `@BatchMapping` or DataLoader to load multiple customers at once. Query logic and access checks still remain in the service/repository; batch mapping simply optimizes data fetching.

## 15. Using `@BatchMapping` Without Moving Business Logic into Controllers

Batch mapping example:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class OrderFieldController {

    private final CustomerQueryService customers;

    OrderFieldController(CustomerQueryService customers) {
        this.customers = customers;
    }

    @BatchMapping(typeName = "Order", field = "customer")
    Mono<Map<Order, CustomerView>> customer(List<Order> orders) {
        Set<String> customerIds = orders.stream()
            .map(Order::customerId)
            .collect(Collectors.toSet());

        return customers.findByIds(customerIds)
            .collectMap(CustomerView::id)
            .map(byId -> {
                Map<Order, CustomerView> result = new LinkedHashMap<>();
                for (Order order : orders) {
                    CustomerView customer = byId.get(order.customerId());
                    if (customer != null) {
                        result.put(order, customer);
                    }
                }
                return result;
            });
    }
}
```

The controller collects keys and maps results back to parent objects. `CustomerQueryService` handles querying, applying tenant/visibility policies, and returning data. Never put business rules such as "upgrade the customer tier if total spend exceeds a threshold" inside a batch method.

## 16. Handle Authorization at the Right Layer

Resolvers can receive `Principal` or `@AuthenticationPrincipal` from Spring Security. However, obtaining the principal does not mean every permission check must be written manually inside each resolver.

A use case can enforce authorization at the application boundary:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CancelOrderUseCase {

    private final OrderRepository orders;

    CancelOrderUseCase(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('order:cancel')")
    @Transactional
    public OrderResult execute(String orderId, String actorId) {
        Order order = orders.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);

        if (!order.canBeManagedBy(actorId)) {
            throw new OrderNotFoundException();
        }

        order.cancel();
        return OrderResult.from(order);
    }
}
```

Method security must be enabled in Spring Security configuration. Ownership/tenant checks must still apply to the specific resource; a broad authority does not automatically guarantee a user has access to every order.

Configuration example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

The resolver extracts the actor from the authenticated principal and calls the use case. Never take `actorId` or `tenantId` from client-supplied GraphQL arguments as proof of identity.

## 17. Handling Business Errors at the GraphQL Boundary

The application/domain layer can throw semantically meaningful exceptions such as `OrderNotFoundException`, `OrderCannotBeCancelledException`, or `InsufficientStockException`. The GraphQL layer translates those exceptions into `GraphQLError` instances matching the API contract.

Example using `@ControllerAdvice`:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
class GraphQlBusinessExceptionHandler {

    @GraphQlExceptionHandler
    GraphQLError handle(
            InsufficientStockException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
            .errorType(ErrorType.BAD_REQUEST)
            .message("Insufficient stock to complete the order")
            .extensions(Map.of("code", "INSUFFICIENT_STOCK"))
            .build();
    }
}
```

`@GraphQlExceptionHandler` inside `@ControllerAdvice` applies to annotated controllers. `DataFetcherExceptionResolver` can be used for DataFetchers registered through other means.

Never make services return `GraphQLError` or import `GraphQlExceptionHandler`. Domain exceptions should express business failures independently; the GraphQL adapter decides the message, error type, path, and extensions. Never return stack traces or internal details to clients.

## 18. Do Not Make Long Remote Service Calls Inside Database Transactions

A database transaction does not automatically cover HTTP calls to external systems. If a use case opens a transaction and calls a remote payment gateway, email service, or inventory service, the transaction holds connections/locks while waiting on the network and still cannot roll back side effects already applied in the external system.

For workflows spanning multiple systems, consider:

- Persisting state and outbox events inside the same database transaction.
- Publishing events after commit via an outbox relay.
- Using sagas/process managers for multi-step workflows and compensating actions.
- Using idempotency keys to handle retries safely.
- Configuring timeouts and retry policies in integration adapters.

Do not confuse local transactions with distributed transactions. When atomicity across multiple systems is required, design corresponding protocols and failure handling.

## 19. Choosing the Right Transaction Model for Imperative vs. Reactive

With Spring MVC/JPA/JDBC, `@Transactional` typically uses an imperative transaction manager, where context is bound to the thread during the proxied method call.

With Spring WebFlux and R2DBC, use `ReactiveTransactionManager` and reactive return types such as `Mono` or `Flux`. Transaction context propagates through the Reactor Context instead of assuming every callback runs on the same thread.

Never open an imperative JPA transaction, shift work onto a reactive pipeline or another scheduler, and expect the thread-bound transaction to follow automatically. Never mix blocking repositories with reactive transactions without an explicit design.

Reactive use case example:

```java
@Service
class PlaceOrderReactiveUseCase {

    private final ReactiveOrderRepository orders;

    PlaceOrderReactiveUseCase(ReactiveOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Mono<OrderResult> execute(PlaceOrderCommand command) {
        return validateAndCreate(command)
            .flatMap(orders::save)
            .map(OrderResult::from);
    }
}
```

This example assumes the application configures a reactive transaction manager and all operations in the pipeline participate in that reactive transaction.

## 20. Testing Resolvers and Use Cases Separately

Layering helps you pick the right test type:

| Test | Target | What to Verify |
|---|---|---|
| Application service unit test | Use case/domain | Business rules, decisions, and exceptions. |
| Repository integration test | Persistence | Queries, constraints, mappings, and transactions. |
| `@GraphQlTest` | Resolver/schema | Argument binding, delegating to the right use case, response paths, and error mapping. |
| End-to-end GraphQL test | Entire application | Security, transactions, database, and GraphQL contract. |

Example testing a resolver with `GraphQlTester`:

```java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

@GraphQlTest(OrderMutationController.class)
@WithMockUser(username = "alice")
class OrderMutationControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    PlaceOrderUseCase placeOrder;

    @Test
    void delegatesToUseCaseAndReturnsOrder() {
        given(placeOrder.execute(any(PlaceOrderCommand.class)))
            .willReturn(new PlaceOrderResult(
                "order-101", OrderStatus.PLACED, new BigDecimal("125.00")
            ));

        graphQlTester.document("""
                mutation {
                    placeOrder(input: {
                        customerId: "customer-1"
                        items: [{ productId: "product-1", quantity: 1 }]
                    }) {
                        id
                        status
                        totalAmount
                    }
                }
                """)
            .execute()
            .path("placeOrder.id")
            .entity(String.class)
            .isEqualTo("order-101");

        then(placeOrder).should().execute(any(PlaceOrderCommand.class));
    }
}
```

This test verifies that the resolver forwards the request to the use case and maps the response. Inventory rules, pricing, and transactions should be tested in `PlaceOrderUseCase` tests rather than crammed into GraphQL tests.

The test imports above target Spring Boot 3.x and Spring Framework 6.2+. In Spring Boot 4.x, `@GraphQlTest`'s package moves to `org.springframework.boot.graphql.test.autoconfigure`; `@MockitoBean` belongs to `org.springframework.test.context.bean.override.mockito`.

Because the test uses `@WithMockUser`, it needs `spring-security-test` in test scope. If the project does not enable Spring Security or the resolver needs no principal, remove this annotation and supply an appropriate principal/context mechanism for your test.

## 21. Signs a Resolver Holds Too Much Business Logic

Revisit the design if a resolver exhibits any of these signs:

- Calls multiple repositories directly to orchestrate a workflow.
- Contains many `if/else` branches expressing business policies.
- Calculates prices, taxes, discounts, or commissions.
- Mutates aggregate state directly.
- Opens, commits, or rolls back transactions itself.
- Calls multiple remote services and decides compensation logic.
- Re-implements ownership checks directly across many resolvers.
- Manually formats business exceptions into `GraphQLError` across many methods.

A long resolver is not automatically wrong if most of the code is mapping. Conversely, a short resolver that calls repositories and mutates domain state directly still violates responsibility boundaries.

## 22. Common Mistakes

**Putting all logic inside `@MutationMapping`.** The resolver ends up handling transport, orchestration, and business rules all at once. Extract into an application use case.

**Placing transactions on individual repository calls.** Multiple operations of one business task can commit separately. Place the transaction on the method representing the atomic use case.

**Holding a transaction for the entire GraphQL request.** The transaction can span many independent fields and retain resources unnecessarily. Use short, well-defined transaction boundaries.

**Assuming multiple root mutation fields are automatically atomic.** Sequential execution does not imply a shared transaction. When multiple steps must succeed together, create one mutation/use case enclosing them.

**Enforcing invariants only in resolvers.** REST, message consumers, or batch jobs can bypass resolvers. Domain/application layers must guard invariants across every entry point.

**Putting `GraphQLError` into domain/service layers.** This couples business logic to GraphQL. Use domain exceptions and map them at the GraphQL boundary.

**Using nested resolvers to continue a mutation's transaction.** The method transaction ends when the method returns; nested fields executing afterward do not automatically join that transaction.

**Calling remote services inside long transactions.** Local transactions cannot roll back external side effects and can hold connections open for too long. Use outboxes/sagas when coordinating systems.

**Mixing imperative and reactive transactions.** Transaction managers and context propagation differ. Choose the model matching your persistence stack.

## Conclusion

Resolvers in Spring for GraphQL should act as adapters: receive arguments/context, invoke application use cases, and transform results into GraphQL responses. Application services orchestrate business operations and define transaction boundaries; domain models guard invariants; repositories and adapters handle persistence and integration. Placing transactions on use cases ensures related operations commit or roll back together while keeping resolvers transport-agnostic. For nested fields, use query services or DataLoaders; for multi-step atomic workflows, design a single mutation/use case; for business failures, map exceptions into GraphQL errors at the API boundary.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Data Integration: Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html#data.transaction)
- [Spring for GraphQL — Request Execution and Exception Handling](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)

# Separating Business Logic from Existing Frameworks and Infrastructure

## Learning Objectives

After this lesson, you will be able to:

- Identify dependencies between business logic, frameworks, runtime, and infrastructure in an existing Java application.
- Explain why domain logic should be decoupled from HTTP frameworks, cloud SDKs, database drivers, and deployment mechanisms.
- Design the domain layer, application layer, and adapters using the Dependency Inversion Principle.
- Apply Ports and Adapters (Hexagonal Architecture) to keep use cases independent of deployment technologies.
- Convert an existing endpoint or batch job into a Java function without leaking serverless details into the domain model.
- Isolate transactions, persistence, messaging, and external APIs behind replaceable ports.
- Manage event contracts, idempotency, and outbox patterns when shifting from synchronous to asynchronous processing.
- Plan a slice-by-slice migration, equivalence testing, and safe traffic shifting.

## 1. Why Separate Business Logic Before Migrating to Serverless?

A traditional Java application is typically built around a web framework, application server, or set of infrastructure libraries. Controllers receive HTTP requests and call services, which use ORMs, database clients, message brokers, and external SDKs. Over time, business logic becomes directly coupled to annotations, transaction APIs, persistence entities, HTTP sessions, or cloud provider classes.

When migrating to serverless, the runtime and how the application is invoked change. A function may be triggered by HTTP, a message, a schedule, or a cloud service event. If business logic is tightly coupled to the old framework, the team has to rewrite large parts just to swap entry points and adapters. That prolongs migration, increases the risk of business behavior drift, and makes the new system harder to test.

The goal is to keep business rules stable while changing how requests are received, data is persisted, messages are sent, and code is deployed. The domain does not need to know whether it is running inside a servlet container, AWS Lambda, Google Cloud Run functions, or a test JVM.

### 1.1. Example of Coupling

A service might mix multiple responsibilities:

~~~java
@Service
public class OrderService {

    @Autowired
    private OrderRepository repository;

    @Autowired
    private SqsClient sqsClient;

    @Transactional
    public OrderEntity createOrder(CreateOrderRequest request) {
        if (request.getItems().isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Order must contain items");
        }

        OrderEntity order = new OrderEntity();
        order.setCustomerId(request.getCustomerId());
        order.setStatus("CREATED");
        repository.save(order);

        sqsClient.sendMessage(builder -> builder
                .queueUrl(System.getenv("ORDER_QUEUE_URL"))
                .messageBody(order.getId().toString()));

        return order;
    }
}
~~~

This code ties business logic to many technical details:

- `@Service`, `@Autowired`, and `@Transactional` belong to the framework.
- `OrderEntity` may be an ORM persistence entity.
- `SqsClient` is an AWS-specific SDK client.
- `ResponseStatusException` and `HttpStatus` belong to the HTTP layer.
- `System.getenv` reads configuration directly from the runtime.
- The service decides the queue URL and how messages are published.

If you migrate this service to a function on another platform, the team must modify many lines of code even though order creation rules have not changed. Unit tests also require more mocks and framework configuration than necessary.

### 1.2. Target State After Separation

A layered, decoupled design might look like this:

~~~mermaid
flowchart TD
    A[HTTP adapter / Event adapter] --> B[Application use case]
    B --> C[Domain model and rules]
    B --> D[Repository port]
    B --> E[Event publisher port]
    D --> F[Database adapter]
    E --> G[Queue or event adapter]
    A --> H[Request/response mapping]
~~~

The domain holds business rules and does not depend on frameworks. The application layer orchestrates use cases and invokes ports. Adapters translate protocols or technologies into port calls.

When migrating to serverless, you can replace the HTTP adapter with a function handler, swap the persistence adapter for an appropriate database client, or replace the event publisher with another messaging service. Use cases remain intact as long as business semantics do not change.

### 1.3. Not Every Abstraction Is Necessary

Separating logic does not mean creating interfaces for every class or building a complex internal framework. Introduce boundaries where there is an independent reason to change:

- Domain rules that need testing without a database.
- A database whose engine or access mechanism may change.
- An HTTP endpoint that might be replaced by an event trigger.
- A message broker or cloud provider that may change.
- A clock, ID generator, or external API that needs stubbing in tests.

A pure calculation class with no external dependencies and no need for substitution can simply remain a plain Java class. Abstractions are only useful when they protect a meaningful boundary.

## 2. Identifying Dependencies and Business Boundaries

Before modifying code, map out components and determine which parts describe business logic and which are implementation details.

### 2.1. Classifying Components

| Existing Component | Layer/Type | Handling Approach When Separating |
|---|---|---|
| Pricing rules, order status transitions | Domain | Keep in plain Java domain models/services |
| Order creation/cancellation workflows | Application use case | Keep in the application layer |
| REST controller, servlet | Inbound adapter | Translate requests into commands/use cases |
| Lambda handler or Functions Framework handler | Inbound adapter | Only parse events, validate contract, and invoke use case |
| JPA repository/ORM | Outbound adapter | Implement repository port |
| SQS, Pub/Sub, Kafka client | Outbound adapter | Implement event/message port |
| Cloud SDK, storage client | Outbound adapter | Hide behind ports when needed by domain/use cases |
| Transaction manager | Infrastructure | Establish explicit transaction boundaries |
| Environment variables, secret manager | Configuration adapter | Bind configuration into typed config objects |
| HTTP status and framework exceptions | Delivery adapter | Map application results/errors to protocol |

### 2.2. Finding Hidden Dependencies

Beyond obvious imports, coupling often shows up through:

- Annotations that alter lifecycle or transactions.
- Static singletons and global mutable state.
- Environment variables read across many classes.
- ORM entities returned directly from APIs.
- Framework exceptions thrown from business services.
- Direct calls to system clock or UUID generators making tests non-deterministic.
- Threads, executors, or schedulers managed by the framework.
- Cloud SDK callbacks embedded in domain logic.
- Transactions opened in controllers or tied to the request thread.
- Messages published before the database transaction commits.

Trace these dependencies in the call graph. A class with few imports can still depend on a framework via static helpers or runtime context.

### 2.3. Defining Domain Boundaries Using Business Language

Domain boundaries should be based on business concepts and rules. For example, an order may have statuses `DRAFT`, `CONFIRMED`, `PAID`, `CANCELLED`; state transitions must follow explicit rules.

Do not leave status names as arbitrary strings assigned by controllers or databases. Use enums/value objects and domain methods to enforce invariants.

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    PAID,
    CANCELLED
}
~~~

~~~java
public final class Order {

    private final OrderId id;
    private final CustomerId customerId;
    private final java.util.List<OrderLine> items;
    private OrderStatus status;

    public Order(OrderId id, CustomerId customerId, OrderStatus status) {
        this(id, customerId, status, java.util.List.of());
    }

    private Order(
            OrderId id,
            CustomerId customerId,
            OrderStatus status,
            java.util.List<OrderLine> items) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.items = java.util.List.copyOf(items);
    }

    public static Order create(
            OrderId id,
            CustomerId customerId,
            java.util.List<OrderLine> items) {
        if (items.isEmpty()) {
            throw new InvalidOrderException("Order must contain items");
        }
        return new Order(id, customerId, OrderStatus.DRAFT, items);
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new InvalidOrderStateException(
                    "Only a draft order can be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void markPaid() {
        if (status != OrderStatus.CONFIRMED) {
            throw new InvalidOrderStateException(
                    "Only a confirmed order can be paid");
        }
        status = OrderStatus.PAID;
    }

    public OrderId id() {
        return id;
    }

    public CustomerId customerId() {
        return customerId;
    }

    public OrderStatus status() {
        return status;
    }

    public java.util.List<OrderLine> items() {
        return items;
    }

    public record OrderLine(String productId, int quantity) {
        public OrderLine {
            if (productId == null || productId.isBlank() || quantity < 1) {
                throw new InvalidOrderException("Invalid order line");
            }
        }
    }
}
~~~

The domain model does not need to know whether the order is stored using JPA, DynamoDB, Firestore, or a REST service. It simply protects business rules and valid states.

## 3. Ports and Adapters Architecture

Ports and Adapters, also known as Hexagonal Architecture, organizes an application around use cases and boundaries. A port describes what the application requires or provides. An adapter translates a specific technology to the port contract.

### 3.1. Inbound Ports and Outbound Ports

- **Inbound port:** a use case that external callers can request the application to execute, e.g., `CreateOrderUseCase`.
- **Inbound adapter:** receives commands from HTTP, messages, CLI, schedulers, or function triggers.
- **Outbound port:** a dependency required by the application, e.g., `OrderRepository`, `PaymentGateway`, `DomainEventPublisher`.
- **Outbound adapter:** implements a port using JPA, JDBC, SQS, Pub/Sub, an HTTP client, or a cloud SDK.

~~~mermaid
flowchart TB
    subgraph Inbound
      A[HTTP handler]
      B[CloudEvent handler]
      C[Scheduled trigger]
    end
    subgraph Application
      D[CreateOrderUseCase]
      E[OrderRepository port]
      F[EventPublisher port]
      G[Domain model]
    end
    subgraph Outbound
      H[JDBC adapter]
      I[Pub/Sub adapter]
      J[Payment API adapter]
    end
    A --> D
    B --> D
    C --> D
    D --> G
    D --> E
    D --> F
    E --> H
    F --> I
    D --> J
~~~

Adapters sit outside the application core. The domain and use cases do not import classes from adapters. Source-code dependencies point inward toward the application/domain contracts.

### 3.2. Dependency Inversion Principle

The Dependency Inversion Principle (DIP) states that high-level modules should not depend directly on low-level modules; both should depend on abstractions. Abstractions should not depend on details; implementation details should depend on abstractions.

In migration:

- A use case needs to save an order, so it defines `OrderRepository`.
- The database adapter implements `OrderRepository`.
- A use case needs to publish a domain event, so it defines `DomainEventPublisher`.
- The messaging adapter implements `DomainEventPublisher`.

The application does not need to import `SqsClient`, `PubSubTemplate`, or `EntityManager`. Concrete implementations are wired together at application startup.

### 3.3. Suggested Java Package Structure

~~~text
order-service/
└── src/main/java/com/example/orders/
    ├── domain/
    │   ├── model/
    │   ├── event/
    │   └── exception/
    ├── application/
    │   ├── port/in/
    │   ├── port/out/
    │   ├── service/
    │   └── command/
    ├── adapter/
    │   ├── in/http/
    │   ├── in/function/
    │   ├── in/messaging/
    │   └── out/
    │       ├── persistence/
    │       ├── messaging/
    │       └── payment/
    └── bootstrap/
        └── ApplicationConfiguration.java
~~~

Package layout is an organizational choice, not a mandatory rule. Smaller projects can use simpler modules/packages. What matters is that domain/application layers are never pulled backward into adapters.

## 4. Designing the Domain and Application Layers

The domain layer models entities, value objects, invariants, and domain services. The application layer orchestrates use cases, transactions, authorization context, and required ports.

### 4.1. Plain Java Domain Models

Domain models should use types that reflect business concepts. Avoid dependencies on `HttpServletRequest`, `ResponseEntity`, ORM entities, or cloud events.

Example value objects:

~~~java
import java.util.Objects;
import java.util.UUID;

public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value);
    }

    public static OrderId newId() {
        return new OrderId(UUID.randomUUID());
    }
}
~~~

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }
}
~~~

Value objects centralize validation at creation time and reduce passing around ambiguous strings and numbers. For currency, avoid `double`; use `BigDecimal` with an explicit currency.

### 4.2. Application Commands and Results

A command describes the input for a use case. It is neither an HTTP DTO nor a message envelope.

~~~java
import java.util.List;

public record CreateOrderCommand(
        String customerId,
        List<CreateOrderItem> items,
        String idempotencyKey) {

    public CreateOrderCommand {
        items = List.copyOf(items);
    }
}

public record CreateOrderItem(
        String productId,
        int quantity) {}
~~~

A result describes the outcome of a use case:

~~~java
public record CreateOrderResult(
        String orderId,
        String status) {}
~~~

An HTTP adapter can map JSON into a command and map a result into a JSON response. An event adapter can map CloudEvent data into the same command if semantics match. Commands should not contain `HttpRequest`, `CloudEvent`, `APIGatewayProxyRequestEvent`, or SDK-specific types.

### 4.3. Defining Inbound Ports

~~~java
public interface CreateOrderUseCase {
    CreateOrderResult create(CreateOrderCommand command);
}
~~~

The use case has a clear contract and can be invoked from multiple entry points. Do not let a controller or function handler call a repository directly when the operation is part of a business workflow.

### 4.4. Defining Outbound Ports

~~~java
import java.util.Optional;

public interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(OrderId id);
    boolean existsByIdempotencyKey(String key);
    void recordIdempotencyKey(String key, OrderId orderId);
}
~~~

~~~java
public interface OrderEventPublisher {
    void publish(OrderCreated event);
}
~~~

~~~java
public interface IdGenerator {
    OrderId newOrderId();
}
~~~

Ports should express the needs of the application. Do not copy SDK APIs verbatim into interfaces; if a port has methods like `sendMessage(softwareVendorRequest)` or `save(EntityManager)`, the abstraction remains tied to technology.

### 4.5. Implementing the Use Case

~~~java
public final class CreateOrderService implements CreateOrderUseCase {

    private final OrderRepository orders;
    private final OrderEventPublisher events;
    private final IdGenerator ids;

    public CreateOrderService(
            OrderRepository orders,
            OrderEventPublisher events,
            IdGenerator ids) {
        this.orders = orders;
        this.events = events;
        this.ids = ids;
    }

    @Override
    public CreateOrderResult create(CreateOrderCommand command) {
        validate(command);

        if (orders.existsByIdempotencyKey(command.idempotencyKey())) {
            // In a real application, fetch and return the stored result.
            throw new DuplicateOrderRequestException();
        }

        java.util.List<Order.OrderLine> lines = command.items().stream()
                .map(item -> new Order.OrderLine(item.productId(), item.quantity()))
                .toList();

        Order order = Order.create(
                ids.newOrderId(),
                new CustomerId(command.customerId()),
                lines);

        orders.save(order);
        orders.recordIdempotencyKey(command.idempotencyKey(), order.id());
        events.publish(new OrderCreated(order.id(), order.customerId()));

        return new CreateOrderResult(
                order.id().value().toString(),
                order.status().name());
    }

    private void validate(CreateOrderCommand command) {
        if (command.items().isEmpty()) {
            throw new InvalidOrderException("Order must contain items");
        }
        if (command.idempotencyKey() == null
                || command.idempotencyKey().isBlank()) {
            throw new InvalidOrderException("Idempotency key is required");
        }
    }
}
~~~

This is a structural example illustrating dependency inversion. In production, saving the order, recording the idempotency key, and publishing events require an appropriate transaction/outbox; do not assume three separate calls are automatically atomic. Checking the key before writing is also insufficient against concurrent requests; a unique constraint or atomic claim operation is needed in the persistence adapter. Event publication is designed in detail in a later section.

## 5. Separating Persistence and Transactions from Use Cases

The persistence adapter translates between the domain model and the database schema. Domain objects should not be forced to carry ORM annotations or extend persistence framework base classes.

### 5.1. Domain Model vs. Persistence Entity

A JPA entity may have fields, constructors, and lifecycle hooks tailored for the ORM. A domain model may have different invariants and business behaviors. The two models can be similar in small applications, but once coupling begins hindering migration, separate them using mappers.

~~~java
@Entity
@Table(name = "orders")
public class OrderJpaEntity {

    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private String customerId;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected OrderJpaEntity() {}

    // getters/setters for ORM
}
~~~

The adapter performs the mapping:

~~~java
import java.util.Optional;

public final class JpaOrderRepository implements OrderRepository {

    private final SpringDataOrderRepository repository;
    private final OrderMapper mapper;

    public JpaOrderRepository(
            SpringDataOrderRepository repository,
            OrderMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return repository.findById(id.value())
                .map(mapper::toDomain);
    }

    @Override
    public boolean existsByIdempotencyKey(String key) {
        return repository.existsByIdempotencyKey(key);
    }

    @Override
    public void recordIdempotencyKey(String key, OrderId orderId) {
        repository.insertIdempotencyRecord(key, orderId.value());
    }
}
~~~

This example assumes `SpringDataOrderRepository` provides the corresponding methods for querying/inserting idempotency records. `SpringDataOrderRepository`, JPA entities, and the transaction framework appear only in the adapter. When migrating to JDBC, DynamoDB, or Firestore, you can replace the adapter and mapper without modifying domain rules.

### 5.2. Placing Transaction Boundaries at the Application Layer

Transactions are part of use case orchestration, while specific transaction APIs are infrastructure. Several approaches exist:

- Use a framework-managed transaction on the application service while keeping annotations in an adapter/decorator.
- Define a `UnitOfWork` or transaction runner port if the application needs independent transaction control.
- Let the repository adapter manage the transaction when the operation spans only one repository with clear semantics.

Do not open a broad transaction around the entire function invocation if the use case also calls HTTP APIs or waits on messages. Long transactions hold connections/locks, increase costs, and risk timeouts. Wrap transactions only around database operations that require atomicity.

### 5.3. Example Transaction Runner

~~~java
public interface TransactionRunner {
    <T> T inTransaction(java.util.concurrent.Callable<T> work);
}
~~~

The application can use this port when a transaction is a boundary that needs explicit control. The adapter implements it via the framework's transaction manager or database mechanisms.

However, do not create an overly generic transaction abstraction covering databases, queues, and HTTP APIs together. A database transaction cannot guarantee atomicity across external systems.

### 5.4. Transactions and Serverless

In serverless, execution environments can be terminated at any time after an invocation. Do not hold a transaction open across multiple invocations or across a long workflow. For multi-step work, persist durable state and use orchestration/state machines or sagas as appropriate.

A use case should clearly define:
- Which parts must commit together in a single database transaction.
- Which parts are external side effects.
- How the system recovers if a side effect fails after commit.
- Whether re-invoking the function is safe if it times out after commit.

## 6. Decoupling Message and Event Contracts

Migrating an application to serverless often entails shifting from synchronous calls to event-driven processing. Do not let domain models depend on specific envelopes from SQS, Pub/Sub, Eventarc, or Kafka.

### 6.1. Domain Events vs. Integration Events

A **domain event** expresses something meaningful within the domain, such as `OrderConfirmed`. It may contain domain identifiers and necessary business facts.

An **integration event** is a public contract for external systems. It needs a schema/version, event ID, timestamp, source, and compatible data. One domain event can map to one or more integration events.

~~~java
public record OrderConfirmed(
        OrderId orderId,
        CustomerId customerId) {}
~~~

~~~java
public record OrderConfirmedV1(
        String eventId,
        String orderId,
        String customerId,
        String occurredAt,
        int schemaVersion) {}
~~~

The messaging adapter is responsible for serializing integration events into the format and metadata required by the broker. The domain must not import `SqsEvent`, `PubSubMessage`, `CloudEvent`, or similar classes.

### 6.2. Outbox Pattern to Avoid Lost Events

If a use case saves an order in the database and then publishes a message directly, there is a failure window:

1. Database commit succeeds.
2. Function stops before publishing.
3. The order exists, but consumers never receive the event.

If it publishes before committing the database transaction, consumers may receive an event for uncommitted data or a transaction that later rolls back.

The outbox pattern solves this by writing domain data and the event record in the same database transaction:

~~~mermaid
flowchart TD
    A[Application use case] --> B[Database transaction]
    B --> C[Save order]
    B --> D[Insert outbox event]
    C --> E[Commit]
    D --> E
    E --> F[Outbox publisher]
    F --> G[Message broker]
    G --> H[Consumer function]
~~~

A separate publisher reads unsent outbox records, publishes messages, and marks their status. The publisher can run as a scheduled function or worker. If publishing succeeds but the worker crashes before marking it sent, the event may be resent; consumers still need idempotency.

### 6.3. Port for the Outbox

The application can define a port that writes events in the same transaction as the aggregate:

~~~java
public interface OrderRepository {
    void save(Order order);
    void appendOutboxEvent(OrderCreated event);
}
~~~

Or define an explicit persistence transaction port to ensure both operations share the same transaction. The choice depends on the database and module boundaries; what matters is that the contract expresses the required atomicity.

Do not let the application invoke two independent adapters and hope they share the same transaction. Transactionality must be guaranteed by the implementation and tested.

### 6.4. Versioning Event Contracts

Events consumed by multiple consumers must preserve backward compatibility. Key principles:

- Adding optional fields is usually safer than renaming/removing fields.
- Do not change the meaning of an already published field.
- Use a schema version when introducing breaking changes.
- Consumers ignore unknown fields when the contract permits.
- Keep identifiers stable and distinguish event IDs from aggregate IDs.
- Test consumers with payloads from older versions.
- Do not serialize domain objects directly into integration events because domain refactoring can break contracts.

### 6.5. Consumer Idempotency

A consumer function may receive the same message again. Use the event ID or business operation ID as an idempotency key, persist state durably, and ensure write operations are safe when re-executed.

Do not use in-memory caches or static sets for deduplication. Instances can be recycled, and multiple instances can receive the same message nearly simultaneously.

## 7. Building Inbound Adapters for HTTP Functions

An HTTP function is a protocol adapter. It reads requests, validates formatting, maps to commands, and converts use case results into responses.

### 7.1. Thin Handlers

~~~java
public final class CreateOrderHttpHandler {

    private final CreateOrderUseCase useCase;
    private final CreateOrderRequestMapper mapper;

    public CreateOrderHttpHandler(
            CreateOrderUseCase useCase,
            CreateOrderRequestMapper mapper) {
        this.useCase = useCase;
        this.mapper = mapper;
    }

    public HttpResult handle(HttpRequestData request) {
        CreateOrderCommand command = mapper.toCommand(request);
        CreateOrderResult result = useCase.create(command);
        return HttpResult.created(mapper.toResponse(result));
    }
}
~~~

Here `HttpRequestData` and `HttpResult` can be internal adapter DTOs or framework-specific types. They never cross the application boundary. The adapter validates the HTTP method, headers, authentication context, content type, and payload size before calling the use case.

### 7.2. Mapping Exceptions to HTTP

The domain should not throw `ResponseStatusException`. The adapter maps business exceptions to status codes:

| Application/Domain Error | Example HTTP Mapping |
|---|---|
| Invalid input | 400 |
| Resource not found | 404 |
| State conflict | 409 |
| Unauthenticated | 401 |
| Forbidden / unauthorized | 403 |
| Temporary dependency failure | 503 |
| Unexpected error | 500 |

This is part of the API contract and may vary by product. Never return stack traces or database details to clients. Log securely with request ID and correlation ID.

### 7.3. A Use Case Can Have Multiple Inbound Adapters

The same `CreateOrderUseCase` can be invoked from:
- A REST endpoint in the legacy application.
- An HTTP function after migration.
- A message consumer if business rules allow creating orders from events.
- A CLI or admin tool.
- Direct tests.

Having multiple adapters does not mean every protocol must be supported. Only build adapters when there is a real use case and a clear contract.

## 8. Building Inbound Adapters for Serverless Events

An event handler receives a CloudEvent or message envelope from the runtime, checks the event type, and transforms the payload into a command. The handler should not contain full business rules.

### 8.1. Adapter for CloudEvents

~~~java
public final class OrderEventFunction
        implements com.google.cloud.functions.CloudEventsFunction {

    private final ConfirmOrderUseCase useCase;
    private final OrderEventMapper mapper;

    public OrderEventFunction(
            ConfirmOrderUseCase useCase,
            OrderEventMapper mapper) {
        this.useCase = useCase;
        this.mapper = mapper;
    }

    @Override
    public void accept(io.cloudevents.CloudEvent event) throws Exception {
        if (!"com.example.order.confirmed-request".equals(event.getType())) {
            return;
        }

        ConfirmOrderCommand command = mapper.toCommand(event);
        useCase.confirm(command);
    }
}
~~~

This is an example adapter. In actual deployments, the Functions Framework may instantiate the entry point according to runtime configuration; ensure dependency injection and lifecycle fit the target runtime.

The handler should:
- Check event type and schema version.
- Check event ID/source.
- Validate payload and tenant/resource scope.
- Transform into a command.
- Call the use case.
- Throw errors according to trigger semantics if platform retries are desired.
- Log the event ID and correlation ID.

### 8.2. Keep CloudEvent Out of the Domain

Do not define domain methods like:

~~~java
// Avoid this
public void confirm(io.cloudevents.CloudEvent event) { ... }
~~~

Instead, the adapter maps event data into commands/domain value objects. This keeps the domain transport-agnostic and able to receive the same command from HTTP, queues, or tests.

### 8.3. Different Triggers, Potentially Same Use Case

An HTTP request and a message can lead to the same use case, though their semantics are not necessarily identical:

- HTTP typically expects an immediate response and a short deadline.
- Message consumers have ack/redelivery semantics.
- Scheduled invocations run repeatedly on a schedule.
- Storage events have distinct payloads and idempotency keys.

Adapters handle protocol semantics. Application use cases only receive business-meaningful commands and return results or application errors.

## 9. Composition Root and Dependency Injection

Separating ports/adapters only works when there is a place to wire concrete implementations. The composition root is where the application initializes and wires dependencies.

### 9.1. Plain Java Wiring

~~~java
public final class ApplicationConfiguration {

    public CreateOrderUseCase createOrderUseCase(
            OrderRepository repository,
            OrderEventPublisher publisher,
            IdGenerator idGenerator) {
        return new CreateOrderService(
                repository, publisher, idGenerator);
    }
}
~~~

In runtimes with a DI framework, the container can instantiate adapters and use cases. For small functions, dependencies can be initialized via factories or manual constructor injection. Choose the approach that fits startup time, lifecycle, and testability.

### 9.2. Separating Configuration from Business Logic

Do not read environment variables directly in the domain or use cases. Bind configuration into a typed configuration object:

~~~java
public record OrderServiceConfig(
        String queueName,
        int maxItemsPerOrder,
        java.time.Duration paymentTimeout) {}
~~~

The configuration adapter reads environment variables, parameter stores, or secret managers and constructs this object. Use cases receive required values via constructors or policy objects.

Secrets should be retrieved from a secret manager and authorized via runtime identity. Never embed secrets in source code, artifacts, or event payloads.

### 9.3. Lifecycle and Cold Start

Serverless runtimes may reuse execution environments. Shared dependencies such as HTTP clients or SDK clients can be initialized once if they are thread-safe and do not retain per-request state.

Do not store user, tenant, request context, or transaction state in mutable static fields. Do not run database queries or external API calls in static initializers if those operations can fail or prolong cold starts.

### 9.4. Do Not Let Frameworks Take Over the Domain

Frameworks can still be used in adapters/bootstrap. The goal is not to eliminate Spring, Quarkus, Micronaut, or Functions Framework from the entire project. The goal is to confine their dependencies to the appropriate layers so business rules do not need to know which framework is running.

## 10. Testing After Layer Separation

Decoupling domain and use cases from frameworks enables faster tests. Each layer has a distinct testing goal.

### 10.1. Domain Unit Tests

Domain tests verify invariants and state transitions without containers, databases, or cloud credentials.

~~~java
@Test
void onlyDraftOrderCanBeConfirmed() {
    Order order = new Order(
            new OrderId(UUID.randomUUID()),
            new CustomerId("customer-1"),
            OrderStatus.DRAFT);

    order.confirm();

    assertEquals(OrderStatus.CONFIRMED, order.status());
}
~~~

~~~java
@Test
void paidOrderCannotBeConfirmedAgain() {
    Order order = new Order(
            new OrderId(UUID.randomUUID()),
            new CustomerId("customer-1"),
            OrderStatus.PAID);

    assertThrows(
            InvalidOrderStateException.class,
            order::confirm);
}
~~~

### 10.2. Application Service Unit Tests

Mock outbound ports to verify orchestration without mocking framework internals:

~~~java
@Test
void createOrderPersistsOrderAndPublishesEvent() {
    OrderRepository repository = mock(OrderRepository.class);
    OrderEventPublisher publisher = mock(OrderEventPublisher.class);
    IdGenerator ids = () -> new OrderId(UUID.fromString(
            "00000000-0000-0000-0000-000000000001"));

    CreateOrderUseCase useCase =
            new CreateOrderService(repository, publisher, ids);

    CreateOrderCommand command = new CreateOrderCommand(
            "customer-1",
            List.of(new CreateOrderItem("product-1", 2)),
            "request-key-123");

    CreateOrderResult result = useCase.create(command);

    assertEquals("DRAFT", result.status());
    verify(repository).save(any(Order.class));
    verify(publisher).publish(any(OrderCreated.class));
}
~~~

This test illustrates how to isolate the application layer. For implementations using an outbox, tests must verify that the event record is written in the same transaction as the aggregate, and integration tests must verify transaction commit/rollback behavior.

### 10.3. Contract Tests for Adapters

- HTTP adapter: method, status, headers, validation, authentication, and error mapping.
- Event adapter: event type, schema version, missing fields, duplicate events, and retry behavior.
- Persistence adapter: mapping, queries, transactions, and unique constraints.
- Messaging adapter: serialization, attributes, ordering, or delivery contracts where applicable.
- External API adapter: timeouts, status mapping, retries, and idempotency headers.

### 10.4. Integration Tests

Run adapters against real test databases or brokers when infrastructure semantics matter. Test containers or emulators can be helpful, but understand their differences from production services. Do not treat mocked unit tests as proof that IAM, networking, triggers, or serialization are configured properly.

## 11. Step-by-Step Migration Roadmap

You do not need to decouple the entire system at once. Pick a use case with clear boundaries, make it framework-independent, then swap adapters and deploy incrementally.

### 11.1. Step 1: Map and Select a Use Case

Document:
- Current entry point.
- Business call graph.
- Database, queue, cache, and API dependencies.
- Transaction boundaries.
- Side effects and event contracts.
- Authorization rules.
- SLOs, throughput, and latency.
- Framework-dependent behaviors.

Select a use case with clear inputs/outputs and minimal shared mutable state. Avoid starting with a large process involving distributed transactions.

### 11.2. Step 2: Create Characterization Tests

Before refactoring, capture current behavior with tests and fixtures. Include success cases, validation errors, state conflicts, and dependency failures.

Characterization tests preserve legacy semantics while extracting code. If current behavior has a known bug, record the decision to fix or retain it; do not accidentally alter business logic during an infrastructure migration.

### 11.3. Step 3: Extract the Domain Model

Move invariants, value objects, and domain services into plain Java classes. Remove HTTP statuses, ORM entities, and cloud SDKs from the domain. Keep mappers in adapters to translate legacy data into domain objects.

### 11.4. Step 4: Define Use Cases and Ports

Create inbound ports for business operations and outbound ports for dependencies that truly need substitution/control. Use constructor injection to make dependencies explicit. Do not let use cases look up implementations via static service locators.

### 11.5. Step 5: Move Infrastructure into Adapters

Write adapters for databases, messaging, caches, payment APIs, and clock/ID providers. Keep transaction boundaries explicit. If events must be published after commit, design an outbox rather than calling a broker arbitrarily from domain services.

### 11.6. Step 6: Build Serverless Adapters

Write thin HTTP functions or event functions. The adapter handles:
- Protocol parsing.
- Authentication/authorization context.
- Transport contract validation.
- Mapping to commands.
- Invoking the use case.
- Mapping results/errors.
- Logging and correlation.

Do not place business rules in the handler just because the function is the new entry point.

### 11.7. Step 7: Shadow, Canary, or Strangler Migration

Depending on the system, you can:
- Run the new logic in shadow mode and compare outputs without triggering side effects.
- Shift a small percentage of traffic to the new function.
- Route by tenant, customer, or operation type.
- Use the strangler pattern to replace capabilities one by one.
- Keep a rollback path to the legacy implementation during the transition.

Do not allow both legacy and new systems to execute real side effects simultaneously without clear idempotency/ownership. Shadow execution should block publishing, payments, or duplicate data writes.

### 11.8. Step 8: Observe and Scale Out

Compare:
- Business results and data consistency.
- Error rates, p95/p99 latency.
- Retries, duplicates, and queue age.
- Database connections and throughput.
- Cold starts and durations.
- Cost per successful operation.
- IAM, network, and audit logs.

Increase traffic incrementally once metrics stabilize. Establish explicit rollback criteria and owners before shifting 100%.

### 11.9. Step 9: Decommission the Legacy Path in a Controlled Manner

After traffic has fully shifted and data is reconciled:
- Disable legacy routes.
- Remove duplicate scheduled jobs or listeners.
- Revoke unused permissions.
- Clean up old configs/secrets after verifying dependencies.
- Update runbooks, dashboards, and ownership.
- Document contracts and migration decisions to support ongoing operations.

Do not delete legacy adapters before confirming no consumers, batches, or jobs still call them.

## 12. Common Pitfalls When Separating Frameworks and Infrastructure

- **Changing only the entry point while business services still depend on SDKs:** the new function remains hard to test and tightly bound to a cloud provider.
- **Putting framework annotations in the domain:** the domain model remains coupled to lifecycle or persistence frameworks.
- **Using persistence entities as API contracts:** database schema changes can break clients.
- **Creating abstractions that mirror SDKs verbatim:** ports still expose vendor types, failing to establish a real boundary.
- **Creating too many interfaces:** increases code complexity without providing meaningful substitutability or testability.
- **Letting handlers call repositories directly:** bypasses use cases and leads to duplicated business rules across adapters.
- **Letting the domain throw HTTP exceptions:** ties the domain to a single delivery protocol.
- **Publishing messages before database commit:** consumers may process events for data that is not durably persisted.
- **Saving orders and outbox records in separate transactions:** risks losing events or emitting invalid events.
- **Splitting transactions improperly:** data can remain in intermediate states without sagas or recovery.
- **Switching to events without versioning contracts:** old consumers can break when producers alter schemas.
- **Assuming exactly-once delivery:** redeliveries can still create duplicate side effects if consumers are not idempotent.
- **Using mutable static fields for request state:** data can leak across invocations on the same instance.
- **Migrating the entire system at once:** large scope makes regressions hard to isolate and complicates rollback.
- **Shadow traffic causing real side effects:** old and new systems can create duplicate orders or duplicate transactions.
- **Overlooking authorization when swapping adapters:** the function's identity may differ from the legacy application's identity.
- **Failing to compare before/after behavior:** new code may compile cleanly while silently altering business rules.

## 13. Pre-Deployment Architecture Checklist

- [ ] Domain models do not import HTTP, ORM, or cloud SDK classes.
- [ ] Application use cases have explicit contracts and are invoked via inbound ports.
- [ ] Outbound ports express business needs rather than copying SDK signatures.
- [ ] Adapters contain mapping logic and protocol/database/broker details.
- [ ] Dependencies are injected via constructors or a composition root.
- [ ] Configuration and secrets are not read directly inside the domain.
- [ ] Transaction boundaries are defined and never held across long network calls.
- [ ] Event publication uses an outbox or equivalent reliability mechanism.
- [ ] Consumers implement idempotency and handle redelivery.
- [ ] HTTP DTOs, persistence entities, and integration events are separated where needed.
- [ ] Event contracts have schemas/versions and a compatibility strategy.
- [ ] Function handlers are thin and handle only transport concerns.
- [ ] Runtime identities follow least privilege for adapters.
- [ ] Cold start initialization and client lifecycles do not hold shared request state.
- [ ] Domain/application unit tests run without cloud credentials.
- [ ] Contract/integration tests verify adapters and transactions.
- [ ] Characterization tests protect legacy behavior.
- [ ] Shadow/canary traffic does not create duplicate side effects.
- [ ] Metrics, traces, rollback criteria, and data reconciliation are in place.
- [ ] Legacy adapters are removed only after confirming zero remaining consumers.

## 14. Self-Check

**Question 1.** Why shouldn't domain services import HTTP frameworks or cloud SDKs?

**Suggested Answer:** The domain represents stable business rules. If it depends on frameworks or SDKs, changing the runtime, transport, or cloud provider forces business logic rewrites and makes testing harder. Adapters should translate technology details to application contracts.

**Question 2.** How do inbound ports and outbound ports differ?

**Suggested Answer:** Inbound ports define use cases that the application exposes for external callers. Outbound ports define dependencies the application needs, such as repositories or event publishers. Adapters invoke or implement these ports using specific technologies.

**Question 3.** Why shouldn't events be published directly before a database commit?

**Suggested Answer:** Consumers might receive events before the data is committed or while a transaction subsequently rolls back. The outbox pattern writes the aggregate and event record in the same transaction, and a publisher dispatches the event after commit.

**Question 4.** When migrating to serverless, why should function handlers be thin?

**Suggested Answer:** Handlers are responsible for protocol handling, parsing, validation, and mapping. Keeping business rules in use cases and the domain allows reuse across HTTP, events, schedules, and tests without trigger coupling.

**Question 5.** Why are characterization tests needed before refactoring?

**Suggested Answer:** Tests capture existing behavior to detect unintended changes during layer separation. They help distinguish structural refactoring from business behavior changes.

**Scenario Exercise:** A Spring Boot application has an order creation endpoint. The controller calls a service; the service uses JPA entities, calls a payment API, and publishes a message to SQS within the same `@Transactional` method. The team wants to migrate this capability to a Java function on a different serverless platform. Propose the domain model, application use case, inbound/outbound ports, adapters, transaction/outbox design, idempotency, and rollout plan.

**Hint:** Create an `Order` domain model with invariants and value objects; define `CreateOrderUseCase`, `OrderRepository`, `PaymentGateway`, and an outbox write port. HTTP/function adapters map requests to commands. Persistence adapters map domain objects to entities/schemas; payment adapters call the API with a stable idempotency key. Write the order and outbox record in the same transaction, with a separate publisher sending integration events; make consumers idempotent. Protect existing behavior with characterization tests, then run side-effect-free shadow testing, canary by tenant or traffic percentage, reconcile results, and retain a rollback path before decommissioning the old endpoint.

## Conclusion

Migrating to serverless becomes much more manageable when business logic is decoupled from existing frameworks and infrastructure. The domain holds invariants and business rules; the application layer orchestrates use cases through ports; adapters handle HTTP, events, databases, messaging, and cloud SDKs. Dependency Inversion lets you swap runtimes or providers without rewriting business logic. Transactions, outbox patterns, event versioning, and idempotency protect data when moving to asynchronous processing. Migration should proceed use case by use case with characterization tests, contract tests, canary rollouts, and rollback criteria to preserve behavior throughout the transition.

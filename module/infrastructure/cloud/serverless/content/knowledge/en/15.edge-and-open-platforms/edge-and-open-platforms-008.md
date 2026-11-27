# Designing Adapters to Reduce Platform Lock-In

In the **Edge and Open Platforms** chapter, a serverless application can run across many environments: a provider's cloud functions, a container platform, an edge runtime, or a traditional Java server. Each environment handles incoming requests, authentication, reading messages, persisting data, emitting events, and managing lifecycles differently. When business logic calls provider SDKs directly or depends on a platform's event types, moving environments ripples changes across many layers.

Adapters establish a translation boundary between a platform's contract and the application model. One adapter receives data from HTTP, queues, or events and translates it into a business command. Other adapters implement ports to access databases, message brokers, object storage, or external services. That way, business logic stays stable even as deployment mechanisms change.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications—specifically Java functions triggered by HTTP, messages, or events. Learners must handle triggers, state, access control, retries, idempotency, cold starts, scaling, and cost to judge when FaaS fits. Well-designed adapters must preserve these operational semantics while reducing coupling to provider-specific APIs and data types.

The Java examples use records, basic library pattern matching, and standard APIs available in Java 17 and later. When targeting other runtimes, adjust syntax and verify the corresponding adapter SDK or library versions.

## 1. Why Are Adapters Needed?

A function often starts by calling the platform SDK directly:

- The handler accepts a provider-defined request type.
- Business logic reads headers, message attributes, or event wrappers directly.
- Use cases call database, queue, or object storage SDKs inline.
- Configuration, secrets, and execution identity are fetched via provider-specific APIs.

This approach can feel fast for a small experiment. As the system grows, however, platform dependencies leak into domain and application services. For example, an order-creation rule might accept an AWS Lambda request class, call the DynamoDB SDK, and emit an EventBridge event inside the same method.

When migrating to another platform, the team has to rewrite handlers, business logic, data access, error handling, and tests. Even running a use case in a unit test requires mocking provider SDK objects.

Adapters isolate change:

- The platform can change how functions are invoked without forcing changes to the domain model.
- Databases or message brokers can be swapped for another implementation.
- Business logic can be tested with fakes or in-memory adapters.
- The same use case can run inside Lambda, a container, or a local environment.
- Differences that cannot be standardized remain explicit at the adapter boundary.

Adapters do not make all platforms identical. They place differences in an intentional boundary and shield business logic from details it does not need to know.

## 2. Ports and Adapters (Hexagonal Architecture)

A common way to structure this is **Ports and Adapters**, also called hexagonal architecture. The application core defines ports—contracts the business logic requires or exposes. Adapters connect those ports to concrete technologies.

- **Inbound port:** contract for asking the application to execute a use case.
- **Inbound adapter:** receives external triggers and invokes an inbound port.
- **Outbound port:** contract the application needs to access data or external services.
- **Outbound adapter:** implements an outbound port using a specific database, queue, API, or platform.

~~~mermaid
flowchart TB
    subgraph IN["Inbound adapters"]
      HTTP["HTTP / API Gateway"]
      QUEUE["Queue / Event adapter"]
      EDGE["Edge request adapter"]
    end

    subgraph CORE["Application core"]
      USE["Use cases"]
      DOMAIN["Domain model"]
      PORTIN["Inbound ports"]
      PORTOUT["Outbound ports"]
    end

    subgraph OUT["Outbound adapters"]
      DB["Database adapter"]
      BUS["Message broker adapter"]
      OBJ["Object storage adapter"]
      EXT["External API adapter"]
    end

    HTTP --> PORTIN
    QUEUE --> PORTIN
    EDGE --> PORTIN
    PORTIN --> USE
    USE --> DOMAIN
    USE --> PORTOUT
    PORTOUT --> DB
    PORTOUT --> BUS
    PORTOUT --> OBJ
    PORTOUT --> EXT
~~~

The key rule is that dependencies point inward toward the application core. Domain and use cases never import cloud provider SDKs. Adapters know both the internal contract and the platform API to translate at the boundary.

### 2.1. Leveraging Open Standards at the Boundary

Open standards reduce the number of custom contracts you must invent, though they do not automatically make underlying services identical:

- **HTTP and OpenAPI** describe request/response interactions and API schemas.
- **CloudEvents** standardizes event context fields such as `id`, `source`, `type`, and `time`; the application still defines the business payload.
- **OpenTelemetry** provides APIs and trace context formats to correlate operations across services.
- **OCI container images** standardize image packaging; platform runtimes, permissions, and limits can still differ.
- **JDBC** abstracts SQL operations, yet does not erase differences in transaction isolation, SQL dialects, quotas, or connection behavior across databases.

Use open standards where they solve the right problem. For example, CloudEvents can serve as a shared envelope for queue and event bus adapters, while each adapter still respects the ACK, ordering, and retry semantics of its source.

## 3. Adapter Design Principles

### 3.1. Name Contracts in Business Language

Ports should express what the application needs to do, not mirror a provider's API.

For example, a business port might represent:

- Saving a confirmed order.
- Looking up payment status.
- Emitting an order-created notification.
- Storing a document file.
- Checking whether an idempotency key has already been processed.

Do not name a port `AwsDynamoClientWrapper` or `GcpPubSubFacade` if the goal is keeping the application core independent. Port names should reflect responsibility, such as `OrderRepository`, `EventPublisher`, or `DocumentStore`.

### 3.2. Adapters Only Translate and Coordinate Protocols

An inbound adapter should:

1. Receive the trigger payload.
2. Validate protocol details and extract necessary metadata.
3. Deserialize and validate input.
4. Map into a command or application event.
5. Invoke the use case.
6. Map the outcome or error into a platform-appropriate response.

Adapters must not contain rules like calculating shipping fees, determining payment eligibility, or deciding order states. Those rules belong in the application/domain core.

### 3.3. Never Leak SDK Types Through Ports

If an interface in the application core accepts an AWS Lambda `Context`, `SQSMessage`, or DynamoDB `AttributeValue`, the core remains coupled to AWS despite having an interface.

Ports should use standard Java types or application-owned domain types. Adapters are responsible for converting provider-specific types into internal types.

### 3.4. Avoid Over-Abstraction

Do not force a single generic interface across every cloud service when their semantics differ. Queues, streams, object storage, and databases do not share the same error handling, ordering, or state guarantees.

Abstract the behaviors the application genuinely needs. If a use case requires relational transactions, a generic `KeyValueStore` interface strips away critical guarantees. If the application requires partition ordering, a port offering only `send(message)` is insufficient.

## 4. Separating Layers in Java

A project structure can be organized by responsibility:

~~~text
src/main/java/com/example/orders/
├── domain/
│   ├── Order.java
│   ├── OrderStatus.java
│   └── OrderPlaced.java
├── application/
│   ├── port/
│   │   ├── in/
│   │   │   └── PlaceOrderUseCase.java
│   │   └── out/
│   │       ├── OrderStore.java
│   │       ├── IdempotencyStore.java
│   │       └── EventPublisher.java
│   └── service/
│       └── PlaceOrderService.java
├── adapter/
│   ├── in/
│   │   ├── http/
│   │   ├── queue/
│   │   └── event/
│   └── out/
│       ├── postgres/
│       ├── dynamodb/
│       ├── pubsub/
│       └── objectstorage/
└── bootstrap/
    └── ApplicationComposition.java
~~~

Package names are illustrative. A smaller project may use fewer folders while keeping the core rule intact: domain depends on no adapters; application defines ports; adapters implement ports; bootstrap wires components together.

Never create provider-named packages at the domain level. Packages like `adapter.out.aws` or `adapter.in.lambda` are the right place to isolate AWS-dependent code.

## 5. Building Inbound Ports and Use Cases

Suppose the application needs to place an order. The inbound port describes the action adapters can invoke:

~~~java
import java.util.List;

public interface PlaceOrderUseCase {
    OrderResult place(PlaceOrderCommand command);
}

public record PlaceOrderCommand(
        String customerId,
        List<OrderLineInput> lines,
        String idempotencyKey) {
}

public record OrderLineInput(
        String productId,
        int quantity) {
}

public record OrderResult(
        String orderId,
        String status) {
}
~~~

This is the application core's contract. It has no knowledge of whether requests arrive from API Gateway, an HTTP server, a queue, or a unit test.

The domain model can enforce its own rules:

~~~java
import java.util.List;

public record Order(
        String id,
        String customerId,
        List<OrderLineInput> lines,
        OrderStatus status) {

    public static Order create(
            String id,
            String customerId,
            List<OrderLineInput> lines) {

        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }

        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain lines");
        }

        if (lines.stream().anyMatch(line -> line.quantity() <= 0)) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        return new Order(id, customerId, List.copyOf(lines),
                OrderStatus.PENDING);
    }
}

public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}
~~~

The rules shown here are minimal. In real applications, the domain may use value objects for IDs, money, and quantities while enforcing richer business invariants.

## 6. Defining Outbound Ports Around Business Needs

The application core needs a way to persist orders and record the intent to publish events. You can define:

~~~java
import java.util.Optional;

public interface OrderStore {
    Optional<OrderResult> findByIdempotencyKey(String key);

    void saveOnce(
            String idempotencyKey,
            Order order,
            OrderPlaced event);
}

public interface EventPublisher {
    void publish(OrderPlaced event);
}

public record OrderPlaced(
        String eventId,
        String orderId,
        String customerId) {
}
~~~

The name `saveOnce` expresses a critical contract: the same idempotency key must never create a second order. The implementation must enforce this via a unique constraint or atomic storage operation, not merely an in-memory check.

In production, saving the order and recording event publication intent must coordinate safely. If the database commits but publishing the event fails, other services will never learn the order was created. `OrderStore` can be implemented using a transaction that writes both the order and a transactional outbox entry; a separate publisher reads the outbox and emits the event. The port keeps the business contract stable while the adapter decides how to implement it on a specific database.

## 7. Cloud-SDK-Independent Use Cases

The use case coordinates business logic through ports:

~~~java
import java.util.UUID;

public final class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderStore orderStore;

    public PlaceOrderService(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    @Override
    public OrderResult place(PlaceOrderCommand command) {
        var previous = orderStore.findByIdempotencyKey(
                command.idempotencyKey());

        if (previous.isPresent()) {
            return previous.get();
        }

        String orderId = UUID.randomUUID().toString();

        Order order = Order.create(
                orderId,
                command.customerId(),
                command.lines());

        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID().toString(),
                order.id(),
                order.customerId());

        orderStore.saveOnce(
                command.idempotencyKey(),
                order,
                event);

        return new OrderResult(order.id(), order.status().name());
    }
}
~~~

The use case knows only `OrderStore`. It does not know whether data is persisted in PostgreSQL, DynamoDB, or another data service. Nor does it know whether events travel over EventBridge, Pub/Sub, Kafka, or an internal broker.

This simplified example includes an idempotency read before saving; in concurrent systems, the check-and-create operation must be atomically protected inside the `OrderStore` implementation. Do not rely on the prior read alone to prevent two concurrent invocations with the same key.

## 8. Inbound Adapter for HTTP

An HTTP adapter converts platform requests into commands. For example, a provider-neutral HTTP controller layer can accept internal types:

~~~java
public record HttpInput(
        String body,
        String idempotencyKey,
        String requestId) {
}

public record HttpOutput(
        int statusCode,
        String contentType,
        String body) {
}
~~~

HTTP adapter:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.JsonProcessingException;

public final class PlaceOrderHttpAdapter {
    private final ObjectMapper mapper;
    private final PlaceOrderUseCase useCase;

    public PlaceOrderHttpAdapter(
            ObjectMapper mapper,
            PlaceOrderUseCase useCase) {
        this.mapper = mapper;
        this.useCase = useCase;
    }

    public HttpOutput handle(HttpInput input) {
        PlaceOrderRequest request;
        try {
            request = mapper.readValue(
                    input.body(), PlaceOrderRequest.class);
        } catch (JsonProcessingException invalidJson) {
            return new HttpOutput(
                    400,
                    "application/json",
                    "{\"error\":\"invalid_json\"}");
        } catch (IllegalArgumentException invalidRequest) {
            return new HttpOutput(
                    400,
                    "application/json",
                    "{\"error\":\"invalid_request\"}");
        }

        try {
            PlaceOrderCommand command = new PlaceOrderCommand(
                    request.customerId(),
                    request.lines(),
                    input.idempotencyKey());

            OrderResult result = useCase.place(command);

            return new HttpOutput(
                    202,
                    "application/json",
                    mapper.writeValueAsString(result));
        } catch (Exception failure) {
            return new HttpOutput(
                    500,
                    "application/json",
                    "{\"error\":\"internal_error\"}");
        }
    }
}

public record PlaceOrderRequest(
        String customerId,
        java.util.List<OrderLineInput> lines) {
}
~~~

The adapter must never return stack traces or raw exception messages to clients. In production, distinguish business errors, parse errors, and transient errors; do not collapse every exception into `500` when a more accurate status code applies.

A concrete API Gateway adapter receives the AWS event class, extracts the body, headers, and request ID, and constructs `HttpInput`. An adapter on Cloud Run or a Java HTTP server can read the corresponding framework request and build the exact same `HttpInput`. The use case remains untouched.

Example AWS Lambda wrapper for an API Gateway proxy event:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.APIGatewayProxyRequestEvent;
import com.amazonaws.services.lambda.runtime.events.APIGatewayProxyResponseEvent;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

public final class ApiGatewayPlaceOrderHandler implements
        RequestHandler<APIGatewayProxyRequestEvent,
                       APIGatewayProxyResponseEvent> {

    private final PlaceOrderHttpAdapter adapter =
            ApplicationComposition.placeOrderHttpAdapter();

    @Override
    public APIGatewayProxyResponseEvent handleRequest(
            APIGatewayProxyRequestEvent event,
            Context context) {

        String idempotencyKey = header(
                event.getHeaders(), "Idempotency-Key");

        String body = Boolean.TRUE.equals(event.getIsBase64Encoded())
                ? new String(Base64.getDecoder().decode(event.getBody()),
                        StandardCharsets.UTF_8)
                : event.getBody();

        HttpOutput output = adapter.handle(new HttpInput(
                body,
                idempotencyKey,
                context.getAwsRequestId()));

        return new APIGatewayProxyResponseEvent()
                .withStatusCode(output.statusCode())
                .withHeaders(Map.of(
                        "Content-Type", output.contentType()))
                .withBody(output.body());
    }

    private static String header(
            Map<String, String> headers,
            String expectedName) {
        if (headers == null) {
            return null;
        }

        return headers.entrySet().stream()
                .filter(entry -> entry.getKey() != null
                        && entry.getKey().equalsIgnoreCase(expectedName))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElse(null);
    }
}
~~~

This is the AWS-coupled layer: it knows the API Gateway event type and Lambda `Context`. It maps data into `HttpInput` and delegates to the neutral HTTP adapter. On another platform, swap this wrapper for the corresponding entry point; `PlaceOrderHttpAdapter` and the use case keep the exact same internal contract. In production, handle Base64-encoded bodies per API Gateway settings and normalize multi-value headers when required by the contract.

## 9. Inbound Adapters for Queues and Events

Queue triggers typically deliver a wrapper containing multiple records to a function. The adapter must map each record into the internal model and honor the platform's acknowledgement mechanism.

Example internal contract:

~~~java
public record IncomingMessage(
        String messageId,
        String eventType,
        String body,
        int deliveryAttempt,
        String correlationId) {
}

public interface OrderMessageHandler {
    void handle(OrderPlaced event);
}
~~~

Handler adapter:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public final class OrderPlacedMessageAdapter {
    private final ObjectMapper mapper;
    private final OrderMessageHandler handler;

    public OrderPlacedMessageAdapter(
            ObjectMapper mapper,
            OrderMessageHandler handler) {
        this.mapper = mapper;
        this.handler = handler;
    }

    public void handle(IncomingMessage message) throws Exception {
        if (!"com.example.orders.order-placed".equals(
                message.eventType())) {
            throw new UnsupportedOperationException(
                    "Unsupported event type");
        }

        OrderPlaced event = mapper.readValue(
                message.body(), OrderPlaced.class);

        handler.handle(event);
    }
}
~~~

This adapter does not acknowledge messages directly. The platform integration layer decides when to ACK, delete, commit offsets, or return partial batch failures. Separating these concerns lets the application handler keep one stable contract while the platform adapter honors exact delivery semantics.

Never assume ACK behavior is identical across queues. Some sources delete messages on ACK; others rely on visibility timeouts; streams use offsets/checkpoints; some triggers require returning a list of failed record identifiers. Preserve these differences inside the dedicated adapter.

## 10. Outbound Adapters for Databases and Brokers

An outbound adapter implements a port using a specific technology. For instance, a PostgreSQL adapter can use JDBC:

~~~java
import javax.sql.DataSource;

public final class PostgresOrderStore implements OrderStore {
    private final DataSource dataSource;

    public PostgresOrderStore(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public java.util.Optional<OrderResult> findByIdempotencyKey(
            String key) {
        // Query the idempotency table with PreparedStatement.
        // Return the saved result if the key exists.
        return java.util.Optional.empty();
    }

    @Override
    public void saveOnce(
            String key,
            Order order,
            OrderPlaced event) {
        // Single transaction:
        // 1. Insert the idempotency key with a unique constraint.
        // 2. Insert the order.
        // 3. Write the event into the transactional outbox.
        // Commit all or roll back all.
    }
}
~~~

This is a skeleton illustrating the boundary; SQL statements, unique conflict handling, and transactions must be implemented against your real schema. Replacing PostgreSQL with another database only requires changing the adapter and composition root configuration, provided the port contract still satisfies the guarantees needed by the use case.

Likewise, `EventPublisher` can be implemented for a specific broker. The adapter handles event serialization, metadata attachment, authentication, and message dispatch. The application core simply requests publishing a domain event.

## 11. Composition Root: Where Adapters Are Wired

Interfaces are useful only when something constructs implementations and wires them together. The composition root is where the object graph is assembled:

~~~java
public final class ApplicationComposition {
    private ApplicationComposition() {
    }

    public static PlaceOrderUseCase placeOrderUseCase() {
        javax.sql.DataSource dataSource =
                DatabaseFactory.createDataSource();

        OrderStore orderStore =
                new PostgresOrderStore(dataSource);

        return new PlaceOrderService(orderStore);
    }
}
~~~

The example above selects the PostgreSQL adapter. In another environment, the composition root can select a different adapter via dependency injection or deployment configuration.

With Java Lambda, you can initialize the object graph once per execution environment to minimize init overhead. Immutable, thread-safe clients can be reused. Never store per-request business state in static fields; invocations may run concurrently or the environment may be recycled at any moment.

The composition root is the right place to read configuration, create clients, choose adapters, and inject dependencies. The domain model should never read environment variables or initialize SDKs itself.

## 12. Adapters for Edge Runtimes

Edge platforms typically place functions close to users or devices to cut latency and handle certain decisions at the network perimeter. However, runtimes, languages, resource limits, and connectivity vary substantially across platforms.

An edge adapter can perform:

- Normalizing HTTP requests and headers.
- Validating tokens or checking simple policies.
- Routing by host, path, or tenant.
- Checking caches and deciding whether to call the origin.
- Normalizing errors and responses.
- Forwarding requests to a backend API with a stable contract.

Do not move database-dependent business logic to the edge if the runtime lacks reliable connectivity or required drivers. Keep latency-sensitive, low-state logic at the edge and forward operations requiring transactions to the backend.

### 12.1. Runtime Limits

Not every edge platform supports a JVM or full Java runtime. Some run only JavaScript, WebAssembly, or restricted sandboxes. Consequently, adapters decouple contracts, yet they do not magically make Java bytecode runnable on any edge runtime.

Available options may include:

- Running Java in cloud functions/containers with a thin edge adapter for routing.
- Compiling Java to a native executable if permitted by the platform and libraries are compatible.
- Using WebAssembly when toolchains, runtimes, and system APIs provide full support.
- Placing a small gateway at the edge while keeping core use cases in the backend.

GraalVM Native Image can reduce startup time and memory footprint in some environments, though it requires configuring reflection, resources, proxies, and native libraries. Not every Java library works seamlessly under native compilation. Always test the artifact on the target runtime.

### 12.2. Locality and Data Considerations

The edge can cut round trips to users, yet primary data may sit in a central region. If every edge request calls a distant database, latency gains vanish.

Explicitly define which data is cached, TTLs, invalidation rules, and behavior when the edge loses connectivity. Never store authoritative business state in edge instance memory because instances can be evicted and requests arrive across multiple locations.

If offline updates are permitted at the edge, design a synchronization model, conflict resolution, and operation identifiers. These are business and data decisions, not mere adapter details.

## 13. Preserving Trigger Semantics Across Platforms

An adapter may standardize method names, but it must never erase source semantics.

### 13.1. HTTP

Preserve:

- Meaningful method, path, query, and headers.
- HTTP status codes.
- Timeouts and payload limits.
- Caller authentication and resource authorization.
- Client or gateway retry rules.
- Streaming, binary bodies, or multi-value headers when required by business logic.

Never flatten every request into a generic command that ignores HTTP method or status semantics. A `GET` must never accidentally trigger side effects just because an adapter calls the same method as a `POST`.

### 13.2. Queues and Streams

Preserve:

- Message IDs or event IDs.
- Delivery attempts and visibility/lease info if available.
- ACK/delete or offset/checkpoint behavior.
- Partial batch failures.
- Ordering, partition keys, and consumer groups.
- Retries, dead-lettering, and replay.
- Correlation/trace context.

If one adapter pulls from a stream while another platform pushes batches, both can invoke the same use case; however, the adapter must ensure checkpoints advance only on successful processing per source rules.

### 13.3. Scheduled Triggers

Schedulers vary in timezones, overlap handling, retries, and execution semantics. The adapter should translate the trigger into an internal command carrying a run identifier, scheduled timestamp, and target data scope.

Never assume a schedule fires strictly once. Enforce idempotency or job locking if two invocations can overlap.

## 14. Where Do State, Idempotency, and Retries Live?

Adapters forward metadata and respond according to protocol. The application core owns business rules and idempotency logic. Infrastructure adapters handle storage, locks, or deduplication using platform capabilities.

For example, a message might be redelivered because the function timed out after the database already committed. If the adapter merely catches an exception and retries everything blindly, business logic could execute twice. Therefore:

- Carry the message/event ID or idempotency key into the command.
- Persist processing results in durable storage.
- Use unique constraints or transactions to prevent races.
- ACK only after results are durably persisted.
- Separate transient failures from permanent failures.
- Use the outbox pattern when data writes and event publication must stay consistent.

Never let an adapter mask errors by returning success. When a source treats `2xx` as complete, returning `2xx` before durable persistence can silently drop messages.

## 15. Security and Identity by Adapter

Each platform authenticates differently: IAM roles, service accounts, workload identity, tokens, mTLS, or API keys. The application core must not contain provider-specific credential retrieval logic.

Adapters and bootstrap are responsible for:

- Reading execution identity from the environment.
- Constructing clients with the appropriate credential provider.
- Authenticating HTTP or message origins.
- Enforcing least-privilege permissions for databases, queues, and object storage.
- Passing a normalized principal or security context when use cases check permissions.
- Keeping secrets out of commands, events, and logs.
- Refreshing tokens and handling expired credentials.

Avoid building an overly generic `AuthProvider` interface when platforms differ in semantics. Define ports for business needs such as `AuthorizationService` or `TenantAccessPolicy`, while concrete adapters authenticate callers and map into an internal principal.

Normalizing the principal must preserve required fields such as tenant, issuer, subject, or scopes. If authorization relies on a claim, the adapter must verify that claim from a trusted source before passing it into the core.

## 16. Configuration and Secrets

Never hardcode endpoints, buckets, topics, database URLs, or secrets inside use cases. Define meaningful internal configuration records:

~~~java
public record OrderApplicationConfig(
        String eventDestination,
        int maxBatchSize,
        java.time.Duration operationTimeout) {
}
~~~

Bootstrap reads configuration from environment variables, files, or the platform secret manager and constructs the config object. The application core receives required configuration via constructor injection.

Not every setting should be abstracted away, though. Regions, ARNs, IAM roles, edge locations, or queue visibility timeouts are deployment-specific details. Keep them in the deployment layer or adapter configuration so the core remains decoupled.

Fetch secrets from the environment's secret manager or workload identity. Avoid re-reading secrets on every operation when the SDK offers safe caching, while still respecting rotation and token expiration.

## 17. Observability and Correlation Across Adapters

Adapters are the right boundary to attach operational metadata to logs and traces:

- Platform request ID.
- Event/message ID.
- Business correlation ID.
- Trace context.
- Adapter or transport name.
- Delivery attempt.
- Function version or deployment revision.

Do not stuff all operational metadata into domain objects if use cases do not need it. You can pass a compact internal `ExecutionContext` for observability and security without turning it into a catch-all bag of SDK objects.

Example:

~~~java
public record ExecutionContext(
        String requestId,
        String correlationId,
        String traceId,
        String tenantId) {
}

public interface ContextAwarePlaceOrderUseCase {
    OrderResult place(
            PlaceOrderCommand command,
            ExecutionContext context);
}
~~~

This is an inbound port variant for use cases that genuinely require context. When context is solely for logging and tracing, keep it in the adapter or tracing scope so every use case is not forced to accept operational parameters.

If the core does not need context for business decisions, record it in the adapter and attach it to the tracing/logging scope. If `tenantId` governs access permissions or data scoping, pass it via an explicit typed field after verifying its authenticity.

## 18. Adapter Design Is Not Lowest Common Denominator

A real risk is designing an interface so stripped-down that every provider can implement it, sacrificing critical capabilities in the process.

For example, a `MessageQueue` port exposing only `send` and `receive` cannot express:

- FIFO or ordering keys.
- Visibility timeouts and lease extensions.
- Batch acknowledgements.
- Offset commits.
- Delayed delivery.
- Dead-letter policies.
- Transactional publishing.

Three ways to handle this:

1. **Capability-driven ports:** include in the contract the guarantees the use case genuinely requires.
2. **Capability interfaces:** extract optional capabilities, such as `OrderedMessagePublisher` or `BatchAcknowledger`, when specific adapters support them.
3. **Provider-specific adapters:** keep specialized behavior inside dedicated adapters or use cases when business logic directly depends on those features.

Never paper over differences by pretending every adapter provides exactly-once delivery, distributed transactions, or global ordering. When a platform lacks a guarantee, reflect that honestly in the contract or deployment documentation.

## 19. Testing Adapters and Substitutability

A port is truly useful only when implementations can be tested against the same contract.

### 19.1. Unit Tests for the Application Core

Use fake adapters to test use cases without cloud SDKs:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public final class InMemoryOrderStore implements OrderStore {
    private final Map<String, OrderResult> results = new HashMap<>();

    @Override
    public Optional<OrderResult> findByIdempotencyKey(String key) {
        return Optional.ofNullable(results.get(key));
    }

    @Override
    public void saveOnce(
            String key,
            Order order,
            OrderPlaced event) {
        if (results.containsKey(key)) {
            throw new IllegalStateException("Duplicate key");
        }

        results.put(
                key,
                new OrderResult(order.id(), order.status().name()));
    }
}
~~~

The fake above suits single-threaded unit tests. It does not simulate real transactions, concurrency, or outbox behavior; never rely on it to conclude a production adapter is safe under concurrent invocations.

### 19.2. Contract Tests for Outbound Adapters

Run the same test suite against each port implementation:

- Saving an order and reading it back produces accurate results.
- Duplicate idempotency keys never create a second order.
- Connection errors translate into classifiable exceptions.
- Transaction rollbacks leave no partial state behind.
- Events/outbox entries commit atomically with the transaction per contract.
- Data and character encodings survive serialization intact.

For database adapters, use a test database or suitable container. For broker adapters, test ACKs, retries, and ordering under realistic configuration.

### 19.3. Integration Tests for Inbound Adapters

Test adapters against sample events or runtime emulators:

- HTTP status codes and response bodies.
- Authentication and idempotency headers.
- Queue batches and partial failures.
- Unsupported event types.
- Malformed payloads failing schema validation.
- Request timeouts and payload size limits.
- Trace/correlation context preserved across mapping.

Passing tests against a local mock adapter does not prove IAM roles, networking, trigger mappings, or permissions are configured correctly. Run smoke tests in a representative deployment environment.

### 19.4. Architecture Tests

Use ArchUnit or build-time dependency checks to ensure domain/application packages never depend on adapter packages or provider SDKs. Dependencies pointing inward toward the core must remain intact across refactors.

## 20. Strategy for Migrating to Another Platform

When migrating from one cloud provider to another, do not start by swapping every SDK simultaneously. Proceed boundary by boundary:

1. Inventory platform dependencies inside handlers, use cases, and domain code.
2. Identify use cases and internal contracts to preserve.
3. Introduce inbound ports for each use case currently called directly from handlers.
4. Move business logic out of provider-specific handlers.
5. Introduce outbound ports for databases, queues, and external APIs likely to change.
6. Wrap existing implementations into adapters without altering behavior.
7. Write contract tests to lock down current semantics.
8. Implement new adapters for the target platform.
9. Run the same test suite and compare outcomes, latency, retries, and cost.
10. Shift traffic or workloads incrementally with observability and rollback plans.

If the target platform lacks equivalent guarantees—such as partial batch failures or matching transaction semantics—design compensating controls or adjust workflows. Never swap an adapter and assume system behavior stays identical.

## 21. Common Design Mistakes

**Putting SDKs in the domain:** The domain imports provider types and cannot be tested or run independently. Move SDKs to adapters and use internal types in ports.

**Renaming an SDK as an interface:** The interface still accepts or returns provider-specific types, leaving the dependency unisolated. Design contracts around business needs.

**Putting business rules in adapters:** With two triggers, logic gets duplicated and diverges. Move rules into use cases or domain services.

**One generic adapter for every transport:** HTTP, queues, and streams have distinct semantics for responses, ACKs, ordering, and retries. Build separate adapters sharing an application port where appropriate.

**Hiding differences under a lowest common denominator:** Overly thin contracts drop transactions, ordering, or batch failure handling. Model required capabilities explicitly and document limits.

**Using static mutable state across invocations:** Execution environments can be recycled or run concurrently. Persist business state in durable storage.

**Assuming adapters guarantee complete portability:** Runtimes, IAM, networking, quotas, and data services still differ. Test on the target platform and document capabilities.

**Skipping event contract versioning:** Two adapters may serialize the same event differently. Standardize schemas, types, timestamps, nulls, and versions.

**Skipping retry semantics testing:** A new adapter might ACK too early or retry differently than the previous source. Test duplicate messages, timeouts, and ambiguous outcomes.

**Adding empty pass-through layers without a real boundary:** Classes merely forward calls without adding contracts or translation. Introduce ports/adapters only when isolating a real boundary or enabling testing.

## 22. Pre-Deployment Checklist

- [ ] Domain and use cases import no provider SDKs or provider event types.
- [ ] Inbound adapters map HTTP/messages/events into clear commands or application events.
- [ ] Outbound ports express business needs rather than mirroring provider APIs.
- [ ] Outbound adapters implement ports using concrete technologies.
- [ ] The composition root builds and injects implementations.
- [ ] Handlers contain no business rules beyond protocol validation.
- [ ] Internal DTOs preserve event IDs, correlation IDs, and required metadata.
- [ ] ACK, delete, offset, and partial batch failure handling honor source semantics.
- [ ] Retries, idempotency, transactions, and outbox handling are explicitly designed.
- [ ] Business state is persisted durably rather than held in instance memory.
- [ ] IAM/service account permissions and secrets are scoped with least privilege in adapters/bootstrap.
- [ ] Platform timeouts, concurrency, cold starts, and payload limits are accounted for.
- [ ] Edge adapters do not rely on runtimes or APIs unsupported by the platform.
- [ ] Specialized capabilities are not hidden behind an overly generic interface.
- [ ] Unit tests cover the core, contract tests cover adapters, and integration tests cover triggers.
- [ ] Logs, metrics, and traces correlate across boundaries.
- [ ] Cost and rollback readiness have been evaluated for swapping adapters or platforms.

## Conclusion

Adapters create a boundary between the platform and the application. Inbound adapters turn triggers into business requests; outbound adapters implement the ports use cases need to persist data, emit events, or call external services. The domain and application core maintain stable contracts, while SDK details, event wrappers, authentication, ACKs, checkpoints, and deployment wiring stay inside adapters or bootstrap.

Reducing platform lock-in without sacrificing correctness requires preserving HTTP, queue, stream, retry, idempotency, and access-control semantics. Adapters do not make runtimes or cloud services identical; they place differences at clear, testable, and controllable boundaries. On edge platforms, you must also confirm whether a Java runtime, native image, or WebAssembly is genuinely supported. When ports reflect real business needs and adapters pass contract tests, the same application core can run across many triggers and deployment environments with far less change.

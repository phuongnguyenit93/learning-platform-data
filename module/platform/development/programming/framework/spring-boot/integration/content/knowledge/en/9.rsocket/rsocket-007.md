# Configuring responders with @MessageMapping when receiving messages

## Objectives and context

Within the **SPRING_BOOT_INTEGRATION** module, Spring Boot organizes integrations across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. These flows do not only need to connect successfully: they must also manage **configuration, data contracts, transactions, errors, duplicate handling, testing, and observability**.

**RSocket** is a message-oriented protocol supporting multiple multiplexed requests/streams over a single TCP or WebSocket connection. Spring Framework provides **RSocket responders** following the Spring Messaging model: a Spring bean annotated with `@Controller`, methods annotated with `@MessageMapping`, and `Mono`/`Flux` return types representing results. Callers typically use `RSocketRequester`.

For example, Inventory Service may accept:

- `inventory.stock.get`: query stock by SKU, returning one result.
- `inventory.stock.watch`: subscribe to a stream of stock changes.
- `inventory.audit.accept`: accept notifications requiring no direct business reply.
- `inventory.batch.reserve`: receive multiple commands in a request-channel and return per-command results.
- `inventory.reserve`: execute a command affecting PostgreSQL and return a receipt.

Suppose `inventory.reserve` was COMMITTED by Inventory, yet the network dropped before Order Service received the response. The caller sees a timeout, even though the reservation already exists. Hence, **a responder with correct routing is not safe on its own**: it needs stable operation IDs, SQL uniqueness, concurrency limits, and reconciliation.

This lesson belongs to the **RSocket** chapter, topic **Configuring responders with `@MessageMapping` when receiving messages**.

### Learning outcomes

1. Explain the roles of requester, responder, route, payload, and routing metadata.
2. Distinguish request-response, fire-and-forget, request-stream, and request-channel.
3. Configure an RSocket TCP responder in Spring Boot and verify the server port.
4. Write `@Controller`/`@MessageMapping` handlers using DTOs, `Mono`, `Flux`, and `@DestinationVariable`.
5. Call responders via `RSocketRequester` and understand connection/request lifecycles.
6. Configure and diagnose MIME types/codecs/`RSocketStrategies`.
7. Handle validation, security, RSocket errors, and unknown business outcomes.
8. Avoid blocking the event loop when calling JDBC, Redis, or HTTP partners.
9. Design backpressure, bounded concurrency, cancellation, and retries.
10. Integrate transactions, outbox/inbox, idempotency, and test fault windows.

> **Principle:** `@MessageMapping` declares a **message-receiving route**; it does not create an HTTP endpoint, a durable queue, or an exactly-once business transaction.

## 1. RSocket in Spring Boot Integration architecture

~~~mermaid
flowchart LR
    A["Order Service / RSocketRequester"] --> B["RSocket TCP/WebSocket"]
    B --> C["RSocketMessageHandler"]
    C --> D["@MessageMapping responder"]
    D --> E["Application service"]
    E --> F["PostgreSQL / Redis"]
    E --> G["Transactional outbox"]
    G --> H["Kafka / RabbitMQ / HTTP"]
    D -. "Mono / Flux" .-> A
~~~

| Component | Responsibility | Does not automatically provide |
| --- | --- | --- |
| RSocket transport | Multiplexes frames over TCP/WebSocket | Durable retention |
| `RSocketRequester` | Sends requests, FNF, streams, channels | Transactions on the target system |
| Routing metadata | Specifies route name | Authentication/authorization |
| `RSocketMessageHandler` | Dispatches messages to annotated methods | Domain logic |
| `@Controller` | Spring bean holding responder methods | TCP port unless configured |
| `@MessageMapping` | Maps logical routes | HTTP methods/paths |
| `RSocketStrategies` | Encoders, decoders, metadata extraction | Business schema semantics |
| `Mono`/`Flux` | Publishers, demand, cancellation | Idempotency/durability |
| Application service | Validation, transactions, receipts | Automatic distributed ACID |

**Distinguishing transports from brokers:**

| Need | RSocket | HTTP REST | Kafka/RabbitMQ |
| --- | --- | --- | --- |
| Request-response | Native | Native | Custom RPC pattern |
| One request → many replies | Native request-stream | SSE/streaming depending on API | Consumers read separate messages |
| Bidirectional in one interaction | Native request-channel | WebSocket/other HTTP streaming | Multiple queues/topics |
| Backpressure | Reactive Streams demand | API/protocol dependent | Broker-specific flow control |
| Works while consumer offline | Does not buffer | Does not buffer | Yes per queue/topic policy |
| Replay after crash | Needs business store/cursor | Needs business store | Yes per broker/retention |
| Exactly-once business effect | Not built-in | Not built-in | Not built-in |

Choose RSocket when bidirectional streaming or multiplexed requests are needed between peers that can maintain connections. For requirements like **holding messages while the target is offline for hours**, use a durable outbox, queue, broker, or work table.

## 2. Four interaction models

~~~mermaid
flowchart TD
    A["Requester"] --> R["REQUEST_RESPONSE: 1 request → 0..1 reply"]
    A --> F["FIRE_AND_FORGET: 1 → no application reply"]
    A --> S["REQUEST_STREAM: 1 request → many replies"]
    A --> C["REQUEST_CHANNEL: many requests ↔ many replies"]
~~~

| Model | Typical client call | Typical responder signature | Use case |
| --- | --- | --- | --- |
| Request-response | `retrieveMono(Reply.class)` | DTO → `Mono<Reply>` | Queries or commands needing a receipt |
| Fire-and-forget | `send()` | DTO → `Mono<Void>` | Notifications accepting no reply |
| Request-stream | `retrieveFlux(Update.class)` | DTO → `Flux<Update>` | Watching inventory changes |
| Request-channel | `data(Flux, Type).retrieveFlux(...)` | `Flux<Command>` → `Flux<Result>` | Bidirectional batch commands |

The frame/interaction type is **chosen by the requester**. The Java return type must match the RSocket interaction and route; returning `Flux` alone does not turn a request-response call into a request-stream.

### 2.1. Demand does not mean durable data

RSocket request-stream/channel uses Reactive Streams demand to pace how many items the receiver requested. This avoids flooding a slow subscriber **if the underlying publisher genuinely honors demand**.

Backpressure does not:

- Persist items to a database when the peer is offline.
- Guarantee commit ordering across multiple concurrent streams.
- Increase HikariCP connections or an HTTP partner's capacity.
- Undo side effects when the client cancels.
- Replace inbox/outbox or idempotency.

## 3. Dependencies and auto-configuration

Example for Spring Boot 3.x, Java 17+, Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'

    // When also using HTTP WebFlux/WebClient:
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    // If the responder calls JDBC:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

`spring-boot-starter-rsocket` provides RSocket/Spring Messaging integration; WebFlux is **not required** just to expose RSocket over TCP. WebSocket transport may require an appropriate web runtime. Use a BOM matching your project's Spring Boot/Spring Framework/Reactor/RSocket Java versions; Boot 4 may change starters/packages/codecs.

### 3.1. TCP server

~~~yaml
spring:
  rsocket:
    server:
      port: 7000
      transport: tcp

app:
  inventory:
    max-watch-subscribers: 100
~~~

`spring.rsocket.server.port` is the **RSocket server port**, distinct from the HTTP `server.port`. Spring Boot auto-configures the responder when dependencies, port, and bean conditions match. Check startup logs to confirm the listener bound cleanly; adding `@MessageMapping` alone does not guarantee the server is running.

### 3.2. TCP and WebSocket

| Transport | When to use | Notes |
| --- | --- | --- |
| RSocket over TCP | Direct service-to-service connections | LB, firewalls, TLS, idle timeouts |
| RSocket over WebSocket | Infrastructure supports HTTP upgrade | Web runtime, mapping path, reverse proxies |
| Local/in-process transport | Testing protocol logic | Does not replace fault tests over real networks |

Some Boot versions provide `spring.rsocket.server.mapping-path` for WebSocket; that is an **HTTP upgrade** path, not an RSocket TCP route like `inventory.stock.get`. Configure TLS according to transport/version; do not assume HTTP `server.ssl.*` automatically protects RSocket TCP.

## 4. First responder: request-response

DTOs for the inventory contract:

~~~java
// StockQuery.java
public record StockQuery(String sku) {
}

// StockAvailability.java
public record StockAvailability(
        String sku,
        long availableQuantity,
        long aggregateVersion) {
}
~~~

Service port:

~~~java
import reactor.core.publisher.Mono;

public interface InventoryReadService {
    Mono<StockAvailability> getAvailability(String sku);
}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class InventoryRSocketResponder {

    private final InventoryReadService inventory;

    public InventoryRSocketResponder(InventoryReadService inventory) {
        this.inventory = inventory;
    }

    @MessageMapping("inventory.stock.get")
    public Mono<StockAvailability> getStock(
            @Payload StockQuery request) {

        if (request == null || request.sku() == null
                || request.sku().isBlank()) {
            return Mono.error(
                    new IllegalArgumentException("sku required"));
        }

        return inventory.getAvailability(request.sku());
    }
}
~~~

- `@Controller` marks the component holding message endpoints.
- `@MessageMapping` registers a **logical RSocket route**.
- `@Payload` binds decoded data from the RSocket frame.
- `Mono<StockAvailability>` emits at most one value.
- `Mono.error(...)` is a reactive error signal; it does not automatically become an HTTP 400.
- `RSocketMessageHandler` handles route lookup, argument resolution, and response encoding.

~~~mermaid
sequenceDiagram
    participant C as RSocketRequester
    participant T as TCP transport
    participant H as RSocketMessageHandler
    participant M as @MessageMapping
    participant S as InventoryReadService
    C->>T: REQUEST_RESPONSE route=inventory.stock.get
    T->>H: Routing metadata + JSON
    H->>M: getStock(StockQuery)
    M->>S: getAvailability(sku)
    S-->>M: Mono result
    M-->>H: Publisher
    H-->>C: RESPONSE payload
~~~

If the route does not exist, the client receives an RSocket/mapping error per implementation, **not HTTP 404**.

## 5. Calling the responder with RSocketRequester

Spring Boot typically provides `RSocketRequester.Builder` when RSocket infrastructure is configured.

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration(proxyBeanMethods = false)
public class InventoryRequesterConfiguration {

    @Bean
    RSocketRequester inventoryRequester(
            RSocketRequester.Builder builder) {

        // Illustrates connection creation for this lesson.
        return builder
                .connectTcp("localhost", 7000)
                .block(Duration.ofSeconds(5));
    }
}
~~~

This configuration is **simplified for tests/learning**. If the peer is down at startup, `block()` can fail bean creation. Production code needs connection/reconnect management, load balancing, authentication, readiness, and shutdown handling; avoid creating a new connection per request. Never call `block()` on the Reactor Netty event loop.

Client:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public class InventoryRSocketClient {

    private final RSocketRequester requester;

    public InventoryRSocketClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<StockAvailability> getStock(String sku) {
        return requester
                .route("inventory.stock.get")
                .data(new StockQuery(sku))
                .retrieveMono(StockAvailability.class);
    }
}
~~~

Publishers are lazy; requests are actually sent upon subscription. In a reactive HTTP handler, **return the publisher** so the outer framework manages subscription.

### 5.1. Anti-pattern: orphaned subscribe

~~~java
public void handle(String sku) {
    client.getStock(sku).subscribe();
    // No remaining ownership to handle errors/cancellation/completion.
}
~~~

Better:

~~~java
public Mono<StockAvailability> handle(String sku) {
    return client.getStock(sku)
            .timeout(java.time.Duration.ofSeconds(2));
}
~~~

A read-only query timeout may be retried per policy; a timeout on a data-mutating command may leave an **UNKNOWN** outcome if the target already committed.

### 5.2. Requester lifecycle

A requester is tied to an RSocket connection/session. When the network fails, the requester may need to be recreated; do not assume `.retrieveMono()` safely reconnects on its own. Configure reconnect backoff/jitter, cap concurrent connection attempts, and preserve stable `operationId` values for retried commands.

## 6. Fire-and-forget with @MessageMapping

Notification DTO:

~~~java
public record AuditEvent(
        String eventId,
        String sku,
        String action) {
}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class AuditResponder {

    private final AuditService audit;

    public AuditResponder(AuditService audit) {
        this.audit = audit;
    }

    @MessageMapping("inventory.audit.accept")
    public Mono<Void> accept(AuditEvent event) {
        return audit.record(event);
    }
}
~~~

`AuditService.record` is an application port returning `Mono<Void>`. Requester:

~~~java
public Mono<Void> sendAudit(
        RSocketRequester requester, AuditEvent event) {

    return requester
            .route("inventory.audit.accept")
            .data(event)
            .send();
}
~~~

**Important:** `send()` provides no **business acknowledgment** that the responder wrote the audit record to the DB. Fire-and-forget returns no receipt response.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Responder
    participant D as PostgreSQL
    C->>R: FIRE_AND_FORGET E-100
    C->>C: send() completes
    R->>D: Write audit
    D--xR: SQL unavailable
    Note over C,D: Caller receives no business receipt
~~~

If audit, payment, or inventory events **must not be lost**, use a durable outbox/broker or request-response with a persisted receipt. Never treat FNF as a substitute for RabbitMQ publisher confirms.

## 7. Request-stream: one request, many responses

DTOs:

~~~java
public record StockWatchRequest(String sku) {
}

public record StockUpdate(
        String sku,
        long quantity,
        long aggregateVersion) {
}
~~~

Update source:

~~~java
import reactor.core.publisher.Flux;

public interface InventoryUpdateSource {
    Flux<StockUpdate> watch(String sku);
}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class StockWatchResponder {

    private final InventoryUpdateSource source;

    public StockWatchResponder(InventoryUpdateSource source) {
        this.source = source;
    }

    @MessageMapping("inventory.stock.watch")
    public Flux<StockUpdate> watch(StockWatchRequest request) {
        return source.watch(request.sku());
    }
}
~~~

Client:

~~~java
public Flux<StockUpdate> watchSku(
        RSocketRequester requester, String sku) {

    return requester
            .route("inventory.stock.watch")
            .data(new StockWatchRequest(sku))
            .retrieveFlux(StockUpdate.class);
}
~~~

### 7.1. Defining the stream contract

Determine:

1. Does the stream emit an initial snapshot, or changes only?
2. Is ordering guaranteed per SKU?
3. Is cursor/`aggregateVersion` replay supported on reconnect?
4. Are slow consumers buffered, dropped, or coalesced?
5. How many subscriptions may each client open?
6. When does the stream complete?
7. Does cancellation release DB cursors/listeners/buffers?

A `Flux` backed by an in-memory source does not persist events across disconnects. When zero event loss is required, use a durable log + cursor or a message broker.

### 7.2. Backpressure REQUEST_N

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Server
    C->>R: REQUEST_STREAM
    C->>R: REQUEST_N(3)
    R-->>C: Update #1
    R-->>C: Update #2
    R-->>C: Update #3
    C->>R: REQUEST_N(2)
    R-->>C: Update #4
    R-->>C: Update #5
~~~

Reactive sources must honor demand. `onBackpressureLatest()` suits only state snapshots where intermediate values may be skipped; **never use it to drop audit or financial events**.

### 7.3. Cancellation

~~~java
return source.watch(request.sku())
        .doFinally(signalType ->
                metrics.recordStreamClosed(signalType.name()));
~~~

`metrics` is an illustrative component. `doFinally` handles completion/error/cancellation, yet never rolls back already-committed transactions. Manage stream source cleanup independently.

## 8. Request-channel: receiving Flux and returning Flux

Request-channel allows the requester to stream multiple commands and receive multiple results in one interaction.

~~~java
public record ReservationCommand(
        String operationId,
        String orderId,
        String sku,
        int quantity) {
}

public record ReservationResult(
        String operationId,
        String outcome,
        String reservationId) {
}
~~~

Port:

~~~java
import reactor.core.publisher.Mono;

public interface ReservationService {
    Mono<ReservationResult> reserveIdempotently(
            ReservationCommand command);
}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class ReservationChannelResponder {

    private final ReservationService reservations;

    public ReservationChannelResponder(
            ReservationService reservations) {
        this.reservations = reservations;
    }

    @MessageMapping("inventory.batch.reserve")
    public Flux<ReservationResult> reserveMany(
            Flux<ReservationCommand> commands) {

        return commands
                .concatMap(reservations::reserveIdempotently);
    }
}
~~~

Requester:

~~~java
public Flux<ReservationResult> reserveMany(
        RSocketRequester requester,
        Flux<ReservationCommand> commands) {

    return requester
            .route("inventory.batch.reserve")
            .data(commands, ReservationCommand.class)
            .retrieveFlux(ReservationResult.class);
}
~~~

`concatMap` serializes processing **within a single subscription**. Multiple concurrent streams/connections can still execute in parallel, requiring per-resource/per-tenant limits.

### 8.1. FlatMap, ordering, and concurrency

- `concatMap`: executes commands one by one in order.
- `flatMap(fn, 8)`: allows concurrent execution; outputs may arrive out of order.
- `flatMapSequential`: preserves output order, though side effects may commit out of order.
- When state machines require strict ordering/versioning, use `aggregateVersion`, conditional updates, or partitioning rather than relying solely on `Flux` order.

### 8.2. Channels are not unbounded transactions

Never wrap a long-lived request-channel inside a single SQL transaction. Each command needs a **short transaction and independent `operationId`**; results emit after commit. A stream can process dozens of items before the network drops, so define partial completion and recovery policies.

### 8.3. Partial failure

~~~text
Client sends K1, K2, K3.
Server COMMITS K1 and K2.
Response for K2 is lost; connection drops.
Client only knows for certain it received K1's receipt.
~~~

The client **cannot** assume K2 was unprocessed and generate a fresh operation ID to resend. Query status or retry with the same key. K3 may or may not have arrived depending on timing.

## 9. Route variables and route ownership

Route names are part of the **wire contract**, not Java method names or URLs.

~~~java
public final class InventoryRoutes {

    private InventoryRoutes() {
    }

    public static final String STOCK_GET =
            "inventory.stock.get";

    public static final String RESERVE =
            "inventory.reserve";
}
~~~

Using constants in annotations:

~~~java
@MessageMapping(InventoryRoutes.STOCK_GET)
public Mono<StockAvailability> get(StockQuery request) {
    return inventory.getAvailability(request.sku());
}
~~~

Route variable:

~~~java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;

@MessageMapping("inventory.stock.{sku}")
public Mono<StockAvailability> bySku(
        @DestinationVariable String sku) {
    return inventory.getAvailability(sku);
}
~~~

Requester:

~~~java
return requester.route("inventory.stock.{sku}", sku)
        .retrieveMono(StockAvailability.class);
~~~

`@DestinationVariable` belongs to Spring Messaging route handling, **not** MVC `@PathVariable`. Validate the SKU and authorization; clients controlling routes must never gain arbitrary business action privileges.

| Annotation | Transport/boundary |
| --- | --- |
| `@MessageMapping` in RSocket responder | Routing metadata → message handler |
| `@PostMapping` | HTTP endpoint |
| `@KafkaListener` | Topic/partition |
| `@RabbitListener` | Queue/consumer container |
| `@ServiceActivator` | Spring Integration `MessageChannel` |

Spring Messaging also uses `@MessageMapping` in STOMP/WebSocket contexts; in this lesson, ensure **RSocket messaging infrastructure** is configured.

## 10. Payloads, MIME types, and RSocketStrategies

An RSocket payload contains **data bytes** and **metadata bytes**. Data may be JSON, Protobuf, CBOR, or binary. Metadata may include routing, authentication, trace/correlation, and custom fields.

A client may send:

~~~json
{"sku":"SKU-A"}
~~~

The responder decodes it into `StockQuery` when a compatible codec is present. `RSocketStrategies` aggregates message encoders/decoders and metadata extractor support.

### 10.1. Data MIME type

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester =
        RSocketRequester.builder()
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .connectTcp("localhost", 7000)
                .block(Duration.ofSeconds(5));
~~~

In Spring Boot, prefer the injected builder since it already applies configured codecs/metadata/observation. Never replace the entire `RSocketStrategies` bean in a way that drops default JSON codecs.

### 10.2. Composite metadata

~~~text
RSocket composite metadata
  - routing: inventory.reserve
  - authentication: credentials / bearer information
  - trace/correlation metadata
  - application-defined metadata
Data MIME: application/json
Data: {"operationId":"K-100","sku":"SKU-A",...}
~~~

Custom metadata does not automatically become Spring message headers without a configured extractor. `@Header("tenantId")` does not imply reading an HTTP header; RSocket TCP has no per-message HTTP request headers with the same semantics.

### 10.3. Security implications

Never trust client-supplied metadata such as `tenantId`, `role`, Java class names, or user identities. Authenticate the connection/request first and enforce domain authorization. In particular, never deserialize arbitrary Java class names from untrusted type metadata.

### 10.4. Data MIME and schema contracts

Publish:

- MIME/codec.
- Required/optional/nullable fields.
- Timestamp/timezone formats, decimal units, unknown-enum policies.
- Schema versions and payload compatibility.
- Maximum payload size/nesting/collection cardinality.
- Error response representation.
- Idempotency/business identity.

The RSocket protocol does not know whether `amountMinor` represents VND or USD. Structural schema compatibility alone does not guarantee business semantics.

## 11. Validation and RSocket error handling

Command DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record ReserveCommand(
        @NotBlank String operationId,
        @NotBlank String orderId,
        @NotBlank String sku,
        @Positive int quantity) {
}
~~~

Method:

~~~java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import reactor.core.publisher.Mono;

@MessageMapping("inventory.reserve")
public Mono<ReservationResult> reserve(
        @Valid @Payload ReserveCommand command) {

    return reservations.reserveIdempotently(command);
}
~~~

`@Valid` only takes effect when Bean Validation/messaging infrastructure is properly configured for your version. Test invalid/missing payloads over a **real RSocket connection**, not just direct Java method calls.

### 11.1. Missing, null, and primitive defaults

If JSON omits `quantity`, primitive `int` may bind to 0 depending on the mapper; `@Positive` rejects 0 when validation runs. If business logic must distinguish **absent** from explicit 0, use `Integer` + `@NotNull` or check JSON presence.

### 11.2. Error signals are not HTTP status codes

| Error | Handling approach |
| --- | --- |
| Invalid JSON/unsupported schema | Reject; do not hot-retry |
| Missing required field | Business validation error |
| Unauthorized route/tenant | Reject + security audit |
| Optimistic lock conflict | Reload/reconcile if safe |
| SQL connection unavailable | Backoff/bulkhead, bounded retry |
| RSocket connection reset | Operation may be `UNKNOWN` |
| Stream canceled | Release subscriptions/resources |
| Fatal codec/server bug | Alert; never expose stack traces |

An exception from `@MessageMapping` normally propagates as a reactive error/RSocket error frame, **not HTTP 400/500**. For structured expected business rejections, define a response contract:

~~~java
public record ReservationReply(
        String operationId,
        String outcome,
        String reservationId,
        String errorCode) {
}
~~~

For example, `outcome` can be `ACCEPTED`, `CONFIRMED`, `REJECTED`, `UNKNOWN`. Never return `CONFIRMED` when only a background `PENDING` job was recorded.

## 12. Never block the Reactor event loop

RSocket runs on reactive/network infrastructure. A handler returning `Mono` that calls blocking JDBC/HTTP **before constructing the Mono** still stalls execution threads.

### 12.1. Anti-pattern

~~~java
@MessageMapping("inventory.reserve")
public Mono<ReservationResult> reserve(
        ReservationCommand command) {

    ReservationResult result =
            jdbcStore.reserve(command); // Blocking!
    return Mono.just(result);
}
~~~

This executes synchronous SQL before the publisher is even returned; it can increase latency across all RSocket streams and connection keepalives.

### 12.2. Offloading properly to boundedElastic

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@MessageMapping("inventory.reserve")
public Mono<ReservationResult> reserve(
        ReservationCommand command) {

    return Mono.fromCallable(() ->
                    blockingReservationService
                            .reserveIdempotently(command))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

`Mono.fromCallable` is lazy and runs upon subscription. `boundedElastic` fits blocking APIs better than `Schedulers.parallel()`, yet **does not automatically bound to Hikari max connections or HTTP quotas**. Add bulkheads at each external resource.

### 12.3. Transaction contexts do not cross threads automatically

A Spring JDBC `@Transactional` method invoked through a proxy opens a transaction on the calling thread. Switching to `boundedElastic` crosses a **thread boundary**: any caller transaction does not automatically propagate. Place the transaction on the business service running on the worker thread, and never attempt to wrap an unbounded reactive stream in one local JDBC transaction.

With R2DBC, use the reactive transaction manager/`TransactionalOperator` and proper Reactor context; never mix JDBC transaction semantics into reactive DB access.

### 12.4. Java 21 virtual threads

Virtual threads reduce the cost of waiting on blocking I/O, yet **do not increase PostgreSQL, Redis, or HTTP partner capacity**. Enabling virtual threads does not replace resource budgets, deadlines, or flow control.

## 13. Backpressure and bounded concurrency

One RSocket connection can carry many in-flight requests and streams. Maximum TCP connections alone cannot serve as the entire admission policy.

| Load source | Limit to consider |
| --- | --- |
| Active streams | Quota per client/tenant |
| Max payload/frame | Codec/memory safety |
| Route QPS | Rate limiter |
| JDBC SQL | HikariCP max + short transactions |
| HTTP downstream | Per-route connection/concurrency pool |
| Redis | Command latency/client capacity |
| Broker | Listener concurrency/prefetch |
| Retries | Attempts + deadline + backoff |
| Streaming sources | Bounded buffers/cancellation cleanup |

### 13.1. Semaphore around blocking SQL

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class BoundedReservationAdapter {

    private final BlockingReservationService service;
    private final Semaphore permits = new Semaphore(8);

    public BoundedReservationAdapter(
            BlockingReservationService service) {
        this.service = service;
    }

    public Mono<ReservationResult> reserve(
            ReservationCommand command) {

        return Mono.fromCallable(() -> {
            boolean acquired =
                    permits.tryAcquire(100, TimeUnit.MILLISECONDS);

            if (!acquired) {
                throw new DownstreamBusyException(
                        "Reservation budget exceeded");
            }

            try {
                return service.reserveIdempotently(command);
            } finally {
                permits.release();
            }
        }).subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

`DownstreamBusyException` is an application-defined exception. At most 8 operations run **per instance**; 8 pods can run up to 64 simultaneously. `tryAcquire(timeout)` avoids indefinite waiting, and `finally` prevents permit leaks.

This is a concurrency bulkhead, **not a QPS rate limiter**. If each call takes 5 ms, 8 permits can exceed a partner's QPS quota. When cluster-wide quotas are needed, use appropriate rate-limiting/distributed coordination.

### 13.2. Unbounded buffers are dangerous

~~~java
// Anti-pattern when producer outpaces subscriber.
return source.watch(sku)
        .onBackpressureBuffer();
~~~

Unbounded buffering risks OOM. If events are state snapshots, coalesce/keep latest per contract; audit/payment records must never be dropped casually. When loss is forbidden, use durable logs or bounded queuing with explicit overflow handling.

### 13.3. Bounding subscription counts

`REQUEST_N` bounds items **within a stream**, not the number of new streams opened. Enforce max streams per client/tenant, stream lifetime/idle policies, resource cleanup, and protection against opening thousands of subscriptions to the same SKU.

## 14. Transactions and idempotency for command responders

A side-effecting `inventory.reserve` command requires a stable **business `operationId`**—never use the RSocket stream ID or connection ID as an idempotency key.

Example PostgreSQL schema:

~~~sql
CREATE TABLE inventory_reservations (
    reservation_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL UNIQUE,
    order_id VARCHAR(120) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    state VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reservation_receipts (
    operation_id UUID PRIMARY KEY,
    request_hash CHAR(64) NOT NULL,
    receipt_json JSONB NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

`request_hash` is a fingerprint of the **canonical business payload**; reusing the same key with a different payload must be rejected as a conflict. Business mutations and receipts must commit in the **same SQL transaction**.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BlockingReservationService {

    private final ReservationStore store;

    public BlockingReservationService(ReservationStore store) {
        this.store = store;
    }

    @Transactional
    public ReservationResult reserveIdempotently(
            ReservationCommand command) {

        return store.insertOrReturnPreviousReceipt(command);
    }
}
~~~

`ReservationStore.insertOrReturnPreviousReceipt` is an application port implementing atomic SQL insert/unique handling and transactions. Checking `SELECT exists` followed by `INSERT` without a unique constraint **is insufficient** when two retries race concurrently.

### 14.1. Retrying with same key but different payload

~~~text
K-100 -> reserve SKU-A quantity=2 -> receipt R-500.
K-100 -> reserve SKU-B quantity=7 -> conflict.
~~~

Neither create a second reservation nor return receipt R-500 as if the new payload applied. Do not treat operation IDs as authorization: verify tenant/user ownership and reserve permissions.

### 14.2. @Transactional does not span HTTP/Kafka/Rabbit

An SQL transaction does not pull remote HTTP APIs, other RSocket peers, Kafka publishes, or RabbitMQ brokers into a distributed ACID transaction. To emit events after committing a reservation, write an **outbox intent** in the SQL transaction and relay after commit.

### 14.3. Outbox/inbox

~~~mermaid
flowchart LR
    C["Order command"] --> T["Local SQL transaction"]
    T --> O["Save order + outbox K-100"]
    O --> R["Relay after commit"]
    R --> S["RSocket inventory.reserve K-100"]
    S --> D["Target SQL reservation + receipt"]
    D --> A["Response / UNKNOWN"]
    A --> P["Reconciliation/retry same K-100"]
~~~

The outbox prevents losing intent if the process crashes after local commit; target idempotency makes retries safe. Outbox provides **at-least-once**, not automatic exactly-once.

**Key point:** Responders must protect business transactions with stable operationIds/SQL uniqueness; RSocket connections and Reactive Streams cannot confirm or undo remote side effects on their own.

 
## 15. Disconnecting after target commit: UNKNOWN outcome

In RSocket request-response, callers can receive `TimeoutException`, `ConnectionErrorException`, connection close errors, or abnormal subscription termination **even when the responder already COMMITTED successfully**. Client exception types do not prove a business operation did not happen.

~~~mermaid
sequenceDiagram
    participant C as Order Service / Requester
    participant R as Inventory / Responder
    participant D as PostgreSQL
    C->>R: REQUEST_RESPONSE reserve(operationId=K-100)
    R->>D: INSERT reservation + receipt
    D-->>R: COMMIT OK
    R--xC: Response lost / connection reset
    C->>C: Timeout -> UNKNOWN
    C->>R: Query K-100 or retry same K-100
    R->>D: Find persisted receipt
    D-->>R: RES-500 already committed
    R-->>C: Return same receipt
~~~

### 15.1. Milestones that must never be conflated

| Milestone | What occurred | Not yet proven |
| --- | --- | --- |
| Requester builds `Mono` | Described an operation | Frame left the JVM |
| Publisher subscribed | RSocket operation started | Responder received all data |
| Responder method invoked | Metadata/route/payload sufficed for dispatch | Business transaction committed |
| Target SQL COMMIT | Local database recorded state | Client received receipt |
| Responder emits response | Server app produced result | Bytes arrived at client |
| Client `retrieveMono` completes | Result received per RSocket contract | Other async downstreams finished |
| Client `send()` completes for FNF | Requester-side send finished | Responder COMMITTED |

A caller timeout after step 4 represents an **unknown outcome**, not a confirmed business failure. APIs need statuses such as `PENDING`, `CONFIRMED`, `REJECTED`, `UNKNOWN`.

### 15.2. Never retry with a new operationId

~~~java
// Wrong: one intent can create two reservations.
return inventoryReserve(newCommandWithRandomId())
        .retry(3);
~~~

Replace with a durably stored operationId:

~~~java
ReservationCommand command =
        outboxRepository.findPendingCommand(operationId);

return rsocketClient.reserve(command)
        .timeout(java.time.Duration.ofSeconds(2))
        .onErrorResume(java.util.concurrent.TimeoutException.class,
                error -> reconciliation.lookup(command.operationId()));
~~~

`outboxRepository`, `rsocketClient`, and `reconciliation` are illustrative ports. Real logic must classify permanent/transient/unknown errors, apply retry budgets, and persist outcomes. Never map every RSocket system error to HTTP 500 and generate a brand-new business command.

### 15.3. Client cancellation is not rollback

When a client cancels a subscription or a timeout operator cancels upstream, the responder may receive cancellation. However:

- Committed SQL transactions do **not** roll back automatically.
- HTTP partners may have already processed side effects even if the client socket closes.
- Brokers may have received events before producer confirms arrived.
- Commands executing on blocking threads may not stop immediately on cancellation.
- Even if a Java task is interrupted, remote side effects may remain active.

Enforce **deadlines, idempotency, and reconciliation**; never rely on `cancel()` for business atomicity.

### 15.4. Choosing request-response vs. accepted-async

If reservation runs in a short transaction, returning a synchronous receipt can fit well. If it calls multiple systems or waits on slow partners:

1. The RSocket responder validates and persists `operationId` + durable intent.
2. Returns `ACCEPTED` with that ID, not `CONFIRMED`.
3. Workers process via outbox/broker.
4. The requester subscribes to a result stream or queries status.
5. On reconnect, the requester uses the same ID to resume/reconcile.

RSocket enables streaming results, yet the **source of truth** must be durable when crash recovery is required.

## 16. Errors at different layers

Not every exception originates inside `@MessageMapping` methods.

~~~mermaid
flowchart TD
    A["RSocket frame"] --> B["Transport / connection"]
    B --> C["Routing metadata"]
    C --> D["Message decoding"]
    D --> E["Argument validation"]
    E --> F["Business service"]
    F --> G["JDBC/HTTP/Redis/broker"]
    G --> H["Response encode/send"]
~~~

Possible failure points:

- **Transport/connection:** TLS handshake, peer disconnect, keepalive timeout.
- **Routing:** missing or ambiguous route.
- **Payload:** MIME/codec mismatch, malformed JSON, unknown schema version.
- **Argument validation:** missing/invalid fields.
- **Authorization:** insufficient principal/tenant permissions.
- **Business:** conflicts, duplicate `operationId`, invalid state transitions.
- **Resource:** Hikari timeout, SQL deadlock, Redis unavailable, HTTP 429/503.
- **Output:** response encode failure, connection lost after SQL commit.

### 16.1. Classifying permanent/transient/unknown

| Error | Category | Recommended policy |
| --- | --- | --- |
| Wrong route, unsupported schema | Permanent for current version | Fix contract/deployment |
| Missing/invalid business field | Permanent for unchanged input | Reject; do not hot-retry |
| Unauthorized/forbidden | Permanent for current credentials | Reject, audit |
| SQL uniqueness duplicate key | Contract-dependent | Dedupe/return prior receipt |
| Optimistic version conflict | Recoverable | Reload, business reconcile |
| SQL deadlock/serialization | Usually transient | Bounded transaction retry |
| Hikari pool exhausted | Resource overload | Bulkhead/backoff, tune pool/tx |
| Remote HTTP 429/503 | Policy-dependent transient | Retry-After/backoff/rate limit |
| RSocket connection lost during command | **Unknown** | Lookup receipt/idempotent replay |
| Cancellation after local COMMIT | **Committed** in local DB | Do not undo; reflect true status |

Error handlers must never leak SQL stack traces, access tokens, or PII. Use `@MessageExceptionHandler`/Spring Messaging exception advice where supported by your version, or map expected business errors to explicit DTOs; RSocket ERROR frames do not carry HTTP status semantics.

### 16.2. Never swallow errors and return success

~~~java
@MessageMapping("inventory.reserve")
public Mono<ReservationReply> incorrect(ReserveCommand command) {
    return reservationService.reserve(command)
            .onErrorResume(ex -> {
                log.warn("reserve failed", ex);
                return Mono.just(new ReservationReply(
                        command.operationId(),
                        "CONFIRMED", null, null));
            });
}
~~~

This is an **anti-pattern**: a failed or UNKNOWN operation is reported as `CONFIRMED`. For side-effecting commands, classify errors, record state, and return the real receipt or error contract.

### 16.3. Bounded retries

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

return requester.route("inventory.stock.get")
        .data(new StockQuery(sku))
        .retrieveMono(StockAvailability.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
~~~

This illustrates a **read-only query**; production code should filter transient errors and enforce an overall deadline. Never copy this policy directly to `inventory.reserve` without server-side idempotency.

Multi-layer retries multiply attempts: client 3 × adapter 3 × broker 3 = 27. Bound total attempts, backoff, jitter, deadlines, and check quotas.

## 17. Connection lifecycle, keepalive, and reconnect

RSocket multiplexes streams over one connection. When the network drops, active subscriptions can terminate with errors; a requester bound to the old connection is not guaranteed to automatically resume sending on a new one.

### 17.1. Configuring keepalive

In RSocket Java versions supporting connector customization, keepalive can be configured:

~~~java
import java.time.Duration;

builder.rsocketConnector(connector ->
        connector.keepAlive(
                Duration.ofSeconds(20),
                Duration.ofSeconds(90)));
~~~

This assumes a compatible `RSocketRequester.Builder builder` configured before connecting. Check exact APIs/versions and load-balancer idle timeouts; never set keepalive intervals longer than LB idle timeouts unintentionally.

**Keepalive only checks connection liveness**; it does not prove the Inventory database is healthy or a reservation committed.

### 17.2. Reconnect and re-subscribe

~~~text
Connection reset
   -> requester marks connection unavailable
   -> backoff + jitter
   -> establish new connection and auth
   -> resubscribe stock.watch
   -> read snapshot / cursor if required
   -> reconcile in-flight reservation operationIds
~~~

Never re-subscribe thousands of streams simultaneously after an outage; enforce connection/admission budgets, retry jitter, restore priorities, and observability.

### 17.3. RSocket resume is not a durable queue

The RSocket protocol supports resumption if both client and server enable and configure it, within session/buffer limits. Never assume Spring Boot enables resume by default or that it survives **process crashes/redeploys**.

When zero lost updates across downtime are required, use a durable event log, monotonic cursors/`aggregateVersion`, or a broker. Resume does not replace business idempotency/SQL transactions.

### 17.4. Graceful shutdown

During rolling deployments:

1. Stop accepting new subscriptions/requests per lifecycle.
2. Let in-flight operations complete within a grace period where safe.
3. Never mark work sitting only in RAM as succeeded.
4. Active streams may cancel; clients reconnect and replay from cursors.
5. Reconcile `UNKNOWN` commands by `operationId`.
6. Preserve metrics/trace correlation to diagnose issues after restart.

Never drop all connections assuming SQL operations rolled back. With Java virtual threads or Reactor cancellation, local transactions may already have committed.

## 18. Securing the RSocket responder

An `inventory.reserve` route mutates state. Define **who may open connections, who may invoke routes, and who may act on a given SKU/tenant**.

### 18.1. Control layers

| Layer | Objective |
| --- | --- |
| TLS/trust | Protect transport, verify peer |
| mTLS where needed | Verify client certificates |
| RSocket authentication | Identify caller via setup/per-request policy |
| Route authorization | Restrict `inventory.reserve` to suitable service roles |
| Domain authorization | Verify caller may reserve that SKU/warehouse/tenant |
| Limits | Bound payload size, streams, QPS, concurrency |
| Schema validation | Reject untrusted/unsupported data |
| Audit/redaction | Log decisions without leaking secrets |

### 18.2. Metadata authentication differs from HTTP headers

Spring Security integrates RSocket authentication/authorization in supported versions. Yet `@Header("Authorization")` or a JSON `tenantId` field **does not trigger MVC/HTTP Spring Security filters**.

Configure RSocket security interceptors/metadata support and test:

- No credentials → reject.
- Invalid/expired credentials → reject.
- Authenticated caller lacking route permission → forbidden.
- Tenant A attempting to reserve Tenant B's SKU → reject in service.
- Raw `tenantId` metadata must never override verified identity.
- Valid service identities route to matching business policies.

Illustrative policy:

~~~text
inventory.stock.get     -> authenticated read scope
inventory.stock.watch   -> read scope + tenant stream quota
inventory.reserve       -> service role INVENTORY_RESERVE
inventory.batch.reserve -> batch role + per-command ownership check
~~~

This outlines business policy requirements, not a complete security DSL config. Exact security APIs vary by Spring Security/RSocket version; consult official docs and test the actual runtime.

### 18.3. TLS and secrets hygiene

- Verify CA chains and hostnames; never disable TLS validation in production.
- Source all credentials/private keys from a secret manager with rotation policies.
- Never log bearer tokens/Basic credentials or raw PII payloads.
- Ensure LBs/proxies support long-lived TCP/WebSocket connections.
- Never put raw Authorization/tenant/email values in metric tags.
- Limit JSON nesting/size to mitigate denial of service.

## 19. Versioning routes, DTOs, and metadata

Routes are contracts. Even additive fields can break strict old readers, and new readers may fail on historical payloads if new fields are marked required.

V1:

~~~json
{"sku":"SKU-A"}
~~~

V2:

~~~json
{"sku":"SKU-A","warehouseId":"WH-1"}
~~~

### 19.1. Compatibility matrix

| Reader | Writer | What to verify |
| --- | --- | --- |
| V1 | V1 | Baseline |
| V2 | V1 | New reader receives old payload |
| V1 | V2 | Old reader receives extra field |
| V2 | V2 | New path |
| V3 | V1 | Historical replay/transitive support |

`@MessageMapping` does not version schemas automatically. Choose versioned routes like `inventory.stock.get.v2`, `schemaVersion` envelopes, data MIME versions, or adapters, and document the policy explicitly.

### 19.2. Event/command identity vs. schemaVersion

~~~json
{
  "operationId": "K-100",
  "schemaVersion": 2,
  "aggregateVersion": 17,
  "orderId": "ORD-100",
  "sku": "SKU-A",
  "quantity": 2
}
~~~

- `operationId`: logical business command identity for idempotency.
- `schemaVersion`: how to deserialize and validate the payload.
- `aggregateVersion`: domain ordering/version conflict detection.
- RSocket stream ID: transport/session identity; **never use as a dedupe key**.

During schema upgrades, never accidentally generate a new `operationId` for the same retried command sitting in an outbox.

### 19.3. Dangerous semantic changes

If `availableQuantity` meant “physical stock” in V1 and means “available-to-promise” in V2, keeping the same field name is a semantic breaking change even though JSON still parses. Introduce new fields/routes, versioning, and migrations.

### 19.4. Unknown versions

Responders must never blindly deserialize an unknown version as the current DTO and run business logic. Reject or park unsupported versions per contract, keeping audit/`operationId` and alerts; never hot-retry unsupported payloads.

## 20. Testing responders

Unit tests calling Java methods directly **do not** verify route metadata, TCP connections, JSON codecs, RSocket frame types, cancellation, or error mapping.

### 20.1. Testing pyramid

| Layer | What to prove |
| --- | --- |
| Domain unit | Validation, business invariants |
| Responder unit | Handler delegates to service/`Mono`/`Flux` properly |
| Contract test | v1/v2 DTOs, missing/null/unknown fields |
| RSocket integration | Real routes, MIME, request-response/stream/channel |
| SQL Testcontainers | Unique `operationId`, transactions, rollbacks, receipts |
| Fault injection | Response lost after COMMIT, reconnect/cancellation |
| Security integration | Authentication, authorization, tenant isolation |
| Load/soak | Backpressure, stream counts, Hikari/HTTP limits |

### 20.2. StepVerifier unit test

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class InventoryResponderUnitTest {

    @Test
    void returnsStock() {
        InventoryReadService fake =
                sku -> Mono.just(
                        new StockAvailability(sku, 8, 5));

        InventoryRSocketResponder responder =
                new InventoryRSocketResponder(fake);

        StepVerifier.create(
                responder.getStock(new StockQuery("SKU-A")))
                .expectNext(new StockAvailability("SKU-A", 8, 5))
                .verifyComplete();
    }
}
~~~

This test verifies method logic only. It does not prove `@MessageMapping("inventory.stock.get")` was registered or JSON codecs work.

### 20.3. RSocket TCP integration test

Illustrative **test skeleton** using a dedicated test port:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
        "spring.rsocket.server.port=7001",
        "spring.rsocket.server.transport=tcp"
})
class InventoryRSocketIntegrationTest {

    @Autowired
    RSocketRequester.Builder builder;

    @Test
    void routesAndDecodesRequestResponse() {
        RSocketRequester requester = builder
                .connectTcp("localhost", 7001)
                .block(Duration.ofSeconds(5));

        StepVerifier.create(
                requester.route("inventory.stock.get")
                        .data(new StockQuery("SKU-A"))
                        .retrieveMono(StockAvailability.class))
                .assertNext(result ->
                        org.junit.jupiter.api.Assertions
                                .assertEquals("SKU-A", result.sku()))
                .verifyComplete();
    }
}
~~~

Requires an application context with the responder and a fake/real `InventoryReadService`. Fixed port 7001 can collide in parallel CI runs; real suites should use random/isolated ports and obtain the actual bound port per Spring Boot version. Close requesters/connections after tests to avoid socket leaks. This snippet is a skeleton only and **does not yet prove SQL or durable business behavior**.

### 20.4. Testing Request-stream with demand/cancel

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(
        requester.route("inventory.stock.watch")
                .data(new StockWatchRequest("SKU-A"))
                .retrieveFlux(StockUpdate.class),
        0)
    .thenRequest(2)
    .expectNextCount(2)
    .thenCancel()
    .verify();
~~~

Requires a mock source producing at least 2 updates and instrumentation confirming subscription cleanup on cancel. Avoid `Thread.sleep(100)` to check “received enough items” when `StepVerifier`/latches with timeouts can be used.

### 20.5. Testing Request-channel partial failure

~~~text
Given K1, K2, K3 command stream
And server commits K1 and K2
When network connection drops before K2 receipt
Then requester records K2 UNKNOWN
And target database has exactly one reservation per K1, K2
When requester reconnects and retries K2 using same key
Then server returns stored K2 receipt
And total business side effects remain unchanged
~~~

For deterministic tests, use `CountDownLatch`/commit markers or fault proxies rather than arbitrary sleeps.

### 20.6. Testing FNF semantics

Testing that `send()` completes is insufficient. Verify:

- Responder receives events on the right route.
- If auditing is non-durable, DB-failure behavior on the consumer is documented.
- If auditing must be durable, use outbox/broker/receipts rather than misinterpreting send completion.
- JSON conversion errors ahead of the handler method are handled cleanly.

### 20.7. Four-interaction test matrix

| Interaction | Happy path | Failure/edge path |
| --- | --- | --- |
| Request-response | Valid DTO and result | Unknown route, validation, response lost after commit |
| Fire-and-forget | Routed to handler | Receiver fails after send, no receipt |
| Request-stream | Backpressure/demand | Slow reader, cancel, reconnect, missed updates |
| Request-channel | Input/output mapping | Partial commits, duplicate IDs, reordering |
| Cross-cutting | Security, codecs | Untrusted metadata, MIME mismatch, overload |

### 20.8. JDBC/Redis/HTTP failure tests

An RSocket endpoint can handle transport flawlessly while integration fails:

- Hikari connection timeouts.
- SQL deadlocks/optimistic version conflicts.
- Redis cache stampedes.
- Partner HTTP 429/503 responses.
- Outbox insert failing after business mutation.
- Connection lost after SQL COMMIT.
- Kafka/RabbitMQ publisher confirms lost.

Use PostgreSQL Testcontainers and fault proxies/HTTP stubs; inspect actual business state after errors rather than asserting only `StepVerifier.expectError()`.

## 21. Observability and operations

### 21.1. Signals to distinguish

| Signal | Layer | Meaning |
| --- | --- | --- |
| Active RSocket connections | Transport | Peer connectivity |
| Active request-response | Responder | In-flight calls |
| Active request-stream/channel | Responder | Subscriptions, memory |
| Route latency p95/p99 | Messaging | Slow routes |
| Route errors by category | Messaging | Mapping/validation/SQL/network |
| Cancellation rate | Stream | Slow/disconnected clients |
| Reconnect attempts | Client | Network instability |
| Keepalive failures | Transport | Connection liveness |
| Hikari active/pending | Database | JDBC bottleneck |
| HTTP downstream 429/503 | Adapter | Partner overload |
| Outbox pending oldest age | Workflow | Durable intent backlog |
| Duplicate operationId | Business | Replay deduplicated |
| Business confirmed count | Domain | Actual commits |
| Unsupported schema version | Contract | Writer/reader drift |

Actuator/Micrometer/Reactor Netty provide metrics/observation capabilities depending on version and config, yet do not assume every row above is exported automatically. Business confirmations, outbox age, and idempotency need explicit instrumentation.

### 21.2. Metrics cardinality

Appropriate tags:

~~~text
route=inventory.reserve
transport=tcp
outcome=confirmed|rejected|unknown
error_type=validation|auth|db|network
schema_version=1|2
~~~

Never put `operationId`, `sku`, `customerId`, emails, raw payloads, or bearer tokens into Prometheus labels. Correlation IDs belong in structured logs under redaction/access-control policies.

### 21.3. Multi-layer tracing

~~~text
RSocket inventory.reserve
  -> metadata auth/authorization
  -> payload decode + validation
  -> concurrency admission
  -> JDBC transaction (reservation + receipt)
  -> COMMIT
  -> RSocket response encode/send
~~~

With an outbox:

~~~text
  -> outbox insert in same SQL transaction
  -> relay after COMMIT
  -> Kafka/Rabbit/HTTP partner
  -> consumer inbox + business commit
~~~

Transport completion and business completion are **two distinct signals**; dashboards must distinguish them clearly.

## 22. Runbook when @MessageMapping does not work

| Symptom | Common cause | Diagnostic steps |
| --- | --- | --- |
| TCP connection refused | Port not open / RSocket server not started | Starter, `spring.rsocket.server.port`, startup logs |
| Connects but unknown route | Wrong route / bean not scanned | `@Controller`, `@MessageMapping`, spelling |
| DTO fails to decode | MIME/codecs/schema mismatch | `RSocketStrategies`, payload fixtures |
| Missing field errors | Required/null/default mismatch | Contract/Bean Validation |
| `Mono` never executes | No subscriber | Return publisher through outer pipeline |
| Event-loop latency spikes | Direct blocking JDBC/HTTP | Thread profiles, offloading |
| Hikari timeout | Too many DB calls / long transactions | Pool active/pending, SQL locks |
| Client times out yet DB committed | Response lost | Query receipt, `operationId` |
| Reservation processed twice | Retry generated new key | SQL UNIQUE/idempotency |
| FNF “success” yet audit missing | No application receipt | Durable handoff |
| Flux memory climbs | Unbounded buffers/streams | Bounded concurrency/overflow |
| Canceled yet resources linger | Missing cleanup | `doFinally`, resource ownership |
| Stream misses updates on reconnect | No replay source | Durable log/cursor |
| Channel replies out of order | `flatMap` or parallel writes | `concatMap`/version guards |
| TLS/auth failure | CA, hostname, credentials, route ACL | Transport/security integration |
| Idle disconnect | LB/proxy timeout, keepalive | Keepalive, network config |
| Reconnect storm | Retries without backoff/jitter | Client admission strategy |
| Code rollback cannot read new schema | Unplanned data evolution | Versioned routes/adapters |
| Missing metrics | Instrumentation disabled | Actuator/Micrometer/custom counters |

### 22.1. Investigation order

1. Check transport/port/TLS/connection setup.
2. Inspect requester routing metadata.
3. Confirm `@Controller` beans and `@MessageMapping` routes registered.
4. Check data MIME, codecs, `schemaVersion`, and validation.
5. Verify authentication/tenant authorization.
6. Measure event loop, schedulers, Hikari, and HTTP partner capacity.
7. Separate request attempted, responder received, database COMMIT, and response received.
8. On timeouts, look up stable `operationId` before retrying.
9. Inspect active subscriptions, cancellations, and buffer pressure.
10. Reproduce with a real TCP connection / fault-injection test.

Never delete outbox/receipt records or generate fresh keys just to clear a pending queue.

## 23. Common anti-patterns

| Anti-pattern | Why it is wrong | How to fix |
| --- | --- | --- |
| Treating `@MessageMapping` like HTTP `@PostMapping` | Different routing/transport/errors | Use RSocket route metadata |
| Omitting server port | Responder has no listener | Configure Boot RSocket server |
| Calling Java methods directly in unit tests | Misses mapping/codecs | Real RSocket integration tests |
| Using FNF for business needing receipts | Caller cannot know target commit | Request-response + idempotency |
| Calling JDBC before `Mono.just` | Blocks event loop | `Mono.fromCallable` + `boundedElastic` |
| Using `Schedulers.parallel()` for blocking SQL | Starves CPU workers | Appropriate scheduler/resource boundary |
| Unbounded `onBackpressureBuffer()` | OOM | Bounded buffer/durable log |
| One SQL transaction across an unbounded stream | Holds JDBC connections/locks | Per-item transactions |
| Using RSocket stream ID to dedupe | Unstable transport identity | Business `operationId` |
| `timeout -> retry with new UUID` | Duplicates side effects | `UNKNOWN` + stable ID/reconciliation |
| Assuming `send()` is a business ACK | No application reply | Durable results/status |
| Assuming reconnect restores stream history | No durable replay | Cursors/event log |
| Unlimited request streams | Overloads DB/HTTP downstream | Quotas/bulkheads |
| `flatMap` while expecting strict output order | Concurrent results reorder | `concatMap`/version guards |
| Trusting metadata `tenantId` | Easily spoofed | Authenticated principal + ACL |
| Disabling certificate validation | MITM/credential leaks | TLS trust/hostname verification |
| Logging full payloads/tokens | Security/privacy leak | Redaction |
| Treating Mono completion as all downstream done | May only mean accepted | Business receipts/status |
| Ignoring cancellation | Resource leaks | Cleanup/lifecycle ownership |
| Auto-retrying every error | Retry storms / permanent errors | Error taxonomy + retry budgets |

## 24. Production checklist

- [ ] RSocket chosen because request/stream/channel is genuinely needed, not novelty.
- [ ] Spring Boot/Reactor/RSocket Java versions aligned via BOM.
- [ ] TCP/WebSocket transport, ports, TLS, load balancers, and readiness configured properly.
- [ ] `@Controller` scanned; `@MessageMapping` routes free of collisions/conflicts.
- [ ] Routes, DTO/MIME/`schemaVersion`/error semantics published as contracts.
- [ ] Responder/requester match interaction models: RR, FNF, stream, channel.
- [ ] FNF avoided for commands needing business receipts unless backed by durable handoff.
- [ ] Requesters manage connections, keepalives, reconnect/backoff, and shutdown.
- [ ] Payload codecs/metadata extraction configured and tested over the wire.
- [ ] Authentication/authorization enforced per route and domain resource; caller-supplied `tenantId` not trusted.
- [ ] Bean Validation and malformed payload/error mapping verified.
- [ ] No direct blocking SQL/HTTP/Redis on the event loop.
- [ ] Blocking adapters use `boundedElastic`/workers with admission/bulkhead caps.
- [ ] Hikari, HTTP pools, Redis, brokers, and replica counts fit capacity budgets.
- [ ] Streams enforce demand, bounded buffers, max subscribers, and cancellation cleanup.
- [ ] Channels use per-item transactions, partial failure handling, and replay policies.
- [ ] Business commands carry stable `operationId` and SQL unique constraints.
- [ ] Timeouts/lost responses after COMMIT map to `UNKNOWN`/reconciliation.
- [ ] Outbox/inbox or durable broker used when process crash recovery is required.
- [ ] Retries have deadlines, attempt limits, backoff/jitter, and error classification.
- [ ] Schema evolution tested for old/new writers-readers, replay, and rollback.
- [ ] Real RSocket connection tests cover all 4 interaction models and route mapping.
- [ ] PostgreSQL Testcontainers verify transactions/idempotency/unique races.
- [ ] Fault-injection tests cover disconnect after commit, cancel, and reconnect.
- [ ] Metrics separate transport sends, route errors, business COMMITs, and outbox lag.
- [ ] No tokens, PII, passwords, or high-cardinality IDs exposed in metrics/logs.

**Key takeaway:** Configuring an RSocket responder in Spring Boot usually starts with `@Controller` and `@MessageMapping("route")`, paired with `Mono`/`Flux` for the four interaction models. These annotations **receive and reply to messages**, but cannot replace **data contracts, resource limits, transactions, outbox/inbox, idempotency, `UNKNOWN` outcome handling, and observability**. Production responders must be tested across both happy paths and fault windows before and after target commits.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): requester/responder architecture.
- [Spring Framework — Annotated RSocket Responders](https://docs.spring.io/spring-framework/reference/rsocket/rsocket-annotated.html): `@MessageMapping`, signatures, routing.
- [Spring Framework — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket/rsocket-requester.html): RR, FNF, stream, channel.
- [Spring Framework — RSocketStrategies](https://docs.spring.io/spring-framework/reference/rsocket/rsocket-strategies.html): codecs, metadata, MIME.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): server auto-config, TCP/WebSocket.
- [RSocket Protocol Specification](https://rsocket.io/about/protocol/): RSocket interaction models, frames, demand.
- [RSocket Java](https://github.com/rsocket/rsocket-java): transport/connector implementation.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, schedulers, backpressure.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/): `StepVerifier`, cancellation tests.
- [Spring Security — RSocket](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): authentication/authorization.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): JDBC/reactive transaction boundaries.
- [Spring Integration — Reference](https://docs.spring.io/spring-integration/reference/): message channels/adapters.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): JDBC, HikariCP, pool sizing.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): SQL transaction tests.
- [Testcontainers — Toxiproxy](https://java.testcontainers.org/modules/toxiproxy/): network fault injection.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate-safe processing.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): durable intent + retry after commit.

# Publishing Order Events from REST with StreamBridge

A Spring Cloud Stream application does not always have to receive its initial message from Kafka, RabbitMQ, or Pulsar. The event source can be a REST API: a client submits an order creation request, the application validates the data, creates a domain event, and publishes the event to a broker so downstream services can process it independently.

`StreamBridge` serves as the bridge for that scenario. It allows a controller or service that is not a `Supplier` to send an object or a `Message` to a Spring Cloud Stream output binding. The binder still performs payload conversion, partitioning, and message delivery according to the binding configuration. This exercise builds the **REST → Order API → StreamBridge → Kafka/RabbitMQ/Pulsar → consumer** flow while clarifying static bindings versus dynamic destinations, HTTP responses, event schemas, send failures, idempotency, transactional outbox, and testing.

## 1. Objectives and Processing Flow

After completing this exercise, you will be able to:

- Receive order creation requests via REST and validate the request.
- Create an event decoupled from the REST API DTO.
- Send events via `StreamBridge` to a clearly named output binding.
- Configure destination, binder, content type, and headers.
- Return HTTP `202 Accepted` appropriate for asynchronous processing.
- Distinguish static bindings from dynamic destinations.
- Handle rejected sends or asynchronous publishing failures.
- Design idempotency and transactional outbox when requests must not be lost.
- Test using the Test Binder and integration tests against a real broker.

### Minimal Dependencies

Maven example for a REST API publishing through Kafka:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-kafka</artifactId>
</dependency>
~~~

Manage Spring Boot and Spring Cloud Stream versions with mutually compatible BOMs; do not manually mix binder and framework versions from different release trains. If using RabbitMQ or Pulsar, swap in the corresponding binder dependency.

Basic flow:

~~~text
Client
  |
  | POST /api/orders
  v
Order REST Controller
  | validate request / authenticate
  v
Order Application Service
  | create OrderCreated event
  v
StreamBridge.send("orders-out-0", message)
  |
  v
Spring Cloud Stream output binding
  |
  v
Kafka topic / Rabbit exchange+queue / Pulsar topic
  |
  +--> inventory-service
  +--> payment-service
  +--> notification-service
~~~

REST requests and event messages serve different purposes. A request describes what the client wants; an event describes what the system has confirmed occurred. Do not publish the raw request DTO if it contains UI-only fields, sensitive information, or an unstable structure.

## 2. Choosing a Static Output Binding

If orders are always sent to a known destination, declare the output binding at application startup:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
          binder: kafka
~~~

In this example:

- `orders-out-0` is the logical binding name passed by application code to `StreamBridge`.
- `orders.created` is the destination on the broker, such as a Kafka topic or the binder's equivalent destination.
- `content-type: application/json` describes the payload format so Spring Cloud Stream performs conversion.
- `binder: kafka` selects the configured binder named `kafka`. If the application has only one default binder, this property may be omitted.
- `output-bindings` requests binding creation before the first REST request arrives.

This is the right choice when the business flow has a fixed destination. It surfaces configuration errors early at startup, makes monitoring straightforward, and makes destination access control easier to enforce.

If the application uses RabbitMQ, swap the binder and configure the corresponding connection while keeping the logical binding name if you want code to stay broker-agnostic:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
          binder: rabbit
~~~

For Pulsar, use the configured Pulsar binder and a destination matching that binder's conventions. Do not apply Kafka or RabbitMQ producer configurations to Pulsar merely because the binding names look similar.

## 3. Declaring the Event Contract

Create an event representing an accepted order:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record OrderCreated(
    UUID eventId,
    int schemaVersion,
    String orderId,
    String customerId,
    List<OrderLine> lines,
    BigDecimal total,
    String currency,
    Instant occurredAt,
    String correlationId
) {
    public OrderCreated {
        lines = List.copyOf(lines);
    }

    public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
    ) { }
}
~~~

Fields should carry stable meanings:

| Field | Purpose |
|---|---|
| `eventId` | Unique ID for the event emission; supports deduplication |
| `schemaVersion` | Contract version so consumers know how to interpret it |
| `orderId` | Domain order ID |
| `customerId` | Business principal; include in the event only if consumers need it |
| `lines` | Confirmed order line items |
| `total`/`currency` | Total monetary amount and currency code |
| `occurredAt` | Timestamp when the business event occurred, in UTC |
| `correlationId` | Links processing steps belonging to the same request |

Do not use the consumer's message reception time in place of `occurredAt`. Do not use `eventId` in place of `orderId`: a single order can emit multiple event types over its lifecycle.

Events should be immutable records or getter-only classes. Once published, do not mutate an old event by overwriting it; if new information is needed, emit a subsequent event or define a compatible schema evolution.

## 4. Creating Separate REST Request and Response DTOs

The DTO received over HTTP is not the event:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;
import java.util.List;

public record CreateOrderRequest(
    @NotBlank String customerId,
    @jakarta.validation.constraints.Pattern(regexp = "[A-Z]{3}")
    String currency,
    @NotEmpty List<@Valid OrderLineRequest> lines
) {
    public record OrderLineRequest(
        @NotBlank String sku,
        @Positive int quantity,
        @Positive BigDecimal unitPrice
    ) { }
}
~~~

The response indicates that the API has accepted the request:

~~~java
import java.net.URI;

public record OrderAcceptedResponse(
    String orderId,
    String eventId,
    String status
) { }
~~~

An API can return `orderId` so the client can query status from another endpoint. Do not claim the order has been paid unless payment actually completed within the same workflow.

## 5. Building the Event from the Request and Sending with StreamBridge

The service is responsible for transforming the request into an event:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class OrderCommandService {

    private final StreamBridge streamBridge;

    public OrderCommandService(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public OrderCreated submit(CreateOrderRequest request) {
        BigDecimal total = request.lines().stream()
            .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        UUID eventId = UUID.randomUUID();
        String orderId = UUID.randomUUID().toString();
        String correlationId = UUID.randomUUID().toString();

        var lines = request.lines().stream()
            .map(line -> new OrderCreated.OrderLine(
                line.sku(), line.quantity(), line.unitPrice()))
            .toList();

        OrderCreated event = new OrderCreated(
            eventId,
            1,
            orderId,
            request.customerId(),
            lines,
            total,
            request.currency(),
            Instant.now(),
            correlationId
        );

        Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader("eventId", eventId.toString())
            .setHeader("correlationId", correlationId)
            .setHeader(
                org.springframework.messaging.MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
            )
            .build();

        boolean sent = streamBridge.send("orders-out-0", message);
        if (!sent) {
            throw new EventPublicationRejectedException(
                "Output binding did not accept the order event");
        }

        return event;
    }
}
~~~

This is an exercise demonstrating the event path; real projects should add checks for pricing, inventory, currency rules, purchase authorization, and persisting the order within a business transaction.

Key points to remember:

- Inject `StreamBridge` from the `org.springframework.cloud.stream.function` package.
- Pass the **logical binding name** `orders-out-0`, not the topic name `orders.created`, when a static binding is declared.
- You can pass a POJO directly; the framework performs output conversion according to the binding configuration. Pass a `Message` when you need to set explicit headers.
- The `contentType` header helps specify conversion; the binding configuration can also define the content type.
- `send` returns a boolean. If `false`, the channel did not accept the message; the application must not return an accepted status as if it had been sent.
- If the binder delivers send results asynchronously, broker errors can occur after the `send` call returns; configure and handle send failures appropriately for the binder.

Do not forward all HTTP headers into the event. Only pass correlation ID, tenant, or trace context when a clear contract exists, sensitive data has been filtered out, and consumers genuinely need it.

## 5.1. Downstream Consumer Receiving the Event

To complete the end-to-end illustration, an independent service can consume the event via a function:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryFunctions {

    @Bean
    Consumer<OrderCreated> reserveInventory(InventoryService inventory) {
        return event -> inventory.reserve(
            event.orderId(),
            event.lines()
        );
    }
}
~~~

Input binding configuration in the inventory service (binding properties sit under `spring.cloud.stream`):

~~~yaml
spring:
  cloud:
    function:
      definition: reserveInventory
    stream:
      bindings:
        reserveInventory-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
~~~

Producer and consumer must use compatible schemas. The consumer must process idempotently by `eventId`/`orderId` because the broker may redeliver messages after restarts or commit failures. Each service has its own consumer group if each needs a copy of every event; instances of the same service share a group to balance load.

## 6. Creating the REST Endpoint

The controller validates the request before calling the service:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.net.URI;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderCommandService orderCommandService;

    public OrderController(OrderCommandService orderCommandService) {
        this.orderCommandService = orderCommandService;
    }

    @PostMapping
    public ResponseEntity<OrderAcceptedResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderCreated event = orderCommandService.submit(request);

        var response = new OrderAcceptedResponse(
            event.orderId(),
            event.eventId().toString(),
            "ACCEPTED"
        );

        return ResponseEntity
            .accepted()
            .location(URI.create("/api/orders/" + event.orderId()))
            .body(response);
    }
}
~~~

HTTP `202 Accepted` is appropriate when a request has been accepted for asynchronous processing while downstream workflows have not yet completed. It does not mean inventory, payment, or notification has succeeded.

If `send` returns `false` or a synchronous error occurs before the request is accepted, the API can return `503 Service Unavailable` so the client retries according to policy. If the request is invalid, return `400 Bad Request`. If an idempotency key has already been used for different content, return `409 Conflict`.

Example exception and synchronous publish error mapping:

~~~java
public class EventPublicationRejectedException
        extends RuntimeException {
    public EventPublicationRejectedException(String message) {
        super(message);
    }
}
~~~

~~~java
@RestControllerAdvice
class OrderApiExceptionHandler {

    @ExceptionHandler(EventPublicationRejectedException.class)
    ResponseEntity<Map<String, String>> publicationRejected(
            EventPublicationRejectedException exception) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of(
                "code", "EVENT_PUBLICATION_REJECTED",
                "message", "Order event could not be accepted"
            ));
    }
}
~~~

Do not expose internal exception details to clients. In production systems, include an error code/correlation ID and log the sanitized root cause.

## 7. Send Success Does Not Mean the Consumer Finished Processing

Distinguish these milestones:

| Milestone | Meaning |
|---|---|
| REST validation passed | The request is structurally valid and passed checked rules |
| `StreamBridge.send` returns `true` | The output channel accepted the message according to the binding's send mechanism |
| Broker publisher acknowledgement | The broker confirmed publication according to binder/protocol semantics |
| Consumer receives message | A consumer group/subscription fetched the message |
| Consumer finishes processing | Downstream business logic completed |
| Consumer commit/ack | Consumption progress is acknowledged on the broker |

`StreamBridge.send` returning `true` does not prove a consumer received or processed the event. With asynchronous producers/binders, this boolean must also not be interpreted as proof that the broker durably persisted the message. Read the binder documentation and enable publisher confirms/acknowledgements or the appropriate send-result mechanism if API guarantees depend on broker acknowledgement.

By default, `StreamBridge` sends on the caller's thread. You can call `setAsync(true)` to offload sending to an executor when you want to avoid blocking the request thread; however, this changes when errors are observed and can affect trace context propagation. Enable it only after configuring bounded executors, metrics, error handling, and load testing.

~~~java
streamBridge.setAsync(true);
boolean acceptedByChannel =
    streamBridge.send("orders-out-0", message);
~~~

The snippet above only illustrates the asynchronous API; do not rely solely on the returned boolean to decide whether a publish was confirmed by the broker. When async is enabled, configure Micrometer context propagation if trace context must cross thread boundaries, and handle send failures per binder.

## 8. Pre-Create Output Bindings or Use Dynamic Destinations?

### Output Binding Created at Startup

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
~~~

Send using:

~~~java
streamBridge.send("orders-out-0", event);
~~~

Advantages: fixed destination, explicit configuration, provisioning occurs at startup, and the binding can be observed like any standard output binding.

### Dynamic Destinations When Runtime Target Selection Is Truly Needed

~~~java
streamBridge.send("orders.created", event);
~~~

If `orders.created` is not yet a binding, `StreamBridge` can create an output binding dynamically and ask the binder to provision a destination with that name. Dynamic bindings are cached for reuse; the cache has an eviction mechanism with a default size of 10 in current documentation. Dynamic bindings are not managed in the application context the same way statically declared bindings are.

If clients are allowed to pass arbitrary destinations via URL or JSON, a single request could create numerous destinations and increase risks of resource exhaustion, misrouted data, or broker abuse. If dynamic destinations are genuinely required:

- Enforce an allow-list using `spring.cloud.stream.dynamicDestinations`.
- Map a validated business code to a destination from a server-side catalog.
- Never use an unvalidated path variable or request field directly as a topic/exchange name.
- Monitor dynamic binding count, cache evictions, and provisioning errors.

Example destination restriction:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.created
        - orders.priority
~~~

When destinations are known in advance, prefer static output bindings over dynamic bindings.

## 9. Multiple Binders in the Same Application

An application can consume messages from Kafka and publish events to RabbitMQ. With `StreamBridge`, an overload lets you specify the binder name when creating a dynamic binding:

~~~java
streamBridge.send("orders-out-0", "rabbit", message);
~~~

However, if the output binding was already created by `spring.cloud.stream.output-bindings` or previously bound to a binder, the binder name parameter in `send` does not change the attached binder. When you want a fixed binder, declare it directly on the binding:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          binder: rabbit
~~~

The name `rabbit` must match a configured named binder instance. Do not confuse the binder name with the middleware type or destination name.

## 10. Choosing Content Type and Headers

Spring Cloud Stream supports content types configured on the binding or in message headers. For REST → StreamBridge:

- Static bindings can set `content-type: application/json`.
- Sending a `Message` can set `MessageHeaders.CONTENT_TYPE`.
- The `send(bindingName, data, MimeType)` overload allows specifying the output content type.

Example:

~~~java
boolean sent = streamBridge.send(
    "orders-out-0",
    event,
    MimeTypeUtils.APPLICATION_JSON
);
~~~

Pick one consistent contract between producer and consumer. If `useNativeEncoding` is enabled for Kafka, serialization is delegated to the Kafka client serializer and no longer relies on the default content-type conversion path. In that case, serializer and deserializer configurations must be compatible across applications.

Commonly useful headers:

| Header | Purpose |
|---|---|
| `eventId` | Event identification and deduplication |
| `correlationId` | Tracking a single business flow |
| `contentType` | Guides payload conversion |
| `traceparent` | W3C trace context when properly propagated |
| `tenantId` | Only when the multi-tenant contract permits it and the value has been validated |

Do not forward Authorization bearer tokens, cookies, session IDs, passwords, or raw HTTP header maps to the broker.

## 11. Publish Failures and REST Responses

Failures can happen at multiple points:

| Stage | Example | Handling |
|---|---|---|
| Before send | Request validation, event mapping failure | Return 400 or appropriate business error |
| Binding creation | Wrong binder, missing destination, provisioning failure | Log with correlation ID, return service error; fix configuration |
| Channel send | Channel rejects or lacks a suitable subscriber | Check boolean return, do not return accepted |
| Producer/broker async | Network timeout, broker unavailable, authorization error | Enable appropriate send-failure handling, alert/retry under control |
| After publish | Consumer error, incompatible schema, downstream timeout | Consumer retry/DLQ/recovery; REST API cannot synchronize this result |

The `error-channel-enabled` binding property can enable an error channel for async send results when supported by the binder. With the Kafka binder, send failures can be routed as an `ErrorMessage` containing `KafkaSendFailureException`; the binder does not automatically send producer exceptions to a DLQ the way it handles consumer failures. Build a dedicated producer error-handling flow and do not assume consumer DLQ semantics apply to REST producers.

Do not retry infinitely inside a REST request. A client might time out and retry while the first publish already succeeded. Use an idempotency key and request state to prevent creating duplicate orders.

## 12. Idempotency for REST Retries

A common failure scenario:

1. The client sends `POST /api/orders`.
2. The server publishes the event successfully, but the response is lost on the network.
3. The client retries the same request.
4. If the server generates a new `orderId`/`eventId`, downstream systems may create two orders.

The API design should accept an `Idempotency-Key`:

~~~http
POST /api/orders
Idempotency-Key: 8e5a...client-generated-key
Content-Type: application/json
~~~

Store the key alongside a request hash and processing outcome in a durable store with a unique constraint:

- New key: record the request and create a single operation.
- Existing key with the same request hash: return the same `orderId`/`eventId` or current operation status.
- Existing key with a different request hash: return `409 Conflict`.

Do not store idempotency keys only in the memory of a single pod: retries can hit another instance or arrive after a restart. Key TTL/retention must outlast client retry windows and business workflows.

REST-level idempotency does not replace consumer-level idempotency. Consumers still need to deduplicate by `eventId` or apply unique constraints / the inbox pattern because the broker can redeliver messages.

When applying this to the earlier controller, require the header and route requests through a persistently backed idempotency component:

~~~java
@PostMapping
public ResponseEntity<OrderAcceptedResponse> create(
        @Valid @RequestBody CreateOrderRequest request,
        @RequestHeader("Idempotency-Key") String idempotencyKey) {

    // This facade atomically claims the key, checks the request hash,
    // and returns the same operation for a repeated identical request.
    OrderCreated event =
        idempotentOrderSubmission.submit(idempotencyKey, request);

    return ResponseEntity.accepted()
        .location(URI.create("/api/orders/" + event.orderId()))
        .body(new OrderAcceptedResponse(
            event.orderId(), event.eventId().toString(), "ACCEPTED"));
}
~~~

`IdempotentOrderSubmission` is an application service backed by a database repository/transaction; do not replace it with an in-memory `ConcurrentHashMap`, as multiple instances and restarts break uniqueness. If using the transactional outbox in the next section, claiming the idempotency key, saving the order, and inserting the outbox row should execute inside the same database transaction.

## 13. Transactional Outbox When Requests Must Not Be Lost

Sending an event directly from REST to the broker and writing the order to the database are two operations across two separate systems. If the database commits while publishing fails, the order exists without an emitted event. If publishing succeeds and the database rolls back, consumers may receive an event for an order that was never saved.

When order acceptance must be durable, use the **transactional outbox** pattern:

~~~text
REST request
   |
   v
Database transaction
   |-- insert order
   |-- insert outbox event (same transaction)
   v
Commit database
   |
   v
Outbox relay reads pending event
   |
   v
StreamBridge -> broker
   |
   v
Broker confirms publish
   |
   v
Mark outbox row as published
~~~

The REST API returns `202 Accepted` after the database transaction persists both the order and the outbox record. The relay can retry when the broker is unavailable. If the relay crashes after the broker received the event but before marking the outbox row as published, the event may be resent; consumers must be idempotent by `eventId`.

Do not mark an outbox row as published merely because `StreamBridge.send` returned `true` if the binder sends asynchronously without broker confirmation. Integrate publisher confirms/acks or the binder's send-result mechanism to determine when it is safe to mark as published. Do not claim exactly-once semantics across database and broker without an appropriate distributed transaction mechanism.

An outbox also needs:

- Indexes on pending status and creation timestamp.
- Batch/claim locking so multiple relays do not publish the same row twice.
- Retry with backoff and alerts when rows age past thresholds.
- A cleanup mechanism after the retention period.
- Metrics for pending count, oldest pending age, publish errors, and retry count.
- Consumer inbox/deduplication to tolerate duplicates.

## 14. Binder-Specific Producer Configuration

### Kafka Binder

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
      kafka:
        bindings:
          orders-out-0:
            producer:
              sync: false
              configuration:
                acks: all
                enable.idempotence: true
                compression.type: lz4
~~~

Kafka properties should be chosen based on durability and throughput requirements. `acks=all` paired with replication/`min.insync.replicas` is appropriate when broker acknowledgment across replicas is required; `enable.idempotence` reduces duplicates from producer retries within Kafka producer guarantees. Compression saves network and disk at the cost of CPU. Do not treat producer idempotence as business-level idempotency for order consumers.

### RabbitMQ Binder

RabbitMQ uses exchanges, queues, routing keys, delivery modes, and publisher confirms according to binder configuration. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
      rabbit:
        bindings:
          orders-out-0:
            producer:
              delivery-mode: PERSISTENT
~~~

Verify exchange/queue durability, message persistence, and publisher confirms/returns according to the binder version and broker policy. A durable queue does not automatically make every message persistent; topology durability and delivery mode are two separate concerns.

### Pulsar Binder

Pulsar has its own topics, schemas, producer batching, and send timeouts. Keep the `content-type`/schema contract aligned with consumers and configure the producer per the Pulsar binder documentation for your project version. Do not copy Kafka `acks` or RabbitMQ `delivery-mode` properties into Pulsar configuration.

## 15. Endpoint and Destination Security

The REST endpoint is the public boundary of the event flow. You should:

- Authenticate clients and authorize order creation permissions.
- Validate quantity, currency, SKU, and cap line item counts.
- Enforce request body size limits, rate limits, and timeouts.
- Never allow clients to specify topics, exchanges, or binders directly.
- Never allow clients to supply arbitrary event IDs unless governed by a verified convention.
- Filter headers; never forward tokens or cookies into messages.
- Use TLS and proper credentials for both REST and the broker.
- Restrict producer permissions so it can only publish to required destinations.
- Protect Actuator, metrics, and error endpoints.
- Log event IDs/correlation IDs; do not log payment details or sensitive payloads.

In multi-tenant systems, extract the tenant ID from the authenticated security context or validate it against a server-side catalog; never trust an arbitrary client-supplied header.

## 16. Testing Services with StreamOperations

`StreamBridge` implements the `StreamOperations` contract containing the send methods. You can inject this interface to mock it in unit tests:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderCommandServiceTest {

    @Mock
    StreamOperations streamOperations;

    @Test
    void publishesOrderCreatedEvent() {
        when(streamOperations.send(
            eq("orders-out-0"), any(Message.class)))
            .thenReturn(true);

        // Construct service with StreamOperations in this test variant.
        // Submit a valid request and capture the Message.

        ArgumentCaptor<Message<?>> captor =
            ArgumentCaptor.forClass(Message.class);
        verify(streamOperations).send(
            eq("orders-out-0"), captor.capture());

        assertThat(captor.getValue().getPayload())
            .isInstanceOf(OrderCreated.class);
    }
}
~~~

This example focuses on mocking and capturing the message; the service constructor can accept `StreamOperations` rather than concrete `StreamBridge` for easier testing. At runtime in the application context, Spring provides `StreamBridge` implementing this interface.

Assertions to include:

- Exact binding name.
- Payload is `OrderCreated`, not the REST request DTO.
- `eventId` and `orderId` are distinct per contract.
- `contentType` header is JSON.
- `correlationId` is preserved across logs, responses, and events.
- When `send` returns `false`, the service does not return an accepted result.

## 17. Integration Testing with the Test Binder

The Test Binder verifies the flow inside the JVM without requiring Kafka, RabbitMQ, or Pulsar:

~~~java
@SpringBootTest(properties = {
    "spring.cloud.stream.output-bindings=orders-out-0",
    "spring.cloud.stream.bindings.orders-out-0.destination=orders.created",
    "spring.cloud.stream.bindings.orders-out-0.content-type=application/json"
})
@EnableTestBinder
class OrderStreamBridgeIntegrationTest {

    @Autowired
    StreamBridge streamBridge;

    @Autowired
    OutputDestination output;

    @Test
    void sendsOrderEventToConfiguredOutputBinding() {
        OrderCreated event = sampleOrderCreated();

        assertThat(streamBridge.send("orders-out-0", event))
            .isTrue();

        Message<byte[]> received =
            output.receive(1_000, "orders-out-0");

        assertThat(received).isNotNull();
        assertThat(received.getHeaders().get(
            MessageHeaders.CONTENT_TYPE).toString())
            .contains("application/json");
    }
}
~~~

In some versions or test configurations, the destination argument to `OutputDestination.receive` is either the binding name or the destination name depending on how the test binder exposes output; check the API for your version. You can deserialize the payload bytes into `OrderCreated` with Jackson and assert its fields. If `@EnableTestBinder` is not used, configure the test binder according to your project version's guide.

The Test Binder does not verify that a real broker provisioned topics/queues, publisher confirms, Kafka partitions/acks, RabbitMQ exchange/queue durability, or Pulsar subscriptions. Always maintain integration tests against the target broker in CI or a test environment.

## 18. REST API Tests and HTTP Contracts

Use MockMvc or WebTestClient to verify:

| Request | Expected outcome |
|---|---|
| Valid body | `202 Accepted`, includes order ID and event ID |
| Missing customer ID | `400 Bad Request` |
| Quantity zero or negative | `400 Bad Request` |
| Unsupported currency | `400 Bad Request` or defined domain error |
| StreamBridge returns false | Transient error, e.g. `503` |
| Synchronous broker send failure | Error mapped to an appropriate response |
| Same idempotency key and same request | Returns the same operation/order without emitting a new event |
| Same idempotency key with different request | `409 Conflict` |
| Unauthorized to create order | `401`/`403` |

Do not include stack traces or internal broker names in public responses. Return an error code and correlation ID for operations teams to investigate.

## 19. Operations and Observability

Dashboards for REST → StreamBridge should track:

- Order creation request rate, 2xx/4xx/5xx counts, and p50/p95/p99 latency.
- Validation failures, idempotency hits/conflicts.
- `StreamBridge.send` invocation counts, true/false/exception outcomes.
- Producer send latency, async send failures, and broker confirmations where available.
- Binding creation/provisioning failures and dynamic binding cache evictions if dynamic destinations are used.
- Broker topic/queue depth, consumer lag, retries, and DLQ counts.
- Outbox pending count, oldest pending age, and retry count if using an outbox.
- Event ID and correlation ID across producer and consumer.

Do not use `orderId` or `eventId` as metric labels because cardinality grows with traffic. They belong in controlled logs and traces. Metrics should use bounded-cardinality labels such as binding name, normalized destination, status code, and error type.

Configure alerts when producer send errors rise, outbox rows grow stale, queue depth/lag climbs continuously, or consumer completion rates drop. The REST endpoint may continue returning 202 while downstream is backed up, so both the broker and consumers must be monitored.

## 20. Step-by-Step Practice Workflow

1. Create a Spring Boot app with Spring Web, Validation, Spring Cloud Stream, and the Kafka or RabbitMQ binder.
2. Create separate `OrderCreated` event and `CreateOrderRequest` DTO classes.
3. Declare output binding `orders-out-0` pointing to destination `orders.created`.
4. Inject `StreamBridge` into the service; map the request to an event and send the message.
5. Create `POST /api/orders` with `@Valid` and a `202 Accepted` response.
6. Send a valid request and verify the event on the broker or Test Binder.
7. Test requests with missing fields, negative quantities, invalid currencies, and event conversion failures.
8. Pause the broker or revoke publish permissions in a test environment to verify send failure handling.
9. Send the same idempotency key multiple times; verify duplicate orders/events are not created.
10. Run a downstream consumer, verify the event schema is correct, and ensure business logic is idempotent.
11. If durable acceptance is required, add a database transaction + outbox relay + broker confirmation.
12. Run increasing load tests and observe REST latency, producer send errors, broker backlog, and consumer lag.

HTTP example:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customerId": "customer-42",
    "currency": "VND",
    "lines": [
      {"sku": "SKU-100", "quantity": 2, "unitPrice": 125000},
      {"sku": "SKU-200", "quantity": 1, "unitPrice": 75000}
    ]
  }'
~~~

The request above matches the basic illustrative controller. If you have applied the idempotency variant from section 12, include the `Idempotency-Key` header per the API contract.

The response takes the form:

~~~http
HTTP/1.1 202 Accepted
Location: /api/orders/<order-id>
Content-Type: application/json

{
  "orderId": "<order-id>",
  "eventId": "<event-id>",
  "status": "ACCEPTED"
}
~~~

ID values are illustrative only; the server generates real IDs and persists them according to idempotency rules.

## 21. Common Issues

| Symptom | Cause | Resolution |
|---|---|---|
| Output binding not found | Typo in binding name or missing `output-bindings`/dynamic setup | Compare the name in code with `output-bindings` and `bindings` |
| Unexpected topic/exchange appears | Dynamic destination used or `destination` missing | Declare static binding and explicit destination |
| `send` returns false | Channel did not accept the message | Check binding lifecycle, channel, and binder |
| `send` returns true but consumer sees no event | Async broker send failed, wrong topic/group, consumer not running, or serialization mismatch | Check send failures, broker metadata, destination, and consumer |
| JSON fails to deserialize | Content type, serializer, or schema mismatch | Check binding content type, Message headers, and native encoding |
| REST returns 202 but event is lost | Relied only on channel send without durable outbox/confirm | Use publisher confirmation or transactional outbox |
| Client retry creates two orders | Missing idempotency key or key stored only in memory | Use a persistent unique constraint |
| Consumer processes event twice | Redelivery or outbox relay retry | Deduplicate using event ID/inbox/unique constraint |
| Dynamic bindings keep growing | Destination taken directly from input | Allow-list, normalize destinations, and monitor cache |
| Trace breaks on async send | Thread boundary did not propagate context | Configure Micrometer context propagation |
| Producer error does not go to DLQ | Consumer DLQ does not handle producer send failures | Use the binder's producer error channel/send result |
| Multiple binders send to wrong broker | Binder name mismatch or binding already created with another binder | Declare `binder` on the static binding and verify named binders |

## 22. Pre-Production Checklist

- [ ] REST request DTO and event contract are separated.
- [ ] Requests are validated and authenticated/authorized before publishing.
- [ ] Events include event ID, schema version, `occurredAt`, and correlation ID.
- [ ] Static output bindings declare explicit destination and binder when destination is known.
- [ ] Content type, serializer, and consumer deserializer are compatible.
- [ ] No HTTP tokens/cookies or sensitive data are forwarded into messages.
- [ ] Channel send result, broker publisher confirmation, and consumer completion are distinguished.
- [ ] Synchronous and asynchronous errors have handling and alerting mechanisms.
- [ ] Dynamic destinations are allow-listed and never taken directly from unvalidated input.
- [ ] REST retries use a persistently stored idempotency key.
- [ ] Downstream consumers are idempotent against duplicate events.
- [ ] If durable acceptance is required, transactional outbox and publisher confirmation are in place.
- [ ] Test Binder, REST contract, and broker integration tests have been executed.
- [ ] Broker unavailability, serialization failure, retries, and duplicates have been tested.
- [ ] Dashboards include REST latency, producer errors, broker backlog, and consumer lag.
- [ ] A replay/reconciliation procedure exists for failed events.

**Conclusion:** A REST API is a valid event source in a Spring Cloud Stream application. Use `StreamBridge` to send events to an output binding, preferring static bindings when destinations are known and allow-listed dynamic destinations when truly needed. Return `202 Accepted` aligned with the system's guarantees; distinguish channel sends from broker confirmations and consumer completion. When requests must not be lost, combine transactional outbox, publisher confirmations, and consumer idempotency to handle failures and retries safely.

## References

- [Spring Cloud Stream — Producing and Consuming Messages / StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream 5.1 — StreamBridge, Async Send and Dynamic Destinations](https://docs.spring.io/spring-cloud-stream/reference/5.1/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream — Kafka Binder Error Channels](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/error-channels.html)
- [Spring Cloud Stream — Event Routing and Dynamic Destinations](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html)

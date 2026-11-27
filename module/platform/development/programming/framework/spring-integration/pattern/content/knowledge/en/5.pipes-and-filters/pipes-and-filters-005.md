# Separating Business Logic from Transport

## 1. The Problem: One Business Capability, Multiple Message Entry Points

Suppose an order system receives the same request via an HTTP API, a message broker, and a scheduled data import job. All three entry points must validate the order, apply quota rules, persist state, and emit a result. If each controller or listener implements all of those rules itself, three versions of the business logic will gradually drift apart:

- The HTTP controller returns an error on an invalid quantity, while the Kafka consumer still saves the order.
- A listener has its own retry mechanism, causing an order to be recorded twice.
- Switching from JSON to Avro or renaming a topic forces developers to edit the business class as well.
- Unit tests checking quota calculations have to spin up a web server or broker.

In the **Pipes and filters** chapter of the **SPRING_INTEGRATION_PATTERN** module, the solution is to turn processing steps into components with explicit inputs and outputs connected via **message channels**. Steps that understand HTTP, Kafka, AMQP, or file formats live at the **transport boundary**; steps that understand orders, inventory, and business rules live in the **application core**.

The goal is more than splitting functions. After this lesson, you need to know how to:

1. Identify accurately what belongs to business logic and what belongs to transport.
2. Design commands, results, and business invocation ports independent of HTTP or brokers.
3. Use Spring Integration **Gateway, Filter, Transformer, Router**, and handlers to connect layers without leaking transport APIs into the domain.
4. Keep correlation, idempotency, retry handling, and error channels at the proper responsibility boundaries.
5. Test business logic without a broker, and test adapters/flows at integration boundaries.

## 2. Combining Pipes and Filters with Ports and Adapters

These two architectural perspectives complement each other:

| Perspective | Primary Question | How It Applies |
|---|---|---|
| **Pipes and Filters** | Which steps does a message pass through? | Each filter/transformer/handler has explicit input and output; channels connect steps |
| **Ports and Adapters** | Which classes are allowed to know about frameworks or protocols? | Business services expose plain Java ports; HTTP/Kafka/JDBC adapters call those ports |

A **Pipe** in Spring Integration is typically a `MessageChannel`; a **filter** in the architectural sense is a general processing step, whereas the concrete **EIP Filter** is an endpoint that decides whether a message proceeds or is rejected. Do not confuse the two meanings. A pipeline can consist of Transformers, Routers, Service Activators, and Aggregators; not every step has to be an EIP `Filter`.

~~~mermaid
flowchart LR
    subgraph Outside["Transport / external systems"]
      H["HTTP JSON"]
      K["Broker event"]
      S["Scheduled import"]
    end
    subgraph Boundary["Adapters and integration"]
      AH["HTTP adapter"]
      AK["Broker adapter"]
      AS["File/scheduled adapter"]
      G["Gateway → orders.in"]
      V["Filter: input contract"]
      T["Transformer: DTO → command"]
    end
    subgraph Core["Business core"]
      U["OrderUseCase"]
      P["RepositoryPort"]
    end
    H --> AH
    K --> AK
    S --> AS
    AH --> G
    AK --> G
    AS --> G
    G --> V --> T --> U --> P
    U --> O["Internal result / event"]
    O --> OUT["Output adapters"]
~~~

Transport adapters translate data into a **shared application contract**. The integration flow handles coordination and routing. The business core does not need to know which adapter called it, which thread is executing, or whether the original data was encoded as JSON or a byte array.

**Dependency rule:** domain/application classes do not import `HttpServletRequest`, `ResponseEntity`, `ConsumerRecord`, `Message<?>`, `MessageHeaders`, `@KafkaListener`, or Spring Integration channel classes merely to execute business rules. Adapters and flows may depend on the core; the core does not depend back on them.

## 3. Classifying Responsibilities Before Writing Code

For example, the requirement “place an order with positive quantity not exceeding limits; received via HTTP or broker” can be partitioned as follows:

| Responsibility | Where It Belongs | Why |
|---|---|---|
| Decoding JSON/Avro, reading HTTP or Kafka headers | Transport adapter | Format- and protocol-dependent |
| Checking content type, size, required fields per wire schema | Inbound adapter/validation boundary | Blocks unparseable data from outside |
| Converting version 1 DTO to normalized command | Transformer/mapper | Translates external contract to application type |
| Checking positive quantity, product limits, customer status | Business use case | Rules must hold across all transports |
| Selecting processing channel by country or order type | EIP Router, based on normalized business decision | Keeps branches observable and infrastructure changeable |
| Persisting the order | Business service calling `OrderRepositoryPort` | Core defines the need; adapter supplies persistence |
| HTTP status 201/400/409, response headers | HTTP adapter | Semantics belong to the HTTP contract |
| Ack/nack, broker retries, DLQ, partitions, serialization | Broker adapter and operational config | Dependent on delivery mechanics |
| Correlation, tracing, routing metadata across channels | Integration boundary | Tracks messages across endpoints |
| Idempotency of order creation | Application/business + suitable storage | The same message may be redelivered from multiple sources |

Some responsibilities appear on both sides but serve **different purposes**. For example, an adapter checks whether `quantity` parses as an integer, while the use case checks whether that quantity satisfies sales rules. Preliminary checks in a Filter drop non-conforming messages; the use case must still enforce invariants even when invoked directly.

## 4. Establishing a Stable Contract at the Application Boundary

Design three data types:

1. **Transport DTO:** describes the external structure, which may evolve by version or protocol.
2. **Application command:** expresses normalized business intent, making no mention of HTTP/Kafka.
3. **Business result:** returns the business outcome; adapters decide how to express it as a response or event.

~~~java
// DTO defined by API/event contract v1.
public record IncomingOrderV1(
    String requestId,
    String itemCode,
    int units,
    String market
) {}

// Type used inside the application core.
public record PlaceOrder(
    String orderId,
    String sku,
    int quantity,
    String region
) {}

public record OrderReceipt(
    String orderId,
    String status
) {}

public interface PlaceOrderUseCase {
    OrderReceipt place(PlaceOrder command);
}
~~~

These records contain only data. They need no HTTP, Kafka, or Spring Integration annotations. `IncomingOrderV1` belongs to the inbound contract and can live in the adapter module; `PlaceOrder`, `OrderReceipt`, and `PlaceOrderUseCase` belong to the core contract.

Keep **business keys** and **event identifiers** separate. `orderId` identifies the order; `eventId` identifies a single event emission; `correlationId` links steps belonging to the same process. They may be related, yet they are not interchangeable by default. When deduplication is needed, the use case/persistence adapter must use the key defined in the business contract.

### A Transport-Agnostic Business Service

~~~java
public final class DefaultPlaceOrderUseCase implements PlaceOrderUseCase {

    private final OrderRepositoryPort repository;

    public DefaultPlaceOrderUseCase(OrderRepositoryPort repository) {
        this.repository = repository;
    }

    @Override
    public OrderReceipt place(PlaceOrder command) {
        if (command == null || command.orderId() == null
                || command.orderId().isBlank()
                || command.sku() == null || command.sku().isBlank()
                || command.quantity() <= 0) {
            throw new InvalidOrderException("Invalid order command");
        }
        // This method illustrates business invariants:
        // Validation rules do not depend on HTTP or broker sources.
        return repository.save(command);
    }
}

public interface OrderRepositoryPort {
    OrderReceipt save(PlaceOrder command);
}

public final class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String reason) {
        super(reason);
    }
}
~~~

`OrderRepositoryPort` is an outbound port. An adapter can implement it with JDBC/JPA or another system without modifying `DefaultPlaceOrderUseCase`. Production code also requires transactions, unique constraints, and an idempotency policy for writes; this example focuses solely on the responsibility boundary.

## 5. Transformer: One Place to Convert External Contracts into Commands

A dedicated mapper avoids duplicating normalization logic across controllers and broker listeners:

~~~java
public final class OrderMapper {
    public PlaceOrder toCommand(IncomingOrderV1 input) {
        return new PlaceOrder(
            input.requestId(),
            input.itemCode().trim(),
            input.units(),
            input.market().trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Input `IncomingOrderV1("O-105", " SKU-7 ", 2, " vn ")` becomes `PlaceOrder("O-105", "SKU-7", 2, "VN")`. Field renaming, trimming, and region code normalization belong to the **Transformer**; checking whether the quantity is permissible remains with the business use case.

Precondition for the mapper: `itemCode` and `market` must be non-`null`. If input is invalid, a Filter or validation boundary must raise a clear error. Do not “fix” bad input by silently defaulting empty values to some fallback market unless the business contract explicitly specifies that rule.

**Distinguish converter from business Transformer:** a converter turns JSON bytes into `IncomingOrderV1`; a Transformer turns `IncomingOrderV1` into `PlaceOrder`. A message may already be parsed into an object and still require normalization before entering the core.

## 6. Wiring Everything with Spring Integration Java DSL

Spring Integration provides **Messaging Gateway** as the entry point to a flow. The Gateway is a Java API that adapters can call; underneath, the framework puts messages onto a channel. It serves as the glue layer between transport adapters and the pipeline.

The example below uses a synchronous flow to obtain results immediately. Java/Spring/Spring Integration imports are omitted, and types from the previous section are reused.

~~~java
@MessagingGateway(defaultRequestChannel = "orders.in")
public interface OrderMessageGateway {
    OrderReceipt submit(IncomingOrderV1 input);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderIntegrationConfig {

    @Bean
    public OrderMapper orderMapper() {
        return new OrderMapper();
    }

    @Bean
    public IntegrationFlow orderFlow(
            PlaceOrderUseCase useCase, OrderMapper mapper) {
        return IntegrationFlow.from("orders.in")
            .filter(IncomingOrderV1.class,
                dto -> dto != null
                    && dto.requestId() != null
                    && !dto.requestId().isBlank()
                    && dto.itemCode() != null
                    && dto.market() != null,
                spec -> spec.throwExceptionOnRejection(true))
            .transform(IncomingOrderV1.class, mapper::toCommand)
            .handle(PlaceOrder.class,
                (command, headers) -> useCase.place(command))
            .get();
    }
}
~~~

This flow performs three distinct steps:

- **Filter:** checks part of the technical contract before invoking the mapper. Setting `throwExceptionOnRejection(true)` turns rejected messages into errors instead of letting them silently vanish in a Gateway that expects a reply. This is a choice for this example, not a mandatory rule for all flows.
- **Transformer:** converts payload `IncomingOrderV1` into `PlaceOrder`, while Spring Integration normally preserves valid headers when constructing the output message.
- **Service Activator:** invokes `PlaceOrderUseCase` and returns `OrderReceipt` to the Gateway caller. The use case only receives a plain Java command.

Along a path using the default `DirectChannel` with no asynchronous boundaries, the Gateway waits for the handler to finish and receives the reply. If you swap part of the path to `ExecutorChannel` or `QueueChannel`, waiting, timeout, and error semantics change; you must redefine the reply contract and error handling accordingly.

**Configuration note:** `PlaceOrderUseCase` and an `OrderRepositoryPort` implementation bean must be declared in your application configuration. The snippet focuses on message routing and omits database setup or network protocol configuration.

~~~mermaid
flowchart LR
    A["Adapter: IncomingOrderV1"] --> G["Gateway: orders.in"]
    G --> F{"Filter: valid fields?"}
    F -->|"Yes"| T["Transformer → PlaceOrder"]
    F -->|"No"| X["Exception / error mapping"]
    T --> U["UseCase: place(command)"]
    U --> R["OrderReceipt"]
    R --> G
~~~

Do not let `OrderMessageGateway` accumulate business conditions; it should only define the interface for sending messages into the pipeline.

## 7. Two Transport Adapters Sharing the Same Flow

An HTTP adapter can receive JSON, deserialize it into `IncomingOrderV1`, and call the Gateway:

~~~java
@RestController
public class OrderHttpAdapter {
    private final OrderMessageGateway gateway;

    public OrderHttpAdapter(OrderMessageGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping("/orders")
    public OrderReceipt submit(@RequestBody IncomingOrderV1 request) {
        return gateway.submit(request);
    }
}
~~~

Here is an example using Spring Kafka as an alternative transport adapter. The listener simply decodes JSON and calls the exact same Gateway:

~~~java
public final class OrderKafkaAdapter {
    private final ObjectMapper objectMapper;
    private final OrderMessageGateway gateway;

    public OrderKafkaAdapter(ObjectMapper mapper, OrderMessageGateway gateway) {
        this.objectMapper = mapper;
        this.gateway = gateway;
    }

    @KafkaListener(topics = "orders.commands", groupId = "orders-service")
    public void onMessage(String json) throws JsonProcessingException {
        IncomingOrderV1 request =
            objectMapper.readValue(json, IncomingOrderV1.class);
        gateway.submit(request);
    }
}
~~~

Spring Kafka requires its own dependencies, bean registration, and consumer/error-handler configuration; this example illustrates the *role of the adapter*, not full Kafka operational config. When receiving an event, the listener does not decide “maximum sellable quantity” or “when to issue an invoice.” The same `PlaceOrderUseCase` handles those decisions for both HTTP and the broker.

The application result `OrderReceipt` can be rendered by the HTTP adapter as an HTTP response. For a message broker, the adapter can publish a separate result event or require no synchronous reply, depending on the contract. **Do not use HTTP status codes as business results** inside the core, and do not assume broker ack means the business transaction succeeded.

### When Different Adapters Truly Need Different Handling

HTTP needs to map exceptions to `400`, `409`, or `5xx`; a broker needs to classify retryable versus non-retryable failures for ack/nack or DLQ routing. That is *transport policy*. The same `InvalidOrderException` can be mapped to `400 Bad Request` by an HTTP mapper, while a broker consumer routes the error event to an audit channel and acks the permanently malformed message. **The rules defining what constitutes an invalid order remain in the use case.**

## 8. Routers and Multiple Branches Still Keep the Core Independent

Not every flow is a single straight line. For example, domestic orders need to update a VN warehouse, while international orders require a different fee calculation step. You can insert an **EIP Router** based on the normalized command's `region`:

~~~mermaid
flowchart LR
    I["Parsed DTO"] --> T["Transformer: PlaceOrder"]
    T --> R{"Router: region"}
    R -->|"VN"| V["orders.vn"]
    R -->|"Other"| W["orders.other"]
    V --> S1["OrderUseCase with VN policy"]
    W --> S2["OrderUseCase with matching policy"]
    S1 --> O["OrderReceipt"]
    S2 --> O
~~~

Within each branch, handlers should call the appropriate **business port** rather than inline pricing or inventory checks. If branch selection carries complex business semantics, the use case or a domain policy can precompute a `ProcessingRoute`; the Router then merely uses that result to dispatch to a channel. This keeps business rules independently testable.

An illustrative DSL routing snippet:

~~~java
.route(PlaceOrder.class, PlaceOrder::region,
    spec -> spec.channelMapping("VN", "orders.vn")
                .defaultOutputChannel("orders.other"))
~~~

This is a **connecting snippet for another flow**, placed after the Transformer and before branch-specific handlers. Do not paste it straight onto the end of the reply-returning Gateway example without configuring terminal handlers and a reply path. For request/reply flows, ensure every branch returns a clear outcome or error; a dropped branch with no reply can cause the Gateway to hit its timeout.

If you add **Splitter/Aggregator**, you can split a `PlaceOrder` into individual line items, process them independently, and combine results by `orderId`/correlation. Line-item pricing belongs in a plain Java service; Splitter/Aggregator handle distribution, grouping, timeouts, and release, not hidden pricing math.

## 9. Message Contract: Business Payload vs. Operational Headers

Spring Integration models a message as `Message<T>`, consisting of **payload** and **headers**. Clarify ownership from the start:

| Data | Where It Usually Lives | Who Uses It |
|---|---|---|
| `orderId`, `sku`, `quantity` | Payload/command | Business use case |
| Normalized `region` | Payload/command | Domain policy, Router |
| `eventId`/idempotency key | Business contract or agreed metadata | Deduplication logic |
| `correlationId`, `sequenceNumber`, `sequenceSize` | Message headers | Splitter/Aggregator, orchestration flow |
| `traceId` and tracing baggage | Standard integration headers/context | Observability |
| HTTP request headers, Kafka offset, partition | Adapter metadata | Transport/error handling |

Do not pass `HttpServletRequest` or `ConsumerRecord` into `PlaceOrderUseCase` just to extract a correlation ID. If the use case genuinely needs an identifier for idempotency, place it in a **plain Java application context type** or a command field, and let the mapper explicitly populate it from the right source.

At broker or serialization boundaries, never assume headers survive automatically. Check header mappers and producer–consumer contracts. For a recreated message after retry, `MessageHeaders.ID` may differ; it does not replace a stable idempotency key.

## 10. Putting Errors, Retries, and Transactions in the Right Layer

Separating the core from transport does not mean the core cannot emit errors. The core must state **business failures** clearly, while adapters decide **how to represent and recover from them**.

| Failure | Where Detected | Recommended Handling |
|---|---|---|
| Malformed JSON or unparseable schema | Adapter/converter | HTTP 400 or broker quarantine/DLQ per policy |
| Missing values before Transformer | Validation/Filter | Rejected message or informative exception |
| Invalid quantity, closed order | Use case | Business exception/result with stable error code |
| Database temporarily unavailable | Repository adapter | Emit technical error so orchestration layer decides retry |
| Redelivered request | Application/idempotency store | Return stored outcome or skip duplicate side effect |
| Gateway reply timeout | Integration boundary | Explicit timeout; do not assume business logic never ran |

With **DirectChannel**, synchronous handler exceptions can propagate back to the HTTP controller or broker listener. When a flow executes via `ExecutorChannel`, pollers, or broker inbound adapters, errors occur in a different execution context and require appropriate **error channels, retry advice, and broker recovery**. Never assume every exception automatically lands on a single shared error channel.

**Separate retries by layer:**

- The use case enforces invariants and idempotency because it does not know how many times the same command may be delivered.
- The integration flow can retry transient technical operations with bounded attempts and backoff.
- The broker adapter decides ack/nack, redelivery, and DLQ per the delivery contract.
- The HTTP adapter decides response codes and whether clients may safely resubmit with the same idempotency key.

In distributed flows, *at-least-once* delivery can re-run handlers. If a write succeeds and a crash happens before broker ack, redelivery can cause a second side effect. Use unique keys/idempotency ledgers, appropriate transactions, and sometimes a **transactional outbox** to tie database updates to event publishing.

**Do not equate “enqueued” with “business completed.”** An in-memory `QueueChannel` does not provide durable persistence or automatic recovery after handler failure; brokers also require proper persistence and ack configuration.

## 11. Testing at Each Boundary Instead of Booting the Whole Stack for Every Test

This structure creates three complementary testing layers.

| Layer | What It Verifies | Infrastructure Needed |
|---|---|---|
| **Use case unit test** | Invariants, business outcomes, idempotency with fake repository | JUnit + plain Java |
| **Integration flow test** | Filter, Transformer, Router, Gateway, headers, reply/error | Spring test context, test channels/handlers |
| **Adapter contract test** | JSON, HTTP status, broker serialization, ack/retry, header mapping | Web integration test or test broker |

Example core unit tests without Spring Integration:

~~~java
@Test
void rejectsNonPositiveQuantity() {
    OrderRepositoryPort repository = command ->
        new OrderReceipt(command.orderId(), "ACCEPTED");

    PlaceOrderUseCase useCase = new DefaultPlaceOrderUseCase(repository);

    assertThrows(InvalidOrderException.class, () ->
        useCase.place(new PlaceOrder("O-101", "SKU-1", 0, "VN")));
}

@Test
void acceptsValidOrderThroughPort() {
    OrderRepositoryPort repository = command ->
        new OrderReceipt(command.orderId(), "ACCEPTED");

    PlaceOrderUseCase useCase = new DefaultPlaceOrderUseCase(repository);

    OrderReceipt receipt =
        useCase.place(new PlaceOrder("O-102", "SKU-2", 3, "VN"));

    assertEquals("O-102", receipt.orderId());
    assertEquals("ACCEPTED", receipt.status());
}
~~~

For the flow, also test that `IncomingOrderV1("O-103", " SKU-3 ", 2, " vn ")` becomes `PlaceOrder("O-103", "SKU-3", 2, "VN")` and reaches the handler. When the Filter rejects, assert the error reaches the Gateway and no write command executes. For Routers, test every branch including the default route and unexpected inputs.

For broker adapters, add a test redelivering the same `eventId` and verify the database records only one side effect. Verify that lost or delayed Gateway replies are classified properly, because a caller-side timeout does not prove the handler failed.

## 12. Observing Flows Without Coupling the Domain to Transport Loggers

Separating logic from transport works even better when logs and metrics are captured at boundaries that hold rich context:

~~~text
HTTP / broker ingress
    └── decode_time, request_id, event_id
Gateway / orders.in
    └── message_count, correlation_id
Filter / Transformer / Router
    └── rejected_count, branch, mapping_error
OrderUseCase
    └── business_result, processing_duration
Repository adapter
    └── db_errors, retry_count, commit_duration
Outbound adapter
    └── publish_status, delivery_attempt, dlq_count
~~~

Do not force the domain to accept Kafka objects, servlets, or tracing spans just to write logs. Use observations/interceptors in the integration layer and stable business identifiers from the input. Avoid logging entire payloads if they contain sensitive data; log order IDs, event types, and error codes when tracing is required.

With Spring Integration and Micrometer/observation configured, track messages passing each channel/endpoint, handler latency, error counts, and backlogs. When adding `Splitter/Aggregator`, make correlation and timeouts observable so you can explain why a group has not emitted a result yet.

## 13. Practices That Quietly Couple Layers Together

**Putting business rules in listeners:** `@KafkaListener` parses JSON, calculates pricing, and saves the order all in one place. Soon the HTTP adapter copies the same logic. Keep listeners limited to decoding and calling the shared port.

**Passing transport headers into the domain:** `PlaceOrderUseCase.place(ConsumerRecord record)` forces every business test to fabricate Kafka metadata. Map records into plain Java commands/contexts instead.

**Letting each channel carry arbitrary payload types:** one handler expects `String`, another `byte[]`, casting ad hoc. Decode once at ingress and establish clear input/output contracts for every filter.

**Confusing domain checks with EIP Filters:** a `Filter` can drop messages from a flow, yet core invariants must still be protected inside the use case. If someone calls the use case directly, the business logic must still reject invalid values.

**Unbounded retries across the whole flow:** a business call that already wrote data might fail while returning a reply. Retrying without idempotency creates duplicate records; cap retries and define deduplication keys.

**Keeping request/reply across queues without timeouts:** switching a `DirectChannel` to a `QueueChannel` introduces an execution boundary; the Gateway may hang waiting for a result. Design reply channels, timeouts, and error paths, or switch the contract to asynchronous.

**Adding layers that provide no value:** the goal is clear responsibilities and boundaries. One simple adapter and a plain Java service may suffice for a small use case. Add EIP steps only when transformation, routing, or message coordination genuinely demands them.

## 14. Practice Exercise: Swapping HTTP for a Broker Without Changing Core

Build an **order intake** feature across these milestones:

1. **Define contracts:** `IncomingOrderV1` (transport DTO), `PlaceOrder` (command), `OrderReceipt` (result), and `PlaceOrderUseCase` interface.
2. **Write the use case:** enforce invariants, call `OrderRepositoryPort`, distinguish business errors from infrastructure failures. Unit test with a fake repository.
3. **Write the Spring Integration flow:** Gateway → structural Filter → Transformer/mapper → Service Activator calling the use case. Test payloads and replies.
4. **Write the HTTP adapter:** accept JSON, map errors to HTTP statuses, and return results. Do not duplicate use-case rules.
5. **Add a broker adapter:** consume events with an appropriate consumer, decode, and call the Gateway; test redelivered messages. Do not touch working business logic.
6. **Add a Router:** split by `region` and observe all branches. When needed, add Splitter/Aggregator for line items while preserving correlation.
7. **Test failures:** malformed JSON, missing fields, negative quantity, database timeout, duplicates, reply timeout, worker restart. Document where each failure is detected and its recovery policy.

**Completion criteria:**

- The same valid command produces equivalent business outcomes whether arriving via HTTP or broker.
- The business service imports no HTTP/Kafka/Spring Integration libraries and passes standalone unit tests.
- Changing endpoint URLs or topic names requires zero edits to order calculation/business rules.
- Failed messages have an explicit handling path; redelivered messages cause no unintended duplicate side effects.
- Tests verify Filter, Transformer, Router, correlation, reply, and error handling at their proper boundaries.
- Logs/metrics show where messages originated, which branches they took, and when they succeeded or failed.

## 15. Design Self-Assessment Checklist

| Question | Passing Signal |
|---|---|
| Do business rules depend on HTTP/Kafka objects? | No; only business types and ports are used |
| Do inputs from multiple transports share a contract? | Explicit DTO-to-command mapping exists |
| Does each Transformer own one clear conversion? | Clear input/output types; mapping errors handled |
| Can Router and Filter break request/reply results? | Every branch returns a defined result or error/timeout |
| Does correlation survive adapters, split, and aggregate? | Verified by tests and header mapping configuration |
| Can retries re-execute side effects? | Idempotency keys and recovery policies are in place |
| Does changing a topic/URL require editing the use case? | No, only adapter/configuration changes |
| Do business tests need a running broker? | No; only integration/contract tests need one |

## 16. Conclusion

**Separating business logic from transport** means keeping business rules inside stable services and ports while confining protocols, serialization, transport headers, and delivery policies to adapters and integration flows. Spring Integration wires these pieces together using channels and endpoints from **Pipes and Filters**, giving **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, and error channels** explicit responsibilities.

A clean design lets you add HTTP, Kafka, AMQP, or scheduled sources without duplicating order logic, while preserving independent testing, correlation, observability, and recovery strategies as your flow scales into a distributed system.

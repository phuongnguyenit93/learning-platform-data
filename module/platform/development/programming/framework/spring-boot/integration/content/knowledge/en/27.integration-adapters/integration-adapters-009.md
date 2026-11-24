# RSocket adapters or gateways and supporting Spring Boot infrastructure

An ordering system might use HTTP to accept browser requests, JDBC to persist orders, RabbitMQ to distribute events, and **RSocket** to query or stream continuous updates from an internal service. When these steps are wired with **Spring Integration**, RSocket becomes an *integration endpoint*: converting incoming RSocket calls into Spring `Message<?>` objects for an integration flow, or taking a Spring Message from a flow to invoke an external RSocket service.

This lesson belongs to the **Integration Adapters** chapter of the **SPRING_BOOT_INTEGRATION** module. The module focuses on organizing Spring Boot system integrations across HTTP clients, databases, caches, message brokers, and Spring Integration adapters—emphasizing configuration, data contracts, transactions, error handling, deduplication, testing, and flow observability. In that context, you must distinguish **Spring Integration's RSocket adapter/gateways** from **Spring Messaging's and Spring Boot's RSocket infrastructure**, and know which responsibilities you must still implement yourself.

The article illustrates APIs available in **Spring Boot 3.x, Spring Framework 6.x, and Spring Integration 6.x**. Newer Spring Boot releases may manage different Spring Integration versions; use an appropriate BOM/dependency management setup and verify APIs for your project's version. The Java examples are presented as modular configuration snippets for server/client apps rather than implying every bean must live in a single place.

## 1. What roles do RSocket, Spring Messaging, and Spring Integration play?

RSocket is a binary protocol supporting bidirectional interaction over a single connection such as TCP or WebSocket. It is not limited to request/response; it defines four interaction models:

| Interaction model | Request data | Response data | Use case |
| --- | --- | --- | --- |
| `requestResponse` | One payload | One response or error | Checking stock, fetching fee quotes |
| `fireAndForget` | One payload | No business response | Sending signals where loss is acceptable or confirmed at another layer |
| `requestStream` | One payload | Multiple response items | Watching order state changes over time |
| `requestChannel` | A stream of payloads | A stream of responses | Bidirectional state sync, interactive sessions |

**Spring Messaging** provides `RSocketRequester`, `RSocketMessageHandler`, `@MessageMapping`, and `RSocketStrategies`. A `@Controller` can handle RSocket requests and return `Mono` or `Flux` without Spring Integration.

**Spring Integration** adds the *MessageChannel → filter/transformer/router/service activator → MessageChannel* model, convenient when RSocket is one stage in a workflow spanning HTTP, SQL, caches, brokers, or external systems.

**Spring Boot** provides dependency alignment, beans, codecs, server/client configuration, and conditional auto-configuration. It does not design business contracts, idempotency, timeouts, retries, database transactions, or durable message storage for you.

~~~mermaid
flowchart LR
    A["RSocket client"] --> B["RSocket transport / SETUP"]
    B --> C["Spring Messaging: RSocketStrategies"]
    C --> D["Spring Integration RSocketInboundGateway"]
    D --> E["MessageChannel"]
    E --> F["filter → transformer → service"]
    F --> G["SQL / cache / HTTP / broker"]
    F --> H["RSocket response"]
~~~

Components participate in a flow only as configured. Not every request hits a database or broker.

### Why does the name "adapter" sometimes cause confusion?

Spring Integration refers generally to protocol-connecting components as *channel adapters/endpoints*, yet the official RSocket endpoint lineup consists of **`RSocketInboundGateway`** and **`RSocketOutboundGateway`**. They can also handle no-response interactions like `fireAndForget`, so do not assume classes named `RSocketInboundChannelAdapter` and `RSocketOutboundChannelAdapter` exist to mirror JMS/AMQP. Use the exact published classes and interaction models.

## 2. Inbound and outbound are defined relative to the integration flow

The names *inbound/outbound* describe **direction relative to the Spring Integration application**, not necessarily which machine initiates the TCP connection.

- **Inbound gateway**: an RSocket request enters **into** Spring Integration; the gateway decodes the payload, creates a Spring Message, and sends it to the request channel. For interactions expecting responses, it sends the flow's reply back to the RSocket client.
- **Outbound gateway**: a Spring Message goes **out** to another RSocket endpoint; the gateway selects the route, interaction model, and metadata, awaits the response, and brings the result back into the integration flow.

~~~mermaid
flowchart TD
    subgraph Provider["inventory-service"]
       IN["RSocketInboundGateway('inventory.stock')"] --> MC["stockReadChannel"]
       MC --> S["InventoryLookupService"]
    end

    subgraph Caller["checkout-service"]
       APP["Checkout flow"] --> OUT["RSocketOutboundGateway('inventory.stock')"]
    end

    OUT -->|"RSocket request-response"| IN
    S -->|"Mono response"| OUT
    OUT -->|"reply channel"| APP
~~~

When two services communicate over RSocket, both can act as server and client in either direction because the protocol is *symmetric*. `ServerRSocketConnector` can maintain a registry of connected clients so the server can send requests back to them, and `ClientRSocketConnector` can handle incoming requests over an established connection if endpoints are registered appropriately.

This does not turn RSocket into a queue: messages sent over a live connection do not automatically have *broker persistence*, DLQs, history, or consumer offsets.

## 3. Choose an implementation approach before declaring beans

There are three common approaches:

| Approach | Primary components | When to use |
| --- | --- | --- |
| **Plain Spring Messaging** | `@Controller`, `@MessageMapping`, `RSocketRequester` | Simple RPC/stream routes without needing EIP flows |
| **Spring Integration RSocket gateways** | `RSocketInboundGateway`, `RSocketOutboundGateway`, `ClientRSocketConnector` | Workflows involving multiple adapters, transformers, filters, routers, error channels |
| **Custom rsocket-java server/client** | `RSocketServer`, `RSocketConnector`, custom codecs/handlers | Low-level integrations or transport requirements outside the abstractions above |

An application can mix Spring Messaging `@MessageMapping` with Spring Integration gateways, provided there is **one consistent route/server registration mechanism**. Never accidentally start two RSocket servers on the same port, or register two independent message handlers for the same route hoping Boot picks the right one.

When you only need a single internal RPC call, `RSocketRequester` directly can be easier to maintain. Gateways earn their keep when plugging RSocket into a **Spring Integration processing pipeline**, especially where `IntegrationFlow`, headers, transformers, routers, and channels are already in use.

## 4. Dependencies and what Spring Boot configures for you

With Maven, an application using both Spring Boot RSocket and Spring Integration can declare:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-rsocket</artifactId>
    </dependency>
</dependencies>
~~~

In projects using Spring Boot dependency management properly, Spring Integration versions are managed by the BOM. Never arbitrarily mix `spring-integration-rsocket` from a newer major release with an older Boot/Framework major release. If your project uses a custom BOM, check compatibility and the dependency tree across Reactor, `rsocket-java`, `spring-messaging`, and codecs.

### Basic auto-configuration

Spring Boot can provide:

- `RSocketStrategies` for payload encoding/decoding, with codecs such as CBOR/JSON when matching dependencies are present. Customizable via `RSocketStrategiesCustomizer`.
- `RSocketMessageHandler` and Spring Messaging `@MessageMapping` support.
- An RSocket TCP/WebSocket server when server properties are configured and required dependencies exist.
- `RSocketRequester.Builder` for applications calling RSocket via Spring Messaging.
- **When `spring-integration-rsocket` is present**, Spring Integration RSocket infrastructure can reuse the Boot-managed server and create a `ClientRSocketConnector` from `spring.integration.rsocket.client.*` when conditions match.

That last point is an important distinction. Having the RSocket starter does not mean you have Spring Integration gateways; having Spring Integration core does not create an RSocket connector if `spring-integration-rsocket` is not on the classpath.

### Standalone RSocket TCP server port

In **inventory-service**, when using RSocket over TCP:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 9898
~~~

This configures the RSocket server, not the REST `server.port`. With WebFlux + Reactor Netty, you can expose RSocket over WebSocket via `spring.rsocket.server.transport=websocket` and `mapping-path`, though not every Servlet web server supports mounting RSocket that way.

### Boot-created Spring Integration client connection

In **checkout-service**, with `spring-integration-rsocket` on the classpath:

~~~yaml
spring:
  integration:
    rsocket:
      client:
        host: inventory.internal
        port: 9898
~~~

This example selects TCP. For WebSocket, you can use `spring.integration.rsocket.client.uri` (as supported by your Boot version) instead of TCP host/port. The Boot-configured connector reduces boilerplate, yet the application must still define **routes, interaction models, expected response types, timeouts, and business error handling**.

When you need multiple backends, custom TLS, or specialized transport settings, you can define connector beans manually. Before doing so, check auto-configuration conditions so you do not end up with two connectors connecting to the same service unintentionally.

## 5. Inbound gateway: turning RSocket requests into Spring Messages

To illustrate, `inventory-service` handles a `requestResponse` on route `inventory.stock`. The receiver declares an `RSocketInboundGateway` bean and a Spring Integration transformer. Assume the request payload is a string SKU and the response is a stock status string.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.rsocket.RSocketInteractionModel;
import org.springframework.integration.rsocket.inbound.RSocketInboundGateway;

@Configuration
public class StockInboundConfiguration {

    @Bean
    RSocketInboundGateway stockInboundGateway() {
        var gateway = new RSocketInboundGateway("inventory.stock");
        gateway.setRequestChannelName("stockRequests");
        gateway.setRequestElementClass(String.class);
        gateway.setInteractionModels(
                RSocketInteractionModel.requestResponse);
        return gateway;
    }
}
~~~

A transformer handles the request reactively:

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class StockTransformer {

    private final InventoryQueryService inventory;

    public StockTransformer(InventoryQueryService inventory) {
        this.inventory = inventory;
    }

    @Transformer(inputChannel = "stockRequests")
    public Mono<String> readStock(Flux<String> skuPublisher) {
        return skuPublisher
                .next()
                .flatMap(inventory::describeStock);
    }
}
~~~

In this example, `InventoryQueryService.describeStock(String)` is defined by the application and returns `Mono<String>`, such as `Mono.just("IN_STOCK")`. In practice it must validate the SKU, enforce authorization, and query via a suitable client/DAO. If using blocking JDBC, never invoke JDBC directly on the RSocket event loop; offload to a bounded scheduler or use an appropriate async adapter.

Explanation of configuration lines:

1. `RSocketInboundGateway("inventory.stock")` registers the RSocket route mapping.
2. `setInteractionModels(requestResponse)` restricts the endpoint to the chosen interaction model; by default the gateway class can accept multiple interaction models.
3. `setRequestElementClass(String.class)` specifies how payload elements are decoded. If omitted, the type is inferred from content type and may be `String` or `byte[]` depending on `RSocketStrategies`.
4. `setRequestChannelName("stockRequests")` sets the Spring Integration request channel name.
5. The transformer accepts a `Flux<String>` because the gateway processes the payload pipeline reactively. `next()` takes the first element for a unary request; this is an example policy and is not how multi-item `requestChannel` streams should be handled.
6. When returning a response, the gateway takes the flow's reply and uses the corresponding encoder to produce the RSocket reply.

If you need a pure transformation without a database, for example:

~~~java
@Transformer(inputChannel = "stockRequests")
public Mono<String> echoUppercase(Flux<String> input) {
    return input.next().map(String::toUpperCase);
}
~~~

This is an **alternative** to the business transformer above; registering two subscribers/transformers on the same request channel creates contention or breaks reply expectations. Pick one primary handler or use a router to dispatch cleanly.

### Input publishers are not automatically a single String

With the `requestChannel` interaction model, payloads can arrive as multiple items over time. Calling `next()` consumes only the first element and cancels the upstream subscription, which is wrong if every item must be processed. With some codecs like `StringDecoder`, element boundaries also depend on MIME/encoding. `setDecodeFluxAsUnit(true)` is a special option when you want to decode the entire `Flux` as a single unit, though you must understand its buffering cost and decoder behavior.

For large streams, avoid unbounded `collectList()`; apply backpressure, bounded batching, or dedicated persistence.

## 6. Inbound gateway with Java DSL

If the application uses the `IntegrationFlow` Java DSL, you can declare the endpoint and transformer in one bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.rsocket.RSocketInteractionModel;
import org.springframework.integration.rsocket.dsl.RSockets;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class StockInboundFlowConfiguration {

    @Bean
    IntegrationFlow uppercaseInboundFlow() {
        return IntegrationFlow
                .from(RSockets.inboundGateway("/text.upper")
                        .interactionModels(
                                RSocketInteractionModel.requestChannel))
                .<Flux<String>, Mono<String>>transform(
                        flux -> flux.next().map(String::toUpperCase))
                .get();
    }
}
~~~

This snippet illustrates **`requestChannel`** while reading only a single item as a short reactive type example. For genuine bidirectional streams, the transformer must consume the full input stream and return an appropriate publisher rather than taking only the first item. Document the interaction contract per route so clients do not send `requestStream` to an endpoint registered only for `requestChannel`.

A `ClientRSocketConnector` or `ServerRSocketConnector` must exist for endpoints to be discovered/registered. When using Boot's server infrastructure with Spring Integration, you do not necessarily create a second `ServerRSocketConnector`. Adding connectors must follow **one consistent server management model**.

## 7. Outbound gateway: calling RSocket from an integration flow

In **checkout-service**, a Spring Message in an integration flow needs to invoke route `inventory.stock` and pass the result to downstream steps. We use the `ClientRSocketConnector` configured by Boot from `spring.integration.rsocket.client.host` and `port` in section 4.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.rsocket.ClientRSocketConnector;
import org.springframework.integration.rsocket.RSocketInteractionModel;
import org.springframework.integration.rsocket.dsl.RSockets;

@Configuration
public class StockOutboundFlowConfiguration {

    @Bean
    IntegrationFlow stockOutboundFlow(
            ClientRSocketConnector inventoryConnector) {

        return IntegrationFlow
                .from("stockLookupRequests")
                .handle(RSockets.outboundGateway("inventory.stock")
                        .interactionModel(
                                RSocketInteractionModel.requestResponse)
                        .expectedResponseType(String.class)
                        .clientRSocketConnector(inventoryConnector))
                .channel("stockLookupReplies")
                .get();
    }
}
~~~

Here:

- `stockLookupRequests` is the input channel of the integration flow; upstream can be an application gateway, transformer, or service activator.
- `RSockets.outboundGateway("inventory.stock")` specifies the target route, **distinct from the TCP hostname**.
- `interactionModel(requestResponse)` selects single-request/single-response semantics.
- `expectedResponseType(String.class)` declares how to decode the response.
- `clientRSocketConnector(...)` supplies the requester/connection.
- `stockLookupReplies` receives the downstream output per the outbound gateway's reactive/async semantics.

**Important note on replies:** `RSocketOutboundGateway` is an `AbstractReplyProducingMessageHandler` operating asynchronously. Its reply relates to `Mono`/`Flux` and how downstream channels handle subscriptions. Specifically for `requestStream`/`requestChannel`, the reply `Flux` may be wrapped in a single reactive response per request; do not assume every emitted event automatically becomes an independent Spring Message for every channel configuration.

When a flow pairs with an application gateway method, `@MessagingGateway`, or functional gateway, test **return types and completion timing** against the exact channel types used. Without a subscriber to a cold publisher, the RSocket call may never execute at all.

### Creating `ClientRSocketConnector` manually when needed

If Boot cannot auto-configure the connector due to custom requirements, you can declare:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.rsocket.ClientRSocketConnector;

@Configuration
public class ManualRSocketClientConfiguration {

    @Bean
    ClientRSocketConnector inventoryConnector() {
        return new ClientRSocketConnector(
                "inventory.internal", 9898);
    }
}
~~~

This is an **alternative** to Boot property-based client configuration. Never create this bean alongside a Boot auto-configured connector targeting the same endpoint without reason. For multiple servers, create named/`@Qualifier` beans per endpoint and control which connectors auto-start when startup depends on downstream availability.

`ClientRSocketConnector` manages RSocket connection lifecycles and can accept `RSocketStrategies`, setup route/data/metadata, and connector configurers. Define TLS, reconnect, keepalive, and call deadlines as required by your environment; host/port alone only solves basic addressing.

## 8. When to use outbound like a one-way "adapter"?

In Spring Integration, outbound gateways normally expect replies, yet RSocket provides `fireAndForget`. To emit a telemetry event that does not return a business payload:

~~~java
@Bean
IntegrationFlow telemetrySignalFlow(
        ClientRSocketConnector telemetryConnector) {

    return IntegrationFlow
            .from("telemetrySignals")
            .handle(RSockets.outboundGateway("telemetry.ingest")
                    .interactionModel(
                            RSocketInteractionModel.fireAndForget)
                    .clientRSocketConnector(telemetryConnector))
            .channel("telemetryCompletions")
            .get();
}
~~~

**Do not confuse fire-and-forget with durable delivery.** Having no business response does not mean the consumer executed or persisted the message. RSocket `fireAndForget` fits droppable signals or state that can be resynchronized from a source of truth.

If using the outbound gateway as an outbound adapter with `expectedResponseType = void`, ensure the **resulting `Mono` is still subscribed to**; Spring Integration documentation notes an output channel must be configured (even `NullChannel`) so the library's reactive pipeline triggers subscription. Exact `NullChannel`/reply wiring depends on your API and flow; fire-and-forget tests must verify the remote handler was actually invoked.

For order creation, payments, or invoicing where delivery is mandatory, use a queue, transactional outbox, or request-response with an idempotency key/receipt per contract. An RSocket `fireAndForget` call does not replace a message queue.

## 9. Comparing Spring Integration gateways with `@MessageMapping` and `RSocketRequester`

An RSocket server does not require `RSocketInboundGateway`. For a single route, Spring Messaging `@MessageMapping` is often clearer:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class StockController {

    private final InventoryQueryService inventory;

    public StockController(InventoryQueryService inventory) {
        this.inventory = inventory;
    }

    @MessageMapping("inventory.stock")
    public Mono<String> stock(String sku) {
        return inventory.describeStock(sku);
    }
}
~~~

On the Spring Messaging client side, you can use `RSocketRequester`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
public class StockRequesterConfig {

    @Bean
    RSocketRequester stockRequester(
            RSocketRequester.Builder builder) {
        return builder.tcp("inventory.internal", 9898);
    }
}
~~~

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public class DirectStockClient {
    private final RSocketRequester requester;

    public DirectStockClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<String> getStock(String sku) {
        return requester.route("inventory.stock")
                .data(sku)
                .retrieveMono(String.class);
    }
}
~~~

These two examples show the **direct Spring Messaging path**. In complex integration systems, Spring Integration gateways wrap RSocket paths as flow endpoints and let you apply routers, transformers, enrichers, error channels, and other adapters seamlessly.

If you use both `@MessageMapping` and Spring Integration RSocket gateways on the same server, check `spring.integration.rsocket.server.message-mapping-enabled` in Spring Boot. When enabled in supported versions, the integration infrastructure can serve both endpoint styles via a compatible message handler. Avoid registering duplicate routes across both and test mappings over a real network connection.

## 10. Mapping interaction models to payloads and channels

No single channel strategy fits all four models:

| Model | Payload entering Spring Integration | Suitable reply | What to avoid |
| --- | --- | --- | --- |
| `requestResponse` | One request, which may appear as a reactive publisher in inbound handlers | `Mono<T>` or single result | Returning an infinite `Flux` from a transformer |
| `fireAndForget` | One-way payload | No business response | Treating ACK/commit as guaranteed execution |
| `requestStream` | One inbound request | `Flux<T>` emitting multiple items | Buffering the entire stream or blocking the event loop |
| `requestChannel` | Multi-item `Publisher<T>` input | Reply `Publisher`/`Flux` | Calling `next()` and dropping the rest of the stream |

Especially in Spring Integration's RSocket inbound gateway, `payload` can be a **`Flux` even for `requestResponse`**. This differs from MVC controllers where handlers receive a direct DTO. Transformers must inspect the payload type emitted by the gateway according to `requestElementClass` and codecs.

### MessageChannel does not automatically split a Flux into individual Messages

- `DirectChannel` delivers one Spring Message synchronously on the calling thread by default; if the payload is a `Flux`, the handler receives **that publisher**, not necessarily individual events.
- `FluxMessageChannel` supports reactive pipelines; subscriptions and publisher propagation have distinct semantics.
- `ExecutorChannel` switches execution threads and does not carry JDBC `ThreadLocal` transactions automatically.
- `QueueChannel` can buffer messages in-process, but **does not replace durable queues** like RabbitMQ or JMS.

In an RSocket-to-JDBC flow, never call `block()` directly on the event loop waiting on SQL. If using blocking JDBC, offload to a bounded scheduler/worker with concurrency limits, or use R2DBC when full reactivity is required.

### Backpressure and subscription cancellation

RSocket supports protocol-level `request(n)` backpressure for streaming models. End-to-end backpressure, however, depends on how channels and transformers inside the flow handle `Publisher` signals. Inserting an unbounded queue or calling `subscribe()` carelessly breaks backpressure and grows memory continuously.

Design guidelines:

1. Cap message sizes, concurrent connections/streams, and in-flight events.
2. Propagate `cancel` signals back to data sources when callers stop consuming.
3. Avoid `collectList()`, `cache()`, and unbounded buffers on long-lived streams.
4. When business ordering matters, enforce sequence numbers/versions and partitioning; never assume parallel consumers preserve end-to-end order.
5. Monitor buffer metrics, event-loop saturation, heap usage, and p99 latency under load.

## 11. Routes, MIME types, codecs, and data contracts

An RSocket route acts like a logical method/destination name, such as `inventory.stock` or `orders.status.watch`. It is **not** a host, port, or file path. RSocket transmits payload and metadata; routing information is encoded in metadata using supported formats.

Spring Messaging/Boot's `RSocketStrategies` holds decoders, encoders, and metadata extractors. Both services must agree on:

- `dataMimeType` such as JSON/CBOR or a custom MIME type with matching encoders/decoders.
- `metadataMimeType` and how routing metadata is encoded.
- Inbound payload type and outbound `expectedResponseType`.
- DTO/schema versions, e.g., `eventVersion`, `schemaVersion`, and backward-compatible evolution rules.
- Representation of missing/null/default values, timestamps, monetary amounts, and error codes.
- Frame/payload size limits and chunking/streaming expectations.

Example business payload:

~~~json
{
  "requestId": "REQ-2026-1093",
  "schemaVersion": 1,
  "sku": "SKU-042",
  "quantity": 2
}
~~~

For structured messages, use explicitly validated DTOs:

~~~java
public record StockQuery(
        String requestId,
        int schemaVersion,
        String sku,
        int quantity
) {}
~~~

When using `RSocketInboundGateway` with a JSON DTO payload, configure `requestElementClass(StockQuery.class)` and compatible codecs. On outbound, set `expectedResponseType` to the response DTO, watching how response types differ for streaming or generic publishers. Never confuse **Spring Integration `MessageHeaders`** with RSocket metadata: not every Java header serializes across the wire automatically.

### Metadata and correlation IDs

`RSocketOutboundGateway` can compute `metadata` from `Message<?>` via an expression returning a map keyed by `MimeType`. Use this to pass trace/correlation fields or contract-defined metadata, ensuring matching MIME types and codecs are registered.

Never put bearer tokens or secrets into logs, error headers, URLs, or trace tags. When passing identity/role info in metadata, the server must **authenticate** the token or connection rather than trusting self-asserted client headers. Enforce authorization per route and tenant after authentication.

## 12. Timeouts, reconnect, retry, and resume in gateways

Four recovery layers are easy to confuse:

| Mechanism | Scope | What it solves | What the app must still decide |
| --- | --- | --- | --- |
| Reactor `timeout` | Specific publisher/RPC | Prevents waiting forever for a response | Timeouts after side effects leave outcomes uncertain |
| Connector `reconnect` | Connection/transport | Establishes a new connection after transport drops | Old streams/requests do not automatically regain full progress |
| Protocol/library `resume` | Existing RSocket session | Attempts to resume frames/streams while both sides retain state | Session expiry, state loss, server restarts, and historical data |
| `retryWhen` or retry flow | Business/request | Retries calls on eligible errors | Attempt limits, idempotency, total time budget |

With Spring Integration `ClientRSocketConnector`, you can configure `RSocketConnectorConfigurer` to tune the underlying `rsocket-java` connector per your version. With Spring Messaging `RSocketRequester.Builder`, `rsocketConnector(...)` callbacks allow similar low-level customization. Keep connection ownership in one place so policies do not drift.

Example retry for a **read-only query** in Reactor code:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<StockReply> readWithBudget(Mono<StockReply> rpc) {
    return rpc.retryWhen(
            Retry.backoff(2, Duration.ofMillis(200))
                    .filter(this::isTransientTransportError))
            .timeout(Duration.ofSeconds(2));
}

private boolean isTransientTransportError(Throwable failure) {
    // Classify exceptions based on the Spring/RSocket version in use.
    return failure instanceof TransientRSocketCallException;
}
~~~

`TransientRSocketCallException` here is an **application-defined business exception** mapped from actual transport failures. Never catch all exceptions and treat every failure as retryable. `Retry.backoff(2, ...)` allows at most two retries after the initial attempt; the outer `timeout` protects the overall publisher budget.

For write operations like `reserveStock`, if the client times out and retries, the server may have **already committed** while the response was lost. Reuse the same `requestId` across attempts, persist an idempotency receipt with a unique constraint, and return the stored result. Connection reconnect/resume windows never replace business transactions and idempotency.

**Resume is not durable messaging.** It only attempts to keep an active RSocket session alive while both peers retain state and frame buffers; it does not provide multi-day history or replay across arbitrary server restarts. To recover missed events, use cursors/sequences backed by a database, outbox, or retention-capable broker.

## 13. Transactions, inbox/outbox, and combining other adapters

An integration flow can receive an RSocket request, write SQL, and publish an event via RabbitMQ:

~~~mermaid
flowchart LR
    Client["RSocket Client"] --> G["Inbound Gateway"]
    G --> V["Validate + authorize"]
    V --> S["@Transactional Service"]
    S --> DB[("SQL + inbox/outbox")]
    DB --> Relay["Outbox relay"]
    Relay --> MQ[("RabbitMQ")]
    S --> Reply["RSocket response"]
~~~

Separate **RSocket processing completion** from **data-store commit**. If a handler emits a response before SQL commits and the transaction later fails, the client gets a false positive. If SQL commits and TCP drops before the response arrives, the caller does not know whether it succeeded. Design state and idempotency for both cases.

### Deduplication key example

~~~sql
CREATE TABLE processed_inventory_commands (
    caller_id     VARCHAR(100) NOT NULL,
    request_id    VARCHAR(120) NOT NULL,
    result_json   TEXT NOT NULL,
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (caller_id, request_id)
);
~~~

Each time `ReserveStock` arrives, the server authenticates the caller, extracts `requestId`, and within one SQL transaction:

1. Inserts the unique processing key or locks/reads an existing receipt per concurrency strategy.
2. If the request already completed, returns the saved result without creating a second reservation.
3. If the request is new, updates inventory and reservation records and stores the result in the same transaction.
4. Commits before reporting business success.
5. If an event must be published, writes an `outbox_event` in the same transaction for a relay to publish afterward.

When using JDBC across Spring Integration async channels, remember imperative transactions are thread-bound; passing messages via `ExecutorChannel` or switching to a new reactive scheduler **does not automatically carry the transaction**. Place transaction boundaries on the Spring service executing on the target thread, or choose R2DBC transactions when the architecture is purely reactive and configured accordingly.

### Combining HTTP and caching

If an RSocket flow receives order status, calls an HTTP client, and updates a cache:

- HTTP timeouts do not roll back an already-committed SQL transaction.
- Updating a cache before SQL commits can leave stale data if SQL rolls back.
- Forwarding status to a broker can deliver duplicates on broker retries; consumers must deduplicate.
- An RSocket message stream should not act as the sole source of truth when long-disconnect recovery is needed.

Define an error contract at every integration point: which stage retries, who owns state, when a job counts as complete, and whether replies may return before downstream steps finish.

## 14. Transport security and route authorization

RSocket runs over TCP/WebSocket and may use TLS or traverse proxies/service meshes. In deployment:

- Define server ports/WebSocket paths, TLS termination, and traffic routing to the right pods.
- Enable TLS outside trusted boundaries with proper certificate/trust-store management and rotation.
- Authenticate callers via tokens, mTLS, or security mechanisms supported in the Spring/RSocket stack.
- Enforce route-level authorization: `inventory.stock` may allow broader callers, whereas `inventory.reserve` requires write privileges.
- Cap connections/streams, payload/metadata sizes, and request rates per tenant.
- Restrict CORS/Origins and authenticate WebSocket handshakes when exposed to browsers or gateways.

Never treat a route or `requestId` as proof of authorization; both are client-supplied. Validate metadata and enforce access control against authenticated identities. Never write tokens, passwords, or customer payloads into default logs or traces.

An application using Spring Integration gateways can enforce auth before messages enter core flows—such as in RSocket authentication/interceptors or a validation service at flow entry. If you reject messages inside a flow filter, define an **explicit RSocket error response path**; silently dropping request-response messages leaves callers hanging until timeout.

## 15. Observing the flow: which metrics show the adapter is healthy?

RSocket gateways bridge the network and message flows; observing only one side is insufficient. Useful signals:

| Metric | Meaning |
| --- | --- |
| Connection opens/closes, handshake failures | Transport and TLS/SETUP stability |
| Active RSocket streams by route | Pressure from `requestStream`/`requestChannel` |
| Request count by route/model/status | Where errors concentrate |
| End-to-end latency p50/p95/p99 | Distinguishes slow codecs from DB or downstream delays |
| Timeout/cancellation counts | Callers giving up or server stalling |
| Backpressure/pending buffers | Whether any stage is falling behind |
| Spring Integration channel dispatch failures | Transformer/router/service activator failures |
| Reactive error signals and `errorChannel` | Whether errors reach intended handling paths |
| Connector reconnect/resume attempts | Network churn and recovery rates |
| SQL transaction rollbacks, retry/inbox hits | Data errors, redeliveries, and duplicate prevention |
| Outbox backlog/age | Whether broker/event relays are lagging |

Use Spring Boot Actuator/Micrometer and Reactor/Spring Integration/RSocket observation/tracing instrumentation matching your versions. **Do not assume** the RSocket starter automatically collects custom metrics for every route and `MessageChannel`; add interceptors/observation handlers where needed and inspect real output.

Suggested log fields: `traceId`, `requestId`, `route`, `interactionModel`, `elapsedMs`, `status`, `exceptionCategory`. Across services, propagate correlation/trace IDs via safe metadata and attach them to the right context. Reactor `Context` and Spring `MessageHeaders` do not stay aligned automatically; design explicit propagation instead of relying on `ThreadLocal`.

### When the flow errors, how does the client receive feedback?

For request-response, errors in transformers/services can become `onError` signals on the publisher and propagate as RSocket errors. If using Spring Integration's `errorChannel`, verify whether the error flow **produces a reply**, emits an error, or terminates silently. Never merely log an `ErrorMessage` and drop it, or callers hang until timeout and data goes unrecorded.

For fire-and-forget, clients have no business response channel to check outcomes; monitor the server, use receipts at another layer, or use durable messaging when SLAs forbid data loss.

## 16. Testing layers independently

**Transformer unit tests** verify payload transformations, validation/routing, and error mapping. **Real RSocket integration tests** verify channels, connectors, codecs, routes, and subscriptions end-to-end with Spring Boot.

| Scenario | Setup | Expected outcome |
| --- | --- | --- |
| Server startup | Boot with `spring.rsocket.server.port` and RSocket module | Calling route over TCP succeeds |
| Inbound `requestResponse` | Send SKU to `inventory.stock` | Transformer receives `Flux` and returns expected response |
| Wrong interaction model | Send `requestStream` to a `requestResponse`-only endpoint | Rejected/not routed per contract |
| Outbound via `ClientRSocketConnector` | Send Message to `stockLookupRequests` | Remote receives one request; reply enters configured channel |
| MIME/codec mismatch | Client sends wrong content type or schema | Controlled decode error; no bad writes |
| Metadata/correlation | Send valid trace ID | Server records trace and returns correlated result |
| Missing auth/wrong permissions | Call restricted route | Rejected before side effects |
| Reactive stream/backpressure | Server streams many items; subscriber requests in chunks | Bounded buffering and demand respected; no OOM |
| Client stream cancel | Caller cancels mid-stream | Server stops work and releases resources per policy |
| Transport drop/reconnect | Cut TCP and retry calls | New connections serve new requests; old stream recovery is clear |
| Resume (if enabled) | Brief network drop while session state exists | `RESUME_OK` or controlled fallback per config |
| Timeout after SQL commit | Hold or drop response after DB write | Retrying with same `requestId` does not duplicate side effects |
| Spring Integration + `@MessageMapping` | Enable compatible property, register 2 distinct routes | Both gateway endpoint and controller work |
| Multiple backends | Two distinct `ClientRSocketConnector` beans | Each flow targets its qualified endpoint |
| Error channel | Transformer throws error | Reaches error flow and signals caller appropriately |
| Shutdown | Stop Spring context while streams are active | Connectors close / streams cancel within SLA |

An integration test can call the test server directly with `RSocketRequester` on a dynamic port. If using server port `0`, obtain the bound port as supported by Boot/connectors rather than hardcoding ports that collide in CI. Never merely assert `ApplicationContext` starts and assume RSocket routes are wired.

### Testing Reactor with `StepVerifier`

Isolated logic example:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class StockTransformerTest {

    @Test
    void convertsFirstSkuToUppercase() {
        var source = Flux.just("sku-1", "sku-2");

        StepVerifier.create(
                source.next().map(String::toUpperCase))
            .expectNext("SKU-1")
            .verifyComplete();
    }
}
~~~

This tests only the reactive operator. To test `RSocketInboundGateway` and `RSocketOutboundGateway`, run connectors against real server/client transports or an integration setup. Pair happy-path tests with parse failures, cancellations, timeouts, concurrent requests, and rollbacks.

## 17. Troubleshooting by symptom

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| Route call returns "route not found"/unhandled | Wrong route, unregistered gateway, wrong server handler | Inspect mappings, connector/server startup, and versions |
| Boot opens server but inbound flow doesn't run | Missing `spring-integration-rsocket` or endpoint not discovered | Check classpath, connector beans, route, and request channel |
| `@MessageMapping` works but Integration gateway doesn't | Two independent handlers or mixed mapping disabled | Check `spring.integration.rsocket.server.message-mapping-enabled` |
| Boot client bean missing | Missing client host/port/uri or unmet auto-config conditions | Inspect properties, dependencies, and auto-configuration report |
| Outbound cannot reach server | Wrong host/port/transport/TLS | Test directly with `RSocketRequester`; check handshake |
| Outbound returns unexpected type | Mismatched `expectedResponseType`/codec/Publisher | Inspect reply publisher and downstream channel |
| Fire-and-forget sends nothing | Cold `Mono` never subscribed | Verify output channel and subscription |
| `requestStream` gets one item then stops | Transformer calls `next()` or cancels upstream | Inspect pipeline/interaction model and subscriber demand |
| Request handler hangs | Blocking code on event loop or missing reply/error | Thread dumps, latency, Reactor debug, error handling |
| Flaky connections | Proxy idle timeout, TLS, keepalive, reconnect policy | Connection/keepalive metrics, proxy logs |
| Business command executes twice | Retry after timeout/reconnect without idempotency | Check `requestId`, unique inbox, SQL transactions |
| `errorChannel` logs but client times out | Error flow produces neither reply nor `onError` | Test gateway reply behavior under exceptions |
| Growing buffers/`OutOfMemoryError` | Unbounded `collectList()`, broken backpressure | Check heap, active streams, pending buffers |
| Browser WebSocket fails to connect | Wrong path, Origin, TLS, codec, or proxy config | Network trace and WebFlux/ingress config |

When diagnosing, separate **transport** (TCP/WebSocket, TLS), **RSocket protocol** (route, interaction model, frames, keepalive), **Spring Integration** (channels, transformers, replies/errors), and **business logic** (DB commit, idempotency, brokers). The same "no response" symptom can originate in any layer; measure timings and signals at each layer to locate the root cause.

## 18. Pre-deployment checklist

1. Choose plain Spring Messaging vs. Spring Integration gateways based on integration flow needs; identify `RSocketInboundGateway`/`RSocketOutboundGateway` accurately.
2. Align `spring-boot-starter-rsocket`, Spring Integration RSocket, and Spring Framework versions via a compatible BOM.
3. Maintain one clear server creation/route registration model; verify `spring.rsocket.server.*` and mixed `@MessageMapping` if used.
4. Use `spring.integration.rsocket.client.host/port` or `uri` for Boot-configured connectors when suitable; avoid duplicate connectors.
5. Lock down routes, interaction models, payload/reply types, MIME types, schema versions, and metadata between clients and servers.
6. Design channels for reactive semantics, subscriptions/backpressure, timeouts, cancellation, and zero event-loop blocking.
7. For fire-and-forget, never treat frame send as a business ACK; for writes, enforce idempotency keys and receipts.
8. Bound retry/reconnect/resume per SLA; maintain an overall time budget and monitor attempt counts.
9. Separate database transactions from RSocket, brokers, and HTTP; use inbox/outbox for durable handoffs.
10. Protect connections with TLS and authentication/authorization; cap payload sizes/concurrency and omit sensitive data from logs.
11. Instrument metrics/traces across transport, gateways, channels, and downstream; alert on connection failures, timeouts, and business lag.
12. Test over real networks for route mapping, codecs, mixed handlers, streaming, cancellation, reconnects, SQL errors, and shutdown.

### Version-aligned references

- [Spring Integration 6.5 – RSocket Support](https://docs.spring.io/spring-integration/reference/6.5/rsocket.html): connectors, inbound/outbound gateways, Java DSL, `Publisher` interactions, and replies.
- [Spring Boot 3.5 – Spring Integration](https://docs.spring.io/spring-boot/3.5/reference/messaging/spring-integration.html): configuring RSocket connectors and Boot's integration infrastructure.
- [Spring Boot – RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): `RSocketStrategies`, servers, `RSocketRequester`, and Spring Messaging.
- [Spring Integration – Endpoint Summary](https://docs.spring.io/spring-integration/reference/endpoint-summary.html): distinguishing adapters and gateways across modules.
- [Spring Integration 6.5 API – RSocketInboundGateway](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/rsocket/inbound/RSocketInboundGateway.html): `requestElementClass`, `interactionModels`, and gateway behavior.
- [Spring Integration 6.5 API – RSocketOutboundGateway](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/rsocket/outbound/RSocketOutboundGateway.html): routes, reactive responses, and channel types.

**Key takeaway:** RSocket provides asynchronous interaction models; Spring Messaging supplies requesters, handlers, and codecs; Spring Integration brings those calls into **`MessageChannel`** pipelines via inbound/outbound gateways; and Spring Boot wires infrastructure from dependencies and properties. Building a reliable integration flow still requires designing response subscriptions, backpressure, timeouts, security, transactions, idempotency, and failure-recovery testing.

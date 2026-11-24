# Distinguishing RSocket from STOMP, HTTP, and Durable Queues

## Learning Objectives

After this lesson, you will be able to:

- Distinguish transport protocols, messaging protocols, and message storage mechanisms.
- Explain how RSocket provides four interaction models: Request-Response, Request-Stream, Channel, and Fire-and-Forget.
- Compare RSocket with HTTP request/response and STOMP over WebSocket.
- Understand RSocket backpressure, multiplexing, metadata, routing, and session resumption.
- Distinguish real-time connections from queues with persistence, acknowledgements, and retries.
- Choose the appropriate technology for RPC, streaming, broadcasting, client-server communication, and background job processing.
- Combine RSocket, HTTP, STOMP, and durable queues in the same architecture when each solves a distinct need.

## 1. Four Commonly Confused Concepts

RSocket, STOMP, HTTP, and durable queues are often placed side by side when designing communication between components. However, they solve problems at different layers.

- **HTTP** is a client/server protocol following a request/response model. The client sends a request and the server returns a response. HTTP is designed to be stateless: the meaning of each request can be understood independently.
- **STOMP** is a frame-based messaging protocol. It defines commands such as CONNECT, SEND, SUBSCRIBE, MESSAGE, UNSUBSCRIBE, and DISCONNECT, along with destinations and headers. In Spring, STOMP typically runs over WebSocket.
- **RSocket** is an application protocol for bidirectional, asynchronous communication supporting multiple interaction styles and Reactive Streams semantics. It can run over TCP, WebSocket, and other byte-stream transports.
- **Durable queue** is a capability of a message broker system: messages and queues can be persisted durably so messages survive certain failures or periods when consumers are offline. Actual durability depends on broker configuration, message persistence, replication, and acknowledgements.

Key point: WebSocket is a transport, STOMP and RSocket are application protocols, and a durable queue is a broker storage and delivery capability. They should not be viewed as four directly interchangeable protocols.

## 2. Communication Layer Map

~~~text
Application behavior
   |
   +-- HTTP API: request / response
   |
   +-- STOMP messaging: SEND / SUBSCRIBE / destination
   |       |
   |       +-- WebSocket transport or SockJS fallback
   |       +-- Simple Broker or external STOMP broker
   |
   +-- RSocket: request-response / stream / channel / fire-and-forget
           |
           +-- TCP, WebSocket, or other byte-stream transports

Durable messaging:
   Publisher --> durable broker/queue --> consumer
                 persistence, ack, retry, replication
~~~

Some systems use WebSocket as the transport for RSocket. That does not turn RSocket into STOMP. The two protocols have separate framing, interaction models, flow control, and semantics, even when running over the same WebSocket transport.

Similarly, STOMP can be relayed to RabbitMQ or ActiveMQ. Having an external broker does not automatically turn every destination into a durable queue; queues, subscriptions, persistence, and acknowledgements must be configured per the specific broker and protocol.

## 3. HTTP: Request/Response for APIs and Resources

HTTP is suitable when a client wants to request an action or resource representation and receive a result:

- Fetching a user profile.
- Creating an order.
- Updating status.
- Downloading a report or file.
- Filtered and paginated search.

Spring MVC example:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderDto getOrder(@PathVariable long id) {
        return orderService.findById(id);
    }

    @PostMapping
    public ResponseEntity<OrderDto> createOrder(
            @RequestBody CreateOrderRequest request) {

        OrderDto created = orderService.create(request);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(created);
    }
}
~~~

HTTP provides clear semantics via methods, status codes, headers, caching, and conditional requests. Request/response also integrates easily with browsers, API gateways, proxies, CDNs, and observability tools.

HTTP is not by default a long-lived bidirectional message stream. The server normally replies to the current request; if the client wants fresh updates, it can send another request, use polling, Server-Sent Events, WebSocket, or an appropriate streaming protocol.

Stateless HTTP also does not mean an application cannot have sessions or authentication. It means the semantics of each request are designed to be self-contained, while application state is managed at a higher layer.

## 4. STOMP: Messaging by Destination and Subscription

STOMP is a frame-based messaging protocol. Clients can:

- Send `SEND` to a destination to ask the application to process a message.
- Send `SUBSCRIBE` to a destination to receive messages.
- Cancel subscriptions with `UNSUBSCRIBE`.
- End the session with `DISCONNECT`.

In Spring, STOMP commonly runs over WebSocket. WebSocket supplies the bidirectional channel; STOMP defines how messages are sent and routed by destination.

Basic configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Controller:

~~~java
@Controller
public class NotificationController {

    @MessageMapping("/notifications/read")
    public NotificationResult markRead(
            ReadNotificationRequest request) {
        return new NotificationResult(
                request.notificationId(), true);
    }

    public record ReadNotificationRequest(long notificationId) {}

    public record NotificationResult(long notificationId,
                                     boolean read) {}
}
~~~

Clients can send `SEND /app/notifications/read` and subscribe via `SUBSCRIBE /topic/notifications`.

Spring routes destinations starting with `/app` to controllers. Destinations starting with `/topic` or `/queue` can be forwarded to the configured message broker.

### 4.1 Strengths of STOMP

- Intuitive pub/sub and destination model.
- Browser support and multi-language STOMP clients.
- Direct integration with Spring `@MessageMapping`, `SimpMessagingTemplate`, and user destinations.
- Well suited for notifications, dashboards, chat, and UI updates.
- Can use SockJS fallback when WebSocket is unavailable.
- Can relay to an external STOMP broker to distribute across multiple nodes.

### 4.2 Simple Broker vs. External Broker

Spring's Simple Broker keeps subscriptions in memory and broadcasts messages to connected clients with matching destinations. It is convenient for getting started, yet it does not fully support STOMP commands like ACK and RECEIPT, is not a clustered broker, and does not provide durable queues.

When a fuller broker is needed, Spring can use STOMP Broker Relay to forward messages over TCP to an external broker. Durable queues, persistence, retries, acknowledgements, and clustering still depend on the external broker, its STOMP plugin, and actual configuration.

The destination name `/queue/orders` by itself does not guarantee that each message is received by only one consumer or stored while a consumer is offline. Destination semantics depend on the broker.

## 5. RSocket: Bidirectional Interaction and Streaming Protocol

RSocket is an application protocol for multiplexed, full-duplex communication over TCP, WebSocket, or other byte-stream transports.

Once a connection is established, both sides can initiate requests. Accordingly, RSocket uses the terms requester and responder rather than fixing one side as always the client and the other as always the server.

RSocket defines four interaction models:

| Interaction | Input | Output | Example |
|---|---|---|---|
| Request-Response | One message | One message | Fetch account details |
| Request-Stream | One message | A stream of many messages | Watch prices or telemetry |
| Channel | A stream | A bidirectional stream | Continuous two-way exchange |
| Fire-and-Forget | One message | No response payload | Send a signal needing no reply |

### 5.1 Request-Response

One request receives one response. This model resembles RPC or HTTP request/response, yet uses an RSocket connection and protocol framing.

Example: service A requests customer information from service B.

### 5.2 Request-Stream

The requester sends one request and receives multiple responses over time. This is a natural choice for telemetry, market quotes, or continuous data.

### 5.3 Channel

Both sides exchange message streams in both directions within the same interaction. For example, a client sends a stream of locations while receiving navigation instructions.

### 5.4 Fire-and-Forget

The requester sends a message without requesting a response payload. This model suits one-way signals when the caller needs no return result.

Understand the semantics accurately: in Spring, `RSocketRequester.send()` returns `Mono<Void>` indicating that sending the message completed. It does not prove the responder finished business processing or durably persisted the data.

## 6. RSocket Backpressure and Multiplexing

A standout feature of RSocket is that Reactive Streams semantics can cross network boundaries.

With Request-Stream and Channel:

- The requester signals demand for the number of elements it wants to receive.
- The responder must honor demand.
- The requester can request additional elements once it finishes processing earlier ones.
- The producer can slow emission at the source when the consumer cannot keep up.

This controls data flow and reduces the need for unbounded buffers. However, backpressure only works when every component in the pipeline actually supports and propagates demand properly. If an application collects all data into a list or uses unbounded blocking APIs, backpressure benefits can be lost.

RSocket also supports multiplexing many requests over a single connection. This lets multiple independent interactions share one connection instead of needing a separate connection per request stream.

Multiplexing must not be mistaken for infinite resources. Connections still consume memory, buffers, CPU, stream state, and processing resources. Set timeouts, limit concurrency, monitor stream counts, and manage cancellation.

## 7. RSocket Has Session Resumption, Not a Durable Queue

RSocket provides session resumption to help recover long-lived streams when the transport connection drops and is re-established. This mechanism requires keeping some state for resuming and can combine with backpressure to limit the amount of retained data.

Distinguish clearly:

- **Session resumption:** recovers protocol/session state within RSocket's capabilities and configuration.
- **Durable queue:** stores messages in a broker so they survive offline consumers or certain failures.
- **Business persistence:** saves business data or events in a database/event store.
- **Acknowledgement:** confirms a message was received or processed per broker/protocol semantics.

Session resumption does not turn RSocket into indefinite message storage. It does not replace a durable queue, database, or outbox. Nor does it prove that a business transaction committed.

If a message must be processed even if the target service is offline for a long time, persist the message to a broker or durable store before delivery. RSocket can serve as the real-time interaction channel between active services, while durability must be designed separately.

## 8. Durable Queues: Message Persistence and Delivery Acknowledgements

A durable queue is a message broker model capable of storing queue metadata and messages according to persistence configuration. A durable queue typically requires combining multiple factors:

- The queue is declared durable.
- Messages are published in persistent mode when required by the protocol/broker.
- The broker has appropriate durable writes and replication.
- Publishers confirm the broker accepted the message.
- Consumers acknowledge messages after successful processing.
- Retry and dead-letter policies are configured to handle failures.

For example, with RabbitMQ, durable queues and persistent messages allow messages to be recovered after restarts according to configuration. Publisher confirms and consumer acknowledgements address two different confirmation directions:

- Publisher confirm: the broker confirms the publish was accepted per broker semantics.
- Consumer acknowledgement: the consumer confirms the delivery was processed so the broker can mark the message for removal appropriately.

These two mechanisms are independent. A publisher confirm does not prove the consumer processed the message; a consumer acknowledgement does not prove the publisher received its confirm.

### 8.1 At-Least-Once and Idempotency

With retries and redeliveries, a consumer may receive the same message multiple times. Therefore, business processing should be idempotent:

- Attach a unique event ID to each message.
- Store processed status or enforce unique constraints.
- Check the event ID before applying changes.
- ACK only after business processing succeeds as designed.

Do not assume retries automatically yield exactly-once processing. End-to-end exactly-once typically requires coordinating transactions, deduplication, and storage-system semantics.

### 8.2 Do Not Confuse STOMP RECEIPT with Consumer Acknowledgement

STOMP RECEIPT confirms that the broker processed a frame that requested a receipt. It does not mean a subscriber completed business processing.

STOMP ACK has its own semantics depending on the acknowledgement mode and broker. Spring's Simple Broker does not fully support ACK and RECEIPT. External brokers may support them partially or fully, so check the STOMP plugin and documentation for your exact version.

If using RabbitMQ, do not assume AMQP 0-9-1 publisher confirms and consumer acknowledgements automatically expose the same API or semantics when clients connect through the STOMP plugin. Verify the capabilities of the protocol actually in use.

## 9. Overall Comparison Table

| Criterion | HTTP | STOMP over WebSocket | RSocket | Durable queue |
|---|---|---|---|---|
| Primary role | Request/response API | Destination-based pub/sub messaging | Bidirectional request/response and streaming | Durable message storage and distribution |
| Protocol | HTTP | STOMP | RSocket | Broker/protocol dependent |
| Transport | TCP/TLS, HTTP/2 or HTTP/3 depending on stack | WebSocket, optionally SockJS fallback | TCP, WebSocket, and byte-stream transports | TCP or broker-supported transports |
| Interactions | Request/response | SEND, SUBSCRIBE, MESSAGE | Request-Response, Request-Stream, Channel, Fire-and-Forget | Publish/consume, queues, acks |
| Streaming | Possible via APIs/extensions like SSE or streaming responses | Continuous messages over subscriptions | Native Request-Stream and Channel | Consumers receive sequences of messages |
| Backpressure | Depends on API/streaming model | No end-to-end Reactive Streams demand by default | Reactive Streams demand across network | Broker prefetch/flow control |
| Routing | URL, method, headers | STOMP destinations | Route metadata | Exchanges, queues, routing keys, or subscriptions |
| Durability | Does not store requests/responses automatically | Not built-in; depends on broker | Not a durable queue itself | Available when persistence is configured |
| Offline consumers | Clients must re-request | Simple Broker does not retain messages for offline clients | Session resumption has limited scope | Can retain messages in queues |
| Best suited for | CRUD, APIs, resources | Real-time UI, notifications, chat | Reactive RPC, streams, duplex services | Jobs, events, retries, and decoupled consumers |

## 10. Spring RSocket Server Example

Spring Framework supports RSocket responders via `@MessageMapping` and `@ConnectMapping`. Spring Boot can auto-configure `RSocketMessageHandler` and `RSocketStrategies` when the appropriate starter is used.

A Request-Response handler:

~~~java
@Controller
public class UserRSocketController {

    @MessageMapping("users.find")
    public Mono<UserView> findUser(UserQuery query) {
        return userService.findById(query.userId());
    }

    public record UserQuery(long userId) {}

    public record UserView(long id, String name) {}
}
~~~

If the method accepts one payload and returns `Mono<T>`, that is a one-input, one-output model matching Request-Response.

Request-Stream handler:

~~~java
@Controller
public class TelemetryRSocketController {

    @MessageMapping("devices.telemetry")
    public Flux<TelemetrySample> telemetry(DeviceQuery query) {
        return telemetryService.stream(query.deviceId());
    }

    public record DeviceQuery(String deviceId) {}
}
~~~

One input payload and `Flux<T>` output create a Request-Stream. When the requester reduces demand or cancels the subscription, the responder must honor the publisher lifecycle and release related resources.

### Spring Boot Configuration

For a WebFlux application exposing RSocket over WebSocket, configure:

~~~properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
~~~

Spring Boot also supports a standalone RSocket server over TCP or WebSocket depending on configuration. When using a standalone TCP server, you can configure the port, for example:

~~~properties
spring.rsocket.server.port=9898
~~~

Embedding RSocket into a WebFlux web server over WebSocket requires Reactor Netty per Spring Boot configuration. Check dependencies and application type before choosing a deployment mode.

## 11. Spring RSocket Client Example with RSocketRequester

`RSocketRequester` provides a fluent API to create requests and encode payloads and metadata.

TCP connection:

~~~java
RSocketRequester requester =
        RSocketRequester.builder()
                .tcp("localhost", 9898);
~~~

Calling Request-Response:

~~~java
Mono<UserView> user = requester
        .route("users.find")
        .data(new UserQuery(42L))
        .retrieveMono(UserView.class);
~~~

Calling Request-Stream:

~~~java
Flux<TelemetrySample> samples = requester
        .route("devices.telemetry")
        .data(new DeviceQuery("device-17"))
        .retrieveFlux(TelemetrySample.class);
~~~

Sending Fire-and-Forget:

~~~java
Mono<Void> sent = requester
        .route("audit.record")
        .data(new AuditEvent("USER_LOGIN", "user-42"))
        .send();
~~~

With Fire-and-Forget, subscribe to `Mono<Void>` or compose it into a reactive pipeline so sending actually runs. The completion signal only indicates the message was sent per client/protocol semantics; it does not prove the handler processed it or the database committed.

Connecting over WebSocket is also supported:

~~~java
URI uri = URI.create("ws://localhost:8080/rsocket");

RSocketRequester requester =
        RSocketRequester.builder()
                .webSocket(uri);
~~~

If timeouts, authentication, keepalive, session resumption, or interceptors are needed, configure `RSocketRequester.Builder` and the underlying `RSocketConnector` to match system requirements.

## 12. When Should Each Technology Be Chosen?

### Choose HTTP When

- Clients need to read or mutate resources per explicit request.
- APIs must be easily called from browsers, mobile apps, partners, or HTTP tooling.
- Caching, status codes, pagination, and idempotent methods matter.
- Requests do not need to hold a long-lived bidirectional stream.

### Choose STOMP When

- Browsers need to subscribe to receive notifications or broadcasts.
- The destination and pub/sub model is central.
- The application already uses Spring WebSocket messaging and needs `@MessageMapping`.
- Simple Broker limits are acceptable or a suitable external STOMP broker is available.

### Choose RSocket When

- Services need request/response and streaming over the same protocol.
- Full-duplex communication and many concurrent interactions over one connection are required.
- Backpressure across the network is an important advantage.
- Both client and server can actively initiate requests.
- The system adopts the reactive model and can operate Reactor/Netty.

### Choose a Durable Queue When

- Work must still be processed even while consumers are offline.
- Retries, redelivery, or dead-letter queues are needed.
- Publisher confirms, consumer acknowledgements, or persistence are required.
- Publishers and consumers need decoupled lifecycles.
- Buffering load when producer and consumer speeds differ is required.

## 13. Combining Technologies Together

You do not have to choose a single protocol for every need.

A common architecture:

~~~text
Browser / Mobile
   |
   +---- HTTP API --------------------> Business service
   |
   +---- STOMP / WebSocket ----------> Realtime notification
                                          |
                                          v
                                    Spring application
                                          |
                                          v
                                   Durable message broker
                                          |
                                          v
                                   Background consumers

Internal reactive services
   |
   +---- RSocket request/stream/channel ----> Other services
~~~

Example order-placement workflow:

1. The client calls HTTP POST to create an order.
2. The service saves the order in the database and writes an event to an outbox in the same transaction.
3. A publisher reads the outbox and sends the event to a durable broker.
4. Consumers handle background tasks such as payment or sending email.
5. The service emits notifications to a STOMP topic so the browser updates the UI.
6. Internal services can use RSocket for reactive queries or streaming telemetry.

Role of each component:

- HTTP is the synchronous business API.
- The durable broker retains jobs/events needing processing independent of client connection state.
- STOMP is the real-time channel for UI updates.
- RSocket is the reactive interaction channel between services needing streaming or duplex requests.

When combining them, design correlation IDs, event IDs, idempotency, retries, timeouts, and observability across all layers.

## 14. Common Misconceptions

| Misconception | Reality |
|---|---|
| RSocket is a kind of durable queue | RSocket is an interaction protocol; durability requires a separate broker/store |
| RSocket runs over WebSocket so it is like STOMP | Sharing a transport does not mean sharing framing, routing, or interaction models |
| Request-Stream automatically stores messages for offline clients | Streams and backpressure do not automatically provide queue persistence |
| Fire-and-Forget guarantees the server finished processing | It has no response payload; send completion does not prove business completion |
| STOMP /queue is always a point-to-point queue | Meaning depends on the broker; Spring Simple Broker broadcasts to matching subscriptions |
| STOMP RECEIPT is a consumer acknowledgement | Receipt confirms the broker processed the frame, not that a consumer finished business logic |
| HTTP cannot stream | HTTP can use SSE, streaming responses, and other mechanisms; semantics depend on the API |
| Session resumption equals message persistence | Resumption recovers session/stream protocol state, not durable storage |
| Using RSocket eliminates timeouts or concurrency limits | Reactive protocols still need resource limits, timeouts, and monitoring |

## 15. Security and Operations

Regardless of the protocol chosen, design authentication and authorization explicitly.

- For HTTP, secure endpoints, verify per-resource permissions, and use TLS.
- For STOMP, authenticate connections and control SEND/SUBSCRIBE permissions by destination.
- For RSocket, configure authentication metadata, per-route authorization, and TLS per deployment requirements.
- For durable brokers, manage credentials, vhosts/namespaces, publish/consume permissions, and isolated network access.

Observability should include:

- Active connection and stream counts.
- Request rates, message rates, and payload sizes.
- p50/p95/p99 latencies.
- Timeouts, cancellations, disconnects, and reconnects.
- Backpressure/demand and buffered element counts.
- Queue depth, unacknowledged messages, redelivery, and dead-letter rates.
- Encode/decode error rates and authentication/authorization failure rates.

Do not log access tokens, passwords, cookies, or sensitive payloads. Use correlation IDs and trace IDs to follow requests or events across services.

## 16. Self-Check Exercises

### Exercise 1

A service needs to send a request and receive an object. Which RSocket interaction model fits?

**Answer:** Request-Response.

### Exercise 2

A client sends one request and continuously receives thousands of telemetry samples. Which model should be used?

**Answer:** Request-Stream. If both sides send message streams, consider Channel.

### Exercise 3

An application needs to retain jobs while workers are offline and process them after workers connect. Is RSocket Fire-and-Forget enough?

**Answer:** No. A durable queue or store with persistence and appropriate acknowledgement/retry mechanisms is required.

### Exercise 4

A browser needs to receive notifications when an order changes status. Which technology fits?

**Answer:** STOMP over WebSocket is a good fit for real-time pub/sub. Order status and notification history should still be persisted in the backend.

### Exercise 5

An internal service needs to stream data with backpressure across the network. Why can RSocket be a better fit than a regular HTTP request/response API?

**Answer:** RSocket provides Request-Stream and Channel with Reactive Streams demand propagated across network boundaries, allowing the requester to pace the responder. HTTP can still stream, yet requires choosing the corresponding mechanism and semantics.

### Exercise 6

A RabbitMQ publisher confirm was received. Does that prove the consumer finished processing the message?

**Answer:** No. Publisher confirm verifies that the broker accepted the publish per its semantics; consumer acknowledgement is a separate mechanism to confirm a delivery was processed.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Framework — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [RabbitMQ — Queues and Durability](https://www.rabbitmq.com/docs/queues)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)

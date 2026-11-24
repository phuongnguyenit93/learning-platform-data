# Choosing JMS, STOMP, or RSocket Based on Communication Peers

JMS, STOMP, and RSocket all enable components to exchange messages, but they serve different communication styles. Choosing the right technology starts with asking **who is talking to whom, what interaction style is needed, and how long messages must survive**.

- Choose **JMS** when backend applications need to send commands or events through a broker, decouple producers from consumers, and support asynchronous processing, queues/topics, acknowledgements, and transactions according to provider capabilities.
- Choose **STOMP** when a server needs to exchange messages with browser or mobile clients over WebSocket, manage subscriptions, and push events to multiple sessions/destinations.
- Choose **RSocket** when two services or client/server need bidirectional communication, request-response, or streaming with Reactive Streams backpressure over a long-lived connection.

Do not choose based on speed alone. Identify requirements upfront for offline delivery, durability, fan-out, request/reply, streaming, backpressure, client count, and broker operational capacity.

## 1. Distinguishing protocols, APIs, and brokers

These three names do not live at the same layer:

| Technology | Nature | Common Spring APIs | Communication infrastructure |
| --- | --- | --- | --- |
| JMS | Standardized Java/Jakarta messaging API and programming model | `JmsTemplate`, `JmsClient` (Spring Framework 7), `@JmsListener` | JMS provider/broker such as ActiveMQ Artemis or IBM MQ |
| STOMP | Text-based messaging protocol with frames `CONNECT`, `SEND`, `SUBSCRIBE`, `MESSAGE`, `ACK`... | Spring WebSocket/STOMP, `@MessageMapping`, `SimpMessagingTemplate` | WebSocket endpoint and simple broker or external STOMP broker relay |
| RSocket | Binary application protocol for multiplexed, duplex messaging | `RSocketRequester`, `@MessageMapping`, `@ConnectMapping` | TCP, WebSocket, or compatible byte-stream transport; usually direct requester-responder connection |

JMS is an API that Java applications use to work with a provider; the broker handles storage, routing, and message delivery. STOMP defines frame formats and semantics; WebSocket only provides a bidirectional channel to carry frames. RSocket defines interaction protocols and flow control over a byte-stream transport. Spring provides programming models for each choice, but does not turn them into the same kind of infrastructure.

## 2. Quick decision table

| Communication peer / need | Usually suitable choice | Reason |
| --- | --- | --- |
| Backend service sending commands to workers for later processing | JMS Queue | Producer and consumer are decoupled; broker holds messages per provider config when consumers are unavailable |
| Multiple backend services needing the same business event | JMS Topic or broker pub/sub | Each subscription can receive a copy per provider semantics |
| Application needing request/reply while still going through a broker | JMS request/reply | Can use reply-to destinations and correlation IDs; requires managing timeouts and temporary/durable reply destinations |
| Browser needing notifications or live UI updates | STOMP over WebSocket | Browser maintains a session, subscribes to destinations, and receives server pushes |
| Multiple browsers needing the same real-time event | STOMP topic/destination | Broker fans out to active subscriptions |
| Browser sending commands to a Spring server via a message destination | STOMP over WebSocket | `@MessageMapping`, destination routing, and Spring Security message authorization |
| Service calling another service and receiving a single result | RSocket Request-Response or HTTP | RSocket supports async request/reply over a connection; HTTP is often simpler if connection-based messaging is not needed |
| Service receiving a data stream with backpressure | RSocket Request-Stream | Demand is propagated across the Reactive Streams boundary |
| Both sides needing to send and receive streams simultaneously | RSocket Channel | Supports bidirectional streaming within the same interaction |
| Work must be retained when consumers are offline or restarting | JMS with appropriate persistence/transactions | RSocket and STOMP session messaging do not provide durable work queues by default |
| Pushing real-time telemetry to clients while durably storing backend events | JMS + STOMP | JMS processes backend events; a service pushes notifications via STOMP to online clients |

These are guiding rules. A technology can support multiple communication styles, given appropriate configuration and application contracts. For instance, JMS also supports request/reply, STOMP has broker relays, and RSocket has Fire-and-Forget; that does not give them identical durability or fan-out semantics.

## 3. JMS: backend communication via a broker

### 3.1. When to choose JMS?

JMS fits when communication peers are Java/backend applications or independent workers and messages must be managed by a broker. Producers can send messages and continue working; consumers receive and process when they have capacity. This is useful for:

- Commands to process orders, send emails, generate invoices, or run background jobs.
- Enterprise system integration via a shared broker.
- Publishing business events to multiple consumers using Topics.
- Work queues with competing consumers to increase throughput.
- Asynchronous request/reply over queues when two systems need explicit correlation and timeouts.

JMS defines two fundamental destination models:

| Destination | Delivery behavior | Common use cases |
| --- | --- | --- |
| Queue (point-to-point) | Each message is processed by one consumer in the group; multiple consumers compete for work | Work queues, commands, jobs |
| Topic (publish-subscribe) | Each matching subscription receives a copy of the message | Domain events needed by multiple interested systems |

Topic subscriptions can be non-durable or durable depending on provider and configuration. Durable subscriptions let subscribers receive messages published while they were offline, subject to the broker's storage policies. Proper subscription/client identifiers and broker retention, expiration, and quota settings are required.

### 3.2. Spring JMS API

`JmsTemplate` is the central API for sending and receiving messages; `@JmsListener` declares consumers. Spring Framework 7 also includes `JmsClient` with a fluent API for send/receive and integrated message conversion. Example sending a command:

```java
jmsTemplate.convertAndSend("orders.commands", command);
```

Example listener processing a command:

```java
@Component
public class OrderCommandListener {

    @JmsListener(destination = "orders.commands",
                 containerFactory = "ordersListenerFactory")
    public void handle(OrderCommand command) {
        orderService.process(command);
    }
}
```

These are illustrative snippets; `OrderCommand`, `orderService`, and `ordersListenerFactory` are application components. `DefaultJmsListenerContainerFactory` is typically used to configure listener containers, concurrency, transactions, and acknowledgements.

```java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}
```

`sessionTransacted=true` makes each listener invocation run in a local JMS transaction. If the listener throws an exception before commit, message receipt can roll back and the provider can redeliver according to policy. This does not automatically create an atomic distributed transaction with databases or HTTP services; design outbox, idempotency, or XA if coordinating multiple resources is truly necessary.

### 3.3. Durability and delivery guarantees are not automatic

Do not infer that "using JMS guarantees zero message loss." Outcomes depend on delivery mode, persistence, broker policies, acknowledgements, transactions, and how consumers handle messages:

- Persistent messages instruct the provider to persist messages per provider semantics; non-persistent messages may not survive broker shutdown.
- With `AUTO_ACKNOWLEDGE`, Spring warns that messages can be lost if a listener fails or the container stops in certain scenarios. If reliability is needed for queues or durable topic subscriptions, consider transacted sessions or appropriate acknowledgement modes.
- Transactional receive rolls back messages when listeners fail, but can produce duplicates if the JVM crashes at the commit/ack boundary. Consumers still need idempotency.
- `DefaultMessageListenerContainer` supports recovery when a broker goes down; by default it uses simple backoff, and a custom `BackOff` can be configured.
- Dead-letter handling, retry limits, TTL, redelivery delays, and poison-message handling are usually provider/broker configurations.

Choose JMS when you need a broker managing work and can operate the broker, schemas, queues/topics, retention, transactions, and monitoring. If you only need a simple synchronous call between two services, HTTP may involve less complexity.

## 4. STOMP: communicating with browsers and client sessions

### 4.1. When to choose STOMP?

STOMP usually fits when the communication peer is a browser or mobile app maintaining a real-time connection with the server. WebSocket establishes a long-lived bidirectional channel; STOMP adds protocol frames and destinations so clients can send, subscribe, and receive messages without inventing a custom protocol.

Examples:

- Dashboards receiving order status updates or telemetry.
- Chat, collaboration, presence, and notifications.
- Clients subscribing to `/topic/rooms/42` to receive events for a room.
- Clients sending commands to `/app/orders.create` for Spring to route to `@MessageMapping`.
- Server sending notifications to `/user/queue/notifications` for a specific session/user.

### 4.2. Message flow in Spring

```text
Browser / Mobile
      | WebSocket + STOMP frames
      v
clientInboundChannel
      |
      +-- /app/... --> @MessageMapping controller
      |                    |
      |                    v
      |               brokerChannel
      |                    |
      +----------------> Message broker
                           |
                           v
                    clientOutboundChannel
                           |
                           v
                    WebSocket sessions
```

Spring commonly configures the application prefix `/app` and broker prefixes such as `/topic` or `/queue`. Messages sent to `/app/...` are routed to annotated controllers; messages sent to broker destinations are handled by the broker according to subscriptions. `SimpMessagingTemplate` allows sending messages from any server-side component.

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Controller receiving commands and broadcasting results:

```java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/rooms")
    public ChatMessage send(ChatMessage message) {
        return chatService.accept(message);
    }
}
```

This code is an illustrative example; in real applications you must authenticate senders, check room membership permissions, and validate payloads. Clients can subscribe to `/topic/rooms` and send to `/app/chat.send`.

### 4.3. Simple broker or external broker relay?

Spring offers two common broker choices:

| Option | Characteristics | When to use |
| --- | --- | --- |
| Simple broker | Runs in memory inside a single Spring application instance; supports basic STOMP features | Demos, development, or small single-node apps with simple needs |
| External broker relay | Spring relays STOMP frames to an external broker such as RabbitMQ or ActiveMQ | Multi-node production, broker subscriptions, clustering, and broker-specific delivery features |

The simple broker is not a durable queue cluster and does not share subscription state across multiple application servers. If scaling across multiple nodes or using broker-managed destinations is needed, use an external broker relay and configure the broker accordingly. Even with an external broker, verify specific ACK modes, durable subscriptions, receipts, retention, and reconnect behavior; the STOMP protocol itself does not promise every message will be stored for offline clients.

### 4.4. User destinations, sessions, and security

`/user/queue/...` is a logical destination that Spring resolves by user/session. `convertAndSendToUser` or `@SendToUser` can send notifications to matching sessions. This is a good option for personalized server pushes, but user destinations only route to active sessions; if notifications must persist while a user is offline, store them durably in a database or broker and let clients query them later.

STOMP requires securing both the HTTP handshake and message destinations. Use Spring Security to authenticate sessions, restrict who may `SEND` or `SUBSCRIBE` to which destinations, check user/tenant permissions, and protect broker relay credentials. Do not treat destination names as an authorization mechanism.

### 4.5. Limitations to consider

- WebSocket is a long-lived connection; proxies, load balancers, mobile networks, or browser sleep can drop connections. Heartbeats, reconnects, and subscription restoration are required.
- The simple broker keeps state in memory; node restarts lose subscriptions and broker state.
- Topic broadcasts generally target active subscribers; offline delivery must be designed separately.
- Many sessions and subscribers incur connection, memory, and outbound fan-out costs.
- If updates occur only a few times per minute, HTTP polling or Server-Sent Events may be simpler than WebSocket.

## 5. RSocket: bidirectional communication and reactive streaming

### 5.1. When to choose RSocket?

RSocket fits when two sides need direct communication over a long-lived connection, have multiple concurrent active requests, or need to stream data with backpressure. It is useful for:

- Asynchronous service-to-service request-response.
- Servers streaming data according to consumer demand instead of pushing unboundedly.
- Both sides simultaneously sending and receiving command/event streams via Channel.
- Clients or servers needing to initiate requests; neither side is locked into strict client/server roles once the connection is established.
- Reactive applications wanting to propagate demand across network boundaries and limit buffering.

RSocket is an application protocol running over TCP, WebSocket, or other byte-stream transports. It supports multiplexing and duplex interactions over a single connection. Core interaction models:

| Interaction | Communication direction | Spring/Reactor representation | Example |
| --- | --- | --- | --- |
| Request-Response | One request, one response | `Mono<T>` | Fetch current quote info |
| Request-Stream | One request, multiple responses | `Flux<T>` | Stream prices or telemetry |
| Channel | Bidirectional request and response streams | `Flux` on both sides | Bidirectional real-time state exchange |
| Fire-and-Forget | Send a message without waiting for a business response | `Mono<Void>` on send | Send signals needing no direct result |

Reactive Streams semantics let the requester send demand (`request(n)`) so the responder does not emit more items than the consumer can accept. This is backpressure across a network boundary, unlike simply growing a queue buffer on one side.

### 5.2. Spring RSocket responder

Spring supports annotated responders via `@MessageMapping` and `@ConnectMapping`. `@MessageMapping` handles individual requests; `@ConnectMapping` handles connection-level events such as setup/metadata pushes.

```java
@Controller
public class QuoteRSocketController {

    private final QuoteService quoteService;

    public QuoteRSocketController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.latest")
    public Mono<Quote> latest(QuoteRequest request) {
        return quoteService.latest(request);
    }

    @MessageMapping("quotes.stream")
    public Flux<Quote> stream(QuoteRequest request) {
        return quoteService.stream(request);
    }
}
```

### 5.3. Spring RSocket requester

`RSocketRequester` is a fluent API to send object data/metadata and receive object responses:

```java
RSocketRequester requester = RSocketRequester.builder()
        .tcp("quotes.internal", 7000);

Mono<Quote> latest = requester.route("quotes.latest")
        .data(new QuoteRequest("VN-INDEX"))
        .retrieveMono(Quote.class);

Flux<Quote> stream = requester.route("quotes.stream")
        .data(new QuoteRequest("VN-INDEX"))
        .retrieveFlux(Quote.class);
```

This is an illustrative snippet; `Quote`, `QuoteRequest`, and `QuoteService` are application-defined. `RSocketRequester` can be created before the connection is actually established; the connection is used when a request is executed. In Spring Boot, `spring-boot-starter-rsocket` provides auto-configuration for the requester builder, strategies, and server handler according to transport settings.

### 5.4. What RSocket does not provide out of the box

RSocket is not a message broker. The protocol provides connections, request streams, backpressure, keepalive, and session resumption, but does not automatically create a durable queue storing business messages while a responder is offline. If messages must survive restarts, retention, dead-lettering, competing consumers, or fan-out to multiple independent subscribers, use a broker such as JMS or an event platform; RSocket can complement it as a real-time API between services and clients.

Session resumption helps continue an RSocket session after an interruption if both sides configure and maintain the required state. It does not replace business event persistence or idempotency. Fire-and-Forget is also not a business acknowledgement; if the caller needs to know processing outcomes, use Request-Response or a dedicated acknowledgement mechanism.

RSocket requires both client and server to support the protocol and codecs, plus configuring authentication/authorization, timeouts, reconnect/resume, and observability. Browsers can use RSocket over WebSocket with a compatible client library, though STOMP typically has a more common ecosystem and programming model for web messaging.

## 6. Deep comparison by operational requirements

| Criterion | JMS | STOMP over WebSocket | RSocket |
| --- | --- | --- | --- |
| Primary peers | Backend apps, workers, enterprise systems | Browser/mobile sessions and server push | Reactive services, clients, and server endpoints |
| Interaction style | Queue, topic, request/reply | Send, subscribe, publish, user destinations | Request-Response, Stream, Channel, Fire-and-Forget |
| Core infrastructure | JMS provider/broker | WebSocket server; optionally a STOMP broker | RSocket server/connection; no broker needed by default |
| Durable/offline | Possible, depending on persistence, delivery mode, subscriptions, and broker policy | Not built in; depends on broker/client subscription configuration | No durable work queue by default |
| Fan-out | Topics/subscriptions | Broker topics and session subscriptions | Must design interaction/service fan-out; not broker pub/sub by default |
| Backpressure | Usually via provider consumer flow control/prefetch | STOMP broker/client-specific flow control; no Reactive Streams demand across protocol by default | Reactive Streams backpressure is a protocol feature |
| Connections | Usually broker connections managed by client/container | Long-lived WebSocket connection per client session | Long-lived, multiplexed connection |
| Request/reply | Possible via reply-to/correlation; usually needs timeouts and reply destination management | Possible via application conventions and destinations | Native Request-Response interaction |
| Browser support | Not normally a direct choice for browsers | Very well suited to browsers over WebSocket | Possible over WebSocket with a compatible client |
| Cluster/scaling | Scale broker/consumers per provider | Scale WebSocket nodes and external broker relay | Scale connection endpoints; separate service discovery/load balancing |
| Operations | Broker persistence, queue depth, consumers, DLQ, transactions | Sessions, subscriptions, heartbeats, broker relay, outbound fan-out | Connections, keepalive, leases, stream demand, resume, timeouts |

No option wins every row. JMS is typically optimal for decoupling and broker-managed work; STOMP for live client messaging; RSocket for reactive interactions between two endpoints.

## 7. Technology selection process

Answer these questions in order:

1. **Can the receiver be offline when a message is sent?** If it must be stored and delivered later, start from JMS or a broker with durable semantics. If only online sessions need updates, STOMP may fit.
2. **Do browsers/mobile apps need subscription-based pushes?** If yes, STOMP over WebSocket is usually the natural choice.
3. **Are bidirectional streams and end-to-end backpressure required?** If yes, evaluate RSocket.
4. **Are queues/topics, competing consumers, redelivery, DLQs, or broker transactions needed?** If yes, JMS/providers or broker messaging is more suitable.
5. **Is a single result per request, multiple streamed responses, or bidirectional streaming needed?** Request-response/stream/channel is a clear strength of RSocket; JMS/STOMP can implement request/reply but require managing correlation and timeouts per contract.
6. **What brokers does the system already run?** If the enterprise already operates a JMS provider, leveraging it can reduce operational cost. If RabbitMQ and browser clients are present, STOMP broker relay may fit. If the backend is already reactive and needs streaming, RSocket is worth evaluating.
7. **Can the team operate long-lived connections, sessions, and reconnects?** STOMP/RSocket require connection lifecycle management. JMS requires operating brokers, persistence, queues, DLQs, and consumer health.
8. **Is communication traversing public networks/proxies?** WebSocket/RSocket over WebSocket may hit proxy idle timeouts; JMS broker connections are usually meant for controlled service-to-service networks. Test real infrastructure before finalizing.

## 8. Common hybrid architectures

### 8.1. JMS for backend, STOMP for UI

This is a common pattern when business events must be processed durably while users also need real-time updates:

```text
Order Service
    |
    v
JMS queue/topic ----> Billing / Inventory / Audit consumers
    |
    v
Notification Service
    |
    v
STOMP broker relay
    |
    v
Browser sessions: /user/queue/notifications
```

JMS holds business events according to broker policies; Notification Service turns a processed outcome into a message suited for online clients. If a browser is offline, the notification service can store notifications in a database so the client can retrieve them later.

### 8.2. RSocket for queries/streams, JMS for business events

A service can use RSocket to query state or receive real-time streams from another service; when a business event must be durably stored and fanned out to multiple consumers, the service publishes the event via JMS. This gives real-time interactions and durable event distribution separate contracts.

### 8.3. STOMP for UI, HTTP for CRUD operations

There is no need to move every web interaction onto STOMP. HTTP/REST suits form submissions, resource queries, and standard CRUD; STOMP is for pushes, presence, chat, and live updates. Choose protocols per flow rather than forcing one protocol across the whole application.

## 9. Common wrong choices

- Using the STOMP simple broker as a durable queue for critical business commands. The simple broker is a simple in-memory broker; message/session state lacks the durability of a dedicated broker.
- Using RSocket Fire-and-Forget and treating a successful send as meaning the consumer committed data. Fire-and-Forget returns no business acknowledgement.
- Using JMS directly from browsers without a gateway/protocol adapter. Browsers usually need WebSocket/STOMP or HTTP APIs.
- Choosing RSocket solely for high speed without needing streaming/backpressure or duplex communication. HTTP may be easier to operate.
- Treating a STOMP topic like a durable offline inbox. Online subscriptions and durable subscriptions have different semantics; verify broker/client support.
- Assuming JMS persistent messages guarantee exactly-once business processing. Redelivery/duplicates can still happen; consumers need idempotency.
- Treating WebSocket, STOMP, and the broker as the same component. WebSocket is the transport; STOMP is the sub-protocol; the broker manages destinations/subscriptions.
- Picking a technology without measuring reconnects, timeouts, queue backlogs, consumer lag, connection counts, fan-out, and failure recovery.

## 10. Pre-deployment checklist

- Clearly document producers, consumers, and who owns a message after sending.
- Choose interaction contracts: command, event, request/reply, stream, or notification.
- Define message schemas, versioning, content types, correlation IDs, and idempotency keys.
- Define persistence, TTL, acknowledgements, redelivery, retries, dead-lettering, and offline behavior.
- Define ordering guarantees needed: global, per queue, per key, per user session, or per stream.
- Configure authentication, authorization, broker ACLs, TLS, and credential protection.
- Test broker restarts, consumer crashes, client disconnects, timeouts, duplicate deliveries, and schema incompatibilities.
- Monitor queue depth, oldest-message age, consumer lag, delivery failures, redeliveries, connection counts, subscription counts, and latency.
- Set limits on concurrency, prefetch/buffers, stream demand, connection idle timeouts, and retry backoff.
- Maintain operational runbooks for brokers, relays, WebSocket sessions, or RSocket connections accordingly.

## 11. Takeaways

- **JMS:** backend-to-backend via a broker; choose when queues/topics, decoupling, persistence, transactions/acknowledgements, and worker processing per provider capabilities are needed.
- **STOMP:** server-to-browser/mobile over WebSocket; choose when destinations, subscriptions, broadcasts, user destinations, and live UI updates are needed.
- **RSocket:** service/client-to-service with bidirectional interactions; choose when request-response, streams, channels, and Reactive Streams backpressure are needed.
- JMS durability depends on provider and configuration; STOMP broker/client semantics depend on the broker; RSocket is not a durable broker on its own.
- Multiple technologies can be combined: JMS stores business events, STOMP updates clients, RSocket provides real-time queries or streams.
- Choose based on communication peers, message semantics, and operational capability, not latency alone.

## References

- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference — Receiving JMS Messages and Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework Reference — STOMP Messaging](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework Reference — Benefits of STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/benefits.html)
- [Spring Framework Reference — Sending STOMP Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot Reference — RSocket Support](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html)
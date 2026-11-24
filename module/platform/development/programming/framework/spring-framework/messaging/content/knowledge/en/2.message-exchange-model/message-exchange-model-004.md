# Publishing and Subscribing to Messages in Spring Framework

## 1. Purpose and the Publish-Subscribe Model

Publish-subscribe is an exchange model in which one party publishes a message to a channel or destination, and interested parties subscribe beforehand to receive that message. The publisher does not need to know how many subscribers exist, which ones are running, or where they are deployed.

For example, when an order is created, the system publishes an `order.created` event. Subscribers may write audit logs, update metrics, send notifications, and synchronize data. Each subscriber processes the same event according to its own responsibility.

This model fits when:
- One event needs to trigger multiple independent tasks.
- You want to reduce direct coupling between publishing and receiving components.
- Subscribers can be added or removed without modifying publisher logic.
- The message signifies announcing that something has happened, rather than asking a single consumer to perform a job.

Two exchange styles should be distinguished:

| Characteristic | Publish-subscribe | Point-to-point |
| --- | --- | --- |
| Distribution | One message is delivered to every matching subscriber | One message is delivered to one consumer in a group |
| Goal | Notify multiple components | Share work among consumers processing together |
| Example | A new order is sent to audit, analytics, and notification | An email-sending task is picked up by one worker |
| Common risks | A failing or slow subscriber affects the publishing flow depending on dispatch mode | Competing consumers, load distribution, and reprocessing |

Publish-subscribe does not automatically imply durable storage. An in-memory channel can broadcast messages to multiple currently registered subscribers, but does not retain messages for offline subscribers to receive later.

## 2. Building Blocks of Spring Messaging

Spring Framework provides the `spring-messaging` module with abstractions to decouple publishers from receivers:

- **`Message<T>`**: a message consisting of a typed payload and a set of metadata.
- **`MessageHeaders`**: holds metadata such as ID, timestamp, content type, correlation ID, destination, or custom headers. The headers of a created message are immutable; use a builder or accessor to create a new message rather than mutating directly.
- **`MessageChannel`**: the message-sending contract. Publishers call `send(message)` without calling handlers directly.
- **`SubscribableChannel`**: extends `MessageChannel`, allowing `MessageHandler` instances to subscribe and unsubscribe.
- **`MessageHandler`**: the contract for processing a message via `handleMessage(message)`.
- **`ExecutorSubscribableChannel`**: implements `SubscribableChannel` and delivers messages to each subscriber. The no-argument constructor runs handlers on the thread calling `send`; the constructor accepting an `Executor` delegates dispatching to that executor.
- **`MessageBuilder`**: creates messages and sets headers safely.

Example of creating a message:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-42")
    .setHeader("eventType", "order.created")
    .setHeader("correlationId", "request-91")
    .build();
~~~

The payload describes the business data; headers describe the transport and routing context. Use an immutable payload or treat the payload as read-only, because multiple subscribers may receive the same message.

Note on class names: `ExecutorSubscribableChannel` belongs to Spring Framework, package `org.springframework.messaging.support`. `PublishSubscribeChannel` and `DirectChannel` are often mentioned in Spring Integration documentation: `PublishSubscribeChannel` broadcasts to registered handlers, whereas `DirectChannel` uses point-to-point delivery. To use Spring Integration classes, the project must include the `spring-integration-core` module; do not confuse them with classes in `spring-messaging`.

## 3. Publish and Receive Flow Within an Application

The processing flow in a publish-subscribe channel can be visualized as follows:

~~~mermaid
flowchart LR
    P[Publisher] --> M[Message: payload + headers]
    M --> C[SubscribableChannel]
    C --> A[Subscriber: audit]
    C --> B[Subscriber: analytics]
    C --> N[Subscriber: notification]
~~~

1. The publisher creates a message with the payload and required headers.
2. The publisher calls `channel.send(message)`.
3. The channel finds registered handlers and dispatches the message according to the implementation's policy.
4. Each subscriber processes the message in its handler.
5. A subscriber may write data, call another service, or publish a new message; do not assume another subscriber has finished before the current handler runs.

`subscribe(handler)` returns `true` when the handler is registered and `false` if that handler was already registered. `unsubscribe(handler)` unregisters the handler. Keep the exact handler instance if you need to unsubscribe later.

## 4. Runnable Example with ExecutorSubscribableChannel

The example below uses Java 17+ and Spring Framework 7.0.10. The channel is created using the no-argument constructor, so both handlers run synchronously on the thread calling `send`. This is a standalone example that does not require bootstrapping a Spring `ApplicationContext`.

Directory structure:

~~~text
spring-messaging-pubsub/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── PublishSubscribeDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-messaging-pubsub</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>PublishSubscribeDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/PublishSubscribeDemo.java**

~~~java
import java.util.Map;
import java.util.TreeMap;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class PublishSubscribeDemo {

    public static void main(String[] args) {
        ExecutorSubscribableChannel channel = new ExecutorSubscribableChannel();
        Map<String, String> received = new TreeMap<>();

        channel.subscribe(message ->
            received.put("audit", String.valueOf(message.getPayload()))
        );

        channel.subscribe(message ->
            received.put("metrics",
                String.valueOf(message.getHeaders().get("eventType")))
        );

        Message<String> event = MessageBuilder
            .withPayload("order-42")
            .setHeader("eventType", "order.created")
            .build();

        boolean sent = channel.send(event);

        received.forEach((subscriber, value) ->
            System.out.println(subscriber + ": " + value)
        );
        System.out.println("sent=" + sent);
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

Output:

~~~text
audit: order-42
metrics: order.created
sent=true
~~~

Both subscribers receive the same payload and can read the `eventType` header. `TreeMap` is only used to print results in a deterministic order; it does not determine the channel's dispatch order. The value `sent=true` indicates that the send was accepted by the channel under its current dispatch mechanism, not proof that the message was durably persisted in an external broker.

## 5. Running Subscribers with an Executor

When handlers perform time-consuming work, you can pass an `Executor` to `ExecutorSubscribableChannel`. In a Spring application, you can manage the thread pool using `ThreadPoolTaskExecutor`:

~~~java
@Configuration
public class MessagingConfig {

    @Bean
    public ThreadPoolTaskExecutor messagingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("messaging-");
        return executor;
    }

    @Bean
    public MessageChannel orderEvents(ThreadPoolTaskExecutor messagingExecutor) {
        return new ExecutorSubscribableChannel(messagingExecutor);
    }
}
~~~

In that case, handlers are dispatched through the executor. Note the following:

- `send` may return once the task has been submitted to the executor, before all handlers finish.
- Exceptions thrown during asynchronous processing may not propagate back to the thread calling `send`; configure appropriate error reporting, logging, and monitoring.
- Transactions, security context, MDC, and `ThreadLocal` values from the sending thread are not automatically transferred to the processing thread.
- Configure queue bounds, thread counts, rejection policies, and shutdown timeouts. An unbounded queue can cause memory to grow continuously when subscribers process slowly.
- Do not rely on completion order across subscribers when running concurrently. If business logic requires ordering, design appropriate partitioning, locking, or serialization.

## 6. Publish-Subscribe with Spring Application Events

If both publisher and subscribers are beans within the same `ApplicationContext`, Spring Application Events are a leaner option when only internal event notification is needed. This mechanism uses `ApplicationEventPublisher` and `@EventListener`, without requiring a `MessageChannel`.

~~~java
public record StockChanged(long productId, int quantity) {
}

@Component
public class StockService {

    private final ApplicationEventPublisher events;

    public StockService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void publishStockChange(long productId, int quantity) {
        events.publishEvent(new StockChanged(productId, quantity));
    }
}

@Component
public class StockAuditListener {

    @EventListener
    public void onStockChanged(StockChanged event) {
        System.out.println(
            "Stock changed: product=" + event.productId()
                + ", quantity=" + event.quantity()
        );
    }
}
~~~

Spring automatically discovers listeners matching the event type. By default, listeners are invoked synchronously on the event-publishing thread; `publishEvent` waits for listeners to complete. You can use `@Async` with `@EnableAsync` or configure `ApplicationEventMulticaster` with an executor for asynchronous processing. When switching to another thread, errors and thread context are no longer propagated back to the publisher synchronously.

If a listener needs to read committed database data, you can use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` to process after the transaction commits. Application Events serve only communication within the application context; they do not automatically send events to other processes or servers and do not replace a persistent message broker.

## 7. Publish-Subscribe for Clients with STOMP and WebSocket

When you need to send notifications from the server to multiple connected browsers or devices, Spring WebSocket supports STOMP. STOMP defines frames such as `CONNECT`, `SUBSCRIBE`, `SEND`, and `MESSAGE`; the destination indicates where a message is sent.

### 7.1. Endpoint and Broker Configuration

~~~java
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
~~~

- Clients establish a WebSocket connection at the `/ws` endpoint.
- Destinations starting with `/app` are routed to `@MessageMapping` methods.
- Destinations starting with `/topic` or `/queue` are forwarded to the configured broker.
- `/topic` is conventionally used for publish-subscribe; `/queue` is conventionally used for point-to-point. In STOMP, destination semantics are determined by the broker; these two prefixes carry no special built-in meaning in the simple broker beyond the configured routing rules.

### 7.2. Receiving Requests and Broadcasting Results to a Topic

~~~java
public record NoticeCommand(String text) {
}

public record Notice(String text) {
}

@Controller
public class NoticeController {

    @MessageMapping("/notices")
    @SendTo("/topic/notices")
    public Notice publish(NoticeCommand command) {
        return new Notice(command.text());
    }
}
~~~

A client sends a STOMP frame to `/app/notices`. Spring routes the frame to `NoticeController.publish`; the returned value is sent to `/topic/notices`. The broker distributes the message to clients subscribed to that destination. Configure an appropriate message converter if payloads are exchanged as JSON.

Example client-side frames (`^@` denotes the STOMP frame null-byte terminator):

~~~text
SUBSCRIBE
id:notice-sub-1
destination:/topic/notices

^@

SEND
destination:/app/notices
content-type:application/json

{"text":"Maintenance at 22:00"}
^@
~~~

### 7.3. Publishing from a Service or Any Component

A client does not need to send a message first. A service, scheduled task, or HTTP controller can also publish to the broker using `SimpMessagingTemplate`:

~~~java
@Component
public class NoticePublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public NoticePublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(Notice notice) {
        messagingTemplate.convertAndSend("/topic/notices", notice);
    }
}
~~~

`convertAndSend` converts the payload into a message and sends it to the destination. Use `convertAndSendToUser(user, destination, payload)` or `@SendToUser` when sending privately to an authenticated user; do not take the recipient identity from an untrusted user ID in the payload.

### 7.4. Simple Broker and Broker Relay

`enableSimpleBroker` enables Spring's built-in broker. This broker keeps subscriptions in memory and broadcasts to connected clients with matching destinations. It is useful for learning, development, and simple deployments, but only supports a subset of STOMP commands, does not support full protocol ACK/receipts, and is not suitable for clustering.

When a dedicated broker or multiple application instances are needed, configure a STOMP broker relay, for example:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue");
~~~

The relay opens TCP connections to an external broker (such as RabbitMQ or ActiveMQ), forwards messages to the broker, and delivers incoming messages to WebSocket clients. You must configure the host, port, credentials, access permissions, and broker operational policies. The relay scales broadcast capability, while durability, acknowledgements, retries, and retention still depend on the actual broker configuration.

Common STOMP flow:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant I as clientInboundChannel
    participant H as @MessageMapping
    participant B as Broker
    participant O as clientOutboundChannel
    C->>I: SUBSCRIBE /topic/notices
    I->>B: Register subscription
    C->>I: SEND /app/notices
    I->>H: Route to controller
    H->>B: Send result via brokerChannel
    B->>O: Broadcast to matching subscribers
    O->>C: STOMP MESSAGE
~~~

## 8. Choosing the Right Mechanism

| Mechanism | Scope | When to Use | Main Limitations |
| --- | --- | --- | --- |
| `ExecutorSubscribableChannel` | Within one application | Multiple handlers need to receive messages via Spring Messaging abstractions | No built-in broker or durable storage by default |
| `ApplicationEventPublisher` + `@EventListener` | Within one `ApplicationContext` | Notifying business changes between beans | Does not send messages over the network; synchronous by default |
| STOMP + simple broker | Server to connected WebSocket clients | Dashboards, chat, or real-time notifications at simple scale | In-memory subscriptions; no clustering and lacks full broker features |
| STOMP broker relay | Server, external broker, and WebSocket clients | Dedicated broker needed, multiple instances, or advanced broker features | Requires operating a broker and configuring connectivity and security |
| Spring Integration `PublishSubscribeChannel` | In-application integration flows | Building integration flows with channels, routers, transformers, and handlers | Requires adding Spring Integration |

You do not need to set up a broker for every case. If beans in the same application only need to notify each other, Application Events are usually sufficient. If you need message channel and handler abstractions, use Spring Messaging. If you need networked clients or distribution across multiple processes, use STOMP with an appropriate broker.

## 9. Reliability, Transactions, and Security

### 9.1. Reliability and Error Handling

- Clearly define what counts as success: the channel accepting the message, the handler completing, or the broker confirming message storage are different levels.
- Design idempotent subscribers. If the broker can redeliver a message, the same event must not repeat business side effects.
- Assign event IDs and correlation IDs for tracing, reconciliation, and duplicate detection.
- With external brokers, configure acknowledgements, retries, dead-letter queues, and retention periods according to business requirements and broker capabilities.
- If you must update the database and publish an event as one consistent operation, consider the Transactional Outbox pattern. Write the business change and an outbox record in the same transaction; a separate process relays the outbox to the broker.
- Do not treat the simple broker or an in-memory channel as a durable queue. When the application stops, subscriptions or unprocessed messages can be lost.

### 9.2. Transactions and Processing Order

Synchronous Application Event listeners run by default on the event-publishing thread and can participate in the current transaction context. If a listener must read committed data, use `@TransactionalEventListener` with phase `AFTER_COMMIT`. When processing asynchronously, the publisher's transaction does not automatically extend to the new thread.

With multiple subscribers running in parallel, completion order is not guaranteed. If a business process needs sequential order per order or account, define a partitioning key and serialization mechanism; do not rely on thread scheduler order.

### 9.3. Security

- Authenticate WebSocket connections and separately authorize STOMP `SEND` and `SUBSCRIBE` operations.
- Only allow clients to subscribe to destinations they are authorized to read; do not rely on destination names being hard to guess.
- Inspect and validate payloads on the server, even when the client already validates them.
- Use the authenticated session's `Principal` to route private messages to users.
- Do not write access tokens, passwords, personal data, or sensitive payloads into message logs.
- With a broker relay, restrict the broker account's permissions by destination and environment.

## 10. Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No subscriber receives the message | Wrong destination, handler not subscribed, or broker not running | Check subscription registration, destination, and broker status |
| Client connects but does not see broadcasts | Client has not sent `SUBSCRIBE`, wrong prefix, or lacks read permission | Check the `SUBSCRIBE` frame, broker config, and security rules |
| Controller is not invoked | Client sends to `/topic` instead of an application prefix like `/app` | Send to a destination matching `@MessageMapping` |
| One listener slows down the publisher | Synchronous handler runs on the sending thread | Use a bounded executor or offload long-running work |
| Send succeeds but subscriber processing fails | Asynchronous dispatch only confirms submitting the task to the executor | Monitor errors on the processing thread and configure an error handler |
| Messages vanish after restart | Using an in-memory channel or simple broker | Use a persistent broker and configure durability appropriately |
| One event causes duplicate side effects | Retry or redelivery while consumer is not idempotent | Use event IDs and persist completion markers |
| Broadcasts do not cross instances | Each instance is running its own simple broker | Use an external broker via a broker relay |

## 11. Implementation Checklist

- [ ] Clearly determine whether the message is a fan-out notification or a point-to-point job.
- [ ] Choose Application Events, Spring Messaging, or STOMP based on exchange scope.
- [ ] Define a typed payload, required headers, event ID, and correlation ID.
- [ ] Choose synchronous or asynchronous execution; configure a bounded executor if needed.
- [ ] Specify how errors, retries, duplicates, and ordering are handled.
- [ ] If both a database and broker are involved, consider Transactional Outbox or publishing events after commit.
- [ ] Secure destinations and authorize send/subscribe permissions.
- [ ] Test scenarios with no subscribers, slow subscribers, broker disconnects, and application restarts.
- [ ] Monitor message volume, latency, handler errors, and broker health.

## 12. References

- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework API — ExecutorSubscribableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Integration — Channel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

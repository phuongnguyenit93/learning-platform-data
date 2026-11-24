# Scope of spring-messaging, spring-jms, and spring-websocket

These three modules all serve message exchange in Spring applications, yet each addresses a distinct layer:

- **spring-messaging** provides the message model and shared processing contracts so producers, channels, and consumers remain loosely coupled.
- **spring-jms** connects a Spring application to a system implementing Jakarta Messaging (JMS), such as a JMS-capable message broker.
- **spring-websocket** provides WebSocket communication on the Servlet stack; when using STOMP, it works together with spring-messaging to route messages between browsers and the application.

Understanding these boundaries helps you choose the right APIs, dependencies, and delivery guarantees. All three are application-side integration components; they do not by themselves turn your application into a message broker with durable storage.

## 1. What Problem Does Messaging Solve?

In the HTTP request-response model, a client sends a request to an endpoint and usually waits for a response in the same interaction. This model fits operations needing immediate results, such as reading information or updating a resource.

Messaging decouples sender from receiver via a message. The sender creates a message and hands it to a destination; the receiver processes it when able. Depending on the technology, messages may be stored in a broker, distributed to multiple subscribers, or transmitted over an open connection.

A message typically requires at least two parts:

- **Payload:** business data, such as an order ID or event details.
- **Headers:** metadata such as event type, correlation ID, content type, timestamp, or routing information.

Messaging is valuable when components need less temporal coupling, asynchronous processing, event distribution to multiple parties, or continuous UI updates. However, messaging also introduces concerns that must be explicitly designed: processing order, retries, duplicates, timeouts, acknowledgements, security, and observability.

## 2. Quick Comparison of the Three Modules

| Module | Primary Responsibility | Representative APIs | External Components |
|---|---|---|---|
| spring-messaging | Message model, channels, handlers, converters, and messaging templates | Message, MessageChannel, MessageHandler, MessageBuilder, MessageConverter | No broker required if using abstractions only within the application |
| spring-jms | Integrating an application with Jakarta Messaging | JmsTemplate, JmsMessagingTemplate, @JmsListener, JmsTransactionManager | JMS ConnectionFactory and a JMS provider/broker |
| spring-websocket | WebSocket connectivity, SockJS, and messaging over STOMP | WebSocketHandler, WebSocketConfigurer, @EnableWebSocketMessageBroker, @MessageMapping, SimpMessagingTemplate | WebSocket client; an external STOMP broker is optional when using broker relay |

You can remember the split through three questions:

1. How does the application represent and pass a message? That is the focus of **spring-messaging**.
2. How does the application send or receive messages through a JMS provider? That is the focus of **spring-jms**.
3. How does the browser maintain a bidirectional connection and exchange messages in real time? That is the focus of **spring-websocket**.

## 3. spring-messaging: The Shared Message Model

### 3.1. Core Abstractions

The main package is org.springframework.messaging. Key abstractions include:

- **Message<T>:** represents a message with a payload of type T and a set of headers.
- **MessageHeaders:** metadata map attached to the message.
- **MessageChannel:** contract for sending a message so the sender need not know which specific handler will process it.
- **MessageHandler:** contract for receiving and handling a message.
- **SubscribableChannel:** channel managing handlers subscribed to receive messages.
- **PollableChannel:** channel allowing consumers to actively fetch messages via polling.
- **MessageBuilder:** builds messages and sets headers.
- **MessageConverter:** converts payloads between wire/transport representations and the Java types handlers expect.
- **GenericMessagingTemplate** (in `org.springframework.messaging.core`): implementation of messaging operations that resolves destination names to a `MessageChannel` for send, receive, and request-reply.

A conceptual processing flow:

~~~text
Producer
   |
   | create Message(payload, headers)
   v
MessageChannel
   |
   v
MessageHandler
   |
   v
Business logic
~~~

The channel creates a boundary between producer and consumer. The producer only needs to know where to send; the handler focuses on processing. That makes it possible to change how messages are distributed or how handlers register with minimal impact on business logic.

### 3.2. Creating a Message in Java

The example below illustrates payloads and headers. It is a small program requiring spring-messaging on the classpath; it does not need a broker connection.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessageModelDemo {

    public static void main(String[] args) {
        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .setHeader("eventType", "OrderCreated")
                .build();

        System.out.println(message.getPayload());
        System.out.println(message.getHeaders().get("eventType"));
    }
}
~~~

Output:

~~~text
order-42
OrderCreated
~~~

The example shows that a message holds more than just business data. Headers allow adding metadata without stuffing routing or correlation fields into the payload. When designing contracts, keep business data in the payload and reserve headers for transport and processing metadata.

### 3.3. Conversion, Handlers, and Annotations

Messages can arrive from many sources in different formats. MessageConverter handles converting payloads, for example from JSON or text into a Java type. Converter selection should match the content type and contract agreed between producer and consumer.

Method-handling APIs also provide annotations such as:

- **@MessageMapping:** maps messages to methods based on destination or routing criteria.
- **@Payload:** specifies the parameter bound from the payload.
- **@Header** and **@Headers:** bind a single header or all headers.
- **@SendTo:** specifies the destination receiving the handler's return value in messaging models supporting this annotation.

These annotations do not create a broker on their own. They are method-mapping and invocation mechanisms once a matching messaging infrastructure is configured.

### 3.4. Boundaries of spring-messaging

spring-messaging provides abstractions and communication helpers, but the module itself does not guarantee:

- that messages are stored durably after the application stops;
- that messages are delivered exactly once;
- that consumers always receive messages when connections drop;
- global ordering across multiple producers or consumers;
- retries, dead-letter queues, or retention per business policies.

Those guarantees depend on the transport, broker, configuration, and application logic. Merely constructing a Message and calling an internal channel does not mean the message entered a distributed queueing system.

## 4. spring-jms: Integrating with Jakarta Messaging

### 4.1. Where Does JMS Fit in the Architecture?

JMS is the standard Java API for messaging between applications or components. Spring provides support classes so business code does not have to repeat boilerplate for creating connections, sessions, producers, consumers, and handling JMS exceptions.

A Spring application using JMS needs a **ConnectionFactory** connected to a JMS provider. The provider handles managing destinations, delivering messages, and enforcing delivery policies. Spring Framework does not act as a replacement for that provider.

Two common destination types:

- **Queue:** point-to-point model; each message is processed by one consumer in a competing group per the provider's mechanism.
- **Topic:** publish-subscribe model; messages are distributed to subscriptions according to the provider's configuration.

Storage traits, durable subscriptions, redelivery, selectors, and resource limits depend on the JMS provider and deployment configuration.

### 4.2. Synchronous Send and Receive with JmsTemplate

JmsTemplate is the central API for synchronous send and receive operations. The template manages the lifecycle of required JMS resources, converts messages, and exposes convenience methods.

Example call from a Spring bean with an injected JmsTemplate:

~~~java
jmsTemplate.convertAndSend("orders", "order-42");
~~~

This call sends the payload to the destination named orders. For it to work, the application must configure a ConnectionFactory and an appropriate destination; naming a destination does not automatically guarantee the broker has created a physical queue or topic.

JmsTemplate also supports synchronous receive. Set an explicit receive timeout because receiving can block the calling thread while waiting for a message. Do not leave an ordinary HTTP request thread blocked indefinitely waiting for a message.

### 4.3. Asynchronous Receiving with @JmsListener

For asynchronous processing, Spring can register methods as listener endpoints:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders")
    public void handle(String payload) {
        System.out.println("Received order: " + payload);
    }
}
~~~

For the annotation to work in plain Spring Framework configuration, enable support with @EnableJms and provide a listener container factory along with a ConnectionFactory:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

These are illustrative configuration fragments, not a standalone application. ConnectionFactory must be supplied by the JMS provider or corresponding platform configuration. In Spring Boot, starters and auto-configuration can create part of this infrastructure once dependencies and connection properties are declared.

A listener container is responsible for receiving messages, managing threads, invoking listeners, coordinating sessions, and managing connection lifecycles. Two standard implementations are SimpleMessageListenerContainer and DefaultMessageListenerContainer; they differ in dynamic scaling and transaction participation. Choose based on environment, transaction manager, and operational requirements.

### 4.4. Conversion and Bridging with Spring Messaging

JMS has its own Jakarta Messaging message types. Spring provides MessageConverter to translate between JMS messages and Java objects. When a listener expects a specific payload type, the converter must know how to build that type from incoming messages.

JmsMessagingTemplate bridges JmsTemplate and the org.springframework.messaging.Message abstraction. This lets code use Spring's common message model when sending over JMS. It is an integration point between the two modules, not a mechanism that turns every internal MessageChannel into a JMS destination.

### 4.5. Transactions, Acknowledgements, and Reliability

JMS defines acknowledgement and transaction modes. Spring supports local transactions via JmsTransactionManager for a single ConnectionFactory. When distributed transactions across multiple resources are required, configure JTA and compatible XA resources; you cannot simply add @Transactional and assume atomicity across broker and database.

Several key operational principles:

1. **Do not assume AUTO_ACKNOWLEDGE is reliable enough.** Default acknowledgement settings can acknowledge a message even when business processing fails, depending on the listener container and provider.
2. **Design listeners to tolerate duplicate messages.** Brokers can redeliver on error or when a process stops at an awkward moment. Use a message ID or business key to enforce idempotency.
3. **Choose the right transaction scope.** A local JMS transaction does not automatically include database transactions. If multiple resources must coordinate, explicitly configure the transaction manager and XA support.
4. **Define intentional retry and error policies.** Specify retry limits, backoff, dead-letter destinations, and handling for invalid messages per provider capabilities.
5. **Monitor consumer lag and broker health.** A running listener that cannot keep up will still cause queues to grow continuously.

Do not claim a system has exactly-once behavior simply because transactions are enabled. In practice, you usually need an appropriate combination of transactions, idempotency, and recovery procedures.

## 5. spring-websocket: Bidirectional Client Communication

### 5.1. How Does WebSocket Differ from HTTP?

WebSocket starts with an HTTP handshake. The client sends a protocol upgrade request; if the server accepts, the TCP connection remains open so client and server can exchange data bidirectionally over that single connection.

HTTP typically routes per request using URL, method, and headers. WebSocket normally uses the URL only during connection setup; afterward, many messages travel over the same connection. WebSocket is a low-level transport protocol and does not define the business semantics of payloads. Client and server must agree on a format or adopt a sub-protocol such as STOMP.

WebSocket fits use cases requiring frequent low-latency updates, such as chat, live dashboards, collaboration, or trading status. For data that only needs refreshing every few minutes, polling or Server-Sent Events may be simpler.

### 5.2. Raw WebSocket API

If an application needs a custom protocol, Spring lets you register a WebSocketHandler and handle frames directly. Common APIs include WebSocketHandler, TextWebSocketHandler, WebSocketConfigurer, and @EnableWebSocket.

At this level, the application decides:

- payload structure and message classification;
- authentication rules, binding users to sessions, and authorization;
- how to broadcast or route to sessions;
- heartbeats, timeouts, reconnection, and closed-session cleanup;
- frame size limits and load control.

Raw WebSocket works well when full protocol control is needed or only a few simple message types are exchanged. In return, the application must design many conventions that a messaging sub-protocol would otherwise supply.

### 5.3. SockJS and Fallback Support

SockJS provides a WebSocket-like client-server model and can fall back to alternative transports when the environment does not support WebSocket. Fallback can be enabled on an endpoint with:

~~~java
registry.addEndpoint("/ws").withSockJS();
~~~

Fallback does not give every transport identical performance or operational traits. When deploying behind reverse proxies, load balancers, or cloud platforms, verify WebSocket Upgrade routing, long-lived connection timeouts, and sticky session configuration if required by the architecture.

### 5.4. STOMP over WebSocket

STOMP is a messaging sub-protocol. It defines frames such as CONNECT, SEND, SUBSCRIBE, MESSAGE, and DISCONNECT, along with destinations so client and server agree on how messages are sent, subscribed to, and distributed.

When using STOMP, spring-websocket provides the transport and broker messaging infrastructure; spring-messaging provides the Message, channel, handler, annotation, and template abstractions used across the processing flow.

Minimal configuration:

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

Controller receiving messages from clients:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

A STOMP client can execute the following flow:

1. Open a WebSocket connection to the `/ws` endpoint.
2. Send a SEND frame to destination `/app/chat.send`.
3. Spring routes the message to the method mapped by `@MessageMapping`.
4. The return value is sent to `/topic/chat`.
5. Clients subscribed (`SUBSCRIBE`) to `/topic/chat` receive the message distributed by the broker.

The prefixes `/app`, `/topic`, and `/queue` are routing conventions in the example configuration. They are not JMS destinations and do not create queues/topics in a JMS broker.

### 5.5. Simple Broker vs. External Broker Relay

Spring can run an in-memory simple broker inside the application. This is convenient for learning, prototyping, and small cases, yet lacks the full capabilities of a standalone broker with durable storage and cluster management.

When a dedicated broker is required, configure a STOMP broker relay to forward matching frames to an external STOMP broker. You must then manage connection addresses, credentials, heartbeats, connection limits, and broker failover/recovery.

Do not pick the simple broker merely because the app uses WebSocket and then expect features like durable subscriptions, replay, or dead-letter queues. Verify actual broker capabilities against real delivery requirements.

### 5.6. Sending Messages to Clients from the Server

SimpMessagingTemplate lets a service send messages to a STOMP destination, even when the message originates from another execution flow rather than an `@MessageMapping` method:

~~~java
simpMessagingTemplate.convertAndSend("/topic/orders", orderEvent);
~~~

This is useful for status updates or broadcasting notifications to many clients. For user-specific destinations, use the user destination mechanism and matching security configuration; never concatenate usernames into destination strings while bypassing access control.

### 5.7. WebSocket Security and Operations

Because WebSocket maintains long-lived connections, connection lifecycle and access control must be designed explicitly:

- Authenticate during handshake or via the STOMP authentication mechanism supported by your application.
- Check Origin headers and configure CORS for allowed clients.
- Authorize by destination and SEND/SUBSCRIBE operations; connecting successfully must not grant read access to every topic.
- Enforce limits on payload size, send rate, connection count, and idle duration.
- Handle reconnection, heartbeats, session closure, and re-syncing missed data after a client reconnects.
- Do not treat WebSocket as a storage layer. Disconnected clients can miss updates; if recovery is needed, persist state/events durably and provide a read/replay API.

## 6. How Do the Three Modules Work Together?

Their relationship can be pictured as follows:

~~~text
                         spring-messaging
                 Message / Channel / Handler
                    /                  \
                   /                    \
          spring-jms                 spring-websocket
       Jakarta JMS API              WebSocket + STOMP
              |                           |
       JMS ConnectionFactory          WebSocket session
              |                           |
       JMS provider/broker            Browser/client
~~~

spring-messaging is the shared abstraction layer. spring-jms maps send/receive operations over JMS; spring-websocket uses messaging abstractions when running STOMP. Both integration modules can coexist in one application, yet they do not automatically connect every JMS queue to every WebSocket topic.

Example of an application receiving events from JMS and broadcasting notifications to browsers:

~~~java
@Component
public class OrderEventBroadcaster {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventBroadcaster(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @JmsListener(destination = "orders.events")
    public void onOrderEvent(OrderEvent event) {
        messagingTemplate.convertAndSend("/topic/orders", event);
    }
}
~~~

In this example:

- The JMS provider delivers the message to the application's listener.
- The listener forwards the business payload to a STOMP destination.
- The WebSocket broker distributes the message to clients subscribed to that destination.

This is an application-written bridge. It does not create an atomic transaction between the JMS acknowledgement and the client receiving the WebSocket frame. If the listener succeeds while a client is offline, that client may miss the notification. For important data, persist business state first, emit the notification as an update signal, and let clients fetch state via an API or replay mechanism.

## 7. Choosing Modules by Need

| Need | Suitable Choice | Reason |
|---|---|---|
| Standardize payloads, headers, channels, and handlers in Spring code | spring-messaging | Provides the shared message model |
| Send async commands or events via queues/topics with a JMS provider | spring-jms | Includes templates, listener containers, converters, and JMS transaction support |
| Continuous bidirectional browser updates | spring-websocket | Maintains WebSocket sessions; can use STOMP for routing |
| Clients need publish-subscribe over WebSocket | spring-websocket + spring-messaging | STOMP uses messaging abstractions and broker routing |
| Rich multi-system integration, routing, transforms, split/aggregate, and adapters | Spring Integration | Dedicated extension project for Enterprise Integration Patterns |
| Integrating Kafka or AMQP/RabbitMQ | Spring for Apache Kafka or Spring AMQP | Uses dedicated integration modules for those brokers/protocols |

Not every application needs all three modules. Add dependencies only for capabilities you actually use; dependencies do not replace provider, broker, security, or operational configuration.

## 8. Project-Level Dependencies and Configuration

Spring Framework module coordinates:

~~~groovy
dependencies {
    implementation("org.springframework:spring-messaging")
    implementation("org.springframework:spring-jms")
    implementation("org.springframework:spring-websocket")
}
~~~

The snippet above assumes the project uses dependency management or a BOM to keep Spring Framework versions aligned. Without a BOM, declare compatible versions across Spring modules. Never mix arbitrary mismatched versions.

Beyond those dependencies:

- spring-jms requires the Jakarta JMS API and the provider's client library; you must declare a ConnectionFactory and broker connection settings.
- spring-websocket on the Servlet stack needs a compatible web runtime and endpoint configuration; a STOMP external broker relay requires a broker supporting STOMP.
- spring-messaging can be used standalone for abstractions and internal message handling; using abstractions does not mean you already have distributed transport.

In Spring Boot, starters bundle dependencies and auto-configure part of the infrastructure. Distinguish Spring Boot starters from the underlying Spring Framework library modules.

## 9. Common Misconceptions

**Confusing abstractions with transport.** Message and MessageChannel describe how the application represents and passes messages. They do not open connections to a JMS broker or browser by themselves.

**Confusing WebSocket with STOMP.** WebSocket is a bidirectional transport; STOMP is a messaging protocol that can run over WebSocket. Using raw WebSocket means the application must define payload structure and routing conventions itself.

**Thinking spring-jms includes a built-in broker.** spring-jms is an integration layer. The application still needs a JMS provider, ConnectionFactory, and valid destinations.

**Assuming STOMP queues and topics match JMS destinations.** They belong to two separate routing systems. Prefixes `/topic` or `/queue` in STOMP do not automatically map to JMS queues/topics.

**Assuming sending a message means the consumer processed it successfully.** Sending, broker receipt, listener execution, database commit, and client rendering are separate stages. You need correlation IDs, logs, metrics, and error handling to observe the entire flow.

**Ignoring duplicates and ordering.** Retries or reconnects can cause duplicate processing; multiple consumers can finish out of send order. Design idempotency and versioning/sequencing when business rules require it.

**Using WebSocket for data that requires persistence.** WebSocket works well for pushing updates to connected clients. History, final state, and replayability require a durable data store.

## 10. Checklist When Designing a Messaging Flow

1. Identify who sends, who receives, and whether the message represents a command or an event.
2. Define the payload, headers, schema version, and correlation ID.
3. Choose the transport: JMS for integration via a JMS provider; WebSocket/STOMP for real-time clients; internal abstractions when decoupling producers from handlers.
4. Define delivery semantics: acknowledgements, retries, timeouts, duplicates, ordering, and dead-letter handling.
5. Define transaction boundaries between broker and database; do not assume they are automatically atomic.
6. Design authentication, destination authorization, payload validation, and load limits.
7. Test normal paths as well as broker disconnects, listener errors, invalid payloads, client reconnects, and duplicate messages.
8. Add logs with correlation IDs, metrics for backlog/consumers/sessions, and alerts for sustained failures.

## 11. References

- [Spring Framework Reference — Messaging](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html)
- [Spring Framework Reference — WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework Reference — STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework 6.1 Javadoc — org.springframework.messaging](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/package-summary.html)
- [Spring Framework 6.1 Javadoc — org.springframework.jms](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/package-summary.html)

When reading documentation, make sure you select the Spring Framework version your project uses. Some APIs and configuration options may vary across release branches.
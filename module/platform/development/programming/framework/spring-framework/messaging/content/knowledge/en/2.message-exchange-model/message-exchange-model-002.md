# In-Memory and Networked Exchange in Spring Framework

## 1. The Big Picture

Messaging is how one component sends information to one or more other components through a message. The sender does not necessarily need to know the details of where the receiver is deployed or which thread it runs on. In Spring, three layers should be distinguished:

- **Message model:** **Message<T>** containing a payload and headers.
- **Application send/receive points:** **MessageChannel**, **SubscribableChannel**, **PollableChannel**, and **MessageHandler**.
- **Transport mechanism:** an in-JVM call, WebSocket/STOMP, JMS, or another broker/protocol.

A **Message<T>** object typically consists of:

- **Payload:** business data, such as **OrderCreated**, a string, or a DTO.
- **Headers:** metadata such as **id**, **timestamp**, **contentType**, **correlationId**, source information, or a routing key.

**MessageHeaders** is an immutable header structure once the message is created; that does not automatically make the payload immutable. If the payload is a mutable object and multiple threads access it concurrently, the application still needs to protect the data or make an appropriate copy.

**MessageChannel** defines where messages are sent via the **send** method. **SubscribableChannel** allows registering one or more **MessageHandler** instances; **PollableChannel** allows the receiver to actively call **receive**. These interfaces describe how exchange works inside the application; by themselves, they do not guarantee that data will travel over a network.

You can create a message with metadata using **MessageBuilder**:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-42")
    .setHeader("correlationId", "corr-001")
    .build();
~~~

## 2. In-Memory Exchange

In-memory exchange takes place within the same Java process. A producer calls a Spring API or sends to a channel; the listener/handler is invoked within that same JVM. No sockets, remote brokers, or payload serialization for network transmission are needed.

### 2.1. Application events

Spring provides **ApplicationEventPublisher** for one bean to publish events and **@EventListener** for another bean to listen:

~~~java
public record OrderCreated(String orderId) {}

@Component
class OrderAuditListener {
    @EventListener
    public void onOrderCreated(OrderCreated event) {
        System.out.println("Created: " + event.orderId());
    }
}

@Service
class OrderService {
    private final ApplicationEventPublisher events;

    OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void create(String orderId) {
        // Save the order here.
        events.publishEvent(new OrderCreated(orderId));
    }
}
~~~

By default, **SimpleApplicationEventMulticaster** invokes listeners synchronously on the event-publishing thread. Therefore, a slow listener can delay **create**; exceptions from a synchronous listener can also affect the event-publishing flow. You can configure an executor for the event multicaster or use **@Async** when asynchronous processing is genuinely needed. When using asynchrony, you must configure the executor, queue limits, exception handling, and task lifecycle.

Internal events are not a durable queue. If the process stops, unprocessed events are lost; Spring does not automatically persist events for replay after application startup. If an event depends on a transaction, consider **@TransactionalEventListener** with an appropriate phase, such as **AFTER_COMMIT**, so the listener runs only after the transaction commits. This adjusts when the listener is invoked, but does not by itself create an atomic delivery guarantee between the database and an external broker.

### 2.2. Message channels in the same JVM

Spring Messaging provides channel abstractions and implementations supporting in-process dispatch. For example, **ExecutorSubscribableChannel** delivers messages to registered handlers. With the default constructor, there is no separate executor so dispatch occurs synchronously; when an **Executor** is provided, handlers can be run on that executor.

The example below is a standalone Java 17+ program runnable with Maven:

**Project structure**

~~~text
in-memory-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          InMemoryMessagingDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>in-memory-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/InMemoryMessagingDemo.java**

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class InMemoryMessagingDemo {
    public static void main(String[] args) {
        ExecutorSubscribableChannel channel = new ExecutorSubscribableChannel();

        channel.subscribe(message -> {
            System.out.println("payload=" + message.getPayload());
            System.out.println(
                "correlationId=" + message.getHeaders().get("correlationId")
            );
        });

        Message<String> message = MessageBuilder
            .withPayload("order-42")
            .setHeader("correlationId", "demo-001")
            .build();

        if (!channel.send(message)) {
            throw new IllegalStateException("Message was not accepted");
        }
    }
}
~~~

Run from the **in-memory-demo** directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.InMemoryMessagingDemo
~~~

**stdout**

~~~text
payload=order-42
correlationId=demo-001
~~~

The example has only one subscriber and uses the default channel, so the output is printed immediately on the thread calling **send**. When an executor is configured, do not assume the handler has completed by the time **send** returns. The boolean value from **send** represents the send/acceptance result at the channel, not confirmation that consumer-side business logic has committed successfully.

### 2.3. Strengths and Limitations

**Strengths**

- Low latency and less overhead than network communication.
- Easy to debug and test because the producer, channel, and handler are in the same process.
- No need to deploy a broker or manage network connections.
- Events or channels can be used to reduce direct coupling between beans.

**Limitations**

- Only components within the same process participate directly; other instances do not automatically receive events or channel messages.
- No default persistence, no replay after restart, and no built-in dead-letter queue.
- Synchronous listeners can block the sending thread; an executor can overload if the send rate exceeds the processing rate.
- Because there is no network boundary, errors, timeouts, and security differ from inter-service communication.
- A shared payload on the heap can be mutated unexpectedly if multiple components hold the same reference.

If you need channels such as **DirectChannel**, **QueueChannel**, or **PublishSubscribeChannel**, those are typically implementations from **Spring Integration** (package **org.springframework.integration.channel**). Spring Framework Messaging provides the foundational abstractions; Spring Integration classes should not be confused with the core Spring Framework API.

## 3. Networked Exchange

Networked exchange occurs when the producer and consumer reside in different processes or on different machines, or when external clients connect to the application. Messages must traverse a transport/protocol such as WebSocket, STOMP, or JMS. Data usually needs to be converted into a transmittable format, such as JSON or a format supported by the broker.

The network introduces new failure boundaries: connections can drop, brokers can go down, requests can time out, and consumers can process duplicates. Therefore, timeouts, retries, acknowledgements, message identifiers, security, and error-message handling must be clearly defined.

### 3.1. WebSocket and STOMP

WebSocket establishes a long-lived two-way connection between client and server. WebSocket provides the transport; it does not by itself define a complete destination, subscription, or routing model for the application. STOMP adds frames and conventions such as **SEND**, **SUBSCRIBE**, and destinations. Spring WebSocket combines with Spring Messaging to route messages to controllers and brokers.

Minimal configuration example:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

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
class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}

public record ChatMessage(String sender, String text) {}
~~~

The client connects to the **/ws** endpoint, sends a STOMP **SEND** to **/app/chat.send**, and registers a **SUBSCRIBE** to **/topic/chat**. Spring strips the application prefix **/app** when matching **@MessageMapping**; the method's return value is sent to the destination in **@SendTo**.

The application can also actively push data using **SimpMessagingTemplate**:

~~~java
messagingTemplate.convertAndSend("/topic/orders", orderUpdate);
~~~

In the configuration above, **enableSimpleBroker** enables the built-in simple broker inside the application. Clients still communicate with the server over the network, but the broker handling subscriptions lives in the Spring process's memory. This is a lightweight option for simple applications or development environments; it does not provide a durable broker shared across multiple instances and only supports a subset of STOMP features.

When an external broker is needed, a relay can be configured:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("localhost")
        .setRelayPort(61613);
~~~

The relay forwards messages between Spring and a compatible STOMP broker, such as a broker configured with a STOMP endpoint. An external broker can provide scaling, persistence, acknowledgements, and distribution according to its own configuration. Credentials, TLS, destination authorization, heartbeats, and connection limits must be configured for production environments.

Spring Boot typically uses the **spring-boot-starter-websocket** dependency; plain Spring Framework applications need the corresponding modules such as **spring-websocket** and **spring-messaging**. The configuration example above assumes the application already has a Spring application context and the required MVC/WebSocket beans.

### 3.2. JMS and Brokers

JMS is a message-broker-oriented messaging API. Spring Framework provides JMS integration in the **spring-jms** module, including **JmsTemplate** for sending and **@JmsListener** for receiving:

~~~java
jmsTemplate.convertAndSend("orders.created", orderCreated);

@JmsListener(destination = "orders.created")
public void handle(OrderCreated event) {
    // Process the message.
}
~~~

The application needs a JMS **ConnectionFactory**, listener container configuration, and an appropriate JMS provider/broker. Converting objects to messages depends on a **MessageConverter**; when communicating between independent services, prefer an explicit schema/format such as JSON rather than relying on Java object serialization.

JMS defines the API and several delivery models; persistence, redelivery, acknowledgment, transactions, and dead-letter queues also depend on the provider and its configuration. You should not conclude that every **convertAndSend** call guarantees the message has been successfully processed by the consumer.

AMQP/RabbitMQ and Apache Kafka are typically integrated through separate Spring projects such as **Spring AMQP** and **Spring for Apache Kafka**. They have their own routing, partition, offset, acknowledgment, and operational models; not every class in those projects belongs to Spring Framework core.

## 4. Comparing the Two Models

| Criterion | In-Memory | Over the Network |
|---|---|---|
| Scope | Same JVM/process | Multiple processes, machines, or clients |
| Latency | Usually low | Additional serialization, network, and broker overhead |
| Dependencies | Beans, channels, or events in the application | Transport, protocol, broker, or remote service |
| Survival across restarts | None by default | Possible if the broker is configured for persistence |
| Horizontal scaling | Events are not automatically shared across instances | Can be distributed via a broker/cluster |
| Common failures | Slow listeners, full executors, in-process exceptions | Timeouts, dropped connections, broker failures, duplicate messages |
| Security | Mainly along application/JVM boundaries | Requires authentication, authorization, TLS, and network controls |
| Testing | Can be tested directly with unit tests | Usually requires integration testing with a transport/broker |

Do not equate **asynchronous** with **over the network**. An in-JVM channel can use an executor to run handlers asynchronously. Conversely, an HTTP call over the network can still be synchronous request-response from the caller's perspective. The two axes to evaluate separately are where the components live and how the processing flow is coordinated.

You should also distinguish **network transport** from a **persistent broker**. WebSocket to Spring's simple broker is networked communication between client and server, yet the broker state still resides in server memory. Conversely, a broker may be installed on the same machine for development yet still have a different communication and storage model than internal events.

## 5. Which Model to Choose?

- **Use ApplicationEventPublisher** when a bean wants to notify listeners in the same application of a business event, such as updating a cache or writing an audit log. Choose synchronous listeners if the caller needs to know the result immediately; choose async when deferred processing is acceptable and an appropriate executor is configured.
- **Use a Spring Messaging channel** when you need a message/handler abstraction inside a pipeline or integration with Spring components that use **Message<?>**.
- **Use WebSocket/STOMP** when a browser or client needs a two-way connection and live updates, such as chat, dashboards, or real-time notifications.
- **Use JMS or a dedicated broker** when services need to communicate without running in the same process, need to decouple producer/consumer uptime, or need storage and distribution capabilities provided by a broker.
- **Use Spring AMQP/Kafka** when the problem requires the routing, queues, exchanges, partitions, consumer groups, or event-log retention of the corresponding ecosystem.

A practical rule: start with internal mechanisms when all components belong to the same application and durable delivery is not required. Move to a broker/transport when you need to cross process boundaries, deploy independently, share across multiple instances, or support storage and replay.

## 6. Reliability and Operations

Whichever model you choose, clarify the following questions before going to production:

1. **Who owns the message?** Identify the producer, consumer, schema, version, and the meaning of each header.
2. **What does a successful send mean?** **MessageChannel.send** returning does not mean the consumer's business logic has committed. With a broker, distinguish between the broker accepting the message, the consumer receiving it, and the consumer completing its transaction.
3. **Can duplicate processing occur?** Retries or redelivery can cause the same message to arrive multiple times. Design idempotent consumers using a message ID or business key.
4. **When to retry and when to route to an error path?** Distinguish transient errors from data errors; bound retry attempts and define a dead-letter/quarantine flow when supported by the broker.
5. **Is ordering required?** Ordering is only guaranteed within the specific scope and conditions of the channel/broker/partition; do not assume system-wide global ordering.
6. **Is observability needed for the processing flow?** Use correlation IDs/trace IDs, structured logging, and metrics for throughput, latency, queue depth, retries, and errors.
7. **Is the payload safe and compatible?** Check size, schema, version, sensitive data, and access permissions. Do not send arbitrary objects across trust boundaries.
8. **Is atomicity with the database required?** If you need to persist business changes and emit a message as a durable unit, consider the transactional outbox pattern or appropriate transaction integration; simply publishing an event after commit does not cover every case where the process crashes between the two operations.

For in-memory async, configure a bounded executor with an explicit task-rejection policy. If the queue is unbounded, sudden load spikes can cause memory to grow continuously. For brokers, monitor queue/partition lag, connections, disk, redelivery, and dead-letter queues. Ensure authentication, per-destination/topic authorization, and transport encryption when messages leave the process.

## 7. Common Design Mistakes

- **Assuming MessageChannel is always a network channel:** the interface only describes a send point; you must check the actual implementation and adapter.
- **Assuming @EventListener runs in the background by default:** default listeners usually run synchronously on the event-publishing thread.
- **Assuming the simple broker is a clustered broker:** Spring's built-in simple broker keeps state in application memory; multiple instances do not automatically share subscriptions.
- **Treating send() as processing confirmation:** the send result does not replace consumer acknowledgements or transaction outcomes.
- **Using a mutable payload across multiple handlers:** one handler mutating the object can cause another handler to see modified data.
- **Omitting correlation IDs or idempotency:** makes it hard to trace a message flow and hard to handle retries safely.
- **Using internal events for tasks that must survive restarts:** in-memory events are not a durable queue; choose a broker or outbox if business requirements need that.
- **Confusing Spring Framework with Spring Integration/Spring AMQP/Spring Kafka:** check dependencies and packages to know which project an abstraction or implementation comes from.

## 8. Conclusion

In-memory exchange fits internal coordination within a single process: it is simple, fast, and requires few operational components, but has no persistence or cross-instance distribution by default. Networked exchange fits when independent clients or services need to communicate; it extends connectivity across boundaries but introduces serialization, network failures, security, and operational requirements.

Spring provides message abstractions to reduce coupling between producers and consumers. Choosing the right option depends on the deployment boundaries, reliability, latency, scalability, and degree of independence the system needs.
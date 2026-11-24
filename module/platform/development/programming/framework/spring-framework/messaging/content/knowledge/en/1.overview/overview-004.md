# Terminology Map in Spring Messaging: Sender, Receiver, Channel, Destination, and Broker

## Objectives

When reading or designing a messaging flow in a Spring application, you need to distinguish five roles:

- **Sender / producer:** creates and sends messages.
- **Receiver / consumer:** receives and processes messages.
- **Channel:** communication path the application uses to pass messages between components.
- **Destination:** logical address to which messages are sent, typically a queue or topic managed by a messaging system.
- **Broker:** intermediary server that receives, routes, buffers, or distributes messages across applications.

These terms describe different parts of a flow. A channel is not automatically a broker; a destination is not a consumer; and an application can use internal channels without an external broker.

## 1. What Is a Message?

In Spring Messaging, a message is a data packet with two parts:

1. **Payload:** the core content to transmit, such as an Order object, a text string, or an event.
2. **Headers:** accompanying metadata, such as message ID, timestamp, sender origin, correlation ID, or routing information.

Spring represents this packet with the `Message<T>` interface. The payload has type `T`; headers are accessed via `MessageHeaders`. Messages can be created using `MessageBuilder`.

Conceptual example:

~~~text
Message<OrderCreated>
  payload:
    orderId = "ORD-42"
    total = 250000
  headers:
    messageId = ...
    timestamp = ...
    correlationId = "REQ-17"
    source = "checkout-service"
~~~

The payload answers "what data is being transmitted?". Headers answer "what metadata does this message carry for processing, tracing, or routing?". Do not put all metadata inside the payload if consumers need it as transport or correlation information.

## 2. The Five Key Terms

| Term | Meaning | Question to Ask |
|---|---|---|
| Sender / producer | Component that creates and sends a message. Can be a service, controller, adapter, or another application. | Who originates the event or request? |
| Receiver / consumer | Component that receives and processes a message. Can be a handler, listener, or another application. | Who is responsible for handling the message? |
| Channel | Abstraction or path transferring messages between components in an application. In Spring, `MessageChannel` defines the send operation. | Through which flow does the sender pass the message? |
| Destination | Logical address targeted by a message in a messaging system, such as a queue, topic, or STOMP destination. | To which address is the message sent? |
| Broker | Intermediary system that receives messages from producers and routes, stores, or distributes them to consumers per configuration. | Which intermediary manages delivery? |

### Sender / producer

The sender is where sending begins. The sender constructs the payload, optionally attaches headers, and invokes a message-sending API.

In Spring, the specific API depends on the technology:

- Sending to an internal channel: call `MessageChannel.send(message)`.
- Sending via JMS: use `JmsTemplate`.
- Sending via RabbitMQ: use `RabbitTemplate`.
- Sending to Kafka: use `KafkaTemplate`.
- Sending to a STOMP destination in a WebSocket app: use `SimpMessagingTemplate`.

The sender does not necessarily need to know which consumer will handle the message. In a broker model, the sender usually only needs to know the destination or routing information.

### Receiver / consumer

The receiver is where messages are accepted and processed. It may inspect the payload, validate data, update state, invoke business logic, or emit follow-up messages.

In Spring, a receiver can be:

- A `MessageHandler` registered with a `SubscribableChannel`.
- A Spring Integration endpoint.
- A method annotated with `@JmsListener`, `@RabbitListener`, or `@KafkaListener` when using the respective module.
- A STOMP/WebSocket message-handling method, such as one using `@MessageMapping`.

Receivers should process messages safely when messages are redelivered. In systems with retries or at-least-once delivery, the same business operation may be seen multiple times; idempotent processing prevents creating duplicate orders or charging twice.

Sender and receiver are roles per direction of communication. In a request/reply flow, a component can be the sender of the request and become the receiver of the reply.

### Channel

A channel is an abstraction connecting messaging components. In Spring Messaging, the `MessageChannel` interface provides the operation to send a `Message`. A channel can reside entirely in the application process's memory; it does not automatically equate to a queue on a broker server.

Important interfaces:

- `MessageChannel`: message-sending abstraction.
- `SubscribableChannel`: channel allowing handlers to subscribe to receive messages.
- `PollableChannel`: channel allowing consumers to actively call a receive operation.
- `MessageHandler`: component that processes messages.

Common channel implementations in Spring:

| Channel | Provided By | High-Level Behavior |
|---|---|---|
| `ExecutorSubscribableChannel` | Spring Messaging | Dispatches to registered handlers; can use an Executor to run handlers. |
| `DirectChannel` | Spring Integration | Invokes the handler directly on the sending thread; commonly used for synchronous in-app processing. |
| `PublishSubscribeChannel` | Spring Integration | Broadcasts messages to subscribers; suits cases where multiple components need the same event. |
| `QueueChannel` | Spring Integration | Holds messages in an internal queue for consumers to retrieve later via poll/receive. |

A channel name only has meaning within the application's configuration. For example, a channel named `orders` may connect an order service to a handler; that name does not automatically create a queue named `orders` on RabbitMQ or Kafka.

### Destination

A destination is the address a producer targets in a messaging system. Depending on the technology, a destination can be:

- **Queue:** commonly used for point-to-point messaging. Multiple consumers may compete for messages; a message in a queue is typically delivered to one consumer at a time per the system's semantics.
- **Topic:** commonly used for publish/subscribe. Independent subscriptions can receive copies of the same event.
- **STOMP destination:** a logical path such as `/topic/prices` or `/queue/orders`. Exact behavior depends on broker and application configuration.
- **Kafka topic:** an event stream split into partitions. Consumer groups determine how consumers share reading partitions.

These examples are not strictly interchangeable. Queues, topics, STOMP destinations, and Kafka topics each have distinct semantics, storage mechanisms, and distribution behavior. Read the documentation for your chosen technology before assuming delivery guarantees.

Destination answers "where is it sent?". Channel answers "through which abstraction does the application transfer the message?". An adapter can bridge an internal channel to an external destination.

### Broker

A broker is an intermediary messaging server or service. Producers send messages to the broker; the broker applies routing rules and delivers messages to matching consumers or subscriptions.

Depending on the product and configuration, a broker typically handles tasks such as:

- Managing queues, topics, partitions, or routing structures.
- Accepting connections from producers and consumers.
- Storing or buffering messages when consumers are not yet ready.
- Routing messages to queues or subscriptions.
- Supporting acknowledgements, retries, redelivery, and persistence.
- Tracking consumer or subscription state.

Common examples of brokers and ecosystems include RabbitMQ, ActiveMQ Artemis, and Apache Kafka. Kafka is more accurately described as a distributed event streaming platform, though Kafka brokers are still the server components that receive and store data for topic partitions.

Spring Framework is not a broker. Spring provides abstractions and integration modules/clients for applications to communicate with brokers or internal channels.

## 3. Two Flows to Distinguish

### Internal Flow Without a Broker

~~~mermaid
flowchart LR
    S["Sender"] --> M["Message: payload + headers"]
    M --> C["MessageChannel"]
    C --> H["MessageHandler / Receiver"]
~~~

Example: a service constructs a message, sends it into an `ExecutorSubscribableChannel`, and a registered handler processes it. Everything can happen inside the same Java process. No queue server, network, or external broker is needed.

### Flow Through a Broker

~~~mermaid
flowchart LR
    S["Sender / producer"] --> T["Spring template or outbound adapter"]
    T --> B["Broker"]
    B --> D["Destination: queue / topic"]
    D --> I["Inbound adapter or listener"]
    I --> R["Receiver / consumer"]
~~~

The broker receives the message, applies routing configuration, and delivers the message to the appropriate destination/subscription. The consumer may run in a different process or on a different host from the producer.

### When Using Spring Integration to Bridge Channels and Brokers

~~~mermaid
flowchart LR
    P["Producer"] --> C1["Internal channel"]
    C1 --> O["Outbound adapter"]
    O --> B["Broker"]
    B --> D["Queue / topic"]
    D --> I["Inbound adapter"]
    I --> C2["Internal channel"]
    C2 --> H["Message handler"]
~~~

An outbound adapter forwards messages from a Spring flow to an external system. An inbound adapter brings messages from an external system back into a Spring flow. The adapter is the bridge; the internal channel and the broker destination remain two distinct concepts.

## 4. Which Parts Does Spring Provide?

Identify which module you are using because their APIs play different roles:

| Component | Role |
|---|---|
| Spring Messaging (`spring-messaging`) | Provides the message model and abstractions such as `Message`, `MessageChannel`, `MessageHandler`, `MessageBuilder`. |
| Spring Integration | Provides channels, endpoints, adapters, and flows to connect components or systems. Channels like `DirectChannel` and `QueueChannel` belong to this module. |
| Spring WebSocket / STOMP | Enables message handling over WebSocket; includes `@MessageMapping`, `SimpMessagingTemplate`, and support for a simple broker or broker relay. |
| Spring JMS | Connects applications to JMS systems via APIs such as `JmsTemplate` and `@JmsListener`. |
| Spring AMQP | Connects to AMQP systems, commonly RabbitMQ, via `RabbitTemplate` and `@RabbitListener`. |
| Spring for Apache Kafka | Connects to Kafka via `KafkaTemplate` and `@KafkaListener`. |

Not every API in the table lives inside the Spring Messaging module. For example, `DirectChannel` is a Spring Integration implementation; `@JmsListener` belongs to Spring JMS; `@RabbitListener` belongs to Spring AMQP. Distinguishing modules helps you select the right dependencies and consult the right documentation.

## 5. Java Example: Sender Sending Through an Internal Channel

The example below uses `ExecutorSubscribableChannel` from Spring Messaging. A handler subscribes directly to the channel. This channel only demonstrates in-app exchange; the example does not create any external broker or destination.

Project structure:

~~~text
spring-messaging-map/
  pom.xml
  src/
    main/
      java/
        demo/
          MessagingMapDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-messaging-map</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.8</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### MessagingMapDemo.java

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessagingMapDemo {

    public static void main(String[] args) {
        // Internal channel within the application.
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        // Receiver registers as a handler on the channel.
        channel.subscribe(message -> System.out.printf(
                "receiver=order-handler, sender=%s, payload=%s%n",
                message.getHeaders().get("sender"),
                message.getPayload()
        ));

        // Sender creates a message containing payload and metadata.
        Message<String> message = MessageBuilder.withPayload("order-42")
                .setHeader("sender", "checkout-service")
                .build();

        // Send the message into the channel.
        System.out.println("sent=" + channel.send(message));
    }
}
~~~

Run from the project directory using Java 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessagingMapDemo
~~~

Stdout result:

~~~text
receiver=order-handler, sender=checkout-service, payload=order-42
sent=true
~~~

How to read the example:

1. `checkout-service` acts as the sender and creates a message with payload `order-42`.
2. The `sender` header carries metadata about the origin. This header is not a destination and does not route the message automatically.
3. `ExecutorSubscribableChannel` is an internal channel. The handler registered via `subscribe` acts as the receiver.
4. `send` transfers the message to the channel; with the default channel without an Executor, the handler is invoked on the sending thread.
5. Returning `true` indicates the send operation through the channel succeeded in this example. It is not a broker acknowledgement, nor is it confirmation that an external system completed business processing.

If you need to send through a broker, the application must use the appropriate template/client or adapter, configure the destination, and connect to the messaging system. You cannot simply rename the channel in the example above to a queue name and expect a broker to appear automatically.

## 6. API Examples by System

The snippets below illustrate API calls; they are not standalone projects and require the corresponding dependencies, connection configurations, and resources.

### STOMP / WebSocket

~~~java
messagingTemplate.convertAndSend("/topic/orders", event);
~~~

`/topic/orders` is a STOMP destination. A configured broker or in-app simple broker distributes the message to matching subscriptions. When using a broker relay, Spring forwards it to an external STOMP broker.

### JMS

~~~java
jmsTemplate.convertAndSend("orders.queue", event);
~~~

The name `orders.queue` is resolved to a JMS destination through JMS configuration. A consumer can listen to that destination with `@JmsListener`. The JMS provider/broker handles transport per configuration.

### RabbitMQ via Spring AMQP

~~~java
rabbitTemplate.convertAndSend("orders.exchange", "orders.created", event);
~~~

In this example, the producer sends to an exchange with a routing key. The exchange applies bindings to route to queues. Hence, exchange, routing key, and queue are separate concepts; do not call all of them channels.

### Apache Kafka

~~~java
kafkaTemplate.send("orders", event);
~~~

`orders` is the topic name. Kafka stores records in topic partitions; consumer groups divide partition reading among consumers in the same group. This distribution model differs from traditional queues and depends on partition count, consumer groups, and offsets.

## 7. How Do Queue, Topic, and Channel Differ?

| Concept | Typical Purpose | Where It Lives |
|---|---|---|
| Spring channel | Connects components inside an application's messaging flow. | In the Spring model or runtime; may reside in memory. |
| Queue | Holds messages for consumers to receive under point-to-point or competing-consumers models. | In a messaging system/broker, depending on technology. |
| Topic | Broadcasts events to multiple subscriptions or consumer groups. | In a messaging system/broker, depending on technology. |
| Destination | General term for a message target address. | Defined by the protocol or messaging system. |
| Broker | Manages accepting, storing, and distributing messages. | Intermediary process or service. |

An application might have a channel named `ordersChannel` wired to an outbound adapter; the adapter sends messages to a RabbitMQ exchange; the exchange routes to the `orders.created` queue. That flow involves a channel, an adapter, an exchange, and a queue. They are related, yet they are not the same object.

## 8. Message Lifecycle and Delivery Guarantees

A messaging flow typically has these steps:

1. Sender creates payload and headers.
2. Sender sends the message to a channel or through a template/client.
3. If a broker is present, the broker receives the message and routes it to a destination per configuration.
4. Receiver obtains the message.
5. Receiver executes business logic.
6. The system acknowledges, retries, or routes the message to an error flow depending on configured mechanisms.

Distinguish three kinds of confirmation:

- **Send result:** the send API indicates whether the send operation was accepted.
- **Broker acknowledgement:** the broker/provider confirms a delivery or storage step according to the protocol.
- **Business acknowledgement:** the application confirms business completion, such as an order having been created.

These three are not synonymous. For instance, `MessageChannel.send` returning `true` does not prove a remote consumer has processed the order.

Guarantees such as at-most-once, at-least-once, redelivery, ordering, and persistence depend on the technology, configuration, transactions, acknowledgements, and how consumers handle failures. Retries can cause the same message to be processed again. Therefore, consumers of critical business workflows should have an idempotency strategy, such as using an event ID or business key to detect already-processed requests.

When messages cross a network, payloads usually need to be serialized into a transmissible format and deserialized on the receiving side. Converters/serializers must agree on data types, schemas, and versions. Do not assume Java objects can be sent directly between two separate-process applications without conversion configuration.

## 9. How to Read a Messaging Diagram

When looking at a diagram or code, locate each element in order:

1. **Who creates the message?** Look for a service, controller, producer, or template call.
2. **Where does the message travel inside the app?** Look for `MessageChannel`, channel names, and adapters.
3. **Is there a broker?** Look for connection configuration, clients/templates, or broker relays. Seeing only an internal channel is not enough basis to conclude a broker exists.
4. **What is the destination?** Identify the queue, topic, STOMP destination, Kafka topic, or exchange/routing key.
5. **Who receives and processes it?** Look for handlers, listeners, subscriptions, or consumers.
6. **What happens on failure?** Check acknowledgements, retries, dead-letter handling, transactions, and idempotency.

## 10. Common Misunderstandings

- **Calling a channel a broker:** a channel is usually an in-application abstraction; a broker is an intermediary system that can run separately.
- **Treating a destination as a receiver:** a destination is an address; a receiver is the component processing messages on the receiving side.
- **Assuming every channel stores messages:** a channel may forward messages directly; only some channel types have a buffer or queue.
- **Assuming internal channels require a broker:** channels like `ExecutorSubscribableChannel` can operate within a single process.
- **Assuming a successful send means business success:** send result, broker acknowledgement, and business acknowledgement are distinct milestones.
- **Equating queues and topics:** they generally represent different distribution models; exact semantics are determined by the technology.
- **Assuming every listener API belongs to Spring Messaging:** `@JmsListener`, `@RabbitListener`, and `@KafkaListener` come from their respective integration modules.
- **Assuming headers are payload:** headers are metadata; payload is the primary content. Also do not add a custom header named `destination` and expect it to automatically route messages.

## Takeaways

- **Sender** creates and sends.
- **Receiver** receives and processes.
- **Channel** is the path or abstraction transferring messages inside the application.
- **Destination** is the receiving address in a messaging system.
- **Broker** is the intermediary system managing receipt, routing, and distribution.
- **Message** carries payload along with headers.
- **Adapter/template** connects Spring APIs to a specific protocol or broker.

When analyzing a flow, identify each role and the boundary between the application and the broker. That helps you pick the right Spring module, configure the right destination, and know accurately how far a message has progressed.
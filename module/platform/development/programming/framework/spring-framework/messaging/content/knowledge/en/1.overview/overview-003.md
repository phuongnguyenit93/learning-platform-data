# The Position of spring-messaging in Spring Framework

## Learning Objectives

After this lesson, you will be able to:

- Explain why Spring Framework has an abstraction layer for messaging.
- Identify the role of the spring-messaging artifact in Spring's architecture and distinguish it from a broker or protocol integration library.
- Describe the relationship between Message, MessageHeaders, MessageChannel, and MessageHandler.
- Recognize how Spring WebSocket/STOMP and Spring Integration build on the messaging foundation.
- Choose the right level of abstraction for an inter-component communication problem.

## 1. The Problem That spring-messaging Solves

In a typical application, one object calls another object's method directly. The caller must know the receiving object and usually depends on that object's type or API. This works well for synchronous calls within the same process, but creates tight coupling when you need to change how work is distributed, add receivers, transmit data over a protocol, or offload processing to another thread.

Messaging changes how components connect: the sender creates a message and sends it through a channel. The receiver registers to process messages on that channel. The sender works against a message-sending contract instead of directly calling a specific business method.

For example, when an order is created, the ordering component can emit a message carrying the order data. Components that send email, update inventory, or record analytics can receive the message through separate flows. This model decouples where an event originates from where it is handled, but a MessageChannel alone does not turn an application into a distributed system: execution, buffering, distribution, and message durability depend on the implementation or adapter being used.

Spring Framework provides the spring-messaging module to standardize these foundational concepts. The module includes a message model, channel contracts, handler contracts, and supporting utilities. Higher-level projects or modules can reuse the same model instead of defining their own separate messaging APIs.

## 2. The Module's Position in Spring Architecture

Spring Framework is divided into several modules with distinct responsibilities: container and dependency injection, context, data access, transactions, web, testing, and messaging. spring-messaging is the module dedicated to the message exchange model and contracts. It belongs to Spring Framework, but is neither synonymous with spring-core nor a message broker.

Its position can be visualized as follows:

~~~mermaid
flowchart TB
    APP["Application business components"]
    API["spring-messaging<br/>Message · Headers · Channel · Handler"]
    WS["spring-websocket<br/>WebSocket and STOMP"]
    SI["Spring Integration<br/>Integration flows and adapters"]
    BROKER["Protocol adapters or clients<br/>JMS · AMQP · Kafka · RSocket"]
    INFRA["Actual transport or broker"]

    APP --> API
    WS --> API
    SI --> API
    BROKER --> API
    BROKER --> INFRA
~~~

The diagram illustrates the conceptual relationships. Each integration has its own concrete wiring, and not every broker is provided directly by Spring Framework.

- **spring-messaging:** defines the shape of a Message, how messages are sent over a MessageChannel, how MessageHandlers are registered, message conversion, and related utilities.
- **spring-websocket:** provides WebSocket infrastructure and STOMP support. When using STOMP, frames are mapped to Spring Messages and flow through Spring channels.
- **Spring Integration:** extends the messaging model with enterprise integration patterns such as routers, filters, transformers, splitters, aggregators, service activators, and adapters to external systems.
- **Spring JMS, Spring AMQP, Spring Kafka, and corresponding adapters:** work with the APIs, clients, and rules specific to each protocol or broker. These are technology-specific integration layers; do not assume that merely adding spring-messaging gives you connectivity to RabbitMQ, Kafka, or a JMS broker.
- **Broker or transport:** is responsible for concrete capabilities such as routing, durable storage, acknowledgements, network delivery, consumer groups, or transport protocols.

spring-messaging originated from Spring Integration's messaging model. The foundational abstractions were extracted and placed into Spring Framework so multiple Spring projects could share them, even when an application does not use all of Spring Integration.

Key point to remember: spring-messaging is the shared contract layer on the application side. It helps components exchange messages under a consistent model; it does not by itself supply all the operational features of a broker.

## 3. Core Abstractions

### 3.1. Message: Data Packaged as a Message

A Message<T> consists of two parts:

- **Payload:** the main content the sender wants to transmit. The payload type can be String, a DTO, a byte array, or another object type.
- **Headers:** metadata accompanying the payload, such as ID, creation timestamp, content type, correlation ID, destination, or application-defined information.

Headers separate business data from control information. For instance, the payload holds order details, while a header can hold a correlation ID to trace the entire processing lifecycle.

In Spring, MessageHeaders is the metadata structure exposed through Message. Under normal usage, a Message and its header map are immutable: they should not be treated as a mutable Map to modify after dispatch. However, immutability of the message envelope does not automatically make every object inside the payload immutable. If the payload is a mutable object and multiple components hold references to it, the application still must control data mutation.

Commonly encountered classes:

- **Message<T>:** interface describing a message with a payload and headers.
- **MessageHeaders:** provides message headers, including standard metadata such as ID and timestamp.
- **GenericMessage<T>:** common implementation of Message.
- **MessageBuilder<T>:** builder API for creating a Message or creating a new message based on an existing Message.
- **ErrorMessage:** message used to carry a Throwable as its payload.

Example of building a message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class BuildMessageExample {
    public static void main(String[] args) {
        Message<String> message = MessageBuilder
                .withPayload("ORD-42")
                .setHeader("eventType", "order.created")
                .setHeader("source", "checkout")
                .build();

        System.out.println(message.getPayload());
        System.out.println(message.getHeaders().get("eventType"));
    }
}
~~~

Output:

~~~text
ORD-42
order.created
~~~

The payload is the order ID. The eventType header describes the event kind, and source identifies the originating component. These headers are application-defined metadata; Spring does not automatically infer business meaning from them.

### 3.2. MessageChannel: Send Point and Boundary Between Sender and Receiver

MessageChannel defines the contract for sending a Message. The sender only needs to know the channel it sends to. It does not need to know which specific handler will receive the message or what class implements that handler.

The two key send methods are:

- send(message): sends the message according to the channel's policy.
- send(message, timeout): sends with a maximum wait time in milliseconds.

The boolean return value indicates whether the channel accepted the message. If send returns false, the send was not accepted, for example due to timeout or rejection by the channel. An unrecoverable error may be thrown as a runtime exception.

Do not interpret send returning true as "business work completed", "broker persisted durably", or "all consumers processed successfully". The exact meaning of acceptance depends on the implementation. With a synchronous channel, the handler may be invoked on the sending thread; with an executor-backed channel, processing may occur on another thread.

### 3.3. PollableChannel and SubscribableChannel

Two common channel groups represent two different ways of receiving messages:

| Channel Type | Receiving Mechanism | Characteristics |
|---|---|---|
| PollableChannel | Consumer actively calls receive() | Can retrieve messages waiting in the channel; typically suits pull-based consumption |
| SubscribableChannel | Consumer registers a MessageHandler | When a message arrives, the channel dispatches it to subscribers per the implementation |

SubscribableChannel manages a list of registered handlers. ExecutorSubscribableChannel is an implementation included in Spring Framework: it dispatches messages to subscribers and can use an Executor. The no-argument constructor executes handlers directly on the thread calling send; the constructor accepting an Executor uses the supplied executor.

Do not confuse Spring Framework's implementations with concrete channels from Spring Integration. For example, DirectChannel, QueueChannel, and PublishSubscribeChannel are frequently mentioned in Spring Integration documentation. They belong to the higher integration layer, not as alternate names for every MessageChannel in spring-messaging.

### 3.4. MessageHandler: Message Handling Contract

MessageHandler is the contract for the component that receives and processes a Message. The handler reads the payload, inspects necessary headers, and invokes the corresponding business logic.

Separating MessageHandler from MessageChannel creates two independent responsibilities:

- The channel decides how messages are delivered to receivers.
- The handler decides what to do with a received message.

A channel may serve one or multiple handlers depending on the channel type and configuration. When using multiple subscribers, make sure you know whether the channel broadcasts a copy to every subscriber or selects a single consumer according to the implementation's policy.

Spring also provides ReactiveMessageHandler for a reactive handling contract. When using reactive APIs, distinguish between creating or returning a Publisher and the point when data is actually consumed.

### 3.5. Other Supporting Components

Beyond the three primary abstractions, the module includes supporting components:

- **MessageConverter:** converts between a payload and a message representation suitable for a given context. Having a converter does not mean every payload is automatically serialized to JSON or that every protocol uses the same format.
- **ChannelInterceptor:** observes or intercepts send/receive operations on a channel, suited for cross-cutting concerns such as logging, metadata validation, or adding correlation information.
- **MessageHeaderAccessor:** accesses and manipulates headers in a controlled manner instead of mutating MessageHeaders directly.
- **GenericMessagingTemplate:** an implementation in `org.springframework.messaging.core` providing send, receive, and request-reply operations over a `MessageChannel`. Integration modules provide their own templates such as `JmsMessagingTemplate` (Spring JMS), `RabbitTemplate` (Spring AMQP), `KafkaTemplate` (Spring Kafka), and `SimpMessagingTemplate` (Spring WebSocket/STOMP).

These utilities complement the core contracts. They do not replace the security, authentication, retry, monitoring, or durability policies of the integrated system.

## 4. Processing Flow of a Message

A basic messaging flow typically follows these steps:

1. The event-producing component constructs a payload from business data.
2. MessageBuilder packages the payload along with necessary headers.
3. The producer calls send on a MessageChannel.
4. The channel implementation decides how to accept and forward the message.
5. One or more MessageHandlers receive the message according to the channel's rules.
6. The handler invokes the business service to process the payload.
7. If a response is needed, the application creates and sends another Message along the designed reply flow.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as MessageBuilder
    participant C as MessageChannel
    participant H as MessageHandler
    participant S as Domain Service

    P->>B: Create payload and headers
    B-->>P: Message<T>
    P->>C: send(message)
    C->>H: Forward Message to subscriber
    H->>S: Invoke business logic
    S-->>H: Processing result
    H-->>C: Complete on current flow
    C-->>P: Send acceptance result
~~~

The diagram depicts the conceptual flow. With a synchronous channel, the handler may run inside the send call itself. With an asynchronous channel or a broker-connected adapter, the timing and outcome of processing may be detached from the send call. Therefore, never assume that the producer always receives the business outcome merely from the boolean returned by send.

## 5. Runnable Example with spring-messaging

The example below uses an ExecutorSubscribableChannel without passing an Executor. By the implementation's contract, the subscriber executes on the thread calling send, so stdout ordering in the example is deterministic.

### 5.1. Maven Configuration

You can use the Spring Framework BOM to keep module versions aligned. The following example illustrates this with Spring Framework 7.0.10 and Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-messaging-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>7.0.10</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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

Create the file src/main/java/demo/MessageDemo.java:

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessageDemo {

    public static void main(String[] args) {
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        MessageHandler handler = message -> {
            String orderId = (String) message.getPayload();
            String eventType = (String) message.getHeaders().get("eventType");
            System.out.println(eventType + "|" + orderId);
        };

        channel.subscribe(handler);

        Message<String> message = MessageBuilder
                .withPayload("ORD-42")
                .setHeader("eventType", "order.created")
                .build();

        boolean accepted = channel.send(message);
        System.out.println("sendAccepted=" + accepted);
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.MessageDemo
~~~

Stdout:

~~~text
order.created|ORD-42
sendAccepted=true
~~~

Explanation:

- The producer creates a Message with payload ORD-42 and header eventType set to order.created.
- The producer only holds a reference to SubscribableChannel and does not invoke the handler directly.
- The handler is registered using subscribe.
- When send is called, ExecutorSubscribableChannel has no Executor so it invokes the subscriber on the current thread.
- The handler reads the payload and header and prints a single line.
- send returns true because the channel accepted the message. In this synchronous example, the handler also ran before send returned. Do not generalize that conclusion to asynchronous channels or adapters.

This example only demonstrates the foundational messaging API. It does not create a Spring ApplicationContext, connect to a broker, persist messages to a database, or set up retries or dead-letter queues.

## 6. Relationship with Other Spring Modules and Projects

### 6.1. Spring WebSocket and STOMP

WebSocket provides a bidirectional connection between client and server, but the WebSocket protocol itself does not fully define the business semantics of individual messages. STOMP can be used as a sub-protocol to define frames, commands, and destinations.

In Spring's STOMP support:

- Frames from clients are decoded and represented as Spring Messages.
- Messages enter channels such as clientInboundChannel.
- Destinations can route messages to controller methods annotated with MessageMapping or to a message broker.
- Messages emitted by the application can pass through brokerChannel and be delivered to clients via clientOutboundChannel.

This is a clear example of spring-websocket using the spring-messaging foundation. To configure STOMP over WebSocket, an application needs the appropriate modules such as spring-messaging and spring-websocket. Adding spring-messaging alone does not open a WebSocket endpoint.

### 6.2. Spring Integration

Spring Integration builds on the Message, MessageChannel, and MessageHandler foundation to construct higher-level integration flows. It adds many enterprise integration patterns and adapters for external systems.

For example, a flow can receive data from an endpoint, transform its format, filter by condition, route to different handlers, and send results to a target system. These steps are features of Spring Integration, not of spring-messaging alone.

### 6.3. JMS, AMQP, Kafka, and Brokers

Each messaging technology has its own concepts:

- JMS defines a Java API for message-oriented middleware systems.
- AMQP is a messaging protocol; RabbitMQ is a broker commonly used with AMQP.
- Kafka organizes data into topics and partitions, with consumer groups and offsets.
- RSocket provides an interaction model over a bidirectional connection, with interaction styles such as request-response and stream.

Each integration must map its technology-specific concepts onto the application's API or model. spring-messaging helps standardize some shared concepts, but it does not make the semantics of these technologies identical. For instance, acknowledgements, offsets, transactions, ordering, partitions, and delivery guarantees must still be understood in terms of the specific technology.

### 6.4. Spring Application Events

ApplicationEventPublisher and event listeners serve event communication inside an ApplicationContext. They are useful when one component in the same application wants to notify another component. They do not themselves provide a broker, durable persistence across restarts, or network communication.

MessageChannel has its own Message and channel model. Both mechanisms can coexist in an application, but Spring application events should not be treated as a messaging broker or vice versa.

### 6.5. HTTP/REST

HTTP controllers typically handle request-response: a client sends a request to an endpoint and receives a response. Messaging fits when an application needs to decouple producer from consumer, emit events, fan out to subscribers, or use an adapter to connect to a broker. Choosing messaging solely because it can be asynchronous adds unnecessary complexity if a request-response API already solves the problem.

## 7. What Does spring-messaging Not Handle on Its Own?

When reading the module name, avoid several misconceptions:

- **Not a message broker:** the module does not provide a broker cluster, durable queues, replicated logs, or an administration UI.
- **Not asynchronous by default:** a channel can execute handlers directly on the sending thread. Asynchronicity depends on the implementation and configuration.
- **Does not guarantee exactly-once processing:** a boolean true returned by send does not prove that business state committed or that a consumer processed the message once.
- **Does not create retries or dead-letter queues automatically:** these policies must come from adapters, brokers, or application logic.
- **Does not define business schemas:** payloads and headers are data agreed upon by the application and integrated systems.
- **Does not guarantee global ordering:** multiple subscribers, executors, partitions, or consumers can cause processing order to differ from emission order.
- **Does not protect payloads automatically:** the application still needs to validate inputs, authenticate senders, enforce authorization, and avoid logging sensitive data.

## 8. Guide to Choosing the Right Abstraction Level

| Need | Where to Start |
|---|---|
| Packaging payload and metadata into a Message | spring-messaging |
| Sending a Message through a channel to in-app handlers | spring-messaging |
| Building integration flows with routers, filters, transformers, splitters, aggregators, and adapters | Spring Integration |
| Exchanging STOMP over WebSocket with browser clients | spring-websocket together with spring-messaging |
| Connecting an application to Kafka | Spring for Apache Kafka |
| Connecting an application to RabbitMQ/AMQP | Spring AMQP |
| Integrating with JMS | Spring JMS |
| Publishing internal events within an ApplicationContext | Spring Application Events |
| Exposing request-response APIs to clients | Spring MVC or Spring WebFlux |

You can use spring-messaging directly when building custom adapters, working with Message/MessageChannel/MessageHandler, or interacting with the messaging APIs of another Spring module. If you need a full integration-flow platform, look at Spring Integration. If you need a specific broker, use the corresponding integration and learn that broker's semantics.

## 9. Design Notes and Common Pitfalls

1. **Confusing sending with completion:** send returning true usually only confirms that the channel accepted the message. To know when business processing completes, design explicit acknowledgements or responses.
2. **Assuming every channel buffers messages:** MessageChannel is a send contract. Buffering capability, capacity limits, and receiving behavior depend on the channel type.
3. **Assuming every channel runs on another thread:** ExecutorSubscribableChannel without an Executor runs handlers on the calling thread. Read the implementation docs before drawing conclusions about concurrency.
4. **Putting all data into headers:** the payload should carry business data; headers should carry metadata such as correlation ID, content type, or destination.
5. **Mutating the payload after sending:** the envelope may be immutable while the payload object remains mutable. Use immutable objects or defensive copies when shared state must be avoided.
6. **Ignoring limits and timeouts:** sending can block or be rejected. Applications must handle false return values, timeouts, and exceptions according to an explicit policy.
7. **Using arbitrary header names:** standardize header names, data types, and meanings between producers and consumers. Avoid overwriting system headers or trusting metadata from untrusted sources.
8. **Using executors without load management:** account for pool sizes, queue capacities, backpressure, shutdown, and exception handling.
9. **Assuming a converter equals a broker serializer:** payload conversion in Spring and serialization on the wire can be two separate steps. Verify the actual adapter configuration.
10. **Neglecting observability and correlation:** correlation IDs, structured logs, and metrics help trace a message across components. Do not log sensitive payloads merely for debugging.

## 10. Self-Check Questions

1. How does a Message differ from a payload? Why are headers useful?
2. How does MessageChannel decouple producers from consumers?
3. What is the primary difference between PollableChannel and SubscribableChannel?
4. Why does send returning true not mean business processing has finished?
5. Where does an ExecutorSubscribableChannel without an Executor execute its handlers?
6. In what scope of responsibility does spring-messaging differ from Spring Integration?
7. Why is adding spring-messaging not enough to connect to RabbitMQ or Kafka?
8. When should you use Application Events or REST instead of messaging?

## 11. Conclusion

spring-messaging is the messaging foundation at the Spring Framework level: it provides the Message model, headers, channels, handlers, and utilities so components can exchange messages under a shared contract. Other modules and projects build on this foundation for higher-level features such as STOMP over WebSocket or integration flows.

When designing a system, clearly separate three layers: the application's message model, the implementation/adapter transferring messages, and the broker or transport infrastructure. That distinction helps you pick the right dependencies, understand processing guarantees accurately, and avoid false expectations of MessageChannel.

## Official References

- Spring Framework Reference Documentation: https://docs.spring.io/spring-framework/reference/
- Spring Framework STOMP message flow: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework STOMP overview: https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html
- Spring Framework Messaging API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/package-summary.html
- Spring Framework messaging support API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/package-summary.html
- Spring Integration overview: https://docs.spring.io/spring-integration/reference/overview.html

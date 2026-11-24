# Learning Path for Spring Framework Messaging: From Core Abstractions to Protocols

> **Lesson scope:** build a layered understanding of messaging in the Spring ecosystem: start from Spring Messaging's Message, MessageChannel, and MessageHandler model; continue with Spring Integration; then connect application protocols such as STOMP and RSocket, and distinguish them from broker integrations like JMS, AMQP, and Kafka.

## 1. Objectives and Architecture Map

Messaging is a way for components to exchange information via messages. A sender constructs a message, passes it into a communication point, and one or more receiving components process it. Sender and receiver can avoid direct coupling to each other's concrete classes; the actual degree of decoupling depends on how channels, protocols, brokers, and delivery policies are chosen.

After this lesson, you should be able to:

- Explain payload, headers, message, channel, handler, and endpoint.
- Read a message flow in a Spring application and identify where messages are created, forwarded, transformed, and processed.
- Distinguish Spring Messaging's abstractions from the channels and Enterprise Integration Patterns provided by Spring Integration.
- Choose the right approach for in-process communication, WebSocket/STOMP, RSocket, or message brokers.
- Recognize issues around threads, ordering, errors, retries, acknowledgements, security, and observability.

The layers can be visualized as follows:

~~~text
Sending application
    |
    v
Message<T> = payload + headers
    |
    v
MessageChannel.send(message)
    |
    v
MessageHandler.handleMessage(message)
    |
    +----> business processing
    |
    +----> next channel / handler
    |
    +----> protocol or broker adapter
                 |
                 +---- STOMP over WebSocket
                 +---- RSocket
                 +---- JMS / AMQP / Kafka (respective integration projects)
~~~

The blocks above are not synonymous. A message is a data model; a channel is an abstraction for passing messages; a handler is a processing component; a protocol defines how systems exchange data over the wire; a broker typically manages storage, routing, and distribution across processes. An in-memory channel does not automatically provide broker guarantees.

## 2. Foundation: Message, Payload, and Headers

### 2.1 Message as a Data Envelope

In Spring Messaging, a message has two parts:

- **Payload:** the core content, which can be a Java object, string, byte array, or another data type.
- **Headers:** accompanying metadata, such as message ID, creation timestamp, content type, correlation ID, routing information, or processing metadata.

The common generic type is `Message<T>`. The type parameter T represents the payload type. Most message-handling APIs accept `Message<?>` because a handler may receive payloads of various types.

Key types and APIs:

- **Message<T>:** interface representing a message, exposing payload and headers.
- **GenericMessage<T>:** basic implementation of Message.
- **MessageHeaders:** the message's metadata collection. Headers are designed to be read-only once the message is created.
- **MessageBuilder:** convenient way to create a new message or build a message from an existing one.
- **MessageHeaderAccessor:** API for controlled access and modification of headers, useful when working with framework-specific headers.

For example, an order event may carry order data as its payload and headers including `tenantId`, `correlationId`, and `contentType`. The payload answers "what is the business data"; headers answer "in what context was this message created and how should it be processed".

Do not put all business data into headers. Headers belong to metadata supporting transport, routing, correlation, or processing. Business content should live in the payload so the payload schema can be governed cleanly.

### 2.2 Creating a Message

The Java example below is a complete class. The project needs the **org.springframework:spring-messaging** dependency, with its version aligned via the Spring Framework BOM or Spring Boot dependency management.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessageEnvelopeDemo {
    public static void main(String[] args) {
        Message<String> message = MessageBuilder
                .withPayload("order.created")
                .setHeader("tenantId", "acme")
                .setHeader("correlationId", "corr-001")
                .build();

        System.out.println(message.getPayload());
        System.out.println(message.getHeaders().get("tenantId"));
    }
}
~~~

Output:

~~~text
order.created
acme
~~~

Once created, a Message is a structured unit of data. If you need to change the payload or headers, create a new message via a builder or appropriate accessor rather than treating headers as an arbitrary mutable map after dispatch.

### 2.3 Common Headers

Several pieces of metadata have well-known meanings:

- **id:** identifier of the message.
- **timestamp:** time when the message was created.
- **contentType:** hint about content type and how to convert the payload.
- **replyChannel:** hint for where to send the reply in certain request-reply flows.
- **errorChannel:** destination for error information in messaging mechanisms supporting error routing.
- **correlationId:** commonly added by the application or integration layer to link messages belonging to the same business flow.

Do not assume every header exists on every message or is preserved by every protocol. When a message crosses a network boundary, adapters may map, convert, or drop metadata. Explicitly distinguish which headers are part of the application contract and which are internal to a framework.

## 3. MessageChannel and MessageHandler: Transport and Processing Abstractions

### 3.1 MessageChannel

**MessageChannel** is the abstraction for sending messages. The sender calls `send` with a message and may specify a timeout. The boolean result indicates whether the send operation was accepted under the channel's contract; it does not prove that business processing on the receiving side has completed.

A channel establishes a boundary between where messages are emitted and where they are handled. The sender needs to know the target channel, yet usually does not need to know the concrete implementation of the downstream handler.

### 3.2 SubscribableChannel and PollableChannel

Two common sub-interfaces describe two ways of receiving messages:

- **SubscribableChannel:** handlers subscribe to receive messages. When a message is sent, the channel distributes it to subscribers according to the implementation's policy.
- **PollableChannel:** the receiver actively calls `receive`, optionally waiting for a timeout to retrieve a message.

These are two distinct communication styles. In the subscription model, the channel proactively invokes handlers when messages arrive. In the polling model, the consumer decides when to fetch messages. This difference affects threading, load, throttling, and behavior when consumers are slow.

### 3.3 MessageHandler

**MessageHandler** is the abstraction for processing a message via its `handleMessage` method. A handler can execute business logic, validate data, convert payloads, log, call other services, or send a new message to the next channel.

A processing flow often consists of several small handlers, each with a clear responsibility. Splitting work this way makes individual steps easier to test and allows reordering processing without forcing every component into direct dependencies.

### 3.4 Distinguishing Abstractions from Implementations

Spring Messaging provides the core abstractions and several supporting messaging implementations, yet does not turn every channel into a broker. Many channel implementations and rich flow-processing patterns come from **Spring Integration**.

In Spring Integration, common channels include:

| Channel | How It Works | Good Fit For |
|---|---|---|
| DirectChannel | Invokes subscriber directly on the sending thread | Simple, synchronous flows |
| PublishSubscribeChannel | Distributes one message to multiple subscribers | One event needing multiple handling branches |
| QueueChannel | Holds messages in a queue for consumers to pull | Decoupling send time from receive time |
| PriorityChannel | Retrieves messages according to priority | Work items with differing priorities |
| ExecutorChannel | Dispatches processing through an executor | Offloading handling to another thread |

Specific channel names and behaviors depend on the implementation. For instance, DirectChannel does not create a durable queue; an in-memory QueueChannel is not equivalent to a broker with durable storage. When durability, distribution across multiple processes, acknowledgements, or persistence are required, use an appropriate broker and adapter.

## 4. Sending, Receiving, and Converting Messages

At the operations API level, Spring Messaging provides **MessageSendingOperations**, **MessageReceivingOperations**, **MessageRequestReplyOperations**, and the **GenericMessagingTemplate** implementation in package `org.springframework.messaging.core`. This template resolves destination names to a `MessageChannel` for sending, receiving, or performing request-reply. Spring Integration has its own **MessagingTemplate** class in package `org.springframework.integration.core`; that is an Integration project API, not part of the spring-messaging module.

Operations to distinguish:

- **send:** sends an already constructed Message.
- **convertAndSend:** converts an object into a message and sends it.
- **receive:** retrieves a message from a channel type that supports receiving.
- **receiveAndConvert:** receives a message and converts its payload to the desired type.
- **sendAndReceive:** sends a request and waits for a reply message when the channel and configuration support request-reply.

Conversion typically involves a **MessageConverter** and metadata such as content type. Serializing an object to JSON does not automatically solve schema compatibility across service versions. You must manage field names, data types, defaults, schema versions, and rules for invalid payloads.

Request-reply is only appropriate when the sender can wait for a reply and the reply path is well defined. For long-running tasks or asynchronous processing, represent the result as a separate message with a correlation ID rather than holding a synchronous call open for a long time.

## 5. From Spring Messaging to Spring Integration

**Spring Messaging** supplies the shared vocabulary for messages, channels, and handlers. **Spring Integration** is a separate project in the Spring ecosystem that builds on those messaging abstractions to construct integration flows and provides numerous channels, endpoints, adapters, and Enterprise Integration Patterns (EIP).

Do not collapse both projects into a single API:

- Spring Messaging defines the core abstractions and supports messaging across several Spring environments.
- Spring Integration provides tools to build integration pipelines across application components, external systems, and data sources.
- Concrete adapters connecting to external technologies may reside in Spring Integration or in other specialized Spring projects.

### 5.1 Key EIPs

| Pattern | Responsibility | Question to Answer |
|---|---|---|
| Service Activator | Invokes a service or method to process a message | Who executes the business logic? |
| Transformer | Transforms payload or message structure | What format does the data need to become? |
| Filter | Lets messages pass or drops them | Does the message meet the criteria? |
| Router | Chooses the destination channel | Which branch should the message take? |
| Splitter | Splits one message into multiple messages | Into what parts should one input be divided? |
| Aggregator | Combines multiple messages into one result | When are enough parts present to aggregate? |
| Gateway | Provides an interface to invoke an integration flow | How does the application call the flow? |
| Channel Adapter | Connects a channel with an external source or target | Where do messages enter or leave the system? |

Spring Integration provides annotations and a DSL to declare these patterns, such as **@ServiceActivator**, **@Transformer**, **@Filter**, **@Router**, **@Splitter**, **@Aggregator**, and **IntegrationFlow**. They belong to Spring Integration—not all of them are Spring Framework core annotations.

### 5.2 Example Integration Flow

An order-processing flow might be designed as follows:

~~~text
Order input
    |
    v
Validate
    |
    v
Router by order type
    |
    +----> Domestic order ----> Calculate shipping fee
    |
    +----> International order ----> Customs check
    |
    v
Record result
    |
    v
Publish OrderProcessed event
~~~

When designing a flow, specify the payload type at each step, which headers are retained, where errors are routed, and which steps can run in parallel. For splitters and aggregators, define correlation, completion conditions, timeouts, and behavior when a part is missing. Without these rules, an aggregator may wait indefinitely or accidentally combine messages belonging to different requests.

## 6. STOMP Protocol over WebSocket

### 6.1 Participating Layers

WebSocket provides a long-lived bidirectional connection between client and server. STOMP is a frame-based messaging protocol that can run over WebSocket. Spring supports the WebSocket messaging and STOMP model through Spring Framework components, notably in Spring WebSocket and Spring Messaging.

Common APIs and annotations:

- **@EnableWebSocketMessageBroker:** enables broker-backed WebSocket message handling.
- **@MessageMapping:** maps destinations to message-handling methods.
- **@SubscribeMapping:** handles subscription requests via controller mapping.
- **@SendTo:** specifies the destination for sending the return value.
- **SimpMessagingTemplate:** sends messages to destinations from application code.
- **@Payload**, **@Header**, **@Headers**, **@DestinationVariable:** extract payload, headers, or destination variables in handler methods.
- **@MessageExceptionHandler:** handles exceptions raised in message-handling methods within supported scopes.

### 6.2 Typical Flow

A configuration typically splits destinations into two groups:

- Application prefixes, such as `/app`, used to route messages from clients to controller methods.
- Broker prefixes, such as `/topic` or `/queue`, used for destinations managed by the broker and distributed to subscribers.

Example flow:

~~~text
Client sends STOMP SEND to /app/orders
             |
             v
Spring routes to @MessageMapping
             |
             v
Controller processes create-order command
             |
             v
@SendTo or SimpMessagingTemplate
             |
             v
Destination /topic/orders
             |
             v
Broker distributes STOMP MESSAGE
             |
             v
Subscribed (SUBSCRIBE) clients receive result
~~~

The prefix names above are example configurations, not mandatory values. The server must declare the corresponding prefixes and broker. An in-memory simple broker fits some development or simple deployment cases; a broker relay connects to an external broker when dedicated distribution infrastructure is needed. Scalability, persistence, acknowledgements, routing, and delivery guarantees depend on the actual broker.

### 6.3 STOMP Frames to Know

- **CONNECT:** client initiates a STOMP session.
- **SUBSCRIBE:** registers to receive messages from a destination.
- **SEND:** sends a message to a destination.
- **MESSAGE:** frame sent by the broker to subscribers.
- **ACK / NACK:** acknowledges or rejects a message in supported modes and brokers.
- **DISCONNECT:** terminates the session.

When working with STOMP, understand both the WebSocket lifecycle and the STOMP session lifecycle. WebSocket opens the transport connection; STOMP exchanges messaging frames over that connection. Successfully sending a frame does not mean the message was processed successfully at the business layer.

### 6.4 Design Considerations

- Authenticate users during connection setup and enforce destination-based access control.
- Check send permissions and subscribe permissions separately.
- Validate payload data, limit frame sizes, and throttle send rates.
- Handle disconnects, reconnects, subscriptions, and session state.
- Never assume clients stay online or receive every message.
- If missed events must be recovered, design storage, replay, or state synchronization at an appropriate layer; WebSocket itself provides no message history.

## 7. RSocket: Reactive Interaction Model

RSocket is an application protocol for message communication between peers, supporting both single-shot and streaming interaction models. Spring provides RSocket integration through Spring Messaging and related components.

Common components:

- **RSocketRequester:** client API for sending requests to an RSocket peer.
- **RSocketMessageHandler:** connects RSocket messages with Spring handler methods.
- **@MessageMapping:** maps routes to message-handling methods.
- **@ConnectMapping:** handles metadata or data during connection setup per supported configuration.
- **Mono and Flux:** reactive types commonly used to represent a single result or a multi-item stream.

### 7.1 Four Interaction Models

| Model | Description | Examples |
|---|---|---|
| Fire-and-forget | Sends a request without waiting for a protocol-level response | Sending a signal or command needing no direct result |
| Request-response | One request receives one response | Looking up order status |
| Request-stream | One request receives a stream of responses | Tracking prices or progress |
| Request-channel | Both sides exchange streams of messages | Continuously sending data and receiving continuous results |

RSocket supports reactive communication and protocol-level flow control. That helps when streams or bidirectional communication are needed, yet it does not eliminate the need to manage errors, timeouts, subscription cancellation, resource limits, and business idempotency.

RSocket can run over several supported transports, such as TCP or WebSocket. Distinguish transport from interaction model: transport decides which connection carries bytes; interaction model decides how requests and responses are exchanged.

### 7.2 When to Choose RSocket?

RSocket fits when an application needs reactive request-response or streaming communication, especially bidirectional streams. If the primary need is web clients subscribing to destinations under a traditional broker pattern, STOMP over WebSocket may be easier to adopt. If durable queues and processing across multiple independent services are required, evaluate a dedicated broker.

## 8. JMS, AMQP, and Kafka: Related Broker Integrations at a Different Layer

These technologies are often used alongside Spring Messaging, yet should be studied as distinct integration systems:

| Technology | Common Spring APIs | Focus |
|---|---|---|
| JMS | Spring JMS, **JmsTemplate**, **@JmsListener** | Standard Java messaging API and JMS providers |
| AMQP | Spring AMQP, **RabbitTemplate**, **@RabbitListener** | Exchanges, queues, bindings, routing keys, and AMQP brokers |
| Kafka | Spring for Apache Kafka, **KafkaTemplate**, **@KafkaListener** | Topics, partitions, offsets, consumer groups, and distributed logs |

They are not simple drop-in implementations for MessageChannel:

- JMS defines a messaging API and depends on a provider implementation.
- AMQP introduces a broker model of exchanges, queues, and bindings.
- Kafka organizes data into topics and partitions; consumers manage offsets and read positions.
- Spring Messaging provides shared message abstractions, yet does not unify the semantics of these systems.

When integrating, understand the specific acknowledgement, retry, dead-letter, ordering, partitioning, transaction, retention, and replay mechanics of the chosen technology. Adapters can let applications use a more uniform message model, but they do not erase the broker's delivery rules.

## 9. How to Choose the Right Layer

| Need | Recommended Direction to Explore |
|---|---|
| Passing messages between components within the same app | Spring Messaging abstractions and an appropriate channel |
| Building pipelines, routing, transforming, and combining messages | Spring Integration |
| Server pushing events to browsers via destinations and subscriptions | WebSocket + STOMP |
| Reactive communication, request-response, or bidirectional streams | RSocket |
| Queues and system integration via JMS | Spring JMS |
| Routing through AMQP exchanges and queues | Spring AMQP |
| Event streams with topics, partitions, and consumer groups | Spring for Apache Kafka |

Choose according to operational requirements: whether durable storage is needed, synchronous vs asynchronous communication, streaming needs, multi-consumer distribution, replayability, and how the system must handle failures or disconnects.

## 10. Recommended Hands-On Practice Order

1. **Message model:** construct Messages with MessageBuilder; read payload and headers; separate metadata from business data.
2. **Channel and handler abstractions:** read MessageChannel, SubscribableChannel, PollableChannel, and MessageHandler interfaces; trace the send flow to handlers.
3. **Sending and converting:** try GenericMessagingTemplate, MessageSendingOperations, MessageReceivingOperations, MessageRequestReplyOperations, and MessageConverter; observe how content type affects conversion.
4. **Spring Integration:** build a small flow with a service activator, transformer, filter, and router; add splitter/aggregator once correlation is clear.
5. **Error handling:** trigger errors in individual handlers, identify where errors arrive, and distinguish send errors from business processing errors.
6. **STOMP:** create a WebSocket server, map a destination with @MessageMapping, send results to a destination, and subscribe from a client.
7. **RSocket:** try request-response, request-stream, and request-channel; observe cancellation, backpressure, and reactive errors.
8. **Brokers:** pick one of JMS, AMQP, or Kafka; learn the broker model first, then integrate using the matching Spring API.
9. **Operations:** test authentication, authorization, retries, idempotency, timeouts, observability, and recovery after consumer or connection interruptions.

Do not start by learning every broker and protocol at once. Mastering messages, channels, and handlers first makes it clear which parts are shared abstractions and which belong to specific protocols or brokers.

## 11. Common Design Mistakes

- **Confusing channels with brokers:** in-memory channels do not automatically provide persistence, retries across restarts, or distribution across multiple instances.
- **Confusing send with processing completion:** an accepted send only reflects the send step; track business completion at the business layer.
- **Putting business data into headers:** makes payload contracts harder to read and schemas harder to govern.
- **Assuming headers are always preserved:** adapters and protocol mappings can alter metadata across system boundaries.
- **Leaving threads unmanaged:** switching to an executor can alter completion order and expose race conditions.
- **Using request-reply for long-running tasks:** holding requests open too long ties up resources; consider asynchronous result messages instead.
- **Omitting correlation IDs:** makes it hard to correlate messages of the same request, especially with splitters, aggregators, or multiple services.
- **Not designing for idempotency:** retries or redeliveries can execute a business action multiple times.
- **Ignoring timeouts and backpressure:** slow consumers can inflate memory usage, latency, or queued backlogs.
- **Treating WebSocket as a durable queue:** clients can disconnect and miss events; add storage or state-sync mechanisms when required by the business.
- **Skipping destination authorization:** an authenticated connection still must not be allowed to publish or subscribe to every destination.
- **Treating broker semantics as identical:** ACKs, retries, ordering, transactions, and retention differ across JMS, AMQP, and Kafka.

## 12. Self-Assessment Checklist

You have mastered the fundamentals when you can answer in your own words:

- How does a Message differ from a payload? What kind of information belongs in headers?
- How do MessageChannel, SubscribableChannel, and PollableChannel differ?
- What is MessageHandler responsible for? What decides which handler receives a message?
- Why is an in-memory channel not equivalent to a durable broker?
- How does Spring Messaging differ from Spring Integration in scope of responsibility?
- How do STOMP frames, WebSocket connections, and broker destinations relate?
- How does RSocket request-stream differ from request-response? What does backpressure mean?
- How do JMS, AMQP, and Kafka differ in delivery models?
- When handling errors, retries, or duplicate deliveries, how do you avoid executing business logic twice?
- How do you secure destinations, track correlation IDs, and detect slow consumers?

Once you can answer these questions and build a small end-to-end flow from incoming message to result, you have the foundation to read deeper documentation and pick protocols aligned with real system requirements.

## 13. Further Reading

Prioritize official documentation matching the layer you are studying:

- Spring Framework Reference Documentation: Messaging, WebSocket/STOMP, and RSocket sections.
- Spring Integration Reference Documentation: channels, endpoints, Enterprise Integration Patterns, DSL, and adapters.
- Spring JMS Reference Documentation: JmsTemplate, listener containers, and transactions.
- Spring AMQP Reference Documentation: exchanges, queues, bindings, listener containers, and RabbitTemplate.
- Spring for Apache Kafka Reference Documentation: producers, consumers, listeners, offsets, and transactions.
- STOMP and RSocket protocol specifications to understand frames, interaction models, and protocol-level semantics.

Always match documentation versions to the Spring version used in your project. API names, configuration options, and integration capabilities can change across major release lines.
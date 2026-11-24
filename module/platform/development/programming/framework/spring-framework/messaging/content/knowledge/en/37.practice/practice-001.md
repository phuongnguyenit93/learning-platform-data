# Building an In-Memory Message Flow from Sender to Processor

## Objectives

After this lesson, you will be able to:

- Explain the roles of Message, MessageChannel, and MessageHandler in a message processing flow.
- Build an in-JVM message flow using Spring Integration.
- Send a payload along with metadata via MessageBuilder.
- Connect sender, channel, and processor using DirectChannel.
- Distinguish between DirectChannel, QueueChannel, PublishSubscribeChannel, and ExecutorChannel.
- Understand the impact of channels on threads, synchronization, buffering, ordering, and transactions.
- Test the flow with a compilable and runnable Java 17+ program.
- Recognize the limitations of in-memory messaging when durability, multiple instances, or network communication is required.

This lesson belongs to the **Spring Framework - messaging** topic, **Practice** track. We will build a small in-memory pipeline: a sender creates a message and sends it to a channel, a processor receives and transforms the payload, and then forwards the result to a final handler.

## 1. Components in a Message Flow

Spring Messaging provides the Message and MessageChannel abstractions. Spring Integration adds channel implementations and endpoints for building Enterprise Integration Patterns (EIP).

A message typically has two parts:

- **Payload:** business data, such as order details or a command.
- **Headers:** accompanying metadata, such as correlationId, contentType, timestamp, or routing information.

MessageChannel is the communication point used by a sender to transfer messages. The sender does not need to know which specific handler will process them. MessageHandler is the component that receives and processes messages.

Basic flow:

~~~text
Sender
  |
  | Message(payload + headers)
  v
MessageChannel
  |
  v
MessageHandler / Processor
  |
  | transformed Message
  v
Output Channel
  |
  v
Next Handler
~~~

The benefit of this organization is decoupling the sender from the processor. The sender only needs to know the channel it sends to; the processor can be replaced or extended without forcing the sender to call the processing class directly.

### 1.1. Message as an Envelope

Example of a simple message:

~~~text
Payload: "  order-42  "
Headers:
  correlationId = "corr-1001"
  contentType   = "text/plain"
~~~

The payload contains the data to be processed. The correlationId header helps correlate logs or traces across multiple steps belonging to the same business flow.

Messages in Spring Messaging are designed to be immutable: do not modify the headers of an already-created message directly. When you need to change the payload or metadata, create a new message using MessageBuilder. The payload object itself may still be mutable; if shared among multiple handlers, use an immutable payload or clearly define data ownership.

### 1.2. MessageChannel as an Abstraction

An application can declare a variable of type MessageChannel and swap implementations as needed:

- DirectChannel: dispatches directly to a subscriber.
- QueueChannel: stores messages in a queue for a consumer to poll.
- PublishSubscribeChannel: broadcasts to all subscribers.
- ExecutorChannel: dispatches via a TaskExecutor.

A channel name in an application is a logical connection point. It is not necessarily a topic, queue, or destination on an external broker.

## 2. Environment Setup

The example uses Java 17 and Spring Integration 7.1.1. Spring Integration 7.1.x requires Java SE 17 or higher and Spring Framework 7.0 or higher. Use the Spring Integration Core dependency directly to run a standalone program without needing a broker or Spring Boot.

Create the directory structure:

~~~text
in-memory-message-flow/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── InMemoryMessageFlow.java
~~~

### 2.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>in-memory-message-flow</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>7.1.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.InMemoryMessageFlow</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Integration Core brings in the necessary Spring Messaging dependencies. There is no need to add a broker client because the entire example runs in the memory of a single process.

## 3. Creating a Flow with DirectChannel

DirectChannel is a simple choice for a sender to transfer messages directly to a handler. When send is called, the handler is invoked immediately on the sender's thread. Therefore, the sender only completes the send call after the synchronous dispatch finishes.

We use two channels:

1. inputChannel receives messages from the sender.
2. outputChannel receives messages normalized by the processor.

The processor registers as a subscriber on inputChannel. When receiving a message, it reads the payload, normalizes the string, creates a new message, and sends it to outputChannel.

### 3.1. Complete Source Code

Save the file at src/main/java/example/InMemoryMessageFlow.java:

~~~java
package example;

import java.util.Locale;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class InMemoryMessageFlow {

    public static void main(String[] args) {
        DirectChannel inputChannel = new DirectChannel();
        DirectChannel outputChannel = new DirectChannel();

        // Final handler receives the processed result.
        outputChannel.subscribe(message -> {
            System.out.println(
                "PROCESSED: " + message.getPayload()
                    + " | correlationId="
                    + message.getHeaders().get("correlationId")
            );
        });

        // Processor receives the message from the sender and transforms the payload.
        inputChannel.subscribe(message -> {
            String rawPayload = (String) message.getPayload();

            String normalized = rawPayload
                .trim()
                .toUpperCase(Locale.ROOT);

            Message<String> result = MessageBuilder
                .withPayload(normalized)
                .setHeader(
                    "correlationId",
                    message.getHeaders().get("correlationId")
                )
                .setHeader("processed", true)
                .build();

            outputChannel.send(result);
        });

        // Sender creates an envelope containing payload and metadata.
        Message<String> incoming = MessageBuilder
            .withPayload("  order-42  ")
            .setHeader("correlationId", "corr-1001")
            .build();

        boolean accepted = inputChannel.send(incoming);

        System.out.println("SEND_ACCEPTED=" + accepted);
    }
}
~~~

### 3.2. Compile and Run

Open a terminal in the in-memory-message-flow directory and run:

~~~bash
mvn -q clean compile exec:java
~~~

Output:

~~~text
PROCESSED: ORDER-42 | correlationId=corr-1001
SEND_ACCEPTED=true
~~~

The result shows:

1. The sender creates a payload with leading and trailing whitespace.
2. The sender sends the message to inputChannel.
3. DirectChannel dispatches the message to the processor immediately on the same thread.
4. The processor trims the string, converts it to uppercase, and preserves correlationId.
5. The processor creates a new message and sends it to outputChannel.
6. The final handler prints the result.
7. After the synchronous handlers complete, the inputChannel.send call returns true.

### 3.3. Reading the Flow Line by Line

**Creating channels**

~~~java
DirectChannel inputChannel = new DirectChannel();
DirectChannel outputChannel = new DirectChannel();
~~~

Both channels exist within the same JVM. They do not open sockets, connect to a broker, or write messages to disk.

**Registering a handler**

~~~java
inputChannel.subscribe(message -> {
    // process message
});
~~~

subscribe registers a MessageHandler with the channel. When the sender sends a message, DirectChannel dispatches to one subscriber with unicast semantics.

**Creating a message**

~~~java
Message<String> incoming = MessageBuilder
    .withPayload("  order-42  ")
    .setHeader("correlationId", "corr-1001")
    .build();
~~~

MessageBuilder creates an envelope with a String payload and a correlationId header. The sender does not need to know which class implements the processor.

**Sending a message**

~~~java
boolean accepted = inputChannel.send(incoming);
~~~

The boolean value indicates whether the channel accepted/dispatched the message according to the channel's semantics. With DirectChannel, the handler is invoked synchronously before send returns. If the handler throws an exception, the error can propagate back to the sender; there is no automatic retry just from using a MessageChannel.

**Creating a new message**

~~~java
Message<String> result = MessageBuilder
    .withPayload(normalized)
    .setHeader("correlationId", message.getHeaders().get("correlationId"))
    .setHeader("processed", true)
    .build();
~~~

The processor creates a new message instead of mutating the input message. It preserves correlationId to correlate the result with the original request and adds the processed header to demonstrate post-processing metadata.

## 4. DirectChannel: Synchronous, Point-to-Point Processing

DirectChannel is a SubscribableChannel. When send is called, it dispatches the message directly to a subscriber. This is the default channel commonly encountered in Spring Integration when declaring a standard channel.

Characteristics:

- Point-to-point: each message is dispatched to one handler in the subscriber group.
- Synchronous: the handler runs on the thread calling send.
- No separate queue buffer to decouple sender and receiver.
- The sender can observe handler errors within the same call.
- Can coordinate with the current thread's transaction when operations participate in the same transaction manager.

If a DirectChannel has multiple subscribers, the dispatcher can use a load-balancing strategy and failover. It does not broadcast messages to all subscribers. To broadcast, use PublishSubscribeChannel.

DirectChannel is suitable when:

- Processing logic needs to complete immediately within the calling flow.
- You want to keep the call stack and transaction context synchronous.
- You need to connect processing steps within the same process without needing a queue.

Do not use DirectChannel expecting the sender and processor to run independently. A slow handler will slow down the send call as well.

## 5. QueueChannel: Buffering Messages in Memory

QueueChannel is a PollableChannel. It stores messages in a queue; the sender can send before the consumer is ready to receive.

Example:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

QueueChannel queue = new QueueChannel(100);

Message<String> job = MessageBuilder
    .withPayload("job-42")
    .build();

boolean queued = queue.send(job, 0);

Message<?> received = queue.receive(0);
~~~

Here:

- QueueChannel has a capacity of 100.
- send(job, 0) attempts to send immediately without waiting if the queue is full.
- receive(0) retrieves a message immediately if the queue has data.
- If the queue is full, send with a timeout of 0 can return false.
- If the queue is empty, receive with a timeout of 0 returns null.

QueueChannel has a no-arg constructor with a very large capacity (Integer.MAX_VALUE). In real-world applications, consider a bounded capacity to limit memory usage. If the queue is full, send can wait for free space according to the chosen timeout.

QueueChannel only provides an in-process memory buffer. It does not have persistence like a broker. When the JVM stops abruptly, messages sitting in the queue can be lost.

### 5.1. Who Retrieves Messages from QueueChannel?

QueueChannel does not create a processing worker on its own. A consumer needs to call receive or be connected to a Spring Integration poller/endpoint. An application can use a poller to read messages periodically, or use another mechanism to trigger the consumer.

Do not call receive without a timeout on an important thread if the queue might be empty, because the call can block indefinitely.

## 6. PublishSubscribeChannel: Sending the Same Message to Multiple Handlers

PublishSubscribeChannel broadcasts messages to all subscribers. It is suitable for events that multiple components need to receive simultaneously, such as an order event used for audit, analytics, and notification.

Example:

~~~java
PublishSubscribeChannel events = new PublishSubscribeChannel();

events.subscribe(message ->
    System.out.println("AUDIT: " + message.getPayload())
);

events.subscribe(message ->
    System.out.println("ANALYTICS: " + message.getPayload())
);

events.send(MessageBuilder.withPayload("order-created").build());
~~~

With the default configuration without a TaskExecutor, subscribers are invoked on the thread that sends the message. If an executor is configured, dispatching can be asynchronous.

PublishSubscribeChannel is not a queue for consumers to poll. Subscribers are MessageHandlers and are invoked when a message is published.

If a message must be processed by exactly one worker in a group, use DirectChannel or QueueChannel according to the appropriate semantics, not publish-subscribe.

## 7. ExecutorChannel: Dispatching via a Thread Pool

ExecutorChannel is a point-to-point channel that uses a TaskExecutor to dispatch to a handler. It is useful when you want to decouple the sender thread from the processing thread.

~~~text
Sender thread
    |
    v
ExecutorChannel
    |
    v
TaskExecutor queue / worker
    |
    v
MessageHandler
~~~

Important differences compared to DirectChannel:

- The sender typically does not wait for the handler to finish.
- The handler can run on a worker thread.
- Exceptions thrown inside the handler might not propagate back to the already-completed send call.
- The sender's transaction context does not automatically propagate to the handler.
- The executor and queue need bounds to prevent task accumulation and memory growth.

ExecutorChannel is not a durable queue. If the process stops, tasks waiting in the executor can be lost. If durable delivery, acknowledgement, and redelivery are needed, a broker or appropriate persistence mechanism is required.

## 8. Comparing Channels in Practice

| Channel | Semantics | Dispatch | Buffer | When to Use |
|---|---|---|---|---|
| DirectChannel | Point-to-point | Synchronous on sender thread | No | Simple pipelines, needing processing results within the call |
| QueueChannel | Point-to-point | Consumer poll | Yes, bounded by capacity | Need to decouple sending and receiving via an in-JVM queue |
| PublishSubscribeChannel | Broadcast | Synchronous by default; can use an executor | Not a pollable queue | Multiple handlers need to receive the same event |
| ExecutorChannel | Point-to-point | Via TaskExecutor | Relies on executor queue | Need to dispatch to worker threads |

Choose a channel based on business semantics, not just speed. An asynchronous channel can reduce sender wait time, but it changes how errors, transactions, and ordering are observed.

## 9. Message Headers and Correlation

In a multi-step pipeline, the payload describes business data while headers describe transport context.

Some commonly useful headers:

- correlationId: links messages belonging to the same request/flow.
- contentType: describes the payload format.
- replyChannel: channel used for replies in some patterns.
- errorChannel: channel used for errors in some flows.
- timestamp: message creation time if required by the contract.

Do not stuff all metadata into the payload. However, also do not use headers as a substitute for business data that must be persisted durably or transmitted across broker boundaries if adapters do not preserve them.

When creating a new message, explicitly decide which headers to keep. MessageBuilder.fromMessage(message) can create a builder from the current message and then replace the payload or add headers; if creating a completely new message, intentionally copy the necessary headers.

Do not put tokens, passwords, or sensitive data into headers if they might be logged or forwarded beyond the intended scope.

## 10. Error Handling in a Message Flow

With DirectChannel, the handler runs inside the send call. If the handler throws an exception, the error can return to the sender. The sender can catch the error and apply an appropriate policy.

With QueueChannel, the sender can send successfully into the queue before the consumer processes it. Processing errors occur at the later receive/handler time, so the original sender cannot receive that exception from the send call alone.

With ExecutorChannel, the sender has usually already returned before the handler runs. Errors need to be handled via the error handling of the executor/endpoint or flow.

Some principles:

1. Distinguish message sending errors from message processing errors.
2. Define where retry responsibility lies.
3. Do not retry infinitely.
4. For repeatable side effects, use an idempotency key or deduplication.
5. If messages must survive restarts, use a broker/persistent store rather than keeping them only in memory.
6. Log correlationId and the processing step name for traceability.

An in-memory channel does not automatically provide a dead-letter queue, durable acknowledgement, or exactly-once processing. These guarantees must be designed at the application or middleware layer.

## 11. Testing the Message Flow

With a synchronous DirectChannel pipeline, tests can send a message and inspect the result immediately after send returns.

Example logic check:

~~~java
DirectChannel input = new DirectChannel();
AtomicReference<Message<?>> captured = new AtomicReference<>();

input.subscribe(captured::set);

Message<String> message = MessageBuilder
    .withPayload("hello")
    .setHeader("correlationId", "test-1")
    .build();

boolean sent = input.send(message);

assert sent;
assert captured.get() != null;
assert "hello".equals(captured.get().getPayload());
assert "test-1".equals(
    captured.get().getHeaders().get("correlationId")
);
~~~

This is an illustrative test snippet; it needs to be run with assertions enabled or converted into JUnit assertions in a test suite. With ExecutorChannel, you cannot assume the handler has run right after send; tests need to synchronize using a latch/future or a waiting mechanism with a timeout. With QueueChannel, tests need to receive the message after sending.

Cases to test:

- No subscriber: whether send is accepted or not depending on the channel.
- Handler throws an exception.
- Payload is not of the expected type.
- The correlationId header is preserved through the processor.
- Queue is full or queue is empty.
- Multiple subscribers on DirectChannel.
- Multiple subscribers on PublishSubscribeChannel.
- Asynchronous handler completes after sender.
- Cancellation/shutdown when tasks are pending.

## 12. When Is In-Memory Messaging Sufficient?

In-memory channels are suitable when processing steps reside in the same process and do not require durable message storage. They are often useful for:

- Decoupling sender and processor modules.
- Connecting processing steps within the same JVM.
- Experimenting with Enterprise Integration Patterns.
- Building internal pipelines that do not require a network.
- Unit/integration testing message handler logic.

When communication across multiple processes or services is needed, a broker or transport adapter is more appropriate. For example, Kafka, RabbitMQ, JMS, or RSocket can provide network communication and their respective semantics.

Choose a broker when one or more of these capabilities are needed:

- Durable message storage.
- Independent consumers or scaling across multiple instances.
- Acknowledgement, retry, and redelivery.
- Retention, replay, or event streaming.
- Connecting independently deployed services.
- Broker-managed routing or queueing.

Do not switch to a broker just because an application has MessageChannel. Start from requirements around durability, topology, scale, failure recovery, and ordering.

## 13. Common Mistakes

- Thinking MessageChannel is always a network channel or broker destination.
- Assuming DirectChannel stores messages in a queue.
- Using DirectChannel while expecting the sender and processor to run on two different threads.
- Using QueueChannel with unbounded capacity and letting the queue accumulate indefinitely.
- Thinking QueueChannel automatically starts a consumer without a poller/receive.
- Using PublishSubscribeChannel when only one worker should process a message.
- Using DirectChannel when every subscriber must receive an event.
- Using ExecutorChannel while expecting handler exceptions to propagate back to the sender.
- Assuming the sender's transaction automatically propagates across ExecutorChannel.
- Failing to preserve correlationId across processing steps.
- Mutating headers/messages directly instead of creating a new message.
- Treating send returning true as proof that business processing completed.
- Treating an in-memory queue as durable and safe across restarts.

## 14. Practice Checklist

- [ ] Identified the message payload and metadata.
- [ ] Created a Message using MessageBuilder.
- [ ] Created input/output channels within the same JVM.
- [ ] Registered a MessageHandler for each step.
- [ ] Sent a message from sender to processor.
- [ ] Processor created a new message and preserved correlationId.
- [ ] Verified the processing result and send status.
- [ ] Understood that DirectChannel runs synchronously on the sender thread.
- [ ] Distinguished QueueChannel, PublishSubscribeChannel, and ExecutorChannel.
- [ ] Identified where to handle errors, retries, and deduplication.
- [ ] Decided whether in-memory channels meet durability requirements.
- [ ] Ran the program with Java 17 and Maven.

## Conclusion

An in-memory message flow can start with a MessageBuilder, pass through a DirectChannel, be processed by a MessageHandler, and then move to an output channel. MessageChannel enables the sender and processor to depend on an abstraction rather than calling each other directly. DirectChannel is suitable for synchronous dispatch; QueueChannel adds buffering and polling; PublishSubscribeChannel broadcasts; ExecutorChannel dispatches via an executor. All of them run in-process and do not automatically provide broker durability, so choose channels based on requirements for threading, errors, transactions, and recoverability.

## References

- [Spring Integration Reference - Core Messaging](https://docs.spring.io/spring-integration/reference/core.html)
- [Spring Integration Reference - Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference - Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference - Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java.html)
- [Spring Framework Reference - Messaging](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Integration 7.1 Requirements](https://docs.spring.io/spring-integration/reference/preface.html)

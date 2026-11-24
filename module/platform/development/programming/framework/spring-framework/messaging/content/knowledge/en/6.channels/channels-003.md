# PollableChannel and the Pull-Based Message Retrieval Model

## Learning Objectives

After this lesson, you will be able to:

- Explain `PollableChannel` as the pull-based message retrieval contract in Spring Messaging.
- Distinguish `PollableChannel` from `SubscribableChannel` and the push model.
- Use `receive()` and `receive(timeout)` to retrieve a `Message`.
- Understand when the consumer thread blocks, how timeouts work, and why polling does not automatically mean asynchronous.
- Distinguish `PollableChannel` in Spring Framework from `QueueChannel` and pollers in Spring Integration.
- Design consumers with load control, timeout handling, error handling, and shutdown.
- Recognize the limits of in-memory queues and when a broker or durable storage is required.

## 1. What Problem Does PollableChannel Solve?

In the messaging model, a producer sends a `Message` to a channel and a consumer receives the `Message` for processing. There are two common ways to organize the receiving side:

- **Push:** the consumer registers a handler; the channel actively invokes the handler when a message arrives.
- **Pull or polling:** the consumer actively requests the channel to return a message by calling `receive()`.

`PollableChannel` is Spring Messaging's contract for the second style of receiving. The consumer controls when to call `receive`, and can choose to wait for a message or wait for a specified duration.

This model is useful when the consumer wants to actively regulate its processing pace, run a message-receiving loop, or have a polling endpoint periodically check the channel. The producer does not need to know when the consumer calls `receive`; the producer simply sends a `Message` according to the `MessageChannel` contract.

One point to distinguish from the start: `PollableChannel` is an interface describing how messages are received. It does not dictate whether data is stored in RAM, a database, or a broker. Storage mechanisms, queue limits, behavior when the channel is full, and recovery capabilities depend on the specific implementation.

## 2. Where PollableChannel Fits in Spring Messaging

`PollableChannel` belongs to the `org.springframework.messaging` package. It extends `MessageChannel` and adds two receive methods:

- `receive()`: retrieves a `Message`, potentially waiting until a message is available.
- `receive(timeout)`: retrieves a `Message` and waits at most the specified duration, measured in milliseconds.

Conceptual model:

~~~mermaid
flowchart TB
    P["Producer"]
    C["MessageChannel"]
    PC["PollableChannel"]
    SC["SubscribableChannel"]
    Q["Queue or storage<br/>determined by implementation"]
    R["Consumer calls receive()"]
    H["Registered MessageHandler"]

    P --> C
    C --> PC
    C --> SC
    PC --> Q
    R --> PC
    SC --> H
~~~

The diagram highlights the two different receiving styles. A concrete implementation may provide its own buffering and dispatch mechanism; looking at the interface alone does not reveal the full operational behavior.

In Spring Framework, `PollableChannel` is the foundational API. A familiar implementation is Spring Integration's `QueueChannel`. `QueueChannel` resides in the Spring Integration module, not as a class available solely from the `spring-messaging` dependency.

## 3. Two receive() Methods

### 3.1. receive() — Waiting Until a Message Arrives

The `receive()` contract allows the consumer to retrieve a `Message` and wait if none is available yet. With a typical queue-based implementation, the thread calling `receive()` blocks until a `Message` arrives or the implementation terminates the operation according to its own policy.

Illustrative example:

~~~java
Message<?> message = channel.receive();

if (message != null) {
    process(message);
}
~~~

Because `receive()` may wait indefinitely, use it only when the consumer lifecycle is clearly managed. The application must have a way to stop the thread, handle interrupts, and release resources on shutdown.

### 3.2. receive(timeout) — Limiting Wait Time

The `receive(timeout)` method takes a timeout in milliseconds. If no `Message` arrives within the wait period, a pollable implementation typically returns `null`.

~~~java
Message<?> message = channel.receive(1_000);

if (message == null) {
    System.out.println("No message before timeout");
}
else {
    process(message);
}
~~~

The timeout lets the consumer periodically check other conditions, such as shutdown state, maintenance schedules, or metrics. It also avoids holding the thread in an unbounded wait state.

Distinguish the receive timeout from payload processing time. `receive(1_000)` limits how long to wait to retrieve a `Message`; it does not automatically limit how long `process(message)` is allowed to run. If business processing requires a timeout, set a separate timeout for I/O or the business operation.

### 3.3. Return Value Is a Message

`PollableChannel` returns `Message<?>` so the consumer has both payload and headers. The consumer can read:

~~~java
Object payload = message.getPayload();
Object correlationId = message.getHeaders().get("correlationId");
~~~

If you want to work directly with a specific payload type, check the data type or use an appropriate converter/template. Do not assume every `Message` in a channel has the same payload type if producers do not enforce a consistent schema.

## 4. How the Pull Flow Works

In the pull model, the consumer actively asks the channel whether a message is available. If the channel has a `Message`, the consumer receives one `Message` and processes it. If not, the consumer may wait or come back later depending on how `receive` is called.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as PollableChannel
    participant C as Consumer thread

    C->>Q: receive(timeout)
    Note over C,Q: Consumer actively pulls messages
    P->>Q: send(message)
    Q-->>C: Return Message
    C->>C: Process payload and headers
    C->>Q: Next receive(timeout)
    Q-->>C: Next Message or null on timeout
~~~

The producer does not invoke the consumer's business method directly. The consumer controls the receiving cadence and processing timing. This approach can reduce pressure on the receiving system when the consumer only wants to pull as much work as it has capacity to process.

In a point-to-point queue model, a `Message` taken from the queue is normally received by only one consumer. If multiple consumers poll concurrently, they compete for available `Message`s. This is a property of queue implementations such as `QueueChannel`, not a universal promise for every `PollableChannel` implementation.

## 5. Polling Does Not Mean Asynchronous

These two concepts describe two different axes:

- **Pull/push:** whether the consumer actively pulls the `Message` or the channel actively invokes a handler.
- **Synchronous/asynchronous:** whether the producer and consumer must wait for each other in the same execution flow.

Examples:

| Receiving approach | Thread and timing | Notes |
|---|---|---|
| PollableChannel.receive() on a separate thread | Consumer waits and processes independently of the producer | Commonly used in background processing |
| PollableChannel.receive() directly on the sending thread | That thread must wait for a Message in its own control flow | Can create synchronous waiting behavior |
| SubscribableChannel invoking handler directly | Handler may run immediately on the thread calling send | Push, yet synchronous processing |
| SubscribableChannel dispatching via executor | Handler runs later on a worker thread | Push, and typically asynchronous |

Therefore, do not conclude that using `PollableChannel` automatically makes the system asynchronous. A consumer can poll on the same thread as the producer, or run on a separate thread. What determines this is how execution threads are organized.

## 6. QueueChannel: A Common Pollable Implementation in Spring Integration

`QueueChannel` is a `PollableChannel` implementation from Spring Integration. It stores `Message`s in a queue for producers to send into and consumers to pull via `receive`.

Key points to understand:

- `QueueChannel` belongs to the `org.springframework.integration.channel` package.
- It implements Spring Messaging's `PollableChannel` contract.
- `Message`s are stored in a queue and removed when a consumer calls `receive`.
- A finite capacity can be configured to limit the number of queued `Message`s.
- With multiple consumers, consumers compete to pull `Message`s from the queue according to the implementation's semantics.
- `QueueChannel` is an in-memory storage mechanism by default; do not treat it as a durable broker.

Example of creating a queue with bounded capacity:

~~~java
QueueChannel channel = new QueueChannel(100);
~~~

The number `100` is the configured capacity for the queue in this example. In a real application, choose capacity based on producer rate, consumer rate, `Message` size, and memory budget.

### 6.1. When the Queue Is Full

If a queue is bounded and the producer sends faster than consumers receive, the queue can fill up. At that point, sending may wait, time out, or fail to be accepted depending on the implementation and the send operation's timeout.

Do not ignore the `boolean` result of `send`. If `send` returns `false`, the producer needs an appropriate policy: record an error, perform bounded retries, slow down emission, or move the work to another storage mechanism.

A bounded queue establishes a memory limit and expresses back-pressure at the send boundary. However, merely setting a capacity does not automatically create a complete back-pressure strategy; the application must still decide how to react when the queue is full.

### 6.2. QueueChannel Is Not a Durable Broker

`QueueChannel` stores `Message`s in the application's memory. If the process stops unexpectedly, unprocessed `Message`s can be lost. It does not inherently provide replication, persistence across restarts, broker acknowledgments, or a dead-letter queue.

If messages must survive restarts or be transferred across multiple processes, use an appropriate adapter/broker such as JMS, AMQP, or Kafka and understand that technology's guarantees.

## 7. Runnable Java 17 Example with QueueChannel

The example below uses Spring Integration's `QueueChannel` to demonstrate how a producer sends and a consumer actively pulls a `Message` using `receive(timeout)`. The program also demonstrates the `null` result when the queue has no messages left.

### 7.1. Maven Configuration

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>pollable-channel-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.0</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `spring-integration-core` dependency pulls in a compatible `spring-messaging`. If an application only needs the `PollableChannel` interface to integrate with another implementation, use the dependency that matches the actual integration rather than adding Spring Integration solely for an interface already in Spring Messaging.

### 7.2. Complete Program

Create `src/main/java/demo/PollableChannelDemo.java`:

~~~java
package demo;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class PollableChannelDemo {

    public static void main(String[] args) {
        QueueChannel channel = new QueueChannel(10);

        Message<String> outbound = MessageBuilder
                .withPayload("ORD-74")
                .setHeader("eventType", "order.created")
                .build();

        boolean accepted = channel.send(outbound);
        System.out.println("sendAccepted=" + accepted);

        // Consumer actively pulls a Message and waits at most 1 second.
        Message<?> received = channel.receive(1_000);

        if (received == null) {
            System.out.println("receivedPayload=null");
        }
        else {
            System.out.println("receivedPayload=" + received.getPayload());
            System.out.println(
                    "eventType=" + received.getHeaders().get("eventType")
            );
        }

        // Queue is now empty; this receive times out and returns null.
        Message<?> secondReceive = channel.receive(100);
        System.out.println(
                "secondReceive=" + (secondReceive == null ? "null" : "message")
        );
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.PollableChannelDemo
~~~

Stdout:

~~~text
sendAccepted=true
receivedPayload=ORD-74
eventType=order.created
secondReceive=null
~~~

### 7.3. Analyzing the Output

The producer creates a `Message` with payload `ORD-74` and header `eventType`, then sends it to `QueueChannel`. `send` returns `true` because the queue accepts the `Message`.

The consumer calls `receive(1_000)`, actively requesting a `Message` and waiting at most one second. The `Message` is removed from the queue, so the consumer reads the payload and header.

On the next `receive`, there is no `Message` left to retrieve. After waiting 100 milliseconds, `QueueChannel` returns `null`. The consumer can use this result to loop back, check a stop flag, or perform other periodic work.

The example runs the producer and consumer on the same thread to keep stdout deterministic. In a real application, the producer and consumer usually have separate threads or components. Using `QueueChannel` does not automatically spawn a consumer thread; the application or a polling endpoint must call `receive`.

## 8. Consumer Polling on a Separate Thread

A background consumer can run a message-receiving loop. Using a finite timeout gives the thread an opportunity to check the shutdown state instead of waiting indefinitely:

~~~java
while (running && !Thread.currentThread().isInterrupted()) {
    Message<?> message = channel.receive(1_000);

    if (message == null) {
        continue;
    }

    try {
        process(message);
    }
    catch (RuntimeException ex) {
        handleFailure(message, ex);
    }
}
~~~

This is illustrative code; the variables `running`, `process`, and `handleFailure` must be defined by the application. In a real deployment, keep in mind:

- Do not swallow exceptions without logging or recording metrics.
- Decide whether a failed `Message` will be retried, sent to an error store, or discarded.
- Have a mechanism to stop the thread and wait for the consumer to finish during application shutdown.
- Do not run many long-blocking tasks on the same polling thread if high throughput is needed.
- If using multiple consumer threads, verify the thread safety of the handler and business resources.

If `receive()` blocks indefinitely, stopping the thread may depend on the implementation's interrupt handling. A finite timeout usually makes the lifecycle easier to control.

## 9. Poller in Spring Integration

Spring Integration has the concept of a poller to automatically call `receive` on a `PollableChannel` on a schedule. That way, the application does not have to write a manual polling loop for every endpoint.

Illustrative annotation configuration example:

~~~java
@Configuration
@EnableIntegration
public class MessagingConfiguration {

    @Bean
    public QueueChannel ordersChannel() {
        return new QueueChannel(100);
    }

    @Bean
    @ServiceActivator(
            inputChannel = "ordersChannel",
            poller = @Poller(
                    fixedDelay = "1000",
                    maxMessagesPerPoll = "10"
            )
    )
    public MessageHandler orderHandler() {
        return message -> System.out.println(
                "Handling order: " + message.getPayload()
        );
    }
}
~~~

In the example:

- `QueueChannel` stores `Message`s for the consumer to retrieve later.
- The service activator registers processing logic for the input channel.
- The poller triggers the endpoint on a fixed delay of one second.
- `maxMessagesPerPoll` limits the number of `Message`s processed in a single polling cycle as configured.

This is a Spring Integration configuration. Annotations and endpoints such as `EnableIntegration`, `ServiceActivator`, and `Poller` do not belong to the `spring-messaging` module itself.

### 9.1. Polling Interval and Receive Timeout Are Different

Two values that are often confused:

- **Polling interval/fixed delay:** the duration the scheduler waits between configured poller triggers.
- **Receive timeout:** the duration a single `receive` call may wait for a `Message`.

For example, a poller runs every second and each `receive` waits at most 200 milliseconds. The consumer may wait at most 200 milliseconds during that receive attempt; the poller schedule determines when the endpoint is triggered next.

Do not set a very long receive timeout without considering the scheduler thread pool, because a long-blocking poll can occupy a scheduler thread. Choose the interval, timeout, and messages per cycle based on actual load.

### 9.2. maxMessagesPerPoll and Processing Throughput

`maxMessagesPerPoll` limits the number of `Message`s received in a single poll. A low value helps each cycle yield time for other work; a high value can increase throughput but makes each cycle last longer.

You need to balance:

- The rate at which producers put `Message`s into the channel.
- The average duration and variance of the handler.
- The number of consumers or polling endpoints.
- Queue capacity and memory budget.
- The latency acceptable to the business.

## 10. Multiple Consumers Polling Concurrently

With a point-to-point `QueueChannel`, multiple consumers can call `receive` on the same queue. When a `Message` is retrieved by one consumer, other consumers do not receive that same `Message` from the queue.

This fits the competing consumers pattern: increase the number of consumers to share the processing load.

However, note the following:

- Processing start order and completion order may differ when multiple consumers run in parallel.
- One slow consumer may hold a `Message` for a long time, while another consumer continues pulling newer `Message`s.
- If `Message`s update the same order, race conditions or business ordering errors can occur.
- Key-based partitioning, data locking, or serialized processing is needed when ordering is a strict requirement.

If you need to broadcast the same `Message` to multiple subscribers, use an appropriate publish-subscribe model. Do not use `QueueChannel` expecting every consumer to receive a copy of every `Message`.

## 11. Error Handling, Retries, and Durability

`PollableChannel` only defines how to retrieve `Message`s. It does not automatically guarantee error-handling policies or durable storage.

When a consumer retrieves a `Message` and fails to process it, the application must decide:

- Should it retry immediately?
- Should it retry with backoff or a maximum attempt limit?
- Should it route the `Message` to an error channel or a dead-letter queue?
- Should it record state to recover after a restart?
- How do you prevent executing business logic twice if the `Message` is redelivered?

With an in-memory `QueueChannel`, once `receive` removes a `Message`, the application must not assume the `Message` will automatically return to the queue if the handler fails. If redelivery or rollback is needed, you must design transactions, an error flow, or an appropriate storage-backed adapter.

With an external broker, acknowledgment, redelivery, visibility timeout, offset commit, and dead-letter handling have their own semantics. Rely on the documentation of the respective broker and Spring integration.

A consumer should process idempotently whenever retries are possible: repeated processing of the same `Message` does not produce incorrect or duplicate business side effects.

## 12. Observability and Load Throttling

Polling produces several signals that should be monitored:

- **Queue depth:** number of waiting `Message`s.
- **Wait time:** how long a `Message` stays in the queue before being received.
- **Processing time:** how long the handler takes to process each `Message`.
- **Poll frequency:** number of polls within a time window.
- **Empty poll count:** number of `receive` timeouts without a `Message`.
- **Failure/retry count:** number of errors and retry attempts.
- **Rejection/send timeout:** number of times the producer could not place a `Message` into the channel.

If queue depth grows continuously, producers are generating load faster than consumption capacity. Increasing the number of workers can help, but check databases, external APIs, CPU, and downstream resources behind the consumer to avoid shifting the bottleneck elsewhere.

A bounded queue helps cap memory usage. When the queue approaches capacity, the application can throttle producers, reject new work, or persist requests to durable storage for later processing.

## 13. When Should You Use PollableChannel?

| Requirement | Is PollableChannel suitable? | Recommendation |
|---|---|---|
| Consumer wants to decide when to receive | Yes | Use receive or a polling endpoint |
| Consumer needs to control the number of Messages processed per batch | Yes | Combine a poller or a bounded loop |
| Need competing workers pulling Messages from a queue | Yes, depending on implementation | QueueChannel is a point-to-point example |
| Need to push Messages immediately to registered handlers | Another mechanism may fit better | See SubscribableChannel |
| Need to broadcast to all subscribers | Should not be assumed from PollableChannel | Use publish-subscribe |
| Need to persist Messages across restarts or across machines | The interface alone is not enough | Use an appropriate broker or MessageStore |
| Need asynchronous processing | Possible | Run the consumer on a separate thread or use a poller |
| Need an immediate response for the current request | Depends on the problem | See request-reply or a synchronous API |

`PollableChannel` fits when the consumer needs to pull and regulate its receiving rate. If you need a durable broker, broadcast, or specific delivery guarantees, choose the corresponding integration.

## 14. Common Mistakes

1. **Assuming PollableChannel stores messages by itself:** the interface does not define storage; the implementation decides.
2. **Assuming PollableChannel is always asynchronous:** `receive` can run on the producer's thread or the caller's thread.
3. **Using unbounded `receive()` without a shutdown strategy:** the consumer can remain stuck waiting when the application needs to stop.
4. **Confusing receive timeout with processing time:** the timeout only limits waiting to retrieve the `Message`.
5. **Not checking for null:** `receive(timeout)` can return `null` when the wait time expires.
6. **Ignoring the result of `send`:** a full queue or rejecting channel can cause a `Message` not to be accepted.
7. **Using an unbounded queue:** increasing load can cause memory to grow continuously.
8. **Expecting `QueueChannel` to provide durability:** an in-memory queue does not replace a persistent broker.
9. **Assuming multiple consumers all receive the same Message:** a point-to-point queue normally delivers each `Message` to the one consumer that pulls it.
10. **Not controlling ordering:** multiple consumers can finish `Message`s out of emission order.
11. **Handling an error and dropping the Message without recording it:** you need retries, an error flow, or an intentional drop policy.
12. **Confusing `PollableChannel` with `QueueChannel`:** `PollableChannel` is Spring Messaging's contract; `QueueChannel` is Spring Integration's implementation.

## 15. Self-Check Questions

1. How does `PollableChannel` differ from `SubscribableChannel` in how consumers receive a `Message`?
2. How does `receive()` differ from `receive(timeout)` in waiting behavior?
3. What is the timeout unit of `receive(timeout)`?
4. Why can `receive(timeout)` return `null`?
5. Does polling always mean asynchronous?
6. Which module does `QueueChannel` belong to, and which contract does it implement?
7. What happens when multiple consumers poll the same `QueueChannel` concurrently?
8. Why does an in-memory `QueueChannel` not satisfy durable delivery requirements?
9. How does the polling interval differ from the receive timeout?
10. When a consumer encounters a processing error after removing a `Message` from the queue, what mechanisms should be designed?

## 16. Conclusion

`PollableChannel` is the pull-based `Message` receiving contract in Spring Messaging. Consumers actively call `receive()` or `receive(timeout)`, control when data is pulled, and can limit wait times. This receiving style is useful when you want to regulate consumer pace or organize batch-by-batch processing.

`PollableChannel` does not dictate storage mechanisms or durability. Spring Integration's `QueueChannel` is a common queue-based implementation, while Spring Integration's poller triggers scheduled receives. When implementing, clearly distinguish the interface, implementation, and broker infrastructure; also manage timeouts, queue capacity, concurrency, shutdown, and error handling.

## Official References

- Spring Framework PollableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html
- Spring Framework MessageChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html
- Spring Framework SubscribableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html
- Spring Integration channel reference: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration QueueChannel API: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html
- Spring Integration endpoint and poller reference: https://docs.spring.io/spring-integration/reference/endpoint.html

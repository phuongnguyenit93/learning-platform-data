# Synchronous and Asynchronous Processing from Sender and Receiver Perspectives

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between synchronous and asynchronous processing in a messaging flow.
- Explain what happens on the sender's thread when calling MessageChannel.send().
- Determine which thread a handler runs on and whether the receiver actively pulls or receives messages pushed by the channel.
- Distinguish between an accepted send and completed business processing.
- Choose an appropriate exchange style when you need request-reply, background processing, timeouts, retries, or load control.
- Read the behavior of channels in Spring Framework and avoid confusing them with Spring Integration channels.

## 1. What Are Synchronous and Asynchronous Processing About?

In messaging, the sender (producer) creates and sends messages; the receiver (consumer) receives and processes them. Synchronous and asynchronous describe how both sides coordinate execution timing, waiting time, and threads.

**Synchronous** typically means the send call does not return until the invoked processing on the same execution flow completes. The sender waits for the receiver on the same call stack. If the handler processes slowly, the sending thread is also held up.

**Asynchronous** typically means the sender hands the message off to an intermediary mechanism such as an executor, queue, or broker, and can continue before the handler finishes. The receiver processes it later, usually on a different thread or even in a different process.

An important point is that the word “synchronous” can be used to describe several different boundaries:

1. **Synchronous at the send call:** does send wait for the handler to finish running, or only wait for the channel to accept the message?
2. **Synchronous at the business level:** does the sender wait for a business result or response from the consumer?
3. **Synchronous at the thread level:** do the producer and handler run on the same thread or not?
4. **Synchronous at the transport level:** does the client wait for the broker to acknowledge receiving or storing the message?

These four aspects are related, but not synonymous. A producer may wait for a broker to acknowledge publishing, while the consumer processes asynchronously afterward. A send call may return quickly after an executor accepts the task, but that does not indicate that business processing is complete.

## 2. Two Roles: Sender and Receiver

### 2.1. From the Sender's Perspective

The sender cares about when it is allowed to continue.

- **Synchronous send to a synchronous handler:** the producer calls send; the handler runs on the current call stack; send returns only after the handler finishes or throws an error.
- **Sending through a channel with an executor:** the producer calls send; the channel hands the task to the executor; send typically returns after the task is accepted or scheduled. The handler may run later on a worker thread.
- **Sending to a broker from an adapter:** the producer sends through an adapter. The adapter may wait for broker acknowledgment, wait for a socket write, or only hand off to an internal client. You need to check the specific contract of the adapter and broker.
- **Producer offloading the send call itself:** the application puts the entire send operation onto a separate executor. The original request thread can continue, though the send call itself may still block the worker thread until the channel accepts the message.

Therefore, “asynchronous send” needs to specify where it is asynchronous: the application offloading the send operation, the channel dispatching the handler via an executor, or the adapter/broker processing over the network.

### 2.2. From the Receiver's Perspective

The receiver cares about how messages reach it and which thread performs the work.

- **Push-based receiving:** the consumer registers a MessageHandler. The channel actively invokes the handler when a message arrives. SubscribableChannel is a contract of this kind.
- **Pull/poll-based receiving:** the consumer actively calls receive() to retrieve a message. PollableChannel is a contract of this kind. The receive call may return immediately, wait up to a timeout, or wait according to the channel configuration.
- **Receiving via an executor:** the channel or adapter moves processing onto a worker thread. The consumer does not need to call receive directly for each message.
- **Receiving via a broker:** the consumer runs independently of the producer, possibly in another process or on another machine. Threads, consumer concurrency, partitioning, and acknowledgment behavior depend on the integration and the broker.

Push/pull describes how the consumer receives messages. Synchronous/asynchronous describes how the parties wait on each other. These two axes should not be conflated into a single concept.

## 3. What Happens in Spring Messaging?

spring-messaging provides foundational contracts such as Message, MessageChannel, SubscribableChannel, PollableChannel, and MessageHandler. The MessageChannel contract defines the send method, but the interface itself does not force every implementation to run synchronously or asynchronously.

Two common receiving interfaces:

| Contract | How the consumer receives | Meaning |
|---|---|---|
| SubscribableChannel | Register a MessageHandler using subscribe() | The channel pushes messages to the handler |
| PollableChannel | Call receive() or receive(timeout) | The consumer actively pulls messages |

Several implementations in Spring Framework clarify the differences:

- **ExecutorSubscribableChannel without an Executor:** invokes the handler directly on the thread calling send. With a normal handler, send does not finish before the handler returns.
- **ExecutorSubscribableChannel with an Executor:** the channel delegates invoking the handler to the Executor. With a typical thread pool, the handler runs on a worker thread and the producer can continue once the task is accepted.
- **ExecutorSubscribableChannel with a direct executor:** even though the constructor accepts an Executor, the executor can run the Runnable immediately on the calling thread. Therefore, the mere presence of an Executor does not prove asynchronous processing.

A channel's contract only tells you its send/receive capabilities. Actual dispatching, buffering, load limits, error handling, and threading must be determined from the specific implementation and configuration in use.

## 4. Synchronous Flow: Producer Waits for Handler

When using a SubscribableChannel where the handler is invoked directly, the sequence is typically:

~~~mermaid
sequenceDiagram
    participant P as Producer thread
    participant C as SubscribableChannel
    participant H as MessageHandler

    P->>C: send(message)
    C->>H: handleMessage(message)
    Note over P,H: Handler runs on the same thread/call stack
    H-->>C: Return
    C-->>P: send returns
    Note over P: Producer continues
~~~

Consequences:

- A slow-running handler prolongs the send duration.
- If the handler blocks on synchronous I/O, the producer thread is also held.
- In the in-process case, an exception from the handler can affect the send call; the final error propagation depends on the channel and error-handling configuration.
- There is no executor queue in between to absorb a large volume of work.
- Returning from the handler only indicates that the handler call finished. By itself, it does not prove that data was durably committed in an external system.

This model fits when immediate processing on the same flow is needed, a simple control flow is desired, and processing does not need to be decoupled from the send call. It can also be useful in tests because execution order is easy to observe.

## 5. Asynchronous Flow: Producer Hands Off and Continues

When a channel dispatches the handler through an executor, the sequence is typically:

~~~mermaid
sequenceDiagram
    participant P as Producer thread
    participant C as SubscribableChannel
    participant E as Executor
    participant W as Worker thread
    participant H as MessageHandler

    P->>C: send(message)
    C->>E: submit task to invoke handler
    E-->>C: Task accepted
    C-->>P: send returns
    Note over P: Producer continues other work
    E->>W: Run task on worker
    W->>H: handleMessage(message)
    H-->>W: Processing complete
~~~

Consequences:

- The producer usually does not have to wait for the handler to finish processing.
- The handler runs on a thread provided by the Executor, typically a worker thread.
- send returns faster when handler processing takes a long time, though there is still wrapping and dispatch overhead.
- Errors occurring after the producer has continued cannot be thrown back up the old call stack in the usual way.
- If the executor has a queue, work may wait in the queue before the handler starts.
- If the executor rejects the task, send may fail or throw an exception depending on the implementation and rejection policy.

Asynchrony reduces the producer's waiting time, but does not make the work disappear. Processing load still requires thread resources, memory, queues, and concurrency limits.

## 6. Java Example: Comparing Sender and Receiver Threads

The example below uses spring-messaging directly. It creates two SubscribableChannels:

1. An ExecutorSubscribableChannel without an Executor to demonstrate the handler running on the sending thread.
2. An ExecutorSubscribableChannel using a single-thread Executor to demonstrate the handler running on a worker thread.

### 6.1. Maven Configuration

The example uses Java 17 and Spring Framework 6.2.8. The Spring Framework BOM keeps dependency versions aligned:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>sync-async-messaging</artifactId>
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
                <version>6.2.8</version>
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

### 6.2. Complete Program

Create the file src/main/java/demo/SyncAsyncMessagingDemo.java:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SyncAsyncMessagingDemo {

    public static void main(String[] args) throws InterruptedException {
        runSynchronousExample();
        runAsynchronousExample();
    }

    private static void runSynchronousExample() {
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        channel.subscribe(message ->
                System.out.println(
                        "sync.receiverThread=" + Thread.currentThread().getName()
                )
        );

        System.out.println(
                "sync.senderThread=" + Thread.currentThread().getName()
        );

        boolean accepted = channel.send(createMessage("sync"));
        System.out.println("sync.sendReturned=" + accepted);
    }

    private static void runAsynchronousExample() throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "messaging-worker")
        );

        CountDownLatch allowHandler = new CountDownLatch(1);
        CountDownLatch handled = new CountDownLatch(1);

        try {
            SubscribableChannel channel =
                    new ExecutorSubscribableChannel(executor);

            channel.subscribe(message -> {
                try {
                    if (!allowHandler.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Timed out waiting for the sender"
                        );
                    }

                    System.out.println(
                            "async.receiverThread="
                                    + Thread.currentThread().getName()
                    );
                }
                catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
                finally {
                    handled.countDown();
                }
            });

            System.out.println(
                    "async.senderThread=" + Thread.currentThread().getName()
            );

            boolean accepted = channel.send(createMessage("async"));
            System.out.println("async.sendReturned=" + accepted);

            // Only allow the handler to run after the sender has printed the send result.
            allowHandler.countDown();

            if (!handled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Handler did not complete in time"
                );
            }
        }
        finally {
            allowHandler.countDown();
            executor.shutdown();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }

    private static Message<String> createMessage(String payload) {
        return MessageBuilder.withPayload(payload).build();
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.SyncAsyncMessagingDemo
~~~

Stdout:

~~~text
sync.senderThread=main
sync.receiverThread=main
sync.sendReturned=true
async.senderThread=main
async.sendReturned=true
async.receiverThread=messaging-worker
~~~

### 6.3. Reading the Output

In the synchronous example, both sender and receiver run on the main thread. The handler is invoked inside the send call, so the sync.receiverThread line appears before sync.sendReturned.

In the asynchronous example, the channel uses an ExecutorService. send hands the work off to the executor and returns true. The program prints async.sendReturned before opening the latch for the handler to proceed. The handler then runs on the messaging-worker thread.

CountDownLatch here only keeps the demonstration output in a deterministic order. In real applications, do not use a latch to coordinate every message. Use synchronization appropriate for your business needs, or design dedicated response/acknowledgement mechanisms.

A result of true indicates that the channel accepted the message according to the implementation's contract. It does not mean that all business processing has completed or that data has been durably stored.

## 7. Consumer Actively Pulling: PollableChannel

SubscribableChannel is a push model: the consumer registers a handler and the channel invokes it when a message arrives.

PollableChannel is a pull model: the consumer actively calls receive:

~~~java
Message<?> message = channel.receive();
~~~

Or wait at most for a given duration:

~~~java
Message<?> message = channel.receive(1_000);
~~~

With pull-based receiving, the consumer decides when to take a message. A receive call may return null when the timeout expires without a message. How the channel stores messages, enforces queue limits, and behaves on send when full depends on the implementation.

A consumer loop might look like:

~~~java
while (running) {
    Message<?> message = channel.receive(1_000);

    if (message == null) {
        continue;
    }

    process(message);
}
~~~

This code illustrates the polling idea; in a real application you must add shutdown, interrupt, timeout, exception, and processing-time limit handling.

Pull does not automatically mean asynchronous. If the producer calls send and the receiver calls receive on separate threads, the two sides are decoupled in execution time. However, if the same thread sequentially calls send and then receive, the program can still block synchronously. Likewise, push does not automatically mean asynchronous: a SubscribableChannel can invoke the handler directly on the sending thread.

## 8. Request-Reply: Sending Asynchronously While Still Needing an Answer

Many systems send a command and need to receive a result. This is request-reply, which differs from publishing a one-way event.

There are two common coordination patterns:

**Synchronous request-reply**

1. The producer sends a request.
2. The producer waits for a reply on the reply channel.
3. The consumer processes it and sends a corresponding response.
4. The producer continues upon receiving the reply or when the timeout expires.

Spring Messaging provides `GenericMessagingTemplate` in `org.springframework.messaging.core`, with the `sendAndReceive` API for suitable scenarios. This call style can block waiting for a response; timeouts must be configured and handled explicitly.

**Asynchronous request-reply**

1. The producer sends a request carrying a request ID or correlation ID.
2. The producer continues with other work.
3. The consumer processes the request and sends a response carrying the matching correlation ID.
4. A pending-request manager matches the response with the original request.
5. The result is delivered to a callback, future, reactive publisher, or the application's response mechanism.

Asynchrony does not eliminate the need for timeout management. The producer still needs to know what to do when no reply arrives, a reply arrives late, or a duplicate reply arrives.

### Events and Commands Are Not the Same

- **Event:** announces that something has happened, such as OrderCreated. The producer usually does not wait for a specific consumer to reply.
- **Command:** requests an action, such as ReserveInventory. The producer may need an acknowledgement or result.
- **Request-reply:** the producer sends a request and expects a corresponding response.

Choosing the right semantics prevents using a one-way event when the business process actually requires a confirmation result.

## 9. Timeouts, Errors, and Processing Guarantees

### 9.1. Timeouts on the Sender Side

Timeouts can occur when:

- Sending through a channel with a wait timeout.
- The executor or queue is overloaded.
- An adapter waits for broker acknowledgment.
- A request-reply waits for a response.
- The producer calls an external service while constructing or sending a message.

A timeout does not always mean the operation did not happen. For example, the producer may time out waiting for a response while the consumer has already received and finished processing it. If the producer retries immediately without idempotency, the business action may be executed twice.

### 9.2. Errors on the Receiver Side

With synchronous processing on the same call stack, errors from the handler can propagate back to the send call depending on the implementation and configuration.

With asynchronous processing, the producer may have already received the send result before the handler fails. In that case, errors must be observed and handled on the consumer side or intermediate infrastructure. Depending on the architecture, mechanisms may include:

- Error handler or error channel.
- Bounded retries with backoff.
- Dead-letter queue or dead-letter topic supported by the broker/integration.
- Recording processing state to enable recovery.
- Idempotency keys to prevent duplicate processing.

spring-messaging provides message and channel abstractions; it does not automatically provide complete retry, dead-letter, transaction, or durable delivery support for every implementation.

### 9.3. Accepted Send Does Not Mean Successful Processing

MessageChannel.send returns a boolean. This value indicates whether the send was accepted by the channel according to the channel's contract.

Do not interpret send=true as any of the following conclusions:

- The consumer has started processing.
- The consumer has finished processing.
- The business transaction has committed.
- The broker has durably persisted the message.
- The message will never be lost or processed more than once.

To obtain those guarantees, you must examine the specific channel/adapter/broker, transactions, acknowledgements, persistence, and retry policies.

## 10. Concurrency, Ordering, and Load Control

When using an executor for asynchronous processing, multiple handlers can run concurrently. This increases throughput but introduces new issues:

- **Race condition:** multiple handlers update the same state or resource concurrently.
- **Ordering:** a message arriving earlier may finish after a message arriving later.
- **Thread safety:** shared services, caches, or objects must be safe for concurrent access.
- **Queue growth:** the producer sends faster than consumers can process, causing the queue to grow and consume memory.
- **Rejection:** the executor rejects tasks when overloaded or already shut down.
- **Shutdown:** the application must decide whether to wait for running tasks, drain the queue, or stop immediately.

Some design measures:

1. Use a thread pool with appropriate size and queue capacity.
2. Define a clear rejection policy; do not let overload turn into silent message loss.
3. Set timeouts for I/O operations and request-reply.
4. Use a correlation ID to trace a processing flow across multiple components.
5. Use an idempotency key for business operations that can be resent.
6. If ordering matters, partition by business key or serialize processing within the required scope.
7. Measure queue depth, wait time, processing time, error counts, and retry counts.
8. Avoid using an unbounded executor for work that can spike.

### Ordering Example

Suppose an order emits two messages in order:

1. OrderCreated
2. OrderPaid

If the two handlers run on two different workers, the handler processing OrderPaid may complete before OrderCreated. If business logic requires ordering, design an ordering mechanism instead of relying on send timing.

## 11. Spring Integration Channels and Module Boundaries

Several channel names frequently appear in Spring documentation:

| Channel | Module | Typical Behavior |
|---|---|---|
| ExecutorSubscribableChannel | Spring Framework, spring-messaging | Pushes to subscribers; can dispatch via an Executor |
| DirectChannel | Spring Integration | Typically invokes the handler synchronously on the sending thread |
| ExecutorChannel | Spring Integration | Uses a TaskExecutor to dispatch handlers |
| QueueChannel | Spring Integration | Buffers messages for consumers to retrieve via polling |
| PublishSubscribeChannel | Spring Integration | Broadcasts messages to subscribers |

This table clarifies API boundaries. DirectChannel, ExecutorChannel, and QueueChannel are implementations from Spring Integration; do not assume they are all provided solely by the spring-messaging dependency.

Similarly, a broker such as Kafka or RabbitMQ has its own consumer threads, acknowledgements, partitions/queues, and semantics. These properties cannot be inferred solely from the name MessageChannel.

## 12. When to Choose Synchronous vs. Asynchronous?

| Scenario | Suitable Direction | Reason |
|---|---|---|
| Need an immediate result to complete the current request | Synchronous or request-reply | Caller needs the response before continuing |
| Lightweight handler, in-process, needing simple control flow | Synchronous | Easy to follow the call stack and errors |
| Long-running work where the user does not need to wait | Asynchronous | Can return an early response and process in the background |
| Need fan-out to multiple independent components | Asynchronous messaging or pub/sub | Producer is decoupled from each consumer |
| Consumer needs to actively pace its processing rate | Pull/poll | Consumer controls the rate at which it fetches data |
| Need communication across multiple processes or machines | Appropriate broker/transport | Requires infrastructure to transport and manage messages |
| Operation must have business confirmation | Request-reply or acknowledgement | Send acceptance is not a business result |

Neither choice is always better. Synchronous is simpler when the caller truly needs an immediate result. Asynchronous fits when you want to decouple processing time, absorb load, or connect independent components, at the cost of additional observability, timeout, retry, and recovery mechanisms.

## 13. Common Mistakes

1. **Assuming every MessageChannel is asynchronous:** the interface does not mandate that; the implementation decides how dispatching works.
2. **Assuming having an Executor guarantees running on another thread:** a direct executor can execute immediately on the calling thread.
3. **Assuming send=true means the consumer has finished processing:** the boolean only reflects that the channel accepted the message.
4. **Confusing push with async:** SubscribableChannel can invoke the handler synchronously on the sending thread.
5. **Confusing pull with sync:** a consumer polling on a separate thread can still operate independently of the producer.
6. **Putting the entire send call into an executor and thinking the channel is now async:** that is application-side offloading; the send inside the worker itself can still block.
7. **Not managing timeouts:** the producer can wait indefinitely or resend while the previous processing attempt is still running.
8. **Not handling asynchronous errors:** handler errors can occur after the producer has already continued.
9. **Not controlling concurrency:** multiple workers can update the same resource and violate business ordering.
10. **Using an unbounded queue:** when the consumer is slow, memory can grow until the application crashes.
11. **Lacking idempotency:** retries or resends after a timeout can produce duplicate business effects.
12. **Confusing Spring Integration channels with core APIs:** check the actual module and dependencies before using them.

## 14. Self-Check Questions

1. In an ExecutorSubscribableChannel without an Executor, which thread does the handler run on?
2. When a channel uses a thread pool, at what point does send typically return?
3. Why does send=true not prove that the consumer has finished processing?
4. How does SubscribableChannel differ from PollableChannel in how consumers receive messages?
5. Is push always asynchronous? Is pull always synchronous?
6. How does a producer offloading the send call to another executor differ from a channel dispatching the handler to an executor?
7. If a handler fails after send has already returned, how does the producer receive the error?
8. When should you use request-reply instead of a one-way event?
9. Why is idempotency needed when a producer retries after a timeout?
10. How can ordering be preserved when multiple workers process concurrently?

## 15. Conclusion

Synchronous and asynchronous behavior must be analyzed from both sides. The sender cares about how far it must wait; the receiver cares about whether messages are pushed to a handler or actively pulled, and which thread the handler runs on.

In Spring Messaging, MessageChannel defines only the sending contract. SubscribableChannel and PollableChannel express two receiving models, while implementations such as ExecutorSubscribableChannel decide the concrete dispatch behavior. A channel running handlers on the sending thread behaves synchronously; a channel dispatching via an executor typically lets the producer continue before the handler completes.

When designing, clearly define the completion condition required by the business process: whether the channel accepted the message, the broker acknowledged it, the consumer processed it, or a business result was returned. From there, choose synchronous, asynchronous, polling, request-reply, and appropriate timeout, retry, and ordering policies.

## Official References

- Spring Framework Messaging API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/package-summary.html
- MessageChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html
- SubscribableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html
- PollableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html
- ExecutorSubscribableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html
- Spring Integration channel reference: https://docs.spring.io/spring-integration/reference/channel.html

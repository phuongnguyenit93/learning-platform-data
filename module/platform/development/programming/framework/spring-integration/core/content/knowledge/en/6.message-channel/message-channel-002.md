# SubscribableChannel

## 1. Objectives and Use Cases

In Spring Integration Core, a message channel connects the message producer with processing components such as transformers, filters, routers, and service activators. When a component needs to be invoked immediately when a message arrives, the handler subscription model of `SubscribableChannel` is a foundational mechanism.

Consider an order intake system:

- An order command needs to be accepted by a processor.
- After the order is accepted, multiple components need to receive the event: logging, sending notifications, updating statistics.
- A slow task may need to be offloaded to a worker thread.

All three needs can use a channel that supports subscription, but you must choose the right implementation. After this lesson, you should be able to explain handler subscription, distinguish single-destination dispatch from multi-destination broadcasting, and predict both the execution thread and the error path.

The examples use APIs from `spring-messaging` and `spring-integration-core`. When placed in a Spring Boot application, use the dependency versions managed by the project; do not arbitrarily mix Spring Framework and Spring Integration versions. The full Java classes below use Java 17+ syntax.

## 2. The SubscribableChannel Contract

### 2.1. Where Does the Interface Live?

`SubscribableChannel` belongs to the `org.springframework.messaging` package of Spring Framework. Spring Integration provides implementations for integration flows.

The core contract can be represented as follows; `send` is inherited from `MessageChannel`:

~~~java
public interface SubscribableChannel extends MessageChannel {

    boolean subscribe(MessageHandler handler);

    boolean unsubscribe(MessageHandler handler);
}
~~~

The registered handler is a `MessageHandler`:

~~~java
@FunctionalInterface
public interface MessageHandler {

    void handleMessage(Message<?> message) throws MessagingException;
}
~~~

These declarations illustrate the API contract. In an application, import the existing interfaces; do not recreate them.

`subscribe(handler)` returns `true` if the handler was registered, or `false` if that handler was already registered. `unsubscribe(handler)` returns `true` when the registration is removed, or `false` when the handler is not in the list. This is the result of changing the subscription, not the result of processing a message. See [SubscribableChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html).

`MessageHandler.handleMessage` has a `void` return type. If business logic needs a reply result, use an endpoint capable of producing a reply and a request-reply mechanism, such as a gateway; subscribing a handler does not by itself create a return value for `send`. See [MessageHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html).

### 2.2. Who Is Responsible for What?

| Component | Responsibility in the order example |
| --- | --- |
| `Message<?>` | Carries the order payload and headers such as trace ID |
| Producer or gateway | Puts the message into the channel |
| `SubscribableChannel` | Manages subscriptions and transfers messages according to the implementation's policy |
| `MessageHandler` | Performs a processing step |
| Consumer endpoint | Connects the handler to the channel and manages its lifecycle in Spring |

The producer only needs to know the target channel. The producer does not have to maintain a list of order-processing services itself.

### 2.3. How Does Push Differ from Polling?

`SubscribableChannel` provides `subscribe`; `PollableChannel` provides `receive`. With a subscribable channel, the send operation triggers dispatch to the handler. With a pollable channel, the receiving side actively pulls messages, either directly or through a Spring Integration poller. See [PollableChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html).

~~~mermaid
flowchart LR
    P["Producer"] -->|"send(message)"| C["SubscribableChannel"]
    C --> D["Dispatcher"]
    D -->|"handleMessage(message)"| H["Selected Handler"]
~~~

The diagram only describes the call relationship. An implementation may choose one handler or multiple handlers, and may delegate dispatching to an executor.

`SubscribableChannel` does not declare `receive()`. Therefore, an endpoint receiving from a `DirectChannel` does not need a poller just to receive messages from that channel. Nor should you infer from the word "subscribe" that this is Reactive Streams: this contract has no `request(n)` for demand backpressure.

## 3. Two Independent Choices: Destination and Execution Thread

### 3.1. Comparison Table of Common Implementations

| Implementation | Normal Dispatch | Thread Calling the Handler | Channel-Level Buffering |
| --- | --- | --- | --- |
| `DirectChannel` | One handler processes successfully per dispatch; failover may try another handler on error | Sender's thread | No message queue |
| `ExecutorChannel` | One handler processes successfully; supports load balancing and failover configuration | Determined by the executor, usually a worker thread | Not a `QueueChannel`; the executor may have a task queue |
| `PublishSubscribeChannel` without executor | Broadcasts to registered handlers | Sender's thread | Keeps no history for replay |
| `PublishSubscribeChannel` with executor | Broadcasts to handlers via the executor | Determined by the executor | Task queue, if any, is not a durable message store |
| `QueueChannel`, for comparison | Each `receive` takes one message | Determined by the receiver or poller | Has a queue; implements `PollableChannel` |

`DirectChannel` invokes subscribers on the sender's thread. `ExecutorChannel` delegates dispatch to an executor; that changes the execution boundary while preserving the single-destination dispatch model. See [DirectChannel Javadoc](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/DirectChannel.html) and [ExecutorChannel Javadoc](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/ExecutorChannel.html).

Thus, two questions should be answered separately when choosing a channel:

1. Does a message need a single processor or do multiple parties need to receive it?
2. Do those steps run on the current thread or need to be handed off to an executor?

### 3.2. DirectChannel with Multiple Subscribers

Two handlers subscribed to the same `DirectChannel` become competing consumers. They do not automatically form two sequential steps.

~~~mermaid
flowchart LR
    P["Order"] --> C["DirectChannel"]
    C -->|"selects one processor"| A["Worker A"]
    C -.->|"alternative choice"| B["Worker B"]
~~~

If A checks inventory and B charges payment, subscribing both to one `DirectChannel` does not create a "check then charge" workflow. Connect them as sequential endpoints instead. If A and B are two workers performing equivalent business logic, the competing model is appropriate.

### 3.3. Broadcast Is Not Necessarily Parallel

`new PublishSubscribeChannel()` invokes handlers on the sending thread. Having multiple subscribers does not automatically make them run concurrently. To delegate processing to an executor, use the constructor that takes an `Executor`. See [PublishSubscribeChannel Javadoc](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

An error in one broadcast branch can also affect other branches. With synchronous dispatch and the default `ignoreFailures=false`, an error can prevent subsequent handlers from being invoked. Treat broadcasting as a distribution policy, not a guarantee that all side effects succeed. See [BroadcastingDispatcher Javadoc](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dispatcher/BroadcastingDispatcher.html).

## 4. Practicing the Direct Subscription API

Here is a standalone program demonstrating subscribing, sending, and unsubscribing. The program requires `spring-integration-core` along with compatible Spring dependencies on the classpath.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SubscriptionDemo {

    public static void main(String[] args) {
        SubscribableChannel orders = new DirectChannel();
        List<String> received = new ArrayList<>();

        MessageHandler handler = message -> {
            String orderId = (String) message.getPayload();
            received.add(orderId);
            System.out.println(
                    orderId + " processed by "
                            + Thread.currentThread().getName());
        };

        System.out.println(orders.subscribe(handler));   // true
        System.out.println(orders.subscribe(handler));   // false

        boolean sent = orders.send(
                MessageBuilder.withPayload("ORDER-1001")
                        .setHeader("traceId", "trace-1001")
                        .build());

        System.out.println(sent);                       // true
        System.out.println(received);                   // [ORDER-1001]

        System.out.println(orders.unsubscribe(handler)); // true
        System.out.println(orders.unsubscribe(handler)); // false
    }
}
~~~

`received` already contains the element when `send` returns because the handler runs synchronously. `ArrayList` fits this single-threaded demonstration; do not extrapolate from this to share the same list across multiple workers without synchronization.

Keep a reference to the handler if you need to unsubscribe. Two identically written lambda expressions are not a reliable way to refer to the same handler:

~~~java
MessageHandler handler = message -> process(message);
channel.subscribe(handler);

// When disconnecting is needed:
channel.unsubscribe(handler);
~~~

The short snippet above assumes `channel` is a `SubscribableChannel` and `process` is an existing business method.

A subscription only applies to messages sent while the handler is connected. The direct-dispatch channels mentioned above do not retain past messages to replay for new subscribers.

## 5. Endpoints Subscribe Handlers on Behalf of the Application

In a real application, you normally declare a flow instead of calling `subscribe` manually. `EventDrivenConsumer` is the endpoint that connects a `MessageHandler` to a `SubscribableChannel`; the endpoint lifecycle manages connecting and disconnecting. See [EventDrivenConsumer Javadoc](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/endpoint/EventDrivenConsumer.html).

This helps distinguish three situations:

- Having a business bean does not mean the bean has become a subscriber.
- Declaring an `IntegrationFlow` with an input channel and a handler creates the corresponding endpoint configuration.
- An endpoint that has not started or has stopped can leave the channel without its expected subscriber.

When diagnosing a "no subscriber" error, check bean creation, channel names, and endpoint state.

## 6. Java DSL Example: Receive Command Then Broadcast Event

### 6.1. Flow Requirements

We want to:

1. Receive an `Order` into `orderInput`.
2. Reject orders with a non-positive value.
3. Transform valid orders into `OrderAccepted`.
4. Broadcast the event to two independent branches.
5. Collect each branch's result into a queue for observation and testing.

~~~mermaid
flowchart LR
    P["Producer or gateway"] --> I["orderInput: DirectChannel"]
    I --> F["Filter: totalCents > 0"]
    F --> T["Transformer: OrderAccepted"]
    T --> E["orderEvents: PublishSubscribeChannel"]
    E --> A["Audit branch"]
    E --> N["Notification branch"]
    A --> Q1["auditResults: QueueChannel"]
    N --> Q2["notificationResults: QueueChannel"]
~~~

The two final queues collect results for this exercise. In a real system, these branches can be replaced with service activators or adapters to external systems.

### 6.2. Complete Configuration

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    public record Order(String id, long totalCents) {
    }

    public record OrderAccepted(String id, long totalCents) {
    }

    @Bean
    public DirectChannel orderInput() {
        DirectChannel channel = new DirectChannel();
        channel.setFailover(false);
        return channel;
    }

    @Bean
    public PublishSubscribeChannel orderEvents() {
        return new PublishSubscribeChannel(true);
    }

    @Bean
    public QueueChannel auditResults() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel notificationResults() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow acceptOrder(
            @Qualifier("orderInput") DirectChannel input,
            @Qualifier("orderEvents") PublishSubscribeChannel events) {

        return IntegrationFlow.from(input)
                .<Order>filter(
                        order -> order.totalCents() > 0,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .<Order, OrderAccepted>transform(
                        order -> new OrderAccepted(
                                order.id(), order.totalCents()))
                .channel(events)
                .get();
    }

    @Bean
    public IntegrationFlow auditBranch(
            @Qualifier("orderEvents") PublishSubscribeChannel events,
            @Qualifier("auditResults") QueueChannel results) {

        return IntegrationFlow.from(events)
                .channel(results)
                .get();
    }

    @Bean
    public IntegrationFlow notificationBranch(
            @Qualifier("orderEvents") PublishSubscribeChannel events,
            @Qualifier("notificationResults") QueueChannel results) {

        return IntegrationFlow.from(events)
                .channel(results)
                .get();
    }
}
~~~

Java DSL builds and registers the flow components in the application context. When no other channel is specified between endpoints, the DSL normally connects them with a `DirectChannel`. Branches that only connect two channels are implemented via a bridge endpoint. See [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html) and [Message Channels in Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-channels.html).

In this configuration:

- The filter endpoint receives messages from `orderInput`; you do not call `subscribe` again.
- The transformer produces the event payload and sends it to `orderEvents`.
- The two bridge endpoints at the head of the two branches both receive the broadcast event.
- `true` in `new PublishSubscribeChannel(true)` requires a subscriber to be present; it does not enable asynchronous processing.
- Both queues have bounded capacity. When a queue is full, sending may block; a slow branch can slow down the synchronous sending path.

The practice examples send only a few messages to avoid filling the queues. In production, you need policies for capacity, consumption rate, and timeouts at the appropriate sending boundary.

### 6.3. Sending and Observing Results

Place the following class next to `OrderFlowConfiguration`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class OrderFlowDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class)) {

            MessageChannel input =
                    context.getBean("orderInput", MessageChannel.class);

            QueueChannel audit =
                    context.getBean("auditResults", QueueChannel.class);

            QueueChannel notifications =
                    context.getBean("notificationResults", QueueChannel.class);

            input.send(
                    MessageBuilder.withPayload(
                                    new OrderFlowConfiguration.Order(
                                            "ORDER-1001", 250_000))
                            .setHeader("traceId", "trace-1001")
                            .build());

            Message<?> audited = audit.receive(0);
            Message<?> notified = notifications.receive(0);

            if (audited == null || notified == null) {
                throw new IllegalStateException(
                        "Missing result in one of the branches");
            }

            System.out.println(audited.getPayload());
            System.out.println(notified.getPayload());
            System.out.println(
                    audited.getHeaders().get("traceId"));
        }
    }
}
~~~

Both branches receive the `OrderAccepted` payload for order `ORDER-1001`. `receive(0)` is sufficient for this example because the entire path to both queues runs synchronously before `input.send` returns.

If you change `orderEvents` to a form with an executor, that assumption no longer holds: the sender can continue before the workers write results. In that case, you must wait with a bounded `receive(timeout)` or a synchronization mechanism in tests.

## 7. Load Balancing, Failover, and Processing Attempts

`DirectChannel` defaults to round-robin with failover enabled. When the selected handler throws an exception, the dispatcher can try the next handler. Therefore, "point-to-point" is not a promise that only one handler was ever called in every failure scenario. See [DirectChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html#channel-configuration-directchannel).

Business example posed by the lesson:

1. Worker A writes the order to the database.
2. A encounters an error calling an external system after having written the data.
3. The dispatcher tries worker B.
4. B can create additional side effects if it does not recognize the already processed order.

You can configure errors to stop at the selected handler:

~~~java
DirectChannel commands = new DirectChannel();
commands.setFailover(false);
~~~

This configuration does not provide an "exactly once" guarantee. To prevent duplicate business writes, you need a business key or idempotent design based on the order ID and appropriate transactions.

You also need to distinguish:

| Concept | What Happens |
| --- | --- |
| Load balancing | Chooses which handler receives a message first |
| Failover | Tries another handler when the selected handler fails |
| Retry | Re-executes an operation according to a retry policy |
| Broadcast | Intentionally sends a message to multiple subscribers |

If handlers represent different business steps, express their order using a flow. Subscriber order is no substitute for workflow structure.

## 8. Changing Threads with ExecutorChannel

### 8.1. Configuring an Asynchronous Channel in Spring

The following configuration is a standalone example, not an implicit replacement for the order configuration class:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageHandler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
public class AsyncJobConfiguration {

    @Bean
    public ThreadPoolTaskExecutor integrationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("integration-worker-");
        return executor;
    }

    @Bean
    public ExecutorChannel asyncJobs(
            @Qualifier("integrationExecutor")
            ThreadPoolTaskExecutor executor) {

        ExecutorChannel channel = new ExecutorChannel(executor);
        channel.setFailover(false);
        return channel;
    }

    @Bean
    public QueueChannel jobErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public IntegrationFlow jobFlow(
            @Qualifier("asyncJobs") ExecutorChannel jobs) {

        return IntegrationFlow.from(jobs)
                .handle((MessageHandler) message -> {
                    String job = (String) message.getPayload();

                    if ("FAIL".equals(job)) {
                        throw new IllegalArgumentException(
                                "Unable to execute task");
                    }

                    System.out.println(
                            job + " running on "
                                    + Thread.currentThread().getName());
                })
                .get();
    }
}
~~~

Spring manages initialization and shutdown of `ThreadPoolTaskExecutor` because the executor is declared as a bean. The thread counts and queue capacity here are illustrative; they must be tuned to the application's load and processing duration. See [ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html).

The executor's queue holds tasks in memory. It does not provide message recovery after process termination like a design backed by a persistent message store.

### 8.2. Observing Errors Raised in a Worker

Run the following snippet in an application with `AsyncJobConfiguration`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

public class AsyncJobDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                AsyncJobConfiguration.class)) {

            MessageChannel jobs =
                    context.getBean("asyncJobs", MessageChannel.class);

            QueueChannel errors =
                    context.getBean("jobErrors", QueueChannel.class);

            jobs.send(
                    MessageBuilder.withPayload("FAIL")
                            .setErrorChannel(errors)
                            .build());

            Message<?> received = errors.receive(2_000);

            if (!(received instanceof ErrorMessage error)) {
                throw new IllegalStateException(
                        "Did not receive ErrorMessage within timeout");
            }

            System.out.println(error.getPayload().getMessage());
        }
    }
}
~~~

Within Spring Integration's managed infrastructure as shown above, errors from an asynchronous task are converted into an `ErrorMessage`. The error-routing path checks the `errorChannel` header first; if absent, it uses the global channel named `errorChannel`. The example only collects the error for observation; a real application must decide whether to log, retry, or route to a final error handler. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Do not generalize this behavior to arbitrary `Executor` instances or standalone channels created outside an application context. Error propagation depends on both the channel and the configured error-handling infrastructure.

## 9. What Does a Successful send Mean?

`MessageChannel.send` returns a `boolean` and may also throw an exception. `true` indicates that the send operation succeeded under the channel's contract; it is not an end-to-end business completion receipt. See [MessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html).

| Case | How to Interpret the Send Result |
| --- | --- |
| Synchronous handler processes and returns normally | The handler invocation has finished on that execution path |
| Task successfully handed off to an executor | The task was accepted; the worker may not have finished yet |
| Handler enqueues additional work to an external system | Not sufficient proof that the external system completed the work |
| Need to know whether the order was processed successfully | Requires an explicit reply, result event, or business status |

### 9.1. No Subscribers

Do not assume every implementation returns `false` when no handler is present:

- With `DirectChannel`, lacking a subscriber causes dispatch to fail and is typically observed as a message delivery exception.
- With a default `PublishSubscribeChannel`, `minSubscribers` defaults to `0`; a send can be considered successful even with no receivers.
- The `PublishSubscribeChannel(true)` constructor requires a subscriber. If business requirements demand a specific number of branches, add corresponding configuration and checks.

Minimum subscriber characteristics are described in [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html). Having enough subscribers still does not prove all side effects have completed, especially when an executor is used.

### 9.2. Timeout Does Not Automatically Stop a Handler

The call:

~~~java
channel.send(message, 1_000);
~~~

must not be interpreted as "after one second, every handler will be interrupted."

For example, a `DirectChannel` handler may make an HTTP call and wait longer than one second. To bound the HTTP operation, you must configure the HTTP client's timeout. For request-reply, also examine the reply timeout; for an executor, examine task acceptance and rejection policies.

## 10. Errors, Transactions, and Shared State

### 10.1. Errors on the Synchronous Path

On a synchronous call path, unhandled errors can propagate back to the sender. Merely attaching an `errorChannel` header to a message and sending it into a `DirectChannel` does not automatically turn that error into asynchronous error handling. A gateway may have its own error-handling policy; inspect the configuration at the flow entry point.

On a path with worker threads, a `try/catch` around `send` remains useful for send failures or executor task rejection, but it cannot catch a business error occurring later in a worker the way a normal synchronous call does.

### 10.2. Transaction Boundaries

A processing chain using `DirectChannel` can participate in an existing transaction on the sending thread if resource-accessing components are configured to join that transaction. A channel neither starts a transaction on its own nor turns multiple external systems into a single atomic transaction.

When crossing an `ExecutorChannel`, do not assume a thread-bound transaction from the producer automatically propagates to the worker. The worker may need its own transaction. If the producer needs to synchronize database writes and durable event publishing, an appropriate coordination mechanism must be designed at the business level.

### 10.3. Concurrency and Ordering

A `DirectChannel` does not spawn new workers, yet multiple producers can still send concurrently from different threads. Consequently, a singleton handler can still be invoked concurrently.

When designing handlers:

- Prefer local state per invocation.
- If sharing memory, use appropriate data structures and synchronization mechanisms.
- Do not assume wrapping in a `Message` makes a mutable payload immutable.
- With broadcasting, avoid mutating a shared payload object across multiple branches.
- When using a multi-threaded executor, do not assume completion order matches send order.

For example, `OrderAccepted` above contains only `String` and `long`, making it suitable for sharing as an immutable value. If a payload contains a mutable `List` or `Map`, protect or copy the data according to each branch's needs.

## 11. Observing Without Creating Competing Consumers

Suppose `orderInput` is a `DirectChannel`. Adding a "logging-only" handler via `subscribe` creates an extra consumer competing with the order-processing endpoint. Some messages may go to the logging handler instead of the business workflow.

To observe the send path, use a `ChannelInterceptor` or a wire tap. For a `SubscribableChannel`, the `preReceive` and `postReceive` callbacks are not suitable observation points because there is no `receive` operation. See [Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html).

Example of adding an interceptor to a `DirectChannel` bean:

~~~java
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public class ObservedChannelFactory {

    public static DirectChannel create() {
        DirectChannel channel = new DirectChannel();

        channel.addInterceptor(new ChannelInterceptor() {
            @Override
            public void afterSendCompletion(
                    Message<?> message,
                    MessageChannel target,
                    boolean sent,
                    Exception exception) {

                System.out.println(
                        "traceId=" + message.getHeaders().get("traceId")
                                + ", sent=" + sent
                                + ", failed=" + (exception != null));
            }
        });

        return channel;
    }
}
~~~

In a real application, emit the data to an appropriate logging or metrics system. With asynchronous channels, the send-completion callback cannot be used as a substitute for business-completion metrics inside the worker.

## 12. Testing Critical Behaviors

The tests below use JUnit Jupiter and the `OrderFlowConfiguration` class from Section 6. They focus on observable behavior: same thread, broadcast to all branches, and response when no subscriber exists.

### 12.1. DirectChannel Handler Runs Before send Returns

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DirectChannelThreadTest {

    @Test
    void invokesHandlerOnSenderThread() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<Thread> invokedOn = new AtomicReference<>();
        Thread sender = Thread.currentThread();

        channel.subscribe(message ->
                invokedOn.set(Thread.currentThread()));

        boolean sent = channel.send(new GenericMessage<>("ORDER-1001"));

        assertTrue(sent);
        assertSame(sender, invokedOn.get());
    }
}
~~~

The test uses `Thread` object identity rather than comparing thread names, and does not need `Thread.sleep`.

### 12.2. One Event Reaches Both Branches

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderBroadcastTest {

    @Test
    void deliversAcceptedOrderToBothBranches() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class)) {

            MessageChannel input =
                    context.getBean("orderInput", MessageChannel.class);
            QueueChannel audit =
                    context.getBean("auditResults", QueueChannel.class);
            QueueChannel notifications =
                    context.getBean("notificationResults", QueueChannel.class);

            assertTrue(input.send(
                    MessageBuilder.withPayload(
                                    new OrderFlowConfiguration.Order(
                                            "ORDER-1001", 250_000))
                            .setHeader("traceId", "trace-1001")
                            .build()));

            Message<?> auditMessage = audit.receive(0);
            Message<?> notificationMessage = notifications.receive(0);

            assertNotNull(auditMessage);
            assertNotNull(notificationMessage);

            var expected = new OrderFlowConfiguration.OrderAccepted(
                    "ORDER-1001", 250_000);

            assertEquals(expected, auditMessage.getPayload());
            assertEquals(expected, notificationMessage.getPayload());

            assertEquals(
                    "trace-1001",
                    auditMessage.getHeaders().get("traceId"));
            assertEquals(
                    "trace-1001",
                    notificationMessage.getHeaders().get("traceId"));

            assertNull(audit.receive(0));
            assertNull(notifications.receive(0));
        }
    }
}
~~~

If `orderEvents` is accidentally changed to `DirectChannel`, the test will detect that one branch receives no result. If an executor is added, the way results are awaited must be updated to reflect the asynchronous boundary.

### 12.3. Comparing Empty Channels

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EmptyChannelTest {

    @Test
    void directChannelWithoutSubscriberFails() {
        DirectChannel channel = new DirectChannel();

        assertThrows(
                MessagingException.class,
                () -> channel.send(new GenericMessage<>("ORDER-1001")));
    }

    @Test
    void defaultPublishSubscribeChannelAllowsNoSubscribers() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();

        assertTrue(channel.send(new GenericMessage<>("OrderAccepted")));
    }

    @Test
    void requiredSubscriberPreventsSilentEmptyBroadcast() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel(true);

        assertThrows(
                MessagingException.class,
                () -> channel.send(new GenericMessage<>("OrderAccepted")));
    }
}
~~~

These tests do not assert durable delivery guarantees. They only describe the behavior of specific implementations and configurations.

## 13. Common Issues and How to Check

| Symptom | Cause to Investigate | How to Check |
| --- | --- | --- |
| Only one of two business steps runs | Both steps subscribed to the same `DirectChannel` | Verify whether the flow chains them sequentially as required |
| One broadcast branch does not receive messages | Endpoint not started, wired to the wrong channel, or an earlier branch failed | Check beans, endpoint lifecycle, and error path |
| Send succeeded but no result yet | Worker has not finished or broadcast allows zero subscribers | Check the executor, business outcome, and subscriber requirement |
| Sender cannot catch errors inside the worker | An asynchronous boundary is present | Check `errorChannel` and the error-handling consumer |
| A handler processes a message twice in business terms | Retry, failover, or upstream resend occurred | Correlate business IDs and idempotent design |
| Attaching logging to a channel drops orders | Logging handler competes with the business handler | Switch to an interceptor or proper observability design |
| Switching to an executor breaks transaction expectations | The old transaction was bound to the sending thread | Redefine transaction start and end boundaries |
| Payload data mutates unexpectedly across branches | Multiple branches mutate a shared object | Check immutability and data ownership |

When logging, prioritize the channel name, trace ID, business ID, and necessary error details. Do not conclude an order is complete merely from a `"send=true"` log line.

## 14. Reinforcement Exercises

1. Use `DirectChannel` with two equivalent handlers and send six messages without errors. Count how many times each handler is invoked. Do not include real side effects in this experiment.
2. Keep both handlers and have one throw an exception. Compare failover enabled vs. disabled; record which handler was called for each message.
3. Change the channel in the first experiment to `PublishSubscribeChannel`. Verify that each handler receives all six messages when all succeed.
4. Change `orderEvents` to a configuration with an executor and update the test to await results with a bound, without using a fixed sleep.
5. Send an `Order` with `totalCents=0` into the flow from Section 6. Verify that the sender receives an error and both result queues remain empty.
6. Have the task in Section 8 throw an error and observe `ErrorMessage`. Identify the root cause along with the message information needed for business correlation.

The completion criterion is being able to explain why results change when switching implementations, failover settings, or thread boundaries. Memorizing interface names alone is not enough to predict the behavior of a flow.

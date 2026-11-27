# Broadcasting Messages to Multiple Subscribers

## 1. The Problem: One Event, Multiple Responsibilities

When an order is created, an application may need to write an audit log, send a notification to the customer, and update operational metrics. All three tasks originate from a single `OrderCreated` event, but each party cares about the event for a different reason.

If the producer calls all three services directly, it must know the list of consumers and how to invoke each one. In Spring Integration, the producer can send a single `Message` to a `PublishSubscribeChannel`; the endpoints subscribed to the channel will receive the message to carry out their own responsibilities.

This lesson belongs to the **PublishSubscribeChannel** chapter of the **SPRING_INTEGRATION_CORE** module, focusing on how to wire `Message`, `MessageChannel`, endpoints, gateways, and Java DSL to broadcast a message to multiple processing branches. After this lesson, you will be able to:

- Distinguish broadcasting from load-sharing among consumers.
- Register multiple subscribers using Java and Java DSL.
- Choose between synchronous execution and using an executor.
- Explain the result of `send()`, the no-subscriber case, and behavior when one branch fails.
- Recognize when `applySequence` and an aggregator are needed.
- Design test cases that verify each branch receives the expected message.

## 2. What Does Broadcasting Really Mean?

### 2.1. From Producer to Multiple Handlers

~~~mermaid
flowchart LR
    P["Producer: OrderCreated"] --> C["PublishSubscribeChannel"]
    C --> A["Subscriber A: Audit"]
    C --> B["Subscriber B: Notification"]
    C --> D["Subscriber C: Metrics"]
~~~

`PublishSubscribeChannel` broadcasts messages to registered `MessageHandler`s. It is a `SubscribableChannel`: consumers receive messages through a `handleMessage(...)` invocation, rather than calling `receive()` to pull data. The registration API consists of `subscribe(handler)` and `unsubscribe(handler)`. [Reference: Spring Integration channel interfaces](https://docs.spring.io/spring-integration/reference/channel/interfaces.html).

For example, the producer sends `E1` and `E2`, while all three subscribers are active and delivery encounters no errors:

| Subscriber | Messages Received | Responsibility |
| --- | --- | --- |
| Audit | E1, E2 | Record business audit trail |
| Notification | E1, E2 | Prepare notification |
| Metrics | E1, E2 | Update metrics |

In total, six message deliveries occur. There is no splitting of `E1` to Audit and `E2` to Notification.

"Send to all" describes the delivery model. It does not create an atomic transaction spanning all subscribers: one branch may already have produced external side effects before another branch fails.

### 2.2. Comparison with Common Channels

| Channel | Delivery Model | How Consumers Receive | Meaning with Multiple Consumers |
| --- | --- | --- | --- |
| `DirectChannel` | Point-to-point | Handler is invoked directly | One handler processes one message successfully; failover may occur when a handler fails |
| `ExecutorChannel` | Point-to-point via executor | Executor executes the handler | Supports load sharing; does not automatically become broadcast |
| `QueueChannel` | Point-to-point, queued | Polling via `receive()` or a poller | Consumers compete to pull each message |
| `PublishSubscribeChannel` | Broadcast | Invokes subscribed handlers | Each registered branch is a recipient of the event |

The difference between `DirectChannel` and `PublishSubscribeChannel` lies in the number of recipients per send, not in "having subscribers or not". Both can have multiple subscribers. [Reference: message channel implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 2.3. What Component Is the Channel's Subscriber?

In a declarative flow, there is usually an endpoint sitting between the channel and the business logic:

~~~text
PublishSubscribeChannel
    -> EventDrivenConsumer endpoint
        -> MessageHandler / service activator
            -> business logic
~~~

When the endpoint starts, it registers its handler with the channel; when it stops, it unsubscribes. Therefore, the number of service classes present in the source code does not equate to the number of active subscribers.

If a subscriber forwards the message into a multi-step flow, the channel only sees the first receiving point of that branch. It does not automatically know whether the branch has sent an email, written to the database, or completed an HTTP request.

## 3. Minimal Java Example

The examples use Java 17 or later to declare `record` types. The channel portion requires the `org.springframework.integration:spring-integration-core` dependency; Java DSL is already included in this dependency. In a Spring Boot project, you can use `spring-boot-starter-integration` and let the project's BOM manage versions.

The Java DSL configuration snippets below use the `IntegrationFlow.from(...)` API style of Spring Integration 6 and later. Each configuration option is a separate example; do not simultaneously register options that share the same bean name.

### 3.1. Event Payload

Create a shared data type for the examples:

~~~java
package example;

import java.math.BigDecimal;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerEmail,
        BigDecimal total) {
}
~~~

`eventId` identifies the business event, while `orderId` identifies the order. These two values answer different questions: a single order can generate multiple events over time.

### 3.2. Registering Three Subscribers

~~~java
package example;

import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class BroadcastDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel orderEvents =
                new PublishSubscribeChannel(true);

        Set<String> observed = new HashSet<>();

        MessageHandler audit = message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            observed.add("audit:" + event.eventId());
        };

        MessageHandler notification = message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            observed.add("notification:" + event.eventId());
        };

        MessageHandler metrics = message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            observed.add("metrics:" + event.eventId());
        };

        orderEvents.subscribe(audit);
        orderEvents.subscribe(notification);
        orderEvents.subscribe(metrics);

        OrderCreated event = new OrderCreated(
                "evt-1001",
                "order-501",
                "customer@example.com",
                new BigDecimal("250000"));

        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader("source", "checkout")
                .build();

        boolean sent = orderEvents.send(message);

        System.out.println("sent=" + sent);
        System.out.println(observed.contains("audit:evt-1001"));
        System.out.println(observed.contains("notification:evt-1001"));
        System.out.println(observed.contains("metrics:evt-1001"));

        orderEvents.unsubscribe(notification);
    }
}
~~~

Expected output:

~~~text
sent=true
true
true
true
~~~

The example uses `HashSet` because the channel is running synchronously on the sending thread; there are no concurrent writes in this snippet. If switched to an executor, the data structure storing results must also be safe for concurrent access.

The `true` argument in the constructor is `requireSubscribers`: it requires subscribers to be present when sending. This is not a flag that enables asynchronous processing.

Calling `unsubscribe(notification)` only affects subsequent sends. It does not undo work the subscriber has already performed, nor does it create a history for the subscriber to catch up on if it subscribes again later.

## 4. Configuring Endpoints with Spring

In a real application, Spring should manage the channel and endpoint lifecycle. The following example creates one channel along with three service activators:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class OrderBroadcastConfiguration {

    @Bean
    public PublishSubscribeChannel orderEvents() {
        return new PublishSubscribeChannel(true);
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEvents")
    public MessageHandler auditSubscriber() {
        return message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            System.out.println("audit: " + event.orderId());
        };
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEvents")
    public MessageHandler notificationSubscriber() {
        return message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            System.out.println("notification: " + event.customerEmail());
        };
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEvents")
    public MessageHandler metricsSubscriber() {
        return message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            System.out.println("metrics: " + event.total());
        };
    }
}
~~~

The `println` statements are only for observing which branch gets invoked. In an application, they are replaced by logic for saving audit records, creating notification requests, and recording metrics.

You can bootstrap the configuration and send an event as follows:

~~~java
package example;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class SpringBroadcastDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderBroadcastConfiguration.class)) {

            MessageChannel channel =
                    context.getBean("orderEvents", MessageChannel.class);

            channel.send(MessageBuilder.withPayload(
                    new OrderCreated(
                            "evt-1002",
                            "order-502",
                            "customer@example.com",
                            new BigDecimal("390000")))
                    .build());
        }
    }
}
~~~

All three endpoints subscribe to `orderEvents`. If you replace this channel with a `DirectChannel`, the bean naming structure might still be valid, but the delivery semantics have changed: you no longer have three parties observing every event.

With `PublishSubscribeChannel`, do not configure a poller on endpoints receiving directly from it. A poller is appropriate at the boundary receiving from a `PollableChannel`, such as a `QueueChannel`.

## 5. Creating Branches with Java DSL

Java DSL clearly expresses three branches sitting together after a broadcast point. The approach below replaces the annotation configuration from the previous section:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderDslConfiguration {

    @Bean
    public IntegrationFlow orderBroadcastFlow() {
        return IntegrationFlow.from("orderIngress")
                .publishSubscribeChannel(fanout -> fanout
                        .subscribe(branch -> branch
                                .handle(message -> {
                                    OrderCreated event =
                                            (OrderCreated) message.getPayload();
                                    System.out.println(
                                            "audit: " + event.orderId());
                                }))
                        .subscribe(branch -> branch
                                .filter(OrderCreated.class,
                                        event -> event.customerEmail() != null
                                                && !event.customerEmail()
                                                        .isBlank())
                                .<OrderCreated, String>transform(event ->
                                        "Order notification "
                                                + event.orderId()
                                                + " to "
                                                + event.customerEmail())
                                .handle(message ->
                                        System.out.println(
                                                message.getPayload())))
                        .subscribe(branch -> branch
                                .handle(message -> {
                                    OrderCreated event =
                                            (OrderCreated) message.getPayload();
                                    System.out.println(
                                            "metrics: " + event.total());
                                })))
                .get();
    }
}
~~~

The producer sends `Message<OrderCreated>` to the `orderIngress` channel bean. The DSL creates the subscribers for the internal broadcast channel inside the flow.

In the example:

- The audit branch receives the event and observes `orderId`.
- The notification branch filters out events missing an email, then transforms the payload into a notification message.
- The metrics branch still receives the event even if the notification filter drops the message from the notification branch.

The notification branch's transformer produces a result for that branch alone. It does not replace the `OrderCreated` payload received by the other branches with a string.

There is an easy-to-misread detail: a step placed immediately after `publishSubscribeChannel(...)` in the main flow can become an additional subscriber to the broadcast point. It does not automatically wait for and merge the results of all `subscribe(...)` branches. [Java DSL subflow documentation](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html).

If you need "all three branches to finish before running a final step", you must design an explicit result-gathering path; simply appending another `handle(...)` does not create that waiting mechanism.

### 5.1. Adding a Gateway on the Producer Side

With the DSL configuration above, the producer can use a gateway to avoid constructing `Message` objects manually:

~~~java
package example;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orderIngress")
public interface OrderEventsGateway {

    void publish(OrderCreated event);
}
~~~

Register the gateway by adding the following annotation to a configuration class loaded by Spring:

~~~java
@IntegrationComponentScan(basePackageClasses = OrderEventsGateway.class)
~~~

This annotation belongs to the `org.springframework.integration.annotation` package. A service can then inject `OrderEventsGateway` and call `publish(event)`.

A `void` return type fits one-way event publishing semantics. However, `void` does not mean background execution: if the downstream flow is synchronous, the gateway call still waits for synchronous handlers to run or fail.

You should not let multiple branches return results directly back to a single gateway call and treat that as an aggregation. Define a single place to gather responses before producing a single reply.

## 6. Synchronous and Asynchronous Execution

### 6.1. Default: Running on the Sending Thread

With the constructor that takes no executor:

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
~~~

Subscribers are invoked on the thread executing `send()`. When no errors occur and handlers do not hand off work elsewhere, the send duration includes the execution time of those handlers.

Suppose three handlers take approximately 20 ms, 200 ms, and 15 ms respectively:

~~~text
send()
  -> audit:        20 ms
  -> notification: 200 ms
  -> metrics:      15 ms
  -> return
~~~

The illustrative duration is around 235 ms plus dispatching overhead. A slow subscriber slows down the producer.

If a handler merely pushes work onto another queue and returns, `send()` only waits for that enqueue operation. It does not know whether the work at the end of the queue has finished.

### 6.2. Providing an Executor to Hand Work Off to Workers

You can replace the `orderEvents` bean in the annotation configuration with the following option, while also adding an executor bean:

~~~java
@Bean
public ThreadPoolTaskExecutor broadcastExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(256);
    executor.setThreadNamePrefix("order-broadcast-");
    return executor;
}

@Bean
public PublishSubscribeChannel orderEvents(
        @Qualifier("broadcastExecutor")
        ThreadPoolTaskExecutor executor) {

    return new PublishSubscribeChannel(executor, true);
}
~~~

Additional imports:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
~~~

Spring manages initializing and shutting down `ThreadPoolTaskExecutor` when it is declared as a bean. There is no need to call `initialize()` manually inside this `@Bean` method.

With the thread pool above, handler invocations are handed off to workers. Branches can run concurrently, depending on available workers and queued work. Executor configuration and channel error handling are described in the [PublishSubscribeChannel configuration guide](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

Keep these distinctions clear:

| Observation | What Can Be Concluded |
| --- | --- |
| `send()` returns successfully | The send satisfied the channel's delivery criteria |
| Executor accepts task | The task was accepted for execution |
| Handler finishes successfully | The work inside that handler invocation completed |
| Email was accepted by the target system | Requires a separate response or proof from the email-sending system |

Do not infer the last row solely from the first row.

An executor can run a task directly on the calling thread; a rejection policy can also run the task back on the sending thread. Therefore, "passing an executor parameter" is not enough to guarantee that calls never block or that every handler always runs on a different thread.

### 6.3. Fan-Out Cost and Resource Limits

If there are 100 events per second and three branches, the executor may need to process around 300 handler invocations per second. Adding a subscriber increases the work for every subsequent event.

With three branches, each invocation taking 50 ms on average, the raw processing demand is:

~~~text
100 event/s × 3 branches × 0.05 s = 15 worker-second/s
~~~

This is a load estimate, excluding I/O wait variability and bursts. It shows that a four-worker pool cannot keep up if each worker is occupied continuously for that entire duration.

Set executor queue bounds, monitor wait times, and handle rejected tasks. An in-memory task queue does not provide replay capability after an abrupt application shutdown.

If the executor rejects a task during a broadcast, some earlier branches may already have had their work submitted. Do not treat an exception received by the producer as proof that no branch ran.

## 7. When a Subscriber Fails

### 7.1. Synchronous: An Error Can Block Remaining Subscribers

Suppose the invocation order for a send is Audit, Notification, Metrics, and `ignoreFailures=false`:

~~~text
Audit:        succeeds
Notification: throws exception
Metrics:      may not have been called
Producer:     receives exception from send()
~~~

`ignoreFailures` defaults to `false`. With synchronous delivery, the dispatcher stops early when a handler throws an error; the error may be wrapped in a messaging-layer exception. If `ignoreFailures=true` is set, the dispatcher attempts to continue to other handlers and logs a warning for the ignored failure. [BroadcastingDispatcher Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/BroadcastingDispatcher.html).

Do not enable `ignoreFailures` just so the producer always receives a clean result. For instance, if Audit is mandatory, ignoring an Audit failure leaves a business requirement unmet even while other branches keep running.

### 7.2. Asynchronous: The Producer Cannot Catch Downstream Errors with Normal try/catch

When a handler runs on a worker after the producer has already exited `send()`, the handler's exception cannot unwind back onto the old call stack.

Spring Integration supports publishing an `ErrorMessage`, whose payload is the throwable, to the channel specified in the message's `errorChannel` header or the global channel named `errorChannel`. This default mechanism applies to framework-executed tasks; it does not automatically apply to every synchronous call just because a message carries an `errorChannel` header. [Error handling documentation](https://docs.spring.io/spring-integration/reference/error-handling.html).

You can send a message to an executor-backed broadcast channel with a dedicated error header:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(
                org.springframework.messaging.MessageHeaders.ERROR_CHANNEL,
                "broadcastErrors")
        .build();

orderEvents.send(message);
~~~

And add an error-observing endpoint to the same application context:

~~~java
@Bean
public MessageChannel broadcastErrors() {
    return new DirectChannel();
}

@Bean
@ServiceActivator(inputChannel = "broadcastErrors")
public MessageHandler broadcastErrorHandler() {
    return message -> {
        Throwable failure = (Throwable) message.getPayload();
        System.err.println("Broadcast failed: " + failure.getMessage());
    };
}
~~~

Additional imports for the configuration snippet:

~~~java
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;
~~~

In a real system, the error handler needs to record the event identifier, the failing branch, and details to support follow-up handling. A `MessagingException` can provide `failedMessage`; check for null before accessing it.

If you configure a custom `ErrorHandler` on `PublishSubscribeChannel`, make it explicit whether it logs the error or forwards it somewhere. The channel's `ErrorHandler` strategy is for executor-backed channels; it does not automatically convert synchronous exceptions into error messages.

### 7.3. Retrying the Whole Broadcast Can Duplicate Completed Side Effects

Consider the scenario:

1. Audit saves successfully.
2. Notification calls an external service and fails.
3. The producer resends the entire event.
4. Audit receives the already-processed event again.

If audit simply inserts a new row on every receipt, you may end up with duplicate records. If an email was actually sent but the response was lost, resending could cause the customer to receive two emails.

A design that is usually easier to control retries at the failing branch while making critical side effects idempotent against duplicate processing.

Example business key for a processing record:

~~~text
(eventId, subscriberName)
("evt-1001", "audit")
("evt-1001", "notification")
~~~

Each subscriber has its own progress. The `MessageHeaders.ID` identifier serves a specific message instance; when rebuilding a message or creating a new one, do not assume that ID is a stable identifier for the business event.

`PublishSubscribeChannel` itself does not provide durable retries, exactly-once delivery, or rollback of sent emails.

## 8. No Subscribers and the Meaning of send()

Four options usually need to be read carefully in configuration:

| Option | Default | Purpose |
| --- | --- | --- |
| `requireSubscribers` | `false` with default constructor | Rejects a send when there are no subscribers if set to `true` |
| `minSubscribers` | `0` | Minimum threshold used to evaluate delivery outcome |
| `ignoreFailures` | `false` | Determines whether handler errors are ignored so delivery attempts continue |
| `applySequence` | `false` | Adds sequence metadata to messages going to subscribers |

You can create channels with different requirements:

~~~java
PublishSubscribeChannel optionalEvents =
        new PublishSubscribeChannel();

PublishSubscribeChannel requiredEvents =
        new PublishSubscribeChannel(true);

PublishSubscribeChannel needsTwoSubscribers =
        new PublishSubscribeChannel(true);
needsTwoSubscribers.setMinSubscribers(2);
~~~

With a default channel that has no subscribers, `send()` can return `true` because the minimum threshold is 0. The message is not retained for delivery if a subscriber appears later.

With `requireSubscribers=true`, having no subscribers is a delivery failure. The executor-accepting constructor also has the variant `new PublishSubscribeChannel(executor, true)`. Details on constructors and options are in the [PublishSubscribeChannel Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

`minSubscribers` does not guarantee that the exact business subscribers you expect are present. Having two subscribers does not prove they are Audit and Notification; they could be two misconfigured endpoints.

In executor mode, the delivery result is not the final processing outcome of the branches. Do not use `minSubscribers` as a waiting mechanism for "at least two emails sent successfully". If you need that kind of outcome, collect replies or persist business state.

Note also: the timeout passed to `send(message, timeout)` is not a hard deadline that forcibly stops all subscribers. A synchronous handler making a slow HTTP call still needs an HTTP client timeout; asynchronous work needs its own deadline policy.

## 9. applySequence and the Result-Gathering Path

### 9.1. Broadcast Does Not Aggregate Replies Automatically

There are two distinct problems:

- Publishing an event to Audit, Notification, and Metrics: each party performs its own responsibility.
- Sending a request to three pricing providers and selecting a result: the producer needs a single aggregated result.

The second problem requires a reply path and an aggregating component, such as an aggregator or a scatter-gather setup. `PublishSubscribeChannel` only handles broadcasting to the branches. [Scatter-Gather documentation](https://docs.spring.io/spring-integration/reference/scatter-gather.html).

~~~mermaid
flowchart LR
    P["Quote Request"] --> C["Broadcast"]
    C --> A["Branch A"]
    C --> B["Branch B"]
    C --> D["Branch C"]
    A --> G["Result-Gathering Channel"]
    B --> G
    D --> G
    G --> AG["Aggregator"]
    AG --> R["One Aggregated Result"]
~~~

### 9.2. Enable Sequence Metadata When the Design Needs It

~~~java
@Bean
public PublishSubscribeChannel quoteRequests() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel(true);
    channel.setApplySequence(true);
    return channel;
}
~~~

For a three-subscriber fan-out, the illustrative metadata looks like this:

| Sent Copy | `correlationId` | `sequenceNumber` | `sequenceSize` |
| --- | --- | --- | --- |
| First branch | Same group | 1 | 3 |
| Second branch | Same group | 2 | 3 |
| Third branch | Same group | 3 | 3 |

`sequenceNumber` indicates the position in the sequence generated for the delivery round; it is not the work completion order.

By default, an aggregator uses correlation and sequence information to know when a group has all its members. When using this strategy, each branch must send an appropriate result to the same gathering path and preserve the required metadata. [Aggregator documentation](https://docs.spring.io/spring-integration/reference/aggregator.html).

A typical design bug:

~~~text
Broadcast has 3 subscribers
  -> A returns a result
  -> B is dropped by a filter and returns nothing
  -> C returns a result

Aggregator waits for a group of 3 results.
~~~

The group may never meet its release condition. You must explicitly design how rejected results are represented, group timeouts, or an alternative release strategy.

Similarly, adding a logging-only subscriber to a broadcast point with `applySequence=true` can increment `sequenceSize`, even though that subscriber sends no result back to the aggregator. Adding an observing branch can also change completion criteria if you rely on subscriber count as the expected member count.

There is no need to enable `applySequence` for every event flow. If Audit, Notification, and Metrics are independent, sequence metadata usually serves no aggregation requirement.

## 10. Immutable Message Does Not Mean Deeply Immutable Payload

Under Spring's message model, you do not directly mutate the headers structure or reassign the payload reference of an already created message. However, the object held inside the payload or inside a header value can still be mutable. [Message and MessageHeaders documentation](https://docs.spring.io/spring-integration/reference/message.html).

Dangerous example:

~~~java
Map<String, Object> payload = new HashMap<>();
payload.put("status", "CREATED");

// Subscriber A:
payload.put("status", "NOTIFIED");

// Subscriber B may also be reading this exact Map.
~~~

When branches share the same object, A can cause B to observe data different from the original event. With multiple threads, this is also a data race hazard.

When `applySequence=false`, the channel may deliver the exact same message instance to subscribers. When sequence is enabled, the wrapper messages with different headers can still share the same payload reference; there is no automatic deep copy of the payload.

Appropriate design approaches:

- Emit an event DTO with state finalized at the moment the event occurs.
- Use immutable types for fields; copy collections when constructing the event if needed.
- Create separate result objects in each branch.
- Do not share an entity managed by a persistence context across workers.

The `record` in the `OrderCreated` example has `String` and `BigDecimal` fields, making it suitable for this kind of sharing. A `record` containing a `List` still requires care regarding whether the list's contents can be modified.

## 11. Ordering, Transactions, and Deployment Scope

### 11.1. Invocation Order Is Not Completion Order

In synchronous mode, you can configure endpoint order when you need to control dispatch order. When using an executor, a branch submitted earlier can still finish later.

Do not model a business dependency using two separate subscribers and expect the later subscriber to always see the result of the earlier subscriber:

~~~text
Wrong dependency model:
    broadcast -> deduct inventory
              -> confirm inventory deducted
~~~

If confirmation is only allowed after inventory deduction succeeds, chain them sequentially or emit a new event after the deduction step:

~~~text
Request -> deduct inventory succeeds -> InventoryReserved
                                     -> broadcast to interested parties
~~~

Broadcasting fits when multiple parties observe an already-established event.

### 11.2. The Channel Does Not Automatically Open a Transaction Spanning Subscribers

If the producer already has a thread-bound transaction and handlers run synchronously, downstream transactional operations may participate in that transaction depending on their configuration.

When switching to a worker thread, the producer's thread-bound transaction does not automatically follow the task. If a branch needs a transaction, you must design transaction boundaries within that branch or use an appropriate handoff mechanism. [Transactions and thread boundaries documentation](https://docs.spring.io/spring-integration/reference/transactions.html).

Even if database operations can all roll back together, a sent email or an HTTP request that already caused external side effects usually cannot be "undone" by a database rollback.

If the business requires publishing events only after the order commits, choose a post-commit publishing mechanism or a pattern like outbox combined with an event forwarder. `PublishSubscribeChannel` does not by itself solve consistency between the database and external notifications.

### 11.3. This Channel Lives Inside the Running Application

`org.springframework.integration.channel.PublishSubscribeChannel` is an in-process channel. It does not automatically broadcast to other JVMs.

If an application has three instances and a message is sent to the channel in the first instance, only subscribers attached to that channel receive the message. Subscribers on the second instance do not become recipients merely because their beans share the same name.

If you need cross-process delivery, replay after restart, or durable buffering, incorporate an appropriate transport or message store into the design. A topic, a consumer group, and a queue can have different delivery semantics; you must verify the "every service receives it" requirement at that layer.

## 12. Testing Broadcast Behavior

The test examples use JUnit Jupiter and the core dependency. They focus on the delivery contract, not on sending real emails.

### 12.1. Two Subscribers Must Both Receive the Message

~~~java
package example;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class PublishSubscribeChannelTest {

    @Test
    void broadcastsToEverySubscriber() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);

        QueueChannel audit = new QueueChannel();
        QueueChannel notification = new QueueChannel();

        channel.subscribe(message -> audit.send(message));
        channel.subscribe(message -> notification.send(message));

        Message<OrderCreated> original = MessageBuilder.withPayload(
                new OrderCreated(
                        "evt-test-1",
                        "order-test-1",
                        "customer@example.com",
                        new BigDecimal("100000")))
                .build();

        assertTrue(channel.send(original));

        assertSame(original, audit.receive(0));
        assertSame(original, notification.receive(0));

        assertNull(audit.receive(0));
        assertNull(notification.receive(0));
    }

    @Test
    void defaultChannelDoesNotRequireSubscribers() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel();

        assertTrue(channel.send(
                MessageBuilder.withPayload("event").build()));
    }

    @Test
    void requiredChannelRejectsWhenThereAreNoSubscribers() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);

        assertThrows(MessagingException.class, () ->
                channel.send(
                        MessageBuilder.withPayload("event").build()));
    }
}
~~~

`receive(0)` prevents the test from waiting indefinitely if no data arrives. The two destination channels in the test merely hold messages so results can be observed; they do not change the broadcast model of the source channel.

The `assertSame` check fits the default configuration without sequence enabled and without interceptors altering the message. If `applySequence` is enabled, assert on the payload and required headers instead of requiring the exact same message instance.

### 12.2. Verifying send() Does Not Wait for Worker Handlers to Finish

Use latches to hold both handlers while asserting that the send call has returned. This approach does not depend on a guessed `sleep` interval.

~~~java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.junit.jupiter.api.Assertions.*;

class AsyncBroadcastTest {

    @Test
    void sendReturnsBeforeSubscribersComplete() throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);

        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(2);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        try {
            PublishSubscribeChannel channel =
                    new PublishSubscribeChannel(workers, true);

            channel.setErrorHandler(failure::set);
            channel.afterPropertiesSet();

            channel.subscribe(message -> {
                started.countDown();
                awaitRelease(release);
                finished.countDown();
            });

            channel.subscribe(message -> {
                started.countDown();
                awaitRelease(release);
                finished.countDown();
            });

            assertTrue(channel.send(
                    MessageBuilder.withPayload("event").build()));

            assertTrue(started.await(5, SECONDS));
            assertEquals(2L, finished.getCount());

            release.countDown();

            assertTrue(finished.await(5, SECONDS));
            assertNull(failure.get());
        } finally {
            release.countDown();
            workers.shutdownNow();
            workers.awaitTermination(5, SECONDS);
        }
    }

    private static void awaitRelease(CountDownLatch release) {
        try {
            if (!release.await(10, SECONDS)) {
                throw new IllegalStateException(
                        "Subscriber did not receive release signal");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(exception);
        }
    }
}
~~~

Because this channel is created outside a Spring context, the test calls `afterPropertiesSet()` and supplies an explicit `ErrorHandler`. In an application with a channel bean, Spring performs the corresponding lifecycle initialization.

The key point of the test is: both handlers have started, both are held at the latch, yet `send()` has already returned. That proves the send result and subscriber completion are two distinct milestones.

### 12.3. Scenarios Worth Testing in Business Applications

| Scenario | What to Verify |
| --- | --- |
| A branch throws an error in synchronous mode | Producer sees the error and any side effects that already occurred are accounted for |
| A branch on a worker fails | Error reaches the configured observer or error handler |
| Filter drops a message in one branch | Other branches still receive it; any gathering path does not stall unexpectedly waiting for missing results |
| A subscriber is stopped | Behavior with zero or insufficient subscribers matches requirements |
| Producer resends the same `eventId` | Side effects requiring idempotency are protected |
| Executor is full | Rejected tasks are detected; do not assume no branches ran |
| `applySequence` is enabled | Group metadata is present and preserved across reply steps |

When testing synchronous failure ordering, configure handler or endpoint order explicitly. When testing multiple threads, use latches or timeout-bounded waits; do not infer completion order from branch declaration order.

## 13. Practice Exercise

Build an `OrderCreated` flow with three branches—Audit, Notification, and Metrics—following these steps:

1. Use a synchronous channel and store each branch's result in a separate observer. Send one event and verify all three receive it.
2. Add a filter for Notification to skip orders without an email. Verify Audit and Metrics still run.
3. Have Notification throw an intentional exception. Observe the send result and identify which branches ran under the configured order.
4. Use a bounded-queue executor. Log thread names in the producer and each handler to identify execution boundaries.
5. Route asynchronous errors into `broadcastErrors`, including the ability to trace the failing `eventId`.
6. Resend the same event and add duplicate-audit prevention using a business key.
7. In a separate quote-request flow, enable `applySequence` and aggregate results. Test leaving one branch without a reply and decide on a timeout or rejected-result representation.

You should be able to explain the outcomes in terms of channel behavior: which party received the message, which thread processed it, where errors went, and what processing milestone the producer actually knows about.

## 14. Key Principles to Remember

- `PublishSubscribeChannel` is for multiple branches observing the same message; load-sharing channels have a different purpose.
- Broadcast runs synchronously by default. To offload work to workers, supply an appropriate executor.
- The return value of `send()` does not prove that the final business side effects of all branches have completed.
- A failure in one branch does not automatically roll back external side effects of branches that already ran.
- Keep payloads safe to share; an immutable message wrapper does not perform a deep copy.
- Only use `applySequence` when the design needs group metadata, and handle missing results as well.
- If a later step depends on an earlier step, express it sequentially or emit a new event after the earlier step succeeds.
- Choose a separate persistence and retry mechanism when requirements call for surviving restarts or per-subscriber recovery.

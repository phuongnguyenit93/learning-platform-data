# Publish-Subscribe Semantics

## 1. One Event, Multiple Interested Parties

In the **Channel Types** chapter of the **SPRING_INTEGRATION_CORE** module, publish-subscribe describes how a single message is broadcast to multiple subscribers. Spring Integration provides `PublishSubscribeChannel` to express this delivery model within an integration flow.

Suppose the system has just recorded an `OrderPlaced` event. Auditing must write an audit trail, the notification service must decide whether to send an alert, and analytics must record revenue. The producer only emits the event; each subscriber is responsible for its own part of the work.

~~~mermaid
flowchart LR
    P["Producer: OrderPlaced"] --> C["PublishSubscribeChannel"]
    C --> A["Audit branch"]
    C --> N["Notification branch"]
    C --> R["Analytics branch"]
~~~

`PublishSubscribeChannel` implements `SubscribableChannel`: consumers register a `MessageHandler` and are invoked when a message is sent into the channel. The channel does not implement `PollableChannel` and has no `receive()` for consumers to pull messages via polling. This is a broadcast mechanism, distinct from dividing each message to one consumer. See [Spring Integration: Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

After this lesson, learners should be able to distinguish:

- **Delivery:** whether a message goes to one subscriber or many subscribers.
- **Execution:** whether handlers run on the sending thread or through an executor.
- **Completion:** channel send acceptance, handler return, and business completion are separate milestones.
- **Reliability:** durability, retries, deduplication, and recovery are additional design decisions.

The examples use Java 17 and Spring Integration 6.5 APIs. Configuration examples require `spring-integration-core` with Spring Context; test examples require JUnit Jupiter. The standalone illustrative configuration classes fit into an application that already has these libraries; the lesson does not require changing build configuration.

## 2. Delivery Contract: Broadcast vs. Competing Consumers

Two handlers subscribed to the same `DirectChannel` do not form two branches that both receive the event. That channel has point-to-point semantics: each dispatch targets one handler according to its load-balancing and failover policy. `ExecutorChannel` is also point-to-point even though it uses an executor. See [Spring Integration: DirectChannel and ExecutorChannel](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

| Channel type | Delivery model | Receiving model | Typical use case |
| --- | --- | --- | --- |
| `DirectChannel` | One handler per successful dispatch | Subscribe; direct execution | Single business processing step |
| `ExecutorChannel` | One handler per successful dispatch | Subscribe; dispatched via executor | Step needing thread offloading |
| `QueueChannel` | Consumers compete to pull messages from queue | Polling | Buffering work for a pool of workers |
| `PublishSubscribeChannel` | Broadcasts to subscribed handlers | Subscribe | One event for multiple branches |

Write down the business requirement before choosing a channel:

- "Each invoice must be processed by only one worker" fits a competing-consumers model.
- "Every payment event must be audited and tracked in analytics" fits broadcast.
- "Orders route to a regional processing team" fits a router.
- "Query multiple services and return one combined response" needs a result-gathering mechanism after fan-out.

In the order example, the name "audit subscriber" refers to a business role. Such a subscriber can be the entry endpoint of an entire `IntegrationFlow` comprising a transformer, filter, and service activator. The number of endpoints deeper inside a branch is not the number of direct channel subscribers.

## 3. Subscriber Scope and Registration Timing

A standard `PublishSubscribeChannel` is an in-memory channel inside the application. It does not automatically become a distributed topic merely because "publish-subscribe" is in the name. If you run three application instances, the three channel beans across those instances are three separate objects.

This leads to several architectural decisions:

1. Producers and subscribers within the same application context can communicate directly through the channel.
2. A subscriber starting after an event was already broadcast has no history to replay from this channel.
3. Stopping the process has no built-in message recovery from `PublishSubscribeChannel` itself.
4. When cross-process delivery is needed, add adapters or channels backed by suitable messaging infrastructure.

Do not project broker-specific guarantees—such as durable subscriptions, replay, or acknowledgments—onto a local channel. For a requirement like "never lose order events after commit", design a durable persistence and recovery path, such as a transactional outbox paired with an appropriate messaging system; in-memory fan-out is just one piece of that architecture.

When managing endpoints with Spring, each endpoint's lifecycle governs when it subscribes and unsubscribes its handler. Consequently, an application with all beans defined does not automatically have all subscribers active at every moment. For flows where consumers are mandatory, treat endpoint startup, shutdown, and redeployment as real design scenarios.

## 4. Direct Example: Observing Two Subscribers Receive One Message

The snippet below focuses on the channel contract without using Java DSL yet:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class PublishSubscribeDemo {

    public record OrderPlaced(
            String eventId,
            String orderId,
            BigDecimal amount) {
    }

    public static void main(String[] args) {
        var channel = new PublishSubscribeChannel(true);

        List<String> audit = new ArrayList<>();
        List<String> notifications = new ArrayList<>();

        channel.subscribe(message -> {
            OrderPlaced order = (OrderPlaced) message.getPayload();
            audit.add("AUDIT:" + order.orderId());
        });

        channel.subscribe(message -> {
            OrderPlaced order = (OrderPlaced) message.getPayload();
            notifications.add("NOTIFY:" + order.orderId());
        });

        Message<OrderPlaced> message = MessageBuilder
                .withPayload(new OrderPlaced(
                        "evt-42",
                        "O-42",
                        new BigDecimal("1500000")))
                .setHeader("source", "checkout")
                .build();

        boolean sent = channel.send(message);

        System.out.println(sent);
        System.out.println(audit);
        System.out.println(notifications);
    }
}
~~~

Expected output:

~~~text
true
[AUDIT:O-42]
[NOTIFY:O-42]
~~~

The example chooses `new PublishSubscribeChannel(true)` to require subscribers. A constructor without an executor invokes handlers on the sender's thread. The default constructor `new PublishSubscribeChannel()` also uses the sending thread but does not require subscribers. See [PublishSubscribeChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

Both lists in the example are mutated only on the same thread, which suffices for synchronous observation. When switching to multi-threaded execution, pick thread-safe data structures and synchronization rather than keeping that assumption.

## 5. Broadcast Does Not Mean Parallel Execution

### 5.1. Without an Executor: Sequential Calls on the Sending Thread

For a channel without an executor, picture a single send as follows, assuming dispatch order A, B, C:

~~~text
sending thread:
  send(message)
    -> handler A
    -> handler B
    -> handler C
  send() returns
~~~

If A takes 20 ms, B takes 300 ms, and C takes 10 ms, handler calls alone take roughly 330 ms. One slow branch increases send latency for the whole flow.

When all handlers finish their work inline and return normally, those calls have finished by the time `send()` returns. If a handler only submits work to another system, puts a message into a queue, or starts a background task, `send()` returning does not prove downstream work is finished.

You can configure endpoint order when invocation order must be controlled. However, if B is only allowed to run after A produces a business outcome, a clearer design is chaining A then B inside a single processing branch.

### 5.2. With an Executor: Adding an Execution Boundary

Supplying an executor lets the channel submit handler invocations to that executor. The degree of parallelism depends on the executor; a single-worker executor still executes tasks sequentially. Furthermore, some executors can run tasks immediately on the calling thread, so never deduce "having an executor always switches threads".

With a multi-worker thread pool, the typical model is:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as PublishSubscribeChannel
    participant E as Executor
    participant A as Handler A
    participant B as Handler B
    P->>C: send(message)
    C->>E: Submit task A
    C->>E: Submit task B
    C-->>P: Return send result
    E->>A: Execute
    E->>B: Execute
    Note over A,B: Completion times may differ
~~~

This diagram illustrates one scheduling possibility, not a guarantee that workers only start after `send()` returns.

The executor should be container-managed for a clean lifecycle. Example bean with a bounded queue:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
public ThreadPoolTaskExecutor orderEventExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("order-event-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(15);
    return executor;
}
~~~

This is a method placed inside a `@Configuration` class. Illustrative numbers must be tuned to real workload. With three subscribers, one event can produce three dispatch tasks; pool capacity must account for total branch load.

When an executor rejects a task due to overload or shutdown, the send can fail right at task submission. Earlier branches may already have been submitted. Hence, a send failure does not prove no branch received the event.

## 6. Return Values, Minimum Subscribers, and Risk of Silent Message Loss

Three concepts to separate:

| Setting/scenario | What to observe |
| --- | --- |
| `requireSubscribers=false`, `minSubscribers=0` | With no subscribers, `send()` can still return `true` |
| `requireSubscribers=true` and no subscribers | Dispatch is rejected with an exception |
| `minSubscribers=n` | Sets threshold of counted successful dispatches |
| With executor | Dispatch result does not confirm handlers completed business work |
| `send()` returns `false` | Do not infer that no branches ran |

Example showing only how the send outcome is evaluated:

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setMinSubscribers(2);

channel.subscribe(message -> System.out.println("One subscriber received"));
boolean sent = channel.send(
        MessageBuilder.withPayload("event").build());

System.out.println(sent);
~~~

With this configuration, the single handler is still invoked, yet `sent` is `false`. The two-subscriber threshold is not a pre-check that blocks all dispatching. The dispatcher source executes dispatches and then compares the counted deliveries against `minSubscribers`. See [BroadcastingDispatcher, Spring Integration 6.5.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/BroadcastingDispatcher.java).

Implication for the order example: if the producer sees `false` and replays the entire event, the audit branch may receive it a second time. Define an explicit retry policy and use business keys, such as `eventId` combined with subscriber name, to prevent duplicate side effects.

`requireSubscribers=true` catches the case where zero subscribers exist. It does not confirm the three present subscribers are specifically "audit", "notification", and "analytics"; count does not replace configuration verification and behavioral tests.

## 7. Java DSL: Three Branches with Transformers and Filter

The following example provides a complete configuration for observing fan-out across result queues. The three branches serve different purposes:

- Audit always creates a string record.
- Notification only accepts orders of 1,000,000 or more.
- Analytics extracts the order's monetary amount.

Result queues are solely for observation and testing and do not represent durable storage.

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderFanOutConfig {

    public record OrderPlaced(
            String eventId,
            String orderId,
            BigDecimal amount) {
    }

    @Bean
    public DirectChannel orderEventsInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel auditResults() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel notificationResults() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel analyticsResults() {
        return new QueueChannel(20);
    }

    @Bean
    public IntegrationFlow orderFanOutFlow() {
        return IntegrationFlow.from(orderEventsInput())
                .publishSubscribeChannel(subscribers -> subscribers
                        .subscribe(flow -> flow
                                .<OrderPlaced, String>transform(
                                        order -> "AUDIT:" + order.orderId())
                                .channel(auditResults()))
                        .subscribe(flow -> flow
                                .<OrderPlaced>filter(order ->
                                        order.amount().compareTo(
                                                new BigDecimal("1000000")) >= 0)
                                .<OrderPlaced, String>transform(
                                        order -> "NOTIFY:" + order.orderId())
                                .channel(notificationResults()))
                        .subscribe(flow -> flow
                                .<OrderPlaced, BigDecimal>transform(
                                        OrderPlaced::amount)
                                .channel(analyticsResults())))
                .get();
    }
}
~~~

`orderEventsInput` is the entry point of the flow. The `publishSubscribeChannel` element behind it is the actual broadcast point. Each `subscribe(...)` declares a subflow receiving messages from that point. The DSL supports both inline subflow definitions and extracting subscribers into separate `IntegrationFlow` beans. See [Spring Integration: Sub-flows support](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html).

Expected behavior table:

| Message | `auditResults` | `notificationResults` | `analyticsResults` |
| --- | --- | --- | --- |
| `O-42`, 1,500,000 | `AUDIT:O-42` | `NOTIFY:O-42` | `1500000` |
| `O-43`, 200,000 | `AUDIT:O-43` | No message | `200000` |

The filter only drops messages from the notification branch. It does not cancel processing in the other two branches. If the rule requires "invalid orders must not reach any branch", place a shared validation step before the fan-out point.

Transformers inside a branch produce output only for that branch. The result `AUDIT:O-42` does not become the input payload of the analytics branch.

To switch the example to the executor declared in the previous section, add the executor bean to the same configuration class and change the fan-out call to the `publishSubscribeChannel(orderEventExecutor(), subscribers -> ...)` overload, keeping all three `subscribe` blocks intact. Do not keep both the synchronous and asynchronous flows subscribed simultaneously to `orderEventsInput` for "comparison", because the `DirectChannel` input would treat them as competing consumers.

A step chained immediately after `publishSubscribeChannel(...)` becomes an additional subscriber at the broadcast point. Do not infer from its trailing position in the DSL that it waits for all branches to finish; design an explicit join instead.

The queues in the example have capacity 20. If run continuously without draining results, queues can fill up and stall queue sends. Having finite capacity does not automatically provide a timeout or message-discard policy.

## 8. Immutable Messages Do Not Mean Payloads Are Deep-Copied

`Message` holds payload and headers. Although the header map prevents direct mutation, the payload or object values stored in headers can still be mutable. See [Spring Integration: Message](https://docs.spring.io/spring-integration/reference/message.html).

Therefore, this design is dangerous:

~~~java
// One branch mutates a shared object:
MutableOrder order = (MutableOrder) message.getPayload();
order.setStatus("NOTIFIED");
~~~

If another branch reads `status`, the result can depend on call order. With an executor, the issue can turn into a data race.

Rules to apply to the order problem:

1. Emit a snapshot containing facts that occurred, such as `OrderPlaced`.
2. Use immutable types like `String`, `BigDecimal`, and appropriate time values.
3. If a record contains collections, defensively copy collections and ensure elements also satisfy immutability.
4. A branch wanting to update business state should do so via its own service or create a new result.
5. Do not use mutable objects in headers to pass implicit results between subscribers.

`record` only prevents field references from being reassigned; a `List` inside a record can still hold mutable data. In the example's `OrderPlaced`, `String` and `BigDecimal` components avoid this issue.

Creating a new message per branch also does not deep-copy the payload. Rely on data isolation only when your data model and copying guarantee it.

## 9. Error Handling: Each Branch Can Have a Different Outcome

### 9.1. Synchronous Flow with Default Failure Behavior

Suppose dispatch order is audit, notification, analytics:

~~~text
Audit succeeds
Notification throws exception
Analytics was not called in this dispatch
Producer receives exception from send()
~~~

That is partial processing. If audit already wrote to an external service, an exception propagating back to the producer does not automatically erase that side effect.

You can configure `setIgnoreFailures(true)` so the dispatcher tries remaining handlers when one handler fails. This is a best-effort choice; it does not add retries or turn the outcome into all-succeed. With an executor, ignoring failures can also suppress error message publishing for swallowed exceptions. See [BroadcastingDispatcher: ignoreFailures](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/BroadcastingDispatcher.java).

Do not enable this option just to "keep the flow from turning red". For branches with important side effects, specify how failures are recorded, who retries, and when manual intervention occurs.

### 9.2. Flow via Executor

In a Spring-managed channel, if an executor is configured without a custom `ErrorHandler`, the default strategy sends errors to the channel in the message's `errorChannel` header, or to the default `errorChannel` bean. Without an executor, the channel's `ErrorHandler` is not used to replace direct exception propagation back to the sending thread. See [PublishSubscribeChannel: initialization and error handler](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/PublishSubscribeChannel.java).

Example building a message specifying where asynchronous task errors go:

~~~java
import org.springframework.messaging.MessageHeaders;

Message<OrderFanOutConfig.OrderPlaced> message = MessageBuilder
        .withPayload(new OrderFanOutConfig.OrderPlaced(
                "evt-42",
                "O-42",
                new BigDecimal("1500000")))
        .setHeader(MessageHeaders.ERROR_CHANNEL, orderErrors)
        .build();
~~~

Here `orderErrors` is a declared `MessageChannel` in the application with an error consumer; if using a `QueueChannel` for observation, something must read from it. That header is not an automatic directive turning every synchronous exception into an error message.

Distinguish two failure paths:

| Failure point | What the producer can observe |
| --- | --- |
| No subscribers when required | Exception during send |
| Executor rejects task | Submission failure may surface during send |
| Handler throws exception on worker | Goes to the task's error handler; producer may already have received send result |
| External system fails after handler handed off work | Needs response/monitoring mechanism on that external system |

Branches already submitted to the executor can keep running even if another branch fails. Canceling already-running work requires a separate protocol; broadcast provides no coordinated cancellation.

For accurate observability and retries, include `eventId`, `orderId`, and branch identity where errors are recorded. Each subscriber needs a deduplication strategy suited to its own side effects.

## 10. Transactions and Ordering: Clear Boundaries Needed

When handlers run synchronously on the same thread, they can join an active transaction if the transaction manager and resources are configured compatibly. This does not make all operations across branches a single atomic transaction: an HTTP call or sent email does not automatically roll back with the database.

When dispatching to thread pool workers, do not assume a transaction bound to the sending thread propagates to workers. If a worker needs a database transaction, configure transactions on the worker's processing step.

Example requirement:

> Send notifications only for committed orders, and allow resending if the notification service is temporarily down.

One design to consider is writing the order and an outbox record within the database transaction, then having a separate flow read the outbox to publish events. Then clarify how published records are marked and how consumers deduplicate. Merely adding an executor to fan-out does not satisfy this requirement.

Similarly, if `OrderCancelled` is sent after `OrderPlaced`, a multi-worker pool can finish processing the two events in different orders. For data requiring ordering per `orderId`, design key-based serialization or version checks at subscribers.

## 11. When Gathering Results Is Needed: applySequence and Aggregator

A broadcast for notifications does not necessarily need responses. If the requirement is "invoke three calculations and return one combined result", add a fan-out/fan-in design:

~~~mermaid
flowchart LR
    I["Request"] --> P["PublishSubscribeChannel: applySequence=true"]
    P --> A["Calculate price"]
    P --> B["Calculate shipping fee"]
    P --> C["Calculate tax"]
    A --> R["Shared result channel"]
    B --> R
    C --> R
    R --> G["Aggregator"]
    G --> O["One aggregated result"]
~~~

Channel configuration:

~~~java
@Bean
public PublishSubscribeChannel quoteRequests() {
    var channel = new PublishSubscribeChannel(true);
    channel.setApplySequence(true);
    return channel;
}
~~~

`applySequence` defaults to `false`. When enabled, the channel adds correlation and sequence headers to messages sent to subscribers. With three direct subscribers, branches receive corresponding sequence numbers and sequence size three. Messages with distinct headers still share the same payload reference. See [Spring Integration: PublishSubscribeChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

By default, an aggregator groups by `correlationId` and checks completion against sequence size. Branches must send results to the aggregation channel while preserving the required headers. See [Spring Integration: Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html).

`applySequence=true` neither creates an aggregator nor waits automatically:

- If a branch ends with a handler that produces no reply, a result will be missing.
- If a filter drops a message, the aggregator does not automatically know that branch "finished with no result".
- If a branch emits multiple results, the one-result-per-sequence-position convention no longer fits.
- If a branch is slow or fails, configure timeouts and incomplete-group handling.

Applying this to the order example: you cannot blindly turn on `applySequence` and aggregate all three branches, because the notification filter can drop messages. One option is having the notification branch return an explicit result such as `SKIPPED` when no notification is needed. Another option is designing correlation and release strategies around a different business contract.

Responses should include role labels such as `PRICE`, `SHIPPING`, or `TAX`, instead of inferring roles from element position in the returned list.

## 12. Gateway: One Calling API Does Not Automatically Combine Multiple Replies

You can use a messaging gateway so business code invokes an interface:

~~~java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orderEventsInput")
public interface OrderEventGateway {

    void publish(OrderFanOutConfig.OrderPlaced event);
}
~~~

The gateway must be registered per application configuration, such as via `@IntegrationComponentScan` on the package containing the interface. Its purpose is hiding the `MessageChannel` API from callers; the gateway does not alter the broadcast contract of the flow behind it. See [Spring Integration: Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html).

With a `void` method, the API signals the caller does not expect a business reply. That does not automatically make the call asynchronous: if the downstream flow processes synchronously, the caller still bears processing latency and can receive corresponding exceptions.

If the API must return a `QuoteSummary` from multiple branches, ensure only one aggregated result returns to the gateway past the aggregator step. Do not let three subscribers send three competing replies to the reply path expecting the gateway to turn them into a list automatically.

In the order problem, also clarify what the API name "publish" means: accepted by the channel, durably persisted, or completed by all subscribers. The method signature alone cannot express those guarantees unless the application contract states them explicitly.

## 13. Testing Fan-Out Behavior

The test class below accompanies `OrderFanOutConfig` from Section 7 and uses JUnit Jupiter. It verifies observable effects across the three branches rather than only asserting `send()`'s return value.

~~~java
import java.math.BigDecimal;

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

class OrderFanOutTest {

    @Test
    void highValueOrderReachesAllThreeBranches() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFanOutConfig.class)) {

            MessageChannel input = context.getBean(
                    "orderEventsInput", MessageChannel.class);
            QueueChannel audit = context.getBean(
                    "auditResults", QueueChannel.class);
            QueueChannel notification = context.getBean(
                    "notificationResults", QueueChannel.class);
            QueueChannel analytics = context.getBean(
                    "analyticsResults", QueueChannel.class);

            boolean sent = input.send(MessageBuilder.withPayload(
                    new OrderFanOutConfig.OrderPlaced(
                            "evt-42",
                            "O-42",
                            new BigDecimal("1500000"))).build());

            assertTrue(sent);
            assertPayload("AUDIT:O-42", audit.receive(0));
            assertPayload("NOTIFY:O-42", notification.receive(0));
            assertPayload(new BigDecimal("1500000"), analytics.receive(0));

            assertNull(audit.receive(0));
            assertNull(notification.receive(0));
            assertNull(analytics.receive(0));
        }
    }

    @Test
    void lowValueOrderIsFilteredOnlyInNotificationBranch() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFanOutConfig.class)) {

            MessageChannel input = context.getBean(
                    "orderEventsInput", MessageChannel.class);
            QueueChannel audit = context.getBean(
                    "auditResults", QueueChannel.class);
            QueueChannel notification = context.getBean(
                    "notificationResults", QueueChannel.class);
            QueueChannel analytics = context.getBean(
                    "analyticsResults", QueueChannel.class);

            assertTrue(input.send(MessageBuilder.withPayload(
                    new OrderFanOutConfig.OrderPlaced(
                            "evt-43",
                            "O-43",
                            new BigDecimal("200000"))).build()));

            assertPayload("AUDIT:O-43", audit.receive(0));
            assertNull(notification.receive(0));
            assertPayload(new BigDecimal("200000"), analytics.receive(0));
        }
    }

    private static void assertPayload(Object expected, Message<?> actual) {
        assertNotNull(actual);
        assertEquals(expected, actual.getPayload());
    }
}
~~~

In this synchronous configuration, by the time send completes, the steps placing results into queues have already run, so `receive(0)` is appropriate. When using an executor, wait for results with a finite timeout such as `receive(2000)`, or synchronize with a latch at the completion point being verified. Do not use `Thread.sleep(...)` as proof of completion.

For a branch that must not emit output in an asynchronous test, an immediate read with timeout 0 does not prove output will not arrive later. Wait for that branch's completion signal or observe over a bounded window aligned with the test contract.

Additional cases to verify in real deployments:

| Scenario | Evidence to collect |
| --- | --- |
| No subscribers when required | Producer receives send error |
| One handler fails synchronously | Identify which branches ran vs. did not run per configured order |
| One handler fails on a worker | Error message arrives at the right error path |
| One branch is very slow | Bounded wait limits and detection mechanism exist |
| Replaying the same `eventId` | Subscriber side effects are deduplicated per requirements |
| Executor overloaded | Submission failures and partial-processing state are observable |
| Fan-in missing one result | Aggregator has timeout/incomplete-group handling |

These are test code and scenarios for learners to practice in their own applications.

## 14. Choosing the Right Model for Each Requirement

| Requirement | Design direction |
| --- | --- |
| Every event must reach audit, notification, and analytics | `PublishSubscribeChannel` with dedicated subscribers |
| Choose one processing branch based on content | Router |
| Multiple workers share processing each job | Channel with point-to-point semantics |
| A branch receives events but only processes valid ones | Filter inside the branch |
| Multiple calculations must return a single answer | Fan-out combined with aggregator and reply contract |
| All application instances must receive events | Cross-process messaging infrastructure with clear subscription semantics |
| Events must recover after crashes | Durable persistence, acknowledgments, retries, and deduplication |

A solid design for `OrderPlaced` begins with "who needs to know about this event and what does each party commit to doing", and only then selects synchronous vs. executor execution, filter placement, error paths, and testing strategy.

The takeaway when reading an integration flow is: **publish-subscribe identifies who receives the message; which threads they run on, when they finish, and how they recover must be designed separately**.

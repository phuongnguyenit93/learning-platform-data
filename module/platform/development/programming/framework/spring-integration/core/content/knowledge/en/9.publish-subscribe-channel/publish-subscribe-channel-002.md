# All Subscribers Receive the Same Message

## 1. The Problem: One Event, Multiple Interested Parties

In the **PublishSubscribeChannel** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson explains how to broadcast a message to multiple subscribers and how to interpret the word "same" accurately. This forms the foundation for wiring endpoints into integration flows using Java configuration and Java DSL.

Suppose the sales system has accepted order `ORD-1042`. Three needs arise from that same event:

- Audit records that the order has been accepted.
- The notification department prepares a confirmation message for the customer.
- The statistics department updates the daily order count.

If all three need to know about the event, the flow must broadcast it to all three branches. Assigning each order to only one of the three branches would not solve the problem.

~~~mermaid
flowchart LR
    P["Producer: OrderAccepted"] --> C["PublishSubscribeChannel"]
    C --> A["Subscriber A: audit"]
    C --> N["Subscriber B: notification"]
    C --> S["Subscriber C: statistics"]
~~~

`PublishSubscribeChannel` broadcasts to subscribed `MessageHandler`s. It is a channel that pushes messages to handlers, not a channel where consumers call `receive()` to pull messages. [Message Channel Implementations documentation](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

After this lesson, you will be able to:

1. Choose broadcasting when multiple functions need the same event.
2. Distinguish between the same event, the same `Message` instance, and the same payload instance.
3. Subscribe multiple endpoints to one channel using annotations or Java DSL.
4. Explain the limitations when a subscriber fails, runs slowly, or executes asynchronously.
5. Write tests that observe the message at each branch.

## 2. What Does "All Subscribers" Mean?

A single call to `send(message)` triggers a single delivery pass across the channel's set of subscribers at the moment dispatching occurs. A subscriber is the handler wired directly to the channel; a branch downstream of that handler may contain multiple additional steps.

In the order example:

| Component | Role |
| --- | --- |
| Producer | Creates the message containing the `OrderAccepted` event |
| Channel | Distributes the event to subscribers |
| Audit endpoint | Connects the channel to audit-recording logic |
| Notification endpoint | Connects the channel to notification-creation logic |
| Statistics endpoint | Connects the channel to statistics-updating logic |

There are three milestones to distinguish:

- **Dispatched:** the channel has handed the message to the handler or submitted the task to an executor.
- **Finished processing:** the branch's logic has completed.
- **Business effect produced:** for example, the audit record has committed or the email has been accepted by the external system.

These three milestones can occur at different times. When designing a flow, you must specify which milestone serves as the use case's success criterion.

For example, the requirement "the order is accepted only after audit succeeds" differs from "the order is accepted and the notification system processes it later". A plain broadcast diagram alone cannot imply the success policy for both requirements.

## 3. Broadcasting vs. Work Distribution

`DirectChannel` has point-to-point semantics: each message is processed by one selected subscriber, even if the channel has multiple subscribers. `QueueChannel` also delivers each message to the single consumer that polls it. Conversely, `PublishSubscribeChannel` is meant for multiple handlers receiving the same message together. [Comparison of channel types](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

| Design Scenario | Appropriate Wiring |
| --- | --- |
| Audit, notification, and statistics all need every order event | Publish-subscribe |
| Three workers perform the same kind of task to share load | Point-to-point |
| An event must go through step A, then A's result goes to B | Endpoint chain |
| Choose a processing branch based on order type or delivery region | Router |

If three workers all perform "send confirmation email", broadcasting could send three emails for one order. If three distinct functions all need to know about the event, load-sharing leaves functions missing out.

A combined topology is often clearer to express:

~~~text
                         -> audit
OrderAccepted -> pub-sub -> notification queue -> notification workers
                         -> statistics
~~~

In this design, the notification branch receives only one delivery from the broadcast point. Load-sharing among workers happens behind that boundary.

## 4. Three Levels of Meaning for "Same Message"

### 4.1. Same Business Event

Audit and statistics may both process event `EVT-7301` even after messages pass through different transformers. Therefore, examples throughout this lesson use `eventId` to identify the business event.

`orderId` identifies the order; a single order can produce multiple events. Thus, using `orderId` alone to deduplicate all event types can mistakenly drop valid updates.

### 4.2. Same Message Object and Same Payload

With the default configuration `applySequence=false`, the channel can pass the exact same `Message` object to subscribers. When `applySequence=true` is enabled, the channel creates messages with separate sequence headers for each subscriber while still sharing the same payload reference. This is not a deep copy of the business data. [PublishSubscribeChannel configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

| What to Verify | Illustrative Check |
| --- | --- |
| Two branches process the same business event | Compare `eventId` |
| Two variables point to the same message | `assertSame(first, second)` |
| Two messages share the same payload | `assertSame(first.getPayload(), second.getPayload())` |

Checking message identity is useful for learning how dispatching behaves under a given configuration. Business tests should prioritize `eventId` and the expected outcome of each branch.

### 4.3. An Immutable Message Does Not Make All Data Immutable

`GenericMessage` and the standard `MessageHeaders` structure do not allow replacing the payload or directly mutating the header map after creation. However, the payload object itself or a header value can still be a mutable object. The application must decide on and protect the immutability of those objects. [Message and MessageBuilder contract](https://docs.spring.io/spring-integration/reference/7.0/message.html)

An example that should not be used as a contract between branches:

~~~java
// Suppose payload is a shared mutable Map.
payload.put("notificationStatus", "SENT");
~~~

Audit could observe data that was mutated by the notification branch. If branches run concurrently, the result also depends on read and write timing.

The example below uses a record with `String` and `BigDecimal` fields:

~~~java
import java.math.BigDecimal;

public record OrderAccepted(
        String eventId,
        String orderId,
        BigDecimal total) {
}
~~~

Choosing this data type allows all three branches to read the event without modifying it. If you add a collection to a record, consider defensive copies and the immutability of its elements as well; a record does not perform deep copies automatically.

A transformer in the notification branch should produce its own output payload, such as an email body string. Audit and statistics continue working with their input event.

## 5. Observing Broadcast in Plain Java

This example uses `PublishSubscribeChannel` directly to inspect the message object received by each handler. Assume the project has `spring-integration-core` and the `OrderAccepted` record from the previous section is in the same package. Examples use Java 17+ syntax.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class BroadcastDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel events =
                new PublishSubscribeChannel(true);

        List<Message<?>> auditInbox = new ArrayList<>();
        List<Message<?>> notificationInbox = new ArrayList<>();
        List<Message<?>> statisticsInbox = new ArrayList<>();

        events.subscribe(message -> auditInbox.add(message));
        events.subscribe(message -> notificationInbox.add(message));
        events.subscribe(message -> statisticsInbox.add(message));

        OrderAccepted event = new OrderAccepted(
                "EVT-7301", "ORD-1042", new BigDecimal("350000"));

        Message<OrderAccepted> sent = MessageBuilder.withPayload(event)
                .setHeader("eventType", "OrderAccepted")
                .build();

        boolean accepted = events.send(sent);

        System.out.println("send=" + accepted);
        System.out.println("audit=" + auditInbox.size());
        System.out.println("notification=" + notificationInbox.size());
        System.out.println("statistics=" + statisticsInbox.size());

        System.out.println(
                "sameMessage=" + (
                        auditInbox.get(0) == sent
                        && notificationInbox.get(0) == sent
                        && statisticsInbox.get(0) == sent));
    }
}
~~~

Expected output:

~~~text
send=true
audit=1
notification=1
statistics=1
sameMessage=true
~~~

The example passes no executor, so handlers execute on the sending thread. Therefore, once `send` returns normally, all three lists have already been updated. Passing `true` to the constructor enables `requireSubscribers`, which detects when there are no subscribers; this option was introduced in Spring Integration 5.4.3. [PublishSubscribeChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html)

The lists in the example merely act as observation inboxes. They do not represent an event store or a durable delivery mechanism.

## 6. Wiring Three Endpoints with Java Configuration

In a Spring application, endpoints handle registering handlers and invoking business methods. The following configuration illustrates three service activators sharing one channel:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.channel.PublishSubscribeChannel;

@Configuration
@EnableIntegration
public class OrderEventsConfiguration {

    @Bean
    public PublishSubscribeChannel orderAcceptedEvents() {
        return new PublishSubscribeChannel(true);
    }

    @ServiceActivator(inputChannel = "orderAcceptedEvents")
    public void audit(OrderAccepted event) {
        System.out.println(
                "AUDIT: " + event.eventId() + " / " + event.orderId());
    }

    @ServiceActivator(inputChannel = "orderAcceptedEvents")
    public void notifyCustomer(OrderAccepted event) {
        System.out.println(
                "NOTIFY: order " + event.orderId() + " has been accepted");
    }

    @ServiceActivator(inputChannel = "orderAcceptedEvents")
    public void updateStatistics(OrderAccepted event) {
        System.out.println(
                "STATISTICS: adding order with total " + event.total());
    }
}
~~~

Example producer running after the application context has started:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class OrderEventPublisher {

    private final MessageChannel events;

    public OrderEventPublisher(
            @Qualifier("orderAcceptedEvents") MessageChannel events) {
        this.events = events;
    }

    public boolean publish(OrderAccepted event) {
        return events.send(
                MessageBuilder.withPayload(event).build());
    }
}
~~~

Register `OrderEventPublisher` as a bean if you want Spring to inject its dependency. The print statements only represent call sites to business logic; a real application calls the corresponding audit, notification, and statistics services.

The consumers here return `void` because the example only publishes events. If the producer needs a single aggregated result from multiple branches, explicitly design replies, an aggregator, and completion conditions rather than inferring a result from a successful send.

You can place a messaging gateway in front of the channel so the business layer only calls an interface. A `void publish(OrderAccepted event)` method signature fits event-publishing intent; the gateway itself does not replace a response aggregation mechanism.

## 7. Expressing Branches with Java DSL

The standalone example below describes a flow with two sub-subscribers and a continuation branch after the publish-subscribe point. Choose this configuration instead of the annotation example when practicing the same topology to avoid accidentally registering extra consumers.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderEventDslConfiguration {

    @Bean
    public IntegrationFlow orderAcceptedFlow() {
        return IntegrationFlow.from("orderAcceptedInput")
                .publishSubscribeChannel(subscribers -> subscribers
                        .subscribe(audit -> audit
                                .handle(message -> System.out.println(
                                        "AUDIT: " + message.getPayload())))
                        .subscribe(notification -> notification
                                .<OrderAccepted, String>transform(event ->
                                        "Order received " + event.orderId())
                                .handle(message -> System.out.println(
                                        "NOTIFY: " + message.getPayload()))))
                .handle(message -> System.out.println(
                        "STATISTICS: " + message.getPayload()))
                .get();
    }
}
~~~

Send a message to the `orderAcceptedInput` channel after the context starts. In this flow:

1. The audit branch receives the event and ends at its handler.
2. The notification branch transforms the event into a string and ends at its handler.
3. The statistics handler wired after `publishSubscribeChannel(...)` also receives the message through the broadcast point.

That continuation branch is not a step that waits for the two sub-branches to finish and aggregates their results. Subflow structure and continuation branches are illustrated in the [Java DSL subflows documentation](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html).

The notification branch's transformer serves that branch's own output contract. You should not use a transformation inside the notification branch as an implicit way to pass data to statistics.

If you want all three branches shown explicitly as three `subscribe(...)` calls, you can make statistics the third sub-subscriber and end the flow at the publish-subscribe step.

## 8. Synchronous, Asynchronous, and Errors

### 8.1. Synchronous Broadcast Can Still Be Blocked Mid-Way

With a channel that has no executor, handlers run sequentially on the sending thread. Under the default `ignoreFailures=false`, an error from one handler causes dispatch to throw an exception; handlers not yet invoked may not receive the message. `setIgnoreFailures(true)` allows the dispatcher to continue when a handler fails, but does not fix or automatically retry failed business logic. [API for ignoreFailures](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html)

Suppose in one run, audit is invoked before notification and statistics:

~~~text
audit: succeeds
notification: throws exception
statistics: may not have been called
~~~

Therefore, the phrase "all subscribers receive the same message" describes the broadcast intent, subject to execution conditions. It is not a guarantee that every branch always succeeds even if other branches fail.

In the sales problem, define a policy for each branch:

| Branch | Design Question to Answer |
| --- | --- |
| Audit | If audit cannot be recorded, can the order be considered accepted? |
| Notification | Can this branch be retried separately a few minutes later? |
| Statistics | Can it be recomputed from the business source of truth? |

If a mandatory sequence "record audit first, then send notification" is required, express it as sequential steps or an orchestration workflow. Do not rely on subscription order to express business dependencies.

### 8.2. Executors Change the Observation Point

You can supply a Spring-managed executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

// Place these methods inside a @Configuration class.
@Bean
public ThreadPoolTaskExecutor orderEventExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(6);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("order-event-");
    return executor;
}

@Bean
public PublishSubscribeChannel asyncOrderEvents(
        ThreadPoolTaskExecutor orderEventExecutor) {
    return new PublishSubscribeChannel(orderEventExecutor, true);
}
~~~

Subscribe consumers to `asyncOrderEvents` when using this configuration. When the executor runs on worker threads, the moment `send` returns is not the moment all branches finish processing. Completion order among branches can also vary.

For tests, replace `ArrayList` with a thread-safe structure and wait for completion conditions with a timeout. Do not infer that a branch succeeded just because the sending thread moved past the next statement.

An executor also needs an overflow policy. A single message creates work for multiple branches, so size capacity according to the total number of generated tasks and each branch's processing time. With an executor configured to run tasks on the calling thread under overload, you cannot assume every handler always runs on another thread.

### 8.3. Observing Asynchronous Errors

In a standard Spring configuration using an executor, `MessagePublishingErrorHandler` turns errors into messages sent to the channel in the `errorChannel` header, or to the global `errorChannel` bean if the header is absent. Without an executor, the channel's `ErrorHandler` does not replace the exception returning to the calling thread. [Channel error handling configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

Example operational design for the notification branch:

~~~text
OrderAccepted
    -> notification branch
        -> send succeeds: record processed eventId
        -> send fails: store eventId, branch name, and cause for retry
~~~

To prevent retries from creating duplicate notifications, you can use a business key `(eventId, branchName)`. Determine how to record the key in a way compatible with the external system; checking a key and sending an email does not automatically become an atomic transaction.

If audit already succeeded before notification failed, retrying the whole send could run audit a second time. Therefore, retry scope is also a design decision, not merely calling `send` again.

## 9. No Subscribers and the Meaning of send()

By default, `minSubscribers=0` allows a send with no subscribers to still be considered successful. `requireSubscribers=true` helps detect when a channel has no handlers. Meanwhile, `minSubscribers` expresses a minimum subscriber threshold; when using an executor, this result does not prove business tasks have completed. [send and minSubscribers semantics](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Examples of different requirement levels:

~~~java
// Must have at least one subscriber.
PublishSubscribeChannel events =
        new PublishSubscribeChannel(true);

// Set the subscriber count threshold for evaluating a dispatch.
events.setMinSubscribers(3);
~~~

A threshold of `3` does not verify that those three are specifically audit, notification, and statistics. If two notification consumers and one audit consumer are misconfigured, meeting the count still fails the business requirement.

Therefore, at application startup and in integration tests, verify the topology by behavior: publish an event with a known `eventId`, then observe the output of each expected function.

## 10. Sequence Headers and Result Aggregation

If the design requires aggregating results from branches, you can enable:

~~~java
PublishSubscribeChannel requests =
        new PublishSubscribeChannel(true);

requests.setApplySequence(true);
~~~

The channel adds correlation information and `sequenceNumber`, `sequenceSize` headers so messages from a single delivery can be correlated during aggregation. Each subscriber receives a message with its own sequence number. [applySequence configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

Example risk check before accepting an order:

~~~text
OrderRiskRequest -> publish-subscribe
                     -> credit limit check -> RiskResult
                     -> address check -> RiskResult
                     -> fraud check -> RiskResult
                                             |
                                             v
                                   shared result channel
                                             |
                                             v
                                         aggregator
~~~

For this diagram to be meaningful in an application, you must decide:

- How many results each branch produces.
- How correlation headers are preserved across transformation steps.
- Whether an error result participates in the decision or routes to a separate handling flow.
- After how long a group is considered missing results.
- Whether an incomplete group is rejected, partially accepted, or routed to manual review.

If a filter drops a message in one branch without producing a fallback result, the expectation "three branches yield three results" no longer holds for that order. Enabling `applySequence` does not automatically synthesize missing results or configure an aggregator.

For the example that only records audit, sends notifications, and updates statistics independently, do not add an aggregator merely to give the diagram a common ending step.

## 11. Tests Illustrating Broadcast Semantics

The JUnit 5 tests below focus on behavior at the channel boundary. They serve as examples for learners to include in a project with `spring-integration-core` and JUnit Jupiter.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.*;

class PublishSubscribeChannelTest {

    @Test
    void everySubscriberReceivesTheOriginalMessageByDefault() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);

        List<Message<?>> first = new ArrayList<>();
        List<Message<?>> second = new ArrayList<>();
        List<Message<?>> third = new ArrayList<>();

        channel.subscribe(message -> first.add(message));
        channel.subscribe(message -> second.add(message));
        channel.subscribe(message -> third.add(message));

        Message<String> sent = new GenericMessage<>("EVT-7301");

        assertTrue(channel.send(sent));

        assertEquals(1, first.size());
        assertEquals(1, second.size());
        assertEquals(1, third.size());

        assertSame(sent, first.get(0));
        assertSame(sent, second.get(0));
        assertSame(sent, third.get(0));
    }

    @Test
    void sequenceCreatesSeparateEnvelopesWithTheSamePayload() {
        PublishSubscribeChannel channel =
                new PublishSubscribeChannel(true);
        channel.setApplySequence(true);

        List<Message<?>> received = new ArrayList<>();
        channel.subscribe(message -> received.add(message));
        channel.subscribe(message -> received.add(message));

        Message<String> sent = new GenericMessage<>("EVT-7301");

        assertTrue(channel.send(sent));
        assertEquals(2, received.size());

        Message<?> first = received.get(0);
        Message<?> second = received.get(1);

        assertNotSame(sent, first);
        assertNotSame(sent, second);
        assertNotSame(first, second);

        assertSame(sent.getPayload(), first.getPayload());
        assertSame(sent.getPayload(), second.getPayload());

        assertEquals(2, first.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE));
        assertEquals(2, second.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE));

        assertNotEquals(
                first.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER),
                second.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER));

        assertNotNull(first.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID));
        assertEquals(
                first.getHeaders().get(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID),
                second.getHeaders().get(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID));
    }
}
~~~

The first test verifies that all three branches receive the message. Checking `send()==true` alone would not prove that.

The second test verifies separate message envelopes with a shared payload. It does not assume which business branch must receive `sequenceNumber=1`.

To test a real flow, replace the inbox lists with observable outputs from audit, notification, and statistics. You should add scenarios for:

| Scenario | What to Observe |
| --- | --- |
| A valid event | Each function produces the right result for the same `eventId` |
| One branch throws an exception | Continue or stop policy matches requirements |
| No subscribers | Required-subscriber configuration detects the failure |
| Resending the same event | Duplicate business effects are controlled |
| With an executor | Wait for all results with a condition and timeout |
| One branch filters out data | Policy for gathering missing results remains well-defined |

These examples do not need a Spring context to illustrate the synchronous dispatcher. Testing annotations, DSL, gateways, and endpoint lifecycles does require the corresponding context.

## 12. Practice Exercise

Design a flow receiving `OrderAccepted` with three branches:

1. Audit logs `eventId` and `orderId`.
2. Notification transforms the event into a confirmation message.
3. Statistics only accepts orders with `total >= 100000`.

Perform two sends: order `50000` and order `350000`. Expected results:

| Branch | Order 50000 | Order 350000 |
| --- | --- | --- |
| Audit | Receives event | Receives event |
| Notification | Creates notification | Creates notification |
| Statistics | Filtered out at branch | Updates statistics |

The point to explain is that the subscriber at the start of the statistics branch can still receive the event, and only then does the filter inside the branch drop it. That does not contradict the broadcast mechanism of the upstream channel.

Next, intentionally trigger an error in the notification branch and describe the outcome under two configurations:

- Synchronous channel, `ignoreFailures=false`.
- Executor-backed channel, with an error-handling consumer.

For each configuration, note what the producer observes, which branches completed, and how to handle the missing work. If the requirement is upgraded to "only accept an order when results from all three checks are present", draw an additional reply flow and aggregator with a concrete timeout policy.

## 13. Decisions to Keep Clear When Using PublishSubscribeChannel

`PublishSubscribeChannel` is an in-process component by default. If you need to persist events so an offline consumer can process them later, or if you need cross-service communication, add a storage mechanism or messaging bridge suited to that requirement.

Before using it in a concrete flow, answer:

- Does every branch need the event, or are workers merely sharing load for the same job?
- Are the event and attached data safe when read concurrently by multiple branches?
- If one branch fails, must other branches continue, stop, or compensate?
- At which milestone is producer success defined?
- Are retries applied to the entire broadcast or to a single branch?
- If a combined result is needed, where are replies gathered and how are missing responses handled?

For the order event in this lesson, a clear contract is: the producer emits `OrderAccepted`, three functions care about that `eventId`, and each function is responsible for its own outcome and error policy. When stronger guarantees are needed, the flow contract must explicitly capture those guarantees.

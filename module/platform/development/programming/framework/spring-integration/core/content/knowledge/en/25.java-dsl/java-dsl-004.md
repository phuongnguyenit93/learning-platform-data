# from MessageSource

In the **Java DSL** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson presents how to use `IntegrationFlow.from(MessageSource<?>)` to initiate a message flow from a periodically polled source. This is the junction between external data retrieval and core components such as `Message`, `MessageChannel`, endpoint, filter, and transformer.

The running scenario is a system that pulls pending orders: the source creates messages with tracing metadata, the poller controls the fetch schedule, and the flow validates and normalizes each order. This initialization style fits when the application must actively ask a data source whether new items are available.

## 1. Objectives and Scope

After this lesson, you will be able to:

- Implement `MessageSource<T>` and accurately explain the meaning of `receive()` returning a message or `null`.
- Declare the source and `IntegrationFlow` with Java DSL, configuring the poller and endpoint lifecycle.
- Distinguish a polled source from an input channel, a `Supplier`, and an event-driven adapter.
- Predict the number of messages per poll cycle, where downstream execution occurs, and how errors route to an error channel.
- Design tests for the source and flow without depending on an arbitrary `Thread.sleep()` duration.

The examples use Java 17 and the Spring Integration 6.x API in the `IntegrationFlow.from(...)` style. The runtime environment requires `spring-integration-core` along with compatible Spring libraries; the testing section uses JUnit Jupiter. Manage versions using a BOM or your project's dependency management mechanism.

The configuration examples use plain Spring with `@EnableIntegration` and do not require Spring Boot. Snippets marked as "alternatives" are different options for the same configuration point, not flows meant to run concurrently.

## 2. MessageSource Is a Source Actively Polled by the Application

`MessageSource<T>` belongs to the package:

~~~java
import org.springframework.integration.core.MessageSource;
~~~

The main contract of the interface is:

~~~java
Message<T> receive();
~~~

`T` is the **payload** type. For example, `MessageSource<Order>` returns `Message<Order>`; do not declare it as `MessageSource<Message<Order>>` just because the method returns a message.

Each time it is called, the source has three possibilities:

| Result | Meaning | Expected behavior |
|---|---|---|
| A `Message<T>` | Data is available to enter the flow | The adapter sends the message to the next channel |
| `null` | No data is available on this poll | No message is sent and the current poll cycle ends |
| Throws an exception | The fetch operation failed | The error enters the polling task's error-handling mechanism |

Returning `null` does not permanently close the source. The poller can still call the source again on the next cycle. A source should also not turn a connection error into `null`, because then "empty source" and "unable to read source" become indistinguishable. The contract for returning a message or `null` is described in [MessageSource Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessageSource.html).

This interface differs from `org.springframework.context.MessageSource`, which is used for looking up message strings and UI internationalization.

### 2.1. Creating a Message Instead of Returning Only a Payload

~~~java
MessageSource<String> source = () ->
        MessageBuilder.withPayload("ORDER-101")
                .setHeader("sourceSystem", "legacy-order-system")
                .build();
~~~

This snippet requires importing `org.springframework.integration.support.MessageBuilder`. Because it produces data on every call, you must bound the number of messages per poll cycle in real usage.

The advantage of `MessageSource` is that you control both the payload and headers right at the system's ingress boundary. For an order source, headers can carry the source system name, a business key, and a reconciliation ID. Use a stable business key to detect duplicate processing; do not treat `MessageHeaders.ID` as a durable business key across re-reads of data.

## 3. Which Components Actually Run at the Start of the Flow

Declaring `from(source)` does not mean the source itself spawns threads or emits messages on its own. The flow needs an endpoint that executes the polling:

~~~mermaid
flowchart LR
    T["Trigger and scheduler"] --> A["SourcePollingChannelAdapter"]
    A -->|"calls receive()"| S["MessageSource"]
    S -->|"Message or null"| A
    A -->|"sends only when Message present"| C["MessageChannel"]
    C --> F["Filter"]
    F --> X["Transformer"]
    X --> Q["Result Channel"]
~~~

There are four distinct responsibilities:

| Component | Responsibility |
|---|---|
| `MessageSource` | Knows how to retrieve data and build a message |
| `SourcePollingChannelAdapter` | Invokes the source and sends messages into the flow |
| Poller | Describes the schedule, max messages, and polling options |
| Downstream endpoints | Process the message after it enters the system |

Therefore, the source should focus on accessing data. Business filtering, normalization, routing, or aggregation steps can reside in the flow so they are visible and testable separately.

Java DSL supports `MessageSource` directly and allows configuring the adapter via the second parameter of `from(...)`. See [Inbound Channel Adapters in Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-inbound-adapters.html).

## 4. Syntax of from(MessageSource)

The two main usages are:

~~~java
IntegrationFlow.from(source)
~~~

and:

~~~java
IntegrationFlow.from(source, endpoint -> endpoint
        .id("orderInbound")
        .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                .maxMessagesPerPoll(5)))
~~~

In the second form:

- `source` is the `MessageSource<?>` instance.
- `endpoint` is a `SourcePollingChannelAdapterSpec`, where the inbound endpoint is configured.
- `poller(...)` supplies the polling configuration.
- Subsequent calls like `filter(...)`, `transform(...)`, or `handle(...)` describe downstream processing.
- `get()` finishes the builder to produce the `IntegrationFlow` object registered in the application context.

A standalone `MessageSource` bean does not create a polling schedule by itself. Likewise, a builder not registered as a flow in the context does not create a running integration application.

### 4.1. Distinguishing Flow ID and Adapter ID

~~~java
@Bean
IntegrationFlow orderPollingFlow(MessageSource<Order> source) {
    return IntegrationFlow.from(source, endpoint -> endpoint
                    .id("orderInbound")
                    .poller(Pollers.fixedDelay(Duration.ofSeconds(1))))
            .handle(message -> {
                // Handle the message at the end of the flow.
            })
            .get();
}
~~~

The flow bean is named `orderPollingFlow`; the inbound endpoint has ID `orderInbound`. When you need to start or stop data retrieval independently, name the adapter explicitly and operate on the corresponding `SourcePollingChannelAdapter` bean.

Here, `Order` is the domain data type defined in the complete example below.

## 5. Complete Example: Polling and Normalizing Orders

Each message contains one order. The flow drops orders with invalid quantities, normalizes the product name, and puts the result into a `QueueChannel` for a receiver or test to read.

The example classes can be placed in package `demo.integration`.

~~~java
package demo.integration;

import java.time.Duration;
import java.util.Locale;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.support.MessageBuilder;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderPollingConfig {

    public record Order(String id, String product, int quantity) {
    }

    public static final class OrderInbox {

        private final Queue<Order> orders = new ConcurrentLinkedQueue<>();

        public void add(Order order) {
            orders.add(order);
        }

        public Order poll() {
            return orders.poll();
        }
    }

    @Bean
    OrderInbox orderInbox() {
        return new OrderInbox();
    }

    @Bean
    MessageSource<Order> orderMessageSource(OrderInbox inbox) {
        return () -> {
            Order order = inbox.poll();

            if (order == null) {
                return null;
            }

            return MessageBuilder.withPayload(order)
                    .setHeader("sourceSystem", "demo-orders")
                    .setHeader("businessKey", order.id())
                    .build();
        };
    }

    @Bean
    QueueChannel acceptedOrders() {
        return new QueueChannel(20);
    }

    @Bean
    QueueChannel orderPollingErrors() {
        return new QueueChannel(20);
    }

    @Bean
    IntegrationFlow orderPollingFlow(
            MessageSource<Order> orderMessageSource,
            @Qualifier("acceptedOrders") QueueChannel acceptedOrders) {

        return IntegrationFlow.from(orderMessageSource, endpoint -> endpoint
                        .id("orderInbound")
                        .autoStartup(false)
                        .poller(Pollers.fixedDelay(Duration.ofMillis(100))
                                .maxMessagesPerPoll(2)
                                .errorChannel("orderPollingErrors")))
                .<Order>filter(order -> order.quantity() > 0)
                .<Order, Order>transform(order -> new Order(
                        order.id(),
                        order.product().strip().toUpperCase(Locale.ROOT),
                        order.quantity()))
                .channel(acceptedOrders)
                .get();
    }
}
~~~

### 5.1. Why Is the Configuration Written This Way?

`OrderInbox` holds domain objects that have not yet entered the messaging system. It uses `ConcurrentLinkedQueue` so additions and removals are safe between the test thread and the polling thread.

`orderMessageSource` turns an `Order` into a `Message<Order>`. When the inbox is empty, it immediately returns `null`. The source does not need to know which filter or transformer sits downstream.

`acceptedOrders` is a `QueueChannel` holding **processed messages**. It differs from the queue inside `OrderInbox`, which holds **domain objects not yet wrapped in messages**.

Both channel beans have type `QueueChannel`, so the output parameter uses `@Qualifier` to select the exact channel needed. Passing dependencies via `@Bean` method parameters also avoids relying on inter-method calls within the configuration class.

`autoStartup(false)` keeps the adapter stopped after the context is created, allowing data to be loaded before running tests. When you want the application to poll automatically at startup, omit this option or set it to `true`.

`filter(...)` by default drops messages that fail the condition without throwing an exception. In the example, the dropped order has already been removed from the inbox. If rejected orders must be reconciled, add a discard channel and handle them separately rather than treating them as technical errors.

`QueueChannel(20)` is only used to observe results and errors in this bounded example. A long-running application must have consumers reading these channels; otherwise, a full queue can block sending. How `QueueChannel` stores messages and its blocking behavior are described in [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

### 5.2. Progression of a Single Run

Suppose the inbox contains in order:

| Order | ID | Product | Quantity |
|---|---|---|---|
| 1 | `O-101` | `" keyboard "` | 2 |
| 2 | `O-102` | `"mouse"` | 0 |
| 3 | `O-103` | `" monitor "` | 1 |

With `maxMessagesPerPoll(2)`:

1. The first cycle pulls `O-101`, the filter passes it, and the transformer produces `KEYBOARD`.
2. Within the same cycle, the source is called again to pull `O-102`. The filter drops this message.
3. Two messages have been received, so that cycle ends.
4. The next cycle pulls `O-103` and produces `MONITOR`.
5. The subsequent call returns `null`, so the cycle ends early.
6. Later cycles keep running and receive `null` if no new orders arrive.

Messages dropped by the filter still count toward the poller's receive limit. This limit is not the final count of valid orders guaranteed to appear on the result channel.

## 6. Reading Poller Configuration Correctly

### 6.1. A Poll Cycle Differs from a Single receive() Call

A poll cycle can contain multiple `receive()` calls. With a positive limit, you can picture the control flow in pseudocode:

~~~text
when trigger fires:
    repeat at most maxMessagesPerPoll times:
        message = source.receive()
        if message == null:
            end current poll cycle
        send message to the first channel
~~~

This model explains the normal case, omitting advice, transactions, and exception handling.

In `SourcePollingChannelAdapter`, the default limit is one message per cycle unless overridden by configuration. A negative value allows continuing to receive until the source returns `null`; a value of `0` causes the adapter to skip calling the source. Do not confuse this adapter's default with a `PollingConsumer` reading from a channel. See [Channel Adapter: poller configuration](https://docs.spring.io/spring-integration/reference/6.5/channel-adapter.html).

| Value | When to consider | What to control |
|---|---|---|
| `1` | Slow source or wanting steady load | Backlog drainage rate may be low |
| A finite positive number | Wanting to pull multiple messages while capping batch size per cycle | Total cycle processing time grows with message count |
| Negative number | Wanting to drain a source guaranteed to run empty | A source that always emits messages can keep the cycle running very long |
| `0` | Pausing retrieval via limit configuration | Does not replace full lifecycle management |

A source like `() -> new GenericMessage<>("tick")` never returns `null`. Combined with a negative limit, the poller can continuously generate messages within the same cycle. Choosing a finite limit is an important decision for such sources.

### 6.2. fixedDelay, fixedRate, and cron

The following configurations are alternative options:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(2))
        .maxMessagesPerPoll(10)
~~~

~~~java
Pollers.fixedRate(Duration.ofSeconds(2))
        .maxMessagesPerPoll(10)
~~~

~~~java
Pollers.cron("0 */5 * * * *")
        .maxMessagesPerPoll(10)
~~~

| Scheduling style | How to interpret |
|---|---|
| `fixedDelay` | Sets a wait interval from when a polling task finishes until the next cycle in a direct execution setup, without offloading tasks to a separate executor |
| `fixedRate` | Computes cadence from scheduled start instants |
| `cron` | Runs according to a calendar expression; the example above is every five minutes at second 0 |

Prefer `Duration` so the unit is visible directly in code. Overloads of `Pollers.fixedDelay` and `Pollers.fixedRate` accepting a `long` use milliseconds. Scheduling calculation is described in [Pollers Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/Pollers.html).

`fixedRate` does not automatically spawn multiple parallel processing threads. When adding a `TaskExecutor` or changing the scheduler, re-evaluate task queuing or overlap, thread-safety of the source, and message ordering.

### 6.3. Estimating Throughput

For a source with abundant data, a sequential poller, no separate executor, and synchronous downstream:

~~~text
time per cycle ≈ total time to receive and process messages
effective period ≈ time per cycle + fixedDelay
throughput ≈ messages received / effective period
~~~

Self-calculation example: each cycle receives 10 messages; total read and processing time is 800 ms; fixed delay is 1 second. Approximate throughput:

~~~text
10 / (0.8 + 1) ≈ 5.56 messages/second
~~~

Therefore, do not deduce "10 messages per second" solely from `maxMessagesPerPoll(10)` and `fixedDelay(1 second)`. This is an estimate for formulating measurement hypotheses; empty reads, I/O, full queues, and errors all alter actual numbers.

### 6.4. Do Not Use receiveTimeout to Bound an Arbitrary Source

`MessageSource.receive()` takes no timeout parameter. If the implementation makes an HTTP call or database query and hangs, changing the poll interval does not create a deadline for that call.

Configure connect timeout, read timeout, query timeout, or appropriate cancellation mechanisms on the library accessing the source. `receiveTimeout` on a channel-reading polling consumer and `sendTimeout` when sending to a channel are different concepts.

## 7. Dedicated Poller vs. Default Poller

Configuring the poller directly in `from(source, endpoint -> ...)` makes the fetch schedule visible right in the flow that owns the source.

If you use the overload that takes only the source:

~~~java
IntegrationFlow.from(source)
~~~

then the context must have a matching default poller. Do not assume this flow automatically gets a one-second schedule when the context has not declared a default poller.

Example shared configuration, requiring imports for `PollerSpec`, `Pollers`, and `org.springframework.integration.scheduling.PollerMetadata`:

~~~java
@Bean(name = PollerMetadata.DEFAULT_POLLER)
PollerSpec defaultPoller() {
    return Pollers.fixedDelay(Duration.ofSeconds(1))
            .maxMessagesPerPoll(3);
}
~~~

This is a `FactoryBean` creating poller metadata. When declaring `PollerSpec` via `@Bean`, return the spec directly without calling `getObject()` in the bean method. See [Java DSL: Pollers](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-pollers.html).

A default poller fits when multiple endpoints share the same policy. For sources with rate limits or distinct load characteristics, configure a dedicated poller so changing the shared configuration does not accidentally alter load on that source.

## 8. One Message Is Not Necessarily One Record

The example source chooses to return one `Order` per `receive()` call. Another adapter might return a single message containing an entire `List<Order>`.

Suppose the source returns:

~~~text
Message<List<Order>> with a payload of 50 orders
~~~

Then:

- `maxMessagesPerPoll(1)` only limits one message from the source.
- That message still contains 50 records.
- Per-order processing steps need a splitter before filtering or transforming by `Order`.

Example downstream segment when **the payload is already a list**:

~~~java
IntegrationFlow.from(batchSource, endpoint -> endpoint
                .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                        .maxMessagesPerPoll(1)))
        .split()
        .<Order>filter(order -> order.quantity() > 0)
        .channel("individualOrders")
        .get();
~~~

Here `batchSource` is an already-defined `MessageSource<List<Order>>`; this snippet illustrates the alternative structure for a source that emits lists instead of individual orders.

`maxMessagesPerPoll` is not a limit on SQL row count, HTTP page size, or payload element count. Those limits belong to the source implementation and its underlying adapter library.

## 9. Choosing How to Start a Flow

| Starting style | Who decides when a message arrives? | Polls source via SourcePollingChannelAdapter? | Typical use case |
|---|---|---|---|
| `from(MessageSource<?>)` | Application's polling schedule | Yes | Actively fetching data and building the full message |
| `fromSupplier(...)` | Application's polling schedule | Yes | Producing payloads via a `Supplier` |
| `from("inputChannel")` with `DirectChannel` | Sender calling `send(...)` | No | Receiving messages from another flow or application |
| `from(queueChannel)` with `QueueChannel` | Sender puts message in queue, consumer pulls it | Does not poll source; downstream uses `PollingConsumer` | Buffering messages already in the system |
| Callback or event-receiving adapter | External system or client library | Depends on adapter; message-driven ones do not poll this way | Receiving messages pushed by the source side |

Distinguishing `PollingConsumer` from `SourcePollingChannelAdapter` helps identify exactly where a poller is needed. Both mechanisms poll, but the target being read is either a channel or an external source. See [Poller and Pollable Message Source](https://docs.spring.io/spring-integration/reference/6.5/polling-consumer.html).

### 9.1. When to Use fromSupplier?

If you do not need to construct headers manually at the source, a `Supplier` can keep code shorter:

~~~java
Supplier<Order> nextOrder = inbox::poll;

IntegrationFlow.fromSupplier(nextOrder, endpoint -> endpoint
                .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                        .maxMessagesPerPoll(2)))
        .channel("rawOrders")
        .get();
~~~

This snippet requires `java.util.function.Supplier` and an `inbox` similar to the previous example. The returned payload value is wrapped in a message by the framework; if no data is ready, the supplier can return `null`. When you need to build a message with headers directly at the source, `MessageSource` expresses that intent more clearly. How supplier results are wrapped is described in [Inbound Channel Adapters](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-inbound-adapters.html).

If a lambda causes confusion with overloads or types, declare an explicitly typed `MessageSource<Order>` or `Supplier<Order>` variable and pass that variable to the corresponding API.

## 10. Threads, Channels, and Lifecycle

### 10.1. Polling Does Not Make Downstream Steps Asynchronous

In the example flow, the polling adapter initiates processing on the polling task's thread. The filter and transformer steps are connected through synchronous channels, so they complete on that thread before sending the result to the queue.

When another consumer reads `acceptedOrders`, post-queue processing can run on a different thread. The moment the adapter successfully sends to the queue only indicates that the message was placed in the queue, not that the downstream consumer has finished business processing.

This characteristic determines where latency is measured and where errors are caught. For instance, product normalization time counts toward the poller's work in the current flow; later processing time by a consumer reading results belongs to a separate execution stage.

### 10.2. Starting and Stopping the Adapter

With `autoStartup(false)`, you can actively start the endpoint after the context is created:

~~~java
SourcePollingChannelAdapter adapter =
        context.getBean("orderInbound", SourcePollingChannelAdapter.class);

adapter.start();

// When you want to stop subsequent polling cycles:
adapter.stop();
~~~

The type to import is `org.springframework.integration.endpoint.SourcePollingChannelAdapter`.

Do not assume `stop()` forcibly aborts an in-flight I/O call immediately. Graceful shutdown still depends on completion, timeouts, or cancellation support of the data-fetching operation.

Stopping the adapter from pulling more items also does not mean every message already in downstream channels has finished processing. Pending data and active work must be tracked separately.

## 11. Error Handling at the Polling Boundary

The example configured:

~~~java
.poller(Pollers.fixedDelay(Duration.ofMillis(100))
        .maxMessagesPerPoll(2)
        .errorChannel("orderPollingErrors"))
~~~

This configuration sets the destination channel for the poller's error publication mechanism. In the example flow without a custom `errorChannel` header, errors from the polling task are routed to `orderPollingErrors` as an `ErrorMessage`.

| Origin | Example | What to infer |
|---|---|---|
| Inside the source | Query fails before creating a message | There may not yet be an original message carrying order details |
| Inside synchronous filter or transformer | `product` is `null`, failing normalization | Error returns to the polling task |
| After another consumer has pulled from the queue | Calling shipping service fails | Must be handled within that consumer's scope |
| Filter returns `false` | Order with quantity 0 | This is the configured discard path, not automatically an error |

An `ErrorMessage` has a `Throwable` payload. If it is a `MessagingException` with a `failedMessage`, you can extract additional data for reconciliation; do not assume every error carries a domain message. Scheduled task error handling and thread boundaries are presented in [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

In the example, the test reads the error queue directly. In an application, attach an error flow or consumer to record the cause, business key if present, and decide next steps.

### 11.1. The Next Poll Does Not Mean Retrying the Failed Message

`inbox.poll()` removes the order from the queue before the filter and transformer run. If the transformer fails:

1. The order has already left the inbox.
2. The poller can emit an error message.
3. The next cycle pulls another order or receives `null`.
4. The failed order does not automatically reappear.

Thus, `errorChannel` provides a route for errors; it does not create rollback, durability, or retry behavior on its own.

Also distinguish retrying **calling the source again** from retrying **processing the exact message already received**. If the source is destructive on read, calling the source again may pull a different item. Place retries around the operation that should actually repeat, rather than merely adding retry wherever it is easiest to configure.

## 12. Designing a Resilient Source

For data that must survive errors or restarts, design answers to both questions:

- When does the source consider data successfully fetched or processed?
- If an error occurs between receiving and completing business processing, how do we locate that exact data again?

Common design patterns:

| Source characteristic | Handling direction |
|---|---|
| Database with processing status | Atomically claim records; manage status, retries, and lease expiration |
| API with cursor or checkpoint | Persist progress at an appropriate success milestone; prepare for duplicates on re-read |
| Source with acknowledgment | Use acknowledgment or rollback mechanisms supported by the adapter |
| Files or object storage | Track processed markers and when to move, mark, or delete |
| Multiple instances reading concurrently | Partitioning, locking, or claiming mechanisms to limit contention |

These are design choices to tailor to the source system, not built-in features of every `MessageSource`.

A poller's transaction can enclose receiving from a transaction-aware resource. However, adding a transaction does not make `ConcurrentLinkedQueue` in the example rollback-capable. When the flow hands off to another thread, a transaction bound to the current thread does not automatically follow there either. See [Transaction Support](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

Combining durability, acknowledgment, and idempotent processing often matters more than merely shortening the poll interval. A key such as `businessKey` should be checked against persisted processing state if the business requires deduplication across restarts.

## 13. Testing the Source and Flow

Separate two levels of testing:

| Level | What to prove |
|---|---|
| Standalone source | Returns `null` when empty; builds proper payload and headers when data is present |
| Flow with context | Adapter runs, downstream processes properly, errors go to the chosen channel |

The tests below sit in the same package as `OrderPollingConfig`. They use queues with timeouts to wait for results and close the context after each test. This is illustrative test code, not execution results from a specific project.

~~~java
package demo.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.endpoint.SourcePollingChannelAdapter;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

import demo.integration.OrderPollingConfig.Order;
import demo.integration.OrderPollingConfig.OrderInbox;

import static org.junit.jupiter.api.Assertions.*;

class OrderPollingFlowTest {

    @Test
    void sourceReturnsNullWhenEmptyAndBuildsHeaders() {
        OrderInbox inbox = new OrderInbox();
        MessageSource<Order> source =
                new OrderPollingConfig().orderMessageSource(inbox);

        assertNull(source.receive());

        Order order = new Order("O-101", " keyboard ", 2);
        inbox.add(order);

        Message<Order> message = source.receive();

        assertNotNull(message);
        assertEquals(order, message.getPayload());
        assertEquals("demo-orders", message.getHeaders().get("sourceSystem"));
        assertEquals("O-101", message.getHeaders().get("businessKey"));
        assertNull(source.receive());
    }

    @Test
    void flowFiltersAndTransformsAcrossPollingCycles() {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderPollingConfig.class)) {

            OrderInbox inbox = context.getBean(OrderInbox.class);
            QueueChannel accepted =
                    context.getBean("acceptedOrders", QueueChannel.class);

            inbox.add(new Order("O-101", " keyboard ", 2));
            inbox.add(new Order("O-102", "mouse", 0));
            inbox.add(new Order("O-103", " monitor ", 1));

            SourcePollingChannelAdapter adapter =
                    context.getBean("orderInbound", SourcePollingChannelAdapter.class);

            assertFalse(adapter.isRunning());
            adapter.start();

            Message<?> first = accepted.receive(3000);
            Message<?> second = accepted.receive(3000);

            assertNotNull(first);
            assertNotNull(second);
            assertEquals(new Order("O-101", "KEYBOARD", 2), first.getPayload());
            assertEquals(new Order("O-103", "MONITOR", 1), second.getPayload());
            assertEquals("O-101", first.getHeaders().get("businessKey"));
        }
    }

    @Test
    void transformationFailureIsPublishedToPollingErrorChannel() {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderPollingConfig.class)) {

            OrderInbox inbox = context.getBean(OrderInbox.class);
            QueueChannel errors =
                    context.getBean("orderPollingErrors", QueueChannel.class);

            // quantity is valid so the message reaches the transformer.
            inbox.add(new Order("O-999", null, 1));

            context.getBean("orderInbound", SourcePollingChannelAdapter.class)
                    .start();

            Message<?> failure = errors.receive(3000);

            assertNotNull(failure);
            assertInstanceOf(ErrorMessage.class, failure);
            assertInstanceOf(Throwable.class, failure.getPayload());

            // The example's source already removed the order and does not put it back on error.
            assertNull(inbox.poll());
        }
    }
}
~~~

The second test observes two business results in order. It verifies that the flow continues pulling data across multiple cycles, not exact wall-clock timing between cycles.

The third test uses invalid data to trigger a synchronous downstream error, while highlighting the recovery limits of an in-memory source. With a real source, add cases for failures inside `receive()`, re-read messages, and application restarts.

If you need exact control over the number of polls, you can use a test trigger like `OnlyOnceTrigger` instead of a periodic schedule, with an appropriate message limit. Spring Integration also provides source and endpoint mocking tools in [Testing support](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

## 14. Diagnosing Common Errors

| Symptom | First thing to check | Resolution |
|---|---|---|
| Context fails to start due to missing poller | Using `from(source)` without a default poller | Declare a poller on the endpoint or provide a default poller |
| Context runs but no data appears | `autoStartup(false)`, empty source, or filter drops all items | Check lifecycle, receive results, and discard branch |
| High CPU, source called continuously | Negative limit with a source that never returns `null` | Set a positive limit and review source behavior |
| Only one message despite query returning multiple rows | Payload is a list | Check payload type and add a splitter if needed |
| Items lost after downstream error | Source deletes or marks data too early | Design claiming, acknowledgment, checkpoint, or rollback |
| Only seeing logs on default error channel | Wrong channel selected or error occurs past an async boundary | Identify which thread and consumer actually owns the error |
| Polling stalls under load | I/O lacks timeout or target channel is full | Measure receive time, send time, and consumer rate |
| Messages processed multiple times across instances | Instances read the same source data | Use locking, partitioning, or a suitable claiming mechanism |

To distinguish an empty source from a stalled system, monitor poll count, `null` receive count, successful message count, error count, processing latency, and queue depth. These metrics should be tied to specific sources or endpoints so slowdowns can be traced.

## 15. Application Principles

`from(MessageSource)` fits when the application owns the data-fetching cadence and needs received data represented as messages with explicit payloads and headers.

When building real flows, keep the source contract simple, configure pollers intentionally, distinguish a message from records inside its payload, and define precisely when data is considered processed. Decisions about retries, transactions, acknowledgments, and deduplication must align with the source's properties and the flow's execution boundaries.

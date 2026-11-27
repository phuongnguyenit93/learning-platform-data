# MethodInvokingMessageSource: turning a POJO method into a message source

## 1. Problem to solve

Suppose an application already has a plain Java class (POJO) providing new orders through a `nextOrder()` method. This class knows nothing about `Message`, `MessageChannel`, or Spring Integration. We want to **periodically invoke that method**, take its result, and feed it into a message processing flow—such as validating the order, writing to a database, or sending it to Kafka.

In the **SPRING_INTEGRATION_ADAPTERS** module, adapters connect external systems with `MessageChannel` flows: files, SFTP, HTTP, JMS, AMQP, Kafka, databases, or an existing Java API. When the data source is **a no-argument Java method**, Spring Integration provides `MethodInvokingMessageSource` to call that method and turn its return value into a message. You can instantiate this class directly or use the `@InboundChannelAdapter` annotation so the framework creates it for you.

After this lesson, you will be able to:

- Distinguish `MethodInvokingMessageSource`, `SourcePollingChannelAdapter`, `Poller`, and `MessageChannel`.
- Create an inbound adapter from a POJO method using annotations or Java DSL.
- Understand the meaning of a `null` return value, `Message<?>`, method invocation errors, and poll counts.
- Choose the appropriate configuration and testing strategy when pulling data from an existing Java API.

## 2. Position in the Spring Integration architecture

`MethodInvokingMessageSource` resides in the `org.springframework.integration.endpoint` package, extends `AbstractMessageSource<Object>`, and implements the `MessageSource<Object>` contract.

A `MessageSource` answers the question **"is there any data for the next receive?"** via `receive()`. `MethodInvokingMessageSource` itself **does not schedule anything**. The `SourcePollingChannelAdapter` component pairs it with a poller, calls `receive()`, and sends the resulting message to a channel.

```mermaid
flowchart LR
    T[Poller / polling schedule] --> E[SourcePollingChannelAdapter]
    E -->|receive()| S[MethodInvokingMessageSource]
    S -->|calls nextOrder()| P[Data source POJO]
    P -->|Order or null| S
    S -->|Message or null| E
    E -->|Message when data exists| C[MessageChannel]
    C --> H[Service Activator / Flow / Other Adapter]
```

| Component | Responsibility | What it does not do itself |
|---|---|---|
| **POJO** | Implements the business logic to fetch one unit of data when called. | Does not need to know about channels, pollers, or Spring Integration structures. |
| **`MethodInvokingMessageSource`** | Calls the **no-argument** POJO method and converts the result into a `Message` when `receive()` is invoked. | Does not schedule itself, does not send to channels directly. |
| **`SourcePollingChannelAdapter`** | Receives signals from the poller, invokes `MessageSource.receive()`, and sends messages to the channel. | Does not decide how business data is fetched. |
| **Poller** | Defines the period, max receives per cycle, and polling policies. | Does not supply data or implement business logic. |
| **`MessageChannel`** | Delivers the message to a handler or the next step in the flow. | Does not call `nextOrder()` on the POJO itself. |

A normal cycle proceeds as follows:

1. The poller triggers the inbound endpoint.
2. The endpoint calls `messageSource.receive()`; the source invokes the configured POJO method.
3. If the method returns an object, Spring Integration creates a message with that object as the payload (or uses the message returned directly by the method).
4. The endpoint sends the message to the channel; the downstream handler receives and processes it.
5. If the method returns `null`, no message is created or sent for that receive; the poller proceeds according to its configured policy.

**Distinguishing data direction:** `MethodInvokingMessageSource` is **inbound**: the framework proactively calls the POJO to *pull* data into the flow. Conversely, `@ServiceActivator` or an outbound adapter receives messages *from* the flow to invoke business logic or push to another system.

## 3. Contract of the invoked method

A POJO method used as a message source has several important characteristics:

| Contract | Explanation |
|---|---|
| **No parameters** | The poller provides no input payload; a method like `nextOrder()` is valid, whereas `nextOrder(String id)` is not suitable. |
| **Has a return value** | Can return a POJO, `String`, `record`, `Message<?>`, etc.; do not use a `void` method. |
| **`null` means no data** | A `null` result signals this read produced no message. `null` is not a valid payload to send. |
| **One call, one result** | Returning `List<Order>` produces one message whose payload is the list; it does not auto-split into multiple messages. To split, add a downstream `Splitter` or return individual `Order`s. |
| **Must be safe under scheduled polling** | The method may be called repeatedly over time; reading/removing records, concurrency, and reprocessing must be designed deliberately. |
| **May return `Message<?>`** | Useful when you need to explicitly set headers such as source system code or correlation key. |

Simple source example:

```java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

public final class PendingOrderStore {
    private final Queue<String> ids = new ConcurrentLinkedQueue<>();

    public void add(String orderId) {
        ids.add(orderId);
    }

    public String nextOrderId() {
        return ids.poll(); // Returns a value when data exists; null when the queue is empty.
    }
}
```

Here `nextOrderId()` can be invoked on a schedule without parameters. `ConcurrentLinkedQueue` keeps queue operations thread-safe when another thread adds data, though this example only simulates an in-memory source; it **does not guarantee durable persistence** or transactions with downstream systems.

## 4. Approach 1 — Using `@InboundChannelAdapter` on a POJO

This is the concise approach when we control the Java class and can place the annotation directly on the method. Spring Integration detects the annotation on a Spring bean and automatically creates the `MethodInvokingMessageSource` along with the required polling endpoint.

Example using **Java 17+, Spring Boot 3.x, and Spring Integration 6.x**. In a Spring Boot project, add the starter:

```groovy
// build.gradle (dependencies snippet)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
}
```

Create the demo application in package `com.example.orders` (classes can be placed in separate Java files):

```java
package com.example.orders;

import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;

@SpringBootApplication
@EnableIntegration
public class OrderDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderDemoApplication.class, args);
    }

    @Bean
    Queue<PendingOrder> pendingOrders() {
        Queue<PendingOrder> orders = new ConcurrentLinkedQueue<>();
        orders.add(new PendingOrder("ORD-101", 150_000));
        orders.add(new PendingOrder("ORD-102", 290_000));
        orders.add(new PendingOrder("ORD-103", 175_000));
        return orders;
    }

    @Bean
    MessageChannel pendingOrderChannel() {
        return new DirectChannel();
    }
}

record PendingOrder(String id, long amountVnd) { }
```

Register the POJO method as the **source**:

```java
package com.example.orders;

import java.util.Queue;

import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.stereotype.Component;

@Component
public class PendingOrderSource {
    private final Queue<PendingOrder> orders;

    public PendingOrderSource(Queue<PendingOrder> orders) {
        this.orders = orders;
    }

    @InboundChannelAdapter(
        channel = "pendingOrderChannel",
        poller = @Poller(fixedDelay = "2000", maxMessagesPerPoll = "2")
    )
    public PendingOrder nextOrder() {
        return orders.poll();
    }
}
```

Define the consumer:

```java
package com.example.orders;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class PendingOrderConsumer {
    @ServiceActivator(inputChannel = "pendingOrderChannel")
    public void process(PendingOrder order) {
        System.out.printf("Processed %s: %d VND%n", order.id(), order.amountVnd());
    }
}
```

When running the application, `@InboundChannelAdapter` creates a polling endpoint that emits messages to `pendingOrderChannel`. With `maxMessagesPerPoll = "2"`, each poll can receive **at most two** elements; after a couple of cycles, the three demo orders are printed. Once the queue is empty, `nextOrder()` returns `null`, so no further messages are emitted. `fixedDelay = "2000"` sets a delay of roughly 2 seconds between polling executions (in milliseconds); the actual number of calls and print timestamps also depend on processing time and the scheduler.

Note three points in this configuration:

1. `PendingOrderSource` is a Spring bean (`@Component`) so the framework processes its annotations.
2. `@InboundChannelAdapter` is placed on a **no-argument, non-`void` method**. Do not attach `@Poller` alone to a regular method expecting Spring to create an adapter automatically.
3. `@ServiceActivator` is the **consuming** side. `DirectChannel` dispatches synchronously, so slow consumer processing can stretch the poll cycle.

> **Do not also register an `IntegrationFlow.from(...)` for the exact same source in this example.** The annotation already creates an inbound endpoint; creating a second endpoint on the same source can cause the method to be read by two different pollers.

## 5. Approach 2 — Declaring `MethodInvokingMessageSource` directly with Java DSL

If the POJO comes from a library whose source code cannot be edited, or if you prefer configuring the method in a `@Configuration` class, you can instantiate `MethodInvokingMessageSource` yourself and pass it to `IntegrationFlow.from(...)`.

The example below is an **independent alternative** to the annotation example in section 4:

```java
package com.example.legacy;

import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.endpoint.MethodInvokingMessageSource;

@Configuration
@EnableIntegration
public class LegacyInboxIntegrationConfig {

    @Bean
    LegacyInbox legacyInbox() {
        return new LegacyInbox();
    }

    @Bean
    MethodInvokingMessageSource legacyInboxSource(LegacyInbox legacyInbox) {
        MethodInvokingMessageSource source = new MethodInvokingMessageSource();
        source.setObject(legacyInbox);       // Bean containing the method to invoke.
        source.setMethodName("takeNext");    // Name of the no-argument method.
        return source;
    }

    @Bean
    IntegrationFlow legacyInboxFlow(MethodInvokingMessageSource legacyInboxSource) {
        return IntegrationFlow.from(
                    legacyInboxSource,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(2000).maxMessagesPerPoll(3)))
                .handle(message -> System.out.println("Received: " + message.getPayload()))
                .get();
    }
}

final class LegacyInbox {
    private final Queue<String> messages =
            new ConcurrentLinkedQueue<>(java.util.List.of("A", "B", "C"));

    public String takeNext() {
        return messages.poll();
    }
}
```

Explanation:

- `setObject(legacyInbox)` holds the reference to the target bean; `setMethodName("takeNext")` specifies the method to execute. The API also offers `setMethod(Method)` if you need to provide a reflected Java `Method` object directly.
- `IntegrationFlow.from(legacyInboxSource, ...)` starts the flow from the `MessageSource`; the lambda configures the polling endpoint.
- `Pollers.fixedDelay(2000).maxMessagesPerPoll(3)` configures the poll delay and up to three receives per trigger.
- `.handle(...)` processes the message directly in the DSL. In a real application, you can replace it with `.channel(...)`, `.transform(...)`, `.route(...)`, or a dedicated handler.

If you only declare `@Bean MethodInvokingMessageSource` **without** a `SourcePollingChannelAdapter`, `IntegrationFlow.from(...)`, or equivalent endpoint, `takeNext()` will not run on a schedule. Likewise, calling `setObject`/`setMethodName` configures the source, not the scheduler.

### Which approach should you choose?

| Criterion | `@InboundChannelAdapter` | Explicit `MethodInvokingMessageSource` + DSL |
|---|---|---|
| POJO code ownership | Convenient when you can edit the method | Works even when the POJO is a third-party library bean |
| Conciseness | Fewer configuration classes, easy to read | Explicit source and endpoint creation |
| Pipeline configuration | Combine with annotations for downstream steps | Write the entire flow in Java DSL |
| Source control | Framework builds the source from the annotated method | Can configure `setObject`, `setMethodName`, or `setMethod` |

Both approaches feed data into Spring Integration using the **same model**: poller → message source → channel/flow.

## 6. Return values and message headers

By default, if `nextOrder()` returns `new PendingOrder(...)`, Spring Integration creates a `Message` whose payload is `PendingOrder`. When downstream needs extra metadata, return a `Message<PendingOrder>` instead of just the POJO.

For example, **replace `nextOrder()` in section 4** with the following version (do not declare two inbound methods concurrently on the same data):

```java
import org.springframework.messaging.Message;
import org.springframework.integration.support.MessageBuilder;

@InboundChannelAdapter(
    channel = "pendingOrderChannel",
    poller = @Poller(fixedDelay = "2000")
)
public Message<PendingOrder> nextOrderMessage() {
    PendingOrder order = orders.poll();
    if (order == null) {
        return null;
    }

    return MessageBuilder.withPayload(order)
            .setHeader("sourceSystem", "legacy-order-queue")
            .setHeader("businessKey", order.id())
            .build();
}
```

The consumer can read them:

```java
@ServiceActivator(inputChannel = "pendingOrderChannel")
public void process(
        PendingOrder order,
        @org.springframework.messaging.handler.annotation.Header("businessKey") String key) {
    System.out.println("Process " + key + " / " + order.amountVnd());
}
```

Here `businessKey` is a business key used for reconciliation or preventing duplicate processing. Spring Message's `id` and `timestamp` headers serve message identification and observability; they **do not** automatically replace an order's durable identifier. Avoid placing secrets in headers since headers may be logged or forwarded across adapters.

If the method returns a `List<Order>`, downstream receives **one** message containing `List<Order>`. You can add `.split()` or `@Splitter` to split it into individual messages; `MethodInvokingMessageSource` does not automatically infer an intent to split lists.

## 7. Understanding poller behavior properly

The poller controls when and at what pace the source is read. Two commonly used parameters:

| Configuration | Practical meaning | When to consider |
|---|---|---|
| `fixedDelay = "2000"` | Waits ~2 seconds after one polling execution finishes before running the next. | Prevents overlapping cycles; suits variable processing times. |
| `fixedRate = "2000"` | Triggers on a ~2-second cadence, subject to scheduler and resources. | When a relatively steady cadence is needed; still account for slow processing. |
| `maxMessagesPerPoll = "1"` | At most one message receive per poll. | Low data volume, or need to throttle items processed. |
| `maxMessagesPerPoll = "10"` | Can attempt up to ten consecutive receives per poll; stops early if source returns `null`. | When draining multiple available items in one cycle. |

**Do not confuse `maxMessagesPerPoll` with payload batch size.** A value of `10` does not ask the method to return a ten-element list; it lets the endpoint call `receive()` multiple times in one cycle, receiving one message per call. If the first receive returns `null`, the poller does not emit ten empty messages.

Operational factors to consider:

- **Source load:** each method invocation may open a connection or query a database; polling too aggressively increases load and empty queries.
- **Latency:** infrequent polling reduces load, but new data takes longer to enter the flow.
- **Downstream processing time:** with `DirectChannel`, the handler runs synchronously on the sender thread; a slow handler affects the polling cadence.
- **Concurrency:** if the source cannot tolerate concurrent calls, constrain the scheduler/endpoint and avoid configuring multiple endpoints scanning the same source.
- **Stop/start:** endpoint lifecycle (`start()`/`stop()`) governs whether the flow is polled; stopping a poller does not delete data sitting in the source.

For sources that lack push notifications (a Java method reading a legacy store, staging table, or internal queue), polling is a great fit. For event-pushing sources (callbacks, listeners, Kafka consumers, etc.), usually prefer an adapter supporting that native event mechanism rather than writing a manual polling loop.

## 8. Errors, transactions, and reliability

`MethodInvokingMessageSource` only knows how to call a method. It **does not automatically guarantee** exactly-once delivery, infinite retries, transactions, or deduplication. Those guarantees depend on the data source, how data is fetched, and downstream components.

### Dangerous case: pull-and-lose

In the `Queue.poll()` example, an item is removed from the queue **before** the handler successfully receives/processes it:

```text
nextOrder() takes ORD-101 from queue
    -> message is created
    -> handler throws an exception
    -> in-memory queue no longer has ORD-101
```

If these are real orders, replace the fetch mechanism with a durable stateful source and confirmation workflow, such as `NEW → PROCESSING → DONE`, timed leases, transactions where appropriate, or a message broker with acknowledgments. For database-backed sources, design keys/idempotency and recovery for in-flight records.

### When the method throws an exception

For example, the method hits a database connection error and throws `RuntimeException`: the error surfaces when the polling endpoint invokes the source; the poller/scheduler error handling determines whether it is logged, routed to an error channel, or handled by advice. Never assume exceptions will automatically retry to completion. Configure an explicit error policy at the endpoint or integration layer and monitor failures.

Implementation principles:

1. **Ensure idempotency** in the handler using a business key, especially when retries exist or source data can be re-read.
2. **Distinguish "no data" from "cannot read data"**: return `null` when out of data; throw an exception when the source system fails so errors remain observable.
3. **Bound source call duration** with proper timeouts if the method performs I/O; the poller cannot recover a call hung forever.
4. **Alert and observe** metrics like poll errors, source latency, successful/failed message counts, and backlog.
5. **Actively manage backpressure**: tune `maxMessagesPerPoll`, poll rate, channel capacity, and downstream capacity.

## 9. Testing the source and flow

Test at two layers: the **`MessageSource` contract** (invoking the method, returning a message or `null`) and the **integration flow** (poller runs, channel delivers messages, handler receives the expected payload/headers).

Minimal source test example without waiting for the scheduler:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.junit.jupiter.api.Test;
import org.springframework.integration.endpoint.MethodInvokingMessageSource;
import org.springframework.messaging.Message;

class MethodSourceTest {
    static class Inbox {
        private final Queue<String> items = new ConcurrentLinkedQueue<>();

        public String next() {
            return items.poll();
        }
    }

    @Test
    void receiveReturnsMessageThenNull() {
        Inbox inbox = new Inbox();
        inbox.items.add("ORDER-1");

        MethodInvokingMessageSource source = new MethodInvokingMessageSource();
        source.setObject(inbox);
        source.setMethodName("next");
        source.afterPropertiesSet(); // Initialize the source like a Spring bean lifecycle.

        Message<?> first = source.receive();
        assertNotNull(first);
        assertEquals("ORDER-1", first.getPayload());
        assertNull(source.receive());
    }
}
```

The test above verifies that the source calls the right method and wraps the result into a message, yet **it does not prove** the polling schedule or downstream runs correctly. For integration tests, boot a Spring context with `@EnableIntegration`, configure a short poller, and use a test channel/handler to await the expected number of messages. Use bounded waits (such as `CountDownLatch`) instead of fixed `Thread.sleep()` calls to avoid flaky tests.

### Common errors

| Symptom | Causes worth checking | How to fix |
|---|---|---|
| Method is never called | POJO is not a bean, missing endpoint, or poller not configured. | Verify Spring scans the bean, `@InboundChannelAdapter` or `IntegrationFlow.from(...)` exists, and the endpoint is running. |
| Startup error related to method | Wrong method name, takes parameters, unsuitable signature, or overlapping config. | Use a `public`, no-argument, non-void method; check `setMethodName`. |
| No messages reach handler | Source always returns `null`, wrong channel name, or handler not subscribed. | Check input data, channel names, and subscriptions; log received values at an appropriate level. |
| A `List` object is received instead of items | Method returns a list as a single payload. | Return individual items or add a Splitter in the flow. |
| Messages processed slowly | Infrequent poller, synchronous `DirectChannel` with heavy handler, or slow source. | Measure each step's timing, tune schedule, and consider controlled async decoupling. |
| Duplicate or missing data on retry | Source lacks ack/transaction, multiple pollers, or non-idempotent handler. | Redesign ack, retry, checkpoints, and business keys for the source type. |

## 10. Self-practice exercises

1. Modify `PendingOrderSource` to fetch at most **one** order per `fixedDelay = "1000"` cycle; observe when the three orders appear.
2. Replace `PendingOrder` with `Message<PendingOrder>`, add `sourceSystem` and `businessKey`, and read those headers in `@ServiceActivator`.
3. Change `nextOrder()` to always return `null`. Verify the application keeps running on schedule while the handler receives no messages.
4. Convert the demo from annotations to explicit `MethodInvokingMessageSource` configuration with Java DSL. Ensure only one endpoint polls the source.
5. Simulate a downstream error after pulling an order. Explain why plain `Queue.poll()` can lose data and propose a fix using a durable source plus processing confirmation.

## 11. Takeaways

- **`MethodInvokingMessageSource` = invoke a no-argument POJO method to obtain one result per `receive()` call**.
- **`SourcePollingChannelAdapter` + poller = decides when to call the source and send messages to the channel**.
- **`@InboundChannelAdapter`** is the concise declaration; the framework creates these components around the annotated method.
- **`IntegrationFlow.from(source, ...)`** is the explicit approach when you want to configure `MethodInvokingMessageSource` yourself or integrate a legacy Java class.
- `null` means **no message**, `Message<?>` lets you set headers; lists are not automatically split into elements.
- Polling and message forwarding do not automatically provide exactly-once delivery, retries, or transactions. Reliability must be designed across both source and consumer.

### References

- [Spring Integration — Annotation Support: `@InboundChannelAdapter` and `@Poller`](https://docs.spring.io/spring-integration/reference/configuration/annotations.html)
- [Spring Integration — Java DSL Inbound Channel Adapters](https://docs.spring.io/spring-integration/reference/6.3/dsl/java-inbound-adapters.html)
- [API: `MethodInvokingMessageSource`](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/endpoint/MethodInvokingMessageSource.html)
- [Spring Integration — Overview of Polling Inbound Endpoints](https://docs.spring.io/spring-integration/reference/overview.html)

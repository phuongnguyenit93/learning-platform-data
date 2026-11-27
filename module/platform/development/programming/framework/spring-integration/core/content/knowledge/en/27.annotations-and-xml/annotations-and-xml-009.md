# @InboundChannelAdapter

## 1. Objectives and Scope

In the **Annotations and XML** chapter of the **SPRING_INTEGRATION_CORE** module, `@InboundChannelAdapter` is a way to create an entry point for a message flow using Java annotations. It fits when the application needs to actively poll a data source on a schedule and push retrieved data into a `MessageChannel`.

After this lesson, you can:

- Distinguish a polled data source from an endpoint receiving messages from a channel.
- Declare a zero-argument source method and understand how return values are handled.
- Choose between a POJO method, a `Supplier` bean, and a `MessageSource` bean.
- Configure pollers, lifecycle, and error-handling paths.
- Write tests for the data source and endpoint, while reading equivalent XML/Java DSL configurations.

The examples use Java 17, Spring Integration 6.x APIs, and JUnit Jupiter. Dependency versions should follow your project's compatible BOM or Spring Boot platform. This lesson covers adapters invoking Java methods or sources; specialized adapters such as JDBC, file, or SFTP add their own contracts.

## 2. Inbound Understood from the Integration System's Side

Suppose an ERP exposes an API to fetch new orders. The application must periodically call the API and send each order into the processing flow:

```text
ERP or data source
        ^
        | poll on schedule
        |
source method / MessageSource
        |
        v
SourcePollingChannelAdapter
        |
        v
ordersChannel
        |
        v
filter -> transformer -> router -> business processing
```

"Inbound" means data enters **into the application's messaging system**. The source can be an external service, a Java library, or an application-managed object.

Unlike a service activator, a source method does not wait for an incoming `Message` to trigger it. A poller actively invokes the source. Any non-`null` result is sent to the output channel.

When used on a POJO method, Spring Integration creates a `MethodInvokingMessageSource` to invoke the method and wraps that source in a `SourcePollingChannelAdapter`. See [Using the @InboundChannelAdapter Annotation](https://docs.spring.io/spring-integration/reference/configuration/annotations.html#using-the-inboundchanneladapter-annotation).

### Quick Role Comparison

| Component | What Triggers It? | Primary Responsibility |
| --- | --- | --- |
| `@InboundChannelAdapter` | Poller invokes source on a schedule | Feeds source data into a channel |
| `@ServiceActivator` | Message available on input channel | Invokes business logic on the message |
| `@BridgeFrom` | Message on source channel | Forwards to another channel |
| Messaging gateway | Call through gateway contract | Provides flow entry/exit interface, optionally request-reply |

A bridge does not turn an ERP source into new data; it only forwards existing messages. An inbound channel adapter is where you start creating messages from source reads.

## 3. Syntax and Contract of a Source Method

A minimal source method:

```java
@InboundChannelAdapter(
    channel = "ordersChannel",
    poller = @Poller(fixedDelay = "1000")
)
public String nextOrderId() {
    return fetchNextOrderId();
}
```

This snippet assumes the containing object is a Spring-managed bean and `fetchNextOrderId()` is an application-provided source read operation.

Three points to read accurately:

1. `channel` is the name of the **output channel**, where the adapter sends messages.
2. A POJO source method takes no parameters and does not return `void`.
3. `poller` drives calling the source, even when the output channel is a `DirectChannel`.

`value` and `channel` are two aliases for the same attribute. You can write `@InboundChannelAdapter("ordersChannel")` when using a default poller, but do not declare both aliases with different values.

| Attribute | Meaning |
| --- | --- |
| `channel` / `value` | Name of the channel bean receiving source messages |
| `poller` | Schedule for invoking the source and polling options |
| `autoStartup` | Whether the endpoint starts automatically on context startup; defaults to `"true"` |
| `phase` | Lifecycle ordering when starting/stopping endpoints |

The annotation definition is in [Javadoc for InboundChannelAdapter](https://docs.spring.io/spring-integration/docs/6.0.x/api/org/springframework/integration/annotation/InboundChannelAdapter.html).

### Why Does a Source Method Have No Parameters?

At the moment the source is invoked, there is no input message from which to map payload or headers into parameters. Thus, this is not the place for `@Payload` or `@Header` to receive request data.

Dependencies such as ERP clients, repositories, or query settings must be injected into the source object via constructor or appropriate dependency injection.

The no-parameter rule applies to **polled POJO methods**. A `@Bean` method creating a `Supplier` or `MessageSource` can accept container-provided dependencies; the bean factory and the source read operation are two separate steps.

## 4. Return Values Determine Emitted Messages

| Source Read Result | Behavior |
| --- | --- |
| A non-`null` POJO, such as `String` or `Order` | Builds a `Message` with that object as payload |
| A `Message<?>` | Uses the message already built by the source |
| `null` | Sends no message for this read; ends further reads in the current poll |
| A non-`null` `List<Order>` | Emits one message whose payload is the list |
| Throws an exception | Polling cycle fails and follows error-handling configuration |

`null` means "currently no data available." It does not permanently stop the adapter. At the next scheduled tick, the poller can still invoke the source.

Do not return `Optional.empty()` instead of `null` expecting the framework to skip it automatically. Under the standard source contract, `Optional.empty()` is still a non-`null` object. Similarly, an empty list is not a signal that no data exists.

### When Should You Return a Message?

If only an order ID is needed, returning `String` suffices. If you want to attach metadata right at data ingestion, build a `Message`:

```java
return MessageBuilder
    .withPayload(orderId)
    .setHeader("sourceSystem", "erp")
    .setHeader("businessEventId", eventId)
    .build();
```

`businessEventId` is an application-designed business key, useful for reconciliation or duplicate protection. Do not automatically rely on the per-message generated `id` header to identify the same event across multiple re-reads.

If the source returns a list and each element needs to go down a separate path, add a splitter. Increasing `maxMessagesPerPoll` does not automatically split a list into multiple messages.

## 5. Complete Example with a POJO Source

The example uses an in-memory buffer to simulate an order source. This allows testing without calling a real ERP.

Create `OrderEventSource.java`:

```java
package example.integration;

import java.util.Objects;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.integration.annotation.EndpointId;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class OrderEventSource {

    private final Queue<String> pendingOrders =
        new ConcurrentLinkedQueue<>();

    public void offer(String orderId) {
        pendingOrders.add(Objects.requireNonNull(orderId));
    }

    @EndpointId("ordersInbound")
    @InboundChannelAdapter(
        channel = "ordersChannel",
        autoStartup = "false",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "1"
        )
    )
    public Message<String> nextOrder() {
        String orderId = pendingOrders.poll();

        if (orderId == null) {
            return null;
        }

        return MessageBuilder
            .withPayload(orderId)
            .setHeader("sourceSystem", "demo-erp")
            .setHeader("businessEventId", "created:" + orderId)
            .build();
    }
}
```

Create `InboundOrderConfiguration.java`:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class InboundOrderConfiguration {

    @Bean
    public QueueChannel ordersChannel() {
        return new QueueChannel(20);
    }

    @Bean
    public OrderEventSource orderEventSource() {
        return new OrderEventSource();
    }
}
```

`OrderEventSource` does not need `@Component` because it is already registered via `@Bean`. `@EnableIntegration` enables Integration infrastructure for this pure Java Configuration example. The main dependency is `org.springframework.integration:spring-integration-core`.

The adapter is set with `autoStartup = "false"` so the runner can populate data first and then start the endpoint. Therefore, simply creating the context will not emit messages yet. In an application that wants polling right on startup, omit this attribute or set it to `"true"`.

`@EndpointId("ordersInbound")` names the polling endpoint, letting you control lifecycle without guessing an auto-generated name. It does not rename the `orderEventSource` bean or the `ordersChannel` bean. See [Javadoc for EndpointId](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/EndpointId.html).

### Controlled Startup

After the context has been created and refreshed, you can operate on it:

```java
OrderEventSource source = context.getBean(OrderEventSource.class);
source.offer("ORDER-1001");

SourcePollingChannelAdapter adapter = context.getBean(
    "ordersInbound",
    SourcePollingChannelAdapter.class
);

adapter.start();
```

This snippet requires importing `org.springframework.integration.endpoint.SourcePollingChannelAdapter` and assumes `context` is the application context of the configuration above.

The endpoint starts calling `nextOrder()` on schedule. It emits the first order and then receives `null` once the buffer is empty. The endpoint remains running to pick up new orders added later.

This buffer is for demonstration only. `poll()` already removes the element from memory; if sending downstream fails, this example does not restore that element.

## 6. Poller: Schedule and Receives Per Poll

For an active polling source, there must be a dedicated poller or a registered default poller in the context. You cannot omit the poller just because the output channel is a `DirectChannel`.

### fixedDelay, fixedRate, and cron

| Scheduling Style | Usage Meaning |
| --- | --- |
| `fixedDelay = "1000"` | Waits 1,000 milliseconds after the previous cycle completes before running the next |
| `fixedRate = "1000"` | Schedules cycles based on scheduled start times |
| `cron = "0 */5 * * * *"` | Schedules at second 0 every five minutes using Spring cron expressions |

Choose one scheduling mechanism per poller. Do not set `fixedDelay`, `fixedRate`, and `cron` simultaneously trying to combine schedules.

If one read-and-send cycle takes 300 ms, `fixedDelay = "1000"` produces an interval between starts of roughly 1,300 ms under ideal conditions. With cron schedules, specify the operational time zone when business requirements tie to local time.

`fixedRate` does not guarantee calls run in parallel or meet exact periods when the source is slow. Scheduler, executor, and execution duration still affect the real schedule.

### maxMessagesPerPoll

For `SourcePollingChannelAdapter`, the typical default is **one** receive per poll. This differs from the default of a `PollingConsumer` reading messages from a queue channel.

```java
poller = @Poller(
    fixedDelay = "1000",
    maxMessagesPerPoll = "5"
)
```

With this setting, one poll cycle can invoke the source up to five times. If the third call returns `null`, that poll stops pulling instead of completing all five calls.

You can visualize it as:

```text
poll 1: ORDER-1, ORDER-2, null
sleep per fixedDelay
poll 2: ORDER-3, null
sleep per fixedDelay
...
```

If a source method always returns data, such as always generating a heartbeat, do not casually set `maxMessagesPerPoll = "-1"`. A single poll could loop endlessly instead of yielding back to the polling schedule. A value of `0` means skipping reads in versions that support it; it is not an unlimited read mode.

These rules are presented in [Important: Poller Configuration](https://docs.spring.io/spring-integration/reference/channel-adapter.html#channel-adapter-inbound).

### Read Count Differs from Business Record Count

If each read returns a `List<Order>` containing 200 records, `maxMessagesPerPoll = "5"` can emit up to five list-carrying messages in one poll. It does not cap total business orders at five.

Therefore, consider together:

- Data size per query.
- Number of receives per poll.
- Downstream processing capacity.
- Message size and memory usage.

### receiveTimeout Does Not Replace Source Timeouts

`receiveTimeout` is primarily for a polling consumer reading from a `PollableChannel`. It does not impose a deadline on HTTP calls, JDBC queries, or arbitrary Java methods inside the source.

When reading an ERP over HTTP, configure connect/read timeouts on the HTTP client. When querying a database, use appropriate timeout mechanisms at the data access layer. See [Javadoc for Poller](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/Poller.html).

### Property Placeholders and Shared Pollers

You can externalize schedule parameters to configuration:

```java
@InboundChannelAdapter(
    channel = "ordersChannel",
    autoStartup = "${orders.inbound.enabled:true}",
    poller = @Poller(
        fixedDelay = "${orders.inbound.delay-ms:1000}",
        maxMessagesPerPoll = "${orders.inbound.max-messages:1}"
    )
)
```

This is a replacement annotation on the source method. The application needs placeholder resolution; standard Spring Boot configuration supplies this infrastructure.

If you want to use a named poller bean:

```java
@InboundChannelAdapter(
    channel = "ordersChannel",
    poller = @Poller("ordersPoller")
)
```

You must register `ordersPoller` as an appropriate `PollerMetadata`. When referencing by name, put the schedule, executor, or advice on the metadata bean; do not mix inline schedule attributes inside the same `@Poller`.

A default poller is another option. Example:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.scheduling.PollerMetadata;
import org.springframework.scheduling.support.PeriodicTrigger;

@Bean(name = PollerMetadata.DEFAULT_POLLER)
public PollerMetadata defaultPoller() {
    PollerMetadata metadata = new PollerMetadata();
    metadata.setTrigger(
        new PeriodicTrigger(Duration.ofSeconds(1))
    );
    metadata.setMaxMessagesPerPoll(1);
    return metadata;
}
```

Place this method in a `@Configuration` class and you can use `@InboundChannelAdapter(channel = "ordersChannel")`. A default poller affects other endpoints relying on it; dedicated pollers usually make each source's policy easier to see.

## 7. Supplier Bean: Factory Invoked Differently from Polled Source

You can annotate a `@Bean` method returning a `Supplier`. The following is a standalone configuration:

```java
package example.integration;

import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class SupplierInboundConfiguration {

    @Bean
    public Queue<String> pendingOrderIds() {
        Queue<String> queue = new ConcurrentLinkedQueue<>();
        queue.add("ORDER-S1");
        queue.add("ORDER-S2");
        return queue;
    }

    @Bean
    public QueueChannel supplierOrders() {
        return new QueueChannel(20);
    }

    @Bean
    @InboundChannelAdapter(
        channel = "supplierOrders",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "1"
        )
    )
    public Supplier<String> orderIdSupplier(
            Queue<String> pendingOrderIds) {
        return pendingOrderIds::poll;
    }
}
```

There are two distinct moments:

- The container calls `orderIdSupplier(...)` to create the bean, passing the `pendingOrderIds` dependency.
- During polling, the adapter calls `Supplier.get()` on the created bean.

The object returned by the factory is a `Supplier<String>`. The emitted data is the `String` returned by the supplier. When the queue drains, `get()` returns `null` so no more messages are emitted.

Do not place `@Bean` on a method returning an order directly expecting the factory method to be invoked on every poll. When declaring a source as a bean, return an appropriate source abstraction such as `Supplier` or `MessageSource`.

A `Supplier` can also return `Message<String>` when headers are needed. Configuration on `@Bean` methods is described in [Annotations on @Bean Methods](https://docs.spring.io/spring-integration/reference/configuration/meta-annotations.html#annotations-on-bean-methods).

## 8. MessageSource Bean: Working Directly with Message

`MessageSource<T>` has a `receive()` operation returning `Message<T>` or `null`. The type parameter `T` is the **payload** type, not the outer `Message<T>` type.

To convert the `Supplier` example to `MessageSource`, keep `pendingOrderIds` and `supplierOrders`, and replace the `orderIdSupplier` bean with:

```java
@Bean
@InboundChannelAdapter(
    channel = "supplierOrders",
    poller = @Poller(
        fixedDelay = "100",
        maxMessagesPerPoll = "1"
    )
)
public MessageSource<String> orderMessageSource(
        Queue<String> pendingOrderIds) {

    return () -> {
        String orderId = pendingOrderIds.poll();

        if (orderId == null) {
            return null;
        }

        return MessageBuilder
            .withPayload(orderId)
            .setHeader("sourceSystem", "demo-erp")
            .build();
    };
}
```

Additional imports:

```java
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.support.MessageBuilder;
```

Keep only one of the two source beans if you do not want two adapters reading the same queue. When both exist, they can pull different items; that is not an event-broadcasting mechanism.

| Source Form | Operation Called per Receive | When Appropriate |
| --- | --- | --- |
| POJO method | Zero-argument method designated by annotation | Reusing Java source-reading logic |
| `Supplier<T>` | `get()` | Simple source returning payload or message |
| `MessageSource<T>` | `receive()` | Integrating with an existing source abstraction or adapter |

The `receive()` contract and meaning of `null` are in [Javadoc for MessageSource](https://docs.spring.io/spring-integration/docs/6.0.x/api/org/springframework/integration/core/MessageSource.html).

## 9. Output Channel and Execution Flow

The inbound adapter's destination is a channel. This channel type determines what happens after the source builds a message.

### Output Is DirectChannel

```text
polling task -> invoke source -> DirectChannel -> synchronous handler
```

Downstream handlers run on the polling task's thread until another asynchronous boundary is reached. If a handler is slow, the polling cycle also stretches. If there is no subscriber, sending to `DirectChannel` can fail.

This is still an adapter with a poller. A subscribable output does not turn it into an event-driven source.

### Output Is QueueChannel

```text
polling task -> invoke source -> QueueChannel
                                    |
                          consumer reads later
```

Putting the message into a queue decouples ingestion time from business processing time. A successful send to the queue does not prove a consumer has finished processing.

A bounded-capacity queue limits buffering, though when full it can cause sends to block or fail depending on timeout settings. An unbounded queue can grow memory if the source outpaces consumers over a long period.

The queues in the examples are in-memory. If the application must persist data across restarts, choose an appropriate message store or broker/durable persistence mechanism.

## 10. Equivalent XML

To use XML as an alternative to the section 5 example, keep the logic of `OrderEventSource` but **remove `@InboundChannelAdapter` and `@EndpointId` from `nextOrder()`**. XML will take responsibility for creating the endpoint:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           https://www.springframework.org/schema/integration/spring-integration.xsd">

    <bean id="orderEventSource"
          class="example.integration.OrderEventSource"/>

    <int:channel id="ordersChannel">
        <int:queue capacity="20"/>
    </int:channel>

    <int:inbound-channel-adapter
            id="ordersInbound"
            ref="orderEventSource"
            method="nextOrder"
            channel="ordersChannel"
            auto-startup="false">
        <int:poller fixed-delay="100"
                    max-messages-per-poll="1"/>
    </int:inbound-channel-adapter>
</beans>
```

`ref` points to the bean holding the source-reading logic. `method` selects the zero-argument method. `channel` is where messages are sent, and `id` names the endpoint.

Load the XML into the application context instead of `InboundOrderConfiguration` to avoid duplicate bean registration. Afterward, you still need to add data to the source and call `start()` on the endpoint because `auto-startup` is `false`.

## 11. Equivalent Java DSL

Java DSL can clearly express the source and downstream flow in a single flow bean. Keep `ordersChannel` and the `orderEventSource` bean, remove the two endpoint annotations from `nextOrder()` as in the XML option, then add:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Bean
public IntegrationFlow ordersInboundFlow(
        OrderEventSource orderEventSource) {

    return IntegrationFlow.fromSupplier(
            orderEventSource::nextOrder,
            endpoint -> endpoint
                .id("ordersInbound")
                .autoStartup(false)
                .poller(
                    Pollers.fixedDelay(Duration.ofMillis(100))
                        .maxMessagesPerPoll(1)
                )
        )
        .channel("ordersChannel")
        .get();
}
```

Place the method in a `@Configuration` class with Integration infrastructure enabled. `fromSupplier(...)` defines the polled source; `.channel(...)` specifies the send destination.

Do not use `IntegrationFlow.from("ordersChannel")` as a direct substitute: the channel-name overload starts from messages **already on the channel**, whereas this problem requires calling a source to create new messages. Overloads are listed in [Javadoc for IntegrationFlow](https://docs.spring.io/spring-integration/docs/6.1.2/api/org/springframework/integration/dsl/IntegrationFlow.html).

The annotation, XML, and DSL options here are alternative declarations for the same endpoint. Combining all three without adjustment creates extra endpoints or name conflicts rather than making polling more accurate.

## 12. Polling Errors and ErrorMessage

A source can fail before creating a message, such as an HTTP client failing to connect to the ERP. Errors can also occur when the adapter sends the message to the channel or while a synchronous downstream handler runs.

The poller runs under scheduling infrastructure, so task failures cannot return to a waiting business request-reply call. You can configure a dedicated error channel:

```java
@InboundChannelAdapter(
    channel = "ordersChannel",
    poller = @Poller(
        fixedDelay = "1000",
        maxMessagesPerPoll = "1",
        errorChannel = "ordersPollingErrors"
    )
)
```

Register the `ordersPollingErrors` bean and connect an error-handling consumer to it. In standard infrastructure, the error handler emits an `ErrorMessage` with the exception as payload. A message's `errorChannel` header, once a message exists and an error handler honors that header, can affect the error destination; the poller's attribute specifies the handler's default channel.

If the source throws an error before constructing a message, there may be no business message available to attach to the error info. Do not assume every source failure includes full order IDs.

The overall mechanism is described in [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

### Standalone Error Configuration for Practice

The following example always throws an exception when reading the source and explicitly waits for startup. It is for testing error paths, not a real order source:

```java
package example.integration;

import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EndpointId;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class FailingInboundConfiguration {

    @Bean
    public QueueChannel failureOutput() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel ordersPollingErrors() {
        return new QueueChannel(20);
    }

    @Bean
    @EndpointId("failingInbound")
    @InboundChannelAdapter(
        channel = "failureOutput",
        autoStartup = "false",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "1",
            errorChannel = "ordersPollingErrors"
        )
    )
    public Supplier<String> failingSource() {
        return () -> {
            throw new IllegalStateException(
                "Unable to read source data"
            );
        };
    }
}
```

An error `QueueChannel` only stores messages for a consumer to read. It does not automatically retry, log, or return data to the source.

Distinguish two scenarios:

- The next poll attempts to call the source again after a connection failure.
- Retrying an order already pulled from the source whose processing failed.

These two tasks may require different policies. Having an adapter continue on schedule does not automatically ensure an already-pulled order gets resent.

## 13. Testing the Source and Endpoint

The test examples below belong in package `example.integration`. They use the three classes presented: `OrderEventSource`, `InboundOrderConfiguration`, and `FailingInboundConfiguration`.

### 13.1. Testing the Source Contract Without Creating a Context

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class OrderEventSourceTest {

    @Test
    void returnsOneMessageThenNullWhenSourceIsEmpty() {
        OrderEventSource source = new OrderEventSource();

        assertNull(source.nextOrder());

        source.offer("ORDER-1001");

        Message<String> message = source.nextOrder();
        assertNotNull(message);
        assertEquals("ORDER-1001", message.getPayload());
        assertEquals(
            "demo-erp",
            message.getHeaders().get("sourceSystem")
        );
        assertEquals(
            "created:ORDER-1001",
            message.getHeaders().get("businessEventId")
        );

        assertNull(source.nextOrder());
    }
}
```

This test verifies source-reading logic and headers. Calling an annotated method directly is still a normal Java call; it creates no polling schedule and does not automatically send results to a channel.

### 13.2. Testing Polling, Lifecycle, and Empty-Source Behavior

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.endpoint.SourcePollingChannelAdapter;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class InboundChannelAdapterTest {

    @Test
    void pollsOnlyAfterAdapterIsStarted() {
        try (var context = new AnnotationConfigApplicationContext(
                InboundOrderConfiguration.class)) {

            OrderEventSource source =
                context.getBean(OrderEventSource.class);
            QueueChannel output = context.getBean(
                "ordersChannel", QueueChannel.class);
            SourcePollingChannelAdapter adapter = context.getBean(
                "ordersInbound",
                SourcePollingChannelAdapter.class
            );

            source.offer("ORDER-A");
            source.offer("ORDER-B");

            assertFalse(adapter.isRunning());
            assertNull(output.receive(0));

            adapter.start();
            assertTrue(adapter.isRunning());

            Message<?> first = output.receive(3_000);
            Message<?> second = output.receive(3_000);

            assertNotNull(first);
            assertNotNull(second);
            assertEquals("ORDER-A", first.getPayload());
            assertEquals("ORDER-B", second.getPayload());
            assertEquals(
                "demo-erp",
                first.getHeaders().get("sourceSystem")
            );

            adapter.stop();
            assertFalse(adapter.isRunning());
        }
    }

    @Test
    void canReceiveNewDataAfterSourceWasEmpty() {
        try (var context = new AnnotationConfigApplicationContext(
                InboundOrderConfiguration.class)) {

            OrderEventSource source =
                context.getBean(OrderEventSource.class);
            QueueChannel output = context.getBean(
                "ordersChannel", QueueChannel.class);
            SourcePollingChannelAdapter adapter = context.getBean(
                "ordersInbound",
                SourcePollingChannelAdapter.class
            );

            adapter.start();

            assertNull(output.receive(250));

            source.offer("ORDER-LATER");

            Message<?> received = output.receive(3_000);
            assertNotNull(received);
            assertEquals("ORDER-LATER", received.getPayload());

            adapter.stop();
        }
    }

    @Test
    void routesSourceFailureToConfiguredErrorChannel() {
        try (var context = new AnnotationConfigApplicationContext(
                FailingInboundConfiguration.class)) {

            SourcePollingChannelAdapter adapter = context.getBean(
                "failingInbound",
                SourcePollingChannelAdapter.class
            );
            QueueChannel errors = context.getBean(
                "ordersPollingErrors", QueueChannel.class);
            QueueChannel output = context.getBean(
                "failureOutput", QueueChannel.class);

            adapter.start();

            Message<?> error = errors.receive(3_000);

            adapter.stop();

            assertNotNull(error);
            assertTrue(error instanceof ErrorMessage);
            assertTrue(error.getPayload() instanceof Throwable);
            assertNull(output.receive(0));
        }
    }
}
```

The tests use `receive(timeout)` to wait for results instead of `Thread.sleep(...)`. When data arrives early, receive returns immediately; when a configuration error exists, the wait time remains bounded.

`try-with-resources` closes the context to stop scheduling resources after tests. Starting the adapter after preparing data cleanly separates arrangement from execution.

The empty-source test observes no data during a wait interval and then adds data to verify the adapter can still emit messages. It does not measure exact source invocation counts or per-tick timing precision.

These tests also do not prove load capacity, read-and-send atomicity, or recovery after process shutdown. If the real source uses an ERP or database, add tests for that layer's contract.

## 14. Diagnosing Common Errors

| Symptom | Causes to Check | How to Fix |
| --- | --- | --- |
| Annotation present but no polling occurs | Object is not a bean, config not loaded, or annotation infrastructure not enabled | Check bean registration and Integration configuration |
| Adapter fails to start | Neither dedicated poller nor valid default poller | Declare an explicit polling schedule |
| Source method rejected | Takes parameters or returns `void` | Inject dependencies into source object; return data or message |
| No data even though context started | `autoStartup` is `false`, source returns `null`, or receive limit is `0` | Check endpoint state and source read results |
| Output queue empty during tests | Checked before poller ran or reading wrong channel | Use `receive(timeout)` on the right output |
| Emits a list instead of individual orders | Source returns a collection | Add a splitter if the contract requires one message per item |
| Poll cycle never finishes | Unlimited receives while source never returns `null` | Set a finite limit or fix the cycle-ending contract |
| Lower frequency than expected | Slow source or synchronous handler; target queue full | Measure read, send, and processing times instead of just shrinking delay |
| Send to DirectChannel fails | No subscriber at output | Register and start a consumer |
| Data read multiple times across instances | Multiple processes polling without coordination | Design claim/lock/partitioning with a deduplication strategy |

### Lifecycle Is Not a Distributed Lock

`autoStartup` controls one endpoint inside one application context. `phase` controls start and stop order among lifecycle components.

These two attributes do not elect a single instance to read the ERP. If the application runs three replicas and all three adapters start, all three can poll the same source.

Depending on the problem, design record claiming, leased locks, leader election, or source partitioning. Downstream processing logic still must account for duplicate events when the source or infrastructure can redeliver.

### Tracking All Three Stages Properly

When investigating data loss, distinguish:

1. What data did the source return and did it mutate source state?
2. Did the adapter successfully send the message to the channel?
3. Did the business consumer process it successfully?

A log saying "read 100 orders" only proves the first stage. A successful send to a queue only proves the message was accepted at the queue boundary. Business tracing is needed to connect the stages.

## 15. Designing a Source for Real-World Applications

The `OrderEventSource` example uses `poll()` to remove items from the buffer before sending. This is simple for learning the API contract, but ensuring data safety in a real system requires defining when completion is marked.

For instance, if reading a `pending_order_events` table:

```text
select/claim event
       |
       v
create message with businessEventId
       |
       v
send into integration flow
       |
       v
process and record outcome per designed contract
```

If an event is marked "processed" immediately on read and the process stops before sending, data can be skipped. If marked only at the end, plan for re-reads or reprocessing.

Requirements must be expressed with concrete mechanisms:

- Timeouts for source queries and connections.
- Marking, claiming, or checkpointing strategy.
- Durable persistence at boundaries requiring data protection.
- Bounded retries and an error-handling path once retries are exhausted.
- Stable business keys so consumers can detect already-processed events.
- Bounds on batch size, payload size, and concurrency.

`@InboundChannelAdapter` does not automatically provide distributed transactions or exactly-once guarantees. Even if transaction advice is used on the poller, identify which resources actually participate in the transaction. An HTTP call or in-memory queue does not automatically become a database transaction resource.

When a source has a dedicated Spring Integration adapter, evaluate that adapter's read and acknowledgment contract instead of assuming every source behaves like a plain Java method in this lesson.

In a complete flow, the inbound adapter brings source data in as messages. Filters, transformers, routers, aggregators, and business handlers carry out their respective roles downstream of the entry point. Reading configurations along the chain **poller -> source -> message -> output channel -> processing endpoints** helps pinpoint where scheduling, data transformation, and error handling live.

# @BridgeFrom

## 1. Objectives and Scope

In the **Annotations and XML** chapter of the **SPRING_INTEGRATION_CORE** module, `@BridgeFrom` declares a message bridge directly on the target channel bean. This lesson focuses on reading the configuration, choosing the source channel, configuring pollers, and testing message forwarding.

After this lesson, you can:

- Accurately identify the input channel, output channel, and endpoint created by `@BridgeFrom`.
- Connect flow segments without writing extra business processing methods.
- Distinguish an event-driven bridge from a bridge that polls messages from a queue.
- Translate configurations between annotations, XML, and Java DSL.
- Explain how a bridge affects execution flow and error paths.

You should know that `Message<?>` contains a payload and headers, `MessageChannel` provides `send(...)`, and `PollableChannel` adds `receive(...)`. The examples use Java 17, Spring Integration 6.x APIs, and JUnit Jupiter. Spring dependencies should be managed by your project's compatible BOM or Spring Boot platform; this lesson does not require changing your current dependency versions.

## 2. Problem: Connecting Two Message Flow Segments

Suppose one component sends order IDs to `incomingOrders`. Another component only knows how to read from `acceptedOrders`. Both teams want to keep separate channel names to express each flow segment's responsibility.

If the message is already in the right format, you can use a bridge:

```text
Producer
   |
   v
incomingOrders
   |
   v
BridgeHandler
   |
   v
acceptedOrders
   |
   v
Consumer
```

A bridge receives messages on one channel and forwards them to another channel. When content needs to change, place a transformer at the appropriate spot. When a path needs to be chosen based on data, use a router. A bridge fits connections with no transformation or branching rules. Spring Integration describes this component in [Messaging Bridge](https://docs.spring.io/spring-integration/reference/bridge.html).

For example, a router can place valid orders onto `validatedOrders`; a bridge then connects that channel to the input of a shared processing flow. Validation and routing still belong to endpoints upstream of the bridge.

## 3. How to Read @BridgeFrom

The shortest configuration looks like:

```java
@Bean
@BridgeFrom("incomingOrders")
public QueueChannel acceptedOrders() {
    return new QueueChannel(20);
}
```

Reading from the annotation name: **the declared channel receives messages from `incomingOrders` through a bridge**.

| Component | Meaning in the Example |
| --- | --- |
| `incomingOrders` | Source channel bean name, where the bridge receives messages |
| `acceptedOrders` | Target channel bean created by the `@Bean` method |
| `BridgeHandler` | Handler registered by annotation infrastructure to forward messages |
| Consumer endpoint | Component attaching the handler to the source channel and managing how messages are received |

A common point of confusion is that the annotation sits on the **output channel bean**. The value `"incomingOrders"` points to the input channel.

The `acceptedOrders()` method is a bean factory method. It is not called again for each order and does not take payloads as business processing parameters. Forwarding happens inside the endpoint created by Spring Integration.

This is how you declare a bridge on a `@Bean` method returning `MessageChannel` or a specific channel type. The annotation can be used as a meta-annotation, though there is no need to build custom annotations for simple configurations. See [Creating a Bridge with Annotations](https://docs.spring.io/spring-integration/reference/configuration/meta-annotations.html#creating-a-bridge-with-annotations).

## 4. Conditions for the Configuration to Take Effect

In an application using plain Spring Java Configuration, declare `@EnableIntegration` on a configuration class loaded into the `ApplicationContext`:

```java
@Configuration
@EnableIntegration
public class OrderIntegrationConfiguration {
    // Channel and endpoint beans.
}
```

The corresponding imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.BridgeFrom;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
```

Production dependencies require `org.springframework.integration:spring-integration-core`. The tests below require JUnit Jupiter and your project's JUnit 5 runner.

With Spring Boot, integration infrastructure may already be auto-configured. The examples still declare `@EnableIntegration` to make the prerequisite clear when running with `AnnotationConfigApplicationContext`.

Explicitly declare the source channel bean rather than relying on implicit channel creation in other configuration styles. If the source should be a queue, an accidentally auto-created `DirectChannel` bean changes both message reception and execution flow.

## 5. The Source Channel Determines How the Bridge Receives Messages

In standard usage without reactive mode enabled, the **source** channel type determines the consumer endpoint type:

| Source Channel | Consumer Endpoint | Reception Mechanism | Poller |
| --- | --- | --- | --- |
| `DirectChannel` or a `SubscribableChannel` implementation | `EventDrivenConsumer` | Registers handler for the channel to invoke when a message arrives | Do not configure |
| `QueueChannel` or a `PollableChannel` implementation | `PollingConsumer` | Actively calls `receive(...)` on a schedule | Requires a dedicated poller or valid default poller |

The target channel can differ in type from the source channel. For example:

```text
Source DirectChannel -> bridge -> Target QueueChannel
Source QueueChannel  -> poller/bridge -> Target DirectChannel
Source QueueChannel  -> poller/bridge -> Target QueueChannel
```

In the first line, the bridge is event-driven even though the target channel is a queue. In the next two lines, the bridge must poll because the source is a queue.

The separation between handler and endpoint is explained in [Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html).

## 6. Complete Example: DirectChannel to QueueChannel

Create class `DirectBridgeConfiguration.java`:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.BridgeFrom;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class DirectBridgeConfiguration {

    @Bean
    public DirectChannel incomingOrders() {
        return new DirectChannel();
    }

    @Bean
    @BridgeFrom("incomingOrders")
    public QueueChannel acceptedOrders() {
        return new QueueChannel(20);
    }
}
```

Flow of execution:

1. Producer calls `incomingOrders.send(message)`.
2. `DirectChannel` invokes the bridge handler on the producer's thread.
3. The bridge sends the message to `acceptedOrders`.
4. `QueueChannel` holds the message for a consumer to read later.

Because the input is a `DirectChannel`, the configuration has no `@Poller`. Having a queue at the output does not make the bridge switch to polling.

In this configuration, a successful `send(...)` indicates the message has been delivered to the target queue. It does not prove a downstream consumer has finished processing the order.

`QueueChannel(20)` has a bounded capacity. If there is no consumer yet and producers keep sending, the queue can fill up. Account for wait timeouts when designing send paths across bounded channels; a send timeout on the source channel does not implicitly limit the entire downstream processing chain.

### Payload and Headers

A bridge declares no payload transformation. With an illustrative flow consisting only of two channels and a bridge, you expect the order ID along with headers such as `traceId` to appear at the output.

Do not generalize this into a guarantee that every header and `Message` object instance always remains untouched in a larger flow. Interceptors, message history, transformers, or adapters in other segments can add metadata or construct new messages. Tests should focus on the data contract that must be preserved.

## 7. Complete Example: QueueChannel to QueueChannel

A producer can enqueue messages first while the bridge drains them on a schedule. Create class `QueueBridgeConfiguration.java`:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.BridgeFrom;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class QueueBridgeConfiguration {

    @Bean
    public QueueChannel bufferedOrders() {
        return new QueueChannel(20);
    }

    @Bean
    @BridgeFrom(
        value = "bufferedOrders",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "10",
            receiveTimeout = "0"
        )
    )
    public QueueChannel readyOrders() {
        return new QueueChannel(20);
    }
}
```

Here:

- `bufferedOrders` decouples intake from when the bridge forwards messages.
- The created endpoint is a `PollingConsumer`.
- `fixedDelay = "100"` sets a 100-millisecond pause after the previous polling cycle finishes.
- `maxMessagesPerPoll = "10"` limits how many messages are pulled in one poll.
- `receiveTimeout = "0"` makes the read return immediately if the source is empty.

A polling cycle does not combine ten orders into one message. The bridge still forwards each `Message` individually. If you need to combine elements into one result, you need an aggregator with correlation rules and a release condition.

A limit of ten messages per poll also does not guarantee an exact rate of 100 messages per second. Processing time, scheduler execution, and downstream receive capacity all affect actual throughput.

### Changing the Output to DirectChannel

If `readyOrders` is a `DirectChannel`, the poller configuration still stays on the annotation of the `readyOrders` bean because it controls reading from `bufferedOrders`:

```java
@Bean
@BridgeFrom(
    value = "bufferedOrders",
    poller = @Poller(
        fixedDelay = "100",
        maxMessagesPerPoll = "10",
        receiveTimeout = "0"
    )
)
public DirectChannel readyOrders() {
    return new DirectChannel();
}
```

When using this variant, there must be a consumer subscribed to `readyOrders`, such as a service activator. If downstream segments continue using synchronous channels, downstream business logic runs on the thread executing the polling cycle. Changing only the output to `DirectChannel` does not return execution to the original producer thread.

## 8. Attributes to Understand

| Attribute | Role | Notes |
| --- | --- | --- |
| `value` | Source channel name | Required for `@BridgeFrom` |
| `poller` | Configuration for reading a pollable source | Do not use for a `DirectChannel` source |
| `autoStartup` | Lets the endpoint start automatically with lifecycle | Defaults to `"true"` |
| `phase` | Controls lifecycle startup/shutdown order | Does not order individual messages |
| `reactive` | Selects reactive consumption | Mutually exclusive with `poller` |

Attributes and usage conditions are documented in [Javadoc for BridgeFrom](https://docs.spring.io/spring-integration/docs/6.0.x/api/org/springframework/integration/annotation/BridgeFrom.html).

### Externalizing Parameters to Application Configuration

String-typed poller attributes support property placeholders:

```java
@Bean
@BridgeFrom(
    value = "bufferedOrders",
    autoStartup = "${orders.bridge.auto-startup:true}",
    poller = @Poller(
        fixedDelay = "${orders.bridge.delay-ms:100}",
        maxMessagesPerPoll = "${orders.bridge.batch-size:10}",
        receiveTimeout = "0"
    )
)
public QueueChannel readyOrders() {
    return new QueueChannel(20);
}
```

This snippet replaces the `readyOrders` bean, rather than adding a second bean with the same name. The application needs placeholder resolution configured; Spring Boot provides this infrastructure when using standard application configuration.

`orders.bridge.batch-size` is simply a property name chosen for the example. It controls the receive limit per poll, without changing payload types.

### Using a Named PollerMetadata

When complex polling options such as advice or transactions are needed, you can declare a `PollerMetadata` bean and reference it:

```java
@BridgeFrom(
    value = "bufferedOrders",
    poller = @Poller("orderBridgePoller")
)
```

This snippet assumes `orderBridgePoller` is already declared. When referencing a bean name in `@Poller`, put other options on the metadata bean; do not mix a bean name with `fixedDelay` or `maxMessagesPerPoll` in the same annotation. See [Javadoc for Poller](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Poller.html).

If the source is a `PollableChannel` and `poller` is omitted, the framework can fall back to a registered default poller. When neither a dedicated poller nor a default poller exists, the configuration fails to initialize the endpoint. The examples declare pollers directly so readers can see the polling schedule.

## 9. Execution Flow and Errors

### 9.1. Synchronous Path

With a chain of synchronous channels:

```text
producer thread
  -> DirectChannel
  -> bridge
  -> DirectChannel
  -> business handler
```

If the downstream handler throws an exception, the error can propagate back along the `send(...)` call to the producer. Simply adding a bean named `errorChannel` does not turn every synchronous exception into an error message.

### 9.2. Path with an Input Queue

With a queue source:

```text
producer thread -> bufferedOrders -> producer continues
                         |
                  scheduled poller
                         |
                       bridge
                         |
                 downstream consumer
```

Errors occurring while the poller is processing cannot propagate back to the producer's already-completed `send(...)` call. Polling infrastructure can publish an `ErrorMessage` to an error channel. The error message carries the exception as its payload.

You can designate a dedicated default error channel for the poller:

```java
@BridgeFrom(
    value = "bufferedOrders",
    poller = @Poller(
        fixedDelay = "100",
        maxMessagesPerPoll = "10",
        receiveTimeout = "0",
        errorChannel = "orderBridgeErrors"
    )
)
```

Declare the corresponding channel in the configuration:

```java
@Bean
public QueueChannel orderBridgeErrors() {
    return new QueueChannel(20);
}
```

The two snippets above show changes to the polling example. An error-handling consumer must read `orderBridgeErrors` or be connected to it by an appropriate endpoint; a queue alone does not log errors or recover orders.

The `errorChannel` header on a message can determine the error destination before the error handler's default channel. To understand resolution and differences from synchronous exceptions, see [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

### 9.3. Additional Design Considerations

An error routed to an error channel does not mean the order will be reprocessed. A bridge does not add retries, dead-letter queues, or duplicate-processing protection.

With an in-memory `QueueChannel`, the message has already been removed from the source before forwarding. If downstream fails, do not assume the message automatically reappears in the old queue. When recovery is needed, design retries, error-handling paths, or appropriate persistence/transaction mechanisms.

Similarly, passing work through a queue does not propagate a transaction bound to the producer thread onto the poller thread. Requirements such as updating order status and emitting an event atomically require dedicated transaction design.

## 10. How Do @BridgeFrom and @BridgeTo Differ?

Both annotations can represent the same connecting edge, but they sit on opposite ends:

| Annotation | Placed On Bean | Annotation Value |
| --- | --- | --- |
| `@BridgeFrom("source")` | Target channel | Source channel name |
| `@BridgeTo("target")` | Source channel | Target channel name |

The following examples are **two alternative options** for expressing `incomingOrders -> acceptedOrders`.

Option using `@BridgeFrom`:

```java
@Bean
public DirectChannel incomingOrders() {
    return new DirectChannel();
}

@Bean
@BridgeFrom("incomingOrders")
public QueueChannel acceptedOrders() {
    return new QueueChannel(20);
}
```

Option using `@BridgeTo`:

```java
@Bean
@BridgeTo("acceptedOrders")
public DirectChannel incomingOrders() {
    return new DirectChannel();
}

@Bean
public QueueChannel acceptedOrders() {
    return new QueueChannel(20);
}
```

The second option requires importing `org.springframework.integration.annotation.BridgeTo`. Do not place both annotations on the same edge trying to "declare both ends"; you will register an extra endpoint.

Choose `@BridgeFrom` when reading configurations from the target channel's input perspective. Choose `@BridgeTo` when you want to place the forwarding destination directly on the source channel. The rule for choosing polling based on the **source** remains unchanged. Details are in [Javadoc for BridgeTo](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/BridgeTo.html).

## 11. Equivalent XML Configuration

The XML example below expresses the same structure—source queue, bridge with poller, and target queue—as `QueueBridgeConfiguration`:

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

    <int:channel id="bufferedOrders">
        <int:queue capacity="20"/>
    </int:channel>

    <int:channel id="readyOrders">
        <int:queue capacity="20"/>
    </int:channel>

    <int:bridge id="ordersBridge"
                input-channel="bufferedOrders"
                output-channel="readyOrders">
        <int:poller fixed-delay="100"
                    max-messages-per-poll="10"
                    receive-timeout="0"/>
    </int:bridge>
</beans>
```

In XML, input and output appear directly on `<int:bridge>`. With annotations, the output is inferred from the bean carrying `@BridgeFrom`.

If the source is a subscribable channel, the XML bridge declaration has no poller element. The XML must be loaded into the application context for the configuration to take effect.

Pick one mechanism to declare this connecting edge. When importing XML into an application that already has the corresponding bridge annotation, remove one of the two declarations to avoid creating a second consumer.

## 12. Equivalent Java DSL

With Java DSL, keep the two beans `bufferedOrders` and `readyOrders`, but remove `@BridgeFrom` from `readyOrders`. Add a flow bean:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

// Method placed in a @Configuration class with @EnableIntegration.
@Bean
public IntegrationFlow ordersBridgeFlow() {
    return IntegrationFlow.from("bufferedOrders")
        .bridge(endpoint -> endpoint.poller(
            Pollers.fixedDelay(Duration.ofMillis(100))
                .maxMessagesPerPoll(10)
                .receiveTimeout(0)
        ))
        .channel("readyOrders")
        .get();
}
```

`.bridge(...)` creates the forwarding step; `.channel("readyOrders")` designates the destination. The poller is configured on the endpoint reading from the source.

Annotations are convenient when the link can be read directly on the channel bean. DSL is often easier to follow when viewing an entire multi-step chain:

```text
gateway -> filter -> transformer -> router -> processing flows
```

A bridge can serve as a connector in that architecture. It does not provide a request-reply contract like a gateway, evaluate filtering predicates, or replace an aggregator's correlation rules.

## 13. Testing the Forwarding Contract

Both configurations from sections 6 and 7 can be used directly in a JUnit 5 test. Create `BridgeFromTest.java` in the same package:

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BridgeFromTest {

    @Test
    void forwardsFromDirectChannelAndKeepsBusinessHeader() {
        try (var context = new AnnotationConfigApplicationContext(
                DirectBridgeConfiguration.class)) {

            MessageChannel input = context.getBean(
                "incomingOrders", MessageChannel.class);
            QueueChannel output = context.getBean(
                "acceptedOrders", QueueChannel.class);

            Message<String> sent = MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("traceId", "trace-direct-1001")
                .build();

            assertTrue(input.send(sent));

            Message<?> received = output.receive(0);
            assertNotNull(received);
            assertEquals("ORDER-1001", received.getPayload());
            assertEquals(
                "trace-direct-1001",
                received.getHeaders().get("traceId")
            );
        }
    }

    @Test
    void forwardsFromQueueUsingConfiguredPoller() {
        try (var context = new AnnotationConfigApplicationContext(
                QueueBridgeConfiguration.class)) {

            MessageChannel input = context.getBean(
                "bufferedOrders", MessageChannel.class);
            QueueChannel output = context.getBean(
                "readyOrders", QueueChannel.class);

            Message<String> sent = MessageBuilder
                .withPayload("ORDER-2001")
                .setHeader("traceId", "trace-queue-2001")
                .build();

            assertTrue(input.send(sent, 1_000));

            Message<?> received = output.receive(3_000);
            assertNotNull(received);
            assertEquals("ORDER-2001", received.getPayload());
            assertEquals(
                "trace-queue-2001",
                received.getHeaders().get("traceId")
            );
        }
    }
}
```

The first test reads with `receive(0)` because the bridge runs immediately on the synchronous send path and the target starts empty. The second test waits up to three seconds because the polling schedule is independent of the producer.

Do not use `Thread.sleep(...)` to guess completion timing. `receive(timeout)` both waits for the expected data and bounds the wait when a configuration has errors. Closing the context via `try-with-resources` stops polling resources after the test.

These assertions verify that the payload and business header reach the destination in both minimal configurations. They do not prove load capacity, data durability, retries, or atomicity of a real order flow. The three-second mark is a test timeout, not an application latency SLA.

## 14. Common Configuration Errors

| Symptom | What to Check | How to Fix |
| --- | --- | --- |
| No forwarding endpoint exists | Was the config class loaded and annotation infrastructure enabled? | Check configuration registration and `@EnableIntegration`/auto-configuration |
| Initialization fails on source channel | Does `value` match the bean name and is that bean a channel? | Explicitly declare the source channel and fix the reference name |
| Source is a queue but endpoint fails to initialize | Is there a dedicated poller or default poller? | Declare an appropriate poller |
| Config reports poller cannot be used | Is the actual source a `DirectChannel`? | Remove the poller or use the channel type intended by the design |
| Sending to `DirectChannel` fails with no subscribers | Is a consumer on the output registered and started? | Add or start the consuming endpoint |
| Messages do not all pass through the bridge | Does the source have another consumer? Is the endpoint running? | Inspect the flow graph and lifecycle |
| Sending slows down or blocks | Is the target queue full? Is a synchronous handler slow? | Check capacity, consumers, and timeouts |
| Errors occur after producer already succeeded | Is there a queue or executor boundary? | Monitor the error path of the asynchronous segment |

### autoStartup and phase

`autoStartup = "false"` prevents the **bridge endpoint** from starting automatically when the context starts. The target channel bean is still created normally.

If the source is a queue, messages can sit in it while the bridge is not yet running. If the source is a `DirectChannel` and no other subscriber exists, sending to the channel can fail because there is no handler.

When operational control is needed, retrieve the endpoint lifecycle to call `start()`/`stop()` or use an appropriate management mechanism. Calling `start()` on the channel object does not replace starting the bridge.

`phase` adjusts the start and stop ordering of lifecycle components. It does not order individual orders and does not make messages on a lower-priority channel wait for messages on another channel.

### Competing Consumers

`DirectChannel` has point-to-point semantics. If a bridge and a service activator are both registered on that source, do not expect both to receive every message. `QueueChannel` also delivers each message to a single reader; a bridge can compete with other consumers.

When the requirement is to broadcast the same event to multiple branches, design a `PublishSubscribeChannel` or a router per the contract. Distribution and blocking properties of channels are described in [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### Avoiding Loops

Do not bridge a channel back to itself, or create a multi-channel cycle with no termination condition:

```text
channelA -> bridge -> channelB -> bridge -> channelA
```

With synchronous channels, a cycle can repeatedly recurse. With queues, it can loop the same data endlessly and exhaust resources. When reviewing configurations, draw directed edges before analyzing business handlers.

## 15. Applying to a Real Flow

Suppose a system intakes orders in this sequence:

```text
gateway
  -> data validation
  -> order normalization
  -> classification router
  -> bufferedOrders
  -> bridge with poller
  -> readyOrders
  -> business handler
```

In this design, `@BridgeFrom` fits well if you want the `readyOrders` channel to explicitly declare that it receives messages from `bufferedOrders`. The poller expresses the policy for draining the buffer, while the downstream handler focuses on processing orders.

Before adopting that pattern, verify specific requirements:

- If orders must survive restarts, the example's in-memory `QueueChannel` does not satisfy durability requirements.
- If the producer needs to know the business result, sending to a queue must be paired with an appropriate reply contract.
- If failed items must be replayed, define where original data is stored, the retry policy, and where error handling terminates.
- If the same event must go to multiple processing groups, pick the right distribution structure before adding bridges.

With a `@BridgeFrom` declaration, the consistent way to read it is: **take messages from the channel named in the annotation, let the endpoint receive according to the source's mechanism, and use the bridge to forward them to the annotated channel bean**.

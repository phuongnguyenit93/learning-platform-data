# MessageCollector Receiving Messages in Spring Integration Runtime Tests

## Goal and an important API distinction

In **SPRING_INTEGRATION_RUNTIME**, an IntegrationFlow can receive messages from a channel, process them with a transformer, service activator, poller, or executor, and send them onward to an output channel. When testing, the fundamental question is: **which messages arrived at the output, with what payload/headers, in what order, and within what duration?**

**MessageCollector** is often mentioned in message flow testing examples because it **collects emitted messages so tests can retrieve and assert on them**. However, you must identify the right library:

> **MessageCollector with the forChannel(...) API belongs to Spring Cloud Stream's legacy test-support binder**, specifically **org.springframework.cloud.stream.test.binder.MessageCollector**, not a default bean/API provided by modern **spring-integration-test**. Spring Cloud Stream has moved to a test binder with **InputDestination/OutputDestination**; a **pure Spring Integration** application typically verifies output using **QueueChannel, WireTap, or a mock MessageHandler**.

All three approaches share the goal of **observing messages after a flow**, yet they have different framework boundaries and dependencies. This lesson covers **legacy MessageCollector** in its proper context, then guides you on implementing equivalent behavior for modern Spring Integration runtimes.

By the end of this lesson, you will be able to:

- Explain how **MessageCollector.forChannel(MessageChannel)** returns a queue for retrieving messages in legacy tests.
- Use **poll(timeout, unit)** to avoid false failures during asynchronous processing.
- Assert payloads, headers, correlation, counts, duplicates, and guaranteed vs. non-guaranteed ordering.
- Know when to use **QueueChannel** in Spring Integration versus **OutputDestination** in Spring Cloud Stream.
- Collect messages from a **DirectChannel that already has a business consumer** without accidentally stealing messages by choosing **WireTap** properly.
- Control pollers, executors, errorChannel, retries, message stores, and lifecycle in tests to reduce flaky tests.
- Distinguish in-JVM tests from tests with real brokers, transactions, persistence, and restarts.

## 1. Where the collector sits in a message flow

Simple business example: receive OrderSubmitted, normalize data, emit OrderAccepted or ErrorMessage.

~~~mermaid
flowchart LR
    T["JUnit test"] --> I["inputChannel"]
    I --> F["IntegrationFlow<br/>transformer / handler"]
    F --> O["outputChannel"]
    O --> C["Message collector<br/>test sink"]
    C --> A["Assertion<br/>payload, headers, count"]
    F -. "exception" .-> E["errorChannel"]
    E --> CE["Error collector"]
~~~

A minimal test performs:

1. **Arrange:** create the application context, channels/flows, input source, and output capture point.
2. **Act:** send a message with a known payload/headers.
3. **Await:** receive the output message from the queue with a finite timeout.
4. **Assert:** verify the message exists, the payload is correct, and correlation/headers are preserved per contract.
5. **Cleanup:** drain queues or isolate the context, reset mocks, and stop auto-producing endpoints.

### Why not just assert that send() returns true?

~~~java
boolean sent = input.send(message);
assertTrue(sent);
~~~

This mainly verifies **the channel accepted the send**. If the flow subsequently goes through an **ExecutorChannel** or a QueueChannel with a polling consumer, business processing may **not yet be complete** when send() returns. Even with a DirectChannel, tests should check **output messages and side effects** rather than merely checking dispatch status.

### Three mechanisms to distinguish

| Component | Which ecosystem? | What is it used for? |
| --- | --- | --- |
| **MessageCollector** + TestSupportBinder | **Legacy Spring Cloud Stream test-support** | Captures outbound messages on a binding/channel so tests can pull them from a BlockingQueue |
| **OutputDestination / InputDestination** | **Modern Spring Cloud Stream test binder** | Receives/sends messages at a simulated **binding/destination** boundary using an in-JVM binder |
| **QueueChannel, WireTap, MockIntegrationContext, MockMessageHandler** | **Spring Integration / spring-integration-test** | Observes and controls messages at channels/endpoints inside an IntegrationFlow |

Do not autowire **MessageCollector** in a project that only includes **spring-integration-test** expecting Spring to create this bean automatically. Without **legacy Spring Cloud Stream test-support**, that bean/class may not exist; the right approach for pure Spring Integration flows is to use Spring Integration's own tools.

## 2. How does legacy MessageCollector work?

In older generations of Spring Cloud Stream using **@EnableBinding**, **Processor**, **Source**, and **Sink**, the **spring-cloud-stream-test-support** module provides **TestSupportBinder**. This test binder replaces the real binder in the test context via the corresponding auto-configuration.

For an output binding, test support records emitted messages into a **MessageCollector**. The test calls:

~~~java
BlockingQueue<Message<?>> captured =
        messageCollector.forChannel(processor.output());
~~~

And then retrieves the message:

~~~java
Message<?> received = captured.poll(5, TimeUnit.SECONDS);
assertNotNull(received);
~~~

### Parts of the API

| Code snippet | Meaning |
| --- | --- |
| **messageCollector** | Bean of type org.springframework.cloud.stream.test.binder.MessageCollector from **legacy test-support** |
| **forChannel(processor.output())** | Retrieves the queue containing messages collected from the specified **output binding channel** |
| **BlockingQueue<Message<?>>** | Thread-safe queue for tests to pull collected messages |
| **poll()** | Immediately returns a message if available; returns null if empty |
| **poll(timeout, unit)** | Waits up to timeout; returns message or null; may throw InterruptedException |
| **take()** | Waits until a message arrives; usually **discouraged** in tests because it can hang indefinitely |

**The collector holds messages for test observation, not as a production broker.** It does not fully simulate durability, acks, offset commits, rebalances, broker ordering, network partitions, or crash recovery.

### Why should tests use poll with a timeout?

Suppose a handler runs on an executor and takes 150 ms to emit a result:

~~~text
T0       Test sends input.
T0+1ms   Test calls queue.poll() immediately → null.
T0+150ms Worker puts output into collector.
~~~

The test can fail even though the flow works properly, because **poll() does not wait**. Using **poll(5, TimeUnit.SECONDS)** reduces the race by waiting a reasonable window. **The timeout is an assertion deadline**, not a deadline configuration on the message flow.

## 3. Dependencies and applicability conditions in legacy projects

Gradle example for an **older-generation Spring Cloud Stream** project:

~~~groovy
dependencies {
    // Version is managed by the Spring Cloud BOM compatible with the project.
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-support'
}
~~~

Or Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-support</artifactId>
    <scope>test</scope>
</dependency>
~~~

**Do not treat this dependency snippet as a recommendation for new Spring Cloud Stream projects.** This section explains and maintains legacy codebases. Modern Spring Cloud Stream versions use **spring-cloud-stream-test-binder** and different APIs; modern examples appear later.

Before running tests:

- Verify compatible dependencies and versions for **Spring Boot, Spring Cloud Stream, and Spring Integration**.
- Confirm the project actually uses the **legacy binding model** such as @EnableBinding and Processor.
- Confirm TestSupportBinder is active in the test context.
- Do not mix the **legacy test support binder** and the **new test binder** in the same test without a clear plan; auto-configuration may conflict with the real binder.
- Keep the dependency in **test scope**; do not pull the test binder into production runtime.

## 4. JUnit example receiving messages with MessageCollector

The example below is a **legacy pattern** based on older Spring Cloud Stream APIs, not sample code for Spring Integration 6/7 or the modern Spring Cloud Stream functional model.

~~~java
import static org.junit.Assert.*;

import java.util.Locale;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.messaging.Processor;
import org.springframework.cloud.stream.test.binder.MessageCollector;
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.test.context.junit4.SpringRunner;

@RunWith(SpringRunner.class)
@SpringBootTest(classes = LegacyCollectorTest.App.class)
public class LegacyCollectorTest {

    @Autowired
    private Processor processor;

    @Autowired
    private MessageCollector messageCollector;

    @Test
    public void receivesTheTransformedOutput() throws Exception {
        BlockingQueue<Message<?>> captured =
                messageCollector.forChannel(processor.output());

        processor.input().send(new GenericMessage<>("hello"));

        Message<?> result = captured.poll(5, TimeUnit.SECONDS);
        assertNotNull("Expected a message within 5 seconds", result);
        assertEquals("HELLO", result.getPayload());
    }

    @SpringBootApplication
    @EnableBinding(Processor.class)
    public static class App {
        @Transformer(inputChannel = Processor.INPUT,
                     outputChannel = Processor.OUTPUT)
        public String uppercase(String value) {
            return value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Points to read carefully:

1. **@EnableBinding(Processor.class)** creates input/output bindings under the legacy annotation model.
2. **@Transformer** is a Spring Integration endpoint that transforms the payload, whereas the collector is **Spring Cloud Stream test support**, not an API of @Transformer.
3. **messageCollector.forChannel(processor.output())** retrieves the queue receiving output corresponding to the defined binding channel.
4. **processor.input().send(...)** triggers processing; the test pulls the message with a finite timeout.
5. The test checks the **transformed payload**; when business logic requires correlation/headers, assert them explicitly.
6. The test binder runs in-JVM, so it **does not prove a real broker** handles ack/redelivery/persistence like production.
7. If multiple tests share a context, the queue may hold leftover messages from an earlier test. Drain the queue or isolate the context.

### Adding assertions for headers

A message with the right payload can still lose correlation:

~~~java
import org.springframework.messaging.support.MessageBuilder;

Message<String> input = MessageBuilder.withPayload("hello")
        .setHeader("requestId", "request-42")
        .setHeader("correlationId", "flow-42")
        .build();

processor.input().send(input);
Message<?> output = captured.poll(5, TimeUnit.SECONDS);
assertNotNull(output);
assertEquals("HELLO", output.getPayload());
assertEquals("request-42", output.getHeaders().get("requestId"));
~~~

This is a **fragment using the same fixture/queue in a separately organized test**. Which headers survive depends on the transformer, binder, mappers, and flow configuration; assertions must match the **actual contract**. A header stripped by an adapter cannot be recreated by the collector.

## 5. Collecting multiple messages: order, count, and unarrived data

With multiple messages sent to the same output binding:

~~~java
BlockingQueue<Message<?>> captured =
        messageCollector.forChannel(processor.output());

processor.input().send(new GenericMessage<>("a"));
processor.input().send(new GenericMessage<>("b"));
processor.input().send(new GenericMessage<>("c"));

Message<?> one = captured.poll(5, TimeUnit.SECONDS);
Message<?> two = captured.poll(5, TimeUnit.SECONDS);
Message<?> three = captured.poll(5, TimeUnit.SECONDS);

assertNotNull(one);
assertNotNull(two);
assertNotNull(three);
~~~

**Do not assume A–B–C ordering by default across all topologies.** If upstream uses a multi-threaded executor, a multi-partition broker, or a parallel router, results can arrive **C–A–B** while still being valid business-wise.

### When you need to verify no messages are lost

Collect all N messages using **N poll calls with deadlines**. Then:

- Check the **set of business IDs**, not just the count.
- Check for **no duplicate eventId** if that is part of the contract.
- Assert **order** only when the topology/protocol actually provides an ordering guarantee.
- Verify unexpected results from earlier tests or other flows did not leak into the queue.

### Absence of output is a different assertion

~~~java
Message<?> unexpected = captured.poll(300, TimeUnit.MILLISECONDS);
assertNull("Must not emit output before all parts arrive", unexpected);
~~~

This only proves **no message arrived within the 300 ms observation window**, not that a message **will never** be emitted. For aggregator timeouts, test the time-based timeout mechanism separately. For “incomplete message” test cases, usually inspect both **MessageGroupStore state** and timeout/discard events upon expiration.

## 6. For pure Spring Integration: QueueChannel is a simple collector

If the application only uses **Spring Integration Java DSL/XML**, the easiest way to stay in control is to designate a **QueueChannel** as the test flow's dedicated output:

~~~mermaid
flowchart LR
    J["JUnit 5 test"] --> I["input<br/>DirectChannel"]
    I --> T["Transformer"]
    T --> Q["results<br/>QueueChannel"]
    Q --> A["results.receive(timeout)<br/>Assertions"]
~~~

**QueueChannel** implements **PollableChannel**, providing **receive(timeoutMillis)**. It is a real Spring Integration channel and needs no legacy MessageCollector.

### Spring Integration Java DSL configuration

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class UppercaseFlowConfig {

    @Bean
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel results() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow uppercaseFlow() {
        return IntegrationFlow.from("input")
                .<String, String>transform(
                        value -> value.toUpperCase(Locale.ROOT))
                .channel("results")
                .get();
    }
}
~~~

**Explanation:** In this example, results is an **output endpoint** designed for testing. A production system that needs to forward messages to another consumer should not **arbitrarily replace production channels** just to test, as doing so changes topology. Use a test-only configuration or an appropriate WireTap if you need to observe a channel that already has a consumer.

### JUnit 5 reading messages directly from the output

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = UppercaseFlowConfig.class)
class UppercaseFlowTest {

    @Autowired
    @Qualifier("input")
    MessageChannel input;

    @Autowired
    @Qualifier("results")
    QueueChannel results;

    @Test
    void collectsAResponse() {
        Message<String> request =
                MessageBuilder.withPayload("hello")
                        .setHeader("requestId", "R-42")
                        .build();

        assertTrue(input.send(request));

        Message<?> received = results.receive(2_000);
        assertNotNull(received);
        assertEquals("HELLO", received.getPayload());
        assertEquals("R-42", received.getHeaders().get("requestId"));
        assertNull(results.receive(0), "No extra message expected");
    }
}
~~~

Advantages of this test:

- **No broker** and no Spring Cloud Stream needed.
- Creates/starts a **real IntegrationFlow**, rather than calling a transformer method in isolation.
- **receive(2_000)** avoids races when tests introduce async processing.
- Can inspect the full message, including headers.
- Interacts only with a **clearly named test channel**, minimizing side effects on other subscribers.

Limitation: This is an **in-JVM** test with an in-memory QueueChannel. It does not verify **transaction rollback, broker ack, Kafka partition ordering, Redis/JDBC MessageStore durability, or restart**.

### How does QueueChannel.receive(...) differ from BlockingQueue.poll(...)?

| Legacy MessageCollector | Pure Spring Integration QueueChannel |
| --- | --- |
| collector.forChannel(outputBinding) | autowired test output QueueChannel bean |
| BlockingQueue<Message<?>> | PollableChannel/QueueChannel |
| queue.poll(5, TimeUnit.SECONDS) | results.receive(5_000) |
| Queue holds messages captured by legacy TestSupportBinder | Channel directly holds messages inside the flow |
| Triggered via Processor.input() | Triggered via MessageChannel.send() |
| Belongs to legacy Spring Cloud Stream test-support | Belongs to Spring Integration core |

Note that **receive() consumes the message**. A successful receive removes the message from the QueueChannel; if two tests receive from the same channel, they can compete for messages. Do not use the same QueueChannel both as a business queue and as a test observer if doing so alters real execution flow.

## 7. Testing outputs that already have a consumer: why use WireTap?

Output is not always a QueueChannel from which tests are allowed to pull messages. For example:

~~~text
Input
  → Handler A
  → DirectChannel businessOutput
  → Handler B (writes to DB)
~~~

If a test subscribes an extra **MessageHandler** to **DirectChannel businessOutput** expecting **both the test and Handler B to receive every message**, that can be a mistake. A standard DirectChannel uses a dispatcher to **pick one subscriber per send** (potentially load-balancing); it **does not broadcast** to all subscribers by default.

### Using WireTap to capture a copy at a defined point

~~~mermaid
flowchart LR
    A["Producer"] --> D["businessOutput<br/>DirectChannel"]
    D --> B["Business handler"]
    D -. "WireTap copy" .-> Q["captured<br/>QueueChannel"]
    Q --> T["Test assertions"]
~~~

**WireTap** observes messages passing through a channel without turning the collector into a competing business subscriber on a DirectChannel. This is useful when you want to test an **internal point in the flow** before the final handler produces side effects.

An illustrative example in Java DSL:

~~~java
@Bean
QueueChannel captured() {
    return new QueueChannel();
}

@Bean
IntegrationFlow observedFlow() {
    return IntegrationFlow.from("input")
            .<String, String>transform(String::toUpperCase)
            .wireTap("captured")
            .channel("businessOutput")
            .get();
}
~~~

This snippet is a **configuration fragment**; input, businessOutput, and related beans must exist in the context. In the test, call **captured.receive(timeout)** to observe the copy; **businessOutput** continues delivering to its business consumer.

### WireTap boundaries to remember

- WireTap observes messages at the **point where it is attached**; it does not automatically collect messages from every channel.
- The copy is typically the **same Message or a new Message carrying matching payload/headers** per the framework implementation; if the payload is a **mutable object**, a consumer mutating the object afterward can make assertions flaky. Prefer immutable payloads or controlled snapshots.
- If the tap sends to an unavailable channel, check error/capacity handling so it does not unintentionally disrupt tests or production flows.
- A WireTap added in test configuration should be removed after tests or exist only in a test profile; do not leave a capture queue growing unbounded in production.
- If downstream emits additional outputs after the tap, a collector at the tap **does not represent the final result**.

With **PublishSubscribeChannel**, subscribers can receive broadcasts per its mechanism, provided you understand its error handling, threading, and existing subscribers. Do not replace DirectChannel with PublishSubscribeChannel in production solely for testing if that alters processing semantics.

## 8. Modern Spring Cloud Stream: OutputDestination instead of MessageCollector

If the project uses the **Spring Cloud Stream functional model**, use the modern test binder:

~~~groovy
dependencies {
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
~~~

Commonly used classes come from package:

~~~java
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
~~~

Minimal application example with a function:

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(TestChannelBinderConfiguration.class)
class StreamFunctionApp {

    @Bean
    Function<String, String> uppercase() {
        return input -> input.toUpperCase(Locale.ROOT);
    }
}
~~~

JUnit 5 using the test binder:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(classes = StreamFunctionApp.class)
class StreamBinderOutputTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void readsOutboundMessageFromTestBinder() {
        input.send(new GenericMessage<>(
                "hello".getBytes(StandardCharsets.UTF_8)),
                "uppercase-in-0");

        Message<byte[]> received =
                output.receive(5_000, "uppercase-out-0");

        assertNotNull(received);
        assertEquals("HELLO", new String(
                received.getPayload(), StandardCharsets.UTF_8));
    }
}
~~~

**Version note:** Some generations of Spring Cloud Stream use **@Import(TestChannelBinderConfiguration.class)** as shown here; newer documentation also uses **@EnableTestBinder**. Pick **one approach compatible with your current version and BOM**, rather than copying both arbitrarily or mixing with legacy **spring-cloud-stream-test-support**.

### Key differences when migrating from collector to OutputDestination

~~~text
Legacy:
  MessageCollector.forChannel(channels.output())
  → BlockingQueue<Message<?>>

Modern:
  OutputDestination.receive(timeout, "uppercase-out-0")
  → Message<byte[]> or null
~~~

- **MessageCollector** targets the **output channel of a legacy binding** directly.
- **OutputDestination** receives by **binding/destination** of the new test binder, usually named **functionName-out-0** or an explicitly configured name.
- OutputDestination payloads may be **byte[] after conversion**, so decode using the appropriate **content type/encoding**.
- If there are multiple output destinations, pass the exact destination/binding name; do not assume only a single output queue exists.
- The new test binder is still an **in-JVM test binder** and does not prove Kafka/Rabbit-specific semantics.

### API mapping when upgrading

| Legacy Spring Cloud Stream | Functional Spring Cloud Stream |
| --- | --- |
| @EnableBinding(Processor.class) | @Bean Function/Consumer/Supplier and function definition |
| Processor.input()/output() | Function binding/destination |
| spring-cloud-stream-test-support | spring-cloud-stream-test-binder |
| MessageCollector.forChannel(...) | OutputDestination.receive(...) |
| TestSupportBinder | Spring Integration-based test binder |
| @RunWith(SpringRunner.class), JUnit 4 common | JUnit 5, @SpringBootTest common |

**It is not just an import change.** The binding model, function names, content-type conversion, and how the test binder simulates transport all differ. After migrating, verify headers, serialization, and destination mapping instead of asserting only a String payload.

## 9. Testing headers, correlation, and batch messages

A message consists of **payload + headers**. Testing a flow solely on payload can miss serious runtime bugs:

- Lost **correlationId** after a transformer/gateway.
- Lost **requestId** or **idempotencyKey**, causing retries/redeliveries to produce duplicate side effects.
- Lost **sequenceNumber/sequenceSize** from a splitter, preventing an aggregator from releasing.
- Wrong content type, causing downstream converters to decode incorrectly.
- A new header holding a non-serializable object in a persistent MessageStore.

General assertion example:

~~~java
Message<?> captured = results.receive(5_000);
assertNotNull(captured);

assertEquals("O-42", captured.getHeaders().get("orderId"));
assertEquals("batch-7", captured.getHeaders().get("correlationId"));
assertEquals("ev-1001", captured.getHeaders().get("eventId"));
~~~

**This example is a fragment**, valid only if the flow is configured to propagate those headers. Do not assume every business variable is automatically generated by Spring Integration.

### When multiple messages arrive out of order

Suppose three branches emit PaymentResult, InventoryResult, and AddressResult. With an ExecutorChannel, arrival order can vary:

~~~text
Input sequence:  PAYMENT → INVENTORY → ADDRESS
Output observed: ADDRESS → PAYMENT → INVENTORY
~~~

If the contract only requires all three result types, the test should:

1. Pull all **3 messages** via polls with timeouts.
2. Map payloads into a set/map keyed by business key.
3. Verify each type appears once, with the same orderId/runId.
4. Avoid asserting by fixed index position.

If the contract requires strict ordering, you need a **resequencer/sequence strategy** or an appropriate transport guarantee; assertions must state that condition explicitly. A test queue records one observed order, which does not by itself prove the source guarantees ordering in a cluster.

## 10. Capturing ErrorMessage: errorChannel differs from outputChannel

A flow may emit no normal output if a handler throws an exception:

~~~mermaid
flowchart LR
    I["Input"] --> H["ServiceActivator"]
    H -- "Success" --> O["outputChannel"]
    H -. "Failure" .-> E["errorChannel"]
    E --> R["Error handler / test collector"]
~~~

**Spring Integration has ErrorMessage**, whose payload is a Throwable; a MessagingException can hold failedMessage. When testing, determine whether **the error is published to errorChannel** or **propagated back to the sending thread**.

### Synchronous error through DirectChannel

If the test sends to a **DirectChannel** and a synchronous handler throws a RuntimeException, the send() call may throw the exception on the **test thread**:

~~~java
assertThrows(RuntimeException.class,
        () -> input.send(badMessage));
~~~

This is a test fragment; the exact exception type may be wrapped by Spring Integration into MessagingException. Do not assume an ErrorMessage appears on the global errorChannel unless the endpoint publishes errors via that mechanism.

### Error in ExecutorChannel or polling consumer

When an error occurs on a worker/poller thread, the original sender may have already completed send(). If an error flow is configured, the test can route ErrorMessage to a test-dedicated QueueChannel:

~~~java
@Bean
QueueChannel testErrors() {
    return new QueueChannel();
}
~~~

You must **wire the endpoint error handler/route** so ErrorMessage actually arrives on channel testErrors. Then:

~~~java
Message<?> error = testErrors.receive(5_000);
assertNotNull(error);
assertTrue(error instanceof
        org.springframework.messaging.support.ErrorMessage);

Throwable failure =
        ((org.springframework.messaging.support.ErrorMessage) error)
                .getPayload();
assertNotNull(failure);
~~~

Merely declaring a QueueChannel does not route every application exception into it. If a RetryAdvice recovery callback catches the error and returns a normal result, the error path may also differ from expectations.

**Correlation on the error path:** When an ErrorMessage is created, check originalMessage or MessagingException.failedMessage if present. Do not assume ErrorMessage headers always contain the original message's requestId/eventId; errors occurring before the MessageSource receives a message can also lack failedMessage.

## 11. Controlling the poller so MessageCollector receives the right messages

An uncontrolled poller can run **before the test begins**, emit more messages than expected, or fail to poll before the test reads the output.

~~~text
TaskScheduler
  → Poller
      → MessageSource.receive()
      → Channel
      → Handler
      → Output collector
~~~

The Spring Integration Test Framework provides supporting tools:

- **@SpringIntegrationTest(noAutoStartup = {...})**: prevents endpoints matching bean/endpoint name patterns from auto-starting.
- **MockIntegrationContext**: replaces a MessageSource or MessageHandler in the endpoint under test, then resets after each test.
- **MockIntegration.mockMessageSource(...)**: creates a message source with fixed data.
- **MockMessageHandler** and Mockito ArgumentCaptor: inspect messages delivered to a handler instead of running real side effects.
- **OnlyOnceTrigger**: supports tests that need exactly one poll.

These are utilities of **spring-integration-test**, **not** legacy MessageCollector. They work well with a test QueueChannel, though they require exact endpoint IDs and proper test context configuration.

### Testing a mock source: skeleton example

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.integration.test.mock.MockIntegration.mockMessageSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.Message;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = PollingTestConfig.class)
@SpringIntegrationTest(noAutoStartup = "ordersSourceEndpoint")
class SourcePollingTest {

    @Autowired
    MockIntegrationContext mocks;

    @Autowired
    QueueChannel results;

    @AfterEach
    void resetMocks() {
        mocks.resetBeans();
    }

    @Test
    void receivesDataFromControlledSource() {
        mocks.substituteMessageSourceFor(
                "ordersSourceEndpoint",
                mockMessageSource("O-42"));

        // Trigger/start ordersSourceEndpoint via an appropriate test fixture.
        // After the poller actually runs:
        Message<?> received = results.receive(5_000);
        assertNotNull(received);
    }
}
~~~

**This is an illustrative skeleton**, not a standalone runnable test class: you need to define PollingTestConfig, an endpoint with ID ordersSourceEndpoint, explicitly start/trigger the poller, and wire the output. Replacing the MessageSource **does not automatically trigger the poller**.

### Waiting on signals

Avoid:

~~~java
Thread.sleep(2_000);
assertNotNull(results.receive(0));
~~~

Prefer:

~~~java
Message<?> received = results.receive(5_000);
assertNotNull(received);
~~~

Or use CountDownLatch/Awaitility with a deadline. When you need exactly one poll cycle, use a controllable trigger/test scheduler rather than relying on CI machine timing.

## 12. Retries and duplicates: which messages does the collector count?

One source message can generate multiple **deliveries** and multiple **handler attempts**:

~~~text
delivery #1:
    handler attempt #1 → exception
    handler attempt #2 → success
    output #1

Crash before broker ACK.

delivery #2:
    handler attempt #1 → success / duplicate suppressed
    output #2 without idempotency
~~~

**MessageCollector counts messages at the observation point**; it does not know how many business operations they represent. Distinguish:

| Unit | Where to test? |
| --- | --- |
| Broker delivery | Adapter/broker instrumentation or real broker test |
| Handler attempt | Mock/spy handler or metrics on handler/advice |
| Output message | MessageCollector, QueueChannel, or OutputDestination |
| Business side effect | DB/inbox/outbox/provider state, idempotency key |

If RetryAdvice retries a handler 3 times and then succeeds, the output collector may receive only **one success message**. Yet if a retry occurs after a side effect already committed, duplicates can happen on re-execution. **Never infer exactly-once just because the collector saw one output.**

### Testing two deliveries with the same eventId

~~~java
Message<String> first =
        MessageBuilder.withPayload("PAYMENT_ACCEPTED")
                .setHeader("eventId", "EV-42")
                .build();

Message<String> redelivered =
        MessageBuilder.withPayload("PAYMENT_ACCEPTED")
                .setHeader("eventId", "EV-42")
                .build();

input.send(first);
input.send(redelivered);
~~~

Two Spring Messages can have different MessageHeaders.ID values yet share the **same business eventId**. If the flow has an idempotent receiver/filter, test output count per contract; if the flow emits output for both deliveries, verify **downstream consumers/DB** still apply only one business effect.

**Do not rely on correlationId alone to conclude a message is a duplicate:** a workflow often has multiple valid messages sharing the same correlationId.

## 13. Test isolation: why do messages from an earlier test appear?

Spring Test may **cache the ApplicationContext**, and the collector/test channel queue may still contain unconsumed messages.

~~~text
Test A:
  Input A → output A
  Queue still holds A when test ends.

Test B:
  Input B → output B
  poll() gets A first → assert expected B fails.
~~~

There is not necessarily a bug in the business flow; the issue is **unisolated fixtures**.

### Options to handle this

1. Use **independent ApplicationContexts** or **separate test configurations** for test groups needing isolated state.
2. For queues used solely for test observation, **drain/reset in a controlled manner** when no producer is in-flight.
3. Generate distinct **groupKey/testRunId** values to identify each scenario's results; still investigate unexpected messages.
4. Avoid running tests in parallel if they share **one output queue**, unless message demultiplexing by testRunId is designed in.
5. With MockIntegrationContext, call **resetBeans()** after the test; prevent an endpoint from one test from still using a mock source in another.
6. Use **@DirtiesContext** when state is too complex to reset, accepting the cost of recreating the ApplicationContext.

**Be careful with clear():** Clearing a queue while a worker/poller is still running can mask “late message” bugs or drop outputs belonging to the test under verification. It is better to control the endpoint lifecycle, wait for in-flight tasks to finish, and then reset.

### Testing multiple messages as a set instead of by order

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.messaging.Message;

List<Message<?>> collected = new ArrayList<>();
for (int i = 0; i < 3; i++) {
    Message<?> item = results.receive(5_000);
    assertNotNull(item, "Missing output " + i);
    collected.add(item);
}

Set<Object> eventIds = new HashSet<>();
for (Message<?> item : collected) {
    eventIds.add(item.getHeaders().get("eventId"));
}

assertEquals(Set.of("EV-1", "EV-2", "EV-3"), eventIds);
assertEquals(3, collected.size());
assertNull(results.receive(0), "Unexpected fourth output");
~~~

This is a fragment inside a test that already has results/input and a flow producing three outputs. **Set assertions** fit when all three eventIds are required and order does not matter. To be sure there are no duplicate eventIds, verify all eventIds are non-null and the set size equals the message count.

### Asserting “no message emitted” requires an observation deadline

~~~java
Message<?> unexpected = results.receive(250);
assertNull(unexpected);
~~~

This only confirms output **did not appear during the 250 ms observation window**. To prove an aggregator does not release early when fragments are missing, inspect **MessageGroupStore** to confirm it remains incomplete and the release strategy is not met, then supply the final fragment and await the expected output. If there is a group timeout, test the expiry branch as well.

## 14. Choosing the right collector tool for the goal

| Testing goal | Recommended tool | Limitations |
| --- | --- | --- |
| Maintaining **legacy Spring Cloud Stream** code using @EnableBinding | **MessageCollector.forChannel(...)** | Legacy API and old test binder; unsuitable as default for new projects |
| Testing modern Spring Cloud Stream functional bindings | **InputDestination/OutputDestination** | Does not fully simulate Kafka/Rabbit semantics |
| Pure Spring Integration flow ending at a test output | **QueueChannel.receive(timeout)** | Requires explicit wiring; receive consumes the message |
| Observing messages on a channel that already has a business consumer | **WireTap → test QueueChannel** | Snapshot at tap point; must avoid instrumentation side effects |
| Verifying whether a handler was called and what message it received | **MockMessageHandler/ArgumentCaptor** | May replace handler logic; does not test real side effects |
| Controlling polling sources / endpoint lifecycle | **@SpringIntegrationTest + MockIntegrationContext** | Requires exact endpoint IDs; still must trigger/start the poller |
| Checking exceptions on worker/poller | **errorChannel route → test QueueChannel** | Must wire error flow; synchronous exceptions may propagate back instead of publishing |
| Verifying real broker ack, redelivery, and restart | **Integration tests with real broker/store** | Slower; requires infrastructure/fault injection |

### Assurance ladder across test types

~~~mermaid
flowchart TD
    U["Unit test transformer / release strategy"] --> C["In-JVM IntegrationFlow + QueueChannel"]
    C --> S["Spring Cloud Stream test binder"]
    S --> I["Test with real DB / message store / broker"]
    I --> F["Crash, restart, redelivery, multiple instances"]
~~~

The diagram illustrates **complementary verification scopes**, not an absolute hierarchy of value: the test binder fits Spring Cloud Stream projects, while QueueChannel fits pure Spring Integration; both approaches can run **in parallel** rather than strictly sequentially.

## 15. Limitations to state clearly when reporting test results

**In-JVM collector tests verify a message reached an observation point**, and do not by themselves verify:

- **Broker durability:** whether an event was actually persisted/acked by the broker.
- **Offset/ack/redelivery:** how a broker redelivers a message after a crash.
- **Cross-process ordering:** whether messages across partitions/consumers in a cluster preserve order.
- **Transaction atomicity:** whether DB operations, MessageStore, and external HTTP calls commit together.
- **Side-effect exactly-once:** whether a payment/email/order effect occurs only once across retries and restarts.
- **Serialization compatibility:** whether payloads/headers survive a persistent store and new-version deployments.
- **Default error channel:** whether error messages route properly across the entire production topology.
- **Backpressure/capacity:** an in-memory test queue may not reproduce real broker limits/bottlenecks.

Therefore, an assertion like:

~~~text
Collector received exactly one OrderCreated message.
~~~

is evidence only at that test point, not proof that the entire system achieves **exactly-once**.

### Combining with durable side-effect checks

When output leads to a DB/outbox:

1. Measure business output on the collector/QueueChannel if applicable.
2. Verify committed **DB rows, unique business keys, and outbox events**.
3. Resend the same eventId with a different Spring Message ID.
4. Verify no duplicate DB effect/outbox logical event was created.
5. If testing crash/restart, kill the process between **side-effect commit and ack**, restart with the same store/broker, and verify recovery.

Collectors help verify *message flow*, while DB/provider/broker assertions verify *business semantics*.

## 16. A test plan for a runtime flow with poller and executor

**Scenario:** The application reads order files via a poller, sends them to a durable QueueChannel, processes them on an executor, calls the DB, then emits OrderAccepted or routes errors to recovery. Occasionally messages arrive out of order and redeliveries occur.

A test suite can be designed as follows:

| Case | Arrange / Act | What to assert |
| --- | --- | --- |
| 1 | One valid order | Collector receives exact OrderAccepted, correct payload/headers |
| 2 | Two distinct orders | Both results collected; no correlation mix-up |
| 3 | Async handler blocked by a latch | Timed poll waits; never assert send() equals completion |
| 4 | Order payload missing required field | No success output; error enters expected error path/exception |
| 5 | MessageSource returns no message in a poll cycle | No output; poller continues running on trigger |
| 6 | Poller may run multiple cycles | Only exact outputs for valid sources are collected |
| 7 | RetryAdvice fails twice then succeeds | One business success output; attempt count verified via spy/metric |
| 8 | Redelivery with same eventId | No duplicate business side effects created |
| 9 | Three messages in arbitrary order | Assert set of business IDs; do not assume order under parallel executor |
| 10 | Incomplete MessageGroup | Does not release early; test timeout/expiry separately |
| 11 | Stop poller | No new receives after stop completes per contract |
| 12 | Start poller | Subsequent valid messages are processed |
| 13 | Persistent store restart | Committed state survives restart; recovery result is correct |
| 14 | Real broker test and crash before ack | Redelivery from source is right; business idempotency holds |

### What a reliable fixture should have

- **Controlled input:** mock MessageSource, in-memory channel, or test binder, matching topology.
- **Explicit endpoint IDs:** convenient for MockIntegrationContext and lifecycle control.
- **Dedicated output channel/collector:** with clear consume/reset rules between tests.
- **Dedicated error collector:** errorChannel is genuinely wired to the observation point.
- **Finite deadlines:** timed polls and bounded awaits; no infinite hangs.
- **Test-run correlation:** stable testRunId within a case, distinct across cases.
- **No orphan tasks:** stop polling/executors and close contexts/connections properly after tests.
- **Isolated external effects:** test DB, fake HTTP server, or test container; never call production services.

### Diagnostic runbook when a collector times out

~~~text
1. Did the test actually manage to send the input?
2. Has the endpoint subscribed/started?
3. Is the poller blocked by noAutoStartup, or has the trigger not run yet?
4. Did the message enter the right channel and pass through the right router/filter?
5. Is the handler blocked in the executor, DB, or HTTP?
6. Was an exception published to errorChannel?
7. Did retry/recovery consume the exception and alter the output?
8. Is the output going to the exact channel/binding/destination the collector listens to?
9. Is another test consuming messages from the collector queue?
10. Did the test use non-waiting poll() or too short a timeout?
~~~

Do not fix this by extending timeouts indefinitely when the real cause is a wrong binding name or a stopped endpoint. Trace the message path first, then pick an appropriate wait duration.

## 17. Self-check questions

**1. Is legacy Spring Cloud Stream's MessageCollector included in spring-integration-test?**

**No.** The MessageCollector.forChannel(...) API comes from legacy **spring-cloud-stream-test-support**. In pure Spring Integration, use QueueChannel, WireTap, mock handlers, and spring-integration-test utilities.

**2. Why does queue.poll() return null even when the flow has no errors?**

**Because** poll() does not wait, while the handler/poller may execute asynchronously. Use poll(timeout, unit), check endpoints, and bound test waits.

**3. Can you add a test subscriber to a DirectChannel so every message goes to both the business consumer and the test?**

**Not by default.** DirectChannel is not a broadcast channel. Use WireTap or an intentionally designed PublishSubscribeChannel structure.

**4. Why does OutputDestination often return byte[] instead of String?**

**Because** the test binder observes messages at the binding boundary, which may have undergone content-type conversion. Decode according to encoding/content type and test against byte[] or objects per the actual contract.

**5. Does receiving exactly one message in the collector prove exactly-once across crash/restart?**

**No.** It only proves behavior at one point in a single in-JVM run. You must test durable storage, broker redelivery, and idempotent business effects.

**6. A test tries to receive errors from errorChannel using a QueueChannel, yet a DirectChannel handler throws the error directly to the test. Where is the test wrong?**

**Likely** the test assumed the wrong error delivery boundary. Synchronous errors can propagate back to the sending thread; an error flow only engages when the endpoint/adapter is configured to publish errors appropriately.

**7. Should tests with multiple outputs via ExecutorChannel assert the exact same order as sent?**

**Only when** the topology guarantees ordering and the test is verifying that exact contract. Otherwise, compare the set of messages by business key.

## 18. Checklist before adding tests to CI

- Identified whether the project is **pure Spring Integration**, **legacy Spring Cloud Stream**, or **functional Spring Cloud Stream**?
- If using MessageCollector, is the legacy dependency intentional and does forChannel(...) match the version?
- If using the new test binder, do InputDestination/OutputDestination use the right binding/destination names?
- If using QueueChannel, is it a dedicated test channel that does not inadvertently alter business consumers?
- If observing a DirectChannel with a business consumer, is WireTap or an appropriate mechanism used?
- Using timed poll/receive rather than unbounded blocking take()?
- Asserting **payload, headers, correlation, and count**, not just non-null messages?
- With executors, not treating send() returning true as downstream completion?
- With out-of-order messages, asserting order only when an ordering guarantee exists?
- Properly testing **no output before release**, timeouts, and late arrivals?
- Observing errorChannel/exceptions at the right thread boundary and endpoint?
- With retries, distinguishing **handler attempts** from **output messages/business operations**?
- Preventing cross-test queue pollution without clearing messages while workers are still in-flight?
- Controlling poller trigger/start/stop and properly resetting/closing the test context?
- Using finite timeouts and helpful diagnostics when output does not arrive?
- Adding real broker/persistent store tests when ack, redelivery, transactions, and restarts are required?

## Conclusion

**MessageCollector** in legacy Spring Cloud Stream test-support is a simple utility for **receiving messages from outbound bindings via a BlockingQueue**. The typical syntax is **collector.forChannel(channel).poll(timeout, unit)**, followed by payload and header assertions. The most important point is **waiting at the right boundary and observing the right output**, rather than merely checking that input.send() succeeded.

In **modern Spring Integration Runtime**, pure Spring Integration flows are usually tested with **QueueChannel, WireTap, MockMessageHandler, or MockIntegrationContext**; if the application uses the **Spring Cloud Stream functional model**, use **InputDestination/OutputDestination** from the new test binder. Picking the right API for your dependencies and version is the first step to avoiding confusing errors.

Finally, a collector only proves **a message reached an observation point in the test**. It does not by itself prove transactions, error recovery, broker acknowledgment, exactly-once delivery, or persistence across restarts. Combine output assertions with **correlation, retries, message stores, real side effects, and end-to-end tests** when high reliability is required.

## References

- [Spring Cloud Stream — Testing with legacy TestSupportBinder and MessageCollector](https://cloud.spring.io/spring-cloud-stream/single/spring-cloud-stream.html)
- [Spring Cloud Stream — Testing with the modern Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Test binder and OutputDestination](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream.html)
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)

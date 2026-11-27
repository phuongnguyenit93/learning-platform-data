# MessageCollector and Output Verification in Spring Integration Adapters

## 1. Why Collect Output When Testing Adapters?

A **Spring Integration** flow typically connects external systems to internal processing via **inbound adapters**, **outbound adapters**, **gateways**, **pollers**, and **MessageChannels**. When receiving files, fetching data over SFTP, reading database records, or consuming messages from JMS/AMQP/Kafka, the key question is not just *"did the code run?"* but rather: **which messages went out, where did they go, what did they contain, and did they actually produce the expected outcome in the target system?**

In the **Testing** chapter of the **Spring Integration Adapters** module, **MessageCollector and output verification** introduces how to capture messages at flow boundaries and write reliable assertions for:

- **Payload:** data type, content, encoding, schema, and transformations.
- **Headers:** correlation ID, filename, routing key, content type, transport metadata.
- **Count and ordering:** single or multiple messages, routing branches, duplicate handling.
- **Timing:** synchronous output, output arriving after a poller or asynchronous consumer.
- **Error paths:** errors routed to an error flow, retries, dead-letter queue, or returned to a gateway.
- **External side effects:** file created, HTTP request reached server, message published, database record written.
- **Lifecycle:** adapter start/stop/restart, backlog, sessions, connections, and post-test cleanup.

This lesson uses Java, JUnit 5, Spring Test, and relevant testing tools. Code examples target modern Spring Integration; **legacy Spring Cloud Stream** examples are explicitly labeled because they should not be used as default APIs in new projects.

**Core principle:** *a message appearing in a collector* proves only that the message reached the **collection point**. It **does not prove on its own** that the outbound adapter completed I/O or that the receiving system finished business processing.

## 2. Distinguishing Three Concepts Often Lumped Together as "MessageCollector"

The name `MessageCollector` easily causes confusion because **Spring Integration** and **Spring Cloud Stream** both use `Message<?>` and channels yet have different test models.

| Context | Tool | Primary Meaning | Recommendation |
|---|---|---|---|
| **Plain Spring Integration** | `QueueChannel`, `PollableChannel`, `MessageHandler`, `MockIntegrationContext`, `WireTap` | Collect messages at channels/endpoints inside a flow | Appropriate approach when the module uses Java DSL, adapters, and gateways directly |
| **Legacy Spring Cloud Stream test support** | `org.springframework.cloud.stream.test.binder.MessageCollector` | Test binder captures messages from outbound bindings for tests to poll via `forChannel(...)` | **Legacy**; use only to understand or maintain compatible older codebases |
| **Modern Spring Cloud Stream test binder** | `InputDestination`, `OutputDestination` | Emulates input/output bindings inside the JVM without an external broker | Use for Spring Cloud Stream apps on compatible versions |

**Key point:** Do not add `spring-cloud-stream-test-support` to a plain Spring Integration project just to get the class name `MessageCollector`. That legacy API belongs to **Spring Cloud Stream**, not the default output collection mechanism of `spring-integration-test`.

Spring Cloud Stream builds on Spring Integration at the messaging layer, so some docs mention "Spring Integration test binder"; that **does not mean** the legacy `MessageCollector` class is part of core Spring Integration.

### 2.1. Which Approach to Pick in Practice?

- Using **`IntegrationFlow` + `MessageChannel`** directly: use `QueueChannel` or a dedicated terminal handler in the Spring Integration test context.
- Need to **replace an outbound endpoint** to isolate connectivity: use `MockIntegrationContext` and a mock/spy handler with an explicit endpoint ID.
- Need to **observe mid-flow without stealing messages from consumers**: use a wire tap or a dedicated observation channel.
- Maintaining a **legacy Spring Cloud Stream** app with `@EnableBinding`: understand `MessageCollector`, while planning migration to the test binder.
- Writing a **Spring Cloud Stream app with function bindings**: use `InputDestination`/`OutputDestination`.
- Need to prove **Kafka/RabbitMQ/SFTP/HTTP really works**: use appropriate test infrastructure and assert at the **target**, not just an in-memory collector.

## 3. Where Does the Collector Sit in the Test Architecture?

~~~mermaid
flowchart LR
    E["External source: file/SFTP/HTTP/broker/DB"] --> IN["Inbound adapter/gateway"]
    IN --> C1["inputChannel"]
    C1 --> F["Filter/Transform/Route/Handle"]
    F --> C2["outputChannel"]
    C2 --> OUT["Outbound adapter/gateway"]
    OUT --> T["External target"]

    C1 -. "observe if needed" .-> O1["Test observer"]
    F -. "test terminal output" .-> COL["QueueChannel / collector"]
    T -. "assert side effect" .-> CHECK["Test verification"]
    F -. "failure" .-> ERR["errorChannel / retry / DLQ"]
~~~

We have at least three output measurement points:

1. **Before the outbound adapter:** inspect the message the adapter is about to receive, such as a JSON DTO, routing key, or filename header.
2. **After a reply-producing gateway:** inspect the response message, status, or result object.
3. **At the target system:** verify side effects such as files, broker records, HTTP requests, or database rows.

A test at point (1) cannot replace a test at point (3). Choose the right point for the business question being asked.

## 4. Writing the Output Contract Before Assertions

Example flow receiving an order from a file:

~~~text
Input:
  file orders-42.csv
  body: "orderId,total\n42,100\n"
  header: sourceSystem=sftp
  header: correlationId=corr-42

Expected internal output:
  payload: OrderEvent(orderId=42, total=100)
  header: eventId=order-42
  header: correlationId=corr-42

Expected external output:
  HTTP POST /orders with orderId=42
  HTTP 201 and externalId=ext-42

Failure behavior:
  Invalid CSV schema -> rejectedOrders
  HTTP 503 -> bounded retry
  HTTP 400 -> business error, no blind retry
~~~

From the contract, clarify:

| Attribute | What to Assert | Pitfall |
|---|---|---|
| `payload.getClass()` | Exact Java type after transformer | Data is `byte[]` while test compares against `String` |
| Content | Normalization, schema, amounts, encoding | Comparing raw JSON strings even when field order is irrelevant |
| Correlation | Preserve business ID across flow | Confusing framework-generated `MessageHeaders.ID` with business ID |
| Transport metadata | Filename, remote path, Kafka key, HTTP status | Asserting headers never configured to propagate |
| Count | Exactly N messages on the right branch | Taking only the first message and ignoring extra messages |
| Ordering | Within what scope is it guaranteed? | Claiming global order across multiple threads/partitions |
| Errors | Are errors handled at caller, error flow, or broker? | Assuming every exception automatically goes to `errorChannel` |
| Target outcome | Side effect completed vs. merely queued/acked? | Treating `send() == true` as business success |

If content includes dynamic timestamps or UUIDs, fix the clock/ID in tests or assert format and business relationships instead of uncontrolled values in snapshot assertions.

## 5. Understanding Channel Semantics Before Collecting Messages

Different channel types carry different semantics:

| Channel | Characteristics | How to Test Output |
|---|---|---|
| `DirectChannel` | Synchronous dispatch to one selected subscriber; exceptions may return to caller | Attach terminal handler/flow and assert outcome; not fan-out |
| `QueueChannel` | `PollableChannel`, buffers messages for `receive(timeout)` | Simple output collection point in tests |
| `PublishSubscribeChannel` | Broadcasts to subscribers; may hand off to an executor | Collector is a separate subscriber; must handle cleanup |
| `ExecutorChannel` | Consumer may run asynchronously | Wait for messages with timeout; never assert immediately |
| `RendezvousChannel` | Synchronous pairing of sender and receiver | Test send/receive timeouts |
| `PriorityChannel` | Orders based on priority | Assert ordering per actually configured priority |
| Broker-backed channel | Has acks, transactions, redelivery, partitions/consumer groups | Integration test with appropriate transport |

**Never register a collector as a second subscriber on a production `DirectChannel` expecting it to receive a copy of messages.** `DirectChannel` selects one subscriber; the observer becomes a **competing consumer**, breaking tests or altering real behavior. When duplicating for observation, use a properly configured `WireTap`/`PublishSubscribeChannel` or a dedicated test terminal output.

### 5.1. Timeouts and Receivers

`PollableChannel.receive(timeoutMillis)` waits up to the supplied duration. On a `QueueChannel`, `receive(0)` does not wait; `receive(1000)` waits boundedly; **avoid `receive()` without a timeout in tests** because it can hang indefinitely when a flow fails.

A `receive(0) == null` call proves only that **at that instant** the queue is empty; it does not prove a message won't arrive later. To assert "no output ever arrives" within bounds, use an observation window, count messages, and ensure the flow has finished/stabilized.

## 6. MessageCollector in Legacy Spring Cloud Stream Test Support

In some projects using Spring Cloud Stream's annotation model, the legacy test binder provides `MessageCollector` and this API:

~~~java
// For legacy Spring Cloud Stream versions with test-support:
@Autowired
private org.springframework.cloud.stream.test.binder.MessageCollector collector;

@Autowired
private org.springframework.cloud.stream.messaging.Processor processor;

@Test
void collectsLegacyOutput() throws InterruptedException {
    processor.input().send(new GenericMessage<>("hello"));

    Message<?> result = collector
            .forChannel(processor.output())
            .poll(2, TimeUnit.SECONDS);

    assertNotNull(result);
    assertEquals("HELLO", result.getPayload());
}
~~~

The snippet above shows the **test body**. Running it in a legacy project requires `@EnableBinding(Processor.class)`, an input→output processing flow, and the matching test binder dependency such as `spring-cloud-stream-test-support`. Other imports include `Message`, `GenericMessage`, `TimeUnit`, `@Autowired`, and `@Test`.

Conceptually, `forChannel(channel)` returns a queue holding messages emitted to an **outbound binding** managed by the test binder. It **does not automatically observe arbitrary `MessageChannel`s** in a Spring Integration application.

**Version warning:** the `@EnableBinding`/`@StreamListener` model and the legacy test binder with `MessageCollector` have been superseded in modern Spring Cloud Stream. Do not copy legacy snippets into a new Spring Integration Java DSL app and wonder why `MessageCollector` is missing from the classpath.

### 6.1. What Legacy Tests Can and Cannot Prove

- **Can prove:** messages traversed the function/processor and appeared on an outbound binding managed by the test binder.
- **Can prove:** expected payloads/headers, single or multiple outputs, branches supported by the emulated binder.
- **Cannot prove from collector alone:** Kafka records were committed, RabbitMQ exchanges routed properly, filesystem/SFTP has files, downstream apps processed data.
- **Should not:** share collector output queues across tests without draining and mistake stale messages for current results.

## 7. Modern Spring Cloud Stream Equivalent: OutputDestination

When an app uses Spring Cloud Stream function bindings, the **Spring Integration Test Binder** emulates destinations with in-JVM channels. Two common APIs:

- `InputDestination.send(message, destinationName)` to inject simulated inputs.
- `OutputDestination.receive(timeoutMillis, destinationName)` to receive messages published to a binding.

Typical test dependency:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-test-binder</artifactId>
  <scope>test</scope>
</dependency>
~~~

Depending on the Spring Cloud Stream release, you may need `@Import(TestChannelBinderConfiguration.class)`; newer releases/docs offer `@EnableTestBinder`. **Use the activation mechanism matching your version**, and never mix legacy and modern test binder configs.

Example test with an `uppercase` function:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(classes = StreamOutputTest.StreamTestApp.class)
@Import(TestChannelBinderConfiguration.class)
class StreamOutputTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void receivesTheExpectedOutboundBindingMessage() {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

        input.send(new GenericMessage<>(bytes), "uppercase-in-0");

        Message<byte[]> result = output.receive(2000, "uppercase-out-0");
        assertNotNull(result);
        assertEquals("HELLO",
                new String(result.getPayload(), StandardCharsets.UTF_8));
    }

    @SpringBootApplication
    static class StreamTestApp {
        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

This example illustrates Spring Cloud Stream lines supporting `TestChannelBinderConfiguration`; on versions requiring `@EnableTestBinder`, adjust annotations per that version's docs. If you configure custom `destination` names different from binding names, pass the **actual destination names** to `send`/`receive`, rather than assuming `uppercase-in-0` and `uppercase-out-0`.

**Important:** this tests **Spring Cloud Stream bindings**, not an automatic replacement for every Spring Integration outbound adapter/gateway. The in-memory test binder does not simulate real Kafka/JMS/AMQP behavior (acks, partitions, rebalances, broker transactions).

## 8. Plain Spring Integration: QueueChannel Is the Simplest Collector

With `IntegrationFlow` and `MessageChannel`, the easiest controlled approach is having the flow in a **test context** send results to a `QueueChannel`. This serves as a collector **conceptually**—no Spring Cloud Stream `MessageCollector` class needed.

A **self-contained** example of a payload normalization flow:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OutputChannelTest.FlowConfig.class)
class OutputChannelTest {

    @Configuration
    @EnableIntegration
    static class FlowConfig {

        @Bean("inputChannel")
        MessageChannel inputChannel() {
            return new DirectChannel();
        }

        @Bean("observedOutput")
        PollableChannel observedOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow normalizeFlow() {
            return IntegrationFlow.from("inputChannel")
                    .<String, String>transform(String::trim)
                    .channel("observedOutput")
                    .get();
        }
    }

    @Autowired
    @Qualifier("inputChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("observedOutput")
    PollableChannel output;

    @Test
    void collectsPayloadAndBusinessHeaders() {
        Message<String> request = MessageBuilder
                .withPayload("  order-42  ")
                .setHeader("correlationId", "corr-42")
                .setHeader("sourceSystem", "file")
                .build();

        assertTrue(input.send(request));

        Message<?> actual = output.receive(1000);
        assertNotNull(actual);
        assertEquals("order-42", actual.getPayload());
        assertEquals("corr-42", actual.getHeaders().get("correlationId"));
        assertEquals("file", actual.getHeaders().get("sourceSystem"));
        assertNull(output.receive(0));
    }
}
~~~

**What the test proves:** messages enter the channel, the transformer executes, and the collected output has the right payload and headers. Because `QueueChannel` sits at the **end of the test flow**, consuming from it does not steal messages from another real consumer.

**What the test does not prove:** whether an inbound adapter read File/SFTP properly, or whether an outbound adapter delivered to a server/broker/database. If the module requires full adapter-boundary coverage, add protocol tests and side-effect assertions.

### 8.1. When Not to Replace Flow Output with a QueueChannel

If the production flow connects a `DirectChannel` directly to an outbound handler in the same transaction, swapping the target for a queue changes exception timing, commit/rollback behavior, and side effects. Keep the test above for **logic and wiring**, and add an integration test preserving the production path to verify critical semantics.

### 8.2. Why Might a Test Hang or Pick Up the Wrong Message?

- Calling `receive()` without a timeout on an empty queue can wait forever.
- Another poller/consumer reading the same queue before the test leaves `receive()` returning `null`.
- A queue surviving across multiple test methods without draining retains outputs from earlier runs.
- Two tests running in parallel on the same channel can mix up correlation IDs.

Fix: use isolated test contexts/queues or strict isolation, enforce bounded timeouts, attach unique business IDs, and clean up per lifecycle.

## 9. Writing Your Own Test Collector: MessageHandler and BlockingQueue

Not every project needs a test binder dependency. A compact collector is a `MessageHandler` receiving messages and storing them in a `BlockingQueue`. This helps when tests need full control over result lists, counts, ordering, and receive timeouts.

~~~java
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

final class CapturedOutput implements MessageHandler {

    private final BlockingQueue<Message<?>> messages =
            new LinkedBlockingQueue<>();

    @Override
    public void handleMessage(Message<?> message) {
        messages.add(message);
    }

    Message<?> next(Duration timeout) throws InterruptedException {
        return messages.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    List<Message<?>> drain() {
        List<Message<?>> result = new ArrayList<>();
        messages.drainTo(result);
        return result;
    }

    void clear() {
        messages.clear();
    }
}
~~~

For the collector to work, **subscribe it at the right message reception point** in the test. For example, given an output `PublishSubscribeChannel`:

~~~java
CapturedOutput collector = new CapturedOutput();

// Fixture already declared PublishSubscribeChannel resultEvents
resultEvents.subscribe(collector);
try {
    // Trigger flow then await result.
    Message<?> first = collector.next(Duration.ofSeconds(2));
    assertNotNull(first);
    assertEquals("processed", first.getHeaders().get("processingStatus"));
}
finally {
    resultEvents.unsubscribe(collector);
}
~~~

This example illustrates the verification/cleanup pattern; `resultEvents` is a bean/fixture in the test context. Using a `BlockingQueue` **does not persist results across restarts**; it is purely an in-memory testing tool.

**Never attach a new collector to a `DirectChannel` that already has a business consumer** because it can steal messages. On a `PublishSubscribeChannel`, the collector receives messages on a fan-out branch, yet the collector receiving a message does not prove the outbound subscriber also finished. If the collector attaches to a flow carrying mutable payloads, avoid holding references to objects mutated by another subscriber.

### 9.1. Why Not Use a Plain ArrayList for Async Collection?

If a producer writes on an executor thread while the test thread reads an unsynchronized `ArrayList`, data races, visibility bugs, or flakiness will occur. `BlockingQueue` or `ConcurrentLinkedQueue` paired with latches or proper synchronization fits better. You must still define **what constitutes completion**; a queue receiving a message is only part of the outcome.

### 9.2. Notes on Collecting Multiple Outputs

`drain()` grabs only messages **already present at the moment of the call**; in async flows, more messages may still arrive afterward. To wait for exactly N results, call `next(timeout)` N times or use a latch/await until business conditions are satisfied. Once N messages arrive, check a stability window or completion signal if you must guarantee no extra messages exist.

## 10. Using MockIntegrationContext to Inspect Output Before a Real Adapter

`spring-integration-test` supports `@SpringIntegrationTest` and `MockIntegrationContext`. When testing a flow without calling real SFTP/HTTP/brokers, you can **replace the outbound endpoint's handler with a mock** to capture messages right at the boundary before they leave.

Diagram:

~~~mermaid
flowchart LR
    IN["Input MessageChannel"] --> F["Parser / Transformer / Router"]
    F --> C["outboundChannel"]
    C --> M["MockMessageHandler in test"]
    C -. "production" .-> R["Real outbound adapter"]
    M --> A["ArgumentCaptor and assertions"]
~~~

Conceptual example using test-support APIs:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

import static org.springframework.integration.test.mock.MockIntegration
        .mockMessageHandler;

// Inside a test with @SpringJUnitConfig and @SpringIntegrationTest:
@Autowired
MockIntegrationContext mockIntegrationContext;

@AfterEach
void restoreEndpoint() {
    mockIntegrationContext.resetBeans();
}

@Test
void capturesTheMessageBeforeExternalSend() {
    ArgumentCaptor<Message<?>> captor =
            ArgumentCaptor.forClass(Message.class);

    MessageHandler mockHandler =
            mockMessageHandler(captor);

    mockIntegrationContext.substituteMessageHandlerFor(
            "partnerOutboundEndpoint", mockHandler);

    // Fixture provides inputChannel; trigger the flow.
    inputChannel.send(new GenericMessage<>("order-42"));

    Message<?> captured = captor.getValue();
    assertEquals("order-42", captured.getPayload());
}
~~~

**Mandatory assumptions:** `partnerOutboundEndpoint` is a substitutable **consumer endpoint ID**, not an arbitrary channel name; the test uses `@SpringIntegrationTest`; and the flow is synchronous enough that results are immediately available—otherwise wait explicitly. Overload syntax on mock factories and typing `ArgumentCaptor<Message<?>>` may require adjustments for specific Mockito/Spring Integration versions. When capturing the whole message isn't needed, pair a mock handler with `Mockito.verify(...)`.

Benefit: no real connection needed to inspect **the message right before the outbound adapter**. Limitation: because the real adapter was replaced, the test **has not verified** adapter-specific serialization, HTTP statuses, SFTP uploads, Kafka publish acks, or database transactions. Keep a separate integration test with the real adapter.

**Do not forget `resetBeans()`** after tests; otherwise mocks can persist across tests sharing the Spring context and produce unreliable results.

## 11. WireTap: Observing Without Consuming the Primary Message

`WireTap` forwards **an observed copy of the message** to a secondary channel while the primary path continues. This is a good option when you want to stay closer to production topology rather than pulling messages off a channel used by real consumers.

~~~mermaid
flowchart TD
    A["Inbound adapter"] --> C["Primary DirectChannel"]
    C --> H["Business handler"]
    C -. "WireTap interceptor" .-> Q["Probe QueueChannel"]
    H --> O["Outbound adapter"]
    Q --> T["Test assertions"]
~~~

A Java DSL setup can attach a wire tap at the target observation point, route copies to `probeChannel`, and let tests call `receive(timeout)` on the probe. Check configuration APIs for your Spring Integration version and **never attach duplicate wire taps** if contexts are reused.

Distinguish carefully:

- `WireTap` **observes** messages passing through a channel; it does not prove downstream handlers finished.
- `PublishSubscribeChannel` uses **fan-out as part of flow semantics**; adding a test subscriber can affect latency/errors if synchronous.
- `QueueChannel` on the **main branch** can alter ordering and transactions if injected into the topology.
- `MockIntegrationContext` **replaces** the real endpoint—great for internal flow tests, but skips external side effects.

For sensitive data, record/inspect only required metadata; never dump full tokens, passwords, or personal payloads into collectors that print on test failure.

## 12. Asserting Payloads: String, byte[], JSON, and DTOs

Not every adapter produces a `String`. File inbound adapters may emit `File` or `byte[]`, HTTP/JMS/Kafka may convert types via message converters, and database inbound adapters may produce `Map` or DTOs.

### 12.1. With String

~~~java
Message<?> message = output.receive(1000);
assertNotNull(message);
assertInstanceOf(String.class, message.getPayload());
assertEquals("order-42", message.getPayload());
~~~

### 12.2. With byte[]

~~~java
Message<?> message = output.receive(1000);
assertNotNull(message);
assertInstanceOf(byte[].class, message.getPayload());

byte[] bytes = (byte[]) message.getPayload();
assertArrayEquals("HELLO".getBytes(StandardCharsets.UTF_8), bytes);
~~~

If the contract allows specific encodings, never compare byte arrays by calling `toString()` on the array (which prints object identity, not content). Decode using the specified charset or compare bytes directly.

### 12.3. With JSON

Example output body:

~~~json
{"orderId":"42","status":"ACCEPTED","amount":100}
~~~

If the business contract does not mandate field ordering, parse JSON and assert individual fields:

~~~java
JsonNode json = objectMapper.readTree(
        (String) message.getPayload());

assertEquals("42", json.path("orderId").asText());
assertEquals("ACCEPTED", json.path("status").asText());
assertEquals(100, json.path("amount").asInt());
~~~

This snippet assumes `objectMapper` is in the test fixture and payload is a `String`; if output is `byte[]`, use the byte-array overload. Never compare raw JSON strings verbatim when field order is insignificant. For strict schemas, also test required fields, null/missing values, enums, monetary values, and schema versions.

### 12.4. With DTOs

~~~java
OrderEvent order = assertInstanceOf(
        OrderEvent.class, message.getPayload());

assertEquals("42", order.orderId());
assertEquals(100, order.amount());
~~~

`OrderEvent` is an illustrative application DTO (e.g., a Java record); keep mapper unit tests separate from message-flow tests so failures pinpoint the exact broken layer.

## 13. Asserting Headers: Provenance, Correlation, and Transport Metadata

Even with a valid payload, wrong headers can break downstream routers, gateways, brokers, or handlers.

~~~java
Message<?> actual = output.receive(1500);
assertNotNull(actual);

assertEquals("corr-42",
        actual.getHeaders().get("correlationId"));
assertEquals("sftp",
        actual.getHeaders().get("sourceSystem"));
assertEquals("order.created",
        actual.getHeaders().get("eventType"));
~~~

Headers particularly worth checking:

| Header / Metadata | Test Focus |
|---|---|
| Business ID / correlation | Accurately links request ↔ output and error ↔ request |
| Source filename / path | File came from the right directory or remote path |
| Routing key / partition key | Message reaches the right destination/topic/partition per policy |
| Content type | Converter applies matching schema/encoding |
| Reply / error channel | Replies/errors arrive at expected locations when configured |
| Timestamp | Relative ordering or format, never uncontrolled snapshot equality |
| Security context | Secret tokens are never unnecessarily copied to outputs/logs |

**Do not assert that every header matches the input message**: transformers, gateways, or adapters may add, alter, or filter out headers. Assert headers **guaranteed** by the contract or adapter config. `MessageHeaders.ID` and `TIMESTAMP` can be regenerated when building new messages, so never treat framework-generated IDs as durable business keys.

## 14. MessageCollector and Testing Multiple Outputs

One input can yield:

- A single output after a transformer.
- Multiple outputs after a splitter.
- One output on one of several branches after a router.
- Multiple copies delivered to `PublishSubscribeChannel` subscribers.
- One business output **plus** an audit/notification event.
- Zero business output because a filter rejected it, alongside a metric or error event.

### 14.1. Splitter: Don't Check Only the First Message

Suppose a CSV contains three records and a splitter produces three messages. Tests should:

1. Send an input with `batchId`.
2. Receive all **three messages** using a bounded timeout.
3. Compare the **set of business IDs** if order isn't guaranteed, or compare in order when configuration guarantees it.
4. Inspect correlation/sequence headers used by the app.
5. Verify batch completion and invalid-record handling policies, if applicable.

Example verification skeleton:

~~~java
Set<String> receivedIds = new HashSet<>();

for (int i = 0; i < 3; i++) {
    Message<?> message = output.receive(2000);
    assertNotNull(message);
    receivedIds.add((String) message.getHeaders().get("orderId"));
}

assertEquals(Set.of("41", "42", "43"), receivedIds);
~~~

This snippet assumes the flow places `orderId` in headers. Checking only `receivedIds.size() == 3` is insufficient if one ID arrives twice and another is dropped: compare against the **expected set** and original count.

### 14.2. Router: Dedicated Collector per Branch

Example:

~~~text
eventType=ORDER_CREATED -> ordersOutput
eventType=ORDER_FAILED  -> failuresOutput
invalid eventType       -> error/reject policy
~~~

Use three separate output channels in tests; never dump them into one collector and guess by arrival order. Assert each event lands on its intended branch and other branches receive nothing unexpected. In async flows, wait out an observation window or wait for all endpoints to finish before concluding "no message."

### 14.3. Publish-Subscribe: Distinguish Fan-Out from Competing Consumers

If the contract requires two handlers to **both** receive an event, use genuine publish-subscribe and verify each subscriber individually. With a point-to-point queue, each message should be taken by **one consumer**. Expecting "both collector and outbound receive the same message from a `QueueChannel`" confuses channel semantics.

## 15. Asynchronous Testing: Controlled Waiting, Never Arbitrary Sleeps

With `ExecutorChannel`, inbound pollers, JMS/Kafka listeners, or async HTTP, outputs can appear **after the send call returns**. Writing:

~~~java
input.send(message);
assertNotNull(output.receive(0)); // flaky if output arrives later
~~~

is unsafe with respect to timing.

Replace it with:

~~~java
assertTrue(input.send(message));

Message<?> actual = output.receive(2000);
assertNotNull(actual, "No output received within test timeout");
assertEquals("order-42", actual.getPayload());
~~~

When waiting for **side effects not landing on a `QueueChannel`**, use condition-waiting tools like latches, Awaitility, or deadline polling:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(1, repository.countByOrderId("42")));
~~~

This assumes Awaitility is configured, `repository` is part of the test fixture, and the test runs against an isolated test DB. Avoid `Thread.sleep(5000)` followed by a single assertion; CI execution speed and scheduler timing fluctuate.

### 15.1. Testing That No Output Appears

When a filter is expected to drop a message, you might write:

~~~java
input.send(invalidMessage);
assertNull(rejectedOutput.receive(300));
~~~

However, this assertion only proves no message arrived **within 300 ms** on that channel; it does not guarantee output will never appear. Stronger conclusions require a flow completion condition, processing-done signal, or synchronous test endpoint with a defined flow.

### 15.2. Tests Should Never Wait Forever

Set bounded timeouts and include correlation IDs/destinations in failure messages; never log payloads containing secrets. When a test spans multiple async stages, budget deadlines realistically for test infrastructure latency instead of stacking huge timeouts that needlessly slow down the suite.

## 16. Verifying File Inbound and File Outbound Output

### 16.1. File Inbound: Received Messages Aren't Necessarily File Contents

A **File inbound adapter** normally emits messages whose payload is a `File` object; converting contents into `String` or `byte[]` is typically done by a subsequent transformer. Tests should separate both layers:

- **Source/filter test:** directory scanned, matching files picked up, filenames accurate, partially written files handled per convention.
- **Output collector test:** post-transformer message has the right payload/headers/correlation without spurious duplicates.

Example contract:

~~~text
Filesystem:
  inbox/orders-42.csv
  inbox/ignore.tmp

Adapter source:
  accepts only *.csv

Collector at parsedOrders:
  payload OrderEvent(orderId=42, amount=100)
  headers sourceFileName=orders-42.csv, correlationId=corr-42
~~~

Know precisely which adapter and transformer sets `sourceFileName`; it is an **example business header**, not a claim that the File adapter always uses that exact header name.

Testing an inbound path:

1. Create an isolated temporary directory with `@TempDir`; never use production directories.
2. Place valid test files and filter-excluded files.
3. Start a poller configured with a fast test schedule.
4. Read from the collector via `receive(timeout)`.
5. Assert payloads, metadata, and receipt counts.
6. Stop the poller and clean up file/metadata-store state.

**Note:** pattern filters like `*.csv` **do not automatically guarantee accept-once**. If business rules require processing each file once, configure an appropriate filter/metadata store and test across multiple polls and restarts.

### 16.2. File Outbound: Collector Is Only the Pre-Write Point

For File outbound adapters, there are two independent assertions:

~~~text
Before outbound:
  outputCollector receives message containing expected content
  targetFileName header matches policy

At destination:
  file output/orders-42.csv actually exists
  file contents match exact bytes/encoding
  no stray temp files remain if contract requires atomic move
~~~

If a test only collects messages before a **mocked outbound handler**, it cannot prove file writing succeeded. An integration test using `@TempDir` as the output directory, sending messages through the **real adapter**, and asserting with `Files.exists` and `Files.readString` provides side-effect evidence.

Negative cases: invalid paths, missing write permissions, duplicate filenames, append vs. overwrite, large files, partial writes before crashes, and temporary file cleanup rules.

## 17. SFTP: Collecting Output After Sync and After Processing

SFTP inbound can operate in two stages:

~~~mermaid
flowchart LR
    R["SFTP remote files"] --> SYNC["Remote synchronizer"]
    SYNC --> LOCAL["Local staging directory"]
    LOCAL --> SOURCE["File inbound source"]
    SOURCE --> CHANNEL["MessageChannel"]
    CHANNEL --> COL["Collector"]
    CHANNEL --> PARSER["Parser/validator"]
~~~

**A collector on the channel proves only that the file entered the message flow**, not that:

- The remote file downloaded every byte completely.
- Filters prevent re-reading files after restarts.
- Files mid-upload were properly ignored.
- Downstream processing succeeded.
- Remote files were deleted/renamed per policy.

To test SFTP inbound realistically, use an isolated SFTP server/container with dedicated accounts and host keys; place a remote file, wait for local sync, then inspect both the collector and downstream results. Never use real credentials or disable SSH host-key validation to make tests pass.

For SFTP outbound, a pre-adapter collector shows only the outgoing message; end-to-end tests must **read back the file at the remote path**, verify contents/checksums, and test connection timeouts/partial uploads. An upload returning success may still require checking rename/temporary suffix rules per contract.

Additional scenarios to cover:

| Scenario | What to Verify |
|---|---|
| Incomplete remote file | Does not emit output and falsely process partial data |
| Disconnect mid-download | Errors follow recovery path; no fake "completed" message emitted |
| Re-poll | Does not duplicate output beyond policy |
| Application restart | Metadata store / remote filter behaves as designed |
| Wrong host key | Connection rejected; logs leak no secrets |
| Duplicate filename upload | Overwrite/rename/skip per contract verified on server |

## 18. HTTP Gateways: Collectors Can Capture Requests or Replies

HTTP involves two distinct testing directions.

### 18.1. Inbound HTTP Gateway

HTTP calls enter the app, the gateway creates a message for the flow, and awaits a reply. Tests must send **real HTTP requests to the test endpoint**, not just build a `GenericMessage`, when the goal is verifying HTTP mapping.

Example:

~~~text
POST /api/orders
Content-Type: application/json
X-Correlation-Id: corr-42
Body: {"orderId":"42","amount":100}

Collector after inbound gateway:
  payload matches order data
  correlationId mapped per config

HTTP response:
  status=201
  body={"accepted":true}
~~~

Tests must verify payload/headers on the channel and status/body in the HTTP response. Missing headers, bad JSON, timeouts, and missing replies must behave deterministically. **A collector receiving a message does not automatically guarantee the right HTTP response was sent.**

### 18.2. Outbound HTTP Gateway

A flow sends a message to the gateway; the gateway calls an external service and returns a reply message to the flow.

- **Mock server** (WireMock/MockWebServer) verifies the exact HTTP method, URI, headers, and body sent.
- **Output collector after gateway** verifies the reply was converted into the expected message.
- **Negative tests** with 4xx/5xx/timeouts prove error mapping, retry/backoff, and missing-reply handling.

Example contract:

~~~text
Input message:
  payload orderId=42
  header correlationId=corr-42

Outbound HTTP:
  POST /shipments
  X-Correlation-Id: corr-42

Mock response:
  HTTP 201 {"shipmentId":"sh-42"}

Reply collector:
  payload shipmentId=sh-42
  correlationId=corr-42
~~~

**Do not assume the gateway automatically forwards every header**. When correlation must cross HTTP, configure an explicit header mapper or transformer and assert against the contract.

### 18.3. One-Way Outbound HTTP Adapter

If the adapter is **one-way**, there is no application-level reply like a gateway. To verify output, combine a pre-adapter collector **with** checking that the mock HTTP server received the request. Waiting for a reply from a one-way adapter violates the contract.

## 19. JMS and AMQP: Verifying Output Alongside Acknowledgments

JMS and AMQP (e.g., RabbitMQ) have their own brokers, sessions, and containers. An in-memory collector proves **internal messages before publish** or **messages entering the flow after consume**, but does not fully simulate:

- Queue/topic destinations or exchange/routing-key/binding topologies.
- Publisher confirms/returns (AMQP) and unroutable message handling.
- Consumer acknowledgments, nacks, rejects, requeues, and redeliveries.
- Transaction commits/rollbacks and dead-letter routing.
- Ordering and competition across multiple consumers.

| Test Point | What to Verify |
|---|---|
| Producer output collector | Payload, routing key, headers to be published |
| Test broker | Message lands in real destination matching topology |
| Consumer input collector | Adapter delivers message to expected channel |
| Consumer business output | Business outcome or side effect succeeded |
| Error/retry collector | Errors retain correlation, bounded retries, and proper DLQ/recovery |

Failure example: a consumer receives a message, writes to the database, then crashes before ack. The broker may redeliver; **the collector seeing two messages does not automatically mean data was duplicated**, yet the consumer must enforce idempotency so side effects aren't repeated unintentionally.

With RabbitMQ, test publisher confirms/returns against the broker when part of the contract; a pre-outbound collector cannot substitute for publisher confirms. With JMS, use an appropriate test provider when verifying acknowledgments and redelivery.

## 20. Kafka: OutputDestination Does Not Replace a Real Kafka Broker

The modern Spring Cloud Stream test binder provides `OutputDestination` to collect **binding** outputs, yet it runs **in-JVM**, not on a Kafka cluster. When an app has multiple function outputs, the test binder checks payloads/bindings quickly; when business behavior relies on Kafka specifics, write separate tests with a test broker.

Critical Kafka assertions:

| Property | Why Test It? |
|---|---|
| Topic | Messages reach the right topic; avoid cross-tenant/env leaks |
| Record key | Drives partitioning and ordering for a given business key |
| Serializer/schema | Producer and consumer agree on compatible data formats |
| Headers | Correlation, event type, version, and required metadata |
| Consumer group | Avoid reading stale records from other test groups |
| Offset/commit | Error handling replays/redelivers per semantics |
| DLT/retry topic | Poison messages do not block consumers indefinitely |
| Sink result | Broker accepting a record does not mean business work finished |

When testing output with `OutputDestination.receive(timeout, destination)`, **do not claim** that Kafka persisted/replicated records or that production consumer groups processed them. That is a binding/flow test. Complement it with integration tests using a Kafka test container/embedded broker matching app config, dedicated topics/groups, and sink side-effect verification.

With multiple partitions and no global ordering guarantee, **assert sets of results or ordering within a single key/partition**, never absolute topic-wide order.

## 21. Database Adapters: Output Collectors and Table State Must Match

A JDBC/JPA inbound polling adapter may:

1. Query records with `status=NEW`.
2. Convert records into messages and send to a channel.
3. Mark records as fetched/in-progress within a transaction.
4. Have a consumer apply side effects in another system.

A collector on the output channel proves records entered the flow; **it does not guarantee the source transaction committed** or the target processed them.

Test example:

~~~text
Before:
  orders_outbox(id=42, status=NEW)

After poll:
  outputCollector: message(eventId=42, valid payload)
  database: NEW/IN_PROGRESS/PROCESSED status matches policy

After consumer:
  sink table: exactly one record/side effect
  audit: correlated with eventId=42
~~~

Negative tests:

- Row fails schema validation → do not mark successfully processed.
- Two parallel pollers/instances → no unintended duplicate side effects.
- Downstream timeout → retry/rollback/compensation per transaction boundary.
- Lost database connection → error/backoff; no spurious outputs emitted.
- Restart after crash → row may be re-read, so an idempotent consumer prevents duplicate outcomes.

If using the transactional outbox pattern, separately test **the transaction writing business data + outbox row**, then test the publisher/consumer. Never assume a DB transaction can roll back an HTTP call or SFTP upload that already succeeded.

## 22. Pollers, Gateways, Service Activators, and Where to Collect Messages

| Component | Reasonable Collection Point | What Remains Unproven If Only Collected There |
|---|---|---|
| File/DB inbound poller | Channel after inbound adapter or transformer | Final processing completion at target |
| SFTP synchronizer | Channel after local file source, plus file state | Remote file deleted/acked properly |
| HTTP inbound gateway | Flow channel and real HTTP response | External consumers of response completed work |
| HTTP outbound gateway | Reply channel after gateway | All remote side effects committed |
| Service activator | Channel after activator or mock endpoint handler | Downstream adapter delivered successfully |
| Router | Per-branch collectors | All branch handlers completed |
| Splitter | Output collector checking count/sequence | Full aggregation/commit succeeded |
| Aggregator | Output after group completion | Each original message independently succeeded if unchecked |

### 22.1. Controlling Poller Timing

Production pollers may run every minute or hour; tests should not wait on production schedules. In a **test context**, use a fast test schedule, control endpoint `start()/stop()`, or use test triggers where supported by your version.

Spring Integration provides `@SpringIntegrationTest(noAutoStartup=...)` and `MockIntegrationContext` for endpoint control. Some newer releases support swapping triggers in tests. Always **assign exact endpoint IDs** and reset configurations after tests.

Never treat `maxMessagesPerPoll(1)` as "emit only one message for the entire test"; it caps messages **per poll cycle**, while the poller can fire repeatedly.

### 22.2. Gateways and Reply Timeouts

For request–reply, test all of:

- Reply arrives with expected type and correlation.
- No reply arrives before timeout.
- Remote system/gateway throws an exception or returns an error status.
- Reply lands on wrong channel or reply mapping mismatches.
- Concurrent requests do not steal each other's replies.

To verify request–reply end-to-end, don't collect only on the gateway's input channel; **assert the value returned to the caller** or the real HTTP/JMS protocol response.

## 23. Error Output, Retries, and Failure Outcomes

A flow has more than "success output." When an adapter or handler fails, a message may:

- Cause a **synchronous caller** to receive an exception.
- Route to an **error channel** depending on endpoint/error-handler config.
- Be retried by an advice/retry template or middleware.
- Be rejected/nacked/redelivered by a broker listener.
- Move to a **DLQ/DLT** or recoverer.
- Stay in a state awaiting manual intervention.

**Never assume having an `errorChannel` bean means every exception from every adapter automatically goes there.** Check threads, adapters, pollers, listener containers, and configured advices.

Example contract for invalid data:

~~~text
Input message:
  payload="malformed-csv"
  correlationId="corr-err-42"

Expected:
  no valid OrderEvent on successOutput
  errorOutput contains error identification info
  correlationId/failedMessage remain traceable where supported
  no HTTP POST sent to partner
  no infinite retries on invalid input data
~~~

### 23.1. Inspecting Messages on the Error Channel

With an explicitly configured error flow writing to a test `PollableChannel`:

~~~java
Message<?> error = errors.receive(2000);
assertNotNull(error);
assertInstanceOf(
        org.springframework.messaging.support.ErrorMessage.class,
        error);

// Depending on version/endpoint, payload is Throwable or a subclass.
Throwable failure = (Throwable) error.getPayload();
assertNotNull(failure.getMessage());
~~~

This assumes `errors` is wired to receive `ErrorMessage` from the **right** asynchronous endpoint. For synchronous `DirectChannel` failures, `assertThrows(...)` on the caller is typically more appropriate.

With `MessagingException`, some cases expose `getFailedMessage()` to identify the failing input; do not assume every `Throwable` has this property. When logging or asserting, never print input secrets/tokens.

### 23.2. Never Confuse Success and Failure Outcomes

When a record is rejected, tests should prove **no side effect occurred at the target**. An error collector receiving a message is helpful, yet if the outbound adapter still sent the bad data, the test must fail. This is vital for payments, notification emails, or partner webhooks.

## 24. Handling Duplicate Messages, Retries, and Idempotency

Real transports can redeliver messages; a collector receiving two messages is not necessarily a bug, whereas **two unintended business side effects** definitely are.

Distinguish:

| Phenomenon | Description | What Should Tests Verify? |
|---|---|---|
| Retry | Re-executing the same operation after a transient error | Attempt count, backoff, deadline, and outcome |
| Redelivery | Broker re-sends due to missing ack/commit | Idempotent consumer and ack state |
| Duplicate input | Same business event arrives multiple times from source | Business ID is not mishandled twice |
| Replay | Reprocessing messages from DLQ/outbox/offset | State is safely recovered |
| Partial failure | Target write succeeds, then error occurs before ack | Retries do not duplicate side effects |
| Poison message | Deterministic payload fails every time | Quarantined/DLQed without blocking system indefinitely |

Example:

~~~text
Attempt 1: HTTP POST /shipments(orderId=42) -> timeout
Server: actually already created shipment sh-42
Attempt 2: retry same orderId=42 -> server recognizes idempotency key
Expected: only one shipment exists, result linked to orderId=42
~~~

For complete tests, a mock server can simulate **operation succeeded yet response was lost**; a post-retry collector reflects only the final outcome. Also assert **side-effect counts on the server/DB**, since HTTP request counts may legitimately exceed one under retries.

### 24.1. "No Extra Messages" Must Be Defined Precisely

If a flow can resend after timeouts, calling `output.receive(0)` once cannot prove no duplicates occur. Depending on contract, you can:

- Verify the business sink holds only one row.
- Wait for a flow-completion signal and count outputs.
- Control retry schedules and observe across a defined window.
- Use unique event IDs and collect every attempt to explain the outcome.

Never demand "exactly-once" guarantees from a collector when the real transport does not promise it. Enforce **consumer idempotency** whenever at-least-once delivery is possible.

## 25. Isolation: Cleaning Collectors, Contexts, and Stale Messages

Output tests can pass or fail randomly if collectors/queues are shared across tests.

### 25.1. Common Issues

- `QueueChannel` retains messages from a prior test.
- `PublishSubscribeChannel` keeps a collector handler subscribed after a test ends.
- `MockIntegrationContext` missed `resetBeans()`, leaving real outbound adapters unrestored.
- A poller or JMS/Kafka listener from an earlier test keeps running and pushing messages.
- Parallel tests share a topic, consumer group, or filename.
- Memory holds mutable payloads; tests inspect them after another thread modified them.
- Test binder `OutputDestination` retains old messages in a shared application context.

### 25.2. Safe Cleanup Rules

| Resource | Approach |
|---|---|
| Custom collector | `clear()` after test and ensure no other consumer shares the queue |
| `QueueChannel` | Controlled drain or dedicated context/queue per test |
| Pub/sub subscriber | `unsubscribe(handler)` in `finally`/`@AfterEach` |
| `MockIntegrationContext` | `resetBeans()` after endpoint substitution |
| Inbound adapter/poller | Control start/stop; shut down sessions/threads per lifecycle |
| Files | `@TempDir`; verify output directory is empty before running |
| HTTP mock server | Random port; reset request journal |
| Kafka/Rabbit/JMS | Dedicated test topics/queues/groups; clean up or isolate test namespaces |
| Database | Rollback where appropriate, truncate/isolated test schema; never rely on stale state |

**Avoid defaulting to `@DirtiesContext` on every test.** It helps isolate contexts when configuration/beans are mutated irreversibly, yet incurs heavy overhead. Prefer accurate cleanup; reserve context isolation for cases where clean resets are impossible.

### 25.3. Debugging Flaky Results

A structured investigation order:

1. Print correlation ID, channel name, deadline, and received message count (without secrets).
2. Verify the flow subscribed its handlers and endpoints are running.
3. Check timing of producers, pollers, consumers, and assertions.
4. Check for competing consumers or publishers.
5. Inspect queues/topics/files/DB for stale data.
6. Verify mock servers/brokers/test containers are ready.
7. Confirm whether the output collector sits before or after target side effects.
8. Check for races from parallel tests, uncleaned subscribers, or retry policies.

Never just bump timeouts from 2 seconds to 60 seconds and ignore wiring bugs, deadlocks, or stopped endpoints.

## 26. Case Study: File/SFTP Inbound → Order Processing → HTTP Outbound

Suppose a system receives CSV files over SFTP, parses orders, calls a partner API via an HTTP gateway, and persists status to a database.

~~~mermaid
flowchart LR
    R["SFTP remote directory"] --> SYNC["SFTP synchronizer"]
    SYNC --> FILE["Local File inbound poller"]
    FILE --> IN["ordersInput"]
    IN --> PARSE["CSV parser / validator"]
    PARSE --> VALID["validOrders"]
    VALID --> HTTP["HTTP outbound gateway"]
    HTTP --> RESULT["ordersResult"]
    RESULT --> DB["Database writer"]
    PARSE -. "invalid data" .-> REJECT["rejectedOrders"]
    HTTP -. "transport error" .-> RETRY["Retry / recovery"]
    VALID -. "test collector" .-> OBS["Observed messages"]
~~~

### 26.1. Contract

Input fixture:

~~~text
remote file: orders-42.csv
content:
  orderId,total
  42,100

Expected internal message:
  payload OrderEvent(orderId=42,total=100)
  header correlationId=order-42
  header sourceFile=orders-42.csv

Expected HTTP:
  POST /shipments
  {"orderId":"42","total":100}
  X-Correlation-Id: order-42

Expected reply:
  shipmentId=sh-42

Expected database:
  orderId=42, shipmentId=sh-42, status=SUBMITTED
~~~

### 26.2. Layered Collector Design

| Collector / Observation | What Does It Receive? | What It Proves |
|---|---|---|
| `ordersInput` | File message after inbound adapter | Poller emitted file into channel |
| `validOrders` / wire tap | DTO + correlation | Parsing/validation succeeded, routing accurate |
| `rejectedOrders` | CSV error details | Invalid data took reject branch |
| `ordersResult` | Reply from HTTP gateway | Response returned to flow |
| Mock HTTP server | Request body/headers | Outbound HTTP actually sent |
| Test database | Final status row | Final business side effect completed |

### 26.3. Test Checklist

1. Valid file → one DTO on collector, one HTTP request, one result row.
2. File failing filter → does not enter flow; no HTTP call.
3. CSV missing column → reject output received, no shipment created.
4. HTTP 201 → reply has accurate `shipmentId` and correlation.
5. HTTP 400 → business error recorded, no retry if policy forbids it.
6. HTTP 503 then 201 → retries matching count and accurate final outcome.
7. Timeout when server actually wrote → idempotency keeps one shipment.
8. Two files with same `orderId` → no unintended duplicate side effects.
9. Poller restart → metadata filter/dedup behaves properly.
10. SFTP disconnect then recovery → no bogus/missing messages, logged and recovered.
11. DB fails after HTTP succeeds → compensating/recovery flow runs without assuming HTTP rollback.
12. Gateway receives no reply → bounded timeout/error handling.
13. Two parallel tests → data, remote paths, mock servers, and DBs do not collide.

### 26.4. Spotting Insufficient Evidence

Asserting only `validOrders.receive(...) != null` proves parsing and routing **before HTTP**. Observing only an HTTP request hitting the mock server does not prove DB writes succeeded. A DB row left over from an earlier test invalidates the result too. Every test needs **independent input data and observable target outcomes**.

## 27. Output Testing Matrix by Adapter Type

| Adapter Type | Suitable Output Collector | Mandatory Checks Beyond Collector |
|---|---|---|
| File inbound | Queue/wire tap after source or parser | File filter, duplicates, encoding, lifecycle |
| File outbound | Pre-handler collector | Real file, name/content, write permissions, overwrite policy |
| SFTP inbound | Channel after synchronizer/file source | Remote sync, host key, reconnect, accept-once |
| SFTP outbound | Pre-sender collector | Remote file and upload/rename state |
| HTTP inbound gateway | Channel after HTTP mapping | HTTP response, status, headers, timeout |
| HTTP outbound gateway | Reply channel after gateway | Mock server received exact request, retry/error |
| JMS inbound/outbound | Channel adjacent to adapter | Broker ack/transaction/redelivery |
| AMQP/RabbitMQ | Channel near adapter | Exchange/binding, confirm, nack/DLQ |
| Kafka | `OutputDestination` (if Stream) or SI channel | Topic/key/schema/offset/partition/sink result |
| JDBC/JPA polling | Queue after mapper/handler | Transactions, row status, concurrent polling |
| Service activator | Terminal output channel/mock handler | Real side effects if external dependencies exist |

Goal of the table: **place collectors where contract boundaries become observable**, without hiding what **remains untested**.

## 28. Anti-Patterns with MessageCollector and Output Verification

| Mistake | Consequence | Fix |
|---|---|---|
| Importing legacy `MessageCollector` into plain Spring Integration | Wrong dependency or missing API | `QueueChannel` / custom collector / `MockIntegrationContext` |
| Using legacy binder `MessageCollector` on new Stream apps | Deprecated/replaced API | `InputDestination`/`OutputDestination` |
| Treating a collector message as outbound success | Misses I/O or downstream errors | Assert side effects at the target |
| Attaching collector as second consumer on `DirectChannel` | Steals messages competitively | Use wire tap, true pub/sub, or dedicated test channel |
| `receive()` without timeout | Test hangs when output is missing | `receive(timeout)` |
| Asserting only the first message | Misses extra outputs or missing branches | Verify counts, business ID sets, completion |
| Snapshotting all headers verbatim | Breaks when framework IDs/timestamps change | Assert contract headers only |
| Comparing `byte[]` via `toString()` | Does not inspect contents | `assertArrayEquals` or UTF-8 decode |
| Asserting `null` immediately after async send | Messages may arrive later | Use deadlines and completion signals |
| Failing to clean collectors/subscribers | Picks up stale outputs from prior tests | Teardown/reset/context isolation |
| Mocking the whole flow then claiming Kafka/SFTP tested | Real protocol never ran | Run adapter integration tests with external infra |
| Reusing one correlation ID across the suite | Cannot distinguish tests/parallel runs | Unique ID per test run |
| Configuring retries without testing idempotency | Side effects get duplicated | Test duplicates, replay, partial failures |
| Logging raw tokens/PII in collectors | Secrets leak via CI reports | Redact and limit captured metadata |

## 29. Acceptance Checklist and Self-Check Exercises

### Checklist

- [ ] Determined whether the project uses plain Spring Integration or Spring Cloud Stream.
- [ ] If specs mention `MessageCollector`, confirmed it refers to the **legacy test binder** and matching version.
- [ ] Selected the right collector: `QueueChannel`, terminal handler, wire tap, mock handler, or `OutputDestination`.
- [ ] Did not alter production semantics outside the test's stated scope.
- [ ] Bounded timeouts, isolated fixtures, and unique correlation IDs used.
- [ ] Asserted payload type, encoding/schema, and required business headers.
- [ ] Asserted counts, routing, ordering within guaranteed scope, and absence of unwanted outputs.
- [ ] For outbound, verified side effects at the target system.
- [ ] For gateways, asserted reply/status/timeout—not just input messages.
- [ ] For pollers, controlled scheduling, duplicates, and restarts.
- [ ] For brokers, verified ack/offset/redelivery where part of the contract.
- [ ] Included negative tests for data errors, timeouts, and retries.
- [ ] Cleaned up collectors, endpoints, subscribers, and test data.
- [ ] Explicitly documented what was tested and what remains unproven.

### Scenario A

**Question:** A plain Spring Integration project cannot find the `MessageCollector` class. Should we add the entire legacy Spring Cloud Stream test support?

**Answer:** Not by default. Use `QueueChannel` or a custom collector handler/`MockIntegrationContext` from Spring Integration. `MessageCollector` belongs to Spring Cloud Stream's legacy test binder.

### Scenario B

**Question:** A test using `OutputDestination.receive(...)` sees a message on binding `orders-out-0`. Does that prove Kafka stored the record?

**Answer:** No. The test binder runs in-JVM and emulates bindings. You need a dedicated Kafka integration test to verify publishing, keys, topics, offsets, and target processing.

### Scenario C

**Question:** Adding a collector handler to a `DirectChannel` that already has an outbound adapter causes the collector to receive messages sometimes while the outbound misses them. Why?

**Answer:** `DirectChannel` does not broadcast the same message to every subscriber; the collector became a competing consumer. Use a wire tap or a semantically appropriate fan-out branch.

### Scenario D

**Question:** `QueueChannel.receive(0)` returns `null` after sending a message to an `ExecutorChannel`. Can we conclude the message was lost?

**Answer:** Not yet. Output may arrive asynchronously later; wait with a timeout, and check active handlers, error flows, and lifecycles.

### Scenario E

**Question:** An HTTP outbound gateway gets 201, yet no row appears in the downstream database. The collector after the gateway shows valid output. Is the test complete?

**Answer:** Not if the contract requires a DB row. Verify the sink result and error handling between the gateway and the writer.

### Scenario F

**Question:** A splitter creates three messages, and the test grabs only the first one and marks PASS. What is missing?

**Answer:** You must verify all three outputs, business IDs, correlation/sequence headers, and cases with extra or missing outputs.

### Scenario G

**Question:** A file adapter picks up the same file again after restart, and the collector reports two messages. Is the collector buggy?

**Answer:** Not necessarily. Check the accept-once filter, metadata store, post-read file handling, and retry semantics; the collector is merely observing incoming messages.

### Scenario H

**Question:** A test replaces an outbound adapter with a mock handler and asserts the payload. Can it claim SFTP SSH host-key verification was tested?

**Answer:** No. The real SFTP adapter was replaced; use an SFTP test server to verify connectivity, host keys, uploads, and network errors.

### Scenario I

**Question:** A test suite finds leftover messages from a previous run in `QueueChannel`. How do you prevent false passes?

**Answer:** Isolate contexts/queues, drain or reset before tests, use unique business IDs, ensure no stray pollers keep running, and unsubscribe listeners in teardown.

## 30. References and Version Notes

- **Spring Integration — Testing support:** https://docs.spring.io/spring-integration/reference/testing.html. Reference for `@SpringIntegrationTest`, `MockIntegrationContext`, mock handlers, and controlling endpoints.
- **Spring Cloud Stream — Testing (test binder):** https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html. Reference for `InputDestination`, `OutputDestination`, bindings/destinations, and version-specific test binder activation.
- **Spring Cloud Stream — legacy documentation:** https://cloud.spring.io/spring-cloud-stream/reference/html/spring-cloud-stream.html. The testing section explains migrating from the legacy test-support binder to the Spring Integration test binder; useful for cross-referencing `MessageCollector` in legacy codebases.

**Choose docs matching your version:** Different Spring Integration/Spring Cloud Stream releases may change signatures, dependencies, test annotations, or lifecycles. In real projects, inspect classes actually on the classpath and never mix APIs from two generations in the same test just because names look similar.

## Conclusion

**MessageCollector and output verification** turn hard-to-observe integration flows into concrete checkpoints: where messages are emitted, what payloads/headers they carry, and whether counts, branches, and timing match expectations. In **plain Spring Integration**, `QueueChannel`, terminal collector handlers, wire taps, and `MockIntegrationContext` are the direct tools for observing flows. In **Spring Cloud Stream**, distinguish the legacy `MessageCollector` from the modern `InputDestination`/`OutputDestination` test binder. Most importantly, **a collector seeing a message is not proof that an external system processed it**; testing adapters across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases requires pairing channel assertions with **real side effects, errors, retries, idempotency, and lifecycles**. Only when each test's claims are scoped accurately and state is cleaned between runs does the suite become accurate, stable, and operationally valuable.

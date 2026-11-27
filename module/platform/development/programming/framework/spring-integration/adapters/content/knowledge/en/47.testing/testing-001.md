# Adapter Channel Testing in Spring Integration

## 1. Goals and Scope

In Spring Integration, an adapter connects an **external source or destination** to the internal message flow. An inbound adapter creates messages from files, SFTP, brokers, HTTP, or databases; an outbound adapter receives messages and produces side effects in an external system. A gateway provides request–reply communication where appropriate, a poller retrieves data on a schedule, and a **MessageChannel** connects endpoints and determines the delivery mechanism.

**Adapter channel testing** means verifying the boundary between the adapter and the message-processing system: whether the adapter emits/receives the right messages; whether the channel delivers to the right place with the right contract and synchronization semantics; and how errors, timeouts, retries, and connection lifecycles are observed. Simply testing a payload transformation function is not enough to prove that the adapter works.

In the *Spring Integration Adapters* module, this lesson ties channel testing to **file, SFTP, HTTP, JMS, AMQP, Kafka, and database** adapters, following the structure of inbound/outbound, gateway, poller, MessageChannel, message contract, errors, and lifecycle.

Goals:

- Distinguish **unit testing logic**, **channel/flow testing**, **adapter testing**, and **integration testing with an isolated real external system**.
- Choose appropriate observation points for `DirectChannel`, `QueueChannel`, `PublishSubscribeChannel`, and asynchronous channels.
- Write JUnit 5 tests covering payload, headers, routing, reply, and error handling.
- Test pollers, file filters, retries, duplicates, timeouts, and transaction boundaries.
- Verify side effects at the destination rather than merely seeing `send()` succeed.
- Make tests **have bounded timeouts, not depend on stale data, and run reliably in CI**.

> Examples focus on Spring Integration Java DSL, JUnit 5, and conceptually stable APIs in modern Spring Integration releases. Cross-check the exact version in use to select the right modules, overloads, and endpoint configurations; test snippets illustrating an isolated boundary explicitly note the required fixtures.

## 2. Visualizing the Message Path

~~~mermaid
flowchart LR
    SRC["File / SFTP / HTTP / JMS / AMQP / Kafka / DB"] --> IN["Inbound adapter or gateway"]
    IN --> IC["inputChannel"]
    IC --> LOGIC["Filter / transform / route / handle"]
    LOGIC --> OC["outputChannel"]
    OC --> OUT["Outbound adapter or gateway"]
    OUT --> DEST["Target system"]
    LOGIC -. "error" .-> ERR["errorChannel / retry / DLQ"]
~~~

There are four different levels of evidence:

| Question | Checkpoint | Required Evidence |
|---|---|---|
| Was the source read properly? | External system and inbound adapter | File/record/request received, filter valid |
| Did the message enter the flow properly? | Input channel | Payload/headers/message type match contract |
| Did the flow process properly? | Output channel or reply | Routing, transformation, correlation, exception |
| Did the target system receive the result? | Outbound adapter and target system | File created, HTTP request, broker record, DB row |

For example, a message appearing on the output channel **does not prove** that an FTP/SFTP upload succeeded; a message sent to the input channel **does not prove** that the broker consumer processed the business logic. Every test must explicitly state what level it proves.

## 3. Distinguishing Channels Before Testing

| Channel | Semantics | Appropriate Observation Approach |
|---|---|---|
| `DirectChannel` | `SubscribableChannel`, typically dispatches synchronously on the sender's thread to a selected subscriber | Attach a handler/test endpoint, assert after `send()` when the flow is synchronous |
| `QueueChannel` | `PollableChannel`, stores messages for a consumer to call `receive(timeout)` | Inspect output from the queue with a timeout |
| `PublishSubscribeChannel` | Broadcasts to multiple subscribers; can be synchronous or executor-backed | Assert each subscriber, fan-out, and behavior when one subscriber fails |
| `ExecutorChannel` | Dispatches via an executor, no longer synchronous on the caller's thread | Use a latch or await until an observable state is reached |
| `RendezvousChannel` | Rendezvous between sender and receiver | Verify pairing and timeout behavior on both sides |
| `PriorityChannel` | Orders messages by priority | Assert priority ordering and tie-breaking policy |
| `FluxMessageChannel` | Reactive stream with subscription and backpressure | Use reactive testing tools; do not expect pollable `receive()` |

**Very common pitfall:** `DirectChannel` is not pub/sub. If there are two subscribers, by default **both will not receive the same message**. If a test requires multiple parties to observe the message, use a proper fan-out channel or a secondary observation mechanism such as a wire tap.

When replacing a production `DirectChannel` with a `QueueChannel` in a test, synchronous semantics, exception handling, and transactions can change. Be clear that this is a **test harness**, and do not use its results to claim all end-to-end behavior matches production.

## 4. Designing the Message Contract

In Spring Integration, a message has a **payload** and **headers**. The contract must describe both:

| Property | What to Test |
|---|---|
| Payload type | `File`, `String`, `byte[]`, DTO, key/value... |
| Schema and encoding | UTF-8 CSV, JSON, date/time, required fields |
| Business identity | `eventId`, `orderId`, `correlationId` |
| Routing | `eventType`, `sourceSystem` headers, processing target |
| Transport metadata | File name, remote path, broker key/partition, HTTP status |
| Reply | Request–reply result, headers, and timeout |
| Error | Exceptions, `errorChannel`, retry or reject |
| Delivery | Possible duplicates, idempotency key, ack/commit |
| Security | No tokens/passwords leaked in payload, logs, or exchanged headers |

**Do not use framework-generated `MessageHeaders.ID` as a durable business ID across multiple endpoints**: new messages may receive different IDs. Use a dedicated correlation/business key when reconciliation across adapters is required.

The contract should distinguish **headers guaranteed to be created by the adapter**, **configuration-dependent headers**, and **business headers set by the flow itself**. Tests should not rely on a transport header that is not documented as stable.

## 5. Multi-Layer Testing Strategy

| Layer | What Runs? | What Does It Prove? |
|---|---|---|
| Unit | Pure mappers, transformers, filters, routers | Isolated logic and data error cases |
| Channel/flow | Lightweight Spring context with channels and endpoints | Wiring, routing, payload/headers, error flow |
| Adapter contract | Adapter + filesystem, test server, or test double | Message/protocol mapping, source/target interaction |
| Integration | SFTP/JMS/AMQP/Kafka/DB test infrastructure | Ack, retry, offset/transaction, reconnect, side effects |
| End-to-end | Full chain from source to target in an isolated environment | Business outcomes and cross-adapter observability |

A `Mockito.verify(sender)` test can prove that a handler called its collaborator, but it **does not** prove that RabbitMQ/Kafka actually received the record. Conversely, spinning up a real cluster for every unit test slows down the suite and makes failure localization harder. Use each layer for its specific risk.

## 6. Example 1 — Testing Channels and Transformers with JUnit 5

This tests the **internal channel contract** into which an inbound adapter can send messages. It intentionally excludes file/SFTP so the test runs fast and pinpoints the root cause of failures.

Spring configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
class ChannelContractConfig {

    @Bean
    MessageChannel adapterInput() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel observedOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow normalizeFlow() {
        return IntegrationFlow.from("adapterInput")
                .<String, String>transform(String::trim)
                .channel("observedOutput")
                .get();
    }
}
~~~

JUnit 5 test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ChannelContractConfig.class)
class ChannelContractTest {

    @Autowired
    @Qualifier("adapterInput")
    MessageChannel adapterInput;

    @Autowired
    @Qualifier("observedOutput")
    PollableChannel observedOutput;

    @Test
    void preservesHeadersAndTrimsPayload() {
        Message<String> input = MessageBuilder
                .withPayload("  order-42  ")
                .setHeader("sourceSystem", "sftp")
                .setHeader("correlationId", "corr-42")
                .build();

        assertTrue(adapterInput.send(input));

        Message<?> result = observedOutput.receive(1000);
        assertNotNull(result);
        assertEquals("order-42", result.getPayload());
        assertEquals("sftp", result.getHeaders().get("sourceSystem"));
        assertEquals("corr-42", result.getHeaders().get("correlationId"));
        assertNull(observedOutput.receive(50));
    }
}
~~~

This test proves the `adapterInput → transform → observedOutput` flow and preservation of business headers. It **does not** prove that SFTP downloaded the file or that the outbound adapter wrote the result at the destination. The test fails if there is no matching subscriber/endpoint or if the transformer violates the contract.

### 6.1. Channel Without Subscribers

A `DirectChannel` without subscribers cannot deliver messages. Depending on position and configuration, calling `send()` may throw `MessageDeliveryException`; do not write tests that merely assert `send() == false` and assume all failure cases share the same semantics.

### 6.2. Observing via Queue and Avoiding Races

`QueueChannel.receive(timeout)` is a good observation point for a test, but **no other consumer may be draining the same queue**. If a competing consumer or poller is present, the message might be processed validly while the test receives `null` and reports a false failure. Use a dedicated output queue for the test, or attach a handler/spy to the appropriate endpoint.

## 7. Example 2 — Testing FileReadingMessageSource

A file inbound source maps files from a directory into messages containing a `File` object. This tests closer to the **adapter source**, though without running a scheduler/poller.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.messaging.Message;

class FileReadingSourceTest {

    @TempDir
    Path inputDirectory;

    @Test
    void readsOnlyCsvMatchingTheFilter() throws Exception {
        Files.writeString(
                inputDirectory.resolve("orders.csv"),
                "orderId,total\n42,100\n",
                StandardCharsets.UTF_8
        );
        Files.writeString(
                inputDirectory.resolve("ignore.tmp"),
                "not an order",
                StandardCharsets.UTF_8
        );

        FileReadingMessageSource source = new FileReadingMessageSource();
        source.setDirectory(inputDirectory.toFile());
        source.setFilter(new SimplePatternFileListFilter("*.csv"));
        source.afterPropertiesSet();

        Message<File> incoming = source.receive();

        assertNotNull(incoming);
        assertEquals("orders.csv", incoming.getPayload().getName());
        assertTrue(incoming.getPayload().isFile());
    }
}
~~~

To test **both the inbound adapter and the poller**, create another context containing the flow:

~~~java
// Illustration of declaration in a test @Configuration.
@Bean
IntegrationFlow fileInboundFlow(
        @Value("#{environment['app.test.inbound-dir']}") File inputDir
) {
    return IntegrationFlow.from(
            org.springframework.integration.file.dsl.Files
                    .inboundAdapter(inputDir)
                    .patternFilter("*.csv"),
            e -> e.poller(
                    Pollers.fixedDelay(java.time.Duration.ofMillis(100))
                           .maxMessagesPerPoll(1)
            )
    ).channel("fileMessages").get();
}
~~~

The fixture must provide the `app.test.inbound-dir` property value, the `fileMessages` bean, and the flow lifecycle. Create a file in the test directory, then receive from `fileMessages` with a bounded timeout. Two specific issues must be tested separately:

1. `patternFilter("*.csv")` filters by name; it **does not automatically guarantee accept-once**. To prevent duplicate processing, add an appropriate filter/metadata store and test restarts.
2. An inbound File source may emit a `File` payload, whereas a transformer reading the file content produces `byte[]` or `String`. Assert the payload at the **exact right channel**.

Never use a production directory or stale developer data as a fixture; `@TempDir` keeps tests independent and self-cleaning.

## 8. Example 3 — Verifying Outbound Behavior via Side Effects

Outbound adapters are usually **one-way**: a channel receives a message, and the handler uses it to write a file, upload via SFTP, publish to a broker, or update a database. Simply seeing `send()` succeed is insufficient; you must observe the target system.

Illustrative contract for File outbound:

~~~text
Input:
  payload = "orderId,total\n42,100\n"
  header targetFileName = "orders-42.csv"

Expected side effect:
  file orders-42.csv appears in an isolated output directory
  bytes/encoding content is correct
  existing file is not overwritten if the contract forbids it
  I/O errors are routed to the caller/error flow as configured
~~~

An assertion snippet, assuming the flow provides `outboundInput` and the fixture provides `outputDirectory`:

~~~java
@Test
void outboundFileAdapterCreatesTheExpectedFile() throws Exception {
    Message<String> outgoing = MessageBuilder
            .withPayload("orderId,total\n42,100\n")
            .setHeader("targetFileName", "orders-42.csv")
            .build();

    assertTrue(outboundInput.send(outgoing));

    Path expected = outputDirectory.resolve("orders-42.csv");
    assertTrue(Files.exists(expected));
    assertEquals(
            "orderId,total\n42,100\n",
            Files.readString(expected, StandardCharsets.UTF_8)
    );
}
~~~

**Precondition:** The outbound flow configuration must actually use the `targetFileName` header or equivalent mapping as the filename; this snippet is **just the assertion part**, not a standalone test without declaring the flow/fixture. For asynchronous channels, wait for the side effect with a timeout instead of asserting immediately.

Also test these cases: duplicate filename, directory without write permission, empty/invalid payload, temporary file name, rename after writing, mid-write crash handling, and whether partial files remain.

## 9. One-Way Adapters and Gateways Have Different Contracts

| Endpoint | Direction | What to Test |
|---|---|---|
| Inbound adapter | External system → channel | Incoming data, filters, message headers, poll/ack |
| Outbound adapter | Channel → external system | Side effects, send errors, retries, and target state |
| Inbound gateway | External request → flow → response | HTTP/JMS request mapping, reply, status, and timeout |
| Outbound gateway | Flow → external request → reply message | Correlation, reply payload/status, timeout |
| Messaging gateway | Java method → flow → return value | Method contract, timeout, and exception mapping |

**Do not expect a one-way outbound adapter to send a reply** if the system does not define such a contract. Conversely, a request–reply gateway must test both **missing replies** and expired deadlines.

## 10. Spring Integration Testing Support

The `spring-integration-test` ecosystem provides support for controlling flows and mocking endpoints, such as `@SpringIntegrationTest`, `MockIntegrationContext`, and tools for mocking message handlers in supported versions.

A typical testing approach is:

1. Initialize the Spring test context with the real flow configuration.
2. Prevent inbound endpoints from auto-starting if the test needs manual source control.
3. Replace the **boundary handler** with a mock/spy via test support at the exact endpoint ID, or supply a test double as a dependency.
4. Send a `Message<?>` to the channel/gateway, then assert the arguments or message received by the handler.
5. Restore all replacements in test teardown to avoid polluting the shared context.

Conceptual example:

~~~text
Context:
  inboundSource -> parseFlow -> outboundEndpoint(id=sendToPartner)

In test:
  use MockIntegrationContext to replace outbound handler sendToPartner
  send message to channel parseFlow
  verify mock receives the expected payload/headers
  reset replacements after the test

A separate integration test:
  keeps the real outbound adapter
  points the adapter to a mock HTTP server or test broker
  verifies the actual side effect
~~~

**API note:** the exact method for replacing an endpoint depends on the test-support API and the ID assigned to the endpoint/bean in the version being used. Do not blindly replace the entire flow with mocks and claim the real adapter was tested. For pollers, you can use a test trigger or a dedicated fast poll schedule in tests to avoid depending on wall-clock timing.

## 11. Testing HTTP Inbound/Outbound Gateways

For HTTP outbound gateways, use a mock server (MockWebServer/WireMock or equivalent) and inspect the **actual emitted request**, or `MockRestServiceServer` if the gateway uses the exact `RestTemplate` bound to the mock server.

Example contract:

~~~text
Input message:
  payload: {"orderId":"42","total":100}
  correlationId: corr-42

Expected HTTP request:
  POST /orders
  Content-Type: application/json
  X-Correlation-Id: corr-42

Mock server returns:
  HTTP 201
  {"accepted":true,"externalId":"ext-42"}

Expected reply:
  accepted=true, externalId=ext-42
  correlation/required headers are preserved
~~~

Minimum test cases: HTTP 2xx and proper transformation, 4xx without blind retries, 5xx/network timeout with bounded retry/backoff, malformed response schema, security headers, and content type. For **inbound HTTP**, send a real HTTP request to the endpoint in the test context and observe the input channel and response, rather than calling the transformer directly.

## 12. Testing SFTP with an Isolated Server

SFTP involves concerns that local files do not simulate: SSH authentication, host keys, remote directories, network timeouts, reconnects, partial file uploads, and metadata synchronization. A unit test mocking the session is useful for checking error-handling code, but a test server or SFTP container is needed to verify protocol behavior.

| Case | Expected Result |
|---|---|
| Remote file matches pattern | Synchronized and emits the proper message |
| File currently being uploaded | Not read mid-transfer per temporary name/rename rules |
| Same filename in two paths | Distinguishes paths if required by contract |
| Network drops during poll/upload | Retries, reconnects, and records errors |
| Invalid credentials/host key | Rejected; do not disable host-key verification just to make tests pass |
| Re-poll or restart | Filter/metadata store prevents duplicates as designed |
| Outbound upload | File exists with accurate content on remote, not just `send()` succeeding |

If the architecture uses a **remote-to-local synchronizer** followed by a local inbound file adapter, test both steps. Successful remote synchronization does not guarantee downstream messages have finished processing.

## 13. JMS, AMQP, and Kafka: Using Test Brokers for Delivery Verification

| System | What Only Broker Tests Can Reliably Prove |
|---|---|
| JMS | Session/ack mode, transactions, queue vs topic, selectors, redelivery |
| AMQP/RabbitMQ | Exchanges, bindings, routing keys, publisher confirms/returns, ack/nack, DLQ |
| Kafka | Topics, partitions, record keys, offset commits, group rebalances, per-partition ordering |

A unit test can validate the **payload before the outbound adapter**, but it is insufficient for claims like "the message was published", "the consumer committed", or "a rollback causes redelivery".

For Kafka, important test cases include:

- Producer sends to the right topic, key, and schema.
- Dedicated test consumer group so it does not consume records from other runs; offsets are controlled.
- Consumer error handling, retry/DLT, and idempotency.
- Ordering within **a single partition** by key is preserved per contract, without assuming global topic-wide ordering.
- After the consumer finishes processing, the **side effect at the sink** appears; a producer ack does not prove this step.

For RabbitMQ, test exchanges/bindings/routing keys, confirms, and returning unroutable messages; for JMS, test ack/commit/rollback. **Do not claim end-to-end exactly-once semantics just because the transport supports transactions**: side effects to HTTP, SFTP, or DB still have their own transaction boundaries.

## 14. Database Adapters: Polling, Concurrency, and Transactions

JDBC/JPA polling sources typically read pending records and emit messages. Critical bugs lie in **re-reading records**, **marking records too early**, **two pollers running concurrently**, and **rollbacks not covering expected operations**.

~~~text
orders_outbox:
  id=42, status=NEW, payload=...

Poller:
  find NEW rows
  create message with business id=42
  update status according to transaction strategy

Consumer:
  process order-42
  write side effect to target system
~~~

Tests should cover: one valid record, malformed record, rollback after downstream error, duplicate polling, two instances selecting rows simultaneously, restart, paging/batch limits, and compensating actions when transactions cannot span external systems. If using the outbox pattern, verify writing **business state + outbox record in the same DB transaction**, and separately test that the publisher/consumer handles duplicate reads.

## 15. Testing Error Paths: DirectChannel Differs from Asynchronous Channels

In a **synchronous flow**, errors thrown while a handler processes a message typically propagate back to the caller invoking `send()` or the gateway, unless a dedicated error handler/advice is configured. For **endpoints running on another thread** (pollers, executors, listener containers), errors cannot return to an already-finished caller; the framework and endpoint configuration decide where errors are reported, retried, rejected, or sent as an `ErrorMessage` to an error channel.

| Situation | Expectation to Verify |
|---|---|
| `DirectChannel` → handler throws exception | Caller sees the exception or advice redirects it as configured |
| Polling inbound encounters an error | Exception is handled by the poller/error handler mechanism, not silently lost |
| Flow uses an executor | Error is reported to the configured error channel/recoverer |
| Outbound HTTP returns an error | Distinguishes retryable errors from non-retryable errors |
| Broker listener fails | Ack/nack/requeue/redelivery/DLQ behaves as configured |
| Error flow also fails | Logs/alerts and applies fallback policy; does not swallow errors |
| Poison message | Does not retry infinitely and block valid messages |

Example contract:

~~~text
Payload: invalid CSV record
Message header: correlationId=corr-42

Expected:
  validator reports error with error category
  source info/message ID remains traceable
  error does not write bad data to the DB
  retry occurs only for transient errors
  eventually the message goes to error output/DLQ or is handled per contract
~~~

**Do not assume every error automatically goes to the global `errorChannel` bean.** Handling depends on endpoint type, the `errorChannel` header, poller/listener error handlers, and advices. Tests must verify the **actual active configuration**, rather than assuming having an error channel is enough.

### 15.1. Inspecting ErrorMessage and Source Information

For an error flow configured to emit `ErrorMessage` to a test-dedicated `PollableChannel`, assert:

- The error payload is the expected exception or has the expected root cause.
- `failedMessage` (if provided by the exception component) identifies the right payload/headers/correlation.
- Logs/error messages do not contain passwords, secrets, or unnecessary personal data.
- Failed messages are not simultaneously routed to the success channel, unless the contract explicitly allows compensating handling.

When catching errors, avoid asserting verbatim full stack traces: framework call stacks and messages may differ across versions. Prioritize **error type, cause, error code, and target behavior**.

## 16. Testing Pollers: Timing, Scheduling, and Determinism

Pollers have notable parameters such as trigger, `maxMessagesPerPoll`, `receiveTimeout` (when applicable), transaction, error handler, and task executor. These affect throughput, ordering, error handling, and data polling cadence.

**Mistake:** `Thread.sleep(5000)` followed by checking a flag; if CI is slow, the test is flaky, and if CI is fast, the suite wastes time.

Replace it with event waiting using a bounded timeout. For example, when a flow subscriber uses an executor:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

@Test
void asyncFlowEventuallyDeliversTheMessage() throws Exception {
    CountDownLatch received = new CountDownLatch(1);
    AtomicReference<Message<?>> observed = new AtomicReference<>();

    // testResultChannel is a test-dedicated SubscribableChannel.
    // Must subscribe before sending and clean up the subscriber after the test.
    testResultChannel.subscribe(message -> {
        observed.set(message);
        received.countDown();
    });

    MessageChannel input = asyncInputChannel;
    assertTrue(input.send(
            MessageBuilder.withPayload("order-42").build()
    ));

    assertTrue(received.await(2, TimeUnit.SECONDS));
    assertEquals("order-42", observed.get().getPayload());
}
~~~

This snippet illustrates **only the test body**; `testResultChannel` and `asyncInputChannel` must be provided by a fixture with a real asynchronous flow. In suites sharing a Spring context, remember to **unregister handlers** in teardown or use an isolated context; otherwise tests will see each other's messages.

For inbound file/DB pollers, structure the fixture as follows:

1. Create source data in the test directory/DB.
2. Start the endpoint under test control.
3. Wait for the output channel or side effect with an appropriate timeout.
4. Verify the exact message count and source state.
5. Stop the endpoint and clean up resources, ensuring no poller keeps running into the next test.

### 16.1. Testing Batch Sizes and Poll Cycles

Using `maxMessagesPerPoll(1)` limits the number of messages **per poll trigger**, which does not mean only one message is processed over the entire application lifetime. To test batch counts per cycle, control the trigger or observe at deterministic points rather than relying on scheduler luck.

### 16.2. Verifying Files Are Not Processed Twice

Inbound adapters often combine a file list filter with a metadata store. Tests should cover: a new file → received once; subsequent poll → not duplicated per policy; restart with a persistent metadata store → predictable behavior. If metadata resides only in memory, restarts can alter how files are picked up.

## 17. Retries, Duplicates, and Idempotency

Integration systems frequently exhibit **at-least-once** characteristics at one or more stages: messages get redelivered, pollers re-read rows, consumers crash after a side effect but before ack, or HTTP times out after the server already succeeded.

Distinguish among:

- **Technical retry:** retrying a transient failure (network/503) with bounded attempts and backoff.
- **Redelivery:** broker/adapter re-sends a message because ack/commit has not occurred.
- **Business duplicate:** the same business event ID traverses the system multiple times.
- **Idempotency:** processing the same business ID multiple times yields the desired outcome without unintended side effects.

Minimum test matrix:

| Input or Failure | What to Assert |
|---|---|
| Two messages with the same `eventId` | Do not create two orders if contract requires idempotency |
| HTTP timeout after target wrote data | Retry does not duplicate side effects or triggers reconciliation |
| Transient exception | Bounded retries with backoff and logging |
| Permanently invalid schema payload | Do not retry infinitely; route to error branch |
| Process dies after DB write, before ack | Consumer recovers safely without duplicating data |
| Retries exhausted | Message moves to recoverer/DLQ or is saved for manual handling |

**Be careful with transactions:** a transaction covers only the resources enlisted in it. Do not assume a database rollback will undo an SFTP upload or an HTTP request that already succeeded.

## 18. Testing Concurrency, Capacity, and Ordering

Concurrency can come from channel executors, multiple consumers on the same queue, multiple broker listeners, multi-instance pollers, or partitions. When parallelism is enabled, tests should measure **correct outcomes** rather than locking onto an unintended global ordering.

| Test | What Must Be Decided Upfront |
|---|---|
| Multiple producers sending to the same channel | Does per-producer ordering need to be preserved? |
| Multiple consumers receiving from the same queue | Is it competing-consumer load sharing or broadcast to all? |
| Executor-backed `PublishSubscribeChannel` | Must every subscriber finish before marking as done? |
| Multi-partition Kafka | Per-key/partition ordering or topic-wide ordering? |
| Bounded-capacity channel | When full, does it block, time out, or fail? |
| Slow downstream | How are backpressure and message production rate limited? |
| One consumer throws an error | Do other consumers' messages continue per contract? |

Concurrency tests should use `CountDownLatch` or barriers to start simultaneously, business IDs to count results, and bounded timeouts. Repeated test runs help uncover races, though **passing once does not prove there is no race**.

If a test cares about ordering, pick a path with explicit ordering guarantees. Do not write tests assuming three adapters running across different executors and brokers maintain global ordering.

## 19. Lifecycle: Start, Stop, Restart, Disconnect, Reconnect

Adapters have connection and endpoint lifecycles. A context loading successfully does not prove connection resilience.

Scenarios worth testing:

- **Start:** endpoint starts and begins polling/consuming only when configuration permits.
- **Stop:** endpoint stops accepting new data; thread/session resources are released per framework semantics.
- **Restart:** filters/metadata stores and ack/offsets remain consistent; completed messages are not reprocessed endlessly.
- **Temporary disconnect:** SFTP/broker/server becomes unavailable and then recovers; retry/reconnect/alerting occurs.
- **Expired credentials:** adapter detects and handles authentication failures without bypassing TLS/SSH checks to self-heal.
- **Shutdown while processing:** in-flight work is drained, nacked/requeued, or has state evidence as designed.
- **Cleanup:** tests leave no listeners, ports, threads, connections, or temporary files affecting subsequent runs.

For Spring Integration endpoints supporting lifecycle interfaces like `SmartLifecycle`, you can control start/stop via the appropriate bean/endpoint in an **isolated test context**. Never alter shared endpoints in a production context or other tests just to run a single test.

## 20. WireTap, Interceptors, and Observability

Sometimes you need to observe messages **without changing the primary recipient**. Spring Integration offers mechanisms like `WireTap`, channel interceptors, and observability/metrics components. While useful for measuring message paths, they have limitations:

- A wire tap copies/forwards messages to a side branch; **the observation branch is not the business target**.
- If observation is asynchronous, messages may arrive at the tap after the main flow completes.
- Do not let a test tap hold mutable objects and infer that the payload was unmodified; use immutable payloads or copy when needed.
- Do not treat the tap seeing a message as proof that an external outbound call succeeded.
- Limit log content: messages may contain PII, tokens, or secrets; inspect appropriate metadata instead of dumping sensitive payloads in full.

A useful test can verify: the inbound message carries `correlationId`, the transformer preserves correlation, the error flow logs the same business ID, and the outbound request passes the identifier in the appropriate header.

~~~mermaid
flowchart TD
    A["Inbound adapter"] --> C["inputChannel"]
    C --> T["Transformer / handler"]
    C -. "WireTap" .-> OBS["Observability channel"]
    T --> O["outboundChannel"]
    O --> X["External target"]
    X --> VERIFY["Assert side effect at target"]
    OBS --> EVIDENCE["Test trace/header assertion"]
~~~

## 21. Designing Test Infrastructure and Isolated Data

Common choices:

| Dependency | Appropriate Fixture |
|---|---|
| File adapter | `@TempDir` or dedicated temporary directory |
| HTTP | Mock server on a random port, request log |
| SFTP | Test SFTP server/Container with dedicated user and host key |
| JMS | Embedded/test broker if appropriate, or container broker |
| AMQP/RabbitMQ | RabbitMQ container, isolated exchange/queue |
| Kafka | Kafka container/embedded broker, dedicated topic and consumer group |
| SQL/DB | Testcontainers database or test DB with transaction/isolation |
| Secret/config | Test credentials, never production secrets |

**Testcontainers** generally tests protocol/broker versions closer to real environments than mocks, but requires managing container readiness, dynamic ports, lifecycle, and cleanup. Use independent queue/topic/schema/consumer group names—optionally prefixed by test run—to avoid collisions across parallel tests.

For brokers or databases persisting across multiple test methods, clean up queues/records/offsets or create a fresh namespace. Never treat leftover messages from a previous run as proof that the current flow works.

### 21.1. When to Use @SpringBootTest?

- Use a small Spring context, such as `@SpringJUnitConfig`, when testing a single flow/channel; it is fast and avoids unexpected auto-configuration.
- Use `@SpringBootTest` when verifying actual application wiring/auto-config, while cleanly isolating external resources.
- Use `@SpringIntegrationTest` and test support when you need to control inbound endpoints or mock handlers/triggers as supported by your version.
- Use `@DirtiesContext` when a test intentionally mutates bean/lifecycle state such that the context cannot be safely reused; avoid overusing it when cleaner fixture resets exist.

## 22. Test Matrix by Adapter Type

| Adapter | Happy Path | Negative Path | Lifecycle / Reliability |
|---|---|---|---|
| **File inbound** | Reads correct filename and payload | Invalid pattern/encoding file | Accept-once, rename, restart |
| **File outbound** | Creates file with right name/content | Invalid path, write denied | Atomic write/temp file policy |
| **SFTP inbound** | Downloads file and emits message | Auth failure, missing remote path | Retry, reconnect, metadata |
| **SFTP outbound** | Uploads to right remote path | Connection drops mid-upload | Partial file, retry, dedup |
| **HTTP inbound gateway** | Request → channel → response | Invalid body, missing header | Timeout, concurrency |
| **HTTP outbound gateway** | Real request sent, valid reply | 4xx/5xx/timeout | Backoff, idempotency |
| **JMS inbound/outbound** | Send/receive and header mapping | Handler failure, invalid payload | Ack, rollback, redelivery |
| **AMQP/RabbitMQ** | Exchange routes to queue | Unroutable, consumer reject | Confirm, DLQ, reconnect |
| **Kafka** | Correct topic/key/schema | Deserialization, poison record | Offset, replay, rebalance |
| **JDBC/JPA polling** | Selects and maps rows properly | DB outage, wrong status | Lock, tx, parallel poll |
| **Service gateway** | Correct method–message–reply | Missing reply, converter failure | Timeout and exception mapping |

Pick **the columns that actually impact business logic**. For instance, a channel ingesting CSV files with **at-least-once** reliability must prioritize duplicate and idempotency testing over asserting a framework timestamp.

## 23. Case Study: File Inbound → Data Validation → HTTP Outbound

Suppose an application picks up order files from a partner-synced directory, validates their contents, and calls a shipping system's HTTP API.

**Proposed contract:**

~~~text
Input:
  order-42.csv, UTF-8 encoding, schema orderId,total
  orderId=42,total=100

Flow:
  file inbound poller
    -> fileInputChannel
    -> file-to-text/CSV parser
    -> validator
    -> validOrderChannel
    -> HTTP outbound gateway
    -> reply/result channel

Error:
  invalid input -> rejectedOrderChannel
  transient HTTP failure -> retry policy
  exhausted retry -> recovery queue/record with reason

Business rule:
  orderId is the idempotency key
  reprocessing the same orderId does not create a second shipment
~~~

Ordered test plan:

1. **Parser unit test:** valid CSV / missing column / invalid encoding; proper error types.
2. **Channel contract test:** message from `fileInputChannel` preserves source filename and correlation; DTO has the expected type on `validOrderChannel`.
3. **File inbound test:** create temporary file; poller emits message; filter skips invalid filenames; verify duplicate filter.
4. **HTTP gateway test:** mock server receives expected JSON and idempotency/correlation headers; 201 response is mapped to result.
5. **Negative test:** file missing `orderId` does not call HTTP; error takes the rejected branch.
6. **Retry test:** server returns 503 then 201; call count matches policy without infinite retries; 400 is not retried if dictated by business rules.
7. **Replay test:** same `orderId` processed twice; if the gateway/target supports idempotency, only one shipment is created.
8. **Restart test:** stop after the file has been seen but before completion; verify retry/recovery and status metadata.
9. **End-to-end test:** from an actual file in the test directory to the mock server record and business outcome; assert both **internal messages and external side effects**.

A good way to present test results:

| Case | What Did the Channel See? | What Did the Target Record? | Conclusion |
|---|---|---|---|
| Valid file | `OrderCreated(42)` | One valid POST | PASS |
| Invalid CSV | Error message with source ID | No POST | PASS |
| HTTP 503 → 201 | Retry/error message per policy | Two requests, one valid result | PASS if matching contract |
| Duplicate order | Input received twice with same business ID | Does not create two shipments | PASS |
| Adapter disconnect | No bad data sent | Alerts/retries, recovers | PASS if per policy |

Do not mark "duplicate" as `PASS` just because the queue received two messages; that could itself be the bug if the contract requires an idempotent outcome.

## 24. Anti-Patterns in the Tests Themselves

| Testing Anti-Pattern | Why It Produces False Results |
|---|---|
| Asserting `channel.send() == true` and concluding outbound succeeded | Does not check the target system or reply |
| Using fixed `Thread.sleep` | Flaky depending on CPU/CI and poller scheduling |
| Replacing all channels with `QueueChannel` | Changes synchronization, exception, and transaction boundaries |
| Mocking adapter, broker, parser, and handler all in one test | Leaves no real integration to verify |
| Sharing directories/topics/queues across tests | Leftover messages or files cause false passes |
| Asserting call counts immediately in async flows | Race condition between assertion and consumer |
| Skipping error and retry tests | Happy path hides duplicates, poison messages, timeouts |
| Comparing entire `MessageHeaders` | ID/timestamp headers change outside the business contract |
| Disabling TLS/SSH verification in fixtures for convenience | Skips security controls required in production |
| Failing to clean up endpoints/threads/subscribers | Subsequent tests receive stray messages or leak resources |
| Skipping restart/transaction tests | Lacks evidence for process crashes or reconnects |
| Using production data/secrets | Unnecessary operational and security risk |

## 25. Acceptance Checklist for an Adapter Channel Test

- [ ] Identified whether this is an inbound adapter, outbound adapter, or gateway.
- [ ] Know whether the channel is subscribable/pollable, synchronous or asynchronous.
- [ ] Payload/header/correlation contract is explicitly documented.
- [ ] Test uses isolated data with setup/teardown.
- [ ] Tests cover both valid and invalid messages.
- [ ] Chose the right **observation point** (channel, handler, reply, or external system).
- [ ] Outbound tests assert real side effects on mock server/broker/filesystem/DB.
- [ ] Inbound tests assert source consumption and message emission.
- [ ] Poller timing is controlled without relying on arbitrary sleeps.
- [ ] Timeouts are bounded with helpful failure messages.
- [ ] Retries, duplicates, idempotency, and DLQ/recovery are tested where required by transport.
- [ ] Transactions/ack/offsets are tested with infrastructure having equivalent semantics when critical.
- [ ] Security headers and sensitive data do not appear in logs.
- [ ] Start/stop/restart/reconnect tested for lifecycle-managed adapters.
- [ ] Cross-flow tests verify the contract between adapter and flow.
- [ ] Coverage notes clearly state **what has been proven and what has not**.

## 26. Self-Assessment Scenario Questions

**Scenario A.** A test calls `inputChannel.send(message)` and it succeeds; the flow has an HTTP outbound adapter. Can we conclude the partner API received the order?

**Answer:** No. You need to verify that the target/mock HTTP server received the request and returned the expected status or produced the corresponding side effect. `send()` only proves behavior up to the channel/handler according to the flow's semantics.

**Scenario B.** A test author replaces `DirectChannel` with `QueueChannel` to call `receive()` easily. Runtime errors then disappear. What can we conclude?

**Answer:** Synchronous semantics and exception/transaction boundaries may have changed. Keep at least one integration test with the production topology, and only use a queue as a controlled observation point.

**Scenario C.** A File inbound test uses `patternFilter("*.csv")`; the next poll receives the same file again. Is this definitely a Spring Integration bug?

**Answer:** No. Pattern filtering does not automatically imply accept-once. Check the file list filter, metadata store, and post-read processing strategy.

**Scenario D.** A Kafka producer gets a broker ack, but the consumer fails while writing to the database. Does the producer test prove the order was processed?

**Answer:** No. Broker ack and DB side effects are two separate points; you must test the consumer and transactions/idempotency.

**Scenario E.** A poller reads the same DB row twice when two instances run; the handler sends two emails to the customer. What controls need testing?

**Answer:** Distribution/locking/transactions and idempotency by business key—not just the happy-path SQL query.

**Scenario F.** An adapter receives a schema-invalid payload on a poller thread. The earlier request caller receives no exception. Can we conclude the error was lost?

**Answer:** Not yet. With asynchronous processing, inspect the error handler/error channel, logs, retries, or DLQ; do not expect exceptions to necessarily return to the original calling thread.

**Scenario G.** An SFTP integration test is stable locally but flaky in CI. Should we increase `Thread.sleep(60000)`?

**Answer:** Do not treat long sleeps as the primary fix. Check server readiness, poller lifecycle, bounded timeouts, metadata filters, races, and isolation; wait on observable conditions.

**Scenario H.** An outbound file test detects a file from a previous run and passes, even though the current handler is disconnected. What needs improvement?

**Answer:** Use an isolated `@TempDir`, ensure output is empty before the test, generate unique IDs/filenames, and assert content, count, and metadata strictly for the current run.

## Conclusion

**Adapter channel testing** in Spring Integration is about testing **the message contract and delivery mechanics at the boundary between external systems and internal flows**, rather than merely asserting a `send()` call. A reliable strategy combines **payload unit tests**, **channel/flow tests**, **adapter contract tests**, and **integration tests using isolated real protocols**. Choose observation points tailored to `DirectChannel`, `QueueChannel`, and asynchronous channels; verify pollers, headers/correlation, errors/retries, duplicates, transactions, and lifecycles. Only when tests verify both **messages taking the right path** and **the target system recording the right outcome** do file, SFTP, HTTP, JMS, AMQP, Kafka, and database flows have solid operational evidence instead of just "working on the happy path".

# MockIntegrationContext: Isolating Endpoints When Testing Spring Integration

In **Spring Integration**, a flow receiving data from an external system typically passes through `MessageChannel`s, transformers, routers, filters, and one or more adapters/gateways. Testing the entire flow against a real SFTP server, HTTP service, JMS/AMQP broker, Kafka, or database can be slow and hard to diagnose. However, if you only test pure Java functions, you still do not know **whether Spring wired the endpoints to the right channels, whether message headers are preserved, and whether the flow routes to the intended external system boundary**.

**`MockIntegrationContext`** is a **Spring Integration Test** utility that allows temporarily substituting the **message handler** or **message source** on an endpoint inside an initialized Spring application context. As a result, the test preserves most of the integration flow structure while actively blocking side effects at the boundary or simulating data entering the flow.

This lesson belongs to the **Testing** chapter of the `SPRING_INTEGRATION_ADAPTERS` module, focusing on connecting to external systems via **inbound/outbound adapters, gateways, pollers, and MessageChannels**. The examples focus on using `MockIntegrationContext` safely, verifying message contracts and errors, and understanding the limits of mocks when systems involve File, SFTP, HTTP, JMS, AMQP, Kafka, or JDBC.

> **Key takeaway:** replacing a handler with a mock proves that the message reached the *simulated integration point*, not that the target system actually received, persisted, or acknowledged processing the message. To prove external side effects, you need adapter tests against the appropriate transport.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain why `MockIntegrationContext` is suited for **integration flow isolation tests**, not as a tool to emulate an entire server/broker.
2. Distinguish **`MessageHandler`**, **`MessageSource`**, **`MessageChannel`**, and **endpoint lifecycles**.
3. Initialize a test context with `@SpringIntegrationTest` and inject the `MockIntegrationContext` bean.
4. Use `substituteMessageHandlerFor(endpointId, handler)` to temporarily replace an outbound or service-activator handler.
5. Use `substituteMessageSourceFor(endpointId, source)` to control input data for an inbound polling endpoint.
6. Manage `noAutoStartup`, `start()`, `stop()`, and `resetBeans()` so tests do not interfere with each other.
7. Verify payloads, headers, routing, retries, synchronous/asynchronous errors, and invocation counts using JUnit/Mockito or a message probe.
8. Identify endpoint ID mistakes, missing replies, poller loops, shared state, mocking the wrong boundary, and cases where a real server/broker is required.

## 2. Where Does MockIntegrationContext Sit in the Test Architecture?

~~~mermaid
flowchart LR
    EXT["External source<br/>SFTP / File / Kafka / HTTP"] --> IN["Inbound endpoint<br/>MessageSource or handler"]
    IN --> C1["Input MessageChannel"]
    C1 --> LOGIC["Filter / Transform / Route / Service"]
    LOGIC --> C2["Output MessageChannel"]
    C2 --> OUT["Outbound endpoint<br/>MessageHandler"]
    OUT --> TARGET["Server / Broker / Database"]
    MOCK["MockIntegrationContext"] -. "Replace source" .-> IN
    MOCK -. "Replace handler" .-> OUT
~~~

When **mocking an inbound source**, the test actively feeds messages into the flow instead of downloading SFTP files or polling a real database. When **mocking an outbound handler**, the test captures/inspects outgoing messages without calling a real API/broker.

**Important point:** `MockIntegrationContext` does not "wipe out" Spring configuration. The remaining channels, transformers, routers, and endpoints remain active in the application context. Therefore, it is ideal for verifying **integration flow wiring** within the isolated scope.

### 2.1. Distinguishing the Components

| Component | Role | Which API Replaces It? |
|---|---|---|
| `Message<?>` | Holds payload and headers | Build test messages using `MessageBuilder`. |
| `MessageChannel` | Transports messages to subscribers or queues | Not a direct target for `substituteMessageHandlerFor`. |
| `MessageHandler` | Receives and processes a message | `substituteMessageHandlerFor(...)` on a compatible endpoint. |
| `MessageSource<?>` | Supplies messages when polled | `substituteMessageSourceFor(...)` for a compatible inbound polling endpoint. |
| `EventDrivenConsumer` | Endpoint consuming messages from a subscribable channel | Can host a replaceable message handler. |
| `PollingConsumer` | Endpoint polling a pollable channel then invoking a handler | Can host a replaceable message handler; mind the poller lifecycle. |
| `SourcePollingChannelAdapter` | Endpoint polling a message source and sending to a channel | Can replace the configured message source on the endpoint. |
| `IntegrationFlow` | Describes a chain of endpoints and channels | Cannot replace an entire flow with a single substitute call. |

The identifier `endpointId` is the **integration endpoint ID** registered by Spring Integration—not necessarily the channel name, adapter factory name, or Java variable name. This is the most common mistake when starting with `MockIntegrationContext`.

## 3. Choosing Correctly Between Unit, Flow, and Transport Tests

| Test Type | Creates Spring Context? | Uses MockIntegrationContext? | What Is Proven |
|---|---|---|---|
| **Unit test** | Usually no | Not needed | Pure Java transformers, validators, routers work properly. |
| **Flow isolation test** | Yes, small context | Very suitable | Channel wiring, message contracts, routing branches, delivery to endpoint. |
| **Mock outbound boundary** | Yes | Yes | Flow constructs the right message before sending externally. |
| **Controlled inbound source** | Yes | Yes | Flow reacts properly to simulated messages from the source. |
| **Transport integration test** | Yes | Usually do not mock the transport under test | Real HTTP requests, SFTP transfers, broker commit/ack, JDBC transactions. |
| **End-to-end test** | Yes | Avoid mocking the path to be proven | Effects across multiple systems and final state. |

For example: verifying that an `ORDER_CREATED` event is converted into valid JSON with a `tenantId` header and sent to the outbound Kafka handler deserves a **flow isolation test**. However, verifying Kafka topic, key, partition, serializer, acknowledgment, and actual delivery requires a **Kafka integration test** against a test broker.

Do not dismiss isolation tests as "fake tests." They verify a valuable boundary—**what command the flow produces, where it goes, and with what data**—provided you explicitly state what is and is not covered.

## 4. Libraries and Dependencies

`MockIntegrationContext` belongs to the `spring-integration-test` module; commonly used imports:

~~~java
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
~~~

Supporting test tools typically paired with it:

- **JUnit Jupiter**: `@Test`, `@BeforeEach`, `@AfterEach`, `@TempDir`, assertions.
- **Spring Test**: `@SpringJUnitConfig`, context caching, and dependency injection for tests.
- **Mockito**: creating fake `MessageHandler`s, verifying call counts, capturing arguments.
- **Spring Messaging**: `Message`, `MessageHandler`, `MessageBuilder`.
- **Spring Integration Core**: `DirectChannel`, `QueueChannel`, `IntegrationFlow`, and pollers.

### 4.1. Maven

When the project uses compatible Spring Boot dependency management/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

### 4.2. Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")
    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

These dependency examples assume **a BOM or version management mechanism is already configured**. Otherwise, the project must declare versions compatible with the Spring Framework/Spring Integration release in use. APIs and imports may vary by version; verify compatibility against your project's source when upgrading.

**You do not need to add `spring-integration-sftp`, `spring-integration-kafka`, or `spring-integration-jms` just to use `MockIntegrationContext`**. Only include adapter modules that the flow actually uses; real-connectivity tests require appropriate server/broker tooling.

## 5. Initializing MockIntegrationContext

In a Spring-backed test, use `@SpringIntegrationTest` to enable Spring Integration test support and inject the `MockIntegrationContext` bean:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(MyIntegrationConfig.class)
@SpringIntegrationTest
class MyIntegrationFlowTest {

    @Autowired
    MockIntegrationContext mockIntegrationContext;

    @Test
    void canUseMockIntegrationContext() {
        org.junit.jupiter.api.Assertions.assertNotNull(
                mockIntegrationContext);
    }
}
~~~

`@SpringIntegrationTest` does not automatically turn every external adapter into a mock. Only when a test **explicitly substitutes** a compatible endpoint is its handler/source behavior replaced. Other endpoints may still start or call external systems as configured.

### 5.1. Why You Should Use a Small Context

A production project can start dozens of inbound polling adapters or listeners when loading the full application context. For flow isolation tests:

1. Import only the beans needed for the flow and their dependencies.
2. Prevent auto-starting endpoints that might read data or write externally.
3. Assign **explicit endpoint IDs** to points slated for substitution.
4. Prepare mocks, inputs, and outputs before triggering the flow.
5. Clean up state after each test.

If a test must load the full app context, guard it with test profiles, lifecycle settings, resource isolation, and restricted credentials so it never accidentally connects to production.

## 6. Two Core APIs

| API | Meaning | Scenario |
|---|---|---|
| `substituteMessageHandlerFor(String endpointId, MessageHandler handler)` | Replaces the handler of a matching endpoint with a test object. | Intercept outbound HTTP/Kafka/SFTP or inspect messages after a transformer. |
| `substituteMessageSourceFor(String endpointId, MessageSource<?> source)` | Replaces the message source used by a polling inbound endpoint to fetch data. | Replace File/DB/SFTP reading with a deterministic test data source. |
| `resetBeans()` | Restores substituted beans/endpoints in the test context per the utility's mechanism. | Call in teardown so subsequent tests do not inherit stale substitutions. |

**Do not assume substitution always "replaces everything with the same ID."** This mechanism operates on a **specific endpoint** whose handler/source type is supported by the framework. If you choose the wrong ID or an endpoint that does not support substitution this way, the test must fail clearly; never catch the exception and pretend the flow was isolated.

### 6.1. About `MockIntegration`

Spring Integration Test also includes `MockIntegration` to build mocks/spies tailored for message handlers/sources according to the capabilities of your version. However, **`MockIntegrationContext` is not restricted to mocks created by `MockIntegration`**: any object implementing the appropriate `MessageHandler` or `MessageSource<?>` interface works in tests.

Mockito is usually enough when verifying invocation counts and payloads. A custom handler is better when collecting messages into a test queue; a custom source is useful when emitting a sequence of messages followed by `null`. Pick the clearest approach for your test condition.

## 7. Endpoint ID: Prerequisite for Accurate Substitution

Suppose a flow goes from the `ordersInput` channel to an outbound endpoint:

~~~java
@Bean
IntegrationFlow outboundFlow(DirectChannel ordersInput) {
    MessageHandler realHandler = message -> {
        throw new IllegalStateException(
                "Real outbound must not be called in test");
    };

    return IntegrationFlow.from(ordersInput)
            .transform(String.class, String::trim)
            .handle(realHandler,
                    endpoint -> endpoint.id("orderOutboundEndpoint"))
            .get();
}
~~~

Above, `orderOutboundEndpoint` is the **endpoint ID** allowing the test to target handler substitution; `ordersInput` is the channel. DSL overloads for handlers or component naming may vary across versions; the essential part is **assigning an explicit ID to any substitutable endpoint**.

### 7.1. Commonly Confused Identifiers

| Name | Object | When to Use? |
|---|---|---|
| `ordersInput` | `DirectChannel` bean | Send messages into the flow. |
| `orderOutboundEndpoint` | Consumer endpoint ID | Pass to `substituteMessageHandlerFor`. |
| `orderOutboundHandler` | Handler bean name if explicitly named | Used for bean wiring/inspection, **not implicitly the endpoint ID**. |
| `ordersOutput` | Test `QueueChannel` | Receive messages for assertions. |
| `orderOutboundFlow` | `IntegrationFlow` bean name | Identifies the flow, **not implicitly a child endpoint's ID**. |

When an adapter is registered via annotations, XML, or Java DSL, default ID rules can differ. In tests using substitution, **explicitly define and verify IDs** rather than guessing a framework-generated name.

## 8. Complete Example: Mocking an Outbound MessageHandler

Let's build a flow that accepts order ID strings, trims extra whitespace, and forwards them to the outbound boundary. The test must prove the right payload and headers are sent while strictly avoiding real side effects.

### 8.1. Test Flow Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class OutboundTestConfig {

    @Bean
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderOutboundFlow(DirectChannel ordersInput) {
        MessageHandler externalBoundary = message -> {
            throw new IllegalStateException(
                    "Unexpected invocation of real outbound boundary");
        };

        return IntegrationFlow.from(ordersInput)
                .transform(String.class, String::trim)
                .handle(externalBoundary,
                        endpoint -> endpoint.id("orderOutboundEndpoint"))
                .get();
    }
}
~~~

This is a **test flow configuration**: the real handler is represented by a sentinel that throws if invoked. In a real application, the endpoint would wrap a configured HTTP outbound adapter, Kafka sender, JMS sender, or external `MessageHandler`.

### 8.2. Testing with Mockito

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OutboundTestConfig.class)
@SpringIntegrationTest
class OutboundBoundaryTest {

    @Autowired
    MockIntegrationContext mockContext;

    @Autowired
    @Qualifier("ordersInput")
    DirectChannel input;

    @AfterEach
    void restoreEndpoints() {
        mockContext.resetBeans();
    }

    @Test
    void shouldDeliverTransformedMessageToBoundary() {
        MessageHandler outboundMock = mock(MessageHandler.class);
        mockContext.substituteMessageHandlerFor(
                "orderOutboundEndpoint", outboundMock);

        boolean accepted = input.send(
                MessageBuilder.withPayload("  PO-2048  ")
                        .setHeader("tenantId", "VN")
                        .setHeader("traceId", "test-trace-2048")
                        .build());

        assertTrue(accepted);
        verify(outboundMock, times(1)).handleMessage(
                argThat(message ->
                        "PO-2048".equals(message.getPayload())
                        && "VN".equals(
                                message.getHeaders().get("tenantId"))
                        && "test-trace-2048".equals(
                                message.getHeaders().get("traceId"))));
    }
}
~~~

### 8.3. Interpreting the Results

This test confirms:

1. `ordersInput` is wired to the flow.
2. The transformer normalizes the payload.
3. Business headers `tenantId` and `traceId` survive to the boundary.
4. The outbound endpoint receives **exactly one invocation** in this simple scenario.
5. Side effects of the real handler do not execute during substitution.

This test **does not** confirm:

- Whether the partner's HTTP endpoint returns 200 or 503;
- Whether the JMS/AMQP/Kafka broker persisted the message or committed offsets;
- Whether a real File/SFTP output was created with accurate bytes;
- Whether connection pooling and TLS/host-key verification work;
- Whether production connector transactions or retries function.

Because `DirectChannel` dispatches synchronously on the same thread when handled inline, Mockito assertions can run right after `send()` in this flow. If an executor/async boundary is present, wait via timeout/latch instead of verifying immediately.

## 9. Alternative: Using a Custom Handler to Capture Messages

Mockito is not always required. A simple handler can record messages for the test to inspect:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

class RecordingMessageHandler implements MessageHandler {

    private final BlockingQueue<Message<?>> received =
            new LinkedBlockingQueue<>();

    @Override
    public void handleMessage(Message<?> message) {
        received.add(message);
    }

    Message<?> awaitMessage(long timeoutMillis)
            throws InterruptedException {
        return received.poll(timeoutMillis,
                java.util.concurrent.TimeUnit.MILLISECONDS);
    }
}
~~~

In the test:

~~~java
RecordingMessageHandler recorder = new RecordingMessageHandler();
mockContext.substituteMessageHandlerFor(
        "orderOutboundEndpoint", recorder);

input.send(MessageBuilder.withPayload(" PO-99 ").build());
Message<?> observed = recorder.awaitMessage(1_000);
assertNotNull(observed);
assertEquals("PO-99", observed.getPayload());
~~~

The advantage of `BlockingQueue` is that it supports testing **asynchronous** flows using bounded waits. Never use a shared static queue across tests; create a fresh recorder each time and ensure no stray messages remain from earlier scenarios.

### 9.1. Verifying Invocation Counts and Duplicates

To verify a handler does not receive a second message:

- For synchronous flows, `verify(..., times(1))` after operations finish is sound.
- For async flows, determine **the completion condition of the entire flow**; immediate verification can yield false passes.
- In pollers, a source will emit multiple messages if it does not return `null` after the first one.
- When the design assumes at-least-once delivery, physical delivery counts may exceed one; verify that **business side effects are not duplicated outside policy**, rather than always demanding a single physical delivery.

## 10. Testing When Outbound Should Not Be Called

`MockIntegrationContext` is equally useful for negative tests. Suppose a filter rejects messages missing `tenantId`, and we want to prove they **never reach the outbound boundary**.

~~~text
Given: message missing tenantId
When:  sent to input channel
Then:  filter rejects or routes to error path per policy
And:   outbound mock receives no message
And:   error handling evidence exists if required by flow
~~~

Do not write only:

~~~java
// Insufficient if async processing is still running!
verify(outboundMock, times(0)).handleMessage(
        org.mockito.ArgumentMatchers.any());
~~~

A "never received" assertion requires **a sufficiently strong observation checkpoint**. In synchronous flows with filters, `send()` returning/completing can serve as that point. In async flows, wait for a terminal signal, error event, drained test event queue, or an explicitly justified bounded observation window.

## 11. Substituting MessageSource for an Inbound Poller

`MessageSource<?>` represents the **message supplier** for a polling adapter. `MockIntegrationContext.substituteMessageSourceFor(...)` is particularly useful when you want to keep downstream processing intact without reading real files or querying a DB.

### 11.1. A Controllable Test Source

~~~java
import java.util.ArrayDeque;
import java.util.Queue;
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;

final class QueueBackedMessageSource<T>
        implements MessageSource<T> {

    private final Queue<Message<T>> messages =
            new ArrayDeque<>();

    void add(Message<T> message) {
        messages.add(message);
    }

    @Override
    public Message<T> receive() {
        return messages.poll(); // null = temporarily no data
    }
}
~~~

In the test:

~~~java
QueueBackedMessageSource<String> source =
        new QueueBackedMessageSource<>();

source.add(MessageBuilder.withPayload("orders-001.csv")
        .setHeader("sourceSystem", "SFTP")
        .build());

mockContext.substituteMessageSourceFor(
        "filePollingEndpoint", source);
~~~

Here `filePollingEndpoint` must be the ID of an **inbound polling adapter** that supports source substitution. If the endpoint expects a `File` payload, supplying a `String` may break downstream transformers. **The mock must honor the real adapter's payload/header contract**, unless the test intentionally exercises an invalid-data branch.

### 11.2. Why Must the Source Return Null When Exhausted?

A fake source written like this will emit **the same message on every poll cycle**:

~~~java
MessageSource<String> badSource = () ->
        MessageBuilder.withPayload("orders-001.csv").build();
~~~

This might be intentional when testing **duplicate delivery**, but normally it triggers endless repeated messages on the scheduler, making count assertions flaky. Scripted fakes should emit messages sequentially and then return `null`.

### 11.3. Poller IDs and Startup Control

A polling source configuration can be declared with Java DSL:

~~~java
@Bean
IntegrationFlow controlledInboundFlow() {
    MessageSource<String> realSource = () -> null;

    return IntegrationFlow
            .from(realSource, endpoint -> endpoint
                    .id("filePollingEndpoint")
                    .poller(
                            org.springframework.integration.dsl.Pollers
                                    .fixedDelay(500)))
            .channel("fileInput")
            .get();
}
~~~

This example highlights the **placement of the endpoint ID and poller** in the DSL. Spring Integration releases may vary in overloads or builder types; verify the actual signatures in your project. `fileInput` is a channel that must be registered or created by the flow config.

In the test, use:

~~~java
@SpringJUnitConfig(PollingTestConfig.class)
@SpringIntegrationTest(noAutoStartup = "filePollingEndpoint")
class SourceSubstitutionTest {
    // Prepare fake source and output first.
    // Substitute the exact endpoint ID.
    // Explicitly start the endpoint and wait for output.
}
~~~

`noAutoStartup` prevents the specified endpoint from **starting automatically when the context initializes**, avoiding polling the real source before the test attaches its fake. This is crucial for File, SFTP, JDBC, or sources with side effects or watermark/filter state.

## 12. Safe Execution Order for a Polling Endpoint Test

~~~mermaid
flowchart TD
    A["Load test context<br/>poller does not auto-start"] --> B["Prepare fixtures / output channel"]
    B --> C["Create finite MessageSource"]
    C --> D["substituteMessageSourceFor(endpointId, source)"]
    D --> E["Start exact endpoint"]
    E --> F["Wait for message or error<br/>bounded timeout"]
    F --> G["Assert payload/header/correlation"]
    G --> H["Stop endpoint"]
    H --> I["resetBeans + cleanup"]
~~~

A sound workflow:

1. Include the endpoint in `noAutoStartup` or keep it stopped before substitution.
2. Create clean test data; use isolated namespaces for filesystems/DBs.
3. Build a finite `MessageSource` without shared state across tests.
4. Call `substituteMessageSourceFor` with the exact ID.
5. Start the **registered endpoint bean**—do not guess and try starting a channel or handler bean.
6. Receive output on a `QueueChannel` or equivalent observation point.
7. Assert expected data and processing counts; fail clearly on timeout.
8. Stop the endpoint, accounting for races with an in-flight poll.
9. Call `resetBeans()` and clean up test data/infrastructure.

### 12.1. Accessing the Endpoint Lifecycle

Example showing how to manage lifecycle when the endpoint bean is exposed under its ID:

~~~java
import org.springframework.context.SmartLifecycle;

@Autowired
org.springframework.context.ApplicationContext applicationContext;

void startPollingEndpoint() {
    SmartLifecycle endpoint = applicationContext.getBean(
            "filePollingEndpoint", SmartLifecycle.class);
    endpoint.start();
}

void stopPollingEndpoint() {
    SmartLifecycle endpoint = applicationContext.getBean(
            "filePollingEndpoint", SmartLifecycle.class);
    endpoint.stop();
}
~~~

In some declaration styles, the actual endpoint name or exposed bean may differ. Verify the **generated endpoint ID** in your version's configuration/bean graph rather than assuming every bean shares the factory method name.

### 12.2. Testing a Poller with No Messages

If the fake source always returns `null`:

- The flow must not emit business messages.
- It must not record "successfully processed a file."
- Having no data is normally not an exception.
- The endpoint may continue polling on schedule until stopped.

To prove "no message arrived," define a clear completion/observation condition; `QueueChannel.receive(0) == null` right after startup **does not prove** the scheduler won't emit a message moments later.

## 13. Snapshot/Restore and Why resetBeans() Is Mandatory

A Spring Test `ApplicationContext` can be **cached and reused** across multiple tests. If one test substitutes a handler without resetting, the next test may continue hitting that mock instead of the real adapter, causing **false passes** or hard-to-reproduce bugs.

### 13.1. Simple Teardown

~~~java
@AfterEach
void afterEach() {
    mockContext.resetBeans();
}
~~~

This restores substitutions; it is **not a silver bullet for cleaning every kind of state**. It does not automatically:

- drain leftover messages in `QueueChannel`s;
- delete files on SFTP/filesystems;
- remove database records, Kafka topics, or JMS queues;
- reset state inside singleton application transformers;
- stop an external task executor;
- restore static variables;
- guarantee an async thread has finished.

Tests must manage state and lifecycles themselves. For pollers, stop the endpoint **before** resetting if needed so it never invokes a handler/source mid-swap. For async flows, wait for in-flight work to finish or isolate the context/fixture.

### 13.2. Never Share Mocks Across Tests

Avoid:

~~~java
static MessageHandler sharedHandler = mock(MessageHandler.class);
~~~

If tests run in parallel, verifications on a shared mock can mix invocations. Create a fresh mock/recorder per test, or use isolated fixtures and ensure tests never concurrently mutate the same endpoint in a shared context.

### 13.3. Is `@DirtiesContext` Needed?

`@DirtiesContext` marks the Spring test context to be rebuilt. It helps when a test mutates application state that cannot be safely restored via reset/cleanup. However, rebuilding contexts is expensive and **should not be used to mask forgetting `resetBeans()`**. For normal substitutions, prefer explicit resets and clean fixtures.

## 14. Differences Among Handler Mock, Spy, and Fake

| Type | Behavior | When Appropriate |
|---|---|---|
| **Mock** | Executes no real side effects; verifies invocations | Need to verify the flow sends expected messages and headers. |
| **Spy** | Can invoke real logic while intercepting parts | Observing harmless internal handlers; beware of side effects. |
| **Fake** | Lightweight in-memory implementation | Replacing a `MessageSource` or recorder with deterministic scenarios. |
| **Stub** | Returns canned data/responses per scenario | Request/reply tests, simulated errors, controlled timeouts. |

**Never spy on a real outbound handler that has network side effects** and then be surprised when the test sends emails, publishes to Kafka, or uploads via SFTP. For risky boundaries, use a genuinely isolated mock/fake; spies should only delegate when effects are safely contained.

### 14.1. Simulating Exceptions

~~~java
MessageHandler failingHandler = message -> {
    throw new IllegalStateException("simulated outbound failure");
};

mockContext.substituteMessageHandlerFor(
        "orderOutboundEndpoint", failingHandler);
~~~

If the flow runs synchronously on a `DirectChannel`, the exception may propagate back to `send()` wrapped by Spring Messaging. With pollers, listeners, or executors, errors may route to the endpoint's error handling. **Assertions must follow the flow's actual semantics**; do not assume every exception travels through a channel named `errorChannel`.

## 15. Cases Where Arbitrary Handler Substitution Is Wrong

### 15.1. Outbound Gateways Requiring Replies

An **outbound gateway** receives a request and produces a reply. If you replace the gateway handler with a Mockito `MessageHandler` that sends no reply, the caller may **time out** even when upstream logic works fine.

When testing request/reply:

1. Identify the original handler's responsibility for producing replies, where replies go, and the response type.
2. Choose a fake matching the endpoint's request/reply semantics.
3. Construct a reply with contract-compliant payload/headers, or use reply-capable mock tools supported by your version.
4. Test timeout and error branches separately.
5. Never use a one-way mock to claim a request/reply gateway works.

Pseudocode illustrating the fake's intent:

~~~text
fakeGatewayHandler(request):
    assert request.payload and request.headers
    reply = buildReply(
        payload = {"status": "ACCEPTED"},
        correlation = request.correlation
    )
    sendReplyThroughConfiguredReplyMechanism(reply)
~~~

Each endpoint/gateway has its own reply mechanism; real code must use the handler/gateway API supported by Spring Integration. Do not assume `replyChannel` is always a string channel name or cast it arbitrarily to send.

### 15.2. Polling Handlers with Transactions

If a `PollingConsumer` uses a transaction and the real message handler updates a DB, replacing the handler with a mock **does not prove real business transaction commit/rollback**. That test only verifies a message was polled and passed to the handler boundary; write separate integration tests to verify transactions against the database/broker.

### 15.3. Endpoints with Dedicated Connection Lifecycles

Never use substitution to claim that:

- SFTP sessions automatically reconnect after disconnects;
- HTTP TLS handshakes and certificate validation work;
- Kafka producers/consumers have valid transaction/offset configs;
- JMS session rollback/redelivery behaves properly;
- AMQP ack/nack and publisher confirms work;
- JDBC locks/row claims prevent duplicates when two instances poll together.

These behaviors belong to the **real transport/endpoint** and require dedicated integration tests.

## 16. Testing Related MessageChannels

`MockIntegrationContext` replaces handlers/sources at endpoints; inputs and outputs still rely on real channels:

### DirectChannel

- Dispatches synchronously to the selected subscriber.
- Easy to verify mocks right after `send()` in purely synchronous flows.
- Handler errors can propagate back to the caller.
- With multiple subscribers, understand the dispatcher strategy; do not assume every subscriber receives a copy.

### QueueChannel

- Buffers messages for tests to actively call `receive(timeout)`.
- Useful for observing outputs or error/test branches.
- Messages can linger between tests if a context is shared and not drained.
- `receive(timeout)` returns `null` if no message arrives within the wait window.

### ExecutorChannel

- Introduces an async boundary; `send()` does not prove the handler finished.
- Mockito verifications must pair with latches/awaits with timeouts; ensure executor cleanup.
- Exceptions on worker threads may not return to the caller.

### PublishSubscribeChannel

- Can broadcast messages to multiple subscribers depending on executor and configuration.
- Tests must verify each intended branch; do not assume ordering when async.
- When one subscriber fails, impact on other subscribers depends on dispatcher/error configuration.

**Select production channels for business semantics**, not merely test convenience. Switching an `ExecutorChannel` to a `DirectChannel` in tests to avoid concurrency can blind the suite to real production bugs.

## 17. MockIntegrationContext with File, SFTP, HTTP, Kafka, and Databases

### 17.1. Appropriate Boundary Matrix

| Adapter / Source | What Can Be Substituted to Test? | What Still Requires Transport Tests |
|---|---|---|
| **File inbound** | Fake `MessageSource<File>` or contract messages to test file processing. | File filters, read permissions, atomic renames, restart metadata store. |
| **SFTP inbound polling** | Fake source emitting `Message<File>` or matching payloads into the flow. | Authentication, host keys, remote directories, streaming/download, reconnect. |
| **SFTP outbound** | Mock handler to verify remote filename/path headers and content. | Real uploads, partial files, permissions, retries, sessions. |
| **HTTP outbound adapter** | Mock handler to verify URI/header/body mapping before the boundary. | HTTP status/error mapping, TLS, timeouts, connection pooling. |
| **HTTP outbound gateway** | Appropriate reply-capable fake boundary to test response handling. | Real server responses, redirects, 4xx/5xx, timeouts, error bodies. |
| **JMS outbound** | Mock handler to inspect payload/correlation before sending. | Broker destinations, session transactions, redelivery. |
| **AMQP outbound** | Mock handler to inspect exchange/routing/business headers. | Publisher confirms, returns, ack/nack, DLX. |
| **Kafka outbound** | Mock handler to verify topic/key/event payload. | Serializers, partitions, broker durability, producer ACKs. |
| **JDBC polling inbound** | Fake `MessageSource` replacing DB rows to test flow logic. | Real queries, transactions, locks, isolation, and concurrency. |
| **JDBC outbound** | Mock handler to verify business commands before the DB boundary. | SQL dialects, commit/rollback, and affected rows. |

### 17.2. File/SFTP Payload Contract

If the production adapter emits `Message<File>`, the fake should also emit a `File` from a temporary directory:

~~~java
@TempDir
java.nio.file.Path workDir;

void prepareSource(QueueBackedMessageSource<java.io.File> source)
        throws Exception {
    java.nio.file.Path csv =
            workDir.resolve("orders-001.csv");
    java.nio.file.Files.writeString(csv, "orderId,amount\nPO-1,100\n");

    source.add(MessageBuilder.withPayload(csv.toFile())
            .setHeader("file_name", "orders-001.csv")
            .build());
}
~~~

The `file_name` header in this example is an **illustrative contract value**, not a guarantee that every adapter uses that exact name. In real projects, use the File/SFTP module header constants and mappings matching your version. Fakes should mirror the exact payload type and headers expected by the production flow.

### 17.3. HTTP/SFTP/JMS/AMQP/Kafka Outbound

For substituted outbound handlers, assert everything **before the boundary**:

- `payload`, schema version, content type, event/business ID;
- route/destination/topic/routing key or remote path computed by the flow;
- security headers and tenant mappings derived from trusted sources;
- correlation/tracing fields for error observability;
- invocation counts matching flow semantics.

With real transports, add tests verifying that the **remote file/HTTP request/broker message/database row** actually exists or was processed.

## 18. Testing Routers, Filters, and Splitters with Mocked Boundaries

A flow may split messages into branches routed to different endpoints:

~~~mermaid
flowchart TD
    IN["InputChannel"] --> VALID["Validate payload"]
    VALID --> R{"Route by eventType"}
    R -- "ORDER_CREATED" --> C["createdEndpoint<br/>mock handler"]
    R -- "ORDER_CANCELLED" --> X["cancelledEndpoint<br/>mock handler"]
    R -- "UNKNOWN" --> ERR["error/unsupported event"]
~~~

Sample test plan:

1. Substitute both endpoint handlers with **two separate mocks**.
2. Send `ORDER_CREATED`; verify only the created handler receives the message.
3. Send `ORDER_CANCELLED`; verify only the cancelled handler receives the message.
4. Send an unsupported type; verify error or drop per policy with zero outbound side effects.
5. Send messages with missing or wrong-typed headers; verify flow handling.

For **splitters/aggregators**:

- Attach a business `correlationId` if operations must be traced across transports.
- Verify `sequenceSize`, `sequenceNumber`, or group completion per contract.
- Never assume framework message IDs remain stable business identities across transformers.
- When part of a group is lost, test aggregator timeout/release/expiry behavior per configuration.

`MockIntegrationContext` is effective at the **outputs of branches**; it does not replace routing/splitting logic itself. That logic still runs in the Spring flow, letting tests catch miswiring or dropped headers.

## 19. How to Test Synchronous and Asynchronous Errors

### 19.1. Synchronous Handler Errors

~~~java
MessageHandler failure = message -> {
    throw new IllegalStateException("simulated failure");
};

mockContext.substituteMessageHandlerFor(
        "orderOutboundEndpoint", failure);

// When the flow runs synchronously with no catching error handler:
org.junit.jupiter.api.Assertions.assertThrows(
        org.springframework.messaging.MessagingException.class,
        () -> input.send(
                MessageBuilder.withPayload("PO-1").build()));
~~~

In practice the exception may be `MessageHandlingException`, `MessagingException`, or a wrapper depending on the handler and failure point. Assert against the **actual flow contract**, avoiding brittle assertions if framework layers wrap exceptions differently.

### 19.2. Errors from Pollers or Async Flows

An inbound poller calls the source/handler on a scheduler thread; errors may go to an error handler/error channel, be logged, or trigger retries. Tests should not wrap `start()` in `assertThrows` expecting to catch an error from a later poll.

Instead:

1. Build a fake source emitting an error-triggering message.
2. Substitute the outbound handler with a throwing handler.
3. Start the poller.
4. Wait for the configured **error event** or recovery state.
5. Assert payload/correlation, retry count, or DLQ decision per policy.
6. Stop the endpoint and clean up.

### 19.3. When There Is No errorChannel

Do not assume every Spring Integration flow automatically publishes exceptions to `errorChannel`. Semantics depend on where the error occurs and how the endpoint, poller, executor, transaction, and error handler are configured. Without a matching error path, exceptions may propagate to the caller or log on the scheduler. Tests must target the **explicitly designed error observation point**.

## 20. Idempotency and Retries: Where to Mock Without Confusing Semantics

A mocked outbound handler counts **flow invocations**, not provider message commits. In environments with at-least-once delivery or retries, separate:

| Level | What Can Be Tested with Mocks | What Must Be Tested at Target |
|---|---|---|
| **Flow invocation** | How many messages and which business keys the handler receives. | No duplicate side effects after retries. |
| **Retry advice/logic** | A handler simulating failure then success, counting attempts per policy. | Whether transport retries/requeues/commits properly. |
| **Business idempotency** | Business handler ignores event IDs already recorded in a fake store. | Concurrency/transactions on a real store produce no duplicates. |
| **Transaction** | Handler invoked in success/failure scenarios. | DB/broker rollback/commit at transaction boundaries. |
| **Recovery** | Flow routes message to the intended error branch. | Message actually lands in DLQ or target data is accurate. |

### 20.1. Testing a Handler That Fails Once Then Succeeds

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger attempts = new AtomicInteger();

MessageHandler flaky = message -> {
    if (attempts.incrementAndGet() == 1) {
        throw new IllegalStateException("transient failure");
    }
};

mockContext.substituteMessageHandlerFor(
        "orderOutboundEndpoint", flaky);
~~~

Substituting the handler above **only simulates a failure**. For the flow to retry automatically, the endpoint must have a retry advice/interceptor or configured retry mechanism. Without retries configured, the first call fails and `attempts` stays at 1. **Do not expect a mock to supply retry behavior on its own.**

### 20.2. Business Keys vs. Framework Message IDs

Message headers include a Spring-generated `id`; across transformers or gateways, this ID can change. Business deduplication usually requires a stable key, such as:

~~~json
{
  "eventId": "evt-order-2048",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 2,
  "orderId": "PO-2048",
  "tenantId": "VN"
}
~~~

Mocks can verify that `eventId` stays intact at the outbound boundary; adapter tests against a broker/database are needed to prove idempotency **under redelivery, lost ACKs, or competing consumers**.

## 21. Common Mistakes When Using MockIntegrationContext

| Mistake | Symptom | Fix |
|---|---|---|
| **Passing channel name instead of endpoint ID** | Substitution misses component or hits wrong target. | Assign explicit endpoint IDs and inspect bean graph. |
| **Forgetting `@SpringIntegrationTest`** | Cannot inject `MockIntegrationContext` in expected test config. | Enable the extension and configure Spring Test context properly. |
| **Poller runs before substitution** | Real files are read or unexpected messages appear. | Use `noAutoStartup` and explicit start. |
| **Omitting `resetBeans()`** | Subsequent tests keep hitting stale mocks. | Reset in teardown and quiesce in-flight work. |
| **One-way mock for reply-expecting gateway** | Gateway times out, test hangs or fails falsely. | Use a reply-capable fake handler for request/reply. |
| **Fake source emits infinitely** | Infinite duplicates or flaky count assertions. | Emit finite items then `null`, unless intentionally testing duplicates. |
| **Asserting only `send() == true`** | Unclear whether handler/target processed message. | Verify mock, output, error, or readback as appropriate. |
| **Immediate Mockito verify on async channel** | Race failures in CI. | Wait for bounded events/latches/recording handler. |
| **Confusing mock pass with production connectivity** | Missing tests for TLS, broker acks, transactions. | Add real adapter integration tests. |
| **Mocking at wrong place, bypassing flow logic** | Tests pass because transformers/routers were replaced too. | Substitute at external boundary; keep flow logic in scope. |
| **Running parallel tests on shared context** | Tests overwrite each other's handlers. | Isolate contexts or avoid parallel runs on same endpoints. |
| **Exposing sensitive data in logs** | Secrets/test credentials leak via CI. | Redact, use synthetic fixtures, restrict log access. |
| **Skipping cleanup checks** | Pollers/queues/topics/DB rows linger after tests. | Stop, reset, and delete test resources by ownership. |

## 22. Recommended Test Matrix for MockIntegrationContext

| # | Scenario | Isolation Approach | Verification Point |
|---:|---|---|---|
| 1 | Valid payload | Mock outbound handler | Correct payload/headers, one invocation in sync flow. |
| 2 | Missing required header | Mock outbound handler | Outbound not called; reject/error branch accurate. |
| 3 | Router selects right branch | Mock two handlers | Only the matching endpoint receives the message. |
| 4 | Transformer changes payload type | Mock outbound handler | Type, value, and headers match contract. |
| 5 | Polling source has no data | Fake source returns `null` | No business output emitted. |
| 6 | Polling source has one message | Fake source emits once | Valid single receipt without infinite loop. |
| 7 | Poller start/stop | `noAutoStartup` + controlled lifecycle | No poll before start; no new polls after stop. |
| 8 | Handler throws in `DirectChannel` | Failing handler | Exception matches sync error contract. |
| 9 | Handler throws in poller | Failing handler + fake source | Error/retry path triggered, no false success. |
| 10 | Retry fails then succeeds | Handler with `AtomicInteger` | Attempt count and state match configured advice. |
| 11 | Duplicate event ID | Fake source emits twice | Business dedup/idempotency policy enforced. |
| 12 | Gateway reply | Reply-capable fake | Reply mapping/correlation/timeout accurate. |
| 13 | Kafka/JMS boundary | Mock handler | Topic/destination, payload, headers valid before adapter. |
| 14 | SFTP/File boundary | Mock source/handler | File payload, remote path, metadata contract valid. |
| 15 | JDBC inbound logic | Fake source with matching DTO | Row-to-message mapping and handling accurate. |
| 16 | Real target unavailable | Unmocked transport | Failure/recovery/ACK verified on real server/broker. |
| 17 | Shared context across two tests | Reset + isolated fixtures | Second test sees neither messages nor mocks from first. |
| 18 | Concurrent execution | Controlled executor/latch | No mixed messages, no shared mock state. |
| 19 | Spoofed tenant header | Mock outbound boundary | Policy blocks before external side effect. |
| 20 | Adapter contract after upgrade | Tests with stable endpoint IDs | Mapping and substitution still work or fail clearly. |

Each case should document **inputs, initial state, endpoint ID, expected event, timeout, cleanup, and scope of evidence**. A test that merely succeeds in calling substitute without sending a message or asserting outputs is incomplete.

## 23. Test Suite Organization and Lifecycle Template

A maintainable structure:

~~~text
src/test/java/...
  flow/
    OrderTransformFlowTest.java
    OrderRoutingFlowTest.java
    OrderErrorFlowTest.java
  polling/
    FileSourceIsolationTest.java
    DatabasePollingFlowTest.java
  adapter/
    SftpTransferIntegrationTest.java
    HttpOutboundIntegrationTest.java
    KafkaOutboundIntegrationTest.java
  e2e/
    FileToKafkaWorkflowTest.java
~~~

Where:

- **flow/**: fast, no external systems; uses `MockIntegrationContext` and fake handlers/sources.
- **polling/**: manages lifecycles, fixtures, metadata/filters, mocking sources only when real connectivity is not the goal.
- **adapter/**: uses HTTP test servers, SFTP servers, brokers, or real/isolated DBs to validate protocols.
- **e2e/**: exercises the full path from source to final outcome with evidence.

### 23.1. Suggested Teardown

~~~java
@AfterEach
void cleanup() {
    // If a poller was started in the test, stop it first
    // and ensure no in-flight work remains per contract.
    mockContext.resetBeans();
    // Clean up QueueChannels, files, broker topics, database rows,
    // and mock state created by this test.
}
~~~

With endpoint lifecycles, ensure proper stop/reset ordering and make cleanup **always run even when assertions fail**. Never share production addresses or un-namespaced topics/files across tests.

## 24. Case Study: File/SFTP Inbound → Validate → Outbound Kafka

Suppose an application fetches CSV order files from SFTP, converts them into events, and publishes to Kafka. The test objective is verifying the logic from **message successfully read** to **event ready to send**.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound polling source"] --> C["fileInput channel"]
    C --> V["Validate file<br/>tenant, format, size"]
    V --> T["Transform CSV → OrderEvent"]
    T --> O["Kafka outbound handler"]
    M["MockIntegrationContext"] -. "fake MessageSource" .-> SFTP
    M -. "mock MessageHandler" .-> O
    V --> ERR["error/invalid channel"]
~~~

### 24.1. Testing the Flow Without Real SFTP/Kafka

1. Create a CSV file in `@TempDir`.
2. Use `QueueBackedMessageSource<File>` to emit `Message<File>` with matching metadata.
3. Substitute the source at `sftpInboundEndpoint` while the poller is stopped.
4. Substitute the Kafka outbound handler at `kafkaOutboundEndpoint`.
5. Start the poller and wait for the mock to receive `OrderEvent` via a recorder/latch.
6. Assert `eventId`, `orderId`, `tenantId`, event type, and content.
7. Verify schema-invalid files go to the error path and never reach the Kafka boundary.
8. Stop the poller, reset substitutions, and clean up files and state.

**What is proven:** validators/transformers/routers and channel wiring produce the right message. **Not yet proven:** whether SFTP actually downloads files, Kafka persists events, or downstream consumers commit offsets.

### 24.2. Separate Tests with Real Transports

| Transport Test | Fixture | Pass Evidence |
|---|---|---|
| SFTP inbound | Test SFTP server, test host key/credentials, remote CSV | File downloaded with accurate bytes, filter works, session opens/closes cleanly. |
| Kafka outbound | Test broker and isolated topic | Test consumer observes event with expected key/topic/partition per contract. |
| End-to-end | SFTP + Kafka + downstream DB if needed | Source file yields final outcome with retries/idempotency per policy. |

If a test case only uses mocks, never name it `shouldPublishToRealKafka`. Name it after what it actually proves, e.g., `shouldBuildKafkaOutboundMessage`.

### 24.3. Mandatory Error Scenarios

- **Empty SFTP source:** poll emits no messages.
- **Malformed payload:** no publish; appropriate reason/error recorded.
- **Same event ID emitted twice:** business layer enforces deduplication policy.
- **Kafka boundary throws:** retry/error flow executes without falsely marking success.
- **Poller runs before substitution:** prevented via `noAutoStartup` and fixture isolation.
- **Context cached across two tests:** `resetBeans()` prevents cross-test interference.

## 25. Practice Exercises

### Exercise 1 — Handler Substitution

Create a Spring Integration flow `inputChannel → trim String → outboundEndpoint`.

Requirements:

1. Assign endpoint ID `trimOutboundEndpoint`.
2. Inject `MockIntegrationContext` using `@SpringIntegrationTest` and `@SpringJUnitConfig`.
3. Replace the handler with a Mockito mock.
4. Send payload `"  invoice-001  "` with a `traceId` header.
5. Assert normalized payload, preserved header, and exact mock invocation count.
6. Reset substitutions after the test; explain why this test does not prove HTTP/Kafka side effects.

### Exercise 2 — Controlled MessageSource

Create a polling adapter emitting messages to a `QueueChannel`.

Requirements:

1. Configure an endpoint ID and `noAutoStartup`.
2. Create a `QueueBackedMessageSource<String>` holding two messages, then returning `null`.
3. Substitute the source and explicitly start the endpoint.
4. Assert exactly two messages matching the contract, with no extras.
5. Stop the endpoint, call `resetBeans()`, and clean up the queue and source.
6. Add an empty-source case and a source-throws-exception case.

### Exercise 3 — Error Behavior

Build a flow whose outbound handler is replaced by a handler that fails once.

Requirements:

1. Test **without retry advice**: verify the matching exception/error event.
2. Add retry per project configuration and re-test attempt counts.
3. Verify correlation and check whether business side effects duplicate.
4. Create an async version and switch assertions from `assertThrows` to bounded observation.
5. Explain why real broker errors still require transport integration tests.

### Exercise 4 — Request/Reply Gateway

Create a simple HTTP or messaging outbound gateway.

Requirements:

1. Document the request/reply contract and timeout.
2. Build a **reply-capable** fake handler, not just a one-way Mockito mock.
3. Send a request and verify response and correlation.
4. Test a missing-reply branch and an error-reply branch.
5. Write an additional integration test using a test server/broker to verify the protocol.

### Exercise 5 — Multi-Adapter Test Plan

Design a test suite for **File/SFTP → transformer → Kafka/JMS → database**.

For each test, specify:

- Objective and which boundary is mocked.
- Endpoint ID of the `MessageSource` or `MessageHandler`.
- Sample data, payload type, headers, and business ID.
- Initial conditions, poller start/stop handling, and cleanup.
- Assertions, timeouts, and pass/fail evidence.
- Behaviors requiring additional proof against a real server/broker/database.

## 26. Acceptance Checklist

A high-quality test suite built on `MockIntegrationContext` meets these criteria:

- [ ] **Right test layer chosen:** flow isolation vs. transport integration.
- [ ] **Includes `@SpringIntegrationTest`** and an appropriate configuration context.
- [ ] **Endpoint IDs explicitly declared or verified**, never confused with channel/flow/handler beans.
- [ ] **Substitutes the right `MessageHandler` or `MessageSource`** supported by the endpoint.
- [ ] **Substitutes at the isolation boundary**, keeping real transformers/routers/filters in scope.
- [ ] **Assertions verify payloads, headers, correlation, and invocation counts**.
- [ ] **Request/reply gateways tested with reply-capable fakes** where needed.
- [ ] **Pollers do not run before setup**, sources are finite, and lifecycles are controlled.
- [ ] **Sync/async semantics handled with appropriate observation**.
- [ ] **Negative paths covered:** invalid data, filters, exceptions, retries, and duplicates.
- [ ] **`resetBeans()` called and state cleaned**, independent of test order or parallelism.
- [ ] **No side effects sent to production** and no unnecessary secrets/PII logged.
- [ ] **Mocks never used as proof of real protocols**, with real adapter tests covering in-scope transports.
- [ ] **Bounded timeouts and reliable observation points**, minimizing CI flakiness.

## 27. Summary

**`MockIntegrationContext` solves the problem of isolating integration points while still verifying Spring Integration wiring and message processing.** With `substituteMessageHandlerFor`, you can inspect messages about to leave for HTTP/SFTP/JMS/AMQP/Kafka/JDBC without triggering real side effects. With `substituteMessageSourceFor`, you can control inputs to inbound polling adapters and test parsers, transformers, routers, and error flows without real files, SFTP, or databases.

Its effectiveness hinges on **exact endpoint IDs, matching handler/source types, proper `start`/`stop`/`noAutoStartup` lifecycle control, sync/async-aware assertions, and cleanup via `resetBeans()`**. By combining isolated flow tests with real server/broker integration tests and final-state evidence, teams keep their test suite fast and reliable without ever mistaking "the mock received the message" for "the external system succeeded."

# Spring Integration Test Utilities: Testing Adapters, Gateways, Channels, and Pollers

A **Spring Integration** flow connected to files, SFTP, HTTP, JMS, AMQP, Kafka, or a database often looks simple when tested manually: receive a message, transform the payload, send it through a `MessageChannel`, and forward it to an external system. Yet when retries, timeouts, delayed replies, duplicate file reads, or slow broker startups occur, manual testing makes it hard to tell whether **the bug lies in business logic, the message contract, the Spring Integration configuration, or the external system**.

The **Spring Integration test utilities** lesson belongs to the **Testing** chapter of the `SPRING_INTEGRATION_ADAPTERS` module. It covers testing inbound/outbound adapter flows, gateways, pollers, and `MessageChannel`s; distinguishing pure in-memory tests from real-protocol integration tests; and verifying message contracts, error handling, connection states, and adapter resilience.

**Core principle:** the closer a test is to pure logic, the faster, more deterministic, and network-free it should be; the closer it is to an adapter boundary, the more it must verify real protocol behavior, connection lifecycles, acknowledgments, and error recovery. No single test type proves everything.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish **unit tests**, **Spring Integration flow tests**, **adapter integration tests**, **contract tests**, and **end-to-end tests**.
2. Use `spring-integration-test`, `@SpringIntegrationTest`, `MockIntegrationContext`, and JUnit/Mockito tools to isolate endpoints.
3. Exercise a `MessageChannel` flow using `DirectChannel`, `QueueChannel`, and `MessageBuilder` without running a broker.
4. Test request/reply gateways, headers, payloads, transformations, routing, filtering, correlation, and error handling.
5. Design inbound/outbound adapter tests for **File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC** matching the realistic capabilities of each transport.
6. Control pollers, timing, concurrency, threads, duplicate messages, retries, and idempotency to avoid flaky tests.
7. Identify scenarios that require a real target system or high-fidelity test environment, and what mocks **cannot prove**.
8. Build a test matrix, verification evidence, and CI checklist for maintainable adapters.

## 2. Spring Integration Testing Map

A flow can be illustrated as follows:

~~~mermaid
flowchart LR
    EXT["External system<br/>File / SFTP / HTTP / Broker / DB"] --> IN["Inbound adapter<br/>or inbound gateway"]
    IN --> CH["MessageChannel"]
    CH --> LOGIC["Filter / Router / Transform<br/>Service activator"]
    LOGIC --> OUT["Outbound adapter<br/>or outbound gateway"]
    OUT --> TARGET["External target"]
    LOGIC --> ERR["Error handling<br/>Error channel / recovery"]
~~~

Components in the diagram carry distinct responsibilities:

| Component | What to Test | Example |
|---|---|---|
| **Inbound adapter** | When it reads external sources, what payload/headers it creates, whether it reads duplicates? | File poller emits `Message<File>`. |
| **Inbound gateway** | Are incoming requests mapped properly and are responses/HTTP statuses accurate? | HTTP endpoint returns processed data. |
| **Channel** | Who receives messages, sync/async behavior, ordering, backpressure/queueing? | `DirectChannel` vs. `ExecutorChannel`. |
| **Transformer / filter / router** | Are data, headers, and conditional branches handled properly? | Accept only CSV files and convert to DTOs. |
| **Outbound adapter** | Does the one-way send to the target system behave accurately? | Write a file or send a JMS event. |
| **Outbound gateway** | Does it wait for and handle replies/timeouts properly? | Call an HTTP API and forward the response. |
| **Poller** | Interval, trigger timing, max messages, stop/start, and poll errors? | Poll a DB on a schedule. |
| **Error handling** | Where are exceptions thrown, published, retried, routed to DLQ, or recorded? | Broker temporarily unavailable. |

**Adapters differ from gateways:** an adapter is typically a one-way bridge between the message flow and an external system; a gateway has request/reply semantics. Outbound adapter tests should not assume a business reply will arrive if the endpoint does not produce one.

## 3. Choosing the Right Testing Layer

| Testing Layer | Starts Spring Context? | External System Dependency? | Purpose |
|---|---|---|---|
| **Unit test** | No | No | Test pure Java mappers, validators, and routers. |
| **In-memory flow test** | Usually a small context | No | Verify channel wiring, headers, payloads, routes, handlers. |
| **Endpoint isolation test** | Yes | No or mocked | Replace adapters/handlers with mocks to test orchestration. |
| **Adapter integration test** | Yes | Yes: test server/broker/DB | Verify protocol mapping, transactions, ack, retry, and networking. |
| **Contract test** | Depends on model | Stub or compatible target | Verify schemas, headers, API versions, error conventions. |
| **End-to-end test** | Yes | Yes, multiple targets | Prove the full path from start to finish, recovery, and real state. |

### Allocation Rules

- JSON conversion logic, correlation ID assignment, or routing decisions should have **fast unit tests**.
- Message flow configuration should have **tests with a minimal Spring context**.
- SFTP handshake failures, AMQP confirms, Kafka offsets/commits, or JDBC transactions need **tests with near-real transports**.
- A passing end-to-end test does not replace negative tests for missing headers, timeouts, duplicates, and malformed data.

~~~mermaid
flowchart TD
    U["Many unit tests<br/>No broker / no network"] --> F["Flow tests<br/>Channels + mock endpoints"]
    F --> A["Adapter integration tests<br/>Ephemeral server/broker/DB"]
    A --> E["Few end-to-end tests<br/>Multiple real boundaries"]
~~~

## 4. Key Testing Utilities

Spring Integration provides its own testing module, combined with Spring Test, JUnit Jupiter, and Mockito:

| Utility | Role |
|---|---|
| `spring-integration-test` | Spring Integration's dedicated testing utilities and integration helpers. |
| `@SpringIntegrationTest` | Enables Spring Integration testing support in a Spring test context; can specify endpoints not to auto-start. |
| `MockIntegrationContext` | Temporarily substitutes the handler or message source of matching endpoints with test objects. |
| `MockIntegration` | Factory/helper creating mocks/spies tailored for Integration endpoints. |
| `TestUtils` | Accesses internal bean properties for diagnostic/config assertions when truly necessary. |
| `MessageBuilder` | Builds `Message<?>` instances with payloads and headers for testing. |
| `DirectChannel` | Synchronous dispatch channel enabling highly deterministic logic tests. |
| `QueueChannel` | Pollable channel to read outputs with a timeout in tests. |
| `@SpringJUnitConfig` | Initializes a Spring Test context on JUnit Jupiter. |
| **Mockito** | Creates mocks/spies and verifies which messages a handler received. |
| **JUnit Jupiter** | Assertions, setup/teardown, `@TempDir`, parameterized tests. |

**Distinguish tool origins:** `QueueChannel`, `DirectChannel`, `MessageBuilder`, and `IntegrationFlow` belong to Spring Integration/Spring Messaging; JUnit and Mockito are external testing libraries. `MockIntegrationContext` and `@SpringIntegrationTest` belong to Spring Integration's test utilities. Do not label everything as an API of `spring-integration-test`.

## 5. Project Dependency Configuration

Maven example when the project uses Spring Boot and compatible BOM/dependency management:

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

Gradle Kotlin DSL example:

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")
    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

These examples assume **the project uses Spring Boot's plugin/dependency management** to manage compatible versions. Without a BOM, declare matching versions for Spring Framework, Spring Integration, JUnit, and Mockito according to your actual build.

Specific adapters require their respective modules, such as `spring-integration-file`, `spring-integration-sftp`, `spring-integration-http`, `spring-integration-jms`, `spring-integration-amqp`, `spring-integration-kafka`, or `spring-integration-jdbc`. Add only what is used; **adding test utilities does not automatically provide an SFTP server, broker, or database**.

**Compatibility note:** package names, DSL APIs, or initialization configurations may vary across release lines. The examples below target the common Java DSL/Spring Test model; when adopting them in a real project, verify against your version's API docs. Do not copy arbitrary versions from a snippet into a project already managing dependencies via BOM.

## 6. First Example: Testing an In-Memory Channel-Only Flow

Let's test a flow that receives an order string, trims whitespace, and forwards it to a result channel—no Kafka, JMS, or HTTP needed.

### 6.1. Flow Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class NormalizationTestConfig {

    @Bean
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel ordersOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow normalizeOrders(DirectChannel ordersInput,
                                    QueueChannel ordersOutput) {
        return IntegrationFlow.from(ordersInput)
                .transform(String.class, String::trim)
                .channel(ordersOutput)
                .get();
    }
}
~~~

`DirectChannel` invokes the handler synchronously on the sender's thread. `QueueChannel` holds output so the test can actively receive with a timeout; this is a common pattern for verifying payloads and headers without relying on `Thread.sleep`.

### 6.2. Testing with JUnit Jupiter

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(NormalizationTestConfig.class)
class NormalizationFlowTest {

    @Autowired
    @Qualifier("ordersInput")
    DirectChannel input;

    @Autowired
    @Qualifier("ordersOutput")
    QueueChannel output;

    @Test
    void shouldNormalizePayloadAndPreserveBusinessHeader() {
        Message<String> request = MessageBuilder.withPayload("  PO-42  ")
                .setHeader("traceId", "trace-test-42")
                .build();

        assertTrue(input.send(request));

        Message<?> result = output.receive(1_000);
        assertNotNull(result, "Flow must emit a message");
        assertEquals("PO-42", result.getPayload());
        assertEquals("trace-test-42",
                result.getHeaders().get("traceId"));
    }
}
~~~

**What this test proves:** bean wiring works; the string is trimmed; the business header passes through; one message reaches the output. **What it does not prove:** whether outbound HTTP/JMS/SFTP will succeed, whether the target persisted data, or whether retries work on network failure.

Note that framework `id` and `timestamp` headers can be regenerated when transforming messages. Avoid writing assertions expecting the message ID to remain identical across every handler unless that is an explicit contract requirement.

## 7. Testing the Message Contract: Payload, Headers, and Routing

A message in Spring Integration holds both a **payload** and **headers**; header contents can critically affect request/reply behavior or routing:

| Component | What to Test | Common Pitfalls |
|---|---|---|
| **Payload type** | `String`, `byte[]`, `File`, DTO, or domain event | Adapter emits `File` while transformer casts to `String`. |
| **Business headers** | `tenantId`, `traceId`, `schemaVersion` | Headers lost during transformation or transport mapping. |
| **Correlation** | `correlationId`, `sequenceNumber`, `sequenceSize` | Aggregator fails to group related messages. |
| **Reply metadata** | `replyChannel`, timeout, response type | Gateway misses reply or receives on the wrong channel. |
| **Error metadata** | `errorChannel` or error handling config | Exceptions do not travel down the path the test expects. |
| **Transport headers** | HTTP status/content type; JMS correlation; Kafka topic/key | Mis-mapped headers or assuming all transports behave identically. |
| **Security context** | Tenant, principal, resource scope | Trusting client-supplied headers without verification. |

### Routing Test Example

A router selects channels based on `eventType`:

~~~java
IntegrationFlow routingFlow(MessageChannel input) {
    return IntegrationFlow.from(input)
            .route(
                org.springframework.messaging.Message.class,
                message -> message.getHeaders().get("eventType"),
                mapping -> mapping
                    .channelMapping("CREATED", "createdChannel")
                    .channelMapping("CANCELLED", "cancelledChannel")
            )
            .get();
}
~~~

The snippet above illustrates **header-based routing conceptually**; `createdChannel` and `cancelledChannel` must exist in the context, and DSL generics/overloads must match your version. Corresponding tests should send two messages with different headers and verify **the right channel receives each**, **the other channel receives nothing**, and **invalid `eventType` values** are handled per policy (reject, default route, or error flow) rather than disappearing silently.

### Questions a Good Contract Test Should Ask

1. Does a valid payload have the right **type and content**?
2. Are required business headers preserved?
3. Where are headers created, from what source, and could they be spoofed?
4. Are invalid messages rejected, sent to an error channel, or routed to a DLQ?
5. What changes when a message arrives from a different transport versus an internal producer?

## 8. Isolating Endpoints with @SpringIntegrationTest and MockIntegrationContext

When you want to test the middle of a flow without calling real external systems, you can **replace an endpoint's handler** inside the Spring Integration test context.

### 8.1. Purpose of the APIs

- `@SpringIntegrationTest` enables dedicated Spring Integration test-context support.
- `MockIntegrationContext` lets you substitute the **message handler** or **message source** attached to a matching endpoint to avoid calling external systems.
- `MockIntegration` provides helpers to create mocks/spies tailored for message handler/source scenarios.
- After each test, **restore endpoints and test data** so mocks from one test do not leak into subsequent tests.

This is **in-flow component substitution**, not replacing every bean of the same name or simulating a full protocol. The endpoint ID must be declared and match the exact ID registered by the Integration configuration.

### 8.2. Example: Substituting an Outbound Handler with Mockito

~~~java
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@SpringJUnitConfig(OutboundIsolationTest.TestConfig.class)
@SpringIntegrationTest
class OutboundIsolationTest {

    @Autowired
    MockIntegrationContext mockIntegrationContext;

    @Autowired
    @Qualifier("toPartner")
    DirectChannel input;

    @AfterEach
    void restoreEndpoints() {
        mockIntegrationContext.resetBeans();
    }

    @Test
    void shouldSendOneMessageToOutboundEndpoint() {
        MessageHandler fakeSender = mock(MessageHandler.class);

        mockIntegrationContext.substituteMessageHandlerFor(
                "partnerOutboundEndpoint", fakeSender);

        input.send(MessageBuilder.withPayload("order-900")
                .setHeader("partner", "partner-A")
                .build());

        verify(fakeSender).handleMessage(argThat(message ->
                "order-900".equals(message.getPayload())
                        && "partner-A".equals(
                                message.getHeaders().get("partner"))));
    }

    @Configuration
    @EnableIntegration
    static class TestConfig {

        @Bean
        DirectChannel toPartner() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow partnerOutboundFlow(DirectChannel toPartner) {
            MessageHandler realAdapterBoundary = message -> {
                throw new IllegalStateException(
                        "Real endpoint must not be called in isolation test");
            };

            return IntegrationFlow.from(toPartner)
                    .handle(realAdapterBoundary,
                            endpoint -> endpoint.id("partnerOutboundEndpoint"))
                    .get();
        }
    }
}
~~~

This pattern verifies that **the message reaches the outbound boundary** and its contents satisfy the contract. It does not verify that the partner actually received the data. In real adapter integration tests, use an HTTP/SFTP/broker target to verify requests and transport state.

**Version note:** if your version differs in the `handle(...)` DSL or endpoint mocking API, choose the equivalent overload from your version's API docs; the goal remains unchanged: **a stable endpoint ID substituted at the external side-effect boundary**.

### 8.3. Substituting an Inbound MessageSource When Testing Pollers

For polling endpoints, you can substitute `MessageSource<?>` to control when messages appear:

~~~java
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.support.MessageBuilder;

MessageSource<String> fakeSource = () ->
        MessageBuilder.withPayload("file-ready.csv").build();

mockIntegrationContext.substituteMessageSourceFor(
        "fileInboundEndpoint", fakeSource);
~~~

This snippet assumes the context has registered a `fileInboundEndpoint` compatible with that source type. In real tests, the fake should return **scripted messages and then return `null`** so the poller does not emit the same message endlessly on every tick; also configure stop/start for the endpoint so tests do not depend on startup timing.

## 9. Controlling Pollers and Endpoint Lifecycles

A poller may use `fixedDelay`, `fixedRate`, cron, `maxMessagesPerPoll`, an executor, or a transaction manager. Common causes of flaky tests include:

- The poller runs before the test attaches a mock.
- The poller reads stale files or leftover database rows from a previous test.
- Two scheduler ticks fire while assertions are executing.
- The source returns messages continuously, filling `QueueChannel` with multiple copies.
- Transaction rollbacks or status filters cause messages to be re-read.
- The endpoint is stopped while an in-flight poll is still executing.

### Purposeful Use of noAutoStartup

~~~java
@SpringIntegrationTest(noAutoStartup = "inboundPollerEndpoint")
@SpringJUnitConfig(PollingTestConfig.class)
class PollerLifecycleTest {
    // Attach mock source, prepare data and output first.
    // Then retrieve the exact endpoint lifecycle bean and explicitly call start().
    // At the end of the test, stop() and restore mocks/context.
}
~~~

The `noAutoStartup` pattern gives the test control over **when the endpoint starts**. You must use the exact declared endpoint ID; it is not necessarily the same as the input channel name. Verify your version and endpoint registration approach before applying.

### Poller Tests Should Separate Conditions

| Condition | Valuable Testing Approach |
|---|---|
| **Empty source** | `MessageSource.receive()` returns `null`, no messages on output. |
| **Single message** | Source emits exactly one message then stops; handler receives once. |
| **Max messages per poll** | Seed multiple items and prove batch count per config, without inferring from sleep. |
| **Source error** | Source throws an exception; verify configured error handling/rollback/alerting. |
| **Stop/start** | Explicitly trigger lifecycle; confirm no new polls occur after stop, accounting for in-flight races. |
| **Idempotency** | Retries or subsequent polls do not cause unintended duplicate side effects. |
| **Transaction** | Source/handler errors result in commit/rollback matching real configuration. |

Prefer **observable conditions** (latches, channel receives, readback state, recorded events) over `Thread.sleep(2_000)` and guessing whether the scheduler ran. When real timing must be tested, use bounded timeouts and explicitly classify the test as a concurrency/timing test.

## 10. Synchronous, Asynchronous, and Request/Reply Tests

### DirectChannel: Same-Thread Logic

With `DirectChannel`, sending a message typically invokes the subscriber synchronously. Exceptions from the handler can propagate back to the sending thread as `MessagingException` or an appropriate wrapper.

~~~java
assertThrows(
        org.springframework.messaging.MessagingException.class,
        () -> input.send(MessageBuilder
                .withPayload("invalid")
                .build()));
~~~

Use such an assertion only when the flow genuinely **throws exceptions synchronously**. If a filter drops the message or an error handler swallows the error, expectations differ; do not assume all invalid inputs throw at `send()`.

### ExecutorChannel: Off-Thread Processing

With `ExecutorChannel` or task-executor-backed endpoints, `send()` returning does not mean the business handler has finished. Tests should:

- Use an output `QueueChannel`, `CountDownLatch`, or future to wait for evidence.
- Set explicit timeouts suitable for CI environments.
- Clean up executors and endpoints after each test.
- Check where errors are published according to the error handling configuration; do not wait for exceptions on the sender's thread.

### Request/Reply Gateways

For gateways, additionally cover:

1. Requests are mapped to messages on the right channel with expected payload and headers.
2. Replies are produced with the right data type, correlation, and response mapping.
3. Missing reply before deadline: gateway handles timeouts per contract.
4. Handler throws exception: error is propagated/mapped per gateway mechanism.
5. One-way messages are not mistakenly treated as calls requiring a response.
6. Requests are never mismatched with another request's reply under high concurrency.

When using `@MessagingGateway`, tests can autowire the gateway interface in the context and invoke it like a normal API. **That tests the gateway's request/reply contract**, not external HTTP/JMS connectivity if the outbound endpoint has been mocked.

## 11. Unit Tests First, Spring Context Second

Not every class needs `@SpringJUnitConfig`. A pure Java transformer should be tested as a plain function:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class FileNameNormalizer {
    String normalize(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing name");
        }
        return value.strip().toLowerCase(java.util.Locale.ROOT);
    }
}

class FileNameNormalizerTest {
    private final FileNameNormalizer normalizer =
            new FileNameNormalizer();

    @Test
    void normalizesFileName() {
        assertEquals("orders.csv",
                normalizer.normalize(" ORDERS.CSV "));
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
                () -> normalizer.normalize("  "));
    }
}
~~~

Benefit: tests run very fast with zero dependency on bean graphs, brokers, schedulers, or environments. Afterward, **a small flow test** proves the transformer is wired into the right channel. Separating layers yields clearer failure diagnostics.

## 12. Testing File Inbound/Outbound Adapters

File adapters carry real filesystem state: directories, filenames, read/write permissions, filters, patterns, partially written files, and post-processing deletion/archiving.

### @TempDir for Filesystem Tests

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileContractTest {

    @TempDir
    Path root;

    @Test
    void preparesAnInputFileAndChecksItsBytes() throws Exception {
        Path inbox = Files.createDirectory(root.resolve("inbox"));
        Path input = inbox.resolve("orders-001.csv");
        Files.writeString(input, "id,amount\n1,120\n");

        assertTrue(Files.isRegularFile(input));
        assertEquals("id,amount\n1,120\n",
                Files.readString(input));

        // In the adapter test, configure inbound directory = inbox.
        // Start poller; read output channel and inspect Message<File>.
    }
}
~~~

`@TempDir` is managed by JUnit Jupiter, creating an isolated directory per test and avoiding production directories or shared directories from prior runs.

### Required Cases

| Case | Expectation |
|---|---|
| Valid file | Emits exactly one message with payload/headers matching contract. |
| File failing pattern/extension | Ignored if excluded by filter. |
| Empty file | Clear outcome: accepted, rejected, or error per policy. |
| File being written | Incomplete files are not processed; uses atomic rename/marker convention if required. |
| Same filename with new content | Filter/key applies appropriate rule; not falsely treated as stale. |
| Missing read/write permissions | Error recorded, retried/alerted per policy; not marked successful. |
| Outbound filename collision | Executes replace/append/fail rule per explicit configuration. |
| Adapter restart | Does not drop or arbitrarily reprocess files; verify metadata store/filter state. |

**Filter note:** some deduplicating filters like `AcceptOnceFileListFilter` store state either in memory or in a metadata store depending on configuration. When testing restarts and durability, use the exact store type used in production; single-process tests do not prove post-restart behavior.

## 13. Testing SFTP Adapters

SFTP requires testing both **connection behavior** and **file transfer semantics**. A mock handler only proves a message reached the outbound endpoint; it does not prove the SFTP server accepts the credentials, paths, permissions, or upload.

### SFTP Test Case Matrix

| Case | Appropriate Test Type | What to Verify |
|---|---|---|
| Local/remote path mapping | Unit or flow | Paths are built from trusted inputs without exposing forbidden paths. |
| Successful upload | Test SFTP server | Remote file actually exists with accurate bytes. |
| Successful download | Test SFTP server | Local file is complete with expected name and metadata. |
| Wrong credentials | Test SFTP server | Connection rejected; error message leaks no secrets. |
| Wrong host key | Test SFTP server | Host-key verification policy rejects untrusted endpoints. |
| Missing remote directory | Test SFTP server | Fails/retries or creates directory per approved convention. |
| Network drop mid-transfer | Integration/fault injection | Partial file is never treated as complete. |
| File updated after poll | Test server | File filter and metadata store preserve proper semantics. |
| Restart/reconnect | Test server | Session/connection lifecycle, retries, and idempotency work properly. |

### Designing the SFTP Test Environment

- Use an **ephemeral/isolated** SFTP server or test container, never a production server.
- Provision separate users, remote directories, and data per test.
- Use test host keys and verify host-key validation behavior; **never weaken host-key verification just to make tests pass**.
- Load credentials from test configuration or an appropriate secret store; never commit real passwords.
- Clean up remote files, sessions, and contexts after tests; assert side effects on both local and remote sides.

Some test libraries provide an **embedded SFTP server**, though APIs and compatibility depend on versions. Do not assume an external library's embedded class is a built-in utility of `spring-integration-test`.

## 14. Testing HTTP Inbound and Outbound

### Outbound HTTP

An outbound HTTP flow has two testing layers:

1. **Flow test**: converts internal messages into URI, method, body, and headers and passes them to the outbound gateway/adapter properly.
2. **HTTP integration test**: a real test server receives requests, returns status/body/headers, and simulates timeouts, 4xx, and 5xx responses.

For adapters backed by HTTP clients with matching mock tools, you can use HTTP stubs or mock servers. For example, `MockRestServiceServer` fits `RestTemplate`-based HTTP clients within compatible setups; if using another client or reactive stack, pick the corresponding tool. Never treat a mocked HTTP client as proof that real sockets/TLS work.

### Inbound HTTP

| Case | What to Check |
|---|---|
| Valid request | HTTP status, content type, body, header mapping, message enters channel. |
| Validation failure | 4xx with clear error schema; invalid message never enters business flow. |
| Unauthenticated/unauthorized | 401/403 per contract; never trust client-supplied identity headers. |
| Gateway request with no reply | Timeout/error response per config; request does not hang. |
| Downstream service error | Proper error mapping; correlation and audit leak no stack traces/secrets. |
| Oversized payload / wrong media type | Safely rejected without unbounded resource consumption. |
| Concurrent requests | Replies match requests without mixing correlation across threads. |

`MockMvc` can work well when an HTTP inbound adapter/gateway runs through a **Spring MVC/servlet context** and requests go through compatible wiring. If the adapter uses a different HTTP stack, test against the real endpoint or an appropriate client/server test harness.

**An HTTP 200 does not mean a downstream broker committed the message or a file finished writing.** When designing request/reply, define whether the response represents *accepted*, *processed*, or *completed with evidence*.

## 15. Testing JMS, AMQP, and Kafka: Distinguishing Broker Semantics

JMS, AMQP, and Kafka all transport messages, yet **they do not share the same acknowledgment, offset, or ordering models**. Tests must reflect the exact protocol and listener configuration.

| Concern | JMS | AMQP (e.g., RabbitMQ) | Kafka |
|---|---|---|---|
| Consumption unit | Destination/queue/topic per provider | Queue + exchange/binding/routing | Topic/partition/consumer group |
| Acknowledgment concept | Acknowledge/commit per session/transaction mode | Consumer acknowledgment, reject/nack, and requeue | Offset commit, position, and poll |
| Retry/redelivery | Provider/session/container | Nack/requeue, retry/DLX per setup | Consumer retry/error topic/offset strategy |
| Ordering | Depends on destination, consumer, priority/provider | Depends on queue and concurrency | Ordering guaranteed within a **partition**, not topic-wide |
| Critical tests | Session/transaction rollback | Requeue/DLX, publisher confirms/returns | Key/partition, offset, consumer group, rebalance |

### Minimum Cases with a Real Broker

1. **Publish/consume success:** payload and headers are transported properly.
2. **Serialization:** schema/version/content type match between producer and consumer.
3. **Consumer throws:** retry/redelivery/ack behavior matches configuration.
4. **Duplicate delivery:** consumer is idempotent; side effects are not duplicated beyond policy.
5. **Broker unavailable:** connection/recovery is bounded with alerts and retries.
6. **Unprocessable message:** routed to DLQ/DLT or error path per contract, never silently dropped.
7. **Concurrency/order:** guaranteed within the scope promised by the transport.
8. **Application restart:** in-flight/uncommitted messages are handled per transaction/ack policy.

**Do not claim end-to-end "exactly once"** solely because Kafka or a broker supports scoped transactions/deduplication. Whenever a message triggers a database write, HTTP call, or file upload, external side effects still require idempotency, transactional outbox, or reconciliation.

### When to Use Testcontainers?

Testcontainers is helpful for spinning up ephemeral broker/DB environments for integration tests:

- Kafka broker container for topics, partitions, consumer groups, and offsets.
- RabbitMQ container for exchanges, queues, DLX, and publisher confirms.
- Database container for transactions, locking, queries, pollers, and JDBC.
- JMS broker or SFTP server containers compatible with the target environment.

**Testcontainers is not part of `spring-integration-test`**; it is a separate library requiring an available container runtime. When CI lacks container support, you can run adapter tests against dedicated managed test infrastructure, while keeping mock tests and real-transport tests clearly separated.

## 16. Testing JDBC/Database Inbound/Outbound Adapters

JDBC polling raises different questions than files and brokers: **which records were selected, when are they marked processed, what does the transaction span, and can multiple pollers collide?**

| Situation | What to Verify |
|---|---|
| Empty DB | Poll returns null/emits no message; no errors. |
| Valid new rows | Query selects the right rows; payload/headers map properly. |
| Invalid row | Validation rejects it; clear quarantine or retry policy. |
| Handler fails before commit | Transaction rolls back per config; row is not lost. |
| Row status update | Marked processed only after required completion criteria are met. |
| Two instances polling concurrently | No unintended duplicate processing; proper row locking/claiming. |
| DB connection lost | Retry/backoff, observable error, and recovery once reconnected. |
| Batching and pagination | No rows skipped during batch processing on changing data. |

### Why Testing Against a Real DB Engine Matters

H2 or fake repositories run fast, yet they do not always match transaction isolation, locking, SQL dialects, or `SELECT ... FOR UPDATE` behavior in PostgreSQL/MySQL/SQL Server. For deduplication or transactional status-update logic, include tests against **a DB engine matching production**.

**Transaction boundary:** a database commit is not naturally atomic with sending to Kafka/JMS/HTTP/SFTP. If a workflow must avoid losing messages when the app crashes between two steps, tests must cover the designed outbox/inbox, retry, and recovery mechanisms.

## 17. Error Channels, Exceptions, and Recovery Workflows

A failing message can be handled very differently depending on the flow:

| Context | What Can Happen | Testing Approach |
|---|---|---|
| Synchronous `DirectChannel`, no swallowing handler | Exception propagates to caller | `assertThrows` and inspect type/cause. |
| Inbound poller | Error may be published as an `ErrorMessage` by an error handler or logged per config | Verify the configured error flow, not just the caller. |
| `ExecutorChannel` / async | Error occurs on another thread | Receive from error path, latch, or bounded observation. |
| JMS/AMQP/Kafka listener | Container decides ack, rollback, requeue, offset | Test against a real broker per listener policy. |
| Outbound HTTP gateway | 4xx/5xx/timeout may convert to exception/error reply | Test status mapping and recoverability. |
| File/SFTP upload | Partial side effect may exist before exception | Inspect actual target files, retries, and cleanup. |

### ErrorMessage and Error Context

Spring Messaging/Spring Integration provides `ErrorMessage` carrying a `Throwable` payload. However, **not every exception** automatically routes to a channel named `errorChannel`—that depends on the endpoint, error handler, and configured sync/async context.

A thorough error test answers:

1. Is the error **thrown**, **sent to an error channel**, or **retried by the broker**?
2. Does the error path retain correlation with the original message?
3. Can the message be reprocessed or must it be quarantined?
4. Are retry limits, backoff, and alerting in place?
5. Could partial side effects exist that need checking before retrying?
6. Once resolved, is there evidence that the message succeeded with no residual errors?

Never assert "no exception was thrown" as proof of success; in async flows, an exception may occur on another thread after the test finishes.

## 18. Retries, Idempotency, Duplicates, Ordering, and Recovery

Transports frequently exhibit **at-least-once** semantics, especially when ACKs or responses are lost. Test designs should rely on a **stable business message ID** rather than expecting framework-generated `MessageHeaders.ID` to remain unchanged across every hop.

### Idempotency Contract

~~~json
{
  "eventId": "evt-order-991",
  "eventType": "ORDER_CONFIRMED",
  "schemaVersion": 2,
  "source": "checkout",
  "occurredAt": "2026-11-23T09:20:00Z",
  "orderId": "PO-991",
  "tenantId": "VN"
}
~~~

For example, if the same `eventId` is delivered twice by the broker:

- The consumer may receive two physical messages.
- The business handler should check `eventId` or a business/operation key in an appropriate store.
- Side effects like invoice creation must enforce idempotency: never create duplicate invoices.
- Audit logs may record two deliveries while only one business operation succeeds.

### Failure State Matrix

| Simulated Failure | Expected Observable Outcome |
|---|---|
| Handler fails before persisting state | Retries appropriately; business event not marked complete. |
| DB write succeeds, then broker ACK is lost | Redelivery produces no duplicate side effects. |
| HTTP target receives request, client times out | Idempotent retry or readback determines state. |
| SFTP upload completes, response is lost | Checks target file/identifier before re-uploading. |
| Kafka consumer rebalances mid-processing | Offsets/commits and side effects follow policy. |
| File poller restarts | Filter/metadata store does not mis-mark file status. |
| Lower-version event arrives late | Handled as stale per contract; does not overwrite newer state. |
| DLQ redrive | Messages are reprocessed in a controlled way without duplicates. |

**Concurrency tests** should run enough iterations or use barriers/latches to intentionally provoke contention, yet passing once never proves a race condition cannot exist.

## 19. Managing Time to Prevent Flaky Tests

Distinguish **business time** from **system wait time**:

- Business time can inject a `Clock`, using fake clocks for expiration, due dates, or business timeouts.
- Pollers/schedulers have their own lifecycles; they may need tests with controlled schedulers or integration tests with bounded timeouts.
- Brokers/networks have variable latency; use bounded waits and observable criteria rather than arbitrary millisecond guesses.

### Practical Rules

1. **Never use sleep as a primary synchronization mechanism.** `Thread.sleep` slows tests down without guaranteeing events finished.
2. **Never assert exact wall-clock durations** unless explicitly required and running in a controlled environment.
3. **Never use overly tight timeouts** that fail under CI load.
4. **Never use infinite timeouts** that hang the pipeline.
5. **Initialize fresh state** per test: channels, broker topics/queues, file directories, database rows, metadata stores.
6. **Stop endpoints/executors and close connections** in teardown so subsequent tests do not receive stale messages.
7. **Assign unique IDs per test run** for easy data identification, cleanup, and log tracing.
8. **Track correlation** to wait for the specific expected message rather than popping an arbitrary item from a queue.

`QueueChannel.receive(timeout)` returns `null` if no message arrives within the configured wait window. Use `assertNotNull` after receiving, and when testing "no message arrives", use a bounded timeout long enough to observe behavior; a single `receive(0)` does not prove a message won't arrive moments later.

## 20. Testing Cross-Adapter Contracts and Message Schemas

When one system publishes JSON over Kafka and another receives via HTTP or JMS, adapters do more than move bytes; they can transform:

- Payload types and encoding (UTF-8, binary, serialized objects).
- Header names, content types, Kafka keys, JMS correlation, AMQP routing.
- Timestamp semantics, event IDs, and schema versions.
- Reply/error states and retries.
- Security rules, trust boundaries, and tenant mapping.

### Contract Test Template

| Item | Test Case |
|---|---|
| **Valid schema** | JSON payload includes complete `eventId`, `eventType`, `schemaVersion`, business key. |
| **Missing schema fields** | Rejected/quarantined without writing side effects. |
| **New schema version** | Consumer supports version per contract or rejects with a clear message. |
| **UTF-8** | Vietnamese and Unicode characters remain intact. |
| **Transport headers** | Keys/routing/correlation mapped accurately without namespace collisions. |
| **Security headers** | Tenant/principal originate from trusted components, never self-asserted client inputs. |
| **Replay** | Repeated event IDs do not duplicate business operations. |
| **Reply/error contract** | Error codes, timeouts, correlation, and data redaction remain consistent. |

Contract tests can run against stubs for speed, but whenever a real protocol/serializer/provider has distinct behavior, add integration tests verifying the real transport. In particular, JMS, AMQP, and Kafka do not share a single "universal header contract" for every attribute.

## 21. Observing Flows in Tests: Channels, Interceptors, and Message History

For long flows, tests need **observation points** without heavily altering the production flow:

| Tool / Approach | When to Use | Caution |
|---|---|---|
| Test output `QueueChannel` | Asserting final payload/headers | Do not convert every production channel into a `QueueChannel`. |
| `MockIntegrationContext` | Substituting inbound sources or outbound handlers in tests | Must reset and use exact endpoint IDs. |
| Mockito mock/spy handler | Verifying messages sent to a boundary | Does not prove external side effects. |
| Channel interceptor / wire tap | Observing messages crossing a channel | Avoid altering latency, ordering, or causing side effects. |
| Message history | Tracing which components a message visited when enabled | Adds overhead; does not replace target-state evidence. |
| Integration graph/actuator (when configured) | Diagnosing bean graphs, endpoints, and wiring | Secure observability endpoints; never expose secrets. |
| Metrics/logging/tracing | Tracking throughput, delay, correlation | Never log passwords, tokens, or full PII. |

`TestUtils` can inspect internal properties to verify endpoint wiring, but tests relying on reflection/private fields break easily across framework upgrades. Prefer testing **public behavior**; use introspection only to verify configuration hard to observe otherwise.

## 22. Testing Error Flow Configurations with Evidence

A common mistake is writing a test like:

~~~java
input.send(MessageBuilder.withPayload("broken").build());
// Did not throw => assumed success. This conclusion is insufficient!
~~~

Instead, specify clearly:

~~~text
Scenario: outbound HTTP returns 503
Given: valid request with eventId=evt-42
When:  adapter sends request to stub HTTP server
Then:
  - Retries/backoff match configuration
  - Success is not recorded before a valid response/evidence arrives
  - Final error routes to the configured error channel or error state
  - Correlation eventId is preserved in audit records
  - No duplicate side effects beyond policy
  - When server recovers, message is reprocessed per recovery rules
~~~

Each outcome must be observed at an **authoritative source**. If a system returns HTTP accepted while a downstream task runs asynchronously, read the final result separately; do not assume the initial response confirms business completion.

## 23. Security Testing for Integration Adapters

Because adapters sit at external boundaries, include dedicated security cases:

| Concern | Recommended Test |
|---|---|
| **Credentials** | Passwords, client secrets, keys, bearer tokens are never logged on connection errors. |
| **TLS/host verification** | HTTP/TLS or SFTP host-key checks are never disabled in real configurations. |
| **Path traversal** | File/SFTP paths are validated; reject `../` or out-of-scope paths. |
| **Tenant isolation** | Messages for tenant VN are never routed to another tenant's resources. |
| **Untrusted headers** | Clients cannot claim admin roles simply via request headers. |
| **Oversized payloads** | Size limits and rejection handling prevent trivial memory exhaustion. |
| **Deserialization** | Reject untrusted types outside allowlists/schemas. |
| **Sensitive error output** | Responses/logs never leak stack traces, tokens, or internal secrets. |
| **Idempotency abuse** | Duplicate/colliding keys cannot arbitrarily overwrite sensitive operations. |

Never use real credentials, private keys, or real customer message data in tests; generate synthetic fixtures and manage test secrets per CI policy.

## 24. Practical Project Example: File Inbound → Validation → Kafka Outbound

Suppose a system reads CSV files from an internal directory, each containing orders, transforms them into JSON events, and publishes them to Kafka for downstream processing.

~~~mermaid
flowchart LR
    FILE["File inbound poller"] --> VF["Validate name/content"]
    VF --> MAP["Transform CSV → OrderEvent"]
    MAP --> CHANNEL["MessageChannel"]
    CHANNEL --> KAFKA["Kafka outbound adapter"]
    VF --> ERR["Invalid file handling"]
    KAFKA --> RETRY["Retry / DLQ / alert"]
~~~

### 24.1. Input and Output Contracts

**Input:** only completed `orders-*.csv` files; each row contains `orderId, amount, tenantId`; files exceeding the policy size limit are rejected.

**Output:** events containing `eventId, eventType, schemaVersion, orderId, amount, tenantId, occurredAt`. The Kafka key should reflect per-order partitioning/ordering needs; payload and encoding must follow the contract.

### 24.2. Layered Testing Strategy

| Layer | Test | Not Needed |
|---|---|---|
| Unit | Valid/invalid CSV parser; validator, mapper, event ID logic | Spring context, broker |
| Flow | File-like message → transformer → mock Kafka boundary; assert payload/headers | Real Kafka |
| File adapter | `@TempDir`, file filter, poller, restart, read-once | Kafka if outbound is mocked |
| Kafka adapter | Test broker, key/topic/partition, serializer, retry | File poller if messages are pushed directly |
| End-to-end | Create file → poll → Kafka → consume with test client → verify event | Mock boundary |

### 24.3. Minimum Test Matrix

1. **One valid file:** exactly one event with accurate contents.
2. **CSV missing column:** no Kafka publish; error recorded with reason.
3. **Incomplete file:** not read before completion.
4. **Two files with same order ID:** verify whether two valid events or duplicate per contract; never guess.
5. **Kafka unavailable:** retry/backoff and file state preserved safely without falsely marking complete.
6. **Publish succeeds but ACK lost:** verify deduplication or reconciliation.
7. **Application restart:** check which files are reprocessed per metadata and commit mechanism.
8. **Two poller instances:** prevent duplicate processing outside policy.
9. **Invalid tenant header:** rejected; never published to the wrong tenant/topic.
10. **Recovery:** broker returns and pending files are processed with evidence.

### 24.4. Evidence Required to Conclude Success

Seeing a mock outbound handler receive an event proves **the flow delivered the message to the boundary**, yet **it does not prove Kafka persisted the event**. Integration tests must verify the broker/consumer observed the event; if downstream services also write to a database, a separate end-to-end test must confirm the final target state.

## 25. Reusable Test Plan Template per Adapter

~~~yaml
# Example test specification, not a direct Spring Integration configuration.
adapterTestPlan:
  id: file-to-kafka-order-events
  owner: integration-team
  inbound:
    type: FILE
    source: isolated-test-directory
    poller:
      controlledStartup: true
      sourceExhaustion: true
  flow:
    inputPayload: File
    outputPayload: OrderEvent
    requiredHeaders: [tenantId, traceId]
    correlationKey: eventId
  outbound:
    type: KAFKA
    target: ephemeral-test-broker
    testTopicPrefix: it-orders-
  isolation:
    unitTestsWithoutSpring: true
    flowTestsWithMockEndpoint: true
    transportTestsWithRealBroker: true
  scenarios:
    - happy-path
    - invalid-csv
    - duplicate-event
    - broker-unavailable
    - retry-after-ack-lost
    - restart-poller
    - wrong-tenant
  evidence:
    - sentMessage
    - targetObservedEvent
    - errorEvent
    - retryCount
    - correlationId
  cleanup:
    - stop-pollers
    - reset-mock-endpoints
    - delete-test-files
    - delete-test-topics
~~~

For HTTP, SFTP, JMS, AMQP, or JDBC, swap the inbound/outbound sections and add protocol semantics while **preserving the separation of flow tests, transport tests, and evidence**.

## 26. Optimizing the Test Suite in CI/CD

### Recommended Execution Cadence

- **Unit + flow isolation**: run on every pull request—fast and deterministic.
- **Adapter integration**: run when adapters/configs/contracts change, or continuously if CI capacity permits.
- **Multi-system end-to-end**: run on a schedule or before major releases, prioritizing high-impact scenarios.
- **Resilience/fault injection**: run under controlled conditions to verify retries, recovery, restarts, and broker unavailability.

### Environmental Requirements

1. Each test has its own directory, topic, queue, schema/records, or namespace.
2. Cleanup runs even when assertions fail.
3. Timestamp logic does not depend on local machine clocks or default timezones.
4. Use compatible dependency versions and pin broker/DB configurations in CI.
5. Enforce bounded timeouts for startup, execution, and teardown; log enough detail for diagnosis.
6. When external systems are unavailable, distinguish **test infrastructure failure** from logic assertion failure where possible.
7. Enable parallel execution only when fixtures, channels, brokers, and state are fully isolated.
8. Save traceable reports: test name, adapter type, correlation/event ID, expected/actual, evidence.

## 27. Anti-Patterns in Spring Integration Testing

| Anti-Pattern | Consequence | Improvement |
|---|---|---|
| **Using a real broker for every test** | Slow suite, infra errors mask logic bugs | Run unit/flow tests first; selective integration tests. |
| **Mocking everything and claiming the adapter works** | Protocol and real side effects go untested | Run adapter tests with real servers/brokers. |
| **Using fixed `Thread.sleep`** | Flaky under varying CI load | Use bounded waits + message/readback observation. |
| **Not resetting `MockIntegrationContext`** | Mocks from earlier tests break later tests | Clean up/reset per lifecycle. |
| **Not isolating directories/topics/queues** | Collisions with stale data or parallel failures | Dedicated fixtures/namespaces per test. |
| **Assuming async `send()` means finished** | Misses off-thread errors | Wait for output signals/evidence. |
| **Assuming all exceptions hit `errorChannel`** | Tests misunderstand sync/async semantics | Verify actual endpoint and error handler config. |
| **Relying on framework message IDs for business dedup** | Retries/transforms create new IDs, breaking idempotency | Use stable event/business keys. |
| **Skipping rollback/ack/offset tests** | Lost or duplicated messages after errors | Test protocol & transaction behavior on real brokers/DBs. |
| **HTTP 200 / Kafka future complete = end-to-end success** | Downstream may still fail or lag | Verify target state/consumption directly. |
| **Leaking secrets in test logs** | Credentials exposed via CI logs | Redact and use synthetic secrets/fixtures. |
| **Testing only one happy path** | Misses schema, timeout, duplicate, security bugs | Build a risk-driven negative test matrix. |

## 28. Practice Exercises

### Exercise 1 — In-Memory Flow

Create a `DirectChannel` accepting `String` payloads, a transformer converting to uppercase, and a `QueueChannel` receiving results.

Requirements:

1. Use `@SpringJUnitConfig` with a minimal context.
2. Send two messages with distinct `traceId` headers.
3. Assert payloads, headers, and ordering per chosen channel semantics.
4. Add blank input to test validation/filtering.
5. Explain why this exercise does not prove SFTP/Kafka connectivity.

### Exercise 2 — Mocking the Outbound Boundary

Build a flow `inputChannel → transformer → HTTP outbound endpoint`.

Requirements:

1. Assign a stable endpoint ID to the outbound handler.
2. Use `@SpringIntegrationTest` and `MockIntegrationContext` to substitute the handler.
3. Verify the HTTP request message has the expected body, destination/reference, and headers.
4. Reset the mock after the test; include a case verifying invalid input is never sent to the boundary.
5. Describe the additional test needed with an HTTP test server to check status codes, timeouts, and retries.

### Exercise 3 — Pollers and File Adapters

Use `@TempDir` to create a source directory, an inbound file adapter, and an output `QueueChannel`.

Requirements:

1. Start the poller in a controlled way to avoid reading files before setup completes.
2. Create a valid file, a pattern-mismatched file, and a partially written file.
3. Assert the valid file is received exactly once per the configured policy.
4. Stop/restart the endpoint and inspect the filter/metadata store.
5. Clean up all files and restore the endpoint.

### Exercise 4 — Testing a Real Transport

Choose one of **SFTP, HTTP, JMS, AMQP, Kafka, or JDBC**.

Requirements:

1. Provision an isolated test environment for the protocol.
2. Write a happy path plus at least three failure cases: authentication/authorization failure, timeout/unavailable, duplicate/redelivery, or transaction rollback.
3. Assert side effects at the target system, not just mock verifications.
4. Document the acknowledge/commit/offset/session semantics matching the protocol.
5. Add cleanup and ensure deterministic CI execution.

### Exercise 5 — Designing a Comprehensive Test Matrix

A pipeline ingests CSV files, publishes to Kafka, and creates database records. Design:

- **Unit tests** for parsers and validators.
- **Flow tests** with a mocked Kafka boundary.
- **Kafka integration tests** on a test broker.
- **Database transaction/idempotency tests** on a suitable database.
- **End-to-end tests** from file to final record.
- **Failure/recovery tests** across broker, database, or application restarts.
- **Security tests** for wrong tenant, path traversal, and secrets in errors.

For each test, specify **inputs, preconditions, observation points, timeouts, pass/fail evidence, and what remains unproven**.

## 29. Acceptance Checklist

A high-quality Spring Integration adapter test suite should satisfy:

- [ ] **Layered testing separation**: unit, flow, adapter integration, and end-to-end.
- [ ] **Lightweight Spring context tests** for channel wiring, payloads, headers, and routes.
- [ ] **Proper use of test utilities**: `@SpringIntegrationTest`/`MockIntegrationContext` for endpoint substitution; mocks never substitute for real protocols.
- [ ] **Controlled poller lifecycles**; tests do not depend on fixed sleeps.
- [ ] **Assertions distinguish sync/async and adapter/gateway** semantics.
- [ ] **Message contract tests**: payload, schema, headers, correlation, and errors.
- [ ] **Tests per transport actually used**: File, SFTP, HTTP, JMS, AMQP, Kafka, or JDBC.
- [ ] **Error, retry, duplicate, ordering, and recovery tests** matching target system semantics.
- [ ] **Idempotency and side-effect checks** for workflows subject to redelivery.
- [ ] **Bounded timeouts, cleanup, and isolation** for filesystems, brokers, DBs, contexts, and endpoints.
- [ ] **No real secrets or production data** in test sources, error logs, or CI reports.
- [ ] **Pass results backed by boundary-accurate evidence**, never equating message sending with completed processing.
- [ ] **Test matrix and diagnostics** separating failures by data, config, environment, or protocol.

## 30. Summary

**Spring Integration test utilities** enable structured message flow testing without spinning up every external system. `MessageBuilder`, `DirectChannel`, `QueueChannel`, `@SpringIntegrationTest`, `MockIntegrationContext`, and Mockito are especially effective for isolating handlers, message sources, and pollers while verifying payloads and headers at flow boundaries.

However, **mocking an endpoint only proves a message reached the simulated boundary**. To confirm File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC work reliably under real conditions, you need protocol-appropriate integration tests verifying acknowledgments, transactions, retries, idempotency, connection lifecycles, and target states. Only by maintaining both forms of evidence—**correct logic inside the flow** and **accurate side effects in external systems**—can a test suite truly keep Spring Integration integrations safe, stable, and maintainable.

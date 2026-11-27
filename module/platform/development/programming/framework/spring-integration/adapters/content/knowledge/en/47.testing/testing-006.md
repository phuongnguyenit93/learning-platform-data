# Testing Outbound Adapters with Mock Clients in Spring Integration

## 1. Learning Objectives

In **Spring Integration**, an *outbound adapter* is an endpoint that receives a `Message<?>` from a **MessageChannel** and executes an operation against an external system: sending an HTTP request, uploading a file over SFTP, publishing to JMS/AMQP/Kafka, writing a file, or updating a database. With an *outbound gateway*, the system also receives a response to feed back into the message flow. **Testing outbound adapters with mock clients** means isolating the client communicating with the external system and verifying **which message was sent, which call occurred, and how success or failure is handled** without depending on a live external service in every test run.

This lesson belongs to the **Testing** chapter of the **Spring Integration Adapters** module (inbound/outbound adapters, gateways, pollers, and MessageChannels connecting File, SFTP, HTTP, JMS, AMQP, Kafka, and databases; managing message contracts, errors, and connection lifecycles).

After this lesson, you will be able to:

- Choose the right **mocking boundary** among the message flow, outbound handler, protocol client, and target system.
- Write **JUnit 5 + Mockito** tests to verify an outbound `MessageHandler` invoked from a `DirectChannel`.
- Assert payloads, headers, routing, call counts, required ordering, and error messages while avoiding assertions on incidental details.
- Use `MockRestServiceServer` or a mock HTTP server when the outbound adapter calls HTTP.
- Use test doubles for SFTP, JMS, RabbitMQ, Kafka, and JDBC with appropriate levels of assurance.
- Understand `MockIntegrationContext` for **replacing the endpoint itself** in the flow when you do not want to run the real client.
- Test retries, timeouts, idempotency, async completion, transactions, shutdown/reconnect, and secret protection.
- Recognize when mocks are **not enough** and integration tests with an isolated SFTP server, broker, database, or HTTP server are required.

**Key takeaway:** A mock client can prove the application **requested sending** data to the transport with the right arguments, yet **cannot prove** that a real server or broker actually received or processed the outcome. Therefore this lesson clearly separates *behavior verified at mock boundary* from *side effect verified at target*.

## 2. Outbound Testing Boundary Map

~~~mermaid
flowchart LR
    SRC["Inbound: file/SFTP/HTTP/broker/DB"] --> IN["inputChannel"]
    IN --> LOGIC["Filter / transform / route"]
    LOGIC --> OUTCH["outboundChannel"]
    OUTCH --> HANDLER["Outbound MessageHandler"]
    HANDLER --> CLIENT["HTTP/SFTP/JMS/AMQP/Kafka/JDBC client"]
    CLIENT --> TARGET["External target"]
    OUTCH -. "mock endpoint" .-> M1["Captured Message<?>"]
    CLIENT -. "mock client" .-> M2["Mockito verify / captor"]
    TARGET -. "integration test" .-> M3["Real side-effect assertion"]
~~~

Choose the substitution boundary based on the question you need to answer:

| Substitution Point | What Still Runs Real? | What Is Proven? | What Is **Not** Yet Proven? |
|---|---|---|---|
| **Mock outbound handler** | Transformer, router, channel, dispatcher | Pre-adapter message meets contract | Protocol mapping and real client |
| **Mock protocol client** | Channel, outbound handler, payload/header mapping logic | Handler called client with expected args and handles client errors | Sockets, auth, transport-level serialization, and real server |
| **Mock HTTP server / test broker / SFTP server** | Both handler and real network client | Protocol exchange, requests, simulated responses/faults | Production system and its full infrastructure |
| **Staging end-to-end** | Near-real integrated system | Business flow and side effects across multiple systems | Rare edge cases, races, and production outages |

**What counts as "enough" depends on the contract.** If you only need to ensure the handler passes the right `partnerId` and `orderId` to the client, mocking the client fits well. If you need guarantees on TCP reconnects, TLS, SFTP host keys, broker acknowledgments, or transaction semantics, mocking a Java method is insufficient.

## 3. Outbound Adapters, Outbound Gateways, and MessageChannels Differ

| Component | Contract | Key Tests |
|---|---|---|
| **Outbound channel adapter** | One-way: receives message and triggers side effect; no business reply emitted | Client called accurately, errors/side effects match |
| **Outbound gateway** | Request–reply: sends request, returns response as a message | Request mapping, response payload/headers, timeouts |
| **DirectChannel** | Synchronous dispatch to one selected handler | Mock client is usually invoked before `send()` returns |
| **ExecutorChannel** | Hands off to thread pool | Use timed verify or wait for completion |
| **QueueChannel** | Consumer polls messages | Sending to the queue does not mean the handler received it |
| **PublishSubscribeChannel** | One message delivered to multiple subscribers | Do not count mock interactions as if there were one consumer |
| **Poller** | Actively reads from source or pollable channel | Must start/control lifecycle so the handler actually executes |

**Mistake:** Asserting `outboundChannel.send(message) == true` and concluding the HTTP upload succeeded. On many channels, `send()` only reflects delivery within the **current channel/endpoint**; it is not confirmation that the external application committed anything.

With a `DirectChannel` running the handler synchronously, exceptions can propagate back to the sending thread. When processing happens on an executor, listener, or poller, exceptions and retries take another path; **tests must match the exact topology**.

## 4. Defining the Message Contract Before Building Mocks

Suppose the system receives an order file and calls a fulfillment service:

~~~text
Input to outbound handler:
  payload: OrderCommand(orderId="42", amount=100)
  header: correlationId="corr-42"
  header: sourceSystem="sftp"
  header: eventId="order-42"

Expected client call:
  partnerClient.submit(
      OrderCommand("42", 100),
      "corr-42"
  )

Expected failure behavior:
  invalid payload/correlation -> reject before calling client
  temporary client outage -> retry/recover per policy
  permanent business error -> fail/reject without blind retry
~~~

The contract should specify:

- **Payload type** and schema accepted by the outbound handler.
- **Required headers** and how they map to URIs/headers/record keys/remote paths/DB columns.
- **Destination** and access scope; never let untrusted inputs arbitrarily steer destinations.
- **Expected send count**; under a retry policy, invocation counts can exceed one.
- **Result semantics**: what does a client method returning normally mean? An ack, a future, or merely enqueued?
- **Timeouts and errors**: when to fail, retry/recover, and block duplicate side effects.
- **Idempotency**: how duplicate business IDs behave when timing out after the target already succeeded.
- **Security**: never capture and print raw tokens/secrets when tests fail.

Do not mock first and infer the contract afterward from `Mockito.verify(...)`. Start from the business behavior, then pick assertions that prove it.

## 5. Dependencies and Version Scope

A typical Java/Spring Integration test setup includes:

| Group | Component | Purpose |
|---|---|---|
| Spring Integration Core | `spring-integration-core` | `IntegrationFlow`, `MessageChannel`, `MessageHandler` |
| Spring Test | `spring-test` | `@SpringJUnitConfig`, Spring test context |
| JUnit 5 | `junit-jupiter` | Test lifecycle and assertions |
| Mockito | `mockito-core` / support via `spring-boot-starter-test` | Mock clients, `verify`, `ArgumentCaptor` |
| Spring Integration Test | `spring-integration-test` | `@SpringIntegrationTest`, `MockIntegrationContext` |
| HTTP | `spring-integration-http`, `spring-test` | HTTP outbound, `MockRestServiceServer` |
| Real transports (per lesson) | SFTP/JMS/AMQP/Kafka/JDBC modules | Real protocol tests against test infrastructure |

**Illustrative Maven dependencies** (for a project using a BOM for version management):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This snippet is **not a complete POM**; artifacts require versions if the project does not use dependency management. For HTTP/SFTP/JMS/AMQP/Kafka/DB, add the specific modules needed for the flow under test rather than importing every adapter just to test one flow.

**HTTP version note:** Starting in Spring Integration **7.1**, HTTP outbound supports `RestClient`, and `RestTemplate`-based configurations are deprecated for gradual migration. `RestTemplate` examples in this lesson illustrate a common testing pattern in maintained codebases; new projects should use the option matching their framework/version and check migration notes. A mock HTTP server operating at the network boundary keeps HTTP client semantics closer to production than mocking a single method.

## 6. Designing Testable Outbound Handlers: Dependency Injection

To mock a client, you need a **dependency injection seam**: the `MessageHandler` must not instantiate an unreplaceable client on its own.

**Hard-to-test design:**

~~~java
// Anti-pattern: client is instantiated directly inside the handler.
class HardToTestOutbound {
    void send(OrderCommand command) {
        PartnerSdkClient sdk = new PartnerSdkClient("https://partner.example");
        sdk.submit(command); // Cannot inject a mock normally.
    }
}
~~~

A more testable approach:

~~~java
interface PartnerClient {
    void submit(OrderCommand order, String correlationId);
}

record OrderCommand(String orderId, int amount) {}

final class OrderOutboundHandler implements MessageHandler {

    private final PartnerClient client;

    OrderOutboundHandler(PartnerClient client) {
        this.client = client;
    }

    @Override
    public void handleMessage(Message<?> message) {
        if (!(message.getPayload() instanceof OrderCommand order)) {
            throw new MessageHandlingException(
                    message, "Expected OrderCommand payload");
        }

        Object correlation = message.getHeaders().get("correlationId");
        if (!(correlation instanceof String id) || id.isBlank()) {
            throw new MessageHandlingException(
                    message, "Missing correlationId");
        }

        client.submit(order, id);
    }
}
~~~

Required imports for the snippet above are `org.springframework.messaging.Message`, `org.springframework.messaging.MessageHandler`, and `org.springframework.messaging.MessageHandlingException`. `PartnerClient` is an **application-defined interface** whose production implementation calls HTTP/SFTP/etc.; `OrderCommand` is an illustrative DTO. Java records and pattern matching use modern Java syntax (at least Java 17 for that combination). Never place production endpoint URLs, passwords, or tokens in examples.

**Benefit:** you can test payload/header validation and client invocation without any network. At the same time, keeping the real client implementation separate lets you test serialization, HTTP headers, TLS, and credentials at the adapter/transport layer.

### 6.1. What to Mock and What Not to Mock?

| Component | Recommendation |
|---|---|
| `PartnerClient` interface | Mock in handler tests; verify method/arguments |
| Pure mappers/validators | Usually keep real to test internal contracts |
| `MessageChannel` + `IntegrationFlow` | Keep real in flow tests to verify wiring |
| Low-level HTTP client/SDK | Mock in unit tests; add mock server tests |
| Network/broker/database | Use test infrastructure for integration tests |
| Clock/ID generator | Fake or inject if governing timeouts/idempotency |
| Retry scheduler | Keep deterministic in tests; use short delays/backoff if needed |
| Logger/metrics | Verify key events/metadata; avoid brittle log-wording assertions |

**Do not mock `MessageChannel` when the goal is verifying channel-to-endpoint wiring.** Send messages through the real channel and verify the mock client behind it.

## 7. JUnit 5 + Mockito Test Through a Real DirectChannel

The example below uses a **real outbound `MessageHandler`** and a **mocked `PartnerClient`**. Beans are declared in a lightweight Spring test context; no external server is needed.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OutboundHandlerTest.Config.class)
class OutboundHandlerTest {

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        PartnerClient partnerClient() {
            return mock(PartnerClient.class);
        }

        @Bean("outboundOrders")
        MessageChannel outboundOrders() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow outboundFlow(PartnerClient client) {
            return IntegrationFlow.from("outboundOrders")
                    .handle(new OrderOutboundHandler(client))
                    .get();
        }
    }

    @Autowired
    @Qualifier("outboundOrders")
    MessageChannel outboundOrders;

    @Autowired
    PartnerClient partnerClient;

    @BeforeEach
    void clearMockInteractions() {
        reset(partnerClient);
    }

    @Test
    void sendsTheExpectedOrderWithCorrelation() {
        OrderCommand command = new OrderCommand("42", 100);

        boolean accepted = outboundOrders.send(
                MessageBuilder.withPayload(command)
                        .setHeader("correlationId", "corr-42")
                        .build()
        );

        assertTrue(accepted);
        verify(partnerClient, times(1))
                .submit(eq(command), eq("corr-42"));
        verifyNoMoreInteractions(partnerClient);
    }

    @Test
    void missingCorrelationDoesNotInvokeClient() {
        OrderCommand command = new OrderCommand("42", 100);

        assertThrows(RuntimeException.class, () ->
                outboundOrders.send(
                        MessageBuilder.withPayload(command).build()
                )
        );

        verifyNoInteractions(partnerClient);
    }
}
~~~

**To run sections 6 and 7 together**, place `PartnerClient`, `OrderCommand`, and `OrderOutboundHandler` in Java files or the same test package per Java visibility rules, using the Spring Messaging imports listed in section 6. The test intentionally references those defined types rather than creating duplicate mismatched ones. The test config uses Mockito to mock `PartnerClient`, while the message handler and channel are real components.

**What is proven:** message traverses `DirectChannel`, handler is dispatched, payload/correlation are validated, client receives exact arguments, and a message missing correlation is rejected **before** the client is called.

**What is not proven:** HTTP POST headers, real SFTP file uploads, broker publish confirmations, database transaction commits, or retries on network drops.

### 7.1. Avoid Assertions Relying Only on send()

On a synchronous `DirectChannel`, the mock call completes before `send()` returns; hence calling `verify(...)` right after `send()` is sound for this topology. If switched to an `ExecutorChannel` or pollable channel, use a bounded wait instead of immediate `verify(...)`.

### 7.2. Exception Types May Be Wrapped by the Framework

A handler may throw `MessageHandlingException`, while Spring Integration's dispatch layer may rethrow a wrapped exception depending on context/advice. The example uses `assertThrows(RuntimeException.class)` to focus on "rejected before sending"; stricter tests can inspect the **cause chain** and standardized business error codes. Avoid asserting exact stack traces or non-contract wrapper classes.

### 7.3. When Is No Spring Context Needed?

If you only test input validation on `OrderOutboundHandler`, instantiate the handler directly:

~~~java
PartnerClient client = mock(PartnerClient.class);
OrderOutboundHandler handler = new OrderOutboundHandler(client);

Message<?> msg = MessageBuilder
        .withPayload(new OrderCommand("42", 100))
        .setHeader("correlationId", "corr-42")
        .build();

handler.handleMessage(msg);
verify(client).submit(new OrderCommand("42", 100), "corr-42");
~~~

This is a **handler unit test**, not an `IntegrationFlow` wiring test. Keep both test types when the workflow must prove channel connectivity as well.

## 8. Using ArgumentCaptor to Verify Payload/Header Mapping

Many clients accept a DTO different from the incoming payload—for example, an HTTP client receiving `ShipmentRequest` built from `OrderCommand`. Use `ArgumentCaptor` to inspect the **actual constructed argument**, not just that a call happened.

~~~java
ArgumentCaptor<ShipmentRequest> requestCaptor =
        ArgumentCaptor.forClass(ShipmentRequest.class);

verify(client).submit(
        requestCaptor.capture(),
        eq("corr-42")
);

ShipmentRequest sent = requestCaptor.getValue();
assertEquals("42", sent.orderId());
assertEquals(100, sent.amount());
assertEquals("v1", sent.schemaVersion());
~~~

This snippet targets an **appropriate application interface/DTO**, not a direct continuation of `PartnerClient` from section 7 (where `submit` took `OrderCommand`). To apply it, define `ShipmentRequest` and the matching client method.

With multiple calls:

~~~java
ArgumentCaptor<ShipmentRequest> requests =
        ArgumentCaptor.forClass(ShipmentRequest.class);

verify(client, times(3)).submit(requests.capture(), anyString());

List<ShipmentRequest> all = requests.getAllValues();
assertEquals(3, all.size());
assertEquals(Set.of("41", "42", "43"),
        all.stream().map(ShipmentRequest::orderId)
                .collect(Collectors.toSet()));
~~~

Consider **whether arbitrary ordering is allowed**. If the flow runs in parallel, compare the set of business IDs instead of assuming call order; if a message can be retried, distinguish **3 business messages** from **3 attempts** for one message.

### 8.1. Using verifyNoInteractions Appropriately

`verifyNoInteractions(client)` fits cases where bad inputs are blocked **before** the outbound boundary. However, if policy defines retries/recovery or metrics routed through the same mocked client, "no interactions" may be too strict. Assert **no dangerous send call occurred** rather than forbidding unrelated interactions.

### 8.2. Do Not Assert Meaningless Implementation Details

If the business contract only requires one valid request sent to the partner, do not assert the exact call order of loggers, mappers, and metrics. Do assert destination, payload, correlation/idempotency key, and side-effect count wherever data integrity depends on them.

## 9. HTTP Outbound Adapters: Mock HTTP Clients Instead of Everything

HTTP clearly illustrates the difference between mocking a **Java interface** and mocking an **HTTP exchange**. Two common approaches exist:

1. **Mockito mock of `PartnerClient` or `RestOperations`:** suitable when only checking that code calls the right method/arguments; skips real serialization and interceptors.
2. **`MockRestServiceServer` or a mock HTTP server:** exercises most of the app's HTTP client pipeline, inspects method/URI/body/headers, and returns simulated responses. A real socket-based mock server like WireMock/MockWebServer also exercises timeouts and network behavior.

### 9.1. Using MockRestServiceServer for HTTP Outbound Channel Adapters

The example below uses Spring Integration Java DSL with `RestTemplate` **for versions supporting this configuration**. It uses `MockRestServiceServer` to intercept HTTP requests before they hit the network.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.http.dsl.Http;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

@SpringJUnitConfig(HttpOutboundAdapterTest.TestConfig.class)
class HttpOutboundAdapterTest {

    @Configuration
    @EnableIntegration
    static class TestConfig {
        @Bean
        RestTemplate partnerRestTemplate() {
            return new RestTemplate();
        }

        @Bean("ordersHttpOut")
        MessageChannel ordersHttpOut() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow httpOutboundFlow(RestTemplate partnerRestTemplate) {
            return IntegrationFlow.from("ordersHttpOut")
                    .handle(Http.outboundChannelAdapter(
                            "https://partner.example/api/orders",
                            partnerRestTemplate)
                            .httpMethod(HttpMethod.POST))
                    .get();
        }
    }

    @Autowired
    RestTemplate partnerRestTemplate;

    @Autowired
    @Qualifier("ordersHttpOut")
    MessageChannel ordersHttpOut;

    @Test
    void outboundAdapterPostsJsonToExpectedUri() {
        MockRestServiceServer server =
                MockRestServiceServer
                        .bindTo(partnerRestTemplate)
                        .build();

        server.expect(requestTo(
                    "https://partner.example/api/orders"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().json(
                    "{\"orderId\":\"42\",\"amount\":100}"))
                .andRespond(withSuccess(
                    "", MediaType.APPLICATION_JSON));

        assertTrue(ordersHttpOut.send(
                MessageBuilder
                        .withPayload(
                            "{\"orderId\":\"42\",\"amount\":100}")
                        .setHeader(
                            MessageHeaders.CONTENT_TYPE,
                            MediaType.APPLICATION_JSON_VALUE)
                        .build()));

        server.verify();
    }
}
~~~

**Critical point:** `MockRestServiceServer` binds to the **exact `RestTemplate` instance** used by the outbound handler. If the app creates a separate `RestTemplate` inside the handler, the mock server will never intercept requests. Hence **client dependency injection is a prerequisite for meaningful tests**.

In newer Spring Integration releases, `RestClient` is preferred. Bind `MockRestServiceServer` to the appropriate builder/client per Spring Framework version, or use a mock HTTP server while keeping the same request/response contract. Avoid copying deprecated `RestTemplate` overloads into new projects without checking versions.

**What `server.verify()` proves:** the request matched Spring Test's mock server expectations; **it does not prove** real TLS, DNS, proxies, load balancers, or the production API succeeded.

### 9.2. Checking Custom Headers

A message header named `correlationId` does **not automatically** become an HTTP header `X-Correlation-Id`. Configure a header mapper or transformer in the flow and assert the actual HTTP request hitting the mock server:

~~~java
// Add after .andExpect(method(HttpMethod.POST))
// once the outbound handler is configured to map the header properly:
.andExpect(header("X-Correlation-Id", "corr-42"))
~~~

If code only sets `correlationId` on the Spring message without HTTP header mapping, this assertion rightly fails. **The test catches missing mappings**—do not "fix" it by deleting the contract assertion.

### 9.3. Negative Tests for HTTP 4xx, 5xx, and Timeouts

An HTTP handler using a client may encounter:

| Outcome | Expected Behavior |
|---|---|
| 201/204 per contract | Success; one-way adapter does not necessarily emit a reply |
| 400 from invalid payload | Business error; no infinite retries |
| 401/403 | Authentication/authorization failure; never log raw tokens |
| 409 | Handle conflict/idempotency per external API |
| 429/503 | May retry with backoff if policy permits |
| Timeout after sending request | **Outcome uncertain**; server may already have processed it |

With `MockRestServiceServer`, use `andRespond(withServerError())` or specific error statuses to verify exception mapping. To reproduce connection resets, closed sockets, TLS handshakes, or network-level delays, a **socket-based mock server** fits better because it preserves near-production HTTP network/client code paths.

### 9.4. Outbound Adapters and Gateways Have Different Reply Contracts

`Http.outboundChannelAdapter(...)` has one-way semantics; tests primarily verify **the request was issued** and errors are handled properly.

`Http.outboundGateway(...)` is used when expecting the **HTTP response as a reply message**, requiring tests for:

- Response body/status/headers routed to the right channel.
- Replies accurately correlated with requests.
- Missing replies, timeouts, and invalid responses routed to the defined error path.
- Concurrent requests never mismatch replies across callers.

Do not call `outputChannel.receive(...)` on a one-way outbound adapter expecting a reply unless the flow explicitly adds another endpoint.

## 10. Mockito Client Mocking at Protocol and Object-Mapping Boundaries

When an outbound implementation uses a dedicated SDK interface:

~~~java
interface ShippingApi {
    ShipmentReceipt createShipment(ShipmentRequest request);
}

record ShipmentRequest(String orderId, int amount) {}
record ShipmentReceipt(String shipmentId) {}
~~~

Tests can stub it:

~~~java
ShippingApi api = mock(ShippingApi.class);

when(api.createShipment(
        eq(new ShipmentRequest("42", 100))))
        .thenReturn(new ShipmentReceipt("sh-42"));

// Trigger the outbound gateway/service activator using api...
verify(api).createShipment(
        eq(new ShipmentRequest("42", 100)));
~~~

This snippet shows **only the client boundary pattern**, without declaring the full gateway/flow. In a complete test, a real handler receives `Message<ShipmentRequest>`, calls `api.createShipment(...)`, and returns `ShipmentReceipt` so the gateway/flow builds a reply message.

If the client returns a callback or `CompletableFuture` instead of returning synchronously, the test must complete the future in a controlled way before asserting output. Mockito `verify(api)` proves only that the client method was invoked; **the future completing successfully** is independent evidence.

### 10.1. Do Not Mock the Mapper When Testing Mapping

Suppose a handler takes `OrderCommand` and builds `ShipmentRequest`. If you mock `ShipmentRequestMapper` to return a canned object, the test proves only that the handler called the mapper—**not** that the right `orderId`/`amount` fields were mapped. Keep core mappers real or cover them with dedicated unit tests.

### 10.2. Captors and Dangerous Arguments

Some outbound adapters derive remote paths or URIs from headers. Tests should verify paths/URIs cannot be steered outside allowlists by untrusted inputs:

~~~text
Expected:
  bucket/path stays inside allowed namespace
  rejects "../" directory traversal
  rejects user-supplied URLs pointing to internal networks
  tenantId bound to authenticated principal
~~~

Do not write only `verify(client).send(any())`: destination arguments can be wrong even when the method was called. For sensitive payloads, **capture metadata** like resource IDs and checksums instead of printing raw secrets in failure reports.

## 11. Using MockIntegrationContext to Replace the Outbound Handler

Sometimes you do not want to mock the client inside an adapter, but instead **replace the entire outbound endpoint handler** to test upstream mapping flows. Spring Integration provides `@SpringIntegrationTest` and `MockIntegrationContext` for this purpose.

~~~mermaid
flowchart LR
    INPUT["inputChannel"] --> MAP["Mapper / filter / router"]
    MAP --> OUT["outboundChannel"]
    OUT --> REAL["Real outbound handler"]
    OUT -. "replace in test" .-> MOCK["MockMessageHandler / captor"]
    MOCK --> ASSERT["Inspect Message<?>"]
~~~

Illustrative test for an endpoint with ID `partnerOutboundEndpoint`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.integration.test.mock.MockIntegration.*;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ProductionLikeFlowConfig.class)
@SpringIntegrationTest
class OutboundEndpointReplacementTest {

    @Autowired
    MockIntegrationContext mockIntegrationContext;

    @Autowired
    MessageChannel outboundInput;

    @AfterEach
    void restoreOriginalHandler() {
        mockIntegrationContext.resetBeans();
    }

    @Test
    void observesMessageBeforeRealTransport() {
        ArgumentCaptor<Message<?>> captor =
                ArgumentCaptor.forClass(Message.class);

        MessageHandler mockHandler = mockMessageHandler(captor);

        mockIntegrationContext.substituteMessageHandlerFor(
                "partnerOutboundEndpoint", mockHandler);

        outboundInput.send(new GenericMessage<>("order-42"));

        Message<?> captured = captor.getValue();
        assertEquals("order-42", captured.getPayload());
    }
}
~~~

**Assumptions:** `ProductionLikeFlowConfig` is a configuration provided by the app/test, `outboundInput` is the flow's channel, and `partnerOutboundEndpoint` is the **consumer endpoint ID** wrapping the handler to replace. This ID must be exact; **never substitute a channel name for an endpoint ID**. For async outputs, wait/verify with a timeout before reading the captor. Generic Mockito APIs may require appropriate compiler warning suppressions.

`MockIntegrationContext.resetBeans()` restores substituted endpoints after the test. Skipping cleanup can cause the next test to silently hit the mock handler instead of the real adapter.

**Key comparison:**

- **Mock client**: real handler executes; tests converting messages into client calls.
- **Mock handler**: real handler does not execute; checks only that messages reach the end of the flow.
- **Mock server**: real handler and client run over HTTP; tests protocol requests/responses at the network boundary.

Never treat these three techniques as equivalent.

## 12. SFTP Outbound: Mock SessionFactory or Mock RemoteUploader?

SFTP outbound typically involves **SSH sessions**, remote directories, renames, temporary files, write streams, retries, and dropped connections. There are multiple testing levels:

1. **Mock an application-defined façade**, such as `RemoteUploader.upload(InputStream, remotePath)`: simple, stable, ideal for testing `MessageHandler` path/content selection.
2. **Mock Spring Integration `SessionFactory`/`Session`**: closer to the protocol, yet requires understanding how the adapter opens/closes sessions and sequences `write/rename/exists`; easily couples tests to framework internals.
3. **Isolated SFTP server**: verifies host keys, auth, file writes, connection resets, and remote readback.

Example façade:

~~~java
interface RemoteUploader {
    void upload(byte[] content, String remotePath);
}

record TransferRequest(String fileName, byte[] content) {}

final class ExportOutboundHandler implements MessageHandler {

    private final RemoteUploader uploader;

    ExportOutboundHandler(RemoteUploader uploader) {
        this.uploader = uploader;
    }

    @Override
    public void handleMessage(Message<?> message) {
        TransferRequest request =
                (TransferRequest) message.getPayload();

        if (!request.fileName().matches("[a-zA-Z0-9_-]+\\.csv")) {
            throw new IllegalArgumentException("Invalid file name");
        }

        uploader.upload(
                request.content(),
                "/partners/orders/" + request.fileName());
    }
}
~~~

Façade mock test:

~~~java
RemoteUploader remoteUploader = mock(RemoteUploader.class);
ExportOutboundHandler handler =
        new ExportOutboundHandler(remoteUploader);

byte[] bytes = "orderId\n42\n"
        .getBytes(StandardCharsets.UTF_8);
handler.handleMessage(MessageBuilder
        .withPayload(new TransferRequest("orders_42.csv", bytes))
        .build());

ArgumentCaptor<byte[]> capturedBytes =
        ArgumentCaptor.forClass(byte[].class);

verify(remoteUploader, times(1)).upload(
        capturedBytes.capture(),
        eq("/partners/orders/orders_42.csv"));

assertArrayEquals(bytes, capturedBytes.getValue());
~~~

JUnit/Mockito/Spring Messaging imports are omitted in this snippet; `RemoteUploader` and `TransferRequest` are illustrative application types. **Never assert file content using `byte[].toString()`**. If production requires atomic SFTP upload via temporary name followed by rename, add a lower-level test (façade implementation or SFTP server) proving that sequence.

### 12.1. Never Weaken Security in SFTP Tests

If the real client validates SSH host keys, a mocked façade **does not prove host-key validation**. An integration test with a test SFTP server must supply trusted host keys and test that invalid host keys are rejected; never disable verification for test convenience.

### 12.2. Simulating Disconnects and Partial Uploads

A mock client can throw an exception inside `upload`, yet that does not distinguish **"nothing written"** from **"partially written."** When recovery logic depends on those two states, test against a test SFTP server or stateful fake simulating partial files, temporary suffixes, and renames, then verify cleanup/idempotency.

## 13. File Outbound Adapters: When to Use a Temp Directory Instead of Mocks

For local files, **a real filesystem inside a temp directory** is usually cheaper and more trustworthy than mocking NIO/`Files` statics. A file outbound adapter test can:

1. Create `@TempDir` as the output directory.
2. Configure the outbound handler with that directory.
3. Send messages through the channel as in production.
4. Assert the file exists with the right name, content/encoding, and overwrite policy.
5. Confirm no incomplete temp files remain, then tear down.

~~~java
@TempDir
Path outputDir;

// After the fixture configures the real file outbound adapter:
Message<String> msg = MessageBuilder
        .withPayload("orderId,total\n42,100\n")
        .setHeader("targetFileName", "orders-42.csv")
        .build();

assertTrue(outboundInput.send(msg));

Path file = outputDir.resolve("orders-42.csv");
assertTrue(Files.exists(file));
assertEquals(
        "orderId,total\n42,100\n",
        Files.readString(file, StandardCharsets.UTF_8));
~~~

This snippet illustrates **the assertions inside a fixture-backed test**: `outboundInput` and filename mapping config belong to the test setup, not the snippet itself. If the handler runs on an executor, wait for the file to exist with a bounded timeout.

For file adapters, **reading back from the filesystem** beats `verify(mockFileWriter).write(...)` because many bugs hide in paths, write permissions, temp filenames, flush/rename, or encoding. You can still mock a file writer wrapper in fast business-mapping unit tests.

## 14. JMS Outbound: Mocking JmsTemplate and the Ack Gap

A JMS outbound adapter may delegate to `JmsTemplate` or an equivalent abstraction. With a custom sender façade:

~~~java
interface QueuePublisher {
    void publish(String destination, String body);
}

// Application handler unit test:
QueuePublisher publisher = mock(QueuePublisher.class);
OrderOutboundHandler handler = /* handler calling publisher */;
handler.handleMessage(/* OrderCommand inside Message<?> */);
verify(publisher).publish(
        eq("orders.outbound"),
        eq("{\"orderId\":\"42\"}"));
~~~

This snippet **omits handler implementation** to focus on the seam. If mocking `JmsTemplate` directly, depending on configuration you can verify `convertAndSend(destination, payload)`, keeping in mind a real Spring Integration JMS adapter may use custom converters, session/connection factories, and headers; **verifying a mock method does not prove the JMS provider accepted or committed the message**.

Integration tests require a test JMS broker to verify queues/topics, message conversion, properties, acks/transactions, broker outages, and redelivery. For JMS transactions, verify real rollback/retry behavior against your exact provider and listener container.

## 15. RabbitMQ/AMQP Outbound: Mocking RabbitTemplate Doesn't Replace Confirms

For RabbitMQ, you can mock your application's **publisher abstraction** or `RabbitTemplate` when verifying exchanges and routing keys:

~~~java
RabbitTemplate rabbitTemplate = mock(RabbitTemplate.class);

MessageHandler handler = /* adapter/handler injected with template */;
handler.handleMessage(/* order event */);

// When the handler actually selects this method:
verify(rabbitTemplate).convertAndSend(
        eq("orders.events"),
        eq("order.created"),
        any());
~~~

This code illustrates **assertion shape**, not a standalone test class. The real API has many overloads; if the handler uses `MessagePostProcessor` or confirmation callbacks, verify the exact overload and mapped message fields. Avoid overusing `any()` when exchange/routing key are part of the business contract.

**Publisher confirms/returns, bindings, durability, nacks, and DLX/DLQ** require a test broker; mocking `RabbitTemplate` cannot reproduce them faithfully. A client method returning normally does not guarantee a message routed to a queue with active consumers.

## 16. Kafka Outbound: Mocking KafkaTemplate and Testing Async Results

Kafka producers usually return an **asynchronous result**. Depending on the Spring Kafka version, `KafkaTemplate.send(...)` returns a `CompletableFuture<SendResult<...>>`; older versions had different async signatures. Tests must separate three questions:

1. **Publish arguments:** are topic, partition/key, payload, and headers accurate?
2. **Producer outcome:** how does the future complete on success/failure, and how does the adapter observe failures?
3. **Consumer outcome:** did a real consumer read and process the record?

Example at the **`KafkaTemplate` boundary** if the handler sends topic/key/value:

~~~java
// Assumes handler actually calls send(topic, key, value).
KafkaTemplate<String, OrderEvent> template =
        mock(KafkaTemplate.class);

OrderEvent event = new OrderEvent("42", 100);

// Stub future matching your Spring Kafka version's signature.
when(template.send(eq("orders.events"),
                   eq("42"), eq(event)))
        .thenReturn(CompletableFuture.completedFuture(
                mockedSendResult));

// Trigger outbound handler...
verify(template, times(1)).send(
        "orders.events", "42", event);
~~~

`mockedSendResult` is a fixture of type `SendResult<String, OrderEvent>`; construct or stub it cleanly for your version. This is an **illustrative snippet**, not standalone copy-paste code. If the implementation sends `ProducerRecord` or calls `send(Message<?>)`, verify **the exact overload**.

### 16.1. Failure After the Client Method Returns

A `send(...)` returning a failed future is not the same as throwing a synchronous exception. Tests should return a `CompletableFuture` completed exceptionally and prove:

- The handler/advice/callback or error flow **observes the failure** rather than silently dropping the future.
- Retries/recovery respect configured attempt limits and bounds.
- Business success is never reported before required producer confirmations arrive.
- Sufficient business IDs exist to correlate the send attempt with the outcome.

**Never treat `verify(template).send(...)` as proof that the Kafka broker persisted the message.** For broker semantics, use Kafka test infrastructure, read from the topic with a dedicated test consumer group/topic, and verify record keys/schemas/headers. For downstream side effects, run the consumer or check the sink.

### 16.2. Idempotency and Kafka

Kafka provides mechanisms for producer reliability and scoped transactions under proper configurations, yet never claim **end-to-end exactly-once from Kafka to HTTP/databases outside that transaction**. Tests must simulate consumer crashes, retries, and duplicate event IDs to prove application side effects remain safe.

## 17. Database Outbound: Mock JdbcTemplate or Use a Test Database?

For JDBC outbound adapters or DB-writing service activators, mocking `JdbcTemplate` can verify SQL and parameters:

~~~java
JdbcTemplate jdbc = mock(JdbcTemplate.class);

// Application handler test calls:
jdbc.update(
        "UPDATE orders SET status=? WHERE id=?",
        "SENT", "42");

// Typical assertion when executed through the handler:
verify(jdbc).update(
        eq("UPDATE orders SET status=? WHERE id=?"),
        eq("SENT"),
        eq("42"));
~~~

In this snippet, `jdbc.update(...)` shows **the call the handler is expected to make**, not something the test should call itself right before `verify` in a real unit test. Proper tests trigger the handler and then verify the mock. Always parameterize SQL instead of concatenating user inputs into query strings.

A JDBC mock does **not** verify:

- Whether SQL is valid for the target database engine.
- Schema constraints, indexes, transactions, and isolation levels.
- Whether DB rows actually changed or committed.
- Whether locks/unique constraints protect concurrent writers.
- Rollback/retry behavior when the driver loses connectivity.

Therefore, whenever logic depends on constraints, transactions, and real row counts, use an **isolated database** (such as a compatible PostgreSQL test container), run the outbound flow, and inspect rows after commit. For file/database adapters, a **cheap near-real test** is often far more reliable than mocking all I/O.

### 17.1. Checking Updated Row Counts

If a handler inspects the row count returned by `JdbcTemplate.update(...)`, getting 0 or more than 1 can indicate a business error. Stub return values of 0, 1, >1, and exceptions to verify handler decisions:

~~~text
0 rows updated -> not found or stale state
1 row updated  -> success per contract
>1 rows        -> data integrity error if only one order should update
DB outage      -> retry or recovery per policy
~~~

Ultimately, claiming "exactly one record updated" requires checking a **real DB**, not just Mockito stubbing `thenReturn(1)`.

## 18. Gateways and Request–Reply: Mock Clients Returning Meaningful Results

For outbound gateways, returning a response is part of the contract. Suppose a client method:

~~~java
interface ShippingGatewayClient {
    ShipmentReceipt create(ShipmentRequest request);
}

record ShipmentReceipt(String shipmentId, String status) {}
~~~

Tests must verify both outbound and return paths:

1. Input message contains a valid request.
2. Handler/gateway invokes client with right payload, correlation, and destination.
3. Mock client returns a valid response.
4. Gateway constructs a reply message of the right type and sends it to the **reply channel** or caller return value.
5. Timeouts/exceptions are never misreported as success.

Conceptual example:

~~~text
Gateway input:
  shipment-request(orderId=42), correlationId=corr-42

Mock client:
  create(42) -> ShipmentReceipt(sh-42, ACCEPTED)

Expected reply:
  payload: ShipmentReceipt(sh-42, ACCEPTED)
  correlationId: corr-42
~~~

Not every adapter/gateway preserves all message headers by default; when correlation is required on replies, explicitly configure and test header propagation.

### 18.1. Client Returns Null, Missing Reply, or Invalid Schema

Test what happens when the mock client returns `null` or a schema-invalid response; depending on contract, the gateway may time out, return null, or emit an error. **Do not write assertions assuming every gateway throws the same exception.** Base checks on the defined business behavior using bounded timeouts.

### 18.2. From Request–Reply to Async Callbacks

If the client returns `CompletableFuture`, `Mono`, or uses callbacks, tests must drive completion:

- Future succeeds → expected output/reply.
- Future fails → expected error flow/recoverer.
- Future never completes → timeout without hanging the suite.
- Request cancelled or adapter stopped → no connections used after shutdown.

A mock client returning an already-completed future **does not test** async race handling; add tests where the future completes after the flow yields control.

## 19. Synchronous and Asynchronous Errors: Testing at the Right Observation Point

With `DirectChannel` and a synchronous handler, a mock client throwing an exception can make `send()` throw:

~~~java
doThrow(new IllegalStateException("simulated transport failure"))
        .when(partnerClient)
        .submit(any(), anyString());

RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> outboundOrders.send(
                MessageBuilder
                    .withPayload(new OrderCommand("42", 100))
                    .setHeader("correlationId", "corr-42")
                    .build()));

assertNotNull(failure);
verify(partnerClient).submit(any(), eq("corr-42"));
~~~

**`partnerClient`, `outboundOrders`, and `OrderCommand` come from section 7's fixture.** This illustrates synchronous error testing. The outer exception class may vary with wrapping/advice; assert the underlying cause and business outcome rather than locking onto stack-trace wording.

With inbound pollers, broker listeners, or `ExecutorChannel`, exceptions cannot return to a caller that already returned. Instead, they may be handled by:

- The polling endpoint's or listener container's error handler.
- `errorChannel`, including header-specified channels where supported.
- `RequestHandlerRetryAdvice`/retry templates or broker retry mechanisms.
- Recoverers/DLQ/DLT or outbox retry records.

**Do not assume creating an `errorChannel` bean routes all errors there automatically.** Verify the actual endpoint type and error handler configuration.

### 19.1. Testing Error Output

If an error flow explicitly routes to `PollableChannel errors`, assert:

~~~java
Message<?> error = errors.receive(2000);
assertNotNull(error);
assertInstanceOf(ErrorMessage.class, error);

Throwable cause = (Throwable) error.getPayload();
assertNotNull(cause);
~~~

This requires importing `org.springframework.messaging.support.ErrorMessage`; `errors` is declared by the test config. If a synchronous handler has no bridge to an error channel, use `assertThrows` on the caller instead of calling `errors.receive(...)` and timing out.

### 19.2. Pitfall When Mocking a Single Exception Throw

Without retry advice attached to the endpoint, code like:

~~~java
doThrow(new RuntimeException("temporary"))
    .doNothing()
    .when(client).submit(any(), anyString());
~~~

**does not make Spring Integration retry automatically**. It merely configures the mock to throw on the first call and succeed on a second call **if something actually calls it a second time**. To test retries, configure real retry policies on the handler/advice and assert `verify(client, times(2))` once the flow settles.

## 20. Testing Retries/Backoff with Controlled Mock Clients

A proper retry test specifies:

| Error Type | Suggested Policy (Illustrative) | Assertion |
|---|---|---|
| Transient network timeout / 503 | Bounded retries, backoff | Attempt count, outcome/recovery |
| 400 invalid payload | No retry | Single call, routed to reject branch |
| 401/403 | No blind retries; handle credentials/policy | Never log tokens; alert per risk |
| Transient DB deadlock | Bounded retry if operation is safe | No duplicated transaction side effects |
| Partial SFTP upload | Depends on atomic rename and cleanup support | Incomplete file never emitted as complete |
| Broker send failure | Proper async ack/future handling | Never report delivered without ack |

**Preserve production retry semantics in tests while controlling elapsed time.** If production uses multi-minute exponential backoff, configure shorter delays for tests without dropping attempt counts, exception filters, recovery, or stop conditions.

Example assertion (only when retry is configured on the endpoint):

~~~java
doThrow(new TransientPartnerException("connection lost"))
        .doNothing()
        .when(client).submit(any(), anyString());

inputChannel.send(validMessage);

// Assert immediately for sync flows; await for async flows.
verify(client, times(2)).submit(any(), eq("corr-42"));
verifyNoMoreInteractions(client);
~~~

`TransientPartnerException`, `inputChannel`, and `validMessage` are illustrative fixtures. **Do not paste this into a test lacking retry advice and expect it to pass**.

### 20.1. Retrying Is Not Sending Two Business Operations

A call can time out **after the server already processed it**. Upon retry, the request could create a duplicate order if the API lacks idempotency. Mock client tests cannot prove the server avoids duplicates when a response is lost. Add **stateful** mock server or database tests tracking side effects by `eventId`/idempotency key.

### 20.2. Exhausted Retries and DLQ/Recoverer

When all attempts fail, verify:

- Error message/correlation reaches the recoverer or dedicated queue.
- Business status is never falsely marked `SENT`/`COMPLETED`.
- No infinite retries piling up backlogs.
- Sufficient metadata exists for operator investigation without raw bearer tokens/secrets.
- Replays enforce idempotency and track attempts.

### 20.3. Distinguish Attempt Counts from Message Counts

If one input is sent once and retries call `client.submit(...)` three times, `times(3)` measures **attempts**, not three distinct business messages. State this clearly in test names and reports. When testing 3 distinct messages, use unique business IDs and `ArgumentCaptor`.

## 21. Async Mockito.verify and Reliable Completion Points

In flows using `ExecutorChannel`, task executors, Kafka futures, or callbacks, verifying immediately after `send()` can race. You can use:

~~~java
input.send(validMessage);

verify(partnerClient, timeout(2000).times(1))
        .submit(any(), eq("corr-42"));
~~~

`Mockito.timeout(...)` only waits for the **mock interaction**; it does not guarantee the remote operation finished, and if retries fire afterward, seeing one call does not prove "only one call occurred."

For stronger guarantees:

- Use `CountDownLatch` or `CompletableFuture` to confirm endpoint completion per contract.
- Wait for side effects on the mock server/DB with an explicit deadline.
- When asserting "no second call," ensure retry schedulers/flows finished or observe over a defined window.
- Never use fixed `Thread.sleep(...)` as your sole mechanism.

### 21.1. Out-of-Order Interactions

When messages dispatch concurrently, use captors to compare **sets of keys** instead of assuming call order unless the contract guarantees ordering (e.g., per partition key). Mockito's `InOrder` applies only when client call order is part of the contract and truly preserved by channels/executors.

### 21.2. Backpressure and Channel Capacity

Mock clients usually respond instantaneously, **hiding** slow-downstream queue buildup. Tests can use a fake client with a barrier/latch to hold a call and observe queue capacity, timeouts, task rejections, and recovery. Never simulate congestion with unsynchronized `Thread.sleep`.

## 22. Transaction Boundaries: What Mock Clients Cannot Conclude

A flow might write to a database, call HTTP, and publish to Kafka. Even if mocked `JdbcTemplate`/`PartnerClient`/`KafkaTemplate` all return normally, that does not mean all three resources share **one ACID transaction**.

~~~mermaid
flowchart LR
    M["Message"] --> DB["Local DB transaction"]
    DB --> HTTP["HTTP outbound"]
    HTTP --> KAFKA["Kafka publish"]
    HTTP -. "timeout after remote commit" .-> RETRY["Retry"]
    RETRY -. "risk" .-> DUP["Duplicate side effect"]
~~~

Failure boundaries requiring separate tests:

1. DB write succeeds, HTTP fails → what state is saved; is there an outbox or compensation?
2. HTTP succeeds, DB rolls back → does a later retry duplicate side effects?
3. Kafka publish future fails after handler returns → who detects and retries it?
4. Process killed between writing output and acking source → how does redelivery behave?
5. Endpoint stopped mid-send → draining, in-flight messages, and connection cleanup?

**Mock clients** excel at forcing individual error branches, whereas **integration tests with stateful DBs/brokers/HTTP mock servers** prove consistency across transaction boundaries. For high reliability, consider transactional outbox, idempotency keys, and reconciliation instead of assuming rollback across protocols.

## 23. Connection Lifecycle: Start, Stop, Restart, Reconnect

Outbound adapters do more than a single `send()`. For SFTP/AMQP/JMS/Kafka, clients may own threads, connection pools, session caches, or producer resources.

| Scenario | What Mock Client Tests Prove | Additional Integration Test |
|---|---|---|
| Context start | Beans injected, endpoints subscribed | Real connection to server/broker |
| Stop | Lifecycle methods invoked if contracted | Connections/sessions/threads closed cleanly |
| Restart | Handler can send again after start | Reconnect/metadata store/producer state |
| Client disconnects | Error/retry paths invoked | Real TCP/SSH/broker recovery |
| Expired credentials | Handler processes auth errors properly | Real auth failure and rotation |
| Shutdown mid-flight | Logic does not falsely mark success | Real drain/requeue/ack behavior |
| Backpressure | Queue/timeout policies under held mock | Real latency/capacity against target |

**Never claim `MockIntegrationContext` or a mock client tested reconnect.** A mock `client.send()` has no socket to drop. Use external integration tests for reconnects and resource leaks; in unit tests, assert only how handlers/recoverers react to simulated failures.

### 23.1. Timeouts at the Right Layer

There are many timeouts: channel send timeout, poller receive timeout, HTTP connect/read timeout, SFTP session timeout, broker ack timeout, gateway reply timeout. Tests must know which timeout is acting. A `receive(1000)` timeout on a test collector **does not prove** the outbound client configured a 1-second network read timeout.

## 24. Security When Mocking Outbound Clients

Outbound adapters frequently carry credentials, secrets, filenames, remote paths, and personal data. Mocking avoids production accounts, yet tests/reports themselves can leak data if they capture too much.

Guidelines:

- Use only **dummy/inactive credentials** or test secrets provisioned securely by CI.
- Never print `Authorization` headers, cookies, API keys, or SSH private keys into failure reports/stack traces to prove calls worked. Check **header presence** or redacted fingerprints per contract.
- Real SFTP tests must verify host keys—never disable validation for convenience.
- For HTTP outbound, block URIs outside allowlists to prevent SSRF and disallow arbitrary user-controlled hosts.
- For file/SFTP paths, validate names/paths and reject `../` or unauthorized absolute paths.
- When mock clients receive sensitive DTOs, avoid printing `ArgumentCaptor.getValue().toString()` automatically in assertion errors if DTOs hold PII.
- Test missing auth, missing scopes, or expired tokens to ensure adapters/flows never turn auth failures into successes.

**Useful testing habit:** verify requests hit `partner.example`/topics/remote directories accurately, without putting real production secrets into stubs just for string comparison.

## 25. Test Matrix by Protocol and Mocking Layer

| Adapter | Suitable Mock Client | Key Assertions | Extra Tests Needed to Verify Protocol |
|---|---|---|---|
| **HTTP outbound one-way** | Client façade / `RestTemplate` / `RestClient` with mock server | Method, URI, body, headers, status/error | Socket-based HTTP mock server, timeouts, TLS where needed |
| **HTTP outbound gateway** | Mock client returning response | Request plus reply/correlation/status | Mock server, response mapping, timeouts |
| **SFTP outbound** | `RemoteUploader` or `SessionFactory` | Remote path, bytes, temp filename, errors | Isolated SFTP server, auth/host key, upload/rename |
| **File outbound** | `FileWriter` façade if needed | Filename, content, policy | `@TempDir` + real files, permissions, atomic writes |
| **JMS outbound** | `JmsTemplate` or publisher port | Destination, payload, properties | Broker, ack, transactions, redelivery |
| **AMQP/RabbitMQ outbound** | `RabbitTemplate` or publisher port | Exchange, routing key, headers | Broker bindings, confirms/returns, DLQ |
| **Kafka outbound** | `KafkaTemplate` or producer port | Topic, key, record, future success/failure | Broker, serialization/schema, offsets, consumer |
| **JDBC/JPA outbound** | `JdbcTemplate` / Repository port | SQL/parameters, rows updated, exceptions | Test DB, schema, transactions/constraints |
| **MessageChannel outbound** | Mock handler at endpoint | End-of-flow message matches contract | Real adapter if external side effects exist |
| **Custom SDK adapter** | Interface injected into handler | DTO mapping, scope, retry classification | Test SDK client against mock server/sandbox |

For *testing outbound adapters with mock clients*, prioritize **one close-to-handler test** per contract, complemented by **minimal transport tests** where integration bugs commonly arise. Never use a mock-client suite to claim full protocol coverage.

## 26. Case Study: SFTP Inbound → Transform → HTTP Outbound with Mock Client

### 26.1. Context

An application receives partner order CSVs over SFTP. A file inbound adapter emits messages, a parser converts data into `OrderCommand`, validation checks required fields, and an outbound handler calls a shipping API. The goal is testing **the outbound point accurately** without hitting the production API.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound / local file"] --> PARSER["CSV parser"]
    PARSER --> VAL["Order validator"]
    VAL --> CH["ordersOutboundChannel"]
    CH --> HANDLER["OrderOutboundHandler"]
    HANDLER --> CLIENT["PartnerClient interface"]
    CLIENT --> API["Shipping API"]
    CLIENT -. "Mockito mock in unit/slice test" .-> MOCK["verify / captor / exception stub"]
    API -. "mock server in integration test" .-> HTTP["HTTP request assertions"]
    HANDLER -. "failure" .-> REC["Retry / Error flow"]
~~~

### 26.2. Input Contract and Expected Outcomes

~~~text
Source:
  remote file: /incoming/orders-42.csv
  CSV: orderId,total
       42,100

Before outbound:
  payload: OrderCommand(orderId=42, amount=100)
  correlationId: order-42
  sourceFileName: orders-42.csv
  eventId: order-42-v1

Expected client call:
  submit(OrderCommand("42", 100), "order-42")

Expected HTTP with real client:
  POST /api/orders
  body {"orderId":"42","amount":100}
  X-Correlation-Id: order-42

Expected failure policy:
  invalid order -> reject before client
  HTTP 503 -> retry at most configured attempts
  timeout after server saved -> idempotency prevents duplicate order
~~~

### 26.3. Layer 1 — Parser and Validator Unit Tests

Test valid CSVs, missing columns, duplicate order IDs, negative/invalid amounts, encoding, and size limits. Do not mock the parser if it produces inputs for handlers in the same contract test; standalone unit tests localize errors faster.

### 26.4. Layer 2 — Flow Tests with Mock Client

Use `@SpringJUnitConfig` with a `DirectChannel` and the real handler. Send a normalized `OrderCommand` to `ordersOutboundChannel`, then:

- `verify(client).submit(eq(command), eq("order-42"))`.
- Missing correlation → `verifyNoInteractions(client)`.
- Wrong DTO type → not sent.
- Two distinct commands → exactly two calls without mixing business IDs.
- With multi-tenant routing, verify the right client/destination is chosen per tenant/project.

**What is proven:** message flow and outbound boundary. No real SFTP/HTTP needed to test this logic.

### 26.5. Layer 3 — HTTP Adapter Tests with a Mock Server

Configure the **real** HTTP outbound handler/client pointing at a mock server:

- Assert `POST /api/orders`, body, content type, correlation header.
- Return 201 plus simulated 400/503/timeouts.
- Verify error mapping/retries matching the production endpoint.
- Verify destination host cannot be arbitrarily derived from user payloads.
- Never print real API tokens in test logs.

**What is proven:** HTTP mapping and how the client interacts with the mock server. Does not yet prove the live production API is up.

### 26.6. Layer 4 — SFTP Adapter Tests

With a test SFTP server, upload files to the remote folder, trigger the inbound poller, and inspect parser and downstream behavior. This covers everything mocking `PartnerClient` misses: remote sync, file filters, restarts, host keys, and connectivity.

### 26.7. Layer 5 — Recovery and Idempotency

Simulate:

1. Mock server saves the order then intentionally drops the response.
2. HTTP client times out.
3. Retry fires with the same `eventId` or idempotency key.
4. Server checks the key and does not create a second order.
5. Application records the final state accurately with attempt audit trails.

This is a **stateful** mock-server/sandbox test—impossible to prove with `Mockito.verify(times(2))` alone.

### 26.8. Sample Results Table

| Test Case | What Did the Mock Client See? | What Did the Simulated Target Hold? | Conclusion |
|---|---|---|---|
| Valid order | One `submit(42)` | One valid HTTP POST at protocol layer | PASS per layer |
| Missing correlation | No `submit` | No HTTP call | PASS |
| HTTP 400 | One request, reject branch | No order created | PASS |
| HTTP 503 then 201 | Two attempts per policy | One valid business outcome | PASS if retry defined |
| Timeout after commit | Retry fired | Only one order via idempotency | PASS |
| SFTP disconnect | HTTP mock client never called | No bogus data or misprocessing | PASS if recovery per contract |
| Duplicate CSV | Possibly multiple inputs | One side effect per business key | PASS if contract idempotent |
| Missing mock/context reset | Interactions from previous test | Unreliable results | FAIL test isolation |

## 27. Sample Test Plan Template for Real Projects

An outbound adapter development ticket should include a clear test plan:

~~~yaml
outboundAdapterTestPlan:
  component: "shipping-orders-http-outbound"
  flowEntry: "ordersOutboundChannel"
  endpointId: "shippingOrdersOutboundEndpoint"
  clientAbstraction: "PartnerClient"
  messageContract:
    payloadType: "OrderCommand"
    requiredHeaders:
      - "correlationId"
      - "eventId"
    destination: "shipping-service"
  cases:
    - "HAPPY_PATH"
    - "MISSING_HEADER_REJECTED"
    - "INVALID_PAYLOAD_REJECTED"
    - "TRANSIENT_FAILURE_RETRY"
    - "PERMANENT_FAILURE_NOT_RETRIED"
    - "TIMEOUT_UNKNOWN_OUTCOME"
    - "DUPLICATE_EVENT_ID"
    - "ASYNC_COMPLETION"
  fixtures:
    - "Mockito mock PartnerClient"
    - "HTTP mock server"
  requiredEvidence:
    - "Mock interaction args"
    - "HTTP request/response assertion"
    - "Side-effect count/idempotency"
    - "Error and recovery"
  isolation:
    - "unique correlationId per test"
    - "reset mock and stop endpoints"
~~~

This is a **test-plan governance template**, not directly runnable Spring Integration config. Its purpose is forcing tests to define observation points, error events, and evidence levels rather than ending up with just `assertTrue(channel.send(...))`.

### 27.1. Splitting Suites by Speed

- **Fast unit suite:** validator/mapper/handler and mock client tests; network-free, run continuously.
- **Spring flow suite:** small context, mocked adapter endpoints or mocked clients; checks wiring, channels, and exception propagation.
- **Protocol contract suite:** HTTP mock server, SFTP test server, broker/database containers; run regularly in infra-enabled CI.
- **Pre-release/staging suite:** connects to sandbox services with auth/TLS and near-production config on an appropriate schedule.

Do not dismiss a fast test as "low quality"; it is valuable within **its stated scope**. The mistake is extrapolating narrow-scope results into broad operational claims.

## 28. Common Pitfalls in the Tests Themselves

| Testing Anti-Pattern | Why It Fails | Replacement |
|---|---|---|
| Mocking the whole `IntegrationFlow` then verifying client | Real wiring and routing never run | Keep real flow in Spring test context |
| Handler instantiates client with `new` | Cannot inject mocks cleanly | Controlled constructor injection/factory |
| Asserting only `send() == true` | Does not verify client received call | `verify`/captor and side-effect tests |
| `verify(client).send(any())` | Hides wrong destinations and payloads | Assert destination, business key, content/headers |
| Mock client returns success for every case | Skips retry/recovery testing | Stub 4xx/5xx, timeouts, exceptions, async failures |
| Treating mock method return as broker ACK | No real broker involved | Integration tests with confirms/offsets/acks |
| Testing retry with `doThrow().doNothing()` without advice | No second invocation occurs | Configure real retry and assert attempt counts |
| Immediate Mockito verify on async flows | Races and CI flakiness | `timeout`/latches and completion signals |
| Replacing adapter with mock then claiming serialization tested | Real serialization bypassed | Mock HTTP server or broker test |
| Forgetting `MockIntegrationContext.resetBeans()` | Real handler stays replaced | `resetBeans()` in teardown |
| Sharing mocks across tests without reset | `verify(times(...))` sees old calls | Reset or isolate contexts |
| Checking gateway reply on one-way adapter | Wrong endpoint semantics | Assert side effects instead of replies |
| Mocking SFTP then claiming host key security | No real SSH handshake | Test SFTP server with negative host-key test |
| Comparing all headers/message IDs | Couples to framework internals | Assert only contract headers |
| Testing only happy paths | Misses outages, duplicates, partial failures | Negative test matrix with deadlines |
| Logging full Authorization header on failure | Risks leaking secrets | Redact; assert presence/redacted metadata |
| Fixed `Thread.sleep` timeouts | Slow and flaky | Bounded condition/event waits |
| Sharing test data | Stale files/broker records cause false passes | Temp dirs, dedicated queues/topics/schemas |
| Retrying every error | Can duplicate side effects or loop forever | Classify transient vs. permanent + idempotency |

## 29. Acceptance Checklist and Self-Assessment Scenarios

### 29.1. Checklist

- [ ] Identified whether endpoint is a **one-way outbound adapter** or **request–reply outbound gateway**.
- [ ] Clear mocking boundary: outbound handler, injected protocol client, or mock server.
- [ ] Flow tests preserve exact channel topology within stated scope.
- [ ] Contract covers payload, headers, destination, timeout, delivery, and failure.
- [ ] Mock client tests assert **exact methods and arguments**, never just `any()`.
- [ ] HTTP tests verify method/URI/body/headers with appropriate client/mock server.
- [ ] For File, SFTP, JMS, AMQP, Kafka, DB, identified what requires protocol integration tests.
- [ ] Invalid payloads/headers verified not to invoke the external client.
- [ ] Retries genuinely configured in tests with accurate attempt counts and recovery.
- [ ] Async clients tested for both future success/failure and completion deadlines.
- [ ] Duplicates/idempotency tested whenever messages can be resent.
- [ ] Target side effects verified where required by contract.
- [ ] Tests use zero production credentials or data.
- [ ] Setup/teardown cleans mocks, endpoints, listeners, queues/topics/files, and test data.
- [ ] No long `Thread.sleep` replacing proper timing control.
- [ ] Test reports state clearly **what was proven and what remains unproven**.
- [ ] For critical systems, negative tests cover lifecycle, reconnect, timeout, and partial failures.

### 29.2. Scenario Questions

**Scenario A.** A test mocks `PartnerClient` and verifies the payload, yet production sends HTTP with the wrong `Content-Type`. Would the test catch it?

**Answer:** Usually no, if serialization/header mapping lives **inside the mocked client implementation**. Add tests with the real HTTP client and a mock HTTP server to inspect actual requests.

**Scenario B.** `DirectChannel.send(message)` returns `true`, and Mockito verifies one client call. Can we declare the SFTP upload succeeded?

**Answer:** No. That only proves the handler called the client. Use a test SFTP server to verify the remote file, rename/temp policies, network errors, and auth/host keys.

**Scenario C.** A test stubs Kafka `send(...)` returning an incomplete future, yet the handler reports business success anyway. What is the risk?

**Answer:** Equating **initiating a send** with **async completion**. Verify future/callback handling, producer failures, and business state updates.

**Scenario D.** `RabbitTemplate` is mocked and verified for the expected exchange/routing key. Messages have no consumers due to a broken broker binding. Would the mock test catch this?

**Answer:** No. You need a RabbitMQ integration test to verify exchanges/bindings, publisher confirms/returns, and messages arriving in the right queue.

**Scenario E.** A mock client is configured to throw once and succeed on the second call. Yet the handler only calls it once. Is Spring Integration's retry mechanism broken?

**Answer:** Check whether retry advice/policy is actually attached to the handler. Mockito does not create retries on its own. If a real policy is configured, investigate endpoint/thread/error-handler wiring.

**Scenario F.** A test replaces the outbound handler via `MockIntegrationContext` and asserts the payload. Has the real HTTP adapter been tested?

**Answer:** No. The real endpoint was substituted, testing only the flow before the adapter; keep another test retaining the real handler/client to verify HTTP requests.

**Scenario G.** Two tests share a mock bean and run in parallel; `verify(times(1))` occasionally fails. What are likely causes?

**Answer:** Interactions from tests sharing a mock/context bleed together, or an async handler from an earlier test is still running. Use isolation, unique correlation IDs, cleanup, and avoid parallel execution on shared mocks/queues without separation.

**Scenario H.** A mock client throws a timeout, the handler retries once, and succeeds. The real server may have processed the first request. What is missing for safety?

**Answer:** An idempotency key, reconciliation logic for uncertain outcomes, and stateful tests proving two side effects aren't created.

**Scenario I.** An outbound HTTP gateway returns 201, yet the test only verifies the mock client call. What is missing?

**Answer:** Reply mapping/status/correlation and timeout/error paths; a request–reply gateway must test **the response returning to the flow/caller**, not just the outbound call.

**Scenario J.** A DB outbound unit test stubs `JdbcTemplate.update(...)` to return 1. Can we conclude a real transaction committed one row?

**Answer:** No. The mock only returned a canned value; use a test database to verify schema, SQL, transactions, constraints, and post-commit rows.

## 30. References and Notes on Using the Examples

Official documentation pages helpful for cross-checking **exact versions** during implementation:

- Spring Integration — Testing support: https://docs.spring.io/spring-integration/reference/testing.html
- Spring Integration — HTTP Outbound Components: https://docs.spring.io/spring-integration/reference/http/outbound.html
- Spring Integration — HTTP Java Configuration: https://docs.spring.io/spring-integration/reference/http/java-config.html
- Spring Framework — Testing Client Applications: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html

Notes:

1. **Self-contained Java examples** can be dropped into a project test context when imports, beans, and DTOs match the provided definitions.
2. Snippets containing `/* handler */`, `mockedSendResult`, `fixture`, or `...` are **partial illustrative patterns**, not complete standalone tests; do not copy them expecting immediate compilation.
3. In Spring Integration **7.1+**, `RestTemplate`-based HTTP configs are gradually being replaced by `RestClient`. Check signatures for your exact version and consider mock servers so tests do not depend on legacy overloads.
4. `@SpringIntegrationTest`/`MockIntegrationContext` are great for substituting endpoints in tests, yet do not replace protocol-level tests of real clients.
5. **Every assertion needs a clear purpose:** arguments sent, exceptions handled, broker acked, file saved, or database committed—these represent distinct levels of verification.

## Conclusion

**Testing outbound adapters with mock clients** provides fast, deterministic, and safe verification of how Spring Integration turns a `Message<?>` into external requests. Keeping **real `MessageChannel`s and handlers** while injecting a **mock client** proves payloads, headers, destinations, invocation counts, validation, exceptions, and retries at the outbound boundary. Substituting **outbound handlers with `MockIntegrationContext`** tests the upstream flow. Pairing these with **HTTP mock servers, SFTP servers, JMS/AMQP/Kafka brokers, or test databases** yields protocol and side-effect evidence. Combining the right layers—with bounded timeouts, idempotency, cleanup, error auditing, and lifecycle control—makes file, SFTP, HTTP, JMS, AMQP, Kafka, and database integrations dependable without mistaking a mocked call for a completed business outcome.

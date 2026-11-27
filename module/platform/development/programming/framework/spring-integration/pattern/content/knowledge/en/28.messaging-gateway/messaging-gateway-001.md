# Messaging Gateway Hides MessageChannel Behind an API

When building an integration flow with Spring Integration, an application can directly construct a `Message<?>`, select a `MessageChannel`, call `send()`, prepare a `replyChannel`, and wait for a response itself. This approach causes **business code to depend on messaging infrastructure**: switching from synchronous processing to a queue, or adding a Router or Transformer, can force many services to change their code.

**Messaging Gateway** is an Enterprise Integration Pattern (EIP) that provides a **familiar method-call interface** on the application side and hides how that call is turned into a message on the integration-flow side. With Spring Integration, `@MessagingGateway` combined with `@Gateway`, `GatewayProxyFactoryBean`, and message endpoints allows a client bean to call:

~~~java
OrderQuote result = quoteGateway.quote(request, trustedTenant);
~~~

instead of:

~~~java
Message<OrderQuoteRequest> message = MessageBuilder
        .withPayload(request)
        .setHeader("trustedTenant", trustedTenant)
        .build();

requestChannel.send(message);
// ... manually manage replyChannel, timeout, correlation, and result conversion ...
~~~

The lesson **Messaging Gateway Hides MessageChannel Behind an API** belongs to the **Messaging gateway** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module aims to implement Enterprise Integration Patterns with Spring Integration to create loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, along with testing and monitoring processing branches.

**Key takeaway:** A Gateway hides the **messaging API** from business code, **not the semantics** of request-reply, timeouts, errors, retries, transactions, ACKs, or missing replies. A method whose signature returns `OrderQuote` still requires a **matching reply message** downstream; if the flow simply drops the message or fails to complete, the method call may time out or receive `null` depending on the configuration and version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the Messaging Gateway EIP and the role of `GatewayProxyFactoryBean`.
2. Compare calling `MessageChannel.send()` directly with calling a proxied Java interface.
3. Understand the flow **method invocation → Message → request channel → handler → reply channel → Java return value**.
4. Distinguish between a **gateway proxy**, **inbound HTTP/JMS gateway**, **outbound gateway**, and service activator.
5. Define `@MessagingGateway`/`@Gateway`, `@Header`, and configure `@IntegrationComponentScan`.
6. Write a Spring Integration Java DSL request-reply flow with `DirectChannel`.
7. Test a complete gateway without caller code importing `Message<?>` or `MessageChannel`.
8. Identify the difference between `requestTimeout` and `replyTimeout`, especially when a synchronous downstream blocks.
9. Design behavior when a Filter drops, a Router finds no route, or a handler returns `null`.
10. Distinguish value-returning methods, `void` methods, and `CompletableFuture<T>` asynchronous APIs.
11. Preserve correlation/reply metadata across Router, Transformer, Splitter/Aggregator, and brokers.
12. Classify validation errors, timeouts, infrastructure failures, and unknown business outcomes.
13. Place retry, idempotency, broker ACK, and transactions within their proper boundaries.
14. Distinguish an internal synchronous Gateway API from a request-reply protocol across multiple JVMs.
15. Monitor latency, timeouts, queue backlog, and traces without creating unbounded metric cardinality.

## 2. The Problem: The Business Layer Knows Too Much About Messages

A quote service calls a message channel directly:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class DirectChannelQuoteCaller {

    private final MessageChannel channel;

    public DirectChannelQuoteCaller(MessageChannel channel) {
        this.channel = channel;
    }

    public void submit(
            OrderQuoteRequest request,
            String trustedTenant) {

        Message<OrderQuoteRequest> message =
                MessageBuilder.withPayload(request)
                        .setHeader(
                                "trustedTenant", trustedTenant)
                        .build();

        boolean sent = channel.send(message);
        if (!sent) {
            throw new IllegalStateException("SEND_FAILED");
        }
        // Only confirms send; NO business reply yet in this example.
    }
}
~~~

The code above is not necessarily wrong, but the caller must know `MessageChannel`, `MessageBuilder`, and the header name. If the API truly needs to **return a quote on success or a rejection reason**, a `void submit(...)` method is not enough; the caller would also have to design reply reception and correlation itself.

With a Messaging Gateway, the caller only sees:

~~~java
OrderQuote quote = quoteGateway.quote(
        new OrderQuoteRequest(
                "quote-1001", "tenant-a", "BOOK", 2),
        "tenant-a");
~~~

The caller does not know that the request passes through:

- A `DirectChannel` or an `ExecutorChannel`.
- A Transformer, Router, Filter, or Service Activator.
- A temporary reply channel and `MessageHeaders.REPLY_CHANNEL`.
- Internal headers used to track the flow.

~~~mermaid
flowchart LR
    A["Application Service"] -->|"quote(request)"| G["Gateway Java Proxy"]
    G -->|"Message<OrderQuoteRequest>"| C["quote.requests"]
    C --> H["Validation / Quote Handler"]
    H -->|"OrderQuote reply"| R["Temporary replyChannel"]
    R --> G
    G -->|"OrderQuote"| A
~~~

**The Gateway is an abstraction boundary**, not a magical business handler. It creates/sends the message, manages the reply-waiting mechanism, and converts the reply into a method return value; the **actual business processing** still lives in the downstream flow.

## 3. How Does the Messaging Gateway EIP Work?

### 3.1. Input Is a Method Invocation

For example:

~~~java
OrderQuote quote(OrderQuoteRequest request, String tenantContext);
~~~

The gateway proxy takes the arguments from the method call and creates a payload and headers according to the mapping contract. Method parameters annotated with `@Header` become message headers; the payload parameter becomes the payload.

### 3.2. Sending via the Request Channel

The proxy sends the message to the configured `requestChannel`, for example `quote.requests`. The receiving end can be a Transformer, Filter, Router, Service Activator, or a complete flow.

### 3.3. The Reply Channel Is Typically Created Temporarily

For **request-reply** calls, a Spring Integration gateway typically creates **a temporary, anonymous, point-to-point reply channel** and attaches it to the `replyChannel` header. The downstream endpoint produces a reply message; the framework routes that reply back to the gateway to return the Java result. Therefore, you **do not need** to create a fixed `QueueChannel` for every call just to wait for replies, unless the topology has a specific reason.

### 3.4. Returning a Value or an Error

- Reply payload compatible with the return type → the gateway returns the Java object.
- Handler throws an exception → the gateway typically propagates the exception to the caller according to error semantics (and may unwrap certain wrappers).
- No reply → depending on topology/timeouts, the method may wait, return `null`, or throw a timeout exception when the corresponding policy is enabled in supported versions.
- `void` method → does not wait for a business reply per the method contract, but **does not** mean the send was persisted by a broker or that all downstream processing has completed.

### 3.5. Do Not Equate Sending with Successful Processing

~~~text
Gateway sent message successfully
     != Business DB transaction committed
     != Remote API completed
     != Broker ACK received
     != User received confirmed receipt
~~~

A successful call to `MessageChannel.send()` only carries the semantics of the specific endpoint/channel; it does not implicitly guarantee business side effects.

## 4. What Does the Gateway Hide and What Does It Not Hide?

| Concern | Can the Gateway Hide It? | Explanation |
|---|---|---|
| Creating `Message<?>` | Yes | Proxy creates the message from method args |
| Calling `MessageChannel.send()` | Yes | Application calls a Java interface |
| Request channel name in the caller | Yes | Lives in annotation/config |
| Temporary reply channel mechanism | Yes | Proxy manages request-reply |
| Converting reply to method return | Yes | Based on return type/converters |
| Multiple Router/Filter/Transformer endpoints | Yes at the API boundary | Flow still needs proper configuration |
| Whether a reply exists | **No** | Downstream must produce a valid reply |
| Durable persistence of events | **No** | Depends on transport/transaction |
| Exactly-once business side effects | **No** | Requires idempotency/transaction |
| Network timeouts and partitions | **No** | API still has uncertainty |
| Data contract/schema | **No** | Payload/reply need a typed contract |
| Authorization and tenant isolation | **No** | Must be verified at the trust boundary |
| Concurrency/ordering/backpressure | **No** | Depends on channel/adapter |
| Retries/late replies | **No** | Requires dedicated policies |

### 4.1. "Changing Just One Annotation" Does Not Safely Turn a Sync System Async

Switching `DirectChannel` to `ExecutorChannel` or a broker queue changes the thread boundary and failure model. Even if the signature `OrderQuote quote(...)` does not change, **latency, ordering, timeouts, retries, ACKs, and late replies** can all change. Abstraction reduces coupling in caller code, but it does not eliminate system design.

## 5. Types of Gateways Easily Confused

| Name | Role | Example |
|---|---|---|
| **Messaging Gateway EIP** | Hides the messaging API behind an interface/contract | `OrderQuoteGateway.quote(...)` |
| **Gateway proxy (`@MessagingGateway`)** | Generates an implementation for a Java interface | `GatewayProxyFactoryBean` |
| **HTTP inbound gateway** | Receives an HTTP request, enters a flow, and returns an HTTP response | `HttpRequestHandlingMessagingGateway` |
| **HTTP outbound gateway** | Flow sends an HTTP request and receives a response | REST client adapter |
| **JMS/AMQP inbound gateway** | Defines request-reply with a broker | Request + reply queues |
| **Service Activator** | Executes logic to process a message | `QuoteCalculator.quote(...)` |
| **Message Endpoint** | Internal consumer/producer inside a flow | Router, Filter, Transformer |

A Java gateway proxy **does not automatically create an HTTP endpoint**. If you need a REST API, you still need a web controller or an HTTP inbound gateway. Likewise, an HTTP outbound gateway is an adapter interacting with an external system, unlike a proxy bean hiding `MessageChannel` for an application service.

## 6. Domain Model: Quote Request and Result

The example uses Java 17 records, does not access a DB, and creates no side effects so the focus stays on request-reply.

### 6.1. Request

~~~java
public record OrderQuoteRequest(
        String quoteId,
        String tenantId,
        String sku,
        int quantity
) {}
~~~

### 6.2. Reply

~~~java
public record OrderQuote(
        String quoteId,
        String tenantId,
        String sku,
        int quantity,
        long totalMinorUnits,
        String currency
) {}
~~~

All top-level `public` types in the code blocks must be placed in **separate Java source files with the same name** when run in a project.

### 6.3. Exception with Reason Code

~~~java
public final class QuoteValidationException
        extends IllegalArgumentException {

    private final String reasonCode;

    public QuoteValidationException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
~~~

### 6.4. Pure Business Handler

~~~java
public final class QuoteCalculator {

    public OrderQuote quote(
            OrderQuoteRequest input,
            String authenticatedTenant) {

        if (input == null) {
            throw new QuoteValidationException(
                    "REQUEST_REQUIRED");
        }

        if (blank(input.quoteId())) {
            throw new QuoteValidationException(
                    "QUOTE_ID_REQUIRED");
        }
        if (blank(input.tenantId())) {
            throw new QuoteValidationException(
                    "TENANT_ID_REQUIRED");
        }
        if (blank(authenticatedTenant)
                || !input.tenantId().equals(
                        authenticatedTenant)) {
            throw new QuoteValidationException(
                    "TENANT_NOT_AUTHORIZED");
        }
        if (blank(input.sku())) {
            throw new QuoteValidationException(
                    "SKU_REQUIRED");
        }
        if (input.quantity() <= 0) {
            throw new QuoteValidationException(
                    "QUANTITY_MUST_BE_POSITIVE");
        }

        long unitMinorUnits = switch (input.sku()) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 15_000L;
            default -> throw new QuoteValidationException(
                    "SKU_UNSUPPORTED");
        };

        final long totalMinorUnits;
        try {
            totalMinorUnits = Math.multiplyExact(
                    unitMinorUnits,
                    input.quantity());
        }
        catch (ArithmeticException ex) {
            throw new QuoteValidationException(
                    "QUOTE_AMOUNT_OVERFLOW");
        }

        return new OrderQuote(
                input.quoteId(),
                input.tenantId(),
                input.sku(),
                input.quantity(),
                totalMinorUnits,
                "VND");
    }

    private static boolean blank(String text) {
        return text == null || text.isBlank();
    }
}
~~~

**Meaning of the example:** the handler produces a **pure quote** from a hypothetical price list without recording an order or payment. Returning `OrderQuote` proves the request-reply API, **not** that an order placement has been committed.

### 6.5. Where Does the `authenticatedTenant` Header Come From?

In the demo, the caller passes a string into the Gateway to illustrate mapping method arg → header. Production code must never treat a client-supplied string as verified authentication proof. An HTTP Controller or security adapter must extract the tenant from the authenticated principal/claims and pass it to the application service; the Gateway only **carries data through the flow** and does not verify JWT/mTLS itself.

## 7. Defining an Interface with `@MessagingGateway`

### 7.1. Java-Typed Contract

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway(
        name = "orderQuoteGateway",
        defaultRequestChannel = "quote.requests",
        defaultRequestTimeout = "2000",
        defaultReplyTimeout = "3000")
public interface OrderQuoteGateway {

    @Gateway
    OrderQuote quote(
            OrderQuoteRequest request,
            @Header("authenticatedTenant") String tenant);
}
~~~

Here:

- `@MessagingGateway` is placed on an **interface**, with no need to write an implementation class manually.
- `name` identifies the proxy bean.
- `defaultRequestChannel` is where the gateway sends messages.
- `defaultRequestTimeout` and `defaultReplyTimeout` (in **milliseconds**, configured as strings) are separate limits.
- `@Gateway` can override the channel, timeouts, and headers **per method**.
- `@Header` maps an argument into the `authenticatedTenant` header.
- The `OrderQuote` return type gives the method a **contract requiring a reply**, if the flow responds properly.

### 7.2. Why Doesn't the Client Need to Import `MessageChannel`?

The client application only sees the interface:

~~~java
public final class QuoteApplicationService {

    private final OrderQuoteGateway gateway;

    public QuoteApplicationService(
            OrderQuoteGateway gateway) {
        this.gateway = gateway;
    }

    public OrderQuote prepareQuote(
            OrderQuoteRequest request,
            String authenticatedTenant) {

        return gateway.quote(
                request,
                authenticatedTenant);
    }
}
~~~

This service knows nothing about `MessageBuilder`, `replyChannel`, `ServiceActivator`, or channel names. If you want to remove even annotation dependencies from the core domain, you can define a **plain Java port interface** (for example `QuotePort`) in the domain layer and use the gateway/proxy as an adapter in the integration layer.

### 7.3. Registering Gateway Interfaces Requires More Than `@ComponentScan`

Spring Integration uses `@IntegrationComponentScan` to discover `@MessagingGateway` interfaces and create proxy beans. A regular `@ComponentScan` is usually not enough to detect and register this kind of interface properly. With Spring Integration 6.0+, registration options via `@Import` may also exist; the lesson uses explicit component scanning for clarity.

## 8. Java DSL: Routing Requests to a Reply-Producing Handler

### 8.1. Complete Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan(
        basePackageClasses = OrderQuoteGateway.class)
public class QuoteGatewayConfiguration {

    @Bean(name = "quote.requests")
    public MessageChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public QuoteCalculator quoteCalculator() {
        return new QuoteCalculator();
    }

    @Bean
    public IntegrationFlow quoteRequestFlow(
            QuoteCalculator calculator) {

        return IntegrationFlow
                .from("quote.requests")
                .handle(
                        OrderQuoteRequest.class,
                        (request, headers) -> calculator.quote(
                                request,
                                (String) headers.get(
                                        "authenticatedTenant")))
                .get();
    }
}
~~~

Place the interface, model, processor, and configuration in appropriately scannable packages; if a project has multiple gateway interfaces, narrow the scope of `@IntegrationComponentScan` so you do not accidentally create beans belonging to other tests or modules.

**Execution flow:**

1. The `OrderQuoteGateway` proxy bean receives `quote(request,tenant)`.
2. The proxy creates a message with payload `OrderQuoteRequest` and header `authenticatedTenant`.
3. The gateway sends the message to `quote.requests`.
4. `DirectChannel` invokes the `QuoteCalculator.quote(...)` handler on the caller thread.
5. The handler returns `OrderQuote`.
6. Spring Integration sends the result back to the **gateway's replyChannel** (header propagated through the flow).
7. The proxy converts the reply into the `OrderQuote` return value for the caller.

~~~mermaid
sequenceDiagram
    participant A as QuoteApplicationService
    participant G as OrderQuoteGateway Proxy
    participant C as quote.requests DirectChannel
    participant H as QuoteCalculator

    A->>G: quote(request, tenant)
    G->>C: Message(payload, headers, replyChannel)
    C->>H: handle(request)
    H-->>C: OrderQuote
    C-->>G: Reply via replyChannel
    G-->>A: OrderQuote
~~~

### 8.2. No Need for an Explicit Reply Channel in a Simple Flow

The Gateway automatically creates a reply channel for request-reply. Do not add a fixed `QueueChannel` as an output and expect the gateway to read from it automatically without bridging or routing. For a `.handle(...)` flow that produces a reply, the `replyChannel` header mechanism is sufficient.

### 8.3. What If a Handler Returns `null`?

If the calculator returns `null` or an endpoint produces no reply, the Gateway cannot turn "no Message" into a valid `OrderQuote`. Depending on the thread boundary and timeout, the caller may wait, receive `null`, or get an error. An application API that forbids null replies must define explicit **error/timeout mapping** and avoid reply-less processing paths.

### 8.4. Why Not Put `.channel("quote.requests")` Twice?

In the configuration above, the Gateway already sends to `quote.requests`; `IntegrationFlow.from("quote.requests")` is the point that **reads** from the channel. Creating another flow that loops back into this same channel can cause message loops or misrouted deliveries. Each channel/endpoint should have a clear role: input, branch, or output.

## 9. Gateway Methods and Header Mapping

### 9.1. Distinguishing Payload and Header Arguments

~~~java
@Gateway(requestChannel = "quote.requests")
OrderQuote quote(
        OrderQuoteRequest request,
        @Header("authenticatedTenant") String tenant);
~~~

`OrderQuoteRequest` is the payload. `tenant` is placed into a header and does not automatically become a new field in the record.

### 9.2. Method-Level Override

~~~java
@MessagingGateway(
        defaultRequestChannel = "quote.requests")
public interface MultiOperationGateway {

    @Gateway(requestChannel = "quote.requests")
    OrderQuote quote(OrderQuoteRequest request);

    @Gateway(requestChannel = "audit.events")
    void audit(AuditEvent event);
}
~~~

This example **illustrates methods using different channels**, not a standalone runnable configuration: you must declare `AuditEvent`, the `audit.events` channel, and an appropriate endpoint handler. Do not let a method accidentally fall back to the default request channel if its payload and contract belong to a different flow.

### 9.3. Do Not Put Raw Secrets into Gateway Headers and Forward Them Indiscriminately

A `@Header("Authorization") String token` method parameter might help a single HTTP adapter hop in a specific scenario, but you should not pass bearer tokens across an entire broker or canonical channel. Use the security context at ingress, token exchange for downstream, or appropriately scoped credentials. Headers leaving the JVM from a Gateway must go through a **header mapper/allowlist**.

## 10. How Does a Gateway Differ from Calling a Service Activator Directly?

A business caller can invoke `QuoteCalculator.quote(...)` directly without Spring Integration. If there is only one pure Java call and no pipeline is needed, **do not add a Gateway just for the sake of it**.

A Gateway is useful when it needs to hide a real pipeline:

~~~text
Java caller
 -> Gateway proxy
 -> input validation
 -> Transformer
 -> Router by tenant/product
 -> Handler A/B
 -> Aggregator or response assembly
 -> reply to gateway
~~~

In that case, the application keeps a simple API even though the integration flow has many endpoints. However, when the topology grows complex, **every route must have reply semantics**; a Filter drop or an unreleased Aggregator will directly affect the Gateway method.

### 10.1. Ports and Adapters

A decoupled architecture can look like this:

~~~text
Domain application code
  -> QuotePort (plain Java interface)
       -> MessagingGateway adapter
            -> Spring Integration channels/endpoints
~~~

The goal does not necessarily require every domain interface to carry Spring annotations. The core distinction is that the **domain caller does not depend directly on `MessageChannel`**.

## 11. Unit Test: Testing the Business Handler Independently of Messaging

Before starting a Spring context, test the quote calculation logic:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuoteCalculatorTest {

    private final QuoteCalculator calculator =
            new QuoteCalculator();

    @Test
    void quoteBookQuantityTwo() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-1001",
                        "tenant-a",
                        "BOOK",
                        2);

        OrderQuote quote =
                calculator.quote(request, "tenant-a");

        assertEquals("quote-1001", quote.quoteId());
        assertEquals("tenant-a", quote.tenantId());
        assertEquals("BOOK", quote.sku());
        assertEquals(2, quote.quantity());
        assertEquals(240_000L, quote.totalMinorUnits());
        assertEquals("VND", quote.currency());
    }

    @Test
    void unknownSkuIsValidationError() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-1002", "tenant-a", "BAD", 1);

        QuoteValidationException error =
                assertThrows(
                        QuoteValidationException.class,
                        () -> calculator.quote(
                                request, "tenant-a"));

        assertEquals(
                "SKU_UNSUPPORTED", error.reasonCode());
    }

    @Test
    void tenantMismatchIsRejected() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-1003", "tenant-b", "PEN", 1);

        QuoteValidationException error =
                assertThrows(
                        QuoteValidationException.class,
                        () -> calculator.quote(
                                request, "tenant-a"));

        assertEquals(
                "TENANT_NOT_AUTHORIZED",
                error.reasonCode());
    }

    @Test
    void invalidQuantityIsRejected() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-1004", "tenant-a", "PEN", 0);

        assertThrows(
                QuoteValidationException.class,
                () -> calculator.quote(
                        request, "tenant-a"));
    }
}
~~~

This is only a **unit test of the handler**; it does not yet prove that the Gateway proxy was created or that the reply channel is used correctly. An integration test calling the real interface bean is also needed.
## 12. Integration Test: Calling the Gateway Interface Like a Normal API

A meaningful test must initialize the Spring context, let `@IntegrationComponentScan` register the Gateway proxy, and then call the method on the interface:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = QuoteGatewayConfiguration.class)
class OrderQuoteGatewayIntegrationTest {

    @Autowired
    OrderQuoteGateway gateway;

    @Test
    void gatewayCallsMessagingFlowAndReturnsTypedReply() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-2001", "tenant-a", "BOOK", 2);

        OrderQuote reply =
                gateway.quote(request, "tenant-a");

        assertNotNull(reply);
        assertEquals("quote-2001", reply.quoteId());
        assertEquals("tenant-a", reply.tenantId());
        assertEquals("BOOK", reply.sku());
        assertEquals(2, reply.quantity());
        assertEquals(240_000L, reply.totalMinorUnits());
        assertEquals("VND", reply.currency());
    }

    @Test
    void methodArgumentAnnotatedAsHeaderReachesHandler() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-2002", "tenant-b", "PEN", 3);

        // Header tenant-b matches payload tenant-b.
        OrderQuote reply =
                gateway.quote(request, "tenant-b");

        assertEquals(45_000L, reply.totalMinorUnits());
        assertEquals("tenant-b", reply.tenantId());
    }

    @Test
    void tenantMismatchIsNotTurnedIntoSuccess() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-2003", "tenant-b", "PEN", 2);

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> gateway.quote(request, "tenant-a"));

        assertTrue(GatewayCauseChecks.contains(
                thrown, QuoteValidationException.class));
    }

    @Test
    void invalidQuantityDoesNotProduceQuote() {
        OrderQuoteRequest request =
                new OrderQuoteRequest(
                        "quote-2004", "tenant-a", "PEN", -1);

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> gateway.quote(request, "tenant-a"));

        assertTrue(GatewayCauseChecks.contains(
                thrown, QuoteValidationException.class));
    }
}
~~~

Helper to inspect the cause chain when the framework/version wraps exceptions:

~~~java
public final class GatewayCauseChecks {

    private GatewayCauseChecks() {}

    public static boolean contains(
            Throwable exception,
            Class<? extends Throwable> expected) {

        Throwable current = exception;
        while (current != null) {
            if (expected.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
~~~

Place `GatewayCauseChecks` in a separate Java test file. Depending on the version, the Gateway may **unwrap** exceptions from the handler before throwing them to the caller or send a wrapper; the test checks the **business error type in the cause chain**, without depending on a specific wrapper shape.

### 12.1. Why Is This an Integration Test?

It verifies all of the following together:

- The `OrderQuoteGateway` interface was registered by Spring Integration as a proxy bean.
- Method invocation is converted into a message on `quote.requests`.
- `@Header("authenticatedTenant")` reaches the handler.
- The handler returns a properly typed `OrderQuote`.
- The reply is sent back to the Gateway, and the method returns the result.
- An exception from the handler is not turned into a fake quote.

The test does not call `MessageChannel.send()` directly to invoke the flow; it verifies the **messaging-API-hiding goal** of the Gateway.

### 12.2. What Has This Test Not Verified Yet?

- Real HTTP/AMQP/Kafka transports.
- Transaction/database commits or idempotency of order-creation commands.
- Timeouts when a handler is slow or stuck.
- Fields lost during serialization across two JVMs.
- Broker ACK/NACK or retry policies.
- Authorization from mTLS/JWT tokens — the demo only compares two tenant strings.

Separate tests are required for each deployed boundary; do not treat an in-memory integration test as proof of production reliability.

### 12.3. Unit Testing the Client Using a Fake Gateway

If you only want to test `QuoteApplicationService`, you can use a fake implementation of `OrderQuoteGateway` or a mock. The application does not need to start a Spring context and does not need to know about channels:

~~~java
OrderQuoteGateway fake = (request, tenant) ->
        new OrderQuote(
                request.quoteId(),
                tenant,
                request.sku(),
                request.quantity(),
                100L,
                "VND");

QuoteApplicationService service =
        new QuoteApplicationService(fake);

OrderQuote result = service.prepareQuote(
        new OrderQuoteRequest(
                "quote-9001", "tenant-a", "PEN", 1),
        "tenant-a");
~~~

Here the interface has only one abstract method, so a Java lambda can be used. A fake does not test Spring Gateway wiring; it helps keep the **business caller layer** easy to unit test.

## 13. Two Different Timeouts: `requestTimeout` and `replyTimeout`

A request-reply Gateway has at least two phases:

~~~mermaid
flowchart LR
    A["Gateway method call"] -->|"requestTimeout"| SEND["Send to request channel"]
    SEND -->|"Downstream processing"| HANDLER["Handler/flow"]
    HANDLER -->|"replyTimeout"| REPLY["Receive reply"]
    REPLY --> RET["Return method result"]
~~~

| Timeout | Where It Applies | Example |
|---|---|---|
| `requestTimeout` | Waiting to **send the message** when channel send can block | Bounded `QueueChannel` is full |
| `replyTimeout` | Waiting for the **reply message** once the Gateway reaches the receive phase | Async worker runs but reply arrives late |
| HTTP socket/connect timeout | In the outbound HTTP client | Remote API is slow/unreachable |
| Broker publish timeout | In the broker adapter | Unclear whether broker persisted the record |
| Business SLA deadline | At the business level | Quote must respond within SLA |
| Transaction timeout | In the transaction manager | Transaction must not run too long |

**Do not equate these values.** Setting `replyTimeout="3000"` does not automatically cap every downstream Java method at 3 seconds.

### 13.1. A Synchronous `DirectChannel` Is Not Interrupted by `replyTimeout`

In the configuration in Section 8, `DirectChannel` invokes the handler directly on the **caller thread**. If `QuoteCalculator` hangs inside a 60-second blocking call, the Gateway cannot run its reply-wait timer while `send()` has not yet returned. The method call duration can exceed `replyTimeout`.

~~~text
Gateway method invoked
  -> DirectChannel.send(...)
      -> handler blocks 60 seconds
      -> handler returns
  -> Gateway can observe the reply
~~~

Therefore `replyTimeout` is the **wait duration during the receive phase**, not an interrupt for synchronous execution. For remote I/O, configure **timeouts on the I/O client itself** or switch to an async mechanism with an explicit cancellation/deadline policy.

### 13.2. With `ExecutorChannel` or a Poller

If the flow hands the request off to a worker thread and `send()` returns, the Gateway can begin **waiting for the reply**. When the worker fails to respond on time, a timeout can occur before business processing finishes. The worker may still continue and produce a **late reply**.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant E as ExecutorChannel
    participant H as Slow handler

    C->>G: quote(request)
    G->>E: send(Message)
    E-->>G: Dispatch accepted
    G->>G: Wait for reply
    E->>H: Process asynchronously
    Note over G: replyTimeout elapsed
    G-->>C: null/timeout outcome per config
    H-->>G: Late reply after deadline
~~~

A timeout **does not prove** that the business action did not happen, especially when downstream calls a remote API or commits to a DB.

### 13.3. Default Timeouts May Differ by Version/Gateway Type

Different Spring Integration versions and gateway types have had different default timeouts in historical documentation. **Do not rely on unknown defaults**: set explicit request/reply timeouts aligned with your SLA, check the reference docs for your exact dependency version, and test them in practice.

### 13.4. Do Not Return `null` Silently in a Domain API

An API returning `OrderQuote` may forbid `null`. Callers should be protected by:

- Downstream **always producing a reply** for every accepted request.
- Validation failure → typed exception or explicit error reply.
- Filter/Router branches having explicit errors or `SKIPPED` outcomes.
- Enabling a **timeout exception policy** when supported by the version, or a wrapper that converts null/timeout into a domain error.
- For long-running flows, using an async result or tracking ID instead of waiting indefinitely.

In Spring Integration **6.2+**, `@MessagingGateway`/GatewayEndpointSpec offers an `errorOnTimeout` option that throws `MessageTimeoutException` when the **receive timeout** expires instead of returning `null`. This option **does not** turn `DirectChannel` into a forcibly preemptible thread and does not replace I/O timeouts.

## 14. When the Reply Never Arrives

A synchronous Gateway method has a **request → reply** contract, yet a messaging flow can have many branches that produce no reply.

### 14.1. Filter Drop

~~~text
Gateway.quote(...)
   -> Filter predicate=false
   -> Message is dropped
   -> No reply produced
   -> Gateway waits until timeout
~~~

If a `Filter` represents an "ineligible for quote" condition, an explicit `QuoteRejected` response is usually better than silent discard. If rejection is truly a contract error, configure the Filter to throw `MessageRejectedException` or validate earlier so the error reaches the caller.

### 14.2. Router Finds No Route

A Router based on SKU, tenant, or a channel header may fail to resolve an output. If the Router silently drops the message, the Gateway gets no reply. In request-reply flows, you need:

- Valid routes for all supported inputs.
- A default error/rejection route or a resolution-required policy.
- Tests for unknown inputs, not just the happy path.
- Avoid redirecting unknown messages to `nullChannel` if the API expects a reply.

### 14.3. Handler Returns `null` or `void`

If a service activator is configured to return `null` or `void`, it can complete without emitting a reply. For a Gateway method returning an object, that is a **contract violation** if no other endpoint produces a reply. Configure `requiresReply` on the handler when appropriate to fail fast, and test the behavior for your version.

### 14.4. Aggregator Fails to Release

The Gateway sends one request, but a downstream Splitter creates multiple parts and an Aggregator waits for the full group. If a Filter drops one part or correlation headers are lost, the Aggregator may never release, causing the Gateway to time out.

### 14.5. Error Flow Sends No Reply

An error entering `errorChannel` is not automatically turned into a business error response. If the error flow only logs and stops, the Gateway may keep waiting. Error handling must be defined clearly: **rethrow**, construct a typed error reply, or return a tracking ID.

## 15. One-Way `void` Methods and Fire-and-Forget

Not every Gateway method needs a reply:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface AuditGateway {

    @Gateway(requestChannel = "audit.commands")
    void record(AuditEvent event);
}
~~~

Here `AuditEvent` is an application DTO you must declare yourself. A `void` Gateway method fits a **one-way message contract** when the caller needs no business reply. However:

- With a synchronous `DirectChannel`, `void` can still **block** until the downstream handler finishes.
- With an async channel, `void` may return after the request is dispatched, **not necessarily when processing completes**.
- With a broker, returning `void` does not by itself prove the broker persisted the message.
- Exceptions on a worker thread after a `void` caller has returned cannot simply be thrown back onto the old call stack.
- If the business needs confirmation, use a typed receipt/ack contract or async completion rather than assuming `void` means "success."

Since Spring Integration 5.4, for a `void` Gateway method with no explicit reply channel, the framework can set `nullChannel` as the reply destination to suppress unnecessary replies. Do not overgeneralize this into a guarantee of no side effects.

### 15.1. Method Naming Does Not Create Semantics

~~~java
void sendAndForget(OrderCommand command);
~~~

The method name `sendAndForget` is just a name. Durability, ACK level, retries, duplicates, and timeouts still depend on the actual integration flow and transport. If you need **at-least-once delivery**, design the broker, persistent queue, and transactions; do not treat a method name as a delivery guarantee.

## 16. Async Gateway: `Future`, `CompletableFuture`, and `Mono`

When quoting must call a slow service, an async Gateway lets the caller **avoid blocking a thread** while waiting for the result.

### 16.1. Interface Returning `CompletableFuture<OrderQuote>`

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway(
        name = "asyncOrderQuoteGateway",
        asyncExecutor = "quoteExecutor")
public interface AsyncOrderQuoteGateway {

    @Gateway(requestChannel = "quote.requests")
    CompletableFuture<OrderQuote> quoteAsync(
            OrderQuoteRequest request,
            @Header("authenticatedTenant") String tenant);
}
~~~

With the configured executor, the Gateway can run the flow on the executor and return a `CompletableFuture` to the caller. The application can compose it:

~~~java
CompletableFuture<OrderQuote> future =
        asyncGateway.quoteAsync(request, "tenant-a");

future.thenApply(OrderQuote::totalMinorUnits)
      .thenAccept(total -> recordTotal(total));
~~~

**Do not call `future.join()` immediately on the request thread** and call it end-to-end async; that merely moves blocking to another spot.

### 16.2. Bounded Executor

An illustrative `ThreadPoolTaskExecutor` configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.util.concurrent.Executor;

@Bean(name = "quoteExecutor")
public Executor quoteExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("quote-gateway-");
    executor.initialize();

    return executor;
}
~~~

The method above must be placed inside a `@Configuration` class. The thread/queue values are only **examples** and must be tuned based on CPU/I/O capacity, rejection policy, downstream SLA, and load tests.

### 16.3. `Future` Differs from Send-Only

A `CompletableFuture<OrderQuote>` can complete **with a value or an exception**. It is not merely "accepted into a queue." When a flow is truly asynchronous across a broker to another system, callbacks/correlation are needed to complete the future for the right request and handle lost or late replies.

### 16.4. `asyncExecutor = NULL` Is a Different Mode

Spring Integration supports the case where **downstream already returns a `Future`/`Mono`** and the gateway only needs to pass that async object back to the caller. In that case, you can disable the internal async executor using `AnnotationConstants.NULL` (depending on version/config). This is a **different mode** from the gateway offloading a synchronous handler onto an executor; do not mix the two modes.

### 16.5. Reactor `Mono<T>`

A Gateway can return `Mono<OrderQuote>` when the project uses Project Reactor. With reactive composition, the flow may be triggered on subscribe, depending on the implementation path and version. Never assume `Mono` means a message was already sent at method-call time; understand subscription lifecycle, cancellation, context propagation, and error signals.

### 16.6. Async Still Needs Deadlines and Idempotency

When a future times out on the caller, the downstream business operation may still be running. Canceling a `CompletableFuture` does not guarantee canceling a payment API call or a dispatched broker task. If an operation has side effects, a stable command ID and reconciliation matter more than having an async return type on the caller.

## 17. Explicit Reply Channel: When Is It Needed?

In many request-reply flows, the temporary reply channel created by the Gateway is enough:

~~~text
Gateway request:
  headers.replyChannel = temporary point-to-point channel
~~~

You can set `defaultReplyChannel`/`replyChannel` when you need to monitor or bridge results through a named channel. However:

- A shared reply channel for many in-flight requests **cannot** arbitrarily receive messages and deliver them to the wrong caller.
- When configuring an explicit reply channel, Spring Integration has a mechanism to bridge back to the temporary gateway reply channel; check the exact behavior for your framework version.
- If multiple subscribers need to observe replies, you can use a controlled `PublishSubscribeChannel`.
- With a point-to-point `DirectChannel` having multiple competing subscribers, messages can go to the wrong consumer if designed incorrectly.
- For a flow with a single handler returning a payload, **do not** create an explicit reply channel just to make the code look "complete."

**Recommendation:** start with the temporary reply channel managed by the Gateway; only add a named reply channel when there is a tested need for observation, bridging, or a special contract.

## 18. Combining Gateway with Router, Filter, and Transformer

The Gateway initiates the flow, while the flow can route by payload/headers before producing a reply:

~~~mermaid
flowchart TD
    C["Gateway.quote(request)"] --> V["Validate request"]
    V --> R{"Router by SKU"}
    R -->|"BOOK"| B["Quote book handler"]
    R -->|"PEN"| P["Quote pen handler"]
    R -->|"Unsupported"| E["Typed rejection"]
    B --> A["OrderQuote reply"]
    P --> A
    A --> G["Gateway returns"]
    E --> G
~~~

### 18.1. Every Branch Must Have an Outcome

If an SKU is unsupported:

- Return a typed error or a business reply such as `UNSUPPORTED_SKU`.
- Do not silently drop the input and leave the Gateway waiting until reply timeout.
- If using a `Filter`, check `throwExceptionOnRejection` and `discardChannel` against the semantic contract.
- If using a `Router`, configure an explicit fallback/error route or resolution-required behavior.

### 18.2. Transformers Should Not Lose Reply Metadata

A Transformer returning a new payload generally benefits from Spring Integration header propagation within the flow, but when constructing a new `Message<?>` manually or crossing a serialization boundary, code can lose `replyChannel`, `errorChannel`, or correlation headers. If `replyChannel` is lost, the Gateway may never receive the result even when the business handler returned an object.

### 18.3. Gateway and Aggregator

If a method needs to combine multiple quotes:

~~~text
Gateway.getBestQuote(request)
  -> Split request to multiple providers
  -> Aggregate replies by business request ID
  -> Select best
  -> Return one QuoteResult
~~~

You must define:

- A stable `quoteRequestId` correlation key.
- Release strategy: wait for all responses or a quorum?
- Group timeout and incomplete-result policy.
- Duplicate replies from a broker.
- A **single** output matching the return type.
- Reply channel back to the right Gateway invocation.

If the group fails to release, the Gateway times out; if the same request ID is carelessly reused, calls can mix up replies.

## 19. Error Handling: Exceptions from Flow to Caller

### 19.1. Downstream Handler Throws an Exception

In a synchronous `DirectChannel` flow, `QuoteCalculator.quote(...)` throws `QuoteValidationException` for an invalid payload. Spring Integration messaging infrastructure may wrap it in `MessagingException` with `failedMessage`, and the Gateway typically unwraps/propagates the cause to the caller. Do **not** assume every version or topology always throws the exact same wrapper.

### 19.2. `errorChannel` Is an Error-Handling Path, Not a Normal Reply

A Gateway can be configured with an error channel—for example, an error flow receiving `ErrorMessage` to perform logging/classification or return an error result. However:

- An error flow that only logs may **provide no reply** to the Gateway.
- An error flow can **rethrow** or build a typed response according to the contract.
- `ErrorMessage` usually carries a `Throwable` payload, **not** an `OrderQuote`.
- If a Gateway has return type `OrderQuote`, do not return an error `String` expecting the proxy to figure it out.
- Never turn every error into `null` just to make tests pass.

### 19.3. Classifying Errors by Retryability

| Error | Example | Recommended Policy |
|---|---|---|
| Invalid input | `quantity=0` | Non-retryable validation error |
| Wrong tenant permission | Authenticated tenant differs from payload | Deny/audit, do not auto-retry |
| Unsupported SKU | `sku=BAD` | Explicit business rejection |
| DB deadlock | Transient transaction failure | Bounded retry/backoff |
| Remote HTTP 503 | Service unavailable | Retry with deadline |
| Remote payment timeout | Unclear if payment committed | Idempotency/reconciliation |
| Gateway reply timeout | No response before deadline | Unknown business outcome if side effects exist |
| Filter silent drop | No reply | Fix flow contract, never treat as success |
| Unexpected exception | Bug/invariant violation | Alert, appropriate error, no silent discard |

### 19.4. A Timeout Exception Is a Transport/Application Outcome, Not a Business Rollback

A `MessageTimeoutException` (when configured) states that the Gateway **did not receive a reply before the deadline**; it does not prove that a downstream DB transaction rolled back. For non-idempotent operations, retrying after a timeout can cause duplicate side effects. You need a stable request/command ID and a way to query status.

## 20. Gateway and Transaction Boundaries

A Gateway in the same JVM can send synchronously over `DirectChannel`, yet transactional guarantees still depend on where the transaction opens and where data is written.

~~~text
Application method
  -> Gateway
  -> DirectChannel
  -> @Transactional business handler
  -> database commit
  -> reply
~~~

If the handler is invoked properly through a Spring transaction proxy and commits successfully before returning a reply, a receipt can reflect committed business state. But if the handler sends the reply **before** the transaction actually commits, or if the flow crosses an async boundary, the return value can arrive before a durable outcome.

### 20.1. Do Not Assume the Gateway Creates a Transaction

`@MessagingGateway` does not automatically open an effective transaction spanning DB, broker, and remote APIs. The transaction manager, adapter, and handler must be configured explicitly.

### 20.2. Do Not Confuse "Accepted" with "Completed"

For long-running operations, the API can return:

~~~java
public record SubmissionAccepted(
        String commandId,
        String trackingId,
        String status
) {}
~~~

An `ACCEPTED` reply may only prove that the task was persisted in a durable inbox/outbox/queue, **not** that payment or shipment has finished. Separate `submit(...) -> AcceptedReceipt` from `getStatus(trackingId)` or a subsequent completion event.

### 20.3. Exactly-Once Does Not Come from the Gateway

If a broker redelivers the same command because an ACK was lost, the Gateway/handler can run again. You need an Idempotent Receiver, a unique business key, and an appropriate transaction marker alongside side effects. If business logic calls a remote API, use a remote idempotency key or reconciliation; a Gateway method cannot solve crash windows by itself.
## 21. Gateway Request-Reply Across Multiple JVMs or Brokers

The Gateway proxy is registered in the **calling application's Spring ApplicationContext**. If the backing flow goes out to Kafka, JMS, AMQP, or another HTTP service, you are crossing a **transport boundary**.

~~~mermaid
sequenceDiagram
    participant A as Application Caller
    participant G as Local Gateway Proxy
    participant P as Request Publisher
    participant B as Broker
    participant W as Remote Worker
    participant R as Reply Consumer

    A->>G: submit(command)
    G->>P: Message + correlation
    P->>B: Publish request with reply destination
    B->>W: Deliver request
    W->>W: Process / commit
    W->>B: Publish reply with correlation ID
    B->>R: Deliver reply
    R-->>G: Resolve waiting request
    G-->>A: Typed result
~~~

### 21.1. A Java `replyChannel` Is Not a Remote Reply Destination

Within the same JVM, the Gateway can attach a `replyChannel` that is a **MessageChannel object** in headers. Across a broker or HTTP, this Java object does not automatically exist in the other process. The adapter needs an appropriate **reply-address protocol**:

- JMS: reply-to destination/correlation ID per the adapter/contract.
- AMQP: reply-to / direct reply-to / reply queue per the RabbitMQ adapter.
- Kafka: reply topic/partition and correlation headers per the Spring Integration Kafka adapter or custom protocol.
- HTTP: response bound to the request connection, or callback/polling if async.

Never serialize a `DirectChannel` object into a JSON envelope expecting a remote service to send a reply to it.

### 21.2. Correlation Must Map to the Exact Invocation

Two callers can send quote requests concurrently:

~~~text
Invocation A: quoteId=quote-1001
Invocation B: quoteId=quote-1002

Both requests -> same broker
Replies can arrive B before A
~~~

To return the reply to the right caller, the adapter needs a unique correlation token for each **request attempt / in-flight exchange** per its rules. A business `quoteId` helps with auditing/idempotency, but it is not automatically a safe correlation token for all concurrent invocations if a business request can be retried.

### 21.3. Replies Arriving Late After a Gateway Timeout

~~~text
t0: Gateway sends request.
t1: Caller exceeds replyTimeout, gets timeout.
t2: Worker commits business transaction.
t3: Reply arrives on topic; no caller is waiting anymore.
~~~

Late replies require a policy: discard with a metric, store the outcome in a result store, or route to a reconciliation handler. **Do not** assume a timeout means the worker did nothing and blindly send a new command with a different event ID.

### 21.4. Brokers Do Not Provide "RPC Exactly-Once"

A request/reply over a broker can be duplicated:

- Request publish succeeded, but the sender lost the ACK.
- Consumer committed the business action and crashed before committing the offset.
- Reply publish succeeded, then the worker retried.
- Caller retried after a timeout.

Therefore, you need a stable command ID, an idempotent receiver, and the ability to return a **cached result/receipt** for duplicate requests. A Gateway lets you express the operation as a method, but it does not eliminate the broker's at-least-once semantics.

### 21.5. When Should You Avoid a Synchronous Remote Gateway?

If an operation takes several minutes—such as creating a shipment, reconciling a payment, or importing thousands of items—holding a Java/HTTP thread waiting for a reply can exhaust threads/connections and cause late-reply problems.

It is usually better to use:

~~~text
submit(command) -> AcceptedReceipt(commandId, trackingId)
getStatus(trackingId) -> ProcessingStatus
event completed -> Notification / Callback
~~~

Separating **request acceptance** from **business completion** fits asynchronous workflows much better.

## 22. Messaging Gateway vs. Inbound/Outbound HTTP Gateway

The word "Gateway" appears in several Spring Integration components:

~~~mermaid
flowchart LR
    HTTP["HTTP Caller"] --> I["HTTP Inbound Gateway"]
    I --> F["IntegrationFlow"]
    J["Java Application"] --> M["@MessagingGateway Proxy"]
    M --> F
    F --> H["HTTP Outbound Gateway"]
    H --> REM["Remote API"]
~~~

### 22.1. `@MessagingGateway`

Defines an **interface** inside the JVM:

~~~java
OrderQuote quote(OrderQuoteRequest request, String tenant);
~~~

Callers receive the injected proxy bean and invoke methods. It is not an HTTP server endpoint.

### 22.2. HTTP Inbound Gateway

Receives an HTTP request, maps body/headers into a Spring Message, sends it to the request channel, waits for the reply, and maps it to an HTTP response. Requires configuring path/method/content type/security/timeouts.

### 22.3. HTTP Outbound Gateway

An endpoint inside an integration flow that calls an external HTTP service and receives an HTTP response, typically with its own HTTP client timeouts and error handling. It is not an interface proxy for the business application.

### 22.4. Layering Multiple Gateways

You can structure it as:

~~~text
HTTP Inbound Gateway
  -> validation
  -> Java business/integration flow
  -> HTTP Outbound Gateway
  -> reply
  -> HTTP Inbound Gateway response
~~~

Or a Spring MVC Controller calling `OrderQuoteGateway`. Avoid accidentally creating **two nested request-reply bridges with inconsistent reply channels**. Choose a clear boundary and test end-to-end.

### 22.5. A Java Gateway Does Not Replace Authentication

Even though callers invoke a Java interface, an upstream HTTP request still requires authentication, authorization, rate limiting, and validation at ingress. `@Header("authenticatedTenant")` is merely an **in-JVM data transport channel**, not an identity verification mechanism.

## 23. XML Gateway and Advanced Configurations

Java annotations/DSL are not the only way. A gateway proxy can be configured using the Spring Integration XML namespace:

~~~xml
<int:gateway
    id="orderQuoteGateway"
    service-interface="com.example.integration.OrderQuoteGateway"
    default-request-channel="quote.requests"
    default-request-timeout="2000"
    default-reply-timeout="3000"/>
~~~

The XML example assumes the `int` namespace, Spring beans, and interface in the corresponding package are declared. Do not register the proxy **both** via XML and `@IntegrationComponentScan` with the same bean ID unless you deliberately configure a single registration.

### 23.1. Method-Level Request Channel Override

~~~xml
<int:gateway
    id="operationGateway"
    service-interface="com.example.integration.OperationGateway"
    default-request-channel="operations.default">
    <int:method
        name="quote"
        request-channel="quote.requests"
        request-timeout="2000"
        reply-timeout="3000"/>
</int:gateway>
~~~

The `quote` method on the interface and the channels must actually be declared. `@Gateway` annotations can override some corresponding XML settings; avoid conflicting configuration sources.

### 23.2. Gateway Methods Without Arguments

Do not assume a zero-argument method always sends an empty message:

~~~java
OrderStatus getStatus();
~~~

Under Gateway mechanics, a no-argument method can be interpreted as **receiving from a `PollableChannel`** if there is no payload to send. To perform a request-reply operation without arguments, specify a **payload expression** on `@Gateway` or `@Payload` per the contract:

~~~java
@Gateway(
        requestChannel = "status.commands",
        payloadExpression = "'QUERY_CURRENT_STATUS'")
String queryCurrentStatus();
~~~

The value `"QUERY_CURRENT_STATUS"` is a **meaningful command payload**. You need an endpoint handler for `status.commands` and a `String`-compatible reply. This is an example method inside a gateway interface, not a standalone program.

### 23.3. Overloads and Generic Return Types

An interface with many overloaded methods, SpEL payload expressions, and generic return types can make mapping hard to trace. Prefer clear method names and DTOs, and test each method-level `requestChannel` and return conversion. Do not rely on reflection over generic types to auto-map an envelope lacking a schema/version contract.

## 24. Security and Data Contracts When the Gateway Hides Infrastructure

Hiding `MessageChannel` does not mean hiding **data safety responsibilities**.

### 24.1. Validation at Both the API and Business Boundaries

The caller sends `OrderQuoteRequest` as a Java record, yet a record can still contain a negative quantity, wrong `tenantId`, or invalid SKU. The Gateway does not automatically turn a record into a validated domain command. Handlers/validators must validate before computation and side effects.

### 24.2. Do Not Trust Arbitrary Caller Headers

If an untrusted client chooses `authenticatedTenant` itself, having the service compare it against `tenantId` in the payload only proves **two strings are equal**, not access rights. The authentication adapter must supply the tenant context from a trusted principal. In the demo, tests pass strings to focus on the messaging API, which does not replace a security integration test.

### 24.3. Header Allowlist When Leaving the JVM

A Gateway message can contain:

~~~text
headers:
  replyChannel = temporary in-JVM channel
  errorChannel = in-JVM error destination
  authenticatedTenant = tenant-a
  traceparent = W3C tracing context
  Authorization = bearer token (if added mistakenly by caller)
~~~

When publishing to a broker or another HTTP endpoint, the adapter must apply a header mapper/allowlist:

- Do not export Java `replyChannel` objects.
- Do not forward `Authorization` tokens unless an intentional token-exchange mechanism exists.
- Do not put secrets/PII on shared topics.
- Propagate trace context according to instrumentation and trust policy.
- Verify tenant/source at the right boundary.
- Content type/schema version must reflect the **current** payload, not stale headers after transformation.

### 24.4. The Gateway Interface Is an Application Contract

Changing `OrderQuote quote(...)` to `void quote(...)` breaks **semantic compatibility** even if the adapter side compiles. Replacing `OrderQuote` with a new DTO version can break callers. Version interfaces/payloads like an API, test consumer contracts, and define errors/timeouts explicitly.

## 25. Observability: Visibility into Methods, Channels, and Business Outcomes

A Gateway introduces an abstraction layer. If you only observe Java method duration, you may not know whether slowness comes from sending, the handler, the broker, or waiting for the reply.

| Metric | Meaning | Recommended Labels |
|---|---|---|
| `gateway_invocations_total` | Number of method calls | method, outcome |
| `gateway_request_send_seconds` | Request channel send latency | channel/flow |
| `gateway_reply_wait_seconds` | Time spent waiting for reply | method |
| `gateway_timeout_total` | Number of timeouts | phase (send/reply) |
| `gateway_reply_null_total` | Missing reply payload per contract | method |
| `gateway_validation_error_total` | Invalid input | reasonCode |
| `gateway_handler_error_total` | Business handler error | error class |
| `gateway_async_inflight` | In-flight futures/requests not yet completed | flow |
| `gateway_late_reply_total` | Replies arriving after deadline | flow |
| `gateway_aggregate_expired_total` | Groups that failed to release in time | flow |
| `gateway_duplicate_command_total` | Duplicate commands by stable ID | flow |
| `gateway_broker_publish_error_total` | Publish failure | adapter |
| `gateway_total_duration_seconds` | End-to-end method duration | method |

Example log:

~~~text
service=quote-service
flow=quote-requests
gatewayMethod=quote
quoteId=quote-1001
tenant=tenant-a
outcome=SUCCESS
durationMs=16
traceId=trace-1001
~~~

### 25.1. Do Not Use High-Cardinality IDs as Metric Labels

`quoteId`, `orderId`, `tenantId` in some large systems, and `traceId` can have very high cardinality. Never put them into labels for every time series. Use access-controlled logs/traces with sampling and retention, or aggregate metrics by method/outcome/reasonCode.

### 25.2. Correlation Between Gateway and Downstream

Use tracing context to link the caller span, Gateway send, service activator, broker publish/consume, and reply. The business request ID serves idempotency/reconciliation; the trace ID serves observability. Never use a trace ID in place of a business ID when a caller retries under a new trace.

### 25.3. Worthwhile Alerts

- Gateway reply timeouts spike after a Router/Filter change.
- Method duration is high even though request send is fast.
- Async in-flight count rises and the worker pool runs out of capacity.
- `null` replies increase after a Handler/Normalizer release.
- Broker publish timeouts rise while business side effects still execute.
- Late replies increase after a network partition.
- Aggregator groups are missing sequence parts.
- Caller retries cause duplicate commands to increase.
- `TENANT_NOT_AUTHORIZED` appears abnormally.

## 26. Common Anti-Patterns

| Mistake | Consequence | Fix |
|---|---|---|
| Business services inject `MessageChannel` everywhere | Coupling to infrastructure | Expose a Java Gateway/port |
| Thinking `@MessagingGateway` creates an HTTP endpoint | No HTTP listener | Configure an HTTP inbound gateway/controller |
| Forgetting `@IntegrationComponentScan`/registration | No gateway proxy bean | Enable scan/import for the right package/version |
| Gateway method returns a DTO but handler does not reply | Timeout/null | Ensure a reply or typed rejection |
| Filter default-drop in request-reply | Caller waits pointlessly | Explicit outcome/throw |
| Router unknown route without fallback | No reply | Required resolution/error route |
| Thinking `replyTimeout` interrupts a `DirectChannel` handler | Method still blocks | I/O deadlines/async design |
| Thinking `requestTimeout` is the business timeout | Misunderstood SLA | Separate send/reply/business |
| One named `QueueChannel` shared improperly for replies | Replies cross between callers | Gateway temporary reply + proper correlation |
| Copying raw `replyChannel` to Kafka | Remote JVM lacks the channel object | Broker reply destination/correlation protocol |
| Treating `void` method as committed | Lost work/false success | Typed durable acceptance receipt |
| Caller retries after timeout with a new command ID | Duplicate side effects | Stable ID + idempotency/reconciliation |
| Async Gateway uses an unbounded executor | Thread/memory pressure | Bounded executor/backpressure |
| Calling `future.join()` immediately and calling it async | Still blocks caller | Compose the async result |
| Error channel only logs while Gateway needs a reply | Caller timeout | Typed error reply/rethrow |
| Gateway returns `null` as a valid quote | Errors leak into business logic | Timeout/error contract |
| Assuming Gateway creates a DB/broker transaction | Non-atomic commits | Transaction/outbox/ACK policy |
| Using trace ID as idempotency key | Retry has new trace → duplicate | Business command/event ID |
| Trusting client-supplied headers as auth | Cross-tenant access | Verify principal at ingress |
| Unit testing only the handler, not the Gateway proxy | Wiring bugs go undetected | Spring integration tests |
| Testing only the happy path without timeouts | Unexpected production timeouts | Fault injection/late reply tests |
| Creating duplicate gateway beans from XML + scan | Bean conflicts/misrouting | Single registration source |
| Changing interface return type without versioning | Client break | API contract/consumer tests |

## 27. Hands-On Exercises and Test Matrix

### 27.1. Exercises

**Exercise 1 — Refactor the caller.** Refactor `DirectChannelQuoteCaller` using `MessageBuilder/send()` into `QuoteApplicationService` calling only `OrderQuoteGateway.quote(...)`.

**Exercise 2 — Gateway interface.** Create `@MessagingGateway(defaultRequestChannel="quote.requests")` with a request and typed reply.

**Exercise 3 — Header mapping.** Use `@Header("authenticatedTenant")`; test that the header reaches `QuoteCalculator` via Java DSL.

**Exercise 4 — Wiring.** Place `@EnableIntegration` and `@IntegrationComponentScan` on the right package. Test that the Spring context has the `OrderQuoteGateway` bean.

**Exercise 5 — Unit vs. integration.** Write `QuoteCalculatorTest` and `OrderQuoteGatewayIntegrationTest`; explain which test catches channel errors.

**Exercise 6 — Filter drop.** Add a `quantity>0` Filter without throwing; observe the no-reply path in a flow with a safe timeout, then fix it with a validation error or typed reply.

**Exercise 7 — Router unknown.** Route by `sku`, send an unmapped SKU; avoid silent discard.

**Exercise 8 — DirectChannel timeout.** Insert a bounded-sleep handler in the sync flow; compare the method duration with `replyTimeout` and explain why it does not interrupt the handler.

**Exercise 9 — ExecutorChannel.** Move a stage to an executor, configure a short `replyTimeout`; simulate a late reply and record a metric.

**Exercise 10 — Async future.** Add `AsyncOrderQuoteGateway` with a bounded executor; compose the result via `CompletableFuture`, test exception propagation.

**Exercise 11 — One-way.** Create `AuditGateway.record(AuditEvent)` returning `void`; distinguish dispatch success from durability.

**Exercise 12 — Header leakage.** Ensure outbound HTTP/Kafka adapters do not serialize `replyChannel`, tokens, or internal Java objects.

**Exercise 13 — Broker request-reply.** Design request/reply topics with correlation ID and reply-to contract; test two requests returning replies out of order.

**Exercise 14 — Gateway/API timeout.** When the caller times out but the worker commits afterward, query status by stable command ID without creating a new command.

**Exercise 15 — Aggregator.** Split a request to three providers, aggregate by request ID, complete on full/quorum/expiry, and return a single typed reply.

**Exercise 16 — Validation/security.** Send a `tenantId` differing from the authenticated principal, ensure the handler rejects; verify client-supplied headers are not trusted.

**Exercise 17 — Contract version.** Change the reply DTO and create a consumer contract test to detect the API break.

**Exercise 18 — Observability.** Measure request send, handler time, reply wait, timeout, late reply, and duplicate business commands.

**Exercise 19 — No-arg method.** Create `@Gateway(payloadExpression="'PING'")` to actively send a request from a zero-argument method.

**Exercise 20 — Fault injection.** Inject Filter drops, database timeouts, broker ACK loss, and reply delays; build an outcome matrix across caller/worker.

### 27.2. Minimum Test Matrix

| Test Case | Expected |
|---|---|
| Interface bean is scanned | Autowiring `OrderQuoteGateway` succeeds |
| Quote BOOK x2 | Typed reply, amount 240000 |
| Quote PEN x3 | Typed reply, amount 45000 |
| Tenant from header matches payload | Handler receives correct context |
| Tenant header mismatch | Validation exception |
| Negative quantity | Non-retryable validation error |
| Unknown SKU | Typed rejection/error |
| Reply matches type | Gateway returns DTO |
| Handler returns null | Clear timeout/error contract |
| Filter drop | No indefinite waiting |
| Router has no route | Verified error/fallback |
| Slow DirectChannel handler | Reply timeout does not preempt handler |
| Delayed ExecutorChannel reply | Timeout/late reply policy |
| `void` method | Does not promise business completion |
| `CompletableFuture` | Completes with result or exception |
| Broker request-reply A/B | Replies do not cross-wire |
| Broker redelivery | Stable command ID, idempotent downstream |
| Gateway caller timeout | Does not assume worker rolled back |
| Async worker failure | Error logged and routed to the right channel |
| Incomplete Aggregator | Clear group expiry/partial outcome |
| Authenticated tenant mismatch | Denied before side effects |
| Header contains secret | Does not leak to transport |
| Schema/reply DTO version change | Contract test catches break |
| Trace propagation | Does not replace business request ID |
| Metric labels | Do not contain unbounded IDs |

### 27.3. Self-Check Questions

1. What kind of coupling does the Messaging Gateway EIP solve?
2. What does `GatewayProxyFactoryBean` create?
3. Does a business caller need to import `MessageChannel`?
4. How does `@MessagingGateway` differ from an HTTP inbound gateway?
5. What is the role of `@Gateway` on individual methods?
6. Where does `@Header` map an argument?
7. Why is `@IntegrationComponentScan` needed for interfaces?
8. Does the Gateway automatically create a temporary reply channel?
9. When should you configure a named reply channel?
10. How does `requestTimeout` differ from `replyTimeout`?
11. Why does `replyTimeout` not interrupt a blocking `DirectChannel` handler?
12. What happens to the Gateway if a Filter returns false and drops the message?
13. What policy is needed if a Router has no route?
14. Is a handler returning `null` a valid `OrderQuote`?
15. What error does `requiresReply` help catch early?
16. Does a `void` method mean durable fire-and-forget?
17. How does `CompletableFuture<OrderQuote>` differ from `void`?
18. Why is a bounded async executor necessary?
19. Can a `replyChannel` object be sent across a broker/JVM?
20. How does a broker match replies to the right caller?
21. How should a late reply after timeout be handled?
22. Why does a timeout not prove a business operation rolled back?
23. Does a Gateway automatically create a transaction?
24. Why is a stable command ID needed when retrying?
25. How does `ErrorMessage` differ from a typed business reply?
26. Does a Gateway API replace authentication/authorization?
27. How do you test the Gateway proxy rather than just the handler?
28. When should you return `AcceptedReceipt` + `trackingId` instead of waiting for completion?
29. How does an unreleased Aggregator affect a Gateway?
30. Why shouldn't a tracing ID be used as an idempotency key?

## 28. Messaging Gateway Implementation Checklist

- [ ] Gateway interface has method names/DTOs/return types expressing the business contract.
- [ ] Business callers do not need to create Spring `Message`s or send to `MessageChannel`.
- [ ] `@MessagingGateway` is scanned/imported properly without creating duplicate proxy beans.
- [ ] `defaultRequestChannel` and method-level overrides point to existing channels.
- [ ] `@Header` arguments come from trusted sources with clear semantics.
- [ ] Request/response DTOs are validated and versioned when needed.
- [ ] A handler/service activator actually returns a reply for non-void methods.
- [ ] All Router/Filter branches have explicit reply or error outcomes.
- [ ] Default discard/`nullChannel` is not used for requests requiring replies.
- [ ] `requestTimeout` and `replyTimeout` are set explicitly per SLA.
- [ ] Separate timeouts exist for HTTP clients, DB, and remote dependencies.
- [ ] Understood that synchronous `DirectChannel` handlers are not preempted by `replyTimeout`.
- [ ] Async flows have late-reply, cancellation/deadline, and backpressure policies.
- [ ] Unbounded executors/queues are not used in production without limits.
- [ ] `void` methods are not treated as "committed successfully."
- [ ] For long requests, consider a durable acceptance receipt + status API.
- [ ] Temporary gateway `replyChannel` is kept within the in-JVM reply path.
- [ ] Across brokers/HTTP, a dedicated reply destination/correlation protocol is used.
- [ ] `replyChannel`/`errorChannel` objects are never serialized across JVMs.
- [ ] Business idempotency keys remain stable across retries/redeliveries.
- [ ] Transaction/ACK/outbox policies exist when business effects need durability.
- [ ] Error flows classify validation, security, transient, timeout, and unknown errors.
- [ ] `null` is not returned as a valid business result if forbidden by the API contract.
- [ ] Authentication/authorization sit at the trust boundary; headers are not blindly trusted.
- [ ] Header mapper/allowlist blocks credentials and PII.
- [ ] Correlation/tracing headers serve their proper role and do not replace business IDs.
- [ ] Unit tests cover the handler and integration tests invoke the real Gateway interface.
- [ ] Error/timeout, Filter drop, Router no-route, late reply, and concurrency are tested.
- [ ] Aggregator group release/incomplete cases are tested if Splitter/Aggregator are present.
- [ ] Contract tests protect callers when changing methods, reply DTOs, or schema versions.
- [ ] Logs/metrics include method/outcome/latency/timeout with bounded labels.
- [ ] Event/quote/trace IDs are never used as high-cardinality metric labels.
- [ ] A runbook exists for DLQ/replay recovery and post-timeout reconciliation.

## 29. Summary

**Messaging Gateway Hides MessageChannel Behind an API** is a clear application of separating **business logic** from **integration infrastructure**. With `@MessagingGateway`, Spring Integration generates a proxy bean for a Java interface: the caller invokes methods with business DTOs, the proxy converts arguments into a message, sends it to the request channel, manages the temporary reply channel, and returns a typed result or error per the contract.

However, **hiding the messaging API does not mean hiding messaging semantics**. A non-void method needs a real reply; a Filter drop, unresolved Router, handler returning null, or unreleased Aggregator can all cause the Gateway to wait, time out, or lack a result. `requestTimeout` mainly relates to a potentially blocking send, while `replyTimeout` relates to the reply-waiting phase; it does not forcibly interrupt a handler running synchronously on `DirectChannel`. With `ExecutorChannel`/brokers, a timeout can occur before a business commit, and late replies must be designed for.

In **SPRING_INTEGRATION_PATTERN**, use the Gateway as an **application-facing port** for Router, Filter, Transformer, Splitter, Aggregator, retry, and error-channel flows; while clearly defining typed errors, caller deadlines, business idempotency, authentication, transaction/ACK, and tracing. Done right, business code stays readable, easy to mock/test, and capable of evolving its messaging implementation without breaking the correctness of the request-reply contract.

### References

- Enterprise Integration Patterns — Messaging Gateway: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Spring Integration Reference — Messaging Gateways: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference — Message: https://docs.spring.io/spring-integration/reference/message.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Gateway API: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Gateway.html
- Spring Integration Reference — MessagingGateway API: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/MessagingGateway.html
- Spring Integration Reference — IntegrationComponentScan API: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/IntegrationComponentScan.html
- Spring Framework Reference — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/




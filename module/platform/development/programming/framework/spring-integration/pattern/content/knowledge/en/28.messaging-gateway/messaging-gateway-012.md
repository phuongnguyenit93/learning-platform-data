# Testing Gateways by Their Public Contract

**Messaging Gateway** in Spring Integration hides creating `Message<?>`, sending to a `MessageChannel`, managing `replyChannel`, and converting replies into the return value of a **Java interface**. When another part of the application depends on that interface, what matters most is not which `DirectChannel`, `Router`, or `Transformer` backs the endpoint, but the **public contract** callers actually observe: which method to call, what to pass, what comes back, when errors occur, and what is guaranteed once a call returns.

**Testing Gateways by Their Public Contract** belongs to the **Messaging gateway** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module's goal is to learn how to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practice Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation while testing and observing processing branches.

**Core focus:** Test a gateway by **calling the interface like a real consumer**, observing result/error types and semantics at the API boundary, and then adding channel/adapter tests at the appropriate layers. A passing `inputChannel.send(message)` test **does not prove** that the gateway proxy was registered, method arguments map to the right headers, replies return to the right caller, or the API has not drifted.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the differences between a **gateway public contract**, **messaging implementation**, and **transport contract**.
2. Define a Java interface contract with explicit request, reply, business rejection, and exception semantics.
3. Distinguish business handler unit tests, fake-backed consumer contract tests, Spring gateway integration tests, and end-to-end adapter tests.
4. Write `@MessagingGateway`/`@Gateway` and use `@Header` to pass controlled caller context.
5. Bootstrap gateway proxies with `@IntegrationComponentScan` and verify the interface can be injected.
6. Call the **actual public method** in JUnit 5 to test request–reply results.
7. Test reply values, required fields, business rejections, access-control errors, and behavior when a handler produces no reply.
8. Distinguish `requestTimeout`, `replyTimeout`, and client/broker timeouts; never equate timeout with rollback.
9. Test correlation when multiple gateway invocations run concurrently.
10. Test compatibility of method signatures, DTOs, null policies, and error taxonomies.
11. Avoid tests coupled to internal bean names, how many times a Router/Transformer ran, or `MessageHeaders.ID` when they are outside the contract.
12. Use fakes/mocks appropriately and understand why passing fake tests **does not prove Spring proxy wiring**.
13. Define tests for async `CompletableFuture<T>`, one-way `void`, and request–reply gateways over brokers.
14. Test retries, idempotency, and duplicate messages at the right layer instead of attributing guarantees to the Java gateway alone.
15. Build a contract test matrix and launch checklist usable when upgrading Spring Integration or refactoring flows.

## 2. What Is a "Public Contract"?

A public contract is the set of expectations a **consumer has the right to rely on**, not a description of every class inside the flow.

~~~mermaid
flowchart LR
    C["Consumer / Application"] -->|"Java method"| G["Public Gateway Interface"]
    G -->|"Message & headers"| F["Private IntegrationFlow"]
    F --> H["Handlers / Router / Filter"]
    H -->|"Reply or error"| G
    G -->|"Typed result / exception"| C
~~~

Example interface:

~~~java
QuoteReply quote(
        QuoteRequest request,
        String trustedTenant);
~~~

A consumer may need to know:

- A method named `quote` accepts `QuoteRequest` and tenant context.
- If valid, it returns `QuoteReply` with `decision=ACCEPTED` and amount/currency.
- If business rules reject it, it returns `decision=REJECTED` with a stable reason code.
- If the caller/tenant is unauthorized, it must fail closed according to authorization policy.
- If no reply arrives or a dependency breaks, it **must not** return a fabricated quote that looks successful.
- The `requestId` in the reply must correlate to the submitted request.
- Calling the method does not charge payment, create an order, or ship goods.

The consumer **should not need to know**:

- Whether the Gateway uses a `DirectChannel` or an `ExecutorChannel`.
- Which handlers were invoked or how many times.
- What temporary `replyChannel` class the proxy creates.
- What UUID value `MessageHeaders.ID` holds.
- How many Transformers/Filters/Routers exist.
- The name of a refactored internal bean.
- Broker offsets/partitions of an alternate implementation (unless promoted into a separate transport-facing contract).

### 2.1. An API Has Layered Contracts

| Layer | What consumers rely on | Example |
|---|---|---|
| **Public/API contract** | Types, reply semantics, error taxonomy, latency/SLA, idempotency expectations | `QuoteGateway.quote(...)` |
| **Implementation contract** | Channel names, bean IDs, handler wiring, advice, deserializers | `quote.requests`, `.handle(...)` |
| **Transport contract** | Serialization, topics, reply-to/correlation, ACK/NACK, mapped headers | HTTP/JMS/Kafka adapter |

In code, a public gateway may not expose an HTTP API itself; it is a **Java interface** inside the same JVM. If a gateway sits behind an HTTP controller, HTTP status codes, headers, and JSON responses belong to the controller/adapter's **separate contract** and must be tested separately.

### 2.2. An API Contract Is More Than a Java Signature

A method:

~~~java
QuoteReply quote(QuoteRequest request);
~~~

can still break its contract without changing its signature if:

- Previously it returned `REJECTED` for unsupported SKUs, and now returns `null`.
- Previously it used minor units, and now returns major units.
- Previously it echoed `requestId`, and now generates a different UUID.
- Previously it rejected mismatched tenants, and now permits them.
- Previously it returned a deterministic outcome, and now silently drops requests.
- Previously `ACCEPTED` meant "quote calculated", and now is overloaded to mean "paid".

Contract tests must check **semantics**, not only compiler types.

## 3. Choosing the Right Test Level for the Goal

| Test | Target invoked | What bugs it catches | What it does NOT prove |
|---|---|---|---|
| **Domain handler unit test** | `QuoteService.calculate(...)` | Validation/pricing/business decisions | Gateway proxy/headers/replyChannel |
| **Consumer test with fake gateway** | Caller using fake `QuoteGateway` | Caller handles replies/errors properly | Spring Integration wiring |
| **Gateway integration test** | Spring-injected `@MessagingGateway` interface | Proxy registration, request mapping, typed replies, handler errors | Broker/HTTP serialization or ACKs |
| **Flow integration test** | Message sent to a specific channel | Router/Filter/Transformer/channel topology | Public method contract if Gateway is bypassed |
| **Adapter contract test** | HTTP/broker boundary | JSON/schema/reply-to/header mapping, ACL | Full business workflow if handlers are mocked |
| **End-to-end test** | Real caller/broker/service | Boundary coordination and selected failure modes | Every distributed failure mode |

### 3.1. The First Rule

**To test a Gateway's contract, call the Gateway.**

~~~java
// Hits the actual gateway contract:
QuoteReply result = quoteGateway.quote(request, tenant);
~~~

~~~java
// Necessary when testing internal flow, but does NOT test the proxy:
quoteRequests.send(
        MessageBuilder.withPayload(request).build());
~~~

A test calling a channel directly can pass even when:

- No `QuoteGateway` bean exists in the ApplicationContext.
- The method routes to the wrong `requestChannel`.
- `@Header` is unmapped.
- The return type fails conversion.
- The default timeout changed.
- The public API was deleted or renamed.

### 3.2. Refactor-Resistant Tests

If a contract test asserts "bean X called bean Y exactly once", refactoring one Handler into two Handlers breaks the test **even though the API remains intact**. Contract tests should prefer **observable outcomes**. Internals such as advice invocation counts, wiring graphs, and bean IDs can have dedicated tests when those internals themselves must be guarded.

## 4. Designing a Sample Quote Contract

To keep focus on gateway testing, we build a **pure quotation flow** with no database writes or payments.

### 4.1. Request DTO

~~~java
public record QuoteRequest(
        String requestId,
        String tenantId,
        String sku,
        int quantity
) {}
~~~

### 4.2. Public Decision Type

~~~java
public enum QuoteDecision {
    ACCEPTED,
    REJECTED
}
~~~

### 4.3. Reply DTO with Two Outcomes

~~~java
public record QuoteReply(
        String requestId,
        QuoteDecision decision,
        Long totalMinorUnits,
        String currency,
        String reasonCode
) {
    public static QuoteReply accepted(
            String requestId,
            long amount,
            String currency) {

        return new QuoteReply(
                requestId,
                QuoteDecision.ACCEPTED,
                amount,
                currency,
                null);
    }

    public static QuoteReply rejected(
            String requestId,
            String reasonCode) {

        return new QuoteReply(
                requestId,
                QuoteDecision.REJECTED,
                null,
                null,
                reasonCode);
    }
}
~~~

Sample contract:

| Condition | Public outcome |
|---|---|
| Request with SKU `BOOK`, valid quantity | `ACCEPTED` + VND amount in minor units |
| Valid SKU `PEN` | `ACCEPTED` + VND amount |
| Quantity `<= 0` | `REJECTED` + `INVALID_QUANTITY` |
| Unsupported SKU | `REJECTED` + `SKU_UNSUPPORTED` |
| Missing request ID | Exception `QuoteContractException("REQUEST_ID_REQUIRED")` |
| Request tenant differs from authenticated context | Exception `QuoteContractException("TENANT_MISMATCH")` |
| Reply lost | Gateway timeout/no-reply error per adapter policy; **never treated as success** |
| Infrastructure failure | Separate error with retry policy; **never faked as business `REJECTED`** |

`QuoteReply` with factory methods clarifies semantics, yet the record's public constructor still permits creating inconsistent replies; in real code, add compact constructor validation or factory-only construction to forbid `ACCEPTED` without an amount and `REJECTED` without a reason.

### 4.4. Why Boxed `Long`?

When `REJECTED`, there is no quoted amount. Nullable `Long` distinguishes **no quotation** from a **zero-dong quotation**. Avoid using `0` as an arbitrary sentinel since it can conflict with domain values.

### 4.5. Do Not Confuse ACCEPTED with Order Creation

The `quote(...)` method only produces a **quotation**. An `ACCEPTED` reply means **a valid quote was calculated**, NOT:

- Payment succeeded.
- An order was committed.
- Inventory was reserved.
- A broker ACKed anything.
- An external side effect finished.

Contract tests must verify the operation's true guarantees without inventing extra transactional claims.

## 5. Public Failures: Business Rejection or Exception?

A Gateway can return a **typed business reply** or throw an **exception**. Each carries different meaning.

| Category | Example | In this lesson |
|---|---|---|
| Expected business outcome | Invalid quantity; unsupported SKU | `QuoteReply.REJECTED` |
| Contract violation preventing safe execution | Missing request ID | `QuoteContractException` |
| Security/tenant scope conflict | Tenant context disagrees with request | `QuoteContractException` in demo; security layer in production |
| Transient infrastructure failure | Database/remote timeout | Separate exception / retry policy |
| No-reply timeout | Handler never responds | Timeout/no-reply outcome, never treated as quote |
| Programming defect | NullPointerException inside Handler | Fail/alert, never fabricate a quote |

### 5.1. Typed Exception for Contract Violations

~~~java
public final class QuoteContractException
        extends RuntimeException {

    private final String reasonCode;

    public QuoteContractException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
~~~

In Spring Integration, exceptions may be wrapped in `MessagingException` depending on the endpoint/channel, or unwrapped by the Gateway proxy. Contract tests can **walk the cause chain** to locate typed reason codes without over-coupling to framework wrappers.

If the public API strictly promises **to throw one exact exception class with no wrapper**, add a boundary adapter to normalize errors before exposing the interface, and assert the exact class on that adapter per contract.

### 5.2. Why Not Just Return `null`?

`null` cannot distinguish among:

- Business rejection with a reason code.
- Message dropped by a Filter.
- Handler failure.
- Gateway reply timeout.
- Unconvertible reply.
- Missing subscribers.

A clean public contract does not use `null` as an overloaded error channel unless explicitly documented and handled by every caller.

## 6. Domain Service Enforcing the Policy

~~~java
public final class QuoteService {

    public QuoteReply calculate(
            QuoteRequest request,
            String authenticatedTenant) {

        if (request == null) {
            throw new QuoteContractException(
                    "REQUEST_REQUIRED");
        }

        if (blank(request.requestId())) {
            throw new QuoteContractException(
                    "REQUEST_ID_REQUIRED");
        }

        if (blank(request.tenantId())) {
            throw new QuoteContractException(
                    "TENANT_ID_REQUIRED");
        }

        if (blank(authenticatedTenant)
                || !request.tenantId().equals(
                        authenticatedTenant)) {
            throw new QuoteContractException(
                    "TENANT_MISMATCH");
        }

        if (request.quantity() <= 0) {
            return QuoteReply.rejected(
                    request.requestId(),
                    "INVALID_QUANTITY");
        }

        if (blank(request.sku())) {
            return QuoteReply.rejected(
                    request.requestId(),
                    "SKU_REQUIRED");
        }

        long unitPrice = switch (request.sku()) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 15_000L;
            default -> -1L;
        };

        if (unitPrice < 0) {
            return QuoteReply.rejected(
                    request.requestId(),
                    "SKU_UNSUPPORTED");
        }

        final long total;
        try {
            total = Math.multiplyExact(
                    unitPrice,
                    request.quantity());
        }
        catch (ArithmeticException exception) {
            throw new QuoteContractException(
                    "TOTAL_OVERFLOW");
        }

        return QuoteReply.accepted(
                request.requestId(),
                total,
                "VND");
    }

    private static boolean blank(String text) {
        return text == null || text.isBlank();
    }
}
~~~

**Security note:** In this example, `authenticatedTenant` is passed as a Java parameter to test header mapping. That is **not** real authentication. Production code must derive the tenant from a verified principal/claims at HTTP/broker ingress and pass trusted context across the interface—never trust a client-supplied string.

### 6.1. Why Does the Service Not Accept `Message<?>`?

`QuoteService` takes DTOs and context and returns a DTO. As a result:

- Unit tests run without Spring.
- Business logic does not depend on `MessageChannel`.
- It is reusable from an HTTP Controller, Gateway, or another adapter.
- Gateway integration tests stay focused on wiring/contracts rather than re-testing private logic.

## 7. Public Gateway Interface

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway(
        name = "quoteContractGateway",
        defaultRequestChannel = "contract.quote.requests",
        defaultRequestTimeout = "2000",
        defaultReplyTimeout = "2000")
public interface QuoteContractGateway {

    @Gateway
    QuoteReply quote(
            QuoteRequest request,
            @Header("authenticatedTenant") String trustedTenant);
}
~~~

What is **public**:

- Method `quote(...)` called by application code.
- Request/reply DTOs published by the module.
- Requirement that `trustedTenant` comes from an authenticated context.
- Request–reply semantics rather than fire-and-forget.

What is **implementation configuration**:

- Channel `contract.quote.requests`.
- Timeout values (which can become part of the SLA contract if published).
- Proxy bean mechanics.
- Backing service activators/filters/routers.

### 7.1. Why Not Implement the Interface Manually?

Spring Integration generates the proxy using `GatewayProxyFactoryBean` and annotation infrastructure, turning calls into messages and awaiting replies. Application code does not write manual `send()`/`receive()`. To register annotated gateway interfaces, configure `@IntegrationComponentScan` or the equivalent mechanism supported by your framework version.

### 7.2. Do Not Merely Check That the Interface Exists on the Classpath

Having an interface on the classpath **does not prove** the ApplicationContext contains the gateway bean. Tests must autowire the interface from Spring and **invoke the method successfully**.

## 8. Java DSL and ApplicationContext for Contract Tests

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
        basePackageClasses = QuoteContractGateway.class)
public class QuoteContractFlowConfiguration {

    @Bean(name = "contract.quote.requests")
    public MessageChannel requests() {
        return new DirectChannel();
    }

    @Bean
    public QuoteService quoteService() {
        return new QuoteService();
    }

    @Bean
    public IntegrationFlow quoteFlow(
            QuoteService service) {

        return IntegrationFlow.from("contract.quote.requests")
                .handle(
                        QuoteRequest.class,
                        (request, headers) -> service.calculate(
                                request,
                                (String) headers.get(
                                        "authenticatedTenant")))
                .get();
    }
}
~~~

The flow uses a synchronous `DirectChannel` to verify the contract inside a minimal Spring context:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as QuoteContractGateway
    participant D as DirectChannel
    participant S as QuoteService

    C->>G: quote(request, trustedTenant)
    G->>D: Message(payload, authenticatedTenant, replyChannel)
    D->>S: calculate(request, header)
    S-->>D: QuoteReply ACCEPTED/REJECTED
    D-->>G: Reply to temporary replyChannel
    G-->>C: QuoteReply
~~~

### 8.1. Why Not Declare an Explicit Reply Channel?

With request–reply Gateways, the framework normally manages a **temporary reply channel** via the `replyChannel` header. Once the handler returns `QuoteReply` and the reply routes back properly, the gateway method returns the typed result. A named `QueueChannel` is unnecessary in this sample flow.

### 8.2. What If `DirectChannel` Is Replaced by `ExecutorChannel`?

The public method may still look like `QuoteReply quote(...)`, yet error propagation, threading, ordering, timeouts, and late replies **change**. Therefore, re-run the same contract tests and add fault/timeout tests; never swap thread boundaries and assume all semantics stayed intact.

### 8.3. This Sample Code Excludes Network and Database Concerns

There is no Kafka/JMS/AMQP, HTTP adapter, persistence, transaction, or ACK here. **This is an in-JVM contract integration test**, not a production end-to-end test. Broker and external-system behaviors must be tested against their real adapters.

## 9. Contract Testing from the Consumer's Perspective

A consumer may wrap the interface in an application service:

~~~java
public final class CheckoutQuoteClient {

    private final QuoteContractGateway gateway;

    public CheckoutQuoteClient(
            QuoteContractGateway gateway) {
        this.gateway = gateway;
    }

    public QuoteReply getQuote(
            QuoteRequest request,
            String authenticatedTenant) {

        return gateway.quote(request, authenticatedTenant);
    }
}
~~~

This code has no knowledge of `Message<?>`, channel names, or `replyChannel`. Proper API tests must therefore prove:

1. The Gateway bean can be injected.
2. The method exists with the published typed signature.
3. Header mapping delivers the expected context to the handler.
4. Happy paths return typed replies with all required fields populated.
5. Business rejections return a **reply rather than an exception** per policy.
6. Contract/security validations fail in the right category.
7. Missing business replies never masquerade as accepted quotes.
8. Callers can be unit-tested with fakes without messaging infrastructure.

## 10. Unit Testing the Business Service (Without Starting Spring)

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuoteServiceTest {

    private final QuoteService service = new QuoteService();

    @Test
    void acceptedBookQuoteHasExpectedAmount() {
        QuoteRequest request = new QuoteRequest(
                "request-1001", "tenant-a", "BOOK", 2);

        QuoteReply reply =
                service.calculate(request, "tenant-a");

        assertEquals("request-1001", reply.requestId());
        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(240_000L), reply.totalMinorUnits());
        assertEquals("VND", reply.currency());
        assertNull(reply.reasonCode());
    }

    @Test
    void unknownSkuIsBusinessRejection() {
        QuoteReply reply = service.calculate(
                new QuoteRequest(
                    "request-1002", "tenant-a", "UNKNOWN", 1),
                "tenant-a");

        assertEquals(
                QuoteDecision.REJECTED, reply.decision());
        assertNull(reply.totalMinorUnits());
        assertEquals(
                "SKU_UNSUPPORTED", reply.reasonCode());
    }

    @Test
    void invalidQuantityHasStableReasonCode() {
        QuoteReply reply = service.calculate(
                new QuoteRequest(
                    "request-1003", "tenant-a", "BOOK", 0),
                "tenant-a");

        assertEquals(
                QuoteDecision.REJECTED, reply.decision());
        assertEquals(
                "INVALID_QUANTITY", reply.reasonCode());
    }

    @Test
    void tenantMismatchIsNotAnAcceptedQuote() {
        QuoteContractException exception =
                assertThrows(
                        QuoteContractException.class,
                        () -> service.calculate(
                            new QuoteRequest(
                                "request-1004",
                                "tenant-b", "BOOK", 1),
                            "tenant-a"));

        assertEquals(
                "TENANT_MISMATCH",
                exception.reasonCode());
    }
}
~~~

These unit tests verify domain logic. They **would still pass** if `@MessagingGateway` pointed to the wrong channel; you must complement them with integration tests invoking the real Gateway bean.
## 11. Integration Testing: Calling the Real Gateway Proxy

This is the centerpiece. We use `@SpringJUnitConfig` to start a Spring context from `QuoteContractFlowConfiguration`, autowire **the interface itself**, and invoke it as a consumer.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(
        classes = QuoteContractFlowConfiguration.class)
class QuoteContractGatewayIntegrationTest {

    @Autowired
    QuoteContractGateway gateway;

    @Test
    void gatewayBeanExistsAndReturnsTypedQuote() {
        assertNotNull(gateway);

        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2001", "tenant-a", "BOOK", 2),
                "tenant-a");

        assertNotNull(reply);
        assertEquals("request-2001", reply.requestId());
        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(240_000L),
                reply.totalMinorUnits());
        assertEquals("VND", reply.currency());
        assertNull(reply.reasonCode());
    }

    @Test
    void penQuoteReturnsExpectedAmount() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2002", "tenant-a", "PEN", 3),
                "tenant-a");

        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(45_000L),
                reply.totalMinorUnits());
    }

    @Test
    void invalidQuantityReturnsBusinessRejection() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2003", "tenant-a", "BOOK", 0),
                "tenant-a");

        assertNotNull(reply);
        assertEquals(
                QuoteDecision.REJECTED, reply.decision());
        assertEquals("request-2003", reply.requestId());
        assertEquals(
                "INVALID_QUANTITY", reply.reasonCode());
        assertNull(reply.totalMinorUnits());
        assertNull(reply.currency());
    }

    @Test
    void unknownSkuDoesNotBecomeAcceptedQuote() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2004", "tenant-a", "UNKNOWN", 1),
                "tenant-a");

        assertNotNull(reply);
        assertEquals(
                QuoteDecision.REJECTED, reply.decision());
        assertEquals(
                "SKU_UNSUPPORTED", reply.reasonCode());
        assertNull(reply.totalMinorUnits());
    }

    @Test
    void tenantHeaderReachesHandler() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(
                    "request-2005", "tenant-b", "PEN", 1),
                "tenant-b");

        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(15_000L),
                reply.totalMinorUnits());
    }

    @Test
    void conflictingTenantFailsContract() {
        RuntimeException failure = assertThrows(
                RuntimeException.class,
                () -> gateway.quote(
                    new QuoteRequest(
                        "request-2006", "tenant-b", "BOOK", 1),
                    "tenant-a"));

        assertEquals(
                "TENANT_MISMATCH",
                QuoteExceptionChecks.findReasonCode(failure));
    }

    @Test
    void missingRequestIdFailsContract() {
        RuntimeException failure = assertThrows(
                RuntimeException.class,
                () -> gateway.quote(
                    new QuoteRequest(
                        "", "tenant-a", "BOOK", 1),
                    "tenant-a"));

        assertEquals(
                "REQUEST_ID_REQUIRED",
                QuoteExceptionChecks.findReasonCode(failure));
    }
}
~~~

Because Spring Integration may wrap exceptions in `MessagingException` or the Gateway proxy may unwrap them, test the **reason code in the cause chain** rather than locking onto a wrapper implementation detail.

~~~java
public final class QuoteExceptionChecks {

    private QuoteExceptionChecks() {}

    public static String findReasonCode(Throwable error) {
        Throwable current = error;

        while (current != null) {
            if (current instanceof QuoteContractException contract) {
                return contract.reasonCode();
            }
            current = current.getCause();
        }

        throw new AssertionError(
                "QuoteContractException not found", error);
    }
}
~~~

### 11.1. What These Tests Prove

- The Gateway bean is created via `@IntegrationComponentScan`.
- The `defaultRequestChannel` annotation connects to the real flow.
- The proxy maps method arguments into payload and headers.
- Handler replies return to the calling method as the matching DTO.
- Business rejections return as **typed replies**, not dropped messages.
- Contract/tenant failures are never converted into fake `ACCEPTED` replies.
- Tests need no knowledge of temporary reply channel classes or proxy classes.

### 11.2. What These Tests Do NOT Prove Yet

- HTTP/JMS/AMQP/Kafka serialization or ACKs.
- Database commits, transactions, or remote API calls.
- Multi-JVM deployment and broker-based reply correlation.
- Late replies, worker crashes, or network partitions.
- Real authentication: the test only checks passing a **trusted context string** in-JVM; ingress security must be tested separately.

### 11.3. Do Not Assert Proxy Classes or Handler Invocation Counts

A refactor can change endpoint counts, bean names, proxy classes, or insert Transformers without changing the API. The public contract only cares about observable results and errors at the interface. When you want to test a Router or Handler individually, write a separate **flow integration test** rather than stuffing implementation assertions into the contract suite.

## 12. Header Mapping: Test Through Public Behavior

Method:

~~~java
QuoteReply quote(
        QuoteRequest request,
        @Header("authenticatedTenant") String trustedTenant);
~~~

has two effective inputs: `request` becomes the **message payload**, and `trustedTenant` becomes a **message header**. If `@Header("authenticatedTenant")` is mistakenly renamed to `@Header("tenant")` while the handler still reads `authenticatedTenant`, `QuoteService` unit tests will miss it, whereas the `tenant-b` gateway integration test in Section 11 catches the mismatch immediately.

### 12.1. Do Not Inspect Internal `MessageHeaders` Just to Test the API

If a header name is not part of the public Java contract, assert the output produced when the handler uses that value. You do not need to inject `contract.quote.requests` and attach a spy to inspect raw messages. Raw-header assertions belong in separate tests when **cross-transport header mapping** itself is part of the contract.

### 12.2. Trusted Tenant Must Be Established at Ingress

In the demo, the caller passes `"tenant-a"`. A production HTTP Controller or broker adapter must derive tenant context from verified principals/JWTs/mTLS/broker ACLs, not trust payload `tenantId`. Security tests should intentionally submit payload `tenant-b` under authenticated `tenant-a` and assert **zero business side effects**.

## 13. Fake Gateways: Consumer-Side Tests

A Java interface is also valuable because callers can be tested with fakes **without booting a Spring context**.

~~~java
public final class CheckoutQuoteClient {

    private final QuoteContractGateway gateway;

    public CheckoutQuoteClient(QuoteContractGateway gateway) {
        this.gateway = gateway;
    }

    public String decide(
            QuoteRequest request,
            String trustedTenant) {

        QuoteReply reply = gateway.quote(
                request, trustedTenant);

        if (reply == null) {
            throw new IllegalStateException(
                    "QUOTE_REPLY_REQUIRED");
        }

        return switch (reply.decision()) {
            case ACCEPTED -> "READY";
            case REJECTED ->
                    "REJECTED:" + reply.reasonCode();
        };
    }
}
~~~

Fake tests can use lambdas because the interface has a single abstract method:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class CheckoutQuoteClientTest {

    @Test
    void consumerHandlesRejectionWithoutChannel() {
        QuoteContractGateway fake = (request, tenant) ->
                QuoteReply.rejected(
                    request.requestId(),
                    "INVALID_QUANTITY");

        String result = new CheckoutQuoteClient(fake)
                .decide(
                    new QuoteRequest(
                        "request-3001", "tenant-a", "BOOK", 0),
                    "tenant-a");

        assertEquals(
                "REJECTED:INVALID_QUANTITY", result);
    }

    @Test
    void consumerHandlesAcceptedQuote() {
        QuoteContractGateway fake = (request, tenant) ->
                QuoteReply.accepted(
                    request.requestId(), 120_000L, "VND");

        String result = new CheckoutQuoteClient(fake)
                .decide(
                    new QuoteRequest(
                        "request-3002", "tenant-a", "BOOK", 1),
                    "tenant-a");

        assertEquals("READY", result);
    }

    @Test
    void nullReplyMustNotBecomeSuccess() {
        QuoteContractGateway noReply = (request, tenant) ->
                null;

        assertThrows(
                IllegalStateException.class,
                () -> new CheckoutQuoteClient(noReply).decide(
                    new QuoteRequest(
                        "request-3003", "tenant-a", "BOOK", 1),
                    "tenant-a"));
    }
}
~~~

### 13.1. Fakes Do Not Prove the Gateway Proxy Works

A fake only tests **how the consumer uses the contract**; it will miss:

- Unscanned Gateway beans.
- Wrong request channels.
- Misnamed `@Header` annotations.
- Handlers failing to reply.
- Broken return type conversion.

Maintain **both** gateway integration tests and consumer unit tests. You do not need every consumer test to boot a Spring context.

### 13.2. Do Not Let Fakes Over-Promise

A fake returning immediately does not prove deadlines, broker durability, or exactly-once delivery. Include fakes for rejection, error, and no-reply cases along caller branches, but only claim guarantees actually promised by the public API.

## 14. Contract Tests Enable Safe Flow Refactoring

Initially:

~~~text
Implementation V1:
  Gateway -> DirectChannel -> QuoteService
~~~

After refactoring:

~~~text
Implementation V2:
  Gateway -> Transformer -> Router -> Book/Pen handlers
~~~

Or:

~~~text
Implementation V3:
  Gateway -> ExecutorChannel -> Aggregator
~~~

As long as the API contract holds, **the exact same test suite** should pass across implementations. Bean names or handler counts can change while output semantics stay intact.

| Public input | Expected public output | Regression caught by contract tests |
|---|---|---|
| BOOK x2 | ACCEPTED 240000 VND | Wrong route/pricing |
| PEN x3 | ACCEPTED 45000 VND | Header/handler bug |
| Quantity=0 | REJECTED INVALID_QUANTITY | Filter drop |
| Unknown SKU | REJECTED SKU_UNSUPPORTED | Unhandled router branch |
| Missing requestId | Typed contract error | Bypassed validator |
| Tenant mismatch | Denied/contract error | Broken header mapping |
| Two concurrent requests | Replies match their requests | Broken correlation |
| Handler produces no reply | Timeout/error outcome | Silent success |
| Downstream failure | Propagated/mapped error | Log-only error flow |

A test doing `assertThat(handler).wasCalledOnce()` binds to implementation details and breaks valid refactors. Interface tests should assert **observable behavior**.

### 14.1. Test Semantics, Not Just Java Types

Keeping the `QuoteReply` type while changing the meaning of `ACCEPTED` or amount units still breaks the contract. If amounts are published in **VND minor units**, returning `240` instead of `240000` violates the contract even though the Java type is still `Long`.

### 14.2. Public Java API Versions and Wire Format Versions Differ

Changing record constructors or return types can cause source/binary compatibility breaks for Java callers. When a Gateway sits behind an HTTP/Kafka adapter, JSON/schema changes form a **separate transport contract**. Java Gateway tests alone do not guarantee off-JVM consumers can still deserialize responses.

## 15. Null / No-Reply: Explicit Policies and Tests

A method returning `QuoteReply` must never let callers mistake `null` for success. Common causes of missing replies:

- Filter predicate evaluates false and drops the message.
- Router fails to resolve a route.
- Service Activator returns null.
- Aggregator never releases the group.
- `replyChannel` header dropped when a Transformer manually builds a new `Message`.
- Async worker does not finish before timeout.
- Error flow only logs without generating a public reply.

### 15.1. Boundary Adapter Enforcing Non-Null

~~~java
public final class StrictQuotePort {

    private final QuoteContractGateway gateway;

    public StrictQuotePort(QuoteContractGateway gateway) {
        this.gateway = gateway;
    }

    public QuoteReply quote(
            QuoteRequest request,
            String tenant) {

        QuoteReply reply = gateway.quote(request, tenant);
        if (reply == null) {
            throw new IllegalStateException(
                    "QUOTE_REPLY_MISSING");
        }
        return reply;
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class StrictQuotePortTest {

    @Test
    void noReplyIsNeverAcceptedSilently() {
        QuoteContractGateway fake =
                (request, tenant) -> null;

        StrictQuotePort port = new StrictQuotePort(fake);

        IllegalStateException failure =
                assertThrows(
                    IllegalStateException.class,
                    () -> port.quote(
                        new QuoteRequest(
                            "request-3101",
                            "tenant-a", "BOOK", 1),
                        "tenant-a"));

        assertEquals(
                "QUOTE_REPLY_MISSING", failure.getMessage());
    }
}
~~~

This is a **unit test of the adapter's null policy**, not a test of Spring Gateway receive timeouts. Depending on Spring Integration version and configuration, a Gateway may throw a timeout exception or return null; normalize at the boundary if consumers depend on a single failure convention.

### 15.2. Do Not Write Misleading Timeout Tests Against `DirectChannel`

With `DirectChannel`, the handler runs synchronously on the caller thread. `replyTimeout` does not forcibly interrupt a handler blocking inside `send()`. To test real timeouts, use a controlled async boundary and set explicit deadlines on remote I/O as well.
## 16. Testing Timeouts at the Right Stage

A Messaging Gateway involves multiple timeouts; each test must identify which stage it measures.

| Limit | Scope | How to test |
|---|---|---|
| `requestTimeout` | Waiting to send a request when channel send can block | Bounded/full `QueueChannel`, send behavior |
| `replyTimeout` | Waiting for a reply in request–reply | Executor/poller with delayed worker |
| HTTP connect/read timeout | Outbound HTTP client | Mock server delaying connection/response |
| Broker publish timeout | Producer/adapter | Broker/publisher fault injection |
| Business deadline | Entire application operation | Boundary policy/monitoring |
| DB transaction timeout | Transaction manager | Real transactional integration test |

### 16.1. `DirectChannel` Can Exceed `replyTimeout`

In the main flow example, `DirectChannel` executes the handler synchronously on the caller thread. If a handler blocks for 5 seconds inside `send()`, the Gateway may not even reach the reply-wait stage yet. Setting `replyTimeout=100ms` **does not guarantee the method finishes within 100ms**.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant D as DirectChannel
    participant H as Blocking handler

    C->>G: quote(request)
    G->>D: send(message)
    D->>H: invoke handler
    Note over H: Blocking remote call
    H-->>D: returns after slow processing
    D-->>G: reply through handler
    G-->>C: result
~~~

Therefore, when an operation performs remote I/O, **configure timeouts on the HTTP/DB client** or use appropriate async boundaries and deadlines; do not write tests under false assumptions about `replyTimeout`.

### 16.2. Async Boundaries Can Produce Late Replies

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant E as ExecutorChannel
    participant W as Worker

    C->>G: request
    G->>E: send
    E-->>G: dispatch accepted
    G->>G: await reply
    E->>W: process
    Note over G: replyTimeout reached
    G-->>C: null/error per policy
    W-->>G: late reply
~~~

Tests should prove:

- Not receiving a reply before the deadline **never** yields `ACCEPTED`.
- Late replies are never misdelivered to another invocation.
- Workers may still commit business side effects even after caller timeout.
- Retries reuse the same command ID or reconcile when operations have side effects.

### 16.3. Use Latches Instead of Sleeps in Tests

In an async flow test, have the worker wait on a test-controlled `CountDownLatch`. Call the gateway from a bounded test executor, assert the pending/timeout state, then release the latch. Wrap test waits with `Future.get(timeout, TimeUnit.SECONDS)` so the test suite never hangs indefinitely; production Gateway timeouts are configured separately.

Avoid peppering tests with exact 10ms `Thread.sleep` calls to assert concurrency; CI scheduling differs from local laptops.

### 16.4. Official APIs Can Standardize Timeouts

If consumers require non-null guarantees and a fixed exception contract, wrap the Gateway in an adapter mapping `null` or timeout exceptions into an application `QuoteUnavailableException`. Some Spring Integration versions offer timeout-exception flags, though defaults should not be assumed identical across versions. **Contract tests on the public adapter** should assert the published error category.

## 17. Testing Exceptions and Error Channels

Failures can originate in different places:

~~~text
Gateway -> DirectChannel -> handler throws
  -> Exception may propagate to Gateway caller.

Gateway -> ExecutorChannel -> handler throws on worker
  -> Error handler / ErrorMessage path if configured.

Gateway -> Broker request -> remote worker throws
  -> Need explicit error reply, retry/dead-letter protocol.
~~~

### 17.1. `ErrorMessage` Is Not a `QuoteReply`

`errorChannel` typically receives an `ErrorMessage` wrapping a `Throwable`. If an error flow merely logs and stops, a public Gateway method may **receive no reply**. Declaring return type `QuoteReply` does not automatically turn every `Throwable` into `QuoteReply.rejected(...)`.

### 17.2. Public Error Taxonomy

| Failure | Public outcome | Retry policy |
|---|---|---|
| Quantity=0 | `REJECTED/INVALID_QUANTITY` | No |
| SKU unsupported | `REJECTED/SKU_UNSUPPORTED` | No |
| Missing request ID | Contract exception | Fix request |
| Tenant mismatch | Contract/security denial | Do not auto-retry |
| DB deadlock | Transient error | Bounded retry |
| Remote HTTP 503 | Dependency error | Bounded retry/backoff |
| Unexpected handler exception | Internal error | Alert/fix |
| No reply | Timeout/no-reply | Investigate outcome |
| Wrong broker reply correlation | Protocol error | Quarantine/alert |
| Duplicate command | Cached reply/no-op per contract | Idempotent |

### 17.3. Do Not Assert Every Exception Shares the Same Wrapper

In the integration test, `QuoteExceptionChecks.findReasonCode` deliberately searches for the **typed cause**. If the public API strictly promises one exact exception class, introduce a **boundary exception adapter** and assert the exact class on that adapter rather than relying on endpoint wrappers.

### 17.4. Error Flows Must Produce an Outcome

If Handler A throws while a Gateway waits, an error flow can:

- Propagate the exception to the caller (sync).
- Build a typed error reply with proper correlation.
- Write to a DLQ/quarantine and return a tracking receipt.
- Time out and reconcile under an explicit async contract.

Whichever approach you choose must be **documented and tested**. "The error was logged" is not a public outcome for a non-void method.

## 18. Preserving the Contract When Refactoring Routers, Filters, and Aggregators

Splitting one handler into multiple branches must not break callers:

~~~mermaid
flowchart TD
    G["QuoteContractGateway.quote()"] --> V["Validation"]
    V --> R{"Router SKU"}
    R -->|"BOOK"| B["Book quote handler"]
    R -->|"PEN"| P["Pen quote handler"]
    R -->|"Other"| X["REJECTED reply"]
    B --> Y["QuoteReply ACCEPTED"]
    P --> Y
    X --> G
    Y --> G
~~~

### 18.1. Filters Can Silently Break Contracts

~~~java
.filter(
        QuoteRequest.class,
        request -> request.quantity() > 0)
~~~

When the predicate is false and the Filter lacks a proper rejection policy, the message may be dropped: callers never receive `REJECTED/INVALID_QUANTITY`. Contract test `invalidQuantityReturnsBusinessRejection` catches this regression.

### 18.2. Unresolved Router Destinations

A Router might route `BOOK`/`PEN` properly yet have no fallback for unknown SKUs. If it discards or fails to emit a reply, `unknownSkuDoesNotBecomeAcceptedQuote` will fail to see the contracted typed `REJECTED` outcome.

### 18.3. Non-Releasing Aggregators

If a Splitter fans out a request to three providers and the Aggregator waits for three replies, one missing/timed-out provider can stall replies past the deadline. The public API must define **partial quote, error, timeout, or async result behavior** instead of leaving behavior to timing luck.

### 18.4. Transformers Dropping `replyChannel`

A Transformer building a brand-new `Message<?>` can strip `replyChannel`/`errorChannel` metadata if headers are not preserved properly. Business handlers may run while replies fail to reach the Gateway. Contract integration tests catch such no-reply regressions without asserting internal header names directly.

## 19. Testing Correlation Under Concurrent Invocations

Two Gateway calls can run concurrently and return replies **out of order**:

~~~text
Request A:
  requestId = req-A, SKU=BOOK

Request B:
  requestId = req-B, SKU=PEN

Replies arrive:
  B before A
~~~

Contract:

\[
\forall r:\quad reply.requestId = request.requestId
\]

and the returned amount/decision must match **that exact request**.

### 19.1. Concurrency Test Against the Public Gateway Interface

The example below runs inside a Spring context using a **test** bounded executor. It verifies two caller threads receive their matching replies; because the sample flow is synchronous, it does not yet simulate out-of-order broker replies.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(
        classes = QuoteContractFlowConfiguration.class)
class ParallelQuoteGatewayContractTest {

    @Autowired
    QuoteContractGateway gateway;

    @Test
    void simultaneousCallsKeepTheirReplies() throws Exception {
        ExecutorService executor =
                Executors.newFixedThreadPool(2);

        try {
            Future<QuoteReply> a = executor.submit(() ->
                    gateway.quote(
                        new QuoteRequest(
                            "req-A", "tenant-a", "BOOK", 1),
                        "tenant-a"));

            Future<QuoteReply> b = executor.submit(() ->
                    gateway.quote(
                        new QuoteRequest(
                            "req-B", "tenant-a", "PEN", 1),
                        "tenant-a"));

            QuoteReply replyA =
                    a.get(5, TimeUnit.SECONDS);
            QuoteReply replyB =
                    b.get(5, TimeUnit.SECONDS);

            assertEquals("req-A", replyA.requestId());
            assertEquals(
                    Long.valueOf(120_000L),
                    replyA.totalMinorUnits());

            assertEquals("req-B", replyB.requestId());
            assertEquals(
                    Long.valueOf(15_000L),
                    replyB.totalMinorUnits());
        }
        finally {
            executor.shutdownNow();
        }
    }
}
~~~

### 19.2. What This Test Does NOT Prove Yet

- Reply B was actually published before A.
- Broker request/reply correlation works across two JVMs.
- Late reply A is never confused with request C.
- Rebalanced consumers preserve durability.
- Calling the same `requestId` twice follows the idempotency policy.

Those guarantees must be tested with a real adapter/broker or a controllable fake broker that reorders replies.

### 19.3. In-JVM Correlation Differs from Remote Correlation

A Gateway proxy typically uses a private temporary reply channel for in-JVM request–reply. Over a broker, reply destinations and correlation metadata must be mapped cleanly by adapters. Never serialize an in-JVM `replyChannel` object onto Kafka/HTTP expecting the remote peer to call that object back.

A business `requestId` aids auditing/idempotency, yet it may not be **unique per in-flight RPC** if callers legitimately retry the same request ID; adapters may need an independent correlation token.

## 20. Idempotency: Public Contract and Layer-Appropriate Tests

A Messaging Gateway does not guarantee exactly-once execution. A brokered command can be redelivered after a worker commits but before an ACK completes.

~~~text
Caller submit(commandId=C-1001)
  -> Worker applies action
  -> Reply/ACK lost
  -> Caller retries C-1001
  -> Same command delivered again
~~~

When a Gateway public API is a **side-effecting command**, the contract can require:

- A stable `commandId`.
- Same `commandId` + same payload → returns the cached result/receipt without re-applying the side effect.
- Same `commandId` + different payload → conflict.
- Error/timeout does not prove the command failed to commit.
- Dedup records persist long enough to cover the retry/replay window.
- Remote idempotency keys or reconciliation when side effects leave the local DB.

### 20.1. Do Not Assert That a Transport Handler Runs Only Once

At-least-once delivery can legitimately invoke a Handler twice. Tests should assert that the **business mutation is applied once**, rather than asserting handler invocation count = 1 across every topology.

### 20.2. Illustrative Idempotent Command Matrix

| Invocation | Payload | Public outcome | Business store |
|---|---|---|---|
| C-1001 attempt 1 | X | ACCEPTED, receipt R | One mutation |
| C-1001 attempt 2 | X | Same effective receipt R | Still one mutation |
| C-1001 attempt 3 | Y | IDEMPOTENCY_CONFLICT | No new mutation |
| C-1002 | X | New request per domain contract | Depends on unique business keys |

This is a **contract test for a separate command gateway**, not inferred from pure `QuoteService`. Proving it requires persistent stores, transactions, and side-effect integration tests.

## 21. Async Public Gateway Contract

A Gateway can return `CompletableFuture<QuoteReply>` or `Future<QuoteReply>` rather than blocking the calling thread until reply arrival:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway(
        name = "asyncQuoteGateway",
        asyncExecutor = "quoteAsyncExecutor")
public interface AsyncQuoteGateway {

    @Gateway(requestChannel = "contract.quote.requests")
    CompletableFuture<QuoteReply> quoteAsync(
            QuoteRequest request,
            @Header("authenticatedTenant") String tenant);
}
~~~

Running this requires an `Executor` bean named `quoteAsyncExecutor` and gateway registration in a controlled ApplicationContext, for instance:

~~~java
import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean(name = "quoteAsyncExecutor")
public Executor quoteAsyncExecutor() {
    ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(2);
    pool.setMaxPoolSize(4);
    pool.setQueueCapacity(50);
    pool.setThreadNamePrefix("gateway-contract-");
    pool.initialize();
    return pool;
}
~~~

Place that `@Bean` method inside a `@Configuration` class; this does not mean every `@MessagingGateway` in a package requires its own dedicated executor.

### 21.1. Async Contracts Must Spell Out Completion Semantics

- The future completes normally with a **typed `QuoteReply`**.
- Valid rejections still return `QuoteReply.REJECTED` per contract.
- Validation/handler errors complete the future exceptionally.
- Caller timeouts do not automatically cancel downstream business work.
- Cancelling a future does not guarantee a remote worker was interrupted.
- Context propagation/tracing may require explicit instrumentation.

### 21.2. Integration Test for an Async Method

Core test snippet for an ApplicationContext registering `AsyncQuoteGateway`, `quoteAsyncExecutor`, and the `contract.quote.requests` flow:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class AsyncQuoteGatewayContractTest {

    @Autowired
    AsyncQuoteGateway gateway;

    @Test
    void futureCompletesWithTypedResult() throws Exception {
        QuoteReply reply = gateway.quoteAsync(
                new QuoteRequest(
                    "async-1001", "tenant-a", "PEN", 2),
                "tenant-a")
                .get(5, TimeUnit.SECONDS);

        assertNotNull(reply);
        assertEquals(
                QuoteDecision.ACCEPTED, reply.decision());
        assertEquals(
                Long.valueOf(30_000L),
                reply.totalMinorUnits());
    }
}
~~~

**This is an illustrative test method**, not a standalone runnable test class: wire `@SpringJUnitConfig(classes=...)` pointing to configuration with gateway scanning, executor, and flow beans. The bounded `get(timeout, unit)` guard belongs **to the test**; it does not replace production `replyTimeout` or remote deadline policies.

### 21.3. Do Not Call `join()` on a Request Thread and Claim Non-Blocking Behavior

If the caller immediately calls `future.join()` and waits for completion, the application still blocks. Async public contracts should be consumed through composition/callbacks with error handling and bounded executor capacity.

## 22. One-Way Gateways and `void` Contracts

A Gateway method:

~~~java
@Gateway(requestChannel = "audit.events")
void record(AuditEvent event);
~~~

has no Java return value. Yet `void` **does not mean**:

- The broker persisted the message.
- A database transaction committed.
- The audit handler will execute exactly once.
- No exception can occur.
- The caller thread always returns immediately.

With `DirectChannel`, handlers run synchronously and can throw on the caller thread; with async channels, the method may return after dispatch while workers keep running. If the API needs durable acceptance, expose a **receipt/tracking ID** instead of pretending `void` guarantees success.

### 22.1. How to Test a `void` Gateway

Contract tests for a `void` operation must explicitly state which guarantee is promised:

- **Dispatch attempt only**: test that calling against an available channel does not throw, plus separate adapter failure tests.
- **Persisted acceptance**: test that the record is durably persisted before returning.
- **Business completion**: require a receipt/result or observable state; `void` usually cannot express this cleanly.
- **At-least-once**: test redelivery and downstream idempotency.

Never use a `void` return test to claim exactly-once semantics just because the method returned normally.

## 23. Adapter Contract Tests: Java API vs. Wire Protocol

If a Gateway is fronted by an HTTP Controller or backed by Kafka/JMS/AMQP, there is a **second contract** at the transport boundary.

| Property | Java Gateway test | Adapter/wire test |
|---|---|---|
| `quote(...)` method exists | Yes | Irrelevant |
| Java return type `QuoteReply` | Yes | May only verify serialized schema |
| Internal `@Header` mapping | Yes | Ingress/egress header mapper |
| JSON field names/types | No | Yes |
| Content-Type / encoding | No | Yes |
| Authentication/JWT/mTLS | Not in demo | Yes |
| Broker correlation/reply-to | Not in demo | Yes |
| Offset/ACK/DLQ | No | Yes |
| End-to-end tracing | No | Yes |
| Cross-JVM reply timeout | No | Yes |

### 23.1. Wire Contract Example

Java reply:

~~~java
new QuoteReply(
    "request-1001",
    QuoteDecision.ACCEPTED,
    240_000L,
    "VND",
    null);
~~~

An external contract might specify JSON response:

~~~json
{
  "requestId": "request-1001",
  "decision": "ACCEPTED",
  "totalMinorUnits": 240000,
  "currency": "VND",
  "reasonCode": null
}
~~~

A `Jackson ObjectMapper` configured to omit null properties might drop `reasonCode`. The public **wire** contract must state whether null fields are required. Java Gateway tests would keep passing even if serializer changes broke JSON consumers; write dedicated serialization / consumer-driven contract tests.

### 23.2. Never Test Another Transport via an In-Memory `DirectChannel`

To test Kafka reply correlation, use a Kafka test container, embedded broker, or controlled adapter setup. Attaching an in-JVM `replyChannel` header never proves multi-JVM Kafka request/reply works.
## 24. Security Contracts at the Gateway Boundary

Hiding `MessageChannel` does not mean authentication and authorization exist. A Gateway merely transports method arguments into payloads and headers; **caller context must come from a trusted source**.

### 24.1. Public Contract for Tenant Isolation

Suppose the API guarantees a tenant can only request quotes for its own requests.

~~~text
Authenticated principal: tenant-a
QuoteRequest.tenantId: tenant-b

Expected:
  Contract/security denial
  No business side effect
  No cross-tenant data in reply or logs
~~~

Testing should span two layers:

1. **Gateway integration test**: verify `@Header("authenticatedTenant")` reaches the handler and tenant mismatches are denied.
2. **Ingress security test**: confirm Spring Security / HTTP / JMS / Kafka adapters derive the tenant from a trusted principal rather than a client-controlled header or JSON field.

A test that only passes two identical `"tenant-a"` strings **does not prove** authentication works.

### 24.2. Never Leak Internals in Error Replies

Public errors should expose stable reason codes. Never return to clients:

- Full Java stack traces.
- Internal channel/bean names.
- DB credentials/tokens.
- Other tenants' message data.
- Broker topics/partitions unless part of the contract.
- Raw `MessageHeaders` or security context objects.

Gateway exceptions may embed `failedMessage` in the cause chain. When mapping to HTTP APIs or public logs, scrub/redact rather than serializing raw exception objects.

### 24.3. Headers and Trust Boundaries

Inside a JVM, `replyChannel`/`errorChannel` can be runtime channel objects. Over a broker, header mappers must use allowlists; never export Authorization tokens, internal proxy details, or sensitive fields. Tracing contexts may propagate via instrumentation, yet `traceId` never replaces business `requestId`/idempotency keys.

## 25. Consumer-Driven Contract Tests and Fixtures

When multiple modules or teams share a gateway, a **consumer-driven contract** specifies the behavior consumers actually rely on.

A sample contract specification table:

| What the consumer needs | What the provider promises | Test fixture |
|---|---|---|
| Display quoted total | ACCEPTED + VND minor units | BOOK x2 → 240000 |
| Display rejection reason | REJECTED + stable reason | Quantity 0 → INVALID_QUANTITY |
| Never show bogus price for unknown SKU | REJECTED, amount=null | SKU UNKNOWN |
| Match replies to requests | requestId preserved | request-2001 |
| Prevent cross-tenant quotes | Tenant mismatch denied | tenant-a vs tenant-b |
| Never show false success when workers fail to reply | Explicit timeout/no-reply policy | Delayed/no-reply fixture |

### 25.1. Provider Verification

The Gateway provider must run the contract suite against its own Spring ApplicationContext. If refactoring from `DirectChannel` to a `Router` turns a business error into a silent no-reply, verification fails before deployment.

### 25.2. Test Fixtures Must Express Semantics

A fixture `amount=240000` must specify **VND minor units**. Asserting bare numbers without preserving currency/unit semantics allows schema changes from minor to major units to create financial bugs.

### 25.3. Never Arbitrarily Snapshot Entire Spring Messages

Snapshotting raw headers captures volatile fields like `id`, `timestamp`, temporary reply channels, or trace IDs that legitimately vary across runs, making tests flaky. Snapshot the **public reply DTO / serialized wire contract** after normalizing dynamic fields instead.

### 25.4. Assessing Compatibility Impact

| Change | Public contract impact |
|---|---|
| Rename private channel | None if method behavior holds |
| Insert internal Transformer | None if reply semantics hold |
| Change BOOK x2 from 240000 to 250000 | Yes if price is contracted by the scenario |
| Change reasonCode `INVALID_QUANTITY` to `BAD_REQUEST` | Yes if consumers depend on the code |
| Change `QuoteReply` field types | Yes |
| Turn `REJECTED` into an exception | Yes |
| Change public reply timeout SLA | Yes if SLA is published |
| Swap underlying broker/serializer | None on Java API if adapter hides it fully; needs wire tests |
| Change authentication policy | Can affect behavior; requires security review |
| Add new nullable field | Potentially compatible depending on reader/serialization policy |

## 26. Observability Supports Contracts Without Replacing Contract Tests

Contract tests tell you whether **specific scenarios pass**; monitoring tells you whether production behavior is drifting.

| Metric | Meaning | Appropriate labels |
|---|---|---|
| `gateway_invocation_total` | Total method calls | method, outcome |
| `gateway_reply_total` | Typed replies | decision, method |
| `gateway_contract_error_total` | Input/API violations | reasonCode |
| `gateway_reply_timeout_total` | Replies missed by deadline | method, flow |
| `gateway_send_timeout_total` | Request channel send timeouts | flow |
| `gateway_late_reply_total` | Replies arriving after caller timeout | flow |
| `gateway_reply_type_mismatch_total` | Replies failing conversion/type match | flow |
| `gateway_correlation_mismatch_total` | Mis-correlated replies | flow |
| `gateway_idempotent_replay_total` | Recognized duplicate commands | operation |
| `gateway_business_duration_seconds` | Operation duration | method, decision |
| `gateway_inflight_requests` | In-flight pending requests | flow |
| `gateway_async_failure_total` | Futures completing exceptionally | errorClass |

### 26.1. Structured Logging

~~~text
flow=quote-contract
gatewayMethod=quote
requestId=request-2001
decision=ACCEPTED
currency=VND
durationMs=16
traceId=trace-example-1001
~~~

Never use `requestId`, `quoteId`, `eventId`, `tenantId`, or `traceId` as **high-cardinality metric labels**. Keep them in logs/traces with appropriate access controls, retention, and redaction/sampling. Log `reasonCode` from a bounded taxonomy rather than raw exceptions containing PII.

### 26.2. Contract-Related Alerts

- Spike in null/no-reply rates right after deploying Router/Filter changes.
- Spike in timeouts after switching from `DirectChannel` to `ExecutorChannel`.
- Business `REJECTED` counts suddenly dropping to zero despite ongoing invalid requests.
- `ErrorChannel` receiving exceptions while callers only see timeouts.
- Rising correlation mismatches as broker replies land on the wrong destination.
- Growing async in-flight requests exhausting bounded executors.
- Tenant mismatches getting `ACCEPTED` after security mapping changes.
- New consumers failing to deserialize an older reply schema.

### 26.3. Never Substitute Metrics for Failure-Semantic Tests

A dashboard cannot prove "every invalid quantity returns `INVALID_QUANTITY`" across boundary cases. Contract tests must actively exercise fixtures, while monitoring catches production distribution drift outside test datasets.

## 27. Common Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Only testing `MessageChannel.send()` | Broken gateway proxies go undetected | Invoke the interface bean in Spring tests |
| Only testing the business handler | Wrong `@Header`/`requestChannel` slips through | Write gateway integration tests |
| Only testing fake Gateways | Proxy registration goes unverified | Run real provider verification |
| Asserting proxy class names | Breaks across framework upgrades | Assert interface behavior |
| Asserting each Handler runs once | Valid refactors fail tests | Assert business outcomes |
| Only testing BOOK happy path | Broken `REJECTED`/exceptions go unseen | Build an outcome/error matrix |
| Quantity 0 becomes a Filter drop | Gateway timeout | Explicit `REJECTED` reply |
| Router lacks fallback for unknown SKUs | Missing reply | Default rejection/error route |
| Handler returning null treated as SUCCESS | Callers misbehave | Strict non-null public adapter |
| Using `replyTimeout` to abort `DirectChannel` | Handler keeps blocking | Set I/O client timeouts or async boundaries |
| Testing timeouts with exact 10ms sleeps | Flaky CI | Use latches, bounded futures, margins |
| Calling `join()` and claiming non-blocking | Caller still blocks | Compose async results |
| Returning `void` and promising commit | False success | Receipt/tracking state |
| Shared reply queue without correlation | Crossed caller replies | Correlation protocol/temporary channels |
| Using Spring Message ID as business ID | IDs change on redelivery | Stable request/command IDs |
| Retrying after timeout with a new ID | Duplicate side effects | Idempotency/reconciliation |
| Faking auth via payload headers | Cross-tenant bugs | Trusted principal/claims tests |
| Sending `replyChannel` object over Kafka | Remote JVM lacks the object | Reply destination/correlation |
| Only testing Java DTOs, never JSON | Wire contract breaks | Adapter serialization fixtures |
| Only asserting HTTP 200 on valid replies | Right status, wrong amount | Assert field semantics |
| Using `assertTrue(duration<5ms)` in CI | Flaky | Separate SLA/load tests |
| Not testing missing replies with Aggregator | Production hangs/timeouts | Partial/expiry contracts |
| Error flow only logs when API expects reply | Callers hang without outcomes | Error mapping/rethrow |
| Using `requestId` as metric label | Cardinality explosion | Bounded dimensions |
| Renaming public reason codes silently | Consumer breakage | Versioning/consumer-driven tests |
| Calling in-memory tests exactly-once | False reliability assumptions | Broker/DB side-effect tests |

## 28. Hands-On Exercises

**Exercise 1 — Public contract.** Starting from `QuoteContractGateway.quote`, specify exact accepted/rejected/exception/null semantics, amount units, and `requestId` propagation.

**Exercise 2 — Handler unit tests.** Run `QuoteServiceTest`; cover BOOK x2, PEN x3, quantity=0, unknown SKU, and tenant mismatch.

**Exercise 3 — Gateway bean.** Build `QuoteContractFlowConfiguration`. Use `@SpringJUnitConfig` and `@Autowired` to invoke the real Gateway method.

**Exercise 4 — Header regression.** Temporarily change `@Header("authenticatedTenant")` to `@Header("tenant")` without changing the handler; confirm the contract test fails, then fix it.

**Exercise 5 — Typed rejection.** Insert a `quantity > 0` Filter that emits no reply; observe the contract regression and fix it with an explicit `REJECTED` outcome.

**Exercise 6 — Router fallback.** Split handlers by SKU. Send an unknown SKU and verify `SKU_UNSUPPORTED` returns.

**Exercise 7 — No-reply.** Write `StrictQuotePortTest`: when a fake gateway returns null, the public adapter must throw `QUOTE_REPLY_MISSING`.

**Exercise 8 — Exception wrapper.** Have a handler throw `QuoteContractException` and use `QuoteExceptionChecks` to inspect the typed cause.

**Exercise 9 — Flow refactor.** Replace the `DirectChannel` handler with Transformer + Router + Handler; re-run the exact same contract suite.

**Exercise 10 — Parallel requests.** Run `ParallelQuoteGatewayContractTest` and confirm `requestId`/amounts never swap across two callers.

**Exercise 11 — Async API.** Define `AsyncQuoteGateway` returning `CompletableFuture`, testing both normal and exceptional completion with bounded timeouts.

**Exercise 12 — Timeouts.** Compare a slow `DirectChannel` handler against an `ExecutorChannel` reply timeout. Explain why `replyTimeout` cannot preempt synchronous code.

**Exercise 13 — Fault injection.** Make a handler drop replies, omit a Router route, and drop one Aggregator part; define explicit timeout/error contracts.

**Exercise 14 — Error channel.** Configure an error handler on `ExecutorChannel` and confirm `ErrorMessage` does not automatically become a `QuoteReply`.

**Exercise 15 — Void Gateway.** Build a one-way audit Gateway and test the difference between dispatch acceptance and durable business commit.

**Exercise 16 — Broker request/reply.** Design reply-to/correlation headers; push requests A/B through a mock broker that reorders replies and verify zero cross-wiring.

**Exercise 17 — Idempotent command.** Introduce `commandId`, dispatch duplicates, and assert business state mutates only once even when the Handler receives multiple deliveries.

**Exercise 18 — Tenant isolation.** Write an ingress test with principal `tenant-a` and payload `tenant-b`; assert rejection prior to any side effect.

**Exercise 19 — Wire schema.** Serialize `QuoteReply` to JSON and verify field names, enum values, null handling, and amount units.

**Exercise 20 — Consumer-driven contracts.** Write consumer-supplied fixtures; run provider verification against the real Gateway bean.

**Exercise 21 — Logging.** Design metrics for success/rejected/timeout/no-reply broken down by method/reason without using `requestId` as a label.

**Exercise 22 — CI strategy.** Categorize unit, gateway contract, adapter, E2E, and fault-injection tests by cost and purpose.

## 29. Minimum Public Test Matrix

| # | Input / condition | Expectation at public boundary | Test layer |
|---|---|---|---|
| 1 | BOOK x2, tenant-a | ACCEPTED, 240000 VND | Gateway integration |
| 2 | PEN x3, tenant-a | ACCEPTED, 45000 VND | Gateway integration |
| 3 | Quantity=0 | REJECTED INVALID_QUANTITY | Gateway integration |
| 4 | Negative quantity | REJECTED INVALID_QUANTITY | Gateway integration |
| 5 | SKU UNKNOWN | REJECTED SKU_UNSUPPORTED | Gateway integration |
| 6 | Missing requestId | Typed contract error | Gateway integration |
| 7 | Blank tenantId | Typed contract error | Gateway integration |
| 8 | Header tenant-b, payload tenant-a | Typed conflict | Gateway integration |
| 9 | Header tenant-b, payload tenant-b | Accepted, correct context | Gateway integration |
| 10 | Gateway bean not scanned | Test context/injection fails | Gateway integration |
| 11 | Handler returns wrong reply type | Conversion/mapping error | Gateway integration |
| 12 | Handler returns null | No-reply policy | Gateway/adapter |
| 13 | Filter drops invalid request | Must not return success | Gateway integration |
| 14 | Router receives unknown SKU | Must return explicit rejection | Gateway integration |
| 15 | Aggregator fails to release | Timeout/partial reply policy | Flow + Gateway |
| 16 | `DirectChannel` slow handler | No false timeout assumption | Controlled integration |
| 17 | Async late reply | No cross-request reply | Controlled integration |
| 18 | Two concurrent requests | Matching requestId/amount | Gateway integration |
| 19 | `CompletableFuture` success | Typed completion | Async Gateway integration |
| 20 | `CompletableFuture` failure | Exceptional completion | Async Gateway integration |
| 21 | Out-of-order broker reply | Accurate correlation | Adapter integration |
| 22 | Broker redelivery | Idempotent state/receipt | E2E/DB/broker |
| 23 | HTTP JSON field renamed | Schema contract failure | Adapter/CDC |
| 24 | HTTP principal tenant mismatch | Forbidden/no side effect | Security adapter |
| 25 | `Authorization` header leak | No secrets sent outbound | Adapter integration |
| 26 | No-reply error only logged | Unacceptable as quote | Gateway/error flow |
| 27 | Stable reason code changed | Consumer contract regression | CDC |
| 28 | SLA exceeded | Deadline policy | SLA/performance tests |

### 29.1. CI Execution Order

A practical pipeline:

1. **Fast unit tests**: `QuoteService` and consumer fake tests.
2. **Gateway contract integration tests**: lightweight ApplicationContext calling the real interface.
3. **Adapter/schema tests**: JSON serializers, Spring Security ingress, broker correlation.
4. **End-to-end / fault injection**: broker, database, timeouts, redelivery, late replies.
5. **SLA/load tests**: controlled environment validating latency and throughput.

Do not force every pull request through a full production-like cluster when unit and gateway contract tests catch most regressions; yet never drop higher test layers when those guarantees are promised to consumers.

## 30. Pre-Release Checklist for a Public Gateway API

- [ ] Public Java interface specifies explicit request/reply/error contracts.
- [ ] `requestId`, `tenantId`, currency, and amount units are defined.
- [ ] Business `REJECTED` is distinguished from technical exceptions.
- [ ] Reason codes required to remain stable are listed and tested.
- [ ] `null` is never returned as success if forbidden by the API contract.
- [ ] `@MessagingGateway` and `@IntegrationComponentScan` register the bean properly.
- [ ] `@Gateway` request channels and method overrides are tested.
- [ ] `@Header` mappings are verified through Gateway behavior.
- [ ] Every non-void method has a complete reply path.
- [ ] Filter/Router fallbacks never silently drop requests expecting replies.
- [ ] Aggregator release/expiry and partial-result policies are clear.
- [ ] `requestTimeout`/`replyTimeout` are explicit and not confused with end-to-end deadlines.
- [ ] Remote I/O clients define their own timeouts.
- [ ] Async Gateways have bounded executors and failure/timeout/cancellation policies.
- [ ] One-way `void` is never treated as a durable business commit.
- [ ] `ErrorChannel` errors have public mappings where needed.
- [ ] Cause chains/wrappers are not hardcoded unless contracted.
- [ ] Public exception classes/typed replies are normalized at boundaries as needed.
- [ ] Replies match the right request under concurrent calls and out-of-order responses.
- [ ] Cross-JVM reply-to/correlation headers have adapter contract coverage.
- [ ] `replyChannel` and security context objects are never serialized onto brokers.
- [ ] Stable command IDs and idempotent receivers protect side-effecting methods.
- [ ] Timeout retries never generate new command IDs for the same business action.
- [ ] Appropriate transaction/ACK/outbox policies are in place.
- [ ] Principal/tenant authentication lives at ingress.
- [ ] Header allowlists prevent leaking tokens or PII.
- [ ] Java DTO changes and JSON/wire schema changes carry separate versioning policies.
- [ ] Handler unit tests do not substitute for gateway integration tests.
- [ ] Consumer fake tests do not substitute for provider verification.
- [ ] Gateway integration tests call the **real interface bean**.
- [ ] Happy paths, rejections, exceptions, no-reply cases, and concurrency are covered.
- [ ] Adapter tests verify HTTP/broker/serialization across external boundaries.
- [ ] Logs/metrics dimension by method/outcome/reason rather than high-cardinality IDs.
- [ ] CI stratifies unit/contract/adapter/E2E/SLA suites.
- [ ] Contract suite is re-run whenever Router/Filter/Transformer/Gateway changes.
- [ ] Runbooks exist for late replies, DLQ, replay, reconciliation, and rollback.

## 31. Summary

**Testing gateways by their public contract** means verifying **what callers actually observe when invoking the Java interface**, not just confirming an internal channel accepts messages. In Spring Integration, `@MessagingGateway` generates a proxy that turns method invocations into messages and maps replies/errors back to return types. Contract tests must therefore invoke the **real interface bean** inside a Spring context, verifying argument/header mapping, typed successes, business rejections, contract errors, non-null policies, correlation, and edge cases introduced by Filters, Routers, and Aggregators.

Stratify your tests: **unit tests** for domain handlers; **consumer fake tests** for caller logic; **gateway integration tests** for proxy and request–reply wiring; **adapter/schema tests** for HTTP/broker/serialization; and **E2E/fault tests** for transactions, retries, late replies, and idempotency. Passing fake tests do not prove the Gateway was scanned; passing `DirectChannel` tests do not prove broker ACKs; reply timeouts do not prove remote side effects rolled back.

In the **SPRING_INTEGRATION_PATTERN** module, this approach lets you refactor Routers, Filters, Transformers, Splitters, Aggregators, Gateways, retries, and error channels while maintaining a **loosely coupled, semantically clear, well-verified API**. Public contracts must stay honest about what a Gateway guarantees—and what it does **not**.

### References

- Enterprise Integration Patterns — Messaging Gateway: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Spring Integration Reference — Messaging Gateways: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message: https://docs.spring.io/spring-integration/reference/message.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration API — MessagingGateway: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/MessagingGateway.html
- Spring Integration API — Gateway: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Gateway.html
- Spring Integration API — IntegrationComponentScan: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/IntegrationComponentScan.html
- Spring Framework Reference — Testing: https://docs.spring.io/spring-framework/reference/testing.html
- Spring Framework Reference — Task Execution: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/







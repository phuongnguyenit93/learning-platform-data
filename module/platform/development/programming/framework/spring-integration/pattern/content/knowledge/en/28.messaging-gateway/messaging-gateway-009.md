# Gateway Returning `null` When There Is No Reply

## 1. Scenario: Request Sent, Yet No Reply to Return to Java

An ordering service wants to query an order's processing status through Spring Integration:

~~~java
OrderStatusReply reply = orderStatusGateway.lookup(
        new OrderStatusQuery("REQ-901", "ORD-901"));

// Here reply can be null if the Gateway does not receive
// a matching reply within the configured wait time.
~~~

An application-service author might assume: "I called a method returning `OrderStatusReply`, so I will definitely get an `OrderStatusReply`." In messaging architectures, that assumption is unsafe. A request can be **dispatched successfully**, yet downstream never sends a reply, sends it too late, gets dropped by a Filter, enters a one-way branch, or hits an error past an async boundary.

**Messaging Gateway returning `null` when there is no reply** is a scenario to understand at its exact boundary: a Java method returning a reference type expects a response value, yet the flow fails to deliver a reply message back to the gateway before the waiting condition ends. Depending on configuration and execution path, the Gateway may return `null`, throw an exception, or report failure differently. Never treat every "missing reply" case as guaranteed to be `null`.

~~~mermaid
sequenceDiagram
    participant A as Application Service
    participant G as Messaging Gateway
    participant R as Request Channel
    participant H as Service Handler
    A->>G: lookup(query)
    G->>R: Send request + reply address
    R->>H: Deliver request
    H-->>H: Process without sending reply
    Note over G,H: No reply is delivered to Gateway
    G-->>A: null after configured waiting behavior
~~~

This lesson sits in the **Messaging gateway** chapter of the `SPRING_INTEGRATION_PATTERN` module. The module's goal is learning Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, along with testing and observing processing branches.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish a **request–reply Gateway returning `null`** from a **one-way Gateway declared `void`**.
2. Explain why "request accepted" does not mean "reply arrived."
3. Understand the roles of `replyChannel`, reply wait timeouts, `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and endpoints returning `null`.
4. Classify **no reply**, **late reply**, **lost reply**, **Filter discard**, **exceptions**, and **business result `NOT_FOUND`**.
5. Design safe Gateway APIs: reference-type responses, bounded timeouts, and explicit business statuses.
6. Write `@MessagingGateway`, Spring Integration Java DSL, and JUnit 5 examples testing both reply and no-reply paths.
7. Design correlation, idempotency, retries, error channels, and observability without duplicating side effects.

## 2. Distinguishing Three Commonly Confused Cases

### 2.1. One-Way Gateway with a `void` Method

~~~java
@MessagingGateway
interface OrderCommandGateway {
    @Gateway(requestChannel = "orders.commands")
    void submit(OrderCommand command);
}
~~~

This Gateway has **no return value** in its Java contract. Callers have no `OrderStatusReply` variable to check for `null`; `void` is a deliberate choice for communication that does not expect an immediate business reply.

Do not infer that `void` is asynchronous, never throws, or is always durable. If `orders.commands` is a `DirectChannel` with a synchronous handler, the caller can block until the handler finishes and still receive an exception if dispatch/handling fails.

### 2.2. Request–Reply Gateway Expecting a Result Object

~~~java
@MessagingGateway
interface OrderStatusGateway {
    @Gateway(
        requestChannel = "orders.status.request",
        replyTimeout = "500")
    OrderStatusReply lookup(OrderStatusQuery query);
}
~~~

Here the method has return type `OrderStatusReply`, so the Gateway needs a **reply message with a compatible payload** to return an object. If the flow emits no reply and the configured timeout/wait condition allows completing without a result, a reference-returning method **can receive `null`**.

The value `500` in the example is merely an **illustrative timeout** in milliseconds for the Gateway setting. Do not treat it as a universal default across all Spring Integration versions. In production, choose timeouts from latency budgets, deadlines, and real adapter behavior; never default to waiting forever.

### 2.3. Handler Returning `null` Is Not "A Reply Payload of `null`"

~~~java
// Terminal handler: emits no reply.
handle(query, headers) {
    audit(query);
    return null;
}
~~~

Spring Messaging requires a `Message<?>` to have a **non-null payload**. In many reply-producing Service Activator endpoints, a handler return of `null` with `requiresReply=false` means **no reply message is generated**, not sending a valid `Message<null>`.

If the handler returns `new OrderStatusReply(...)`, the framework builds a reply message. If the handler returns `null` while the Gateway is waiting, that can lead to timeout and returning `null` in Java, depending on pipeline and configuration.

**Note:** Not all Transformers/Handlers treat `null` alike. A Transformer may require non-null output or have `requiresReply=true`; `null` there can throw an exception instead of ending silently.

### 2.4. Outcome Comparison Table

| Case | Java API | What Happens | Outcome at Caller |
|---|---|---|---|
| One-way Gateway | `void send(Command)` | No reply required. | No return value; can still throw. |
| Request–reply Gateway succeeds | `Reply find(Query)` | Valid reply arrives within deadline. | Returns `Reply`. |
| Request–reply Gateway gets no reply | `Reply find(Query)` | Downstream emits no reply. | Can return `null` after timeout per config. |
| Handler configured to require reply | `Reply find(Query)` | Handler produces no reply while `requiresReply=true`. | Can throw reply-required exception. |
| Downstream synchronous exception | `Reply find(Query)` | Service Activator throws on `DirectChannel`. | Exception can propagate or be wrapped. |
| Async worker throws while caller waits | `Reply find(Query)` | No reply; error handling runs separately. | `null`/timeout/exception per error flow; never assume one outcome. |
| Business reply `NOT_FOUND` | `Reply find(Query)` | Handler sends a reply message with status `NOT_FOUND`. | Receives reply object, **not `null`**. |

## 3. Request–Reply Lifecycle and Reply Channel

### 3.1. Gateway Creates a Temporary Reply Channel

When a gateway has a return type expecting a result, Spring Integration can use a **temporary reply channel** to receive the response message for the current invocation. Requests typically carry reply-destination metadata such as `replyChannel` so downstream knows where to respond.

~~~text
Caller
   |
   v
Gateway proxy
   |
   +-- request payload: OrderStatusQuery
   +-- reply address: temporary reply channel
   |
   v
orders.status.request
   |
   v
Service Activator
   |
   +-- returns reply object
   |
   v
Temporary reply channel
   |
   v
Gateway unwraps payload -> OrderStatusReply to caller
~~~

What matters is that **the reply goes back to the exact place the Gateway is waiting**. If a handler crosses to an external broker while dropping the reply destination/correlation, or writes output to an unrelated channel, the Gateway may never receive it.

### 3.2. Request Accepted Differs from Reply Available

A `MessageChannel.send(...)` succeeding per channel semantics may only confirm **the request was accepted/dispatched**. It does not guarantee downstream builds a reply, the reply reaches the right channel, or the caller receives it before the deadline.

A flow can succeed completely at the initial step:

~~~text
gateway.lookup -> requestChannel accepted -> Filter discards
                                         -> no reply sent
                                         -> Gateway waits
                                         -> null / timeout handling
~~~

### 3.3. Milestones to Distinguish

| Milestone | Meaning | Does Not Prove |
|---|---|---|
| Invocation started | Caller invoked Gateway. | Request was dispatched. |
| Request sent | Channel accepted/dispatched per contract. | Handler produced a reply. |
| Handler invoked | A subscriber executed. | Reply was sent to `replyChannel`. |
| Handler completed | Handler finished. | A non-null reply payload exists. |
| Reply sent | An endpoint sent a reply message. | Gateway received it before deadline. |
| Reply received | Gateway got a matching reply. | Business side effects are durable without a receipt. |
| Gateway returned `null` | Invocation had no value when waiting ended. | Business state is `NOT_FOUND` or unprocessed. |

### 3.4. `replyChannel` Is Not a Business Correlation ID

`replyChannel` states **where the reply must be sent in the messaging runtime**. `correlationId` links logical messages or workflows. The two do not replace each other:

~~~text
replyChannel = temporary JVM channel for call #71
correlationId = CHECKOUT-88
requestId = REQ-901
businessOperationId = RESERVE-ORD-901
~~~

If the Gateway sends across Kafka/HTTP/JMS, never serialize a JVM `MessageChannel` object for remote consumers to use. Across transport boundaries, you need **wire-portable** reply destinations, request IDs, and correlation mappings if you want cross-service request–reply.

### 3.5. Never Assume a Reply Arrives Just Because a Handler Returned an Object

If a handler sits on **another branch**, has the wrong output channel, or gets dropped by a downstream Filter after creating an object, the reply may never reach the Gateway. Therefore testing must cover the **entire flow from Gateway to return value**, not stop at unit testing `handler.handle(...)`.

## 4. Timeouts: Why Can the Gateway Return `null`?

### 4.1. Reply Timeout Caps Waiting Time

A configuration:

~~~java
@Gateway(
    requestChannel = "orders.status.request",
    replyTimeout = "500")
OrderStatusReply lookup(OrderStatusQuery query);
~~~

expresses the **Gateway's reply wait limit**. If no matching reply arrives within that wait window per framework/version semantics, a reference-returning method can complete with `null`.

**Never guess default reply timeouts.** Configure them explicitly per use case and test on your real dependency version. A reply-wait timeout does not automatically cancel downstream work and does not prove the request went unprocessed.

### 4.2. Request Timeout Differs from Reply Timeout

| Concept | Applies To | Risk If Conflated |
|---|---|---|
| Request/send timeout | Wait time to send/handoff into request channel, per channel | Mistaking channel unaccepted for missing business reply |
| Reply timeout | Time Gateway waits for reply to return | Concluding `null` means `NOT_FOUND` while worker is still running |
| Worker execution timeout | Deadline on downstream computation | Thinking Gateway timeout auto-cancels worker |
| Broker reply TTL | Reply retention/expiry at broker | Replies arriving late or lost |
| API request deadline | External HTTP/gRPC client deadline | Client timed out while internal processing continues |
| Business operation SLA | Time limit to complete a command | Reporting processing success just from Gateway return |

### 4.3. Returning `null` Does Not Equal "Processed and Found No Data"

Suppose:

~~~text
T0: Gateway lookup(ORD-901).
T1: Worker receives request, starts processing.
T2: Gateway gets no reply before deadline.
T3: Gateway returns null.
T4: Worker returns OrderStatusReply(FOUND).
~~~

At T3, `null` only means **no reply existed when the Gateway stopped waiting**. It does not mean the order does not exist; T4 shows the business result can appear afterward.

If the caller writes:

~~~java
if (gateway.lookup(query) == null) {
    return OrderStatus.NOT_FOUND;
}
~~~

that is a **semantic bug** unless the contract proved `null` can only mean `NOT_FOUND` (which is rarely provable under messaging timeouts).

### 4.4. Late Replies Are Not Automatically Delivered to Callers

The temporary reply channel attached to an invocation may no longer be active after timeout. A late reply can be rejected, ignored, log a warning, or hit error handling per configuration—**never assume it will magically populate the return variable of an already-finished call**.

If late results matter, design a **durable status store, completion event, callback, or reply queue with correlation/deadlines**. Never rely on a temporary reply channel as long-term result storage.

### 4.5. `null` Becomes Dangerous When Callers Retry

If the request is a **pure query**, bounded retries may be reasonable. If the request is a **side-effecting command**, a `null` from timeout can arrive after the worker committed. Blind retries can execute the action twice.

~~~text
SubmitPayment(requestId=PAY-901) 
    -> Gateway times out / returns null
    -> Remote payment already charged
    -> Caller retries with NEW id
    -> Double charge risk
~~~

For commands, use a **stable operation ID**, consumer/remote idempotency, and reconciliation for `UNKNOWN` outcomes. `null` is not proof that it is safe to send a brand-new command.

## 5. Business Nulls, Missing Replies, and Errors Need Separate Models

### 5.1. An Explicit Reply Type

Instead of using `null` as a business status, design:

~~~java
enum LookupStatus {
    FOUND, NOT_FOUND, PENDING, REJECTED
}

record OrderStatusReply(
        String requestId,
        LookupStatus status,
        String orderId,
        String detailCode) {}
~~~

These statuses are **business/application outcomes with real payloads**. For example:

~~~java
new OrderStatusReply(
    "REQ-901",
    LookupStatus.NOT_FOUND,
    "ORD-901",
    "ORDER_NOT_FOUND");
~~~

This differs from `null`, because the Gateway received a reply message carrying **concrete evidence** of the business outcome.

### 5.2. An Operation Not Finished Before the Deadline

If the system cannot return status before the deadline, callers should distinguish:

~~~text
FOUND       = Reply arrived and order was found.
NOT_FOUND   = Reply arrived and authoritative system confirmed no order.
PENDING     = Reply confirmed work in progress, with operation/reference.
REJECTED    = Reply/contract error confirmed invalid request.
NO_REPLY    = No reply within wait window; outcome unknown.
ERROR       = Technical failure / conversion / routing exception.
~~~

Never write `reply == null ? NOT_FOUND : FOUND`. If the API must always return an explicit value, wrap `null` at the **application boundary** into `NO_REPLY` or an appropriate exception rather than mislabeling it.

### 5.3. `null` Is Not a Valid Message Payload

A Spring `Message<T>` cannot hold a `null` payload under normal contracts. When the domain wants to say "no such order," send a **non-null DTO** such as `OrderStatusReply(NOT_FOUND)`.

A Service Activator returning `null` may mean **emit no reply message**; a Transformer returning `null` may raise an error depending on contract/`requiresReply`. Test these differences against the exact endpoint implementation.

### 5.4. Primitive Return Types Are an Anti-Pattern with No-Reply

~~~java
// Dangerous if the request might receive no reply:
@Gateway(requestChannel = "orders.count.request", replyTimeout = "500")
int countOrders(CountQuery query);
~~~

Primitive `int` cannot represent `null`. If the Gateway gets no reply, converting/unboxing to a primitive fails instead of returning a usable value. Use **reference types/DTOs and clear contracts**, or require a reply with explicit error handling.

## 6. Java and Spring Integration: Simulating Reply and No-Reply Requests

### 6.1. Transport-Independent Request Payload

~~~java
record OrderStatusQuery(String requestId, String orderId) {
    OrderStatusQuery {
        if (requestId == null || requestId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_ORDER_STATUS_QUERY");
        }
    }
}
~~~

`OrderStatusQuery` is a plain Java DTO; it does not know whether the Gateway uses `DirectChannel`, `ExecutorChannel`, a broker, or HTTP. `requestId` links logs and replies per query, and is not necessarily a side-effecting business operation ID.

### 6.2. One Gateway with Two Methods for Comparison

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
interface OrderStatusLookupGateway {

    @Gateway(
            requestChannel = "orders.lookup.reply",
            replyTimeout = "300")
    OrderStatusReply lookup(OrderStatusQuery query);

    @Gateway(
            requestChannel = "orders.lookup.silent",
            replyTimeout = "300")
    OrderStatusReply lookupWithoutReply(OrderStatusQuery query);
}
~~~

Both methods are **request–reply by Java signature** because they return `OrderStatusReply`, yet their target flows differ:

- `orders.lookup.reply`: Service Activator emits a response object.
- `orders.lookup.silent`: terminal handler only records the request and **emits no reply**.

`replyTimeout="300"` is illustrative so tests have bounded waits; production chooses per SLA. If a method returned `void`, that would be a **different one-way API** and could not prove a reference-returning Gateway returning `null`.

### 6.3. Probe for the Non-Replying Terminal Handler

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class LookupProbe {
    private final List<OrderStatusQuery> seen =
            new CopyOnWriteArrayList<>();

    void record(OrderStatusQuery query) {
        seen.add(query);
    }

    List<OrderStatusQuery> snapshot() {
        return List.copyOf(seen);
    }
}
~~~

`LookupProbe` is only for lessons and integration tests. It has no transactions, idempotency, durability, or access control. A probe recording a request proves **the handler was invoked**, not that a reply was sent.

### 6.4. Two `IntegrationFlow`s: One Replies, One Does Not

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
@IntegrationComponentScan
class GatewayNullReplyConfiguration {

    @Bean(name = "orders.lookup.reply")
    MessageChannel replyInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.lookup.silent")
    MessageChannel silentInput() {
        return new DirectChannel();
    }

    @Bean
    LookupProbe lookupProbe() {
        return new LookupProbe();
    }

    @Bean
    IntegrationFlow lookupWithReplyFlow() {
        return IntegrationFlow.from("orders.lookup.reply")
                .handle(OrderStatusQuery.class, (query, headers) ->
                        new OrderStatusReply(
                                query.requestId(),
                                LookupStatus.FOUND,
                                query.orderId(),
                                "READ_OK"))
                .get();
    }

    @Bean
    IntegrationFlow lookupWithoutReplyFlow(LookupProbe probe) {
        return IntegrationFlow.from("orders.lookup.silent")
                .handle(OrderStatusQuery.class, (query, headers) -> {
                    probe.record(query);
                    return null; // No reply message emitted.
                })
                .get();
    }
}
~~~

To run the example, place `OrderStatusLookupGateway` and the configuration in the same package scanned by `@IntegrationComponentScan`, or register the gateway interface explicitly. Examples use Spring Integration 6.x illustratively; verify exact overloads/semantics against your project's dependency in a dedicated Content QA pass instead of assuming all versions behave identically by default.

### 6.5. Flow with Reply

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Gateway
    participant C as DirectChannel
    participant H as Lookup Service Activator
    A->>G: lookup(REQ-901, ORD-901)
    G->>C: Request + temporary replyChannel
    C->>H: Lookup request
    H-->>G: OrderStatusReply(FOUND)
    G-->>A: Non-null OrderStatusReply
~~~

When the handler returns a non-null `OrderStatusReply`, Spring Integration sends the reply along the Gateway's reply route if flow and headers remain intact. At the application layer, callers can read `reply.status()==FOUND`.

### 6.6. Flow Emitting No Reply

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Gateway
    participant C as DirectChannel
    participant H as Terminal Handler
    A->>G: lookupWithoutReply(REQ-902)
    G->>C: Request + replyChannel
    C->>H: Deliver request
    H->>H: record query
    H-->>C: return null / no reply
    Note over G,C: No reply arrives before configured deadline
    G-->>A: null (no reply result)
~~~

Here **the handler truly received the message, yet the Gateway still returned `null`**. That differs sharply from "no subscriber" or "request not dispatched"; those two can throw at the channel instead of waiting for a reply.

### 6.7. Do Not Cram All Logic into the Gateway Itself

The Gateway should own the API/entrypoint, while downstream owns clear steps:

~~~text
Gateway -> Channel -> Validate -> Service Activator -> Reply
                     |
                     +-> Error / rejection outcome
~~~

If a handler only writes audit logs and emits no reply, consider **switching the Gateway API to one-way `void`** when the business truly needs no result. Never let callers believe they are running a result-returning query when they are calling a reply-less consumer.

## 7. JUnit 5: Proving Gateway Receives Replies and Returns `null`

### 7.1. Normal Reply Test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(GatewayNullReplyConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class GatewayReplyPresentIntegrationTest {

    @Autowired
    OrderStatusLookupGateway gateway;

    @Test
    void lookupReturnsRealReplyPayload() {
        OrderStatusReply reply = gateway.lookup(
                new OrderStatusQuery("REQ-901", "ORD-901"));

        assertNotNull(reply);
        assertEquals("REQ-901", reply.requestId());
        assertEquals(LookupStatus.FOUND, reply.status());
        assertEquals("ORD-901", reply.orderId());
    }
}
~~~

This test is meaningful because it traverses **Gateway proxy → request channel → Service Activator → reply channel → Java return**. Unit testing a plain handler method cannot prove reply wiring works.

### 7.2. No-Reply Test: Handler Runs, Return Is `null`

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

@SpringJUnitConfig(GatewayNullReplyConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class GatewayNoReplyIntegrationTest {

    @Autowired
    OrderStatusLookupGateway gateway;

    @Autowired
    LookupProbe probe;

    @Test
    void returnsNullWhenTerminalHandlerEmitsNoReply() {
        OrderStatusQuery query =
                new OrderStatusQuery("REQ-902", "ORD-902");

        OrderStatusReply reply =
                gateway.lookupWithoutReply(query);

        assertNull(reply);
        assertEquals(1, probe.snapshot().size());
        assertEquals(query, probe.snapshot().get(0));
    }
}
~~~

This is an **intentional scenario for no-reply configuration and bounded timeout**. If a project enables `requiresReply=true` on the handler or uses a different error-handling policy, expect an exception test instead of forcing every failure path to return `null`.

### 7.3. Do Not Measure Timeouts with Uncontrolled `Thread.sleep(...)`

A test expecting a timeout should choose a small timeout with generous tolerance for CI; never assert "exactly 300 ms." JVM scheduling, GC, executors, and build environments affect elapsed time.

If you want to measure:

~~~java
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BoundedNoReplyPatternTest {
    private final OrderStatusLookupGateway gateway;

    BoundedNoReplyPatternTest(OrderStatusLookupGateway gateway) {
        this.gateway = gateway;
    }

    @Test
    void noReplyFinishesWithinReasonableUpperBound() {
        Instant start = Instant.now();
        OrderStatusReply reply =
                gateway.lookupWithoutReply(
                        new OrderStatusQuery(
                                "REQ-903", "ORD-903"));

        assertNull(reply);
        assertTrue(Duration.between(start, Instant.now())
                .compareTo(Duration.ofSeconds(5)) < 0);
    }
}
~~~

This timing snippet only illustrates an **upper-bound** assertion and must run inside a test context injecting a valid gateway bean; it is not a runnable standalone test class without Spring Test extension/constructor injection. In the real test in Section 7.2, you can add the same measurement inside the `@SpringJUnitConfig`-managed test method.

### 7.4. Why Must the Test Check the Probe Too?

With `assertNull(reply)` alone, a test can pass for multiple reasons:

- The handler ran and returned nothing.
- The reply was dropped by a Filter.
- The handler waited too long on an executor.
- The reply went to the wrong channel.
- An error handler swallowed an exception.

Checking `probe.snapshot().size()==1` at least proves the terminal handler actually received the request in this **synchronous demo flow**. With async flows, use latches or persisted traces rather than synchronous assertions.

## 8. Three Failure Paths Distinct from Normal No-Reply

### 8.1. Channel Has No Subscriber

~~~text
Gateway -> DirectChannel (no subscribers)
~~~

Here the request may **fail to dispatch**, and Spring Messaging typically throws a dispatch/delivery error rather than silently waiting for a reply. Never lump missing subscribers together with "handler received and did not reply."

### 8.2. Handler Throws an Exception

~~~java
// Synchronous Service Activator example:
(query, headers) -> {
    throw new IllegalStateException(
            "BACKEND_LOOKUP_UNAVAILABLE");
}
~~~

With `DirectChannel`, the exception can propagate through the Gateway, possibly wrapped in `MessagingException`. With `errorChannel` or advice, routing can differ. Never write `assertNull` for every error if the contract specifies throwing.

### 8.3. Handler Catches Errors and Returns `null`

~~~java
try {
    return repository.findStatus(query);
} catch (Exception ignored) {
    return null;
}
~~~

This is a very dangerous anti-pattern: callers cannot distinguish **`NOT_FOUND`**, database timeouts, authorization denials, or bugs. Replace with typed outcomes and explicit technical error handling; never swallow exceptions and return `null` as a "safe fallback."

### 8.4. Diagnostic Table

| Symptom | Likely Path | What to Check |
|---|---|---|
| No handler invocation | Channel routing / subscriber | Bean registration, channel name, dispatch errors |
| Handler ran and returned `null` | Terminal no-reply handler | Handler contract, `requiresReply` |
| Handler returned object, caller got `null` | Reply routing / timeout | `replyChannel`, output channels, downstream Filters |
| Caller receives exception | Synchronous failure or `requiresReply` | Cause chain, endpoint/error config |
| Caller got `null`, worker finishes later | Async reply exceeded deadline | Reply deadline, late-reply/error path |
| Caller got `null` for non-existent query | Must not infer `NOT_FOUND` | Does backend emit a typed `NOT_FOUND` reply? |
| Raw JSON parse failure before handler | Inbound adapter / deserializer | Adapter error handler, raw DLQ |

## 9. `requiresReply` and `null` Return: An Easily Missed Boundary

### 9.1. `null` Permitted on a Non-Reply-Requiring Handler

On a request–reply Service Activator with `requiresReply=false`, returning `null` can mean **no reply message is produced**. The Gateway waits for a reply and may return `null` upon timeout.

### 9.2. Requiring a Reply Changes the Failure Mode

When an endpoint requires a reply (e.g., `requiresReply=true` on a reply-producing handler), returning `null` can trigger a **reply-required exception** instead of silent absence. That is usually sensible for operations whose contract forbids missing replies.

Conceptual configuration example:

~~~text
Service Activator endpoint:
  inputChannel = orders.lookup.replyRequired
  requiresReply = true

Handler returns null
  -> reply-required failure
  -> error handling / synchronous exception
~~~

That is **endpoint semantics**, distinct from a `void` Gateway method. Never enable `requiresReply` blindly on handlers designed to be one-way, as it turns valid completion into an error.

### 9.3. A Transformer Returning `null` Can Be a Different Error

A Transformer normally converts a message into a new form. If transformation cannot produce a payload, throwing a validation/mapping exception or returning an outcome object is usually better than returning `null` and dropping the message downstream. Endpoints can have different `requiresReply` defaults; test against the exact handler implementation and Spring Integration version.

### 9.4. Why Default Behavior Is Not Enough as a Contract

Production/design contracts must specify:

- Is a reply **required or optional**?
- Is `null` on missing reply **accepted API behavior** or a failure?
- What is the **total deadline** for the request?
- If no reply arrives, should the caller **retry, fallback, query status, or alert**?
- If downstream has side effects, where do **`operationId`** and idempotency live?
- Is the error channel permitted to turn exceptions into typed replies?

Never assume every Spring Integration configuration and every Gateway method share identical default timeout and exception semantics.

## 10. Filters and Routers Can Prevent Gateways from Receiving Replies

### 10.1. Filter Drops Message on the Request Path

A request can hit a Filter before reaching the Service Activator:

~~~mermaid
flowchart TD
    G["Order Status Gateway"] --> F{"Filter: orderId accepted?"}
    F -->|Yes| H["Status Handler"]
    H --> REP["OrderStatusReply"]
    F -->|No| D["Discard / no reply"]
    D -.-> GW["Gateway waits then no-reply outcome"]
~~~

If the Filter simply drops the request without creating a reply or exception per contract, the Gateway gets no response. **`Filter` returning `false`** is a routing decision, **not automatically a Java `OrderStatusReply(REJECTED)`**.

In a synchronous query API, it is usually better to return a **typed rejection** rather than silence:

~~~java
new OrderStatusReply(
        query.requestId(),
        LookupStatus.REJECTED,
        query.orderId(),
        "ORDER_ID_NOT_ALLOWED");
~~~

If invalid messages must be saved for investigation, use a discard flow/quarantine, yet design the **reply path** separately if callers still await a synchronous result.

### 10.2. `discardChannel` Does Not Automatically Reply to the Gateway

Example:

~~~text
Gateway -> Filter
             |
             +-- accepted -> Service Activator -> Reply
             |
             +-- rejected -> discardChannel -> Audit Writer
~~~

On the rejected branch, Audit Writer can finish logging while **emitting no business reply**. The Gateway still times out or returns `null`. When the API requires a result, have the rejected branch send a `REJECTED` DTO to the right reply destination or route a controlled error. Never assume sending to `discardChannel` satisfies a request–reply contract.

### 10.3. `throwExceptionOnRejection` Changes Semantics

A Filter can be configured to throw on rejection. Then the Gateway can receive the exception on the synchronous error path rather than waiting until timeout and returning `null`. Choose based on contract:

| Policy | Gateway / Caller Side | When Appropriate |
|---|---|---|
| Silent discard | Risk of no-reply / `null`. | One-way event; caller needs no reply and auditing exists. |
| Discard with reply | Can get typed `REJECTED` if reply flow is wired properly. | Request–reply API needing rejection reasons. |
| Throw on rejection | Exception / error handling. | Validation failures needing fail-fast. |
| Quarantine + async completion | No immediate business outcome; track operation status. | Long requests, asynchronous contracts. |

### 10.4. Router Fails to Resolve a Target

A Content-Based Router or Header-Based Router may find no matching channel for an input. Depending on `defaultOutputChannel`, `resolutionRequired`, and config, it may throw an error or take a default/discard route.

~~~text
orderType = UNKNOWN
    |
    v
Router
    +-- known -> handler -> reply
    +-- unknown -> default/drop/error
~~~

Never design a default route where messages are **accepted yet produce no reply** without observability. For request–reply, unknown routes usually need an explicit `UNSUPPORTED_REQUEST_TYPE` outcome or managed exception.

### 10.5. Transformers/Enrichers Dropping Reply Metadata

A Spring `Message<?>` can carry a `replyChannel` header. If a custom Transformer builds a new message and **fails to preserve selected headers** or alters the reply destination, downstream can return the right object yet send the reply to the wrong place.

~~~text
Gateway request (replyChannel=temp#1)
  -> Custom Transformer builds fresh message without replyChannel
  -> Service Activator returns Reply
  -> No valid reply destination for temp#1
  -> Gateway receives nothing
~~~

Never assume "the handler returned an object, so the Gateway definitely got it." Test the **entire route**, verifying correlation/reply destinations at the final endpoint. Yet never copy arbitrary headers from external sources blindly either, due to privileged/internal headers and security concerns.

## 11. `DirectChannel`, `ExecutorChannel`, and `QueueChannel`

### 11.1. `DirectChannel`: Synchronous Processing, Still Missing Reply

~~~text
Gateway -> DirectChannel -> Service Activator (return null)
    |                                |
    +------ no reply observed --------+
~~~

If the handler returns `null` normally without emitting a reply, the Gateway still has to handle absence. A synchronous handler can also **block for a long time** before returning, making the caller wait for the handler's execution time rather than just "reply timeout."

**Trap:** configuring `replyTimeout=300ms` does not mean synchronous downstream operations get aborted at 300 ms. A receive-reply timeout is not a mechanism that kills a handler executing on the same thread.

### 11.2. `ExecutorChannel`: Worker May Finish Past Deadline

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Gateway
    participant E as ExecutorChannel
    participant W as Worker
    A->>G: lookup(query)
    G->>E: schedule request
    E->>W: handle request later
    Note over G,W: Gateway is waiting for reply
    G-->>A: null after timeout
    W->>W: finishes processing
    W--xG: Late reply cannot satisfy finished invocation
~~~

`ExecutorChannel` introduces a thread boundary, yet does not persist replies in a durable store. If workers are slow, overloaded, or throw exceptions, the Gateway may receive no reply. Use bounded executors, queue-depth monitoring, error handling, and fitting deadlines.

### 11.3. `QueueChannel`: Message Present, No Consumer

`QueueChannel` can hold requests for a poller to pick up later. If:

- No poller is configured.
- The poller is stopped.
- Consumers are overloaded.
- The queue is full or fails on receive.

the Gateway may get no reply within the deadline or hit a send/handoff error. Distinguish **pending requests** from **lost requests**.

### 11.4. Comparison Table

| Channel / Flow | When Can the Gateway Return `null`? | Errors to Watch | Durability |
|---|---|---|---|
| `DirectChannel` + null-returning terminal handler | No reply produced. | Reply-required, sync exceptions, misrouting. | Not storage. |
| `ExecutorChannel` + delayed worker | Reply misses deadline. | Task rejections, async exceptions, late replies. | Not durable by default. |
| `QueueChannel` + poller | Request queued, no reply before deadline. | Queue depth, poller state, send timeouts. | In-memory queue not durable by default. |
| Persistent message channel/store | Pending reply past deadline. | Transactions, retries, correlation, retention. | Per store/config. |
| External broker request–reply | Reply misses reply destination before timeout. | Network, codec, reply topic/queue, consumer group. | Per broker/adapter. |

No channel type guarantees every business request gets a timely reply just because the Gateway method declares a return type.

### 11.5. Async Tests Must Wait on Clear Signals

An `ExecutorChannel` integration test should use `CountDownLatch`/`BlockingQueue.poll(timeout)` or a test message store; avoid:

~~~java
gateway.lookup(query);
Thread.sleep(100);
assertThat(worker).hasCompleted();
~~~

Every test using latches must release them in `finally` and shut down executors so CI never hangs. When testing **late replies**, control when the worker emits its response with a latch instead of relying on random thread scheduling.

## 12. Late Replies and Correlation

### 12.1. Lifecycle of a Delayed Reply

~~~text
Request:
  requestId = REQ-901
  correlationId = CHECKOUT-88
  sentAt = T0
  replyDeadline = T0 + 300 ms

Worker:
  starts at T0 + 150 ms
  completes at T0 + 700 ms

Gateway:
  no reply by deadline -> null/no-reply result
~~~

A reply produced at 700 ms must never be treated as the response to **another Java invocation** just because both share an `orderId`. Accurate request identities and reply matching/correlation are mandatory.

### 12.2. A Late Reply Does Not Mean the Message Was Lost at the Business Layer

A consumer may finish a query or command after the deadline. For a **query**, callers can re-query status; for a **command**, check the operation ledger before retrying. Never treat `NO_REPLY` as an automatic rollback signal.

### 12.3. Protecting Against Replies from Old Requests

Suppose the same `orderId`:

~~~text
Request #1: REQ-901 (times out)
Request #2: REQ-902 (new query)
Late reply: REQ-901
~~~

If custom reply routing matches solely by `orderId`, late reply #1 can be misrouted into #2. Use distinct request IDs, correlation IDs, deadlines, and contract-aligned reply selectors/consumers. With a shared broker reply queue, track an in-flight request registry and audit late replies.

### 12.4. Spring `replyChannel` Is Not a Durable Reply Inbox

Temporary reply channels work well for an active waiting Java call. Once the invocation ends, however, **it is not a place to store replies for callers to read tomorrow**. If deadlines can span minutes or hours, switch to **asynchronous operation status + completion events**, or a durable request–reply architecture with clear correlation, dead letters, and expiry.

### 12.5. Choose Timeouts by Deadlines and SLOs

A sensible timeout should consider:

- Expected downstream p50/p95/p99 latency.
- Tail latency and queue backlog impact.
- Network/broker delivery and serialization overhead.
- Upstream HTTP caller deadlines.
- Retry budgets and total max duration.
- Consequences of late replies, especially for payments and inventory.

Too short → frequent false nulls even when the backend is about to reply. Too long → threads/resources stay pinned, hurting throughput. If downstream can take minutes, do not leave thousands of Gateway request threads waiting endlessly.

## 13. Error Channel and Exceptions Differ from No-Reply

### 13.1. Synchronous Exceptions Can Propagate

With `DirectChannel`, downstream throws on the call stack can be wrapped in a Spring Messaging exception:

~~~text
Gateway.lookup()
  -> DirectChannel
  -> Service Activator throws DatabaseUnavailableException
  -> MessagingException / cause chain
  -> Caller sees exception
~~~

Never catch all exceptions and return `null`, or you hide **technical failures**.

### 13.2. Asynchronous Exceptions May Not Return to the Caller

With `ExecutorChannel` or a broker adapter:

~~~text
Gateway waiting...
Async worker throws
  -> configured error handling
  -> ErrorMessage / errorChannel or adapter recovery
Gateway may still have no normal reply
~~~

`ErrorMessage` and `errorChannel` depend on configuration. Never assume every deserialization error, broker consumer failure, JVM exception, and security denial routes to the global `errorChannel` automatically.

### 13.3. If You Want to Return an Error Reply, Design It Explicitly

A gateway method expecting a result every time can use a typed envelope:

~~~java
enum LookupOutcomeType {
    FOUND, NOT_FOUND, REJECTED, TECHNICAL_ERROR
}

record LookupOutcome(
        String requestId,
        LookupOutcomeType type,
        OrderStatusReply value,
        String errorCode) {}
~~~

An error-handling flow **can** send `LookupOutcome(TECHNICAL_ERROR)` along the right reply path. Yet that is **application logic you must configure**, not something that appears automatically just by enabling an error channel.

If a failure happens before dispatch or in an adapter without a reply destination, callers can still receive direct exceptions or timeouts. A reply contract never replaces observing all failure modes.

### 13.4. No-Reply Is an Under-Evidenced Outcome

For system status:

~~~text
No reply:
  knows: no usable reply before invocation ended
  does not know: processing never started
  does not know: consumer failed
  does not know: business state not found
  does not know: operation not committed
~~~

If the application needs a guaranteed `"NOT_FOUND"`, it must receive an **authoritative lookup reply**, never infer it from absence.

## 14. Distinguishing `null` from Empty Results and `NOT_FOUND`

### 14.1. Query Finding No Data

Not finding an order can be a valid business outcome:

~~~java
return new OrderStatusReply(
        query.requestId(),
        LookupStatus.NOT_FOUND,
        query.orderId(),
        "ORDER_NOT_FOUND");
~~~

Returning this DTO has clear advantages:

- Callers distinguish `NOT_FOUND` from timeouts.
- Logs/metrics get concrete reason codes.
- The Gateway genuinely received a reply.
- You can audit which backend concluded `NOT_FOUND`.

### 14.2. An Empty List Is a Valid Reply

For a list query:

~~~java
record OrderListReply(
        String requestId,
        java.util.List<String> orderIds) {}

// No orders:
new OrderListReply("REQ-903", java.util.List.of());
~~~

That is a **non-null object containing an empty collection**, unlike a Gateway returning `null` due to missing reply.

### 14.3. `Optional` Is Not a Cure-All by Default

`Optional<OrderStatusReply>` can express absence in a Java API, yet **it does not by itself distinguish**:

- Backend confirming `NOT_FOUND`.
- Timeout with no reply.
- Filter discard.
- Swallowed system error.

Moreover, how a Gateway maps no-reply to `Optional.empty()` depends on converters/framework support; never assume changing the return type solves everything. To distinguish these states, use typed domain statuses and explicit mappings/tests.

### 14.4. Primitives, Boxing, and Null Dereferences

~~~java
int count = gateway.countOrders(query);
// If reply is absent, primitive cannot represent null.

OrderStatusReply result = gateway.lookup(query);
result.status(); // NPE if result == null.
~~~

Callers must handle `null` explicitly or prevent no-reply via API contracts, `requiresReply`, and error mapping. Never use primitives for operations that might lack replies without a clear failure policy.

### 14.5. `null` in Async Callbacks Is Not Automatic Completion

If building custom adapters with `CompletableFuture` or callbacks, `complete(null)` can mean different things depending on the library. Never project `CompletableFuture<Reply>` semantics onto traditional `@MessagingGateway` without verifying type conversion and async gateway contracts. Choose typed results and test them.

## 15. Application Boundary: Turning No-Reply into an Explicit Outcome

### 15.1. Do Not Let `null` Leak Throughout Domain Code

An application service can wrap the Gateway:

~~~java
enum StatusQueryState {
    REPLIED, NO_REPLY
}

record StatusQueryResult(
        StatusQueryState state,
        OrderStatusReply reply,
        String diagnosticCode) {

    static StatusQueryResult received(OrderStatusReply reply) {
        if (reply == null) {
            throw new IllegalArgumentException(
                    "REPLY_MUST_NOT_BE_NULL");
        }
        return new StatusQueryResult(
                StatusQueryState.REPLIED, reply, null);
    }

    static StatusQueryResult noReply() {
        return new StatusQueryResult(
                StatusQueryState.NO_REPLY,
                null,
                "GATEWAY_NO_REPLY");
    }
}
~~~

`StatusQueryResult` never claims no-reply means `NOT_FOUND`. It simply turns a **technical absence** into a named state. In production, add deadlines, `requestId`, elapsed time, and error classification as needed.

### 15.2. Safe Wrapper Service Using the Gateway

~~~java
final class OrderStatusLookupService {
    private final OrderStatusLookupGateway gateway;

    OrderStatusLookupService(OrderStatusLookupGateway gateway) {
        this.gateway = gateway;
    }

    StatusQueryResult findStatus(String requestId, String orderId) {
        OrderStatusReply reply = gateway.lookup(
                new OrderStatusQuery(requestId, orderId));

        if (reply == null) {
            return StatusQueryResult.noReply();
        }
        return StatusQueryResult.received(reply);
    }
}
~~~

Here logic handles only **returning `null` per the Gateway contract**. Exceptions like deserialization errors, dispatch failures, or security denials **keep propagating** unless caught/mapped by explicit policy. Never catch `RuntimeException` and return `NO_REPLY` for everything, hiding fixable bugs and security risks.

### 15.3. Testing the Wrapper Without Running Spring

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class OrderStatusLookupServiceTest {

    @Test
    void absenceOfReplyIsNotBusinessNotFound() {
        OrderStatusLookupGateway fake =
                new OrderStatusLookupGateway() {
                    @Override
                    public OrderStatusReply lookup(
                            OrderStatusQuery query) {
                        return null;
                    }

                    @Override
                    public OrderStatusReply lookupWithoutReply(
                            OrderStatusQuery query) {
                        return null;
                    }
                };

        StatusQueryResult result =
                new OrderStatusLookupService(fake)
                        .findStatus("REQ-100", "ORD-100");

        assertEquals(StatusQueryState.NO_REPLY, result.state());
        assertEquals("GATEWAY_NO_REPLY", result.diagnosticCode());
        assertNull(result.reply());
    }
}
~~~

This pure Java test proves **how the application interprets `null`**. It does not prove a real Gateway proxy returns `null` in a Spring flow; that evidence comes from the integration tests in Section 7.

### 15.4. API Options When a Reply Is Mandatory

For operations requiring "every request must return a business response," you can:

- Ensure handlers always return non-null replies for valid outcomes: `FOUND`, `NOT_FOUND`, `REJECTED`, `PENDING`.
- Configure `requiresReply` on appropriate endpoints so `null` from a bug becomes an exception.
- Use bounded timeouts; on expiry, translate to `NO_REPLY`/`OUTCOME_UNKNOWN` at the API boundary.
- Provide fallbacks/status queries or explicit error policies.
- Test misrouting, Filter discards, and late replies.

Not every case should enable `requiresReply`: a valid one-way command handler intentionally emits no reply. Avoid applying one blanket policy across every endpoint in the system.

## 16. When a Query Truly Has No Data

### 16.1. `NOT_FOUND` Must Come Only from an Authoritative Source

A database query returns empty/not-found. The handler must **build the response**:

~~~java
OrderStatusReply handleLookup(OrderStatusQuery query) {
    return repository.findById(query.orderId())
            .map(order -> new OrderStatusReply(
                    query.requestId(),
                    LookupStatus.FOUND,
                    order.id(),
                    "ORDER_FOUND"))
            .orElseGet(() -> new OrderStatusReply(
                    query.requestId(),
                    LookupStatus.NOT_FOUND,
                    query.orderId(),
                    "ORDER_NOT_FOUND"));
}
~~~

This is simplified domain logic; `repository` is an injected dependency assumed by the implementation. Use an equivalent mapping whenever an API needs to report `NOT_FOUND`, instead of returning `null` from the repository and letting the Gateway/Service Activator silently emit no reply.

### 16.2. `NO_REPLY` Should Usually Remain an Unknown Status

~~~text
Reply(FOUND)       -> Business knows order exists
Reply(NOT_FOUND)   -> Business knows authoritative source found no order
Reply(PENDING)     -> Business knows processing is pending
null / no reply    -> Caller cannot know final business outcome
Exception          -> Caller knows a technical/dispatch failure was reported
~~~

When mapping no-reply to HTTP `504 Gateway Timeout` or `UNKNOWN`, keep it separate from HTTP `404 Not Found`. A downstream network outage does not make an existing order "not found."

### 16.3. Status Can Change After a Reply

Even after receiving `Reply(NOT_FOUND)`, distributed systems can exhibit eventual consistency: an order may just have been created on another shard while the projection lags. Business contracts should state the **consistency model** of `NOT_FOUND`, not merely handle `null`.

### 16.4. Do Not Use `null` to Express Permission Denied

An API may intentionally hide resource existence under certain security policies, yet that must be designed at the API boundary with proper status codes and auditing; never let network timeouts and authentication failures collapse into the same `null`.

## 17. Retries When the Gateway Returns `null`

### 17.1. Idempotent Queries Can Use Bounded Retries

For **read-only lookups**:

~~~text
Attempt 1: lookup(requestId=REQ-1) -> NO_REPLY
Backoff with jitter
Attempt 2: lookup(requestId=REQ-2) -> Reply(FOUND)
~~~

The two attempts may use separate request IDs for tracing while targeting the **same business entity**. Retries need an overall deadline, not 30-second waits repeated endlessly per attempt. Under backend overload, aggressive retries worsen incidents.

### 17.2. Commands Must Never Retry Blindly Just Because of `null`

For `ReserveInventory` or `ChargePayment`:

~~~text
Attempt 1:
  operationId = RESERVE-ORD-901
  Gateway receives no reply
  Remote consumer may have committed

Attempt 2:
  same operationId + same semantic payload
  consumer/remote service checks authoritative ledger
~~~

Never mint a new `operationId` on each attempt for the same logical operation. Use remote idempotency keys, inbox/operation ledgers, and reconciliation for uncertain states.

### 17.3. `null` Is Not Evidence for Rollback

Getting `null` after a timeout **does not prove** an external service's transaction failed to commit. A local rollback only undoes resources inside the local transaction scope. Remote effects require sagas, compensation, or reconciled state; never "undo" by pretending the operation never ran.

### 17.4. Backoff and Retry Budgets

Example policy:

~~~text
Total request deadline = 2 seconds
Attempt #1 reply wait = 400 ms
Backoff = 100 ms + jitter
Attempt #2 reply wait = 400 ms
Backoff = 200 ms + jitter
Remaining time used for status lookup or final UNKNOWN
~~~

Numbers are illustrative only, not universal best practices. Deadlines must include network/queue/handler latency, serialization, and fallback time. Stop retrying once the overall deadline expires.

### 17.5. When `null` Is a Configuration Bug, Retrying Is Pointless

If a handler is written to `return null` in all cases, or a Router unconditionally directs to a discard channel, retrying 100 times still produces no reply. Fix the flow contract instead of raising timeouts or retry counts.

## 18. Controlled Testing of Late Replies

### 18.1. Goals

Prove that:

1. The Gateway actually sends the request.
2. The handler **starts processing**.
3. The Gateway finishes waiting before the handler emits a reply.
4. The late reply **is not assigned** to a newer or wrongly correlated Java invocation.
5. The system tracks completion/errors properly.

### 18.2. Use Latches Instead of `Thread.sleep`

Test fixture pattern:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

final class DelayedReplyProbe {
    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch allowReply = new CountDownLatch(1);

    OrderStatusReply handle(OrderStatusQuery query)
            throws InterruptedException {
        started.countDown();
        if (!allowReply.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("TEST_REPLY_WAIT_EXPIRED");
        }
        return new OrderStatusReply(
                query.requestId(),
                LookupStatus.FOUND,
                query.orderId(),
                "LATE_REPLY");
    }
}
~~~

This fixture is intended for an **`ExecutorChannel` integration test**, where the worker runs on another thread. Never use it directly on a single-threaded `DirectChannel` expecting the Gateway to time out while the handler blocks synchronously, as the caller gets held right inside the handler.

### 18.3. Test Sequence

~~~text
T1  Start gateway.lookup(...) on test caller thread.
T2  Worker enters delayed handler -> started latch.
T3  Assert gateway returned no-reply at configured timeout.
T4  Release allowReply latch.
T5  Worker emits late response.
T6  Assert no reply leaked into another request.
T7  Inspect configured error/late-reply handling.
~~~

If tests spin up threads/executors, clean them up in `finally` and never leave latches stuck on assertion failures. How a temporary reply channel handles a late send is **framework- and configuration-specific**; tests should reflect actual behavior rather than assuming one fixed exception or log.

### 18.4. Late Replies After Timeout Can Still Be Valuable Data

For a computation taking several seconds, the response may contain a business result worth saving. Design a **separate durable completion path** rather than sending only to an expired temporary `replyChannel`. Delayed results can be stored by `requestId`/`operationId` for later querying after checking permissions and retention.

## 19. Correlation and Reply Matching in Distributed Systems

### 19.1. Internal Gateways and Remote Replies Do Not Use the Same Mechanism

With `DirectChannel`, reply paths can travel via internal Spring message headers. With a broker:

~~~text
Requester:
  request queue = orders.lookup.requests
  reply queue = orders.lookup.replies
  requestId = REQ-901
  correlationId = CHECKOUT-88

Responder:
  consumes request
  replies to approved reply queue
  includes requestId/correlation

Requester reply listener:
  matches in-flight request registry
  ignores/archives replies after deadline by policy
~~~

This is an **application-level request–reply pattern**; simply calling a Java Gateway does not make Spring auto-provision reply topics, temporary reply queues, correlation registries, or DLQs on every broker.

### 19.2. Never Trust Client-Supplied Reply Destinations

An untrusted request could carry `replyTo=malicious-endpoint`. If the responder sends full order details to a self-declared address, that creates **data exfiltration**. Reply destinations require allowlists/authentication, tenant scoping, and authorization; never use arbitrary URLs/topics/channel names from payloads.

### 19.3. Correlation Differs from Business Operation Identity

~~~text
correlationId = CHECKOUT-88
requestId = REQ-901
businessOperationId = RESERVE-ORD-901
traceId = TRACE-...
~~~

One workflow spans multiple requests; a request can retry; a business operation can undergo multiple deliveries. Never use a single `correlationId` as an idempotency key across all branches, and never use `traceId` as an authorization token.

### 19.4. Two Requests for the Same `orderId` Must Keep Separate Responses

~~~text
REQ-901 asks ORD-901 -> no reply
REQ-902 asks ORD-901 -> successful reply
Late reply for REQ-901 arrives
~~~

Matching solely by `orderId` lets the late reply steal `REQ-902`'s slot. Mint a new `requestId` per attempt and track per invocation; for side-effecting commands, keep **`businessOperationId`** stable across retries.

### 19.5. Trace Context Does Not Replace Durable Audits

Traces can be sampled, expire, or drop under load. Investigating "Gateway returned `null`" requires logs with `requestId`, reply timeout, channel/handler outcomes, broker coordinates, and business receipts when available. Never conclude the backend did nothing from an empty trace span.

## 20. Connection to Enterprise Integration Patterns

### 20.1. Messaging Gateway and Service Activator

The Gateway bridges **Java method invocation → Spring message**, while the Service Activator receives messages and invokes service/business logic:

~~~text
Java Caller
   -> Messaging Gateway
   -> MessageChannel
   -> Service Activator
   -> [reply object] or [no reply]
~~~

When callers expect `OrderStatusReply`, the Service Activator needs an **explicit reply contract**. A `void` side-effect method beneath an object-returning Gateway easily causes a no-reply mismatch. Never assume two APIs align just because they accept the same request DTO.

### 20.2. Transformer

A Transformer can convert:

~~~text
OrderStatusQuery
   -> PartnerLookupRequest
   -> External Service
   -> PartnerLookupResponse
   -> OrderStatusReply
~~~

If a Transformer step returns `null` for an unsupported source schema or mapping error, depending on endpoint semantics it may throw or emit no reply. To avoid turning data errors into "Gateway got nothing," return a **`MappingResult`/`RejectedResult`** or throw an exception with a clear reason.

### 20.3. Filter

Filters can keep or drop requests or replies. Two cases:

~~~text
A. Gateway -> Filter(request) -> no handler -> no reply.

B. Gateway -> Handler -> Filter(reply) -> discard
   -> no reply reaches Gateway.
~~~

In B, the handler built a reply, yet a downstream Filter dropped it. Debugging only the handler can mislead you into thinking "it already replied." Trace all the way to the **final reply channel**, and preserve validation/rejection outcomes when Filters block invalid data.

### 20.4. Content-Based Router and Default Route

~~~mermaid
flowchart TD
    G["Gateway lookup"] --> R{"Router by query type"}
    R -->|Order status| A["Order handler -> reply"]
    R -->|Shipment status| B["Shipping handler -> reply"]
    R -->|Unknown| U["Default discard?"]
    U --> N["No reply / error path"]
~~~

For reply-expecting Gateways, default branches must never quietly turn unknown requests into `null`. An explicit `UNSUPPORTED_REQUEST_TYPE` reply or exception is far easier to govern.

### 20.5. Recipient List and Publish–Subscribe

A request sent to multiple recipients can yield **multiple responses**. A `OrderStatusReply lookup(...)` method represents **one result** by default; it does not decide which reply to pick automatically:

~~~text
Gateway request
  -> Recipient A: reply A
  -> Recipient B: reply B
  -> Recipient C: no reply
~~~

If business logic needs all replies, use Aggregator/Scatter–Gather with correlation and a release strategy. If it needs only the first reply, define **first valid reply**, cancellation/late-reply rules, and fault isolation—never blindly ignore side-effecting branches.

### 20.6. Splitter

A query for 100 orders is split by a Splitter into 100 child requests. If one child never replies, the Aggregator may wait for all 100 and cause the Gateway to return `null` on timeout.

~~~text
BatchStatusQuery(B-1)
  -> Splitter:
       ORD-1 -> FOUND reply
       ORD-2 -> FOUND reply
       ORD-3 -> no reply
  -> Aggregator waiting for 3
  -> Gateway receives nothing before deadline
~~~

Here the cause of no-reply lies in the **group release condition**, not the Gateway sending the wrong request. You need per-child statuses, timeouts, partial-result policies, stable child IDs, and duplicate handling.

### 20.7. Aggregator

An Aggregator has a release strategy and group timeout. If a group **fails to release**, no aggregated reply is emitted. The Gateway can return `null` even though individual branches ran.

Options:

- **All required:** return result once all children arrive; timeout yields typed failure/partial outcome.
- **Quorum:** accept a sufficient subset; define policy for missing branches.
- **Partial result:** return `BatchStatusReply(PARTIAL)` listing missing IDs.
- **No partial allowed:** emit explicit error instead of vanishing silently.

Never assume an Aggregator emits a reply on timeout by default; release/expiry/partial semantics depend on configuration and business contracts.

### 20.8. Scatter–Gather

~~~mermaid
flowchart LR
    G["Lookup Gateway"] --> S["Scatter: Inventory, Pricing, Fraud"]
    S --> I["Inventory reply"]
    S --> P["Pricing reply"]
    S --> F["Fraud timeout"]
    I --> A["Gatherer"]
    P --> A
    F -.-> A
    A --> R["Release / timeout strategy"]
    R --> G
~~~

If Fraud is mandatory, two replies are not enough to mark the transaction `APPROVED`. Gateway `null` may mean the Gatherer is waiting on Fraud. Produce **`missing`/`timeout`/`invalid`** outcomes rather than forcing fake success.

### 20.9. Resequencer

If replies pass through a Resequencer and `sequenceNumber=2` is missing, it can buffer later replies waiting for order:

~~~text
reply seq=1 -> released
reply seq=3 -> buffered
reply seq=2 -> missing
Gateway deadline -> no usable final reply
~~~

Never renumber `seq=3` to `2` "to fill the gap." Define gap policies, timeouts, correlation, and business ordering semantics. `schemaVersion` is not a business sequence number.

### 20.10. Envelope Wrapper

Over a transport:

~~~text
Request Envelope:
  messageId, requestId, correlationId, reply destination
  payload = OrderStatusQuery

Reply Envelope:
  replyMessageId, requestId, correlationId
  payload = OrderStatusReply
~~~

Never confuse `MessageHeaders.ID` with `requestId`, and never let untrusted headers choose privileged reply destinations. A Transformer that strips envelope metadata can misroute replies even when the business handler returns the right DTO.

### 20.11. Claim Check

A request may carry only a claim token pointing to the payload. If the token expired or the Claim Store is unreadable, the handler may be unable to reply:

~~~text
Gateway -> Claim token -> Claim Restore fails
       -> technical error / expired claim outcome
       -> not business NOT_FOUND
~~~

Classify `CLAIM_EXPIRED`/`CLAIM_NOT_ACCESSIBLE` with recovery paths. Never infer from Gateway `null` that the business object does not exist; it could merely be a failure restoring the original payload.

### 20.12. Idempotent Receiver

A side-effecting Gateway request retried after `null` can hit an Idempotent Receiver. If an interceptor marks the message `"SEEN"` right at the start and the handler crashes, retries can be blocked even though the operation never completed.

Critical operations need durable state:

~~~text
operationId -> NEW
            -> IN_PROGRESS
            -> COMPLETED(receipt)
            -> FAILED_RETRYABLE / OUTCOME_UNKNOWN
~~~

On duplicate receipt, check **business receipt/state**, not just `SEEN`. A `null` from the Gateway does not eliminate this idempotency problem.

### 20.13. Retry and Error Channel

Retry advice helps on transient errors; error channels route technical failures. However, **missing replies** can happen **without throwing any exception**, so exception-only retry/error advice may miss them completely.

Observing no-reply requires tracking **Gateway returns, timeouts, late replies, and operation statuses**, not just exception counts.

## 21. Why Should Gateways Never Return `null` for Critical Commands?

### 21.1. Side-Effecting Commands Differ from Queries

~~~text
Query:
  "What is the status of order ORD-901?"
  Retrying can be safer if read-only.

Command:
  "Charge 850000 VND for PAY-901."
  Retrying can double-charge if remote outcome already committed.
~~~

A `PaymentReceipt charge(...)` Gateway method returning `null` leaves the caller **not knowing** whether payment completed. Proper handling usually returns `OUTCOME_UNKNOWN` and uses a durable operation ID to reconcile.

### 21.2. Typical Timeline

~~~mermaid
sequenceDiagram
    participant A as Checkout Caller
    participant G as Gateway
    participant B as Broker
    participant P as Payment Service
    A->>G: charge(PAY-901)
    G->>B: command(PAY-901)
    B->>P: deliver command
    P->>P: commit payment
    Note over G,P: reply lost or delayed
    G-->>A: null at deadline
    Note over A,P: Payment may already be completed
~~~

If the caller immediately emits `PAY-902` because `PAY-901` "got no reply," double charging becomes likely. Keep the same stable `paymentOperationId` when retrying the same business intent and use remote idempotency/ledgers; if the value must change, use an approved correction operation rather than mutating payload under the same key.

### 21.3. Durable Receipts Instead of Only Temporary Replies

A stronger design:

~~~text
POST payment command (operationId=PAY-901)
  -> authenticated validation
  -> durable outbox/broker
  -> payment consumer
  -> durable receipt store (PAY-901, COMPLETED/FAILED/UNKNOWN)
  -> completion event or query API
~~~

Synchronous Gateways still work well for fast hops; whenever external results may not finish within the deadline, consider an **asynchronous command contract** with operation status.

### 21.4. An Outbox Does Not Make Replies Appear Automatically

A transactional outbox solves **intent publishing** inside the DB transaction. It keeps commands from getting lost, yet it does not force downstream to emit replies. If the goal is a business receipt, add an **inbox/ledger, completion event/status projection, or request–reply over broker**.

### 21.5. Returning `PENDING` Requires Evidence

A typed `PENDING` reply should rest on **proof that the command was received / durably enqueued** per contract, not merely "Gateway hasn't received a reply yet." If the request was lost before reaching the broker, returning `PENDING` misleads clients.

## 22. Security, Sensitive Data, and Replies

### 22.1. Do Not Use `null` to Hide Security Failures

If a caller lacks permission to look up an order, hiding resource existence may be intentional, yet it still requires an **API security contract + audit**. Swallowing security exceptions and returning `null` like a normal timeout makes attacks indistinguishable from infrastructure errors.

### 22.2. Reply Destinations Must Be Protected

In external request–reply, if reply destinations come unverified from request headers, attackers can redirect order details to queues/topics/URLs they control.

Design:

- Authenticated caller/producer identity.
- Reply queue/topic allowlists or server-assigned addresses.
- Tenant isolation and permissions across both request and reply transports.
- Unpredictable correlation IDs if exposure is risky, though **IDs never replace authorization**.
- Data minimization: replies contain only fields the caller is authorized to read.
- Appropriate TTL/retention so sensitive replies do not sit in DLQs forever.

### 22.3. Never Log Whole Requests When Debugging `null`

Bad log:

~~~text
GatewayTimeout request={full order, customerEmail, bearerToken, cardData}
~~~

Recommended log:

~~~text
event=GATEWAY_NO_REPLY
  requestRef=REQ-901
  queryType=ORDER_STATUS
  route=orders.status.request
  configuredReplyTimeoutMs=300
  elapsedMs=...
  authenticatedTenantScope=...
~~~

If original payloads are needed for investigation, use protected storage references with access control and retention; never dump raw PII into `errorChannel` logs or metric labels.

### 22.4. Rate Limiting and Timeout Amplification

Attackers can send floods of requests that wait until reply timeout, tying up threads and connections. Enforce rate limits, bounded queues, per-tenant quotas, bulkheads, and proper timeouts. Never leave thousands of Gateway requests waiting indefinitely due to unclear defaults.

### 22.5. Late Replies Can Contain Data the Caller No Longer Has Access To

If a user's access is revoked while a request is pending, a reply emitted afterward must still pass security/tenant checks at the delivery boundary. Never push sensitive results over an old callback that is no longer authorized solely because `requestId` matches.

## 23. Observability: Measuring "No Reply" at the Right Boundaries

### 23.1. Structured Logs Should Separate Milestones

~~~text
event=GATEWAY_REQUEST_STARTED
  requestRef=REQ-901
  messageType=ORDER_STATUS_LOOKUP
  route=orders.status.request
  replyDeadlineMs=300

event=REQUEST_CHANNEL_ACCEPTED
  requestRef=REQ-901
  channel=orders.status.request

event=HANDLER_STARTED
  requestRef=REQ-901
  handler=orderStatusLookup

event=HANDLER_COMPLETED_WITHOUT_REPLY
  requestRef=REQ-901
  handler=orderStatusLookup

event=GATEWAY_NO_REPLY
  requestRef=REQ-901
  observedOutcome=NO_REPLY
  elapsedMs=...

event=REPLY_DELIVERED
  requestRef=REQ-902
  responseType=OrderStatusReply

event=LATE_REPLY_OBSERVED
  requestRef=REQ-903
  replyAgeMs=...
~~~

This is an **application-recommended logging schema**, not a set of logs emitted automatically by Spring Integration in every configuration. Emit `HANDLER_COMPLETED_WITHOUT_REPLY` only when you actually observed the handler finish normally without producing a reply—never infer it from caller timeout.

### 23.2. Recommended Metrics

| Metric | What It Measures |
|---|---|
| `gateway_requests_total{method}` | Number of invocations. |
| `gateway_replies_received_total{method}` | Calls receiving usable replies. |
| `gateway_no_reply_total{method}` | Calls completing with no reply. |
| `gateway_request_dispatch_failed_total{reason}` | Errors sending requests to channels. |
| `gateway_reply_latency_seconds{method}` | Reply latency (for successes). |
| `gateway_no_reply_wait_seconds{method}` | Duration before finishing with no reply. |
| `gateway_reply_required_error_total` | Times a reply-requiring endpoint returned `null`. |
| `gateway_late_reply_total{route}` | Replies arriving after deadline / correlation expiry. |
| `gateway_reply_routing_failed_total{reason}` | Wrong reply destination / correlation. |
| `gateway_filter_discarded_requests_total` | Requests dropped by Filters. |
| `gateway_async_worker_failed_total{class}` | Worker errors past async boundaries. |
| `gateway_outcome_unknown_total` | Commands with undetermined outcomes. |
| `gateway_inflight_requests` | Currently waiting requests. |
| `gateway_executor_queue_depth` | Backlog that can delay replies. |

These names are **instrumentation suggestions**, not guaranteed framework defaults. Avoid using `requestId`, `operationId`, `customerId`, `traceId`, or free-form order IDs as metric labels due to high cardinality and data leakage risks.

### 23.3. Why Is a Dedicated No-Reply Metric Necessary?

If a dashboard counts only exceptions:

~~~text
Gateway errors: 0
Gateway calls: 10000
Business replies: 9000
~~~

then 1,000 calls lacking business replies **do not appear in the error count** when no-reply is valid per config and the method returns `null`. Never conclude "100% of requests succeeded" just because exception count is zero.

Note that these numbers are illustrative; reconcile time windows, in-flight requests, and duplicate attempts to calculate accurate rates.

### 23.4. Split No-Reply Rates by Route and Policy

A one-way `void` Gateway must not be counted as a **no-reply failure**, since that is its intended behavior. Measure no-reply only on **methods expecting business replies**. If a specific route legitimately returns `null` under a special contract, track it under its own semantics and alert when exceeding that route's SLO.

### 23.5. Message History Helps, Yet Never Replaces a Receipt

Spring Integration Message History (when enabled) helps trace which endpoints a request traversed. It does not by itself confirm:

- The temporary reply channel was still active when the reply arrived.
- A remote consumer committed its transaction.
- Reply matching/correlation across a broker succeeded.
- A Filter did not drop the reply before the reply channel.
- The client received the reply if the connection dropped.

Combine **message history, request/reply audit events, broker transport references, trace contexts, and authoritative business statuses**.

### 23.6. SLOs Should Target Business Results, Not Just Gateway Returns

Examples:

~~~text
SLO A:
  99.9% validated status queries return a typed Reply
  within 800 ms, excluding explicitly cancelled requests.

SLO B:
  99.99% accepted payment commands reach durable
  operation status COMPLETED or FAILED within 2 minutes.
~~~

These figures illustrate how to phrase SLOs. If you only target "Gateway does not throw," a system can return `null` everywhere and still look healthy.

## 24. Runbook: Where to Start Investigating When the Gateway Returns `null`?

### 24.1. First Question: Which Gateway Type?

**Is it a `void` method?** If yes, having no reply value is normal per contract; the task then is tracking handoff and business completion, not "null return."

**If the method returns an object:** inspect timeouts, endpoints, and reply routing below.

### 24.2. Step-by-Step Checklist

1. **Method declaration:** is the return type object, primitive, collection, `Optional`, or `void`? Is `@Gateway(replyTimeout=...)` set?
2. **Gateway bean:** was the proxy registered via `@MessagingGateway` and component scan on the right package?
3. **Request channel:** is the channel name exact, does it have a subscriber/poller, and can messages be sent?
4. **Send failure:** did the caller catch and ignore a `MessageDeliveryException`, channel timeout, or task rejection?
5. **Handler invocation:** do logs/probes prove the Service Activator actually ran?
6. **Handler return:** did it return an object, `null`, throw, or send replies to another channel?
7. **Reply required:** does the endpoint have `requiresReply=true` or an exception policy?
8. **Filter/Router:** was the request or reply dropped or sent to a silent default route?
9. **Transformer/headers:** were `replyChannel`, `requestId`, correlation, or wire reply destinations lost?
10. **Async boundary:** does Executor/Queue/broker have backlog, a stopped poller, worker errors, or conversion errors?
11. **Timeouts:** are request send timeout, reply timeout, and HTTP deadlines consistent?
12. **Reply produced:** is there evidence a reply message was created and sent to the right destination?
13. **Late reply:** was the reply emitted after the invocation ended?
14. **Broker transport:** are header mappers, reply queues/topics, ACLs, consumer groups, and DLQs configured properly?
15. **Side-effect state:** if it is a command, does the durable operation ledger/receipt show `COMPLETED` or `OUTCOME_UNKNOWN`?
16. **Security:** was the query/callback blocked due to invalid tenant/source or revoked permissions?
17. **Observability:** are `NO_REPLY`, `NOT_FOUND`, `ERROR`, and `REJECTED` separated in logs/metrics?
18. **Regression:** write an integration test reproducing the exact route/timeout/loss before fixing.

### 24.3. Quick Diagnostic Table

| Symptom | Check First | Fix Direction |
|---|---|---|
| Method returns `null` right at deadline | Handler emitted no reply or async was too slow. | Typed reply or timeout/async status redesign. |
| Method throws immediately on send | Channel subscriber / configuration. | Fix wiring/dispatch. |
| Handler returns object yet Gateway gets `null` | Reply routing, Filters, temporary reply channel. | Trace reply path end-to-end. |
| `null` happens only under high load | Executor/queue saturation, broker lag. | Backpressure, capacity, deadline policy. |
| `null` happens only for one event type | Router missing route or translator bug. | Schema/routing contract. |
| `null` after schema upgrade | Codec / header mapper / version mismatch. | Compatibility tests, typed error. |
| No reply and `errorChannel` shows exception | Async failure emitted no business reply. | Map errors to reply/status if contract needs one. |
| Reply arrives after `null` | Gateway deadline too tight or slow worker. | Durable late-result handling, deadline tuning. |
| `NOT_FOUND` reply exists yet caller got `null` | Reply channel/correlation lost. | Transport/header path. |
| Caller treats `null` as 404 | Wrong API boundary semantics. | Use `NO_REPLY`/`UNKNOWN` instead of `NOT_FOUND`. |
| Payment caller gets `null`, receipt is `COMPLETED` | Reply lost after side effect. | Reconcile; do not re-charge. |
| No reply when Filter discards | One-way rejection branch. | Return rejected DTO or fail-fast exception. |

### 24.4. Short Investigation Flow

~~~text
Start with requestRef
  |
  +-> Was request accepted by channel?
  |       No -> dispatch failure
  |       Yes
  |
  +-> Was handler invoked?
  |       No -> routing/queue/broker
  |       Yes
  |
  +-> Was reply generated?
  |       No -> contract/handler/filter
  |       Yes
  |
  +-> Was reply sent to correct destination?
  |       No -> header mapping/routing
  |       Yes
  |
  +-> Did it arrive before Gateway deadline?
          No -> late reply/timeout/correlation
          Yes -> conversion/return handling
~~~

Follow **milestone evidence**, rather than "fixing" by setting `replyTimeout` to infinity or retrying 100 times when the handler always returns `null`.

## 25. Test Matrix for Missing Gateway Replies

| ID | Scenario | Must Verify | Must Not Happen |
|---|---|---|---|
| NR-01 | Gateway returns `OrderStatusReply`, handler returns object | Caller receives real reply. | Returning `null`. |
| NR-02 | Gateway returns reference type, terminal handler returns `null` | Caller gets no-reply outcome per config. | Treating `null` as `FOUND`. |
| NR-03 | Handler records request without replying | Probe records request; caller gets no-reply. | Concluding no handler existed. |
| NR-04 | `void` Gateway method | Caller has no business return value. | Counting `void` as a no-reply failure. |
| NR-05 | `DirectChannel` handler throws | Exception propagates/wraps. | Swallowing exception into `null`. |
| NR-06 | `DirectChannel` has no subscriber | Dispatch failure surfaces. | Treating request as processed. |
| NR-07 | Wrong Gateway request channel name | Clear context/config failure. | Silent fallback. |
| NR-08 | Gateway not component-scanned | No proxy bean; test fails. | Invoking a nonexistent object. |
| NR-09 | Short reply timeout configured | No reply -> bounded no-reply. | Infinite wait. |
| NR-10 | Reply arrives right before deadline | Caller receives exact reply. | Returning `null` despite valid reply. |
| NR-11 | Reply arrives past deadline | Late reply classified/observed. | Matching into a newer request. |
| NR-12 | 300ms timeout, sync handler blocks 5s | Test observes actual execution duration. | Assuming timeout kills handler. |
| NR-13 | `requiresReply=true` and handler returns `null` | Reply-required failure per endpoint. | Turning every case into `null`. |
| NR-14 | `requiresReply=false` and handler returns `null` | No-reply path per config. | Unexpected exception in test. |
| NR-15 | Transformer produces no output | Error/handling per Transformer contract. | Equating with Service Activator `null`. |
| NR-16 | Filter discards request | Business handler skips; clear no-reply/rejection route. | Caller treating as `NOT_FOUND`. |
| NR-17 | Filter discards produced reply | Gateway gets no reply; metrics mark drop point. | Reporting reply reached Gateway. |
| NR-18 | Filter throws on rejection | Error path runs instead of silent drop. | Assuming `discardChannel` always runs. |
| NR-19 | Router receives unknown type | Explicit rejection/error route. | Unaudited silent no-reply default. |
| NR-20 | Router defaults to terminal sink | Gateway no-reply detected. | Treating as business success. |
| NR-21 | Transformer drops `replyChannel` | Regression test catches broken reply routing. | Concluding handler never replied. |
| NR-22 | Handler outputs to unrelated channel | Gateway gets no-reply; trace shows destination. | Confusing `outputChannel` with `replyChannel`. |
| NR-23 | Spring `MessageHeaders.ID` changes on rebuild | Request matched by stable request ID. | Deduplicating by runtime ID. |
| NR-24 | Handler returns typed `NOT_FOUND` | Caller receives non-null `NOT_FOUND` reply. | Returning `null` instead of typed status. |
| NR-25 | Handler returns typed `PENDING` | Caller knows work is underway. | Treating `PENDING` as `null`. |
| NR-26 | Handler returns empty collection inside DTO | Non-null reply received. | Treating empty result as no-reply. |
| NR-27 | Gateway returns primitive with no reply | Clear error/conversion contract. | Silent null unboxing. |
| NR-28 | Gateway returns `Optional` with custom mapping | Real converter/type semantics tested. | Assuming `Optional` solves timeouts. |
| NR-29 | Caller calls `reply.status()` when `reply` is `null` | Wrapper prevents NPE. | Unhandled NPE. |
| NR-30 | Slow async worker | Gateway expires while worker keeps running. | Assuming `null` means worker never started. |
| NR-31 | Async worker throws | Clear error handling/alert; no-reply does not mask failure. | Expecting caller to catch across thread boundary. |
| NR-32 | Executor saturated | Queue depth/rejections rise. | Raising timeouts endlessly without backpressure. |
| NR-33 | `QueueChannel` has no poller | Pending queue observed. | Assuming request is definitely lost. |
| NR-34 | `QueueChannel` full | Send failure/timeout distinguished from reply timeout. | Counting send failure as normal no-reply. |
| NR-35 | Broker request–reply missing reply topic | Clear configuration error. | Treating as `NOT_FOUND`. |
| NR-36 | Reply consumer group not listening | Reply backlog/TTL/correlation audited. | Unalerted silent loss. |
| NR-37 | Reply header mapper drops `requestId` | No-reply/mis-correlation detected. | Matching replies by `orderId` arbitrarily. |
| NR-38 | Late reply #1 arrives while request #2 waits | Never matches into #2. | Reply leak. |
| NR-39 | Duplicate reply with same `requestId` | First-valid / multiple-reply policy. | Two side effects from duplicate responses. |
| NR-40 | Splitter child #2 emits no reply | Aggregator partial/timeout policy. | Hanging forever without status. |
| NR-41 | Aggregator group not yet released | Gateway gets no-reply at timeout; group stays pending. | Treating whole batch as `NOT_FOUND`. |
| NR-42 | Scatter–Gather Fraud times out | Not `APPROVED` solely from Pricing/Inventory. | Returning fake success. |
| NR-43 | Resequencer missing sequence #2 | Gap/recovery/timeout policy. | Reordering or faking replies. |
| NR-44 | Claim Check token expired | Technical expired-claim outcome. | Treating as order not found. |
| NR-45 | JSON decode failure before typed handler | Adapter-specific error route. | Blaming Filter as if parsed. |
| NR-46 | Authorization denied | Security error/rejection. | Hiding behind `null` like a network timeout. |
| NR-47 | Client specifies dangerous reply destination | Destination allowlist/auth. | Exfiltrating data to attacker. |
| NR-48 | Query no-reply with bounded retries | Overall deadline, bounded backoff. | Retry storm. |
| NR-49 | Command no-reply after side effect committed | Reconciliation + stable `operationId`. | Double charge. |
| NR-50 | Same `operationId`, different payload | Fingerprint conflict. | Deduplicating success on wrong payload. |
| NR-51 | Broker redelivery mints new Spring message ID | Business operation dedupe holds. | Double processing. |
| NR-52 | Outbox publishes duplicate | Consumer idempotency + receipt. | Claiming automatic exactly-once. |
| NR-53 | Caller times out while status store is `COMPLETED` | Status query returns authoritative result. | Auto-rolling back remote effects. |
| NR-54 | Debug logs contain PII | Redaction / protected references. | Logging raw full requests. |
| NR-55 | Client sends 10,000 no-reply queries | Rate limits / bulkheads / timeouts. | Thread exhaustion. |
| NR-56 | Gateway no-reply metric rises | Alerts right route; excludes `void` methods. | Reporting 100% success because exceptions=0. |
| NR-57 | Message History enabled without receipt | Distinguishes tracing from business completion. | Using history to claim commit. |
| NR-58 | Backend returns `NOT_FOUND` from stale projection | Document consistency contract. | Treating `NOT_FOUND` as globally instantaneous. |
| NR-59 | Method returns `LookupOutcome` with `ERROR` | Caller handles typed error properly. | Coercing to `FOUND`/`NOT_FOUND`. |
| NR-60 | Status query and command share timeout policy | Config separates latency/risk profiles. | Blindly copying timeouts. |

### 25.1. Which Layers Should Be Tested?

| Level | Proves | Cannot Prove |
|---|---|---|
| **Java unit test** | Wrapper `null → NO_REPLY`, typed result handling. | Gateway proxy and message routing. |
| **Spring Integration sync test** | Gateway/`DirectChannel`/handler/return/`requiresReply`. | Async races or broker mapping. |
| **Spring Integration async test** | `ExecutorChannel`, bounded waits, late reply/error flows. | Broker persistence when no broker is used. |
| **Adapter/contract test** | Reply topic/queue, headers, serializers, correlation. | Business commit outside the adapter. |
| **Database/ledger test** | Idempotency, operation status, transactions/fingerprints. | External side effects when mocked. |
| **System/chaos test** | Crashes, lost acks, duplicates, overload, late replies. | Unsimulated production edge cases. |
| **Security test** | Tenants, reply-destination ACLs, PII, replay authorization. | Untested trust boundaries. |

### 25.2. Three Core Golden Fixtures

~~~text
Fixture A — normal reply:
  requestId=REQ-1
  handlerResponse=OrderStatusReply(FOUND)
  expected=non-null Reply(FOUND)

Fixture B — no reply:
  requestId=REQ-2
  handlerEmitsReply=false
  gatewayReplyTimeout=bounded
  expected=null or explicit no-reply mapping by tested configuration
  expectedHandlerInvoked=true

Fixture C — business not found:
  requestId=REQ-3
  handlerResponse=OrderStatusReply(NOT_FOUND)
  expected=non-null Reply(NOT_FOUND)
~~~

Testing these three fixtures separately catches the most common bug: **equating a Gateway receiving no reply with a business `NOT_FOUND` outcome**. Even if your system standardizes on a single `LookupOutcome` wrapper, fixtures should still distinguish these states at the Gateway boundary.

## 26. Common Mistakes

| Anti-Pattern | Consequence | Solution |
|---|---|---|
| "Gateway returned `null` means `NOT_FOUND`." | Wrong conclusions on backend timeouts. | Return explicit `NOT_FOUND`; map `null` → `NO_REPLY`. |
| "Gateway has a return type so the handler surely replies." | Misses Filters, Routers, terminal endpoints. | Integration-test the full request–reply flow. |
| "`void` methods and `null`-returning methods are the same." | Broken business contracts. | Separate one-way from request–reply. |
| "Service Activator returning `null` sends `Message<null>`." | Misunderstands Spring Message payload contract. | `null` usually means no-reply or error per endpoint. |
| "No `null`-returning handler ever throws." | Ignores `requiresReply` / Transformer behavior. | Test endpoint-specific semantics. |
| "Reply timeout always cancels downstream handlers." | Side effects still commit past timeout. | Operation status / reconciliation. |
| "Set `replyTimeout` to infinity to eliminate `null`." | Thread starvation and high latency. | Bounded deadlines and async redesign. |
| "Catch exceptions and return `null` to keep it simple." | Hides DB, mapping, auth, and code bugs. | Typed errors and classified handling. |
| "If the handler returned an object, the Gateway definitely got it." | Reply dropped by Filter or missing header. | Trace `replyChannel` all the way to Gateway. |
| "Filter discard automatically returns `REJECTED`." | Caller gets no-reply/timeout. | Rejected DTO or fail-fast error contract. |
| "No subscriber just waits and returns `null`." | Misses dispatch failures. | Verify channel errors and subscriptions. |
| "Routing unknown messages to `nullChannel` is fine." | Silent loss in request–reply. | Explicit default rejection. |
| "`MessageHeaders.ID` is the `requestId`." | Mismatch when messages are rebuilt. | Stable application request ID. |
| "Spring `replyChannel` objects work over Kafka." | Reply routing is not wire-portable. | Protocol reply queue/topic + correlation. |
| "If a reply is late, the Java caller gets it later." | Finished call cannot receive a late return value. | Completion events / status store. |
| "Matching replies by `orderId` is enough." | Late responses match the wrong request. | Request ID + in-flight registry. |
| "No reply means the command never ran." | Retries cause double side effects. | Durable operation ledger / idempotency. |
| "Mint a new payment ID on every retry." | Repeated remote charges. | Keep stable `operationId` and fingerprint. |
| "Configuring `errorChannel` means Gateway returns typed errors." | Async errors are not mapped into replies. | Explicit error-to-reply/status flow. |
| "Count no-reply in the exception metric." | Non-throwing failures go unseen. | Measure `gateway_no_reply_total` separately. |
| "`Optional.empty()` provides enough semantics." | Cannot tell timeout from `NOT_FOUND`. | Typed result statuses. |
| "Primitive return types can represent no-reply." | Unboxing/conversion failures. | Reference DTOs or explicit failure contracts. |
| "`QueueChannel` is always durable." | Process crashes lose pending requests. | Persistent queues/brokers when needed. |
| "Incomplete aggregate means the Gateway erred." | May just be waiting on release until timeout. | Partial/timeout release policies. |
| "Caller-declared reply destinations are trustworthy." | Data exfiltration. | Destination allowlists/authorization. |
| "An empty trace span proves the request never ran." | Missing/sampled data does not prove no work. | Rely on business/transport evidence. |
| "Test only the handler method, not the Gateway." | Reply routing bugs go unverified. | Spring Integration integration tests. |
| "No status store needed because Gateway returns an object." | No way to recover after timeouts/late replies. | Durable receipts for critical operations. |

## 27. Hands-On Exercises

1. **Create a request–reply Gateway:** declare `OrderStatusLookupGateway.lookup(...)` returning `OrderStatusReply` with an explicit `replyTimeout`.
2. **Create a one-way Gateway:** declare `void submit(...)` on another interface/method; explain the Java contract differences.
3. **Replying flow:** build a Service Activator returning `OrderStatusReply(FOUND)`, and assert the caller receives non-null.
4. **`null`-returning flow:** build a terminal Service Activator returning `null`, assert the Gateway returns no-reply per config, and verify via probe that the handler ran.
5. **`null` vs. `NOT_FOUND`:** return a typed `OrderStatusReply(NOT_FOUND)` and prove it is not `null`.
6. **`null` vs. empty list:** return `OrderListReply(List.of())` and verify the payload is non-null.
7. **Application wrapper:** write `OrderStatusLookupService` converting `null` into `StatusQueryResult(NO_REPLY)`.
8. **Fake Gateway unit test:** one fake returning `null` and one returning `FOUND`; verify the wrapper never mistakes `null` for `NOT_FOUND`.
9. **Reply timeout:** vary the wait limit and measure a reasonable upper bound without using fixed `Thread.sleep` to assert millisecond precision.
10. **Slow sync handler:** use `DirectChannel` with a blocking handler and explain why `replyTimeout` does not abort synchronous work.
11. **No subscriber:** remove the Service Activator in a test context and distinguish dispatch failure from no-reply.
12. **`requiresReply`:** enable reply-required on a return-typed endpoint; verify `null` fails fast instead of producing silent absence.
13. **Filter discards request:** design an explicit rejection path instead of letting the Gateway return `null` as a business result.
14. **Filter discards reply:** generate a reply and intentionally drop it downstream; observe the Gateway getting nothing and debug the drop point.
15. **Router unknown:** define a default rejection or error route instead of routing unknowns silently to `nullChannel`.
16. **Transformer header loss:** write a test where a transformer constructs a new message missing `replyChannel`, catch the regression, and fix with selective propagation.
17. **`ExecutorChannel`:** run the handler on a worker thread and use a latch to show the Gateway can expire before completion.
18. **Late reply:** hold the worker with a latch, wait for Gateway no-reply, release the latch, and verify the late reply never leaks into another request.
19. **`QueueChannel`:** stop/start the poller, observe queue backlog and timeouts, and avoid calling in-memory queues durable.
20. **Reply over broker:** design request/reply topics or queues with `requestId`, correlation, and authorized reply destinations.
21. **Wrong correlation:** send a reply for `REQ-901` while the caller waits for `REQ-902`; verify no mismatch occurs.
22. **Multiple replies:** send two replies with the same `requestId` and define a first-valid/duplicate policy.
23. **Primitive Gateway return:** test an `int`-returning method under no-reply, document the failure behavior, and switch to a DTO.
24. **Technical error:** make the Service Activator throw; ensure callers observe the error class/cause chain rather than coercing to `NOT_FOUND`.
25. **Async `errorChannel`:** make the worker throw after Gateway return; check the error handler and `NO_REPLY`/correlation metrics.
26. **Business command:** simulate `ReserveInventory` committing while the reply is lost; retry with the same `operationId` and verify only one effect occurs.
27. **Payload conflict:** resend the same `operationId` with a different amount; detect the conflict instead of blindly returning the old receipt.
28. **Splitter/Aggregator:** one child fails to reply; test timeout/partial results and prevent fake success.
29. **Scatter–Gather:** Fraud times out while Inventory/Pricing succeed; design a safe final outcome.
30. **Resequencer:** one reply sequence is missing; add a gap policy without arbitrarily renumbering sequences.
31. **Claim Check:** claim token expires before reply; return a technical error/reconciliation state rather than `NOT_FOUND`.
32. **Security:** pass a self-declared reply destination targeting an unauthorized queue and verify the allowlist blocks it.
33. **Metrics:** record `gateway_no_reply_total` per route without counting `void` Gateways as failures.
34. **Runbook:** starting from a `REQ-901` returning `null`, trace request sent, handler invoked, reply generated, reply delivered, and deadline.
35. **Production decision:** choose among synchronous Gateway, bounded request–reply, and async command + durable status, justifying by SLA.

### 27.1. Acceptance Criteria

An implementation meets the lesson's standards when:

- Reference-returning Gateway methods and `void` methods are clearly separated by contract.
- Valid replies carry non-null payloads and explicit business statuses.
- No-reply is never conflated with `NOT_FOUND`, `REJECTED`, or `ERROR`.
- Reply timeouts are configured deliberately, bounded, and instrumented.
- Handlers returning `null` are observed apart from dispatch failures and exceptions.
- Reply routing across Transformer/Filter/Router/adapters preserves correlation.
- Late replies never attach to newer requests.
- Side-effecting commands use stable operation identity, durable receipts, and safe retry/reconciliation.
- Error channels, SLOs, logging, and metrics reflect real milestones.
- JUnit unit/integration/system tests cover every boundary relied upon.

## 28. Self-Check Questions

**Question 1: Is a Gateway returning `null` on no-reply the same as a `void` Gateway method?**

No. `void` is a signature requesting no business value. A method returning `OrderStatusReply` that yields `null` is a request–reply invocation that got no response value within the configured condition.

**Question 2: Does a Service Activator returning `null` send a Spring `Message<null>`?**

No. Spring Message payloads must not be `null` under standard contracts; `null` from a reply-producing handler usually means no reply is emitted, or raises an error when a reply is required.

**Question 3: Does the Gateway receiving no reply prove the handler never ran?**

No. The handler may have run and returned `null`, sent the reply to the wrong channel, or finished after the deadline. Check logs, probes, and traces at each milestone.

**Question 4: Does `replyTimeout` automatically kill a handler running on `DirectChannel`?**

No. Waiting for a reply does not interrupt or cancel downstream operations, especially synchronous handlers executing on the caller thread.

**Question 5: If a Gateway returns `null`, can you return HTTP 404 Not Found?**

Not by default. `null` can mean timeout, misrouting, or no response. Only a typed authoritative `NOT_FOUND` proves that business outcome.

**Question 6: How do you represent an order that truly does not exist?**

Return a non-null DTO such as `OrderStatusReply(status=NOT_FOUND)` with `requestId` and a reason code per the consistency contract.

**Question 7: Does a reply arriving after a Gateway timeout automatically populate the Java method's return value?**

No. The invocation already ended; use a late-reply or durable completion path if the result still matters.

**Question 8: If a Router finds no route, does the Gateway always return `null`?**

No. Depending on default routes, `resolutionRequired`, and error handling, it may throw or discard/no-reply. Test the real configuration.

**Question 9: Does a Filter discard automatically return a `REJECTED` reply?**

No. Design a dedicated rejection response or error path if callers are waiting.

**Question 10: What does `requiresReply=true` change?**

It turns a handler emitting no reply into a reply-required exception instead of silent absence, depending on endpoint implementation.

**Question 11: Is primitive `int` suitable when a Gateway might get no reply?**

Unsafe, because primitives cannot hold `null`; use typed DTOs/error contracts and test conversion/unboxing.

**Question 12: Does `Optional` automatically distinguish no-reply from `NOT_FOUND`?**

No. `Optional.empty()` hides why no value was present, and framework mapping semantics still must be tested.

**Question 13: When an async worker throws, does the caller always get the exception directly?**

No. An async boundary generally requires its own `errorChannel`, adapter handler, audit, or status route.

**Question 14: Why is a Gateway with a short `replyTimeout` prone to returning `null` under heavy load?**

Because queue backlogs, thread scheduling, broker lag, or handler latency can push replies past the deadline. Measure p99, queue depth, and backpressure.

**Question 15: If a payment Gateway returns `null`, can you retry with a new `paymentOperationId`?**

Not for the same logical payment. Remote side effects may already have committed; use a stable idempotency key, receipt/status reconciliation, and proper policy.

**Question 16: Is `MessageHeaders.ID` a stable `requestId` across a broker?**

No. Runtime messages can be rebuilt with new IDs; keep `requestId`, correlation, and application identity in the wire contract.

**Question 17: Do correlation ID and `replyChannel` have the same job?**

No. Correlation links logical messages; `replyChannel`/reply destination specifies where to send the response.

**Question 18: Can an unreleased Aggregator group prevent a Gateway from getting a reply?**

Yes. When the flow expects an aggregated result and the group has not met its release condition, no aggregated reply is sent. Define timeout/partial/failure policies.

**Question 19: In Scatter–Gather, if two of three branches succeed, should overall success be returned?**

Depends on the business contract. If the Fraud branch is mandatory, never return `APPROVED` before Fraud produces a valid outcome.

**Question 20: A reply was created yet the Gateway still got `null`—what should you check?**

Reply output channels, downstream Filters/Transformers, `replyChannel` propagation, broker reply destinations, correlation, and deadlines.

**Question 21: Can `errorChannel` be used as an automatic business reply?**

Not by default. `ErrorMessage`/`errorChannel` requires configuration; returning typed error replies requires mapping and routing back through the proper reply path.

**Question 22: Should `void` Gateways be counted in `gateway_no_reply_total`?**

No, because they do not promise a business reply. The no-reply metric is for methods expecting replies.

**Question 23: Why shouldn't you log entire requests when debugging `null`?**

Payloads may carry PII or credentials. Log opaque `requestId`s, reason/status codes, routes, elapsed times, and protected payload references if needed.

**Question 24: What is the first investigation step when a Gateway has no reply?**

Check the method's return type and timeout config, verify whether the request dispatched, whether the handler ran and produced a reply, and trace the reply channel, correlation, and deadline.

**Question 25: If replies cannot be guaranteed within a few seconds, what architecture makes more sense?**

Consider asynchronous commands + durable acceptance/status stores + completion events instead of blocking synchronous Gateway threads endlessly.

## 29. Pre-Production Checklist for Request–Reply Gateways

| Question | State to Confirm |
|---|---|
| Does the method truly need an immediate business reply? | If not, choose an explicit one-way `void` API. |
| Are reply types and business outcomes defined? | `FOUND`/`NOT_FOUND`/`REJECTED`/`PENDING` or equivalent statuses. |
| What does `null` represent? | `NO_REPLY`/`UNKNOWN`, never automatically `NOT_FOUND`. |
| Are reply deadlines set deliberately? | Bounded, grounded in latency budgets and SLOs. |
| Are request send timeouts tested separately? | Not confused with reply timeouts. |
| Does the handler always reply when required by contract? | Typed reply or reply-required/error semantics. |
| Do Filters/Routers have explicit default rejections? | No silent discards in request–reply. |
| Do Transformers keep selected reply metadata? | Replies reach the Gateway across every hop. |
| Do async handlers have error paths and backpressure? | Never rely solely on callers catching exceptions. |
| Are late replies handled? | Never misassigned to another request. |
| Are broker reply destinations authenticated and correlated? | No arbitrary client-supplied destinations. |
| Do command retries have idempotency keys and receipts? | No duplicate side effects on timeout. |
| Does observability measure no-reply separately? | Not just exception counters. |
| Are security and PII governed? | Redacted logs, tenant permissions, TTLs, and rate limits. |
| Do integration/system tests cover real transports? | Proxies, channels, adapters, and recovery verified. |

## 30. Conclusion

**Gateway returning `null` when there is no reply** must be understood as **response absence at the request–reply boundary**, never as a business verdict. When a `@MessagingGateway` method declares return type `OrderStatusReply`, a request can be sent successfully yet receive no reply because the Service Activator returned nothing, a Filter discarded, a Router took a silent branch, a Transformer dropped `replyChannel`, an Aggregator did not release, or a reply arrived past deadline. Under configurations that allow completing without a value, callers can receive `null`; on other failure paths, the Gateway/endpoint may **throw an exception** instead.

**Three distinctions you must never skip:**

1. **One-way `void` differs from a reference-returning Gateway returning `null`.** `void` requests no business reply; `null` on a return-typed Gateway means an expected value was missing.
2. **`null` differs from `Reply(NOT_FOUND)`.** Lacking a reply before the deadline does not prove an order does not exist or that a command did not run; use typed statuses, `NO_REPLY`/`UNKNOWN`, and authoritative receipts.
3. **Reply timeout differs from canceling downstream work.** `DirectChannel` can block synchronously; `ExecutorChannel`/`QueueChannel`/brokers can finish past the deadline; late replies and retries require correlation, error handling, and idempotency.

In `SPRING_INTEGRATION_PATTERN`, test end-to-end from the Java Gateway proxy through Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, Service Activator, and retry/error channel all the way to the actual reply destination. A trustworthy design answers three questions: **"Where was the request actually processed?"**, **"Was a reply created and delivered to the right Gateway before deadline?"**, and **"If no reply arrived, which state does the caller receive and how can it recover safely?"** Once those boundaries are clear, `null` ceases to be a mysterious value that triggers wrong `NOT_FOUND` responses, broken correlation, or duplicate business effects.

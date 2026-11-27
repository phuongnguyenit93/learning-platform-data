# Gateway and the Boundary Between Application Code and Flows

## 1. The Problem: Application Code Should Not Know the Internals of a Message Flow

An e-commerce application needs two operations:

- **Preview a quote**: calculate the total amount without creating an order.
- **Place an order**: validate the request, persist the order, and return the result.

If a controller/service depends directly on `MessageChannel`, `MessageBuilder`, and internal headers, business code starts accumulating integration logic:

~~~java
// Example of a design that couples application code too tightly to messaging.
public OrderReceipt place(PlaceOrderCommand command) {
    Message<PlaceOrderCommand> message =
        MessageBuilder.withPayload(command)
            .setHeader("replyChannel", temporaryChannel)
            .setHeader("errorChannel", errorChannel)
            .build();
    orderRequestChannel.send(message);
    Message<?> reply = temporaryChannel.receive(5_000);
    return (OrderReceipt) reply.getPayload();
}
~~~

The code has to manually manage **reply channel, timeout, casting, error path, and message identity**. When the architecture shifts from a synchronous DirectChannel to an executor/broker or adds a Router–Transformer–Aggregator, the controller may have to be modified along with it.

**Messaging Gateway** creates a **typed invocation boundary** so application code can interact with a message-driven system:

~~~java
OrderReceipt receipt = orderGateway.place(command);
~~~

Application code calls a method like an ordinary service; Spring Integration dispatches the request into the flow, waits for or receives the reply as configured, and converts the result into the declared return type.

~~~mermaid
flowchart LR
    APP["Application / Controller"] --> IFACE["Java Gateway interface"]
    IFACE --> PROXY["Spring Integration gateway proxy"]
    PROXY --> REQ["Request channel"]
    REQ --> FLOW["Filter → Router → Transformer → Handler"]
    FLOW --> REP["Reply / error path"]
    REP --> PROXY
    PROXY --> APP
~~~

**Important boundary:** A Gateway **hides messaging protocol mechanics from the caller**, not **the responsibility of defining the business contract**. The caller still needs to know whether an operation is a query or a command, whether it can time out, whether retrying is safe, and what the result status means.

This lesson belongs to the **Messaging gateway** chapter in the **SPRING_INTEGRATION_PATTERN** module. The module teaches implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows, practicing **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and observing processing branches.

After this lesson, you will be able to distinguish a gateway proxy from protocol adapters/gateways, design request–reply or one-way APIs, place boundaries along business capabilities, understand timeout and error semantics, preserve correlation across distributed flows, and write tests proving that application code does not depend on internal channel topology.

## 2. How Does a Gateway Differ from a Service Activator?

| Component | Role | Perspective |
|---|---|---|
| **Messaging Gateway proxy** | Lets application code invoke a message flow through a method | **Application → messaging** |
| **Service Activator** | Dispatches a message into a method executing business logic | **Messaging → application/service** |
| **Message Channel** | Transfers messages between endpoints | Wiring inside the flow |
| **Router** | Selects the processing branch | Orchestration |
| **Transformer** | Changes payload/message representation | Contract translation |
| **Protocol gateway** | Exchanges request/reply with HTTP, AMQP, etc. | External transport boundary |

A round trip can look like this:

~~~text
Application service
   → Messaging Gateway interface
   → request channel
   → Transformer
   → Service Activator
   → reply
   → Messaging Gateway proxy
   → application service
~~~

**Do not invert responsibilities.** `@MessagingGateway` does not execute business logic itself: it dispatches a request into the flow. `@ServiceActivator` does not define a public application API itself: it handles messages arriving at an endpoint.

For transports, the terms “inbound gateway” and “outbound gateway” have distinct meanings: an **inbound gateway** brings requests from the outside world into Spring Integration and returns a response; an **outbound gateway** sends a request from a flow to an external system and receives a response. They still follow the request–reply pattern, but they are not the same bean/proxy as a `@MessagingGateway` interface.

## 3. Ports and Adapters Architecture: Application Port First, Flow Second

An application port:

~~~java
public interface OrderApplicationPort {
    QuoteResult quote(QuoteRequest request);
    PlaceOrderResult place(PlaceOrderCommand command);
}
~~~

A Gateway can implement this port via an interface proxied by Spring Integration, or a thin Java adapter delegating to a gateway.

Desired dependency direction:

~~~text
Controller / Use case
    ↓ uses
OrderApplicationPort (plain DTOs)
    ↓ implemented by
MessagingGateway adapter
    ↓ sends to
IntegrationFlow
    ↓ invokes
Domain / infrastructure components
~~~

**Application code should not know:** `DirectChannel` vs. `ExecutorChannel`, Spring bean names of Routers, `replyChannel`, `MessageHeaders.ID`, or how many endpoints exist in the flow.

**Application code needs to know:** request schema, output schema, business status, timeout/cancel behavior, retry/idempotency contract, and how to distinguish invalid input from infrastructure failure.

This is a **stable API boundary**, not a promise that every change behind it is always transparent. If you change a synchronous flow into processing that takes hours, keeping the old synchronous return type may no longer make sense.

## 4. Define DTOs Around Business Concepts, Not Spring Messages

Java 17 example:

~~~java
record QuoteRequest(
    String tenantId,
    String productId,
    int quantity
) {}

record QuoteResult(
    String productId,
    BigDecimal total,
    String currency
) {}

record PlaceOrderCommand(
    String tenantId,
    String commandId,
    String orderId,
    List<OrderLine> lines
) {}

record OrderLine(
    String sku,
    int quantity
) {}

record PlaceOrderResult(
    String orderId,
    String commandId,
    String status
) {}
~~~

DTOs are the **application contract**, not Spring Integration classes. `commandId` identifies a **logical operation** across retries; do not substitute `MessageHeaders.ID` or `traceId`.

For multi-tenancy, `tenantId` in the payload may only be a **claim that needs verification**, not automatically a trusted identity. The ingress/gateway adapter step must cross-check the principal/verified identity before allowing a command to mutate data.

When rich domain status is needed, prefer clear enums or sealed results such as `ACCEPTED`, `SUCCEEDED`, `REJECTED`, `PENDING` rather than arbitrary strings or HTTP status codes leaked deep into the domain.

## 5. Configuring Your First Messaging Gateway Interface

Spring Integration can generate an implementation for an annotated interface:

~~~java
@MessagingGateway(
    defaultRequestChannel = "orders.quote.requests")
public interface QuoteGateway {
    QuoteResult quote(QuoteRequest request);
}
~~~

Register annotation scanning support according to your project configuration, for example:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class MessagingConfiguration {
}
~~~

`@IntegrationComponentScan` detects annotated interfaces via package scanning; if a project uses another gateway registration approach such as `@Bean`/factory, apply the corresponding setup. With Spring Boot, verify the exact scan packages, Spring Integration dependencies, and enabled auto-configuration.

Application code can then inject it:

~~~java
@Service
class CheckoutUseCase {
    private final QuoteGateway quotes;

    CheckoutUseCase(QuoteGateway quotes) {
        this.quotes = quotes;
    }

    QuoteResult preview(QuoteRequest request) {
        return quotes.quote(request);
    }
}
~~~

**No manual `Message<?>` construction at the caller.** The proxy builds a request message from the method argument and routes it to `orders.quote.requests`. This is the primary benefit of the Gateway boundary.

## 6. Adding a Flow for Request–Reply

A plain service:

~~~java
@Service
class QuoteCalculator {
    QuoteResult calculate(QuoteRequest request) {
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException(
                "INVALID_QUANTITY");
        }
        BigDecimal unitPrice = new BigDecimal("12.50");
        BigDecimal total = unitPrice.multiply(
            BigDecimal.valueOf(request.quantity()));
        return new QuoteResult(
            request.productId(), total, "USD");
    }
}
~~~

Java DSL flow:

~~~java
@Bean
IntegrationFlow quoteFlow(QuoteCalculator calculator) {
    return IntegrationFlow.from("orders.quote.requests")
        .handle(
            QuoteRequest.class,
            (request, headers) -> calculator.calculate(request))
        .get();
}
~~~

This example is **synchronous, with one handler producing one reply payload**. Spring Integration uses the request–reply reply channel mechanism to return the value to the gateway; you do not need to manually create a QueueChannel just to return a reply.

`QuoteCalculator` is a sample business service and does not yet cover tenant authorization, currency sourcing, or full pricing concurrency. The key point of the example is: **the caller invokes a method; the flow processes the message; the result returns as a DTO**.

Do not wire multiple competing subscribers onto the same input channel just to add another test flow; when broadcast is needed, use a Publish-Subscribe Channel with the proper semantics.

## 7. What Does Request–Reply Mean?

A method:

~~~java
QuoteResult quote(QuoteRequest request);
~~~

implicitly tells the caller there is a **reply belonging to that request** or an **error/timeout**. In a synchronous flow:

~~~mermaid
sequenceDiagram
    participant A as Application
    participant G as Gateway proxy
    participant C as Request channel
    participant H as Quote handler
    A->>G: quote(request)
    G->>C: Message + replyChannel
    C->>H: QuoteRequest
    H-->>G: QuoteResult reply
    G-->>A: QuoteResult
~~~

In an asynchronous flow, a message may traverse an executor or broker before the reply returns to the Gateway. At that point, request–reply requires **correlation, return address, deadline, and handling of late replies**; you cannot assume every handler finishes immediately.

**A reply does not by itself prove business commit.** If a handler only enqueues the command into a durable queue and returns `ACCEPTED`, the caller must understand that as **accepted for processing**, not `SUCCEEDED`.

## 8. The Gateway Proxy Hides `Message<?>`, Not Message Semantics

In the application:

~~~java
QuoteResult result = quoteGateway.quote(request);
~~~

Inside the flow, there are still:

- A `Message<?>` with a payload.
- A `MessageHeaders.ID` per Spring message.
- Reply/error channels.
- Correlation metadata if the flow includes Splitter/Aggregator or request–reply over a transport.
- Headers for tracing, verified tenant context, content type, and routing.

**Good boundary:** application services do not directly declare those internal headers, while the Gateway adapter/flow still propagates the necessary metadata.

When a DTO cannot fully express transport security/identity, an application adapter can accept a verified `AuthenticatedCommand`/envelope and then invoke the gateway. Avoid passing the entire HTTP request, Kafka ConsumerRecord, or Spring `MessageHeaders` into the public domain interface.

## 9. `@Gateway` on Methods for Multiple Operations

One interface can declare methods mapped to distinct request channels:

~~~java
@MessagingGateway
public interface OrderGateway {

    @Gateway(requestChannel = "orders.quote.requests")
    QuoteResult quote(QuoteRequest request);

    @Gateway(requestChannel = "orders.place.requests")
    PlaceOrderResult place(PlaceOrderCommand command);
}
~~~

Each method expresses one **operation** and one **request channel**. This helps:

- Avoid a single generic `execute(Object payload)` method for both queries and commands.
- Prevent runtime payload types from accidentally selecting the wrong branch.
- Give the Gateway operation-specific policies.
- Make it easy to mock/stub the application port in unit tests.

Do not let clients supply arbitrary channel or method names and route into write-capable handlers from an unchecked string. For dynamic operations, use an allowlisted Router with authorization and validation.

## 10. A Gateway Interface Is Not an HTTP Controller

A controller can invoke a gateway:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderGateway gateway;

    OrderController(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping
    PlaceOrderResult place(@RequestBody PlaceOrderCommand cmd) {
        return gateway.place(cmd);
    }
}
~~~

**The snippet above is not production security configuration:** an HTTP controller must validate request bytes/schema, authenticate the principal, verify tenant access, and map exceptions/timeouts to appropriate HTTP statuses. Never let clients fill in `tenantId` and implicitly write to any tenant.

The HTTP boundary handles HTTP semantics; the Gateway accepts typed Java calls; IntegrationFlow processes messages. That lets the HTTP API evolve response mapping without forcing every business handler to know `ResponseEntity`, status 400/503, or HTTP headers.

Conversely, a **Spring Integration HTTP inbound gateway** can replace part of a controller by bridging HTTP requests directly into a message flow. That is a different architectural choice and still requires its own authentication, validation, and response mapping.

## 11. Read-Only Ports and Command Ports Must Have Different Semantics

| Property | `quote()` | `place()` |
|---|---|---|
| Business side effect | No | Yes |
| Caller retry after timeout | Usually safer | Safe only with an idempotency key |
| Transaction | May not need a write transaction | Must control commit/rollback |
| Reply | Calculated price/terms | Order receipt or outcome |
| Timeout | No quote returned at call time | Does not prove order was not created |
| Authorization | Allowed to view quotes | Allowed to create orders / spend money |
| Idempotency | Result can be cached | Needs durable dedupe per logical command |

**Calling through the same Gateway abstraction does not give two methods the same behavior.** When a write command outcome is unknown due to timeout, the caller must not generate a new `commandId` for the same order intent, because it will be treated as a new operation and may double-create.

## 12. One-Way Gateways and `void`: “Sent” Does Not Mean “Processed”

A fire-and-forget API:

~~~java
@MessagingGateway(
    defaultRequestChannel = "audit.events")
interface AuditGateway {
    void record(AuditEvent event);
}
~~~

With a synchronous input channel, the method may return once the corresponding send/dispatch completes; with a queue, executor, or broker, downstream may still be processing or may not have received the message yet. **`void` has no business reply**, so never interpret a method return as proof that the audit record was durably committed.

If the application requires the event to be durably persisted before confirmation:

- Write to a **durable queue/outbox** within the appropriate transaction; or
- Define a meaningful acknowledgement/result once the receiver has persisted it; or
- Have the workflow manage asynchronous status and expose a lookup mechanism.

Do not use `void` for a Gateway where the caller **must know** the `OrderReceipt` or business failure. If a handler returns `null` on a request–reply path, the caller may block until reply timeout instead of receiving a meaningful result.

## 13. A Gateway Is an API Boundary, Not an Implicit Authorization Boundary

A method named:

~~~java
PlaceOrderResult place(PlaceOrderCommand command);
~~~

does not prove the caller is authorized to place orders. A Gateway interface is a **programming interface**, not an automatic principal or tenant authenticator.

At the ingress boundary:

1. Authenticate the HTTP/broker producer according to the transport.
2. Verify permissions for the tenant and operation.
3. Validate the request schema and business invariants.
4. Establish a verified identity/context when entering the flow.
5. Re-check domain authorization at the command service boundary where appropriate.

With an ExecutorChannel or broker, thread-local security context **does not propagate automatically**. If the flow needs authorization across an async boundary, design a verified identity envelope/claims structure with proper integrity and lifetime instead of trusting raw client headers.

In particular, never treat `businessCorrelationId` as an authorization token, and never let external callers supply `replyChannel`/`errorChannel` headers to redirect responses to arbitrary internal channels.

## 14. Reply Channel: An Invocation Return Address, Not a Business ID

A synchronous Gateway creates or uses a **return address** mechanism so replies route back to the right caller. In Spring Messaging, the reply address is typically represented via `MessageHeaders.REPLY_CHANNEL`/`replyChannel`.

~~~text
Gateway request #A
  replyChannel=A-return-address
  commandId=C-801
  businessCorrelationId=tenant-a|O-801

Gateway request #B
  replyChannel=B-return-address
  commandId=C-801        (caller retries the same logical command)
  businessCorrelationId=tenant-a|O-801
~~~

**A and B can have two distinct reply addresses** even though they represent the same business operation. Never use a return address as an idempotency key or group key.

| Field | Purpose | Stable across retry/broker? |
|---|---|---|
| `replyChannel` | Destination for the current call's reply | Do not assume |
| `errorChannel` | Error routing path depending on topology | Do not assume |
| `MessageHeaders.ID` | Spring message instance ID | Can change |
| `commandId` | Logical command / idempotency identity | Must stay stable per contract |
| `businessCorrelationId` | Groups a workflow | Must be domain-scoped |
| `traceId` | Request tracing | Does not replace business IDs |

An in-JVM channel object is normally **not something you can serialize verbatim over Kafka/AMQP**. External gateways/protocol adapters may need a reply-to destination, correlation ID, and a dedicated gateway reply listener depending on the protocol.

## 15. Request Send Timeout and Reply Wait Timeout Are Two Different Problems

A request–reply Gateway can encounter:

- **Request/send timeout**: failed to send the message into a channel with bounded capacity, buffering, or send constraints; with blocking DirectChannel calls, deadline semantics can differ from a queue-backed channel.
- **Reply/receive timeout**: the request was sent, but no reply arrived within the allowed window.
- **Business deadline**: the request is no longer useful after a point in time; downstream needs its own rule.
- **Transport timeout**: AMQP/HTTP/Kafka request–reply waiting for a response or connection expiration.

Example:

~~~text
T0 Gateway.place(C-801) starts.
T1 Request enters the flow.
T2 Handler writes to the database.
T3 Caller hits reply timeout.
T4 Handler COMMITS.
T5 Reply arrives after the deadline; caller already timed out.
~~~

**Timeout does not mean downstream was cancelled or rolled back.** Callers cannot assume the command never ran and immediately retry with a fresh `commandId`.

When configuring timeouts, verify the exact **unit, annotation/factory attribute, and request channel type** for your actual Spring Integration version. Do not treat a single timeout number as an end-to-end guarantee covering transactions, queue delays, and remote handlers.

## 16. Configuring Deadlines: Gateway Layer vs. Business Processing Layer

An API might advertise:

~~~text
Gateway reply timeout: e.g. 3 seconds
Business operation deadline: e.g. 15 seconds
Broker message expiration: separate policy
Remote service timeout: separate policy
Retry budget: maximum 3 attempts
~~~

These thresholds must be compatible. For instance, if the caller's deadline expires at 3 seconds while the worker runs for 15 seconds and commits, and the client retries at second 4, **idempotency** must block duplicates. Whether cancellation is possible depends on the handler, transport, interruption behavior, and transaction state; **there is no automatic cross-flow cancellation**.

Choosing the contract:

1. **Short, read-only queries**: synchronous with a reply timeout, allowing retries under read semantics.
2. **Short commands with side effects**: synchronous only if the system can genuinely guarantee responses within SLA and enforces idempotency.
3. **Long or fan-out commands**: return `ACCEPTED/PENDING` once durable intent is stored; provide a status endpoint or event callback.

Never fabricate `OrderResult(status="SUCCESS")` merely because the Gateway received a queue ACK or submitted a task to an ExecutorChannel.

## 17. How Do Exceptions Propagate Through a Gateway?

With a synchronous flow:

~~~text
Application → Gateway → DirectChannel → Service Activator
                                      ↘ throws InvalidOrderException
Application ← exception / wrapper
~~~

When an exception propagates back to the caller, the API layer can:

- Map **validation/authorization/permanent business errors** to specific responses.
- Map **temporary DB/network failures** to retryable errors per policy.
- Keep **unknown outcomes** of remote side effects in a state requiring reconciliation.
- Preserve the cause chain for secured logs without leaking raw stack traces.

Spring may wrap errors into `MessagingException`, `MessageHandlingException`, or other exceptions depending on the endpoint. Avoid coupling application logic to the **exact exception message string**; prefer typed exceptions/reasonCodes and inspect the cause chain.

In async flows, errors thrown **after the caller's send returns** typically travel to an error channel or container recoverer rather than “time-traveling” back to throw directly at the caller. Design an intentional **error reply** or status contract.

## 18. An Error Channel Is Not an Error Reply

Two distinct paths must be separated:

~~~text
Path A: Gateway request ─→ Service Activator ─→ reply

Path B: Gateway request ─→ async handler throws
                         └→ ErrorMessage → errorChannel → recoverer
~~~

An `ErrorMessage` is a message wrapping a `Throwable`; it may go to a channel determined by the source, poller, adapter, header, or system configuration. **Having an `ErrorMessage` land on a monitoring channel does not mean the caller receives a business error response.**

If the caller expects a reply:

- For synchronous exceptions, let the exception propagate to the Gateway and map it at the application boundary.
- For async flows, build an error response following the **proper correlation/reply-to protocol** when a reply is still possible.
- If the caller already timed out, persist a **durable terminal outcome** so the client can query or reconcile.
- If the Gateway only has a one-way contract, let the error channel drive recovery without pretending a reply exists.

**Avoid loops:** an error handler that rethrows an exception onto the same error channel without a recoverer can mask the original failure. Recovery logic needs clear ownership, a retry budget, and endpoint semantics.

## 19. Missing Replies and Filters: Turning Bad Input into a Timeout

Broken flow:

~~~text
Gateway.quote(request)
   → Filter.isValid(request) == false
   → silent discard
   → Gateway waits for reply until timeout
~~~

The caller sees a timeout and blames slow networking, even though `quantity=-1` will never be valid.

Clear options:

1. **Fail-fast:** enable `throwExceptionOnRejection(true)` on the Filter and have the API mapper convert it into a validation error with a reasonCode.
2. **Typed decision:** have a validation service return `QuoteRejected(reasonCode)` or `QuoteAccepted(result)` on the **same request–reply contract**.
3. **Quarantine:** for broker ingestion needing no reply, route malformed input to a durable rejection flow.

**A discard channel does not automatically produce a typed reply.** If you want to return an error from a discard flow, the message must reach the right request reply address or go through structured reply handling; this becomes tricky if the request already timed out or `replyChannel` was lost across a broker.

## 20. Typed Results: Distinguishing Accepted, Rejected, and Pending

Instead of forcing every outcome into `PlaceOrderResult(status="SUCCESS")`, you can use a Java 17 sealed interface:

~~~java
sealed interface PlaceOrderDecision
    permits OrderPlaced, OrderRejected, OrderPending {}

record OrderPlaced(
    String orderId,
    String commandId
) implements PlaceOrderDecision {}

record OrderRejected(
    String commandId,
    String reasonCode
) implements PlaceOrderDecision {}

record OrderPending(
    String commandId,
    String statusReference
) implements PlaceOrderDecision {}
~~~

Gateway contract:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.decide")
interface OrderDecisionGateway {
    PlaceOrderDecision place(PlaceOrderCommand command);
}
~~~

Meaning:

- `OrderPlaced`: the operation reached the success milestone **defined by the contract**.
- `OrderRejected`: terminal business/validation rejection; **do not retry the same payload**.
- `OrderPending`: durably accepted, but the final outcome cannot be determined yet; the caller gets a status reference.

These are **custom application types**, not classes auto-generated by Spring Integration from annotations. The flow must actually produce replies of the matching type—if a message gets silently discarded or an error channel only logs it, the Gateway still has no `PlaceOrderDecision` to return.

## 21. Write Boundary: Transactions Belong to the Handler, Not the Gateway Interface

A Gateway interface does not create a durable transaction by itself:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.place.requests")
interface PlaceOrderGateway {
    PlaceOrderDecision place(PlaceOrderCommand command);
}
~~~

The proper transaction boundary usually sits on the **command-executing service bean**:

~~~java
@Service
class PlaceOrderService {
    private final CommandInbox inbox;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    PlaceOrderService(
            CommandInbox inbox,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public PlaceOrderDecision execute(PlaceOrderCommand command) {
        validateAndAuthorize(command);
        String key = command.tenantId() + ":" + command.commandId();
        boolean first = inbox.claimIfAbsent(key, command);
        if (!first) {
            inbox.assertSameFingerprint(key, command);
            return inbox.loadCommittedDecision(key);
        }
        OrderPlaced result = orders.place(command);
        outbox.recordOrderPlaced(command, result);
        inbox.saveDecision(key, result);
        return result;
    }

    private void validateAndAuthorize(PlaceOrderCommand command) {
        // Trusted tenant, request validation, operation authorization.
    }
}
~~~

`CommandInbox`, `OrderRepository`, and `OutboxRepository` are **application interfaces**, not built-in Spring Integration types. Storage needs real unique constraints and a real transaction manager. Note that string concatenation for the key here is illustrative: production needs an unambiguous encoded/composite key scoped by tenant/operation alongside a payload fingerprint.

**If all repositories share the same database transaction**, failures before COMMIT roll back inbox, order, and outbox together. Redelivery after COMMIT can read the stored decision without creating a second order. However, `@Transactional` does not automatically roll back an already committed HTTP payment, an out-of-transaction Redis marker, or a publish to another broker.

## 22. A Gateway Does Not Make a Side-Effecting Command Exactly-Once

Timeline:

~~~text
T1 Application calls gateway.place(commandId=C-901).
T2 Flow dispatches the command to the Service Activator.
T3 Database COMMITS order + inbox + outbox.
T4 Caller times out or process crashes before receiving the reply.
T5 Caller retries the same logical operation.
T6 Gateway sends another message.
~~~

**The Gateway may resend the request, but the domain effect must not repeat.** Combine:

- A stable `commandId` in the domain contract.
- A transactional inbox / processed record with a unique constraint.
- A payload fingerprint to detect different content under the same key.
- A cached result or durable status for completed duplicates.
- A transactional outbox when post-commit publishing is required.
- Remote idempotency keys and reconciliation when external payments or HTTP mutations exist.

Never use `MessageHeaders.ID`, `replyChannel`, or an attempt-specific UUID as an idempotency key. Each retry may create a new Spring message, yet it must represent the **same logical command**.

## 23. Transaction Context Across Async Boundaries

Example:

~~~text
Caller thread:
  @Transactional CheckoutUseCase.place()
    → Gateway
    → ExecutorChannel.enqueue()
    → return

Worker thread:
  ServiceActivator.place()
    → database writes
~~~

A local transaction bound to the caller thread **does not automatically travel** with the task to the worker thread. If the worker needs a transaction, start the transaction **on the service actually running on the worker** under an appropriate transaction manager.

**Do not put `@Transactional` on a Gateway caller and assume database writes behind a queue or broker share the caller's transaction.** Even in synchronous flows, when multiple resources or remote calls are involved, you still need to know which transaction manager covers which operations.

A more resilient pattern for an asynchronous command:

~~~text
Caller → Gateway → durable command inbox/queue
        ← OrderPending(commandId, statusRef)

Worker → claim → business commit + outbox
       → durable status SUCCEEDED/FAILED

Caller → query status / consume completion event
~~~

OrderPending must be returned only after **durable intent has been stored**, not merely after calling `executor.submit()` in memory.

## 24. External API Request–Reply: Outbound Gateway vs. Outbound Adapter

Suppose a flow needs tax rates from an HTTP service:

~~~text
QuoteGateway.quote()
  → local request channel
  → HTTP outbound gateway: GET tax estimate
  ← HTTP response
  → Transformer
  → QuoteResult reply
~~~

An **outbound gateway** fits when you need **request–reply** with an external system. An **outbound channel adapter** typically has a **one-way** contract: it sends messages out without returning a Gateway-style business reply.

Do not force a one-way outbound adapter into request–reply and treat a send ACK as a business response from the remote system. With brokers, verify the request–reply protocol, reply-to destination, correlation, and timeouts; not every transport supports the same model.

When an outbound gateway times out, classify the operation:

| Remote operation | Safe to retry? |
|---|---|
| Pure idempotent GET/lookup | Can retry within bounds |
| POST creating a charge/payment | Only with remote idempotency/reconciliation |
| Order status lookup | Usually retryable, subject to side effects and rate limits |
| Send email | May already have sent even if response was lost; needs message/provider idempotency |

A Gateway boundary hides how an external service is called; it **does not automatically make** an operation idempotent.

## 25. Inbound Gateways and the Public API Boundary

A Spring Integration **HTTP inbound gateway** accepts an HTTP request, dispatches a message into the flow, and waits for a reply to build the HTTP response. It is an alternative to a controller calling `@MessagingGateway`:

~~~text
Option A:
HTTP Controller
  → Java @MessagingGateway interface
  → IntegrationFlow

Option B:
Spring Integration HTTP inbound gateway
  → IntegrationFlow
  → HTTP response
~~~

Commonalities: both need decoding, authentication, validation, HTTP status mapping, and timeout/error policies. Differences: Option A provides an explicit **Java application port** for multiple callers (controllers, scheduled jobs, services); Option B places the inbound messaging boundary right at the transport.

**You do not need to use both.** Pick the topology based on application use-case reuse, security/validation structure, and operational experience. If choosing an inbound gateway, do not assume authentication/authorization happens automatically just because the endpoint is Spring Integration.

## 26. Correlation When a Flow Splits, Branches, and Aggregates

Quote example requiring three services:

~~~text
QuoteGateway.quote(Q-901)
  → Splitter:
       PriceTask #1
       DiscountTask #2
       TaxTask #3
  → workers run in parallel
  → Aggregator
  → QuoteResult
  → Gateway reply
~~~

~~~mermaid
flowchart TD
    G["Gateway request Q-901"] --> SPLIT["Splitter: 3 tasks"]
    SPLIT --> P["Pricing"]
    SPLIT --> D["Discount"]
    SPLIT --> T["Tax"]
    P --> A["Aggregator"]
    D --> A
    T --> A
    A --> R["QuoteResult"]
    R --> G
~~~

For the Gateway to receive **one reply for the right request**, you need:

- Unique **parent business correlation** scoped by tenant/request/revision where appropriate.
- **Member IDs/sequence metadata** so the Aggregator knows when all results have arrived.
- Duplicate-child handling so duplicates do not inflate completion counts.
- A release strategy checked against an expected member manifest if needed.
- An Output Processor returning the exact `QuoteResult` type.
- A still-valid reply channel/return address, or an external request–reply protocol with durable correlation.

**Aggregator correlation IDs differ from Gateway reply addresses.** One request can spawn multiple child messages sharing a group; the return address tells the flow where to deliver the **final result**, not the business group identity.

## 27. One Failed Child Must Not Turn into a Meaningless Gateway Timeout

Scenario:

~~~text
QuoteGateway.quote(Q-901)
  → PriceTask success
  → DiscountTask success
  → TaxTask invalid payload / HTTP 503
  → Aggregator has only 2/3 outcomes
  → Gateway reply timeout
~~~

This is an important failure mode: a single child failure can **look like a Gateway failure** even though the Gateway itself worked properly. Distinguish:

1. **Permanent child error**: emit a `TaskOutcome(failed, reasonCode)` preserving parent correlation + member ID, if the contract allows aggregating partial/failure states.
2. **Transient child error**: bounded retry at the worker; once budget is exhausted, emit a durable failure outcome or clear workflow recovery.
3. **Group expiry**: never treat a partial group as success by default; define explicit timeout/release/cleanup policies.
4. **Gateway timeout before group completion**: the caller sees pending/timeout while workers/groups may continue; persist durable results and define a late-reply policy.

**Do not shrink `sequenceSize` from 3 to 2 just to force release.** A failed `TaxTask` is business information that must either be reflected or fail the entire request, never silently dropped from the total.

## 28. Where Does a Gateway Sit in a Layered Application?

A clean structure:

~~~text
Presentation
  └── OrderController
Application
  ├── CheckoutUseCase
  ├── OrderApplicationPort (interface)
  └── DTO/decision contracts
Integration adapter
  ├── SpringOrderMessagingGateway (proxy/adapter)
  └── IntegrationFlows
Domain + infrastructure
  ├── QuoteCalculator
  ├── PlaceOrderService
  ├── Repository/Outbox
  └── Remote gateway adapters
~~~

This is a way to **organize responsibilities**, not a mandate for one specific package layout. Two options exist:

- Application code injects `@MessagingGateway` interfaces directly if Spring Integration annotations at the port boundary are acceptable.
- Application code injects only plain Java `OrderApplicationPort`, while an adapter underneath delegates to the Spring Integration Gateway to keep the application layer framework-free.

If you want the domain completely independent, never let `Message<?>`, `ErrorMessage`, or `MessagingException` leak into domain method signatures. Translate them into typed application results/exceptions at the adapter boundary.

**A boundary does not remove the need for observability.** When debugging the application, you need to know which request entered which flow; use tracing/structured logs produced by the integration adapter rather than forcing controllers to set Spring-specific headers manually.

## 29. Designing a Plain Java Adapter Wrapping a Gateway Proxy

Example keeping Spring annotations out of the application port:

~~~java
public interface OrderApplicationPort {
    QuoteResult quote(QuoteRequest request);
}

@MessagingGateway(
    defaultRequestChannel = "orders.quote.requests")
interface SpringQuoteMessagingGateway {
    QuoteResult quote(QuoteRequest request);
}

@Component
class OrderApplicationAdapter implements OrderApplicationPort {
    private final SpringQuoteMessagingGateway gateway;

    OrderApplicationAdapter(SpringQuoteMessagingGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public QuoteResult quote(QuoteRequest request) {
        return gateway.quote(request);
    }
}
~~~

The caller sees only `OrderApplicationPort`:

~~~java
@Service
class CheckoutApplicationService {
    private final OrderApplicationPort orders;

    CheckoutApplicationService(OrderApplicationPort orders) {
        this.orders = orders;
    }

    QuoteResult preview(QuoteRequest query) {
        return orders.quote(query);
    }
}
~~~

**Value:** Unit tests for application code can fake `OrderApplicationPort` without starting a Spring Integration context. Integration testing the adapter/flow belongs to a separate layer.

If a Spring-centric project only has one small flow, this extra adapter layer may not be necessary. What matters is a **consistent boundary**, not adding indirection just for pattern purity.

## 30. Unit Testing Application Code Without Spring Integration

JUnit 5 + a fake port:

~~~java
@Test
void checkoutUseCaseUsesTypedPortWithoutChannels() {
    OrderApplicationPort fakePort = request ->
        new QuoteResult(
            request.productId(),
            new BigDecimal("25.00"),
            "USD");

    CheckoutApplicationService useCase =
        new CheckoutApplicationService(fakePort);

    QuoteResult reply = useCase.preview(
        new QuoteRequest("tenant-a", "SKU-9", 2));

    assertEquals("SKU-9", reply.productId());
    assertEquals(
        0,
        new BigDecimal("25.00").compareTo(reply.total()));
}
~~~

**This is a unit test of the application boundary**, not a test of the request channel, Transformer, or Service Activator. It proves the caller **depends solely on the method contract and DTOs**, rather than `MessageBuilder`, `@Header`, or `QueueChannel`.

Try swapping the `OrderApplicationPort` implementation for a fake HTTP adapter or an in-memory service; the application use case still compiles and retains the same business semantics as long as the contract holds.

## 31. Integration Testing the Gateway Proxy Through a Real Flow

Spring test context:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class QuoteGatewayTestConfig {

    @Bean
    QuoteCalculator calculator() {
        return new QuoteCalculator();
    }

    @Bean
    IntegrationFlow quoteTestFlow(QuoteCalculator calculator) {
        return IntegrationFlow
            .from("orders.quote.requests")
            .handle(
                QuoteRequest.class,
                (request, headers) ->
                    calculator.calculate(request))
            .get();
    }
}
~~~

If the test class falls within the appropriate component scan scope:

~~~java
@Autowired
QuoteGateway quoteGateway;

@Test
void gatewayReturnsTypedReplyFromFlow() {
    QuoteResult result = quoteGateway.quote(
        new QuoteRequest("tenant-a", "SKU-9", 2));

    assertNotNull(result);
    assertEquals("SKU-9", result.productId());
    assertEquals(
        0,
        result.total().compareTo(new BigDecimal("25.00")));
}
~~~

In this snippet, `QuoteCalculator` uses a unit price of 12.50 so quantity 2 yields 25.00. JUnit/Spring test imports and bootstrapping are omitted; configure `@SpringJUnitConfig` or equivalent and make sure **the gateway interface is scanned**. If the project already defines a `QuoteCalculator` bean, do not register a duplicate bean in the test.

**Verify the actual test context:** Ensure no other production endpoint is concurrently consuming `orders.quote.requests`. With a shared channel and competing consumers, test results can become flaky or mis-dispatched.

## 32. Testing Request–Reply Correlation Under Concurrency

Two callers:

~~~text
Caller A: quote(Q-A, product=SKU-A)
Caller B: quote(Q-B, product=SKU-B)

Flow:
  Q-B finishes first
  Q-A finishes second

Expected:
  A receives QuoteResult for SKU-A
  B receives QuoteResult for SKU-B
~~~

Test:

1. Use an executor/test barrier to control completion ordering.
2. Send two concurrent requests with **unique logical request IDs** if required by the contract.
3. Reverse the reply order.
4. Assert each caller receives its matching product/request.
5. Verify a timeout on one request does not corrupt the reply of another.
6. When using an external broker, verify correlation mapper and reply-to destination behavior.

**Never use a caller-managed shared `QueueChannel` calling `receive()` in sequence as proof of safe Gateway correlation.** If two callers pull arbitrarily from one queue, they can consume each other's replies. Gateway/protocol correlation must be sound at the request–reply adapter layer.

## 33. Testing Gateway Timeout While Downstream Still Commits

Fault injection:

~~~text
T0 Gateway.place(C-901)
T1 Handler starts
T2 Caller reply times out
T3 Handler COMMITS order
T4 Reply arrives late; caller is no longer waiting
T5 Caller queries status(C-901) → SUCCEEDED
T6 Caller retries C-901 → same committed receipt, no second order
~~~

An integration test should assert:

- The Gateway observes timeout or a pending response per contract, **without asserting FAILED**.
- Domain state can transition to SUCCEEDED after the timeout.
- Retrying with the **same commandId** produces no new business side effect.
- The late reply does not trigger an extra `place()` invocation.
- The durable outcome can be queried by commandId.

**Watch out for test timing:** arbitrary `Thread.sleep()` calls easily become flaky. Use a `CountDownLatch` or test barrier to hold the handler at the exact point, deliberately trigger the timeout, then release the handler to commit. You do not need to alter production code for testing if you use a mock clock, injected executor, or suitable test fixtures.

## 34. Testing That Invalid Gateway Requests Do Not Time Out Meaninglessly

If quantity must be positive, this request:

~~~java
new QuoteRequest("tenant-a", "SKU-9", -1);
~~~

should be **meaningfully rejected**, not turned into a “service timeout”.

Two ways to test:

| Configuration | Assertion |
|---|---|
| Handler throws typed invalid request | Gateway/caller receives an exception carrying `INVALID_QUANTITY` or a wrapper with that cause |
| Flow produces typed `QuoteRejected` | Gateway returns the appropriate decision/result |
| Filter silently discards | Test catches the design flaw via missing reply / timeout |

In the `QuoteCalculator` example in Section 6, `IllegalArgumentException("INVALID_QUANTITY")` is illustrative only. Production should use a **typed exception / reasonCode** and explicit mapping across the application boundary, HTTP responses, logs, and broker recovery.

Do not enable a retry policy for every `IllegalArgumentException` expecting a negative quantity to magically become valid on the next attempt.

## 35. Testing Async Errors Without Mistaking Them for Synchronous Ones

A flow:

~~~text
Gateway → ExecutorChannel → Service Activator
                         → throws on worker
                         → ErrorMessage / recoverer
~~~

Tests should verify:

- Exceptions surface at the configured worker/error boundary.
- Do not assume `gatewayMethod()` directly throws the worker's cause when no error reply is wired.
- If the Gateway defines a reply timeout, it enforces the corresponding timeout/pending contract.
- The error handler preserves the logical request ID/correlation for status lookup or compensating outcomes.
- Side-effecting commands are not ACKed before becoming durable merely because an executor accepted the task.

**Exception paths on a `DirectChannel` are not identical to an `ExecutorChannel`.** A test that only exercises a synchronous flow is insufficient to prove error channels, transaction contexts, and retry semantics of an asynchronous flow.

## 36. Testing Header Loss Across Brokers and Preserving Identity

Suppose a Transformer rebuilds a message or a broker adapter drops custom headers. A contract test needs to ensure:

~~~text
commandId=C-901 (payload)
tenantId=verified tenant context
businessCorrelationId=tenant-a|O-901
reply-to=transport-defined return destination
~~~

Losing the in-JVM `replyChannel` object across a process boundary does not automatically kill reply capability: **protocol-level outbound/inbound gateways must map reply-to and correlation** properly. Sending a bare payload over a broker without that protocol, however, will cause the caller to time out.

Verify:

1. Allowed headers are serializable and allowlisted.
2. Logical command IDs remain stable across retries and message rebuilds.
3. Replies correlate to the exact request, not merely an unscoped productId/orderId.
4. Invalid headers or tenant claims are rejected.
5. Late replies have a cleanup path and do not leak entries in the pending-reply registry.
6. New Spring message IDs **never replace** business idempotency keys.

Do not pass raw `replyChannel`/`errorChannel` objects across an external trust boundary as a mandatory compatibility requirement.

## 37. Security Boundary: Preventing Write Commands Through an Open Gateway

An application Gateway method `place()` is a side-effecting entry point. Risks include:

- An HTTP caller spoofing a tenant or role.
- A broker producer sending the wrong operation onto an allowed channel.
- Clients injecting an internal `verifiedTenantId` header themselves.
- A Router choosing flows from user-supplied method names or SpEL expressions.
- A message sent to another service carrying spoofed `replyChannel`/`errorChannel` headers.
- Logs or error replies accidentally leaking raw payment data or PII.

Mitigations:

- Authenticate at the ingress adapter.
- Enforce domain authorization inside the command-handling service.
- Route solely through an **operation/channel allowlist**, never arbitrary reflection.
- Keep tokens/credentials out of business DTOs when unneeded, and avoid logging them.
- Re-verify identity when crossing broker or service boundaries.
- Enforce quotas, max payload sizes, timeouts, and allowed schema versions.

**Never use `@MessagingGateway` as a security mechanism.** The annotation only declares how to enter a message flow; it does not decide who is permitted to call `place()`.

## 38. Observability: Gateway Invocation vs. Business Completion

To distinguish proxy activity from business completion, track:

| Suggested metric | Meaning |
|---|---|
| `gateway.requests.count` | Total caller invocations |
| `gateway.request.send.failure.count` | Failed request sends |
| `gateway.reply.received.count` | Replies matching contract |
| `gateway.reply.timeout.count` | Requests missing a reply within deadline |
| `gateway.reply.late.count` | Replies arriving after caller timeout |
| `gateway.error.received.count` | Errors mapped back to caller |
| `gateway.calls.duration` | Caller-visible latency |
| `flow.command.accepted.count` | Durably accepted intents |
| `flow.command.committed.count` | Business commits |
| `flow.command.duplicate.count` | Logical duplicates |
| `flow.command.unknown.outcome.count` | Unverified remote statuses |
| `flow.aggregate.pending.count` | Groups waiting on children |
| `flow.aggregate.expired.count` | Expired groups |
| `flow.outbox.pending.count` | Events waiting to publish |

These are **suggested metrics**, not Spring Integration's default meter list. Keep tag cardinality low (`gatewayMethod`, `flowName`, `outcome`, `reasonCode`, `operation`). **Never put commandId, eventId, traceId, email, or raw payloads into metric labels.**

Access-controlled structured logs/traces:

~~~text
gatewayMethod=place
commandId=C-901
operation=PLACE
requestAccepted=true
replyOutcome=TIMEOUT
businessOutcome=PENDING
correlationId=tenant-a|O-901
elapsedMillis=3000
~~~

When the operation finishes later, another log/event:

~~~text
commandId=C-901
businessOutcome=SUCCEEDED
transactionOutcome=COMMITTED
replayedMessage=false
~~~

**Do not increment an “order failed” metric whenever a Gateway reply times out.** A timeout only states the caller received no response before its deadline; it does not prove the domain operation failed.

## 39. Method Arguments and Headers: Only Pass Necessary Metadata Across the Boundary

A Gateway can map the payload and select method arguments into headers. Illustrative example:

~~~java
@MessagingGateway
interface TenantQuoteGateway {

    @Gateway(requestChannel = "orders.quote.requests")
    QuoteResult quote(
        @Payload QuoteRequest request,
        @Header("sourceApp") String sourceApp);
}
~~~

`@Payload` designates the payload; `@Header` attaches a metadata field to the message. Still, **having a header does not prove the value is trustworthy**. If the caller is an HTTP controller, it must verify `sourceApp` or derive it from authenticated identity rather than copying raw headers straight from the HTTP client.

Practical rules:

- Place **required business IDs** inside the DTO/wire contract when they must survive brokers or restarts.
- Place **transient technical context** like tracing hints or source application in allowlisted headers.
- Do not embed framework `replyChannel`/`errorChannel` in domain DTOs.
- Do not pass raw security tokens in headers that may be copied across multiple services.
- When a service needs authorization, rely on verified identity established at the trust boundary.

If an interface accumulates too many technical `@Header` arguments, consider wrapping it in an **adapter** that keeps framework details hidden and exposes a single business-friendly method to application code.

## 40. When to Use a Messaging Gateway vs. Just Sending a Message?

| Goal | Usually suitable choice |
|---|---|
Java application needs to invoke a flow and receive a typed result | `@MessagingGateway` request–reply |
| Java application needs to emit a one-way event | `void` Gateway or channel-sending adapter with a durable delivery policy |
| External HTTP client calls an API | Controller + Gateway or HTTP inbound gateway |
| Flow calls external HTTP and waits for response | HTTP outbound gateway |
| Flow publishes an event to a broker without a business response | Outbound channel adapter / publisher |
| Work runs for minutes | Durable command queue + status/events instead of forcing a synchronous reply |
| Flow has Splitter/Aggregator producing one combined result | Gateway with clear correlation/release/deadline |
| Simple batch processor merely feeding a flow | Using `MessageChannel` inside an integration adapter can suffice if a Gateway proxy adds no value |

**A Gateway is not always required.** When an application port is already simple and there is no real message flow, calling the business service directly can be clearer. Do not force business code through a Gateway merely to inflate endpoint counts.

Conversely, when a flow involves Routers, Transformers, error channels, and adapters, a Gateway keeps application callers **decoupled from topology** and makes tests and application contracts clearer.

## 41. Contract Evolution: Keeping the Port Stable When the Flow Changes

Suppose you start with:

~~~text
QuoteGateway.quote()
  → QuoteCalculator
  → QuoteResult
~~~

And later expand to:

~~~text
QuoteGateway.quote()
  → validate
  → enrich product catalog
  → route regional pricing
  → split price/discount/tax
  → aggregate
  → QuoteResult
~~~

As long as the same **input/output semantics and latency contract** hold, application code may not need any changes. That is the payoff of a solid boundary.

However, some changes should not be hidden:

- The new flow takes 30 seconds instead of 30 ms.
- The result is now only `PENDING` instead of the final price.
- Currency semantics change from gross to net.
- A previously read-only Gateway now performs side effects.
- The method begins throwing a new class of failures that callers must handle.
- Commands are durably accepted, but final completion shifts to an event callback.

Those are **application contract changes**. Version DTOs/APIs and roll out intentionally rather than tweaking the flow and trusting the Gateway annotation to keep everything compatible.

## 42. Runbook: Gateway Timed Out and You Do Not Know Whether Business Work Finished

An investigation procedure:

1. **Identify method and operation:** `quote()` (read-only) or `place()` (side effect)?
2. **Identify logical IDs:** commandId, tenant, orderId, and request/correlation scope.
3. **Check request send:** did the message enter the request channel/queue, or fail due to capacity/timeout?
4. **Check the flow:** did a Filter discard it, a Router pick the wrong branch, or a Transformer fail?
5. **Check the Service Activator:** did the handler start, finish, commit, or throw?
6. **Check the transaction:** did inbox, domain rows, and outbox commit together?
7. **Check the error boundary:** did exceptions propagate to the caller or go to an error channel/container?
8. **Check reply correlation:** is the return address still valid, reply-to correct, or did a reply arrive late?
9. **Check Splitter/Aggregator:** is a child missing, a member duplicated, or did the group expire?
10. **Check external services:** could the timeout leave a remote outcome unknown?
11. **Reconcile durable outcome:** is the operation SUCCEEDED, FAILED, PENDING, or UNKNOWN_OUTCOME?
12. **Decide on retry:** keep the **same commandId** for the same logical work; reconcile first if remote effects are uncertain.
13. **Remediate and add regression tests:** add fault-injection tests covering the exact failure window, metrics, and status reply policy.

**Never blindly delete idempotency markers and replay in bulk** before checking committed side effects. A Gateway reply error does not prove the handler failed.

## 43. End-to-End Testing Matrix for the Gateway Boundary

| Scenario | Fault/input | Expectation |
|---|---|---|
| Typed query | Valid `QuoteRequest` | `QuoteResult` of expected type/value |
| Typed command | Valid `PlaceOrderCommand` | `OrderPlaced` or matching decision |
| Wrong payload type | Incompatible schema | Rejected, wrong handler not called |
| Missing required field | `quantity=-1` | Validation error, not silent timeout |
| Filter discard | False predicate | Detects missing error reply if contract requires one |
| Gateway request cannot send | Queue capacity/dispatch failure | Clear send error, never reports business success |
| Gateway no reply | Handler returns void/null or child drops | Reply timeout per contract |
| Synchronous handler error | Exception on DirectChannel | Cause/reasonCode reaches caller |
| Asynchronous handler error | Exception on ExecutorChannel | Error channel/recoverer and durable status behave properly |
| Two concurrent requests | Out-of-order replies | Callers receive their matching replies |
| Broker header mapping | Translated reply-to/correlation | No swapped replies or dropped metadata |
| Caller timeout before commit | Worker keeps running | Does not report definite failure |
| Retry same command | Same commandId and fingerprint | No duplicate business effect |
| Same ID, changed payload | Fingerprint mismatch | Conflict/reject |
| Crash after commit before reply | Redelivery/retry | Cached result, no second order created |
| Remote HTTP timeout after commit | Outcome unknown | Reconcile / reuse same remote key |
| Splitter child missing | Aggregator missing member | Proper failure/timeout/pending, no fake partial success |
| Duplicate child outcome | Two replies for one member | Does not hit fake expected count |
| Late reply | Caller already timed out | Triggers no new side effects |
| DLQ/recovery unavailable | Failed command cannot be persisted | Does not ACK and lose work |
| Unauthorized tenant | Spoofed header/payload | Rejected before business write |
| Schema evolution | New flow with unchanged contract | Caller needs no edits |
| Breaking contract | Result shifts to async pending | Intentional API migration |

**Do not only assert that `Gateway.quote()` returns an object.** For commands, assert **database row counts, outbox records, external-provider call counts, status transitions, and retry duplicate behavior**. For async flows, test actual error channel/container recovery rather than just unit testing Java methods.

## 44. Common Misconceptions

**“Messaging Gateway is just another name for Service Activator.”** No. A Gateway lets application code call into a flow; a Service Activator invokes a service from an incoming message.

**“Having `@MessagingGateway` means you do not need validation/authorization.”** False. The annotation only configures the messaging boundary; it grants no permissions and validates no input.

**“The Gateway returning an object proves the transaction committed.”** Only when the handler and contract genuinely guarantee that commit point.

**“A reply timeout means the operation was cancelled.”** No. Workers can keep running and commit.

**“The Gateway timeout is the deadline for every service in the flow.”** Not by default. Request, reply, broker, and business deadlines are distinct.

**“A `void` Gateway means downstream side effects have finished.”** Not with async queues/executors or non-durable delivery.

**“When a Filter drops input, the Gateway automatically generates a validation reply.”** No. The caller may time out.

**“An `ErrorMessage` in `errorChannel` means the caller was notified.”** No. You need an explicit error reply or status protocol.

**“A Gateway automatically retries every error safely.”** No. Retry policies must account for side effects, idempotency, and failure classification.

**“Generate a new `commandId` on every retry to ensure delivery.”** On the contrary, doing so can create duplicate business operations.

**“`ReplyChannel` is a business correlation ID.”** No. It is an invocation return address.

**“Spring Message IDs survive broker redelivery.”** Never assume that.

**“With Splitter/Aggregator, the Gateway always gets one result.”** Not when children go missing, expire, duplicate, or release policies are wrong.

**“Synchronous tests guarantee async error handling works.”** No. Thread, transaction, and error boundaries differ.

**“A JDBC transaction rolls back an already captured HTTP payment.”** No. External side effects require remote idempotency and reconciliation.

**“An inbound gateway and a Java `@MessagingGateway` are the same endpoint.”** No. One is a transport-facing adapter; the other is an application interface proxy.

**“A gateway interface hides every breaking change behind it.”** Not when semantics, latency, or outcome contracts change.

**“Forwarding all HTTP headers into the message preserves full context.”** Doing so can leak secrets and inject untrusted values into routing or authorization.

## 45. Hands-On Exercise: From Channel-Calling Controller to Application Port

Build the **CheckoutMessagingBoundary** mini project:

1. Define `QuoteRequest`, `QuoteResult`, `PlaceOrderCommand`, and `PlaceOrderDecision`.
2. Create `QuoteGateway` with `@MessagingGateway(defaultRequestChannel=...)`.
3. Wire an `IntegrationFlow.from(...).handle(QuoteCalculator)` producing a typed reply.
4. Write `CheckoutApplicationService` depending solely on an application port.
5. Unit test with a fake port: **no Spring context or `MessageChannel` required**.
6. Integration test the Gateway proxy: verify requests reach the handler and return the right DTO.
7. Add a Filter rejecting negative quantities; ensure callers receive a meaningful error rather than only a reply timeout.
8. Create `PlaceOrderGateway` and a transactional handler with inbox + order + outbox.
9. Test duplicate commands and same-key/different-payload conflicts.
10. Inject a crash after commit before reply; verify retrying the same `commandId` does not create a second order.
11. Insert an `ExecutorChannel`; observe errors belonging to the worker/error boundary rather than the caller thread.
12. Create a request fanning out 3 children via Splitter/Aggregator.
13. Inject a failure in one child; define explicit failure outcomes and group expiry behavior.
14. Test concurrent requests with out-of-order replies and a late reply.
15. Add an HTTP controller or HTTP inbound gateway, mapping validation/timeouts to appropriate HTTP responses.
16. Exercise an outbound gateway reading external data, simulating HTTP 503 and timeouts.
17. Record dashboard metrics separating gateway timeouts from business committed/error metrics.
18. Swap the internal topology while preserving the synchronous quote API; document where versioning is needed when migrating to async pending.

**Completion criteria:** application code calls **methods + DTOs** with no awareness of `replyChannel`, internal channels, or broker records; Gateway correlation never mixes callers; timeouts are not treated as definite business failures; write commands are idempotent; sync/async errors are handled properly; new flows do not break caller contracts when semantics remain intact.

## 46. Takeaways

**Messaging Gateway is the boundary between application code and message flows.** It lets controllers and use cases invoke **typed Java interfaces** while Spring Integration wraps requests into messages, routes them through Router/Filter/Transformer/Service Activator pipelines, and returns replies to callers. A Gateway **reduces coupling to topology** without removing request–reply rules, error handling, or business semantics.

Distinguish **Java `@MessagingGateway` proxies** from **protocol inbound/outbound gateways**. Keep application ports explicit around **queries, commands, and expected outcomes**. Never confuse `replyChannel` with business correlation, `MessageHeaders.ID` with an idempotency key, or a Gateway timeout with transaction rollback.

For distributed or fan-out request–reply flows, establish **correlation, reply-to addresses, deadlines, retry/error channels, and late-reply policies**. For side-effecting commands, combine **durable inboxes, transactions, outboxes, remote idempotency, and reconciliation**. Test at the application port, Spring Integration flow, and transport boundary so your Gateway genuinely decouples the application from messaging **without hiding errors or creating duplicate side effects**.

### References

- Enterprise Integration Patterns, **Messaging Gateway**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Spring Integration Reference, **Messaging Gateways**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **Service Activator**: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Integration Reference, **HTTP Support**: https://docs.spring.io/spring-integration/reference/http.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Idempotent Receiver**: https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
- Spring Framework Reference, **Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html

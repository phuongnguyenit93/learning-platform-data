# Encapsulating Remote Calls as Messages

## 1. Problem: Application Code Calling a Remote Service

In an e-commerce system, Checkout needs to ask Inventory to **reserve stock** for an order. If Checkout calls an HTTP client directly, business code may have to know the URL, headers, timeout, request/response format, and how to handle retries:

~~~java
// Example intentionally coupling application code with transport.
StockReservationResult reserve(ReserveStockCommand command) {
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.set("Idempotency-Key", command.operationId());

    ResponseEntity<StockReservationHttpResponse> response =
        restTemplate.exchange(
            inventoryUrl + "/reservations",
            HttpMethod.POST,
            new HttpEntity<>(toHttpRequest(command), headers),
            StockReservationHttpResponse.class);

    return toDomainResult(response.getBody());
}
~~~

The issue is not that HTTP clients are bad. The issue is that **the business use case is forced to depend on how the remote call is made**: which endpoint, which headers, how to retry on connection loss, and how to return errors. If Inventory later moves to broker request–reply, we would have to change multiple layers without a boundary.

**Encapsulating remote calls as messages** means using a **request message**, a **request–reply contract** (when a result is needed), and endpoints/adapters to hide remote call details from application code:

~~~mermaid
flowchart LR
    A["Checkout use case"] --> PORT["Inventory port / Gateway"]
    PORT --> REQ["Command message"]
    REQ --> OUT["Outbound gateway/adapter"]
    OUT --> REM["Remote Inventory service"]
    REM --> OUT
    OUT --> RESP["Reply message"]
    RESP --> PORT
    PORT --> A
~~~

The application calls:

~~~java
StockReservationResult result = inventoryPort.reserve(command);
~~~

Inside, an integration flow can create the message, route, transform, send to the remote service, receive the response, classify errors, and return the application data type. **A Gateway turns an RPC-style call into a messaging boundary; it does not turn a remote call into a true local call.** Latency, availability, timeouts, duplicate delivery, and partial failures still exist.

This lesson belongs to the **Remote procedure invocation** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module teaches implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, scalable message flows; practicing **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and observing processing branches.

After this lesson, you will design typed remote-call APIs, convert commands into request messages, configure a Spring Integration Gateway + HTTP outbound gateway, preserve correlation across transport, classify timeouts/retries/error channels, and test so that remote side effects are not duplicated on network failures.

## 2. Remote Procedure Invocation and Messaging Are Two Different Perspectives

**Remote Procedure Invocation (RPI/RPC)** lets the caller use an operation like calling a method:

~~~text
reserveStock(orderId, sku, quantity) → reservationResult
~~~

**Messaging** expresses the exchange as an independent message with a payload and metadata:

~~~text
Request message:
  operation = RESERVE_STOCK
  operationId = RES-901
  orderId = O-901
  sku = SKU-7
  quantity = 2

Reply message:
  operationId = RES-901
  status = RESERVED
  reservationId = RSV-555
~~~

Spring Integration lets you place **a Gateway at the application boundary** so code calls a method while the integration layer uses messages and endpoints.

**Mindset to keep:** a remote call can fail in many places where a local call cannot: request not sent, sent but not yet processed by the server, server committed but reply lost, reply arrives late, or client timed out. You cannot deduce the remote outcome solely from a Java exception.

## 3. What Risks Differ Between Local and Remote Calls?

| Aspect | In-Process Method | Remote Call |
|---|---|---|
| Duration | Usually very low | Includes network, queueing, service latency |
| Process failure | Usually same JVM/process | Caller and receiver fail independently |
| Transaction | Can share transaction manager | Usually separate transaction boundaries |
| Return value | Received directly | Reply may be lost even if server committed |
| Exception | Usually from running code | Includes transport, protocol, timeouts, remote errors |
| Identity | Object/method context | Needs serialized business IDs and correlation |
| Retry | Can re-invoke method | Risks duplicate side effects |
| Security | Internal invocation context | Requires authentication, authorization, TLS, credentials |
| Versioning | Same binary/deployment can stay in sync | Caller/receiver deploy independently |

**Do not build a "distributed object" assuming a remote endpoint is always cheap, fast, and reliable like a local method.** No matter how clean the API is, it must declare timeout, failure classification, and idempotency semantics.

## 4. Messagifying a Call: From Method Signature to Contract

For the stock reservation operation, define the Java contract:

~~~java
record ReserveStockCommand(
    String tenantId,
    String operationId,
    String orderId,
    String sku,
    int quantity
) {}

record StockReservationResult(
    String operationId,
    String orderId,
    String reservationId,
    ReservationStatus status
) {}

enum ReservationStatus {
    RESERVED,
    REJECTED_OUT_OF_STOCK,
    PENDING
}
~~~

**Design points:**

- `operationId` identifies **one logical stock reservation request** across retries/redeliveries, not the ID of an HTTP attempt.
- `tenantId` is business scope information that must be verified against a trusted identity; do not blindly trust a self-declared client value.
- `orderId`, `sku`, and `quantity` describe the operation.
- `ReservationStatus` represents the **business outcome**, distinct from HTTP statuses 200/409/503.
- `PENDING` is only valid when the backend has accepted a durable intent or provides status lookup/reconciliation—not a label to mask a network failure.

If an order has multiple lines with the same SKU, the operation ID must be scoped finely enough to distinguish **each reservation member**. For example, `tenant + orderId + operation + lineId` can be the business key; do not use one shared ID for all children when the receiver deduplicates by key.

## 5. Application Port: Typed Method Without HTTP Dependency

A pure Java interface:

~~~java
public interface InventoryReservationPort {
    StockReservationResult reserve(ReserveStockCommand command);
}
~~~

Checkout only depends on the port:

~~~java
@Service
class CheckoutUseCase {
    private final InventoryReservationPort inventory;

    CheckoutUseCase(InventoryReservationPort inventory) {
        this.inventory = inventory;
    }

    StockReservationResult reserveForOrder(
            ReserveStockCommand command) {
        validateUseCase(command);
        return inventory.reserve(command);
    }

    private void validateUseCase(ReserveStockCommand command) {
        // Validation & authorization per application contract.
    }
}
~~~

With Spring Integration, we can create a **Gateway proxy** behind this interface or have a Java adapter implement the port and delegate to the Gateway. Thus application code does not need to know `Message<?>`, `MessageChannel`, HTTP status, or broker records.

This is **Ports and Adapters**, not a mandatory rule to add extra interfaces in every project. The biggest benefits appear when switching transports/flows, unit testing use cases independently, or having multiple callers share the same business contract.

## 6. Messaging Gateway Interface Receiving DTOs from Application Code

A Spring Integration Gateway:

~~~java
@MessagingGateway(
    defaultRequestChannel = "inventory.reserve.requests")
interface InventoryReservationGateway {
    StockReservationResult reserve(ReserveStockCommand command);
}
~~~

An adapter can be declared:

~~~java
@Component
class MessagingInventoryAdapter
        implements InventoryReservationPort {
    private final InventoryReservationGateway gateway;

    MessagingInventoryAdapter(InventoryReservationGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public StockReservationResult reserve(
            ReserveStockCommand command) {
        return gateway.reserve(command);
    }
}
~~~

Register component scan / bean scanning for annotated gateways per project setup, for example:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class IntegrationConfiguration {
}
~~~

`@MessagingGateway` creates **a proxy that turns a Java call into a message sent to a request channel**. It does not call remote Inventory on its own; the flow behind it must have a real endpoint/adapter. Spring Integration supports several ways to register Gateways; check the exact version and component scanning in your application.

## 7. Essential Components for a Remote Request–Reply

~~~text
Application
  → Gateway interface
  → request channel
  → Validate/Transform internal command
  → HTTP outbound gateway (or broker request–reply)
  → Remote receiver
  ← response from receiver
  → Transform remote response into domain result
  → Gateway reply
  → Application
~~~

| Component | Function |
|---|---|
| **Gateway interface** | Typed Java boundary |
| **Request channel** | Feeds the call into the integration flow |
| **Request Transformer** | Converts domain DTO → remote/wire DTO |
| **Outbound gateway** | Executes remote call and receives response |
| **Reply Transformer** | Converts response → application result |
| **Reply channel/address** | Returns result to the exact waiting call |
| **Error handler** | Classifies input/transport/remote/business errors |
| **Correlation + idempotency IDs** | Matches reply to request; prevents duplicate side effects |

**Gateway and Message Translator do not have overlapping roles.** The Gateway lets callers invoke the flow as a method, while the Translator/Transformer determines payload types and semantics. The outbound gateway handles request–reply transport.

## 8. Internal DTO Differs from the Remote API's Wire DTO

A remote Inventory API may accept JSON:

~~~json
{
  "requestId": "RES-901",
  "orderRef": "O-901",
  "productCode": "SKU-7",
  "units": 2
}
~~~

and return:

~~~json
{
  "requestId": "RES-901",
  "orderRef": "O-901",
  "result": "RESERVED",
  "reservationRef": "RSV-555"
}
~~~

Do not force `CheckoutUseCase` to use `productCode`, `units`, or `reservationRef` directly if the domain agreed on `sku`, `quantity`, and `reservationId`. Create DTOs in the integration adapter:

~~~java
record StockReservationHttpRequest(
    String requestId,
    String orderRef,
    String productCode,
    int units
) {}

record StockReservationHttpResponse(
    String requestId,
    String orderRef,
    String result,
    String reservationRef
) {}
~~~

**The wire DTO is a contract with the remote service**, which can change independently of the domain DTO. The Transformer must validate required fields, enums, numeric ranges, conversions, and response correlation; do not simply cast JSON to an object and return it directly.

## 9. Request Transformer: Packaging the Call into a Wire Payload

A pure mapper:

~~~java
@Component
class ReservationRequestMapper {

    StockReservationHttpRequest toHttpRequest(
            ReserveStockCommand command) {
        if (command == null
                || command.operationId() == null
                || command.operationId().isBlank()
                || command.orderId() == null
                || command.orderId().isBlank()
                || command.sku() == null
                || command.sku().isBlank()
                || command.quantity() <= 0) {
            throw new InvalidReservationCommandException(
                "INVALID_RESERVATION_COMMAND");
        }

        return new StockReservationHttpRequest(
            command.operationId(),
            command.orderId(),
            command.sku(),
            command.quantity());
    }
}
~~~

`InvalidReservationCommandException` is an application exception we define; it is not a default Spring Integration class. This mapper **makes no HTTP calls, writes no DB records, and produces no side effects**. As a result, retry/validation can re-run it without causing business changes.

In practice, you must also validate `tenantId` against a trusted principal, bound payload size, ensure operation ID uniqueness, and check canonical fingerprints when the same key is sent with different content.

## 10. Header Contract: What Metadata Travels with the Request?

A Spring message has a payload and headers:

~~~text
payload = StockReservationHttpRequest
headers:
  operationId = RES-901
  businessCorrelationId = tenant-a|O-901|inventory
  verifiedTenantId = tenant-a
  traceparent = <trace context>
  replyChannel = <temporary return address>
~~~

Different metadata groups:

- **Business IDs:** `operationId`, `orderId`, correlation key; must remain stable across retries.
- **Trust/security context:** verified tenant, credentials/tracing; has clear origin and lifetime.
- **Transport headers:** HTTP `Content-Type`, `Idempotency-Key`, reply-to/Correlation ID when required by a broker.
- **Framework headers:** Spring `replyChannel`, `errorChannel`, and `MessageHeaders.ID`; do not blindly send these out externally.

Do not copy **every HTTP header from the client** into Spring headers and let Routers/Gateways use them arbitrarily. Only carry whitelisted, validated fields valid under the contract.

## 11. Idempotency-Key Is Not correlationId

A request needs at least two kinds of identification when a remote operation has side effects:

~~~text
operationId = RES-901
    → remote idempotency key to re-handle one logical reservation.

requestCorrelationId = INVOKE-ATTEMPT-3
    → pairs one transport request/attempt with its corresponding reply.
~~~

A retry may use a **different request correlation** but must keep the **same operationId**. If the receiver gets the same idempotency key + same canonical payload, it can return the **cached result** or in-progress status without creating a second reservation.

If same key but different payload:

~~~text
RES-901, sku=SKU-7, quantity=2
RES-901, sku=SKU-7, quantity=200
~~~

the receiver must enforce a **fingerprint conflict policy**; never silently reuse the old result or create a new reservation. Transport correlation helps match the right reply; it does not replace business operation idempotency checks.

## 12. Synchronous Gateway Enables Remote Calls, But Does Not Make Remote Local

In a synchronous flow:

~~~mermaid
sequenceDiagram
    participant App as Checkout
    participant G as Messaging Gateway
    participant Flow as IntegrationFlow
    participant Rem as Remote Inventory
    App->>G: reserve(RES-901)
    G->>Flow: ReserveStockCommand message
    Flow->>Flow: Validate + toHttpRequest
    Flow->>Rem: HTTP POST /reservations
    Rem-->>Flow: RESERVED / RSV-555
    Flow->>Flow: toDomainResult
    Flow-->>G: StockReservationResult
    G-->>App: RESERVED
~~~

At the caller, the syntax looks simple:

~~~java
StockReservationResult result = gateway.reserve(command);
~~~

Yet the method can:

- Block on the network.
- Time out on request/send/reply.
- Receive 4xx/5xx or a remote business rejection.
- Miss the reply even though the receiver committed.
- Fail due to a circuit breaker or quota.

**API design must explicitly state latency, exceptions, retry semantics, and possible unknown outcomes.** Do not pass `null` as an "uncertain" result if the caller expects a meaningful result.

## 13. HTTP Outbound Gateway: Spring Integration's Request–Reply Adapter

Spring Integration provides an HTTP outbound gateway to turn a message from a flow into an HTTP request and receive the HTTP response as a reply. Illustrative Java DSL form:

~~~java
@Bean
IntegrationFlow inventoryHttpFlow() {
    return IntegrationFlow
        .from("inventory.http.requests")
        .handle(
            Http.outboundGateway(
                    "https://inventory.internal.example/reservations")
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(
                    StockReservationHttpResponse.class))
        .channel("inventory.http.replies")
        .get();
}
~~~

This is an **illustrative structure**, not a complete application. You need to configure the HTTP client, serialization/conversion (JSON), timeouts, authentication, TLS, header mapping, and error handling according to your Spring Integration version. The address `inventory.internal.example` is a placeholder, **not a real service**.

**Important:** An HTTP outbound gateway has a request–reply contract; a one-way HTTP outbound channel adapter has a different contract. An HTTP POST returning 202 only indicates **the request was accepted under remote API semantics**; it does not prove Inventory finished reserving stock if the server processes asynchronously.

## 14. Composing Gateway, Transformer, and HTTP Outbound Gateway into a Flow

A complete conceptual flow:

~~~mermaid
flowchart LR
    P["InventoryReservationPort"] --> G["@MessagingGateway"]
    G --> V["Validate command"]
    V --> T1["Request Transformer"]
    T1 --> H["HTTP outbound gateway"]
    H --> R["Remote Inventory API"]
    R --> H
    H --> T2["Reply Transformer"]
    T2 --> G
~~~

Java DSL for the **happy path**:

~~~java
@Configuration
@EnableIntegration
class InventoryRemoteFlowConfiguration {

    @Bean
    IntegrationFlow reserveRemoteInventory(
            ReservationRequestMapper requestMapper,
            ReservationReplyMapper replyMapper) {
        return IntegrationFlow
            .from("inventory.reserve.requests")
            .transform(
                ReserveStockCommand.class,
                requestMapper::toHttpRequest)
            .handle(
                Http.outboundGateway(
                        "https://inventory.internal.example/reservations")
                    .httpMethod(HttpMethod.POST)
                    .expectedResponseType(
                        StockReservationHttpResponse.class))
            .transform(
                StockReservationHttpResponse.class,
                replyMapper::toResult)
            .get();
    }
}
~~~

`ReservationReplyMapper` is an application service, shown in section 15. The flow does three things: **convert domain command to remote DTO → send request/receive response → convert reply to domain result**.

For production, you must add **a compatible REST client and JSON converter, authentication, HTTP timeouts, idempotency header mapping, status/error mapping, rate limiting, circuit breaker, and tracing**. The example omits them to separate the EIP structure from version/adapter configuration details.

**Do not register both this flow and the flow in section 13 consuming the same input channel** unless competing-consumer distribution is intentional. Section 13 shows the outbound gateway alone; section 14 shows composing it into an end-to-end flow.

## 15. Reply Transformer Must Not Treat Every HTTP 2xx as Business Success

A response:

~~~json
{
  "requestId": "RES-901",
  "result": "REJECTED_OUT_OF_STOCK",
  "reservationRef": null
}
~~~

HTTP 200 here can carry a **valid business rejection**. Conversely, an HTTP 202 response may only represent **PENDING**.

Mapper:

~~~java
@Component
class ReservationReplyMapper {

    StockReservationResult toResult(
            StockReservationHttpResponse reply) {
        if (reply == null
                || reply.requestId() == null
                || reply.requestId().isBlank()
                || reply.orderRef() == null
                || reply.orderRef().isBlank()
                || reply.result() == null) {
            throw new RemoteProtocolException(
                "INVALID_REMOTE_RESPONSE");
        }

        ReservationStatus status;
        try {
            status = ReservationStatus.valueOf(reply.result());
        } catch (IllegalArgumentException invalidStatus) {
            throw new RemoteProtocolException(
                "UNKNOWN_REMOTE_STATUS");
        }

        if (status == ReservationStatus.RESERVED
                && (reply.reservationRef() == null
                    || reply.reservationRef().isBlank())) {
            throw new RemoteProtocolException(
                "MISSING_RESERVATION_ID");
        }

        return new StockReservationResult(
            reply.requestId(),
            reply.orderRef(),
            reply.reservationRef(),
            status);
    }
}
~~~

`RemoteProtocolException` is an application exception, not built into Spring Integration. The example remote reply includes `orderRef` to build a complete domain result; if a real API does not echo `orderRef`, retrieve that information from a trusted request context instead of guessing.

**In real implementations:** keep `orderId`/`operationId` from the request in a verified message envelope/header or require the remote service to echo the necessary fields, and **verify that `response.requestId` matches the request's `operationId`**. If they do not match, that is a **correlation/protocol failure**; do not return another request's data.

## 16. Preserving Request Context to Build a Complete Domain Reply

An application context type:

~~~java
record ReservationCallContext(
    String tenantId,
    String operationId,
    String orderId
) {}
~~~

`ReservationCallContext` can be stored in internal headers before the outbound gateway, or persisted as correlation state keyed by request ID if request–reply crosses a broker/process boundary.

A mapper checking correlation:

~~~java
StockReservationResult mapCheckedReply(
        StockReservationHttpResponse reply,
        ReservationCallContext expected) {
    if (reply == null || expected == null
            || !expected.operationId().equals(reply.requestId())
            || !expected.orderId().equals(reply.orderRef())) {
        throw new RemoteProtocolException(
            "REMOTE_CORRELATION_MISMATCH");
    }

    ReservationStatus status;
    try {
        status = ReservationStatus.valueOf(reply.result());
    } catch (RuntimeException invalidStatus) {
        throw new RemoteProtocolException(
            "UNKNOWN_REMOTE_STATUS");
    }
    if (status == ReservationStatus.RESERVED
            && (reply.reservationRef() == null
                || reply.reservationRef().isBlank())) {
        throw new RemoteProtocolException(
            "MISSING_RESERVATION_ID");
    }

    return new StockReservationResult(
        expected.operationId(),
        expected.orderId(),
        reply.reservationRef(),
        status);
}
~~~

This helper illustrates **the correlation rule**. In Spring Integration, choose the right place to attach/persist context; a local header may not survive after the message crosses an external transport or is rebuilt by an adapter. For one-way fire-and-forget, there is no reply so the same mapping does not apply.

Do not take `orderId` from another remote field and trust it blindly, because a response can be misaligned with the request, returned erroneously by the server, or altered by an intermediary.

## 17. Mapping Idempotency-Key from the Business Operation

The remote Inventory API should support a stable key:

~~~http
POST /reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: RES-901

{"requestId":"RES-901","orderRef":"O-901","productCode":"SKU-7","units":2}
~~~

**There is no universal HTTP standard forcing every service to understand `Idempotency-Key`**. It is an agreement with the remote API: key scope, retention, response replay, concurrent requests, and conflict behavior must be documented.

An idea to enrich a header **before transforming the payload**:

~~~java
.enrichHeaders(h -> h.headerFunction(
    "remoteIdempotencyKey",
    m -> ((ReserveStockCommand) m.getPayload()).operationId()))
.transform(
    ReserveStockCommand.class,
    requestMapper::toHttpRequest)
~~~

This is a Java DSL fragment, not a standalone flow. Afterward, the HTTP outbound gateway needs an **appropriate mapper** to turn the internal header `remoteIdempotencyKey` into the wire header `Idempotency-Key`. Do not assume every custom Spring header is forwarded automatically by the HTTP outbound adapter.

**Always preserve the key when retrying the same logical operation.** If you resend with a new key after a timeout, the remote service may create a second reservation. Likewise, do not share one key across independent line items.

## 18. Classification Table of Remote Call Outcomes

| Observed at caller | What is actually known | Potentially appropriate action |
|---|---|---|
| HTTP 200 + valid `RESERVED` | Remote reports success | Verify correlation, store outcome |
| HTTP 200 + `REJECTED_OUT_OF_STOCK` | Terminal business rejection | Do not retry same input just because it rejected |
| HTTP 202 + accepted reference | Remote accepted per contract | Track pending/status |
| HTTP 400/422 | Remote considers input invalid | Validate, notify caller, do not hot-retry |
| HTTP 401/403 | Authn/authz rejected | Fix credentials/permissions, audit |
| HTTP 409 | May be conflict or duplicate depending on API | Check documented reason |
| HTTP 429 | Rate limited | Retry within budget/Retry-After when valid |
| HTTP 500/503 | Remote encountered an error | Bounded retry if operation is idempotent |
| Connect refused before send | Likely server never saw request | Can retry, needs proper classifier |
| Read timeout after send | **Outcome unknown** | Use same key, status lookup/reconciliation |
| Invalid reply body schema | Remote protocol incompatibility | Alert/quarantine, do not fake success |
| Correlation mismatch | Reply does not match request | Reject/safe recovery; do not deliver to wrong caller |

**Do not map every non-2xx to `ReservationStatus.REJECTED_OUT_OF_STOCK`.** Permission errors, network errors, contract mismatches, and business insufficient-stock differ in owner, retryability, and recovery responsibility.

HTTP status is not an independent business truth; follow the **specific contract of the remote API**. For instance, HTTP 409 might mean an idempotency conflict, not-found in some workflow, or in-progress state; never guess from status alone.

## 19. Timeout Does Not Prove the Remote Operation Rolled Back

A classic failure window:

~~~mermaid
sequenceDiagram
    participant C as Checkout/Gateway
    participant N as Network
    participant I as Remote Inventory
    C->>N: POST reserve(RES-901)
    N->>I: Request delivered
    I->>I: COMMIT reservation RSV-555
    I--xC: Reply lost / read timeout
    Note over C: UNKNOWN_OUTCOME
    C->>I: GET status by RES-901
    I-->>C: RESERVED, RSV-555
~~~

A Gateway timeout only means **the caller did not receive a reply within the deadline**, not that the remote side did not process it. If Checkout immediately POSTs again with a **new operationId**, there is a risk of reserving stock twice.

Handling approach:

1. Keep the original `operationId`.
2. If the remote supports idempotency, retry per the API contract with the **same key**.
3. If the response is uncertain, try a **status lookup by operationId** when available.
4. Persist a durable `UNKNOWN_OUTCOME/PENDING_RECONCILIATION` state.
5. Never emit a definite `RESERVED` or `REJECTED` solely from a timeout.

**Forbid the mindset "timeout = failure so we can call again as fresh."** This is especially dangerous for payments, refunds, resource cancellations, or sending notifications.

## 20. Send Timeout, Remote Timeout, and Reply Timeout Must Be Distinguished

A flow has multiple milestones:

~~~text
T0 Application calls Gateway.reserve()
T1 Gateway sends Message to request channel
T2 Worker begins processing
T3 HTTP client connects/sends
T4 Remote handler writes reservation
T5 HTTP response is read
T6 Reply Transformer returns domain result
T7 Gateway receives reply
~~~

The timeouts:

- **Request-channel/send timeout**: failed to put the request into the channel within the configured limit.
- **Connection timeout**: failed to establish a connection to the remote service.
- **Read/response timeout**: remote did not return a response in time; outcome may be unknown.
- **Gateway reply timeout**: caller waited too long for the result through the message flow.
- **Business deadline**: caller/domain no longer accepts a result after a defined point in time.

A synchronous `DirectChannel` can block inside the handler despite a configured request-channel send timeout; its deadline does not automatically bound total execution. When using `ExecutorChannel`, a broker, or request–reply gateways, timeout behavior must be **tested per topology and Spring Integration version**.

**Avoid unintended timeout stacking:** HTTP connect+read, retry attempts, and queue time can far exceed the Gateway reply timeout, producing floods of late responses and pending operations.

## 21. Setting an End-to-End Deadline and Retry Budget

Suppose:

~~~text
Business deadline  = 8 seconds
Gateway reply wait = 3 seconds
Remote call budget = 2 seconds / attempt
Retry budget       = at most 2 attempts
Backoff            = bounded with jitter
~~~

A design:

- Caller receives **PENDING/UNKNOWN_OUTCOME** if the request was durably accepted but not yet completed.
- Worker only retries while within the deadline, within budget, and when the operation is idempotent.
- After budget exhaustion, persist failure/unknown state and move to a recovery path.
- Remote call carries a deadline/cancellation hint if the remote contract supports it.
- Do not let a late reply produce a second result or a new side effect.

Do not claim a timeout automatically cancels every downstream request. Network packets may have already arrived and the remote commit may have happened. Cancellation is **a separate protocol**, not a guaranteed consequence of Java thread interruption or caller timeout.

## 22. Synchronous Gateway and Broker Request–Reply Do Not Share the Same Characteristics

**HTTP outbound gateway**:

~~~text
Message → HTTP POST → HTTP response → Message reply
~~~

**Broker request–reply**:

~~~text
Gateway
  → request topic/queue
  → remote consumer
  → reply topic/queue
  → correlation to pending request
  → Gateway
~~~

With a broker, you additionally need:

- Request destination and reply destination/reply-to.
- Correlation ID for each in-flight invocation.
- Reply listener/container running and authorized to read.
- TTL/expiry, pending-reply registry, or durable tracking.
- Consumer ACK/DLQ semantics independent of the reply.
- Handling late replies when the caller has already timed out.
- Idempotency on the receiver because brokers often perform redelivery.

**A broker ACK is not a domain response.** It may only confirm that the transport received/consumed the message. If the business operation requires confirmation, there must be a **reply message or status event** carrying the outcome.

## 23. Request–Reply Correlation over a Broker

A request:

~~~text
headers:
  transportCorrelationId = rpc-try-0042
  replyTo = inventory.replies.client-a
payload:
  operationId = RES-901
  orderId = O-901
  quantity = 2
~~~

A reply:

~~~text
headers:
  transportCorrelationId = rpc-try-0042
payload:
  operationId = RES-901
  result = RESERVED
  reservationId = RSV-555
~~~

Before returning the result:

1. Look up the pending request by **transport correlation**.
2. Validate whether the reply type/schema is valid.
3. Verify the **business operationId** against the request context.
4. Ensure the reply belongs to the right tenant/authorized client.
5. Deduplicate or ignore late/duplicate replies per policy.
6. Complete **exactly one** caller invocation.

Do not use only `sku` or `orderId` as the return correlation key when multiple requests run concurrently; two attempts for the same orderId may return different results. And do not use Spring's temporary `replyChannel` JVM object as a required wire header for a receiver in another process.

## 24. Replies Arriving Late or Twice

Timeline:

~~~text
T0 Caller A sends rpc-try-0042, operation RES-901.
T1 Remote finishes reserving stock, reply is published.
T2 Caller A hits reply timeout, pending request expires.
T3 Reply for rpc-try-0042 arrives late.
T4 Caller A retries RES-901 with rpc-try-0043.
T5 Reply for rpc-try-0043 arrives.
~~~

Proper recovery:

- A late reply must not be delivered to **another caller** just because the orderId matches.
- A late reply must not trigger stock reservation again.
- The business result for `RES-901` can be saved/updated for status lookup.
- Duplicate replies must not create two completion events.
- Pending-reply mappings need TTL/cleanup to avoid memory leaks.
- For a request that timed out while the remote committed, the caller receives **unknown/pending** rather than assuming failure.

An async workflow with durable status is often easier to operate than RPC-style blocking when remote service latency is high or there is multi-branch fan-out.

## 25. Error Channel and Remote Exception Mapping

In Spring Integration, you can see:

~~~text
Remote 503
  → HTTP outbound gateway raises exception
  → MessagingException / MessageHandlingException wrapper
  → caller exception (synchronous DirectChannel)

Or:

Remote 503
  → asynchronous worker / poller
  → ErrorMessage(Throwable)
  → errorChannel / recoverer
~~~

The path depends on the **sync vs async boundary** and endpoint/adapter configuration. Do not claim all errors automatically go to the global `errorChannel`; a JSON deserialization error can happen in a converter or container before a Spring Message is emitted.

The application should classify errors into:

~~~java
enum RemoteFailureKind {
    INVALID_REQUEST,
    UNAUTHORIZED,
    BUSINESS_REJECTED,
    RATE_LIMITED,
    TEMPORARILY_UNAVAILABLE,
    UNKNOWN_OUTCOME,
    PROTOCOL_MISMATCH,
    INTERNAL_CLIENT_ERROR
}
~~~

Do not turn a raw exception into domain `REJECTED_OUT_OF_STOCK` if the remote has not returned a trusted business result. Preserve `reasonCode`, remote operation, endpoint alias, and correlation; avoid exposing raw HTTP bodies/tokens/stack traces in public APIs.

## 26. Recovery Boundary Must Distinguish Permanent from Transient

| Failure | Fixable by retrying same payload? | Recovery |
|---|---|---|
| Local invalid quantity | No | Reject before remote call |
| Remote HTTP 400/invalid schema | No when contract unchanged | Notify caller/fix producer |
| Authentication/authorization fail | Not by hot-retrying | Fix credentials/permissions, audit |
| Remote 503 | Possibly | Bounded retry + backoff/circuit breaker |
| HTTP 429 | Possibly | Respect retry hints + quota |
| Remote 409 duplicate key | Depends on API | Query existing result/conflict |
| Read timeout | **Operation outcome unknown** | Reconcile/same idempotency key |
| Response correlation mismatch | Not a normal retry | Protocol alert/quarantine |
| Deserializer failure | No if response schema is wrong | Contract compatibility fix |
| Worker process crash | Redelivery possible | Durable inbox/idempotency |

**Do not retry every exception with a single policy.** Even HTTP 503 for a remote request with side effects needs an idempotency key and unknown-outcome handling if the request may have reached the server.

A circuit breaker can **prevent sending more requests** when downstream is overloaded, but it does not roll back already-sent requests or guarantee success. When the circuit is open, the caller receives failure/pending per the application contract.

## 27. RetryAdvice and HTTP/Broker Retries Must Not Multiply Attempts Indefinitely

Layers can retry together:

~~~text
Application retry:       3 attempts
Spring handler advice:   3 attempts
HTTP client retry:       2 attempts
Broker redelivery:       5 attempts

Worst-case potential: 3 × 3 × 2 × 5 = 90 remote requests
~~~

This is a **worst-case amplification estimate in the example** when layers are actually nested, not Spring Integration's default behavior. It illustrates why you need **one end-to-end retry budget**, rather than configuring each library independently.

Remediation:

- Choose the single layer responsible for retrying a specific failure kind.
- Use deadlines, max attempts, and backoff with jitter.
- Distinguish request-not-sent from read timeout after sending.
- Keep the same business operation ID across all attempts.
- Use a circuit breaker/rate limit to protect the remote service.
- After exhaustion, route to durable recovery/status; do not report fake success.

**RequestHandlerRetryAdvice** only wraps the handler to which the advice is attached. If a message transitions onto an `ExecutorChannel` and a downstream handler fails, retry advice on the upstream endpoint does not automatically wrap the downstream worker.

## 28. Transaction Boundary: Local Database Does Not Control Remote Side Effects

A dangerous flow:

~~~text
BEGIN local transaction
  INSERT order
  HTTP POST /inventory/reservations (remote COMMIT)
  UPDATE local order with reservation ID
COMMIT
~~~

If the remote reserved stock but the local DB rolls back, the system has a **remote reservation with no matching local state**. JDBC rollback does not automatically send a cancellation to Inventory.

Architectural options:

1. **Synchronous remote call** with stable idempotency key + reconcile + failure state; suitable when latency is low and the remote protocol is strong enough.
2. **Transactional Outbox:** local transaction saves order intent and outbox command; a publisher sends to remote asynchronously.
3. **Saga/process manager:** stores step state, retries, and compensates if the domain permits.
4. **Reservation with expiry:** Inventory holds stock with a TTL; workflow can release/cancel if the order does not complete.

**Outbox does not create a distributed transaction across two DBs/services**; it makes intent durable at the sender and allows retries. The receiver still needs an inbox/idempotency to handle duplicate deliveries.

## 29. Receiver Must Also Understand the Request Message as a Command

A remote service can receive HTTP and process it:

~~~text
HTTP inbound gateway/controller
  → Deserialize + authenticate
  → Validate schema/operationId/tenant
  → Convert wire DTO to ReserveStockCommand
  → Service Activator: reserve()
  → Database transaction + inbox
  → Reservation result
  → Serialize HTTP reply
~~~

On the sender, the request is packaged into a message. On the receiver, the symmetric process turns the message into **a call to an internal service**. This is where the EIP **Service Activator** connects messaging to domain logic.

A receiver can use:

- HTTP controller + Spring Integration inbound channel/Gateway; or
- Spring Integration HTTP inbound gateway directly; or
- Kafka/AMQP inbound adapter and reply publisher.

**Do not let the HTTP deserializer call repositories before validation.** Ingress must block malformed raw bytes, unsupported schemas, and unauthenticated requests before side effects. Once a request reaches the transactional handler, the receiver still needs to verify business rules and tenant permissions.

## 30. Receiver Idempotency: ACK/HTTP Reply Does Not Replace Durable Dedupe

A service receives `RES-901` the first time and again after a client timeout:

~~~text
First request:
  operationId=RES-901 → reserve stock → COMMIT RSV-555

Retry:
  operationId=RES-901 → load committed result RSV-555
  (does not decrement stock a second time)
~~~

A data design:

~~~sql
CREATE TABLE processed_reservation (
    tenant_id VARCHAR(80) NOT NULL,
    operation_id VARCHAR(100) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    state VARCHAR(24) NOT NULL,
    reservation_id VARCHAR(100),
    result_json TEXT,
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

**This is an example table**, not including transaction logic, secondary indexes, retention, state transitions, or migrations. When receiving a request:

1. Validate/authorize tenant and command before side effects.
2. Claim `(tenantId, operationId)` with a **unique constraint**.
3. Compare the canonical command fingerprint against the existing record.
4. If the result is already COMMITTED and the fingerprint matches, return the cached result.
5. If currently PROCESSING, return pending/conflict per contract instead of running blindly in parallel.
6. If same key but different payload, return an idempotency conflict.
7. If first time, write the reservation and completion state **in one local transaction**.

An in-process `ConcurrentHashMap` is insufficient because it is lost on restart, not shared across replicas, and not atomic with the database. "Received the HTTP request" is also insufficient proof that stock was successfully reserved.

## 31. Failure Between Commit and Reply: Why Does Dedupe Need a Cached Result?

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant R as Receiver
    participant DB as Receiver DB
    S->>R: Reserve RES-901
    R->>DB: INSERT operation + reserve stock
    DB-->>R: COMMIT RSV-555
    R--xS: Response lost
    S->>R: Retry RES-901 (same payload/key)
    R->>DB: Lookup committed operation
    DB-->>R: RSV-555
    R-->>S: RESERVED RSV-555
~~~

If the receiver only writes a `seen=true` marker and returns null for duplicates, the sender may not know the remote outcome and the Gateway keeps timing out. Dedupe is far more useful when storing the **terminal outcome or status reference**, so repeated invocations receive a meaningful result.

If the handler fails **after inserting the marker but before business commit**, the marker must roll back or the state must allow safe retry. Separating the marker into Redis outside the inventory DB transaction easily creates a **"seen but not reserved"** state.

**Do not attach idempotency semantics to an HTTP header that the receiver ignores.** The header is just a protocol request; the guarantee lives in the receiver's transaction/state machine.

## 32. Cancellation and Compensation Are Another Call, Not a Timeout

When Checkout no longer needs a reservation:

~~~text
Reserve:
  operationId=RES-901 → reservationId=RSV-555

Cancel:
  operationId=CANCEL-901 → reservationId=RSV-555
~~~

The cancel command must have its own **operation identity** and permissions. Do not resend `RES-901` with an arbitrary `"cancel": true` header if the remote contract does not define it that way.

If the receiver has already captured payment or allocated resources, "cancel" may be a **compensating action**, not an atomic rollback. You need to know whether the domain permits reversal, how to handle duplicate cancels, cancels arriving before the reserve reply, and timeouts on the cancel operation itself.

Some domains require a **reservation TTL** that auto-releases if unconfirmed, but TTL does not replace persisting state for reconciliation. If it expires before order commit, the business flow must explicitly handle `RESERVATION_EXPIRED`.

## 33. Remote Call Security: The Trust Boundary Changes

A Java Gateway interface at the application layer **does not automatically secure** a remote call. When a request leaves the process:

- Use **TLS** and verify certificates/hostnames.
- Authenticate service identity (mTLS, OAuth2 client credentials, or deployed mechanism).
- Authorize the operation **at the receiver**, not just trusting the sender.
- Whitelist allowed headers and Content-Types.
- Do not trust raw `tenantId` or `sourceSystem` self-declared by external callers.
- Do not let clients supply arbitrary URLs/hostnames in messages, turning the outbound gateway into an SSRF proxy.
- Do not let input inject bean names, SpEL expressions, or internal `replyChannel` references to the receiver.
- Limit payload size, nesting depth, item counts, header length, and request rate.

In multi-tenant systems, operationId can collide across tenants; **idempotency key scope** must include the verified identity/tenant. Correlation IDs are not access tokens; never use them as proof of authorization to read a reservation.

**Secrets do not belong in domain payloads.** Never let authorization bearer tokens be logged, routed to a broker DLQ, or serialized to child messages via wildcard header mapping.

## 34. Serialization and Schema Evolution of Request/Reply

Renaming a field in a Java record does not automatically preserve wire schema compatibility:

~~~text
Client v1: productCode, units
Server v2: sku, quantity
~~~

If the server deploys independently, a clear schema/version contract is required:

| Change | Risk | Handling |
|---|---|---|
| Add optional field | Potentially compatible | Default/unknown behavior must be defined |
| Rename required field | Usually breaking | Versioned mapper/schema |
| Change units from integer to decimal | Breaking semantics | Validated conversion |
| Change meaning of operationId | Breaking idempotency | Migration protocol |
| HTTP 200 changes from final to accepted | Breaking outcome contract | Client update or versioning |
| Remote returns new enum value | Potentially breaking | Explicit unknown enum policy |
| Null in previously non-null field | Potentially breaking | Reject/tri-state per contract |
| Change currency/number precision | Risk of data corruption | BigDecimal/scale tests |

Do not accept every unknown field and assume compatibility: semantic changes may not fail the deserializer yet still cause wrong downstream processing. If the same API path serves multiple versions, Router/Transformer should select by a **trusted contract**, not accidental type inference.

Schema registries or JSON Schema help validate structure; **they do not guarantee business meaning**. Version the mapping policy as well when replaying events from a DLQ after an upgrade.

## 35. Combining Filter, Router, and Transformer Before a Remote Call

A controlled flow:

~~~text
Inbound Java Gateway
  → Filter / schema validation
  → Router by allowed operation
  → Transformer to remote DTO
  → Remote outbound gateway
  → Transformer to domain result
  → Gateway reply
~~~

| Endpoint | Responsibility | Common Mistake |
|---|---|---|
| **Filter** | Block invalid payloads before I/O | Triggering remote side effects inside predicate |
| **Router** | Select a whitelisted remote operation/endpoint | Routing by arbitrary URL/method header |
| **Transformer** | Convert DTO/units/headers with validation | Calling remote API inside mapper without error policy |
| **Outbound gateway** | Execute request–reply transport | Assuming HTTP 202 is business success |
| **Service Activator** | Run a business method | Mixing query/command ambiguously |
| **Error handler** | Classify failures and recovery | Catching all errors as invalid input |

**It is not strictly necessary to split a small flow into separate endpoints.** Multiple steps can be packaged in one well-tested adapter. What matters is **clear responsibilities and side-effect boundaries**.

## 36. RPC-Style Calls Do Not Fit Every Workflow

A reply-waiting Gateway is a sound choice when:

- The remote API has predictable latency and a short SLA.
- The caller genuinely needs the result immediately.
- Strong retry/idempotency and error contracts exist.
- Concurrency/connection limits are controlled.

Consider asynchronous messaging when:

- The operation takes minutes/hours.
- There are multiple steps and compensations.
- The workflow must tolerate downtime of a service.
- There is large fan-out or batch processing.
- The caller can accept `PENDING` and query status/callback later.

~~~text
Synchronous RPC-style:
  Checkout.reserve() → wait → RESERVED

Asynchronous workflow:
  Checkout.submitReserve() → durable ACCEPTED
  → worker → remote Inventory
  → eventual completion event/status
~~~

**Do not call `ACCEPTED` `SUCCEEDED`** if the remote side has not committed. Likewise, do not build a blocking Gateway with a 60-minute reply timeout just to disguise a process manager that actually needs durability and progress tracking.

## 37. Async Request–Reply with Durable Status and Outbox

A pattern:

~~~mermaid
flowchart TD
    C["Checkout"] --> IN["Durable command intake"]
    IN -->|"Persist accepted"| P["Return PENDING + operationId"]
    IN --> OUT["Outbox / work queue"]
    OUT --> W["Worker"]
    W --> REM["Inventory remote API"]
    REM --> W
    W --> STATE["Durable operation result"]
    STATE --> Q["GET status / completion event"]
~~~

Principles:

1. Sender persists **command intent and status reference** durably before returning pending.
2. Worker claims work with a lease/visibility timeout and retry budget.
3. OperationId stays unchanged across retries and remote calls.
4. Receiver deduplicates using unique key + fingerprint.
5. Worker stores final result or unknown outcome state.
6. Caller obtains final outcome via status endpoint/event; do not rely solely on a JVM-local `replyChannel`.
7. Provide expiry/reconciliation/cleanup for long-unfinished work.

A message broker does not automatically guarantee durability in every configuration; verify persistence, publisher confirms, retention, ordering, consumer ACKs, and failure recovery for the specific transport.

## 38. Remote Invocation in Scatter-Gather or Splitter/Aggregator

An order with three warehouses:

~~~text
ReserveStockCommand parent=O-901
  → Splitter:
      Warehouse A, member A
      Warehouse B, member B
      Warehouse C, member C
  → three remote reservations
  → Aggregator
  → OrderReservationSummary
~~~

For each child:

- Share a `parentCorrelationId` for the same logical group.
- Have a distinct **memberId** (warehouse/line ID).
- Have a distinct **child operationId** so the remote service deduplicates each reservation properly.
- Have its own deadline/retry budget without exceeding the parent deadline.
- Produce a `StockReservationResult` **or an explicit terminal error outcome** when unable to complete.

**Do not use the same idempotency key for all three warehouses if the receiver treats that key as representing a single reservation.** And do not drop an exception onto a global error channel and forget to reply for member B: the Aggregator may wait indefinitely.

If one warehouse reserved successfully while another rejected, a domain policy is needed: partial accept, release/compensate, or retry the failed member. "All three replies arrived" does not equal "all stock was reserved."

## 39. One Member Fails: Return a Correlated Failure Outcome

A result type:

~~~java
record ReservationMemberOutcome(
    String parentGroupId,
    String memberId,
    String operationId,
    boolean successful,
    String reservationId,
    String reasonCode
) {}
~~~

When warehouse B returns out-of-stock:

~~~java
ReservationMemberOutcome rejected =
    new ReservationMemberOutcome(
        "tenant-a|O-901|reservation-v2",
        "warehouse-B",
        "RES-901-B",
        false,
        null,
        "OUT_OF_STOCK");
~~~

The Aggregator needs to:

- Match results against the **expected member manifest** (A, B, C).
- Not count a duplicate B as a new member.
- Not mix groups from two tenants/revisions sharing the same `orderId`.
- Distinguish **business rejection** from timeout/unknown remote outcome.
- Release/expire per intentional policy; do not drop failed members and report success.
- If compensation is needed, trigger cancel on the exact committed reservation IDs.

An `UNKNOWN_OUTCOME` must not be turned into `OUT_OF_STOCK` just so the Aggregator hits its count; it requires reconciliation or an appropriate terminal workflow status.

## 40. Resource Limits at the Remote Call Boundary

An RPC-style request can block threads, occupy HTTP connections, and amplify traffic to a remote service:

~~~text
100 concurrent checkout calls
  × 3 warehouses each
  × 2 retry attempts
  = up to 600 remote calls
~~~

This is an example estimate if every request fans out and retries; in reality it is also bounded by pools/rate limits/deadlines.

Safeguards:

- Connection pool with sensible max total/per-route limits.
- Bounded executor/queue and backpressure; do not dispatch unboundedly.
- Per-tenant/per-service concurrency quota.
- Circuit breaker, rate limit, and bulkhead to isolate remote dependencies.
- Unified timeouts and retry deadlines.
- Max payload/header sizes before serialization.
- Pending reply/group stores with TTL/expiry and cleanup.
- Quarantine/DLQ with retention/capacity limits so a failing producer does not fill storage.

**Do not solve overload by increasing timeouts indefinitely.** Large timeouts hold threads/connections for a long time and can take down all of Checkout when Inventory slows down.

## 41. Unit Testing the Application Port Without a Spring Integration Context

Because Checkout only depends on `InventoryReservationPort`, it can be tested with a fake:

~~~java
@Test
void checkoutUsesTypedInventoryPort() {
    InventoryReservationPort fake = cmd ->
        new StockReservationResult(
            cmd.operationId(),
            cmd.orderId(),
            "RSV-555",
            ReservationStatus.RESERVED);

    CheckoutUseCase checkout = new CheckoutUseCase(fake);
    ReserveStockCommand command = new ReserveStockCommand(
        "tenant-a", "RES-901", "O-901", "SKU-7", 2);

    StockReservationResult result =
        checkout.reserveForOrder(command);

    assertEquals("RES-901", result.operationId());
    assertEquals("O-901", result.orderId());
    assertEquals("RSV-555", result.reservationId());
    assertEquals(ReservationStatus.RESERVED, result.status());
}
~~~

**This test only verifies the application boundary**; it does not prove HTTP requests, authentication, reply correlation, or Spring configuration are correct. However, it shows the domain use case has no knowledge of `MessageChannel`, URLs, or HTTP statuses.

Another test can have the fake port throw `RemoteOperationUnknownException` (an application exception) to verify Checkout does **not** assign a definite `RESERVED` or `FAILED` when the remote outcome is unclear.

## 42. Unit Testing the Mapper: Invalid Input Never Reaches Remote I/O

Minimal application exceptions:

~~~java
final class InvalidReservationCommandException
        extends RuntimeException {
    InvalidReservationCommandException(String reasonCode) {
        super(reasonCode);
    }
}

final class RemoteProtocolException extends RuntimeException {
    RemoteProtocolException(String reasonCode) {
        super(reasonCode);
    }
}
~~~

Unit testing request mapping:

~~~java
@Test
void mapperKeepsLogicalOperationIdentity() {
    ReservationRequestMapper mapper =
        new ReservationRequestMapper();
    ReserveStockCommand command = new ReserveStockCommand(
        "tenant-a", "RES-901", "O-901", "SKU-7", 2);

    StockReservationHttpRequest wire =
        mapper.toHttpRequest(command);

    assertEquals("RES-901", wire.requestId());
    assertEquals("O-901", wire.orderRef());
    assertEquals("SKU-7", wire.productCode());
    assertEquals(2, wire.units());
}

@Test
void invalidQuantityIsRejectedBeforeRemoteCall() {
    ReservationRequestMapper mapper =
        new ReservationRequestMapper();
    ReserveStockCommand invalid = new ReserveStockCommand(
        "tenant-a", "RES-901", "O-901", "SKU-7", -3);

    InvalidReservationCommandException failure =
        assertThrows(
            InvalidReservationCommandException.class,
            () -> mapper.toHttpRequest(invalid));

    assertEquals(
        "INVALID_RESERVATION_COMMAND",
        failure.getMessage());
}
~~~

The fact that the mapper throws an exception **does not prove the outbound gateway did not call remote** if the flow executes side effects **before** the mapper. Integration tests must place the mapper **before** the outbound gateway and use a fake remote server/spy to assert request count = 0 on invalid input.

Do not assume `quantity=0` is always invalid in every domain; this example chooses a reservation contract requiring positive units. Return/cancel-reservation operations may have different rules and require separate command types.

## 43. Unit Testing Reply: Enums, Required Fields, and Correlation

Testing response mapping:

~~~java
@Test
void validRemoteReplyMapsToDomain() {
    ReservationReplyMapper mapper =
        new ReservationReplyMapper();
    StockReservationHttpResponse raw =
        new StockReservationHttpResponse(
            "RES-901", "O-901", "RESERVED", "RSV-555");

    StockReservationResult result = mapper.toResult(raw);

    assertEquals(ReservationStatus.RESERVED, result.status());
    assertEquals("O-901", result.orderId());
    assertEquals("RES-901", result.operationId());
}

@Test
void unknownStatusIsProtocolFailure() {
    ReservationReplyMapper mapper =
        new ReservationReplyMapper();
    StockReservationHttpResponse raw =
        new StockReservationHttpResponse(
            "RES-901", "O-901", "SOMETHING_NEW", "RSV-555");

    assertThrows(
        RemoteProtocolException.class,
        () -> mapper.toResult(raw));
}
~~~

For the `mapCheckedReply()` helper in section 16, additionally test:

~~~text
Expected operationId=RES-901, orderId=O-901
Reply requestId=RES-902, orderRef=O-901
  → REMOTE_CORRELATION_MISMATCH

Expected operationId=RES-901, orderId=O-901
Reply requestId=RES-901, orderRef=O-902
  → REMOTE_CORRELATION_MISMATCH
~~~

**Do not only assert that the response has the right type.** If a remote reply is matched to the wrong request, a structurally valid `StockReservationHttpResponse` can still cause data leakage and corrupted business state.

## 44. Integration Testing the Gateway Proxy with a Fake Handler

Before testing real HTTP, verify Spring Integration builds the typed Gateway and reply properly:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class ReservationGatewayTestConfig {

    @Bean
    IntegrationFlow reservationTestFlow() {
        return IntegrationFlow
            .from("inventory.reserve.requests")
            .handle(
                ReserveStockCommand.class,
                (command, headers) ->
                    new StockReservationResult(
                        command.operationId(),
                        command.orderId(),
                        "RSV-TEST",
                        ReservationStatus.RESERVED))
            .get();
    }
}
~~~

Test:

~~~java
@Autowired
InventoryReservationGateway gateway;

@Test
void javaGatewayGetsReplyWithoutManualMessageBuilder() {
    StockReservationResult reply = gateway.reserve(
        new ReserveStockCommand(
            "tenant-a", "RES-901", "O-901", "SKU-7", 2));

    assertEquals("RES-901", reply.operationId());
    assertEquals("RSV-TEST", reply.reservationId());
    assertEquals(ReservationStatus.RESERVED, reply.status());
}
~~~

Run in an **isolated Spring test context**, ensuring the annotated Gateway interface is scanned. Do not register both the production HTTP flow and this fake handler consuming `inventory.reserve.requests` simultaneously; with competing subscribers, a request may go to an unintended endpoint.

This test proves the Gateway **packages a method call into a message and receives a reply**, but does not test HTTP wire format, connection timeouts, or remote idempotency; those require integration tests with a mock server.

## 45. Integration Testing with a Fake HTTP Server and Real Contract

You can use WireMock, MockWebServer, or a local HTTP test server whose lifecycle is controlled by the test. What to simulate:

~~~text
POST /reservations
Request Content-Type: application/json
Request Idempotency-Key: RES-901
Body requestId=RES-901, orderRef=O-901, units=2

HTTP 200
{
  "requestId":"RES-901",
  "orderRef":"O-901",
  "result":"RESERVED",
  "reservationRef":"RSV-555"
}
~~~

Test assertions:

1. Gateway sends the right POST method/path and Content-Type.
2. Wire payload has exact field names/types and quantity.
3. Idempotency header **is actually present on the HTTP request**, not only on the Spring message.
4. Authentication/TLS or fake auth interceptor is invoked as configured.
5. Response body is decoded by the converter into `StockReservationHttpResponse`.
6. Reply Transformer returns the right `StockReservationResult`.
7. Response requestId/orderRef must match the **request context**.
8. If the remote returns a business rejection, the Gateway does not map it to reserved.
9. If the server returns 503/timeout, the error classifier behaves per contract.
10. Never call real production Inventory in tests.

**Do not merely mock `InventoryReservationPort`** and claim the outbound gateway is tested. Mocking the port bypasses the integration adapter, HTTP serializer, headers, timeouts, and error mapping—the primary failure points of this lesson.

Because this exercise depends on the Spring Integration/HTTP client version, configure the test server URL via an injected property/URI template. **Never hardcode a production endpoint** in unit/integration test code.

## 46. Fault Injection: Request Not Sent, Server Commits, and Reply Lost

Three distinct failure windows:

~~~text
A. DNS/connect refused:
   No connection; request likely never reached remote.

B. Remote receives request, throws before commit:
   Receiver processing failed; caller may receive 500.

C. Remote commits reservation, reply dropped:
   Caller gets read timeout; remote effect already exists.
~~~

Test C is the most critical for commands with side effects. A fake server stores:

~~~text
operation RES-901 → RESERVED RSV-555
~~~

then intentionally **drops the response** on the first attempt. The caller gets a timeout, then resends with **RES-901**. The receiver returns the same `RSV-555` without creating a new reservation.

Assertions:

- Remote committed reservations count = 1.
- Sender does not change operationId on retry.
- Local workflow does not record `FAILED_PERMANENT` solely because of a read timeout.
- Without a reply or status lookup, state is `UNKNOWN_OUTCOME`.
- Retry or reconciliation produces a single valid terminal outcome.
- No leaked sockets/threads/pending requests after timeout.

**HTTP 503 does not guarantee the remote had no side effects** in all APIs. A server might commit and then fail while building the response; for mutation requests, always consider idempotency/reconciliation per contract.

## 47. Concurrency Test: Same operationId Reaching Two Receiver Threads

A sequential test:

~~~text
reserve(RES-901)
reserve(RES-901)
assert one reservation
~~~

cannot detect races when two requests arrive concurrently.

Concurrency tests need real transactions/unique constraints:

~~~mermaid
sequenceDiagram
    participant A as Receiver A
    participant B as Receiver B
    participant DB as Inventory DB
    A->>DB: Claim RES-901
    B->>DB: Claim RES-901 concurrently
    DB-->>B: Wait/conflict by unique key
    A->>DB: Reserve stock + COMMIT
    B->>DB: Lookup committed result
    DB-->>B: RESERVED RSV-555
    Note over A,B: one business reservation committed
~~~

Cases:

- Two calls with same key/same fingerprint → **one** business side effect.
- Same key/different fingerprint → conflict, never silently overwrite.
- Worker A rolls back before commit → worker B can safely retry.
- Worker A commits then crashes before reply → worker B gets cached result.
- Two tenants with same operation ID → dedupe scope **does not mix tenants**.
- Restart/multi-instance → dedupe still works.

Use `CountDownLatch` or transaction test barriers, test timeouts, and verify final DB row counts. `synchronized` on a singleton bean or an in-JVM `ConcurrentHashMap` cannot replace unique constraints/durable state.

## 48. Testing Broker Request–Reply, ACK, and Late Replies

When replacing an HTTP outbound gateway with Kafka/AMQP/JMS request–reply, test at the **real transport boundary**, not just with `DirectChannel`:

~~~text
Request rpc-try-0042 → queue "inventory.requests"
  payload.operationId = RES-901
  header.replyTo = "inventory.replies.client-a"

Remote consumer → reserve stock
  → reply rpc-try-0042 on reply destination

Gateway reply listener → correlate → StockReservationResult
~~~

Checks:

1. **Request publish/ACK** per broker contract is not confused with business completion.
2. `replyTo` and `transportCorrelationId` are mapped accurately between protocol headers.
3. Two concurrent requests with **out-of-order replies** still return to the right callers.
4. Duplicate requests do not create duplicate reservations.
5. Duplicate replies do not create a second completion event.
6. Replies arriving after timeout are cleaned up/quarantined/recorded to durable status per policy.
7. Malformed messages go to rejection/DLQ with a reasonCode rather than retrying forever.
8. DLQ publish failure does not cause the source message to be ACKed and lost without other recovery.
9. Receiver crashes after commit before ACK: redelivery returns cached result.
10. Sender restarts while requests are pending: durable workflows must recover; temporary JVM-only reply addresses will not revive on their own.

**Broker reply-to/correlation features and transaction semantics vary by adapter.** Configure and test with the specific protocol; do not reuse Spring's Java `replyChannel` object directly as a broker wire value.

## 49. End-to-End Test Matrix

| Case | Input/fault | Expectation |
|---|---|---|
| Valid reservation | `RES-901`, quantity 2 | Reply RESERVED matches request |
| Invalid quantity | `quantity=-1` | Rejected before I/O |
| Missing operationId | Empty/null ID | Rejected, remote not called |
| Wrong wire shape | JSON array instead of object | Decode/schema rejection |
| Unsupported schema | Unsupported new reply/version | Protocol error, no fake success |
| Remote out-of-stock | Business rejection | `REJECTED_OUT_OF_STOCK`, no hot retry |
| HTTP 202 | Remote accepted async | PENDING + status reference |
| HTTP 400 | Invalid request | Permanent error |
| HTTP 401/403 | Credentials/rights | Security error + audit |
| HTTP 409 | Conflict/duplicate | Handled per documented API |
| HTTP 429 | Rate limit | Retry budget/Retry-After |
| HTTP 503 | Transient outage | Bounded retry + circuit breaker |
| Connect refused | No connection established | Accurate classifier, no fabricated result |
| Read timeout after commit | Remote already reserved | UNKNOWN/reconcile, no double reserve |
| Malformed reply body | Missing reservationRef | Protocol failure |
| Wrong reply requestId | Correlation mismatch | Do not deliver mismatched reply |
| Wrong reply orderRef | Different order | Protocol error + audit |
| Two concurrent callers | Out-of-order responses | No cross-caller mix-up |
| Same ID, same payload | Redelivery | Cached reply, one effect |
| Same ID, different payload | Key conflict | Never silently overwrite |
| Two tenants same key | Cross-tenant collision | Dedupe scoped per tenant |
| Duplicate broker reply | Two replies same correlation | One completion |
| Late broker reply | Caller already timed out | Does not trigger new reservation |
| Outbox publisher crash | Sent, not yet marked sent | Receiver idempotent |
| Sender worker restart | In-flight command | Durable status/recovery |
| Receiver DB rollback | Claim exists before commit | Valid retry, no poisoned marker |
| DLQ unavailable | Quarantine publish fail | Never ACK and lose responsibility |
| Splitter child failure | Warehouse B rejects | Final group FAILED/PARTIAL per policy |
| Aggregator duplicate | Warehouse A replies twice | Not counted as member C |
| Large payload | Exceeds limit | Rejected before deserialize/fan-out |
| Header spoofing | Fake tenant/auth | Security rejection |
| Contract v1→v2 | Rename required field | Mapper/versioned contract |
| Gateway timeout | Worker continues to commit | Do not mistake timeout for rollback |

**Three-layer testing:** (1) Java mappers, (2) IntegrationFlow/Gateway proxy, (3) HTTP/broker adapter + remote receiver/DB. One test layer does not replace the other two. For side effects, assert **database row counts, idempotency records, remote call counts**, and outbox/reply state—not only exceptions.

## 50. Observability: Measuring Remote Attempts Differently from Business Completions

These metrics are **suggestions**, not default Spring Integration meters:

| Metric | What to observe |
|---|---|
| `remote.invoke.request.count` | Number of logical requests |
| `remote.invoke.attempt.count` | Number of transport attempts (including retries) |
| `remote.invoke.reply.count` | Replies received |
| `remote.invoke.reply.timeout.count` | Callers exceeding reply timeout |
| `remote.invoke.connect.failure.count` | Connection failures |
| `remote.invoke.read.timeout.count` | Network read timeouts |
| `remote.invoke.correlation.mismatch.count` | Replies not matching requests |
| `remote.invoke.protocol.failure.count` | Abnormal remote schema/status |
| `remote.invoke.business.rejected.count` | Remote domain rejections |
| `remote.invoke.unknown.outcome.count` | Operations without final result |
| `remote.invoke.reconciliation.pending.count` | Commands needing remote state verification |
| `remote.invoke.retry.exhausted.count` | Retry budget exhausted |
| `remote.invoke.circuit.open.count` | Calls blocked by circuit breaker |
| `remote.receiver.duplicate.completed.count` | Receiver returned cached result |
| `remote.receiver.idempotency.conflict.count` | Same key, changed payload |
| `remote.receiver.side_effect.committed.count` | Number of reservations actually created |
| `remote.invoke.duration` | Latency per endpoint/operation |
| `remote.invoke.pending.reply.count` | Pending request map entries held |

**Logical requests and attempts differ**: one operation `RES-901` may be sent three times while the receiver commits only one reservation. Do not report that the system created three reservations just because HTTP request count equals 3.

Tags should have low cardinality such as `remoteServiceAlias`, `operation`, `outcome`, `reasonCode`, `schemaVersion`; do not put `operationId`, sensitive `tenantId`, full URLs with query strings, `eventId`, or emails as metric labels.

Controlled structured logging/tracing:

~~~text
operation=RESERVE_STOCK
remoteService=inventory
operationId=RES-901
transportAttempt=2
transportCorrelationId=rpc-try-0043
remoteStatus=RESERVED
businessOutcome=SUCCEEDED
idempotentReplay=true
sideEffectCommittedCount=0
~~~

On timeout:

~~~text
operationId=RES-901
transportAttempt=1
failureKind=UNKNOWN_OUTCOME
reconciliationStatus=PENDING
businessOutcome=UNKNOWN
~~~

Specific IDs can appear in properly access-controlled logs/traces with appropriate retention; do not copy entire payloads, authorization headers, or raw HTTP responses into default logs.

## 51. Runbook: Gateway Reports Timeout—Did Inventory Reserve or Not?

Investigation procedure:

1. **Find the logical operationId** from Checkout, tenant scope, and orderId.
2. **Check local validation:** was the command rejected before the outbound gateway?
3. **Check the request channel:** was it sent successfully, or is there queue backlog/executor saturation?
4. **Check transform/header mapping:** do the wire DTO and Idempotency-Key match the contract?
5. **Check the network:** connect refused, read timeout, HTTP 503, or 429?
6. **Distinguish the timeout:** request send, HTTP response, Gateway reply, or business deadline?
7. **Check the remote idempotency record:** does the receiver have a record for `RES-901`, and with what fingerprint/state?
8. **Check the remote reservation:** was stock reserved/committed, and under which reservationId?
9. **Check local outbox/state:** what durable intent and outcome did the sender record?
10. **Check correlation/reply-to:** were there late, duplicate, or mismatched replies?
11. **Check retries:** did retries use the same operationId or accidentally generate a new key per attempt?
12. **Check other side effects:** did payment, email, or cancellation already run?
13. **Reconcile:** query remote status by key; if no API exists, handle unknown outcome per manual/recovery policy.
14. **Remediate:** fix mapper/timeout/bulkhead/circuit/idempotency, and add a test reproducing the crash window.
15. **Close:** update the final business outcome; do not merely close a network alert while local/remote states still conflict.

**Do not automatically cancel and recreate a reservation** when you only know the caller timed out. An old request might complete after the cancellation is sent, causing state oscillation if the workflow does not control ordering and idempotency.

## 52. Hands-On Exercise: Replacing a Direct HTTP Client with Message-Driven Invocation

Build the mini project **InventoryRemoteInvocation**:

1. Define `ReserveStockCommand` and `StockReservationResult` in the application layer.
2. Define `InventoryReservationPort` and use a fake implementation to unit test Checkout.
3. Create the `InventoryReservationGateway` interface with `@MessagingGateway`.
4. Write `ReservationRequestMapper` and `ReservationReplyMapper`.
5. Create `IntegrationFlow.from("inventory.reserve.requests")` with a request Transformer, HTTP outbound gateway, and reply Transformer.
6. Use a fake HTTP server exposing `/reservations` accepting the JSON wire contract.
7. Configure HTTP Content-Type, TLS/auth in the appropriate test environment, and the Idempotency-Key header mapper.
8. Test payload/headers/response result/correlation; never call production Inventory.
9. Test invalid input before the HTTP call: the fake server must see request count = 0.
10. Fake server returns `REJECTED_OUT_OF_STOCK`; Gateway returns business rejection.
11. Fake server returns 503; design bounded retries, asserting attempts and backoff policy.
12. Fake server commits then drops the reply; caller must record unknown outcome/reconcile with the **same operationId**.
13. Write a receiver-side inbox DB with unique constraint and fingerprint.
14. Test two concurrent requests with the same key; only one reservation actually commits.
15. Replace HTTP with a broker request–reply test flow with reply-to/correlation without changing the Checkout application port if semantics are preserved.
16. Add a Splitter for three warehouses, each child having its own operationId; Aggregator does not count duplicates.
17. Inject one child failure and one late reply, verifying the summary is accurate.
18. Add outbox/saga or durable pending status for slow operations.
19. Limit concurrent remote calls and monitor retry amplification.
20. Write a runbook for debugging remote call timeouts by `operationId` rather than relying solely on HTTP exception text.

**Completion criteria:** caller only invokes the typed port, wire requests are built accurately; remote replies are correlated and validated; timeouts are not mislabeled as business failures; retries do not duplicate side effects; error channel, DLQ/reconciliation, and status stay synchronized between sender–receiver; tests verify both message flows and HTTP/broker boundaries.

## 53. Common Misconceptions

**"RPC through a Gateway is like a local method—just try/catch."** False. Remote calls have timeouts, partial failures, and unknown outcomes.

**"Encapsulating into messages means zero coupling."** No. Wire schemas, latency, security, and remote service semantics still exist.

**"`@MessagingGateway` calls remote HTTP by itself."** No. It sends the request into an IntegrationFlow; the outbound gateway/adapter performs transport.

**"HTTP outbound channel adapter always returns a reply."** No. Distinguish one-way adapters from request–reply gateways.

**"HTTP 200 always means business success."** No. The body can represent a domain rejection.

**"HTTP 202 means stock was successfully reserved."** No, it usually means accepted per API contract; status must be checked.

**"HTTP 503 proves the server did not commit."** Not necessarily, especially if an error occurred while building the response after the side effect.

**"Timeout means the operation was canceled/rolled back."** No. The remote side may continue and commit.

**"A retry should use a new requestId to avoid conflicts."** Dangerous: it can create a new business operation and double-reserve.

**"Transport correlation ID and idempotency key are the same thing."** No. Correlation matches request–reply; idempotency protects logical effects.

**"Spring Message ID is durable across broker replays."** Not by default.

**"The Idempotency-Key header has meaning even if the receiver ignores it."** No. The receiver must enforce a dedupe/transaction contract.

**"Local @Transactional rolls back the remote inventory DB."** No. The two services have separate transaction boundaries.

**"A seen marker in Redis means the remote side committed."** Not if the marker is not atomic with the reservation write.

**"Having an ErrorMessage on errorChannel means the caller received an error."** No. Async error recovery is not automatically a reply.

**"Broker ACK equals business outcome."** False. Transport ACK and business outcome are different.

**"If a reply is needed, just block the Gateway for minutes."** Usually hard to operate; a durable async workflow/status may be better suited.

**"A child remote failure can be dropped and the Aggregator still succeeds."** False. The group needs a failure outcome/release/compensation policy.

**"All custom headers from Spring pass through HTTP/broker automatically."** No. You need mappers/whitelists/tests.

**"Unit testing mappers alone is enough."** No. You must test outbound transport, receiver dedupe, retries, and crash windows.

## 54. Key Takeaways

**Encapsulating remote calls as messages** lets application code use **a typed method** while Spring Integration orchestrates the request channel, Transformer, outbound gateway, reply message, Router/Filter, and error handling. The typical flow is **application port → `@MessagingGateway` → request message → outbound transport gateway → remote receiver → reply message → typed result**.

The value of the pattern is not making a remote service **look local and guaranteed to succeed**, but **decoupling remote invocation from business code** so transport/versioning, validation, correlation, and recovery are managed at a clear integration boundary.

For commands with side effects, keep the **logical operationId/idempotency key** across retries, use a separate **correlation ID** per request/reply attempt, distinguish **HTTP/broker ACKs from business completion**, and never infer rollback from a timeout. When a remote outcome is unknown, **status lookup/reconciliation** is required; for long-running or fan-out workflows, prefer durable messaging, inbox/outbox, and a process manager where appropriate. Test the **happy path, malformed input, connection errors, remote commits before lost replies, duplicate/concurrent requests, and late replies** so a convenient Gateway never obscures distributed risks.

### References

- Enterprise Integration Patterns, **Messaging Gateway**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Enterprise Integration Patterns, **Request-Reply**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/RequestReply.html
- Enterprise Integration Patterns, **Correlation Identifier**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html
- Spring Integration Reference, **Messaging Gateways**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **HTTP Support**: https://docs.spring.io/spring-integration/reference/http.html
- Spring Integration Reference, **Transformer**: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference, **Router**: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Service Activator**: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Framework Reference, **Declarative Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html

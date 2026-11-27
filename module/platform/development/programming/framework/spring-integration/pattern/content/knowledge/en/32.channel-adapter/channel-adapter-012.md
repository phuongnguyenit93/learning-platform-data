# Distinguishing adapters from gateways and service activators

## 1. The problem: three endpoints that look alike yet have different contracts

An order system needs to connect the application with Kafka, HTTP APIs, a database, and a business service. Looking at Java DSL, you may see `from(...)` or `handle(...)` calls everywhere:

~~~java
// Conceptual only; these three options do NOT share the same semantics.
IntegrationFlow.from(inboundSource);
IntegrationFlow.from("orders.commands").handle(someHandler);
IntegrationFlow.from("orders.requests").handle(remoteEndpoint);
~~~

Because their shapes look similar, a team can easily pick the wrong one:

- Using an **outbound channel adapter** in a flow that needs a **business reply** over HTTP.
- Using an **inbound channel adapter** where an external client **is waiting for a response**.
- Calling a **Service Activator** a gateway and assuming it provides transport protocols, timeouts, and reply correlation by itself.
- Seeing a broker ACK or HTTP 202 and assuming business processing **is already complete**.
- Putting HTTP/Kafka access logic straight inside a business method, making retries, security, and error observability hard to manage.

These three components relate closely yet answer **three distinct questions**:

1. **Channel Adapter:** how do messages **enter or leave** the messaging system, usually under a **one-way** contract?
2. **Gateway:** does the system require **request–reply** and returning a result or error to the right caller?
3. **Service Activator:** which **application handler method** receives the message, and how might that method return a reply?

~~~mermaid
flowchart LR
    EXT["External event source"] --> IN["Inbound Channel Adapter"]
    IN --> CH["Spring MessageChannel"]
    CH --> SA["Service Activator"]
    SA --> OUT["Outbound Channel Adapter"]
    OUT --> SYS["External sink"]
    REQ["External caller"] --> IG["Inbound Gateway"]
    IG --> CH
    SA --> IG
    CH --> OG["Outbound Gateway"]
    OG <--> API["Remote request–reply API"]
~~~

This lesson belongs to the **Channel adapter** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module teaches implementing Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, extensible message flows, practicing **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, along with testing and observing processing branches. The direct topic here is **"Distinguishing adapters from gateways and service activators."**

**Learning outcomes:** you will pick the right endpoint by flow direction and reply requirements; distinguish transport ACKs from business results; understand synchronous/asynchronous error handling; preserve correlation and idempotency; and test inbound/outbound paths in Spring Integration.

## 2. Defining Channel Adapter

Under Enterprise Integration Patterns, a **Channel Adapter** connects an application or external system to a **message channel**, bridging external sources/targets and messaging infrastructure.

There are two directions:

~~~text
Inbound Channel Adapter:
  External source → Adapter → MessageChannel → IntegrationFlow

Outbound Channel Adapter:
  IntegrationFlow → MessageChannel → Adapter → External target
~~~

Adapters typically follow a **one-way messaging** contract: sending or receiving a message **without requiring a business reply** on that endpoint itself.

Examples include reading new CSV files, consuming Kafka records, publishing events to a queue, writing export files, or pushing messages to a remote sink. An outbound call may receive a **transport-level acknowledgement** or throw an exception, yet that is **not automatically an application reply message**.

**Remember:** Adapter does not always mean async. File polling uses a poller, HTTP outbound adapters can block while sending, and Kafka producers can use async callbacks. **One-way** describes the *reply contract*, not strictly threading or execution timing.

## 3. Defining Gateway

A **Messaging Gateway** bridges the request/response call world into a message flow, or calls an external endpoint and retrieves a result:

~~~text
Inbound Gateway:
  External request → Gateway → Request channel
                               ↓
                           Flow handler
                               ↓
  External reply ← Gateway ← Reply message

Outbound Gateway:
  Internal request message → Gateway → Remote request
  Internal reply message   ← Gateway ← Remote reply
~~~

Unlike a one-way Adapter, a request–reply Gateway manages the **result contract**: reply address, correlation, timeouts, and error mapping, depending on protocol and configuration.

There is also the **Java `@MessagingGateway` interface**: Spring Integration generates a proxy so application code invokes a typed method, injecting requests into a flow and receiving replies. It is an **application-facing gateway proxy**, not necessarily the same thing as an HTTP inbound/outbound transport gateway.

**Remember:** Gateway does not mean every call is synchronous end-to-end or every error automatically becomes a business response. Requests can time out, arrive late, or be dropped by a Filter; handling those cases is part of the contract.

## 4. Defining Service Activator

A **Service Activator** routes a message to **an application method**:

~~~text
MessageChannel → Service Activator → businessService.method(payload)
                                        ↓
                                    return value
                                        ↓
                                reply Message (if any)
~~~

A `void` method can consume an event and update state; a DTO-returning method can emit a reply for a request–reply flow. A Service Activator **does not define an external transport protocol** and is not the construct for polling files or consuming Kafka partitions.

Spring Integration configures it via `@ServiceActivator` or DSL `.handle(bean, "method")`/typed handlers. Service methods can have side effects, so you must manage **authorization, transactions, idempotency, retries, and error handling** per domain requirements.

**Remember:** Service Activator connects **messaging → application method**, Gateway provides the **request–reply boundary**, and Channel Adapter connects **external endpoint ↔ messaging** with **one-way** semantics.

## 5. High-level comparison table

| Characteristic | Channel Adapter | Gateway | Service Activator |
|---|---|---|---|
| Goal | Connect messages to external sources/targets | Connect requests to replies | Invoke an application handler method |
| Direction | Inbound or outbound | Inbound or outbound; Java proxy is also a form | From MessageChannel to handler |
| Required reply message | **No** under one-way contract | **Yes** in request–reply mode | **Optional**, depending on method |
| Examples | Kafka inbound, file inbound, file/HTTP outbound adapter | HTTP inbound/outbound gateway, `@MessagingGateway` | `@ServiceActivator`, DSL `.handle(orderService, "place")` |
| Who manages transport? | Adapter + client/container | Gateway + client/container | Not by default; owned by flow/adapter |
| Who handles business logic? | Typically no | Typically delegates to flow | Business service method |
| Timeouts | Poll/send/transport policy | Plus request/reply timeouts and correlation | Handler timeouts / dependency policy |
| Can the endpoint cause side effects? | Yes, when writing to target | Yes, remote/service may commit | Yes, if business method writes |
| Error boundary | Adapter/poller/container | Caller/error reply/transport/container | Caller thread/error channel depending on channel |

**The reply column is not a reliability guarantee.** A Gateway receiving no reply can time out; a one-way Adapter succeeding does not mean the remote finished business logic; a Service Activator returning may still leave internal async side effects unfinished.

## 6. Quick selection with one decision tree

~~~mermaid
flowchart TD
    A["Need to connect a message flow to an external source/target?"] -->|"Yes"| B{"Does the caller need an application reply?"}
    B -->|"No"| C["Inbound/Outbound Channel Adapter"]
    B -->|"Yes"| D["Inbound/Outbound Gateway"]
    A -->|"No, need to invoke an application method"| E["Service Activator"]
    A -->|"Java application calling a flow"| F["@MessagingGateway interface"]
~~~

This is an **initial decision tree**, not a substitute for business analysis:

- External source pushes one-way events → inbound adapter usually fits.
- External HTTP client sends requests and needs responses → inbound gateway.
- Flow publishes events without needing a business reply → outbound adapter.
- Flow calls remote HTTP and needs the response → outbound gateway.
- Flow needs to invoke `OrderService.place()` → Service Activator.
- Java controller wants to invoke a flow via a typed method → `@MessagingGateway` proxy.

**Do not choose an endpoint solely by labels like "HTTP," "Kafka," or "JMS."** Determine one-way vs. request–reply first, then select the endpoint supporting that transport.

## 7. Two Adapter directions do not equal two Gateway directions

The arrows below show **direction relative to the Spring Integration flow**:

~~~text
INBOUND ADAPTER:
External (event producer) ──▶ MessageChannel

OUTBOUND ADAPTER:
MessageChannel ──▶ External (event sink)

INBOUND GATEWAY:
External caller ──▶ MessageChannel
External caller ◀── Reply from MessageChannel

OUTBOUND GATEWAY:
MessageChannel ──▶ External service
MessageChannel ◀── External reply
~~~

**Inbound/outbound** describes direction into or out of the integration application, **not** request/response semantics. Both Adapters and Gateways come in inbound and outbound forms.

For instance, an **HTTP inbound channel adapter** can receive an HTTP request and return a transport response/ACK as configured while **not waiting for a business reply message from the flow**. An **HTTP inbound gateway** is used when the HTTP response must derive from the flow's reply.

## 8. End-to-end example: Orders, Inventory, and Audit

Design four paths:

~~~text
1. Broker event:
   Kafka orders.events
     → Kafka inbound adapter
     → OrderEvent handler

2. Query:
   HTTP GET /orders/{id}
     → HTTP inbound gateway
     → OrderQuery Service Activator
     → HTTP reply

3. Remote reservation:
   Internal command
     → HTTP outbound gateway
     → Inventory API
     ← Reservation reply

4. Audit event:
   Order processing event
     → outbound channel adapter
     → audit topic/file
~~~

Each path has a distinct contract:

| Path | Meaning | Business reply |
|---|---|---|
| Kafka event ingress | Ingest an event for downstream processing | No reply to original producer |
| HTTP order query | Caller asks and waits for data | Yes |
| Remote inventory reservation | Flow needs to know if stock was reserved | Yes |
| Audit sink | Emit one-way audit event | No |

A Service Activator can appear **inside all four flows** whenever a business method must be called. It is a processing step, not a competitor to the transport boundary.

## 9. Message flows and application code should be layered cleanly

A maintainable layout:

~~~text
Transport layer:
  Kafka inbound adapter / HTTP inbound gateway
          ↓
Integration layer:
  MessageChannel → Filter → Router → Transformer
          ↓
Application layer:
  Service Activator → OrderService
          ↓
Integration layer:
  Outbound adapter / outbound gateway
~~~

Clear boundaries help you:

- Swap Kafka for another event source without touching domain logic while message contracts stay intact.
- Replace a remote HTTP API with broker request–reply without exposing details to application ports.
- Unit-test business services independently of the Spring Integration context.
- Test transport serialization and header mapping in isolation at adapters/gateways.
- Place retries and error handling at the right boundary instead of catching all exceptions in one giant method.

**Layering does not mean creating a separate endpoint for every tiny operation.** The goal is ensuring every endpoint has clear responsibilities and message contracts.

## 10. Inbound adapter: polling sources vs. event-driven sources

An inbound adapter can **poll** a source:

~~~text
Poller fixedDelay
  → inspect directory
  → find new file
  → emit Message<File> to channel
~~~

Or be **message-driven**:

~~~text
Kafka/AMQP listener
  → receive record/delivery via callback/container
  → emit Message<Payload> to channel
~~~

**Polling** controls when data is pulled from a source. **Event-driven** lets the source/container invoke the adapter when events appear; underneath, a Kafka consumer still runs Kafka client poll loops, so "message-driven adapter" in Spring Integration describes *how the adapter connects to the flow*, not whether the broker avoids polling internally.

Do not pick a poller just because you want "guaranteed delivery": delivery guarantees also depend on source state, transactions, duplicate detection, error handling, and recovery.

## 11. Outbound adapter: one-way does not mean send equals commit

An outbound adapter emits an event:

~~~text
Message<OrderPlaced>
  → outbound Kafka/AMQP/file/HTTP adapter
  → external destination
~~~

The send call may:

- Return once the local API accepts the request.
- Wait for a transport acknowledgement.
- Time out or hit a network error.
- Fire an async success/failure callback.

However, **an application reply like ReservationResult or PaymentStatus** does not magically appear downstream in the message flow. If you need that response, use an **outbound gateway** or a workflow pairing correlated command and completion events—never assume an outbound adapter returns a typed result.

Never equate **broker publish confirmed**, **consumer ACK**, **downstream database COMMIT**, and **final business outcome**.

## 12. A Service Activator can also act as a request–reply handler

A method:

~~~java
@MessageEndpoint
class OrderQueryEndpoint {
    private final OrderQueryService queries;

    OrderQueryEndpoint(OrderQueryService queries) {
        this.queries = queries;
    }

    @ServiceActivator(
        inputChannel = "orders.query")
    public OrderView get(FindOrderQuery query) {
        return queries.get(query);
    }
}
~~~

Because the method returns `OrderView`, **the Service Activator can emit a reply message**; when the endpoint does not specify a fixed output channel, it can use the request's return address/reply channel under Spring Integration's message-handling rules. This **does not turn the endpoint into a transport Gateway**: the Gateway still owns bringing requests from the caller and returning replies to the external boundary.

Do not add a hardcoded `outputChannel` for a Gateway without checking topology: in request–reply flows, the Gateway sets a temporary `replyChannel`; a custom reply channel must still route cleanly back to the caller rather than stranding results in an unmonitored queue.

## 13. Java records for the end-to-end examples

To illustrate the four boundary types, define a few Java 17 types:

~~~java
record FindOrderQuery(
    String tenantId,
    String orderId
) {}

record OrderView(
    String orderId,
    String status
) {}

record PlaceOrderCommand(
    String tenantId,
    String commandId,
    String orderId
) {}

record ReserveStockCommand(
    String tenantId,
    String commandId,
    String orderId,
    String sku,
    int quantity
) {}

record ReservationResult(
    String commandId,
    String reservationId,
    String status
) {}

record ReservationHttpResponse(
    String requestId,
    String reservationId,
    String state
) {}

record AuditEvent(
    String eventId,
    String operation,
    String outcome
) {}
~~~

These records are **application contracts**, not DTOs supplied by Spring Integration. In production:

- Validate `quantity > 0`, non-null/non-blank IDs, and schema versions.
- Verify `tenantId` from a trusted principal/context, not solely from a caller-supplied body.
- Protect `commandId` as a stable logical idempotency key across retries.
- Distinguish `status=ACCEPTED` from `status=COMMITTED` per contract.
- Use typed errors or reason codes rather than treating every `null` as success.

The standalone examples below reuse these types without assuming they all run together on every input channel.

## 14. Inbound Channel Adapter example: reading files with a poller

An annotation-based configuration:

~~~java
@Configuration
@EnableIntegration
class FileIntakeConfiguration {

    @Bean
    @InboundChannelAdapter(
        channel = "files.incoming",
        poller = @Poller(fixedDelay = "1000"))
    MessageSource<File> orderFiles() {
        FileReadingMessageSource source =
            new FileReadingMessageSource();
        source.setDirectory(new File("/var/app/orders/incoming"));
        return source;
    }
}
~~~

**Flow:**

~~~text
Directory /var/app/orders/incoming
  → FileReadingMessageSource
  → @InboundChannelAdapter + Poller
  → Message<File> on files.incoming
  → Transformer parser/Validator
  → downstream business flow
~~~

The adapter **polls the source and emits messages**. It does not know whether the application succeeded in creating an order; no external caller awaits a reply from `FileReadingMessageSource` itself.

**Production note:** source/file filters should handle file locking, markers or move-to-processed, retry/quarantine, directory permissions, size caps, and duplicate detection. A file can be seen or processed again after a crash; `@Poller` alone does not prove exactly-once behavior.

This snippet requires Spring Integration File imports and version-appropriate annotations; the directory path is illustrative only. Do not read other workspace files to carry out this lesson.

## 15. Message-driven inbound adapter example: receiving from a broker

With Kafka, a common shape is:

~~~text
Kafka topic orders.events
  → Kafka consumer group/container
  → Kafka message-driven inbound adapter
  → Message<OrderEvent> on orders.events.in
  → IntegrationFlow
~~~

A consumer container manages:

- Consumer groups and partition assignments.
- Polling, offset commits, and rebalances.
- Deserialization and container error handling.
- Transport retries/DLTs when configured.

The inbound adapter turns records into Spring messages. **Never confuse broker offset commits / consumer ACKs with a business reply to the producer**; a Kafka producer does not automatically receive an `OrderReceipt` when a consumer reads a record.

With RabbitMQ/JMS, listener adapters have different ACK/redelivery semantics than Kafka. Calling an inbound adapter message-driven does not guarantee subscribers run on the caller thread or prevent duplicate processing.

## 16. Outbound Channel Adapter example: emitting an audit event

When a flow only needs to send an audit event to an external HTTP endpoint without reading a business result:

~~~java
@Bean
IntegrationFlow auditOutboundFlow() {
    return IntegrationFlow.from("audit.out")
        .handle(
            Http.outboundChannelAdapter(
                    "https://audit.example.invalid/events")
                .httpMethod(HttpMethod.POST))
        .get();
}
~~~

This is an **outbound channel adapter**. It sends the payload to a remote sink without turning the HTTP response body into an `AuditResult` reply message continuing through the flow.

The address `audit.example.invalid` is a placeholder, not a real URL. Production setups must configure serializers, request factories/HTTP clients, TLS/authentication, timeouts, response status/error classifiers, quotas, and retries. Never send unnecessary secrets or PII in audit payloads.

**Rule:** if callers need certainty that the audit record was **persisted remotely**, sending HTTP and observing a transport status may be insufficient; define an explicit remote API contract, callback/status check, or a request–reply gateway if a business response exists.

## 17. Outbound adapter writing a file vs. business commit

A data-export adapter:

~~~text
Business service → Message<OrderExport>
  → Transformer to CSV
  → File outbound adapter
  → /exports/orders-501.csv
~~~

A file outbound adapter performs I/O, yet **a written file does not mean the external consumer imported the data into its system**.

Questions to ask:

- Is the file written atomically or left partial if the process crashes?
- On retry of the same message, does it overwrite, append, or create duplicate files?
- Is there a marker or idempotent filename?
- If the file was written before the broker offset committed, will redelivery write a second file?
- Does the downstream partner send an **ingestion acknowledgement** afterward or rely solely on file arrival?

If the partner must return ingestion results, it is a **two-way workflow**, no longer solved by a single one-way outbound adapter. Use two adapters for correlated command/completion messages, or a gateway if the protocol is genuinely request–reply.

## 18. HTTP inbound Gateway example: client waiting for a result

A request–reply HTTP endpoint:

~~~java
@Bean
IntegrationFlow orderHttpQueryFlow(
        OrderQueryService queries) {
    return IntegrationFlow
        .from(
            Http.inboundGateway("/orders/query")
                .requestMapping(m -> m.methods(HttpMethod.POST))
                .requestPayloadType(FindOrderQuery.class))
        .handle(
            FindOrderQuery.class,
            (query, headers) -> queries.get(query))
        .get();
}
~~~

Contract:

~~~text
HTTP request
  → Inbound Gateway
  → Message<FindOrderQuery>
  → Service handler returns OrderView
  → Reply message
  → Gateway maps response to HTTP
~~~

**Never use an inbound channel adapter** when the HTTP client needs `OrderView` itself as the response. A one-way inbound adapter may return a configured transport response **without waiting for business data from the flow**.

This DSL snippet shows structure only; running it requires HTTP message converters, method/status mappings, authentication, and error mappings matching your Spring Integration version. If content negotiation or response serialization is wrong, a valid `OrderView` inside the JVM can still fail to produce a proper HTTP response.

## 19. HTTP outbound Gateway example: response body required

Reserving inventory via a remote API:

~~~java
@Bean
IntegrationFlow reserveStockRemoteFlow() {
    return IntegrationFlow.from("stock.reserve.remote")
        .handle(
            Http.outboundGateway(
                    "https://inventory.example.invalid/reservations")
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(
                    ReservationHttpResponse.class))
        .get();
}
~~~

Contract:

~~~text
Message<ReserveStockCommand>
  → HTTP outbound gateway
  → remote Inventory API
  ← HTTP response body
  ← Message<ReservationHttpResponse> in flow
~~~

The Gateway lets the flow **receive the response message for further processing**. A Transformer must inspect `requestId`/`commandId`, `reservationId`, `state`, schema, and tenant before producing `ReservationResult`. If the remote returns 202 Accepted, you may only have a pending reference rather than a committed reservation.

For a real API, configure request mappers/JSON converters, authentication, and HTTP status mappings; this snippet only illustrates endpoint choice. **Never translate a 503 or network timeout into `OUT_OF_STOCK`**.

## 20. `@MessagingGateway` example: application calls a flow like a method

A Gateway interface:

~~~java
@MessagingGateway
interface StockApplicationGateway {

    @Gateway(requestChannel = "stock.reserve.remote")
    ReservationHttpResponse reserve(
        ReserveStockCommand command);
}
~~~

Caller:

~~~java
@Service
class CheckoutUseCase {
    private final StockApplicationGateway stock;

    CheckoutUseCase(StockApplicationGateway stock) {
        this.stock = stock;
    }

    ReservationHttpResponse reserve(ReserveStockCommand command) {
        return stock.reserve(command);
    }
}
~~~

Differences:

- **`@MessagingGateway`:** Java application method → request message → awaits reply (per method signature/contract).
- **HTTP outbound Gateway:** message in flow → HTTP remote call → reply message.
- **Service Activator:** message in flow → local service method → optional reply.

All three layers **can sit in the same chain**. They are not 1:1 substitutes for one another.

~~~text
CheckoutUseCase
  → StockApplicationGateway [Java proxy]
  → stock.reserve.remote [request channel]
  → HTTP outbound Gateway [transport request–reply]
  → Inventory API
  ← ReservationHttpResponse
  ← StockApplicationGateway
  ← CheckoutUseCase
~~~

Spring Integration must enable scanning/registration of Gateway interfaces, such as `@IntegrationComponentScan` in appropriate configuration. In production, have application ports return **domain results** rather than coupling the entire business layer to remote HTTP DTOs.

## 21. Service Activator example: processing internal commands

A command service:

~~~java
@Service
class OrderCommandService {
    private final OrderRepository orders;

    OrderCommandService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public OrderView place(PlaceOrderCommand command) {
        validateAndAuthorize(command);
        return orders.createIdempotently(command);
    }

    private void validateAndAuthorize(PlaceOrderCommand command) {
        // Application implements validation/authorization.
    }
}
~~~

An endpoint:

~~~java
@MessageEndpoint
class PlaceOrderActivator {
    private final OrderCommandService orders;

    PlaceOrderActivator(OrderCommandService orders) {
        this.orders = orders;
    }

    @ServiceActivator(inputChannel = "orders.place")
    public OrderView place(PlaceOrderCommand command) {
        return orders.place(command);
    }
}
~~~

Here `PlaceOrderCommand`, `OrderRepository`, and `createIdempotently()` are **application abstractions** to be implemented. The Service Activator dispatches to the right method; `@Transactional` on the business service manages transactions when invoked via the Spring proxy. **Do not assume Service Activator automatically enables transactions or idempotency**.

If an external request needs `OrderView` returned over HTTP, the **HTTP inbound Gateway** (or a Controller calling `@MessagingGateway`) owns transport and reply handling. Service Activator only knows how to call `orders.place()`.

## 22. One flow can contain all three roles

~~~mermaid
sequenceDiagram
    participant Client as HTTP client
    participant IG as HTTP Inbound Gateway
    participant SA as Service Activator
    participant OG as HTTP Outbound Gateway
    participant Inventory as Inventory API
    Client->>IG: POST /orders
    IG->>SA: PlaceOrderCommand message
    SA->>SA: Validate + persist intent
    SA->>OG: ReserveStockCommand message
    OG->>Inventory: POST /reservations
    Inventory-->>OG: ReservationResult
    OG-->>IG: Completion reply (after workflow)
    IG-->>Client: HTTP response
~~~

This diagram shows a **conceptual workflow**. Running it properly requires Routers/Transformers, transaction boundaries, reply routing, error handling, and orchestration state across steps. Do not treat a sequence diagram as an automatic link between `Service Activator` and `Outbound Gateway`.

If a business workflow is long-running or needs extensive retries or compensation, **do not hold a synchronous HTTP Gateway open for minutes** just to mimic a method call. Return `ACCEPTED/PENDING` after persisting durable intent, then use status queries or completion events where appropriate.

## 23. Channel Adapter and Gateway differ in reply semantics

| Scenario | Outbound Adapter | Outbound Gateway |
|---|---|---|
| Send an `AuditEvent`, no response body needed | Suitable | Usually overkill |
| Send POST and need `ReservationResult` | No business reply by pattern | Suitable |
| Remote returns HTTP 202 | May just be transport/accepted response | Can map to `PENDING` per contract |
| Remote returns 503 error | Send/handler can fail | Request–reply call can fail |
| Client times out after server commit | Outcome remains uncertain | Outcome remains uncertain |
| Emit event to Kafka | Suitable | Use gateway only if a reply protocol is designed |

**Do not say Adapters never receive any transport-level response.** Client libraries can observe HTTP status codes or broker publish acknowledgements. The difference lies in the **message-reply contract back to the flow/caller**, not whether network response bytes exist.

## 24. Gateway and Service Activator differ in responsibility boundaries

| Question | Gateway | Service Activator |
|---|---|---|
| Who invokes it? | External caller or Java application/flow | Upstream message channel |
| Who receives the result? | Gateway caller/request | Potentially downstream flow/Gateway |
| Remote protocol? | Can use HTTP/AMQP/JMS gateway directly | Has no transport of its own |
| Business validation? | Can pre-filter/map | Business service must validate |
| Executes side effects? | Remote call can cause side effects | Method can cause side effects |
| Retries? | Transport/call policy | Handler/advice/business policy |
| Reply correlation? | Essential for request–reply, especially async | Does not create cross-process correlation by itself |

A Gateway can invoke a Service Activator and receive its reply, so **it is not "Gateway vs. Service Activator"** when both are needed. A request–reply pipeline commonly pairs a Gateway **at the boundary** with a Service Activator **at the processing stage**.

## 25. Choose endpoints by requirements, not method names

Suppose a method is named `send()`:

~~~java
void send(AuditEvent event);
~~~

The name `send` does not tell you whether to use an adapter or a gateway: it could be a one-way Java Gateway method, or a POJO invoked by a Service Activator while an adapter handles outbound transport.

Likewise, a `place()` method returning `OrderView` does not turn it into a transport Gateway. And an outbound HTTP adapter blocking on the network **does not make it** a request–reply Gateway.

Check **direction, caller, contract, return address, side effects, and retry/error boundaries** before picking a component.

## 26. Reply channel: what happens if a handler returns no reply?

Suppose an external HTTP caller sends a request to an **inbound Gateway**, expecting an `OrderView`:

~~~text
HTTP client
  → Inbound Gateway
  → Filter rejects and discards
  → no reply message
  → HTTP request waits until reply timeout
~~~

A Filter returning `false` can be valid in **one-way event ingestion** when skipping events is allowed. In a **request–reply flow**, however, silent discards cause the caller to hit an **unexplained timeout**.

Clearer designs:

- **Fail-fast:** throw a typed validation exception and map it to an HTTP 4xx / response with a reason code.
- **Typed rejection:** have the handler return `OrderRejected(reasonCode)` instead of nothing.
- **Async accepted:** for long work, return `OrderPending(statusReference)` **after persisting durable intent**, without pretending completion.

**A discard channel is not automatically an error reply channel.** If a discard flow must return a rejection, wire it deliberately to the return address while verifying correlation and the Gateway contract.

## 27. Is a `void`-returning Service Activator appropriate?

One-way example:

~~~java
@MessageEndpoint
class AuditActivator {
    private final AuditService audit;

    AuditActivator(AuditService audit) {
        this.audit = audit;
    }

    @ServiceActivator(inputChannel = "audit.in")
    public void record(AuditEvent event) {
        audit.record(event);
    }
}
~~~

If upstream simply emits an event, `void` fits well. If a **synchronous Gateway awaits a business result** while the Service Activator returns `void` and nothing else builds a reply, the caller can time out.

**A `void` handler succeeding does not safely turn a Gateway into one-way if the caller expects a reply.** Choose the contract right at the application boundary:

- One-way `void` or fire-and-forget when no result is genuinely needed.
- Typed request–reply method when success/rejection/pending is needed.
- Async workflow with durable status when awaiting the final result is impractical.

If a handler creates a side effect and returns `null`, a Gateway timeout does not undo that side effect. Caller retries must reuse **the same logical command ID** to prevent double writes.

## 28. Error channel, reply channel, and discard channel are three distinct things

A flow can involve:

~~~text
Request Message
  ├── replyChannel → successful or meaningful result for caller
  ├── errorChannel → errors at boundaries supporting error messaging
  └── discardChannel → messages dropped by a Filter per policy
~~~

| Channel / context | What does it carry? | Automatically replies to caller? |
|---|---|---|
| **Reply channel** | Request's result message | Possibly, if wired to gateway caller |
| **Error channel** | Usually `ErrorMessage(Throwable)` | Not automatically a business reply |
| **Discard channel** | Message discarded by Filter | Not automatically an error response |
| **DLQ/DLT** | Broker-side message/recovery evidence | Not a synchronous gateway reply |

Never use `errorChannel` as a "success response sink," and never dump every business rejection into a DLQ. An `OUT_OF_STOCK` outcome can be a **valid business result**, not a transport failure.

## 29. Synchronous vs. asynchronous changes where errors are caught

~~~mermaid
flowchart TD
    IN["Inbound message"] --> D{"Boundary"}
    D -->|"DirectChannel"| SYNC["Handler on sender thread"]
    D -->|"ExecutorChannel / listener / poller"| ASYNC["Worker thread"]
    SYNC -->|"Throws"| CALLER["Caller exception path"]
    ASYNC -->|"Throws"| ERROR["ErrorMessage / container recoverer"]
    SYNC -->|"Returns"| REPLY["Reply if contract expects"]
    ASYNC -->|"Returns"| STATUS["Async completion/transport policy"]
~~~

**Synchronous DirectChannel:** exceptions typically propagate on the caller thread; not every error moves automatically to global `errorChannel`.

**ExecutorChannel/broker/poller:** handlers can throw after `send()` has already returned; you need error handlers/recoverers at **the exact async boundary**. ACKing the source before durable processing finishes risks losing work if the JVM crashes.

**Service Activator alone does not determine sync/async execution.** Channel types, pollers, schedulers, transport adapters, and handler behavior together determine it.

## 30. Four failure windows across Adapter/Gateway/Service Activator

Suppose an inbound adapter receives `PlaceOrderCommand`, a Service Activator writes the DB, and an outbound adapter emits an event:

~~~text
T1 Broker receives event.
T2 Inbound adapter feeds message into flow.
T3 Service Activator begins transaction.
T4 DB commits order.
T5 Outbound adapter publishes completion event.
T6 Inbound source ACKs / commits offset.
~~~

| Where does crash occur? | Risk | Mitigation |
|---|---|---|
| Before T2 | Message may be redelivered | Transport durability/ACK policy |
| After T2, before T4 | Processing uncommitted | Retry if transaction rolled back cleanly |
| After T4, before T6 | Redelivery causes double write | Durable idempotency/inbox |
| After T5 publish, before mark sent | Completion event may republish | Outbox + consumer dedupe |

With a request–reply Gateway, there is an extra window: **business COMMIT succeeds, yet the reply arrives late or is lost**. A Gateway timeout is only what the caller observed—**not proof of transaction rollback**.

## 31. Transport acknowledgement is not business outcome

A Kafka producer receives a publish acknowledgement:

~~~text
Producer → Broker ACK
Broker → Consumer group processes later
Consumer → Service Activator commits business DB
~~~

The producer's ACK can occur **before** the consumer ever runs. Likewise, RabbitMQ consumer ACKs or Kafka offset commits reflect transport progress; they do not automatically guarantee external business systems finished all downstream effects.

With an HTTP outbound channel adapter, an HTTP 202 Accepted may mean the remote **accepted the request for deferred processing**, not that email/payment/order placement succeeded.

If the application needs to know the remote **finished**, design a reply/callback/status workflow rather than fabricating a typed business result out of a transport ACK.

## 32. Retry: Adapter and Gateway require different strategies

| Endpoint | Common failures | Retry considerations |
|---|---|---|
| File inbound adapter | Locked file, partial read, parse error | Retry/quarantine, file identity, atomic rename |
| Kafka inbound adapter | Deserializer error, rebalance, handler failure | Offset commit/DLT/recovery, domain dedupe |
| HTTP outbound adapter | Connect/read timeout, 429/503 | Remote side effect may already have occurred |
| HTTP outbound gateway | Remote timeout, invalid reply/correlation | Unknown outcome; reuse same idempotency key |
| Service Activator | DB deadlock, validation failure, conflict | Transaction rollback, permanent vs. transient |
| Java `@MessagingGateway` | Send timeout, reply timeout, caller retry | Never generate a new commandId for the same logical command |

**Never blindly retry every exception.** Malformed payloads, unauthorized operations, or same-id/different-payload conflicts rarely become valid when retried verbatim. Network timeouts after side-effecting requests require **reconciliation**.

Wrapping an endpoint with `RequestHandlerRetryAdvice` wraps only **that handler**. Failures in downstream async workers may lie outside the advice's scope; never assume one retry policy covers the entire flow.

## 33. Gateway timeouts and the "unknown outcome" state

Timeline:

~~~mermaid
sequenceDiagram
    participant A as Application
    participant G as Gateway
    participant W as Worker
    participant DB as Database
    A->>G: place(commandId=C-701)
    G->>W: Request message
    W->>DB: Create order
    DB-->>W: COMMIT
    Note over G: Reply timeout
    G-->>A: Timeout / unknown outcome
    W--xG: Late reply
    A->>G: Retry same commandId C-701
    G->>W: Same logical command
    W-->>G: Cached committed result
    G-->>A: OrderPlaced once
~~~

A Gateway does not turn a remote call into a local method call with atomic cancellation. When the caller times out, the worker may have committed or still be running.

**Deduplication:**

1. Keep `commandId` in the domain contract.
2. Enforce a unique constraint in the DB inbox/processed table on tenant/operation/commandId.
3. Store a fingerprint to catch same-key/different-command conflicts.
4. If already committed, return the stored durable result.
5. If remote effects are uncertain, use remote idempotency/reconciliation.

Changing `replyChannel` or Gateway call identities per attempt is normal; **changing the business command ID** across retries of the same intent is dangerous.

## 34. Correlation between Gateway and Aggregator

A request may split into three branches:

~~~text
Gateway quote(Q-701)
  → Splitter
     → price task (member A)
     → tax task (member B)
     → discount task (member C)
  → Aggregator
  → QuoteResult
  → Gateway reply
~~~

The **Gateway reply address** answers **the waiting call**. The **Aggregator correlation ID** groups the three members of one logical workflow; the two IDs may relate, yet they are distinct concepts.

A sound design:

- Parent group ID scoped by tenant/request/revision; never use trace IDs as business groups.
- Members A/B/C carry unique identities and an expected manifest.
- Child failures yield typed failure outcomes or a whole-group failure policy rather than silent drops that hang forever.
- Duplicate child messages never count as new members.
- Release/expiry policies handle partial or failed groups.
- Return addresses are preserved/mapped properly across transports, or backed by durable result lookup if the caller already timed out.

An **Inbound Channel Adapter** consuming events without needing replies does not turn into an Aggregator caller on its own. If a workflow must send final status to an external system, design an outbound result event/notification or an appropriate Gateway.

## 35. Service Activator methods with side effects and transaction boundaries

Unsafe example:

~~~java
@ServiceActivator(inputChannel = "orders.preview")
public OrderView preview(FindOrderQuery query) {
    orders.createOrder(query.orderId()); // Violates business intent.
    return orders.getOrder(query.orderId());
}
~~~

A method named `preview` can still write to the DB. No annotation automatically proves a handler is read-only.

Safer example:

~~~java
@ServiceActivator(inputChannel = "orders.preview")
public OrderView preview(FindOrderQuery query) {
    return orderQueries.get(query);
}
~~~

Separate read-only query methods from command methods, validate/authorize in business terms, place transactions on Spring-managed business services, and enforce idempotency for side-effecting commands.

**Never place `@Transactional` on the caller and assume the transaction spans an ExecutorChannel or broker.** Transaction context binds to threads/managers; workers need their own transaction boundaries.

## 36. Adapters should not swallow all business logic

An inbound adapter may perform necessary technical work: parsing metadata, converting bytes to messages, mapping transport headers, and ACKing/retrying. However, if you cram business processing into the adapter callback:

~~~java
void onKafkaRecord(ConsumerRecord<String, String> record) {
    Order order = parse(record.value());
    inventory.reserve(order);
    payment.charge(order);
    email.sendReceipt(order);
    acknowledgment.acknowledge();
}
~~~

then **transport, business rules, side effects, and ACK logic become tangled**: hard to test per layer, hard to swap brokers, and hard to manage committed side effects when later steps fail.

Separate responsibilities:

~~~text
Kafka inbound adapter
  → decode/validate
  → route
  → Service Activator: domain command handler
  → transactional inbox/outbox
  → Outbound adapter: publish completion event
~~~

You do not need a separate class for every line of code; the goal is making boundaries and failure semantics **reviewable, testable, and operable**.

## 37. Gateways should not become a "business God Object"

A Gateway interface:

~~~java
@MessagingGateway
interface DangerousGateway {
    Object execute(String methodName, Object payload);
}
~~~

If a flow lets callers supply arbitrary method or bean names to invoke dynamically, it risks **arbitrary method invocation** or routing into handlers with write/cancel privileges.

Replace with a typed API:

~~~java
@MessagingGateway
interface OrderApplicationGateway {
    @Gateway(requestChannel = "orders.preview")
    OrderView preview(FindOrderQuery query);

    @Gateway(requestChannel = "orders.place")
    OrderView place(PlaceOrderCommand command);
}
~~~

These are two **distinct operations**, eligible for distinct authorization and retry policies. **Gateway interfaces do not enforce permissions by themselves**; ingress adapters and business services must authorize tenant, principal, and operation.

Never funnel all outbound HTTP calls through one endpoint accepting arbitrary URLs from payloads controllable by external callers: that opens SSRF or unauthorized internal service access.

## 38. Where do Transformer and Router fit among the three components?

An IntegrationFlow:

~~~text
Inbound Adapter/Gateway
  → Transformer: wire DTO → canonical payload
  → Filter: schema/business preconditions
  → Router: choose operation/workflow branch
  → Service Activator: invoke business method
  → Transformer: domain result → external DTO
  → Outbound Adapter/Gateway
~~~

**Transformers** convert payload types/representations; they are not outbound transports themselves. **Routers** select channels; they do not send HTTP requests without a downstream outbound endpoint. **Filters** allow or drop messages and must never trigger business side effects inside predicates.

Choose **Gateway** when a result must return; choose **Adapter** when one-way. **Service Activator** sits where application methods are invoked and can emit replies back to a Gateway.

**Never treat a Filter discard as a rejection reply.** A Gateway whose request is silently dropped risks timing out.

## 39. Preserving headers and distinguishing identity types

A message carries:

~~~text
payload.commandId = C-701
payload.orderId = O-701
headers.businessCorrelationId = tenant-a|O-701|revision-1
headers.traceId = trace-abc
headers.replyChannel = <temporary channel object>
headers.errorChannel = <configured error return address>
headers.kafka_receivedPartitionId = 2
headers.kafka_offset = 71
~~~

| Field | Purpose | Should not be used in place of |
|---|---|---|
| `commandId` | Durable idempotency / business operation | Spring Message ID |
| `businessCorrelationId` | Grouping a logical workflow | Return address, trace ID |
| `traceId` | Tracing call chains | Business groups or authorization |
| `replyChannel` | Replying to the invocation caller | Cross-broker business ID |
| `errorChannel` | Error routing in supporting topologies | Guaranteed terminal outcome |
| Kafka partition/offset | Source position / replay | System-wide domain idempotency |

Across external transports, **Spring JVM channel objects are not portable wire contracts**. Adapters and gateways must map headers via allowlists per protocol (HTTP headers, AMQP reply-to, Kafka correlation). Whenever domain identity must survive retries or restarts, carry it in the wire DTO or durable mappings.

## 40. Choose the end-to-end delivery contract before choosing adapter/gateway

| Need | Design to consider |
|---|---|
| Receive events, process as resources allow | Inbound adapter + durable source ACK/retry/DLT |
| Push events to another system, no result needed | Outbound adapter + delivery confirmation / Outbox |
| HTTP client needs data immediately | Inbound gateway + reply result/exception mapper |
| Flow needs remote response immediately | Outbound gateway + correlation/timeout |
| Java service wants to call a flow like a method | `@MessagingGateway` interface |
| Execute a domain command once a message exists | Service Activator + transaction/idempotency |
| Long-running business flow needing eventual status | Durable command/event workflow + callbacks/status, potentially using adapters |

Two follow-up questions:

1. **Who owns retries if a request fails halfway?** External caller, inbound container, handler advice, workflow manager, or one single layer with a budget?
2. **When is it safe to ACK?** Upon source reception, durable intent persistence, or full business completion?

There is no single answer across Kafka, HTTP, JMS, files, and AMQP. Decide based on API contracts and the domain's tolerance for crashes and duplicates.

## 41. Unit test: Service Activator invokes the right business method

To verify a query message never invokes a side-effecting write method, mock the business services:

~~~java
@Test
void queryActivatorDoesNotInvokeWriteService() {
    OrderQueryService queries = mock(OrderQueryService.class);
    OrderCommandService writes = mock(OrderCommandService.class);

    FindOrderQuery query =
        new FindOrderQuery("tenant-a", "O-701");
    OrderView expected = new OrderView("O-701", "CREATED");
    when(queries.get(query)).thenReturn(expected);

    OrderQueryEndpoint activator =
        new OrderQueryEndpoint(queries);
    OrderView result = activator.get(query);

    assertEquals(expected, result);
    verify(queries).get(query);
    verifyNoInteractions(writes);
}
~~~

**This test only verifies the Java business wrapper**, not Spring Integration dispatching to the right `@ServiceActivator`. To test channel/method binding, write an integration test sending messages through real channels and asserting writes are untouched.

`OrderQueryService` and `OrderCommandService` are application abstractions; the test uses JUnit 5/Mockito and needs matching imports and configuration.

## 42. Integration test: request–reply Gateway invoking a Service Activator

In an isolated Spring test context:

~~~java
@MessagingGateway(
    defaultRequestChannel = "test.orders.query")
interface TestOrderGateway {
    OrderView query(FindOrderQuery input);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class GatewayTestConfiguration {

    @Bean
    IntegrationFlow testOrderQueryFlow() {
        return IntegrationFlow.from("test.orders.query")
            .handle(
                FindOrderQuery.class,
                (query, headers) ->
                    new OrderView(query.orderId(), "CREATED"))
            .get();
    }
}
~~~

Testing once `TestOrderGateway` is scanned/registered:

~~~java
@Autowired
TestOrderGateway gateway;

@Test
void gatewayReturnsTypedReply() {
    OrderView reply = gateway.query(
        new FindOrderQuery("tenant-a", "O-701"));

    assertEquals("O-701", reply.orderId());
    assertEquals("CREATED", reply.status());
}
~~~

One reply message from the typed handler suffices for the Java gateway to return a typed result synchronously. **The caller does not construct `MessageBuilder`, manage `replyChannel`, or cast payloads manually**. That is the benefit of `@MessagingGateway`.

To run this test, the project needs JUnit Spring test annotations and imports, gateway scanning on the right package, and no competing consumers from production configuration registered on the same channel.

## 43. Integration test: one-way outbound adapter produces no business reply

Suppose a fake HTTP server accepts audit POST events and returns:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"receiptId":"A-701","state":"PENDING"}
~~~

For an outbound **channel adapter**:

- Assert the fake server received the expected URL, method, body, and headers.
- Assert the endpoint does not emit an `AuditReceipt` reply message onto a downstream channel **just because the server returned a body**.
- If the server returns HTTP 500, assert the error path executes properly.
- If a send times out after remote commit, do not assume the event was never received.
- Test that replaying the same eventId does not double remote side effects per remote policy.

If the application needs `receiptId` for subsequent steps, **switch to an outbound HTTP Gateway** and map the response type rather than stretching a one-way adapter's HTTP 202 into an undefined result.

**Do not test "no reply" by calling a mocked sender:** mocks skip the actual HTTP adapter. Use a fake HTTP server with the real IntegrationFlow and adapter.

## 44. Integration test: outbound Gateway returns a typed remote reply

A fake Inventory API:

~~~http
POST /reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: C-701

{"commandId":"C-701","sku":"SKU-5","quantity":2}
~~~

returns:

~~~json
{
  "requestId": "C-701",
  "reservationId": "RSV-701",
  "state": "RESERVED"
}
~~~

The test should verify:

1. The Gateway sends **exact wire JSON and headers**.
2. Correlation matches `requestId == commandId`.
3. The HTTP client converter decodes `ReservationHttpResponse` cleanly.
4. The Transformer checks status and constructs the right `ReservationResult`.
5. HTTP 409/422/503 map appropriately without turning into `RESERVED`.
6. Network timeouts after remote commit map to **unknown outcome/reconciliation**, not a definite business failure.

**Fire two concurrent requests** and return out-of-order replies; each caller must receive its own reservation. With a synchronous HTTP client per invocation, responses map to specific requests; when moving to broker request–reply, rely on a real reply-to/correlation protocol rather than queue ordering.

## 45. Integration test: inbound adapter emits messages without caller replies

With a file source or fake broker adapter:

~~~text
External source → Inbound adapter
  → files.incoming / orders.events.in
  → TestChannel / capture handler
~~~

Assertions:

- Each **source item** produces the exact payload/header contract when picked up by the adapter.
- Invalid source items follow rejection/quarantine policy.
- The poller does not spin aggressively and cause CPU/broker pressure.
- Source items reprocessed after a crash behave idempotently.
- External senders are never assumed to receive a typed `OrderView` merely because a message entered a channel.
- Stopping and restarting the adapter recovers properly.

**Counting messages alone cannot prove delivery semantics.** For file adapters, verify files remain or move cleanly to processed directories; for broker adapters, verify ACK/offset commits and fault injection.

## 46. Failure injection: committed, yet caller never receives reply

Scenario:

~~~text
1. HTTP Inbound Gateway receives PlaceOrderCommand C-701.
2. Service Activator writes order + inbox, COMMIT.
3. HTTP client disconnects before receiving the response.
4. Client resends C-701.
5. Business service returns cached receipt; no new order is created.
~~~

Test against a real DB/inbox:

~~~java
@Test
void retryWithSameCommandDoesNotCreateDuplicateOrder() {
    PlaceOrderCommand cmd =
        new PlaceOrderCommand("tenant-a", "C-701", "O-701");

    OrderView first = orderCommands.place(cmd);
    OrderView replay = orderCommands.place(cmd);

    assertEquals(first, replay);
    assertEquals(1, orders.countByOrderId("O-701"));
}
~~~

`orderCommands` and `orders` are application test fixtures/repositories backed by a real unique constraint / inbox implementation. To test the **Gateway failure window**, also inject crashes/network drops after commit and before reply at the HTTP boundary; calling the handler twice does not substitute for transport testing.

**Never wrap the test method itself in an outer `@Transactional`** that keeps both calls inside one uncommitted transaction; test real commit boundaries.

## 47. Testing differences between error channels and Filter discards

Suppose:

~~~text
One-way adapter:
  invalid event → Filter discard allowed → skipped metric.

Request–reply Gateway:
  invalid command → Filter discard → caller timeout (bad design).
  invalid command → typed rejection → caller receives useful error.

Async handler:
  unexpected failure → ErrorMessage / container recoverer.
~~~

Test assertions:

- One-way intentional skips produce no side effects.
- Gateway invalid inputs never degrade into "network timeouts" when the reason is already known.
- Handler exceptions on `DirectChannel` surface through the synchronous caller path.
- Handler exceptions on `ExecutorChannel` reach the configured error path.
- Error handlers never swallow failures and ACK the source without saving durable recovery state.
- DLQs never collect raw secrets or unnecessary PII.

**Never claim every exception enters `errorChannel` automatically.** Deserializer failures can occur **before any Spring Message exists**, and async worker runtime errors do not return directly to callers automatically.

## 48. Testing concurrency, ordering, and duplicate delivery

A broker inbound adapter has three consumers in a group processing records independently. A downstream Service Activator can write the same order under two conditions:

~~~text
EV-701  O-701 version 1
EV-702  O-701 version 2

Producer publishes order key = tenant-a|O-701
→ same Kafka partition with stable mapping
→ inbound adapter
→ ExecutorChannel thread pool
→ EV-702 may commit before EV-701
~~~

Tests:

1. Same key → consistent producer partition assignment.
2. Rebalance/replay → duplicate events produce no second side effect.
3. Executor concurrency → version guard rejects stale state updates.
4. Offset ACK/commit never precedes durable completion without a safe handoff.
5. A Filter discard never leaves an Aggregator short a child or reporting false success.
6. Outbound adapter publishes events under an idempotent/outbox policy.

**An IntegrationFlow's outcome is determined by the entire topology**, not just whether the first endpoint is an Adapter or a Gateway.

## 49. Test matrix for choosing endpoints

| Scenario | Expected component | What must be proven |
|---|---|---|
| New file appears | File inbound adapter | Emits file message; poll/recovery works |
| Kafka event enters flow | Kafka inbound adapter | Group/offset/error semantics accurate |
| Fire-and-forget audit | Outbound adapter | External sink receives event; no fake business reply |
| HTTP client needs `OrderView` | HTTP inbound gateway | Caller receives expected reply |
| Flow needs Inventory response | HTTP outbound gateway | Typed reply, accurate correlation |
| Java service wants to call flow | `@MessagingGateway` | No manual MessageChannel/header boilerplate |
| Message needs to call `OrderService.place()` | Service Activator | Right method/transaction/idempotency |
| `void` handler in request–reply | Gateway contract mismatch | Does not silently time out |
| Filter rejects client input | Gateway typed rejection | Does not turn validation into timeout |
| HTTP 202 from outbound adapter | One-way adapter | Not treated as domain completion |
| Remote reply has wrong request ID | Outbound gateway | Rejects mismatch |
| Remote commits then times out | Gateway + business policy | Reconciles / reuses idempotency key |
| Broker crashes after DB commit | Inbound adapter + handler | Redelivery creates no double write |
| DLT unavailable | Adapter/container recovery | Does not drop source record |
| Multiple child replies | Splitter/Aggregator + Gateway | Parent correlation / member identity |
| Spoofed auth header | Ingress + business handler | Rejects tenant/operation |
| Client-supplied external URL | Outbound adapter/gateway | Allowlist / SSRF prevention |

The goal is not writing redundant tests, but ensuring **every boundary type has an observable contract**: right caller behavior, right reply semantics, right transport failure behavior, and right business effects.

## 50. Metrics: measuring message transport vs. business completion

The metric names below are **application-layer suggestions**, not Spring Integration's complete default metric set:

| Metric | Why track it |
|---|---|
| `inbound.adapter.received.count` | Messages brought from sources into flows |
| `inbound.adapter.source.read.failure.count` | File/broker source read errors |
| `inbound.adapter.ack.failure.count` | Source ACK/offset commit failures |
| `outbound.adapter.send.attempt.count` | Outbound sends to remote sinks |
| `outbound.adapter.send.failure.count` | Transport send failures |
| `gateway.request.count` | Logical calls expecting replies |
| `gateway.reply.success.count` | Valid replies received |
| `gateway.reply.timeout.count` | Replies not received by deadline |
| `gateway.reply.late.count` | Replies arriving after deadline |
| `gateway.correlation.mismatch.count` | Replies failing request correlation |
| `service.activator.invocation.count` | Handler execution count |
| `service.activator.business.commit.count` | Successful durable effects |
| `service.activator.duplicate.suppressed.count` | Blocked duplicates |
| `error.channel.messages.count` | Errors routed to error recovery |
| `quarantine.pending.count` | Unresolved terminal rejections |
| `integration.flow.duration` | End-to-end flow latency |

Never equate `adapter.received.count` with `service.activator.business.commit.count`. Events can be legitimately dropped by Filters, retried, permanently failed, or queued asynchronously.

Keep metric label cardinality bounded (`flowName`, `endpointName`, `operation`, `outcome`, `reasonCode`). Never put raw payloads, emails, commandIds, or message IDs into metric labels; keep IDs in access-controlled structured logs and traces.

## 51. Observing a message traverse all three components

Example structured log:

~~~text
eventId=EV-701
sourceAdapter=kafka-orders-inbound
sourceTopic=orders.events
sourcePartition=2
sourceOffset=71
flowName=order-intake
handler=OrderCommandService.place
businessCommandId=C-701
transactionOutcome=COMMITTED
outboundAdapter=order-completion-publisher
publishOutcome=ACKNOWLEDGED
~~~

For an outbound Gateway:

~~~text
businessCommandId=C-701
gatewayName=inventory-reservation-http
transportAttempt=2
remoteRequestId=INV-701
replyOutcome=TIMEOUT
businessOutcome=UNKNOWN
reconciliationStatus=PENDING
~~~

**Never conclude `businessOutcome=FAILED` solely because `replyOutcome=TIMEOUT`.** A remote service may have committed before the response dropped.

If the same message is re-read after a crash, log event ID, source position, and duplicate outcome explicitly; never count handler invocations and assume that equals created orders.

## 52. Checklist for selecting components when designing flows

Before writing Spring Integration configuration, confirm:

- Does the message originate from an **external system** or an **application Java method**?
- Is the direction inbound or outbound **relative to the integration application**?
- Is a **business reply** required back to the caller?
- Must the result return immediately, or is a durable `ACCEPTED/PENDING` sufficient?
- Are we bridging transport, invoking a business method, or transforming payloads?
- Is the input a skippable event or a side-effecting command needing confirmation?
- What is the max wait budget, and who owns timeouts?
- Can retries duplicate side effects?
- Which business command/event IDs, correlations, and reply-to fields are required?
- At which milestone after durable processing should source ACK/offset commit happen?
- Do errors happen before message creation, in handlers, or on async workers?
- Do adapters/gateways enforce header mapping, TLS, auth, and allowlists?
- Is there a DLT/quarantine and replay owner for permanent failures?
- Are there tests against real transports or fake servers with fault injection?

**Summary rule:** **One-way transport** → Channel Adapter; **request–reply transport needed** → Gateway; **message must invoke an application method** → Service Activator; **Java code wants to call a flow via a typed interface** → `@MessagingGateway`.

## 53. Runbook: system used the wrong Adapter/Gateway/Service Activator

A team reports "the HTTP client got 202 but never got the order placement result":

1. **Identify the caller:** external HTTP client, Java application, Kafka producer, or cron job?
2. **Identify the expected contract:** only a transport ACK, immediate business result, or deferred status?
3. **Inspect endpoints:** was an inbound/outbound Adapter used instead of a Gateway? Does the Service Activator return a reply?
4. **Inspect channel topology:** did a Filter discard, a Router pick another branch, or a Transformer throw?
5. **Inspect reply paths:** is `replyChannel`/return address still valid, or did a hardcoded `outputChannel` misroute the reply?
6. **Inspect sync/async boundaries:** did the caller time out before the worker committed?
7. **Inspect error paths:** did exceptions propagate to the caller or enter `ErrorMessage`/container recoverers?
8. **Inspect business state:** did the DB/order/outbox/remote side effect commit?
9. **Inspect transport state:** what do Kafka offsets, broker ACKs, or HTTP status codes mean under the contract?
10. **Inspect retries:** was `commandId` preserved, and did remote idempotency work?
11. **Inspect correlation:** did Gateway replies match requests; is an Aggregator missing a child member?
12. **Remediate:** pick the right endpoint or switch the API to async status, and add durable recovery.
13. **Regression test:** test timeout-after-commit, missing replies, duplicate deliveries, and wrong header mappings.

**Do not simply swap a Channel Adapter for a Gateway without adapting the whole flow.** Adding replies requires designing response DTOs, routing, timeouts, error handling, correlation, and client contracts.

## 54. Common misconceptions

**"Adapter, Gateway, and Service Activator all use `.handle()`, so they are the same."** False. Java DSL syntax looks similar, yet endpoint semantics differ.

**"Channel Adapters are always asynchronous."** False. One-way is a reply contract, not a threading model.

**"Outbound HTTP Adapters never see HTTP status codes."** False; the transport client can observe status codes/exceptions, yet the Adapter emits no business reply message by pattern.

**"A Gateway guarantees the server committed."** False. Replies and HTTP ACKs must be interpreted per remote contract.

**"A Gateway timeout means the business operation failed."** False; the outcome may simply be unknown.

**"An Inbound Gateway is just a renamed Inbound Adapter."** False. Gateways carry a request–reply contract.

**"Service Activators manage Kafka partitions and consumer groups."** False. Containers/adapters own that.

**"Adding `@ServiceActivator` guarantees a method is idempotent."** False. You need transactions, inboxes, and constraints.

**"If a Service Activator returns a DTO, HTTP does not need a Gateway."** False; the external HTTP request/reply boundary still needs a gateway or controller.

**"A Gateway needs no Service Activator because it already holds business logic."** Gateways are boundaries; business services/handlers still run downstream.

**"A `@MessagingGateway` Java interface is an HTTP inbound gateway."** False. It is a Java proxy invoking a message flow.

**"Gateway ReplyChannel and Aggregator correlation ID are identical."** False. Return addresses and logical group IDs have distinct semantics.

**"Filter discards automatically generate an error reply for a Gateway."** False. They risk timeouts.

**"Global errorChannel receives every exception."** False. It depends on sync/async boundaries and whether failures happen before or after message creation.

**"Publisher ACK means the consumer finished processing."** False. Broker ACKs and business completion are separate.

**"Adding executor threads preserves ordering."** False; per-key completion order can diverge.

**"Kafka offsets serve as durable system-wide idempotency IDs."** False. Offsets only mark positions within a topic/partition.

**"Retrying HTTP POST with a fresh key after timeout is safer."** On the contrary, it can double remote side effects.

**"`@Transactional` on the caller automatically flows across ExecutorChannel."** False; transaction contexts bind to threads.

**"A void Service Activator inside a request–reply Gateway automatically returns OK."** False. Callers may receive no reply at all.

## 55. Hands-on exercise: swap endpoints as reply requirements change

Build a mini project **ChannelBoundaryLab** with Spring Integration:

1. Create DTOs `FindOrderQuery`, `OrderView`, `ReserveStockCommand`, `ReservationResult`, and `AuditEvent`.
2. Use `@InboundChannelAdapter` + poller to ingest JSON order files from a test directory.
3. Add a Filter/Transformer converting files into canonical commands and rejecting malformed inputs with a reasonCode.
4. Use a Service Activator to invoke a fake `OrderService.place()` with idempotency.
5. Use an HTTP outbound channel adapter to send `AuditEvent` to a fake server.
6. Have the fake server return `{"state":"PENDING"}` and prove the adapter **does not emit a business reply** for the application to consume.
7. Switch to an HTTP outbound gateway when the flow must read the response body and emit a typed result.
8. Build an HTTP inbound gateway accepting `FindOrderQuery` and returning `OrderView`.
9. Create a Java `@MessagingGateway` for `CheckoutUseCase` so callers avoid constructing Spring Messages directly.
10. Test a `void` Service Activator on a request–reply path and observe the reply timeout.
11. Fix it with typed rejection/acceptance results and a proper error mapper.
12. Insert an `ExecutorChannel`, throw inside a worker, and verify a dedicated error channel.
13. Simulate a remote HTTP timeout after server commit and retry with the same logical command ID.
14. Add a durable inbox/outbox or test fake store to guard against duplicate deliveries.
15. Add a three-child Splitter and an Aggregator with distinct member IDs and parent correlation.
16. Reject one child and emit an explicit failed outcome instead of dropping silently.
17. Verify broker ACKs/offsets do not equate to business completion.
18. Add metrics for Adapter received, Gateway reply timeouts, Activator commits, and DLT pending counts.
19. Write a runbook for when an external caller receives no reply even though the DB committed.
20. Swap file inbound for a Kafka inbound adapter while keeping business handler contracts unchanged.

**Pass criteria:** every boundary uses the right direction and reply semantics; business handlers remain transport-independent; errors, retries, and correlation are explicit; crashes and retries cause no duplicate side effects; tests demonstrate that one-way HTTP Adapters differ from request–reply Gateways while Service Activators invoke methods.

## 56. Key takeaways

**Channel Adapter, Gateway, and Service Activator are not three ways to write the same endpoint.** They collaborate across **three boundaries**:

1. **Channel Adapter:** one-way communication between an **external source/sink** and a message channel, in **inbound** or **outbound** direction.
2. **Gateway:** handles **request–reply**, managing return addresses, correlation, and timeouts via inbound/outbound transport gateways or `@MessagingGateway` Java proxies for application code.
3. **Service Activator:** dispatches messages to **an application method** for processing and optional replies, without acting as an external transport adapter or gateway.

A typical flow combines all three: **Kafka inbound Adapter → Filter/Router/Transformer → Service Activator → HTTP outbound Gateway → Outbound Adapter emitting completion events**. Never pick an endpoint type simply because they can all be wired with `.handle()`.

**The most important distinction is the contract:** who sends the request, who receives the reply, when a business operation counts as succeeded, and who handles timeouts or crashes? Choosing the right endpoint is only step one; safe operation still demands **authorization, idempotency, transactions, error channels, retries/DLTs, correlation, and integration tests**.

### References

- Enterprise Integration Patterns, **Channel Adapter**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/ChannelAdapter.html
- Enterprise Integration Patterns, **Messaging Gateway**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html
- Enterprise Integration Patterns, **Service Activator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingAdapter.html
- Spring Integration Reference, **Channel Adapter**: https://docs.spring.io/spring-integration/reference/channel-adapter.html
- Spring Integration Reference, **Messaging Gateways**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **Service Activator**: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Integration Reference, **HTTP Support**: https://docs.spring.io/spring-integration/reference/http.html
- Spring Integration Reference, **File Support**: https://docs.spring.io/spring-integration/reference/file.html
- Spring Integration Reference, **Kafka Support**: https://docs.spring.io/spring-integration/reference/kafka.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html

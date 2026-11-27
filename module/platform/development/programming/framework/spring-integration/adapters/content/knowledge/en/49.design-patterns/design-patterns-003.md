# Gateway Request–Reply Pattern in Spring Integration Adapters

> **Chapter:** Design patterns  
> **Topic:** Gateway request-reply pattern  
> **Module context:** SPRING_INTEGRATION_ADAPTERS — connecting external systems via inbound/outbound adapters, gateways, pollers, and MessageChannels; message flows over files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; designing message contracts, error handling, and connection lifecycles.

## 1. The Problem: An Application Sends a Request and Needs a Result

In integration systems, not every message is a one-way emitted event. A pricing service may need to ask a pricing engine: “What is the final price of product A for customer B?” An HTTP endpoint may receive an order-status query and need to return a response to the client. A Java application also wants to **call a normal method**, while multiple message-based steps execute behind the scenes.

The **Gateway Request–Reply Pattern** bridges that gap: the sender puts a **request message** into a flow and receives a corresponding **reply message**, or an error/timeout outcome per contract. The gateway hides most message/channel details from calling code, though it does not by itself guarantee the success of external systems.

Conceptual example:

~~~text
REST Controller / Java Service
      calls pricingGateway.quote(request)
              |
              v
      Message<PriceRequest>
              |
              v
         requestChannel
              |
         Pricing handler
              |
              v
      Message<PriceReply>
              |
              v
      pricingGateway.quote(...) returns result
~~~

### 1.1. Learning objectives

After this lesson, you can:

1. Present the **Request–Reply** model and the gateway's role in Enterprise Integration Patterns (EIP).
2. Distinguish between **Messaging Gateway**, **Inbound Gateway**, **Outbound Gateway**, and **Channel Adapter** in Spring Integration.
3. Understand **requestChannel, replyChannel, reply-to, correlation ID, timeout, and Message headers**.
4. Write a **@MessagingGateway** interface and a request-handling service activator in Java.
5. Build HTTP or message-broker integration flows with request/reply without assuming every broker supports replies like HTTP.
6. Design reply mapping, validation, business errors, transport errors, and late replies.
7. Choose between **DirectChannel, ExecutorChannel, and QueueChannel** based on dispatch model, latency, errors, and transactions.
8. Prevent duplicate requests, timeout-retry issues, commit errors, and confusing a successful response with end-to-end side effects.
9. Build test scenarios, track metrics, and write a runbook sufficient for operating a gateway.

### 1.2. What a valid design must prove

A design meets expectations when you can answer:

- **Who sends the request?** Has the identity or workload been authenticated and authorized for the operation?
- **Where is it sent?** Which channel/endpoint does the request enter, and what is the payload/header contract?
- **Who processes it?** Which handler, service, HTTP server, or broker consumer is responsible?
- **Where does the reply go?** How do you avoid sending request A's result to caller B?
- **How long do we wait?** How are timeouts and final result acceptance criteria defined?
- **What happens on failure?** How do business errors differ from connection errors or lost replies?
- **What if the client retries?** Will it trigger the same side effect twice?

## 2. Request–Reply in Enterprise Integration Patterns

In a one-way (*fire-and-forget*) model, a producer emits a message and does not wait for a direct business result. In **Request–Reply**, a producer sends a request and expects a result correlated to that request.

### 2.1. Two halves of an exchange

| Component | Responsibility | Example |
| --- | --- | --- |
| **Requester** | Initiates the request and awaits/receives the reply | PricingService calling quote |
| **Gateway** | Translates a method call or protocol into a request/reply message | Spring Messaging Gateway |
| **Request channel** | Delivers the request to the handler/adapter | pricingRequests |
| **Request handler** | Executes business logic or calls an external system | PriceQuoteHandler |
| **Reply** | Valid result or domain rejection info | QuoteAccepted / QuoteRejected |
| **Reply channel / reply destination** | Return path back to the requester | Message replyChannel or JMSReplyTo |
| **Correlation** | Links a reply back to the original request | Correlation ID or reply routing mechanism |
| **Deadline / timeout** | Upper bound on how long the caller waits | 3 seconds in lab |

**Key point:** requests and replies may travel on two different channels or two different queues/topics; therefore, you must correlate pairs accurately rather than relying on arrival order.

### 2.2. API-level synchronicity is not network-level synchronicity

~~~mermaid
sequenceDiagram
    participant CALL as Java caller
    participant GW as Messaging Gateway
    participant REQ as RequestChannel
    participant H as Handler
    participant REP as ReplyChannel
    CALL->>GW: quote(PriceRequest)
    GW->>REQ: Message<PriceRequest>
    REQ->>H: handle(request)
    H-->>REP: Message<PriceReply>
    REP-->>GW: Reply for the right request
    GW-->>CALL: PriceReply
~~~

The caller may see a simple synchronous call, while the backing flow may traverse executors, TCP, HTTP, or brokers and return. Choose an architecture based on **latency, error handling, and business rules**, not just because a method has a return type.

### 2.3. Request–Reply variants

| Variant | How it completes | When to use |
| --- | --- | --- |
| **In-process synchronous** | Handler replies immediately on the same call stack | Fast lookups, validation, or in-JVM business functions |
| **Remote synchronous** | Sends HTTP/JMS request and waits for remote response | Querying external services with tight SLAs |
| **Asynchronous Request–Reply** | Request and reply traverse separate channels/brokers | Decoupled systems, variable processing times |
| **Request accepted + callback/status** | Responds immediately with a job ID; result arrives later | Long batches, exports, prolonged processing |
| **Scatter–Gather** | One request sent to multiple recipients and replies aggregated | Gathering quotes or data from multiple sources |

Do not use a synchronous gateway to wait on work that could take hours. In such cases it is better to **return a job ID**, persist durable state, and let clients poll or receive a callback/event upon completion.

## 3. How Gateways Differ from Adapters, Handlers, and Pollers

Spring Integration has many endpoints working with MessageChannels, yet the **contract between caller and callee** differs significantly.

| Component | Communication direction | Does caller await a reply? | Example |
| --- | --- | --- | --- |
| **Inbound channel adapter** | External → channel | Usually no request-reply in the flow | File inbound adapter, message-driven listener |
| **Outbound channel adapter** | Channel → external | No reply message by default | Sending files, publishing notifications |
| **Inbound gateway** | External request → flow → external response | Yes, per protocol/contract | HTTP inbound gateway, JMS inbound gateway |
| **Outbound gateway** | Flow → external request → reply back into flow | Yes | HTTP outbound gateway, JMS outbound gateway |
| **Messaging Gateway** | Method invocation → message → reply → return value | Yes if method declares a return type | Java @MessagingGateway interface |
| **Service activator** | MessageChannel → business handler | Returns result if handler/method has a return value | validateQuote, calculatePrice |
| **Poller** | Scheduled receive from MessageSource/PollableChannel | Not a gateway | File/SFTP polling, QueueChannel consumer |

### 3.1. Inbound gateway and outbound gateway

An **inbound gateway** is where **external callers invoke** our integration flow. With HTTP, it receives requests and can send an HTTP response once the flow returns a reply.

An **outbound gateway** is where our integration flow **calls outward**, such as an HTTP GET to an exchange-rate service, and brings the HTTP response back into the flow as a reply message.

~~~mermaid
flowchart LR
    EXT["External HTTP client"] --> IG["HTTP Inbound Gateway"]
    IG --> CH["MessageChannel"]
    CH --> H["Service handler"]
    H --> OG["HTTP Outbound Gateway"]
    OG --> REM["Remote price API"]
    REM --> OG
    OG --> H
    H --> IG
    IG --> EXT
~~~

The return arrows in the diagram represent **request/reply logic**, not a promise that the exact same object or thread traverses every component. When a flow involves routers, transformers, or brokers, appropriate reply-routing metadata must be preserved.

### 3.2. A Messaging Gateway is not necessarily an HTTP gateway

A Messaging Gateway is a **Java proxy** for a message flow. It can invoke an in-JVM handler, send over JMS/AMQP, or trigger an HTTP outbound gateway. **HTTP is not required** by definition.

### 3.3. Polling Consumer and Gateway can coexist

A flow can use an **SFTP inbound poller** to pick up files, call an **outbound HTTP gateway** to validate data, and forward results to a DB adapter. The poller decides when to fetch files; the gateway manages request/reply when calling the API. Never conflate these two responsibilities.

## 4. Messages and Headers That Govern the Reply Path

Spring Integration uses Spring **Messages** consisting of a **payload** and **headers**. For request/reply, besides metadata like message ID and timestamp, headers such as **replyChannel** and **errorChannel** are especially important in internal routing.

### 4.1. Basic contract

~~~text
Request Message:
  payload      = PriceRequest(sku, quantity, customerTier)
  headers:
    messageId        = technical message ID
    replyChannel     = internal reply channel/address
    errorChannel     = error-handling channel if appropriately configured
    correlationId    = key linking back to the request (when needed)
    traceId          = tracing key (if added by the integration system)

Reply Message:
  payload      = PriceReply(sku, currency, total)
  headers:
    correlationId    = matching correlation key per contract
    traceId          = used to correlate logs/traces
~~~

This is a **conceptual** example. Not every gateway automatically populates all of these headers, nor is there any guarantee that the same correlation field carries identical semantics across HTTP, JMS, and Kafka. Distinguish **internal Spring Messaging headers** from **transport protocol headers**.

### 4.2. replyChannel and Reply-To

- For internal gateways, the framework can set up a **temporary reply channel** so results return to the exact waiting call.
- A reply-producing handler can return a payload or Message; the framework uses reply routing info to return the result.
- For JMS, **JMSReplyTo** or a configured reply destination can be used; results must be matched by correlation.
- For AMQP and Kafka, reply-to/correlation mechanics differ from JMS; configure according to the specific adapters, containers, and topics/queues.
- For an HTTP inbound gateway, the final reply maps to an **HTTP response** bound to the request/connection, not a broker-persisted message by default.

**Do not arbitrarily strip replyChannel or correlation metadata** when constructing a new Message mid-flow; losing routing info can cause the gateway to time out even though the handler produced a valid result.

### 4.3. Correlation ID and Business ID are different

| ID | What it is used for | Example |
| --- | --- | --- |
| **messageId** | Identifies a technical Spring Message | A new UUID per created message |
| **requestId** | Identifies a business request | PRICE-REQ-0198 |
| **correlationId** | Links a reply to the right request | CORR-7C2A |
| **traceId** | Connects spans/logs across systems | TRACE-9021 |
| **idempotencyKey** | Prevents duplicate business effects on retry | customer + order + operation |

They may share values if intentionally designed that way by contract, yet there is **no universal rule that they are always identical**. On retry, messageId may change while requestId/idempotencyKey stay unchanged.

### 4.4. A flow handling hundreds of concurrent requests

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant GW as Gateway
    participant H as Remote Service
    A->>GW: Request A (corr=A1)
    B->>GW: Request B (corr=B1)
    GW->>H: A1
    GW->>H: B1
    H-->>GW: Reply B1 (arrives first)
    GW-->>B: Result B1
    H-->>GW: Reply A1
    GW-->>A: Result A1
~~~

If replies were routed by **arrival order** instead of proper correlation, callers could receive someone else's data. That is both a business correctness bug and a cross-tenant/customer data leak risk.

## 5. Request–Reply States and What a Reply Does NOT Prove

A gateway must distinguish multiple stages:

| Milestone | What is known? | What is still uncertain? |
| --- | --- | --- |
| **SUBMITTED** | Caller constructed a valid request locally | Not certain the channel/broker accepted it |
| **SENT/ACCEPTED** | Endpoint accepted the request per contract | Whether downstream handlers have committed |
| **PROCESSING** | Consumer is processing | Whether a reply will arrive on time |
| **REPLIED** | Gateway received and mapped the reply | Whether external systems have unfinished extra side effects |
| **TIMED_OUT** | Caller exceeded wait time | Request may still be running or may have already committed |
| **FAILED** | A failing step was detected | Rollback/recovery capability depends on the systems |
| **COMMITTED** | A business unit durably persisted results per contract | Whether out-of-transaction steps completed |

**Critical hazard:** caller timeout **does not mean** the target system did not process the request. Retrying without idempotency can create two orders, charge twice, or grant permissions twice.

### 5.1. How to choose a reply contract

- **Pure queries:** return data or errors; usually safe to retry if side-effect-free.
- **Commands with side effects:** attach requestId/idempotencyKey and clarify accepted/committed states.
- **Long-running tasks:** return 202/jobId or status messages instead of blocking gateways indefinitely.
- **Business rejections:** return a structured business outcome (e.g., QUOTE_NOT_AVAILABLE); do not conflate with TCP errors.
- **Transport timeouts:** report an **unknown actual outcome** state with a query/reconciliation path if the command has side effects.

### 5.2. When to return an error instead of a normal reply?

A nonexistent price can be a **valid business outcome** (PriceUnavailable). Malformed JSON, disconnected services, or security violations are different failures. The API/message contract must define which failures are domain replies and which go through exceptions/error channels.

Never return empty strings or null for every failure: callers must distinguish **no price available**, **wait timed out**, and **invalid server state**.

## 6. Java 17: Building a Working In-JVM Messaging Gateway

The example uses **Spring Integration 6.x**, the Spring context, and Java 17. We define a **Java interface** as a gateway, a DirectChannel to carry requests, and a service activator calculating prices. This is an **internal** request/reply model: no HTTP or broker yet, isolating the core concepts before adding I/O.

### 6.1. Request and reply DTOs

Create two records representing the business contract:

~~~java
// QuoteRequest.java
public record QuoteRequest(
        String requestId,
        String sku,
        int quantity,
        String customerTier
) {}
~~~

~~~java
// QuoteReply.java
import java.math.BigDecimal;

public record QuoteReply(
        String requestId,
        String sku,
        String currency,
        BigDecimal unitPrice,
        BigDecimal total
) {}
~~~

The request includes **requestId** for business tracking; in this example it is not yet an idempotency key for a side-effecting operation. Pure price lookups can be retried, whereas replacing the handler with “create order” would require durable idempotency.

### 6.2. Declaring the gateway interface

~~~java
// QuoteGateway.java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "pricingRequests",
        defaultRequestTimeout = "1000",
        defaultReplyTimeout = "3000"
)
public interface QuoteGateway {
    QuoteReply quote(QuoteRequest request);
}
~~~

**Meaning:**

- **@MessagingGateway** instructs Spring Integration to create a **proxy** converting method calls into Messages.
- **defaultRequestChannel** routes requests to the channel named pricingRequests.
- **defaultRequestTimeout** bounds the wait when **sending** requests to the channel in scenarios supporting blocking sends.
- **defaultReplyTimeout** bounds the wait for a reply on synchronous calls.
- The **QuoteReply** return type is mapped by the gateway from the received reply.

Do not confuse request timeout with **HTTP connect timeout** or reply timeout with **the maximum time a remote transaction can live**. For external network calls, connectors have their own timeouts.

### 6.3. Creating the channel and enabling gateway scanning

~~~java
// GatewayConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class GatewayConfiguration {

    @Bean
    public MessageChannel pricingRequests() {
        return new DirectChannel();
    }
}
~~~

**@IntegrationComponentScan** discovers gateway interfaces within configured scan packages. With Spring Boot, ensure your package layout or scan settings cover both gateways and handlers. Never manually instantiate the interface.

### 6.4. Service activator answering requests

~~~java
// PricingHandler.java
import java.math.BigDecimal;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class PricingHandler {

    @ServiceActivator(inputChannel = "pricingRequests")
    public QuoteReply calculate(QuoteRequest request) {
        if (request == null
                || request.requestId() == null
                || request.requestId().isBlank()
                || request.sku() == null
                || request.sku().isBlank()
                || request.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid quote request");
        }

        BigDecimal unitPrice = new BigDecimal("125000");
        BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity())
        );
        return new QuoteReply(
                request.requestId(),
                request.sku(),
                "VND",
                unitPrice,
                total
        );
    }
}
~~~

When the method returns **QuoteReply**, the service activator turns the return value into a reply via Spring Integration's request/reply mechanism. In this standard request/reply flow, the gateway receives the reply without the handler **having to explicitly send to a named queue**.

**Explicit limitation:** unitPrice is hardcoded for ease of learning, with no catalog, customer-tier policy, authorization, deadlines, or real DB queries. Do not deploy a production pricing service directly from this example.

### 6.5. The caller sees a plain Java interface

~~~java
// A Spring @Service or @Component
import org.springframework.stereotype.Service;

@Service
public class QuoteApplicationService {
    private final QuoteGateway quoteGateway;

    public QuoteApplicationService(QuoteGateway quoteGateway) {
        this.quoteGateway = quoteGateway;
    }

    public QuoteReply getQuote() {
        return quoteGateway.quote(new QuoteRequest(
                "PRICE-LAB-001",
                "SKU-LAB-A",
                2,
                "STANDARD"
        ));
    }
}
~~~

Illustrative result:

~~~json
{
  "requestId": "PRICE-LAB-001",
  "sku": "SKU-LAB-A",
  "currency": "VND",
  "unitPrice": 125000,
  "total": 250000
}
~~~

**Execution path:** quote call → gateway proxy builds Message → DirectChannel delivers to PricingHandler → handler returns QuoteReply → reply routes back to gateway → Java method returns data.

### 6.6. Reading the code across three boundaries

1. **Java invocation boundary:** QuoteGateway looks like an ordinary method interface.
2. **Message boundary:** channels and headers route messages; the handler does not need to know who called it.
3. **Business boundary:** PricingHandler decides pricing rules and input validity.

If you add an outbound HTTP gateway after a transformation step, a fourth boundary appears: **external connectivity** and timeout/lost-reply risks.

## 7. Request–Reply Across Synchronous and Asynchronous Channels

### 7.1. DirectChannel: simple with a synchronous call stack

In the section 6 example, DirectChannel typically dispatches the handler on the sender's thread. If the handler computes in 50 ms, the caller receives the reply after processing time plus minimal overhead. If the handler blocks for 30 seconds on a hung API, the caller is also blocked.

**Note:** reply timeout is not a hard interrupt respected by all synchronous operations. If the sender is blocked inside a synchronous call stack on DirectChannel, total wait time still depends on the handler itself and the timeouts it uses. Configure timeouts at every I/O layer rather than relying solely on defaultReplyTimeout.

### 7.2. ExecutorChannel: decoupled threads, added error responsibility

When switching the request channel to an ExecutorChannel, `send` can return once the executor accepts the task, while the handler executes on another thread. The gateway can still wait for a reply, but now:

- Tasks can be **rejected** if the executor queue is full.
- Transaction context on the sending thread does not automatically propagate to the handler.
- A reply arriving past the deadline may no longer have a waiting caller.
- Handler errors must be routed via error flows and the gateway per contract; exceptions will not magically unwind onto the original thread.
- Caller retries may arrive while the first request is **still executing**.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant GW as Gateway
    participant EX as ExecutorChannel
    participant H as Handler
    C->>GW: quote(Q1)
    GW->>EX: send(Q1)
    EX-->>GW: accepted by executor
    EX->>H: handle(Q1) on another thread
    Note over GW: Caller waits for reply up to deadline
    H-->>GW: reply or error routing
    GW-->>C: result / timeout per contract
~~~

**Mistake:** seeing ExecutorChannel accept a message and logging “request processed successfully.” That only says a dispatch step happened—not that the handler committed and returned a reply.

### 7.3. QueueChannel: must have a consumer pulling messages

QueueChannel is a **PollableChannel**. Sending requests into a QueueChannel requires a **PollingConsumer** or a component explicitly calling `receive()` downstream. Without a consumer, the gateway waits for a reply until timeout; merely sending to a QueueChannel never invokes handlers on its own.

Additionally, an in-memory QueueChannel is **not durable across crashes by default**. If critical requests must survive JVM shutdown, choose a broker/MessageStore or appropriate durable solution.

### 7.4. PublishSubscribeChannel and multiple results

A typical gateway expects **one reply** per request. Broadcasting a request to multiple handlers can produce multiple replies or ambiguity over which reply is valid. To collect all results, use **Scatter–Gather/Aggregator** with explicit correlation and completion strategies; never wire three replies into a temporary reply channel hoping the framework guesses how to merge them.

## 8. Request–Reply via HTTP Inbound and Outbound Gateways

### 8.1. HTTP inbound gateway: clients calling us

Suppose the system accepts HTTP POST requests to calculate quotes:

~~~http
POST /api/prices/quote HTTP/1.1
Content-Type: application/json

{
  "requestId": "PRICE-LAB-001",
  "sku": "SKU-LAB-A",
  "quantity": 2,
  "customerTier": "STANDARD"
}
~~~

An **HTTP inbound gateway** receives the request, creates a Spring Message, sends it into the flow, awaits a reply if required by the contract, and maps it to an HTTP response. Configure appropriate mappings and converters for JSON DTOs, plus authentication/authorization, validation, payload limits, and timeouts.

~~~mermaid
flowchart LR
    CLIENT["HTTP Client"] --> HTTP["HTTP Inbound Gateway"]
    HTTP --> CHANNEL["pricingRequests"]
    CHANNEL --> HANDLER["PricingHandler"]
    HANDLER --> CHANNEL
    CHANNEL --> HTTP
    HTTP --> CLIENT
~~~

The return arrow travels along the **reply route**, not necessarily backwards through the same requestChannel. The diagram is simplified to show the request/reply contract.

A **reference** Java DSL configuration style:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.http.dsl.Http;

@Configuration
public class HttpQuoteGatewayConfiguration {

    @Bean
    public IntegrationFlow inboundQuoteFlow() {
        return IntegrationFlow.from(
                    Http.inboundGateway("/api/prices/quote")
                        .requestMapping(m -> m.methods(HttpMethod.POST))
                        .requestPayloadType(QuoteRequest.class)
                )
                .channel("pricingRequests")
                .get();
    }
}
~~~

This example shows **configuration style** in Spring Integration 6.x, not a complete project. In real projects, you need the Spring Integration HTTP dependency, proper Jackson/message converters, JSON handling, HTTP response statuses, security, exception mapping, and verification of exact overloads for your library version.

### 8.2. HTTP outbound gateway: the flow calls another API

A flow can receive a message from a broker, call an external pricing service via an **HTTP outbound gateway**, and continue processing the HTTP response as a reply:

~~~text
OrderCreated message
  → transformer builds PriceRequest
  → HTTP outbound gateway calls pricing service
  ← HTTP response / PriceReply
  → validate reply
  → handler updates order with result
~~~

Before sending, define HTTP method GET/POST, URL, path/query variables, auth headers, content type, expected response type, connect/read timeouts, and 4xx/5xx handling. **HTTP 200** does not automatically guarantee the returned data matches the schema or that the price is finalized under the business contract.

### 8.3. HTTP status codes and domain results

| Status | Typical meaning | Gateway handling direction |
| --- | --- | --- |
| **200/201** | Request returned a successful result per HTTP contract | Parse/validate reply, verify business status |
| **202** | Request accepted for later processing | Return jobId/status URI; do not report immediate completion |
| **400/422** | Invalid request or business constraint failure | Return coded error; do not blindly retry |
| **401/403** | Unauthenticated or unauthorized | Never bypass; log safely |
| **404** | Resource not found at endpoint | May be a domain result or mapping bug; requires contract |
| **409** | State/version conflict | Query state or resolve concurrency; no infinite retries |
| **429** | Rate limit | Respect Retry-After if present and back off |
| **500/502/503/504** | Server or gateway failure | Bounded retry, especially cautious with side effects |

HTTP status codes are merely **transport signals**. Never treat a network exception as proof that the request did not commit.

### 8.4. When NOT to hold an HTTP request open

If exporting a report takes 20 minutes, waiting synchronously in an HTTP inbound gateway is a weak design: clients/proxies may time out, restarts lose state, and users cannot tell if work is still running. A better pattern:

~~~text
POST /exports → validate + persist job → 202 Accepted + jobId
Worker processes asynchronously via broker
GET /exports/{jobId} → progress and results
Event/callback when job completes (if supported)
~~~

Request/reply still exists at the **job creation** step, without forcing long-running execution inside one gateway call.

## 9. Request–Reply Gateways over JMS, AMQP, and Kafka

Message brokers decouple requesters and responders into separate services, yet **not every broker provides built-in request/reply like HTTP calls**. You typically must define reply destinations, correlation, late-reply handling, timeouts, and ownership of pending requests.

### 9.1. JMS: request destination, reply destination, and correlation

A JMS request/reply flow typically involves:

1. Requester sends a message to the **request queue**.
2. The message carries **reply destination** info (e.g., JMSReplyTo) and correlation metadata.
3. Responder receives, processes, and sends a reply to that destination.
4. Requester receives the reply and matches it to the pending request using ID/correlation.
5. On deadline expiration, requester cleans up pending state per policy; late responses must be handled.

~~~mermaid
sequenceDiagram
    participant A as Requester
    participant GW as JMS Outbound Gateway
    participant Q as JMS Request Queue
    participant RESP as Responder
    participant RQ as JMS Reply Destination
    A->>GW: Request Quote Q17
    GW->>Q: JMS request + reply destination
    Q->>RESP: Deliver request
    RESP->>RQ: Reply + correlation
    RQ-->>GW: Match Q17
    GW-->>A: QuoteReply
~~~

**JMSReplyTo** carries routing info; **JMSCorrelationID** and JMSMessageID play related roles that are not always identical. One solution sets correlation from a request ID, while another links via generated message IDs. Design according to your specific gateway/client/broker rather than forcing one rigid formula across all products.

**JMS checklist:**

- [ ] Is the reply queue temporary, shared, or a named destination? Who creates/deletes it?
- [ ] With multiple concurrent requester instances, is reply routing/matching accurate?
- [ ] Are timeouts set for sending, awaiting replies, and broker disconnections?
- [ ] Does the responder use proper transactions/acks? If it reprocesses, will it emit duplicate replies?
- [ ] If the requester crashes, where do replies go? How are TTL/quotas and cleanup handled?
- [ ] If a reply arrives past the deadline, is it discarded, stored for reconciliation, or able to affect another request?

### 9.2. AMQP/RabbitMQ: request queues and reply-to

RabbitMQ supports multiple ways to structure request/reply, such as reply queues or client/library-supported **direct reply-to**. An AMQP outbound gateway needs queue/exchange routing and a mechanism for the broker/client to correlate replies to requests.

~~~text
Integration Flow
    -> AMQP outbound gateway
    -> exchange/routing key
    -> request queue
    -> responder
    -> reply-to destination / direct reply-to
    -> AMQP gateway receives and matches reply
    -> Integration Flow continues
~~~

**Milestones to separate:** message accepted by broker, message acknowledged by responder, responder committed business logic, responder emitted reply, and requester received reply are **distinct events**.

With temporary reply queues, a requester restart can leave old replies with no waiting receiver. With shared reply queues, correlation and consumer coordination are mandatory. A request processed by the responder whose reply was lost is a critical scenario for idempotent retries.

### 9.3. Kafka: a reply topic does not automatically turn a stream into RPC

Kafka is optimized for partitioned event logs and consumer groups. **Request/reply can still be designed** using a request topic, reply topic, correlation ID, and a client/coordinator managing pending requests. The Spring Kafka ecosystem provides request/reply capabilities in appropriate APIs; when integrating with Spring Integration, verify exact adapters/gateways and version support.

~~~mermaid
flowchart LR
    REQ["Request Producer/Gateway"] --> QT["quotes.requests topic"]
    QT --> WORK["Quote responder"]
    WORK --> RT["quotes.replies topic"]
    RT --> MATCH["Reply listener + correlation registry"]
    MATCH --> REQ
~~~

**Additional problems to solve compared to a method call:**

- Which **partition/topic** should replies go to so the right requester receives them?
- How do multiple requesters configure **consumer groups** so another service doesn't steal replies?
- Does the correlation registry live in memory or persistent storage? How do timeouts purge pending entries?
- If the requester restarts, how are old replies retained/re-read?
- If the responder rebalances/retries, how are two replies for the same request handled?
- How do the responder's offset commits and transactions relate to business commits/reply records?

Do not force Kafka RPC onto every simple interaction just because Kafka is present. For fast lookups needing immediate responses, HTTP/gRPC may be far simpler. For multi-minute workflows, use asynchronous events and state machines instead of holding thousands of futures/promises awaiting replies.

### 9.4. Comparing transports for request/reply

| Aspect | HTTP | JMS | AMQP/RabbitMQ | Kafka |
| --- | --- | --- | --- | --- |
| Reply route | HTTP response bound to request/connection | Reply destination + correlation | Reply queue/direct reply-to + correlation | Reply topic + correlation/partition strategy |
| Who manages pending | HTTP client/server/proxy per connection | Gateway/client | Gateway/client | Reply coordinator/client |
| Timeouts | Connect/read/request/proxy | Send + receive reply + broker | Broker/client/reply timeout | Produce/fetch/reply deadline |
| When requester dies | HTTP connection drops | Reply may or may not remain depending on destination | Depends on reply queue/expiry | Reply record may still exist in topic |
| Duplicates | Client retries | Duplicate redelivery/replies | Duplicate redelivery/replies | At-least-once/replay/rebalance |
| Ordering | Per request/connection, not global | Per destination/consumer | Per queue/consumer | Within partition per contract |
| Best fit | Short queries, web APIs | Enterprise messaging with request/reply | Governed RabbitMQ workflows and RPC | Stream integration with explicitly designed replies |

**No option automatically provides exactly-once across HTTP, brokers, and databases**. Reliability comes from processing contracts, idempotency, transactions, timeouts, and reconciliation.

## 10. Gateways and File, SFTP, and Database Adapters

Files/SFTP/DBs typically act as **data sources** or **side-effect targets**, rather than real-time request/reply pairs like HTTP. A gateway can be invoked **mid-flow** to query additional data or issue commands.

### 10.1. File inbound → outbound HTTP gateway

For example, each CSV file must be validated against a customer service before DB ingestion:

~~~mermaid
flowchart LR
    FILE["File/SFTP inbound poller"] --> PARSE["Parse + Validate"]
    PARSE --> REQ["Build CustomerLookupRequest"]
    REQ --> GW["HTTP Outbound Gateway"]
    GW --> API["Customer Service"]
    API --> GW
    GW --> DECIDE["Check reply"]
    DECIDE --> DB["Commit valid data"]
    DECIDE --> ERR["Quarantine / Retry"]
~~~

Here, the **poller** detects new files; the gateway handles request/reply with Customer Service. If HTTP times out after Customer Service performed an update, distinguish safe-to-retry queries from side-effecting commands.

### 10.2. SFTP commands/replies are not arbitrary RPC

An adapter sending/receiving files can acknowledge a protocol operation, yet that does not mean the partner **has processed the file contents**. Uploading a file over SFTP successfully only proves the server received the file per the transfer contract; if business confirmation is needed, use a dedicated **ack file, status API, broker event, or reconciliation workflow**.

Do not build a request/reply gateway simply by “waiting for the file to disappear” without an explicit contract: the file might be moved by another job or deleted on error.

### 10.3. Databases as request/reply targets

A **JDBC outbound gateway** or a service handler calling a repository can fetch data and return a reply. However, when mutating the DB:

- Pure queries can use appropriate read timeouts and retries.
- Write commands require transactions, constraints, and idempotency.
- Reading a reply after writing must account for isolation levels and the source of truth.
- Never assume a JDBC transaction wraps SFTP transfers or separate HTTP requests.
- If events must be emitted post-commit, consider a transactional outbox.

### 10.4. Gateways and message stores

In a flow traversing **QueueChannel/MessageStore**, a gateway can wait for results from a downstream consumer. However, if waiting across crashes/restarts is required, pending requests, correlation state, and reply destinations must be managed **durably**. Persisting requests while leaving temporary reply channels in RAM does not guarantee callers receive replies after a restart.

## 11. Timeouts: Three Clocks and a Late Reply

Timeouts are one of the most severe failure sources in request/reply when target systems slow down or fail.

### 11.1. Distinguishing timeout types

| Timeout | What does it measure? | Failure example |
| --- | --- | --- |
| **Request send timeout** | Waiting to send a message into a channel/destination when blocking | Queue/MessageChannel full |
| **Gateway reply timeout** | Waiting for a reply to return to the gateway | Handler or responder too slow |
| **Connect timeout** | Waiting to establish an HTTP/TCP/broker connection | Service unreachable |
| **Read/response timeout** | Waiting to read data from a remote connection | Server received request but failed to respond in time |
| **Business deadline** | Business cutoff beyond which results lose value | Quote expired |
| **Broker message TTL** | Duration a message is kept/accepted by the broker | Request/reply expired in queue/topic |

Not all timeouts start from the same instant or share the same annotation. A gateway timeout does not replace an HTTP socket timeout, transaction timeout, or remote application deadline.

### 11.2. Timeline: timeout followed by retry

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant GW as Gateway
    participant H as Responder
    participant DB as Database
    C->>GW: CreateOrder(requestId=R1)
    GW->>H: Message R1
    H->>DB: Commit order R1
    DB-->>H: OK
    Note over GW,C: Reply timeout, caller unaware of state
    GW-->>C: TIMEOUT / UNKNOWN
    C->>GW: Retry R1 with same idempotency key
    GW->>H: Message R1
    H->>DB: Check requestId R1 already completed
    DB-->>H: Return prior result, do not create second order
    H-->>GW: Reply R1
    GW-->>C: Result of R1
~~~

**If R1 already committed, a retry must return the same result or a queryable status**. Retrying with a new requestId without deduplication easily causes a second side effect.

### 11.3. What should happen to late replies?

Replies arriving after the deadline usually have no waiting caller left. Depending on the architecture:

1. **Drop cleanly** and emit a late-replies metric if the request is a stateless query.
2. **Persist results by requestId** and let callers query again for long/critical commands.
3. **Purge pending correlations** by TTL to prevent unbounded memory growth.
4. **Never misroute** a late reply from request A to request B sharing a connection/queue.
5. **Never re-trigger side effects** merely because a reply arrived late.

### 11.4. Timeouts and retry storms

If 1,000 callers time out simultaneously and retry infinitely, an already degraded service collapses further. Use **retry budgets, exponential backoff, jitter, rate limiting, bulkheads, and circuit breakers** tailored to risk. For writes, require idempotency and state queries before uncertain retries.

### 11.5. Deadline propagation

In a chain API A → gateway B → HTTP gateway C, if caller A only has 500 ms left for the request, B should not wait another 30 seconds on C without reason. Propagate **business deadlines** or remaining budgets across trusted internal layers. Never accept client-supplied deadlines to bypass validation or escalate privileges.

## 12. Error Channels and Error Responses

### 12.1. Three outcome types to separate

| Outcome | Example | Representation |
| --- | --- | --- |
| **Business success** | Quote calculated | Valid QuoteReply |
| **Business rejection** | SKU unavailable, customer ineligible | Domain reply with code/reason; distinct from transport failure |
| **Technical failure** | DB timeout, broker disconnect, malformed JSON | Exception/ErrorMessage/error flow mapped to caller |

**A business error is not necessarily an exception:** “Product out of stock” can be a completely valid reply. Conversely, parsing a response that violates the schema must be treated as a technical failure.

### 12.2. Synchronous vs. asynchronous errors

**Synchronous DirectChannel:** exceptions from handlers can propagate back to the gateway on the same call stack and be wrapped/translated by Spring Messaging. Java callers invoking the gateway must handle appropriate exceptions.

**ExecutorChannel or brokers:** responder exceptions do not naturally unwind onto the requester's call stack; they may travel via an error channel, DLT, or a correlated error reply. Designs must ensure callers distinguish **timeout / technical failure / business rejection**.

### 12.3. ErrorMessage and errorChannel

Spring Integration uses **ErrorMessage** and error channels for many flow errors. However, where ErrorMessages are emitted, whether errors reach the gateway, and fallback behaviors depend on endpoint types, sync/async boundaries, and configured error handlers.

- [ ] Identify whether errors occur **before sending request**, **during send**, **during processing**, **sending reply**, or **after reply**.
- [ ] For synchronous errors, never swallow exceptions and fake a successful reply.
- [ ] For async errors, provide an error flow or correlated error reply.
- [ ] For remote adapter errors, preserve source requestId, target, attempt, and exception type.
- [ ] Never leak stack traces, secrets, raw tokens, or sensitive PII in external replies.
- [ ] If the caller already timed out, handle late errors per runbook rather than trying to send to an abandoned reply channel.
- [ ] When configuring errorChannel, test which callback actually receives errors in your library version.

### 12.4. Example structured error reply

~~~json
{
  "requestId": "PRICE-LAB-001",
  "status": "REJECTED",
  "code": "SKU_UNAVAILABLE",
  "message": "Product is unavailable at the time of request",
  "retryable": false
}
~~~

This is an illustrative **domain reply**. Over HTTP, it can map to an appropriate 4xx per contract; over JMS/AMQP, it can be a reply message carrying status/code. Not every business rejection needs to be thrown as a Java exception on the producer side.

## 13. Idempotency and Transactions When Gateways Create Side Effects

A gateway does not make an operation **end-to-end exactly-once** simply because one method call pairs a request and reply. When flows create orders, process payments, send notifications, or mutate state, you must handle **duplicate requests and lost replies**.

### 13.1. Five points that can cause duplicates

1. Caller fails to receive a reply and resends the request.
2. HTTP reverse proxy or client retries on network errors.
3. JMS/AMQP responder gets redelivered requests due to missing acks/uncommitted transactions.
4. Kafka records are re-read after rebalances or uncommitted offsets.
5. Gateway/adapter has automatic retry advice when the target side effect actually succeeded.

### 13.2. Idempotency keys must be durable business keys

Order creation example:

~~~json
{
  "requestId": "CREATE-ORDER-LAB-0098",
  "idempotencyKey": "TENANT-LAB-01/CHECKOUT-0098",
  "tenantId": "TENANT-LAB-01",
  "customerId": "CUST-LAB-03",
  "items": [
    {"sku": "SKU-A", "quantity": 2}
  ]
}
~~~

On retry, the caller **keeps the same idempotencyKey**. Responder:

~~~text
processCreateOrder(request):
  validateRequesterAndScope(request)
  validateBusinessPayload(request)
  checkKeyNotReusedForDifferentPayload(request.idempotencyKey)

  with databaseTransaction:
      existing = findOrderByIdempotencyKeyForUpdate(key)
      if existing:
          return persistedResult(existing)

      order = createOrder(request)
      persistIdempotencyRecord(key, hashOfSignificantRequestFields, order.id)
      commit

  return persistedResult(order)
~~~

This is **pseudocode**. A plain SELECT followed by INSERT is insufficient against races between concurrent requests; you need unique constraints, proper transaction/locking, and conflict resolution. Never store a “success” idempotency record before business changes commit per contract.

### 13.3. What if the responder calls another API?

Suppose the CreateOrder handler both writes to the DB and calls a Payment API. A standard JDBC transaction **cannot roll back an HTTP payment call**. You also need:

- A payment API supporting its own idempotency key or transaction lookup by business reference.
- Outbox or saga/process managers for asynchronous steps.
- Compensation where business rules allow; never assume all side effects can roll back.
- Returning **PENDING/UNKNOWN** on timeout before external effects are verified.
- Tracking attempts, operation IDs, and actual per-step outcomes.

### 13.4. Query gateways vs. command gateways

| Characteristic | Query gateway | Command gateway |
| --- | --- | --- |
| Side effects | No state changes expected | May mutate state |
| Retry after timeout | Usually simpler if purely read-only | Requires verification/idempotency |
| Business key needed | Helpful for tracing/caching | Essential whenever duplicates are possible |
| Reply | Data snapshot | Accepted/Committed/Rejected/Unknown |
| Integrity | Freshness, schema, authorization | Transactions, concurrency, permissions, reconciliation |

### 13.5. Events emitted after a gateway returns a reply

A service may accept CreateOrder, commit to the DB, return a reply to the HTTP caller, and then emit OrderCreated. If event publishing fails, the caller sees the order created while downstream consumers never get the event. Use a **transactional outbox** to save the order and outbox event in the same DB transaction, then have a relay publish with retries. Event consumers still need idempotency because the relay may republish.

## 14. Correlation, Routing, Aggregation, and Reply Ownership

### 14.1. One request traversing multiple handlers

A flow with a router selecting service providers:

~~~mermaid
flowchart TD
    GW["Quote Gateway"] --> ROUTER{"Route by currency / region"}
    ROUTER -->|VN| VN["VN Price Service"]
    ROUTER -->|EU| EU["EU Price Service"]
    ROUTER -->|Other| FALL["Unsupported region reply"]
    VN --> REPLY["Reply route"]
    EU --> REPLY
    FALL --> REPLY
    REPLY --> GW
~~~

Routers must have explicit fallback or error routes; if messages are silently dropped, the gateway typically only sees a **reply timeout**. A reply-expecting flow should never use a filter that silently drops invalid requests without producing an error reply/exception per contract.

### 14.2. Aggregator and Scatter–Gather

Suppose a request needs **quotes from three providers** to pick the best option:

~~~mermaid
flowchart LR
    REQ["GetBestQuote(request)"] --> SCATTER["Scatter to 3 providers"]
    SCATTER --> P1["Provider A"]
    SCATTER --> P2["Provider B"]
    SCATTER --> P3["Provider C"]
    P1 --> AGG["Aggregator"]
    P2 --> AGG
    P3 --> AGG
    AGG --> REP["One CombinedQuote reply"]
~~~

The aggregator requires a **correlation key** so replies from different requests never mix, plus a **completion condition**: wait for all three, wait up to a deadline, or return once two valid quotes arrive? When one provider fails to respond, define whether partial results are acceptable.

### 14.3. Aggregation design table

| Decision | Question |
| --- | --- |
| Correlation | Which key groups replies belonging to the same request? |
| Sequence | Is expected count known upfront or via dynamic recipients? |
| Completion | N replies, deadline expiration, quorum, or early return? |
| Missing results | Return partial, retry, fallback, or fail overall? |
| Duplicate replies | Can the same provider respond twice? |
| Late replies | Discard, audit-log, or update already-returned results? |
| State store | Does the aggregator need persistence across restarts? |
| Resource bounds | Are there TTLs and pending-group caps to avoid memory leaks? |

**Do not** use a static global list to hold replies across concurrent requests; it mixes data and violates tenant boundaries. Correlation and state must remain isolated by authenticated request/tenant.

### 14.4. Header propagation

When transformers or handlers construct new Messages:

- Preserve **requestId/correlationId/traceId** as needed.
- Let Spring Integration manage internal reply/error headers where possible, avoiding uncontrolled routing loops.
- Do not forward all HTTP client headers across brokers or internal systems unfiltered; they can carry spoofed claims, credentials, or inappropriate content.
- Map headers across JMS/AMQP/Kafka/HTTP using **tested mappings**.
- Ensure each reply maps back to the right requester/tenant without cross-contamination across concurrent requests.

## 15. Backpressure, Thread Pools, and Bounding In-Flight Requests

Request/reply typically **holds pending state while awaiting replies**. Unbounded concurrent requests can exhaust threads, connections, heap, or correlation slots.

### 15.1. Simple capacity math

Suppose a system receives **100 requests/second** and each takes an average of **2 seconds** to finish; in steady state, concurrent in-flight requests are approximately:

~~~text
concurrent in-flight requests ≈ arrivalRate × averageResponseTime
                             ≈ 100 × 2
                             ≈ 200
~~~

This is only an **average steady-state intuition** from Little's Law, not a substitute for load testing. P95/P99 response times, traffic bursts, retries, and timeouts can drive in-flight counts much higher.

### 15.2. Where bottlenecks happen

| Component | Symptom | Measures to consider |
| --- | --- | --- |
| HTTP ingress | Many waiting threads/connections, 5xx/timeouts | Rate limits, deadlines, async accepted jobs |
| DirectChannel handler | Callers blocked by I/O latency | Bound remote call timeouts, optimize handlers |
| ExecutorChannel | Full queue, rejected tasks | Bounded queues, bulkheads, durable handoff if needed |
| JMS/AMQP reply queue | Reply backlog, correlation mismatches | Consumer health, cleanup, reply TTLs |
| Kafka reply topic | Reply lag, unassigned partitions | Reply consumer group/partition configuration |
| Connection pools | HTTP/DB/broker connection exhaustion | Bounded pools, timeouts, load-based tuning |
| Aggregator | Uncleaned pending groups growing | Group timeouts, expiry, release/cleanup |

### 15.3. Bulkheads and circuit breakers

If an external pricing service slows down, do not let **all order-processing threads** stall waiting on prices:

1. Set realistic SLA-aligned timeouts.
2. Limit concurrent pricing calls using bulkheads/rate limiters.
3. Use circuit breakers on repeated failures with controlled recovery probing.
4. Bound retries with jitter; avoid cascading retry storms across layers.
5. For queries, use caches/fallbacks **if business rules permit**; never fabricate fake prices or stale invalid data just to inflate success rates.

### 15.4. Reply latency affects caller value

A late reply may still be an accurate result from the target system yet **no longer useful** to the caller. For time-limited quotes, replies should carry validity or quote expiry metadata; never cache an expired price just because the previous call returned a success status.

## 16. Communication Security and Reply Data Protection

A gateway is a **trust boundary**: it can forward data and caller identities to other systems. Misrouting or skipped checks can let a request from tenant A receive a reply containing tenant B's data.

### 16.1. Security checklist

- [ ] Callers are authenticated via approved mechanisms (IdP/SSO, service principals, mTLS, etc.).
- [ ] Authorization checks **caller, action, and resource**, not just login success.
- [ ] Payloads and headers are validated; never trust unverified client-asserted userId/tenantId.
- [ ] Replies are routed via exact correlation without leaking to other callers.
- [ ] Outbound gateways enforce TLS, server verification, and policy-compliant credential management.
- [ ] Gateway service credentials follow **least privilege**; avoid shared admin accounts unnecessarily.
- [ ] Never log access tokens, refresh tokens, passwords, private keys, or unnecessary PII.
- [ ] Bound request/reply sizes, in-flight counts, timeouts, and call rates against overload.
- [ ] Parse JSON/XML/schemas using safe libraries and secure parser configurations.
- [ ] Never expose raw internal exceptions/stack traces in public HTTP responses.
- [ ] Enforce retry/idempotency policies so malicious callers cannot easily trigger repeated side effects.
- [ ] Audit requestId, caller, target, and decision/outcome while minimizing sensitive metadata.

### 16.2. Protecting correlation metadata

Correlation IDs route replies accurately, yet **are not proof of authorization**. Knowing someone else's requestId does not grant access to their results. If an API exposes `GET /jobs/{requestId}`, enforce **requester ownership/tenant checks** server-side.

### 16.3. Gateways creating confused-deputy vulnerabilities

A gateway holding privileged credentials to call a Finance API can be exploited if it blindly accepts an arbitrary accountId from a client and executes transactions without checking permissions. Therefore:

~~~text
Authenticated caller
   → policy verifies permission on specific account/resource
   → retain only valid request fields
   → gateway calls Finance API with scoped credentials
   → validate reply and scope
   → return authorized data
~~~

Never rely on **“the gateway is an internal service”** to skip business authorization checks.

## 17. Gateway Lifecycle, Connections, Failover, and Graceful Shutdown

Request/reply gateways need operational strategies for **application startup**, **unavailable external brokers or APIs**, **rolling deployments**, and **shutdown with in-flight requests**.

### 17.1. Startup

- [ ] Channels, handlers, gateway proxies, and related adapters are properly registered in the Spring ApplicationContext.
- [ ] Define startup ordering when gateways depend on broker connections, MessageStores, or schema registries.
- [ ] Verify remote endpoints/destinations, credentials, publish/consume permissions, and health.
- [ ] Do not just check that app HTTP returns 200; verify the actual reply path works.
- [ ] For broker reply queues/topics, confirm reply listeners are subscribed/active before sending requests expecting replies.
- [ ] Initialize idempotency stores, correlation registries, and in-flight request caps.
- [ ] Have fast-fail or controlled fallbacks when downstream dependencies are not ready.

### 17.2. Shutdown and rolling deployments

- [ ] Stop accepting new requests or report not-ready status per lifecycle hooks.
- [ ] Allow in-flight requests to complete up to a bounded deadline instead of waiting forever.
- [ ] With brokers, define whether pending replies are preserved, discarded, or handled by another instance.
- [ ] Clean up pending correlations and safely removable temporary reply destinations.
- [ ] Do not ack/commit request messages prior to business commit if required by contract.
- [ ] Ensure retries or resumes are idempotency-protected when callers resend after deploys.
- [ ] Prevent leaking data from request A into request B when registries reinitialize.

**In-JVM synchronous** gateways lose pending wait state if the process dies. A reply arriving after a restart cannot find an old method call that no longer exists. If recovery **across restarts** is required, move to durable job/request state with status polling/callbacks or a specialized persistent coordinator.

### 17.3. Remote connections

| External system | Resources/lifecycle to manage | Symptoms |
| --- | --- | --- |
| HTTP API | Connection pools, TLS, DNS, timeouts, credential rotation | Socket timeouts, 429/503, pool exhaustion |
| JMS | ConnectionFactory, sessions, listeners, reply destinations | Broker restarts, lost temporary replies, redeliveries |
| RabbitMQ | TCP/channels, exchanges/queues, direct-reply-to listeners | Reply queue disconnected, unknown correlation |
| Kafka | Producers, reply consumers, assignments, offsets, topics | Rebalances, lag, growing pending replies |
| JDBC | Connection pools, transactions, query timeouts | Deadlocks, lock waits, pool starvation |
| SFTP/File bridge | Remote sessions, directories, metadata processing | Incomplete files, transport timeouts |

**Do not treat automatic reconnect as sufficient.** Verify whether requests sent right before disconnection were processed by the target and how callers verify outcomes after timeouts.

### 17.4. Multiple requester instances

If three gateway instances share one request queue and one reply queue, ensure **each reply reaches the exact instance owning the pending request**, or use a designed distributed state layer. You cannot blindly put competing consumers on a shared reply queue and hope replies magically land on the originating JVM.

For HTTP request/reply, connections typically bind callers to the receiving instance. If an instance dies, clients may retry on another instance; **idempotency stores must be shared/durable** if side effects must be deduplicated across instances.

### 17.5. Reconfiguration and version compatibility

When evolving PriceRequest/PriceReply schemas, old responders and new requesters may run simultaneously during rolling deploys. Ensure:

- Version contracts or backward compatibility mechanisms.
- Verification of optional new fields vs. required fields.
- Never changing a field's meaning while keeping schemaVersion unchanged.
- Deploying consumers supporting new versions before producers mandate them where appropriate.
- Canary/rollback tests covering bidirectional flows, not just the request leg.

## 18. Observability and Runbooks for Request–Reply

Every gateway must measure both **request send/receive rates** and **on-time reply rates**. A service may process plenty of requests while clients still time out due to broken reply routing.

### 18.1. Key metrics

| Metric | Purpose | Signals to investigate |
| --- | --- | --- |
| **request sent / accepted** | Flow ingress/egress throughput | Unexpected drops or sudden spikes |
| **reply received** | Replies received by gateway | Unexpected gap vs. requests sent |
| **reply success / business reject** | Business outcome breakdown | Unusual spike in rejections |
| **gateway reply timeout** | Callers missing replies before deadline | Slow broker/handlers or lost correlation |
| **late / unmatched reply** | Replies arriving past timeout or unmatched | Pending cleanup, reply queue topology |
| **request/reply latency P50/P95/P99** | Caller experience and responsiveness | Rising tail latency even when median is flat |
| **in-flight requests** | Active pending exchanges | Near cap or failing to drain |
| **executor queue/rejection** | Async backpressure | Full queue, rejected messages |
| **HTTP connect/read failures** | Network and remote issues | Concurrent spikes across requests |
| **retry / duplicate detected** | Repeat load and duplicate-effect risk | Retry storms or idempotency conflicts |
| **broker reply queue depth / lag** | Accumulated replies | Reply listener stalled |
| **correlation registry size** | Memory used tracking pending replies | Monotonic growth from missing cleanup |
| **last successful end-to-end reply** | Contract-level progress | Stale while sent counts keep rising |

Slice all metrics by **endpoint, target, operation, and environment**; never attach unbounded-cardinality requestId/eventId values as metric labels. Keep requestId details in access-controlled tracing/logs.

### 18.2. Safe audit sample

~~~json
{
  "requestId": "PRICE-LAB-001",
  "correlationId": "CORR-LAB-019",
  "operation": "price.quote",
  "requesterType": "service",
  "target": "pricing-api-lab",
  "schemaVersion": 1,
  "requestSentAt": "2026-11-23T10:00:00+07:00",
  "replyReceivedAt": "2026-11-23T10:00:00.170+07:00",
  "outcome": "SUCCESS",
  "latencyMs": 170,
  "retryAttempt": 0,
  "traceId": "TRACE-LAB-020"
}
~~~

This is an **illustrative** log, not Spring Integration's default format. Never log raw API tokens, passwords, private keys, unnecessary customer PII, or entire sensitive responses.

### 18.3. Runbook A — Mass gateway timeouts

1. Inspect requests sent, replies received, timeout rates, and per-endpoint latencies.
2. Check remote APIs/brokers, reply listeners, destinations, partition assignments, and connection pools.
3. Look for cases where **targets committed requests yet replies failed to return**.
4. Determine whether it is a correlation/header mapping bug or simply a slow handler.
5. Apply valid containment: rate limits, circuit breakers, lowered concurrency, or switching to durable queues if appropriate.
6. Never enable infinite retries. For side-effecting commands, query status by requestId before retrying.
7. Document root cause, scope of UNKNOWN requests, and the reconciliation plan.

### 18.4. Runbook B — Replies reaching the wrong caller

This is a severe data and authorization incident. Halt the affected response path per procedure, inspect routing/correlation/tenant boundaries, preserve logs, assess leak scope, fix mappings, and add concurrency tests where two requests return out-of-order replies. Never mask the bug by sorting callbacks by arrival time.

### 18.5. Runbook C — Caller retries creating duplicate side effects

Check requestId/idempotencyKey across both attempts, ACK/reply timelines, transactions, and responder unique constraints. Remediate duplicated records through authorized business workflows; enforce idempotency at the **commit point** rather than relying solely on in-memory gateway dedupe.

### 18.6. Runbook D — One responder sending two replies

If a responder receives redelivered requests or retries post-commit logic, it may emit two replies with the same correlation. The gateway must handle the second result per contract without misrouting an extra reply into another request. Track duplicate/late replies; fix responder idempotency and registry cleanup.

## 19. Comprehensive Lab: Quote Gateway and Remote Price Service

The lab builds a **caller-friendly Java gateway**, wires it to a local handler, and then simulates remote APIs/brokers with timeouts, errors, and out-of-order replies. Use exclusively **mock data, test endpoints, or authorized mocks**.

### 19.1. Two-stage architecture

**Stage A — In-process:** QuoteApplicationService → QuoteGateway → DirectChannel → PricingHandler → QuoteReply. Verifies Java–Message–Reply mapping only.

**Stage B — Remote:** HTTP inbound gateway receives client requests; the flow calls an HTTP outbound gateway to a mock Price API and returns replies. Optionally swap the remote leg for JMS/AMQP request/reply queues.

~~~mermaid
flowchart TD
    CLIENT["HTTP Client"] --> IG["HTTP Inbound Gateway"]
    JAVA["Java Application Service"] --> MG["@MessagingGateway"]
    IG --> REQ["Quote request channel"]
    MG --> REQ
    REQ --> VALIDATE["Validate + authorize"]
    VALIDATE --> ROUTE{"Local or remote?"}
    ROUTE -->|Local| LOCAL["PricingHandler"]
    ROUTE -->|Remote| OUT["HTTP/JMS Outbound Gateway"]
    OUT --> REMOTE["Mock Price Service"]
    REMOTE --> OUT
    LOCAL --> REP["Reply mapping"]
    OUT --> REP
    REP --> IG
    REP --> MG
~~~

The reply paths in the diagram are logical; at runtime the gateway and framework route using **each** request's reply channel/correlation. During the lab, run **two concurrent calls** with distinct requestIds to prove results never cross-contaminate.

### 19.2. Input fixtures

| Request | SKU | Quantity | Sample outcome |
| --- | --- | --- | --- |
| **PRICE-LAB-001** | SKU-LAB-A | 2 | 250,000 VND |
| **PRICE-LAB-002** | SKU-LAB-A | 1 | 125,000 VND |
| **PRICE-LAB-003** | SKU-NOT-FOUND | 1 | Domain reply SKU_UNAVAILABLE |
| **PRICE-LAB-004** | SKU-LAB-A | 0 | Validation error |
| **PRICE-LAB-005** | SKU-LAB-A | 5 | Simulated remote timeout |

These are fixtures only; real pricing systems have distinct currencies, discounts, customer tiers, pricing versions, and validity windows. Validate thoroughly when replacing mocks.

### 19.3. Implementation steps

**Step 1 — Build the core flow.** Create QuoteRequest, QuoteReply, QuoteGateway, GatewayConfiguration, and PricingHandler per section 6. Start the Spring context and invoke `quote` from a service.

**Step 2 — Verify mapping.** For valid requests, QuoteReply must preserve requestId, SKU, currency, and price per fixtures. For quantity=0, route to a valid error path instead of returning 0 as a successful quote.

**Step 3 — Test DirectChannel.** Add a handler logging start/end to observe caller and handler on the same call stack without async boundaries. No poller is needed.

**Step 4 — Test ExecutorChannel.** Switch requestChannel to a bounded-queue executor. Observe replies returning after handler completion, check timeouts, and observe cross-thread error handling.

**Step 5 — Build a remote mock.** Replace the local handler with an HTTP outbound gateway or a mock responder replying via a message channel. Add realistic connect/read timeouts in the mock.

**Step 6 — Reverse reply order.** Send Q1 and Q2 nearly concurrently; delay Q1 by 300 ms and reply to Q2 after 50 ms. Both callers must receive their exact matching requestId and price.

**Step 7 — Simulate lost replies.** Responder finishes execution but drops the reply. Caller times out; logs must clearly record UNKNOWN/TIMED_OUT. For side-effecting commands, never retry blindly.

**Step 8 — Idempotency.** Add a CreateOrder command with an idempotencyKey and a test durable result store. Send the same request twice; order creation occurs once with consistent replies.

**Step 9 — Test errors and security.** Have a tenant A user swap tenantId to tenant B; the backend must reject it. Have the remote mock return 429/503, malformed schemas, and late replies; classify errors and retry appropriately.

**Step 10 — Operations.** Measure sent/replied/timedOut, late replies, in-flight counts, and latency; write runbooks for dead reply queues, HTTP timeouts, and correlation mismatches.

### 19.4. JUnit tests for Stage A

Example in a Spring Boot project with Spring Integration, Spring Boot Test, and JUnit Jupiter enabled:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class QuoteGatewayTest {

    @Autowired
    private QuoteGateway quoteGateway;

    @Test
    void shouldReturnCorrelatedQuote() {
        QuoteReply result = quoteGateway.quote(
                new QuoteRequest("REQ-001", "SKU-LAB-A", 2, "STANDARD")
        );

        assertEquals("REQ-001", result.requestId());
        assertEquals("SKU-LAB-A", result.sku());
        assertEquals("VND", result.currency());
        assertEquals(new BigDecimal("250000"), result.total());
    }

    @Test
    void shouldRejectInvalidQuantity() {
        assertThrows(RuntimeException.class, () ->
                quoteGateway.quote(
                        new QuoteRequest("REQ-002", "SKU-LAB-A", 0, "STANDARD")
                )
        );
    }
}
~~~

The test snippet above is an **example for learners to run**, not a report of tests executed in this repository. Tests should additionally assert **error types and business codes** rather than just RuntimeException, as gateways may wrap exceptions. When writing timeout integration tests, use eventual assertions with deadlines and controlled test doubles instead of arbitrary long `Thread.sleep` calls.

### 19.5. An experiment to understand replyChannel

If you send a message directly to a channel **without using a gateway proxy**, a returning handler needs to know where to send the reply. You can design a dedicated return path or attach a valid reply channel to the message:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

// Illustrative snippet inside a Spring component/test with pricingRequests injected.
QueueChannel privateReply = new QueueChannel(1);

Message<QuoteRequest> message = MessageBuilder.withPayload(
        new QuoteRequest("REQ-MANUAL", "SKU-LAB-A", 2, "STANDARD")
    )
    .setReplyChannel(privateReply)
    .build();

boolean sent = pricingRequests.send(message);
if (!sent) {
    throw new IllegalStateException("Cannot send request");
}

Message<?> reply = privateReply.receive(3000);
if (reply == null) {
    throw new IllegalStateException("Reply timeout");
}

QuoteReply result = (QuoteReply) reply.getPayload();
~~~

This snippet is **illustrative inside a method/test**, assuming `pricingRequests` is already injected as a MessageChannel and the handler returns replies via the framework mechanism. It shows that a gateway effectively **manages sending requests and receiving replies for you**, rather than inventing an entirely different message kind.

Never pass an in-memory reply channel across JVM/broker boundaries by serializing the channel object directly. Over a network, you need a **reply destination** and protocol-appropriate correlation headers.

### 19.6. Extensions

1. Add `@Gateway` on an individual method to override requestChannel or replyTimeout on the gateway interface per policy and your annotation version.
2. Create two handlers with a router and a response code for unavailable SKUs.
3. Use Scatter–Gather to fetch quotes from three mock providers, returning partial results if two respond validly before the deadline.
4. Add an in-flight request gauge; test 100 concurrent requests to detect correlation mixing.
5. Add JMS/AMQP request/reply on a test broker, observing temporary reply queues and requester restarts.
6. Simulate a Kafka reply topic with a correlation registry, late replies, and rebalances; compare complexity with HTTP.
7. Add an outbox for CreateOrder and an inbox for the responder to prevent duplicates across restarts.
8. Verify tenant isolation when two concurrent callers share an SKU with different pricing/policies.

## 20. Request–Reply Gateway Test Matrix

These cases describe **expected conditions**, not automatically executed results. For each case, record Input, Expected, Actual, PASS/FAIL/UNKNOWN, and Evidence.

| ID | Scenario | PASS condition |
| --- | --- | --- |
| **GW-01** | QuoteGateway calls DirectChannel and handler returns reply | Caller receives accurate QuoteReply |
| **GW-02** | Handler returns payload of unexpected type | Mapping error detected; wrong data not returned |
| **GW-03** | Request missing SKU or quantity=0 | Validation rejects; no false success |
| **GW-04** | Reply preserves caller's requestId | No cross-mixing between requests |
| **GW-05** | Two concurrent requests receive reversed-order replies | Each caller gets its exact matching reply |
| **GW-06** | Router receives unsupported region | Explicit domain rejection or error; does not hang indefinitely |
| **GW-07** | Synchronous handler throws exception | Gateway receives proper error instead of success |
| **GW-08** | ExecutorChannel dispatches work to another thread | `send` accepted is not treated as business committed |
| **GW-09** | Executor queue full | Rejection/backpressure recorded |
| **GW-10** | QueueChannel holds requests without a consumer | Gateway timeout/alert, no fabricated reply |
| **GW-11** | HTTP inbound gateway receives valid JSON schema | Returns payload and HTTP status per contract |
| **GW-12** | HTTP caller sends unauthorized tenantId | Backend rejects; no reply leaked |
| **GW-13** | Outbound HTTP API returns 429 | Backoff/rate limits respected; no retry storm |
| **GW-14** | Outbound HTTP API returns 503 | Classified as transient; bounded retries |
| **GW-15** | Remote committed yet reply lost | Retrying causes no second side effect |
| **GW-16** | Reply arrives after defaultReplyTimeout | Late reply handled, pending state cleaned up |
| **GW-17** | Reply arrives with unknown correlation ID | Never misdelivered to another caller |
| **GW-18** | Responder emits reply twice | Does not send two results or contaminate other requests |
| **GW-19** | Old requestId reused with different payload | Idempotency key reuse detected |
| **GW-20** | JMS responder receives request and replies to valid JMSReplyTo | Correlation matches; no lost replies |
| **GW-21** | JMS broker restarts while requester waits | No false success; clear timeout state |
| **GW-22** | AMQP reply queue/direct reply-to disconnects | Gateway timeout/error without silent loss per policy |
| **GW-23** | Kafka request/reply across two topics | Request/reply matched per correlation strategy |
| **GW-24** | Kafka reply consumer rebalances | Late/duplicate replies handled safely |
| **GW-25** | SFTP file polled then calls HTTP gateway | Source polling separated from downstream request/reply |
| **GW-26** | JDBC query gateway times out | Connect/query timeouts distinguished from business errors |
| **GW-27** | Scatter–Gather misses one provider | Completion strategy handles deadline/partial correctly |
| **GW-28** | Caller loses HTTP connection after creating job | Queryable by jobId without creating duplicates |
| **GW-29** | 100 concurrent requests, out-of-order replies | Correlation and tenant isolation remain intact |
| **GW-30** | Consumer uses over-privileged credentials | Authorization blocks invalid actions |
| **GW-31** | Audit contains raw token/password | Test verifies credentials are stripped/redacted |
| **GW-32** | Rolling deploy with pending replies | No reply leakage; timeout/resume strategy active |

### 20.1. Sample test case report template

~~~yaml
testCase: GW-15
requestId: CREATE-ORDER-LAB-0098
scenario: "Business commit succeeds but the reply is lost"
expected: "Caller sees UNKNOWN; retry with same idempotency key does not duplicate"
actual: "Fill with observed result when the lab runs"
result: PENDING
evidenceRef: "lab://tests/GW-15"
owner: gateway-lab
verifiedAt: null
~~~

Do not change **PENDING** to PASS merely because the implementation claims idempotency on paper. Verify actual target state and logs after simulating lost replies/crashes.

### 20.2. Test failure categories

- **Contract tests:** request/reply mapping, schemas, validation, status codes, correlation.
- **Integration tests:** HTTP/JMS/AMQP/Kafka adapters and remote responders in test environments.
- **Failure injection:** lost replies, remote timeouts, broker restarts, schema mismatches, duplicate requests.
- **Concurrency tests:** multiple callers, reversed-order replies, in-flight caps, executor queues.
- **Security tests:** subject/resource/tenant authorization, credential redaction.
- **Recovery tests:** requester/responder restarts, idempotent retries, pending correlation cleanup.

## 21. Anti-Patterns and Production Checklist

### 21.1. Common design mistakes

| Anti-pattern | Why it is wrong | Better approach |
| --- | --- | --- |
| **Treating Messaging Gateway as an HTTP gateway** | Java gateways do not require HTTP | Separate gateway proxies from HTTP/JMS/AMQP endpoints |
| **Using an outbound channel adapter and awaiting a reply** | One-way adapters do not build a request/reply contract | Use an outbound gateway with reply handling |
| **Stripping replyChannel/correlation during transforms** | Replies cannot route back to the right caller | Preserve required routing metadata |
| **Matching replies by arrival order** | Out-of-order replies leak data | Match strictly by accurate correlation |
| **Using reply timeout to cancel remote transactions** | Timeout does not prove side effects didn't run | Deadlines, valid cancellation, idempotency, reconciliation |
| **Retrying commands post-timeout with a new requestId** | Creates duplicate side effects | Preserve idempotencyKey, query prior outcome |
| **Holding HTTP connections open for hours** | Proxy/client timeouts, state lost on restarts | Async accepted jobs + status/callbacks |
| **Adding QueueChannel without a consumer** | Messages go unprocessed, gateway times out | PollingConsumer or alternative channel design |
| **Pushing requests to ExecutorChannel and reporting success** | Handler hasn't committed; crashes lose work | Durable handoffs or ack at commit points |
| **Using PublishSubscribeChannel expecting one automatic reply** | Multiple replies with no completion strategy | Scatter–Gather/Aggregator with correlation |
| **Measuring only HTTP 200** | Misses pending, late replies, business rejects | Measure send–reply–commit–timeout |
| **Sharing reply queues without isolation** | Wrong instances grab replies, correlation breaks | Appropriate routing/consumer setup |
| **Treating Kafka as free RPC** | Complex reply topics, offsets, groups, and state | Choose protocols aligned with SLA and domain needs |
| **Using gateway's internal role instead of caller authorization** | Confused deputy, cross-tenant bypass | Per-resource authorization and least privilege |
| **Logging full payloads/headers** | Credential and PII leaks | Redaction, data minimization, and RBAC auditing |

### 21.2. Design checklist

- [ ] Gateway role is clearly identified (Java messaging, inbound, or outbound) with a genuine reply need.
- [ ] Request/reply is distinguished from fire-and-forget adapters and polling sources.
- [ ] Request and reply messages define schemas, versions, validation, and error contracts.
- [ ] requestId, correlation strategy, and business idempotencyKey (for side effects) exist.
- [ ] Unverified external permission/tenant headers are never trusted.
- [ ] Request send timeout, reply timeout, and I/O timeouts are configured independently.
- [ ] Caller behavior is defined for business rejections, technical failures, timeouts, and UNKNOWN.
- [ ] Late replies, duplicate replies, and unknown correlations are handled.
- [ ] Threading semantics of DirectChannel/ExecutorChannel/QueueChannel are understood.
- [ ] No fake cross-HTTP/broker/DB atomic transactions are assumed.
- [ ] For side-effecting commands, retries rely on idempotency and actual state.
- [ ] HTTP gateways enforce rate limits, authn/authz, content types, schemas, and response mappings.
- [ ] Broker gateways have verified reply destinations/topics, listeners, acks/offsets, and cleanup.
- [ ] Multi-instance routing cannot deliver requester A's reply to requester B.
- [ ] Long-running requests use job status/callbacks instead of indefinite waits.
- [ ] Bounded concurrency, in-flight limits, circuit breakers/backpressure match load.
- [ ] Logs/metrics/tracing link requests to handlers and replies without leaking secrets.
- [ ] Remote failures, retries, duplicates, slow replies, restarts, and schema mismatches are tested.
- [ ] Runbooks exist for timeouts, reply mismatches, duplicate side effects, and shutdown.

## 22. Summary: Gateways Are the Boundary Between Calls and Messages

The **Gateway Request–Reply Pattern** lets code invoke an interface or endpoint as a result-returning interaction, while Spring Integration orchestrates processing with **MessageChannels, handlers, and adapters**.

Key takeaways:

1. **Messaging Gateway** converts Java calls into request messages and maps replies back to return values.
2. **Inbound Gateway** accepts external requests and returns responses; **Outbound Gateway** calls external systems and brings replies back into the flow.
3. **replyChannel/correlation** ensures each request receives its matching reply, especially with concurrent requests and out-of-order replies.
4. **DirectChannel, ExecutorChannel, and QueueChannel** govern dispatch semantics, latency, failure propagation, and transaction boundaries; a successful send does not always mean a business commit.
5. **HTTP, JMS, AMQP, and Kafka** have distinct reply semantics; no single ack/offset/timeout formula fits all of them.
6. **Timeouts do not mean the target did not process the request**. Commands with side effects require idempotency, state inspection, and recovery.
7. **Files, SFTP, and DBs** can use pollers at ingress and invoke request/reply gateways mid-flow; the two patterns complement rather than exclude each other.
8. **Observability and security** must track requestId, correlation, tenant, deadlines, reply status, and real business outcomes.

### 22.1. End-of-lesson questions

1. Why doesn't a Java `@MessagingGateway` interface necessarily generate an HTTP request?
2. If a handler receives a request yet returns no reply, how does the gateway behave?
3. Why are replyChannel and correlation ID not always the exact same concept?
4. When using ExecutorChannel, does a successful `send()` guarantee remote business logic committed?
5. An HTTP POST request times out after creating an order; what must the client do to prevent duplicate orders?
6. When should you return 202 + jobId instead of holding a gateway open waiting for a reply?
7. Why can sharing a single reply queue across multiple requester instances misroute replies?
8. What must be specified when Scatter–Gather misses one out of three replies?
9. How do you prove responses cannot leak across tenants when replies arrive out of order?
10. Which metrics distinguish a slow remote service from a broken correlation registry?

**Hints:** (1) gateway maps methods to any message flow; (2) timeout or error per contract; (3) one is the return path, the other is the matching key; (4) no; (5) keep idempotencyKey / query status; (6) long-running work; (7) wrong instance's reply consumer grabs it; (8) correlation, deadline, completion/partial policy; (9) run concurrency tests verifying requester/tenant; (10) remote latency, replies received/late/unmatched, and pending registry size.

**Final takeaway:** *A good gateway doesn't merely send requests and receive replies; it proves each reply belongs to the right caller, the right business action, and within deadline—while safely handling every gap between sending requests, committing at targets, and receiving responses.*

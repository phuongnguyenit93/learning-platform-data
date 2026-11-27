# AMQP inbound gateway

## Learning Objectives

After this lesson, you will be able to:

- Explain the **request–reply** contract of an AMQP inbound gateway and distinguish it from a one-way AMQP inbound channel adapter.
- Describe the path **RabbitMQ request queue → listener container → inbound gateway → MessageChannel → service activator → AMQP reply**.
- Understand how **reply-to**, **correlation ID**, request/reply conversion, message headers, and reply timeout work when calling via RabbitTemplate.
- Build a **Spring Integration Java DSL** example serving quote requests over RabbitMQ, complete with exchange, binding, request queue, handler, and test client.
- Analyze processing errors, ACK/NACK, retry/requeue, timeouts, late replies, duplicate messages, and the impact of asynchronous channels.
- Design testing, security, concurrency, observability, and operational procedures for a request–reply gateway.

## 1. Problem: The Consumer Must Reply to the Sender

In an event-driven architecture, a system often emits an **OrderCreated** event without waiting for the consumer to finish processing. In that case, an **AMQP inbound channel adapter** fits: it receives the message from a RabbitMQ queue, pushes it into a MessageChannel, and ends its responsibility in a one-way inbound flow.

However, some operations require an **immediate result for every request**. For example, a sales application sends product and quantity details to a quoting service via RabbitMQ and must receive the total price to complete the next step. A broker confirmation or consumer ACK **does not contain the quote result**. A true **request–reply** flow is required.

An **AMQP inbound gateway** is the endpoint serving that requirement on the **receiving side**. It consumes requests from an AMQP queue, converts the request into a Spring Message, sends it into the flow, waits for or receives a reply per the contract, and publishes the reply back to the address specified by the caller.

~~~mermaid
flowchart LR
    C["Caller<br/>RabbitTemplate"] --> X["RabbitMQ exchange"]
    X --> Q["Request queue<br/>quotes.request.q"]
    Q --> L["Spring AMQP<br/>listener container"]
    L --> G["AMQP inbound gateway"]
    G --> MC["MessageChannel<br/>quoteRequests"]
    MC --> H["Service activator<br/>QuoteService"]
    H -->|"Spring reply message"| G
    G -->|"AMQP reply-to + correlation"| R["Reply destination"]
    R --> C
~~~

In this example, **inbound** is from the quoting service's perspective: the request enters the application from outside. Even though it publishes a reply back to RabbitMQ, the endpoint is still called an **inbound gateway** because it exposes a request–reply service to external callers.

## 2. Distinguishing Inbound Adapter from Inbound Gateway

| Criterion | AMQP inbound channel adapter | AMQP inbound gateway |
| --- | --- | --- |
| Application contract | **One-way**: consumes messages | **Request–reply**: request expects a result |
| Data source | RabbitMQ queue | RabbitMQ request queue |
| Input to Spring Integration | Spring Message via channel | Spring request Message via channel |
| Business response | Does not automatically send a business reply | Takes the reply from the flow and sends an AMQP reply |
| Reply destination | Not required for one-way exchange | Usually requires **reply-to** or a configured reply destination |
| Correlation | Mainly for tracing if needed | Needed to match each response to its request across concurrent calls |
| When service activator returns null | Typically no reply needed | Risks failing to complete the request–reply exchange |
| Example | Receive OrderCreated event | Receive QuoteRequest, return QuoteResponse |

An **AMQP outbound gateway** is the perspective of *an application actively sending a request* and waiting for a reply. An architecture can have an outbound gateway in application A and an inbound gateway in application B; the caller can also use **RabbitTemplate.convertSendAndReceive(...)** directly without building an outbound IntegrationFlow.

Do not choose an inbound gateway just to "get a RabbitMQ ACK." Broker acknowledgment and business replies are two mechanisms with different purposes, timings, and success conditions.

## 3. Request–Reply Protocol: Request Queue, Reply-To, Correlation

A typical AMQP request carries:

- **Body:** request payload, such as JSON or a String supported by the converter.
- **reply-to:** the address where the caller expects the response.
- **correlation ID:** helps the caller match the reply to the corresponding request.
- **Message properties/headers:** content type, encoding, message ID, trace ID, or business metadata.

On the service side:

1. The caller publishes the request to an exchange with a routing key so it reaches the queue.
2. The RabbitMQ listener container receives the delivery from the request queue.
3. The inbound gateway converts the AMQP message into a Spring Message and sends it to the request channel.
4. The handler produces **a reply**; Spring Integration routes the reply back to the gateway.
5. The gateway converts the reply into an AMQP message and sends it to the reply destination.
6. The caller uses correlation to receive the right result, or times out if no reply arrives in time.

~~~mermaid
sequenceDiagram
    participant C as Caller / RabbitTemplate
    participant X as RabbitMQ
    participant G as AMQP inbound gateway
    participant H as QuoteService
    C->>X: Publish request, reply-to, correlation
    X->>G: Request delivery
    G->>H: Spring Message on quoteRequests
    H-->>G: Spring reply message
    G->>X: Publish reply using reply-to
    X-->>C: AMQP reply (matching correlation)
    C->>C: Convert reply into caller result
~~~

**Correlation ID is not an idempotency key.** Correlation pairs a request with a reply for one exchange; a **business requestId** identifies the same request if retried or resent. They may share a value in a specific design, but never assume every library preserves the same correlation ID across retries.

### 3.1. Reply Destination Mechanisms

| Reply Mechanism | Characteristics | Things to Note |
| --- | --- | --- |
| **RabbitMQ direct reply-to** | Optimizes request–reply when supported by client and broker using a reply-to pseudo-queue | Not a durable queue storing reply backlogs for offline callers |
| **Temporary/exclusive reply queue** | Caller can create a dedicated queue for replies | Requires managing queue/consumer and connection lifecycles |
| **Fixed reply queue** | A predefined reply queue | Requires an appropriate consumer, correlation, concurrency, and configuration to avoid mixing replies |

When using RabbitTemplate.convertSendAndReceive with standard defaults, Spring AMQP can use direct reply-to. That does not mean every RabbitMQ deployment and configuration will automatically use the same mechanism. If using a fixed reply queue, explicitly design the queue, listener container, routing, timeout, and correlation.

### 3.2. What If the Request Has No Reply-To?

A request sent via a one-way publish mechanism may **lack a reply address**. In that case, the inbound gateway lacks sufficient information to return a result through the normal reply path unless the endpoint is configured with an appropriate **default reply destination**. Do not promise a response will reach the caller without reply-to/correlation or another contract.

### 3.3. In-Flow MessageHeaders Are Not AMQP Properties

A Spring Message has a payload and headers such as **replyChannel**, **errorChannel**, correlation, or flow-specific metadata. The inbound gateway can use a temporary reply channel or equivalent reply path to receive the result from the flow; a message converter/header mapper then maps appropriate fields into the AMQP reply.

Never serialize a Spring MessageChannel object directly to RabbitMQ. **AMQP reply-to** is external protocol information, whereas **Spring replyChannel** is an *in-flow* reply routing mechanism.

## 4. RabbitMQ Topology and Listener Container

Request–reply over AMQP still relies on core RabbitMQ concepts:

| Component | Role in Inbound Gateway |
| --- | --- |
| **Exchange** | Receives requests published by callers |
| **Routing key/binding** | Routes requests into the right request queue |
| **Request queue** | Holds requests waiting for the gateway to process |
| **ConnectionFactory** | Provides RabbitMQ connections for clients and listeners |
| **Listener container** | Consumes request deliveries; manages ACK/NACK, concurrency, and prefetch |
| **MessageConverter** | Converts AMQP body/properties into payload/headers, and converts the reply back |
| **AMQP inbound gateway** | Connects the request–reply protocol to the messaging flow |
| **MessageChannel** | Passes requests to the service activator or processing endpoint |

With a listener-based AMQP inbound gateway, the source is **message-driven**, not a scheduled File/SFTP poller. The Spring AMQP listener container has its own start/stop lifecycle and receiving mechanism. Do not add a Spring Integration poller just because requests originate from a queue.

A **durable request queue** keeps the queue topology across broker policies; it does not automatically make request/reply exactly-once, does not guarantee replies survive after the caller times out, and does not replace idempotency.

## 5. Designing Request and Reply Contracts

In our learning example, the caller sends the string:

~~~text
requestId|productId|quantity
~~~

Example:

~~~text
req-1001|SKU-42|2
~~~

The gateway forwards the request to QuoteService; the service returns:

~~~text
OK|req-1001|100000
~~~

Here the mock unit price is **50,000 VND/unit**. If the input is invalid, the demo returns a simple structured result:

~~~text
ERROR|INVALID_REQUEST
~~~

This is a minimal format to make the request–reply path easy to see. In production, use JSON/Avro/Protobuf with a schemaVersion, required fields, error codes, and compatibility rules:

~~~json
{
  "requestId": "req-1001",
  "productId": "SKU-42",
  "quantity": 2
}
~~~

A reply can include fields such as:

~~~json
{
  "requestId": "req-1001",
  "status": "OK",
  "totalVnd": 100000,
  "schemaVersion": 1
}
~~~

A **business error** such as INVALID_REQUEST can be a *valid reply* informing the caller that the request was rejected. **Technical errors** such as broker disconnects, database timeouts, or converter failures typically need a different error-handling path. Do not return the same error payload for every kind of failure, or the caller will not know whether it is safe to retry.

## 6. Spring Integration Java DSL Example: AMQP Inbound Gateway

Let's build a quoting service:

- Direct exchange: **quotes.requests**.
- Routing key: **quote.calculate**.
- Durable request queue: **quotes.request.q**.
- Inbound gateway listening on the request queue.
- Internal MessageChannel: **quoteRequests** (DirectChannel).
- Service activator invoking QuoteService and returning a String reply.
- Caller using RabbitTemplate.convertSendAndReceive(...) to receive the result.

### 6.1. Dependencies and Connectivity

With Spring Boot, use dependencies whose versions are managed in sync with the Spring Boot BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

In development, the application needs a running RabbitMQ broker and a ConnectionFactory with appropriate host, port, virtual host, and credentials. Use a secret manager/environment variables and TLS where transport protection is needed; **never hardcode real credentials** in source code.

### 6.2. Creating Exchange, Queue, Binding, and Gateway Flow

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class QuoteAmqpGatewayConfiguration {

    public static final String EXCHANGE = "quotes.requests";
    public static final String ROUTING_KEY = "quote.calculate";
    public static final String REQUEST_QUEUE = "quotes.request.q";

    @Bean
    public DirectExchange quotesExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue quotesRequestQueue() {
        return new Queue(REQUEST_QUEUE, true);
    }

    @Bean
    public Binding quotesBinding(
            Queue quotesRequestQueue,
            DirectExchange quotesExchange) {
        return BindingBuilder.bind(quotesRequestQueue)
            .to(quotesExchange)
            .with(ROUTING_KEY);
    }

    @Bean
    public MessageChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow quoteInboundGatewayFlow(
            ConnectionFactory connectionFactory,
            QuoteService quoteService) {
        return IntegrationFlow
            .from(Amqp.inboundGateway(
                connectionFactory, REQUEST_QUEUE))
            .channel("quoteRequests")
            .handle(String.class, (request, headers) ->
                quoteService.calculate(request))
            .get();
    }
}
~~~

**Explanation:**

1. **quotesExchange**, **quotesRequestQueue**, and **quotesBinding** describe the topology so callers can publish to the exchange with a fixed routing key.
2. **Amqp.inboundGateway(connectionFactory, REQUEST_QUEUE)** registers the request-receiving endpoint via a Spring AMQP listener container.
3. **quoteRequests** is the internal DirectChannel. Messages flow through the channel to the handler without writing a manual RabbitMQ consumer.
4. **handle(String.class, ...)** invokes QuoteService. The returned String is used by the framework as the reply message for the gateway.
5. The gateway reads reply destination/correlation info from the AMQP request and sends the reply over AMQP using the configured mechanism.

Topology beans are **only actually created on the broker** when an AmqpAdmin/RabbitAdmin or equivalent deployment tool is present and the account has sufficient permissions. Do not assume bean declarations mean the queue/exchange already exists in RabbitMQ. If your organization manages topology separately, provision it outside the application.

### 6.3. Service Handling the Request

~~~java
import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    public String calculate(String body) {
        String[] fields = body.split("\\|", -1);

        if (fields.length != 3) {
            return "ERROR|INVALID_REQUEST";
        }

        String requestId = fields[0];
        String productId = fields[1];

        if (!requestId.matches("[A-Za-z0-9_-]{1,64}")
                || !productId.matches("[A-Za-z0-9_-]{1,64}")) {
            return "ERROR|INVALID_REQUEST";
        }

        int quantity;
        try {
            quantity = Integer.parseInt(fields[2]);
        } catch (NumberFormatException ex) {
            return "ERROR|INVALID_QUANTITY";
        }

        if (quantity <= 0 || quantity > 100) {
            return "ERROR|INVALID_QUANTITY";
        }

        // Mock pricing rule: 50,000 VND per unit.
        long totalVnd = quantity * 50_000L;
        return "OK|" + requestId + "|" + totalVnd;
    }
}
~~~

**Why return a String instead of null?** A gateway requires a reply to complete the interaction. When the service returns a valid String, the framework has a result to send back to the gateway. If the handler **returns null/void**, the flow may not produce a reply, causing the caller to wait until timeout or triggering error behavior depending on configuration.

This example only computes a price in memory, **produces no side effects**, and stores no state. If real processing creates invoices, deducts inventory, or writes to a database, proper validation, transactions, authorization, and idempotency are required.

### 6.4. Caller Using RabbitTemplate

The requesting application can use Spring AMQP directly:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class QuoteClient {

    private final RabbitTemplate rabbitTemplate;

    public QuoteClient(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public String askQuote(
            String requestId, String productId, int quantity) {

        String request = requestId + "|"
            + productId + "|" + quantity;

        Object reply = rabbitTemplate.convertSendAndReceive(
            "quotes.requests", "quote.calculate", request);

        if (!(reply instanceof String text)) {
            throw new IllegalStateException(
                "Did not receive a valid reply / timeout");
        }
        return text;
    }
}
~~~

When invoked:

~~~java
quoteClient.askQuote("req-1001", "SKU-42", 2);
~~~

Expected successful result:

~~~text
OK|req-1001|100000
~~~

**RabbitTemplate.convertSendAndReceive(...)** sets up the request–reply mechanism matching the client configuration, sends the message, waits for a matching reply, and converts the result. When the wait time expires without a reply, the method can return null; the example treats null or a wrong type as an error. Do not use the caller receiving a String as proof that all external transactions have committed if the real service still has asynchronous steps.

In the example, Spring AMQP's default converter typically handles Strings as text content. If the producer uses JSON/binary or a custom converter, verify the actual body/contentType and payload types on both request and reply.

### 6.5. Caller-Side Timeout

A common Spring Boot configuration:

~~~yaml
spring:
  rabbitmq:
    template:
      reply-timeout: 5s
~~~

**reply-timeout** bounds how long the caller waits for a reply via RabbitTemplate, not the maximum server-side business processing duration. If the handler performs I/O or waits on downstream services, configure separate timeouts for those steps. A wait time that is too short can cause the caller to time out even while the gateway is still processing and sends the response late.

## 7. Distinguishing Four Types of Confirmation Information

AMQP request–reply involves several signals that are easily confused:

| Signal | Direction | What Does It Tell You? | What Does It Not Tell You? |
| --- | --- | --- | --- |
| **Publisher confirm** | Broker → request/reply publisher | Broker confirmed the publish under the confirm mechanism | Business handler succeeded |
| **Consumer ACK/NACK** | Consumer/gateway → broker | Acknowledgment status of the request delivery | Caller received the business reply |
| **AMQP reply message** | Gateway → caller | Business outcome per the reply contract | All other external side effects have completed |
| **Reply timeout** | Determined by caller | Reply did not arrive in time | Request was definitely not processed by the server |

In particular, a request may already be processed successfully by the service and the reply sent, while the caller disconnects or times out before reading it. When the caller retries, the system may receive **two requests for the same business operation**.

## 8. ACK, Exceptions, Requeue, and Business Errors

The inbound gateway builds on a Spring AMQP listener container; the container typically manages ACK per configuration. Do not assume the gateway creates an atomic transaction across RabbitMQ, the service handler, and the database.

### 8.1. With DirectChannel and AUTO ACK

In the example, the request passes through DirectChannel to QuoteService **synchronously**. When the handler returns a String reply, the gateway proceeds to send the AMQP reply; the listener container handles ACK according to AUTO mode and the callback result. If an exception propagates to the listener/container, reject, NACK, or requeue depends on configuration and error type.

Note: the exact ordering between publishing the reply, consumer acknowledgment, transactions, and callbacks depends on implementation and configuration. **ACK does not prove the caller read the reply.**

### 8.2. Business Errors Should Return Structured Replies

A quote request with an invalid quantity is not necessarily an infrastructure failure. In the example, QuoteService returns **ERROR|INVALID_QUANTITY** as a valid reply so the caller knows to fix the input. This avoids turning every data error into an infinite requeue loop.

A real system should use error codes, safe messages, requestId, and schemaVersion; never expose raw stack traces or internal database exceptions to the client.

### 8.3. Technical Errors Require a Dedicated Policy

Examples: database timeout, RabbitMQ reply publish error, temporary downstream outage, converter unable to parse request. When an exception is thrown:

- The container may apply ACK/NACK/requeue or error handling depending on configuration.
- The client may only observe a **timeout** if no AMQP reply is sent.
- Unbounded requeue can create a **poison message loop**, especially with invalid data.
- If the request already produced side effects before the exception, redelivery/retry risks duplication.

Choose an explicit policy: bounded retry with backoff for transient errors; quarantine/DLQ or error reply for permanent errors; state recording and reconciliation when outcomes are uncertain.

### 8.4. DLQ Does Not Automatically Send a Reply to the Caller

A dead-letter exchange/queue can receive request messages rejected without requeue, expired by TTL, or dead-lettered by broker policy. However, **routing a request to a DLQ is not equivalent to sending a business reply**. The caller may already have timed out; the system needs a separate way to report status to the user or calling system.

~~~mermaid
flowchart TD
    REQ["AMQP request"] --> V{"Validate request"}
    V -- "Invalid business input" --> BR["Return structured error reply"]
    V -- "Valid" --> H["Process business logic"]
    H --> R{"Outcome"}
    R -- "Success" --> OK["Return result reply"]
    R -- "Transient error" --> RET["Bounded retry / backoff"]
    R -- "Permanent error / retries exhausted" --> ERR["Store error, DLQ, or reply per policy"]
    RET --> H
~~~

There should never be a single blanket rule of "throw an error and retry forever" for both invalid requests and network errors.

## 9. Timeouts and Late Replies

A request–reply gateway creates a timing dependency between caller and handler. A timeline might look like this:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant B as RabbitMQ
    participant G as Inbound gateway
    participant S as QuoteService
    C->>B: Request req-1001
    B->>G: Delivery
    G->>S: Process request
    Note over C: Reply timeout occurs
    C--xC: No reply in time
    S-->>G: Late result
    G->>B: Send reply via reply-to
    Note over B,C: Caller may no longer be waiting for reply
~~~

**A caller timeout does not automatically cancel server-side work.** Depending on the implementation, the server may still be processing, write to the database, and send a reply after the caller has stopped waiting. Therefore:

1. Set timeouts according to real business SLAs and downstream wait times.
2. Include a stable **business requestId** inside the request payload.
3. If the request has side effects, apply idempotency and status lookup before retrying.
4. Do not produce oversized replies; control size and serialization time.
5. If an operation takes minutes, consider **asynchronous request submission + job ID + status event/callback**, rather than holding synchronous request–reply open for a long duration.

### 9.1. Replies Arriving with Wrong Correlation

When multiple concurrent requests share a reply mechanism, the caller must match responses by correlation. If custom reply queues/converters/header mappers drop the correlation ID, the system can time out even though the broker already holds the reply. Test concurrent requests, requestIds, and correlation IDs to catch mismatches.

### 9.2. Direct Reply-To and Durability

RabbitMQ's direct reply-to optimizes the return path for short RPCs, but it should not be treated as a durable reply queue storing results for offline callers. If responses must persist for hours, a status API may suit better than RPC over direct reply-to.

## 10. Concurrency, Prefetch, and MessageChannel

An AMQP inbound gateway can serve many requests via its listener container. Consumer count, prefetch, and channel type govern concurrent throughput and latency.

| Component | Impact | Risk |
| --- | --- | --- |
| **Listener concurrency** | Number of requests accepted/processed in parallel | Too many consumers can overload the DB or downstream services |
| **Prefetch** | Number of deliveries sent to a consumer before ACK within scope | Requests sit in consumer buffers longer, inflating unacked backlog |
| **DirectChannel** | Handler runs in a synchronous call chain | Slow handlers hold listener threads |
| **ExecutorChannel** | Offloads handler to an executor | Gateway must wait for reply asynchronously; requires tuning timeout, correlation, and capacity |
| **QueueChannel** | Buffers requests for a polling consumer | Requires poller; replies may arrive late; durability/timeouts must be designed |

### 10.1. DirectChannel Is an Understandable Choice for Demos

In the example, the gateway invokes the handler over a DirectChannel and receives the reply within the same logical interaction. This bounds in-flight execution to listener concurrency and makes exception paths easy to trace. However, a slow handler holds the listener thread; enforce realistic timeouts and protect downstream systems.

### 10.2. When Switching to ExecutorChannel

Do not replace DirectChannel with ExecutorChannel merely to boost throughput. The gateway may still wait for a reply on a temporary channel while the handler executes on a worker thread, requiring careful timeout configuration. When the executor queue fills up or the reply arrives past timeout, the caller may get no result.

Unlike a one-way inbound adapter, **a gateway has a reply-waiting contract**, so how ACK and listener callback completion behave must be verified against the actual configuration; never assume ACK happens automatically right after the executor accepts the task or definitely waits until all side effects finish.

### 10.3. Backpressure

Suppose the system receives 500 quote requests/second, but the service can only calculate and respond to 80 requests/second. Continuing to raise listener or executor counts without limits increases wait times and backlog, causing even more caller timeouts.

Solutions can include:

- Capping listener concurrency to real downstream capacity.
- Configuring timeouts for both RPCs and downstream calls.
- Bounding queue capacity and applying rejection or producer-throttling policies.
- Tracking pending requests, unacked deliveries, p95/p99 latency, and retries.
- Moving long-running tasks to stateful asynchronous workflows.

## 11. Idempotency When Requests Have Side Effects

The demo QuoteService only computes values, making it easy to re-run. Now consider a **PaymentGatewayService** that creates a payment transaction:

1. Caller sends requestId **pay-1001**.
2. Inbound gateway receives the request; service records the transaction successfully.
3. Connection drops before the reply reaches the caller.
4. Caller times out and resends requestId pay-1001.

Without idempotency, two calls can create two transactions. You should:

- Use a **requestId** or **idempotencyKey** that remains stable across retries.
- Enforce the key check where the side effect happens, ideally backed by a unique constraint and appropriate transaction.
- Persist the business result of the successful execution so it can be returned for duplicate requests.
- Distinguish a duplicate retry with the same payload from **a reused requestId with a different payload**.
- Provide recovery when the process crashes after committing but before sending the reply.

**Correlation ID is not automatically an idempotency key.** Libraries may generate a fresh correlation per RPC attempt; business identity must be committed in the request contract.

### 11.1. ACK and Transactions Are Not Enough for Exactly-Once

A single database transaction does not automatically encompass request acknowledgment and reply publishing over RabbitMQ. If the database commits but consumer ACK never reaches the broker, the request can be redelivered. If the reply is published but ACK is lost, the caller may see two replies or a late reply. Business-layer idempotency remains necessary.

## 12. ErrorMessage, errorChannel, and replyChannel

In Spring Integration:

- **replyChannel** indicates the reply path of a Spring Message inside a flow.
- **errorChannel** is where an ErrorMessage can be routed under appropriate error-handling configurations.
- **AMQP reply-to** specifies the RabbitMQ protocol destination where the gateway publishes the reply back to the caller.

These three concepts are not interchangeable.

If a handler throws an exception, how the error propagates, turns into an ErrorMessage, triggers listener reject/requeue, or becomes an error reply **depends on the endpoint and configuration**. An ErrorMessage is not automatically an AMQP reply body that callers understand.

If clients should always receive business error codes, explicitly define how **predictable errors** are converted into valid replies. For infrastructure errors, log, emit metrics, retry, alert, and dead-letter per policy; if sending a technical error reply, never expose stack traces, database internals, or credentials.

## 13. Lifecycle, Connectivity, and Security

An inbound gateway depends on the listener container, RabbitMQ ConnectionFactory, converters, and application schedulers/thread pools. Many endpoints participate in **Lifecycle/SmartLifecycle** with **start(), stop(), isRunning(), autoStartup**, and **phase**.

| Item | Operational Concern |
| --- | --- |
| **Startup** | RabbitMQ already has exchange/queue/binding; listener container has consume permissions |
| **Connectivity** | Host, TLS, virtual host, credentials, and reconnects |
| **Shutdown** | Stop accepting new requests; manage in-flight requests and unsent replies |
| **Overload** | Listener concurrency, prefetch, downstream latency, and queue depth |
| **Security** | Least-privilege accounts, no logging of sensitive payloads, business auth/authorization |
| **Observability** | Requests received, replies sent, timeouts, errors, redeliveries, business outcomes |

**isRunning() = true does not prove the broker and reply path are healthy.** Monitor connections, queue ready/unacked counts, consumer counts, listener errors, and RPC completion rates.

### 13.1. Stopping and Restarting

During graceful shutdown:

1. Stop accepting new requests or pause the listener using a supported mechanism.
2. Let in-flight requests finish within the committed time window, or rely on idempotency/redelivery to resume cleanly.
3. Monitor in-flight/unacked deliveries, failed reply publishes, and timeouts.
4. Close resources following the Spring lifecycle; do not close a shared ConnectionFactory arbitrarily.
5. After restart, inspect request queue backlog and reprocessing behavior per the ACK policy.

Do not assume **stop()** will automatically send errors to every waiting caller. If callers time out during maintenance, they need clear retry/idempotency rules or a status lookup mechanism.

## 14. Required Test Suite

| Scenario | What to Verify |
| --- | --- |
| Valid request | req-1001/SKU-42/2 returns OK and total 100000 |
| Invalid payload | Handler returns a structured error reply with clear code, no poison loop |
| Routing misses queue | Caller times out or receives error per policy, with metrics/alerts |
| Missing/invalid reply-to | Gateway does not promise a successful reply; error is observable |
| Two concurrent requests | Correlation never mixes results between callers |
| Service slower than timeout | Caller times out; late reply behavior handled |
| Broker restart | Consumer reconnects; unacked requests can redeliver |
| Handler exception | Requeue/DLQ or error reply follows configured policy |
| Duplicate requestId | Side effects do not execute twice |
| Disconnect after side effect | Caller retry creates no duplicate business outcome |
| Peak load | Latency, unacked, ready backlog, consumer count, and timeouts |
| Graceful shutdown | In-flight requests complete or recover in a controlled manner |

### 14.1. Steps to Test the Example

1. Start a test RabbitMQ broker and the service with QuoteAmqpGatewayConfiguration.
2. Verify **quotes.requests** exchange and **quotes.request.q** have binding **quote.calculate**.
3. Call QuoteClient.askQuote with requestId **req-1001**, productId **SKU-42**, quantity **2**; verify reply **OK|req-1001|100000**.
4. Send quantity 0; verify reply **ERROR|INVALID_QUANTITY**.
5. Pause the listener or stop the service and invoke the client; verify reply timeout rather than assuming broker publish failed.
6. Send two different requestIds concurrently to verify replies match correlation properly.
7. Trigger an exception in the handler in a controlled test environment; observe retry/requeue and confirm no infinite loop.

Running the service in the same process as the test client only demonstrates the RabbitTemplate API; real deployments should test across two separate processes to catch topology, network, authentication, and connection open/close issues.

## 15. Common Mistakes

**Choosing a one-way inbound adapter and expecting a business reply.** An adapter does not perform request–reply on its own; use a gateway or build a dedicated reply mechanism.

**Confusing a RabbitMQ ACK with an AMQP reply.** ACK concerns delivery acknowledgment; a reply is business data sent to the reply destination.

**Ignoring reply-to and correlation.** A request without a reply destination or a reply that loses correlation can cause client timeouts.

**Treating direct reply-to as a durable queue.** It is optimized for short RPCs, not storing results for offline clients.

**Using a timeout to infer the server did not execute.** The server may have committed and the reply was lost; retries must be idempotent.

**Returning null from a service activator in a request–reply flow.** The gateway may fail to receive a complete reply message.

**Retrying invalid-data requests infinitely.** Return a business error or quarantine instead of creating a requeue loop.

**Pushing raw technical errors into replies without a contract.** Clients need stable error codes, not stack traces or arbitrary exceptions.

**Raising listener concurrency without measuring downstream capacity.** That may simply increase in-flight requests and timeouts.

**Using correlation ID as the sole deduplication key.** Use a business requestId/idempotencyKey that stays stable across retries.

**Assuming gateway and database share one transaction.** There is no atomic guarantee across database, request ACK, and reply publish without dedicated design.

## 16. Self-Check Questions

1. Why does an AMQP inbound gateway differ from an inbound channel adapter even though both consume requests from a RabbitMQ queue?
2. What metadata must the caller send so the gateway can return the reply accurately?
3. How does AMQP reply-to differ from Spring replyChannel?
4. What does RabbitTemplate.convertSendAndReceive solve that one-way convertAndSend does not?
5. If the service returns null, what can the caller observe?
6. How do producer confirm, consumer ACK, and business reply differ?
7. When a reply arrives after the caller times out, what risks must the caller and server handle?
8. Why is a stable requestId/idempotencyKey needed even when a correlation ID is already present?
9. When a handler throws an exception, why can you not assume the caller receives a valid error reply?
10. When should a fixed reply queue be used instead of direct reply-to? What must be evaluated?
11. Why can increasing ExecutorChannel concurrency make timeout rates worse?
12. If the application crashes after committing to the database but before sending the reply, what issue can request redelivery cause?
13. Which metrics show that the gateway is running but the reply path is broken?
14. When processing takes minutes, why can an asynchronous workflow with a job ID be better than AMQP RPC?

## Summary

An **AMQP inbound gateway** receives requests from a **RabbitMQ request queue**, maps deliveries into **Spring Messages**, routes requests through a **MessageChannel** for processing, and returns a **business reply** to the AMQP reply destination. For the flow to work reliably, you must define payload/converter contracts, reply-to, correlation, request/reply timeouts, and error paths. **Publisher confirm, consumer ACK, and business reply** are three distinct signals. A reliable gateway must manage timeouts, late replies, redeliveries, idempotency when side effects exist, concurrency, security, and listener lifecycle. These principles help you apply AMQP request–reply properly inside a Spring Integration system spanning files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, instead of equating every message receipt with a completed business transaction.

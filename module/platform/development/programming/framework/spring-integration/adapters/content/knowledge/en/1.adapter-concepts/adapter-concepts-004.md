# Distinguishing One-Way Adapters and Two-Way Gateways

## Learning Objectives

After this lesson, you will be able to:

- Distinguish a **channel adapter** with a one-way message contract from a **gateway** with a request–reply contract.
- Identify all four endpoint variants: inbound adapter, outbound adapter, inbound gateway, and outbound gateway.
- Explain the role of MessageChannel, replyChannel, errorChannel, timeouts, and correlation IDs in an exchange.
- Choose the right endpoint when integrating files, SFTP, HTTP, JMS, AMQP, Kafka, or databases.
- Read a Java DSL example combining a one-way outbound file adapter and a messaging gateway returning a result.
- Evaluate retry, timeout, deduplication, and delivery-guarantee risks across both models.

## 1. The Problem: Fire-and-Forget or Need a Reply?

Suppose an order-processing application must perform two tasks:

1. When an order is approved, **export a CSV file** for operations. The application only needs to know whether writing the file succeeded, with no business reply message required for further calculation.
2. Before quoting a price, **call a pricing service** and use the returned amount to finalize the order. The next step strictly depends on the result of that call.

The two tasks differ in their **communication contract**. Exporting the CSV fits a **one-way channel adapter**; pricing requires a **request–reply gateway**.

In Spring Integration, endpoints exchange **Message<?>** objects over **MessageChannel** instances. A message consists of a **payload** (data) and **headers** (metadata for routing, correlation, error handling, and protocol mapping).

A **channel adapter** connects the messaging flow to an external system along one direction of message flow:

- **Inbound adapter:** brings data from outside **into** a MessageChannel.
- **Outbound adapter:** takes data from a MessageChannel and **sends it out** to an external system.

A **gateway** connects two sides under a **request–reply** contract: it receives or constructs a request, crosses the protocol/messaging boundary, and returns a response to the party awaiting the result.

~~~mermaid
flowchart TB
  subgraph OneWay["Channel adapter: one-way message flow"]
    A["MessageChannel"] --> B["Outbound adapter"] --> C["Target system"]
  end
  subgraph TwoWay["Gateway: request–reply"]
    X["Caller / Request channel"] --> G["Gateway"] --> Y["System / Handler"]
    Y -->|Response| G
    G -->|Reply| R["Caller / Reply channel"]
  end
~~~

**One-way does not mean devoid of technical confirmation.** An outbound adapter can still block while writing a file, receive an ACK from a broker, time out, or throw an exception. The difference is that an adapter **does not produce a business reply message inside the flow** the way a gateway does.

**Two-way does not necessarily mean a duplex network connection or synchronous execution at all times.** A gateway describes a request–reply relationship at the application level; sending and receiving may use separate channels or require asynchronous correlation mechanisms.

## 2. Four Endpoint Types to Distinguish

First determine the **direction of data** relative to the Spring Integration application; then determine **whether a business reply is needed**.

| Endpoint Type | Data Flow Direction | Business Reply in Flow? | Illustrative Case |
| --- | --- | --- | --- |
| **Inbound channel adapter** | External system → MessageChannel | No | Scanning files, reading SFTP, receiving JMS messages |
| **Outbound channel adapter** | MessageChannel → external system | No | Writing files, publishing to Kafka, sending AMQP messages |
| **Inbound gateway** | External system → request channel → reply back to caller | Yes | HTTP POST waiting for processing outcome and HTTP response |
| **Outbound gateway** | Request channel → external system → reply channel | Yes | Calling an HTTP API and extracting the response body for next steps |

### 2.1. Inbound Adapter: Ingesting Without a Business Reply Pair

For example, a File inbound adapter is triggered by a poller every few seconds. It picks up a file, wraps the File object into a message, and sends it to a channel. Downstream subscribers read the CSV, validate it, and save the order. The file system is not a caller waiting for a reply message back from the flow.

For protocols with acknowledgments such as JMS, AMQP, or Kafka, the adapter may participate in the source's ACK/commit/redelivery mechanisms. Those signals operate at the **transport/delivery level**; they do not turn an inbound adapter into an inbound gateway.

### 2.2. Outbound Adapter: Creating Side Effects

A message containing CSV content is sent to exportChannel. The outbound file adapter consumes the message, writes the file to the target directory, and ends the one-way endpoint. If a write permission error or file-exists error occurs, the adapter can report the error per configuration; that error is distinct from a **business response**.

Similarly, an outbound Kafka adapter publishes a record. The producer may receive a callback or broker acknowledgment, but a reply message carrying the consumer's processing result does not automatically flow back.

### 2.3. Inbound Gateway: External Caller Requests a Result

For example, an HTTP client calls an API to generate a quote:

~~~text
HTTP client --POST /quotes--> HTTP inbound gateway
               |
               v
         requestChannel
               |
               v
        Validate + PriceService
               |
               v
           reply message
               |
               v
HTTP client <--HTTP response-- HTTP inbound gateway
~~~

The gateway creates a request message from the HTTP request, feeds it into the flow, waits for or receives the reply message per the configured contract, and maps it to an HTTP response. If no reply arrives within the allowed timeout, the timeout must be handled; never leave the client hanging indefinitely.

### 2.4. Outbound Gateway: Flow Calls Out and Uses the Result

Suppose the system must fetch a credit limit before confirming an order. An outbound HTTP gateway sends a request to the partner's API, receives the response, and converts it into a message for the next routing or validation step.

~~~mermaid
sequenceDiagram
    participant F as Internal flow
    participant G as Outbound HTTP gateway
    participant S as Partner API
    F->>G: Message<CreditCheckRequest>
    G->>S: HTTP request
    S-->>G: HTTP response
    G-->>F: Message<CreditCheckResponse>
    F->>F: Inspect result and decide
~~~

The critical point is that the flow **needs the response data to continue**. If you only want to emit a notification event, an outbound adapter is usually simpler and more appropriate.

## 3. How Does a Messaging Gateway Differ from an HTTP/JMS Gateway?

Spring Integration also provides a **messaging gateway**, typically declared with **@MessagingGateway** and a Java interface. This is an **entry/exit point allowing Java code to invoke an integration flow like a regular method call**:

~~~java
@MessagingGateway(defaultRequestChannel = "quoteRequests")
interface QuoteGateway {
    QuoteResponse calculate(QuoteRequest request);
}
~~~

The caller only sees the calculate method, while the gateway builds a request message, sends it to the channel, and converts the reply into the return value. For methods with a return value, this is a request–reply contract.

Distinguish three concepts:

- **Messaging gateway (@MessagingGateway):** bridges **Java method ↔ messaging flow**; can expose a result-returning interface or a one-way method.
- **Inbound protocol gateway:** bridges **external system request → messaging flow → external response**; for example, an HTTP inbound gateway.
- **Outbound protocol gateway:** bridges **messaging flow → request to external system → response back to flow**; for example, an HTTP outbound gateway.

A method on a messaging gateway returning **void** can be a one-way call. Therefore, not every API with "gateway" in its name always waits for a result; always check the **specific method/endpoint contract**.

## 4. MessageChannel and the Request–Reply Contract

In the adapter model, data travels one way through a channel. In the gateway model, beyond the request path, there must also be a **reply path**.

~~~mermaid
flowchart LR
    Caller["Caller"] --> G["Messaging gateway"]
    G --> Req["requestChannel"]
    Req --> H["Service activator<br/>processes request"]
    H --> Rep["replyChannel / Temporary channel"]
    Rep --> G
    G --> Caller
~~~

When a **@MessagingGateway** is invoked and expects a result, the framework can create or use a reply channel and attach a reference to it in the request's **replyChannel** header. The handler produces a reply; the framework routes the reply back to that channel so the gateway can complete the call. Depending on configuration, you can specify a **defaultReplyChannel** or use a temporary reply channel.

Commonly involved headers:

| Header / Mechanism | Meaning in Request–Reply |
| --- | --- |
| **replyChannel** | Specifies where to send the reply message when the flow or endpoint supports a reply contract |
| **errorChannel** | Where an ErrorMessage can be routed when an error path is configured appropriately |
| **correlationId** | Matches responses to requests when handling concurrent requests or asynchronous channels |
| **id, timestamp** | Identifies and traces messages, but should not replace a stable business key |
| **replyTimeout** | Caps how long to wait for a reply in a synchronous gateway model |
| **requestTimeout** | Caps how long to wait when sending/placing a request onto the channel if configured and supported by the channel |

A reply can be produced by a service activator, transformer, external gateway, or routing branch. If a handler produces no reply, returns null, or drops the replyChannel header, a waiting gateway can time out. Never assume every error is automatically converted into a valid reply message.

### 4.1. Role of Channel Types

| Channel Type | Consequence for Adapters | Consequence for Gateways |
| --- | --- | --- |
| **DirectChannel** | Invokes subscriber synchronously; slow I/O can block producer thread | Easy to use for synchronous request–reply; exceptions typically propagate along the call chain |
| **ExecutorChannel** | Asynchronous processing via an executor | Must consider reply timing, timeouts, errors, and ordering |
| **QueueChannel** | Requires a consumer/poller to pull messages from the queue | Can serve as request or reply channel, but needs a consumer and explicit correlation conditions |
| **PublishSubscribeChannel** | Broadcasts events to multiple subscribers | Does not automatically determine which reply answers a request when multiple branches exist |

Channels do not decide whether the target system succeeded. A gateway receiving a reply is meaningful only within the **response contract agreed upon by both sides**.

### 4.2. Synchronous, Asynchronous, and Timeouts

A synchronous gateway normally makes the caller wait until a reply arrives or the timeout expires. If a flow calls an HTTP API taking several seconds, total elapsed time can include channel waiting, queueing, network transmission, target processing, and receiving the response. Set explicit bounds for each segment so callers are not held indefinitely.

Gateways can also implement asynchronous interactions depending on the API, return type, and endpoint. In that case, requests and replies need correlation metadata or an appropriate completion mechanism. **Request–reply is an exchange pattern**, not a guarantee that every request executes on a single thread.

## 5. Java DSL Example: One-Way File Export vs. Two-Way Price Calculation

This example places two flows side by side to clearly show the boundary outcome:

1. **Adapter:** a service sends CSV into exportChannel; the outbound file adapter writes it to a directory. The service receives no QuoteResponse or business message back from the adapter.
2. **Messaging gateway:** Java code invokes PriceGateway.quote(...) with a PriceRequest; the pricing flow produces a PriceReply and the gateway returns the result to the caller.

The example uses Spring Integration Java DSL with Spring Boot, the spring-integration-file module, and Java 17+ for records. You can rely on Spring Boot's dependency management to select a compatible Spring Integration version.

### 5.1. Declaring Both Flows

~~~java
import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.file.FileHeaders;
import org.springframework.integration.file.dsl.Files;
import org.springframework.integration.file.support.FileExistsMode;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class AdapterGatewayConfiguration {

    @Bean
    public MessageChannel exportChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow exportFlow() {
        return IntegrationFlow.from("exportChannel")
            .handle(Files.outboundAdapter(new File("./data/export"))
                .autoCreateDirectory(true)
                .fileNameGenerator(message ->
                    (String) message.getHeaders().get(FileHeaders.FILENAME))
                .fileExistsMode(FileExistsMode.FAIL))
            .get();
    }

    @Bean
    public MessageChannel priceRequests() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow priceFlow() {
        return IntegrationFlow.from("priceRequests")
            .handle(PriceRequest.class, (request, headers) -> {
                if (request.quantity() <= 0) {
                    throw new IllegalArgumentException(
                        "quantity must be greater than 0");
                }
                long total = request.quantity() * 50_000L;
                return new PriceReply(request.productId(), total);
            })
            .get();
    }
}

@MessagingGateway(
    defaultRequestChannel = "priceRequests",
    defaultReplyTimeout = "3000")
interface PriceGateway {
    PriceReply quote(PriceRequest request);
}

record PriceRequest(String productId, int quantity) {}

record PriceReply(String productId, long totalVnd) {}
~~~

**Reading the export flow:** exportChannel is a DirectChannel; the outbound file adapter subscribes to the channel. The adapter takes the payload and filename from the FileHeaders.FILENAME header. Once writing completes per contract, the flow ends at the one-way handler without producing a business reply.

**Reading the price flow:** when PriceGateway.quote is called, the messaging gateway constructs a request message and sends it to priceRequests. The service activator validates the quantity and returns a PriceReply object; the framework creates/routes the reply back to the gateway, and the quote method returns PriceReply to the caller.

**defaultReplyTimeout = "3000"** sets the messaging gateway's reply wait timeout to 3,000 milliseconds. Specific error handling on timeout or when a handler throws an exception must be designed according to configuration and calling APIs. A timeout does not automatically cancel work already handed off asynchronously.

### 5.2. Producer Comparing Both Invocation Styles

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class DemoBusinessService {

    private final MessageChannel exportChannel;
    private final PriceGateway priceGateway;

    DemoBusinessService(
            @Qualifier("exportChannel") MessageChannel exportChannel,
            PriceGateway priceGateway) {
        this.exportChannel = exportChannel;
        this.priceGateway = priceGateway;
    }

    PriceReply execute() {
        boolean accepted = exportChannel.send(
            MessageBuilder.withPayload("productId,quantity\nP-100,2\n")
                .setHeader(FileHeaders.FILENAME, "order-P-100.csv")
                .build());

        if (!accepted) {
            throw new IllegalStateException(
                "Failed to send message to exportChannel");
        }

        return priceGateway.quote(new PriceRequest("P-100", 2));
    }
}
~~~

If the target directory is writable and no conflicting file exists, the adapter flow attempts to write **./data/export/order-P-100.csv** with two CSV lines. The gateway call returns a PriceReply with **productId = P-100** and **totalVnd = 100000** according to the simulated calculation rule.

**Difference between the two interactions:** send puts a message onto a channel; quote has a **business return value** generated from the flow's reply. With DirectChannel, a file-write error can propagate back to the producer as an exception; that does not turn the file adapter into a gateway.

This code is an educational example: prices are hardcoded rather than pulled from a real price list; filenames must be sanitized before using user input; production CSV content needs an encoder to handle commas, quotes, and newlines. Do not treat successful file writing as confirmation that the partner has processed the order.

### 5.3. Replacing the Pricing Handler with an External HTTP Service

In the example above, PriceGateway is the **gateway from a Java method into an internal flow**. If prices must be computed by an external system, you can replace the internal service activator with an **outbound HTTP gateway** that sends PriceRequest to the API and receives PriceReply. The diagram becomes:

~~~text
Java code
  |
  v
@MessagingGateway interface
  |
  v
priceRequests
  |
  v
Outbound HTTP gateway ---> External pricing API
  ^                              |
  |                              |
  +---------- HTTP response -----+
  |
  v
Reply returns to Java caller
~~~

At that point, you must configure the HTTP endpoint, method, URL, serializer/deserializer, authentication, connection and response timeouts, and HTTP status handling. An outbound HTTP gateway fits because the flow genuinely **needs the response body**. If it only notifies "order created" without needing a body, a one-way outbound adapter may be more appropriate.

## 6. Choosing Between Endpoints in Common Integration Scenarios

| Scenario | Suggested Choice | Reason |
| --- | --- | --- |
| Reading new files from a shared directory | File inbound adapter + poller | No caller waiting for a business reply |
| Synchronizing files from SFTP on a schedule | SFTP inbound adapter | One-way ingestion; records processed downstream |
| Writing or uploading a file to SFTP | File/SFTP outbound adapter | One-way data export |
| HTTP client sends POST /orders and needs order ID | HTTP inbound gateway | Must map the flow's reply to an HTTP response |
| Flow calls a REST API and needs the response body | HTTP outbound gateway | Request–reply to continue processing |
| Publishing an OrderCreated event to Kafka | Kafka outbound adapter | One-way publish; broker ACK is not a business reply |
| Consuming OrderCreated events from Kafka | Kafka inbound adapter | Feeds records into messaging flow; has offset mechanics |
| Sending a notification to a JMS/AMQP queue | JMS/AMQP outbound adapter | Produces a message for a downstream receiver |
| Sending a JMS request and awaiting reply on reply destination | JMS outbound gateway | Requires correlation and waiting for response |
| Querying a database to feed results to next step | Appropriate request–reply endpoint/gateway | Flow needs returned data, not just an update |
| Java app wants to invoke a flow like a method | @MessagingGateway | Hides channel/message details from caller |

There is no rule that **one protocol has only one endpoint type**. HTTP alone supports inbound adapters, inbound gateways, outbound adapters, and outbound gateways; which one fits depends on the request and response contract. Likewise, JMS provides both one-way send/receive adapters and request–reply gateways.

## 7. Timeouts, Retries, and Errors: How Do They Differ?

### 7.1. One-Way Adapters

Adapters mainly report status based on receiving or sending at the endpoint/client level. Failures can stem from invalid data, connectivity, permissions, destination misconfiguration, overload, or I/O errors.

- With **DirectChannel**, synchronous outbound handlers can throw exceptions back to the caller.
- With **ExecutorChannel** or QueueChannel, sending can fail after the producer already returned successfully; separate ErrorMessage, retry, or state-tracking mechanisms are needed.
- For message-driven inbound adapters, examine source ack/commit/redelivery; for polling inbound adapters, examine the poller, source filters, and restart recovery.

Adapters do not inherently prevent duplicates or data loss. For example, a Kafka producer drops its connection after the broker stores the event but before the client receives an ack; if retried, the consumer may see two identical events.

### 7.2. Request–Reply Gateways

Gateways add the requirement to **complete an exchange**: they must receive the right reply, convert it to the type the caller expects, and handle missing replies.

- **Timeout:** set response timeouts aligned with system SLAs. A timeout only tells the caller a reply did not arrive in time; **it does not prove the target operation never ran**.
- **Correlation:** with concurrent requests or broker-based replies, use proper correlation IDs / reply destinations to route results back to the right caller.
- **Error results:** distinguish technical errors like timeouts from business rejections like "credit limit exceeded" or "insufficient stock". Design response payloads or dedicated error channels accordingly.
- **Retry:** a gateway retrying a request can cause duplicate side effects on the target. For resource-creation commands, enforce stable idempotency keys and reconciliation.
- **Response contract:** specify reply data types, schemas, error codes, correlation info, and validity window of results.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant S as Target system
    C->>G: Request #A
    G->>S: Send request #A
    Note over G: Wait within timeout
    G-->>C: Timeout
    S-->>G: Late reply #A arrives
    Note over G,S: Must handle late reply<br/>and operation state
~~~

The diagram illustrates why retrying after a timeout must be designed carefully. The earlier attempt may have already mutated state on the target system. Late replies must also be handled according to gateway and infrastructure rules; never treat one implicitly as the reply to a newer request.

### 7.3. errorChannel Is Not replyChannel

**replyChannel** carries return data for the request–reply contract. **errorChannel** is used in error-handling configurations to receive ErrorMessages. When a handler throws an exception, whether the error propagates to the caller, moves to errorChannel, or is handled by a listener container depends on threads, channels, endpoints, and actual configuration.

Do not send an arbitrary ErrorMessage directly into replyChannel assuming the caller will always receive a valid business response. Explicitly define how errors map into status codes and payloads understood by the partner or API caller.

## 8. Call Volume and Processing Capacity

Gateways introduce a temporal coupling between caller and outcome:

| Criterion | One-Way Channel Adapter | Request–Reply Gateway |
| --- | --- | --- |
| Must caller wait for business return data? | No | Yes, unless designed with a separate async API |
| Risk when downstream is slow | Backlog or blocked thread depending on channel/client | Backlog, held open requests, timeouts, and late replies |
| Correlation tracking | Useful for tracing/reconciliation | Essential with multiple asynchronous requests/replies |
| Load limits | Poller, concurrency, queue capacity, rate limits | All of the above plus in-flight requests, timeouts, connection pools |
| Confirmation level | Per adapter and protocol | Per response contract plus target guarantees |
| Safe retry | Needs idempotency when side effects exist | Even stricter control needed because timeouts can hide completed side effects |

For example, an API taking 30 seconds while an HTTP gateway times out after 3 seconds causes callers to see errors even though the API may finish later. For long-running operations, consider a **202 Accepted + job ID + status polling/callback** design rather than holding a request–reply connection open too long.

That asynchronous pattern can use adapters to ingest or emit events, while the status-query contract is defined separately. Changing the endpoint does not substitute for defining UX and system SLAs.

## 9. Transactions and Delivery Guarantees

A successful request–reply call does not guarantee **end-to-end exactly-once** execution. For example:

1. The gateway calls a payment creation API; the target creates the payment.
2. The connection drops before the response reaches the caller.
3. The caller times out and resends the same operation.

If the API lacks an idempotency key, two transactions may be created. Likewise, when an outbound adapter sends an event to a broker but fails to record the sent state in time, a rerun may emit it again.

Mechanisms to evaluate:

- **Idempotency key:** a business key stable across retries, verified by the receiver.
- **Correlation ID:** used for request–reply matching and tracing; does not replace an idempotency key by default.
- **Outbox/inbox:** helps coordinate persisting business state and publishing/consuming messages across multiple resources.
- **Acknowledgment/offset:** understand JMS, AMQP, and Kafka semantics when producing or consuming messages.
- **Transactions:** claim atomicity only where underlying resources and configuration truly support it.
- **Compensation:** handles cases where multiple systems partially succeeded without a shared transaction.

With file/SFTP, similar issues arise when a file is written but the app stops before marking it "exported"; re-exporting requires naming/overwrite rules and reconciliation. With HTTP gateways, define status code meanings and safe retry behavior after timeouts.

## 10. Practical Flow Design Guide

When selecting an endpoint, follow this sequence:

1. **Identify who initiates the interaction.** Does an external system send in, or does the application flow send out?
2. **Determine whether a reply is needed.** Does the next step strictly require a business result back from the other side?
3. **Design payload and headers.** Pick request/reply types, schemas, correlation IDs, idempotency keys, and protocol-mapped headers.
4. **Select channels.** DirectChannel for simple synchronous paths; ExecutorChannel/QueueChannel when decoupling load, paired with capacity bounds and error paths.
5. **Set time bounds.** Request send, connection, reply wait, and retry backoff timeouts need not share one single value.
6. **Define completion semantics.** Channel acceptance, target acknowledgment, or end-to-end business completion?
7. **Test failures and restarts.** Connection loss, late replies, duplicate messages, full queues, schema changes, and process crashes.

### 10.1. Minimum Test Scenarios

| Scenario | What to Verify |
| --- | --- |
| Adapter writes file successfully | File has the expected content, name, and location |
| Adapter fails to write file | Exception or error flow is observed; never reports false success |
| Gateway receives normal reply | Result has expected type, matches request, and arrives within timeout |
| Gateway receives no reply | Timeout is detected; caller executes fallback/handling logic |
| Handler throws exception | Error is mapped properly; caller never hangs indefinitely |
| Two concurrent requests | Replies are never mixed up between requests |
| Reply arrives after timeout | Does not corrupt business state or caller session |
| Retry under ambiguous state | Idempotency key remains stable; no duplicate side effects |
| Application restarts | Unprocessed/sent messages recover according to chosen policy |

## 11. Common Misconceptions

**"One-way" means no error handling needed.** False: connection failures, serialization errors, write permissions, and timeouts still must be reported or managed.

**Receiving a broker ACK means a business reply arrived.** An ACK confirms a broker delivery tier; it usually says nothing about the consumer completing business processing.

**Two-way gateways guarantee zero loss or duplicates.** Request–reply only defines the exchange contract; transactions, idempotency, and proper acknowledgments are still needed to control delivery.

**Every HTTP call requires a gateway.** If the flow needs the response body, an outbound HTTP gateway fits; if it only performs a one-way action, an adapter can be used depending on endpoint capabilities and API contract.

**@MessagingGateway always calls an external system.** This annotation creates a Java interface into an internal flow; the flow itself decides whether to invoke an HTTP/JMS gateway.

**When a gateway times out, the target operation definitely failed.** The target may have already executed it, be executing it, or the reply may have been lost; reconciliation is mandatory.

**replyChannel and errorChannel are the same.** One routes business replies, while the other is for error-handling paths depending on configuration; never conflate their contracts.

## 12. Self-Check Questions

1. An outbound adapter writes a file successfully without returning a business message. Why does completing the file write not make it a gateway?
2. If an HTTP client calls the application and needs the order ID immediately in the response, should you choose an inbound adapter or an inbound gateway? Why?
3. When a flow calls a tax calculation API and uses the tax amount to compute the grand total, why is an outbound gateway appropriate?
4. In Spring Integration, what problem does @MessagingGateway solve differently from an outbound HTTP gateway?
5. What role does the replyChannel header play? When is a correlation ID required?
6. If a gateway times out after the partner already created the order, what mechanism must retries include to prevent creating two orders?
7. Why do DirectChannel and ExecutorChannel lead to different ways of observing errors?
8. When a Kafka message is accepted by the broker, is that acknowledgment a business reply from the consumer?

## Summary

**Channel adapters** connect external systems into or out of Spring Integration via **one-way message flows**; **gateways** add a **request–reply contract** so a caller or flow can receive and use a result. Picking the right one begins with two questions: **who initiates the interaction** and **is business response data required**. From there, design channels, payloads/headers, replyChannel, errorChannel, timeouts, correlation, retries, and idempotency for the specific protocol. This distinction enables accurate implementations across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases without mistaking technical acknowledgments for business outcomes.

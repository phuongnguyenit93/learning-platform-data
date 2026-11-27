# JMS outbound gateway request-reply

## 1. When is a JMS outbound gateway used?

An order-management application written in Spring Integration needs to ask a legacy warehouse system: *"Does order ORD-501 have enough stock to ship?"*. The warehouse system only supports JMS communication: it receives requests on the `inventory.check.request` queue and sends replies back to the destination specified in the request. The Spring Integration application must **send a JMS request, wait for the matching JMS reply, convert the reply into a Spring Message, and return the result to the caller**.

The **JMS outbound gateway** fulfills this exact role. It is a two-way communication point where **Spring Integration initiates the request**. It differs from a `JMS outbound channel adapter`: an adapter only pushes a message to the broker, whereas a gateway provides a mechanism to correlate a request with its reply within a single logical call.

In the **SPRING_INTEGRATION_ADAPTERS** module, inbound/outbound adapters, gateways, pollers, and `MessageChannel` connect external systems into integration flows. Examples across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases all require a clear payload/header contract, timeout/error handling at the proper boundaries, and connection lifecycle management. This lesson focuses on **JMS outbound gateway request-reply**, applying those principles to connecting with a JMS broker.

**Learning objectives:**

1. Distinguish an outbound gateway from an outbound adapter and an inbound gateway.
2. Configure a flow that sends a JMS request and receives a JMS reply using Spring Integration Java DSL and XML.
3. Explain `JMSReplyTo`, `JMSCorrelationID`, `JMSMessageID`, temporary/fixed reply destinations, and business request IDs.
4. Handle timeouts, late replies, converter errors, broker failures, transactions, and redeliveries without creating duplicate business side effects.
5. Test the flow with a real JMS consumer and interpret essential operational metrics.

## 2. How it works from Spring Message to JMS reply

~~~mermaid
sequenceDiagram
    participant App as Spring application
    participant Flow as MessageChannel
    participant Gateway as JMS outbound gateway
    participant Broker as JMS broker
    participant Service as Inventory JMS server

    App->>Flow: Spring Message (check ORD-501)
    Flow->>Gateway: Request message
    Gateway->>Broker: JMS request + JMSReplyTo + correlation
    Broker->>Service: Deliver inventory.check.request
    Service->>Broker: JMS reply to JMSReplyTo
    Broker-->>Gateway: Matching JMS reply
    Gateway-->>Flow: Spring Message result
    Flow-->>App: AVAILABLE / OUT_OF_STOCK
~~~

A typical request-reply cycle has these steps:

1. **The Spring caller** sends a Spring Message to the outbound gateway's request channel. The payload may be a JSON `String`, `byte[]`, or a Java object converted per contract.
2. The gateway **selects the JMS request destination** and uses `JmsTemplate`/JMS provider to send the JMS message. It records reply destination info in `JMSReplyTo` and maintains correlation tracking for the pending request.
3. The broker delivers the request to a consumer in the external system. The consumer processes it and sends a reply JMS message to the destination agreed upon by the gateway or protocol.
4. The gateway **receives the reply matching the request**, converts the JMS reply into a Spring Message, and sends it to the integration flow's reply channel.
5. The Spring caller obtains the reply payload or encounters a timeout/exception depending on configuration and runtime conditions.

An outbound gateway is not a poller periodically looking for requests inside the app. It is **triggered when a Spring Message arrives**. Waiting for/receiving the JMS reply is handled by the gateway's JMS infrastructure; exact reception mechanics vary by reply destination mode and Spring Integration version.

### Two message layers to distinguish

| Component | Data type | Responsibility |
|---|---|---|
| Request/reply inside integration flow | `org.springframework.messaging.Message<?>` | Payload and Spring Message headers, request/reply channels |
| Request/reply crossing the broker | `jakarta.jms.Message`, e.g., `TextMessage` | JMS body, standard JMS headers, and JMS properties |
| `JmsOutboundGateway` | Spring Integration gateway | Converts between the two message types and matches JMS replies to Spring requests |
| JMS broker/provider | Infrastructure | Destinations, message delivery, sessions, timeout/expiry, and durability per config |
| Warehouse system | Consumer/server | Reads requests, executes business logic, sends accurate replies |

Spring's `replyChannel` is not JMS's `JMSReplyTo`. `replyChannel` is where the **Spring Message** is returned inside the app; `JMSReplyTo` is the **JMS destination** where the server sends the JMS reply.

## 3. Choosing the right endpoint: adapter or gateway?

| Requirement | Recommended endpoint | Who initiates exchange? | Returns reply to Spring? |
|---|---|---|---|
| Send a one-way event to a queue | **JMS outbound channel adapter** | Spring Integration | No |
| Send a JMS request, wait for a JMS reply | **JMS outbound gateway** | Spring Integration | Yes |
| Receive an external JMS request and return a JMS reply | **JMS inbound gateway** | External JMS client | Gateway sends reply over JMS |
| Receive a JMS event when delivered by the broker | JMS message-driven inbound adapter | External JMS producer | No |
| Poll a JMS queue on a schedule | JMS polling inbound adapter | Spring Integration poller | No |

The `InventoryCheck` example is a short lookup with a clear reply, so an outbound gateway fits. If you need to send `OrderPaid` and let the warehouse system process asynchronously for several minutes, an outbound adapter + separate result event is usually more appropriate, because request-reply holds waiting resources during processing.

## 4. Building a JMS outbound gateway with Java DSL

The example uses Spring Integration 6+ and Jakarta JMS. Older Spring versions may use `javax.jms` and different detailed API names. You need a valid `ConnectionFactory` for the broker, a request queue, and a JMS consumer capable of sending replies.

### 4.1. Dependencies

In a Maven project using the Spring Boot BOM for version management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Add JMS starter/client for ActiveMQ Artemis, IBM MQ, or a specific JMS provider. -->
~~~

Configure the `ConnectionFactory` bean, address, credentials, and security settings per environment. The Java snippet below **does not create a broker** or queues on behalf of the JMS system.

### 4.2. Defining the request flow

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class InventoryJmsClientConfiguration {

    @Bean
    public IntegrationFlow inventoryJmsRequestFlow(
            ConnectionFactory connectionFactory) {

        return IntegrationFlow
                .from("inventoryJmsRequests")
                .handle(Jms.outboundGateway(connectionFactory)
                        .requestDestination("inventory.check.request"))
                .get();
    }
}
~~~

**Explanation:**

- `IntegrationFlow.from("inventoryJmsRequests")` creates or uses a channel as the entry point for requests from other Spring Integration components.
- `Jms.outboundGateway(connectionFactory)` creates the JMS-side request-reply endpoint. The gateway tracks pending requests to route replies back to the right Spring caller.
- `requestDestination("inventory.check.request")` specifies the external destination receiving requests. In this example, it is a queue.
- `.handle(...)` creates an endpoint capable of producing a reply for the flow; it differs from `Jms.outboundAdapter(...)`, which is a one-way sender.
- There is no `poller` in this configuration because requests are triggered when a caller invokes the gateway.

If the warehouse system has no JMS consumer or fails to send a valid reply, the flow cannot complete a normal request-reply exchange; the client will hit a timeout or error depending on configuration.

### 4.3. Creating a Spring messaging gateway for calling services

So business code can call an interface instead of manually building `Message<?>` and reading from a reply channel, use `@MessagingGateway`:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface InventoryQueryClient {

    @Gateway(
            requestChannel = "inventoryJmsRequests",
            replyTimeout = 8000)
    String checkInventory(String requestJson);
}
~~~

In the calling service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final InventoryQueryClient inventoryQueryClient;

    public CheckoutService(InventoryQueryClient inventoryQueryClient) {
        this.inventoryQueryClient = inventoryQueryClient;
    }

    public String checkOrderStock() {
        String requestJson = """
                {
                  "requestId": "req-501",
                  "schemaVersion": 1,
                  "operation": "checkStock",
                  "orderId": "ORD-501"
                }
                """;
        return inventoryQueryClient.checkInventory(requestJson);
    }
}
~~~

In Spring with Java 17+, the `"""` text block above is valid Java syntax. The messaging gateway interface gets a proxy when Spring Integration is enabled. The `checkInventory` method is declared to return `String` because the convention is that the warehouse system returns a JMS `TextMessage` and the converter produces a `String` Spring payload.

**Important note:** `replyTimeout = 8000` on `@Gateway` is the timeout while the **Spring messaging gateway waits for the Spring reply** (8 seconds). It does not replace every timeout of the JMS outbound gateway or downstream services. In a synchronous model, waiting at the JMS endpoint may already consume most of that time; configure timeouts on the JMS endpoint and client under the same SLA budget.

### 4.4. Sample JSON contract

Request `TextMessage`:

~~~json
{
  "requestId": "req-501",
  "schemaVersion": 1,
  "operation": "checkStock",
  "orderId": "ORD-501"
}
~~~

Reply `TextMessage`:

~~~json
{
  "requestId": "req-501",
  "schemaVersion": 1,
  "resultCode": "OK",
  "orderId": "ORD-501",
  "availability": "AVAILABLE",
  "availableQuantity": 6
}
~~~

`requestId` in the payload is a **business key** chosen by the client. It is not automatically JMS `JMSMessageID` or `JMSCorrelationID`. Matching replies to requests relies on JMS correlation per the two-way contract, while `requestId` aids tracing and idempotency.

### 4.5. Equivalent XML configuration

~~~xml
<int:channel id="inventoryJmsRequests"/>
<int:channel id="inventoryJmsReplies"/>

<int-jms:outbound-gateway
        id="inventoryJmsGateway"
        request-channel="inventoryJmsRequests"
        reply-channel="inventoryJmsReplies"
        connection-factory="jmsConnectionFactory"
        request-destination-name="inventory.check.request"/>
~~~

This is a Spring XML configuration snippet: you need `int`/`int-jms` namespace declarations, the `jmsConnectionFactory` bean, and a consumer for `inventoryJmsReplies`. In the Java DSL above, the `@MessagingGateway` interface creates a temporary reply channel per call, so you do not have to declare a fixed `inventoryJmsReplies` channel.

To bound reply wait time, set the timeout attribute supported by your Spring Integration version on the outbound gateway/JMS endpoint, then test against a server that does not reply. Do not infer that XML `reply-channel` is the name of the JMS reply queue.

## 5. `JMSReplyTo` and reply destination strategies

When sending a JMS request, the client must tell the server **where to send the reply**. JMS uses the `JMSReplyTo` header to hold this `Destination`.

### Temporary reply destination

In a simple setup, the outbound gateway can use a JMS **temporary queue** to receive replies. A temporary destination is bound to the JMS connection lifecycle; the server reads `JMSReplyTo` from the request and sends the reply there. This is convenient when requests are short, a caller can hold a connection, and the provider permits creating temporary destinations.

Advantage: no need to pre-manage a fixed reply queue for every client. Trade-off: creating/managing destinations has overhead depending on deployment mode; if the client closes the connection or times out and no listener remains, a **late reply may have nowhere to land**.

### Fixed reply destination

In enterprise environments, an app may want a fixed reply queue to configure ACLs, metrics, and operations. In that case, decide **how the gateway distinguishes replies for multiple pending requests**:

- Set `JMSCorrelationID` using a convention understood by both client and server.
- If using a shared reply queue, the reply consumer may need a selector or a reply listener with correlation-based dispatch, depending on Spring Integration version and gateway configuration.
- Plan for late replies, stale replies, unmatched messages, and reply queue depth.

Conceptual example declaring a fixed destination:

~~~java
// Replace the JMS endpoint configuration in section 4 if both sides agree on a reply queue.
Jms.outboundGateway(connectionFactory)
        .requestDestination("inventory.check.request")
        .replyDestination("inventory.check.reply")
~~~

Before deploying, check the methods on `JmsOutboundGatewaySpec` in your version, receive permissions on the reply destination, correlation filters, and reply listener options. **Simply setting a reply queue name without defining matching for concurrent requests is not enough**.

| Configuration | Suitable when | What to verify |
|---|---|---|
| Temporary reply queue | Short request-reply, client manages JMS connection | Permission to create temporary destinations and behavior on timeout/reconnect |
| Dedicated fixed reply queue per client | Infrastructure requires named queues and stable ACLs | Queue name, cleanup, send/receive permissions, per-request matching |
| Shared fixed reply queue | Many concurrent requests or shared across instances | Correlation, selector/listener, ordering, load, stale-reply handling |

If the receiver ignores `JMSReplyTo` and always sends to another queue, fix the contract or configure the gateway accordingly; do not expect the outbound gateway to find replies on a destination it is not monitoring.

## 6. Correlation: matching the right request with the right reply

Two requests sent close together can finish out of order. JMS supports standard headers:

| Header/ID | Who creates it, what is it for? | Example |
|---|---|---|
| `JMSMessageID` | Assigned by JMS provider per send; can serve as reply reference | `ID:request-501` |
| `JMSCorrelationID` | Client/server agreed value linking reply to request | `ID:request-501` or `corr-501` |
| `JMSReplyTo` | Destination where server should send JMS reply | Temp queue or `inventory.check.reply` |
| `requestId` in payload | Business key, typically used for audit, deduplication, and tracing | `req-501` |

### Pattern using JMSMessageID

~~~text
Client sends request:
  JMSMessageID     = ID:A   (assigned by broker/provider)
  JMSReplyTo       = temp-reply-A

Server sends reply:
  JMSCorrelationID = ID:A
  Destination      = temp-reply-A
~~~

### Pattern using client-supplied correlation ID

~~~text
Client sends request:
  JMSCorrelationID = corr-501
  JMSReplyTo       = shared.reply.queue

Server sends reply:
  JMSCorrelationID = corr-501
  Destination      = shared.reply.queue
~~~

Both patterns can appear in JMS integration. **Actual configuration must align between gateway and server**: do not assume which ID the server copies or which header the client filters on. What `JMSCorrelationID` carries, when it is set, and how the gateway maps it to Spring headers must be verified via integration tests with a real broker.

When multiple clients share one reply destination, never match replies by arrival order:

~~~mermaid
sequenceDiagram
    participant C as Spring JMS client
    participant B as Broker
    participant S as Inventory service
    C->>B: Request A (corr-A)
    C->>B: Request B (corr-B)
    B->>S: A and B
    S->>B: Reply B (corr-B) arrives first
    S->>B: Reply A (corr-A) arrives second
    B-->>C: Reply B: mapped to B
    B-->>C: Reply A: mapped to A
~~~

A reply with missing or wrong correlation may be ignored, left unmatched, or cause a timeout depending on implementation. Never "work around" this by dropping correlation and grabbing the first message off the queue.

### Header mapper and payload contract

`DefaultJmsHeaderMapper` transfers supported headers/properties between Spring Messages and JMS messages. Not every Spring header can become a JMS property: JMS properties only accept types allowed by the spec, while Spring headers can hold arbitrary objects. Prefer simple `String`, numeric, and boolean types for metadata needed by the server.

In the JSON example, `schemaVersion` and `requestId` should live in the payload so the contract does not depend solely on JMS headers. Do not use `JMSMessageID` as a substitute for `requestId` when deduplication is needed: resending the same command can produce a new JMS message ID.

## 7. Converting request and reply bodies

The outbound gateway performs **two-way conversion**: Spring request → JMS request, then JMS reply → Spring reply.

| Initial Spring payload | Common JMS body with default converter | Receiver must understand |
|---|---|---|
| `String` | `TextMessage` | JSON/XML/schema-defined string |
| `byte[]` | `BytesMessage` | Binary format, charset/encoding |
| `Map` with JMS-supported values | `MapMessage` | Keys/values and type rules |
| Java `Serializable` | `ObjectMessage` | Class compatibility and deserialization risks |

With the common `SimpleMessageConverter`, `String` typically becomes `TextMessage`. If the warehouse system only understands JSON, **serialize the domain object before calling the gateway** or configure an appropriate `MessageConverter`. Do not assume every Java record/DTO converts automatically to JSON.

Properties to distinguish during design:

- `extractRequestPayload` controls how the gateway creates JMS content from the Spring request; normally keep the default payload extraction.
- `extractReplyPayload` controls how the JMS reply is turned into a Spring payload; normally keep a business payload rather than forcing services to handle raw JMS objects.
- `MessageConverter` determines actual body mapping; `HeaderMapper` determines header/property mapping. The two mechanisms serve different purposes.

**Do not assume the reply has the same type as the request.** The server might return a `TextMessage` containing JSON, a `BytesMessage` containing Protobuf, or an invalid payload. If the Spring interface declares a `String` result while the converter returns `byte[]`, add a transformer or make the contract explicit.

### Validating the contract before sending

Example required request fields:

- `requestId` is a non-empty string, unique within business scope; reuse the exact same ID when retrying the same command.
- `schemaVersion` is an integer supported by both sides.
- `operation` belongs to an allowed command set such as `checkStock`.
- `orderId` matches expected format and length limits.

The reply should echo `requestId`, `resultCode`, and result fields. A business-error reply might be:

~~~json
{
  "requestId": "req-501",
  "schemaVersion": 1,
  "resultCode": "ORDER_NOT_FOUND",
  "message": "Order does not exist"
}
~~~

A **business-error reply** is a valid JMS reply whose `resultCode` is not `OK`. **Infrastructure errors** such as inability to connect to the broker, missing reply, or message parse failure are separate scenarios and must be handled via exceptions/timeouts.

## 8. Timeouts: distinguishing each wait point

In request-reply there are multiple independent deadlines. No single `timeout` parameter solves everything automatically.

| Location | What is it waiting for? | Risk |
|---|---|---|
| Spring `@Gateway(replyTimeout=...)` | Spring reply via message channel | Caller may wait too long or too short relative to the JMS layer |
| Outbound JMS gateway | JMS reply on configured destination | Timeout/no reply; in-flight resources remain occupied |
| JMS broker | Request or reply TTL/expiry | Message expires before service receives/responds |
| Inventory service | Internal warehouse DB/API completion | Slow service, growing queue of waiting requests |
| Network/provider | Send/receive or connection recovery | May be unknown whether broker already accepted the request |

Example: the Spring client sets an 8-second SLA, the warehouse may take 12 seconds, and the server still sends a reply. The client already timed out at second 8; the reply arriving afterward is a **late reply**. It may be discarded, expire, or linger on the reply queue depending on the receive mechanism. The caller might retry before the server finishes the first attempt, causing duplicate execution of the same command.

### Designing a timeout budget

For an assumed 8-second SLA, operational targets can be budgeted as:

~~~text
Total client SLA:                        8.0 seconds
  JMS delivery + queue wait:             1.0 second
  Warehouse/DB processing:               5.0 seconds
  Sending & receiving JMS reply:         1.0 second
  Network/scheduler headroom:            1.0 second
~~~

This is a **design target**, not a measured guarantee. During implementation, set JMS gateway receive/reply timeout, Spring gateway timeout, broker expiry, and downstream timeouts so they do not conflict; verify by measuring p95/p99 latency.

For processes taking minutes, consider an **asynchronous command + result event/status query** instead of synchronous request-reply. The caller receives a quick acknowledgement and queries status later, reducing how long requests stay blocked waiting for replies.

## 9. Transactions, retries, idempotency, and failure windows

Running request-reply over JMS does not mean both sides execute a **distributed transaction**. The outbound gateway may send the JMS request in a local JMS transaction; the server may receive/transact the request separately; the warehouse DB has its own transaction; and the reply may also be sent in its own transaction.

### Scenario: send succeeds but reply is lost

Suppose the server checked and *reserved inventory* for `ORD-501`, then the connection breaks while sending the reply. The client times out and resends:

~~~mermaid
flowchart TD
    A["Spring sends request req-501"] --> B["Warehouse receives request"]
    B --> C["DB commits reservation"]
    C --> D{"JMS reply reaches client?"}
    D -->|"Yes"| E["Client processes result"]
    D -->|"No, client timeout"| F["Client may retry req-501"]
    F --> G{"Has server processed req-501?"}
    G -->|"Yes"| H["Return stored result"]
    G -->|"No"| I["Execute business logic once"]
    I --> J["Store result keyed by req-501"]
    J --> H
~~~

If the client generates a new `requestId` for every retry of the same command, the server cannot easily detect the duplicate operation. For **state-changing** commands:

1. Assign a stable `requestId` for the logical action.
2. On the server side, use a unique constraint/idempotency store keyed by `requestId`.
3. In the same DB transaction, persist the business state and the processed request result.
4. When receiving an existing `requestId` again, return the stored result instead of executing side effects again.
5. Retain idempotency records long enough for retry/redelivery windows and business requirements.

For read-only queries, retries are usually safer but still need rate limits, timeouts, and backoff to avoid overloading a slow server.

### Other failure windows

| Scenario | What is actually known | How to handle |
|---|---|---|
| Serialization error before send | JMS request was not sent | Fix payload/schema; do not retry broken data endlessly |
| Broker refuses connection before send | Likely did not reach broker | Retry with backoff, circuit breaker, metrics |
| Connection drops right after send | Broker **may** have received it | Retries must be idempotent because send outcome is uncertain |
| Server commits DB but reply is lost | Operation may have succeeded | Re-query by `requestId` or perform idempotent retry |
| Client gets reply then crashes before saving state | Client may repeat the call | Persist state durably and deduplicate on the server |
| Reply has wrong correlation | Cannot match to request | Log/trace and fix contract; never accept an arbitrary reply |

**Local JMS transactions do not automatically coordinate commits with a DB.** If consistency between persisting data and emitting events is required, use outbox/inbox; if atomicity across multiple resources is needed, consider XA/distributed transactions only when genuinely supported by provider, broker, and infrastructure. Do not claim `exactly-once` based on a transaction flag.

### When the request originates from an inbound JMS flow

Architectural example:

~~~text
JMS inbound gateway receives request from ERP
    -> process / transform
    -> JMS outbound gateway queries inventory
    -> build reply for ERP
~~~

With handlers connected by `DirectChannel`, the request-reply chain can stay on a single listener thread. If the outbound gateway waits 8 seconds for inventory, the inbound listener may also tie up resources for that duration. Using `ExecutorChannel` or `QueueChannel` alters thread and transaction boundaries; errors on the outbound side may no longer roll back the upstream JMS receive. Design end-to-end timeouts and fallbacks when one system stops responding.

## 10. Error handling and returning meaningful results

At the outbound gateway, not every failure arrives as a JMS error reply:

- **Business error with reply:** the server returns JSON with a `resultCode` such as `NOT_FOUND` or `OUT_OF_STOCK`. The gateway receives it normally; the app inspects `resultCode` to decide next steps.
- **No reply:** the server did not send, the reply was lost, correlation mismatched, the reply queue was unusable, or the reply arrived late. Gateway/caller must handle the timeout.
- **Send/receive failure:** broker disconnected, missing permissions, wrong destination, converter or header mapper failure. The endpoint may throw `MessagingException`/wrapped provider exceptions.
- **Post-gateway processing error:** a downstream transformer or service fails on the reply; Spring Integration's error handling determines where it is reported.

In a synchronous flow, exceptions can usually propagate back to the Spring messaging gateway calling `InventoryQueryClient.checkInventory(...)`. However, exact exception wrapping and timeout return behavior depend on endpoint, timeout, and version. Never catch all exceptions and return `"AVAILABLE"` or `null` as though the request succeeded.

`errorChannel`/`ErrorMessage` are helpful for collecting errors from asynchronous endpoints. However, an error channel **does not automatically** retry requests, restore correlation, or send JMS replies. When adding retry advice, define explicitly which errors are safe to retry, attempt limits, backoff, and the possibility that the server already executed side effects.

### Application-layer result classification pattern

~~~text
InventoryQueryClient.checkInventory(requestJson)
  -> JMS reply "OK"              : read/update result normally
  -> JMS reply "OUT_OF_STOCK"    : business outcome, do not blindly retry
  -> JMS reply "INVALID_REQUEST" : contract error, fix payload
  -> timeout                     : unknown state; retry idempotently
  -> broker unavailable          : retry with backoff or return 503 to caller
  -> converter error             : route to data/configuration error tracking
~~~

Do not log raw payloads containing tokens or personal data; log `requestId`, correlation ID, JMS message ID, destination, processing duration, error type, and outcome.

## 11. Connection lifecycle, concurrency, and operations

The JMS outbound gateway uses `ConnectionFactory`, JMS sessions/producers, and reply-reception mechanisms managed by Spring Integration/JMS provider. When using a fixed reply destination with many concurrent requests, configure correlation and the reply listener appropriately for your Spring Integration version and broker capabilities.

What to monitor:

| Metric/status | Why it matters |
|---|---|
| Requests sent/sec | Detects traffic spikes |
| Valid replies/sec | Confirms the server is responding |
| In-flight requests waiting for replies | Detects resource exhaustion when the server slows down |
| Reply latency p50/p95/p99 | Compares against SLA and spots bottlenecks |
| Timeout rate | Indicates delayed, lost, or mis-correlated replies |
| Late/unmatched replies | Reveals contract, timeout budget, or retry bugs |
| JMS connection/reconnect errors | Detects broker or network instability |
| Request queue depth and oldest age | Shows server backlog buildup |
| Reply queue depth and expiry | Detects lingering, stale, or unconsumed replies |

Across multiple instances, account for total pending requests, connection pools, and access permissions on reply destinations. Each instance using temporary reply destinations provides natural isolation, though creating/managing many temporary destinations consumes broker resources. A shared reply queue reduces queue creation overhead but requires accurate routing, especially when multiple gateways/instances listen concurrently.

During application shutdown/restart, temporary queues and in-flight pending requests may not survive. Clients must handle failed calls, persist `requestId` for important commands, and safely re-query/retry after recovery. Never treat a live JVM process as proof that the JMS connection and reply consumer are healthy.

## 12. Hands-on exercise: querying inventory over JMS and receiving replies

**Environment:** a test JMS broker, `inventory.check.request` queue, a Spring Integration client using an outbound gateway, and a JMS server using an inbound gateway or custom listener. Deploy only **one** request-processing consumer per basic test so results are easy to correlate.

1. **Happy path:** server receives request JSON `req-501` and returns `AVAILABLE`; Spring `InventoryQueryClient` receives a `String` reply with matching `requestId` and `resultCode=OK`.
2. **Correlation:** send 20 requests with distinct `requestId` values and intentionally vary processing delays so replies return out of order. Record `JMSCorrelationID` and prove replies are never mismatched.
3. **No reply:** have the server consume the request without replying. Verify timeouts at both the JMS gateway and Spring caller; measure elapsed time.
4. **Late reply:** have the server reply after the caller times out. Observe orphan/expired replies, then retry the request with the same `requestId` and verify idempotency.
5. **Broker unavailable:** drop the broker connection before and after sending. Inspect exceptions, logs, reconnects, and whether retries could produce duplicates.
6. **Invalid schema:** send JSON missing `orderId` and have the server return `INVALID_REQUEST`; ensure the caller distinguishes business errors from timeouts.
7. **Fixed reply queue:** configure a fixed reply destination, set up correlation matching, run multiple concurrent callers, and verify no reply is misdelivered.
8. **Temporary reply queue:** confirm the provider permits temporary queue creation and inspect the reply destination's lifecycle when the client stops/restarts.
9. **State-mutating operation:** switch from `checkStock` to `reserveStock` and add an idempotency table keyed by `requestId`; drop the reply after DB commit, retry, and verify stock is not reserved twice.
10. **Load and observability:** raise concurrency, collect p95 latency, timeout rate, request queue depth, and in-flight count; decide whether long tasks should move to an async pattern.

### Contract verification checklist

| Expectation | How to prove |
|---|---|
| Client sends to the right JMS request destination | Inspect request metadata at broker/server |
| Server knows where to send reply | Inspect `JMSReplyTo` on the request |
| Reply matches the right call | Inspect `JMSCorrelationID`/correlation per contract |
| Converted body has expected type | Client receives JSON `String`, validates schema/version |
| Timeouts are handled intentionally | Server omits reply and client exits within budget |
| No double side effects on retry | Unique `requestId` in server DB and verify row counts |
| Restarts do not misinterpret outcomes | Retry/re-query using durable request ID |

Tests covering correlation, JMS transactions, reply destinations, late replies, and recovery require a **real broker/JMS provider** or equivalent test container. Mocking `JmsTemplate` or `MessageChannel` cannot prove those behaviors.

### Self-check questions

1. Why can an outbound channel adapter not replace an outbound gateway when the caller needs inventory status back?
2. Distinguish Spring `replyChannel` from `JMSReplyTo` in a request-reply flow.
3. How do `JMSMessageID`, `JMSCorrelationID`, and `requestId` differ?
4. When the server sends reply B before reply A, how does the client route results back to the right calls?
5. Why should `@Gateway(replyTimeout=8000)` not be treated as the sole deadline setting across the whole JMS flow?
6. What happens if the client times out after the server already committed a stock reservation and the reply was lost?
7. Why does using a shared fixed reply queue require stricter correlation design?
8. When should you switch from JMS request-reply to asynchronous command + result event?

## 13. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): outbound gateway, request/reply, correlation, reply destinations, and JMS settings.
- [Spring Integration API — JmsOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundGatewaySpec.html): Java DSL configuration for the outbound gateway.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): `@MessagingGateway`, Spring request/reply channels, and timeouts.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): `JmsTemplate`, `MessageConverter`, and JMS transactions.

**Remember:** a JMS outbound gateway enables a Spring Integration flow to send a request to a broker and return the reply to the right Spring caller. Request-reply quality depends not only on a successful JMS send, but also on **reply destinations, correlation, payload contracts, aligned timeouts, transaction boundaries, error handling, and retry idempotency**.

# Temporary reply destinations in JMS

## 1. Problem: receiving replies without pre-provisioning a reply queue

A sales application wants to check inventory before confirming order `ORD-1101`. The warehouse service only exposes JMS: it receives requests on the `inventory.check.requests` queue and returns results via JMS messages. The sales app must know **where replies are sent**, **which request a reply belongs to**, and **how long to wait at most**.

A simple approach is creating a **temporary reply destination**. The caller creates a temporary JMS destination, places it into the request's `JMSReplyTo` header, waits for a reply on that temporary destination, and releases resources upon completion. There is no need to pre-create a shared reply queue for every client.

In the **SPRING_INTEGRATION_ADAPTERS** module, outbound adapters, inbound adapters, gateways, pollers, and `MessageChannel`s connect external systems to Spring Integration flows. In JMS, a temporary reply destination is a foundational mechanism for the **request-reply gateway**, directly tied to payload/header contracts, timeout handling, errors, connection management, and consumer lifecycle. Unlike files, SFTP, HTTP, AMQP, Kafka, or databases, JMS has the `JMSReplyTo` concept pointing directly to a client-supplied `Destination` object.

**After this lesson, you should be able to:**

1. Explain `TemporaryQueue`/`TemporaryTopic`, ownership scope per JMS `Connection`, and consumer restrictions.
2. Distinguish a request queue, temporary reply queue, fixed reply queue, and Spring `replyChannel`.
3. Configure `JmsTemplate.sendAndReceive(...)` and Spring Integration `Jms.outboundGateway(...)` with temporary destinations.
4. Compare **one temporary destination per request** vs. **a reply listener sharing one temporary destination per gateway**.
5. Explain correlation IDs, timeouts, late replies, broker reconnects, retry/idempotency, and consumer-caching pitfalls.
6. Verify behavior against a real JMS broker rather than inferring from mock services.

## 2. What are `TemporaryQueue`, `TemporaryTopic`, and `JMSReplyTo`?

JMS defines `jakarta.jms.Destination`; `Queue` and `Topic` are the two common destination types. Jakarta Messaging also defines:

- `jakarta.jms.TemporaryQueue`: a queue generated specifically for a JMS connection, commonly used as a reply address.
- `jakarta.jms.TemporaryTopic`: a temporary topic with similar connection scope, used only when the provider and reply protocol truly require it.
- `Message.getJMSReplyTo()` / `Message.setJMSReplyTo(Destination)`: the JMS header telling the server which destination **the client wants to receive replies on**.

### Standard Jakarta Messaging lifecycle rules

| Attribute | Rule |
|---|---|
| Who creates it? | A JMS `Session` or `JMSContext` creates a temporary destination on the JMS provider |
| Who may **receive** from it? | Only consumers belonging to **the same connection that created** the temporary destination may receive |
| Who may **send** to it? | Producers on other connections can send to the temporary destination given its reference and appropriate broker permissions |
| How long does it exist? | Scoped to the **owning connection**, or until explicitly deleted |
| When the connection closes? | The temporary destination ceases to exist; pending contents may be lost |
| Is it a durable queue surviving restarts? | **No**; never rely on temporary destinations to preserve replies across connection loss |
| Does each `Session` get its own private reply queue? | Not necessarily; the creating session is only the API entry point—**ownership scope is the connection** |

A temporary destination is not a preconfigured queue name in the system. The broker typically generates a unique internal identifier whose format is provider-specific. Never hard-code or persist an observed temporary queue name as configuration for future startups.

**Common misconception:** only the owning connection may create a consumer receiving from the temporary destination; **the server can still send the reply from a different connection**. If both sides had to share the same connection, request-reply between two services could never work; JMS imposes no such requirement.

### Request queue and reply destination are two distinct targets

| Component | Example | Who uses it? | Purpose |
|---|---|---|---|
| JMS request destination | `inventory.check.requests` | Client sends, server receives | Delivers a request to a processing consumer |
| Temporary reply destination | Broker-created `TemporaryQueue` | Server sends, owning client connection receives | Returns the result to the waiting client |
| Fixed reply destination | `inventory.check.replies` | Administered and accessed by authorized clients | Replaces temporary replies when a fixed address is required |
| Spring `replyChannel` | `inventoryResponses` or temporary reply channel | Internal to Spring Integration | Returns a **Spring Message**, not a JMS message |

`JMSReplyTo` is a **JMS header**, whereas `replyChannel` is a **Spring Message header/channel**. A JMS outbound gateway bridges these two worlds; they are not interchangeable.

## 3. Request-reply lifecycle with a temporary queue

~~~mermaid
sequenceDiagram
    participant App as Spring caller
    participant Gateway as JMS outbound gateway
    participant Broker as JMS broker
    participant Server as Inventory service

    App->>Gateway: Spring request (req-1101)
    Gateway->>Broker: Create TemporaryQueue on client connection
    Gateway->>Broker: Send JMS request to inventory.check.requests
    Note over Gateway,Broker: JMSReplyTo points to TemporaryQueue
    Broker->>Server: Deliver request
    Server->>Server: Validate and process
    Server->>Broker: JMS reply to request.JMSReplyTo
    Broker-->>Gateway: Reply on TemporaryQueue
    Gateway-->>App: Spring reply
    Gateway->>Broker: Release temporary destination per gateway mode
~~~

Logical sequence:

1. Caller sends a Spring Message to the outbound gateway or invokes a Spring messaging gateway interface.
2. Gateway selects the request queue and prepares a temporary reply destination, attaching it to `JMSReplyTo` when sending the request.
3. The warehouse system receives the request, reads `JMSReplyTo`, constructs a JMS reply, and sends it **to that exact supplied destination**.
4. Gateway receives the reply, maps JMS body/headers to a Spring Message, matches it to the waiting call, and forwards it to the Spring reply channel.
5. The reply consumer and temporary destination are closed/deleted according to the **gateway's receive mode**, not necessarily at the same time as closing the entire connection.

### Distinguishing three identifiers

- `JMSMessageID`: ID assigned by the provider to **each JMS message send**.
- `JMSCorrelationID`: ID agreed upon by client/server to link a reply to a request in the JMS protocol.
- `requestId`: **business** key inside the JSON payload, which must stay stable when retrying the same command.

With a **dedicated temporary queue per request**, the queue itself isolates that request's reply; a selector on `JMSCorrelationID` is not strictly required to find the reply. Still, the server **should follow an explicit correlation contract**, such as setting the reply's `JMSCorrelationID` to the request's `JMSMessageID`. Especially when switching to a fixed reply queue, correlation becomes mandatory to avoid mismatches.

### Illustrative JSON contract

Request:

~~~json
{
  "requestId": "req-1101",
  "schemaVersion": 1,
  "operation": "checkStock",
  "orderId": "ORD-1101"
}
~~~

Reply:

~~~json
{
  "requestId": "req-1101",
  "schemaVersion": 1,
  "resultCode": "OK",
  "orderId": "ORD-1101",
  "availability": "AVAILABLE"
}
~~~

This is strictly the business contract. `requestId` in JSON does not automatically turn into `JMSCorrelationID`. JMS headers are set by the gateway/provider per configuration, while payloads must be validated independently on each side.

## 4. Example with `JmsTemplate.sendAndReceive(...)`

Spring Framework provides a simple JMS request-reply mechanism via `JmsTemplate.sendAndReceive(...)`. This method **creates a temporary queue as part of each operation**, sets it as the request's `JMSReplyTo`, sends the request, and waits for the JMS reply on the newly created queue.

With Spring Framework 6+ and Jakarta JMS:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

public class InventoryJmsClient {
    private final JmsTemplate template;

    public InventoryJmsClient(JmsTemplate template) {
        this.template = template;
    }

    public String checkStock(String requestJson) throws JMSException {
        // Configure this on the bean at startup; do not mutate at runtime across threads.
        Message reply = template.sendAndReceive(
                "inventory.check.requests",
                session -> session.createTextMessage(requestJson));

        if (reply == null) {
            throw new IllegalStateException("No reply received before timeout");
        }
        if (!(reply instanceof TextMessage textReply)) {
            throw new IllegalStateException("Reply is not a TextMessage");
        }
        return textReply.getText();
    }
}
~~~

To configure the wait timeout on the bean:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@Bean("inventoryJmsTemplate")
public JmsTemplate inventoryJmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setReceiveTimeout(5000); // Wait up to 5 seconds for a reply.
    return template;
}
~~~

These snippets assume a `ConnectionFactory` bean pointing to the JMS broker and a request queue with proper permissions. `JmsTemplate` is a reusable bean once configured; **never call `setReceiveTimeout(...)` back and forth across concurrent threads**.

**Distinction:** `JmsTemplate.sendAndReceive(...)` is a **Spring JMS** API. It does not create an `IntegrationFlow`, `MessageChannel`, or Spring Integration gateway. When an app already builds flows with transformers, routers, filters, and error channels, usually prefer **JMS outbound gateway**; `sendAndReceive` is useful for understanding the mechanism or writing a small JMS client.

### Server handling `JMSReplyTo`

For a custom-implemented JMS server, the core reply-sending code looks like:

~~~java
// Fragment inside a JMS server callback with "request" and "session" available.
jakarta.jms.Destination replyTo = request.getJMSReplyTo();
if (replyTo == null) {
    throw new jakarta.jms.JMSException("Request is missing JMSReplyTo");
}

jakarta.jms.TextMessage response =
        session.createTextMessage(resultJson);
response.setJMSCorrelationID(request.getJMSMessageID());

jakarta.jms.MessageProducer producer = session.createProducer(replyTo);
try {
    producer.send(response);
} finally {
    producer.close();
}
~~~

`resultJson` is the JSON string built and validated by the business service. The fragment illustrates the server's responsibility; in production, inspect how the listener container supplies `Session` and manages transactions so you do not interfere with session lifecycle at the wrong time.

**Classic mistake:** the server always sends replies to a fixed `inventory.check.replies` queue even when requests carry a temporary `JMSReplyTo`. Clients creating temporary queues will wait forever on their temporary queues; both sides may log "send succeeded" while replies never reach the right destination.

## 5. Spring Integration Java DSL: temporary reply by default

Spring Integration provides `Jms.outboundGateway(connectionFactory)`. When `replyDestination(...)` is omitted, **the outbound gateway uses a temporary reply destination**, defaulting to `TemporaryQueue`.

### 5.1. Client-side flow

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class InventoryClientConfiguration {

    @Bean
    public IntegrationFlow inventoryRequestFlow(
            ConnectionFactory connectionFactory) {

        return IntegrationFlow
                .from("inventoryRequestChannel")
                .handle(Jms.outboundGateway(connectionFactory)
                        .requestDestination("inventory.check.requests")
                        .receiveTimeout(5000))
                .get();
    }
}
~~~

Omitting `replyDestination(...)` is an **intentional choice**, not a missing setting. The gateway uses a temporary JMS reply destination and feeds results into Spring Integration's reply path. `receiveTimeout(5000)` sets how long the JMS outbound gateway waits for a reply in milliseconds.

### 5.2. Business interface invoking the gateway

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface InventoryQueryPort {

    @Gateway(
            requestChannel = "inventoryRequestChannel",
            replyTimeout = 7000)
    String checkStock(String requestJson);
}
~~~

`@IntegrationComponentScan` in section 5.1 discovers `@MessagingGateway` interfaces. Services call `inventoryQueryPort.checkStock(json)` without knowing about JMS `Session` or `TemporaryQueue`.

**Two timeout layers:** `receiveTimeout(5000)` on the JMS gateway is the wait time for the JMS reply; `@Gateway(replyTimeout=7000)` on the Spring messaging gateway is the wait time for the Spring reply. Do not set both values arbitrarily equal and assume they are a single timer.

### 5.3. Spring Integration server using a JMS inbound gateway

In a **separate server application**, you can use an inbound gateway:

~~~java
@Bean
public IntegrationFlow inventoryServerFlow(
        ConnectionFactory connectionFactory,
        InventoryStockService inventoryStockService) {

    return IntegrationFlow
            .from(Jms.inboundGateway(connectionFactory)
                    .requestDestination("inventory.check.requests"))
            .handle(String.class, (requestJson, headers) ->
                    inventoryStockService.createReplyJson(requestJson))
            .get();
}
~~~

`InventoryStockService` is an app-implemented interface/service with `String createReplyJson(String requestJson)`. It parses/validates the request and returns a JSON `String`. The JMS inbound gateway uses `JMSReplyTo` from the request to send the JMS reply if contract and infrastructure allow; there is no need to hard-code a client-named temporary reply queue.

The client and server flows represent **two distinct applications or roles**. Do not deploy both inside one app and mistake that for a real architectural requirement; they are shown side-by-side to illustrate the path.

## 6. Two temporary reply queue modes in outbound gateway

**Spring Integration's outbound gateway has two major ways to receive replies.** Which mode you choose directly impacts how many temporary destinations/consumers are created, how correlation works, and operational overhead.

### 6.1. Without a reply listener: one temporary queue per request

This is the default behavior when neither a reply listener nor a reply destination is configured:

~~~text
Request A -> TemporaryQueue A -> Reply A -> delete TemporaryQueue A
Request B -> TemporaryQueue B -> Reply B -> delete TemporaryQueue B
Request C -> TemporaryQueue C -> Reply C -> delete TemporaryQueue C
~~~

According to Spring Integration documentation, a `TemporaryQueue` is created for **each request** and deleted when the request finishes, whether it succeeds, times out, or errors. Each reply receive uses a consumer bound to that request's reply destination. Because each request gets its own destination, no shared JMS selector is needed to separate replies A and B.

**Advantages:** simple reply isolation; no pre-configured physical reply queue or shared listener needed.

**Limitations:** continuously creating/deleting temporary destinations and consumers can consume substantial broker/provider resources at high throughput. If many requests arrive every second, measure active destination/consumer counts and setup overhead rather than assuming this mode is free.

### 6.2. With a reply listener: one temporary queue per gateway

Since Spring Integration 2.2, an outbound gateway can use a **dedicated reply `MessageListenerContainer`** instead of creating a new consumer for every reply. When `replyDestination` is not configured, the reply listener uses **one temporary queue per gateway instance**; the gateway recreates the temporary queue when recovering from connection loss.

~~~mermaid
flowchart LR
    subgraph G["One JMS outbound gateway instance"]
        A["Request A"]
        B["Request B"]
        C["Request C"]
        Map["Pending requests / correlation table"]
        Listener["Reply listener container"]
    end
    A --> R[("inventory.check.requests")]
    B --> R
    C --> R
    R --> S["Inventory service"]
    S --> T[("One gateway TemporaryQueue")]
    T --> Listener
    Listener --> Map
    Map --> A
    Map --> B
    Map --> C
~~~

Each request still carries `JMSReplyTo` pointing to **the gateway's single temporary queue**. The gateway uses request/message ID information to route each reply back to the right waiting caller. The server must uphold the correlation contract; a common convention is setting reply `JMSCorrelationID` to request `JMSMessageID`. In this temporary reply listener mode, **no custom `correlationKey` needs to be configured** unlike a shared fixed reply queue.

**Advantages:** eliminates per-request temporary destination and reply consumer creation/deletion; well suited when a gateway handles high concurrency or throughput.

**Limitations:** the reply listener/connection runs for the gateway's lifecycle; monitor in-flight request counts, listener health, timeouts, and connection drops. Multiple gateway beans still create multiple temporary queues rather than a single queue shared across the entire application or cluster.

### 6.3. Java DSL: enabling the reply container

Replace the outbound gateway config in section 5 with:

~~~java
@Bean
public IntegrationFlow inventoryRequestWithReplyListener(
        ConnectionFactory connectionFactory) {

    return IntegrationFlow
            .from("inventoryRequestsWithListener")
            .handle(Jms.outboundGateway(connectionFactory)
                    .requestDestination("inventory.check.requests")
                    .receiveTimeout(5000)
                    .replyContainer())
            .get();
}
~~~

`.replyContainer()` configures a default reply listener. To customize the listener (Java DSL 6.x+), use:

~~~java
.handle(Jms.outboundGateway(connectionFactory)
        .requestDestination("inventory.check.requests")
        .receiveTimeout(5000)
        .replyContainer(listener ->
                listener.concurrentConsumers(1)
                        .recoveryInterval(5000L)))
~~~

This is a fragment inside an `IntegrationFlow`, not a standalone Java method. Typically a single reply listener consumer can dispatch many fast replies because its main job is routing results to waiting requests; only raise concurrency after load testing.

**Do not register both flows from sections 5 and 6 on the same request channel and expect only one request to be sent.** They are **alternative configurations** for comparison. If running both in one app for A/B testing, give them distinct channel names and route callers intentionally.

### 6.4. XML namespace with reply listener

~~~xml
<int:channel id="inventoryRequests"/>
<int:channel id="inventoryResults"/>

<int-jms:outbound-gateway
        id="inventoryOutboundGateway"
        connection-factory="jmsConnectionFactory"
        request-destination-name="inventory.check.requests"
        request-channel="inventoryRequests"
        reply-channel="inventoryResults"
        receive-timeout="5000">
    <int-jms:reply-listener
            concurrent-consumers="1"/>
</int-jms:outbound-gateway>
~~~

This is an **XML fragment** requiring `int`, `int-jms` namespaces, the `jmsConnectionFactory` bean, and a consumer on `inventoryResults`. With no `reply-destination-name`, the reply listener uses a gateway-created temporary destination. If using the Java DSL above, do not register an additional XML gateway for the same purpose unintentionally.

### 6.5. Comparison table

| Criterion | Temporary queue per request | Temporary queue with reply listener |
|---|---|---|
| Spring Integration config | No `replyDestination`, no reply listener | No `replyDestination`, **has `replyContainer()`** |
| Number of temporary queues | One queue per pending request | One queue per active gateway |
| Reply consumer | Bound per request | Shared reply-receiving container |
| Correlation | Dedicated destination isolates reply | Gateway dispatches reply to matching request |
| On connection loss | Existing temporary queues become invalid | Listener/container recovers and creates a new temporary queue as needed |
| High load | Frequent destination and consumer churn | Reduces churn, still must monitor in-flight requests |
| Reply scope | Current pending call; no durable recovery | Pending calls of one gateway; not persisted across restarts |

## 7. Fixed reply queue: when not to use a temporary destination?

Some JMS providers or enterprise environments require:

- Pre-provisioned destinations governed by ACLs/JNDI.
- Clients lacking permission to create temporary destinations.
- Dedicated monitoring/analytics on a long-lived reply queue.
- Gateway and receiver needing a **fixed reply queue** due to cross-broker routing constraints.

In those cases, replace the temporary queue with `replyDestination("inventory.check.replies")` or an equivalent `Destination` bean. Because **a fixed reply queue can serve multiple requests and multiple gateways**, correlation must be configured accurately.

### 7.1. Example fixed reply queue with reply listener and correlation key

~~~java
.handle(Jms.outboundGateway(connectionFactory)
        .requestDestination("inventory.check.requests")
        .replyDestination("inventory.check.replies")
        .correlationKey("JMSCorrelationID")
        .receiveTimeout(5000)
        .replyContainer())
~~~

This is a Java DSL fragment. `correlationKey("JMSCorrelationID")` lets the gateway generate and use a correlation ID that the server must echo on the JMS reply. With a reply listener, Spring Integration uses a per-gateway-instance selector/correlation mechanism when configured properly.

**Warning:** configuring a **fixed reply destination + reply listener without a correlation key** is not valid for a reply listener sharing a queue. Spring Integration may log a warning and fall back to creating per-request consumers/selectors, causing performance and caching risks. Never simply add `.replyContainer()` to a fixed reply queue while ignoring the correlation contract.

### 7.2. Risk of `CachingConnectionFactory.cacheConsumers=true`

With a **fixed reply queue** and no reply listener, the gateway often creates a consumer with a **per-request selector** based on `JMSCorrelationID` or message ID. If `CachingConnectionFactory` caches consumers, each distinct selector can leave an unused consumer in the cache, growing memory/resource usage.

Therefore, when using a fixed reply queue:

1. Prefer a reply listener with a properly configured and tested correlation key.
2. If using per-request consumers, avoid `cacheConsumers=true` on the connection factory used by the gateway.
3. Measure consumer/session counts, broker connections, and heap under load testing, especially after tens of thousands of requests.

| Reply reception mode | Destination | Correlation | Operational consequence |
|---|---|---|---|
| Temporary per request | Broker-generated per request | No shared selector needed; still echo standard JMS correlation | Continuous destination creation/deletion |
| Temporary shared per gateway | Broker-generated for one gateway with reply listener | Gateway matches messages to waiting calls | Shared listener; connection loss requires recreation |
| Fixed queue, per-request consumer | Pre-provisioned queue | Selector by request ID | Watch out for consumer caching |
| Fixed queue, reply listener | Pre-provisioned queue | **Correlation key must be configured properly** | Can share queue across gateways; test selectors |

### 7.3. Why not switch arbitrarily to a Topic?

With a fixed reply queue, a reply is typically meant for **one client/request**. Using a topic risks lost or duplicated replies if a subscriber is not ready at publish time, uses a non-durable subscription, or competes across subscriptions. Spring Integration advises against topics for certain fixed-reply strategies without a reply listener.

**Default to queues for replies** unless topic semantics and provider support have been thoroughly verified for your protocol.

## 8. `TemporaryTopic` in Spring Integration 6+

Since **Spring Integration 6.0**, when an outbound gateway has no fixed reply destination and is configured with `replyPubSubDomain(true)`, it uses **`TemporaryTopic` instead of `TemporaryQueue`**.

~~~java
.handle(Jms.outboundGateway(connectionFactory)
        .requestDestination("inventory.check.requests")
        .replyPubSubDomain(true)
        .receiveTimeout(5000))
~~~

The DSL snippet above is a **custom option**, not the default recommendation. The request destination remains a queue unless `requestPubSubDomain(true)` is also configured; `replyPubSubDomain` affects only the reply domain.

Points to evaluate:

- A temporary topic is also scoped to the JMS connection lifecycle; only the owning connection may create consumers on it.
- A temporary topic is **not a durable topic subscription** for offline clients. When the connection closes, the destination disappears.
- Some JMS providers handle temporary queues and temporary topics differently; test creation, ACLs, reconnect, and resource cleanup.
- For typical request-reply, `TemporaryQueue` is easier to understand and more common. Do not enable `replyPubSubDomain(true)` simply assuming topics are always faster.

## 9. Correlation: dedicated destinations do not eliminate the need for clear contracts

### 9.1. Correlation pattern based on `JMSMessageID`

~~~text
Client sends request:
    JMSMessageID      = ID:request-1101
    JMSReplyTo        = TemporaryQueue:client-xyz
    payload.requestId = req-1101

Server sends reply:
    JMSCorrelationID  = ID:request-1101
    Destination       = TemporaryQueue:client-xyz
    payload.requestId = req-1101
~~~

This is a **common contract pattern**: the server copies `request.getJMSMessageID()` into `reply.setJMSCorrelationID(...)`. The gateway can use correlation to dispatch replies in shared-destination modes; per-request temporary destinations additionally isolate by address.

### 9.2. Client-supplied correlation pattern

In a system using a fixed reply queue, the client may generate `JMSCorrelationID` and require the server to **echo that exact value**:

~~~text
Client: JMSCorrelationID=corr-1101; JMSReplyTo=inventory.check.replies
Server: JMSCorrelationID=corr-1101; sent to inventory.check.replies
~~~

Both contract styles are not the same gateway mode. If the server always echoes `JMSMessageID` while the client uses a selector waiting for `JMSCorrelationID=corr-1101`, the client will time out even though the reply reached the queue. Align and test both sides.

### 9.3. Business request ID does not replace JMS correlation

`requestId` identifies a **business action**. A request may be resent with a new JMS message ID after a timeout, yet **should keep the same `requestId`** so the server detects duplicates. With per-request temporary queues, JMS correlation is not an idempotency mechanism. With a shared fixed reply queue, `requestId` in JSON also does not replace a selector on JMS metadata unless explicit routing is defined.

## 10. Timeouts and late replies: what happens when the server is too slow?

Suppose the client waits at most 5 seconds while the server takes 8 seconds:

~~~mermaid
sequenceDiagram
    participant Client as Client gateway
    participant Broker as Broker
    participant Server as Inventory service
    Client->>Broker: Request req-1101 / JMSReplyTo=temp-1
    Broker->>Server: Deliver request
    Note over Client: 5-second receiveTimeout expires
    Client-->>Client: Timeout / release wait
    Note over Broker: Per-request temp queue may already be deleted
    Server->>Broker: Reply req-1101 after 8 seconds
    Broker-->>Server: May reject/discard reply if destination expired
~~~

With **one temporary queue per request**, Spring Integration deletes the temporary queue when the request ends, including on timeout. When the server sends a late reply, the provider may report that the destination no longer exists or stop accepting replies; there is no general mechanism to "retroactively deliver" a reply to an expired request.

With a **temporary queue and a reply listener**, the queue may remain alive because other requests use the gateway, yet the `req-1101` call has already timed out. The gateway must handle late/unmatched replies safely; **never assume a late reply gets routed to a subsequent request**.

### Timeouts that cannot replace each other

| Timeout/TTL | Where does it live? | What it controls |
|---|---|---|
| `JmsTemplate.receiveTimeout` | Spring JMS client | Maximum wait per `sendAndReceive` call for a reply |
| `JmsOutboundGateway.receiveTimeout` | Spring Integration outbound JMS gateway | Deadline for receiving the JMS reply |
| `@Gateway(replyTimeout=...)` | Spring messaging gateway interface | Wait time for the Spring reply over message channels |
| Downstream DB/API timeout | Service receiving JMS request | Business processing duration |
| JMS `timeToLive` | Message sent through broker | Validity period of the JMS message before expiry |
| Reply-listener idle timeout | Spring Integration reply listener | When an idle listener stops; not a per-request deadline |

**TTL is not a receive timeout.** A request expiring on the broker does not automatically notify the client with a JMS reply; the client still needs timeouts and handling for uncertain outcomes.

### Retrying after a timeout

The request's state **may be unknown**: a timeout does not prove the server failed to commit business changes. If `checkStock` is read-only, bounded retries are relatively safe. When switching to `reserveStock` or `chargePayment`, the client must resend **the same `requestId`** so the server detects duplicates.

The server should maintain an idempotency table with a unique constraint on `requestId` and store the result in the same transaction as the business update. When the same ID arrives again, return the stored result instead of executing side effects a second time. `JMSMessageID` is insufficient because each retry can generate a new message ID.

## 11. Connection lifecycle, reconnect, transactions, and caching

A temporary destination belongs to a **JMS connection**, not to the logic of an order or a Spring call. This leads to three distinct operational scenarios:

1. **A request completes:** in temporary-per-request mode, the gateway deletes the request's temporary queue; the shared connection may stay open.
2. **A gateway stops or the app restarts:** the reply listener and gateway-managed temporary destinations are released per lifecycle. In-flight requests cannot be resumed simply by reusing an old temporary queue name.
3. **The JMS connection drops:** temporary destinations tied to the old connection become invalid. Infrastructure can reconnect and recreate consumers/temporary destinations, yet **replies for requests waiting at the time of failure may be lost**.

### 11.1. Reconnecting does not resume an old exchange

`CachingConnectionFactory`, the JMS provider, or a listener container can recover a connection; that **does not automatically restore lost JMS replies**. If the receiver already committed business work, the client will still see a timeout and must query status or retry using the business request ID.

Never store a `TemporaryQueue` reference in a database to reuse after a restart. A reference created by an old connection is no longer a valid reply channel for a new connection.

### 11.2. Consumer caching and broker resources

With per-request temporary queues, monitor the creation/deletion rate of temporary destinations and consumers; with a shared reply listener, monitor listener tasks and in-flight requests. A `CachingConnectionFactory` can reduce JMS session creation overhead on some `JmsTemplate` paths, but:

- Never assume every JMS consumer type is safe to cache.
- **Specifically avoid caching per-request selector consumers on a fixed reply queue**, because obsolete consumers can accumulate.
- Monitor connection/session/consumer counts on the broker and producer heap; multiple Spring beans/gateways across replicas multiply total resource demand.
- Test broker restarts and failover for your specific JMS provider, as recovery behavior can differ between temporary queues and fixed reply queues.

### 11.3. Transactions: do not wait for a reply before the request is committed/visible

A classic design mistake:

~~~text
BEGIN JMS transaction on client
  -> send request (uncommitted)
  -> wait for reply inside the same transaction
  -> server cannot yet see the uncommitted request
  -> client times out
~~~

When using a **JMS transaction for sending**, the broker may only make the request visible to other consumers **after commit**. If the client holds an uncommitted transaction while synchronously waiting for a reply, the flow can deadlock or time out. Clarify request-send transaction boundaries and how the gateway sends/receives; never blindly wrap the whole request-reply in an outer JMS transaction just to make it "atomic".

On the server side, a **JMS inbound gateway** can receive a request inside a JMS transaction and send the reply before committing, depending on listener settings. A JMS transaction can protect the related JMS operations, but does not automatically commit a database. If the server committed the DB and the reply failed to reach the client, retries still require idempotency.

### 11.4. Failure modes table

| Failure point | Possible state | Resolution |
|---|---|---|
| No permission to create temporary queue | Client fails before sending/waiting for reply | Check broker ACLs, connection roles, and gateway config |
| Server lacks permission to **send** to temp destination | Server processes but cannot send reply | Grant appropriate permissions; verify provider policy |
| Client closes connection while request is running | Temporary queue becomes invalid | Caller sees error/timeout; use `requestId` for status check/retry |
| Broker failover between request and reply | Old connection/destination may be lost | Test reconnect, in-flight metrics, and idempotent retry |
| Server ignores `JMSReplyTo` | Reply goes to the wrong destination | Fix JMS contract or configure gateway/fixed reply properly |
| Reply body fails conversion | JMS reply arrives but Spring handler gets no valid data | Align schema, converter, and error flow |
| Correlation ID mismatch | Reply cannot match the right caller | Log request/reply headers and fix correlation echo rules |
| `replyContainer()` uses fixed reply without key | Gateway warns/falls back to per-request consumers | Configure `correlationKey` or change strategy |
| Request times out while server continues | Late reply and possible committed side effect | Query status by `requestId`, retry safely |

## 12. Security and permissions for temporary destinations

Just because a temporary destination is broker-generated **does not mean permissions are unnecessary**. An application may need distinct permissions to:

- **Create temporary destinations** on the client's connection.
- **Consume** replies from the destination owned by that connection.
- **Send** requests to the fixed queue `inventory.check.requests`.
- **Send** replies from the server's connection to the client-supplied temporary destination.

JMS allows producers on other connections to send to a temporary destination, yet providers/brokers still enforce authentication, authorization, and resource quotas. Verify real ACLs rather than assuming every producer can send to every temporary destination.

### Controlling `JMSReplyTo` on the server side

`JMSReplyTo` is message data supplied by the client. If a server accepts requests from untrusted sources, enforce broker permissions and application policies to avoid becoming an **open relay sending replies to arbitrary destinations**. Limit sensitive data in replies, validate payloads, and ensure only authorized clients can invoke operations.

**Never do these two things in production:**

- Log raw credentials, tokens, PII, or serialized bodies containing sensitive data just to debug lost replies.
- Use an unvalidated destination name passed freely by an HTTP client as `JMSReplyTo`/reply queue without authorization and validation.

In multi-tenant brokers, verify temporary destinations against each provider's ACL model, namespaces, quotas, connection limits, and monitoring.

## 13. Choosing temporary reply vs. fixed reply?

| Architectural requirement | Typical fit | Things to watch |
|---|---|---|
| Short request, client only needs reply within current call | **TemporaryQueue per request** | Simple, but incurs create/delete overhead |
| One outbound gateway with many parallel requests | **Shared TemporaryQueue with reply listener** | Monitor in-flight mapping, listener, and reconnect |
| Broker forbids creating temporary destinations | **Fixed reply queue** | Explicit provisioning/ACL and correlation |
| Multiple gateways/instances share a governed reply queue | **Fixed reply queue + reply listener + `correlationKey`** | Verify unique selectors and avoid per-request consumer caching |
| Must receive reply after client restart | Do not rely on temporary destinations | Switch to async command/result protocol with durable storage |
| Server takes minutes to process | Consider request-acknowledgement + result event/status query | Do not hold thousands of requests waiting indefinitely |
| Strict temporary destination limits | Evaluate reply listener / fixed reply queue | Measure quotas and failover behavior |

**Decisive question:** does the reply need to survive **after the caller's connection closes**? If yes, a temporary destination **cannot meet** that requirement, even with persistent JMS delivery mode. Change the protocol rather than merely increasing retry counts.

## 14. Operational observability and capacity planning

Temporary reply queues are short-lived and hard to inspect by fixed queue name. Track each request by **business ID**, JMS metadata, and timing:

| Metric | Meaning |
|---|---|
| Requests sent/second | Rate of outbound JMS calls |
| Replies received/second | Rate of requests receiving matching replies |
| In-flight requests | Calls currently waiting for replies at the gateway |
| Reply latency p50/p95/p99 | End-to-end request-reply latency |
| Timeout rate | Share of requests receiving no reply within deadline |
| Late/unmatched replies | Indicator of delayed replies or correlation bugs |
| Temporary destination count | Active temporary queues/topics on the broker |
| Reply consumer count | Consumers waiting on gateway replies |
| Reconnect/recovery events | Connection drops and temporary destination recreation |
| Request queue depth/oldest age | Server backlog or slow processing |
| Conversion/business errors | Avoid confusing bad data with network timeouts |

For example, suppose cluster-wide in-flight requests total 200, each lasting up to 5 seconds. With one temporary queue per request, **hundreds of temporary destinations may exist simultaneously**. With a shared reply listener per gateway, temporary queue count tracks **active gateway instances** rather than request count directly; still, the app holds in-flight state and consumes resources per request.

When benchmarking, record both **broker metrics and JVM metrics**, because an option that reduces temporary queues can raise gateway heap usage or pressure on request processors.

## 15. Hands-on lab: observing temporary reply destinations on a real broker

**Environment:** Spring Integration 6+ (or your project's version), Java 17+, a test JMS broker, a client app, and a server with a JMS inbound gateway. The request queue is `inventory.check.requests`. No manual temporary reply queue needs to be pre-created in broker config; it is created per JMS operation. Test credentials must have permission to create/consume temporary destinations and send replies.

### Lab A — `JmsTemplate.sendAndReceive`

1. Create a `JmsTemplate` bean with `receiveTimeout(5000)`.
2. Have the server read `JMSReplyTo` from the request and send a `TextMessage` reply to that destination.
3. Send three requests with different `requestId` values; compare `JMSReplyTo` on each JMS request via metadata logs/broker console.
4. Inspect reply body and correlation ID rather than assuming success solely because `sendAndReceive` returned a `Message`.
5. Observe temporary queues/consumers being created and released; confirm with a real provider, not just mocks.

### Lab B — Outbound gateway without a reply listener

1. Run the client flow from section 5 with `receiveTimeout(5000)`.
2. Send 20 concurrent requests, each with a unique `requestId`.
3. Record how many temporary queues exist while requests wait; watch consumer counts.
4. Have the server return replies in reverse order; verify each caller receives its own JSON.
5. Measure elapsed time, session/consumer counts, and destination creation/deletion overhead.

### Lab C — Reply listener sharing a temporary queue

1. Replace the flow in section 5 with the `.replyContainer()` flow from section 6.
2. Send 20 requests again; observe them sharing the temporary queue of **one gateway instance**.
3. Verify correlation when replies arrive out of order.
4. Compare throughput, temporary destination counts, and consumer counts against Lab B.
5. Start a second gateway instance and verify each instance manages its own temporary destination.

### Lab D — Timeouts and late replies

1. Make the server take 8 seconds while the client waits 5 seconds.
2. With one temporary queue per request, check when the queue is deleted and what happens when the server tries to reply afterward.
3. With a shared reply listener, observe the late/unmatched reply and ensure it is never matched to another request.
4. Resend the **same `requestId`**; verify the server does not execute side effects twice.
5. Design a `getRequestStatus(requestId)` API or result event for long-running tasks.

### Lab E — Connection failover, ACLs, and operations

1. Drop the JMS connection while client requests are waiting; record timeouts/exceptions.
2. Bring the broker back up and verify whether the gateway/reply listener recreates its temporary queue.
3. Revoke the client's permission to create temporary destinations (in the test broker); observe errors and alerting.
4. Revoke the server's permission to send replies to temporary destinations; verify the client times out even though the server can receive requests.
5. Test a fixed reply queue with `correlationKey("JMSCorrelationID")` and a reply listener; verify replies are never misconsumed by other gateways.
6. Run a load test with `cacheConsumers=true` **in the test environment only** for a fixed reply queue using per-request selectors; observe why cached consumers accumulate.

### Expected results checklist

| Check | PASS signal |
|---|---|
| Client sets `JMSReplyTo` | JMS request contains a valid temporary destination |
| Server replies to the right place | Producer sends reply to the destination from the request |
| Reply matches request | Payload `requestId` and correlation match |
| Bounded timeout | Caller does not hang forever when server is silent |
| Late reply is not mismatched | Another request never receives data from a timed-out request |
| Temporary destinations cleaned up | Broker resources return to baseline after load |
| Connection loss observed | Clear metrics/logs and reconnect behavior |
| Retries cause no double effects | Server enforces idempotency by `requestId` |
| No cached-consumer leak | Consumer count does not grow unboundedly across many requests |

**Temporary destination lifecycles cannot be verified solely by unit tests mocking `ConnectionFactory` or `JmsTemplate`.** Use a real JMS provider/broker or matching test container, and test ACLs, timeouts, and recovery.

### Self-check questions

1. Does `TemporaryQueue` belong to the lifecycle of the creating `Session` or the JMS `Connection`?
2. Why can a server on a different connection still send a reply to the client's temporary queue?
3. Why can only the connection owning a temporary destination create a consumer to receive from it?
4. Distinguish JMS `JMSReplyTo` from Spring Integration `replyChannel`.
5. Without `replyDestination` configured, which reply destination does an outbound gateway choose?
6. What is the difference between **one `TemporaryQueue` per request** and **one `TemporaryQueue` per gateway with a reply listener**?
7. Why does a reply listener on a fixed reply destination require a properly configured correlation key?
8. Why can `cacheConsumers=true` cause problems on a fixed reply queue using per-request selectors?
9. What happens if the server sends a reply after the temporary queue has already been deleted?
10. Does a timeout prove the server failed to write to the database? Why or why not?
11. When does `replyPubSubDomain(true)` create a `TemporaryTopic`, and why should it not be enabled by default?
12. Why can holding an outbound JMS request inside an uncommitted transaction while waiting for a reply cause a timeout?
13. If results must survive a client restart, should you keep temporary destinations or change protocols?
14. Which metrics verify that a gateway using a reply listener genuinely reduces resource usage?

## 16. Official references

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): **Outbound Gateway**, `TemporaryQueue`, `TemporaryTopic`, `reply-listener`, correlation, and reply destination combinations.
- [Spring Integration API — JmsOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundGatewaySpec.html): `requestDestination`, `replyDestination`, `replyContainer`, `receiveTimeout`, `correlationKey`, `replyPubSubDomain`.
- [Spring Integration API — ReplyContainerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundGatewaySpec.ReplyContainerSpec.html): concurrency, recovery, and idle reply listeners.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate` and request-reply with temporary queues.
- [Spring Framework API — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `sendAndReceive`, `receiveTimeout`, and JMS resource management.
- [Jakarta Messaging Concepts — Creating Temporary Destinations](https://jakarta.ee/learn/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html): connection scope, consumer permissions, and lifecycle of temporary destinations.
- [Jakarta Messaging API — TemporaryQueue](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/TemporaryQueue.html): interface and `delete()` operation.

**Remember:** a temporary reply destination is a client-created JMS target for receiving responses in a request-reply exchange, whose lifecycle is tied to the JMS connection. Spring Integration's outbound gateway uses `TemporaryQueue` by default; **without a reply listener** it creates one queue per request, while **with a reply listener** it can share one queue per gateway. For reliability, honor `JMSReplyTo`, define correlation, bound timeouts, handle late replies, recovery, ACLs, and idempotency. Temporary destinations do **not** replace durable result storage across restarts.
